"""Turn grid onset features into note patterns for a key layout (4-key or 9-key).

Two steps: choose *which* grid slots get a note (loudness + rhythmic position,
tuned to a target density per difficulty), then choose *which columns* (hand
alternation, jack limits, bass-inner / treble-outer flavour). Notes whose sound
keeps going become holds. Both steps are deterministic for a given seed.

Rows are strings with one character per column: 0 empty, 1 tap, 2 hold head,
3 hold tail.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter1d

from . import events
from .features import SLOTS_PER_BEAT, SLOTS_PER_MEASURE, GridFeatures
from .layouts import DANCE_SINGLE, NEUTRAL, KeyLayout

_MIN_ABSOLUTE_STRENGTH = 0.15
_BAND_WEIGHTS = (1.0, 0.9, 0.75)  # low, mid, high
_LOCAL_WINDOW_SLOTS = 2 * SLOTS_PER_MEASURE
_MIN_HOLD_SLOTS = SLOTS_PER_BEAT
_MAX_HOLD_SLOTS = SLOTS_PER_MEASURE
_HOLD_STEP_SLOTS = 2  # hold starts and lengths snap to eighth notes


@dataclass(frozen=True)
class Profile:
    name: str
    meter: int
    target_rows_per_second: float
    # Weight of a slot by position inside the beat: on-beat, 16th, 8th, 16th.
    slot_weights: tuple[float, float, float, float]
    min_gap_slots: int
    max_same_column_run: int
    allow_jumps: bool = False
    jump_strength: float = 1.0
    max_jump_ratio: float = 0.0
    hold_ratio: float = 0.0  # at most this share of notes may become holds
    # Stem-based charts: how much each musical part contributes, and how many of the
    # (typically long) melody notes become holds.
    melody_weight: float = 1.0
    # how many melodic parts (the loudest, then the next) the chart follows
    melodic_parts: int = 1
    kick_weight: float = 0.0
    snare_weight: float = 0.0
    hat_weight: float = 0.0
    melody_hold_ratio: float = 0.0


PROFILES: tuple[Profile, ...] = (
    Profile("Beginner", 1, 0.9, (1.0, 0.0, 0.0, 0.0), 4, 2, kick_weight=0.5),
    Profile("Easy", 2, 1.4, (1.0, 0.0, 0.6, 0.0), 2, 2,
            kick_weight=0.6, snare_weight=0.3, melody_hold_ratio=0.10),
    Profile("Medium", 4, 2.3, (1.0, 0.0, 0.85, 0.0), 2, 2, True, 1.1, 0.02, 0.04,
            kick_weight=0.8, snare_weight=0.7, hat_weight=0.1, melody_hold_ratio=0.14),
    Profile("Hard", 6, 3.3, (1.0, 0.35, 0.85, 0.35), 1, 2, True, 0.95, 0.06, 0.06,
            melodic_parts=2, kick_weight=0.9, snare_weight=0.9, hat_weight=0.4, melody_hold_ratio=0.18),
    Profile("Challenge", 9, 4.5, (1.0, 0.6, 0.9, 0.6), 1, 3, True, 0.8, 0.10, 0.08,
            melodic_parts=2, kick_weight=1.0, snare_weight=1.0, hat_weight=0.7, melody_hold_ratio=0.22),
)
PROFILE_BY_NAME = {p.name.lower(): p for p in PROFILES}
DEFAULT_DIFFICULTIES = ("beginner", "low", "medium", "high")
_DIFFICULTY_ALIASES = {
    "low": "easy",
    "低": "easy",
    "medium": "medium",
    "mid": "medium",
    "中": "medium",
    "high": "hard",
    "高": "hard",
}


def resolve_profiles(selection: Sequence[str]) -> tuple[Profile, ...]:
    """Map user-facing difficulty words (low/medium/high, or an exact name) to profiles.

    low -> Easy, medium -> Medium, high -> Hard. "Beginner" and "Challenge" are
    reachable by name, and "all" yields every profile. Order is preserved and
    duplicates dropped.
    """
    if not selection:
        raise ValueError("choose at least one difficulty (low, medium, high)")
    resolved: dict[str, Profile] = {}
    for raw in selection:
        word = raw.strip().lower()
        if word == "all":
            resolved.update({p.name: p for p in PROFILES})
            continue
        profile = PROFILE_BY_NAME.get(_DIFFICULTY_ALIASES.get(word, word))
        if profile is None:
            valid = "low, medium, high, beginner, challenge, all"
            raise ValueError(f"unknown difficulty {raw!r}; valid difficulties: {valid}")
        resolved.setdefault(profile.name, profile)
    return tuple(resolved.values())


@dataclass(frozen=True)
class Chart:
    name: str
    meter: int
    measures: tuple[tuple[str, ...], ...]  # one char per column in every row
    steps_type: str = DANCE_SINGLE.name


@dataclass(frozen=True)
class ChartStats:
    rows: int
    notes: int
    jumps: int
    holds: int
    average_rows_per_second: float
    peak_rows_per_second: float
    max_jack_run: int


def _slot_scores(features: GridFeatures, profile: Profile) -> tuple[np.ndarray, np.ndarray]:
    """Return (score, raw) per slot; raw is the unweighted loudness."""
    weights = np.asarray(_BAND_WEIGHTS)
    raw = (features.strengths * weights).max(axis=1)
    local_max = maximum_filter1d(raw, size=_LOCAL_WINDOW_SLOTS, mode="nearest")
    relative = raw / np.maximum(local_max, 1e-6)
    position = np.asarray(profile.slot_weights)[np.arange(len(raw)) % SLOTS_PER_BEAT]
    return (0.5 * raw + 0.5 * relative) * position, raw


def _select_slots(features: GridFeatures, profile: Profile) -> list[int]:
    score, raw = _slot_scores(features, profile)
    candidate = (raw >= _MIN_ABSOLUTE_STRENGTH) & (score > 0)
    if not candidate.any():
        return []
    measures_with_music = candidate.reshape(-1, SLOTS_PER_MEASURE).any(axis=1).sum()
    active_seconds = measures_with_music * SLOTS_PER_MEASURE * features.slot_seconds
    target = int(round(profile.target_rows_per_second * active_seconds))

    occupied = np.zeros(features.n_slots, dtype=bool)
    chosen: list[int] = []
    gap = profile.min_gap_slots
    for slot in np.argsort(-score, kind="stable"):
        if len(chosen) >= target:
            break
        if not candidate[slot]:
            continue
        lo, hi = max(0, slot - gap + 1), min(features.n_slots, slot + gap)
        if occupied[lo:hi].any():
            continue
        occupied[slot] = True
        chosen.append(int(slot))
    return sorted(chosen)


@dataclass(frozen=True)
class _Cursor:
    """Pattern state carried from one note to the next."""

    prev_cols: tuple[int, ...] = ()
    prev_slot: int = -100
    run: int = 0
    jumps: int = 0
    events: int = 0
    last_was_jump: bool = False
    usage: tuple[int, ...] = ()
    holds: int = 0


def _travel(columns: Sequence[int], previous: Sequence[int]) -> int:
    """Fewest columns between any of `columns` and any of `previous` (0 with no history)."""
    return min((abs(c - p) for c in columns for p in previous), default=0)


def _pick_jump(
    cursor: _Cursor, layout: KeyLayout, rng: np.random.Generator, target: float | None = None
) -> tuple[int, int]:
    reachable = [
        pair for pair in layout.jump_pairs
        if _travel(pair, cursor.prev_cols) <= layout.max_step
    ] or list(layout.jump_pairs)

    def score(pair: tuple[int, int]) -> float:
        overlap = len(set(pair) & set(cursor.prev_cols))
        travel = _travel(pair, cursor.prev_cols)
        score = -10.0 * overlap - layout.leap_penalty * max(0, travel - 1) + float(rng.random()) * 0.5
        if target is not None:  # keep one of the two notes where the melody is
            score -= 0.6 * min(abs(c - target) for c in pair)
        return score

    return max(reachable, key=score)


def _pick_column(
    cursor: _Cursor,
    strengths: np.ndarray | None,
    profile: Profile,
    layout: KeyLayout,
    blocked: frozenset[int],
    rng: np.random.Generator,
    bonus: Sequence[float] | None = None,
) -> int:
    band = int(np.argmax(strengths)) if strengths is not None else -1
    total = max(sum(cursor.usage), 1)
    prev_hands = {layout.hands[c] for c in cursor.prev_cols} - {NEUTRAL}
    best_column, best_score = -1, -1e9
    for column in range(layout.columns):
        if column in blocked:
            continue
        if column in cursor.prev_cols and cursor.run >= profile.max_same_column_run:
            continue
        travel = _travel((column,), cursor.prev_cols)
        if travel > layout.max_step:
            continue
        score = float(rng.random()) * 0.5
        if column in cursor.prev_cols:
            score -= 1.5
        score -= layout.leap_penalty * max(0, travel - 1)
        hand = layout.hands[column]
        if prev_hands and hand != NEUTRAL and hand not in prev_hands:
            score += layout.hand_bonus
        if band == 0 and column in layout.bass_columns:
            score += 0.4
        if band == 2 and column in layout.treble_columns:
            score += 0.4
        if bonus is not None:
            score += bonus[column]
        if cursor.prev_cols and min(abs(column - c) for c in cursor.prev_cols) == 1:
            score += 0.3
        score += (1.0 / layout.columns - cursor.usage[column] / total) * layout.usage_weight
        if score > best_score:
            best_column, best_score = column, score
    if best_column < 0:  # every nearby column was ruled out; take the closest free one
        free = [c for c in range(layout.columns) if c not in blocked]
        best_column = min(free, key=lambda c: _travel((c,), cursor.prev_cols))
    return best_column


def _wants_jump(cursor: _Cursor, slot: int, strength: float, profile: Profile) -> bool:
    if not profile.allow_jumps or cursor.last_was_jump:
        return False
    if slot - cursor.prev_slot < 2 or slot % 2 != 0:
        return False
    if strength < profile.jump_strength:
        return False
    return cursor.jumps < profile.max_jump_ratio * (cursor.events + 1)


def _hold_release(slot: int, length: int, n_slots: int) -> int | None:
    """Slot a hold of about `length` slots starting here is released, or None if it can't be one."""
    if slot % _HOLD_STEP_SLOTS != 0:
        return None
    length = min(int(length), _MAX_HOLD_SLOTS)
    length -= length % _HOLD_STEP_SLOTS
    if length < _MIN_HOLD_SLOTS or slot + length >= n_slots:
        return None
    return slot + length


def _hold_end(
    slot: int, features: GridFeatures, profile: Profile, cursor: _Cursor, enabled: bool
) -> int | None:
    """Slot where a hold starting here would be released, or None for a plain tap."""
    if not enabled or features.sustain is None or profile.hold_ratio <= 0:
        return None
    if cursor.holds >= profile.hold_ratio * (cursor.events + 1):
        return None
    return _hold_release(slot, int(features.sustain[slot]), features.n_slots)


_Placed = dict[int, dict[int, str]]  # slot -> {column: "1" | "2" | "3"}


def _advance(
    cursor: _Cursor, slot: int, columns: tuple[int, ...], is_jump: bool, held_for_hold: bool
) -> _Cursor:
    """The cursor after placing a note (or jump) at `slot`."""
    run = 1 if is_jump or not (set(columns) & set(cursor.prev_cols)) else cursor.run + 1
    return _Cursor(
        prev_cols=columns,
        prev_slot=slot,
        run=run,
        jumps=cursor.jumps + (1 if is_jump else 0),
        events=cursor.events + 1,
        last_was_jump=is_jump,
        usage=tuple(u + (1 if c in columns else 0) for c, u in enumerate(cursor.usage)),
        holds=cursor.holds + (1 if held_for_hold else 0),
    )


def _record(
    placed: _Placed, slot: int, columns: tuple[int, ...], end: int | None
) -> tuple[tuple[int, int], ...]:
    """Write a note, jump or hold into `placed`; returns the hold now in force, if any."""
    if end is None:
        placed.setdefault(slot, {}).update({c: "1" for c in columns})
        return ()
    placed.setdefault(slot, {})[columns[0]] = "2"
    placed.setdefault(end, {})[columns[0]] = "3"
    return ((columns[0], end),)


def _assign_columns(
    slots: list[int],
    features: GridFeatures,
    profile: Profile,
    layout: KeyLayout,
    rng: np.random.Generator,
    holds: bool,
) -> _Placed:
    cursor = _Cursor(usage=(0,) * layout.columns)
    placed: _Placed = {}
    held: tuple[tuple[int, int], ...] = ()  # (column, release slot); at most one
    for slot in slots:
        held = tuple(h for h in held if h[1] >= slot)
        blocked = frozenset(column for column, _ in held)
        strengths = features.strengths[slot]
        loudness = float(strengths.max())
        end: int | None = None
        if not held and _wants_jump(cursor, slot, loudness, profile):
            columns: tuple[int, ...] = _pick_jump(cursor, layout, rng)
            is_jump = True
        else:
            columns = (_pick_column(cursor, strengths, profile, layout, blocked, rng),)
            is_jump = False
            if not held:
                end = _hold_end(slot, features, profile, cursor, holds)
        held = _record(placed, slot, columns, end) or held
        cursor = _advance(cursor, slot, columns, is_jump, end is not None)
    return placed


# --- charts from melody and drum events ---------------------------------------------------

_LANE_PULL = 1.6  # a melody note wants the lane its pitch maps to...
_LANE_FALLOFF = 0.7  # ...and loses this much per lane of distance


def _event_bonus(event: events.Event, layout: KeyLayout) -> list[float]:
    """Per-column preference: melody follows its pitch, drums go where a drummer's hands are."""
    columns = range(layout.columns)
    centre = (layout.columns - 1) / 2
    if event.kind == events.MELODY and event.lane is not None:
        return [_LANE_PULL - _LANE_FALLOFF * abs(c - event.lane) for c in columns]
    if event.kind == events.KICK:
        return [1.0 - 0.7 * abs(c - centre) for c in columns]
    if event.kind == events.SNARE:
        return [0.9 - 0.45 * min(abs(c - (centre - 1)), abs(c - (centre + 1))) for c in columns]
    return [0.8 - 0.4 * min(c, layout.columns - 1 - c) for c in columns]  # hi-hat: outer lanes


def _jump_allowed(cursor: _Cursor, slot: int, profile: Profile) -> bool:
    if not profile.allow_jumps or cursor.last_was_jump:
        return False
    if slot - cursor.prev_slot < 2 or slot % 2 != 0:
        return False
    return cursor.jumps < profile.max_jump_ratio * (cursor.events + 1)


def _melody_hold_end(
    event: events.Event, n_slots: int, profile: Profile, cursor: _Cursor, enabled: bool
) -> int | None:
    if not enabled or event.kind != events.MELODY or profile.melody_hold_ratio <= 0:
        return None
    if cursor.holds >= profile.melody_hold_ratio * (cursor.events + 1):
        return None
    return _hold_release(event.slot, event.length_slots, n_slots)


def _assign_event_columns(
    chosen: list[events.Event],
    n_slots: int,
    profile: Profile,
    layout: KeyLayout,
    rng: np.random.Generator,
    holds: bool,
) -> _Placed:
    cursor = _Cursor(usage=(0,) * layout.columns)
    placed: _Placed = {}
    held: tuple[tuple[int, int], ...] = ()
    for event in chosen:
        slot = event.slot
        held = tuple(h for h in held if h[1] >= slot)
        blocked = frozenset(column for column, _ in held)
        end: int | None = None
        if not held and event.partner is not None and _jump_allowed(cursor, slot, profile):
            columns: tuple[int, ...] = _pick_jump(cursor, layout, rng, event.lane)
            is_jump = True
        else:
            bonus = _event_bonus(event, layout)
            columns = (_pick_column(cursor, None, profile, layout, blocked, rng, bonus),)
            is_jump = False
            if not held:
                end = _melody_hold_end(event, n_slots, profile, cursor, holds)
        held = _record(placed, slot, columns, end) or held
        cursor = _advance(cursor, slot, columns, is_jump, end is not None)
    return placed


def measure_rows(placed: _Placed, measure: int, columns: int) -> tuple[str, ...]:
    base = measure * SLOTS_PER_MEASURE
    empty = "0" * columns
    rows = []
    for offset in range(SLOTS_PER_MEASURE):
        cells = placed.get(base + offset, {})
        rows.append("".join(cells.get(c, "0") for c in range(columns)))
    used = [i for i, r in enumerate(rows) if r != empty]
    if all(i % 4 == 0 for i in used):
        return tuple(rows[::4])
    if all(i % 2 == 0 for i in used):
        return tuple(rows[::2])
    return tuple(rows)


def generate_chart(
    features: GridFeatures,
    profile: Profile,
    seed: int = 0,
    layout: KeyLayout = DANCE_SINGLE,
    holds: bool = True,
    music: events.MusicFeatures | None = None,
) -> Chart:
    """A chart for one difficulty.

    With `music` (melody and drum events read from separated stems) the chart follows the
    song's parts; without it, notes come from onsets in the mix alone.
    """
    rng = np.random.default_rng(seed)
    if music is None:
        slots = _select_slots(features, profile)
        placed = _assign_columns(slots, features, profile, layout, rng, holds)
    else:
        chosen = events.select_events(music, profile, layout.columns)
        placed = _assign_event_columns(chosen, features.n_slots, profile, layout, rng, holds)
    measures = tuple(
        measure_rows(placed, m, layout.columns) for m in range(features.n_measures)
    )
    return Chart(
        name=profile.name, meter=profile.meter, measures=measures, steps_type=layout.name
    )


def _pressed(row: str) -> int:
    """Columns that must be pressed on this row (taps and hold heads)."""
    return row.count("1") + row.count("2")


def count_rows(chart: Chart) -> int:
    return sum(1 for m in chart.measures for r in m if _pressed(r))


def _row_times(chart: Chart, slot_seconds: float) -> list[tuple[float, str]]:
    timed = []
    for index, measure in enumerate(chart.measures):
        step = SLOTS_PER_MEASURE // len(measure)
        for i, row in enumerate(measure):
            if _pressed(row):
                slot = index * SLOTS_PER_MEASURE + i * step
                timed.append((slot * slot_seconds, row))
    return timed


def _peak_rate(times: list[float]) -> float:
    peak, start = 0, 0
    for end, moment in enumerate(times):
        while moment - times[start] >= 1.0:
            start += 1
        peak = max(peak, end - start + 1)
    return float(peak)


def _max_run(rows: list[str]) -> int:
    best = run = 0
    previous = None
    for row in rows:
        pattern = row.replace("2", "1").replace("3", "0")
        run = run + 1 if pattern == previous and _pressed(row) == 1 else 1
        previous = pattern
        best = max(best, run)
    return best if rows else 0


def chart_stats(chart: Chart, slot_seconds: float) -> ChartStats:
    timed = _row_times(chart, slot_seconds)
    rows = [r for _, r in timed]
    times = [t for t, _ in timed]
    span = (len(chart.measures) * SLOTS_PER_MEASURE * slot_seconds) or 1.0
    return ChartStats(
        rows=len(rows),
        notes=sum(_pressed(r) for r in rows),
        jumps=sum(1 for r in rows if _pressed(r) >= 2),
        holds=sum(r.count("2") for r in rows),
        average_rows_per_second=round(len(rows) / span, 2),
        peak_rows_per_second=_peak_rate(times),
        max_jack_run=_max_run(rows),
    )
