---
name: mew-context-save
description: Save durable mew context before a long session, context compression risk, interruption, or major handoff. Use to write current intent, next action, validation state, blockers, active work-session notes, and durable product decisions into mew's own memory/state before continuing.
---

# Mew Context Save

Use this skill before starting a long session, when context may compress, before pausing, or after a meaningful work chunk.

Goal: make the next resident recover from mew itself, not from chat history.

## Save Checklist

First inspect the current state so the saved context is accurate:

```bash
date '+%Y-%m-%d %H:%M:%S %Z'
git status --short
./mew desk --kind coding --json
./mew focus --kind coding
./mew brief --kind coding
```

If active work exists, save a session note:

```bash
./mew work <task-id> --session-note "<current intent; exact next action; validation state; blockers; pending approvals/recovery>"
```

If there is a durable product or roadmap decision, save it to typed project memory:

```bash
./mew memory --add "<Decision YYYY-MM-DD: decision, rationale, deferred work, next trigger>" \
  --type project \
  --scope private \
  --name "Decision: <short name>" \
  --description "<when future sessions should retrieve this>"
```

Then verify the memory is retrievable with a short query:

```bash
./mew memory --search "<short decision keywords>" --type project --json
```

## What To Save

Save only durable context:

- current intent and why it matters
- exact next action and command if known
- validation state: current, last observed, or not run
- blockers, pending approvals, recovery paths, or user pivots
- product/roadmap decisions and why alternatives were deferred
- trigger condition for revisiting a deferred structural choice

Do not save noisy transcript summaries, temporary thoughts, or facts already obvious from git status.

## Long-Session Start

Before a user-approved long session, always save:

- planned time budget and start time
- the chosen objective for the session
- non-goals for the session
- task selection rules, including what evidence is required before changing direction
- authoritative docs or decision memories that future reentry must consult
- what should happen if context compresses
- how to know the session should stop or report back

For long sessions, prefer one concise `mew memory --add` planning note named like `Long session charter: <short name>` plus session notes on active work as it evolves.

Write the charter separately from progress checkpoints. Checkpoints record what just happened; the charter records what should continue to govern task selection after context compression.

For free-form mew improvement sessions, include the active roadmap milestone,
the unmet Done-when criterion being attacked, and the rule for rejecting polish.
Use `mew-product-evaluator` and `ROADMAP_STATUS.md` as the source of that
decision instead of copying only the latest chat preference.

Always save the governing chain explicitly:

- active milestone
- single target criterion
- next task mapped to that criterion

If the checkpoint says "hold", "wait", or "do not spend a proof item", also
save **why** that constraint exists and what event would re-open task
selection. Do not save the hold note by itself as if it were the governing
goal.

If the current context diagnostics themselves are useful, prefer the native checkpoint command:

```bash
./mew context --save "<current intent; exact next action; validation state; blockers; stop/report trigger>" \
  --name "Long session checkpoint: <short name>" \
  --description "Recover this after context compression or interruption."
```

Use `--json` only when you need the saved memory path programmatically; the JSON output includes the full context diagnostics and can be large.

After compression or interruption, recover saved checkpoints with:

```bash
./mew context --load --json
```

## Pair With Load

After saving, a future agent should be able to use `mew-planning-reentry` and recover:

- the session charter and decision precedence
- current work
- durable decisions
- deferred work and reasons
- latest validation
- next safest action
- milestone -> criterion -> task mapping
