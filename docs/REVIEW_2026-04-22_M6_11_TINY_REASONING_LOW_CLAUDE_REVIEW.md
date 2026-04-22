# M6.11 Tiny Reasoning-Low — Slice Review (Claude)

Subject: proposal in
`docs/REVIEW_2026-04-22_M6_11_POST_C0E_NEXT_SLICE_CLAUDE.md`
(tiny write-ready draft lane forces `reasoning_effort="low"`),
weighed against the competing proposal in
`docs/REVIEW_2026-04-22_M6_11_POST_C0E_NEXT_SLICE_CODEX.md`
(pairing-aware tiny-lane preclassification) and the evidence
after `c0eba4c` on task `#402`.

## Verdict

**Approve** as the next bounded M6.11 Phase 3 slice. One minor
revision suggestion below; not blocking.

## Rationale

1. **Architecture fit is clean.** The change is one local lever in
   `_attempt_write_ready_tiny_draft_turn`
   (`src/mew/work_loop.py:1515`). It does not touch
   `select_work_reasoning_policy`
   (`src/mew/reasoning_policy.py:84`), the regular write-ready THINK
   path, the tiny prompt text, the patch compiler, the fallback
   wiring, or the preview translator. The caller keeps passing its
   inherited `reasoning_effort`; the tiny lane logs it as
   observability and overrides the env scope locally. Fork-path
   propagation is sound: the multiprocess guard at
   `work_loop.py:116-168` uses `fork`, so the child inherits the
   `MEW_CODEX_REASONING_EFFORT` set by `codex_reasoning_effort_scope`
   (`reasoning_policy.py:131-145`). Restore-on-exit keeps the
   fallback THINK path at the caller's effort.

2. **Evidence alignment is the strongest argument.** Turn `1825`
   shows `elapsed≈30.017s` and `timeout_budget_utilization≈1.0006`
   with `patch_draft_compiler_ran=false` — a genuine full-budget
   model burn, not a sub-second fast-fail. That was exactly the
   disambiguation the `c0eba4c` observability slice was scoped to
   produce, and it picks *prompt/reasoning-cost* as the lever, not
   guard/transport. The tiny contract has already been narrowed to a
   translation task (pick a path from `active_work_todo.source.
   target_paths`, cite exact `old` from `cached_window_texts`, emit
   `patch_proposal` or `patch_blocker`), so `medium` reasoning has
   no exploration surface to spend tokens on — it just consumes the
   budget. Forcing `low` directly tests that hypothesis.

3. **Calibration value is high and deterministic.** The slice
   produces a clean A/B against the existing `v2` (medium) cohort
   on `tiny_write_ready_draft_elapsed_seconds` /
   `exit_stage`. The decision tree in the proposal
   (elapsed drops → reassess gate; elapsed stays → per-window
   `cached_window_texts[i].text` cap; mixed compiler_fallback →
   structural per-file split or anchor-based matching) closes out
   three distinct next-slice branches from one experiment. Whatever
   the data says, the next slice is picked without new plumbing.

4. **Right next experiment vs the Codex alternative.** The Codex
   proposal (pairing-aware preclassification) targets turns
   `1822`/`1824`, which **already** produced
   `unpaired_source_edit_blocked` blockers and are in the 2 of 9
   `compiler_bundles`, not the 7 of 9 `work-loop-model-failure`
   timeout bundles driving the `0.778` dominant share. Removing the
   already-working blocker paths from the stream wouldn't move the
   dominant share and could arguably make it worse (7/7 = 1.0 if
   those two bundles disappear from the denominator without a
   compensating change in the timeout bucket). The reasoning-effort
   slice attacks the actually-dominant bucket with a lighter change.
   If it moves the needle, Codex's preclassification becomes a
   defensive hygiene follow-up; if it doesn't, the proposal's
   per-window cap branch is the natural next slice, and
   preclassification remains a viable parallel option.

5. **Fallback preserved.** The caller's `reasoning_policy.effort`
   is still honored by the regular write-ready THINK path at
   `work_loop.py:2758` and `:2799`. Any case where `low` reasoning
   is insufficient falls through to the regular path at the full
   effort the caller chose. No loss of the "real" reasoning surface.

## Minor revision suggestion (non-blocking)

Reconsider the `WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION`
bump from `"v2"` to `"v3"`. The tiny *prompt text* is unchanged by
this slice; only the reasoning budget moves. The proposal already
adds a first-class `tiny_write_ready_draft_reasoning_effort`
metric, which is the cleaner cohort split key. Keeping the prompt
contract version at `"v2"` and relying on the new reasoning-effort
field for calibration bucketing avoids conflating two orthogonal
dimensions and keeps the semantics of "prompt contract version =
prompt text shape" intact for the *next* real prompt change.

If the team prefers to bump regardless (so any
`tiny_write_ready_draft_prompt_contract_version`-grouped analysis
automatically sees a cohort break), that's defensible — the Claude
proposal acknowledges the rationale. But flag it in the commit
message so future prompt-text changes don't stumble on "is `v3`
reasoning-only or does it include prompt changes?"

This is a code-hygiene nit; it does not block the slice.

## Risks and calibration hygiene (already flagged in the proposal,
confirming)

- **Cohort split on first rerun** needs manual exclusion of `v2`
  medium-reasoning bundles from the post-slice `dominant_share`
  evaluation. `proof_summary.summarize_m6_11_replay_calibration`
  (`src/mew/proof_summary.py:202`) does not auto-split on the
  prompt-contract or reasoning-effort keys, so operators doing the
  first comparison must filter by `tiny_write_ready_draft_
  reasoning_effort` on the bundle side. Acceptable — the proposal
  names this.
- **Diagnostic dilution** if bundled with other changes. Land as a
  single isolated commit. The working tree already scopes it to
  `src/mew/work_loop.py` + `tests/test_work_session.py`; keep it
  that way.
- **No widening beyond Phase 3.** Confirmed: no Phase 4 recovery
  vocabulary work, no timeout budget change, no per-window text
  cap, no blocker-stop short-circuit, no stream-delta timestamping.
  The slice stays inside the Phase 2/3 calibration checkpoint scope
  per `docs/PROPOSE_M6_11_CLOSE_GATE_STRENGTHEN_2026-04-22.md` §3.3.

## Summary

Approve. The slice is the right next experiment given `#402` turn
`1825`: a one-line reasoning-budget lever that directly tests the
remaining hypothesis (reasoning tokens are the at-budget burn) and
produces a deterministic fork for picking the slice after this one.
It beats the Codex pairing-aware alternative on dominant-bucket
coverage, has minimal blast radius, preserves the full-effort
fallback, and reuses existing calibration infrastructure. The only
open nit is whether to bump the prompt contract version when the
prompt text is unchanged; that can be resolved in-commit.
