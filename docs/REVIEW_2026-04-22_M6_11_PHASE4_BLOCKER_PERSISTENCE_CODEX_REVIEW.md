# M6.11 Phase 4 Blocker Persistence Review (Codex)

## Findings

1. **High: the new blocker recovery table forks from the canonical `PatchBlocker` mapping and persists the wrong recovery action for known codes.**

   In [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:51), the new `_TINY_WRITE_READY_DRAFT_BLOCKER_RECOVERY_ACTIONS` table maps:

   - `ambiguous_old_text_match -> refresh_cached_window`
   - `unpaired_source_edit_blocked -> refresh_cached_window`

   But the canonical mapping in [`src/mew/patch_draft.py`](/Users/mk/dev/personal-pj/mew/src/mew/patch_draft.py:11) already freezes those codes as:

   - `ambiguous_old_text_match -> narrow_old_text`
   - `unpaired_source_edit_blocked -> add_paired_test_edit`

   This is a source-of-truth violation inside the bounded slice itself. The new persistence path will write the wrong `recovery_action` onto `active_work_todo.blocker`, so any later Phase 4 consumer that trusts the persisted blocker will be pointed at the wrong recovery behavior. This is not just “missing future wiring”; it stores incorrect data now.

2. **Medium: successful tiny-draft turns clear the blocker without recording that the successful draft attempt happened.**

   In [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:142), the `succeeded` branch clears `status`/`blocker` but leaves `attempts["draft"]` unchanged. That makes the persisted todo internally inconsistent with the existing write-ready attempt contract, which counts every write-ready draft attempt via model-turn metrics in [`src/mew/work_loop.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_loop.py:679) and [`src/mew/work_session.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_session.py:4442).

   The new regression at [`tests/test_work_session.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_session.py:8343) currently asserts the stale value (`3` stays `3` after a successful tiny draft), so it locks in the inconsistency instead of catching it. Resume may recompute a higher number later from turn metrics, but the persisted `active_work_todo` is wrong in the meantime.

## Residual Risks / Follow-Ups

- Unknown model-emitted blocker codes currently default to `refresh_cached_window`. That is tolerable for this bounded slice only if the code is treated as a temporary conservative fallback. Before any consumer starts executing blocker-driven recovery automatically, unknown codes should either normalize onto the frozen `PatchBlocker` vocabulary or fail closed more explicitly.
- The slice remains bounded. I do not see pressure here for a broader refactor; fixing the mapping source of truth and the attempt-counter semantics should be enough.

## Verification

Ran:

```bash
uv run pytest -q tests/test_work_session.py -k 'update_work_model_turn_plan_persists_tiny_write_ready_draft_blocker or update_work_model_turn_plan_succeeds_clears_tiny_write_ready_draft_blocker or build_work_session_resume_prefers_persisted_active_work_todo'
```

Result: `3 passed`.

## Verdict

**Revise.**

The slice is still small and on the right surface, but it should not land with a second, incorrect blocker-recovery mapping or with a persisted draft-attempt counter that disagrees with the existing write-ready attempt contract.
