# M6.11 Phase 4 Blocker Persistence — Final Implementation Review (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `5085ff0`, after revision:

- `src/mew/work_loop.py` (+28 lines): new
  `_work_loop_tiny_write_ready_draft_blocker_payload` that builds a
  structured `{code, detail, path?, line_start?, line_end?}` object, and
  stamps it onto `action_plan["blocker"]` in both the model-direct
  `patch_blocker` branch (line 1693) and the compiler-derived blocker
  branch (line 1720).
- `src/mew/work_session.py` (+125 lines): imports
  `PATCH_BLOCKER_RECOVERY_ACTIONS` from `patch_draft`, replaces the prior
  local 4-entry map, adds
  `_tiny_write_ready_draft_recovery_action`,
  `_tiny_write_ready_draft_blocker_from_turn` (now prefers
  `action_plan["blocker"]` over reason-string parsing),
  `_tiny_write_ready_draft_attempt_counter`,
  `_update_tiny_write_ready_draft_active_work_todo`, and hooks the last
  into `update_work_model_turn_plan`.
- `tests/test_work_session.py` (+365 lines): five new tests (recovery
  default, recovery prefers frozen taxonomy, normalize preserves blocker
  detail, persists blocker on update, clears blocker on success, preserves
  blocker across stable-frontier re-observation) plus a continuity 9/9
  assertion on the existing persisted-todo test.

## Prior findings — resolution check

1. **HIGH, "pinned recovery map contradicts the frozen Recovery
   Contract" — RESOLVED.** The local 4-entry map is gone. The
   tiny-lane now consults `PATCH_BLOCKER_RECOVERY_ACTIONS` from
   `src/mew/patch_draft.py:11-24`, which matches the design doc's
   frozen map for all 12 codes, including
   `ambiguous_old_text_match → narrow_old_text` and
   `unpaired_source_edit_blocked → add_paired_test_edit`. Verified
   directly against `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:585-598`.
2. **MEDIUM, "blocker code recovered by prefix-stripping the wait
   reason" — RESOLVED.** The tiny-lane now emits a structured
   `action_plan["blocker"]` payload computed from `validator_result` at
   the point where the code is definitively known.
   `_tiny_write_ready_draft_blocker_from_turn` prefers that payload and
   only falls back to reason-string parsing / `decision_plan["code"]` if
   it is absent. The formatter `_stable_write_ready_tiny_draft_blocker_reason`
   is no longer the sole source of the persisted code.
3. **LOW, "map covers only 4 of 12 codes" — RESOLVED** (same fix as
   finding 1).
4. **LOW, "no test for stable-frontier re-observation" — RESOLVED.**
   `test_build_work_session_resume_preserves_stable_frontier_blocker_across_reobservation`
   runs `build_work_session_resume(session)` twice in succession and
   asserts `status=blocked_on_patch`, `blocker.code`, `blocker.path`, and
   todo `id` are all preserved on the second call.
5. **LOW, "success-path attempts semantics undocumented" — PARTIALLY
   RESOLVED.** The attempt counter now consumes
   `model_metrics["draft_attempts"]` as the canonical source, using the
   idempotent rule: prefer a larger observed count, else bump by one if
   the metric is absent, else leave unchanged. This is better-defined
   than before and matches real turn-counting. No docstring was added
   but the new logic is self-documenting.
6. **LOW, "success test uses empty-tools batch" — NOT ADDRESSED.**
   Cosmetic, remains.

## Findings on the revised diff

No active blocker-severity findings.

### Residual (LOW) — attempt-counter double-bump on missing metric
`_update_tiny_write_ready_draft_active_work_todo`
(`src/mew/work_session.py:~143-153`) applies:

```python
if observed_draft_attempts > draft_attempts:
    draft_attempts = observed_draft_attempts
elif observed_draft_attempts == 0:
    draft_attempts += 1
```

If a consumer calls `update_work_model_turn_plan` twice for the same
turn with `model_metrics["draft_attempts"]` unset (or zero), the counter
bumps both times. In the live write-ready path the metric is always
stamped by `work_loop.py:~2710`, so this is a test/edge case concern
only. Acceptable for this slice; note for Phase 5 hardening.

### Residual (LOW) — divergent unknown-code defaults
`_tiny_write_ready_draft_recovery_action` returns `refresh_cached_window`
for unknown codes, while `build_patch_blocker`
(`src/mew/patch_draft.py:41`) returns `inspect_blocker` for the same
unknown-code case. The design does not freeze a specific unknown
default, and the tiny-lane's conservative pick is correct for the
current live #402 path, but the asymmetry is worth recording. Pinning
one default in a single helper that both sites call would remove the
duplication; not required for this slice.

### Residual (LOW) — success-path test shape
`test_update_work_model_turn_plan_succeeds_clears_tiny_write_ready_draft_blocker`
still uses `action = {"type": "batch", "tools": []}`, which would be
flagged earlier as `preview_unusable` in the real tiny-lane flow. The
test exercises only the persistence helper's success branch, so the
shape is fine for that purpose. A rename or one-line comment would make
the intent clearer. Non-blocking.

## Non-blocking follow-ups

1. **`latest_model_failure` stale-timeout vs. resume blocker.** Still
   unresolved; explicitly deferred. The slice's scope doesn't touch
   `src/mew/commands.py:6616`, and that is correct. File a small
   follow-up to prefer the newer stop-reason over the older
   `request_timed_out` snapshot once downstream consumers are ready.
2. **Live validator codes outside the frozen taxonomy.** The #402
   attempt-4 replay shows `code=insufficient_cached_context`, which is
   not in the 12-code map, so `_tiny_write_ready_draft_recovery_action`
   falls back to `refresh_cached_window`. The fallback is benign, but
   either the validator should stop emitting off-taxonomy codes or the
   taxonomy should grow. Out of scope here.
3. **Helper location.** The tiny-lane-specific persistence helpers live
   inside `update_work_model_turn_plan`, which is shared by multiple
   commands.py call sites. The `tiny_write_ready_draft_outcome` guard
   correctly scopes the mutation today; consider moving to a tiny-lane
   wrapper once Phase 5 review work introduces additional writers.

## Bounding check

- Files touched: 3 — `work_loop.py`, `work_session.py`,
  `tests/test_work_session.py`. Matches the revised plan. ✓
- No change to `commands.py`, `write_tools.py`, prompts, or
  `patch_draft.py` semantics beyond reading its existing taxonomy. ✓
- No new top-level resume field; still derives everything from
  `active_work_todo`. ✓
- `active_work_todo.status` remains the canonical source of truth; phase
  derivation at `src/mew/work_session.py:5053` is untouched. ✓
- Phase 5/6 territory untouched (no review lane, no executor lifecycle
  states, no new recovery-plan item source). ✓

## Verdict

**Approve.**

The HIGH finding is resolved by wiring the tiny-lane persistence to the
frozen taxonomy in `patch_draft.PATCH_BLOCKER_RECOVERY_ACTIONS` instead
of a local overlay map. The MEDIUM finding is resolved by threading a
structured `blocker` payload through `action_plan["blocker"]`. The
stable-frontier re-observation test locks in the invariant that the
whole slice depends on. The attempt-counter logic is now defined against
turn metrics instead of a bare `+= 1`.

Residual items listed above are either cosmetic or out-of-scope
follow-ups and should not block landing.
