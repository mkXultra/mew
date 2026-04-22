# M6.11 Patch Draft Path Canonicalization Review

## 1. Verdict

`approve`

## 2. Findings

No blocking findings in the current scoped diff.

The source change in [`src/mew/work_loop.py:1346`](</Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1346>)-[`1364`](</Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1364>) remains the right bounded repair for the malformed cached-window paths, and the added paired regression in [`tests/test_work_loop_patch_draft.py:98`](</Users/mk/dev/personal-pj/mew/tests/test_work_loop_patch_draft.py:98>)-[`163`](</Users/mk/dev/personal-pj/mew/tests/test_work_loop_patch_draft.py:163>) now covers the missing replay-style proof from the previous review.

## 3. Does The Fix Match The Actual Replay Root Cause?

Yes.

The root cause described for `session-402` was a key mismatch inside `_write_ready_patch_draft_environment()`: repo-relative todo target paths were being compared against cached-window keys like `Users/mk/dev/.../tests/test_dogfood.py`, so `compile_patch_draft()` could not find an exact window bundle and returned `missing_exact_cached_window_texts` for `tests/test_dogfood.py`.

The change in [`src/mew/work_loop.py:1346`](</Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1346>)-[`1364`](</Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1364>) fixes that exact mismatch by stripping the current working tree prefix from cwd-rooted malformed paths before building `todo`, `cached_windows`, and `live_files`.

I also replayed the saved bundle at `.mew/replays/work-loop/2026-04-22/session-402/todo-todo-402-1/attempt-1/` through the current helper. The malformed cached-window keys normalized back to:

- `src/mew/dogfood.py`
- `tests/test_dogfood.py`

With those normalized keys, `compile_patch_draft()` returned `kind="patch_draft"` instead of the recorded blocker `code="missing_exact_cached_window_texts"`.

## 4. Are The New Tests Sufficient Before Commit?

Yes.

The new paired regression is sufficient for the stated `session-402` root cause.

[`tests/test_work_loop_patch_draft.py:98`](</Users/mk/dev/personal-pj/mew/tests/test_work_loop_patch_draft.py:98>)-[`163`](</Users/mk/dev/personal-pj/mew/tests/test_work_loop_patch_draft.py:163>) now exercises the key mixed shape that mattered:

- repo-relative todo target paths
- paired `src/mew/dogfood.py` + `tests/test_dogfood.py` recent windows
- malformed cwd-rooted absolute window paths missing the leading slash
- end-to-end `compile_patch_draft()` success instead of `missing_exact_cached_window_texts`

That is the right automated guard for this bounded fix.

## 5. Remaining Blocker Before Commit

None in the reviewed scope.

If follow-up hardening is desired later, the next adjacent cases would be outside-cwd absolute paths and Windows-style backslash variants, but those are not blockers for this `session-402` fix.

## Verification

Ran:

- `PYTHONPATH=src python3 -m unittest tests.test_work_loop_patch_draft tests.test_patch_draft`
- `PYTHONPATH=src python3 -m unittest tests.test_work_loop_patch_draft`
- A local replay probe using `.mew/replays/work-loop/2026-04-22/session-402/todo-todo-402-1/attempt-1/` to feed the recorded malformed cached windows back through `_write_ready_patch_draft_environment()` and `compile_patch_draft()`
