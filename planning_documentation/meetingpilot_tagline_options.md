# MeetingPilot — tagline options

Goal: one line, in italics under the "MeetingPilot" title, that covers the actual feature set — extraction/tasks, memory, Calendar/Gmail/Tasks/.ics, and the summary+diagram+chat-refine layer — without turning into a feature list.

Currently live in the app (option 1). Swap by editing the `st.caption(...)` call right under `st.title("MeetingPilot")` in `app.py`.

1. **"From transcript to clarity — tasks, summaries, and diagrams, automatically."**
   Broadest one-liner; names all three output types without listing every tool.

2. **"Say it once. MeetingPilot remembers, plans, and shows the rest."**
   More personality/voice-forward; "remembers" nods to memory, "plans" nods to tasks, "shows" nods to summaries/diagrams.

3. **"Every meeting, understood — action items, summaries, and diagrams from what was actually said."**
   Leans hardest on "faithful read, not invented" — matches the app's actual design philosophy, slightly longer.

4. **"Turn conversation into action — tasks, summaries, and diagrams, on autopilot."**
   Plays on the "Pilot" in the name; punchier, more marketing-toned.

5. **"Meetings in. Clarity out."**
   Shortest, most abstract — works well visually but doesn't name any specific feature.

6. **"Read the room, remember the work — tasks, summaries, and diagrams from every meeting."**
   Slightly longer, leans into the multimodal ("read the room" = screenshots too) angle.

7. **"From what was said to what gets done."**
   Short, memorable, action-oriented — implicit about summaries/diagrams rather than explicit.

## Recommendation

Option 1 for the live default — it's the most complete without being a bullet list, and reads naturally as one sentence. Option 7 as a backup if you want something shorter/punchier for a slide title instead of the app itself.
