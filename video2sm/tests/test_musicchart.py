"""Charts built from melody and drum events (the stem-based path)."""

import numpy as np
import pytest

from video2sm import charting, events, layouts
from video2sm.features import SLOTS_PER_MEASURE, GridFeatures
from video2sm.melody import Note

SLOT_SECONDS = 0.1
N_MEASURES = 24
N_SLOTS = N_MEASURES * SLOTS_PER_MEASURE
PROFILES = {p.name: p for p in charting.PROFILES}
SEVEN = layouts.KB7_SINGLE
NINE = layouts.POPN_NINE


def grid() -> GridFeatures:
    return GridFeatures(
        strengths=np.zeros((N_SLOTS, 3)), slot_seconds=SLOT_SECONDS, first_beat_time=0.0
    )


def note(slot: int, slots: int, pitch: float, strength: float = 1.0) -> Note:
    return Note(slot * SLOT_SECONDS, (slot + slots) * SLOT_SECONDS, pitch, strength)


def music(notes=(), kicks=(), snares=(), hats=()) -> events.MusicFeatures:
    drums = np.zeros((N_SLOTS, 3))
    for column, slots in enumerate((kicks, snares, hats)):
        for slot in slots:
            drums[slot, column] = 1.0
    return events.MusicFeatures(
        n_slots=N_SLOTS, slot_seconds=SLOT_SECONDS, first_beat_time=0.0,
        drum_strengths=drums, vocal_strengths=np.zeros(N_SLOTS), melody=tuple(notes),
    )


def build(profile_name, m, layout=SEVEN, seed=3, holds=True) -> charting.Chart:
    return charting.generate_chart(grid(), PROFILES[profile_name], seed, layout, holds, music=m)


def timed_rows(chart: charting.Chart) -> list[tuple[int, str]]:
    out = []
    for index, measure in enumerate(chart.measures):
        step = SLOTS_PER_MEASURE // len(measure)
        for i, row in enumerate(measure):
            if set(row) != {"0"}:
                out.append((index * SLOTS_PER_MEASURE + i * step, row))
    return out


def pressed_columns(row: str) -> list[int]:
    return [i for i, ch in enumerate(row) if ch in "12"]


def spearman(a, b) -> float:
    ra, rb = np.argsort(np.argsort(a)), np.argsort(np.argsort(b))
    return float(np.corrcoef(ra, rb)[0, 1])


def scale_melody(count=24, spacing=4, length=2):
    """Up two octaves and back down: a melody whose shape is easy to check."""
    pitches = list(np.linspace(55, 79, count // 2)) + list(np.linspace(79, 55, count // 2))
    return [note(2 * spacing + i * spacing, length, p) for i, p in enumerate(pitches)]


def test_notes_follow_the_pitch_of_the_melody() -> None:
    notes = scale_melody()
    chart = build("Medium", music(notes))
    rows = timed_rows(chart)
    columns = [pressed_columns(r)[0] for _, r in rows]
    pitches = [n.pitch for n in notes]
    assert len(columns) >= 16
    # the chart can skip a note, so line up by time rather than by index
    by_slot = {slot: pressed_columns(row)[0] for slot, row in rows}
    pairs = [(n.pitch, by_slot[round(n.start / SLOT_SECONDS)]) for n in notes
             if round(n.start / SLOT_SECONDS) in by_slot]
    assert len(pairs) >= 16
    assert spearman([p for p, _ in pairs], [c for _, c in pairs]) > 0.75


def test_rising_melody_moves_right_and_falling_melody_moves_left() -> None:
    notes = scale_melody()
    chart = build("Hard", music(notes))
    rows = timed_rows(chart)
    first_half = [pressed_columns(r)[0] for s, r in rows if s < N_SLOTS // 4 + 8]
    assert first_half[-1] > first_half[0]
    peak = max(range(len(rows)), key=lambda i: pressed_columns(rows[i][1])[0])
    assert pressed_columns(rows[-1][1])[0] < pressed_columns(rows[peak][1])[0]


def test_note_starts_land_on_the_melody_slots() -> None:
    notes = scale_melody(count=16, spacing=8)
    chart = build("Easy", music(notes))
    slots = {slot for slot, _ in timed_rows(chart)}
    starts = {round(n.start / SLOT_SECONDS) for n in notes}
    assert slots and slots <= starts | {s + 1 for s in starts} | {s - 1 for s in starts}


def test_sustained_notes_become_holds_that_end_with_the_note() -> None:
    notes = [note(8 + i * 12, 8, 55 + (i * 3) % 20) for i in range(24)]
    chart = build("Hard", music(notes))
    heads, spans = {}, []
    for slot, row in timed_rows(chart):
        for column, ch in enumerate(row):
            if ch == "2":
                heads[column] = slot
            elif ch == "3":
                spans.append((heads.pop(column), slot))
    assert len(spans) >= 3
    ends = {round(n.start / SLOT_SECONDS): round(n.end / SLOT_SECONDS) for n in notes}
    for start, end in spans:
        assert abs(end - ends[start]) <= 2


def test_holds_never_overlap_and_nothing_else_is_pressed_in_their_column() -> None:
    notes = [note(8 + i * 8, 6, 55 + (i * 5) % 22) for i in range(30)]
    m = music(notes, kicks=range(0, N_SLOTS, 8), snares=range(4, N_SLOTS, 16))
    chart = build("Challenge", m)
    held: dict[int, int] = {}
    for slot, row in timed_rows(chart):
        for column, ch in enumerate(row):
            if ch == "3":
                held.pop(column)
            elif ch == "2":
                assert not held, "second hold started while one was held"
                held[column] = slot
            elif ch == "1":
                assert column not in held
        if any(slot > start for start in held.values()):
            assert len(pressed_columns(row)) <= 1


def hold_heads(chart: charting.Chart) -> list[int]:
    return [slot for slot, row in timed_rows(chart) if "2" in row]


def short_notes_with_two_long_ones() -> list[Note]:
    """Twenty notes a beat apart, short but for two held for a whole measure."""
    long_at = {3, 12}
    return [note(8 + i * 8, 16 if i in long_at else 4, 55 + (i * 3) % 12) for i in range(20)]


def test_the_longest_sung_notes_get_the_holds_not_the_first_ones() -> None:
    chart = build("Medium", music(short_notes_with_two_long_ones()))
    # a hold is the way to play a sustained note: the two held vowels come first, and only
    # what is left of the share goes to a short note (the old rule gave it all to early blips)
    heads = hold_heads(chart)
    assert {8 + 3 * 8, 8 + 12 * 8} <= set(heads)
    assert len(heads) <= 3


def test_holds_still_stay_within_the_difficulty_share() -> None:
    notes = short_notes_with_two_long_ones()
    chart = build("Medium", music(notes))
    share = PROFILES["Medium"].melody_hold_ratio
    assert len(hold_heads(chart)) <= np.ceil(share * len(notes))


def test_a_long_note_that_also_has_a_drum_hit_is_still_held() -> None:
    notes = short_notes_with_two_long_ones()
    chart = build("Hard", music(notes, kicks=[8 + 3 * 8, 8 + 12 * 8]))
    assert {8 + 3 * 8, 8 + 12 * 8} <= set(hold_heads(chart))  # not turned into a two-key tap


def test_holds_can_be_switched_off() -> None:
    notes = [note(8 + i * 12, 8, 55 + (i * 3) % 20) for i in range(24)]
    chart = build("Hard", music(notes), holds=False)
    assert not any(set(r) & {"2", "3"} for _, r in timed_rows(chart))


def test_beginner_charts_have_no_holds() -> None:
    notes = [note(8 + i * 12, 8, 55 + (i * 3) % 20) for i in range(24)]
    chart = build("Beginner", music(notes))
    assert not any(set(r) & {"2", "3"} for _, r in timed_rows(chart))


def test_kicks_sit_near_the_middle_lane() -> None:
    chart = build("Beginner", music(kicks=range(0, N_SLOTS, 4)))
    columns = [pressed_columns(r)[0] for _, r in timed_rows(chart)]
    assert len(columns) > 20
    assert 1.5 <= float(np.mean(columns)) <= 4.5
    assert 3 in columns


def test_hats_are_pushed_to_the_outer_lanes() -> None:
    chart = build("Challenge", music(hats=range(0, N_SLOTS, 2)))
    columns = [pressed_columns(r)[0] for _, r in timed_rows(chart)]
    outer = sum(1 for c in columns if c in (0, 1, 5, 6))
    assert outer / len(columns) > 0.6


def test_drums_fill_in_where_there_is_no_melody() -> None:
    notes = [note(i * 4, 2, 60 + i % 5) for i in range(0, 40)]  # vocal for the first 160 slots only
    m = music(notes, kicks=range(0, N_SLOTS, 8))
    slots = [slot for slot, _ in timed_rows(build("Medium", m))]
    assert any(s > 200 for s in slots)  # kicks carry the instrumental part


@pytest.mark.parametrize("name,cap", [("Beginner", 1.1), ("Easy", 1.6), ("Medium", 2.6),
                                       ("Hard", 3.7), ("Challenge", 5.0)])
def test_density_stays_in_the_playable_range(name, cap) -> None:
    notes = [note(i * 2, 1, 55 + (i * 7) % 24) for i in range(N_SLOTS // 2)]
    m = music(notes, kicks=range(0, N_SLOTS, 4), snares=range(8, N_SLOTS, 8), hats=range(0, N_SLOTS, 2))
    chart = build(name, m)
    stats = charting.chart_stats(chart, SLOT_SECONDS)
    assert stats.average_rows_per_second <= cap


def test_same_seed_gives_the_same_chart() -> None:
    m = music(scale_melody(), kicks=range(0, N_SLOTS, 8))
    assert build("Hard", m, seed=5) == build("Hard", m, seed=5)
    assert build("Hard", m, seed=5) != build("Hard", m, seed=6)


@pytest.mark.parametrize("layout", [layouts.DANCE_SINGLE, SEVEN, NINE], ids=lambda l: l.name)
def test_every_layout_gets_rows_of_the_right_width(layout) -> None:
    m = music(scale_melody(), kicks=range(0, N_SLOTS, 8), snares=range(4, N_SLOTS, 16))
    chart = build("Hard", m, layout=layout)
    assert chart.steps_type == layout.name
    assert all(len(row) == layout.columns for _, row in timed_rows(chart))


def test_jumps_come_from_coinciding_melody_and_drum_hits() -> None:
    notes = [note(i * 8, 2, 55 + (i * 5) % 22) for i in range(40)]
    m = music(notes, kicks=range(0, N_SLOTS, 8))
    chart = build("Challenge", m)
    jumps = [r for _, r in timed_rows(chart) if len(pressed_columns(r)) == 2]
    assert jumps
    allowed = {frozenset(p) for p in SEVEN.jump_pairs}
    assert all(frozenset(pressed_columns(r)) in allowed for r in jumps)


def test_easy_charts_never_have_jumps() -> None:
    notes = [note(i * 8, 2, 55 + (i * 5) % 22) for i in range(40)]
    chart = build("Easy", music(notes, kicks=range(0, N_SLOTS, 8)))
    assert all(len(pressed_columns(r)) <= 1 for _, r in timed_rows(chart))


def test_notes_stay_within_reach_of_the_previous_note() -> None:
    notes = [note(i * 4, 2, 55 + (i * 11) % 24) for i in range(60)]
    chart = build("Hard", music(notes))
    rows = [pressed_columns(r) for _, r in timed_rows(chart)]
    steps = [abs(a[0] - b[0]) for a, b in zip(rows, rows[1:]) if len(a) == 1 and len(b) == 1]
    assert max(steps) <= SEVEN.max_step


def test_silence_gives_an_empty_chart() -> None:
    chart = build("Hard", music())
    assert timed_rows(chart) == []
