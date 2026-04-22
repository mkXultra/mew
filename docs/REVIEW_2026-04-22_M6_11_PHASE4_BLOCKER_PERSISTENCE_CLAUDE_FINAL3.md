# M6.11 Phase 4 Blocker Persistence — Final Review 3 (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `5085ff0`, after the frontier-identity
guard fix:

- `src/mew/work_loop.py` (+40 lines): captures
  `tiny_write_ready_todo_id` from `context["active_work_todo"]["id"]`
  at the start of `_attempt_write_ready_tiny_draft_turn`, and stamps
  `action_plan["todo_id"] = tiny_write_ready_todo_id` in both blocker
  branches and the success branch. The blocker payload builder also
  now carries `todo_id` through from `validator_result`.
- `src/mew/work_session.py` (+276 lines): adds
  `_tiny_write_ready_draft_turn_todo_id`,
  `_tiny_write_ready_draft_turn_matches_todo`, and threads `todo_id`
  through `_latest_tiny_write_ready_draft_turn` and
  `_apply_tiny_write_ready_draft_outcome_to_active_work_todo`. All
  three call sites in `_observe_active_work_todo` (new-todo,
  frontier-changed, stable-frontier) and the one in
  `build_work_session_resume` now look up the latest tiny turn scoped
  to the current candidate/existing todo id.
- `tests/test_work_session.py` (+467 lines): adds todo_id stamping to
  the synthetic tiny-lane turns in
  `test_build_work_session_resume_blocks_on_latest_tiny_blocker_turn`,
  `…_preserves_blocker_on_stable_frontier_reobservation`,
  `…_clears_tiny_write_ready_draft_blocker_on_succeeded`, and the
  frontier-change test. The frontier-change test now carries a matching
  blocker turn *and* asserts `todo["blocker"] == {}` on the newly
  minted `todo-1-2`, which is the direct contamination-bug regression
  check.

## Contamination-bug analysis

The bug shape: a blocker turn stamped against frontier A was applied
to a newly minted todo for frontier B (or vice versa) when the
session transitioned frontiers without the turn set being trimmed.
The fix installs an identity match on every apply boundary.

Trace through the scenarios:

1. **Frontier change (the contamination case).**
   - Existing `todo-1-1` with `status=blocked_on_patch`, blocker=X.
   - Candidate built for new target paths; fails the frontier-key
     match against existing.
   - `candidate["id"] = "todo-1-2"`.
   - `_latest_tiny_write_ready_draft_turn(model_turns, todo_id="todo-1-2")`
     filters turns via
     `_tiny_write_ready_draft_turn_matches_todo(turn, todo_id="todo-1-2")`.
     The old blocker turn is stamped `todo_id="todo-1-1"` — mismatch —
     skipped. Result: `{}`.
   - `_apply_tiny_write_ready_draft_outcome_to_active_work_todo` sees
     outcome `""` and returns candidate unchanged.
   - Candidate retains `status="drafting"`, `blocker={}`. ✓
   - Verified by the updated frontier-change test asserting
     `todo["blocker"] == {}`.

2. **Stable frontier, todo id unchanged.**
   - `updated.get("id") == existing.id`. Lookup filters turns stamped
     with that id. Latest match is applied normally, same as before.

3. **New todo (no existing).**
   - `candidate["id"]` is freshly minted. No prior turn carries that
     new id, so lookup returns `{}`. Apply is a no-op. The todo starts
     clean as it should. Subsequent tiny-lane invocations stamp the
     new id (via `context.active_work_todo.id`), and the next resume
     picks them up.

4. **Empty todo id edge case.**
   - `_tiny_write_ready_draft_turn_matches_todo` treats an empty
     `expected_todo_id` as a non-match (returns `False`). The apply
     helper therefore does nothing when asked to apply to a todo
     without an id. This is a safe refusal rather than silent
     application — the prior architecture had no such guard.
   - `_latest_tiny_write_ready_draft_turn`, however, returns the
     latest turn *without* id filtering when `todo_id` is empty
     (`if todo_id and ...: continue`). This is the escape hatch used
     by `build_work_session_resume` when `active_work_todo` is absent,
     so `_tiny_write_ready_draft_recovery_plan_item` can still be
     evaluated (and short-circuited when the todo is empty).

5. **Turn has no stamp** (pre-upgrade persisted state).
   - `_tiny_write_ready_draft_turn_todo_id` returns `""`. Match
     against a non-empty expected id fails. Turn is skipped. The
     apply helper does nothing. Any already-persisted blocker on the
     todo is preserved by the `dict(existing)` path in
     `_observe_active_work_todo`. So upgraded sessions keep their
     visible state until the next tiny-lane turn carries a stamp.
     Acceptable migration behavior.

The fix is targeted, symmetric across all four entry points, and the
new frontier-change test asserts the contamination is absent on the
exact boundary the bug lived on.

## Findings on this revision

No active blocker-severity findings. The contamination bug is
resolved.

### 1. LOW — Stamp only on `action_plan["todo_id"]`

`_attempt_write_ready_tiny_draft_turn` stamps `action_plan["todo_id"]`
only. `_tiny_write_ready_draft_turn_todo_id` also inspects
`action.todo_id` and `decision_plan.todo_id` as fallbacks, which is
defensive but currently unused. If a future path (e.g. deterministic
`normalize_work_model_action`) drops the `todo_id` key when rebuilding
`action` or `decision_plan`, the lookup still recovers from
`action_plan`. Note for later: if any code re-serializes
`action_plan` through a schema that strips unknown fields, the stamp
is lost and the apply silently no-ops. Defensive but worth a
regression test if you extend `normalize_work_model_action`.

### 2. LOW — Blocker-payload `todo_id` is redundant with the
action_plan stamp

`_work_loop_tiny_write_ready_draft_blocker_payload` now carries
`todo_id` from `validator_result` into the blocker payload. The
match function only reads `action_plan.todo_id` /
`action.todo_id` / `decision_plan.todo_id`, not
`action_plan.blocker.todo_id`. So the blocker-payload `todo_id`
is currently not consulted. This is harmless — it's just
observability — but consider either (a) removing the unused field, or
(b) extending `_tiny_write_ready_draft_turn_todo_id` to also look at
`action_plan.blocker.todo_id` so the two paths agree. Not a defect.

### 3. LOW — Migration window for in-flight sessions

Sessions with pre-upgrade tiny-lane blocker turns (no `todo_id`
stamp) will, on the first post-upgrade resume, retain the persisted
blocker only because the `dict(existing)` path in
`_observe_active_work_todo` keeps it. The next time a different tiny
turn lands with a proper stamp, the state fully aligns. There is a
narrow window in which a frontier-change during the migration could
clear a blocker that has no stamp to re-attach. Given the expected
upgrade cadence and the low cost of a re-run, acceptable. Flag for
the roadmap note.

### 4. LOW (carry-over) — 8/9 on the "persisted-todo" fixture test

`test_build_work_session_resume_prefers_persisted_active_work_todo`
still asserts continuity `8/9` because its synthetic turn carries no
`tiny_write_ready_draft_outcome` metric and no
`last_model_turn_id`, so the generated recovery item has
`model_turn_id=None` and fails `_continuity_recovery_item_visible`.
This is unchanged from FINAL2; the live path is `9/9` per user
evidence. Non-blocking.

## Prior findings — resolution re-check

- HIGH recovery-map contradiction — resolved (FINAL).
- MEDIUM reason-string coupling — resolved (FINAL).
- LOW partial map — resolved (FINAL).
- LOW stable-frontier re-observation coverage — resolved (FINAL).
- LOW attempt-counter double-bump — resolved (FINAL2).
- NEW contamination of blocker across frontier change — **resolved
  this revision** via `todo_id` stamping plus identity-matching
  guards at all four apply sites, verified by the updated
  frontier-change test.

## Residual non-blocking follow-ups

1. **Follow-status stale-timeout bug** (unchanged from FINAL2).
   `./mew work 402 --follow-status --json` still shows the older
   `request_timed_out` with an empty `suggested_recovery`. Dedicated
   slice, untouched here by design.
2. **Validator codes outside the frozen taxonomy** (e.g.
   `insufficient_cached_context`). Still falls back to
   `refresh_cached_window`. Out of scope.
3. **Recovery item fallback handle when no `last_model_turn_id`**
   (FINAL2 finding 1). Still cosmetic; live sessions populate it via
   `start_work_model_turn`.
4. **Stamp visibility during action/decision normalization**
   (finding 1 above).
5. **Blocker-payload `todo_id` not consulted by the match helper**
   (finding 2 above).

## Bounding check

- Files touched: 3 (plan-matching). ✓
- No change to `commands.py`, `write_tools.py`, prompts, or
  `patch_draft.py` semantics beyond reading its existing taxonomy and
  the `todo_id` already produced by `build_patch_blocker`. ✓
- No new top-level resume field. Uses `active_work_todo` +
  `recovery_plan` (existing surfaces). ✓
- `active_work_todo.status` remains the canonical source of truth;
  `work_session_phase` derivation unchanged. ✓
- Phase 5/6 territory untouched. ✓
- The identity guard is scoped to the tiny-lane. Non-tiny code paths
  are unaffected. ✓

## Verdict

**Approve.**

The frontier-identity guard cleanly resolves the stale-blocker
contamination bug. The stamp is emitted at a single point in
`_attempt_write_ready_tiny_draft_turn` and consumed symmetrically at
every apply site via `_tiny_write_ready_draft_turn_matches_todo`. The
updated frontier-change test pins the invariant in regression form.

All prior findings remain resolved. Residual items are cosmetic,
migration-window, or explicit follow-ups. None should block landing.
