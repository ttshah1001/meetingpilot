"""Gmail draft tool tests — mocked Google client and LLM, no live network, never sends."""

from __future__ import annotations

import base64
from unittest.mock import patch

from meetingpilot.gmail_tool import build_draft_payload, compose_email, create_draft
from meetingpilot.models import PlannedItem, Priority


class FakeDrafts:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, userId, body):
        self.calls.append({"userId": userId, "body": body})
        return self

    def execute(self):
        return {"id": "draft_mock_123"}


class FakeUsers:
    def __init__(self) -> None:
        self._drafts = FakeDrafts()

    def drafts(self):
        return self._drafts


class FakeService:
    def __init__(self) -> None:
        self._users = FakeUsers()

    def users(self):
        return self._users


def _item() -> PlannedItem:
    return PlannedItem(
        task="Draft the Q3 checkout roadmap",
        owner="Marcus",
        due_date_iso="2026-08-21",
        priority=Priority.high,
        source_quote="I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
        confidence=0.93,
    )


@patch("meetingpilot.gmail_tool.call_tool")
def test_compose_email_grounds_prompt_in_item_fields(mock_call_tool):
    mock_call_tool.return_value = {"subject": "Q3 checkout roadmap", "body": "Hi Priya, ..."}
    compose_email(_item())

    _, kwargs = mock_call_tool.call_args
    assert "Draft the Q3 checkout roadmap" in kwargs["user"]
    assert "Marcus" in kwargs["user"]
    assert "I will draft the Q3 checkout roadmap" in kwargs["user"]


@patch("meetingpilot.gmail_tool.call_tool")
def test_build_draft_payload_uses_composed_subject_and_body(mock_call_tool):
    mock_call_tool.return_value = {
        "subject": "Q3 checkout roadmap",
        "body": "Hi Priya, quick note that the Q3 checkout roadmap is due Friday, will send it over then.",
    }
    payload, preview = build_draft_payload(_item())
    assert "message" in payload
    raw = payload["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8")).decode("utf-8")
    assert "Q3 checkout roadmap" in decoded
    assert "quick note that the Q3 checkout roadmap is due Friday" in decoded
    # Composed body should read like an email, not a field dump.
    assert "Confidence" not in decoded
    assert "Priority" not in decoded
    # The preview is a plain-text rendering, independent of MIME wire
    # encoding (e.g. base64 CTE for non-ASCII bodies) — always readable.
    assert "Q3 checkout roadmap" in preview
    assert "quick note that the Q3 checkout roadmap is due Friday" in preview


@patch("meetingpilot.gmail_tool.call_tool")
def test_preview_stays_readable_for_non_ascii_body(mock_call_tool):
    mock_call_tool.return_value = {
        "subject": "Coupon copy check",
        "body": "Hey Lin, once the mock is up — that's medium priority — can you ping legal about the coupon copy?",
    }
    item = PlannedItem(
        task="Ping legal about the coupon copy",
        owner="Lin",
        due_date_iso="2026-08-26",
        priority=Priority.medium,
        source_quote="once the mock is up — that's medium priority",
        confidence=0.9,
    )
    _, preview = build_draft_payload(item)
    assert "once the mock is up — that's medium priority" in preview
    assert "base64" not in preview.lower()


@patch("meetingpilot.gmail_tool.call_tool")
def test_dry_run_does_not_call_service(mock_call_tool):
    mock_call_tool.return_value = {"subject": "Q3 checkout roadmap", "body": "Hi Priya, ..."}
    service = FakeService()
    result = create_draft(_item(), dry_run=True, gmail_service=service)
    assert result.dry_run is True
    assert result.draft_id is None
    assert service._users._drafts.calls == []
    assert "Q3 checkout roadmap" in result.mime_preview


@patch("meetingpilot.gmail_tool.call_tool")
def test_live_draft_uses_mocked_service_and_never_sends(mock_call_tool):
    mock_call_tool.return_value = {"subject": "Q3 checkout roadmap", "body": "Hi Priya, ..."}
    service = FakeService()
    result = create_draft(_item(), dry_run=False, gmail_service=service)
    assert result.dry_run is False
    assert result.draft_id == "draft_mock_123"
    assert len(service._users._drafts.calls) == 1
    assert service._users._drafts.calls[0]["userId"] == "me"
    # Only drafts().create was exercised — no send-adjacent call exists on
    # the fake service at all, so this is structurally draft-only.
