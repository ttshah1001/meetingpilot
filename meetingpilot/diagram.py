"""Diagram synthesis (optional LLM call #3): reconstruct a Mermaid diagram
from a whiteboard/flowchart screenshot, or a process described in the
transcript. Off by default — not every meeting has anything diagram-worthy,
and it's an extra LLM call on top of the two-call extraction/planning core.
"""

from __future__ import annotations

from typing import Any

from meetingpilot.llm import call_tool
from meetingpilot.models import DiagramResult, Screenshot, TranscriptDocument

DIAGRAM_TOOL = "submit_diagram"

DIAGRAM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["has_diagram", "title", "mermaid_code"],
    "properties": {
        "has_diagram": {
            "type": "boolean",
            "description": "True only if the transcript or a screenshot actually describes/shows a process, workflow, system architecture, or board (e.g. Kanban) structure worth diagramming.",
        },
        "title": {
            "type": ["string", "null"],
            "description": "Short title for the diagram, or null if has_diagram is false.",
        },
        "mermaid_code": {
            "type": ["string", "null"],
            "description": "Valid Mermaid syntax (flowchart/graph) reconstructing the structure, or null if has_diagram is false. Do not include the ```mermaid code fence, just the diagram body.",
        },
    },
}

SYSTEM = """You look at a meeting transcript and any attached screenshots
(whiteboards, Kanban boards, slides, architecture sketches) to see whether
there is an actual process, workflow, system, or board structure worth
drawing as a diagram.

Rules:
- Do NOT invent structure that isn't there. If nothing describable exists,
  set has_diagram to false and leave title/mermaid_code null — same
  discipline as action-item extraction: a faithful read, not a guess.
- If something is describable (e.g. a whiteboard shows Step A -> Step B ->
  Step C, or the transcript describes a request/response flow between
  services, or a Kanban board's columns and cards), reconstruct it as
  Mermaid syntax: `flowchart TD` for processes/architecture, or a simple
  graph for board layouts (columns as subgraphs, cards as nodes).
- Keep node labels short and derived from what was actually said/shown.
- Call submit_diagram exactly once.
"""


def generate_diagram(
    document: TranscriptDocument,
    screenshots: list[Screenshot] | None = None,
) -> DiagramResult:
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
        tool_name=DIAGRAM_TOOL,
        tool_description="Submit whether a diagram exists and its Mermaid code.",
        input_schema=DIAGRAM_SCHEMA,
        images=images,
    )
    return DiagramResult.model_validate(payload)
