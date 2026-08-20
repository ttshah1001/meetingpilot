"""Streamlit UI helper logic — the bulk-action owner filter."""

from __future__ import annotations

from app import _filter_by_owner
from meetingpilot.models import PlannedItem, Priority


def _item(task: str, owner: str | None, proposed_owner: str | None = None) -> PlannedItem:
    return PlannedItem(
        task=task,
        owner=owner,
        proposed_owner=proposed_owner,
        due_date_iso="2026-08-21",
        priority=Priority.medium,
        source_quote="quote",
        confidence=0.9,
    )


def test_empty_name_returns_everything():
    items = [_item("A", "Marcus"), _item("B", "Priya")]
    assert _filter_by_owner(items, "") == items


def test_filters_to_matching_owner_case_insensitive():
    items = [_item("A", "Marcus"), _item("B", "Priya")]
    result = _filter_by_owner(items, "marcus")
    assert [i.task for i in result] == ["A"]


def test_matches_proposed_owner_too():
    items = [_item("A", None, proposed_owner="Sai"), _item("B", "Priya")]
    result = _filter_by_owner(items, "sai")
    assert [i.task for i in result] == ["A"]


def test_no_match_returns_empty():
    items = [_item("A", "Marcus")]
    assert _filter_by_owner(items, "nobody-here") == []
