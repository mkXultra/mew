# Review 2026-05-02: Codex CLI Long-Build Continuation Patterns

Reviewer: Codex

Scope:

- Reference implementation audited: `references/fresh-cli/codex`.
- Mew comparison context: M6.24 dossier, decision ledger, gap loop, long-build
  substrate design, and the current compile-compcert timeout classification.
- No mew source code was modified for this review.

## Bottom Line

Codex CLI has two distinct terminal-command paths. The older `exec` path is a
bounded command runner with timeout, output capture, and terminal begin/end
events. The newer `unified_exec` path is the relevant pattern for M6.24:
commands can yield while still running, keep a process/session id, stream output
deltas, preserve a bounded transcript, accept later polling or stdin, and emit a
single terminal end event when the process finally exits.

Mew M6.24 has already adopted much of the evidence and reducer philosophy:
terminal command evidence is authoritative, timed-out builds cannot satisfy
acceptance, long-build state is explicit, stale same-evidence blockers are being
cleared more carefully, and wall-budget reserves now exist. The important missing
generic piece is live long-command continuation: a command can currently consume
wall time and be killed, but mew does not yet have a Codex-style process handle
plus poll/finalize lifecycle that separates "running progress evidence" from
"terminal acceptance evidence."

## 1. Codex CLI Mechanisms

### Bounded command execution

`references/fresh-cli/codex/codex-rs/core/src/exec.rs` implements the traditional
bounded command path:

- `ExecParams` carries command, cwd, environment, sandbox policy, capture policy,
  and `ExecExpiration`.
- `ExecExpiration::{Timeout, DefaultTimeout, Cancellation}` gives every command
  an explicit timeout or cancellation token.
- `consume_output()` waits for child exit, expiration, or Ctrl-C. On timeout or
  interrupt it kills the process group and still drains available output.
- `read_output()` continuously drains stdout and stderr so the child does not
  block on full pipes. It emits `ExecCommandOutputDelta` events while retaining
  capped output for the tool result.
- `finalize_exec_result()` returns `ExecToolCallOutput` with `exit_code`,
  stdout, stderr, aggregated output, duration, and `timed_out`; timeout errors
  still carry captured output.
- `aggregate_output()` keeps a bounded stdout/stderr aggregate rather than
  allowing unbounded terminal text to enter model context.

The event boundary for this path is in:

- `references/fresh-cli/codex/codex-rs/core/src/tools/events.rs`
  (`ToolEmitter::exec`, `emit_exec_begin`, `emit_exec_end`).
- `references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs`
  (`ExecCommandBeginEvent`, `ExecCommandOutputDeltaEvent`,
  `ExecCommandEndEvent`).

The key lesson is that even the short command path treats terminal output as a
typed event stream with a terminal end record, not as unstructured assistant
memory.

### Long-running command continuation

The more relevant design is `unified_exec`.

Tool schema and model-facing fields are defined in
`references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs`:

- `ExecCommandArgs` accepts `yield_time_ms`, `max_output_tokens`, optional `tty`,
  workdir, shell, sandbox policy, and approval metadata.
- `WriteStdinArgs` accepts a `session_id`, optional input bytes, yield time, and
  output token cap. Empty input acts as poll.
- `UnifiedExecHandler::handle_exec_command()` returns an
  `ExecCommandToolOutput` that includes `process_id` when the process is still
  running and `exit_code` when it has finished.
- `UnifiedExecHandler::handle_write_stdin()` polls or writes to the same
  process session.

The runtime substrate is in
`references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs` and
`references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs`:

- `ProcessStore` holds live `ProcessEntry` records keyed by process id.
- `UnifiedExecProcessManager::allocate_process_id()` reserves an id before the
  command starts, so the id can appear in begin events and later tool output.
- `UnifiedExecProcessManager::exec_command()` starts the process, starts output
  streaming immediately, waits only until the requested yield deadline, and if
  the process is still alive stores it before returning to the model.
- `UnifiedExecProcessManager::write_stdin()` refreshes process state, writes
  input for TTY sessions, or polls with an empty input. It returns the next output
  chunk plus either `process_id` or `exit_code`.
- `collect_output_until_deadline()` watches output, process exit, output closure,
  and cancellation. After process exit it waits briefly for trailing output.
- `store_process()` records the live process and starts a background exit watcher
  so the terminal event is emitted even after the initial tool call yielded.
- `prune_processes_if_needed()` bounds the number of live processes and prefers
  pruning exited or least-recently-used sessions.

Process ownership and output streaming are split into:

- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process.rs`
  (`UnifiedExecProcess`, `write`, `terminate`, `output_handles`,
  `spawn_local_output_task`, `spawn_exec_server_output_task`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs`
  (`start_streaming_output`, `spawn_exit_watcher`,
  `emit_exec_end_for_unified_exec`, `resolve_aggregated_output`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
  (`HeadTailBuffer`), which preserves a bounded prefix and suffix transcript.

The model-facing response format is in
`references/fresh-cli/codex/codex-rs/core/src/tools/context.rs`:
`ExecCommandToolOutput::response_text()` reports chunk id, wall time, output,
original token count, and one of:

- `Process running with session ID ...`
- `Process exited with code ...`

This is the precise pattern mew lacks for long source builds: a nonterminal tool
response can return progress while the authoritative terminal result remains
pending.

### Timeouts and interrupts

Codex has separate timeout/interrupt behavior for short and long command paths:

- Short `exec`: `ExecExpiration`, `consume_output()`, and
  `IO_DRAIN_TIMEOUT_MS` kill and drain the process on timeout or Ctrl-C.
- `unified_exec`: initial yields are clamped by
  `MIN_YIELD_TIME_MS`/`MAX_YIELD_TIME_MS`; empty polls can wait longer; live
  processes remain in `ProcessStore`; `UnifiedExecProcess::terminate()` cancels
  the stream, updates state, and aborts the output task.
- CLI interrupt plumbing in
  `references/fresh-cli/codex/codex-rs/exec/src/lib.rs` sends `turn/interrupt`
  instead of pretending the interrupted turn completed normally.

### Continuation after tool calls

Continuation after terminal or tool calls is handled by the turn loop:

- `references/fresh-cli/codex/codex-rs/core/src/session/turn.rs`
  (`run_turn`, `try_run_sampling_request`, `drain_in_flight`) keeps looping while
  tool calls require follow-up.
- `references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs`
  (`handle_output_item_done`, `record_completed_response_item`,
  `drain_in_flight`) records the model's completed tool-call item, runs the tool,
  records the tool response into history, and only then samples the next model
  response.

The important property is that a follow-up model turn is built from recorded
history after the tool result, not from stale local assumptions that predate the
tool call.

## 2. Stale State and Authoritative Evidence Boundaries

Codex avoids stale post-tool state through append-only typed events and history
reconstruction:

- `references/fresh-cli/codex/codex-rs/core/src/session/mod.rs`
  (`record_conversation_items`, `send_event`, `persist_rollout_items`,
  `flush_rollout`, `ensure_rollout_materialized`) persists conversation items
  and event messages into the rollout.
- `references/fresh-cli/codex/codex-rs/core/src/session/rollout_reconstruction.rs`
  (`reconstruct_history_from_rollout`) rebuilds resumed history from the durable
  rollout suffix, respecting compaction/replacement boundaries.
- `references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs`
  (`ToolCallRuntime::handle_tool_call`) serializes mutating tools behind a write
  lock while allowing safe parallel read tools.
- `references/fresh-cli/codex/codex-rs/core/src/tools/registry.rs`
  (`dispatch_any`) centralizes pre-hooks, post-hooks, active tool-call tracking,
  mutation gates, and telemetry.

The authoritative output boundary is also explicit:

- Streaming deltas are progress evidence: `ExecCommandOutputDeltaEvent`.
- Running `unified_exec` responses are snapshots: they include `process_id` and
  no exit code.
- Terminal evidence is the end event: `ExecCommandEndEvent` with command, cwd,
  process id, stdout/stderr/aggregate, exit code, duration, formatted output,
  and status.
- `ExecCommandToolOutput::post_tool_use_response()` only provides post-tool
  command output for completed non-running commands with hook output. It does
  not treat a running snapshot as a final post-tool-use answer.

One caution for mew: Codex's rollout persistence may intentionally truncate
terminal output. In
`references/fresh-cli/codex/codex-rs/rollout/src/recorder.rs`,
`sanitize_rollout_item_for_persistence()` keeps bounded
`ExecCommandEnd.aggregated_output` and clears some large fields in extended
mode. That is fine for Codex chat continuity, but mew's acceptance lane may need
an explicit `CommandEvidence` artifact/log object if full terminal proof must
outlive model context truncation.

## 3. Patch, Apply, and Review Lifecycle Ideas

Codex treats patch application as a first-class lifecycle, not just a shell
command:

- `references/fresh-cli/codex/codex-rs/apply-patch/src/parser.rs`
  (`parse_patch`, `parse_patch_streaming`, `ParseMode`) separates strict
  application parsing from lenient or streaming progress parsing.
- `references/fresh-cli/codex/codex-rs/apply-patch/src/lib.rs`
  (`maybe_parse_apply_patch_verified`, `ApplyPatchAction`, `apply_patch`,
  `apply_hunks_to_files`, `print_summary`) verifies patch shape before mutation
  and reports a structured file summary.
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs`
  (`ApplyPatchArgumentDiffConsumer`, `ApplyPatchHandler`,
  `intercept_apply_patch`) emits patch begin/update/end events and routes
  accidental `apply_patch` shell invocations through the same verified handler.
- `references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/apply_patch.rs`
  (`ApplyPatchRuntime`) handles approval keys, sandbox context, and execution.
- `references/fresh-cli/codex/codex-rs/core/src/tools/events.rs`
  (`emit_patch_begin`, `emit_patch_updated`, `emit_patch_end`,
  `TurnDiffEvent`) connects patch application to a turn diff.

Relevant mew idea: implement-lane mutations should have typed begin/update/end
records, parsed change identity, post-mutation diff evidence, and review hooks.
Long-build tasks should avoid hiding source/build mutations inside generic
terminal text when those mutations affect later proof.

Codex review mode is also separated from implementation:

- `references/fresh-cli/codex/codex-rs/core/review_prompt.md` defines structured
  reviewer output and prioritization.
- `references/fresh-cli/codex/codex-rs/core/src/review_prompts.rs`
  (`ReviewTarget`, `resolve_review_request`) builds review prompts for
  uncommitted changes, base branches, commits, or custom targets.
- `references/fresh-cli/codex/codex-rs/core/src/session/review.rs`
  (`spawn_review_thread`) starts review in a separate thread/turn.
- `references/fresh-cli/codex/codex-rs/core/src/tasks/review.rs`
  (`ReviewTask`, `process_review_events`, `exit_review_mode`) records the final
  review output back into the main rollout.

Relevant mew idea: review should be a separate lifecycle product with durable
findings, not a hidden side effect of the implementation turn. That matters for
long-build repairs because review should inspect the actual diff, evidence
contracts, and reducer transitions before a costly rerun.

## 4. Mew M6.24 Comparison

### Already adopted or convergent

Mew M6.24 has already adopted the core acceptance philosophy that Codex's
terminal model suggests:

- `CommandEvidence` is planned as the canonical evidence record in
  `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`.
- Final acceptance rejects timed-out, non-terminal, masked, spoofed, or
  post-mutation evidence.
- `long_dependency_build_state` makes long-build status explicit instead of
  letting old blockers float in prompt text.
- `LongBuildAttempt` and `RecoveryDecision` are convergent with Codex's idea
  that command result, wall time, and recovery state are typed records.
- The decision ledger records repairs for stale blocker clearing, terminal
  acceptance closeout, source authority, compact recovery under timeout ceiling,
  and final recovery-budget reserve.
- The current timeout classification correctly names the live blocker as
  `long-build wall-time/continuation budget`, not as a new task-specific
  compile strategy rule.

### Missing patterns

The missing Codex-like substrate is generic live command continuation:

- No durable process/session id comparable to `unified_exec` `process_id`.
- No start/yield/poll/finalize lifecycle for one long command attempt.
- No background watcher that emits the terminal command evidence after the
  first model-facing tool response has returned.
- No model-visible distinction equivalent to "Process running with session ID"
  versus "Process exited with code".
- No bounded transcript object equivalent to `HeadTailBuffer` that can feed
  both model context and durable command evidence without conflating the two.
- No generic `write_stdin`/poll equivalent for interactive or long-running
  commands. For M6.24, empty poll is more important than stdin.
- No budget policy that can say: "do not start a new long command, but continue
  polling the already-started long command because it is the current evidence
  chain."
- No final terminal event that automatically resolves or preserves blockers from
  the latest command attempt after a yield.

### Patterns not worth copying yet

Do not copy the whole Codex implementation surface into mew yet:

- Full PTY stdin support is not necessary for the current long-build blocker.
  Poll-only continuation is likely enough for the first generic slice.
- Codex's 64-process LRU process store is more general than mew needs. Mew can
  start with one active long command per work session or per task stage.
- Remote exec-server support and Codex sandbox approval plumbing are not the
  current M6.24 gap.
- Codex rollout truncation is not an acceptance-evidence design. Mew should not
  copy truncation unless it also stores separate durable command evidence.
- Codex review threads are useful as a lifecycle pattern, but mew does not need
  to copy the whole chat-thread implementation to make implement-lane review
  cleaner.
- Auto-compaction and model-client window management are adjacent, not the core
  wall-time/continuation fix.

One documentation drift to resolve: `docs/M6_24_GAP_IMPROVEMENT_LOOP.md` still
names Long-Build Substrate Phase 0 as the selected next action, while the latest
decision ledger and timeout classification identify
`long-build wall-time/continuation budget`. Treat the ledger plus current timeout
classification as the fresher blocker state.

## 5. Smallest Generic Mew Design Direction

The smallest generic design direction is a minimal long-command continuation
layer, not a compile-compcert-specific timeout patch.

Add a `LongCommandRun` or equivalent runtime record underneath
`CommandEvidence`:

- `start`: run a high-cost command with stage, cwd, command hash, artifact
  targets, requested timeout, wall budget, recovery reserve, yield time, and
  capture policy.
- `yield`: if still running, persist a live command/session id, elapsed wall
  time, bounded head/tail output snapshot, current stage, and linked
  `CommandEvidence` id in `running` state. This state cannot satisfy
  acceptance.
- `poll`: refresh the same command/session id and append progress snapshots
  without starting a new broad command or resurrecting stale blockers.
- `finalize`: on exit, write one terminal `CommandEvidence` record with exit
  code, duration, timeout/killed status, final bounded transcript, and artifact
  proof metadata. Only this terminal record can clear final acceptance.
- `interrupt`: explicitly mark killed/interrupted command evidence and preserve
  the last transcript snapshot for recovery planning.

Budget policy should be stage-aware but generic:

- Refuse to start a new long command unless minimum expected run time plus
  recovery reserve fits the remaining wall budget.
- Permit polling or finalization of the already-running command when it is the
  active evidence chain and enough reserve remains for closeout.
- If wall budget is exhausted before terminal success, persist a resumable
  continuation state instead of converting old source/proof blockers into the
  current failure.
- Recovery decisions must read the latest live or terminal command state, but
  acceptance must read only terminal success evidence.

This is intentionally narrower than full Codex `unified_exec`: one active long
command, poll-first continuation, bounded transcript, terminal evidence, and
budget state are enough for the current upper-level failure class.

## 6. Recommended Next Action

Next action should be **reference-backed redesign first**.

Reason: the current evidence already shows the strategy reached the intended
final build and was killed during the long command. A one-time timeout-shape
diagnostic can answer whether extra outer wall time lets this exact task pass,
but it does not add much information about the product substrate. Immediate
implementation without first pinning the generic start/yield/poll/finalize
contract risks another narrow budget patch that still lacks a durable evidence
boundary.

The redesign can be small:

1. Amend the M6.24 long-build substrate design with a minimal
   Codex-style long-command continuation contract.
2. Define the persisted states and reducer rules for running versus terminal
   command evidence.
3. Then implement the smallest poll-only continuation slice and test it against
   generic long-running dependency/toolchain fixtures.

Do not make the next repair Terminal-Bench or compile-compcert specific. The
blocker class is now the generic wall-time/continuation boundary for long
source-build tasks.
