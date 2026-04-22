# Review — Promote compiler tiny-lane `patch_blocker` to authoritative blocker

Scope reviewed: the next bounded M6.11 slice proposed jointly by
`docs/REVIEW_2026-04-22_M6_11_POST_5BBC_NEXT_SLICE_CODEX.md` and
`docs/REVIEW_2026-04-22_M6_11_POST_5BBC_NEXT_SLICE_CLAUDE.md`, at HEAD
`5bbc994`. I verified the line references against the working tree
before reviewing.

## Verdict: **approve (with the CLAUDE-variant `exit_stage` and a Phase 4 follow-up flagged)**

Both docs converge on the same slice, the same two files, the same
gate, and the same out-of-scope list. The technical claims line up
with the current repo:

- proposal-side `patch_blocker` branch is real at
  `src/mew/work_loop.py:1654-1684`
- compiler-side fallback branch is real at
  `src/mew/work_loop.py:1686-1699` (the promotion target)
- caller's early-return on `status != "fallback"` is real at
  `src/mew/work_loop.py:2755-2782`, so the flip truly prevents the
  generic THINK at `:2785-2796`
- `_stable_write_ready_tiny_draft_blocker_reason` is real at `:712-714`
  and already produces the literal `"write-ready tiny draft blocker: <code>"`
  the caller/recovery can key off
- `unpaired_source_edit_blocked → add_paired_test_edit` is real at
  `src/mew/patch_draft.py:19`, and the pairing check at `:395-405` is
  a pure filename check (no LLM judgment), so promoting it to a blocker
  is not discarding useful model work

## Rationale

- **Right direction.** Turn 1826 shows the tiny lane already does its
  job in ~12 s and produces a deterministic compiler classification;
  the remaining 90 s burn is the *consumer* ignoring that classification
  and asking a heavyweight think the same deterministic question. Both
  docs correctly identify this as the dominant waste after `5bbc994`.
- **Smallest viable change.** A branch split inside a single helper,
  reusing the existing wait-reason helper and the existing caller
  short-circuit. No new constant, no new schema, no prompt contract
  bump.
- **Right scope discipline.** Both docs explicitly reject widening into
  prompt shrink, timeout tuning, pairing preclassification, recovery
  wiring, or calibration-constant changes. That restraint is what
  makes the post-slice diagnostic attribution clean.
- **Evidence-grounded.** Claims are tied to turn-1826 observations, not
  speculation; the live replay path is named.

## Between the two docs

The CODEX doc is tighter; the CLAUDE doc is the better landing plan
because it adds three things that matter:

1. **New `exit_stage = "compiler_blocker"`** distinct from
   `"blocker_accepted"` (proposal-side) and `"compiler_fallback"`
   (genuine compiler rejection). Preserves calibration attribution so
   the cohort that used to bucket as `compiler_fallback + request_timed_out`
   can be re-identified post-slice. Prefer this over CODEX's implicit
   "reuse existing blocker vocabulary" since collapsing the two sources
   into `blocker_accepted` would lose the signal.
2. **Three-test scope** (promotion, non-promotion preservation for
   `model_returned_non_schema`, caller-level early-return integration).
   The integration test is the one that actually proves the 90 s burn
   is gone.
3. **Loop-stranding risk named.** `build_work_recovery_plan` in
   `src/mew/work_session.py:4007` does not currently recognize the
   `"write-ready tiny draft blocker: unpaired_source_edit_blocked"`
   wait reason (I grepped — no match). So the next turn will fall
   through to a generic replan, and without Phase 4 wiring can feed
   back the same plan-item. Net still better than the status quo
   (1×12 s vs 1×90 s), but Phase 4 wiring should be the *next*
   slice, not a distant one.

## Bounded files

- `src/mew/work_loop.py` — split the `compiler_kind != "patch_draft"`
  branch at `:1686-1699` into (a) `compiler_kind == "patch_blocker"`
  with stable non-`model_returned_non_schema` code → mirror
  `:1665-1684` proposal-side return with `exit_stage="compiler_blocker"`,
  (b) existing fallback otherwise.
- `tests/test_work_session.py` — add the three tests adjacent to
  `test_tiny_write_ready_draft_lane_returns_wait_for_patch_blocker`
  at `:7402` so the tiny-lane group stays contiguous.

Nothing else. In particular: no `patch_draft.py` edit, no prompt
contract bump, no timeout/reasoning constant change, no recovery-plan
change.

## What to watch for in tests and review

- **`exit_stage` choice is load-bearing.** Confirm the new value is
  `"compiler_blocker"`, not reused `"blocker_accepted"`. Any existing
  `test_tiny_write_ready_draft_*` assertion that pins
  `exit_stage == "blocker_accepted"` must still hold for the
  proposal-side path — i.e. the split must not merge the two.
- **Integration test must actually prove the early return.** The
  `plan_work_model_turn`-level test should assert `len(observed) == 1`
  (only one model call total), not just that the wait-reason string
  matches. Without the call-count assertion, a regression where the
  caller re-enters generic THINK would be masked by the tiny branch
  still producing a valid wait.
- **`model_metrics.think.elapsed_seconds`.** Must equal the tiny
  elapsed (via `:2758-2771`), not tiny+generic. If the integration
  test doesn't pin this, the "90 s burn is gone" claim is not
  mechanically verified.
- **Metrics continuity.** The promoted branch must still populate
  `tiny_write_ready_draft_compiler_artifact_kind == "patch_blocker"`
  and `patch_draft_compiler_ran == True` (both already set at `:1632-1642`
  before the branch), and must set
  `tiny_write_ready_draft_fallback_reason = ""` on the blocker path so
  downstream calibration doesn't see a stale `compiler_unpaired_*`
  string alongside `outcome="blocker"`.
- **Recovery wiring gap.** Verify in review that the commit message
  or roadmap addendum explicitly states Phase 4 wiring for
  `unpaired_source_edit_blocked → add_paired_test_edit` inside
  `build_work_recovery_plan` is the intended next slice. Without that
  callout, the loop-stranding risk is easy to miss.
- **Fixture realism for the new test.** The
  `unpaired_source_edit_blocked` test needs a scenario where the model
  returns `kind="patch_proposal"` with hunks editing an `src/mew/<x>.py`
  path whose `convention_test_path_for_mew_source` result is *not* in
  the edited set. Reusing the existing `paired_src_test_happy` fixture
  with a model stub that drops the test hunk is the simplest shape;
  avoid invoking the real test-discovery helper inside the test body.
- **Calibration pre/post comparison.** The roadmap/replay commentary
  should explicitly say post-slice bundles for the `#402` cohort will
  carry `exit_stage="compiler_blocker"` and no `request_timed_out`
  failure, so `failure_mode_concentration` reshaping is mechanical,
  not a real regression. Bucketing should be by `exit_stage`, not by
  `failure.code`, during the comparison.
- **Not in scope, do not let in.** Watch for accidental expansion:
  prompt text edits, contract version bump to `v4`, timeout knob tweaks,
  reasoning-effort policy changes, or a preclassification shortcut
  before the tiny call. If any of those appear in the diff, revert
  them to preserve single-variable attribution.

## Summary

Approve landing this as a single isolated commit, using the CLAUDE
doc's `exit_stage="compiler_blocker"` and its three-test plan, with an
explicit one-line pointer to the Phase 4 recovery-wiring follow-up.
