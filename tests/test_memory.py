"""SQLite memory read/write."""

from __future__ import annotations

from datetime import date

from meetingpilot.memory import list_open_items, save_meeting
from meetingpilot.models import PlannedItem, Priority


def test_save_and_list_open_items(tmp_path):
    db = str(tmp_path / "meetings.db")
    items = [
        PlannedItem(
            task="Draft the Q3 checkout roadmap",
            owner="Marcus",
            due_date_iso="2026-08-21",
            priority=Priority.high,
            source_quote="I will draft the Q3 checkout roadmap",
            confidence=0.91,
        ),
        PlannedItem(
            task="Mock the coupon flow",
            owner="Lin",
            due_date_iso="2026-08-26",
            priority=Priority.medium,
            source_quote="I can mock the new coupon flow",
            confidence=0.88,
        ),
    ]
    meeting_id = save_meeting(
        title="Sprint planning",
        meeting_date=date(2026, 8, 19),
        source_name="01_sprint_planning.txt",
        transcript="fake transcript",
        items=items,
        db_path=db,
    )
    assert meeting_id >= 1

    opened = list_open_items(db_path=db)
    assert len(opened) == 2
    owners = {row.owner for row in opened}
    assert owners == {"Marcus", "Lin"}

    marcus_only = list_open_items(owner="Marcus", db_path=db)
    assert len(marcus_only) == 1
    assert marcus_only[0].task == "Draft the Q3 checkout roadmap"
    assert marcus_only[0].meeting_title == "Sprint planning"
    assert marcus_only[0].status == "open"


def test_exclude_current_meeting(tmp_path):
    db = str(tmp_path / "meetings.db")
    item = PlannedItem(
        task="Send launch checklist",
        owner="Priya",
        due_date_iso="2026-08-21",
        priority=Priority.medium,
        source_quote="I will send the launch checklist",
        confidence=0.8,
    )
    first = save_meeting(
        title="Day 1",
        meeting_date=date(2026, 8, 19),
        source_name="a.txt",
        transcript="a",
        items=[item],
        db_path=db,
    )
    second = save_meeting(
        title="Day 2",
        meeting_date=date(2026, 8, 20),
        source_name="b.txt",
        transcript="b",
        items=[item],
        db_path=db,
    )
    previous = list_open_items(exclude_meeting_id=second, db_path=db)
    assert len(previous) == 1
    assert previous[0].meeting_id == first
