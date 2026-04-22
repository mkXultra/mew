# Recommendation

Choose one bounded slice: **accept compiler-produced tiny-lane `patch_blocker` results as authoritative stop conditions instead of generic fallback**.

## Why This Slice

- HEAD is `5bbc994` and the fresh `#402` rerun at `.mew/replays/work-loop/2026-04-22/session-392/todo-no-todo-392/turn-1826/attempt-1/report.json` changes the bottleneck.
- The tiny lane is no longer the dominant stall:
  - `tiny_write_ready_draft_elapsed_seconds ≈ 11.58`
  - `patch_draft_compiler_ran = true`
  - `tiny_write_ready_draft_outcome = fallback`
  - `tiny_write_ready_draft_fallback_reason = compiler_unpaired_source_edit_blocked`
- The turn still fails as `model_error/request_timed_out` because `plan_work_model_turn()` falls through into the generic write-ready THINK path after that exact blocker and spends the remaining full timeout there.
- Current code already proves the blocker vocabulary is stable and meaningful:
  - `src/mew/patch_draft.py:11-23` maps `unpaired_source_edit_blocked -> add_paired_test_edit`
  - `src/mew/work_loop.py:1654-1684` already accepts model-returned `patch_blocker` authoritatively
  - `src/mew/work_loop.py:1686-1698` treats compiler-returned `patch_blocker` as fallback, which is the waste exposed by turn `1826`
  - `src/mew/work_loop.py:2755-2796` then runs generic THINK because only non-`fallback` tiny results short-circuit

This is the smallest slice that directly addresses the new live evidence without widening into broader recovery or follow-status work.

## Exact Bounded Change

Touch only:

- `src/mew/work_loop.py`
- `tests/test_work_session.py`

Implement this behavior in `_attempt_write_ready_tiny_draft_turn()`:

- When the tiny model returns `patch_proposal` but `compile_patch_draft(...)` returns a schema-valid `patch_blocker` with a stable non-empty code other than `model_returned_non_schema`, treat it the same way the function already treats a model-returned `patch_blocker`.
- Return `status="blocker"` with a `wait` action using `_stable_write_ready_tiny_draft_blocker_reason(...)`.
- Do not fall through to the generic THINK path for this case.
- Reuse the existing blocker vocabulary and metrics where possible; do not invent a second blocker namespace just for compiler-originated blockers.

Do not expand scope in this slice:

- no `src/mew/patch_draft.py` changes
- no prompt text change
- no timeout-budget change
- no resume/follow-status wiring
- no pairing preclassification before the tiny call

## Alternatives Rejected

- **More tiny prompt shrinking**: not next anymore. The latest report shows the tiny lane already finishes in about `11.58s` and reaches the compiler. Prompt size is no longer the immediate limiter on this shape.
- **Pairing-aware preclassification before the tiny call**: lower value than blocker acceptance now. The compiler is already classifying the exact problem quickly as `unpaired_source_edit_blocked`; the waste is that mew ignores that result and reruns generic THINK.
- **Timeout-budget increase**: wrong direction. The generic fallback path is what consumes the long budget after a useful blocker already exists.
- **Phase 4 follow-status / resume surfacing**: too wide as the next slice. First stop the unnecessary second model call; only then widen into state/reporting surfaces if needed.

## Acceptance Criteria

1. A focused work-loop test proves that a tiny-lane `patch_proposal` which compiles to `patch_blocker(code="unpaired_source_edit_blocked")` returns a terminal `wait` action immediately, with no second generic THINK call.
2. That test proves the returned reason is the stable blocker form, e.g. `write-ready tiny draft blocker: unpaired_source_edit_blocked`.
3. The same test proves `model_metrics.patch_draft_compiler_ran = true`, `patch_draft_compiler_artifact_kind = "patch_blocker"`, and the replay path is populated.
4. The same test proves the turn no longer ends in `model_error/request_timed_out` for this shape solely because the generic fallback path ran afterward.
5. Existing tiny-lane success and model-returned-blocker tests still pass unchanged.

## Why This Is The Next Slice

Before `5bbc994`, the dominant question was whether the tiny lane itself was too slow. After `5bbc994`, the latest evidence answers that: on this live shape, the tiny lane is now fast enough to produce a real compiler classification. The next bounded move is to consume that classification authoritatively instead of discarding it and timing out in the generic path.
