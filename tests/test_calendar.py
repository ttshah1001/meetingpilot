"""Calendar tool tests — mocked Google client, no live network."""

from __future__ import annotations

from meetingpilot.calendar_tool import build_event_payload, push_item
from meetingpilot.models import PlannedItem, Priority


class FakeEvents:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def insert(self, calendarId, body):
        self.calls.append({"calendarId": calendarId, "body": body})
        return self

    def execute(self):
        return {"id": "evt_mock_123"}


class FakeService:
    def __init__(self) -> None:
        self._events = FakeEvents()

    def events(self):
        return self._events


def _item() -> PlannedItem:
    return PlannedItem(
        task="Draft the Q3 checkout roadmap",
        owner="Marcus",
        due_date_iso="2026-08-21",
        priority=Priority.high,
        source_quote="I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
        confidence=0.93,
    )


def test_build_event_payload_shape():
    payload = build_event_payload(_item(), calendar_id="primary")
    assert payload["calendarId"] == "primary"
    body = payload["body"]
    assert body["summary"] == "Draft the Q3 checkout roadmap"
    assert "Marcus" in body["description"]
    assert "I will draft the Q3 checkout roadmap" in body["description"]
    assert body["start"]["date"] == "2026-08-21"
    # All-day events use exclusive end dates.
    assert body["end"]["date"] == "2026-08-22"


def test_dry_run_does_not_call_service():
    service = FakeService()
    result = push_item(_item(), dry_run=True, calendar_service=service)
    assert result.dry_run is True
    assert result.event_id is None
    assert service._events.calls == []
    assert result.payload["body"]["summary"] == "Draft the Q3 checkout roadmap"


def test_live_push_uses_mocked_service():
    service = FakeService()
    result = push_item(_item(), dry_run=False, calendar_service=service)
    assert result.dry_run is False
    assert result.event_id == "evt_mock_123"
    assert len(service._events.calls) == 1
    assert service._events.calls[0]["body"]["summary"] == "Draft the Q3 checkout roadmap"


def test_push_item_forwards_custom_calendar_id():
    """Regression: build_event_payload() accepted calendar_id, but push_item()
    never forwarded it, so a custom target calendar was unreachable."""
    service = FakeService()
    result = push_item(
        _item(), dry_run=False, calendar_service=service, calendar_id="demo@group.calendar.google.com"
    )
    assert result.payload["calendarId"] == "demo@group.calendar.google.com"
    assert service._events.calls[0]["calendarId"] == "demo@group.calendar.google.com"
