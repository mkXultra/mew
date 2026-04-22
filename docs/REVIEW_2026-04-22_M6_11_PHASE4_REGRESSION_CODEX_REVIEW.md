# Phase4 Regression Review

## Findings

No blocking findings in the current uncommitted slice.

## Notes

- The scenario now enforces the frozen comparator identity as exact `(case_id, shape)` pairs rather than a loose id set. [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1512) builds the observed pairs, and [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1537) compares them against the expected `M6.6-A/B/C` mapping.
- Per-case provenance is now preserved in artifacts. [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1507) carries `source_reference` through, and [tests/test_dogfood.py](/Users/mk/dev/personal-pj/mew/tests/test_dogfood.py:655) asserts the emitted artifact mapping matches the fixture provenance from [tests/fixtures/work_loop/phase4_regression/m6_6_comparator_budget/scenario.json](/Users/mk/dev/personal-pj/mew/tests/fixtures/work_loop/phase4_regression/m6_6_comparator_budget/scenario.json:11).
- Median and budget computation remain correct for the pinned fixture. [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1487) reads `B0.iter_wall`, [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1488) applies the `× 1.10` ceiling, and [src/mew/dogfood.py](/Users/mk/dev/personal-pj/mew/src/mew/dogfood.py:1523) computes the median from the numeric comparator timings.
- Focused verification passed:
  - `PYTHONPATH=src python3 -m unittest tests.test_dogfood.DogfoodTests.test_run_dogfood_m6_11_phase4_regression_scenario tests.test_dogfood.DogfoodTests.test_run_dogfood_m6_11_all_subset_aggregate_reflects_full_coverage`

approve
