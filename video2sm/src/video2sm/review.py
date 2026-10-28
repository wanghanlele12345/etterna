"""Reviewing and editing charts, measure by measure.

A language model does the choreography: it reads a chart next to what the music contains
(`inspect_chart`), decides how the fingers should move, and rewrites measures (`edit_chart`).
This module is the model's eyes and hands. It never decides what is musical; it shows the
facts, applies what it is told, and refuses edits that cannot be played or are malformed.

Notation for a measure's notes (16 slots, s0 is the downbeat, lanes counted from 1):
    s4:3        a tap on lane 3 at slot 4
    s8:2+6      a jump (two taps)
    s8:H3       a hold starts on lane 3
    s12:|3      that hold ends
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import chartfile, charting, layouts
from .chartfile import ChartBlock
from .errors import SimfileError
from .features import SLOTS_PER_BEAT, SLOTS_PER_MEASURE

MUSIC_FILE = "music.json"
_TOKEN = re.compile(r"^s(\d+):(.+)$", re.IGNORECASE)
_ITEM = re.compile(r"^([h|]?)(\d+)$", re.IGNORECASE)
_NOTATION_HELP = "write slot:lane like s4:3, s8:2+6 (jump), s8:H3 (hold start), s12:|3 (hold end)"
_SUPPORT_REACH = 1  # a note is "supported" by a melody onset or drum hit this many slots away
_DENSITY_SLACK = 1.3
_UNSUPPORTED_WARN_SHARE = 0.4
_LONG_SUNG_SLOTS = SLOTS_PER_MEASURE  # a sung note this long (4 beats) is a held vowel: it wants a hold
_LONG_NOTES_LISTED = 10
_SIMILAR_MIN = 0.5
_SIMILAR_LISTED = 2
_VOCABULARY_SIZE = 6
_MAX_PRESSES = 2

Cells = dict[int, str]  # column (0-based) -> "1" tap, "2" hold head, "3" hold tail
Slots = dict[int, Cells]  # slot within the measure -> cells
_GLYPH = {"1": "", "2": "H", "3": "|"}
_CHAR = {"": "1", "H": "2", "|": "3"}


# --- notation -------------------------------------------------------------------------------


def parse_notes(text: str, columns: int) -> Slots:
    slots: Slots = {}
    for token in re.split(r"[\s,]+", text.strip()):
        if not token:
            continue
        match = _TOKEN.match(token)
        if match is None:
            raise SimfileError(f"cannot read token {token!r}: {_NOTATION_HELP}")
        slot = int(match.group(1))
        if not 0 <= slot < SLOTS_PER_MEASURE:
            raise SimfileError(f"slot {slot} is outside 0-{SLOTS_PER_MEASURE - 1}")
        if slot in slots:
            raise SimfileError(f"slot {slot} appears twice; put both lanes in one token (s{slot}:2+5)")
        cells: Cells = {}
        for item in match.group(2).split("+"):
            parsed = _ITEM.match(item.strip())
            if parsed is None:
                raise SimfileError(f"cannot read {item!r} in {token!r}: {_NOTATION_HELP}")
            lane = int(parsed.group(2))
            if not 1 <= lane <= columns:
                raise SimfileError(f"lane {lane} is outside 1-{columns}")
            if lane - 1 in cells:
                raise SimfileError(f"lane {lane} appears twice at slot {slot}")
            cells[lane - 1] = _CHAR[parsed.group(1).upper()]
        if sum(1 for ch in cells.values() if ch != "3") > _MAX_PRESSES:
            raise SimfileError(f"slot {slot} presses more than two lanes; at most two at once")
        slots[slot] = cells
    return slots


def format_notes(slots: Slots) -> str:
    parts = []
    for slot in sorted(slots):
        items = "+".join(f"{_GLYPH[ch]}{col + 1}" for col, ch in sorted(slots[slot].items()))
        parts.append(f"s{slot}:{items}")
    return " ".join(parts)


def _measure_slots(rows: tuple[str, ...], columns: int) -> Slots:
    """The measure on the 16th grid. Finer rows (from align_chart) are shown at their nearest 16th."""
    count = len(rows)
    if not count:
        raise SimfileError("a measure has no rows")
    slots: Slots = {}
    for index, row in enumerate(rows):
        if len(row) != columns:
            raise SimfileError(f"a row has {len(row)} columns, expected {columns}")
        cells = {col: ch for col, ch in enumerate(row) if ch in "123"}
        if not cells:
            continue
        slot = min(int(index * SLOTS_PER_MEASURE / count + 0.5), SLOTS_PER_MEASURE - 1)
        merged = slots.setdefault(slot, {})
        for col, ch in cells.items():
            merged.setdefault(col, ch)
    return slots


def _slot_rows(slots: Slots, columns: int) -> tuple[str, ...]:
    return charting.measure_rows(dict(slots), 0, columns)


# --- loading ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedChart:
    path: Path
    text: str
    block: ChartBlock
    columns: int
    layout: layouts.KeyLayout | None
    facts: dict[str, Any] | None
    slot_seconds: float
    measures: list[Slots]


def _read_facts(path: Path) -> dict[str, Any] | None:
    facts_path = path.parent / MUSIC_FILE
    if not facts_path.is_file():
        return None
    return json.loads(facts_path.read_text(encoding="utf-8"))


def _bpm(text: str) -> float:
    match = re.search(r"#BPMS:[^=]*=([0-9.]+)", text)
    return float(match.group(1)) if match else 120.0


def load_chart(ssc_path: Path, difficulty: str, steps_type: str | None) -> LoadedChart:
    path = Path(ssc_path)
    if not path.is_file():
        raise SimfileError(f"simfile not found: {path}")
    text = path.read_text(encoding="utf-8")
    block = chartfile.find_chart(text, steps_type, difficulty)
    layout = layouts.layout_for_steps_type(block.steps_type)
    columns = layout.columns if layout else len(block.measures[0][0])
    facts = _read_facts(path)
    slot_seconds = float(facts["slot_seconds"]) if facts else 60.0 / _bpm(text) / SLOTS_PER_BEAT
    return LoadedChart(
        path=path, text=text, block=block, columns=columns, layout=layout, facts=facts,
        slot_seconds=slot_seconds,
        measures=[_measure_slots(rows, columns) for rows in block.measures],
    )


# --- the music, per measure --------------------------------------------------------------------


def _melody_by_measure(facts: dict[str, Any] | None) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    for note in (facts or {}).get("melody", []):
        out.setdefault(note["slot"] // SLOTS_PER_MEASURE, []).append(note)
    return out


def _drums_by_measure(facts: dict[str, Any] | None) -> dict[int, dict[str, list[int]]]:
    out: dict[int, dict[str, list[int]]] = {}
    for kind, hits in (facts or {}).get("drums", {}).items():
        for slot in hits:
            out.setdefault(slot // SLOTS_PER_MEASURE, {}).setdefault(kind, []).append(slot % SLOTS_PER_MEASURE)
    return out


def _signatures(facts: dict[str, Any] | None, count: int) -> list[frozenset]:
    melody, drums = _melody_by_measure(facts), _drums_by_measure(facts)
    sigs = []
    for m in range(count):
        items = {("m", n["slot"] % SLOTS_PER_MEASURE, n["midi"]) for n in melody.get(m, [])}
        items |= {(k, s) for k, slots in drums.get(m, {}).items() for s in slots}
        sigs.append(frozenset(items))
    return sigs


def _similar_earlier(sigs: list[frozenset], m: int) -> list[tuple[int, float]]:
    here = sigs[m]
    if len(here) < 2:
        return []
    scored = []
    for earlier in range(m):
        other = sigs[earlier]
        union = len(here | other)
        similarity = len(here & other) / union if union else 0.0
        if similarity >= _SIMILAR_MIN:
            scored.append((earlier, similarity))
    return sorted(scored, key=lambda pair: -pair[1])[:_SIMILAR_LISTED]


def _hit_slots(facts: dict[str, Any] | None) -> set[int] | None:
    if facts is None:
        return None
    hits = {n["slot"] for n in facts.get("melody", []) + facts.get("second_melody", [])}
    for slots in facts.get("drums", {}).values():
        hits.update(slots)
    return hits


# --- statistics and checks ------------------------------------------------------------------------


def _pressed(cells: Cells) -> int:
    return sum(1 for ch in cells.values() if ch != "3")


def _rows(measures: list[Slots]) -> list[tuple[int, int, int, Cells]]:
    """(absolute slot, measure, slot in measure, cells) of every row, in time order."""
    return [
        (m * SLOTS_PER_MEASURE + s, m, s, cells)
        for m, slots in enumerate(measures)
        for s, cells in sorted(slots.items())
    ]


def _unheld_long_notes(loaded: LoadedChart, measures: list[Slots]) -> list[dict[str, Any]]:
    """Sustained sung notes the chart plays as a tap, or not at all, instead of a hold.

    The "answers N% of the sung notes" figures cannot show this: a tap on a held vowel's
    first slot counts as answering it. Beginner charts have no holds by design.
    """
    profile = charting.PROFILE_BY_NAME.get(loaded.block.difficulty.lower())
    if loaded.facts is None or (profile is not None and profile.melody_hold_ratio <= 0):
        return []
    heads = {slot for slot, _, _, cells in _rows(measures) if "2" in cells.values()}
    return [
        n for n in loaded.facts.get("melody", [])
        if n["length_slots"] >= _LONG_SUNG_SLOTS
        and not any(n["slot"] + d in heads for d in range(-_SUPPORT_REACH, _SUPPORT_REACH + 1))
    ]


def _unheld_text(notes: list[dict[str, Any]]) -> str:
    listed = ", ".join(
        f"m{n['slot'] // SLOTS_PER_MEASURE}@{n['slot'] % SLOTS_PER_MEASURE}/{n['length_slots']}"
        for n in notes[:_LONG_NOTES_LISTED]
    )
    more = f" and {len(notes) - _LONG_NOTES_LISTED} more" if len(notes) > _LONG_NOTES_LISTED else ""
    return (
        f"{len(notes)} long sung notes (4+ beats) not played as holds: {listed}{more} "
        "(a held vowel wants a hold: sSLOT:Hlane at its start, s..:|lane where it ends)"
    )


def _stats(loaded: LoadedChart, measures: list[Slots]) -> dict[str, Any]:
    rows = [(slot, cells) for slot, _, _, cells in _rows(measures) if _pressed(cells)]
    seconds = len(measures) * SLOTS_PER_MEASURE * loaded.slot_seconds
    hits = _hit_slots(loaded.facts)
    unsupported = None
    if hits is not None:
        unsupported = sum(
            1 for slot, _ in rows
            if not any(slot + d in hits for d in range(-_SUPPORT_REACH, _SUPPORT_REACH + 1))
        )
    masks = [
        frozenset(s for s, cells in slots.items() if _pressed(cells))
        for slots in measures
    ]
    played = [m for m in masks if m]
    vocabulary = (
        sum(count for _, count in Counter(played).most_common(_VOCABULARY_SIZE)) / len(played)
        if played else 0.0
    )
    singles = [next(iter(c for c, ch in cells.items() if ch != "3")) for _, cells in rows if _pressed(cells) == 1]
    reach = loaded.layout.max_step if loaded.layout else loaded.columns
    leaps = sum(1 for a, b in zip(singles, singles[1:]) if abs(a - b) > reach)
    profile = charting.PROFILE_BY_NAME.get(loaded.block.difficulty.lower())
    return {
        "measures": len(measures),
        "rows": len(rows),
        "notes": sum(_pressed(cells) for _, cells in rows),
        "holds": sum(1 for _, cells in rows for ch in cells.values() if ch == "2"),
        "jumps": sum(1 for _, cells in rows if _pressed(cells) >= 2),
        "rows_per_second": round(len(rows) / seconds, 2) if seconds else 0.0,
        "target_rows_per_second": profile.target_rows_per_second if profile else None,
        "unsupported_notes": unsupported,
        "long_notes_not_held": None if loaded.facts is None else len(_unheld_long_notes(loaded, measures)),
        "supported_share": None if unsupported is None or not rows else round(1 - unsupported / len(rows), 2),
        "rhythm_vocabulary": round(vocabulary, 2),
        "reach_violations": leaps,
    }


def _structure_errors(measures: list[Slots]) -> list[str]:
    errors: list[str] = []
    held: dict[int, tuple[int, int]] = {}
    for _, m, slot, cells in _rows(measures):
        if _pressed(cells) > _MAX_PRESSES:
            errors.append(f"m{m} s{slot} presses more than two lanes at once")
        for col, ch in sorted(cells.items()):
            where = f"m{m} s{slot}"
            if ch == "3":
                if col not in held:
                    errors.append(f"lane {col + 1} is released at {where} but was not held")
                held.pop(col, None)
            elif ch == "2":
                if col in held:
                    errors.append(f"a hold starts on lane {col + 1} at {where} while one is already held")
                held[col] = (m, slot)
            elif col in held:
                errors.append(f"lane {col + 1} is pressed at {where} while held since m{held[col][0]} s{held[col][1]}")
    for col, (m, slot) in held.items():
        errors.append(f"the hold on lane {col + 1} started at m{m} s{slot} is never released")
    return errors


def _warnings(loaded: LoadedChart, measures: list[Slots], stats: dict[str, Any]) -> list[str]:
    warnings = []
    target = stats["target_rows_per_second"]
    if target and stats["rows_per_second"] > target * _DENSITY_SLACK:
        warnings.append(
            f"density {stats['rows_per_second']}/s is well above {loaded.block.difficulty}'s "
            f"{target}/s; this will play harder than its meter says"
        )
    if stats["reach_violations"]:
        reach = loaded.layout.max_step if loaded.layout else loaded.columns
        warnings.append(f"{stats['reach_violations']} moves jump more than {reach} lanes (beyond comfortable reach)")
    if stats["unsupported_notes"] and stats["rows"]:
        if stats["unsupported_notes"] / stats["rows"] > _UNSUPPORTED_WARN_SHARE:
            warnings.append(
                f"{stats['unsupported_notes']} of {stats['rows']} notes have nothing to hear nearby "
                "(no melody onset or drum hit within a slot)"
            )
    unheld = _unheld_long_notes(loaded, measures)
    if unheld:
        warnings.append(_unheld_text(unheld))
    busy = 0
    held: set[int] = set()
    for _, _, _, cells in _rows(measures):
        pressed_now = _pressed(cells)
        starts = {c for c, ch in cells.items() if ch == "2"}
        if held and pressed_now >= 2:
            busy += 1
        held = (held | starts) - {c for c, ch in cells.items() if ch == "3"}
    if busy:
        warnings.append(f"{busy} jumps happen while a hold is down (hard to play)")
    return warnings


# --- inspecting -----------------------------------------------------------------------------------


def _section_lines(loaded: LoadedChart, sections: list[dict[str, Any]]) -> list[str]:
    """Per section: density, and how much of the singing gets a note (within a slot)."""
    pressed = {
        m * SLOTS_PER_MEASURE + s
        for m, slots in enumerate(loaded.measures)
        for s, cells in slots.items()
        if _pressed(cells)
    }
    sung = [n["slot"] for n in (loaded.facts or {}).get("melody", [])]
    lines = []
    for sec in sections:
        lo, hi = sec["start"] * SLOTS_PER_MEASURE, (sec["end"] + 1) * SLOTS_PER_MEASURE
        rows = sum(1 for slot in pressed if lo <= slot < hi)
        seconds = (hi - lo) * loaded.slot_seconds
        notes = [slot for slot in sung if lo <= slot < hi]
        answered = sum(
            1 for slot in notes
            if any(slot + d in pressed for d in range(-_SUPPORT_REACH, _SUPPORT_REACH + 1))
        )
        share = f"answers {answered / len(notes):.0%} of {len(notes)} sung notes" if notes else "no singing"
        lines.append(f"section {sec['label']} m{sec['start']}-{sec['end']}: {rows / seconds:.1f}/s, {share}")
    return lines


def _melody_text(notes: list[dict[str, Any]]) -> str:
    parts = []
    for n in notes:
        length = n["length_slots"]
        parts.append(f"{n['name']}@{n['slot'] % SLOTS_PER_MEASURE}" + (f"/{length}" if length > 1 else ""))
    return " ".join(parts)


def _drums_text(drums: dict[str, list[int]]) -> str:
    return " ".join(
        f"{letter}{','.join(str(s) for s in sorted(drums[kind]))}"
        for kind, letter in (("kick", "K"), ("snare", "S"), ("hat", "H"))
        if drums.get(kind)
    )


def inspect_chart(
    ssc_path: Path, difficulty: str, start: int = 0, count: int = 16, steps_type: str | None = None
) -> dict[str, Any]:
    """A range of measures: the chart's notes next to the melody and drums they should follow."""
    loaded = load_chart(ssc_path, difficulty, steps_type)
    total = len(loaded.measures)
    start = min(max(start, 0), max(total - 1, 0))
    count = max(0, min(count, total - start))
    melody, drums = _melody_by_measure(loaded.facts), _drums_by_measure(loaded.facts)
    sigs = _signatures(loaded.facts, total)
    stats = _stats(loaded, loaded.measures)
    bpm = _bpm(loaded.text)
    energy = (loaded.facts or {}).get("energy", [])
    sections = (loaded.facts or {}).get("sections", [])
    reprises = (loaded.facts or {}).get("repeats", [])
    reprise_of = {
        target: rep["source"][0] + (target - rep["target"][0])
        for rep in reprises
        for target in range(rep["target"][0], rep["target"][1] + 1)
    }

    lines = [
        f"{loaded.block.steps_type} {loaded.block.difficulty} (meter {loaded.block.meter}): {total} measures, "
        f"{bpm:g} BPM; a measure has 16 slots s0..s15 (s0 = downbeat, one slot = {loaded.slot_seconds:.3f}s)",
        f"lanes 1..{loaded.columns} left to right. notation: sSLOT:LANE  H=hold start  |=hold end  a+b=jump",
        "music per measure: melody NAME@SLOT[/LENGTH]; drums K=kick S=snare H=hat with their slots; "
        "'like mN(similarity)' = this measure sounds like an earlier one",
        f"stats: {json.dumps(stats, ensure_ascii=False)}",
    ]
    unheld = _unheld_long_notes(loaded, loaded.measures)
    if unheld:
        lines.append(_unheld_text(unheld))
    if sections:
        lines.append(
            "sections: " + ", ".join(f"{sec['label']} m{sec['start']}-{sec['end']}" for sec in sections)
            + "  (same letter = sounds alike; eN = loudness 0-9)"
        )
        lines.extend(_section_lines(loaded, sections))
    if reprises:
        lines.append(
            "repeats: " + ", ".join(
                f"m{r['source'][0]}-{r['source'][1]} again at m{r['target'][0]}-{r['target'][1]} (match {r['match']})"
                for r in reprises
            ) + "  (repeated music should get the same choreography)"
        )
    lines.append("")
    for m in range(start, start + count):
        heard = []
        if melody.get(m):
            heard.append("melody " + _melody_text(melody[m]))
        drum = _drums_text(drums.get(m, {}))
        if drum:
            heard.append("drums " + drum)
        if m in reprise_of:
            heard.append(f"reprise of m{reprise_of[m]}")
        like = _similar_earlier(sigs, m)
        if like and m not in reprise_of:
            heard.append("like " + " ".join(f"m{k}({sim:.2f})" for k, sim in like))
        level = f"e{min(int(energy[m] * 9 + 0.5), 9)} " if m < len(energy) else ""
        lines.append(f"m{m} {level}" + (" | ".join(heard) if heard else "(silent)"))
        lines.append("    chart " + (format_notes(loaded.measures[m]) or "(empty)"))
    return {
        "steps_type": loaded.block.steps_type,
        "difficulty": loaded.block.difficulty,
        "meter": loaded.block.meter,
        "total_measures": total,
        "start": start,
        "count": count,
        "bpm": bpm,
        "slot_seconds": loaded.slot_seconds,
        "target_rows_per_second": stats["target_rows_per_second"],
        "stats": stats,
        "text": "\n".join(lines),
    }


# --- editing --------------------------------------------------------------------------------------


def _measure_index(value: Any, total: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SimfileError(f"measure must be a number, got {value!r}")
    if not 0 <= value < total:
        raise SimfileError(f"measure {value} does not exist (0-{total - 1})")
    return value


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else [value]


def _apply(
    measures: list[Slots], exact: list[tuple[str, ...] | None], edit: dict[str, Any], columns: int
) -> None:
    """Apply one edit. `exact` holds each measure's literal rows while it is unchanged or a copy."""
    total = len(measures)
    if "measure" in edit and "notes" in edit:
        index = _measure_index(edit["measure"], total)
        measures[index] = parse_notes(str(edit["notes"]), columns)
        exact[index] = None
    elif "copy" in edit and isinstance(edit["copy"], dict):
        source = _measure_index(edit["copy"].get("from"), total)
        for target in _as_list(edit["copy"].get("to")):
            index = _measure_index(target, total)
            measures[index] = {s: dict(c) for s, c in measures[source].items()}
            exact[index] = exact[source]
    elif "clear" in edit:
        for target in _as_list(edit["clear"]):
            index = _measure_index(target, total)
            measures[index] = {}
            exact[index] = None
    elif "repeat" in edit and isinstance(edit["repeat"], dict):
        span = _as_list(edit["repeat"].get("from"))
        if len(span) != 2:
            raise SimfileError("repeat needs from: [first, last] and to: first target measure")
        first, last = (_measure_index(m, total) for m in span)
        if last < first:
            raise SimfileError(f"repeat from [{first}, {last}] is backwards")
        start = edit["repeat"].get("to")
        for offset in range(last - first + 1):
            index = _measure_index(start + offset if isinstance(start, int) else start, total)
            measures[index] = {s: dict(c) for s, c in measures[first + offset].items()}
            exact[index] = exact[first + offset]
    else:
        raise SimfileError(
            "unknown edit; use {measure, notes}, {copy: {from, to}}, {repeat: {from: [a, b], to}} "
            "or {clear}, got " + json.dumps(edit)
        )


def _write(path: Path, text: str) -> None:
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def edit_chart(
    ssc_path: Path,
    difficulty: str,
    edits: list[dict[str, Any]],
    steps_type: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply edits to one chart. All of them are checked first; if any is wrong nothing changes."""
    loaded = load_chart(ssc_path, difficulty, steps_type)
    measures = [{s: dict(c) for s, c in slots.items()} for slots in loaded.measures]
    exact: list[tuple[str, ...] | None] = list(loaded.block.measures)
    errors: list[str] = []
    for number, edit in enumerate(edits, start=1):
        try:
            if not isinstance(edit, dict):
                raise SimfileError(f"an edit must be an object, got {edit!r}")
            _apply(measures, exact, edit, loaded.columns)
        except SimfileError as exc:
            errors.append(f"edit {number}: {exc}")
    if not errors:
        errors = _structure_errors(measures)
    if errors:
        return {"ok": False, "errors": errors, "warnings": [], "stats": _stats(loaded, loaded.measures)}

    stats = _stats(loaded, measures)
    result = {
        "ok": True, "errors": [], "warnings": _warnings(loaded, measures, stats), "stats": stats,
        "written": False,
    }
    changed = [i for i, rows in enumerate(exact) if rows is not loaded.block.measures[i]]
    if changed and any(len(rows) > SLOTS_PER_MEASURE for rows in loaded.block.measures):
        result["warnings"].append(
            "this chart was aligned to the audio; run align_chart again so the edited measures are too"
        )
    if not dry_run:
        # unchanged and copied measures keep their literal rows (they may be finely aligned)
        rows = tuple(
            exact[i] if exact[i] is not None else _slot_rows(slots, loaded.columns)
            for i, slots in enumerate(measures)
        )
        _write(loaded.path, chartfile.replace_measures(loaded.text, loaded.block, rows))
        result["written"] = True
    return result


def merge_chart(
    source: Path, target: Path, difficulty: str, steps_type: str | None = None
) -> None:
    """Copy one chart's notes from `source` into the same chart of `target`."""
    source_text = Path(source).read_text(encoding="utf-8")
    from_block = chartfile.find_chart(source_text, steps_type, difficulty)
    target_path = Path(target)
    target_text = target_path.read_text(encoding="utf-8")
    to_block = chartfile.find_chart(target_text, from_block.steps_type, difficulty)
    if len(from_block.measures) != len(to_block.measures):
        raise SimfileError(
            f"charts differ in length ({len(from_block.measures)} vs {len(to_block.measures)} measures)"
        )
    _write(target_path, chartfile.replace_measures(target_text, to_block, from_block.measures))
