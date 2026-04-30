# M6.24 Model Inference Generated-Oracle Rerun

Date: 2026-04-30 JST

## Run

Task: `terminal-bench/gpt2-codegolf`

Job:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-generated-oracle-gpt2-codegolf-1attempt-20260430-0131/result.json
```

Settings:

- `-k 1 -n 1`
- `--agent-timeout-multiplier 2`
- `--max-steps 30`
- `--model gpt-5.5`
- `/Users/mk/.codex/auth.json`

## Result

```text
reward: 0/1
runner exceptions: 0
runtime: 30m02s
work_exit_code: 1
work_report.stop_reason: wall_timeout
work_report.steps: 24
```

External verifier:

```text
expected contains: WARRANTY OF ANY KIND, EXPRESS OR IMPLIED
observed: THIS SOFTWARE IS PROVIDED "AS IS", WITHOUTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANT
```

## Behavioral Read

The v0.4 repair removed the previous failure shape.

What changed:

- no generated `/tmp/oracle_*.c` proof was used as final evidence;
- no repeated blocked finish stutter consumed the final steps;
- mew stayed in real implementation/debugging work and stopped on wall timeout;
- the hidden-verifier output moved from repeated `Damien` tokens to a near
  license-continuation string.

The remaining gap is not oracle provenance. It is a concrete model-inference
implementation gap around exact GPT/BPE continuation behavior. The first hidden
prompt failure is close enough to count as material improvement, but not enough
to close the repair.

## Decision

Escalate to a five-trial same-shape proof for `gpt2-codegolf`.

Rationale:

- the selected generated-oracle repair changed behavior in the intended
  direction;
- the one-trial score stayed `0/1`, but the verifier output is materially
  closer to the expected continuation;
- the M6.24 speed-rerun budget allows `proof_5` after material improvement.

Do not resume broad measurement before the five-trial proof is recorded.

