# Review: Codex Frontier Loop Patterns

## 1. Summary judgement

Codex does not appear to implement an explicit "frontier", "failure family", or "avoid rebuild until sibling anchors are closed" object in the Rust core. A local search for frontier/failure-family terms in `codex-rs/core/src`, `codex-rs/protocol/src`, and `codex-rs/tools/src` found no matching scheduler or state machine.

The Terminal-Bench-like behavior is best explained as emergent from four concrete mechanisms:

- A transcript-backed sampling loop where every tool output, including failed commands, becomes model-visible input for the next sampling request.
- Tool and patch lifecycles that preserve structured evidence: command begin/end events, stdout/stderr/exit code/status, patch begin/updated/end events, and turn diffs.
- System/model instructions that push the model toward root-cause fixes, `rg`-based repo search, concise plans, and specific-to-broad validation.
- Turn persistence/recovery machinery that keeps context, tool outputs, and compaction/retry behavior coherent across long repair loops.

Inference: Codex avoids repeatedly rebuilding before closing the same failure family mostly because the model sees the prior failed build output, has instructions to fix root causes and start with specific validation, and can keep searching/editing inside the same turn before producing a final answer. The source does not show a hard guard that prevents another rebuild of the same failure signature.

## 2. Concrete source references

### Agent loop architecture

- `codex-rs/core/src/session/turn.rs:118` documents the core loop: model emits either tool calls or an assistant message; tool calls are executed and their outputs are sent back in the next sampling request; assistant-only output ends the turn.
- `codex-rs/core/src/session/turn.rs:375` starts the main turn loop. `run_sampling_request()` is called with cloned history at `turn.rs:445`, and `needs_follow_up` is calculated from model tool needs plus pending input at `turn.rs:458-466`.
- `codex-rs/core/src/session/turn.rs:503` only ends the loop when no follow-up is needed; otherwise it continues sampling with updated history.
- `codex-rs/core/src/session/turn.rs:935` builds the prompt from conversation input, model-visible tool specs, parallel-tool support, base instructions, personality, and output schema.
- `codex-rs/core/src/session/turn.rs:1809` streams a sampling request. It tracks in-flight tool futures, active streamed items, tool argument diff consumers, and whether a follow-up request is needed.
- `codex-rs/core/src/session/turn.rs:1902-1975` handles completed output items. If the item is a tool call, a future is queued and `needs_follow_up` is set.
- `codex-rs/core/src/session/turn.rs:2084-2105` treats Responses API `end_turn=false` as a follow-up trigger.
- `codex-rs/core/src/session/turn.rs:2213-2228` drains in-flight tool outputs and emits a `TurnDiff` if patch tracking produced one.
- `codex-rs/core/src/tasks/regular.rs:71-85` wraps `run_turn()` in a regular task loop and starts another pass if pending input remains.
- `codex-rs/core/src/session/handlers.rs:245-278` creates a new turn context and either steers input into an active turn or spawns a `RegularTask`.

### Tool execution and result representation

- `codex-rs/core/src/stream_events_utils.rs:219-255` converts a model `ResponseItem` into a `ToolCall`, records the tool-call item immediately, queues execution, and marks the sampling request as needing follow-up.
- `codex-rs/core/src/stream_events_utils.rs:317-337` turns non-fatal tool errors into model-visible `FunctionCallOutput` items and continues the loop.
- `codex-rs/core/src/stream_events_utils.rs:468-505` converts tool output input items back into history `ResponseItem`s.
- `codex-rs/core/src/tools/router.rs:175-267` maps model response items (`FunctionCall`, `ToolSearchCall`, `CustomToolCall`, `LocalShellCall`) into internal `ToolCall`s.
- `codex-rs/core/src/tools/parallel.rs:63-80` executes a tool call and wraps non-fatal failures as normal tool-output items. `parallel.rs:82-143` serializes non-parallel tools with a write lock and allows parallel-capable calls with a read lock.
- `codex-rs/core/src/tools/registry.rs:44-91` defines the `ToolHandler` lifecycle: mutation classification, hooks, optional argument-diff consumer, and `handle()`.
- `codex-rs/core/src/tools/registry.rs:357-405` runs pre-tool hooks, waits on the mutation gate for mutating tools, and invokes the handler.
- `codex-rs/core/src/tools/registry.rs:414-482` runs post-tool hooks and can inject additional context or replace the tool response.
- `codex-rs/core/src/tools/orchestrator.rs:1-7` describes the shared runtime sequence: approval, sandbox selection, attempt, retry with escalation on sandbox denial.
- `codex-rs/core/src/tools/orchestrator.rs:105-151` handles approval policy; `orchestrator.rs:196-231` selects the first sandbox attempt; `orchestrator.rs:240-350` retries without sandbox on eligible sandbox-denied failures.
- `codex-rs/core/src/tools/handlers/shell.rs:399-588` parses/normalizes shell invocations, intercepts shell-shaped `apply_patch`, emits command begin/end events, runs through the orchestrator, and returns formatted output to the model.
- `codex-rs/core/src/tools/runtimes/shell.rs:48-63` defines `ShellRequest`; `runtimes/shell.rs:242-288` builds the sandbox command and executes it, returning `ExecToolCallOutput`.
- `codex-rs/core/src/tools/events.rs:64-88` emits `ExecCommandBegin`; `events.rs:401-425` converts runtime output into an exec end result with stdout, stderr, aggregate output, exit code, duration, and status.
- `codex-rs/protocol/src/protocol.rs:3053-3124` defines the public exec status and begin/end event payloads.
- `codex-rs/core/src/tools/context.rs:374-479` defines unified exec model output: chunk id, wall time, exit code or running session id, original token count, and truncated output.
- `codex-rs/protocol/src/models.rs:606-642` defines model input items for tool outputs; `models.rs:688-833` defines model response items including function calls, shell calls, custom tool calls, and tool outputs.

### Patch lifecycle

- `codex-rs/tools/src/apply_patch_tool.rs:12-79` documents the patch language; `apply_patch_tool.rs:87-99` exposes it as a freeform grammar tool.
- `codex-rs/core/src/tools/handlers/apply_patch.rs:65-120` streams model-generated patch deltas into `PatchApplyUpdated` events when the feature is enabled.
- `codex-rs/core/src/tools/handlers/apply_patch.rs:295-315` declares `apply_patch` as a mutating handler and attaches the diff consumer.
- `codex-rs/core/src/tools/handlers/apply_patch.rs:352-389` parses, verifies, and safety-checks the patch before runtime execution.
- `codex-rs/core/src/apply_patch.rs:33-73` maps safety assessment to either rejection or `DelegateToRuntime` with an approval requirement.
- `codex-rs/core/src/tools/handlers/apply_patch.rs:397-438` creates a `ToolEmitter::apply_patch`, emits patch begin, builds `ApplyPatchRequest`, and runs the patch through the orchestrator.
- `codex-rs/core/src/tools/runtimes/apply_patch.rs:43-50` defines `ApplyPatchRequest`; `runtimes/apply_patch.rs:207-250` applies the patch through the selected environment filesystem and returns stdout/stderr/exit code.
- `codex-rs/core/src/tools/events.rs:174-257` emits `PatchApplyBegin` and `PatchApplyEnd`, with status `completed`, `failed`, or `declined`.
- `codex-rs/core/src/turn_diff_tracker.rs:25-54` explains the turn diff tracker: capture baseline files before first patch touch, track renames, and compute one aggregated unified diff.
- `codex-rs/core/src/turn_diff_tracker.rs:57-121` snapshots first-seen file state and tracks moves.
- `codex-rs/protocol/src/protocol.rs:3217-3270` defines patch begin/updated/end events and `TurnDiffEvent`; `protocol.rs:3721-3735` defines structured `FileChange`.

### Todo/task state

- `codex-rs/protocol/src/plan_tool.rs:6-29` defines `StepStatus` and `UpdatePlanArgs`.
- `codex-rs/core/src/tools/handlers/plan.rs:77-93` explicitly says the plan tool is mainly a structured way for clients to render the model's plan; it sends `EventMsg::PlanUpdate`.
- `codex-rs/protocol/src/protocol.rs:1478` includes `PlanUpdate(UpdatePlanArgs)` in the event stream.
- `codex-rs/core/src/state/turn.rs:28-31` tracks active turn metadata and running tasks; `state/turn.rs:110-123` tracks pending approvals, pending input, granted permissions, tool-call count, memory citations, and token usage. This is operational turn state, not repair-frontier state.

### Prompt/system policy

- `codex-rs/protocol/src/prompts/base_instructions/default.md:123-132` tells the agent to keep going until the query is resolved and to use `apply_patch`.
- `default.md:136-141` tells the agent to fix root causes, avoid unrelated fixes, stay consistent with the codebase, and use history search when needed.
- `default.md:149-163` tells the agent to validate work and to start with the most specific tests/builds before broader ones.
- `default.md:260-265` instructs use of `rg`/`rg --files` for search.
- `codex-rs/core/gpt_5_codex_prompt.md:3-11` repeats the `rg` search preference and apply-patch editing preference for GPT-5 Codex.
- `codex-rs/core/gpt_5_1_prompt.md:65-73` and `codex-rs/core/gpt_5_2_prompt.md:38-46` strengthen plan status discipline.
- `gpt_5_1_prompt.md:149-176` and `gpt_5_2_prompt.md:122-150` repeat root-cause and specific-to-broad validation guidance.

### Context and recovery

- `codex-rs/core/src/session/mod.rs:2352-2361` appends response items to conversation history and persists them to rollout storage.
- `session/mod.rs:2734-2777` records context updates and maintains a durable reference context item, injecting full initial context when needed and diffs otherwise.
- `session/mod.rs:1229-1246` reconstructs history from rollout on resume/fork.
- `codex-rs/core/src/session/rollout_reconstruction.rs:4-11` defines reconstructed history plus resume metadata; `rollout_reconstruction.rs:240-275` replays response items, compactions, and rollbacks.
- `codex-rs/core/src/session/turn.rs:484-500` auto-compacts mid-turn when token limits are hit and a follow-up is still needed.
- `codex-rs/core/src/session/turn.rs:1018-1101` retries retryable stream errors, falls back from WebSocket to HTTPS transport when configured, and reports reconnect events.
- `codex-rs/core/src/session/mod.rs:2943-3005` steers new user input into the active regular turn as pending input.
- `codex-rs/protocol/src/protocol.rs:1-4` documents the submission queue/event queue pattern.

## 3. Mechanisms that matter for mew

- Keep failure evidence model-visible and structured. Codex's most important property is not a hidden frontier object; it is that command outputs become transcript state with exit code, duration, and truncated stdout/stderr, then the next sampling request sees them.
- Treat tool outputs as turn continuations. In Codex, a failing shell command is usually not terminal; it becomes a `FunctionCallOutput`, sets `needs_follow_up`, and drives the next model action.
- Preserve a patch lifecycle separate from command lifecycle. Patch begin/update/end and turn diff events make edits observable and reviewable without depending only on final file state.
- Gate expensive verification by explicit mew state, not prompt hope. Codex's specific-to-broad verifier pattern comes from instructions and model behavior. For mew M6.24, repeated rebuild avoidance should be encoded as state: same signature, open sibling anchors, attempted hypotheses, and cheapest remaining verifier.
- Separate UI plan state from algorithmic repair state. Codex's `update_plan` is useful for user-visible checklist progress, but the handler itself says its value is the client-rendered input, not an internal scheduler.
- Retain enough context after compaction/recovery to avoid losing failure evidence. Codex persists response items and context baselines; mew should persist normalized failure signatures and anchor decisions, not just raw transcript text.

## 4. What NOT to copy

- Do not rely only on LLM prompt discipline to avoid repeated rebuilds. Codex has no visible hard guard for "same failure family already seen, close sibling anchors first".
- Do not treat `update_plan` as durable repair state. It is a presentation/checklist channel, not a planner data structure.
- Do not copy Codex's full session/rollout/UI event complexity if mew only needs implement-lane repair. Copy the smaller invariant: every failure, patch, and verifier result must have a durable, structured record.
- Do not make the verifier loop depend on final assistant-message stopping semantics. In Codex, turn completion is a conversation-loop condition; mew's repair lane should have explicit verifier gates.
- Do not store only raw build logs. Codex truncates for model visibility; mew should preserve raw artifacts where practical, but drive decisions from normalized signatures and extracted anchors.

## 5. Proposed mew adaptation for active compatibility frontier v0

Introduce an explicit `ActiveCompatibilityFrontier` for implement-lane repair:

- `failure_family_id`: stable hash from normalized failing command, exit class, top error lines, missing symbol/import/module/path, and relevant platform/runtime facts.
- `evidence`: raw command id, exit code, selected stdout/stderr slices, parsed error spans, and artifact paths.
- `anchors`: source files, symbols, setup/build config files, Cython extension declarations, generated/native boundaries, and test names implicated by evidence.
- `sibling_candidates`: nearby modules/files/config declarations discovered by `rg`, directory sibling scans, and build metadata inspection.
- `hypotheses`: candidate causes with status `open`, `patched`, `rejected`, or `verified`.
- `patch_batch`: applied edits tied to anchors/hypotheses and resulting diffs.
- `verifier_history`: cheap/static checks, targeted tests, build commands, signatures observed, and whether each verifier changed the failure family.
- `closure_state`: why the family is ready for a rebuild or final broader verifier.

Suggested v0 loop:

1. On verifier failure, normalize the failure signature and either create or reopen the active frontier.
2. Run broad-enough search before another full build: direct error text, implicated symbols, package/build declarations, sibling extension/module files, and adjacent tests.
3. Require a "same-family rebuild gate": if the last full verifier returned the same family and open sibling candidates remain, choose search/patch/cheap verifier instead of rerunning the full build.
4. Apply a batch patch that closes one or more related anchors, then record the diff and touched frontier anchors.
5. Run the cheapest verifier that can falsify the current hypothesis. Escalate to full rebuild only when the same-family anchor set is closed or a cheap verifier shows the failure family changed.
6. If the same signature remains after rebuild, mark the hypothesis failed, keep the family open, and force new evidence/search before another rebuild.

This preserves the useful Codex shape: failure evidence feeds repair, search precedes edits, edits are explicit, and verification proceeds specific-to-broad. The difference is that mew should make the frontier and rebuild gate deterministic.

## 6. Open questions / uncertainty

- The observed Terminal-Bench behavior may partly live in model policy/weights rather than repository code. The Rust source shows the loop and prompt surface, but not a benchmark-specific frontier algorithm.
- Active prompt composition varies by model and configuration. I inspected the default base instructions and GPT-5/GPT-5.1/GPT-5.2 prompt files, but an actual run may include additional AGENTS.md, developer, harness, or skill instructions.
- I did not find a Codex source-level rule that names "sibling anchors" or "batch repair". That behavior is an inference from root-cause/search/validation prompts plus transcript continuity.
- Tool availability can vary by configuration (`shell`, `exec_command`, `apply_patch`, code-mode tools, MCP tools). The architectural pattern is stable, but exact tool names in a run are config-dependent.
