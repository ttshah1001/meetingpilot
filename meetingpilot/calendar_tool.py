"""Tool-use layer: create Google Calendar events for due-dated action items."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from meetingpilot.config import get_settings
from meetingpilot.models import PlannedItem

SCOPES = ["https://www.googleapis.com/auth/calendar.events"]


@dataclass
class CalendarPushResult:
    dry_run: bool
    payload: dict[str, Any]
    event_id: Optional[str] = None


def build_event_payload(
    item: PlannedItem,
    *,
    calendar_id: Optional[str] = None,
) -> dict[str, Any]:
    """Exact Calendar API body we would send. Shared by live + dry-run."""
    settings = get_settings()
    due = item.due_date_iso or item.proposed_due_date_iso
    if not due:
        raise ValueError("Cannot create a calendar event without a due date.")

    start = date.fromisoformat(due)
    end = start + timedelta(days=1)
    owner = item.owner or item.proposed_owner or "unassigned"
    description_lines = [
        f"Owner: {owner}",
        f"Priority: {item.priority.value}",
        f"Confidence: {item.confidence:.2f}",
        "",
        "Source quote:",
        item.source_quote,
    ]
    if item.planning_notes:
        description_lines.extend(["", "Planning notes:", item.planning_notes])

    return {
        "calendarId": calendar_id or settings.google_calendar_id,
        "body": {
            "summary": item.task,
            "description": "\n".join(description_lines),
            "start": {"date": start.isoformat()},
            "end": {"date": end.isoformat()},
        },
    }


def _google_service():
    """Build an authenticated Calendar API client. Token is stored locally."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    settings = get_settings()
    creds_path = settings.google_credentials_path
    token_path = settings.google_token_path

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google OAuth client file not found at {creds_path}. "
            "See README.md for Cloud Console setup, or use --dry-run."
        )

    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        token_path.write_text(creds.to_json(), encoding="utf-8")

    return build("calendar", "v3", credentials=creds)


def push_item(
    item: PlannedItem,
    *,
    dry_run: bool = True,
    calendar_service=None,
) -> CalendarPushResult:
    """Create one all-day event, or print/return the payload in dry-run mode."""
    payload = build_event_payload(item)
    if dry_run:
        return CalendarPushResult(dry_run=True, payload=payload, event_id=None)

    service = calendar_service or _google_service()
    created = (
        service.events()
        .insert(calendarId=payload["calendarId"], body=payload["body"])
        .execute()
    )
    return CalendarPushResult(
        dry_run=False,
        payload=payload,
        event_id=created.get("id"),
    )


def push_items(
    items: list[PlannedItem],
    *,
    dry_run: bool = True,
    calendar_service=None,
) -> list[CalendarPushResult]:
    results: list[CalendarPushResult] = []
    for item in items:
        due = item.due_date_iso or item.proposed_due_date_iso
        if not due:
            continue
        results.append(
            push_item(item, dry_run=dry_run, calendar_service=calendar_service)
        )
    return results
