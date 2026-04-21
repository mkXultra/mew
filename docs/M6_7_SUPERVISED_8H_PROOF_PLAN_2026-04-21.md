# M6.7 Supervised 8-Hour Proof Plan 2026-04-21

Status: planned.

This document fixes the remaining M6.7 gate after the clean short-loop proof
recorded in `docs/M6_7_SIXTH_SUPERVISED_ITERATION_2026-04-21.md`.

## Remaining Gate

M6.7 is not done until a supervised 8-hour run completes with:

1. at least three real roadmap items
2. reviewer decisions recorded on each iteration
3. zero proof-or-revert failures
4. a green drift canary throughout

## Session Rules

- mew is the implementer
- Codex is the reviewer
- one bounded roadmap item per iteration
- no chained autonomous task selection inside a single iteration
- no auto-merge
- roadmap/milestone status changes remain reviewer-owned

## Item Selection Rules

Choose only items that satisfy all of these:

- bounded, single-surface or paired source/test scope
- obvious scope fence
- focused verifier already known and cheap to repeat
- visible product behavior in `mew focus`, `mew brief`, `mew work`, or another
  real CLI surface
- worth shipping even outside the proof

Reject items with any of these traits:

- touches `ROADMAP.md`, `ROADMAP_STATUS.md`, `docs/`, or milestone-close wording
- cross-module refactor or rename
- requires a full-suite verifier as the focused check
- daemon/scheduler/collector work that is blocked behind M6.7 itself
- speculative coding-loop polish or any task likely to require reviewer rescue

## Candidate Queue

The original A/B/C/D/E queue was exercised and exhausted mostly as honest
no-change outcomes on already-green surfaces. This refreshed queue replaces it
with open product gaps drawn from the current M6.7 evidence trail.

Freeze five candidates so one failed item does not force mid-proof replanning.
The first three completed items can close the gate if every iteration stays
green.

Primary order for the next supervised run:

1. Candidate N-A
2. Candidate N-B
3. Candidate N-C

Fallbacks if one primary candidate is rejected by the canary or does not
converge:

4. Candidate N-D
5. Candidate N-E

## Current Outcomes

- Candidate N-A: soft-stopped. After the focused verifier shape was repaired,
  the bounded run stayed inside `src/mew/proof_summary.py` +
  `tests/test_proof_summary.py`, but two fresh attempts stalled before a
  reviewable paired dry-run diff surfaced. Carry this as non-converging proof
  evidence, not closure credit.
- Candidate N-B: soft-stopped. The initial task framing drifted toward
  focus-only `active_work_session_items()` work, while the real target is
  `brief` / `next` / JSON output. Keep the task notes as repair guidance, but
  do not count it as M6.7 proof credit.
- Candidate N-C: reviewer no-change. Existing `active_work_session_items()`
  gates plus the current `tests/test_brief.py` blocked/done coverage already
  satisfy the target, so no product patch landed.
- Candidate N-E: direct supervisor product patch landed in
  `src/mew/toolbox.py` + `tests/test_toolbox.py`, adding additive structured
  timeout diagnostics and one focused regression. This is product progress, not
  supervised-proof credit, because mew session `#372` stalled twice during edit
  planning.

### Candidate N-A: proof-summary supervised-iteration validator

- scope fence: `src/mew/proof_summary.py`, `tests/test_proof_summary.py`
- target shape: `mew proof-summary --supervised-iteration <doc>` validates
  that an M6.7 iteration doc includes drift canary, focused verifier, broader
  verifier, scope fence, reviewer decision, same-surface audit, and
  no-rescue-edit evidence; `--strict` fails on any missing section
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_proof_summary.py -k "supervised or strict" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_proof_summary
```

### Candidate N-B: brief/next governance-blocked approval context

- scope fence: `src/mew/brief.py`, `tests/test_brief.py`
- target shape: when the active work session carries
  `approve_all_blocked_reason`, `mew brief` and `mew next` surface the blocked
  reason plus `blocked_approve_all_hint`; JSON output exposes the same fields
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_brief.py -k "blocked_approve_all or governance_blocked or next_move_blocked" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_brief
```

### Candidate N-C: active-work non-actionable state parity

- scope fence: `src/mew/brief.py`, `tests/test_brief.py`
- target shape: `active_work_session_items()` excludes all non-actionable
  session states, not only stale blocked ones, so `mew focus --kind coding`
  does not suppress the next useful move for aborted, rejected, or stale
  finished-without-proof work
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_brief.py -k "active_work_session or focus_kind_coding" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_brief
```

### Candidate N-D: reply-file per-tool governance approval audit trail

- scope fence: `src/mew/commands.py`, `tests/test_work_session.py`
- target shape: governance/policy dry-run edits approved via
  `mew work --reply-file` per-tool approvals record reviewer id, reason, and
  governance target in the effect journal and surface in audit output; missing
  reviewer identity is rejected before execution
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_work_session.py -k "reply_file and (governance or per_tool_approve)" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_work_session tests.test_commands
```

### Candidate N-E: live verifier timeout diagnostic surface

- scope fence: `src/mew/toolbox.py`, `tests/test_toolbox.py`
- target shape: on verifier timeout, the streaming helper records structured
  timeout diagnostics (`timed_out`, kill status, stdout/stderr tail) so the
  work session surfaces an actionable diagnostic instead of an opaque timeout
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_toolbox.py -k "timeout or streaming_kill" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_toolbox
```

## Per-Iteration Runbook

Every iteration must follow the same shape:

1. run the drift canary first
2. bound the scope explicitly
3. anchor exact source/test windows
4. require a paired dry-run diff
5. record a reviewer decision
6. run the focused verifier after approval
7. run the broader module verifier before finish
8. perform same-surface audit
9. record the result in a checked-in `docs/M6_7_...` artifact

## Stop Conditions

Hard stop the whole 8-hour proof immediately if any of these happen:

- drift canary fails
- proof-or-revert failure
- out-of-scope edit
- reviewer rescue edit
- missing reviewer decision for a landed change

Soft stop an iteration and switch to a different candidate if:

- the item is not converging inside about two hours
- the bounded surface is wrong
- the focused verifier turns out to be unstable

## Near-Term Plan

The next three hours should be used for preparation, not for claiming the 8-hour
proof itself.

Before iteration 1 starts:

1. freeze the refreshed candidate list
2. pre-write scope fence, drift canary, focused verifier, and broader verifier
   for each candidate
3. confirm a continuous reviewer window exists for the full proof
4. prepare the iteration-doc skeletons so evidence is recorded during the run,
   not reconstructed after the fact

Only after those are fixed should the supervised 8-hour proof start.
