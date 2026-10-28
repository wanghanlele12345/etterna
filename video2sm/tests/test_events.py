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


def test_a_long_drumless_stretch_does_not_lower_the_bar_for_hits() -> None:
    import dataclasses

    # no drummer for three quarters of the song; where one plays, the flux between
    # the hits is still background, not more hits
    drums = np.zeros((N_SLOTS, 3))
    start = 3 * N_SLOTS // 4
    drums[start:, 0] = 0.9
    drums[start::4, 0] = 1.8
    playing = np.arange(N_SLOTS) >= start
    m = dataclasses.replace(music(drums=drums), drums_playing=playing)
    found = events.drum_events(m, PROFILES["Challenge"])
    assert found and all(e.slot % 4 == 0 for e in found)


def test_no_drum_hits_where_no_drummer_plays() -> None:
    import dataclasses

    drums = drum_hits(kick=[0, 16, 48], snare=[8, 40])
    playing = np.arange(N_SLOTS) >= 32
    m = dataclasses.replace(music(drums=drums), drums_playing=playing)
    assert {(e.slot, e.kind) for e in events.drum_events(m, PROFILES["Challenge"])} == {
        (48, "kick"), (40, "snare")
    }


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


def with_drum_gain(stems_, gain):
    """The same stems with the drums scaled sample by sample."""
    import dataclasses

    from video2sm import dsp

    drums = dsp.Audio(samples=(stems_.drums.samples * gain).astype(np.float32), sample_rate=stems_.drums.sample_rate)
    return dataclasses.replace(stems_, drums=drums)


def stem_music(click_wav, stems_):
    from video2sm import beats, dsp, features

    mix = dsp.load_audio(click_wav)
    analysis = beats.analyze_beats(mix)
    n_slots = features.extract_grid_features(mix, analysis).n_slots
    return events.music_from_stems(stems_, analysis, n_slots)


def test_drums_buried_far_under_the_music_are_stem_bleed(click_wav, vocal_wav) -> None:
    # Separation leaks a trace of the mix into the drum stem. In the first half the drums
    # sit 60 dB under the singing: that is leak, not a drummer, however crisp it looks
    # on a log-scale onset envelope.
    stems_ = synthetic_stems(click_wav, vocal_wav)
    half = len(stems_.drums.samples) // 2
    gain = np.ones_like(stems_.drums.samples)
    gain[:half] = 10 ** (-60 / 20)
    found = stem_music(click_wav, with_drum_gain(stems_, gain))

    half_time = half / stems_.drums.sample_rate
    measure = SLOTS_PER_MEASURE * found.slot_seconds  # the measure straddling the change may count
    hit_times = [
        found.first_beat_time + e.slot * found.slot_seconds
        for e in events.drum_events(found, PROFILES["Challenge"])
    ]
    assert min(hit_times) > half_time - measure
    assert sum(t > half_time for t in hit_times) >= 30
    for band in found.drum_onsets:
        assert band and min(band) > half_time - measure
    assert len(found.melody) >= 60  # the singing is untouched


def test_a_soft_drum_part_still_counts(click_wav, vocal_wav) -> None:
    stems_ = synthetic_stems(click_wav, vocal_wav)
    soft = with_drum_gain(stems_, np.full_like(stems_.drums.samples, 10 ** (-25 / 20)))
    found = stem_music(click_wav, soft)
    kicks = [e for e in events.drum_events(found, PROFILES["Challenge"]) if e.kind == "kick"]
    assert len(kicks) >= 60
    assert len(found.drum_onsets[0]) >= 60


# --- the loudest instrument leads ----------------------------------------------------------

LEAD_NOTE_MIDI = 76.0  # far above anything the vocal track sings (57..70.5)


def other_track(first_second: float, gain: float = 0.5) -> np.ndarray:
    """One steady note per beat from `first_second` on: the strings under (or instead of) the voice."""
    from tests.conftest import DURATION, SAMPLE_RATE, TRUE_BPM, TRUE_FIRST_BEAT, VOCAL_NOTE_SECONDS

    signal = np.zeros(int(DURATION * SAMPLE_RATE), dtype=np.float32)
    t = np.arange(int(VOCAL_NOTE_SECONDS * SAMPLE_RATE)) / SAMPLE_RATE
    hz = 440.0 * 2 ** ((LEAD_NOTE_MIDI - 69.0) / 12.0)
    fade = np.minimum(1.0, np.minimum(t, VOCAL_NOTE_SECONDS - t) / 0.02)
    tone = (gain * np.sin(2 * np.pi * hz * t) * fade).astype(np.float32)
    beat = 0
    while True:
        start = TRUE_FIRST_BEAT + beat * 60.0 / TRUE_BPM
        if start + VOCAL_NOTE_SECONDS + 0.05 >= DURATION:
            break
        if start >= first_second:
            index = int(start * SAMPLE_RATE)
            signal[index : index + len(t)] += tone
        beat += 1
    return signal


def lead_stems(click_wav, vocal_wav, other: np.ndarray, vocal_gain_after_half: float = 1.0):
    """Stems with the voice singing throughout (quieter after the half, if asked) and `other` beside it."""
    import dataclasses

    from video2sm import dsp

    base = synthetic_stems(click_wav, vocal_wav)
    gain = np.ones_like(base.vocals.samples)
    gain[len(gain) // 2 :] = vocal_gain_after_half
    vocals = dsp.Audio(samples=(base.vocals.samples * gain).astype(np.float32), sample_rate=base.vocals.sample_rate)
    other_audio = dsp.Audio(samples=other, sample_rate=base.vocals.sample_rate)
    return dataclasses.replace(base, vocals=vocals, other=other_audio)


def test_the_melody_follows_whichever_instrument_is_loudest(click_wav, vocal_wav) -> None:
    from tests.conftest import DURATION

    half = DURATION / 2
    # the voice sings the first half, then drops 40 dB while the strings carry on loudly
    stems_ = lead_stems(click_wav, vocal_wav, other_track(first_second=half), vocal_gain_after_half=0.01)
    found = stem_music(click_wav, stems_)

    measure = SLOTS_PER_MEASURE * found.slot_seconds
    early = [n for n in found.melody if n.start < half - measure]
    late = [n for n in found.melody if n.start > half + measure]
    assert len(early) >= 20 and len(late) >= 20
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) > 3 for n in early)  # the voice
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) < 0.6 for n in late)  # the strings
    # exact attacks come from the leading instrument too
    assert any(t > half + measure for t in found.vocal_onsets)
    assert found.lead_other is not None and len(found.lead_other) == found.n_slots
    assert not found.lead_other[: found.n_slots // 4].any() and found.lead_other[-found.n_slots // 4 :].all()


def test_the_voice_keeps_the_lead_unless_the_others_are_clearly_louder(click_wav, vocal_wav) -> None:
    # the same note positions, the other instrument 1.5 dB louder: not enough to take over
    stems_ = lead_stems(click_wav, vocal_wav, other_track(first_second=0.0, gain=0.5 * 10 ** (1.5 / 20)))
    found = stem_music(click_wav, stems_)
    assert len(found.melody) >= 60
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) > 3 for n in found.melody)
    assert found.lead_other is not None and not found.lead_other.any()


def test_a_leak_into_the_other_stem_never_leads(click_wav, vocal_wav) -> None:
    from tests.conftest import DURATION

    # after the half the voice is silent and the "other" stem holds only a 60 dB-down trace
    half = DURATION / 2
    stems_ = lead_stems(
        click_wav, vocal_wav, other_track(first_second=half, gain=0.5 * 10 ** (-60 / 20)),
        vocal_gain_after_half=0.0,
    )
    found = stem_music(click_wav, stems_)
    assert found.lead_other is not None and not found.lead_other.any()
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) > 3 for n in found.melody)


# --- a second melodic part on harder charts ------------------------------------------------


def two_part_music():
    import dataclasses

    lead = [note(i * 8, 2, 62 + (i % 4)) for i in range(8)]  # on slots 0, 8, 16, ...
    second = [note(i * 8 + 4, 2, 50 + (i % 3)) for i in range(8)]  # between them
    return dataclasses.replace(music(lead), second_melody=tuple(second))


def test_harder_charts_also_follow_the_second_loudest_part() -> None:
    m = two_part_music()
    medium = events.melody_events(m, PROFILES["Medium"], columns=7)
    hard = events.melody_events(m, PROFILES["Hard"], columns=7)
    assert {e.slot for e in medium} == {i * 8 for i in range(8)}
    assert {e.slot for e in hard} == {i * 8 for i in range(8)} | {i * 8 + 4 for i in range(8)}


def test_the_second_part_sits_where_its_pitch_does_on_the_leads_keyboard() -> None:
    m = two_part_music()  # lead 62..65; the second part sings well below it
    hard = events.melody_events(m, PROFILES["Hard"], columns=7)
    second = [e for e in hard if e.slot % 8 == 4]
    lead = [e for e in hard if e.slot % 8 == 0]
    assert all(e.lane == 0.0 for e in second)  # below the lead's whole range: the lowest lane
    assert max(e.lane for e in lead) == pytest.approx(6.0, abs=0.01)


def test_the_lead_wins_a_slot_both_parts_want() -> None:
    import dataclasses

    m = dataclasses.replace(
        music([note(8, 2, 64)]), second_melody=(note(8, 2, 50),)
    )
    chosen = events.select_events(m, PROFILES["Hard"], columns=7)
    (event,) = [e for e in chosen if e.slot == 8]
    assert event.lane != 0.0 or event.score > 0  # still one event...
    lead_only = events.melody_events(dataclasses.replace(m, second_melody=()), PROFILES["Hard"], 7)
    assert event.score == pytest.approx(lead_only[0].score)  # ...and it is the lead's


def test_second_part_is_the_quieter_instrument_within_six_decibels(click_wav, vocal_wav) -> None:
    # the voice leads; the strings are 4 dB under it: close enough to be a second part
    close = lead_stems(click_wav, vocal_wav, other_track(0.0, gain=0.5 * 10 ** (-4 / 20)))
    found = stem_music(click_wav, close)
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) > 3 for n in found.melody)
    assert len(found.second_melody) >= 60
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) < 0.6 for n in found.second_melody)
    assert len(found.second_onsets) >= 60

    # 12 dB under: background, not a part worth a key
    far = lead_stems(click_wav, vocal_wav, other_track(0.0, gain=0.5 * 10 ** (-12 / 20)))
    assert stem_music(click_wav, far).second_melody == ()


def test_when_the_strings_lead_the_voice_is_the_second_part(click_wav, vocal_wav) -> None:
    loud_strings = lead_stems(click_wav, vocal_wav, other_track(0.0, gain=0.5 * 10 ** (4 / 20)))
    found = stem_music(click_wav, loud_strings)
    on_the_grid = [
        n for n in found.melody if 0 <= (n.start - found.first_beat_time) / found.slot_seconds < found.n_slots
    ]  # notes before the first beat or past the last whole measure never reach a chart
    assert len(on_the_grid) >= 60
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) < 0.6 for n in on_the_grid)
    assert len(found.second_melody) >= 60
    assert all(abs(n.pitch - LEAD_NOTE_MIDI) > 3 for n in found.second_melody)


def test_music_facts_list_the_second_part_apart_from_the_melody() -> None:
    m = two_part_music()
    facts = events.music_facts(m, bpm=137.7, chart_source="stems")
    assert len(facts["melody"]) == 8 and len(facts["second_melody"]) == 8
    assert facts["second_melody"][0]["slot"] == 4 and facts["second_melody"][0]["midi"] == 50
    assert events.music_facts(music(), bpm=137.7, chart_source="stems")["second_melody"] == []


def test_music_facts_say_who_leads_each_measure() -> None:
    import dataclasses

    lead = np.arange(N_SLOTS) >= N_SLOTS // 2  # the second half of the song is led by the others
    m = dataclasses.replace(music([note(8, 4, 62.2)]), lead_other=lead)
    facts = events.music_facts(m, bpm=137.7, chart_source="stems")
    measures = N_SLOTS // SLOTS_PER_MEASURE
    assert facts["lead"] == ["vocals"] * (measures // 2) + ["other"] * (measures // 2)
    assert "lead" not in events.music_facts(music(), bpm=137.7, chart_source="stems")


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
