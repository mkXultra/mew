from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shlex
from typing import Iterable, Mapping

from .acceptance_evidence import (
    COMMAND_EVIDENCE_TOOLS,
    _long_dependency_invoked_command_token,
    _long_dependency_segment_may_mutate_artifact_scope,
    long_dependency_artifact_proven_by_call,
    split_unquoted_shell_command_segment_spans,
    split_unquoted_shell_command_segments,
    tool_call_output_text,
    tool_call_terminal_success,
)


LONG_BUILD_SCHEMA_VERSION = 1
EXECUTION_CONTRACT_SCHEMA_VERSION = 2
ENV_SUMMARY_POLICY = "env_summary_v1"
COMMAND_OUTPUT_CLIP_CHARS = 1200
LONG_COMMAND_OUTPUT_MAX_BYTES = 1_000_000
ENV_VALUE_CLIP_CHARS = 120
LONG_COMMAND_MINIMUM_RESUME_SECONDS = 600
LONG_COMMAND_DEFAULT_FINAL_PROOF_RESERVE_SECONDS = 60
NONTERMINAL_COMMAND_STATUSES = {"running", "yielded"}
TERMINAL_NON_SUCCESS_COMMAND_STATUSES = {"failed", "timed_out", "killed", "interrupted"}
COMMAND_RUN_TERMINAL_STATUSES = {"completed", "failed", "timed_out", "killed", "interrupted"}

EXECUTION_CONTRACT_PURPOSES = {
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
}
EXECUTION_CONTRACT_STAGES = {
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
}
EXECUTION_CONTRACT_PROOF_ROLES = {
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
}
EXECUTION_CONTRACT_ACCEPTANCE_KINDS = {
    "not_acceptance",
    "progress_only",
    "candidate_source_authority",
    "candidate_artifact_proof",
    "candidate_runtime_smoke",
    "candidate_final_proof",
    "external_verifier",
}
EXECUTION_CONTRACT_RISK_CLASSES = {
    "read_only",
    "network_read",
    "build_mutation",
    "source_tree_mutation",
    "runtime_install",
    "system_mutation",
    "destructive",
    "unknown",
}
_PROOF_ROLE_ACCEPTANCE_KINDS = {
    "none": {"not_acceptance", "progress_only"},
    "progress": {"progress_only", "not_acceptance"},
    "source_authority": {"candidate_source_authority", "candidate_final_proof"},
    "target_build": {"progress_only", "candidate_artifact_proof", "candidate_final_proof"},
    "final_artifact": {"candidate_artifact_proof", "candidate_final_proof", "external_verifier"},
    "default_smoke": {"candidate_runtime_smoke", "candidate_final_proof", "external_verifier"},
    "custom_runtime_smoke": {"candidate_runtime_smoke", "external_verifier"},
    "runtime_install": {"progress_only", "candidate_final_proof"},
    "verifier": {"external_verifier", "candidate_final_proof"},
    "negative_diagnostic": {"not_acceptance", "progress_only"},
    "dependency_strategy": {"progress_only", "not_acceptance"},
}

_SAFE_ENV_NAMES = {
    "AR",
    "CC",
    "CFLAGS",
    "CMAKE_BUILD_PARALLEL_LEVEL",
    "CXX",
    "CXXFLAGS",
    "LDFLAGS",
    "MAKEFLAGS",
    "OPAMSWITCH",
    "OPAM_SWITCH_PREFIX",
    "PATH_KIND",
    "PKG_CONFIG_PATH",
}
_SECRET_ENV_NAME_RE = re.compile(r"(?:secret|token|password|passwd|credential|api[_-]?key|private[_-]?key)", re.I)
_RUNTIME_PROOF_TASK_MARKER_RE = re.compile(
    r"\b(?:compiler|toolchain|interpreter|runtime|sdk|linker|standard[- ]library|stdlib|vm|emulator)\b",
    re.I,
)
_RUNTIME_PROOF_EVIDENCE_MARKER_RE = re.compile(
    r"(?:cannot find -l|default link|default-link|runtime library|standard library|stdlib|"
    r"LD_LIBRARY_PATH|LIBRARY_PATH|-stdlib)",
    re.I,
)
_SOURCE_AUTHORITY_RE = re.compile(
    r"(?:official release|release archive|distribution archive|signed checksum|upstream|project docs|"
    r"download page|package-manager metadata|package manager metadata)",
    re.I,
)
_PACKAGE_METADATA_OUTPUT_RE = re.compile(
    r"(?:^dist\.tarball\s*=|^dist\.integrity\s*=|^\s*tarball:\s*['\"]?https?://|"
    r"^\s*integrity:\s*['\"]?sha(?:256|512)-|^Package:\s*\S+|^Version:\s*\S+|"
    r"^https?://\S+|^sha(?:256|512)-\S+|Available versions:|LATEST:)",
    re.I | re.M,
)
_PACKAGE_METADATA_ASSERTION_RE = re.compile(r"(?:https?://\S+|sha(?:256|512)-\S+)", re.I)
_DIRECT_SOURCE_AUTHORITY_OUTPUT_RE = re.compile(
    r"(?:^upstream_(?:ref|ref_url)=|^authority_(?:archive_)?url=https?://|"
    r"^matched_authority_url=https?://|^url=https?://|^CHOSEN https?://)",
    re.I | re.M,
)
_SAVED_SOURCE_URL_OUTPUT_RE = re.compile(r"^source_url=https?://\S+", re.I | re.M)
_SELECTED_SOURCE_ARCHIVE_OUTPUT_RE = re.compile(
    r"^(?:==\s*)?(?:selected|chosen|matched)\s+(?:source\s+)?archive(?:\s*==)?$",
    re.I | re.M,
)
_AUTHORITY_PAGE_OUTPUT_RE = re.compile(r"^authority_page_(?:saved|fetched)=https?://\S+", re.I | re.M)
_ARCHIVE_HASH_OUTPUT_RE = re.compile(r"^archive_sha256=[0-9a-f]{32,128}\b", re.I | re.M)
_DYNAMIC_SOURCE_URL_WRITER_PATH = "<dynamic-source-url-writer>"
_ARCHIVE_ROOT_OUTPUT_RE = re.compile(r"^archive_root=\S+", re.I | re.M)
_ARCHIVE_MEMBER_OUTPUT_RE = re.compile(
    r"^[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+-]+)?/(?:configure|Makefile|README(?:\.[A-Za-z0-9]+)?|LICENSE|VERSION)(?:$|\s)",
    re.I | re.M,
)
_PYTHON_SOURCE_ARCHIVE_OUTPUT_RE = re.compile(
    r"^ARCHIVE\s+\S+\s+bytes=\d+\s+sha256=[0-9a-f]{32,128}\b",
    re.I | re.M,
)
_CONFIGURE_RE = re.compile(r"(?:\./configure|\bcmake\b|\bmeson\b|\bautoconf\b|\bconfigure\b)", re.I)
_DEPENDENCY_GENERATION_RE = re.compile(r"(?:make\s+depend|\.depend|dependency generation|generated depend)", re.I)
_BUILD_RE = re.compile(r"\b(?:make|ninja|cargo|go build|npm run build|python -m build|opam install|pip install)\b", re.I)
_RUNTIME_BUILD_RE = re.compile(r"(?:runtime|stdlib|standard[- ]library|lib[A-Za-z0-9_+-]*\.a)", re.I)
_INSTALL_RE = re.compile(r"\b(?:install|cp -a|cp -r|ln -s)\b", re.I)
_BUILD_FAILURE_RE = re.compile(r"(?:error:|failed|failure|no rule to make target|unsupported|version mismatch)", re.I)
_CUSTOM_RUNTIME_PATH_PROOF_RE = re.compile(r"(?:LD_LIBRARY_PATH|LIBRARY_PATH|-stdlib|-L\s*(?:/|\$|\.|[A-Za-z0-9_]))")
_GENERIC_FAILURE_CLASS_BY_BLOCKER_CODE = {
    "compatibility_override_probe_missing": "dependency_strategy_unresolved",
    "version_pinned_source_toolchain_before_compatibility_override": "dependency_strategy_unresolved",
    "compatibility_branch_budget_contract_missing": "budget_reserve_violation",
    "external_branch_help_probe_too_narrow_before_source_toolchain": "dependency_strategy_unresolved",
    "source_toolchain_before_external_branch_attempt": "dependency_strategy_unresolved",
    "external_dependency_source_provenance_unverified": "source_authority_unverified",
    "source_archive_version_grounding_too_strict": "source_authority_overconstrained",
    "vendored_dependency_patch_surgery_before_supported_branch": "dependency_strategy_unresolved",
    "dependency_generation_order_issue": "dependency_generation_required",
    "untargeted_full_project_build_for_specific_artifact": "target_selection_overbroad",
    "runtime_link_library_missing": "runtime_link_failed",
    "default_runtime_link_path_failed": "runtime_link_failed",
    "default_runtime_link_path_unproven": "runtime_default_path_unproven",
    "runtime_install_before_runtime_library_build": "runtime_install_before_build",
    "runtime_library_subdir_target_path_invalid": "build_system_target_surface_invalid",
}
_RECOVERY_DECISION_FAILURE_CLASSES = {
    "artifact_missing_or_unproven",
    "build_timeout",
    "runtime_link_failed",
    "runtime_default_path_unproven",
    "runtime_install_before_build",
    "build_system_target_surface_invalid",
    "budget_reserve_violation",
}
_SOURCE_AUTHORITY_BLOCKER_CODES = {
    "external_dependency_source_provenance_unverified",
    "source_archive_version_grounding_too_strict",
}


@dataclass(frozen=True)
class CommandEvidence:
    schema_version: int
    id: int
    ref: dict
    source: str
    tool: str
    command: str
    cwd: str
    env_summary: dict
    start_order: int
    finish_order: int
    started_at: str
    finished_at: str
    duration_seconds: float | None
    requested_timeout_seconds: int | None
    effective_timeout_seconds: int | None
    wall_budget_before_seconds: int | None
    wall_budget_after_seconds: int | None
    status: str
    exit_code: int | None
    timed_out: bool
    terminal_success: bool
    output_ref: object | None
    stdout_head: str
    stdout_tail: str
    stderr_head: str
    stderr_tail: str
    output_head: str
    output_tail: str
    truncated: bool
    output_bytes: int | None
    source_tool_call_id: object | None = None
    command_run_id: str = ""
    execution_contract: dict = field(default_factory=dict)
    fallback_used: bool = False
    contract_invalid_reason: str = ""
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CommandEvidence":
        data = dict(data or {})
        known = {name for name in cls.__dataclass_fields__ if name != "unknown_fields"}
        unknown = {key: value for key, value in data.items() if key not in known}
        evidence_id = _coerce_int(data.get("id"), default=0) or 0
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), default=0) or 0,
            id=evidence_id,
            ref=dict(data.get("ref") or {"kind": "command_evidence", "id": evidence_id}),
            source=str(data.get("source") or ""),
            tool=str(data.get("tool") or ""),
            command=str(data.get("command") or ""),
            cwd=str(data.get("cwd") or ""),
            env_summary=dict(data.get("env_summary") or {"policy": ENV_SUMMARY_POLICY, "items": []}),
            start_order=_coerce_int(data.get("start_order"), default=0) or 0,
            finish_order=_coerce_int(data.get("finish_order"), default=0) or 0,
            started_at=str(data.get("started_at") or ""),
            finished_at=str(data.get("finished_at") or ""),
            duration_seconds=_coerce_float(data.get("duration_seconds")),
            requested_timeout_seconds=_coerce_int(data.get("requested_timeout_seconds")),
            effective_timeout_seconds=_coerce_int(data.get("effective_timeout_seconds")),
            wall_budget_before_seconds=_coerce_int(data.get("wall_budget_before_seconds")),
            wall_budget_after_seconds=_coerce_int(data.get("wall_budget_after_seconds")),
            status=str(data.get("status") or ""),
            exit_code=_coerce_int(data.get("exit_code")),
            timed_out=bool(data.get("timed_out")),
            terminal_success=bool(data.get("terminal_success")),
            output_ref=data.get("output_ref"),
            stdout_head=str(data.get("stdout_head") or ""),
            stdout_tail=str(data.get("stdout_tail") or ""),
            stderr_head=str(data.get("stderr_head") or ""),
            stderr_tail=str(data.get("stderr_tail") or ""),
            output_head=str(data.get("output_head") or ""),
            output_tail=str(data.get("output_tail") or ""),
            truncated=bool(data.get("truncated")),
            output_bytes=_coerce_int(data.get("output_bytes")),
            source_tool_call_id=data.get("source_tool_call_id"),
            command_run_id=str(data.get("command_run_id") or ""),
            execution_contract=dict(data.get("execution_contract") or {}),
            fallback_used=bool(data.get("fallback_used")),
            contract_invalid_reason=str(data.get("contract_invalid_reason") or ""),
            unknown_fields=unknown,
        )


@dataclass(frozen=True)
class CommandRun:
    schema_version: int
    id: str
    session_id: str
    task_id: str
    tool_call_id: object | None
    tool: str
    command: str
    cwd: str
    status: str
    command_evidence_ref: dict | None
    terminal_command_evidence_ref: dict | None
    execution_contract: dict
    resume_identity: dict
    output_ref: object | None
    terminal: dict
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "CommandRun":
        data = dict(data or {})
        known = {name for name in cls.__dataclass_fields__ if name != "unknown_fields"}
        unknown = {key: value for key, value in data.items() if key not in known}
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), default=0) or 0,
            id=str(data.get("id") or ""),
            session_id=str(data.get("session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            tool_call_id=data.get("tool_call_id"),
            tool=str(data.get("tool") or ""),
            command=str(data.get("command") or ""),
            cwd=str(data.get("cwd") or ""),
            status=str(data.get("status") or ""),
            command_evidence_ref=_optional_dict(data.get("command_evidence_ref")),
            terminal_command_evidence_ref=_optional_dict(data.get("terminal_command_evidence_ref")),
            execution_contract=dict(data.get("execution_contract") or {}),
            resume_identity=dict(data.get("resume_identity") or {}),
            output_ref=data.get("output_ref"),
            terminal=dict(data.get("terminal") or {}),
            unknown_fields=unknown,
        )


@dataclass(frozen=True)
class LongBuildContract:
    schema_version: int
    id: str
    authority_source: str
    required_artifacts: list[dict]
    source_policy: dict
    dependency_policy: dict
    build_policy: dict
    runtime_proof: dict
    budget: dict
    final_proof: dict
    model_hypotheses: list[dict] = field(default_factory=list)
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data


@dataclass(frozen=True)
class BuildAttempt:
    schema_version: int
    id: str
    contract_id: str
    command_evidence_ref: dict
    stage: str
    selected_target: str
    requested_timeout_seconds: int | None
    effective_timeout_seconds: int | None
    wall_budget_before_seconds: int | None
    wall_budget_after_seconds: int | None
    result: str
    produced_artifacts: list[dict]
    mutation_refs: list[dict]
    diagnostics: list[dict]
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data


@dataclass(frozen=True)
class LongBuildState:
    schema_version: int
    kind: str
    contract_id: str
    status: str
    stages: list[dict]
    artifacts: list[dict]
    attempt_ids: list[str]
    latest_attempt_id: str | None
    current_failure: dict | None
    recovery_decision_id: str | None
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data


@dataclass(frozen=True)
class RecoveryDecision:
    schema_version: int
    id: str
    contract_id: str
    state_status: str
    failure_class: str
    prerequisites: list[str]
    clear_condition: str
    allowed_next_action: dict
    prohibited_repeated_actions: list[str]
    budget: dict
    decision: str
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data


@dataclass(frozen=True)
class LongCommandRun:
    schema_version: int
    id: str
    session_id: str
    task_id: str
    contract_id: str
    attempt_id: str
    running_command_evidence_ref: dict | None
    terminal_command_evidence_ref: dict | None
    tool_call_id: object | None
    stage: str
    selected_target: str
    command: str
    cwd: str
    env_summary: dict
    status: str
    process: dict
    budget: dict
    output: dict
    terminal: dict
    continuation_eligible: bool
    idempotence_key: str
    reducer_hint: dict
    unknown_fields: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = dict(self.unknown_fields)
        data.update(asdict(self))
        data.pop("unknown_fields", None)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "LongCommandRun":
        data = dict(data or {})
        known = {name for name in cls.__dataclass_fields__ if name != "unknown_fields"}
        unknown = {key: value for key, value in data.items() if key not in known}
        return cls(
            schema_version=_coerce_int(data.get("schema_version"), default=0) or 0,
            id=str(data.get("id") or ""),
            session_id=str(data.get("session_id") or ""),
            task_id=str(data.get("task_id") or ""),
            contract_id=str(data.get("contract_id") or ""),
            attempt_id=str(data.get("attempt_id") or ""),
            running_command_evidence_ref=_optional_dict(data.get("running_command_evidence_ref")),
            terminal_command_evidence_ref=_optional_dict(data.get("terminal_command_evidence_ref")),
            tool_call_id=data.get("tool_call_id"),
            stage=str(data.get("stage") or ""),
            selected_target=str(data.get("selected_target") or ""),
            command=str(data.get("command") or ""),
            cwd=str(data.get("cwd") or ""),
            env_summary=dict(data.get("env_summary") or {"policy": ENV_SUMMARY_POLICY, "items": []}),
            status=str(data.get("status") or ""),
            process=dict(data.get("process") or {}),
            budget=dict(data.get("budget") or {}),
            output=dict(data.get("output") or {}),
            terminal=dict(data.get("terminal") or {}),
            continuation_eligible=bool(data.get("continuation_eligible")),
            idempotence_key=str(data.get("idempotence_key") or ""),
            reducer_hint=dict(data.get("reducer_hint") or {}),
            unknown_fields=unknown,
        )


def command_run_id(session_id: object, ordinal: object) -> str:
    return f"work_session:{_stable_id_component(session_id)}:command_run:{_stable_id_component(ordinal)}"


def long_command_run_id(session_id: object, ordinal: object) -> str:
    return f"work_session:{_stable_id_component(session_id)}:long_command:{_stable_id_component(ordinal)}"


def normalize_execution_contract(
    raw: object,
    *,
    tool: object = "",
    command: object = "",
    cwd: object = "",
    task_contract: Mapping[str, object] | None = None,
) -> dict:
    """Normalize typed command semantics.

    `command` remains execution payload. The normalized contract is semantic
    intent; when absent, reducers may use legacy classifiers only as explicit
    fallback.
    """
    fallback_used = not isinstance(raw, Mapping)
    data = dict(raw or {}) if isinstance(raw, Mapping) else {}
    tool_name = str(tool or "")
    purpose_default = "verification" if tool_name == "run_tests" else "generic_command"
    stage_default = "verification" if tool_name == "run_tests" else "command"
    proof_default = "verifier" if tool_name == "run_tests" else "none"
    acceptance_default = "external_verifier" if tool_name == "run_tests" else "not_acceptance"
    invalid_reasons = []
    if isinstance(raw, Mapping):
        missing = [
            key
            for key in ("purpose", "stage", "proof_role", "acceptance_kind")
            if key not in data or str(data.get(key) or "").strip() == ""
        ]
        if missing:
            invalid_reasons.append("missing required execution_contract field(s): " + ", ".join(missing))

    purpose = _enum_value(data.get("purpose"), EXECUTION_CONTRACT_PURPOSES, purpose_default)
    stage = _enum_value(data.get("stage"), EXECUTION_CONTRACT_STAGES, stage_default)
    proof_role = _enum_value(data.get("proof_role"), EXECUTION_CONTRACT_PROOF_ROLES, proof_default)
    acceptance_kind = _enum_value(
        data.get("acceptance_kind"),
        EXECUTION_CONTRACT_ACCEPTANCE_KINDS,
        acceptance_default,
    )
    risk_class = _enum_value(data.get("risk_class"), EXECUTION_CONTRACT_RISK_CLASSES, "unknown")
    invalid_reasons.extend(
        reason
        for reason in [
            _enum_invalid_reason(data.get("purpose"), EXECUTION_CONTRACT_PURPOSES, "purpose"),
            _enum_invalid_reason(data.get("stage"), EXECUTION_CONTRACT_STAGES, "stage"),
            _enum_invalid_reason(data.get("proof_role"), EXECUTION_CONTRACT_PROOF_ROLES, "proof_role"),
            _enum_invalid_reason(data.get("acceptance_kind"), EXECUTION_CONTRACT_ACCEPTANCE_KINDS, "acceptance_kind"),
            _enum_invalid_reason(data.get("risk_class"), EXECUTION_CONTRACT_RISK_CLASSES, "risk_class"),
        ]
        if reason
    )
    expected_artifacts = _list_of_dicts(data.get("expected_artifacts"))
    declared_target_refs = _list_of_dicts(data.get("declared_target_refs"))
    if not expected_artifacts and isinstance(task_contract, Mapping):
        expected_artifacts = _list_of_dicts(task_contract.get("required_artifacts"))
    if not declared_target_refs:
        declared_target_refs = _declared_refs_from_artifacts(expected_artifacts)

    source_authority_requirement = _normalize_source_authority_requirement(
        data.get("source_authority_requirement"),
        task_contract=task_contract,
    )
    resume_identity = _normalize_resume_identity(
        data.get("resume_identity"),
        contract_id=str(data.get("contract_id") or (task_contract or {}).get("id") or ""),
        purpose=purpose,
        stage=stage,
        cwd=cwd,
        command=command,
        expected_artifacts=expected_artifacts,
        declared_target_refs=declared_target_refs,
        source_tree_ref=source_authority_requirement.get("source_tree_ref") or "",
        execution_mode="argv" if tool_name == "run_tests" else "shell",
    )
    invalid_reason = _execution_contract_invalid_reason(
        proof_role=proof_role,
        acceptance_kind=acceptance_kind,
        purpose=purpose,
    )
    if invalid_reason:
        invalid_reasons.append(invalid_reason)
    contract = {
        "schema_version": EXECUTION_CONTRACT_SCHEMA_VERSION,
        "purpose": purpose,
        "stage": stage,
        "proof_role": proof_role,
        "expected_artifacts": expected_artifacts,
        "declared_target_refs": declared_target_refs,
        "acceptance_kind": acceptance_kind,
        "continuation_policy": _normalize_continuation_policy(data.get("continuation_policy")),
        "background_policy": _normalize_background_policy(data.get("background_policy"), tool=tool_name),
        "source_authority_requirement": source_authority_requirement,
        "resume_identity": resume_identity,
        "risk_class": risk_class,
        "evidence_refs": _list_of_dicts(data.get("evidence_refs")),
        "notes": str(data.get("notes") or "")[:240],
        "fallback_used": bool(fallback_used or data.get("fallback_used")),
        "contract_invalid_reason": "; ".join(invalid_reasons),
    }
    substeps = _list_of_dicts(data.get("substeps"))
    if substeps:
        contract["substeps"] = [
            normalize_execution_contract(
                substep,
                tool=tool_name,
                command=command,
                cwd=cwd,
                task_contract=task_contract,
            )
            for substep in substeps
        ]
    if "contract_id" in data or (task_contract or {}).get("id"):
        contract["contract_id"] = str(data.get("contract_id") or (task_contract or {}).get("id") or "")
    return contract


def execution_contract_is_valid(contract: object) -> bool:
    return isinstance(contract, Mapping) and not str(contract.get("contract_invalid_reason") or "")


def execution_contract_stage(contract: object) -> str:
    if not execution_contract_is_valid(contract):
        return ""
    if bool((contract or {}).get("fallback_used")):
        return ""
    stage = str((contract or {}).get("stage") or "")
    return stage if stage in EXECUTION_CONTRACT_STAGES else ""


def execution_contract_continuation_policy(contract: object) -> dict:
    if not isinstance(contract, Mapping):
        return {}
    policy = contract.get("continuation_policy")
    return dict(policy) if isinstance(policy, Mapping) else {}


def build_command_run(
    *,
    session_id: object,
    task_id: object,
    ordinal: object,
    tool_call_id: object | None,
    tool: object,
    command: object,
    cwd: object,
    status: object,
    command_evidence_ref: Mapping[str, object] | None = None,
    terminal_command_evidence_ref: Mapping[str, object] | None = None,
    execution_contract: Mapping[str, object] | None = None,
    output_ref: object | None = None,
    exit_code: object | None = None,
    timed_out: object = False,
) -> dict:
    contract = dict(execution_contract or {})
    run = CommandRun(
        schema_version=EXECUTION_CONTRACT_SCHEMA_VERSION,
        id=command_run_id(session_id, ordinal),
        session_id=str(session_id or ""),
        task_id=str(task_id or ""),
        tool_call_id=tool_call_id,
        tool=str(tool or ""),
        command=str(command or ""),
        cwd=str(cwd or ""),
        status=str(status or ""),
        command_evidence_ref=dict(command_evidence_ref or {}),
        terminal_command_evidence_ref=dict(terminal_command_evidence_ref) if terminal_command_evidence_ref else None,
        execution_contract=contract,
        resume_identity=dict(contract.get("resume_identity") or {}),
        output_ref=output_ref,
        terminal={
            "exit_code": _coerce_int(exit_code),
            "timed_out": bool(timed_out),
            "terminal": str(status or "").casefold() in COMMAND_RUN_TERMINAL_STATUSES,
        },
    )
    return run.to_dict()


def _enum_value(value: object, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _enum_invalid_reason(value: object, allowed: set[str], field: str) -> str:
    if value is None or str(value or "").strip() == "":
        return ""
    text = str(value or "").strip()
    if text in allowed:
        return ""
    return f"invalid execution_contract {field}: {text!r}"


def _list_of_dicts(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _declared_refs_from_artifacts(artifacts: Iterable[Mapping[str, object]]) -> list[dict]:
    refs = []
    for artifact in artifacts or []:
        path = str((artifact or {}).get("path") or "")
        if path:
            refs.append({"kind": "artifact", "path": path})
    return refs


def _normalize_continuation_policy(value: object) -> dict:
    policy = dict(value or {}) if isinstance(value, Mapping) else {}
    mode = str(policy.get("mode") or "blocking").strip()
    if mode not in {"blocking", "managed", "foreground_blocking", "foreground_yieldable", "none"}:
        mode = "blocking"
    return {
        "mode": mode,
        "yield_after_seconds": _coerce_int(policy.get("yield_after_seconds")),
        "max_continuations": _coerce_int(policy.get("max_continuations"), default=3) or 3,
        "resume_policy": str(policy.get("resume_policy") or "none"),
        "terminal_required_for_acceptance": bool(policy.get("terminal_required_for_acceptance", True)),
        "final_proof_reserve_seconds": _coerce_int(policy.get("final_proof_reserve_seconds"), default=60) or 60,
    }


def _normalize_background_policy(value: object, *, tool: str) -> dict:
    policy = dict(value or {}) if isinstance(value, Mapping) else {}
    mode = str(policy.get("mode") or ("foreground_blocking" if tool == "run_tests" else "foreground_yieldable"))
    if mode not in {"foreground_blocking", "foreground_yieldable", "background_allowed"}:
        mode = "foreground_blocking" if tool == "run_tests" else "foreground_yieldable"
    return {
        "mode": mode,
        "allow_background": bool(policy.get("allow_background")),
        "handoff": str(policy.get("handoff") or ""),
    }


def _normalize_source_authority_requirement(value: object, *, task_contract: Mapping[str, object] | None) -> dict:
    policy = dict(value or {}) if isinstance(value, Mapping) else {}
    task_source_policy = (task_contract or {}).get("source_policy") if isinstance(task_contract, Mapping) else {}
    task_source_policy = task_source_policy if isinstance(task_source_policy, Mapping) else {}
    mode = str(policy.get("mode") or "inherits_task_contract")
    if mode not in {"inherits_task_contract", "produces_authority", "consumes_authority", "not_applicable"}:
        mode = "inherits_task_contract"
    return {
        "mode": mode,
        "required": bool(policy.get("required", task_source_policy.get("authority_required", False))),
        "source_tree_ref": str(policy.get("source_tree_ref") or task_source_policy.get("source_tree_ref") or ""),
        "authority_refs": [str(item) for item in policy.get("authority_refs") or [] if str(item or "")],
        "same_source_tree_required": bool(policy.get("same_source_tree_required", True)),
    }


def _normalize_resume_identity(
    value: object,
    *,
    contract_id: str,
    purpose: str,
    stage: str,
    cwd: object,
    command: object,
    expected_artifacts: list[dict],
    declared_target_refs: list[dict],
    source_tree_ref: str,
    execution_mode: str,
) -> dict:
    identity = dict(value or {}) if isinstance(value, Mapping) else {}
    normalized = {
        "contract_id": str(identity.get("contract_id") or contract_id),
        "purpose": str(identity.get("purpose") or purpose),
        "stage": str(identity.get("stage") or stage),
        "declared_target_refs": _list_of_dicts(identity.get("declared_target_refs")) or declared_target_refs,
        "expected_artifacts": _list_of_dicts(identity.get("expected_artifacts")) or expected_artifacts,
        "source_tree_ref": str(identity.get("source_tree_ref") or source_tree_ref),
        "cwd": str(identity.get("cwd") or cwd or ""),
        "execution_mode": str(identity.get("execution_mode") or execution_mode),
        "payload_hash": str(identity.get("payload_hash") or _sha256_text(command)),
        "env_fingerprint": str(identity.get("env_fingerprint") or ""),
    }
    normalized["idempotence_key"] = str(identity.get("idempotence_key") or execution_contract_idempotence_key(normalized))
    return normalized


def execution_contract_idempotence_key(identity: Mapping[str, object]) -> str:
    payload = {
        "contract_id": str(identity.get("contract_id") or ""),
        "purpose": str(identity.get("purpose") or ""),
        "stage": str(identity.get("stage") or ""),
        "cwd": str(identity.get("cwd") or ""),
        "execution_mode": str(identity.get("execution_mode") or ""),
        "payload_hash": str(identity.get("payload_hash") or ""),
        "declared_target_refs_json": _stable_json(identity.get("declared_target_refs") or []),
        "expected_artifacts_json": _stable_json(identity.get("expected_artifacts") or []),
        "source_tree_ref": str(identity.get("source_tree_ref") or ""),
        "env_fingerprint": str(identity.get("env_fingerprint") or ""),
    }
    return "sha256:" + hashlib.sha256(_stable_json(payload).encode("utf-8")).hexdigest()


def _sha256_text(value: object) -> str:
    return "sha256:" + hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _stable_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _execution_contract_invalid_reason(*, proof_role: str, acceptance_kind: str, purpose: str) -> str:
    allowed = _PROOF_ROLE_ACCEPTANCE_KINDS.get(proof_role, set())
    if acceptance_kind not in allowed:
        if proof_role == "final_artifact" and acceptance_kind == "not_acceptance" and purpose == "diagnostic":
            return ""
        return f"proof_role {proof_role!r} cannot use acceptance_kind {acceptance_kind!r}"
    return ""




def long_command_output_ref(session_id: object, ordinal: object, *, filename: str = "output.log") -> str:
    return (
        f"work-session/{_safe_path_component(session_id)}/"
        f"long-command/{_safe_path_component(ordinal)}/{_safe_path_component(filename)}"
    )


def long_command_idempotence_key(
    *,
    cwd: object,
    command: object,
    contract_id: object,
    stage: object,
    selected_targets: Iterable[object] = (),
) -> str:
    payload = {
        "command": str(command or ""),
        "contract_id": str(contract_id or ""),
        "cwd": str(cwd or ""),
        "selected_targets": sorted(str(item or "") for item in selected_targets or [] if str(item or "")),
        "stage": str(stage or ""),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def long_command_output_snapshot(
    *,
    stdout: object = "",
    stderr: object = "",
    output_ref: object = "",
    max_bytes: int = LONG_COMMAND_OUTPUT_MAX_BYTES,
) -> dict:
    stdout_text = str(stdout or "")
    stderr_text = str(stderr or "")
    combined = f"{stdout_text}\n{stderr_text}" if stdout_text and stderr_text else stdout_text or stderr_text
    return {
        "output_ref": str(output_ref or ""),
        "stdout_head": _head(stdout_text),
        "stdout_tail": _tail(stdout_text),
        "stderr_head": _head(stderr_text),
        "stderr_tail": _tail(stderr_text),
        "output_bytes": len(combined.encode("utf-8")) if combined else 0,
        "max_bytes": int(max_bytes),
        "truncated": any(len(value) > COMMAND_OUTPUT_CLIP_CHARS for value in (stdout_text, stderr_text)),
    }


def long_command_yield_after_seconds(
    effective_timeout_seconds: object,
    *,
    requested_yield_after_seconds: int = 30,
) -> int | None:
    effective = _coerce_int(effective_timeout_seconds)
    requested = max(1, int(requested_yield_after_seconds))
    if effective is not None and requested >= effective:
        return None
    return requested


def build_long_command_run(
    *,
    session_id: object,
    ordinal: object,
    task_id: object,
    contract_id: object,
    attempt_id: object,
    tool_call_id: object | None,
    stage: object,
    selected_target: object,
    command: object,
    cwd: object,
    env: object = None,
    status: str = "running",
    pid: object | None = None,
    process_group_id: object | None = None,
    owner_token: object | None = None,
    running_command_evidence_ref: Mapping[str, object] | None = None,
    terminal_command_evidence_ref: Mapping[str, object] | None = None,
    requested_timeout_seconds: object | None = None,
    effective_timeout_seconds: object | None = None,
    work_wall_remaining_seconds: object | None = None,
    final_proof_reserve_seconds: object | None = 60,
    continuation_count: object | None = 0,
    max_continuations: object | None = 3,
    stdout: object = "",
    stderr: object = "",
) -> dict:
    run_id = long_command_run_id(session_id, ordinal)
    output_ref = long_command_output_ref(session_id, ordinal)
    selected_targets = [selected_target] if str(selected_target or "") else []
    yield_after = long_command_yield_after_seconds(effective_timeout_seconds)
    budget = {
        "requested_timeout_seconds": _coerce_int(requested_timeout_seconds),
        "effective_timeout_seconds": _coerce_int(effective_timeout_seconds),
        "work_wall_remaining_seconds": _coerce_int(work_wall_remaining_seconds),
        "yield_after_seconds": yield_after,
        "final_proof_reserve_seconds": _coerce_int(final_proof_reserve_seconds, default=60),
        "continuation_count": _coerce_int(continuation_count, default=0) or 0,
        "max_continuations": _coerce_int(max_continuations, default=3) or 3,
    }
    run = LongCommandRun(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=run_id,
        session_id=str(session_id or ""),
        task_id=str(task_id or ""),
        contract_id=str(contract_id or ""),
        attempt_id=str(attempt_id or ""),
        running_command_evidence_ref=dict(running_command_evidence_ref or {}),
        terminal_command_evidence_ref=dict(terminal_command_evidence_ref) if terminal_command_evidence_ref else None,
        tool_call_id=tool_call_id,
        stage=str(stage or ""),
        selected_target=str(selected_target or ""),
        command=str(command or ""),
        cwd=str(cwd or ""),
        env_summary=summarize_env(env),
        status=str(status or "running"),
        process={
            "pid": _coerce_int(pid),
            "process_group_id": _coerce_int(process_group_id),
            "owner_token": str(owner_token or f"managed-runner:{run_id}"),
        },
        budget=budget,
        output=long_command_output_snapshot(stdout=stdout, stderr=stderr, output_ref=output_ref),
        terminal={"exit_code": None, "timed_out": False, "kill_reason": "", "finished_at": None},
        continuation_eligible=True,
        idempotence_key=long_command_idempotence_key(
            cwd=cwd,
            command=command,
            contract_id=contract_id,
            stage=stage,
            selected_targets=selected_targets,
        ),
        reducer_hint={
            "scope": "current_failure_selection_only",
            "suppresses_stale_classes": ["build_timeout"],
            "never_suppresses": ["artifact_missing_or_unproven", "acceptance_proof"],
        },
    )
    return run.to_dict()


def build_long_build_contract(
    task_text: object,
    required_artifacts: Iterable[object],
    *,
    contract_id: str = "work_session:unknown:long_build:1",
    authority_source: str = "task_text",
    acceptance_constraints: Iterable[object] | None = None,
) -> dict:
    artifacts = []
    for artifact in required_artifacts or []:
        path = str(artifact or "").strip()
        if not path:
            continue
        artifacts.append(
            {
                "path": path,
                "kind": _artifact_kind(path),
                "proof_required": "exists_and_invokable",
            }
        )
    text = "\n".join(str(value or "") for value in [task_text, *(acceptance_constraints or [])] if value)
    runtime_required = _runtime_proof_required(text, artifacts)
    contract = LongBuildContract(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=contract_id,
        authority_source=authority_source,
        required_artifacts=artifacts,
        source_policy={
            "authority_required": True,
            "accepted_authorities": [
                "project_docs",
                "package_manager_metadata",
                "official_release_archive",
                "signed_checksum",
                "upstream_download_page",
            ],
            "invalid_authorities": ["model_assertion", "random_mirror", "ungrounded_generated_source"],
        },
        dependency_policy={
            "prefer_source_provided_compatibility_branch": True,
            "allow_vendored_dependency_surgery": "only_after_supported_branches_exhausted",
        },
        build_policy={
            "prefer_shortest_final_target": True,
            "dependency_generation_before_final_target": True,
        },
        runtime_proof={
            "required": "required" if runtime_required else "not_required",
            "classifier": "runtime_proof_classifier_v1",
            "reason": _runtime_proof_reason(text, artifacts, runtime_required),
            "default_lookup_required": bool(runtime_required),
            "custom_lookup_is_diagnostic": bool(runtime_required),
        },
        budget={"wall_seconds": None, "final_proof_reserve_seconds": 60},
        final_proof={
            "terminal_success_required": True,
            "artifact_freshness_required": True,
            "evidence_kinds": ["command_evidence"],
        },
    )
    return contract.to_dict()


def build_attempts_from_command_evidence(
    evidences: Iterable[CommandEvidence | Mapping[str, object]],
    contract: Mapping[str, object],
) -> list[dict]:
    attempts = []
    for index, item in enumerate(evidences or [], start=1):
        evidence = item if isinstance(item, CommandEvidence) else CommandEvidence.from_dict(item)
        stage = _command_stage(evidence, contract)
        attempt = BuildAttempt(
            schema_version=LONG_BUILD_SCHEMA_VERSION,
            id=f"{contract.get('id') or 'long_build'}:attempt:{index}",
            contract_id=str(contract.get("id") or ""),
            command_evidence_ref={"kind": "command_evidence", "id": evidence.id},
            stage=stage,
            selected_target=_selected_target(evidence.command, contract),
            requested_timeout_seconds=evidence.requested_timeout_seconds,
            effective_timeout_seconds=evidence.effective_timeout_seconds,
            wall_budget_before_seconds=evidence.wall_budget_before_seconds,
            wall_budget_after_seconds=evidence.wall_budget_after_seconds,
            result=_attempt_result(evidence),
            produced_artifacts=_produced_artifacts(evidence, contract),
            mutation_refs=[],
            diagnostics=_diagnostics(evidence, contract),
            unknown_fields={
                "command_run_id": evidence.command_run_id,
                "proof_role": (evidence.execution_contract or {}).get("proof_role") or "",
                "acceptance_kind": (evidence.execution_contract or {}).get("acceptance_kind") or "",
                "fallback_used": bool(evidence.fallback_used),
                "contract_invalid_reason": evidence.contract_invalid_reason,
            },
        )
        attempts.append(attempt.to_dict())
    return attempts


def reduce_long_build_state(
    contract: Mapping[str, object],
    attempts: Iterable[Mapping[str, object]],
    evidences: Iterable[CommandEvidence | Mapping[str, object]],
    *,
    long_command_runs: Iterable[LongCommandRun | Mapping[str, object]] = (),
    progress: Iterable[Mapping[str, object]] = (),
    strategy_blockers: Iterable[Mapping[str, object]] = (),
    incomplete_reason: str = "",
    latest_build_call: Mapping[str, object] | None = None,
    latest_build_command: str = "",
    suggested_next: str = "",
) -> dict:
    normalized_evidence = [item if isinstance(item, CommandEvidence) else CommandEvidence.from_dict(item) for item in evidences or []]
    evidence_by_tool_call_id = {
        evidence.source_tool_call_id: evidence.id
        for evidence in normalized_evidence
        if evidence.source_tool_call_id is not None
    }
    artifact_status = []
    attempts = [dict(item) for item in attempts or [] if isinstance(item, Mapping)]
    fresh_default_smoke = _has_fresh_default_smoke(attempts, normalized_evidence, contract)
    source_authority_satisfied = _source_authority_satisfied(attempts) or _source_authority_satisfied_by_correlated_archive_readback(
        normalized_evidence
    )
    for artifact in contract.get("required_artifacts") or []:
        path = str((artifact or {}).get("path") or "")
        artifact_evidence = [evidence for evidence in normalized_evidence if _artifact_proof_contract_allows_acceptance(evidence)]
        proof = fresh_long_dependency_artifact_evidence(artifact_evidence, path) if path else None
        produced_proof = _attempt_produced_artifact_proof(attempts, path, normalized_evidence) if path else None
        artifact_status.append(
            {
                "path": path,
                "kind": (artifact or {}).get("kind") or _artifact_kind(path),
                "status": "proven" if proof or produced_proof else "missing_or_unproven",
                "proof_evidence_id": proof.id if proof else (produced_proof or {}).get("proof_evidence_id"),
                "source_tool_call_id": proof.source_tool_call_id if proof else None,
            }
        )
    blockers = [dict(item) for item in strategy_blockers or [] if isinstance(item, Mapping)]
    active_blockers = _active_strategy_blockers(
        blockers,
        attempts,
        artifact_status,
        contract,
        evidence_by_tool_call_id=evidence_by_tool_call_id,
        fresh_default_smoke=fresh_default_smoke,
        source_authority_satisfied=source_authority_satisfied,
    )
    stages = _reduce_stages(
        contract,
        attempts,
        artifact_status,
        active_blockers,
        fresh_default_smoke=fresh_default_smoke,
        source_authority_satisfied=source_authority_satisfied,
    )
    missing = [item for item in artifact_status if item.get("status") != "proven"]
    current_failure = _current_failure(
        contract,
        attempts,
        active_blockers,
        missing,
        incomplete_reason,
        evidence_by_tool_call_id,
        fresh_default_smoke=fresh_default_smoke,
    )
    status = _state_status(attempts, missing, current_failure, stages)
    latest_attempt_id = attempts[-1].get("id") if attempts else None
    latest_build_tool_call_id = latest_build_call.get("id") if isinstance(latest_build_call, Mapping) else None
    normalized_long_command_runs = [
        item if isinstance(item, LongCommandRun) else LongCommandRun.from_dict(item)
        for item in long_command_runs or []
        if isinstance(item, (LongCommandRun, Mapping))
    ]
    normalized_long_command_runs = _cap_timed_out_long_command_budgets_by_prior_wall(normalized_long_command_runs)
    latest_long_command = _latest_long_command_run(normalized_long_command_runs)
    latest_long_command_status = str(latest_long_command.status or "").casefold() if latest_long_command else ""
    latest_live_long_command = (
        latest_long_command if latest_long_command_status in NONTERMINAL_COMMAND_STATUSES else None
    )
    latest_terminal_long_command = (
        latest_long_command if latest_long_command_status in TERMINAL_NON_SUCCESS_COMMAND_STATUSES else None
    )
    effective_incomplete_reason = (
        ""
        if _incomplete_reason_cleared_by_later_success(incomplete_reason, attempts)
        else str(incomplete_reason or "")
    )
    if latest_live_long_command:
        status = "in_progress"
        current_failure = None
        recovery_decision = _derive_long_command_poll_recovery_decision(contract, latest_live_long_command)
    elif latest_terminal_long_command:
        current_failure = _long_command_terminal_failure(latest_terminal_long_command)
        status = "blocked"
        recovery_decision = _derive_long_command_terminal_recovery_decision(contract, latest_terminal_long_command, status)
    else:
        recovery_decision = _derive_recovery_decision(
            contract,
            status,
            current_failure,
            attempts,
            normalized_evidence,
            blockers,
        )
    state = LongBuildState(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        kind="long_build_state",
        contract_id=str(contract.get("id") or ""),
        status=status,
        stages=stages,
        artifacts=artifact_status[:6],
        attempt_ids=[str(item.get("id") or "") for item in attempts if item.get("id")],
        latest_attempt_id=str(latest_attempt_id) if latest_attempt_id else None,
        current_failure=current_failure,
        recovery_decision_id=recovery_decision.id if recovery_decision else None,
        unknown_fields={
            "contract": dict(contract),
            "attempts": attempts[-6:],
            "progress": [dict(item) for item in progress or [] if isinstance(item, Mapping)][-6:],
            "expected_artifacts": artifact_status[:6],
            "missing_artifacts": missing[:6],
            "latest_build_tool_call_id": latest_build_tool_call_id,
            "latest_build_evidence_id": evidence_by_tool_call_id.get(latest_build_tool_call_id),
            "latest_build_status": str(latest_build_call.get("status") or "") if isinstance(latest_build_call, Mapping) else "",
            "latest_build_command": latest_build_command,
            "latest_long_command_run_id": latest_live_long_command.id if latest_live_long_command else (latest_terminal_long_command.id if latest_terminal_long_command else None),
            "latest_live_command_evidence_id": _long_command_evidence_id(latest_live_long_command.running_command_evidence_ref) if latest_live_long_command else None,
            "latest_build_stage": latest_live_long_command.stage if latest_live_long_command else (latest_terminal_long_command.stage if latest_terminal_long_command else ""),
            "latest_long_command_status": latest_live_long_command.status if latest_live_long_command else (latest_terminal_long_command.status if latest_terminal_long_command else ""),
            "latest_build_output_ref": (latest_live_long_command.output or {}).get("output_ref") if latest_live_long_command else ((latest_terminal_long_command.output or {}).get("output_ref") if latest_terminal_long_command else ""),
            "latest_nonterminal_reason": "long_command_running" if latest_live_long_command else "",
            "continuation_required": bool(latest_live_long_command),
            "long_command_runs": [run.to_dict() for run in normalized_long_command_runs[-3:]],
            "incomplete_reason": effective_incomplete_reason,
            "strategy_blockers": active_blockers[-6:],
            "cleared_strategy_blockers": _cleared_strategy_blockers(blockers, active_blockers)[-6:],
            "recovery_decision": recovery_decision.to_dict() if recovery_decision else None,
            "suggested_next": str(suggested_next or "") if (current_failure and not recovery_decision) else "",
        },
    )
    return state.to_dict()


def summarize_env(env: object) -> dict:
    items = []
    if isinstance(env, Mapping):
        for name, value in sorted(env.items(), key=lambda item: str(item[0])):
            key = str(name or "")
            if key not in _SAFE_ENV_NAMES or _SECRET_ENV_NAME_RE.search(key):
                continue
            text = str(value or "")
            if _SECRET_ENV_NAME_RE.search(text):
                continue
            items.append({"name": key, "value": _clip(text, ENV_VALUE_CLIP_CHARS)})
    return {"policy": ENV_SUMMARY_POLICY, "items": items}


def synthesize_command_evidence_from_tool_calls(
    tool_calls: Iterable[Mapping[str, object]],
    *,
    source: str = "synthesized_fixture",
) -> list[CommandEvidence]:
    evidences: list[CommandEvidence] = []
    for call_index, call in enumerate(tool_calls or [], start=1):
        evidence = synthesize_command_evidence_from_tool_call(
            call,
            evidence_id=len(evidences) + 1,
            call_order=call_index,
            source=source,
        )
        if evidence:
            evidences.append(evidence)
    return evidences


def synthesize_command_evidence_from_session(session: object, *, source: str = "synthesized_fixture") -> list[CommandEvidence]:
    if not isinstance(session, Mapping):
        return []
    return synthesize_command_evidence_from_tool_calls(session.get("tool_calls") or [], source=source)


def migrate_command_evidence_fixture_contracts(
    evidences: Iterable[CommandEvidence | Mapping[str, object]],
    contract: Mapping[str, object],
    *,
    fallback: bool = False,
) -> list[dict]:
    """Annotate legacy replay fixtures with explicit execution contracts.

    This helper is intentionally fixture/replay oriented. It may use legacy
    stage discovery to preserve old expected behavior. By default it writes
    typed fixture contracts. Pass `fallback=True` only for fallback fixtures
    that intentionally exercise legacy classifier behavior.
    """
    migrated = []
    for item in evidences or []:
        evidence = item if isinstance(item, CommandEvidence) else CommandEvidence.from_dict(item)
        data = evidence.to_dict()
        if isinstance(data.get("execution_contract"), dict) and not data["execution_contract"].get("fallback_used"):
            migrated.append(data)
            continue
        stage = _command_stage(evidence, contract)
        if (
            stage not in {"artifact_proof", "default_smoke", "custom_runtime_smoke", "verification"}
            and (_source_authority_signal(evidence) or _command_uses_source_acquisition_tool(evidence.command))
        ):
            stage = "source_acquisition"
        proof_role, acceptance_kind = _fixture_contract_role_for_stage(stage)
        continuation_policy = _fixture_contract_continuation_policy(stage, evidence)
        raw_contract = {
            "schema_version": EXECUTION_CONTRACT_SCHEMA_VERSION,
            "contract_id": str(contract.get("id") or ""),
            "purpose": _fixture_contract_purpose_for_stage(stage, evidence.tool),
            "stage": stage or "command",
            "proof_role": proof_role,
            "acceptance_kind": acceptance_kind,
            "expected_artifacts": _list_of_dicts(contract.get("required_artifacts")),
            "declared_target_refs": _declared_refs_from_artifacts(_list_of_dicts(contract.get("required_artifacts"))),
            "continuation_policy": continuation_policy,
            "background_policy": {
                "mode": "foreground_blocking" if evidence.tool == "run_tests" else "foreground_yieldable",
                "allow_background": False,
            },
            "source_authority_requirement": {
                "mode": "inherits_task_contract",
                "required": bool((contract.get("source_policy") or {}).get("authority_required", False)),
                "source_tree_ref": str((contract.get("source_policy") or {}).get("source_tree_ref") or ""),
            },
            "risk_class": "read_only" if evidence.tool == "run_tests" else "unknown",
            "fallback_used": bool(fallback),
        }
        normalized = normalize_execution_contract(
            raw_contract,
            tool=evidence.tool,
            command=evidence.command,
            cwd=evidence.cwd,
            task_contract=contract,
        )
        normalized["fallback_used"] = bool(fallback)
        normalized["migration_source"] = "legacy_fixture_stage_classifier_v1"
        data["execution_contract"] = normalized
        data["fallback_used"] = bool(fallback)
        data["contract_invalid_reason"] = normalized.get("contract_invalid_reason") or ""
        migrated.append(data)
    return migrated


def _fixture_contract_role_for_stage(stage: object) -> tuple[str, str]:
    stage_text = str(stage or "")
    if stage_text in {"source_acquisition", "source_authority"}:
        return "source_authority", "candidate_source_authority"
    if stage_text == "artifact_proof":
        return "final_artifact", "candidate_final_proof"
    if stage_text == "default_smoke":
        return "default_smoke", "candidate_runtime_smoke"
    if stage_text == "custom_runtime_smoke":
        return "custom_runtime_smoke", "candidate_runtime_smoke"
    if stage_text == "verification":
        return "verifier", "external_verifier"
    if stage_text == "runtime_install":
        return "runtime_install", "progress_only"
    if stage_text == "dependency_generation":
        return "dependency_strategy", "progress_only"
    if stage_text in {"build", "runtime_build"}:
        return "target_build", "progress_only"
    if stage_text in {"configure", "diagnostic"}:
        return "negative_diagnostic", "not_acceptance"
    return "none", "not_acceptance"


def _fixture_contract_purpose_for_stage(stage: object, tool: object) -> str:
    if str(tool or "") == "run_tests":
        return "verification"
    stage_text = str(stage or "")
    if stage_text in EXECUTION_CONTRACT_PURPOSES:
        return stage_text
    if stage_text == "source_authority":
        return "source_authority_readback"
    if stage_text == "default_smoke" or stage_text == "custom_runtime_smoke":
        return "smoke"
    if stage_text == "artifact_proof":
        return "artifact_proof"
    return "generic_command"


def _fixture_contract_continuation_policy(stage: object, evidence: CommandEvidence) -> dict:
    stage_text = str(stage or "")
    effective_timeout = evidence.effective_timeout_seconds or evidence.requested_timeout_seconds or 0
    managed = bool(evidence.timed_out) or (
        stage_text in {"build", "runtime_build", "runtime_install", "dependency_generation"}
        and int(effective_timeout or 0) >= 600
    )
    return {
        "mode": "managed" if managed else "blocking",
        "yield_after_seconds": 30 if managed else None,
        "resume_policy": "same_resume_identity" if managed else "none",
        "terminal_required_for_acceptance": True,
        "final_proof_reserve_seconds": 60,
    }


def synthesize_command_evidence_from_tool_call(
    call: Mapping[str, object],
    *,
    evidence_id: int,
    call_order: int,
    source: str = "synthesized_fixture",
) -> CommandEvidence | None:
    return command_evidence_from_tool_call(
        call,
        evidence_id=evidence_id,
        start_order=call_order * 2 - 1,
        finish_order=call_order * 2,
        source=source,
    )


def command_evidence_from_tool_call(
    call: Mapping[str, object],
    *,
    evidence_id: int,
    start_order: int,
    finish_order: int,
    source: str = "native_command",
) -> CommandEvidence | None:
    if not isinstance(call, Mapping):
        return None
    tool = str(call.get("tool") or "")
    if tool not in COMMAND_EVIDENCE_TOOLS:
        return None
    result = _dict_value(call.get("result"))
    parameters = _dict_value(call.get("parameters"))
    command = str(result.get("command") or parameters.get("command") or "")
    cwd = str(result.get("cwd") or parameters.get("cwd") or "")
    stdout = _combined_output_text(result, "stdout")
    stderr = _combined_output_text(result, "stderr")
    output = tool_call_output_text(dict(call))
    output_bytes = len(output.encode("utf-8")) if output else None
    timed_out = bool(result.get("timed_out"))
    exit_code = _coerce_int(result.get("exit_code"))
    raw_contract = parameters.get("execution_contract")
    if raw_contract is None:
        raw_contract = result.get("execution_contract")
    execution_contract = normalize_execution_contract(
        raw_contract,
        tool=tool,
        command=command,
        cwd=cwd,
    )
    wall_ceiling = _dict_value(parameters.get("wall_timeout_ceiling") or result.get("wall_timeout_ceiling"))
    requested_timeout = _coerce_int(wall_ceiling.get("requested_timeout_seconds"), default=_coerce_int(parameters.get("timeout")))
    effective_timeout = _coerce_int(
        wall_ceiling.get("capped_timeout_seconds"),
        default=_coerce_int(result.get("timeout"), default=_coerce_int(parameters.get("timeout"))),
    )
    return CommandEvidence(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=int(evidence_id),
        ref={"kind": "command_evidence", "id": int(evidence_id)},
        source=source,
        tool=tool,
        command=command,
        cwd=cwd,
        env_summary=summarize_env(parameters.get("env") or result.get("env")),
        start_order=int(start_order),
        finish_order=int(finish_order),
        started_at=str(call.get("started_at") or result.get("started_at") or "unknown"),
        finished_at=str(call.get("finished_at") or result.get("finished_at") or "unknown"),
        duration_seconds=_coerce_float(result.get("duration_seconds") or call.get("duration_seconds")),
        requested_timeout_seconds=requested_timeout,
        effective_timeout_seconds=effective_timeout,
        wall_budget_before_seconds=_coerce_int(
            wall_ceiling.get("remaining_seconds")
            or parameters.get("wall_budget_before_seconds")
            or result.get("wall_budget_before_seconds")
        ),
        wall_budget_after_seconds=_coerce_int(
            result.get("wall_budget_after_seconds"),
            default=_wall_budget_after_seconds(wall_ceiling, result),
        ),
        status=str(call.get("status") or ""),
        exit_code=exit_code,
        timed_out=timed_out,
        terminal_success=tool_call_terminal_success(dict(call)),
        output_ref=result.get("output_ref"),
        stdout_head=_head(stdout),
        stdout_tail=_tail(stdout),
        stderr_head=_head(stderr),
        stderr_tail=_tail(stderr),
        output_head=_head(output),
        output_tail=_tail(output),
        truncated=any(len(value) > COMMAND_OUTPUT_CLIP_CHARS for value in (stdout, stderr, output)),
        output_bytes=output_bytes,
        source_tool_call_id=call.get("id"),
        command_run_id=str(parameters.get("command_run_id") or result.get("command_run_id") or ""),
        execution_contract=execution_contract,
        fallback_used=bool(execution_contract.get("fallback_used")),
        contract_invalid_reason=str(execution_contract.get("contract_invalid_reason") or ""),
    )


def planned_long_build_command_stage(
    action_type: object,
    parameters: Mapping[str, object] | None,
    contract: Mapping[str, object],
) -> str:
    """Classify a planned command with the same stage logic used for recorded attempts."""
    if str(action_type or "") not in COMMAND_EVIDENCE_TOOLS:
        return ""
    parameters = dict(parameters or {})
    if isinstance(parameters.get("execution_contract"), Mapping):
        contract_stage = execution_contract_stage(
            normalize_execution_contract(
                parameters.get("execution_contract"),
                tool=action_type,
                command=parameters.get("command") or "",
                cwd=parameters.get("cwd") or "",
                task_contract=contract,
            )
        )
        if contract_stage:
            return contract_stage
    call = {
        "id": "planned",
        "tool": str(action_type or ""),
        "status": "completed",
        "parameters": parameters,
        "result": {
            "command": parameters.get("command") or "",
            "cwd": parameters.get("cwd") or "",
            "exit_code": 0,
        },
    }
    evidence = command_evidence_from_tool_call(
        call,
        evidence_id=0,
        start_order=0,
        finish_order=0,
        source="planned_timeout_policy",
    )
    if evidence is None:
        return ""
    return _command_stage(evidence, contract)


def planned_long_build_command_budget_stage(
    action_type: object,
    parameters: Mapping[str, object] | None,
    contract: Mapping[str, object],
) -> str:
    if isinstance((parameters or {}).get("execution_contract"), Mapping):
        contract_stage = execution_contract_stage(
            normalize_execution_contract(
                (parameters or {}).get("execution_contract"),
                tool=action_type,
                command=(parameters or {}).get("command") or "",
                cwd=(parameters or {}).get("cwd") or "",
                task_contract=contract,
            )
        )
        if contract_stage:
            return contract_stage
    stage = planned_long_build_command_stage(action_type, parameters, contract)
    command = str((parameters or {}).get("command") or "")
    if (
        stage == "custom_runtime_smoke"
        and _command_uses_source_acquisition_tool(command)
        and not _command_has_non_source_acquisition_build_segment(command)
    ):
        return "source_acquisition"
    if stage in {
        "artifact_proof",
        "build",
        "custom_runtime_smoke",
        "default_smoke",
        "dependency_generation",
        "runtime_build",
        "runtime_install",
    }:
        return stage
    if not command or str(action_type or "") not in COMMAND_EVIDENCE_TOOLS:
        return stage
    if not _BUILD_RE.search(command):
        return stage
    cwd = str((parameters or {}).get("cwd") or "")
    artifact_paths = [
        str((artifact or {}).get("path") or "")
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping) and (artifact or {}).get("path")
    ]
    if any(_command_has_default_smoke_artifact_segment(command, path, cwd) for path in artifact_paths):
        return "default_smoke"
    artifact_names = [Path(path).name for path in artifact_paths if path]
    artifact_mentioned = any(
        item and re.search(r"(?:^|[\s/])" + re.escape(item) + r"(?:$|[\s;&|])", command)
        for item in [*artifact_paths, *artifact_names]
    )
    if artifact_mentioned:
        return "build"
    if _CONFIGURE_RE.search(command) and (_INSTALL_RE.search(command) or _DEPENDENCY_GENERATION_RE.search(command)):
        return "dependency_generation"
    return stage


def _command_has_non_source_acquisition_build_segment(command: object) -> bool:
    for segment in split_unquoted_shell_command_segments(command):
        if _segment_uses_source_acquisition_tool(segment):
            continue
        if _segment_invokes_build_tool(segment):
            return True
    return False


def _segment_invokes_build_tool(segment: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    command_token = _long_dependency_invoked_command_token(parts)
    if not command_token:
        return False
    command_name = Path(command_token).name.casefold()
    command_index = next((index for index, part in enumerate(parts) if str(part or "") == command_token), None)
    if command_index is None:
        return False
    tail = [str(part or "").casefold() for part in parts[command_index + 1 :]]
    if command_name in {"make", "ninja"}:
        return True
    if command_name in {"cargo", "go"}:
        return bool(tail and tail[0] == "build")
    if command_name == "npm":
        return len(tail) >= 2 and tail[0] == "run" and tail[1] == "build"
    if command_name in {"python", "python3"} or re.fullmatch(r"python3(?:\.\d+)?", command_name):
        return len(tail) >= 2 and tail[0] == "-m" and tail[1] == "build"
    if command_name == "opam":
        return bool(tail and tail[0] == "install")
    if command_name in {"pip", "pip3"} or re.fullmatch(r"pip3(?:\.\d+)?", command_name):
        return bool(tail and tail[0] == "install")
    return False


def command_evidence_to_tool_call(evidence: CommandEvidence | Mapping[str, object]) -> dict:
    if isinstance(evidence, CommandEvidence):
        evidence = evidence.to_dict()
    evidence = dict(evidence or {})
    output = _merge_head_tail(evidence.get("output_head"), evidence.get("output_tail"))
    return {
        "id": evidence.get("id"),
        "tool": evidence.get("tool") or "run_command",
        "status": evidence.get("status") or "",
        "started_at": evidence.get("started_at") or "",
        "finished_at": evidence.get("finished_at") or "",
        "parameters": {
            "command": evidence.get("command") or "",
            "cwd": evidence.get("cwd") or "",
            "command_run_id": evidence.get("command_run_id") or "",
            "execution_contract": evidence.get("execution_contract") or {},
        },
        "result": {
            "command": evidence.get("command") or "",
            "cwd": evidence.get("cwd") or "",
            "exit_code": evidence.get("exit_code"),
            "timed_out": bool(evidence.get("timed_out")),
            "stdout": _merge_head_tail(evidence.get("stdout_head"), evidence.get("stdout_tail")),
            "stderr": _merge_head_tail(evidence.get("stderr_head"), evidence.get("stderr_tail")),
            "text": output,
            "summary": output,
            "output": output,
        },
    }


def long_dependency_artifact_proven_by_command_evidence(
    evidence: CommandEvidence | Mapping[str, object],
    artifact: object,
) -> bool:
    if not isinstance(evidence, CommandEvidence):
        evidence = CommandEvidence.from_dict(evidence)
    if evidence.schema_version != LONG_BUILD_SCHEMA_VERSION:
        return False
    if evidence.tool not in COMMAND_EVIDENCE_TOOLS:
        return False
    if not command_evidence_terminal_acceptance_success(evidence):
        return False
    return long_dependency_artifact_proven_by_call(command_evidence_to_tool_call(evidence), artifact)


def command_evidence_terminal_acceptance_success(evidence: CommandEvidence | Mapping[str, object]) -> bool:
    if not isinstance(evidence, CommandEvidence):
        evidence = CommandEvidence.from_dict(evidence)
    if _contract_blocks_acceptance(evidence):
        return False
    if evidence.status != "completed":
        return False
    if evidence.exit_code != 0:
        return False
    if evidence.timed_out:
        return False
    if evidence.finish_order <= 0:
        return False
    return bool(evidence.terminal_success)


def _latest_long_command_run_with_status(
    runs: Iterable[LongCommandRun],
    statuses: set[str],
) -> LongCommandRun | None:
    latest = None
    for run in runs or []:
        if str(run.status or "").casefold() in statuses:
            latest = run
    return latest


def _latest_long_command_run(runs: Iterable[LongCommandRun]) -> LongCommandRun | None:
    latest = None
    for run in runs or []:
        latest = run
    return latest


def _cap_timed_out_long_command_budgets_by_prior_wall(
    runs: Iterable[LongCommandRun],
) -> list[LongCommandRun]:
    capped_runs = []
    prior_remaining: int | None = None
    for run in runs or []:
        current = run
        budget = dict(run.budget or {})
        remaining = _coerce_int(budget.get("work_wall_remaining_seconds"))
        effective_timeout = _coerce_int(budget.get("effective_timeout_seconds"))
        if (
            str(run.status or "").casefold() == "timed_out"
            and prior_remaining is not None
            and effective_timeout is not None
        ):
            capped_remaining = max(0, prior_remaining - effective_timeout)
            if remaining is None or capped_remaining < remaining:
                data = run.to_dict()
                budget = dict(data.get("budget") or {})
                budget["work_wall_remaining_seconds"] = capped_remaining
                data["budget"] = budget
                current = LongCommandRun.from_dict(data)
                remaining = capped_remaining
        if remaining is not None:
            prior_remaining = remaining if prior_remaining is None else min(prior_remaining, remaining)
        capped_runs.append(current)
    return capped_runs


def _long_command_evidence_id(ref: object) -> int | None:
    if not isinstance(ref, Mapping):
        return None
    return _coerce_int(ref.get("id"))


def _derive_long_command_poll_recovery_decision(
    contract: Mapping[str, object],
    run: LongCommandRun,
) -> RecoveryDecision:
    contract_id = str(contract.get("id") or run.contract_id or "")
    return RecoveryDecision(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=f"{contract_id}:recovery:long_command:{_safe_path_component(run.id)}",
        contract_id=contract_id,
        state_status="in_progress",
        failure_class="long_command_running",
        prerequisites=["active_long_command_run"],
        clear_condition="terminal command evidence is finalized",
        allowed_next_action={
            "kind": "poll_long_command",
            "long_command_run_id": run.id,
            "stage": run.stage or "continue_long_command",
            "required_evidence": "terminal_command_progress_or_success",
            "targets": _contract_artifact_paths(contract),
        },
        prohibited_repeated_actions=[
            "source_reacquisition",
            "clean_rebuild",
            "abandon_existing_source_tree_progress",
        ],
        budget={
            "remaining_seconds": _coerce_int(run.budget.get("work_wall_remaining_seconds")),
            "reserve_seconds": _coerce_int(run.budget.get("final_proof_reserve_seconds"), default=60),
            "may_spend_reserve": False,
            "minimum_poll_seconds": 5,
            "continuation_count": _coerce_int(run.budget.get("continuation_count"), default=0) or 0,
            "max_continuations": _coerce_int(run.budget.get("max_continuations"), default=3) or 3,
        },
        decision="continue",
    )


def _long_command_terminal_failure(run: LongCommandRun) -> dict:
    status = str(run.status or "").casefold()
    failure_class = "build_timeout" if status in {"timed_out", "killed"} else "long_command_failed"
    if status == "interrupted":
        failure_class = "long_command_interrupted"
    if status == "failed" and str(run.stage or "") == "source_acquisition":
        failure_class = "source_acquisition_failed"
    return {
        "failure_class": failure_class,
        "source": "long_command_run",
        "long_command_run_id": run.id,
        "stage": run.stage,
        "status": run.status,
        "excerpt": _first_nonempty_line((run.output or {}).get("stderr_tail") or (run.output or {}).get("stdout_tail") or ""),
    }


def _derive_long_command_terminal_recovery_decision(
    contract: Mapping[str, object],
    run: LongCommandRun,
    status: str,
) -> RecoveryDecision:
    contract_id = str(contract.get("id") or run.contract_id or "")
    failure = _long_command_terminal_failure(run)
    failure_class = str(failure.get("failure_class") or "")
    if failure_class not in {"build_timeout", "long_command_interrupted"}:
        return RecoveryDecision(
            schema_version=LONG_BUILD_SCHEMA_VERSION,
            id=f"{contract_id}:recovery:long_command:{_safe_path_component(run.id)}",
            contract_id=contract_id,
            state_status=status,
            failure_class=failure_class,
            prerequisites=["diagnose_terminal_failure", "changed_command_or_new_source_channel"],
            clear_condition="run a repaired command and produce terminal successful evidence",
            allowed_next_action={
                "kind": "repair_failed_long_command",
                "long_command_run_id": run.id,
                "stage": run.stage or "continue_or_repair_build",
                "failed_idempotence_key": run.idempotence_key,
                "failed_status": run.status,
                "failed_exit_code": (run.terminal or {}).get("exit_code"),
                "required_evidence": "terminal_command_progress_or_success",
                "targets": _contract_artifact_paths(contract),
            },
            prohibited_repeated_actions=[
                "repeat_identical_failed_command_without_new_evidence",
                "repeat_same_failed_source_url_without_new_source_channel",
                "abandon_existing_diagnostic_output",
            ],
            budget={
                "remaining_seconds": _coerce_int(run.budget.get("work_wall_remaining_seconds")),
                "reserve_seconds": _coerce_int(run.budget.get("final_proof_reserve_seconds"), default=60),
                "may_spend_reserve": False,
                "minimum_repair_seconds": 600,
                "minimum_repair_seconds_by_stage": {
                    "diagnostic": 30,
                    "source_acquisition": 60,
                    "source_authority": 60,
                    "configure": 120,
                },
                "continuation_count": _coerce_int(run.budget.get("continuation_count"), default=0) or 0,
                "max_continuations": _coerce_int(run.budget.get("max_continuations"), default=3) or 3,
            },
            decision="continue",
        )
    minimum_resume_seconds = LONG_COMMAND_MINIMUM_RESUME_SECONDS
    reserve_seconds = _coerce_int(
        run.budget.get("final_proof_reserve_seconds"),
        default=LONG_COMMAND_DEFAULT_FINAL_PROOF_RESERVE_SECONDS,
    )
    remaining_seconds = _coerce_int(run.budget.get("work_wall_remaining_seconds"))
    if remaining_seconds is not None and remaining_seconds < minimum_resume_seconds + reserve_seconds:
        return RecoveryDecision(
            schema_version=LONG_BUILD_SCHEMA_VERSION,
            id=f"{contract_id}:recovery:long_command:{_safe_path_component(run.id)}",
            contract_id=contract_id,
            state_status=status,
            failure_class=failure_class,
            prerequisites=["valid_source_tree", "same_idempotence_key", "fresh_wall_budget"],
            clear_condition="resume budget exhausted before required artifact proof",
            allowed_next_action={
                "kind": "resume_budget_exhausted",
                "long_command_run_id": run.id,
                "stage": run.stage or "continue_or_resume_build",
                "idempotence_key": run.idempotence_key,
                "required_evidence": "new_work_session_or_larger_wall_budget",
                "targets": _contract_artifact_paths(contract),
            },
            prohibited_repeated_actions=[
                "low_wall_model_retry",
                "resume_without_larger_wall_budget",
                "abandon_existing_source_tree_progress",
            ],
            budget={
                "remaining_seconds": remaining_seconds,
                "reserve_seconds": reserve_seconds,
                "may_spend_reserve": False,
                "minimum_resume_seconds": minimum_resume_seconds,
                "continuation_count": _coerce_int(run.budget.get("continuation_count"), default=0) or 0,
                "max_continuations": _coerce_int(run.budget.get("max_continuations"), default=3) or 3,
            },
            decision="stop",
        )
    return RecoveryDecision(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=f"{contract_id}:recovery:long_command:{_safe_path_component(run.id)}",
        contract_id=contract_id,
        state_status=status,
        failure_class=failure_class,
        prerequisites=["valid_source_tree", "same_idempotence_key", "larger_or_diagnostic_budget"],
        clear_condition="resume same idempotent command and produce terminal successful evidence",
        allowed_next_action={
            "kind": "resume_idempotent_long_command",
            "long_command_run_id": run.id,
            "stage": run.stage or "continue_or_resume_build",
            "idempotence_key": run.idempotence_key,
            "required_evidence": "terminal_command_progress_or_success",
            "targets": _contract_artifact_paths(contract),
        },
        prohibited_repeated_actions=[
            "source_reacquisition",
            "clean_rebuild",
            "repeat_same_timeout_without_budget_change",
            "abandon_existing_source_tree_progress",
        ],
        budget={
            "remaining_seconds": remaining_seconds,
            "reserve_seconds": reserve_seconds,
            "may_spend_reserve": False,
            "minimum_resume_seconds": minimum_resume_seconds,
            "continuation_count": _coerce_int(run.budget.get("continuation_count"), default=0) or 0,
            "max_continuations": _coerce_int(run.budget.get("max_continuations"), default=3) or 3,
        },
        decision="continue",
    )


def _contract_artifact_paths(contract: Mapping[str, object]) -> list[str]:
    return [
        str((artifact or {}).get("path") or "")
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping) and str((artifact or {}).get("path") or "")
    ]


def fresh_long_dependency_artifact_evidence(
    evidences: Iterable[CommandEvidence | Mapping[str, object]],
    artifact: object,
) -> CommandEvidence | None:
    latest: CommandEvidence | None = None
    normalized = [item if isinstance(item, CommandEvidence) else CommandEvidence.from_dict(item) for item in evidences or []]
    for evidence in normalized:
        if long_dependency_artifact_proven_by_command_evidence(evidence, artifact):
            latest = evidence
            continue
        if latest and evidence.finish_order > latest.finish_order and _command_may_mutate_artifact_scope(
            evidence.command,
            artifact,
            evidence.cwd,
        ):
            latest = None
    return latest


def _artifact_kind(path: object) -> str:
    suffix = Path(str(path or "")).suffix.casefold()
    if suffix in {"", ".exe", ".out", ".bin"}:
        return "executable"
    if suffix in {".a", ".so", ".dylib", ".dll", ".lib"}:
        return "library"
    return "file"


def _runtime_proof_required(text: object, artifacts: Iterable[Mapping[str, object]]) -> bool:
    value = str(text or "")
    if _RUNTIME_PROOF_EVIDENCE_MARKER_RE.search(value):
        return True
    if _RUNTIME_PROOF_TASK_MARKER_RE.search(value):
        return True
    for artifact in artifacts or []:
        name = Path(str((artifact or {}).get("path") or "")).name.casefold()
        if name and re.search(r"(?:cc|gcc|clang|compiler|ld|link|interp|runtime|sdk|vm)", name):
            return True
    return False


def _runtime_proof_reason(text: object, artifacts: Iterable[Mapping[str, object]], required: bool) -> str:
    if not required:
        return "task does not require default runtime/link proof"
    value = str(text or "")
    if _RUNTIME_PROOF_EVIDENCE_MARKER_RE.search(value):
        return "task or evidence mentions default link/runtime behavior"
    if _RUNTIME_PROOF_TASK_MARKER_RE.search(value):
        return "task asks for a compiler/toolchain/runtime-like artifact"
    names = [Path(str((artifact or {}).get("path") or "")).name for artifact in artifacts or []]
    return "artifact name is compiler/toolchain-like: " + ", ".join(name for name in names if name)


def _typed_contract_present(evidence: CommandEvidence) -> bool:
    contract = evidence.execution_contract
    return isinstance(contract, Mapping) and int(contract.get("schema_version") or 0) >= EXECUTION_CONTRACT_SCHEMA_VERSION and not bool(
        contract.get("fallback_used")
    )


def _contract_blocks_acceptance(evidence: CommandEvidence) -> bool:
    return _typed_contract_present(evidence) and bool(evidence.contract_invalid_reason)


def _legacy_stage_classifier_allowed(evidence: CommandEvidence) -> bool:
    source = str(evidence.source or "")
    return bool(evidence.fallback_used or (evidence.execution_contract or {}).get("fallback_used")) and source in {
        "planned_timeout_policy",
        "synthesized_fixture",
    }


def _typed_proof_matches(evidence: CommandEvidence, *, proof_roles: set[str], acceptance_kinds: set[str]) -> bool:
    if _contract_blocks_acceptance(evidence):
        return False
    if _typed_contract_present(evidence):
        contract = evidence.execution_contract or {}
        primary_match = _contract_role_matches(contract, proof_roles=proof_roles, acceptance_kinds=acceptance_kinds)
        substep_match = any(
            isinstance(substep, Mapping)
            and execution_contract_is_valid(substep)
            and _contract_role_matches(substep, proof_roles=proof_roles, acceptance_kinds=acceptance_kinds)
            for substep in contract.get("substeps") or []
        )
        if _compound_acceptance_requires_substeps(evidence):
            return substep_match
        return primary_match or substep_match
    return _legacy_stage_classifier_allowed(evidence)


def _contract_role_matches(contract: Mapping[str, object], *, proof_roles: set[str], acceptance_kinds: set[str]) -> bool:
    proof_role = str((contract or {}).get("proof_role") or "")
    acceptance_kind = str((contract or {}).get("acceptance_kind") or "")
    return proof_role in proof_roles and acceptance_kind in acceptance_kinds


def _compound_acceptance_requires_substeps(evidence: CommandEvidence) -> bool:
    contract = evidence.execution_contract or {}
    if contract.get("migration_source"):
        return False
    acceptance_kind = str(contract.get("acceptance_kind") or "")
    if acceptance_kind in {"not_acceptance", "progress_only"}:
        return False
    command = str(evidence.command or "")
    return len(split_unquoted_shell_command_segments(command)) > 1


def _artifact_proof_contract_allows_acceptance(evidence: CommandEvidence) -> bool:
    return _typed_proof_matches(
        evidence,
        proof_roles={"final_artifact", "target_build", "default_smoke", "custom_runtime_smoke"},
        acceptance_kinds={
            "candidate_artifact_proof",
            "candidate_runtime_smoke",
            "candidate_final_proof",
        },
    )


def _source_authority_contract_allows_acceptance(evidence: CommandEvidence) -> bool:
    return _typed_proof_matches(
        evidence,
        proof_roles={"source_authority"},
        acceptance_kinds={"candidate_source_authority", "candidate_final_proof"},
    )


def _default_smoke_contract_allows_acceptance(evidence: CommandEvidence) -> bool:
    return _typed_proof_matches(
        evidence,
        proof_roles={"default_smoke"},
        acceptance_kinds={"candidate_runtime_smoke", "candidate_final_proof"},
    )


def _command_stage(evidence: CommandEvidence, contract: Mapping[str, object]) -> str:
    if _contract_blocks_acceptance(evidence):
        return "command"
    contract_stage = execution_contract_stage(evidence.execution_contract)
    if contract_stage:
        return contract_stage
    if not _legacy_stage_classifier_allowed(evidence):
        return "command"
    text = f"{evidence.command}\n{evidence.output_head}\n{evidence.output_tail}"
    if _custom_runtime_path_proof(evidence):
        return "custom_runtime_smoke"
    if _default_compile_link_smoke(evidence, contract):
        return "default_smoke"
    if _produced_artifacts(evidence, contract):
        return "artifact_proof"
    if _RUNTIME_PROOF_EVIDENCE_MARKER_RE.search(text):
        if _INSTALL_RE.search(text):
            return "runtime_install"
        return "default_smoke"
    if _RUNTIME_BUILD_RE.search(text) and _BUILD_RE.search(text):
        return "runtime_build"
    if _DEPENDENCY_GENERATION_RE.search(text):
        return "dependency_generation"
    if _CONFIGURE_RE.search(text):
        return "configure"
    if _source_authority_signal(evidence) or _command_uses_source_acquisition_tool(evidence.command):
        return "source_acquisition"
    if _BUILD_RE.search(text):
        return "build"
    return "command"


def _selected_target(command: object, contract: Mapping[str, object]) -> str:
    command_text = str(command or "")
    artifact_names = [
        Path(str((artifact or {}).get("path") or "")).name
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping)
    ]
    for name in artifact_names:
        if name and re.search(r"(?:^|[\s/])" + re.escape(name) + r"(?:$|\s)", command_text):
            return name
    make_match = re.search(r"\bmake\b(?:\s+-[A-Za-z0-9\"'$()._-]+)*\s+([A-Za-z0-9_./+-]+)", command_text)
    if make_match:
        return make_match.group(1)
    return ""


def _attempt_result(evidence: CommandEvidence) -> str:
    status = str(evidence.status or "").casefold()
    if status in {"running", "yielded", "interrupted"}:
        return status
    if evidence.timed_out:
        return "timeout"
    if command_evidence_terminal_acceptance_success(evidence):
        return "success"
    if status == "completed" or evidence.exit_code not in (None, 0):
        return "failure"
    return "unknown"


def _produced_artifacts(evidence: CommandEvidence, contract: Mapping[str, object]) -> list[dict]:
    if not _artifact_proof_contract_allows_acceptance(evidence):
        return []
    produced = []
    for artifact in contract.get("required_artifacts") or []:
        path = str((artifact or {}).get("path") or "")
        if path and (
            long_dependency_artifact_proven_by_command_evidence(evidence, path)
            or _terminal_command_uses_required_artifact(evidence, path)
        ):
            produced.append({"path": path, "proof_evidence_id": evidence.id})
    return produced


def _diagnostics(evidence: CommandEvidence, contract: Mapping[str, object] | None = None) -> list[dict]:
    text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    diagnostics = []
    final_default_smoke_satisfied = bool(contract and _default_compile_link_smoke(evidence, contract))
    if _source_authority_signal(evidence):
        diagnostics.append({"signal": "source_authority", "excerpt": _source_authority_excerpt(evidence)})
    if evidence.timed_out:
        diagnostics.append({"failure_class": "build_timeout", "excerpt": _first_nonempty_line(text)})
    if (
        re.search(r"cannot find -l|ld: library not found|missing runtime|stdlib", text, re.I)
        and not final_default_smoke_satisfied
    ):
        diagnostics.append({"failure_class": "runtime_link_failed", "excerpt": _first_matching_line(text, "cannot find -l|library not found|runtime|stdlib")})
    if re.search(r"no rule to make target|No rule to make target", text):
        diagnostics.append({"failure_class": "build_system_target_surface_invalid", "excerpt": _first_matching_line(text, "no rule")})
    if _BUILD_FAILURE_RE.search(text) and not diagnostics and not final_default_smoke_satisfied:
        diagnostics.append({"failure_class": "build_failed", "excerpt": _first_matching_line(text, _BUILD_FAILURE_RE.pattern)})
    return [item for item in diagnostics if item.get("failure_class") or item.get("signal")]


def _source_authority_signal(evidence: CommandEvidence) -> bool:
    if not _source_authority_contract_allows_acceptance(evidence):
        return False
    text = f"{evidence.command}\n{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    output_text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    if _saved_authority_page_archive_signal(evidence, output_text):
        return True
    if _validated_source_archive_acquisition_signal(evidence):
        return True
    if _selected_authoritative_source_archive_acquisition_signal(evidence, output_text):
        return True
    if _command_uses_direct_source_acquisition_tool(evidence.command):
        has_direct_source_authority = bool(_DIRECT_SOURCE_AUTHORITY_OUTPUT_RE.search(output_text))
        direct_authority_urls = _direct_source_authority_output_urls(output_text)
        remote_source_urls = _command_remote_source_urls(evidence.command)
        direct_authority_url_matches_fetch = not direct_authority_urls or bool(direct_authority_urls & remote_source_urls)
        non_python_remote = _command_has_strict_non_python_remote_source_acquisition(evidence.command)
        python_remote = _command_uses_python_remote_source_acquisition_tool(evidence.command)
        if (
            has_direct_source_authority
            and direct_authority_url_matches_fetch
            and (
                non_python_remote
                or (
                    python_remote
                    and _command_enables_errexit(evidence.command)
                    and not _command_disables_errexit(evidence.command)
                    and not _command_masks_python_source_fetch_failure(evidence.command)
                    and _PYTHON_SOURCE_ARCHIVE_OUTPUT_RE.search(output_text)
                )
            )
        ):
            return True
        if _command_has_assertion_only_source_authority_segment(evidence.command):
            return False
        return bool(_SOURCE_AUTHORITY_RE.search(output_text) and not _BUILD_FAILURE_RE.search(output_text))
    if _command_has_assertion_only_source_authority_segment(evidence.command):
        return False
    if _SOURCE_AUTHORITY_RE.search(text) and _command_uses_source_acquisition_tool(evidence.command):
        return True
    return bool(_command_uses_package_metadata_tool(evidence.command) and _PACKAGE_METADATA_OUTPUT_RE.search(output_text))


def _source_authority_excerpt(evidence: CommandEvidence) -> str:
    text = f"{evidence.command}\n{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    output_text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    if _AUTHORITY_PAGE_OUTPUT_RE.search(output_text):
        return _first_matching_line(output_text, _AUTHORITY_PAGE_OUTPUT_RE.pattern)
    if _validated_source_archive_acquisition_signal(evidence):
        return "validated source archive acquisition"
    if _DIRECT_SOURCE_AUTHORITY_OUTPUT_RE.search(output_text):
        return _first_matching_line(output_text, _DIRECT_SOURCE_AUTHORITY_OUTPUT_RE.pattern)
    if _SOURCE_AUTHORITY_RE.search(text):
        return _first_matching_line(text, _SOURCE_AUTHORITY_RE.pattern)
    return _first_matching_line(output_text, _PACKAGE_METADATA_OUTPUT_RE.pattern)


def _saved_authority_page_archive_signal(evidence: CommandEvidence, output_text: str) -> bool:
    if not (
        _marked_authority_page_archive_identity(output_text)
        or _saved_authority_archive_readback_identity(evidence, output_text)
    ):
        return False
    command = str(evidence.command or "")
    if not (_command_enables_errexit(command) and not _command_disables_errexit(command)):
        return False
    if _command_masks_remote_source_fetch_failure(command):
        return False
    if _command_uses_python_remote_source_acquisition_tool(command):
        return False
    if _command_has_authority_page_readback(command):
        return True
    return bool(_command_has_strict_non_python_remote_source_acquisition(command))


def _marked_authority_page_archive_identity(output_text: str) -> bool:
    return bool(
        _AUTHORITY_PAGE_OUTPUT_RE.search(output_text)
        and _ARCHIVE_HASH_OUTPUT_RE.search(output_text)
        and _ARCHIVE_ROOT_OUTPUT_RE.search(output_text)
    )


def _saved_authority_archive_readback_identity(evidence: CommandEvidence, output_text: object) -> bool:
    command = evidence.command
    if not _command_has_authority_page_readback(command):
        return False
    if _command_defines_shell_function(command):
        return False
    if not _command_readbacks_source_archive_identity(command):
        return False
    text = str(output_text or "")
    return bool(
        _saved_authority_readback_output_signal(text)
        and _source_acquisition_completed_output_signal(text)
        and _archive_root_listing_output_signal(text)
    )


def _saved_source_archive_identity_readback_signal(evidence: CommandEvidence, output_text: object) -> bool:
    return bool(_saved_source_archive_identity_readback_paths(evidence, output_text))


def _saved_source_url_archive_readback_signal(
    evidence: CommandEvidence,
    output_text: object,
    *,
    fabricated_source_url_paths: Iterable[object] = (),
) -> bool:
    if not command_evidence_terminal_acceptance_success(evidence):
        return False
    command = evidence.command
    if _command_defines_shell_function(command):
        return False
    if _command_has_assertion_only_source_authority_segment(command):
        return False
    read_paths = _command_saved_source_url_readback_paths(command)
    if not read_paths:
        return False
    fabricated_paths = {str(path or "").strip("'\"") for path in fabricated_source_url_paths or []}
    if _DYNAMIC_SOURCE_URL_WRITER_PATH in fabricated_paths:
        return False
    if fabricated_paths and read_paths & fabricated_paths:
        return False
    if not any(_authoritative_source_archive_url(url) for url in _saved_source_url_output_urls(output_text)):
        return False
    return _saved_source_archive_identity_readback_signal(evidence, output_text)


def _saved_source_url_output_urls(output_text: object) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(r"^source_url=(https?://\S+)", str(output_text or ""), re.I | re.M):
        urls.add(match.group(1).rstrip("'\"),;"))
    return urls


def _command_reads_saved_source_url_file(command: object) -> bool:
    return bool(_command_saved_source_url_readback_paths(command))


def _command_saved_source_url_readback_paths(command: object) -> set[str]:
    paths: set[str] = set()
    for parts in _invoked_command_parts(command):
        values = [str(part or "").strip("'\"") for part in parts]
        if not values:
            continue
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        if token not in {"awk", "cat", "grep", "sed"}:
            continue
        paths.update(value for value in values[1:] if re.search(r"source[-_]url", value, re.I))
    return paths


def _saved_source_archive_identity_readback_paths(evidence: CommandEvidence, output_text: object) -> set[str]:
    if not command_evidence_terminal_acceptance_success(evidence):
        return set()
    command = evidence.command
    if _command_defines_shell_function(command):
        return set()
    if _command_has_assertion_only_source_authority_segment(command):
        return set()
    readback_paths = _command_hashes_source_archive_paths(command) & _command_lists_source_archive_paths(command)
    if not readback_paths:
        return set()
    readback_paths = {path for path in readback_paths if _versioned_source_archive_path(path)}
    if not readback_paths:
        return set()
    text = str(output_text or "")
    if not _archive_listing_output_signal(text):
        return set()
    return {path for path in readback_paths if _source_archive_hash_output_for_path(text, path)}


def _selected_authoritative_source_archive_acquisition_signal(
    evidence: CommandEvidence,
    output_text: object,
) -> bool:
    if not command_evidence_terminal_acceptance_success(evidence):
        return False
    command = str(evidence.command or "")
    if not (
        _command_enables_errexit(command)
        and not _command_disables_errexit(command)
        and not _command_disables_pipefail(command)
        and not _command_masks_remote_source_fetch_failure(command)
    ):
        return False
    if _command_uses_python_remote_source_acquisition_tool(command):
        return False
    if _command_defines_shell_function(command):
        return False
    text = str(output_text or "")
    selected_urls = _selected_source_archive_output_urls(text)
    if not selected_urls:
        return False
    authoritative_archive_paths = _selected_authoritative_source_archive_fetch_paths(command, selected_urls)
    archive_paths = _command_hashes_source_archive_paths(command) & _command_lists_source_archive_paths(command)
    archive_paths = {path for path in archive_paths if _versioned_source_archive_path(path)}
    archive_paths &= authoritative_archive_paths
    if not archive_paths:
        return False
    for path in archive_paths:
        if not _command_validates_and_extracts_archive_path(command, path):
            continue
        if _source_archive_hash_output_for_path(text, path) and _archive_listing_output_signal(text):
            return True
    return False


def _selected_source_archive_output_urls(output_text: object) -> set[str]:
    urls: set[str] = set()
    after_marker = False
    for line in str(output_text or "").splitlines():
        stripped = line.strip()
        if _SELECTED_SOURCE_ARCHIVE_OUTPUT_RE.search(stripped):
            after_marker = True
            continue
        if not after_marker:
            continue
        line_urls = {url for url in _extract_urls(stripped) if _authoritative_source_archive_url(url)}
        if line_urls:
            urls.update(line_urls)
            continue
        if not stripped:
            continue
        break
    return urls


def _selected_authoritative_source_archive_fetch_paths(command: object, selected_urls: Iterable[object]) -> set[str]:
    command_text = _strip_heredoc_bodies(command)
    selected = {str(url or "").rstrip("'\"),;") for url in selected_urls if _authoritative_source_archive_url(url)}
    if not selected:
        return set()
    paths: set[str] = set()
    assignments: dict[str, str] = {}
    for segment in _top_level_direct_fetch_segments(command_text):
        try:
            raw_parts = shlex.split(str(segment or ""))
        except ValueError:
            raw_parts = str(segment or "").split()
        resolved_parts = _resolve_shell_parts(_drop_shell_control_prefix(raw_parts), assignments)
        token = Path(_long_dependency_invoked_command_token(resolved_parts)).name.casefold()
        source_tokens = _curl_wget_effective_source_tokens(resolved_parts)
        if (
            token in {"curl", "wget"}
            and not _curl_wget_uses_no_download_mode(resolved_parts)
            and len(source_tokens) == 1
            and source_tokens[0] in selected
        ):
            path = _curl_wget_output_path(resolved_parts)
            if path and _versioned_source_archive_path(path):
                paths.add(path)
        _apply_top_level_shell_assignment_segment(assignments, segment)
    paths.update(_selected_loop_alias_authoritative_source_archive_fetch_paths(command_text, selected))
    return paths


def _selected_loop_alias_authoritative_source_archive_fetch_paths(
    command_text: object,
    selected_urls: set[str],
) -> set[str]:
    paths: set[str] = set()
    for variable, values, body in _top_level_for_loop_blocks(command_text):
        urls = _extract_urls_in_order(values)
        if not urls or not _authoritative_source_archive_url(urls[0]) or urls[0] not in selected_urls:
            continue
        body_parts = _invoked_command_parts(body)
        aliases = set()
        if not any(_parts_invalidates_selected_loop_variable(parts, variable) for parts in body_parts):
            aliases.add(variable)
        for index, parts in enumerate(body_parts):
            alias = _parts_alias_variable_from_loop_variable(parts, variable)
            if alias and not any(
                _parts_invalidates_selected_loop_variable(later_parts, alias, empty_assignment_invalidates=True)
                for later_parts in body_parts[index + 1 :]
            ):
                aliases.add(alias)
        for alias in aliases:
            paths.update(_top_level_fetch_paths_after_selected_variable_print(command_text, alias))
    return paths


def _parts_alias_variable_from_loop_variable(parts: Iterable[object], variable: str) -> str:
    values = [str(part or "").strip("'\"") for part in parts]
    if len(values) != 1:
        return ""
    match = re.fullmatch(rf"([A-Za-z_][A-Za-z0-9_]*)=\$\{{?{re.escape(variable)}\}}?", values[0])
    return match.group(1) if match else ""


def _top_level_fetch_paths_after_selected_variable_print(
    command: object,
    variable: str,
) -> set[str]:
    paths: set[str] = set()
    selected_print_seen = False
    assignments: dict[str, str] = {}
    top_level_segments = _top_level_direct_fetch_segments(command)
    marker_segments = _selected_marker_segments(top_level_segments)
    if len(marker_segments) != 1:
        return set()
    expected_marker = marker_segments[0]
    for segment in top_level_segments:
        if segment == expected_marker and not _segment_prints_selected_archive_variable(segment, variable):
            return set()
        if _segment_prints_selected_archive_variable(segment, variable):
            selected_print_seen = True
            _apply_top_level_shell_assignment_segment(assignments, segment)
            continue
        if not selected_print_seen:
            if _segment_invalidates_selected_loop_variable(segment, variable):
                return set()
            _apply_top_level_shell_assignment_segment(assignments, segment)
            continue
        try:
            raw_parts = shlex.split(str(segment or ""))
        except ValueError:
            raw_parts = str(segment or "").split()
        resolved_parts = _resolve_shell_parts(_drop_shell_control_prefix(raw_parts), assignments)
        token = Path(_long_dependency_invoked_command_token(resolved_parts)).name.casefold()
        if (
            token not in {"curl", "wget"}
            or _curl_wget_uses_no_download_mode(resolved_parts)
            or not _parts_fetches_exact_loop_variable_source(raw_parts, variable)
        ):
            selected_print_seen = False
            _apply_top_level_shell_assignment_segment(assignments, segment)
            continue
        path = _curl_wget_output_path(resolved_parts)
        if path and _versioned_source_archive_path(path):
            paths.add(path)
        selected_print_seen = False
        _apply_top_level_shell_assignment_segment(assignments, segment)
    return paths


def _segment_invalidates_selected_loop_variable(segment: object, variable: str) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    return _parts_invalidates_selected_loop_variable(parts, variable)


def _parts_invalidates_selected_loop_variable(
    parts: Iterable[object],
    variable: str,
    *,
    empty_assignment_invalidates: bool = False,
) -> bool:
    values = _drop_shell_builtin_mutation_wrapper_prefix(_drop_shell_control_prefix(parts))
    if not values:
        return False
    invoked = str(_long_dependency_invoked_command_token(values) or "")
    token = Path(invoked).name.casefold() or invoked.casefold()
    if token == "eval" or token == "source" or invoked == ".":
        return True
    if token in {"unset", "read", "mapfile", "readarray"}:
        return any(str(part or "").strip("'\"") == variable for part in values[1:])
    if token == "printf" and "-v" in values:
        index = values.index("-v")
        return index + 1 < len(values) and str(values[index + 1] or "").strip("'\"") == variable
    assignment_tokens = values
    if token in {"export", "declare", "typeset", "local", "readonly"}:
        assignment_tokens = [part for part in values[1:] if not str(part or "").startswith("-")]
    if len(assignment_tokens) != 1:
        return False
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)", str(assignment_tokens[0] or ""))
    if not match or match.group(1) != variable:
        return False
    if match.group(2) == "+=":
        return True
    value = match.group(3).strip("'\"")
    return empty_assignment_invalidates or bool(value)


def _selected_marker_segments(segments: Iterable[object]) -> list[str]:
    return [
        str(segment or "")
        for segment in segments
        if "selected" in str(segment or "").casefold() or "chosen" in str(segment or "").casefold()
    ]


def _segment_prints_selected_archive_variable(segment: object, variable: str) -> bool:
    segment_text = str(segment or "")
    if "selected" not in segment_text.casefold() and "chosen" not in segment_text.casefold():
        return False
    if "$(" in segment_text or "`" in segment_text or "<(" in segment_text:
        return False
    if ">" in segment_text or "|" in segment_text or _shell_text_has_unquoted_background_operator(segment_text):
        return False
    if any(_authoritative_source_archive_url(url) for url in _extract_urls(segment_text)):
        return False
    try:
        parts = shlex.split(segment_text)
    except ValueError:
        parts = segment_text.split()
    token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    if token not in {"printf", "echo"}:
        return False
    if token == "printf" and "-v" in parts:
        return False
    return _parts_referenced_variables(parts) == {variable}


def _parts_referenced_variables(parts: Iterable[object]) -> set[str]:
    variables: set[str] = set()
    for part in parts:
        token = str(part or "")
        for match in re.finditer(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", token):
            variables.add(match.group(1))
    return variables


def _parts_reference_variable(parts: Iterable[object], variable: str) -> bool:
    refs = {f"${variable}", f"${{{variable}}}"}
    return any(str(part or "").strip("'\"") in refs for part in parts)


def _source_authority_satisfied_by_correlated_archive_readback(evidences: Iterable[CommandEvidence]) -> bool:
    authoritative_paths: set[str] = set()
    absent_archive_paths: set[str] = set()
    fabricated_source_url_paths: set[str] = set()
    for evidence in sorted(
        [item for item in evidences or [] if isinstance(item, CommandEvidence)],
        key=lambda item: item.finish_order,
    ):
        if not _source_authority_contract_allows_acceptance(evidence):
            continue
        output_text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
        for path in _authoritative_source_archive_paths(evidence.command):
            if _authoritative_archive_acquisition_completed(
                evidence,
                path,
            ) or _authoritative_archive_acquisition_structurally_completed(
                evidence,
                path,
                output_text,
                archive_previously_absent=path in absent_archive_paths,
            ):
                authoritative_paths.add(path)
        readback_paths = _saved_source_archive_identity_readback_paths(evidence, output_text)
        if _source_archive_readback_matches_authoritative_path(authoritative_paths, readback_paths, evidence.command):
            return True
        if _saved_source_url_archive_readback_signal(
            evidence,
            output_text,
            fabricated_source_url_paths=fabricated_source_url_paths,
        ):
            return True
        fabricated_source_url_paths.update(_fabricated_source_url_file_paths(evidence))
        absent_archive_paths.update(_source_archive_absence_paths(evidence.command, output_text))
    return False


def _fabricated_source_url_file_paths(evidence: CommandEvidence) -> set[str]:
    command = str(evidence.command or "")
    if _source_authority_signal(evidence):
        return set()
    paths: set[str] = set()
    redirect_re = r"(?:&>>|&>\|?|(?:\d*)?(?:>\||>>|>))"
    if re.search(r"source_url\b", command, re.I):
        paths.update(_mentioned_source_url_file_paths(command))
        if re.search(r"(?:write_text|\.write\s*\(|\bopen\s*\(|\bPath\s*\()", command):
            paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
    for match in re.finditer(rf"{redirect_re}\s*>\(([^)]*)\)", command, re.I):
        process_body = str(match.group(1) or "")
        process_paths = {
            item.strip("'\"")
            for item in re.findall(r"(\S*source[-_]url\S*)", process_body, re.I)
            if item.strip("'\"")
        }
        if process_paths:
            paths.update(process_paths)
        elif "$" in process_body:
            paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
    for match in re.finditer(rf"{redirect_re}\s*(['\"]?)(\S+)\1", command, re.I):
        target = str(match.group(2) or "").strip("'\"")
        if re.search(r"source[-_]url", target, re.I):
            paths.add(target)
    assignments: dict[str, str] = {}
    for segment in _ordered_shell_command_segments(_strip_heredoc_bodies(command)):
        for match in re.finditer(rf"{redirect_re}\s*(['\"]?)(\S+)\1", str(segment or ""), re.I):
            target = _resolve_shell_token(match.group(2), assignments)
            if re.search(r"source[-_]url", target, re.I):
                paths.add(target.strip("'\""))
            elif "$" in str(target or ""):
                paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        values = _resolve_shell_parts(_drop_shell_control_prefix(parts), assignments)
        if not values:
            _apply_top_level_shell_assignment_segment(assignments, segment)
            continue
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        if token == "tee":
            for value in values[1:]:
                if value.startswith("-"):
                    continue
                if re.search(r"source[-_]url", value, re.I):
                    paths.add(value)
                elif "$" in str(value or ""):
                    paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
        if token in {"cp", "install", "mv"}:
            destination = _file_materialization_destination_arg(values)
            if re.search(r"source[-_]url", destination, re.I):
                paths.add(destination)
            elif "$" in str(destination or ""):
                paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
        if token == "dd":
            destination = _dd_output_destination_arg(values, assignments)
            if re.search(r"source[-_]url", destination, re.I):
                paths.add(destination)
            elif "$" in str(destination or ""):
                paths.add(_DYNAMIC_SOURCE_URL_WRITER_PATH)
        _apply_top_level_shell_assignment_segment(assignments, segment)
    return paths


def _mentioned_source_url_file_paths(command: object) -> set[str]:
    text = str(command or "")
    paths: set[str] = set()
    for match in re.finditer(r"['\"]([^'\"]*source[-_]url[^'\"]*)['\"]", text, re.I):
        candidate = match.group(1).strip("'\"")
        if "/" in candidate or candidate.startswith("$"):
            paths.add(candidate.rstrip("),;"))
    for match in re.finditer(r"(?:^|\s)(\S*source[-_]url\S*)", text, re.I):
        candidate = match.group(1).strip("'\"")
        if "/" in candidate or candidate.startswith("$"):
            paths.add(candidate.rstrip("),;"))
    return paths


def _dd_output_destination_arg(parts: Iterable[object], assignments: Mapping[str, str]) -> str:
    values = [str(part or "").strip("'\"") for part in parts]
    for index, value in enumerate(values[1:], start=1):
        if value.startswith("of="):
            return _resolve_shell_token(value[3:], assignments).strip("'\"")
        if value == "of" and index + 1 < len(values):
            return _resolve_shell_token(values[index + 1], assignments).strip("'\"")
    return ""


def _file_materialization_destination_arg(parts: Iterable[object]) -> str:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return ""
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    operands: list[str] = []
    skip_next = False
    option_takes_value = {
        "cp": {"-t", "--target-directory", "-T", "--no-target-directory"},
        "install": {"-m", "--mode", "-o", "--owner", "-g", "--group", "-t", "--target-directory"},
        "mv": {"-t", "--target-directory", "-T", "--no-target-directory"},
    }
    for value in values[1:]:
        if skip_next:
            skip_next = False
            continue
        if value == "--":
            operands.extend(item for item in values[values.index(value) + 1 :] if item)
            break
        if value.startswith("--") and "=" in value:
            continue
        if value.startswith("-"):
            if value in option_takes_value.get(token, set()):
                skip_next = True
            continue
        operands.append(value)
    if not operands:
        return ""
    if "-t" in values or "--target-directory" in values:
        for index, value in enumerate(values):
            if value in {"-t", "--target-directory"} and index + 1 < len(values):
                return str(values[index + 1] or "").strip("'\"")
    return operands[-1]


def _source_archive_readback_matches_authoritative_path(
    authoritative_paths: Iterable[object],
    readback_paths: Iterable[object],
    readback_command: object,
) -> bool:
    for authoritative_path in authoritative_paths or []:
        authoritative_text = str(authoritative_path or "").strip("'\"")
        if not authoritative_text:
            continue
        for readback_path in readback_paths or []:
            readback_text = str(readback_path or "").strip("'\"")
            if not readback_text:
                continue
            if authoritative_text == readback_text:
                return True
            if Path(readback_text).is_absolute():
                continue
            if Path(readback_text).name != Path(authoritative_text).name:
                continue
            if _relative_source_archive_readback_runs_from_archive_parent(
                readback_command,
                readback_text,
                authoritative_text,
            ):
                return True
    return False


def _relative_source_archive_readback_runs_from_archive_parent(
    command: object,
    readback_path: object,
    archive_path: object,
) -> bool:
    readback_text = str(readback_path or "").strip("'\"")
    if not readback_text or Path(readback_text).is_absolute():
        return False
    if not _safe_relative_source_archive_readback_path(readback_text):
        return False
    archive_text = str(archive_path or "").strip("'\"")
    parent = _normalized_absolute_shell_path(str(Path(archive_text).parent))
    if not parent:
        return False
    command_text = _strip_heredoc_bodies(command)
    current_cwd = ""
    hash_seen = False
    list_seen = False
    for span in split_unquoted_shell_command_segment_spans(command_text):
        parts = _segment_invoked_command_parts(span.get("text"))
        if not parts:
            continue
        token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        if token == "cd":
            next_cwd = _cwd_after_cd_segment(span, command_text, parts, current_cwd)
            current_cwd = next_cwd
            continue
        if _unmodeled_cwd_mutating_segment_token(parts):
            current_cwd = ""
            continue
        source_paths = _source_archive_paths(parts[1:])
        if readback_text not in source_paths:
            continue
        if current_cwd != parent:
            continue
        if not _source_archive_readback_segment_control_safe(span, command_text, {readback_text}):
            continue
        if token in {"sha256sum", "shasum", "sha512sum"}:
            hash_seen = True
        if token == "tar" and _tar_parts_use_mode(parts, "t"):
            list_seen = True
        if token == "unzip" and _unzip_parts_use_test_mode(parts):
            list_seen = True
    return hash_seen and list_seen


def _safe_relative_source_archive_readback_path(path: object) -> bool:
    text = str(path or "").strip("'\"")
    if not text or Path(text).is_absolute():
        return False
    parts = [part for part in text.split("/") if part and part != "."]
    return len(parts) == 1 and parts[0] not in {"..", "."}


def _unmodeled_cwd_mutating_segment_token(parts: Iterable[object]) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return False
    invoked = _long_dependency_invoked_command_token(values)
    token = Path(invoked).name.casefold() or str(invoked or "").casefold()
    if token in {"pushd", "popd", "eval", "source", "."}:
        return True
    if token not in {"builtin", "command"} or len(values) < 2:
        return False
    wrapped = Path(str(values[1] or "")).name.casefold()
    return wrapped in {"cd", "pushd", "popd"}


def _cwd_after_cd_segment(
    span: Mapping[str, object],
    command: object,
    parts: Iterable[object],
    current_cwd: object,
) -> str:
    if not _cd_segment_control_safe(span, command):
        return ""
    values = [str(part or "").strip("'\"") for part in parts]
    if len(values) != 2:
        return ""
    target = values[1]
    if not target or target in {"-", "~"} or "$" in target:
        return ""
    if Path(target).is_absolute():
        return _normalized_absolute_shell_path(target)
    base = str(current_cwd or "")
    if not base:
        return ""
    return _normalized_absolute_shell_path(posixpath.join(base, target))


def _cd_segment_control_safe(span: Mapping[str, object], command: object) -> bool:
    text = str(span.get("text") or "").strip()
    if not text or ">" in text:
        return False
    if _shell_text_has_unquoted_background_operator(text):
        return False
    before = str(span.get("before_operator") or "")
    after = str(span.get("after_operator") or "")
    if before in {"&&", "||", "|"} or after in {"||", "|"}:
        return False
    if _span_is_inside_stdout_redirected_compound_command(span, command):
        return False
    if _span_is_inside_if_body(span, command) or _span_is_inside_shell_loop_body(span, command):
        return False
    return not re.match(r"^(?:if|while|until|for)\b|^!", text, re.I)


def _normalized_absolute_shell_path(path: object) -> str:
    text = str(path or "").strip("'\"")
    if not text or "$" in text or not Path(text).is_absolute():
        return ""
    return posixpath.normpath(text)


def _authoritative_archive_acquisition_completed(evidence: CommandEvidence, archive_path: object) -> bool:
    if command_evidence_terminal_acceptance_success(evidence):
        return True
    output_text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    if _source_acquisition_generated_hash_output_signal(evidence.command, output_text, archive_path):
        return True
    return _output_contains_post_source_archive_extract_marker(evidence.command, output_text, archive_path)


def _authoritative_archive_acquisition_structurally_completed(
    evidence: CommandEvidence,
    archive_path: object,
    output_text: object,
    *,
    archive_previously_absent: bool = False,
) -> bool:
    if evidence.timed_out or _source_acquisition_failed_output_signal(output_text):
        return False
    archive_text = str(archive_path or "").strip("'\"")
    if not archive_text:
        return False
    if not _command_validates_and_extracts_archive_path(evidence.command, archive_text):
        return False
    if not (archive_previously_absent or _command_removes_archive_path_before_fetch(evidence.command, archive_text)):
        return False
    return bool(_authoritative_source_archive_paths(evidence.command) & {archive_text})


def _source_archive_absence_paths(command: object, output_text: object) -> set[str]:
    text = str(output_text or "")
    paths = _source_archive_paths(_shell_words(command))
    paths.update(_source_archive_paths(_shell_words(text)))
    return {path for path in paths if _source_archive_absence_output_for_path(text, path)}


def _source_archive_absence_output_for_path(output_text: object, archive_path: object) -> bool:
    path = str(archive_path or "").strip("'\"")
    if not path:
        return False
    escaped = re.escape(path)
    return bool(
        re.search(rf"(?:cannot access|cannot stat|stat(?:x)?:).*['\"]?{escaped}['\"]?: No such file", str(output_text or ""), re.I)
        or re.search(rf"No such file or directory[^\n]*['\"]?{escaped}['\"]?", str(output_text or ""), re.I)
    )


def _command_removes_archive_path_before_fetch(command: object, archive_path: object) -> bool:
    command_text = _strip_heredoc_bodies(command)
    assignments = _simple_shell_assignments(command_text)
    archive_text = str(archive_path or "").strip("'\"")
    for segment in _ordered_shell_command_segments(command_text):
        parts = _resolve_shell_parts(_segment_invoked_command_parts(segment), assignments)
        if _parts_fetch_archive_path(parts, archive_text) or _parts_fetch_source_archive_temp_path(parts, archive_text):
            return False
        if _parts_remove_path(parts, archive_text):
            return True
    return False


def _output_contains_post_source_archive_extract_marker(
    command: object, output_text: object, archive_path: object
) -> bool:
    if _source_acquisition_failed_output_signal(output_text):
        return False
    markers = _post_source_archive_extract_markers(command, archive_path)
    if not markers:
        return False
    text = str(output_text or "")
    return any(marker and marker in text for marker in markers)


def _post_source_archive_extract_markers(command: object, archive_path: object) -> set[str]:
    command_text = _strip_heredoc_bodies(command)
    assignments = _simple_shell_assignments(command_text)
    pre_extract_markers: set[str] = set()
    markers: set[str] = set()
    after_extract = False
    for line in command_text.splitlines():
        if not after_extract and _line_extracts_archive_path_with_assignments(line, archive_path, assignments):
            after_extract = True
            continue
        marker = _explicit_progress_marker_from_line(line)
        if not after_extract:
            if marker:
                pre_extract_markers.add(marker)
            continue
        if marker:
            markers.add(marker)
    return markers - pre_extract_markers


def _line_extracts_archive_path_with_assignments(
    line: object, archive_path: object, assignments: Mapping[str, str]
) -> bool:
    archive_text = str(archive_path or "").strip("'\"")
    if not archive_text:
        return False
    for parts in _line_invoked_command_parts(line):
        if _parts_extract_archive_path(_resolve_shell_parts(parts, assignments), archive_text):
            return True
    return False


def _explicit_progress_marker_from_line(line: object) -> str:
    stripped = str(line or "").strip()
    match = re.search(r"\b(?:printf|echo)\s+['\"]([^'\"]{3,120})", stripped)
    if not match:
        return ""
    marker = match.group(1).replace("\\n", "").strip()
    if not re.search(r"(?:CONFIGURE|BUILD|SOURCE_TREE|DEPENDENCY|TARGET|VERSION|ARTIFACT|SMOKE)", marker, re.I):
        return ""
    return marker


def _authoritative_source_archive_paths(command: object) -> set[str]:
    return {
        path
        for path in _strict_authoritative_archive_fetch_paths(command)
        if _source_archive_pathish(path) and _versioned_source_archive_path(path)
    }


def _versioned_source_archive_path(path: object) -> bool:
    name = Path(str(path or "").strip("'\"")).name
    return bool(re.search(r"(?:^|[-_./])v?\d+(?:\.\d+)+", name, re.I))


def _source_archive_hash_output_for_path(output_text: object, path: object) -> bool:
    expected = str(path or "").strip("'\"")
    if not expected:
        return False
    for line in str(output_text or "").splitlines():
        stripped = line.strip()
        if _ARCHIVE_HASH_OUTPUT_RE.match(stripped):
            return True
        match = re.match(r"^[0-9a-f]{32,128}\s+(.+)$", stripped, re.I)
        if match and _same_archive_output_path(match.group(1), expected):
            return True
    return False


def _archive_listing_output_signal(output_text: object) -> bool:
    return _archive_root_listing_output_signal(output_text) or bool(_ARCHIVE_MEMBER_OUTPUT_RE.search(str(output_text or "")))


def _saved_authority_readback_output_signal(output_text: object) -> bool:
    value = str(output_text or "")
    return bool(
        _SOURCE_AUTHORITY_RE.search(value)
        or _DIRECT_SOURCE_AUTHORITY_OUTPUT_RE.search(value)
        or re.search(r"^\s*\"ref\":\s*\"refs/tags/[^\"/]+\"", value, re.I | re.M)
        or re.search(r"^\s*\"url\":\s*\"https?://[^\"]+/(?:releases|archive|git/refs/tags|git/commits)/", value, re.I | re.M)
    )


def _archive_root_listing_output_signal(output_text: object) -> bool:
    value = str(output_text or "")
    return bool(
        _ARCHIVE_ROOT_OUTPUT_RE.search(value)
        or re.search(r"^[A-Za-z0-9_.+-]+(?:-[A-Za-z0-9_.+-]+)?/\s*$", value, re.I | re.M)
    )


def _command_readbacks_source_archive_identity(command: object) -> bool:
    return bool(
        _command_hashes_source_archive_paths(command)
        & _command_lists_source_archive_paths(command)
    )


def _command_hashes_source_archive_paths(command: object) -> set[str]:
    paths: set[str] = set()
    command_text = _strip_heredoc_bodies(command)
    assignments = _simple_shell_assignments(command_text)
    for span in split_unquoted_shell_command_segment_spans(command_text):
        raw_values = [str(part or "").strip("'\"") for part in _segment_invoked_command_parts(span.get("text"))]
        values = _resolve_shell_parts(raw_values, assignments)
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        source_paths = _source_archive_paths(values[1:])
        if token in {"sha256sum", "shasum", "sha512sum"} and _source_archive_readback_segment_control_safe(
            span, command, source_paths
        ):
            paths.update(source_paths)
    return paths


def _command_lists_source_archive_paths(command: object) -> set[str]:
    paths: set[str] = set()
    command_text = _strip_heredoc_bodies(command)
    assignments = _simple_shell_assignments(command_text)
    for span in split_unquoted_shell_command_segment_spans(command_text):
        raw_values = [str(part or "").strip("'\"") for part in _segment_invoked_command_parts(span.get("text"))]
        values = _resolve_shell_parts(raw_values, assignments)
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        source_paths = _source_archive_paths(values[1:])
        if token == "tar" and _tar_parts_use_mode(values, "t") and _source_archive_readback_segment_control_safe(
            span, command, source_paths
        ):
            paths.update(source_paths)
        if (
            token == "unzip"
            and _unzip_parts_use_test_mode(values)
            and _source_archive_readback_segment_control_safe(span, command, source_paths)
        ):
            paths.update(source_paths)
    return paths


def _source_archive_readback_segment_control_safe(
    span: Mapping[str, object], command: object, source_paths: set[str]
) -> bool:
    text = str(span.get("text") or "").strip()
    if not text or not source_paths:
        return False
    if ">" in text:
        return False
    if _shell_text_has_unquoted_background_operator(text):
        return False
    before = str(span.get("before_operator") or "")
    after = str(span.get("after_operator") or "")
    if before in {"&&", "||"} or after in {"&&", "||"}:
        return False
    if before == "|":
        return False
    if after == "|":
        return False
    if _span_has_stdout_redirected_by_prior_exec(span, command):
        return False
    if _span_is_inside_stdout_redirected_compound_command(span, command):
        return False
    if _span_is_inside_if_body(span, command) or _span_is_inside_shell_loop_body(span, command):
        return False
    return not re.match(r"^(?:if|while|until)\b|^!", text, re.I)


def _span_has_stdout_redirected_by_prior_exec(span: Mapping[str, object], command: object) -> bool:
    start = _coerce_int(span.get("start"), default=0) or 0
    stdout_redirected = False
    for prior_span in split_unquoted_shell_command_segment_spans(_strip_heredoc_bodies(command)):
        end = _coerce_int(prior_span.get("end"), default=0) or 0
        if end > start:
            break
        parts = _segment_invoked_command_parts(prior_span.get("text"))
        token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        if token != "exec":
            continue
        if _exec_segment_restores_stdout(parts):
            stdout_redirected = False
        if _exec_segment_redirects_stdout(parts):
            stdout_redirected = True
    return stdout_redirected


def _exec_segment_redirects_stdout(parts: Iterable[object]) -> bool:
    values = [str(part or "") for part in parts][1:]
    return any(
        value in {">", ">>", "1>", "1>>", "&>"}
        or re.match(r"^(?:1)?>{1,2}(?!&)", value)
        or re.match(r"^1<>", value)
        or re.match(r"^&>", value)
        for value in values
    )


def _exec_segment_restores_stdout(parts: Iterable[object]) -> bool:
    values = [str(part or "") for part in parts][1:]
    return any(re.match(r"^(?:1)?>&[0-9-]+$", value) for value in values)


def _span_is_inside_stdout_redirected_compound_command(span: Mapping[str, object], command: object) -> bool:
    command_text = _strip_heredoc_bodies(command)
    start = _coerce_int(span.get("start"), default=0) or 0
    end = _coerce_int(span.get("end"), default=start) or start
    return any(
        _span_is_inside_stdout_redirected_compound(command_text, start, end, opener, closer)
        for opener, closer in (("{", "}"), ("(", ")"))
    )


def _span_is_inside_stdout_redirected_compound(text: str, start: int, end: int, opener: str, closer: str) -> bool:
    opener_start = _last_shell_compound_opener(text[:start], opener)
    if opener_start < 0:
        return False
    if text[opener_start:start].rfind(closer) >= text[opener_start:start].rfind(opener):
        return False
    suffix = text[end:]
    close_match = re.search(rf"{re.escape(closer)}(?P<tail>[^\n;|]*)", suffix)
    if not close_match:
        return False
    return _shell_tail_redirects_stdout(close_match.group("tail"))


def _last_shell_compound_opener(text: str, opener: str) -> int:
    last = -1
    escaped = re.escape(opener)
    prefix = r"(?:time\s+(?:(?:-[A-Za-z]+|--[A-Za-z0-9_-]+)\s+)*)?"
    for match in re.finditer(rf"(?:^|[;&|\n])\s*{prefix}{escaped}(?:\s|$)", text):
        last = match.start()
    return last


def _shell_tail_redirects_stdout(tail: object) -> bool:
    value = str(tail or "")
    return bool(re.search(r"(?:^|\s)(?:1?>{1,2}(?!&)|&>|1<>)(?:\s|\S)", value))


def _span_is_inside_if_body(span: Mapping[str, object], command: object) -> bool:
    return bool(_if_body_prefix_for_span(span, command))


def _span_is_inside_shell_loop_body(span: Mapping[str, object], command: object) -> bool:
    command_text = _strip_heredoc_bodies(command)
    start = _coerce_int(span.get("start"), default=0) or 0
    prefix = command_text[:start]
    last_loop = _last_shell_control_start(prefix, ("for", "while", "until"))
    last_done = _last_shell_control_start(prefix, ("done",))
    return last_loop > last_done and re.search(r"\bdo\b", prefix[last_loop:], re.I) is not None


def _if_body_prefix_for_span(span: Mapping[str, object], command: object) -> str:
    command_text = _strip_heredoc_bodies(command)
    start = _coerce_int(span.get("start"), default=0) or 0
    prefix = command_text[:start]
    last_if = _last_shell_control_start(prefix, ("if",))
    last_fi = _last_shell_control_start(prefix, ("fi",))
    if last_if <= last_fi:
        return ""
    candidate = prefix[last_if:]
    return candidate if re.search(r"\bthen\b", candidate, re.I) else ""


def _last_shell_control_start(text: object, words: Iterable[str]) -> int:
    last = -1
    pattern = "|".join(re.escape(word) for word in words)
    for match in re.finditer(rf"(?:^|[;&|\n])\s*(?:{pattern})\b", str(text or ""), re.I):
        last = match.start()
    return last


def _source_archive_paths(values: Iterable[object]) -> set[str]:
    return {str(value or "").strip("'\"),;:") for value in values if _source_archive_pathish(value)}


def _shell_words(value: object) -> list[str]:
    try:
        return shlex.split(str(value or ""))
    except ValueError:
        return str(value or "").split()


def _source_archive_pathish(value: object) -> bool:
    text = str(value or "").strip("'\"),;:")
    return bool(re.search(r"\.(?:tar\.gz|tgz|zip|tar|tar\.xz|tar\.bz2)(?:$|[?#])", text, re.I))


def _validated_source_archive_acquisition_signal(evidence: CommandEvidence) -> bool:
    command = str(evidence.command or "")
    archive_paths = _validated_source_archive_acquisition_paths(command)
    if not archive_paths:
        return False
    text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    if _source_acquisition_failed_output_signal(text):
        return False
    if not command_evidence_terminal_acceptance_success(evidence):
        if not any(_source_acquisition_generated_hash_output_signal(command, text, archive_path) for archive_path in archive_paths):
            return False
    return not _BUILD_FAILURE_RE.search(text) or _source_acquisition_completed_output_signal(text)


def _source_acquisition_completed_output_signal(text: object) -> bool:
    value = str(text or "")
    return bool(
        _ARCHIVE_HASH_OUTPUT_RE.search(value)
        or re.search(r"^archive_sha256=\S+", value, re.I | re.M)
        or re.search(r"^[0-9a-f]{32,128}\s+\S+\.(?:tar\.gz|tgz|zip|tar|tar\.xz|tar\.bz2)\b", value, re.I | re.M)
    )


def _source_acquisition_failed_output_signal(text: object) -> bool:
    return bool(
        re.search(r"\b(?:curl|wget):\s*(?:\(\d+\)|error|failed)", str(text or ""), re.I)
        or re.search(r"\btar:\s+.*(?:error|failed|cannot|not found|no such file)", str(text or ""), re.I)
        or re.search(r"\bunzip:\s+.*(?:error|failed|cannot|not found|no such file)", str(text or ""), re.I)
    )


def _source_acquisition_generated_hash_output_signal(command: object, output_text: object, archive_path: object) -> bool:
    command_text = str(command or "")
    if not _command_hashes_archive_path(command_text, str(archive_path or "")):
        return False
    for line in str(output_text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped in command_text:
            continue
        if not _command_has_ordered_source_archive_completion(command_text, archive_path, stripped):
            continue
        if _pre_fetch_output_may_emit_source_hash(command_text, archive_path, stripped):
            continue
        if _ARCHIVE_HASH_OUTPUT_RE.match(stripped):
            return True
        match = re.match(r"^[0-9a-f]{32,128}\s+(\S+)", stripped, re.I)
        if match and _same_archive_output_path(match.group(1), archive_path):
            return True
    return False


def _same_archive_output_path(observed: object, expected: object) -> bool:
    observed_text = str(observed or "").strip("'\"")
    expected_text = str(expected or "").strip("'\"")
    if not observed_text or not expected_text:
        return False
    return observed_text == expected_text or Path(observed_text).name == Path(expected_text).name


def _command_has_ordered_source_archive_completion(command: object, archive_path: object, output_line: object) -> bool:
    fetched = False
    pending_temp_fetch_path = ""
    hashed = False
    validated = False
    extracted = False
    archive_text = str(archive_path or "").strip("'\"")
    command_text = _strip_heredoc_bodies(command)
    assignments = _simple_shell_assignments(command_text)
    for segment in _ordered_shell_command_segments(command_text):
        parts = _resolve_shell_parts(_segment_invoked_command_parts(segment), assignments)
        if not parts:
            continue
        if not fetched:
            if _parts_fetch_archive_path(parts, archive_text):
                fetched = True
                continue
            temp_path = _parts_fetch_source_archive_temp_path(parts, archive_text)
            if temp_path:
                pending_temp_fetch_path = temp_path
                continue
            if pending_temp_fetch_path and _parts_move_path_to_archive_path(parts, pending_temp_fetch_path, archive_text):
                fetched = True
                pending_temp_fetch_path = ""
                continue
            if not _parts_are_source_archive_setup_safe(parts, archive_text, output_line):
                return False
            continue
        if not hashed:
            if _parts_hash_archive_path(parts, archive_text):
                hashed = True
                continue
            if not _parts_are_source_archive_setup_safe(parts, archive_text, output_line):
                return False
            continue
        if not validated:
            if _parts_validate_archive_path(parts, archive_text) or _command_substitution_validates_archive_path(
                segment,
                archive_text,
                assignments=assignments,
            ):
                validated = True
                continue
            if not _parts_are_post_hash_source_archive_setup_safe(parts, archive_text, output_line):
                return False
            continue
        if not extracted:
            if _parts_extract_archive_path(parts, archive_text):
                extracted = True
                continue
            if not _parts_are_post_hash_source_archive_setup_safe(parts, archive_text, output_line):
                return False
            continue
        if _parts_move_extracted_source_root(parts):
            return True
        if not _parts_are_post_hash_source_archive_setup_safe(parts, archive_text, output_line):
            return False
    return False


def _parts_fetch_source_archive_temp_path(parts: Iterable[object], archive_path: object) -> str:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token not in {"curl", "wget"} or _curl_wget_uses_no_download_mode(values):
        return ""
    if not any(_authoritative_source_archive_url(url) for url in _parts_remote_source_fetch_urls(values)):
        return ""
    fetched_path = _curl_wget_output_path(values)
    if not fetched_path:
        return ""
    if _same_archive_output_path(fetched_path, archive_path):
        return ""
    return fetched_path


def _parts_move_path_to_archive_path(parts: Iterable[object], source_path: object, archive_path: object) -> bool:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token != "mv" or len(values) < 3:
        return False
    if str(values[1] or "").strip("'\"") != str(source_path or "").strip("'\""):
        return False
    return _same_archive_output_path(values[2], archive_path)


def _parts_move_path_to_source_archive_final(parts: Iterable[object], source_path: object) -> str:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token != "mv" or len(values) < 3:
        return ""
    if str(values[1] or "").strip("'\"") != str(source_path or "").strip("'\""):
        return ""
    target = str(values[2] or "").strip("'\"")
    return target if _versioned_source_archive_path(target) else ""


def _line_is_source_archive_setup_safe(line: object, archive_path: object, output_line: object) -> bool:
    for parts in _line_invoked_command_parts(line):
        if not _parts_are_source_archive_setup_safe(parts, archive_path, output_line):
            return False
    return True


def _parts_are_source_archive_setup_safe(parts: Iterable[object], archive_path: object, output_line: object) -> bool:
    if _parts_may_print_source_hash_line(parts, archive_path, output_line):
        return False
    return _parts_are_stdout_safe_before_archive_fetch(parts) or _parts_print_non_hash_source_status(parts)


def _parts_are_post_hash_source_archive_setup_safe(
    parts: Iterable[object], archive_path: object, output_line: object
) -> bool:
    if _parts_may_print_source_hash_line(parts, archive_path, output_line):
        return False
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return True
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if len(values) == 1 and token in {":", "do", "done", "else", "esac", "fi", "then", "true"}:
        return True
    return _parts_are_plain_assignments(values)


def _parts_are_plain_assignments(parts: Iterable[object]) -> bool:
    for part in parts:
        value = str(part or "")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", value):
            return False
        if any(marker in value for marker in {"$", "`", "<("}):
            return False
    return True


def _parts_print_non_hash_source_status(parts: Iterable[object]) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return True
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    return token in {"echo", "printf"} and "source_url" in " ".join(values[1:]).casefold()


def _pre_fetch_stdout_risk_before_archive_fetch(command: object, archive_path: object) -> bool:
    for line in str(command or "").splitlines():
        if _line_fetches_archive_path(line, archive_path):
            break
        if re.search(r"<<-?\s*['\"]?[A-Za-z_][A-Za-z0-9_]*['\"]?", line):
            return True
    for parts in _invoked_command_parts(command):
        if _parts_fetch_archive_path(parts, archive_path):
            return False
        if not _parts_are_stdout_safe_before_archive_fetch(parts):
            return True
    return False


def _parts_are_stdout_safe_before_archive_fetch(parts: Iterable[object]) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return True
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token in {
        ":",
        "[",
        "break",
        "case",
        "cd",
        "continue",
        "do",
        "done",
        "esac",
        "export",
        "fi",
        "for",
        "if",
        "mkdir",
        "rm",
        "set",
        "test",
        "then",
        "true",
        "umask",
        "unset",
        "until",
        "while",
    }:
        return True
    return all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", value) for value in values)


def _pre_fetch_output_may_emit_source_hash(command: object, archive_path: object, output_line: object) -> bool:
    if _pre_fetch_heredoc_may_emit_source_hash(command, archive_path, output_line):
        return True
    for parts in _invoked_command_parts(command):
        if _parts_fetch_archive_path(parts, archive_path):
            return False
        if _parts_may_print_source_hash_line(parts, archive_path, output_line):
            return True
    return False


def _pre_fetch_heredoc_may_emit_source_hash(command: object, archive_path: object, output_line: object) -> bool:
    lines = str(command or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if _line_fetches_archive_path(line, archive_path):
            break
        match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if not match:
            index += 1
            continue
        delimiter = match.group(1)
        body: list[str] = []
        index += 1
        while index < len(lines) and lines[index].strip() != delimiter:
            body.append(lines[index])
            index += 1
        if _text_may_emit_source_hash_line("\n".join(body), archive_path, output_line):
            return True
        index += 1
    return False


def _parts_may_print_source_hash_line(parts: Iterable[object], archive_path: object, output_line: object) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return False
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token not in {"awk", "cat", "echo", "perl", "printf", "ruby", "sed"} and not token.startswith("python"):
        return False
    line = str(output_line or "").strip()
    joined = " ".join(values[1:])
    return _text_may_emit_source_hash_line(joined, archive_path, line)


def _text_may_emit_source_hash_line(text: object, archive_path: object, output_line: object) -> bool:
    body = str(text or "")
    line = str(output_line or "").strip()
    dynamic_or_literal_hash = bool(
        re.search(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", body) or re.search(r"[0-9a-f]{32,128}", body, re.I)
    )
    if re.match(r"^archive_sha256=\S+", line, re.I):
        return "archive_sha256" in body.casefold() and dynamic_or_literal_hash
    match = re.match(r"^[0-9a-f]{32,128}\s+(\S+)", line, re.I)
    if not match:
        return False
    archive_text = str(archive_path or "").strip("'\"")
    output_path = str(match.group(1) or "").strip("'\"")
    path_referenced = any(
        candidate and candidate in body
        for candidate in {
            archive_text,
            output_path,
            Path(archive_text).name if archive_text else "",
            Path(output_path).name if output_path else "",
        }
    )
    return path_referenced and dynamic_or_literal_hash


def _line_fetches_archive_path(line: object, archive_path: object) -> bool:
    for parts in _line_invoked_command_parts(line):
        if _parts_fetch_archive_path(parts, archive_path):
            return True
    return False


def _line_hashes_archive_path(line: object, archive_path: object) -> bool:
    return _command_hashes_archive_path(line, str(archive_path or ""))


def _line_validates_archive_path(line: object, archive_path: object) -> bool:
    archive_text = str(archive_path or "").strip("'\"")
    if not archive_text:
        return False
    for parts in _line_invoked_command_parts(line):
        if _parts_validate_archive_path(parts, archive_text):
            return True
    return _command_substitution_validates_archive_path(line, archive_text)


def _line_extracts_archive_path(line: object, archive_path: object) -> bool:
    archive_text = str(archive_path or "").strip("'\"")
    if not archive_text:
        return False
    for parts in _line_invoked_command_parts(line):
        token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        if token == "tar" and _tar_parts_use_mode(parts, "x") and _parts_reference_path(parts, archive_text):
            return True
        if token == "unzip" and not _unzip_parts_use_test_mode(parts) and _parts_reference_path(parts, archive_text):
            return True
    return False


def _line_moves_extracted_source_root(line: object) -> bool:
    return _command_moves_extracted_source_root(line)


def _line_invoked_command_parts(line: object) -> list[list[str]]:
    parts_list: list[list[str]] = []
    for segment in split_unquoted_shell_command_segments(line):
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        parts = _drop_shell_control_prefix(parts)
        if parts:
            parts_list.append(parts)
    return parts_list


def _parts_fetch_archive_path(parts: Iterable[object], archive_path: object) -> bool:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token not in {"curl", "wget"} or _curl_wget_uses_no_download_mode(values):
        return False
    output_path = _curl_wget_output_path(values)
    return bool(output_path and _same_archive_output_path(output_path, archive_path))


def _command_has_validated_source_archive_acquisition(command: object) -> bool:
    return bool(_validated_source_archive_acquisition_paths(command))


def _validated_source_archive_acquisition_paths(command: object) -> set[str]:
    command_text = str(command or "")
    if not (_command_enables_errexit(command_text) and not _command_disables_errexit(command_text)):
        return set()
    if _command_masks_remote_source_fetch_failure(command_text):
        return set()
    if _command_uses_python_remote_source_acquisition_tool(command_text):
        return set()
    if _command_defines_shell_function(command_text):
        return set()
    validated_paths: set[str] = set()
    for archive_path in _strict_authoritative_archive_fetch_paths(command_text):
        if _command_validates_and_extracts_archive_path(command_text, archive_path):
            validated_paths.add(archive_path)
    return validated_paths


def _command_defines_shell_function(command: object) -> bool:
    command_text = _shell_logical_command_text(command)
    return bool(re.search(r"(?:^|[;&|\n])\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*(?:\(\s*\))?\s*\{", command_text))


def _strict_authoritative_archive_fetch_paths(command: object) -> set[str]:
    raw_command_text = str(command or "")
    command_text = _strip_heredoc_bodies(raw_command_text)
    if not (
        _command_enables_errexit(command_text)
        and not _command_disables_errexit(command_text)
        and not _command_disables_pipefail(command_text)
        and not _command_masks_remote_source_fetch_failure(command_text)
    ):
        return set()
    paths = set()
    pending_temp_paths: set[str] = set()
    assignments: dict[str, str] = {}
    for segment in _top_level_direct_fetch_segments(command_text):
        for path in _segment_authoritative_archive_fetch_paths(segment, assignments):
            if _source_archive_pathish(path) and _versioned_source_archive_path(path):
                paths.add(path)
            else:
                pending_temp_paths.add(path)
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        values = _resolve_shell_parts(_drop_shell_control_prefix(parts), assignments)
        for temp_path in list(pending_temp_paths):
            target = _parts_move_path_to_source_archive_final(values, temp_path)
            if target:
                paths.add(target)
                pending_temp_paths.remove(temp_path)
        _apply_top_level_shell_assignment_segment(assignments, segment)
    paths.update(_url_loop_authoritative_archive_fetch_paths(raw_command_text))
    return paths


def _url_loop_authoritative_archive_fetch_paths(command: object) -> set[str]:
    command_text = _shell_logical_command_text(_strip_heredoc_bodies(command))
    paths: set[str] = set()
    for variable, values, body in _top_level_for_loop_blocks(command_text):
        if not _candidate_values_allow_authoritative_source(values, body, variable):
            continue
        body_parts = _invoked_command_parts(body)
        for index, parts in enumerate(body_parts):
            token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
            if token not in {"curl", "wget"} or _curl_wget_uses_no_download_mode(parts):
                continue
            if not _parts_fetches_exact_loop_variable_source(parts, variable):
                continue
            if any(
                _parts_invalidates_selected_loop_variable(prior_parts, variable, empty_assignment_invalidates=True)
                for prior_parts in body_parts[:index]
            ):
                continue
            archive_path = _curl_wget_output_path(parts)
            if archive_path and _loop_body_proves_selected_archive(body_parts, index, archive_path, variable):
                paths.add(archive_path)
            elif archive_path and _loop_body_records_selected_archive_fetch(
                command_text, body_parts, index, archive_path, variable
            ):
                paths.add(archive_path)
    paths.update(_while_read_authoritative_archive_fetch_paths(command))
    return paths


def _while_read_authoritative_archive_fetch_paths(command: object) -> set[str]:
    command_text = str(command or "")
    logical_text = _shell_logical_command_text(_strip_heredoc_bodies(command_text))
    candidate_text_by_path = _heredoc_text_by_output_path(command_text)
    paths: set[str] = set()
    for variable, input_path, body, prefix in _top_level_while_read_blocks(logical_text):
        assignments = _top_level_shell_assignments_in_order(prefix)
        resolved_input = _resolve_shell_token(input_path, assignments)
        candidate_text = candidate_text_by_path.get(resolved_input, "")
        if not _first_candidate_url_is_authoritative(candidate_text):
            continue
        body_parts = _invoked_command_parts(body)
        resolved_body_parts = [_resolve_shell_parts(parts, assignments) for parts in body_parts]
        for index, parts in enumerate(resolved_body_parts):
            token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
            if token not in {"curl", "wget"} or _curl_wget_uses_no_download_mode(parts):
                continue
            if not _parts_fetches_exact_loop_variable_source(parts, variable):
                continue
            if any(
                _parts_invalidates_selected_loop_variable(prior_parts, variable, empty_assignment_invalidates=True)
                for prior_parts in body_parts[:index]
            ):
                continue
            archive_path = _curl_wget_output_path(parts)
            if archive_path and _loop_body_proves_selected_archive(resolved_body_parts, index, archive_path, variable):
                paths.add(archive_path)
            elif archive_path and _loop_body_records_selected_archive_fetch(
                logical_text, resolved_body_parts, index, archive_path, variable
            ):
                paths.add(archive_path)
    return paths


def _candidate_values_allow_authoritative_source(values: object, _body: object, _variable: str) -> bool:
    return _first_candidate_url_is_authoritative(values)


def _first_candidate_url_is_authoritative(candidate_text: object) -> bool:
    urls = _extract_urls_in_order(candidate_text)
    return bool(urls and _authoritative_source_archive_url(urls[0]))


def _top_level_while_read_blocks(command: object) -> list[tuple[str, str, str, str]]:
    lines = str(command or "").splitlines()
    blocks: list[tuple[str, str, str, str]] = []
    control_depth = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if control_depth == 0:
            match = re.match(
                r"^while\s+(?:IFS=\s*)?read\b(?:\s+-[A-Za-z]+)*\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:;\s*do|\s+do)\s*(.*)$",
                stripped,
                re.I,
            )
            if match:
                start_index = index
                variable = match.group(1)
                first_body = match.group(2).strip()
                body: list[str] = [first_body] if first_body else []
                index += 1
                input_path = ""
                while index < len(lines):
                    current = lines[index]
                    current_stripped = current.strip()
                    done_match = re.match(r"^done\s*<\s*(\S+)\s*$", current_stripped, re.I)
                    if done_match:
                        input_path = done_match.group(1).strip("'\"")
                        break
                    if re.fullmatch(r"done\b", current_stripped, re.I):
                        break
                    body.append(current)
                    index += 1
                if input_path:
                    blocks.append((variable, input_path, "\n".join(body), "\n".join(lines[:start_index])))
                index += 1
                continue
        control_depth = _update_shell_block_depth(stripped, control_depth)
        index += 1
    return blocks


def _heredoc_text_by_output_path(command: object) -> dict[str, str]:
    lines = str(command or "").splitlines()
    results: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        cat_match = re.search(
            r"\bcat\s*(>{1,2})\s*(\S+)\s*<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?",
            line,
        )
        tee_match = re.search(
            r"\btee\s+((?:-[A-Za-z]+\s+)*)?(\S+)\s*<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?",
            line,
        )
        if cat_match:
            append = cat_match.group(1) == ">>"
            output_path = cat_match.group(2).strip("'\"")
            delimiter = cat_match.group(3)
        elif tee_match:
            options = str(tee_match.group(1) or "")
            append = "-a" in options.split()
            output_path = tee_match.group(2).strip("'\"")
            delimiter = tee_match.group(3)
        else:
            index += 1
            continue
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != delimiter:
            body.append(lines[index])
            index += 1
        if body:
            body_text = "\n".join(body).strip()
            if append and output_path in results:
                results[output_path] = "\n".join([results[output_path], body_text]).strip()
            else:
                results[output_path] = body_text
        if index < len(lines):
            index += 1
    return results


def _simple_shell_assignments(command: object) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for segment in _ordered_shell_command_segments(_strip_heredoc_bodies(command)):
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        if len(parts) != 1:
            continue
        match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)=(.+)", parts[0])
        if not match:
            continue
        value = match.group(2).strip("'\"")
        if value and "$" not in value and "`" not in value and "<(" not in value:
                assignments[match.group(1)] = value
    return assignments


def _top_level_shell_assignments_in_order(command: object) -> dict[str, str]:
    assignments: dict[str, str] = {}
    for segment in _top_level_direct_fetch_segments(command):
        _apply_top_level_shell_assignment_segment(assignments, segment)
    return assignments


def _apply_top_level_shell_assignment_segment(assignments: dict[str, str], segment: object) -> None:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    values = _drop_shell_control_prefix(parts)
    values = _drop_shell_builtin_mutation_wrapper_prefix(values)
    if not values:
        return

    invoked = str(_long_dependency_invoked_command_token(values) or "")
    token = Path(invoked).name.casefold() or invoked.casefold()
    if token == "eval" or token == "source" or invoked == ".":
        assignments.clear()
        return
    if token == "unset":
        for part in values[1:]:
            name = str(part or "").strip("'\"")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                assignments.pop(name, None)
        return
    if token in {"read", "mapfile", "readarray"}:
        for part in values[1:]:
            name = str(part or "").strip("'\"")
            if name.startswith("-"):
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                assignments.pop(name, None)
        return
    if token == "printf" and "-v" in values:
        index = values.index("-v")
        if index + 1 < len(values):
            name = str(values[index + 1] or "").strip("'\"")
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                assignments.pop(name, None)
        return

    assignment_tokens = values
    if token in {"export", "declare", "typeset", "local", "readonly"}:
        assignment_tokens = [part for part in values[1:] if not str(part or "").startswith("-")]
    if len(assignment_tokens) != 1:
        return
    assignment = str(assignment_tokens[0] or "")
    match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)", assignment)
    if not match:
        return
    name, operator, raw_value = match.group(1), match.group(2), match.group(3)
    if operator == "+=":
        assignments.pop(name, None)
        return
    value = _resolve_shell_token(raw_value.strip("'\""), assignments)
    if value and "$" not in value and "`" not in value and "<(" not in value:
        assignments[name] = value
    else:
        assignments.pop(name, None)


def _drop_shell_builtin_mutation_wrapper_prefix(parts: Iterable[object]) -> list[str]:
    values = [str(part or "") for part in parts]
    while values:
        name = Path(values[0]).name.casefold()
        if name == "builtin":
            values = values[1:]
            continue
        if name == "command":
            values = values[1:]
            while values:
                option = str(values[0] or "")
                if option == "--":
                    values = values[1:]
                    break
                if option in {"-p", "-v", "-V"}:
                    values = values[1:]
                    continue
                break
            continue
        break
    return values


def _resolve_shell_token(value: object, assignments: Mapping[str, str]) -> str:
    token = str(value or "").strip("'\"")
    match = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", token)
    if match:
        return assignments.get(match.group(1), token)
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}(.+)", token)
    if match and match.group(1) in assignments and "$" not in match.group(2):
        return assignments[match.group(1)] + match.group(2)
    match = re.fullmatch(r"\$([A-Za-z_][A-Za-z0-9_]*)(.+)", token)
    if match and match.group(1) in assignments and "$" not in match.group(2):
        return assignments[match.group(1)] + match.group(2)
    return token


def _resolve_shell_parts(parts: Iterable[object], assignments: Mapping[str, str]) -> list[str]:
    return [_resolve_shell_token(part, assignments) for part in parts]


def _top_level_for_loop_blocks(command: object) -> list[tuple[str, str, str]]:
    lines = str(command or "").splitlines()
    blocks: list[tuple[str, str, str]] = []
    control_depth = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if control_depth == 0:
            match = re.match(r"^for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s+(.*)$", stripped, re.I)
            if match:
                variable = match.group(1)
                values_text = match.group(2)
                body: list[str] = []
                same_line_do = re.match(r"^(.*?)(?:;\s*do|\s+do)\s*(.*)$", values_text, re.I)
                if same_line_do:
                    values_parts = [same_line_do.group(1)]
                    first_body = same_line_do.group(2).strip()
                    if first_body:
                        body.append(first_body)
                    index += 1
                else:
                    values_parts = [values_text]
                    index += 1
                    while index < len(lines):
                        current = lines[index]
                        current_stripped = current.strip()
                        if re.fullmatch(r"do\b", current_stripped, re.I):
                            index += 1
                            break
                        if current_stripped.endswith(" do"):
                            values_parts.append(current_stripped[: -len(" do")])
                            index += 1
                            break
                        values_parts.append(current)
                        index += 1
                while index < len(lines) and not re.fullmatch(r"done\b", lines[index].strip(), re.I):
                    body.append(lines[index])
                    index += 1
                blocks.append((variable, "\n".join(values_parts), "\n".join(body)))
                index += 1
                continue
        control_depth = _update_shell_block_depth(stripped, control_depth)
        index += 1
    return blocks


def _top_level_direct_fetch_segments(command: object) -> list[str]:
    lines = str(command or "").splitlines()
    segments: list[str] = []
    control_depth = 0
    for line in lines:
        stripped = line.strip()
        if control_depth == 0 and not re.match(r"^(?:if|for|while|until|case|function)\b", stripped, re.I):
            segments.extend(split_unquoted_shell_command_segments(stripped))
        control_depth = _update_shell_block_depth(stripped, control_depth)
    return segments


def _update_if_depth(stripped_line: str, current: int) -> int:
    return _update_shell_block_depth(stripped_line, current)


def _update_shell_block_depth(stripped_line: str, current: int) -> int:
    line = stripped_line.strip()
    if not line or line.startswith("#"):
        return current
    for segment in split_unquoted_shell_command_segments(line):
        part = str(segment or "").strip()
        if not part or part.startswith("#"):
            continue
        if re.match(r"^(?:fi|done|esac)\b", part):
            current = max(0, current - 1)
        if re.match(r"^if\b", part):
            current += 1
        elif re.match(r"^(?:while|until|for)\b", part):
            current += 1
        elif re.match(r"^case\b", part):
            current += 1
    return current


def _segment_authoritative_archive_fetch_paths(
    segment: object,
    assignments: Mapping[str, str] | None = None,
) -> set[str]:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    parts = _resolve_shell_parts(_drop_shell_control_prefix(parts), assignments or {})
    token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    if token not in {"curl", "wget"}:
        return set()
    if _curl_wget_uses_no_download_mode(parts):
        return set()
    source_tokens = _curl_wget_effective_source_tokens(parts)
    if len(source_tokens) != 1 or not _authoritative_source_archive_url(source_tokens[0]):
        return set()
    archive_path = _curl_wget_output_path(parts)
    return {archive_path} if archive_path else set()


def _top_level_archive_move_target(
    command: object,
    source_path: object,
    assignments: Mapping[str, str] | None = None,
) -> str:
    source_text = str(source_path or "").strip("'\"")
    if not source_text:
        return ""
    for segment in _top_level_direct_fetch_segments(command):
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        values = _resolve_shell_parts(_drop_shell_control_prefix(parts), assignments or {})
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        if token != "mv" or len(values) < 3:
            continue
        if not _same_archive_output_path(values[1], source_text):
            continue
        target = str(values[2] or "").strip("'\"")
        if _source_archive_pathish(target):
            return target
    return ""


def _curl_wget_output_path(parts: Iterable[object]) -> str:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    if not values:
        return ""
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    option_flags = {"-o", "--output"} if token == "curl" else {"-O", "--output-document"}
    for index, part in enumerate(values[1:], start=1):
        if part in option_flags and index + 1 < len(values):
            return values[index + 1]
        for flag in option_flags:
            if part.startswith(f"{flag}="):
                return part.split("=", 1)[1]
    return ""


def _loop_body_proves_selected_archive(parts_list: list[list[str]], fetch_index: int, archive_path: str, variable: str) -> bool:
    if not any(_parts_remove_path(parts, archive_path) for parts in parts_list[: fetch_index + 1]):
        return False
    validation_index = None
    for index, parts in enumerate(parts_list[fetch_index + 1 :], start=fetch_index + 1):
        if _parts_validate_archive_path(parts, archive_path):
            validation_index = index
            break
    if validation_index is None:
        return False
    return any(_parts_assign_selected_url(parts, variable) for parts in parts_list[validation_index + 1 :])


def _loop_body_records_selected_archive_fetch(
    command_text: str,
    parts_list: list[list[str]],
    fetch_index: int,
    archive_path: str,
    variable: str,
) -> bool:
    if not (
        any(_parts_remove_path(parts, archive_path) for parts in parts_list[: fetch_index + 1])
        or _command_prepares_archive_output_path(command_text, archive_path)
    ):
        return False
    return any(_parts_assign_selected_url(parts, variable) for parts in parts_list[fetch_index + 1 :])


def _command_prepares_archive_output_path(command: object, archive_path: object) -> bool:
    path = str(archive_path or "").strip("'\"")
    if not path:
        return False
    cleaned_dirs: set[str] = set()
    for parts in _invoked_command_parts(command):
        values = [str(part or "").strip("'\"") for part in parts]
        if not values:
            continue
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        if token == "rm" and any(option in values[1:] for option in {"-r", "-rf", "-fr", "-R", "-Rf", "-fR"}):
            cleaned_dirs.update(value for value in values[1:] if value.startswith("/tmp/"))
        if token == "rm" and _parts_reference_path(values, path):
            return True
    if path.startswith("/"):
        return False
    for parts in _invoked_command_parts(command):
        values = [str(part or "").strip("'\"") for part in parts]
        token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
        if token == "cd" and len(values) > 1 and values[1] in cleaned_dirs:
            return True
    return False


def _parts_reference_loop_variable(parts: Iterable[object], variable: str) -> bool:
    refs = {f"${variable}", f"${{{variable}}}"}
    return any(str(part or "").strip("'\"") in refs for part in parts)


def _parts_fetches_exact_loop_variable_source(parts: Iterable[object], variable: str) -> bool:
    values = _drop_shell_control_prefix([str(part or "") for part in parts])
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token not in {"curl", "wget"} or _curl_wget_uses_no_download_mode(values):
        return False
    refs = {f"${variable}", f"${{{variable}}}"}
    source_tokens = _curl_wget_effective_source_tokens(values)
    return len(source_tokens) == 1 and source_tokens[0].strip("'\"") in refs


def _curl_wget_effective_source_tokens(parts: Iterable[object]) -> list[str]:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token not in {"curl", "wget"}:
        return []
    if _curl_wget_uses_external_config(values):
        return []
    option_value_flags = {
        "-o",
        "--output",
        "-O" if token == "wget" else "",
        "--output-document",
        "-H",
        "--header",
        "-e",
        "--referer",
        "-A",
        "--user-agent",
        "-d",
        "--data",
        "--data-binary",
        "--connect-timeout",
        "--max-time",
        "--retry",
        "--retry-delay",
        "--retry-max-time",
        "--speed-limit",
        "--speed-time",
        "--timeout",
        "--tries",
        "--url-query",
    }
    source_tokens: list[str] = []
    skip_next = False
    source_next = False
    for part in values[1:]:
        part_text = str(part or "")
        if skip_next:
            skip_next = False
            continue
        if source_next:
            stripped = part_text.strip("'\"")
            if stripped.startswith(("http://", "https://")) or re.fullmatch(
                r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", stripped
            ):
                source_tokens.append(stripped)
            elif _untrusted_dynamic_source_operand(stripped):
                source_tokens.append("__dynamic_source_operand__")
            else:
                source_tokens.append("__literal_source_operand__")
            source_next = False
            continue
        if part_text == "--url":
            source_next = True
            continue
        if part_text.startswith("--url="):
            stripped = part_text.split("=", 1)[1].strip("'\"")
            if stripped.startswith(("http://", "https://")) or re.fullmatch(
                r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", stripped
            ):
                source_tokens.append(stripped)
            elif _untrusted_dynamic_source_operand(stripped):
                source_tokens.append("__dynamic_source_operand__")
            else:
                source_tokens.append("__literal_source_operand__")
            continue
        if part_text in option_value_flags:
            skip_next = True
            continue
        if any(part_text.startswith(f"{flag}=") for flag in option_value_flags if flag):
            continue
        if part_text.startswith("-"):
            continue
        stripped = part_text.strip("'\"")
        if stripped.startswith(("http://", "https://")) or re.fullmatch(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?", stripped):
            source_tokens.append(stripped)
        elif _untrusted_dynamic_source_operand(stripped):
            source_tokens.append("__dynamic_source_operand__")
        else:
            source_tokens.append("__literal_source_operand__")
    return source_tokens


def _untrusted_dynamic_source_operand(value: object) -> bool:
    text = str(value or "")
    return bool(text.startswith("$") or "$(" in text or "`" in text or "<(" in text or ">(" in text)


def _parts_assign_selected_url(parts: Iterable[object], variable: str) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if len(values) != 1:
        return False
    return bool(
        re.fullmatch(
            rf"(?:found|got(?:_url)?|selected(?:_url)?|chosen(?:_url)?|source(?:_url)?)=\$\{{?{re.escape(variable)}\}}?",
            values[0],
            re.I,
        )
    )


def _parts_remove_path(parts: Iterable[object], path: object) -> bool:
    values = [str(part or "").strip("'\"") for part in parts]
    if not values:
        return False
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    force_flag = any(value == "--force" or (value.startswith("-") and "f" in value[1:]) for value in values[1:])
    return token == "rm" and force_flag and _parts_reference_path(values, path)


def _drop_shell_control_prefix(parts: Iterable[object]) -> list[str]:
    values = [str(part or "") for part in parts]
    while values and values[0] in {"if", "while", "until", "then", "do"}:
        values = values[1:]
    return values


def _command_validates_and_extracts_archive_path(command: object, archive_path: str) -> bool:
    assignments = _simple_shell_assignments(command)
    return (
        _command_validates_archive_path(command, archive_path, assignments=assignments)
        and _command_extracts_archive_path(command, archive_path, assignments=assignments)
        and (
            _command_moves_extracted_source_root(command)
            or _command_extracts_archive_to_source_root(command, archive_path, assignments=assignments)
        )
    )


def _command_hashes_archive_path(command: object, archive_path: str) -> bool:
    assignments = _simple_shell_assignments(command)
    for parts in _invoked_command_parts(command):
        if _parts_hash_archive_path(_resolve_shell_parts(parts, assignments), archive_path):
            return True
    return False


def _parts_hash_archive_path(parts: Iterable[object], archive_path: str) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    return bool(token in {"sha256sum", "shasum", "sha512sum"} and _parts_reference_path(values, archive_path))


def _command_validates_archive_path(
    command: object,
    archive_path: str,
    *,
    assignments: Mapping[str, str] | None = None,
) -> bool:
    assignments = assignments or _simple_shell_assignments(command)
    for parts in _invoked_command_parts(command):
        if _parts_validate_archive_path(_resolve_shell_parts(parts, assignments), archive_path):
            return True
    return _command_substitution_validates_archive_path(command, archive_path, assignments=assignments)


def _command_substitution_validates_archive_path(
    command: object,
    archive_path: str,
    *,
    assignments: Mapping[str, str] | None = None,
) -> bool:
    path_text = str(archive_path or "").strip("'\"")
    if not path_text:
        return False
    path_patterns = [rf"['\"]?{re.escape(path_text)}['\"]?"]
    for name, value in (assignments or {}).items():
        if _same_archive_output_path(value, path_text):
            path_patterns.append(rf"['\"]?\$\{{{re.escape(name)}\}}['\"]?")
            path_patterns.append(rf"['\"]?\${re.escape(name)}\b['\"]?")
    path = "(?:" + "|".join(path_patterns) + ")"
    command_text = _strip_heredoc_bodies(command)
    return bool(
        re.search(rf"\$\([^)]*\btar\b[^)]*-[A-Za-z]*t[A-Za-z]*[^)]*{path}(?:\s|[|)])", command_text)
        or re.search(rf"\$\([^)]*\bunzip\b[^)]*(?:-t|--test)[^)]*{path}(?:\s|[|)])", command_text)
    )


def _parts_validate_archive_path(parts: Iterable[object], archive_path: str) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token == "tar" and _tar_parts_use_mode(values, "t") and _parts_reference_path(values, archive_path):
        return True
    return bool(token == "unzip" and _unzip_parts_use_test_mode(values) and _parts_reference_path(values, archive_path))


def _command_extracts_archive_path(
    command: object,
    archive_path: str,
    *,
    assignments: Mapping[str, str] | None = None,
) -> bool:
    assignments = assignments or _simple_shell_assignments(command)
    for parts in _invoked_command_parts(command):
        if _parts_extract_archive_path(_resolve_shell_parts(parts, assignments), archive_path):
            return True
    return False


def _command_extracts_archive_to_source_root(
    command: object,
    archive_path: str,
    *,
    assignments: Mapping[str, str] | None = None,
) -> bool:
    assignments = assignments or _simple_shell_assignments(command)
    for parts in _invoked_command_parts(command):
        if _parts_extract_archive_to_source_root(_resolve_shell_parts(parts, assignments), archive_path):
            return True
    return False


def _parts_extract_archive_path(parts: Iterable[object], archive_path: str) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token == "tar" and _tar_parts_use_mode(values, "x") and _parts_reference_path(values, archive_path):
        return True
    return bool(token == "unzip" and not _unzip_parts_use_test_mode(values) and _parts_reference_path(values, archive_path))


def _parts_extract_archive_to_source_root(parts: Iterable[object], archive_path: str) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token != "tar":
        return False
    if not (_tar_parts_use_mode(values, "x") and _parts_reference_path(values, archive_path)):
        return False
    if not _tar_parts_strip_single_top_component(values):
        return False
    target_dir = _tar_extract_target_dir(values)
    return bool(target_dir and target_dir.startswith(("/tmp/", "/src/", "/work/", "/app/")))


def _tar_parts_strip_single_top_component(values: Iterable[object]) -> bool:
    parts = [str(part or "") for part in values]
    for index, value in enumerate(parts):
        if value in {"--strip-components", "--strip-components=1", "--strip=1"}:
            if value.endswith("=1"):
                return True
            return index + 1 < len(parts) and parts[index + 1] == "1"
        if re.fullmatch(r"--strip-components=['\"]?1['\"]?", value):
            return True
    return False


def _tar_extract_target_dir(values: Iterable[object]) -> str:
    parts = [str(part or "").strip("'\"") for part in values]
    for index, value in enumerate(parts):
        if value == "-C" and index + 1 < len(parts):
            return parts[index + 1]
        if value.startswith("--directory="):
            return value.split("=", 1)[1]
    return ""


def _command_moves_extracted_source_root(command: object) -> bool:
    for parts in _invoked_command_parts(command):
        if _parts_move_extracted_source_root(parts):
            return True
    return False


def _parts_move_extracted_source_root(parts: Iterable[object]) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token != "mv":
        return False
    args = values[1:]
    return bool(
        any(re.search(r"(?:root|\$root|\$\{root\}|top|\$top|\$\{top\}|extract)", part, re.I) for part in args)
        and any(part.startswith(("/tmp", "/src", "/work", "/app")) for part in args)
    )


def _invoked_command_parts(command: object) -> list[list[str]]:
    parts_list: list[list[str]] = []
    for segment in split_unquoted_shell_command_segments(_strip_heredoc_bodies(command)):
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        parts = _drop_shell_control_prefix(parts)
        if parts:
            parts_list.append(parts)
    return parts_list


def _segment_invoked_command_parts(segment: object) -> list[str]:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    return _drop_shell_control_prefix(parts)


def _ordered_shell_command_segments(command: object) -> list[str]:
    text = str(command or "")
    segments: list[str] = []
    start = 0
    index = 0
    in_single = False
    in_double = False
    command_sub_depth = 0
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            index += 1
            continue
        if not in_single and text[index : index + 2] == "$(":
            command_sub_depth += 1
            index += 2
            continue
        if not in_single and command_sub_depth and char == "(":
            command_sub_depth += 1
            index += 1
            continue
        if not in_single and command_sub_depth and char == ")":
            command_sub_depth = max(0, command_sub_depth - 1)
            index += 1
            continue
        if in_single or in_double or command_sub_depth:
            index += 1
            continue
        operator_len = 0
        if text[index : index + 2] in {"&&", "||"}:
            operator_len = 2
        elif char in {"\n", "\r", "|", ";"}:
            operator_len = 1
        if operator_len:
            segment = text[start:index].strip()
            if segment:
                segments.append(segment)
            index += operator_len
            start = index
            continue
        index += 1
    tail = text[start:].strip()
    if tail:
        segments.append(tail)
    return segments or [text]


def _strip_heredoc_bodies(command: object) -> str:
    lines = str(command or "").splitlines()
    stripped: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped.append(line)
        match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if not match:
            index += 1
            continue
        delimiter = match.group(1)
        index += 1
        while index < len(lines) and lines[index].strip() != delimiter:
            index += 1
        if index < len(lines):
            stripped.append(lines[index])
            index += 1
    return "\n".join(stripped)


def _tar_parts_use_mode(parts: Iterable[object], mode: str) -> bool:
    long_mode = "--list" if mode == "t" else "--extract"
    for part in [str(value or "") for value in parts][1:]:
        if part == long_mode:
            return True
        if part.startswith("-") and not part.startswith("--") and mode in part[1:]:
            return True
    return False


def _unzip_parts_use_test_mode(parts: Iterable[object]) -> bool:
    return any(str(part or "") in {"-t", "--test"} for part in list(parts)[1:])


def _parts_reference_path(parts: Iterable[object], path: object) -> bool:
    expected = str(path or "").strip("'\"")
    if not expected:
        return False
    return any(str(part or "").strip("'\"") == expected for part in parts)


def _extract_urls(text: object) -> set[str]:
    return set(_extract_urls_in_order(text))


def _extract_urls_in_order(text: object) -> list[str]:
    return [match.group(0).rstrip("'\"),;") for match in re.finditer(r"https?://[^\s'\"<>]+", str(text or ""))]


def _authoritative_source_archive_url(url: object) -> bool:
    value = str(url or "").rstrip("'\"),;").casefold()
    if not value.startswith(("http://", "https://")):
        return False
    archiveish = bool(re.search(r"\.(?:tar\.gz|tgz|zip|tar|tar\.xz|tar\.bz2)(?:$|[?#])", value))
    github_release_or_tag = bool(
        re.search(r"github\.com/[^/\s]+/[^/\s]+/(?:releases/download|archive/refs/tags)/", value)
    )
    github_api_archive = bool(
        re.search(r"api\.github\.com/repos/[^/\s]+/[^/\s]+/(?:tarball|zipball)(?:/|$)", value)
    )
    github_codeload_archive = bool(
        re.search(r"codeload\.github\.com/[^/\s]+/[^/\s]+/(?:tar\.gz|zip)(?:/|$)", value)
    )
    release_or_download_archive = archiveish and bool(
        re.search(r"/(?:release|releases|download|downloads|dist|archive|source|src)/", value)
    )
    return github_release_or_tag or github_api_archive or github_codeload_archive or release_or_download_archive


def _command_has_authority_page_readback(command: object) -> bool:
    command_text = _shell_logical_command_text(command)
    return bool(
        re.search(r"\bgrep\b[^\n;]*(?:release|download|version|v?[0-9]+(?:\.[0-9]+)+)[^\n;]*\.(?:html|txt|md)\b", command_text, re.I)
        or re.search(r"\bgrep\b[^\n;]*\.(?:html|txt|md)\b[^\n;]*(?:release|download|version|v?[0-9]+(?:\.[0-9]+)+)", command_text, re.I)
        or re.search(r"\bgrep\b[^\n;]*(?:\"ref\"|\"sha\"|\"url\"|refs/tags)[^\n;]*\.json\b", command_text, re.I)
        or re.search(r"\bgrep\b[^\n;]*\.json\b[^\n;]*(?:\"ref\"|\"sha\"|\"url\"|refs/tags)", command_text, re.I)
    )


def _command_has_assertion_only_source_authority_segment(command: object) -> bool:
    for segment in split_unquoted_shell_command_segments(command):
        segment_text = str(segment or "")
        if (
            (
                _SOURCE_AUTHORITY_RE.search(segment_text)
                or _PACKAGE_METADATA_OUTPUT_RE.search(segment_text)
                or _PACKAGE_METADATA_ASSERTION_RE.search(segment_text)
            )
            and not _segment_uses_source_acquisition_tool(segment)
        ):
            return True
    return False


def _command_uses_source_acquisition_tool(command: object) -> bool:
    return any(_segment_uses_source_acquisition_tool(segment) for segment in split_unquoted_shell_command_segments(command))


def _command_uses_direct_source_acquisition_tool(command: object) -> bool:
    return any(_segment_uses_direct_source_acquisition_tool(segment) for segment in split_unquoted_shell_command_segments(command))


def _command_uses_remote_source_acquisition_tool(command: object) -> bool:
    return _command_uses_non_python_remote_source_acquisition_tool(command) or _command_uses_python_remote_source_acquisition_tool(
        command
    )


def _command_uses_non_python_remote_source_acquisition_tool(command: object) -> bool:
    return any(_segment_uses_remote_source_acquisition_tool(segment) for segment in split_unquoted_shell_command_segments(command))


def _command_has_strict_non_python_remote_source_acquisition(command: object) -> bool:
    command_text = str(command or "")
    return bool(
        _command_uses_non_python_remote_source_acquisition_tool(command_text)
        and _command_enables_errexit(command_text)
        and not _command_disables_errexit(command_text)
        and not _command_disables_pipefail(command_text)
        and not _command_masks_remote_source_fetch_failure(command_text)
        and not _command_pipes_remote_source_fetch_without_pipefail(command_text)
    )


def _command_masks_remote_source_fetch_failure(command: object) -> bool:
    command_text = _shell_logical_command_text(command)
    return bool(
        re.search(r"\b(?:curl|wget)\b[^\n;]*https?://[^\n;]*(?:\|\||&&[^\n;]*|&(?!&)|;\s*(?:true|:)\b)", command_text)
        or re.search(r"\|\|\s*\b(?:curl|wget)\b[^\n;]*https?://", command_text)
        or re.search(r"&&\s*\b(?:curl|wget)\b[^\n;]*https?://", command_text)
        or re.search(r"\bgh\s+(?:release\s+download|repo\s+clone)\b[^\n;]*(?:\|\||&&[^\n;]*|&(?!&)|;\s*(?:true|:)\b)", command_text)
        or re.search(r"\|\|\s*\bgh\s+(?:release\s+download|repo\s+clone)\b", command_text)
        or re.search(r"&&\s*\bgh\s+(?:release\s+download|repo\s+clone)\b", command_text)
        or re.search(r"\bgit\s+(?:clone|fetch|ls-remote)\b[^\n;]*(?:\|\||&&[^\n;]*|&(?!&)|;\s*(?:true|:)\b)", command_text)
        or re.search(r"\|\|\s*\bgit\s+(?:clone|fetch|ls-remote)\b", command_text)
        or re.search(r"&&\s*\bgit\s+(?:clone|fetch|ls-remote)\b", command_text)
    )


def _command_masks_python_source_fetch_failure(command: object) -> bool:
    command_text = _shell_logical_command_text(command)
    return bool(
        re.search(r"(?:\|\||&&)\s*\bpython3?\b", command_text)
        or re.search(r"\bpython3?\b[\s\S]{0,4000}(?:\|\||&&)", command_text)
        or (not _command_enables_pipefail(command_text) and re.search(r"\bpython3?\b[\s\S]{0,4000}\|(?!\|)", command_text))
        or re.search(r"(?:^|[;&|\n])\s*(?:if|while|until)\b", command_text)
        or re.search(r"(?:^|[;&|\n])\s*!", command_text)
        or re.search(r"(?:^|[;&|\n])\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", command_text)
    )


def _command_enables_errexit(command: object) -> bool:
    return bool(re.match(r"^\s*set\s+-[A-Za-z]*e[A-Za-z]*\b", str(command or "")))


def _command_disables_errexit(command: object) -> bool:
    command_text = str(command or "")
    return bool(
        re.search(r"(?:^|[;&|\n])\s*set\s+\+[A-Za-z]*e[A-Za-z]*\b", command_text)
        or re.search(r"(?:^|[;&|\n])\s*set\s+\+o\s+errexit\b", command_text)
    )


def _command_disables_pipefail(command: object) -> bool:
    return bool(re.search(r"(?:^|[;&|\n])\s*set\s+\+o\s+pipefail\b", str(command or "")))


def _command_pipes_remote_source_fetch_without_pipefail(command: object) -> bool:
    command_text = _shell_logical_command_text(command)
    if _command_enables_pipefail(command_text):
        return False
    return bool(
        re.search(r"\b(?:curl|wget)\b[^\n;|]*https?://[^\n;|]*\|(?!\|)", command_text)
        or re.search(r"\bgh\s+(?:release\s+download|repo\s+clone)\b[^\n;|]*\|(?!\|)", command_text)
        or re.search(r"\bgit\s+(?:clone|fetch|ls-remote)\b[^\n;|]*\|(?!\|)", command_text)
    )


def _command_enables_pipefail(command: object) -> bool:
    first_line = str(command or "").splitlines()[0] if str(command or "").splitlines() else ""
    first_command = first_line.split("#", 1)[0]
    return bool(re.match(r"^\s*set\b(?=[^;\n]*(?:\s-o\s+pipefail\b|\s-[A-Za-z]*o[A-Za-z]*\s+pipefail\b))", first_command))


def _shell_logical_command_text(command: object) -> str:
    return re.sub(r"\\\s*\n\s*", " ", str(command or ""))


def _direct_source_authority_output_urls(output_text: str) -> set[str]:
    urls: set[str] = set()
    for match in re.finditer(
        r"^(?:upstream_(?:ref|ref_url)=|authority_(?:archive_)?url=|matched_authority_url=|url=)(https?://\S+)|^CHOSEN\s+(https?://\S+)",
        output_text,
        re.I | re.M,
    ):
        urls.add((match.group(1) or match.group(2)).rstrip("'\""))
    return urls


def _command_remote_source_urls(command: object) -> set[str]:
    urls: set[str] = set()
    for segment in split_unquoted_shell_command_segments(command):
        if _segment_uses_remote_source_acquisition_tool(segment):
            urls.update(_segment_remote_source_fetch_urls(segment))
    return {url.rstrip("'\"") for url in urls}


def _segment_remote_source_fetch_urls(segment: object) -> set[str]:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    return _parts_remote_source_fetch_urls(parts)


def _parts_remote_source_fetch_urls(parts: Iterable[object]) -> set[str]:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token in {"curl", "wget"}:
        if _curl_wget_uses_no_download_mode(values):
            return set()
        if _curl_wget_uses_external_config(values):
            return set()
        option_value_flags = {
            "-o",
            "--output",
            "-O" if token == "wget" else "",
            "--output-document",
            "-H",
            "--header",
            "-e",
            "--referer",
            "-A",
            "--user-agent",
            "-d",
            "--data",
            "--data-binary",
            "--url-query",
        }
        urls: set[str] = set()
        skip_next = False
        source_next = False
        for part in values[1:]:
            part_text = str(part or "")
            if skip_next:
                skip_next = False
                continue
            if source_next:
                if part_text.startswith(("http://", "https://")):
                    urls.add(part_text.rstrip("'\""))
                source_next = False
                continue
            if part_text == "--url":
                source_next = True
                continue
            if part_text.startswith("--url="):
                value = part_text.split("=", 1)[1]
                if value.startswith(("http://", "https://")):
                    urls.add(value.rstrip("'\""))
                continue
            if part_text in option_value_flags:
                skip_next = True
                continue
            if any(part_text.startswith(f"{flag}=") for flag in option_value_flags if flag):
                continue
            if part_text.startswith("-"):
                continue
            if part_text.startswith(("http://", "https://")):
                urls.add(part_text.rstrip("'\""))
        return urls
    if token == "git" and any(str(part or "").casefold() in {"clone", "fetch", "ls-remote"} for part in values[1:3]):
        return {
            str(part or "").rstrip("'\"")
            for part in values[1:]
            if str(part or "").startswith(("http://", "https://"))
        }
    return set()


def _curl_wget_uses_external_config(parts: Iterable[object]) -> bool:
    values = [str(part or "") for part in parts]
    token = Path(_long_dependency_invoked_command_token(values)).name.casefold()
    if token == "curl":
        for part in values[1:]:
            part_text = str(part or "")
            if part_text in {"-K", "--config"}:
                return True
            if part_text.startswith("--config="):
                return True
            if part_text.startswith("-K") and part_text != "-K":
                return True
    if token == "wget":
        for part in values[1:]:
            part_text = str(part or "")
            if part_text in {"-i", "--input-file"}:
                return True
            if part_text.startswith("--input-file="):
                return True
            if part_text.startswith("-i") and part_text != "-i":
                return True
    return False


def _python_remote_source_urls(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    urls: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _python_call_name(node.func) not in {
            "urllib.request.urlopen",
            "urllib.request.urlretrieve",
            "requests.get",
            "requests.head",
            "httpx.get",
            "httpx.head",
            "urlopen",
            "urlretrieve",
            "get",
            "head",
        }:
            continue
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and arg.value.startswith(("http://", "https://")):
                urls.add(arg.value.rstrip("'\""))
        for keyword in node.keywords:
            if keyword.arg in {None, "url"}:
                value = keyword.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.startswith(("http://", "https://")):
                    urls.add(value.value.rstrip("'\""))
    return urls


def _command_uses_python_remote_source_acquisition_tool(command: object) -> bool:
    return any(
        _python_remote_source_urls(code)
        or _python_code_has_remote_fetch_with_http_context(code)
        or _python_code_has_remote_source_call(code)
        for code in _python_command_bodies(command)
    )


def _python_command_bodies(command: object) -> list[str]:
    return [*_python_heredoc_bodies(command), *_python_inline_bodies(command)]


def _python_inline_bodies(command: object) -> list[str]:
    bodies: list[str] = []
    for segment in split_unquoted_shell_command_segments(command):
        try:
            parts = shlex.split(str(segment or ""))
        except ValueError:
            parts = str(segment or "").split()
        token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
        if not re.fullmatch(r"python(?:3(?:\.\d+)?)?", token):
            continue
        index = 1
        while index < len(parts):
            part = str(parts[index] or "")
            if part == "-c" and index + 1 < len(parts):
                bodies.append(str(parts[index + 1] or ""))
                break
            if part.startswith("-c") and len(part) > 2:
                bodies.append(part[2:])
                break
            index += 1
    return bodies


def _command_has_plain_python_heredoc_source(command: object) -> bool:
    for line in str(command or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.match(r"^set\b", stripped):
            continue
        return bool(re.match(r"^python(?:3(?:\.\d+)?)?\b[^\n|&;]*<<[^\n|&;]*$", stripped))
    return False


def _command_has_python_remote_source_call(command: object) -> bool:
    for code in _python_heredoc_bodies(command):
        if _python_code_has_remote_source_call(code):
            return True
    return False


def _python_heredoc_bodies(command: object) -> list[str]:
    bodies: list[str] = []
    lines = str(command or "").splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
        if not match or not re.search(r"\bpython(?:3(?:\.\d+)?)?\b", line):
            index += 1
            continue
        delimiter = match.group(1)
        index += 1
        body: list[str] = []
        while index < len(lines) and lines[index].strip() != delimiter:
            body.append(lines[index])
            index += 1
        bodies.append("\n".join(body))
        index += 1
    return bodies


def _python_code_has_remote_source_call(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    if _python_code_has_ambiguous_source_flow(tree):
        return False

    class RemoteSourceCallVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.found = False
            self.archive_success_after_remote = False
            self.http_vars: set[str] = set()
            self.http_list_vars: set[str] = set()
            self.request_vars: set[str] = set()

        def visit_If(self, node: ast.If) -> None:  # noqa: N802
            truth_value = _python_static_truth_value(node.test)
            if truth_value is False:
                for item in node.orelse:
                    self.visit(item)
                return
            if truth_value is True:
                for item in node.body:
                    self.visit(item)
                return
            for item in node.body:
                self.visit(item)
            for item in node.orelse:
                self.visit(item)

        def visit_Try(self, node: ast.Try) -> None:  # noqa: N802
            if self._try_body_has_remote_archive_success(node.body):
                self.found = True
                return
            for item in node.orelse:
                self.visit(item)
            for item in node.finalbody:
                self.visit(item)

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
            return

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
            return

        def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
            return

        def visit_Lambda(self, node: ast.Lambda) -> None:  # noqa: N802
            return

        def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
            target_names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if _python_expr_is_http_literal(node.value):
                self.http_vars.update(target_names)
            if _python_expr_is_http_literal_list(node.value):
                self.http_list_vars.update(target_names)
            if isinstance(node.value, ast.Call):
                if self._node_has_remote_fetch(node.value):
                    self.found = True
                    return
                if (
                    _python_call_name(node.value.func) == "urllib.request.Request"
                    and node.value.args
                    and self._expr_is_http_url(node.value.args[0])
                ):
                    self.request_vars.update(target_names)

        def visit_Expr(self, node: ast.Expr) -> None:  # noqa: N802
            if isinstance(node.value, ast.Call) and self._node_has_remote_fetch(node.value):
                self.found = True
                return
            if self.found and self._call_prints_archive_success(node.value):
                self.archive_success_after_remote = True

        def _call_prints_archive_success(self, node: ast.AST) -> bool:
            if not isinstance(node, ast.Call) or _python_call_name(node.func) != "print":
                return False
            output = " ".join(_python_static_text(arg) for arg in node.args)
            return "ARCHIVE" in output and "sha256" in output

        def visit_For(self, node: ast.For) -> None:  # noqa: N802
            if _python_iter_is_static_empty(node.iter):
                for item in node.orelse:
                    self.visit(item)
                return
            added: str | None = None
            if isinstance(node.target, ast.Name) and (
                _python_expr_is_http_literal_list(node.iter)
                or (isinstance(node.iter, ast.Name) and node.iter.id in self.http_list_vars)
                or (
                    isinstance(node.iter, ast.Name)
                    and node.iter.id in {"candidate", "candidates", "url", "urls"}
                    and bool(self.http_list_vars)
                )
            ):
                added = node.target.id
                self.http_vars.add(added)
            for item in node.body:
                self.visit(item)
            if added:
                self.http_vars.discard(added)
            for item in node.orelse:
                self.visit(item)

        def _expr_is_http_url(self, node: ast.AST) -> bool:
            if _python_expr_is_http_literal(node):
                return True
            if isinstance(node, ast.Name) and node.id in self.http_vars:
                return True
            if isinstance(node, ast.Name) and node.id in self.request_vars:
                return True
            if _python_call_name(getattr(node, "func", ast.Name(id="", ctx=ast.Load()))) == "urllib.request.Request":
                args = getattr(node, "args", [])
                return bool(args and self._expr_is_http_url(args[0]))
            return False

        def _try_body_has_remote_archive_success(self, body: list[ast.stmt]) -> bool:
            has_remote = False
            for statement in body:
                if self._statement_binds_http_request(statement):
                    continue
                if self._statement_has_remote_fetch(statement):
                    has_remote = True
                if has_remote and self._statement_has_archive_success_print(statement):
                    return True
            return False

        def _statement_binds_http_request(self, statement: ast.stmt) -> bool:
            if not isinstance(statement, ast.Assign) or not isinstance(statement.value, ast.Call):
                return False
            if _python_call_name(statement.value.func) != "urllib.request.Request":
                return False
            if not statement.value.args or not self._expr_is_http_url(statement.value.args[0]):
                return False
            self.request_vars.update(target.id for target in statement.targets if isinstance(target, ast.Name))
            return True

        def _statement_has_remote_fetch(self, statement: ast.stmt) -> bool:
            return any(self._node_has_remote_fetch(node) for node in _python_reachable_statement_nodes(statement))

        def _statement_has_archive_success_print(self, statement: ast.stmt) -> bool:
            for node in _python_reachable_statement_nodes(statement):
                if not isinstance(node, ast.Call) or _python_call_name(node.func) != "print":
                    continue
                output = " ".join(_python_static_text(arg) for arg in node.args)
                if "ARCHIVE" in output and "sha256" in output:
                    return True
            return False

        def _node_has_remote_fetch(self, node: ast.AST) -> bool:
            if not isinstance(node, ast.Call):
                return False
            return _python_call_name(node.func) in {
                "urllib.request.urlopen",
                "urllib.request.urlretrieve",
                "requests.get",
                "requests.head",
                "httpx.get",
                "httpx.head",
            } and any(self._expr_is_http_url(arg) for arg in node.args)

    visitor = RemoteSourceCallVisitor()
    visitor.visit(tree)
    return bool(visitor.found and visitor.archive_success_after_remote)


def _python_code_has_remote_fetch_with_http_context(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    remote_names = {
        "urllib.request.urlopen",
        "urllib.request.urlretrieve",
        "requests.get",
        "requests.head",
        "httpx.get",
        "httpx.head",
        "urlopen",
        "urlretrieve",
        "get",
        "head",
    }
    has_http_literal = any(
        isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(("http://", "https://"))
        for node in ast.walk(tree)
    )
    if not has_http_literal:
        return False
    return any(isinstance(node, ast.Call) and _python_call_name(node.func) in remote_names for node in ast.walk(tree))


def _python_code_has_ambiguous_source_flow(tree: ast.AST) -> bool:
    match_type = getattr(ast, "Match", None)
    ambiguous_types = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.Try,
        ast.Raise,
        ast.Assert,
        ast.BinOp,
        ast.With,
        ast.AsyncWith,
        ast.FunctionDef,
        ast.AsyncFunctionDef,
        ast.ClassDef,
        ast.Lambda,
        ast.BoolOp,
        ast.IfExp,
        ast.ListComp,
        ast.SetComp,
        ast.DictComp,
        ast.GeneratorExp,
    )
    return any(
        isinstance(node, ambiguous_types)
        or (match_type is not None and isinstance(node, match_type))
        or (
            isinstance(node, ast.Call)
            and (
                _python_call_name(node.func) not in {
                    "urllib.request.urlopen",
                    "urllib.request.urlretrieve",
                    "requests.get",
                    "requests.head",
                    "httpx.get",
                    "httpx.head",
                    "print",
                }
                or _python_call_name(node.func) in {"sys.exit", "os._exit", "exit", "quit"}
                or _python_call_name(node.func).endswith(".exit")
            )
        )
        or (
            isinstance(node, ast.ImportFrom)
            and node.module == "sys"
            and any(alias.name == "exit" for alias in node.names)
        )
        or (
            isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign))
            and any(
                _python_call_name(target)
                in {
                    "urllib.request.urlopen",
                    "urllib.request.urlretrieve",
                    "requests.get",
                    "requests.head",
                    "httpx.get",
                    "httpx.head",
                }
                for target in ([node.target] if isinstance(node, (ast.AnnAssign, ast.AugAssign)) else node.targets)
            )
        )
        for node in ast.walk(tree)
    )


def _python_expr_is_http_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(("http://", "https://"))


def _python_expr_is_http_literal_list(node: ast.AST) -> bool:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return False
    return any(_python_expr_is_http_literal(item) for item in node.elts)


def _python_reachable_statement_nodes(statement: ast.stmt) -> list[ast.AST]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return []
    if isinstance(statement, ast.If):
        truth_value = _python_static_truth_value(statement.test)
        if truth_value is False:
            return [node for item in statement.orelse for node in _python_reachable_statement_nodes(item)]
        if truth_value is True:
            return [node for item in statement.body for node in _python_reachable_statement_nodes(item)]
    if isinstance(statement, ast.For) and _python_iter_is_static_empty(statement.iter):
        return [node for item in statement.orelse for node in _python_reachable_statement_nodes(item)]
    if isinstance(statement, ast.Try):
        return []
    nodes: list[ast.AST] = []

    def visit(node: ast.AST) -> None:
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.Lambda,
                ast.BoolOp,
                ast.IfExp,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        ):
            return
        nodes.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(statement)
    return nodes


def _python_static_truth_value(node: ast.AST) -> bool | None:
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None:
            return False
        if isinstance(value, (bool, int, float, complex, str, bytes)):
            return bool(value)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return bool(node.elts)
    if isinstance(node, ast.Dict):
        return bool(node.keys)
    return None


def _python_iter_is_static_empty(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return not node.elts
    if isinstance(node, ast.Dict):
        return not node.keys
    if isinstance(node, ast.Constant) and isinstance(node.value, (str, bytes)):
        return not bool(node.value)
    return False


def _python_static_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_python_static_text(item) for item in node.values)
    return ""


def _python_call_name(node: ast.AST) -> str:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return ".".join(reversed(parts))


def _command_uses_package_metadata_tool(command: object) -> bool:
    return any(_segment_uses_package_metadata_tool(segment) for segment in split_unquoted_shell_command_segments(command))


def _segment_uses_source_acquisition_tool(segment: object) -> bool:
    return _segment_uses_direct_source_acquisition_tool(segment) or _segment_uses_package_metadata_tool(segment)


def _segment_uses_direct_source_acquisition_tool(segment: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    lowered_parts = [str(part or "").casefold() for part in parts]
    if token in {"curl", "wget", "tar", "unzip", "gh"}:
        return True
    if token == "git" and any(part in {"clone", "checkout", "fetch", "ls-remote"} for part in lowered_parts[1:3]):
        return True
    return False


def _segment_uses_remote_source_acquisition_tool(segment: object) -> bool:
    segment_text = str(segment or "")
    try:
        parts = shlex.split(segment_text)
    except ValueError:
        parts = segment_text.split()
    token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    lowered_parts = [str(part or "").casefold() for part in parts]
    has_url_arg = any(str(part or "").startswith(("http://", "https://")) for part in parts[1:])
    if token in {"curl", "wget"}:
        if _curl_wget_uses_no_download_mode(parts):
            return False
        return has_url_arg
    if token == "gh":
        return ("release" in lowered_parts[1:3] and "download" in lowered_parts[2:4]) or (
            "repo" in lowered_parts[1:3] and "clone" in lowered_parts[2:4]
        )
    if token == "git" and any(part in {"clone", "fetch", "ls-remote"} for part in lowered_parts[1:3]):
        return True
    return False


def _curl_wget_uses_no_download_mode(parts: list[str]) -> bool:
    arguments = [str(part or "") for part in parts[1:]]
    lowered = [part.casefold() for part in arguments]
    for index, part in enumerate(lowered):
        if re.match(r"^-[A-Za-z]*XHEAD\b", arguments[index]):
            return True
        if part in {"--head", "--spider"}:
            return True
        if part.startswith("--request=head") or part.startswith("--method=head"):
            return True
        if part in {"-x", "--request", "--method"} and index + 1 < len(lowered) and lowered[index + 1] == "head":
            return True
        if part.startswith("--range"):
            return True
        if arguments[index] == "-r" or arguments[index].startswith("-r"):
            return True
        if part in {"-h", "--header"} and index + 1 < len(lowered) and lowered[index + 1].lstrip().startswith("range:"):
            return True
        if part.startswith("--header=") and part.split("=", 1)[1].lstrip().startswith("range:"):
            return True
        if arguments[index].startswith("-H") and arguments[index][2:].lstrip().casefold().startswith("range:"):
            return True
        if part.startswith("-") and not part.startswith("--") and "i" in part[1:]:
            return True
    return False


def _segment_uses_package_metadata_tool(segment: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    token = Path(_long_dependency_invoked_command_token(parts)).name.casefold()
    lowered_parts = [str(part or "").casefold() for part in parts]
    segment_lower = str(segment or "").casefold()
    if token == "apt-cache" and "show" in lowered_parts[1:3]:
        return True
    if token == "apt" and "show" in lowered_parts[1:3]:
        return True
    if token == "pip" and any(part in {"index", "show"} for part in lowered_parts[1:3]):
        return True
    if token == "npm" and any(part in {"view", "info"} for part in lowered_parts[1:3]):
        return True
    return bool(re.search(r"\bpython3?\s+-m\s+pip\s+(?:index|show)\b", segment_lower))


def _reduce_stages(
    contract: Mapping[str, object],
    attempts: Iterable[Mapping[str, object]],
    artifacts: Iterable[Mapping[str, object]],
    blockers: Iterable[Mapping[str, object]],
    *,
    fresh_default_smoke: bool = False,
    source_authority_satisfied: bool | None = None,
) -> list[dict]:
    attempts = [dict(item) for item in attempts or []]
    blockers = [dict(item) for item in blockers or []]
    stages: list[dict] = []
    source_blocked = _has_source_blocker(blockers)
    source_satisfied = (
        bool(source_authority_satisfied)
        if source_authority_satisfied is not None
        else _source_authority_satisfied(attempts)
    )
    target_proven = all((item or {}).get("status") == "proven" for item in artifacts or [])
    stages.append(
        {
            "id": "source_authority",
            "required": bool((contract.get("source_policy") or {}).get("authority_required", True)),
            "status": "blocked" if source_blocked else ("satisfied" if source_satisfied else "unknown"),
        }
    )
    if any(str(item.get("stage") or "") == "configure" for item in attempts):
        stages.append(
            {
                "id": "configure",
                "required": False,
                "status": _stage_status(attempts, "configure"),
            }
        )
    if any(str(item.get("stage") or "") == "dependency_generation" for item in attempts):
        stages.append(
            {
                "id": "dependency_generation",
                "required": bool((contract.get("build_policy") or {}).get("dependency_generation_before_final_target")),
                "status": "satisfied"
                if target_proven or fresh_default_smoke
                else _stage_status(attempts, "dependency_generation"),
            }
        )
    stages.append(
        {
            "id": "target_built",
            "required": True,
            "status": "satisfied" if target_proven else ("blocked" if blockers else "unknown"),
        }
    )
    runtime_policy = contract.get("runtime_proof") if isinstance(contract.get("runtime_proof"), Mapping) else {}
    runtime_required = runtime_policy.get("required") == "required"
    if runtime_required:
        stages.append(
            {
                "id": "default_smoke",
                "required": True,
                "status": _runtime_stage_status(attempts, blockers, fresh_default_smoke=fresh_default_smoke),
            }
        )
    else:
        stages.append({"id": "default_smoke", "required": False, "status": "not_required"})
    return stages


def _active_strategy_blockers(
    blockers: Iterable[Mapping[str, object]],
    attempts: Iterable[Mapping[str, object]],
    artifacts: Iterable[Mapping[str, object]],
    contract: Mapping[str, object],
    *,
    evidence_by_tool_call_id: Mapping[object, int] | None = None,
    fresh_default_smoke: bool = False,
    source_authority_satisfied: bool | None = None,
) -> list[dict]:
    blockers = [dict(item) for item in blockers or [] if isinstance(item, Mapping)]
    if not blockers:
        return []
    attempts = [dict(item) for item in attempts or [] if isinstance(item, Mapping)]
    artifacts = [dict(item) for item in artifacts or [] if isinstance(item, Mapping)]
    source_required = bool((contract.get("source_policy") or {}).get("authority_required", True))
    source_satisfied = (
        bool(source_authority_satisfied)
        if source_authority_satisfied is not None
        else _source_authority_satisfied(attempts)
    )
    target_proven = bool(artifacts) and all(item.get("status") == "proven" for item in artifacts)
    runtime_policy = contract.get("runtime_proof") if isinstance(contract.get("runtime_proof"), Mapping) else {}
    runtime_required = runtime_policy.get("required") == "required"
    runtime_satisfied = (not runtime_required) or fresh_default_smoke
    target_runtime_satisfied = target_proven and runtime_satisfied
    final_contract_satisfied = target_proven and runtime_satisfied and ((not source_required) or source_satisfied)
    latest_diagnostic_failure = _latest_attempt_diagnostic_failure(attempts) or {}
    latest_diagnostic_failure_class = str(latest_diagnostic_failure.get("failure_class") or "")
    latest_diagnostic_evidence_id = latest_diagnostic_failure.get("evidence_id")
    evidence_by_tool_call_id = dict(evidence_by_tool_call_id or {})

    active = []
    for blocker in blockers:
        code = str(blocker.get("code") or "")
        if _blocker_masked_by_latest_build_timeout(
            blocker,
            latest_diagnostic_failure_class,
            latest_diagnostic_evidence_id,
            evidence_by_tool_call_id,
        ):
            continue
        if code == "external_dependency_source_provenance_unverified" and source_satisfied:
            continue
        if target_runtime_satisfied and code not in _SOURCE_AUTHORITY_BLOCKER_CODES:
            if not final_contract_satisfied and blocker.get("source_tool_call_id") in evidence_by_tool_call_id:
                active.append(blocker)
                continue
            if latest_diagnostic_failure_class and _generic_failure_class(code) == latest_diagnostic_failure_class:
                active.append(blocker)
            continue
        if final_contract_satisfied:
            continue
        active.append(blocker)
    return active


def _cleared_strategy_blockers(
    blockers: Iterable[Mapping[str, object]],
    active_blockers: Iterable[Mapping[str, object]],
) -> list[dict]:
    active_ids = {_blocker_identity(item) for item in active_blockers or [] if isinstance(item, Mapping)}
    cleared = []
    for blocker in blockers or []:
        if not isinstance(blocker, Mapping):
            continue
        if _blocker_identity(blocker) not in active_ids:
            cleared.append(dict(blocker))
    return cleared


def _blocker_identity(blocker: Mapping[str, object]) -> tuple[str, str, str]:
    return (
        str(blocker.get("code") or ""),
        str(blocker.get("source_tool_call_id") or ""),
        str(blocker.get("excerpt") or ""),
    )


def _source_authority_satisfied(attempts: Iterable[Mapping[str, object]]) -> bool:
    return any(
        _attempt_has_signal(item, "source_authority")
        for item in attempts or []
        if isinstance(item, Mapping)
    )


def _stage_status(attempts: Iterable[Mapping[str, object]], stage: str) -> str:
    stage_attempts = [item for item in attempts if item.get("stage") == stage]
    if any(item.get("result") == "success" for item in stage_attempts):
        return "satisfied"
    if any(item.get("result") in {"failure", "timeout"} for item in stage_attempts):
        return "blocked"
    if stage_attempts:
        return "unknown"
    return "unknown"


def _runtime_stage_status(
    attempts: Iterable[Mapping[str, object]],
    blockers: Iterable[Mapping[str, object]],
    *,
    fresh_default_smoke: bool = False,
) -> str:
    if fresh_default_smoke:
        return "satisfied"
    if any(item.get("stage") == "custom_runtime_smoke" and item.get("result") == "success" for item in attempts):
        return "blocked"
    if any(
        str(item.get("code") or "") in {"default_runtime_link_path_failed", "default_runtime_link_path_unproven", "runtime_link_library_missing"}
        for item in blockers or []
    ):
        return "blocked"
    return "unknown"


def _state_status(
    attempts: Iterable[Mapping[str, object]],
    missing: Iterable[Mapping[str, object]],
    current_failure: Mapping[str, object] | None,
    stages: Iterable[Mapping[str, object]],
) -> str:
    if not attempts:
        return "not_started"
    if current_failure:
        return "blocked"
    if any(item.get("status") == "blocked" and item.get("required") for item in stages or []):
        return "blocked"
    if any(item.get("status") == "unknown" and item.get("required") for item in stages or []):
        return "ready_for_final_proof" if not missing else "in_progress"
    if not missing:
        return "complete"
    return "in_progress"


def _current_failure(
    contract: Mapping[str, object],
    attempts: Iterable[Mapping[str, object]],
    blockers: Iterable[Mapping[str, object]],
    missing: Iterable[Mapping[str, object]],
    incomplete_reason: object,
    evidence_by_tool_call_id: Mapping[object, int],
    *,
    fresh_default_smoke: bool = False,
) -> dict | None:
    blockers = [dict(item) for item in blockers or []]
    if blockers:
        blocker = blockers[-1]
        source_tool_call_id = blocker.get("source_tool_call_id")
        legacy_code = blocker.get("code") or "long_build_strategy_blocked"
        return {
            "failure_class": _generic_failure_class(legacy_code),
            "legacy_code": legacy_code,
            "evidence_id": evidence_by_tool_call_id.get(source_tool_call_id),
            "source_tool_call_id": source_tool_call_id,
            "clear_condition": _clear_condition(blocker.get("code"), contract, missing),
        }
    if str(incomplete_reason or "") == "tool_timeout" and not _incomplete_reason_cleared_by_later_success(
        incomplete_reason,
        attempts,
    ):
        return {
            "failure_class": "build_timeout",
            "evidence_id": None,
            "clear_condition": "resume or rerun the shortest idempotent command with an explicit wall budget",
        }
    diagnostic_failure = _latest_attempt_diagnostic_failure(attempts)
    if diagnostic_failure:
        return diagnostic_failure
    if list(missing or []):
        paths = ", ".join(str(item.get("path") or "") for item in missing if isinstance(item, Mapping))
        return {
            "failure_class": "artifact_missing_or_unproven",
            "evidence_id": None,
            "clear_condition": f"terminal command evidence proves required artifact(s): {paths}",
        }
    runtime_policy = contract.get("runtime_proof") if isinstance(contract.get("runtime_proof"), Mapping) else {}
    if runtime_policy.get("required") == "required" and not fresh_default_smoke:
        return {
            "failure_class": "runtime_default_path_unproven",
            "evidence_id": None,
            "clear_condition": "default compile/link smoke succeeds without custom runtime path flags",
        }
    return None


def _blocker_masked_by_latest_build_timeout(
    blocker: Mapping[str, object],
    latest_diagnostic_failure_class: str,
    latest_diagnostic_evidence_id: object,
    evidence_by_tool_call_id: Mapping[object, int],
) -> bool:
    if latest_diagnostic_failure_class != "build_timeout":
        return False
    if str(blocker.get("code") or "") != "untargeted_full_project_build_for_specific_artifact":
        return False
    excerpt = str(blocker.get("excerpt") or "").casefold()
    if "install" not in excerpt:
        return False
    source_tool_call_id = blocker.get("source_tool_call_id")
    if source_tool_call_id is None:
        return False
    blocker_evidence_id = evidence_by_tool_call_id.get(source_tool_call_id)
    if blocker_evidence_id is None:
        return False
    return blocker_evidence_id == latest_diagnostic_evidence_id


def _latest_attempt_diagnostic_failure(attempts: Iterable[Mapping[str, object]]) -> dict | None:
    for attempt in reversed([dict(item) for item in attempts or [] if isinstance(item, Mapping)]):
        failure_class = ""
        excerpt = ""
        for diagnostic in attempt.get("diagnostics") or []:
            if not isinstance(diagnostic, Mapping):
                continue
            candidate = str(diagnostic.get("failure_class") or "")
            if candidate in _RECOVERY_DECISION_FAILURE_CLASSES:
                failure_class = candidate
                excerpt = str(diagnostic.get("excerpt") or "")
                break
        if not failure_class:
            if _attempt_clears_prior_recovery_failure(attempt):
                return None
            continue
        evidence_ref = attempt.get("command_evidence_ref") if isinstance(attempt.get("command_evidence_ref"), Mapping) else {}
        return {
            "failure_class": failure_class,
            "evidence_id": evidence_ref.get("id"),
            "attempt_id": attempt.get("id"),
            "excerpt": excerpt,
            "clear_condition": _clear_condition_for_failure_class(failure_class, missing=()),
        }
    return None


def _incomplete_reason_cleared_by_later_success(
    incomplete_reason: object,
    attempts: Iterable[Mapping[str, object]],
) -> bool:
    return str(incomplete_reason or "") == "tool_timeout" and _latest_failure_cleared_by_later_success(
        attempts,
        "build_timeout",
    )


def _latest_failure_cleared_by_later_success(
    attempts: Iterable[Mapping[str, object]],
    failure_class: str,
) -> bool:
    for attempt in reversed([dict(item) for item in attempts or [] if isinstance(item, Mapping)]):
        if _attempt_clears_prior_recovery_failure(attempt):
            return True
        if any(
            isinstance(diagnostic, Mapping) and diagnostic.get("failure_class") == failure_class
            for diagnostic in attempt.get("diagnostics") or []
        ):
            return False
    return False


def _attempt_clears_prior_recovery_failure(attempt: Mapping[str, object]) -> bool:
    if attempt.get("result") != "success":
        return False
    return str(attempt.get("stage") or "") in {
        "artifact_proof",
        "default_smoke",
        "runtime_build",
        "runtime_install",
    }


def _derive_recovery_decision(
    contract: Mapping[str, object],
    state_status: str,
    current_failure: Mapping[str, object] | None,
    attempts: Iterable[Mapping[str, object]],
    evidences: Iterable[CommandEvidence],
    blockers: Iterable[Mapping[str, object]],
) -> RecoveryDecision | None:
    if not current_failure:
        return None
    failure_class = str(current_failure.get("failure_class") or "")
    if failure_class not in _RECOVERY_DECISION_FAILURE_CLASSES:
        return None
    contract_id = str(contract.get("id") or "long_build")
    failure_attempts = _failure_attempt_count(failure_class, attempts, blockers)
    budget = _recovery_budget(contract, evidences, failure_class, failure_attempts)
    return RecoveryDecision(
        schema_version=LONG_BUILD_SCHEMA_VERSION,
        id=f"{contract_id}:recovery:{failure_attempts}",
        contract_id=contract_id,
        state_status=str(state_status or ""),
        failure_class=failure_class,
        prerequisites=_recovery_prerequisites(failure_class, contract),
        clear_condition=str(current_failure.get("clear_condition") or _clear_condition_for_failure_class(failure_class, missing=())),
        allowed_next_action=_recovery_allowed_next_action(failure_class, contract),
        prohibited_repeated_actions=_recovery_prohibited_repeated_actions(failure_class),
        budget=budget,
        decision="block_for_budget" if failure_class == "budget_reserve_violation" else "continue",
    )


def _failure_attempt_count(
    failure_class: str,
    attempts: Iterable[Mapping[str, object]],
    blockers: Iterable[Mapping[str, object]],
) -> int:
    count = 0
    for attempt in attempts or []:
        if not isinstance(attempt, Mapping):
            continue
        for diagnostic in attempt.get("diagnostics") or []:
            if isinstance(diagnostic, Mapping) and diagnostic.get("failure_class") == failure_class:
                count += 1
                break
    for blocker in blockers or []:
        if isinstance(blocker, Mapping) and _generic_failure_class(blocker.get("code")) == failure_class:
            count += 1
    return max(count, 1)


def _recovery_budget(
    contract: Mapping[str, object],
    evidences: Iterable[CommandEvidence],
    failure_class: str,
    failure_attempts: int,
) -> dict:
    budget_policy = contract.get("budget") if isinstance(contract.get("budget"), Mapping) else {}
    reserve_seconds = _coerce_int(budget_policy.get("final_proof_reserve_seconds"), default=60) or 60
    latest_evidence = max(
        [item for item in evidences or [] if isinstance(item, CommandEvidence)],
        key=lambda item: item.finish_order,
        default=None,
    )
    remaining_seconds = latest_evidence.wall_budget_after_seconds if latest_evidence else None
    return {
        "remaining_seconds": remaining_seconds,
        "reserve_seconds": reserve_seconds,
        "may_spend_reserve": failure_class
        in {
            "runtime_link_failed",
            "runtime_install_before_build",
            "build_system_target_surface_invalid",
        },
        "attempts_for_failure_class": failure_attempts,
        "max_attempts_for_failure_class": 2,
    }


def _recovery_prerequisites(failure_class: str, contract: Mapping[str, object]) -> list[str]:
    if failure_class == "artifact_missing_or_unproven":
        return ["source_authority_if_required", "required_artifact_contract"]
    if failure_class == "build_timeout":
        return ["preserve_existing_source_tree", "known_current_build_stage"]
    if failure_class == "runtime_link_failed":
        return ["artifact_invoked_by_failed_default_smoke", "runtime_proof_required"]
    if failure_class == "runtime_default_path_unproven":
        return ["target_built", "runtime_proof_required"]
    if failure_class == "runtime_install_before_build":
        return ["runtime_library_target_known_or_discovered"]
    if failure_class == "build_system_target_surface_invalid":
        return ["build_system_surface_inspected"]
    if failure_class == "budget_reserve_violation":
        return ["remaining_wall_budget_checked", "final_proof_reserve_policy"]
    return ["long_build_contract"]


def _recovery_allowed_next_action(failure_class: str, contract: Mapping[str, object]) -> dict:
    artifact_paths = [
        str((artifact or {}).get("path") or "")
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping) and (artifact or {}).get("path")
    ]
    if failure_class == "artifact_missing_or_unproven":
        return {
            "kind": "command",
            "stage": "target_build_or_artifact_proof",
            "description": "run the shortest idempotent build/proof command that produces and terminally proves the missing required artifact",
            "required_evidence": "terminal_success_command_evidence",
            "targets": artifact_paths[:6],
        }
    if failure_class == "build_timeout":
        return {
            "kind": "command",
            "stage": "continue_or_resume_build",
            "description": "resume or rerun the shortest idempotent build command with an explicit wall budget and preserve existing source/tree progress",
            "required_evidence": "terminal_command_progress_or_success",
            "targets": artifact_paths[:6],
        }
    if failure_class == "runtime_link_failed":
        return {
            "kind": "command",
            "stage": "runtime_build_or_install",
            "description": "when the default compile/link smoke fails with a missing runtime library, do not restart source acquisition; build or install the shortest runtime/library target into the default lookup path, then rerun the same smoke",
            "required_evidence": "terminal_success_default_runtime_smoke",
            "targets": artifact_paths[:6],
        }
    if failure_class == "runtime_default_path_unproven":
        return {
            "kind": "command",
            "stage": "default_runtime_smoke",
            "description": "rerun the compile/link smoke without custom runtime/library path flags after the runtime is installed or configured for the default lookup path",
            "required_evidence": "terminal_success_default_runtime_smoke",
            "targets": artifact_paths[:6],
        }
    if failure_class == "runtime_install_before_build":
        return {
            "kind": "command",
            "stage": "runtime_build_then_install",
            "description": "build the shortest explicit runtime-library target first, then retry install and default compile/link smoke",
            "required_evidence": "terminal_success_runtime_build_install_and_default_smoke",
            "targets": artifact_paths[:6],
        }
    if failure_class == "build_system_target_surface_invalid":
        return {
            "kind": "command",
            "stage": "build_system_target_surface_probe",
            "description": "switch to the valid build-system target surface, such as make -C <runtime-dir> all/install for a runtime subdirectory Makefile, then prove the runtime/default smoke",
            "required_evidence": "terminal_success_valid_target_surface",
            "targets": artifact_paths[:6],
        }
    if failure_class == "budget_reserve_violation":
        return {
            "kind": "replan",
            "stage": "budget_preserving_recovery",
            "description": "commit to one coherent branch, preferably an external/prebuilt compatibility branch, and reserve enough wall budget for final build/proof before spending the final proof reserve",
            "required_evidence": "updated_wall_budget_plan",
            "targets": artifact_paths[:6],
        }
    return {"kind": "command", "stage": "long_build_recovery", "description": "clear the current long-build failure"}


def _recovery_prohibited_repeated_actions(failure_class: str) -> list[str]:
    if failure_class == "artifact_missing_or_unproven":
        return ["repeat_non_proving_status_probe", "restart_source_acquisition_without_new_failure"]
    if failure_class == "build_timeout":
        return ["repeat_same_timeout_without_budget_change", "abandon_existing_source_tree_progress"]
    if failure_class == "runtime_link_failed":
        return ["source_reacquisition", "clean_rebuild", "custom_runtime_path_only_proof"]
    if failure_class == "runtime_default_path_unproven":
        return ["custom_runtime_path_only_proof", "repeat_custom_lookup_smoke"]
    if failure_class == "runtime_install_before_build":
        return ["retry_runtime_install_before_runtime_build", "clean_rebuild"]
    if failure_class == "build_system_target_surface_invalid":
        return ["retry_invalid_parent_target_path", "clean_rebuild"]
    if failure_class == "budget_reserve_violation":
        return ["long_validation_without_recovery_reserve", "serial_branch_probe_without_budget"]
    return ["repeat_same_failed_branch_without_new_evidence"]


def _clear_condition_for_failure_class(
    failure_class: str,
    *,
    missing: Iterable[Mapping[str, object]],
) -> str:
    if failure_class == "artifact_missing_or_unproven":
        paths = ", ".join(str(item.get("path") or "") for item in missing or [] if isinstance(item, Mapping))
        return f"terminal command evidence proves required artifact(s): {paths}" if paths else "terminal command evidence proves required artifact(s)"
    if failure_class == "build_timeout":
        return "shortest idempotent build/resume command completes or records bounded progress with wall budget preserved"
    if failure_class == "runtime_link_failed":
        return "default compile/link smoke succeeds after runtime or standard library is built/installed into the default lookup path"
    if failure_class == "runtime_default_path_unproven":
        return "default compile/link smoke succeeds without custom runtime path flags"
    if failure_class == "runtime_install_before_build":
        return "runtime/library artifact is built before runtime install is retried"
    if failure_class == "build_system_target_surface_invalid":
        return "valid build-system target surface succeeds for the runtime/library or required artifact"
    if failure_class == "budget_reserve_violation":
        return "recovery plan preserves the final proof reserve or explicitly spends it on the known recovery condition"
    return "the current failure is superseded by successful terminal evidence"


def _custom_runtime_path_proof(evidence: CommandEvidence) -> bool:
    return bool(_CUSTOM_RUNTIME_PATH_PROOF_RE.search(f"{evidence.command}\n{evidence.output_head}\n{evidence.output_tail}"))


def _terminal_command_uses_required_artifact(evidence: CommandEvidence, artifact: object) -> bool:
    if not command_evidence_terminal_acceptance_success(evidence):
        return False
    command = str(evidence.command or "")
    artifact_text = str(artifact or "")
    if re.search(r"\|\|\s*true\b|;\s*true\b", command):
        return False
    return _command_has_default_smoke_artifact_segment(command, artifact_text, evidence.cwd)


def _default_compile_link_smoke(evidence: CommandEvidence, contract: Mapping[str, object]) -> bool:
    if not _default_smoke_contract_allows_acceptance(evidence):
        return False
    if not command_evidence_terminal_acceptance_success(evidence):
        return False
    command = str(evidence.command or "")
    if _custom_runtime_path_proof(evidence):
        return False
    if not re.search(r"\.(?:c|cc|cpp|cxx)\b", command):
        return False
    if not re.search(r"(?:^|\s)-o\s+\S+", command):
        return False
    artifact_paths = [
        str((artifact or {}).get("path") or "")
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping)
    ]
    return any(path and _command_has_default_smoke_artifact_segment(command, path, evidence.cwd) for path in artifact_paths)


def _command_has_default_smoke_artifact_segment(command: object, artifact: object, cwd: object) -> bool:
    artifact_text = str(artifact or "")
    if not artifact_text:
        return False
    segment_entries = split_unquoted_shell_command_segment_spans(command)
    segments = [str(entry.get("text") or "") for entry in segment_entries]
    for index, segment in enumerate(segments):
        if not (
            _segment_invokes_required_artifact(segment, artifact_text, cwd)
            and re.search(r"\.(?:c|cc|cpp|cxx)\b", segment)
            and re.search(r"(?:^|\s)-o\s+\S+", segment)
        ):
            continue
        before_operator = str(segment_entries[index].get("before_operator") or "")
        after_operator = str(segment_entries[index].get("after_operator") or "")
        segment_errexit_active = _command_errexit_active_before_span(command, segment_entries[index])
        if before_operator == "||":
            continue
        if before_operator == "&&" and not _previous_shell_segment_is_positive_artifact_guard(
            segment_entries,
            index,
            artifact_text,
            cwd,
        ):
            continue
        if after_operator == "||" and _or_failure_guard_end_index(segment_entries, index) < 0:
            continue
        if after_operator == "|":
            continue
        if after_operator in {";", "\n", "\r"} and not segment_errexit_active:
            continue
        if _shell_text_has_unquoted_background_operator(segment):
            continue
        if _later_shell_segments_mask_artifact_failure(segment_entries, index, command):
            continue
        if _long_dependency_segment_may_mutate_artifact_scope(segment, artifact_text, cwd):
            continue
        if any(
            _long_dependency_segment_may_mutate_artifact_scope(later_segment, artifact_text, cwd)
            for later_segment in segments[index + 1 :]
        ):
            continue
        wrapper = _long_dependency_shell_wrapper_keyword(segment)
        if wrapper in {"elif", "while", "until"}:
            continue
        if wrapper == "if" and not _command_has_if_failure_exit_guard(command, segment):
            continue
        return True
    return False


def _command_errexit_active_before_span(command: object, span: Mapping[str, object]) -> bool:
    start = _coerce_int((span or {}).get("start"), default=0) or 0
    command_prefix = str(command or "")[:start]
    return _command_enables_errexit(command_prefix) and not _command_disables_errexit(command_prefix)


def _later_shell_segments_mask_artifact_failure(
    segment_entries: list[dict[str, object]],
    index: int,
    command: object,
) -> bool:
    segment_start = _coerce_int((segment_entries[index] or {}).get("start"), default=0) or 0
    command_prefix = str(command or "")[:segment_start]
    errexit_active = _command_errexit_active_before_span(command, segment_entries[index])
    pipefail_active = _command_enables_pipefail(command_prefix) and not _command_disables_pipefail(command_prefix)
    guard_end_index = _or_failure_guard_end_index(segment_entries, index)
    for absolute_index, entry in enumerate(segment_entries[index + 1 :], start=index + 1):
        if absolute_index <= guard_end_index:
            continue
        if _shell_text_has_unquoted_background_operator(entry.get("text")):
            return True
        before_operator = str(entry.get("before_operator") or "")
        after_operator = str(entry.get("after_operator") or "")
        if before_operator == "||" or after_operator == "||":
            return True
        if (before_operator == "|" or after_operator == "|") and not (errexit_active and pipefail_active):
            return True
        if after_operator in {";", "\n", "\r"} and not errexit_active:
            return True
    return False


def _or_failure_guard_end_index(segment_entries: list[dict[str, object]], index: int) -> int:
    if index < 0 or index >= len(segment_entries):
        return -1
    if str(segment_entries[index].get("after_operator") or "") != "||":
        return -1
    next_index = index + 1
    if next_index >= len(segment_entries):
        return -1
    if str(segment_entries[next_index].get("before_operator") or "") != "||":
        return -1
    guard_end = -1
    for candidate_index in range(next_index, min(len(segment_entries), next_index + 5)):
        text = str(segment_entries[candidate_index].get("text") or "").strip()
        if re.match(r"^(?:exit|return)\s+[1-9]\d*\b", text):
            guard_end = candidate_index
            continue
        if text == "}":
            return candidate_index if guard_end >= next_index else -1
        if candidate_index == next_index and re.match(r"^(?:exit|return)\s+[1-9]\d*\b", text):
            return candidate_index
    return guard_end if guard_end >= next_index else -1


def _shell_text_has_unquoted_background_operator(text: object) -> bool:
    value = str(text or "")
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\" and not in_single:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if in_single or in_double or char != "&":
            continue
        previous_char = value[index - 1] if index > 0 else ""
        next_char = value[index + 1] if index + 1 < len(value) else ""
        if previous_char in {"<", ">"} or next_char in {"<", ">"}:
            continue
        if previous_char != "&" and next_char != "&":
            return True
    return False


def _previous_shell_segment_is_positive_artifact_guard(
    segment_entries: list[dict[str, object]],
    index: int,
    artifact: object,
    cwd: object,
) -> bool:
    if index <= 0:
        return False
    previous = str(segment_entries[index - 1].get("text") or "").strip()
    refs = _artifact_guard_refs(artifact, cwd)
    try:
        parts = shlex.split(previous)
    except ValueError:
        parts = previous.split()
    if len(parts) >= 3 and parts[0] == "test" and parts[1] == "-x":
        return _shell_token_matches_artifact_guard_ref(parts[2], refs)
    if len(parts) >= 4 and parts[0] == "[" and parts[1] == "-x" and parts[-1] == "]":
        return _shell_token_matches_artifact_guard_ref(parts[2], refs)
    return False


def _artifact_guard_refs(artifact: object, cwd: object) -> list[str]:
    artifact_text = str(artifact or "").strip()
    refs = [artifact_text] if artifact_text else []
    cwd_text = str(cwd or "").strip()
    artifact_path = Path(artifact_text)
    if artifact_path.is_absolute() and cwd_text and str(Path(cwd_text)) == str(artifact_path.parent):
        basename = artifact_path.name.strip()
        if basename:
            refs.extend([basename, f"./{basename}"])
    return refs


def _shell_token_matches_artifact_guard_ref(token: object, refs: list[str]) -> bool:
    token_text = str(token or "").strip().rstrip(";")
    return any(token_text == ref for ref in refs if ref)


def _long_dependency_shell_wrapper_keyword(segment: object) -> str:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    if not parts:
        return ""
    token = Path(str(parts[0] or "")).name.casefold()
    return token if token in {"if", "elif", "while", "until"} else ""


def _command_has_if_failure_exit_guard(command: object, segment: object) -> bool:
    command_text = str(command or "")
    segment_text = str(segment or "").strip()
    if not segment_text:
        return False
    lines = command_text.splitlines()
    start_index = next(
        (
            index
            for index, line in enumerate(lines)
            if segment_text in line.strip() and re.match(r"^\s*(?:if|elif)\b", line)
        ),
        -1,
    )
    if start_index < 0:
        return False
    saw_else = False
    depth = 0
    for line in lines[start_index + 1 :]:
        stripped = line.strip()
        if re.search(r"(?:^|[;&|]\s*)(?:if|case|for|while|until)\b", stripped):
            depth += 1
            continue
        if re.match(r"^fi\b", stripped):
            if depth > 0:
                depth -= 1
                continue
            return False
        if depth == 0 and re.match(r"^else\b", stripped):
            saw_else = True
            continue
        if depth == 0 and saw_else and re.match(r"^exit\s+[1-9]\d*\b", stripped):
            return True
    return False


def _segment_invokes_required_artifact(segment: object, artifact: object, cwd: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    if _long_dependency_shell_invocation_is_negated(parts):
        return False
    command_token = _long_dependency_shell_invoked_command_token(parts)
    if _segment_names_required_artifact(command_token, artifact, cwd):
        return True
    return False


def _long_dependency_shell_invocation_is_negated(parts: list[str]) -> bool:
    index = 0
    if parts and Path(str(parts[0] or "")).name.casefold() in {"if", "elif", "while", "until"}:
        index = 1
    if index < len(parts or []) and str(parts[index] or "") == "!":
        return True
    if index < len(parts or []) and Path(str(parts[index] or "")).name.casefold() == "time":
        index += 1
        while index < len(parts or []) and str(parts[index] or "").startswith("-"):
            index += 1
        return index < len(parts or []) and str(parts[index] or "") == "!"
    return False


def _long_dependency_shell_invoked_command_token(parts: list[str]) -> str:
    index = 0
    if parts and Path(str(parts[0] or "")).name.casefold() in {"if", "elif", "while", "until"}:
        index = 1
    while index < len(parts or []) and str(parts[index] or "") == "!":
        index += 1
    while index < len(parts or []) and Path(str(parts[index] or "")).name.casefold() == "time":
        index += 1
        while index < len(parts or []) and str(parts[index] or "").startswith("-"):
            index += 1
    return _long_dependency_invoked_command_token([str(part or "") for part in (parts or [])[index:]])


def _segment_names_required_artifact(segment: object, artifact: object, cwd: object) -> bool:
    segment_text = str(segment or "")
    artifact_text = str(artifact or "")
    if not artifact_text:
        return False
    if re.search(r"(?:^|[\s'\"])" + re.escape(artifact_text) + r"(?:$|\s|['\"])", segment_text):
        return True
    artifact_parent = str(Path(artifact_text).parent).rstrip("/")
    cwd_text = str(Path(str(cwd or ""))).rstrip("/")
    if artifact_parent and artifact_parent != "." and cwd_text == artifact_parent:
        basename = Path(artifact_text).name
        basename_pattern = r"(?:\./)?" + re.escape(basename)
        return bool(basename and re.search(r"(?:^|\s)" + basename_pattern + r"(?:$|\s)", segment_text))
    return False


def _generic_failure_class(code: object) -> str:
    return _GENERIC_FAILURE_CLASS_BY_BLOCKER_CODE.get(str(code or ""), str(code or "long_build_strategy_blocked"))


def _attempt_has_signal(attempt: Mapping[str, object], signal: str) -> bool:
    return any(
        isinstance(item, Mapping) and item.get("signal") == signal
        for item in attempt.get("diagnostics") or []
    )


def _attempt_produced_artifact_proof(
    attempts: Iterable[Mapping[str, object]],
    path: str,
    evidences: Iterable[CommandEvidence],
) -> dict:
    latest = {}
    for attempt in attempts or []:
        if not isinstance(attempt, Mapping):
            continue
        for artifact in attempt.get("produced_artifacts") or []:
            if isinstance(artifact, Mapping) and artifact.get("path") == path:
                latest = dict(artifact)
    if latest and _later_evidence_mutates_artifact(latest, path, evidences):
        return {}
    return latest


def _has_fresh_default_smoke(
    attempts: Iterable[Mapping[str, object]],
    evidences: Iterable[CommandEvidence],
    contract: Mapping[str, object],
) -> bool:
    artifact_paths = [
        str((artifact or {}).get("path") or "")
        for artifact in contract.get("required_artifacts") or []
        if isinstance(artifact, Mapping) and (artifact or {}).get("path")
    ]
    if not artifact_paths:
        return False
    for attempt in attempts or []:
        if not (
            isinstance(attempt, Mapping)
            and attempt.get("stage") == "default_smoke"
            and attempt.get("result") == "success"
        ):
            continue
        if any(
            isinstance(diagnostic, Mapping)
            and str(diagnostic.get("failure_class") or "") in _RECOVERY_DECISION_FAILURE_CLASSES
            for diagnostic in attempt.get("diagnostics") or []
        ):
            continue
        produced_paths = {
            str((artifact or {}).get("path") or "")
            for artifact in attempt.get("produced_artifacts") or []
            if isinstance(artifact, Mapping)
        }
        if not all(path in produced_paths for path in artifact_paths):
            continue
        evidence_id = (attempt.get("command_evidence_ref") or {}).get("id")
        proof = {"proof_evidence_id": evidence_id}
        if not any(_later_evidence_mutates_artifact(proof, path, evidences) for path in artifact_paths):
            return True
    return False


def _later_evidence_mutates_artifact(
    proof: Mapping[str, object],
    path: str,
    evidences: Iterable[CommandEvidence],
) -> bool:
    proof_evidence_id = proof.get("proof_evidence_id")
    evidence_items = [item for item in evidences or [] if isinstance(item, CommandEvidence)]
    proof_evidence = next((item for item in evidence_items if item.id == proof_evidence_id), None)
    if proof_evidence is None:
        return False
    proof_order = proof_evidence.finish_order
    return any(
        item.finish_order > proof_order and _command_may_mutate_artifact_scope(item.command, path, item.cwd)
        for item in evidence_items
    )


def _clear_condition(code: object, contract: Mapping[str, object], missing: Iterable[Mapping[str, object]]) -> str:
    code_text = str(code or "")
    if code_text in {"default_runtime_link_path_failed", "default_runtime_link_path_unproven", "runtime_link_library_missing"}:
        return "default compile/link smoke succeeds without custom runtime path flags"
    if code_text == "runtime_install_before_runtime_library_build":
        return "shortest runtime/library target is built before runtime install is retried"
    if code_text == "runtime_library_subdir_target_path_invalid":
        return "runtime subdirectory build/install target succeeds from the subdirectory Makefile"
    if code_text == "compatibility_branch_budget_contract_missing":
        return "one external/prebuilt compatibility branch is selected early enough to preserve final build/proof budget"
    if code_text == "untargeted_full_project_build_for_specific_artifact":
        return "shortest explicit target for the required artifact is attempted"
    if code_text == "external_dependency_source_provenance_unverified":
        return "source authority is grounded by project docs, package metadata, official release archive, checksum, or upstream page"
    if code_text == "external_branch_help_probe_too_narrow_before_source_toolchain":
        return "project help is inspected broadly enough to find external/prebuilt/system dependency branches"
    if code_text == "source_toolchain_before_external_branch_attempt":
        return "the exposed external/prebuilt/system dependency branch is attempted before version-pinned source toolchain work"
    if list(missing or []):
        paths = ", ".join(str(item.get("path") or "") for item in missing if isinstance(item, Mapping))
        return f"terminal command evidence proves required artifact(s): {paths}"
    return "the blocker-specific command evidence is superseded by a successful terminal proof"


def _has_source_blocker(blockers: Iterable[Mapping[str, object]]) -> bool:
    return any(str(item.get("code") or "") in _SOURCE_AUTHORITY_BLOCKER_CODES for item in blockers or [])


def _first_matching_line(text: object, pattern: str) -> str:
    regex = re.compile(pattern, re.I)
    for line in str(text or "").splitlines():
        if regex.search(line):
            return _clip(line.strip(), 180)
    return _first_nonempty_line(text)


def _first_nonempty_line(text: object) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped:
            return _clip(stripped, 180)
    return ""


def _dict_value(value: object) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _combined_output_text(result: Mapping[str, object], stream: str) -> str:
    values = [result.get(stream), result.get(f"{stream}_tail")]
    parts = []
    for value in values:
        text = str(value or "")
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts)


def _head(text: object, limit: int = COMMAND_OUTPUT_CLIP_CHARS) -> str:
    return str(text or "")[:limit]


def _tail(text: object, limit: int = COMMAND_OUTPUT_CLIP_CHARS) -> str:
    value = str(text or "")
    return value[-limit:] if len(value) > limit else value


def _clip(text: object, limit: int) -> str:
    value = str(text or "")
    return value[:limit]


def _merge_head_tail(head: object, tail: object) -> str:
    head_text = str(head or "")
    tail_text = str(tail or "")
    if not head_text:
        return tail_text
    if not tail_text or tail_text == head_text or head_text.endswith(tail_text):
        return head_text
    return f"{head_text}\n...\n{tail_text}"


def _optional_dict(value: object) -> dict | None:
    return dict(value) if isinstance(value, Mapping) else None


def _stable_id_component(value: object) -> str:
    text = str(value or "unknown")
    return text if text else "unknown"


def _safe_path_component(value: object) -> str:
    text = str(value or "unknown")
    safe = re.sub(r"[^A-Za-z0-9_.+-]+", "-", text).strip("-")
    return safe or "unknown"


def _coerce_int(value: object, default: int | None = None) -> int | None:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _wall_budget_after_seconds(wall_ceiling: Mapping[str, object], result: Mapping[str, object]) -> int | None:
    before = _coerce_float(wall_ceiling.get("remaining_seconds"))
    if before is None:
        return None
    duration = _coerce_float(result.get("duration_seconds"))
    if duration is None:
        return None
    return max(0, int(before - duration))


def _command_may_mutate_artifact_scope(command: object, artifact: object, cwd: object = "") -> bool:
    for segment in split_unquoted_shell_command_segments(command):
        if _long_dependency_segment_may_mutate_artifact_scope(segment, artifact, cwd):
            return True
    return False
