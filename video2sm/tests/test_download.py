from pathlib import Path
from typing import Any

import pytest

from video2sm import download
from video2sm.errors import MediaError


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc123",
        "https://youtu.be/abc123",
        "https://music.youtube.com/watch?v=abc123",
        "https://m.youtube.com/watch?v=abc123",
    ],
)
def test_accepts_youtube_urls(url: str) -> None:
    assert download.validate_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.youtube.com/watch?v=abc",  # not https
        "https://evil.example.com/watch?v=abc",
        "https://youtube.com.evil.example/watch?v=abc",  # lookalike host
        "file:///etc/passwd",
        "not a url",
        "",
    ],
)
def test_rejects_other_urls(url: str) -> None:
    with pytest.raises(ValueError, match="YouTube"):
        download.validate_url(url)


class FakeYDL:
    options: dict[str, Any] = {}
    error: Exception | None = None

    def __init__(self, opts: dict[str, Any]) -> None:
        FakeYDL.options = opts

    def __enter__(self) -> "FakeYDL":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> dict[str, Any]:
        if FakeYDL.error:
            raise FakeYDL.error
        out = Path(FakeYDL.options["outtmpl"].replace("%(id)s", "vid1").replace("%(ext)s", "mp4"))
        out.write_bytes(b"fake")
        return {
            "id": "vid1", "title": "Radetzky March", "uploader": "Some Band", "duration": 180,
            "license": "Creative Commons Attribution license (reuse allowed)",
            "requested_downloads": [{"filepath": str(out)}],
        }


@pytest.fixture
def fake_ydl(monkeypatch: pytest.MonkeyPatch) -> type[FakeYDL]:
    FakeYDL.error = None
    FakeYDL.options = {}
    monkeypatch.setattr(download.yt_dlp, "YoutubeDL", FakeYDL)
    return FakeYDL


def test_download_returns_metadata_and_file(fake_ydl, tmp_path: Path) -> None:
    result = download.download_video("https://youtu.be/vid1", tmp_path)
    assert result.path == tmp_path / "vid1.mp4" and result.path.is_file()
    assert (result.title, result.uploader, result.video_id) == ("Radetzky March", "Some Band", "vid1")
    assert result.duration == 180 and "Creative Commons" in (result.license or "")


def test_download_never_fetches_playlists_and_caps_quality(fake_ydl, tmp_path: Path) -> None:
    download.download_video("https://youtu.be/vid1", tmp_path, max_height=480)
    assert fake_ydl.options["noplaylist"] is True
    assert "480" in fake_ydl.options["format"]


def test_download_error_becomes_media_error(fake_ydl, tmp_path: Path) -> None:
    fake_ydl.error = download.yt_dlp.utils.DownloadError("Video unavailable")
    with pytest.raises(MediaError, match="Video unavailable"):
        download.download_video("https://youtu.be/vid1", tmp_path)


def test_download_rejects_bad_url_before_network(fake_ydl, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        download.download_video("https://evil.example.com/x", tmp_path)
    assert fake_ydl.options == {}  # yt-dlp was never constructed
    assert list(tmp_path.iterdir()) == []
