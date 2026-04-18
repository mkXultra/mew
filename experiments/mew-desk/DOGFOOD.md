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

## 2026-04-18

Task: long-session continuation after observer/recovery validation.

Built:

- Added `terminal_pet.py`, a small renderer that consumes the existing
  `mew desk --json` view model from a file or stdin.
- Kept the prototype terminal-first and isolated under `experiments/mew-desk`
  instead of starting a GUI/Tauri surface too early.
- Added tests for alerting, fallback state handling, stdin loading, and file
  rendering.
- Applied external `codex-ultra` review polish: long focus text is compacted for
  glanceability and malformed counts degrade to zero instead of crashing.

Validation:

- `uv run pytest -q experiments/mew-desk` -> `11 passed`.

Product learning:

- `mew desk --json` is already enough to drive a visible resident shell.
- The next UI can stay dumb: it only needs to map `pet_state`, `focus`, and
  counts into a shape the human can keep nearby.
- A terminal renderer is not the final pet, but it proves the boundary before
  platform-specific desktop work.

## 2026-04-19

Task: `#153 Prototype mew-desk browser shell`

Buddy use:

- Created work session `#172` for task `#153`.
- Asked `mew work --live --max-steps 1` to inspect `experiments/mew-desk`
  before editing.
- Mew chose the same first move: inspect the existing isolated scaffold instead
  of touching core runtime code.

Built:

- Added `browser_pet.py`, a standalone HTML renderer for the existing
  `mew desk --json` view model.
- Kept it local-first: it reads a JSON file or stdin and writes HTML to stdout
  or `--output`.
- Added tests for state rendering, escaping, focus compaction, stdin/file
  handling, and unknown-state fallback.

Validation:

- `uv run pytest -q experiments/mew-desk` -> `17 passed`.
- `uv run --with ruff ruff check experiments/mew-desk` -> passed.
- Generated live-state HTML at `/tmp/mew-desk-browser.html`; it rendered
  `data-state="alerting"` from the current `mew desk` view model.

Product learning:

- `mew desk --json` can now drive both terminal and browser shells without any
  direct dependency on `.mew/state.json`.
- The UI boundary is still intentionally dumb. That is good: a future Tauri or
  tray app should not need to understand resident internals.
- The next useful UI proof is no longer "can it render?" but "can it stay open
  and refresh calmly?"
