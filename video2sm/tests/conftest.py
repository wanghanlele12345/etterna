"""Shared fixtures: a synthetic click-track song with a known beat grid."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SAMPLE_RATE = 22050
TRUE_BPM = 128.0
TRUE_FIRST_BEAT = 0.234
DURATION = 40.0


def _burst(freq: float, length: float, decay: float) -> np.ndarray:
    t = np.arange(int(length * SAMPLE_RATE)) / SAMPLE_RATE
    return np.sin(2 * np.pi * freq * t) * np.exp(-t * decay)


def make_click_track() -> np.ndarray:
    """Kick on every beat, hat on every off-eighth, silence before first beat."""
    signal = np.zeros(int(DURATION * SAMPLE_RATE), dtype=np.float32)
    kick = _burst(70.0, 0.15, 25.0)
    hat = _burst(6000.0, 0.04, 120.0) * 0.5
    period = 60.0 / TRUE_BPM
    beat = 0
    while True:
        start = TRUE_FIRST_BEAT + beat * period
        if start + 0.2 >= DURATION:
            break
        for offset, sound in ((0.0, kick), (period / 2, hat)):
            index = int((start + offset) * SAMPLE_RATE)
            end = min(index + len(sound), len(signal))
            signal[index:end] += sound[: end - index]
        beat += 1
    return np.clip(signal, -1.0, 1.0)


@pytest.fixture(autouse=True)
def no_stem_separation_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep tests hermetic: Demucs may be installed here, but only tests that fake it use it."""
    from video2sm import stems

    monkeypatch.setattr(stems, "_installed", lambda name: False)


@pytest.fixture(autouse=True)
def no_title_cards_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Title cards depend on system fonts; only the titlecard tests exercise them."""
    from video2sm import titlecard

    monkeypatch.setattr(titlecard, "find_font", lambda: None)


VOCAL_CYCLE_BEATS = 28
VOCAL_NOTE_SECONDS = 0.3


def vocal_pitch(beat_index: int) -> float:
    """MIDI pitch sung on a beat: climbs half a semitone per beat, then starts over."""
    return 57.0 + (beat_index % VOCAL_CYCLE_BEATS) * 0.5


def make_vocal_track() -> np.ndarray:
    """A sine 'vocal' with one note on every beat, rising in pitch over each cycle."""
    signal = np.zeros(int(DURATION * SAMPLE_RATE), dtype=np.float32)
    period = 60.0 / TRUE_BPM
    beat = 0
    while True:
        start = TRUE_FIRST_BEAT + beat * period
        if start + VOCAL_NOTE_SECONDS + 0.05 >= DURATION:
            break
        hz = 440.0 * 2 ** ((vocal_pitch(beat) - 69.0) / 12.0)
        t = np.arange(int(VOCAL_NOTE_SECONDS * SAMPLE_RATE)) / SAMPLE_RATE
        fade = np.minimum(1.0, np.minimum(t, VOCAL_NOTE_SECONDS - t) / 0.02)
        index = int(start * SAMPLE_RATE)
        signal[index : index + len(t)] += (0.5 * np.sin(2 * np.pi * hz * t) * fade).astype(np.float32)
        beat += 1
    return signal


@pytest.fixture(scope="session")
def vocal_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("audio") / "vocal.wav"
    sf.write(path, make_vocal_track(), SAMPLE_RATE)
    return path


@pytest.fixture(scope="session")
def click_wav(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("audio") / "click.wav"
    sf.write(path, make_click_track(), SAMPLE_RATE)
    return path


@pytest.fixture(scope="session")
def click_video(tmp_path_factory: pytest.TempPathFactory, click_wav: Path) -> Path:
    path = tmp_path_factory.mktemp("video") / "click.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", f"testsrc=size=640x360:rate=24:duration={DURATION}",
            "-i", str(click_wav),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest",
            str(path),
        ],
        check=True,
    )
    return path
