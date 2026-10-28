from pathlib import Path

from PIL import Image

from tests.test_review import EMPTY, COLUMNS, build_song, measure_from, row
from video2sm import view


def pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    return image.convert("RGB").getpixel((x, y))


def slot_y(slot: int, first_slot: int = 0) -> int:
    return view.HEADER + (slot - first_slot) * view.SLOT_HEIGHT + view.SLOT_HEIGHT // 2


def test_image_size_follows_the_number_of_measures(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    one = view.render_chart(path, "Easy", start=0, count=1)
    four = view.render_chart(path, "Easy", start=0, count=4)
    assert one.width == four.width == view.WIDTH
    assert four.height - one.height == 3 * 16 * view.SLOT_HEIGHT


def test_notes_are_drawn_in_the_colour_of_their_lane(tmp_path: Path) -> None:
    path = build_song(tmp_path)  # measure 0: lane 4 at s0 and s8, lane 3 at s4, lane 5 at s12
    image = view.render_chart(path, "Easy", start=0, count=1)
    yellow = pixel(image, view.lane_center(3), slot_y(0))
    white = pixel(image, view.lane_center(2), slot_y(4))
    assert yellow[0] > 200 and yellow[1] > 170 and yellow[2] < 130
    assert min(white) > 200


def test_empty_lane_positions_keep_the_lane_background(tmp_path: Path) -> None:
    image = view.render_chart(build_song(tmp_path), "Easy", start=0, count=1)
    background = pixel(image, view.lane_center(0), slot_y(2))
    assert max(background) < 80


def test_holds_are_drawn_between_head_and_tail(tmp_path: Path) -> None:
    from video2sm import review

    path = build_song(tmp_path)
    assert review.edit_chart(path, "Easy", [{"measure": 1, "notes": "s0:H6 s12:|6"}])["ok"]
    image = view.render_chart(path, "Easy", start=1, count=1)
    middle = pixel(image, view.lane_center(5), slot_y(6, first_slot=0))
    outside = pixel(image, view.lane_center(5), slot_y(14, first_slot=0))
    assert max(middle) > 120 and max(outside) < 80


def test_melody_and_drums_are_drawn_beside_the_lanes(tmp_path: Path) -> None:
    image = view.render_chart(build_song(tmp_path), "Easy", start=0, count=1)
    melody_band = [pixel(image, x, slot_y(0)) for x in range(view.MELODY_LEFT, view.MELODY_LEFT + view.MELODY_WIDTH)]
    drum_band = [pixel(image, x, slot_y(0)) for x in range(view.DRUM_LEFT, view.DRUM_LEFT + view.DRUM_WIDTH)]
    assert any(max(c) > 150 for c in melody_band)  # the D4 that starts on the downbeat
    assert any(max(c) > 150 for c in drum_band)  # the kick


def test_save_writes_a_png(tmp_path: Path) -> None:
    path = build_song(tmp_path)
    out = tmp_path / "view.png"
    view.save_chart_view(path, "Easy", 0, 2, out)
    assert Image.open(out).format == "PNG"


def test_range_is_clamped(tmp_path: Path) -> None:
    image = view.render_chart(build_song(tmp_path), "Easy", start=6, count=50)
    assert image.height == view.HEADER + 2 * 16 * view.SLOT_HEIGHT + view.FOOTER


def test_sections_and_energy_are_drawn_in_the_gutter(tmp_path: Path) -> None:
    image = view.render_chart(build_song(tmp_path), "Easy", start=4, count=1)
    # measure 4 has energy 0.9: a long bar in the gutter just under its label
    bar = [pixel(image, x, view.HEADER + 21) for x in range(4, view.GUTTER - 4)]
    assert sum(1 for c in bar if max(c) > 120) >= 20


# --- looking at the video -------------------------------------------------------------------


def test_contact_sheet_has_one_tile_per_time(click_video) -> None:
    sheet = view.contact_sheet(click_video, [2.0, 10.0, 20.0, 30.0], columns=2, tile_width=160)
    assert sheet.width == 2 * 160
    assert sheet.height > 2 * 80  # two rows of 16:9-ish tiles plus label strips


def test_contact_sheet_defaults_to_evenly_spaced_times(click_video) -> None:
    sheet = view.contact_sheet(click_video, None, count=6, columns=3, tile_width=120)
    assert sheet.width == 3 * 120


def test_contact_sheet_times_outside_the_video_are_clamped(click_video) -> None:
    sheet = view.contact_sheet(click_video, [-5.0, 9999.0], columns=2, tile_width=100)
    assert sheet.width == 200
