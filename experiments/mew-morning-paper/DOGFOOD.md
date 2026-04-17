# mew-morning-paper Dogfood Report

## 2026-04-17

Task: `#81 Prototype mew-morning-paper side project`

Buddy use:

- Started work session `#107` for task `#81`.
- Asked `mew work --ai` to inspect `SIDE_PROJECTS.md` and adjacent experiment
  patterns.
- Mew recommended the smallest slice: static fixture feed, local interest tags,
  simple tag-overlap scoring, and one markdown report.

Built:

- `morning_paper.py` renders `.mew/morning-paper/YYYY-MM-DD.md`.
- It reads `sample_feed.json`, optional state interests, and explicit
  `--interest` flags.
- Ranking uses exact tag matches first, then title/summary mentions.
- The report separates direct matches into `Top picks` and unmatched items into
  `Explore later` so low-score exploration does not pollute the main list.

Validation:

- `uv run pytest -q experiments/mew-morning-paper` -> `6 passed`.
- Generated sample output at
  `/tmp/mew-morning-paper/.mew/morning-paper/2026-04-17.md`.

Early product learning:

- This should stay offline until the ranking/report shape feels useful.
- The first value is not crawling; it is remembering what to ignore.
- Interest tags need to become durable mew memory later, not command flags.

Would this make an AI more willing to live inside mew?

Somewhat. It gives the resident model a reason to wake up overnight even when
there is no coding task: gather and rank context for the next morning. It is
still a prototype until real feeds and feedback learning exist.
