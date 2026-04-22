# M6.11 Phase 4 Blocker Persistence — Final Review 2 (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `5085ff0`, after the latest revision:

- `src/mew/work_loop.py` (+28 lines, unchanged since FINAL): structured
  `action_plan["blocker"]` payload stamped in both the model-direct and
  compiler-derived blocker branches of
  `_attempt_write_ready_tiny_draft_turn`.
- `src/mew/work_session.py` (+219 lines, grew +94 since FINAL): the
  persistence pathway has been re-architected. The
  `update_work_model_turn_plan` hook is gone. Instead, a new
  `_apply_tiny_write_ready_draft_outcome_to_active_work_todo` derives
  `status=blocked_on_patch`, `blocker={...}`, and `attempts.draft` from
  the latest completed tiny-lane turn (via
  `_latest_tiny_write_ready_draft_turn`) and is now called from all three
  branches of `_observe_active_work_todo` (new-todo, frontier-changed,
  stable-frontier merge). Also adds
  `_tiny_write_ready_draft_recovery_plan_item` and
  `_append_unique_recovery_plan_item`, wired into
  `build_work_session_resume` to inject a `kind=model_turn`,
  `action=needs_user_review` item carrying a `mew work … --session
  --resume --allow-read . --auto-recover-safe` hint whenever the active
  todo is `blocked_on_patch`.
- `tests/test_work_session.py` (+442 lines, grew +77 since FINAL): three
  new resume-derivation tests (blocks-on-latest-turn,
  stable-frontier-reobservation, clears-on-succeeded) plus the earlier
  ones adapted to the new derivation entry point. The existing
  `test_build_work_session_resume_prefers_persisted_active_work_todo`
  now asserts continuity `8/9` with `missing == ["risks_preserved"]`
  (previously 9/9) — see finding 1 below for the reason.

## Architectural note

This revision moves blocker persistence from eager write at
`update_work_model_turn_plan` time to lazy derivation at
`build_work_session_resume` time. That is a better fit for the design
doc's canonical-source-of-truth invariant
(`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:327-332`): session phase
is derived from `active_work_todo.status`, and the todo status is now
derived from model_turns. It also removes the attempt-counter
double-bump edge case I flagged in the prior FINAL review, because
resume is idempotent over the same turn set.

Live evidence confirms the intent: `./mew work 402 --session --resume …
--json` now reports `phase=blocked_on_patch`, a populated blocker
payload, a non-empty recovery_plan, and continuity `9/9`.

## Findings on this revision

No active blocker-severity findings.

### 1. LOW — Persisted-todo test regressed 9/9 → 8/9

`test_build_work_session_resume_prefers_persisted_active_work_todo` now
asserts `continuity.score == "8/9"` with `missing == ["risks_preserved"]`.
That fixture has an active `blocked_on_patch` todo and a matching
model_turn with `write_ready_fast_path: True` but *no*
`tiny_write_ready_draft_outcome` metric, so:

- `_latest_tiny_write_ready_draft_turn(turns)` returns `{}`.
- `_tiny_write_ready_draft_recovery_plan_item(...)` populates
  `model_turn_id = tiny_turn.get("id") or session.get("last_model_turn_id")`
  — both are missing in the synthetic fixture, so
  `model_turn_id = None`.
- `_continuity_recovery_item_visible` requires
  `tool_call_id is not None or model_turn_id is not None`. The
  generated item has neither → `has_id = False` → item invisible →
  `risks_preserved` axis fails.

In live runs this doesn't happen: `start_work_model_turn` writes
`session["last_model_turn_id"]`
(`src/mew/work_session.py:1489`), so the fallback always populates.
The #402 evidence (9/9) confirms that.

This is therefore a fixture-only degradation, not a real regression.
Still worth noting:

- Option A (low effort): when both tiny_turn and
  `session["last_model_turn_id"]` are empty, fall back to
  `f"todo:{todo.get('id')}"` as the item handle so the item's
  visibility is anchored to the todo that supplies the evidence.
- Option B (no code change): leave the test at 8/9 as an honest
  statement that the fixture does not carry all the evidence a real
  session would.

Either is acceptable for this slice. Option A costs one line.

### 2. LOW — Recovery item reason text differs from resume next_action text

`_tiny_write_ready_draft_recovery_plan_item.reason` produces:

```
"tiny draft blocker <code>; <detail-or-default-fallback>"
```

while `build_work_session_resume` already sets its own
`next_action`:

```
"inspect the active patch blocker and refresh the exact cached windows
or todo source before retrying"
```

Both are user-facing. Runnability is satisfied because the item's `hint`
field contains `mew work … --session --resume`, which
`_continuity_text_has_command_control` matches. But readers see two
distinct phrasings for the same state. Cosmetic. Pinning the item's
`reason` to mirror the existing resume next_action (or vice versa)
would remove the divergence later without widening scope now.

### 3. LOW — `hint` and `review_hint` carry the same command

`_tiny_write_ready_draft_recovery_plan_item` sets both `hint` and
`review_hint` to
`mew work … --session --resume --allow-read . --auto-recover-safe`.
Harmless duplication — the continuity and follow-status formatters read
both fields. Tiny follow-up: keep `review_hint` as the human-review
command and leave `hint` for an `auto-recover-safe` retry if/when one
becomes appropriate.

### 4. LOW — `_apply_tiny_write_ready_draft_outcome_to_active_work_todo` rewrites status on every stable-frontier resume

On each `build_work_session_resume`, after `_observe_active_work_todo`
merges `existing` and `candidate`, the apply helper unconditionally
re-computes `status` from the latest tiny outcome. If the same session
is resumed repeatedly without a new tiny-lane turn, this is a no-op
(the same turn produces the same outcome). But it does mean that if a
later phase flips the todo to a different non-terminal status (e.g. a
hypothetical `awaiting_review` transition in Phase 5), a stale
blocker-or-succeeded metric on a prior turn could overwrite it. Not a
concern for Phase 4, but worth remembering when the Phase 5 review lane
lands.

## Prior findings — resolution re-check

- HIGH recovery-map contradiction → resolved (single source of truth in
  `patch_draft.PATCH_BLOCKER_RECOVERY_ACTIONS`).
- MEDIUM reason-string coupling → resolved (structured blocker payload
  in `action_plan["blocker"]`).
- LOW partial map → resolved (all 12 codes available via the taxonomy
  import).
- LOW stable-frontier re-observation coverage → resolved (two tests:
  `test_build_work_session_resume_preserves_blocker_on_stable_frontier_reobservation`
  and
  `test_build_work_session_resume_preserves_stable_frontier_blocker_across_reobservation`).
- LOW attempt-counter semantics → resolved by re-architecture — the
  counter is now derived from `model_metrics.draft_attempts`, with an
  idempotency branch (`observed==0` only bumps when status was not
  already `blocked_on_patch` AND outcome is `blocker`), so resume calls
  are truly idempotent.

## Residual, explicitly non-blocking follow-ups

1. **Follow-status stale-timeout bug (user-confirmed).**
   `./mew work 402 --follow-status --json` still shows the older
   `request_timed_out` and an empty `suggested_recovery`. The relevant
   merge at `src/mew/commands.py:6616` is untouched by this slice and
   should ship as a dedicated small slice: prefer the newer session
   state when snapshot reports a stale timeout and resume reports a
   classified blocker.
2. **Validator codes outside the frozen taxonomy** (e.g.
   `insufficient_cached_context` observed on #402 attempt-4): the
   tiny-lane falls back to `refresh_cached_window`. Either extend the
   taxonomy or tighten the validator — out of scope here.
3. **Recovery item `model_turn_id` fallback** (see finding 1).
4. **Recovery item reason/hint duplication** (findings 2, 3).
5. **Helper location for future Phase 5 review lane** — the tiny-lane
   outcome-apply helper is guarded by the tiny-lane-specific metric;
   when the review lane lands, it should grow its own helper rather
   than extending this one.

## Bounding check

- Files touched: 3 (plan-matching). ✓
- No change to `commands.py`, `write_tools.py`, prompts, or
  `patch_draft.py` semantics beyond reading its existing taxonomy. ✓
- No new top-level resume fields; uses `active_work_todo` +
  `recovery_plan` (existing surfaces). ✓
- `active_work_todo.status` is still the canonical source of truth;
  phase derivation via `work_session_phase` is unchanged. ✓
- Phase 5/6 territory untouched (no review lane, no executor lifecycle
  states). ✓
- Recovery-plan wiring stays inside Phase 4 scope
  (`docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:836-847` — "replace
  draft-time `replan` with draft-aware recovery actions"). ✓

## Verdict

**Approve.**

The revision:

1. Correctly implements the slice's stated goal — `#402` now resumes
   with `phase=blocked_on_patch`, a populated blocker, a non-empty
   `recovery_plan`, and continuity `9/9`, per live evidence.
2. Resolves every blocker-severity finding from the prior review.
3. Moves to a cleaner architecture (derive at resume, not persist at
   turn write) that better respects the design's source-of-truth
   invariant and eliminates the earlier idempotency risk.
4. Stays inside Phase 4 scope; does not widen into review, executor
   lifecycle, or prompt-contract changes.

Residual items listed above are cosmetic, test-fixture artifacts, or
explicit follow-ups the user has already acknowledged (notably the
`follow-status` stale-timeout gap). None of them should block landing
this slice.
