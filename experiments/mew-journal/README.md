# mew-journal

Small CLI-first experiment that reads a mew state JSON file and generates a
dated morning/evening markdown journal.

Output:

- `.mew/journal/YYYY-MM-DD.md`

The report has two top-level sections:

- `Morning`: yesterday, today, and one short mew note.
- `Evening`: progress, stuck points, and tomorrow hints.

It is intentionally isolated from `src/mew`. The goal is to test whether mew can
turn its existing task state, work sessions, open questions, and runtime effects
into a useful daily continuity artifact before adding any core journal feature.

## Usage

```bash
uv run python experiments/mew-journal/journal_report.py experiments/mew-journal/sample_state.json --output-dir /tmp/mew-journal
```

Optionally override the output date:

```bash
uv run python experiments/mew-journal/journal_report.py experiments/mew-journal/sample_state.json --output-dir /tmp/mew-journal --date 2026-04-17
```

Read the generated report:

```bash
cat /tmp/mew-journal/.mew/journal/2026-04-17.md
```

Generate from this repository's live mew state:

```bash
uv run python experiments/mew-journal/journal_report.py .mew/state.json --output-dir /tmp/mew-journal-real
```

## Test

```bash
uv run pytest -q experiments/mew-journal
```
