# M6.11 Post-451 Wait Review - Codex

Date: 2026-04-23  
HEAD: `aa31cdc`

## Verdict

Classify the initial finish-to-wait conversion as a **healthy guardrail outcome**, but the continued inability to close after an exact verifier rerun as a **narrow product-loop closeout bug**. It is not a `patch_draft.py` measurement-path bug.

The guardrail did the right thing when `#451` tried to finish from cached-window no-change reasoning with no current-head replay bundle and no recognized current-turn closeout. That should not become counted M6.11 evidence.

The bug is that the closeout recognizer is too narrow for the real `#451` shape. `_write_ready_fast_path_verifier_closeout_passed(...)` requires the latest verifier model turn to have `write_ready_fast_path_reason == "insufficient_cached_window_context"`. In session `#435`, the exact closeout verifier was rerun and passed as tool `#3573`, but that verifier turn carried `write_ready_fast_path_reason == "missing_plan_item_observations"`. With the current predicate, the loop can keep blocking `finish` even after doing the requested closeout verifier.

## Next Safe Action

Do not change `src/mew/patch_draft.py` or `tests/test_patch_draft.py`; the scoped verifier already passes and there is no concrete source/test defect.

Do not count `#451` as a current-head compiler replay bundle. If no fix is made, record it only as non-counted guardrail/no-bundle evidence.

Preferred next action: implement a narrow closeout-recognition fix, then let `#451` finish with the scoped no-change conclusion using the already-passed exact verifier. Ledger disposition after that should still be non-counted no-change closeout evidence, not a counted replay bundle.

## Minimal Fix

Likely files:

- `src/mew/work_loop.py`
- `tests/test_work_session.py`

Narrow fix shape:

- In `_write_ready_fast_path_verifier_closeout_passed(...)`, keep the existing hard checks: active todo is `drafting`, verifier command matches the active todo, latest completed tool call is `run_tests`, exit code is passing, model-turn/tool-call IDs match, and target paths match.
- Broaden only the fast-path reason accepted for a verifier closeout to include the observed `missing_plan_item_observations` closeout shape, or otherwise remove that reason as a decisive closeout blocker once the stricter command/tool/path checks pass.
- Do not treat any stale earlier passing verifier as closeout evidence.

Acceptance criteria:

- Add a regression that reproduces `#451`: measured current-head `patch_draft` task, drafting todo on `src/mew/patch_draft.py` + `tests/test_patch_draft.py`, latest `run_tests` turn/tool call passes `uv run python -m unittest tests.test_patch_draft.PatchDraftTests`, and the turn has `write_ready_fast_path_reason="missing_plan_item_observations"`; a no-change `finish` is allowed.
- Existing blocker tests still pass: no verifier/replay still converts finish to `wait`; failed, mismatched-command, and mismatched-target verifier turns still do not allow finish.
- Focused verifier: `uv run pytest tests/test_work_session.py -q -k 'calibration_measured_patch_draft_finish or verifier_closeout'`.
