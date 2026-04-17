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

### `mew journal`

Purpose: generate a morning/evening daily report from local state.

Useful commands:

```bash
uv run mew journal
uv run mew journal --show
uv run mew journal --json
uv run mew journal --write
```

Outputs:

- yesterday/progress from completed tasks and runtime effects
- today/tomorrow hints from active tasks
- stuck points from open questions and active work sessions
- optional `.mew/journal/YYYY-MM-DD.md` report for `mew bundle`

### `mew morning-paper`

Purpose: rank a static feed JSON against interest tags and generate a morning
paper report.

Useful commands:

```bash
uv run mew morning-paper feed.json --interest ai
uv run mew morning-paper feed.json --interest ai --json
uv run mew morning-paper feed.json --interest ai --show
uv run mew morning-paper feed.json --interest ai --write
```

Outputs:

- interest tags from explicit flags and local state
- scored top picks and lower-priority exploration items
- optional `.mew/morning-paper/YYYY-MM-DD.md` report for `mew bundle`

This is only static-feed ranking. Web collection remains outside core.

### `mew self-memory`

Purpose: preserve what mew has learned about itself for context compression and
future reentry.

Useful commands:

```bash
uv run mew self-memory
uv run mew self-memory --json
uv run mew self-memory --show
uv run mew self-memory --write
```

Outputs:

- durable traits from local state and preference memory
- recent self learnings from state, memory, and completed task notes
- continuity cues from active work sessions
- optional `.mew/self/learned-YYYY-MM-DD.md` report for `mew bundle`

### `mew dream`

Purpose: preserve an overnight-style reflection from active tasks, active work
sessions, and recent learnings.

Useful commands:

```bash
uv run mew dream
uv run mew dream --json
uv run mew dream --show
uv run mew dream --write
```

Outputs:

- active tasks
- active work sessions and next actions
- recent learnings
- optional `.mew/dreams/YYYY-MM-DD.md` report for `mew bundle`

### `mew bundle`

Purpose: compose generated daily report markdown files into one reentry
artifact.

Useful commands:

```bash
uv run mew bundle --show
uv run mew bundle --json
uv run mew bundle --date 2026-04-17
uv run mew bundle --generate-core --morning-feed feed.json --interest ai --show
```

Current source report paths:

- `.mew/journal/YYYY-MM-DD.md`
- `.mew/mood/YYYY-MM-DD.md`
- `.mew/morning-paper/YYYY-MM-DD.md`
- `.mew/dreams/YYYY-MM-DD.md`
- `.mew/self/learned-YYYY-MM-DD.md`

The command composes existing reports only.
`mew journal --write`, `mew mood --write`, `mew self-memory --write`, and
`mew dream --write`, and `mew morning-paper ... --write` can generate core
source reports.
`--generate-core` can generate journal and mood first; `--morning-feed` adds the
static morning-paper source report before composing. It also generates
dream and self-memory. Generated source reports are written under
`--reports-root`, then composed into `--output-dir`.
When a generated report would overwrite different existing content, mew writes
a sibling `.bak` file first.

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
- journal generation
- static-feed morning paper ranking
- self-memory generation
- dream generation

Not promoted yet:

- morning-paper feed collection
- any visual desktop shell

## Latest Verification

After the core `desk`, `journal`, `mood`, `morning-paper`, `self-memory`,
`dream`, and `bundle` promotions and review fixes:

```text
uv run pytest -q
789 passed, 6 subtests passed

./mew dogfood --scenario all --cleanup --json
status: pass
```

Review:

- `codex-ultra`: no blocking findings remain.
- `claude-ultra`: no blocking findings remain.
