Decision: approve

Summary:
This revision closes the blocker from the prior review. The write-ready fast-path preflight in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1276) now fails closed not only for truncated or delimiter-broken windows, but also for orphaned leading-indented body fragments and clause-tail fragments before tiny-draft activation. The corresponding tests in [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6783) cover the previously missing fragment shapes, and the slice looks safe to land as a narrow M6.11 completeness guard.

Findings:
No blocking findings.

Non-blocking risks:
The heuristic is still intentionally syntactic and conservative rather than a full parser-backed proof of semantic sufficiency. That means it may still allow some top-level but context-poor windows, or reject some unusual but technically usable fragments. For this slice, that tradeoff is acceptable: the goal is to stop obviously under-scoped cached windows from activating `write_ready_fast_path`, and the current checks do that without disturbing the existing write-ready happy path in test coverage.

Verification judgment:
- `uv run python -m unittest tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_falls_back_to_recent_target_path_windows tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_reports_missing_exact_cached_window_texts_reason tests.test_work_session.WorkSessionTests.test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_unfinished_source_block_window tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_test_window_with_unmatched_open_paren tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_orphaned_leading_indented_body_fragment tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_clause_tail_fragment tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_blocks_source_window_starting_mid_fragment` passes.
- `uv run python -m unittest tests.test_work_session` passes.
- `uv run pytest -q tests/test_dogfood.py -k 'm6_11_compiler_replay' --no-testmon` passes.
- Direct helper probes confirm the revised guard now rejects `"    return foo\\n"` and `"else:\\n    x = 1\\n"` while still accepting ordinary complete snippets such as `"value = compute_value()\\n"` and `"def f():\\n    return 1\\n"`.

Concrete next action:
Land this slice as-is. After that, move back to live-current-head measurement or the next M6.11 guard only if a new replay shows a different false-positive write-ready activation class. No further revision is needed on `src/mew/work_loop.py` and `tests/test_work_session.py` before landing this preflight completeness change.
