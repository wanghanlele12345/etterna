"""Split a song into vocals / drums / bass / other with Demucs.

Demucs (and PyTorch) are an optional extra: `uv sync --extra stems`. Separation takes a
minute or so per song, so results are cached by the audio's content.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import dsp
from .errors import AnalysisError

STEM_NAMES = ("vocals", "drums", "bass", "other")
MODEL = "htdemucs"
CACHE_DIR_ENV = "VIDEO2SM_CACHE_DIR"
DEVICE_ENV = "VIDEO2SM_DEMUCS_DEVICE"
_TIMEOUT_SECONDS = 3600
INSTALL_HINT = "stem separation needs Demucs: run `uv sync --extra stems` in the video2sm project"

Runner = Callable[[list[str]], None]


@dataclass(frozen=True)
class Stems:
    vocals: dsp.Audio
    drums: dsp.Audio
    bass: dsp.Audio
    other: dsp.Audio

    def mixed(self) -> dsp.Audio:
        """The stems summed back together: what the listener hears."""
        parts = (self.vocals, self.drums, self.bass, self.other)
        length = min(len(p.samples) for p in parts)
        samples = sum((p.samples[:length] for p in parts), np.zeros(length, dtype=np.float32))
        return dsp.Audio(samples=samples, sample_rate=self.drums.sample_rate)


def _installed(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def available() -> bool:
    """True when Demucs and PyTorch can be imported."""
    return _installed("demucs") and _installed("torch")


def default_cache_dir() -> Path:
    return Path(os.environ.get(CACHE_DIR_ENV, Path.home() / ".cache" / "video2sm" / "stems"))


def demucs_command(source: Path, out_dir: Path, device: str) -> list[str]:
    return [
        sys.executable, "-m", "demucs",
        "-n", MODEL,
        "-d", device,
        "--flac",
        "-o", str(out_dir),
        str(source),
    ]


def _run(command: list[str]) -> None:
    try:
        subprocess.run(
            command, check=True, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS
        )
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-4:]
        raise AnalysisError(f"demucs failed: {' | '.join(tail)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError(f"demucs timed out after {_TIMEOUT_SECONDS}s") from exc


def _digest(path: Path) -> str:
    sha = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _cached_files(folder: Path) -> dict[str, Path]:
    return {name: folder / f"{name}.flac" for name in STEM_NAMES}


def _load(folder: Path) -> Stems:
    files = _cached_files(folder)
    return Stems(**{name: dsp.load_audio(path) for name, path in files.items()})


def separate(
    source: Path,
    cache_dir: Path | None = None,
    runner: Runner | None = None,
    device: str | None = None,
) -> Stems:
    """Stems of `source`, from the cache when this exact audio was separated before."""
    source = Path(source)
    if runner is None:
        if not available():
            raise AnalysisError(INSTALL_HINT)
        runner = _run
    root = Path(cache_dir) if cache_dir else default_cache_dir()
    final = root / f"{_digest(source)}-{MODEL}"
    if all(path.is_file() for path in _cached_files(final).values()):
        return _load(final)

    root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".separating-", dir=root))
    try:
        runner(demucs_command(source, work, device or os.environ.get(DEVICE_ENV, "cpu")))
        produced = work / MODEL / source.stem
        missing = [n for n, p in _cached_files(produced).items() if not p.is_file()]
        if missing:
            raise AnalysisError(f"demucs produced incomplete stems, missing: {', '.join(missing)}")
        shutil.move(str(produced), str(final))
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return _load(final)
