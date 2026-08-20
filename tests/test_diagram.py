"""Diagram synthesis (optional LLM call #3) — mocked, no live network."""

from __future__ import annotations

from unittest.mock import patch

from meetingpilot.diagram import generate_diagram
from meetingpilot.ingestion import ingest_text
from meetingpilot.models import Screenshot


@patch("meetingpilot.diagram.call_tool")
def test_no_diagram_when_nothing_describable(mock_call_tool):
    mock_call_tool.return_value = {"has_diagram": False, "title": None, "mermaid_code": None}
    doc = ingest_text("Marcus: I will draft the roadmap by Friday.", source_name="t.txt")

    result = generate_diagram(doc)
    assert result.has_diagram is False
    assert result.mermaid_code is None


@patch("meetingpilot.diagram.call_tool")
def test_diagram_returned_when_process_described(mock_call_tool):
    mock_call_tool.return_value = {
        "has_diagram": True,
        "title": "Checkout flow",
        "mermaid_code": "flowchart TD\n  A[Cart] --> B[Checkout] --> C[Confirmation]",
    }
    doc = ingest_text(
        "Priya: The flow is cart, then checkout, then confirmation.", source_name="t.txt"
    )

    result = generate_diagram(doc)
    assert result.has_diagram is True
    assert result.title == "Checkout flow"
    assert "flowchart TD" in result.mermaid_code


@patch("meetingpilot.diagram.call_tool")
def test_screenshots_are_passed_through_as_images(mock_call_tool):
    mock_call_tool.return_value = {"has_diagram": False, "title": None, "mermaid_code": None}
    doc = ingest_text("Standup notes.", source_name="t.txt")
    shot = Screenshot(name="board.png", mime_type="image/png", data=b"fake-png-bytes")

    generate_diagram(doc, screenshots=[shot])

    _, kwargs = mock_call_tool.call_args
    assert kwargs["images"] == [(b"fake-png-bytes", "image/png")]
