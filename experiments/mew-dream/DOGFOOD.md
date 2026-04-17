# mew-dream Dogfood Report

Date: 2026-04-17

## Goal

Use mew as a buddy to grow the isolated `mew-dream` side project without
touching core runtime code.

## What mew did

- Created coding task #75: `Dogfood mew-dream side project`.
- Started work session #101.
- Read `SIDE_PROJECTS.md`.
- Inspected `experiments/mew-dream`.
- Read `dream_journal.py` and `test_dream_journal.py`.
- Recommended the smallest next slice: add a `## Learnings` section to dream
  output, backed by tests.

## Implemented slice

- `render_dream` now writes:
  - non-done active tasks
  - a `## Learnings` section
- `collect_learnings` reads:
  - explicit `learnings`
  - `changes`
  - `decisions`
  - recent done-task notes from real mew state
- The prototype remains isolated under `experiments/mew-dream`.

## Validation

```bash
uv run pytest -q experiments/mew-dream
```

Result:

```text
5 passed
```

Generated from sample state:

```bash
uv run python experiments/mew-dream/dream_journal.py experiments/mew-dream/sample_state.json --output-dir /tmp/mew-dream-demo --date 2026-04-17
```

Generated from live mew state:

```bash
uv run python experiments/mew-dream/dream_journal.py .mew/state.json --output-dir /tmp/mew-dream-real --date 2026-04-17
```

Live-state dream excerpt:

```text
## Active tasks
- Subsidy research task [todo]
- Subsidy research constraints [todo]
- Subsidy research task [ready]
- Dogfood mew-dream side project [ready]

## Learnings
- Implemented the session #100 follow-up: idle work-session resume next_action now includes the task id when known (mew work <task-id> --live). Verified with uv run pytest -q tests/test_work_session.py.
- Implemented the session #99 recommendation: /help work now documents task-first /work-session <task-id> live usage, with test coverage. Verified with uv run pytest -q tests/test_commands.py.
```

## What mew learned about itself

- The side-project file was enough for mew to choose a small isolated slice.
- The existing prototype was too shallow: it recorded tasks and notes, but not
  what mew learned.
- Real `.mew/state.json` already contains enough task-note history to generate a
  useful first dream without adding core storage.

## Friction observed

- The resident work session needed an extra step after reading files to make a
  concrete recommendation. Bounded `max_steps` is safe, but it can stop just
  before the decision.
- `mew-dream` still has no direct command for writing into the real `.mew/dreams`
  location. That is acceptable for an experiment, but a future integration will
  need an explicit output gate.

## Would this make an AI more willing to live inside mew?

Slightly, yes. This does not solve passive autonomy by itself, but it gives mew
a concrete way to remember what it learned across work sessions. That is closer
to resident continuity than another cockpit-only polish.
