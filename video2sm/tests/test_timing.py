import numpy as np
import pytest

from video2sm import dsp, timing

SR = dsp.SAMPLE_RATE


def clicks(times, seconds=6.0, hz=1000.0) -> dsp.Audio:
    signal = np.zeros(int(seconds * SR), dtype=np.float32)
    t = np.arange(int(0.08 * SR)) / SR
    # decays smoothly to zero: a hard cut would itself be a click
    burst = (np.sin(2 * np.pi * hz * t) * np.exp(-t * 40) * (1 - t / t[-1])).astype(np.float32)
    for at in times:
        i = int(at * SR)
        signal[i : i + len(burst)] += burst[: len(signal) - i]
    return dsp.Audio(samples=signal, sample_rate=SR)


def test_onset_times_find_each_attack_within_a_few_milliseconds() -> None:
    truth = [0.5, 1.237, 2.0, 3.41, 4.05]
    found = timing.onset_times(clicks(truth))
    assert len(found) == len(truth)
    assert np.max(np.abs(found - np.array(truth))) < 0.012


def test_onset_times_of_silence_are_empty() -> None:
    silent = dsp.Audio(samples=np.zeros(SR * 2, dtype=np.float32), sample_rate=SR)
    assert len(timing.onset_times(silent)) == 0


def test_nearest_picks_the_closest_time_inside_the_window() -> None:
    onsets = np.array([1.0, 1.10, 1.30])
    assert timing.nearest(onsets, 1.12, before=0.05, after=0.05) == pytest.approx(1.10)
    assert timing.nearest(onsets, 1.20, before=0.05, after=0.05) is None


def test_nearest_window_can_be_lopsided() -> None:
    onsets = np.array([0.90, 1.06])
    # a pitch tracker reports notes late, so look further back than forward
    assert timing.nearest(onsets, 1.0, before=0.12, after=0.03) == pytest.approx(0.90)


def test_refined_start_moves_a_late_note_back_to_its_attack() -> None:
    onsets = np.array([2.00, 2.50])
    assert timing.refined_start(2.04, onsets) == pytest.approx(2.00)
    assert timing.refined_start(2.30, onsets) == pytest.approx(2.30)  # nothing close: keep it
