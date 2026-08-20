"""Shared Pydantic / dataclass schemas used by every layer."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Priority(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


class SpeakerTurn(BaseModel):
    """One normalized utterance from the ingestion layer."""

    index: int
    speaker: str
    text: str
    start_ts: str | None = None
    end_ts: str | None = None

    def as_prompt_line(self) -> str:
        ts = ""
        if self.start_ts:
            ts = f"[{self.start_ts}"
            if self.end_ts:
                ts += f" --> {self.end_ts}"
            ts += "] "
        return f"{self.index}. {ts}{self.speaker}: {self.text}"


SCREENSHOT_MIME_BY_EXTENSION = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


class Screenshot(BaseModel):
    """One image (slide, whiteboard, Kanban board) uploaded alongside the transcript."""

    name: str
    mime_type: str
    data: bytes


class TranscriptDocument(BaseModel):
    source_name: str
    raw_text: str
    turns: list[SpeakerTurn]
    format: str = "txt"


class ItemSource(str, Enum):
    transcript = "transcript"
    screenshot = "screenshot"


def _validated_iso_date(value: Any) -> str | None:
    """Accept a date field only if it's actually a valid YYYY-MM-DD date.

    The LLM occasionally emits a malformed value here (a rare glitch,
    same class as other observed token-level hallucinations) -- without
    this check, that garbage string passes straight through to any
    consumer that calls date.fromisoformat() on it (Calendar, Tasks,
    .ics export), crashing the whole page instead of just being treated
    as "no real date was given."
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        date.fromisoformat(text[:10])
    except ValueError:
        return None
    return text[:10]


class ExtractedItem(BaseModel):
    """Strict extraction schema (LLM call #1)."""

    task: str
    owner: str | None = None
    due_date_iso: str | None = None
    due_date_text: str | None = None
    priority: Priority = Priority.medium
    source_quote: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: ItemSource = ItemSource.transcript

    @field_validator("owner", mode="before")
    @classmethod
    def blank_owner_to_none(cls, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() in {"", "none", "unknown", "n/a", "unspecified", "tbd"}:
            return None
        return text

    @field_validator("due_date_iso", mode="before")
    @classmethod
    def blank_date_to_none(cls, value: Any) -> str | None:
        return _validated_iso_date(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, value: Any) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("confidence must be a number") from exc
        return max(0.0, min(1.0, score))


class ExtractedItemList(BaseModel):
    items: list[ExtractedItem]


class PlannedItem(ExtractedItem):
    """Extraction schema plus planning-layer annotations (LLM call #2)."""

    missing_owner: bool = False
    missing_due_date: bool = False
    proposed_owner: str | None = None
    proposed_due_date_iso: str | None = None
    rank: int = 1
    merged_from_quotes: list[str] = Field(default_factory=list)
    planning_notes: str | None = None
    still_open_from_last_time: list[str] = Field(default_factory=list)
    needs_review: bool = False

    @field_validator("proposed_due_date_iso", mode="before")
    @classmethod
    def validate_proposed_date(cls, value: Any) -> str | None:
        return _validated_iso_date(value)

    def resolved_due_date(self) -> str | None:
        return self.due_date_iso or self.proposed_due_date_iso

    def description_text(self) -> str:
        """Shared event/draft description text — used identically by the
        Calendar tool and the .ics export so both stay in sync."""
        owner = self.owner or self.proposed_owner or "unassigned"
        lines = [
            f"Owner: {owner}",
            f"Priority: {self.priority.value}",
            f"Confidence: {self.confidence:.2f}",
            "",
            "Source quote:",
            self.source_quote,
        ]
        if self.planning_notes:
            lines.extend(["", "Planning notes:", self.planning_notes])
        return "\n".join(lines)


class PlannedItemList(BaseModel):
    items: list[PlannedItem]


class Diagram(BaseModel):
    title: str
    mermaid_code: str


class MeetingSummary(BaseModel):
    """Output of the optional summary + diagram-synthesis LLM call.

    `diagrams` length is model-decided (0, 1, or more) based on what's
    actually describable in the content -- never a fixed count.
    """

    summary: str | None = None
    diagrams: list[Diagram] = Field(default_factory=list)


class OpenMemoryItem(BaseModel):
    id: int
    meeting_id: int
    meeting_title: str
    meeting_date: date | None
    task: str
    owner: str | None
    due_date_iso: str | None
    priority: Priority
    status: str


class PipelineResult(BaseModel):
    meeting_id: int | None = None
    title: str
    meeting_date: date
    turns: list[SpeakerTurn]
    extracted: list[ExtractedItem]
    planned: list[PlannedItem]
    open_from_previous: list[OpenMemoryItem] = Field(default_factory=list)
    summary: MeetingSummary | None = None

    def to_console_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "meeting_date": self.meeting_date.isoformat(),
            "meeting_id": self.meeting_id,
            "turn_count": len(self.turns),
            "extracted": [item.model_dump() for item in self.extracted],
            "planned": [item.model_dump() for item in self.planned],
            "open_from_previous": [item.model_dump() for item in self.open_from_previous],
            "summary": self.summary.model_dump() if self.summary else None,
        }


def utc_now() -> datetime:
    return datetime.utcnow()
