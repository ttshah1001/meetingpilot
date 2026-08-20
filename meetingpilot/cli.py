"""Command-line interface — useful before (and besides) the Streamlit UI."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from meetingpilot.calendar_tool import push_items
from meetingpilot.extraction import extract_action_items
from meetingpilot.gmail_tool import create_drafts
from meetingpilot.ingestion import ingest_file, ingest_text
from meetingpilot.models import SCREENSHOT_MIME_BY_EXTENSION, Screenshot
from meetingpilot.pipeline import process_meeting


def _meeting_date(value: str) -> date:
    return date.fromisoformat(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="meetingpilot",
        description="Turn a meeting transcript into tracked, calendared action items.",
    )
    parser.add_argument(
        "--transcript",
        "-t",
        help="Path to a .txt / .vtt / .srt transcript. Omit to read stdin.",
    )
    parser.add_argument(
        "--meeting-date",
        type=_meeting_date,
        default=date.today(),
        help="ISO date of the meeting (default: today). Used to resolve 'Friday', etc.",
    )
    parser.add_argument("--title", help="Optional meeting title stored in memory.")
    parser.add_argument(
        "--screenshot",
        "-s",
        action="append",
        default=[],
        dest="screenshots",
        help="Path to a .png/.jpg screenshot to extract alongside the transcript. Repeatable.",
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Stop after LLM call #1 and print extracted JSON (no planning, no DB).",
    )
    parser.add_argument(
        "--diagram",
        action="store_true",
        help="Also run the optional diagram-synthesis LLM call (Mermaid, from screenshots/transcript).",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Run extraction+planning but do not write to SQLite.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Print Calendar API payloads instead of creating events (default).",
    )
    parser.add_argument(
        "--push-calendar",
        action="store_true",
        help="After processing, create Google Calendar events (requires OAuth setup).",
    )
    parser.add_argument(
        "--live-calendar",
        action="store_true",
        help="Disable dry-run when used with --push-calendar.",
    )
    parser.add_argument(
        "--push-gmail",
        action="store_true",
        help="After processing, create Gmail drafts for each item (draft-only, never sends).",
    )
    parser.add_argument(
        "--live-gmail",
        action="store_true",
        help="Disable dry-run when used with --push-gmail. Still only creates drafts, never sends.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.transcript:
        document = ingest_file(args.transcript)
    else:
        raw = sys.stdin.read()
        if not raw.strip():
            print("No transcript provided. Pass --transcript PATH or pipe text.", file=sys.stderr)
            return 2
        document = ingest_text(raw, source_name="stdin.txt")

    screenshots = []
    for path in args.screenshots:
        shot_path = Path(path)
        if not shot_path.exists():
            print(f"Screenshot not found: {path}", file=sys.stderr)
            return 2
        screenshots.append(
            Screenshot(
                name=shot_path.name,
                mime_type=SCREENSHOT_MIME_BY_EXTENSION.get(shot_path.suffix.lower(), "image/png"),
                data=shot_path.read_bytes(),
            )
        )

    if args.extract_only:
        items = extract_action_items(document, args.meeting_date, screenshots=screenshots or None)
        print(json.dumps([item.model_dump() for item in items], indent=2))
        return 0

    result = process_meeting(
        document=document,
        meeting_date=args.meeting_date,
        title=args.title or Path(args.transcript).stem if args.transcript else "stdin",
        persist=not args.no_save,
        screenshots=screenshots or None,
        generate_diagram_from_content=args.diagram,
    )
    print(json.dumps(result.to_console_dict(), indent=2, default=str))

    if args.push_calendar:
        dry_run = not args.live_calendar
        pushes = push_items(result.planned, dry_run=dry_run)
        print(
            json.dumps(
                {
                    "calendar": [
                        {
                            "dry_run": p.dry_run,
                            "event_id": p.event_id,
                            "payload": p.payload,
                        }
                        for p in pushes
                    ]
                },
                indent=2,
            )
        )

    if args.push_gmail:
        dry_run = not args.live_gmail
        drafts = create_drafts(result.planned, dry_run=dry_run)
        print(
            json.dumps(
                {
                    "gmail": [
                        {
                            "dry_run": d.dry_run,
                            "draft_id": d.draft_id,
                            "mime_preview": d.mime_preview,
                        }
                        for d in drafts
                    ]
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
