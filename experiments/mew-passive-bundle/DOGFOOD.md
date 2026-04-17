# mew-passive-bundle Dogfood Report

## 2026-04-17

Task: `#82 Prototype mew passive bundle side project`

Buddy use:

- Started work session `#108` for task `#82`.
- Asked `mew work --ai` to inspect the side-project state and recommend the
  smallest integration pass.
- Mew recommended composing existing generated markdown reports, not generating
  or promoting them yet.

Built:

- `passive_bundle.py` renders `.mew/passive-bundle/YYYY-MM-DD.md`.
- It scans a local reports root for journal, mood, morning paper, dream, and
  self-memory reports for one date.
- The bundle includes an included/missing summary, reentry hints, and one
  section per found report.

Validation:

- `uv run pytest -q experiments/mew-passive-bundle` -> `3 passed`.
- Generated journal, mood, and morning-paper reports under `/tmp/mew-daily`.
- Generated bundle at
  `/tmp/mew-daily/.mew/passive-bundle/2026-04-17.md`.
- Live bundle included Journal, Mood, and Morning Paper, and reported missing
  Dream and Self Memory.

Early product learning:

- Composition is the right pre-core step. The individual reports can remain
  experiments while mew learns which one is worth surfacing first.
- Missing-report visibility matters: it tells the resident model what passive
  artifact was not produced yet.
- A single daily bundle is a better reentry object than five unrelated files.

Would this make an AI more willing to live inside mew?

Yes. This is the first side-project layer that feels like a daily cockpit
artifact rather than a standalone report. It gives a resident model one file to
open at the start of a day.
