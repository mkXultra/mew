# M6.11 Post-Phase4 Follow-Status Parity Review 2

## Findings

- Medium: the overlay path still drops live pending approvals and reports `pending_approval_count=0` from the raw session object instead of the overlaid live resume. In `src/mew/commands.py:6866-6868`, the count switches to `len((session or {}).get("pending_approvals") or [])` when `use_session_overlay` is true, but the same function already treats `effective_resume` as the source of truth for `next_action`, `continuity`, `active_work_todo`, `blocker_code`, and `next_recovery_action` at `src/mew/commands.py:6852-6863`. I reproduced this directly by patching `build_work_session_resume()` to return a live overlaid resume with one pending approval: the command returned `resume_source=session_overlay` and `pending_approval_count=0`. The new follow-status tests in `tests/test_work_session.py:24690-25061` cover blocker/recovery/continuity/latest-failure overlay behavior, but they still do not cover overlay plus live pending approvals.

## Verdict

`revise` — the continuity-score bug is fixed and the targeted follow-status tests now pass, but the patch still has one remaining overlay correctness bug, so it is not yet approvable.

## Verification

- Reviewed the current uncommitted diff directly in `src/mew/commands.py` and `tests/test_work_session.py`.
- Ran `uv run pytest -q tests/test_work_session.py -k 'work_follow_status and (overlay or blocker_resume or human_output_includes_active_work_todo_and_next_recovery_action or marks_session_state_newer_than_snapshot or keeps_snapshot_when_fresher_than_live_session or prefers_snapshot_recovery_plan or omits_draft_placeholders_for_non_draft_failure or reports_fresh_snapshot_when_producer_alive)'`
- Result: `10 passed, 475 deselected`
