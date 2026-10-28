import numpy as np

from video2sm import repeats

PHRASE = [[(0, 62), (4, 64), (8, 66)], [(0, 67), (8, 66)], [(0, 64), (4, 62), (12, 59)], [(0, 62)]]
OTHER = [[(2, 70), (10, 71)], [(6, 50)], [(0, 55), (14, 57)], [(4, 73)]]


def song(*parts):
    measures = []
    for part in parts:
        measures.extend([list(m) for m in part])
    return measures


def test_a_phrase_sung_again_is_found() -> None:
    found = repeats.find_repeats(song(PHRASE, OTHER, PHRASE))
    assert [(r.source_start, r.source_end, r.target_start, r.target_end) for r in found] == [(0, 3, 8, 11)]
    assert found[0].match > 0.9


def test_small_differences_still_count_as_a_repeat() -> None:
    varied = [list(m) for m in PHRASE]
    varied[1] = [(0, 67), (9, 66)]  # one note a slot late
    varied[2] = [(0, 64), (4, 61), (12, 59)]  # one note a semitone off
    found = repeats.find_repeats(song(PHRASE, OTHER, varied))
    assert [(r.source_start, r.target_start) for r in found] == [(0, 8)]


def test_different_music_is_not_a_repeat() -> None:
    assert repeats.find_repeats(song(PHRASE, OTHER)) == []


def test_silence_does_not_break_or_make_a_repeat() -> None:
    gap = [[], []]
    found = repeats.find_repeats(song(PHRASE, gap, OTHER, PHRASE))
    assert [(r.source_start, r.source_end, r.target_start, r.target_end) for r in found] == [(0, 3, 10, 13)]
    assert repeats.find_repeats(song(gap, gap, gap, gap)) == []


def test_each_measure_is_the_target_of_at_most_one_repeat() -> None:
    found = repeats.find_repeats(song(PHRASE, OTHER, PHRASE, OTHER, PHRASE))
    targets = [set(range(r.target_start, r.target_end + 1)) for r in found]
    assert all(not (a & b) for i, a in enumerate(targets) for b in targets[i + 1 :])
    covered = set().union(*targets)
    assert set(range(8, 12)) <= covered and set(range(16, 20)) <= covered  # both reprises are known


def test_short_coincidences_are_ignored() -> None:
    lone = [PHRASE[0]]
    assert repeats.find_repeats(song(lone, OTHER, lone)) == []


def test_from_facts_reads_the_melody_per_measure() -> None:
    facts = {"n_slots": 64, "melody": [{"slot": 0, "midi": 60}, {"slot": 17, "midi": 62}, {"slot": 50, "midi": 64}]}
    assert repeats.melody_by_measure(facts) == [[(0, 60)], [(1, 62)], [], [(2, 64)]]


def test_describe_is_plain_data() -> None:
    found = repeats.find_repeats(song(PHRASE, OTHER, PHRASE))
    assert repeats.describe(found) == [{"source": [0, 3], "target": [8, 11], "match": round(found[0].match, 2)}]
