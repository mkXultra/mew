# M6.24 Build-Timeout Recovery Speed Rerun

Date: 2026-05-02

Artifact:
`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-build-timeout-recovery-compile-compcert-1attempt-20260502-1755`

## Result

- Terminal-Bench reward: `0.0`
- Runner exceptions: `0`
- Total runtime: `30m 23s`
- Trial: `compile-compcert__qXd8U2b`
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`
- External verifier: failed because `/tmp/CompCert/ccomp` was not present.

## What Improved

The prior repair moved the failure forward.

- The run reached authoritative source/archive readback.
- It installed the required toolchain/dependency packages.
- It configured CompCert with
  `-ignore-coq-version -use-external-Flocq -use-external-MenhirLib`.
- It ran `make depend`.
- It reached the explicit final build command:
  `make -j"$(nproc)" ccomp`.
- The previous same-evidence unreached `make install` masking no longer appears
  to be the primary failure; the live process was killed while the final build
  was still running.
- Compact recovery was materially smaller than the prior failure shape:
  final recovery prompts were about `53k-56k` chars rather than about `124k`.

## Current Failure Class

Primary class:
`long-build wall-time/continuation budget`.

This is not primarily another toolchain-strategy failure. The selected
dependency branch was plausible and the task was inside the final compiler
build. It is also not a closeout-verification failure because no final artifact
had been produced before the external verifier ran.

The decisive signal is budget:

- command `10` entered `make -j"$(nproc)" ccomp`;
- command `10` had `exit_code=null` in the report because the work loop stopped
  under wall time;
- the final model turns had only about `23.8s`, `11.5s`, and `5.4s`;
- the work loop stopped with `wall_timeout`.

## Decision

Do not start another narrow source-authority, toolchain-strategy, or closeout
reducer repair from this run.

Run one documented timeout-shape diagnostic before changing source:

```text
M6.24 -> long_dependency/toolchain gap -> wall-time/continuation budget ->
one same-shape compile-compcert speed_1 with matched outer timeout and larger
mew --max-wall-seconds
```

The diagnostic asks one question:

```text
Does the current strategy pass when the final ccomp build is allowed to finish?
```

If the diagnostic passes only with extra wall time, record that M6.24 needs a
generic continuation/budget repair before proof_5. If it still times out inside
`make ccomp`, open that tool/runtime repair immediately.

## Next Run Shape

Use the same task/model/permissions, but match the Harbor agent timeout and
`mew --max-wall-seconds` headroom. This is a one-run diagnostic, not broad
measurement and not proof_5.

Close only if all usual clean-closeout gates hold:

- reward `1.0`;
- runner errors `0`;
- `mew work` exit `0`;
- `/tmp/CompCert/ccomp` invokable;
- default compile/link/run smoke passed;
- `source_authority=satisfied`;
- no stale `current_failure` or active strategy blockers.
