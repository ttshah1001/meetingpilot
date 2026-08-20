"""Tool-use layer: .ics file export for due-dated action items.

No OAuth, no API key, no network call — this is the live-demo fallback
if Google auth or the venue's wifi fails. One .ics file per task, plus a
bundle helper for a single "download all" file.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from icalendar import Calendar, Event

from meetingpilot.models import PlannedItem

PRODID = "-//MeetingPilot//meetingpilot.local//"


def _slug(text: str, max_length: int = 60) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_length] or "task"


def build_event(item: PlannedItem) -> Event:
    """One all-day VEVENT for the item. Raises if there's no due date."""
    due = item.resolved_due_date()
    if not due:
        raise ValueError("Cannot build an .ics event without a due date.")

    start = date.fromisoformat(due)
    end = start + timedelta(days=1)

    event = Event()
    event.add("summary", item.task)
    event.add("description", item.description_text())
    event.add("dtstart", start)
    event.add("dtend", end)
    event.add("uid", f"{_slug(item.task)}-{due}@meetingpilot.local")
    return event


def build_ics_bytes(item: PlannedItem) -> bytes:
    """One complete .ics file (single VEVENT) for one task."""
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    cal.add_component(build_event(item))
    return cal.to_ical()


def build_ics_bundle_bytes(items: list[PlannedItem]) -> bytes:
    """One .ics file containing every dated item as a separate VEVENT —
    convenient single download; skips items with no due date."""
    cal = Calendar()
    cal.add("prodid", PRODID)
    cal.add("version", "2.0")
    for item in items:
        if item.resolved_due_date():
            cal.add_component(build_event(item))
    return cal.to_ical()


def ics_filename(item: PlannedItem) -> str:
    due = item.resolved_due_date() or "no-date"
    return f"{_slug(item.task)}-{due}.ics"


def write_ics_files(items: list[PlannedItem], output_dir: str) -> list[str]:
    """Write one .ics file per dated item into output_dir. Returns the
    paths written; items with no due date are skipped."""
    from pathlib import Path

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for item in items:
        if not item.resolved_due_date():
            continue
        path = out / ics_filename(item)
        path.write_bytes(build_ics_bytes(item))
        written.append(str(path))
    return written
