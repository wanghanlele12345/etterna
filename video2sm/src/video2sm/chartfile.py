"""Find a chart inside an `.ssc` written by video2sm and read or replace its measures.

Works on the text directly, so everything else in the file (timing, tags, other charts) is
left byte for byte as it was.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import SimfileError

_NOTEDATA = re.compile(r"#NOTEDATA:;")
_NOTES = re.compile(r"#NOTES:\n(.*?)\n;", re.DOTALL)
_MEASURE_BREAK = "\n,\n"


@dataclass(frozen=True)
class ChartBlock:
    steps_type: str
    difficulty: str
    meter: int
    body_start: int  # where the measure rows begin in the file text
    body_end: int
    measures: tuple[tuple[str, ...], ...]  # the rows of each measure


def _tag(chunk: str, name: str) -> str:
    match = re.search(rf"#{name}:([^;]*);", chunk)
    return match.group(1).strip() if match else ""


def _blocks(text: str) -> list[ChartBlock]:
    starts = [m.start() for m in _NOTEDATA.finditer(text)]
    found = []
    for begin, end in zip(starts, starts[1:] + [len(text)]):
        chunk = text[begin:end]
        notes = _NOTES.search(chunk)
        if notes is None:
            continue
        measures = tuple(
            tuple(line.strip() for line in measure.split("\n") if line.strip())
            for measure in notes.group(1).split(_MEASURE_BREAK)
        )
        meter = _tag(chunk, "METER")
        found.append(
            ChartBlock(
                steps_type=_tag(chunk, "STEPSTYPE"),
                difficulty=_tag(chunk, "DIFFICULTY"),
                meter=int(meter) if meter.isdigit() else 0,
                body_start=begin + notes.start(1),
                body_end=begin + notes.end(1),
                measures=measures,
            )
        )
    return found


def list_charts(text: str) -> list[tuple[str, str]]:
    """(steps type, difficulty) of every chart in the file."""
    return [(b.steps_type, b.difficulty) for b in _blocks(text)]


def find_chart(text: str, steps_type: str | None, difficulty: str) -> ChartBlock:
    """The chart with this difficulty (and steps type, when given)."""
    wanted = difficulty.strip().lower()
    matches = [
        b for b in _blocks(text)
        if b.difficulty.lower() == wanted and (steps_type is None or b.steps_type == steps_type)
    ]
    if not matches:
        available = ", ".join(f"{s} {d}" for s, d in list_charts(text)) or "none"
        raise SimfileError(f"no {steps_type or 'any'} chart named {difficulty}; the file has: {available}")
    if len(matches) > 1:
        kinds = ", ".join(b.steps_type for b in matches)
        raise SimfileError(f"{difficulty} exists for several key modes ({kinds}); say which one")
    return matches[0]


def replace_measures(
    text: str, block: ChartBlock, measures: tuple[tuple[str, ...], ...]
) -> str:
    body = _MEASURE_BREAK.join("\n".join(rows) for rows in measures)
    return text[: block.body_start] + body + text[block.body_end :]
