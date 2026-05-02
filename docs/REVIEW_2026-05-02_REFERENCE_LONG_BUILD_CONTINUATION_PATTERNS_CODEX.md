# Review 2026-05-02: Reference Long-Build Continuation Patterns

Reviewer: Codex

Scope: reference patterns in `references/fresh-cli/codex` and
`references/fresh-cli/claude-code` for the M6.24 upper-level failure class:
long source-build and dependency-toolchain tasks must preserve state, manage
long wall time, resume intelligently, maintain terminal-proof boundaries, and
avoid stale blockers or task-specific hacks.

## Verdict

Both references solve long-running terminal work by separating progress from
proof:

- Codex CLI keeps a live process in a process manager, returns a stable
  `session_id` while the process is still running, lets the model poll or send
  input, and only gives terminal exit evidence when the process exits.
- Claude Code promotes long foreground shell commands to background tasks with
  durable output files, status notifications, and a separate task-output read
  path. Progress is visible, but completion status and exit code remain the
  proof boundary.

Mew M6.24 has already adopted much of the typed evidence/state/recovery shape.
The missing piece for the current blocker is not another compile-compcert rule;
it is a generic continuation/budget layer for long commands that may outlive one
foreground tool call or one work-session wall envelope.

The next action should remain one timeout-shape diagnostic, not immediate
implementation. It distinguishes "same strategy succeeds with a matched larger
wall envelope" from "mew needs a managed continuation primitive now."

## 1. Codex CLI Patterns

### Long-running terminal commands

Codex has a first-class unified terminal runtime rather than only a
fire-and-forget shell call.

- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:45-80`
  defines `exec_command` with `yield_time_ms`, `max_output_tokens`, sandbox
  controls, optional TTY, and `write_stdin` with `session_id`. The model can
  start a command, receive bounded output, then poll or continue it.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs:59-70`
  sets global bounds: minimum yield, maximum yield, default background
  terminal timeout, output byte cap, and process-count caps.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:231-319`
  opens the session and starts output streaming. A key safety comment at
  `:271-290` stores the live process before the initial yield so interruption
  cannot drop the last handle and kill the process accidentally.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:346-405`
  returns a response after the bounded yield. If the process is still alive, the
  response includes the process id instead of pretending the command finished.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:408-524`
  implements `write_stdin` and empty polling. Non-empty writes require a TTY;
  empty polls are bounded by minimum/background limits; the result still reports
  either an exit code or the live process id.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:527-550`
  refreshes stored process state and removes exited processes from the live
  table.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:984-1029`
  prunes old process handles when the manager exceeds capacity, preferring
  exited/LRU processes while protecting recent entries.

Concept to copy: a live long command has a stable handle and an explicit poll
operation. Running output is progress, not success.

### Command output and evidence preservation

Codex preserves bounded but stable terminal evidence while keeping output size
under control.

- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs:4-31`
  defines a capped head/tail transcript buffer. The beginning and end are kept;
  the middle is dropped under pressure.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs:60-130`
  appends output, splits head/tail, snapshots, and drains bounded transcript
  data.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:37-40`
  starts a background reader that appends process output and emits deltas.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:104-135`
  waits for process exit and output drain before finalizing.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:190-214`
  emits the terminal `ExecCommandEnd` event with aggregated transcript and
  timeout status.
- `references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:375-386`
  defines the model-facing exec output shape.
- `references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:453-479`
  formats tool output with a chunk id, wall time, exit code if present, live
  process id if still running, original token count, and output.

Concept to copy: preserve a bounded head/tail plus a durable reference or
stable id. Do not require full output in context for proof; require a terminal
event or output reference that can be inspected.

### Timeout and continuation

Codex distinguishes the old shell timeout path from the unified continuation
path.

- `references/fresh-cli/codex/codex-rs/core/src/exec.rs:51` keeps the classic
  shell default timeout at 10 seconds.
- `references/fresh-cli/codex/codex-rs/core/src/exec.rs:151-210` models command
  expiration and shell capture policy.
- `references/fresh-cli/codex/codex-rs/core/src/exec.rs:1267-1284` kills the
  child or process group when the classic shell call expires.
- `references/fresh-cli/codex/codex-rs/core/src/exec.rs:647-690` maps timeout to
  a synthetic timeout error and conventional exit code `124`; timed-out output
  is preserved but is not success evidence.
- In contrast, unified exec can yield before completion and return a live
  `session_id`; `write_stdin`/poll later obtains more output or the final exit.

Concept to copy: a wall-time yield is not the same as command timeout. A
long-build controller needs a "still running; poll/continue" state before it
falls back to kill/rerun.

### Patch/application lifecycle

Codex gives patching a separate verified path instead of treating it as arbitrary
shell text.

- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:307-330`
  intercepts `apply_patch` before normal process execution.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/invocation.rs:134-223`
  parses and verifies apply-patch invocations, resolves effective cwd, and
  derives exact file changes.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/invocation.rs:225-245`
  only permits strict heredoc forms such as `apply_patch <<EOF` and
  `cd <path> && apply_patch <<EOF`; extra shell composition is rejected.
- `references/fresh-cli/codex/codex-rs/core/src/turn_diff_tracker.rs:25-31`
  snapshots first-seen file baselines with stable ids.
- `references/fresh-cli/codex/codex-rs/core/src/turn_diff_tracker.rs:50-54`
  front-runs apply-patch tracking.
- `references/fresh-cli/codex/codex-rs/core/src/turn_diff_tracker.rs:222-242`
  recomputes the aggregate diff from baseline to disk.

Concept to copy later, if needed: source/build continuation should have the same
separation between typed lifecycle events and arbitrary shell prose. For M6.24,
the needed lifecycle is command/process lifecycle, not patch lifecycle.

### Avoiding stale state after tool calls

Codex invalidates incremental context when the baseline may no longer be valid.

- `references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs:32-50`
  stores history version and optional reference context baseline.
- `references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs:221-237`
  clears reference context when dropping turns could make diffing stale.
- `references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs:357-370`
  normalizes history by preserving valid tool call/output pairs and removing
  unsupported orphan outputs.
- `references/fresh-cli/codex/codex-rs/core/src/context_manager/history.rs:407-438`
  clears reference context when trimmed initial context could invalidate a
  cached diff baseline, forcing full reinjection instead of stale incremental
  state.

Concept to copy: if a continuation handle, output reference, or baseline is
trimmed/invalidated, force a full state refresh before deciding recovery or
success.

## 2. Claude Code Patterns

### Tool execution and orchestration

Claude Code has a strong tool contract and keeps execution, permission, progress,
and result boundaries separate.

- `references/fresh-cli/claude-code/src/Tool.ts:362-475` defines the `Tool`
  interface, including concurrency safety, read-only/destructive flags,
  interrupt behavior, user-interaction requirements, permissions, and result
  size limits.
- `references/fresh-cli/claude-code/src/Tool.ts:743-769` builds tools with
  fail-closed defaults: not concurrency-safe, not read-only, and permission
  checks delegated unless explicitly provided.
- `references/fresh-cli/claude-code/src/Tool.ts:284-299` gives tool calls a
  context with content replacement state and the parent rendered system prompt
  frozen at turn start, preventing prompt-cache divergence across subagents.
- `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:19-82`
  executes batches while preserving ordering and serializing unsafe/non-read-only
  work.
- `references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:86-116`
  partitions consecutive concurrency-safe calls while treating parse failure as
  unsafe.
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:34-40`
  executes tools as tool calls stream in while preserving result order.
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:45-48`
  uses sibling abort control so a Bash error can stop sibling subprocesses
  without aborting the parent turn.
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:262-390`
  separates progress events from final tool results and maps abort/error states
  into explicit tool_result blocks.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:337-480`
  resolves tool aliases and returns explicit error tool_results for missing or
  cancelled tools.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:599-733`
  validates input and converts validation failures into model-visible tool
  errors.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:775-793`
  backfills observer-only input on a shallow clone so hooks and permission checks
  can see derived fields without mutating the API-bound tool call.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:1207-1222`
  executes the tool with a progress callback.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:1403-1474`
  emits the final mapped tool result as a user message after persistence and
  budget processing.

Concept to copy: keep progress plumbing and final proof plumbing separate. Never
let a progress callback become the acceptance artifact.

### Long waits, sleep, streaming, and background shell

Claude Code uses background tasks and output files for commands that exceed the
assistant-mode blocking budget.

- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:54-57`
  defines a two-second progress threshold and a fifteen-second assistant-mode
  blocking budget.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:220-241`
  exposes `timeout` and `run_in_background`.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:317-337`
  detects long standalone or leading `sleep`.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:524-533`
  blocks long foreground sleep when monitoring/background support is available,
  telling the model to use background execution or monitoring.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:555-623`
  maps Bash results into tool_result content. Interrupted commands are errors;
  background commands include task id and output path, not success.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:650-678`
  streams progress messages with elapsed time, output, full output, line counts,
  byte counts, task id, and timeout.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:881-898`
  runs shell commands with timeout, progress, sandbox, and auto-background
  controls.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:923-963`
  backgrounds an existing foreground task in place, avoiding duplicate task
  starts and preserving the process.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:965-982`
  auto-backgrounds after timeout or the assistant blocking budget; the command
  keeps running instead of being killed solely because the assistant wait ended.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:985-1000`
  returns immediately for explicit `run_in_background`.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1003-1029`
  starts `TaskOutput` polling after the progress threshold.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1033-1100`
  either returns a clean completed output if the command finishes or a background
  task id if it remains running.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1108-1138`
  registers foreground/background task metadata and yields progress.
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:44-103`
  detects stalled output that looks like an interactive prompt while staying
  silent for normal slow builds.
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:180-245`
  creates shell tasks whose output is owned by `TaskOutput`; completion updates
  task state and enqueues a notification while preserving the output file.
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:293-367`
  and `:420-474` background foreground tasks in place and set completion
  handlers.
- `references/fresh-cli/claude-code/src/utils/ShellCommand.ts:135-141`
  auto-backgrounds on timeout when allowed; otherwise timeout kills the process.
- `references/fresh-cli/claude-code/src/utils/ShellCommand.ts:186-193`
  treats user interrupt as a reason that does not kill the process, allowing the
  caller to background it.
- `references/fresh-cli/claude-code/src/utils/ShellCommand.ts:349-366`
  removes timeout/listeners and starts file-size monitoring when a command is
  backgrounded.

Concept to copy: a long build should be backgroundable or pollable before it is
killed for assistant wall time. The controller should know whether it is waiting
on an existing process, starting a rerun, or collecting final status.

### Output persistence and proof boundaries

Claude Code stores shell output outside the prompt and makes the model retrieve
it explicitly when needed.

- `references/fresh-cli/claude-code/src/utils/Shell.ts:281-312` creates
  `TaskOutput` and routes stdout/stderr to a file descriptor in file mode.
- `references/fresh-cli/claude-code/src/utils/Shell.ts:385-421` updates cwd only
  for completed foreground commands and cleans up task resources without
  corrupting background output.
- `references/fresh-cli/claude-code/src/utils/task/TaskOutput.ts:21-31` defines
  `TaskOutput` as the single output owner; file mode writes stdout/stderr
  directly to disk while progress comes from tail polling.
- `references/fresh-cli/claude-code/src/utils/task/TaskOutput.ts:77-140`
  manages shared polling and wakes progress loops even when no new output
  arrives.
- `references/fresh-cli/claude-code/src/utils/task/TaskOutput.ts:278-326`
  reads bounded stdout from disk and returns an explicit diagnostic if the output
  file is missing, preserving evidence of evidence loss.
- `references/fresh-cli/claude-code/src/utils/task/diskOutput.ts:25-48`
  caps task output storage and includes session id in the output directory so
  concurrent sessions do not delete each other's in-flight outputs.
- `references/fresh-cli/claude-code/src/utils/task/diskOutput.ts:268-370`
  appends, flushes, evicts handles, and bounds delta/tail reads.
- `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:144-181`
  retrieves output/logs from running or completed background tasks.
- `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:219-239`
  non-blockingly returns current task state or not-ready.
- `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:242-307`
  can block for completion with timeout and returns task status, exit code, and
  output in the tool_result.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:728-753`
  copies or hardlinks large output to the tool-results directory, truncating over
  a hard cap.

Concept to copy: durable output references plus explicit task status are better
than trying to keep entire build logs in prompt memory.

### Prompt/cache sectioning

Claude Code aggressively protects cached prompt structure and compaction state
from stale or unstable tool output.

- `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:16-37`
  distinguishes memoized prompt sections from deliberately uncached sections.
- `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:43-67`
  resolves cached sections and clears them on `/clear` or `/compact`.
- `references/fresh-cli/claude-code/src/services/compact/prompt.ts:61-77`
  requires summaries to preserve user intent, files/code touched, errors/fixes,
  pending work, and a next step tied to the latest request.
- `references/fresh-cli/claude-code/src/services/compact/prompt.ts:206-223`
  supports partial compaction as continuing context.
- `references/fresh-cli/claude-code/src/services/compact/microCompact.ts:262-304`
  only uses cached microcompact in the main thread and removes tool results via
  cache edit without mutating local messages.
- `references/fresh-cli/claude-code/src/services/compact/microCompact.ts:409-522`
  performs time-based microcompact, clears old tool results when cache is cold,
  preserves at least one recent result, and resets cache-break detection.
- `references/fresh-cli/claude-code/src/services/compact/autoCompact.ts:257-305`
  has a circuit breaker for repeated autocompact failure and resets memory/cache
  tracking after session-memory compaction.
- `references/fresh-cli/claude-code/src/utils/toolResultStorage.ts:575-599`
  aggregates tool results by wire-level user message to avoid budget mistakes.
- `references/fresh-cli/claude-code/src/utils/toolResultStorage.ts:641-768`
  partitions tool results into must-reapply/frozen/fresh and replaces only fresh
  large results so prior cache decisions stay stable.
- `references/fresh-cli/claude-code/src/utils/toolResultStorage.ts:938-970`
  reconstructs replacement state from transcript on resume.

Concept to copy only selectively: mew already has prompt section ids and hashes.
The relevant idea is not Claude's whole cache system; it is that continuation
state must be reconstructable from durable transcript/output refs after
compaction.

### Tool permissions

Claude Code's permission system is broad and fail-closed.

- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:916-932`
  keeps permission decisions separate from tool execution.
- `references/fresh-cli/claude-code/src/services/tools/toolExecution.ts:995-1103`
  maps deny/ask paths into explicit tool_result failures and optional hooks.
- `references/fresh-cli/claude-code/src/services/tools/toolHooks.ts:321-405`
  enforces that hook allow cannot bypass settings deny/ask or later permission
  checks.
- `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:1060-1156`
  checks whole-tool, tool-specific, content-specific, and safety rules before
  bypass.
- `references/fresh-cli/claude-code/src/utils/permissions/permissions.ts:1158-1319`
  runs the full deny/ask/allow pipeline.
- `references/fresh-cli/claude-code/src/hooks/useCanUseTool.tsx:27-168`
  routes permission decisions through coordinator, swarm, interactive, and
  classifier-assisted paths.
- `references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts:95-103`
  caps subcommand fanout and falls back to ask.
- `references/fresh-cli/claude-code/src/tools/BashTool/bashPermissions.ts:1663-1845`
  parses Bash permissions via AST and treats complex/unsafe cases as ask.

Concept not to copy now: M6.24's blocker is continuation/budget, not an
interactive permission-stack gap. Keep mew's changes in the work-session/tool
runtime lane unless a permission failure appears in evidence.

### Todo and state continuity

Claude Code uses explicit todo state and transcript restoration to keep long
work coherent.

- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:65-103`
  stores todos keyed by agent id or session id and clears when all are complete.
- `references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:104-114`
  reminds the model to keep using the todo list and may nudge verification.
- `references/fresh-cli/claude-code/src/utils/sessionRestore.ts:72-149`
  restores last todo state, file history, attribution, context-collapse state,
  and todos from the transcript.
- `references/fresh-cli/claude-code/src/utils/sessionRestore.ts:340-389`
  restores worktree/cwd state on resume and clears memory/system prompt/plans
  caches when the worktree changes.

Concept to copy selectively: state continuity belongs in durable reducer state,
not only in model prose. Mew's `LongBuildState` is the right target surface.

## 3. Comparison To Mew M6.24

### Already adopted

Mew has already adopted the core proof-boundary and typed-state direction:

- `src/mew/long_build_substrate.py` defines `CommandEvidence`,
  `LongBuildContract`, `BuildAttempt`, `LongBuildState`, and `RecoveryDecision`.
  These correspond to the reference pattern of separating terminal evidence,
  semantic build interpretation, and controller recovery policy.
- `src/mew/work_session.py` records native command evidence start/finish events
  and renders long-build state/recovery budget into resume context.
- `src/mew/commands.py` enforces work-tool wall timeout ceilings and records
  wall-time stop reasons.
- `src/mew/work_loop.py` routes acceptance guidance through command evidence
  references instead of model-only claims.
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md` correctly defers a
  full managed long command until the typed state/reducer layers exist.
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` and
  `docs/M6_24_DECISION_LEDGER.md` correctly classify the current selected chain
  as:

  ```
  M6.24 -> long_dependency_toolchain_build_strategy_contract
         -> wall-time/continuation budget -> compile-compcert
  ```

### Missing

The current missing piece is generic continuation for a long command that is
still doing useful work when the foreground wall envelope runs out.

The latest compile-compcert speed rerun reached source readback, external
dependency setup, `make depend`, and explicit `make -j"$(nproc)" ccomp`, then
stopped with `work_report.stop_reason=wall_timeout` while final build work was
still running. The terminal evidence had no successful compiler artifact and no
finished exit code for the final build. In reference terms, mew hit a state that
should be "live process/task; continue or poll" but currently becomes "work
session wall timeout; classify and rerun."

Concretely missing:

- a durable `long_command_ref` or equivalent process/task handle for selected
  long-build commands;
- a bounded foreground yield that does not imply command failure;
- a poll/continue action that can collect more output or final exit status;
- durable output refs for large build logs;
- `RecoveryDecision` logic that prefers continuing an existing live build over
  restarting an idempotent build when the state says the build is still running;
- resume reconstruction that can say "this build command is still running",
  "this command ended and has final evidence", or "the continuation handle was
  lost, so recovery must refresh state before deciding."

### Should not be copied yet

Do not copy these reference systems wholesale for M6.24:

- Codex's full unified exec stack. Mew needs only the generic long-build subset:
  stable handle, bounded yield, poll/continue, durable head/tail/output ref, and
  terminal evidence promotion.
- Claude's full background-task UI, monitor system, sleep-specific policy, and
  interactive task notification machinery. Mew does not need a general assistant
  shell UX to fix the current upper-level cause.
- Claude's full permission and hook pipeline. No M6.24 evidence currently points
  to permission orchestration as the blocker.
- A Terminal-Bench or compile-compcert-specific recipe. The design must remain a
  generic long dependency/source-build substrate.
- More prompt-profile accretion. The references solve this class with durable
  state and tool lifecycle boundaries, not additional task-specific reminders.

## 4. Smallest Generic Mew Design Direction

Keep the existing M6.24 substrate and add only the missing continuation surface
if the timeout-shape diagnostic confirms it is needed.

The smallest generic direction is a managed long-build command layer, narrower
than Codex unified exec and narrower than Claude background tasks:

1. Identify eligible long-build commands through existing
   `LongBuildContract`/`BuildAttempt` classification, not task names.
2. Start eligible commands with a stable `long_command_ref`, command/cwd/env
   summary, start time, timeout/budget fields, and durable output ref.
3. Return bounded head/tail progress after the initial wait. Mark it as
   non-terminal progress, not acceptance evidence.
4. Add a poll/continue action that can wait again, append output, and either
   preserve the live ref or promote the result into terminal `CommandEvidence`
   with exit code and final output refs.
5. Teach `RecoveryDecision` to spend wall budget on continuing a live long build
   before rerunning the same build command.
6. If the handle/output ref is lost, force a state refresh or conservative rerun
   classification instead of letting stale resume prose decide success.
7. Keep acceptance unchanged: only terminal successful command evidence plus
   task-required artifact/readback evidence can close the task.

This is essentially Phase 6 of
`docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`, but it should remain a
small long-build primitive rather than a general terminal replacement.

## 5. Next Action Decision

Choose (a): one timeout-shape diagnostic.

Do not jump straight to implementation yet. The current evidence shows an upper
level wall-time/continuation budget failure, but it does not yet prove whether
the immediate issue is a mismatched outer wall envelope or the absence of a live
continuation primitive.

The diagnostic should rerun the same compile-compcert speed-1 shape with:

- the Harbor/outer agent timeout matched to the larger intended wall envelope;
- a larger `mew --max-wall-seconds`;
- no Terminal-Bench-specific solver rules;
- the same model/task/permissions otherwise preserved;
- explicit recording of whether the final `make -j"$(nproc)" ccomp` reaches
  terminal success, terminal failure, or still-running timeout.

Interpretation:

- If the task passes only with the larger matched wall envelope, do not proceed
  to proof_5. Record that M6.24 needs generic continuation/budget repair before
  close.
- If it still times out inside the final build even with the matched envelope,
  open the generic managed long-build continuation repair immediately.
- If it fails earlier for a different reason, reclassify from fresh terminal
  evidence and avoid stale blocker reuse.

Do not choose (b) yet because immediate implementation risks building the wrong
continuation surface before the run-shape distinction is known. Do not choose
(c) because this report and the existing M6.24 design already provide the needed
reference-backed design basis for the next diagnostic.
