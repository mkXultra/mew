# M6.11 Phase 4 Blocker Persistence — Implementation Review (2026-04-22, claude)

## Scope reviewed

Uncommitted diff against HEAD `5085ff0`:

- `src/mew/work_session.py` (+107 lines): new
  `_TINY_WRITE_READY_DRAFT_BLOCKER_RECOVERY_ACTIONS` map,
  `_tiny_write_ready_draft_recovery_action`,
  `_tiny_write_ready_draft_blocker_from_turn`,
  `_tiny_write_ready_draft_attempt_counter`,
  `_update_tiny_write_ready_draft_active_work_todo`, and a hook in
  `update_work_model_turn_plan`.
- `tests/test_work_session.py` (+241 lines): four new tests + an extension
  to `test_build_work_session_resume_prefers_persisted_active_work_todo`
  that asserts continuity `9/9`.

The intended slice goal is: when the tiny write-ready lane returns a
classified blocker, mutate `session["active_work_todo"]` so its `status`
flips to `blocked_on_patch` and `blocker` carries `code`, `detail`,
`recovery_action` (plus optional path/line span). When the lane succeeds,
reset `blocker = {}` and `status = "drafting"`. The phase/next_action
derivation already present in `build_work_session_resume` (see
`src/mew/work_session.py:5053-5054`) then automatically surfaces the
inspect-and-retry next action, lifting continuity's
`next_action_runnable` axis to met.

## Findings

### 1. HIGH — Pinned recovery map contradicts the frozen Recovery Contract

`_TINY_WRITE_READY_DRAFT_BLOCKER_RECOVERY_ACTIONS`
(`src/mew/work_session.py:51-58`) maps:

```python
"ambiguous_old_text_match":     "refresh_cached_window",
"unpaired_source_edit_blocked": "refresh_cached_window",
```

But `docs/LOOP_STABILIZATION_DESIGN_2026-04-22.md:585-598` pins a frozen
blocker→recovery-action map that says:

```
ambiguous_old_text_match     -> narrow_old_text
unpaired_source_edit_blocked -> add_paired_test_edit
```

This is two direct contradictions of a contract the design doc labels
"frozen early and used consistently in runtime state, follow-status, and
tests." The unknown-code fallback to `refresh_cached_window` is fine for
codes not yet observed in the wild, but these two codes are explicitly
*in* the frozen taxonomy and explicitly mapped to something else. Users
or downstream tooling reading `active_work_todo.blocker.recovery_action`
will be told to refresh cached windows when the correct recovery is to
narrow the old-text span or add a paired test edit.

**Required change:** match the frozen map for at least the four codes the
diff chose to enumerate:

```python
"missing_exact_cached_window_texts": "refresh_cached_window",
"stale_cached_window_text":          "refresh_cached_window",
"ambiguous_old_text_match":          "narrow_old_text",
"unpaired_source_edit_blocked":      "add_paired_test_edit",
```

Also add a focused test that pins `ambiguous_old_text_match →
narrow_old_text` and `unpaired_source_edit_blocked → add_paired_test_edit`
so the mapping cannot regress silently. The existing
`test_tiny_write_ready_draft_recovery_action_defaults_to_refresh_cached_window`
only covers the unknown-code path.

### 2. MEDIUM — Blocker code is recovered by substring-stripping the wait reason

`_tiny_write_ready_draft_blocker_from_turn`
(`src/mew/work_session.py:77-83`) extracts the blocker code by stripping
the literal prefix `"write-ready tiny draft blocker:"` off
`action.reason`, falling back to `decision_plan.get("code")`.

That works today because `_stable_write_ready_tiny_draft_blocker_reason`
in `src/mew/work_loop.py:712-714` produces exactly that format for both
the model-direct `patch_blocker` case and the compiler-derived blocker
case. But it couples blocker persistence to a formatter string. If the
formatter is ever re-worded (e.g. localized, prefixed differently, or
the code escaped), this extractor silently produces `""` for the code
and the persisted blocker becomes an empty-code, default-recovery entry
with no loud failure mode.

The tiny-lane code path already has the classified blocker in
`validator_result["code"]` when the compiler ran, and in
`decision_plan["code"]` when the model returned `patch_blocker` directly.
Threading that through the tiny-lane return value (or persisting from
`work_loop.py` after the tiny-lane returns, where both `decision_plan`
and `validator_result` are in scope) is more durable than re-parsing the
user-facing reason string.

Not a blocker for landing this slice — it happens to be correct today —
but add at minimum a `_TINY_WRITE_READY_DRAFT_BLOCKER_REASON_PREFIX`
assertion or test that fails loudly if the prefix in `work_loop.py` and
the prefix constant in `work_session.py` drift apart.

### 3. LOW — Pinned map covers only 4 of 12 frozen taxonomy codes

The frozen taxonomy (design doc line 485-500) names 12 codes. The diff's
map enumerates 4. Unmapped codes fall back to `refresh_cached_window`,
which is *wrong* for at least:

- `overlapping_hunks`      (frozen map → `merge_or_split_hunks`)
- `no_material_change`     (frozen map → `revise_patch`)
- `write_policy_violation` (frozen map → `revise_patch_scope`)
- `model_returned_non_schema` (frozen map → `retry_with_schema`)
- `model_returned_refusal`    (frozen map → `inspect_refusal`)
- `review_rejected`           (frozen map → `revise_patch_from_review_findings`)

These codes are not currently emitted by the live tiny lane on `#402`, so
the silent miss doesn't block the continuity 8/9 → 9/9 goal of this
slice. But the map is meant to be the frozen contract; leaving a partial
map encoded in the source invites quiet drift. Consider landing the
whole 12-row map now (it is read-only data) and enforcing parity in a
test that enumerates the design's list.

If the reviewer chooses to keep this slice strictly bounded, file an
explicit follow-up instead.

### 4. LOW — No test covers frontier-stable re-observation preserving the persisted blocker

After `_update_tiny_write_ready_draft_active_work_todo` stamps
`status=blocked_on_patch` + `blocker={code,...}`, the next work step will
run `_observe_active_work_todo`, which (for a stable frontier key) does
`updated = dict(existing)` and then overwrites `source`,
`cached_window_refs`, `updated_at`, and `attempts` but not `status` or
`blocker` (see `src/mew/work_session.py:4611-4629` in the current file).

Reading the code, the blocker is preserved through re-observation, but
neither new test locks that in. Given the whole point of this slice is
that `blocked_on_patch` must survive to the next `build_work_session_resume`,
add one test that:

1. persists a tiny-lane blocker via `update_work_model_turn_plan`,
2. runs `_observe_active_work_todo` (or full `build_work_session_resume`)
   on the same frontier,
3. asserts `session["active_work_todo"]["status"] == "blocked_on_patch"`
   and `blocker.code` is still the original code.

Without it, a future refactor of `_observe_active_work_todo` could flip
the status back to `drafting` between steps and the existing tests would
still pass.

### 5. LOW — Success-path test asserts `attempts.draft` stays at 3

`test_update_work_model_turn_plan_succeeds_clears_tiny_write_ready_draft_blocker`
(`tests/test_work_session.py:~8259`) sets starting attempts to
`{"draft": 3, "review": 0}` and after a `succeeded` outcome asserts
`{"draft": 3, "review": 0}`. This matches the implementation
(`_update_tiny_write_ready_draft_active_work_todo` preserves the counter
on the success branch). But it is slightly non-obvious: some readers
might expect a success to *reset* `draft`. The current behavior —
preserve the monotone attempt history so resume can surface "took N
attempts to succeed" — is reasonable, but a one-line code comment or
docstring on `_update_tiny_write_ready_draft_active_work_todo` would
save a future reader a round trip. Not a correctness problem.

### 6. LOW — Success branch with `action={"type":"batch","tools":[]}` is a fabricated shape

The succeeded-path test feeds an action of `{"type": "batch", "tools":
[]}`. A tiny-lane succeeded result in practice has non-empty `previews`.
An empty-tools batch would be flagged earlier in `work_loop.py` as
`preview_unusable`. The test exercises the persistence helper in
isolation, which is fine, but the shape is not representative of a real
success. If you keep the helper as a pure state transform (which is
good), rename the test or annotate the intent so future readers do not
treat an empty-tools batch as a legal real-world success. Cosmetic.

## Residual risks / follow-ups (not blockers)

1. **`latest_model_failure` still shows the older timeout.** The user
   called this out as still unresolved. This slice intentionally does
   not touch the snapshot/session turn merge at
   `src/mew/commands.py:6616`. File as a dedicated small follow-up
   slice so the inconsistency between follow-status and resume closes
   cleanly.
2. **Coupling of persistence to `update_work_model_turn_plan`.** This
   entry point is shared with multiple commands.py call sites. The
   `tiny_write_ready_draft_outcome` guard correctly scopes the mutation
   today, but any future code path that adopts the same metric for a
   different purpose will unintentionally trigger todo mutation.
   Consider moving the hook to a tiny-lane-specific wrapper once
   Phase 5 starts.
3. **`_observe_active_work_todo` does not clear a persisted blocker
   when the frontier key stays stable but the blocker should expire
   (e.g. cached windows refreshed).** Out of scope here; relevant once
   the recovery action is actually executed in Phase 5.
4. **Design doc freezes 12 blocker codes, live tiny lane emits codes
   outside that taxonomy** (e.g. `insufficient_cached_context` seen on
   `#402` attempt-4). That is a validator-side gap, not persistence.
   Finding 3 is a local consequence; the upstream fix is a separate
   slice.

## Bounding check

- Files touched: 2 (the ones named in the plan). ✓
- No change to `write_tools.py`, `commands.py`, prompt shape, or
  validator semantics. ✓
- No new top-level resume field; uses the existing `active_work_todo`
  surface. ✓
- Phase-5/6 territory untouched (no review lane, no executor lifecycle
  states, no new recovery plan item source). ✓
- `active_work_todo.status` remains canonical; resume phase continues to
  derive from it. ✓

## Verdict

**Revise.**

Finding 1 is a correctness issue against a frozen design contract and
must be fixed before landing: two enumerated blocker codes are mapped to
the wrong recovery action. Fixing it is a two-line change plus one test
addition and does not widen the slice.

Finding 2 is worth addressing opportunistically (thread the
already-computed code through instead of parsing the reason string), but
can be deferred if you want to keep this slice strictly minimal.

Findings 3–6 are non-blocking and are fine as follow-ups.

Once finding 1 is resolved and the new mapping test is added, this slice
achieves its stated goal — `#402` resume flips to `blocked_on_patch`
with a runnable inspect-and-retry next action, continuity reaches 9/9,
and no other surface is disturbed.
