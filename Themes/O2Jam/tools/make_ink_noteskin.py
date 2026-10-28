"""Vinyl-record textures for the 'ink' kb7 noteskin (cells are 64px; the player is drawn at
zoom 0.75 so a cell is one 48px lane). Drawn at 4x and shrunk for smooth, hand-inked edges.

    python3 -I tools/make_ink_noteskin.py <noteskin dir>
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

SKIN = Path(sys.argv[1])
SS = 4
INK = (29, 20, 36)
VINYL = (45, 36, 62)
GROOVE = (70, 58, 92)
CREAM = (244, 234, 210)
LABELS = {
    "White": ((95, 180, 201), (62, 135, 156)),
    "Blue": ((232, 117, 138), (183, 80, 102)),
    "Yellow": ((240, 184, 64), (196, 140, 34)),
}


def canvas(w=64, h=64):
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def done(img, w, h):
    return img.resize((w, h), Image.LANCZOS)


def circle(d, cx, cy, r, fill=None, outline=None, width=1):
    d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS],
              fill=None if fill is None else fill + (255,),
              outline=None if outline is None else outline + (255,), width=int(width * SS))


def disc(frame, label, dim=False):
    img, d = canvas()
    shade = (lambda c: tuple(int(v * 0.5) for v in c)) if dim else (lambda c: c)
    circle(d, 32 + 1.2, 32 + 1.8, 28, fill=INK)  # hard drop shadow, same ink
    circle(d, 32, 32, 28, fill=shade(VINYL), outline=INK, width=3.2)
    for r in (23, 19, 15):
        circle(d, 32, 32, r, outline=shade(GROOVE), width=0.8)
    base, dark = label
    circle(d, 32, 32, 11, fill=shade(base), outline=INK, width=2.4)
    circle(d, 32, 32, 3.2, fill=CREAM if not dim else shade(CREAM), outline=INK, width=1.4)
    # a spinning glint on the vinyl and a notch on the label, so the record turns across frames
    a0 = math.radians(-60 + frame * 90)
    for off, wd in ((0, 3.2), (math.radians(180), 2.0)):
        pts = [(32 + 21 * math.cos(a0 + off + t * 0.38), 32 + 21 * math.sin(a0 + off + t * 0.38)) for t in range(-3, 4)]
        d.line([(x * SS, y * SS) for x, y in pts], fill=shade((200, 190, 225)) + (255,), width=int(wd * SS), joint="curve")
    nx, ny = 32 + 7 * math.cos(a0 * 2), 32 + 7 * math.sin(a0 * 2)
    circle(d, nx, ny, 1.5, fill=shade(dark))
    return done(img, 64, 64)


def sheet_tap(name, label):
    out = Image.new("RGBA", (4 * 64, 2 * 64), (0, 0, 0, 0))
    for row in range(2):
        for frame in range(4):
            out.alpha_composite(disc(frame, label), (frame * 64, row * 64))
    out.save(SKIN / name)


def ribbon(label, active, kind):
    """Hold ribbon: a flat colour band between two ink lines, with a dash pattern."""
    img, d = canvas(64, 64)
    base, dark = label
    if not active:
        base, dark = (tuple(int(v * 0.45) for v in c) for c in (base, dark))
    x0, x1 = 18, 46
    if kind == "body":
        d.rectangle([x0 * SS, 0, x1 * SS, 64 * SS], fill=base + (255,))
        d.rectangle([x0 * SS, 0, (x0 + 4) * SS, 64 * SS], fill=dark + (255,))
        for y in range(4, 64, 16):
            d.rounded_rectangle([(x0 + 10) * SS, y * SS, (x1 - 8) * SS, (y + 7) * SS], radius=2 * SS,
                                fill=(CREAM if active else dark) + (255,))
        d.line([(x0 * SS, 0), (x0 * SS, 64 * SS)], fill=INK + (255,), width=3 * SS)
        d.line([(x1 * SS, 0), (x1 * SS, 64 * SS)], fill=INK + (255,), width=3 * SS)
    elif kind == "top":
        img, d = canvas(64, 8)
        d.rectangle([x0 * SS, 0, x1 * SS, 8 * SS], fill=base + (255,))
        d.line([(x0 * SS, 0), (x0 * SS, 8 * SS)], fill=INK + (255,), width=3 * SS)
        d.line([(x1 * SS, 0), (x1 * SS, 8 * SS)], fill=INK + (255,), width=3 * SS)
        d.line([(x0 * SS, 1.5 * SS), (x1 * SS, 1.5 * SS)], fill=INK + (255,), width=3 * SS)
        return done(img, 64, 8)
    else:  # bottom cap: a rounded end
        d.rectangle([x0 * SS, 0, x1 * SS, 30 * SS], fill=base + (255,))
        d.pieslice([x0 * SS, 12 * SS, x1 * SS, 48 * SS], 0, 180, fill=base + (255,))
        d.line([(x0 * SS, 0), (x0 * SS, 30 * SS)], fill=INK + (255,), width=3 * SS)
        d.line([(x1 * SS, 0), (x1 * SS, 30 * SS)], fill=INK + (255,), width=3 * SS)
        d.arc([x0 * SS, 12 * SS, x1 * SS, 48 * SS], 0, 180, fill=INK + (255,), width=3 * SS)
    return done(img, 64, 64)


def receptor(label):
    """The record slot: an inked ring in the lane colour with a spindle dot."""
    img, d = canvas()
    base, dark = label
    circle(d, 32, 32, 27, fill=(40, 31, 58), outline=INK, width=3.2)
    circle(d, 32, 32, 22, outline=base, width=2.4)
    circle(d, 32, 32, 9, outline=dark, width=1.6)
    circle(d, 32, 32, 2.6, fill=base, outline=INK, width=1.2)
    return done(img, 64, 64)


def flash():
    img, d = canvas(128, 128)
    for r, a in ((60, 70), (48, 120), (36, 190)):
        d.ellipse([(64 - r) * SS, (64 - r) * SS, (64 + r) * SS, (64 + r) * SS], fill=(255, 255, 255, a))
    return done(img, 128, 128)


def burst(size=128, spikes=10):
    img, d = canvas(size, size)
    cx = size / 2
    pts = []
    for i in range(spikes * 2):
        ang = math.pi * i / spikes
        r = size * (0.47 if i % 2 == 0 else 0.3)
        pts.append(((cx + r * math.cos(ang)) * SS, (cx + r * math.sin(ang)) * SS))
    d.polygon(pts, fill=(255, 255, 255, 255))
    d.line(pts + [pts[0]], fill=INK + (255,), width=3 * SS, joint="curve")
    return done(img, size, size)


for lane, label in LABELS.items():
    sheet_tap(f"_{lane} tap note 4x2.png", label)
    disc(0, label).save(SKIN / f"{lane} tap fake.png")
    for state, active in (("active", True), ("inactive", False)):
        ribbon(label, active, "body").save(SKIN / f"{lane} Hold Body {state}.png")
        ribbon(label, active, "top").save(SKIN / f"{lane} Hold TopCap {state}.png")
        ribbon(label, active, "bottom").save(SKIN / f"{lane} Hold BottomCap {state}.png")
    receptor(label).save(SKIN / f"_bar receptor base {lane.lower()}.png")
flash().save(SKIN / "_bar receptor tap.png")
burst().save(SKIN / "_Tap explosion bright.png")
flash().save(SKIN / "_bar hold explosion bright.png")
flash().save(SKIN / "_bar hold explosion dim.png")
print("ink noteskin textures written to", SKIN)
