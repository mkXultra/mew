# M6.11 Post-425 Review — Codex

Date: 2026-04-23  
HEAD: `7fc7de0`

decision: revise  
summary: The current-head cohort is now sufficient to justify a narrow M6.11 implementation slice: tighten write-ready cached-window completeness gating in `work_loop.py` before the tiny draft lane runs. The new calibration ledger is already good enough as the M6.12 seed shape; do not widen its schema while M6.11 is still open.  
product_goal_drift: none  
safety_boundary_status: ok  
evidence_quality: strong  
verification_status: adequate  
hidden_rescue_edits: none

## Findings

- Current-head now has three clean counted compiler bundles and one honest non-counted rejection. `proof-summary` reports `total_bundles=3`, `non_counted_bundle_count=1`, blocker mix `{ no_concrete_draftable_change: 1, insufficient_cached_window_context: 1, insufficient_cached_context: 1 }`, and off-schema/refusal/malformed all `0`.
- The last two counted samples converge on the same underlying failure family: **cached context exists, but it is not sufficient for a safe paired draft**.
  - `#424` / `#414` attempt `2`: `insufficient_cached_window_context` on the compiler-local `patch_draft.py` surface
  - `#425` / `#415` attempt `1`: `insufficient_cached_context` on the dogfood compiler-replay surface
- That convergence maps directly onto the current write-ready activation logic. `src/mew/work_loop.py:1198-1234` activates the fast path once the first plan item is `edit_ready`, paired source/test cached windows exist, and the guidance requests draft mode. `src/mew/work_loop.py:1274-1306` only rejects when exact cached text is missing or marked truncated. It does **not** reject when the cached windows are present but too narrow to support a safe paired edit.
- So even though the coarse concentration threshold still reports `false`, the blocker semantics are no longer random. The measured problem is now specific enough to justify one bounded implementation slice: preflight cached-window **sufficiency**, not just existence.

## Answers

### 1. Is the current-head cohort now sufficient to justify starting a specific M6.11 implementation slice?

Yes.

Not because the current-head threshold math is green; it is not.  
Yes because the last two distinct-surface counted samples point at the same substrate weakness:

- compiler-local surface: cached window present, but too incomplete to draft safely
- dogfood surface: cached context present, but too incomplete to draft safely

That is enough evidence to stop spending more measured slices on the same upstream gap and instead land one bounded fix.

`#423` remains useful as a no-delta/fail-closed control, but it is no longer the dominant interpretation of the cohort. The actionable signal is now the repeated **context-sufficiency** failure on `#424` and `#425`.

### 2. Which exact slice and files?

Start this exact M6.11 slice:

**Slice:** preflight cached-window completeness before entering the write-ready tiny draft lane.

**Files:**

- `src/mew/work_loop.py`
- `tests/test_work_session.py`

**Exact implementation target:**

- tighten `_work_write_ready_fast_path_state(...)` / `_work_write_ready_fast_path_details(...)`
- do not let the fast path stay `active=true` merely because paired cached windows exist and their text is non-empty/non-truncated
- add a stricter preflight that detects when the paired source/test windows stop at an adjacent definition boundary or otherwise lack enough exact old-text context to support one safe paired draft
- return a stable pre-draft blocker / non-active reason instead of discovering the insufficiency only after the tiny draft turn starts

This is the smallest honest slice because it addresses the shared upstream cause exposed by both `#424` and `#425`, without broadening into `patch_draft.py`, `dogfood.py`, or proof-summary schema work first.

### 3. If yes, what should we do instead of another bounded sample?

Do **direct implementation**, not another `mew live` calibration sample.

Reason:

- M6.11 is reviewer-implemented substrate work, not mew-first implementation
- the current-head sample already surfaced enough evidence for this exact preflight fix
- another measured sample is now more likely to reproduce the same context-insufficiency family than to change the decision

Recommended focused verification after the slice:

```bash
uv run python -m unittest \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_falls_back_to_recent_target_path_windows \
  tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_reports_missing_exact_cached_window_texts_reason \
  tests.test_work_session.WorkSessionTests.test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path
```

Then run the sampled loop-level regression:

```bash
uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay' --no-testmon
```

### 4. Is the new canonical ledger enough as an M6.12 input shape?

Yes, the **shape is already enough** as the canonical M6.12 seed shape.

The ledger already carries the important fields:

- `head`
- `task_id` / `session_id` / `attempt`
- `scope_files`
- `verifier`
- `counted`
- `non_counted_reason`
- `blocker_code`
- `reviewer_decision`
- `replay_bundle_path`
- `review_doc`
- `notes`

That is sufficient for later ingestion, clustering, and reviewer audit. While M6.11 remains open, do **not** widen the schema. Extra fields now would be scope creep.

What it **does** need is disciplined population of the existing fields:

- backfill the `review_doc` for `#425` with this review file
- keep `reviewer_decision` values normalized
- keep `non_counted_reason` reviewer-authored and exact

So the answer is: **enough shape, no extra fields now, just field-completeness discipline.**

## Concrete Recommendation

- Start a reviewer-owned implementation slice now.
- Exact files: `src/mew/work_loop.py`, `tests/test_work_session.py`
- Exact slice: tighten write-ready cached-window completeness/sufficiency gating before tiny draft execution
- Exact verification:
  - `uv run python -m unittest tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_falls_back_to_recent_target_path_windows tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_reports_missing_exact_cached_window_texts_reason tests.test_work_session.WorkSessionTests.test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path`
  - `uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay' --no-testmon`
- Execution mode: **direct implementation**, not `mew live` sampling
- Ledger: keep the current schema; just populate the existing `review_doc`/decision fields consistently while M6.11 stays open
