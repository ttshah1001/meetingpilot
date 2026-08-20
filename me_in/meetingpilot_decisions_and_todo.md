# MeetingPilot — Decisions & TODO Notes

Running log of decisions made while scoping the multimodal extension for the ENGR 689 final project. Use this as a build checklist, not final documentation — fold anything relevant back into the README before submission.

## Scope decisions (locked in)

- **LLM provider: Google Gemini (AI Studio free tier), not Anthropic Claude.** Switched to avoid paying for API calls. `gemini-3.6-flash` supports both forced tool/function calling (needed for the structured JSON extraction schema) and native image input (needed for the screenshot multimodal feature) in one model, so it covers both LLM calls without a second provider. `meetingpilot/llm.py` still wraps Anthropic and needs a rewrite to Gemini's `google-genai` SDK before this is real — not done yet, tracked as a Build TODO below. `ANTHROPIC_API_KEY` / Claude path kept as optional/legacy in config and the access-check script, not removed, in case of a fallback comparison. **Confirmed working end-to-end** via `scripts/check_access.py` on 2026-08-19 — all 4 doors (Gemini text, Gemini vision, Calendar events, Gmail compose) pass. Still untested against the actual class rubric constraints (pending, rubric not yet reviewed).
  - `gemini-2.5-flash` (the initial default) is deprecated for new users (404 from the API) — use `gemini-3.6-flash`.
  - `gemini-3.5-flash` has a very thin free-tier cap (20 requests/day) that our own testing exhausted twice — avoid it for anything involving repeated runs or a live demo. `gemini-3.6-flash` did not hit this limit in testing.
  - **Code review pass on the `llm.py` rewrite** (2026-08-19, `/code-review` at medium effort): found 2 real bugs, both fixed — (1) `candidate.content` can be `None` (safety-filtered or truncated response) and the old code did `candidate.content.parts` before the `or []` fallback could apply, crashing with `AttributeError` instead of raising the intended `LLMError`; (2) a dead `isinstance(payload, dict)` check left over from the Anthropic version that could never fire. Added `tests/test_llm.py` (8 tests) covering the schema-nullable-conversion logic against the *real* `EXTRACT_SCHEMA`/`PLAN_SCHEMA` (not toy schemas) and the `content=None` regression case specifically — the existing 23 tests all mock the LLM layer, so none of them would have caught this class of bug.
  - **Google OAuth setup gotchas** (cost real time, worth remembering): (1) On this Mac, `google-auth-oauthlib`'s local OAuth callback server must bind explicitly to `host="127.0.0.1"` — the default `"localhost"` sometimes resolves to `::1` in the browser and the redirect fails with "Safari can't connect to the server," even though the Google-side consent already succeeded. (2) Project owners can't be added to their own "Test users" list ("ineligible" error) — that's expected, owners already have implicit access, not a sign of misconfiguration. (3) The Calendar `calendar.events` scope only covers the *Events* resource (`events.list`, `events.insert`, etc.) — calling `calendars().get()` (Calendars resource) 403s with "insufficient authentication scopes" even with a fully valid token; verify with an events-resource call instead.
- **No live OS automation.** Dropped the idea of auto-detecting meeting/screenshare start on Mac/Windows. Too unreliable (no clean "screenshare active" OS signal) and too risky for a live 15-minute demo.
- **Post-hoc input model instead.** User downloads the transcript from their meeting tool after the call and drops in any relevant screenshots (slides, whiteboards, Kanban boards) taken manually during the meeting. This is simpler, fully in the user's control, and still genuinely multimodal.
- **No custom web app for uploads.** Streamlit's `st.file_uploader(accept_multiple_files=True)` already gives native drag-and-drop for the transcript + screenshots together. A `.zip`-of-the-folder option is the fallback if a real "drop one folder" experience is wanted later — not required for the rubric.
- **Slack integration dropped.** Lower novelty than Calendar/Gmail, not worth splitting build time across a third tool integration.

## Architecture (updated)

```
Ingestion (transcript + screenshots, post-hoc upload)
        |
Extraction — LLM call 1 (multimodal: text + image content blocks)
        |  tags each item source: "transcript" | "screenshot"
        v
Planning / dedup — LLM call 2 (unchanged)
        |
Memory — SQLite (unchanged)
        |
Tools:
  - Google Calendar push (existing, dry-run supported)
  - Gmail draft creation (new — reuses existing OAuth pattern, adds `gmail.compose` scope)
  - .ics file export (new — no OAuth, good live-demo fallback if Google auth flakes)
        |
Interface — Streamlit (multi-file upload, table grouped by owner)
```

Maps directly onto Day 2's "LLM Agents: Key Components" diagram (LLM Core → Planning & Reasoning → Memory → Tools → Environment/Actions) — worth putting the course's own diagram on a slide and labeling each box with the matching component.

## Build TODOs

- [x] **Swap LLM provider to Gemini** (done 2026-08-19): rewrote `meetingpilot/llm.py` (`call_tool`) to the `google-genai` SDK's forced function-calling (`FunctionCallingConfig(mode="ANY", ...)`), including a JSON-Schema → Gemini-Schema converter (drops `additionalProperties`, converts `type: [X, "null"]` to `type: X` + `nullable: true`). `extraction.py`/`planning.py` needed no changes — same `call_tool()` signature and dict return. Verified end-to-end against the real `01_sprint_planning.txt` sample (both LLM calls, correct schema, correct dates). `pipeline.py`'s `require_api_key()` also updated to check `GEMINI_API_KEY` instead of the old Anthropic key. All 23 existing tests still pass (they mock the LLM layer).
- [x] **Multimodal extraction call** (done 2026-08-19): see full writeup in `meetingpilot_project_spec.md` Section 4. Verified live against a real image (synthetic Kanban card) — correctly tagged `source: screenshot`, survived planning. Also added Gemini retry-with-backoff (503/429) since those errors were common during testing.
- [x] **Validation pass on the multimodal diff** (2026-08-19/20, `/code-review` high effort across `models.py`/`extraction.py`/`planning.py`/`pipeline.py`/`cli.py`/`app.py`/`llm.py`): found and fixed 6 real issues — (1) `source` wasn't `required` in `PLAN_SCHEMA`, so the planning LLM could legally drop it; fixed by requiring it **and** adding a deterministic fallback in `plan_action_items()` that cross-checks the LLM's echoed `source` against the locally-tracked (trusted) value by quote match, so the tag can't silently revert to "transcript" even if the model still gets it wrong; (2) `source` wasn't persisted to SQLite at all (`ActionItemRecord` had no column) — added the column + wired `save_meeting`/`stored_items_as_planned`; (3) `process_path`/`process_pasted_text` didn't forward the new `screenshots` param; (4) `cli.py --screenshot` crashed with a raw traceback on a bad path instead of a clean error; (5) MIME-type-by-extension was duplicated between `app.py` and `cli.py` — consolidated into `models.SCREENSHOT_MIME_BY_EXTENSION`; (6) removed an unnecessary `arbitrary_types_allowed` on `Screenshot`. Added `tests/test_source_tag.py` (4 tests) covering the LLM-drops-the-field case, the LLM-reports-it-wrong case, and a full SQLite persist/reload round-trip. 38/38 tests pass; re-verified live against a real screenshot after all fixes.
- [ ] **Gmail draft tool**: add `gmail.compose` scope to existing `credentials.json` OAuth flow. Draft-only — never auto-send. Show the exact MIME payload in dry-run mode, matching the existing Calendar dry-run pattern.
- [ ] **.ics export**: use `icalendar` or `ics` Python library to write one `.ics` file per task. No API keys required — good fallback if live Calendar OAuth fails during the presentation.
- [ ] **Transcript chunking for long meetings**: split transcript into overlapping chunks (by speaker-turn count or token budget), run Extraction per chunk, let existing Planning/dedup layer (LLM call 2) merge across chunks. Directly resolves the "long transcript truncation" failure case already documented in the README.
- [ ] **Streamlit multi-file upload**: switch/confirm `st.file_uploader(accept_multiple_files=True)` for transcript + screenshots in one drag-and-drop action.
- [ ] **Repo visibility**: flip to public before submission. Confirm no secrets (`.env`, `credentials.json`, `token.json`) are in git history — scrub or rotate keys if they ever were committed.

## Slide/demo material to highlight

- **Known failure cases** (from README) — move into an actual slide with a real transcript excerpt + wrong/flagged output, not just prose. Rubric explicitly grades "thoughtful discussion of limitations."
- **Two-call design rationale** (extraction = faithful read, planning = editorial pass) — good "system design" talking point, shows deliberate architecture choice, not just a single mega-prompt.
- **Source-tagged items** (`source: transcript` vs `source: screenshot`) — good visual for showing the multimodal input is actually being used, not just accepted and ignored.
- **Acknowledgments section** — already covers Anthropic API, Google Calendar API, Streamlit, Pydantic, SQLAlchemy, python-dateutil, uv, Cursor. Carry this onto a slide; rubric asks for it there too.
- **Live demo path**: dry-run mode as default for both Calendar and Gmail, `.ics` export as the no-internet-required fallback if OAuth or wifi fails in the room.

## Multi-file upload — implementation

Decided: use Streamlit's native multi-file uploader for transcript + screenshots together, no custom web app. Route files by extension after upload:

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

- Extension-based routing — user doesn't need to label anything, just drags transcript + screenshots in together.
- **TODO**: add a validation error if two transcript files are dropped by mistake (don't silently pick one — this could cause a confusing failure mid-demo).
- Feeds directly into the multimodal Extraction call: transcript text as the text content block, each screenshot as an image content block. The `source` field on each extracted item (`"transcript"` vs `"screenshot"`) traces back to which input it came from.

## Open questions (not yet decided)

- Exact chunk size/overlap for transcript chunking — needs a couple of test runs against a long sample transcript to tune.
- Whether to demo the Gmail draft live (shows a real Drafts folder appearing) or just show the payload — live is more convincing but adds a dependency on the demo machine's Gmail account being logged in and reachable.
