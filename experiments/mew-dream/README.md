# mew-dream

Small CLI-first experiment that reads a mew state JSON file and generates dated markdown files under a local `.mew` directory.

Outputs:

- `.mew/dreams/YYYY-MM-DD.md`
- `.mew/journal/YYYY-MM-DD.md`

The dream file summarizes non-done active tasks, active work sessions, and a
`Learnings` section. It uses optional `learnings`, `changes`, and `decisions`
lists when present, and it can also derive recent learnings from done-task notes
in a real mew `.mew/state.json`. That keeps the prototype focused on passive
self-improvement memory without touching the core mew runtime.

## Usage

```bash
uv run python experiments/mew-dream/dream_journal.py experiments/mew-dream/sample_state.json --output-dir /tmp/mew-dream
```

Optionally override the output date:

```bash
uv run python experiments/mew-dream/dream_journal.py experiments/mew-dream/sample_state.json --output-dir /tmp/mew-dream --date 2026-04-17
```

Read the generated dream:

```bash
cat /tmp/mew-dream/.mew/dreams/2026-04-17.md
```

Generate from this repository's live mew state:

```bash
uv run python experiments/mew-dream/dream_journal.py .mew/state.json --output-dir /tmp/mew-dream-real
```

## Test

```bash
uv run pytest -q experiments/mew-dream
```

This prototype is intentionally isolated from `src/mew`.
