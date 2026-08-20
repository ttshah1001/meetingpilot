# MeetingPilot — live demo script

Say this roughly as written. Target: **about 6 minutes**, leaving room in a 15-minute presentation slot for framing/motivation and a limitations discussion around it. Every step below has been run for real against the live Gemini API before writing this — not just written and assumed to work.

**Prep (before the timer):**
```bash
uv sync --extra dev
uv run python scripts/check_access.py   # confirms Gemini + Calendar + Gmail are all reachable
rm -f meetings.db                       # fresh sidebar, no leftover demo state
uv run streamlit run app.py
```
`.env` needs `GEMINI_API_KEY` set. Leave **Calendar dry-run** and **Gmail dry-run** checked in the sidebar the whole time — a missing/expired Google login cannot kill the demo this way.

---

### 0:00–0:30 — Frame the product

> "MeetingPilot is not a chatbot with a prompt. It's ingestion, two forced LLM calls — extraction, then planning — memory, and three tools: Calendar, Gmail, and offline `.ics` export. Everything runs on Google Gemini's free tier. I'll run a few sample meetings so you see state and multimodal input, not just a one-shot parse."

Point at the `docs/ARCHITECTURE.md` diagram if it's on a slide; otherwise the sidebar + main form is enough.

---

### 0:30–1:45 — Clean extraction + multimodal screenshot (sample 01 + Kanban image)

1. In **Drop transcript + screenshots**, upload `samples/01_sprint_planning.txt` **and** `samples/04_kanban_board.png` together in one drag.
2. Meeting title: `Sprint planning`. Meeting date: `2026-08-19` (a Wednesday — matters for "Friday" / "next week").
3. Click **Process Meeting**.
4. While it spins: "That's one Gemini call reading the transcript *and* the screenshot together — real multimodal input, not OCR bolted on afterward. Then a second call that only plans: merge, flag gaps, rank."

**What to point at when results appear**

- Items grouped by owner — 11 total: 7 from the transcript, 4 from the Kanban board.
- Expand a transcript item (e.g. Marcus — draft the Q3 checkout roadmap): note the 📝 badge, due date resolved to **2026-08-21**, the source quote.
- Expand a screenshot item (e.g. **Ship v2 payments API**): note the 🖼️ badge and that the source quote is a description of the card, not a spoken line — "this task was never said out loud, it came straight from reading the board image."
- Point out **"Update pricing copy"** (the Done column) is *not* in the list: "already-completed work gets filtered, same discipline as the transcript side."

Click **Push to Calendar** on one dated item — show the dry-run JSON payload (`summary`/`description`/`start.date`). "Same body a real `events.insert` call would send."

Click **Draft Gmail** on the same item — show the dry-run preview. "Structurally draft-only — this code path can only call `drafts().create`, there's no send call anywhere in the module."

Click **Download .ics** on one item — open the downloaded file if easy, or just note: "no API key, no network, works even if Google or the venue wifi is down."

---

### 1:45–2:45 — Memory + duplicates (sample 03)

1. Load `samples/03_standup_followup.txt` (transcript only this time — clear the screenshot upload first).
2. Title: `Standup follow-up`. Date: `2026-08-20`.
3. Click **Process Meeting**.

**What to point at**

- Sidebar: **Open items from previous meetings** — yesterday's roadmap/Figma/tests should appear as still open.
- The new Marcus roadmap row shows **"Still open from last time."**
- Marcus mentions the roadmap **twice** in this transcript — point at a single merged item: "planning collapsed the duplicate. Extraction is allowed to be redundant; planning is the cleanup pass."

---

### 2:45–3:30 — Summary + diagram synthesis, with chat refinement (optional bonus beat, if time allows)

1. Toggle **"Generate summary + diagrams"** in the sidebar's "⚙️ Testing & advanced options" before processing (or reprocess sample 01 + the Kanban image with it on).
2. Point at the summary paragraph, then the rendered Mermaid diagram it reconstructs from the board layout. Click **"Download PNG"** or **"Download SVG"** on it — real client-side download, no server round-trip.
3. Scroll to **"Refine summary / diagrams"** and type something in the chat box — e.g. *"make the summary one sentence"* — and hit enter. Point out the summary above visibly shortens/updates in place.

> "This is opt-in and off by default — it's an extra LLM call, and not every meeting has anything worth summarizing or diagramming. The model itself decides how many diagrams are warranted — zero, one, or more — it's not a fixed count. If there's nothing describable, it says so honestly instead of inventing structure — same discipline as the extraction layer. And it's not a one-shot generation — you can chat with it afterward to refine the summary or a diagram, and it edits in place rather than starting over."

---

### 3:30–4:15 — Limitation (sample 02) — graders reward honesty

1. Load `samples/02_design_review.vtt` (clear any screenshot upload).
2. Title: `Design review`. Date: `2026-08-19`.
3. Click **Process Meeting**.

**Deliberately imperfect extraction to discuss**

Point at **Unassigned / missing owner** rows — the transcript never names an owner for several tasks (empty-state copy, the follow-up review). The UI flags **missing owner** and **needs review**, with a **proposed due date** when none was spoken.

> "A one-shot prompt would often hallucinate an owner here. We leave it null, flag it, and propose a default instead of pretending the meeting was clear. We also don't split 'draft Friday / final on the 28th' into two milestones — one task, one date, the quote is the audit trail."

Optional: point at the `.vtt` timestamps in the speaker-turns table — ingestion isn't text-only.

---

### 4:15–4:45 — Close

> "51 tests cover schema, date math, dedup, SQLite memory, Gemini's response parsing, and mocked Calendar/Gmail/.ics — `uv run pytest -q`. Everything ran live against the real Gemini API before this demo was written, including the multimodal and diagram paths. Live Calendar/Gmail push is documented in the README; we stayed on dry-run so nothing here depends on OAuth working in this room."

Stop. Do not start a fourth transcript unless there's real time left.

---

## Known risks for this specific demo

- **Gemini's free-tier daily quota** (`gemini-flash-lite-latest`, chosen specifically for headroom) is not a documented "unlimited" guarantee — see `docs/ARCHITECTURE.md`. Don't rehearse this script more than a few times back-to-back right before presenting; get a fresh API key close to demo day if unsure.
- If Gemini itself is down or over quota mid-demo, there is no fallback — extraction/planning both need a live call. `.ics` export and dry-run Calendar/Gmail payloads only work *after* a successful extraction+planning pass, not as a substitute for it.
