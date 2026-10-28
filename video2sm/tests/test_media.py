from pathlib import Path

import pytest
import soundfile as sf

from video2sm import media
from video2sm.errors import MediaError


def test_probe_reports_streams(click_video: Path) -> None:
    info = media.probe(click_video)
    assert info.has_video and info.has_audio
    assert (info.width, info.height) == (640, 360)
    assert info.duration == pytest.approx(40.0, abs=0.5)


def test_probe_missing_file(tmp_path: Path) -> None:
    with pytest.raises(MediaError, match="not found"):
        media.probe(tmp_path / "nope.mp4")


def test_extract_audio_is_ogg_stereo_44k(click_video: Path, tmp_path: Path) -> None:
    out = media.extract_audio(click_video, tmp_path / "song.ogg")
    info = sf.info(out)
    assert info.format == "OGG"
    assert (info.samplerate, info.channels) == (44100, 2)
    assert info.duration == pytest.approx(40.0, abs=0.5)


def test_transcode_background_drops_audio(click_video: Path, tmp_path: Path) -> None:
    out = media.transcode_background(click_video, tmp_path / "bg.mp4")
    with pytest.raises(MediaError, match="no audio"):
        media.probe(out)  # silent video is exactly what we want


def test_extract_frame_crops_to_size(click_video: Path, tmp_path: Path) -> None:
    out = media.extract_frame(click_video, tmp_path / "banner.png", 5.0, 512, 160)
    assert out.is_file() and out.stat().st_size > 0
    info = media.probe  # noqa: F841 - ffprobe on png checked below
    import subprocess, json
    meta = json.loads(
        subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    assert (meta["streams"][0]["width"], meta["streams"][0]["height"]) == (512, 160)
