from pathlib import Path

import numpy as np

from video2sm import dsp, features


def _attacks(n: int, **hits: float) -> np.ndarray:
    strengths = np.zeros((n, 3))
    for slot, value in hits.items():
        strengths[int(slot.removeprefix("s"))] = value
    return strengths


def test_sustained_energy_counts_following_slots() -> None:
    rms = np.zeros(30)
    rms[10:26] = 1.0
    sustain = features.sustain_slots(rms, _attacks(30, s10=1.0))
    assert sustain[10] == 15  # slots 11..25 keep the energy


def test_new_attack_ends_the_sustain() -> None:
    rms = np.zeros(30)
    rms[10:26] = 1.0
    sustain = features.sustain_slots(rms, _attacks(30, s10=1.0, s14=1.0))
    assert sustain[10] == 3  # slots 11..13, then a fresh attack


def test_attack_threshold_is_relative_to_the_song() -> None:
    # Busy music: every slot has flux well above any fixed floor, only the bursts are attacks.
    strengths = np.full((30, 3), 0.8)
    strengths[10] = strengths[20] = 2.0
    rms = np.ones(30)
    sustain = features.sustain_slots(rms, strengths)
    assert sustain[10] == 9  # slots 11..19, then the burst at 20


def test_decaying_energy_ends_the_sustain() -> None:
    rms = np.zeros(30)
    rms[10:14] = 1.0
    rms[14:20] = 0.3
    sustain = features.sustain_slots(rms, _attacks(30, s10=1.0))
    assert sustain[10] == 3


def test_silent_slot_has_no_sustain() -> None:
    sustain = features.sustain_slots(np.zeros(12), np.zeros((12, 3)))
    assert not sustain.any()


def test_last_slot_has_no_sustain() -> None:
    sustain = features.sustain_slots(np.ones(8), np.zeros((8, 3)))
    assert sustain[-1] == 0 and sustain[0] == 7


def test_grid_features_carry_sustain(click_wav: Path) -> None:
    from video2sm import beats

    audio = dsp.load_audio(click_wav)
    grid = features.extract_grid_features(audio, beats.analyze_beats(audio))
    assert grid.sustain is not None
    assert grid.sustain.shape == (grid.n_slots,)
    assert (grid.sustain >= 0).all()
