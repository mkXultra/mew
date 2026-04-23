# M6.11 Post-466 Countedness Review — Codex

Date: 2026-04-24
HEAD: `395f9b4`

decision: counted
summary: Task `#466` / session `#456` produced honest current-head calibration
evidence on `395f9b4`: after exact non-truncated paired cached windows on
`src/mew/patch_draft.py` + `tests/test_patch_draft.py` became edit-ready, the
next live turn emitted a counted `work-loop-model-failure.request_timed_out`
bundle at `.mew/replays/work-loop/2026-04-23/session-456/todo-no-todo-456/turn-2173/attempt-1/report.json`.
This is fresh current-head evidence after the guidance-aware finish-gate fix.
It does not close M6.11 because the current-head cohort is now `1/1`
timeout-dominant, not stable.

## Findings

- The replay bundle exists on disk at:
  `.mew/replays/work-loop/2026-04-23/session-456/todo-no-todo-456/turn-2173/attempt-1/report.json`.
- That report stamps `git_head=395f9b4ef6dff3850f7e9a9c84a10e547d611e1b`,
  `bundle=work-loop-model-failure`, `failure.code=request_timed_out`,
  `failure.kind=timeout`, and `calibration_counted=true`.
- The saved `active_work_todo` is the intended scoped pair:
  `src/mew/patch_draft.py` + `tests/test_patch_draft.py`.
- The saved cached windows are exact and non-truncated:
  - `src/mew/patch_draft.py:416-451`
  - `tests/test_patch_draft.py:576-603`
- `plan_item_observations[0].edit_ready=true`, so this is no longer the older
  "never reached exact paired windows" failure shape.
- The failed live turn still records
  `write_ready_fast_path=false` with
  `write_ready_fast_path_reason="missing_exact_cached_window_texts"`.
- `./mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration`
  now reports:
  - `cohort[current_head]: total=1`
  - `bundles=work-loop-model-failure.request_timed_out=1`
  - `share=1.0000`

## Decision

Count this sample.

Why:

- it emitted a same-session replay artifact on the active head
- it stayed inside the declared scoped pair
- it reached exact edit-ready cached windows before failing
- the stop condition is the saved replay/model-failure artifact itself, not a
  verifier-only finish or a reviewer-invented relabel

Do not relabel this as a native `patch_draft` blocker. The honest current-head
signal is "exact paired cached windows reached, then the live turn timed out."

## Next Action

- Append a canonical ledger row for `#466`.
- Keep M6.11 open.
- Continue the bounded current-head incidence gate with another distinct
  current-head sample so the cohort is not a single timeout point.
- Do not widen scope into new substrate work from this sample alone.
