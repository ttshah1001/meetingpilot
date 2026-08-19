"""Extraction layer (LLM call #1): segments → structured action items."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError

from meetingpilot.dates import resolve_due_date, to_iso
from meetingpilot.llm import call_tool
from meetingpilot.models import ExtractedItem, ExtractedItemList, TranscriptDocument

EXTRACT_TOOL = "submit_action_items"

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["items"],
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "task",
                    "owner",
                    "due_date_text",
                    "priority",
                    "source_quote",
                    "confidence",
                ],
                "properties": {
                    "task": {
                        "type": "string",
                        "description": "Short actionable task in imperative form.",
                    },
                    "owner": {
                        "type": ["string", "null"],
                        "description": "Person responsible, or null if not stated.",
                    },
                    "due_date_text": {
                        "type": ["string", "null"],
                        "description": "Due date exactly as spoken (e.g. 'Friday', 'next week').",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                    "source_quote": {
                        "type": "string",
                        "description": "Verbatim quote from the transcript that justifies the item.",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "How sure you are this is a real committed action item.",
                    },
                },
            },
        }
    },
}

SYSTEM = """You extract action items from a meeting transcript.
You MUST call submit_action_items with a JSON list. Do not invent work that nobody committed to.
Rules:
- task: one concrete deliverable (verb + object).
- owner: the named person who committed, else null. Never guess from job title alone.
- due_date_text: copy the relative/absolute date language from the transcript, else null.
- source_quote: a short verbatim span from the transcript.
- confidence: 0.9+ if owner+task+date are explicit; 0.5-0.7 if something is implied; <0.5 if shaky.
- Ignore small talk, status updates with no future work, and already-completed work.
"""


def validate_extraction_payload(payload: dict[str, Any]) -> list[ExtractedItem]:
    """Validate raw JSON against the extraction schema. Used by tests and the LLM path."""
    try:
        parsed = ExtractedItemList.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Extraction JSON failed schema validation: {exc}") from exc
    return parsed.items


def extract_action_items(
    document: TranscriptDocument,
    meeting_date: date,
) -> list[ExtractedItem]:
    """LLM call #1, then local date resolution against meeting_date."""
    transcript_block = "\n".join(turn.as_prompt_line() for turn in document.turns)
    user = (
        f"Meeting date (ISO): {meeting_date.isoformat()}\n"
        f"Source: {document.source_name}\n\n"
        f"Normalized speaker turns:\n{transcript_block}"
    )
    payload = call_tool(
        system=SYSTEM,
        user=user,
        tool_name=EXTRACT_TOOL,
        tool_description="Submit the list of extracted action items.",
        input_schema=EXTRACT_SCHEMA,
    )
    items = validate_extraction_payload(payload)
    return [apply_date_resolution(item, meeting_date) for item in items]


def apply_date_resolution(item: ExtractedItem, meeting_date: date) -> ExtractedItem:
    """Fill due_date_iso from due_date_text (or keep an already-valid ISO string)."""
    raw = item.due_date_text or item.due_date_iso
    resolved = resolve_due_date(raw, meeting_date)
    data = item.model_dump()
    data["due_date_iso"] = to_iso(resolved)
    return ExtractedItem.model_validate(data)
