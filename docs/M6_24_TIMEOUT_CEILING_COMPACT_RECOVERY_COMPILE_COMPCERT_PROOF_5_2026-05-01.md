# M6.24 `compile-compcert` Timeout-Ceiling Compact-Recovery Proof 5

Task: `compile-compcert`

Selected chain:

```text
M6.24 -> long_dependency_toolchain_build_strategy_contract -> model_context_budgeting -> work_timeout_ceiling_full_context_recovery_prompt proof_5 -> compile-compcert
```

Result root:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-timeout-ceiling-compile-compcert-5attempts-seq-20260501-0356/result.json
```

## Summary

- requested shape: sequential `-k 5 -n 1`
- auth: refreshable `~/.codex/auth.json` mounted as `/codex-home/auth.json`
- frozen Codex target: `5/5`
- completed valid trials before stop: `3`
- score on valid completed trials: `2/3`
- cancelled trials: `1` operator cancellation after `5/5` became impossible
- Harbor root mean at stop: `0.500` because the cancelled trial is counted as
  an error
- close-gate result: missed

The timeout-ceiling compact-recovery speed proof did not regress: two valid
completed trials passed. The failed valid trial did not show another
full-context model-timeout recovery loop. Instead, it reached the real
CompCert source build and timed out in the final external-Flocq build branch
before `/tmp/CompCert/ccomp` existed.

## Trial Outcomes

| Trial | Reward | Notes |
|---|---:|---|
| `compile-compcert__kSjnmGt` | `1.0` | Built `/tmp/CompCert/ccomp`; external verifier passed. |
| `compile-compcert__dk4RUc3` | `1.0` | Built `/tmp/CompCert/ccomp`, recovered `runtime/libcompcert.a`, and external verifier passed. |
| `compile-compcert__tPDsncu` | `0.0` | Timed out while building with external Flocq after earlier serial compatibility probes consumed the wall budget. |
| `compile-compcert__vDfpvJD` | n/a | Cancelled intentionally after the close target was impossible. |

## Failed Trial Readout

The failed valid trial made real progress:

- fetched the `v3.13.1` source archive and grounded `/tmp/CompCert`;
- installed distro OCaml, Coq, Flocq, Menhir, and Menhir API packages;
- configured Linux `x86_64` with `-ignore-coq-version`;
- ran dependency generation after an initial generated-source failure;
- identified bundled Flocq / Coq 8.18 incompatibility:

```text
File "./flocq/Calc/Bracket.v", line 654, characters 0-27:
Error: The variable Z_div_mod_eq was not found in the current environment.
```

It then chose the correct source-supported branch, `-use-external-Flocq`, but
too late. The final build command was capped to `702.927s` by the remaining
wall-clock budget and timed out:

```text
make -j"$(nproc)" ccomp runtime
result.timed_out: true
kill_status: process_group_terminated
mew stop_reason: wall_timeout
external verifier: /tmp/CompCert/ccomp does not exist
```

## Failure Classification

This is not another runtime-link rule, source-identity rule, or compact
recovery regression. The model was able to think and act under the timeout
ceiling. The miss came from serially exploring compatibility branches and only
starting the known viable long build branch after too much wall budget was
gone.

Prior evidence matters:

- the v0.5 prebuilt override speed proof passed by configuring with
  `-ignore-coq-version`, `-use-external-Flocq`, and `-use-external-MenhirLib`;
- the v1.2 timeout-ceiling speed proof also passed with external Flocq /
  MenhirLib and default runtime install;
- this proof miss repeated the same winning strategy too late, not a new
  CompCert-specific dependency fact.

The selected gap is:

```text
gap_reason: long_dependency_compatibility_branch_budget_contract_missing
layer: profile_contract
```

The fix should not be another narrow inline THINK sentence. This is now a
profile/contract consolidation point for long dependency/toolchain builds:
source-provided compatibility flags, prebuilt external dependency packages,
and long-build wall-budget commitment need one coherent strategy boundary.

## Next

Continue M6.24 improvement phase. Do not resume broad measurement.

Next bounded repair:

```text
long_dependency_compatibility_branch_budget_contract
```

Implement this as a generic long-dependency profile/contract repair, then run
a one-trial same-shape `compile-compcert` speed proof before another
resource-normalized proof_5.
