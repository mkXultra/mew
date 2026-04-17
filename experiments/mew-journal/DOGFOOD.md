# mew-journal Dogfood Report

## 2026-04-17

Task: `#79 Prototype mew-journal side project`

Buddy use:

- Started work session `#105` for task `#79`.
- Asked `mew work --ai` to inspect `SIDE_PROJECTS.md` plus adjacent
  `mew-dream` and `mew-bond` experiments.
- Mew recommended the smallest slice: an isolated CLI-first generator that
  writes one dated markdown journal from existing state JSON.

Built:

- `journal_report.py` renders `.mew/journal/YYYY-MM-DD.md`.
- Morning sections summarize yesterday, today's active tasks, and one short
  mew note.
- Evening sections summarize progress, stuck points, and tomorrow hints.
- The generator reads tasks, done-task notes, active work sessions, open
  questions, and runtime effects.

Validation:

- `uv run pytest -q experiments/mew-journal` -> `5 passed`.
- Generated sample output at `/tmp/mew-journal/.mew/journal/2026-04-17.md`.
- Generated live-state output at
  `/tmp/mew-journal-real/.mew/journal/2026-04-17.md`.

Early product learning:

- Daily continuity is different from dream/self-memory output: it should be
  readable by the human first, but still preserve enough state for a model to
  reenter tomorrow.
- Open questions and active work sessions are the strongest stuck-point signal.
- Quiet runtime effects become much more useful after `--echo-effects` because
  they can be trusted as observable passive cycles.

Would this make an AI more willing to live inside mew?

Yes, slightly. A daily journal gives mew a less brittle reentry surface than raw
state JSON or long chat history. It is not enough by itself, but it is a useful
layer between passive runtime memory and a future resident shell.
