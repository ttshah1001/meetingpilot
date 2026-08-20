"""Extraction layer (LLM call #1): segments → structured action items."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import ValidationError

from meetingpilot.dates import resolve_due_date, to_iso
from meetingpilot.llm import call_tool
from meetingpilot.models import ExtractedItem, ExtractedItemList, Screenshot, TranscriptDocument

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
                    "source",
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
                    "source": {
                        "type": "string",
                        "enum": ["transcript", "screenshot"],
                        "description": "Whether this item came from the spoken transcript or from a screenshot image (e.g. a slide, whiteboard, or Kanban board).",
                    },
                },
            },
        }
    },
}

SYSTEM = """You extract action items from a meeting transcript, and from any
screenshot images provided alongside it (slides, whiteboards, Kanban boards).
You MUST call submit_action_items with a JSON list. Do not invent work that nobody committed to.
Rules:
- task: one concrete deliverable (verb + object).
- owner: the named person who committed, else null. Never guess from job title alone.
- due_date_text: copy the relative/absolute date language from the transcript or screenshot, else null.
- source_quote: a short verbatim span from the transcript that justifies the item; for
  screenshot-only items with no matching transcript line, briefly describe what the
  screenshot shows instead (e.g. "Kanban card: 'Ship v2 API' in the To Do column").
- source: "transcript" if the item comes from spoken dialogue, "screenshot" if it comes
  from an image (a slide bullet, a sticky note, a board column) with no matching transcript line.
- confidence: 0.9+ if owner+task+date are explicit; 0.5-0.7 if something is implied; <0.5 if shaky.
- Ignore small talk, status updates with no future work, and already-completed work.
- Do not duplicate an item that is both spoken and shown on a screenshot — extract it once,
  tagged with whichever source states it most precisely.
- If screenshots are attached, you MUST extract from them as a separate pass, independent of
  how many items the transcript already gave you. A busy transcript with several action items
  is not a reason to skip or shortchange screenshot content — every actionable card, bullet, or
  sticky note not already covered by a spoken line belongs in the list too.
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
    screenshots: list[Screenshot] | None = None,
) -> list[ExtractedItem]:
    """LLM call #1, then local date resolution against meeting_date.

    `screenshots`, if given, are sent as real image content blocks in the
    same call as the transcript text — genuine multimodal extraction, not
    a separate OCR pass.
    """
    transcript_block = "\n".join(turn.as_prompt_line() for turn in document.turns)
    screenshot_note = (
        f"\n\n{len(screenshots)} screenshot image(s) are attached below the transcript "
        "text — read them too (slides, whiteboards, Kanban boards, etc.)."
        if screenshots
        else ""
    )
    user = (
        f"Meeting date (ISO): {meeting_date.isoformat()}\n"
        f"Source: {document.source_name}\n\n"
        f"Normalized speaker turns:\n{transcript_block}"
        f"{screenshot_note}"
    )
    images = [(shot.data, shot.mime_type) for shot in screenshots] if screenshots else None
    payload = call_tool(
        system=SYSTEM,
        user=user,
        tool_name=EXTRACT_TOOL,
        tool_description="Submit the list of extracted action items.",
        input_schema=EXTRACT_SCHEMA,
        images=images,
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
