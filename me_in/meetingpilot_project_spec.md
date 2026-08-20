# MeetingPilot — Full Project Spec for Claude Code

**Purpose of this document**: This is a single reference file combining the course rubric, relevant course background, the current state of the repo, and every scoping decision made so far. Use it to (1) generate new code that stays aligned with the rubric and architecture below, and (2) audit existing/generated code against the checklist at the bottom before considering a feature "done."

Course: TAMU ENGR 689, Multimodal LLM Agents (Fall 2026, Sprint Course)
Instructors: Yu Zhang (yuzhang@tamu.edu), Cheng Zhang (chzhang@tamu.edu)

---

## 1. Course context (why this project is shaped the way it is)

### Course grading structure
- Quizzes: 40% (10% × 4, one per day, in-class)
- **Group Project: 60%**
  - Presentation: 20% (Day 5, in-class, 15 minutes)
  - Slides: 20% (due 11:59 PM Day 5)
  - Code/Demo: 20% (due 11:59 PM Day 5)

### Group project framing (from Day 1 slides, verbatim intent)
- Teams of 2-3
- **Goal: "Build a practical, demo-friendly LLM agent"**
- Example projects given by instructors: a web agent for booking tickets; a research agent that turns a paper into a website
- Any open/closed-source LLM allowed as backbone
- **"Your agent may be multimodal or primarily text-based"** — multimodality is explicitly optional, not required
- Vibe-coding tools (Cursor, Codex, Claude Code, etc.) explicitly encouraged: *"Use AI freely and extensively... A key goal of this sprint course is to help you learn how to use AI tools to rapidly build projects that would otherwise be very time-consuming to develop from scratch."*

### The course's own LLM agent architecture (Day 2, "LLM Agents: Key Components")
This diagram recurs throughout Day 2 and is the conceptual backbone the instructors are teaching toward. **MeetingPilot's architecture should map onto it explicitly** — this is the single most useful thing to put on a slide.

```
        Planning & Reasoning        Memory
                \                    /
                 \                  /
                  \                /
        Tools ---- LLM Core ---- Agent Actions
    (Search,                          |
     Calculator,                      | act
     Code, ...)                       v
                          Environment / External World
                    (Desktop OS, Web browser, Mobile apps,
                     Games, Robots, Databases, ...)
                                      |
                                      | observe
                                      v
                              (back to LLM Core)
```

Course also frames agents generally as having an **observation space** and **action space** relative to their environment (used repeatedly, e.g. for "Coding Agents": observation space = code files, execution outputs, docs, errors, commit history; action space = code editing, file search/view, test modification). Useful framing to explicitly state for MeetingPilot too (see Section 4).

### Multimodal content (Day 3) — relevant only if we lean into the vision extension
Day 3 covers vision-language models: understanding and generation, and multimodal agents. If MeetingPilot's screenshot-extraction feature is built, it is a genuine (not cosmetic) application of this material — Claude accepting image + text content blocks in the same call is real multimodal LLM usage, not just OCR bolted on.

**Important honesty note**: multimodality is NOT required by the rubric. Do not oversell it in slides/pitch if the image-input feature isn't fully working — an instructor who taught Day 3 will notice immediately if "multimodal" is claimed without real image content blocks being sent to the model.

---

## 2. Final Project Grading Rubric (verbatim)

> Your project does not need to perform a task that ChatGPT cannot already do. What matters is the layer you build around the LLM core, such as the interface, workflow, tools, memory, planning, automation, or data handling, and how effectively you demonstrate and visualize your effort.

### Presentation (20%) — 15 min in-class, Day 5, live (demo may be pre-recorded)
- Clear motivation and well-defined problem
- Clear system design and explanation of what was built around the LLM
- Smooth demo, meaningful results, and thoughtful discussion of limitations (e.g., failure cases)
- Clear organization and effective time management

### Slides (20%)
- Clear organization and coherent explanation of the architecture or workflow
- Effective use of figures, diagrams, screenshots, tables, or examples
- Thoughtful discussion of results and limitations
- Readable slides and proper acknowledgment of external resources

### Code/Demo (20%)
- Whether the documentation (e.g., README) clearly explains the system, its major components, setup requirements, and how to run it
- Whether the code runs successfully
- Whether the demo shows meaningful end-to-end behavior
- How effectively the demo or visualization communicates what your team built and the effort involved
- Repo must be a complete repository with a README, **and must be public** so instructors can access it
- Demo may be a recorded video, hosted interactive system, or another accessible webpage

**Explicitly NOT required anywhere in the rubric or Day 1 slides**: full autonomy, zero manual triggers, OS-level background automation, or a fully "self-contained" system. Manual/CLI/hotkey triggers are fine as long as documented and demoable.

---

## 3. Current repo state (as of last README)

Repo: `https://github.com/ttshah1001/meetingpilot` — **currently private, must be flipped to public before submission.**

### What exists today
- Input: pasted text, `.txt`, `.vtt`, `.srt` transcript (text-only, single file)
- Two separate LLM calls (Google Gemini, forced function calling / structured JSON output — switched from the original Anthropic implementation on 2026-08-19 to stay on the free tier; permitted by rubric Section 1, "Any open/closed-source LLM allowed as backbone"):
  1. **Extraction**: faithful read of the transcript → `{task, owner, due_date_iso, priority, source_quote, confidence}`
  2. **Planning**: editorial pass → merge/dedup overlapping items, flag missing owner/date, rank
- Deterministic (non-LLM) relative-date resolution in Python against the meeting date (e.g., "by Friday")
- **Memory**: local SQLite (`meetings.db`) — persists tasks, surfaces "still open from last time" across meetings
- **Tools**: Google Calendar event creation via OAuth (`calendar.events` scope only), with a `--dry-run` mode that prints the exact `events.insert` payload instead of calling Google
- **Interface**: Streamlit web UI (`app.py`) and CLI (`python -m meetingpilot`)
- Tests: `uv run pytest -q`, no API keys or Google account required (Calendar is mocked; schema/date/dedup/memory logic tested locally)
- Stack: Python 3.11, uv, Google Gemini API (`gemini-flash-lite-latest` default as of 2026-08-20, `google-genai` SDK), Streamlit, Pydantic, SQLAlchemy, python-dateutil, google-api-python-client, google-auth-oauthlib, icalendar. Anthropic (`anthropic` SDK) kept as an optional/legacy dependency, not used by the app itself.
- Cursor (Composer) used to scaffold/implement; Claude Code used for the Gemini migration and Google OAuth setup

### Documented known limitations (already in README — reuse for slides, don't just restate)
- Very long transcripts may truncate/miss items mid-document (context window limit; chunking not yet implemented)
- Speaker names not in transcript → `owner` labeled `Unknown`, extraction often leaves owner null
- Multiple due dates for one task may get merged into a single date by the planning pass
- "Next Friday" ambiguity — resolved deterministically but not all humans agree on the meaning
- Cross-meeting duplicate recall matches on owner + rough task similarity; paraphrases with few shared tokens may not link up
- LLM non-determinism — same transcript can yield different wording/confidence on reruns (schema stays consistent)
- **New (2026-08-19): Gemini free-tier transient errors.** Hit real `503 UNAVAILABLE` (model overloaded) repeatedly during dev testing. Mitigated with retry-with-backoff in `llm.py` (3 attempts, 2s/4s backoff). Unlike the Calendar/Gmail fallback (`.ics` export, now built), there is no fallback for a sustained Gemini outage — extraction and planning both require a live LLM call, so a full Google-side outage during the demo would still be a hard failure. Worth rehearsing with, not just hoping around.
- **Updated (2026-08-20): Gemini free-tier *daily* quota (20 requests/day) applies to `gemini-3.6-flash`, not just `gemini-3.5-flash` as first assumed.** Hit it for real after a full day of development testing — each meeting-processing run costs 2+ requests (extraction, planning, optionally diagram synthesis), so the quota covers roughly 10 runs before the app stops working entirely until reset. This is a genuine demo-day risk, not a dev inconvenience: **get a fresh API key close to demo day**, and budget rehearsal runs. The existing 429-retry logic doesn't help here — a daily quota exhaustion isn't a transient rate limit, retrying just fails again immediately.

---

## 4. Extension scope — decisions made this session (build against this, not the old README alone)

### Rejected approaches (do not build these — decided against, with reasons)
- ❌ **OS-level meeting/screenshare auto-detection** (Mac/Windows). No clean OS signal for "screenshare is active" exists; approximating it (timer + "is Zoom running") is unreliable and too risky to demo live in front of the class.
- ❌ **Custom-built web app / bespoke drag-and-drop frontend.** Streamlit's built-in uploader already covers the need; building a separate frontend is real engineering effort the rubric doesn't reward directly (rubric cares about the agent pipeline, not upload UX polish).
- ❌ **Slack integration.** Lower novelty than Calendar/Gmail extensions; not worth splitting limited build time across a third tool integration.
- ❌ **True "drop a whole folder"** — browsers don't support folder drag-and-drop into a standard file input without the non-standard `webkitdirectory` attribute, which Streamlit doesn't expose. Not pursuing a workaround (e.g. zip upload) unless time allows; multi-file select/drop is the accepted substitute.

### Accepted approach: post-hoc multimodal input, no live automation
User downloads/exports the transcript from their meeting tool **after** the call, and separately has screenshots (slides, whiteboards, Kanban boards, etc.) taken manually during the meeting. Both are dropped into the app together, after the fact. This keeps the whole system offline-testable and fully within the user's control — no background process, no permissions dialogs, no flaky live detection.

### Multi-file upload (Streamlit, decided implementation)

```python
uploaded_files = st.file_uploader(
    "Drop transcript + screenshots",
    accept_multiple_files=True,
    type=["txt", "vtt", "srt", "png", "jpg", "jpeg"]
)

transcript_file = None
screenshot_files = []

for f in uploaded_files:
    if f.name.lower().endswith((".txt", ".vtt", ".srt")):
        transcript_file = f
    elif f.name.lower().endswith((".png", ".jpg", ".jpeg")):
        screenshot_files.append(f)
```
- Extension-based routing, no manual labeling required from the user.
- **Must add**: validation error if more than one transcript-type file is dropped (don't silently pick one — would cause a confusing failure mid-live-demo).

### Updated architecture (target state)

```
Ingestion (transcript + screenshots, post-hoc multi-file upload via Streamlit)
        |
Extraction — LLM call 1 (MULTIMODAL: text content block + image content blocks in same Anthropic call)
        |  each extracted item tagged: source = "transcript" | "screenshot"
        v
Planning / dedup — LLM call 2 (unchanged from current implementation)
        |
Memory — SQLite (unchanged)
        |
Tools:
  - Google Calendar push (existing; dry-run supported; scope: calendar.events)
  - Gmail draft creation (NEW; reuses existing OAuth/credentials.json pattern; adds gmail.compose scope; DRAFT ONLY, never auto-send)
  - .ics file export (NEW; no OAuth required; local file write; live-demo fallback if Google auth/wifi fails in the room)
        |
Interface — Streamlit (multi-file upload; table grouped by owner)
```

This maps directly onto the Day 2 "LLM Agents: Key Components" diagram (Section 1) — Ingestion/Environment observe, Extraction = LLM Core, Planning = Planning & Reasoning, SQLite = Memory, Calendar/Gmail/.ics = Tools, event creation/draft = Agent Actions. **Use this mapping explicitly on a slide.**

### New/changed schema
Extend the existing extracted-item schema (currently `{task, owner, due_date_iso, priority, source_quote, confidence}`) with:
- `source: "transcript" | "screenshot"` — which input this item came from

### Build TODOs (in priority order)

0. [x] **Diagram synthesis** (done 2026-08-20, added mid-session, not in the original TODO list below — user-requested) — optional 3rd LLM call reconstructs a Mermaid diagram from a whiteboard/flowchart screenshot or a process described in the transcript. Off by default. Directly supports the Slides rubric line "Effective use of figures, diagrams, screenshots, tables, or examples" — a live-generated diagram is a stronger demo beat than a static screenshot of one. See `meetingpilot_decisions_and_todo.md` for full detail including a real bug it surfaced (planning-call truncation, now fixed with a larger token budget + retry).

1. [x] **Multimodal extraction call** (done 2026-08-19) — Extraction (LLM call 1) now accepts real image content blocks (`types.Part.from_bytes`) alongside transcript text in the same Gemini call, via `llm.py::call_tool(images=...)`. Added `source: "transcript" | "screenshot"` to `ExtractedItem`/the extraction+planning JSON schemas, and the field survives both LLM calls (verified live: a synthetic Kanban-card screenshot with no matching transcript line was correctly extracted and tagged `source: screenshot`, with owner/task read from image pixels, and the tag survived the planning/dedup pass). Threaded through `pipeline.py`, `cli.py` (`--screenshot PATH`, repeatable), and `app.py` (multi-file Streamlit uploader routing by extension, with a validation error if >1 transcript file is dropped, per the decided implementation below). The Streamlit item view now shows a 🖼️/📝 badge per item so the multimodal input is visibly used, not just accepted and ignored. Also added retry-with-backoff in `llm.py` for transient Gemini 503/429 errors (hit repeatedly during dev testing) — reduces live-demo failure risk.
2. [x] **Gmail draft tool** (done 2026-08-20) — new `gmail_tool.py`, draft-only (`drafts().create`, no send call in the module), dry-run shows a readable Subject+body preview (decoupled from MIME wire encoding after a bug where non-ASCII bodies rendered as unreadable base64). OAuth refactored into shared `google_auth.py` requesting Calendar+Gmail scopes together in one consent. Wired into CLI (`--push-gmail`) and Streamlit (per-item "Draft Gmail" button). See `meetingpilot_decisions_and_todo.md` for full detail.
3. [x] **.ics export** (done 2026-08-20) — new `ics_export.py`, real round-trip tests, per-item + bundle download in Streamlit, `--export-ics DIR` in CLI. See `meetingpilot_decisions_and_todo.md` for full detail. Also surfaced an important correction: **Gemini's free-tier 20-req/day quota applies to `gemini-3.6-flash` too**, not just 3.5 — a real demo-day risk, see Section 3 limitations below.
4. **Transcript chunking for long meetings** — split transcript into overlapping chunks (by speaker-turn count or token budget), run Extraction per chunk, let the existing Planning/dedup layer (LLM call 2) merge across chunks. This directly resolves the already-documented "long transcript truncation" limitation — don't build a separate merge mechanism, reuse Planning.
5. **Streamlit multi-file upload** — implement the routing logic in Section 4 above.
6. **Repo visibility** — flip to public before submission deadline. Before doing so, confirm `.env`, `credentials.json`, `token.json` are gitignored and were never committed to history (check with `git log --all --full-history -- <file>`; if found, scrub history or rotate the exposed keys — do not just delete-and-recommit).

### Open questions (not yet decided — flag rather than silently assume)
- Exact chunk size/overlap for transcript chunking — needs tuning against a real long sample transcript, not a guessed constant.
- Whether to demo the Gmail draft live (shows a real Drafts folder on screen — more convincing) vs. just show the payload (safer — no dependency on the demo machine being logged into a live Gmail account during presentation).

---

## 5. Rubric alignment checklist — audit against this before calling anything "done"

Use this as a literal checklist when reviewing generated code or drafting slides. Each row ties directly back to specific rubric language from Section 2.

| Rubric criterion | What satisfies it in this project | Status |
|---|---|---|
| "Layer you build around the LLM core" (workflow/tools/memory/planning) | Two-call extraction/planning split + SQLite memory + Calendar/Gmail/.ics tools | ✅ all built: multimodal extraction, Calendar, Gmail, .ics, plus optional diagram synthesis |
| README explains system, components, setup, how to run | Existing README architecture section + setup steps | ✅ Gemini setup steps updated; still needs a multimodal/screenshot section |
| Code runs successfully | `uv run pytest -q` needs no API keys; dry-run modes need no live Google account | ✅ (34 tests passing) |
| Demo shows meaningful end-to-end behavior | Upload → multimodal extraction → planning → memory → tool output, live or recorded | ✅ core pipeline verified live end-to-end (transcript + screenshot → tagged items → planning → memory, Gmail/Calendar dry-run payloads confirmed live); .ics generation verified via round-trip tests but not yet re-run against a fresh live meeting (Gemini daily quota exhausted during dev — see limitations) |
| Effectively communicates effort involved | Source-tagged items, dry-run payload visibility, two-call design | ✅ `source` field built, verified, and visible in the Streamlit UI (🖼️/📝 badge per item) |
| Clear motivation and well-defined problem (Presentation) | Not yet drafted — needs a slide | 🔲 |
| Clear system design explanation (Presentation + Slides) | Architecture diagram in Section 4, mapped to Day 2's own diagram | 🔲 needs to go on an actual slide |
| Smooth demo (Presentation) | Dry-run defaults + .ics fallback reduce live-failure risk | 🔲 needs rehearsal |
| Thoughtful discussion of limitations (Presentation + Slides, graded twice) | Known limitations already written in README (Section 3) | 🔲 needs to move onto a slide with a real example, not just prose |
| Figures/diagrams/screenshots/tables/examples (Slides) | Mermaid architecture diagram exists in README | 🔲 needs export to image (mermaid.live or `mmdc`) for slide software |
| Acknowledgment of external resources (Slides) | Acknowledgments section already in README | 🔲 needs to be copied onto a slide |
| Repo public | — | ❌ **currently private, must fix before submission** |

---

## 6. Instructions for Claude Code

When generating or reviewing code for this project:
1. Check new code against Section 4's architecture and TODOs before writing anything — don't reintroduce rejected approaches from Section 4 (OS auto-detection, custom web frontend, Slack, folder-only drag-drop).
2. Keep the two-call extraction/planning separation intact — don't collapse them into one prompt even if it seems simpler; this is a deliberate design choice documented in the README ("why extraction and planning are separate LLM calls").
3. New tools (Gmail, .ics) must follow the existing dry-run pattern used by Calendar — every new external-write action needs a dry-run mode that prints the payload instead of executing it.
4. Any new failure modes discovered while building should be added to Section 3's limitations list — this feeds the "thoughtful discussion of limitations" rubric criterion directly, so don't silently fix and forget edge cases; note them even if handled.
5. After generating code for a TODO in Section 4, update the Status column in Section 5 and check off the corresponding box — this file should stay in sync with actual progress so it stays usable as a submission-readiness check.
