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

Freeze five or six candidates so one failed item does not force mid-proof
replanning. The first three completed items can close the gate if every
iteration stays green.

Primary order for the first supervised run:

1. Candidate A
2. Candidate B
3. Candidate D

Fallbacks if one primary candidate is rejected by the canary or does not
converge:

4. Candidate C
5. Candidate E

### Candidate A: brief active-work and next-move coherence

- scope fence: `src/mew/brief.py`, `tests/test_brief.py`
- target shape: visible focus/brief behavior only
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_brief.py -k "focus or brief or active_work_session" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_brief
```

### Candidate B: work-session resume or repair anchor clarity

- scope fence: `src/mew/work_session.py`, `tests/test_work_session.py`
- target shape: reviewer surface, resume, repair anchor, or same-surface audit
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_work_session.py -k "resume or same_surface or repair_anchor" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_work_session
```

### Candidate C: commands reply or approval surface clarity

- scope fence: `src/mew/commands.py`, `tests/test_work_session.py`
- target shape: visible `mew work` control or reply behavior
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_work_session.py -k "approve_all or governance or reply_file" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_work_session tests.test_commands
```

### Candidate D: commands top-level legibility surface

- scope fence: `src/mew/commands.py`, `tests/test_commands.py`
- target shape: visible top-level `status` / `brief` / `focus` / `next`
  behavior, especially JSON, quiet, or kind-filtered output
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_commands.py -k "status_brief_and_next or focus_and_daily or next_and_focus" --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_commands
```

### Candidate E: read-only signal provenance or journal surface

- scope fence: `src/mew/signals.py`, `tests/test_signals.py`
- target shape: read-only signal provenance, journaling, or CLI rendering only;
  no collectors, daemon schedule, or wake-up behavior
- drift canary / focused verifier:

```bash
uv run pytest -q tests/test_signals.py --no-testmon
```

- broader verifier:

```bash
uv run python -m unittest tests.test_signals
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

1. freeze the candidate list
2. pre-write scope fence, drift canary, focused verifier, and broader verifier
   for each candidate
3. confirm a continuous reviewer window exists for the full proof
4. prepare the iteration-doc skeletons so evidence is recorded during the run,
   not reconstructed after the fact

Only after those are fixed should the supervised 8-hour proof start.
