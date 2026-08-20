"""Summary + diagram synthesis (optional LLM call #3): a short narrative
summary of the meeting, plus zero or more Mermaid diagrams reconstructed
from screenshots or a process described in the transcript. Off by default
-- not every meeting has anything diagram-worthy, and it's an extra LLM
call on top of the two-call extraction/planning core.

The model decides how many diagrams are warranted (0, 1, or more) based
on what's actually in the content -- never a hardcoded count.
"""

from __future__ import annotations

from typing import Any

from meetingpilot.llm import call_tool
from meetingpilot.models import MeetingSummary, Screenshot, TranscriptDocument

SUMMARY_TOOL = "submit_summary"

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "diagrams"],
    "properties": {
        "summary": {
            "type": ["string", "null"],
            "description": "A 2-4 sentence plain-English summary of what was discussed and decided. Null only if the transcript is too trivial/short to meaningfully summarize.",
        },
        "diagrams": {
            "type": "array",
            "description": "Zero or more diagrams -- use your judgment. Only include a diagram if the transcript or a screenshot actually describes/shows a process, workflow, system architecture, or board (e.g. Kanban) structure worth drawing. Do not force a diagram if nothing describable exists, and do not artificially cap yourself at one -- if there are genuinely two distinct describable structures (e.g. a system architecture AND a separate Kanban board), include both as separate entries.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "mermaid_code"],
                "properties": {
                    "title": {"type": "string", "description": "Short title for this diagram."},
                    "mermaid_code": {
                        "type": "string",
                        "description": "Valid Mermaid syntax (flowchart/graph). Do not include the ```mermaid code fence, just the diagram body.",
                    },
                },
            },
        },
    },
}

SYSTEM = """You look at a meeting transcript and any attached screenshots
(whiteboards, Kanban boards, slides, architecture sketches) and produce two
things: a short summary, and zero or more diagrams.

Rules:
- summary: 2-4 sentences, plain English, covering what was actually discussed
  and decided. Null only if there's truly nothing to summarize.
- diagrams: do NOT invent structure that isn't there -- same discipline as
  action-item extraction, a faithful read, not a guess. If nothing is
  describable, return an empty list. If something is describable (e.g. a
  whiteboard shows Step A -> Step B -> Step C, the transcript describes a
  request/response flow between services, or a Kanban board's columns and
  cards), reconstruct it as Mermaid syntax: `flowchart TD` for
  processes/architecture, or a simple graph for board layouts (columns as
  subgraphs, cards as nodes). Use your own judgment on how many diagrams are
  warranted -- usually 0, sometimes 1, occasionally 2 if there are genuinely
  separate describable structures. Never force a fixed count.
- Keep node labels short and derived from what was actually said/shown.
- Call submit_summary exactly once.
"""


def generate_summary(
    document: TranscriptDocument,
    screenshots: list[Screenshot] | None = None,
) -> MeetingSummary:
    """LLM call #3 (optional). Multimodal: reads transcript text + any screenshots."""
    transcript_block = "\n".join(turn.as_prompt_line() for turn in document.turns)
    screenshot_note = (
        f"\n\n{len(screenshots)} screenshot image(s) are attached below — check them "
        "for whiteboards, diagrams, or board layouts."
        if screenshots
        else ""
    )
    user = (
        f"Source: {document.source_name}\n\n"
        f"Normalized speaker turns:\n{transcript_block}"
        f"{screenshot_note}"
    )
    images = [(shot.data, shot.mime_type) for shot in screenshots] if screenshots else None
    payload = call_tool(
        system=SYSTEM,
        user=user,
        tool_name=SUMMARY_TOOL,
        tool_description="Submit the meeting summary and any diagrams.",
        input_schema=SUMMARY_SCHEMA,
        images=images,
    )
    return MeetingSummary.model_validate(payload)
