# M6.24 Model Inference Handoff Guard Rerun

Date: 2026-04-29

Controller chain:

`M6.24 -> compact_model_inference_contract_failure -> model_inference_incomplete_handoff_guard -> speed_1 gpt2-codegolf`

## Run

Task:

`terminal-bench/gpt2-codegolf`

Job:

`mew-m6-24-incomplete-handoff-gpt2-codegolf-1attempt-20260429-2250`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-incomplete-handoff-gpt2-codegolf-1attempt-20260429-2250/2026-04-29__22-50-18/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `0.0`
- runtime: `30m 24s`

External verifier:

- `test_gpt2_implementation`: failed
- expected substring: `WARRANTY OF ANY KIND, EXPRESS OR IMPLIED`
- observed continuation:
  `premier bush premierlich backdoor ...`

## Work Session

Report source:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-incomplete-handoff-gpt2-codegolf-1attempt-20260429-2250/2026-04-29__22-50-18/gpt2-codegolf__jggJtWd/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`

Observed:

- `work_exit_code`: `1`
- `stop_reason`: `model_error`
- `step_count`: `30`
- final action: `wait`, reason `request timed out`
- no unverified `finish` handoff occurred
- all 30 model turns used `reasoning_effort=medium`

Important behavior:

- The incomplete-handoff guard worked as a handoff guard: the session no
  longer closed with `task_done=false` and exact equivalence unverified.
- mew kept repairing the implementation until the step/model budget was
  exhausted.
- The remaining failure is no longer "finish bypass"; it is hard compact model
  inference search under medium effort and no independent oracle.

## Decision

Do not escalate to five trials. The next bounded repair is:

`model_inference_complex_reasoning_policy`

Scope:

- keep this inside the implementation/tiny lane;
- do not add a GPT-2 or Terminal-Bench-specific solver;
- classify checkpoint/tokenizer/model-inference implementation tasks as
  `complex_implementation` so they get high reasoning effort and full prompt
  context instead of medium small-implementation handling;
- preserve existing read-only exploration behavior.

After the repair, run another one-trial same-shape speed rerun for
`gpt2-codegolf`.
