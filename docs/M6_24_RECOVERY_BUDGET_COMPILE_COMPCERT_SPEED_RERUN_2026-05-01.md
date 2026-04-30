# M6.24 `compile-compcert` Recovery-Budget Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> tool/runtime -> long_dependency_final_recovery_budget_after_failed_validation speed_1 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `29m 25s`
- result: speed gate passed

Trial:

- `compile-compcert__whkZiag`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The v1.0 recovery-budget reserve did not regress the selected
`compile-compcert` same-shape path. `mew work` exited cleanly with
`stop_reason=finish` after 20 work-session steps. The run built CompCert from
source, applied the local Coq 8.18 / Flocq compatibility repair, built
`/tmp/CompCert/ccomp`, installed default runtime support, ran a default-path
compile/link/run smoke, and the external verifier passed.

This speed proof does not close the selected gap. It justifies returning to the
resource-normalized `compile-compcert` proof_5 with the refreshable auth shape.
Broad measurement remains paused until the proof either reaches `5/5` or
exposes the next clean structural blocker.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/compile-compcert__whkZiag/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/compile-compcert__whkZiag/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/compile-compcert__whkZiag/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-recovery-budget-compile-compcert-1attempt-20260501-0018/compile-compcert__whkZiag/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized `compile-compcert` proof_5 with sequential
`-k 5 -n 1` and refreshable `~/.codex/auth.json`. Broad measurement remains
paused.
