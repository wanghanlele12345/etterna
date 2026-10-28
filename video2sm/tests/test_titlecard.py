from pathlib import Path

import pytest
from PIL import Image

from video2sm import titlecard

FONT = next((p for p in titlecard._FONT_CANDIDATES if Path(p).is_file()), None)
needs_font = pytest.mark.skipif(FONT is None, reason="no CJK-capable system font found")


@needs_font
def test_card_has_the_requested_height_and_fits_the_width(tmp_path: Path) -> None:
    out = titlecard.render_comic_text("盆栽哥 Test", tmp_path / "t.png", 300, 32, 3, FONT)
    image = Image.open(out)
    assert image.height == 32 and image.width <= 300


@needs_font
def test_face_is_white_with_a_dark_outline_so_only_the_face_tints(tmp_path: Path) -> None:
    image = Image.open(titlecard.render_comic_text("ABC", tmp_path / "t.png", 300, 32, 3, FONT)).convert("RGBA")
    solid = [p for p in image.getdata() if p[3] == 255]
    assert (255, 255, 255, 255) in solid  # the face
    assert any(p[:3] == titlecard.INK[:3] for p in solid)  # the outline
    assert any(0 < p[3] < 255 for p in image.getdata())  # smooth edges, not blocks


@needs_font
def test_long_text_is_shrunk_to_fit(tmp_path: Path) -> None:
    long = "盆栽哥梦幻联动现场 " * 6
    image = Image.open(titlecard.render_comic_text(long, tmp_path / "t.png", 300, 32, 3, FONT))
    assert image.width <= 300


@needs_font
def test_chinese_characters_are_drawn(tmp_path: Path) -> None:
    image = Image.open(titlecard.render_comic_text("联动现场", tmp_path / "t.png", 300, 32, 3, FONT)).convert("RGBA")
    lit = sum(1 for p in image.getdata() if p[3])
    assert lit > 800  # four dense characters, not four empty boxes


def test_missing_font_gives_no_card(tmp_path: Path) -> None:  # find_font() is disabled by conftest
    assert titlecard.write_cards(tmp_path, "Title", "Artist") == ()
    assert list(tmp_path.iterdir()) == []


@needs_font
def test_write_cards_creates_title_and_artist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(titlecard, "find_font", lambda: FONT)
    written = titlecard.write_cards(tmp_path, "盆栽哥梦幻联动现场", "王菲")
    assert sorted(p.name for p in written) == ["artist.png", "title.png"]
    assert all(p.is_file() for p in written)


@needs_font
def test_blank_text_makes_no_card(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(titlecard, "find_font", lambda: FONT)
    assert [p.name for p in titlecard.write_cards(tmp_path, "Only Title", "  ")] == ["title.png"]
