"""Exact moments things are heard: attack times to the millisecond, for aligning notes to audio.

The chart grid only knows 16th notes; a singer does not. These helpers find the actual
attack nearest to a grid time, so a note can sit where the sound really starts.
"""

from __future__ import annotations

import librosa
import numpy as np

from . import dsp

# A pitch tracker only reports a note once the pitch has settled, typically a few tens of
# milliseconds after the consonant. So look further back than forward for its attack.
REFINE_BEFORE_SECONDS = 0.15
REFINE_AFTER_SECONDS = 0.04


def onset_times(
    audio: dsp.Audio, fmin: float | None = None, fmax: float | None = None
) -> np.ndarray:
    """Attack times in seconds (latency-corrected), optionally within a frequency band."""
    if not np.any(audio.samples):
        return np.zeros(0)
    envelope = dsp.onset_envelope(audio, fmin=fmin, fmax=fmax)
    frames = librosa.onset.onset_detect(
        onset_envelope=envelope,
        sr=audio.sample_rate,
        hop_length=dsp.HOP_LENGTH,
        units="frames",
    )
    return dsp.frame_times(len(envelope), audio.sample_rate)[frames]


def nearest(onsets: np.ndarray, t: float, before: float, after: float) -> float | None:
    """The onset closest to `t` within [t - before, t + after], or None."""
    if len(onsets) == 0:
        return None
    window = onsets[(onsets >= t - before) & (onsets <= t + after)]
    if len(window) == 0:
        return None
    return float(window[np.argmin(np.abs(window - t))])


def refined_start(t: float, onsets: np.ndarray) -> float:
    """Where a note reported at `t` actually begins: its attack if one is close, else `t`."""
    found = nearest(onsets, t, REFINE_BEFORE_SECONDS, REFINE_AFTER_SECONDS)
    return t if found is None else found
