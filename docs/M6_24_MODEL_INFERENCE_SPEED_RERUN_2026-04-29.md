# M6.24 Model Inference Speed Rerun

Date: 2026-04-29

Controller chain:

`M6.24 -> compact_model_inference_contract_failure -> speed_1 gpt2-codegolf`

## Run

Task:

`terminal-bench/gpt2-codegolf`

Job:

`mew-m6-24-model-inference-gpt2-codegolf-1attempt-20260429-2221`

Artifact:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-model-inference-gpt2-codegolf-1attempt-20260429-2221/2026-04-29__22-21-46/result.json`

## Result

- trials: `1`
- runner errors: `0`
- reward: `0.0`
- runtime: `17m 9s`

External verifier:

- `test_gpt2_implementation`: failed
- expected substring: `WARRANTY OF ANY KIND, EXPRESS OR IMPLIED`
- observed substring: `WARRANT8 OF ANY KIND, EXPRESS OR IMPLIED`

## Work Session

Report source:

`proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-model-inference-gpt2-codegolf-1attempt-20260429-2221/2026-04-29__22-21-46/gpt2-codegolf__DqHNvni/agent/terminal-bench-harbor-smoke/unknown-task/command-transcript.json`

Observed:

- `work_exit_code`: `0`
- `stop_reason`: `finish`
- `step_count`: `24`
- generated `/app/gpt2.c`: `3124` bytes
- `gcc -O3 gpt2.c -lm -o /app/a.out`: passed
- advertised runtime shape with `gpt2-124M.ckpt` and `vocab.bpe`: passed

Important behavior:

- The previous compile/size/token-count smoke finish did not recur.
- mew built a real dependency-free C implementation that reads the checkpoint
  and BPE file.
- mew explicitly preserved the remaining gap:
  `No independent golden/reference greedy-token equivalence proof is available locally.`
- The final action still closed the work session with `task_done=false`, so the
  external harness tested a handoff that mew itself had marked as exact-output
  unverified.

## Decision

The v0 guard moved the failure from smoke-only completion to a real
model-inference implementation attempt, but reward stayed `0/1`.

Do not escalate to five trials. The next bounded repair is:

`model_inference_incomplete_handoff_guard`

Scope:

- keep this inside the implementation/tiny lane;
- do not add a GPT-2 or Terminal-Bench-specific solver;
- when a model/checkpoint/tokenizer inference task finishes with
  `task_done=false`, still apply the model-output acceptance gate before
  closing the session and handing artifacts to an external verifier;
- if exact equivalence is unverified, block finish and continue the repair loop
  instead of returning a successful handoff.

After the repair, run another one-trial same-shape speed rerun for
`gpt2-codegolf`.
