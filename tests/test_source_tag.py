"""`source` (transcript vs screenshot) survives the planning LLM call.

Regression coverage for a code-review finding: the planning LLM could
legally omit or mangle `source` in its response, silently defaulting
screenshot-derived items back to "transcript" in the UI. plan_action_items
must cross-check against the locally-tracked (trusted) value instead of
blindly trusting the LLM's echo.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from meetingpilot.memory import save_meeting
from meetingpilot.models import ExtractedItem, ItemSource, PlannedItem, Priority
from meetingpilot.pipeline import stored_items_as_planned
from meetingpilot.planning import plan_action_items

MEETING = date(2026, 8, 19)


def _item(task: str, quote: str, source: ItemSource) -> ExtractedItem:
    return ExtractedItem(
        task=task,
        owner="Devon",
        due_date_iso="2026-08-21",
        priority=Priority.medium,
        source_quote=quote,
        confidence=0.9,
        source=source,
    )


def _fake_llm_payload(items, *, drop_source: bool = False, wrong_source: bool = False):
    out = []
    for item in items:
        row = item.model_dump()
        row.update(
            {
                "missing_owner": False,
                "missing_due_date": False,
                "proposed_owner": None,
                "proposed_due_date_iso": None,
                "rank": 1,
                "merged_from_quotes": [],
                "planning_notes": None,
            }
        )
        if drop_source:
            row.pop("source", None)
        elif wrong_source:
            row["source"] = "transcript"
        out.append(row)
    return {"items": out}


@patch("meetingpilot.planning.call_tool")
def test_screenshot_source_survives_even_if_llm_drops_the_field(mock_call_tool):
    items = [_item("Ship v2 payments API", "Kanban card: Ship v2 payments API", ItemSource.screenshot)]
    mock_call_tool.return_value = _fake_llm_payload(items, drop_source=True)

    planned = plan_action_items(items, MEETING)
    assert planned[0].source == ItemSource.screenshot


@patch("meetingpilot.planning.call_tool")
def test_screenshot_source_survives_even_if_llm_reports_it_wrong(mock_call_tool):
    items = [_item("Ship v2 payments API", "Kanban card: Ship v2 payments API", ItemSource.screenshot)]
    mock_call_tool.return_value = _fake_llm_payload(items, wrong_source=True)

    planned = plan_action_items(items, MEETING)
    assert planned[0].source == ItemSource.screenshot


@patch("meetingpilot.planning.call_tool")
def test_transcript_source_stays_transcript(mock_call_tool):
    items = [_item("Draft the roadmap", "I will draft the roadmap by Friday.", ItemSource.transcript)]
    mock_call_tool.return_value = _fake_llm_payload(items)

    planned = plan_action_items(items, MEETING)
    assert planned[0].source == ItemSource.transcript


def test_source_survives_sqlite_persist_and_reload(tmp_path):
    db = str(tmp_path / "meetings.db")
    planned = [
        PlannedItem(
            task="Ship v2 payments API",
            owner="Devon",
            due_date_iso="2026-08-21",
            priority=Priority.medium,
            source_quote="Kanban card: Ship v2 payments API",
            confidence=0.9,
            source=ItemSource.screenshot,
        ),
        PlannedItem(
            task="Draft the roadmap",
            owner="Marcus",
            due_date_iso="2026-08-21",
            priority=Priority.medium,
            source_quote="I will draft the roadmap by Friday.",
            confidence=0.9,
            source=ItemSource.transcript,
        ),
    ]
    meeting_id = save_meeting(
        title="Sprint planning",
        meeting_date=MEETING,
        source_name="test.txt",
        transcript="fake",
        items=planned,
        db_path=db,
    )

    rehydrated = stored_items_as_planned(meeting_id, db_path=db)
    sources = {item.task: item.source for item in rehydrated}
    assert sources["Ship v2 payments API"] == ItemSource.screenshot
    assert sources["Draft the roadmap"] == ItemSource.transcript
