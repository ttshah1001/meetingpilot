"""Summary + diagram synthesis (optional LLM call #3) — mocked, no live network."""

from __future__ import annotations

from unittest.mock import patch

from meetingpilot.ingestion import ingest_text
from meetingpilot.models import Screenshot
from meetingpilot.summary import generate_summary


@patch("meetingpilot.summary.call_tool")
def test_no_diagrams_when_nothing_describable(mock_call_tool):
    mock_call_tool.return_value = {
        "summary": "Marcus committed to a roadmap draft by Friday.",
        "diagrams": [],
    }
    doc = ingest_text("Marcus: I will draft the roadmap by Friday.", source_name="t.txt")

    result = generate_summary(doc)
    assert result.summary == "Marcus committed to a roadmap draft by Friday."
    assert result.diagrams == []


@patch("meetingpilot.summary.call_tool")
def test_null_summary_when_trivial(mock_call_tool):
    mock_call_tool.return_value = {"summary": None, "diagrams": []}
    doc = ingest_text("Standup: nothing notable today.", source_name="t.txt")

    result = generate_summary(doc)
    assert result.summary is None
    assert result.diagrams == []


@patch("meetingpilot.summary.call_tool")
def test_single_diagram_returned(mock_call_tool):
    mock_call_tool.return_value = {
        "summary": "The team walked through the checkout flow.",
        "diagrams": [
            {
                "title": "Checkout flow",
                "mermaid_code": "flowchart TD\n  A[Cart] --> B[Checkout] --> C[Confirmation]",
            }
        ],
    }
    doc = ingest_text(
        "Priya: The flow is cart, then checkout, then confirmation.", source_name="t.txt"
    )

    result = generate_summary(doc)
    assert len(result.diagrams) == 1
    assert result.diagrams[0].title == "Checkout flow"
    assert "flowchart TD" in result.diagrams[0].mermaid_code


@patch("meetingpilot.summary.call_tool")
def test_model_can_return_multiple_diagrams(mock_call_tool):
    """The model decides the count -- not hardcoded to 0 or 1."""
    mock_call_tool.return_value = {
        "summary": "Covered both the system architecture and the sprint board.",
        "diagrams": [
            {"title": "Architecture", "mermaid_code": "flowchart TD\n  A --> B"},
            {"title": "Kanban board", "mermaid_code": "flowchart LR\n  subgraph ToDo\n  C\n  end"},
        ],
    }
    doc = ingest_text("Two separate topics discussed.", source_name="t.txt")

    result = generate_summary(doc)
    assert len(result.diagrams) == 2
    assert {d.title for d in result.diagrams} == {"Architecture", "Kanban board"}


@patch("meetingpilot.summary.call_tool")
def test_screenshots_are_passed_through_as_images(mock_call_tool):
    mock_call_tool.return_value = {"summary": None, "diagrams": []}
    doc = ingest_text("Standup notes.", source_name="t.txt")
    shot = Screenshot(name="board.png", mime_type="image/png", data=b"fake-png-bytes")

    generate_summary(doc, screenshots=[shot])

    _, kwargs = mock_call_tool.call_args
    assert kwargs["images"] == [(b"fake-png-bytes", "image/png")]
