# M6.11 Blocker-Code Visibility Review

Date: 2026-04-22
Scope: `src/mew/proof_summary.py`, `tests/test_proof_summary.py`
Verdict: `approve`

## Findings

No findings in scoped files.

The change is additive as intended: it threads `blocker_code_counts` into the
top-level and per-cohort calibration summaries and renders that breakdown in the
text output without changing threshold math, dominant bundle-type math, or
cohort classification.

## Residual Risk Notes

- Test coverage is focused on the `unknown` cohort path. The implementation for
  `current_head` and `legacy` uses the same shared accumulation/finalization
  path, so this is acceptable for the slice, but those cohorts are not
  explicitly pinned by the new assertions.
- Local verification passed with
  `PYTHONPATH=src python3 -m unittest tests.test_proof_summary -q`. `pytest`
  was not available in the environment.
