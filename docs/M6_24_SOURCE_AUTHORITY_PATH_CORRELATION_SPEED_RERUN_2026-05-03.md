# M6.24 Source-Authority Path-Correlation Speed Rerun

Date: 2026-05-03 JST

Task: `terminal-bench/compile-compcert`

Run:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-source-authority-path-correlation-compile-compcert-1attempt-20260502-2336`

## Result

- Trials: `1`
- Runner errors: `0`
- Harbor reward: `0.0`
- External verifier: `2/3` checks passed
- `mew-report.work_exit_code`: `1`
- `work_report.stop_reason`: `wall_timeout`
- `timeout_shape.latest_long_command_run_id`: `null`

The prior source-authority path-correlation blocker moved. The internal
long-build state now records `source_authority=satisfied`, and the external
verifier found `/tmp/CompCert/ccomp` executable.

The remaining external failure is runtime-link/default library lookup:

```text
/usr/bin/ld: cannot find -lcompcert: No such file or directory
```

## Classification

codex-ultra reviewed the rerun in
`docs/REVIEW_2026-05-03_M6_24_SOURCE_AUTHORITY_RERUN_CLASSIFICATION_CODEX.md`
and recommended repair.

Current gap class:

`long_command_continuation_dispatch_not_engaged`

The decisive internal evidence is that the same-shape run still has
`long_command_runs=[]` and `latest_long_command_run_id=null`. The work loop
computed long-command budget metadata, but production command execution still
used the blocking command path. The long command also included dependency
generation plus build/smoke work in one command, so its planned stage was
classified as `dependency_generation` and did not receive the reserve-preserving
budget path.

## Next Repair

Repair at the generic tool/runtime layer:

- dispatch `run_command` and `run_tests` through `ManagedCommandRunner` when
  `long_command_budget` requests `start_long_command`,
  `resume_idempotent_long_command`, or `poll_long_command`;
- persist `LongCommandRun` records from managed command snapshots;
- keep running/yielded managed command snapshots nonterminal and non-failing
  for the model loop;
- preserve reserve for compound dependency-generation commands that also start
  long build work.

Do not add a CompCert-specific runtime-link recipe. After the repair is
reviewed, rerun exactly one same-shape `compile-compcert` speed_1 before
`proof_5` or broad measurement.
