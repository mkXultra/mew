# M6.24 `compile-compcert` Compatibility Override Proof Result

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-5attempts-seq-20260430-0915/2026-04-30__09-15-21/result.json`

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- valid completed trials before stop: `3`
- score on valid completed trials: `2/3`
- Harbor stats at stop: `n_errors=1`, mean `0.5`
- trial 4: `CancelledError` from supervisor stop after the `5/5` close target became impossible

This rejects the selected close proof. It is not a reason to resume broad
measurement.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__87Ppbzz` | `1.0` | Built `/tmp/CompCert/ccomp`; external verifier passed. |
| `compile-compcert__EB5NJbe` | `1.0` | Built `/tmp/CompCert/ccomp`; external verifier passed. |
| `compile-compcert__ERSnx38` | `0.0` | Built `/tmp/CompCert/ccomp`, but external verifier failed on runtime library linking. |
| `compile-compcert__3kfrg3N` | n/a | Cancelled intentionally after the close target was already impossible. |

## Stop Decision

The frozen Codex target for this task shape is `5/5`. After one valid failure,
the close proof could no longer reach `5/5`. Continuing the remaining
sequential CompCert builds would spend wall time without changing the
close-gate decision.

The cancelled fourth trial is therefore recorded as operator cancellation, not
as score evidence.

## Failure Shape

The failed valid trial reached an apparently successful work-session finish:

- source identity was grounded as CompCert `3.13`;
- it used the source-provided `-ignore-coq-version` path;
- it patched the bundled Flocq proof for Coq `8.18`;
- it built `/tmp/CompCert/ccomp`;
- it ran a local smoke check and reported success.

The external verifier still failed:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
ccomp: error: linker command failed with exit code 1
```

The local smoke was too weak because it did not exercise the default runtime or
standard-library link path used by the verifier. The task requires a functional
compiler/toolchain, not just an executable compiler frontend.

## Next Repair Candidate

Generic class:

`long_dependency_runtime_link_library_contract`

Bounded repair:

For compiler/toolchain/source-build tasks, when the result must be functional
or invokable, a trivial return-only smoke binary is not enough. The loop should
surface missing runtime/link-library failures such as `cannot find -l...`,
prefer installing or configuring the project runtime/library target, and verify
a program that exercises the default runtime/link path before finish.

This is a generic compiler/toolchain policy repair, not a `compile-compcert` or
Terminal-Bench-specific solver.

## Evidence To Use Before Code Changes

- result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-5attempts-seq-20260430-0915/2026-04-30__09-15-21/result.json`
- failed trial report:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-5attempts-seq-20260430-0915/2026-04-30__09-15-21/compile-compcert__ERSnx38/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- failed verifier:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-compat-override-compile-compcert-5attempts-seq-20260430-0915/2026-04-30__09-15-21/compile-compcert__ERSnx38/verifier/test-stdout.txt`
- passing contrast trials:
  `compile-compcert__87Ppbzz`, `compile-compcert__EB5NJbe`

After repair, run `compile-compcert` speed_1 first. Escalate only if the speed
proof passes or materially changes the selected failure shape.
