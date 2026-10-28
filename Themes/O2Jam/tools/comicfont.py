"""Bitmap fonts for Etterna, hand-lettered comic style: a white face with a thick near-black
ink outline (tint it with diffuse; the outline stays dark). Written to <theme>/Fonts.

    python3 -I tools/comicfont.py <theme dir>

Font names must not be prefixes of one another (the engine matches by prefix).
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FACE = "/System/Library/Fonts/MarkerFelt.ttc"
INK = (29, 20, 36, 255)
ROWS = [
    " !\"#$%&'()*+,-./",
    "0123456789:;<=>?",
    "@ABCDEFGHIJKLMNO",
    "PQRSTUVWXYZ[\\]^_",
    "`abcdefghijklmno",
    "pqrstuvwxyz{|}~ ",
]
# (name, face index, size, outline)
FONTS = [("Marker", 1, 24, 2), ("Scrawl", 1, 50, 4), ("Poster", 1, 100, 7)]


def build(out_dir: Path, name: str, index: int, size: int, stroke: int) -> None:
    font = ImageFont.truetype(FACE, size, index=index)
    chars = [c for row in ROWS for c in row]
    ascent, descent = font.getmetrics()
    cell_h = ascent + descent + 2 * stroke + 2
    advances = {c: int(math.ceil(font.getlength(c))) for c in chars}
    digit_w = max(advances[c] for c in "0123456789")
    for c in "0123456789":
        advances[c] = digit_w  # tabular figures keep the rolling score from jittering
    cell_w = max(advances.values()) + 2 * stroke + 2
    sheet = Image.new("RGBA", (16 * cell_w, len(ROWS) * cell_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    widths = []
    for r, row in enumerate(ROWS):
        for col, ch in enumerate(row):
            advance = advances[ch] + 2 * stroke
            widths.append(advance if ch != " " else max(advance, size // 3))
            if ch == " ":
                continue
            ox = col * cell_w + (cell_w - advances[ch]) // 2
            oy = r * cell_h + stroke + 1
            draw.text((ox, oy), ch, font=font, fill=(255, 255, 255, 255), stroke_width=stroke, stroke_fill=INK)
    sheet.save(out_dir / f"{name} [main] 16x6.png")
    lines = ["[common]", f"Baseline={ascent + stroke + 1}", f"Top={stroke + 1}", f"LineSpacing={cell_h}",
             "DrawExtraPixelsLeft=0", "DrawExtraPixelsRight=0", "AdvanceExtraPixels=0", "", "[main]"]
    lines += [f"Line {r}={row}" for r, row in enumerate(ROWS)]
    lines += [f"{i}={w}" for i, w in enumerate(widths)]
    lines += ["", "TextureHints=32bpp"]
    (out_dir / f"{name}.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(name, sheet.size, "cell", (cell_w, cell_h))


if __name__ == "__main__":
    target = Path(sys.argv[1]) / "Fonts"
    target.mkdir(exist_ok=True)
    for spec in FONTS:
        build(target, *spec)
