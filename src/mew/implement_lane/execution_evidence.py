"""Structured execution evidence for implement_v2.

This module is intentionally pure for M6.24 Phase 1. It defines the
expected-artifact execution records and deterministic reducers without touching
the filesystem or the live tool runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, Sequence

EXECUTION_CONTRACT_SCHEMA_VERSION = 3
COMMAND_RUN_SCHEMA_VERSION = 1
TOOL_RUN_RECORD_SCHEMA_VERSION = 1
ARTIFACT_EVIDENCE_SCHEMA_VERSION = 1
VERIFIER_EVIDENCE_SCHEMA_VERSION = 1
FAILURE_CLASSIFICATION_SCHEMA_VERSION = 1
TYPED_ACCEPTANCE_SCHEMA_VERSION = 1

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
OracleObligationKind = Literal[
    "artifact_exists",
    "artifact_fresh",
    "visual_dimension",
    "visual_similarity",
    "verifier_pass",
    "source_grounding",
]
EvidenceEventKind = Literal[
    "tool_result",
    "artifact_check",
    "oracle_check",
    "verifier_result",
    "source_grounding",
    "failure_classification",
    "structured_finish_gate",
    "cleanup",
]
EvidenceEventStatus = Literal["passed", "failed", "partial", "unknown"]
DoneDecisionKind = Literal["allow_complete", "block_continue", "no_typed_decision"]
DoneDecisionGateSource = Literal["typed_evidence", "legacy_string_safety", "none"]

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
ORACLE_OBLIGATION_KINDS = set(OracleObligationKind.__args__)
EVIDENCE_EVENT_KINDS = set(EvidenceEventKind.__args__)
EVIDENCE_EVENT_STATUSES = set(EvidenceEventStatus.__args__)
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


@dataclass(frozen=True)
class OracleObligation:
    id: str
    kind: OracleObligationKind
    subject: dict[str, Any]
    expected: dict[str, Any]
    source: str
    provenance_refs: tuple[dict[str, Any], ...] = ()
    candidate_derived_allowed: bool = False
    required: bool = True
    schema_version: int = TYPED_ACCEPTANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "subject": dict(self.subject),
            "expected": dict(self.expected),
            "source": self.source,
            "provenance_refs": [dict(ref) for ref in self.provenance_refs],
            "candidate_derived_allowed": self.candidate_derived_allowed,
            "required": self.required,
        }


@dataclass(frozen=True)
class OracleBundle:
    id: str
    source: str
    obligations: tuple[OracleObligation, ...]
    provenance_refs: tuple[dict[str, Any], ...] = ()
    schema_version: int = TYPED_ACCEPTANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "source": self.source,
            "obligations": [obligation.as_dict() for obligation in self.obligations],
            "provenance_refs": [dict(ref) for ref in self.provenance_refs],
        }


@dataclass(frozen=True)
class EvidenceEvent:
    id: str
    kind: EvidenceEventKind
    status: EvidenceEventStatus
    observed: dict[str, Any]
    refs: tuple[dict[str, Any], ...] = ()
    contract_id: str = ""
    oracle_id: str = ""
    obligation_id: str = ""
    tool_call_id: str = ""
    provider_call_id: str = ""
    command_run_id: str = ""
    tool_run_record_id: str = ""
    freshness: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    supersedes: tuple[str, ...] = ()
    schema_version: int = TYPED_ACCEPTANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "observed": dict(self.observed),
            "refs": [dict(ref) for ref in self.refs],
            "contract_id": self.contract_id,
            "oracle_id": self.oracle_id,
            "obligation_id": self.obligation_id,
            "tool_call_id": self.tool_call_id,
            "provider_call_id": self.provider_call_id,
            "command_run_id": self.command_run_id,
            "tool_run_record_id": self.tool_run_record_id,
            "freshness": dict(self.freshness),
            "provenance": dict(self.provenance),
            "supersedes": list(self.supersedes),
        }


@dataclass(frozen=True)
class FinishClaim:
    outcome: str
    summary: str = ""
    evidence_refs: tuple[dict[str, Any], ...] = ()
    oracle_refs: tuple[str, ...] = ()
    legacy_acceptance_checks: tuple[dict[str, Any], ...] = ()
    schema_version: int = TYPED_ACCEPTANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "outcome": self.outcome,
            "summary": self.summary,
            "evidence_refs": [dict(ref) for ref in self.evidence_refs],
            "oracle_refs": list(self.oracle_refs),
            "legacy_acceptance_checks": [dict(check) for check in self.legacy_acceptance_checks],
        }


@dataclass(frozen=True)
class DoneDecision:
    decision: DoneDecisionKind
    gate_source: DoneDecisionGateSource
    missing_obligations: tuple[dict[str, Any], ...] = ()
    failed_evidence_refs: tuple[dict[str, Any], ...] = ()
    stale_evidence_refs: tuple[dict[str, Any], ...] = ()
    invalid_evidence_refs: tuple[dict[str, Any], ...] = ()
    blockers: tuple[dict[str, Any], ...] = ()
    continuation_prompt: str = ""
    schema_version: int = TYPED_ACCEPTANCE_SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision": self.decision,
            "gate_source": self.gate_source,
            "missing_obligations": [dict(item) for item in self.missing_obligations],
            "failed_evidence_refs": [dict(item) for item in self.failed_evidence_refs],
            "stale_evidence_refs": [dict(item) for item in self.stale_evidence_refs],
            "invalid_evidence_refs": [dict(item) for item in self.invalid_evidence_refs],
            "blockers": [dict(item) for item in self.blockers],
            "continuation_prompt": self.continuation_prompt,
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
        terminal_artifact_failure = _primary_failed_artifact(artifacts, normalized_contract)
        if status_kind is not None and not _terminal_failure_should_defer_to_artifact(
            run,
            terminal_artifact_failure,
            normalized_contract,
        ):
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


def evidence_events_from_tool_payload(
    *,
    tool_index: int,
    tool_name: str,
    tool_status: str,
    provider_call_id: str,
    payload: Mapping[str, Any],
) -> tuple[EvidenceEvent, ...]:
    """Reduce an existing v2 tool result payload into replay-stable typed events."""

    events: list[EvidenceEvent] = []
    raw_tool_record = payload.get("tool_run_record")
    tool_record = _tool_run_record(raw_tool_record) if isinstance(raw_tool_record, Mapping) else None
    command_run_id = str(payload.get("command_run_id") or "")
    if tool_record is not None:
        command_run_id = tool_record.command_run_id or command_run_id
        events.append(
            EvidenceEvent(
                id=f"ev:tool:{tool_record.command_run_id}:{tool_record.record_id}",
                kind="tool_result",
                status=_event_status_from_tool_record(tool_record),
                observed={
                    "tool_name": tool_name,
                    "tool_status": tool_status,
                    "exit_code": tool_record.exit_code,
                    "timed_out": tool_record.timed_out,
                    "semantic_exit": dict(tool_record.semantic_exit),
                },
                refs=(
                    {"kind": "tool_run_record", "id": tool_record.record_id},
                    {"kind": "command_run", "id": tool_record.command_run_id},
                ),
                contract_id=tool_record.contract_id,
                provider_call_id=provider_call_id or tool_record.provider_call_id,
                command_run_id=tool_record.command_run_id,
                tool_run_record_id=tool_record.record_id,
                freshness={"started_at": tool_record.started_at, "finished_at": tool_record.finished_at},
            )
        )
    for raw_artifact in _list(payload.get("artifact_evidence")):
        if not isinstance(raw_artifact, Mapping):
            continue
        artifact = _artifact_evidence(raw_artifact)
        events.append(
            EvidenceEvent(
                id=f"ev:artifact:{artifact.evidence_id}",
                kind="artifact_check",
                status=_event_status_from_artifact(artifact),
                observed={
                    "artifact_id": artifact.artifact_id,
                    "path": artifact.path,
                    "kind": artifact.kind,
                    "status": artifact.status,
                    "blocking": artifact.blocking,
                    "checks": [dict(check) for check in artifact.checks],
                    "post_run_stat": dict(artifact.post_run_stat),
                },
                refs=(
                    {"kind": "artifact_evidence", "id": artifact.evidence_id},
                    {"kind": "command_run", "id": artifact.command_run_id},
                    {"kind": "tool_run_record", "id": artifact.tool_run_record_id},
                ),
                contract_id=artifact.contract_id,
                provider_call_id=provider_call_id,
                command_run_id=artifact.command_run_id,
                tool_run_record_id=artifact.tool_run_record_id,
                freshness={
                    "freshness": artifact.freshness,
                    "pre_run_stat": dict(artifact.pre_run_stat),
                    "post_run_stat": dict(artifact.post_run_stat),
                },
                provenance={"source": artifact.source, "confidence": artifact.confidence},
            )
        )
        events.extend(_oracle_check_events_from_artifact(artifact, provider_call_id=provider_call_id))
    raw_verifier = payload.get("verifier_evidence")
    if isinstance(raw_verifier, Mapping):
        verifier = _verifier_evidence(raw_verifier)
        events.append(
            EvidenceEvent(
                id=f"ev:verifier:{verifier.verifier_id}",
                kind="verifier_result",
                status=_event_status_from_verifier(verifier),
                observed={
                    "verdict": verifier.verdict,
                    "reason": verifier.reason,
                    "checks": [dict(check) for check in verifier.checks],
                    "missing_evidence": [dict(item) for item in verifier.missing_evidence],
                },
                refs=({"kind": "verifier_evidence", "id": verifier.verifier_id},),
                contract_id=verifier.contract_id,
                provider_call_id=provider_call_id,
                command_run_id=command_run_id,
                tool_run_record_id=tool_record.record_id if tool_record is not None else "",
            )
        )
    raw_classification = payload.get("failure_classification")
    if isinstance(raw_classification, Mapping):
        classification = _failure_classification(raw_classification)
        events.append(
            EvidenceEvent(
                id=f"ev:failure:{classification.classification_id}",
                kind="failure_classification",
                status=("unknown" if classification.failure_class == "unknown_failure" else "failed"),
                observed=classification.as_dict(),
                refs=tuple(dict(ref) for ref in classification.evidence_refs),
                contract_id=str(_mapping(payload.get("execution_contract_normalized")).get("id") or ""),
                provider_call_id=provider_call_id,
                command_run_id=command_run_id,
                tool_run_record_id=tool_record.record_id if tool_record is not None else "",
            )
        )
    raw_finish_gate = payload.get("structured_finish_gate")
    if isinstance(raw_finish_gate, Mapping):
        blocked = bool(raw_finish_gate.get("blocked"))
        events.append(
            EvidenceEvent(
                id=f"ev:finish_gate:{command_run_id or provider_call_id or tool_index}",
                kind="structured_finish_gate",
                status="failed" if blocked else "passed",
                observed=dict(raw_finish_gate),
                refs=_tuple_dicts(raw_finish_gate.get("evidence_refs")),
                provider_call_id=provider_call_id,
                command_run_id=command_run_id,
                tool_run_record_id=tool_record.record_id if tool_record is not None else "",
            )
        )
    return tuple(events)


def build_oracle_bundle(
    *,
    task_contract: Mapping[str, Any],
    execution_contracts: Sequence[Mapping[str, Any] | ExecutionContract] = (),
    verifier_evidence: Sequence[Mapping[str, Any] | VerifierEvidence] = (),
    artifact_evidence: Sequence[Mapping[str, Any] | ArtifactEvidence] = (),
    source_grounding_refs: Sequence[Mapping[str, Any]] = (),
) -> OracleBundle | None:
    """Build v0 typed acceptance obligations from structured sources only."""

    obligations: list[OracleObligation] = []
    provenance_refs: list[dict[str, Any]] = []
    normalized_contracts = tuple(
        item if isinstance(item, ExecutionContract) else normalize_execution_contract(item, task_contract=task_contract)
        for item in execution_contracts
    )
    non_completion_contract_ids: set[str] = set()
    completion_contracts_by_key: dict[tuple[str, ...], ExecutionContract] = {}
    for contract in normalized_contracts:
        provenance_refs.append({"kind": "execution_contract", "id": contract.id})
        contract_can_complete = contract.acceptance_kind not in {"not_acceptance", "progress_only"}
        if not contract_can_complete:
            non_completion_contract_ids.add(contract.id)
        else:
            completion_contracts_by_key[_oracle_completion_contract_key(contract)] = contract
    for contract in completion_contracts_by_key.values():
        for artifact in contract.expected_artifacts:
            obligations.extend(_obligations_from_expected_artifact(contract, artifact))
        if contract.verifier_required or contract.acceptance_kind == "external_verifier":
            obligations.append(
                OracleObligation(
                    id=f"oracle:{contract.id}:verifier_pass",
                    kind="verifier_pass",
                    subject={"contract_id": contract.id},
                    expected={"verdict": "pass"},
                    source="execution_contract",
                    provenance_refs=({"kind": "execution_contract", "id": contract.id},),
                )
            )
    for verifier in (_verifier_evidence(item) for item in verifier_evidence):
        if verifier.contract_id and verifier.contract_id in non_completion_contract_ids:
            continue
        provenance_refs.append({"kind": "verifier_evidence", "id": verifier.verifier_id})
        if verifier.verdict == "pass":
            obligations.append(
                OracleObligation(
                    id=f"oracle:{verifier.verifier_id}:verifier_pass",
                    kind="verifier_pass",
                    subject={"verifier_id": verifier.verifier_id, "contract_id": verifier.contract_id},
                    expected={"verdict": "pass"},
                    source="verifier_evidence",
                    provenance_refs=({"kind": "verifier_evidence", "id": verifier.verifier_id},),
                )
            )
    for ref in source_grounding_refs:
        path = str(ref.get("path") or ref.get("source_ref") or "").strip()
        if not path:
            continue
        obligations.append(
            OracleObligation(
                id=f"oracle:source:{_stable_token(path)}",
                kind="source_grounding",
                subject={"path": path},
                expected={"grounded": True},
                source=str(ref.get("source") or "source_grounding"),
                provenance_refs=(dict(ref),),
            )
        )
    if not obligations:
        return None
    bundle_id_source = "|".join(obligation.id for obligation in obligations[:16])
    return OracleBundle(
        id=f"oracle:bundle:{_stable_token(bundle_id_source)}",
        source="structured_execution_evidence",
        obligations=tuple(_dedupe_obligations(obligations)),
        provenance_refs=_unique_refs(provenance_refs),
    )


def _oracle_completion_contract_key(contract: ExecutionContract) -> tuple[str, ...]:
    artifact_targets = []
    for artifact in contract.expected_artifacts:
        target_path = str(artifact.path or artifact.target.get("path") or "").strip()
        artifact_targets.append(target_path or artifact.id)
    if artifact_targets:
        return ("artifacts", *sorted(str(item) for item in artifact_targets if str(item)))
    return ("contract", contract.id)


def resolve_typed_finish(
    finish_claim: FinishClaim | Mapping[str, Any],
    oracle_bundle: OracleBundle | Mapping[str, Any] | None,
    evidence_events: tuple[EvidenceEvent | Mapping[str, Any], ...] | list[EvidenceEvent | Mapping[str, Any]],
) -> DoneDecision:
    """Resolve completion from cited typed evidence ids."""

    claim = _finish_claim(finish_claim)
    bundle = _oracle_bundle(oracle_bundle) if oracle_bundle is not None else None
    if bundle is None:
        return DoneDecision(decision="no_typed_decision", gate_source="none")
    if claim.outcome not in {"completed", "task_complete", "done", "success"}:
        return DoneDecision(decision="allow_complete", gate_source="typed_evidence")
    events = tuple(_evidence_event(event) for event in evidence_events)
    event_by_id = {event.id: event for event in events}
    cited_ids = tuple(dict.fromkeys(_finish_claim_ref_ids(claim)))
    if not cited_ids:
        return _typed_block(
            code="missing_typed_evidence",
            message="Finish must cite typed evidence_refs for required oracle obligations.",
            missing_obligations=tuple(obligation.as_dict() for obligation in bundle.obligations if obligation.required),
        )
    invalid = tuple({"id": event_id, "reason": "not_found"} for event_id in cited_ids if event_id not in event_by_id)
    if invalid:
        return _typed_block(
            code="invalid_typed_evidence_ref",
            message="Finish cited typed evidence ids that do not exist.",
            invalid_evidence_refs=invalid,
        )
    cited_events = tuple(event_by_id[event_id] for event_id in cited_ids)
    failed_refs = tuple(_failed_event_ref(event) for event in cited_events if event.status in {"failed", "partial", "unknown"})
    if failed_refs:
        return _typed_block(
            code="failed_typed_evidence_ref",
            message="Finish cited failed, partial, or unknown typed evidence.",
            failed_evidence_refs=failed_refs,
        )
    missing: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for obligation in bundle.obligations:
        if not obligation.required:
            continue
        covering_event = _covering_event_for_obligation(obligation, cited_events)
        if covering_event is None:
            missing.append(obligation.as_dict())
            continue
        superseding_failure = _superseding_failed_event(obligation, covering_event, events)
        if superseding_failure is not None:
            failed.append(_failed_event_ref(superseding_failure))
    if missing or failed:
        return _typed_block(
            code="missing_typed_obligation",
            message="Finish is missing passing typed evidence for required oracle obligations.",
            missing_obligations=tuple(missing),
            failed_evidence_refs=tuple(failed),
        )
    return DoneDecision(decision="allow_complete", gate_source="typed_evidence")


def recommend_finish_evidence_refs(
    oracle_bundle: OracleBundle | Mapping[str, Any] | None,
    evidence_events: tuple[EvidenceEvent | Mapping[str, Any], ...] | list[EvidenceEvent | Mapping[str, Any]],
    *,
    include_supplemental: bool = True,
    limit: int = 16,
) -> tuple[dict[str, Any], ...]:
    """Return evidence refs that directly cover required finish obligations.

    This is intentionally obligation-driven. Picking the first N passing events
    is unstable for long sessions because final verifier/artifact evidence tends
    to arrive late in the trace.
    """

    if oracle_bundle is None:
        return ()
    bundle = _oracle_bundle(oracle_bundle)
    events = tuple(_evidence_event(event) for event in evidence_events)
    refs: list[dict[str, Any]] = []
    for obligation in bundle.obligations:
        if not obligation.required:
            continue
        covering_event = _covering_event_for_obligation(obligation, events)
        if covering_event is None:
            continue
        if _superseding_failed_event(obligation, covering_event, events) is not None:
            continue
        ref = {"kind": "evidence_event", "id": covering_event.id}
        if ref not in refs:
            refs.append(ref)
    if include_supplemental and len(refs) < limit:
        for event in reversed(events):
            if event.status != "passed":
                continue
            if event.kind not in {"verifier_result", "artifact_check", "oracle_check", "source_grounding"}:
                continue
            ref = {"kind": "evidence_event", "id": event.id}
            if ref not in refs:
                refs.append(ref)
            if len(refs) >= limit:
                break
    return tuple(refs[: max(0, limit)])


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
            if check.get("text_contains") is not None and not isinstance(check.get("text_contains"), bool):
                check["text"] = check["text_contains"]
            elif "value" in check:
                check["text"] = check["value"]
            elif "expected" in check:
                check["text"] = check["expected"]
        elif check_type == "regex" and "pattern" not in check:
            if check.get("regex") is not None and not isinstance(check.get("regex"), bool):
                check["pattern"] = check["regex"]
            elif "value" in check:
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


def _oracle_obligation(value: OracleObligation | Mapping[str, Any]) -> OracleObligation:
    if isinstance(value, OracleObligation):
        return value
    raw = _mapping(value)
    return OracleObligation(
        id=str(raw.get("id") or "oracle:obligation:unknown"),
        kind=_enum(raw.get("kind"), ORACLE_OBLIGATION_KINDS, "artifact_exists"),
        subject=dict(_mapping(raw.get("subject"))),
        expected=dict(_mapping(raw.get("expected"))),
        source=str(raw.get("source") or ""),
        provenance_refs=_tuple_dicts(raw.get("provenance_refs")),
        candidate_derived_allowed=bool(raw.get("candidate_derived_allowed")),
        required=bool(raw.get("required", True)),
    )


def _oracle_bundle(value: OracleBundle | Mapping[str, Any]) -> OracleBundle:
    if isinstance(value, OracleBundle):
        return value
    raw = _mapping(value)
    return OracleBundle(
        id=str(raw.get("id") or "oracle:bundle:unknown"),
        source=str(raw.get("source") or ""),
        obligations=tuple(_oracle_obligation(item) for item in _list(raw.get("obligations"))),
        provenance_refs=_tuple_dicts(raw.get("provenance_refs")),
    )


def _evidence_event(value: EvidenceEvent | Mapping[str, Any]) -> EvidenceEvent:
    if isinstance(value, EvidenceEvent):
        return value
    raw = _mapping(value)
    return EvidenceEvent(
        id=str(raw.get("id") or "ev:unknown"),
        kind=_enum(raw.get("kind"), EVIDENCE_EVENT_KINDS, "tool_result"),
        status=_enum(raw.get("status"), EVIDENCE_EVENT_STATUSES, "unknown"),
        observed=dict(_mapping(raw.get("observed"))),
        refs=_tuple_dicts(raw.get("refs")),
        contract_id=str(raw.get("contract_id") or ""),
        oracle_id=str(raw.get("oracle_id") or ""),
        obligation_id=str(raw.get("obligation_id") or ""),
        tool_call_id=str(raw.get("tool_call_id") or ""),
        provider_call_id=str(raw.get("provider_call_id") or ""),
        command_run_id=str(raw.get("command_run_id") or ""),
        tool_run_record_id=str(raw.get("tool_run_record_id") or ""),
        freshness=dict(_mapping(raw.get("freshness"))),
        provenance=dict(_mapping(raw.get("provenance"))),
        supersedes=tuple(str(item) for item in _list(raw.get("supersedes")) if str(item)),
    )


def _finish_claim(value: FinishClaim | Mapping[str, Any]) -> FinishClaim:
    if isinstance(value, FinishClaim):
        return value
    raw = _mapping(value)
    finish = _mapping(raw.get("finish")) if isinstance(raw.get("finish"), Mapping) else raw
    legacy_checks = _tuple_dicts(finish.get("acceptance_checks") or raw.get("acceptance_checks"))
    return FinishClaim(
        outcome=str(finish.get("outcome") or finish.get("status") or ""),
        summary=str(finish.get("summary") or raw.get("summary") or ""),
        evidence_refs=_finish_evidence_refs(finish.get("evidence_refs") or finish.get("evidence_ref")),
        oracle_refs=tuple(str(item) for item in _list(finish.get("oracle_refs")) if str(item)),
        legacy_acceptance_checks=legacy_checks,
    )


def _event_status_from_tool_record(record: ToolRunRecord) -> EvidenceEventStatus:
    if record.status in NONTERMINAL_TOOL_STATUSES:
        return "partial"
    semantic_exit = dict(record.semantic_exit)
    if semantic_exit:
        return "passed" if bool(semantic_exit.get("ok")) else "failed"
    return "passed" if record.status == "completed" and record.exit_code in {None, 0} else "failed"


def _event_status_from_artifact(artifact: ArtifactEvidence) -> EvidenceEventStatus:
    if artifact.status == "passed" and not artifact.blocking:
        return "passed"
    if artifact.status == "partial":
        return "partial"
    return "failed"


def _event_status_from_verifier(verifier: VerifierEvidence) -> EvidenceEventStatus:
    if verifier.verdict == "pass":
        return "passed"
    if verifier.verdict == "partial":
        return "partial"
    if verifier.verdict == "fail":
        return "failed"
    return "unknown"


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _visual_similarity_check_status(check: Mapping[str, Any], artifact: ArtifactEvidence) -> EvidenceEventStatus:
    observed = _mapping(check.get("observed"))
    expected = _mapping(check.get("expected"))
    reference = (
        check.get("reference_path")
        or check.get("reference")
        or expected.get("reference_path")
        or observed.get("reference_path")
    )
    score = _float_or_none(check.get("score") or observed.get("score"))
    threshold = _float_or_none(check.get("threshold") or expected.get("threshold"))
    if not reference or score is None or threshold is None:
        return "failed"
    comparator = str(check.get("comparator") or expected.get("comparator") or ">=").strip()
    if comparator in {">=", "gte", "at_least"}:
        passed = score >= threshold
    elif comparator in {">", "gt"}:
        passed = score > threshold
    elif comparator in {"<=", "lte", "at_most"}:
        passed = score <= threshold
    elif comparator in {"<", "lt"}:
        passed = score < threshold
    else:
        passed = score >= threshold
    if not bool(check.get("passed", artifact.status == "passed")):
        passed = False
    return "passed" if passed else "failed"


def _oracle_check_events_from_artifact(
    artifact: ArtifactEvidence,
    *,
    provider_call_id: str = "",
) -> tuple[EvidenceEvent, ...]:
    events: list[EvidenceEvent] = []
    for index, check in enumerate(artifact.checks):
        check_type = str(check.get("type") or check.get("kind") or "").casefold()
        if check_type in {"image_dimensions", "dimensions", "visual_dimension"}:
            obligation_id = f"oracle:{artifact.contract_id}:{artifact.artifact_id}:visual_dimension"
            events.append(
                EvidenceEvent(
                    id=f"ev:oracle:{obligation_id}:{artifact.evidence_id}:{index}",
                    kind="oracle_check",
                    status="passed" if bool(check.get("passed", artifact.status == "passed")) else "failed",
                    observed={
                        "kind": "visual_dimension",
                        "artifact_id": artifact.artifact_id,
                        "path": artifact.path,
                        "width": check.get("width") or _mapping(check.get("observed")).get("width"),
                        "height": check.get("height") or _mapping(check.get("observed")).get("height"),
                        "expected_width": check.get("expected_width") or _mapping(check.get("expected")).get("width"),
                        "expected_height": check.get("expected_height") or _mapping(check.get("expected")).get("height"),
                    },
                    refs=(
                        {"kind": "artifact_evidence", "id": artifact.evidence_id},
                        {"kind": "command_run", "id": artifact.command_run_id},
                    ),
                    contract_id=artifact.contract_id,
                    oracle_id=obligation_id,
                    obligation_id=obligation_id,
                    provider_call_id=provider_call_id,
                    command_run_id=artifact.command_run_id,
                    tool_run_record_id=artifact.tool_run_record_id,
                    provenance={"source": artifact.source, "confidence": artifact.confidence},
                )
            )
        elif check_type in {"visual_similarity", "similarity", "ssim"}:
            obligation_id = f"oracle:{artifact.contract_id}:{artifact.artifact_id}:visual_similarity"
            observed = _mapping(check.get("observed"))
            expected = _mapping(check.get("expected"))
            events.append(
                EvidenceEvent(
                    id=f"ev:oracle:{obligation_id}:{artifact.evidence_id}:{index}",
                    kind="oracle_check",
                    status=_visual_similarity_check_status(check, artifact),
                    observed={
                        "kind": "visual_similarity",
                        "artifact_id": artifact.artifact_id,
                        "candidate_path": artifact.path,
                        "reference_path": check.get("reference_path")
                        or check.get("reference")
                        or expected.get("reference_path")
                        or observed.get("reference_path"),
                        "metric": check.get("metric") or observed.get("metric") or check_type,
                        "score": check.get("score") or observed.get("score"),
                        "threshold": check.get("threshold") or expected.get("threshold"),
                        "comparator": check.get("comparator") or expected.get("comparator") or ">=",
                    },
                    refs=(
                        {"kind": "artifact_evidence", "id": artifact.evidence_id},
                        {"kind": "command_run", "id": artifact.command_run_id},
                    ),
                    contract_id=artifact.contract_id,
                    oracle_id=obligation_id,
                    obligation_id=obligation_id,
                    provider_call_id=provider_call_id,
                    command_run_id=artifact.command_run_id,
                    tool_run_record_id=artifact.tool_run_record_id,
                    provenance={"source": artifact.source, "confidence": artifact.confidence},
                )
            )
    return tuple(events)


def _obligations_from_expected_artifact(
    contract: ExecutionContract,
    artifact: ExpectedArtifact,
) -> tuple[OracleObligation, ...]:
    obligations: list[OracleObligation] = []
    if artifact.required:
        obligations.append(_expected_artifact_exists_obligation(contract.id, artifact))
    if artifact.required and artifact.freshness != "exists_before_or_after":
        obligations.append(
            OracleObligation(
                id=f"oracle:{contract.id}:{artifact.id}:fresh",
                kind="artifact_fresh",
                subject={"artifact_id": artifact.id, "path": artifact.path, "target": dict(artifact.target)},
                expected={"freshness": artifact.freshness},
                source="execution_contract",
                provenance_refs=({"kind": "execution_contract", "id": contract.id},),
            )
        )
    for check in artifact.checks:
        check_type = str(check.get("type") or "").casefold()
        if check_type in {"image_dimensions", "dimensions", "visual_dimension"}:
            expected = {
                key: check.get(key)
                for key in ("width", "height", "expected_width", "expected_height")
                if check.get(key) is not None
            }
            obligations.append(
                OracleObligation(
                    id=f"oracle:{contract.id}:{artifact.id}:visual_dimension",
                    kind="visual_dimension",
                    subject={"artifact_id": artifact.id, "path": artifact.path, "target": dict(artifact.target)},
                    expected=expected,
                    source="execution_contract",
                    provenance_refs=({"kind": "execution_contract", "id": contract.id},),
                )
            )
        if check_type in {"visual_similarity", "similarity", "ssim"}:
            reference = str(check.get("reference_path") or check.get("reference") or check.get("oracle_path") or "")
            expected = {
                "reference_path": reference,
                "metric": str(check.get("metric") or check_type),
                "threshold": check.get("threshold"),
                "comparator": str(check.get("comparator") or ">="),
            }
            if not reference:
                expected["missing_reference"] = True
            obligations.append(
                OracleObligation(
                    id=f"oracle:{contract.id}:{artifact.id}:visual_similarity",
                    kind="visual_similarity",
                    subject={"artifact_id": artifact.id, "path": artifact.path, "target": dict(artifact.target)},
                    expected=expected,
                    source="execution_contract",
                    provenance_refs=({"kind": "execution_contract", "id": contract.id},),
                )
            )
    return tuple(obligations)


def _expected_artifact_exists_obligation(contract_id: str, artifact: ExpectedArtifact) -> OracleObligation:
    return OracleObligation(
        id=f"oracle:{contract_id}:{artifact.id}:exists",
        kind="artifact_exists",
        subject={"artifact_id": artifact.id, "path": artifact.path, "target": dict(artifact.target)},
        expected={"exists": True},
        source="execution_contract",
        provenance_refs=({"kind": "execution_contract", "id": contract_id},),
    )


def _artifact_exists_obligation(source: str, contract_id: str, artifact: ArtifactEvidence) -> OracleObligation:
    return OracleObligation(
        id=f"oracle:{contract_id or 'artifact'}:{artifact.artifact_id}:exists",
        kind="artifact_exists",
        subject={"artifact_id": artifact.artifact_id, "path": artifact.path, "target": dict(artifact.target)},
        expected={"exists": True},
        source=source,
        provenance_refs=({"kind": "artifact_evidence", "id": artifact.evidence_id},),
    )


def _dedupe_obligations(obligations: list[OracleObligation]) -> list[OracleObligation]:
    seen: set[str] = set()
    deduped: list[OracleObligation] = []
    for obligation in obligations:
        if obligation.id in seen:
            continue
        seen.add(obligation.id)
        deduped.append(obligation)
    return deduped


def _finish_claim_ref_ids(claim: FinishClaim) -> list[str]:
    ids: list[str] = []
    for ref in claim.evidence_refs:
        value = str(ref.get("id") or ref.get("evidence_id") or ref.get("ref") or "").strip()
        if value:
            ids.append(value)
    return ids


def _typed_block(
    *,
    code: str,
    message: str,
    missing_obligations: tuple[dict[str, Any], ...] = (),
    failed_evidence_refs: tuple[dict[str, Any], ...] = (),
    invalid_evidence_refs: tuple[dict[str, Any], ...] = (),
) -> DoneDecision:
    blockers = ({"code": code, "message": message},)
    return DoneDecision(
        decision="block_continue",
        gate_source="typed_evidence",
        missing_obligations=missing_obligations,
        failed_evidence_refs=failed_evidence_refs,
        invalid_evidence_refs=invalid_evidence_refs,
        blockers=blockers,
        continuation_prompt=_typed_continuation_prompt(
            message=message,
            missing_obligations=missing_obligations,
            failed_evidence_refs=failed_evidence_refs,
            invalid_evidence_refs=invalid_evidence_refs,
        ),
    )


def _failed_event_ref(event: EvidenceEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "kind": event.kind,
        "status": event.status,
        "obligation_id": event.obligation_id,
        "observed": dict(event.observed),
    }


def _covering_event_for_obligation(
    obligation: OracleObligation,
    cited_events: tuple[EvidenceEvent, ...],
) -> EvidenceEvent | None:
    covering: EvidenceEvent | None = None
    for event in cited_events:
        if event.status != "passed":
            continue
        if event.obligation_id == obligation.id:
            if obligation.kind == "verifier_pass":
                if _event_matches_verifier_obligation(event, obligation):
                    covering = event
                continue
            if obligation.kind == "source_grounding":
                if _event_matches_source_grounding_obligation(event, obligation):
                    covering = event
                continue
            if obligation.kind in {"artifact_exists", "artifact_fresh"}:
                if _event_matches_artifact_obligation(event, obligation):
                    covering = event
                continue
            if obligation.kind == "visual_dimension":
                if _event_matches_visual_dimension_obligation(event, obligation):
                    covering = event
                continue
            if obligation.kind == "visual_similarity":
                if _event_matches_visual_similarity_obligation(event, obligation):
                    covering = event
                continue
            covering = event
            continue
        if obligation.kind == "verifier_pass" and event.kind == "verifier_result":
            if str(event.observed.get("verdict") or "") == "pass" and _event_matches_verifier_obligation(
                event,
                obligation,
            ):
                covering = event
        if obligation.kind in {"artifact_exists", "artifact_fresh"} and event.kind == "artifact_check":
            if _event_matches_artifact_obligation(event, obligation):
                covering = event
        if obligation.kind == "source_grounding" and event.kind == "source_grounding":
            if _event_matches_source_grounding_obligation(event, obligation):
                covering = event
        if obligation.kind in {"visual_dimension", "visual_similarity"} and event.kind == "oracle_check":
            if obligation.kind == "visual_dimension" and _event_matches_visual_dimension_obligation(event, obligation):
                covering = event
            if obligation.kind == "visual_similarity" and _event_matches_visual_similarity_obligation(
                event,
                obligation,
            ):
                covering = event
    return covering


def _event_matches_verifier_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    subject = obligation.subject
    verifier_id = str(subject.get("verifier_id") or "")
    contract_id = str(subject.get("contract_id") or "")
    if verifier_id:
        return any(str(ref.get("id") or "") == verifier_id for ref in event.refs)
    if contract_id:
        return event.contract_id == contract_id or str(event.observed.get("contract_id") or "") == contract_id
    return False


def _event_matches_source_grounding_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    expected_path = str(obligation.subject.get("path") or "")
    observed_path = str(event.observed.get("path") or "")
    return bool(expected_path and observed_path and expected_path == observed_path)


def _event_matches_artifact_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    subject = obligation.subject
    artifact_id = str(subject.get("artifact_id") or "")
    path = str(subject.get("path") or "")
    target = _mapping(subject.get("target"))
    event_artifact = str(event.observed.get("artifact_id") or "")
    event_path = str(event.observed.get("path") or "")
    if artifact_id and event_artifact == artifact_id:
        return True
    if path and event_path == path:
        return True
    target_path = str(target.get("path") or "")
    return bool(target_path and event_path == target_path)


def _event_matches_visual_dimension_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    if event.kind != "oracle_check" or event.status != "passed":
        return False
    if event.oracle_id and event.oracle_id != obligation.id:
        return False
    if not _event_matches_artifact_obligation(
        EvidenceEvent(
            id=event.id,
            kind="artifact_check",
            status=event.status,
            observed={
                "artifact_id": event.observed.get("artifact_id"),
                "path": event.observed.get("path") or event.observed.get("candidate_path"),
            },
        ),
        obligation,
    ):
        return False
    expected = obligation.expected
    observed_width = _float_or_none(event.observed.get("width"))
    observed_height = _float_or_none(event.observed.get("height"))
    expected_width = _float_or_none(
        expected.get("width") or expected.get("expected_width") or event.observed.get("expected_width")
    )
    expected_height = _float_or_none(
        expected.get("height") or expected.get("expected_height") or event.observed.get("expected_height")
    )
    if expected_width is not None and observed_width != expected_width:
        return False
    if expected_height is not None and observed_height != expected_height:
        return False
    return True


def _event_matches_visual_similarity_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    if event.kind != "oracle_check" or event.status != "passed":
        return False
    if obligation.expected.get("missing_reference"):
        return False
    provenance_source = str(event.provenance.get("source") or event.observed.get("source") or "").casefold()
    if (
        provenance_source in {"candidate_derived", "model_authored", "model_declared"}
        or bool(event.observed.get("candidate_derived"))
    ) and not obligation.candidate_derived_allowed:
        return False
    if event.oracle_id and event.oracle_id != obligation.id:
        return False
    if not _event_matches_artifact_obligation(
        EvidenceEvent(
            id=event.id,
            kind="artifact_check",
            status=event.status,
            observed={
                "artifact_id": event.observed.get("artifact_id"),
                "path": event.observed.get("candidate_path") or event.observed.get("path"),
            },
        ),
        obligation,
    ):
        return False
    expected_reference = str(obligation.expected.get("reference_path") or "")
    observed_reference = str(event.observed.get("reference_path") or "")
    if not observed_reference:
        return False
    if expected_reference and observed_reference != expected_reference:
        if observed_reference.rsplit("/", 1)[-1] != expected_reference.rsplit("/", 1)[-1]:
            return False
    score = _float_or_none(event.observed.get("score"))
    threshold = _float_or_none(event.observed.get("threshold") or obligation.expected.get("threshold"))
    if score is None or threshold is None:
        return False
    comparator = str(event.observed.get("comparator") or obligation.expected.get("comparator") or ">=").strip()
    if comparator in {">=", "gte", "at_least"}:
        return score >= threshold
    if comparator in {">", "gt"}:
        return score > threshold
    if comparator in {"<=", "lte", "at_most"}:
        return score <= threshold
    if comparator in {"<", "lt"}:
        return score < threshold
    return score >= threshold


def _superseding_failed_event(
    obligation: OracleObligation,
    covering_event: EvidenceEvent,
    events: tuple[EvidenceEvent, ...],
) -> EvidenceEvent | None:
    seen_covering = False
    superseding_failure: EvidenceEvent | None = None
    for event in events:
        if event.id == covering_event.id:
            seen_covering = True
            continue
        if not seen_covering:
            continue
        if event.status not in {"failed", "partial", "passed"}:
            continue
        relevant = False
        if event.obligation_id == obligation.id and not (
            event.status == "passed" and obligation.kind in {"visual_dimension", "visual_similarity"}
        ):
            relevant = True
        if obligation.kind in {"artifact_exists", "artifact_fresh"} and event.kind == "artifact_check":
            relevant = relevant or _event_matches_artifact_obligation(event, obligation)
        if obligation.kind in {"artifact_exists", "artifact_fresh"} and event.kind == "verifier_result":
            relevant = relevant or _event_matches_verifier_for_artifact_obligation(event, obligation)
        if obligation.kind == "verifier_pass" and event.kind == "verifier_result":
            relevant = relevant or _event_matches_verifier_obligation(event, obligation)
        if obligation.kind == "source_grounding" and event.kind == "source_grounding":
            relevant = relevant or _event_matches_source_grounding_obligation(event, obligation)
        if obligation.kind == "visual_dimension" and event.kind == "oracle_check":
            if event.status == "passed":
                relevant = relevant or _event_matches_visual_dimension_obligation(event, obligation)
            else:
                relevant = relevant or event.obligation_id == obligation.id
        if obligation.kind == "visual_similarity" and event.kind == "oracle_check":
            if event.status == "passed":
                relevant = relevant or _event_matches_visual_similarity_obligation(event, obligation)
            else:
                relevant = relevant or event.obligation_id == obligation.id
        if not relevant:
            continue
        if event.status in {"failed", "partial"}:
            superseding_failure = event
        elif event.status == "passed":
            superseding_failure = None
    return superseding_failure


def _event_matches_verifier_for_artifact_obligation(event: EvidenceEvent, obligation: OracleObligation) -> bool:
    contract_ids = _obligation_contract_ids(obligation)
    event_contract_id = str(event.contract_id or event.observed.get("contract_id") or "")
    return bool(event_contract_id and event_contract_id in contract_ids)


def _obligation_contract_ids(obligation: OracleObligation) -> set[str]:
    contract_ids = {str(obligation.subject.get("contract_id") or "")}
    for ref in obligation.provenance_refs:
        if str(ref.get("kind") or "") == "execution_contract":
            contract_ids.add(str(ref.get("id") or ""))
    return {item for item in contract_ids if item}


def _typed_continuation_prompt(
    *,
    message: str,
    missing_obligations: tuple[dict[str, Any], ...],
    failed_evidence_refs: tuple[dict[str, Any], ...],
    invalid_evidence_refs: tuple[dict[str, Any], ...],
) -> str:
    lines = ["Finish was blocked by the typed evidence gate.", message]
    for obligation in missing_obligations[:6]:
        lines.append(
            "- missing "
            f"{obligation.get('kind') or 'obligation'} "
            f"{obligation.get('id') or ''}".strip()
        )
    for ref in failed_evidence_refs[:6]:
        lines.append(f"- failed evidence {ref.get('id')}: status={ref.get('status')}")
    for ref in invalid_evidence_refs[:6]:
        lines.append(f"- invalid evidence ref {ref.get('id')}: {ref.get('reason')}")
    lines.append("Next action: produce or cite passing typed evidence_refs for the missing obligation ids.")
    return "\n".join(line for line in lines if line)


def _stable_token(value: object) -> str:
    import hashlib

    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _hashable_ref(ref: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), str(value)) for key, value in ref.items()))


def _unique_refs(refs: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for ref in refs:
        key = _hashable_ref(ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(dict(ref))
    return tuple(deduped)


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


def _terminal_failure_should_defer_to_artifact(
    run: ToolRunRecord,
    failed_artifact: ArtifactEvidence | None,
    contract: ExecutionContract,
) -> bool:
    if failed_artifact is None:
        return False
    if run.status not in {"killed", "timed_out", "interrupted"}:
        return False
    if run.stdout_preview.strip() or run.stderr_preview.strip():
        return False
    role = _role_for_record(run, contract)
    artifact_phase = _phase_for_artifact(failed_artifact, contract)
    if role in {"runtime", "verify"}:
        return True
    return artifact_phase in {"runtime", "verification"}


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


def _finish_evidence_refs(value: object) -> tuple[dict[str, Any], ...]:
    refs: list[dict[str, Any]] = []
    for item in _list(value):
        if isinstance(item, Mapping):
            mapping = dict(item)
            if mapping:
                refs.append(mapping)
            continue
        if isinstance(item, str) and item.strip():
            refs.append({"kind": "evidence_event", "id": item.strip()})
    return tuple(refs)


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
    "recommend_finish_evidence_refs",
    "semantic_exit_from_run",
]
