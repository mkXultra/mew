# mew-bond

Small CLI-first experiment that reads a mew state JSON file and generates a
cross-task self-memory markdown report.

Output:

- `.mew/self/learned-YYYY-MM-DD.md`

The report has three sections:

- `Durable traits`
- `Recent self learnings`
- `Continuity cues`

It is intentionally isolated from `src/mew`. The goal is to test whether mew can
extract useful self-continuity from existing task notes, explicit state fields,
and active work-session metadata before adding any core self-memory feature.

## Usage

```bash
uv run python experiments/mew-bond/self_memory.py experiments/mew-bond/sample_state.json --output-dir /tmp/mew-bond
```

Generate from this repository's live mew state:

```bash
uv run python experiments/mew-bond/self_memory.py .mew/state.json --output-dir /tmp/mew-bond-real
```

Read the generated report:

```bash
cat /tmp/mew-bond/.mew/self/learned-2026-04-17.md
```

## Test

```bash
uv run pytest -q experiments/mew-bond
```
