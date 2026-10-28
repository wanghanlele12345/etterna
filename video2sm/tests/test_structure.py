import numpy as np
import pytest

from video2sm import structure

N_PER = 8


def blocks(*vectors, noise=0.02, seed=0):
    rng = np.random.default_rng(seed)
    cols = []
    for vec in vectors:
        for _ in range(N_PER):
            cols.append(np.asarray(vec, dtype=float) + rng.normal(0, noise, len(vec)))
    return np.stack(cols, axis=1)  # (features, measures)


A, B, C = [1.0, 0.0, 0.0, 0.2], [0.0, 1.0, 0.0, 0.8], [0.0, 0.0, 1.0, 0.5]


def test_sections_split_where_the_sound_changes() -> None:
    found = structure.sections_from_features(blocks(A, B, A), count=3)
    assert [(s.start, s.end) for s in found] == [(0, 7), (8, 15), (16, 23)]


def test_repeated_sounds_share_a_label() -> None:
    found = structure.sections_from_features(blocks(A, B, A, C), count=4)
    assert [s.label for s in found] == ["A", "B", "A", "C"]


def test_labels_are_assigned_in_order_of_first_appearance() -> None:
    found = structure.sections_from_features(blocks(C, A, C), count=3)
    assert [s.label for s in found] == ["A", "B", "A"]


def test_too_few_measures_make_one_section() -> None:
    found = structure.sections_from_features(blocks(A)[:, :3], count=5)
    assert [(s.start, s.end, s.label) for s in found] == [(0, 2, "A")]


def test_sections_cover_every_measure_without_gaps() -> None:
    found = structure.sections_from_features(blocks(A, B, A, C, B), count=6)
    assert found[0].start == 0 and found[-1].end == 5 * N_PER - 1
    assert all(b.start == a.end + 1 for a, b in zip(found, found[1:]))


def test_section_count_scales_with_song_length() -> None:
    assert structure.section_count(24) == 3
    assert 6 <= structure.section_count(120) <= 12
    assert structure.section_count(400) <= 12


def test_measure_features_describe_loudness_and_sound(click_wav) -> None:
    from video2sm import beats, dsp, features

    audio = dsp.load_audio(click_wav)
    analysis = beats.analyze_beats(audio)
    grid = features.extract_grid_features(audio, analysis)
    matrix, energy = structure.measure_features(audio, analysis, grid.n_measures)
    assert matrix.shape[1] == grid.n_measures == len(energy)
    assert energy.min() >= 0.0 and energy.max() == pytest.approx(1.0)


def test_loud_measures_have_higher_energy() -> None:
    from video2sm import dsp
    from video2sm.beats import BeatAnalysis

    sr = dsp.SAMPLE_RATE
    analysis = BeatAnalysis(bpm=120.0, first_beat_time=0.0, confidence=1.0, stability_ms=1.0, duration=16.0)
    seconds = 2.0  # four beats per measure at 120 BPM = 2 s
    t = np.arange(int(sr * seconds * 4)) / sr
    gain = np.repeat([0.05, 0.5, 0.05, 0.5], int(sr * seconds))
    audio = dsp.Audio(samples=(gain * np.sin(2 * np.pi * 220 * t)).astype(np.float32), sample_rate=sr)
    _, energy = structure.measure_features(audio, analysis, 4)
    assert energy[1] > 3 * energy[0] and energy[3] > 3 * energy[2]


def test_describe_lists_sections_and_energy_for_the_facts_file() -> None:
    found = structure.sections_from_features(blocks(A, B, A), count=3)
    energy = np.linspace(0, 1, 3 * N_PER)
    data = structure.describe(found, energy)
    assert data["sections"][0] == {"start": 0, "end": 7, "label": "A"}
    assert len(data["energy"]) == 24 and data["energy"][-1] == 1.0
