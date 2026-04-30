# M6.24 `compile-compcert` Timeout-Ceiling Compact-Recovery Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> model_context_budgeting -> work_timeout_ceiling_full_context_recovery_prompt speed_1 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `16m 55s`
- result: speed gate passed

Trial:

- `compile-compcert__WAEEA9e`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The timeout-ceiling compact-recovery repair did not regress the selected
`compile-compcert` same-shape path. `mew work` exited cleanly with
`stop_reason=finish` after 9 work-session steps.

The run built CompCert 3.13.1 from source, used external Flocq and MenhirLib,
built `/tmp/CompCert/ccomp`, installed runtime support into the default
library path, ran a default-path compile/link/run smoke, and the external
verifier passed.

This speed proof shows that the same benchmark shape remains viable after
switching low-wall timeout-ceiling planning from full prompt context to
`compact_recovery`. It does not close the selected gap. Broad measurement
remains paused until the resource-normalized proof reaches `5/5` or exposes
the next clean blocker.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/compile-compcert__WAEEA9e/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/compile-compcert__WAEEA9e/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/compile-compcert__WAEEA9e/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-1attempt-20260501-0332/compile-compcert__WAEEA9e/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized `compile-compcert` proof_5 with sequential
`-k 5 -n 1` and refreshable `~/.codex/auth.json`. Broad measurement remains
paused.
