import numpy as np
import pytest

from video2sm import charting
from video2sm.charting import PROFILES
from video2sm.features import SLOTS_PER_MEASURE, GridFeatures

SLOT_SECONDS = 60.0 / 140 / 4


def make_features(n_measures: int = 48, silent_measures: int = 4, seed: int = 0) -> GridFeatures:
    rng = np.random.default_rng(seed)
    n = n_measures * SLOTS_PER_MEASURE
    strengths = rng.random((n, 3)) * 0.6
    beat_slots = np.arange(0, n, 4)
    strengths[beat_slots] += 0.5  # beats are louder, like real music
    strengths[: silent_measures * SLOTS_PER_MEASURE] = 0.0
    return GridFeatures(strengths=strengths, slot_seconds=SLOT_SECONDS, first_beat_time=0.1)


@pytest.fixture(scope="module")
def charts() -> dict[str, charting.Chart]:
    features = make_features()
    return {p.name: charting.generate_chart(features, p, seed=7) for p in PROFILES}


def _rows(chart: charting.Chart) -> list[str]:
    return [row for measure in chart.measures for row in measure]


def test_rows_are_valid_four_key_strings(charts) -> None:
    for chart in charts.values():
        for measure in chart.measures:
            assert len(measure) in (4, 8, 16)
            assert all(len(r) == 4 and set(r) <= {"0", "1"} for r in measure)


def test_measure_count_matches_features(charts) -> None:
    assert all(len(c.measures) == 48 for c in charts.values())


def test_silent_intro_has_no_notes(charts) -> None:
    for chart in charts.values():
        assert not any("1" in r for m in chart.measures[:4] for r in m)


def test_density_increases_with_difficulty(charts) -> None:
    counts = [charting.count_rows(charts[p.name]) for p in PROFILES]
    assert counts == sorted(counts)
    assert counts[0] < counts[-1]


def test_easy_charts_have_no_jumps_or_triple_jacks(charts) -> None:
    easy = charts["Easy"]
    assert all(r.count("1") <= 1 for r in _rows(easy))
    columns = [r.index("1") for r in _rows(easy) if "1" in r]
    for a, b, c in zip(columns, columns[1:], columns[2:]):
        assert not (a == b == c)


def test_hard_uses_some_jumps(charts) -> None:
    assert any(r.count("1") == 2 for r in _rows(charts["Challenge"]))


def test_all_four_columns_used(charts) -> None:
    for name in ("Medium", "Hard", "Challenge"):
        used = {i for r in _rows(charts[name]) for i, ch in enumerate(r) if ch == "1"}
        assert used == {0, 1, 2, 3}


def test_same_seed_is_deterministic() -> None:
    features = make_features()
    profile = PROFILES[2]
    a = charting.generate_chart(features, profile, seed=1)
    b = charting.generate_chart(features, profile, seed=1)
    c = charting.generate_chart(features, profile, seed=2)
    assert a == b
    assert a != c


def test_meter_matches_profile(charts) -> None:
    assert [charts[p.name].meter for p in PROFILES] == [p.meter for p in PROFILES]


def test_stats_reports_peak_density(charts) -> None:
    stats = charting.chart_stats(charts["Hard"], SLOT_SECONDS)
    assert stats.rows > 0 and stats.peak_rows_per_second >= stats.average_rows_per_second


@pytest.mark.parametrize(
    "selection, expected",
    [
        (["low"], ["Easy"]),
        (["low", "medium", "high"], ["Easy", "Medium", "Hard"]),
        (["低", "中", "高"], ["Easy", "Medium", "Hard"]),
        (["HIGH", "challenge", "Beginner"], ["Hard", "Challenge", "Beginner"]),
        (["high", "hard", "high"], ["Hard"]),
        (["all"], ["Beginner", "Easy", "Medium", "Hard", "Challenge"]),
    ],
)
def test_resolve_profiles(selection, expected) -> None:
    assert [p.name for p in charting.resolve_profiles(selection)] == expected


@pytest.mark.parametrize("selection", [[], ["extreme"], [""]])
def test_resolve_profiles_rejects_unknown_or_empty(selection) -> None:
    with pytest.raises(ValueError, match="difficult"):
        charting.resolve_profiles(selection)


# --- nine-key layout -------------------------------------------------------

from dataclasses import replace  # noqa: E402

from video2sm import layouts  # noqa: E402

NINE = layouts.resolve_layout("pnm-nine")


@pytest.fixture(scope="module")
def nine_key_charts() -> dict[str, charting.Chart]:
    features = make_features()
    return {p.name: charting.generate_chart(features, p, seed=7, layout=NINE) for p in PROFILES}


def test_default_layout_is_dance_single(charts) -> None:
    assert all(c.steps_type == "dance-single" for c in charts.values())


def test_nine_key_rows_are_nine_wide(nine_key_charts) -> None:
    for chart in nine_key_charts.values():
        assert chart.steps_type == "pnm-nine"
        for measure in chart.measures:
            assert len(measure) in (4, 8, 16)
            assert all(len(r) == 9 and set(r) <= {"0", "1"} for r in measure)


def test_nine_key_uses_every_column(nine_key_charts) -> None:
    for name in ("Hard", "Challenge"):
        used = {i for r in _rows(nine_key_charts[name]) for i, ch in enumerate(r) if ch == "1"}
        assert used == set(range(9))


def test_nine_key_jumps_use_declared_pairs(nine_key_charts) -> None:
    allowed = {frozenset(p) for p in NINE.jump_pairs}
    jumps = [
        frozenset(i for i, ch in enumerate(r) if ch == "1")
        for r in _rows(nine_key_charts["Challenge"])
        if r.count("1") == 2
    ]
    assert jumps and all(j in allowed for j in jumps)


def test_nine_key_easy_has_no_jumps(nine_key_charts) -> None:
    assert all(r.count("1") <= 1 for r in _rows(nine_key_charts["Easy"]))


def test_nine_key_density_matches_four_key(charts, nine_key_charts) -> None:
    for name in ("Easy", "Hard"):
        four = charting.count_rows(charts[name])
        nine = charting.count_rows(nine_key_charts[name])
        assert abs(four - nine) <= max(8, four * 0.1)


# --- hold notes ------------------------------------------------------------


def held_features(sustain_slots: float = 8.0, **kwargs) -> GridFeatures:
    base = make_features(**kwargs)
    return replace(base, sustain=np.full(base.n_slots, sustain_slots))


def _grid(chart: charting.Chart) -> list[tuple[int, str]]:
    """(slot, row) for every non-empty row, in time order."""
    out = []
    for index, measure in enumerate(chart.measures):
        step = SLOTS_PER_MEASURE // len(measure)
        for i, row in enumerate(measure):
            if set(row) != {"0"}:
                out.append((index * SLOTS_PER_MEASURE + i * step, row))
    return out


def _hold_spans(chart: charting.Chart) -> list[tuple[int, int, int]]:
    """(column, start_slot, end_slot) for every hold; fails on unbalanced heads/tails."""
    open_heads: dict[int, int] = {}
    spans = []
    for slot, row in _grid(chart):
        for column, ch in enumerate(row):
            if ch == "2":
                assert column not in open_heads, f"hold re-opened in column {column}"
                open_heads[column] = slot
            elif ch == "3":
                assert column in open_heads, f"tail without head in column {column}"
                spans.append((column, open_heads.pop(column), slot))
            elif ch == "1":
                assert column not in open_heads, f"tap inside hold in column {column}"
    assert not open_heads, "hold never released"
    return spans


@pytest.fixture(scope="module")
def hold_charts() -> dict[str, charting.Chart]:
    features = held_features()
    return {p.name: charting.generate_chart(features, p, seed=7) for p in PROFILES}


def test_no_holds_without_sustain_data(charts) -> None:
    for chart in charts.values():
        assert not any(set(r) & {"2", "3"} for r in _rows(chart))


def test_holds_can_be_switched_off() -> None:
    chart = charting.generate_chart(held_features(), PROFILES[3], seed=7, holds=False)
    assert not any(set(r) & {"2", "3"} for r in _rows(chart))


def test_holds_are_balanced_and_never_overlapped(hold_charts) -> None:
    for chart in hold_charts.values():
        _hold_spans(chart)  # asserts head/tail pairing and no taps inside a hold


def test_beginner_and_easy_have_no_holds(hold_charts) -> None:
    for name in ("Beginner", "Easy"):
        assert not any(set(r) & {"2", "3"} for r in _rows(hold_charts[name]))


@pytest.mark.parametrize("name", ["Medium", "Hard", "Challenge"])
def test_harder_charts_have_holds(hold_charts, name) -> None:
    assert _hold_spans(hold_charts[name])


def test_hold_lengths_are_musical(hold_charts) -> None:
    for chart in hold_charts.values():
        for _, start, end in _hold_spans(chart):
            assert 4 <= end - start <= SLOTS_PER_MEASURE


def test_only_one_hold_at_a_time_and_no_jump_during_it(hold_charts) -> None:
    for chart in hold_charts.values():
        spans = _hold_spans(chart)
        for (_, s1, e1), (_, s2, e2) in zip(spans, spans[1:]):
            assert s2 > e1, "holds overlap"
        for slot, row in _grid(chart):
            inside = any(start < slot <= end for _, start, end in spans)
            if inside:
                assert row.count("1") + row.count("2") <= 1


def test_hold_ratio_is_bounded(hold_charts) -> None:
    for profile in PROFILES:
        chart = hold_charts[profile.name]
        notes = sum(1 for _, r in _grid(chart) if set(r) & {"1", "2"})
        assert len(_hold_spans(chart)) <= profile.hold_ratio * notes + 1


def test_short_sustain_makes_no_holds() -> None:
    features = held_features(sustain_slots=2.0)
    chart = charting.generate_chart(features, PROFILES[3], seed=7)
    assert not any(set(r) & {"2", "3"} for r in _rows(chart))


def test_holds_work_on_nine_keys() -> None:
    chart = charting.generate_chart(held_features(), PROFILES[4], seed=7, layout=NINE)
    assert chart.steps_type == "pnm-nine"
    assert all(len(r) == 9 for r in _rows(chart))
    assert _hold_spans(chart)


def test_hold_generation_is_deterministic() -> None:
    features = held_features()
    a = charting.generate_chart(features, PROFILES[3], seed=3)
    b = charting.generate_chart(features, PROFILES[3], seed=3)
    assert a == b


def test_stats_count_holds_and_do_not_count_tails_as_rows(hold_charts) -> None:
    chart = hold_charts["Hard"]
    stats = charting.chart_stats(chart, SLOT_SECONDS)
    heads = sum(r.count("2") for r in _rows(chart))
    tails = sum(r.count("3") for r in _rows(chart))
    assert stats.holds == heads == tails > 0
    pressed_rows = sum(1 for r in _rows(chart) if set(r) & {"1", "2"})
    assert stats.rows == pressed_rows == charting.count_rows(chart)
    assert stats.notes == sum(r.count("1") + r.count("2") for r in _rows(chart))


# --- playable difficulty ---------------------------------------------------

DENSITY_CAP = {"Beginner": 1.1, "Easy": 1.6, "Medium": 2.6, "Hard": 3.7, "Challenge": 5.0}


@pytest.mark.parametrize("layout", [layouts.DANCE_SINGLE, NINE], ids=lambda l: l.name)
def test_density_stays_in_a_playable_range(layout) -> None:
    features = make_features()
    for profile in PROFILES:
        chart = charting.generate_chart(features, profile, seed=7, layout=layout)
        stats = charting.chart_stats(chart, SLOT_SECONDS)
        # Averaged over the whole song, silent intro included, so these are generous caps.
        assert stats.average_rows_per_second <= DENSITY_CAP[profile.name], profile.name


def test_jumps_are_occasional_not_a_pattern(charts, nine_key_charts) -> None:
    for chart_set in (charts, nine_key_charts):
        for name in ("Medium", "Hard", "Challenge"):
            stats = charting.chart_stats(chart_set[name], SLOT_SECONDS)
            assert stats.jumps <= 0.12 * stats.rows, name


def _single_tap_steps(chart: charting.Chart) -> list[int]:
    """Column distance between consecutive rows that each press exactly one column."""
    rows = [r for r in _rows(chart) if set(r) != {"0"}]
    pressed = [[i for i, ch in enumerate(r) if ch in "12"] for r in rows]
    return [abs(a[0] - b[0]) for a, b in zip(pressed, pressed[1:]) if len(a) == 1 and len(b) == 1]


@pytest.mark.parametrize("name", ["Beginner", "Easy", "Medium", "Hard", "Challenge"])
def test_nine_key_notes_stay_near_the_previous_one(nine_key_charts, name) -> None:
    steps = _single_tap_steps(nine_key_charts[name])
    assert steps and max(steps) <= NINE.max_step
    assert sum(steps) / len(steps) <= 2.4  # was ~4.9: a leap across the whole keyboard


def test_four_key_flow_is_unchanged_by_the_nine_key_rules(charts) -> None:
    steps = _single_tap_steps(charts["Hard"])
    assert max(steps) <= layouts.DANCE_SINGLE.max_step


def test_nine_key_jump_pairs_are_reachable_by_one_hand_span() -> None:
    assert all(abs(a - b) <= NINE.max_step for a, b in NINE.jump_pairs)


def test_beginner_is_part_of_the_default_selection() -> None:
    names = [p.name for p in charting.resolve_profiles(charting.DEFAULT_DIFFICULTIES)]
    assert names == ["Beginner", "Easy", "Medium", "Hard"]


# --- seven-key layout (S D F space J K L) ------------------------------------

SEVEN = layouts.resolve_layout("7k")


@pytest.fixture(scope="module")
def seven_key_charts() -> dict[str, charting.Chart]:
    features = make_features()
    return {p.name: charting.generate_chart(features, p, seed=7, layout=SEVEN) for p in PROFILES}


def test_seven_key_rows_are_seven_wide(seven_key_charts) -> None:
    for chart in seven_key_charts.values():
        assert chart.steps_type == "kb7-single"
        for measure in chart.measures:
            assert all(len(r) == 7 and set(r) <= {"0", "1"} for r in measure)


def test_seven_key_uses_every_column(seven_key_charts) -> None:
    for name in ("Medium", "Hard", "Challenge"):
        used = {i for r in _rows(seven_key_charts[name]) for i, ch in enumerate(r) if ch == "1"}
        assert used == set(range(7))


@pytest.mark.parametrize("name", ["Beginner", "Easy", "Medium", "Hard", "Challenge"])
def test_seven_key_notes_stay_near_the_previous_one(seven_key_charts, name) -> None:
    steps = _single_tap_steps(seven_key_charts[name])
    assert steps and max(steps) <= SEVEN.max_step
    assert sum(steps) / len(steps) <= 2.4


def test_seven_key_jumps_use_declared_pairs(seven_key_charts) -> None:
    allowed = {frozenset(p) for p in SEVEN.jump_pairs}
    jumps = [
        frozenset(i for i, ch in enumerate(r) if ch == "1")
        for r in _rows(seven_key_charts["Challenge"])
        if r.count("1") == 2
    ]
    assert jumps and all(j in allowed for j in jumps)


def test_seven_key_density_is_playable() -> None:
    features = make_features()
    for profile in PROFILES:
        chart = charting.generate_chart(features, profile, seed=7, layout=SEVEN)
        stats = charting.chart_stats(chart, SLOT_SECONDS)
        assert stats.average_rows_per_second <= DENSITY_CAP[profile.name], profile.name


def test_holds_work_on_seven_keys() -> None:
    chart = charting.generate_chart(held_features(), PROFILES[4], seed=7, layout=SEVEN)
    assert chart.steps_type == "kb7-single"
    assert all(len(r) == 7 for r in _rows(chart))
    assert _hold_spans(chart)
