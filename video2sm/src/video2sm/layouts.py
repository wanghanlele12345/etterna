"""Key layouts: how many columns a chart has and how notes should be spread over them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

NEUTRAL = -1  # a column that belongs to neither hand (e.g. pop'n's centre button)


@dataclass(frozen=True)
class KeyLayout:
    name: str  # the StepMania steps type written to #STEPSTYPE
    columns: int
    hands: tuple[int, ...]  # per column: 0 left, 1 right, NEUTRAL for none
    bass_columns: tuple[int, ...]  # columns that suit low-frequency hits
    treble_columns: tuple[int, ...]  # columns that suit high-frequency hits
    jump_pairs: tuple[tuple[int, int], ...]
    # How far the hands travel. Wide layouts need these tight or patterns turn into
    # leaps across the whole keyboard.
    max_step: int  # most columns between one note and the next
    leap_penalty: float  # score lost per column of travel beyond the first
    usage_weight: float  # how hard to even out column usage
    hand_bonus: float  # reward for switching hands


DANCE_SINGLE = KeyLayout(
    name="dance-single",
    columns=4,
    hands=(0, 0, 1, 1),
    bass_columns=(1, 2),
    treble_columns=(0, 3),
    jump_pairs=((0, 3), (1, 2), (0, 2), (1, 3)),
    max_step=3,
    leap_penalty=0.0,
    usage_weight=2.0,
    hand_bonus=1.0,
)

# S D F [space] J K L: three fingers per hand, thumb on the shared centre column.
KB7_SINGLE = KeyLayout(
    name="kb7-single",
    columns=7,
    hands=(0, 0, 0, NEUTRAL, 1, 1, 1),
    bass_columns=(2, 3, 4),
    treble_columns=(0, 1, 5, 6),
    jump_pairs=(
        (0, 2), (1, 3), (2, 4), (3, 5), (4, 6),
        (1, 2), (4, 5), (0, 3), (3, 6),
    ),
    max_step=3,
    leap_penalty=0.2,
    usage_weight=1.0,
    hand_bonus=0.8,
)

POPN_NINE = KeyLayout(
    name="pnm-nine",  # Etterna's StepsType spelling; the Style is called "popn-nine"
    columns=9,
    hands=(0, 0, 0, 0, NEUTRAL, 1, 1, 1, 1),
    bass_columns=(3, 4, 5),
    treble_columns=(0, 1, 7, 8),
    # Chords a hand can actually hold: two to four columns apart, never the full width.
    jump_pairs=(
        (0, 2), (1, 3), (2, 4), (3, 5), (4, 6), (5, 7), (6, 8),
        (0, 4), (4, 8),
    ),
    max_step=4,
    leap_penalty=0.2,
    usage_weight=0.5,
    hand_bonus=0.8,
)

ALL_LAYOUTS: tuple[KeyLayout, ...] = (DANCE_SINGLE, KB7_SINGLE, POPN_NINE)
_BY_STEPS_TYPE = {layout.name: layout for layout in ALL_LAYOUTS}
_ALIASES = {
    "4k": DANCE_SINGLE.name,
    "dance": DANCE_SINGLE.name,
    "7k": KB7_SINGLE.name,
    "kb7": KB7_SINGLE.name,
    "9k": POPN_NINE.name,
    "popn": POPN_NINE.name,
    "popn-nine": POPN_NINE.name,
    "pnm": POPN_NINE.name,
}
VALID_KEY_MODES = "kb7-single (7k), dance-single (4k), pnm-nine (9k, popn)"
DEFAULT_KEY_MODES = (KB7_SINGLE.name,)


def layout_for_steps_type(steps_type: str) -> KeyLayout | None:
    """The layout that produces this #STEPSTYPE, or None if it isn't one of ours."""
    return _BY_STEPS_TYPE.get(steps_type)


def resolve_layout(name: str) -> KeyLayout:
    word = name.strip().lower()
    layout = _BY_STEPS_TYPE.get(_ALIASES.get(word, word))
    if layout is None:
        raise ValueError(f"unknown key mode {name!r}; valid key modes: {VALID_KEY_MODES}")
    return layout


def resolve_layouts(selection: Sequence[str]) -> tuple[KeyLayout, ...]:
    """Resolve several key modes, keeping order and dropping duplicates."""
    if not selection:
        raise ValueError(f"choose at least one key mode: {VALID_KEY_MODES}")
    resolved: dict[str, KeyLayout] = {}
    for raw in selection:
        layout = resolve_layout(raw)
        resolved.setdefault(layout.name, layout)
    return tuple(resolved.values())
