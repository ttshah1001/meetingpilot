# MeetingPilot — Presentation Source Material

**Purpose of this document**: everything a separate agent (or you) needs to build a slideshow/presentation, rooted entirely in what was actually built, decided, tested, and discovered in this repo. Every claim below is verifiable against the actual code, tests, and commit history — nothing here is aspirational or generic. Pull sections directly for slide content; the headers are written to map cleanly onto slide topics.

Course context: TAMU ENGR 689, Multimodal LLM Agents, Fall 2026 Sprint Course. Presentation: 15 minutes in-class, Day 5. Rubric grades Presentation (20%), Slides (20%), Code/Demo (20%), on top of quizzes (40%).

---

## 1. Motivation — why this project, why this shape

**The problem**: meeting transcripts are a rich, wasted data source. People leave meetings having verbally committed to work, but nobody reliably extracts "who owns what, by when" into a system that survives past the meeting. Calendars, task trackers, and follow-up emails all require someone to manually re-type what was already said.

**Why an LLM agent, not a script**: extracting "Marcus will draft the roadmap by Friday" from raw dialogue requires actual language understanding — who is speaking, what they committed to, whether it's a real commitment or just discussion, what "Friday" resolves to relative to the meeting date. This is exactly the kind of task where an LLM earns its keep over a rules-based parser.

**Why layered, not a single mega-prompt**: the course's own Day 2 material frames agents as LLM Core + Planning & Reasoning + Memory + Tools + Environment. MeetingPilot is built to map onto that model directly, not incidentally — see Section 3.

**Why multimodal was added deliberately, not bolted on**: the rubric explicitly states multimodality is *optional* ("Your agent may be multimodal or primarily text-based"). The screenshot-extraction feature was added specifically because meetings aren't purely verbal — a whiteboard sketch, a Kanban board on screen-share, a slide with bullet points, all carry real information that a transcript-only pipeline would miss entirely. This was a deliberate choice to genuinely exercise Day 3's multimodal material, not a checkbox feature — see Section 9 for how this was validated as *real* multimodal use, not OCR dressed up as AI.

**Why so many tools (Calendar, Gmail, Tasks, .ics)**: the rubric's own framing states "What matters is the layer you build around the LLM core, such as the interface, workflow, tools, memory, planning, automation, or data handling." The tool layer was treated as a first-class design surface, not an afterthought — four tools, each added for a distinct reason (see Section 6), all following one consistent dry-run-first safety pattern.

---

## 2. High-level pipeline (map this directly onto the course's own diagram)

```
transcript (.txt/.vtt/.srt/paste) + screenshots (.png/.jpg)
        |
   1. Ingestion            — parses speaker turns, timestamps; format-detects .vtt/.srt/.txt
        |
   2. Extraction            — Gemini call #1, MULTIMODAL (text + image content blocks in one call)
        |                      -> {task, owner, due_date_iso, priority, source_quote, confidence, source}
   3. Planning / dedup      — Gemini call #2 + deterministic Python dedup
        |                      -> merged, ranked, gap-flagged items
   4. Memory                — SQLite; "still open from last time" across meetings
        |
   5. Tools (all dry-run by default):
        5a. Google Calendar
        5b. Gmail (draft-only, structurally cannot send)
        5c. Google Tasks
        5d. .ics export (no API key, no network — offline fallback)
        |
   6. Summary + diagrams    — Gemini call #3, OPTIONAL, multimodal, model decides 0-N diagrams
        |                      -> chat-based refinement loop (ask for changes, it edits in place)
        v
   Streamlit UI — action items grouped by owner, source-tagged (🖼️/📝)
```

Maps onto the course's "LLM Agents: Key Components" diagram: Ingestion/screenshots = **observation**; Extraction = **LLM Core**; Planning = **Planning & Reasoning**; SQLite = **Memory**; Calendar/Gmail/Tasks/.ics/summary = **Tools**; event/draft/task/file creation = **Agent Actions**.

Two things worth calling out as deliberate design, not accidents:
- **Extraction and Planning are two separate LLM calls, not one.** Extraction is a *faithful read* (copy what was said, even if messy/duplicated). Planning is an *editorial pass* (merge, flag gaps, rank). This separation makes it possible to tell "the model misheard the meeting" apart from "the model over-normalized" — a debugging and demo-ability win the rubric rewards ("clear system design").
- **Every tool that writes to an external system defaults to dry-run.** Calendar, Gmail, and Tasks all print the exact API payload they *would* send instead of sending it, until explicitly turned off. Gmail goes further — the code path only ever calls `drafts().create()`, there is no send call anywhere in the module, so it's structurally impossible for it to send an email even by accident.

---

## 3. Architecture decisions, and why (with the actual tradeoffs)

**LLM provider: Google Gemini, not Anthropic Claude.**
The project originally used Claude. Switched specifically to avoid paying for API calls — the course rubric explicitly permits "any open/closed-source LLM allowed as backbone," so this was a free choice, not a compromise. `gemini-flash-lite-latest` was landed on after real iteration:
- `gemini-2.5-flash` (first choice) → deprecated for new users (404 from the live API — discovered by actually calling it, not by reading changelog)
- `gemini-3.5-flash` → worked, but has a **20 requests/day free-tier cap per API key** — hit this for real during development
- `gemini-3.6-flash` → initially assumed to have a higher cap; **this assumption was wrong** and later corrected in the docs once actually hit in practice — it shares the same 20/day cap
- `gemini-flash-lite-latest` (final) → chosen specifically because Flash-Lite tiers are built for high-volume, low-cost use and are historically the most quota-generous free tier. This is **not a documented "unlimited" guarantee** — it was confirmed empirically (multiple full pipeline runs with zero quota errors) and documented honestly as "a reasoned bet, not a verified claim."

**Why this matters for the presentation**: this is a genuine example of iterating based on real production behavior rather than assumptions — worth a slide on its own as a "thoughtful discussion of limitations" beat, since the rubric explicitly rewards that.

**Google Tasks added alongside Calendar, not instead of it.**
Calendar events are date-based reminders, not real to-dos with a completion checkbox — a semantic mismatch for "action items." Google Tasks (title/notes/due date/checkbox) is the more natural fit conceptually. Calendar was kept because it was already built, tested, and part of the original locked scope — Tasks was added as a genuinely better-fit *additional* tool, following the exact same dry-run pattern as everything else.

**Multimodal extraction is real, not decorative.**
Screenshots are sent as actual image content blocks in the *same* Gemini API call as the transcript text — this is genuine multimodal model usage, the model is literally looking at pixels, not a separate OCR step feeding text back in. Each extracted item is tagged `source: "transcript" | "screenshot"`. This tag is *cross-checked* against the locally-tracked value after the planning pass rather than blindly trusted from a second LLM call, specifically because testing showed the planning LLM could echo it back incorrectly (see Section 9).

**Diagram count is model-decided, not hardcoded.**
The summary+diagram feature doesn't force "always show exactly one diagram." The model returns a list — zero, one, or more — based on its own judgment of what's genuinely describable in the content. Verified live that a meeting with two distinct describable structures (e.g. an architecture flow and a separate Kanban board) can return two diagrams, and a content-free transcript correctly returns zero rather than inventing one to fill the slot.

**Chat-based refinement is grounded, not a blind rewrite.**
When a user asks for a change ("make it shorter," "rename the second diagram"), the refinement call is sent the *original transcript/screenshots* **and** the *current draft* together, with an explicit "this is an edit, not a rewrite" instruction. Verified live: asking for a shorter summary took a 112-word draft to 47 words while keeping the same facts; asking to rename+relayout a diagram changed only that diagram, leaving unrelated content untouched.

---

## 4. Features, explained in depth (one section per feature — pull individually per slide)

### 4.1 Multimodal extraction (transcript + screenshots)
Ingests `.txt`/`.vtt`/`.srt` transcripts or pasted text, plus optional `.png`/`.jpg` screenshots, uploaded together via a single Streamlit multi-file drop. Extraction (Gemini call #1) reads both in one call and produces structured items: `{task, owner, due_date_iso, priority, source_quote, confidence, source}`. The `source_quote` field for a screenshot-derived item describes what the image shows (e.g. "Kanban card: 'Ship v2 payments API' in the To Do column") rather than a spoken line — this is the audit trail proving the model actually looked at the image, not guessed.

### 4.2 Planning / deduplication
A second Gemini call (planning) merges duplicate items (someone mentioning the same task twice), flags missing owner/date, proposes defaults (owner left blank, due date defaults to meeting date + 7 days), and ranks by priority/date/confidence. Deterministic Python dedup runs first as a guaranteed baseline (testable without any API key), and the LLM planning pass can merge more aggressively on top of it.

### 4.3 Memory (SQLite)
Every processed meeting is persisted. On the next meeting, items still open from before (matched by owner + rough task-text similarity) surface in the sidebar and get annotated onto newly-extracted items as "still open from last time" — this is the "agent with state" beat, not just a one-shot parser.

### 4.4 Google Calendar tool
Creates one all-day event per dated item (`summary` = task, `description` = owner/priority/confidence/source-quote/planning-notes, `start`/`end` = due date). Dry-run by default. A sidebar field lets a user point live pushes at a dedicated calendar (not their primary one) so test events can be isolated and hidden/deleted in bulk instead of hunted down individually.

### 4.5 Gmail draft tool
Creates one draft email per item — a real LLM-composed subject and body grounded in the task, owner, due date, and source quote (`compose_email()`), not a template dump of internal fields (owner/priority/confidence) the way Calendar's event description is. That distinction matters: Calendar's description is an internal-facing record, but an email is read by a human recipient, so it's written the way a person would actually write it. Structurally draft-only — the module contains no code path that can send mail, only `drafts().create()`. The dry-run preview is built as plain "Subject + body" text, deliberately decoupled from the underlying MIME wire encoding (see Section 9 for the bug this fixes).

### 4.6 Google Tasks tool
Creates a real, checkable Google Task per item — the semantically correct destination for an "action item" (see Section 3 for the reasoning). Same dry-run pattern, same shared description-text logic as Calendar/Gmail (factored into one place in `models.py` so all three tools stay consistent instead of duplicating formatting).

### 4.7 `.ics` export
Writes one `.ics` calendar file per dated item (or a single bundle file for all of them), using the `icalendar` library. Requires no API key, no OAuth, no network call at all — this is the deliberate offline fallback if Google access or venue wifi fails mid-demo. Validated with real round-trip parsing (generate the file, parse it back with `icalendar`, confirm the fields match) — not just "didn't crash."

### 4.8 Summary + diagram synthesis (optional third LLM call)
Off by default (costs an extra call, not every meeting has anything worth summarizing). When enabled, produces a detailed 2-3 paragraph narrative summary plus zero or more Mermaid diagrams reconstructed from screenshots or a described process. Each diagram renders live via `mermaid.js` (Streamlit has no native Mermaid support) with real client-side "Download SVG"/"Download PNG" buttons — the browser already has the rendered SVG, the buttons just save it, no server round-trip.

### 4.9 Chat-based refinement
After the first summary+diagram pass, a chat box lets the user ask for changes in natural language. Each message triggers a new LLM call grounded in the original transcript/screenshots *and* the current draft, with explicit instructions to edit rather than regenerate from scratch. This directly addresses a real gap: a one-shot summary/diagram generation has no way to course-correct if it's too long, too short, or misses the point — the chat loop makes it interactive instead of a dead end.

### 4.10 Streamlit UI
Multi-file drag-and-drop for transcript + screenshots (with validation against dropping more than one transcript file at once). Per-item action buttons (Push to Calendar / Draft Gmail / Add to Tasks / Download .ics), bulk versions of each scoped by an optional "your name" filter so bulk actions don't grab a whole team's tasks. A warm, light, "editorial" visual theme (cream/tan background, deep brown text, a muted burnt-orange accent, serif headers over a clean sans body) replacing Streamlit's plain default — sourced from an existing personal design system for consistency rather than invented from scratch. Testing/dry-run toggles are deliberately tucked into a collapsed "advanced options" section so the top-level UI reads as client-facing, not developer-facing.

---

## 5. Known limitations and out-of-scope decisions (the rubric explicitly rewards this — don't undersell it)

**Explicitly rejected during scoping, with reasons:**
- OS-level meeting/screenshare auto-detection — no reliable cross-platform signal exists, and it's too risky for a live 15-minute demo to depend on.
- A custom-built upload web app — Streamlit's native multi-file uploader already does the job; a bespoke frontend would be real engineering effort the rubric doesn't reward directly.
- Slack integration — lower novelty than Calendar/Gmail/Tasks, not worth splitting limited build time across a fourth tool integration.
- True "drop a whole folder" — browsers don't support folder drag-and-drop without a non-standard attribute Streamlit doesn't expose; multi-file select is the accepted substitute.

**Built but with known, documented failure modes:**
- **Very long transcripts** may truncate or miss items mid-document (finite context window). Chunking by time range is the next engineering step — not implemented; tracked as a real TODO, not hidden.
- **Speaker names not in the transcript** get labeled `Unknown`; extraction leaves `owner` null rather than guessing from job title or context. One of the sample transcripts is deliberately written to demonstrate this.
- **Multiple due dates in one utterance** ("draft Friday, final by the 28th") may collapse to one date during planning — the tool does not model multi-milestone tasks; the source quote remains the audit trail.
- **"Next Friday" ambiguity** — resolved deterministically in Python (not left to the LLM), but humans don't universally agree on what it means; documented as a known human-language ambiguity, not a bug to "fix."
- **Cross-meeting duplicate recall** matches on owner + rough task-text similarity — paraphrases sharing few tokens may not link up, though the sidebar still lists every open item regardless.
- **LLM non-determinism** — the same transcript can yield different wording/confidence on a rerun; schema validation guarantees the same *keys* are always present, not the same content.
- **Rare token-level hallucination, observed once**: one extraction run substituted "ll" with Arabic script inside an otherwise-correct English quote. Reran the same extraction 5 more times immediately after with zero recurrence — treated as a rare glitch worth documenting honestly, not a systemic bug worth a speculative fix.
- **Gemini free-tier daily quota risk** — even the quota-optimized model choice is not a documented-unlimited guarantee; a fresh API key close to demo day is the recommended mitigation, not a code fix.
- **No fallback if Gemini itself is down** — extraction and planning both require a live LLM call; `.ics` export and dry-run payloads only work *after* a successful extraction pass, they are not a substitute for the LLM layer being reachable at all.

**A crash that was found and fixed, worth mentioning as a testing-process story (see Section 9):** a malformed date value from the LLM could crash the entire page before this was caught and fixed — a genuine example of testing surfacing something dangerous, not just cosmetic.

---

## 6. How this was actually built — process, not just output

**Starting point**: a `planning_documentation/meetingpilot_decisions_and_todo.md` file the user had already written before AI involvement, scoping the multimodal extension idea, rejected alternatives, and an initial Build TODO list. This became the running decision log for the entire session — every major choice from that point on was logged there with reasoning, not just the final state.

**Verification before building, not after**: before writing any new code, real API access was verified against live endpoints (`scripts/check_access.py`, built specifically for this) — Gemini text, Gemini vision, Calendar, Gmail, and later Tasks — each tested with the smallest possible real request rather than assumed to work from documentation. This surfaced several real, non-obvious problems before they could waste build time:
- A macOS-specific OAuth bug (`localhost` resolving to a different address than the callback server was listening on) that looked like a permissions problem but was a networking one.
- A Google Calendar scope misunderstanding — `calendar.events` covers the *Events* resource, not the *Calendars* resource; calling the wrong endpoint 403'd even with fully valid access.
- A misconception that project owners need to add themselves as OAuth test users (they don't — that's expected, not an error).

**BMAD workflow — considered, explained, deliberately not fully adopted**: BMAD (a structured multi-agent product-development framework: product brief → PRD → architecture → spec → epics/stories → build) was explained in full at the start of the session as an available option. The team chose a **lighter-weight path instead**: `planning_documentation/meetingpilot_project_spec.md` (audited and kept in sync throughout, functioning as the de facto living spec) plus targeted use of the `/code-review` skill at specific checkpoints, rather than running the full BMAD ceremony (formal PRD, architecture doc, spec distillation, epic/story breakdown). This was a deliberate scope decision for a fast course sprint — the heavier BMAD machinery (Test Architect framework setup, formal traceability matrices, NFR audits) was judged to cost more time than it would save for a 3-person, few-day project, versus the direct build-test-verify-document loop actually used.

**The iteration loop that was actually used, repeatedly:**
1. Build a feature
2. Run the real test suite (mocked, fast, no API key needed)
3. Verify live against the actual Gemini/Google APIs (not just mocks) — catch things mocks structurally cannot catch
4. Run `/code-review` at an appropriate effort level on the diff
5. Fix what it finds, add regression tests specifically for what was found
6. Log the decision + what was learned in `planning_documentation/` docs
7. Commit, push, open a PR, merge

This loop caught real bugs repeatedly — not hypothetical ones. See Section 9 for the specific list; it's long, and that's the point: a working test suite that's "green" is not the same as a working feature, and this project has concrete evidence of both mocked tests passing *and* the underlying feature still being broken until live-verified (the multimodal-crowding bug is the clearest example — 51/51 tests were green when that bug existed).

**Feedback loop, both directions:**
- User feedback shaped scope repeatedly mid-build (e.g. "the bulk .ics export should only include my tasks, not the whole team's" → added an owner-name filter; "why don't we push to Calendar" → clarified dry-run's actual purpose rather than just flipping a switch; direct UI critique → full theme redesign sourced from the user's own existing design system).
- The chat-based summary/diagram refinement feature *is itself* a direct response to a feedback pattern noticed during the session: a one-shot LLM generation has no way to course-correct if it misses the mark, so the same "ask for a change, get it applied precisely" loop that was happening in this development conversation was built into the product itself.

---

## 7. Testing & validation approach

- **71 automated tests** (final count), covering schema validation, date resolution, deterministic dedup, SQLite memory, the Gemini response-parsing/retry layer, and every tool (Calendar/Gmail/Tasks/.ics) via mocked Google clients — runs with zero API keys or network access (`uv run pytest -q`).
- **Retry-with-backoff** for Gemini's transient `503`/`429` errors, including a specific retry path for a successful-but-truncated response missing the required tool call — found by hitting it live, not by reading about it.
- **No browser automation tool was available in this environment.** UI verification used `streamlit.testing.v1.AppTest` to headlessly drive the actual app — real widget interactions (button clicks, chat input, checkbox toggles), not just "does the function work in isolation." This is explicitly called out in the project's own docs as a known constraint, worked around rather than skipped.
- **Live verification against the real API was treated as mandatory, not optional**, for every feature — extraction, planning, multimodal image input, Gmail drafts, Calendar events, Google Tasks, `.ics` file generation (round-trip parsed back), summary generation, diagram generation (including the model correctly returning zero diagrams for content-free input), and chat-based refinement (both text and diagram edits).

### 7.1 "By the Numbers" — slide-ready stats (all live-verified, 2026-08-21)

Every number below was produced by actually running the pipeline against real data (`Sample_DATA/`, 16 distinct meeting transcripts spanning architecture reviews, sales syncs, onboarding, incident postmortems, investor updates) or the repo's own test suite/changelog — not estimated or asserted.

- **71** — Tests passing (`uv run pytest -q`), zero external API keys required.
- **11** — Items extracted in one call (7 from transcript + 4 from a screenshot, sample 01 + Kanban board image), correctly merged with no duplicates.
- **5** — API doors verified live: Gemini text, Gemini vision, Calendar, Gmail, Tasks (`scripts/check_access.py`).
- **69** — Total real action items extracted across all 16 `Sample_DATA` meetings (transcript-only, no screenshots — a conservative floor), averaging **4.3 items/meeting** at **0.95 average confidence**. Only 1% fell below the 0.6 low-confidence threshold; only 1% had no stated owner; 9% had no stated due date (correctly left null rather than invented).
- **538 → 159** — Average transcript-to-summary compression across 5 real ~500-word transcripts (473-600 words each), live-tested.
- **159 → 35 (78%)** — Average further reduction when the chat asked to shorten the summary, tested across 15 of the 16 `Sample_DATA` meetings (1 skipped on a transient per-minute rate limit, not a failure) — consistent with the smaller 3-sample run (123 → 35, also ~78%), so this compression rate holds up at scale, not cherry-picked.
- **3** — Output paths per item: live push, dry-run preview, or fully offline `.ics` export.
- **9** — Shipped versions, v0.1.0 → v0.7.0 (`CHANGELOG.md`), each with a dated entry of what changed and why.

---

## 8. Timeline of major decisions (chronological, for a "how we got here" slide)

1. Locked initial scope: post-hoc transcript + screenshot upload, no live OS automation, no custom upload frontend, no Slack.
2. Verified all API access live before writing extension code.
3. Switched LLM provider: Anthropic → Google Gemini (cost), with real model iteration (2.5-flash deprecated → 3.5-flash quota-capped → 3.6-flash *also* quota-capped, corrected after initially assuming otherwise → flash-lite-latest).
4. Built genuine multimodal extraction; code-reviewed, fixed 2 real bugs in the LLM wrapper.
5. Built the Gmail draft tool; fixed a MIME-encoding bug that made non-ASCII previews unreadable.
6. Corrected the Gemini quota assumption after hitting it live a second time; switched the default model.
7. Built `.ics` export; consolidated duplicated description-formatting logic across all three push tools.
8. Wrote a real, timed demo script and a purpose-built sample screenshot asset — testing that asset surfaced a genuine multimodal-crowding bug (screenshots silently dropped when paired with a busy transcript) and fixed it at the prompt level.
9. Repo flipped to public; work merged to `main` via reviewed PRs throughout, not direct pushes.
10. Added Google Tasks as a fourth tool, with an explicit semantic argument for why (real to-dos vs. calendar reminders).
11. Added meeting summary + diagram synthesis, with model-decided (not hardcoded) diagram count.
12. Added chat-based refinement; found and fixed a real page-crashing bug (malformed date from the LLM) while building it.
13. Full UI redesign: moved off Streamlit's default theme to a warm, light, sourced design system; fixed two real layout bugs along the way (chat input floating below unrelated content; oversized default top margin).
14. Removed a UI element (sample-transcript dropdown) on request, cleaning up the now-dead code it depended on rather than leaving it stranded.
15. Built a native macOS launcher app for demo-day convenience; clarified (rather than glossed over) that this doesn't solve "instructor runs it on their own machine" — that's still the standard documented terminal setup, which is normal, not a shortcoming.

---

## 9. Real bugs found during development (this is strong "thoughtful discussion of limitations" material — testing process, not just output)

Each of these was caught by actually running the software against real inputs, not by inspection:

1. **`candidate.content` can be `None`** (safety-filtered/truncated Gemini response) — old code crashed with `AttributeError` instead of raising the intended clean error. Found via code review, fixed, regression-tested.
2. **A dead `isinstance` check** left over from the Anthropic-era code, which could never fire under the new Gemini path — removed as part of the same review pass (a "should this code even exist" catch, not just a crash fix).
3. **Gmail MIME preview became unreadable for non-ASCII text** — Python's `MIMEText` silently switches to base64 encoding for bodies containing e.g. an em-dash, which made the "preview" shown to the user an unreadable blob instead of the actual content for some items. Fixed by decoupling the human-readable preview from the wire-format encoding.
4. **`source` (transcript vs. screenshot tag) could silently revert** if the planning LLM dropped or mangled it in its JSON response — required in the schema *and* cross-checked against the locally-tracked value after planning, not just trusted blindly.
5. **Multimodal extraction got crowded out by a busy transcript** — a screenshot with several real, actionable cards was silently dropped entirely (0 of 4 items) when paired with a transcript that already had 7 spoken items, even though the same model could correctly describe the same image in a plain, non-schema-constrained request. This was found specifically *because* a demo asset was built and tested against the realistic pairing it would actually be used with, not a toy example. Fixed by explicitly instructing the extraction prompt to treat screenshot content as a mandatory separate pass regardless of transcript length; reverified twice on the exact failing case.
6. **A malformed due-date value from the LLM could crash the entire page** — not just corrupt one field cosmetically. `.ics` export, Calendar, and Google Tasks all call a real date-parsing function on `due_date_iso`/`proposed_due_date_iso` *eagerly while just rendering the page* (not only on button click), so an unvalidated garbage string from the model brought down the whole UI. Fixed at the data-validation boundary (Pydantic model level) instead of patching every downstream consumer separately — the malformed value now falls back to "no date given" (correctly flagged for review) rather than propagating.
7. **A real Google Cloud/OAuth debugging saga**, non-code but genuinely time-costing and worth a slide as an "engineering reality" beat: an auto-generated Google Cloud project turned out to have broken OAuth test-user behavior; `localhost` vs `127.0.0.1` binding caused a browser-redirect failure that looked like a permissions error; and the `calendar.events` scope only covers the Events API resource, not the Calendars resource, which 403'd a check that was actually testing the wrong endpoint. All root-caused and fixed, not worked around.

---

## 10. Acknowledgments (carry onto its own slide, rubric asks for this explicitly)

- [Google Gemini API](https://ai.google.dev/) — structured function calling for extraction, planning, and the optional summary/diagram call (free tier via AI Studio)
- [Google Calendar API](https://developers.google.com/calendar), [Gmail API](https://developers.google.com/gmail/api), [Google Tasks API](https://developers.google.com/tasks) via `google-api-python-client` and `google-auth-oauthlib`
- [Mermaid](https://mermaid.js.org/) for diagram rendering
- [Streamlit](https://streamlit.io/), [Pydantic](https://docs.pydantic.dev/), [SQLAlchemy](https://www.sqlalchemy.org/), [python-dateutil](https://dateutil.readthedocs.io/), [icalendar](https://icalendar.readthedocs.io/)
- [uv](https://docs.astral.sh/uv/) for Python environments
- Cursor (Composer) and Claude Code were used to scaffold and implement this class project

---

## 11. Where to look in the repo for more detail

- `README.md` — setup, running, and quick feature tour
- `docs/ARCHITECTURE.md` — full diagrams, design rationale, and the complete known-limitations list with more technical detail than this document
- `CHANGELOG.md` — every version bump with what changed and why, in order
- `DEMO.md` — the actual timed live-demo script, including specific things to click and say
- `planning_documentation/meetingpilot_decisions_and_todo.md` — the full, chronological, unfiltered decision log this document was distilled from — includes more granular detail on every bug and decision than fits here
- `planning_documentation/meetingpilot_project_spec.md` — the rubric-alignment tracking document, including a literal checklist mapping rubric criteria to what's built
- `planning_documentation/meetingpilot_tagline_options.md` — tagline alternatives if the current one isn't right for a slide title
