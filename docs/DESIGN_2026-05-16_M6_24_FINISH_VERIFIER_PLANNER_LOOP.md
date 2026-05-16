# Design 2026-05-16 - M6.24 Finish Verifier Planner Loop

Status: design only.

Scope: design a bounded read-only `FinishVerifierPlannerLoop` v0 component for
`implement_v2` native finish closeout. This document does not implement code and
does not change source, tests, live Harbor behavior, or Terminal-Bench spending
by itself.

This design supersedes the no-tools planner shape in
`docs/DESIGN_2026-05-15_M6_24_FINISH_VERIFIER_PLANNER.md` for the next
implementation slice. The May 15 design remains useful for provenance,
artifact, and safety constraints, but make-doom-for-mips exposed that compact
recent-output context alone is not enough to generate a strong final verifier.

## Decision

Build `FinishVerifierPlannerLoop` v0 as a lightweight bounded read-only
component inside `implement_v2`, not as a resident lane.

The component improves final verifier command generation. It may read task text,
`task_contract`, the latest mutation summary, recent command outputs, external
verifier failure details when available, and selected workspace files through a
strict read-only tool surface. It must not write files, mutate state, execute the
final verifier, call `finish`, or decide task completion.

The component returns one structured verifier command candidate plus confidence,
rationale, and observability fields. The main harness validates and executes the
selected command through the normal command runtime. If that trusted final
verifier command exits `0`, the native finish gate allows completion.

Durable decisions preserved here:

- final verifier command exit `0` means finish;
- do not block an exit-0 finish with task-contract or oracle-obligation
  coverage;
- do not use node-vm-specific or weak-verifier regex heuristics as the primary
  fix;
- do not reintroduce `recent_successful_verifier` as finish authority;
- configured verifier remains rank 1 when explicitly provided;
- `FinishVerifierPlannerLoop` v0 is the main rank-2 command-quality path;
- auto-detected verifier may remain as a later fallback, but fallback must be
  observable and must not hide planner rejection;
- planner v0 is an `implement_v2` component until evidence shows it needs
  independent memory, reentry, scheduling, or long-lived lane state.

## 1. Problem Statement And Non-Goals

### Problem

M6.24 is trying to close the remaining gap between mew's software/coding
Terminal-Bench behavior and stronger coding agents. The current finish problem
is no longer just "the model tries to finish too early." The native finish gate
can now accept a trusted final verifier command that exits `0`, which is the
right hot-path completion rule. The failure mode has moved upstream: command
quality.

For `make-doom-for-mips`, the internal loop can reach a finish because a final
verifier command exits `0`, while the external Terminal-Bench verifier still
fails. The internal verifier is too weak or pointed at the wrong proof surface.
Blocking the exit-0 finish with task-contract obligations would repair one
artifact by undoing the recent native finish-gate decision and would reproduce
old resolver drift. The right repair is to make the command-generation path
stronger before the command is executed.

Current implementation signals:

- `src/mew/implement_lane/native_finish_gate.py` already models final verifier
  source precedence and allows completion when
  `NativeFinishCloseoutResult.status == "completed_zero"`.
- `src/mew/implement_lane/native_tool_harness.py` already has an experimental
  planner spike, but it is compact-context-only, mixed into the harness, and
  still falls back to auto-detected commands through local helper logic.
- `tests/test_native_finish_gate.py` and `tests/test_native_tool_harness.py`
  already encode key decisions: configured verifier precedence, planner before
  auto-detected verifier, observable fallback records, and exit-0 native finish
  authority.
- The May 15 planner design intentionally forbade direct read-only workspace
  access. That kept the planner simple, but it leaves hard runtime tasks without
  enough source/context to identify a verifier command that checks the external
  task outcome rather than an internal surrogate.

The new component should improve the command selected for final closeout while
leaving the native finish gate's authority unchanged.

### Non-Goals

- No source or test implementation in this document.
- No change to the rule that a trusted final verifier closeout exit `0` allows
  completion.
- No task-contract or typed-obligation veto after an accepted final verifier
  command exits `0`.
- No node-vm, Doom, MIPS, frame-size, or benchmark-specific verifier heuristics
  as the primary fix.
- No `recent_successful_verifier` authority. Prior command output may inform the
  planner, but a previous successful command is not itself a finish source.
- No planner acceptance authority. Planner rationale, confidence, and prose are
  never completion evidence.
- No direct final-verifier execution by the planner.
- No write, exec, shell, network, or state-mutating tools in the planner loop.
- No resident lane promotion in v0.
- No replacement of the external Terminal-Bench verifier as final oracle.

## 2. Current Flow And Proposed Flow

### Current Flow

The current native path is broadly:

```text
provider-native model turn
  -> model emits finish_call
  -> harness executes finish protocol result
  -> _run_native_finish_time_closeouts(...)
       -> active command closeout if needed
       -> find latest source mutation without later verifier
       -> choose final verifier plan
            configured verifier
            else experimental compact planner if enabled
            else auto-detected verifier
       -> run closeout command through run_command or exec_command
       -> derive closeout context
  -> NativeFinishGateDecision if closeout is available
       exit 0 -> completed
       nonzero/timeout/missing/unsafe -> block
  -> paired finish_output
```

The current planner spike is:

```text
task text + task_contract subset + last 8 tool-result summaries
  -> call_codex_json separate planner request
  -> coerce one command JSON
  -> local safety checks
  -> accepted planner plan
       or rejected/error planner record + auto-detected fallback
```

The useful properties are already present: separate provider session,
configured-verifier precedence, fallback records, command safety checks, and
sidecar persistence. The main limitations are that the planner cannot inspect
selected source files, cannot see external verifier failure details unless they
happen to be summarized in recent output, and is not yet a clean component API.

### Proposed Flow

`FinishVerifierPlannerLoop` v0 becomes a controller-owned component invoked only
when no explicit configured verifier is available and final closeout needs a
better command source.

```text
model finish_call
  -> active-command closeout if needed
  -> latest mutation needs final verifier
  -> rank 1: configured verifier?
       yes -> validate + execute configured command
       no
  -> rank 2: FinishVerifierPlannerLoop v0
       build bounded request from task, contract, mutation, recent output,
       optional external failure, and selected read-only file roots
       planner may read files/search selected paths only
       planner returns exactly one command JSON or no_plan
       controller records raw transcript and raw plan
       controller validates command safety/provenance
       accepted -> execute planner command through normal runtime
       rejected/unavailable/no_plan -> record reason
  -> rank 3: auto-detected fallback if available and policy allows
       selected only after planner is missing/rejected/unavailable
       fallback record must include planner status and reason
  -> native finish gate evaluates actual closeout result
       exit 0 -> completed
       nonzero/timeout/missing/unsafe -> blocked
  -> observer artifacts link planner, fallback, command execution, and finish
```

Authority remains simple:

```text
command selection quality:
  configured verifier > planner loop > auto-detected fallback

finish authority:
  trusted selected command executed by harness exits 0 -> finish
```

The planner improves the command before execution. It does not add a second
post-execution gate.

## 3. Component API And Schema

### Component Boundary

`FinishVerifierPlannerLoop` v0 is a small `implement_v2` component with three
interfaces:

1. Build a bounded request from existing lane state.
2. Run a separate read-only planner loop.
3. Return a structured candidate plus observer records for the harness.

It does not own provider continuity for the main implementer. It must not reuse
the implementer's `previous_response_id`.

### Implementation Boundary And Carrier Mapping

V0 should fit the current harness without creating a second finish-command
carrier. The planner loop returns a component result, not direct finish
authority.

Proposed Python boundary:

```python
@dataclass(frozen=True)
class FinishVerifierPlannerLoopPolicy:
    enabled: bool
    max_turns: int = 3
    max_wall_seconds: float = 30.0
    max_file_reads: int = 12
    max_searches: int = 8
    max_bytes_per_file: int = 20_000
    max_total_read_bytes: int = 120_000
    allowed_tools: tuple[str, ...] = ("inspect_dir", "read_file", "search_text", "glob")
    allowed_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierPlannerLoopRequest:
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    task_id: str
    task_description: str
    task_contract: Mapping[str, object]
    latest_mutation: Mapping[str, object]
    recent_tool_results: tuple[Mapping[str, object], ...]
    candidate_paths: tuple[str, ...]
    policy: FinishVerifierPlannerLoopPolicy
    external_verifier_failure: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class FinishVerifierPlannerLoopResult:
    status: Literal["selected", "no_plan", "rejected", "error", "timed_out"]
    plan: _NativeFinishVerifierPlan | None
    record: Mapping[str, object]
    blockers: tuple[str, ...] = ()
    reason: str = ""
```

Controller entrypoint:

```python
def run_finish_verifier_planner_loop(
    request: FinishVerifierPlannerLoopRequest,
    *,
    planner_provider: FinishVerifierPlannerProvider,
    read_dispatcher: PlannerReadOnlyDispatcher,
    artifact_sink: PlannerArtifactSink,
) -> FinishVerifierPlannerLoopResult:
    ...
```

Layer mapping:

- The planner loop returns `FinishVerifierPlannerLoopResult`.
- `result.plan` is `_NativeFinishVerifierPlan | None` because
  `native_tool_harness.py` currently uses `_NativeFinishVerifierPlan` to build
  `_native_final_verifier_closeout_call(...)`.
- The harness converts `_NativeFinishVerifierPlan(source="finish_verifier_planner")`
  into `FinishCloseoutCommand(source="finish_verifier_planner")` only when
  building `NativeFinishGateRequest` or when pure `native_finish_gate.py`
  helpers need the public carrier.
- `FinishCloseoutCommand` remains the public native finish-gate command shape.
  `_NativeFinishVerifierPlan` is an internal harness carrier and should be
  deleted or moved once final closeout dispatch is fully extracted from the
  harness.
- Neither carrier is finish authority. Authority begins only after the harness
  executes the selected closeout command and `NativeFinishGateDecision` consumes
  the terminal result.

Source-value mapping is closed:

```text
configured_verifier       -> _NativeFinishVerifierPlan.source -> FinishCloseoutCommand.source
finish_verifier_planner   -> _NativeFinishVerifierPlan.source -> FinishCloseoutCommand.source
auto_detected_verifier    -> _NativeFinishVerifierPlan.source -> FinishCloseoutCommand.source
```

No other planner output source value is accepted in v0.

### Request Schema

Proposed request shape:

```json
{
  "schema_version": 1,
  "component": "FinishVerifierPlannerLoop",
  "role": "independent_read_only_finish_verifier_planner",
  "lane_attempt_id": "attempt-id",
  "turn_id": "turn-7",
  "finish_call_id": "finish-1",
  "workspace": ".",
  "task": {
    "task_id": "make-doom-for-mips",
    "description": "original task text",
    "contract": {
      "description": "bounded task_contract fields",
      "acceptance_constraints": [],
      "expected_artifacts": [],
      "verify_command_source": "auto_detected_verifier"
    }
  },
  "latest_mutation": {
    "provider_call_id": "write-4",
    "tool_name": "write_file",
    "paths": ["vm.js"],
    "summary": "latest source/artifact mutation summary",
    "turn_index": 6
  },
  "recent_command_outputs": [
    {
      "tool_name": "run_command",
      "command": "node vm.js",
      "status": "failed",
      "exit_code": 1,
      "summary": "bounded stdout/stderr summary",
      "content_refs": [],
      "evidence_refs": []
    }
  ],
  "external_verifier_failure": {
    "available": true,
    "source_ref": "proof-artifacts/.../verifier/test-stdout.txt",
    "same_shape_key": "terminal-bench:make-doom-for-mips:profile-hash",
    "summary": "bounded terminal-bench failure summary",
    "failed_checks": ["test_vm_execution", "test_frame_exists"],
    "artifact_paths": ["/tmp/frame.bmp"]
  },
  "read_policy": {
    "allowed_tools": ["inspect_dir", "read_file", "search_text", "glob"],
    "allowed_roots": ["/app"],
    "max_turns": 3,
    "max_file_reads": 12,
    "max_searches": 8,
    "max_bytes_per_file": 20000,
    "max_total_read_bytes": 120000,
    "candidate_paths": ["vm.js", "Makefile", "doomgeneric/doomgeneric_img.c"]
  },
  "command_policy": {
    "available_execution_surface": "run_command",
    "cwd_roots": ["."],
    "allow_shell_execution": true,
    "shell_composition_blocked": true,
    "max_timeout_seconds": 60,
    "forbidden_command_families": [
      "noop_success",
      "self_acceptance",
      "source_mutation",
      "package_install",
      "network",
      "background",
      "secret_access"
    ]
  },
  "output_contract": {
    "json_object": true,
    "required": ["status", "command", "cwd", "confidence", "rationale"],
    "meaning": "one non-mutating command that verifies current task completion"
  }
}
```

`external_verifier_failure` is optional and should be present only when the
harness has saved external failure information from a prior same-shape run or
replay. It is input for command planning, not a finish blocker.

Early v0 phases should omit `external_verifier_failure` unless the data comes
from a local replay/proof artifact with a same-shape key matching task id,
Terminal-Bench task name, selected lane/profile, and command/workspace shape.
Acceptable sources are saved verifier stdout/stderr, `result.json`
`verifier_result`, or a proof-manifest field that points to those files. Live
planner execution must not query Harbor or Terminal-Bench for new external
failure data.

`allow_shell_execution` means the normal runtime may use its shell-capable
command surface to run one selected command string. It does not allow command
composition: chains, pipes, redirection, backgrounding, and unconditional
success fallbacks remain validation blockers.

### Read-Only Tool Surface

V0 allowed planner tools:

- `inspect_dir` or equivalent directory listing;
- `read_file` with byte cap and line/window cap;
- `search_text` or `rg`-equivalent read-only search;
- `glob` or path enumeration under allowed roots.

V0 does not expose `read_command_output` to the planner because that tool lives
on the command/process surface today. Prior command output is supplied through
bounded `recent_command_outputs` summaries in the request. A later design may
add a stored-output read shim, but it must be unable to poll, cancel, resume, or
touch live processes.

V0 forbidden planner tools:

- write/edit tools;
- command execution tools;
- process lifecycle tools that can alter running commands;
- network, package install, shell, and credential access;
- `finish` or any control tool that can mutate lane state.

Every read must be recorded with path/ref, byte count, digest when available,
and reason.

### Planner Loop Dispatch Semantics

`run_finish_verifier_planner_loop(...)` is a provider-tool loop, not a
single-shot JSON call. It starts a planner-only provider session for one finish
call. The planner session may keep its own planner `previous_response_id` inside
that invocation, but it must not read, write, or update the implementer's
provider session state.

Loop behavior:

```text
build planner request
  -> planner provider turn with read-only tool specs
  -> controller intercepts tool calls
       allowed read tool -> execute through PlannerReadOnlyDispatcher
       forbidden tool -> do not execute, record planner_forbidden_tool
  -> append bounded tool output to planner transcript
  -> repeat until JSON plan, no_plan, max_turns, timeout, or forbidden tool
  -> write finish_verifier_planner_decisions row
```

Allowed dispatch table:

```text
inspect_dir  -> read-only directory listing under allowed roots
read_file    -> bounded file/window read under allowed roots
search_text  -> bounded search under allowed roots
glob         -> bounded path enumeration under allowed roots
```

Forbidden-tool interception is controller-side. A forbidden call is not executed
and produces a planner-loop result with `status="rejected"`,
`blockers=("planner_forbidden_tool",)`, a transcript item describing the
rejection, and an artifact record naming the attempted tool. The harness may
still consider observable auto fallback after such a planner rejection, but the
fallback record must carry `planner_forbidden_tool`.

Cap enforcement is also controller-side. Exceeding file, byte, search, turn, or
wall-clock caps stops the planner loop and records stable blockers such as
`planner_read_cap_exceeded`, `planner_turn_cap_exceeded`, or
`planner_timeout`.

### Response Schema

The planner returns one JSON object. The controller records the raw object
before coercion.

```json
{
  "schema_version": 1,
  "component": "FinishVerifierPlannerLoop",
  "status": "selected",
  "command": "node vm.js",
  "cwd": ".",
  "confidence": "medium",
  "rationale": "bounded rationale for why this command checks the external task outcome",
  "checks": [
    {
      "kind": "runtime_artifact",
      "target": "/tmp/frame.bmp",
      "why": "source or verifier failure indicates this is the verifier-visible artifact"
    }
  ],
  "source_refs": [
    {"kind": "task_text", "ref": "task.description"},
    {"kind": "file_read", "path": "doomgeneric/doomgeneric_img.c", "digest": "sha256:..."},
    {"kind": "recent_output", "ref": "tool_result:run_command:17"}
  ],
  "read_summary": {
    "turn_count": 2,
    "file_reads": [
      {"path": "vm.js", "bytes": 12000, "digest": "sha256:..."}
    ],
    "searches": [
      {"pattern": "frame.bmp", "matches": 3}
    ]
  },
  "observability": {
    "planner_model": "gpt-5.5",
    "request_hash": "sha256:...",
    "planner_transcript_ref": "finish-verifier-planner/transcript-finish-1.jsonl"
  }
}
```

Allowed `status` values:

- `selected`: one candidate command is present.
- `no_plan`: the planner found no safe verifier command.
- `rejected`: the planner returned a raw command plan, but controller coercion
  or validation rejected it.
- `error`: controller-recorded status when the planner provider or loop fails.
- `timed_out`: controller-recorded status when the planner exceeds its budget.

The controller coerces only `selected` responses into the harness-local carrier:

```python
_NativeFinishVerifierPlan(
    command=response["command"],
    cwd=response.get("cwd", "."),
    source="finish_verifier_planner",
    reason=response.get("rationale", ""),
    confidence=response.get("confidence", ""),
    raw=response,
)
```

That `_NativeFinishVerifierPlan` is the value carried in
`FinishVerifierPlannerLoopResult.plan`. It is not converted into
`FinishCloseoutCommand` in the planner response path. The only
`FinishCloseoutCommand` conversion happens later, when the harness assembles the
native finish-gate request or calls pure `native_finish_gate.py` helpers.

Coercion does not imply dispatch. The native finish gate or command validator
still rejects unsafe, malformed, out-of-root, or disallowed commands before
execution.

The planner response does not carry dispatch timeout authority. The harness
derives the closeout timeout from the existing final-verifier closeout budget
and policy caps. If a later response includes `timeout_seconds`, v0 records it
in `raw_plan` only and ignores it for dispatch.

V0 accepts exactly one raw plan object per invocation. `rejected_plans` in
observer artifacts means rejected planner-loop attempts over time, not multiple
candidate alternatives in one model response. If the model returns an array of
candidates or an object whose meaning is "choose among these," coercion rejects
the raw plan as `planner_plan_not_single_command`.

## 4. Ranking And Fallback Policy

### Rank 1: Configured Verifier

Configured verifier remains highest precedence when explicitly provided through
lane config, task contract, or a task/profile-controlled source marked as
`configured_verifier`.

Rules:

- do not invoke the planner on the hot path when a configured verifier exists;
- validate command safety/provenance before dispatch;
- execute through the normal runtime;
- if exit code is `0`, native finish gate completes;
- if nonzero, timeout, unsafe, or missing, native finish gate blocks;
- task-contract obligations remain diagnostic after exit `0`.

Configured verifier can still be too weak. That is a task/profile quality issue,
not a reason to demote configured verifier behind planner v0.

### Rank 2: FinishVerifierPlannerLoop

Planner loop is the primary command-quality path when no configured verifier is
present.

Planner is eligible when:

- native finish closeout is allowed;
- there is a latest relevant mutation without a later trusted verifier;
- no rank-1 configured verifier is available;
- read-only tool budget and model budget remain;
- `lane_config.experimental_finish_verifier_planner` is true.

V0 reuses the existing `experimental_finish_verifier_planner` flag. It does not
introduce a new public feature flag. Because the flag is already experimental,
the migration impact is that enabled runs move from the current single-shot
compact planner spike to the bounded read-only loop. Additional caps may use
new optional config keys such as `finish_verifier_planner_max_turns`, but they
do not change the enablement flag.

Planner output may be rejected before dispatch for stable reasons such as:

- empty or malformed plan;
- command safety violation;
- cwd outside allowed roots;
- no task/source/recent-output subject link;
- planner exceeded read or turn budget;
- planner tried to call a forbidden tool;
- no command selected.

Planner rejection does not finish or block by itself. It only determines whether
rank 3 fallback may be considered.

### Rank 3: Auto-Detected Fallback

Auto-detected verifier remains a later fallback. It must be deterministic and
derived from task/run metadata, not model finish prose and not arbitrary prior
successful commands.

Auto fallback may run only when:

- rank 1 is absent;
- planner is disabled, unavailable, timed out, returned no plan, or had its plan
  rejected;
- fallback command source and detector reason are recorded;
- fallback record carries the planner status and rejection/failure reason.

Fallback must be observable:

```json
{
  "selected_source": "auto_detected_verifier",
  "fallback_after_finish_verifier_planner": {
    "planner_status": "rejected",
    "planner_reject_reason": "planner selected only source-existence checks",
    "planner_record_id": "finish-verifier-planner:finish-1:1",
    "fallback_source": "auto_detected_verifier",
    "fallback_reason": "terminal-bench task metadata supplied auto_verify_command"
  }
}
```

Auto fallback must not silently hide planner rejection in metrics, proof
manifest, native finish-gate decisions, or provider-visible summaries.

### Explicitly Excluded Authority

`recent_successful_verifier` must not reappear as a command source or finish
authority. Prior successful commands can appear in `recent_command_outputs` and
can inform the planner, but the selected closeout command must still come from a
configured verifier, planner loop, or deterministic auto-detected fallback.

## 5. Safety Model

### Read-Only Planner

The planner loop is read-only by construction:

- separate provider session from the implementer;
- no access to implementer `previous_response_id`;
- explicit tool allowlist containing only read-only tools;
- file roots, file counts, byte counts, search counts, and turn counts are
  bounded;
- all reads are recorded in sidecars;
- planner cannot write files, execute commands, mutate active process state, or
  call `finish`;
- any forbidden tool attempt aborts the planner and records
  `planner_forbidden_tool`.

### Bounded Loop

Recommended v0 defaults:

- maximum planner turns: 3;
- maximum wall time: 30 seconds or less, capped by remaining closeout budget;
- maximum file reads: 12;
- maximum total read bytes: 120 KB;
- maximum search calls: 8;
- maximum raw response size: bounded before coercion;
- maximum one selected command.

When the budget is exhausted, the component returns `timed_out` and the harness
may proceed to observable auto fallback if available.

### Command Safety Validation

The controller validates planner commands before dispatch using one canonical
dispatch validator path. V0 should not keep `_finish_verifier_command_safety(...)`
and `native_finish_gate.validate_closeout_command(...)` as divergent authorities.

Implementation decision:

- `native_finish_gate.validate_closeout_command(...)` is the canonical
  pre-dispatch validator for closeout commands. If the current helper cannot
  express source-aware planner policy, refactor that helper or add a
  native-finish-gate-owned wrapper; do not preserve a separate harness regex
  authority.
- The planner loop may do JSON-shape coercion before that call, but it must not
  independently allow a command that the canonical validator would reject.
- Weak assertion rejection is planner-source-specific command-quality policy.
  Planner-selected commands such as `test -f vm.js`, `test -s /app/vm.js`, or
  `[ -f output ]` are rejected as `planner_command_weak_assertion` unless a
  future explicit design expands planner evidence semantics.
- Universal no-op/self-pass assertions such as `test 1 = 1`, `true`, `exit 0`,
  `echo acceptance: pass`, or equivalent are rejected for every source.
- Explicit configured verifier rank 1 is not demoted because it looks weak; it
  remains rank 1 unless it violates universal safety/provenance rules. This
  preserves configured-verifier authority while making planner-generated weak
  checks unable to become the rank-2 fix.
- Auto-detected fallback remains observable rank 3. If it is weak but selected
  by deterministic metadata, that weakness is recorded as fallback provenance,
  not hidden by planner metrics.

Existing planner spike tests that use planner-returned `test -f vm.js` as a
successful plan should migrate to a stronger local fixture command, or become
configured-verifier tests when the test is explicitly about rank-1 authority.

Validator checks:

- exactly one command;
- non-empty command;
- cwd is inside the allowed workspace/verifier roots;
- no `true`, `:`, `exit 0`, `test 1 = 1`, or equivalent no-op success;
- no `echo`, `printf`, or self-acceptance marker command;
- no command chains, shell fallbacks that hide failure, pipes that mask exit
  status, redirection, backgrounding, or daemonization;
- no source mutation commands, package install, network fetch, privilege
  escalation, credential reads, or secret markers;
- no inline evaluator programs that synthesize pass status;
- command subject must be grounded in task text, task_contract, recent command
  output, external verifier failure, or files the planner read;
- broad project test commands are allowed only when they are the best available
  task-relevant verifier and are recorded as such; they are not treated as
  stronger than a configured verifier.

This is safety validation, not a second completion gate. Once a command is
accepted for dispatch and exits `0`, task-contract obligations do not veto
finish.

### No Task-Specific Heuristics

The primary fix is not a rule like "reject `node vm.js`" or "require
`/tmp/frame.bmp` for Doom." The planner may discover those facts from task text,
source files, recent output, or external verifier failure, and then choose a
better command. The code should enforce generic properties: read-only planning,
source grounding, command safety, source precedence, bounded budgets, and
observability.

## 6. Observability Artifacts

Preserve the existing artifact and manifest names. V0 extends the current
`finish_verifier_planner_decisions.jsonl` row shape instead of introducing a
second top-level `finish_verifier_planner_loop.jsonl` source of truth.

```text
finish_verifier_planner_decisions.jsonl
finish-verifier-planner/
  request-<finish_call_id>.json
  transcript-<finish_call_id>.jsonl
  raw-plan-<finish_call_id>.json
```

The existing proof-manifest fields remain:

```text
finish_verifier_planner_decisions_ref
finish_verifier_planner_decisions_sha256
metrics.finish_verifier_planner_decisions
```

New loop counters should be nested under
`metrics.finish_verifier_planner_decisions` or use the existing
`finish_verifier_planner_*` prefix. Do not emit both
`finish_verifier_planner_decisions` and `finish_verifier_planner_loop` as
independent authoritative artifacts.

One JSONL row should represent one planner-loop attempt:

```json
{
  "schema_version": 1,
  "record_id": "finish-verifier-planner:attempt:finish-1:1",
  "lane_attempt_id": "attempt",
  "turn_id": "turn-7",
  "finish_call_id": "finish-1",
  "transcript_hash_before_plan": "sha256:...",
  "compact_sidecar_digest_hash": "sha256:...",
  "request_ref": "finish-verifier-planner/request-finish-1.json",
  "request_hash": "sha256:...",
  "planner": {
    "model": "gpt-5.5",
    "separate_agent": true,
    "read_only": true,
    "max_turns": 3,
    "turn_count": 2,
    "timed_out": false
  },
  "read_observation": {
    "file_reads": [
      {"path": "vm.js", "bytes": 12000, "sha256": "sha256:..."}
    ],
    "searches": [
      {"pattern": "frame.bmp", "match_count": 3}
    ],
    "forbidden_tool_attempts": []
  },
  "raw_plan_ref": "finish-verifier-planner/raw-plan-finish-1.json",
  "raw_plan_hash": "sha256:...",
  "raw_plan": {
    "status": "selected",
    "command": "node vm.js",
    "cwd": ".",
    "confidence": "medium"
  },
  "coercion": {
    "status": "accepted",
    "reject_reason": "",
    "reject_blockers": []
  },
  "rejected_plans": [
    {
      "command": "test -f vm.js",
      "reason": "planner raw plan rejected as weak assertion",
      "blockers": ["planner_command_weak_assertion"]
    }
  ],
  "selected_command": {
    "command": "node vm.js",
    "cwd": ".",
    "source": "finish_verifier_planner",
    "confidence": "medium",
    "source_ref": "finish-verifier-planner:attempt:finish-1:1"
  },
  "fallback": {
    "used": false,
    "source": "",
    "reason": ""
  },
  "execution": {
    "dispatched_by_harness": true,
    "tool_name": "run_command",
    "provider_call_id": "call-final-verifier-closeout-007",
    "command_run_id": "attempt:command:...",
    "status": "completed",
    "exit_code": 0,
    "timed_out": false,
    "duration_ms": 1200,
    "stdout_tail_ref": "implement-v2-exec://...",
    "stderr_tail_ref": "implement-v2-exec://..."
  },
  "finish_decision": {
    "native_finish_gate_decision_id": "native-finish-gate:...",
    "lane_status": "completed",
    "result": "allow",
    "reason": "trusted final verifier closeout exited 0"
  }
}
```

Required observability fields:

- planner transcript;
- raw plan;
- rejected plan attempts and reasons. In v0 there is at most one raw plan per
  invocation; the array exists so multiple finish attempts can be summarized
  consistently;
- selected command;
- fallback reason and source;
- turn count;
- file reads and searches;
- forbidden tool attempts;
- request hash and raw plan hash;
- final command execution result;
- native finish-gate decision id and result.

Proof manifest metrics should include:

- `finish_verifier_planner_invocation_count`;
- `finish_verifier_planner_selected_count`;
- `finish_verifier_planner_no_plan_count`;
- `finish_verifier_planner_rejected_count`;
- `finish_verifier_planner_error_count`;
- `finish_verifier_planner_timeout_count`;
- `finish_verifier_planner_file_read_count`;
- `finish_verifier_planner_forbidden_tool_count`;
- `finish_verifier_planner_dispatch_count`;
- `finish_verifier_planner_exit_zero_count`;
- `finish_verifier_planner_fallback_count`;
- `auto_detected_fallback_after_planner_reject_count`.

## 7. Implementation Phases With Close Gates

### Phase 0 - Contract Freeze

Work:

- land this design review;
- define request/response/artifact schemas in a doc or test fixture only;
- identify which existing helper names can be reused and which need extraction.

Close gate:

- reviewers agree that rank order, exit-0 finish authority, read-only planner
  limits, and fallback observability are unambiguous.

### Phase 1 - Component Scaffold Behind Feature Flag

Work:

- introduce `FinishVerifierPlannerLoop` as an internal `implement_v2` component;
- reuse the existing `experimental_finish_verifier_planner` flag and keep it
  disabled by default;
- support fake-provider planner responses;
- expose only read-only planner tools;
- add `run_finish_verifier_planner_loop(...)` with separate planner-session
  semantics and no implementer `previous_response_id` reuse.

Close gate:

- focused unit tests prove planner cannot write, execute, call finish, mutate
  process state, or reuse the implementer provider session.

### Phase 2 - Bounded Context And Read Selection

Work:

- build planner requests from task text, `task_contract`, latest mutation,
  recent command outputs, optional external verifier failure, and selected file
  candidates;
- enforce read caps and path roots;
- record read digests and transcript.

Close gate:

- snapshot tests prove request size, file-read count, byte caps, and redaction
  are stable;
- tests prove external verifier failure details appear when available and are
  omitted when unavailable.

### Phase 3 - Plan Coercion And Command Safety

Work:

- coerce planner JSON into `_NativeFinishVerifierPlan` inside the harness, then
  into `FinishCloseoutCommand` only at the native finish-gate boundary;
- make `native_finish_gate.validate_closeout_command(...)` the canonical
  dispatch validator, with planner-specific weak-assertion rejection layered as
  source-aware policy;
- cover cwd/root, no-op/self-pass, mutation, network, background,
  shell-composition, and forbidden inline evaluator shapes;
- record rejected plans and stable rejection blockers.

Close gate:

- unsafe command table is rejected before dispatch;
- rejected planner plans never reach the runtime;
- `recent_successful_verifier` does not appear as a command source or accepted
  plan provenance.

### Phase 4 - Harness Ranking And Fallback Integration

Work:

- wire rank order: configured verifier, planner loop, auto-detected fallback;
- do not invoke planner when configured verifier exists;
- record auto fallback only with planner status/reason attached;
- link selected planner command to closeout execution and finish decision.

Close gate:

- fake-provider tests cover configured precedence, planner selection, planner
  rejection plus observable auto fallback, no fallback available, nonzero
  command, timeout, and exit-0 completion.

### Phase 5 - Artifact And Fastcheck Coverage

Work:

- extend `finish_verifier_planner_decisions.jsonl` and related detail files;
- patch proof manifest with metrics and hashes;
- extend hot-path fastcheck/replay checks for artifact consistency.

Close gate:

- replay validates planner transcript refs, raw plan refs, selected command,
  fallback reason, final command result, and native finish-gate decision id;
- fastcheck fails if auto fallback hides planner rejection.

### Phase 6 - make-doom-for-mips Pre-Speed Proof

Work:

- run focused UT and replay/fastcheck first;
- run one same-shape pre-speed diagnostic with planner loop enabled;
- inspect whether the planner reads the relevant source/runtime surfaces and
  chooses a verifier command that checks the external outcome rather than only a
  surrogate internal condition.

Close gate:

- pre-speed artifact has valid `finish_verifier_planner_decisions` records, no
  forbidden tool attempts, a selected rank-2 command or clearly observable
  fallback, and a native finish-gate decision consistent with the command
  result;
- speed proof is allowed only after the pre-speed artifact shows the planner
  path is useful or fails in an actionable way.

### Phase 7 - Decide Whether Lane Promotion Is Needed

Work:

- compare planner-loop usefulness, latency, file-read volume, and failure
  classes across saved artifacts and one live proof slice.

Close gate:

- keep as component if the loop remains bounded and stateless;
- redesign as a lane only if it demonstrably needs independent memory, reentry,
  scheduling, long-running investigation, or cross-turn planner state.

## 8. Validation Plan

### Focused Unit Tests And Fake Provider

Target areas:

- `tests/test_native_finish_gate.py` for source precedence, safety validation,
  exit-0 authority, nonzero/timeout/missing/unsafe blocks, and diagnostic
  sidecar mode;
- `tests/test_native_tool_harness.py` for planner-loop request/response,
  configured verifier precedence, planner before auto fallback, observable
  rejection, artifact writing, native transcript pairing, and Codex hot-path
  `exec_command` surface;
- new focused tests for read-only planner tool restrictions, read caps, selected
  file reads, and forbidden tool attempts.

Example test families:

- configured verifier present: planner not called, exit `0` completes;
- no configured verifier, planner selects safe command: command executes, exit
  `0` completes;
- planner selects unsafe command: no dispatch, rejection recorded;
- planner selects weak assertion command such as `test -f vm.js`: no dispatch
  for planner source, rejection recorded as `planner_command_weak_assertion`;
- configured verifier uses the same command shape: rank-1 behavior is tested
  separately and is not silently converted into planner authority;
- planner returns no plan or a rejected plan and auto verifier exists: auto
  fallback runs, fallback record names planner rejection;
- planner returns no plan or a rejected plan and no fallback exists: finish
  blocks with missing final verifier command;
- planner tries write/exec/finish tool: abort planner, record
  `planner_forbidden_tool`;
- external verifier failure is included in request only when supplied by saved
  artifact/replay context.

### Replay And Fastcheck

Replay checks should validate:

- `finish_verifier_planner_decisions.jsonl` hashes are stable;
- planner transcript refs and raw plan refs exist;
- file-read paths are inside allowed roots;
- rejected plans do not dispatch;
- auto fallback never hides planner rejection;
- selected command source agrees across planner artifact, closeout call
  arguments, tool result, and `NativeFinishGateDecision`;
- exit `0` closeout still allows completion even when task-contract or typed
  obligation projection sidecars are warnings;
- nonzero/timeout/unsafe/missing command still blocks deterministically.

Fastcheck should add explicit failure codes for:

- `finish_verifier_planner_missing_artifact`;
- `finish_verifier_planner_fallback_unexplained`;
- `finish_verifier_planner_forbidden_tool`;
- `finish_verifier_planner_selected_command_mismatch`;
- `finish_verifier_planner_execution_result_missing`;
- `finish_verifier_planner_exit_zero_blocked_by_task_contract`;
- `recent_successful_verifier_source_reintroduced`.

### make-doom-for-mips Pre-Speed And Speed Proof

Pre-speed goal:

- prove that the planner-loop path can inspect the relevant source/runtime
  surfaces and select a stronger final verifier command than compact
  recent-output planning or auto fallback alone.

Pre-speed success signals:

- planner reads bounded source files relevant to runtime output and verifier
  artifact paths;
- planner's selected command is grounded in task/source/recent-output/external
  failure refs;
- selected command executes through normal runtime;
- final command result and native finish decision are linked in sidecars;
- if internal finish occurs and external verifier fails, the failure artifact
  clearly shows whether the selected command was weak, stale, or missing an
  external assertion.

Speed proof gate:

- run only after focused UT, replay, fastcheck, and one pre-speed diagnostic are
  green or produce an accepted known-risk decision.

### Regression Checks For Exit-0 Finish Authority

Required regressions:

- configured verifier exit `0` completes even when task-contract obligations
  would not all project into typed evidence;
- planner-selected verifier exit `0` completes under the same rule;
- auto-detected fallback exit `0` completes when selected, but fallback reason
  remains visible;
- `strict_verifier_evidence`, `oracle:*`, and finish-cited evidence alias
  warnings do not veto trusted exit `0`;
- nonzero, timeout, unsafe, missing-command, active-running-command, and
  unexpected source mutation still block.

## 9. Risks And Stop/Redesign Triggers

### Risks

- The planner can still select a weak command with plausible rationale.
- Read-only access can add latency or context volume if caps are loose.
- Auto fallback can make planner rejection look harmless unless artifacts make
  the fallback explicit.
- Configured verifier rank 1 can still be weak; planner v0 intentionally does
  not override explicit verifier configuration.
- A read-only planner loop may tempt hidden lane-like behavior without reentry
  semantics.
- Command-quality validation can drift into task-specific heuristics if the
  generic grounding rules are not enforced.

### Stop Or Redesign Triggers

Stop promotion and redesign if any of these occur:

- planner has any write, exec, process mutation, network, or finish capability;
- planner uses the implementer `previous_response_id` or mutates implementer
  provider continuity;
- planner requires more than 3 turns or regularly exceeds the configured wall
  budget;
- planner artifacts omit raw plan, rejected plans, read list, selected command,
  fallback reason, or final execution result;
- auto-detected fallback executes after planner rejection without a visible
  `fallback_after_finish_verifier_planner` record;
- `recent_successful_verifier` or arbitrary prior successful command matching is
  reintroduced as finish authority;
- command selection logic adds task-name, node-vm, Doom, MIPS, or frame-size
  hardcoding as the primary repair;
- a trusted exit-0 closeout is blocked by task-contract obligations or typed
  obligation projection;
- planner-selected exit-0 commands repeatedly produce internal completion while
  external verifier fails for the same missing assertion class;
- the component needs durable memory/reentry across sessions to work. That is
  the trigger to redesign it as a real lane, not to keep growing hidden state
  inside the harness.

## 10. Avoiding Context-Compression Drift

This design avoids context-compression drift by moving authority and provenance
out of prose and into durable, replayable records.

Hard anchors:

- source precedence is encoded as data:
  `configured_verifier > finish_verifier_planner > auto_detected_verifier`;
- exit-0 finish authority is encoded in `NativeFinishGateDecision`;
- task-contract obligations are diagnostic after trusted closeout pass;
- planner reads, raw plan, rejected plan records, selected command, fallback, and
  final execution result are written to sidecars;
- request hashes and transcript hashes link planner output to the exact finish
  call;
- fallback records preserve planner rejection instead of allowing later readers
  to infer that auto-detection was the primary path;
- `recent_successful_verifier` is explicitly excluded from command-source
  enums and fastcheck can reject its reintroduction.

Reentry rule:

```text
On context compression or handoff, recover finish-verifier state from sidecars:
  finish_verifier_planner_decisions.jsonl
  native_finish_gate_decisions.jsonl
  tool_results.jsonl
  proof-manifest metrics

Do not recover finish authority from summary prose, model rationale, or a prior
successful command.
```

The planner's own rationale is useful audit context, but the only hot authority
that survives compression is the selected command's harness-executed terminal
result and the native finish-gate decision that consumed it.
