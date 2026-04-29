# M6.24 Artifact Handoff Five-Trial Proof

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_external_artifact_path_and_cleanup_contract -> proof_5 make-mips-interpreter`

## Run

Task:

`terminal-bench/make-mips-interpreter`

Job:

`mew-m6-24-artifact-handoff-make-mips-interpreter-5attempts-20260429-2021`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-artifact-handoff-make-mips-interpreter-5attempts-20260429-2021/result.json`

## Result

- trials: `5`
- runner errors: `0`
- reward: `3/5`
- mean: `0.600`
- pass@2: `0.900`
- pass@4: `1.000`
- pass@5: `1.000`
- runtime: `27m 7s`
- frozen Codex target for `make-mips-interpreter`: `3/5`
- gap to target: `0/5`

Rewarded trials:

- `make-mips-interpreter__rpsLXge`
- `make-mips-interpreter__P7ZL8Zc`
- `make-mips-interpreter__3ukniQS`

Failed trials:

- `make-mips-interpreter__TNCGFSx`
- `make-mips-interpreter__Rb6mAN2`

## Observations

The v0.5 repair reached the frozen Codex target for this task shape. The two
direct handoff regressions from the previous proof did not recur:

- sibling-path-only frame proof was no longer accepted as sufficient for a
  verifier-read `/tmp/frame.bmp` contract;
- deferred cleanup removed stale `/tmp` runtime artifacts when self-verifier
  output surfaced them.

Three passing trials:

- `3ukniQS`: finished in 18 steps; all verifier checks passed.
- `P7ZL8Zc`: finished in 27 steps; deferred cleanup removed `/tmp/frame.bmp`
  and `/tmp/frame.png`; all verifier checks passed.
- `rpsLXge`: finished in 16 steps; deferred cleanup removed `/tmp/vm.err`,
  `/tmp/vm.out`, `/tmp/frame.bmp`, `/tmp/frame_*.bmp`, and
  `/tmp/frame_000001.bmp`; all verifier checks passed.

Two failures remained, but they are not the selected artifact-handoff blocker:

- `TNCGFSx`: frame existence and image similarity passed; VM stdout execution
  check failed because no expected startup text was captured.
- `Rb6mAN2`: VM execution and frame existence passed; image similarity failed
  at `0.8065` against the `0.95` threshold.

## Decision

Record `runtime_external_artifact_path_and_cleanup_contract` as stable enough
for this selected repair. The same-shape proof reached the Codex target with no
runner errors and no repeated selected structural blocker.

Next action:

`resume_broad_measurement -> M6.24 Batch 6 -> gpt2-codegolf`

If the next measured task exposes a gap above threshold or an accepted
structural blocker, return to the M6.24 gap-improvement loop with that new
evidence. Do not continue polishing `make-mips-interpreter` before measuring
the next Batch 6 task.
