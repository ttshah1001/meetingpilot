"""Orchestrates the six layers: ingest → extract → plan → memory → (calendar)."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from meetingpilot.config import get_settings
from meetingpilot.summary import generate_summary
from meetingpilot.extraction import extract_action_items
from meetingpilot.ingestion import ingest_file, ingest_text
from meetingpilot.memory import (
    list_items_for_meeting,
    list_open_for_owners,
    list_open_items,
    save_meeting,
)
from meetingpilot.models import ItemSource, PipelineResult, PlannedItem, Screenshot, TranscriptDocument
from meetingpilot.planning import plan_action_items, task_similarity


def _attach_memory(planned: list[PlannedItem], open_items) -> list[PlannedItem]:
    """Annotate new items when the same owner still has open work."""
    annotated: list[PlannedItem] = []
    for item in planned:
        still = []
        owner = (item.owner or item.proposed_owner or "").strip().lower()
        for remembered in open_items:
            same_owner = (
                remembered.owner
                and owner
                and remembered.owner.strip().lower() == owner
            )
            similar = task_similarity(item.task, remembered.task) >= 0.4
            if same_owner or similar:
                label = (
                    f"{remembered.owner or 'unassigned'}: {remembered.task} "
                    f"(from '{remembered.meeting_title}')"
                )
                still.append(label)
        annotated.append(item.model_copy(update={"still_open_from_last_time": still}))
    return annotated


def process_meeting(
    *,
    document: TranscriptDocument,
    meeting_date: date,
    title: Optional[str] = None,
    persist: bool = True,
    db_path: Optional[str] = None,
    default_owner: Optional[str] = None,
    screenshots: Optional[list[Screenshot]] = None,
    generate_summary_from_content: bool = False,
) -> PipelineResult:
    extracted = extract_action_items(document, meeting_date, screenshots=screenshots)
    planned = plan_action_items(extracted, meeting_date, default_owner=default_owner)

    summary = None
    if generate_summary_from_content:
        summary = generate_summary(document, screenshots=screenshots)

    owners = [p.owner for p in planned if p.owner]
    previous = list_open_for_owners(owners, db_path=db_path) if persist else []
    if persist and not previous:
        previous = list_open_items(db_path=db_path)

    planned = _attach_memory(planned, previous)

    meeting_id = None
    meeting_title = title or document.source_name
    if persist:
        meeting_id = save_meeting(
            title=meeting_title,
            meeting_date=meeting_date,
            source_name=document.source_name,
            transcript=document.raw_text,
            items=planned,
            db_path=db_path,
        )

    return PipelineResult(
        meeting_id=meeting_id,
        title=meeting_title,
        meeting_date=meeting_date,
        turns=document.turns,
        extracted=extracted,
        planned=planned,
        open_from_previous=previous,
        summary=summary,
    )


def process_path(
    path: str | Path,
    *,
    meeting_date: date,
    title: Optional[str] = None,
    persist: bool = True,
    db_path: Optional[str] = None,
    screenshots: Optional[list[Screenshot]] = None,
    generate_summary_from_content: bool = False,
) -> PipelineResult:
    document = ingest_file(path)
    return process_meeting(
        document=document,
        meeting_date=meeting_date,
        title=title,
        persist=persist,
        db_path=db_path,
        screenshots=screenshots,
        generate_summary_from_content=generate_summary_from_content,
    )


def process_pasted_text(
    text: str,
    *,
    meeting_date: date,
    source_name: str = "pasted.txt",
    title: Optional[str] = None,
    persist: bool = True,
    db_path: Optional[str] = None,
    screenshots: Optional[list[Screenshot]] = None,
    generate_summary_from_content: bool = False,
) -> PipelineResult:
    document = ingest_text(text, source_name=source_name)
    return process_meeting(
        document=document,
        meeting_date=meeting_date,
        title=title,
        persist=persist,
        db_path=db_path,
        screenshots=screenshots,
        generate_summary_from_content=generate_summary_from_content,
    )


def stored_items_as_planned(meeting_id: int, db_path: Optional[str] = None) -> list[PlannedItem]:
    """Rehydrate planned items from SQLite so the UI can push to calendar later."""
    rows = list_items_for_meeting(meeting_id, db_path=db_path)
    items: list[PlannedItem] = []
    for row in rows:
        items.append(
            PlannedItem(
                task=row.task,
                owner=row.owner,
                due_date_iso=row.due_date_iso,
                priority=row.priority,  # type: ignore[arg-type]
                source_quote=row.source_quote,
                confidence=row.confidence,
                planning_notes=row.planning_notes,
                source=ItemSource(row.source),
            )
        )
    return items


def require_api_key() -> None:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
