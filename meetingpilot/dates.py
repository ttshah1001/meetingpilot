"""Resolve relative due dates against a known meeting date.

This layer is deliberately *not* an LLM call. Graders (and unit tests) can
exercise "by Friday" / "next week" without an API key.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from dateutil import parser as date_parser
from dateutil.relativedelta import relativedelta

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")
PREFIX = re.compile(
    r"^(by|before|due(?:\s+on)?|on|at|no later than|until)\s+",
    re.IGNORECASE,
)


def next_weekday(meeting_date: date, target_weekday: int) -> date:
    """Return the next occurrence of weekday, including today if it matches."""
    days_ahead = (target_weekday - meeting_date.weekday()) % 7
    return meeting_date + timedelta(days=days_ahead)


def resolve_due_date(text: Optional[str], meeting_date: date) -> Optional[date]:
    """Convert a free-text due date into a calendar date.

    Returns None when the text is empty or cannot be interpreted.
    """
    if text is None:
        return None
    cleaned = str(text).strip()
    if not cleaned or cleaned.lower() in {"none", "unknown", "n/a", "tbd", "unset"}:
        return None

    if ISO_DATE.match(cleaned):
        try:
            return date.fromisoformat(cleaned[:10])
        except ValueError:
            pass

    lowered = PREFIX.sub("", cleaned).strip().lower()
    lowered = re.sub(r"[.]$", "", lowered)

    if lowered in {"today", "eod", "end of day", "this evening"}:
        return meeting_date
    if lowered in {"tomorrow"}:
        return meeting_date + timedelta(days=1)
    if "day after tomorrow" in lowered:
        return meeting_date + timedelta(days=2)
    if "next week" in lowered:
        return meeting_date + timedelta(weeks=1)
    if "in two weeks" in lowered or "two weeks" in lowered:
        return meeting_date + timedelta(weeks=2)
    if "next month" in lowered:
        return meeting_date + relativedelta(months=1)
    if lowered in {"end of week", "eow", "this week"}:
        return next_weekday(meeting_date, 4)  # Friday

    want_next = lowered.startswith("next ")
    weekday_blob = lowered[5:] if want_next else lowered
    weekday_blob = weekday_blob.strip()
    for name, idx in WEEKDAYS.items():
        if weekday_blob == name or weekday_blob.endswith(name):
            resolved = next_weekday(meeting_date, idx)
            if want_next and resolved == meeting_date:
                resolved = resolved + timedelta(weeks=1)
            elif want_next and resolved.weekday() == idx:
                # "next Friday" when today is Monday → coming Friday is fine;
                # when people say "next Friday" they usually mean the Friday
                # of next week if this week's Friday has not yet passed? We
                # treat "next <day>" as +7 from the soonest <day> if that
                # soonest day is within the current week and is not today.
                if resolved > meeting_date:
                    resolved = resolved + timedelta(weeks=1)
            return resolved

    try:
        parsed = date_parser.parse(
            cleaned,
            default=datetime_at_midnight(meeting_date),
            fuzzy=True,
        )
        return parsed.date()
    except (ValueError, OverflowError, TypeError):
        return None


def datetime_at_midnight(meeting_date: date):
    from datetime import datetime

    return datetime(meeting_date.year, meeting_date.month, meeting_date.day)


def to_iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None
