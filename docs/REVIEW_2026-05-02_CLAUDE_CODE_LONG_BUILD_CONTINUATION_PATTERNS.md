# Review 2026-05-02: Claude Code Long-Build Continuation Patterns

## Scope

Reference audited: `references/fresh-cli/claude-code`.

Mew comparison context:
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `docs/REVIEW_2026-05-02_M6_24_COMPILE_COMPCERT_TIMEOUT_CLASSIFICATION_CODEX.md`

Current mew blocker from the dossier and decision ledger: `long-build wall-time/continuation budget`. The latest compile-compcert rerun reached the final compiler build command and then ended in wall timeout with the relevant build still running or killed. That makes the upper-level class generic: preserve state across long build time, keep evidence/proof boundaries clean, and continue from the latest valid build state instead of re-opening stale source/toolchain blockers.

## Executive Finding

Claude Code does not solve long builds by recognizing a particular benchmark or dependency graph. It uses a generic execution substrate:

- command/task identity,
- persisted output references,
- progress streaming and backgrounding,
- explicit permission decisions,
- first-class todo/task state,
- prompt/cache section discipline,
- isolated subagent contexts,
- transcript records for sidechains and content replacement decisions.

The closest mapping for mew M6.24 is not a Terminal-Bench or compile-compcert patch. It is a generic continuation/budget layer over typed command evidence: "this long build reached stage X, command Y has terminal/nonterminal status Z, output is at ref R, proof is still blocked until terminal success, and the next safe action is continue/resume latest build attempt with enough budget."

## 1. Claude Code Mechanisms

### Tool Execution

Relevant Claude Code files and symbols:

- `src/Tool.ts`
  - `Tool`
  - `ToolUseContext`
  - `ToolResult`
  - `ToolPermissionContext`
  - `contentReplacementState`
  - `renderedSystemPrompt`
  - `setInProgressToolUseIDs`
  - `setHasInterruptibleToolInProgress`
  - `setAppStateForTasks`

`ToolUseContext` is the important abstraction. It carries the current abort controller, messages, file-read state, permission context, prompt/cache state, app-state mutation hooks, and task-state mutation hook. The comments on `contentReplacementState` and `renderedSystemPrompt` are especially relevant: content replacement decisions are per conversation thread, and fork subagents reuse the parent's exact rendered system prompt bytes to avoid prompt-cache divergence.

- `src/services/tools/StreamingToolExecutor.ts`
  - `StreamingToolExecutor`
  - `TrackedTool.status`
  - `TrackedTool.pendingProgress`
  - `siblingAbortController`
  - `processQueue()`
  - `executeTool()`
  - `getCompletedResults()`
  - `getRemainingResults()`
  - `getAbortReason()`

This executor lets safe tools run concurrently while preserving result ordering and state updates. It tracks each tool as `queued`, `executing`, `completed`, or `yielded`. Progress is separated from final result messages through `pendingProgress`, so a long-running tool can produce liveness without pretending to be done. Bash errors abort sibling subprocesses through `siblingAbortController` without aborting the parent query.

- `src/services/tools/toolOrchestration.ts`
  - `runTools()`
  - `partitionToolCalls()`
  - `runToolsSerially()`
  - `runToolsConcurrently()`
  - `markToolUseAsComplete()`

Non-concurrent tools run alone. Consecutive concurrency-safe tools are batched and run concurrently, with context modifiers applied after the batch. This is a reusable pattern for mew: separate execution safety from output ordering and from state mutation.

- `src/services/tools/toolExecution.ts`
  - `runToolUse()`
  - `streamedCheckPermissionsAndCallTool()`
  - `checkPermissionsAndCallTool()`
  - `processToolResultBlock()`
  - `processPreMappedToolResultBlock()`

Tool execution validates the model input schema, calls tool-specific `validateInput`, runs pre-tool hooks, checks permissions, runs the tool, then maps results into tool-result blocks. A notable stale-state guard is the shallow `backfillObservableInput` clone: hooks and permission checks can see derived fields without mutating the API-bound input that later becomes part of the transcript and cache prefix.

### Streaming, Long Waits, and Long Commands

Relevant files and symbols:

- `src/tools/BashTool/BashTool.tsx`
  - `inputSchema` fields: `command`, `timeout`, `description`, `run_in_background`, `dangerouslyDisableSandbox`
  - `PROGRESS_THRESHOLD_MS`
  - `ASSISTANT_BLOCKING_BUDGET_MS`
  - `COMMON_BACKGROUND_COMMANDS`
  - `DISALLOWED_AUTO_BACKGROUND_COMMANDS`
  - `detectBlockedSleepPattern()`
  - `validateInput()`
  - `mapToolResultToToolResultBlockParam()`
  - `call()`
  - `runShellCommand()`

Bash has explicit timeout and backgrounding semantics. It blocks long `sleep` patterns when monitor/background support is enabled, because a shell sleep holds the command channel. `runShellCommand()` emits progress events, can background a command explicitly, can background on timeout when allowed, and in assistant mode can auto-background after the assistant blocking budget.

The tool result distinguishes completed output from background state. If a background task exists, the model receives the task id and output path. If output is too large, the result points to persisted output instead of stuffing the full content into context.

- `src/utils/Shell.ts`
  - `DEFAULT_TIMEOUT`
  - `exec()`
  - `TaskOutput`

`exec()` uses `TaskOutput` as the owner of shell output. In file mode, stdout and stderr are written to the same output file descriptor, and the current working directory is updated only for foreground commands that are not backgrounded. This avoids treating a still-running or backgrounded command as if its side effects and cwd are final.

- `src/utils/ShellCommand.ts`
  - `ExecResult`
  - `ShellCommand.status`
  - `ShellCommandImpl.background()`
  - `ShellCommandImpl.kill()`
  - `ShellCommandImpl.#handleExit()`

`ShellCommand` has explicit states: `running`, `backgrounded`, `completed`, `killed`. Timeout either backgrounds or kills, depending on configuration. `#handleExit()` is where terminal status is converted into `ExecResult`, and large output is converted into output-file metadata. This is the strongest direct model for mew's `CommandEvidence`: terminal status and nonterminal continuation state must be distinguishable.

- `src/utils/task/TaskOutput.ts`
  - `TaskOutput`
  - `TaskOutput.startPolling()`
  - `TaskOutput.stopPolling()`
  - `TaskOutput.#tick()`
  - `TaskOutput.getStdout()`
  - `TaskOutput.spillToDisk()`

`TaskOutput` is documented as the single source of truth for shell output. File-mode progress is extracted by polling the tail, and `getStdout()` returns bounded inline output while preserving a full output file reference when needed.

- `src/tasks/LocalShellTask/LocalShellTask.tsx`
  - `spawnShellTask()`
  - `registerForeground()`
  - `backgroundAll()`
  - `backgroundExistingForegroundTask()`
  - `markTaskNotified()`
  - `startStallWatchdog()`
  - `enqueueShellNotification()`

Background shell work is represented as an app task with an id, command, output path, status, and agent id. Completion is reported through a task notification with task id, output file, status, and summary. `startStallWatchdog()` is notable: it stays silent for merely slow commands, including long builds, and only notifies when the output tail looks like an interactive prompt.

- `src/tools/SleepTool/prompt.ts`
  - `SLEEP_TOOL_NAME`
  - `SLEEP_TOOL_PROMPT`
- `src/constants/prompts.ts`
  - `getProactiveSection()`
- `src/query.ts`
  - task-notification attachment drain around queued commands

Sleep is a separate tool for waiting. The prompt tells the model to prefer Sleep over `Bash(sleep ...)`, and the query loop drains task notifications differently when Sleep ran. This cleanly separates "wait/poll" from "run shell command".

### Permission Boundaries

Relevant files and symbols:

- `src/types/permissions.ts`
  - `PermissionMode`
  - `PermissionBehavior`
  - `PermissionRule`
  - `PermissionDecisionReason`
  - `PermissionUpdate`

Claude Code has explicit permission modes: `acceptEdits`, `bypassPermissions`, `default`, `dontAsk`, `plan`, plus internal modes such as `auto` and `bubble`.

- `src/hooks/useCanUseTool.tsx`
  - `useCanUseTool()`
  - `CanUseToolFn`

`useCanUseTool()` routes permission decisions through config, hooks, swarm/coordinator handling, speculative classifier checks, and interactive prompts. It checks abort state before and after async boundaries to avoid stale prompts.

- `src/hooks/toolPermission/PermissionContext.ts`
  - `createPermissionContext()`
  - `createResolveOnce()`
  - `resolveIfAborted()`
  - `persistPermissions()`
  - `cancelAndAbort()`
  - `handleUserAllow()`
  - `handleHookAllow()`

`createResolveOnce()` prevents double resolution in races between hooks, classifier, user prompt, and aborts. `cancelAndAbort()` is explicit about when rejection should abort the turn. This is a boundary discipline mew should mirror at smaller scale: one decision, one reason, no hidden rescue edit.

- `src/utils/permissions/permissions.ts`
  - `hasPermissionsToUseTool()`
  - `hasPermissionsToUseToolInner()`
  - `runPermissionRequestHooksForHeadlessAgent()`
  - `toolAlwaysAllowedRule()`
  - `getDenyRuleForTool()`
  - `getAskRuleForTool()`

The permission path checks deny before allow, converts `ask` to `deny` in `dontAsk`, and for headless/background agents runs hooks before auto-denying. The result carries a decision reason rather than a bare boolean.

- `src/tools/BashTool/bashPermissions.ts`
  - `bashToolHasPermission()`
  - `bashToolCheckExactMatchPermission()`
  - `bashToolCheckPermission()`
  - `matchingRulesForInput()`
  - `checkSandboxAutoAllow()`
  - `awaitClassifierAutoApproval()`

Bash permission handling is deeper than mew needs for M6.24, but the useful pattern is precedence and provenance: exact deny/ask, prefix/wildcard deny, path constraints, sandbox auto-allow, classifier results, and explicit decision reasons.

### Todo and State Continuity

Relevant files and symbols:

- `src/tools/TodoWriteTool/TodoWriteTool.ts`
  - `TodoWriteTool`
  - `oldTodos`
  - `newTodos`
  - `verificationNudgeNeeded`

V1 todos are stored in `AppState.todos` keyed by agent id or session id. Completing all todos clears the list. The tool result reminds the model to continue using the list and, in some builds, nudges for independent verification when a nontrivial list closes.

- `src/tools/TodoWriteTool/prompt.ts`
  - task-state instructions: `pending`, `in_progress`, `completed`

The prompt makes state transitions explicit: one item in progress, complete immediately after finishing, do not mark complete when tests fail or blockers remain.

- `src/tools/TaskCreateTool/TaskCreateTool.ts`
  - `TaskCreateTool`
  - `createTask()`
  - `executeTaskCreatedHooks()`
- `src/tools/TaskUpdateTool/TaskUpdateTool.ts`
  - `TaskUpdateTool`
  - `updateTask()`
  - `blockTask()`
  - `executeTaskCompletedHooks()`
- `src/tools/TaskListTool/TaskListTool.ts`
  - `TaskListTool`
  - `listTasks()`

Task V2 moves todo state into a task-list abstraction with owners, status, blockers, and metadata. `TaskUpdateTool` can merge metadata and create task dependencies, which is directly relevant to long builds: dependency/toolchain state should be task metadata or typed state, not prompt prose.

- `src/hooks/useTaskListWatcher.ts`
  - `useTaskListWatcher()`
  - `findAvailableTask()`
  - `formatTaskAsPrompt()`

The watcher keeps refs for current task and unstable callbacks so it does not re-create watchers per turn. It only claims unowned, unblocked pending tasks. That is a stale-state lesson: watch continuity must be stable across turns, and claims need explicit ownership.

- `src/state/AppStateStore.ts`
  - `todos`
  - `tasks`
  - `notifications`

Claude Code keeps user-visible session state outside the prompt transcript.

### Prompt and Cache Sectioning

Relevant files and symbols:

- `src/constants/prompts.ts`
  - `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`
  - `getSystemPrompt()`
  - `getProactiveSection()`
  - `SUMMARIZE_TOOL_RESULTS_SECTION`

The dynamic boundary separates static globally-cacheable prompt material from user/session-specific dynamic material. `SUMMARIZE_TOOL_RESULTS_SECTION` tells the model that tool results may be cleared and important facts should be written down.

- `src/constants/systemPromptSections.ts`
  - `systemPromptSection()`
  - `DANGEROUS_uncachedSystemPromptSection()`
  - `resolveSystemPromptSections()`
  - `clearSystemPromptSections()`

Most dynamic prompt sections are memoized until `/clear` or `/compact`. Uncached sections require an explicit reason. This is a strong match for mew's `prompt_sections.py` ids/hashes/cache policy.

- `src/utils/api.ts`
  - `splitSysPromptPrefix()`
  - `appendSystemContext()`
- `src/services/api/claude.ts`
  - `buildSystemPromptBlocks()`

Prompt blocks are split into cache scopes, and cache control is attached in a controlled location. The warning in `buildSystemPromptBlocks()` that no more cache blocks should be added is a useful design constraint: cache markers need a narrow owner.

- `src/utils/toolSchemaCache.ts`
  - `getToolSchemaCache()`
  - `clearToolSchemaCache()`

Rendered tool schemas are memoized per session so mid-session feature/gate changes do not churn the tool block and downstream prompt cache.

- `src/utils/toolResultStorage.ts`
  - `persistToolResult()`
  - `buildLargeToolResultMessage()`
  - `processToolResultBlock()`
  - `ContentReplacementState`
  - `cloneContentReplacementState()`
  - `enforceToolResultBudget()`
  - `applyToolResultBudget()`
  - `reconstructContentReplacementState()`
  - `reconstructForSubagentResume()`

Large tool results are persisted to disk with bounded previews. Aggregate tool-result budget decisions are frozen per `tool_use_id`; previously replaced results get byte-identical replacements on later turns, and previously seen unreplaced results are not later replaced. That protects prompt cache and evidence continuity.

- `src/query.ts`
  - `applyToolResultBudget()` call before microcompact
  - `buildPostCompactMessages()` use after compaction
  - queued task-notification attachment drain

Query ordering matters: tool result budgeting runs before microcompact, compaction rewrites the current query's messages to post-compact messages, then attachments/notifications are drained after tool calls so tool results do not interleave with ordinary user messages.

- `src/services/compact/compact.ts`
  - `CompactionResult`
  - `buildPostCompactMessages()`
  - `createPostCompactFileAttachments()`
  - `createAsyncAgentAttachmentsIfNeeded()`
  - `createPlanAttachmentIfNeeded()`
  - `createSkillAttachmentIfNeeded()`

Compaction carries forward a summary, selected attachments, hooks, plan state, recent file state, async agent attachments, and skill attachment state. The pattern is not "trust the summary"; it is "summary plus typed attachments for facts the next turn needs."

- `src/services/compact/postCompactCleanup.ts`
  - `runPostCompactCleanup()`

Cleanup is scoped by query source so subagent compaction does not corrupt main-thread module-level state. This is directly relevant to mew if helper lanes and main lane share process state.

### Subagent and Helper Separation

Relevant files and symbols:

- `src/tools/AgentTool/AgentTool.tsx`
  - `AgentTool`
  - `inputSchema`
  - `outputSchema`
  - `run_in_background`
  - `isolation`
  - `effectiveType`
  - `shouldRunAsync`
  - `workerPermissionContext`
  - `runAgentParams`

AgentTool is a helper boundary. It selects an agent, resolves permissions and tools for that worker, optionally isolates cwd/worktree, can run foreground or background, and returns either a completed result or an async task id/output file. Forked agents inherit exact parent tool definitions and rendered system prompt to preserve prompt cache.

- `src/tools/AgentTool/runAgent.ts`
  - `runAgent()`
  - `filterIncompleteToolCalls()`
  - `recordSidechainTranscript()`
  - `writeAgentMetadata()`
  - `killShellTasksForAgent()`

`runAgent()` creates the worker prompt/context, records the sidechain transcript, writes metadata, yields only recordable messages, and kills agent-scoped background shell tasks on exit. It filters incomplete parent tool calls before context sharing.

- `src/utils/forkedAgent.ts`
  - `createSubagentContext()`
  - `runForkedAgent()`
  - `CacheSafeParams`

`createSubagentContext()` clones mutable state by default, uses a child abort controller unless explicitly shared, makes app-state mutation callbacks no-op for isolated subagents, and separately keeps `setAppStateForTasks` pointed at the root store so task registration and killing still work. It clones content-replacement state by default for cache-sharing forks.

- `src/tasks/LocalAgentTask/LocalAgentTask.tsx`
  - `registerAsyncAgent()`
  - `registerAgentForeground()`
  - `backgroundAgentTask()`
  - `completeAgentTask()`
  - `failAgentTask()`

Background agents are app tasks with their own ids, abort controllers, progress, transcript symlinks, and completion notifications.

- `src/utils/sessionStorage.ts`
  - `recordSidechainTranscript()`
  - `recordContentReplacement()`
  - `getAgentTranscript()`
  - `loadAllSubagentTranscriptsFromDisk()`

Subagent transcripts and content replacement records survive app task eviction. That is the evidence-boundary pattern mew should preserve: helper output is durable but not automatically authoritative.

## 2. How Claude Code Avoids Stale State and Preserves Evidence Boundaries

Claude Code uses several overlapping guards.

First, progress is not proof. `StreamingToolExecutor` emits progress messages separately from final tool results. `BashTool` emits `bash_progress` events with tail output, elapsed time, line counts, bytes, task id, and timeout, but the final `ExecResult` is produced only by `ShellCommandImpl.#handleExit()` or by explicit backgrounding.

Second, terminal and nonterminal command states are represented differently. `ShellCommand.status` can be `running`, `backgrounded`, `completed`, or `killed`. `ExecResult` can carry `backgroundTaskId`, `interrupted`, `outputFilePath`, and exit code. A backgrounded command returns a task id and output path, not a fake success.

Third, output has a durable owner. `TaskOutput` owns stdout/stderr and can persist or spill to disk. `LocalShellTask` completion notifications include task id and output file. Large tool outputs are persisted through `toolResultStorage.ts` and replaced with bounded previews. This prevents both context overload and "I remember the build passed" without a file-backed result.

Fourth, notification consumption is explicit. `LocalShellTask.enqueueShellNotification()` atomically marks tasks as notified before queueing. It aborts prompt speculation because background task state changed and speculation may reference stale output. `query.ts` drains only matching queued notifications and removes only consumed commands.

Fifth, prompt/cache mutation is frozen by id. `ContentReplacementState` tracks seen tool result ids and exact replacement strings. On resume, `reconstructContentReplacementState()` rebuilds the same decisions from transcript records. That prevents a later turn from replacing an old result differently and invalidating the cache or changing the model-visible evidence.

Sixth, compaction is a boundary with typed carry-forward data. `buildPostCompactMessages()` orders boundary marker, summary, kept messages, attachments, and hook results. Post-compact attachments reintroduce recent file state, plan mode, async agents, deferred tools, agent listing deltas, MCP instructions, and invoked skills as needed. `runPostCompactCleanup()` resets caches carefully and scopes main-thread-only resets away from subagent compaction.

Seventh, permission and input state use one-decision semantics. `PermissionContext.createResolveOnce()` and repeated abort checks stop stale dialogs from resolving after a turn has moved on. `toolExecution.ts` uses a cloned observable input for hooks/permissions so derived-path mutations do not silently change the transcript-bound tool call.

Mapping to mew: timed-out or interrupted command evidence must remain nonterminal. It can support continuation and diagnosis, but it cannot satisfy `acceptance_done_gate_decision()` or proof closeout. Mew's proposed `CommandEvidence.start_order`, `finish_order`, `terminal_success`, `status`, `output_ref`, and `BuildAttempt` concepts are consistent with Claude Code's boundaries.

## 3. Prompt Section, Cache, and Agent-Tool Patterns That Map Well to Mew

Patterns that map well:

- Stable prompt sections with explicit cache policy: `systemPromptSection()`, `DANGEROUS_uncachedSystemPromptSection()`, and `SYSTEM_PROMPT_DYNAMIC_BOUNDARY`.
- One owner for cache marker placement: `splitSysPromptPrefix()` plus `buildSystemPromptBlocks()`.
- Session-scoped tool-schema memoization: `toolSchemaCache.ts`.
- Tool result budget with persisted output refs and frozen replacement decisions: `ContentReplacementState`, `applyToolResultBudget()`, and `recordContentReplacement()`.
- Summary plus typed attachments after compaction: `CompactionResult` and `buildPostCompactMessages()`.
- Long-running shell commands as task ids with output files, progress, and completion notifications: `TaskOutput`, `LocalShellTask`, and `BashTool.mapToolResultToToolResultBlockParam()`.
- Explicit sleep/wait primitive instead of shell sleeps: `SleepTool` and `getProactiveSection()`.
- Todo/task state as structured state, not only prompt text: `TodoWriteTool`, `TaskCreateTool`, `TaskUpdateTool`, `TaskListTool`.
- Subagents/helpers as isolated contexts with sidechain transcripts and scoped permissions: `AgentTool`, `runAgent()`, `createSubagentContext()`, `recordSidechainTranscript()`.

For mew's long-build implementation lane, the best mapping is smaller than Claude Code:

- Keep M6.24's `prompt_sections.py` discipline.
- Add generic long-build continuation fields to typed evidence/state.
- Persist bounded output refs.
- Carry continuation decisions across compaction/recovery as structured state.
- Keep helpers advisory unless the existing mew lane explicitly grants authority.

## 4. Adopted, Missing, and Not Yet Worth Copying

### Already Adopted by Mew M6.24

From the M6.24 dossier, decision ledger, gap loop, and design doc, mew has already adopted these Claude-aligned patterns:

- Deterministic acceptance evidence: `acceptance_evidence.py` rejects timed-out, nonterminal, masked, spoofed, or post-mutation evidence.
- Done gate discipline: `acceptance_done_gate_decision()` blocks completion without terminal tool evidence.
- Wall ceilings and recovery reserve: `commands.py` enforces ceilings and reserve.
- Prompt/cache sectioning: `prompt_sections.py` has ids, hashes, stability, and cache policy.
- Structured long-build state: `work_session.py` emits `long_dependency_build_state`.
- Current M6.24 controller docs identify stale-blocker risk and shifted the selected chain to `wall-time/continuation budget`.
- Architecture fit: the gap loop says to keep the existing implementation/tiny lane and not add new authoritative helper lanes.
- Non-goal discipline: the long-build design rejects Terminal-Bench/compile-compcert-specific solvers.

### Missing or Under-Specified in Mew

Mew is still missing the smaller generic equivalents of Claude Code's long-run substrate:

- Persistent command/task identity for long build attempts across recovery turns.
- Native `output_ref` or artifact-backed output storage for long command tail/full logs.
- First-class nonterminal statuses such as `running`, `backgrounded`, `interrupted`, `timed_out`, or `killed` that support continuation but never proof.
- A continuation decision that points at the latest valid build attempt/stage instead of allowing stale source/toolchain blockers to re-enter.
- A wall-time/continuation budget that is separate from the acceptance proof boundary.
- Explicit ordering/freshness fields that say which command result supersedes prior blocker hypotheses.
- A generic "wait/poll/continue" path that does not depend on `sleep` in the shell transcript.
- Integration between todo/state continuity and long-build state, so "in progress" work survives compaction and recovery as typed state rather than prose.

### Should Not Be Copied Yet

Do not copy these Claude Code mechanisms wholesale for M6.24:

- Full Bash permission parser/classifier stack. Mew needs permission provenance and deny-before-allow discipline, not Claude Code's entire classifier and sandbox model.
- Full background task UI and Monitor/Sleep/autonomous daemon loop. Mew should first represent continuation evidence and budget; resident task orchestration can come later if the product needs it.
- Full Agent Teams, swarm, remote agent, worktree, and fork subagent architecture. Mew's current fit gate explicitly avoids new authoritative lanes.
- Exact assistant auto-background threshold such as Claude Code's 15s budget. Mew needs its own budget model tied to work-session wall time and outer harness time.
- Verification-agent nudges as a product gate. Mew already has acceptance evidence and proof gates; adding a Claude-style verifier lane now would blur authority.
- Cache-global boundary machinery at Claude scale. Mew should keep its existing prompt-section hashes and only add the minimum continuation state that needs stable prompt placement.

## 5. Smallest Generic Mew Design Direction for `long-build wall-time/continuation budget`

The smallest generic design direction is:

Add a typed long-build continuation layer over command evidence, not a benchmark-specific retry rule.

Concrete shape:

- Extend or formalize `CommandEvidence` with:
  - `command_id`
  - `attempt_id`
  - `contract_id`
  - `command`
  - `cwd`
  - `status`: `completed`, `failed`, `timed_out`, `killed`, `interrupted`, `running` if supported
  - `exit_code`
  - `timeout_ms` or wall budget consumed
  - `start_order`
  - `finish_order`
  - `terminal_success`
  - `output_ref`
  - bounded `stdout_tail` / `stderr_tail`
  - `continuation_eligible`

- Extend `LongBuildContract` / `BuildAttempt` state with:
  - selected dependency/toolchain strategy satisfied or not,
  - source authority satisfied or not,
  - latest build stage,
  - latest command id,
  - required artifact checks,
  - latest nonterminal reason,
  - retry/continuation count,
  - required additional budget shape.

- Add `RecoveryDecision(kind="continue_long_build")` for the wall-time case:
  - allowed next action: continue/resume the latest idempotent build command or inspect a still-running task output,
  - disallowed next action: reopen stale source-authority or dependency-strategy blockers without newer evidence,
  - proof boundary: nonterminal command evidence remains proof-blocking,
  - output evidence: use `output_ref` and bounded tails, not transcript recall.

- If a process can remain alive across turns, prefer task id plus output ref and later completion notification.
- If the outer harness kills the process, rerun the latest idempotent build target with preserved working directory and typed state.
- Do not mark broad proof or `proof_5` from a timed-out command, even if the output tail looks promising.

This is generic to long source-build/dependency-toolchain work. It does not need to know CompCert, Terminal-Bench, Flocq, MenhirLib, or `ccomp`.

## 6. Recommended Next Action

Next action should be: one timeout-shape diagnostic.

Reason: the current mew docs already narrowed the failure to `long-build wall-time/continuation budget`, but the last run still needs one matched outer/inner timeout diagnostic to distinguish:

- the existing strategy succeeds with enough wall time, versus
- the final build still times out and needs continuation/runtime substrate immediately.

The diagnostic should use matched Harbor agent timeout plus larger `mew --max-wall-seconds`, and it should be documented as a shape diagnostic, not proof closure.

If the diagnostic passes only with extra wall time, do not proceed to `proof_5` as if the product issue is closed. Record that generic continuation/budget support is required before broad proof.

If the diagnostic still times out inside the long build command despite the larger budget, proceed directly to the generic continuation/budget implementation above.

It should not be "reference-backed redesign first" because this review already supplies the relevant reference-backed patterns. It should not be "immediate implementation first" because the current ledger/dossier explicitly selects the one-run timeout-shape diagnostic as the next classifier for the blocker.
