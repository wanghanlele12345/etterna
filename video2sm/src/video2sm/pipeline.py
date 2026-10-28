"""End-to-end: video in, playable Etterna song folder out."""

from __future__ import annotations

import json
import os
import re
import tempfile
import zlib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import align, beats, charting, dsp, events, features, layouts, media, repeats, ssc, stems, structure, titlecard
from .errors import AnalysisError, SimfileError

DEFAULT_GROUP = "video2sm"
# video2sm/ sits in the root of the game checkout, next to Songs/
DEFAULT_SONGS_DIR = Path(__file__).resolve().parents[3] / "Songs"
SONGS_DIR_ENV = "VIDEO2SM_SONGS_DIR"
BANNER_SIZE = (512, 160)
BACKGROUND_SIZE = (1280, 720)
CHART_SOURCES = ("auto", "stems", "mix")
_UNSAFE_PATH_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


@dataclass(frozen=True)
class ChartSummary:
    steps_type: str
    difficulty: str
    meter: int
    rows: int
    notes: int
    jumps: int
    holds: int
    average_rows_per_second: float
    peak_rows_per_second: float


@dataclass(frozen=True)
class BuildResult:
    song_dir: Path
    ssc_path: Path
    title: str
    bpm: float
    offset: float
    confidence: float
    duration: float
    charts: tuple[ChartSummary, ...]
    warnings: tuple[str, ...]
    chart_source: str = "mix"  # "stems": built from separated vocals/drums; "mix": from the full mix
    melody_notes: int = 0  # sung notes read from the vocal stem
    aligned_notes: int = 0  # notes moved onto the exact attack they answer


def default_songs_dir() -> Path:
    return Path(os.environ.get(SONGS_DIR_ENV, DEFAULT_SONGS_DIR))


def safe_name(value: str, fallback: str = "song") -> str:
    cleaned = _UNSAFE_PATH_CHARS.sub(" ", value)
    cleaned = " ".join(cleaned.split()).strip(". ")
    return cleaned or fallback


def _stable_seed(title: str) -> int:
    return zlib.crc32(title.encode("utf-8"))


def _summaries(
    chart_list: Sequence[charting.Chart], slot_seconds: float
) -> tuple[ChartSummary, ...]:
    out = []
    for chart in chart_list:
        stats = charting.chart_stats(chart, slot_seconds)
        out.append(
            ChartSummary(
                steps_type=chart.steps_type,
                difficulty=chart.name,
                meter=chart.meter,
                rows=stats.rows,
                notes=stats.notes,
                jumps=stats.jumps,
                holds=stats.holds,
                average_rows_per_second=stats.average_rows_per_second,
                peak_rows_per_second=stats.peak_rows_per_second,
            )
        )
    return tuple(out)


def _add_visuals(
    info: media.MediaInfo, song_dir: Path, preview_start: float, include_video: bool
) -> tuple[str, str, str]:
    """Create banner/background/video; returns their file names ('' if absent)."""
    if not info.has_video:
        return "", "", ""
    banner = media.extract_frame(
        info.path, song_dir / "banner.png", preview_start, *BANNER_SIZE
    )
    background = media.extract_frame(
        info.path, song_dir / "bg.png", info.duration * 0.1, *BACKGROUND_SIZE
    )
    video_name = ""
    if include_video:
        video_name = media.transcode_background(info.path, song_dir / "video.mp4").name
    return banner.name, background.name, video_name


def _music_features(
    audio_path: Path,
    analysis: beats.BeatAnalysis,
    n_slots: int,
    chart_source: str,
) -> tuple[events.MusicFeatures | None, tuple[str, ...]]:
    """Stem-based features when asked for and possible, else None plus the reason why not."""
    if chart_source == "mix":
        return None, ()
    if not stems.available():
        if chart_source == "stems":
            raise AnalysisError(stems.INSTALL_HINT)
        return None, (f"charts are built from the full mix: {stems.INSTALL_HINT}",)
    try:
        separated = stems.separate(audio_path)
        return events.music_from_stems(separated, analysis, n_slots), ()
    except AnalysisError as exc:
        if chart_source == "stems":
            raise
        return None, (f"charts are built from the full mix because separation failed: {exc}",)


MUSIC_FACTS_FILE = "music.json"


def _write_music_facts(
    song_dir: Path,
    grid: features.GridFeatures,
    music: events.MusicFeatures | None,
    analysis: beats.BeatAnalysis,
    mix: dsp.Audio,
) -> None:
    """Save what was heard (melody, drum hits) beside the song, for reviewing its charts."""
    heard = music or events.MusicFeatures(
        n_slots=grid.n_slots,
        slot_seconds=grid.slot_seconds,
        first_beat_time=grid.first_beat_time,
        drum_strengths=grid.strengths,
        vocal_strengths=np.zeros(grid.n_slots),
        melody=(),
        drum_onsets=events.band_onsets(mix),
    )
    facts = events.music_facts(heard, analysis.bpm, "stems" if music is not None else "mix")
    matrix, energy = structure.measure_features(mix, analysis, grid.n_measures)
    sections = structure.sections_from_features(matrix, structure.section_count(grid.n_measures))
    facts.update(structure.describe(sections, energy))
    facts["repeats"] = repeats.describe(repeats.find_repeats(repeats.melody_by_measure(facts)))
    (song_dir / MUSIC_FACTS_FILE).write_text(json.dumps(facts, ensure_ascii=False), encoding="utf-8")


def build_song(
    video: Path,
    songs_dir: Path | None = None,
    title: str | None = None,
    artist: str = "Unknown Artist",
    group: str = DEFAULT_GROUP,
    difficulties: Sequence[str] = charting.DEFAULT_DIFFICULTIES,
    include_video: bool = True,
    seed: int | None = None,
    key_modes: Sequence[str] = layouts.DEFAULT_KEY_MODES,
    holds: bool = True,
    chart_source: str = "auto",
    align_to_audio: bool = True,
) -> BuildResult:
    profiles = charting.resolve_profiles(difficulties)  # fail fast, before any ffmpeg work
    if chart_source not in CHART_SOURCES:
        raise ValueError(
            f"unknown chart source {chart_source!r}; valid chart sources: {', '.join(CHART_SOURCES)}"
        )
    key_layouts = layouts.resolve_layouts(key_modes)
    info = media.probe(video)
    song_title = (title or info.path.stem).strip() or "Untitled"
    folder = safe_name(song_title)
    root = Path(songs_dir) if songs_dir else default_songs_dir()
    song_dir = root / safe_name(group, DEFAULT_GROUP) / folder
    song_dir.mkdir(parents=True, exist_ok=True)

    audio_name = f"{folder}.ogg"
    audio_path = media.extract_audio(info.path, song_dir / audio_name)
    audio = dsp.load_audio(audio_path)  # analyse what the game will actually play

    analysis = beats.analyze_beats(audio)
    grid = features.extract_grid_features(audio, analysis)
    preview = features.preview_window(audio)
    chart_seed = _stable_seed(song_title) if seed is None else seed
    music, source_warnings = _music_features(audio_path, analysis, grid.n_slots, chart_source)
    chart_list = tuple(
        charting.generate_chart(grid, profile, chart_seed, layout, holds, music=music)
        for layout in key_layouts
        for profile in profiles
    )

    banner, background, video_name = _add_visuals(info, song_dir, preview[0], include_video)
    meta = ssc.SongMeta(
        title=song_title,
        artist=artist,
        music=audio_name,
        banner=banner,
        background=background,
        video=video_name,
    )
    ssc_path = song_dir / f"{folder}.ssc"
    ssc_path.write_text(ssc.render_ssc(meta, analysis, preview, chart_list), encoding="utf-8")

    _write_music_facts(song_dir, grid, music, analysis, audio)
    titlecard.write_cards(song_dir, song_title, artist)
    aligned = 0
    if align_to_audio:
        aligned = sum(c["moved"] for c in align.align_chart(ssc_path)["charts"])

    report = ssc.validate_ssc(ssc_path)
    if not report.ok:
        raise SimfileError("generated simfile failed validation: " + "; ".join(report.problems))

    return BuildResult(
        song_dir=song_dir,
        ssc_path=ssc_path,
        title=song_title,
        bpm=analysis.bpm,
        offset=analysis.offset,
        confidence=analysis.confidence,
        duration=info.duration,
        charts=_summaries(chart_list, grid.slot_seconds),
        warnings=analysis.warnings + source_warnings,
        chart_source="stems" if music is not None else "mix",
        melody_notes=len(music.melody) if music is not None else 0,
        aligned_notes=aligned,
    )


def analyze_notes(video: Path, max_notes: int = 200) -> dict[str, Any]:
    """What the music contains: tempo, the vocal melody's notes and the drum hits. Writes nothing."""
    info = media.probe(video)
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = media.extract_audio(info.path, Path(tmp) / "audio.ogg")
        mix = dsp.load_audio(audio_path)
        analysis = beats.analyze_beats(mix)
        grid = features.extract_grid_features(mix, analysis)
        separated = stems.separate(audio_path)  # raises with an install hint if Demucs is missing
        music = events.music_from_stems(separated, analysis, grid.n_slots)
    return {
        "duration": info.duration,
        "bpm": analysis.bpm,
        "offset": analysis.offset,
        "confidence": analysis.confidence,
        **events.describe_music(music, max_notes),
    }
