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

from meetingpilot.llm import call_tool, call_tool_choice
from meetingpilot.models import MeetingSummary, Screenshot, TranscriptDocument

SUMMARY_TOOL = "submit_summary"
CHAT_REPLY_TOOL = "reply_in_chat"

CHAT_REPLY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["message"],
    "properties": {
        "message": {
            "type": "string",
            "description": "A short, direct plain-text reply to what the user actually asked -- "
            "this chat box only edits the summary/diagrams, so if their message isn't an edit "
            "request, say so and, if relevant, point them to the right place in the UI instead "
            "of pretending to make an edit.",
        },
    },
}

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


REFINE_SYSTEM = """You are handling one message in a chat box attached to a
meeting summary and its diagrams. You have the original transcript, any
screenshots, the current draft, and the user's message. The chat box is
scoped ONLY to editing that summary/diagrams -- decide which of two tools
fits the user's message and call exactly one:

- submit_summary: use this ONLY if the message is actually requesting a
  change to the summary or diagrams (e.g. "make it shorter", "add a diagram
  for X", "rename the second diagram"). Apply the requested change
  precisely -- don't ignore it, don't overcorrect. Everything NOT related to
  the feedback should stay materially the same as the current draft -- this
  is an edit, not a rewrite from scratch. Stay grounded in the original
  transcript/screenshots -- same "don't invent what isn't there" discipline
  as the original summary. If feedback is about one diagram, revise that
  diagram's title or Mermaid code; leave other diagrams unchanged unless
  told otherwise. Call it with the FULL updated summary and FULL updated
  diagrams list, not just the part that changed.

- reply_in_chat: use this for anything that is NOT a summary/diagram edit
  request -- a question, a request unrelated to the summary/diagrams (e.g.
  asking for an email draft, asking about an action item), or general
  chat. Do not silently treat it as an edit request and do not fabricate a
  summary change to paper over it -- just reply honestly and helpfully to
  what was actually asked, grounded in the transcript if relevant.
"""


def refine_summary(
    current: MeetingSummary,
    feedback: str,
    document: TranscriptDocument,
    screenshots: list[Screenshot] | None = None,
) -> tuple[str, MeetingSummary | str]:
    """Handle one chat message about an existing summary/diagrams.

    Returns ("summary", MeetingSummary) if the message was actually a
    summary/diagram edit request, or ("chat", str) with a plain-text reply
    otherwise -- the model picks between the two based on the message, so a
    tangential or off-topic message gets an honest reply instead of a
    fabricated "updated" summary.
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
        f"User message:\n{feedback}"
    )
    images = [(shot.data, shot.mime_type) for shot in screenshots] if screenshots else None
    tool_name, payload = call_tool_choice(
        system=REFINE_SYSTEM,
        user=user,
        tools=[
            {
                "name": SUMMARY_TOOL,
                "description": "Submit the revised meeting summary and diagrams -- only if the "
                "message is actually requesting a change to them.",
                "schema": SUMMARY_SCHEMA,
            },
            {
                "name": CHAT_REPLY_TOOL,
                "description": "Reply directly in chat -- use for anything that is not a "
                "summary/diagram edit request.",
                "schema": CHAT_REPLY_SCHEMA,
            },
        ],
        images=images,
    )
    if tool_name == SUMMARY_TOOL:
        return "summary", MeetingSummary.model_validate(payload)
    return "chat", payload["message"]
