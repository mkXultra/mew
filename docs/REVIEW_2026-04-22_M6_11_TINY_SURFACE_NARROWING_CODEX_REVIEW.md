# M6.11 Tiny Surface Narrowing Review (Codex)

## Verdict

Approve. The prior blocking issue is fixed: the tiny write-ready context now replaces stale `active_work_todo.source.plan_item` text with the first actionable `plan_item_observations[0].plan_item`, and the tiny prompt no longer carries the stale surface.

## Findings

No blocking findings in the current slice.

## Assessment

1. Stale `plan_item` leakage is fixed. In [`src/mew/work_loop.py:1838`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1838) to [`src/mew/work_loop.py:1845`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1845), the tiny lane now prefers the actionable observation plan item, and [`src/mew/work_loop.py:1881`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1881) emits that narrowed value into `active_work_todo.source.plan_item`.
2. The regression test now locks the prompt content sufficiently for this slice. [`tests/test_work_session.py:6316`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6316) to [`tests/test_work_session.py:6331`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:6331) assert the narrowed plan item in context, the narrowed target paths, the narrowed cached-window paths, absence of stale plan-item text, presence of the actionable plan-item text, and absence of the stale `src/mew/cli.py` path from the tiny prompt.
3. I did not find anything else that should block landing this as bounded M6.11 progress. The change remains confined to the tiny drafting lane, and adjacent write-ready fallback tests still pass.

## Landing Recommendation

Land now as bounded M6.11 progress.

## Validation Performed

- `uv run python -m unittest tests.test_work_session.WorkSessionTests.test_tiny_write_ready_draft_context_prefers_first_actionable_plan_item_surface`
- `uv run python -m unittest tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_falls_back_to_recent_target_path_windows tests.test_work_session.WorkSessionTests.test_write_ready_fast_path_reports_missing_exact_cached_window_texts_reason tests.test_work_session.WorkSessionTests.test_cached_exact_read_plan_item_is_skipped_for_write_ready_fast_path`
- Direct prompt reproduction with a stale `active_work_todo.source.plan_item` fixture confirmed:
  - actionable plan item present
  - stale plan-item text absent
  - stale `src/mew/cli.py` path absent
