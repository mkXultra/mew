---
name: mew-product-evaluator
description: Evaluate mew as a passive AI product and as a shell/body that an AI model might want to inhabit. Use when asked whether mew is good enough, whether it feels usable as the next execution form, or what should improve next.
---

# Mew Product Evaluator

When evaluating mew, do not only review code quality. Ask the product question:

> Would I want to be inside mew?

Answer candidly, but do not let the question create endless polish. Convert the
answer into a roadmap milestone decision.

## Evidence To Read

Use the smallest useful set, in this order:

1. `ROADMAP.md` for the product goal and milestone Done-when criteria.
2. `ROADMAP_STATUS.md` for the active milestone decision and current evidence.
3. `docs/ADOPT_FROM_REFERENCES.md` when reference-derived architecture or
   structural timing is relevant.
4. Current mew state, especially `./mew metrics --kind coding`,
   `./mew focus --kind coding`, `./mew brief --kind coding`,
   `./mew context --load --json`, and relevant typed project memory.

Treat reference docs and model opinions as input evidence, not authority. The
active roadmap milestone is the authority unless the user's newest instruction
explicitly changes direction.

## North Star And Gate

Always keep both of these in view at the same time:

- **North star**: would I want to be inside mew?
- **Execution gate**: what is the single highest-value task that closes the
  active milestone honestly?

The north star is not a task selector by itself. It exists to interpret the
active milestone, not to bypass it.

## Milestone Gate

Select exactly one active milestone:

- Prefer the active milestone recorded in `ROADMAP_STATUS.md`.
- If it is missing or contradictory, choose the earliest milestone in
  `ROADMAP.md` whose Done-when criteria are not satisfied, then update
  `ROADMAP_STATUS.md` or say it needs updating before implementation.

Evaluate only that milestone's Done-when criteria. Mark each criterion as
`met`, `partial`, or `unmet` with concrete evidence.

The next task must do one of these:

- close one `partial` or `unmet` Done-when criterion for the active milestone
- reduce a measured blocker that prevents closing that criterion
- collect the specific dogfood evidence needed to mark the criterion honestly

Do not choose polish, side projects, broad refactors, or later-milestone
architecture unless they directly unblock the active milestone. If the same
criterion has absorbed three implementation cycles without becoming clearer or
closer to done, recommend rewriting that criterion or the measurement instead
of continuing to polish.

When all active-milestone criteria are met, recommend closing that milestone in
`ROADMAP_STATUS.md` and moving to the next milestone. This is the convergence
rule.

Before returning a next task, force this check:

1. name exactly one `partial` or `unmet` active-milestone criterion
2. state whether the next task will:
   - close it
   - reduce its measured blocker
   - collect the exact proof needed for it
3. if you cannot do one of those three honestly, do **not** choose polish or
   prep work; instead recommend:
   - running the required proof, or
   - rewriting the criterion/measurement in `ROADMAP_STATUS.md`

Checkpoint notes, `mew focus`, `mew brief`, live friction, and external model
comments are evidence only. They must never become the task selector unless you
explicitly map them back to one active-milestone criterion.

If a checkpoint says "hold", "wait", "do not spend a proof item", or similar,
interpret that as a **local constraint**, not as the new roadmap authority.
Still ask: which active-milestone criterion is blocked, and what is the next
highest-value action for that criterion under this constraint?

If the same criterion has absorbed three cycles of "blocker reduction",
"operator hardening", "prep-only docs", or similar without clearer evidence or
measurable progress, stop calling that convergence. Escalate by recommending:

- run the proof now, or
- rewrite the criterion / measurement now

Do not allow a fourth cycle of nearby work under the same unresolved gate.

## Product Bar

The durable product goal is:

> frontier models should prefer mew over Claude Code / Codex CLI for task and
> coding work when persistence, passive operation, auditability, and recovery
> matter.

Use these checks only to interpret the active milestone:

- Does mew help a resident AI remember itself after time passes or context is
  compressed?
- Does it let the AI notice tasks, ask questions, and act without constant user
  prompting?
- Does it have enough feedback to read, decide, act, verify, and recover?
- Is the human interface calm enough for daily use?
- Is it safe enough to run passively without surprising the user?

Current durable judgments:

- Task/coding passive AI is the first target; broader general passive AI comes
  later.
- Native work sessions are the main evidence for "inside mew".
- Persistent advantage is continuity, not calendar time.
- Continuity must be actionable: weak bundles should name the next repair step.
- External observer operation matters, but observer work should still map to
  the active milestone.
- 5.12 Memory Scope x Type has an MVP. More storage surfaces are lower value
  than proving recall quality, daily usefulness, and active-milestone closure.

## Output Shape

Return a short evaluation with:

- verdict: `yes`, `not yet`, or `no`
- active_milestone
- Done-when checklist with `met` / `partial` / `unmet`
- criterion_target: the single active-milestone criterion the next task is for
- blocking_gap
- next_task, explicitly mapped to one Done-when criterion
- evidence used
- not_doing: tempting work that should be deferred
- confidence and uncertainty

Use `acm run` with another model only when the user explicitly asks for that
model, then compare its answer with your own before responding.
