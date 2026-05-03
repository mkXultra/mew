# Claude Code build/test speed strategy review

Date: 2026-05-03

Reference tree: `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code`

## Bottom line

Claude Code does not appear to have a Terminal-Bench-specific trick for `build-cython-ext`. Its advantage is mostly orchestration: it separates "the command may keep running" from "the main agent must sit idle", makes long shell work observable through task IDs and output files, pushes independent read/search work into parallel safe lanes, and uses prompt/planning pressure to avoid sleep/poll/full-rerun loops.

For mew M6.24, the highest leverage change is to treat builds/tests as background tasks with a small foreground blocking budget, while the main agent keeps inspecting source, narrowing the repro, and preparing the next action. This directly targets the ~29m timeout pattern: the system should not spend most of the budget passively waiting on one foreground build.

## Relevant Claude Code paths

### Bash and terminal lifecycle

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:54`: progress UI starts after 2s.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:57`: assistant-mode blocking budget is 15s.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:227`: Bash schema exposes `timeout`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:241`: Bash schema exposes `run_in_background`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:265`: common background command classes include `make`, `pytest`, `build`, `test`, `cargo`, `docker`, etc.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:322`: detects leading `sleep N`; `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:524` blocks long foreground sleeps when the Monitor feature is active.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:420`: Bash is strict and capped at 30k inline result chars.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:434`: Bash is concurrency-safe only when read-only.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:606`: background task results include task ID and output path; auto-background text explicitly says the command exceeded the 15s blocking budget.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:860`: foreground command timeout defaults through `getDefaultTimeoutMs()`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:973`: assistant-mode auto-background after 15s keeps the command running.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:989`: explicit `run_in_background` returns immediately.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1003`: first 2s are foreground; after that, the command can be registered and backgrounded.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1027`: progress is driven by polling command output.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/BashTool/BashTool.tsx:1127`: progress events include tail output, elapsed time, total lines/bytes, task ID, and timeout.

### Timeout semantics and process IO

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/timeouts.ts:2`: default Bash timeout is 120s.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/timeouts.ts:3`: max Bash timeout is 600s unless env overrides.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:106`: Bash stdout/stderr go directly to a file fd; progress comes from polling the file tail.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:135`: on timeout, a command is backgrounded if auto-background is enabled; otherwise it is killed.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:186`: user interrupt does not necessarily kill the shell; caller can background so partial output remains available.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:269`: waits on child `exit`, not `close`, so grandchildren holding FDs do not keep the tool blocked.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:297`: command results are reconstructed from `TaskOutput`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:337`: kill uses process-tree kill.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/ShellCommand.ts:349`: backgrounding clears foreground timeout/listeners and starts output size protection.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:22`: background task summaries use a stable prefix for UI/message collapse.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:24`: stall watchdog checks every 5s, with a 45s threshold.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:28`: prompt-like tails are detected so the agent is notified only when a command likely needs input, not merely because a build is slow.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:105`: shell completion notifications are queued as task notifications with output paths.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:180`: background shell task registration transitions the process into a task and attaches completion handling.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:390`: `backgroundAll` can background all foreground bash and agent tasks.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/LocalShellTask.tsx:420`: auto-backgrounded foreground tasks are flipped in place to avoid duplicate task events and leaked cleanup.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tasks/LocalShellTask/killShellTasks.ts:48`: running bash tasks spawned by an agent are killed when that agent exits.

### Tool execution and parallelism

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:8`: max tool concurrency defaults to 10.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:19`: tool execution partitions into concurrent-safe batches and serial unsafe calls.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/toolOrchestration.ts:86`: safety is conservative; parse failures or thrown safety checks become serial.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:34`: tools can begin executing while the assistant response is still streaming.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:45`: sibling Bash commands get a child abort controller so one Bash error can kill dependent siblings without aborting the whole query.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:129`: concurrency-safe tools run in parallel when all executing tools are also safe.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:320`: each tool call runs with a per-tool abort controller.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:354`: only Bash errors cancel sibling tools.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/tools/StreamingToolExecutor.ts:417`: progress messages are yielded immediately, even while ordered final results are buffered.

### Query recovery and budget semantics

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:181`: query params include `taskBudget`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:193`: `taskBudget` is API-side task budget, distinct from auto-continue token budget.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:508`: after compaction, remaining task budget is adjusted by pre-compact context.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:561`: streaming tool executor is created per query loop.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:699`: `taskBudget` total/remaining is passed to the model call.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:1185`: max-output-token failures are withheld and recovered rather than surfaced prematurely.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:1223`: recovery continues up to a fixed limit with a "break remaining work into smaller pieces" meta prompt.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/query.ts:1308`: token budget auto-continuation exists, with diminishing-return stop logic.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/api/claude.ts:479`: `configureTaskBudgetParams` adds `output_config.task_budget` when eligible.

### Planning, verification, and subagents

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/prompts.ts:269`: tool prompt tells the agent to break down/manage work with task/todo tools.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/prompts.ts:310`: independent tool calls should be parallelized.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/TodoWriteTool/TodoWriteTool.ts:72`: when a 3+ item list closes with no verification task, the tool can nudge for independent verification.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/TaskUpdateTool/TaskUpdateTool.ts:326`: the same structural verification nudge exists for V2 tasks.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:24`: Explore is read-only by design.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:52`: Explore is explicitly told to return quickly and use parallel searches/reads.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/exploreAgent.ts:59`: Explore has a threshold constant of 3 queries for when broad exploration is worth it.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/prompts.ts:378`: simple directed searches should use direct search tools; broader research should use Explore only when needed.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:10`: verification agent is adversarial, not rubber-stamp.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:42`: verification must read project build/test conventions.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:81`: verifier output requires command evidence and PASS/FAIL/PARTIAL verdict.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/built-in/verificationAgent.ts:134`: verifier is built-in, background, inherit-model, and disallows edit/write tools.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/forkSubagent.ts:18`: fork subagent feature inherits parent context and system prompt.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/forkSubagent.ts:96`: forked messages preserve byte-identical prompt prefixes for cache sharing.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/AgentTool.tsx:555`: fork mode forces all spawns async.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/tools/AgentTool/AgentTool.tsx:686`: async agents are registered and the parent gets an immediate `async_launched` result.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/coordinator/coordinatorMode.ts:200`: coordinator workflow separates research, synthesis, implementation, and verification.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/coordinator/coordinatorMode.ts:213`: coordinator prompt calls parallelism the core performance lever.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/coordinator/coordinatorMode.ts:280`: coordinator chooses continue vs. fresh worker based on context overlap.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/coordinator/coordinatorMode.ts:289`: verification of another worker's code should spawn fresh.

### Prompt/cache design

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/context.ts:36`: git status is memoized.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/context.ts:61`: git branch/default/status/log/user are fetched in parallel.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/context.ts:113`: system context is memoized for the conversation.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:16`: prompt sections are cached until `/clear` or `/compact`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/systemPromptSections.ts:27`: volatile prompt sections are explicit and marked dangerous.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/prompts.ts:105`: system prompt has a dynamic boundary marker for global cacheability.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/constants/prompts.ts:491`: dynamic prompt sections are registry-managed and mostly memoized.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/api/claude.ts:1235`: tool schemas are rendered in parallel with `Promise.all`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/api/claude.ts:1327`: deferred tool names can be carried as delta attachments instead of per-request prompt prepends.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/utils/api.ts:296`: `splitSysPromptPrefix` defines cache strategies for global vs. org vs. uncached blocks.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/claude-code/src/services/api/claude.ts:3213`: system prompt blocks are built through `splitSysPromptPrefix` with cache controls.

## Mechanisms mew should consider borrowing

1. **Separate blocking budget from command lifetime.** A build command may legitimately run for 10-20m, but the main model should not be blocked more than ~10-15s. Claude Code has both command timeout and foreground blocking budget; mew should adopt this as a first-class contract.

2. **Make long commands task objects, not raw terminal waits.** Each long command should have a task ID, output file, progress tail, total bytes/lines, status, owner agent, and completion notification. The model can resume from structured status instead of re-running or polling.

3. **Default likely builds/tests to background.** `pip install`, `python setup.py build_ext`, `python -m build`, `pytest`, `make`, `cargo test`, `npm test`, and similar commands should run with an immediate background path unless their result is needed in the next few seconds.

4. **Continue useful work while builds run.** After launching a build/test, the main agent should inspect source, setup metadata, failing logs, package config, and likely Cython extension points. This is the main time-to-pass lever for `build-cython-ext`.

5. **Use progress for decision points, not polling.** Progress tails should trigger only meaningful decisions: failed fast, interactive prompt, no-output-suspicion, or completion. Avoid sleep loops and repeated `tail`/`ps` checks by the model.

6. **Run independent read/search operations in parallel.** Claude Code allows read-only Bash and dedicated search/read tools to run concurrently and starts safe tools as they stream in. Mew should aggressively parallelize repo inspection while the build runs.

7. **Kill wasted sibling work on Bash failure.** If a Bash step fails in a parallel block, dependent sibling Bash commands should abort quickly. This avoids continuing a full test after setup/build already failed.

8. **Persist huge output to disk with previews.** Large compiler/test logs should not flood model context. Return a preview plus path and metadata; let the agent inspect targeted log slices.

9. **Add structured task pressure.** A short task list should force "minimal repro", "root-cause inspect", "targeted fix", "targeted verify", "final verify". Completion without a verify item should trigger a nudge.

10. **Use subagents selectively.** Use read-only Explore for broad, parallel discovery; use fresh verifier only after a plausible fix or when confidence is uncertain. Do not spawn a verifier before the first candidate fix on Terminal-Bench if it increases wall-clock time without reducing rework.

11. **Cache stable prompt/context pieces.** Static prompt, tool schema bases, git snapshot, and environment sections should be stable across turns. Dynamic tool lists or MCP/plugin state should move into delta attachments or equivalent side channels.

## What Claude Code does not appear to do

- It does not appear to have Terminal-Bench- or `build-cython-ext`-specific build heuristics.
- It does not appear to automatically choose Cython-specific commands, patch strategies, ccache, wheel cache, or incremental build reuse.
- It does not appear to automatically decide that a slow-but-healthy build should be killed and replaced with a narrower command. It provides progress/background/stall primitives and relies on the agent strategy.
- Its default Bash timeout is only 2m, max 10m. Long builds require explicit timeout/background semantics or assistant-mode auto-background; otherwise a legitimate long command can still be killed.
- The 15s auto-background path is gated to assistant/Kairos-style mode. It is not universally active in all modes.
- The stall watchdog intentionally ignores ordinary slow builds unless the output tail looks like an interactive prompt.
- Verification can add latency. Claude Code's independent verifier is quality-oriented, not a time-to-pass optimizer by itself.
- It does not provide a global DAG optimizer for build/test plans. The concurrency is tool-level and agent-level, guided by prompts and safety flags.

## M6.24 recommendations for mew

### P0: Long-command lifecycle for Terminal-Bench

- Add `run_in_background` and `blocking_budget_ms` to the terminal tool. Default `blocking_budget_ms` to 10-15s for interactive agent mode.
- Keep command timeout separate. For known Terminal-Bench build/test commands, use a timeout that can actually pass the benchmark, but auto-background after the blocking budget.
- Return `{task_id, output_path, status, elapsed_ms, tail, total_bytes, total_lines}` on backgrounding.
- Emit completion/failure notifications into the agent loop. The agent should not sleep or poll for completion.
- Write stdout/stderr directly to disk or a bounded spool, with context-safe previews.

Expected impact: removes passive foreground waiting and lets source investigation overlap with the slow build, the most direct path from ~29m timeout toward ~15m pass.

### P0: Build/test strategy policy

- Classify commands such as `pip install`, `build_ext`, `pytest`, `make`, `cargo test`, `npm test`, `docker build` as long-running unless proven otherwise.
- On first encounter, run the cheapest discriminating check before the full build when available: inspect `pyproject.toml`, `setup.py`, `setup.cfg`, `tox.ini`, `Makefile`, extension sources, and test entrypoints.
- Prefer targeted reproduction after a failure. Do not run the full suite repeatedly after every edit.
- Enforce a "time-to-first-signal" rule: after 45-60s with no output, inspect the task tail and classify as healthy compile silence, interactive prompt, network stall, or deadlock. Only kill on evidence.

### P1: Structured work loop

- Auto-create a task list for coding benchmarks:
  1. map build/test commands
  2. start/observe long build in background
  3. inspect likely root cause while build runs
  4. patch minimal root cause
  5. targeted verify
  6. final benchmark command
- Block or nudge final answer if no verification task completed.
- Record command attempts with status and elapsed time so the agent sees "full build already cost 8m and failed at X" instead of re-running blindly.

### P1: Parallel read/search and streaming execution

- Mark read-only terminal commands as concurrency-safe.
- Run multiple independent `rg`, file reads, config reads, and log slices in parallel.
- If the model streams several safe tools, start them before the whole assistant message finishes.
- Abort sibling Bash commands when an earlier Bash dependency fails.

### P1: Recovery from long-running commands

- Add foreground-to-background conversion for user interrupt and for automatic blocking-budget expiry.
- Add process-tree kill and agent-scoped cleanup so subagent-created background commands cannot survive their owner.
- Add interactive prompt detection on stalled output tails and notify with the last output plus suggested noninteractive rerun.
- Cap output file size and kill runaway background output producers.

### P2: Subagent/explore/verifier separation

- Add a fast read-only explorer for broad codebase discovery, with no write tools and strict "return quickly" instructions.
- For Terminal-Bench, use verifier after the candidate fix or when there is a high-risk uncertainty. Do not let verifier orchestration delay the first pass attempt.
- If mew adds forks, keep fork children async and avoid reading their full transcripts mid-flight; use completion summaries and output paths.

### P2: Prompt/cache latency hygiene

- Split static prompt from dynamic session context with an explicit boundary.
- Cache system prompt sections and tool schema bases for the session.
- Memoize git/environment context; compute independent context pieces in parallel.
- Move volatile tool/plugin/MCP listings to delta attachments or structured side channels to avoid busting prompt cache.

## Benchmark-specific target behavior for `build-cython-ext`

The desired mew loop should look like this:

1. Start the likely full build/test command in background with a realistic timeout.
2. Immediately inspect packaging and extension source in parallel.
3. If the background command fails, consume the relevant tail/path and patch from the failure.
4. Run the narrowest compile/test command that validates the patch.
5. Run the final Terminal-Bench command once confidence is high.

The key difference from the ~29m timeout behavior is not "run fewer tests" in the abstract. It is: never let the main agent spend the benchmark budget waiting idly for a command that can be observed as a background task while reasoning and source inspection continue.
