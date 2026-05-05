# Review 2026-05-03: Codex Build-Cython Speed Strategy

Scope: Codex CLI source in
`/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex`, reviewed as a
reference for why Codex can finish Terminal-Bench `build-cython-ext` in roughly
10-20 minutes while mew can spend about 29 minutes and still time out.

No Codex source was modified.

## Bottom Line

Codex does not appear to have a Terminal-Bench or Cython-specific solver. The
speed advantage visible in source is a generic software-engineering execution
substrate:

- commands are typed tool calls with cwd, timeout/yield, output caps, process
  identity, and terminal status;
- long commands can yield while still running, then be polled by id instead of
  being killed or lost;
- shell output is continuously drained, bounded, and streamed so builds do not
  block on pipes or flood model context;
- mutating tools are serialized while safe inspection commands can run in
  parallel;
- patches are a first-class grammar-backed tool, not fragile shell heredocs;
- the base prompt biases the model toward specific validation first, broader
  validation only after confidence, and autonomous completion.

For mew M6.24, the highest-leverage change is not another task detector. It is a
small managed command lifecycle plus a strategy contract that prevents the model
from burning the final wall budget on repeated broad verification or same-shape
timeouts.

## Relevant Codex Code Paths

### Model instructions and validation strategy

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:123`
  tells the agent to keep going until the query is resolved and not guess.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:149`
  starts the validation section; lines 151-155 explicitly say to test from
  specific to broader and iterate formatting/test fixes up to 3 times.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/protocol/src/prompts/base_instructions/default.md:159`
  says non-interactive modes should proactively run tests/lint.

Effect: Codex gives the model a simple default loop: inspect, patch, run the
smallest meaningful verification, then broaden. It does not ask the model to
prove many stale blocker classes before acting.

### Tool exposure and command schema

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:19`
  defines `exec_command` with `cmd`, `workdir`, optional shell/login/tty,
  `yield_time_ms`, `max_output_tokens`, and sandbox permission fields.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:92`
  defines `write_stdin`, where empty input is a poll against an existing
  session.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/local_tool.rs:299`
  defines the model-visible unified exec output schema: `chunk_id`,
  `wall_time_seconds`, `exit_code`, `session_id`, `original_token_count`, and
  `output`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:156`
  exposes unified `exec_command` and `write_stdin`; `exec_command` supports
  parallel tool calls while `write_stdin` does not.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/tool_registry_plan.rs:322`
  exposes `apply_patch` as a non-parallel mutating tool.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/tool_config.rs:170`
  selects unified exec when the feature and environment allow it, otherwise
  falls back to shell command modes.

Effect: the model sees command lifecycle state directly. A running build is not
just a wall-clock wait or a clipped shell string; it is a resumable session id.

### Unified exec long-command lifecycle

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:45`
  defines `ExecCommandArgs`; lines 82-88 set default initial yield to 10s and
  default `write_stdin` yield to 250ms.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:209`
  handles `exec_command`: resolves cwd, parses shell command, applies granted
  permissions, computes max output tokens, and allocates a process id.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:307`
  intercepts accidental shell-level `apply_patch` and routes it through the
  verified patch handler.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs:382`
  handles `write_stdin` polling or input against an existing session.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/mod.rs:59`
  defines yield clamps: 250ms minimum, 30s maximum initial wait, 5s minimum empty
  poll, 300s default background poll cap, 10k default output tokens, 1 MiB
  retained output, and 64 max live processes.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:60`
  forces noninteractive command env (`NO_COLOR`, `TERM=dumb`, pagers to `cat`,
  `CODEX_CI=1`) to reduce noisy output and blocked pagers.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:231`
  starts a command, begins streaming output, stores the live process before the
  initial yield can be interrupted, and returns either terminal status or a live
  process id.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:408`
  polls/writes an existing process and returns new output plus either a
  still-running id or an exit code.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:595`
  stores live processes, warns near the process cap, prunes old entries, and
  starts an exit watcher.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/process_manager.rs:859`
  drains output until deadline, process exit, cancellation, or output closure,
  with a short post-exit trailing-output wait.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:37`
  continuously streams output deltas in the background.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/async_watcher.rs:104`
  emits one terminal end event after process exit and output drain.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs:4`
  preserves bounded head and tail output, dropping the middle after the cap.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/context.rs:446`
  formats the model response with wall time, exit code if finished, session id
  if still running, original token count, and truncated output.

Effect: a build that takes longer than the first yield is not a failure. The
model receives progress quickly, can make a next decision, and can later poll
the same command. This is the most direct reference pattern for mew's
long-command timeout problem.

### Classic shell fallback

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/exec.rs:51`
  sets the classic shell default timeout to 10s.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/exec.rs:149`
  defines `ExecExpiration` as explicit timeout, default timeout, or
  cancellation.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/exec.rs:1230`
  consumes child output; lines 1275-1284 kill the process group on timeout and
  record a synthetic timeout result.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/exec.rs:1295`
  caps stdout/stderr drain after timeout to avoid hanging on inherited pipes.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/exec.rs:1331`
  continuously drains output while retaining bounded buffers.

Effect: even the old path has hard timeout, process-group kill, and bounded
drain semantics. It is safe, but not the fast/long-build path to copy.

### Tool scheduling, follow-up, and retry semantics

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:935`
  builds prompts with `parallel_tool_calls` set from model capabilities.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:1002`
  retries retryable model-stream failures with provider-specific retry budget
  and optional WebSocket to HTTPS fallback.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:1846`
  tracks in-flight tool futures; lines 1961-1971 enqueue tool execution as
  output items arrive.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:2084`
  marks model follow-up when the response is not an end turn.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/session/turn.rs:2213`
  drains in-flight tool futures and records their outputs before returning.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/stream_events_utils.rs:199`
  records completed tool-call items immediately so history stays in sync even
  if a turn is later cancelled.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/parallel.rs:83`
  runs parallel-capable tools behind a read lock and non-parallel tools behind a
  write lock.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/registry.rs:357`
  centralizes pre-tool hooks; lines 372-393 wait on the mutating tool gate; lines
  422-482 run post-tool hooks and can replace/add context.

Effect: Codex reduces idle time by letting safe tool calls overlap while keeping
mutations ordered. The model's next step is based on recorded tool outputs, not
stale local assumptions.

### Sandbox/approval retry

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs:4`
  documents the approval/sandbox/retry sequence.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs:194`
  selects the first sandbox attempt.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs:240`
  handles sandbox denial; lines 257-283 refuse escalation when policy/tool does
  not allow it.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/orchestrator.rs:326`
  performs a second attempt without sandbox only after approval/retry policy
  permits it.

Effect: retry is targeted at sandbox denial. Codex does not blindly rerun failed
commands or repeat the same timeout shape.

### Patch/apply lifecycle

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/tools/src/apply_patch_tool.rs:87`
  exposes a grammar-backed freeform patch tool for GPT-5-class models.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:53`
  streams patch argument progress with a 500ms buffer.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:309`
  marks patching as mutating and therefore serialized.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:341`
  verifies and applies the patch through the dedicated runtime.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/handlers/apply_patch.rs:468`
  intercepts shell-invoked `apply_patch`, warns the model, and routes it through
  the same verified handler.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/core/src/tools/runtimes/apply_patch.rs:207`
  applies verified patches under sandbox context and returns terminal output.

Effect: file edits are quick, structured, and low-friction. This saves model
rounds compared with shell-driven patch creation, validation, and cleanup.

### Headless CLI lifecycle and resume

- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:272`
  maps `--full-auto` to workspace-write and dangerous bypass to full access.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:387`
  sets headless default approval policy to `Never`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:661`
  starts or resumes a thread through app-server APIs.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:710`
  avoids waiting up to 10s for a later streamed `SessionConfigured` event by
  trusting the start/resume response.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:730`
  sends Ctrl-C as `turn/interrupt`.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:803`
  runs until turn completion and exits nonzero for non-retrying errors/failures.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/lib.rs:1122`
  backfills final turn items with `thread/read` if streaming dropped item
  notifications.
- `/Users/mk/dev/personal-pj/mew/references/fresh-cli/codex/codex-rs/exec/src/cli.rs:139`
  exposes `resume`; lines 148-177 support last-session resume plus prompt/images.

Effect: Codex has low startup overhead, durable history, clean interrupt
semantics, and final-output recovery. These are not the whole 10-20 minute
difference, but they prevent time loss and evidence loss around long runs.

## Mechanisms Mew Should Consider

### P0 for M6.24

1. Add one managed live-command lifecycle:
   `start -> yielded/running -> poll -> finalized`, with command id, cwd, argv or
   shell string, wall time, output owner, timeout/yield fields, exit code, and
   terminal status. A running snapshot must never satisfy acceptance. Codex
   reference: unified exec process id plus `write_stdin` polling.

2. Make long-command output bounded and durable:
   keep model-visible head/tail snippets plus a durable full-output artifact ref
   for acceptance. Codex's `HeadTailBuffer` is enough for chat continuity; mew
   likely needs stricter artifact proof retention.

3. Separate process lifecycle from task proof:
   command status should be generic (`running`, `exited`, `timed_out`, `killed`),
   while proof role should come from typed execution contract (`source proof`,
   `build`, `final artifact`, `smoke`). Avoid inferring proof role from shell
   string shape as the primary mechanism.

4. Put a strategy budget in the prompt/tool contract:
   start with targeted inspection and a narrow repro/build command, only run the
   final broad verifier after source/toolchain and patch are coherent, reserve
   final proof budget, and prohibit repeating the same timed-out command with
   the same budget.

5. Make mutating actions explicit and serialized:
   patches, file writes, dependency installs, and cleanup should pass through a
   mutation gate. Safe reads/searches can run in parallel to reduce idle model
   time.

6. Use a first-class patch path:
   do not make model-created shell heredocs the normal edit path. A grammar or
   structured patch operation cuts down edit retries and makes post-patch diff
   evidence cheap.

### P1 after the lifecycle lands

7. Add targeted retry semantics only:
   retry sandbox/permission denials with a different policy if allowed; retry
   transport/model stream failures; do not blindly retry build failures or
   timeouts.

8. Normalize command environment:
   disable color/pagers, mark CI/noninteractive mode, set deterministic locale,
   and drain stdout/stderr continuously. This reduces large noisy logs and pager
   stalls.

9. Backfill final events before closeout:
   if the UI/event stream misses an item under pressure, force one durable read
   before producing the final work report. Mew's acceptance should use terminal
   command evidence, not a stale transcript fragment.

10. Keep prompt rules compact:
    Codex's useful prompts are broad but simple: complete the task, do not guess,
    edit with patch, test specific first, broaden after confidence. Mew should
    avoid growing a benchmark-specific instruction stack that consumes the same
    context needed for diagnosis.

## What Codex Does Not Appear To Do

- No Terminal-Bench-specific or `build-cython-ext`-specific solver is visible in
  these paths.
- No automatic Cython/build-system optimizer is visible outside normal model
  reasoning and shell tools.
- No global CLI wall budget comparable to mew's work-session timeout appears in
  the inspected command loop. Codex has per-command timeout/yield semantics and
  keeps the turn running until completion or interruption.
- No automatic failed-test repair loop is implemented in controller code. The
  model decides what to patch and rerun; the prompt only encourages validation.
- No blind shell-command retry loop appears. Retries are mainly model transport
  retries and sandbox-denial escalation.
- No running command snapshot is treated as proof of success; terminal exit
  status/end event is the proof boundary.
- No full-output persistence guarantee for acceptance is apparent. Codex bounds
  output for model/history health, which is fine for chat but not enough by
  itself for mew verifier proof.
- No parallel mutating edits are allowed by default; parallelism is for safe
  inspection/tool calls.
- No primary reliance on shell-string classifiers for source/build/smoke stages
  is visible in the command substrate.

## Why This Likely Beats Mew On `build-cython-ext`

Codex's likely advantage is not that it waits less for the final build. It is
that it spends fewer wasted cycles before the final build and does not lose the
build once it starts.

The important efficiency differences are:

- fast command feedback: initial unified exec yield is 10s by default, so the
  model gets early build output or a process id instead of blocking silently;
- no evidence loss on long commands: a running command can be polled and later
  finalized rather than converting into `wall_timeout`;
- low-context logs: output caps and head/tail retention prevent build logs from
  consuming the reasoning budget;
- fewer edit retries: grammar-backed `apply_patch` and patch interception avoid
  shell quoting/heredoc failure loops;
- targeted validation: the prompt pushes specific tests first, which is exactly
  what a Cython-extension task needs before a full benchmark/verifier rerun;
- ordered mutations plus parallel reads: the model can inspect quickly without
  racing its own edits;
- no stale blocker ladder: follow-up prompts are built from recorded tool
  outputs, not from older failure labels that still dominate after new evidence.

For M6.24, the practical target is therefore:

```text
time_to_first_relevant_failure < 2 min
time_to_patch_after_relevant_failure < 5 min
final_build_or_test started with enough remaining budget
long command yielded/polled/finalized instead of killed by work-session timeout
acceptance reads terminal evidence only
```

## Recommended M6.24 Priorities

1. Ship managed long-command continuation first.
   Implement the smallest Codex-like lifecycle: one active process, bounded
   output, poll by id, terminal finalization, and acceptance rejection for
   running snapshots. This directly attacks the 29m timeout shape.

2. Add typed execution contracts to the model action schema.
   Let the model say `purpose=source_probe|build|unit_test|final_verify`,
   `expected_artifact`, `yield_after_seconds`, `timeout_seconds`, and
   `budget_class`. Reducers should consume these fields before shell text.

3. Protect final proof budget.
   Before starting a long build or broad verifier, require enough remaining wall
   time for a meaningful run plus final evidence write. If not, block or poll an
   existing command instead of starting a doomed one.

4. Add "same timeout, same command" suppression.
   If a command timed out, a retry needs a materially different timeout/budget,
   command shape, or recovered active process id. Otherwise the controller
   should force diagnosis or budget block.

5. Make patch application structured.
   A mew patch tool does not need all Codex UI streaming, but it should parse,
   apply, summarize changed files, and provide post-patch diff evidence without
   shell quoting.

6. Allow parallel safe inspection.
   Reads, `rg`, file stats, and metadata queries should be schedulable in
   parallel; writes/builds/tests remain serialized. This improves
   time-to-diagnosis without complicating proof semantics.

7. Normalize and cap command output.
   Use noninteractive env defaults, drain stdout/stderr continuously, store
   bounded prompt snippets, and preserve full verifier-relevant logs separately.

8. Simplify the strategy prompt around efficient SWE.
   Keep the core behavior short: inspect targeted files, make the minimal patch,
   run the narrowest relevant test/build, poll long commands, then run final
   proof. Avoid adding task-specific prompt branches for Cython unless the typed
   contract has already failed.

## M6.24 Acceptance Implication

For `build-cython-ext`, mew should consider the run successful only when a
terminal command record proves the extension builds/tests successfully and the
required artifact exists. But it should not require that the build command fit
inside one blocking tool call. Codex's source shows the key distinction:
nonterminal progress is useful for strategy, while terminal command evidence is
the acceptance boundary.
