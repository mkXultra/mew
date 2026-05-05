# M6.24 `compile-compcert` Runtime-Link Recovery Speed Rerun

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> default_runtime_link_path_failed recovery v1 -> compile-compcert speed_1 -> proof_5 only if speed_1 is viable
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/result.json
```

## Summary

- requested shape: `-k 1 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- score: `1/1`
- frozen Codex target for the close proof: `5/5`
- runner errors: `0`
- Harbor mean: `1.000`
- total runtime: `30m 23s`
- result: speed gate passed

Trial:

- `compile-compcert__NiiEzri`: reward `1.0`

External verifier passed all three checks:

- `test_compcert_exists_and_executable`
- `test_compcert_valid_and_functional`
- `test_compcert_rejects_unsupported_feature`

## Readout

The generic `default_runtime_link_path_failed` recovery did not regress the
selected `compile-compcert` same-shape score path. The run completed without
Harbor exceptions, produced a valid `/tmp/CompCert/ccomp`, and passed the
Terminal-Bench verifier.

This validates the speed gate for the runtime-link recovery head. It does not
close M6.24 by itself; the selected close gate remains a resource-normalized
sequential `proof_5`.

## Evidence

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/compile-compcert__NiiEzri/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/compile-compcert__NiiEzri/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/compile-compcert__NiiEzri/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-recovery-compile-compcert-1attempt-20260501-1315/compile-compcert__NiiEzri/verifier/test-stdout.txt`

## Next

Escalate to resource-normalized sequential `compile-compcert` proof_5 with
`-k 5 -n 1` and refreshable `~/.codex/auth.json`. If proof_5 misses the frozen
`5/5` target, use `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`, this
runtime-link recovery evidence, and the source-acquisition evidence before
selecting another generic repair.
