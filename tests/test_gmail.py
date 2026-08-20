"""Gmail draft tool tests — mocked Google client, no live network, never sends."""

from __future__ import annotations

import base64

from meetingpilot.gmail_tool import build_draft_payload, create_draft
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


def test_build_draft_payload_shape():
    payload, preview = build_draft_payload(_item())
    assert "message" in payload
    raw = payload["message"]["raw"]
    decoded = base64.urlsafe_b64decode(raw.encode("utf-8")).decode("utf-8")
    assert "Draft the Q3 checkout roadmap" in decoded
    assert "Marcus" in decoded
    assert "I will draft the Q3 checkout roadmap" in decoded
    # The preview is a plain-text rendering, independent of MIME wire
    # encoding (e.g. base64 CTE for non-ASCII bodies) — always readable.
    assert "Draft the Q3 checkout roadmap" in preview
    assert "Marcus" in preview
    assert "I will draft the Q3 checkout roadmap" in preview


def test_preview_stays_readable_for_non_ascii_body():
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


def test_dry_run_does_not_call_service():
    service = FakeService()
    result = create_draft(_item(), dry_run=True, gmail_service=service)
    assert result.dry_run is True
    assert result.draft_id is None
    assert service._users._drafts.calls == []
    assert "Draft the Q3 checkout roadmap" in result.mime_preview


def test_live_draft_uses_mocked_service_and_never_sends():
    service = FakeService()
    result = create_draft(_item(), dry_run=False, gmail_service=service)
    assert result.dry_run is False
    assert result.draft_id == "draft_mock_123"
    assert len(service._users._drafts.calls) == 1
    assert service._users._drafts.calls[0]["userId"] == "me"
    # Only drafts().create was exercised — no send-adjacent call exists on
    # the fake service at all, so this is structurally draft-only.
