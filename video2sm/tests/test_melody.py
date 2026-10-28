import numpy as np
import pytest

from video2sm import dsp, melody

HOP = 0.01


def frames(segments, total=2.4):
    """Build (times, midi, rms) frame arrays from [(start, end, midi_or_None)] segments."""
    times = np.arange(0.0, total, HOP)
    midi = np.full(len(times), np.nan)
    rms = np.full(len(times), 0.0)
    for start, end, pitch in segments:
        mask = (times >= start) & (times < end)
        if pitch is not None:
            midi[mask] = pitch
            rms[mask] = 0.5
    return times, midi, rms


def test_segments_notes_at_pitch_changes_and_gaps() -> None:
    times, midi, rms = frames([(0.2, 0.6, 60.0), (0.6, 1.0, 64.0), (1.2, 1.9, 67.0)])
    notes = melody.segment_notes(times, midi, rms)
    assert len(notes) == 3
    assert [round(n.pitch) for n in notes] == [60, 64, 67]
    assert [round(n.start, 2) for n in notes] == [0.2, 0.6, 1.2]
    assert [round(n.end, 1) for n in notes] == [0.6, 1.0, 1.9]


def test_vibrato_does_not_split_a_note() -> None:
    times, midi, rms = frames([(0.2, 1.4, 62.0)])
    mask = ~np.isnan(midi)
    midi[mask] += 0.35 * np.sin(2 * np.pi * 5.5 * times[mask])
    notes = melody.segment_notes(times, midi, rms)
    assert len(notes) == 1
    assert notes[0].pitch == pytest.approx(62.0, abs=0.2)


def test_short_dropout_is_bridged() -> None:
    times, midi, rms = frames([(0.2, 0.7, 60.0), (0.73, 1.2, 60.0)])
    assert len(melody.segment_notes(times, midi, rms)) == 1


def test_blips_shorter_than_a_syllable_are_dropped() -> None:
    times, midi, rms = frames([(0.3, 0.35, 60.0), (0.8, 1.4, 64.0)])
    notes = melody.segment_notes(times, midi, rms)
    assert [round(n.pitch) for n in notes] == [64]


def test_strength_is_relative_loudness() -> None:
    times, midi, rms = frames([(0.2, 0.7, 60.0), (1.0, 1.5, 64.0)])
    rms[(times >= 1.0) & (times < 1.5)] = 0.25  # half as loud
    loud, quiet = melody.segment_notes(times, midi, rms)
    assert loud.strength == pytest.approx(1.0, abs=0.01)
    assert quiet.strength == pytest.approx(0.5, abs=0.05)


def test_clean_drops_notes_far_from_the_melody_register() -> None:
    notes = [
        melody.Note(1.0, 1.5, 62.0, 1.0),
        melody.Note(2.0, 2.5, 64.0, 1.0),
        melody.Note(3.0, 3.5, 60.0, 1.0),
        melody.Note(4.0, 4.4, 37.0, 1.0),  # bass bleeding into the vocal stem
        melody.Note(5.0, 5.4, 63.0, 0.05),  # barely audible
    ]
    kept = melody.clean_notes(notes)
    assert [round(n.pitch) for n in kept] == [62, 64, 60]


def test_clean_keeps_everything_when_there_are_too_few_to_judge() -> None:
    notes = [melody.Note(1.0, 1.5, 62.0, 1.0), melody.Note(2.0, 2.5, 40.0, 1.0)]
    assert melody.clean_notes(notes) == notes


def sine_melody(parts, sr=dsp.SAMPLE_RATE):
    out = []
    for hz, seconds in parts:
        n = int(seconds * sr)
        t = np.arange(n) / sr
        tone = np.sin(2 * np.pi * hz * t) if hz else np.zeros(n)
        fade = np.minimum(1.0, np.minimum(t, seconds - t) / 0.03)
        out.append((0.6 * tone * fade).astype(np.float32))
    return dsp.Audio(samples=np.concatenate(out), sample_rate=sr)


def test_transcribes_a_synthetic_melody() -> None:
    audio = sine_melody([(0, 0.5), (440.0, 0.6), (523.25, 0.6), (0, 0.3), (659.26, 0.7), (0, 0.3)])
    notes = melody.transcribe(audio)
    assert [round(n.pitch) for n in notes] == [69, 72, 76]  # A4, C5, E5
    starts = [n.start for n in notes]
    assert starts == pytest.approx([0.5, 1.1, 2.0], abs=0.07)
    assert notes[2].end - notes[2].start == pytest.approx(0.7, abs=0.1)


def test_transcribe_silence_gives_no_notes() -> None:
    audio = dsp.Audio(samples=np.zeros(dsp.SAMPLE_RATE * 2, dtype=np.float32), sample_rate=dsp.SAMPLE_RATE)
    assert melody.transcribe(audio) == []
