# M6.11 Blocker-Code Visibility Next Step — Codex

Date: 2026-04-22  
HEAD: `f61e657`

## Verdict

**Not yet.**

## Why

The visibility gap is real, but it is not the next bounded implementation
slice.

- In [`src/mew/proof_summary.py`](../src/mew/proof_summary.py),
  `_summarize_patch_draft_compiler_bundle(...)` and
  `_summarize_model_failure_bundle(...)` already read and retain
  `blocker_code` / `bucket_tag`, but
  `summarize_m6_11_replay_calibration(...)` only aggregates
  `calibration_bundle_type`, and `format_proof_summary(...)` only renders those
  coarse bundle-type counts.
- The current live current-HEAD cohort therefore collapses two different
  compiler blockers into the same visible bucket:
  `patch_draft_compiler.other=2`, even though the underlying fresh bundles are
  `unpaired_source_edit_blocked` and `insufficient_cached_test_context`.
- But the roadmap and the latest local review state already put the immediate
  gap somewhere else: first fresh **non-`#402`** current-HEAD evidence, not
  finer reporting on the same `#402` pair.
- Adding blocker-code incidence visibility now would only make the current
  two-bundle `#402` sample easier to read. It would not answer the actual next
  close-gate question: whether fresh M6.11-era live evidence diversifies beyond
  that single historical source.

This matches the current `ROADMAP_STATUS.md` next action: collect fresh
current-HEAD bundles first, then rerun calibration.

## Safe As Fresh Non-`#402` Evidence Source?

**No.**

A `proof-summary` / textual-formatting slice would be reporting-only. It would
re-cut existing replay bundles, mostly the current `#402` pair, and would not
produce a fresh live bounded implementation slice from a new task/session.

## Deferred Follow-Up

Once the first non-`#402` current-HEAD live slice exists, this becomes a good
small follow-up:

- add additive `blocker_code_counts` at top level and per cohort in
  `summarize_m6_11_replay_calibration(...)`
- render them in `format_proof_summary(...)` without changing threshold math
- add focused tests in [`tests/test_proof_summary.py`](../tests/test_proof_summary.py)
  proving two `patch_draft_compiler.other` bundles with different blocker codes
  stay coarse in bundle-type counts but split cleanly in blocker-code counts

That would improve operator legibility, but it should follow, not precede, the
next fresh non-`#402` evidence collection step.
