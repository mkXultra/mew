# M6.24 `compile-compcert` Resource-Normalized Proof Result

Task: `compile-compcert`

Result root:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-5attempts-seq-20260430-0727/2026-04-30__07-26-40/result.json`

## Summary

- requested shape: `-k 5 -n 1`
- auth: `auth.plus.json` mounted as `/codex-auth/auth.json`
- valid completed trials before stop: `2`
- score on valid completed trials: `1/2`
- runner errors before stop: `0`
- trial 3: `CancelledError` from supervisor stop after the `5/5` close target became impossible

This is enough to reject the selected close proof. It is not enough to resume
broad measurement.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__z4XjZ35` | `1.0` | Built `/tmp/CompCert/ccomp`; external verifier passed all three tests. |
| `compile-compcert__gGYcm6o` | `0.0` | `mew work` ended with `wall_timeout`; `/tmp/CompCert/ccomp` was missing. |
| `compile-compcert__YrYh8f4` | n/a | Cancelled intentionally after the close target was already impossible. |

## Stop Decision

The frozen Codex target for this task shape is `5/5`. After one valid failure,
the close proof could no longer reach `5/5`. Continuing three more sequential
CompCert builds would spend wall time without changing the close-gate decision.

The cancelled third trial is therefore recorded as operator cancellation, not
as score evidence.

## Failure Shape

The failed valid trial made real source/toolchain/configure/build progress and
did not reproduce the earlier parallel-resource contention issue. The important
failure shape is:

- source identity was grounded as CompCert `3.13.1`;
- distro Coq `8.18.0` caused `./configure` to reject the version;
- the model moved into a heavy local OPAM Coq/Menhir strategy;
- it did not first inspect or try source-provided compatibility/override
  configure options;
- the session used wall budget on alternate toolchain setup and repeated build
  continuation;
- the final verifier failed because `/tmp/CompCert/ccomp` did not exist.

## Next Repair Candidate

Generic class:

`long_dependency_toolchain_compatibility_override_order_contract`

Bounded repair:

For long dependency/source-build tasks, when a configure/build step rejects an
installed dependency version but the required source tree is otherwise grounded,
the work loop should prefer source-provided compatibility/override flags and
targeted configure-help inspection before building an alternate toolchain from
scratch. Alternate toolchain construction remains allowed, but only after a
cheap compatibility override probe is invalidated or unavailable.

This is a generic source-build policy repair, not a `compile-compcert` or
Terminal-Bench-specific solver.

## Evidence To Use Before Code Changes

- failed trial:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-5attempts-seq-20260430-0727/2026-04-30__07-26-40/compile-compcert__gGYcm6o/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- passing contrast trial:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-wall-target-compile-compcert-5attempts-seq-20260430-0727/2026-04-30__07-26-40/compile-compcert__z4XjZ35/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`
- decision ledger:
  `docs/M6_24_DECISION_LEDGER.md`
- gap loop:
  `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`

After the repair, run `compile-compcert` speed_1 first. Escalate only if the
speed proof passes or materially changes the selected failure shape.
