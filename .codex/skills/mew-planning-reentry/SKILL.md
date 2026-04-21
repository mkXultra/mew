---
name: mew-planning-reentry
description: Re-enter mew planning or long-session work after context compression, interruption, or a user asks what to do next. Use to recover current work, durable product decisions, deferred decisions, and the next safe action from mew's own state and memory.
---

# Mew Planning Reentry

Use this skill when resuming mew work after context compression, a long session, an interruption, or when deciding what to do next.

Goal: rebuild the current plan from mew itself, not from stale chat memory, and avoid drifting from the long-session charter after context compression.

If the user asks what to do next, gives long-session freedom, or asks whether
mew is good enough, route task selection through `mew-product-evaluator`.
The evaluator's active milestone and Done-when checklist are the value
function; do not keep selecting polish after context compression.

When reentry reaches task selection, require an explicit chain:

`active milestone -> single unmet/partial criterion -> next task`

If you cannot write that chain in one line, you are not ready to choose a task.
Run `mew-product-evaluator` again or rewrite the criterion/measurement instead
of drifting into nearby work.

## Decision Precedence

When deciding what to do next, apply this order:

1. The user's newest explicit instruction.
2. The long-session charter or plan saved before the session started.
3. `mew-product-evaluator` active milestone / Done-when decision, backed by
   `ROADMAP.md` and `ROADMAP_STATUS.md`.
4. Durable project decisions in mew memory and project docs such as
   `docs/ADOPT_FROM_REFERENCES.md`.
5. Current active task/session state and the latest context checkpoint.
6. `mew focus`, latest friction, and recent model recommendations.

Do not let a fresh active task, latest checkpoint, or external model comment override the session charter unless the user explicitly changed direction.
Do not let `mew focus` or an attractive recent suggestion override the active
milestone gate unless it closes that milestone's Done-when criteria.
Do not let a checkpoint "hold", "wait", or "do not spend a proof item" note
become the new task selector. Treat it as a local constraint only.
Do not treat a checkpoint, a commit boundary, or a clean worktree as a reason
to return control to the user during a long session.

## Reentry Checklist

Run the smallest useful set:

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
./mew memory --search "long session plan session charter objective non-goals task selection decision precedence ADOPT" --type project --json
./mew memory --search "observation before structural skeletons ADOPT references memory scope active recall cockpit recovery" --type project --json
./mew desk --kind coding --json
./mew focus --kind coding
./mew brief --kind coding
./mew memory --search "decision" --type project --json
./mew memory --search "next safe action context compression long session" --type project --json
./mew context --load --json
sed -n '1,120p' ROADMAP.md
sed -n '1,140p' ROADMAP_STATUS.md
```

If these do not explain deferred structural work, add a targeted project-memory search:

```bash
./mew memory --search "structural snapshot mailbox streaming trust reliability latency self-improve dogfood" --type project --json
```

If the next action may involve reference-derived architecture, inspect the adoption decision before selecting a task:

```bash
sed -n '1,180p' docs/ADOPT_FROM_REFERENCES.md
```

If an active work session or task is visible, inspect it before acting:

```bash
./mew work <task-id> --session --resume --allow-read .
./mew work <task-id> --cells
./mew work <task-id> --follow-status --json
```

If roadmap status is the question, use `mew-roadmap-status` after this reentry check.
If product direction or next implementation target is the question, use
`mew-product-evaluator` after this reentry check and choose only work that maps
to the active milestone's Done-when checklist.

## What To Extract

Summarize only:

- the session charter: objective, non-goals, task selection rule, stop/report trigger, and authoritative docs/decisions
- current active work or confirmation there is none
- durable product decisions from mew memory
- deferred work and why it is deferred
- pending approvals, recovery paths, or stale sessions
- latest known validation and whether it is current
- active roadmap milestone, unmet Done-when criteria, and which one the next
  task closes
- next safest action
- the one-line chain `milestone -> criterion -> task`
- output gate: whether this is an internal checkpoint or a user-visible report
- remaining long-session budget and the next allowed report trigger

## Drift Check

Before starting or continuing a self-improve task, compare it against the session charter and durable decisions:

- If the active task matches the charter, continue normally.
- If it was created from a recent model suggestion but does not match the charter, pause it or mark it blocked before doing implementation work.
- If the charter says to wait for concrete signal, do not start structural skeletons just because a reference review mentioned them.
- If `docs/ADOPT_FROM_REFERENCES.md` and a later memory decision disagree, prefer the newer explicit decision memory and mention the conflict.
- If the next step is chosen from `mew focus`, explain why it is compatible with the charter instead of treating focus as authoritative.
- If the next step does not map to the active milestone's Done-when checklist,
  do not implement it during a free-form long session; record it as deferred.
- If a checkpoint or external model opinion conflicts with the active milestone
  next action in `ROADMAP_STATUS.md`, prefer `ROADMAP_STATUS.md` unless the
  user explicitly changed direction.
- If you have already spent three cycles on blocker reduction or nearby polish
  for the same active criterion, do not start a fourth. Recommend running the
  gate proof or rewriting the criterion/measurement.

Validation rule: report validation visible in `brief`, task notes, or work-session resume as "last observed". Do not rerun full validation unless the user asked for validation or you changed files in this turn.

## Long-Session Rule

Before context may compress or after each meaningful chunk, leave a durable trail:

- record task/session notes for active work
- save product or roadmap decisions with `./mew memory --add ... --type project --scope private`
- save charter changes separately from progress checkpoints; progress checkpoints should not silently replace the charter
- include exact next action, validation state, and blockers
- do not rely on chat transcript alone for long-lived decisions

Checkpoint rule:

- A checkpoint is an internal continuity artifact, not a user-visible boundary.
- After saving a checkpoint, continue working unless the saved output gate says
  reporting is allowed.
- During a user-granted long session, return control only when one of these is
  true:
  - the explicit time/report boundary was reached
  - progress is blocked and cannot be worked through locally
  - approval or another user decision is required
  - the user explicitly interrupted and asked for control/status

If none of those is true, keep working silently after the checkpoint.

## Safety

Do not start large structural work from memory alone. Cross-check current `desk`, `focus`, `git status`, and any active work-session resume first.

Treat schema/skeleton decisions as product commitments. Prefer observation metrics over unused schemas unless a concrete use-case is active.
