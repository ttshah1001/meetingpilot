# MeetingPilot

MeetingPilot is a small agent that reads a meeting transcript (pasted text, `.txt`, `.vtt`, or `.srt`) — and, optionally, screenshots taken during the meeting (slides, whiteboards, Kanban boards) — and turns it into tracked action items with owners, due dates, priorities, source quotes, and confidence scores. It stores them in a local SQLite database so later meetings can surface work that is still open, and can push a task to Google Calendar, draft it in Gmail (both dry-run by default), or export it as a `.ics` file (no API keys or network required — the fallback if Google access or wifi isn't available). It can also optionally reconstruct a Mermaid diagram from a whiteboard/flowchart screenshot or a process described in the transcript.

Full architecture (diagrams, design rationale, known limitations) is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). See [CHANGELOG.md](CHANGELOG.md) for what changed and when.

## Setup

1. Clone the repo and enter it:

   ```bash
   git clone https://github.com/ttshah1001/meetingpilot.git
   cd meetingpilot
   ```

2. Install Python 3.11+ and [uv](https://docs.astral.sh/uv/). This project pins 3.11 in `.python-version`. If you only have 3.12+, `uv` will still install a 3.11 interpreter:

   ```bash
   uv python install 3.11
   uv sync --extra dev
   ```

   Prefer a venv instead of uv?

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

3. **LLM API key (required for extraction, planning, and diagram synthesis).** MeetingPilot uses the Google Gemini API (free tier, AI Studio) with forced function calling (structured JSON), not free-text parsing.

   - Create a free API key at [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey) — no credit card required.
   - Copy the example env file and paste the key:

     ```bash
     cp .env.example .env
     ```

   - Set `GEMINI_API_KEY=...` inside `.env`. Optionally override `GEMINI_MODEL` (default `gemini-flash-lite-latest` — chosen for its more generous free-tier daily quota; `gemini-3.5-flash`/`gemini-3.6-flash` both cap at 20 requests/day).

4. **Google Calendar + Gmail OAuth (optional — skip if you will demo with dry-run, which is the default).**

   1. Open [Google Cloud Console](https://console.cloud.google.com/) and create (or select) a project.
   2. **APIs & Services → Library** → enable **Google Calendar API** and **Gmail API**.
   3. **APIs & Services → OAuth consent screen** (or **Audience**, in the newer console UI):
      - User type: External (or Internal on a Workspace org).
      - App name: `MeetingPilot`.
      - Add your Google account as a test user if the app is in Testing (project owners don't need to add themselves — that's expected, not an error).
      - Under **Data Access**, add both scopes: `.../auth/calendar.events` and `.../auth/gmail.compose`.
   4. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
      - Application type: **Desktop app**.
      - Download the JSON file.
   5. Save that file as `credentials.json` in the project root (it is gitignored). `credentials.example.json` shows the expected shape.
   6. On the first live Calendar/Gmail action, a browser window opens requesting **both** scopes in one consent (`meetingpilot/google_auth.py`) — accept it, and MeetingPilot writes `token.json` next to the project (also gitignored). Later runs reuse and refresh that token automatically.
   7. `calendar.events` allows creating/updating events, not wiping the whole calendar. `gmail.compose` only allows creating drafts — the app never sends mail.

5. Run `python scripts/check_access.py` (or `uv run python scripts/check_access.py`) to verify all four API doors (Gemini text, Gemini vision, Calendar, Gmail) work before relying on them for a demo.

## Running it

From the project root, with the virtualenv managed by uv:

**Web UI (fastest demo):**

```bash
uv run streamlit run app.py
```

Drop a transcript + screenshots together in the uploader (or load a sample), leave Calendar/Gmail dry-run checked unless you completed Google OAuth, and click **Process Meeting**. Toggle "Generate diagram from content" in the sidebar to also try the Mermaid feature. Each item has a "Download .ics" button — that path needs no Google setup at all, useful if OAuth or wifi isn't available.

**CLI — extraction only (LLM call #1, JSON to stdout, no DB):**

```bash
uv run python -m meetingpilot \
  --transcript samples/01_sprint_planning.txt \
  --meeting-date 2026-08-19 \
  --extract-only
```

**CLI — full pipeline (ingest → extract → plan → SQLite), with screenshots + diagram synthesis** (`samples/04_kanban_board.png` is a ready-made sample screenshot for trying this):

```bash
uv run python -m meetingpilot \
  --transcript samples/01_sprint_planning.txt \
  --meeting-date 2026-08-19 \
  --title "Sprint planning" \
  --screenshot samples/04_kanban_board.png \
  --diagram
```

**CLI — Calendar/Gmail dry-run payloads (no live Google calls):**

```bash
uv run python -m meetingpilot \
  --transcript samples/01_sprint_planning.txt \
  --meeting-date 2026-08-19 \
  --push-calendar --push-gmail
```

**CLI — `.ics` export (no API keys, no network, no Google account):**

```bash
uv run python -m meetingpilot \
  --transcript samples/01_sprint_planning.txt \
  --meeting-date 2026-08-19 \
  --export-ics ./out
```

**CLI — actually create a Calendar event / Gmail draft** (requires `credentials.json` + a one-time browser login):

```bash
uv run python -m meetingpilot \
  --transcript samples/01_sprint_planning.txt \
  --meeting-date 2026-08-19 \
  --push-calendar --live-calendar \
  --push-gmail --live-gmail
```

Paste mode: omit `--transcript` and pipe text on stdin. Full flag list: `uv run python -m meetingpilot --help`.

Demo without Google credentials is the expected path: keep dry-run on. The UI/CLI still show the exact payload that would be sent.

## Running tests

No API keys and no Google account required. Mocks cover Calendar, Gmail, and the LLM layer; schema/date/dedup/memory tests are local.

```bash
uv run pytest -q
```

Equivalent with venv: `pytest -q`.

## Acknowledgments

- [Google Gemini API](https://ai.google.dev/) — structured function calling for extraction, planning, and diagram synthesis (free tier via AI Studio)
- [Google Calendar API](https://developers.google.com/calendar) and [Gmail API](https://developers.google.com/gmail/api) via `google-api-python-client` and `google-auth-oauthlib`
- [Mermaid](https://mermaid.js.org/) for diagram rendering
- [Streamlit](https://streamlit.io/), [Pydantic](https://docs.pydantic.dev/), [SQLAlchemy](https://www.sqlalchemy.org/), [python-dateutil](https://dateutil.readthedocs.io/)
- [uv](https://docs.astral.sh/uv/) for Python environments
- Cursor (Composer) and Claude Code were used to scaffold and implement this class project
