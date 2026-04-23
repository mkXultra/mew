# M6.11 Post-470 Review - Codex

STATUS: PASS

## Attempt 1

COUNTEDNESS: non-counted

- Task `#470` / session `#460` attempt 1 stayed on the exact
  `patch_draft` pair:
  - `src/mew/patch_draft.py:416-451`
  - `tests/test_patch_draft.py:576-603`
- Focused verifier passed.
- The live draft lane emitted a `patch_draft_compiler` replay bundle, but the
  proposal and validator both used a model-authored `patch_blocker` with code
  `insufficient_cached_window_context`.
- Replay metadata therefore marked the sample non-counted with:
  - `model-authored patch_blocker code outside native patch_draft vocabulary`

This is valid replay evidence, but not counted incidence.

## Attempt 2

COUNTEDNESS: counted

- Session `#460` then refreshed the same surface with broader exact windows:
  - `src/mew/patch_draft.py:416-519`
  - `tests/test_patch_draft.py:576-639`
- The next model turn (`#2193`) failed with `request_timed_out`.
- That emitted:
  - `.mew/replays/work-loop/2026-04-23/session-460/todo-no-todo-460/turn-2193/attempt-1/report.json`
- Replay summary fields:
  - `bundle=work-loop-model-failure`
  - `failure.code=request_timed_out`
  - `git_head=e9a13f934f4b86198bd6ce33d50c8373879e2cc7`
  - `calibration_counted=true`
  - `draft_runtime_mode=guarded`
  - `write_ready_fast_path_reason=insufficient_cached_window_context`

## Result

This is the first valid counted current-head bundle on `e9a13f9`.

`mew proof-summary --m6_11-phase2-calibration` now reports:

- `cohort[current_head]: total=1`
- `bundles=work-loop-model-failure.request_timed_out=1`
- `cohort[current_head]_non_counted: total=2`

So the head is no longer empty, but it is still timeout-only and still needs
additional bounded slices before M6.11 can close.
