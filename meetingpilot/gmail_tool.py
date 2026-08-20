"""Tool-use layer: create Gmail drafts for action items.

Draft-only — this module never sends mail. Mirrors calendar_tool.py's
dry-run pattern: build_draft_payload() returns the exact API body we
would send, usable identically in dry-run and live mode.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Any, Optional

from meetingpilot.google_auth import get_credentials
from meetingpilot.models import PlannedItem


@dataclass
class GmailDraftResult:
    dry_run: bool
    payload: dict[str, Any]
    mime_preview: str
    draft_id: Optional[str] = None


def build_draft_payload(item: PlannedItem) -> tuple[dict[str, Any], str]:
    """Exact Gmail API drafts.create body we would send, plus a human-readable
    preview of the message for dry-run display.

    The preview is built separately from the wire-format MIME bytes: when
    the body contains non-ASCII characters, Python's MIMEText switches
    Content-Transfer-Encoding to base64, which would otherwise make the
    dry-run "preview" an unreadable blob instead of the actual text.
    """
    subject = f"Action item: {item.task}"
    due = item.due_date_iso or item.proposed_due_date_iso or "no due date set"
    owner = item.owner or item.proposed_owner or "unassigned"
    body_lines = [
        f"Task: {item.task}",
        f"Owner: {owner}",
        f"Due: {due}",
        f"Priority: {item.priority.value}",
        f"Confidence: {item.confidence:.2f}",
        "",
        "Source quote:",
        item.source_quote,
    ]
    if item.planning_notes:
        body_lines.extend(["", "Planning notes:", item.planning_notes])
    body = "\n".join(body_lines)

    message = MIMEText(body)
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    payload = {"message": {"raw": raw}}
    preview = f"Subject: {subject}\n\n{body}"
    return payload, preview


def _gmail_service():
    """Build an authenticated Gmail API client via the shared OAuth token."""
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=get_credentials())


def create_draft(
    item: PlannedItem,
    *,
    dry_run: bool = True,
    gmail_service=None,
) -> GmailDraftResult:
    """Create one Gmail draft, or return the payload without sending in dry-run mode."""
    payload, preview = build_draft_payload(item)
    if dry_run:
        return GmailDraftResult(dry_run=True, payload=payload, mime_preview=preview, draft_id=None)

    service = gmail_service or _gmail_service()
    created = service.users().drafts().create(userId="me", body=payload).execute()
    return GmailDraftResult(
        dry_run=False,
        payload=payload,
        mime_preview=preview,
        draft_id=created.get("id"),
    )


def create_drafts(
    items: list[PlannedItem],
    *,
    dry_run: bool = True,
    gmail_service=None,
) -> list[GmailDraftResult]:
    return [create_draft(item, dry_run=dry_run, gmail_service=gmail_service) for item in items]
