"""Streamlit interface layer for MeetingPilot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from meetingpilot.calendar_tool import push_item
from meetingpilot.config import get_settings
from meetingpilot.gmail_tool import create_draft
from meetingpilot.ics_export import build_ics_bundle_bytes, build_ics_bytes, ics_filename
from meetingpilot.ingestion import ingest_text
from meetingpilot.memory import list_open_items
from meetingpilot.models import SCREENSHOT_MIME_BY_EXTENSION, Screenshot
from meetingpilot.pipeline import process_meeting
from meetingpilot.summary import refine_summary
from meetingpilot.tasks_tool import push_task

TRANSCRIPT_EXTENSIONS = (".txt", ".vtt", ".srt")
SCREENSHOT_EXTENSIONS = tuple(SCREENSHOT_MIME_BY_EXTENSION)

def _filter_by_owner(items: list, name: str) -> list:
    """Bulk-action filter: only items whose owner/proposed owner matches
    `name` (case-insensitive substring). Empty name = no filtering."""
    if not name:
        return items
    needle = name.strip().lower()
    return [
        item
        for item in items
        if needle in (item.owner or "").lower() or needle in (item.proposed_owner or "").lower()
    ]


def main() -> None:
    st.set_page_config(page_title="MeetingPilot", layout="wide")
    _inject_theme_css()
    st.title("MeetingPilot")
    st.markdown(
        '<p style="font-style: italic; color: #5C3D2E; font-size: 1.1rem; margin-top: -8px;">'
        "From transcript to clarity — tasks, summaries, and diagrams, automatically."
        "</p>",
        unsafe_allow_html=True,
    )

    settings = get_settings()

    st.sidebar.subheader("Your setup")
    my_name_filter = st.sidebar.text_input(
        "Your name",
        placeholder="e.g. Sai",
        help="Matched case-insensitively against each item's owner.",
    ).strip()
    st.sidebar.caption(
        "Why: with this set, the bulk **\"Push all\"** and **\"Download all\"** buttons only grab tasks "
        "assigned to you — not your whole team's. Per-item buttons on individual cards always work "
        "regardless of this field."
    )
    calendar_id = st.sidebar.text_input(
        "Calendar for live events",
        placeholder="primary",
        help="Google Calendar → that calendar's Settings → 'Integrate calendar' → Calendar ID.",
    ).strip() or None
    st.sidebar.caption(
        "Why: leave blank to use your main calendar. Paste a dedicated calendar's ID instead to keep "
        "test/demo events separate from your real one — hide or delete them all with one click later "
        "instead of hunting down individual events."
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

    st.sidebar.markdown("---")
    with st.sidebar.expander("⚙️ Testing & advanced options"):
        st.caption(
            "These control whether actions touch Google's real systems. Dry-run means safe: "
            "nothing is created, you just see the exact payload. Turn a toggle off only when you "
            "actually want that action to happen for real."
        )
        dry_run = st.checkbox(
            "Calendar dry-run",
            value=True,
            help="Prints the exact Google Calendar API payload instead of creating events.",
        )
        gmail_dry_run = st.checkbox(
            "Gmail dry-run",
            value=True,
            help="Shows the exact draft MIME content instead of creating a real Gmail draft. Never sends either way.",
        )
        tasks_dry_run = st.checkbox(
            "Google Tasks dry-run",
            value=True,
            help="Prints the exact Google Tasks API payload instead of creating a real, checkable to-do.",
        )
        generate_summary_from_content = st.checkbox(
            "Generate summary + diagrams",
            value=False,
            help="Extra LLM call: a detailed text summary plus zero or more Mermaid diagrams reconstructed "
            "from a whiteboard/flowchart screenshot or a process described in the transcript. The model "
            "decides how many diagrams are warranted (0, 1, or more) — off by default since it's an extra "
            "call and not every meeting has anything summary/diagram-worthy.",
        )

    meeting_title = st.text_input("Meeting title", value="Weekly sync")
    meeting_date = st.date_input("Meeting date", value=date.today())
    uploaded_files = st.file_uploader(
        "Drop transcript + screenshots (.txt/.vtt/.srt + .png/.jpg)",
        type=["txt", "vtt", "srt", "png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    pasted = st.text_area("…or paste transcript text", height=220)

    transcript_files = [
        f for f in uploaded_files if Path(f.name).suffix.lower() in TRANSCRIPT_EXTENSIONS
    ]
    screenshot_files = [
        f for f in uploaded_files if Path(f.name).suffix.lower() in SCREENSHOT_EXTENSIONS
    ]
    if len(transcript_files) > 1:
        st.error(
            f"Got {len(transcript_files)} transcript files "
            f"({', '.join(f.name for f in transcript_files)}) — drop only one at a time."
        )
        st.stop()

    transcript_text = pasted
    source_name = "pasted.txt"
    if transcript_files:
        transcript_text = transcript_files[0].getvalue().decode("utf-8")
        source_name = transcript_files[0].name

    if screenshot_files:
        st.caption(f"{len(screenshot_files)} screenshot(s) attached: " + ", ".join(f.name for f in screenshot_files))

    if st.button("Process Meeting", type="primary", disabled=not (transcript_text or "").strip()):
        if not settings.gemini_api_key:
            st.error(
                "GEMINI_API_KEY is missing. Copy `.env.example` to `.env` and add your key."
            )
            st.stop()
        fmt = {".vtt": "vtt", ".srt": "srt"}.get(Path(source_name).suffix.lower())
        document = ingest_text(transcript_text, source_name=source_name, fmt=fmt)
        screenshots = [
            Screenshot(
                name=f.name,
                mime_type=SCREENSHOT_MIME_BY_EXTENSION[Path(f.name).suffix.lower()],
                data=f.getvalue(),
            )
            for f in screenshot_files
        ]
        spinner_text = (
            f"Extraction (LLM #1, reading transcript + {len(screenshots)} screenshot(s)), then planning (LLM #2)…"
            if screenshots
            else "Extraction (LLM #1), then planning (LLM #2)…"
        )
        if generate_summary_from_content:
            spinner_text += " Also generating a summary + diagrams (LLM #3)…"
        with st.spinner(spinner_text):
            st.session_state["result"] = process_meeting(
                document=document,
                meeting_date=meeting_date,
                title=meeting_title,
                persist=True,
                screenshots=screenshots or None,
                generate_summary_from_content=generate_summary_from_content,
            )
            st.session_state["last_payloads"] = []
            st.session_state["last_gmail_drafts"] = []
            st.session_state["last_task_payloads"] = []
            st.session_state["last_document"] = document
            st.session_state["last_screenshots"] = screenshots
            st.session_state["summary_chat_history"] = []

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

    if result.summary is not None:
        if result.summary.summary:
            st.subheader("Summary")
            st.write(result.summary.summary)
        if result.summary.diagrams:
            for i, diagram in enumerate(result.summary.diagrams):
                st.subheader(f"Diagram: {diagram.title}")
                _render_mermaid(diagram.mermaid_code, key=str(i), file_stem=diagram.title)
                with st.expander("Mermaid source"):
                    st.code(diagram.mermaid_code, language="text")
        elif not result.summary.summary:
            st.caption("Summary check: nothing meaningfully describable found in the transcript/screenshots.")

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
            source_icon = "🖼️ screenshot" if item.source.value == "screenshot" else "📝 transcript"
            header = (
                f"#{item.rank} {item.task} — {item.priority.value} · "
                f"{item.confidence:.0%} · {source_icon}{flag_text}"
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
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    if st.button(
                        "Push to Calendar",
                        key=f"push-{owner}-{item.rank}-{hash(item.task)}",
                        disabled=not due,
                    ):
                        _do_push(item, dry_run=dry_run, calendar_id=calendar_id)
                with col2:
                    if st.button(
                        "Draft Gmail",
                        key=f"gmail-{owner}-{item.rank}-{hash(item.task)}",
                    ):
                        _do_gmail_draft(item, dry_run=gmail_dry_run)
                with col3:
                    if st.button(
                        "Add to Tasks",
                        key=f"tasks-{owner}-{item.rank}-{hash(item.task)}",
                        disabled=not due,
                    ):
                        _do_push_task(item, dry_run=tasks_dry_run)
                with col4:
                    if due:
                        st.download_button(
                            "Download .ics",
                            data=build_ics_bytes(item),
                            file_name=ics_filename(item),
                            mime="text/calendar",
                            key=f"ics-{owner}-{item.rank}-{hash(item.task)}",
                        )
                    else:
                        st.button(
                            "Download .ics",
                            disabled=True,
                            key=f"ics-disabled-{owner}-{item.rank}-{hash(item.task)}",
                        )

    dated_items = [i for i in result.planned if i.due_date_iso or i.proposed_due_date_iso]
    bulk_items = _filter_by_owner(dated_items, my_name_filter)
    filter_note = f" owned by '{my_name_filter}'" if my_name_filter else ""

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button(f"Push all {len(bulk_items)} dated item(s){filter_note} to Calendar"):
            st.session_state["last_payloads"] = []
            succeeded = sum(
                _do_push(item, dry_run=dry_run, calendar_id=calendar_id) for item in bulk_items
            )
            failed = len(bulk_items) - succeeded
            if failed:
                st.warning(f"{succeeded}/{len(bulk_items)} succeeded, {failed} failed (see errors above). dry-run={dry_run}")
            else:
                st.success(f"Processed {succeeded} calendar payload(s). dry-run={dry_run}")
    with col_b:
        if st.button(f"Push all {len(bulk_items)} dated item(s){filter_note} to Tasks"):
            st.session_state["last_task_payloads"] = []
            succeeded = sum(_do_push_task(item, dry_run=tasks_dry_run) for item in bulk_items)
            failed = len(bulk_items) - succeeded
            if failed:
                st.warning(f"{succeeded}/{len(bulk_items)} succeeded, {failed} failed (see errors above). dry-run={tasks_dry_run}")
            else:
                st.success(f"Processed {succeeded} task payload(s). dry-run={tasks_dry_run}")
    with col_c:
        st.download_button(
            f"Download {len(bulk_items)} dated item(s){filter_note} as one .ics",
            data=build_ics_bundle_bytes(bulk_items),
            file_name=f"{result.title.lower().replace(' ', '-')}-action-items.ics",
            mime="text/calendar",
            disabled=not bulk_items,
        )

    payloads = st.session_state.get("last_payloads") or []
    if payloads:
        st.subheader("Calendar API payloads")
        if st.button("Clear log", key="clear-calendar-log"):
            st.session_state["last_payloads"] = []
            st.rerun()
        for payload in payloads:
            st.code(json.dumps(payload, indent=2), language="json")

    drafts = st.session_state.get("last_gmail_drafts") or []
    if drafts:
        st.subheader("Gmail drafts (draft-only, never sent)")
        if st.button("Clear log", key="clear-gmail-log"):
            st.session_state["last_gmail_drafts"] = []
            st.rerun()
        for preview in drafts:
            st.code(preview, language="text")

    task_payloads = st.session_state.get("last_task_payloads") or []
    if task_payloads:
        st.subheader("Google Tasks API payloads")
        if st.button("Clear log", key="clear-tasks-log"):
            st.session_state["last_task_payloads"] = []
            st.rerun()
        for payload in task_payloads:
            st.code(json.dumps(payload, indent=2), language="json")

    if result.summary is not None:
        st.markdown("---")
        st.subheader("Refine summary / diagrams")
        st.caption(
            'Chat here to request changes — e.g. "make it shorter", "add a diagram for the '
            'deployment flow", "rename the second diagram". Each message regenerates the summary '
            "and diagrams shown above, grounded in the same transcript/screenshots — not a rewrite "
            "from scratch."
        )
        chat_history = st.session_state.setdefault("summary_chat_history", [])
        chat_box = st.container(height=360, border=True)
        with chat_box:
            if not chat_history:
                st.caption("No messages yet — ask for a change below.")
            for msg in chat_history:
                _render_chat_bubble(msg["role"], msg["content"])
            # Placed inside this fixed-height container so it pins to the
            # bottom of the *chat box*, not the whole page — otherwise
            # st.chat_input floats to the absolute page bottom regardless
            # of where it's called, ending up visually below unrelated
            # content (e.g. the speaker-turns table) rendered after it.
            feedback = st.chat_input("Ask for a change to the summary or diagrams…")
        if feedback:
            chat_history.append({"role": "user", "content": feedback})
            last_document = st.session_state.get("last_document")
            last_screenshots = st.session_state.get("last_screenshots")
            if last_document is None:
                chat_history.append(
                    {
                        "role": "assistant",
                        "content": "Can't refine — the original transcript for this session isn't "
                        "available (likely processed before this feature was added). Reprocess the "
                        "meeting once, then refinement will work.",
                    }
                )
            else:
                with st.spinner("Regenerating summary + diagrams…"):
                    try:
                        updated = refine_summary(
                            result.summary,
                            feedback,
                            last_document,
                            screenshots=last_screenshots or None,
                        )
                        result.summary = updated
                        st.session_state["result"] = result
                        chat_history.append(
                            {"role": "assistant", "content": "Updated the summary and diagrams above."}
                        )
                    except Exception as exc:  # noqa: BLE001
                        chat_history.append({"role": "assistant", "content": f"Couldn't apply that: {exc}"})
            st.rerun()

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


def _render_mermaid(mermaid_code: str, *, key: str, file_stem: str = "diagram") -> None:
    """Render Mermaid syntax via mermaid.js loaded from a CDN, with real
    client-side SVG/PNG download buttons.

    This Streamlit version has no native Mermaid support, so the diagram
    is rendered inside an embedded HTML component instead. mermaid.js
    already produces the SVG in the browser — the download buttons just
    save that output, no server round-trip needed.
    """
    safe_code = json.dumps(mermaid_code)
    safe_stem = json.dumps(_slugify(file_stem))
    node_id = f"mp-diagram-{key}"
    components.html(
        f"""
        <div class="mermaid" id="{node_id}"></div>
        <div id="{node_id}-controls" style="display:none; margin-top:8px;">
            <button id="{node_id}-svg-btn">Download SVG</button>
            <button id="{node_id}-png-btn">Download PNG</button>
        </div>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
        <script>
            mermaid.initialize({{ startOnLoad: false, theme: "neutral" }});
            const code = {safe_code};
            const stem = {safe_stem};
            const container = document.getElementById("{node_id}");
            const controls = document.getElementById("{node_id}-controls");

            function downloadBlob(blob, filename) {{
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = filename;
                a.click();
                URL.revokeObjectURL(url);
            }}

            mermaid.render("{node_id}-svg", code).then(({{ svg }}) => {{
                container.innerHTML = svg;
                controls.style.display = "block";

                document.getElementById("{node_id}-svg-btn").onclick = () => {{
                    downloadBlob(new Blob([svg], {{ type: "image/svg+xml" }}), stem + ".svg");
                }};

                document.getElementById("{node_id}-png-btn").onclick = () => {{
                    const img = new Image();
                    const svgUrl = URL.createObjectURL(
                        new Blob([svg], {{ type: "image/svg+xml;charset=utf-8" }})
                    );
                    img.onload = () => {{
                        const scale = 2; // render at 2x for a crisper PNG
                        const canvas = document.createElement("canvas");
                        canvas.width = img.naturalWidth * scale;
                        canvas.height = img.naturalHeight * scale;
                        const ctx = canvas.getContext("2d");
                        ctx.fillStyle = "white";
                        ctx.fillRect(0, 0, canvas.width, canvas.height);
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                        URL.revokeObjectURL(svgUrl);
                        canvas.toBlob((blob) => downloadBlob(blob, stem + ".png"));
                    }};
                    img.src = svgUrl;
                }};
            }}).catch((err) => {{
                container.innerHTML = "<pre>Mermaid render error: " + err + "</pre>";
            }});
        </script>
        """,
        height=460,
        scrolling=True,
    )


def _slugify(text: str) -> str:
    import re

    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "diagram"


def _render_chat_bubble(role: str, content: str) -> None:
    """Custom-styled chat bubble, not relying on Streamlit's internal
    st.chat_message DOM structure (which varies by version) for the
    user-vs-assistant color distinction — this guarantees it regardless."""
    is_user = role == "user"
    bg = "#F0C9A8" if is_user else "#FDF8EE"
    label = "You" if is_user else "MeetingPilot"
    align = "flex-end" if is_user else "flex-start"
    st.markdown(
        f"""
        <div style="display:flex; justify-content:{align}; margin-bottom:10px;">
            <div style="max-width:85%; background-color:{bg}; border:1px solid #D4B896;
                        border-radius:12px; padding:10px 14px;">
                <div style="font-size:0.75rem; font-weight:600; color:#5C3D2E; margin-bottom:4px;">
                    {label}
                </div>
                <div style="color:#2C1810;">{content}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _inject_theme_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&family=DM+Sans:wght@300;400;500;600&family=DM+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
        h1, h2, h3 { font-family: 'Playfair Display', Georgia, serif !important; color: #2C1810 !important; }
        code, pre, [data-testid="stCodeBlock"] * { font-family: 'DM Mono', monospace !important; }

        /* Streamlit reserves a large top margin above the content by
        default -- pull it up so the title isn't floating in empty space. */
        .block-container { padding-top: 1.5rem !important; }
        [data-testid="stSidebar"] .block-container { padding-top: 1.5rem !important; }

        /* App-generated / displayed content text — bigger and more readable
        (separate from the input-field font-size rule below, which covers
        what the user types). Covers summary text, action item bodies,
        expander headers, captions, chat bubble text. */
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stExpander"] summary,
        [data-testid="stExpander"] p {
            font-size: 1.08rem !important;
            line-height: 1.55 !important;
        }
        [data-testid="stCaptionContainer"], .stCaption {
            font-size: 0.95rem !important;
        }

        /* Bigger, higher-contrast text in every input-shaped widget */
        input, textarea, select,
        [data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
        [data-baseweb="select"] * {
            font-size: 1.08rem !important;
            color: #2C1810 !important;
        }
        [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
        [data-testid="stChatInput"] textarea {
            border: 1.5px solid #9B7B6A !important;
            border-radius: 8px !important;
            background-color: #FDF8EE !important;
        }
        [data-testid="stTextInput"] input:focus, [data-testid="stTextArea"] textarea:focus,
        [data-testid="stChatInput"] textarea:focus {
            border-color: #C8521A !important;
            box-shadow: 0 0 0 1px #C8521A !important;
        }
        /* Streamlit's "Press Enter to apply" hint -- make it visible, not gray-on-gray */
        [data-testid*="InputInstructions"], [data-testid*="inputInstructions"] {
            color: #C8521A !important;
            font-weight: 600 !important;
        }

        [data-testid="stExpander"] {
            border: 1.5px solid #9B7B6A !important;
            border-radius: 10px !important;
            background-color: #FAF3E4 !important;
            margin-bottom: 8px;
        }
        .stButton > button, .stDownloadButton > button {
            border-radius: 8px !important;
            border: 1.5px solid #9B7B6A !important;
            font-size: 1rem !important;
        }
        .stButton > button[kind="primary"] {
            background-color: #C8521A !important;
            border-color: #C8521A !important;
            color: #FDF8EE !important;
            font-weight: 600 !important;
        }
        [data-testid="stFileUploader"], [data-testid="stTextArea"] textarea {
            border-radius: 10px !important;
        }
        /* Sidebar: darker card tone so it visibly separates from the main page */
        [data-testid="stSidebar"] {
            background-color: #EADFC0 !important;
            border-right: 1px solid #9B7B6A;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _do_push(item, *, dry_run: bool, calendar_id: str | None = None) -> bool:
    try:
        result = push_item(item, dry_run=dry_run, calendar_id=calendar_id)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return False
    st.session_state.setdefault("last_payloads", []).append(result.payload)
    if dry_run:
        st.caption("Dry-run: payload captured below — nothing was sent to Google.")
    else:
        st.success(f"Created calendar event {result.event_id}")
    return True


def _do_gmail_draft(item, *, dry_run: bool) -> bool:
    try:
        result = create_draft(item, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return False
    st.session_state.setdefault("last_gmail_drafts", []).append(result.mime_preview)
    if dry_run:
        st.caption("Dry-run: MIME content captured below — no draft was created, nothing was sent.")
    else:
        st.success(f"Created Gmail draft {result.draft_id} (draft only — not sent)")
    return True


def _do_push_task(item, *, dry_run: bool) -> bool:
    try:
        result = push_task(item, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        st.error(str(exc))
        return False
    st.session_state.setdefault("last_task_payloads", []).append(result.payload)
    if dry_run:
        st.caption("Dry-run: payload captured below — nothing was sent to Google.")
    else:
        st.success(f"Created Google Task {result.task_id}")
    return True


if __name__ == "__main__":
    main()
