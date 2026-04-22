# M6.11 Phase 4 — Next Bounded Slice Recommendation (Codex)

## Recommendation

Choose one bounded Phase 4 slice: **promote an accepted draft blocker into persisted `active_work_todo` blocker state plus a blocker-driven recovery plan**.

This should be a consumer-side recovery slice, not another Phase 3 generation slice.

## Why This Is The Best Next Slice

The current live `#402` / session `#392` evidence says the important Phase 3 question is already answered:

- the latest turn stopped cleanly at `2026-04-22T05:58:01Z`
- `last_step.action.reason` is `write-ready tiny draft blocker: insufficient_cached_context`
- `last_step.model_turn.id` is `1827`
- `tiny_write_ready_draft_outcome=blocker`
- `tiny_write_ready_draft_exit_stage=blocker_accepted`
- `tiny_write_ready_draft_elapsed_seconds≈7.568`

So the loop is no longer losing this turn to the old 30s/90s timeout path. The failure now is on the recovery surface:

- follow snapshot resume still shows `phase="drafting"`
- `active_work_todo.status` is still `drafting`
- `active_work_todo.blocker` is still empty
- `recovery_plan` is empty
- continuity is only `8/9`, missing `next_action_runnable`
- follow-status can still report the older timeout turn as `latest_model_failure`

That means the next unit of value is not more prompt tuning, preclassification, or timeout work. The missing behavior is exactly Phase 4: consume the accepted blocker and turn it into a runnable recovery path.

Why this is better than the alternatives:

- **Better than pairing-aware preclassification:** that was the right Phase 3 candidate while the lane still timed out. The new live run already produced a clean blocker in 7.6s. Another Phase 3 slice would improve an already-successful stop condition, but it would still leave the operator with no runnable next step.
- **Better than fixing `latest_model_failure` selection first:** stale timeout reporting is real, but it is secondary. If the session still has no blocker-backed recovery item, changing which failure line wins only improves narration, not recovery.
- **Better than more tiny-lane prompt or reasoning work:** the dominant problem on the current live sample is no longer “can the tiny lane stop cleanly?” It can. The dominant problem is “what happens after it stops?”

## Exact Slice

Implement one narrow recovery-consumer bridge:

1. Detect the latest accepted draft blocker from the current draft frontier.
2. Promote it onto `active_work_todo` as:
   - `status="blocked_on_patch"`
   - `blocker={code, detail, path?, line_start?, line_end?, recovery_action}`
3. Build a blocker-driven `recovery_plan` item instead of leaving `recovery_plan={}`.
4. Make `next_action` runnable enough to satisfy continuity and to give follow-status a real command via existing `work_follow_status_suggested_recovery(...)`.

For the current `#402` evidence, the recovery should point at refreshing the exact cached windows / draft frontier rather than generic replan.

## Exact Files To Change

1. `src/mew/work_session.py`

   Add the blocker-consumer logic here:

   - extract the latest draft-lane blocker from recent model turns
   - only trust turns that are clearly draft blockers, not generic `wait`
   - attach that blocker to the current `active_work_todo`
   - switch the todo to `blocked_on_patch`
   - generate a blocker-driven `recovery_plan`
   - make `next_action` include a concrete recovery control or command so `next_action_runnable` becomes true

   This is the right surface because `build_work_session_resume()`, `_observe_active_work_todo()`, `work_session_phase()`, `build_work_recovery_plan()`, and continuity scoring already meet here.

2. `tests/test_work_session.py`

   Add focused resume/recovery/follow-status regressions for the new blocker-consumer behavior.

No `src/mew/work_loop.py` change is required for this slice. The live turn already records the accepted blocker cleanly enough to consume.

## Focused Tests To Add Or Adjust

Add or adjust exactly these test shapes:

1. **Resume promotes latest accepted draft blocker into the todo**

   Build a session with:

   - an edit-ready frontier
   - a latest completed model turn whose `decision_plan.kind == "patch_blocker"`
   - blocker code/detail matching the current live contract

   Assert:

   - `resume["phase"] == "blocked_on_patch"`
   - `resume["active_work_todo"]["status"] == "blocked_on_patch"`
   - `resume["active_work_todo"]["blocker"]["code"]` matches the blocker
   - the blocker does not get overwritten back to plain `drafting`

2. **Resume maps blocker to recovery plan and runnable next action**

   Assert:

   - `resume["recovery_plan"]["items"][0]["action"]` is the expected draft-lane recovery action
   - `resume["recovery_plan"]["items"][0]["hint"]` or `review_hint` is populated
   - `resume["continuity"]["score"] == "9/9"`
   - `next_action_runnable` is no longer missing

3. **Follow-status suggestion reuses the blocker recovery plan**

   Use a follow snapshot plus session state shaped like `#392`:

   - latest failed model turn is still an older timeout
   - latest completed turn is the newer accepted blocker
   - resume carries the new blocker recovery plan

   Assert:

   - `work --follow-status --json` returns a non-empty `suggested_recovery`
   - the suggested recovery command comes from the blocker recovery plan, not generic replan

4. **Unknown blocker codes fail closed**

   Add one narrow regression where the blocker code is not in the pinned mapping.

   Assert:

   - the todo still becomes `blocked_on_patch`
   - recovery falls back to a conservative inspect/resume command
   - the loop does not silently degrade to generic exploratory replan

## Recovery Mapping For This Slice

Keep the mapping small and implementation-ready.

Use the existing frozen draft-lane vocabulary where possible:

- `missing_exact_cached_window_texts` -> `refresh_cached_window`
- `cached_window_text_truncated` -> `refresh_cached_window`
- `stale_cached_window_text` -> `refresh_cached_window`
- `old_text_not_found` -> `refresh_cached_window`
- `ambiguous_old_text_match` -> `narrow_old_text`
- `overlapping_hunks` -> `merge_or_split_hunks`
- `no_material_change` -> `revise_patch`
- `unpaired_source_edit_blocked` -> `add_paired_test_edit`
- `write_policy_violation` -> `revise_patch_scope`
- `model_returned_non_schema` -> `retry_with_schema`
- `model_returned_refusal` -> `inspect_refusal`

For the current live `#402` blocker `insufficient_cached_context`, use a temporary conservative alias to the same recovery family as missing exact window coverage: `refresh_cached_window`.

That is small, directly useful for `#402`, and does not require a broader blocker-taxonomy refactor in this slice.

## Risks

1. **False blocker promotion**

   If the consumer treats any `wait` as a blocker, it will misclassify ordinary waiting turns. Only consume turns that clearly carry the draft-blocker contract.

2. **Taxonomy drift**

   `insufficient_cached_context` is not part of the frozen compiler blocker vocabulary. If more ad hoc model-emitted codes appear, the mapping could sprawl. Keep this slice limited to the current live code plus fail-closed fallback behavior.

3. **State persistence asymmetry**

   `build_work_session_resume()` already mutates in-memory session state. If persistence timing stays unchanged, the follow snapshot may reflect the blocker before `state.json` does. That is acceptable for this slice as long as follow-status and resume become actionable immediately.

## Non-Goals

1. Do not reopen Phase 3 prompt, reasoning, timeout, or preclassification work.
2. Do not refactor the whole blocker taxonomy.
3. Do not add the Phase 5 review lane.
4. Do not widen into executor lifecycle / Phase 6.
5. Do not change `latest_model_failure` election in follow-status yet.

That stale timeout line is a real follow-up, but it is not the best next slice. First make the clean blocker produce a recovery path. Then, if needed, make follow-status narration prefer the blocker over the older timeout.

## Expected Outcome

After this slice, the next clean blocker on `#402` should no longer end as:

- blocker visible only in the last step
- todo still `drafting`
- `recovery_plan={}`
- continuity `8/9`

It should instead end as:

- `phase=blocked_on_patch`
- blocker attached to `active_work_todo`
- blocker-specific recovery action exposed
- follow-status returns a concrete `suggested_recovery`
- continuity reaches `9/9`

That is the smallest Phase 4 step that converts the new clean blocker stop into an actually runnable recovery path.
