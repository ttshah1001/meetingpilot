"""Google Tasks tool tests — mocked Google client, no live network."""

from __future__ import annotations

from meetingpilot.models import PlannedItem, Priority
from meetingpilot.tasks_tool import build_task_payload, push_task


class FakeTasks:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def insert(self, tasklist, body):
        self.calls.append({"tasklist": tasklist, "body": body})
        return self

    def execute(self):
        return {"id": "task_mock_123"}


class FakeService:
    def __init__(self) -> None:
        self._tasks = FakeTasks()

    def tasks(self):
        return self._tasks


def _item() -> PlannedItem:
    return PlannedItem(
        task="Draft the Q3 checkout roadmap",
        owner="Marcus",
        due_date_iso="2026-08-21",
        priority=Priority.high,
        source_quote="I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
        confidence=0.93,
    )


def test_build_task_payload_shape():
    payload = build_task_payload(_item())
    assert payload["tasklist"] == "@default"
    body = payload["body"]
    assert body["title"] == "Draft the Q3 checkout roadmap"
    assert "Marcus" in body["notes"]
    assert "I will draft the Q3 checkout roadmap" in body["notes"]
    assert body["due"] == "2026-08-21T00:00:00.000Z"


def test_build_task_payload_raises_without_due_date():
    item = _item().model_copy(update={"due_date_iso": None, "proposed_due_date_iso": None})
    try:
        build_task_payload(item)
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_custom_tasklist_is_forwarded():
    payload = build_task_payload(_item(), tasklist="my-tasklist-id")
    assert payload["tasklist"] == "my-tasklist-id"


def test_dry_run_does_not_call_service():
    service = FakeService()
    result = push_task(_item(), dry_run=True, tasks_service=service)
    assert result.dry_run is True
    assert result.task_id is None
    assert service._tasks.calls == []
    assert result.payload["body"]["title"] == "Draft the Q3 checkout roadmap"


def test_live_push_uses_mocked_service():
    service = FakeService()
    result = push_task(_item(), dry_run=False, tasks_service=service)
    assert result.dry_run is False
    assert result.task_id == "task_mock_123"
    assert len(service._tasks.calls) == 1
    assert service._tasks.calls[0]["tasklist"] == "@default"
