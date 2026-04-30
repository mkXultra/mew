# M6.24 `compile-compcert` Artifact Proof Calibration Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> instrumentation/report -> long_dependency_timed_out_artifact_proof_calibration speed_1 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `15m 57s`
- result: speed gate passed

Trial:

- `compile-compcert__59Tggt5`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The v0.9 artifact-proof calibration did not regress the selected
`compile-compcert` same-shape path. The run built CompCert from the source tree,
built and installed runtime support, proved `/tmp/CompCert/ccomp` invokable, and
the external verifier passed.

Residual internal-report signal:

- `mew work` exited `0`, but the final `finish` was internally blocked because
  `long_dependency_build_state` still reported `/tmp/CompCert/ccomp` as
  `missing_or_unproven`.
- This is conservative proof-state residue from the stricter v0.9 calibration.
  It is not a score blocker in this run, but it should remain dossier evidence
  if later work needs finish-ergonomics calibration.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/compile-compcert__59Tggt5/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/compile-compcert__59Tggt5/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/compile-compcert__59Tggt5/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-proof-calibration-compile-compcert-1attempt-20260430-2102/compile-compcert__59Tggt5/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized `compile-compcert` proof_5 with `-k 5 -n 1`
and `auth.plus.json`. Broad measurement remains paused.
