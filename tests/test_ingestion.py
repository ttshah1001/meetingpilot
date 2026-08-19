"""Ingestion smoke tests for the sample files (no LLM)."""

from __future__ import annotations

from meetingpilot.config import PROJECT_ROOT
from meetingpilot.ingestion import ingest_file

SAMPLES = PROJECT_ROOT / "samples"


def test_plain_text_speakers():
    doc = ingest_file(SAMPLES / "01_sprint_planning.txt")
    speakers = {t.speaker for t in doc.turns}
    assert {"Priya", "Marcus", "Lin", "Samir"} <= speakers
    assert "Meeting" not in speakers
    assert "Date" not in speakers
    assert all(t.start_ts is None for t in doc.turns)


def test_vtt_timestamps_and_speakers():
    doc = ingest_file(SAMPLES / "02_design_review.vtt")
    assert doc.format == "vtt"
    assert doc.turns[0].start_ts is not None
    speakers = {t.speaker for t in doc.turns}
    assert {"Jordan", "Avery", "Riley"} <= speakers
