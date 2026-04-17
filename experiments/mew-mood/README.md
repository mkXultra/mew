# mew-mood

Small CLI-first experiment that reads a mew state JSON file and generates a
dated mood report.

Output:

- `.mew/mood/YYYY-MM-DD.md`

The report computes three conservative axes:

- `energy`: momentum versus open load.
- `worry`: unresolved questions, open attention, blocked work, and failures.
- `joy`: recent completed work and passed verification, reduced by unresolved
  questions or failed verification.

It is intentionally isolated from `src/mew`. The goal is to test whether mew can
make its passive state legible to a human before any desktop pet, journal, or
visual integration depends on a mood signal.

## Usage

```bash
uv run python experiments/mew-mood/mood_report.py experiments/mew-mood/sample_state.json --output-dir /tmp/mew-mood
```

Optionally override the output date:

```bash
uv run python experiments/mew-mood/mood_report.py experiments/mew-mood/sample_state.json --output-dir /tmp/mew-mood --date 2026-04-17
```

Read the generated report:

```bash
cat /tmp/mew-mood/.mew/mood/2026-04-17.md
```

Generate from this repository's live mew state:

```bash
uv run python experiments/mew-mood/mood_report.py .mew/state.json --output-dir /tmp/mew-mood-real
```

## Test

```bash
uv run pytest -q experiments/mew-mood
```
