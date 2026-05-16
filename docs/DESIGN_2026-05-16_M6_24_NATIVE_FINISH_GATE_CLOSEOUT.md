# Design 2026-05-16 - M6.24 Native Finish Gate Closeout

Status: design only.

Scope: extract native finish gate and final verifier closeout responsibility
from `src/mew/implement_lane/native_tool_harness.py` into a dedicated
`src/mew/implement_lane/native_finish_gate.py` module. This document does not
authorize source or test changes by itself. It also does not change
`finish_gate` or `task_contract` semantics; those are deliberately deferred.

Backward compatibility is not required. The project is pre-release, and this
redesign may delete, bypass, or demote the existing hot-path dependency on
`tool result -> typed evidence -> resolver obligation` when a trusted final
verifier closeout exits `0`.

## Decision

The harness remains the native loop owner. It owns provider turns, transcript
append order, tool dispatch outside finish, and loop stop behavior. A new native
finish gate owns the completion decision for a valid native `finish` call.

Final verifier closeout exit `0` is the primary hot completion signal. Typed
evidence, oracle obligations, resolver obligation coverage, and legacy
`strict_verifier_evidence` blockers become diagnostic/proof sidecar data for
this path. They must not be required before allowing completion after a trusted
final verifier closeout pass.

The hot closeout rule replaces the current typed-obligation resolver path:

```text
finish request
  -> final verifier command exists
  -> command source is allowed
  -> command passes closeout safety/provenance checks
  -> closeout command runs through the normal exec runtime
  -> terminal result has exit code 0 and did not time out
  -> native finish gate allows completion
```

`strict_verifier_evidence`, `oracle:*` obligations, typed evidence aliases, and
finish-cited evidence refs remain observable sidecar material, but they are not
required to allow the hot closeout path when the final verifier closeout itself
passed. The implementation should prefer deleting or bypassing hot resolver
blockers over preserving compatibility shims that can reproduce the SvsqcuQ
failure mode. The external Terminal-Bench verifier remains the final oracle
after mew exits.

## Problem

The recent `make-mips-interpreter` runs show that correct verifier/tool results
can exist without cleanly satisfying the completion resolver's obligation/ref
shape. That delays or blocks task completion for plumbing reasons rather than
because the closeout verifier failed.

Concrete artifacts:

- Old success:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-speed-proof-ts-codex-hot-path-20260515-135942/2026-05-15__13-59-43/make-mips-interpreter__YiztSTx`
  - External reward: `1`.
  - Internal lane status: `completed`.
  - `completion_resolver_decision_count`: `1`.
  - `final_verifier_closeout_count`: `1`.
  - The single resolver decision allowed completion with closeout refs for
    terminal, tool-run-record, command-run, and verifier-evidence sidecars from
    `call-final-verifier-closeout-036`.
  - Closeout command was `node vm.js`, exited `0`, and produced a 640 by 400
    32 bpp BMP observation.

- New pass but internally blocked:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-speed-proof-ts-codex-hot-path-20260516-022643/2026-05-16__02-26-44/make-mips-interpreter__SvsqcuQ`
  - External reward: `1`.
  - Internal lane status: `blocked`.
  - `completion_resolver_decision_count`: `14`.
  - `finish_gate_block_count`: `14`.
  - `final_verifier_closeout_count`: `2`; both deterministic closeout attempts
    failed before producing refs with `artifact rendered_frames has no path
    target`.
  - Correct command evidence existed outside the resolver's accepted ref shape:
    fresh `node vm.js` runs saved `/tmp/frame.bmp`, and frame checks reported
    `FRAME_DIMS=640x-400x32` / size `1024054`.
  - Resolver blockers repeated across finish attempts:
    `invalid_typed_evidence_ref`, `verifier_evidence_missing`,
    `strict_verifier_evidence`, and multiple `oracle:*` obligation ids.
  - The problem was completion plumbing: the successful task evidence did not
    map cleanly through the alias/ref/obligation path.

- New fail with a separate semantic issue:
  `proof-artifacts/terminal-bench/harbor-smoke/mew-make-mips-interpreter-speed-proof-ts-codex-hot-path-20260516-035201/2026-05-16__03-52-01/make-mips-interpreter__4zcjzxq`
  - External reward: `0`.
  - Internal lane status: `completed`.
  - The accepted internal evidence included `FRAME_BMP_OK=true` for a
    `320x-200x32` BMP of size `256054`.
  - This design does not solve the hidden-oracle semantic problem. It must
    preserve enough observer detail for a later semantic closeout design, while
    avoiding another alias-sprawl repair in this closeout-plumbing change.

## Current Responsibility Map

`native_tool_harness.py` currently owns too much finish-time behavior:

- provider-native loop execution and transcript item pairing;
- finish protocol validation and finish output construction;
- active command closeout before finish resolution;
- final verifier closeout command planning and dispatch;
- finish verifier planner request/coercion/safety checks;
- closeout context extraction from command results;
- compatibility translation into `CompletionResolverInput`;
- finish-gate blocker suppression when closeout refs are present;
- provider-visible finish block summaries.

`completion_resolver.py` is a pre-extracted semantic resolver:

- rejects raw transcript/tool payloads in resolver input;
- combines blockers, missing obligations, finish readiness, fresh verifier refs,
  closeout refs, unsafe blockers, and budget blockers;
- writes `resolver_decisions.jsonl` and proof-manifest refs;
- currently blocks when `verifier_required` is true and neither
  `fresh_verifier_refs` nor `closeout_refs` are populated.

`execution_evidence.py` owns structured evidence shapes:

- execution contracts, expected artifacts, command runs, tool run records,
  artifact evidence, verifier evidence, failure classification;
- typed acceptance shapes such as `OracleBundle`, `EvidenceEvent`,
  `FinishClaim`, and `DoneDecision`;
- `derive_verifier_evidence(...)` and `apply_finish_gate(...)` for structured
  evidence and diagnostic finish-gate records.

`exec_runtime.py` owns command execution and side-effect observation:

- `run_command`, `run_tests`, command polling/cancel/read output;
- command/result payload projection, output refs, source observer;
- artifact checks, verifier evidence derivation, structured finish gate records;
- it should not decide lane completion.

The main boundary bug is that the finish-time controller, typed evidence
checker, resolver adapter, and command provenance policy are all interleaved in
`native_tool_harness.py`.

## Proposed Module Boundary

Add `src/mew/implement_lane/native_finish_gate.py`.

The module owns:

- final verifier closeout command source selection;
- command provenance validation;
- active-command closeout handling needed before final verification;
- final verifier closeout dispatch through the provided runtime;
- hot-path completion decision;
- construction of finish output payload fields consumed by the harness;
- sidecar decision records for finish gate decisions;
- optional diagnostic projection into existing resolver/proof artifacts, if the
  implementation keeps those files for review tooling.

The module does not own:

- provider API calls or `previous_response_id`;
- request building;
- normal non-finish tool routing;
- WorkFrame or compact sidecar projection;
- source/test execution outside finish closeout;
- hidden task oracle semantics.

`native_tool_harness.py` becomes the caller:

```text
model finish_call
  -> harness validates finish protocol
  -> harness builds NativeFinishGateRequest
  -> native_finish_gate.evaluate_finish(...)
  -> harness appends closeout transcript items returned by the gate
  -> harness emits paired finish_output from the decision
  -> harness stops, continues, or returns to supervisor
```

`completion_resolver.py` is demoted out of the hot completion path. It may be
deleted, bypassed, or kept only as a diagnostic sidecar writer for proof
tooling. Its blockers must not override a `NativeFinishGateDecision` that
allowed completion from a trusted closeout exit `0`.

## Public API Sketch

The exact field names can move during implementation, but the public shapes
should stay close to this contract.

```python
FinishVerifierSource = Literal[
    "configured_verifier",
    "auto_detected_verifier",
    "finish_verifier_planner",
]

FinishGateStatus = Literal[
    "completed",
    "blocked_continue",
    "blocked_return",
]

FinishGateResult = Literal["allow", "block"]


@dataclass(frozen=True)
class NativeFinishGatePolicy:
    policy_version: str = "native-finish-gate-v1"
    allowed_sources: tuple[FinishVerifierSource, ...] = (
        "configured_verifier",
        "auto_detected_verifier",
        "finish_verifier_planner",
    )
    min_closeout_seconds: float = 5.0
    default_closeout_seconds: float = 60.0
    max_closeout_seconds: float = 3600.0
    allow_shell: bool = False
    require_no_unexpected_source_mutation: bool = True
    record_typed_evidence: bool = True
    typed_evidence_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"
    oracle_obligation_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"


@dataclass(frozen=True)
class FinishCloseoutCommand:
    command: str
    cwd: str = "."
    source: FinishVerifierSource = "configured_verifier"
    source_ref: str = ""
    reason: str = ""
    confidence: str = ""
    raw: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class NativeFinishGateRequest:
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    finish_arguments: dict[str, object]
    task_id: str = ""
    task_description: str = ""
    task_contract: dict[str, object] = field(default_factory=dict)
    lane_config: dict[str, object] = field(default_factory=dict)
    workspace: str = ""
    allowed_read_roots: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    latest_source_mutation: dict[str, object] = field(default_factory=dict)
    prior_tool_summary: tuple[dict[str, object], ...] = ()
    configured_command: FinishCloseoutCommand | None = None
    auto_detected_command: FinishCloseoutCommand | None = None
    planner_command: FinishCloseoutCommand | None = None
    remaining_wall_seconds: float | None = None


@dataclass(frozen=True)
class NativeFinishCloseoutResult:
    command: FinishCloseoutCommand | None
    call_item: object | None
    output_item: object | None
    tool_result: object | None
    status: Literal[
        "not_run",
        "completed_zero",
        "completed_nonzero",
        "timed_out",
        "unsafe",
        "missing_command",
        "active_command_running",
        "budget_insufficient",
        "runtime_error",
    ]
    exit_code: int | None = None
    timed_out: bool = False
    observed_unexpected_source_mutation: bool = False
    typed_evidence_projection_status: Literal[
        "not_attempted",
        "passed",
        "warning",
        "failed",
    ] = "not_attempted"
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class NativeFinishGateDecision:
    decision_id: str
    policy_version: str
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    lane_status: FinishGateStatus
    result: FinishGateResult
    closeout: NativeFinishCloseoutResult
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    transcript_items_to_append: tuple[object, ...] = ()
    finish_output_payload: dict[str, object] = field(default_factory=dict)
    diagnostic_resolver_record: dict[str, object] = field(default_factory=dict)
    reason: str = ""
```

Primary API:

```python
def evaluate_native_finish(
    request: NativeFinishGateRequest,
    *,
    policy: NativeFinishGatePolicy,
    exec_runtime: ImplementV2ManagedExecRuntime,
    active_command_finalizer: Callable[[float], tuple[object, ...]],
    planner: FinishVerifierPlanner | None = None,
) -> NativeFinishGateDecision:
    ...
```

The harness supplies runtime/finalizer callables; the finish gate uses them but
does not own the loop or provider.

## Closeout Command Provenance

Allowed command sources are closed and auditable.

1. Configured verifier.
   - Comes from `lane_config.verify_command` or `task_contract.verify_command`.
   - The command is controller/task supplied, not model supplied.
   - The command string and source key are recorded as `source_ref`.

2. Auto-detected verifier.
   - Comes from deterministic task/run metadata, such as the Terminal-Bench
     auto verifier recorded as `auto_verify_command: node vm.js`.
   - The detector must be deterministic and must write why it selected the
     command.
   - It must not infer a verifier from finish prose, assistant text, or an
     arbitrary prior command that happened to pass.

3. `finish_verifier_planner`.
   - Comes from the separate planner session described in
     `docs/DESIGN_2026-05-15_M6_24_FINISH_VERIFIER_PLANNER.md`.
   - The planner proposes one command. The native finish gate still validates
     and executes it. Planner rationale is never acceptance evidence.

Rejected commands include:

- `true`, `:`, `exit 0`, `test 1 = 1`, or equivalent no-op success commands;
- `echo`, `printf`, or self-acceptance marker commands such as
  `acceptance: pass`;
- source mutation commands, write redirection, package installation, network
  fetches, credentials, `sudo`, daemons, and backgrounding;
- command chains that hide failure behind unconditional success;
- model-authored finish evidence aliases as a command source;
- arbitrary successful commands such as `test -s /app/vm.js` unless they came
  from an allowed source and are itself the configured verifier, which should be
  rare and explicit.

This provenance rule is why the design does not bless the 4zcjzxq internal
acceptance path: that run's accepted `320x200` evidence was model-crafted
typed/prose verifier material, not a trusted native final closeout semantic
oracle.

## Completion Algorithm

Pseudo-code:

```python
def evaluate_native_finish(req, policy, exec_runtime, active_command_finalizer, planner):
    finish = normalize_finish_claim(req.finish_arguments)
    if finish.outcome not in {"completed"} or finish.task_done is False:
        return block_continue("finish_claim_not_completed")

    active = active_command_finalizer(active_closeout_budget(req, policy))
    if active_contains_still_running_command(active):
        return active_command_block(req, active)
    record_active_closeout_items(active)

    command = select_closeout_command(req, policy, planner)
    if command is None:
        return block_continue(
            "closeout_verifier_command_missing",
            missing=("final_verifier_closeout",),
        )

    provenance = validate_closeout_command(command, req, policy)
    if not provenance.allowed:
        return block_for_unsafe_or_invalid_command(provenance)

    budget = closeout_budget(req, policy)
    if budget < policy.min_closeout_seconds:
        return block_return(
            "closeout_verifier_budget_insufficient",
            missing=("final_verifier_closeout",),
        )

    closeout = run_closeout_command(command, budget, exec_runtime)
    record_closeout_transcript_items(closeout)
    record_typed_evidence_and_observer_sidecars(closeout)

    if closeout.status == "completed_zero" and not closeout.timed_out:
        if policy.require_no_unexpected_source_mutation and closeout.observed_unexpected_source_mutation:
            return block_continue("closeout_unexpected_source_mutation")
        return allow_completed(
            evidence_refs=closeout.evidence_refs,
            closeout_refs=closeout.closeout_refs,
            observer_refs=closeout.observer_refs,
        )

    if closeout.timed_out:
        return block_timeout(closeout, req)

    if closeout.exit_code not in (0, None):
        return block_continue("closeout_verifier_failed", refs=closeout.closeout_refs)

    return block_continue("closeout_verifier_not_terminal", refs=closeout.closeout_refs)
```

The important negative rule is:

```python
if closeout.exit_code == 0:
    do_not_require("strict_verifier_evidence")
    do_not_require("oracle:*")
    do_not_require("finish cited typed evidence aliases")
    do_not_require("resolver obligation coverage")
```

Those facts are still recorded. They are not hot-path blockers.

## Closeout Dispatch Invariant

The final verifier process must run before typed evidence or artifact projection
can fail the hot closeout path. This directly addresses SvsqcuQ, where
deterministic closeout attempts failed before process execution with
`artifact rendered_frames has no path target`.

Implementation requirements:

- Build the runtime call with a minimal closeout execution contract:
  verifier role, expected exit `0`, command provenance, cwd, timeout, and
  source-observer configuration.
- Do not copy model-declared artifact obligations or compiled task-contract
  artifact entries into the pre-dispatch execution contract if they can cause
  pre-spawn validation errors.
- Run the final verifier command first.
- After the terminal process result exists, run typed evidence, artifact
  evidence, oracle coverage, and resolver/proof projections in best-effort
  observer mode.
- Catch projection exceptions such as missing artifact path targets and record
  them as `typed_evidence_projection_status="warning"` plus stable warning
  codes.
- If the process result is `completed_zero`, projection warnings do not affect
  hot completion.
- If the process result is nonzero, timed out, killed, interrupted, or still
  active, typed evidence cannot rescue it.

This intentionally deletes the old dependency order where the final verifier
closeout could be blocked before the actual command ran because artifact or
oracle projection was malformed.

## Evidence Sidecar Without Hot-Path Blocking

The finish gate still preserves typed evidence because it is useful for replay,
proof review, and later semantic validation.

On every finish closeout attempt, write or update:

- `tool_results.jsonl` entry from the normal runtime;
- command output refs under `.mew/implement-v2/...`;
- command-run and tool-run-record evidence refs when available;
- verifier-evidence refs when `exec_runtime` can derive them;
- artifact-evidence refs when the command contract has valid artifact targets;
- `native_evidence_observation` summary;
- proof manifest refs and hashes;
- optional `resolver_decisions.jsonl` diagnostic record, if retained;
- a new finish-gate decision sidecar, for example
  `native_finish_gate_decisions.jsonl`.

If typed evidence derivation fails because an artifact id has no path target or
because a finish cited an alias that the evidence index cannot resolve, the
sidecar records a warning such as `typed_evidence_projection_failed`. It does
not convert a passing final verifier closeout into
`invalid_typed_evidence_ref`, `verifier_evidence_missing`,
`strict_verifier_evidence`, `missing_typed_obligation`, or `oracle:*` blockers.

This makes SvsqcuQ debuggable without forcing the model through repeated finish
attempts to satisfy alias shapes.

## Non-Happy Paths

Exit nonzero:

- Do not allow completion.
- Return `blocked_continue` with `closeout_verifier_failed`.
- Include command refs, exit code, stderr/stdout tails, and derived failure
  classification when available.
- The next model turn may repair from the concrete verifier failure.

Missing command:

- Do not allow completion.
- Return `blocked_continue` with `closeout_verifier_command_missing`.
- Do not fall back to `strict_verifier_evidence` or model prose.
- If this came from a bad task profile, the observer should identify which
  source keys were checked.

Unsafe command:

- Do not dispatch the command.
- Return `blocked_continue` for planner/model-recoverable rejection.
- Return `blocked_return` only when the configured task/profile verifier itself
  is unsafe and needs supervisor/config repair.
- Record the rejected source and validation reason.

Budget or timeout:

- If there is insufficient budget to start the verifier, return
  `blocked_return` with `closeout_verifier_budget_insufficient`.
- If the verifier times out and there is still enough wall budget for a repair
  turn, return `blocked_continue` with `closeout_verifier_timeout`.
- If timeout consumes the remaining safe wall budget, return `blocked_return`.
- Never allow completion from a yielded, timed-out, killed, orphaned, or
  interrupted closeout command.

Active command still running:

- The finish gate first asks the runtime to finalize active commands within a
  bounded active-closeout budget.
- If active commands reach terminal status, their results become prior evidence
  before selecting/running the final verifier.
- If any active command is still running/yielded, do not run the final verifier
  over moving state.
- Return `blocked_continue` when the model can poll/cancel/finish later, or
  `blocked_return` when the wall budget is no longer safe.

Unexpected source mutation during closeout:

- The configured final verifier should be non-mutating except for expected
  runtime artifacts, caches, and task outputs.
- If the runtime source observer sees source-tree mutation during closeout,
  block with `closeout_unexpected_source_mutation` unless the task profile
  explicitly classifies that mutation as benign.

## Transcript And Provider Continuity

`previous_response_id` belongs to provider model continuity, not to controller
closeout. It is deliberately not part of `NativeFinishGateRequest`. The native
finish gate must not advance or replace the implementer provider session's
`previous_response_id`.

Transcript rules:

- The model-emitted `finish_call` remains a provider-native item.
- Controller-dispatched final verifier closeout is represented as synthetic
  native transcript items with deterministic ids, for example
  `call-final-verifier-closeout-NNN`.
- The closeout call/output items carry `response_id` values that identify the
  controller closeout event, but those ids are not sent as the next
  `previous_response_id` for the model.
- The paired `finish_output` contains the finish gate decision and bounded
  model-visible summary.
- If completion is allowed, there is no next provider turn.
- If blocked, the next provider request includes the transcript window and
  compact sidecar refs needed to inspect the closeout result, not full raw
  stdout/stderr.

Ordering should stay deterministic:

```text
provider finish_call
controller closeout function_call
controller closeout function_call_output
paired finish_output with NativeFinishGateDecision
```

The proof sidecars should link `finish_call_id`, closeout `call_id`,
`finish_output_call_id`, transcript hash before decision, and compact sidecar
digest hash.

## Phased Implementation Plan

Phase 1 - New finish-gate module and public contract.

- Add `native_finish_gate.py` with dataclasses, pure command-source selection,
  and decision serialization.
- Add focused unit tests for policy defaults, command source precedence,
  decision serialization, and finish output payload shape.
- State in code comments and tests that backward compatibility with legacy
  resolver hot blockers is not a goal.
- Review boundary: no live behavior switch yet, but the new API must already
  encode `diagnostic_sidecar` typed-evidence/oracle modes.
- Commit boundary: module skeleton, dataclasses, pure policy functions, tests.

Phase 2 - Provenance validator.

- Implement closed command source rules for configured, auto-detected, and
  planner commands.
- Reject arbitrary self-pass/no-op commands before dispatch.
- Add tests for unsafe configured command, unsafe planner command, and accepted
  `node vm.js` from configured/auto-detected sources.
- Commit boundary: validator and tests only.

Phase 3 - Dispatch isolation before evidence projection.

- Move final verifier closeout dispatch into `native_finish_gate.py`.
- Build a minimal verifier execution contract that cannot fail pre-dispatch
  because of malformed artifact targets or oracle obligations.
- Run typed evidence, artifact evidence, oracle coverage, resolver/proof
  projection, and observer summarization after the terminal process result.
- Catch projection failures and record warning codes without changing
  `completed_zero` hot allow.
- Commit boundary: SvsqcuQ regression proving `artifact rendered_frames has no
  path target` cannot prevent dispatch of the trusted verifier command.

Phase 4 - Hot closeout decision switch.

- Make `NativeFinishGateDecision` the completion authority.
- On closeout exit `0`, allow completion even when typed evidence aliases,
  `strict_verifier_evidence`, or `oracle:*` obligations do not resolve.
- Delete or bypass the legacy resolver/finish-gate blocker path for trusted
  closeout pass. If resolver artifacts are still written, they are diagnostic
  only and cannot override `NativeFinishGateDecision`.
- Commit boundary: hot decision switch plus SvsqcuQ/YiztSTx regression tests.

Phase 5 - Sidecar and fastcheck.

- Add `native_finish_gate_decisions.jsonl`.
- Extend proof manifest and hot-path fastcheck to verify finish-gate decision
  refs, transcript hashes, and closeout refs.
- Ensure typed evidence projection warnings are visible but non-blocking for
  hot closeout pass.
- Add a projection-warning fastcheck fixture so alias/path-target regressions
  remain visible even though they no longer block hot completion.
- Commit boundary: artifact contract and fastcheck coverage.

Phase 6 - Live proof gate.

- Run focused UT and saved-artifact fastchecks first.
- Run one pre-speed same-shape diagnostic before speed proof.
- Run one speed-proof only after the pre-speed artifact shows that completion
  occurs from the first valid final verifier closeout and no repeated
  evidence-alias finish loop remains.
- Do not run proof-5 until the speed proof confirms the closeout plumbing.

## Test Plan

Focused unit tests:

- `NativeFinishGatePolicy` default policy is closed and stable.
- Configured verifier command is selected before auto-detected or planner.
- Auto-detected verifier is accepted only with deterministic detector metadata.
- Planner command is accepted only after source and safety validation.
- `echo acceptance: pass`, `true`, `exit 0`, `printf`, redirection, mutation,
  network, backgrounding, and arbitrary pass-marker commands are rejected.
- Missing verifier command blocks with `closeout_verifier_command_missing`.
- Nonzero verifier blocks with `closeout_verifier_failed`.
- Timeout and budget cases choose `blocked_continue` or `blocked_return`
  according to remaining wall budget.
- Active running command prevents final verifier dispatch until terminal.
- Typed evidence or artifact projection exceptions after closeout are converted
  to warnings and cannot change `completed_zero` into a block.
- Malformed artifact obligations such as an artifact id with no path target do
  not prevent the final verifier command from being dispatched.
- Passing closeout with exit `0` allows completion even when typed evidence
  projection reports `invalid_typed_evidence_ref`, missing
  `strict_verifier_evidence`, or unresolved `oracle:*` obligations.
- Legacy `CompletionResolver` blockers cannot override an allowed
  `NativeFinishGateDecision`.
- Typed evidence projection warnings are written to observer detail.

Regression fixtures:

- YiztSTx fixture: preserve one-decision completion after
  `call-final-verifier-closeout-036` exits `0`.
- SvsqcuQ fixture: reproduce the old 14 blocked decisions and assert the new
  gate dispatches the trusted configured/auto-detected `node vm.js` closeout
  even when artifact projection would previously raise `artifact rendered_frames
  has no path target`.
- SvsqcuQ fixture: assert the new gate completes when that trusted closeout
  exits `0`, without requiring finish-cited evidence alias repair, resolver
  obligation coverage, `strict_verifier_evidence`, or `oracle:*` coverage.
- SvsqcuQ fixture should also assert the observed 640 by 400 32 bpp details
  remain in sidecars.
- 4zcjzxq fixture: assert the run remains visible as a semantic mismatch
  example. Do not make this design claim to detect the hidden oracle failure;
  assert only that model-crafted `acceptance: pass` evidence is not treated as
  an allowed final closeout source.

Fastcheck/pre-speed/speed proof plan:

1. Run focused tests for `native_finish_gate.py`, `native_tool_harness.py`,
   `completion_resolver.py`, `execution_evidence.py`, and
   `hot_path_fastcheck.py`.
2. Run `scripts/check_implement_v2_hot_path.py` against the latest saved native
   artifact and the SvsqcuQ/YiztSTx fixtures.
3. Run a pre-speed same-shape `make-mips-interpreter` diagnostic with the
   `ts-codex-hot-path` profile.
4. Inspect that the pre-speed artifact has valid pairing, finish-gate decision
   refs, a trusted closeout command source, closeout exit `0`, and no repeated
   alias/obligation finish loop after the first valid closeout.
5. Only then run one `speed-proof`.
6. Treat external Terminal-Bench reward as final; if reward fails with internal
   completion, classify that as a later hidden-oracle/semantic closeout issue,
   not a regression in this plumbing design.

## Risks

- This deliberately trades away one layer of defense in depth on the hot path:
  typed evidence/oracle coverage no longer gets to veto a trusted verifier
  closeout exit `0`. The mitigation is strict command provenance, not resolver
  alias repair.
- A configured verifier can be too weak. That is more visible after this design
  because the configured verifier becomes the primary hot completion signal.
  External Terminal-Bench reward remains the final oracle and must be treated
  as authoritative when it disagrees with internal completion.
- If auto-detection is too permissive, it can recreate the 4zcjzxq problem.
  This is why auto-detected source must be deterministic task/run metadata, not
  model prose or arbitrary passing commands.
- Making typed evidence non-blocking on the hot closeout path may hide alias
  regressions unless observer warnings and fastcheck explicitly track them.
- Projection-warning fastchecks and sidecar diagnostics must stay mandatory so
  malformed artifact targets, invalid evidence refs, and unresolved
  obligations remain visible after they stop blocking completion.
- Keeping resolver diagnostic records during migration may confuse readers if
  they resemble the old authority path. If retained, artifact names and
  manifests must clearly mark them diagnostic and lower authority than
  `NativeFinishGateDecision`.

## Non-Goals

- Do not solve the 4zcjzxq hidden oracle semantic issue in this design.
- Do not add obligation alias sprawl to make every model-authored ref string
  acceptable.
- Do not make WorkFrame required for closeout.
- Do not infer task correctness from finish prose.
- Do not preserve the old hot closeout dependency on typed evidence aliases,
  `strict_verifier_evidence`, `oracle:*`, or resolver obligation coverage.
- Do not move provider request building or `previous_response_id` management
  into the finish gate.
- Do not replace the external Terminal-Bench verifier.

## Close Gate

This design is implemented when all of these are true:

1. `native_finish_gate.py` owns final verifier closeout command provenance,
   closeout dispatch coordination, and the hot completion decision.
2. `native_tool_harness.py` no longer contains the native finish closeout
   decision logic; it only validates protocol, calls the finish gate, appends
   returned transcript items, and applies the returned lane status.
3. A configured or auto-detected `node vm.js` closeout that exits `0` allows
   completion without requiring `strict_verifier_evidence`, `oracle:*`
   obligation coverage, or finish-cited typed evidence aliases.
4. Typed evidence, artifact evidence, oracle coverage, and resolver projection
   happen after command execution and cannot prevent dispatch of the final
   verifier process.
5. Legacy `CompletionResolver`/finish-gate blockers are deleted, bypassed, or
   diagnostic-only for trusted closeout pass; they cannot override
   `NativeFinishGateDecision`.
6. Unsafe/no-op/self-pass commands are rejected before dispatch.
7. Missing command, nonzero exit, timeout, insufficient budget, and active
   command still running all produce deterministic block decisions and sidecar
   reasons.
8. Typed evidence, verifier evidence, artifact evidence, optional resolver
   diagnostic records, transcript refs, and observer details are still written
   when available, and projection failures are warnings rather than hot
   blockers.
9. YiztSTx remains a one-decision internal completion.
10. SvsqcuQ no longer repeats finish attempts due to
   `invalid_typed_evidence_ref`, `verifier_evidence_missing`,
   `strict_verifier_evidence`, `oracle:*` mismatch, or artifact path-target
   projection errors once trusted closeout exits `0`.
11. 4zcjzxq remains classified as a separate semantic-oracle risk; this design
   does not claim to repair it.
12. Focused UT, native hot-path fastcheck, one pre-speed diagnostic, and one
    speed proof pass the review gate described above.
