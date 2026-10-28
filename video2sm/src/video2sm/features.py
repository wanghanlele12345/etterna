"""Per-grid-slot onset strengths, the raw material for chart generation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter1d

from . import dsp
from .beats import BeatAnalysis

SLOTS_PER_BEAT = 4  # 16th-note grid
BEATS_PER_MEASURE = 4
SLOTS_PER_MEASURE = SLOTS_PER_BEAT * BEATS_PER_MEASURE
BANDS_HZ = ((None, dsp.LOW_BAND_HZ), (dsp.LOW_BAND_HZ, 2000.0), (2000.0, None))
_WINDOW_FRACTION = 0.35  # look this far (of a slot) either side of the grid line
_PREVIEW_SECONDS = 12.0
_SUSTAIN_KEEP = 0.6  # a note keeps sounding while energy stays above this share of its peak
# ...and no new attack arrives. "Attack" is relative to the song: flux is rarely near
# zero in real music, so a fixed level would end every sustain at once. The floor keeps
# near-silent tracks (where the quantile is ~0) from calling every wobble an attack.
_ATTACK_QUANTILE = 75.0
_ATTACK_FLOOR = 0.4
_SUSTAIN_LOOKAHEAD = 2 * SLOTS_PER_MEASURE


@dataclass(frozen=True)
class GridFeatures:
    """Onset strength per slot and band (low, mid, high), each ~0..1."""

    strengths: np.ndarray  # shape (n_slots, 3)
    slot_seconds: float
    first_beat_time: float
    # Slots the sound at each slot keeps going after its attack; None = unknown (no holds).
    sustain: np.ndarray | None = None

    @property
    def n_slots(self) -> int:
        return int(self.strengths.shape[0])

    @property
    def n_measures(self) -> int:
        return self.n_slots // SLOTS_PER_MEASURE

    def slot_time(self, slot: int) -> float:
        return self.first_beat_time + slot * self.slot_seconds


def _band_envelope(audio: dsp.Audio, fmin: float | None, fmax: float | None) -> np.ndarray:
    envelope = dsp.onset_envelope(audio, fmin=fmin, fmax=fmax)
    scale = float(np.percentile(envelope, 95))
    return envelope / scale if scale > 0 else envelope


def sustain_slots(rms: np.ndarray, strengths: np.ndarray) -> np.ndarray:
    """For each slot, how many following slots the sound keeps going.

    The sound goes on while RMS energy stays near its level at the attack and no
    new attack (onset strength above the song's own 75th percentile) arrives. Looks ahead at most two measures, which is more than a
    hold ever needs and keeps this linear in the song length.
    """
    n = len(rms)
    attack = strengths.max(axis=1)
    attack_limit = max(float(np.percentile(attack, _ATTACK_QUANTILE)), _ATTACK_FLOOR) if n else 0.0
    out = np.zeros(n, dtype=np.int64)
    for slot in range(n):
        reference = rms[slot]
        if reference <= 0:
            continue
        floor = reference * _SUSTAIN_KEEP
        stop = min(n, slot + 1 + _SUSTAIN_LOOKAHEAD)
        end = slot + 1
        while end < stop and rms[end] >= floor and attack[end] <= attack_limit:
            end += 1
        out[slot] = end - slot - 1
    return out


def extract_grid_features(audio: dsp.Audio, analysis: BeatAnalysis) -> GridFeatures:
    slot_seconds = analysis.beat_period / SLOTS_PER_BEAT
    usable = audio.duration - analysis.first_beat_time
    n_measures = int(usable // (slot_seconds * SLOTS_PER_MEASURE))
    n_slots = n_measures * SLOTS_PER_MEASURE
    if n_slots <= 0:
        raise ValueError("audio is shorter than one measure after the first beat")

    frame_seconds = dsp.HOP_LENGTH / audio.sample_rate
    half = max(1, round(slot_seconds * _WINDOW_FRACTION / frame_seconds))
    slot_times = analysis.first_beat_time + np.arange(n_slots) * slot_seconds

    columns = []
    for fmin, fmax in BANDS_HZ:
        envelope = _band_envelope(audio, fmin, fmax)
        times = dsp.frame_times(len(envelope), audio.sample_rate)
        peaks = maximum_filter1d(envelope, size=2 * half + 1)
        columns.append(np.interp(slot_times, times, peaks))
    strengths = np.clip(np.stack(columns, axis=1), 0.0, 2.0)

    rms = dsp.rms_envelope(audio)
    rms_peaks = maximum_filter1d(rms, size=2 * half + 1)
    rms_at_slots = np.interp(slot_times, dsp.rms_frame_times(len(rms), audio.sample_rate), rms_peaks)
    return GridFeatures(
        strengths=strengths,
        slot_seconds=slot_seconds,
        first_beat_time=analysis.first_beat_time,
        sustain=sustain_slots(rms_at_slots, strengths),
    )


def preview_window(audio: dsp.Audio) -> tuple[float, float]:
    """Start/length (seconds) of the most energetic stretch, for the song-select preview."""
    length = min(_PREVIEW_SECONDS, audio.duration)
    window = int(length * audio.sample_rate)
    if window <= 0 or len(audio.samples) <= window:
        return 0.0, length
    energy = np.square(audio.samples.astype(np.float64))
    cumulative = np.concatenate(([0.0], np.cumsum(energy)))
    sums = cumulative[window:] - cumulative[:-window]
    # Skip the first 10% so previews don't start on the intro.
    start_index = int(np.argmax(sums[int(len(sums) * 0.1):])) + int(len(sums) * 0.1)
    return round(start_index / audio.sample_rate, 3), round(length, 3)
