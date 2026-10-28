"""Constant-tempo beat grid detection: BPM, first beat, confidence.

The grid is found in two stages: librosa's beat tracker gives a rough tempo,
then a dense search over (BPM, phase) maximises onset energy on the grid so
the result is accurate to a few milliseconds, which is what sync depends on.
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d

from . import dsp
from .errors import AnalysisError

MIN_DURATION_SECONDS = 8.0
BPM_RANGE = (90.0, 180.0)
_SEARCH_BPM_SPAN = 0.6
_SEARCH_BPM_STEP = 0.005
_PHASE_STEP_SECONDS = 0.002
_UNSTABLE_MS = 25.0
_LOW_CONFIDENCE = 0.5


@dataclass(frozen=True)
class BeatAnalysis:
    bpm: float
    first_beat_time: float  # seconds; the grid's first measure line
    confidence: float  # 0..1, how strongly onsets sit on the grid
    stability_ms: float  # median distance of real onsets from the grid
    duration: float
    warnings: tuple[str, ...] = ()

    @property
    def offset(self) -> float:
        """The #OFFSET value: simfiles store the first-beat time negated."""
        return -self.first_beat_time

    @property
    def beat_period(self) -> float:
        return 60.0 / self.bpm


def _normalise_bpm(bpm: float) -> float:
    low, high = BPM_RANGE
    while bpm < low:
        bpm *= 2.0
    while bpm >= high:
        bpm /= 2.0
    return bpm


def _rough_period(envelope: np.ndarray, sample_rate: int) -> float:
    tempo, beat_frames = librosa.beat.beat_track(
        onset_envelope=envelope,
        sr=sample_rate,
        hop_length=dsp.HOP_LENGTH,
        start_bpm=120.0,
        tightness=100,
        trim=False,
    )
    bpm = float(np.atleast_1d(tempo)[0])
    if len(beat_frames) > 8:
        times = librosa.frames_to_time(
            beat_frames, sr=sample_rate, hop_length=dsp.HOP_LENGTH
        )
        bpm = 60.0 / float(np.median(np.diff(times)))
    return 60.0 / _normalise_bpm(bpm)


def _grid_score(
    envelope: np.ndarray,
    times: np.ndarray,
    period: float,
    phase: float,
    duration: float,
) -> float:
    beat_times = np.arange(phase, duration, period)
    return float(np.interp(beat_times, times, envelope).sum())


def _best_grid(
    envelope: np.ndarray, times: np.ndarray, rough_period: float, duration: float
) -> tuple[float, float]:
    """Dense (period, phase) search; returns the best pair."""
    smooth = gaussian_filter1d(envelope, sigma=2.0)
    rough_bpm = 60.0 / rough_period
    bpms = np.arange(
        rough_bpm - _SEARCH_BPM_SPAN,
        rough_bpm + _SEARCH_BPM_SPAN + _SEARCH_BPM_STEP,
        _SEARCH_BPM_STEP,
    )
    best = (-1.0, rough_period, 0.0)
    for bpm in bpms:
        period = 60.0 / bpm
        phases = np.arange(0.0, period, _PHASE_STEP_SECONDS)
        beat_grid = phases[:, None] + period * np.arange(int(duration / period) + 1)
        beat_grid = np.where(beat_grid < duration, beat_grid, duration)
        scores = np.interp(beat_grid, times, smooth).sum(axis=1)
        index = int(scores.argmax())
        if scores[index] > best[0]:
            best = (float(scores[index]), period, float(phases[index]))
    _, period, phase = best
    # Polish the phase on the raw envelope at 1 ms resolution.
    candidates = phase + np.arange(-0.006, 0.0061, 0.001)
    polished = max(
        candidates,
        key=lambda p: _grid_score(envelope, times, period, p % period, duration),
    )
    return period, polished % period


def _stability_and_confidence(
    envelope: np.ndarray,
    times: np.ndarray,
    period: float,
    phase: float,
    duration: float,
) -> tuple[float, float]:
    beat_times = np.arange(phase, duration - period / 2, period)
    window = period / 4
    threshold = float(np.percentile(envelope, 60))
    residuals: list[float] = []
    hits = 0
    for beat in beat_times:
        mask = (times >= beat - window) & (times <= beat + window)
        if not mask.any():
            continue
        local = envelope[mask]
        if local.max() >= threshold:
            hits += 1
            peak_time = times[mask][int(local.argmax())]
            residuals.append(abs(peak_time - beat))
    if not residuals:
        return 1000.0, 0.0
    return float(np.median(residuals)) * 1000.0, hits / max(len(beat_times), 1)


def _downbeat_shift(
    audio: dsp.Audio, times: np.ndarray, period: float, phase: float
) -> int:
    """Pick which of 4 beats starts a measure: the one with the most bass."""
    low = dsp.onset_envelope(audio, fmax=dsp.LOW_BAND_HZ)
    beat_times = np.arange(phase, audio.duration - period, period)
    strengths = np.interp(beat_times, times, low)
    scores = [float(strengths[p::4].mean()) if len(strengths[p::4]) else 0.0 for p in range(4)]
    return int(np.argmax(scores))


def analyze_beats(audio: dsp.Audio) -> BeatAnalysis:
    if audio.duration < MIN_DURATION_SECONDS:
        raise AnalysisError(
            f"audio too short ({audio.duration:.1f}s); need at least "
            f"{MIN_DURATION_SECONDS:.0f}s to find a tempo"
        )
    if float(np.abs(audio.samples).max()) < 1e-4:
        raise AnalysisError("audio is silent; no beat can be detected")

    envelope = dsp.beat_envelope(audio)
    if float(envelope.max()) <= 0.0:
        raise AnalysisError("no onsets found in the audio")
    times = dsp.frame_times(len(envelope), audio.sample_rate)

    rough = _rough_period(envelope, audio.sample_rate)
    period, phase = _best_grid(envelope, times, rough, audio.duration)
    stability_ms, confidence = _stability_and_confidence(
        envelope, times, period, phase, audio.duration
    )

    shift = _downbeat_shift(audio, times, period, phase)
    first_beat = phase + shift * period
    if first_beat >= 4 * period:  # phase + shift never exceeds this, but be safe
        first_beat -= 4 * period

    warnings: list[str] = []
    if stability_ms > _UNSTABLE_MS:
        warnings.append(
            f"onsets drift {stability_ms:.0f} ms from a fixed grid: the tempo may "
            "vary or the track may be live; check sync in an editor"
        )
    if confidence < _LOW_CONFIDENCE:
        warnings.append(
            f"low beat confidence ({confidence:.2f}); the track may lack a clear "
            "steady beat"
        )
    return BeatAnalysis(
        bpm=round(float(60.0 / period), 3),
        first_beat_time=round(float(first_beat), 3),
        confidence=round(float(confidence), 3),
        stability_ms=round(float(stability_ms), 2),
        duration=float(audio.duration),
        warnings=tuple(warnings),
    )
