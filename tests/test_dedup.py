"""Deterministic planning-layer dedup (no LLM)."""

from __future__ import annotations

from datetime import date

from meetingpilot.models import ExtractedItem, Priority
from meetingpilot.planning import (
    apply_defaults,
    deduplicate_items,
    should_merge,
    task_similarity,
)

MEETING = date(2026, 8, 19)


def _item(task: str, owner: str | None, quote: str, confidence: float = 0.8) -> ExtractedItem:
    return ExtractedItem(
        task=task,
        owner=owner,
        due_date_iso="2026-08-21",
        due_date_text="Friday",
        priority=Priority.medium,
        source_quote=quote,
        confidence=confidence,
    )


def test_similar_tasks_same_owner_merge():
    a = _item(
        "Draft the Q3 checkout roadmap",
        "Marcus",
        "I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
        0.9,
    )
    b = _item(
        "Draft the Q3 checkout roadmap and circulate it",
        "Marcus",
        "I will draft the Q3 checkout roadmap and circulate it.",
        0.7,
    )
    assert should_merge(a, b)
    merged = deduplicate_items([a, b])
    assert len(merged) == 1
    assert merged[0].owner == "Marcus"
    assert merged[0].confidence == 0.9


def test_different_owners_do_not_merge():
    a = _item("Write the regression test plan", "Samir", "I'll write the test plan")
    b = _item("Write the regression test plan", "Priya", "Priya will write the test plan")
    assert not should_merge(a, b)
    assert len(deduplicate_items([a, b])) == 2


def test_unrelated_tasks_stay_separate():
    a = _item("Draft the Q3 checkout roadmap", "Marcus", "roadmap")
    b = _item("Mock the coupon flow in Figma", "Lin", "figma")
    assert task_similarity(a.task, b.task) < 0.4
    assert len(deduplicate_items([a, b])) == 2


def test_missing_owner_and_date_get_defaults():
    item = ExtractedItem(
        task="Book a follow-up review",
        owner=None,
        due_date_iso=None,
        due_date_text=None,
        priority=Priority.low,
        source_quote="We'll treat booking that review as unassigned",
        confidence=0.4,
    )
    planned = apply_defaults([item], MEETING, default_owner="Jordan")
    assert planned[0].missing_owner is True
    assert planned[0].missing_due_date is True
    assert planned[0].proposed_owner == "Jordan"
    assert planned[0].proposed_due_date_iso == "2026-08-26"
    assert planned[0].needs_review is True
    assert planned[0].rank == 1
