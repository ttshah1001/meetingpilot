# MeetingPilot — 3-minute live demo script

Say this roughly as written. Total target: **about 3 minutes**. Use dry-run the whole time so a missing Google login cannot kill the demo.

**Prep (before the timer):** `uv sync --extra dev`, `.env` has `ANTHROPIC_API_KEY`, then `uv run streamlit run app.py`. Leave **Calendar dry-run** checked in the sidebar. If `meetings.db` already exists from a rehearsal, delete it so the sidebar starts empty: `rm meetings.db`.

---

### 0:00–0:20 — Frame the product

> “MeetingPilot is not a chatbot with a prompt. It is six layers: ingest, extract, plan, remember, calendar tool, and a UI. I’ll run two sample meetings so you can see state, not just a one-shot parse.”

Point at the README architecture diagram if it is on screen; otherwise the sidebar + main form is enough.

---

### 0:20–1:10 — Clean extraction (sample 01)

1. In **Load a sample transcript**, choose `01_sprint_planning.txt`.
2. Set **Meeting title** to `Sprint planning`.
3. Set **Meeting date** to `2026-08-19` (a Wednesday — this matters for “Friday” / “next week”).
4. Click **Process Meeting**.
5. While it spins, say: “That spinner is two Anthropic tool calls. Call one extracts a strict JSON schema. Call two only plans: merge, flag gaps, rank.”

**What to point at when results appear**

- The **normalized speaker turns** table at the bottom (ingestion worked: `Priya`, `Marcus`, `Lin`, `Samir`).
- The **action items grouped by owner** (Marcus / Lin / Samir / Priya).
- Expand **Marcus — draft the Q3 checkout roadmap**.
  - Due date should resolve to **2026-08-21** (that Wednesday’s Friday).
  - Expand to show the **source quote**.
  - Note the **confidence** score.
- Expand **Priya — stakeholder review**. Due should be **2026-08-28** if the model copied “next Friday” (the date resolver treats that as the following Friday).

Click **Push to Calendar** on one high-confidence dated item. Show the JSON payload (`summary` = task, `description` contains owner + quote, `start.date` = due date). Say: “Dry-run. Same body `events.insert` would send; the demo does not need a live Google account.”

---

### 1:10–2:10 — Memory + duplicates (sample 03)

1. Load `03_standup_followup.txt`.
2. Title: `Standup follow-up`. Date: `2026-08-20`.
3. Click **Process Meeting**.

**What to point at**

- Sidebar: **Open items from previous meetings** — yesterday’s roadmap / Figma / tests should appear as still open.
- On the new Marcus roadmap row, the **Still open from last time** note (same owner, same work).
- Marcus says the roadmap **twice** in this transcript. Point at a **single** planned roadmap item and say: “Planning merged the duplicate. Extraction is allowed to be redundant; planning is the cleanup step.”

This is the “agent with state” beat. Do not skip it.

---

### 2:10–2:50 — Limitation (sample 02) — graders reward honesty

1. Load `02_design_review.vtt`.
2. Title: `Design review`. Date: `2026-08-19`.
3. Click **Process Meeting**.

**Deliberately imperfect extraction to discuss**

Point at **Unassigned / missing owner** rows:

- Avery: “Someone needs to tighten the empty-state copy.”
- Jordan: “Let’s just say it should be done by Friday. Whoever grabs it, grab it.”
- Avery: “Somebody — really anybody — needs to book a follow-up review next week.”

The UI should flag **missing owner** and **needs review**, with a **proposed due date** (meeting + 7 days when no date was spoken, or Friday when they said Friday). Confidence should be lower than Marcus’s roadmap from sample 01.

> “Here’s a limitation: the transcript never names an owner. A one-shot prompt would often hallucinate one. We leave `owner` null, flag it, and propose a default instead of pretending the meeting was clear. Fix: add a speaker roster to ingestion, or a human confirm step before Calendar push. We also don’t split ‘draft Friday / final on the 28th’ into two milestones — one task, one date.”

Optional: mention `.vtt` timestamps in the turns table (`00:00:10.000 --> …`) to show ingestion is not text-only.

---

### 2:50–3:00 — Close

> “Tests cover schema, date math, dedup, SQLite memory, and a mocked Calendar insert — `uv run pytest -q`. Live Calendar is documented in the README; today we stayed on dry-run so the demo cannot flake on OAuth.”

Stop. Do not start a fourth transcript.
