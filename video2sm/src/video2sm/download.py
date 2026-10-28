"""Download a YouTube video with yt-dlp, for use as chart source material."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp

from .errors import MediaError

DOWNLOAD_DIR_ENV = "VIDEO2SM_DOWNLOAD_DIR"
_ALLOWED_HOSTS = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
)
_SOCKET_TIMEOUT_SECONDS = 30
_RETRIES = 5


@dataclass(frozen=True)
class Downloaded:
    path: Path
    video_id: str
    title: str
    uploader: str
    duration: float
    license: str | None  # as declared on YouTube; None when not stated
    source_url: str


def default_download_dir() -> Path:
    return Path(os.environ.get(DOWNLOAD_DIR_ENV, Path.home() / "Downloads" / "video2sm"))


def validate_url(url: str) -> str:
    """Accept only https YouTube links (exact host match, no lookalike domains)."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https" or (parsed.hostname or "") not in _ALLOWED_HOSTS:
        raise ValueError(f"only https YouTube URLs are supported, got: {url!r}")
    return url.strip()


def _options(dest_dir: Path, max_height: int) -> dict[str, object]:
    return {
        "format": (
            f"bv*[height<={max_height}][ext=mp4]+ba[ext=m4a]"
            f"/b[height<={max_height}][ext=mp4]/b[height<={max_height}]/b"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "restrictfilenames": True,
        "quiet": True,
        "no_warnings": True,
        "retries": _RETRIES,
        "fragment_retries": _RETRIES,
        "socket_timeout": _SOCKET_TIMEOUT_SECONDS,
    }


def download_video(url: str, dest_dir: Path | None = None, max_height: int = 720) -> Downloaded:
    source = validate_url(url)
    target = Path(dest_dir) if dest_dir else default_download_dir()
    target.mkdir(parents=True, exist_ok=True)
    try:
        with yt_dlp.YoutubeDL(_options(target, max_height)) as ydl:
            info = ydl.extract_info(source, download=True)
    except yt_dlp.utils.DownloadError as exc:
        raise MediaError(f"YouTube download failed: {exc}") from exc

    downloads = info.get("requested_downloads") or []
    filepath = downloads[0].get("filepath") if downloads else None
    if not filepath or not Path(filepath).is_file():
        raise MediaError("YouTube download finished but no file was produced")
    return Downloaded(
        path=Path(filepath),
        video_id=str(info.get("id", "")),
        title=str(info.get("title", "")),
        uploader=str(info.get("uploader") or info.get("channel") or ""),
        duration=float(info.get("duration") or 0.0),
        license=info.get("license"),
        source_url=source,
    )
