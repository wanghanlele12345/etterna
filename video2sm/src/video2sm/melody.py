"""Read a melody (note start, end and pitch) out of a mono vocal track.

Pitch is tracked frame by frame with pYIN, then the voiced frames are cut into notes
wherever the voice breaks off or moves to a new pitch. Vibrato and short tracking
dropouts do not split a note.
"""

from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np

from .dsp import Audio

HOP_LENGTH = 256
FRAME_LENGTH = 2048
_FMIN_HZ = float(librosa.note_to_hz("C2"))
_FMAX_HZ = float(librosa.note_to_hz("C6"))
_BRIDGE_SECONDS = 0.06  # a dropout this short stays inside the note
_SPLIT_SEMITONES = 0.9  # moving this far from the note's pitch starts a new note
_FRAMES_BEFORE_SPLIT = 6  # ...once the note has settled
_PITCH_WINDOW_FRAMES = 15  # recent frames that define "the note's pitch"
_MIN_NOTE_SECONDS = 0.08
_REGISTER_SEMITONES = 14.0  # notes this far from the median pitch are bleed or tracking errors
_MIN_STRENGTH = 0.15
_MIN_NOTES_TO_JUDGE = 5


@dataclass(frozen=True)
class Note:
    start: float  # seconds
    end: float
    pitch: float  # MIDI note number (fractional)
    strength: float  # 0..1, loudness relative to the loud parts of the track

    @property
    def length(self) -> float:
        return self.end - self.start


def segment_notes(times: np.ndarray, midi: np.ndarray, rms: np.ndarray) -> list[Note]:
    """Cut frame-wise pitch (NaN = unvoiced) into notes."""
    if len(times) < 2:
        return []
    step = float(np.median(np.diff(times)))
    bridge_frames = max(1, int(round(_BRIDGE_SECONDS / step)))
    voiced = np.isfinite(midi)
    reference = float(np.percentile(rms[voiced], 95)) if voiced.any() else 0.0

    spans: list[tuple[int, int, list[float]]] = []  # (first frame, last frame, pitches)
    current: tuple[int, int, list[float]] | None = None
    last_voiced = -(10**9)
    for i in np.flatnonzero(voiced):
        pitch = float(midi[i])
        if current is not None and i - last_voiced > bridge_frames:
            spans.append(current)
            current = None
        if current is not None:
            first, _, pitches = current
            settled = len(pitches) >= _FRAMES_BEFORE_SPLIT
            recent = float(np.median(pitches[-_PITCH_WINDOW_FRAMES:]))
            if settled and abs(pitch - recent) > _SPLIT_SEMITONES:
                spans.append(current)
                current = None
        if current is None:
            current = (int(i), int(i), [pitch])
        else:
            first, _, pitches = current
            current = (first, int(i), pitches + [pitch])
        last_voiced = int(i)
    if current is not None:
        spans.append(current)

    notes = []
    for first, last, pitches in spans:
        length = (last - first + 1) * step
        if length < _MIN_NOTE_SECONDS:
            continue
        loudness = float(np.mean(rms[first : last + 1]))
        strength = min(loudness / reference, 1.0) if reference > 0 else 0.0
        notes.append(
            Note(
                start=float(times[first]),
                end=float(times[last]) + step,
                pitch=float(np.median(pitches)),
                strength=strength,
            )
        )
    return notes


def clean_notes(notes: list[Note]) -> list[Note]:
    """Drop notes too quiet or too far from the melody's register (stem bleed, octave slips)."""
    if len(notes) < _MIN_NOTES_TO_JUDGE:
        return notes
    centre = float(np.median([n.pitch for n in notes]))
    return [
        n for n in notes
        if abs(n.pitch - centre) <= _REGISTER_SEMITONES and n.strength >= _MIN_STRENGTH
    ]


def transcribe(audio: Audio) -> list[Note]:
    """Melody notes of a (vocal) track, in time order."""
    f0, voiced, _ = librosa.pyin(
        audio.samples,
        fmin=_FMIN_HZ,
        fmax=_FMAX_HZ,
        sr=audio.sample_rate,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
    )
    midi = np.where(voiced & np.isfinite(f0), librosa.hz_to_midi(f0), np.nan)
    rms = librosa.feature.rms(
        y=audio.samples, frame_length=FRAME_LENGTH, hop_length=HOP_LENGTH
    )[0]
    rms = rms[: len(midi)]
    times = librosa.times_like(f0, sr=audio.sample_rate, hop_length=HOP_LENGTH)
    return clean_notes(segment_notes(times, midi[: len(rms)], rms))
