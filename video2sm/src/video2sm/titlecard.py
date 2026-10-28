"""Hand-lettered title and artist images for the gameplay HUD.

Etterna's bundled CJK font misses many characters, so song titles in Chinese render as boxes.
This draws the text with a system font instead: a white face with a thick near-black ink
outline (the theme's comic look), anti-aliased by drawing at 2x and shrinking. The face is
white so the theme can tint it; the outline stays dark.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SUPERSAMPLE = 2
INK = (29, 20, 36, 255)
TITLE_FILE = "title.png"
ARTIST_FILE = "artist.png"
TITLE_WIDTH, TITLE_HEIGHT, TITLE_STROKE = 300, 32, 3  # pixels: fits the HUD's title slot
ARTIST_WIDTH, ARTIST_HEIGHT, ARTIST_STROKE = 380, 22, 2
_MIN_SIZE = 10

_FONT_CANDIDATES = (
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/msyh.ttc",
)


def find_font() -> str | None:
    """A system font that covers Chinese, Japanese and Latin text, if there is one."""
    return next((p for p in _FONT_CANDIDATES if Path(p).is_file()), None)


def _measure(font: ImageFont.FreeTypeFont, text: str) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return right - left, bottom - top


def render_comic_text(text: str, out: Path, max_width: int, height: int, stroke: int, font: str | None) -> Path:
    """Draw `text` (shrunk until it fits `max_width`) as white lettering with an ink outline."""
    scale = SUPERSAMPLE
    size = (height - 2 * stroke) * scale
    face = ImageFont.truetype(font, size)
    while size > _MIN_SIZE * scale and _measure(face, text)[0] + 2 * stroke * scale > max_width * scale:
        size -= scale
        face = ImageFont.truetype(font, size)
    left, top, right, bottom = face.getbbox(text)
    pad = stroke * scale
    canvas = Image.new("RGBA", (right - left + 2 * pad, height * scale), (0, 0, 0, 0))
    ImageDraw.Draw(canvas).text(
        (pad - left, (canvas.height - (bottom - top)) // 2 - top), text, font=face,
        fill=(255, 255, 255, 255), stroke_width=pad, stroke_fill=INK,
    )
    card = canvas.resize((min(max(canvas.width // scale, 1), max_width), height), Image.LANCZOS)
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    card.save(out)
    return Path(out)


def write_cards(song_dir: Path, title: str, artist: str) -> tuple[Path, ...]:
    """Write title.png and artist.png into the song folder; nothing if no font is available."""
    font = find_font()
    if font is None:
        return ()
    written = []
    for text, name, width, height, stroke in (
        (title, TITLE_FILE, TITLE_WIDTH, TITLE_HEIGHT, TITLE_STROKE),
        (artist, ARTIST_FILE, ARTIST_WIDTH, ARTIST_HEIGHT, ARTIST_STROKE),
    ):
        if text.strip():
            written.append(render_comic_text(text.strip(), Path(song_dir) / name, width, height, stroke, font))
    return tuple(written)
