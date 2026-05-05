# Claude Code Frontier Loop Patterns for mew M6.24

Scope: local source inspection only, under `references/fresh-cli/claude-code`. No runtime tracing and no source modifications.

## 1. Summary judgement

Claude Code does not appear to implement an explicit "active compatibility frontier" object. A source search for `frontier` found only unrelated prompt/model wording, notably `src/constants/prompts.ts:117`. The behavior observed on Terminal-Bench `build-cython-ext` is best explained as an emergent product of:

- a turn loop that repeatedly appends assistant tool batches, normalized tool results, reminders, compact summaries, and injected follow-up context;
- prompt policy that favors broad read/search before edits, exact edit anchors, task visibility, and late independent verification;
- tool design that makes read/search tools concurrency-safe, makes edits serial and read-gated, and preserves result shape for later turns;
- Todo/Task state and reminders that keep unfinished work visible even after many turns or compaction;
- specialized read-only Explore and Verification agents that create separation between discovery, implementation, and validation.

Implementation implication for mew: copy the loop properties, not the implicitness. mew should make the active compatibility frontier an explicit internal state object, while using Claude Code's prompt/tool split as the operating discipline around that state.

## 2. Concrete source references

### Agent loop architecture

- `src/query.ts:query()` around `219-238` delegates to `queryLoop` and handles command lifecycle completion.
- `src/query.ts:queryLoop()` around `241-279` initializes mutable loop state, then enters the main `while (true)` loop around `307`.
- `src/query.ts:365-394` prepares `messagesForQuery` from the post-compact boundary and applies tool-result budget trimming.
- `src/query.ts:396-447` applies history snipping, microcompact, and context collapse before model call.
- `src/query.ts:449-535` builds the system prompt and may run autocompaction, then yields compacted messages and continues.
- `src/query.ts:545-558` derives `toolUseBlocks` from assistant messages. The comment states `stop_reason === 'tool_use'` is unreliable; actual tool-use blocks drive continuation.
- `src/query.ts:654-708` streams the model call with messages, system prompt, tools, and token options.
- `src/query.ts:826-861` collects assistant messages and feeds streaming tool-use blocks into `StreamingToolExecutor`.
- `src/query.ts:893-953` handles model fallback cases, including tombstone or missing tool-result recovery.
- `src/query.ts:1062-1183` handles prompt-too-long/media recovery via collapse or reactive compact.
- `src/query.ts:1185-1255` handles max-output recovery by retrying with a larger cap, then injecting a resume instruction if needed.
- `src/query.ts:1267-1306` runs stop hooks and turns blocking hook errors into loop-continuing user messages.
- `src/query.ts:1363-1408` executes tools, yields tool messages, and normalizes results for the next API call.
- `src/query.ts:1484-1520` handles aborts and hook-stopped tool calls.
- `src/query.ts:1535-1628` injects attachments, queued command/task notifications, memory, and skill-prefetch context after tool execution.
- `src/query.ts:1659-1727` refreshes tools, appends assistant plus tool results, and loops until max turns.

### Tool execution and result shape

- `src/services/tools/StreamingToolExecutor.ts:34-39` documents streaming tool execution: concurrency-safe tools can run in parallel, non-concurrent tools run exclusively, results are buffered in output order.
- `src/services/tools/StreamingToolExecutor.ts:76-151` parses tool input, computes concurrency safety, queues tools, and enforces the parallel/serial boundary.
- `src/services/tools/StreamingToolExecutor.ts:347-363` cancels sibling tools only for Bash failures, because Bash commands often have implicit dependency chains; read/search failures do not cancel siblings.
- `src/services/tools/StreamingToolExecutor.ts:412-490` yields completed results in order and waits for remaining tool results.
- `src/services/tools/toolOrchestration.ts:19-82` partitions a model tool batch into concurrency-safe groups and serial tools.
- `src/services/tools/toolOrchestration.ts:86-116` groups consecutive concurrency-safe calls and isolates non-safe calls.
- `src/services/tools/toolOrchestration.ts:152-177` runs safe batches with `getMaxToolUseConcurrency()`, defaulting to 10 unless overridden.
- `src/services/tools/toolExecution.ts:337-490` maps unknown tools, aliases, aborts, and call errors into `tool_result` messages.
- `src/services/tools/toolExecution.ts:599-733` validates zod input and tool-specific input before execution.
- `src/services/tools/toolExecution.ts:800-862` runs `PreToolUse` hooks.
- `src/services/tools/toolExecution.ts:916-1104` resolves permission decisions and returns structured denial results.
- `src/services/tools/toolExecution.ts:1207-1295` calls the tool and maps returned content to API `tool_result` blocks.
- `src/services/tools/toolExecution.ts:1397-1479` builds the user message that carries tool results into the next turn.
- `src/services/tools/toolExecution.ts:1481-1563` runs `PostToolUse` hooks.
- `src/utils/toolResultStorage.ts:1-3`, `137-180`, `189-226`, `272-333`, and `367-388` persist or replace large tool results and maintain replacement state across turns.
- `src/constants/toolLimits.ts:36-49` caps aggregate tool-result content per single user message, which matters for large parallel read/search batches.

### Read/search/edit mechanics

- `src/tools/FileReadTool/FileReadTool.ts:373-378` marks Read as read-only and concurrency-safe.
- `src/tools/FileReadTool/FileReadTool.ts:523-568` deduplicates repeated unchanged reads.
- `src/tools/FileReadTool/FileReadTool.ts:842-847` and `1032-1037` update `readFileState` with content, mtime, offset, and limit.
- `src/tools/GrepTool/GrepTool.ts:183-187` marks Grep as read-only and concurrency-safe.
- `src/tools/GlobTool/GlobTool.ts:76-80` marks Glob as read-only and concurrency-safe.
- `src/tools/BashTool/BashTool.tsx:434-440` marks Bash as concurrency-safe only when the command satisfies read-only constraints.
- `src/tools/Tool.ts:748-760` defaults tools to non-read-only and non-concurrency-safe unless they override this.
- `src/tools/FileEditTool/prompt.ts:4-27` tells the model to Read before Edit, use exact strings, preserve indentation, and include enough context when `old_string` is not unique.
- `src/tools/FileEditTool/FileEditTool.ts:275-287` rejects edits to files that have not been read.
- `src/tools/FileEditTool/FileEditTool.ts:289-310` rejects stale reads when the file changed after being read.
- `src/tools/FileEditTool/FileEditTool.ts:315-343` rejects missing or non-unique `old_string` unless `replace_all` is set.
- `src/tools/FileEditTool/FileEditTool.ts:442-525` rechecks file content atomically, writes the edit, notifies LSP, and refreshes `readFileState`.
- `src/tools/FileEditTool/utils.ts:262-335` applies multi-edit sequences internally with order and overlap checks, but the visible Edit tool input is still singular. Observed "batch edits" are therefore better explained by multiple Edit calls in one assistant turn, executed serially by the orchestration layer.
- `src/tools/FileWriteTool/FileWriteTool.ts:198-218` requires prior read and freshness for overwriting existing files.

### Todo and Task visibility

- `src/tools/TodoWriteTool/TodoWriteTool.ts:65-103` stores V1 todos in app state under `agentId` or session ID and clears only when all are completed.
- `src/tools/TodoWriteTool/TodoWriteTool.ts:72-86` injects a structural verification nudge when the main thread closes 3+ todos without a verification item.
- `src/tools/TodoWriteTool/prompt.ts:3-16` instructs the model to use todos proactively, including immediately capturing new instructions.
- `src/tools/TodoWriteTool/prompt.ts:144-180` defines todo states and warns not to mark work complete if tests fail, implementation is partial, errors remain, or dependencies are missing.
- `src/utils/todo/types.ts:4-18` defines the V1 todo item shape.
- `src/utils/tasks.ts:69-108` defines file-backed Task V2, including task fields and lock options for concurrent agents.
- `src/utils/tasks.ts:133-139` gates Todo V2 by environment or interactive session.
- `src/utils/tasks.ts:190-230` chooses task-list IDs and stores tasks under `$CLAUDE_CONFIG_HOME/tasks/<id>`.
- `src/utils/tasks.ts:279-390` creates and updates tasks under locks.
- `src/tools/TaskCreateTool/TaskCreateTool.ts:80-129` creates V2 tasks and expands the task list in app state.
- `src/tools/TaskCreateTool/prompt.ts:16-55` tells the model to create tasks for complex work, plans, new instructions, and started/completed work.
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts:123-274` updates task fields, status, deletion, and completion hooks.
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts:326-349` adds a verification nudge for closing a 3+ task list without verification.
- `src/tools/TaskListTool/TaskListTool.ts:33-115` exposes a read-only task list view.
- `src/tools/TaskGetTool/TaskGetTool.ts:38-98` exposes read-only task details.
- `src/utils/attachments.ts:3212-3317` injects hidden Todo reminders based on turns since todo activity.
- `src/utils/attachments.ts:3319-3431` injects hidden Task reminders for file-backed tasks.
- `src/utils/messages.ts:3663-3698` renders todo and task reminders as hidden system reminders.
- `src/utils/sessionRestore.ts:72-149` restores V1 TodoWrite state from transcript for SDK and non-interactive sessions.
- `src/components/Spinner.tsx:161-170` and `282-299`, plus `src/components/TaskListV2.tsx:30-150`, make current and next tasks visible in the UI.

### Explore and verification separation

- `src/tools/AgentTool/built-in/exploreAgent.ts:24-56` defines a read-only file-search specialist that is prohibited from file creation, modification, deletion, moves, copies, temp files, redirects, or state changes.
- `src/tools/AgentTool/built-in/exploreAgent.ts:59-83` recommends Explore only for broad searches with at least three independent queries, disallows write/edit/agent/plan tools, uses inherited or Haiku model, and omits CLAUDE.md.
- `src/tools/AgentTool/built-in/verificationAgent.ts:10-22` defines an adversarial verifier and prohibits project modification, with a narrow exception for temp scripts outside the project.
- `src/tools/AgentTool/built-in/verificationAgent.ts:27-72` requires build/test/lint/typecheck or targeted manual verification, and says reading code is not verification.
- `src/tools/AgentTool/built-in/verificationAgent.ts:81-129` requires evidence fields and final `VERDICT: PASS|FAIL|PARTIAL`.
- `src/tools/AgentTool/built-in/verificationAgent.ts:131-151` recommends verifier use for nontrivial tasks and runs it as a background agent with write tools disallowed.
- `src/tools/AgentTool/agentToolUtils.ts:70-224` filters allowed tools for subagents, applying async-agent allowlists and agent-specific disallowed tools.
- `src/constants/tools.ts:36-88` defines all-agent disallowed tools and async-agent allowed tools.
- `src/tools/AgentTool/runAgent.ts:368-410` builds subagent initial messages and omits CLAUDE.md/git status for Explore/Plan-style read-only agents.
- `src/tools/AgentTool/runAgent.ts:500-518` resolves subagent tools and system prompt.
- `src/tools/AgentTool/runAgent.ts:666-806` creates agent-specific tool context and runs nested `query()`.
- `src/tools/AgentTool/AgentTool.tsx:483-637` distinguishes forked agents from normal agents and assembles worker tool pools.
- `src/tools/AgentTool/AgentTool.tsx:686-764` launches async/background agents and returns output-file metadata.
- `src/tools/AgentTool/AgentTool.tsx:1127-1260` finalizes sync agent results, including partial results after errors.
- `src/tools/AgentTool/AgentTool.tsx:1264-1275` reports AgentTool as read-only and concurrency-safe, while delegated permissions are enforced inside the worker context.

### Prompt registry and finish policy

- `src/constants/systemPromptSections.ts:16-25` memoizes static system-prompt sections until `/clear` or `/compact`.
- `src/constants/systemPromptSections.ts:27-38` defines uncached dynamic sections for content that must recompute every turn.
- `src/constants/systemPromptSections.ts:43-68` resolves and clears prompt-section cache.
- `src/constants/prompts.ts:105-115` defines the dynamic boundary: content before it is global-cacheable, dynamic content follows it.
- `src/constants/prompts.ts:199-252` includes coding guidance: read files before changes, diagnose failures before changing strategy, verify before reporting complete, and report outcomes truthfully.
- `src/constants/prompts.ts:269-314` tells the model to use dedicated tools, maintain task state, and make independent tool calls in parallel when possible.
- `src/constants/prompts.ts:343-399` adds dynamic session guidance, including when to use Explore and when to spawn verification. Lines `390-395` state that nontrivial implementation must spawn a verification agent and loop on FAIL.
- `src/constants/prompts.ts:760-790` enhances prompts with environment and subagent details.
- `src/constants/prompts.ts:821-839` warns that function results can be cleared.
- `src/constants/prompts.ts:841` names the summarize-tool-results section, instructing the model to preserve important information because tool results may be cleared.

### Context, compact, and recovery

- `src/query.ts:365-535` combines post-compact messages, context collapse, system-prompt construction, and autocompact.
- `src/query.ts:1062-1183` recovers from prompt-too-long and media-too-long states by context collapse or reactive compaction.
- `src/query.ts:1185-1255` recovers from max output by retrying and then injecting a resume message.
- `src/utils/toolResultStorage.ts` persists large tool outputs and replaces them with previews plus retrieval metadata.
- `src/utils/sessionStorage.ts:2097-2195` performs read-side recovery of sibling assistant blocks and tool results that a single-parent transcript walk would orphan after parallel tool use.
- `src/services/compact/compact.ts:343-365` annotates compact boundaries with preserved-segment metadata so loaders can relink kept messages.

## 3. Mechanisms that matter for mew

- Slower first edit is structural, not just model style. Edit and Write require a prior Read, enforce freshness, and require unique exact anchors. This forces an initial local map of files and surrounding context before the first patch.

- Broad exploration comes from both prompt and tools. Prompt guidance says direct Grep/Glob is right for simple searches, but Explore is intended for broad searches with multiple independent queries. Read, Grep, Glob, and read-only Bash are concurrency-safe, so a single assistant turn can fan out across sibling files.

- Sibling-anchor gathering is an inference. I did not find a source object named "sibling anchor" for implementation planning. The observed pattern follows from exact `old_string` matching, non-unique-match edit failures, prompt guidance to include enough context, and cheap parallel reads/searches. The `sessionStorage` sibling recovery code is about transcript recovery for parallel tool results, not code-repair frontier selection.

- Batch edits are model-turn batches, not free parallel writes. The model can emit multiple Edit calls in one response. The executor batches the turn, but Edit/Write are non-concurrency-safe by default, so edits serialize behind a write barrier. This is the right property for mew: fewer reasoning round trips without concurrent file mutation races.

- Todo/Task state is a visibility layer. V1 todos live in app state and can be restored from transcript. V2 tasks are file-backed and locked. Hidden reminders push open work back into later turns. This is enough to keep "what remains" visible, but it is not a typed compatibility frontier.

- The verifier pass is mostly policy plus a specialized agent. Dynamic prompt instructions and Todo/Task verification nudges push late verification. The verification agent is read-only with a strict evidence/verdict output contract. The main loop itself does not appear to have a hard-coded verifier phase for every task.

- Context compaction is designed to preserve operational continuity. The loop compacts or collapses context on budget pressure, tool outputs can be replaced with previews, and reminders plus summaries are injected so unfinished work can survive result clearing.

- Permissions are part of behavior shaping. Tool calls pass through input validation, pre-hooks, permission resolution, denial result shaping, actual execution, result mapping, and post-hooks. mew should treat permission and result shape as first-class lane mechanics, not UI-only concerns.

## 4. What NOT to copy

- Do not rely only on prompt text plus todos to represent mew's compatibility frontier. Claude Code can get away with emergence; mew M6.24 repair needs inspectable frontier state.

- Do not parallelize writes just because the model emits a batch. Preserve Claude Code's property: read/search fan out, mutations serialize.

- Do not copy the full subagent sidechain and transcript machinery unless mew already needs it. The useful abstraction is read-only exploration and read-only verification, not the complete AgentTool implementation.

- Do not copy feature-flag complexity or ant-specific prompt branches. Several relevant behaviors are gated or product-specific.

- Do not make "large tool result persistence" the primary memory model. It is a budget recovery mechanism. mew's frontier should keep distilled evidence and status explicitly.

- Do not copy `AgentTool.isReadOnly()` at face value unless delegated tool permissions are enforced as carefully as Claude Code's worker context. A meta-tool that can launch write-capable workers is only read-only if the worker tool pool and permission mode make it so.

- Do not omit project instructions from read-only exploration automatically. Claude Code omits CLAUDE.md for Explore/Plan to save tokens. mew may need a compressed convention view when exploration is meant to inform edits.

## 5. Proposed mew adaptation for active compatibility frontier v0

Represent the active compatibility frontier explicitly:

- `FrontierItem`: `id`, `kind` (`failing_test`, `file`, `symbol`, `sibling_anchor`, `dependency`, `verifier_finding`, `todo_projection`), `subject`, `reason`, `source_event`, `status` (`unexplored`, `read`, `anchored`, `edited`, `verified`, `blocked`, `deferred`), `evidence_refs`, `freshness` (`mtime` or read token), `owner`, `last_updated_turn`.
- `FrontierState`: open items, resolved items, blocked items, current edit lane, verification obligations, compact summary, and a monotonic turn counter.

Loop shape for implement-lane repair:

1. Seed frontier from user request, failing tests, build logs, and known task profile.
2. Explore frontier breadth first until each candidate edit lane has file reads plus sibling anchors. Allow parallel read/search only.
3. Select a minimal implementation lane from anchored items and project it into user-visible todos.
4. Apply model-emitted edit batches through a serial write barrier. Require read tokens and reject stale or non-unique anchors.
5. Convert tool failures, stale reads, and non-unique anchors back into frontier items instead of treating them as generic errors.
6. Run targeted tests/build commands. Add failures as frontier items with source command and output reference.
7. For nontrivial edits, launch or simulate an independent verifier pass. A FAIL or PARTIAL verdict reopens frontier items; PASS can close verification obligations.
8. Finish only when open frontier items are resolved, blocked with an explicit reason, or intentionally deferred in the final report.

Prompt and memory policy:

- Static prompt: tool discipline, read-before-edit, serial mutation barrier, verification honesty.
- Dynamic prompt: current frontier summary, active edit lane, unresolved verifier obligations, recent failures, and stale-read warnings.
- Compact summary: preserve frontier items and evidence refs, not raw full outputs.
- Todo/Task projection: expose only the user-facing subset of frontier state. Do not let todo completion be the source of truth for repair completeness.

## 6. Open questions / uncertainty

- Feature gates matter. Verification agent, forked agents, context collapse, and token-budget behavior may not all have been active in the Terminal-Bench run that motivated this review.

- I did not run Claude Code. The mapping from source mechanisms to `build-cython-ext` behavior is source-based inference.

- "Sibling-anchor gathering" is not a named implementation mechanism in the inspected source. I infer it from read-gated exact edits, non-unique edit failures, and parallel search/read behavior.

- The source contains transcript sibling recovery for parallel tool results. That is relevant to context recovery, but it should not be confused with a code-compatibility frontier.

- No explicit frontier object was found. The nearest durable state mechanisms are Todo V1, Task V2, read-file state, tool-result replacement state, transcript recovery, and prompt-reminder injection.
