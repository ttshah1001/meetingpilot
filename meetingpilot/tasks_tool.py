"""Tool-use layer: push action items to Google Tasks (real checkable to-dos).

Unlike Calendar (a date-based event) and Gmail (a draft you have to send
yourself), Google Tasks is the semantically correct destination for a
"task" -- title, notes, a due date, and a completion checkbox. Same
dry-run pattern as the other tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from meetingpilot.google_auth import get_credentials
from meetingpilot.models import PlannedItem


@dataclass
class TaskPushResult:
    dry_run: bool
    payload: dict[str, Any]
    task_id: Optional[str] = None


def build_task_payload(item: PlannedItem, *, tasklist: Optional[str] = None) -> dict[str, Any]:
    """Exact Google Tasks API body we would send. Shared by live + dry-run."""
    due = item.resolved_due_date()
    if not due:
        raise ValueError("Cannot create a task without a due date.")

    body: dict[str, Any] = {
        "title": item.task,
        "notes": item.description_text(),
        # Tasks API wants a full RFC3339 timestamp even for a date-only due date.
        "due": f"{due}T00:00:00.000Z",
    }
    return {"tasklist": tasklist or "@default", "body": body}


def _tasks_service():
    """Build an authenticated Google Tasks API client via the shared OAuth token."""
    from googleapiclient.discovery import build

    return build("tasks", "v1", credentials=get_credentials())


def push_task(
    item: PlannedItem,
    *,
    dry_run: bool = True,
    tasks_service=None,
    tasklist: Optional[str] = None,
) -> TaskPushResult:
    """Create one Google Task, or return the payload without creating it in dry-run mode."""
    payload = build_task_payload(item, tasklist=tasklist)
    if dry_run:
        return TaskPushResult(dry_run=True, payload=payload, task_id=None)

    service = tasks_service or _tasks_service()
    created = (
        service.tasks()
        .insert(tasklist=payload["tasklist"], body=payload["body"])
        .execute()
    )
    return TaskPushResult(dry_run=False, payload=payload, task_id=created.get("id"))


def push_tasks(
    items: list[PlannedItem],
    *,
    dry_run: bool = True,
    tasks_service=None,
    tasklist: Optional[str] = None,
) -> list[TaskPushResult]:
    results: list[TaskPushResult] = []
    for item in items:
        if not item.resolved_due_date():
            continue
        results.append(
            push_task(item, dry_run=dry_run, tasks_service=tasks_service, tasklist=tasklist)
        )
    return results
