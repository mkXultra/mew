# mew-bond

Small CLI-first experiment that reads a mew state JSON file and generates a
cross-task self-memory markdown report.

Output:

- `.mew/self/learned-YYYY-MM-DD.md`

The report has four sections:

- `Durable traits`
- `Recent self learnings`
- `Continuity cues`
- `Promotion audit`

It is intentionally isolated from `src/mew`. The goal is to test whether mew can
extract useful self-continuity from existing task notes, explicit state fields,
and active work-session metadata before adding any core self-memory feature.
When no explicit durable trait exists, the prototype only promotes a recent
self-learning into a durable trait if the same normalized learning appears at
least twice. The deterministic `Promotion audit` section shows, for each recent
self-learning, whether it matched an explicit durable trait, repeated enough to
be promoted, or stayed a continuity cue because it was seen once.

## Usage

```bash
uv run python experiments/mew-bond/self_memory.py experiments/mew-bond/sample_state.json --output-dir /tmp/mew-bond
```

Generate from another copied state fixture:

```bash
uv run python experiments/mew-bond/self_memory.py /tmp/copied-state.json --output-dir /tmp/mew-bond-copy
```

Keep isolated reviews pointed at fixtures or copied state files rather than live
`.mew` state.

Read the generated report:

```bash
cat /tmp/mew-bond/.mew/self/learned-2026-04-17.md
```

## Test

```bash
UV_CACHE_DIR=.uv-cache uv run pytest --no-testmon -q experiments/mew-bond
```
