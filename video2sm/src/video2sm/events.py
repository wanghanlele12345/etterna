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
# Drums this far under everything heard in a measure are separation leak, not a drummer:
# over whole measures, played drums sit 8-35 dB under the mix and leak 50 dB or more.
_DRUMS_PLAYING_DB = -40.0
# The melody follows whichever instrument is loudest in a measure. The voice is the default
# lead; the other instruments (strings, guitar, piano...) take over only when clearly louder
# than it, and only when they are really playing, not leaking: within this of the song's
# loudest measure.
_LEAD_MARGIN_DB = 3.0
_LEAD_AUDIBLE_DB = -40.0
# Harder charts also follow the second loudest melodic part: the one that is not leading,
# when it is within this of the lead. Further down it is background, not a part worth a key.
_SECOND_PART_DB = -6.0
_SECOND_PART_SCORE = 0.8  # of a lead note's, and with no lead priority: the lead wins a slot
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
    # (n_slots,): whether a drummer plays in the slot's measure; None = throughout
    drums_playing: np.ndarray | None = None
    # (n_slots,): whether the other instruments, not the voice, lead the slot's measure
    lead_other: np.ndarray | None = None
    # the second loudest melodic part (the voice under strings, or strings under the voice),
    # only where it is close to the lead; harder charts play it too
    second_melody: tuple[Note, ...] = ()
    second_onsets: tuple[float, ...] = ()


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
    """Read the lead melody and drum hits of separated stems onto the chart's grid.

    The melody is the voice's, except in measures where the other instruments are clearly
    louder (an instrumental intro, a string line between verses): there it is theirs.
    """
    drums = features.extract_grid_features(stems.drums, analysis)
    vocals = features.extract_grid_features(stems.vocals, analysis)
    first_beat = drums.first_beat_time
    measure_seconds = drums.slot_seconds * SLOTS_PER_MEASURE
    playing = drums_playing(stems, first_beat, measure_seconds, n_slots)
    playing_slots = np.repeat(playing, SLOTS_PER_MEASURE)[:n_slots]
    others_lead, others_second, voice_second = melodic_roles(stems, first_beat, measure_seconds, n_slots)
    lead_slots = np.repeat(others_lead, SLOTS_PER_MEASURE)[:n_slots]

    vocal_strengths = _fit(vocals.strengths.max(axis=1), n_slots)
    voice_notes = list(melody.transcribe(stems.vocals))
    voice_onsets = [float(t) for t in timing.onset_times(stems.vocals)]
    lead, lead_onsets = voice_notes, voice_onsets
    second: list[Note] = []
    second_onsets: list[float] = []
    if others_lead.any() or others_second.any():
        other_notes = list(melody.transcribe(stems.other))
        other_onsets = [float(t) for t in timing.onset_times(stems.other)]
        if others_lead.any():
            others = features.extract_grid_features(stems.other, analysis)
            vocal_strengths = np.where(lead_slots, _fit(others.strengths.max(axis=1), n_slots), vocal_strengths)
            lead = _by_lead(voice_notes, other_notes, others_lead, first_beat, measure_seconds, _start)
            lead_onsets = _by_lead(voice_onsets, other_onsets, others_lead, first_beat, measure_seconds, float)
        second = sorted(
            _in_measures(other_notes, others_second, first_beat, measure_seconds, _start)
            + _in_measures(voice_notes, voice_second, first_beat, measure_seconds, _start),
            key=_start,
        )
        second_onsets = sorted(
            _in_measures(other_onsets, others_second, first_beat, measure_seconds, float)
            + _in_measures(voice_onsets, voice_second, first_beat, measure_seconds, float)
        )
    return MusicFeatures(
        n_slots=n_slots,
        slot_seconds=drums.slot_seconds,
        first_beat_time=first_beat,
        drum_strengths=_fit(drums.strengths, n_slots) * playing_slots[:, None],
        vocal_strengths=vocal_strengths,
        melody=tuple(lead),
        vocal_onsets=tuple(lead_onsets),
        drum_onsets=tuple(
            _while_playing(band, playing, first_beat, measure_seconds) for band in band_onsets(stems.drums)
        ),
        drums_playing=playing_slots,
        lead_other=lead_slots,
        second_melody=tuple(second),
        second_onsets=tuple(second_onsets),
    )


def _start(note: Note) -> float:
    return note.start


def _measure_powers(
    audio, first_beat_time: float, measure_seconds: float, n_measures: int
) -> np.ndarray:
    """Mean power of the audio in each measure of the grid."""
    samples, rate = audio.samples, audio.sample_rate
    powers = np.zeros(n_measures)
    for m in range(n_measures):
        lo = max(0, int((first_beat_time + m * measure_seconds) * rate))
        hi = min(len(samples), int((first_beat_time + (m + 1) * measure_seconds) * rate))
        if hi > lo:
            powers[m] = float(np.mean(samples[lo:hi].astype(np.float64) ** 2))
    return powers


def melodic_roles(
    stems: Stems, first_beat_time: float, measure_seconds: float, n_slots: int
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per measure of the grid: (the others lead, the others are the second part, the voice is).

    The voice is the default lead. The `other` stem (strings, guitar, piano...) takes the
    measure when it is clearly louder than the voice and really playing, not a leak. The
    part that is not leading is the second part when it is within a few dB of the lead.
    """
    n_measures = -(-n_slots // SLOTS_PER_MEASURE)
    voice = _measure_powers(stems.vocals, first_beat_time, measure_seconds, n_measures)
    other = _measure_powers(stems.other, first_beat_time, measure_seconds, n_measures)
    mix = _measure_powers(stems.mixed(), first_beat_time, measure_seconds, n_measures)
    loudest = float(mix.max()) if n_measures else 0.0
    floor = loudest * 10 ** (_LEAD_AUDIBLE_DB / 10)
    voice_playing = (voice >= floor) & (loudest > 0)
    other_playing = (other >= floor) & (loudest > 0)
    others_lead = other_playing & (other > voice * 10 ** (_LEAD_MARGIN_DB / 10))
    close = 10 ** (_SECOND_PART_DB / 10)
    others_second = other_playing & ~others_lead & (other >= voice * close)
    voice_second = voice_playing & others_lead & (voice >= other * close)
    return others_lead, others_second, voice_second


def _measure_of(seconds: float, first_beat_time: float, measure_seconds: float) -> int:
    return int(np.floor((seconds - first_beat_time) / measure_seconds))


def _in_measures(items, wanted, first_beat_time, measure_seconds, time_of) -> list:
    """The items that fall in a measure marked in `wanted`."""
    kept = []
    for item in items:
        m = _measure_of(time_of(item), first_beat_time, measure_seconds)
        if 0 <= m < len(wanted) and wanted[m]:
            kept.append(item)
    return kept


def _by_lead(voice_items, other_items, other_leads, first_beat_time, measure_seconds, time_of) -> list:
    """The voice's items outside the measures the others lead, theirs inside, in time order."""

    def led_by_others(item) -> bool:
        m = _measure_of(time_of(item), first_beat_time, measure_seconds)
        return 0 <= m < len(other_leads) and bool(other_leads[m])

    kept = [i for i in voice_items if not led_by_others(i)] + [i for i in other_items if led_by_others(i)]
    return sorted(kept, key=time_of)


def drums_playing(
    stems: Stems, first_beat_time: float, measure_seconds: float, n_slots: int
) -> np.ndarray:
    """Per measure of the grid, whether a drummer is playing in it.

    Separation leaks a trace of every instrument into the drum stem, and onset strength is
    measured on a log scale, so in a drumless verse that leak reads as hits as crisp as
    real ones. Power over a whole measure (which the hits dominate) tells them apart.
    """
    n_measures = -(-n_slots // SLOTS_PER_MEASURE)
    drum = _measure_powers(stems.drums, first_beat_time, measure_seconds, n_measures)
    mix = _measure_powers(stems.mixed(), first_beat_time, measure_seconds, n_measures)
    ratio = np.divide(drum, mix, out=np.zeros(n_measures), where=mix > 0)
    return (mix > 0) & (10 * np.log10(np.maximum(ratio, 1e-12)) >= _DRUMS_PLAYING_DB)


def _while_playing(
    onsets, playing: np.ndarray, first_beat_time: float, measure_seconds: float
) -> tuple[float, ...]:
    """The onsets that fall in a measure where the drums play."""
    times = np.asarray(onsets, dtype=np.float64)
    index = np.floor((times - first_beat_time) / measure_seconds).astype(np.int64)
    inside = (index >= 0) & (index < len(playing))
    keep = np.zeros(len(times), dtype=bool)
    keep[inside] = playing[index[inside]]
    return tuple(float(t) for t in times[keep])


def band_onsets(audio) -> tuple[tuple[float, ...], ...]:
    """Exact attack times in the kick, snare and hi-hat bands."""
    return tuple(tuple(timing.onset_times(audio, fmin, fmax)) for fmin, fmax in features.BANDS_HZ)


def pitch_lanes(notes: list[Note], columns: int, reference: list[Note] | None = None) -> list[float]:
    """Map each note's pitch to a lane: higher notes sit further right.

    The scale runs from the 5th to the 95th percentile of the melody's pitches (those of
    `reference` when given, so a second part shares the lead's keyboard), so a few stray
    notes do not squash the rest into the middle of the keyboard.
    """
    if not notes:
        return []
    pitches = np.array([n.pitch for n in notes])
    scale = np.array([n.pitch for n in reference]) if reference else pitches
    low = float(np.percentile(scale, _PITCH_LOW_PERCENTILE))
    high = float(np.percentile(scale, _PITCH_HIGH_PERCENTILE))
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
    found = _part_events(music.melody, music.melody, music, profile, columns, 1.0, _MELODY_PRIORITY)
    if profile.melodic_parts >= 2:
        # the second part plays on the lead's keyboard, and never outbids the lead for a slot
        scale = music.melody or music.second_melody
        found += _part_events(
            music.second_melody, scale, music, profile, columns, _SECOND_PART_SCORE, 0.0
        )
    return found


def _part_events(
    notes: tuple[Note, ...], scale: tuple[Note, ...], music: MusicFeatures, profile: Profile,
    columns: int, weight: float, priority: float,
) -> list[Event]:
    lanes = pitch_lanes(list(notes), columns, list(scale))
    found = []
    for note, lane in zip(notes, lanes):
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
                score=profile.melody_weight * score * weight + priority,
                lane=lane,
                length_slots=length,
            )
        )
    return found


def _drum_hits(strengths: np.ndarray, playing: np.ndarray | None = None) -> np.ndarray:
    """Per band, 0..1 where 0 is the band's noise floor (its median) and 1 its loud hits.

    Onset strength is never near zero in real music, so a fixed threshold would call the
    background hum a hit; measuring from each band's own floor keeps only real peaks.
    The floor is taken only where the drums play (`playing`, per slot): a long drumless
    stretch would otherwise drag it down and turn the flux between real hits into hits.
    """
    playing = np.ones(len(strengths), dtype=bool) if playing is None else playing[: len(strengths)]
    if not playing.any():
        return np.zeros_like(strengths)
    floor = np.median(strengths[playing], axis=0)
    peak = np.maximum(
        np.percentile(strengths[playing], _DRUM_PEAK_PERCENTILE, axis=0), _MIN_DRUM_PEAK
    )
    span = peak - floor  # a band whose floor is already its peak has no hits standing out
    hits = np.clip((strengths - floor) / np.where(span > 0, span, np.inf), 0.0, 1.0)
    return np.where((hits >= _MIN_DRUM_HIT) & playing[:, None], hits, 0.0)


def drum_events(music: MusicFeatures, profile: Profile) -> list[Event]:
    weights = np.array([profile.kick_weight, profile.snare_weight, profile.hat_weight])
    scored = _drum_hits(music.drum_strengths[: music.n_slots], music.drums_playing) * weights
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


def _melody_facts(notes, onsets: np.ndarray, music: MusicFeatures) -> list[dict[str, Any]]:
    facts = []
    for note in notes:
        slot = _slot_of(note.start, music)
        if not 0 <= slot < music.n_slots:
            continue
        facts.append(
            {
                "slot": slot,
                "length_slots": max(_slot_of(note.end, music) - slot, 0),
                "midi": round(note.pitch),
                "name": librosa.midi_to_note(round(note.pitch), unicode=False),
                "strength": round(note.strength, 2),
                "start_time": round(timing.refined_start(note.start, onsets), 4),
                "end_time": round(note.end, 4),
            }
        )
    return facts


def music_facts(music: MusicFeatures, bpm: float, chart_source: str) -> dict[str, Any]:
    """Plain data of what was heard, saved next to a song so charts can be reviewed against it."""
    melody_notes = _melody_facts(music.melody, np.array(music.vocal_onsets), music)
    second_notes = _melody_facts(music.second_melody, np.array(music.second_onsets), music)
    hits = drum_events(music, _ALL_DRUMS)
    reach = 0.6 * music.slot_seconds  # a drum hit is heard within this of its grid line
    drum_times: dict[str, list[float]] = {kind: [] for kind in _DRUM_KINDS}
    for event in hits:
        grid = music.first_beat_time + event.slot * music.slot_seconds
        band = np.array(music.drum_onsets[_DRUM_KINDS.index(event.kind)])
        exact = timing.nearest(band, grid, reach, reach)
        drum_times[event.kind].append(round(grid if exact is None else exact, 4))
    facts = {
        "version": 1,
        "chart_source": chart_source,
        "bpm": round(bpm, 3),
        "first_beat_time": round(music.first_beat_time, 4),
        "slot_seconds": music.slot_seconds,
        "n_slots": music.n_slots,
        "melody": melody_notes,
        "second_melody": second_notes,
        "drums": {kind: [e.slot for e in hits if e.kind == kind] for kind in _DRUM_KINDS},
        "drum_times": drum_times,
    }
    if music.lead_other is not None:
        facts["lead"] = [
            "other" if music.lead_other[slot] else "vocals"
            for slot in range(0, music.n_slots, SLOTS_PER_MEASURE)
        ]
    return facts
