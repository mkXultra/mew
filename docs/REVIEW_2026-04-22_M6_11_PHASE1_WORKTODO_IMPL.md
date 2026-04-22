# M6.11 Phase 1 WorkTodo Implementation Note

## Scope

- Implemented the smallest persisted `active_work_todo` skeleton in [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py).
- Added focused regression coverage in [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py).
- Did not touch `src/mew/commands.py`.

## What Landed

- Added a persisted `session["active_work_todo"]` shape with stable core fields:
  - `id`
  - `status`
  - `source.plan_item`
  - `source.target_paths`
  - `source.verify_command`
  - `cached_window_refs[*].path|tool_call_id|line_start|line_end|context_truncated|window_sha1`
  - `attempts.draft|review`
  - `patch_draft_id`
  - `blocker`
  - `created_at|updated_at`
- Bound `plan_item_observations[0].edit_ready` to `active_work_todo` creation/update.
- Made resume draft fields prefer persisted `active_work_todo` state when present.
- Made session phase derive from `active_work_todo.status` for the Phase 1 statuses introduced here:
  - `drafting`
  - `blocked_on_patch`
- Kept the change bounded:
  - no `PatchDraftCompiler`
  - no write/apply flow rewrite
  - no prompt contract rewrite

## Review-Driven Corrections

- Stale `active_work_todo` no longer pins resume to an old frontier:
  - if the current first frontier is not `edit_ready`, resume ignores the persisted todo
  - if the frontier key changed and the new frontier is `edit_ready`, the todo is replaced with the new frontier instead of preserving the stale one
- Fresher runtime failure state now beats todo phase in `work_session_phase()`.
- Phase 0 draft observability fields remain populated from the latest write-ready model metrics even when `active_work_todo` exists:
  - `draft_runtime_mode`
  - `draft_prompt_contract_version`
  - `draft_prompt_static_chars`
  - `draft_prompt_dynamic_chars`
  - `draft_retry_same_prefix`
- Reduced resume-time mutation:
  - `build_work_session_resume()` no longer writes normalized/preserved stale todos back into `session`
  - mutation is limited to substantive create/update/replacement of the active frontier
- Added focused tests for:
  - stale frontier ignore
  - stale frontier replacement
  - failure precedence over todo phase
  - repeated-resume idempotence on the same drafting frontier
  - drafting / blocked-on-patch `next_action` and formatter surface

## Changed Files

- [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py)
- [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py)
- [`docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md`](/Users/mk/dev/personal-pj/mew/docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md)

## Validation Commands

```bash
uv run pytest tests/test_work_session.py -k 'build_work_session_resume_surfaces_draft_placeholders or active_work_todo_round_trips_through_session_state or build_work_session_resume_prefers_persisted_active_work_todo or build_work_session_resume_ignores_stale_active_work_todo_when_frontier_is_not_edit_ready or build_work_session_resume_replaces_stale_active_work_todo_on_frontier_change or build_work_session_resume_creates_active_work_todo_for_edit_ready_frontier or work_session_resume_failure_beats_active_work_todo_phase or test_work_session_resume_surfaces_working_memory or test_plan_item_exact_read_window_blocks_edit_ready_until_cached or test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path'
uv run ruff check src/mew/work_session.py tests/test_work_session.py
uv run python -m py_compile src/mew/work_session.py tests/test_work_session.py
git diff --check
```
