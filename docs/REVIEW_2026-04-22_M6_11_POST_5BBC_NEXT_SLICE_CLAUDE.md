# M6.11 Post-5bbc994 — Next Bounded Slice Recommendation (Claude)

Scope: pick one bounded M6.11 Phase 0-4 slice to land after
`5bbc994 "Force low reasoning in M6.11 tiny draft lane"` and the
fresh `#402` rerun (session 392, turn 1826). Stay inside Phase 0-4;
do not enter M6.9 or post-M6.11 work.

## Current facts (2026-04-22, turn 1826)

From `.mew/replays/work-loop/2026-04-22/session-392/todo-no-todo-392/turn-1826/attempt-1/report.json`:

- **Tiny lane is now fast and authoritative:**
  - `tiny_write_ready_draft_elapsed_seconds = 11.579`
  - `tiny_write_ready_draft_timeout_budget_utilization = 0.386`
  - `tiny_write_ready_draft_reasoning_effort = "low"` (auto-override)
  - `tiny_write_ready_draft_prompt_chars = 17030`
  - `tiny_write_ready_draft_prompt_contract_version = "v3"`
  - `tiny_write_ready_draft_compiler_artifact_kind = "patch_blocker"`
  - `patch_draft_compiler_ran = true`
- **But the lane returns `fallback`, not `blocker`:**
  - `tiny_write_ready_draft_outcome = "fallback"`
  - `tiny_write_ready_draft_fallback_reason = "compiler_unpaired_source_edit_blocked"`
  - `tiny_write_ready_draft_exit_stage = "compiler_fallback"`
- **And the overall turn still fails as a 90 s generic-think timeout:**
  - `failure.code = "request_timed_out"`, `failure.kind = "timeout"`
  - `model_metrics.think.timeout_seconds = 90.0`
  - `reasoning_effort = "high"` (auto-policy matched `roadmap`,
    `work_type = "high_risk"`)

So the tiny lane did its job in ~12 s and produced an authoritative,
deterministic blocker. The 30 s budget burn is gone. What burns the
budget now is the **subsequent** generic THINK call that runs because
the tiny lane reported `fallback` instead of `blocker`.

## Recommendation

**Promote a compiler-derived `patch_blocker` in the tiny lane from
`status="fallback"` to `status="blocker"`.** When
`_attempt_write_ready_tiny_draft_turn` finds that the compiler validated
the model's `patch_proposal` and produced
`validator_result.kind == "patch_blocker"` with a stable code (anything
except `model_returned_non_schema`), return the same `wait`-with-reason
shape the proposal-side `patch_blocker` branch already returns at
`src/mew/work_loop.py:1665-1684`, instead of falling through to the
caller's 90 s generic-think path at `src/mew/work_loop.py:2785-2796`.

This is the smallest M6.11 Phase 3 slice that closes the loop on the
compiler's authority and stops burning a 90 s think on a surface the
compiler has already declared impossible.

## Why this slice now

The current failure shape is a **two-stage** loss, not a single timeout:

1. **Stage 1 (tiny lane, 11.58 s):** The model returns
   `kind="patch_proposal"` for `src/mew/cli.py` (the third actionable
   surface). The compiler at `src/mew/patch_draft.py:395-405` runs the
   pairing check, finds no `tests/test_cli.py` paired edit, and emits
   `build_patch_blocker(..., "unpaired_source_edit_blocked", ...)`. The
   tiny lane records this at `src/mew/work_loop.py:1686-1699` as
   `status="fallback"` because the proposal_kind was `patch_proposal`
   (not `patch_blocker`) — the lane's existing logic only treats a
   *model-emitted* `patch_blocker` as authoritative.

2. **Stage 2 (generic think, 90 s timeout):** Caller hits
   `if tiny_result.get("status") != "fallback":` at
   `src/mew/work_loop.py:2755`, sees `"fallback"`, skips the early
   return, and runs `call_model_json_with_retries(..., think_timeout)`
   at `:2787-2796` with `think_timeout = max(timeout, 90.0)` from
   `:2640-2644`. This call asks the **same** model the **same**
   question against the **same** impossible surface (cli.py without
   paired test) at `reasoning_effort="high"` — and predictably times
   out at 90 s.

The compiler's blocker is **deterministic**: `convention_test_path_for_mew_source`
is a pure file-path check (`patch_draft.py:399`); no LLM judgment is
involved. Asking the heavyweight think to reconsider it is wasted
budget at best and a guaranteed timeout at worst.

Three independent signals argue this is the right slice now:

- **The tiny lane works.** `5bbc994` already cut tiny elapsed by ~60 %
  (30 s → ~12 s) and the compiler now runs to completion on every
  tiny-lane attempt. There is no further tiny-lane prompt or reasoning
  lever to pull before the *consumer* of its output is fixed.
- **The compiler is authoritative for this code.** The
  `unpaired_source_edit_blocked` recovery action
  (`add_paired_test_edit`, `patch_draft.py:19`) is fully specified
  offline. There is no model question left to ask.
- **The fix is a two-line semantic flip plus tests.** Same
  return-shape as the existing `proposal_kind == "patch_blocker"`
  branch at `:1665-1684`; reuses `_stable_write_ready_tiny_draft_blocker_reason`
  at `:712-714`. No new helper, no new constant, no schema change.

## Alternatives considered

| Alternative | Why not now |
| --- | --- |
| Pre-model offline preclassification (`POST_C0E_NEXT_SLICE_CODEX`) — short-circuit before the tiny model call by detecting unpaired surfaces and skipping the call entirely | Duplicates the pairing logic at `patch_draft.py:395-405` in a second location. The tiny lane already produces the right answer in ~12 s; the next slice should use that answer, not re-derive it. Worth pursuing as a follow-up *only if* this slice lands and the residual 12 s tiny call still dominates. |
| Lower the 90 s generic-think timeout (`WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS`, `work_loop.py:63`) | Doesn't address root cause; would just move the timeout earlier and turn `compiler_unpaired_source_edit_blocked` into `model_error/request_timed_out_at_45s` instead of `_at_90s`. The generic think shouldn't run at all in this case. |
| Further tiny-prompt shrink (cap `cached_window_texts[i].text`) | The dominant time cost in turn 1826 is no longer the tiny lane (12 s is fine); it's the 90 s generic-think that follows. Shrinking the tiny prompt cannot move the post-tiny think. Tagged as the *next* slice in `POST_C0E_NEXT_SLICE_CLAUDE.md` only if low reasoning didn't bring elapsed below ~10 s — which it has. |
| Force `reasoning_effort="low"` on the generic-think path too | Would shrink the timeout-bound but on a *write-ready* surface where the model is being asked for a multi-file batch. The tiny lane is the correct place for `low` (translation task); the generic think is correctly `high` when it runs. The fix is to not run it on impossible surfaces, not to neuter it everywhere. |
| Phase 4 drafting-specific recovery vocabulary | This *is* the recovery surface — emitting a `wait` with a stable blocker reason is exactly what lets the next turn's `build_work_recovery_plan` map `unpaired_source_edit_blocked` → `add_paired_test_edit`. But Phase 4 work belongs in `build_work_recovery_plan`, not in the tiny lane. This slice unblocks Phase 4 by making sure the blocker actually surfaces. |
| Raise the generic-think timeout | Calibration-gate-relevant constant change in the wrong direction. Even infinite budget would not change a deterministic compiler blocker into an actionable patch. |
| Skip M6.11 close-gate calibration recheck | Still required after this slice lands per `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` §3.3, but the recheck is post-slice operational work, not a code slice. |

## Concrete scope

Files: **`src/mew/work_loop.py`** and **`tests/test_work_session.py`**
only. Phase: stays inside M6.11 Phase 3.

### Code change

In `_attempt_write_ready_tiny_draft_turn`, modify the
`compiler_kind != "patch_draft"` branch at
`src/mew/work_loop.py:1686-1699` so that a compiler-emitted
`patch_blocker` with a stable code is treated as a blocker (not a
fallback), mirroring the existing proposal-side branch at `:1665-1684`:

```python
compiler_kind = str(validator_result.get("kind") or "").strip()
if compiler_kind != "patch_draft":
    code = str(validator_result.get("code") or "").strip()
    if compiler_kind == "patch_blocker" and code and code != "model_returned_non_schema":
        action = {
            "type": "wait",
            "reason": _stable_write_ready_tiny_draft_blocker_reason(validator_result),
        }
        action_plan = {
            "summary": (
                decision_plan.get("summary")
                or validator_result.get("detail")
                or action["reason"]
            ),
            "action": action,
            "act_mode": "tiny_write_ready_draft",
        }
        metrics["tiny_write_ready_draft_outcome"] = "blocker"
        metrics["tiny_write_ready_draft_fallback_reason"] = ""
        return {
            "status": "blocker",
            "decision_plan": decision_plan,
            "action_plan": action_plan,
            "action": action,
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("compiler_blocker"),
            "compiler_observed": compiler_observed,
        }
    metrics["tiny_write_ready_draft_outcome"] = "fallback"
    metrics["tiny_write_ready_draft_fallback_reason"] = (
        "invalid_shape" if code == "model_returned_non_schema" else f"compiler_{code or 'unusable_output'}"
    )
    metrics["tiny_write_ready_draft_exit_stage"] = "compiler_fallback"
    return {
        "status": "fallback",
        "metrics": metrics,
        "elapsed_seconds": _finalize_tiny_draft_metrics("compiler_fallback"),
        "compiler_observed": compiler_observed,
    }
```

Notes:

- **New `exit_stage` value `"compiler_blocker"`** is introduced. This
  preserves the existing `"compiler_fallback"` value for genuine
  compiler-rejection-without-stable-code cases (model_returned_non_schema,
  empty code) so calibration can still see the distinction.
- **No change to the caller** at `src/mew/work_loop.py:2755-2782`. The
  existing `if tiny_result.get("status") != "fallback":` branch already
  handles `status="blocker"` correctly: it sets `model_metrics["think"]`
  and `model_metrics["act"]` for the tiny call, returns the wait
  action, and the caller's generic THINK at `:2785-2796` is never
  reached.
- **`_stable_write_ready_tiny_draft_blocker_reason` reuse** at `:712-714`
  guarantees the wait reason is byte-identical to the existing
  proposal-side blocker path: `"write-ready tiny draft blocker: <code>"`.
- **`model_returned_non_schema` exclusion** mirrors the existing
  proposal-side branch at `:1656`, so the slice does not promote
  shape-rejection failures to blockers (those still need the regular
  think to attempt recovery).

### Test changes

Add to `tests/test_work_session.py`, in the same area as existing
`tiny_write_ready_draft_*` tests (after `:7402`,
`test_tiny_write_ready_draft_lane_returns_wait_for_patch_blocker`):

1. **`test_tiny_write_ready_draft_lane_promotes_compiler_patch_blocker_to_wait`**
   — stub the model to return `kind="patch_proposal"` with hunks
   editing `src/mew/cli.py` *without* a paired `tests/test_cli.py`
   edit. Drive `_attempt_write_ready_tiny_draft_turn` end-to-end.
   Assert:
   - `result["status"] == "blocker"`
   - `result["action"] == {"type": "wait", "reason": "write-ready tiny draft blocker: unpaired_source_edit_blocked"}`
   - `metrics["tiny_write_ready_draft_outcome"] == "blocker"`
   - `metrics["tiny_write_ready_draft_fallback_reason"] == ""`
   - `metrics["tiny_write_ready_draft_exit_stage"] == "compiler_blocker"`
   - `metrics["tiny_write_ready_draft_compiler_artifact_kind"] == "patch_blocker"`

2. **`test_tiny_write_ready_draft_lane_keeps_compiler_fallback_for_model_returned_non_schema`**
   — stub the model to return `kind="patch_proposal"` with malformed
   hunks that cause the compiler to emit
   `code="model_returned_non_schema"`. Assert the existing fallback
   shape is preserved:
   - `result["status"] == "fallback"`
   - `metrics["tiny_write_ready_draft_outcome"] == "fallback"`
   - `metrics["tiny_write_ready_draft_fallback_reason"] == "invalid_shape"`
   - `metrics["tiny_write_ready_draft_exit_stage"] == "compiler_fallback"`

3. **`test_plan_work_model_turn_skips_generic_think_when_tiny_lane_returns_compiler_blocker`**
   — integration test at the `plan_work_model_turn` level (the caller).
   Use the same setup as
   `test_tiny_write_ready_draft_lane_promotes_compiler_patch_blocker_to_wait`,
   but additionally stub `call_model_json_with_retries` to raise on
   any *second* invocation. Assert:
   - `planned["action"]["type"] == "wait"`
   - The generic-think model call is **never** invoked (the second-call
     stub never fires)
   - `planned["model_metrics"]["think"]["elapsed_seconds"]` is the
     tiny lane elapsed, not 0 + 90 s
   - `planned["model_metrics"]["act"]["mode"] == "tiny_write_ready_draft"`

Three tests, one per surface: helper-level promotion, helper-level
non-promotion preservation, caller-level early-return integration.

## Out of scope

- Any change to `WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS`
  (still 90 s).
- Any change to `WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS`
  (still 30 s).
- Any change to `WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT` (still
  `"low"`).
- Any change to `select_work_reasoning_policy` or the generic-think
  reasoning effort.
- Any change to the tiny prompt body or context builder
  (`build_write_ready_tiny_draft_model_context`,
  `build_work_write_ready_tiny_draft_prompt`).
- Any change to `build_patch_blocker`, the compiler, or the pairing
  check at `patch_draft.py:395-405`.
- Any change to `build_work_recovery_plan` to map the blocker code to
  `add_paired_test_edit` (Phase 4 scope).
- Pre-model offline preclassification (separate slice; defer until we
  measure whether even 12 s of tiny lane is too much).
- Roadmap status copy update (acceptable to add a one-line addendum
  under `ROADMAP_STATUS.md` noting the post-tiny-draft follow-up now
  honors compiler blockers without a generic-think retry).
- Any prompt contract version bump. The tiny prompt text and shape
  are unchanged; this is a control-flow change, not a contract change.
  Keep `WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION = "v3"`.

## Acceptance criteria

1. On a `#402`-shape rerun where the model returns
   `kind="patch_proposal"` editing `src/mew/cli.py` without a paired
   test edit:
   - The turn completes in ≤ 30 s wall time (no 90 s generic-think).
   - `failure` is absent OR is the next-turn recovery shape (not
     `model_error/request_timed_out`).
   - `model_metrics.tiny_write_ready_draft_outcome == "blocker"`.
   - `model_metrics.tiny_write_ready_draft_exit_stage == "compiler_blocker"`.
   - `model_metrics.think.elapsed_seconds ≈ tiny_write_ready_draft_elapsed_seconds`
     (no separately accumulated generic-think elapsed).
   - The planned `action.type == "wait"` and `action.reason` contains
     the literal `"write-ready tiny draft blocker: unpaired_source_edit_blocked"`.
2. On a write-ready turn where the compiler returns
   `kind="patch_blocker"` with `code="model_returned_non_schema"`:
   - Behavior is byte-identical to the pre-slice state. The lane
     still falls back to the generic-think (which is the correct
     escalation for a shape-rejection).
   - `model_metrics.tiny_write_ready_draft_outcome == "fallback"`.
   - `model_metrics.tiny_write_ready_draft_exit_stage == "compiler_fallback"`.
3. On every existing tiny-lane test path
   (`test_tiny_write_ready_draft_*` at `tests/test_work_session.py:6245`,
   `:6333`, `:7140`, `:7161`, `:7218`, `:7301`, `:7345`, `:7402`):
   - All assertions pass unchanged. The slice does not modify any
     existing exit_stage value (`unknown_kind`, `non_dict_response`,
     `model_exception`, `succeeded`, `blocker_accepted`,
     `compiler_fallback`, `preview_*`, `translated_preview_unusable`).
4. The full `tests/test_work_session.py` suite passes with no new
   skips, no new flakes, no fixture changes outside the three new
   tests.
5. Calibration replay bundles collected after this slice:
   - Carry `tiny_write_ready_draft_exit_stage == "compiler_blocker"`
     for the `unpaired_source_edit_blocked` cohort previously bucketed
     as `compiler_fallback`.
   - The `failure_mode_concentration` calculation in
     `mew proof-summary --m6_11-phase2-calibration` re-buckets:
     `work-loop-model-failure.request_timed_out` share for `#402`-shape
     bundles drops materially (the dominant failure mode shifts from
     timeout to compiler_blocker, which is a *recovered* shape, not a
     failure).

## Risks

- **Regression risk: low.** The change only fires when
  `compiler_kind == "patch_blocker"` AND `code != "model_returned_non_schema"`
  AND code is non-empty — the same gate the proposal-side branch at
  `:1656` already uses for explicit `patch_blocker` proposals. There
  is no new schema, no new prompt, no new constant.
- **Recovery wiring not in scope.** The wait reason
  `"write-ready tiny draft blocker: unpaired_source_edit_blocked"` is
  the same shape the explicit-blocker branch already produces, but
  `build_work_recovery_plan` does not yet map this reason to a
  draft-specific recovery — it falls through to generic replan. That
  is acceptable for this slice (one-turn loss instead of one-turn +
  90 s loss) but should be the next Phase 4 slice once this lands.
- **Calibration cohort mix.** Pre-slice bundles for `#402` carry
  `exit_stage="compiler_fallback"` AND `failure.code="request_timed_out"`
  on the same turn; post-slice bundles will carry
  `exit_stage="compiler_blocker"` AND no failure. The
  `failure_mode_concentration` metric re-shapes mechanically because
  `exit_stage` is recorded distinctly. Document in the slice commit
  that pre/post comparison should bucket by `exit_stage`, not by
  `failure.code`, to avoid confounding the gate.
- **Loop-stranding hazard.** If `build_work_recovery_plan` does not
  recognize the wait reason and emits a generic replan that re-feeds
  the same plan-item to the next turn, we get a `wait` → `replan` →
  `wait` loop on `cli.py`. Existing replan budgeting in
  `_write_ready_draft_attempts` at `:2689` caps this at 10 attempts;
  after the cap the loop escalates out of the write-ready fast path
  entirely. So worst case is 10 turns × ~12 s = ~2 min of churn vs
  the current 1 turn × 90 s + replan churn. Net better, but Phase 4
  recovery wiring should land soon to make this a 1-turn resolution.
- **Diagnostic dilution if landed alongside other changes.** Land
  this as a single isolated commit; do not bundle with the prompt
  shrink, the recovery wiring, or any caller-side change. The whole
  point is to attribute any observed dominant-share change to one
  variable.

## Implementer checklist

- [ ] Edit `src/mew/work_loop.py:1686-1699` — split the
      `compiler_kind != "patch_draft"` branch into a
      compiler-blocker-promote case and the existing fallback case.
- [ ] Add three unit tests in `tests/test_work_session.py` per the
      "Test changes" section above; place them adjacent to the
      existing `test_tiny_write_ready_draft_lane_returns_wait_for_patch_blocker`
      at `:7402` so the file's tiny-lane group stays contiguous.
- [ ] Run `uv run python -m pytest -q tests/test_work_session.py -k
      tiny_write_ready_draft` — expect all existing tiny-lane tests
      to pass plus three new tests.
- [ ] Run `uv run python -m pytest -q tests/test_work_session.py` —
      expect no new failures or flakes.
- [ ] Verify in a fresh local trace on a `#402`-shape task that
      `model_metrics.tiny_write_ready_draft_exit_stage` is
      `"compiler_blocker"` on the unpaired-source-edit case and the
      turn does not run a generic-think after the tiny call.
- [ ] Confirm `failure` is absent on the same trace (or is a
      next-turn-recovery shape, not `request_timed_out`).
- [ ] Optional one-line addendum under `ROADMAP_STATUS.md` noting the
      post-tiny-draft follow-up now honors compiler blockers without
      a generic-think retry.

Slice is landable as a single commit titled roughly
`Promote M6.11 tiny lane compiler patch_blocker to wait action`.
