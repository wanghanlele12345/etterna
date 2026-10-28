"""Shared audio loading and onset-envelope helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from .errors import AnalysisError

SAMPLE_RATE = 22050
HOP_LENGTH = 128  # ~5.8 ms per frame
N_FFT = 1024
# Spectral-flux peaks trail the true attack by a few ms; calibrated against
# synthetic click tracks with known onset times.
ONSET_LATENCY_SECONDS = 0.007
LOW_BAND_HZ = 200.0
_LOW_BAND_WEIGHT = 1.5


@dataclass(frozen=True)
class Audio:
    samples: np.ndarray
    sample_rate: int

    @property
    def duration(self) -> float:
        return len(self.samples) / self.sample_rate


def load_audio(path: Path) -> Audio:
    """Load any audio file as mono float32 at the analysis sample rate."""
    try:
        samples, rate = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    except Exception as exc:  # librosa raises many backend-specific types
        raise AnalysisError(f"could not decode audio {Path(path).name}: {exc}") from exc
    return Audio(samples=samples.astype(np.float32), sample_rate=int(rate))


def frame_times(n_frames: int, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    # onset_strength uses centered frames, so no n_fft offset here.
    return (
        librosa.frames_to_time(
            np.arange(n_frames), sr=sample_rate, hop_length=HOP_LENGTH
        )
        - ONSET_LATENCY_SECONDS
    )


def onset_envelope(
    audio: Audio, fmin: float | None = None, fmax: float | None = None
) -> np.ndarray:
    """Spectral-flux onset strength, optionally restricted to a frequency band."""
    kwargs: dict[str, float] = {}
    if fmin is not None:
        kwargs["fmin"] = fmin
    if fmax is not None:
        kwargs["fmax"] = fmax
    return librosa.onset.onset_strength(
        y=audio.samples,
        sr=audio.sample_rate,
        hop_length=HOP_LENGTH,
        n_fft=N_FFT,
        n_mels=64 if fmax is None and fmin is None else 16,
        **kwargs,
    ).astype(np.float64)


def rms_envelope(audio: Audio) -> np.ndarray:
    """Short-time RMS energy per frame, on the same hop grid as the onset envelope."""
    return librosa.feature.rms(
        y=audio.samples, frame_length=N_FFT, hop_length=HOP_LENGTH
    )[0].astype(np.float64)


def rms_frame_times(n_frames: int, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Frame centres for rms_envelope (no onset-latency correction: RMS has no attack lag)."""
    return librosa.frames_to_time(np.arange(n_frames), sr=sample_rate, hop_length=HOP_LENGTH)


def _normalised(envelope: np.ndarray) -> np.ndarray:
    scale = float(np.percentile(envelope, 95))
    return envelope / scale if scale > 0 else envelope


def beat_envelope(audio: Audio) -> np.ndarray:
    """Full-band onsets plus extra weight on bass, where the beat usually lives."""
    full = _normalised(onset_envelope(audio))
    low = _normalised(onset_envelope(audio, fmax=LOW_BAND_HZ))
    return full + _LOW_BAND_WEIGHT * low
