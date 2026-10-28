import numpy as np
import pytest

from video2sm import charting, events
from video2sm.features import SLOTS_PER_MEASURE
from video2sm.melody import Note

SLOT_SECONDS = 0.1
FIRST_BEAT = 0.0
N_SLOTS = 16 * SLOTS_PER_MEASURE
PROFILES = {p.name: p for p in charting.PROFILES}


def note(slot: float, slots: float, pitch: float, strength: float = 1.0) -> Note:
    return Note(FIRST_BEAT + slot * SLOT_SECONDS, FIRST_BEAT + (slot + slots) * SLOT_SECONDS, pitch, strength)


def music(notes=(), drums=None, vocals=None) -> events.MusicFeatures:
    return events.MusicFeatures(
        n_slots=N_SLOTS,
        slot_seconds=SLOT_SECONDS,
        first_beat_time=FIRST_BEAT,
        drum_strengths=drums if drums is not None else np.zeros((N_SLOTS, 3)),
        vocal_strengths=vocals if vocals is not None else np.zeros(N_SLOTS),
        melody=tuple(notes),
    )


# --- pitch to lane -----------------------------------------------------------------------


def test_pitch_lanes_span_the_whole_keyboard_in_order() -> None:
    notes = [note(i * 4, 3, 55 + i) for i in range(20)]
    lanes = events.pitch_lanes(notes, columns=7)
    assert lanes == sorted(lanes)
    assert lanes[0] == pytest.approx(0.0, abs=0.01) and lanes[-1] == pytest.approx(6.0, abs=0.01)


def test_pitch_lanes_ignore_a_few_outliers() -> None:
    notes = [note(i * 4, 3, 60 + (i % 5)) for i in range(40)] + [note(200, 3, 30)]
    lanes = events.pitch_lanes(notes, columns=7)
    assert lanes[-1] == 0.0  # the outlier is clamped to the lowest lane, not stretching the scale
    assert max(lanes[:40]) > 5  # the real melody still reaches the top lanes


def test_pitch_lanes_of_a_monotone_melody_sit_in_the_middle() -> None:
    notes = [note(i * 4, 3, 62.0) for i in range(10)]
    assert set(events.pitch_lanes(notes, columns=7)) == {3.0}


# --- melody events -----------------------------------------------------------------------


def test_melody_note_becomes_an_event_on_its_slot() -> None:
    m = music([note(8, 4, 60)])
    found = events.melody_events(m, PROFILES["Hard"], columns=7)
    assert [(e.slot, e.kind, e.length_slots) for e in found] == [(8, "melody", 4)]


def test_melody_onsets_snap_to_positions_the_difficulty_allows() -> None:
    # Easy only allows on-beat and eighth positions (slot % 4 in 0, 2); a note on the 16th snaps
    m = music([note(9, 2, 60)])
    (event,) = events.melody_events(m, PROFILES["Easy"], columns=7)
    assert event.slot in (8, 10)


def test_snapping_prefers_the_stronger_vocal_attack() -> None:
    vocals = np.zeros(N_SLOTS)
    vocals[10] = 1.0
    m = music([note(9, 2, 60)], vocals=vocals)
    (event,) = events.melody_events(m, PROFILES["Easy"], columns=7)
    assert event.slot == 10


def test_longer_and_louder_notes_score_higher() -> None:
    m = music([note(0, 1, 60, 0.4), note(16, 1, 60, 1.0), note(32, 8, 60, 1.0)])
    quiet, loud, long = events.melody_events(m, PROFILES["Hard"], columns=7)
    assert quiet.score < loud.score < long.score


def test_notes_outside_the_song_grid_are_ignored() -> None:
    m = music([note(-5, 2, 60), note(N_SLOTS + 4, 2, 60)])
    assert events.melody_events(m, PROFILES["Hard"], columns=7) == []


# --- drum events -------------------------------------------------------------------------


def drum_hits(**hits) -> np.ndarray:
    strengths = np.zeros((N_SLOTS, 3))
    for name, slots in hits.items():
        column = {"kick": 0, "snare": 1, "hat": 2}[name]
        for slot in slots:
            strengths[slot, column] = 1.0
    return strengths


def test_drum_hits_are_classified_by_band() -> None:
    m = music(drums=drum_hits(kick=[0, 16], snare=[8], hat=[4, 12]))
    found = events.drum_events(m, PROFILES["Challenge"])
    assert {(e.slot, e.kind) for e in found} == {
        (0, "kick"), (16, "kick"), (8, "snare"), (4, "hat"), (12, "hat")
    }


def test_easier_difficulties_leave_out_the_busy_drums() -> None:
    m = music(drums=drum_hits(kick=[0, 16], snare=[8], hat=[4, 12]))
    beginner = {e.kind for e in events.drum_events(m, PROFILES["Beginner"])}
    assert beginner == {"kick"}
    hard = {e.kind for e in events.drum_events(m, PROFILES["Hard"])}
    assert {"kick", "snare"} <= hard


def test_faint_drum_noise_is_ignored() -> None:
    drums = np.full((N_SLOTS, 3), 0.1)
    assert events.drum_events(music(drums=drums), PROFILES["Challenge"]) == []


# --- selection ---------------------------------------------------------------------------


def test_selection_respects_the_density_target() -> None:
    notes = [note(i * 2, 1, 55 + (i % 12)) for i in range(60)]
    drums = drum_hits(kick=list(range(0, N_SLOTS, 4)), snare=list(range(2, N_SLOTS, 8)))
    m = music(notes, drums=drums)
    profile = PROFILES["Easy"]
    chosen = events.select_events(m, profile, columns=7)
    seconds = N_SLOTS * SLOT_SECONDS
    assert len(chosen) <= profile.target_rows_per_second * seconds * 1.1
    assert chosen == sorted(chosen, key=lambda e: e.slot)


def test_selection_keeps_the_melody_ahead_of_the_drums() -> None:
    notes = [note(i * 8, 4, 55 + i) for i in range(12)]
    drums = drum_hits(kick=list(range(0, N_SLOTS, 4)))
    chosen = events.select_events(music(notes, drums=drums), PROFILES["Beginner"], columns=7)
    melody_slots = {e.slot for e in chosen if e.kind == "melody"}
    assert len(melody_slots) >= 8  # the vocal line survives even when the kicks compete for room


def test_selection_enforces_the_minimum_gap() -> None:
    notes = [note(i, 1, 60 + (i % 7)) for i in range(0, 60)]
    profile = PROFILES["Beginner"]
    chosen = events.select_events(music(notes), profile, columns=7)
    slots = [e.slot for e in chosen]
    assert all(b - a >= profile.min_gap_slots for a, b in zip(slots, slots[1:]))


def test_coinciding_melody_and_drum_merge_into_one_event_with_a_partner() -> None:
    m = music([note(8, 2, 60)], drums=drum_hits(kick=[8]))
    chosen = events.select_events(m, PROFILES["Hard"], columns=7)
    (merged,) = [e for e in chosen if e.slot == 8]
    assert merged.kind == "melody" and merged.partner == "kick"


def test_silence_gives_no_events() -> None:
    assert events.select_events(music(), PROFILES["Hard"], columns=7) == []


# --- from separated stems ------------------------------------------------------------------


def synthetic_stems(click_wav, vocal_wav):
    from video2sm import dsp, stems

    drums = dsp.load_audio(click_wav)
    silent = dsp.Audio(samples=np.zeros_like(drums.samples), sample_rate=drums.sample_rate)
    return stems.Stems(vocals=dsp.load_audio(vocal_wav), drums=drums, bass=silent, other=silent)


def test_music_features_from_stems(click_wav, vocal_wav) -> None:
    from tests.conftest import TRUE_BPM, TRUE_FIRST_BEAT, vocal_pitch
    from video2sm import beats, dsp, features

    mix = dsp.load_audio(click_wav)
    analysis = beats.analyze_beats(mix)
    grid = features.extract_grid_features(mix, analysis)
    found = events.music_from_stems(synthetic_stems(click_wav, vocal_wav), analysis, grid.n_slots)

    assert found.n_slots == grid.n_slots
    assert found.slot_seconds == pytest.approx(60.0 / analysis.bpm / 4)
    # kicks on the beat, hi-hats on the off-eighth
    beat_slots = np.arange(0, found.n_slots, 4)
    off_slots = np.arange(2, found.n_slots, 4)
    assert found.drum_strengths[beat_slots, 0].mean() > found.drum_strengths[off_slots, 0].mean()
    assert found.drum_strengths[off_slots, 2].mean() > found.drum_strengths[beat_slots, 2].mean()
    drum_events = events.drum_events(found, PROFILES["Challenge"])
    kicks = [e.slot for e in drum_events if e.kind == "kick"]
    # the click track's second hit is a broadband burst, so it may read as snare or hi-hat
    offbeat = [e.slot for e in drum_events if e.kind != "kick"]
    assert len(kicks) >= 60 and sum(s % 4 == 0 for s in kicks) / len(kicks) > 0.9
    assert len(offbeat) >= 60 and sum(s % 4 == 2 for s in offbeat) / len(offbeat) > 0.9
    # one sung note per beat, on pitch
    assert len(found.melody) >= 60
    for index in (0, 5, 12):
        n = found.melody[index]
        assert n.pitch == pytest.approx(vocal_pitch(index), abs=0.4)
        assert n.start == pytest.approx(TRUE_FIRST_BEAT + index * 60.0 / TRUE_BPM, abs=0.06)
    assert found.vocal_strengths[beat_slots].mean() > 3 * found.vocal_strengths[off_slots].mean()
    # exact attack times, for aligning notes to the audio
    beat_times = TRUE_FIRST_BEAT + np.arange(60) * 60.0 / TRUE_BPM
    sung = np.array(found.vocal_onsets)
    assert len(sung) >= 60
    assert np.median([np.min(np.abs(sung - b)) for b in beat_times]) < 0.015
    kicks_heard = np.array(found.drum_onsets[0])
    assert np.median([np.min(np.abs(kicks_heard - b)) for b in beat_times]) < 0.015


def test_music_features_pad_or_trim_to_the_chart_grid(click_wav, vocal_wav) -> None:
    from video2sm import beats, dsp

    analysis = beats.analyze_beats(dsp.load_audio(click_wav))
    stems_ = synthetic_stems(click_wav, vocal_wav)
    short = events.music_from_stems(stems_, analysis, 100)
    long = events.music_from_stems(stems_, analysis, 5000)
    assert short.drum_strengths.shape == (100, 3) and short.vocal_strengths.shape == (100,)
    assert long.drum_strengths.shape == (5000, 3) and long.vocal_strengths.shape == (5000,)


# --- describing the music -------------------------------------------------------------------


def test_describe_music_summarises_melody_and_drums() -> None:
    notes = [note(i * 8, 6 if i % 2 else 1, 60 + i) for i in range(10)]  # 0.6 s or 0.1 s long
    m = music(notes, drums=drum_hits(kick=[0, 16, 32], snare=[8, 24], hat=[4]))
    report = events.describe_music(m, max_notes=4)
    melody_part = report["melody"]
    assert melody_part["note_count"] == 10
    assert melody_part["pitch_range"] == {"low": "C4", "high": "A4"}
    assert melody_part["long_notes"] == 5  # notes of half a second or more
    assert len(melody_part["notes"]) == 4
    first = melody_part["notes"][0]
    assert set(first) == {"time", "length", "midi", "name", "strength"}
    assert first["name"] == "C4" and first["midi"] == 60
    assert report["drums"] == {"kick": 3, "snare": 2, "hat": 1}


def test_describe_music_without_a_melody() -> None:
    report = events.describe_music(music(drums=drum_hits(kick=[0])), max_notes=10)
    assert report["melody"] == {"note_count": 0, "pitch_range": None, "long_notes": 0, "notes": []}


# --- facts saved next to a song ----------------------------------------------------------------


def test_music_facts_are_plain_json_data() -> None:
    import json

    notes = [note(8, 4, 62.2), note(24, 1, 65.0)]
    m = music(notes, drums=drum_hits(kick=[0, 16], snare=[8], hat=[4]))
    facts = events.music_facts(m, bpm=137.7, chart_source="stems")
    assert json.loads(json.dumps(facts)) == facts
    assert facts["bpm"] == 137.7 and facts["chart_source"] == "stems"
    assert facts["slot_seconds"] == SLOT_SECONDS and facts["n_slots"] == N_SLOTS
    assert facts["melody"][0] == {
        "slot": 8, "length_slots": 4, "midi": 62, "name": "D4", "strength": 1.0,
        "start_time": 0.8, "end_time": 1.2,  # no attacks known: the tracker's own times
    }
    assert facts["drums"] == {"kick": [0, 16], "snare": [8], "hat": [4]}
    assert facts["drum_times"] == {"kick": [0.0, 1.6], "snare": [0.8], "hat": [0.4]}


def test_music_facts_carry_exact_attack_times() -> None:
    import dataclasses

    m = dataclasses.replace(
        music([note(8, 4, 62.2)], drums=drum_hits(kick=[16])),
        vocal_onsets=(0.77,),  # the singer started 30 ms before the tracker noticed
        drum_onsets=((1.62,), (), ()),  # the kick landed 20 ms after the grid line
    )
    facts = events.music_facts(m, bpm=150.0, chart_source="stems")
    assert facts["melody"][0]["start_time"] == pytest.approx(0.77)
    assert facts["drum_times"]["kick"] == [pytest.approx(1.62)]


def test_music_facts_skip_notes_off_the_grid() -> None:
    m = music([note(-3, 2, 60), note(N_SLOTS + 1, 2, 60), note(10, 2, 60)])
    assert [n["slot"] for n in events.music_facts(m, 120.0, "stems")["melody"]] == [10]
