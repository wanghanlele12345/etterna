import pytest

from video2sm import layouts


def test_dance_single_is_four_columns() -> None:
    layout = layouts.resolve_layout("dance-single")
    assert (layout.name, layout.columns) == ("dance-single", 4)


def test_nine_key_is_nine_columns() -> None:
    layout = layouts.resolve_layout("pnm-nine")
    assert (layout.name, layout.columns) == ("pnm-nine", 9)


def test_seven_key_is_seven_columns() -> None:
    layout = layouts.resolve_layout("kb7-single")
    assert (layout.name, layout.columns) == ("kb7-single", 7)


def test_seven_key_is_the_default_key_mode() -> None:
    assert [l.name for l in layouts.resolve_layouts(layouts.DEFAULT_KEY_MODES)] == ["kb7-single"]


def test_seven_key_centre_column_belongs_to_neither_hand() -> None:
    # S D F | space | J K L: the thumb column is shared.
    assert layouts.KB7_SINGLE.hands == (0, 0, 0, layouts.NEUTRAL, 1, 1, 1)


def test_nine_key_steps_type_is_the_one_etterna_reads() -> None:
    # Etterna's StepsType table (GameManager.cpp) spells pop'n music "pnm-nine"; its Style
    # is called "popn-nine". Writing the Style name makes the engine drop every chart.
    assert layouts.POPN_NINE.name == "pnm-nine"


@pytest.mark.parametrize(
    "alias, expected",
    [("7k", "kb7-single"), ("kb7", "kb7-single"), ("KB7-Single", "kb7-single"), ("4k", "dance-single"), ("4K", "dance-single"), ("9k", "pnm-nine"), ("popn", "pnm-nine"),
     ("popn-nine", "pnm-nine"), (" Popn-Nine ", "pnm-nine"), ("pnm", "pnm-nine")],
)
def test_aliases(alias: str, expected: str) -> None:
    assert layouts.resolve_layout(alias).name == expected


@pytest.mark.parametrize("name", ["", "12k", "nonsense"])
def test_unknown_key_mode_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="key mode"):
        layouts.resolve_layout(name)


@pytest.mark.parametrize("layout", layouts.ALL_LAYOUTS, ids=lambda l: l.name)
def test_layouts_are_internally_consistent(layout: layouts.KeyLayout) -> None:
    columns = range(layout.columns)
    assert len(layout.hands) == layout.columns
    assert set(layout.hands) <= {-1, 0, 1}
    assert set(layout.bass_columns) <= set(columns)
    assert set(layout.treble_columns) <= set(columns)
    assert layout.jump_pairs
    assert len({frozenset(p) for p in layout.jump_pairs}) == len(layout.jump_pairs)
    for a, b in layout.jump_pairs:
        assert a != b and a in columns and b in columns


def test_resolve_layouts_dedupes_and_keeps_order() -> None:
    names = [l.name for l in layouts.resolve_layouts(["9k", "4k", "popn-nine"])]
    assert names == ["pnm-nine", "dance-single"]


def test_resolve_layouts_requires_a_choice() -> None:
    with pytest.raises(ValueError, match="key mode"):
        layouts.resolve_layouts([])


def test_lookup_by_steps_type() -> None:
    assert layouts.layout_for_steps_type("pnm-nine").columns == 9
    assert layouts.layout_for_steps_type("dance-double") is None
