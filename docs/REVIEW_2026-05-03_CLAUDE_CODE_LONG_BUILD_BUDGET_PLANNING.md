# Claude Code Long Build Budget Planning Review - 2026-05-03

## Scope

Reference inspected: `references/fresh-cli/claude-code`.

Orientation docs used:

- `docs/ADOPT_FROM_REFERENCES.md:218-228`
- `docs/M6_24_COMPOUND_LONG_COMMAND_BUDGET_REPAIR_2026-05-03.md:14-39`
- `docs/M6_24_FINAL_CLOSEOUT_PROJECTION_SPEED_RERUN_2026-05-03.md:120-152`

Question: whether Claude Code has a long-build wall-budget planner that would prevent the current M6.24 failure shape, where real build progress starts too late and the session exhausts before final artifact proof.

## Bottom Line

Claude Code does not appear to solve this with explicit heavy-build admission control. It solves a different problem: keep long shell commands observable, backgroundable, continuable, killable, and separable from final proof. It has per-command timeouts, default/max bash timeout settings, auto-backgrounding for responsiveness, task output files, output tail polling, and verification-agent discipline. I did not find logic that estimates whether a build plus final proof can fit a remaining hard work-session wall budget before starting the build.

For M6.24, copy the generic concepts around command lifecycle and evidence separation, but add a mew-specific admission gate before starting a managed build/dependency/final-artifact command. If the current wall budget cannot cover a minimum useful long-command slice plus final proof reserve, mew should yield with structured nonterminal evidence instead of starting the build late and consuming the proof window.

## Relevant Claude Code Source

- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:227-295`: Bash input/output schema. The model can set `timeout` and `run_in_background`; output can include `backgroundTaskId`, `assistantAutoBackgrounded`, and persisted output metadata.
- `references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:826-1143`: `runShellCommand()` async generator. It spawns the shell command, streams progress, backgrounds explicitly or automatically, yields progress with `taskId`, and returns terminal `ExecResult`.
- `references/fresh-cli/claude-code/src/utils/timeouts.ts:1-38`: bash timeout defaults: 2 minutes default, 10 minutes max, env-overridable.
- `references/fresh-cli/claude-code/src/utils/Shell.ts:181-195`, `:281-345`, `:385-421`: `exec()` constructs the process, routes bash stdout/stderr to a task output file in normal mode, wraps the child as `ShellCommand`, and only updates cwd for foreground non-backgrounded commands.
- `references/fresh-cli/claude-code/src/utils/ShellCommand.ts:32-47`, `:135-140`, `:186-192`, `:269-315`, `:337-366`: process interface, timeout handling, interrupt behavior, terminal result assembly, kill, and background transition.
- `references/fresh-cli/claude-code/src/utils/task/TaskOutput.ts:21-31`, `:50-90`, `:109-157`: `TaskOutput` is the output owner; bash output goes to a file and progress is extracted by polling the file tail.
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:24-104`, `:180-245`, `:259-368`: background task lifecycle, stall watchdog, foreground task registration, backgrounding, final status notification.
- `references/fresh-cli/claude-code/src/tools/TaskOutputTool/TaskOutputTool.tsx:30-34`, `:59-74`, `:172-181`, `:219-281`: task output continuation API. It can block or poll, but the prompt says the preferred continuation path is reading the task output file directly.
- `references/fresh-cli/claude-code/src/tasks/LocalShellTask/killShellTasks.ts:16-75` and `references/fresh-cli/claude-code/src/tools/TaskStopTool/TaskStopTool.ts:107-129`: kill/stop paths for background shell tasks.
- `references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:34-151`, `:407-490` and `references/fresh-cli/claude-code/src/query.ts:837-862`, `:1011-1051`: tools can start as streamed tool_use blocks arrive; progress and completed results are emitted while streaming continues, with synthetic tool results on abort.
- `references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:10-62`, `:81-152`: separate verification agent is read-only in the project and requires command/output evidence plus a final `VERDICT`.

## Long Commands, Streaming, And Lifecycle

Claude Code's Bash tool is an async generator over a `ShellCommand`. It launches with a per-command timeout, records output through `TaskOutput`, waits briefly before showing progress, then races terminal completion against output-progress wakeups (`BashTool.tsx:826-1143`). Progress carries recent output, line/byte counts, elapsed time, task id, and optional timeout.

Normal bash output bypasses JS streams: stdout and stderr are both attached to one output file descriptor (`Shell.ts:281-345`). `TaskOutput` owns that file and a shared poller tails it every second for progress (`TaskOutput.ts:21-31`, `:81-90`, `:109-157`). This is important: the transcript is not the source of truth for long-command output.

Continuation is task/file based. A foreground command can be registered as a task and backgrounded in place (`LocalShellTask.tsx:259-368`). An explicitly backgrounded Bash call returns a `backgroundTaskId` immediately (`BashTool.tsx:985-1000`). The TaskOutput tool can read/poll task output, but its prompt says to prefer reading the task output file path directly (`TaskOutputTool.tsx:172-181`).

Timeout does not always mean kill. `ShellCommandImpl.#handleTimeout()` backgrounds if auto-backgrounding is enabled; otherwise it kills (`ShellCommand.ts:135-140`). In assistant mode, a 15 second blocking budget auto-backgrounds long blocking commands to keep the agent responsive (`BashTool.tsx:973-982`). This is a responsiveness budget, not an acceptance budget.

Lifecycle is explicit. A shell command has `running`, `backgrounded`, `completed`, and `killed` states (`ShellCommand.ts:32-47`). Terminal results are assembled only on process exit (`ShellCommand.ts:291-315`). Background tasks update final status and enqueue notifications when their `ShellCommand.result` resolves (`LocalShellTask.tsx:222-244`, `:331-366`). Stop/kill paths clean state and evict output (`killShellTasks.ts:16-75`).

Claude Code also distinguishes slow from stuck. Its background stall watchdog only notifies if output stops and the tail looks like an interactive prompt; it intentionally stays silent on merely slow commands and long builds (`LocalShellTask.tsx:24-104`).

## Budget Planning / Admission Control

Found budget-like mechanisms:

- Bash default/max timeout: 2 minutes default, 10 minutes max, env-overridable (`timeouts.ts:1-38`).
- Per-call `timeout` in the Bash schema (`BashTool.tsx:227-242`).
- Assistant blocking budget before auto-backgrounding (`BashTool.tsx:973-982`).
- Output size guard for background tasks: watchdog kills runaway output (`ShellCommand.ts:52-55`, `:239-260`).
- TaskOutput polling/blocking timeout for reading task state (`TaskOutputTool.tsx:30-34`, `:117-143`).

Not found: explicit admission control that says "do not start this heavy build unless remaining wall budget is enough for the build slice plus final artifact proof." Claude Code's design lets a long command continue beyond the current foreground wait by backgrounding it and preserving an output/task handle. That avoids losing progress, but it does not by itself prove an artifact before an external wall deadline.

This differs from mew's M6.24 failure. The documented failure says step 8 requested `timeout=2400`, was capped to about `899.53`, had no `long_command_budget`, and left `/tmp/CompCert/ccomp` missing (`docs/M6_24_COMPOUND_LONG_COMMAND_BUDGET_REPAIR_2026-05-03.md:14-24`). A later rerun hit a related terminal budget issue: stale optimistic remaining budget caused the next model turn to run with about 32 seconds left and timeout (`docs/M6_24_FINAL_CLOSEOUT_PROJECTION_SPEED_RERUN_2026-05-03.md:132-152`).

## Acceptance / Proof Separation

Claude Code separates progress from proof operationally:

- Progress events are yielded while the process is still running (`BashTool.tsx:1127-1138`).
- Terminal command evidence is only available after exit/result assembly (`ShellCommand.ts:291-315`).
- Background task completion is a later notification, not the initial backgrounded Bash result (`LocalShellTask.tsx:222-244`).
- Verification is delegated to a read-only verifier with a required command/output evidence format and final `VERDICT` (`verificationAgent.ts:10-62`, `:81-152`).

This is mostly prompt/agent/tool discipline rather than a deterministic acceptance reducer. For mew, the useful generic rule is stronger: progress output, package installation output, configure output, or partial make output must not satisfy acceptance while the required final artifact is missing or unproven.

## Concepts Mew Should Adopt Generically

1. Persistent command identity from launch. A long command should have a stable run id, stage, command, cwd, process id/group id, output ref, status, and running vs terminal evidence refs from the first slice.

2. Output file as source of truth. Stream/tail output for UX and planning, but keep a durable output ref independent of the model transcript. Progress summaries should be disposable; terminal evidence should point at the persisted output.

3. Nonterminal continuation state. Running/yielded long commands should force the next allowed action to poll/read/continue that command, not reacquire source, clean rebuild, or mark success.

4. Terminal proof gate. A successful build command is not final acceptance unless the required artifact proof or smoke proof also ran and is fresh. Keep final proof as a separate evidence kind.

5. Lifecycle controls. Keep explicit stop/kill/orphan handling, process-group cleanup, output caps, and prompt-like stall detection. Long silence should not automatically mean failure if no interactive prompt is detected.

6. Streaming dispatch where useful. `docs/ADOPT_FROM_REFERENCES.md:218-228` correctly identifies Claude Code's streaming tool executor as a major responsiveness pattern. It reduces idle time before starting tools, but it is not a substitute for wall-budget admission.

## What Not To Copy

- Do not copy Claude Code's background task UI, XML notifications, SDK attachment behavior, or Ant/KAIROS feature gates wholesale.
- Do not treat auto-backgrounding as the acceptance solution. It preserves process progress, but it does not reserve time for final proof under a hard wall budget.
- Do not copy the exact 2 minute / 10 minute bash timeout defaults or the 15 second assistant blocking budget. Those are product/runtime choices, not long-build correctness rules.
- Do not replace mew's deterministic acceptance reducer with a verifier-agent prompt. The verifier-agent pattern is useful as defense in depth, but M6.24 needs structured state and budget accounting.
- Do not make the repair CompCert-specific. Command classification should use generic execution-contract stage, build/dependency/final-artifact semantics, idempotence identity, and required artifact proof.

## Minimal M6.24 Repair Direction

mew already has most of the substrate:

- `src/mew/commands.py:6446-6613`: `work_tool_long_command_budget_policy()`
- `src/mew/commands.py:6683-6848`: `apply_work_tool_wall_timeout_ceiling()`
- `src/mew/work_session.py:2267-2319`: managed command start/poll wrapper
- `src/mew/toolbox.py:644-750`: `ManagedCommandRunner`
- `src/mew/long_build_substrate.py:889-968`: `build_long_command_run()`
- `src/mew/long_build_substrate.py:1069-1211`: `reduce_long_build_state()`
- `src/mew/long_build_substrate.py:1727-1898`: long-command poll/resume recovery decisions

The missing repair is earlier admission for heavy managed commands, not another CompCert recipe:

1. Recompute current wall remaining immediately before dispatch in `apply_work_tool_wall_timeout_ceiling()`. Do not rely on stale long-command state or start-of-poll budget.

2. For any planned command whose execution contract or planned budget stage is build, dependency generation/install, runtime build/install, final artifact proof, or default smoke, require:
   `current_remaining >= stage_minimum_seconds + final_proof_reserve_seconds + tool_timeout_guard`.

3. If that condition fails, do not start the command. Return a blocked/yielded long-command result with `stop_reason=long_command_budget_blocked`, stage, idempotence key, required artifact targets, remaining seconds, minimum seconds, and output/evidence refs sufficient for the next session to resume.

4. If the command starts, cap its effective timeout to preserve final proof reserve. After terminal success, schedule/run the final artifact proof from that reserve before finish. Do not spend the reserve on another build slice unless the recovery policy explicitly allows it for a narrow last-mile proof/install case.

5. On timeout, kill, interrupt, or yield, record terminal/nonterminal long-command evidence and keep the reducer in `in_progress` or `blocked`, never accepted, until terminal success plus artifact proof exists.

6. Add a regression for the M6.24 shape without naming CompCert as the rule: source/configure are already done, the next command is a shortest final-target build/smoke compound command, and remaining wall budget is below build minimum plus proof reserve. Expected result: mew refuses to start and emits a continuation/budget-blocked state. With enough budget, the managed command starts with `long_command_budget`, durable output ref, and terminal success still requires separate artifact proof.
