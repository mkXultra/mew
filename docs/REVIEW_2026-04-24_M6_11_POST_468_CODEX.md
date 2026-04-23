# M6.11 Post-468 Review — Codex

Date: 2026-04-24
HEAD: `e9a13f9`

decision: non-counted
summary: Task `#468` / session `#458` produced a fresh current-head
`patch_draft_compiler` replay bundle on `e9a13f9`, but the proposed paired
dry-run patch is off-target and must be reviewer-rejected. The patch invents
absolute-path cached-window fallback behavior not justified by the observed
`missing_exact_cached_window_texts` source/test window, and the proposed test
asserts the wrong artifact kind (`patch_proposal` instead of `patch_draft`).
The replay should be kept as current-head non-counted evidence, not counted
incidence.

## Findings

- The live run reached exact paired cached windows:
  - `src/mew/patch_draft.py:416-451`
  - `tests/test_patch_draft.py:576-603`
- The focused verifier passed:
  `uv run python -m unittest tests.test_patch_draft.PatchDraftTests.test_compile_patch_draft_blocks_missing_exact_cached_window_texts`
- The tiny write-ready draft lane emitted a replay bundle at:
  `.mew/replays/work-loop/2026-04-23/session-458/todo-todo-458-1/attempt-1/replay_metadata.json`
- The proposed source edit adds an absolute-path suffix fallback when no exact
  cached-window key matches `proposal_file["path"]`.
- The proposed test is not credible evidence for the scoped defect:
  - it introduces an absolute workspace path into `cached_windows`
  - it asserts `artifact["kind"] == "patch_proposal"`, but
    `compile_patch_draft(...)` returns `patch_draft` or `patch_blocker`
- That makes the dry-run patch off-target relative to the actual anchored
  blocker contract, which is still the existing
  `missing_exact_cached_window_texts` path.

## Decision

Reject both dry-run edits and mark the replay non-counted with the same
rejection reason.

Why:

- the patch is not supported by the observed scoped source/test windows
- the proposed test expectation is invalid on its face
- counting this sample would inflate current-head calibration with a reviewer-
  rejected behavior invention instead of an honest incidence signal

## Resulting State

- `replay_metadata.json` is backfilled to:
  - `calibration_counted=false`
  - `calibration_exclusion_reason=<review rejection reason>`
- `mew proof-summary --m6_11-phase2-calibration` now reports:
  - `cohort[current_head]: total=0`
  - `cohort[current_head]_non_counted: total=1`

## Next Action

- Keep M6.11 open.
- Do not retry the same off-target patch_draft shape on `e9a13f9`.
- Take another fresh current-head sample on a surface that can emit either:
  - a justified native blocker / replay bundle, or
  - a model-failure bundle
  without inventing new product behavior.
