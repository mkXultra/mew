# M6.24 Visual Quality Five-Trial Proof

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> runtime_visual_artifact_quality_contract -> speed_1 passed -> proof_5 make-mips-interpreter`

## Run

Task:

`terminal-bench/make-mips-interpreter`

Job:

`mew-m6-24-visual-quality-make-mips-interpreter-5attempts-20260429-1908`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-visual-quality-make-mips-interpreter-5attempts-20260429-1908/result.json`

Command shape:

- trials: `-k 5 -n 5`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: `30`
- result: `1/5`
- exceptions: `0`
- pass@2: `0.4`
- pass@4: `0.8`
- pass@5: `1.0`
- total runtime: `30m 35s`

## Result

The proof did not reach the frozen Codex target for this task:

- mew: `1/5`
- Codex target: `3/5`
- gap: `-2/5`

Reward buckets:

- reward `1.0`: `make-mips-interpreter__gEJSUfJ`
- reward `0.0`: `make-mips-interpreter__rzf7QBU`,
  `make-mips-interpreter__RpsNHsE`, `make-mips-interpreter__Wbr7XBC`,
  `make-mips-interpreter__XsB9GXa`

The v0.4 visual quality contract is useful but not sufficient. It removed the
previous repeated `320x200` format-only finish pattern in this proof, but the
remaining failures expose a narrower verifier-handoff gap plus ongoing hard VM
runtime repair gaps.

## Trial Notes

### `make-mips-interpreter__gEJSUfJ`

Passed.

Observed from `mew-report.json`:

- `work_exit_code`: `0`
- `stop_reason`: `finish`
- `step_count`: `13`

The session verified exact `node vm.js`, Doom boot markers, `640x400` frame
artifacts, and cleaned temporary `/tmp` frames before handoff. The external
verifier passed VM execution, frame existence, and frame similarity.

### `make-mips-interpreter__XsB9GXa`

Failed only external stdout timing:

- external `test_vm_execution`: failed
- external `test_frame_bmp_exists`: passed
- external `test_frame_bmp_similar_to_reference`: passed

The internal final verifier validated:

```text
PPM ok: frames/frame000001.ppm 640x400
BMP ok: frames/frame000001.bmp and /tmp/frame.bmp 640x400
content ok: nonblack_pixels=256000/256000 sampled_unique_colors=237
```

`post_run_cleanup` was `{}`. The fallback cleanup did not recognize this
validator output as evidence that `/tmp/frame.bmp` had been created during
self-verification. The stale artifact survived into the external verifier,
which then terminated `node vm.js` before the expected stdout marker appeared.

### `make-mips-interpreter__rzf7QBU`

Finished internally, but external verifier failed all three checks because
`/tmp/frame.bmp` did not exist.

The final internal evidence proved `frames/frame000001.bmp` and a root
`frame000001.bmp` copy:

```text
path frames/frame000001.bmp exists True size 1024054
path frame000001.bmp exists True size 1024054
tmp_frame_before_cleanup False -1
```

The task's fresh verifier expected `/tmp/frame.bmp`. The finish gate accepted
a semantically valid frame at the wrong artifact path.

### `make-mips-interpreter__RpsNHsE`

Timed out after a real VM/runtime repair path. The last verifier reached Doom
startup but stopped at a runtime/source gap:

```text
R_TextureNumForName: SW1BLUE not found
vm.js failed at pc=0x40e6d4 step=350000000: Error: step limit reached
```

This remains a hard VM/runtime task-solving gap, not a visual quality or
handoff cleanup false finish.

### `make-mips-interpreter__Wbr7XBC`

Timed out after a real VM/runtime repair path. The last verifier failed before
frame creation:

```text
vm error: Error: special 52 at 0x439e3c
Error: ENOENT: no such file or directory, open '/tmp/frame.bmp'
```

This is another hard VM/runtime opcode/source repair gap.

## Decision

Do not resume broad measurement yet.

The next bounded generic repair is:

`runtime_external_artifact_path_and_cleanup_contract`

Repair shape:

- keep this inside the `implementation/tiny` hard-task profile;
- do not add a Terminal-Bench-specific solver;
- when a fresh external verifier expects a runtime artifact path such as
  `/tmp/frame.bmp`, finish evidence must prove that exact path or an explicitly
  equivalent verifier-read path, not only `frames/...` or root copies;
- deferred-verifier cleanup must detect validator output that mentions a
  generated `/tmp/...` artifact, including lines like `BMP ok: ... and
  /tmp/frame.bmp ...`, not only `saved /tmp/...` or `exists size=...`;
- after repair, run a one-trial same-shape speed proof before another
  five-trial proof.

Accept the next repair as directionally improved if the same-shape speed rerun
either passes or no longer fails from a wrong final artifact path / missed
stale `/tmp/frame.bmp` handoff.
