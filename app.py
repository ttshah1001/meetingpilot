"""Streamlit interface layer for MeetingPilot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st

from meetingpilot.calendar_tool import push_item
from meetingpilot.config import PROJECT_ROOT, get_settings
from meetingpilot.ingestion import ingest_text
from meetingpilot.memory import list_open_items
from meetingpilot.pipeline import process_meeting

SAMPLES = PROJECT_ROOT / "samples"


def _sample_names() -> list[str]:
    if not SAMPLES.exists():
        return []
    return sorted(
        p.name
        for p in SAMPLES.iterdir()
        if p.suffix.lower() in {".txt", ".vtt", ".srt"}
    )


def main() -> None:
    st.set_page_config(page_title="MeetingPilot", layout="wide")
    st.title("MeetingPilot")
    st.caption("Transcript → action items → memory → calendar")

    settings = get_settings()
    dry_run = st.sidebar.checkbox(
        "Calendar dry-run (recommended for demo)",
        value=True,
        help="Prints the exact Google Calendar API payload instead of creating events.",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Open items from previous meetings")
    try:
        previous = list_open_items()
    except Exception as exc:  # noqa: BLE001
        previous = []
        st.sidebar.warning(f"Memory DB not ready yet: {exc}")

    if previous:
        for item in previous:
            due = item.due_date_iso or "—"
            st.sidebar.markdown(
                f"**{item.owner or 'unassigned'}** — {item.task}  \n"
                f"from *{item.meeting_title}* · due {due} · {item.priority.value}"
            )
    else:
        st.sidebar.info("No open items in memory yet. Process a meeting to start tracking.")

    meeting_title = st.text_input("Meeting title", value="Weekly sync")
    meeting_date = st.date_input("Meeting date", value=date.today())
    sample_choice = st.selectbox("Load a sample transcript", ["(none)"] + _sample_names())
    uploaded = st.file_uploader("Upload transcript (.txt, .vtt, .srt)", type=["txt", "vtt", "srt"])
    pasted = st.text_area("…or paste transcript text", height=220)

    transcript_text = pasted
    source_name = "pasted.txt"
    if uploaded is not None:
        transcript_text = uploaded.getvalue().decode("utf-8")
        source_name = uploaded.name
    elif sample_choice != "(none)":
        sample_path = SAMPLES / sample_choice
        transcript_text = sample_path.read_text(encoding="utf-8")
        source_name = sample_choice

    if st.button("Process Meeting", type="primary", disabled=not (transcript_text or "").strip()):
        if not settings.anthropic_api_key:
            st.error(
                "ANTHROPIC_API_KEY is missing. Copy `.env.example` to `.env` and add your key."
            )
            st.stop()
        fmt = {".vtt": "vtt", ".srt": "srt"}.get(Path(source_name).suffix.lower())
        document = ingest_text(transcript_text, source_name=source_name, fmt=fmt)
        with st.spinner("Extraction (LLM #1), then planning (LLM #2)…"):
            st.session_state["result"] = process_meeting(
                document=document,
                meeting_date=meeting_date,
                title=meeting_title,
                persist=True,
            )
            st.session_state["last_payloads"] = []

    result = st.session_state.get("result")
    if not result:
        st.info("Load a sample or paste a transcript, then click **Process Meeting**.")
        return

    st.success(
        f"Saved meeting #{result.meeting_id}: {len(result.planned)} planned item(s) "
        f"from {len(result.turns)} speaker turns "
        f"({len(result.extracted)} extracted before the planning pass)."
    )
    if result.open_from_previous:
        st.warning(
            f"{len(result.open_from_previous)} still-open item(s) from earlier meetings "
            "are listed in the sidebar."
        )

    st.subheader("Action items (grouped by owner)")
    grouped: dict[str, list] = {}
    for item in sorted(result.planned, key=lambda row: (row.owner or "zzz", row.rank)):
        grouped.setdefault(item.owner or "Unassigned", []).append(item)

    for owner, items in grouped.items():
        st.markdown(f"### {owner}")
        for item in items:
            flags = []
            if item.needs_review:
                flags.append("needs review")
            if item.missing_owner:
                flags.append("missing owner")
            if item.missing_due_date:
                flags.append("missing date")
            flag_text = f" · {' · '.join(flags)}" if flags else ""
            header = (
                f"#{item.rank} {item.task} — {item.priority.value} · "
                f"{item.confidence:.0%}{flag_text}"
            )
            with st.expander(header):
                st.write(
                    f"**Due:** {item.due_date_iso or item.proposed_due_date_iso or '—'} "
                    f"(spoken as: {item.due_date_text or '—'})"
                )
                if item.proposed_owner:
                    st.write(f"**Proposed owner:** {item.proposed_owner}")
                st.write("**Source quote**")
                st.markdown(f"> {item.source_quote}")
                if item.merged_from_quotes:
                    st.caption("Also merged from:")
                    for quote in item.merged_from_quotes:
                        st.markdown(f"> {quote}")
                if item.still_open_from_last_time:
                    st.info(
                        "Still open from last time:\n\n- "
                        + "\n- ".join(item.still_open_from_last_time)
                    )
                if item.planning_notes:
                    st.caption(item.planning_notes)
                due = item.due_date_iso or item.proposed_due_date_iso
                if st.button(
                    "Push to Calendar",
                    key=f"push-{owner}-{item.rank}-{hash(item.task)}",
                    disabled=not due,
                ):
                    _do_push(item, dry_run=dry_run)

    if st.button("Push all dated items to Calendar"):
        dated = [i for i in result.planned if i.due_date_iso or i.proposed_due_date_iso]
        for item in dated:
            _do_push(item, dry_run=dry_run)
        st.success(f"Processed {len(dated)} calendar payload(s). dry-run={dry_run}")

    payloads = st.session_state.get("last_payloads") or []
    if payloads:
        st.subheader("Calendar API payloads")
        for payload in payloads:
            st.code(json.dumps(payload, indent=2), language="json")

    st.subheader("Normalized speaker turns")
    st.dataframe(
        [
            {
                "speaker": turn.speaker,
                "start": turn.start_ts,
                "end": turn.end_ts,
                "text": turn.text,
            }
            for turn in result.turns
        ],
        use_container_width=True,
        hide_index=True,
    )


def _do_push(item, *, dry_run: bool) -> None:
    try:
        result = push_item(item, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return
    st.session_state.setdefault("last_payloads", []).append(result.payload)
    if dry_run:
        st.caption("Dry-run: payload captured below — nothing was sent to Google.")
    else:
        st.success(f"Created calendar event {result.event_id}")


if __name__ == "__main__":
    main()
