"""Where the song sings something again: a chorus coming back, a verse repeated.

Repeated music should get repeated choreography, so the choreographer needs to know which
measures are a reprise of which. Found from the melody: two stretches repeat when, measure
by measure, their notes land on the same slots with the same pitches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from .features import SLOTS_PER_MEASURE

Measure = list[tuple[int, int]]  # (slot in measure, MIDI pitch)

_SLOT_REACH = 1
_PITCH_REACH = 1
_STEP_MATCH = 0.4  # a measure this similar keeps a repeat going
_MIN_MATCH = 0.55  # average similarity for a stretch to count as a repeat
_MIN_MEASURES = 4
_MIN_SUNG_MEASURES = 3


@dataclass(frozen=True)
class Repeat:
    source_start: int
    source_end: int  # inclusive
    target_start: int
    target_end: int
    match: float  # average melody similarity over the sung measures

    @property
    def length(self) -> int:
        return self.target_end - self.target_start + 1


def melody_by_measure(facts: dict[str, Any]) -> list[Measure]:
    count = facts["n_slots"] // SLOTS_PER_MEASURE
    measures: list[Measure] = [[] for _ in range(count)]
    for note in facts.get("melody", []):
        m = note["slot"] // SLOTS_PER_MEASURE
        if 0 <= m < count:
            measures[m].append((note["slot"] % SLOTS_PER_MEASURE, note["midi"]))
    return measures


def similarity(a: Measure, b: Measure) -> float:
    """Share of notes matched one-to-one by slot and pitch; NaN when both measures are silent."""
    if not a and not b:
        return float("nan")
    if not a or not b:
        return 0.0
    used: set[int] = set()
    hits = 0
    for slot, pitch in a:
        for k, (other_slot, other_pitch) in enumerate(b):
            if k in used:
                continue
            if abs(slot - other_slot) <= _SLOT_REACH and abs(pitch - other_pitch) <= _PITCH_REACH:
                used.add(k)
                hits += 1
                break
    return 2 * hits / (len(a) + len(b))


def _runs(measures: list[Measure], lag: int) -> list[Repeat]:
    """Stretches where measure m sounds like measure m - lag, for every m in the stretch."""
    count = len(measures)
    found = []
    m = lag
    while m < count:
        scores = []
        end = m
        while end < count:
            score = similarity(measures[end], measures[end - lag])
            if not np.isnan(score) and score < _STEP_MATCH:
                break
            scores.append(score)
            end += 1
        # silence at either edge is not part of the repeat
        first = next((i for i, s in enumerate(scores) if not np.isnan(s)), None)
        if first is not None:
            last = max(i for i, s in enumerate(scores) if not np.isnan(s))
            kept = scores[first : last + 1]
            sung = [s for s in kept if not np.isnan(s)]
            if len(kept) >= _MIN_MEASURES and len(sung) >= _MIN_SUNG_MEASURES and np.mean(sung) >= _MIN_MATCH:
                start = m + first
                found.append(Repeat(start - lag, start - lag + len(kept) - 1, start, start + len(kept) - 1,
                                    float(np.mean(sung))))
        m = end + 1
    return found


def _trimmed(repeat: Repeat, taken: set[int], measures: list[Measure]) -> Repeat | None:
    """The repeat without measures already claimed at its edges, if enough of it is left."""
    start, end = repeat.target_start, repeat.target_end
    while start <= end and start in taken:
        start += 1
    while end >= start and end in taken:
        end -= 1
    if end - start + 1 < _MIN_MEASURES or any(m in taken for m in range(start, end + 1)):
        return None
    lag = repeat.target_start - repeat.source_start
    scores = [similarity(measures[m], measures[m - lag]) for m in range(start, end + 1)]
    sung = [x for x in scores if not np.isnan(x)]
    if len(sung) < _MIN_SUNG_MEASURES or np.mean(sung) < _MIN_MATCH:
        return None
    return Repeat(start - lag, end - lag, start, end, float(np.mean(sung)))


def find_repeats(measures: list[Measure]) -> list[Repeat]:
    """Reprises in the song, each measure the target of at most one.

    Closer matches win over longer but looser ones (match squared times length), and a
    repeat that overlaps a stronger one keeps whatever part of it does not.
    """
    candidates = [run for lag in range(_MIN_MEASURES, len(measures)) for run in _runs(measures, lag)]
    candidates.sort(key=lambda r: (-(r.match**2) * r.length, r.target_start))
    taken: set[int] = set()
    chosen = []
    for candidate in candidates:
        repeat = _trimmed(candidate, taken, measures)
        if repeat is None:
            continue
        taken |= set(range(repeat.target_start, repeat.target_end + 1))
        chosen.append(repeat)
    return sorted(chosen, key=lambda r: r.target_start)


def describe(found: list[Repeat]) -> list[dict[str, Any]]:
    return [
        {"source": [r.source_start, r.source_end], "target": [r.target_start, r.target_end],
         "match": round(r.match, 2)}
        for r in found
    ]
