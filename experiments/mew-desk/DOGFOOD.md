# mew-desk Dogfood Report

## 2026-04-17

Task: `#84 Prototype mew-desk state model`

Buddy use:

- Started work session `#109` for task `#84`.
- Asked `mew work --ai` to inspect `SIDE_PROJECTS.md` and adjacent experiments.
- Mew recommended the smallest slice: a CLI-first state-to-view-model mapper,
  not a real desktop app.

Built:

- `desk_state.py` renders `.mew/desk/YYYY-MM-DD.json` and `.md`.
- The view model exposes `sleeping`, `thinking`, `typing`, or `alerting`.
- It includes a short focus summary and counts for open tasks, questions,
  active work sessions, and open attention.

Validation:

- `uv run pytest -q experiments/mew-desk` -> `5 passed`.
- Generated sample output at `/tmp/mew-desk/.mew/desk/2026-04-17.json`.
- Generated live-state output at
  `/tmp/mew-desk-real/.mew/desk/2026-04-17.json`.
- Live-state pet state was `alerting` because three unanswered questions and
  three open attention items are present.
- The view model was promoted as the core `mew desk` command with text, JSON,
  and optional file output.

Early product learning:

- A desktop pet should not read raw `.mew/state.json` directly.
- The view model gives the UI a stable, tiny contract while the resident runtime
  continues evolving.
- In the current live state, unanswered questions dominate and should put the
  pet into `alerting`.

Would this make an AI more willing to live inside mew?

Yes, slightly. It creates the first boundary between resident state and visible
presence. It is not the desktop shell yet, but it is the correct substrate for
one.
