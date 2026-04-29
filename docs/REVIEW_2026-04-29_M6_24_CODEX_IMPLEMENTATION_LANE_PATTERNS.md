# REVIEW 2026-04-29 - M6.24 Codex Implementation-Lane Patterns

Scope: local-file review only. This note targets the selected M6.24 gap class `hard_task_implementation_strategy_contract_retention`, with emphasis on the smallest Codex-inspired architecture slice that would reduce surrogate/stub strategies, lost task contracts, weak verifier-driven repair, and weak source grounding.

## Recommendation

Do not import a new planner, patch engine, or review subagent yet. Add one small implementation-lane primitive: a durable **hard-task contract capsule** with a pre-finish proof check.

The capsule should be created early for hard implementation tasks, carried through work-session resume/report context, and checked before `task_done=true`. It should record:

- `objective`: compact restatement of the task contract.
- `source_inventory`: required or discovered source paths, commands, artifacts, docs, and expected external behavior.
- `prohibited_surrogates`: task-specific disallowed substitutions inferred from exact tool/source requirements.
- `strategy_steps`: the current implementation route, linked to existing `work_todos`.
- `evidence_refs`: tool-call or observation references proving source reads, edits, exact commands, verifier runs, artifact checks, and remaining failures.
- `open_contract_gaps`: unsatisfied source, verifier, artifact, or behavior requirements.

This is deliberately smaller than Codex's full architecture: mew already has `work_todos`, `active_work_todo`, `verifier_failure_repair_agenda`, `extract_acceptance_constraints()`, and finish blockers. The missing piece is a durable, typed contract/provenance object that makes it hard for the implementation lane to forget what it was supposed to build or to finish from a surrogate path.

## Observed Codex Patterns

1. Persistent objective state
   - `references/fresh-cli/codex/codex-rs/core/src/goals.rs`
   - `references/fresh-cli/codex/codex-rs/tools/src/goal_tool.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/goal.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/session/tests.rs`

   Codex has a structured goal lifecycle: create, read, update, completion state, duplicate-goal rejection, and persisted thread objective state. The useful pattern is not the product concept of "goals"; it is that task intent becomes a first-class object instead of only prompt text.

2. Structured plan state
   - `references/fresh-cli/codex/codex-rs/protocol/src/plan_tool.rs`
   - `references/fresh-cli/codex/codex-rs/tools/src/plan_tool.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/plan.rs`
   - `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs`

   Codex's `update_plan` carries explicit item status and enforces a simple model: pending, in progress, completed, with at most one active item. The mew-compatible import is to link existing work todos to a hard-task contract, not to replace mew's todo machinery.

3. Scoped source/instruction grounding
   - `references/fresh-cli/codex/codex-rs/core/src/agents_md.rs`
   - `references/fresh-cli/codex/codex-rs/core/hierarchical_agents_message.md`
   - `references/fresh-cli/codex/docs/agents_md.md`

   Codex discovers project instructions from root to current directory, preserves scope, and reports instruction sources. The smallest mew equivalent is not `AGENTS.md` compatibility; it is an explicit source inventory and contract-source list for hard tasks.

4. Patch and diff lifecycle
   - `references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/apply_patch.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs`
   - `references/fresh-cli/codex/codex-rs/apply-patch/src/lib.rs`
   - `references/fresh-cli/codex/codex-rs/apply-patch/src/parser.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/turn_diff_tracker.rs`

   Codex treats edits and turn diffs as structured evidence. The smallest useful mew import is not patch grammar; it is finish-time provenance: what source was read, what changed, what command proved it, and what still failed.

5. Review-mode verifier loop
   - `references/fresh-cli/codex/codex-rs/core/src/review_prompts.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/session/review.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/tasks/review.rs`
   - `references/fresh-cli/codex/codex-rs/core/review_prompt.md`

   Codex has a distinct review task shape that prioritizes concrete findings from diffs and configured targets. For mew, the import should be an in-process hard-task pre-finish review against the contract capsule, not another model or subagent.

6. Rollout/context reconstruction
   - `references/fresh-cli/codex/codex-rs/core/src/session/rollout_reconstruction.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/thread_rollout_truncation.rs`
   - `references/fresh-cli/codex/codex-rs/core/src/compact.rs`

   Codex keeps enough structured turn context to rebuild and continue after truncation or compaction. mew's smallest import is to make the hard-task capsule part of resume context and reports so the task contract survives long runs.

## Mapping To M6.24 Gap Evidence

- `make-doom-for-mips`: M6.24 batch 3 shows 0/5 success, with agents running `node vm.js` but generating small MIPS stubs instead of cross-compiling the expected `doomgeneric` path and producing the expected stdout/frame behavior. A contract capsule would require source-path evidence, exact verifier evidence, and a no-stub proof before finish.

- `make-mips-interpreter`: M6.24 batch 4 shows 0/5 success; some runs reached `/tmp/frame.bmp` similarity but missed exact stdout such as `I_InitGraphics: DOOM screen size: w x h: 320 x 200`. This needs behavior-level contract tracking, not artifact-existence-only completion.

- `video-processing`: M6.24 batch 3 shows visible helper/example validation but hidden `test_video.mp4` frame ranges failed. This maps to a contract field for generalization/holdout proof, already hinted by mew's prompts but not yet made durable as evidence.

- `mcmc-sampling-stan`: M6.24 batch 3 shows deterministic fallback or package-availability failures where the task required the Stan/R sampling route. This maps directly to `prohibited_surrogates` and exact-tool evidence.

- `compile-compcert`: M6.24 batch 5 shows `/tmp` scratch permissions were repaired by SR-016, but long-build strategy remains the hard part. This needs plan/progress retention and source-grounded build-route evidence, not another permission gate.

- `crack-7z-hash`, `count-dataset-tokens`, `custom-memory-heap-crash`, `fix-ocaml-gc`, and `git-multibranch`: later batches show residual task-solving failures rather than one missing finish heuristic. They are useful regression shapes, but the first proof should use `make-doom-for-mips` or `make-mips-interpreter` because those most clearly expose surrogate strategy and contract loss.

Relevant mew baseline:

- `src/mew/acceptance.py` already extracts acceptance constraints and blocks several exact-command, external-ground-truth, query-only, numeric, and artifact false finishes.
- `src/mew/work_session.py` already carries `work_todos`, `active_work_todo`, and verifier repair agendas.
- `src/mew/work_loop.py` already prompts for exact external commands, verifier repair, black-box generalization, numeric cross-checks, and no surrogate substitutions.

So the new architecture should make these obligations durable and checkable instead of adding more prompt text.

## Smallest Mew-Compatible Design Slice

1. Add `implementation_contract` to work-session state for hard tasks.
   - Derive from task text, acceptance constraints, exact commands, discovered source paths, and verifier failures.
   - Keep it compact enough for resume context.
   - Update it after source reads, writes, verifier runs, artifact reads, and failures.

2. Link existing `work_todos` to contract obligations.
   - At least one active todo should correspond to the next open contract gap on hard tasks.
   - Verifier failure repair agenda should attach to `open_contract_gaps` rather than living only as prompt text.

3. Add a hard-task pre-finish proof check.
   - Block `task_done=true` when required source paths were not read, exact commands were not run, expected artifacts/behavior are not evidenced, or the implementation route is a known surrogate.
   - Allow failure reports, but require explicit noncompletion language and evidence of the remaining gap.

4. Emit contract/provenance in final reports.
   - Include objective, source paths used, exact verifier commands, artifact checks, unresolved failures, and whether the result is complete or blocked.

This can reuse the existing acceptance/finish-blocker path and work-session serialization. It should not require a new tool surface for the model in the first version.

## Tests And Proof Shape

Unit/regression tests:

- Contract extraction captures objective, exact commands, required artifacts, and prohibited surrogate hints from synthetic hard-task descriptions.
- Resume/report serialization preserves the contract capsule across work-session context rebuilds.
- Finish blocker rejects completion when a hard task lacks required source-read evidence, exact command evidence, verifier evidence, or artifact/behavior evidence.
- Finish blocker rejects obvious surrogate routes, such as dummy `vm.js` output, deterministic replacement for a required sampler, or validation only against visible fixtures.
- Finish blocker permits a noncomplete failure report when it cites exact attempted source, commands, verifier output, and remaining blocker.
- Verifier failure repair agenda updates `open_contract_gaps` and makes the next action target the failing contract item.

End-to-end proof:

- Rerun one same-shape hard task, preferably `make-doom-for-mips` first or `make-mips-interpreter` second.
- Success evidence does not need to be full benchmark success on the first repair. It should show fewer surrogate/stub finishes, stronger source-use evidence, exact verifier stdout/frame evidence, and no false complete state when the verifier still fails.
- Update `proof-artifacts/m6_24_gap_ledger.jsonl` only after the rerun shows the selected gap class is actually narrower.

## What Not To Import Yet

- Full Codex goal management, token accounting, or auto-continuation behavior.
- Full `AGENTS.md` hierarchy and instruction precedence system.
- Codex's `apply_patch` grammar, patch subprocess, or diff streaming events.
- Review subagents or a separate review model.
- Full rollout reconstruction, compaction rewrite, or thread rollback machinery.
- Broad Codex execution infrastructure such as sandbox policy, MCP tool registry, multi-agent delegation, or terminal approval flows.

Those are larger architecture moves. The bounded import for M6.24 is contract retention plus source/proof grounding in the implementation lane.
