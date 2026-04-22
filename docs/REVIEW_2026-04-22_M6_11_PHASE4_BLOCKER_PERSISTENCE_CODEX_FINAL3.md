# M6.11 Phase 4 Blocker Persistence Review (Codex, Final 3)

## Findings

No active findings.

The prior stale-blocker-to-new-frontier contamination issue is resolved in the actual code:

- `src/mew/work_loop.py` now threads the active todo identity into tiny-lane `action_plan` payloads via `todo_id` on both blocker and success paths ([`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:714), [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1696), [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1725), [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:1787)).
- `src/mew/work_session.py` now extracts that identity with `_tiny_write_ready_draft_turn_todo_id(...)`, filters `_latest_tiny_write_ready_draft_turn(..., todo_id=...)`, and refuses to apply a tiny-lane outcome to a todo unless the turn’s todo id matches the current todo id ([`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:55), [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:104), [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:121), [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4726), [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4767), [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:5260)).
- The revised regression in `tests/test_work_session.py` now pins the formerly-buggy frontier-change case by asserting that a newly created todo `todo-1-2` does **not** inherit the old blocker from `todo-1-1` ([`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:8773)).

That is the right bounded fix for the source-of-truth problem in this slice.

## Residual Non-Blocking Risks

- The supplied local evidence says `./mew work 402 --session --resume --allow-read . --json` now shows the intended `blocked_on_patch` state, populated blocker, non-empty `recovery_plan`, and continuity `9/9`. That supports the stable-frontier path.
- `./mew work 402 --follow-status --json` still reporting the stale older timeout with empty `suggested_recovery` remains a follow-up consumer/snapshot gap. I do not see a blocker in this patch that requires widening the current slice to fix it.
- Unknown blocker codes still conservatively fall back to `refresh_cached_window`. That is acceptable for this bounded persistence slice, but if the blocker vocabulary expands later, the follow-status/recovery consumer should tighten unknown-code handling separately.

## Verification

Ran focused tests:

```bash
uv run pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft or stable_frontier or blocker_turn or frontier'
```

Result: `19 passed`, plus `5` passing subtests.

## Verdict

**Approve.**

This revision resolves the blocker contamination bug, keeps the change bounded to the Phase 4 persistence/recovery surface, and does not introduce any new blocker-level correctness issues in the reviewed diff.
