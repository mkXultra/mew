# M6.11 Post-Phase4 Follow-Status Parity Review 4

## Findings

No active findings.

The current uncommitted diff is now approvable for the bounded follow-status parity slice:

- `src/mew/commands.py` now overlays fresher or equal-timestamp-but-richer live resume state onto stale follow snapshots.
- `blocker_code`, `active_work_todo`, `pending_approval_count`, and `latest_model_failure` are sourced consistently from the overlaid live resume/session path when overlay is chosen.
- `next_recovery_action` is now aligned to the bounded blocker slice intent via `_work_follow_status_next_recovery_action()`: it prefers the active blocker’s canonical `recovery_action`, and only falls back to a recovery-plan item action when the blocker does not provide one.

Live local evidence for task `#402` matches the intended outcome of this slice:

- `./mew work 402 --follow-status --json` returned `resume_source=session_overlay`.
- It surfaced `phase=blocked_on_patch`, populated `active_work_todo`, `blocker_code=insufficient_cached_context`, and `next_recovery_action=refresh_cached_window`.
- It also preferred the live session failure as `latest_model_failure.source=session` and exposed a concrete recovery command via `suggested_recovery`.

That is the bounded Phase 4 parity goal: follow-status now reflects the live blocked frontier and recovery surface instead of the older stale timeout snapshot.

## Verdict

`approve`

## Verification

- Reviewed the current uncommitted diff directly in `src/mew/commands.py` and `tests/test_work_session.py`.
- Ran `./mew work 402 --follow-status --json` and verified the overlaid blocked-frontier fields listed above.
- Ran `uv run pytest -q tests/test_work_session.py -k 'work_follow_status and (overlay or blocker_resume or human_output_includes_active_work_todo_and_next_recovery_action or overlay_uses_effective_resume_pending_approval_count or keeps_snapshot_when_fresher_than_live_session or marks_session_state_newer_than_snapshot or prefers_snapshot_recovery_plan or omits_draft_placeholders_for_non_draft_failure or reports_fresh_snapshot_when_producer_alive)'`
- Result: `11 passed, 475 deselected`
