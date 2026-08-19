"""Planning / dedup layer (LLM call #2): merge, fill gaps, rank.

Extraction and planning are separate on purpose: extraction is a faithful
read of the transcript; planning is an editorial pass (merge, defaults, rank).
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from pydantic import ValidationError

from meetingpilot.config import get_settings
from meetingpilot.llm import call_tool
from meetingpilot.models import ExtractedItem, PlannedItem, PlannedItemList, Priority

PLAN_TOOL = "submit_planned_items"

PLAN_SCHEMA: dict[str, Any] = {
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
                    "due_date_iso",
                    "priority",
                    "source_quote",
                    "confidence",
                    "missing_owner",
                    "missing_due_date",
                    "proposed_owner",
                    "proposed_due_date_iso",
                    "rank",
                    "planning_notes",
                ],
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": ["string", "null"]},
                    "due_date_iso": {"type": ["string", "null"]},
                    "due_date_text": {"type": ["string", "null"]},
                    "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                    "source_quote": {"type": "string"},
                    "confidence": {"type": "number"},
                    "missing_owner": {"type": "boolean"},
                    "missing_due_date": {"type": "boolean"},
                    "proposed_owner": {"type": ["string", "null"]},
                    "proposed_due_date_iso": {"type": ["string", "null"]},
                    "rank": {
                        "type": "integer",
                        "minimum": 1,
                        "description": "1 = do first.",
                    },
                    "merged_from_quotes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "planning_notes": {"type": ["string", "null"]},
                },
            },
        }
    },
}

SYSTEM = """You are the planning layer. You receive action items already extracted
from a meeting. You do NOT re-read a transcript to invent new tasks.
Your job:
1) Merge duplicate or overlapping items (same deliverable, possibly different wording).
2) Flag missing owners or dates and propose defaults (do not silently invent owners
   unless a default_owner is provided).
3) Rank remaining items (1 = highest urgency) using priority, due date, and confidence.
Call submit_planned_items. Keep source_quote from the strongest original item.
When merging, put extra quotes in merged_from_quotes.
"""

_STOP = {
    "the",
    "a",
    "an",
    "to",
    "for",
    "of",
    "and",
    "or",
    "on",
    "in",
    "with",
    "our",
    "we",
}


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if w not in _STOP and len(w) > 2}


def task_similarity(a: str, b: str) -> float:
    """Jaccard similarity over content tokens. Used by deterministic dedup."""
    left, right = _tokens(a), _tokens(b)
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def should_merge(left: ExtractedItem, right: ExtractedItem, threshold: float = 0.55) -> bool:
    owners_compatible = (
        left.owner is None
        or right.owner is None
        or left.owner.strip().lower() == right.owner.strip().lower()
    )
    return owners_compatible and task_similarity(left.task, right.task) >= threshold


def merge_pair(left: ExtractedItem, right: ExtractedItem) -> ExtractedItem:
    """Keep the higher-confidence row; union quotes; fill missing fields from the other."""
    primary, secondary = (left, right) if left.confidence >= right.confidence else (right, left)
    data = primary.model_dump()
    data["owner"] = primary.owner or secondary.owner
    data["due_date_iso"] = primary.due_date_iso or secondary.due_date_iso
    data["due_date_text"] = primary.due_date_text or secondary.due_date_text
    if _priority_rank(secondary.priority) < _priority_rank(primary.priority):
        data["priority"] = secondary.priority
    extra_quote = secondary.source_quote
    if extra_quote and extra_quote not in data["source_quote"]:
        data["source_quote"] = data["source_quote"]
    data["confidence"] = max(primary.confidence, secondary.confidence)
    return ExtractedItem.model_validate(data)


def _priority_rank(priority: Priority) -> int:
    return {Priority.high: 0, Priority.medium: 1, Priority.low: 2}[priority]


def deduplicate_items(items: list[ExtractedItem], threshold: float = 0.55) -> list[ExtractedItem]:
    """Deterministic merge of overlapping items. Testable without an LLM.

    The LLM planning pass may merge more aggressively; this function is the
    guaranteed, documented dedup behavior.
    """
    merged: list[ExtractedItem] = []
    consumed = [False] * len(items)
    for i, item in enumerate(items):
        if consumed[i]:
            continue
        current = item
        extra_quotes: list[str] = []
        for j in range(i + 1, len(items)):
            if consumed[j]:
                continue
            if should_merge(current, items[j], threshold=threshold):
                extra_quotes.append(items[j].source_quote)
                current = merge_pair(current, items[j])
                consumed[j] = True
        merged.append(current)
    return merged


def apply_defaults(
    items: list[ExtractedItem],
    meeting_date: date,
    default_owner: str | None = None,
) -> list[PlannedItem]:
    """Flag gaps and propose defaults (owner + due date = meeting + 7 days)."""
    settings = get_settings()
    planned: list[PlannedItem] = []
    default_due = (meeting_date + timedelta(days=7)).isoformat()
    for item in items:
        missing_owner = item.owner is None
        missing_due = item.due_date_iso is None
        data = item.model_dump()
        data.update(
            {
                "missing_owner": missing_owner,
                "missing_due_date": missing_due,
                "proposed_owner": default_owner if missing_owner else None,
                "proposed_due_date_iso": default_due if missing_due else None,
                "needs_review": item.confidence < settings.low_confidence_threshold
                or missing_owner
                or missing_due,
            }
        )
        planned.append(PlannedItem.model_validate(data))
    return rank_items(planned)


def rank_items(items: list[PlannedItem]) -> list[PlannedItem]:
    def sort_key(item: PlannedItem) -> tuple:
        due = item.due_date_iso or item.proposed_due_date_iso or "9999-12-31"
        return (_priority_rank(item.priority), due, -item.confidence)

    ordered = sorted(items, key=sort_key)
    ranked: list[PlannedItem] = []
    for index, item in enumerate(ordered, start=1):
        ranked.append(item.model_copy(update={"rank": index}))
    return ranked


def validate_plan_payload(payload: dict[str, Any]) -> list[PlannedItem]:
    try:
        parsed = PlannedItemList.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Planning JSON failed schema validation: {exc}") from exc
    return parsed.items


def plan_action_items(
    items: list[ExtractedItem],
    meeting_date: date,
    default_owner: str | None = None,
) -> list[PlannedItem]:
    """LLM call #2 on top of deterministic dedup + defaults."""
    # Local pass first so the model sees a cleaner list, and so tests of
    # dedup/defaults do not depend on the network.
    local = apply_defaults(deduplicate_items(items), meeting_date, default_owner)

    payload = call_tool(
        system=SYSTEM,
        user=_planning_user_prompt(local, meeting_date, default_owner),
        tool_name=PLAN_TOOL,
        tool_description="Submit merged, ranked, gap-flagged action items.",
        input_schema=PLAN_SCHEMA,
    )
    planned = validate_plan_payload(payload)
    # Re-apply rank + needs_review so local policy always wins on those fields.
    return rank_items(
        [
            item.model_copy(
                update={
                    "needs_review": item.confidence
                    < get_settings().low_confidence_threshold
                    or item.owner is None
                    or item.due_date_iso is None,
                    "missing_owner": item.owner is None,
                    "missing_due_date": item.due_date_iso is None,
                }
            )
            for item in planned
        ]
    )


def _planning_user_prompt(
    items: list[PlannedItem],
    meeting_date: date,
    default_owner: str | None,
) -> str:
    blob = [item.model_dump() for item in items]
    return (
        f"Meeting date: {meeting_date.isoformat()}\n"
        f"Suggested default_owner: {default_owner or 'unassigned'}\n"
        f"Default due date if missing: {(meeting_date + timedelta(days=7)).isoformat()}\n\n"
        f"Extracted items after local dedup (JSON):\n{blob}\n\n"
        "Merge remaining duplicates, keep flags for missing owner/date, "
        "and rank the final list."
    )
