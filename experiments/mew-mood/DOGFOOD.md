# mew-mood Dogfood Report

## 2026-04-17

Task: `#80 Prototype mew-mood side project`

Buddy use:

- Started work session `#106` for task `#80`.
- Asked `mew work --ai` to inspect `SIDE_PROJECTS.md` and adjacent experiments.
- Mew recommended the smallest slice: an isolated CLI-first generator that
  computes `energy`, `worry`, and `joy` from local state JSON.

Built:

- `mood_report.py` renders `.mew/mood/YYYY-MM-DD.md`.
- The report includes a mood label, three score axes, reasons for each score,
  and compact signal lines.
- The heuristic reads open tasks, done tasks, active work sessions, open
  questions, attention items, verification runs, and runtime effects.

Validation:

- `uv run pytest -q experiments/mew-mood` -> `6 passed`.
- Generated sample output at `/tmp/mew-mood/.mew/mood/2026-04-17.md`.
- Generated live-state output at `/tmp/mew-mood-real/.mew/mood/2026-04-17.md`.
- Live-state label was `productive but watchful`, driven by many completed
  verified tasks plus unresolved questions.

Early product learning:

- Mood is useful only if every score has reasons. A bare number would feel like
  decoration; reasons make it inspectable.
- Open questions are the strongest worry signal in the current live state.
- Passed verification and done tasks can coexist with worry, which is why
  `productive but watchful` matters as a label.

Would this make an AI more willing to live inside mew?

Yes, slightly. It gives the resident model a compact self-state surface that is
easier to inspect than raw counters and easier to show to a human than runtime
effects.
