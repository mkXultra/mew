---
name: mew-first-implementation-loop
description: Run bounded mew roadmap/coding tasks with mew as the first implementer and Codex as reviewer. Use when implementing mew tasks after M6.7, assessing mew-first success or failure, deciding whether to repair loop substrate immediately, or preserving autonomy-credit accounting across context compression.
---

# Mew-First Implementation Loop

Use this skill for bounded mew roadmap/coding implementation unless the user
explicitly asks for direct Codex implementation or the task is governance,
milestone-close, roadmap-status, permission, safety, or agent-loop substrate
surgery.

Goal: make product progress while measuring whether mew can actually implement
the work. Do not hide failures behind supervisor rescue edits.

## Default Protocol

1. Pick one task from the active roadmap milestone:
   `milestone -> unmet/partial Done-when criterion -> bounded task`.
2. Start with mew as implementer. Codex acts as human-style reviewer/approver.
3. Require a scoped patch, proof command, and reviewer-visible rationale.
4. If mew succeeds, classify the result as `success_mew_first`.
5. If mew fails, classify the failure before fixing anything.
6. If the failure is a reproducible loop/substrate blocker, make at most one
   bounded substrate repair, then retry the same task.
7. If retry succeeds, classify as `success_after_substrate_fix`.
8. If retry fails or the failure is not a narrow substrate blocker, record it
   and either supervisor-rescue the product gap or choose another task.

## Failure Classes

- `success_mew_first`: mew produced the patch, verification passed, and Codex
  only reviewed/approved.
- `success_after_substrate_fix`: mew failed, a bounded substrate fix landed,
  then the same task succeeded mew-first.
- `product_progress_supervisor_rescue`: Codex or another reviewer implemented
  the patch. This may be valuable product progress, but it is not autonomy
  credit.
- `blocked_reproducible`: mew exposed a repeatable loop blocker worth fixing
  now.
- `blocked_deferred`: the failure is real but not the active milestone's
  highest-value blocker.
- `invalid_task_spec`: the task scope, proof, or verifier was wrong.
- `transient_model_failure`: timeout, API, quota, or model-service issue.

## Immediate Repair Rule

Repair immediately only when all are true:

- the same failure is reproducible or has clear replay/cached-window evidence;
- the repair is narrower than the task itself;
- the repair protects future mew-first work, not just the current patch;
- the active milestone still benefits from retrying the same task.

Otherwise record the failure and move on. Do not spend multiple cycles turning
one task into hidden polish.

## Accounting

For every mew-first attempt, leave enough durable evidence to recover after
context compression:

- task/session id, model, and reasoning effort
- target milestone and criterion
- result class
- patch owner: `mew`, `supervisor`, or `mixed`
- verification commands and status
- reviewer rescue edits count
- substrate blocker, if any
- next action: retry, repair, rescue, defer, or close

Roadmap/status edits, milestone close decisions, and governance changes remain
reviewer-owned unless a later milestone explicitly moves that boundary.

## Stop Conditions

Stop mew-first execution and switch to reviewer decision when:

- the patch would edit governance, roadmap status, permissions, auth, or skill
  policy;
- proof cannot be made explicit;
- the same blocker has consumed two repair/retry cycles;
- mew is about to claim autonomy credit for a supervisor-authored patch.

## Relationship To Other Skills

- Use `mew-planning-reentry` first after context compression or interruption.
- Use `mew-product-evaluator` to choose the active milestone criterion.
- Use this skill to execute the chosen coding task honestly.
- Use `mew-context-save` before long sessions or after meaningful chunks.
