# M6.11 Post-e474b6a — Next Bounded Slice Recommendation (Claude)

Scope: pick one bounded M6.11 Phase 0-4 slice to land after
`e474b6a "Narrow M6.11 tiny draft surface"`. Do not widen into M6.9 or
post-M6.11 work.

## Current facts (2026-04-22)

- Latest live rerun on task `#402`, turn `1823`:
  `tiny_write_ready_draft_outcome=timeout`,
  `tiny_write_ready_draft_fallback_reason=timeout`,
  `patch_draft_compiler_ran=false`.
- Tiny-lane prompt envelope still `tiny_write_ready_draft_prompt_chars=18040`.
- Calibration: `total_bundles=6`, `compiler_bundles=1`, dominant timeout share
  `0.833`.
- `e474b6a` fixed stale tiny-surface contamination (`target_paths`,
  `cached_window_texts`, `plan_item` now align to the first actionable
  observation) but did not move the timeout rate.

## Recommendation

**Land a lane-specific elapsed-time observability slice for the tiny
write-ready draft lane.** Add dedicated `tiny_write_ready_draft_elapsed_seconds`
(and related) fields to the metrics dict in `_attempt_write_ready_tiny_draft_turn`
so every return path — timeout, invalid_shape, blocker, compiler-fallback,
success — records the wall-clock span of the tiny model call. No behavior
change; observability only.

This is the smallest M6.11 Phase 3 slice that unblocks the *next* fix decision.

## Why this slice now

The live signal (`0.833` timeout share, 6 bundles) is currently
**uninterpretable**:

- `tiny_write_ready_draft_timeout_seconds` today records only the **budget**
  (30.0s), not the actual elapsed.
- `elapsed_seconds` is returned by `_attempt_write_ready_tiny_draft_turn`
  (`src/mew/work_loop.py:1567`, `:1577`, `:1588`, `:1622`, `:1641`, `:1655`,
  `:1668`, `:1677`, `:1694`, `:1704`) but is only folded into
  `model_metrics["think"]["elapsed_seconds"]` as a **blended** total
  (`work_loop.py:2714`, `:2753`), and on the fallback path it is summed with
  the subsequent regular think-elapsed, so the tiny-lane contribution is no
  longer separable once recorded in replay bundles.
- Result: we cannot distinguish a timeout that burned the full 30s budget
  (model genuinely slow or response-too-long under an 18k prompt) from a
  timeout that aborted in <1s (network/auth/guard-subprocess failure
  surfacing as a timeout-looking exception via
  `_work_model_error_looks_like_timeout`, `work_loop.py:1557`).

Every other candidate slice is premature without this data:

| Alternative considered | Why not now |
| --- | --- |
| Prompt-contract shrinking (18040 → ~8-10k) | Direct and attractive, but we do not yet know if timeouts are input-processing-bound or not. Landing this blind risks shipping a shrink that leaves the dominant-share gate red for an orthogonal reason; we would then still need the observability slice to interpret the next rerun. |
| Blocker-stop short-circuit (offline classify before model call) | Valuable, but the current turn-1823 state (`patch_draft_compiler_ran=false`) shows the tiny lane is failing *inside* the model call, not because of a missed blocker state. Short-circuit targets a different loss bucket than the one actually dominating `#402`. |
| Raise 30s budget | Not bounded — changes a calibration-gate-relevant constant while the gate is already red on concentration. Budget changes should be data-driven, i.e., after this observability slice. |
| Phase 4 drafting-specific recovery | Phase 3 calibration checkpoint is explicitly held open while off-schema/refusal/timeout concentration exceeds thresholds (`docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md`). Cannot enter Phase 4 until Phase 3 calibration produces interpretable data. |

## Concrete scope

Files: `src/mew/work_loop.py`, `tests/test_work_session.py` only.
Phase: stays inside M6.11 Phase 3 (shadow/live calibration), no M6.9 surface.

### Code changes

In `_attempt_write_ready_tiny_draft_turn` (`src/mew/work_loop.py:1531-1705`):

1. Add three new keys to the `metrics` dict initialized at `:1533`:
   - `tiny_write_ready_draft_elapsed_seconds`: `0.0` (float, round to 3dp via
     `_round_seconds`)
   - `tiny_write_ready_draft_timeout_budget_utilization`: `0.0` (float,
     `elapsed / timeout_seconds`, clamped to `[0.0, 1.0]` and 3dp)
   - `tiny_write_ready_draft_exit_stage`: `""`, populated with a stable,
     enum-like string identifying **which return path** was taken. Values:
     `model_exception`, `non_dict_response`, `unknown_kind`,
     `blocker_invalid_shape`, `blocker_accepted`, `compiler_fallback`,
     `preview_blocker`, `preview_unusable`, `translated_preview_unusable`,
     `succeeded`.

2. Before each `return { ... "elapsed_seconds": time.monotonic() - started }`
   block, write the same elapsed value into the metrics dict and set
   `exit_stage`. This is a mechanical ~10-line change: every existing return
   site already computes `time.monotonic() - started`; reuse that expression
   into both keys.

3. In the caller at `work_loop.py:2705-2753`, leave the blended
   `model_metrics["think"]["elapsed_seconds"]` path untouched (avoid rippling
   into the regular think flow). The tiny-lane metrics dict already flows
   through `model_metrics.update(tiny_result.get("metrics") or {})` at
   `:2706`, so the new keys surface in calibration bundles with no extra
   wiring.

No new helper, no new schema, no new config knob.

### Test changes

Add to `tests/test_work_session.py`, in the same area as existing
`tiny_write_ready_draft_*` tests:

- `test_tiny_write_ready_draft_records_elapsed_on_timeout`: stub the model
  call to raise a timeout-shaped exception after a non-zero monotonic delta;
  assert `tiny_write_ready_draft_elapsed_seconds > 0`,
  `tiny_write_ready_draft_exit_stage == "model_exception"`,
  `tiny_write_ready_draft_fallback_reason == "timeout"`, and that
  `timeout_budget_utilization` is in `[0.0, 1.0]`.
- `test_tiny_write_ready_draft_records_elapsed_on_success`: stub the model
  call to return a valid `patch_proposal` that compiles to a preview; assert
  `tiny_write_ready_draft_elapsed_seconds > 0` and
  `tiny_write_ready_draft_exit_stage == "succeeded"`.
- `test_tiny_write_ready_draft_records_elapsed_on_invalid_shape`: stub model
  to return `{}`; assert `exit_stage == "non_dict_response"` or
  `"unknown_kind"` as appropriate and elapsed is populated.

Three tests, one per exit-stage family (exception, success, shape-reject),
lock the observability contract on representative paths. Do not add a test
per exit_stage value; the enum is internal.

## Out of scope

- Any change to the 30s tiny-lane budget
  (`WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS`).
- Any shrink of the tiny prompt envelope (still at 18040 chars).
- First-chunk / token-streaming latency (currently non-trivial because the
  call runs in a forked timeout-guard subprocess at `work_loop.py:115-139`;
  plumbing stream-delta timestamps through that boundary is a separate slice).
- Any offline blocker-stop / pre-model short-circuit logic.
- Any Phase 4 recovery vocabulary work.
- Roadmap status wording update (acceptable to include a one-line addendum
  under `ROADMAP_STATUS.md:2009-2015` saying the post-tiny-draft follow-up
  now includes elapsed observability before further fixes).

## Acceptance signal

After this slice lands and a fresh `#402` rerun is collected:

- Every replay bundle and live metrics record carries
  `tiny_write_ready_draft_elapsed_seconds` and
  `tiny_write_ready_draft_exit_stage`.
- The calibration dominant-share computation can be **re-bucketed by
  `exit_stage`**, cheaply answering: *of the 5/6 timeout bundles, how many
  burned ≥25s vs aborted in <2s?*
- That answer picks the next slice deterministically:
  - Most timeouts near budget → prompt-shrink slice (Option B).
  - Most timeouts sub-second → guard/transport fix or
    `_work_model_error_looks_like_timeout` over-triggering investigation.
  - Mixed → pursue both in parallel bounded slices with data to justify each.

## Risks

- **Regression risk: effectively zero.** Pure metrics-dict additions on
  return paths; no control flow changes; no schema changes visible to the
  model or the validator.
- **Scope creep risk:** the ten `exit_stage` enum values are tempting to
  collapse into fewer. Resist — each one corresponds to an existing
  distinct return site and is useful for calibration bucketing. But do **not**
  promote `exit_stage` into the validator contract or into
  `active_work_todo`; it is an observability-only field.
- **Cache interaction risk:** calibration summaries that aggregate pre- and
  post-slice bundles will see `exit_stage=""` on old bundles. Document in
  the slice commit that a fresh `#402` collection is required to get
  interpretable share breakdown; do not backfill.

## Implementer checklist

- [ ] Edit `src/mew/work_loop.py:1533-1541` — add three keys to initial
      metrics dict.
- [ ] Edit each return site in `_attempt_write_ready_tiny_draft_turn`
      (lines `1564`, `1574`, `1585`, `1619`, `1635`, `1652`, `1665`, `1674`,
      `1691`, `1698`) — populate the three new keys, including exit_stage,
      reusing the existing elapsed expression.
- [ ] Add three unit tests in `tests/test_work_session.py`.
- [ ] Run `uv run python -m unittest tests.test_work_session` for the
      `write_ready` / `tiny_write_ready_draft` group only.
- [ ] Verify `model_metrics` shown in a fresh local trace contains the new
      keys on both timeout and success paths.
- [ ] Optional one-line addendum to `ROADMAP_STATUS.md:2009-2015`.

Slice is landable as a single commit titled roughly
`Add tiny write-ready draft elapsed observability`.
