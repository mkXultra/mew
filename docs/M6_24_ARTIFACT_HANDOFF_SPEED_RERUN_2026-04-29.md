# M6.24 Artifact Handoff Speed Rerun

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_external_artifact_path_and_cleanup_contract -> speed_1 make-mips-interpreter`

## Run

Task:

`terminal-bench/make-mips-interpreter`

Job:

`mew-m6-24-artifact-handoff-make-mips-interpreter-1attempt-20260429-1950`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-handoff-make-mips-interpreter-1attempt-20260429-1950/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `1.0`
- runtime: `27m 30s`

External verifier:

- `test_vm_execution`: passed
- `test_frame_bmp_exists`: passed
- `test_frame_bmp_similar_to_reference`: passed

## Mew Report

Report:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-handoff-make-mips-interpreter-1attempt-20260429-1950/make-mips-interpreter__FuJEJJU/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

Observed:

- `work_exit_code`: `0`
- `stop_reason`: `max_steps`
- `step_count`: `30`
- `post_run_cleanup`: `{}`
- `resume.stale_runtime_artifact_risk`: `{}`

Important behavior:

- mew did not finish early with sibling-path-only frame evidence;
- the session stayed in the hard runtime repair loop until the final step;
- the final applied edit added MIPS SPECIAL3 `EXT` / `INS` support after a
  localized runtime failure;
- the work session hit `max_steps` immediately after that edit, before an
  internal finish/cleanup turn;
- the external verifier then ran the delivered `vm.js` and passed all checks.

This is a clean score pass for the same task shape, but it did not directly
exercise the new deferred-cleanup validator-output path because no final
self-verification `/tmp` artifact was created before handoff.

## Decision

The v0.5 repair is directionally positive enough to escalate under the M6.24
rerun budget rule:

- score improved on the speed shape: `1/1`;
- no wrong-path finish was accepted;
- no stale `/tmp/frame.bmp` handoff short-circuited the external verifier;
- the remaining proof question is stability across trials.

Next action:

`proof_5 make-mips-interpreter`

Do not resume broad measurement until the five-trial proof is recorded or a
written decision explains why escalation should be skipped.
