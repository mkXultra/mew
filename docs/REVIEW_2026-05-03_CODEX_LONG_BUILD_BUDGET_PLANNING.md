# Codex CLI Long Build Budget Planning Review

Date: 2026-05-03

Scope: read-only source inspection of `references/fresh-cli/codex`, with orientation from `docs/ADOPT_FROM_REFERENCES.md` and `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md`. The comparison target is mew M6.24's current failure mode: a hard build reaches real progress late, then exhausts wall budget before final artifact proof.

## 1. Relevant Codex Source Files And Functions

Classic shell execution:

- `references/fresh-cli/codex/codex-rs/protocol/src/models.rs` defines `ShellToolCallParams` / `ShellCommandToolCallParams` with optional `timeout_ms`.
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/shell.rs`
  - `ShellHandler::to_exec_params` and `ShellCommandHandler::to_exec_params` map model `timeout_ms` into `ExecParams.expiration`.
  - `run_exec_like` emits begin/finish events and routes shell execution through the shared orchestrator.
- `references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/shell.rs`
  - `ShellRequest` carries `timeout_ms`.
  - `ShellRuntime::run` builds `ExecOptions { expiration: req.timeout_ms.into(), capture_policy: ShellTool }`.
- `references/fresh-cli/codex/codex-rs/core/src/exec.rs`
  - `DEFAULT_EXEC_COMMAND_TIMEOUT_MS` is 10 seconds (`exec.rs:51`).
  - `ExecExpiration::{Timeout, DefaultTimeout, Cancellation}` controls classic exec termination (`exec.rs:149-182`).
  - `consume_output` waits for process exit, expiration, or Ctrl-C; on expiration it kills the process group and child (`exec.rs:1232-1290`).
  - `read_output` streams `ExecCommandOutputDelta` chunks while retaining capped output (`exec.rs:1331-1385`).

Unified exec / resumable long-running process execution:

- `references/fresh-cli/codex/codex-rs/tools/src/tool_config.rs`
  - `ToolsConfig::new` selects `ConfigShellToolType::UnifiedExec` when the feature and environment support it.
- `references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs`
  - Registers `exec_command` and `write_stdin` for unified exec.
- `references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs`
  - `create_exec_command_tool` describes `exec_command` as returning output or a session id for ongoing interaction (`local_tool.rs:19-90`).
  - `create_write_stdin_tool` describes polling or writing to an existing session (`local_tool.rs:92-134`).
  - Output schema includes `wall_time_seconds`, `exit_code`, `session_id`, `original_token_count`, and `output` (`local_tool.rs:300-330`).
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
  - `ExecCommandArgs` defaults `yield_time_ms` to 10,000 ms; `WriteStdinArgs` defaults to 250 ms (`unified_exec.rs:45-88`).
  - Handler allocates a process id, normalizes shell command/permissions, then calls `UnifiedExecProcessManager::exec_command` (`unified_exec.rs:209-355`).
  - `write_stdin` maps model `session_id` to `UnifiedExecProcessManager::write_stdin` and emits a `TerminalInteraction` event (`unified_exec.rs:382-407`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs`
  - Top-level comment states the responsibility: manage interactive processes, reusable handles, capped buffers, approvals, sandbox retry (`mod.rs:1-23`).
  - Yield and retention constants: min initial yield 250 ms, min empty poll 5,000 ms, max initial/non-empty yield 30,000 ms, default max background poll 300,000 ms, output cap 1 MiB, process cap 64 (`mod.rs:59-70`).
  - `ExecCommandRequest` and `WriteStdinRequest` carry command, process id, yield window, output cap, tty, permissions (`mod.rs:88-111`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs`
  - `exec_command` opens a process, emits begin, starts streaming, stores live process before yielding, waits only until the yield deadline, and returns `process_id` if still alive (`process_manager.rs:231-406`).
  - `write_stdin` writes to tty sessions or polls empty input; empty polls are clamped between 5 seconds and the configured max background wait, default 5 minutes (`process_manager.rs:408-524`).
  - Process store, pruning, exit watcher, and `terminate_all_processes` manage lifecycle (`process_manager.rs:527-1047`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/process.rs`
  - `UnifiedExecProcess` owns process handle, output buffer, broadcast channel, cancellation token, and lifecycle task.
  - `write`, `has_exited`, `exit_code`, and `terminate` are the process lifecycle surface.
  - `Drop` terminates the process when the handle is dropped.
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs`
  - `start_streaming_output` continuously emits output deltas from the running process (`async_watcher.rs:37-102`).
  - `spawn_exit_watcher` emits one terminal `ExecCommandEnd` after process exit and output drain (`async_watcher.rs:104-156`).
  - Unified exec terminal events set `timed_out: false`; unified exec is not using a per-command wall timeout in this path (`async_watcher.rs:190-214`).
- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
  - Capped head/tail buffer preserves useful transcript context and drops middle output under cap pressure.

Shared tool policy and proof/goal handling:

- `references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs` centralizes approval, sandbox selection, execution attempt, and retry-on-sandbox-denial.
- `references/fresh-cli/codex/codex-rs/core/src/tools/sandboxing.rs` defines approval requirements and sandbox override behavior.
- `references/fresh-cli/codex/codex-rs/core/templates/goals/continuation.md`
  - Injects time/token budget context and requires a completion audit against real files, command output, tests, PR state, or other evidence before marking complete (`continuation.md:9-28`).
- `references/fresh-cli/codex/codex-rs/core/templates/goals/budget_limit.md`
  - On budget limit, forbids new substantive work and forbids `update_goal` unless complete (`budget_limit.md:1-16`).
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/goal.rs`
  - The goal contract intentionally splits creation from completion; `update_goal` can only mark the existing goal complete (`goal.rs:1-5`, `goal.rs:156-184`).
- `references/fresh-cli/codex/codex-rs/core/src/goals.rs`
  - Accounts goal progress on turn/tool lifecycle events and can inject continuation or budget-limit steering.

Orientation docs:

- `docs/ADOPT_FROM_REFERENCES.md` already identifies Codex's streaming tool executor as a reference pattern worth adopting.
- `docs/REVIEW_2026-04-20_MISSING_PATTERNS_SURVEY.md` frames reference adoption as evidence-based pattern transfer, which matches this review's approach.

## 2. What Codex CLI Does For Long Commands

Codex has two execution modes with different semantics.

Classic shell execution is timeout-bound and blocking. If a command does not finish by `timeout_ms` or the 10-second default, `consume_output` kills the process group and child, drains stdout/stderr with a 2-second guard, marks the result timed out, and returns an exec result. It streams output deltas while reading pipes, but the command lifecycle is still one tool call.

Unified exec is the long-running-command mechanism. `exec_command` starts a process, stores it in a process manager, starts a background streaming task, waits only for a bounded yield window, and returns either an `exit_code` if the command finished or a `session_id`/process id if it is still running. The model can then call `write_stdin` with empty `chars` to poll for more output or with input for tty sessions. Initial yield is clamped to 250 ms to 30 seconds. Empty polling is clamped to at least 5 seconds and up to the configured background wait, default 5 minutes.

Output has two channels:

- Event stream: background tasks emit `ExecCommandOutputDelta` chunks while the command runs, then one terminal `ExecCommandEnd` when the process exits and output is drained.
- Tool response: each `exec_command` / `write_stdin` call returns a bounded snapshot with `wall_time_seconds`, `output`, `original_token_count`, and either `session_id` or `exit_code`.

Lifecycle is explicit:

- Live processes are stored before the first yield so interruption does not drop the last handle and kill the process.
- Process ids are refreshed and removed on exit.
- Old process entries are pruned under a cap.
- Session shutdown can terminate all managed processes.
- Dropping a `UnifiedExecProcess` terminates it, so stored ownership is the durability boundary.

The important design point is that Codex separates "how long this tool call waits for output" from "how long the process may live." Long builds continue outside the current model wait window and are resumed by process id.

## 3. Budget Planning / Admission Control Finding

I did not find explicit heavy-build budget planning or admission control in the Codex CLI paths inspected.

Codex does enforce resource and interaction bounds:

- Classic shell has per-call timeout and process-group kill.
- Unified exec clamps yield/poll wait windows.
- Unified exec caps retained output and emitted deltas.
- Unified exec caps stored processes and prunes old entries.
- The orchestrator controls approval, sandboxing, and retry.
- Goal runtime tracks time/tokens and injects continuation or budget-limit steering.

But the unified exec long-command path does not appear to estimate command duration, classify heavy build stages, reserve wall time for final proof, or reject a build because the remaining external wall budget is too small. `yield_time_ms` controls how long Codex waits before yielding output; it is not a lifecycle timeout or admission budget. The default 5-minute empty poll is also a wait window, not proof that the process has enough total wall budget to finish.

Codex solves the common long-command UX problem differently: it makes long commands resumable and observable instead of trying to predict whether they should start. That helps with normal agent continuity, but it does not by itself solve mew's M6.24 failure class where the evaluator imposes a hard wall deadline and final acceptance requires artifact proof after the build.

## 4. Generic Concepts Mew Should Adopt

Adopt the lifecycle model, not the exact implementation:

- Treat long commands as durable managed process objects with ids, start time, last poll time, terminal state, exit code, and capped transcript.
- Return early with a run/session id and output snapshot instead of binding command lifetime to one model/tool wait.
- Poll managed commands explicitly and make empty polls first-class.
- Stream output into a capped transcript while also giving the model bounded snapshots.
- Preserve process state before yielding so interruption or continuation does not accidentally kill real work.
- Emit a single terminal event/record when the process exits; attach duration, exit code, and transcript evidence.
- Separate "command made progress" from "objective accepted." Final acceptance must require explicit artifact/test/proof evidence.
- Add a Codex-style completion audit before any success claim: map every requirement to concrete evidence and treat uncertainty as incomplete.

Mew also needs one layer Codex does not have: wall-budget admission for hard external deadlines. Before starting a heavy stage, the substrate should check whether remaining wall time can cover the stage plus a proof reserve. If not, it should block or force a cheaper strategy before spending the remaining wall on a doomed late build.

## 5. What Not To Copy

Do not copy Codex's no-admission long-command policy as-is. It is adequate for an interactive CLI where a background process can keep running and the user/model can resume. It is insufficient for M6.24-style benchmark runs with a hard outer wall and mandatory final proof.

Do not copy the classic shell default timeout behavior for heavy builds. A 10-second default timeout is useful for ordinary shell probes, but hard builds need managed lifecycle and explicit wall accounting.

Do not rely on model-selected `yield_time_ms` as the budget mechanism. Yield windows are responsiveness controls; they do not reserve enough time for build completion and proof.

Do not port Codex's PTY, remote exec-server, login-shell, or sandbox/approval stack wholesale unless mew independently needs those surfaces. The transferable pattern is the managed process contract, output discipline, and proof separation.

Do not let capped transcripts become acceptance proof. Output snapshots are evidence sources; M6.24 acceptance still needs structured artifact existence/provenance and a smoke/default command proof tied to the final artifact.

## 6. Proposed Minimal M6.24 Repair Direction

Add a generic heavy-command admission and proof-reserve guard around mew's existing managed long-command substrate.

Minimal behavior:

1. For every managed long command, persist `started_at`, `duration_seconds`, latest terminal state, and `wall_budget_after_seconds` computed from actual elapsed tool-call time, including terminal polls.
2. Classify long-command stages generically, for example source acquisition, dependency/toolchain setup, final artifact build, smoke/proof, and cleanup/closeout. Avoid CompCert-specific names in the substrate.
3. Before starting a heavy or non-idempotent stage, compute:
   - current wall budget remaining,
   - conservative minimum stage reserve,
   - required final proof reserve,
   - closeout/reporting reserve.
4. If remaining wall budget is less than `stage_reserve + proof_reserve + closeout_reserve`, reject the start with a structured blocker such as `insufficient_wall_budget_for_build_and_proof`. The model should then choose a cheaper/reuse/compatibility path or stop with a real blocker instead of beginning a late build.
5. If admitted, run through the managed command lifecycle: return run id early, poll until terminal, update actual remaining wall after each poll, and preserve transcript/head-tail evidence.
6. On terminal success, require a separate final artifact proof step before acceptance. Progress lines from the build are not enough.
7. Add focused regression coverage:
   - late heavy build is blocked before starting,
   - admitted heavy build preserves enough proof reserve,
   - terminal poll subtracts actual current tool-call elapsed time,
   - successful managed build without artifact proof is not accepted,
   - failed non-timeout acquisition/build is not retried as the same doomed command without a changed plan.

This keeps the M6.24 repair small: Codex confirms that resumable processes, streaming, polling, and proof separation are the right generic shape; mew's added requirement is an admission/proof-reserve layer because its wall budget is externally enforced.
