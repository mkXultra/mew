# M6.24 Compile CompCert v0.1 Rerun - 2026-04-30

Task:

`terminal-bench/compile-compcert`

Repair under test:

`long_dependency_toolchain_compatibility_and_continuation_contract v0.1`

Artifact directory:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-long-dep-v01-compile-compcert-1attempt-20260430-0509`

## Result

This run is **diagnostic evidence**, not score evidence.

- Harbor result: cancelled by operator after the trial exceeded the intended
  wall-clock window
- Harbor stats: `n_errors=1`, exception `CancelledError`
- mew partial report phase: `running`
- mew observed wall before cancellation: `1693s`
- mew active tool: `run_command` #8
- final artifact: `/tmp/CompCert/ccomp` still missing/unproven

The cancellation was intentional. The process had already outlived the
intended `mew work --max-wall-seconds 1740` budget, and continuing would only
measure a runaway proof build instead of the M6.24 repair loop.

## What Improved

The v0.1 repair did surface useful state:

- `long_dependency_build_state.latest_build_status=running`
- `long_dependency_build_state.latest_build_tool_call_id=8`
- `strategy_blockers` included `toolchain_version_constraint_mismatch`
- progress included source preparation, configure, dependency generation, and
  a running build attempt

The model correctly found the source tree, detected the Coq compatibility
constraint, selected a compatible opam Coq `8.16.1` path, configured CompCert,
and reached the real Coq proof build.

## New Failure Shape

Two generic loop problems remain:

1. Running tool calls can outlive `--max-wall-seconds`.

   `mew work` only checked the wall-clock budget before model turns. Once the
   model launched a long `run_command`, the running subprocess could continue
   past the mew wall budget. Harbor eventually had to be cancelled externally.

2. The build command chose a full project build for a specific final artifact.

   The command entered `make -j"$(nproc)"`, which started the full CompCert Coq
   proof build. The task required `/tmp/CompCert/ccomp`; the next generic repair
   should steer long source-build tasks toward the shortest explicit target that
   produces the named artifact, not full proof/doc/all builds unless required.

## Decision

Do not escalate to `proof_5`.

Implement v0.2:

- cap `run_command` / `run_tests` timeout to the remaining `mew work`
  wall-clock budget;
- record the applied wall-clock tool ceiling in tool parameters;
- block tool execution if no bounded tool call can fit the remaining budget;
- surface `untargeted_full_project_build_for_specific_artifact` in
  `long_dependency_build_state.strategy_blockers`;
- extend THINK guidance to prefer the shortest explicit build target for the
  named final artifact.

Then run another one-trial same-shape `compile-compcert` speed rerun.
