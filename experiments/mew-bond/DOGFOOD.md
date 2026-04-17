# mew-bond Dogfood Report

Date: 2026-04-17

## Goal

Prototype cross-task self-memory without touching mew core.

## What mew did

- Created coding task #77: `Prototype mew-bond self memory`.
- Started work session #103.
- Read `SIDE_PROJECTS.md`.
- Read recent `mew-dream` dogfood notes.
- Recommended an isolated `experiments/mew-bond/self_memory.py` report
  generator over existing mew state.

## Implemented slice

- `self_memory.py` reads a local state JSON file.
- It writes `.mew/self/learned-YYYY-MM-DD.md`.
- The report includes:
  - durable traits
  - recent self learnings
  - active work-session continuity cues
- It extracts self learnings from explicit state fields and recent done-task
  notes.
- It deduplicates repeated learnings while preserving order.
- It now conservatively promotes repeated self learnings into durable traits
  only when the same normalized learning appears at least twice.

## Validation

```bash
uv run pytest -q experiments/mew-bond
```

Result:

```text
9 passed
```

Generated from sample state:

```bash
uv run python experiments/mew-bond/self_memory.py experiments/mew-bond/sample_state.json --output-dir /tmp/mew-bond-demo --date 2026-04-17
```

Generated from live mew state:

```bash
uv run python experiments/mew-bond/self_memory.py .mew/state.json --output-dir /tmp/mew-bond-real --date 2026-04-17
```

Live-state report excerpt:

```text
## Recent self learnings
- Dogfooded mew-dream live-state report with work session #102. Added active work-session continuity rendering and tests, updated sample/README/DOGFOOD. Verified with uv run pytest -q experiments/mew-dream.
- Dogfooded mew-dream side project with work session #101. Added dream Learnings output from explicit learnings/changes/decisions and recent done-task notes, verified sample and live-state generation, and recorded DOGFOOD.md. Verified with uv run pytest -q experiments/mew-dream.

## Continuity cues
- No active continuity cues
```

## What mew learned about itself

- Existing task notes already contain useful self-learning seeds.
- There is still no durable trait source in live state, so traits render empty
  unless explicit state fields exist or the same self-learning repeats.
- A future core self-memory feature should probably promote selected learnings
  into durable traits instead of only replaying recent task notes.

## Friction observed

- The resident session again needed bounded read steps before making a concrete
  recommendation. This is safe but sometimes slow.
- The prototype can infer repeated traits conservatively, but it cannot yet
  decide whether a one-off learning is important enough to keep long term. That
  selection likely needs model judgment later.

## Would this make an AI more willing to live inside mew?

Yes, more than cockpit polish. It starts to answer "what have I learned across
tasks?" rather than only "what was I doing in this task?".
