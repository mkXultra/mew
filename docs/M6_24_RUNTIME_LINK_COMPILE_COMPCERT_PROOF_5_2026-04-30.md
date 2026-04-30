# M6.24 `compile-compcert` Runtime Link Proof Result

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-5attempts-seq-20260430-1119/2026-04-30__11-19-01/result.json`

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- valid completed trials before stop: `1`
- score on valid completed trials: `0/1`
- Harbor stats at stop: `n_errors=1`, mean `0.0`
- trial 2: `CancelledError` from supervisor stop after the `5/5` close target became impossible

This rejects the selected close proof. It is not a reason to resume broad
measurement.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__mhwxWgK` | `0.0` | Fresh container spent the wall/model budget building version-pinned OPAM Coq/Flocq dependencies; `/tmp/CompCert/ccomp` was still missing. |
| `compile-compcert__mcdaHee` | n/a | Cancelled intentionally after the close target was already impossible. |

## Stop Decision

The frozen Codex target for this task shape is `5/5`. After one valid failure,
the close proof could no longer reach `5/5`. Continuing the remaining
sequential CompCert builds would spend wall time without changing the
close-gate decision.

The cancelled second trial is therefore recorded as operator cancellation, not
as score evidence.

## Failure Shape

The failed valid trial preserved the long dependency state, but chose a slow
toolchain route:

- it grounded CompCert `3.13.1` source under `/tmp/CompCert`;
- it observed distro package candidates including Coq `8.18`;
- it saw the Coq version rejection and resume state surfaced
  `compatibility_override_probe_missing`;
- it then installed OPAM/OCaml and started version-pinned source-built
  `coq.8.16.1` / `coq-flocq` dependency construction;
- the work session reached `1720s` wall elapsed, model timeout/failure pressure,
  and `/tmp/CompCert/ccomp` remained missing.

The v0.4 speed pass on the same task shape used a shorter route: install
prebuilt distro dependencies, configure through source compatibility overrides,
patch the bundled proof surface as needed, build `ccomp`, build/install the
runtime library, and run a runtime-link smoke.

## Next Repair Candidate

Generic class:

`long_dependency_prebuilt_dependency_override_precedence_contract`

Bounded repair:

For source-build/toolchain tasks, if package-manager prebuilt dependencies are
available and the project exposes or likely supports a compatibility/ignore
override, the loop should try the prebuilt dependency plus source override path
before constructing a version-pinned source-built dependency/toolchain. If it
does choose the source-built route, reentry should preserve that it skipped an
unresolved compatibility override path.

This is a generic long dependency strategy repair, not a `compile-compcert` or
Terminal-Bench-specific solver.

## Evidence To Use Before Code Changes

- result:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-5attempts-seq-20260430-1119/2026-04-30__11-19-01/result.json`
- failed trial report:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-5attempts-seq-20260430-1119/2026-04-30__11-19-01/compile-compcert__mhwxWgK/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- passing contrast report:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-runtime-link-compile-compcert-1attempt-20260430-1050/2026-04-30__10-49-08/compile-compcert__dHLBSPJ/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

After repair, run `compile-compcert` speed_1 first. Escalate only if the speed
proof passes or materially changes the selected failure shape.
