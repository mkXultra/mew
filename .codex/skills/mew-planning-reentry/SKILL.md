---
name: mew-planning-reentry
description: Re-enter mew planning or long-session work after context compression, interruption, or a user asks what to do next. Use to recover current work, durable product decisions, deferred decisions, and the next safe action from mew's own state and memory.
---

# Mew Planning Reentry

Use this skill when resuming mew work after context compression, a long session, an interruption, or when deciding what to do next.

Goal: rebuild the current plan from mew itself, not from stale chat memory.

## Reentry Checklist

Run the smallest useful set:

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
./mew desk --kind coding --json
./mew focus --kind coding
./mew brief --kind coding
./mew memory --search "decision" --type project --json
./mew memory --search "next safe action context compression long session" --type project --json
./mew context --load --json
```

If these do not explain deferred structural work, add a targeted project-memory search:

```bash
./mew memory --search "structural snapshot mailbox streaming trust reliability latency self-improve dogfood" --type project --json
```

If an active work session or task is visible, inspect it before acting:

```bash
./mew work <task-id> --session --resume --allow-read .
./mew work <task-id> --cells
./mew work <task-id> --follow-status --json
```

If roadmap status is the question, use `mew-roadmap-status` after this reentry check.

## What To Extract

Summarize only:

- current active work or confirmation there is none
- durable product decisions from mew memory
- deferred work and why it is deferred
- pending approvals, recovery paths, or stale sessions
- latest known validation and whether it is current
- next safest action

Validation rule: report validation visible in `brief`, task notes, or work-session resume as "last observed". Do not rerun full validation unless the user asked for validation or you changed files in this turn.

## Long-Session Rule

Before context may compress or after each meaningful chunk, leave a durable trail:

- record task/session notes for active work
- save product or roadmap decisions with `./mew memory --add ... --type project --scope private`
- include exact next action, validation state, and blockers
- do not rely on chat transcript alone for long-lived decisions

## Safety

Do not start large structural work from memory alone. Cross-check current `desk`, `focus`, `git status`, and any active work-session resume first.

Treat schema/skeleton decisions as product commitments. Prefer observation metrics over unused schemas unless a concrete use-case is active.
