# M6.24 Non-Timeout Source Retry Speed Rerun - 2026-05-03

## Run

Job:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-non-timeout-source-retry-compile-compcert-1attempt-20260503-0327`

Trial:

`compile-compcert__bgkpoge`

Command shape:

`terminal-bench/compile-compcert`, `-k 1 -n 1`, same Harbor wrapper, same
`mew work --oneshot --defer-verify` command template, `gpt-5.5`, Codex auth
mounted from `~/.codex/auth.json`.

## Result

- Harbor reward: `1/1`
- runner exceptions: `0`
- total runtime: `23m15s`
- `mew-report.work_exit_code`: `0`
- `mew-report.work_report.stop_reason`: `finish`
- external verifier: `3 passed`
- `timeout_shape.latest_long_command_run_id`: `null`
- `timeout_shape.latest_long_command_status`: `null`

The reviewed non-timeout source-acquisition retry repair is score-effective for
this same-shape run. The previous live blocker did not repeat.

## Internal Closeout Signal

The run is still not a clean internal closeout:

- `resume.long_build_state.status`: `blocked`
- `source_authority`: `unknown`
- `target_built`: `satisfied`
- `default_smoke`: `unknown`
- stale `current_failure.failure_class`: `dependency_generation_required`
- stale blocker excerpt: `Error: Can't find file ./Axioms.v`

This is narrower than the previous failure. The final successful command
contains terminal evidence for:

- `/tmp/CompCert/ccomp` exists, is executable, and reports version `3.13`;
- default runtime library exists at `/usr/local/lib/compcert/libcompcert.a`;
- default compile/link/run smoke succeeds with `smoke:11`;
- source/config readback repeats `/tmp/compcert-3.13.1.source` hash and
  `Makefile.config` with external Flocq/MenhirLib.

The reducer records the final attempt as `artifact_proof` and does not turn the
same terminal command into `default_smoke=satisfied` or clear the stale earlier
dependency-generation blocker.

## Classification Candidate

`final_artifact_and_default_smoke_closeout_not_projected_to_long_build_state`

This should be treated as a generic internal closeout/reducer defect, not a
Terminal-Bench solver. The score path passed; the remaining issue is that mew's
own long-build state is more pessimistic than the terminal evidence and finish
gate.

## Next Action

codex-ultra classified this as `REPAIR_NOW` at the reducer/closeout layer.
The local repair is recorded in
`docs/M6_24_FINAL_CLOSEOUT_PROJECTION_REPAIR_2026-05-03.md`.

Next: review the repair with codex-ultra. Do not run `proof_5` or broad
measurement until the repair is reviewed and one same-shape speed rerun records
clean internal closeout or a newer narrower gap.
