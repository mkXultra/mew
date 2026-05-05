# Design 2026-05-01 - M6.24 Long-Build Substrate

Status: design proposal for review.

Scope: bounded, generic long dependency/source-build reliability for mew work
mode. This is not an implementation note and does not authorize source edits by
itself.

## Inputs Reviewed

Required review and controller inputs:

- `docs/REVIEW_2026-05-01_M6_24_LONG_DEPENDENCY_REFERENCE_DIVERGENCE.md`
- `docs/REVIEW_2026-05-01_M6_24_CODEX_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_CLAUDE_CODE_LONG_DEPENDENCY_AUDIT.md`
- `docs/REVIEW_2026-05-01_M6_24_MEW_LONG_DEPENDENCY_DIVERGENCE.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `docs/M6_24_DOSSIER_LONG_DEPENDENCY_TOOLCHAIN.md`
- `docs/M6_24_GAP_IMPROVEMENT_LOOP.md`

Required mew source and tests:

- `src/mew/work_session.py`
- `src/mew/work_loop.py`
- `src/mew/commands.py`
- `src/mew/acceptance.py`
- `src/mew/acceptance_evidence.py`
- `src/mew/prompt_sections.py`
- `tests/test_work_session.py`
- `tests/test_acceptance.py`

Reference source sampled:

- `references/fresh-cli/codex/codex-rs/core/src/unified_exec/*`
- `references/fresh-cli/codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- `references/fresh-cli/codex/codex-rs/protocol/src/protocol.rs`
- `references/fresh-cli/claude-code/src/Tool.ts`
- `references/fresh-cli/claude-code/src/constants/systemPromptSections.ts`
- `references/fresh-cli/claude-code/src/services/tools/*`

## Thesis

M6.24 should stop adding one more `compile-compcert`-shaped detector plus prompt
sentence. The correct next unit is a small long-build substrate that turns
source-build facts into typed command evidence, build attempts, state, and
recovery decisions.

The substrate should be mew-sized:

- Keep the existing work-session loop and tool model.
- Keep prompt sections as presentation/cache units.
- Keep deterministic acceptance evidence as the final authority.
- Add a typed reducer and allow a flag-day internal cutover before release.
- Avoid a full Codex unified-exec clone, Claude Code permission stack, helper
  agent architecture, Terminal-Bench solver, or CompCert solver.

The target is not to teach mew "how CompCert works." The target is to make mew
remember and enforce generic long-build contracts: source authority, dependency
strategy, configuration, dependency generation, target build, runtime/default
link proof, final artifact proof, and bounded recovery budget.

## Architecture Fit

This stays inside the existing implementation/tiny work lane. There is no new
authoritative lane and no write-capable helper lane.

Helpers may later review the design or validate fixtures, but the production
path remains:

```text
model action -> work_session/work_loop -> commands/tool execution -> evidence
-> resume/recovery state -> acceptance done gate
```

The substrate hardens that path. It does not route hard source-build tasks to a
second planner, benchmark oracle, or specialist solver.

## Non-Goals

- No Terminal-Bench-specific solver.
- No `compile-compcert` special case.
- No table of known CompCert, Coq, Flocq, Menhir, or `libcompcert.a` recovery
  recipes.
- No wholesale Codex or Claude Code clone.
- No replacement of mew's deterministic done gate with final-message trust.
- No broad prompt rewrite before typed state exists.
- No new concurrency or subagent architecture for M6.24.

## Current Mew Shape

The current implementation already has useful pieces:

- `acceptance_evidence.py` rejects timed-out, non-terminal, masked, spoofed, or
  post-mutation final-artifact evidence.
- `acceptance_done_gate_decision()` blocks `task_done=true` until acceptance
  checks cite terminal tool evidence.
- `commands.py` enforces wall-clock ceilings and a long-build recovery reserve.
- `prompt_sections.py` records section ids, hashes, stability, and cache policy.
- `work_session.py` emits `long_dependency_build_state` with progress, missing
  artifacts, latest build command, blockers, and suggested next action.

The weak shape is where the same operational fact lives:

- transcript regex in `work_session.py`;
- model-facing prose in `work_loop.py`;
- resume `suggested_next` prose in `work_session.py`;
- external controller notes in the dossier and decision ledger;
- mostly CompCert-shaped test vocabulary.

The new design consolidates those facts behind a typed reducer. Prompt text can
render the current state, but should not own the operational memory.

Important round-2 premise: mew is not released yet. Backward compatibility with
old internal dict shapes is not a requirement. The design should preserve
behavioral safety invariants, not byte-identical resume output.

## Core Concepts

These are schema concepts, not necessarily new public classes in the first
patch. They can start as dictionaries/dataclasses in a small module and later
become stricter.

### CommandEvidence

`CommandEvidence` is the normalized terminal evidence record. It is the common
source for acceptance, resume, and recovery.

Minimum fields:

```json
{
  "schema_version": 1,
  "id": 9,
  "ref": {"kind": "command_evidence", "id": 9},
  "source": "native_command|synthesized_fixture",
  "tool": "run_command",
  "command": "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
  "cwd": "/tmp/FooCC",
  "env_summary": {"policy": "env_summary_v1", "items": []},
  "start_order": 9,
  "finish_order": 10,
  "started_at": "unknown-or-iso8601",
  "finished_at": "unknown-or-iso8601",
  "duration_seconds": null,
  "status": "completed|failed|running|interrupted",
  "exit_code": 0,
  "timed_out": false,
  "terminal_success": true,
  "output_ref": null,
  "stdout_head": "",
  "stdout_tail": "FooCC 1.2.3\n",
  "stderr_head": "",
  "stderr_tail": "",
  "truncated": false,
  "output_bytes": null
}
```

Responsibilities:

- Preserve command/cwd/status/exit/timeout facts without re-parsing prompt
  prose.
- Provide bounded head/tail output for model-visible diagnosis.
- Optionally point at persisted full output through `output_ref`.
- Preserve current terminal-success semantics: completed, not timed out, and
  exit code zero for command tools.

ID and ref strategy:

- `CommandEvidence.id` is a session-local monotonic integer allocated only for
  terminal command evidence.
- The model-facing ref is `{"kind": "command_evidence", "id": N}`. Textual
  evidence may also say `command #N`.
- String ids are not used in v1 because acceptance evidence resolution needs a
  small deterministic lookup table.
- Existing `tool_call` ids may continue to exist for UI/debugging, but they are
  not canonical long-build evidence after cutover.

Ordering and freshness:

- `start_order` and `finish_order` are monotonic session counters and are the
  ordering authority. Wall-clock timestamps are diagnostic only.
- Final artifact proof is fresh only if there is no later command or write
  mutation with order greater than the proof `finish_order` that may mutate the
  artifact path, artifact parent glob, runtime/default-link search path, or
  source tree required by the contract.
- Running or interrupted evidence can support progress and recovery, but cannot
  prove final acceptance.

Synthesis scope:

- Production cutover should write native `CommandEvidence` for `run_command`
  and `run_tests`.
- Synthesis is allowed for migration tests, transfer fixtures, and one-time
  offline comparison reports only. It is not a production compatibility
  fallback for old active sessions.
- Synthesis may read only command tools that correspond to terminal execution:
  current `run_command` and `run_tests` records.
- Synthesis must not convert write tools, dry-run approvals, or write-tool
  `verify_command` parameters into command evidence. Those can remain write or
  verification metadata, but not final artifact proof records.

Environment privacy:

- `env_summary` defaults to an empty item list.
- Early phases may record only whitelisted, non-secret names and bounded values
  needed for build diagnosis, such as `CC`, `CXX`, `MAKEFLAGS`, `PATH_KIND`, or
  package-manager switch names.
- Values matching secret/token/key/password credential patterns are omitted.
- Values are clipped, and raw environment dumps are never stored.
- The policy name is versioned independently as `env_summary_v1`.

Mew-sized boundary:

- Phase 0 defines the schema and fixture synthesis rules.
- Phase 1 records native fields and optional durable output refs at tool
  completion.
- Phase 6 may add pollable process ids, but only if the previous phases prove
  the need.

### LongBuildContract

`LongBuildContract` is the task-level contract for a source-build or long
dependency build. It is derived from deterministic task authority first, then
augmented by evidence observations. Model-provided memory may add hypotheses,
but cannot remove, narrow, or weaken contract requirements.

Minimum fields:

```json
{
  "schema_version": 1,
  "id": "work_session:1:long_build:1",
  "authority_source": "task_text",
  "required_artifacts": [
    {
      "path": "/tmp/FooCC/foocc",
      "kind": "executable",
      "proof_required": "exists_and_invokable"
    }
  ],
  "source_policy": {
    "authority_required": true,
    "accepted_authorities": [
      "project_docs",
      "package_manager_metadata",
      "official_release_archive",
      "signed_checksum",
      "upstream_download_page"
    ]
  },
  "dependency_policy": {
    "prefer_source_provided_compatibility_branch": true,
    "allow_vendored_dependency_surgery": "only_after_supported_branches_exhausted"
  },
  "build_policy": {
    "prefer_shortest_final_target": true,
    "dependency_generation_before_final_target": true
  },
  "runtime_proof": {
    "required": "required|not_required",
    "classifier": "runtime_proof_classifier_v1",
    "reason": "task asks for a compiler/toolchain that must compile/link a program by default",
    "default_lookup_required": true,
    "custom_lookup_is_diagnostic": true
  },
  "budget": {
    "wall_seconds": null,
    "final_proof_reserve_seconds": 60
  },
  "final_proof": {
    "terminal_success_required": true,
    "artifact_freshness_required": true,
    "evidence_kinds": ["command_evidence"]
  }
}
```

Responsibilities:

- State what final artifacts and proof shape matter.
- Keep generic source/dependency/build/runtime policy in one compact object.
- Avoid embedding one benchmark's recovery sequence.
- Feed prompt rendering and acceptance checks, but not replace acceptance.

Authority precedence:

1. Current user instruction and task text.
2. Explicit task acceptance constraints and exact command/artifact requirements.
3. Deterministic contract extraction from task text.
4. Command evidence observations, which may satisfy or strengthen the contract.
5. Model working memory or action acceptance checks, which may add candidate
   observations but may not weaken artifacts, source policy, runtime proof, or
   final proof.

If two sources conflict, the higher source wins. For example, model memory
cannot turn a required artifact into optional, cannot replace a default runtime
proof with a custom path proof, and cannot downgrade official source authority
to an arbitrary VCS archive.

Source authority precedence:

- Highest: explicit task-provided source artifact or exact command.
- High: official release/distribution archive, signed checksum, upstream
  download page, release notes, or project documentation.
- Medium: package-manager metadata or distro source package when the task does
  not require an upstream release artifact.
- Low fallback: VCS-generated tag/archive URL or generic branch checkout.
- Invalid as authority: model assertion without evidence, random mirror, or
  generated source tree whose provenance is not tied to the task/project.

Runtime proof classifier:

- Required when the task asks to build a compiler, toolchain, interpreter, VM,
  emulator, SDK, runtime, standard library, linker-facing tool, or an artifact
  that must compile/link/run a secondary program through its default invocation.
- Required when task acceptance constraints or command evidence mention default
  link/runtime/standard-library behavior, missing `-l...` libraries, or custom
  runtime paths used only to make a smoke pass.
- Not required for ordinary CLI/source-build artifacts that only need to run
  themselves, such as a Rust CLI, Python extension import, CMake utility, or
  native addon, unless the task text or evidence requires runtime/default-link
  behavior.
- If classifier evidence is ambiguous for a compiler-like artifact, require
  runtime/default proof. If it is ambiguous for an ordinary CLI, do not require
  runtime proof; final artifact terminal proof still applies.

### BuildAttempt

`BuildAttempt` is a semantic view over one or more `CommandEvidence` records.
In the first implementation, one attempt should normally correspond to one
command tool call.

Minimum fields:

```json
{
  "schema_version": 1,
  "id": "work_session:1:long_build:1:attempt:3",
  "contract_id": "work_session:1:long_build:1",
  "command_evidence_ref": {"kind": "command_evidence", "id": 9},
  "stage": "source_acquisition|configure|dependency_generation|build|runtime_build|runtime_install|default_smoke|artifact_proof",
  "selected_target": "foocc",
  "requested_timeout_seconds": 1800,
  "effective_timeout_seconds": 840,
  "wall_budget_before_seconds": 900,
  "wall_budget_after_seconds": 50,
  "result": "success|failure|timeout|running|unknown",
  "produced_artifacts": [],
  "mutation_refs": [],
  "diagnostics": [
    {
      "failure_class": "runtime_link_failed",
      "excerpt": "ld: cannot find -lfoo"
    }
  ]
}
```

Responsibilities:

- Attach stage and target meaning to raw command evidence.
- Record budget and timeout facts at the command boundary.
- Record produced artifacts and mutations when observable.
- Feed `LongBuildState` through a reducer.

### LongBuildState

`LongBuildState` is the reducer output. It replaces the current free-form
`long_dependency_build_state` as the source of truth. Because mew is unreleased,
the cutover may remove old state keys and old dict shapes instead of preserving
them.

Minimum fields:

```json
{
  "schema_version": 1,
  "kind": "long_build_state",
  "contract_id": "work_session:1:long_build:1",
  "status": "not_started|in_progress|blocked|ready_for_final_proof|complete",
  "stages": [
    {"id": "source_authority", "required": true, "status": "unknown|satisfied|blocked"},
    {"id": "target_built", "required": true, "status": "unknown|satisfied|blocked"},
    {"id": "default_smoke", "required": false, "status": "not_required"}
  ],
  "artifacts": [
    {
      "path": "/tmp/FooCC/foocc",
      "status": "missing_or_unproven|proven",
      "proof_evidence_id": null
    }
  ],
  "attempt_ids": [],
  "latest_attempt_id": null,
  "current_failure": {
    "failure_class": "artifact_missing",
    "evidence_id": null,
    "clear_condition": "terminal command proves /tmp/FooCC/foocc exists and is invokable"
  },
  "recovery_decision_id": null
}
```

Responsibilities:

- Provide one compact state for resume, prompt, and recovery.
- Track stage status and clear conditions, not just blocker strings.
- Let old blocker lessons map to generic failure classes, without preserving
  old blocker dict output.
- Remain task-generic: names like `runtime_link_failed` are allowed; names like
  `compcert_runtime_libcompcert_path_invalid` are not.

Stage policy:

- Stages are contract-driven. A stage is present only when the contract or
  observed evidence makes it relevant.
- Irrelevant stages are omitted. They should not sit forever in `unknown`.
- A stage may be explicitly present with `required: false` and
  `status: "not_required"` only when rendering that negative fact prevents
  accidental over-enforcement, such as runtime proof on an ordinary CLI build.
- Every blocked required stage must name a failure class, evidence id when
  available, and clear condition.

### RecoveryDecision

`RecoveryDecision` is controller-owned recovery policy derived from
`LongBuildState`, command evidence, and wall budget.

Scope boundary: `RecoveryDecision` chooses the next recovery action only. It
does not decide whether a task may finish, and it does not handle generic model
format recovery. Finish authority remains in `acceptance_done_gate_decision()`.
Malformed model JSON remains work-loop/model recovery, not long-build state.

Minimum fields:

```json
{
  "schema_version": 1,
  "id": "work_session:1:long_build:1:recovery:4",
  "contract_id": "work_session:1:long_build:1",
  "state_status": "blocked",
  "failure_class": "runtime_link_failed",
  "prerequisites": ["target_built"],
  "clear_condition": "default compile/link smoke succeeds without custom runtime path flags",
  "allowed_next_action": {
    "kind": "command",
    "stage": "runtime_build_or_install",
    "description": "build or install the shortest runtime/library target, then rerun the same default smoke"
  },
  "prohibited_repeated_actions": [
    "source_reacquisition",
    "clean_rebuild",
    "custom_runtime_path_only_proof"
  ],
  "budget": {
    "remaining_seconds": null,
    "reserve_seconds": 60,
    "may_spend_reserve": false,
    "attempts_for_failure_class": 1,
    "max_attempts_for_failure_class": 2
  },
  "decision": "continue|block_for_budget|ask_user"
}
```

Responsibilities:

- Move `RecoveryBudget` from prose into state.
- Prevent repeated expensive branches when the clear condition did not change.
- Preserve final proof reserve before long validation commands.
- Render only the next allowed recovery action into prompt/resume.
- Never mark acceptance complete and never weaken the done gate.

### Relationship Between Concepts

```text
task text + acceptance constraints
  -> LongBuildContract

run_command/run_tests tool result
  -> CommandEvidence
  -> BuildAttempt
  -> LongBuildState
  -> RecoveryDecision

LongBuildState + RecoveryDecision
  -> work_session long-build resume state
  -> compact prompt sections

CommandEvidence + LongBuildContract
  -> acceptance evidence / done gate
```

No concept above can independently complete a task. Completion still requires
the deterministic done gate to accept terminal evidence.

## Layer Integration

### `src/mew/work_session.py`

Current role:

- Reconstructs `long_dependency_build_state` from `tool_calls`.
- Emits progress, missing artifacts, latest build command, blockers, and long
  suggested-next prose.

New role:

- Build or load native `CommandEvidence` records from command execution.
- Build `LongBuildContract` from task text and acceptance constraints.
- Reduce `BuildAttempt` records into `LongBuildState`.
- Format resume lines from state fields and `RecoveryDecision`, not from a
  long static paragraph.
- Remove old `long_dependency_build_state` output when the flag-day cutover
  lands, unless a short-lived developer-only debug view is explicitly useful.

Important constraint:

- Existing blocker lessons must be mapped into the failure-class inventory
  before old detector output is removed. The inventory preserves safety, not
  old wording or old dict shape.

### `src/mew/work_loop.py`

Current role:

- Slices a large legacy THINK prompt into `SourceAcquisitionProfile`,
  `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget`.

New role:

- Keep stable, short policy sections:
  - source-build contract discipline;
  - final artifact proof discipline;
  - runtime/default-link proof discipline;
  - budget discipline.
- Render dynamic facts from `LongBuildState` and `RecoveryDecision` near the
  existing dynamic context, not in static profile prose.
- Do not add a new recovery sentence unless the anti-accretion gate passes.

The prompt should say, in effect:

```text
Current long-build state says stage X is blocked by failure class Y.
The next allowed recovery is Z.
Do not repeat A.
Final proof requires terminal command evidence for artifact B.
```

It should not carry the full history of every previous M6.24 repair.

### `src/mew/commands.py`

Current role:

- Executes work tools.
- Applies wall-clock ceilings.
- Preserves a heuristic long-build recovery reserve.
- Applies finish gates and continuation after deterministic finish blockers.

New role:

- Attach command evidence metadata at tool start and completion.
- Record requested/effective timeout, wall budget before/after, and timeout
  ceiling data in a typed shape.
- Ask `RecoveryDecision` whether a proposed long command may spend reserve or
  must be blocked for budget.
- Keep the existing blocking command execution path in early phases.

Possible later role:

- Add a managed long-command option with process id, bounded output snapshot,
  poll, and final end evidence. This should be deferred until the reducer and
  evidence schema are in place.

### `src/mew/acceptance.py` and `src/mew/acceptance_evidence.py`

Current role:

- Extract long dependency tasks and final artifacts.
- Require verified acceptance checks.
- Reject invalid evidence refs and non-terminal command evidence.
- Prove long dependency artifacts through strict command/output checks.

New role:

- Resolve `command_evidence` refs as the canonical terminal evidence path after
  cutover.
- Use native `CommandEvidence` for terminal success, ordering, freshness, and
  strict artifact proof.
- Keep current proof strictness: timeout rejection, masked output rejection,
  spoof rejection, path-prefix rejection, and post-proof mutation guards.
- Optionally require `LongBuildContract.runtime_proof` evidence for
  compiler/toolchain tasks after the runtime proof schema exists.

The invariant stays unchanged:

```text
task_done=true is not allowed unless terminal-success evidence proves the
required final artifact and required acceptance checks.
```

### `src/mew/prompt_sections.py`

Current role:

- Records section metadata, hash, stability, cache policy, and metrics.

New role:

- Add no complex policy.
- Continue exposing profile size and stability metrics.
- Support anti-accretion checks by making profile growth visible.

## Failure Taxonomy

The first taxonomy should be small. It should absorb current blocker families
without encoding benchmark details.

Proposed initial failure classes:

- `source_authority_unverified`: build started from a lower-authority source
  artifact and compatibility repair began before authoritative source evidence.
- `source_identity_evidence_overconstrained`: source identity evidence from an
  archive, tag, root directory, or coarse version marker was rejected too
  narrowly before build work could proceed.
- `dependency_strategy_incoherent`: mutually incompatible dependency/toolchain
  paths were attempted without selecting a coherent branch.
- `source_provided_branch_unchecked`: source help/config/docs likely expose a
  compatibility/prebuilt/external branch that was not adequately inspected.
- `vendored_dependency_surgery_too_early`: local dependency/proof-library edits
  began while supported dependency branches remained viable.
- `dependency_generation_missing`: final target failed because generated
  dependencies/configuration were absent.
- `target_too_broad_for_artifact`: command started a broad build when a named
  final artifact target was requested and time was material.
- `build_timeout`: a long prerequisite or final target timed out without final
  artifact proof.
- `artifact_missing_or_unproven`: required artifact is absent or not proven by
  terminal evidence.
- `artifact_proof_invalid`: proposed proof was timed out, masked, spoofed, or
  followed by a relevant mutation.
- `runtime_link_failed`: default invocation failed due missing runtime or
  standard library.
- `runtime_default_path_unproven`: only custom `-L`, `-stdlib`, or env lookup
  proof exists where default lookup proof is required.
- `runtime_install_before_build`: install failed because the runtime/library
  artifact had not been built.
- `build_system_target_surface_invalid`: requested target path is not a valid
  target surface for the active build system.
- `budget_reserve_violation`: proposed command would consume the final proof or
  recovery reserve.

Current blocker inventory:

| Current emitted blocker family | Generic failure class | Clear condition |
| --- | --- | --- |
| `dependency_generation_order_issue` | `dependency_generation_missing` | Run the project's configure/dependency-generation target, then rerun the final target. |
| `untargeted_full_project_build_for_specific_artifact` | `target_too_broad_for_artifact` | Select the shortest target that produces the required artifact, or prove the broad target is required. |
| `toolchain_version_constraint_mismatch` | `dependency_strategy_incoherent` | Choose a dependency/toolchain branch compatible with the source contract. |
| `compatibility_override_probe_missing` | `source_provided_branch_unchecked` | Inspect source/project compatibility options or prove none exist. |
| `version_pinned_source_toolchain_before_compatibility_override` | `source_provided_branch_unchecked` | Try or reject the source-provided compatibility branch before heavy version-pinned source toolchain work. |
| `source_archive_version_grounding_too_strict` | `source_identity_evidence_overconstrained` | Accept archive/tag/root identity when it grounds the requested release, or cite stronger source evidence. |
| `external_dependency_source_provenance_unverified` | `source_authority_unverified` | Check a higher-authority source channel before invasive compatibility repair. |
| `external_branch_help_probe_too_narrow_before_source_toolchain` | `source_provided_branch_unchecked` | Re-probe help/docs with external/use-external/prebuilt/system/library terms or inspect unfiltered help. |
| `compatibility_branch_budget_contract_missing` | `dependency_strategy_incoherent` with `budget_reserve_violation` evidence | Commit to one coherent viable branch early enough to preserve final build/proof budget. |
| `vendored_dependency_patch_surgery_before_supported_branch` | `vendored_dependency_surgery_too_early` | Stop local dependency/proof-library surgery until supported dependency branches are exhausted or rejected. |
| `runtime_link_library_missing` | `runtime_link_failed` | Build/install/configure the runtime or standard library and rerun default smoke. |
| `default_runtime_link_path_failed` | `runtime_link_failed` | Clear the missing default runtime link failure with terminal evidence. |
| `default_runtime_link_path_unproven` | `runtime_default_path_unproven` | Rerun the smoke without custom `-L`, `-stdlib`, or runtime env path flags. |
| `runtime_install_before_runtime_library_build` | `runtime_install_before_build` | Build the runtime/library artifact, then retry install and default smoke. |
| `runtime_library_subdir_target_path_invalid` | `build_system_target_surface_invalid` | Use the correct build-system target surface, such as the subdirectory's own target, then prove the runtime/default smoke. |
| timed-out final build/proof | `build_timeout` or `artifact_proof_invalid` | Rerun or continue with enough wall budget and terminal-success proof. |
| masked/echoed/path-prefix/spoofed artifact proof | `artifact_proof_invalid` | Run a non-masked terminal proof command that directly references the required artifact. |
| missing required final artifact | `artifact_missing_or_unproven` | Produce and terminally prove the required artifact. |

This table is the required migration inventory. It preserves the safety lesson
from each current blocker without preserving old blocker names or output shape.

## State Machine

The reducer should not attempt a full package-manager solver. It should track
observable stages and conservative clear conditions.

Stages are contract-driven. The contract decides which stages are required,
optional, or omitted. A simple source-build CLI may only require source
authority, target build, and final artifact proof. A compiler/toolchain contract
may additionally require runtime/default-link proof. A build system with no
configure step should not carry a permanent unknown `configured` stage.

Nominal state path for a contract that requires every stage:

```text
not_started
  -> source_acquired
  -> source_authority_satisfied
  -> dependency_strategy_selected
  -> configured
  -> dependencies_generated
  -> target_built
  -> runtime_built_or_not_required
  -> runtime_installed_default_or_not_required
  -> default_smoke_satisfied_or_not_required
  -> final_artifact_proof_satisfied
  -> complete
```

Failure handling:

```text
attempt emits CommandEvidence
  -> reducer classifies failure_class
  -> RecoveryDecision selects one allowed next action and clear condition
  -> prompt/resume renders only that next action
  -> next attempt either clears the condition, changes the failure class, or
     consumes the bounded retry count
```

The state machine must permit partial progress. A failed default smoke after a
successful target build should not reset source acquisition, configuration, or
target build status.

## Prompt Policy After Consolidation

The static long-build prompt should become shorter, not longer.

Stable policy should cover:

- Source-build tasks require final artifact proof, not only progress.
- Use source/project-provided compatibility branches before expensive alternate
  toolchain construction.
- Do not replace default runtime proof with custom runtime path proof.
- Preserve wall budget for final artifact and proof.
- Follow `LongBuildState` and `RecoveryDecision` when present.

Dynamic prompt should cover:

- Contract id and required artifacts.
- Current stage statuses.
- Current failure class and evidence id.
- Next allowed recovery action.
- Prohibited repeated action.
- Remaining/reserved budget, when known.
- Final proof requirement.

Everything else should be read from state or evidence.

## Acceptance Evidence Invariant

Mew's deterministic acceptance evidence is an advantage and should become
stronger through this design.

Rules:

- `CommandEvidence.terminal_success` is necessary but not sufficient for final
  artifact proof.
- Final artifact proof still uses strict artifact proof logic: exact artifact
  reference, terminal success, no timeout, no masked/suppressed proof, no fake
  echo, no path-prefix spoof, and no later artifact-scope mutation.
- `LongBuildState.status == complete` is advisory until
  `acceptance_done_gate_decision()` allows completion.
- `RecoveryDecision.decision == continue` cannot mark acceptance as satisfied.
- After cutover, canonical final evidence refs are `command_evidence` refs.
  Old `tool_call` refs do not need to remain supported for compatibility.

## Flag-Day Cutover

Because mew is unreleased, this design intentionally drops backward
compatibility for old internal state and evidence shapes.

Cutover contract:

1. The implementation may remove `work_session.resume.long_dependency_build_state`.
2. The implementation may remove old long-dependency blocker dicts and old
   `suggested_next` paragraphs.
3. The implementation may require new `command_evidence` refs for final
   long-build proof after the prompt/action schema is updated.
4. Old active sessions that lack native command evidence do not need to resume
   byte-identically. They may require a fresh proof command or a new work
   session.
5. Historical docs, reports, and gap ledgers remain as audit records, but the
   runtime does not need to consume their old shapes.

What must be preserved is behavior and safety:

- deterministic acceptance evidence;
- terminal-success final proof;
- timeout, masked-output, spoofed-output, and path-prefix proof rejection;
- post-proof mutation guard;
- wall-clock and recovery-budget protection;
- recovery decisions that are same-or-better on existing failure scenarios;
- transfer fixtures;
- anti-accretion enforcement.

Behavior/safety parity replaces compatibility. Old fixtures may produce new
state keys, new wording, and new ids, but they must preserve or improve:

- failure class classification;
- next recovery action;
- final artifact proof rejection/acceptance;
- runtime/default-link proof enforcement when required;
- budget reserve behavior;
- final done-gate decision.

## Migration Plan

Each phase should be independently reviewable and small enough to validate with
unit tests before any same-shape benchmark rerun.

### Phase 0 - Schema and Safety-Parity Harness

Add schema helpers for:

- `CommandEvidence`
- `LongBuildContract`
- `BuildAttempt`
- `LongBuildState`
- `RecoveryDecision`

Define schema version policy:

- All long-build records carry `schema_version`.
- Additive optional fields do not require a version bump.
- Removing fields, changing field semantics, changing id/ref resolution, or
  changing ordering/freshness semantics requires a schema version bump.
- A flag-day cutover may reject mixed schema versions rather than attempting
  compatibility.

Build a test-only fixture synthesis path from old `run_command`/`run_tests`
tool records so current failure scenarios can be compared. This synthesis is
not a runtime compatibility path.

Validation:

- Terminal-success parity with current acceptance helpers.
- Artifact-proof rejection parity for timeout, masked, spoofed, path-prefix,
  and post-proof mutation cases.
- Verify synthesis never turns write tools or write-tool `verify_command`
  fields into `CommandEvidence`.

No prompt behavior change. No command execution behavior change. No same-shape
benchmark required.

### Phase 1 - Native CommandEvidence Cutover

Record native `CommandEvidence` at command-tool start/completion:

- id/ref;
- command/cwd;
- env summary under privacy policy;
- start/finish ordering;
- requested/effective timeout;
- wall budget before/after when available;
- exit/timed-out status;
- bounded output head/tail;
- optional full output ref.

Update acceptance ref resolution to use `command_evidence` as the canonical
terminal evidence path. Update model-facing prompt/action guidance so final
acceptance checks cite command evidence ids.

Validation:

- Done-gate tests using `command_evidence` refs.
- Strict final artifact proof tests using native records.
- Safety-parity tests against synthesized fixtures.

### Phase 2 - Contract Extraction and State Cutover

Build `LongBuildContract` from the same classifier inputs currently used by
`is_long_dependency_toolchain_build_task()` and `long_dependency_final_artifacts()`.

Build a reducer that produces `LongBuildState` from `CommandEvidence` and
contract policy. Replace old `long_dependency_build_state` resume output with
the new `long_build_state` shape.

Validation:

- Existing long-dependency work-session fixtures may change output shape, but
  must preserve behavior/safety parity.
- Add non-CompCert transfer fixtures for artifact extraction and stage
  reduction.
- Add negative fixtures where runtime proof is not required.

No benchmark rerun required unless recovery behavior changes materially.

### Phase 3 - RecoveryDecision Recovery Actions

Add `RecoveryDecision` derivation for a narrow subset:

- `artifact_missing_or_unproven`
- `build_timeout`
- `runtime_link_failed`
- `runtime_default_path_unproven`
- `runtime_install_before_build`
- `build_system_target_surface_invalid`
- `budget_reserve_violation`

Render the decision into the new long-build resume state instead of long
suggested-next paragraphs. Do not include finish policy or model-format
recovery in this object.

Validation:

- Behavior/safety parity tests for current CompCert-shaped fixtures.
- Transfer fixtures for at least two non-CompCert source-build shapes.
- Prompt section metrics should show dynamic state movement without expanding
  static long-dependency profile text.

Run one same-shape `compile-compcert` speed_1 only after unit/fixture tests pass
and the decision ledger records this as the selected rerun.

### Phase 4 - Budget Enforcement From RecoveryDecision

Replace marker-based long-build recovery reserve detection with
contract/state/recovery based budget decisions.

Keep current constants unless the tests prove a threshold needs adjustment.
This phase should move logic out of command-text marker heuristics and into:

- whether the task has a `LongBuildContract`;
- current failure class;
- whether the command is a final validation/build attempt;
- whether reserve may be spent to clear a known recovery condition.

Validation:

- Current wall budget tests.
- Transfer fixture where recovery may spend reserve after a known link/install
  failure.
- Transfer fixture where a new long validation command is capped to preserve
  reserve.

Run one same-shape speed_1 if behavior changes are material.

### Phase 5 - Anti-Accretion Enforcement

Add the concrete enforcement surface described below:

- prompt-section metric/hash comparison;
- required anti-accretion ledger record for static profile growth;
- required transfer fixture for new failure classes or recovery actions.

This phase may land before Phase 4 if prompt growth resumes.

### Phase 6 - Optional Managed Long Command

Only if Phases 0-5 still leave long-build evidence loss or timeout recovery
gaps, add a bounded managed long-command mode:

- process id;
- bounded initial yield;
- poll/continue action;
- output head/tail and full-output ref;
- final end evidence;
- process cap and cleanup.

This should be smaller than Codex unified exec:

- no broad UI protocol;
- no new permission stack;
- no interactive shell as the default;
- no background process survival beyond the work session unless explicitly
  designed.

Validation must prove that managed commands improve a generic transfer fixture
before using them for `compile-compcert` proof escalation.

## Anti-Accretion Gate

This gate applies to future changes to `LongDependencyProfile`,
`RuntimeLinkProof`, `RecoveryBudget`, and long-build resume blockers.

No new prompt clause, blocker code, or recovery budget exception should be
accepted unless all answers are recorded in the design note, repair note, or
decision ledger:

1. What generic failure class does this map to?
2. Which typed field was missing from `LongBuildContract`,
   `BuildAttempt`, `LongBuildState`, `RecoveryDecision`, or
   `CommandEvidence`?
3. Why can the current reducer not express it?
4. What clear condition tells mew the blocker is resolved?
5. What existing action is prohibited from repeating?
6. What non-CompCert transfer fixture covers it?
7. Does the change preserve `command_evidence` id/ref resolution and freshness?
8. Does the static prompt profile grow? If yes, why is dynamic state rendering
   insufficient?
9. Does the change avoid benchmark-specific names, paths, package versions, or
   solver recipes?
10. What same-shape rerun, if any, is required?

Automatic rejection criteria:

- The proposed text names only one benchmark's package, binary, library, or
  path.
- The proposed repair is "add another sentence" while a typed state field is
  absent.
- The clear condition is "model should remember to do better" rather than
  terminal evidence.
- The change weakens the acceptance done gate.
- The change adds a helper lane or second authority for M6.24 coding tasks.

Prompt profile budget:

- Static `LongDependencyProfile`, `RuntimeLinkProof`, and `RecoveryBudget`
  sections should trend down after Phase 2.
- Any increase in static chars must cite an anti-accretion gate record.
- Dynamic `LongBuildState` rendering may grow within a bounded item limit, but
  raw logs must stay in `CommandEvidence` refs, not prompt prose.

Concrete enforcement surface:

- Add a prompt-section metric/hash snapshot test for the static long-build
  sections.
- If `long_dependency_profile`, `runtime_link_proof`, or `recovery_budget`
  static chars increase, the test must require a matching anti-accretion record.
- The record should be machine-readable in the M6.24 gap ledger or an adjacent
  design artifact and include:
  - `failure_class`;
  - `typed_field_added_or_changed`;
  - `clear_condition`;
  - `prohibited_repeat_action`;
  - `transfer_fixture`;
  - `same_shape_rerun_required`;
  - `prompt_static_chars_before`;
  - `prompt_static_chars_after`.
- New failure classes or recovery actions must be listed in this design's
  taxonomy inventory or a successor design before implementation.
- New classifier behavior must include at least one positive fixture and one
  negative fixture.
- A prompt-only change that lacks the record and fixtures should fail review,
  even if it passes existing unit tests.

## Validation Strategy

Validation should prove transfer, behavior/safety parity, and same-shape
behavior. It should not require byte-identical old dict output.

### Unit and Reducer Tests

Required test groups:

- `CommandEvidence` native records and test-only synthesis from command tools.
- Terminal-success parity with current terminal-success behavior.
- Strict artifact proof parity with `long_dependency_artifact_proven_by_call()`.
- `LongBuildContract` extraction for generic source-build tasks.
- Contract authority precedence: model memory cannot weaken task-derived
  artifacts, source policy, runtime proof, or final proof.
- Runtime proof classifier positive and negative cases.
- `LongBuildState` reducer stage transitions with contract-driven omitted or
  `not_required` stages.
- Failure taxonomy mapping for old blocker fixtures.
- Behavior/safety parity for old blocker fixtures, not old dict compatibility.
- `RecoveryDecision` clear conditions and retry budgets.
- Prompt section metrics showing static/dynamic separation.
- Done-gate tests for `command_evidence` refs.
- Env summary privacy tests: secrets omitted, values clipped, whitelist
  enforced.
- Command evidence ordering/freshness tests, including post-proof mutation.

### Transfer Fixtures

Add fixtures that deliberately avoid CompCert names and assumptions:

- `toy_toolchain_default_runtime`: source-build `/tmp/FooCC/foocc`, missing
  default `-lfoo` runtime, recovery through runtime build/install, final
  default smoke.
- `cmake_generated_dependency`: CMake or Make project where final target fails
  until generated headers/dependencies are produced.
- `python_native_extension_cli`: source build of a wheel/extension that produces
  a CLI artifact and requires exact artifact proof.
- `rust_or_cargo_cli_long_build`: long but ordinary source build with no runtime
  link requirement, to prove runtime proof is conditional.
- `invalid_target_surface_generic`: parent build command asks for a subdirectory
  artifact path that is not a build-system target, then clears by using the
  subdirectory's own target surface. This fixture must not mention CompCert or
  `libcompcert.a`.
- `unverified_source_build_rejected`: source-build starts from a low-authority
  VCS/generated archive, then dependency surgery begins before authoritative
  source evidence. Expected recovery is source authority check, not more local
  surgery.
- `non_toolchain_runtime_not_required`: ordinary source-built CLI or native
  extension has terminal artifact proof and no compiler/toolchain runtime
  requirement. Expected state omits or marks runtime proof as not required.
- `write_verify_command_not_command_evidence`: a write tool includes a
  verification command, but synthesis does not turn that field into command
  evidence.
- `stale_artifact_after_mutation_rejected`: final artifact proof is followed by
  a later artifact-scope mutation. Expected done gate rejects stale proof.
- `masked_or_spoofed_artifact_proof_rejected`: echo, `/dev/null`, masked
  output, or path-prefix proof cannot satisfy final artifact evidence.

Real-task transfer candidates from the dossier may be used after synthetic
fixtures:

- `mcmc-sampling-stan`
- `protein-assembly`
- `adaptive-rejection-sampler`

These are transfer checks, not places to add task solvers.

### Same-Shape Reruns

Same-shape reruns should follow the M6.24 controller:

- Preserve the same task, model, permissions, timeout shape, and wrapper.
- Use `speed_1` to answer "did the failure mode move?" after behavior-changing
  phases.
- Use resource-normalized `proof_5` only after transfer fixtures and speed_1
  justify escalation.
- Do not run another `compile-compcert` proof_5 solely because the current
  repair chain has one more local detector.

Recommended sequence:

1. Phases 0-2: unit and fixture tests only unless behavior changes earlier.
2. Phase 3: unit/fixture tests, then one `compile-compcert` speed_1 if visible
   recovery behavior changed.
3. Phase 4: unit/fixture tests, then speed_1 if budget behavior changed.
4. Phase 5: anti-accretion tests only unless prompt behavior changed.
5. Proof escalation: only after transfer fixtures pass and the decision ledger
   records the escalation condition.

## Deferred

Deferred by this design:

- Full Codex-style unified exec with rich UI/protocol events.
- Full Claude Code-style tool permission classifier and prompt-cache economics.
- Long-lived background shells outside a work session.
- New authoritative helper lanes, review lanes, or deliberation loops.
- Automatic package-manager or source-authority solver.
- Benchmark-specific recipes for Terminal-Bench tasks.
- Migrating old active sessions or historical transcript state.
- Replacing all transcript pattern matching in one patch.
- Supporting old `tool_call` final evidence refs after cutover.
- Weakening or bypassing `acceptance_done_gate_decision()`.

## Open Questions

- Where should native `CommandEvidence` be stored after cutover:
  session-level `command_evidence`, command tool records, or both?
- What output retention path should be used for full logs, and what cleanup
  policy prevents unbounded disk growth?
- Should `BuildAttempt` represent one shell segment inside a compound command,
  or only one mew command tool call in v1?
- What exact threshold classifies a command as long-build relevant for budget
  enforcement without over-classifying ordinary tests?
- Should source-authority observations be model-declared, parser-derived, or
  both with provenance?
- How much runtime/default-link proof can be inferred generically without
  becoming compiler-specific?
- Should command ids share the visible numbering surface with work tools, or
  should the prompt show a separate "command #N" evidence list?
- What is the minimum useful managed long-command subset if Phase 6 becomes
  necessary?

## Risks

- The schema becomes too large and recreates reference-CLI complexity.
  Mitigation: require Phases 0-3 to prove reducer/evidence value before new
  runtime features.
- The reducer misclassifies generic build output and blocks useful recovery.
  Mitigation: require behavior/safety parity and transfer fixtures before
  same-shape reruns.
- Flag-day cutover breaks old active sessions.
  Mitigation: accept that risk before release; require fresh proof rather than
  preserving old state shapes.
- CommandEvidence ref numbering confuses the model.
  Mitigation: make ids small integers, render a compact evidence list, and test
  done-gate resolution through command refs.
- Static prompt sections continue to grow despite typed state.
  Mitigation: enforce the anti-accretion gate and track section chars/hashes.
- Transfer fixtures accidentally remain CompCert-shaped.
  Mitigation: require fixtures with different build systems, artifact names,
  dependency shapes, and runtime-proof requirements.
- Managed long-command work expands into a full process manager.
  Mitigation: defer Phase 6 and require evidence that Phases 0-5 are
  insufficient.
- Runtime/default-link proof becomes too compiler-centric.
  Mitigation: express it as conditional final-proof policy for toolchains,
  runtimes, and standard libraries, not as a specific library path.

## Reviewer Checklist

Reviewers should focus on:

- Whether the design is small enough for mew.
- Whether any concept smuggles in a `compile-compcert` solver.
- Whether deterministic acceptance evidence remains the final authority.
- Whether dropping backward compatibility is clean and still preserves safety.
- Whether `CommandEvidence` id/ref/ordering/freshness rules are deterministic.
- Whether the anti-accretion gate is enforceable.
- Whether the migration phases can land without broad source churn.
- Whether transfer fixtures are diverse enough to prove generality.
