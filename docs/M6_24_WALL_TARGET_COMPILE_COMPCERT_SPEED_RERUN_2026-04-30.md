# M6.24 Wall-Clock / Targeted-Artifact `compile-compcert` Speed Rerun

Task: `compile-compcert`

Result:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-1attempt-20260430-0615/2026-04-30__06-14-47/result.json`

Trial:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-1attempt-20260430-0615/2026-04-30__06-14-47/compile-compcert__42Z5Wsw/result.json`

Agent report:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-1attempt-20260430-0615/2026-04-30__06-14-47/compile-compcert__42Z5Wsw/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

## Summary

- trials: `1`
- errors: `0`
- reward: `1.0`
- runtime: `25m 38s`
- verifier: `3 passed`

This is score evidence for the v0.2 wall-clock / targeted-artifact repair.
The previous diagnostic failure shape changed materially:

- the early untargeted full build `make -j2 all` was surfaced as
  `untargeted_full_project_build_for_specific_artifact`;
- the run recovered from toolchain/version and dependency-generation blockers;
- the final material build used the explicit target `make -j2 ccomp`;
- the external verifier passed executable existence, functionality, and
  unsupported-feature rejection checks.

## Residual Signal

The final `mew-report.json` still contains stale/incomplete
`long_dependency_build_state` fields after success, including missing-artifact
entries. This did not affect the external verifier, but it is useful future
calibration evidence for report/resume cleanup. It is not a blocker for the
selected M6.24 score repair.

## Decision

Escalate to a five-trial same-shape proof for `compile-compcert`.

Close this selected repair only if the five-trial proof reaches the frozen
Codex target `5/5` or if a new repeated structural blocker is selected and
recorded in the decision ledger.
