# mew-dream

Small CLI-first experiment that reads a mew state JSON file and generates dated markdown files under a local `.mew` directory.

Outputs:

- `.mew/dreams/YYYY-MM-DD.md`
- `.mew/journal/YYYY-MM-DD.md`

## Usage

```bash
uv run python experiments/mew-dream/dream_journal.py experiments/mew-dream/sample_state.json --output-dir /tmp/mew-dream
```

Optionally override the output date:

```bash
uv run python experiments/mew-dream/dream_journal.py experiments/mew-dream/sample_state.json --output-dir /tmp/mew-dream --date 2026-04-17
```

## Test

```bash
uv run pytest -q experiments/mew-dream
```

This prototype is intentionally isolated from `src/mew`.
