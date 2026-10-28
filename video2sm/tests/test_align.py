"""Moving chart notes onto the exact moment their sound is heard."""

import json
from pathlib import Path

import pytest
import simfile
from simfile.notes import NoteData, NoteType
from simfile.timing import TimingData
from simfile.timing.engine import TimingEngine

from tests.test_review import EMPTY, SLOT_SECONDS, build_song, measure_from, row
from video2sm import align, chartfile, review, ssc
from video2sm.errors import SimfileError


def note_times(path: Path, difficulty: str = "Easy") -> list[tuple[float, int, str]]:
    sim = simfile.open(str(path))
    engine = TimingEngine(TimingData(sim))
    chart = next(c for c in sim.charts if c.difficulty == difficulty)
    kinds = {NoteType.TAP: "tap", NoteType.HOLD_HEAD: "head", NoteType.TAIL: "tail"}
    return [(float(engine.time_at(n.beat)), n.column, kinds[n.note_type]) for n in NoteData(chart)]


def set_facts(path: Path, melody=(), drum_times=None) -> None:
    facts_path = path.parent / "music.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    facts["melody"] = [
        {"slot": round(start / SLOT_SECONDS), "length_slots": 2, "midi": 62, "name": "D4", "strength": 1.0,
         "start_time": start, "end_time": end}
        for start, end in melody
    ]
    facts["drums"] = {"kick": [], "snare": [], "hat": []}
    facts["drum_times"] = drum_times or {"kick": [], "snare": [], "hat": []}
    facts_path.write_text(json.dumps(facts), encoding="utf-8")


def two_measure_song(tmp_path: Path, first: dict, second: dict | None = None) -> Path:
    return build_song(tmp_path, measures=[measure_from(first), measure_from(second or {})])


def test_notes_move_onto_the_attacks_they_answer(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4), 4: row(3), 8: row(5)})  # 0.0 s, 0.5 s, 1.0 s
    set_facts(path, melody=[(0.03, 0.4), (0.46, 0.9)], drum_times={"kick": [1.02], "snare": [], "hat": []})
    report = align.align_chart(path, "Easy")
    times = sorted(t for t, _, _ in note_times(path))
    assert times == pytest.approx([0.03, 0.46, 1.02], abs=0.006)
    (chart,) = report["charts"]
    assert chart["moved"] == 3 and chart["unmatched"] == 0
    assert chart["max_shift_ms"] == pytest.approx(40, abs=6)


def test_notes_with_nothing_close_stay_on_the_grid(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4), 8: row(5)})
    set_facts(path, melody=[(0.30, 0.5)])  # 300 ms from the first note: too far to be its attack
    report = align.align_chart(path, "Easy")
    assert sorted(t for t, _, _ in note_times(path)) == pytest.approx([0.0, 1.0], abs=0.001)
    assert report["charts"][0]["unmatched"] == 2


def test_hold_tails_move_to_the_end_of_the_sung_note(tmp_path: Path) -> None:
    hold = {0: row(chars={3: "2"}), 8: row(chars={3: "3"})}  # head 0.0 s, tail 1.0 s
    path = two_measure_song(tmp_path, hold)
    set_facts(path, melody=[(0.02, 1.37)])
    align.align_chart(path, "Easy")
    found = {kind: t for t, _, kind in note_times(path)}
    assert found["head"] == pytest.approx(0.02, abs=0.006)
    assert found["tail"] == pytest.approx(1.37, abs=0.006)


def test_a_tail_never_runs_into_the_next_note_in_its_lane(tmp_path: Path) -> None:
    hold = {0: row(chars={3: "2"}), 4: row(chars={3: "3"}), 12: row(3)}  # next tap on lane 3 at 1.5 s
    path = two_measure_song(tmp_path, hold)
    set_facts(path, melody=[(0.0, 1.9)])  # the vowel goes on past the next note
    align.align_chart(path, "Easy")
    lane3 = sorted((t, kind) for t, col, kind in note_times(path) if col == 2)
    tail = next(t for t, kind in lane3 if kind == "tail")
    tap = next(t for t, kind in lane3 if kind == "tap")
    assert tail < tap - 0.02
    assert ssc.validate_ssc(path).ok


def test_rows_keep_their_order_and_jumps_move_together(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(2, 6), 1: row(4)})  # jump at 0.0 s, tap at 0.125 s
    # both rows are within reach of the same attack; the second must not cross the first
    set_facts(path, melody=[(0.06, 0.1)])
    align.align_chart(path, "Easy")
    found = sorted(note_times(path))
    jump = [t for t, col, _ in found if col in (1, 5)]
    tap = [t for t, col, _ in found if col == 3]
    assert jump[0] == pytest.approx(jump[1])
    assert tap[0] > jump[0]


def test_alignment_is_idempotent(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4), 4: row(3)})
    set_facts(path, melody=[(0.03, 0.4), (0.47, 0.9)])
    align.align_chart(path, "Easy")
    once = path.read_text(encoding="utf-8")
    again = align.align_chart(path, "Easy")
    assert path.read_text(encoding="utf-8") == once
    assert again["charts"][0]["max_shift_ms"] < 6


def test_aligned_charts_still_validate_and_can_be_reviewed(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4), 4: row(3)}, {0: row(5)})
    set_facts(path, melody=[(0.03, 0.4), (0.47, 0.9)])
    align.align_chart(path, "Easy")
    assert ssc.validate_ssc(path).ok
    shown = review.inspect_chart(path, "Easy", 0, 2)["text"]
    assert "s0:4" in shown and "s4:3" in shown  # still readable on the 16th grid


def test_editing_one_measure_keeps_the_alignment_of_the_others(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4), 4: row(3)}, {0: row(5)})
    set_facts(path, melody=[(0.03, 0.4), (0.47, 0.9)])
    align.align_chart(path, "Easy")
    aligned_first = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures[0]
    assert review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1"}])["ok"]
    after = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures
    assert after[0] == aligned_first and after[1][0] == row(1)


def test_every_chart_is_aligned_when_no_difficulty_is_named(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4)})
    set_facts(path, melody=[(0.03, 0.4)])
    report = align.align_chart(path)
    assert [c["difficulty"] for c in report["charts"]] == ["Easy"]


def test_changing_tempo_is_refused(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4)})
    text = path.read_text(encoding="utf-8").replace("#BPMS:0.000=120.000;", "#BPMS:0.000=120.000,4.000=140.000;")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SimfileError, match="tempo"):
        align.align_chart(path, "Easy")


def test_without_music_facts_nothing_happens(tmp_path: Path) -> None:
    path = two_measure_song(tmp_path, {0: row(4)})
    (path.parent / "music.json").unlink()
    with pytest.raises(SimfileError, match="music.json"):
        align.align_chart(path, "Easy")
