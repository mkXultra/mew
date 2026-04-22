# M6.11 Phase 4 Blocker Persistence Review (Codex, Final 2)

## Findings

1. **High: latest tiny-draft blocker state is applied to any newly observed frontier, even when the latest tiny turn belongs to an older todo/frontier.**

   The new persistence path derives blocker state from `_latest_tiny_write_ready_draft_turn(model_turns)` and then applies it inside `_observe_active_work_todo(...)` when:

   - there is no existing todo yet, or
   - the frontier changed and a new todo id is being created

   See:

   - [`src/mew/work_session.py:4688`]( /Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4688 )
   - [`src/mew/work_session.py:4697`]( /Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4697 )
   - [`src/mew/work_session.py:128`]( /Users/mk/dev/personal-pj/mew/src/mew/work_session.py:128 )
   - [`src/mew/work_session.py:160`]( /Users/mk/dev/personal-pj/mew/src/mew/work_session.py:160 )

   There is no frontier identity check between the newly constructed candidate todo and the returned `latest_tiny_turn`. The turn does not carry a todo id or any equivalent guard here, so a blocker from frontier A can be replayed onto freshly created frontier B.

   Concretely:

   - tiny lane blocks on one edit-ready slice
   - later model turns change `working_memory.plan_items` / `target_paths`
   - `_observe_active_work_todo()` correctly detects a new frontier and allocates a new todo id
   - the code immediately re-applies the old blocker to the new todo because it only looks at the latest tiny outcome globally

   That breaks source-of-truth discipline for exactly the thing this slice is trying to stabilize: blocker state becomes session-global rather than frontier-specific.

   The supplied local evidence does not disprove this, because it only exercises the stable-frontier path on task `#402` where the same todo/frontier is still active.

## Residual Non-Blocking Risks

- The local evidence is otherwise good for the bounded slice: `work 402 --session --resume --json` now shows `phase=blocked_on_patch`, populated `active_work_todo.blocker`, non-empty `recovery_plan`, and continuity `9/9`. That supports the “same frontier, latest blocker” path.
- `work 402 --follow-status --json` still surfacing the stale older timeout with empty `suggested_recovery` looks like a follow-up consumer/snapshot issue, not a blocker for this persistence slice by itself. I would keep that as the next follow-status slice rather than widening this patch further.
- The new recovery-plan item is intentionally conservative: it uses `needs_user_review` plus resume hints rather than immediately encoding per-blocker executable recovery actions. That is acceptable for this bounded patch as long as the persisted blocker remains frontier-correct.

## Verification

Ran targeted tests:

```bash
uv run pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft_recovery_action_defaults_to_refresh_cached_window or tiny_write_ready_draft_recovery_action_prefers_patch_draft_mapping or normalize_active_work_todo_preserves_tiny_blocker_detail or update_work_model_turn_plan_persists_tiny_write_ready_draft_blocker or update_work_model_turn_plan_succeeds_clears_tiny_write_ready_draft_blocker or build_work_session_resume_prefers_persisted_active_work_todo or build_work_session_resume_preserves_stable_frontier_blocker_across_reobservation'
```

Result: targeted tests passed.

I also considered the supplied live evidence:

- `./mew work 402 --session --resume --allow-read . --json`
- `./mew work 402 --follow-status --json`

## Verdict

**Revise.**

The slice is close and stays bounded, but the frontier-correlation bug is a blocker. The code should not carry blocker state from “latest tiny turn in the session” onto a newly created todo unless it can prove that the turn belongs to that same frontier.
