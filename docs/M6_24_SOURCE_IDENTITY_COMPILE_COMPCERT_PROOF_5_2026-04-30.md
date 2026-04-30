# M6.24 `compile-compcert` Source Identity / Empty Response Proof 5

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> implementation_profile/no_lane_change -> long_dependency_source_archive_identity_and_empty_response_recovery_contract -> proof_5 compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/result.json
```

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- score: `4/5`
- frozen Codex target: `5/5`
- runner errors: `0`
- Harbor mean: `0.800`
- total runtime: `1h 52m 15s`
- result: close target missed

The v0.8 source-identity / empty-response repair is directionally validated:
four trials passed, including archive/tag/root source identity acceptance,
CompCert source build, default runtime support installation, and external
verifier success. The selected close gate still stays open because one valid
trial failed.

Passing trials:

- `compile-compcert__cy4MZxb`: reward `1.0`
- `compile-compcert__YUardSK`: reward `1.0`
- `compile-compcert__PRG3fhw`: reward `1.0`
- `compile-compcert__HyUZXPt`: reward `1.0`

Failed trial:

- `compile-compcert__zoD2LKy`: reward `0.0`

## Failed Trial Readout

The failed trial did not reproduce the earlier source-identity or empty
assistant-response blocker. It reached the real CompCert source path and
progressed through dependency/setup repair, then timed out during a final
patched build:

```text
tool_call_id=13
command: make -j10 ccomp
result.timed_out: true
result.exit_code: null
incomplete_reason: tool_timeout
external verifier: /tmp/CompCert/ccomp does not exist
```

The report/resume state was inconsistent with the external verifier:

```text
long_dependency_build_state.expected_artifacts[0].status = proven
long_dependency_build_state.missing_artifacts = []
```

but the final command timed out before `/tmp/CompCert/ccomp` existed, and the
external verifier failed all checks because the file was missing.

## Dossier Preflight

This is not a clean new source-identity blocker. It is a repeated
long-dependency wall-budget/report-calibration issue:

- v0.2 already handled wall-clock / targeted-artifact build shape.
- v0.8 speed proof showed local Flocq patching can pass.
- This proof miss came from artifact-proof calibration after a timed-out build,
  not from another missing Flocq-specific prompt rule.

`codex-ultra` review session `019dde0c-5719-7af1-b488-5b929e6c95af`
classified the next bounded repair as `instrumentation/report`: timed-out or
failed long-dependency build commands must not mark required final artifacts as
proven, and timed-out final builds must preserve missing artifact state.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/compile-compcert__zoD2LKy/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/compile-compcert__zoD2LKy/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/compile-compcert__zoD2LKy/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-identity-compile-compcert-5attempts-seq-20260430-1808/compile-compcert__zoD2LKy/verifier/test-stdout.txt`

## Next

Continue M6.24 improvement phase. Do not resume broad measurement.

Next bounded repair:

```text
long_dependency_timed_out_artifact_proof_calibration
```

After repair, run a one-trial same-shape speed proof for `compile-compcert`
before any proof_5 or broad measurement.
