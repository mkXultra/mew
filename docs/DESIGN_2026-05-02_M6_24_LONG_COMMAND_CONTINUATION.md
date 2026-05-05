# Design 2026-05-02 - M6.24 Long-Command Continuation

Status: design proposal for decision.

Scope: generic long-command continuation and wall-budget handling for mew work
mode. This is not an implementation note and does not authorize source edits by
itself.

## Inputs Reviewed

- `docs/REVIEW_2026-05-02_CODEX_CLI_LONG_BUILD_CONTINUATION_PATTERNS.md`
- `docs/REVIEW_2026-05-02_CLAUDE_CODE_LONG_BUILD_CONTINUATION_PATTERNS.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `docs/REVIEW_2026-05-02_M6_24_COMPILE_COMPCERT_TIMEOUT_CLASSIFICATION_CODEX.md`

Relevant current source was sampled only to confirm integration shape:

- `src/mew/commands.py`
- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `src/mew/long_build_substrate.py`
- `.harbor/mew_terminal_bench_agent.py`

## Problem

The latest `compile-compcert` same-shape speed rerun reached the intended final
build path: source readback, external Flocq/MenhirLib configuration,
`make depend`, and explicit `make -j"$(nproc)" ccomp`. It then stopped with
`work_report.stop_reason=wall_timeout`; command evidence for the final build was
non-successful and `/tmp/CompCert/ccomp` was absent at verifier time.

The current blocker is therefore not another source-authority, dependency
strategy, runtime-link, or closeout reducer clause. The selected upper-level
failure class is:

```text
long-build wall-time/continuation budget
```

Mew already has most of the evidence substrate from the 2026-05-01 design:
native `CommandEvidence`, `LongBuildContract`, `BuildAttempt`,
`LongBuildState`, `RecoveryDecision`, wall-budget reserve enforcement, strict
terminal acceptance evidence, and compact recovery rendering. What it still
lacks is a generic way to treat a long command as an active evidence chain that
can yield, be polled, and later finalize without reopening stale blockers or
pretending progress is proof.

## Implementation Direction

Primary design decision: **adopt the smaller generic long-command continuation
contract and proceed with Phase 1+ design implementation once this document is
accepted**.

The current failure class is already pinned as
`long-build wall-time/continuation budget` by the timeout classification and by
both reference audits. The shared Codex CLI / Claude Code idea is not a
CompCert recipe and not a full shell-task clone. It is a generic command
identity, output, yield, poll, finalize, and proof-boundary contract.

The remaining one-run timeout-shape diagnostic is still useful, but it gates
proof escalation and same-shape benchmark closure, not Phase 1+ implementation.
It answers this narrow benchmark-classification question:

```text
Does the current strategy pass when the final ccomp build is allowed to finish?
```

That diagnostic must use a matched outer Harbor agent timeout and a larger
`mew --max-wall-seconds`. It is a run-shape diagnostic, not proof closure, not
broad measurement, and not a prerequisite for schema/runtime implementation.

The diagnostic should close only as classification evidence:

- If it passes only with extra wall time, do not escalate to `proof_5`. Continue
  the smaller generic continuation repair in this design before proof closure.
- If it still times out inside the final build despite the larger matched
  timeout, continue the smaller generic continuation repair immediately.
- If it fails before the final build with newer source/toolchain evidence,
  reclassify from the new evidence before spending more implementation effort.

Do not implement a full Codex-style `unified_exec` clone now, and do not
continue the current local detector/prompt repair loop. The references show the
right durable direction. The diagnostic can only redirect the plan if it
surfaces newer pre-final-build evidence that invalidates the current
wall-time/continuation classification.

## Adopted Reference Pattern

Adopt the concept, not the surface area.

Codex's transferable pattern is:

- command start identity;
- bounded output snapshots;
- yield while still running;
- poll with the same id;
- terminal finalization with a single end record;
- running snapshots never satisfy acceptance.

Claude Code's transferable pattern is:

- command/task status distinguishes running, backgrounded, completed, killed,
  and interrupted;
- output has a durable owner or file ref;
- progress is separate from final result;
- task notifications do not mutate proof boundaries;
- structured state carries continuation across compaction/recovery.

Mew's adaptation should be smaller:

- one active managed long command per work session;
- poll-only continuation first, no stdin support;
- one output owner with bounded head/tail and optional full-output ref;
- terminal `CommandEvidence` remains the only acceptance proof path;
- `LongBuildState` and `RecoveryDecision` decide whether to poll, resume, or
  block for budget;
- no new authoritative lane.

## Minimal Generic Architecture

### Concepts

Add one concept under the existing long-build substrate:

```text
LongCommandRun
```

`LongCommandRun` is the live runtime owner for one high-cost command attempt. It
does not replace `CommandEvidence`. It links process lifetime, output snapshots,
wall-budget state, and finalization to existing command evidence.

The relationship is:

```text
work action
  -> LongCommandRun(started|running|yielded)
  -> nonterminal CommandEvidence(status=running, terminal_success=false)
  -> LongBuildState(latest live build stage)
  -> RecoveryDecision(kind=poll_or_resume_long_command)
  -> LongCommandRun(finalized)
  -> terminal CommandEvidence(status=completed|failed|timed_out|killed)
  -> acceptance evidence / done gate
```

Running or yielded state may guide recovery. It cannot prove final acceptance.

### `LongCommandRun` Fields

Minimum persisted fields:

```json
{
  "schema_version": 1,
  "id": "work_session:1:long_command:3",
  "session_id": 1,
  "task_id": "source-build:foocc",
  "contract_id": "work_session:1:long_build:1",
  "attempt_id": "work_session:1:long_build:1:attempt:5",
  "running_command_evidence_ref": {"kind": "command_evidence", "id": 10},
  "terminal_command_evidence_ref": null,
  "tool_call_id": 10,
  "stage": "build",
  "selected_target": "foocc",
  "command": "make -j\"$(nproc)\" foocc",
  "cwd": "/tmp/FooCC",
  "env_summary": {"policy": "env_summary_v1", "items": []},
  "status": "running",
  "process": {
    "pid": 12345,
    "process_group_id": 12345,
    "owner_token": "managed-runner:session-1:nonce-3",
    "started_at": "2026-05-02T00:00:00Z",
    "last_poll_at": "2026-05-02T00:05:00Z"
  },
  "budget": {
    "outer_timeout_seconds": 3600,
    "mew_max_wall_seconds": 3480,
    "work_wall_remaining_seconds": 900,
    "requested_timeout_seconds": 1800,
    "effective_timeout_seconds": 840,
    "yield_after_seconds": 30,
    "final_proof_reserve_seconds": 60,
    "continuation_count": 0,
    "max_continuations": 3
  },
  "output": {
    "output_ref": "work-session/1/long-command/3/output.log",
    "stdout_head": "",
    "stdout_tail": "",
    "stderr_head": "",
    "stderr_tail": "",
    "output_bytes": 0,
    "truncated": false
  },
  "terminal": {
    "exit_code": null,
    "timed_out": false,
    "kill_reason": "",
    "finished_at": null
  },
  "continuation_eligible": true,
  "idempotence_key": "sha256(cwd\\0command\\0contract_id\\0stage\\0selected_targets_json)",
  "reducer_hint": {
    "scope": "current_failure_selection_only",
    "suppresses_stale_classes": ["build_timeout"],
    "never_suppresses": ["artifact_missing_or_unproven", "acceptance_proof"]
  }
}
```

The example values are illustrative. Implementation tests must not embed
CompCert, Coq, Flocq, MenhirLib, `ccomp`, or `libcompcert.a` as the only
positive path.

The field names may be adjusted during implementation, but the semantics should
remain stable:

- The process `owner_token` is generated by the current managed runner and is
  required for every poll/finalize operation.
- `pid` and `process_group_id` are diagnostic handles, not durable authority
  after process restart. A poll must verify that the live child is still owned by
  the current managed runner and matches the recorded owner token.
- `idempotence_key` is a deterministic tuple or hash of `(cwd, command,
  contract_id, stage, selected_targets_json)`. Equality means all tuple members
  match byte-for-byte after deterministic target JSON serialization.
- `reducer_hint` is not proof. It can only suppress stale current-failure
  selection that predates the live command chain. It must never satisfy artifact
  proof or acceptance.

### Output Owner and Retention

`output_ref` must point under the mew state/session artifact directory, for
example:

```text
work-sessions/<session-id>/long-command/<run-id>/output.log
```

The output owner stores the full stream up to a bounded cap and exposes bounded
head/tail previews for prompts and reports. The first slice should define a
small deterministic cap for tests and a product cap large enough for long-build
diagnosis; when the cap is reached, the owner preserves head/tail, marks
`truncated=true`, and records byte counts.

Retention follows work-session artifact retention. Cleanup may remove old
output refs only after their containing session/artifact directory is out of
scope; it must not delete the active run's output or the output linked from the
latest terminal evidence. A resumed command creates a new `LongCommandRun` and a
new `output_ref`; earlier runs and output refs remain available for diagnosis.

### Lifecycle

`start`

- Work loop identifies a planned `run_command` or `run_tests` as a long-build
  stage through `LongBuildContract` and `planned_long_build_command_stage()`.
- If the command is eligible and the feature gate is enabled for the current
  implementation phase, `commands.py` starts a managed process instead of a
  blocking command call.
- Mew writes `LongCommandRun(status=running)`.
- Mew writes a nonterminal `CommandEvidence` record with
  `terminal_success=false` and stores it in
  `LongCommandRun.running_command_evidence_ref`.
- Output begins streaming to the output owner immediately.
- The managed runner registers the live child with `owner_token`,
  `process_group_id`, command hash, cwd, and `LongCommandRun.id`.
- `yield_after_seconds` must be strictly less than `effective_timeout_seconds`.
  If it is not, the command must either run as a normal blocking command or
  return `block_for_budget` before starting.

`yield`

- If the process is still alive after `yield_after_seconds`, mew returns a tool
  result that says the command is still running and cites `long_command_run_id`,
  `running_command_evidence_ref`, current stage, elapsed time, and output tail.
- The work loop does not interpret this as failure.
- `LongBuildState` records the latest live stage and suppresses stale
  source/toolchain blockers that predate the live command chain.

`poll`

- A later work step may choose `poll_long_command` or an internal continuation
  action keyed by `LongCommandRun.id`.
- Empty poll is enough for M6.24. Do not support stdin in the first slice.
- Poll first verifies that the recorded child is still present in the live
  registry and that `owner_token`, process group, cwd, command hash, and run id
  still match. A bare pid match is not enough because pids can be reused.
- Poll refreshes output head/tail, elapsed wall time, process status, and
  budget fields.
- If still running and budget remains, it may yield again.
- Polling an already-running process does not increment `continuation_count`.

`finalize`

- On process exit, mew writes a new terminal `CommandEvidence` record and stores
  it in `LongCommandRun.terminal_command_evidence_ref`.
- The earlier running/yielded snapshot is retained as nonterminal evidence.
- `exit_code`, `timed_out`, `duration_seconds`, `finished_at`, output refs, and
  terminal status become authoritative.
- `LongBuildState` reduces from the terminal evidence.
- Only terminal success can satisfy final artifact proof.
- Acceptance resolves only the latest terminal evidence linked from the
  `LongCommandRun` and rejects the running/yielded evidence records.

`timeout` / `kill`

- If the managed command hits its effective timeout, mew records
  `LongCommandRun(status=timed_out|killed)` and terminal non-success
  `CommandEvidence`.
- `RecoveryDecision` may allow `resume_idempotent_long_command` only when the
  same contract/stage/cwd remains valid and enough wall budget is available.
- It must prohibit `repeat_same_timeout_without_budget_change`.
- A continuation is a resume after kill, timeout, or verified orphan loss. It is
  not a poll of an already-running process. `continuation_count` increments only
  for resumes.

`orphan`

- If an outer Harbor timeout kills mew before finalization, the next report
  cannot claim terminal status. The agent wrapper should preserve the command
  transcript and timeout shape so the run is classified as outer timeout, not
  task proof.
- If mew restarts or the live registry cannot prove ownership for a persisted
  `pid`, the run becomes `orphaned` or `killed` non-success evidence. Mew may
  resume only through `resume_idempotent_long_command` after verifying that the
  source tree, cwd, contract, stage, and idempotence key remain safe.
- Cleanup must terminate active managed process groups when the work session is
  cancelled, interrupted, or exits without a background-capable owner.

### `CommandEvidence` Integration

Current mew already records command evidence at work-tool start and completion.
The continuation contract should extend that shape, not create a second proof
system.

Required fields or semantics:

- `status`: allow `running`, `yielded`, `completed`, `failed`, `timed_out`,
  `killed`, `interrupted`.
- `terminal_success`: derived true only for `status=completed`, exit code zero,
  and no timeout. If any of those facts are absent or contradictory, acceptance
  must treat `terminal_success` as false even if a stored boolean says true.
- `finish_order`: unset or `0` while running; set only at terminal finalization.
- `long_command_run_id`: optional backref for managed commands.
- `running_command_evidence_ref`: points to the retained nonterminal snapshot.
- `terminal_command_evidence_ref`: points to the separate terminal record after
  finalize.
- `output_ref`: durable output owner for large logs.
- `output_head` / `output_tail`: bounded model-visible preview.
- `timed_out` and `kill_reason`: non-success evidence, not proof.

Acceptance must continue rejecting running, yielded, killed, interrupted,
timed-out, nonzero, masked, spoofed, and stale post-mutation evidence.
Acceptance must also reject any nonterminal evidence with unset or `0`
`finish_order`. The acceptance path must resolve the terminal evidence linked
from `LongCommandRun`, not the running snapshot.

### `LongBuildState` Integration

Add explicit nonterminal continuation fields:

```json
{
  "latest_long_command_run_id": "work_session:1:long_command:3",
  "latest_live_command_evidence_id": 10,
  "latest_build_stage": "build",
  "latest_build_status": "running",
  "latest_build_output_ref": "work-session/1/long-command/3/output.log",
  "latest_nonterminal_reason": "long_command_running",
  "continuation_required": true
}
```

Reducer rules:

- A running long command makes the state `in_progress`, not `blocked`.
- A killed or timed-out final build maps to `build_timeout` unless newer
  terminal evidence proves a more specific failure.
- Stale source-authority, dependency-strategy, or closeout blockers must not
  become `current_failure` when the latest evidence is a later live or killed
  final build.
- `reducer_hint.suppresses_stale_classes` and existing
  `cleared_strategy_blockers` interact only at this current-failure selection
  boundary. They do not change artifact status, source authority, default-smoke
  proof, or acceptance.
- `source_authority`, dependency strategy, and target selection can stay
  satisfied or superseded while the final build is running.
- `target_built` and final artifact proof remain unsatisfied until terminal
  evidence proves the artifact.

### `RecoveryDecision` Integration

Add a smaller continuation decision shape:

```json
{
  "decision": "continue",
  "failure_class": "build_timeout",
  "allowed_next_action": {
    "kind": "poll_long_command",
    "long_command_run_id": "work_session:1:long_command:3",
    "stage": "continue_or_resume_build",
    "description": "poll the active build; if no active process remains, rerun the same idempotent target with a larger budget",
    "required_evidence": "nonterminal_progress_or_terminal_command_status",
    "targets": ["/tmp/FooCC/foocc"]
  },
  "prohibited_repeated_actions": [
    "source_reacquisition",
    "clean_rebuild",
    "repeat_same_timeout_without_budget_change",
    "abandon_existing_source_tree_progress"
  ],
  "budget": {
    "remaining_seconds": 900,
    "reserve_seconds": 60,
    "may_spend_reserve": false,
    "minimum_poll_seconds": 5,
    "minimum_resume_seconds": 600,
    "continuation_count": 0,
    "max_continuations": 3
  }
}
```

Decision rules:

- `poll_long_command` is allowed when the process is still alive and the active
  run belongs to the latest long-build stage.
- `resume_idempotent_long_command` is allowed when the previous process was
  killed or timed out, the cwd/source tree remains valid, and the new budget
  differs materially from the failed timeout.
- `block_for_budget` is returned when starting or resuming cannot preserve the
  final proof reserve.
- `ask_user` is reserved for non-idempotent commands, uncertain cwd/source
  state, or repeated continuation exhaustion.

`RecoveryDecision` still does not finish a task. It only chooses the next safe
recovery action.

### Work Loop Wall-Budget Integration

Current `apply_work_tool_wall_timeout_ceiling()` prevents a command from
starting when remaining wall budget cannot cover the requested timeout plus
reserve. That remains correct for new commands.

Continuation needs one added distinction:

- starting a new long command requires enough budget for a meaningful run slice
  plus final proof reserve;
- polling an already-running command may use a smaller wait slice because it is
  not opening a new evidence branch;
- resuming a killed command requires a materially larger or explicitly
  diagnostic budget than the failed timeout;
- none of these may consume the final proof reserve unless
  `RecoveryDecision.budget.may_spend_reserve` explicitly allows it for a known
  recovery condition.

Production-visible yielding must remain disabled until the reducer and work-loop
presentation can safely handle `running` and `yielded` command evidence. Before
Phase 3 and Phase 4 are complete, the managed runtime may exist only as an
internal, feature-gated helper for unit tests.

The work loop should stop with a typed stop reason such as
`long_command_running` or `long_command_budget_blocked` instead of converting
the condition into a generic `wall_timeout` that reopens stale blockers.

### Harbor Agent Timeout-Shape Integration

`.harbor/mew_terminal_bench_agent.py` currently derives
`mew_max_wall_seconds` from `timeout_seconds` minus a bounded reserve and records
both values in `command-transcript.json`.

For the diagnostic and future continuation proof, the report should make the
timeout shape explicit:

```json
{
  "timeout_shape": {
    "agent_timeout_seconds": 3600,
    "mew_max_wall_seconds": 3480,
    "timeout_reserve_seconds": 120,
    "matched_outer_inner_timeout": true,
    "diagnostic_timeout_shape": true,
    "latest_long_command_run_id": "work_session:1:long_command:3",
    "latest_long_command_status": "completed"
  }
}
```

Close rules:

- If Harbor kills the outer command, the run is outer-timeout evidence, not
  proof of task failure strategy.
- The mew report writer is the enforcement point: it refuses verifier-ready
  success while any `LongCommandRun` is nonterminal.
- If mew exits while a managed long command is still running, the Harbor wrapper
  may cross-check timeout shape and transcript state, but it must not override
  the report writer into success. It must either poll/wait according to the
  managed command contract or record a nonterminal diagnostic.
- A speed diagnostic with larger timeout may classify the shape, but it is not
  a resource-normalized close proof.

## What Not To Copy Yet

Do not copy from Codex yet:

- full `unified_exec` protocol surface;
- PTY and stdin support;
- remote exec-server support;
- 64-process LRU process store;
- broad tool-event UI protocol;
- sandbox approval plumbing;
- rollout truncation as an acceptance-evidence store;
- review-thread architecture.

Do not copy from Claude Code yet:

- full Bash permission parser/classifier stack;
- auto-background thresholds;
- Monitor/Sleep/background task UI;
- full task V2/todo infrastructure;
- prompt-cache content replacement machinery;
- forked subagent and agent-team architecture;
- completion notifications as a replacement for deterministic evidence.

Do not add in mew yet:

- long-lived background processes outside a work session;
- multiple active long commands per work session;
- interactive build sessions;
- a benchmark-specific CompCert, Coq, Flocq, MenhirLib, or `ccomp` recipe;
- a broad prompt rewrite;
- another local detector sentence for this failure.

## Implementation Phases

The phases below implement the generic continuation contract. The diagnostic
classification run is listed first because the M6.24 controller still needs it
before proof escalation or benchmark closure, but it is not Phase 0 and it does
not block Phase 1+ schema/runtime implementation after this design is accepted.
Each implementation phase has a close gate.

### Diagnostic Classification Run

Run one same-shape `compile-compcert` speed diagnostic with:

- matched larger Harbor `timeout_seconds`;
- larger `mew --max-wall-seconds`;
- same model, permissions, task, wrapper, and trial count except for the
  documented timeout shape;
- report path recorded in the decision ledger.

Close gate:

- If reward `1.0`, runner errors `0`, `mew work` exit `0`, invokable target
  artifact, and smoke/default invocation passed, classify the current strategy
  as wall-limited. Do not run `proof_5`; continue this continuation design as
  the durable repair before proof closure.
- If it still times out inside the final build, select this continuation design
  immediately as tool/runtime repair.
- If it fails earlier with new evidence, reclassify before spending more
  implementation effort.

Residual closeout reducer noise such as stale `current_failure`, strategy
blockers, or source-authority state should be recorded separately. It should not
block diagnostic classification of the wall-time question unless it is newer
pre-final-build evidence that changes the failure class.

Tests: none beyond artifact/report validation, because this phase is a run-shape
diagnostic.

### Phase 1 - Schema and Output Owner

Add `LongCommandRun` schema helpers and an output owner/ref policy.

Close gate:

- one active run per work session is representable;
- running/yielded records cannot satisfy terminal acceptance;
- output head/tail and output ref are deterministic and bounded;
- `output_ref` storage root, retention, and cleanup policy are documented;
- schema version and cleanup policy are documented.

Tests:

- unit tests for serialization, id allocation, output clipping, output refs,
  and secret-free env summaries;
- acceptance tests proving running/yielded command evidence is rejected;
- acceptance tests proving `running`, `yielded`, `killed`, `interrupted`,
  `timed_out`, failed, unset-finish-order, and contradictory
  `terminal_success=true` nonterminal records are rejected;
- non-CompCert fixture for a generic long build that emits large output.

### Phase 2 - Managed Start/Yield/Finalize Runtime

Implement a poll-only managed command runner for `run_command` and `run_tests`.
This phase is internal and feature-gated. Production-visible yielding remains
disabled until Phase 3 and Phase 4 land.

Close gate:

- a long command can start, yield while alive, preserve process id, and finalize
  with a separate terminal `CommandEvidence`;
- timeout and kill produce terminal non-success evidence with output tail;
- stale/missing live process handles become orphan/killed non-success evidence;
- no stdin, PTY, or multi-process store is added.

Tests:

- synthetic command that sleeps, emits output, yields, then exits `0`;
- synthetic command that exits nonzero after yield;
- synthetic command that exceeds timeout and is killed as a process group;
- output streaming does not deadlock on stdout/stderr;
- interrupted/killed evidence cannot satisfy final artifact proof;
- second managed long command is rejected while one active command exists;
- resumed-running record is rejected by acceptance;
- finalized killed evidence is rejected by acceptance;
- restart/stale-pid/orphan cleanup tests prove owner-token validation and
  process-group cleanup.

### Phase 3 - LongBuildState and RecoveryDecision Continuation

Connect `LongCommandRun` to `LongBuildState` and `RecoveryDecision`.

Close gate:

- running final-build command produces `LongBuildState.status=in_progress`;
- killed/timed-out final-build command maps to `build_timeout`;
- stale source/toolchain/closeout blockers do not override the latest final
  build chain;
- `RecoveryDecision` can choose `poll_long_command`,
  `resume_idempotent_long_command`, or `block_for_budget`;
- `poll_long_command` does not increment `continuation_count`; only
  resume-after-kill/timeout/orphan does.

Tests:

- current compile-compcert-shaped fixture replay, without adding CompCert
  constants;
- `toy_toolchain_default_runtime` transfer fixture;
- `cmake_generated_dependency` transfer fixture;
- stale source-authority blocker followed by newer final build timeout stays
  classified as build timeout;
- repeated same timeout without larger budget is prohibited;
- idempotence keys compare cwd, command, contract id, stage, and selected
  targets deterministically.

### Phase 4 - Work Loop Budget and Prompt Rendering

Teach the work loop to present continuation actions and budget states.

Close gate:

- starting, polling, resuming, and blocking have distinct stop/action records;
- compact recovery renders the latest live/killed build state and not old
  `suggested_next` prose;
- work-loop budgeting enforces `yield_after_seconds <
  effective_timeout_seconds` and blocks or uses normal blocking execution when
  that relationship cannot hold;
- static long-build prompt sections do not grow unless the anti-accretion gate
  records why.

Tests:

- wall-budget unit tests for start versus poll versus resume;
- compact recovery prompt-size tests;
- prompt-section metric/hash tests;
- done-gate tests with `command_evidence` refs after continuation.

### Phase 5 - Harbor Timeout-Shape Reporting

Add timeout-shape reporting and nonterminal handling in the Harbor wrapper.

Close gate:

- `command-transcript.json`, `summary.json`, and `mew-report.json` expose
  outer timeout, mew wall timeout, reserve, and diagnostic flag;
- outer timeout is distinguishable from mew command timeout;
- mew report writer refuses verifier-ready success while a managed long command
  is still nonterminal, and the Harbor wrapper preserves that refusal.

Tests:

- local import-without-Harbor tests for timeout-shape fields;
- wrapper tests for `_mew_max_wall_seconds()` with diagnostic timeout shapes;
- transcript normalization tests for nonzero, timeout, and nonterminal status;
- Harbor-killed session with an active `LongCommandRun` produces a nonterminal
  diagnostic and never verifier-ready success.

### Phase 6 - Transfer Then Same-Shape Rerun

Run transfer fixtures before spending a new `compile-compcert` proof.

Close gate:

- at least two non-CompCert long-build transfer fixtures pass;
- acceptance still rejects nonterminal proof;
- one same-shape `compile-compcert` speed_1 records movement or pass under the
  normal selected timeout shape.

Tests:

- `toy_toolchain_default_runtime`;
- `rust_or_cargo_cli_long_build` or equivalent ordinary source build with no
  runtime/default-link requirement;
- `invalid_target_surface_generic`;
- `masked_or_spoofed_artifact_proof_rejected`;
- scoped ruff and `git diff --check`.

Only after this phase should the decision ledger consider resource-normalized
`proof_5`.

## Avoiding Compile-CompCert Overfitting

The continuation contract must be stage- and evidence-based:

- use `LongBuildContract` artifact paths, not `/tmp/CompCert/ccomp` constants;
- use generic stages such as `build`, `runtime_build`, `runtime_install`,
  `default_smoke`, and `artifact_proof`;
- use generic failure classes such as `build_timeout`,
  `artifact_missing_or_unproven`, `runtime_link_failed`, and
  `budget_reserve_violation`;
- require transfer fixtures with different artifact names, build systems, and
  runtime-proof requirements;
- forbid implementation tests whose only positive case names CompCert, Flocq,
  MenhirLib, Coq, `libcompcert.a`, or `ccomp`;
- keep acceptance proof strict and terminal, so a long-output tail that "looks
  close" never passes the task;
- keep source-authority and dependency strategy state as prerequisites, not as
  recipes.

The generic invariant is:

```text
continue the latest valid idempotent long-build evidence chain; never reopen
older blockers without newer evidence; never treat nonterminal progress as
proof.
```

## Dossier and Ledger Changes If Adopted

`docs/M6_24_DECISION_LEDGER.md` should get one append-only decision row:

```text
2026-05-02 | Adopt long-command continuation design as the durable repair for
the wall-time/continuation budget class. | Evidence: this design, the two
reference audits, the timeout classification, and the latest build-timeout
recovery speed rerun. | Next action: implement Phase 1+ behind the documented
feature gate, run transfer fixtures, then one same-shape speed_1 before proof_5.
The one-run timeout-shape diagnostic gates benchmark closure/proof escalation,
not implementation. | continuation_design_adopted_repair_pending
```

If the file has a status for the old 2026-05-01 Long-Build Substrate Phase 0/3/4
measurement gate, mark it superseded by the continuation design using an
append-only row rather than rewriting history.

`docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md` should change:

- add this design to controller inputs;
- update Current Decision to name the diagnostic plus precommitted continuation
  repair trigger;
- add a timeline row after v2.1 for `long-command continuation design`;
- add a Pattern Readout bullet: the current blocker is above source/toolchain
  policy and should be repaired as generic command continuation/budget, not
  another prompt/profile clause;
- add a Non-Goal: no full Codex/Claude clone and no compile-compcert solver.

`docs/M6_24_GAP_IMPROVEMENT_LOOP.md` has documented drift: it still names the
old Long-Build Substrate Phase 0 next action even though Phases 0-4 are
implemented and the ledger now selects the timeout/continuation class. If this
design is adopted, update the controller precisely:

- add this design and both reference reviews to authoritative inputs;
- make this design the active authoritative design, with the 2026-05-01
  Long-Build Substrate design retained as foundational substrate;
- replace the stale paragraph that says Long-Build Substrate Phase 0 schema +
  safety-parity harness is current;
- update the selected next action to:

```text
M6.24 -> long_dependency/toolchain gap -> wall-time/continuation budget
-> adopt long-command continuation contract
-> implementation phases
-> same-shape speed_1 after transfer fixtures
```

The one-run timeout-shape diagnostic remains a run-shape/proof-escalation gate
and may redirect only if it surfaces newer pre-final-build evidence.

`proof-artifacts/m6_24_gap_ledger.jsonl` should get one append-only JSON object
recording this as structural/tool-runtime repair adoption with `status` set to
`repair_pending` or `repairing` and evidence paths to this design plus the two
reference reviews.
