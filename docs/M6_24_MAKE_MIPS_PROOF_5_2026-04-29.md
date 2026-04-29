# M6.24 Make MIPS Interpreter Five-Trial Proof

Date: 2026-04-29

Controller chain:

`M6.24 -> hard_task_implementation_strategy_contract_retention -> deferred_verify_runtime_artifact_cleanup_report_fallback_missing -> speed_1 passed -> proof_5 make-mips-interpreter`

## Run

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-report-step-cleanup-make-mips-interpreter-5attempts-20260429-1802/result.json`

Command shape:

- task: `terminal-bench/make-mips-interpreter`
- trials: `-k 5 -n 5`
- model: `gpt-5.5`
- wrapper: `mew_terminal_bench_agent:MewTerminalBenchAgent`
- max steps: 30
- result: `1/5`
- exceptions: 0
- total runtime: 26m 23s

## Result

The proof did not reach the frozen Codex target for this task:

- mew: `1/5`
- Codex target: `3/5`
- gap: `-2/5`

Reward buckets:

- reward `1.0`: `make-mips-interpreter__d7DyzWB`
- reward `0.0`: `make-mips-interpreter__47fW8dm`,
  `make-mips-interpreter__5psqz3h`, `make-mips-interpreter__bTrij8k`,
  `make-mips-interpreter__s5bJ9kY`

The selected stale-runtime artifact handoff repair is real but not sufficient.
One trial passed because `post_run_cleanup` removed stale runtime artifacts
before external verifier handoff. The remaining failures expose the next
generic verifier-alignment gap.

## Failure Classes

### Runtime visual artifact quality

Trials:

- `make-mips-interpreter__47fW8dm`
- `make-mips-interpreter__bTrij8k`

Both trials finished after self-verifying a generated BMP frame, but the frame
was `320x200` while the external verifier expected `640x400`.

Representative verifier failure:

```text
Image sizes do not match: (320, 200) vs (640, 400)
```

Representative internal proof:

```text
artifact validation passed: both outputs were identical 320x200x32 BMPs
```

Diagnosis: mew treated a syntactically valid/non-empty BMP as sufficient visual
artifact proof. For hard runtime/generated-frame tasks, artifact existence,
header validity, nonzero pixels, or internal self-consistency are not enough.
The final evidence must check semantic verifier properties such as expected
dimensions/resolution, reference similarity, and exact stdout markers.

### Exact stdout / fresh verifier timing

Trial:

- `make-mips-interpreter__5psqz3h`

This trial produced a valid 640x400 frame and passed frame existence plus image
similarity, but the external verifier captured stdout before the expected
`I_InitGraphics: DOOM screen size: w x h: 320 x 200` line.

Diagnosis: the stale-runtime cleanup improved handoff, but hard runtime tasks
also need final proof that the fresh verifier-shaped command emits required
stdout before or by the time the generated artifact appears.

### Model JSON parse failure

Trial:

- `make-mips-interpreter__s5bJ9kY`

The work session stopped with:

```text
failed to parse JSON plan: Expecting ',' delimiter
```

Diagnosis: this is a separate model-output robustness gap. It should be kept as
an implementation-lane repair candidate, but it is not the selected next repair
because the repeated proof failures are artifact/verifier-contract quality.

## Decision

Do not resume broad measurement yet.

Select the next bounded generic repair:

`runtime_visual_artifact_quality_contract`

Repair shape:

- keep this inside the implementation/tiny hard-task profile;
- do not add a Terminal-Bench-specific solver;
- strengthen finish gating and THINK guidance so rendered-frame/runtime visual
  artifact tasks require grounded quality evidence, not merely artifact
  existence or valid file format;
- rerun `make-mips-interpreter` with a one-trial speed proof before another
  five-trial proof.

Accept the next repair as directionally improved if a same-shape speed rerun
either passes or no longer finishes with 320x200/format-only frame evidence.
