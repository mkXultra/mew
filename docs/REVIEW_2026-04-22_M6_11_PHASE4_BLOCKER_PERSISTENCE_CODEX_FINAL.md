# M6.11 Phase 4 Blocker Persistence Review (Codex, Final)

## Findings

No active findings.

The two prior issues are resolved in the actual code:

- The blocker recovery action now reuses the canonical [`PATCH_BLOCKER_RECOVERY_ACTIONS`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py:11) source of truth instead of carrying a divergent local table ([`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:55)).
- Successful tiny-draft turns now advance the persisted draft-attempt count via observed `model_metrics["draft_attempts"]` instead of leaving the stale value in `active_work_todo` ([`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:145)).

The added `action_plan["blocker"]` payload in [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:717) is the right bounded fix for source-of-truth discipline here: it lets persistence consume structured blocker fields directly instead of re-deriving path/span from the human-readable wait reason.

## Residual Non-Blocking Risks

- Unknown blocker codes still fall back to `refresh_cached_window` ([`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:51)). That is acceptable for this bounded persistence slice, but if the model starts emitting new stable blocker codes outside the frozen `PatchBlocker` vocabulary, the fallback could become too permissive for later recovery consumers.
- The slice stays intentionally narrow: it persists blocker state and attempt counts, but it does not yet widen into full blocker-driven recovery-plan generation or follow-status election changes. That is consistent with the bounded scope of this patch.

## Verification

Ran:

```bash
uv run pytest -q tests/test_work_session.py -k 'tiny_write_ready_draft_recovery_action_defaults_to_refresh_cached_window or tiny_write_ready_draft_recovery_action_prefers_patch_draft_mapping or normalize_active_work_todo_preserves_tiny_blocker_detail or update_work_model_turn_plan_persists_tiny_write_ready_draft_blocker or update_work_model_turn_plan_succeeds_clears_tiny_write_ready_draft_blocker or build_work_session_resume_prefers_persisted_active_work_todo or build_work_session_resume_preserves_stable_frontier_blocker_across_reobservation'
```

Result: `7 passed`.

## Verdict

**Approve.**

This revision fixes the prior correctness problems, keeps the slice bounded, and improves source-of-truth discipline rather than weakening it.
