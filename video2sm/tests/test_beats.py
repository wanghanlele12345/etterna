from pathlib import Path

import numpy as np
import pytest

from tests.conftest import TRUE_BPM, TRUE_FIRST_BEAT
from video2sm import beats, dsp
from video2sm.errors import AnalysisError


@pytest.fixture(scope="module")
def analysis(click_wav: Path) -> beats.BeatAnalysis:
    return beats.analyze_beats(dsp.load_audio(click_wav))


def test_bpm_is_accurate(analysis: beats.BeatAnalysis) -> None:
    assert analysis.bpm == pytest.approx(TRUE_BPM, abs=0.1)


def test_grid_is_aligned_within_10ms(analysis: beats.BeatAnalysis) -> None:
    period = 60.0 / TRUE_BPM
    error = (analysis.first_beat_time - TRUE_FIRST_BEAT) % period
    error = min(error, period - error)
    assert error < 0.010


def test_offset_is_negated_first_beat(analysis: beats.BeatAnalysis) -> None:
    assert analysis.offset == pytest.approx(-analysis.first_beat_time)
    assert 0.0 <= analysis.first_beat_time < 4 * 60.0 / analysis.bpm


def test_clean_track_is_confident_and_stable(analysis: beats.BeatAnalysis) -> None:
    assert analysis.confidence > 0.8
    assert analysis.stability_ms < 15
    assert not analysis.warnings


def test_silence_raises() -> None:
    audio = dsp.Audio(samples=np.zeros(22050 * 20, dtype=np.float32), sample_rate=22050)
    with pytest.raises(AnalysisError):
        beats.analyze_beats(audio)


def test_too_short_raises() -> None:
    audio = dsp.Audio(samples=np.random.rand(22050).astype(np.float32), sample_rate=22050)
    with pytest.raises(AnalysisError, match="short"):
        beats.analyze_beats(audio)
