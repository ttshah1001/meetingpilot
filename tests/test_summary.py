"""Summary + diagram synthesis (optional LLM call #3) — mocked, no live network."""

from __future__ import annotations

from unittest.mock import patch

from meetingpilot.ingestion import ingest_text
from meetingpilot.models import MeetingSummary, Screenshot
from meetingpilot.summary import generate_summary, refine_summary


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


@patch("meetingpilot.summary.call_tool_choice")
def test_refine_summary_applies_feedback(mock_call_tool_choice):
    mock_call_tool_choice.return_value = (
        "submit_summary",
        {
            "summary": "Shorter version: Marcus will draft the roadmap by Friday.",
            "diagrams": [],
        },
    )
    current = MeetingSummary(summary="A much longer original summary about the roadmap.", diagrams=[])
    doc = ingest_text("Marcus: I will draft the roadmap by Friday.", source_name="t.txt")

    kind, result = refine_summary(current, "make it shorter", doc)
    assert kind == "summary"
    assert result.summary == "Shorter version: Marcus will draft the roadmap by Friday."


@patch("meetingpilot.summary.call_tool_choice")
def test_refine_summary_includes_current_draft_and_feedback_in_prompt(mock_call_tool_choice):
    mock_call_tool_choice.return_value = ("submit_summary", {"summary": "revised", "diagrams": []})
    current = MeetingSummary(summary="original draft text", diagrams=[])
    doc = ingest_text("Some transcript.", source_name="t.txt")

    refine_summary(current, "add more detail about Marcus", doc)

    _, kwargs = mock_call_tool_choice.call_args
    assert "original draft text" in kwargs["user"]
    assert "add more detail about Marcus" in kwargs["user"]


@patch("meetingpilot.summary.call_tool_choice")
def test_refine_summary_replies_in_chat_for_off_topic_message(mock_call_tool_choice):
    mock_call_tool_choice.return_value = (
        "reply_in_chat",
        {"message": "This chat only edits the summary/diagrams -- use the Draft Gmail button for that."},
    )
    current = MeetingSummary(summary="original draft text", diagrams=[])
    doc = ingest_text("Raj: I'll send the heads-up email today.", source_name="t.txt")

    kind, result = refine_summary(current, "can u give me a draft for the email raj is supposed to send", doc)
    assert kind == "chat"
    assert "Draft Gmail" in result
