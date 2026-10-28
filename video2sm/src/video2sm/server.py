"""MCP server exposing the video -> Etterna song pipeline as tools."""

from __future__ import annotations

import functools
import io
import tempfile
from importlib import resources
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import align, beats, charting, download, dsp, layouts, media, pipeline, review, ssc, view
from .errors import Video2SmError

_F = TypeVar("_F", bound=Callable[..., Any])

INSTRUCTIONS = """\
Turns a music video into a playable Etterna (StepMania) song: audio, beat-synced
.ssc charts, banner, background image and background video, written straight
into the Songs folder.

The charts are a dance for the fingers on a simplified MIDI keyboard, and YOU are the
choreographer. The code gives you senses and checks; it should not make the musical
decisions. make_song_from_video produces a first draft plus a music.json (melody notes,
drum hits, sections, loudness) beside it. Then rework the draft with your own judgement:
choreography_guide explains what a good chart feels like and the working method;
inspect_chart shows measures next to the music they follow (including which stretches
are a reprise of earlier ones); view_chart draws that as a picture; look_at_video shows
frames of the video; edit_chart applies your rewritten measures and refuses anything
unplayable; align_chart finally snaps every note onto the exact attack it answers. Prefer a clear, repeating shape that answers the
music over notes that merely line up with onsets.

Source can be a local file (make_song_from_video) or a YouTube link
(make_song_from_url / download_video). Only download material the user has the
right to use (public domain, CC0, their own work) and say which in rights_basis.

Typical use: call make_song_from_video with the video path, then tell the user to
restart Etterna (or reload songs) to see it. Difficulty is low / medium / high
(Easy / Medium / Hard); the default is beginner + those three, and 'challenge'
is also accepted.
Charts are 7-key (kb7-single, the default: S D F space J K L), 4-key (dance-single)
and/or 9-key (pnm-nine, pop'n) via key_modes;
medium and harder charts include hold notes unless holds is false.

Charts follow the music when Demucs is installed (chart_source auto/stems): the melody
sets which lane each note is on (higher pitch, further right) and long sung notes become
holds, with kick/snare/hi-hat from the drum stem filling in. The melody is the voice's,
except in measures where the other instruments (strings, guitar, piano) are clearly louder,
where it is theirs (music.json "lead" says who leads each measure); Hard and Challenge also
follow the second loudest melodic part ("second_melody"). Without Demucs, or with
chart_source "mix", notes come from onsets in the full mix only. analyze_video_notes
shows what was heard (melody notes, drum hits) without creating anything.
If the notes feel early or late in-game, call adjust_song_offset with a small
delta in milliseconds (positive = notes later) and have the user re-test.
"""

mcp = MCPServer("video2sm", instructions=INSTRUCTIONS)


def _reported(func: _F) -> _F:
    """Show expected failures (bad input, ffmpeg errors) to the agent.

    The framework hides every other exception's text from the client, so only
    errors we raise on purpose are converted; real crashes stay opaque.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except (Video2SmError, ValueError) as exc:
            raise ToolError(str(exc)) from exc

    return wrapper  # type: ignore[return-value]


def _beat_report(analysis: beats.BeatAnalysis) -> dict[str, Any]:
    return {
        "bpm": analysis.bpm,
        "offset": analysis.offset,
        "confidence": analysis.confidence,
        "stability_ms": analysis.stability_ms,
        "warnings": list(analysis.warnings),
    }


@mcp.tool()
@_reported
def make_song_from_video(
    video_path: str,
    title: str | None = None,
    artist: str = "Unknown Artist",
    difficulties: list[str] | None = None,
    group: str = pipeline.DEFAULT_GROUP,
    include_video: bool = True,
    songs_dir: str | None = None,
    key_modes: list[str] | None = None,
    holds: bool = True,
    chart_source: str = "auto",
) -> dict[str, Any]:
    """Convert a music video into a ready-to-play Etterna song folder.

    Args:
        video_path: Path to the video (any format ffmpeg reads; must have audio).
        title: Song title; defaults to the file name.
        artist: Artist name.
        difficulties: Any of "low", "medium", "high" (-> Easy, Medium, Hard),
            plus "beginner", "challenge", or "all". Defaults to beginner, low,
            medium, high.
        group: Song pack (folder) name inside Songs/.
        include_video: Use the video as the in-game background (otherwise the
            background is a still frame).
        songs_dir: Override the Etterna Songs folder (default: the built project's
            Songs directory, or $VIDEO2SM_SONGS_DIR).
        key_modes: Any of "kb7-single" ("7k"), "dance-single" ("4k") and "pnm-nine"
            ("9k", "popn"); each adds a chart per difficulty to the same song.
            Defaults to kb7-single. Each mode only shows in the matching Etterna game
            mode (kb7 plays on S D F space J K L by default; popn needs its nine
            buttons bound by hand).
        holds: Add hold notes where sung notes are sustained (default true).
        chart_source: "auto" (default) follows the music with separated stems (vocal
            melody sets the lanes, drums fill in) when Demucs is installed and falls
            back to the full mix otherwise; "stems" requires it; "mix" never separates.
            The first separation of a song takes about a minute; results are cached.
    """
    result = pipeline.build_song(
        Path(video_path),
        songs_dir=Path(songs_dir) if songs_dir else None,
        title=title,
        artist=artist,
        group=group,
        difficulties=difficulties or list(charting.DEFAULT_DIFFICULTIES),
        include_video=include_video,
        key_modes=key_modes or list(layouts.DEFAULT_KEY_MODES),
        holds=holds,
        chart_source=chart_source,
    )
    payload = asdict(result)
    payload["song_dir"] = str(result.song_dir)
    payload["ssc_path"] = str(result.ssc_path)
    payload["warnings"] = list(result.warnings)
    payload["next_step"] = (
        "Restart Etterna or reload songs, then pick the song. If notes feel "
        "early/late, use adjust_song_offset."
    )
    return payload


def _downloaded_payload(item: download.Downloaded, rights_basis: str) -> dict[str, Any]:
    return {
        "path": str(item.path),
        "title": item.title,
        "uploader": item.uploader,
        "duration": item.duration,
        "youtube_license": item.license,
        "source_url": item.source_url,
        "rights_basis": rights_basis,
    }


def _require_rights_basis(rights_basis: str) -> str:
    cleaned = rights_basis.strip()
    if not cleaned:
        raise ValueError(
            "rights_basis is required: say why this may be used "
            "(e.g. 'public domain: US Marine Band recording', 'CC0', 'own work')"
        )
    return cleaned


@mcp.tool()
@_reported
def download_video(url: str, rights_basis: str, max_height: int = 720) -> dict[str, Any]:
    """Download a YouTube video to the local downloads folder.

    Args:
        url: An https YouTube link (single video; playlists are not expanded).
        rights_basis: Required. Why the user may use this (e.g. "public domain",
            "CC0", "own work"). Recorded in the result; the tool does not verify it.
        max_height: Highest video resolution to fetch.

    The result includes the licence YouTube declares (often null), which is not
    proof of public-domain status; check the source yourself.
    """
    basis = _require_rights_basis(rights_basis)
    item = download.download_video(url, max_height=max_height)
    return _downloaded_payload(item, basis)


@mcp.tool()
@_reported
def make_song_from_url(
    url: str,
    rights_basis: str,
    title: str | None = None,
    artist: str | None = None,
    difficulties: list[str] | None = None,
    group: str = pipeline.DEFAULT_GROUP,
    include_video: bool = True,
    songs_dir: str | None = None,
    key_modes: list[str] | None = None,
    holds: bool = True,
    chart_source: str = "auto",
) -> dict[str, Any]:
    """Download a YouTube video and convert it to an Etterna song in one step.

    Same options as make_song_from_video, plus rights_basis (required; why the
    user may use this material). Title and artist default to the YouTube metadata.
    """
    basis = _require_rights_basis(rights_basis)
    item = download.download_video(url)
    result = make_song_from_video(
        video_path=str(item.path),
        title=title or item.title,
        artist=artist or item.uploader or "Unknown Artist",
        difficulties=difficulties,
        group=group,
        include_video=include_video,
        songs_dir=songs_dir,
        key_modes=key_modes,
        holds=holds,
        chart_source=chart_source,
    )
    return {**result, "source": _downloaded_payload(item, basis)}


@mcp.tool()
@_reported
def analyze_video_beats(video_path: str) -> dict[str, Any]:
    """Detect BPM, first-beat offset and confidence without creating any files.

    Use this to check whether a video has a steady, detectable beat before
    generating charts.
    """
    info = media.probe(Path(video_path))
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = media.extract_audio(info.path, Path(tmp) / "audio.ogg")
        analysis = beats.analyze_beats(dsp.load_audio(audio_path))
    return {"duration": info.duration, "has_video": info.has_video, **_beat_report(analysis)}


@mcp.tool()
@_reported
def analyze_video_notes(video_path: str, max_notes: int = 200) -> dict[str, Any]:
    """Read the music's notes without creating any files.

    Separates the audio into vocals and drums (needs Demucs; the first run on a song takes
    about a minute, later runs use a cache), then returns the tempo, the lead melody (the
    voice, or the other instruments where they are louder) as a list of notes (time, length, MIDI number, note name, loudness), the pitch range, and how
    many kick, snare and hi-hat hits were found.

    Args:
        video_path: Path to the video (any format ffmpeg reads; must have audio).
        max_notes: How many melody notes to list (the count covers all of them).
    """
    return pipeline.analyze_notes(Path(video_path), max_notes=max_notes)


@mcp.tool()
def choreography_guide() -> str:
    """How to choreograph a chart: what a good one feels like, difficulty, and the working method.

    Read this before reworking a draft with inspect_chart, view_chart and edit_chart.
    """
    return (resources.files("video2sm") / "choreography.md").read_text(encoding="utf-8")


@mcp.tool()
@_reported
def inspect_chart(
    ssc_path: str,
    difficulty: str,
    start_measure: int = 0,
    measures: int = 16,
    steps_type: str | None = None,
) -> dict[str, Any]:
    """Show part of a chart next to the music it should follow, to review or rework it.

    The text lists, for each measure (16 slots, s0 = downbeat): the sung melody notes
    (NAME@SLOT/LENGTH), the kick/snare/hat slots, which earlier measures it sounds like,
    and the chart's notes. The stats cover the whole chart: density against the
    difficulty's target, how many notes have something to hear nearby, how consistent the
    rhythm patterns are, and how many moves are beyond comfortable reach.

    Args:
        ssc_path: The song's .ssc (a music.json written by make_song_from_video sits beside it).
        difficulty: Easy, Medium, Hard, ... (as named in the file).
        start_measure: First measure to show (0-based).
        measures: How many measures to show.
        steps_type: Only needed when the same difficulty exists for several key modes.
    """
    return review.inspect_chart(
        Path(ssc_path), difficulty, start=start_measure, count=measures, steps_type=steps_type
    )


@mcp.tool()
@_reported
def view_chart(
    ssc_path: str,
    difficulty: str,
    start_measure: int = 0,
    measures: int = 8,
    steps_type: str | None = None,
) -> Image:
    """Look at a chart: a picture of measures and the music they follow.

    Time runs downward. Left: the sung melody (further right = higher pitch, bar length =
    how long it is held). Middle: the lanes with the chart's notes, white/blue/yellow like
    the keys, holds as long bars. Right: kick (circle), snare (square) and hi-hat (cross).
    A thin line from each melody onset runs across the lanes. Use it to judge whether the
    choreography has a clear, repeating shape and answers the music.
    """
    picture = view.render_chart(
        Path(ssc_path), difficulty, start=start_measure, count=measures, steps_type=steps_type
    )
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    return Image(data=buffer.getvalue(), format="png")


@mcp.tool()
@_reported
def look_at_video(
    video_path: str, count: int = 8, at_seconds: list[float] | None = None
) -> Image:
    """See the video: a contact sheet of frames, each labelled with its time.

    Use it to understand what is on screen (performers, scene changes, lyrics, mood) when
    deciding how the choreography should feel. Frames are evenly spaced unless at_seconds
    lists the moments to look at (e.g. the start of each section from inspect_chart).
    """
    sheet = view.contact_sheet(Path(video_path), at_seconds, count=count)
    buffer = io.BytesIO()
    sheet.save(buffer, format="PNG")
    return Image(data=buffer.getvalue(), format="png")


@mcp.tool()
@_reported
def edit_chart(
    ssc_path: str,
    difficulty: str,
    edits: list[dict[str, Any]],
    steps_type: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Rewrite measures of a chart. The choreography is yours; this checks and applies it.

    Notation for a measure's notes: s4:3 (tap on lane 3 at slot 4), s8:2+6 (jump),
    s8:H3 (hold starts on lane 3), s12:|3 (that hold ends). Lanes count from 1, left to
    right; slots 0-15 per measure.

    Edits (applied in order): {"measure": 5, "notes": "s0:4 s8:3"} replaces a measure,
    {"copy": {"from": 5, "to": [9, 13]}} repeats a measure, {"repeat": {"from": [41, 54],
    "to": 97}} copies a whole reprised section, {"clear": [20, 21]} empties measures. If any edit is malformed, a hold is left open, a lane is pressed while held,
    or more than two lanes are pressed at once, nothing is changed and `errors` says why.
    `warnings` (not refusals) flag density above the difficulty, leaps beyond reach, jumps
    during holds, and notes with nothing to hear nearby. Use dry_run to check without writing.
    """
    return review.edit_chart(
        Path(ssc_path), difficulty, edits, steps_type=steps_type, dry_run=dry_run
    )


@mcp.tool()
@_reported
def align_chart(
    ssc_path: str,
    difficulty: str | None = None,
    steps_type: str | None = None,
    tolerance_ms: float = 90.0,
) -> dict[str, Any]:
    """Snap notes to the exact moment their sound is heard; run it after choreographing.

    Keeps every choreographic choice (notes, lanes, holds, jumps) and only nudges timing:
    each note moves onto the sung attack or drum hit it answers if one is within
    tolerance_ms, and each hold ends when the sung note it holds ends. Written with fine
    rows, so the chart follows the singer to within a few milliseconds. Aligns every chart
    unless a difficulty is given. Editing afterwards puts edited measures back on the grid;
    align again when done.
    """
    return align.align_chart(
        Path(ssc_path), difficulty, steps_type, tolerance_seconds=tolerance_ms / 1000
    )


@mcp.tool()
@_reported
def validate_song(ssc_path: str) -> dict[str, Any]:
    """Check an .ssc parses, has notes and sane timing, and its files exist."""
    report = ssc.validate_ssc(Path(ssc_path))
    return {"ok": report.ok, "problems": list(report.problems), "charts": list(report.chart_names)}


@mcp.tool()
@_reported
def adjust_song_offset(ssc_path: str, delta_ms: float) -> dict[str, Any]:
    """Nudge chart sync. Positive delta_ms makes notes arrive later, negative earlier.

    Typical fixes are 10-50 ms. Edits only the #OFFSET value.
    """
    path = Path(ssc_path)
    new_offset = ssc.adjust_offset(path, -delta_ms)
    return {"ssc_path": str(path), "offset": new_offset}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
