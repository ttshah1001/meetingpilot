"""Date resolution against a known meeting date (no LLM)."""

from __future__ import annotations

from datetime import date

from meetingpilot.dates import resolve_due_date

# Wednesday, 19 August 2026
MEETING = date(2026, 8, 19)


def test_iso_passthrough():
    assert resolve_due_date("2026-08-28", MEETING) == date(2026, 8, 28)


def test_today_and_tomorrow():
    assert resolve_due_date("today", MEETING) == MEETING
    assert resolve_due_date("tomorrow", MEETING) == date(2026, 8, 20)


def test_by_friday_is_this_week():
    assert resolve_due_date("by Friday", MEETING) == date(2026, 8, 21)
    assert resolve_due_date("Friday", MEETING) == date(2026, 8, 21)


def test_next_friday_is_following_week():
    assert resolve_due_date("next Friday", MEETING) == date(2026, 8, 28)


def test_next_week():
    assert resolve_due_date("next week", MEETING) == date(2026, 8, 26)


def test_end_of_week_is_friday():
    assert resolve_due_date("end of week", MEETING) == date(2026, 8, 21)


def test_empty_and_unknown_return_none():
    assert resolve_due_date(None, MEETING) is None
    assert resolve_due_date("TBD", MEETING) is None
    assert resolve_due_date("", MEETING) is None
