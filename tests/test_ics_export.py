""".ics export — no network, no OAuth. Validates real icalendar round-trips."""

from __future__ import annotations

from icalendar import Calendar

from meetingpilot.ics_export import (
    build_ics_bundle_bytes,
    build_ics_bytes,
    ics_filename,
    write_ics_files,
)
from meetingpilot.models import PlannedItem, Priority


def _item(task: str = "Draft the Q3 checkout roadmap", due: str | None = "2026-08-21") -> PlannedItem:
    return PlannedItem(
        task=task,
        owner="Marcus",
        due_date_iso=due,
        priority=Priority.high,
        source_quote="I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
        confidence=0.93,
    )


def test_build_ics_bytes_is_valid_and_round_trips():
    raw = build_ics_bytes(_item())
    cal = Calendar.from_ical(raw)
    events = list(cal.walk("VEVENT"))
    assert len(events) == 1
    event = events[0]
    assert str(event["summary"]) == "Draft the Q3 checkout roadmap"
    assert "Marcus" in str(event["description"])
    assert event["dtstart"].dt.isoformat() == "2026-08-21"
    # All-day events use exclusive end dates, matching the Calendar tool.
    assert event["dtend"].dt.isoformat() == "2026-08-22"


def test_build_ics_bytes_raises_without_due_date():
    item = _item(due=None)
    try:
        build_ics_bytes(item)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_bundle_skips_items_without_due_date():
    items = [_item("Task A", due="2026-08-21"), _item("Task B", due=None), _item("Task C", due="2026-08-22")]
    raw = build_ics_bundle_bytes(items)
    cal = Calendar.from_ical(raw)
    summaries = {str(e["summary"]) for e in cal.walk("VEVENT")}
    assert summaries == {"Task A", "Task C"}


def test_filename_is_filesystem_safe_and_includes_due_date():
    name = ics_filename(_item("Draft the Q3 checkout roadmap!!", due="2026-08-21"))
    assert name.endswith("-2026-08-21.ics")
    assert " " not in name
    assert "!" not in name


def test_write_ics_files_writes_one_file_per_dated_item(tmp_path):
    items = [_item("Task A", due="2026-08-21"), _item("Task B", due=None)]
    paths = write_ics_files(items, str(tmp_path))
    assert len(paths) == 1
    assert (tmp_path / ics_filename(items[0])).exists()
