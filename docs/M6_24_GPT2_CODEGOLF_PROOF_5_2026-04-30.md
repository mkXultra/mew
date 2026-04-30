# M6.24 GPT-2 Codegolf Proof 5

Date: 2026-04-30 JST

## Run

Task: `terminal-bench/gpt2-codegolf`

Job:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-generated-oracle-gpt2-codegolf-5attempts-20260430-0204/result.json
```

Settings:

- `-k 5 -n 5`
- `--agent-timeout-multiplier 2`
- `--max-steps 30`
- `--model gpt-5.5`
- `/Users/mk/.codex/auth.json`

## Result

```text
reward: 5/5
runner exceptions: 0
mean: 1.000
Pass@2: 1.000
Pass@4: 1.000
Pass@5: 1.000
runtime: 30m11s
frozen Codex target: 5/5
```

All five external verifiers passed:

```text
PASSED ../tests/test_outputs.py::test_gpt2_implementation
```

## Behavioral Read

The selected `model_inference_generated_oracle_provenance_guard` repair is
stable enough for this task shape.

What improved:

- the original Batch 6 result was `0/5`;
- the v0.3 rerun still repeated false generated-oracle proof attempts;
- after v0.4, the five-trial proof reached `5/5`, matching the frozen Codex
  target for `gpt2-codegolf`;
- no runner exceptions occurred.

Residual product signal:

- several passing trials ended as `ask_user` or `wall_timeout` rather than a
  clean `task_done=true` finish;
- this is acceptable for the Terminal-Bench score because the external harness
  verified the artifact, but it is still useful future evidence for calibration
  ergonomics and finish/closeout behavior.

## Decision

Close this selected repair for M6.24.

Do not resume broad measurement automatically. Per the M6.24 controller, a
selected same-shape proof closes only that repair. Recheck aggregate/current
gap first. If the aggregate gap remains above `20pp`, stay in improvement phase
and choose the next generic gap class.

