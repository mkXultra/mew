# M6.11 Phase 4 Blocker Persistence — Final Review 4 (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `5085ff0`:

- `src/mew/work_loop.py` (+40 lines, +12 since FINAL2)
- `src/mew/work_session.py` (+280 lines, +61 since FINAL2)
- `tests/test_work_session.py` (+545 lines, +103 since FINAL2)

The delta since FINAL2 is focused: tiny-lane turns now carry a
`todo_id` linkage so resume-time derivation only applies an outcome to
the todo it was produced against.

## What changed since FINAL2

### Turn ↔ todo linkage is now explicit

`src/mew/work_loop.py`:

- `_attempt_write_ready_tiny_draft_turn` captures
  `tiny_write_ready_todo_id` from `context["active_work_todo"]["id"]` at
  turn start and stamps `action_plan["todo_id"]` in all three tiny-lane
  exit branches (model-direct blocker, compiler blocker, success
  preview) when non-empty.
- `_work_loop_tiny_write_ready_draft_blocker_payload` now also
  propagates `validator_result["todo_id"]` into
  `action_plan["blocker"]["todo_id"]`. This matches the shape that
  `patch_draft.build_patch_blocker` already emits, so the validator's
  own todo linkage survives into the persisted blocker object.

`src/mew/work_session.py`:

- New `_tiny_write_ready_draft_turn_todo_id(...)` reads the todo_id from
  `action_plan.todo_id`, `action.todo_id`, or `decision_plan.todo_id`,
  falling back to the nested `<candidate>.blocker.todo_id` if the top
  level is absent — this is the specific fix for the validator-emitted
  shape.
- `_latest_tiny_write_ready_draft_turn(model_turns, *, todo_id=None)`
  now filters turns to only those matching the given `todo_id`.
- `_tiny_write_ready_draft_turn_matches_todo(turn, *, todo_id)` guards
  `_apply_tiny_write_ready_draft_outcome_to_active_work_todo` so a turn
  issued against a different todo cannot flip a later todo.
- Every call site in `_observe_active_work_todo` and
  `build_work_session_resume` now threads the active todo id through to
  the latest-turn lookup and the outcome-apply helper.

### New regression test

- `test_build_work_session_resume_blocks_on_nested_blocker_todo_id`
  reproduces the `#402` live shape: `action_plan.blocker.todo_id =
  "todo-392-1"` (nested, no top-level `action_plan.todo_id`) with
  `session.id = 392`. The test asserts `phase=blocked_on_patch`, todo
  `id=todo-392-1`, blocker code/detail preserved, and continuity `9/9`.

This is the fix the review brief refers to as "nested blocker.todo_id."

## Correctness assessment

The todo_id filter is the right guard. Without it,
`_latest_tiny_write_ready_draft_turn` would return the most recent tiny
turn *regardless of todo frontier* — so if the frontier key changed
(e.g. user shifted targets) and a new todo `todo-1-2` was minted, a
stale `todo-1-1` blocker turn could re-flip the new todo into
`blocked_on_patch` with the wrong blocker. That latent bug is now
closed.

Two additional correctness points I checked by tracing the new code:

1. **First-iteration timing.** When `_observe_active_work_todo` mints a
   fresh todo id in its new-todo or frontier-changed branch, no earlier
   turn could have carried that fresh id. The filtered
   `_latest_tiny_write_ready_draft_turn` returns `{}`, the apply helper
   short-circuits, and the newly minted todo keeps `status=drafting`
   with `blocker={}`. That is the desired behaviour — we do not want
   an old todo's blocker attached to a brand-new frontier. The blocker
   flip only fires on the *next* resume after the turn runs, which is
   exactly how the live #402 session reached `phase=blocked_on_patch`.
2. **Dual-source todo_id resolution.** Work_loop.py stamps
   `action_plan.todo_id` at the top level when the session already has
   an active todo, and
   `_work_loop_tiny_write_ready_draft_blocker_payload` also copies the
   validator-emitted `todo_id` into the nested blocker dict. The
   reader helper walks top-level candidates first, then falls back to
   `<candidate>.blocker.todo_id`. Either source alone is sufficient,
   and both paths have coverage
   (`test_build_work_session_resume_blocks_on_latest_tiny_blocker_turn`
   exercises top-level, the new nested test exercises the fallback).

## Prior findings — resolution re-check

- HIGH recovery-map contradiction → resolved in FINAL via
  `patch_draft.PATCH_BLOCKER_RECOVERY_ACTIONS`; unchanged here.
- MEDIUM reason-string coupling → resolved; unchanged here.
- LOW partial map → resolved; unchanged here.
- LOW stable-frontier re-observation coverage → resolved; unchanged.
- LOW attempt-counter semantics → resolved; unchanged.
- LOW (FINAL2) wrong-todo application risk → **newly resolved** by the
  `todo_id` filter.

## Findings on this revision

No active blocker-severity findings.

### 1. LOW (residual from FINAL2) — Persisted-todo test still asserts 8/9

`test_build_work_session_resume_prefers_persisted_active_work_todo`
continues to claim `continuity.score == "8/9"` with
`missing == ["risks_preserved"]`. That fixture has a persisted
`blocked_on_patch` todo but no turn carrying
`tiny_write_ready_draft_outcome`, so
`_latest_tiny_write_ready_draft_turn` returns `{}` and the recovery
item's `model_turn_id` falls through to
`session.get("last_model_turn_id")`, which the synthetic fixture also
omits. `_continuity_recovery_item_visible` requires a non-None
tool_call_id or model_turn_id, so the item is dropped and
`risks_preserved` fails. In live sessions `last_model_turn_id` is set
by `start_work_model_turn` (`src/mew/work_session.py:1489`), so this
does not reproduce on #402. Fixture-only degradation. Optional
one-line mitigation: fall back to `f"todo:{todo['id']}"` when neither
turn id is present. Non-blocking.

### 2. LOW — Recovery item `reason` text still does not match resume `next_action` text

`_tiny_write_ready_draft_recovery_plan_item.reason` builds
`"tiny draft blocker <code>; <detail>"`, while
`build_work_session_resume` produces `"inspect the active patch
blocker and refresh the exact cached windows or todo source before
retrying"`. Both surfaces are user-facing. Runnability is satisfied by
the item's `hint` field matching `_continuity_text_has_command_control`.
Cosmetic only; not a regression from FINAL2.

### 3. LOW — `hint` and `review_hint` carry the same command

Unchanged from FINAL2. Harmless duplication. Later, `review_hint` can
stay as the human-review command while `hint` adopts a distinct
`--auto-recover-safe` retry command once such a thing exists.

## Residual, non-blocking follow-ups

1. **Follow-status stale-timeout gap (explicitly deferred by the
   user).** `./mew work 402 --follow-status --json` still reports the
   older `request_timed_out` with empty `suggested_recovery`. The merge
   at `src/mew/commands.py:6616` does not yet prefer newer
   session-derived state over a stale snapshot turn. Pure follow-up
   slice; does not affect the resume path this slice targets.
2. **Validator codes outside the frozen taxonomy** (e.g.
   `insufficient_cached_context` observed on #402 attempt-4). The
   tiny-lane falls back to `refresh_cached_window`. Either tighten the
   validator or grow the taxonomy. Out of scope.
3. **Recovery item turn-id fallback** (finding 1 above).
4. **Recovery item phrasing / hint duplication** (findings 2, 3).
5. **Phase-5 review-lane helper location.** The tiny-lane outcome-apply
   helper is scoped to `{blocker, succeeded}` outcomes; when the
   review lane lands it should add its own helper rather than extend
   this one.

## Bounding check

- Files touched: 3 (plan-matching). ✓
- No change to `commands.py`, `write_tools.py`, prompts, or
  `patch_draft.py` semantics beyond reading its existing taxonomy. ✓
- No new top-level resume fields; uses existing `active_work_todo` +
  `recovery_plan` surfaces. ✓
- `active_work_todo.status` remains the canonical source of truth;
  phase derivation via `work_session_phase` unchanged. ✓
- Phase 5/6 territory untouched (no review lane, no executor lifecycle
  states, no new recovery-plan item source beyond the tiny-lane
  specific one). ✓
- Recovery-plan wiring stays inside Phase 4 scope
  (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:836-847`). ✓

## Live evidence reconciliation

- `./mew work 402 --session --resume --allow-read . --json` reports
  `phase=blocked_on_patch`, populated blocker, non-empty
  `recovery_plan`, continuity `9/9`. Matches the slice's goal. ✓
- `./mew work 402 --follow-status --json` still reports stale timeout
  with empty `suggested_recovery`. Treated as a deferred follow-up
  slice per the review brief — not a blocker for this slice.

## Verdict

**Approve.**

The nested `blocker.todo_id` fix closes the last correctness concern
surfaced during FINAL2 review (wrong-todo application risk). All prior
blocker-severity findings remain resolved. The resume path produces the
target `blocked_on_patch` / populated-blocker / non-empty
`recovery_plan` / continuity `9/9` live on #402. The slice stays inside
the bounds set at the start: three files, no prompt or validator
semantic changes, no new top-level resume fields, canonical source of
truth preserved, Phase 5/6 territory untouched.

Residual items above are cosmetic, fixture-only artifacts, or explicit
follow-up slices (notably the follow-status stale-timeout gap the user
already acknowledged). None of them should block landing.
