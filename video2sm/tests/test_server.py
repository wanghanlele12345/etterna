import asyncio
from pathlib import Path
from typing import Any

import pytest
import simfile
from simfile.timing import Beat, TimingData
from simfile.timing.engine import TimingEngine

from video2sm import server


def call(name: str, args: dict[str, Any]) -> Any:
    result = asyncio.run(server.mcp.call_tool(name, args))
    return result.structured_content if hasattr(result, "structured_content") else result


def test_tools_are_registered() -> None:
    names = {t.name for t in asyncio.run(server.mcp.list_tools())}
    assert names == {
        "make_song_from_video", "make_song_from_url", "download_video",
        "analyze_video_beats", "analyze_video_notes", "validate_song", "adjust_song_offset",
        "inspect_chart", "view_chart", "look_at_video", "edit_chart", "choreography_guide",
        "align_chart",
    }


def test_difficulty_is_documented_on_the_tool() -> None:
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "make_song_from_video")
    assert "low" in tool.description and "high" in tool.description


def test_make_validate_and_adjust_round_trip(click_video: Path, tmp_path: Path) -> None:
    made = call(
        "make_song_from_video",
        {"video_path": str(click_video), "songs_dir": str(tmp_path), "difficulties": ["low", "high"]},
    )
    assert [c["difficulty"] for c in made["charts"]] == ["Easy", "Hard"]
    ssc_path = made["ssc_path"]
    assert call("validate_song", {"ssc_path": ssc_path})["ok"] is True

    def first_beat() -> float:
        return float(TimingEngine(TimingData(simfile.open(ssc_path))).time_at(Beat(0)))

    before = first_beat()
    call("adjust_song_offset", {"ssc_path": ssc_path, "delta_ms": 25})
    assert first_beat() == pytest.approx(before + 0.025, abs=1e-4)  # notes later


def test_analyze_creates_no_files(click_video: Path) -> None:
    report = call("analyze_video_beats", {"video_path": str(click_video)})
    assert report["bpm"] == pytest.approx(128.0, abs=0.1)
    assert report["has_video"] is True


def test_errors_are_reported_not_swallowed(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="not found"):
        call("make_song_from_video", {"video_path": str(tmp_path / "nope.mp4")})


def test_download_requires_a_rights_basis() -> None:
    with pytest.raises(Exception, match="rights_basis"):
        call("download_video", {"url": "https://youtu.be/abc", "rights_basis": "  "})


def test_download_rejects_non_youtube_url() -> None:
    with pytest.raises(Exception, match="YouTube"):
        call("download_video", {"url": "https://example.com/v", "rights_basis": "public domain"})


def test_make_song_from_url_chains_download_then_build(
    click_video: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = server.download.Downloaded(
        path=click_video, video_id="vid1", title="Click Song", uploader="Metronome Band",
        duration=40.0, license=None, source_url="https://youtu.be/vid1",
    )
    monkeypatch.setattr(server.download, "download_video", lambda url, **kw: fake)
    result = call(
        "make_song_from_url",
        {"url": "https://youtu.be/vid1", "rights_basis": "public domain",
         "songs_dir": str(tmp_path), "difficulties": ["medium"]},
    )
    assert result["title"] == "Click Song"
    assert [c["difficulty"] for c in result["charts"]] == ["Medium"]
    assert result["source"]["rights_basis"] == "public domain"
    assert "Metronome Band" in Path(result["ssc_path"]).read_text(encoding="utf-8")


def test_key_modes_are_documented_on_the_tool() -> None:
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "make_song_from_video")
    assert "pnm-nine" in tool.description and "holds" in tool.description


def test_make_song_with_nine_keys(click_video: Path, tmp_path: Path) -> None:
    made = call(
        "make_song_from_video",
        {"video_path": str(click_video), "songs_dir": str(tmp_path),
         "difficulties": ["high"], "key_modes": ["4k", "9k"], "holds": False},
    )
    assert [(c["steps_type"], c["holds"]) for c in made["charts"]] == [
        ("dance-single", 0), ("pnm-nine", 0),
    ]
    assert call("validate_song", {"ssc_path": made["ssc_path"]})["ok"] is True


def test_unknown_key_mode_is_reported(click_video: Path, tmp_path: Path) -> None:
    with pytest.raises(Exception, match="key mode"):
        call("make_song_from_video",
             {"video_path": str(click_video), "songs_dir": str(tmp_path), "key_modes": ["13k"]})


def test_chart_source_is_reported_and_documented(click_video: Path, tmp_path: Path) -> None:
    tool = next(t for t in asyncio.run(server.mcp.list_tools()) if t.name == "make_song_from_video")
    assert "chart_source" in tool.description and "stems" in tool.description
    made = call(
        "make_song_from_video",
        {"video_path": str(click_video), "songs_dir": str(tmp_path), "chart_source": "mix",
         "difficulties": ["high"]},
    )
    assert made["chart_source"] == "mix" and made["melody_notes"] == 0


def test_unknown_chart_source_is_reported(click_video: Path, tmp_path: Path) -> None:
    with pytest.raises(Exception, match="chart source"):
        call("make_song_from_video",
             {"video_path": str(click_video), "songs_dir": str(tmp_path), "chart_source": "magic"})


def test_analyze_video_notes_reads_the_melody_and_drums(click_video: Path, click_wav: Path,
                                                         vocal_wav: Path, monkeypatch) -> None:
    import numpy as np
    from video2sm import dsp, stems

    drums = dsp.load_audio(click_wav)
    silent = dsp.Audio(samples=np.zeros_like(drums.samples), sample_rate=drums.sample_rate)
    fake = stems.Stems(vocals=dsp.load_audio(vocal_wav), drums=drums, bass=silent, other=silent)
    monkeypatch.setattr(stems, "available", lambda: True)
    monkeypatch.setattr(stems, "separate", lambda source, **kw: fake)

    report = call("analyze_video_notes", {"video_path": str(click_video), "max_notes": 5})
    assert report["bpm"] == pytest.approx(128.0, abs=0.1)
    assert report["melody"]["note_count"] >= 50 and len(report["melody"]["notes"]) == 5
    assert report["drums"]["kick"] > 20


def test_analyze_video_notes_explains_a_missing_demucs(click_video: Path) -> None:
    with pytest.raises(Exception, match="uv sync --extra stems"):
        call("analyze_video_notes", {"video_path": str(click_video)})


def test_chart_review_tools_are_registered_and_explained() -> None:
    tools = {t.name: t for t in asyncio.run(server.mcp.list_tools())}
    assert {"inspect_chart", "edit_chart"} <= set(tools)
    assert "s4:3" in tools["edit_chart"].description  # the notation is documented where it is used


def test_inspect_and_edit_chart_round_trip(tmp_path: Path) -> None:
    from tests.test_review import build_song

    path = build_song(tmp_path)
    shown = call("inspect_chart", {"ssc_path": str(path), "difficulty": "Easy", "start_measure": 0, "measures": 2})
    assert "chart s0:4 s4:3 s8:4 s12:5" in shown["text"] and shown["total_measures"] == 8
    edited = call("edit_chart", {"ssc_path": str(path), "difficulty": "Easy",
                                 "edits": [{"measure": 0, "notes": "s0:1 s8:7"}]})
    assert edited["ok"] and edited["written"]
    again = call("inspect_chart", {"ssc_path": str(path), "difficulty": "Easy", "start_measure": 0, "measures": 1})
    assert "chart s0:1 s8:7" in again["text"]


def test_edit_chart_returns_refusals_instead_of_raising(tmp_path: Path) -> None:
    from tests.test_review import build_song

    result = call("edit_chart", {"ssc_path": str(build_song(tmp_path)), "difficulty": "Easy",
                                 "edits": [{"measure": 0, "notes": "s0:H3"}]})
    assert result["ok"] is False and any("never released" in e for e in result["errors"])


def test_view_chart_returns_an_image(tmp_path: Path) -> None:
    from tests.test_review import build_song

    path = build_song(tmp_path)
    result = asyncio.run(server.mcp.call_tool(
        "view_chart", {"ssc_path": str(path), "difficulty": "Easy", "start_measure": 0, "measures": 2}))
    blocks = result.content
    assert blocks and blocks[0].type == "image" and blocks[0].mime_type == "image/png"


def test_look_at_video_returns_a_contact_sheet(click_video: Path) -> None:
    result = asyncio.run(server.mcp.call_tool("look_at_video", {"video_path": str(click_video), "count": 4}))
    assert result.content[0].type == "image" and result.content[0].mime_type == "image/png"


def test_choreography_guide_is_served_from_the_package() -> None:
    result = asyncio.run(server.mcp.call_tool("choreography_guide", {}))
    text = "".join(getattr(block, "text", "") for block in result.content)
    assert "MIDI keyboard" in text and "edit_chart" in text


def test_align_chart_tool_reports_per_chart(tmp_path: Path) -> None:
    from tests.test_review import build_song

    report = call("align_chart", {"ssc_path": str(build_song(tmp_path))})
    assert [c["difficulty"] for c in report["charts"]] == ["Easy"]
