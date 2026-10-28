from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from video2sm import dsp, stems
from video2sm.errors import AnalysisError


def write_tone(path: Path, hz: float, seconds: float = 1.0, sr: int = dsp.SAMPLE_RATE) -> None:
    t = np.arange(int(seconds * sr)) / sr
    sf.write(path, (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32), sr)


@pytest.fixture()
def song(tmp_path: Path) -> Path:
    path = tmp_path / "song.wav"
    write_tone(path, 220.0)
    return path


class FakeDemucs:
    """Stands in for the demucs subprocess: writes the four stems where demucs would."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, command: list[str]) -> None:
        self.calls += 1
        out = Path(command[command.index("-o") + 1])
        source = Path(command[-1])
        model = command[command.index("-n") + 1]
        folder = out / model / source.stem
        folder.mkdir(parents=True)
        for index, name in enumerate(stems.STEM_NAMES):
            write_tone(folder / f"{name}.flac", 110.0 * (index + 1))


def test_separation_returns_four_stems(song: Path, tmp_path: Path) -> None:
    runner = FakeDemucs()
    result = stems.separate(song, cache_dir=tmp_path / "cache", runner=runner)
    assert runner.calls == 1
    for name in stems.STEM_NAMES:
        audio = getattr(result, name)
        assert isinstance(audio, dsp.Audio)
        assert audio.duration == pytest.approx(1.0, abs=0.05)


def test_second_call_is_served_from_the_cache(song: Path, tmp_path: Path) -> None:
    runner = FakeDemucs()
    cache = tmp_path / "cache"
    first = stems.separate(song, cache_dir=cache, runner=runner)
    second = stems.separate(song, cache_dir=cache, runner=runner)
    assert runner.calls == 1
    assert np.allclose(first.vocals.samples, second.vocals.samples, atol=1e-3)


def test_cache_is_keyed_by_content_not_name(song: Path, tmp_path: Path) -> None:
    runner = FakeDemucs()
    cache = tmp_path / "cache"
    stems.separate(song, cache_dir=cache, runner=runner)
    renamed = tmp_path / "other name.wav"
    renamed.write_bytes(song.read_bytes())
    stems.separate(renamed, cache_dir=cache, runner=runner)
    assert runner.calls == 1

    different = tmp_path / "different.wav"
    write_tone(different, 330.0)
    stems.separate(different, cache_dir=cache, runner=runner)
    assert runner.calls == 2


def test_incomplete_output_is_an_error_and_not_cached(song: Path, tmp_path: Path) -> None:
    def broken(command: list[str]) -> None:
        out = Path(command[command.index("-o") + 1])
        folder = out / command[command.index("-n") + 1] / Path(command[-1]).stem
        folder.mkdir(parents=True)
        write_tone(folder / "vocals.flac", 220.0)  # the other three are missing

    cache = tmp_path / "cache"
    with pytest.raises(AnalysisError, match="stems"):
        stems.separate(song, cache_dir=cache, runner=broken)
    runner = FakeDemucs()
    stems.separate(song, cache_dir=cache, runner=runner)
    assert runner.calls == 1  # the failed attempt left nothing behind to be mistaken for a result


def test_command_uses_this_interpreter_and_flac(song: Path, tmp_path: Path) -> None:
    command = stems.demucs_command(song, tmp_path / "out", device="cpu")
    assert command[1:3] == ["-m", "demucs"]
    assert "--flac" in command and command[command.index("-d") + 1] == "cpu"
    assert command[-1] == str(song)


def test_availability_reflects_whether_demucs_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stems, "_installed", lambda name: name != "demucs")
    assert stems.available() is False
    monkeypatch.setattr(stems, "_installed", lambda name: True)
    assert stems.available() is True


def test_missing_demucs_gives_an_install_hint(
    song: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(stems, "_installed", lambda name: False)
    with pytest.raises(AnalysisError, match="uv sync --extra stems"):
        stems.separate(song, cache_dir=tmp_path / "cache")
