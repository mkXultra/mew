# Design 2026-05-03 - M6.24 Execution Contract

Status: v2 design proposal for review.

Scope: move M6.24 command semantics away from task-semantic shell-string
classification and toward typed execution contracts plus generic command
lifecycle. This is a design document only and does not authorize source edits by
itself.

## Inputs Reviewed

- `docs/DESIGN_2026-05-01_M6_24_LONG_BUILD_SUBSTRATE.md`
- `docs/DESIGN_2026-05-02_M6_24_LONG_COMMAND_CONTINUATION.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md`
- `docs/REVIEW_2026-05-02_CODEX_CLI_LONG_BUILD_CONTINUATION_PATTERNS.md`
- `docs/REVIEW_2026-05-02_CLAUDE_CODE_LONG_BUILD_CONTINUATION_PATTERNS.md`
- `src/mew/work_loop.py`
- `src/mew/work_session.py`
- `src/mew/commands.py`
- `src/mew/long_build_substrate.py`
- `src/mew/acceptance_evidence.py`
- `src/mew/toolbox.py`

## Problem

Mew currently asks the model for `run_command.command` and `run_tests.command`
plus a few thin operational fields. The model can output objects, but the action
schema gives it no durable place to say that a command is source authority
proof, dependency generation, final artifact proof, default runtime smoke, or a
managed continuation candidate. The model therefore packs command semantics into
shell strings, echo markers, command order, and clipped output. Reducers later
recover that meaning through regex and helper classifiers in
`long_build_substrate.py` and `acceptance_evidence.py`.

That is structurally weak:

- `command` is transport. It is the payload passed to a shell or argv runner,
  the text shown to users, and the surface inspected for permission/safety. It
  is not a reliable task contract.
- Compound shell commands can span source acquisition, configure, build,
  runtime install, and smoke proof. A single inferred stage from regex cannot
  represent that lifecycle safely.
- Shell markers can be spoofed or can satisfy the classifier without satisfying
  the task. More spoof guards reduce some risk but also expand the classifier.
- Lifecycle and task semantics are mixed. Running/yielded/completed/failed is
  generic process state; source authority/default smoke/final artifact is task
  proof state.
- The M6.24 repair history shows classifier accretion: source authority,
  dependency strategy, runtime link, closeout, and budget-routing repairs keep
  adding command-shape detectors.

The target is not a larger shell classifier. The target is a typed command
contract, generic lifecycle state for command execution, and reducers that
consume typed evidence first.

## Controller Trigger

`docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md` says to keep narrow
budget routing until specific triggers fire. This design proceeds only because
the controller gate is now considered fired by the following documented M6.24
signals:

- Repeated false negatives: the current controller history records multiple
  cases where real long work did not receive the right managed lifecycle or
  recovery semantics. Examples include the continuation speed rerun where
  `long_command_runs=[]`, the managed-dispatch repair for production long
  commands, and the later `compound_long_command_budget_not_attached` gap in
  `docs/M6_24_GAP_IMPROVEMENT_LOOP.md` and `docs/M6_24_DECISION_LEDGER.md`.
- Classifier accretion: the ledger records successive detector/reducer repairs
  for source authority, external/prebuilt branches, dependency generation,
  runtime-link/default smoke, source-channel retry, and closeout projection.
  This matches the generic-managed-exec decision's warning that repeated
  classifier additions should trigger a deliberate design slice.
- Lifecycle gaps dominate the selected local repair chain: recent selected gaps
  include missing continuation dispatch, nonterminal handoff, compound budget
  attachment, killed/failed managed status, and timeout-vs-non-timeout recovery
  inversion. Those are command lifecycle and ownership issues, not benchmark
  recipes.

If reviewers decide these references are insufficient to declare the trigger
fired, the controller must explicitly override
`docs/M6_24_GENERIC_MANAGED_EXEC_DECISION_2026-05-03.md` before implementation.
Without either fired-trigger acceptance or explicit override, this design should
remain a proposal and must not drive code changes.

## Reference Direction

Codex CLI and Claude Code do not appear to use task-semantic shell classifiers
for build/source/smoke/runtime-link lifecycle decisions. Their transferable
concepts are:

- generic command identity and lifecycle;
- running/yielded/backgrounded vs terminal status;
- durable output owners/refs plus bounded prompt-visible output;
- poll/finalize/kill semantics;
- terminal-only proof boundaries;
- permission/safety parsing separate from task semantics;
- tool contracts that carry structured intent.

Mew should adopt those concepts, not clone either implementation. String parsing
remains for shell execution setup, approval/sandbox/display, redaction, spoof
validation, and fallback. It must not remain the primary source of truth for
stage, proof role, source authority, runtime smoke, continuation, timeout
recovery, or closeout.

## Core Model

The model has four layers.

`command` is payload:

- shell string for `run_command`;
- argv-like verifier string for `run_tests`;
- user-visible audit text;
- permission/safety/display input.

`execution_contract` / `CommandExecutionContract` is semantics:

- purpose, stage, proof role, acceptance kind;
- expected artifacts and declared targets;
- source authority refs;
- continuation/background policy;
- risk class and notes.

`CommandRun` is generic lifecycle:

- run id, tool call id, process/session identity;
- lifecycle status;
- timeout/yield/background policy;
- output refs;
- terminal result;
- typed resume identity.

`CommandEvidence` links payload, lifecycle, output, and contract:

- command/cwd/env summary;
- command_run_id and tool_call id;
- start/finish ordering;
- terminal/nonterminal status;
- output refs and bounded head/tail;
- copied normalized execution_contract.

Reducers consume typed contracts and evidence first. Regex helpers are
validators or explicit fallbacks.

## `execution_contract` Schema

Target shape:

```json
{
  "schema_version": 2,
  "purpose": "build",
  "stage": "build",
  "proof_role": "final_artifact",
  "expected_artifacts": [
    {
      "path": "/tmp/FooCC/foocc",
      "kind": "executable",
      "proof_required": "exists_and_invokable",
      "freshness_scope": ["artifact_path", "source_tree", "runtime_lookup_path"]
    }
  ],
  "declared_target_refs": [
    {"kind": "artifact", "path": "/tmp/FooCC/foocc"}
  ],
  "acceptance_kind": "candidate_final_proof",
  "continuation_policy": {
    "mode": "managed",
    "yield_after_seconds": 30,
    "max_continuations": 3,
    "resume_policy": "same_resume_identity",
    "terminal_required_for_acceptance": true,
    "final_proof_reserve_seconds": 60
  },
  "background_policy": {
    "mode": "foreground_yieldable",
    "allow_background": false,
    "handoff": "block_external_verifier_until_terminal_or_safe_pause"
  },
  "source_authority_requirement": {
    "mode": "inherits_task_contract",
    "required": true,
    "source_tree_ref": "source-tree:primary",
    "authority_refs": ["source-authority:official-release-archive"],
    "same_source_tree_required": true
  },
  "resume_identity": {
    "idempotence_key": "<computed from the Typed Resume Identity normative hash spec>",
    "contract_id": "work_session:1:long_build:1",
    "purpose": "build",
    "stage": "build",
    "declared_target_refs": [
      {"kind": "artifact", "path": "/tmp/FooCC/foocc"}
    ],
    "expected_artifacts": [
      {"path": "/tmp/FooCC/foocc", "kind": "executable", "proof_required": "exists_and_invokable"}
    ],
    "source_tree_ref": "source-tree:primary",
    "cwd": "/tmp/FooCC",
    "execution_mode": "shell",
    "payload_hash": "sha256:...",
    "env_fingerprint": "sha256:..."
  },
  "risk_class": "build_mutation",
  "evidence_refs": [
    {"kind": "command_evidence", "id": 4}
  ],
  "notes": "short diagnostic reason only"
}
```

Allowed `purpose` values:

- `source_acquisition`
- `source_authority_readback`
- `configure`
- `dependency_generation`
- `build`
- `runtime_build`
- `runtime_install`
- `smoke`
- `artifact_proof`
- `verification`
- `diagnostic`
- `cleanup`
- `generic_command`

Allowed `stage` values:

- `source_acquisition`
- `source_authority`
- `configure`
- `dependency_generation`
- `build`
- `runtime_build`
- `runtime_install`
- `default_smoke`
- `custom_runtime_smoke`
- `artifact_proof`
- `verification`
- `diagnostic`
- `cleanup`
- `command`

Allowed `proof_role` values:

- `none`
- `progress`
- `source_authority`
- `dependency_strategy`
- `target_build`
- `runtime_install`
- `default_smoke`
- `custom_runtime_smoke`
- `final_artifact`
- `verifier`
- `negative_diagnostic`

Allowed `acceptance_kind` values:

- `not_acceptance`
- `progress_only`
- `candidate_source_authority`
- `candidate_artifact_proof`
- `candidate_runtime_smoke`
- `candidate_final_proof`
- `external_verifier`

Allowed `risk_class` values:

- `read_only`
- `network_read`
- `build_mutation`
- `source_tree_mutation`
- `runtime_install`
- `system_mutation`
- `destructive`
- `unknown`

`notes` is never reducer authority. `evidence_refs` links prior evidence the
command depends on; refs are not proof unless the reducer validates them against
the task contract and terminal evidence.

## Proof Role and Acceptance Precedence

`proof_role` and `acceptance_kind` intentionally overlap. The normalizer must
make the relationship explicit.

Precedence:

1. `proof_role` identifies what the command claims to prove.
2. `acceptance_kind` identifies whether that proof class may participate in
   finish/closeout.
3. Validators decide whether terminal evidence actually satisfies the claimed
   proof.

Mismatch rules:

| proof_role | allowed acceptance_kind | disallowed handling |
|---|---|---|
| `none` | `not_acceptance`, `progress_only` | reject if paired with any candidate proof |
| `progress` | `progress_only`, `not_acceptance` | downgrade to `progress_only` or reject if terminal proof is claimed |
| `source_authority` | `candidate_source_authority`, `candidate_final_proof` | reject `candidate_artifact_proof` and `candidate_runtime_smoke` |
| `target_build` | `progress_only`, `candidate_artifact_proof`, `candidate_final_proof` | final proof still requires artifact validator |
| `final_artifact` | `candidate_artifact_proof`, `candidate_final_proof`, `external_verifier` | reject `not_acceptance` unless the command is diagnostic-only |
| `default_smoke` | `candidate_runtime_smoke`, `candidate_final_proof`, `external_verifier` | reject `candidate_source_authority` |
| `custom_runtime_smoke` | `candidate_runtime_smoke`, `external_verifier` | do not satisfy default-smoke requirement |
| `runtime_install` | `progress_only`, `candidate_final_proof` | cannot prove runtime smoke by itself |
| `verifier` | `external_verifier`, `candidate_final_proof` | require exact acceptance refs/checks |
| `negative_diagnostic` | `not_acceptance`, `progress_only` | cannot close positive proof |

If a pair is invalid, the normalizer should reject the action before execution
when possible. If rejection would strand an already completed tool record, the
reducer must mark the contract `contract_invalid` and treat the evidence as
`not_acceptance`. It must not silently upgrade or reinterpret the proof.

## Source Authority Ownership

Source authority is owned by the task-level `LongBuildContract`, not by a single
command. The task contract defines:

- whether source authority is required;
- accepted authority kinds;
- source tree identity;
- required relationship between source proof and build proof;
- whether later commands must use the same source tree.

Per-command `source_authority_requirement` refines or cites that task contract.
It does not replace it.

Command behavior:

- `mode=inherits_task_contract`: command must preserve the task contract's
  source requirement but does not itself prove authority.
- `mode=produces_authority`: command claims to produce source authority evidence
  and must use `proof_role=source_authority` or
  `purpose=source_authority_readback`.
- `mode=consumes_authority`: command depends on prior authority refs and must
  cite them in `evidence_refs` or `authority_refs`.
- `mode=not_applicable`: allowed only when the task contract does not require
  source authority for this command's stage.

Omit/mismatch rules:

- If the task contract requires source authority and a build/default-smoke/final
  proof command omits source authority fields, the normalizer fills
  `mode=inherits_task_contract` and the reducer requires prior authority proof.
- If a command declares a different `source_tree_ref` than the task contract,
  the reducer must mark the evidence as progress/diagnostic until a task-level
  contract update explicitly accepts the new source tree.
- If a source-authority-producing command cites no authority refs or produces no
  validator-confirmed authority output, it cannot satisfy source authority.
- A command may cite prior authority evidence but cannot weaken task-level
  accepted authority kinds.

## Typed Resume Identity

Resume eligibility must not fall back to parsing shell strings. `CommandRun`
and `CommandEvidence.execution_contract.resume_identity` should preserve:

- `command_run_id`;
- `contract_id`;
- `purpose`;
- `stage`;
- `declared_target_refs` or `selected_targets`;
- `expected_artifacts`;
- `source_tree_ref`;
- `cwd`;
- `execution_mode`;
- `payload_hash`;
- `env_fingerprint` for whitelisted build-critical env only;
- `idempotence_key`.

The `idempotence_key` is a deterministic hash over normalized typed identity:

```text
contract_id
purpose
stage
cwd
execution_mode
payload_hash
declared_target_refs_json
expected_artifacts_json
source_tree_ref
env_fingerprint
```

Resume comparisons use typed fields plus `cwd` and `contract_id`. Shell payload
equality alone is insufficient. A timeout resume may proceed only when the
resume identity matches and `continuation_policy.resume_policy` permits same-run
or same-idempotence continuation. A failed non-timeout source acquisition must
require a changed source channel, changed authority ref, or diagnostic evidence;
it must not be handled as same-timeout resume merely because the command string
looks similar.

## Compound Commands

Compound handling must be resolved in the first implementation slice because
recent failures came from compound commands spanning multiple stages.

V1 rule:

- Mixed-stage commands are allowed only when they declare `substeps`.
- A command without `substeps` has exactly one primary `stage` and one primary
  `proof_role`.
- A mixed-stage command may not satisfy final acceptance unless every accepting
  proof role is represented by a terminal validated substep.
- If a command mixes source acquisition, build, runtime install, and smoke but
  declares only `stage=build`, it may count as build progress only. It cannot
  satisfy source authority or default smoke.

Minimal `substeps` shape:

```json
{
  "substeps": [
    {
      "id": "fetch-source",
      "purpose": "source_acquisition",
      "stage": "source_acquisition",
      "proof_role": "source_authority",
      "acceptance_kind": "candidate_source_authority",
      "declared_target_refs": [{"kind": "source_tree", "ref": "source-tree:primary"}]
    },
    {
      "id": "build-artifact",
      "purpose": "build",
      "stage": "build",
      "proof_role": "final_artifact",
      "acceptance_kind": "candidate_artifact_proof",
      "declared_target_refs": [{"kind": "artifact", "path": "/tmp/FooCC/foocc"}]
    }
  ]
}
```

Substeps are declarative proof segments, not a shell parser. Validators may use
shell/output surface to confirm that a claimed substep actually ran and was not
masked, but substeps define the semantic targets.

Implementation can choose the stricter route first: ask the model to split
source acquisition, build, runtime install, and default smoke into separate
commands unless wall budget requires a compound command. If the model chooses a
compound command, it must provide substeps or acceptance is downgraded to
progress.

## Action Schema Changes

`run_command` target shape:

```json
{
  "type": "run_command",
  "command": "make -j\"$(nproc)\" foocc",
  "cwd": "/tmp/FooCC",
  "timeout": 1800,
  "execution_contract": {
    "purpose": "build",
    "stage": "build",
    "proof_role": "final_artifact",
    "acceptance_kind": "candidate_final_proof",
    "expected_artifacts": [
      {"path": "/tmp/FooCC/foocc", "kind": "executable", "proof_required": "exists_and_invokable"}
    ],
    "declared_target_refs": [{"kind": "artifact", "path": "/tmp/FooCC/foocc"}],
    "continuation_policy": {"mode": "managed", "resume_policy": "same_resume_identity"},
    "background_policy": {"mode": "foreground_yieldable", "allow_background": false},
    "source_authority_requirement": {"mode": "consumes_authority", "required": true},
    "risk_class": "build_mutation"
  }
}
```

`run_tests` target shape:

```json
{
  "type": "run_tests",
  "command": "uv run pytest -q tests/test_widget.py --no-testmon",
  "cwd": ".",
  "timeout": 300,
  "execution_contract": {
    "purpose": "verification",
    "stage": "verification",
    "proof_role": "verifier",
    "acceptance_kind": "external_verifier",
    "expected_artifacts": [],
    "continuation_policy": {"mode": "managed", "resume_policy": "none"},
    "background_policy": {"mode": "foreground_blocking", "allow_background": false},
    "source_authority_requirement": {"mode": "not_applicable", "required": false},
    "risk_class": "read_only"
  }
}
```

## `run_tests` Lifecycle Policy

`run_tests` uses the same `CommandRun`/`CommandEvidence` lifecycle as
`run_command`, but with stricter execution policy:

- argv-style execution only;
- shell control remains rejected;
- no backgrounding in V1;
- no stdin continuation in V1;
- poll/yield is allowed only for explicitly long verifier/test commands when
  `continuation_policy.mode=managed`;
- terminal status is required for verifier acceptance;
- timed-out or killed tests are diagnostic/progress only;
- a yielded `run_tests` blocks finish and external verifier handoff until it is
  polled to terminal status or explicitly cancelled/recovered.

Lifecycle tests must cover a short terminal `run_tests`, a yielded managed
`run_tests`, a timed-out `run_tests`, and rejection of `background_policy` values
that would background tests.

## Runner and Lifecycle

Current path:

```text
planned command
  -> string classifier decides whether long_command_budget exists
  -> budget-marked commands enter ManagedCommandRunner
  -> LongCommandRun exists only for that subset
  -> reducers infer stage/proof/source/runtime meaning from strings
```

Target path:

```text
planned command with execution_contract
  -> CommandRun allocated for every run_command/run_tests
  -> generic runner starts/polls/finalizes
  -> CommandEvidence records lifecycle + output refs + contract
  -> reducers consume typed contracts and evidence
```

All command tools should receive:

- `command_run_id`;
- lifecycle status;
- process/session id when live;
- output ref and bounded output snapshots;
- terminal exit/timeout/kill/interruption result;
- typed resume identity.

Short commands can still block until terminal completion by default, so the
model does not see poll noise. Long or explicitly managed commands may yield and
must be resumed or polled by `command_run_id`.

`long_command_budget` should become a derived runner policy from
`execution_contract.continuation_policy`, not a task-semantic string classifier.
Pure source readbacks still get lifecycle records but normally finish as
foreground commands and do not enter long-build continuation state.

## Reducer Changes

Reducer order:

1. Normalize task-level `LongBuildContract`.
2. Normalize command-level `execution_contract`.
3. Build `CommandRun` lifecycle records.
4. Build `CommandEvidence` from lifecycle plus contract.
5. Reduce stages, artifacts, source authority, default smoke, timeout recovery,
   and closeout from typed contracts.
6. Run validators and explicit fallback classifiers only where needed.

Long-build state:

- use `execution_contract.stage` for progress and attempt stage;
- use `proof_role` for proof candidates;
- use `declared_target_refs` and `expected_artifacts` for target association;
- use `CommandRun.status` for lifecycle;
- record `fallback_used=true` when stage/proof comes from old classifiers.

Artifact proof requires:

- terminal successful command evidence;
- valid proof_role/acceptance_kind pair;
- matching expected artifact or declared target;
- artifact validator success;
- freshness after later artifact/source/runtime mutations.

Source authority requires:

- task-level source policy requiring or accepting authority;
- source-authority command or substep with terminal successful evidence;
- authority validator success;
- matching source_tree_ref for later build/default-smoke evidence.

Default runtime smoke requires:

- `stage=default_smoke`;
- `proof_role=default_smoke`;
- valid acceptance kind;
- terminal successful evidence;
- validator confirming default lookup path, not only custom `-L`,
  `LD_LIBRARY_PATH`, `LIBRARY_PATH`, or similar diagnostic paths.

Timeout recovery:

- `running`/`yielded` -> poll by `command_run_id`;
- `timed_out`/`killed` -> resume only when typed resume identity matches and
  policy permits it;
- `failed` source acquisition -> require changed source channel or diagnostic
  evidence;
- `orphaned` -> block automatic proof handoff.

Closeout:

- all required artifacts proven by fresh terminal evidence;
- source authority satisfied when required;
- default smoke satisfied when required;
- no required accepting run remains nonterminal/backgrounded;
- no newer blocker evidence invalidates the proof;
- acceptance checks cite matching command evidence refs.

## Validator Migration Catalog

Regex/helper families should move into one of four buckets: keep as safety,
keep as proof validator, keep as explicit fallback, or delete after fixture
conversion.

`acceptance_evidence.py`:

- Keep as safety: shell splitting, shell operator detection, resident command
  rejection support, artifact mutation-scope checks.
- Keep as proof validators: strict artifact proof surface, artifact output spoof
  rejection, artifact mutation invalidation, terminal-success checks.
- Keep as fallback: old tool-call artifact proof reconstruction for converted
  replay fixtures only.
- Delete/narrow after cutover: helpers that infer final artifact proof intent
  solely from command text when no typed proof role exists, except in explicit
  fallback fixtures.

`long_build_substrate.py`:

- Keep as safety/validator: source fetch masking checks, `errexit`/`pipefail`
  guards, authority readback spoof rejection, default-smoke default-path
  validators, runtime custom-path rejection.
- Keep as proof validators: archive hash/list/readback correlation, validated
  source archive acquisition confirmation, source-tree correlation,
  default-link smoke confirmation, freshness/order invalidation.
- Keep as fallback: `_command_stage`, planned budget-stage helpers, and
  command/output diagnostics only when `execution_contract` is absent or marked
  malformed.
- Delete/narrow after cutover: classifiers whose only purpose is to discover
  source/build/runtime/default-smoke intent from command substrings,
  ecosystem-specific build-token routing, and stale blocker clearing that exists
  only because typed proof state was missing.

Migration rule: validators may reject a typed proof claim or downgrade it to
progress. They may not upgrade an untyped command into final acceptance except
under explicit fallback mode with `fallback_used=true`.

## Permission and Safety Boundary

String parsing remains allowed for:

- shell/argv execution setup;
- approval/sandbox/path-scope decisions;
- resident-loop rejection;
- destructive command detection;
- UI summaries and audit display;
- secret redaction and output clipping;
- proof spoof validation;
- explicit fallback classification.

String parsing must not be the primary authority for:

- command stage;
- proof role;
- acceptance kind;
- source authority ownership;
- default smoke satisfaction;
- lifecycle routing;
- timeout recovery class;
- closeout status.

If safety parsing conflicts with a typed contract, safety wins and the command
must be rejected or downgraded with a visible reason such as
`contract_rejected_by_safety_validator`.

## Migration Plan

Backward compatibility with old active sessions is not required before release.
Fixture compatibility is required only through explicit conversion or fallback
fixtures.

### Phase 0 - Schema and Prompt Contract

- Expand `CommandExecutionContract` to schema v2.
- Update `run_command` and `run_tests` action schema text.
- Add normalizer enums, mismatch rules, source authority ownership rules, and
  compound/substep handling.

### Phase 1 - Generic CommandRun

- Allocate `CommandRun` for every `run_command` and `run_tests`.
- Route all command tools through generic managed lifecycle internally.
- Keep short commands blocking to terminal completion by default.
- Persist output refs and typed resume identity.

### Phase 2 - Evidence Cutover

- Copy normalized contract and command_run_id into `CommandEvidence`.
- Treat nonterminal evidence as progress only.
- Require terminal lifecycle for acceptance.

### Phase 3 - Reducer Typed-First Cutover

- Use contract stage/proof/targets before fallback.
- Validate typed proof claims with existing validators.
- Record `fallback_used` whenever legacy classifiers are used.

### Phase 4 - Recovery and Closeout Cutover

- Poll/resume/recover by `command_run_id`.
- Use typed resume identity for idempotence.
- Derive closeout from typed source/artifact/default-smoke satisfaction.

### Phase 5 - Fixture Migration and Pre-Speed Gate

Fixture conversion strategy:

- Add a small fixture migration helper or checklist that reads old command
  evidence/tool-call fixtures and writes typed `execution_contract` fields for
  each command.
- Require every converted fixture to identify task contract id, stage,
  proof_role, acceptance_kind, declared_target_refs, source_tree_ref, and
  expected_artifacts.
- Preserve a small fallback fixture set with intentionally absent/malformed
  contracts and expected `fallback_used=true`.
- Do not mix converted typed fixtures and legacy semantic expectations in the
  same assertion.
- Add review checklist entries for compound commands: either split commands,
  add substeps, or assert progress-only downgrade.

Pre-speed operation required before any same-shape Terminal-Bench speed proof:

1. Focused local validation for the changed gap surface, including schema,
   lifecycle, reducer, source authority, artifact proof, default smoke,
   timeout recovery, compound command, fixture conversion, and `run_tests`
   lifecycle tests.
2. `mew replay terminal-bench` against the latest relevant saved Harbor
   artifact, or a synthetic same-shape replay fixture if no artifact exists.
3. `mew dogfood --scenario m6_24-terminal-bench-replay`, with
   `--terminal-bench-job-dir` and explicit `--terminal-bench-assert-*` flags
   when validating an existing Harbor artifact.

Only after all three pass should the controller spend exactly one same-shape
speed_1. Do not run proof_5 or broad measurement first.

After a live speed/proof miss, run the same replay and dogfood checks against
the exact saved Harbor job before any code repair. If dogfood is too narrow to
represent the classified failure shape, expand dogfood instrumentation first.

### Phase 6 - Cleanup

- Delete or narrow superseded task-semantic classifiers.
- Keep safety/display parsers and validators.
- Update prompt text that still tells the model to encode proof in shell labels.

## Test Plan

Focused tests before any speed proof:

- schema normalization accepts valid fields and rejects invalid enum/mismatch
  pairs;
- source authority ownership fills inherited requirements and rejects source
  tree mismatches;
- typed resume identity controls poll/resume and rejects command-string-only
  equality;
- compound commands without substeps downgrade to progress;
- compound commands with validated substeps satisfy only their declared proof
  roles;
- `run_command` records CommandRun, output ref, contract, evidence, and resume
  identity;
- `run_tests` records lifecycle, rejects backgrounding, can yield only when
  managed, and cannot prove acceptance before terminal status;
- artifact proof comes from typed final-artifact contract plus validator;
- source authority comes from task contract plus per-command refs and validator;
- default smoke requires typed default-smoke proof plus default-path validator;
- timeout/killed/failed/orphaned statuses choose distinct recovery decisions;
- fallback fixtures record `fallback_used=true` and cannot silently upgrade to
  final proof;
- converted fixtures preserve prior intended evidence with typed contracts.

Then run the Phase 5 pre-speed operation: focused tests, terminal-bench replay,
and dogfood replay scenario.

## Non-Goals

- No Terminal-Bench-specific solver.
- No `compile-compcert` special case.
- No full Codex `unified_exec` clone.
- No full Claude Code Bash/task/permission clone.
- No new multi-agent lane.
- No replacement of deterministic acceptance with final-message trust.
- No proof by shell labels alone.

## Open Questions and Risks

- Trigger interpretation: if reviewers do not accept the controller trigger
  evidence, an explicit controller override is required before implementation.
- Compound substeps add schema complexity, but deferring them would preserve the
  current failure mode. The strict alternative is to forbid mixed-stage
  acceptance until commands are split.
- Source authority still needs shell validators until mew has a typed source
  artifact store. This design demotes those validators to validation rather
  than discovery.
- All-command managed exec can add UX noise if short commands yield too early.
  The first slice should keep ordinary short commands blocking.
- Clean fixture conversion may invalidate old tests. That is acceptable before
  release if fallback fixtures are explicit and small.

## Architecture Fit

This stays in the implementation/tiny lane. It hardens the same authoritative
path:

```text
model action -> typed execution contract -> generic command lifecycle
-> command evidence -> deterministic reducer and acceptance gate
```

It does not add a new authoritative lane, helper lane, benchmark solver, or
task-specific recipe.
