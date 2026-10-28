import json
from pathlib import Path

import pytest

from tests.test_review import build_song, measure_from, row
from video2sm import chartfile, cli


def run(capsys, *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_inspect_prints_the_text_view(tmp_path: Path, capsys) -> None:
    path = build_song(tmp_path)
    code, out = run(capsys, "inspect", str(path), "Easy", "--start", "0", "--count", "2")
    assert code == 0 and "m0 " in out and "chart s0:4 s4:3 s8:4 s12:5" in out


def test_edit_reads_a_json_file_and_reports(tmp_path: Path, capsys) -> None:
    path = build_song(tmp_path)
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps([{"measure": 1, "notes": "s0:1 s8:7"}]), encoding="utf-8")
    code, out = run(capsys, "edit", str(path), "Easy", str(edits))
    result = json.loads(out)
    assert code == 0 and result["ok"] and result["written"]
    block = chartfile.find_chart(path.read_text(encoding="utf-8"), "kb7-single", "Easy")
    assert block.measures[1][0] == row(1)


def test_edit_reports_refusals_with_a_failing_exit_code(tmp_path: Path, capsys) -> None:
    path = build_song(tmp_path)
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps([{"measure": 1, "notes": "s0:9"}]), encoding="utf-8")
    code, out = run(capsys, "edit", str(path), "Easy", str(edits))
    result = json.loads(out)
    assert code == 1 and not result["ok"] and result["errors"]


def test_edit_dry_run_does_not_write(tmp_path: Path, capsys) -> None:
    path = build_song(tmp_path)
    before = path.read_text(encoding="utf-8")
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps([{"clear": [0]}]), encoding="utf-8")
    code, out = run(capsys, "edit", str(path), "Easy", str(edits), "--dry-run")
    assert code == 0 and json.loads(out)["written"] is False
    assert path.read_text(encoding="utf-8") == before


def test_merge_copies_a_chart_between_files(tmp_path: Path, capsys) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    source, target = build_song(tmp_path / "a"), build_song(tmp_path / "b")
    edits = tmp_path / "edits.json"
    edits.write_text(json.dumps([{"measure": 0, "notes": "s0:1"}]), encoding="utf-8")
    assert run(capsys, "edit", str(source), "Easy", str(edits))[0] == 0
    code, _ = run(capsys, "merge", str(source), str(target), "Easy")
    assert code == 0
    assert chartfile.find_chart(target.read_text(encoding="utf-8"), "kb7-single", "Easy").measures[0][0] == row(1)


def test_errors_are_printed_not_raised(tmp_path: Path, capsys) -> None:
    code, out = run(capsys, "inspect", str(tmp_path / "missing.ssc"), "Easy")
    assert code == 1 and "not found" in out


def test_view_writes_a_png(tmp_path: Path, capsys) -> None:
    from PIL import Image

    path = build_song(tmp_path)
    out = tmp_path / "shots" / "view.png"
    code, printed = run(capsys, "view", str(path), "Easy", "--start", "0", "--count", "2", "--out", str(out))
    assert code == 0 and printed.strip() == str(out)
    assert Image.open(out).format == "PNG"


def test_frames_writes_a_contact_sheet(tmp_path: Path, capsys, click_video) -> None:
    from PIL import Image

    out = tmp_path / "frames.png"
    code, printed = run(capsys, "frames", str(click_video), "--count", "4", "--out", str(out))
    assert code == 0 and printed.strip() == str(out)
    assert Image.open(out).format == "PNG"


def test_align_prints_a_report(tmp_path: Path, capsys) -> None:
    path = build_song(tmp_path)
    code, out = run(capsys, "align", str(path), "--difficulty", "Easy")
    report = json.loads(out)
    assert code == 0 and report["charts"][0]["difficulty"] == "Easy"
