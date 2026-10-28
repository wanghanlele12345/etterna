"""Musical events for stem-based charting: melody notes and drum hits placed on the grid.

The vocal melody is the backbone of a chart. Kick, snare and hi-hat hits from the drum
stem fill in around it, more of them as the difficulty rises. Each event knows which
musical part it came from, so column assignment can follow the pitch of the melody and
put drums where a drummer's hands would be.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import librosa
import numpy as np

from . import features, melody, timing
from .features import SLOTS_PER_BEAT, SLOTS_PER_MEASURE
from .melody import Note

if TYPE_CHECKING:  # charting imports this module, so only the types are needed here
    from .beats import BeatAnalysis
    from .charting import Profile
    from .stems import Stems

MELODY = "melody"
KICK, SNARE, HAT = "kick", "snare", "hat"
_DRUM_KINDS = (KICK, SNARE, HAT)  # in the order of the drum stem's low / mid / high bands

_MELODY_BASE_SCORE = 0.55
_MELODY_STRENGTH_SCORE = 0.45
_LONG_NOTE_SLOTS = SLOTS_PER_BEAT
_LONG_NOTE_BONUS = 0.25
_MELODY_PRIORITY = 0.3  # keeps the vocal line ahead of drums that compete for the same room
_SNAP_REACH_SLOTS = 1
_MIN_DRUM_HIT = 0.5  # share of the way from a band's noise floor to its loud hits
_DRUM_PEAK_PERCENTILE = 95.0
_MIN_DRUM_PEAK = 1.0  # a band whose loudest hits are fainter than this has no clear hits
_PITCH_LOW_PERCENTILE = 5.0
_PITCH_HIGH_PERCENTILE = 95.0
_MIN_PITCH_SPREAD = 2.0  # semitones; a flatter melody all sits on the middle lane
_LONG_NOTE_SECONDS = 0.5  # what describe_music counts as a sustained note
# every drum part at full weight and every grid position allowed: "what is in the track"
_ALL_DRUMS = SimpleNamespace(kick_weight=1.0, snare_weight=1.0, hat_weight=1.0, slot_weights=(1.0,) * 4)


@dataclass(frozen=True)
class MusicFeatures:
    """What the stems say about the song, on the chart's 16th-note grid."""

    n_slots: int
    slot_seconds: float
    first_beat_time: float
    drum_strengths: np.ndarray  # (n_slots, 3): kick, snare, hi-hat onset strength, ~0..1
    vocal_strengths: np.ndarray  # (n_slots,): vocal attack strength, used to place onsets
    melody: tuple[Note, ...]
    # exact attack times in seconds, for aligning notes to the audio afterwards
    vocal_onsets: tuple[float, ...] = ()
    drum_onsets: tuple[tuple[float, ...], ...] = ((), (), ())  # kick, snare, hat bands


@dataclass(frozen=True)
class Event:
    slot: int
    kind: str  # MELODY, KICK, SNARE or HAT
    score: float
    lane: float | None = None  # melody only: where its pitch sits, 0..columns-1
    length_slots: int = 0  # melody only: how long the note is held
    partner: str | None = None  # a drum hit on the same slot, merged into a melody event


def _fit(values: np.ndarray, length: int) -> np.ndarray:
    """Trim or zero-pad along the first axis so per-slot arrays match the chart grid."""
    if len(values) >= length:
        return values[:length]
    pad = [(0, length - len(values))] + [(0, 0)] * (values.ndim - 1)
    return np.pad(values, pad)


def music_from_stems(stems: Stems, analysis: BeatAnalysis, n_slots: int) -> MusicFeatures:
    """Read the vocal melody and drum hits of separated stems onto the chart's grid."""
    drums = features.extract_grid_features(stems.drums, analysis)
    vocals = features.extract_grid_features(stems.vocals, analysis)
    return MusicFeatures(
        n_slots=n_slots,
        slot_seconds=drums.slot_seconds,
        first_beat_time=drums.first_beat_time,
        drum_strengths=_fit(drums.strengths, n_slots),
        vocal_strengths=_fit(vocals.strengths.max(axis=1), n_slots),
        melody=tuple(melody.transcribe(stems.vocals)),
        vocal_onsets=tuple(timing.onset_times(stems.vocals)),
        drum_onsets=band_onsets(stems.drums),
    )


def band_onsets(audio) -> tuple[tuple[float, ...], ...]:
    """Exact attack times in the kick, snare and hi-hat bands."""
    return tuple(tuple(timing.onset_times(audio, fmin, fmax)) for fmin, fmax in features.BANDS_HZ)


def pitch_lanes(notes: list[Note], columns: int) -> list[float]:
    """Map each note's pitch to a lane: higher notes sit further right.

    The scale runs from the 5th to the 95th percentile of the melody's pitches, so a few
    stray notes do not squash the rest into the middle of the keyboard.
    """
    if not notes:
        return []
    pitches = np.array([n.pitch for n in notes])
    low = float(np.percentile(pitches, _PITCH_LOW_PERCENTILE))
    high = float(np.percentile(pitches, _PITCH_HIGH_PERCENTILE))
    top = columns - 1
    if high - low < _MIN_PITCH_SPREAD:
        return [top / 2.0] * len(notes)
    return [float(np.clip((p - low) / (high - low), 0.0, 1.0)) * top for p in pitches]


def _slot_of(seconds: float, music: MusicFeatures) -> int:
    return int(round((seconds - music.first_beat_time) / music.slot_seconds))


def _position_weight(profile: Profile, slot: int) -> float:
    return profile.slot_weights[slot % SLOTS_PER_BEAT]


def _snapped_slot(slot: int, music: MusicFeatures, profile: Profile) -> int | None:
    """Nearest slot the difficulty allows, preferring the one with the stronger vocal attack."""
    reach = range(slot - _SNAP_REACH_SLOTS, slot + _SNAP_REACH_SLOTS + 1)
    allowed = [
        s for s in reach if 0 <= s < music.n_slots and _position_weight(profile, s) > 0
    ]
    if not allowed:
        return None
    return max(allowed, key=lambda s: float(music.vocal_strengths[s]) + 0.5 * (s == slot))


def melody_events(music: MusicFeatures, profile: Profile, columns: int) -> list[Event]:
    lanes = pitch_lanes(list(music.melody), columns)
    found = []
    for note, lane in zip(music.melody, lanes):
        raw = _slot_of(note.start, music)
        if not 0 <= raw < music.n_slots:
            continue
        slot = _snapped_slot(raw, music, profile)
        if slot is None:
            continue
        length = max(_slot_of(note.end, music) - slot, 0)
        score = _MELODY_BASE_SCORE + _MELODY_STRENGTH_SCORE * note.strength
        if length >= _LONG_NOTE_SLOTS:
            score += _LONG_NOTE_BONUS
        found.append(
            Event(
                slot=slot,
                kind=MELODY,
                score=profile.melody_weight * score + _MELODY_PRIORITY,
                lane=lane,
                length_slots=length,
            )
        )
    return found


def _drum_hits(strengths: np.ndarray) -> np.ndarray:
    """Per band, 0..1 where 0 is the band's noise floor (its median) and 1 its loud hits.

    Onset strength is never near zero in real music, so a fixed threshold would call the
    background hum a hit; measuring from each band's own floor keeps only real peaks.
    """
    floor = np.median(strengths, axis=0)
    peak = np.maximum(np.percentile(strengths, _DRUM_PEAK_PERCENTILE, axis=0), _MIN_DRUM_PEAK)
    hits = np.clip((strengths - floor) / (peak - floor), 0.0, 1.0)
    return np.where(hits >= _MIN_DRUM_HIT, hits, 0.0)


def drum_events(music: MusicFeatures, profile: Profile) -> list[Event]:
    weights = np.array([profile.kick_weight, profile.snare_weight, profile.hat_weight])
    scored = _drum_hits(music.drum_strengths[: music.n_slots]) * weights
    found = []
    for slot in range(len(scored)):
        position = _position_weight(profile, slot)
        if position <= 0:
            continue
        band = int(np.argmax(scored[slot]))
        score = float(scored[slot, band]) * position
        if score > 0:
            found.append(Event(slot=slot, kind=_DRUM_KINDS[band], score=score))
    return found


def select_events(music: MusicFeatures, profile: Profile, columns: int) -> list[Event]:
    """The events a chart of this difficulty plays, in time order."""
    melody = melody_events(music, profile, columns)
    drums = drum_events(music, profile)
    if not melody and not drums:
        return []

    candidates: dict[int, list[Event]] = {}
    for event in melody + drums:
        candidates.setdefault(event.slot, []).append(event)

    merged: list[Event] = []
    for slot_events in candidates.values():
        best = max(slot_events, key=lambda e: e.score)
        drum = next((e for e in slot_events if e.kind != MELODY), None)
        if best.kind == MELODY and drum is not None:
            best = Event(
                slot=best.slot, kind=MELODY, score=best.score, lane=best.lane,
                length_slots=best.length_slots, partner=drum.kind,
            )
        merged.append(best)

    measures_with_music = len({e.slot // SLOTS_PER_MEASURE for e in merged})
    active_seconds = measures_with_music * SLOTS_PER_MEASURE * music.slot_seconds
    target = int(round(profile.target_rows_per_second * active_seconds))

    occupied = np.zeros(music.n_slots, dtype=bool)
    chosen: list[Event] = []
    gap = profile.min_gap_slots
    for event in sorted(merged, key=lambda e: -e.score):
        if len(chosen) >= target:
            break
        lo, hi = max(0, event.slot - gap + 1), min(music.n_slots, event.slot + gap)
        if occupied[lo:hi].any():
            continue
        occupied[event.slot] = True
        chosen.append(event)
    return sorted(chosen, key=lambda e: e.slot)


def describe_music(music: MusicFeatures, max_notes: int) -> dict[str, Any]:
    """A plain-data summary of what was heard: the melody's notes and the drum hit counts."""
    notes = list(music.melody)
    pitch_range = None
    if notes:
        pitches = [n.pitch for n in notes]
        pitch_range = {
            "low": librosa.midi_to_note(round(min(pitches)), unicode=False),
            "high": librosa.midi_to_note(round(max(pitches)), unicode=False),
        }
    drums = drum_events(music, _ALL_DRUMS)
    return {
        "melody": {
            "note_count": len(notes),
            "pitch_range": pitch_range,
            "long_notes": sum(1 for n in notes if n.length >= _LONG_NOTE_SECONDS),
            "notes": [
                {
                    "time": round(n.start, 3),
                    "length": round(n.length, 3),
                    "midi": round(n.pitch),
                    "name": librosa.midi_to_note(round(n.pitch), unicode=False),
                    "strength": round(n.strength, 2),
                }
                for n in notes[:max_notes]
            ],
        },
        "drums": {kind: sum(1 for e in drums if e.kind == kind) for kind in _DRUM_KINDS},
    }


def music_facts(music: MusicFeatures, bpm: float, chart_source: str) -> dict[str, Any]:
    """Plain data of what was heard, saved next to a song so charts can be reviewed against it."""
    sung = np.array(music.vocal_onsets)
    melody_notes = []
    for note in music.melody:
        slot = _slot_of(note.start, music)
        if not 0 <= slot < music.n_slots:
            continue
        melody_notes.append(
            {
                "slot": slot,
                "length_slots": max(_slot_of(note.end, music) - slot, 0),
                "midi": round(note.pitch),
                "name": librosa.midi_to_note(round(note.pitch), unicode=False),
                "strength": round(note.strength, 2),
                "start_time": round(timing.refined_start(note.start, sung), 4),
                "end_time": round(note.end, 4),
            }
        )
    hits = drum_events(music, _ALL_DRUMS)
    reach = 0.6 * music.slot_seconds  # a drum hit is heard within this of its grid line
    drum_times: dict[str, list[float]] = {kind: [] for kind in _DRUM_KINDS}
    for event in hits:
        grid = music.first_beat_time + event.slot * music.slot_seconds
        band = np.array(music.drum_onsets[_DRUM_KINDS.index(event.kind)])
        exact = timing.nearest(band, grid, reach, reach)
        drum_times[event.kind].append(round(grid if exact is None else exact, 4))
    return {
        "version": 1,
        "chart_source": chart_source,
        "bpm": round(bpm, 3),
        "first_beat_time": round(music.first_beat_time, 4),
        "slot_seconds": music.slot_seconds,
        "n_slots": music.n_slots,
        "melody": melody_notes,
        "drums": {kind: [e.slot for e in hits if e.kind == kind] for kind in _DRUM_KINDS},
        "drum_times": drum_times,
    }
