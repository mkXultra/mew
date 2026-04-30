# M6.24 `compile-compcert` Malformed-JSON Recovery Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> loop_recovery -> work_oneshot_malformed_json_plan_recovery speed_1 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `25m 37s`
- result: speed gate passed

Trial:

- `compile-compcert__Fb6UudL`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The malformed-JSON recovery repair did not regress the selected
`compile-compcert` same-shape path. `mew work` exited cleanly with
`stop_reason=finish` after 8 work-session steps. The run built CompCert from
source, applied the local Coq 8.18 / Flocq compatibility repair, built
`/tmp/CompCert/ccomp`, proved the executable, and the external verifier
passed.

This one-trial pass does not prove that malformed JSON will recur and be
recovered in the next proof. The focused unit test pins that specific recovery
path; this speed proof shows the same benchmark shape remains viable after the
loop-recovery change. Broad measurement remains paused until the
resource-normalized proof reaches `5/5` or exposes the next clean blocker.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/compile-compcert__Fb6UudL/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/compile-compcert__Fb6UudL/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/compile-compcert__Fb6UudL/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-json-plan-recovery-compile-compcert-1attempt-20260501-0152/compile-compcert__Fb6UudL/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized `compile-compcert` proof_5 with sequential
`-k 5 -n 1` and refreshable `~/.codex/auth.json`. Broad measurement remains
paused.
