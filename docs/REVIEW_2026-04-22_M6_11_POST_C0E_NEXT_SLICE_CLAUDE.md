# M6.11 Post-c0eba4c — Next Bounded Slice Recommendation (Claude)

Scope: pick one bounded M6.11 Phase 0-4 slice to land after
`c0eba4c "Add M6.11 tiny lane observability"` and the fresh `#402`
live rerun. Stay inside Phase 0-4; do not enter M6.9 or post-M6.11
work.

## Current facts (2026-04-22, turn 1825)

- `tiny_write_ready_draft_prompt_chars=17030` (down only ~5% from the
  pre-v2 18040 baseline)
- `tiny_write_ready_draft_outcome=fallback`
- `tiny_write_ready_draft_fallback_reason=timeout`
- `tiny_write_ready_draft_exit_stage=model_exception`
- `tiny_write_ready_draft_elapsed_seconds≈30.017`
- `tiny_write_ready_draft_timeout_budget_utilization≈1.0006`
- `patch_draft_compiler_ran=false`
- Calibration: `total_bundles=9`, `compiler_bundles=2`, dominant
  timeout share `0.778` (was `0.833` at 6 bundles — within noise)

## What the new observability proves

The c0eba4c slice was scoped exactly to disambiguate "near-budget vs
sub-second" timeouts so the next slice could be picked deterministically
(see `REVIEW_2026-04-22_M6_11_POST_E474_NEXT_SLICE_CLAUDE.md`,
"Acceptance signal"). The data answers it cleanly:

> Most timeouts near budget → prompt-shrink slice.

`elapsed≈30.017s` against a `30.0s` budget (utilization `1.0006`,
overshoot is just the post-`monotonic` finalizer slice) means the model
call genuinely consumes the full timeout window. This is **not** a
guard/transport fast-fail and **not**
`_work_model_error_looks_like_timeout` over-triggering — the call is
actively running for 30 s, producing nothing recoverable, and only
then surfacing a timeout exception.

## Recommendation

**Force the tiny write-ready draft lane to `reasoning_effort="low"`,
regardless of the caller's reasoning policy.** Add a module-level
constant `WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT = "low"` and
use it inside `_attempt_write_ready_tiny_draft_turn`'s
`codex_reasoning_effort_scope(...)` invocation, ignoring the
`reasoning_effort` parameter passed in by the caller (the parameter
stays for signature continuity but is recorded as observability only).
Surface the decision in the metrics dict as
`tiny_write_ready_draft_reasoning_effort` and bump the prompt contract
version `v2 → v3`.

This is the smallest M6.11 Phase 3 slice that actually attacks the
30-second budget burn without compromising correctness.

## Why this slice now

The tiny lane currently inherits `reasoning_effort="medium"` from
`select_work_reasoning_policy`
(`src/mew/reasoning_policy.py:113-120`): any work turn with
`allowed_write_roots` set or `allow_verify` enabled is classified
`small_implementation` and promoted to `medium`. The tiny lane qualifies
because every write-ready turn does. So today the tiny call runs
`codex_reasoning_effort_scope("medium")` at
`src/mew/work_loop.py:1557` and receives a medium reasoning budget on
top of a 17 k prompt that asks the model to emit a multi-file
`patch_proposal` with exact `old`/`new` text per hunk.

That combination explains the at-budget burn:

- **Output is non-trivial.** The schema requires the model to repeat
  exact `old` text for each hunk. Multi-file paired edits with
  reasoning tokens streaming first push generation past 30 s.
- **The tiny prompt is already mechanically constrained.** The
  contract has narrowed to: pick a path from
  `active_work_todo.source.target_paths`, find the hunk inside
  `cached_window_texts`, emit `{kind, summary, files:[...], code,
  detail}` or block. There is no exploration left for the model to
  reason over — the slice is a translation, not a planning task.
- **Medium reasoning has no hunk to chew on.** The tiny lane has no
  resume continuity, no recent failure, no broad action menu. Medium
  reasoning produces tokens that don't change the output decision but
  do consume the 30 s budget.
- **The fallback is intact.** If the tiny lane fails under `low`
  reasoning, the regular write-ready THINK path runs next at the
  reasoning effort the caller's policy chose. We never lose the "real"
  reasoning surface.

## Alternatives considered

| Alternative | Why not now |
| --- | --- |
| Further prompt-envelope shrink (cap `cached_window_texts[i].text` per-window for tiny lane, e.g. 6000 → 1500 chars) | Direct prompt-size lever, but the v2 shrink already removed every non-load-bearing field; the remaining 17 k is dominated by the cached window text the model needs to cite as exact `old`. Capping risks the model lacking the substring it must emit, which would push failures from `model_exception` to `compiler_fallback` / `preview_unusable` without proving the underlying contention. Worth pursuing as a follow-up only if the reasoning lever doesn't move the needle. |
| Blocker-stop preclassification short-circuit (offline classify before model call) | The current bundle distribution shows the failure occurs **inside** the model call (`exit_stage=model_exception`, `compiler_ran=false`). There is no blocker state being silently re-fed into the model — the lane is timing out on first contact. Short-circuit targets a different loss bucket than what dominates `#402`. |
| Lower the 30 s budget | Doesn't address root cause. We already learned the model needs >30 s under current settings; lowering would just move failures left. Budget changes should be data-driven, after we know what the lane actually needs at minimum reasoning. |
| Raise the 30 s budget | Calibration-gate-relevant constant change while the dominant-share gate is already red. Even a 60 s budget at medium reasoning would still concentrate timeouts. Raising masks rather than fixes. |
| Stream-delta first-chunk timestamp instrumentation | Useful, but plumbing stream deltas through the timeout-guard subprocess (`work_loop.py:115-139`) is a separate slice. The reasoning-effort change is a one-line lever that doesn't require crossing the subprocess boundary. |
| Phase 4 drafting-specific recovery | Phase 3 calibration checkpoint is explicitly held open while concentration exceeds thresholds (`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` §3.3). Cannot enter Phase 4 with a 0.778 dominant share. |

## Concrete scope

Files: `src/mew/work_loop.py`, `tests/test_work_session.py` only.
Phase: stays inside M6.11 Phase 3.

### Code changes

1. Add a module-level constant near the existing tiny-lane constants
   (`src/mew/work_loop.py:64-66`):

   ```python
   WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT = "low"
   ```

2. In `_attempt_write_ready_tiny_draft_turn`
   (`src/mew/work_loop.py:1515-1567`):
   - Replace `with codex_reasoning_effort_scope(reasoning_effort):` at
     `:1557` with
     `with codex_reasoning_effort_scope(WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT):`.
   - Keep the `reasoning_effort` parameter on the helper signature so
     the caller in `work_loop.py:2707` does not need to change (and so
     the inherited policy remains observable).
   - Add `"tiny_write_ready_draft_reasoning_effort": WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT`
     to the initial `metrics` dict at `:1533`.
   - Add `"tiny_write_ready_draft_inherited_reasoning_effort": str(reasoning_effort or "")`
     to the same dict so calibration can see the original policy and
     the override side-by-side.

3. Bump `WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION` from
   `"v2"` to `"v3"` at `src/mew/work_loop.py:66`. Reasoning effort is
   not technically part of the prompt text, but it is a reasoning-
   contract change the calibration replay grouping should treat as a
   distinct cohort.

4. Mirror the two new keys in the caller metrics block at
   `src/mew/work_loop.py:2679-2689` so the pre-model metrics sink
   carries them on the optimistic path (parallel to how
   `tiny_write_ready_draft_prompt_contract_version` is mirrored).

No new helper, no changes to the tiny prompt text, no changes to the
context builder, no changes to fallback wiring.

### Test changes

Add to `tests/test_work_session.py`, in the same area as existing
`tiny_write_ready_draft_*` tests:

- `test_tiny_write_ready_draft_uses_low_reasoning_effort_regardless_of_caller`:
  stub the model call to capture the active value of
  `MEW_CODEX_REASONING_EFFORT` during the call (the
  `codex_reasoning_effort_scope` writes it into `os.environ`). Pass
  `reasoning_effort="medium"` (and separately `"high"`) into
  `_attempt_write_ready_tiny_draft_turn`; assert the captured env
  value is `"low"` in both cases.
- `test_tiny_write_ready_draft_metrics_record_reasoning_effort_override`:
  assert the result `metrics` dict contains
  `tiny_write_ready_draft_reasoning_effort == "low"` and
  `tiny_write_ready_draft_inherited_reasoning_effort == "medium"` when
  the caller passes `reasoning_effort="medium"`.
- Update the existing integration-style fixture (search for the
  current `tiny_write_ready_draft_prompt_contract_version` assertion
  near `tests/test_work_session.py:7140-7155`) to assert the bumped
  `"v3"` version.

Three tests, one per contract surface (env scope, metrics dict, version
bump). The existing exception/success/shape-reject coverage from the
c0eba4c slice already exercises the return paths.

## Out of scope

- Any change to `WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS`
  (still 30 s).
- Any change to `cached_window_texts` content or per-window text
  limits (`WORK_RECENT_READ_FILE_WINDOW_TEXT_LIMIT` stays 6000).
- Any change to `select_work_reasoning_policy` itself — the override
  is local to the tiny lane, not a global policy change.
- Any structural change to the patch contract or to the tiny prompt
  body text.
- Any first-chunk / token-streaming latency instrumentation.
- Any Phase 4 recovery vocabulary work.
- Roadmap status copy update (acceptable to add a one-line addendum
  under `ROADMAP_STATUS.md:2009-2017` noting the post-tiny-draft
  follow-up now includes the reasoning-effort override before further
  shrink work).

## Acceptance signal

After this slice lands and a fresh `#402` rerun is collected:

- Every replay bundle and live metrics record carries
  `tiny_write_ready_draft_reasoning_effort="low"` and
  `tiny_write_ready_draft_inherited_reasoning_effort=<original>`.
- The `tiny_write_ready_draft_elapsed_seconds` distribution can be
  re-bucketed against the v2 (medium) baseline already in calibration.
- That comparison picks the next slice deterministically:
  - **Elapsed drops materially (median below ~10 s) and timeout share
    falls below the 0.4 dominant-share gate** → reasoning was the
    latency; lane is now within budget. Next slice: re-evaluate the
    Phase 2/3 calibration checkpoint as potentially passable; if still
    tipping on a different bucket, address that bucket directly.
  - **Elapsed stays near 30 s and timeout share stays above ~0.6** →
    reasoning was not the latency. Next slice: cap per-window
    `cached_window_texts[i].text` for the tiny lane (the
    correctness-risky shrink we deferred above), with an explicit
    blocker code for "cached window truncated past anchor" so
    failures stay diagnosable.
  - **Mixed result (some elapsed near budget, some sub-15 s but with
    `compiler_fallback` exit_stage)** → low-reasoning is fast enough
    but not capable enough; next slice is the structural one (split
    the schema into per-file calls, or move to anchor-based old-text
    matching in the compiler).

## Risks

- **Regression risk: low.** The tiny lane has a complete fallback to
  the regular write-ready THINK path; if low reasoning produces a
  shape the compiler rejects, the regular path runs next at the
  caller's policy effort. The change touches no schema, no prompt
  text, and no compiler logic.
- **Diagnostic dilution if landed alongside other changes.** Land
  this as a single isolated commit; do not bundle with the cached-
  window cap or any prompt-text edit. The whole point is to attribute
  any observed elapsed-distribution change to one variable.
- **`os.environ` mutation in the scope.** `codex_reasoning_effort_scope`
  already mutates `os.environ[CODEX_REASONING_ENV]` and restores it on
  exit (`reasoning_policy.py:131-145`). No new threading concerns
  introduced; the tiny lane runs inline before the regular think path
  in the same process, so the env is restored before the fallback runs.
- **Calibration cohort split.** Bundles collected at `v2` (medium) and
  `v3` (low) differ in a load-bearing variable. Document in the slice
  commit that the `v2` cohort should be excluded from the post-slice
  `dominant_share` evaluation; the calibration evaluator already
  groups by `calibration_bundle_type`, but the `v2 vs v3` split is
  on a different field, so a manual exclusion in the analysis (not
  in code) is required for the first rerun.

## Implementer checklist

- [ ] Edit `src/mew/work_loop.py:64-66` — add the new constant; bump
      contract version to `"v3"`.
- [ ] Edit `src/mew/work_loop.py:1533-1544` — add the two new keys to
      the initial metrics dict.
- [ ] Edit `src/mew/work_loop.py:1557` — replace the
      `codex_reasoning_effort_scope(reasoning_effort)` argument with
      the new constant.
- [ ] Edit `src/mew/work_loop.py:2679-2689` — mirror the two new keys
      in the caller's pre-model metrics block.
- [ ] Add three unit tests in `tests/test_work_session.py`.
- [ ] Run `uv run python -m unittest tests.test_work_session` for the
      `tiny_write_ready_draft` group only.
- [ ] Verify in a fresh local trace that the tiny call's
      `MEW_CODEX_REASONING_EFFORT` env is `"low"` during the model
      call and restored after.
- [ ] Optional one-line addendum to `ROADMAP_STATUS.md:2009-2017`.

Slice is landable as a single commit titled roughly
`Force M6.11 tiny draft lane to low reasoning effort`.
