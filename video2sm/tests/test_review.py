"""Reviewing and editing charts: the part where a language model proposes and code verifies."""

import json
from pathlib import Path

import pytest

from video2sm import chartfile, layouts, review, ssc
from video2sm.beats import BeatAnalysis
from video2sm.charting import Chart
from video2sm.errors import SimfileError

BPM = 120.0
SLOT_SECONDS = 60.0 / BPM / 4
ANALYSIS = BeatAnalysis(bpm=BPM, first_beat_time=0.0, confidence=1.0, stability_ms=1.0, duration=60.0)
META = ssc.SongMeta(title="Review Song", artist="Tester", music="song.ogg")
COLUMNS = 7
EMPTY = "0" * COLUMNS


def row(*lanes: int, chars: dict[int, str] | None = None) -> str:
    cells = ["0"] * COLUMNS
    for lane in lanes:
        cells[lane - 1] = "1"
    for lane, ch in (chars or {}).items():
        cells[lane - 1] = ch
    return "".join(cells)


def measure_from(slots: dict[int, str]) -> tuple[str, ...]:
    return tuple(slots.get(i, EMPTY) for i in range(16))


# 8 measures: a steady quarter-note pulse on measures 0-3, then a different rhythm
QUARTERS = {0: row(4), 4: row(3), 8: row(4), 12: row(5)}
OFFBEAT = {2: row(2), 6: row(6), 10: row(2), 14: row(6)}


def build_song(tmp_path: Path, measures=None, difficulty="Easy") -> Path:
    measures = measures or ([measure_from(QUARTERS)] * 4 + [measure_from(OFFBEAT)] * 4)
    chart = Chart(difficulty, 2, tuple(measures), steps_type="kb7-single")
    (tmp_path / "song.ogg").write_bytes(b"x")
    path = tmp_path / "song.ssc"
    path.write_text(ssc.render_ssc(META, ANALYSIS, (0.0, 10.0), (chart,)), encoding="utf-8")
    facts = {
        "version": 1, "chart_source": "stems", "bpm": BPM, "first_beat_time": 0.0,
        "slot_seconds": SLOT_SECONDS, "n_slots": 16 * len(measures),
        "melody": [
            {"slot": 0, "length_slots": 6, "midi": 62, "name": "D4", "strength": 1.0},
            {"slot": 8, "length_slots": 1, "midi": 64, "name": "E4", "strength": 0.9},
            {"slot": 16 * 4 + 2, "length_slots": 2, "midi": 67, "name": "G4", "strength": 0.8},
        ],
        "drums": {"kick": [0, 4, 8, 12, 16, 20, 24, 28], "snare": [4, 12], "hat": [16 * 4 + 6]},
        "energy": [0.2, 0.3, 0.4, 0.5, 0.9, 1.0, 0.6, 0.1],
        "sections": [
            {"start": 0, "end": 3, "label": "A"}, {"start": 4, "end": 5, "label": "B"},
            {"start": 6, "end": 7, "label": "A"},
        ],
        "repeats": [{"source": [0, 1], "target": [6, 7], "match": 0.9}],
    }
    (tmp_path / "music.json").write_text(json.dumps(facts), encoding="utf-8")
    return path


# --- note notation -----------------------------------------------------------------------------


def test_parse_taps_jumps_and_holds() -> None:
    parsed = review.parse_notes("s0:4 s4:2+6 s8:H3 s12:|3", COLUMNS)
    assert parsed == {0: {3: "1"}, 4: {1: "1", 5: "1"}, 8: {2: "2"}, 12: {2: "3"}}


def test_notation_round_trips() -> None:
    text = "s0:4 s4:2+6 s8:H3 s12:|3+5"
    assert review.format_notes(review.parse_notes(text, COLUMNS)) == text


def test_commas_and_case_are_tolerated() -> None:
    assert review.parse_notes("S0:4, s4:h3", COLUMNS) == {0: {3: "1"}, 4: {2: "2"}}


@pytest.mark.parametrize(
    "text, message",
    [
        ("s16:4", "slot"),
        ("s0:8", "lane"),
        ("s0:0", "lane"),
        ("s0:4+4", "twice"),
        ("s0:4 s0:5", "twice"),
        ("s0:4+5+6", "at most two"),
        ("s0", "token"),
        ("hello", "token"),
    ],
)
def test_bad_notation_is_explained(text: str, message: str) -> None:
    with pytest.raises(SimfileError, match=message):
        review.parse_notes(text, COLUMNS)


def test_empty_notation_is_an_empty_measure() -> None:
    assert review.parse_notes("", COLUMNS) == {}


# --- reading and writing the chart's measures -----------------------------------------------


def test_chartfile_round_trips_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    text = path.read_text(encoding="utf-8")
    block = chartfile.find_chart(text, "kb7-single", "Easy")
    assert len(block.measures) == 8
    assert chartfile.replace_measures(text, block, block.measures) == text


def test_chartfile_replaces_only_the_named_chart(tmp_path: Path) -> None:
    easy = Chart("Easy", 2, (measure_from(QUARTERS),) * 2, steps_type="kb7-single")
    hard = Chart("Hard", 6, (measure_from(OFFBEAT),) * 2, steps_type="kb7-single")
    text = ssc.render_ssc(META, ANALYSIS, (0.0, 10.0), (easy, hard))
    block = chartfile.find_chart(text, "kb7-single", "Hard")
    new = chartfile.replace_measures(text, block, (measure_from({0: row(1)}),) * 2)
    assert chartfile.find_chart(new, "kb7-single", "Easy").measures == chartfile.find_chart(text, "kb7-single", "Easy").measures
    assert chartfile.find_chart(new, "kb7-single", "Hard").measures[0][0] == row(1)


def test_missing_chart_is_explained(tmp_path: Path) -> None:
    text = build_song(tmp_path).read_text(encoding="utf-8")
    with pytest.raises(SimfileError, match="Hard"):
        chartfile.find_chart(text, "kb7-single", "Hard")


# --- inspecting -------------------------------------------------------------------------------


def test_inspect_shows_chart_and_music_side_by_side(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    report = review.inspect_chart(path, "Easy", start=0, count=2)
    assert (report["steps_type"], report["difficulty"], report["total_measures"]) == ("kb7-single", "Easy", 8)
    text = report["text"]
    assert "m0" in text and "m1" in text and "m2" not in text
    assert "s0:4 s4:3 s8:4 s12:5" in text  # the chart, 1-based lanes
    assert "D4@0/6" in text and "E4@8" in text  # melody: name@slot[/length]
    assert "K0,4,8,12" in text and "S4,12" in text  # drums


def test_inspect_points_out_measures_that_repeat_the_music(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    text = review.inspect_chart(path, "Easy", start=0, count=8)["text"]
    line = next(l for l in text.splitlines() if l.startswith("m1 "))
    assert "like m0" in line  # same drums (and quiet melody) as the first measure


def test_inspect_clamps_the_range(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    report = review.inspect_chart(path, "Easy", start=6, count=50)
    assert report["start"] == 6 and report["count"] == 2


def test_inspect_reports_overall_stats(tmp_path: Path) -> None:
    stats = review.inspect_chart(build_song(tmp_path), "Easy", 0, 1)["stats"]
    assert stats["rows"] == 32 and stats["holds"] == 0 and stats["jumps"] == 0
    assert stats["measures"] == 8
    assert stats["rows_per_second"] == pytest.approx(32 / (8 * 16 * SLOT_SECONDS), abs=0.01)
    assert 0.0 <= stats["supported_share"] <= 1.0
    assert 0.0 < stats["rhythm_vocabulary"] <= 1.0


def test_stats_flag_notes_with_nothing_to_hear(tmp_path: Path) -> None:
    unsupported = {2: row(1), 6: row(2), 10: row(3), 14: row(4)}  # two slots from every kick and note
    path = build_song(tmp_path, measures=[measure_from(unsupported)] * 2)
    stats = review.inspect_chart(path, "Easy", 0, 1)["stats"]
    assert stats["unsupported_notes"] == 8 and stats["supported_share"] == 0.0


def test_a_note_on_the_second_part_has_something_to_hear(tmp_path: Path) -> None:
    path = build_song(tmp_path, measures=[measure_from({2: row(1)}), measure_from({})])
    assert review.inspect_chart(path, "Easy", 0, 1)["stats"]["unsupported_notes"] == 1  # nothing near slot 2
    facts_path = tmp_path / "music.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    facts["second_melody"] = [{"slot": 2, "length_slots": 2, "midi": 50, "name": "D3", "strength": 1.0}]
    facts_path.write_text(json.dumps(facts), encoding="utf-8")
    assert review.inspect_chart(path, "Easy", 0, 1)["stats"]["unsupported_notes"] == 0


# --- editing ----------------------------------------------------------------------------------


def test_edit_replaces_a_measure(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1 s8:7"}])
    assert result["ok"] and result["errors"] == []
    block = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy")
    assert block.measures[1] == (row(1), EMPTY, row(7), EMPTY)


def test_edit_copies_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"copy": {"from": 0, "to": [5, 6]}}])
    assert result["ok"]
    measures = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures
    assert measures[5] == measures[0] == measures[6]


def test_edit_clears_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    assert review.edit_chart(path, "Easy", [{"clear": [0, 1]}])["ok"]
    measures = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures
    assert all(set(r) == {"0"} for m in measures[:2] for r in m)


def test_edits_apply_in_order(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    edits = [{"measure": 0, "notes": "s0:1"}, {"copy": {"from": 0, "to": [7]}}]
    assert review.edit_chart(path, "Easy", edits)["ok"]
    measures = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures
    assert measures[7][0] == row(1)


def test_a_bad_edit_changes_nothing(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    before = path.read_text(encoding="utf-8")
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1"}, {"measure": 2, "notes": "s0:9"}])
    assert not result["ok"] and any("lane" in e for e in result["errors"])
    assert path.read_text(encoding="utf-8") == before


def test_unknown_measure_is_rejected(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"measure": 40, "notes": "s0:1"}])
    assert not result["ok"] and any("measure 40" in e for e in result["errors"])


def test_unknown_edit_shape_is_rejected(tmp_path: Path) -> None:
    result = review.edit_chart(build_song(tmp_path), "Easy", [{"explode": 1}])
    assert not result["ok"] and result["errors"]


def test_dry_run_checks_without_writing(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    before = path.read_text(encoding="utf-8")
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1"}], dry_run=True)
    assert result["ok"] and path.read_text(encoding="utf-8") == before


# --- what the code refuses ----------------------------------------------------------------------


def test_unreleased_hold_is_an_error(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:H3"}])
    assert not result["ok"] and any("never released" in e for e in result["errors"])


def test_hold_may_span_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    edits = [{"measure": 1, "notes": "s8:H3"}, {"measure": 2, "notes": "s4:|3"}]
    assert review.edit_chart(path, "Easy", edits)["ok"]


def test_tap_inside_a_hold_is_an_error(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:H3 s4:3 s8:|3"}])
    assert not result["ok"] and any("lane 3" in e for e in result["errors"])


def test_more_than_two_presses_at_once_is_an_error(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    assert review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1+2"}])["ok"]  # a jump is fine
    result = review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:1+2+3"}])
    assert not result["ok"] and any("at most two" in e for e in result["errors"])


def test_density_far_above_the_difficulty_is_only_a_warning(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    busy = " ".join(f"s{i}:{(i % 7) + 1}" for i in range(0, 16))
    result = review.edit_chart(path, "Easy", [{"measure": m, "notes": busy} for m in range(8)])
    assert result["ok"] and any("density" in w for w in result["warnings"])


def test_leaps_beyond_reach_are_warned(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    result = review.edit_chart(path, "Easy", [{"measure": 0, "notes": "s0:1 s4:7 s8:1 s12:7"}])
    assert result["ok"] and any("reach" in w for w in result["warnings"])
    assert result["stats"]["reach_violations"] >= 3


def test_unsupported_notes_are_warned(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    edits = [{"measure": m, "notes": "s2:2 s6:3 s10:4 s14:5"} for m in range(8)]
    result = review.edit_chart(path, "Easy", edits)
    assert result["ok"] and any("nothing to hear" in w for w in result["warnings"])


# --- handing a reviewed chart back -----------------------------------------------------------


def test_merge_copies_one_chart_into_another_file(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    source = build_song(tmp_path / "a")
    target = build_song(tmp_path / "b")
    assert review.edit_chart(source, "Easy", [{"measure": 0, "notes": "s0:1"}])["ok"]
    review.merge_chart(source, target, "Easy")
    merged = chartfile.find_chart(target.read_text(encoding="utf-8"), "kb7-single", "Easy")
    assert merged.measures[0][0] == row(1)


def test_edited_files_still_validate(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    assert review.edit_chart(path, "Easy", [{"measure": 0, "notes": "s0:1 s4:H3 s8:|3 s12:5"}])["ok"]
    assert ssc.validate_ssc(path).ok


def test_the_layout_governs_the_lane_count(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    layout = layouts.layout_for_steps_type("kb7-single")
    assert layout is not None and layout.columns == COLUMNS
    result = review.edit_chart(path, "Easy", [{"measure": 0, "notes": "s0:8"}])
    assert not result["ok"] and any("1-7" in e for e in result["errors"])


def test_inspect_shows_sections_and_energy(tmp_path: Path) -> None:
    text = review.inspect_chart(build_song(tmp_path), "Easy", 0, 8)["text"]
    assert "sections: A m0-3, B m4-5, A m6-7" in text
    line = next(l for l in text.splitlines() if l.startswith("m5 "))
    assert "e9" in line  # energy 1.0 on a 0-9 scale
    assert "e2" in next(l for l in text.splitlines() if l.startswith("m0 "))  # 0.2 -> 2


# --- repeated music ------------------------------------------------------------------------------


def test_inspect_lists_the_repeats_and_marks_the_reprised_measures(tmp_path: Path) -> None:
    text = review.inspect_chart(build_song(tmp_path), "Easy", 0, 8)["text"]
    assert "repeats: m0-1 again at m6-7 (match 0.9)" in text
    assert "reprise of m0" in next(l for l in text.splitlines() if l.startswith("m6 "))
    assert "reprise of m1" in next(l for l in text.splitlines() if l.startswith("m7 "))


def test_repeat_edit_copies_a_block_of_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    edits = [{"measure": 0, "notes": "s0:1 s8:H2"}, {"measure": 1, "notes": "s0:|2 s8:3"},
             {"repeat": {"from": [0, 1], "to": 6}}]
    assert review.edit_chart(path, "Easy", edits)["ok"]
    measures = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy").measures
    assert measures[6] == measures[0] and measures[7] == measures[1]


def test_repeat_edit_must_fit_in_the_song(tmp_path: Path) -> None:
    result = review.edit_chart(build_song(tmp_path), "Easy", [{"repeat": {"from": [0, 3], "to": 6}}])
    assert not result["ok"] and any("measure 8" in e for e in result["errors"])


def test_inspect_reports_how_much_of_the_singing_each_section_answers(tmp_path: Path) -> None:
    path = build_song(tmp_path)  # melody notes at m0 s0, m0 s8, m4 s2; the chart plays m0 s0 and s8
    text = review.inspect_chart(path, "Easy", 0, 1)["text"]
    line = next(l for l in text.splitlines() if l.startswith("section A m0-3"))
    assert "answers 100% of 2 sung notes" in line
    line = next(l for l in text.splitlines() if l.startswith("section B m4-5"))
    assert "answers 100% of 1 sung notes" in line  # the off-beat note at m4 s2 is on it
    assert review.edit_chart(path, "Easy", [{"clear": [4]}])["ok"]
    text = review.inspect_chart(path, "Easy", 0, 1)["text"]
    line = next(l for l in text.splitlines() if l.startswith("section B m4-5"))
    assert "answers 0% of 1 sung notes" in line
