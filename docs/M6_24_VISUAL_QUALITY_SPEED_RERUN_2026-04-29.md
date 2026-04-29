# M6.24 Visual Quality Speed Rerun

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_visual_artifact_quality_contract -> speed_1 make-mips-interpreter`

## Run

Task:

`terminal-bench/make-mips-interpreter`

Job:

`mew-m6-24-visual-quality-make-mips-interpreter-1attempt-20260429-1845`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-visual-quality-make-mips-interpreter-1attempt-20260429-1845/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `1.0`
- runtime: `19m 42s`

External verifier:

- `test_vm_execution`: passed
- `test_frame_bmp_exists`: passed
- `test_frame_bmp_similar_to_reference`: passed

## Mew Report

Report:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-visual-quality-make-mips-interpreter-1attempt-20260429-1845/make-mips-interpreter__QfovMsf/agent/terminal-bench-harbor-smoke/unknown-task/mew-report.json`

Observed:

- `work_exit_code`: `0`
- `stop_reason`: `finish`
- `step_count`: `15`
- verifier command: `node vm.js`
- `post_run_cleanup`: `{}`

Important behavior:

- mew grounded the provided ELF/source/WAD contract before final completion;
- a first finish attempt was blocked by the implementation-contract source
  evidence guard, then mew continued instead of falsely finishing;
- final verifier-shaped command output included Doom Shareware boot markers,
  `I_InitGraphics` framebuffer/stdout markers, and fresh frame creation;
- explicit artifact validation checked both `/tmp/frame_000001.bmp` and
  `/tmp/frame.bmp` as matching `640x400` top-down `32bpp` BMPs with nonblank
  content;
- mew removed `/tmp/frame.bmp` and `/tmp/frame_000001.bmp` before returning to
  the external verifier, so the harness recreated them via `node vm.js`.

## Decision

The v0.4 runtime visual artifact quality contract moved the task from
format-only/self-consistency acceptance to grounded expected output evidence on
this same shape.

Because the speed rerun passed `1/1`, the M6.24 rerun budget rule allows
escalation to a five-trial same-shape proof. The frozen Codex target for this
task remains `3/5`.

Next action:

`proof_5 make-mips-interpreter`

Do not resume broad measurement until the five-trial proof is recorded or a
written decision explains why escalation should be skipped.
