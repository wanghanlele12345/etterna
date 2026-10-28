from pathlib import Path

import pytest
import simfile
from simfile.timing import Beat, TimingData
from simfile.timing.engine import TimingEngine

from tests.conftest import TRUE_BPM, TRUE_FIRST_BEAT
from video2sm import pipeline, ssc, stems, titlecard
from video2sm.errors import MediaError


@pytest.fixture(scope="module")
def built(click_video: Path, tmp_path_factory: pytest.TempPathFactory) -> pipeline.BuildResult:
    songs = tmp_path_factory.mktemp("Songs")
    # a module-scoped fixture runs before the per-test autouse patches, so switch off the
    # heavy optional parts (stem separation, system fonts) here
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(stems, "_installed", lambda name: False)
        patch.setattr(titlecard, "find_font", lambda: None)
        return pipeline.build_song(
            click_video, songs_dir=songs, title="Click: Test", artist="Metronome",
            group="Tests", difficulties=["low", "medium", "high"],
        )


def test_creates_complete_song_folder(built: pipeline.BuildResult) -> None:
    names = {p.name for p in built.song_dir.iterdir()}
    assert names == {"Click Test.ogg", "Click Test.ssc", "banner.png", "bg.png", "video.mp4", "music.json"}
    assert built.song_dir.parent.name == "Tests"


def test_simfile_is_valid_and_has_chosen_difficulties(built: pipeline.BuildResult) -> None:
    report = ssc.validate_ssc(built.ssc_path)
    assert report.ok, report.problems
    assert report.chart_names == ("Easy", "Medium", "Hard")
    assert [c.difficulty for c in built.charts] == ["Easy", "Medium", "Hard"]


def test_title_with_special_chars_is_kept_in_simfile(built: pipeline.BuildResult) -> None:
    assert simfile.open(str(built.ssc_path)).title == "Click: Test"


def test_sync_is_accurate_end_to_end(built: pipeline.BuildResult) -> None:
    sim = simfile.open(str(built.ssc_path))
    engine = TimingEngine(TimingData(sim))
    period = 60.0 / TRUE_BPM
    # Any beat of the detected grid must land on a true beat (vorbis re-encode included).
    for beat in (0, 17, 40):
        t = engine.time_at(Beat(beat))
        error = (t - TRUE_FIRST_BEAT) % period
        assert min(error, period - error) < 0.015
    assert built.bpm == pytest.approx(TRUE_BPM, abs=0.1)


def test_harder_charts_are_denser(built: pipeline.BuildResult) -> None:
    rows = [c.rows for c in built.charts]
    assert rows == sorted(rows) and rows[0] < rows[-1]


def test_can_skip_video(click_video: Path, tmp_path: Path) -> None:
    result = pipeline.build_song(click_video, songs_dir=tmp_path, difficulties=["high"], include_video=False)
    assert not (result.song_dir / "video.mp4").exists()
    assert "#BGCHANGES" not in result.ssc_path.read_text(encoding="utf-8")
    assert (result.song_dir / "bg.png").exists()


def test_bad_difficulty_fails_before_any_work(click_video: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="difficult"):
        pipeline.build_song(click_video, songs_dir=tmp_path, difficulties=["nightmare"])
    assert list(tmp_path.iterdir()) == []


def test_missing_video(tmp_path: Path) -> None:
    with pytest.raises(MediaError):
        pipeline.build_song(tmp_path / "x.mp4", songs_dir=tmp_path)


def test_safe_name() -> None:
    assert pipeline.safe_name('a/b:c*"d"') == "a b c d"
    assert pipeline.safe_name("...") == "song"


def test_builds_several_key_modes_into_one_simfile(click_video: Path, tmp_path: Path) -> None:
    result = pipeline.build_song(
        click_video, songs_dir=tmp_path, difficulties=["medium", "high"], key_modes=["4k", "9k"]
    )
    assert [(c.steps_type, c.difficulty) for c in result.charts] == [
        ("dance-single", "Medium"), ("dance-single", "Hard"),
        ("pnm-nine", "Medium"), ("pnm-nine", "Hard"),
    ]
    assert ssc.validate_ssc(result.ssc_path).ok
    charts = simfile.open(str(result.ssc_path)).charts
    assert [c.stepstype for c in charts] == ["dance-single"] * 2 + ["pnm-nine"] * 2


def test_default_key_mode_is_seven_key(built: pipeline.BuildResult) -> None:
    assert {c.steps_type for c in built.charts} == {"kb7-single"}


def test_seven_key_song_validates_and_declares_seven_columns(built: pipeline.BuildResult) -> None:
    assert ssc.validate_ssc(built.ssc_path).ok
    charts = simfile.open(str(built.ssc_path)).charts
    assert {c.stepstype for c in charts} == {"kb7-single"}


def test_bad_key_mode_fails_before_any_work(click_video: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="key mode"):
        pipeline.build_song(click_video, songs_dir=tmp_path, key_modes=["12k"])
    assert list(tmp_path.iterdir()) == []


def test_holds_can_be_turned_off(click_video: Path, tmp_path: Path) -> None:
    result = pipeline.build_song(
        click_video, songs_dir=tmp_path, difficulties=["all"], holds=False
    )
    assert all(c.holds == 0 for c in result.charts)
    text = result.ssc_path.read_text(encoding="utf-8")
    assert not any(set(line) <= set("0123") and ("2" in line or "3" in line) for line in text.splitlines())


def test_built_charts_pass_validation_with_holds(click_video: Path, tmp_path: Path) -> None:
    result = pipeline.build_song(click_video, songs_dir=tmp_path, difficulties=["all"], key_modes=["9k"])
    assert ssc.validate_ssc(result.ssc_path).ok


# --- charts from separated stems ---------------------------------------------------------

import numpy as np  # noqa: E402

from tests.conftest import TRUE_BPM, TRUE_FIRST_BEAT, vocal_pitch  # noqa: E402
from video2sm import dsp, stems  # noqa: E402
from video2sm.errors import AnalysisError  # noqa: E402


@pytest.fixture()
def fake_stems(monkeypatch: pytest.MonkeyPatch, click_wav: Path, vocal_wav: Path) -> stems.Stems:
    drums = dsp.load_audio(click_wav)
    silent = dsp.Audio(samples=np.zeros_like(drums.samples), sample_rate=drums.sample_rate)
    result = stems.Stems(vocals=dsp.load_audio(vocal_wav), drums=drums, bass=silent, other=silent)
    monkeypatch.setattr(stems, "available", lambda: True)
    monkeypatch.setattr(stems, "separate", lambda source, **kw: result)
    return result


def build_stem_song(click_video: Path, tmp_path: Path, **kwargs) -> pipeline.BuildResult:
    options = dict(difficulties=["high"], key_modes=["7k"], holds=False, songs_dir=tmp_path)
    options.update(kwargs)
    return pipeline.build_song(click_video, **options)


def test_stem_charts_report_their_source(click_video: Path, tmp_path: Path, fake_stems) -> None:
    result = build_stem_song(click_video, tmp_path, chart_source="stems")
    assert result.chart_source == "stems"
    assert result.melody_notes >= 50
    assert ssc.validate_ssc(result.ssc_path).ok


def test_stem_chart_lanes_follow_the_sung_pitch(click_video: Path, tmp_path: Path, fake_stems) -> None:
    from simfile.notes import NoteData, NoteType

    result = build_stem_song(click_video, tmp_path, chart_source="stems")
    period = 60.0 / TRUE_BPM
    shift = round((-result.offset - TRUE_FIRST_BEAT) / period)  # grid beat 0 is sung beat `shift`
    chart = simfile.open(str(result.ssc_path)).charts[0]
    pairs = [
        (vocal_pitch(round(float(n.beat)) + shift), n.column)
        for n in NoteData(chart)
        if n.note_type == NoteType.TAP and abs(float(n.beat) - round(float(n.beat))) < 0.01
    ]
    assert len(pairs) >= 30
    ranks = [np.argsort(np.argsort(values)) for values in zip(*pairs)]
    assert float(np.corrcoef(ranks[0], ranks[1])[0, 1]) > 0.6


def test_auto_uses_stems_when_available(click_video: Path, tmp_path: Path, fake_stems) -> None:
    assert build_stem_song(click_video, tmp_path).chart_source == "stems"


def test_auto_falls_back_to_the_mix_without_demucs(
    click_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stems, "available", lambda: False)
    result = build_stem_song(click_video, tmp_path)
    assert result.chart_source == "mix" and result.melody_notes == 0
    assert any("uv sync --extra stems" in w for w in result.warnings)


def test_auto_falls_back_when_separation_fails(
    click_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(source, **kw):
        raise AnalysisError("demucs failed: out of memory")

    monkeypatch.setattr(stems, "available", lambda: True)
    monkeypatch.setattr(stems, "separate", boom)
    result = build_stem_song(click_video, tmp_path)
    assert result.chart_source == "mix"
    assert any("out of memory" in w for w in result.warnings)


def test_stems_mode_fails_loudly_when_demucs_is_missing(
    click_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stems, "available", lambda: False)
    with pytest.raises(AnalysisError, match="uv sync --extra stems"):
        build_stem_song(click_video, tmp_path, chart_source="stems")


def test_mix_mode_never_separates(click_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kw):
        raise AssertionError("separation must not run in mix mode")

    monkeypatch.setattr(stems, "available", lambda: True)
    monkeypatch.setattr(stems, "separate", boom)
    result = build_stem_song(click_video, tmp_path, chart_source="mix")
    assert result.chart_source == "mix" and not result.warnings


def test_bad_chart_source_fails_before_any_work(click_video: Path, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="chart source"):
        pipeline.build_song(click_video, songs_dir=tmp_path, chart_source="magic")
    assert list(tmp_path.iterdir()) == []


# --- music.json ------------------------------------------------------------------------------


def test_song_folder_includes_the_music_facts(click_video: Path, tmp_path: Path, fake_stems) -> None:
    import json

    result = build_stem_song(click_video, tmp_path, chart_source="stems")
    facts = json.loads((result.song_dir / "music.json").read_text(encoding="utf-8"))
    assert facts["chart_source"] == "stems" and len(facts["melody"]) >= 50
    assert facts["bpm"] == pytest.approx(TRUE_BPM, abs=0.1)
    assert len(facts["drums"]["kick"]) > 20
    assert len(facts["energy"]) == facts["n_slots"] // 16
    assert facts["sections"][0]["start"] == 0 and facts["sections"][-1]["end"] == len(facts["energy"]) - 1


def test_music_facts_exist_in_mix_mode_too(click_video: Path, tmp_path: Path) -> None:
    import json

    result = build_stem_song(click_video, tmp_path, chart_source="mix")
    facts = json.loads((result.song_dir / "music.json").read_text(encoding="utf-8"))
    assert facts["chart_source"] == "mix" and facts["melody"] == []
    assert sum(len(v) for v in facts["drums"].values()) > 20



def test_built_song_lists_repeats_and_is_aligned_to_the_audio(click_video: Path, tmp_path: Path, fake_stems) -> None:
    import json

    result = build_stem_song(click_video, tmp_path, chart_source="stems")
    facts = json.loads((result.song_dir / "music.json").read_text(encoding="utf-8"))
    assert "repeats" in facts and isinstance(facts["repeats"], list)
    # the synthetic vocal rises in a 28-beat (7-measure) cycle: the melody repeats
    assert any(r["target"][0] - r["source"][0] == 7 for r in facts["repeats"])
    assert result.aligned_notes > 0
    assert ssc.validate_ssc(result.ssc_path).ok


def test_alignment_can_be_skipped(click_video: Path, tmp_path: Path, fake_stems) -> None:
    result = build_stem_song(click_video, tmp_path, chart_source="stems", align_to_audio=False)
    assert result.aligned_notes == 0
