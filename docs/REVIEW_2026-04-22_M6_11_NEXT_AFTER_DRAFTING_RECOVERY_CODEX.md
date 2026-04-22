# M6.11 Next Slice After Drafting Recovery — Codex

## Verdict

**A — `m6_11-draft-timeout`**

## Why

- `HEAD` is now `b4c1018`, the worktree is clean, and the close-gate dogfood matrix is honestly `2 pass + 3 not_implemented` (`m6_11-compiler-replay`, `m6_11-drafting-recovery` pass; timeout/refusal/phase4-regression do not).
- The sharpest remaining missing proof is still `#401`: `ROADMAP.md:618-619` and `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:648-652,694-695` require timeout-before-draft recovery to preserve the same drafting frontier via `resume_draft_from_cached_windows`, not generic `replan`.
- Current calibration is already instrumented and already red for the active problem: `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` at `HEAD` reports dominant bundle type `work-loop-model-failure.request_timed_out` with share `0.5714285714285714`, above the `0.4` concentration ceiling. That points at timeout recovery as the next highest-value stabilization target.
- **Not B:** refusal is currently rare in the only live calibration we have (`refusal_count=0`), and the lower-level refusal classifier/mapping already has source coverage (`src/mew/patch_draft.py`, `tests/test_patch_draft.py`, `src/mew/proof_summary.py`, `tests/test_proof_summary.py`). A dogfood wrapper is useful, but it does not close the most active blocker first.
- **Not C:** the calibration/instrumentation surface already exists and is doing its job. Adding more incidence/reporting work before landing the next missing deterministic scenario widens scope without improving close-gate evidence or loop stability.

## Exact Bounded Slice

- Touch only:
  - `src/mew/work_session.py`
  - `src/mew/commands.py`
  - `src/mew/dogfood.py`
  - `tests/test_work_session.py`
  - `tests/test_dogfood.py`
  - `tests/fixtures/work_loop/recovery/401_exact_windows_timeout_before_draft/scenario.json` (new)
- Land the smallest structural recovery hook needed for honest `#401` evidence:
  - split timeout-before-draft recovery in `build_work_recovery_plan()` so an interrupted write-ready turn with a surviving `active_work_todo` emits `action="resume_draft_from_cached_windows"` instead of generic `replan`
  - preserve the same todo / exact-window frontier in the recovery item and its hint/command
  - teach follow-status suggested-recovery rendering to surface that action cleanly
- Implement `m6_11-draft-timeout` as the deterministic offline harness for that fixture:
  - same `WorkTodo` survives
  - recovery action is `resume_draft_from_cached_windows`
  - follow-status and resume agree on the recovery surface
  - no generic `replan` survives in the asserted path
- Keep out of scope:
  - `m6_11-refusal-separation`
  - incidence / batch-analysis instrumentation
  - `m6_11-phase4-regression`
  - broader prompt or runtime tuning

## Acceptance Checks

- `./.venv/bin/python -m pytest tests/test_work_session.py -q`
- `./.venv/bin/python -m pytest tests/test_dogfood.py -k m6_11`
- `./.venv/bin/python -m mew dogfood --scenario m6_11-draft-timeout`
- The `m6_11-*` subset is now honestly `3 pass + 2 not_implemented`.
- The timeout fixture proves `resume_draft_from_cached_windows`, not `replan`, for the surviving `WorkTodo`.

## Risks / Not Doing

- This is slightly wider than a pure dogfood wrapper, because `resume_draft_from_cached_windows` is still missing from the current recovery vocabulary at `HEAD`. Keep it tightly scoped to the `#401` timeout path only.
- If we do **B** first, we add a wrapper around a currently non-dominant failure bucket while the dominant timeout bucket remains unproven at the close gate.
- If we do **C** first, we spend scope on measuring a problem that is already measured instead of closing the next missing structural proof.
- If we do neither now, `ROADMAP.md:618-619` remains unmet and the most active live calibration failure still has no honest deterministic dogfood evidence.
