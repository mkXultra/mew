# M6.18 Close Gate Audit - Implementation Failure Diagnosis Gate

Date: 2026-04-27 JST

## Verdict

M6.18 is closed.

The gate was intentionally small: add a diagnosis surface that separates
ordinary polish retry from structural repair before more mew-first product
dogfood. The implementation now records failure scope, evidence signals,
confidence, recommended route, and structural reason in the existing
mew-first calibration path, then exposes the counts through implementation-lane
metrics.

## Done-When Evidence

- `MewFirstAttempt` now includes `failure_scope`,
  `failure_scope_confidence`, `diagnosis_signals`, `recommended_route`, and
  `structural_reason`.
- `summarize_mew_first_calibration` reports counts for `failure_scope`,
  `structural_reason`, and `recommended_route`.
- `mew metrics --implementation-lane` exposes the diagnosis counts under
  `mew_first.diagnosis`.
- The `mew-first-implementation-loop` skill states the route:
  polish -> same-task retry, structural -> M6.14 repair, invalid task spec ->
  task correction, transient -> retry, ambiguous -> replay/proof collection.
- Recent failures are now classified through the new surface. On current
  `ROADMAP_STATUS.md`, `./mew metrics --mew-first --limit 10 --json` reports:
  - `failure_scope`: `structural=5`, `ambiguous=1`, `none_observed=4`
  - `structural_reason`: `supervisor_product_rescue_required=4`,
    `wrong_target_substitution=1`
  - `recommended_route`: `m6_14_repair=5`,
    `collect_replay_or_reviewer_evidence=1`, `no_action=4`

## Validation

- `uv run pytest -q tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py --no-testmon`
- `uv run ruff check src/mew/mew_first_calibration.py src/mew/implementation_lane_baseline.py tests/test_mew_first_calibration.py tests/test_implementation_lane_baseline.py`
- `./mew metrics --mew-first --limit 10 --json`
- `./mew metrics --implementation-lane --limit 10`

## Caveats

- The diagnosis is evidence-based triage, not an automatic truth oracle.
  `ambiguous` remains a first-class output and should trigger replay/proof
  collection before M6.14 structural repair.
- `supervisor_product_rescue_required` is intentionally treated as a structural
  signal for failed mew-first attempts. If future evidence shows this is too
  coarse, refine the reason enum rather than bypassing the diagnosis gate.
- Larger reference-derived changes from `ADOPT_FROM_REFERENCES.md` and
  `REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` remain deferred until the
  diagnosis surface points at a specific structural reason.

## Next

Resume M7. Future mew-first implementation failures in M7+ should pass through
M6.18 diagnosis before either same-task polish retry or M6.14 substrate repair.
