"""Validate extraction JSON against the strict action-item schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from meetingpilot.extraction import validate_extraction_payload
from meetingpilot.models import ExtractedItem, PlannedItem, Priority


VALID_PAYLOAD = {
    "items": [
        {
            "task": "Draft the Q3 checkout roadmap",
            "owner": "Marcus",
            "due_date_text": "Friday",
            "priority": "high",
            "source_quote": "I will draft the Q3 checkout roadmap and send it to Priya by Friday.",
            "confidence": 0.93,
        }
    ]
}


def test_valid_extraction_payload_parses():
    items = validate_extraction_payload(VALID_PAYLOAD)
    assert len(items) == 1
    item = items[0]
    assert isinstance(item, ExtractedItem)
    assert item.owner == "Marcus"
    assert item.priority == Priority.high
    assert item.confidence == pytest.approx(0.93)


def test_unknown_owner_becomes_none():
    payload = {
        "items": [
            {
                **VALID_PAYLOAD["items"][0],
                "owner": "unknown",
            }
        ]
    }
    items = validate_extraction_payload(payload)
    assert items[0].owner is None


def test_missing_required_field_raises():
    payload = {"items": [{"task": "Do the thing", "confidence": 0.5}]}
    with pytest.raises(ValueError, match="schema validation"):
        validate_extraction_payload(payload)


def test_confidence_outside_range_is_clamped_or_rejected():
    payload = {
        "items": [
            {
                **VALID_PAYLOAD["items"][0],
                "confidence": 1.4,
            }
        ]
    }
    items = validate_extraction_payload(payload)
    assert items[0].confidence == 1.0


def test_invalid_priority_rejected():
    payload = {
        "items": [
            {
                **VALID_PAYLOAD["items"][0],
                "priority": "urgent",
            }
        ]
    }
    with pytest.raises((ValueError, ValidationError)):
        validate_extraction_payload(payload)


def test_malformed_due_date_iso_becomes_none_not_a_crash():
    """Regression: a real crash was found where a malformed due_date_iso
    from the LLM (e.g. a stray JSON fragment) passed straight through
    unvalidated, then blew up any consumer calling date.fromisoformat()
    on it (Calendar, Tasks, .ics export). Must be nulled at the model
    boundary instead, so the item just gets flagged missing_due_date."""
    payload = {
        "items": [
            {
                **VALID_PAYLOAD["items"][0],
                "due_date_iso": "null,due_date_text:",
            }
        ]
    }
    items = validate_extraction_payload(payload)
    assert items[0].due_date_iso is None


def test_malformed_proposed_due_date_iso_becomes_none():
    item = PlannedItem(
        task="Do the thing",
        source_quote="quote",
        confidence=0.9,
        proposed_due_date_iso="not-a-real-date",
    )
    assert item.proposed_due_date_iso is None


def test_well_formed_due_date_iso_is_preserved():
    payload = {
        "items": [
            {
                **VALID_PAYLOAD["items"][0],
                "due_date_iso": "2026-08-21",
            }
        ]
    }
    items = validate_extraction_payload(payload)
    assert items[0].due_date_iso == "2026-08-21"
