# M6.11 Tiny Write-Ready Draft Lane — Claude Review

Scope: uncommitted diff on `main` touching `src/mew/work_loop.py`, `tests/test_work_session.py`, `ROADMAP_STATUS.md`. Reviewed against the seven criteria in the review prompt. Code not modified per instructions.

## Verdict

**No blocking findings. Safe to land after acknowledging the observability trade-offs in Findings A and C and the test-coverage gap in Finding D.** All seven invariants the prompt asked about hold. The lane is correctly gated, its success path is routed through the same normalizer as the regular path (so downstream dispatch shape is preserved), the blocker wait reason is stable, fallbacks are all classified, and the shadow compiler cannot double-write.

## Criterion-by-criterion

### (1) Non-write-ready turns unchanged — **holds**

All tiny-lane machinery is behind `write_ready_fast_path.get("active")`:

- `tiny_write_ready_context = build_write_ready_tiny_draft_model_context(context) if write_ready_fast_path.get("active") else {}` (`src/mew/work_loop.py:2530-2534`).
- `tiny_write_ready_prompt` / `tiny_write_ready_timeout` only computed when context is truthy (`work_loop.py:2561-2570`).
- The `tiny_write_ready_draft_*` metric keys are only injected inside the `if write_ready_fast_path.get("active"):` block (`work_loop.py:2596-2630`).
- The tiny-lane attempt itself is gated by `if tiny_write_ready_context:` (`work_loop.py:2635`).
- Inside `build_write_ready_tiny_draft_model_context`, fast-path-inactive returns `{}` (`work_loop.py:1802-1805`), and a second belt-and-suspenders check returns `{}` if the regular write-ready context is empty (`work_loop.py:1807-1808`).

For a non-write-ready turn, `model_metrics` does not gain any `tiny_write_ready_draft_*` keys, no extra model call is issued, and `plan_work_model_turn` proceeds through the pre-existing THINK/ACT flow unchanged.

### (2) Tiny lane tries only on write_ready_fast_path.active — **holds**

Three overlapping gates (see Criterion 1). The lane can only run when `_work_write_ready_fast_path_details` returns `active=True`, i.e., paired src/test cached windows with exact texts and edit-ready first plan-item observation (`work_loop.py:1170-1283`). No path calls `_attempt_write_ready_tiny_draft_turn` outside this guard.

### (3) Tiny-lane success returns authoritative preview action without changing downstream dispatch shape — **holds**

Success path at `work_loop.py:1659-1706`:

1. `compile_patch_draft_previews` produces `edit_file` / `edit_file_hunks` preview dicts with `apply=False, dry_run=True` (`src/mew/patch_draft.py:230-243`).
2. Previews are wrapped exactly the way the regular path would express the same edit set: `{"type": "batch", "tools": previews}` when `len > 1`, else `dict(previews[0])` (`work_loop.py:1681`).
3. The wrapped action is routed through the SAME `normalize_work_model_action` the regular path uses (`work_loop.py:1687`). That normalizer runs the full paired-write batch policy — `paired_write_batch_rejection_reason`, `normalize_paired_write_batch_tools` (which reorders to `[tests_tools, source_tools]`, sets `defer_verify_on_approval`, `paired_test_source_path`) — so the action that leaves the tiny lane is byte-identical in shape to what the regular path would have emitted for the same validated draft (`work_loop.py:2051-2108, 2362-2384`).
4. The returned plan dict matches the regular-path return shape (`decision_plan, action_plan, action, context, model_metrics, model_stream`) at `work_loop.py:2674-2681` vs. `2765-2772`.

One nuance worth noting (not a finding): the tiny lane calls `normalize_work_model_action(action_plan)` without `verify_command` / `suggested_verify_command`. Those two parameters are only consulted for `run_tests` actions (`work_loop.py:2243-2251`), which the tiny lane cannot emit, so omitting them is safe.

### (4) Tiny-lane blocker returns stable wait reason — **holds**

Blocker path at `work_loop.py:1614-1643`:

- The validator's patch-blocker result drives the wait reason, not the raw model output, so malformed model blockers are filtered first (`work_loop.py:1616`).
- `_stable_write_ready_tiny_draft_blocker_reason` emits `f"write-ready tiny draft blocker: {code}"` with a deterministic prefix and the validator's `code`, defaulting to `unspecified_blocker` when empty (`work_loop.py:711-713`).
- Because the blocker goes through `_normalize_blocker_proposal` -> `build_patch_blocker` (`patch_draft.py:350-363`), an empty model code collapses to `model_returned_non_schema` and is explicitly downgraded to a fallback rather than surfaced as a wait reason (`work_loop.py:1616-1618`). So the wait reason only ever exposes a meaningful, non-empty code.

`tests/test_work_session.py` locks the exact format: `"write-ready tiny draft blocker: missing_exact_cached_window_texts"` (`test_work_session.py:7054` area, via the new `test_tiny_write_ready_draft_lane_returns_wait_for_patch_blocker`).

### (5) Timeout/refusal/invalid/unusable fall back cleanly to the current generic path — **holds**

Every non-success path returns `status="fallback"` with a distinct `fallback_reason`, and the outer code only short-circuits on non-fallback (`work_loop.py:2654`). Fallback classification:

| Branch | `fallback_reason` | Source |
| --- | --- | --- |
| Exception, text contains `timeout` / `timed out` | `timeout` | `work_loop.py:1557-1558` |
| Exception, class/text contains `refusal` | `refusal` | `work_loop.py:1559-1560` |
| Other exception | `error` | `work_loop.py:1561-1562` |
| Non-dict model output | `invalid_shape` | `work_loop.py:1571-1579` |
| Kind not in `{patch_proposal, patch_blocker}` | `invalid_shape` | `work_loop.py:1581-1590` |
| `patch_blocker` with empty or `model_returned_non_schema` code | `invalid_shape` | `work_loop.py:1614-1624` |
| Compiler non-schema on `patch_proposal` | `invalid_shape` | `work_loop.py:1649-1651` |
| Compiler emits any other blocker | `compiler_<code>` | `work_loop.py:1649-1651` |
| `compile_patch_draft_previews` returns a blocker | `preview_<code>` | `work_loop.py:1661-1664` |
| Previews empty | `preview_unusable` | `work_loop.py:1671-1673` |
| Normalized preview collapses to `wait` | `translated_preview_unusable` | `work_loop.py:1687-1696` |

On any fallback the outer code proceeds to the pre-existing `call_model_json_with_retries(think_prompt, …)` with the untouched full write-ready think prompt and timeout (`work_loop.py:2684-2695`). No state leaks back into the regular path — `tiny_write_ready_elapsed` is only consumed when folding into `think.elapsed_seconds` at `work_loop.py:2699`.

### (6) Shadow compiler does not double-write replay bundles — **holds**

The gate is `skip_shadow_compile = bool(tiny_result.get("compiler_observed"))` (`work_loop.py:2653`) combined with `if write_ready_fast_path.get("active") and not skip_shadow_compile:` around the regular shadow compile call (`work_loop.py:2748`).

`compiler_observed` is true iff `_compile_write_ready_patch_draft_proposal` ran, whether it succeeded or hit an exception (`work_loop.py:1607-1612`; the exception branch in `_compile_write_ready_patch_draft_proposal` populates `patch_draft_compiler_artifact_kind="exception"` / `patch_draft_compiler_error`, so `compiler_observed` still flips true on a replay-writer failure — `work_loop.py:1503-1506`). Every terminal tiny-lane return after the compile call propagates `compiler_observed=True`; the three pre-compile fallbacks (`work_loop.py:1564-1590`) propagate `compiler_observed=False`. So:

- Tiny lane runs compiler, regardless of succeeded/blocker/post-compile-fallback → regular shadow compile skipped → exactly one replay bundle per turn.
- Tiny lane fails before invoking compiler (exception, non-dict, wrong kind) → regular shadow compile runs as before → one replay bundle per turn.

**Observability trade-off (Finding A, below):** when the tiny lane runs its compiler and then falls back (e.g., compiler returned a blocker, or the preview translator rejected the draft), the regular-path action that is actually dispatched is no longer shadow-compiled. The replay bundle and the generic `patch_draft_compiler_*` keys describe the *tiny lane's proposal*, while the dispatched `action` came from the regular path. This is correct per the stated criterion ("no double-write") but is worth acknowledging for calibration analytics.

### (7) Metrics clearly distinguish tiny lane attempts/results/fallback — **holds with minor gaps (Findings B/C)**

Dedicated keys on the tiny lane:

- `tiny_write_ready_draft_attempted` (bool, from prompt length — `work_loop.py:2619`).
- `tiny_write_ready_draft_outcome` (`""` / `succeeded` / `blocker` / `fallback` — `work_loop.py:1634, 1697, 1556`, etc.).
- `tiny_write_ready_draft_fallback_reason` (the table in Criterion 5).
- `tiny_write_ready_draft_error` (clipped exception text; also populated from the compiler error — `work_loop.py:1603-1604`).
- `tiny_write_ready_draft_compiler_artifact_kind` (mirror of the compiler observation, scoped to the tiny lane — `work_loop.py:1600-1601`).
- `tiny_write_ready_draft_prompt_chars`, `tiny_write_ready_draft_timeout_seconds`, `tiny_write_ready_draft_prompt_contract_version="v1"` (`work_loop.py:1536-1540, 2619-2628`).
- `act.mode = "tiny_write_ready_draft"` on success/blocker, vs. `"model"` / `"deterministic"` for the regular path (`work_loop.py:1632, 1685, 2665`).

This is enough to disambiguate every outcome shape. Two non-blocking gaps are called out as Findings B and C.

## Findings

### Finding A (Low) — post-compiler fallback drops replay coverage of the dispatched action

Where: `work_loop.py:2653, 2748-2758`.

When the tiny lane's compiler runs, stores a replay bundle, and the tiny lane then falls back (e.g., `compiler_kind != patch_draft`, preview blocker, `translated_preview_unusable`), the regular path re-runs THINK and dispatches its own action. `skip_shadow_compile=True` suppresses the regular-path shadow compile, so the replay bundle saved for this turn describes the *tiny lane's rejected proposal*, not the action that was actually taken. The final `model_metrics` shows `patch_draft_compiler_artifact_kind ∈ {patch_blocker, exception, ...}` alongside a `batch` / write action that was never seen by the compiler.

Why: **Low.** The criterion explicitly asked only for "no double-write," which is met. The disambiguating keys (`tiny_write_ready_draft_outcome`, `tiny_write_ready_draft_compiler_artifact_kind`, `act.mode`) are present; analytics dashboards can join them. The ROADMAP_STATUS `Next action` block already says live-calibration confirmation is required before widening recovery work, which is the right gate for catching any skew.

How to apply: acknowledge in ROADMAP notes / calibration queries that the compiler replay for a `fallback` tiny lane describes the tiny proposal, not the dispatched regular-path action. If calibration starts reporting `patch_draft_compiler_artifact_kind="patch_blocker"` on turns whose action is a successful write, that is this case (and is not a bug in the regular path).

### Finding B (Low) — no dedicated tiny-lane elapsed metric

Where: `work_loop.py:1533-1541, 2657-2661, 2699`.

The metrics dict initialized for the tiny lane records `prompt_chars`, `timeout_seconds`, and the contract version, but no `tiny_write_ready_draft_elapsed_seconds`. Instead, time bookkeeping is folded into `think.elapsed_seconds`:

- On tiny success/blocker: `think.elapsed_seconds = _round_seconds(tiny_write_ready_elapsed)` (`work_loop.py:2657-2661`). OK but implicit.
- On tiny fallback: `think.elapsed_seconds = _round_seconds(tiny_write_ready_elapsed + think_elapsed)` (`work_loop.py:2699`). Tiny and regular think times are conflated.

Why: **Low.** All timing is captured in aggregate; `act.mode` tells you whether `think` refers to the tiny lane or the regular lane. But calibration of "how much budget is the tiny lane consuming on fallback turns?" is not directly answerable from metrics alone.

How to apply: if the phase-3 calibration queries need per-lane timing, add a `tiny_write_ready_draft_elapsed_seconds` key inside `_attempt_write_ready_tiny_draft_turn` and let the outer code reuse it rather than reconstructing from `think.elapsed_seconds`.

### Finding C (Low) — generic `patch_draft_compiler_*` keys get rewritten by the tiny lane even on fallback, and `think.prompt_chars` reinterprets on success

Where: `work_loop.py:1603-1606, 2657-2661`.

Two small semantic reinterpretations:

1. On any tiny-lane branch where the compiler ran, the generic keys are re-written via `metrics.update(observation)` (`work_loop.py:1605-1606`). On a subsequent fallback the generic keys now describe the tiny-lane proposal, and when the regular path runs it re-enters with `skip_shadow_compile=True` so those generic keys are never overwritten by the dispatched action. See Finding A.
2. On tiny-lane success, `model_metrics["think"]` is replaced entirely with `{prompt_chars: len(tiny_write_ready_prompt), timeout_seconds: tiny_write_ready_timeout, elapsed_seconds: ...}` (`work_loop.py:2657-2661`). The sibling keys `draft_prompt_static_chars`, `draft_prompt_dynamic_chars`, `draft_prompt_contract_version="v2"` set earlier still describe the REGULAR write-ready prompt (`work_loop.py:2611-2613`). So on a tiny success turn, `think.prompt_chars` and `draft_prompt_*_chars` reference two different prompts with no explicit marker — the reader has to notice `act.mode="tiny_write_ready_draft"` to reconcile them.

Why: **Low.** Not a functional defect. Dashboards that already filter on `act.mode` or on the `tiny_write_ready_draft_outcome` will be fine.

How to apply: if phase-3 calibration needs a clean split, two tweaks would close this without reshaping outputs: (a) emit `tiny_write_ready_draft_prompt_contract_version` alongside (already present) but also gate `draft_prompt_*_chars` on "the regular write-ready prompt was sent" so those keys are not set when the tiny lane short-circuits; (b) prefix the generic `patch_draft_compiler_*` keys with the lane that populated them, or don't auto-copy on fallback.

### Finding D (Medium) — fallback branches are thinly tested

Where: `tests/test_work_session.py:6885-7064` area.

The diff adds two new happy-path / blocker tests and updates one existing test so the tiny lane is exercised as a fallback via `invalid_shape`. The other ten fallback branches enumerated in Criterion 5 have no direct test:

- Exception paths: `timeout`, `refusal`, `error`.
- `patch_blocker` with empty / non-schema code → `invalid_shape` (only the *happy* blocker test exists).
- `compile_patch_draft` returns a non-`patch_draft` blocker (`compiler_<code>`).
- `compile_patch_draft_previews` returns a blocker (`preview_<code>`).
- Previews empty (`preview_unusable`).
- Normalized preview collapses to `wait` (`translated_preview_unusable`).

The classification code is new and carries the contract downstream observers will read; without tests, a future refactor could silently re-label a branch (e.g., move `translated_preview_unusable` into `preview_unusable`) and break calibration. The existing shadow-bridge tests still pass under the new lane because their `fake_model` responses don't carry `kind`, so the tiny lane always fallbacks with `invalid_shape` before invoking its compiler — meaning those tests do not exercise any of the post-compiler fallback branches either.

Why: **Medium.** No blocker for landing, because the happy path and the blocker path are locked, and the existing shadow-bridge coverage protects the pre-existing flow. But if the phase-3 live-calibration work starts reasoning about `fallback_reason` distributions, those strings should be test-locked so they don't drift.

How to apply: add one narrow unit test per classification. The existing fixture + `fake_model` pattern suffices — varying the scenario's live file contents drives the compiler into blocker territory, and raising `RuntimeError("model timed out")` from `fake_model` drives the timeout branch. Do not need a big table; one assertion per `fallback_reason` string is enough.

### Finding E (Low) — error classification is substring-based

Where: `work_loop.py:700-708`.

`_work_model_error_looks_like_timeout` matches any exception whose `str(exc)` contains `timeout` or `timed out`; `_work_model_error_looks_like_refusal` matches class name or message containing `refusal` / `model returned refusal`. These are permissive enough that an unrelated exception mentioning "timeout" in its detail message would be classified as a timeout in metrics.

Why: **Low.** Metrics-only impact; the fallback outcome is the same. The existing codebase uses similar idioms for `call_model_json_with_retries` error shapes, and the strict alternative (catching named exception types) would couple the work loop to the backend client's exception taxonomy.

How to apply: leave as is unless calibration starts showing ambiguous `timeout` vs. `error` counts. If it does, switch to typed exception handling in `_attempt_write_ready_tiny_draft_turn`.

## Residual non-findings (acknowledged, not flagged)

- **`normalize_work_model_action` omits `verify_command`/`suggested_verify_command` in the tiny lane.** Documented above in Criterion 3. Safe because the tiny lane cannot emit `run_tests`.
- **`compile_patch_draft_previews` returns a list on success and a dict-blocker on failure.** The tiny lane handles both (`work_loop.py:1659-1670`); `compiled["previews"]` is always a list.
- **`paired_write_batch_rejection_reason` could reject an unpaired tiny draft.** Also possible, but upstream `_validate_pairing` in `compile_patch_draft` already enforces paired src/test before previews are generated (`patch_draft.py:395-405`), so a single-file tiny proposal lands as a compiler blocker, not a translated-preview-unusable fallback.
- **Pre-model metrics sink is invoked twice on fallback.** Once with initial metrics (`work_loop.py:2631-2632`), once with tiny-lane-merged metrics after fallback (`work_loop.py:2682-2683`). Correct and intentional — observers can see the tiny lane's disposition before the regular THINK begins.
- **ROADMAP update.** Accurately reflects the new lane and keeps the v2 prompt claim (the tiny lane is `v1`; the fallback regular prompt is still `v2`). Next-action block pivots to live collection on `#402`, which is the right next step.

Nothing in the above blocks landing the lane; Finding D is the one piece of follow-up that would pay off directly during the phase-3 live-calibration checkpoint.

## Operational addendum — live evidence from task #402 (2026-04-22)

**Land recommendation: yes, land the slice.** The live data does not contradict the static review; it does re-shape the follow-up priority.

Evidence summary:

- Calibration across 5 bundles: `compiler_bundles=1`, `dominant_bundle_type=work-loop-model-failure.request_timed_out` at 0.8 share. 4 of 5 write-ready turns are *timing out* before reaching the compiler, not being rejected by it.
- Turn 1822 is the lone compiler-bundle turn: `tiny_write_ready_draft_attempted=true`, `tiny_write_ready_draft_outcome=fallback`, `tiny_write_ready_draft_fallback_reason=compiler_unpaired_source_edit_blocked`, `tiny_write_ready_draft_compiler_artifact_kind=patch_blocker`, `patch_draft_compiler_replay_path` populated, `tiny_write_ready_draft_prompt_chars=18040`.

What this confirms:

- The lane plumbing works end-to-end in a real session: the tiny lane caught the model's unpaired src edit, classified it as `compiler_unpaired_source_edit_blocked`, wrote a replay, and fell through to the regular path without changing outer dispatch shape. That is exactly Finding A's predicted trajectory — evidence that the fallback classification and no-double-write gate behave as reviewed.
- The `patch_blocker` artifact kind landing on a turn whose dispatched action presumably came from the regular path is the exact "generic compiler key describes the tiny proposal, not the dispatched action" situation Findings A/C warned about. It is now observable in calibration, so any downstream query that reads `patch_draft_compiler_artifact_kind` on live data must join on `tiny_write_ready_draft_outcome`.

What the live data surfaces that the static review did not anticipate:

1. **Timeouts dominate, not tiny-lane outcomes.** Four of five write-ready turns are `request_timed_out`. The tiny lane was designed to *shrink* the write-ready failure surface; if the timeouts are on the tiny lane itself these would show up as `tiny_write_ready_draft_fallback_reason=timeout` bundles, not a compiler bundle. Need to confirm which call (tiny or regular) is timing out before widening scope.
2. **`tiny_write_ready_draft_prompt_chars=18040` is close to the full v2 prompt.** The roadmap quoted v2 at roughly 20k chars on `#402`, so the "tiny" lane is only ~10% shorter than the full prompt on this task. Either the cached-window texts are the bulk of the prompt and the tiny framing cannot shrink them further, or the tiny prompt builder is carrying fields it does not need. Prompt size is the cheapest timeout lever, so this is worth looking at before more functional work.
3. **n=5, compiler_bundles=1 is too thin to judge tiny-lane distribution.** `tiny_write_ready_draft_outcome` mix across succeeded/blocker/fallback is not yet statistically meaningful.

Next step (replaces the ROADMAP "Next action" currently pointing at live collection alone):

- Keep collecting on `#402` until `total_bundles ≥ ~20` AND `compiler_bundles ≥ ~5`, so the tiny-lane outcome distribution is readable.
- In parallel, attribute the timeout bundles: which lane (tiny vs. regular write-ready vs. regular generic) is exceeding which timeout? That tells us whether the lane is actually reducing the failure surface or just adding a 30s prefix to turns that then still time out on the 90s regular path.
- Inspect the turn-1822 tiny prompt to see why it is ~18k chars and whether the builder can drop any fields that are not load-bearing for drafting.
- Finding D (test-lock the fallback classifier strings) stays on the follow-up list; the live bundle already relies on the `compiler_unpaired_source_edit_blocked` string being stable.
