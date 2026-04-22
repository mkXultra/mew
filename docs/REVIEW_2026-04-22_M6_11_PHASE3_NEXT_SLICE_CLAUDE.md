# M6.11 Phase 3 — Next Slice Planning Note (Claude)

Planning only. Given HEAD `6152a47` (shadow-only live bridge landed), identifies the next smallest safe implementation slice toward Phase 3 close.

## Recommendation

**Land (d) a narrower bridge — specifically "authoritative blocker-stop, no prompt swap, no translator dispatch."** On a write-ready fast-path turn where the shadow compiler produces a `patch_blocker`, rewrite the turn's `action` to a `wait` with a blocker-derived reason so the existing dispatch path naturally skips write-tool dispatch. On validated drafts or exceptions or unadapted shapes, leave the action byte-identical to today. Keep the prompt (`build_work_write_ready_think_prompt`) unchanged. Do not consume `compile_patch_draft_previews` as a dispatch source in this slice.

This is the single-bit promotion of the already-landed shadow observation to authoritative blocker-stop. It is the smallest change that makes the compiler load-bearing at all, while leaving all validated-path dispatch semantics unchanged.

## Why this slice — grounded in repo state

The three remaining Phase 3 sub-tasks from the design doc (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:817-823`) after the shadow-bridge and translator slices land are: prompt swap, authoritative dispatch on validation, authoritative reject on blocker.

**(a) Prompt swap only is not viable.** The write-ready prompt currently asks for the generic tool-batch schema (`build_work_write_ready_think_prompt` at `src/mew/work_loop.py:1610`, contract version `"v1"` at `src/mew/work_loop.py:64`). `normalize_work_model_action` at the call site (`src/mew/work_loop.py:2270-2274`) expects that old shape. Swapping the prompt to the tiny `patch_proposal | patch_blocker` schema leaves `normalize_work_model_action` with nothing it can parse — the turn returns something like `wait` and the loop strands on write-ready turns. This is the same "cannot land first" argument the shadow-bridge planning note made (`docs/REVIEW_2026-04-22_M6_11_PHASE3_LIVE_BRIDGE_PLAN_CLAUDE.md:18-22`), and it still holds.

**(b) Full authoritative dispatch in one slice is too wide.** Two changes would land together: "blocker now stops" and "validated drafts now dispatch through the translator." The second is riskier — it introduces the translator output (`{type, path, old, new, apply: False, dry_run: True}`, per `src/mew/patch_draft.py:225-231`) as a new dispatch source, which has never been round-tripped against the existing write-tool dispatch path. That reviewable surface belongs to its own slice with its own translator-shape parity tests.

**(c) Combined prompt swap + authoritative dispatch is worst of both** — three new failure modes reviewed together (prompt regression, blocker false-positives, translator-vs-old dispatch divergence). Rejected on review-surface grounds.

**(d) "Authoritative blocker-stop only"** uses the infrastructure that already shipped:

- `_shadow_compile_patch_draft_for_write_ready_turn` at `src/mew/work_loop.py:1249` already runs on every write-ready turn and sets `model_metrics["patch_draft_compiler_artifact_kind"]` to one of `""` / `"unadapted"` / `"patch_draft"` / `"patch_blocker"` / `"exception"` (`src/mew/work_loop.py:1307, 1313, 1318, 1324, 1342, 1351, 1402, 1421`).
- The call site at `src/mew/work_loop.py:2275-2285` is the only place a dispatch-affecting decision would need to be inserted.
- Every validated / blocker / exception / unadapted / inactive branch is already test-pinned (`tests/test_work_session.py:6868, 6933, 6997, 7039, 7123`). The blocker test at `:6933` currently asserts the outer action stays as `"batch"` on a blocker — that assertion is exactly what this slice flips, making the test diff the semantic record of the change.

Grounded in the existing observation dict, (d)'s full implementation is: forward the blocker code into the observation, then at `src/mew/work_loop.py:2275-2285` rewrite `action` when `artifact_kind == "patch_blocker"`. That is the smallest surface that moves Phase 3 forward.

## Prerequisite check — calibration

The entry condition from `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` §3.3 and `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:830-834` is that the calibration checkpoint must be evaluable before Phase 3 rollout proceeds. The checkpoint itself is wired (`mew proof-summary --m6_11-phase2-calibration`, landed earlier), and the shadow bridge is now feeding it real bundles. Before landing (d), a reviewer-initiated invocation of the checkpoint against a representative replay-root sample must pass — specifically `off_schema_rate ≤ 5%`, `refusal_rate ≤ 3%`, `failure_mode_concentration ≤ 40%`, and `malformed_relevant_bundles_ok`. If the gate fails, (d) is not the next slice; a Phase 2.5 calibration slice is.

This slice does not re-implement the gate; it only depends on the gate's pass signal as an external prerequisite before land.

## Scope boundary

**In scope:**

- Extend `_shadow_compile_patch_draft_for_write_ready_turn` at `src/mew/work_loop.py:1249` to carry the blocker code and recovery action in its return dict. Candidate keys: `patch_draft_compiler_blocker_code` (str, e.g., `"stale_cached_window_text"`), `patch_draft_compiler_blocker_recovery` (str, e.g., `"refresh_cached_window"`). Both empty-string when not applicable. Populated at the existing validated-branch block at `src/mew/work_loop.py:1401-1407` by reading `validator_result.get("code")` and `validator_result.get("recovery_action")`.
- Add matching keys to the pre-model initialization at `src/mew/work_loop.py:2202-2208`.
- Add a single conditional at `src/mew/work_loop.py:2275-2285` (immediately after the `model_metrics.update(...)` call):

    ```python
    if model_metrics.get("patch_draft_compiler_artifact_kind") == "patch_blocker":
        action = {
            "type": "wait",
            "reason": (
                f"patch draft compiler blocker: "
                f"{model_metrics.get('patch_draft_compiler_blocker_code') or 'unknown'}"
            ),
        }
    ```

- That is the entire production-code change. No new dispatch plumbing; the overridden `action` flows through the existing return path at `src/mew/work_loop.py:2292-2299` and thereafter through `commands.py` like any other `wait` action.

**Out of scope (explicit non-goals for this slice):**

- Do not touch `build_work_write_ready_think_prompt` at `src/mew/work_loop.py:1610`. Prompt stays at contract version `"v1"`.
- Do not consume `compile_patch_draft_previews` as a dispatch source. Validated drafts still flow through the existing action path. The translator remains offline-only.
- Do not touch `normalize_work_model_action`. The adapter from old-shape action to `patch_proposal` (`src/mew/work_loop.py:1310-1352`) stays as-is.
- Do not add `build_work_recovery_plan` routing based on blocker code. Generic replan is acceptable for this slice; draft-specific recovery is Phase 4 scope.
- Do not touch `build_work_session_resume` or `work --follow-status` rendering. Blocker visibility via `model_metrics` is sufficient for this slice.
- Do not change `write_tools.py` (still frozen per design doc line 881).
- Do not change `src/mew/commands.py`. The existing `update_work_model_turn_plan(..., model_metrics=planned.get("model_metrics"))` already carries the two new keys through.
- Do not add a feature flag or env var. The conditional is always-on when the compiler produces a blocker on a write-ready turn; there is no "shadow vs authoritative" toggle.
- Do not add any new replay-bundle fields. `write_patch_draft_compiler_replay` is unchanged.
- Do not touch the existing validated / unadapted / exception / inactive test assertions — only the blocker test needs updating.

## Files to touch

| File | Change |
| --- | --- |
| `src/mew/work_loop.py` | Extend the shadow helper (`src/mew/work_loop.py:1249`) to populate two new observation keys from `validator_result` on the success branch (`:1401-1407`). Add matching empty-string defaults to the pre-model initialization (`:2202-2208`). Insert a six-line conditional after `:2285` that rewrites `action` to `wait` when `artifact_kind == "patch_blocker"`. |
| `src/mew/work_replay.py` | No change. |
| `src/mew/patch_draft.py` | No change. `build_patch_blocker` already emits `code` and `recovery_action` fields. |
| `src/mew/commands.py` | No change. |
| `src/mew/proof_summary.py` | No change. Calibration gate evaluation is a prerequisite to this slice, not a deliverable. |

## Tests

All changes in `tests/test_work_session.py`. Four net changes:

1. **Update** `test_patch_draft_compiler_shadow_bridge_records_blocker_without_changing_outer_action` at `tests/test_work_session.py:6933`. Current assertion is `planned["action"]["type"] == "batch"` on blocker. New assertion is `planned["action"]["type"] == "wait"`, with `"patch draft compiler blocker:"` and the blocker code (e.g., `"stale_cached_window_text"`) in `planned["action"]["reason"]`. The metrics assertions (`artifact_kind == "patch_blocker"`, `replay_path` non-empty) remain unchanged. Rename the test to `..._rewrites_outer_action_to_wait` to reflect the new semantics. This test is the single commit-level record of the behavior change.

2. **Add** a new test `test_patch_draft_compiler_shadow_bridge_blocker_forwards_code_and_recovery_to_metrics`. Uses the same stale-cached-window fixture setup as (1). Asserts the two new `model_metrics` keys are populated with the exact blocker code and recovery action. Pins the forwarding-from-observation half of the change independently of the action-rewrite half.

3. **Leave unchanged** `test_patch_draft_compiler_shadow_bridge_records_validated_replay_for_write_ready_batch` (`:6868`), `test_patch_draft_compiler_shadow_bridge_marks_unadapted_wait_without_replay` (`:6997`), `test_patch_draft_compiler_shadow_bridge_replay_writer_exception_does_not_escape` (`:7039`), `test_patch_draft_compiler_shadow_bridge_is_skipped_when_write_ready_fast_path_is_inactive` (`:7123`). Each of these exercises a non-blocker path; the new conditional does not fire on any of them. Passing-without-edit is the regression check that the slice's scope did not leak.

4. **Optional**: if the implementer wants an explicit round-trip test, add one that builds a validated PatchDraft artifact, forces it to produce both `code == ""` and `recovery_action == ""` (the validated case), and asserts the two new metric keys are empty strings after the helper runs. Nice-to-have; not required for coverage.

No changes in `tests/test_patch_draft.py` or `tests/test_work_replay.py`.

## Acceptance criteria

1. On a write-ready fast path turn where `_shadow_compile_patch_draft_for_write_ready_turn` returns `artifact_kind == "patch_blocker"`, the planned turn's `action` has `type == "wait"` and its `reason` contains both the literal `"patch draft compiler blocker:"` and the blocker code.
2. On a write-ready fast path turn where the helper returns `artifact_kind == "patch_draft"`, the planned turn's `action` is byte-identical to the pre-slice behavior (the model's original `batch` / `edit_file` / `edit_file_hunks` action, in the original tool order).
3. On a write-ready fast path turn where the helper returns `artifact_kind == "exception"` or `"unadapted"` or `""`, the planned turn's `action` is byte-identical to the pre-slice behavior.
4. On a non-write-ready turn, behavior is byte-identical to today; the conditional at the call site is only reachable when `write_ready_fast_path.get("active")` is true.
5. `model_metrics.patch_draft_compiler_blocker_code` and `model_metrics.patch_draft_compiler_blocker_recovery` are populated from `validator_result.code` and `validator_result.recovery_action` on the blocker branch, empty strings otherwise (validated / unadapted / exception / inactive).
6. The replay bundle written by `write_patch_draft_compiler_replay` is unchanged in shape; `validator_result` on disk continues to carry the blocker code and recovery action directly.
7. `build_work_write_ready_think_prompt`, `normalize_work_model_action`, `compile_patch_draft_previews`, `build_work_recovery_plan`, `build_work_session_resume`, `write_tools.py`, and every approval/apply path are byte-identical to the pre-slice state.
8. The calibration gate (`mew proof-summary --m6_11-phase2-calibration`) passes on a representative replay sample collected under shadow mode before this slice lands. Record the pass signal in the land notes.
9. The existing four shadow-bridge tests on non-blocker paths pass unchanged; the blocker test is updated per the Tests section above; the new blocker-code forwarding test passes.

## Follow-on work (explicitly NOT in this slice)

- **Validated-path dispatch via translator.** Flip the validated branch so `compile_patch_draft_previews` output drives dispatch instead of the original action. Requires teaching the dispatch path to consume the translator's `{type, path, old, new, apply, dry_run}` shape, or invoking `write_tools.edit_file` / `edit_file_hunks` directly from the helper. This is the slice that finally makes the translator load-bearing.
- **Prompt swap.** Replace `build_work_write_ready_think_prompt` with the tiny `patch_proposal | patch_blocker` contract, bump `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION` to `"v2"`, retire the adapter at `src/mew/work_loop.py:1310-1352`. Must land AFTER validated-path dispatch lands, else the loop strands on write-ready turns.
- **Draft-specific recovery.** Phase 4 scope. Map the `patch_draft_compiler_blocker_recovery` metric value to an actual recovery action (`refresh_cached_window`, `narrow_old_text`, `revise_patch`, etc.) in `build_work_recovery_plan` so a blocker does not collapse to generic `replan`.
- **Follow-status surface.** Expose `patch_draft_compiler_artifact_kind`, `patch_draft_compiler_blocker_code`, and `patch_draft_compiler_blocker_recovery` in `work --follow-status` so operators can see why a turn stopped.
- **Retention knob for `.mew/replays/work-loop`.** Operationally relevant as write-ready turns become more common; out of scope for the dispatch-flip slice.

## Residual risks for this slice

- **Compiler-stricter-than-dispatch false positives.** If the compiler emits a blocker for a proposal the existing dispatch would have applied successfully, this slice trades a successful turn for a blocked one. The calibration gate's `off_schema_rate ≤ 5%` threshold is the operational guard; Acceptance criterion 8 forces a reviewer to look at the rate before landing. Without a pre-land gate pass, this slice must not land.
- **Generic replan on blocker.** Without Phase 4 recovery wiring, a blocker-stop leads to a generic replan next turn, which may re-draft a similar proposal and re-block. Acceptable for this slice because the total work lost per blocker is bounded (one turn, one replan), and the blocker code is now observable in metrics for any operator who wants to intervene. But it's a temporary inefficiency until Phase 4 lands draft-specific recovery.
- **Adapter is still load-bearing.** The `action_plan → patch_proposal` adapter at `src/mew/work_loop.py:1310-1352` continues to mediate until the prompt swap lands. A future write-ready prompt tweak that changes tool shape must keep matching the adapter, or bundles silently flip to `unadapted` and this slice silently stops firing its new blocker branch (since `unadapted` falls through to original-action dispatch). `artifact_kind="unadapted"` staying distinct from `"patch_blocker"` in metrics makes this diagnosable.
- **Wait-reason text is user-facing.** The `reason` string ends up in session traces and possibly `follow-status` output. Keep it stable across blocker codes (`"patch draft compiler blocker: <code>"`) so it's grep-able by operators; resist the temptation to paraphrase per code.
- **No rollback toggle.** This slice does not add a feature flag; if the compiler turns out to be too strict in practice, rollback requires a code revert. Given the calibration gate is an explicit prerequisite, this is the right tradeoff — but it means the land review must take the calibration-gate pass seriously rather than treating it as a rubber stamp.

## Addendum (2026-04-22): Calibration sample is empty

`./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` currently returns `ok=false` with `errors: ["replay root not found: .mew/replays/work-loop"]`. That is the gate working correctly, not failing — `has_bundles=false` is the only unsatisfied threshold, and it fires because the shadow bridge has written zero bundles since landing.

**This is not a Phase 2.5 trigger.** Phase 2.5 per `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:150-156` is for "model-behavior adjustment, prompt tightening, or contract revision" when the gate fails on a *populated* sample (rates above threshold, or concentration too high, or malformed relevant bundles present). An empty replay root means "we have no measurement yet," not "we measured and the measurement is bad." The proposal's own Risk #3 ("Phase 2/3 calibration always trips") anticipates failing-on-real-data; it does not anticipate absence-of-data.

**Neither is (d) the next slice yet.** The "authoritative blocker-stop" above has the calibration pass as a hard prerequisite (Acceptance criterion 8). That prerequisite is not merely unsatisfied — it is unevaluable. Landing (d) against a zero-bundle sample would be landing it against no evidence at all, which is strictly worse than landing it against evidence the gate rejects (in which case we'd at least know something).

**The next step is a bundle-collection step, not a code slice.** Concretely:

1. Run `mew work <task-id> --ai ...` on one or two bounded real coding tasks — i.e., any task with paired `src/mew/*.py` + `tests/test_*.py` edits where the existing write-ready fast path activates (`_work_write_ready_fast_path_details` returns `active=True`). Each such turn writes a replay bundle at `.mew/replays/work-loop/<date>/session-<id>/todo-<id>/attempt-<n>/`.
2. Re-run the calibration command. Evaluate the four thresholds against the populated sample.
3. Depending on outcome:
   - **Gate passes** → (d) becomes the next code slice as described above.
   - **Gate fails on `off_schema_rate > 5%` or `refusal_rate > 3%`** → Phase 2.5 calibration slice (prompt tightening or contract revision per proposal §3.3).
   - **Gate fails on `failure_mode_concentration > 40%`** with a monoculture of `patch_draft_compiler.other` → sample is too narrow; collect more turns, ideally including at least one write-ready turn the current loop fails on, before deciding.
   - **Bundles still absent after a reasonable collection window** → there is a latent bug in the shadow bridge (helper runs but `write_patch_draft_compiler_replay` is not writing, or the fast path never activates in practice). That becomes the next code slice — a diagnostic one, not (d). In that case, the shadow-bridge exception-isolation test at `tests/test_work_session.py:7039` would be the starting point for investigation since it confirms the helper *can* exercise the writer.

No code change is warranted today. The next reviewer-gated action is operational (collect bundles + evaluate), and this planning note's body stands for what comes after the gate has something to say.

## Addendum 2 (2026-04-22): Bundles populated, but sample is 100% `request_timed_out`

Supersedes both Addendum 1 and the body's (d) recommendation. Collection on task `#402` has produced a populated sample with these characteristics:

- Two bundles, both `work-loop-model-failure.request_timed_out`.
- `compiler_bundles = 0`. The shadow helper never produced a validator_result for either turn.
- `patch_draft_compiler_ran = false` on both turns.
- `prompt_chars ≈ 41–42k`, `active_memory_chars ≈ 13k`, `tool_context_chars ≈ 57k`.

**Interpretation.** This is the `#401` pattern — timeout before the model returns any draft — dominating the live sample. The model never produces output for the shadow helper to compile, so there is no compiler bundle to measure and (d) blocker-stop cannot apply: its fire condition (`artifact_kind == "patch_blocker"`) is unreachable until the model starts returning something. The gate fails on `failure_mode_concentration = 1.0` (100% `work-loop-model-failure.request_timed_out`), which per `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md:150-156` triggers **Phase 2.5 — "model-behavior adjustment, prompt tightening, or contract revision."** The current evidence points squarely at prompt tightening: a ~41k character think prompt plus ~57k of tool context is at or above the model's timeout budget for the current backend.

**Recommendation.** The next slice is a **Phase 2.5 prompt-contract reduction, schema-preserving**, targeted only at the write-ready fast path. Not a schema swap, not a new model call, not (d). Concretely:

- Rewrite the body of `build_work_write_ready_think_prompt` at `src/mew/work_loop.py:1610` so the draft envelope is a bounded stable prefix + a narrow dynamic suffix: stable prefix carries only the schema contract and invariant instructions; dynamic suffix carries only the active `WorkTodo` + the cached windows for its target_paths + any focused verify command. Drop full tool-call history, drop off-path recent file reads, drop instruction boilerplate that is already implied by the schema.
- Keep the **output shape byte-identical**: the model must still emit `{summary, action: {type: "batch", tools: [{"type": "edit_file"/"edit_file_hunks", ...}]}}`. That is what avoids stranding runtime — `normalize_work_model_action` at `src/mew/work_loop.py:2270-2274` keeps parsing the same shape, the adapter at `src/mew/work_loop.py:1310-1352` keeps recognizing the same tool shapes, dispatch is unchanged, and the shadow compiler keeps running against the same adapter input. The compiler's existing `model_returned_non_schema` blocker code is the safety net if the trim accidentally regresses shape compliance.
- Bump `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION` at `src/mew/work_loop.py:64` from `"v1"` to `"v2"` so replay bundles and session traces record which envelope generated them. Calibration rates across the `v1` → `v2` boundary then become directly comparable.

**Why this is the smallest safe shape.**

- **Does not strand runtime.** Output schema unchanged means `normalize_work_model_action`, the adapter, and dispatch all stay on their current contract. Regression surface is only in prompt text.
- **Does not require authoritative dispatch first.** The original reason (a) prompt swap was non-viable was that it changed output shape. A *content* reduction at fixed shape has none of that hazard.
- **Directly addresses the measured failure mode.** Timeouts in the live sample are caused by prompt + context size. Reducing that reduces timeouts; non-timeouts produce compiler bundles; compiler bundles are what the original body (d) plan needs to be reachable.
- **Is exactly what proposal §3.3 names as the Phase 2.5 response.** "Prompt tightening" is the middle term of the three remedies the proposal enumerates. This lands cleanly inside the adopted close-gate scope without reopening it.

**Explicit non-goals for this slice (in addition to the body's non-goals).**

- Do not change the output JSON schema. No `patch_proposal` shape. No `patch_blocker` shape from the model. The adapter stays as-is.
- Do not introduce a separate draft model call. A dedicated tiny-draft RPC (bypass `plan_work_model_turn` for drafting) is a *different* slice, appropriate if (e1) content-reduction does not bring `compiler_bundles` to non-zero.
- Do not touch `build_work_act_prompt`, non-write-ready `build_work_think_prompt`, or any think-prompt surface outside the write-ready fast path. The timeouts observed are write-ready-specific; the fix should be too.
- Do not remove prompt-caching boundaries. Stable prefix stays stable across turns so the backend cache keeps hitting.
- Do not change `build_work_recovery_plan` for timeouts. Timeout recovery stays generic in this slice; draft-specific timeout recovery is Phase 4.
- Do not add a feature flag. The `v1`/`v2` contract-version field on every bundle and turn is sufficient for A/B-style audit after land.

**Files to touch (revised for this slice).**

| File | Change |
| --- | --- |
| `src/mew/work_loop.py` | Rewrite `build_work_write_ready_think_prompt` body at `:1610` — split into stable prefix + dynamic suffix, drop off-path tool context and instruction boilerplate. Bump `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION` at `:64` to `"v2"`. |
| `tests/test_work_session.py` | Update every existing assertion that pins write-ready prompt text (there are several — locate via `grep "build_work_write_ready_think_prompt\|write.*ready.*prompt"` in the test file). Add one new test that asserts the stable prefix is ≤ a documented ceiling (suggest 6k chars) and the dynamic suffix is ≤ a documented ceiling as a function of cached-window count. Add one new test that asserts `model_metrics["draft_prompt_contract_version"] == "v2"` on a write-ready turn. |

No other production files. No test-fixture files.

**Acceptance criteria (revised for this slice).**

1. `build_work_write_ready_think_prompt` emits the same JSON-output-shape instructions as `v1` — a `batch` of `edit_file` / `edit_file_hunks` tool dicts. Not `patch_proposal`, not anything else.
2. The total `prompt_chars` on a representative write-ready turn under the new envelope is materially smaller than the `v1` measurement (target: ≤ 20k on the `#402`-shape task; the stable prefix should be ≤ 6k).
3. `WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION == "v2"` on every write-ready turn and in every shadow bundle written after land.
4. `normalize_work_model_action`, the shadow adapter (`src/mew/work_loop.py:1310-1352`), `compile_patch_draft`, `compile_patch_draft_previews`, `write_patch_draft_compiler_replay`, `build_work_recovery_plan`, `write_tools.py`, and every dispatch/approval/apply path are byte-identical to the pre-slice state.
5. All existing write-ready dispatch tests pass unchanged, modulo the prompt-text assertion updates noted above. No test needs to change its expected `action` shape.
6. After land: a follow-up shadow collection run on the same `#402`-shape task shows `compiler_bundles > 0`. If it still shows `compiler_bundles = 0` (timeouts persist despite the trim), the next slice is a separate tiny-draft model call rather than further prompt-content trimming — escalation, not iteration.
7. The post-land calibration sample should be re-evaluated before Phase 3 authoritative dispatch (d) is reconsidered. The v1-era failure-timeout bundles remain in the sample as archaeological evidence of the pre-`v2` regime and do not contaminate future measurements because `draft_prompt_contract_version` distinguishes them.

**Residual risks.**

- **Over-trimming loses model quality.** If the envelope drops information the model was actually using, write-ready turns will start emitting malformed batches. That shows up as shadow `artifact_kind == "model_returned_non_schema"` blockers, which is *diagnostic success* — it gives us non-zero compiler_bundles and an actionable signal — but until (d) lands, those turns still dispatch their original actions, so dispatch correctness depends on whether the malformed output also fails the existing dispatch path. Likely yes (malformed tools don't dispatch cleanly), but worth an explicit check during land.
- **The `v1` → `v2` change is not toggle-able.** If v2 regresses live behavior below v1, rollback is a code revert. The `draft_prompt_contract_version` stamp on every bundle makes the before/after rate comparison mechanical, but it's not a runtime kill switch.
- **Tool context at 57k is large and probably the real cost driver.** The trim must target tool-context inclusion rules, not just the static instruction text, to get prompt_chars down. A trim that only touches static text while leaving the tool-context builder untouched will not move the needle.
- **Phase 4 recovery is still generic.** A post-v2 timeout still collapses to generic replan. That's unchanged by this slice; this slice only aims to make timeouts less frequent, not to recover from them intelligently.

**Body sections superseded by this addendum.**

- The body's (d) recommendation is deferred until `compiler_bundles > 0` is observed in the live sample. The body's argument that (d) is the smallest safe dispatch-flip still holds; its precondition is not satisfied today.
- Addendum 1's "not Phase 2.5" judgment was correct *at the time of an empty sample* and incorrect *now that the sample is populated with a concentration violation*. This addendum is the Phase 2.5 slice the proposal anticipated.
