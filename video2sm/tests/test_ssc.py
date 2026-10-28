from pathlib import Path

import pytest
import simfile
from simfile.notes import NoteData
from simfile.timing import Beat, TimingData
from simfile.timing.engine import TimingEngine

from video2sm import ssc
from video2sm.beats import BeatAnalysis
from video2sm.charting import Chart
from video2sm.errors import SimfileError

ANALYSIS = BeatAnalysis(bpm=128.0, first_beat_time=0.234, confidence=0.9, stability_ms=2.0, duration=60.0)
MEASURE = ("1000", "0000", "0100", "0000", "0010", "0000", "0001", "0000")
CHART = Chart("Hard", 9, (MEASURE, ("0000",) * 4, MEASURE))
META = ssc.SongMeta(
    title="My: Song; (test)", artist="Some Artist", music="song.ogg",
    banner="banner.png", background="bg.png", video="video.mp4",
)


def render(**overrides) -> str:
    return ssc.render_ssc(META, ANALYSIS, (20.0, 12.0), (CHART,), **overrides)


def test_renders_parseable_ssc_with_correct_timing() -> None:
    sim = simfile.loads(render())
    assert sim.music == "song.ogg" and sim.banner == "banner.png"
    assert float(sim.offset) == pytest.approx(-0.234)
    engine = TimingEngine(TimingData(sim))
    assert engine.time_at(Beat(0)) == pytest.approx(0.234, abs=1e-6)
    assert engine.time_at(Beat(4)) == pytest.approx(0.234 + 4 * 60 / 128, abs=1e-3)


def test_special_characters_are_escaped_and_round_trip() -> None:
    assert simfile.loads(render()).title == "My: Song; (test)"


def test_chart_notes_survive_round_trip() -> None:
    chart = simfile.loads(render()).charts[0]
    assert (chart.difficulty, chart.meter, chart.stepstype) == ("Hard", "9", "dance-single")
    assert len(list(NoteData(chart))) == 8


def test_video_background_is_declared() -> None:
    text = render()
    assert "#BGCHANGES:0.000=video.mp4=" in text and "-nosongbg-" in text
    assert "#BGCHANGES" not in ssc.render_ssc(
        ssc.SongMeta(title="t", artist="a", music="s.ogg"), ANALYSIS, (0.0, 10.0), (CHART,)
    )


def test_validate_accepts_good_file(tmp_path: Path) -> None:
    (tmp_path / "song.ogg").write_bytes(b"x")
    (tmp_path / "banner.png").write_bytes(b"x")
    (tmp_path / "bg.png").write_bytes(b"x")
    (tmp_path / "video.mp4").write_bytes(b"x")
    path = tmp_path / "song.ssc"
    path.write_text(render(), encoding="utf-8")
    report = ssc.validate_ssc(path)
    assert report.ok, report.problems
    assert report.chart_names == ("Hard",)


def test_validate_reports_missing_assets(tmp_path: Path) -> None:
    path = tmp_path / "song.ssc"
    path.write_text(render(), encoding="utf-8")
    report = ssc.validate_ssc(path)
    assert not report.ok
    assert any("song.ogg" in p for p in report.problems)


def test_validate_rejects_garbage(tmp_path: Path) -> None:
    path = tmp_path / "song.ssc"
    path.write_text("not a simfile", encoding="utf-8")
    assert not ssc.validate_ssc(path).ok


def test_adjust_offset_shifts_the_value(tmp_path: Path) -> None:
    path = tmp_path / "song.ssc"
    path.write_text(render(), encoding="utf-8")
    new_offset = ssc.adjust_offset(path, delta_ms=-30.0)
    assert new_offset == pytest.approx(-0.264)
    assert float(simfile.open(path).offset) == pytest.approx(-0.264)


def test_adjust_offset_requires_file(tmp_path: Path) -> None:
    with pytest.raises(SimfileError):
        ssc.adjust_offset(tmp_path / "missing.ssc", 10.0)


# --- hold notes and nine-key charts ------------------------------------------

from simfile.notes import NoteType  # noqa: E402

HOLD_MEASURE = ("2000", "0100", "3000", "0010", "0001", "0000", "0000", "0000")
HOLD_CHART = Chart("Hard", 9, (HOLD_MEASURE,))
NINE_MEASURE = ("100000000", "000010000", "000000001", "000000000")
NINE_CHART = Chart("Hard", 9, (NINE_MEASURE,), steps_type="pnm-nine")


def test_hold_notes_survive_round_trip() -> None:
    text = ssc.render_ssc(META, ANALYSIS, (20.0, 12.0), (HOLD_CHART,))
    types = [n.note_type for n in NoteData(simfile.loads(text).charts[0])]
    assert NoteType.HOLD_HEAD in types and NoteType.TAIL in types


def test_nine_key_chart_declares_its_steps_type_and_width() -> None:
    text = ssc.render_ssc(META, ANALYSIS, (20.0, 12.0), (NINE_CHART,))
    chart = simfile.loads(text).charts[0]
    assert chart.stepstype == "pnm-nine"
    assert NoteData(chart).columns == 9


def test_one_file_can_hold_charts_for_several_key_modes() -> None:
    text = ssc.render_ssc(META, ANALYSIS, (20.0, 12.0), (CHART, NINE_CHART))
    assert [c.stepstype for c in simfile.loads(text).charts] == ["dance-single", "pnm-nine"]


def _write_song(tmp_path: Path, chart: Chart) -> Path:
    for name in ("song.ogg", "banner.png", "bg.png", "video.mp4"):
        (tmp_path / name).write_bytes(b"x")
    path = tmp_path / "song.ssc"
    path.write_text(ssc.render_ssc(META, ANALYSIS, (20.0, 12.0), (chart,)), encoding="utf-8")
    return path


def test_validate_accepts_holds_and_nine_key(tmp_path: Path) -> None:
    assert ssc.validate_ssc(_write_song(tmp_path, HOLD_CHART)).ok
    nine_dir = tmp_path / "nine"
    nine_dir.mkdir()
    assert ssc.validate_ssc(_write_song(nine_dir, NINE_CHART)).ok


def test_validate_rejects_wrong_column_count(tmp_path: Path) -> None:
    wrong = Chart("Hard", 9, (MEASURE,), steps_type="pnm-nine")  # 4-wide rows, 9-key type
    report = ssc.validate_ssc(_write_song(tmp_path, wrong))
    assert not report.ok
    assert any("column" in p for p in report.problems)


def test_validate_rejects_unbalanced_hold(tmp_path: Path) -> None:
    broken = Chart("Hard", 9, (("2000", "0100", "0000", "0000"),))  # head, never released
    report = ssc.validate_ssc(_write_song(tmp_path, broken))
    assert not report.ok
