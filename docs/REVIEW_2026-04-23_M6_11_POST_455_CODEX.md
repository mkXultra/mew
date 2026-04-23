STATUS: FAIL

COUNTEDNESS: non-counted

LEDGER_ROW:
{"recorded_at":"2026-04-23T10:47:26Z","head":"4cb9bcd","task_id":455,"session_id":439,"attempt":null,"scope_files":["src/mew/patch_draft.py","tests/test_patch_draft.py"],"verifier":"uv run python -m unittest tests.test_patch_draft.PatchDraftTests","counted":false,"non_counted_reason":"PatchDraftTests passed and the model finished by treating existing happy-path preview tests as reviewer-visible paired dry-run evidence, but session #439 produced no replay bundle, no live paired dry-run patch, no source/test diff, and no exact live draft-lane blocker; verifier-only evidence violates task #455 accounting instructions.","blocker_code":null,"reviewer_decision":"rejected_as_no_bundle_verifier_only_false_finish","replay_bundle_path":null,"review_doc":"docs/REVIEW_2026-04-23_M6_11_POST_455_CODEX.md","notes":"Resume shows draft_attempts=0, cached_window_ref_count=0, latest_patch_draft_compiler_replay={}, and only latest_verifier_closeout from tool_call_id=3606. find found no .mew/replays/work-loop/2026-04-23/session-439 directory, and proof-summary still reports current_head.total_bundles=0."}

NEXT_TASK: Implement a bounded finish-gate guard so an M6.11 replay-sample task whose goal requires a fresh replay bundle, reviewer-visible paired dry-run patch, or exact live draft-lane blocker cannot close from `latest_verifier_closeout` alone, then rerun one fresh patch_draft sample after that guard lands.

RATIONALE:

- Task #455 explicitly required one fresh current-head sample after `4cb9bcd` that yielded a replay bundle, reviewer-visible paired dry-run patch, or exact live draft-lane blocker, and explicitly said not to finish from a passing verifier alone.
- Session #439 only read the fenced source/test pair and ran `uv run python -m unittest tests.test_patch_draft.PatchDraftTests`, which passed 20 tests.
- The finish claim relied on existing happy-path preview tests, not a session-produced paired dry-run patch or applied/reviewable source/test diff.
- `./mew work 455 --session --resume --json` shows `draft_attempts=0`, `cached_window_ref_count=0`, `latest_patch_draft_compiler_replay={}`, and no active replay artifact.
- `.mew/replays/work-loop/2026-04-23/session-439` does not exist, and `mew proof-summary .mew/replays/work-loop --m6_11-phase2-calibration --json` still reports `current_head.total_bundles=0`.
- Therefore the session does not count toward Phase 2/3 replay-bundle calibration and does not count toward the 20-slice `#399/#401` incidence gate.
