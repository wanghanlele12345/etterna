"""Move each chart note onto the exact moment its sound is heard.

Choreography is written on a 16th-note grid; singers do not sing on it. This pass keeps
every choice of the choreography (which notes, which lanes, holds, jumps) and only nudges
timing: a note moves to the sung attack or drum hit it answers if one is within reach, and
a hold ends when the sung note it holds ends. The result is written with fine rows
(192 per measure), so the chart follows the performance to within a few milliseconds.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from . import chartfile, layouts, review, timing
from .chartfile import ChartBlock
from .errors import SimfileError
from .features import SLOTS_PER_MEASURE

FINE_ROWS = 192  # rows per measure in the written file
_FINE_PER_SLOT = FINE_ROWS // SLOTS_PER_MEASURE
_RESOLUTIONS = (4, 8, 12, 16, 24, 32, 48, 64, 96, 192)
DEFAULT_TOLERANCE_SECONDS = 0.09  # how far a note may move to meet its sound
_MIN_ROW_GAP = 0.03  # rows never get closer than this
_MIN_HOLD_SECONDS = 0.15
_MAX_HOLD_MEASURES = 2
_MOVED_SECONDS = 0.001


@dataclass
class _Note:
    time: float
    column: int
    char: str  # "1" tap, "2" hold head, "3" hold tail


def _timing(text: str) -> tuple[float, float]:
    """(time of beat 0, seconds per 16th slot) for a constant-tempo file."""
    offset = re.search(r"#OFFSET:([^;]*);", text)
    bpms = re.search(r"#BPMS:([^;]*);", text)
    if not offset or not bpms:
        raise SimfileError("the simfile has no #OFFSET or #BPMS")
    changes = [part for part in bpms.group(1).split(",") if part.strip()]
    if len(changes) != 1:
        raise SimfileError("only charts with a constant tempo can be aligned (found tempo changes)")
    bpm = float(changes[0].split("=")[1])
    return -float(offset.group(1)), 60.0 / bpm / 4


def _notes(block: ChartBlock, columns: int, first_beat: float, slot_seconds: float) -> list[_Note]:
    notes = []
    for m, rows in enumerate(block.measures):
        for i, row in enumerate(rows):
            slot = m * SLOTS_PER_MEASURE + i * SLOTS_PER_MEASURE / len(rows)
            for column, ch in enumerate(row[:columns]):
                if ch in "123":
                    notes.append(_Note(first_beat + slot * slot_seconds, column, ch))
    return notes


def _targets(facts: dict[str, Any], first_beat: float, slot_seconds: float) -> np.ndarray:
    times = [
        n.get("start_time", first_beat + n["slot"] * slot_seconds) for n in facts.get("melody", [])
    ]
    for hits in facts.get("drum_times", {}).values():
        times.extend(hits)
    return np.array(sorted(times))


def _align_presses(
    notes: list[_Note], targets: np.ndarray, tolerance: float
) -> tuple[int, int, int, list[float]]:
    """Move rows of presses (taps and hold heads); returns (rows, moved, unmatched, shifts)."""
    rows: dict[float, list[_Note]] = {}
    for note in notes:
        if note.char != "3":
            rows.setdefault(round(note.time, 6), []).append(note)
    moved = unmatched = 0
    shifts: list[float] = []
    last = -1e9
    for original in sorted(rows):
        target = timing.nearest(targets, original, tolerance, tolerance)
        if target is None:
            unmatched += 1
        new = original if target is None else target
        if new - last < _MIN_ROW_GAP:  # would cross or crowd the row before it
            new = original if original - last >= _MIN_ROW_GAP else last + _MIN_ROW_GAP
        for note in rows[original]:
            note.time = new
        if abs(new - original) > _MOVED_SECONDS:
            moved += 1
            shifts.append(abs(new - original))
        last = new
    return len(rows), moved, unmatched, shifts


def _align_tails(
    notes: list[_Note], original_times: dict[int, float], facts: dict[str, Any],
    tolerance: float, measure_seconds: float, slot_seconds: float,
) -> tuple[int, int, list[float]]:
    """End each hold with the sung note it holds; returns (holds, matched, shifts)."""
    sung = [(n["start_time"], n["end_time"]) for n in facts.get("melody", []) if "end_time" in n]
    starts = np.array([s for s, _ in sung])
    ordered = sorted(notes, key=lambda n: n.time)
    holds = matched = 0
    shifts: list[float] = []
    for index, head in enumerate(ordered):
        if head.char != "2":
            continue
        tail = next((n for n in ordered[index + 1 :] if n.column == head.column and n.char == "3"), None)
        if tail is None:
            continue
        holds += 1
        head_shift = head.time - original_times[id(head)]
        wanted = tail.time + head_shift  # by default keep the hold's length
        found = timing.nearest(starts, head.time, tolerance, tolerance) if len(starts) else None
        if found is not None:
            wanted = sung[int(np.argmin(np.abs(starts - found)))][1]
            matched += 1
        # stop before the lane is pressed again, and before another hold or jump starts
        limit = head.time + _MAX_HOLD_MEASURES * measure_seconds
        for other in ordered[index + 1 :]:
            if other is tail or other.time <= head.time:
                continue
            if other.column == head.column and other.char != "3":
                limit = min(limit, other.time - max(_MIN_ROW_GAP * 2, slot_seconds / 2))
            elif other.char == "2":
                limit = min(limit, other.time - _MIN_ROW_GAP)
        new = min(max(wanted, head.time + _MIN_HOLD_SECONDS), limit)
        new = max(new, head.time + _MIN_ROW_GAP)
        if abs(new - tail.time) > _MOVED_SECONDS:
            shifts.append(abs(new - tail.time))
        tail.time = new
    return holds, matched, shifts


def _render(notes: list[_Note], n_measures: int, columns: int, first_beat: float, slot_seconds: float) -> tuple[tuple[str, ...], ...]:
    fine_seconds = slot_seconds / _FINE_PER_SLOT
    last_fine = n_measures * FINE_ROWS - 1
    cells: dict[int, dict[int, str]] = {}
    for note in sorted(notes, key=lambda n: (n.time, n.char != "3")):
        fine = min(max(int(round((note.time - first_beat) / fine_seconds)), 0), last_fine)
        step = -1 if note.char == "3" else 1  # a crowded tail gives way backwards, a press forwards
        while note.column in cells.get(fine, {}) and 0 <= fine + step <= last_fine:
            fine += step
        cells.setdefault(fine, {})[note.column] = note.char
    measures = []
    for m in range(n_measures):
        base = m * FINE_ROWS
        used = [f - base for f in cells if base <= f < base + FINE_ROWS]
        resolution = next(r for r in _RESOLUTIONS if all(u % (FINE_ROWS // r) == 0 for u in used))
        stride = FINE_ROWS // resolution
        rows = []
        for i in range(resolution):
            row_cells = cells.get(base + i * stride, {})
            rows.append("".join(row_cells.get(c, "0") for c in range(columns)))
        measures.append(tuple(rows))
    return tuple(measures)


def _align_block(
    text: str, block: ChartBlock, facts: dict[str, Any], tolerance: float
) -> tuple[str, dict[str, Any]]:
    first_beat, slot_seconds = _timing(text)
    layout = layouts.layout_for_steps_type(block.steps_type)
    columns = layout.columns if layout else len(block.measures[0][0])
    notes = _notes(block, columns, first_beat, slot_seconds)
    original = {id(n): n.time for n in notes}
    targets = _targets(facts, first_beat, slot_seconds)
    rows, moved, unmatched, shifts = _align_presses(notes, targets, tolerance)
    measure_seconds = slot_seconds * SLOTS_PER_MEASURE
    holds, matched, tail_shifts = _align_tails(notes, original, facts, tolerance, measure_seconds, slot_seconds)
    measures = _render(notes, len(block.measures), columns, first_beat, slot_seconds)
    report = {
        "difficulty": block.difficulty,
        "steps_type": block.steps_type,
        "rows": rows,
        "moved": moved,
        "unmatched": unmatched,
        "mean_shift_ms": round(float(np.mean(shifts)) * 1000, 1) if shifts else 0.0,
        "max_shift_ms": round(float(np.max(shifts)) * 1000, 1) if shifts else 0.0,
        "holds": holds,
        "holds_ended_with_the_voice": matched,
        "mean_tail_shift_ms": round(float(np.mean(tail_shifts)) * 1000, 1) if tail_shifts else 0.0,
    }
    return chartfile.replace_measures(text, block, measures), report


def align_chart(
    ssc_path: Path,
    difficulty: str | None = None,
    steps_type: str | None = None,
    tolerance_seconds: float = DEFAULT_TOLERANCE_SECONDS,
) -> dict[str, Any]:
    """Align one chart (or every chart) of a song to the attacks listed in its music.json."""
    path = Path(ssc_path)
    facts_path = path.parent / review.MUSIC_FILE
    if not facts_path.is_file():
        raise SimfileError(f"no {review.MUSIC_FILE} beside {path.name}; build the song with make_song_from_video")
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    text = path.read_text(encoding="utf-8")
    wanted = (
        [(steps_type, difficulty)] if difficulty
        else chartfile.list_charts(text)
    )
    reports = []
    for chart_type, name in wanted:
        block = chartfile.find_chart(text, chart_type, name)
        text, report = _align_block(text, block, facts, tolerance_seconds)
        reports.append(report)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)
    return {"ssc_path": str(path), "charts": reports}
