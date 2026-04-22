# M6.11 Phase 4 Blocker Persistence Final Re-Review

## Findings

No active findings.

I reviewed the current uncommitted diff in `src/mew/work_loop.py`, `src/mew/work_session.py`, and `tests/test_work_session.py` against `5085ff0`, with focus on the bounded blocker-persistence slice and the prior stale-blocker-to-new-frontier contamination bug.

The current revision resolves the remaining blocker correctly:

- `src/mew/work_loop.py` now threads the active todo identity through the tiny-lane outcome via both `action_plan["todo_id"]` and `action_plan["blocker"]["todo_id"]`.
- `src/mew/work_session.py` now treats that todo id as the correlation key when selecting and replaying tiny-lane outcomes onto `active_work_todo`.
- `_observe_active_work_todo()` only reapplies blocker/success state from a tiny-lane turn whose todo id matches the currently observed todo frontier, which closes the prior stale-blocker-to-new-frontier contamination path.
- The recovery mapping stays disciplined by reusing `PATCH_BLOCKER_RECOVERY_ACTIONS` as the source of truth rather than introducing a second mapping.
- The slice remains bounded: it wires persistence/recovery for the active todo and does not widen into broader follow-status/history refactors.

The added tests are also pointed at the right failure modes, including:

- blocker persistence from tiny-lane turns,
- nested `blocker.todo_id` extraction,
- stable-frontier re-observation,
- success clearing a prior blocker,
- regression coverage for not carrying an old blocker onto a newly created frontier.

Focused verification passed:

- `uv run pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft or stable_frontier or blocker_turn or frontier or todo_id'`
- Result: `20 passed, 459 deselected, 5 subtests passed`

## Residual Follow-Ups

- `./mew work 402 --follow-status --json` still surfaces the older timeout and empty `suggested_recovery`. Based on the current local evidence, that looks like a separate consumer/status-projection gap rather than a blocker for this bounded persistence slice.
- Unknown blocker codes still fall back to `refresh_cached_window`. That is acceptable for this slice, but any future blocker taxonomy expansion should continue to flow from `PATCH_BLOCKER_RECOVERY_ACTIONS`.

## Verdict

Approve.
