# Review: ForgeCode Long Build Budget Planning

Date: 2026-05-03

Scope: direct source inspection of `references/fresh-cli/forgecode`, compared against the M6.24 compile-compcert failure pattern where mew reached real `make -j ccomp` progress late, then exhausted wall budget before final artifact proof.

## 1. Relevant ForgeCode source

- Product shell tool:
  - `references/fresh-cli/forgecode/crates/forge_services/src/tool_services/shell.rs:15-65` defines `ForgeShell::execute`; it validates the command, delegates to infra, strips ANSI unless requested, and returns stdout/stderr/exit code.
  - `references/fresh-cli/forgecode/crates/forge_infra/src/executor.rs:29-90` prepares the shell process with configured shell `-c`, forced color env vars, piped stdout/stderr, inherited stdin, `current_dir`, and `kill_on_drop(true)`.
  - `references/fresh-cli/forgecode/crates/forge_infra/src/executor.rs:93-149` spawns one command, waits for the child, streams stdout/stderr concurrently, captures all output, and returns only after the command exits.
  - `references/fresh-cli/forgecode/crates/forge_infra/src/executor.rs:186-238` streams output in 1024-byte chunks, writes/flushed chunks to the UI writer, and accumulates the complete output in memory.
  - `references/fresh-cli/forgecode/crates/forge_domain/src/shell.rs:1-12` stores command/stdout/stderr/exit code. Its `success()` treats any nonnegative exit code as transport success, so nonzero shell exits are surfaced as shell output rather than failed tool calls.
  - `references/fresh-cli/forgecode/crates/forge_domain/src/tools/descriptions/shell.md:1-47` documents the shell contract: explicit `cwd`, no `cd`, use specialized file tools for file operations, output may be truncated for display, and the result contains stdout/stderr/exit code.

- Tool timeout, loop, and output shaping:
  - `references/fresh-cli/forgecode/crates/forge_app/src/tool_registry.rs:45-61` wraps ordinary tool calls in `tokio::time::timeout(config.tool_timeout_secs)`.
  - `references/fresh-cli/forgecode/crates/forge_app/src/tool_registry.rs:108-132` treats task-agent tools specially and notes that agents should not timeout.
  - `references/fresh-cli/forgecode/crates/forge_app/src/tool_registry.rs:140-166` applies permission checks before timeout and wraps ordinary Forge tools with the timeout.
  - `references/fresh-cli/forgecode/crates/forge_config/.forge.toml:12-27` sets defaults including `max_requests_per_turn = 100`, shell output line limits, `max_tool_failure_per_turn = 3`, and `tool_timeout_secs = 300`.
  - `references/fresh-cli/forgecode/README.md:813-824` documents `FORGE_TOOL_TIMEOUT=300` as the maximum tool execution time before termination.
  - `references/fresh-cli/forgecode/crates/forge_app/src/tool_executor.rs:68-113` writes full stdout/stderr to temp files when display truncation occurs.
  - `references/fresh-cli/forgecode/crates/forge_app/src/operation.rs:162-198` renders truncated streams with head/tail metadata and a `full_output` path.
  - `references/fresh-cli/forgecode/crates/forge_app/src/truncation/truncate_shell.rs:1-49` and `:139-201` implement prefix/suffix truncation and stream metadata.

- Orchestration and acceptance-adjacent behavior:
  - `references/fresh-cli/forgecode/crates/forge_app/src/orch.rs:56-167` executes task-tool calls in parallel, ordinary tool calls sequentially, emits tool start/end events, and waits for UI readiness before command output appears.
  - `references/fresh-cli/forgecode/crates/forge_app/src/orch.rs:240-452` runs the agent loop, persists turns, retries model requests, executes tools, applies max tool failure and max request guards, and emits `TaskComplete` only after model stop with no tool calls.
  - `references/fresh-cli/forgecode/crates/forge_domain/src/result_stream_ext.rs:56-68` and `:119-165` stream model reasoning/content deltas and tool-call deltas.
  - `references/fresh-cli/forgecode/crates/forge_app/src/hooks/pending_todos.rs:25-30` and `:117-128` inject a reminder if the model tries to finish with pending/in-progress todos.
  - `references/fresh-cli/forgecode/crates/forge_app/src/hooks/doom_loop.rs:12-23` and `:222-249` detect repetitive tool-call patterns and inject a reminder.
  - `references/fresh-cli/forgecode/crates/forge_repo/src/agents/forge.md:47-58` instructs the model to use todos and mark complete only after implementation and verification when appropriate.
  - `references/fresh-cli/forgecode/crates/forge_repo/src/agents/forge.md:120-147` instructs compilation/testing validation and use of specialized tools.

- Benchmark harness:
  - `references/fresh-cli/forgecode/benchmarks/task-executor.ts:49-54` spawns benchmark commands with `child_process.spawn(..., { shell: true, stdio: ["ignore","pipe","pipe"] })`.
  - `references/fresh-cli/forgecode/benchmarks/task-executor.ts:60-92` checks validations after every stdout/stderr chunk and, if `early_exit` is set and validations pass, sends `SIGTERM` and resolves.
  - `references/fresh-cli/forgecode/benchmarks/task-executor.ts:94-108` enforces per-task timeout and sends `SIGKILL`.
  - `references/fresh-cli/forgecode/benchmarks/cli.ts:175-177` runs tasks with configured parallelism.
  - `references/fresh-cli/forgecode/benchmarks/cli.ts:232-256` runs each row's commands sequentially.
  - `references/fresh-cli/forgecode/benchmarks/cli.ts:382-388` exits nonzero only for command failures; validation failures and timeouts affect the summary but not process exit.
  - `references/fresh-cli/forgecode/benchmarks/verification.ts:21-34` supports regex validations over output.
  - `references/fresh-cli/forgecode/benchmarks/verification.ts:39-111` supports shell validations by piping captured output to a validation command.
  - `references/fresh-cli/forgecode/benchmarks/evals/multi_file_patch/task.yml:1-17`, `references/fresh-cli/forgecode/benchmarks/evals/parallel_tool_calls/task.yml:2-8`, and `references/fresh-cli/forgecode/benchmarks/evals/refactoring_uses_patch/task.yml:1-23` show typical short timeouts, high parallelism, `early_exit: true`, and validations that often inspect trace/debug context rather than final compiled artifacts.

## 2. Long-running command handling

ForgeCode product shell execution is live-streaming but not backgrounded. A shell command is spawned, stdout/stderr are streamed to the UI while also being accumulated, and the tool call returns only when the command exits (`executor.rs:93-149`, `executor.rs:186-238`). The executor has a mutex (`executor.rs:14-22`), so only one product shell command runs through that service at a time.

Timeout is per ordinary tool call, not a wall-budget planner. The registry wraps the shell future in `tokio::time::timeout` using `tool_timeout_secs`, whose default is 300 seconds (`tool_registry.rs:45-61`, `.forge.toml:27`). Because the spawned command has `kill_on_drop(true)`, a timed-out future should best-effort kill the direct child when dropped. I did not find explicit process-group cleanup, graceful termination, grandchild cleanup, or post-timeout output drain in the product shell path.

Output visibility is better than a simple buffered shell call. ForgeCode streams chunks live and, when displayed output is too large, records head/tail plus a temp-file path for the full stream (`tool_executor.rs:68-113`, `operation.rs:162-198`). The full stream is still accumulated in memory before the temp dump; this is not a durable log-backed process handle.

ForgeCode has loop guards, not wall guards. `max_requests_per_turn` and `max_tool_failure_per_turn` bound runaway agent loops, while doom-loop and pending-todo hooks nudge the model away from repetitive or premature completion (`orch.rs:372-410`, `pending_todos.rs:25-30`, `doom_loop.rs:12-23`). These mechanisms do not reserve time for a final proof step.

The benchmark harness has a separate process model. It streams logs, checks validations incrementally, kills on timeout, and can early-exit once validations pass (`task-executor.ts:60-108`). That design is useful for benchmark throughput, but it is not the same as the product shell lifecycle and does not provide durable resumable build execution.

## 3. Heavy-build budget planning/admission control

I did not find explicit heavy-build admission control in ForgeCode. There is no source-level concept equivalent to:

- classify a command as a heavyweight build,
- estimate minimum useful build slice,
- recompute remaining wall budget immediately before dispatch,
- reserve final artifact proof time,
- refuse to start if the command cannot reach proof,
- resume or poll a durable long-running build after a turn boundary.

ForgeCode mostly solves comparable tasks through a different architecture and contract:

- live command output and display truncation keep the model informed;
- the tool timeout prevents indefinite hangs;
- the prompt tells the model to verify before completion;
- todo and doom-loop hooks reduce premature or repetitive behavior;
- benchmarks use high parallelism, short timeouts, early validations, and trace-oriented success checks.

That is enough for many short coding benchmarks. It is not enough for mew M6.24's failure mode, because M6.24 needs a time-aware decision before starting the final expensive build and must preserve enough wall for independent artifact proof.

## 4. Why ForgeCode may finish around 10 minutes

The source points to several non-heavy-build reasons:

- Benchmark parallelism: tasks can run with high `parallelism` (`cli.ts:175-177`), and some examples use very high values such as `parallelism: 50` in `benchmarks/evals/multi_file_patch/task.yml:1-7`.
- Early exit: benchmark commands can terminate as soon as validations pass while output is still streaming (`task-executor.ts:60-92`).
- Short per-task timeouts: example evals commonly use 60-240 second task timeouts rather than admitting a long build.
- Trace validations: several benchmark validations inspect ForgeCode trace/context data, such as whether patch or parallel tool calls were used, rather than proving a final compiled artifact (`benchmarks/evals/multi_file_patch/task.yml:8-17`, `benchmarks/evals/parallel_tool_calls/task.yml:2-8`).
- Product timeout default: `FORGE_TOOL_TIMEOUT=300` gives a command up to 5 minutes by default, which is useful for many tasks but too small for a late CompCert final build plus proof reserve.
- Model/tool strategy: the Forge prompt emphasizes specialized tools, semantic search, patching, todos, and validation (`forge.md:131-147`), which helps avoid slow exploratory shell work on benchmark-style tasks.

Therefore, a ~10 minute benchmark finish is not evidence that ForgeCode has solved the generic "late heavyweight build with final artifact proof" problem. It appears to be a combination of benchmark structure, model behavior, prompt discipline, and streaming per-tool execution.

## 5. Concepts mew should adopt generically

- Live long-command output with stable lifecycle events: ForgeCode's `ToolCallStart`/`ToolCallEnd` flow and UI-ready handshake before output (`orch.rs:103-148`) are a good model for making active work observable.
- Head/tail display plus full-output reference: show concise current evidence while preserving the full transcript path (`operation.rs:162-198`, `tool_executor.rs:68-113`).
- Explicit shell contract: require `cwd`, discourage `cd`, require a command description, and make stdout/stderr/exit code first-class output (`shell.md:1-47`).
- Runaway-loop pressure valves: max tool failures, max requests, doom-loop detection, and pending-todo reminders are useful generic safeguards.
- Separate UI progress from acceptance: ForgeCode streams progress well, but mew should pair that with a deterministic acceptance reducer rather than relying on model self-assessment.
- Benchmark-style early validation as optimization only: incremental validation can shorten work when a proof predicate is already satisfied, but it must not replace artifact proof for build tasks.

## 6. What not to copy

- Do not copy product shell execution as the full long-build solution. It is synchronous per tool call and lacks a durable run id, polling API, and resume semantics.
- Do not rely on a fixed 300 second per-tool timeout for heavy builds. M6.24 failed because the final build started too late, not because a single timeout constant was missing.
- Do not rely on `kill_on_drop(true)` alone as process lifecycle cleanup. mew should use process-group cleanup, terminal state recording, and output drain where possible.
- Do not treat prompt/todo completion discipline as artifact acceptance. ForgeCode's TODO hook is useful, but M6.24 needs separate proof that `/tmp/CompCert/ccomp` exists and passes the required smoke check.
- Do not copy benchmark `early_exit` semantics for production acceptance. Some ForgeCode benchmarks validate traces or partial conditions and even exit the benchmark process with success despite validation failures/timeouts being present in the summary (`cli.ts:382-388`).
- Do not use nonzero shell exit handling as the only failure boundary. ForgeCode surfaces exit codes in output, but mew's acceptance path should classify failed commands structurally.

## 7. Proposed minimal M6.24 repair direction

ForgeCode reinforces the same direction as the prior Codex CLI and Claude Code pattern reviews: streaming and process handles are necessary, but admission control and proof separation are the missing M6.24 layer.

Minimal repair:

- Add a generic wall-budget admission gate immediately before heavyweight or finalizing commands. Recompute current remaining wall, classify the stage generically, and require `minimum_useful_stage_time + final_proof_reserve + closeout_guard`.
- If the gate fails, do not start the heavy command. Emit a structured nonterminal result such as `long_command_budget_blocked` with current remaining wall, required reserve, intended command, stage, and latest durable evidence.
- If the gate passes, run the command as a managed long process with a durable run id, process-group lifecycle, streaming head/tail/full-log evidence, poll/resume state, and terminal status.
- Cap the command timeout so the final artifact proof reserve is preserved. A build timeout can be progress evidence, but it cannot be accepted as completion.
- After terminal build success, run a separate acceptance/proof step. For M6.24 that means artifact existence and smoke proof; generically it means the milestone's declared artifact predicate. Progress output, dependency generation, or partial `make` logs are not enough.
- Keep the repair generic. The policy should apply to long dependency builds, large test suites, package compilation, and final artifact production, not to CompCert paths specifically.

ForgeCode's useful contribution is observability: live output, bounded display, lifecycle events, and model-loop safeguards. The missing piece mew must add is a planner/enforcer that decides whether starting or continuing a long build can still leave enough wall budget to prove the result.
