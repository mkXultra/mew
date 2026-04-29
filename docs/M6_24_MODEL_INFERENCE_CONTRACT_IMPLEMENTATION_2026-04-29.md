# M6.24 Model Inference Contract Implementation

Date: 2026-04-29 JST

## Change

Implemented v0 of `compact_model_inference_contract_failure` repair.

Generic behavior:

- model/checkpoint/tokenizer inference tasks are detected by task wording such
  as checkpoint, `.ckpt`, tokenizer, `vocab.bpe`, `model.bin`, weights plus
  model context, and sampling/inference/continuation/next-token output;
- `task_done=true` is blocked when evidence is only compile success, file size,
  CLI shape, source reads, or "printed N tokens";
- completion requires a cited completed `run_command` or `run_tests` result
  whose output proves reference/golden/oracle equivalence, expected
  continuation, argmax/top-1 match, logits match, token-id match, or same-token
  comparison;
- oracle words in command parameters or model-written acceptance text do not
  count unless the completed tool result also contains passing evidence;
- failed evidence such as `false`, `not equal`, `different`, `wrong output`, or
  ratios like `0/20` is rejected;
- the blocker participates in the existing finish-block repair continuation
  path so the live work loop can keep repairing instead of stopping at the first
  blocked finish.

This intentionally does not encode GPT-2, Terminal-Bench, the MIT license prompt,
or any expected hidden verifier substring.

## Files

- `src/mew/acceptance.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `tests/test_acceptance.py`
- `tests/test_work_session.py`

## Validation

```text
uv run pytest tests/test_acceptance.py --no-testmon -q
72 passed

uv run pytest tests/test_work_session.py -k 'finish_blocker_allows_acceptance_repair_continuation or work_finish_blocks or work_think_prompt_guides_independent_reads_to_batch or model_inference' --no-testmon -q
14 passed, 770 deselected

uv run ruff check src/mew/acceptance.py src/mew/work_loop.py src/mew/commands.py tests/test_acceptance.py tests/test_work_session.py
All checks passed

git diff --check
passed
```

## Review

codex-ultra reviewed the first draft and returned `REVISE` for three blockers:

- weak oracle success detection;
- missing repair-continuation allowlist entry;
- classifier false positives/false negatives.

After fixes, the same reviewer session returned `APPROVE`.

Residual risk from review: this is still a heuristic contract guard; differently
worded model-inference tasks may need later marker tuning. The same-shape
`gpt2-codegolf` speed proof is the behavioral confirmation.

## Next

Run one same-shape speed proof:

```text
gpt2-codegolf after compact model/inference contract repair
```

Do not resume broad measurement before recording that rerun.

## v0.1 Handoff Guard

The first speed rerun showed that the v0 guard moved behavior from smoke-only
completion to a real checkpoint/BPE-reading implementation, but the session
still closed with `task_done=false` while stating that exact GPT-2 equivalence
was unverified. In one-shot/external-harness mode, a closed work session is a
handoff even if the task record is not marked done.

Generic repair:

- model/checkpoint/tokenizer inference tasks now apply the model-output
  acceptance gate to `finish` handoffs even when `task_done=false`;
- grounded reference/golden/token equivalence still allows the handoff;
- unverified exact output blocks the finish so the work loop can continue
  repairing instead of returning a successful handoff.

Validation:

```text
uv run pytest tests/test_work_session.py -k 'model_inference_handoff_without_task_done or finish_blocker_allows_acceptance_repair_continuation' --no-testmon -q
3 passed, 783 deselected

uv run pytest tests/test_acceptance.py -k 'model_inference' --no-testmon -q
5 passed, 67 deselected

uv run ruff check src/mew/commands.py tests/test_work_session.py
All checks passed
```

Next proof:

```text
gpt2-codegolf after model_inference_incomplete_handoff_guard v0.1
```

## v0.2 Reasoning Policy

The v0.1 speed rerun blocked the unverified handoff, but every model turn still
used `reasoning_effort=medium` even though the task required compact C
inference over checkpoint weights and a tokenizer. The session spent the full
budget in layout/tokenizer repair and stopped with a model timeout.

Generic repair:

- checkpoint/tokenizer/model-inference implementation terms such as `.ckpt`,
  `.bpe`, `vocab.bpe`, `model weights`, `tokenizer`, `transformer`, and
  `model inference` now classify as `complex_implementation`;
- implementation-capable turns for these tasks use `high` reasoning effort and
  full prompt context;
- read-only exploration behavior is unchanged.

Validation:

```text
uv run pytest tests/test_reasoning_policy.py --no-testmon -q
21 passed

uv run pytest tests/test_work_session.py -k 'model_inference_handoff_without_task_done or finish_blocker_allows_acceptance_repair_continuation' --no-testmon -q
3 passed, 783 deselected

uv run ruff check src/mew/reasoning_policy.py tests/test_reasoning_policy.py src/mew/commands.py tests/test_work_session.py
All checks passed
```

Next proof:

```text
gpt2-codegolf after model_inference_complex_reasoning_policy v0.2
```
