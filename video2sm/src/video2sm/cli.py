"""Command line for reviewing charts: the same tools the MCP server offers, for any agent with a shell."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import align, review, view
from .errors import Video2SmError


def _read_edits(source: str) -> list[dict[str, Any]]:
    raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    edits = json.loads(raw)
    if not isinstance(edits, list):
        raise ValueError("the edits file must contain a JSON list")
    return edits


def _inspect(args: argparse.Namespace) -> int:
    report = review.inspect_chart(
        Path(args.ssc), args.difficulty, start=args.start, count=args.count, steps_type=args.steps_type
    )
    print(report["text"])
    return 0


def _view(args: argparse.Namespace) -> int:
    out = view.save_chart_view(
        Path(args.ssc), args.difficulty, args.start, args.count, Path(args.out), args.steps_type
    )
    print(out)
    return 0


def _frames(args: argparse.Namespace) -> int:
    times = [float(t) for t in args.at.split(",")] if args.at else None
    sheet = view.contact_sheet(Path(args.video), times, count=args.count, columns=args.columns)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    print(out)
    return 0


def _edit(args: argparse.Namespace) -> int:
    result = review.edit_chart(
        Path(args.ssc), args.difficulty, _read_edits(args.edits),
        steps_type=args.steps_type, dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


def _align(args: argparse.Namespace) -> int:
    report = align.align_chart(
        Path(args.ssc), args.difficulty, args.steps_type, tolerance_seconds=args.tolerance_ms / 1000
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def _merge(args: argparse.Namespace) -> int:
    review.merge_chart(Path(args.source), Path(args.target), args.difficulty, args.steps_type)
    print(f"merged {args.difficulty} from {args.source} into {args.target}")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="video2sm-review", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    show = commands.add_parser("inspect", help="show measures next to the music they follow")
    show.add_argument("ssc")
    show.add_argument("difficulty")
    show.add_argument("--start", type=int, default=0)
    show.add_argument("--count", type=int, default=16)
    show.add_argument("--steps-type")
    show.set_defaults(run=_inspect)

    picture = commands.add_parser("view", help="draw measures and the music they follow as a PNG")
    picture.add_argument("ssc")
    picture.add_argument("difficulty")
    picture.add_argument("--start", type=int, default=0)
    picture.add_argument("--count", type=int, default=8)
    picture.add_argument("--steps-type")
    picture.add_argument("--out", required=True, help="where to write the PNG")
    picture.set_defaults(run=_view)

    frames = commands.add_parser("frames", help="a contact sheet of video frames, to see what is on screen")
    frames.add_argument("video")
    frames.add_argument("--count", type=int, default=8)
    frames.add_argument("--columns", type=int, default=4)
    frames.add_argument("--at", help="comma-separated seconds; default is evenly spaced")
    frames.add_argument("--out", required=True)
    frames.set_defaults(run=_frames)

    edit = commands.add_parser("edit", help="apply a JSON list of edits; refused edits change nothing")
    edit.add_argument("ssc")
    edit.add_argument("difficulty")
    edit.add_argument("edits", help="path to a JSON file, or - for stdin")
    edit.add_argument("--steps-type")
    edit.add_argument("--dry-run", action="store_true")
    edit.set_defaults(run=_edit)

    snap = commands.add_parser("align", help="move notes onto the exact attacks they answer")
    snap.add_argument("ssc")
    snap.add_argument("--difficulty", help="one chart; default is every chart")
    snap.add_argument("--steps-type")
    snap.add_argument("--tolerance-ms", type=float, default=90.0)
    snap.set_defaults(run=_align)

    merge = commands.add_parser("merge", help="copy one reviewed chart into another copy of the song")
    merge.add_argument("source")
    merge.add_argument("target")
    merge.add_argument("difficulty")
    merge.add_argument("--steps-type")
    merge.set_defaults(run=_merge)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.run(args)
    except (Video2SmError, ValueError, OSError) as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
