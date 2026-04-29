# M6.24 Compact Model Contract From References

Date: 2026-04-29 JST

Scope: review the `gpt2-codegolf` M6.24 gap evidence, Codex/Claude Code reference
patterns, and the smallest generic mew substrate repair. This is not an
implementation note for a Terminal-Bench-specific solver.

## 1. Failure Class And Genericity

Failure class: `compact_model_inference_contract_failure`, more generally a
semantic model-output contract finish gap.

Selected evidence:

- `docs/M6_24_BATCH_6_RUNS_2026-04-29.md` records `gpt2-codegolf` at `0/5`
  against Codex target `5/5`.
- `proof-artifacts/terminal-bench/harbor-smoke/mew-m6-24-batch6-gpt2-codegolf-5attempts-20260429-2103/result.json`
  records five trials, zero runner errors, and reward `0.0` for every trial.
- The trial reports show mew accepted compile/size/run smoke evidence, for
  example `.../gpt2-codegolf__JjZhuz3/.../mew-report.json:82` and `:438`,
  where the accepted proof was effectively "compiled and printed 20 Damien
  tokens."
- External verifier output shows the semantic contract failed, for example
  `.../gpt2-codegolf__Po5A8mh/verifier/test-stdout.txt:90-97` and
  `.../gpt2-codegolf__3npxH3b/verifier/test-stdout.txt:103-104`.

Why this is generic:

- The task required behavior under a supplied model/checkpoint/tokenizer, not
  merely a syntactically valid CLI or non-empty token stream.
- Mew collapsed "continue under what the model would print" into "program
  compiles and emits 20 tokens."
- The same class applies to compact inference runners, checkpoint/tokenizer
  loaders, decoders/codecs, interpreters/emulators, protocol implementations,
  and numerical solvers whenever a hidden or external verifier checks semantic
  output rather than shape.

Keep the repair boundary narrower than "all stdout tasks." Ordinary tasks that
only ask for a fixed count or format of output must not be blocked by a model
oracle requirement.

## 2. Reference Patterns

| Reference | Local path | Pattern to adopt |
| --- | --- | --- |
| Codex plan state | `references/fresh-cli/codex/codex-rs/core/gpt-5.2-codex_prompt.md:21-27` | Explicitly maintain task state and update it after completing a subtask. Mew analog: keep `working_memory.implementation_contract` and acceptance checks current. |
| Codex review posture | `references/fresh-cli/codex/codex-rs/core/gpt-5.2-codex_prompt.md:31` | Reviews prioritize bugs, risks, regressions, and missing tests. Mew analog: classify this as a false-completion risk, not a task-specific miss. |
| Codex strict final schema | `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:935-951`, `references/fresh-cli/codex/codex-rs/core/src/client_common.rs:44-48` | Model-visible output schema and strict validation keep completion surfaces mechanical. Mew analog: finish blockers should enforce evidence shape before `task_done=true`. |
| Codex project instructions | `references/fresh-cli/codex/codex-rs/core/src/agents_md.rs:1-16` | Keep scoped project/task instructions in prompt context. Mew analog: durable contract memory should preserve the exact behavior contract across turns. |
| Codex explorer/awaiter roles | `references/fresh-cli/codex/codex-rs/core/src/agent/role.rs:368-376`, `references/fresh-cli/codex/codex-rs/core/src/agent/builtins/awaiter.toml:8-22` | Helpers can answer scoped questions or await terminal state, but must not hallucinate completion. Mew analog: helper evidence is useful, but finish authority remains in the work lane gate. |
| Claude verify before complete | `references/fresh-cli/claude-code/src/constants/prompts.ts:211`, `:233`, `:240` | Verify before reporting done, diagnose failures before switching tactics, and report outcomes faithfully. |
| Claude todo completion rules | `references/fresh-cli/claude-code/src/tools/TodoWriteTool/prompt.ts:144-171` | A task is not complete with failing tests, partial implementation, or unresolved errors. Mew analog: smoke-only model output leaves an unresolved semantic contract. |
| Claude verification nudge | `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:72-107` | Mechanical loop-exit nudges catch missing verification exactly when agents tend to close out. Mew analog: finish blocker should fire at `task_done=true`. |
| Claude verification agent | `references/fresh-cli/claude-code/src/constants/prompts.ts:390-394`, `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:27-40`, `:51-62`, `:71-83`, `:117-129` | Verification requires direct execution, expected-output checks, command output, and a parsed verdict. Mew should adopt the invariant, not necessarily the whole helper-agent architecture. |
| Claude stop hooks | `references/fresh-cli/claude-code/src/query/stopHooks.ts:268-331` | Lifecycle hooks can block continuation/completion mechanically. Mew analog: `acceptance_finish_blocker` is the right substrate surface. |

Synthesis: both references separate "task looks runnable" from "contract is
verified." The reusable pattern is a model-visible contract plus a mechanical
completion gate that demands verifier-shaped semantic evidence.

## 3. Architecture Fit

Decision: `implementation_profile` in the existing authoritative
implementation/tiny lane.

Architecture fit:

- `docs/DESIGN_2026-04-26_RESIDENT_LANE_ARCHITECTURE.md:146-158` says one
  authoritative lane owns final output, helper lanes are non-authoritative, and
  the implementation lane must become reliable before broad deliberation or
  meta-loop expansion.
- The failure is not lane selection. The implementation lane produced code and
  then over-accepted weak proof.
- The repair belongs in the existing policy/finish gate plus THINK guidance, not
  in a new `model` lane, verifier lane with final authority, or Terminal-Bench
  adapter.

Helper verification can remain future evidence/advice. It must not silently
replace the authoritative lane's output or become required for this M6.24 slice.

## 4. Recommended Smallest Generic Repair In Mew

Smallest repair: add or keep a generic model/checkpoint/tokenizer inference
output finish guard.

Current checkout already appears to contain this repair shape. If these edits are
the active draft, do not widen them before proof; validate and land the narrow
slice instead.

Likely files and functions:

- `src/mew/acceptance.py`
  - `is_model_inference_output_task`
  - `_model_inference_output_quality_blocker`
  - `_has_model_inference_output_quality_evidence`
  - `acceptance_finish_blocker`
- `src/mew/work_loop.py`
  - `build_work_think_prompt`
  - `_work_action_schema_text`
- `src/mew/work_session.py`
  - `_implementation_contract_from_task` only if rerun evidence shows the
    semantic contract is not retained across turns.
- `src/mew/commands.py:3606-3628`
  - use the existing finish-blocker aggregation; no new command path is needed.

Recommended contract:

- Detect tasks that combine model/checkpoint/tokenizer source markers
  (`checkpoint`, `.ckpt`, `weights`, `tokenizer`, `vocab.bpe`) with inference or
  generation actions (`inference`, `sample`, `sampling`, `argmax`, `arg-max`,
  `continuation`, `next tokens`) and an output obligation.
- Reject `task_done=true` when evidence is only compile success, file size, CLI
  shape, file-read proof, non-empty output, or "printed N tokens."
- Accept evidence only when a completed `run_command` or `run_tests` result
  itself proves reference/golden/oracle equivalence, expected continuation,
  argmax/top-1 match, logits/token-id match, or same-token comparison.
- Do not accept oracle words that appear only in command parameters or in the
  model's assertion text; the completed tool result must contain the proof.
- If no oracle-like verifier can be built, keep
  `working_memory.implementation_contract.open_contract_gaps` focused on the
  semantic output gap instead of claiming completion.

This follows `docs/ISSUE_REPAIR_POLICY.md`: the repair is a reusable contract,
not a trigger on `gpt2-codegolf`, `gpt2.c`, `/app/a.out`, or a hidden verifier
substring.

## 5. Tests And Proof Needed

Focused unit tests:

- Classifier covers the GPT-2-like checkpoint/tokenizer prompt and a generic
  checkpoint-inference prompt.
- Classifier does not escalate ordinary non-model token/count/output tasks.
- Finish blocker rejects compile/size/read/CLI-shape plus "printed 20 tokens"
  evidence.
- Finish blocker accepts grounded reference/golden/top-1/token-id evidence from
  a completed `run_command` or `run_tests` result.
- Finish blocker rejects oracle markers present only in the command string or
  model-written acceptance text.
- Work-loop prompt includes the model-output contract warning.
- Finish control path keeps the session/task open when the new blocker fires.

Suggested focused validation:

```sh
uv run pytest tests/test_acceptance.py -k 'model_inference_output or plain_token_output' -q
uv run pytest tests/test_work_session.py -k 'finish_blocker or model_inference or work_prompt' -q
uv run ruff check src/mew tests
git diff --check
```

Proof after implementation:

- Run one same-shape speed proof for `gpt2-codegolf`; do not run a long five-run
  proof or resume broad measurement first.
- Minimum substrate proof: mew must not finish `task_done=true` after only a
  `Hello`/token-count smoke run. If it cannot build semantic model-output proof,
  it should preserve an open semantic contract gap or continue repair instead of
  claiming completion.
- Strong proof: one-trial reward improves or passes. Escalate to five trials
  only after material one-trial evidence.

While preparing this review, only a short unit sanity check was run:

```sh
uv run pytest tests/test_acceptance.py::test_model_inference_output_task_classifier_covers_checkpoint_sampling -q
```

It passed. No benchmark rerun was performed.

## 6. Explicit Non-goals

- No Terminal-Bench-specific GPT-2 solver.
- No hard-coded `gpt2-codegolf`, `gpt2.c`, `/app/a.out`, `gpt2-124M.ckpt`,
  `vocab.bpe`, `Damien`, `WARRANTY`, MIT-license prompt, or verifier substring.
- No task-specific hidden-test probing.
- No new authoritative lane, verifier lane, or broad deliberation route for this
  repair.
- No requirement that mew prove a hidden oracle when unavailable; the generic
  behavior is to block/record the unresolved semantic contract gap.
- No broad M6.24 measurement resume before the controller records same-shape
  proof and threshold status.
- No cloning Codex or Claude Code subsystems. Adopt the invariant: contract
  retention plus command-grounded semantic verification before completion.
