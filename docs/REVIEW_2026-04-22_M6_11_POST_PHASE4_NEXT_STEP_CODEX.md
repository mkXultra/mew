# M6.11 Post-Phase4 Next Step — Codex

## Verdict

**Choose (A): start close-gate evidence collection, beginning with dogfood scenario registration.**

Do **not** spend another bounded slice on `latest_model_failure` semantics first.

## Reasoning

The current operator surface is already good enough for the bounded Phase 4 intent:

- `./mew work 402 --follow-status --json` now reports:
  - `resume_source=session_overlay`
  - `phase=blocked_on_patch`
  - populated `active_work_todo`
  - `blocker_code=insufficient_cached_context`
  - `next_recovery_action=refresh_cached_window`
  - populated `suggested_recovery`
- That means the live blocked frontier and its recovery path are now authoritative on the follow surface, even though `latest_model_failure` still points at the older timeout.

I do **not** think the stale timeout `latest_model_failure` is materially obscuring blocker-backed recovery enough to justify option (B):

- the current blocked state is explicit and higher-signal than the historical failure
- the recovery command is already concrete
- the bounded Phase 4 operator goal was parity on blocker/recovery state, and the live `#402` output now meets that goal

The blocking problem is now the close-gate evidence itself:

- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` is still red
- current calibration is `total_bundles=14`
- `dominant_bundle_type=work-loop-model-failure.request_timed_out`
- `dominant_bundle_share=0.5714285714285714`
- `failure_mode_concentration_ok=false`

That is not an operator-surface problem anymore. Another follow-status slice would polish interpretation while leaving the actual close gate blocked on evidence and incidence.

`ROADMAP_STATUS.md` already points the same way: move from Phase 4 parity into close-gate evidence collection unless stale `latest_model_failure` still prevents operators from using the blocker-backed recovery surface. The current `#402` output shows that it no longer does.

## Exact Bounded Next Step

**Register the M6.11 close-gate dogfood scenarios, with `m6_11-drafting-recovery` as the first mandatory executable scenario in the slice.**

Why this is the right bounded A-slice:

- it is the smallest step that unlocks honest close-gate evidence collection
- the proposal already names the required `m6_11-*` scenario family
- it converts the now-authoritative blocker/recovery surface into repeatable proof instead of one-off manual inspection
- it avoids drifting into more operator-surface polish before the evidence gate is exercised

Recommended scope inside this slice:

1. Add the `m6_11-*` scenario names to the dogfood registry.
2. Implement at least `m6_11-drafting-recovery` end-to-end as a deterministic scenario.
3. Use that scenario to assert the same blocker code and `next_recovery_action` across resume and follow-status for the same `WorkTodo`.
4. Defer any new `latest_model_failure` reinterpretation unless the scenario proves the current surface is still misleading.

## Files To Touch If Code Is Recommended

- `src/mew/dogfood.py`
  - `DOGFOOD_SCENARIOS`
  - `run_dogfood_scenario(...)`
  - new `run_m6_11_*_scenario(...)` helpers, starting with `m6_11-drafting-recovery`
- `tests/test_dogfood.py`
  - CLI scenario choice coverage
  - scenario execution/report assertions for `m6_11-drafting-recovery`
- Optional close-gate artifact stub only if you want to start recording evidence immediately:
  - `docs/M6_11_CLOSE_GATE_2026-04-22.md` or the project’s chosen M6.11 close artifact path

No further `src/mew/commands.py` changes are recommended for the next slice.

## Focused Validation

- `uv run pytest -q tests/test_dogfood.py -k m6_11`
- `./mew dogfood --scenario m6_11-drafting-recovery --json`
- Scenario pass criteria:
  - resume and follow-status surface the same `blocker_code`
  - resume and follow-status surface the same canonical `next_recovery_action`
  - follow-status remains `resume_source=session_overlay` when the live session is richer
- After registration lands, start the bounded incidence runbook:
  - collect the planned controlled `#399/#401` slices
  - rerun `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json`
  - record whether `request_timed_out` concentration and combined `#399/#401` incidence are actually dropping

## Why Not (B)

One more operator-surface slice would be polish-first, not gate-first.

- The bounded Phase 4 parity goal is already met on live `#402`.
- The remaining milestone blocker is red calibration / missing close-gate evidence.
- The next highest-value truth is whether the stabilized loop is reducing timeout concentration and `#399/#401` incidence, not whether the historical failure field can be made prettier.
