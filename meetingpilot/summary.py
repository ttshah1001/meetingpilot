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
            "description": "A detailed, multi-paragraph plain-English summary (roughly 2-3 short paragraphs) covering what was discussed, key decisions made, who owns what at a narrative level, and any notable context, tradeoffs, or open questions raised. More thorough than a one-liner -- write enough that someone who missed the meeting could understand what happened without reading the transcript. Null only if the transcript is too trivial/short to meaningfully summarize.",
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
- summary: a detailed, multi-paragraph plain-English summary (roughly 2-3
  short paragraphs) -- not a one-liner. Cover what was actually discussed,
  key decisions, who owns what at a narrative level, and any notable
  context, tradeoffs, or open questions. Write enough that someone who
  missed the meeting could understand what happened without reading the
  full transcript. Still faithful to what was said -- do not pad with
  invented detail just to sound longer. Null only if there's truly nothing
  to summarize.
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


REFINE_SYSTEM = """You are revising an existing meeting summary and its
diagrams based on user feedback. You have the original transcript, any
screenshots, the current draft, and what the user wants changed.

Rules:
- Apply the requested change precisely. Don't ignore it, don't overcorrect.
- Everything NOT related to the feedback should stay materially the same as
  the current draft -- this is an edit, not a rewrite from scratch. Don't
  drift the tone, length, or content unless asked to.
- Stay grounded in the original transcript/screenshots -- same "don't invent
  what isn't there" discipline as the original summary. If the user asks for
  information that genuinely isn't in the source material, say so in the
  summary text rather than fabricating it.
- Diagrams: if feedback is about one diagram, revise that diagram's title or
  Mermaid code; leave other diagrams unchanged unless told otherwise. If
  feedback asks to add or remove a diagram, do that.
- Call submit_summary exactly once with the FULL updated summary and the
  FULL updated diagrams list -- not just the part that changed.
"""


def refine_summary(
    current: MeetingSummary,
    feedback: str,
    document: TranscriptDocument,
    screenshots: list[Screenshot] | None = None,
) -> MeetingSummary:
    """Revise an existing summary/diagrams based on follow-up chat feedback.

    Same schema and multimodal grounding as generate_summary(), but the
    prompt includes the current draft plus the user's requested change so
    the model edits it rather than starting over from scratch.
    """
    transcript_block = "\n".join(turn.as_prompt_line() for turn in document.turns)
    screenshot_note = (
        f"\n\n{len(screenshots)} screenshot image(s) are attached below."
        if screenshots
        else ""
    )
    user = (
        f"Source: {document.source_name}\n\n"
        f"Original transcript:\n{transcript_block}"
        f"{screenshot_note}\n\n"
        f"Current draft (JSON):\n{current.model_dump_json()}\n\n"
        f"User feedback / requested change:\n{feedback}\n\n"
        "Apply this feedback and resubmit the full updated summary + diagrams."
    )
    images = [(shot.data, shot.mime_type) for shot in screenshots] if screenshots else None
    payload = call_tool(
        system=REFINE_SYSTEM,
        user=user,
        tool_name=SUMMARY_TOOL,
        tool_description="Submit the revised meeting summary and diagrams.",
        input_schema=SUMMARY_SCHEMA,
        images=images,
    )
    return MeetingSummary.model_validate(payload)
