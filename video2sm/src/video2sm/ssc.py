"""Render, validate and nudge StepMania 5 / Etterna `.ssc` files."""

from __future__ import annotations

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

with warnings.catch_warnings():
    warnings.simplefilter("ignore", UserWarning)  # simfile -> pkg_resources
    import simfile
    from simfile.notes import NoteData, NoteType
    from simfile.timing import Beat, TimingData
    from simfile.timing.engine import TimingEngine

from .beats import BeatAnalysis
from .charting import Chart
from .errors import SimfileError
from .layouts import layout_for_steps_type

SSC_VERSION = "0.83"
_OFFSET_LINE = re.compile(r"^(#OFFSET:)([^;]*)(;)", re.MULTILINE)


@dataclass(frozen=True)
class SongMeta:
    title: str
    artist: str
    music: str
    banner: str = ""
    background: str = ""
    video: str = ""
    credit: str = "video2sm"


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    problems: tuple[str, ...]
    chart_names: tuple[str, ...] = ()


def _escape(value: str) -> str:
    cleaned = " ".join(value.split())
    return cleaned.replace("\\", "\\\\").replace(":", "\\:").replace(";", "\\;")


def _tag(name: str, value: str) -> str:
    return f"#{name}:{value};"


def _bg_changes(video: str) -> str:
    return (
        f"#BGCHANGES:0.000={_escape(video)}=1.000=0=0=1=====,\n"
        "99999=-nosongbg-=1.000=0=0=0;"
    )


def _render_chart(chart: Chart, credit: str) -> str:
    body = "\n,\n".join("\n".join(measure) for measure in chart.measures)
    return "\n".join(
        [
            "#NOTEDATA:;",
            _tag("STEPSTYPE", chart.steps_type),
            _tag("DESCRIPTION", _escape(chart.name)),
            _tag("DIFFICULTY", chart.name),
            _tag("METER", str(chart.meter)),
            _tag("CREDIT", _escape(credit)),
            f"#NOTES:\n{body}\n;",
        ]
    )


def render_ssc(
    meta: SongMeta,
    analysis: BeatAnalysis,
    preview: tuple[float, float],
    charts: tuple[Chart, ...],
) -> str:
    sample_start, sample_length = preview
    header = [
        _tag("VERSION", SSC_VERSION),
        _tag("TITLE", _escape(meta.title)),
        _tag("SUBTITLE", ""),
        _tag("ARTIST", _escape(meta.artist)),
        _tag("CREDIT", _escape(meta.credit)),
        _tag("BANNER", _escape(meta.banner)),
        _tag("BACKGROUND", _escape(meta.background)),
        _tag("MUSIC", _escape(meta.music)),
        _tag("OFFSET", f"{analysis.offset:.6f}"),
        _tag("SAMPLESTART", f"{sample_start:.3f}"),
        _tag("SAMPLELENGTH", f"{sample_length:.3f}"),
        _tag("SELECTABLE", "YES"),
        _tag("BPMS", f"0.000={analysis.bpm:.3f}"),
        _tag("STOPS", ""),
    ]
    if meta.video:
        header.append(_bg_changes(meta.video))
    blocks = ["\n".join(header)] + [_render_chart(c, meta.credit) for c in charts]
    return "\n\n".join(blocks) + "\n"


def _required_assets(sim: simfile.types.Simfile) -> list[str]:
    names = [sim.music, sim.banner, sim.background]
    bgchanges = getattr(sim, "bgchanges", "") or ""
    first = bgchanges.split(",")[0].split("=")
    if len(first) > 1 and first[1]:
        names.append(first[1])
    return [n for n in names if n]


_HOLD_HEADS = (NoteType.HOLD_HEAD, NoteType.ROLL_HEAD)


def _hold_problems(notes: list, label: str) -> list[str]:
    """Heads must be released before the column is used again, and every head released."""
    open_columns: set[int] = set()
    for note in sorted(notes, key=lambda n: (n.beat, n.note_type != NoteType.TAIL)):
        if note.note_type in _HOLD_HEADS:
            if note.column in open_columns:
                return [f"chart {label} starts a hold in column {note.column} that is still held"]
            open_columns.add(note.column)
        elif note.note_type == NoteType.TAIL:
            if note.column not in open_columns:
                return [f"chart {label} releases column {note.column} that is not held"]
            open_columns.discard(note.column)
        elif note.column in open_columns:
            return [f"chart {label} has a note in column {note.column} during a hold"]
    if open_columns:
        return [f"chart {label} has a hold that is never released"]
    return []


def _chart_problems(chart) -> list[str]:
    label = f"{chart.stepstype} {chart.difficulty}"
    try:
        data = NoteData(chart)
        notes = list(data)
    except Exception as exc:
        return [f"chart {label} unreadable: {exc}"]
    if not notes:
        return [f"chart {label} has no notes"]
    layout = layout_for_steps_type(chart.stepstype)
    if layout is not None and data.columns != layout.columns:
        return [f"chart {label} has {data.columns} columns, expected {layout.columns}"]
    return _hold_problems(notes, label)


def validate_ssc(path: Path) -> ValidationReport:
    """Parse the file and check timing, charts and referenced assets."""
    path = Path(path)
    problems: list[str] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            sim = simfile.open(str(path))
    except Exception as exc:
        return ValidationReport(False, (f"cannot parse {path.name}: {exc}",))

    if not sim.charts:
        problems.append("simfile has no charts")
    if not sim.music:
        problems.append("no #MUSIC set")
    try:
        engine = TimingEngine(TimingData(sim))
        if engine.time_at(Beat(4)) <= engine.time_at(Beat(0)):
            problems.append("timing is not increasing; check #BPMS")
    except Exception as exc:
        problems.append(f"invalid timing data: {exc}")

    for chart in sim.charts:
        problems.extend(_chart_problems(chart))

    for name in _required_assets(sim):
        if not (path.parent / name).is_file():
            problems.append(f"missing file referenced by simfile: {name}")
    return ValidationReport(
        ok=not problems,
        problems=tuple(problems),
        chart_names=tuple(str(c.difficulty) for c in sim.charts),
    )


def adjust_offset(path: Path, delta_ms: float) -> float:
    """Shift #OFFSET by delta_ms (negative = notes come earlier); returns the new value.

    Sync fixes are the one thing the game can't do for you, so this edits the
    value in place without re-rendering (and re-formatting) the rest of the file.
    """
    path = Path(path)
    if not path.is_file():
        raise SimfileError(f"simfile not found: {path}")
    text = path.read_text(encoding="utf-8")
    match = _OFFSET_LINE.search(text)
    if match is None:
        raise SimfileError(f"no #OFFSET tag in {path.name}")
    new_offset = round(float(match.group(2)) + delta_ms / 1000.0, 6)
    updated = _OFFSET_LINE.sub(rf"\g<1>{new_offset:.6f}\g<3>", text, count=1)
    path.write_text(updated, encoding="utf-8")
    return new_offset
