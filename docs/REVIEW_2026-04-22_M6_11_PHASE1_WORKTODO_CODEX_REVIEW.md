# M6.11 Phase 1 WorkTodo Codex Review

## Findings

No active findings in the scoped files. The two findings from the prior Codex review are resolved.

## Resolved Prior Findings

1. Resolved: stale `active_work_todo` no longer pins resume to an obsolete frontier
   - Code path: [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4440), [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4479), [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4532)
   - `_build_active_work_todo_candidate()` now yields a candidate only when the current first observation is actually `edit_ready`. If there is no current candidate, `_observe_active_work_todo()` returns `{}` for resume instead of preserving the stale persisted todo as the live frontier. If there is a newer `edit_ready` frontier with a different `(plan_item, target_paths)` key, `_observe_active_work_todo()` replaces the persisted todo with a new one.
   - Regression coverage: [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7055), [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7111), [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7190)

2. Resolved: fresher tool failure state now beats todo phase
   - Code path: [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:3896)
   - `work_session_phase()` now returns `failed` before consulting `active_work_todo.status`, so a latest failed tool call is no longer masked by `drafting` or `blocked_on_patch`. Resume can still surface the todo-backed draft metadata separately, but the session phase and `next_action` now point at the failure first.
   - Regression coverage: [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7260)

## Residual Risks / Test Gaps

- Review scope was limited to [src/mew/work_session.py](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py), [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py), and [docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md](/Users/mk/dev/personal-pj/mew/docs/REVIEW_2026-04-22_M6_11_PHASE1_WORKTODO_IMPL.md).
- The new coverage is unit-focused. There is persistence round-trip coverage for storing `active_work_todo`, but there is still no end-to-end persisted-session resume test that reloads a stale todo from disk and then exercises the stale-frontier replacement or failure-precedence paths through the CLI/session boundary.
- Phase 1 only exercises the `drafting` and `blocked_on_patch` todo phases in resume logic. The broader `WORK_TODO_STATUSES` set is present in code, but the additional statuses are not meaningfully exercised in this slice.

## Validation

- `uv run pytest tests/test_work_session.py -k 'build_work_session_resume_ignores_stale_active_work_todo_when_frontier_is_not_edit_ready or build_work_session_resume_replaces_stale_active_work_todo_on_frontier_change or work_session_resume_failure_beats_active_work_todo_phase or build_work_session_resume_creates_active_work_todo_for_edit_ready_frontier or build_work_session_resume_prefers_persisted_active_work_todo'` -> `5 passed, 443 deselected`
- `uv run ruff check src/mew/work_session.py tests/test_work_session.py`
- `uv run python -m py_compile src/mew/work_session.py tests/test_work_session.py`
