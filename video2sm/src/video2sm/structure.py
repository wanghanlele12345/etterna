"""The song's shape: how loud each measure is and which stretches sound alike (verse, chorus...).

Gives a choreographer the same overview a listener has: where the music builds, where it
drops, and which sections come back.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import librosa
import numpy as np

from . import dsp
from .features import SLOTS_PER_MEASURE, SLOTS_PER_BEAT

if TYPE_CHECKING:
    from .beats import BeatAnalysis

_HOP = 512
_N_MFCC = 13
_MEASURES_PER_SECTION = 12
_MIN_SECTIONS, _MAX_SECTIONS = 3, 12
_MIN_SECTION_MEASURES = 2
_SAME_SOUND = 0.8  # cosine similarity of two sections' average sound to share a label
_LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@dataclass(frozen=True)
class Section:
    start: int  # first measure
    end: int  # last measure, inclusive
    label: str  # sections that sound alike share a letter


def section_count(n_measures: int) -> int:
    return int(min(max(round(n_measures / _MEASURES_PER_SECTION), _MIN_SECTIONS), _MAX_SECTIONS))


def measure_features(
    audio: dsp.Audio, analysis: BeatAnalysis, n_measures: int
) -> tuple[np.ndarray, np.ndarray]:
    """(features per measure as a (d, n) matrix, loudness per measure scaled to 0..1)."""
    sr = audio.sample_rate
    rms = librosa.feature.rms(y=audio.samples, hop_length=_HOP)[0]
    mfcc = librosa.feature.mfcc(y=audio.samples, sr=sr, hop_length=_HOP, n_mfcc=_N_MFCC)
    chroma = librosa.feature.chroma_stft(y=audio.samples, sr=sr, hop_length=_HOP)
    frames = np.vstack([mfcc, chroma, rms[np.newaxis, :]])
    times = librosa.frames_to_time(np.arange(frames.shape[1]), sr=sr, hop_length=_HOP)
    measure_seconds = analysis.beat_period * SLOTS_PER_MEASURE / SLOTS_PER_BEAT

    columns, loudness = [], []
    for m in range(n_measures):
        begin = analysis.first_beat_time + m * measure_seconds
        inside = (times >= begin) & (times < begin + measure_seconds)
        if inside.any():
            columns.append(frames[:, inside].mean(axis=1))
            loudness.append(float(rms[inside].mean()))
        else:
            columns.append(np.zeros(frames.shape[0]))
            loudness.append(0.0)
    matrix = np.stack(columns, axis=1) if columns else np.zeros((frames.shape[0], 0))
    spread = matrix.std(axis=1, keepdims=True)
    standard = np.where(spread > 1e-9, (matrix - matrix.mean(axis=1, keepdims=True)) / np.maximum(spread, 1e-9), 0.0)
    energy = np.asarray(loudness)
    peak = float(energy.max()) if len(energy) else 0.0
    return standard, (energy / peak if peak > 0 else energy)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b) / norm if norm > 0 else 0.0


def sections_from_features(matrix: np.ndarray, count: int) -> list[Section]:
    """Cut the measures into `count` stretches and give alike-sounding stretches one letter."""
    n = matrix.shape[1]
    k = min(count, n // _MIN_SECTION_MEASURES)
    if k <= 1:
        return [Section(0, max(n - 1, 0), "A")]
    starts = sorted(int(b) for b in librosa.segment.agglomerative(matrix, k))
    ends = [b - 1 for b in starts[1:]] + [n - 1]
    centroids: list[np.ndarray] = []
    found = []
    for begin, end in zip(starts, ends):
        mean = matrix[:, begin : end + 1].mean(axis=1)
        label_index = next(
            (i for i, c in enumerate(centroids) if _cosine(mean, c) >= _SAME_SOUND), None
        )
        if label_index is None:
            centroids.append(mean)
            label_index = len(centroids) - 1
        found.append(Section(begin, end, _LABELS[label_index % len(_LABELS)]))
    return found


def describe(sections: list[Section], energy: np.ndarray) -> dict[str, Any]:
    return {
        "sections": [{"start": s.start, "end": s.end, "label": s.label} for s in sections],
        "energy": [round(float(e), 2) for e in energy],
    }
