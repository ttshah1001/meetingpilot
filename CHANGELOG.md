# Changelog

All notable changes to this project are documented here. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

- Transcript chunking for long meetings — planned, not yet built.

## [0.5.0] - 2026-08-20

### Added
- Google Tasks tool (`meetingpilot/tasks_tool.py`) — same dry-run pattern as Calendar/Gmail. A more semantically correct destination for "action items" than Calendar all-day events (real checkable to-dos vs. date-based reminders). Wired into CLI (`--push-tasks`/`--live-tasks`) and Streamlit (per-item + bulk buttons, dry-run toggle).
- Meeting summary text, alongside the existing optional diagram synthesis — renamed `diagram.py` → `summary.py`, `DiagramResult` → `MeetingSummary`. The diagram *count* is now model-decided (0, 1, or more) instead of a hardcoded single diagram.
- Real client-side "Download SVG"/"Download PNG" buttons on each rendered diagram — mermaid.js already produces the SVG in the browser, the buttons just save that output, no server round-trip.
- `scripts/check_access.py` now also verifies Google Tasks API access.

### Changed
- Extended the shared OAuth scope (`meetingpilot/google_auth.py`) to include `.../auth/tasks` alongside Calendar and Gmail — one combined consent covers all three.

## [0.4.1] - 2026-08-20

### Changed
- Default model switched from `gemini-3.6-flash` to `gemini-flash-lite-latest` to reduce free-tier daily-quota risk on demo day. Confirmed to still support both forced function calling and multimodal image input before switching; re-verified a full live extraction+planning+Calendar+Gmail+.ics run on the new default.

## [0.4.0] - 2026-08-20

### Added
- `.ics` file export (`meetingpilot/ics_export.py`, `icalendar`) — no OAuth, no network, live-demo fallback if Google auth/wifi fails. One file per dated item, plus a single-bundle option. `--export-ics DIR` CLI flag; per-item and "download all" buttons in Streamlit (`st.download_button`, no OAuth popup).
- Tests: `tests/test_ics_export.py`, including real `icalendar` round-trip parsing (not just "didn't crash").

### Changed
- Factored the shared event/draft description-text logic out of `calendar_tool.py` into `PlannedItem.description_text()`/`.resolved_due_date()` (`models.py`), so Calendar, Gmail, and `.ics` all build consistent descriptions instead of duplicating the same formatting three times.

### Fixed
- **Corrected an earlier (0.2.0) note**: both `gemini-3.5-flash` and `gemini-3.6-flash` share the same 20-requests/day free-tier quota per API key — not just 3.5-flash as first assumed. Hit it for real during this release's testing. This is a genuine demo-day risk (roughly 10 full meeting-processing runs per day per key); mitigations documented in `docs/ARCHITECTURE.md`.

## [0.3.0] - 2026-08-20

### Added
- Gmail draft tool (`meetingpilot/gmail_tool.py`) — draft-only, never sends, dry-run shows a readable preview. Same pattern as the Calendar tool.
- Optional Mermaid diagram synthesis (`meetingpilot/diagram.py`) — a third, opt-in LLM call that reconstructs a diagram from a whiteboard/flowchart screenshot or a process described in the transcript. Rendered in Streamlit via an embedded `mermaid.js` component.
- `scripts/check_access.py` combined-scope OAuth flow shared with Calendar via new `meetingpilot/google_auth.py`.
- `--push-gmail`/`--live-gmail` and `--diagram` CLI flags; matching Streamlit UI controls.
- Tests: `tests/test_gmail.py`, `tests/test_diagram.py`, expanded `tests/test_llm.py`.

### Fixed
- Planning LLM calls could return a technically-successful response missing the tool call on large multi-item payloads (truncation from too-small `max_tokens`), not caught by the existing HTTP-error retry logic. Raised the default token budget and extended retries to cover this case.
- OAuth scope mismatch: Calendar and Gmail previously would have requested different scopes against the same token file independently, silently producing a token missing one tool's scope. Now request both scopes together in one consent.

## [0.2.0] - 2026-08-19

### Changed
- Swapped the LLM backbone from Anthropic Claude to Google Gemini (`gemini-3.6-flash`, free tier) to avoid paying for API calls — permitted by the course rubric ("any open/closed-source LLM allowed as backbone"). `ANTHROPIC_API_KEY` remains as an optional/legacy config path; the app itself only calls Gemini.

### Added
- Genuine multimodal extraction: screenshots (slides, whiteboards, Kanban boards) sent as real image content blocks alongside the transcript in the extraction call. Each item tagged `source: "transcript" | "screenshot"`, surviving the planning pass and SQLite persistence.
- Retry-with-backoff for Gemini's transient `503`/`429` errors.
- `scripts/check_access.py` — standalone tool to verify Gemini/Calendar/Gmail API access before building against them.
- `--screenshot`/`-s` CLI flag (repeatable); multi-file Streamlit uploader routing transcript vs. screenshots by extension, with a validation error on more than one transcript file.
- Tests: `tests/test_llm.py`, `tests/test_source_tag.py`.

## [0.1.0] - 2026-08-19

Initial version. Transcript (`.txt`/`.vtt`/`.srt`/paste) → two-call LLM pipeline (extraction, then planning/dedup) → SQLite memory → optional Google Calendar event creation, dry-run by default. Streamlit UI and CLI.
