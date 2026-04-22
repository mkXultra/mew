# Findings

No active blocker-level findings.

The two previously reported correctness issues are resolved in the current uncommitted diff:

1. Summary-time head lookup failure now degrades to `unknown`, not fabricated `legacy`, via `_cohort_label(...)` in [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:129). The follow-up tests pin both the patched-empty-head path and the non-git subprocess failure path at [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:558) and [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py:581).
2. The stale-head cache has been removed. `_current_git_head()` in both [`src/mew/work_replay.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_replay.py:50) and [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:113) now shells out on each call instead of freezing the first observed `HEAD`, so the replay writers no longer persist stale cohort tags across a long-lived process.

Beyond that, the slice still matches the bounded goal cleanly:

- replay writers add `git_head`, `bucket_tag`, and `blocker_code` additively in [`src/mew/work_replay.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_replay.py:239) and [`src/mew/work_replay.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_replay.py:331)
- calibration reporting adds `current_head` / `legacy` / `unknown` cohort summaries alongside the existing top-level aggregate in [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:340) and [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:483)
- top-level threshold math remains unchanged; the existing aggregate totals, rates, and gate predicates are still computed at the top level in [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py:431)

# Verdict

`approve`

I do not see a remaining correctness or contract blocker in the scoped diff. The cohort split is additive, the prior misclassification paths are fixed, and the current tests cover the intended bounded behavior closely enough for this slice.

# Validation

- Inspected the current uncommitted diff directly for:
  - [`src/mew/work_replay.py`](/Users/mk/dev/personal-pj/mew/src/mew/work_replay.py)
  - [`src/mew/proof_summary.py`](/Users/mk/dev/personal-pj/mew/src/mew/proof_summary.py)
  - [`tests/test_work_replay.py`](/Users/mk/dev/personal-pj/mew/tests/test_work_replay.py)
  - [`tests/test_proof_summary.py`](/Users/mk/dev/personal-pj/mew/tests/test_proof_summary.py)
- Executed `PYTHONPATH=src python3 -m unittest tests.test_work_replay tests.test_proof_summary`
- Re-checked the prior blocker repro: stamped bundles now land in `calibration.cohorts.unknown` when summary-time head lookup returns `""`
- Re-checked the stale-head repro by patching consecutive `subprocess.run` results; `_current_git_head()` now returns fresh values on repeated calls in both modules
