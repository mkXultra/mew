# M6.11 Next Slice After Refusal Separation — Codex

Context: `HEAD` is `60832b9` (`Land M6.11 refusal separation slice`). The active milestone is still **M6.11 Loop Stabilization**, and `ROADMAP_STATUS.md` says the only remaining explicit `not_implemented` close-gate scenario is `m6_11-phase4-regression`.

## Recommendation

Implement exactly one narrow slice next: **`m6_11-phase4-regression` as a deterministic dogfood regression-budget scenario**.

This should be a harness/proof slice, not a product-behavior slice. Do not reopen `work_loop`, `work_session`, timeout recovery, or refusal handling. Those semantics are already covered by the four landed `m6_11-*` scenarios. The missing proof is now the cross-cutting Phase 4 non-functional check.

## What `m6_11-phase4-regression` Should Prove

`m6_11-phase4-regression` should prove that enabling the M6.11 Phase 4 drafting-recovery surfaces does **not** introduce unacceptable wall-time regression on the three frozen M6.6 comparator task shapes:

- M6.6-A: behavior-preserving refactor
- M6.6-B: bug fix with regression test
- M6.6-C: small feature with paired source/test changes

Per the adopted close-gate proposal, the scenario should:

- load a pinned deterministic fixture describing those three comparator shapes and their measured M6.11 wall times
- compute the median comparator wall time
- compare that median against the pinned budget ceiling `B0.iter_wall × 1.10`
- fail if the median exceeds the budget, or if any comparator case is missing the timing data needed to make the claim honestly

That is the remaining bounded proof because it answers a different question from the semantic recovery scenarios: not "did we classify/recover the blocker correctly?", but "did the stabilized drafting path stay within the allowed regression envelope on representative coding work?"

## How It Differs From The Other `m6_11-*` Scenarios

- `m6_11-drafting-recovery` proves **surface parity**: the same blocked `WorkTodo` yields the same `blocker_code`, `next_recovery_action`, and active todo payload across direct resume and `work --follow-status`.
- `m6_11-draft-timeout` proves **`#401` recovery correctness**: timeout-before-draft preserves the drafting frontier and offers `resume_draft_from_cached_windows` instead of generic `replan`.
- `m6_11-refusal-separation` proves **refusal classification correctness**: refusal-shaped output becomes `model_returned_refusal` with `inspect_refusal`, rather than collapsing into generic non-schema or transport failure.
- `m6_11-phase4-regression` should prove **budget discipline across representative task shapes**: the landed Phase 4 recovery/follow-status machinery did not make the loop too slow.

So `m6_11-phase4-regression` is the only remaining **NFR comparator** proof. It is not another blocker-taxonomy or recovery-contract slice.

## Exact Files And Tests That Should Change

1. `src/mew/dogfood.py`

Replace the current `run_m6_11_phase4_regression_scenario(...)` stub with a real deterministic implementation.

Exact scope inside that file:

- add one fixture root constant for a new phase-4 regression fixture directory
- add one small helper to load the pinned comparator fixture and compute median wall time / budget pass-fail
- implement `run_m6_11_phase4_regression_scenario(...)` so it:
  - reads the pinned `B0.iter_wall`
  - reads the three pinned M6.6 comparator cases
  - emits `_scenario_check(...)` assertions for:
    - exactly 3 comparator cases present
    - comparator names/shapes are the frozen M6.6 A/B/C set
    - every case has a wall-time measurement
    - median wall time is `<= B0.iter_wall × 1.10`
  - records artifacts such as `b0_iter_wall_seconds`, `budget_wall_seconds`, `median_wall_seconds`, and the per-case timings

No `src/mew/work_loop.py`, `src/mew/work_session.py`, or `src/mew/commands.py` change should be part of this slice.

2. `tests/test_dogfood.py`

Update the dogfood tests so Phase 4 regression is treated as implemented evidence instead of an honest stub.

Exact test changes:

- remove `m6_11-phase4-regression` from `test_run_dogfood_m6_11_not_implemented_scenarios`
- add `test_run_dogfood_m6_11_phase4_regression_scenario`
  - assert overall `pass`
  - assert scenario name is `m6_11-phase4-regression`
  - assert the artifact payload includes the pinned `B0` value, computed budget, computed median, and all three comparator cases
  - assert all checks pass
- update `test_run_dogfood_m6_11_all_subset_aggregate_reflects_not_implemented`
  - rename it to reflect full pass coverage
  - assert all five `m6_11-*` scenarios now pass
  - assert the aggregate `m6_11-*` subset is now `pass`, not `fail`
  - assert the formatted report includes `m6_11-phase4-regression: pass`

3. New fixture file

Add one pinned deterministic fixture file, for example:

- `tests/fixtures/work_loop/phase4_regression/m6_6_comparator_budget/scenario.json`

That fixture should contain only the data needed for the proof:

- pinned `B0.iter_wall`
- the three frozen comparator case ids / shape labels (`M6.6-A/B/C`)
- one pinned wall-time measurement per case
- optional source references back to the M6.6 evidence doc or trace ids for auditability

This keeps the slice bounded. It avoids inventing a live benchmark runner, avoids new runtime behavior, and still makes `proof-summary --strict` honest.

## Why This Is The Right Next Slice

- `ROADMAP_STATUS.md` already says `m6_11-phase4-regression` is the only remaining explicit `not_implemented` dogfood scenario.
- `ROADMAP.md` requires all five `m6_11-*` scenarios to pass for M6.11 close.
- The other four scenarios already cover semantic correctness for compiler replay, timeout recovery, refusal classification, and resume/follow-status parity.
- The remaining gap is therefore the single bounded regression-budget proof, not another behavior change.

This is the smallest slice that moves the close-gate matrix from `4 pass + 1 not_implemented` to `5 pass`, without widening into a refactor or reopening already-landed M6.11 semantics.

Recommended next task title: `Implement m6_11-phase4-regression comparator budget dogfood scenario`
