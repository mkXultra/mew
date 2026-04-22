# M6.11 Post-Phase4 Follow-Status Parity Review

## Findings

- Medium: equal-timestamp overlay does not actually recognize richer live continuity for real resume data. `src/mew/commands.py:6580-6620` only treats `continuity.score` as an `int`, but the real source of truth emits `"passed/total"` strings such as `"9/9"` in `src/mew/work_session.py:3961-3965`. I confirmed the mismatch directly: `_work_follow_status_continuity_score({"score": "9/9"})` returns `None`, while `build_work_continuity_score(... )["score"]` returns `"9/9"`. That means the new equal-timestamp overlay heuristic will not choose the live resume when continuity is the only richer signal. The added test at `tests/test_work_session.py:24822-24872` passes only because it patches non-production integer scores (`9` and `1`) instead of the real `"9/9"` style payload.

## Open Questions

- `src/mew/commands.py:6848-6850` switches `pending_approval_count` to `len((session or {}).get("pending_approvals") or [])` when overlay is chosen. I did not see `pending_approvals` persisted on the raw session object elsewhere in this diff, only on the resume/snapshot surface, so this looks worth validating with an overlay-path test before approval.

## Verdict

`revise` — the main blocker/recovery overlay behavior looks on-scope and the focused tests pass, but the new continuity-based richness path is not correct against the repo’s real continuity shape, so the slice is not fully implemented as claimed.

## Verification

- Reviewed the current uncommitted diff directly in `src/mew/commands.py` and `tests/test_work_session.py`.
- Ran `uv run pytest -q tests/test_work_session.py -k 'work_follow_status and (overlay or blocker_resume or human_output_includes_active_work_todo_and_next_recovery_action or marks_session_state_newer_than_snapshot or prefers_snapshot_recovery_plan or omits_draft_placeholders_for_non_draft_failure or reports_fresh_snapshot_when_producer_alive)'`
- Result: `9 passed, 475 deselected`
