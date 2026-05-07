"""Structured execution evidence for implement_v2.

This module is intentionally pure for M6.24 Phase 1. It defines the
expected-artifact execution records and deterministic reducers without touching
the filesystem or the live tool runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

EXECUTION_CONTRACT_SCHEMA_VERSION = 3
COMMAND_RUN_SCHEMA_VERSION = 1
TOOL_RUN_RECORD_SCHEMA_VERSION = 1
ARTIFACT_EVIDENCE_SCHEMA_VERSION = 1
VERIFIER_EVIDENCE_SCHEMA_VERSION = 1
FAILURE_CLASSIFICATION_SCHEMA_VERSION = 1

Role = Literal[
    "setup",
    "source",
    "dependency",
    "build",
    "test",
    "runtime",
    "artifact_probe",
    "verify",
    "cleanup",
    "diagnostic",
    "compound",
    "unknown",
]
Purpose = Literal[
    "source_acquisition",
    "source_authority_readback",
    "configure",
    "dependency_generation",
    "build",
    "runtime_build",
    "runtime_install",
    "smoke",
    "artifact_proof",
    "verification",
    "diagnostic",
    "cleanup",
    "generic_command",
]
Stage = Literal[
    "source_acquisition",
    "source_authority",
    "configure",
    "dependency_generation",
    "build",
    "runtime_build",
    "runtime_install",
    "default_smoke",
    "custom_runtime_smoke",
    "artifact_proof",
    "verification",
    "diagnostic",
    "cleanup",
    "command",
]
ProofRole = Literal[
    "none",
    "progress",
    "source_authority",
    "dependency_strategy",
    "target_build",
    "runtime_install",
    "default_smoke",
    "custom_runtime_smoke",
    "final_artifact",
    "verifier",
    "negative_diagnostic",
]
AcceptanceKind = Literal[
    "not_acceptance",
    "progress_only",
    "candidate_source_authority",
    "candidate_artifact_proof",
    "candidate_runtime_smoke",
    "candidate_final_proof",
    "external_verifier",
]
RiskClass = Literal[
    "read_only",
    "network_read",
    "build_mutation",
    "source_tree_mutation",
    "runtime_install",
    "system_mutation",
    "destructive",
    "unknown",
]
ExpectedExitMode = Literal["zero", "nonzero", "any", "code_set"]
ArtifactKind = Literal[
    "file",
    "directory",
    "glob",
    "stdout",
    "stderr",
    "json",
    "image",
    "binary",
    "executable",
    "report",
    "log",
]
ArtifactFreshness = Literal[
    "exists_before_or_after",
    "created_after_run_start",
    "modified_after_run_start",
    "modified_after_previous_check",
]
ArtifactSource = Literal["model_declared", "task_contract_inherited", "runtime_inferred"]
Confidence = Literal["high", "medium", "low"]
ToolRunStatus = Literal[
    "queued",
    "running",
    "yielded",
    "completed",
    "failed",
    "timed_out",
    "interrupted",
    "killed",
    "backgrounded",
    "orphaned",
    "pre_spawn_error",
    "contract_rejected",
]
SemanticExitCategory = Literal[
    "ok",
    "nonzero_exit",
    "timeout",
    "interrupted",
    "killed",
    "pre_spawn_error",
    "contract_rejected",
    "tool_contract_recovery",
    "unknown",
]
SemanticExitSource = Literal["default", "known_command", "contract_override", "verifier_policy"]
VerifierVerdict = Literal["pass", "fail", "partial", "unknown"]
FailurePhase = Literal[
    "setup",
    "source",
    "dependency",
    "build",
    "test",
    "runtime",
    "artifact",
    "verification",
    "internal",
    "unknown",
]
FailureKind = Literal[
    "pre_spawn_error",
    "permission_error",
    "sandbox_error",
    "contract_rejected",
    "timeout",
    "interrupted",
    "killed",
    "nonzero_exit",
    "missing_artifact",
    "stale_artifact",
    "schema_mismatch",
    "verifier_failed",
    "partial_evidence",
    "unknown_failure",
]
FailureClass = Literal[
    "build_failure",
    "test_failure",
    "runtime_failure",
    "artifact_validation_failure",
    "build_artifact_missing",
    "runtime_artifact_missing",
    "verification_failure",
    "internal_failure",
    "unknown_failure",
]

ROLES = set(Role.__args__)
PURPOSES = set(Purpose.__args__)
STAGES = set(Stage.__args__)
PROOF_ROLES = set(ProofRole.__args__)
ACCEPTANCE_KINDS = set(AcceptanceKind.__args__)
RISK_CLASSES = set(RiskClass.__args__)
EXPECTED_EXIT_MODES = set(ExpectedExitMode.__args__)
ARTIFACT_KINDS = set(ArtifactKind.__args__)
ARTIFACT_FRESHNESS = set(ArtifactFreshness.__args__)
ARTIFACT_SOURCES = set(ArtifactSource.__args__)
TOOL_RUN_STATUSES = set(ToolRunStatus.__args__)
FAILURE_CLASSES = set(FailureClass.__args__)
FAILURE_KINDS = set(FailureKind.__args__)
FAILURE_PHASES = set(FailurePhase.__args__)
ROLE_ALIASES = {
    # These are model-facing source/frontier roles that sometimes leak into
    # execution_contract.role. Keep them as compatibility aliases rather than
    # expanding the execution contract vocabulary.
    "primary_source": "source",
    "runtime_harness": "runtime",
    "build_file": "build",
    "test_harness": "test",
    "toolchain_probe": "dependency",
    "final_verifier": "verify",
}
PROOF_ROLE_ALIASES = {
    "final_verifier": "verifier",
    "artifact_verifier": "final_artifact",
}
ACCEPTANCE_KIND_ALIASES = {
    "final_verification": "external_verifier",
    "runtime_verification": "external_verifier",
    "artifact_verification": "external_verifier",
    "artifact_and_runtime_verification": "external_verifier",
}

TERMINAL_TOOL_STATUSES = frozenset(
    {
        "completed",
        "failed",
        "timed_out",
        "interrupted",
        "killed",
        "orphaned",
        "pre_spawn_error",
        "contract_rejected",
    }
)
NONTERMINAL_TOOL_STATUSES = frozenset({"queued", "running", "yielded", "backgrounded"})
ALLOWED_ACCEPTANCE_BY_PROOF: dict[str, frozenset[str]] = {
    "none": frozenset({"not_acceptance", "progress_only"}),
    "progress": frozenset({"progress_only", "not_acceptance"}),
    "source_authority": frozenset({"candidate_source_authority", "candidate_final_proof"}),
    "dependency_strategy": frozenset({"not_acceptance", "progress_only"}),
    "target_build": frozenset({"progress_only", "candidate_artifact_proof", "candidate_final_proof"}),
    "runtime_install": frozenset({"progress_only", "candidate_final_proof"}),
    "default_smoke": frozenset({"candidate_runtime_smoke", "candidate_final_proof", "external_verifier"}),
    "custom_runtime_smoke": frozenset({"candidate_runtime_smoke", "external_verifier"}),
    "final_artifact": frozenset({"candidate_artifact_proof", "candidate_final_proof", "external_verifier"}),
    "verifier": frozenset({"external_verifier", "candidate_final_proof"}),
    "negative_diagnostic": frozenset({"not_acceptance", "progress_only"}),
}


@dataclass(frozen=True)
class ExecutionSubstep:
    id: str
    role: Role = "unknown"
    stage: Stage = "command"
    purpose: Purpose = "generic_command"
    proof_role: ProofRole = "none"
    acceptance_kind: AcceptanceKind = "not_acceptance"
    declared_target_refs: tuple[dict[str, Any], ...] = ()
    expected_exit: dict[str, Any] = field(default_factory=lambda: {"mode": "zero"})
    requires_artifacts: tuple[str, ...] = ()
    produces_artifacts: tuple[str, ...] = ()
    verifier_required: bool = False
    source_authority_requirement: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "role": self.role,
            "stage": self.stage,
            "purpose": self.purpose,
            "proof_role": self.proof_role,
            "acceptance_kind": self.acceptance_kind,
            "declared_target_refs": [dict(ref) for ref in self.declared_target_refs],
            "expected_exit": dict(self.expected_exit),
            "requires_artifacts": list(self.requires_artifacts),
            "produces_artifacts": list(self.produces_artifacts),
            "verifier_required": self.verifier_required,
            "source_authority_requirement": dict(self.source_authority_requirement),
        }


@dataclass(frozen=True)
class ExpectedArtifact:
    id: str
    kind: ArtifactKind = "file"
    target: dict[str, Any] = field(default_factory=dict)
    path: str = ""
    required: bool = True
    source: ArtifactSource = "model_declared"
    confidence: Confidence = "high"
    producer_substep_id: str = ""
    freshness: ArtifactFreshness = "exists_before_or_after"
    checks: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": dict(self.target),
            "path": self.path,
            "required": self.required,
            "source": self.source,
            "confidence": self.confidence,
            "producer_substep_id": self.producer_substep_id,
            "freshness": self.freshness,
            "checks": [dict(check) for check in self.checks],
        }


@dataclass(frozen=True)
class ExecutionContract:
    id: str
    role: Role = "unknown"
    stage: Stage = "command"
    purpose: Purpose = "generic_command"
    proof_role: ProofRole = "none"
    acceptance_kind: AcceptanceKind = "not_acceptance"
    expected_exit: dict[str, Any] = field(default_factory=lambda: {"mode": "zero"})
    expected_artifacts: tuple[ExpectedArtifact, ...] = ()
    substeps: tuple[ExecutionSubstep, ...] = ()
    verifier_required: bool = False
    risk_class: RiskClass = "unknown"
    declared_target_refs: tuple[dict[str, Any], ...] = ()
    source_authority_requirement: dict[str, Any] = field(default_factory=dict)
    resume_identity: dict[str, Any] = field(default_factory=dict)
    continuation_policy: dict[str, Any] = field(default_factory=dict)
    background_policy: dict[str, Any] = field(default_factory=dict)
    affected_paths: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    notes: str = ""
    schema_version: int = EXECUTION_CONTRACT_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "role": self.role,
            "stage": self.stage,
            "purpose": self.purpose,
            "proof_role": self.proof_role,
            "acceptance_kind": self.acceptance_kind,
            "expected_exit": dict(self.expected_exit),
            "expected_artifacts": [artifact.as_dict() for artifact in self.expected_artifacts],
            "substeps": [substep.as_dict() for substep in self.substeps],
            "verifier_required": self.verifier_required,
            "risk_class": self.risk_class,
            "declared_target_refs": [dict(ref) for ref in self.declared_target_refs],
            "source_authority_requirement": dict(self.source_authority_requirement),
            "resume_identity": dict(self.resume_identity),
            "continuation_policy": dict(self.continuation_policy),
            "background_policy": dict(self.background_policy),
            "affected_paths": list(self.affected_paths),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "notes": self.notes,
        }

    def substep_by_id(self, substep_id: object) -> ExecutionSubstep | None:
        wanted = str(substep_id or "")
        if not wanted:
            return None
        for substep in self.substeps:
            if substep.id == wanted:
                return substep
        return None

    def artifact_by_id(self, artifact_id: object) -> ExpectedArtifact | None:
        wanted = str(artifact_id or "")
        if not wanted:
            return None
        for artifact in self.expected_artifacts:
            if artifact.id == wanted:
                return artifact
        return None

    def producer_substep_for_artifact(self, artifact_id: object) -> ExecutionSubstep | None:
        artifact = self.artifact_by_id(artifact_id)
        if artifact is None:
            return None
        return self.substep_by_id(artifact.producer_substep_id)


@dataclass(frozen=True)
class CommandRun:
    command_run_id: str
    contract_id: str = ""
    started_at: str = ""
    status: ToolRunStatus = "queued"
    record_ids: tuple[str, ...] = ()
    terminal_record_id: str = ""
    schema_version: int = COMMAND_RUN_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_run_id": self.command_run_id,
            "contract_id": self.contract_id,
            "started_at": self.started_at,
            "status": self.status,
            "record_ids": list(self.record_ids),
            "terminal_record_id": self.terminal_record_id,
        }


@dataclass(frozen=True)
class ToolRunRecord:
    record_id: str
    command_run_id: str
    provider_call_id: str = ""
    declared_tool_name: str = ""
    effective_tool_name: str = ""
    contract_id: str = ""
    substep_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_seconds: float | None = None
    status: ToolRunStatus = "completed"
    exit_code: int | None = None
    timed_out: bool = False
    interrupted: bool = False
    semantic_exit: dict[str, Any] = field(default_factory=dict)
    stdout_ref: str = ""
    stderr_ref: str = ""
    combined_output_ref: str = ""
    stdout_preview: str = ""
    stderr_preview: str = ""
    output_truncated: bool = False
    tool_contract_recovery: dict[str, Any] | None = None
    terminal_failure_reaction_eligible: bool = True
    schema_version: int = TOOL_RUN_RECORD_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "command_run_id": self.command_run_id,
            "provider_call_id": self.provider_call_id,
            "declared_tool_name": self.declared_tool_name,
            "effective_tool_name": self.effective_tool_name,
            "tool_contract_recovery": (
                dict(self.tool_contract_recovery) if isinstance(self.tool_contract_recovery, dict) else None
            ),
            "terminal_failure_reaction_eligible": self.terminal_failure_reaction_eligible,
            "contract_id": self.contract_id,
            "substep_id": self.substep_id or None,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "status": self.status,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "interrupted": self.interrupted,
            "semantic_exit": dict(self.semantic_exit),
            "stdout_ref": self.stdout_ref,
            "stderr_ref": self.stderr_ref,
            "combined_output_ref": self.combined_output_ref,
            "stdout_preview": self.stdout_preview,
            "stderr_preview": self.stderr_preview,
            "output_truncated": self.output_truncated,
        }


@dataclass(frozen=True)
class ArtifactEvidence:
    evidence_id: str
    artifact_id: str
    command_run_id: str
    tool_run_record_id: str
    contract_id: str = ""
    substep_id: str = ""
    target: dict[str, Any] = field(default_factory=dict)
    path: str = ""
    kind: ArtifactKind = "file"
    required: bool = True
    source: ArtifactSource = "model_declared"
    confidence: Confidence = "high"
    freshness: ArtifactFreshness = "exists_before_or_after"
    pre_run_stat: dict[str, Any] = field(default_factory=dict)
    post_run_stat: dict[str, Any] = field(default_factory=dict)
    checks: tuple[dict[str, Any], ...] = ()
    status: Literal["passed", "failed", "partial"] = "passed"
    blocking: bool = False
    schema_version: int = ARTIFACT_EVIDENCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "artifact_id": self.artifact_id,
            "command_run_id": self.command_run_id,
            "tool_run_record_id": self.tool_run_record_id,
            "contract_id": self.contract_id,
            "substep_id": self.substep_id or None,
            "target": dict(self.target),
            "path": self.path,
            "kind": self.kind,
            "required": self.required,
            "source": self.source,
            "confidence": self.confidence,
            "freshness": self.freshness,
            "pre_run_stat": dict(self.pre_run_stat),
            "post_run_stat": dict(self.post_run_stat),
            "checks": [dict(check) for check in self.checks],
            "status": self.status,
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class VerifierEvidence:
    verifier_id: str
    contract_id: str
    verdict: VerifierVerdict
    reason: str = ""
    checks: tuple[dict[str, Any], ...] = ()
    missing_evidence: tuple[dict[str, Any], ...] = ()
    schema_version: int = VERIFIER_EVIDENCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "verifier_id": self.verifier_id,
            "contract_id": self.contract_id,
            "verdict": self.verdict,
            "reason": self.reason,
            "checks": [dict(check) for check in self.checks],
            "missing_evidence": [dict(item) for item in self.missing_evidence],
        }


@dataclass(frozen=True)
class FailureClassification:
    classification_id: str
    phase: FailurePhase
    kind: FailureKind
    failure_class: FailureClass
    confidence: Confidence = "low"
    retryable: bool = True
    summary: str = ""
    secondary_classes: tuple[FailureClass, ...] = ()
    secondary_kinds: tuple[FailureKind, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()
    required_next_probe: str = ""
    schema_version: int = FAILURE_CLASSIFICATION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "classification_id": self.classification_id,
            "phase": self.phase,
            "kind": self.kind,
            "class": self.failure_class,
            "secondary_classes": list(self.secondary_classes),
            "secondary_kinds": list(self.secondary_kinds),
            "confidence": self.confidence,
            "retryable": self.retryable,
            "summary": self.summary,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "required_next_probe": self.required_next_probe,
        }


@dataclass(frozen=True)
class FinishGateResult:
    blocked: bool
    reasons: tuple[str, ...] = ()
    evidence_refs: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "blocked": self.blocked,
            "reasons": list(self.reasons),
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
        }


def normalize_execution_contract(
    value: object,
    *,
    task_contract: Mapping[str, Any] | None = None,
    frontier_state: Mapping[str, Any] | None = None,
) -> ExecutionContract:
    """Normalize provider/user contract JSON into the v3 pure dataclass."""

    raw = _mapping(value)
    expected_artifacts = tuple(_normalize_expected_artifact(item) for item in _list(raw.get("expected_artifacts")))
    if not expected_artifacts:
        expected_artifacts = _infer_expected_artifacts(task_contract=task_contract, frontier_state=frontier_state)
    substeps = tuple(_normalize_substep(item) for item in _list(raw.get("substeps")))
    return ExecutionContract(
        id=str(raw.get("id") or raw.get("contract_id") or "contract:unknown"),
        role=_normalize_contract_role(raw),
        stage=_enum(raw.get("stage"), STAGES, "command"),
        purpose=_enum(raw.get("purpose"), PURPOSES, "generic_command"),
        proof_role=_normalize_proof_role(raw.get("proof_role")),
        acceptance_kind=_normalize_acceptance_kind(raw.get("acceptance_kind")),
        expected_exit=_normalize_expected_exit(raw.get("expected_exit")),
        expected_artifacts=expected_artifacts,
        substeps=substeps,
        verifier_required=bool(raw.get("verifier_required")),
        risk_class=_enum(raw.get("risk_class"), RISK_CLASSES, "unknown"),
        declared_target_refs=_tuple_dicts(raw.get("declared_target_refs")),
        source_authority_requirement=dict(_mapping(raw.get("source_authority_requirement"))),
        resume_identity=dict(_mapping(raw.get("resume_identity"))),
        continuation_policy=dict(_mapping(raw.get("continuation_policy"))),
        background_policy=dict(_mapping(raw.get("background_policy"))),
        affected_paths=tuple(str(item) for item in _list(raw.get("affected_paths")) if str(item)),
        evidence_refs=_tuple_dicts(raw.get("evidence_refs")),
        notes=str(raw.get("notes") or ""),
    )


def semantic_exit_from_run(record: ToolRunRecord | Mapping[str, Any], contract: ExecutionContract | Mapping[str, Any]) -> dict[str, Any]:
    """Resolve semantic exit from status/exit code and contract expected_exit."""

    run = _tool_run_record(record)
    normalized_contract = contract if isinstance(contract, ExecutionContract) else normalize_execution_contract(contract)
    expected_exit = _expected_exit_for_record(run, normalized_contract)
    status_category = _semantic_category_from_status(run)
    if status_category != "unknown":
        return {
            "ok": False,
            "category": status_category,
            "source": "default",
            "message": status_category.replace("_", " "),
        }
    if run.status not in TERMINAL_TOOL_STATUSES:
        return {"ok": False, "category": "unknown", "source": "default", "message": f"nonterminal status {run.status}"}
    mode = _enum(expected_exit.get("mode"), EXPECTED_EXIT_MODES, "zero")
    exit_code = run.exit_code
    if mode == "any":
        return {"ok": True, "category": "ok", "source": "contract_override", "message": "any exit accepted"}
    if exit_code is None:
        return {"ok": False, "category": "unknown", "source": "default", "message": "no exit code"}
    if mode == "zero":
        ok = exit_code == 0
        return _semantic_exit(ok=ok, exit_code=exit_code, source="default")
    if mode == "nonzero":
        ok = exit_code != 0
        return _semantic_exit(ok=ok, exit_code=exit_code, source="contract_override")
    codes = {int(code) for code in _list(expected_exit.get("codes")) if _is_int_like(code)}
    ok = exit_code in codes
    return _semantic_exit(ok=ok, exit_code=exit_code, source="contract_override")


def derive_verifier_evidence(
    contract: ExecutionContract | Mapping[str, Any],
    tool_runs: tuple[ToolRunRecord | Mapping[str, Any], ...] | list[ToolRunRecord | Mapping[str, Any]],
    artifact_evidence: tuple[ArtifactEvidence | Mapping[str, Any], ...] | list[ArtifactEvidence | Mapping[str, Any]],
) -> VerifierEvidence:
    """Derive a deterministic verifier verdict from structured run/evidence."""

    normalized_contract = contract if isinstance(contract, ExecutionContract) else normalize_execution_contract(contract)
    runs = tuple(_tool_run_record(record) for record in tool_runs)
    artifacts = tuple(_artifact_evidence(record) for record in artifact_evidence)
    checks: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    failed = False
    partial = False
    invalid_pairs = _invalid_proof_acceptance_pairs(normalized_contract)
    if invalid_pairs:
        failed = True
        checks.append(
            {
                "id": f"{normalized_contract.id}:proof_acceptance",
                "passed": False,
                "observed": {"invalid_pairs": invalid_pairs},
                "expected": {"valid_proof_acceptance_pair": True},
                "message": "invalid proof_role/acceptance_kind pair",
            }
        )

    for run in runs:
        if run.status in NONTERMINAL_TOOL_STATUSES:
            partial = True
            missing.append({"kind": "tool_run_terminal", "command_run_id": run.command_run_id, "record_id": run.record_id})
            continue
        semantic_exit = semantic_exit_from_run(run, normalized_contract)
        if not bool(semantic_exit.get("ok")):
            failed = True
            checks.append(
                {
                    "id": f"{run.record_id}:semantic_exit",
                    "passed": False,
                    "command_run_ids": [run.command_run_id],
                    "tool_run_record_ids": [run.record_id],
                    "observed": {"semantic_exit": semantic_exit},
                    "expected": {"ok": True},
                    "message": semantic_exit.get("message") or "semantic exit failed",
                }
            )

    evidence_artifact_ids = {artifact.artifact_id for artifact in artifacts}
    for expected in normalized_contract.expected_artifacts:
        if expected.required and expected.id not in evidence_artifact_ids:
            partial = True
            missing.append({"kind": "artifact_evidence", "artifact_id": expected.id})

    for artifact in artifacts:
        if not _artifact_required_by_contract(artifact, normalized_contract) and not artifact.blocking:
            continue
        if artifact.status == "partial":
            partial = True
            missing.append({"kind": "artifact_evidence", "artifact_evidence_id": artifact.evidence_id})
        elif artifact.blocking or artifact.status == "failed":
            failed = True
            checks.append(
                {
                    "id": artifact.evidence_id,
                    "passed": False,
                    "command_run_ids": [artifact.command_run_id],
                    "tool_run_record_ids": [artifact.tool_run_record_id],
                    "artifact_evidence_ids": [artifact.evidence_id],
                    "observed": {"status": artifact.status, "blocking": artifact.blocking},
                    "expected": {"status": "passed"},
                    "message": f"artifact {artifact.artifact_id} failed required checks",
                }
            )

    if failed:
        verdict: VerifierVerdict = "fail"
        reason = "required run or artifact evidence failed"
    elif partial:
        verdict = "partial"
        reason = "required evidence is missing or nonterminal"
    elif normalized_contract.verifier_required and not runs and not artifacts:
        verdict = "partial"
        reason = "verifier is required but no run or artifact evidence exists"
    elif normalized_contract.verifier_required or any(artifact.required for artifact in artifacts):
        verdict = "pass"
        reason = "required structured evidence passed"
    else:
        verdict = "unknown"
        reason = "no contract-backed verifier obligation exists"
    return VerifierEvidence(
        verifier_id=f"verifier:{normalized_contract.id}",
        contract_id=normalized_contract.id,
        verdict=verdict,
        reason=reason,
        checks=tuple(checks),
        missing_evidence=tuple(missing),
    )


def classify_execution_failure(
    record: ToolRunRecord | Mapping[str, Any] | None,
    artifact_evidence: tuple[ArtifactEvidence | Mapping[str, Any], ...] | list[ArtifactEvidence | Mapping[str, Any]] = (),
    verifier_evidence: VerifierEvidence | Mapping[str, Any] | None = None,
    contract: ExecutionContract | Mapping[str, Any] | None = None,
) -> FailureClassification:
    """Classify the primary next-action driver from structured evidence."""

    normalized_contract = (
        contract
        if isinstance(contract, ExecutionContract)
        else normalize_execution_contract(contract or {"id": "contract:unknown"})
    )
    run = _tool_run_record(record) if record is not None else None
    artifacts = tuple(_artifact_evidence(item) for item in artifact_evidence)
    verifier = _verifier_evidence(verifier_evidence) if verifier_evidence is not None else None
    evidence_refs: list[dict[str, Any]] = []
    secondary_classes: list[FailureClass] = []
    secondary_kinds: list[FailureKind] = []

    if run is not None:
        evidence_refs.extend(
            (
                {"kind": "tool_run_record", "id": run.record_id},
                {"kind": "command_run", "id": run.command_run_id},
            )
        )
        if run.status in {"pre_spawn_error", "contract_rejected"}:
            kind: FailureKind = "pre_spawn_error" if run.status == "pre_spawn_error" else "contract_rejected"
            return _classification(
                contract_id=normalized_contract.id,
                phase="internal",
                kind=kind,
                failure_class="internal_failure",
                confidence="high",
                summary=f"tool did not execute: {kind}",
                evidence_refs=tuple(evidence_refs),
            )
        status_kind = _failure_kind_from_terminal_status(run.status)
        if status_kind is not None:
            return _classification(
                contract_id=normalized_contract.id,
                phase=_phase_for_record(run, normalized_contract),
                kind=status_kind,
                failure_class=_failure_class_for_semantic_role(_role_for_record(run, normalized_contract)),
                confidence="high",
                summary=f"tool run {run.record_id} ended with {run.status}",
                evidence_refs=tuple(evidence_refs),
            )

    unreachable_input = _unreachable_input_for_failed_artifacts(artifacts, normalized_contract)
    if unreachable_input is not None:
        failed_later_artifact, required_artifact_id = unreachable_input
        evidence_refs.append({"kind": "artifact_evidence", "id": failed_later_artifact.evidence_id})
        required_artifact = normalized_contract.artifact_by_id(required_artifact_id)
        producer_substep = normalized_contract.producer_substep_for_artifact(required_artifact_id)
        phase = _phase_for_role(producer_substep.role if producer_substep is not None else "artifact")
        failure_class: FailureClass = (
            "build_artifact_missing" if producer_substep is not None and producer_substep.role == "build" else "artifact_validation_failure"
        )
        concrete_required_failure = failed_later_artifact.artifact_id == required_artifact_id
        return _classification(
            contract_id=normalized_contract.id,
            phase=phase,
            kind=(
                (
                    "partial_evidence"
                    if failed_later_artifact.status == "partial"
                    else ("stale_artifact" if _artifact_is_stale(failed_later_artifact) else "missing_artifact")
                )
                if concrete_required_failure
                else "partial_evidence"
            ),
            failure_class=failure_class,
            confidence=(
                _confidence_for_artifact(failed_later_artifact, normalized_contract)
                if concrete_required_failure
                else _confidence_for_expected_artifact(required_artifact)
            ),
            summary=f"required input artifact {required_artifact_id} lacks passing evidence before later substep",
            secondary_classes=("runtime_artifact_missing",),
            secondary_kinds=("missing_artifact",),
            evidence_refs=tuple(evidence_refs),
            required_next_probe="Prove the required input artifact before treating the later runtime artifact as primary.",
        )

    failed_artifact = _primary_failed_artifact(artifacts, normalized_contract)
    if failed_artifact is not None:
        evidence_refs.append({"kind": "artifact_evidence", "id": failed_artifact.evidence_id})
        if run is not None:
            semantic_exit = semantic_exit_from_run(run, normalized_contract)
            if not bool(semantic_exit.get("ok")):
                secondary_classes.append(_failure_class_for_semantic_role(_role_for_record(run, normalized_contract)))
                secondary_kinds.append(_kind_from_semantic_exit(semantic_exit))
        artifact_is_partial = failed_artifact.status == "partial"
        failure_class = "artifact_validation_failure" if artifact_is_partial else _failure_class_for_artifact(failed_artifact, normalized_contract)
        kind = "partial_evidence" if artifact_is_partial else ("stale_artifact" if _artifact_is_stale(failed_artifact) else "missing_artifact")
        phase = _phase_for_artifact(failed_artifact, normalized_contract)
        return _classification(
            contract_id=normalized_contract.id,
            phase=phase,
            kind=kind,
            failure_class=failure_class,
            confidence=_confidence_for_artifact(failed_artifact, normalized_contract),
            summary=f"required artifact {failed_artifact.artifact_id} failed structured checks",
            secondary_classes=tuple(dict.fromkeys(secondary_classes)),
            secondary_kinds=tuple(dict.fromkeys(secondary_kinds)),
            evidence_refs=tuple(evidence_refs),
            required_next_probe="Inspect the producing substep and artifact path before another rebuild.",
        )

    if run is not None:
        semantic_exit = semantic_exit_from_run(run, normalized_contract)
        if not bool(semantic_exit.get("ok")) and run.status in TERMINAL_TOOL_STATUSES:
            return _classification(
                contract_id=normalized_contract.id,
                phase=_phase_for_record(run, normalized_contract),
                kind=_kind_from_semantic_exit(semantic_exit),
                failure_class=_failure_class_for_semantic_role(_role_for_record(run, normalized_contract)),
                confidence="high",
                summary=str(semantic_exit.get("message") or "semantic exit failed"),
                evidence_refs=tuple(evidence_refs),
            )

    if verifier is not None and verifier.verdict in {"fail", "partial"}:
        kind = "partial_evidence" if verifier.verdict == "partial" else "verifier_failed"
        return _classification(
            contract_id=normalized_contract.id,
            phase="verification",
            kind=kind,
            failure_class="verification_failure",
            confidence="high",
            summary=verifier.reason or f"verifier verdict {verifier.verdict}",
            evidence_refs=({"kind": "verifier_evidence", "id": verifier.verifier_id},),
        )

    return _classification(
        contract_id=normalized_contract.id,
        phase="unknown",
        kind="unknown_failure",
        failure_class="unknown_failure",
        confidence="low",
        retryable=False,
        summary="no structured failure evidence",
    )


def apply_finish_gate(
    contract: ExecutionContract | Mapping[str, Any],
    verifier_evidence: VerifierEvidence | Mapping[str, Any] | None,
    classifications: tuple[FailureClassification | Mapping[str, Any], ...] | list[FailureClassification | Mapping[str, Any]],
) -> FinishGateResult:
    """Return whether finish should be blocked by structured evidence."""

    normalized_contract = contract if isinstance(contract, ExecutionContract) else normalize_execution_contract(contract)
    reasons: list[str] = []
    evidence_refs: list[dict[str, Any]] = []
    verifier = _verifier_evidence(verifier_evidence) if verifier_evidence is not None else None
    if verifier is not None and verifier.verdict in {"fail", "partial"}:
        reasons.append(f"verifier_{verifier.verdict}")
        evidence_refs.append({"kind": "verifier_evidence", "id": verifier.verifier_id})
    for item in classifications:
        classification = _failure_classification(item)
        if classification.failure_class != "unknown_failure":
            reasons.append(classification.failure_class)
            evidence_refs.extend(classification.evidence_refs)
    if normalized_contract.verifier_required and verifier is None:
        reasons.append("verifier_evidence_missing")
    return FinishGateResult(blocked=bool(reasons), reasons=tuple(dict.fromkeys(reasons)), evidence_refs=tuple(evidence_refs))


def _normalize_contract_role(raw: Mapping[str, Any]) -> Role:
    role = _enum(raw.get("role"), ROLES, "")
    if role:
        return role
    raw_role = _enum_text(raw.get("role"))
    if raw_role == "generated_artifact":
        if _raw_contract_is_build_artifact_intent(raw):
            return "build"
        if _raw_contract_is_runtime_artifact_intent(raw):
            return "runtime"
        return "artifact_probe"
    aliased = ROLE_ALIASES.get(raw_role)
    if aliased:
        return aliased  # type: ignore[return-value]
    return "unknown"


def _normalize_proof_role(value: object) -> ProofRole:
    proof_role = _enum(value, PROOF_ROLES, "")
    if proof_role:
        return proof_role
    aliased = PROOF_ROLE_ALIASES.get(_enum_text(value), "")
    return _enum(aliased, PROOF_ROLES, "none")


def _normalize_acceptance_kind(value: object) -> AcceptanceKind:
    acceptance_kind = _enum(value, ACCEPTANCE_KINDS, "")
    if acceptance_kind:
        return acceptance_kind
    aliased = ACCEPTANCE_KIND_ALIASES.get(_enum_text(value), "")
    return _enum(aliased, ACCEPTANCE_KINDS, "not_acceptance")


def _raw_contract_is_runtime_artifact_intent(raw: Mapping[str, Any]) -> bool:
    purpose = _enum(raw.get("purpose"), PURPOSES, "")
    stage = _enum(raw.get("stage"), STAGES, "")
    proof_role = _normalize_proof_role(raw.get("proof_role"))
    acceptance_kind = _normalize_acceptance_kind(raw.get("acceptance_kind"))
    return (
        purpose in {"runtime_build", "runtime_install", "smoke", "verification", "artifact_proof"}
        or stage in {"runtime_build", "runtime_install", "default_smoke", "custom_runtime_smoke", "artifact_proof", "verification"}
        or proof_role in {"runtime_install", "default_smoke", "custom_runtime_smoke", "final_artifact", "verifier"}
        or acceptance_kind in {"candidate_runtime_smoke", "candidate_final_proof", "external_verifier"}
    )


def _raw_contract_is_build_artifact_intent(raw: Mapping[str, Any]) -> bool:
    purpose = _enum(raw.get("purpose"), PURPOSES, "")
    stage = _enum(raw.get("stage"), STAGES, "")
    proof_role = _normalize_proof_role(raw.get("proof_role"))
    return purpose in {"build", "runtime_build"} or stage in {"build", "runtime_build"} or proof_role == "target_build"


def _normalize_substep(value: object) -> ExecutionSubstep:
    raw = _mapping(value)
    return ExecutionSubstep(
        id=str(raw.get("id") or ""),
        role=_normalize_contract_role(raw),
        stage=_enum(raw.get("stage"), STAGES, "command"),
        purpose=_enum(raw.get("purpose"), PURPOSES, "generic_command"),
        proof_role=_normalize_proof_role(raw.get("proof_role")),
        acceptance_kind=_normalize_acceptance_kind(raw.get("acceptance_kind")),
        declared_target_refs=_tuple_dicts(raw.get("declared_target_refs")),
        expected_exit=_normalize_expected_exit(raw.get("expected_exit")),
        requires_artifacts=tuple(str(item) for item in _list(raw.get("requires_artifacts")) if str(item)),
        produces_artifacts=tuple(str(item) for item in _list(raw.get("produces_artifacts")) if str(item)),
        verifier_required=bool(raw.get("verifier_required")),
        source_authority_requirement=dict(_mapping(raw.get("source_authority_requirement"))),
    )


def _normalize_expected_artifact(value: object) -> ExpectedArtifact:
    raw = _mapping(value)
    target = _normalize_artifact_target(raw)
    path = str(raw.get("path") or target.get("path") or "")
    stream = str(raw.get("stream") or target.get("stream") or "")
    artifact_id = str(raw.get("id") or path or stream or "artifact")
    source = _enum(raw.get("source"), ARTIFACT_SOURCES, "model_declared")
    confidence = _enum(raw.get("confidence"), {"high", "medium", "low"}, "high")
    if source == "runtime_inferred" and confidence == "high":
        confidence = "medium"
    kind_default = stream if stream in {"stdout", "stderr"} else "file"
    return ExpectedArtifact(
        id=artifact_id,
        kind=_enum(raw.get("kind"), ARTIFACT_KINDS, kind_default),
        target=target,
        path=path,
        required=bool(raw.get("required", True)),
        source=source,
        confidence=confidence,
        producer_substep_id=str(raw.get("producer_substep_id") or ""),
        freshness=_enum(raw.get("freshness"), ARTIFACT_FRESHNESS, "exists_before_or_after"),
        checks=_normalize_artifact_checks(raw.get("checks")),
    )


def _normalize_artifact_target(raw: Mapping[str, Any]) -> dict[str, Any]:
    target_value = raw.get("target")
    raw_stream = str(raw.get("stream") or "")
    raw_path = str(raw.get("path") or "")
    if isinstance(target_value, str):
        stream = _normalize_stream_name(target_value)
        if stream:
            return {"type": "stream", "stream": stream}
        return {"type": "path", "path": target_value}
    target = dict(_mapping(target_value))
    stream = _normalize_stream_name(raw_stream or target.get("stream") or target.get("type"))
    if stream:
        normalized = {key: value for key, value in target.items() if key != "path"}
        normalized["type"] = "stream"
        normalized["stream"] = stream
        return normalized
    path = str(raw_path or target.get("path") or "")
    if path:
        normalized = dict(target)
        normalized.setdefault("type", "path")
        normalized["path"] = path
        return normalized
    return target


def _normalize_stream_name(value: object) -> str:
    text = _enum_text(value).removeprefix("stream:")
    return text if text in {"stdout", "stderr"} else ""


def _normalize_artifact_checks(value: object) -> tuple[dict[str, Any], ...]:
    checks: list[dict[str, Any]] = []
    for item in (_mapping(item) for item in _list(value)):
        if not item:
            continue
        check = dict(item)
        check_type = _normalize_artifact_check_type(check)
        check["type"] = check_type
        if check_type == "text_contains" and "text" not in check:
            if "value" in check:
                check["text"] = check["value"]
            elif "expected" in check:
                check["text"] = check["expected"]
        elif check_type == "regex" and "pattern" not in check:
            if "value" in check:
                check["pattern"] = check["value"]
            elif "expected" in check:
                check["pattern"] = check["expected"]
        checks.append(check)
    return tuple(checks)


def _normalize_artifact_check_type(check: Mapping[str, Any]) -> str:
    explicit = _enum_text(check.get("type") or check.get("kind") or check.get("check"))
    aliases = {
        "contains": "text_contains",
        "text": "text_contains",
        "not_empty": "non_empty",
        "nonempty": "non_empty",
        "matches": "regex",
        "regexp": "regex",
    }
    if explicit:
        return aliases.get(explicit, explicit)
    for shorthand in ("non_empty", "text_contains", "regex", "json_schema", "kind", "size_between", "mtime_after", "exists"):
        if shorthand in check:
            return shorthand
    return "exists"


def _infer_expected_artifacts(
    *,
    task_contract: Mapping[str, Any] | None,
    frontier_state: Mapping[str, Any] | None,
) -> tuple[ExpectedArtifact, ...]:
    for source in (task_contract, frontier_state):
        raw = _mapping(source)
        if isinstance(raw.get("expected_artifacts"), (list, tuple)):
            return tuple(
                _normalize_expected_artifact({**_mapping(item), "source": _mapping(item).get("source") or "runtime_inferred"})
                for item in _list(raw.get("expected_artifacts"))
            )
        for key in ("final_artifact", "output_artifact", "required_artifact"):
            if raw.get(key):
                value = raw[key]
                if isinstance(value, Mapping):
                    artifact = {**dict(value), "source": value.get("source") or "runtime_inferred"}
                else:
                    artifact = {"id": str(value), "path": str(value), "kind": "file", "source": "runtime_inferred"}
                return (_normalize_expected_artifact(artifact),)
    return ()


def _tool_run_record(value: ToolRunRecord | Mapping[str, Any]) -> ToolRunRecord:
    if isinstance(value, ToolRunRecord):
        return value
    raw = _mapping(value)
    record_id = str(raw.get("record_id") or raw.get("tool_run_record_id") or "tool-run-record:unknown")
    command_run_id = str(raw.get("command_run_id") or "")
    return ToolRunRecord(
        record_id=record_id,
        command_run_id=command_run_id,
        provider_call_id=str(raw.get("provider_call_id") or ""),
        declared_tool_name=str(raw.get("declared_tool_name") or raw.get("tool_name") or ""),
        effective_tool_name=str(raw.get("effective_tool_name") or raw.get("tool_name") or ""),
        contract_id=str(raw.get("contract_id") or ""),
        substep_id=str(raw.get("substep_id") or ""),
        started_at=str(raw.get("started_at") or ""),
        finished_at=str(raw.get("finished_at") or ""),
        duration_seconds=_optional_float(raw.get("duration_seconds")),
        status=_enum(raw.get("status"), TOOL_RUN_STATUSES, "completed"),
        exit_code=_optional_int(raw.get("exit_code")),
        timed_out=bool(raw.get("timed_out")),
        interrupted=bool(raw.get("interrupted")),
        semantic_exit=dict(_mapping(raw.get("semantic_exit"))),
        stdout_ref=str(raw.get("stdout_ref") or ""),
        stderr_ref=str(raw.get("stderr_ref") or ""),
        combined_output_ref=str(raw.get("combined_output_ref") or ""),
        stdout_preview=str(raw.get("stdout_preview") or ""),
        stderr_preview=str(raw.get("stderr_preview") or ""),
        output_truncated=bool(raw.get("output_truncated")),
        tool_contract_recovery=dict(_mapping(raw.get("tool_contract_recovery"))) if raw.get("tool_contract_recovery") else None,
        terminal_failure_reaction_eligible=bool(raw.get("terminal_failure_reaction_eligible", True)),
    )


def _artifact_evidence(value: ArtifactEvidence | Mapping[str, Any]) -> ArtifactEvidence:
    if isinstance(value, ArtifactEvidence):
        return value
    raw = _mapping(value)
    return ArtifactEvidence(
        evidence_id=str(raw.get("evidence_id") or raw.get("artifact_id") or "artifact-evidence:unknown"),
        artifact_id=str(raw.get("artifact_id") or ""),
        command_run_id=str(raw.get("command_run_id") or ""),
        tool_run_record_id=str(raw.get("tool_run_record_id") or ""),
        contract_id=str(raw.get("contract_id") or ""),
        substep_id=str(raw.get("substep_id") or ""),
        target=dict(_mapping(raw.get("target"))),
        path=str(raw.get("path") or ""),
        kind=_enum(raw.get("kind"), ARTIFACT_KINDS, "file"),
        required=bool(raw.get("required", True)),
        source=_enum(raw.get("source"), ARTIFACT_SOURCES, "model_declared"),
        confidence=_enum(raw.get("confidence"), {"high", "medium", "low"}, "high"),
        freshness=_enum(raw.get("freshness"), ARTIFACT_FRESHNESS, "exists_before_or_after"),
        pre_run_stat=dict(_mapping(raw.get("pre_run_stat"))),
        post_run_stat=dict(_mapping(raw.get("post_run_stat"))),
        checks=_tuple_dicts(raw.get("checks")),
        status=_enum(raw.get("status"), {"passed", "failed", "partial"}, "passed"),
        blocking=bool(raw.get("blocking")),
    )


def _verifier_evidence(value: VerifierEvidence | Mapping[str, Any]) -> VerifierEvidence:
    if isinstance(value, VerifierEvidence):
        return value
    raw = _mapping(value)
    return VerifierEvidence(
        verifier_id=str(raw.get("verifier_id") or "verifier:unknown"),
        contract_id=str(raw.get("contract_id") or ""),
        verdict=_enum(raw.get("verdict"), {"pass", "fail", "partial", "unknown"}, "unknown"),
        reason=str(raw.get("reason") or ""),
        checks=_tuple_dicts(raw.get("checks")),
        missing_evidence=_tuple_dicts(raw.get("missing_evidence")),
    )


def _failure_classification(value: FailureClassification | Mapping[str, Any]) -> FailureClassification:
    if isinstance(value, FailureClassification):
        return value
    raw = _mapping(value)
    return FailureClassification(
        classification_id=str(raw.get("classification_id") or "failure:unknown"),
        phase=_enum(raw.get("phase"), FAILURE_PHASES, "unknown"),
        kind=_enum(raw.get("kind"), FAILURE_KINDS, "unknown_failure"),
        failure_class=_enum(raw.get("class") or raw.get("failure_class"), FAILURE_CLASSES, "unknown_failure"),
        confidence=_enum(raw.get("confidence"), {"high", "medium", "low"}, "low"),
        retryable=bool(raw.get("retryable", True)),
        summary=str(raw.get("summary") or ""),
        secondary_classes=tuple(_enum(item, FAILURE_CLASSES, "unknown_failure") for item in _list(raw.get("secondary_classes"))),
        secondary_kinds=tuple(_enum(item, FAILURE_KINDS, "unknown_failure") for item in _list(raw.get("secondary_kinds"))),
        evidence_refs=_tuple_dicts(raw.get("evidence_refs")),
        required_next_probe=str(raw.get("required_next_probe") or ""),
    )


def _expected_exit_for_record(run: ToolRunRecord, contract: ExecutionContract) -> dict[str, Any]:
    substep = contract.substep_by_id(run.substep_id)
    if substep is not None:
        return dict(substep.expected_exit)
    return dict(contract.expected_exit)


def _semantic_category_from_status(run: ToolRunRecord) -> SemanticExitCategory:
    if run.timed_out or run.status == "timed_out":
        return "timeout"
    if run.interrupted or run.status == "interrupted":
        return "interrupted"
    if run.status == "killed":
        return "killed"
    if run.status == "pre_spawn_error":
        return "pre_spawn_error"
    if run.status == "contract_rejected":
        return "contract_rejected"
    return "unknown"


def _semantic_exit(*, ok: bool, exit_code: int, source: SemanticExitSource) -> dict[str, Any]:
    if ok:
        return {"ok": True, "category": "ok", "source": source, "message": f"exit code {exit_code} accepted"}
    return {"ok": False, "category": "nonzero_exit", "source": source, "message": f"exit code {exit_code}"}


def _failure_kind_from_terminal_status(status: str) -> FailureKind | None:
    if status == "timed_out":
        return "timeout"
    if status == "interrupted":
        return "interrupted"
    if status == "killed":
        return "killed"
    return None


def _role_for_record(run: ToolRunRecord, contract: ExecutionContract) -> Role:
    substep = contract.substep_by_id(run.substep_id)
    if substep is not None:
        return substep.role
    return contract.role


def _phase_for_record(run: ToolRunRecord, contract: ExecutionContract) -> FailurePhase:
    return _phase_for_role(_role_for_record(run, contract))


def _phase_for_role(role: str) -> FailurePhase:
    if role in {"setup", "source", "dependency", "build", "test", "runtime"}:
        return role  # type: ignore[return-value]
    if role in {"verify", "artifact_probe"}:
        return "verification" if role == "verify" else "artifact"
    return "unknown"


def _failure_class_for_semantic_role(role: str) -> FailureClass:
    if role == "build":
        return "build_failure"
    if role == "test":
        return "test_failure"
    if role == "runtime":
        return "runtime_failure"
    if role == "verify":
        return "verification_failure"
    return "internal_failure" if role in {"setup", "unknown"} else "unknown_failure"


def _primary_failed_artifact(artifacts: tuple[ArtifactEvidence, ...], contract: ExecutionContract) -> ArtifactEvidence | None:
    failed = tuple(
        artifact
        for artifact in artifacts
        if (_artifact_required_by_contract(artifact, contract) and artifact.status in {"failed", "partial"}) or artifact.blocking
    )
    if not failed:
        return None
    artifact_by_id = {artifact.artifact_id: artifact for artifact in failed}
    for substep in contract.substeps:
        for required_artifact_id in substep.requires_artifacts:
            if required_artifact_id in artifact_by_id:
                return artifact_by_id[required_artifact_id]
        for produced_artifact_id in substep.produces_artifacts:
            if produced_artifact_id in artifact_by_id:
                return artifact_by_id[produced_artifact_id]
    return failed[0]


def _unreachable_input_for_failed_artifacts(
    artifacts: tuple[ArtifactEvidence, ...],
    contract: ExecutionContract,
) -> tuple[ArtifactEvidence, str] | None:
    passed_artifact_ids = {
        artifact.artifact_id
        for artifact in artifacts
        if artifact.status == "passed" and not artifact.blocking
    }
    failed_artifacts = tuple(
        artifact
        for artifact in artifacts
        if (_artifact_required_by_contract(artifact, contract) and artifact.status in {"failed", "partial"}) or artifact.blocking
    )
    if not failed_artifacts:
        return None
    artifact_by_id = {artifact.artifact_id: artifact for artifact in artifacts}
    for artifact in failed_artifacts:
        substep = contract.substep_by_id(artifact.substep_id) or contract.producer_substep_for_artifact(artifact.artifact_id)
        if substep is None:
            continue
        for required_artifact_id in substep.requires_artifacts:
            required_evidence = artifact_by_id.get(required_artifact_id)
            if required_evidence is not None and (
                (_artifact_required_by_contract(required_evidence, contract) and required_evidence.status in {"failed", "partial"})
                or required_evidence.blocking
            ):
                return required_evidence, required_artifact_id
            if required_artifact_id not in passed_artifact_ids:
                return artifact, required_artifact_id
    return None


def _failure_class_for_artifact(artifact: ArtifactEvidence, contract: ExecutionContract) -> FailureClass:
    substep = contract.substep_by_id(artifact.substep_id) or contract.producer_substep_for_artifact(artifact.artifact_id)
    role = substep.role if substep is not None else contract.role
    if role == "runtime":
        return "runtime_artifact_missing"
    if role == "build":
        return "build_artifact_missing"
    return "artifact_validation_failure"


def _artifact_required_by_contract(artifact: ArtifactEvidence, contract: ExecutionContract) -> bool:
    expected_artifact = contract.artifact_by_id(artifact.artifact_id)
    return artifact.required or (expected_artifact is not None and expected_artifact.required)


def _phase_for_artifact(artifact: ArtifactEvidence, contract: ExecutionContract) -> FailurePhase:
    substep = contract.substep_by_id(artifact.substep_id) or contract.producer_substep_for_artifact(artifact.artifact_id)
    return _phase_for_role(substep.role if substep is not None else contract.role)


def _artifact_is_stale(artifact: ArtifactEvidence) -> bool:
    if artifact.freshness not in {"created_after_run_start", "modified_after_run_start", "modified_after_previous_check"}:
        return False
    for check in artifact.checks:
        check_type = str(check.get("type") or "")
        if check_type in {"mtime_after", "freshness"} and check.get("passed") is False:
            return True
    return artifact.status == "failed" and bool(artifact.post_run_stat.get("exists"))


def _confidence_for_artifact(artifact: ArtifactEvidence, contract: ExecutionContract) -> Confidence:
    expected_artifact = contract.artifact_by_id(artifact.artifact_id)
    if artifact.source == "runtime_inferred" or (expected_artifact is not None and expected_artifact.source == "runtime_inferred"):
        return "medium"
    return artifact.confidence


def _confidence_for_expected_artifact(artifact: ExpectedArtifact | None) -> Confidence:
    if artifact is not None and artifact.source == "runtime_inferred":
        return "medium"
    return "low"


def _invalid_proof_acceptance_pairs(contract: ExecutionContract) -> tuple[dict[str, str], ...]:
    invalid: list[dict[str, str]] = []
    _append_invalid_pair(
        invalid,
        location="contract",
        purpose=contract.purpose,
        proof_role=contract.proof_role,
        acceptance_kind=contract.acceptance_kind,
    )
    for substep in contract.substeps:
        _append_invalid_pair(
            invalid,
            location=substep.id,
            purpose=substep.purpose,
            proof_role=substep.proof_role,
            acceptance_kind=substep.acceptance_kind,
        )
    return tuple(invalid)


def _append_invalid_pair(
    invalid: list[dict[str, str]],
    *,
    location: str,
    purpose: str,
    proof_role: str,
    acceptance_kind: str,
) -> None:
    if proof_role == "final_artifact" and acceptance_kind == "not_acceptance" and purpose == "diagnostic":
        return
    allowed = ALLOWED_ACCEPTANCE_BY_PROOF.get(proof_role, frozenset())
    if acceptance_kind not in allowed:
        invalid.append({"location": location, "proof_role": proof_role, "acceptance_kind": acceptance_kind})


def _kind_from_semantic_exit(semantic_exit: Mapping[str, Any]) -> FailureKind:
    category = str(semantic_exit.get("category") or "")
    return _enum(category, FAILURE_KINDS, "unknown_failure")


def _classification(
    *,
    contract_id: str,
    phase: FailurePhase,
    kind: FailureKind,
    failure_class: FailureClass,
    confidence: Confidence,
    summary: str,
    retryable: bool = True,
    secondary_classes: tuple[FailureClass, ...] = (),
    secondary_kinds: tuple[FailureKind, ...] = (),
    evidence_refs: tuple[dict[str, Any], ...] = (),
    required_next_probe: str = "",
) -> FailureClassification:
    return FailureClassification(
        classification_id=f"failure:{contract_id}",
        phase=phase,
        kind=kind,
        failure_class=failure_class,
        confidence=confidence,
        retryable=retryable,
        summary=summary,
        secondary_classes=secondary_classes,
        secondary_kinds=secondary_kinds,
        evidence_refs=evidence_refs,
        required_next_probe=required_next_probe,
    )


def _normalize_expected_exit(value: object) -> dict[str, Any]:
    raw = dict(_mapping(value))
    mode = _enum(raw.get("mode"), EXPECTED_EXIT_MODES, "zero")
    normalized: dict[str, Any] = {"mode": mode}
    if mode == "code_set":
        normalized["codes"] = [int(code) for code in _list(raw.get("codes")) if _is_int_like(code)]
    return normalized


def _tuple_dicts(value: object) -> tuple[dict[str, Any], ...]:
    return tuple(dict(item) for item in (_mapping(item) for item in _list(value)) if item)


def _mapping(value: object) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _enum_text(value: object) -> str:
    return str(value or "").strip().lower()


def _enum(value: object, allowed: set[str], default: str) -> Any:
    text = _enum_text(value)
    return text if text in allowed else default


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if _is_int_like(value):
        return int(value)
    return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_int_like(value: object) -> bool:
    try:
        int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return True


__all__ = [
    "ACCEPTANCE_KINDS",
    "ARTIFACT_EVIDENCE_SCHEMA_VERSION",
    "ARTIFACT_FRESHNESS",
    "ARTIFACT_KINDS",
    "ARTIFACT_SOURCES",
    "COMMAND_RUN_SCHEMA_VERSION",
    "EXECUTION_CONTRACT_SCHEMA_VERSION",
    "EXPECTED_EXIT_MODES",
    "FAILURE_CLASSIFICATION_SCHEMA_VERSION",
    "FAILURE_CLASSES",
    "FAILURE_KINDS",
    "FAILURE_PHASES",
    "PROOF_ROLES",
    "RISK_CLASSES",
    "ROLES",
    "STAGES",
    "TOOL_RUN_RECORD_SCHEMA_VERSION",
    "TOOL_RUN_STATUSES",
    "VERIFIER_EVIDENCE_SCHEMA_VERSION",
    "ArtifactEvidence",
    "CommandRun",
    "ExecutionContract",
    "ExecutionSubstep",
    "ExpectedArtifact",
    "FailureClassification",
    "FinishGateResult",
    "ToolRunRecord",
    "VerifierEvidence",
    "apply_finish_gate",
    "classify_execution_failure",
    "derive_verifier_evidence",
    "normalize_execution_contract",
    "semantic_exit_from_run",
]
