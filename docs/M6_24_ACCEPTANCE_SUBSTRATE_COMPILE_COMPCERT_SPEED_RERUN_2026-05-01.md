# M6.24 `compile-compcert` Acceptance-Substrate Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> acceptance_substrate_v1 -> compile-compcert speed_1 -> proof_5 only if speed_1 is viable
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `31m 10s`
- result: external speed gate passed

Trial:

- `compile-compcert__nJyWmyk`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The acceptance-substrate head did not break the external
`compile-compcert` same-shape score path. The run produced a functional
`/tmp/CompCert/ccomp`, installed enough runtime support for default verifier
use, and passed Terminal-Bench verification.

However, the run exposed an internal resume/acceptance calibration issue:
`long_dependency_build_state.expected_artifacts` included slash-compound
fragments from guidance text, specifically `/toolchain` from
`dependency/toolchain` and `/invokable` from `executable/invokable`. This made
the internal resume state still report missing artifacts even though the
external verifier passed.

This is not a Terminal-Bench-specific solver issue. It is a generic artifact
path extraction false positive. Fix it before spending the five-trial proof so
the acceptance substrate being measured is the intended one.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/compile-compcert__nJyWmyk/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/compile-compcert__nJyWmyk/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/compile-compcert__nJyWmyk/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-acceptance-substrate-compile-compcert-1attempt-20260501-0950/compile-compcert__nJyWmyk/verifier/test-stdout.txt`

## Next

Apply the bounded generic slash-compound path extraction repair, rerun one
same-shape `compile-compcert` speed proof, and escalate to sequential proof_5
only if that rerun remains viable.
