# M6.24 Model Inference Output Contract

Date: 2026-04-29 JST

## Failure Class

`compact_model_inference_contract_failure`

M6.24 Batch 6 `gpt2-codegolf` measured `0/5` against frozen Codex target `5/5`.
All mew trials created and compiled a small model runner, then finished after
local smoke evidence such as "prints 20 generated tokens." The external
verifier failed the actual model-continuation contract: output either repeated a
degenerate token or timed out while trying to generate the expected continuation.

This is a generic implementation-lane issue, not a Terminal-Bench-specific one:

- the task asked for behavior under a supplied model/checkpoint/tokenizer, not
  merely any syntactically valid output;
- a smoke command that emits the right shape of output is weaker than the
  behavioral contract;
- the failure is the same class as other verifier-contract misses: mew accepted
  existence/shape evidence where the task required semantic equivalence.

## Architecture Fit

Resident Lane Architecture decision:

- authoritative lane: `implementation/tiny`
- architecture decision: `implementation_profile`
- helper lanes: none
- new lane: no

Reasoning: this is still a coding task with one authoritative patch/output.
Adding a new model-inference lane would hide an implementation-lane weakness.
The correct M6.24 repair is a generic finish guard and prompt contract that
forces the implementation lane to preserve the exact model-output semantics.

## Smallest Generic Repair

Add a finish blocker for model/checkpoint/tokenizer inference tasks:

```text
If a task asks for model/checkpoint/tokenizer-based inference, sampling, token
generation, or continuation, then compile success, file size, and "printed N
tokens" smoke output are not enough to finish. Before task_done=true, cite a
completed run_command or run_tests tool whose result proves an oracle-like
output contract: reference implementation comparison, golden/expected
continuation, top-1/argmax token match, logits/token-id match, or another
explicit model-output equivalence check.
```

Likely files:

- `src/mew/acceptance.py`
- `src/mew/work_loop.py`
- `tests/test_acceptance.py`
- `tests/test_work_session.py` only if prompt-surface coverage is needed
- `src/mew/commands.py` for the existing finish-block repair continuation
  allowlist

The repair must not encode GPT-2, Terminal-Bench, the MIT license prompt, or the
expected `WARRANTY...` substring. It should apply to compact model runners,
token generators, checkpoint loaders, and similar arbitrary-workspace tasks.

## Same-Shape Rerun

After implementation, run a one-trial same-shape speed proof for:

```text
gpt2-codegolf after compact model/inference contract repair
```

Escalate to five trials only if the one-trial rerun shows material improvement
or a pass. Do not resume broad measurement first.

## Done When

- focused unit tests prove the blocker rejects smoke-only token output;
- focused unit tests prove the blocker accepts oracle/reference/golden output
  evidence grounded in completed tool output;
- false-positive tests show ordinary non-model token/output tasks are not
  blocked;
- `work_loop` guidance tells the model not to finish on token count alone;
- the new blocker participates in the existing repair-continuation path instead
  of stopping the live loop at the first blocked finish;
- the M6.24 gap ledger records the repair and same-shape rerun condition.
