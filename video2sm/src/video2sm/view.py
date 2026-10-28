"""Draw a chart and the music it follows as one picture, so it can be looked at.

Time runs downward. Left: the sung melody (further right = higher pitch, bar length = how
long the note is held). Middle: the lanes with the chart's notes. Right: kick, snare and
hi-hat hits. A thin line from each melody onset runs across the lanes, so it is easy to
see which chart note answers which sung note.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import media, review
from .features import SLOTS_PER_BEAT, SLOTS_PER_MEASURE

SLOT_HEIGHT = 14
LANE_WIDTH = 44
HEADER = 44
FOOTER = 12
GUTTER = 64
MELODY_LEFT = GUTTER
MELODY_WIDTH = 170
LANES_LEFT = MELODY_LEFT + MELODY_WIDTH + 16
DRUM_WIDTH = 120
_MAX_COLUMNS = 9
WIDTH = LANES_LEFT + LANE_WIDTH * 7 + 16 + DRUM_WIDTH + 12
DRUM_LEFT = LANES_LEFT + LANE_WIDTH * 7 + 16

_BACKGROUND = (10, 12, 18)
_LANE_TINT = {"white": (20, 24, 32), "blue": (14, 24, 52), "yellow": (40, 34, 12)}
_NOTE_COLOR = {"white": (245, 245, 250), "blue": (70, 120, 255), "yellow": (255, 224, 70)}
_O2JAM_COLORS = ("white", "blue", "white", "yellow", "white", "blue", "white")
_GRID = (36, 42, 56)
_BEAT = (60, 70, 92)
_MEASURE = (120, 140, 180)
_KICK, _SNARE, _HAT = (255, 150, 60), (255, 80, 80), (80, 220, 255)


def lane_center(lane_index: int) -> int:
    """x of the middle of a lane (0-based)."""
    return LANES_LEFT + lane_index * LANE_WIDTH + LANE_WIDTH // 2


def _lane_colors(columns: int) -> list[str]:
    return list(_O2JAM_COLORS) if columns == 7 else ["white"] * columns


def _font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size)


def _pitch_color(t: float) -> tuple[int, int, int]:
    """Low to high: violet, blue, green, yellow, orange."""
    stops = [(150, 90, 255), (70, 150, 255), (70, 220, 140), (255, 230, 80), (255, 140, 60)]
    scaled = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    i = min(int(scaled), len(stops) - 2)
    frac = scaled - i
    return tuple(int(a + (b - a) * frac) for a, b in zip(stops[i], stops[i + 1]))  # type: ignore[return-value]


def render_chart(
    ssc_path: Path, difficulty: str, start: int = 0, count: int = 8, steps_type: str | None = None
) -> Image.Image:
    loaded = review.load_chart(ssc_path, difficulty, steps_type)
    total = len(loaded.measures)
    start = min(max(start, 0), max(total - 1, 0))
    count = max(1, min(count, total - start))
    first_slot = start * SLOTS_PER_MEASURE
    last_slot = (start + count) * SLOTS_PER_MEASURE
    height = HEADER + (last_slot - first_slot) * SLOT_HEIGHT + FOOTER
    image = Image.new("RGB", (WIDTH, height), _BACKGROUND)
    draw = ImageDraw.Draw(image, "RGBA")
    columns = min(loaded.columns, _MAX_COLUMNS)
    colors = _lane_colors(columns)
    small, label = _font(10), _font(12)

    def y_of(slot: int) -> int:
        return HEADER + (slot - first_slot) * SLOT_HEIGHT

    draw.text((8, 6), f"{loaded.block.steps_type} {loaded.block.difficulty}  m{start}-m{start + count - 1}",
              fill=(235, 240, 255), font=_font(14))
    draw.text((MELODY_LEFT, 26), "melody (right = higher)", fill=(150, 160, 190), font=small)
    draw.text((LANES_LEFT, 26), "lanes", fill=(150, 160, 190), font=small)
    draw.text((DRUM_LEFT, 26), "kick  snare  hat", fill=(150, 160, 190), font=small)

    # lane backgrounds
    for lane, name in enumerate(colors):
        x = LANES_LEFT + lane * LANE_WIDTH
        draw.rectangle([x, HEADER, x + LANE_WIDTH - 1, height - FOOTER], fill=_LANE_TINT[name])
        draw.line([(x, HEADER), (x, height - FOOTER)], fill=_GRID)
    right = LANES_LEFT + columns * LANE_WIDTH
    draw.line([(right, HEADER), (right, height - FOOTER)], fill=_GRID)

    energy = (loaded.facts or {}).get("energy", [])
    tags = {sec["start"]: sec["label"] for sec in (loaded.facts or {}).get("sections", [])}

    # time grid
    for slot in range(first_slot, last_slot + 1):
        y = y_of(slot)
        if slot % SLOTS_PER_MEASURE == 0:
            draw.line([(MELODY_LEFT, y), (DRUM_LEFT + DRUM_WIDTH, y)], fill=_MEASURE)
            if slot < last_slot:
                m = slot // SLOTS_PER_MEASURE
                draw.text((8, y + 2), f"m{m}", fill=(200, 215, 255), font=label)
                if m < len(energy):  # how loud this measure is
                    draw.rectangle([4, y + 18, 4 + int(energy[m] * (GUTTER - 12)), y + 24],
                                   fill=(90, 200, 140, 255))
                if m in tags:  # where a new section starts, and which earlier ones it sounds like
                    draw.rectangle([GUTTER - 26, y + 2, GUTTER - 6, y + 16], fill=(255, 190, 60, 255))
                    draw.text((GUTTER - 20, y + 3), tags[m], fill=(20, 20, 20), font=label)
        elif slot % SLOTS_PER_BEAT == 0:
            draw.line([(MELODY_LEFT, y), (DRUM_LEFT + DRUM_WIDTH, y)], fill=_BEAT)
        else:
            draw.line([(LANES_LEFT, y), (right, y)], fill=_GRID)

    facts = loaded.facts or {}
    notes = facts.get("melody", [])
    if notes:
        pitches = np.array([n["midi"] for n in notes])
        low, high = float(np.percentile(pitches, 5)), float(np.percentile(pitches, 95))
        spread = max(high - low, 1.0)
        for note in notes:
            slot = note["slot"]
            if not first_slot <= slot < last_slot:
                continue
            t = (note["midi"] - low) / spread
            x = MELODY_LEFT + int(min(max(t, 0.0), 1.0) * (MELODY_WIDTH - 34)) + 4
            color = _pitch_color(t)
            top = y_of(slot)
            bottom = y_of(min(slot + max(note["length_slots"], 1), last_slot))
            draw.rectangle([x, top + 1, x + 9, max(bottom - 1, top + SLOT_HEIGHT - 2)], fill=color + (230,))
            draw.text((x + 12, top), note["name"], fill=color + (255,), font=small)
            draw.line([(LANES_LEFT, top), (right, top)], fill=color + (70,))

    drums = facts.get("drums", {})
    for kind, offset, color in (("kick", 18, _KICK), ("snare", 60, _SNARE), ("hat", 100, _HAT)):
        for slot in drums.get(kind, []):
            if not first_slot <= slot < last_slot:
                continue
            cx, cy = DRUM_LEFT + offset, y_of(slot) + SLOT_HEIGHT // 2
            if kind == "kick":
                draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=color + (255,))
            elif kind == "snare":
                draw.rectangle([cx - 5, cy - 5, cx + 5, cy + 5], fill=color + (255,))
            else:
                draw.line([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=color + (255,), width=2)
                draw.line([(cx - 4, cy + 4), (cx + 4, cy - 4)], fill=color + (255,), width=2)

    # the chart: holds first so their heads and tails are drawn over them
    open_holds: dict[int, int] = {}
    pending: list[tuple[int, int, int]] = []  # (lane, start slot, end slot)
    taps: list[tuple[int, int, bool]] = []
    for m, slots in enumerate(loaded.measures):
        for s, cells in sorted(slots.items()):
            slot = m * SLOTS_PER_MEASURE + s
            for lane, ch in cells.items():
                if ch == "2":
                    open_holds[lane] = slot
                elif ch == "3" and lane in open_holds:
                    pending.append((lane, open_holds.pop(lane), slot))
                elif ch == "1":
                    taps.append((lane, slot, False))
    for lane, begin in open_holds.items():
        pending.append((lane, begin, last_slot))
    for lane, begin, end in pending:
        if end < first_slot or begin >= last_slot or lane >= columns:
            continue
        color = _NOTE_COLOR[colors[lane]]
        x = LANES_LEFT + lane * LANE_WIDTH + 8
        draw.rectangle([x + 6, y_of(max(begin, first_slot)) + SLOT_HEIGHT // 2,
                        x + LANE_WIDTH - 22, y_of(min(end, last_slot)) + SLOT_HEIGHT // 2],
                       fill=color + (150,))
        taps.append((lane, begin, True))
        taps.append((lane, end, True))
    for lane, slot, _ in taps:
        if not first_slot <= slot < last_slot or lane >= columns:
            continue
        x = LANES_LEFT + lane * LANE_WIDTH + 4
        top = y_of(slot) + 1
        color = _NOTE_COLOR[colors[lane]]
        draw.rounded_rectangle([x, top, x + LANE_WIDTH - 9, top + SLOT_HEIGHT - 3], radius=3,
                               fill=color + (255,), outline=(0, 0, 0, 160))
    return image


def save_chart_view(
    ssc_path: Path, difficulty: str, start: int, count: int, out: Path, steps_type: str | None = None
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render_chart(ssc_path, difficulty, start, count, steps_type).save(out)
    return out


def contact_sheet(
    video: Path,
    times: Sequence[float] | None,
    count: int = 8,
    columns: int = 4,
    tile_width: int = 320,
) -> Image.Image:
    """Frames of the video at the given times (default: evenly spaced), each labelled with its time."""
    info = media.probe(video)
    if not info.has_video:
        raise ValueError(f"{info.path.name} has no video stream to look at")
    if times is None:
        times = [info.duration * (i + 0.5) / count for i in range(count)]
    times = [min(max(float(t), 0.0), max(info.duration - 0.1, 0.0)) for t in times]
    tile_height = max(int(tile_width * (info.height / info.width)) if info.width else tile_width * 9 // 16, 1)
    strip = 18
    rows = -(-len(times) // columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * (tile_height + strip)), (12, 14, 20))
    draw = ImageDraw.Draw(sheet)
    with tempfile.TemporaryDirectory() as tmp:
        for index, moment in enumerate(times):
            frame = media.extract_frame(info.path, Path(tmp) / f"f{index}.png", moment, tile_width, tile_height)
            x, y = (index % columns) * tile_width, (index // columns) * (tile_height + strip)
            sheet.paste(Image.open(frame).convert("RGB"), (x, y + strip))
            minutes, seconds = divmod(moment, 60)
            draw.text((x + 6, y + 2), f"{int(minutes)}:{seconds:04.1f}", fill=(220, 230, 255), font=_font(12))
    return sheet
