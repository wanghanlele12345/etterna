"""Thin, validated wrappers around ffmpeg/ffprobe."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .errors import MediaError

_FFMPEG_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    has_video: bool
    has_audio: bool
    width: int
    height: int


def _require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise MediaError(f"{name} not found on PATH; install ffmpeg (brew install ffmpeg)")
    return found


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
            timeout=_FFMPEG_TIMEOUT_SECONDS,
        )
    except subprocess.CalledProcessError as exc:
        tail = (exc.stderr or "").strip().splitlines()[-5:]
        raise MediaError(f"{args[0]} failed: {' | '.join(tail)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaError(f"{args[0]} timed out after {_FFMPEG_TIMEOUT_SECONDS}s") from exc


def _require_file(path: Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise MediaError(f"input file not found: {resolved}")
    return resolved


def probe(path: Path) -> MediaInfo:
    """Return basic stream facts about a media file."""
    source = _require_file(path)
    result = _run(
        [
            _require_tool("ffprobe"),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(source),
        ]
    )
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    duration = float(data.get("format", {}).get("duration") or 0.0)
    if audio is None:
        raise MediaError(f"no audio stream in {source.name}")
    if duration <= 0:
        raise MediaError(f"could not determine duration of {source.name}")
    return MediaInfo(
        path=source,
        duration=duration,
        has_video=video is not None,
        has_audio=True,
        width=int(video.get("width", 0)) if video else 0,
        height=int(video.get("height", 0)) if video else 0,
    )


def extract_audio(source: Path, destination: Path) -> Path:
    """Extract the audio track to stereo 44.1 kHz Ogg Vorbis.

    Etterna's decoder handles Ogg without the encoder-delay problems MP3 has,
    so the beat grid measured here stays aligned in-game.
    """
    src = _require_file(source)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            _require_tool("ffmpeg"),
            "-y", "-v", "error",
            "-i", str(src),
            "-vn",
            "-c:a", "vorbis", "-strict", "-2",
            "-ac", "2", "-ar", "44100", "-b:a", "192k",
            str(dest),
        ]
    )
    return dest


def transcode_background(source: Path, destination: Path, max_height: int = 720) -> Path:
    """Re-encode the video as silent H.264 MP4 (the song audio is separate)."""
    src = _require_file(source)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    scale = f"scale=-2:'min({max_height},ih)'"
    _run(
        [
            _require_tool("ffmpeg"),
            "-y", "-v", "error",
            "-i", str(src),
            "-an",
            "-vf", scale,
            "-r", "30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(dest),
        ]
    )
    return dest


def extract_frame(
    source: Path,
    destination: Path,
    at_seconds: float,
    width: int,
    height: int,
) -> Path:
    """Grab one frame, scaled to cover width x height and center-cropped."""
    src = _require_file(source)
    dest = Path(destination)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cover = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}"
    )
    _run(
        [
            _require_tool("ffmpeg"),
            "-y", "-v", "error",
            "-ss", f"{max(at_seconds, 0.0):.3f}",
            "-i", str(src),
            "-frames:v", "1",
            "-vf", cover,
            str(dest),
        ]
    )
    if not dest.is_file():
        raise MediaError(f"no frame could be extracted at {at_seconds:.1f}s")
    return dest
