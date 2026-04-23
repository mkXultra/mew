STATUS: ISSUES

COUNTEDNESS: non_counted

LEDGER_ROW_RECOMMENDATION: {
  "head": "b31ba0b",
  "task_id": 452,
  "session_id": 436,
  "attempt": null,
  "scope_files": ["src/mew/patch_draft.py", "tests/test_patch_draft.py"],
  "verifier": "uv run python -m unittest tests.test_patch_draft.PatchDraftTests",
  "counted": false,
  "non_counted_reason": "PatchDraftTests passed and latest_verifier_closeout was preserved, but after ledger-scope approval the loop re-entered the write-ready tiny-draft lane against stale patch_draft target paths; turns 2057 and 2058 emitted request_timed_out model-failure bundles, then turn 2059 emitted a model-authored missing_exact_cached_window_texts patch_blocker about calibration-ledger closeout text rather than a native source/test compiler defect, so treat #452 as non-counted tiny-draft closeout-misroute evidence.",
  "blocker_code": null,
  "reviewer_decision": "accepted_as_non_counted_tiny_draft_closeout_misroute_evidence",
  "replay_bundle_path": ".mew/replays/work-loop/2026-04-23/session-436/todo-todo-436-1/attempt-1/replay_metadata.json",
  "related_timeout_reports": [
    ".mew/replays/work-loop/2026-04-23/session-436/todo-no-todo-436/turn-2057/attempt-1/report.json",
    ".mew/replays/work-loop/2026-04-23/session-436/todo-no-todo-436/turn-2058/attempt-1/report.json"
  ],
  "review_doc": "docs/REVIEW_2026-04-23_M6_11_POST_452_NEXT_CODEX.md"
}

NEXT_ACTION: Implement a narrow loop fix before taking another sample. The fix should route preserved verifier-closeout / ledger-record plan items to no-change closeout or explicit ledger handling instead of activating the write-ready tiny-draft lane from stale src/test target paths; it should also let reviewer-superseded model-failure reports be excluded from current-head calibration counts. After that, mark all #452 artifacts non-counted and rerun one fresh post-fix patch_draft sample.

FINDINGS:
- High - Reference both timeout reports, not just the second/latest. `turn-2057` and `turn-2058` are separate persisted current-head `work-loop-model-failure.request_timed_out` reports, both with `tiny_write_ready_draft_outcome=fallback`, `tiny_write_ready_draft_fallback_reason=timeout`, `write_ready_fast_path=true`, and `patch_draft_compiler_ran=false`.
- High - This does not show that `b31ba0b` failed. `.mew/follow/session-436.json` preserves `latest_verifier_closeout` for tool call `3578`, model turn `2055`, exit code `0`, and the exact `PatchDraftTests` command; the later failures are a separate tiny write-ready draft / Codex Web API path.
- Medium - The current artifact set also includes `turn-2059` and `.mew/replays/work-loop/2026-04-23/session-436/todo-todo-436-1/attempt-1/replay_metadata.json`. That replay is currently stamped `calibration_counted=true`, but its blocker text is about missing calibration-ledger closeout context while the todo target paths remain the patch_draft src/test pair, so it should be reviewer-excluded.
- Medium - `src/mew/proof_summary.py` currently counts every `report.json` model-failure bundle; a ledger-only non-counted row will not remove the two timeout reports from current-head proof-summary without an artifact/accounting fix.
