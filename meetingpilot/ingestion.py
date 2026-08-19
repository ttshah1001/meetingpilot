"""Ingestion layer: raw transcript → speaker-turn segments."""

from __future__ import annotations

import re
from pathlib import Path

from meetingpilot.models import SpeakerTurn, TranscriptDocument

SPEAKER_LINE = re.compile(
    r"^(?:\[(?P<bracket>[^\]]+)\]|(?P<name>[A-Za-z][\w .'-]{0,40}))\s*[:\-–]\s*(?P<body>.+)$"
)
# Header fields in our sample .txt files — not dialogue.
META_SPEAKERS = {
    "meeting",
    "date",
    "attendees",
    "attendee",
    "location",
    "title",
    "agenda",
}
VTT_TS = re.compile(
    r"(?P<start>\d{2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-->\s*(?P<end>\d{2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)"
)
SRT_INDEX = re.compile(r"^\d+$")
WEBVTT_HEADER = re.compile(r"^WEBVTT", re.IGNORECASE)


def ingest_file(path: str | Path) -> TranscriptDocument:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    fmt = {".vtt": "vtt", ".srt": "srt"}.get(suffix, "txt")
    return ingest_text(text, source_name=file_path.name, fmt=fmt)


def ingest_text(
    text: str,
    source_name: str = "pasted.txt",
    fmt: str | None = None,
) -> TranscriptDocument:
    """Normalize pasted or file-backed transcript text."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not raw:
        raise ValueError("Transcript is empty.")

    detected = fmt or _detect_format(raw, source_name)
    if detected == "vtt":
        turns = _parse_cue_file(raw, kind="vtt")
    elif detected == "srt":
        turns = _parse_cue_file(raw, kind="srt")
    else:
        turns = _parse_plain(raw)

    if not turns:
        turns = [
            SpeakerTurn(index=0, speaker="Unknown", text=raw.replace("\n", " ").strip())
        ]

    return TranscriptDocument(
        source_name=source_name,
        raw_text=raw,
        turns=turns,
        format=detected,
    )


def _detect_format(text: str, source_name: str) -> str:
    lower_name = source_name.lower()
    if lower_name.endswith(".vtt") or WEBVTT_HEADER.match(text):
        return "vtt"
    if lower_name.endswith(".srt"):
        return "srt"
    if "-->" in text and VTT_TS.search(text):
        return "vtt" if "WEBVTT" in text.upper() else "srt"
    return "txt"


def _split_speaker(text: str) -> tuple[str, str]:
    match = SPEAKER_LINE.match(text.strip())
    if not match:
        return "Unknown", text.strip()
    speaker = (match.group("bracket") or match.group("name") or "Unknown").strip()
    return speaker, match.group("body").strip()


def _parse_plain(text: str) -> list[SpeakerTurn]:
    turns: list[SpeakerTurn] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        speaker, body = _split_speaker(stripped)
        if not body:
            continue
        if speaker.lower() in META_SPEAKERS:
            continue
        turns.append(
            SpeakerTurn(index=len(turns), speaker=speaker, text=body)
        )
    return turns


def _parse_cue_file(text: str, kind: str) -> list[SpeakerTurn]:
    """Parse WebVTT or SRT cue blocks into speaker turns."""
    lines = text.split("\n")
    turns: list[SpeakerTurn] = []
    i = 0
    if kind == "vtt" and lines and WEBVTT_HEADER.match(lines[0]):
        i = 1

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if kind == "srt" and SRT_INDEX.match(line):
            i += 1
            if i >= len(lines):
                break
            line = lines[i].strip()

        ts_match = VTT_TS.search(line)
        start_ts = end_ts = None
        if ts_match:
            start_ts = ts_match.group("start").replace(",", ".")
            end_ts = ts_match.group("end").replace(",", ".")
            i += 1
        else:
            # Cue text without a timestamp on this line
            pass

        payload: list[str] = []
        while i < len(lines) and lines[i].strip():
            if VTT_TS.search(lines[i]):
                break
            payload.append(lines[i].strip())
            i += 1
        body = " ".join(payload).strip()
        if not body:
            continue
        speaker, spoken = _split_speaker(body)
        if speaker.lower() in META_SPEAKERS:
            continue
        turns.append(
            SpeakerTurn(
                index=len(turns),
                speaker=speaker,
                text=spoken,
                start_ts=start_ts,
                end_ts=end_ts,
            )
        )
    return turns
