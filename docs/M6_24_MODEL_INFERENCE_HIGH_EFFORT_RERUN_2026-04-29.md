# M6.24 Model Inference High-Effort Rerun

Date: 2026-04-29 JST

## Shape

- Task: `terminal-bench/gpt2-codegolf`
- Repair under test: `model_inference_complex_reasoning_policy v0.2`
- Job: `mew-m6-24-high-effort-gpt2-codegolf-1attempt-20260429-2335`
- Rerun tier: `speed_1`
- Model: `gpt-5.5`

## Result

- Score: `0/1`
- Runner errors: `0`
- Runtime: `31m14s`
- Trial: `gpt2-codegolf__H5HygbY`
- Work exit: `1`
- Stop reason: `wall_timeout`
- Work steps: `22`
- Reasoning effort: `high` on all 22 model turns

Artifacts:

- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-high-effort-gpt2-codegolf-1attempt-20260429-2335/2026-04-29__23-35-53/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-high-effort-gpt2-codegolf-1attempt-20260429-2335/2026-04-29__23-35-53/gpt2-codegolf__H5HygbY/result.json`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-high-effort-gpt2-codegolf-1attempt-20260429-2335/2026-04-29__23-35-53/gpt2-codegolf__H5HygbY/verifier/test-stdout.txt`
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-high-effort-gpt2-codegolf-1attempt-20260429-2335/2026-04-29__23-35-53/gpt2-codegolf__H5HygbY/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`

## Observed Delta

The v0.2 policy worked mechanically: every model turn selected
`complex_implementation` with `reasoning_effort=high`, and the task used full
prompt context.

The failure moved, but reward did not improve:

- mew produced and compiled a `4118` byte C implementation;
- mew avoided the earlier unverified `task_done=false` handoff;
- finish attempts were blocked four times by the model-inference quality gate;
- the claimed verifier compared the candidate against a temporary reference
  derived from the current `gpt2.c` source, not an independent oracle;
- after repeated blocked finishes, the session hit `wall_timeout`;
- the external verifier failed exact continuation:
  expected `WARRANTY OF ANY KIND, EXPRESS OR IMPLIED`, observed repeated
  `Damien` tokens.

## Decision

Do not escalate to five trials.

High effort alone is not the selected repair. The next generic gap is:

`model_inference_oracle_provenance_guard`

The implementation lane must distinguish independent model-output evidence
from self-derived references. A reference/oracle built by copying, slicing, or
lightly modifying the candidate implementation is not an independent GPT/model
oracle, even if candidate/reference outputs match.

## Next Same-Shape Condition

After the provenance guard, run another one-trial same-shape speed proof for:

`gpt2-codegolf after model_inference_oracle_provenance_guard v0.3`

Do not resume broad measurement first.
