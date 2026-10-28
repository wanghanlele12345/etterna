"""Hand-inked cartoon textures for the O2Jam theme (a "record shop" look: warm muted flats,
thick near-black ink outlines, hard drop shadows, paper grain).

Shapes are drawn at 4x and shrunk for smooth edges, with a little low-frequency wobble on the
outlines so nothing looks ruler-straight. Deterministic (seeded). Run with python3 -I:

    python3 -I tools/make_ink_assets.py <theme dir>
"""

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SS = 4
OUT = Path(sys.argv[1]) / "Graphics" / "ink"
OUT.mkdir(parents=True, exist_ok=True)

INK = (29, 20, 36)
CREAM = (244, 234, 210)
WHITE = (255, 255, 255)
PLUM0 = (40, 31, 58)
PLUM1 = (58, 45, 82)
PLUM2 = (80, 63, 108)
MAUVE = (106, 86, 138)
WOOD = (168, 115, 74)
WOOD_D = (122, 80, 52)
MUSTARD = (240, 184, 64)
CORAL = (232, 117, 138)
TEAL = (95, 180, 201)
MINT = (143, 209, 158)
ORANGE = (239, 138, 75)
RED = (217, 84, 77)
LAV = (167, 154, 214)


def mix(a, b, t):
    return tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


class Art:
    def __init__(self, w, h, seed=1):
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.rng = random.Random(seed)

    def pts(self, points):
        return [(x * SS, y * SS) for x, y in points]

    def poly(self, points, fill=None, outline=INK, width=4):
        p = self.pts(points)
        if fill is not None:
            self.d.polygon(p, fill=fill + (255,) if len(fill) == 3 else fill)
        if outline is not None:
            self.d.line(p + [p[0]], fill=outline + (255,), width=int(width * SS), joint="curve")
            for x, y in p:  # round the joints
                r = width * SS / 2
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=outline + (255,))

    def shadow(self, points, dx=5, dy=6, color=INK, alpha=90):
        shifted = [(x + dx, y + dy) for x, y in points]
        layer = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
        ImageDraw.Draw(layer).polygon(self.pts(shifted), fill=color + (alpha,))
        self.img.alpha_composite(layer)
        self.d = ImageDraw.Draw(self.img)

    def wobble_rect(self, x0, y0, x1, y1, r, wob=1.6, step=3):
        """Rounded-rectangle outline sampled densely, each point nudged by smooth noise."""
        path = []
        corners = [(x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)]
        for cx, cy, start in corners:
            for i in range(0, 91, 6):
                a = math.radians(start + i)
                path.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        # resample along the perimeter
        dense = []
        for (ax, ay), (bx, by) in zip(path, path[1:] + path[:1]):
            n = max(int(math.hypot(bx - ax, by - ay) / step), 1)
            for k in range(n):
                dense.append((ax + (bx - ax) * k / n, ay + (by - ay) * k / n))
        phases = [self.rng.random() * 6.28 for _ in range(3)]
        out = []
        count = len(dense)
        for i, (x, y) in enumerate(dense):
            t = i / count * 6.28
            nx, ny = dense[(i + 1) % count][1] - dense[i - 1][1], -(dense[(i + 1) % count][0] - dense[i - 1][0])
            ln = math.hypot(nx, ny) or 1
            off = wob * (0.55 * math.sin(t * 7 + phases[0]) + 0.3 * math.sin(t * 13 + phases[1]) + 0.15 * math.sin(t * 29 + phases[2]))
            out.append((x + nx / ln * off, y + ny / ln * off))
        return out

    def finish(self, name):
        small = self.img.resize((self.w, self.h), Image.LANCZOS)
        small.save(OUT / name)
        print("wrote", name, small.size)


def card(name, w, h, fill, r=16, border=4, shadow=True, seed=1, glint=True):
    a = Art(w, h, seed)
    body = a.wobble_rect(border + 2, border + 1, w - border - 8, h - border - 9, r)
    if shadow:
        a.shadow(body, 6, 7)
    a.poly(body, fill=fill, outline=INK, width=border)
    if glint:  # a lighter inner stroke, like the dialogue boxes
        inner = a.wobble_rect(border + 8, border + 7, w - border - 14, h - border - 15, max(r - 6, 4), wob=1.0)
        a.poly(inner, fill=None, outline=mix(fill, CREAM, 0.28), width=2)
    a.finish(name)


def bottom_bar(name, w=960, h=96):
    a = Art(w, h, 11)
    top = []
    for x in range(0, w + 1, 6):
        top.append((x, 12 + 3.5 * math.sin(x / 31) + 2 * math.sin(x / 11 + 1.3)))
    body = top + [(w, h), (0, h)]
    a.poly(body, fill=PLUM1, outline=None)
    a.poly(top, fill=None, outline=INK, width=5)
    band = [(x, y + 8) for x, y in top]
    a.poly(band, fill=None, outline=mix(PLUM1, CREAM, 0.22), width=2)
    a.finish(name)


def video_frame(name, w=504, h=294):
    """A wooden picture frame around a transparent window (the video)."""
    a = Art(w, h, 21)
    outer = a.wobble_rect(4, 3, w - 9, h - 10, 18, wob=1.4)
    a.shadow(outer, 6, 7)
    a.poly(outer, fill=WOOD, outline=INK, width=5)
    # clear the window, then outline it
    win = [(x, y) for x, y in a.wobble_rect(12, 12, w - 17, h - 18, 8, wob=0.8)]
    layer = Image.new("RGBA", a.img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).polygon(a.pts(win), fill=(255, 255, 255, 255))
    mask = layer.split()[3]
    a.img.paste((0, 0, 0, 0), (0, 0), mask)
    a.d = ImageDraw.Draw(a.img)
    a.poly(win, fill=None, outline=INK, width=4)
    inner = a.wobble_rect(6, 6, w - 11, h - 12, 14, wob=1.0)
    a.poly(inner, fill=None, outline=mix(WOOD, CREAM, 0.35), width=2)
    for cx, cy in ((11, 11), (w - 12, 11), (11, h - 13), (w - 12, h - 13)):  # screws
        a.d.ellipse([(cx - 3.2) * SS, (cy - 3.2) * SS, (cx + 3.2) * SS, (cy + 3.2) * SS], fill=WOOD_D + (255,), outline=INK + (255,), width=2 * SS // 2)
    a.finish(name)


def strip(name, w=24, h=720):
    """Vertical divider: a dark band with cream dashes, like film perforations."""
    a = Art(w, h, 31)
    a.d.rectangle([0, 0, w * SS, h * SS], fill=PLUM0 + (255,))
    a.d.rectangle([2 * SS, 0, 5 * SS, h * SS], fill=INK + (255,))
    a.d.rectangle([w * SS - 5 * SS, 0, (w - 2) * SS, h * SS], fill=INK + (255,))
    for y in range(6, h, 22):
        r = [(7 + 1, y), (w - 8, y), (w - 8, y + 12), (8, y + 12)]
        a.poly(r, fill=mix(MUSTARD, PLUM0, 0.15 if (y // 22) % 2 else 0.45), outline=INK, width=2)
    a.finish(name)


def record_icon(name, lit):
    a = Art(30, 30, 41)
    c = 15
    rim = INK
    a.d.ellipse([2 * SS, 2 * SS, 28 * SS, 28 * SS], fill=(PLUM0 if not lit else (47, 38, 60)) + (255,), outline=rim + (255,), width=3 * SS)
    for r in (11, 8):
        a.d.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], outline=mix(PLUM1, CREAM, 0.18 if lit else 0.0) + (255,), width=SS // 2)
    label = MUSTARD if lit else mix(MUSTARD, PLUM0, 0.7)
    a.d.ellipse([(c - 6) * SS, (c - 6) * SS, (c + 6) * SS, (c + 6) * SS], fill=label + (255,), outline=INK + (255,), width=2 * SS)
    a.d.ellipse([(c - 1.4) * SS, (c - 1.4) * SS, (c + 1.4) * SS, (c + 1.4) * SS], fill=CREAM + (255,) if lit else PLUM0 + (255,))
    a.finish(name)


def tube(name_back="energy_back.png", name_fill="energy_fill.png", h=336):
    a = Art(24, h, 51)
    body = a.wobble_rect(3, 3, 19, h - 6, 9, wob=0.8)
    a.shadow(body, 3, 4)
    a.poly(body, fill=PLUM0, outline=INK, width=4)
    a.finish(name_back)
    f = Art(18, h - 12, 52)
    height = (h - 12) * SS
    bands = [(0.0, MINT), (0.45, MUSTARD), (0.75, CORAL)]
    for y in range(height):
        t = y / height
        color = bands[0][1]
        for pos, col in bands:
            if t >= pos:
                color = col
        f.d.line([(0, y), (18 * SS, y)], fill=color + (255,))
    for y in range(0, h - 12, 12):  # graduation marks
        f.d.line([(0, y * SS), (6 * SS, y * SS)], fill=INK + (110,), width=SS)
    f.finish(name_fill)


def bars():
    a = Art(336, 18, 61)
    body = a.wobble_rect(2, 2, 333, 15, 7, wob=0.6, step=4)
    a.poly(body, fill=PLUM0, outline=INK, width=3)
    a.finish("progress_back.png")
    f = Art(336, 18, 62)
    f.d.rounded_rectangle([3 * SS, 3 * SS, 332 * SS, 14 * SS], radius=5 * SS, fill=MUSTARD + (255,))
    for x in range(10, 330, 14):
        f.d.line([(x * SS, 3 * SS), ((x - 5) * SS, 14 * SS)], fill=mix(MUSTARD, CREAM, 0.45) + (255,), width=3 * SS)
    f.finish("progress_fill.png")
    s = Art(210, 15, 63)
    body = s.wobble_rect(2, 2, 207, 12, 5, wob=0.5, step=4)
    s.poly(body, fill=PLUM0, outline=INK, width=3)
    s.finish("stat_back.png")
    s2 = Art(210, 15, 64)
    s2.d.rounded_rectangle([3 * SS, 3 * SS, 206 * SS, 11 * SS], radius=4 * SS, fill=WHITE + (255,))
    s2.finish("stat_fill.png")


def badge_pill(name="badge.png", w=132, h=42):
    a = Art(w, h, 71)
    body = a.wobble_rect(3, 3, w - 6, h - 8, 17, wob=0.9)
    a.shadow(body, 3, 4)
    a.poly(body, fill=WHITE, outline=INK, width=4)
    a.finish(name)


def grade_badge(name="grade_ring.png", size=90):
    a = Art(size, size, 81)
    c = size / 2
    points = []
    spikes = 14
    for i in range(spikes * 2):
        ang = math.pi * i / spikes + a.rng.uniform(-0.04, 0.04)
        r = (size * 0.46) if i % 2 == 0 else (size * 0.36)
        points.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    a.shadow(points, 3, 4)
    a.poly(points, fill=PLUM2, outline=INK, width=4)
    a.d.ellipse([(c - 27) * SS, (c - 27) * SS, (c + 27) * SS, (c + 27) * SS], fill=PLUM0 + (255,), outline=INK + (255,), width=3 * SS)
    a.finish(name)


def lane(name, tint, w=48, h=621):
    img = Image.new("RGBA", (w, h))
    px = img.load()
    rng = random.Random(91)
    for y in range(h):
        t = y / h
        base = mix(mix(PLUM0, tint, 0.05), mix(PLUM1, tint, 0.14), t)
        for x in range(w):
            n = rng.randint(-4, 4)
            px[x, y] = (base[0] + n, base[1] + n, base[2] + n, 255)
    img.save(OUT / name)
    print("wrote", name, img.size)


def beam(name="beam.png", w=48, h=360):
    """A halftone column of dots: full and bright at the bottom, shrinking and fading to nothing
    at the top, so the tail dissolves instead of ending in a hard edge."""
    a = Art(w, h, 101)
    step = 8
    rows = h // step
    for row in range(rows):
        u = row / rows  # 0 at the top of the column, 1 at the bottom
        r = 3.8 * u ** 1.6
        alpha = int(255 * u ** 1.2)
        if r < 0.5 or alpha < 8:
            continue
        for col in range(0, w // step + 1):
            ox = step / 2 if row % 2 else 0
            x = col * step + ox
            if x < w + 2:
                y = row * step + step / 2
                a.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=WHITE + (alpha,))
    a.finish(name)


def burst(name="burst.png", size=192, spikes=11, seed=111, fill=WHITE):
    """A comic explosion: spiky star, white fill so it can be tinted, inked outline."""
    a = Art(size, size, seed)
    c = size / 2
    pts = []
    for i in range(spikes * 2):
        ang = math.pi * i / spikes + a.rng.uniform(-0.05, 0.05)
        r = size * (0.47 if i % 2 == 0 else 0.3) * a.rng.uniform(0.92, 1.05)
        pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    a.shadow(pts, 4, 5, alpha=70)
    a.poly(pts, fill=fill, outline=INK, width=max(4, size // 40))
    a.finish(name)


def star(name="star.png", size=48):
    a = Art(size, size, 121)
    c = size / 2
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + math.pi * i / 5
        r = size * (0.44 if i % 2 == 0 else 0.2)
        pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))
    a.poly(pts, fill=WHITE, outline=INK, width=3)
    a.finish(name)


def dot(name="dot.png", size=24):
    a = Art(size, size, 131)
    a.d.ellipse([3 * SS, 3 * SS, (size - 3) * SS, (size - 3) * SS], fill=WHITE + (255,), outline=INK + (255,), width=3 * SS)
    a.finish(name)


def ring(name="ring.png", size=96):
    """A hand-inked ring: white band between two ink lines (tintable)."""
    a = Art(size, size, 135)
    c = size / 2
    for r, col, w in ((c - 6, INK, 12), (c - 6, WHITE, 6)):
        a.d.ellipse([(c - r) * SS, (c - r) * SS, (c + r) * SS, (c + r) * SS], outline=col + (255,), width=int(w * SS))
    a.finish(name)


def sleeve(back="sleeve_back.png", frame="sleeve_frame.png", w=288, h=300):
    """A record sleeve: cream card with an art window (drawn separately) and a bottom strip."""
    a = Art(w, h, 181)
    body = a.wobble_rect(6, 5, w - 10, h - 11, 14, wob=1.8)
    a.shadow(body, 7, 8)
    a.poly(body, fill=CREAM, outline=INK, width=5)
    a.finish(back)
    f = Art(w, h, 182)
    win = a.wobble_rect(24, 24, 264, 264, 4, wob=0.9)
    f.poly(win, fill=None, outline=INK, width=4)
    for i, x in enumerate(range(48, 241, 48)):  # little notches in the bottom strip, like a barcode of dots
        f.d.ellipse([(x - 3) * SS, (279 + 3) * SS, (x + 3) * SS, (279 + 9) * SS], fill=mix(CREAM, PLUM2, 0.55) + (255,))
    f.finish(frame)





def chip_pill(name="diff_chip.png", w=190, h=46):
    a = Art(w, h, 211)
    body = a.wobble_rect(4, 4, w - 6, h - 9, 18, wob=0.9)
    a.shadow(body, 3, 4)
    a.poly(body, fill=WHITE, outline=INK, width=4)
    a.finish(name)


BRICK = (112, 76, 72)
FLOOR = (111, 103, 148)
TRAY = (176, 168, 220)
TRAY_D = (143, 134, 196)


def wall(name="wall.png", w=960, h=720, horizon=452):
    """Select screen room: a brick wall over a flat purple floor, split by an inked skirting line."""
    a = Art(w, h, 301)
    rng = a.rng
    a.d.rectangle([0, 0, w * SS, h * SS], fill=FLOOR + (255,))
    bw, bh = 72, 34
    for row in range(0, horizon // bh + 2):
        y = row * bh
        for col in range(-1, w // bw + 2):
            x = col * bw + (bw / 2 if row % 2 else 0)
            tone = rng.uniform(-9, 9)
            fill = tuple(int(max(0, min(255, v + tone))) for v in BRICK)
            a.d.rectangle([(x + 1) * SS, (y + 1) * SS, (x + bw - 1) * SS, (y + bh - 1) * SS], fill=fill + (255,))
    for row in range(0, horizon // bh + 2):  # mortar, drawn as slightly shaky ink lines
        y = row * bh
        a.d.line([(0, y * SS), (w * SS, y * SS)], fill=INK + (255,), width=3 * SS)
        for col in range(-1, w // bw + 2):
            x = col * bw + (bw / 2 if row % 2 else 0)
            a.d.line([(x * SS, y * SS), (x * SS, (y + bh) * SS)], fill=INK + (255,), width=3 * SS)
    a.d.rectangle([0, horizon * SS, w * SS, h * SS], fill=FLOOR + (255,))
    base = [(x, horizon + 3 * math.sin(x / 37) + 2 * math.sin(x / 11)) for x in range(0, w + 1, 6)]
    a.poly(base, fill=None, outline=INK, width=7)
    strip = [(x, y + 11) for x, y in base]
    a.poly(strip, fill=None, outline=mix(FLOOR, CREAM, 0.18), width=2)
    for _ in range(260):  # floor speckle
        x, y = rng.uniform(0, w), rng.uniform(horizon + 18, h)
        r = rng.uniform(1.2, 3.2)
        a.d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS], fill=mix(FLOOR, INK, 0.12) + (255,))
    a.finish(name)


def tray(name="tray.png", w=560, h=210):
    """The front of the record crate: a lavender board with an inked lip and a short side wall."""
    a = Art(w, h, 311)
    side = [(500, 70), (556, 30), (556, 150), (500, 196)]
    a.shadow(side, 5, 6)
    a.poly(side, fill=TRAY_D, outline=INK, width=5)
    body = a.wobble_rect(8, 62, 502, 196, 14, wob=1.5)
    a.shadow(body, 6, 7)
    a.poly(body, fill=TRAY, outline=INK, width=5)
    lip = a.wobble_rect(18, 70, 492, 92, 6, wob=1.0)
    a.poly(lip, fill=mix(TRAY, CREAM, 0.4), outline=None)
    a.finish(name)


def tag(name="tag.png", w=170, h=46):
    """The little label that sticks up from the back of the stack."""
    a = Art(w, h, 321)
    body = a.wobble_rect(4, 4, w - 8, h - 8, 8, wob=1.0)
    a.shadow(body, 3, 4)
    a.poly(body, fill=CREAM, outline=INK, width=4)
    a.finish(name)


def pill(name="pill.png", w=76, h=36):
    a = Art(w, h, 331)
    body = a.wobble_rect(3, 3, w - 6, h - 7, 15, wob=0.7)
    a.poly(body, fill=(252, 238, 170), outline=INK, width=3)
    a.finish(name)



def chip(name="chip.png", w=28, h=18):
    a = Art(w, h, 141)
    a.poly([(3, 3), (w - 4, 4), (w - 3, h - 4), (4, h - 3)], fill=WHITE, outline=INK, width=3)
    a.finish(name)


def bubble(name="bubble.png", w=240, h=150):
    """A speech bubble with a tail, white fill (tinted by the judgment colour)."""
    a = Art(w, h, 151)
    body = a.wobble_rect(6, 6, w - 8, h - 36, 40, wob=2.2)
    tail = [(w * 0.40, h - 40), (w * 0.46, h - 8), (w * 0.58, h - 40)]
    a.shadow(body, 5, 6)
    a.poly(tail, fill=WHITE, outline=INK, width=5)
    a.poly(body, fill=WHITE, outline=INK, width=5)
    a.poly([(w * 0.405, h - 42), (w * 0.455, h - 14), (w * 0.575, h - 42)], fill=WHITE, outline=None)
    a.poly([(w * 0.42, h - 44), (w * 0.57, h - 44), (w * 0.57, h - 36), (w * 0.42, h - 36)], fill=WHITE, outline=None)
    a.finish(name)


def wallpaper(name="backdrop.png", w=960, h=720):
    """Muted mauve wallpaper with a diamond lattice and little hand-drawn flowers."""
    a = Art(w, h, 161)
    a.d.rectangle([0, 0, w * SS, h * SS], fill=mix(PLUM1, MAUVE, 0.35) + (255,))
    cell = 96
    for gy in range(-1, h // cell + 2):
        for gx in range(-1, w // cell + 2):
            cx, cy = gx * cell + (cell / 2 if gy % 2 else 0), gy * cell * 0.5
            diamond = [(cx, cy - 40), (cx + 34, cy), (cx, cy + 40), (cx - 34, cy)]
            a.poly(diamond, fill=None, outline=mix(PLUM1, MAUVE, 0.15), width=2)
            petals = [(CORAL, 0), (MUSTARD, 72), (TEAL, 144), (CORAL, 216), (MUSTARD, 288)]
            tint = a.rng.choice((CORAL, MUSTARD, TEAL, LAV))
            for k in range(5):
                ang = math.radians(k * 72 + 20)
                px, py = cx + 9 * math.cos(ang), cy + 9 * math.sin(ang)
                a.d.ellipse([(px - 5) * SS, (py - 5) * SS, (px + 5) * SS, (py + 5) * SS], fill=mix(tint, PLUM1, 0.62) + (255,))
            a.d.ellipse([(cx - 3.5) * SS, (cy - 3.5) * SS, (cx + 3.5) * SS, (cy + 3.5) * SS], fill=mix(CREAM, PLUM1, 0.55) + (255,))
    a.finish(name)


def grain(name="grain.png", size=256):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    rng = random.Random(171)
    for _ in range(size * size // 3):
        x, y = rng.randrange(size), rng.randrange(size)
        dark = rng.random() < 0.55
        px[x, y] = (20, 12, 28, rng.randint(14, 34)) if dark else (255, 245, 225, rng.randint(10, 22))
    img.save(OUT / name)
    print("wrote", name, img.size)


def vignette(name="vignette.png", w=480, h=360):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    px = img.load()
    for y in range(h):
        for x in range(w):
            d = math.hypot((x - w / 2) / (w / 2), (y - h / 2) / (h / 2))
            a = max(0.0, (d - 0.78) / 0.7)
            px[x, y] = (22, 12, 30, int(min(1.0, a * a) * 120))
    img.save(OUT / name)
    print("wrote", name, img.size)


if __name__ == "__main__":
    card("panel_info.png", 486, 96, PLUM2, seed=1)
    card("panel_stats.png", 486, 204, PLUM1, seed=2)
    card("panel_score.png", 276, 60, PLUM0, r=14, seed=3)
    card("panel_wide.png", 342, 60, PLUM0, r=14, seed=4)
    card("panel_grade.png", 210, 60, PLUM0, r=14, seed=5)
    card("panel_select.png", 888, 236, PLUM1, seed=7)
    bottom_bar("panel_bottom.png")
    video_frame("video_frame.png")
    strip("strip.png")
    record_icon("cell_off.png", False)
    record_icon("cell_on.png", True)
    tube()
    bars()
    badge_pill()
    grade_badge()
    lane("lane_mustard.png", MUSTARD)
    lane("lane_coral.png", CORAL)
    lane("lane_teal.png", TEAL)
    beam()
    burst()
    star()
    dot()
    ring()
    sleeve()
    wall()
    tray()
    tag()
    pill()
    chip_pill()
    chip()
    bubble()
    wallpaper()
    grain()
    vignette()
