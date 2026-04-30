# M6.24 `compile-compcert` Compatibility-Branch Budget Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> profile_contract -> long_dependency_compatibility_branch_budget_contract speed_1 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `19m 26s`
- result: speed gate passed

Trial:

- `compile-compcert__xd7Sf5E`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The compatibility-branch budget contract did not regress the selected
`compile-compcert` same-shape path. `mew work` exited cleanly with
`stop_reason=finish` after 7 work-session steps.

The run installed the narrow missing Menhir API dev package, configured the
existing CompCert 3.13.1 source for Linux `x86_64`, built `/tmp/CompCert/ccomp`,
built and installed the runtime library into the default path, ran a
default-path compile/link/run smoke producing `compcert-smoke:42`, and the
external verifier passed.

This speed proof shows the same benchmark shape remains viable after surfacing
`compatibility_branch_budget_contract_missing` and steering long
dependency/toolchain tasks toward an early coherent external/prebuilt branch
commitment. It does not close the selected gap. Broad measurement remains
paused until the resource-normalized proof reaches `5/5` or exposes the next
clean blocker.

Residual calibration signal:

- the final `mew-report.json` top-level `resume.long_dependency_build_state`
  was absent in this successful finish path. That is acceptable for this score
  repair; stale or missing internal finish ergonomics remain secondary to the
  external close gate.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/compile-compcert__xd7Sf5E/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/compile-compcert__xd7Sf5E/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/compile-compcert__xd7Sf5E/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-branch-budget-compile-compcert-1attempt-20260501-0545/compile-compcert__xd7Sf5E/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized `compile-compcert` proof_5 with sequential
`-k 5 -n 1` and refreshable `~/.codex/auth.json`. Broad measurement remains
paused.
