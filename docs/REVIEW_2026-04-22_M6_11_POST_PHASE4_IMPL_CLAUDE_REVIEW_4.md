# M6.11 Post-Phase-4 Follow-Status Parity — Final Review 4 (2026-04-22, claude)

## Scope re-reviewed

Uncommitted diff against HEAD `8f48189`:

- `src/mew/commands.py` (+178 / -25, +13 code lines since REVIEW_3)
- `tests/test_work_session.py` (+459 / -20, +3 lines since REVIEW_3)

## Delta since REVIEW_3 — `next_recovery_action` alignment

A new helper `_work_follow_status_next_recovery_action` at
`src/mew/commands.py:6613-6623` now computes `next_recovery_action`
from the canonical blocker taxonomy rather than the human-readable
recovery-plan summary. The source order is:

1. `active_work_todo.blocker.recovery_action` — the pinned taxonomy
   action (e.g. `refresh_cached_window`, `narrow_old_text`,
   `add_paired_test_edit`) that the tiny-lane persistence stamps via
   `_tiny_write_ready_draft_recovery_action` →
   `PATCH_BLOCKER_RECOVERY_ACTIONS`.
2. `recovery_plan.items[0].action` — first recovery item's `action`
   field (e.g. `retry_tool`, `needs_user_review`).
3. empty string.

Previously `next_recovery_action` read directly from
`recovery_plan.next_action`, which is a free-form sentence like
`"tiny draft blocker stale_cached_window_text; cached window text
changed"`. The alignment fix flips that to the frozen-taxonomy code,
matching the design doc's Recovery Contract at
`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:585-598`.

### Live `#402` behaviour after the fix

For the `#402` live session, the tiny-lane persistence sets
`active_work_todo.blocker.recovery_action` to a pinned taxonomy code
(e.g. `refresh_cached_window` for
`stale_cached_window_text` / `missing_exact_cached_window_texts`).
Follow-status will now surface that code verbatim under
`next_recovery_action`, giving parity with the resume view and with
the canonical taxonomy that machine consumers and tests can key off of.

### New test coverage

Two assertions lock the behaviour in:

- `test_work_follow_status_blocker_resume_surfaces_suggested_recovery`
  (`tests/test_work_session.py:~155-181`): live resume has
  `blocker.recovery_action = "refresh_cached_window"` AND
  `recovery_plan.items[0].action = "retry_tool"`. The test asserts
  `data["next_recovery_action"] == "refresh_cached_window"` — the
  blocker-recovery-action wins over the recovery-plan item.
- `test_work_follow_status_human_output_includes_active_work_todo_and_next_recovery_action`
  (`tests/test_work_session.py:~432-490`): live resume has
  `blocker` without `recovery_action` AND
  `recovery_plan.items[0].action = "retry_tool"`. The test asserts the
  human-output line `next_recovery_action: retry_tool` — the fallback
  chain picks up the recovery-plan item action.

The two cases exercise both branches of the new helper.

## Findings

No blocker-severity findings.

### 1. LOW — Helper uses `recovery_items[0]` rather than the most recent item

`_work_follow_status_next_recovery_action` at
`src/mew/commands.py:6618-6622` reads `recovery_items[0].action`.
`_append_unique_recovery_plan_item`
(`src/mew/work_session.py:4478-4493`) appends new items to the tail,
so `items[0]` is the oldest entry. If a session has both an older
interrupted-tool recovery item and a newer tiny-lane item, the helper
surfaces the older action.

For `#402` this is fine because the blocker path (priority 1) short-
circuits before the items array is consulted. But when the fallback
is hit (blocker has no `recovery_action`), the oldest item wins. If
the intent is "most relevant recovery action first", switching to
`items[-1]` would match the recovery-plan append order. Minor;
acceptable if the author intentionally picked first-in-plan.

### 2. LOW (unchanged) — `session_state_newer` still computed twice

`src/mew/commands.py:6800` and `6833` both assign
`session_state_newer` with identical arguments. Tidiness only.

### 3. LOW / OPEN QUESTION (unchanged) — Stale snapshot `latest_model_failure` persists when live has no new failure

`_work_follow_status_latest_model_failure(..., prefer_session=True)`
at `src/mew/commands.py:6716-6721` only returns the session failure
when one exists. For the `#402` tiny-lane-wait scenario,
`session_failure` is `None`, so the snapshot's stale timeout is still
reported with `source="snapshot"`. Whether to also suppress the
snapshot failure entirely when overlay is chosen is still an open
question; worth a tiny follow-up slice after this one lands.

### 4. LOW (unchanged) — `build_work_session_resume` side effects and per-call cost

`_work_follow_status_from_snapshot` invokes
`build_work_session_resume(session, ...)` at
`src/mew/commands.py:6798`. That call mutates `session` (via
`_observe_active_work_todo`). Mutations are discarded on exit (no
`save_state`) but propagate within the call. Per-call cost is
non-trivial. No correctness regression; noting for later tightening.

### 5. LOW (unchanged) — `phase` hardcoded override

`src/mew/commands.py:6860-6864` duplicates the canonical-source
derivation already done by `build_work_session_resume`
(`src/mew/work_session.py:5281`). Cosmetic.

### 6. LOW (unchanged) — Continuity-score comparison uses only the numerator

`_work_follow_status_resume_is_richer` compares parsed integer scores
without the denominator. Stable today with 9 axes; brittle if axis
count shifts between versions.

### 7. LOW (unchanged) — `working_memory_stale` is not overlayed

`working_memory_stale` is computed from `resume` (the snapshot's
resume) at `src/mew/commands.py:6791-6793`, before the overlay
decision. Every other resume-derived field switches to the live resume
when overlay fires, except this one. Small parity gap.

### 8. LOW (unchanged) — Dead `except` branch in `_work_follow_status_continuity_score`

`src/mew/commands.py:6600-6604` wraps `int(value)` for `float` inputs,
which cannot raise for normal floats. Unreachable `except`. Tidy only.

## Residual non-blocking follow-ups

1. Resolve the intent on stale-snapshot `latest_model_failure`
   (Finding 3).
2. Deduplicate `session_state_newer` (Finding 2).
3. Consider `items[-1]` instead of `items[0]` for the recovery-plan
   fallback (Finding 1), or document the "first-in-plan" intent.
4. Factor `phase` derivation into one helper (Finding 5).
5. Parse/compare the full `passed/total` ratio or document the stable
   denominator assumption (Finding 6).
6. Overlay `working_memory_stale` consistently (Finding 7).
7. Drop the unreachable `float` branch (Finding 8).

## Bounding check

- Files touched: 2 (`src/mew/commands.py`, `tests/test_work_session.py`). ✓
- No change to `work_session.py`, `work_loop.py`, `patch_draft.py`, or
  write/apply/verify flow. ✓
- No new top-level fields on `build_work_session_resume`. The new
  `resume_source`, `active_work_todo`, `blocker_code`, and
  `next_recovery_action` keys live only on
  `_work_follow_status_from_snapshot`'s return dict and the follow-
  status formatter. ✓
- Stays inside the post-Phase-4 follow-status parity slice. ✓

## Verdict

**Approve.**

The alignment fix correctly sources `next_recovery_action` from the
canonical blocker taxonomy first (`active_work_todo.blocker.recovery_action`,
which the Phase 4 tiny-lane persistence stamps from the frozen
`PATCH_BLOCKER_RECOVERY_ACTIONS` map) and falls back to the first
recovery-plan item's action only when the blocker has no classified
action. Both paths are test-covered.

For the `#402` live scenario, follow-status now surfaces the same
taxonomy action that the resume view and the design doc's Recovery
Contract already agree on — closing the parity gap the whole post-
Phase-4 slice was built to address. Live evidence so far:
- resume path: `phase=blocked_on_patch`, populated blocker, non-empty
  recovery_plan, continuity `9/9`;
- follow-status path (after this fix): `phase=blocked_on_patch`,
  `blocker_code` populated, `next_recovery_action` carrying the
  frozen-taxonomy code, `active_work_todo` overlayed, and
  `resume_source=session_overlay`.

All remaining findings are LOW-severity and unchanged from REVIEW_3
(plus one new very minor observation about the first-vs-last recovery
item selection). None block landing.

Series trajectory:

- REVIEW_1: established the overlay trigger + resume pass-through.
- REVIEW_2: fixed the continuity-score parser and added the
  snapshot-fresher negative test.
- REVIEW_3: fixed `pending_approval_count` to source from the
  effective resume.
- REVIEW_4: aligns `next_recovery_action` with the frozen blocker
  taxonomy.

The slice is now functionally complete for its stated goal and
consistent with the Phase 4 canonical-source-of-truth rules.
