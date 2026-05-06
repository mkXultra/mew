# Design 2026-05-06 - M6.24 Expected Artifact Contract

Status: design proposal for implementation.

Scope: replace marker-driven runtime/build/artifact failure inference in
`implement_v2` with structured execution, artifact, and verifier evidence.

Compatibility stance: no backward compatibility required before release. Prefer
one clean source of truth over adapters that preserve old reducer projections.

## Inputs Reviewed

- `docs/DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md`
- `docs/DESIGN_2026-05-03_M6_24_GENERIC_MANAGED_EXEC.md`
- `docs/DESIGN_2026-05-06_M6_24_IMPLEMENT_V2_TOOL_CONTRACT_AND_FRONTIER_STATE.md`
- `docs/REVIEW_2026-05-06_CODEX_EXPECTED_ARTIFACT_AND_FAILURE_CLASSIFICATION.md`
- `docs/REVIEW_2026-05-06_CLAUDE_CODE_EXPECTED_ARTIFACT_AND_FAILURE_CLASSIFICATION.md`
- `docs/M6_24_IMPLEMENT_V2_REBASELINE_2026-05-06.md`
- `docs/M6_24_DECISION_LEDGER.md`
- `src/mew/implement_lane/v2_runtime.py`
- `src/mew/toolbox.py`
- `src/mew/work_session.py`
- `src/mew/long_build_substrate.py`
- `src/mew/acceptance_evidence.py`

## Problem

The latest `make-doom-for-mips` same-shape speed run reached a useful runtime
failure: the compound command rebuilt and linked, then ran a VM verifier that
terminated at `PC=0x0` and produced no output artifact. The bridge repair
classified this by recognizing text markers such as `vm_rc=`, `Program
terminated at PC=`, and `NO_FRAME`.

That repair is intentionally narrow, but it is still a marker bridge. It asks
later code to infer the true failure class from terminal text. This is the same
structural smell that M6.24 has repeatedly hit:

- command strings contain multiple semantic phases;
- clipped stdout/stderr becomes the only available evidence;
- reducers infer build/runtime/artifact semantics from text;
- each miss adds another marker or classifier branch;
- replay/dogfood can reproduce the artifact but not always the semantic reason.

The correct boundary is not "better string markers". The correct boundary is:

```text
execution contract declares expected artifacts
  -> command/tool execution writes typed run records
  -> artifact checks run against declared artifacts
  -> failure classification consumes structured records first
  -> text is only low-confidence supporting evidence
```

## Reference Conclusion

Codex CLI and Claude Code do not have a direct generic equivalent of
`execution_contract.expected_artifacts`.

They do have strong adjacent patterns:

- typed command/tool execution records;
- raw exit code, timeout, interruption, and output refs;
- command lifecycle events;
- structured tool schemas and MCP-style structured results;
- command-specific exit semantics instead of universal nonzero failure;
- hook/verifier-style structured gates;
- persisted large-output artifacts with prompt-visible previews;
- stable error categories and orphaned-tool-result recovery.

Mew should adopt those structural patterns, but not copy the absence of a
generic expected-artifact contract. `implement_v2` can be stronger here by
making expected artifacts first-class.

## Design Decision

Replace the current marker-first frontier classification path with four
authoritative records:

```text
ExecutionContract
ToolRunRecord
ArtifactEvidence
FailureClassification
```

`ToolRunRecord` is about what happened to a command or tool.
`ArtifactEvidence` is about what exists or does not exist after that run.
`FailureClassification` is derived from structured records and points to
evidence ids. Output text can add hints but cannot be the primary source of
truth when a contract/artifact record exists.

## Goals

- Classify `build_failure`, `runtime_failure`, and
  `artifact_validation_failure` from structured facts.
- Make expected artifacts explicit, including path, kind, required checks, and
  freshness.
- Preserve raw process facts: exit code, timeout, interruption, duration, and
  output refs.
- Preserve artifact facts: existence, size, mtime, kind, and check result.
- Keep model-visible summaries compact and derived from records.
- Make replay/dogfood recompute the same classifications from saved records.
- Delete or demote marker classifiers once structured evidence covers them.

## Non-Goals

- Do not implement a benchmark/task-specific solver.
- Do not introduce a second planner or a new lane for this change.
- Do not make shell text parsing the source of truth.
- Do not preserve historical reducer schemas unless needed for current tests.
- Do not require Codex/Claude provider-specific cache changes in this slice.

## Relation To The 2026-05-03 Execution Contract

This design does not discard
`DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md`. It makes that contract
operational.

`schema_version=3` supersedes the previous projection shape only where this
document explicitly says so. The following v2 fields remain first-class
contract fields and must keep their v2 structured shapes unless a migration
mapping is listed here:

- `proof_role`
- `acceptance_kind`
- `declared_target_refs`
- `source_authority_requirement`
- `resume_identity`
- `continuation_policy`
- `background_policy`
- `risk_class`
- `affected_paths`
- `evidence_refs`

The new fields are additive at the semantic layer:

- `substeps`
- `expected_artifacts`
- `tool_run_records`
- `artifact_evidence`
- `verifier_evidence`
- `failure_classifications`

There is no backward compatibility requirement for on-disk v2 fixtures. During
implementation, tests and reducers should move to the v3 source of truth rather
than keeping v2 and v3 as co-equal projections. If a model-visible legacy field
is still useful, it must be derived from v3 records.

Enum stance: keep v2 `proof_role` and `acceptance_kind` values. Do not replace
them with new synonym enums. New v3 behavior should be expressed through
`expected_artifacts`, `substeps`, evidence records, and classifiers, not by
renaming v2 proof concepts.

## Data Model

### ExecutionContract

`execution_contract` is supplied on model tool calls and normalized by runtime.
It describes intent and verification obligations, not process state.

```json
{
  "schema_version": 3,
  "id": "contract:turn27:call1",
  "role": "compound",
  "stage": "command",
  "purpose": "verification",
  "proof_role": "verifier",
  "acceptance_kind": "external_verifier",
  "declared_target_refs": [
    {"kind": "artifact", "path": "./doomgeneric_mips"},
    {"kind": "artifact", "path": "/tmp/frame.bmp"}
  ],
  "source_authority_requirement": {
    "mode": "inherits_task_contract",
    "required": true,
    "source_tree_ref": "source-tree:primary",
    "authority_refs": ["source-authority:official-release-archive"],
    "same_source_tree_required": true
  },
  "resume_identity": {
    "idempotence_key": "sha256:...",
    "contract_id": "contract:turn27:call1",
    "purpose": "verification",
    "stage": "command",
    "declared_target_refs": [
      {"kind": "artifact", "path": "./doomgeneric_mips"},
      {"kind": "artifact", "path": "/tmp/frame.bmp"}
    ],
    "expected_artifacts": [
      {"path": "./doomgeneric_mips", "kind": "executable"},
      {"path": "/tmp/frame.bmp", "kind": "file"}
    ],
    "source_tree_ref": "source-tree:primary",
    "cwd": "/work",
    "execution_mode": "shell",
    "payload_hash": "sha256:...",
    "env_fingerprint": "sha256:..."
  },
  "continuation_policy": {
    "mode": "managed",
    "yield_after_seconds": 15,
    "max_continuations": 3,
    "resume_policy": "same_resume_identity",
    "terminal_required_for_acceptance": true,
    "final_proof_reserve_seconds": 60
  },
  "background_policy": {
    "mode": "foreground_yieldable",
    "allow_background": true,
    "handoff": "block_external_verifier_until_terminal_or_safe_pause"
  },
  "expected_exit": {"mode": "any"},
  "substeps": [
    {
      "id": "substep:build",
      "stage": "build",
      "role": "build",
      "proof_role": "target_build",
      "acceptance_kind": "candidate_artifact_proof",
      "purpose": "compile and link target binary",
      "declared_target_refs": [{"kind": "artifact", "path": "./doomgeneric_mips"}],
      "expected_exit": {"mode": "zero"},
      "requires_artifacts": [],
      "produces_artifacts": ["doomgeneric_mips"]
    },
    {
      "id": "substep:runtime-verifier",
      "stage": "verification",
      "role": "runtime",
      "proof_role": "verifier",
      "acceptance_kind": "external_verifier",
      "purpose": "run target under verifier/emulator and produce frame",
      "declared_target_refs": [{"kind": "artifact", "path": "/tmp/frame.bmp"}],
      "expected_exit": {"mode": "code_set", "codes": [0, 4]},
      "verifier_required": true,
      "requires_artifacts": ["doomgeneric_mips"],
      "produces_artifacts": ["frame"]
    }
  ],
  "expected_artifacts": [
    {
      "id": "doomgeneric_mips",
      "kind": "executable",
      "target": {"type": "path", "path": "./doomgeneric_mips"},
      "path": "./doomgeneric_mips",
      "required": true,
      "source": "model_declared",
      "confidence": "high",
      "producer_substep_id": "substep:build",
      "freshness": "modified_after_run_start",
      "checks": [
        {"type": "exists", "severity": "blocking"},
        {"type": "non_empty", "severity": "blocking"},
        {"type": "executable", "severity": "warning"}
      ]
    },
    {
      "id": "frame",
      "kind": "file",
      "target": {"type": "path", "path": "/tmp/frame.bmp"},
      "path": "/tmp/frame.bmp",
      "required": true,
      "source": "model_declared",
      "confidence": "high",
      "producer_substep_id": "substep:runtime-verifier",
      "freshness": "modified_after_run_start",
      "checks": [
        {"type": "exists", "severity": "blocking"},
        {"type": "non_empty", "severity": "blocking"},
        {"type": "kind", "expected": "bmp", "severity": "blocking"},
        {"type": "size_between", "min": 54, "max": 20000000, "severity": "warning"}
      ]
    }
  ],
  "verifier_required": true,
  "risk_class": "build_mutation",
  "notes": "short reason only"
}
```

Allowed `role` values:

- `setup`
- `source`
- `dependency`
- `build`
- `test`
- `runtime`
- `artifact_probe`
- `verify`
- `cleanup`
- `diagnostic`
- `compound`
- `unknown`

Allowed `purpose` values are the v2 values:

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

Allowed `stage` values are the v2 values:

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

Allowed `expected_exit.mode` values:

- `zero`
- `nonzero`
- `any`
- `code_set`

When `mode=code_set`, the contract must include `codes`:

```json
{"mode": "code_set", "codes": [0, 4]}
```

Allowed artifact `kind` values:

- `file`
- `directory`
- `glob`
- `stdout`
- `stderr`
- `json`
- `image`
- `binary`
- `executable`
- `report`
- `log`

Allowed artifact `freshness` values:

- `exists_before_or_after`
- `created_after_run_start`
- `modified_after_run_start`
- `modified_after_previous_check`

Allowed artifact `source` values:

- `model_declared`
- `task_contract_inherited`
- `runtime_inferred`

`runtime_inferred` artifacts are allowed only from structured task/frontier
state, never from regex over the command text. Runtime-inferred artifacts carry
at most medium classification confidence unless a later verifier/tool result
confirms the artifact obligation.

Substep semantics:

- `substeps` are declarative proof segments, not shell execution splits.
- A single compound shell command normally creates one `ToolRunRecord` with
  `substep_id=null`.
- Single-role commands may set `substep_id` to the matching contract substep.
- `requires_artifacts` are input artifact ids that must already exist before
  the substep can be considered reachable.
- `produces_artifacts` are artifact ids the substep is expected to produce or
  verify.
- v2 proof/acceptance mismatch rules apply per substep. A substep cannot
  satisfy acceptance unless its `proof_role` / `acceptance_kind` pair is valid
  and its structured evidence is terminal.
- The runtime must not infer that a later substep ran from stdout/stderr
  markers. A later substep is reachable only when there is structured evidence:
  a separate terminal tool run for that substep, a terminal verifier run for the
  substep, or contract-backed artifact evidence tied to that substep after its
  required input artifacts are satisfied.
- If a compound command lacks structured evidence that a later substep ran, the
  later substep remains `partial` and cannot become the primary failure merely
  because output text resembles that stage.

### ToolRunRecord

Every `run_command`, `run_tests`, `poll_command`, and verifier-like tool result
must write a normalized `ToolRunRecord`.

```json
{
  "schema_version": 1,
  "record_id": "tool-run-record:turn27:call1:poll2",
  "command_run_id": "command-run:turn27:call1",
  "provider_call_id": "call-force-rename-source-start-and-verify",
  "declared_tool_name": "run_command",
  "effective_tool_name": "run_command",
  "tool_contract_recovery": null,
  "terminal_failure_reaction_eligible": true,
  "contract_id": "contract:turn27:call1",
  "substep_id": null,
  "started_at": "2026-05-06T13:01:26Z",
  "finished_at": "2026-05-06T13:01:53Z",
  "duration_seconds": 27.409,
  "status": "failed",
  "exit_code": 4,
  "timed_out": false,
  "interrupted": false,
  "semantic_exit": {
    "ok": true,
    "category": "ok",
    "source": "contract_override",
    "message": "exit code accepted by compound contract; artifact checks decide verification"
  },
  "stdout_ref": "implement-v2-exec://.../stdout",
  "stderr_ref": "implement-v2-exec://.../stderr",
  "combined_output_ref": "implement-v2-exec://.../output",
  "stdout_preview": "... bounded tail ...",
  "stderr_preview": "... bounded tail ...",
  "output_truncated": false
}
```

Identity rules:

- `command_run_id` is the stable lifecycle id for one command/process.
- `record_id` is unique for each provider-visible tool observation, including
  start, yield, poll, terminal poll, kill, or recovery result.
- A yielded start and a later terminal `poll_command` therefore share
  `command_run_id` but have different `record_id` and `provider_call_id`.
- Persistence keys use `record_id`; lifecycle grouping uses `command_run_id`.

`status` values:

- `queued`
- `running`
- `yielded`
- `completed`
- `failed`
- `timed_out`
- `interrupted`
- `killed`
- `backgrounded`
- `orphaned`
- `pre_spawn_error`
- `contract_rejected`

`semantic_exit.source` values:

- `default`
- `known_command`
- `contract_override`
- `verifier_policy`

`semantic_exit.category` values:

- `ok`
- `nonzero_exit`
- `timeout`
- `interrupted`
- `killed`
- `pre_spawn_error`
- `contract_rejected`
- `tool_contract_recovery`
- `unknown`

Semantic exit resolution:

- `expected_exit.mode=zero`: `semantic_exit.ok=true` iff `exit_code == 0`.
- `expected_exit.mode=nonzero`: `semantic_exit.ok=true` iff `exit_code != 0`.
- `expected_exit.mode=any`: `semantic_exit.ok=true` for any terminal exit.
- `expected_exit.mode=code_set`: `semantic_exit.ok=true` iff `exit_code` is in
  the declared `codes` list. When it matches, `semantic_exit.source` is
  `contract_override` and `semantic_exit.category` is `ok`; when it does not
  match, the category is `nonzero_exit` or `unknown` depending on whether an
  exit code exists.

`poll_command` records must reference the original `command_run_id`; freshness
checks use the original command run's `started_at`, not the poll observation
time. A `yielded` or `running` record is nonterminal and cannot satisfy a
verifier gate.

### ArtifactEvidence

Artifact checks run immediately after the command reaches a terminal state when
`expected_artifacts` are declared. They must also run after `poll_command`
finalizes a previously backgrounded command.

```json
{
  "schema_version": 1,
  "evidence_id": "artifact-evidence:frame:run27:check1",
  "check_id": "check:frame:exists:run27",
  "artifact_id": "frame",
  "command_run_id": "command-run:turn27:call1",
  "tool_run_record_id": "tool-run-record:turn27:call1:poll2",
  "contract_id": "contract:turn27:call1",
  "substep_id": "substep:runtime-verifier",
  "target": {"type": "path", "path": "/tmp/frame.bmp"},
  "path": "/tmp/frame.bmp",
  "kind": "file",
  "required": true,
  "source": "model_declared",
  "confidence": "high",
  "freshness": "modified_after_run_start",
  "pre_run_stat": {"exists": false, "mtime": null, "size": null},
  "post_run_stat": {"exists": false, "mtime": null, "size": null},
  "checks": [
    {
      "type": "exists",
      "passed": false,
      "severity": "blocking",
      "observed": {"exists": false},
      "message": "expected artifact /tmp/frame.bmp was not found after run"
    }
  ],
  "status": "failed",
  "blocking": true
}
```

Check types:

- `exists`
- `non_empty`
- `size_between`
- `mtime_after`
- `kind`
- `json_schema`
- `text_contains`
- `regex`

Only explicit artifact checks may use text matching. Global stdout/stderr regex
classification is demoted to fallback.

`command_probe` is intentionally not part of the first slice. If needed later,
it must be modeled as a verifier tool with its own `ExecutionContract`,
`ToolRunRecord`, and artifact/verifier evidence. It should not be a hidden
artifact-check side effect.

Artifact target addressing:

- Filesystem artifacts use `target.type=path` and must include `path`.
- Stream artifacts use `target.type=stream`, `stream=stdout|stderr|combined`,
  and `source_tool_run_record_id`; they do not use filesystem freshness checks.
- Text/regex checks may apply only to explicitly declared stream artifacts or
  to explicitly declared text files. They must not be global output classifiers.

Freshness rules:

- `created_after_run_start`: artifact did not exist before the run and exists
  with `mtime >= run.started_at`.
- `modified_after_run_start`: artifact exists with `mtime >= run.started_at`.
- `modified_after_previous_check`: artifact exists with `mtime` greater than
  the most recent previous evidence check for the same artifact id/path.
- `exists_before_or_after`: no freshness requirement.

`created_after_run_start` requires a persisted `pre_run_stat` and
`post_run_stat`. If the runtime did not capture a pre-run stat, the check result
is `partial`, not pass. `modified_after_run_start` can be decided from
`post_run_stat` and the referenced run's `started_at`.

### VerifierEvidence

Verifier output is a structured verdict over run and artifact evidence.

```json
{
  "schema_version": 1,
  "verifier_id": "verifier:contract:turn27:call1",
  "contract_id": "contract:turn27:call1",
  "verdict": "fail",
  "reason": "runtime verifier completed but required frame artifact is missing",
  "checks": [
    {
      "id": "frame-exists",
      "passed": false,
      "command_run_ids": ["command-run:turn27:call1"],
      "tool_run_record_ids": ["tool-run-record:turn27:call1:poll2"],
      "artifact_evidence_ids": ["artifact-evidence:frame:run27:check1"],
      "observed": {"exists": false},
      "expected": {"exists": true},
      "message": "missing required runtime output artifact"
    }
  ],
  "missing_evidence": []
}
```

This can be produced by deterministic runtime checks first. AI verifier agents
may be added later, but if used they must output this schema and cite concrete
`command_run_id`, `tool_run_record_id`, and `artifact_evidence_id` values.

Deterministic derivation:

- `pass` iff every terminal required run has acceptable semantic exit and every
  blocking required artifact check passes.
- `fail` iff any terminal required run violates semantic exit or any blocking
  required artifact check fails.
- `partial` iff required evidence is absent because a run is still nonterminal,
  a verifier crashed before emitting evidence, or a required artifact was not
  checkable.
- `unknown` iff no contract-backed verifier obligation exists.

### FailureClassification

Classification consumes structured records and emits one primary class plus
optional secondary classes. It must be deterministic.

Primary precedence:

1. pre-spawn / contract rejection / permission / sandbox errors;
2. timeout / interruption / killed;
3. earliest failed blocking substep in a compound command;
4. required artifact check failures for the active substep;
5. semantic exit for the active substep;
6. verifier failures;
7. low-confidence text hints.

Compound exception: if a later verifier/runtime substep reached a terminal run
and its required artifact check failed, that verifier/runtime artifact failure
is primary even if the command's aggregate exit is nonzero. If an earlier build
substep failed before producing the runtime input artifact, the primary class
remains build/build-artifact failure.

For compound commands, "substep reached a terminal run" means structured
reachability evidence exists. Accepted evidence is a separate terminal tool run
for the substep, a terminal verifier/tool record tied to the substep, or
contract-backed artifact evidence for a produced artifact after the substep's
input artifacts were satisfied. Plain stdout/stderr markers do not prove
substep reachability.

```json
{
  "schema_version": 1,
  "classification_id": "failure:contract:turn27:call1",
  "phase": "runtime",
  "kind": "missing_artifact",
  "class": "runtime_artifact_missing",
  "secondary_classes": ["runtime_failure"],
  "secondary_kinds": ["nonzero_exit"],
  "confidence": "high",
  "retryable": true,
  "summary": "runtime verifier finished but required artifact /tmp/frame.bmp is missing",
  "evidence_refs": [
    {"kind": "tool_run_record", "id": "tool-run-record:turn27:call1:poll2"},
    {"kind": "command_run", "id": "command-run:turn27:call1"},
    {"kind": "artifact_evidence", "id": "artifact-evidence:frame:run27:check1"}
  ],
  "required_next_probe": "Inspect runtime progress and artifact production path before another rebuild."
}
```

High-level phase mapping:

- `role=build` plus failed semantic exit -> `build_failure`
- `role=test` plus failed semantic exit -> `test_failure`
- `role=runtime` plus timeout/nonzero runtime command -> `runtime_failure`
- any failed required artifact check -> `artifact_validation_failure`
- `role=build` plus failed required build artifact -> `build_artifact_missing`
- `role=runtime` plus failed required artifact check -> `runtime_artifact_missing`
- verifier verdict failure -> `verification_failure`
- no structured evidence -> `unknown_failure`

Allowed `class` values:

- `build_failure`
- `test_failure`
- `runtime_failure`
- `artifact_validation_failure`
- `build_artifact_missing`
- `runtime_artifact_missing`
- `verification_failure`
- `internal_failure`
- `unknown_failure`

Allowed `phase` values:

- `setup`
- `source`
- `dependency`
- `build`
- `test`
- `runtime`
- `artifact`
- `verification`
- `internal`
- `unknown`

Allowed `kind` values:

- `pre_spawn_error`
- `permission_error`
- `sandbox_error`
- `contract_rejected`
- `timeout`
- `interrupted`
- `killed`
- `nonzero_exit`
- `missing_artifact`
- `stale_artifact`
- `schema_mismatch`
- `verifier_failed`
- `partial_evidence`
- `unknown_failure`

`secondary_classes` draws from the same `class` enum as `class`.
`secondary_kinds` draws from the `kind` enum. Together they record non-primary
facts such as `runtime_failure` / `nonzero_exit` when artifact evidence is the
primary next-action driver.

Confidence rules:

- `high`: model-declared or task-contract-inherited artifact obligation with
  concrete run/artifact evidence.
- `medium`: runtime-inferred artifact obligation with concrete evidence.
- `low`: text-only hint or missing contract.

## Execution Flow

```text
model emits tool call
  |
  v
normalize ExecutionContract
  |
  v
record declared substeps as classification metadata
  |
  v
capture pre-run artifact stats for declared path artifacts
  |
  v
execute tool / command
  |
  v
persist ToolRunRecord
  |
  v
run declared ArtifactChecks
  |
  v
persist ArtifactEvidence
  |
  v
derive VerifierEvidence when verifier_required=true
  |
  v
derive FailureClassification from structured records
  |
  v
update hard runtime frontier and prompt summary
```

Important rule: if `execution_contract.expected_artifacts` is present, artifact
checks run even when `exit_code != 0`. A nonzero exit and missing artifact are
not alternatives; they are two facts. Classification decides which fact is the
dominant next-action driver based on contract role.

Substeps do not imply runtime shell decomposition. A compound command still runs
as one command unless the model/tool layer explicitly emits separate tool calls.
The classifier may use substep metadata to interpret structured evidence, but it
must not parse a compound shell string into hidden sub-runs.

### Finish Gate Integration

Required artifact/verifier failures are finish blockers.

`implement_v2` may not mark a task done when the latest contract-backed evidence
contains:

- a failed blocking artifact check;
- a `partial` verifier verdict for required evidence;
- a terminal run with `semantic_exit.ok=false` for a required substep;
- a stale failure that has not been superseded by newer evidence for the same
  artifact id/path.

A blocker is superseded only by later evidence with the same contract/artifact
identity and a later terminal `tool_run_record_id` under the same or superseding
`command_run_id`, or by a freshness timestamp that satisfies the contract. A
successful stdout line is not enough to clear a failed required artifact check.

## Prompt / Model Contract

`implement_v2` prompt sections should require tool calls to include
`execution_contract.expected_artifacts` whenever the task asks for an output
file, generated binary, report, image, JSON artifact, stdout/stderr contract, or
runtime side effect.

Minimal model-facing guidance:

```text
When a command is meant to prove or create an artifact, declare
execution_contract.expected_artifacts. Do not rely on echo markers or prose to
prove artifact existence. Mew will check declared artifacts after the command.
```

If the model omits expected artifacts for a verifier-shaped command and the task
contract clearly requires an artifact, runtime may add a deterministic inferred
contract from task/frontier state. The inference must be recorded with
`source="runtime_inferred"` and lower confidence than model-declared contracts.

## Replay / Dogfood

Replay must not rely on re-running commands. It reads saved raw records and
recomputes derived records.

On-disk layout:

```text
proof-artifacts/
  implement_v2/
    evidence/
      contracts/<contract_id>.json
      command_runs/<command_run_id>.json
      tool_run_records/<record_id>.json
      artifact_evidence/<evidence_id>.json
      verifier_evidence/<verifier_id>.json
      classifications/<classification_id>.json
    proof-manifest.json
```

`proof-manifest.json` stores references to latest records, not copied
classifications as the source of truth.

Replay inputs:

- `ExecutionContract`
- `ToolRunRecord`
- `ArtifactEvidence`
- `VerifierEvidence`

`command_runs/<command_run_id>.json` is the lifecycle aggregate. It may cite
many `tool_run_records/<record_id>.json` observations. Replay uses the terminal
record for verifier/artifact decisions but preserves earlier yielded/running
records for lifecycle audit.

Replay recomputes `FailureClassification` from those inputs and compares it to
the stored classification. A mismatch is a replay failure and must block
speed-proof interpretation until fixed. Stored classifications are audit output,
not replay input.

Replay should recompute:

- whether the proof manifest is pairable;
- latest failure;
- expected next action;
- hard runtime frontier entries.

Dogfood should include at least:

1. a positive runtime-artifact-missing scenario:
   - runtime role;
   - command exits nonzero or zero;
   - expected artifact missing;
   - classification is `runtime_artifact_missing`.
2. a negative build-artifact-missing scenario:
   - build role;
   - artifact missing before runtime verifier;
   - classification remains build/artifact failure, not runtime.
3. a stale artifact scenario:
   - artifact exists before command;
   - freshness requires modified after run;
   - classification is stale artifact.
4. a passing artifact scenario:
   - artifact exists, non-empty, fresh, kind ok;
   - no artifact blocker.
5. a runtime-inferred artifact scenario:
   - task/frontier declares required artifact;
   - model omits expected artifact;
   - runtime adds `source=runtime_inferred`;
   - classification confidence is medium unless later confirmed.
6. a poll-finalized scenario:
   - command starts as `running`/`yielded`;
   - later poll creates a terminal run;
   - artifact checks use the original run start time.
7. a partial verifier scenario:
   - required verifier evidence is absent because the run is nonterminal,
     timed out, or crashed before evidence was produced;
   - finish gate blocks on `partial`.
8. a multi-artifact mixed scenario:
   - one required artifact passes;
   - one required artifact fails;
   - blocker cites only the failing evidence id.
9. a re-run freshness scenario:
   - a stale failed evidence record is superseded by a later fresh artifact;
   - finish gate clears only after the newer evidence is present.
10. a stream artifact scenario:
    - stdout/stderr/combined output is declared with `target.type=stream`;
    - text/regex checks read only that declared stream target;
    - global marker classification remains inactive.

## Implementation Plan

### Phase 1 - Schema and Pure Classifier

Files:

- `src/mew/implement_lane/execution_evidence.py` (new)
- `tests/test_execution_evidence.py` (new)

Implement dataclasses or typed dict helpers for:

- `ExecutionContract`
- `ExecutionSubstep`
- `ExpectedArtifact`
- `CommandRun`
- `ToolRunRecord`
- `ArtifactEvidence`
- `VerifierEvidence`
- `FailureClassification`

Implement pure functions:

- `normalize_execution_contract(value, *, task_contract, frontier_state)`
- `semantic_exit_from_run(record, contract)`
- `classify_execution_failure(record, artifact_evidence, verifier_evidence, contract)`
- `derive_verifier_evidence(contract, tool_runs, artifact_evidence)`
- `apply_finish_gate(contract, verifier_evidence, classifications)`

No filesystem checks yet. Tests are pure dict inputs/outputs.

Phase 1 must also encode:

- v2 contract-field carry-forward;
- v2 `proof_role` and `acceptance_kind` enum preservation;
- `code_set.codes`;
- `semantic_exit.ok` resolution from `expected_exit`;
- `command_run_id` vs `record_id` identity separation;
- primary/secondary classification precedence;
- compound substep precedence;
- runtime-inferred confidence limits.
- allowed `phase`, `kind`, `class`, and `secondary_classes` tokens.

### Phase 2 - Artifact Check Runtime

Files:

- `src/mew/implement_lane/artifact_checks.py` (new)
- `tests/test_artifact_checks.py` (new)

Implement deterministic checks:

- path normalization and safety;
- pre-run stat capture for path artifacts;
- exists;
- non-empty;
- size range;
- mtime after run start;
- file kind: bmp/json/text/binary/executable where cheap;
- stream target checks for explicitly declared stdout/stderr/combined output
  artifacts;
- explicit text/regex checks only when declared.

No model calls. No task-specific paths.

Do not add `command_probe` in this phase. If a probe is needed later, route it
through the normal tool execution contract and evidence records.

### Phase 3 - `implement_v2` Tool Result Integration

Files:

- `src/mew/implement_lane/v2_runtime.py`
- `tests/test_implement_lane.py`

When `run_command`, `run_tests`, or `poll_command` produces a result:

1. capture pre-run artifact stats for declared path artifacts;
2. create or update `CommandRun`;
3. create a unique `ToolRunRecord` observation;
4. preserve `declared_tool_name`, `effective_tool_name`,
   `tool_contract_recovery`, and terminal-failure reaction eligibility;
5. run artifact checks for declared artifacts when the observation is terminal;
6. attach `command_runs`, `tool_run_records`, and `artifact_evidence` to proof manifest /
   updated lane state;
7. derive `VerifierEvidence`;
8. derive `FailureClassification`;
9. apply finish gate blockers;
10. update `lane_hard_runtime_frontier` from classification.

Delete or demote the bridge path:

- `_frontier_runtime_artifact_missing(...)`
- `_frontier_runtime_execution_timeout(...)` should become fallback only;
- `_frontier_failure_key_from_payload(...)` should prefer structured
  classifications.

### Phase 4 - Prompt Section and Contract Inference

Files:

- `src/mew/implement_lane/prompt.py`
- prompt-section tests

Add a stable prompt section:

- `implement_v2_execution_artifact_contract`

It should be cacheable/static and explain:

- declare expected artifacts;
- declare role/stage;
- artifact checks are runtime-owned;
- text markers are not proof;
- finish should cite artifact evidence ids, not only stdout text.

Runtime inference:

- if task contract/frontier says a final artifact path is required and the
  model emits a verifier-shaped command without `expected_artifacts`, add an
  inferred expected artifact with `source=runtime_inferred`;
- only infer from structured task/frontier fields, not regex over command text.
- prompt summaries should cite evidence ids and blocker classes rather than
  asking the model to rediscover the same missing-artifact fact from stdout.

### Phase 5 - Replay / Dogfood / Emulator

Files:

- `src/mew/terminal_bench_replay.py`
- `src/mew/dogfood.py`
- `tests/test_terminal_bench_replay.py`
- `tests/test_dogfood.py`

Make replay and dogfood consume the new records. Add emulator coverage for the
same shape that caused this design:

```text
compound build+verification command
  -> runtime role
  -> expected artifact declared
  -> command exits nonzero
  -> artifact missing
  -> replay says latest failure is runtime_artifact_missing
```

Replay must recompute classifications from saved raw evidence and compare with
stored classification records. Do not treat stored classification as the replay
input.

### Phase 6 - Remove Old Bridge Authority

Remove old reducer authority once tests pass:

- marker-only `NO_FRAME` / `VM_RC` runtime classification should no longer be
  authoritative;
- shell-string build/runtime stage inference should not override structured
  `role`;
- legacy projection fields should be generated from the new records only when
  model-visible summaries need them.
- any remaining string marker fallback must be explicitly low-confidence and
  inactive when contract-backed evidence exists.

This is where no-backward-compatibility matters. Do not carry both systems as
co-equal truth sources.

### Phase 7 - Same-Shape Validation

Before live speed:

1. focused UT for new schema/classifier/checks;
2. exact replay on the latest `make-doom-for-mips` artifact;
3. terminal-bench replay dogfood;
4. new expected-artifact emulator;
5. ruff;
6. `git diff --check`;
7. codex-ultra or claude-ultra review.

Then spend exactly one same-shape live speed:

```text
terminal-bench/make-doom-for-mips
selected_lane=implement_v2
speed_1
```

If it misses, do not edit from live output directly. Replay/dogfood the saved
artifact and classify whether the next gap is:

- artifact contract missing;
- artifact checker wrong;
- model strategy failure;
- command lifecycle failure;
- verifier/harness mismatch;
- actual task-solving failure.

## Acceptance Criteria

Done when:

- `implement_v2` records `ToolRunRecord` for terminal tools.
- `implement_v2` separates stable `command_run_id` from unique
  provider-visible `record_id`, including poll/finalize observations.
- `implement_v2` preserves v2 contract semantics in v3 records:
  proof role, acceptance kind, source authority, resume identity,
  continuation/background policy, and evidence refs.
- v3 keeps v2 `proof_role` / `acceptance_kind` values and mismatch precedence
  rather than introducing synonym enums.
- `implement_v2` records `ArtifactEvidence` for declared expected artifacts.
- `implement_v2` captures pre-run and post-run stats for freshness checks that
  require them.
- `implement_v2` derives `VerifierEvidence` deterministically from run and
  artifact records.
- `implement_v2` blocks finish when required artifact/verifier evidence fails
  or is partial.
- A runtime verifier command with missing required artifact classifies as
  `runtime_artifact_missing` without reading `NO_FRAME`.
- A build command with missing build artifact does not classify as runtime.
- A compound build+runtime command picks the correct primary class and keeps
  non-primary facts as secondary classes/kinds.
- A compound command does not claim a later substep ran unless structured
  evidence proves reachability; stdout/stderr markers alone are insufficient.
- Runtime-inferred artifacts are represented with source/confidence and do not
  silently become high-confidence model-declared facts.
- Poll-finalized commands run artifact checks using the original run start time.
- Stream artifacts use explicit stream targets and cannot revive global output
  marker classification.
- Replay and dogfood recompute the same classification from saved artifacts.
- Old string marker classifiers are fallback only and cannot override structured
  evidence.
- `command_probe` is either absent from the first slice or modeled as a normal
  verifier tool record.
- Focused UT, replay, dogfood, emulator, ruff, and diff check pass.
- At least one codex-ultra or claude-ultra review approves.
- One same-shape live speed run is recorded after implementation.

## Risks

### Risk: Model omits expected artifacts

Mitigation: static prompt section plus runtime inference from task/frontier
state. Inference must be explicit and visible.

### Risk: Artifact checks become task-specific

Mitigation: only generic check primitives are allowed. Task-specific knowledge
must come from `ExecutionContract`, not checker code.

### Risk: Too much schema slows iteration

Mitigation: implement pure classifier and artifact checks first. Keep records
small in model-visible prompts; full records live in proof artifacts.

### Risk: Existing tests depend on old frontier fields

Mitigation: no backward compatibility requirement. Update tests to the new
source of truth rather than preserving old projections. If model-visible
frontier fields remain, derive them from `FailureClassification`.

### Risk: Exit code dominates artifact evidence incorrectly

Mitigation: classification uses both. Nonzero exit remains a fact, but required
artifact checks may be the dominant next-action driver when `role=runtime` or
`verifier_required=true`.

## Why Not Just Add More Markers?

Because the observed failure is not the literal string `NO_FRAME`. The observed
failure is:

```text
runtime verifier executed
required artifact was declared or inferable
artifact did not exist or was stale after the verifier
```

Text markers are a lossy way to approximate that relation. The expected
artifact contract represents the relation directly.

## Relation To Existing Designs

This design supersedes the marker bridge added after the 2026-05-06
`make-doom-for-mips` provider-id replay miss.

It extends `DESIGN_2026-05-03_M6_24_EXECUTION_CONTRACT.md` with concrete
artifact and classification records. It does not replace generic managed exec;
it consumes its command lifecycle output.

It should be implemented before another broad M6.24 measurement batch if the
current same-shape runtime/artifact gap remains active.
