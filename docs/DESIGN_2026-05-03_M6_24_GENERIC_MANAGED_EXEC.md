# Design 2026-05-03 - M6.24 Generic Managed Execution

Status: accepted design; implementation slice 1 landed on 2026-05-03.

Implementation note:

- `run_command` and `run_tests` now default to managed execution in work mode.
- `poll_command`, `cancel_command`, and `read_command_output` are exposed as
  work tools.
- Command output is spooled to `.mew/work-session/.../output.log`.
- Nonterminal managed results remain non-acceptance evidence; polling a yielded
  command finalizes the corresponding `CommandRun` and terminal evidence.
- The runtime still uses an in-process bounded registry. Durable cross-process
  process recovery remains a later slice before broad speed proof.
- Validation before speed proof: focused unit tests, broad work-session /
  long-build / command / acceptance / dogfood suites, Terminal-Bench replay
  dogfood, and the `build-cython-ext` repository-test-tail emulator pass on
  the implementation slice. Claude-ultra re-review approved with no must-fix
  findings.

Scope: replace mew's narrow `long_command_budget` / long-build classifier
dispatch path with a generic managed command lifecycle for `run_command` and
`run_tests`.

## 1. Problem Statement

Mew's current command execution substrate can still spend most of a Terminal-
Bench run passively waiting on a foreground build, then lose the managed command
chain before terminal evidence exists. The immediate evidence is
`build-cython-ext`: Codex CLI averages about 14m41s and passes, while the
current mew rebaseline took about 29m30s and timed out with
`long_command_runs=null`.

The old decision in
`docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md` kept the classifier
narrow until lifecycle-routing failures became the active pattern. That decision
is now superseded. The observed failure is not "Cython needs a better
classifier"; it is that an already-existing partial substrate did not engage for
a real long build. The trigger condition is met:

- a real long command consumed wall budget without a managed run record;
- the gap class is structural command lifecycle, not a local build recipe;
- same-shape reruns risk repeating the same timeout without new strategy;
- current M6.24 focus says structural gaps should pause scoped measurement and
  repair generic substrate before another speed run.

Backward compatibility is not required before release, so the safer migration is
to replace the routing model instead of adding more classifier patches.

## 2. Current-State Inventory

Already implemented:

- `src/mew/toolbox.py` has blocking command execution through
  `run_command_record` and streaming blocking execution through
  `run_command_record_streaming`.
- `src/mew/toolbox.py` also has a partial `ManagedCommandRunner` with one
  in-memory active `ManagedCommandHandle`, `start`, `poll`, `finalize`, and
  `cancel`.
- `src/mew/work_session.py` routes `run_command` and `run_tests` through the
  managed runner only when `parameters.long_command_budget.action_kind` is
  `start_long_command`, `resume_idempotent_long_command`, or
  `poll_long_command`.
- `src/mew/work_session.py` records nonterminal managed snapshots as
  `CommandEvidence.status=running|yielded` with `finish_order=0`, and terminal
  polls/finalization as separate terminal evidence.
- `src/mew/long_build_substrate.py` defines `CommandEvidence`, `CommandRun`,
  `ExecutionContract` normalization, `LongCommandRun`, `LongBuildState`, and
  recovery decisions.
- `src/mew/commands.py` has wall-budget ceiling logic, reserve handling,
  same-timeout guards such as `repeat_same_timeout_without_budget_change`, and
  one-shot wait-to-poll conversion for live long commands.
- `src/mew/acceptance.py` already rejects non-terminal command evidence for
  verified acceptance checks.

Missing or insufficient:

- The lifecycle is not generic. Most commands still enter blocking subprocess
  paths unless the long-build budget classifier attaches special metadata.
- Foreground blocking time and command lifetime are not first-class separate
  fields. `yield_after_seconds` exists only in the managed budget branch.
- Output is primarily clipped inline memory. There is no generic durable
  command output file contract for every command.
- Process identity is not durable enough. The global in-process runner cannot
  recover active commands across process restart and does not own a session-level
  registry.
- The agent loop can still wait or poll passively instead of being scheduled to
  inspect source/config/tests while a command runs.
- Same-timeout suppression is local to long-build recovery shape; it is not a
  global execution fingerprint rule across all command attempts.
- `run_tests` currently has background restrictions in execution-contract
  validation. That conflicts with the target design where tests may be managed
  and backgrounded while still requiring terminal evidence before acceptance.
- The partial substrate did not engage for `build-cython-ext`, which means
  proof of code presence is not enough. The default tool path must change.

## 3. Target Architecture

All `run_command` and `run_tests` calls go through one managed execution
service. Short commands still usually complete during the foreground budget, but
they are represented with the same lifecycle and persisted output shape as long
commands.

```text
model action
  |
  v
run_command / run_tests
  |
  v
ExecutionContract normalizer
  |
  v
ManagedExecutionService
  |             |                 |
  | start       | poll/finalize    | cleanup
  v             v                 v
ManagedProcess registry ----> CommandOutputRef spool
  |
  v
CommandRun events
  |
  v
CommandEvidence
  |
  +--> nonterminal: running/yielded, finish_order=0, never acceptance
  |
  +--> terminal: completed/failed/timed_out/killed/interrupted, verifier-ready
  |
  v
Work session resume + agent loop scheduler
  |
  +--> if process running: continue read-only investigation or targeted edits
  |
  +--> if process terminal: consume output ref and decide next strategy
```

The long-build substrate becomes a consumer of generic managed execution. It
may still interpret a command as build, smoke, artifact proof, or verifier
evidence, but it no longer owns process lifecycle routing.

Live concurrency is intentionally bounded, not fully free-form:

- max live managed processes per work session: 4;
- max live managed processes per model/agent owner: 2;
- max live side-effecting command per work session: 1;
- read-only commands may run while one side-effecting build/test is yielded;
- unknown-risk commands are treated as side-effecting and serialize.

This adopts the useful part of Codex/Claude Code concurrency without giving a
benchmark agent an unbounded shell process pool. It is enough for the target
behavior: keep one build/test running while the agent performs short read-only
inspection commands or native read/search tools.

## 4. Data Model

### CommandRun

`CommandRun` is the durable user-visible record for every command attempt.

Required fields:

```json
{
  "schema_version": 3,
  "id": "work_session:1:command_run:4",
  "session_id": "1",
  "task_id": "task-1",
  "tool_call_id": 12,
  "tool": "run_command",
  "command": "python setup.py build_ext --inplace",
  "argv": ["python", "setup.py", "build_ext", "--inplace"],
  "execution_mode": "argv",
  "cwd": "/workspace",
  "status": "yielded",
  "started_at": "2026-05-03T00:00:00Z",
  "finished_at": null,
  "elapsed_seconds": 15.02,
  "foreground_budget_seconds": 15,
  "timeout_seconds": 1800,
  "final_proof_reserve_seconds": 60,
  "diagnostic_budget_seconds": 0,
  "managed_process_id": "work_session:1:process:4",
  "output_ref": {"kind": "command_output", "path": "work-session/1/command/4/output.log"},
  "execution_contract": {},
  "reducer_context": {},
  "failure_fingerprint": null,
  "terminal": {"exit_code": null, "timed_out": false, "terminal": false}
}
```

Statuses:

- `queued`: accepted but not started.
- `starting`: process launch in progress.
- `running`: process is live and still within foreground return window.
- `yielded`: process is live after foreground budget has expired.
- `finalizing`: exit observed, output drain and evidence write in progress.
- `completed`: terminal exit code 0.
- `failed`: terminal nonzero exit or launch failure.
- `timed_out`: command timeout expired and process tree was killed.
- `killed`: explicitly cancelled by user/session cleanup.
- `interrupted`: interrupted by user or owner agent.
- `orphaned`: durable state references a process that cannot be proven owned.

`CommandRun.reducer_context` replaces `LongCommandRun.reducer_hint`. The runtime
does not write semantic reducer hints. Reducers such as `LongBuildState` may
attach:

```json
{
  "long_build": {
    "scope": "current_failure_selection_only",
    "suppresses_stale_classes": ["build_timeout"],
    "never_suppresses": ["artifact_missing_or_unproven", "acceptance_proof"]
  }
}
```

Existing reducer tests that assert `LongCommandRun.reducer_hint` should map to
this field or to the equivalent reducer-owned `LongBuildState` projection. The
proof boundary is unchanged: reducer context may suppress stale failure
selection only; it never proves artifacts or acceptance.

### ManagedProcess

`ManagedProcess` is the runtime-owned process identity. It is authority for
polling and cleanup, not acceptance proof.

Required fields:

```json
{
  "schema_version": 1,
  "id": "work_session:1:process:4",
  "command_run_id": "work_session:1:command_run:4",
  "pid": 12345,
  "process_group_id": 12345,
  "owner_token": "managed-exec:session-1:nonce-4",
  "state": "live",
  "started_monotonic": 123.45,
  "timeout_deadline_monotonic": 1923.45,
  "foreground_deadline_monotonic": 138.45,
  "last_poll_at": "2026-05-03T00:00:15Z",
  "output_ref": {"kind": "command_output", "path": "work-session/1/command/4/output.log"}
}
```

Owner token verification is mandatory before poll, finalize, interrupt, or
cleanup. A pid match without owner token and registry match is not authority.

### ExecutionContract

`ExecutionContract` remains the semantic contract, but it must not decide
whether a command receives managed lifecycle. It decides interpretation,
parallel safety, acceptance role, and strategy pressure.

Important fields:

- `purpose`: source acquisition, configure, build, verification, diagnostic,
  generic command, and existing long-build roles.
- `stage`: semantic stage for reducers.
- `proof_role` and `acceptance_kind`: whether terminal success can support
  acceptance.
- `risk_class`: read-only, network read, build mutation, source mutation,
  runtime install, destructive, unknown.
- `foreground_policy`: default foreground budget, normally 10-15s.
- `timeout_policy`: command lifetime timeout.
- `background_policy`: whether yielding is automatic or explicit.
- `parallel_policy`: read-only safe, mutation exclusive, or serial unknown.
- `affected_paths`: optional list of files, directories, or simple prefix roots
  the command may read or mutate. Values are normalized relative to the work
  session root using POSIX separators. If omitted, affected roots are derived
  from `expected_artifacts`, `declared_target_refs`, `source_tree_ref`, and
  finally command `cwd`.
- `resume_identity`: stable idempotence key for reasoning, not lifecycle
  routing.

### CommandOutputRef

Every command has a durable output owner.

```json
{
  "kind": "command_output",
  "path": "work-session/1/command/4/output.log",
  "stdout_path": "work-session/1/command/4/stdout.log",
  "stderr_path": "work-session/1/command/4/stderr.log",
  "head": "bounded first output",
  "tail": "bounded latest output",
  "bytes": 123456,
  "lines": 3210,
  "truncated": false,
  "cap_bytes": 1000000,
  "tail_cap_bytes": 65536,
  "dropped_middle_bytes": 0,
  "encoding": "utf-8-replace"
}
```

The model sees tail/head previews and paths. Capped durable logs and the live
tail ring stay in artifacts and are inspected through targeted read/log-slice
tools.

Initial cap policy:

- `COMMAND_OUTPUT_SPOOL_MAX_BYTES = 1_000_000`, matching the existing
  `LONG_COMMAND_OUTPUT_MAX_BYTES` first-slice storage budget.
- `COMMAND_OUTPUT_TAIL_BYTES = 65_536` stays current after overflow.
- The process stays alive when output reaches the cap.
- The capped combined log preserves the first cap bytes. After overflow, the
  writer stops appending to the capped combined file, keeps updating the tail
  ring, increments total byte/line counters, and emits `output_overflow`.
- Poll results always include the current bounded tail, even after overflow.
- Retention follows the work-session artifact directory. Cleanup may delete old
  command output only when the containing session/artifact retention window
  expires and the output is not referenced by latest terminal evidence.

### FailureFingerprint

`FailureFingerprint` suppresses same-timeout-shape reruns.

```json
{
  "schema_version": 1,
  "id": "sha256:...",
  "command_key": "sha256:cwd+normalized_command+env+execution_contract",
  "budget_key": "timeout=1800;reserve=60;diagnostic=0",
  "failure_class": "timed_out",
  "failure_tail_hash": "sha256:last-significant-tail",
  "exit_code": null,
  "timed_out": true,
  "material_strategy_key": "sha256:runtime-computed-session-delta",
  "strategy_delta_refs": [{"kind": "tool_call", "id": 18}],
  "created_at": "2026-05-03T00:30:00Z"
}
```

The fingerprint is global within a work session and carried into resume context.
The same command plus same budget plus same failure fingerprint is blocked until
the agent records a materially different strategy.

Fingerprint records are appended to:

```text
work-session/<session-id>/managed-exec/failure-fingerprints.jsonl
```

Resume context includes the latest compact fingerprints for active affected
roots. The full JSONL file is the durable suppression source after compaction.

Normalization pipeline:

1. Parse command env assignments with `split_command_env`.
2. Unwrap no-op shell wrappers such as `bash -lc 'cmd'`, `sh -c 'cmd'`, and
   `zsh -lc 'cmd'` when the wrapper only delegates to one script.
3. Normalize argv commands as JSON array tokens. Normalize shell commands as the
   shell script text after trimming whitespace and collapsing redundant outer
   shell wrappers. Do not reorder shell segments.
4. Resolve `cwd` to an absolute normalized path string.
5. Compute `env_fingerprint` from an allowlist only: `AR`, `CC`, `CFLAGS`,
   `CMAKE_BUILD_PARALLEL_LEVEL`, `CXX`, `CXXFLAGS`, `LDFLAGS`, `MAKEFLAGS`,
   `OPAMSWITCH`, `OPAM_SWITCH_PREFIX`, `PATH_KIND`, `PKG_CONFIG_PATH`.
   Secret-looking names or values are excluded. Volatile values such as `PWD`,
   random temp dirs, tokens, and timestamps are excluded.
6. Compute `contract_key` from stable semantic fields:
   `purpose`, `stage`, `proof_role`, `acceptance_kind`, `risk_class`,
   `expected_artifacts`, `declared_target_refs`,
   `source_authority_requirement.source_tree_ref`,
   `resume_identity.source_tree_ref`, `resume_identity.execution_mode`, and
   `resume_identity.payload_hash`. Exclude `notes`, `evidence_refs`,
   timestamps, and model-authored prose.
7. `command_key = sha256(cwd, execution_mode, normalized_command,
   env_fingerprint, contract_key)`.
8. `budget_key = sha256(timeout_seconds, final_proof_reserve_seconds,
   diagnostic_budget_seconds)`.
9. `failure_tail_hash` normalizes the latest significant tail by stripping ANSI
   codes, carriage-return progress frames, blank-line runs, and obvious elapsed
   time counters. Absolute paths are preserved because they often distinguish a
   real strategy change.
10. `material_strategy_key` is runtime-computed from verifiable session state
    between the previous matching failure and the proposed rerun. It is not
    accepted from model free text.

Examples:

- `python setup.py build_ext --inplace` and
  `bash -lc 'python setup.py build_ext --inplace'` produce the same
  `command_key` when env, cwd, and contract are equal.
- Changing only the foreground budget from 15s to 30s does not unblock a
  timeout because the command timeout and failure fingerprint are unchanged.
- Reading `setup.py`, reading the failed log slice, and editing `pyproject.toml`
  produces a different `material_strategy_key` because those tool/evidence refs
  are included in `strategy_delta_refs`.

`material_strategy_key` is:

```text
sha256(stable_json({
  "strategy_delta_refs": sorted(strategy_delta_refs),
  "touched_path_digests": sorted(touched_path_digests),
  "contract_key_delta": contract_key_delta
}))
```

Allowed `strategy_delta_refs` are citeable session records: `read_file`,
`search_text`, `glob`, `inspect_dir`, `read_command_output`, diagnostic
`CommandEvidence`, and applied write/edit tool calls touching affected roots.
If no such record exists, the key remains unchanged and suppression holds.

Formula symbols:

- `strategy_delta_refs`: normalized citeable refs created after the matching
  failure and before the candidate rerun. Shape is
  `{"kind": "tool_call|command_evidence", "id": N, "role": "read|log_slice|diagnostic|edit"}`.
  Diagnostic commands are represented here; there is no separate
  `diagnostic_command_refs` input.
- `touched_path_digests`: hashes of normalized relative path strings only, not
  file content. Paths are resolved against the work-session root, converted to
  POSIX separators, stripped of `.` segments, and hashed as
  `sha256("path:" + relative_path)`. This records that relevant paths were
  touched without making the key depend on content churn.
- `contract_key_delta`: empty string when the candidate command's
  `contract_key` equals the failed command's `contract_key`; otherwise the
  candidate command's new `contract_key`.

Worked material strategy structure before hashing:

```json
{
  "strategy_delta_refs": [
    {"kind": "tool_call", "id": 18, "role": "read"},
    {"kind": "tool_call", "id": 19, "role": "log_slice"},
    {"kind": "tool_call", "id": 23, "role": "edit"}
  ],
  "touched_path_digests": [
    "sha256:path:pyproject.toml",
    "sha256:path:setup.py"
  ],
  "contract_key_delta": ""
}
```

Budget key fields:

- `timeout_seconds`: command lifetime timeout from `CommandRun.timeout_seconds`.
- `final_proof_reserve_seconds`: verifier/proof reserve recorded on
  `CommandRun.final_proof_reserve_seconds`; default 60.
- `diagnostic_budget_seconds`: explicit extra diagnostic budget recorded on
  `CommandRun.diagnostic_budget_seconds`; default 0.

`foreground_budget_seconds` is recorded on `CommandRun` for lifecycle behavior,
but it is intentionally excluded from `budget_key`. Increasing only foreground
blocking time changes how long the model waits before yield; it does not change
the command's chance to finish before timeout and must not unblock a same-timeout
rerun.

### Lifecycle Events

Events are append-only:

- `command_queued`
- `process_started`
- `foreground_yielded`
- `poll_observed`
- `output_progress`
- `output_overflow`
- `process_exited`
- `timeout_killed`
- `user_interrupted`
- `cleanup_killed`
- `evidence_finalized`
- `fingerprint_recorded`
- `same_timeout_suppressed`

Reducers may rebuild current state from events. Terminal evidence is still
written as a compact current-state convenience.

## 5. Tool Behavior

### Default Path

`run_command` and `run_tests` always call `ManagedExecutionService.start`.
There is no fallback blocking subprocess path for product work mode. If launch
fails, the service returns a terminal `failed` `CommandRun`.

### Model-Visible API

Use new tools for lifecycle operations instead of overloading command strings.
`run_command` and `run_tests` are start operations. Follow-up operations are
command-id only.

Start with `run_command`:

```json
{
  "type": "run_command",
  "command": "python setup.py build_ext --inplace",
  "cwd": ".",
  "timeout": 1800,
  "foreground_budget_seconds": 15,
  "execution_contract": {}
}
```

Start with `run_tests`:

```json
{
  "type": "run_tests",
  "command": "pytest tests/test_ext.py -q",
  "cwd": ".",
  "timeout": 900,
  "foreground_budget_seconds": 15,
  "execution_contract": {}
}
```

Both return:

```json
{
  "command_run_id": "work_session:1:command_run:4",
  "status": "yielded",
  "elapsed_seconds": 15.0,
  "timeout_seconds": 1800,
  "foreground_budget_seconds": 15,
  "exit_code": null,
  "command_evidence_ref": {"kind": "command_evidence", "id": 21},
  "terminal_command_evidence_ref": null,
  "output_ref": {"kind": "command_output", "path": "work-session/1/command/4/output.log"},
  "tail": "... latest output ..."
}
```

Poll/finalize:

```json
{
  "type": "poll_command",
  "command_run_id": "work_session:1:command_run:4",
  "wait_seconds": 5
}
```

Validation for `poll_command` is command-run-id only:

- `command_run_id` is required and must reference a live or finalizing
  `CommandRun` owned by the current work session;
- `command`, `cwd`, `timeout`, `execution_contract`, and shell fields are
  rejected if present;
- poll verifies owner token and managed process registry identity before
  observing or finalizing;
- polling a terminal command returns the cached terminal result and does not
  create duplicate evidence.

If poll observes terminal state, it performs finalization and returns:

```json
{
  "command_run_id": "work_session:1:command_run:4",
  "status": "completed",
  "elapsed_seconds": 412.3,
  "exit_code": 0,
  "timed_out": false,
  "terminal_command_evidence_ref": {"kind": "command_evidence", "id": 22},
  "output_ref": {"kind": "command_output", "path": "work-session/1/command/4/output.log"},
  "tail": "... final output ..."
}
```

Terminal poll/finalize writes one citeable `CommandEvidence` with
`finish_order > 0`, `command_run_id` equal to the original run, output refs,
exit code, timeout status, and `terminal_success` derived from exit status and
tool semantics. The earlier yielded evidence remains nonterminal with
`finish_order=0`.

Cancel/interrupt:

```json
{
  "type": "cancel_command",
  "command_run_id": "work_session:1:command_run:4",
  "mode": "interrupt",
  "reason": "need to edit files this build is reading"
}
```

`mode` is `interrupt` for graceful termination and `kill` for immediate process
tree kill. Validation is also command-run-id only. Cancel finalizes the run as
`interrupted` or `killed`, writes terminal non-success command evidence, and
returns `terminal_command_evidence_ref`. That evidence is citeable for diagnosis
but cannot satisfy acceptance.

Log slice:

```json
{
  "type": "read_command_output",
  "command_run_id": "work_session:1:command_run:4",
  "stream": "combined",
  "tail_lines": 120,
  "max_bytes": 20000
}
```

`read_command_output` is a read-only inspection tool. It accepts
`command_run_id`, `stream` (`stdout`, `stderr`, or `combined`), and one slice
selector: `tail_lines`, `line_start` plus `line_count`, or `byte_offset` plus
`max_bytes`. It never writes `CommandEvidence`; it can be cited as inspection
evidence, not terminal command proof.

### Foreground Blocking Budget

Foreground budget is separate from command timeout.

- Default foreground budget: 15s in agent work mode, allowed range 1-30s.
- Preferred M6.24 value: 10-15s. Use 15s for parity with Claude Code behavior.
- If the command exits before the foreground deadline, return terminal evidence.
- If still running at the foreground deadline, return `status=yielded` with
  command id, output path, elapsed, tail, bytes/lines, and timeout deadline.
- A yielded command is not failed and not successful.

### Command Timeout

Timeout is the maximum command lifetime, not the foreground wait.

- The timeout countdown starts at process start.
- Polling must enforce timeout even if no poll happens exactly at the deadline.
  A watcher or scheduler should finalize timeout independently.
- Timeout kills the process tree, drains bounded trailing output, and emits
  terminal `timed_out` evidence.
- The timeout can be longer than remaining model foreground budget but must fit
  the outer work-session wall and verifier reserve policy.

### `run_tests` Managed Yield

`run_tests` uses the same managed lifecycle as `run_command`, but it is not a
detached background task.

Required validation/default changes:

- In `normalize_execution_contract`, change the `run_tests`
  `background_policy.mode` default from `foreground_blocking` to
  `foreground_yieldable`.
- Keep `background_policy.allow_background=false` for `run_tests`.
- In `normalize_and_validate_work_execution_contract`, allow
  `background_policy.mode=foreground_yieldable` for `run_tests`.
- Continue rejecting `background_policy.mode=background_allowed` and
  `allow_background=true` for `run_tests`.
- Allow `continuation_policy.mode=managed` for `run_tests` when
  `terminal_required_for_acceptance=true`.
- `run_tests` may return `yielded` after the foreground budget, but acceptance
  remains blocked until a later `poll_command` finalizes terminal evidence.

This resolves the current validation conflict without making tests detached
from the work-session proof boundary.

### Background and Poll

The model can poll explicitly by command id, but the loop should not require
manual sleep. Resume context lists running commands and completion
notifications.

Poll result shape:

```json
{
  "command_run_id": "work_session:1:command_run:4",
  "status": "yielded",
  "elapsed_seconds": 72.4,
  "timeout_seconds": 1800,
  "exit_code": null,
  "output_ref": {"kind": "command_output", "path": "work-session/1/command/4/output.log"},
  "tail": "... latest compiler output ...",
  "bytes": 654321,
  "lines": 1234
}
```

If terminal, poll returns terminal result and writes final `CommandEvidence`.

### Live Command Concurrency

Scheduler rules:

- If live process count for the work session is already 4, new command starts
  are rejected with `too_many_live_commands`.
- If the owner model/agent already has 2 live processes, new command starts are
  rejected for that owner.
- If any live side-effecting command overlaps affected roots with a proposed
  side-effecting command, the proposed command is blocked until the live command
  finalizes or is cancelled.
- Read-only native tools and read-only `run_command` actions may proceed while
  one side-effecting command runs.
- Unknown `risk_class`, shell commands with unclassified operators, and
  commands lacking a valid `ExecutionContract` are side-effecting for
  concurrency.

Rejected start shape:

```json
{
  "status": "blocked",
  "reason": "too_many_live_commands",
  "blocked_tool": "run_command",
  "live_command_runs": [
    {"command_run_id": "work_session:1:command_run:4", "status": "yielded"}
  ],
  "suggested_next": "poll_command or continue read-only investigation"
}
```

### Output Persistence

Stdout and stderr are written to files as the process runs. The runtime keeps
bounded head/tail previews. Output must be drained continuously to avoid pipe
deadlock.

Minimum persistence rules:

- create output directory before launch;
- write stdout/stderr directly or drain to spool files immediately;
- cap total output using the head-plus-current-tail policy defined by
  `CommandOutputRef` and mark truncation;
- preserve the latest terminal command output until session artifact retention
  deletes the containing work session;
- never rely only on clipped model-visible stdout/stderr for verifier evidence.

### Process Cleanup

Cleanup is owner-scoped.

- When a work session exits, kill live processes owned by that session unless
  the session is explicitly preserved for resume.
- When an agent/subagent exits, kill processes it owns unless transferred to the
  parent session registry.
- On timeout, interrupt, or cleanup, kill the process group and then force kill
  after a short grace period.
- Mark unknown or unverifiable live records as `orphaned`, never as failed
  terminal evidence unless cleanup actually observes and records the kill.

## 6. Agent-Loop Behavior

Launching a long command should create work, not idle time. After a command
yields, the next prompt should include:

- command id, status, elapsed, timeout, output path, and tail;
- explicit note that running/yielded is progress only;
- a suggested useful-work lane based on the command type.

For `build-cython-ext`, useful work while the build runs includes:

- inspect `pyproject.toml`, `setup.py`, `setup.cfg`, and build backend config;
- inspect Cython extension sources and generated C/C++ surfaces;
- inspect failing tests and expected import/runtime behavior;
- inspect previous output tail for compiler errors or missing headers;
- prepare a narrow verification command for after completion.

The loop scheduler should prefer read-only and diagnostic actions while a
process is running. It should avoid passive `wait` unless no useful read,
inspection, or strategy step is available. A yielded command can trigger:

- completion notification: consume terminal result and decide next action;
- fast failure notification: inspect output ref and patch/narrow;
- prompt-like tail notification: handle possible interactive prompt;
- stall notification: classify healthy compile silence vs. deadlock/network
  stall before killing.

Polling is a state refresh, not the main activity. The model should not emit
sleep loops to poll. In one-shot mode, the runtime may auto-poll at bounded
intervals while still allowing the model loop to take useful actions between
notifications.

### Mutation Gate

The runtime enforces mutation gates before executing `write_file`, `edit_file`,
`edit_file_hunks`, `run_command`, `run_tests`, and cleanup/service commands.

Classification:

- Native reads (`read_file`, `search_text`, `glob`, `inspect_dir`,
  `git_status`, `git_diff`, `git_log`, `read_command_output`) are read-only.
- Native writes (`write_file`, `edit_file`, `edit_file_hunks`) are mutating.
- `run_tests` is side-effecting for concurrency unless its validated
  `ExecutionContract.risk_class` is `read_only` and its affected roots do not
  overlap a live side-effecting command.
- `run_command` is read-only only when the validated contract says
  `risk_class=read_only|network_read`, `parallel_policy=read_only_safe`, and
  command parsing finds no write, install, cleanup, redirection-to-file, or
  background control surface.
- Missing or invalid contracts are `unknown`, and `unknown` is mutating.

Affected roots are computed from:

- command `cwd`;
- `ExecutionContract.expected_artifacts`;
- `ExecutionContract.declared_target_refs`;
- explicit `affected_paths` or `source_tree_ref` fields when present;
- write tool target paths;
- conservative project root fallback for unknown shell commands.

Gate rule:

```text
if proposed action is mutating
and any live CommandRun is side-effecting
and affected roots overlap
then block proposed action unless it is cancel_command for that run
```

Blocked result shape:

```json
{
  "status": "blocked",
  "reason": "live_command_mutation_conflict",
  "blocked_tool": "edit_file",
  "blocked_paths": ["setup.py"],
  "conflicting_command_run": {
    "command_run_id": "work_session:1:command_run:4",
    "status": "yielded",
    "risk_class": "build_mutation",
    "affected_roots": ["."]
  },
  "allowed_next": [
    {"type": "poll_command", "command_run_id": "work_session:1:command_run:4"},
    {"type": "cancel_command", "command_run_id": "work_session:1:command_run:4"},
    {"type": "read_file", "path": "setup.py"}
  ]
}
```

The model may continue read-only investigation after a blocked mutation. To
edit files that the live command may be reading, it must first poll to terminal
state or cancel/interrupt the live command.

## 7. Acceptance and Proof Boundary

Running and yielded states never pass.

Verifier-ready state requires terminal evidence:

- terminal `CommandEvidence.finish_order > 0`;
- `terminal_success=true` for acceptance checks that cite command evidence;
- exit code and timeout status recorded;
- output ref retained;
- required artifacts or behavior proven by terminal command, readback, or
  external verifier evidence.

`CommandRun.status=yielded` can support recovery and planning only. It cannot
clear an acceptance constraint, cannot satisfy `task_done=true`, and cannot
allow external verifier handoff as final proof. If one-shot mode reaches a
yielded command at the end of the model step, it must either continue/poll until
terminal evidence or close with a nonfinal continuation report.

Default one-shot rule:

- Compute `poll_available = wall_remaining_seconds - reserve_seconds`.
- If `poll_available >= minimum_poll_seconds` and output progressed recently,
  auto-run `poll_command` with `wait_seconds=min(poll_available,
  default_poll_seconds)`.
- Otherwise close the one-shot report as nonfinal with
  `stop_reason=yielded_command_nonfinal`, `task_done=false`, latest
  `command_run_id`, output ref, elapsed, timeout deadline, and suggested resume
  action.

`minimum_poll_seconds` defaults to 5. `default_poll_seconds` defaults to 15 for
one-shot. "Output progressed recently" means the command has increased
`bytes`, `lines`, or `last_output_at` since the previous observation and
`now - last_output_at <= 60s`. Process exit observed by the watcher also counts
as progress because a poll can finalize immediately.

### One-Shot and Harbor Boundary

The Harbor wrapper and one-shot report writer are part of the proof boundary.
They must not convert yielded progress into verifier-ready success.

Required report fields:

```json
{
  "managed_exec": {
    "active_command_runs": [],
    "latest_command_run_id": "work_session:1:command_run:4",
    "latest_command_status": "yielded",
    "latest_terminal_command_evidence_ref": null,
    "command_output_refs": [],
    "failure_fingerprints_path": "work-session/1/managed-exec/failure-fingerprints.jsonl"
  },
  "timeout_shape": {
    "latest_command_run_id": "work_session:1:command_run:4",
    "latest_command_status": "yielded",
    "latest_long_command_run_id": null,
    "diagnostic_timeout_shape": true
  }
}
```

Report writer duties:

- refuse `verification=passed`, verifier-ready handoff, or
  `task_done=true` when any required command proof is `running` or `yielded`;
- include `active_command_runs`, output refs, terminal evidence refs, and
  compact failure fingerprints;
- preserve old `timeout_shape.latest_long_command_run_id` as a compatibility
  diagnostic only during artifact comparison, but populate the new
  `latest_command_run_id` and `latest_command_status` fields;
- replace synthetic `sleep` polling with `poll_command` by id under the default
  one-shot rule above;
- when outer Harbor timeout happens before a mew report exists, synthesize a
  report that says lifecycle state is unavailable instead of inventing a
  terminal command result.

`.harbor/mew_terminal_bench_agent.py` implementation duties:

- copy `managed_exec` and new timeout-shape fields from `mew-report.json` into
  `command-transcript.json` and Harbor result metadata;
- keep nonzero command exits captured as artifacts;
- mark yielded/running reports as nonfinal benchmark attempts, not verifier
  passes;
- preserve output refs and fingerprint paths in the task artifact directory;
- add tests for yielded one-shot reporting, outer-timeout-without-report, and
  terminal poll reporting.

## 8. Same-Timeout-Shape Suppression

Mew must globally suppress repeated same-timeout-shape reruns:

```text
same normalized command
+ same cwd/env/contract identity
+ same command-lifetime budget_key
+ same failure fingerprint
= blocked unless strategy changed
```

Here "same command-lifetime budget_key" means same `timeout_seconds`,
`final_proof_reserve_seconds`, and `diagnostic_budget_seconds`. Foreground
blocking budget is excluded; changing only the 10-15s foreground wait shape does
not unblock a rerun.

A materially different strategy can include:

- source or config inspection that identifies a concrete cause;
- an edit to relevant source/config/test/build files;
- a narrower repro or targeted build command;
- a changed dependency/toolchain path grounded by new evidence;
- a larger timeout only when the previous failure showed healthy progress and
  the new budget fits the strategy budget;
- a diagnostic command with a different purpose and explicit diagnostic budget.

Not materially different:

- rerunning the identical command with the same timeout;
- wrapping the same command in `bash -lc` without semantic change;
- increasing only foreground budget while command timeout stays the same;
- changing comments or unrelated files;
- polling an already terminal timed-out run as if it were still live.

The runtime decides materiality from session records, not from a model-authored
claim. Before a suppressed rerun can start, the candidate action must cite or be
preceded by at least one qualifying `strategy_delta_ref` after the matching
failure fingerprint:

- read/log evidence under affected roots;
- diagnostic command evidence with a different `purpose` or `stage`;
- applied write/edit evidence touching affected roots;
- execution contract change that alters `contract_key`;
- timeout increase paired with recent healthy output progress and available
  final-proof reserve.

If the model provides only free text such as "I will try a different strategy",
the material key remains unchanged and the rerun is blocked.

Strategy budget rules:

- First full broad build/test is allowed when needed for baseline signal.
- After a timeout, the next command must be poll/finalize if live, or a
  materially different diagnostic/targeted strategy if terminal.
- A second broad same-family attempt requires either a new fingerprint or a
  specific reason the prior timeout was healthy and under-budgeted.
- A third same-family timeout in one task stops the loop and records a structural
  blocker instead of burning the live proof budget.
- Timeout increases must reserve final proof time and must be recorded in the
  fingerprint's budget key.

## 9. Migration Plan

Backward compatibility is intentionally out of scope. Prefer deletion and
replacement over adapters where old behavior would hide lifecycle gaps.

Phase 0: freeze current failure shape.

- Preserve the `build-cython-ext` current-head artifact and this design.
- Do not run broad Terminal-Bench jobs during implementation.
- Build the same-shape `build-cython-ext` emulator before any focused
  `speed_1`. This is mandatory; there is no current emulator to merely
  identify.

Phase 1: introduce generic managed execution service.

- Add a session-owned process registry and durable event log.
- Move subprocess launch/drain/timeout/kill behavior out of the long-build
  budget path.
- Write output files for every command.
- Make short commands complete through the same service.

Phase 2: replace tool default paths.

- Delete or deprecate direct work-mode calls to `run_command_record` and
  `run_command_record_streaming`.
- Route all `run_command` and `run_tests` through managed execution.
- Add `poll_command`, `cancel_command`, and `read_command_output` to the work
  action schema with command-run-id-only validation.
- Change `run_tests` defaults and validation exactly as specified in
  `run_tests` Managed Yield.
- Keep non-work utility calls separate if they are outside work-session command
  evidence.

Phase 3: simplify long-build substrate.

- Remove `long_command_budget` as the lifecycle switch.
- Keep `ExecutionContract` and long-build reducers as semantic interpretation.
- Convert `LongCommandRun` into either a view over `CommandRun` or a specialized
  reducer projection, not a separate runtime owner.
- Move `LongCommandRun.reducer_hint` expectations to
  `CommandRun.reducer_context.long_build` or the reducer-owned
  `LongBuildState` projection.

Phase 4: agent-loop scheduling.

- Add running-command context to resume.
- Add completion notifications or runtime auto-poll records.
- Add useful-work nudges for build/test/package commands.
- Add mutating-tool gates while a command is live.
- Add one-shot default poll-vs-nonfinal behavior and remove synthetic `sleep`
  polling.
- Update `.harbor/mew_terminal_bench_agent.py` reporting to preserve
  `managed_exec`, new timeout-shape fields, output refs, and nonfinal yielded
  status.

Phase 5: suppression and strategy budget.

- Record `FailureFingerprint` for terminal failures and timeouts.
- Block same-timeout-shape reruns before tool execution.
- Require runtime-computed `material_strategy_key` from verifiable
  `strategy_delta_refs` to unblock.

Phase 6: delete narrow classifier reliance.

- Remove old classifier-only dispatch as the managed execution gate.
- Remove one-shot synthetic `sleep` polling if runtime notifications replace it.
- Keep stage classification only for semantic reducers and strategy prompts.

## 10. Test Plan

Unit tests:

- short command completes before foreground budget with terminal evidence;
- long command yields after 10-15s but continues to its timeout;
- `poll_command` rejects command/cwd/timeout fields and validates by
  `command_run_id` only;
- poll returns running status without creating terminal success;
- poll after exit creates terminal evidence exactly once;
- `cancel_command` finalizes interrupted/killed evidence that is citeable but
  not acceptance-successful;
- `read_command_output` returns log slices without writing command evidence;
- timeout kills process tree and records `timed_out`;
- output file receives stdout/stderr and exposes bounded head/tail;
- output cap overflow keeps the process alive, marks truncation, preserves head,
  and keeps tail current;
- owner-token mismatch becomes `orphaned` and cannot be accepted;
- live command concurrency limits reject the fifth live process and the second
  overlapping side-effecting process;
- mutation gate blocks overlapping writes while a side-effecting command is
  yielded and returns the specified blocked result shape;
- `run_tests` default contract is `foreground_yieldable`,
  `allow_background=false`, can yield, and still requires terminal success for
  acceptance;
- same-timeout fingerprint normalization maps a shell wrapper and direct argv
  command to the same key;
- same-timeout fingerprint blocks identical rerun when no verifiable
  `strategy_delta_refs` exist;
- material strategy key changes after a qualifying read/log slice/edit under
  affected roots.

Replay tests:

- migrate existing command evidence fixtures to new `CommandRun` shape;
- migrate `LongCommandRun.reducer_hint` fixtures to `CommandRun.reducer_context`
  or reducer-owned `LongBuildState` fields;
- replay a yielded long command followed by terminal poll;
- replay terminal timeout and verify recovery decision blocks same-shape rerun;
- replay `long_command_runs=null` build-cython-ext style artifact and verify the
  new default path would have produced a command run.

Dogfood tests:

- run a small local package build that sleeps or compiles long enough to yield;
- verify the model performs source/config inspection while the command runs;
- verify final acceptance waits for terminal command evidence.

Emulator:

- build the smallest `build-cython-ext` emulator with a slow build phase,
  output tail, failure fingerprint, and targeted source/config inspection lane;
- verify the first command yields, useful work happens, final poll completes,
  and same-timeout rerun is suppressed.

Harbor and one-shot tests:

- yielded one-shot with recent output and enough budget auto-polls by
  `command_run_id`;
- yielded one-shot without recent output or without minimum poll budget writes a
  nonfinal continuation report;
- `.harbor/mew_terminal_bench_agent.py` preserves `managed_exec`, output refs,
  timeout shape, and nonfinal yielded status in transcript/result metadata;
- outer timeout before mew report writes lifecycle-unavailable timeout shape
  without inventing terminal command evidence.

Focused speed_1:

- After UT, replay, dogfood, and emulator pass, run exactly one focused
  `build-cython-ext` speed_1 before broad measurement.
- Compare wall time, command run lifecycle, output refs, and terminal evidence
  against the 29m30s timeout artifact.

Broad measurement:

- Only after focused speed_1 shows the managed lifecycle engages and avoids the
  same failure shape.

## 11. Risks and Rollback/Stop Conditions

Risks:

- Process leaks if cleanup misses process groups or owner transfer.
- Output spool growth if caps are too high or truncation is wrong.
- The model may edit files while a running build is reading them, producing
  nondeterministic evidence.
- Too much lifecycle state may bloat prompts unless compacted aggressively.
- Generic management may add overhead for very short commands.
- Orphaned process recovery can be misread as terminal failure if proof
  boundaries are weak.
- Same-timeout suppression can block a legitimate rerun if fingerprints are too
  coarse.
- Command-run-id-only lifecycle tools can strand work if resume context loses
  the id.
- `run_tests` yielding can confuse old verifier assumptions if validation and
  acceptance tests are not updated together.
- Harbor may report a nonfinal yielded attempt as a benchmark failure even when
  a later poll would pass; this is intentional unless enough wall budget remains
  for the default one-shot poll rule.

Stop conditions:

- Any test shows running/yielded evidence can satisfy acceptance.
- A managed timeout leaves child processes alive in the same process group.
- Output is lost for a terminal failure.
- `run_command` or `run_tests` can still bypass managed lifecycle in work mode.
- The emulator reproduces `long_command_runs=null` after migration.
- Focused `build-cython-ext` speed_1 still times out with no command id, no
  output ref, or passive waiting as the dominant loop behavior.
- A yielded one-shot report is marked verifier-ready or `task_done=true`.
- Same-timeout suppression accepts a model free-text strategy claim without a
  qualifying session record.

Rollback:

- Because backward compatibility is not required, rollback should be a git-level
  revert of the managed execution migration slice, not a runtime flag that keeps
  both substrates alive.
- If only same-timeout suppression is too aggressive, disable suppression at the
  policy layer while keeping managed execution lifecycle intact.

## 12. Non-Goals

- No Terminal-Bench-specific Cython solver.
- No Codex CLI or Claude Code feature clone.
- No general shell parser beyond existing safe argv/shell execution needs.
- No stdin/interactive terminal support in the first migration.
- No multi-host or remote process manager.
- No indefinite daemon supervision.
- No acceptance from progress, running, yielded, or output tail alone.
- No broad Terminal-Bench measurement before focused emulator and speed_1 proof.

## 13. Implementation Order and Source Files

Likely source files touched:

1. `src/mew/toolbox.py`
   - Extract or replace `ManagedCommandRunner` with a durable
     `ManagedExecutionService`.
   - Add output file spool, process registry, foreground budget, timeout
     watcher, process-tree cleanup, and output caps.

2. `src/mew/long_build_substrate.py`
   - Promote generic `CommandRun` schema.
   - Add `ManagedProcess`, `CommandOutputRef`, `FailureFingerprint`, and event
     model helpers.
   - Convert `LongCommandRun` to a reducer projection or remove separate runtime
     ownership.
   - Move reducer hint semantics into `CommandRun.reducer_context` or
     `LongBuildState` reducer state.

3. `src/mew/work_session.py`
   - Route every `run_command` and `run_tests` through managed execution.
   - Add `poll_command`, `cancel_command`, and `read_command_output` execution
     handlers.
   - Record command events, nonterminal evidence, terminal evidence, and output
     refs.
   - Enforce mutating-tool gates while commands are live.
   - Update `run_tests` execution-contract validation to allow
     `foreground_yieldable` but reject detached background mode.

4. `src/mew/commands.py`
   - Remove lifecycle gating from `work_tool_long_command_budget_policy`.
   - Keep wall-budget and strategy-budget decisions as policy over generic
     `CommandRun`.
   - Replace one-shot synthetic sleep polling with command-id poll or runtime
     completion notification.
   - Add same-timeout-shape suppression before tool execution.

5. `src/mew/work_loop.py`
   - Include running command context and completion notifications in prompts.
   - Prefer useful investigation over passive waits.
   - Keep final answer blocked until terminal evidence exists.
   - Add model action schema entries for `poll_command`, `cancel_command`, and
     `read_command_output`.
   - Apply the one-shot poll-vs-nonfinal rule.

6. `src/mew/acceptance.py`
   - Preserve terminal-only proof boundary.
   - Add tests for new statuses and output refs.

7. `.harbor/mew_terminal_bench_agent.py`
   - Preserve `managed_exec`, command output refs, failure fingerprint path, and
     new timeout-shape fields in transcripts and result metadata.
   - Refuse verifier-ready interpretation for yielded/running reports.
   - Add Harbor wrapper tests for yielded, terminal, and outer-timeout reports.

8. Tests likely touched or added:
   - `tests/test_toolbox.py`
   - `tests/test_work_session.py`
   - `tests/test_long_build_substrate.py`
   - `tests/test_commands.py`
   - `tests/test_work_loop.py`
   - `tests/test_acceptance.py`
   - `tests/test_harbor_terminal_bench_agent.py`
   - focused emulator tests for `build-cython-ext` lifecycle.

## 14. M6.24 Close Gate

Close M6.24 generic managed execution repair only when all of these are true:

- `run_command` and `run_tests` default to managed lifecycle in work mode.
- `poll_command`, `cancel_command`, and `read_command_output` exist with
  command-run-id-only validation.
- A command that exceeds 10-15s foreground budget returns yielded/running state
  with command id, output path, elapsed, tail, and timeout deadline while the
  process continues.
- Poll/finalize produces one terminal command evidence record with exit code,
  timeout status, output ref, and elapsed time.
- `run_tests` can yield under `foreground_yieldable` while detached background
  mode remains rejected and terminal evidence remains mandatory.
- Running/yielded evidence cannot satisfy acceptance or external verifier-ready
  closeout.
- Harbor and one-shot reports preserve nonfinal yielded state and never report
  yielded/running as verifier-ready success.
- The agent loop demonstrates useful investigation while a build/test command
  runs.
- Same command plus same budget plus same failure fingerprint is globally
  suppressed unless a runtime-computed material strategy key changes from
  verifiable session state.
- Focused UT, replay, dogfood, and the newly built same-shape
  `build-cython-ext` emulator pass.
- Exactly one `build-cython-ext` speed_1 is run after those checks.
- The speed_1 artifact shows non-null command runs, durable output refs,
  terminal evidence, and no repeat of the 29m30s passive timeout shape.
