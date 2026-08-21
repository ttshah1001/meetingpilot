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
from meetingpilot.llm import call_tool
from meetingpilot.models import PlannedItem


@dataclass
class GmailDraftResult:
    dry_run: bool
    payload: dict[str, Any]
    mime_preview: str
    draft_id: Optional[str] = None


EMAIL_TOOL = "submit_email_draft"

EMAIL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["subject", "body"],
    "properties": {
        "subject": {
            "type": "string",
            "description": "Short, clear email subject line for this action item.",
        },
        "body": {
            "type": "string",
            "description": "A short, natural email body a person would actually send -- a "
            "sentence or two of context/lead-in grounded in what was said in the meeting, the "
            "actual ask, and the due date if there is one. Written the way a person writes an "
            "email. NOT a data dump of fields like confidence score, priority level, or raw "
            "internal metadata.",
        },
    },
}

EMAIL_SYSTEM = """You draft a short, natural, professional email for one
action item from a meeting. You're given the task, owner, due date, and the
source quote (what was actually said in the meeting that produced this
item).

Rules:
- Write like a person would actually write this email -- a brief lead-in for
  context, the ask, and the due date if there is one. Keep it short: a
  couple of sentences, not a report.
- Ground it in the source quote/context given -- don't invent details that
  aren't there.
- Never include internal metadata like a confidence score or priority label
  in the email body -- those are for MeetingPilot's UI, not for the
  recipient.
- Call submit_email_draft exactly once.
"""


def compose_email(item: PlannedItem) -> tuple[str, str]:
    """LLM call: write an actual email (subject, body) for one action item,
    instead of mechanically dumping the item's fields into a template."""
    owner = item.owner or item.proposed_owner or "unassigned"
    due = item.resolved_due_date() or "no due date set"
    user = (
        f"Task: {item.task}\n"
        f"Owner: {owner}\n"
        f"Due: {due}\n"
        f"Source quote from the meeting:\n{item.source_quote}"
    )
    if item.planning_notes:
        user += f"\n\nPlanning notes:\n{item.planning_notes}"
    payload = call_tool(
        system=EMAIL_SYSTEM,
        user=user,
        tool_name=EMAIL_TOOL,
        tool_description="Submit the drafted email subject and body.",
        input_schema=EMAIL_SCHEMA,
    )
    return payload["subject"], payload["body"]


def build_draft_payload(item: PlannedItem) -> tuple[dict[str, Any], str]:
    """Exact Gmail API drafts.create body we would send, plus a human-readable
    preview of the message for dry-run display.

    The preview is built separately from the wire-format MIME bytes: when
    the body contains non-ASCII characters, Python's MIMEText switches
    Content-Transfer-Encoding to base64, which would otherwise make the
    dry-run "preview" an unreadable blob instead of the actual text.
    """
    subject, body = compose_email(item)

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
