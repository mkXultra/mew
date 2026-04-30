# M6.24 Model Inference Oracle Provenance Rerun

Date: 2026-04-30 JST

## Run

Task: `terminal-bench/gpt2-codegolf`

Job:

```text
proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-oracle-provenance-gpt2-codegolf-1attempt-20260430-0041/result.json
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
runtime: 29m51s
work_exit_code: 0
work_report.stop_reason: finish
work_report.steps: 30
```

External verifier:

```text
expected contains: WARRANTY OF ANY KIND, EXPRESS OR IMPLIED
observed: THIS SOFTWARE IS PROVIDED "AS IS", WITHOUT Damien ... Damien
```

## Behavioral Read

The v0.3 provenance guard prevented an ungrounded model-inference finish from
being accepted, but reward stayed at `0/1`.

Observed behavior:

- all model turns used high effort;
- mew inspected the checkpoint/BPE layout and wrote a real 3478-byte C
  implementation;
- mew generated `/tmp/oracle_gpt2.c` as a second model implementation and used
  it to claim top-1 token-id equivalence;
- that generated oracle produced the same wrong `Damien` continuation as the
  candidate, while the hidden verifier expected the license-text continuation;
- finish was blocked repeatedly with model-inference evidence ungrounded;
- the session spent the remaining steps retrying finish instead of running a
  new repair/grounding command.

This is a useful failure: the guard stopped the false proof from becoming a
clean completion, but it did not yet give the model a sharp enough repair path.

## Decision

Do not escalate to five trials.

Next bounded repair:

```text
model_inference_generated_oracle_provenance_guard
```

Generic repair target:

- reject model-generated `/tmp/...oracle/reference/golden...` sources as
  independent model-output proof;
- keep task-provided references such as `/tests/reference_model.c` valid;
- keep finish-block continuation active for the new provenance blocker;
- strengthen THINK guidance so a blocked model-inference finish does not repeat
  the same finish/tool-id/oracle source.

