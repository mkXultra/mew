# Mew Passive Surfaces

This file records the current passive-surface architecture after the 2026-04-17
dogfood session.

## Core Surfaces

### `mew run --once --passive-now --echo-effects`

Purpose: prove one passive cycle without waiting for a resident loop.

- `--passive-now` makes the first no-input cycle a `passive_tick`.
- `--echo-effects` prints the runtime effect id, status, reason, actions,
  summary, and outcome even when no outbox message is created.

Use this when validating passive behavior:

```bash
uv run mew run --once --passive-now --autonomous --autonomy-level propose --echo-effects
```

### `mew desk`

Purpose: expose a tiny desktop-pet view model without coupling a UI to raw
state.

States:

- `sleeping`
- `thinking`
- `typing`
- `alerting`

Useful commands:

```bash
uv run mew desk
uv run mew desk --json
uv run mew desk --write
```

Implementation notes:

- Uses canonical question status when available, so deferred and reopened
  questions behave correctly.
- Ignores active work sessions whose linked task is already done.
- Validates `--date` as strict `YYYY-MM-DD` before writing files.

### `mew mood`

Purpose: expose a compact emotional state model from local work state.

Useful commands:

```bash
uv run mew mood
uv run mew mood --json
uv run mew mood --show
uv run mew mood --write
```

Outputs:

- current label, such as `steady`, `concerned`, or `productive but watchful`
- `energy`, `worry`, and `joy` scores with reason lines
- compact signals from open tasks, open questions, and runtime effects
- optional `.mew/mood/YYYY-MM-DD.md` report for `mew bundle`

### `mew bundle`

Purpose: compose generated daily report markdown files into one reentry
artifact.

Useful commands:

```bash
uv run mew bundle --show
uv run mew bundle --json
uv run mew bundle --date 2026-04-17
```

Current source report paths:

- `.mew/journal/YYYY-MM-DD.md`
- `.mew/mood/YYYY-MM-DD.md`
- `.mew/morning-paper/YYYY-MM-DD.md`
- `.mew/dreams/YYYY-MM-DD.md`
- `.mew/self/learned-YYYY-MM-DD.md`

The command composes existing reports only. It does not generate journal,
morning-paper, dream, or self-memory reports. `mew mood --write` can generate
the mood source report.

## Experiments

These remain isolated under `experiments/` until their source-report behavior is
worth promoting.

- `experiments/mew-dream`: dream and learning report from state.
- `experiments/mew-bond`: self-memory and durable trait extraction.
- `experiments/mew-journal`: morning/evening report from tasks and runtime
  effects.
- `experiments/mew-mood`: energy/worry/joy scoring from state.
- `experiments/mew-morning-paper`: static-feed ranking against interest tags.
- `experiments/mew-passive-bundle`: original bundle composer prototype.
- `experiments/mew-desk`: original desk view-model prototype.

## Promotion Rule

Promote stable, low-risk surfaces before source generators.

Promoted:

- passive tick observability
- passive bundle composition
- desk view model
- mood scoring

Not promoted yet:

- journal generation
- morning-paper feed collection or ranking
- dream/self-memory generation
- any visual desktop shell

## Latest Verification

After the core `desk`, `mood`, and `bundle` promotions and review fixes:

```text
uv run pytest -q
762 passed, 6 subtests passed

./mew dogfood --scenario all --cleanup --json
status: pass
```

Review:

- `codex-ultra`: no blocking findings remain.
- `claude-ultra`: no blocking findings remain.
