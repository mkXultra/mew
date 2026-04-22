# Review

Status: **commit-ready**

## Findings

- No blocking findings.

## Rationale

- The promoted branch in [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1686) is correctly gated: only compiler results with `kind == "patch_blocker"`, a non-empty `code`, and `code != "model_returned_non_schema"` are upgraded to `status="blocker"`. The existing fallback path remains unchanged for malformed/non-schema output.
- The generic THINK path is truly skipped. The caller already returns early for any non-`fallback` tiny result at [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:2776), so the new `status="blocker"` return is sufficient by itself. The new caller-level test at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7605) proves this by failing on any second model call, asserting only one model invocation, and pinning `model_metrics["think"]["timeout_seconds"]` to the tiny-lane timeout rather than the generic 90 s path.
- The tests cover the promoted branch well. The helper-level branch is pinned at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7301), and the caller-level early-return behavior is pinned at [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7605).
- The non-promotion case is also covered for the new logic. [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7377) proves `model_returned_non_schema` stays on `status="fallback"` with `exit_stage="compiler_fallback"` instead of being promoted. That is the only new decision boundary this diff introduces; caller-side fallback handling is pre-existing shared behavior.

## Bounded Files

- [src/mew/work_loop.py](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1686)
- [tests/test_work_session.py](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:7301)

## Verification

- `uv run python -m pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft'` -> `9 passed`
- `uv run python -m pytest -q tests/test_work_session.py` -> `461 passed, 10 deselected, 19 subtests passed`
