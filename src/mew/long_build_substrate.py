from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
import shlex
from typing import Iterable, Mapping

from .acceptance_evidence import (
    COMMAND_EVIDENCE_TOOLS,
    _long_dependency_invoked_command_token,
    _long_dependency_segment_may_mutate_artifact_scope,
    long_dependency_artifact_proven_by_call,
    split_unquoted_shell_command_segments,
    tool_call_output_text,
    tool_call_terminal_success,
)


LONG_BUILD_SCHEMA_VERSION = 1
ENV_SUMMARY_POLICY = "env_summary_v1"
COMMAND_OUTPUT_CLIP_CHARS = 1200
ENV_VALUE_CLIP_CHARS = 120

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
    r"^matched_authority_url=https?://)",
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
            diagnostics=_diagnostics(evidence),
        )
        attempts.append(attempt.to_dict())
    return attempts


def reduce_long_build_state(
    contract: Mapping[str, object],
    attempts: Iterable[Mapping[str, object]],
    evidences: Iterable[CommandEvidence | Mapping[str, object]],
    *,
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
    for artifact in contract.get("required_artifacts") or []:
        path = str((artifact or {}).get("path") or "")
        proof = fresh_long_dependency_artifact_evidence(normalized_evidence, path) if path else None
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
        fresh_default_smoke=fresh_default_smoke,
    )
    stages = _reduce_stages(contract, attempts, artifact_status, active_blockers, fresh_default_smoke=fresh_default_smoke)
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
    effective_incomplete_reason = (
        ""
        if _incomplete_reason_cleared_by_later_success(incomplete_reason, attempts)
        else str(incomplete_reason or "")
    )
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
        "parameters": {"command": evidence.get("command") or "", "cwd": evidence.get("cwd") or ""},
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
    if not evidence.terminal_success:
        return False
    return long_dependency_artifact_proven_by_call(command_evidence_to_tool_call(evidence), artifact)


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


def _command_stage(evidence: CommandEvidence, contract: Mapping[str, object]) -> str:
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
    if status in {"running", "interrupted"}:
        return status
    if evidence.timed_out:
        return "timeout"
    if evidence.terminal_success:
        return "success"
    if status == "completed" or evidence.exit_code not in (None, 0):
        return "failure"
    return "unknown"


def _produced_artifacts(evidence: CommandEvidence, contract: Mapping[str, object]) -> list[dict]:
    produced = []
    for artifact in contract.get("required_artifacts") or []:
        path = str((artifact or {}).get("path") or "")
        if path and (
            long_dependency_artifact_proven_by_command_evidence(evidence, path)
            or _terminal_command_uses_required_artifact(evidence, path)
        ):
            produced.append({"path": path, "proof_evidence_id": evidence.id})
    return produced


def _diagnostics(evidence: CommandEvidence) -> list[dict]:
    text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    diagnostics = []
    if _source_authority_signal(evidence):
        diagnostics.append({"signal": "source_authority", "excerpt": _source_authority_excerpt(evidence)})
    if evidence.timed_out:
        diagnostics.append({"failure_class": "build_timeout", "excerpt": _first_nonempty_line(text)})
    if re.search(r"cannot find -l|ld: library not found|missing runtime|stdlib", text, re.I):
        diagnostics.append({"failure_class": "runtime_link_failed", "excerpt": _first_matching_line(text, "cannot find -l|library not found|runtime|stdlib")})
    if re.search(r"no rule to make target|No rule to make target", text):
        diagnostics.append({"failure_class": "build_system_target_surface_invalid", "excerpt": _first_matching_line(text, "no rule")})
    if _BUILD_FAILURE_RE.search(text) and not diagnostics:
        diagnostics.append({"failure_class": "build_failed", "excerpt": _first_matching_line(text, _BUILD_FAILURE_RE.pattern)})
    return [item for item in diagnostics if item.get("failure_class") or item.get("signal")]


def _source_authority_signal(evidence: CommandEvidence) -> bool:
    text = f"{evidence.command}\n{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    output_text = f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}"
    if _command_uses_direct_source_acquisition_tool(evidence.command):
        if _DIRECT_SOURCE_AUTHORITY_OUTPUT_RE.search(output_text):
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
    if _SOURCE_AUTHORITY_RE.search(text):
        return _first_matching_line(text, _SOURCE_AUTHORITY_RE.pattern)
    return _first_matching_line(f"{evidence.output_head}\n{evidence.output_tail}\n{evidence.stderr_tail}", _PACKAGE_METADATA_OUTPUT_RE.pattern)


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
) -> list[dict]:
    attempts = [dict(item) for item in attempts or []]
    blockers = [dict(item) for item in blockers or []]
    stages: list[dict] = []
    source_blocked = _has_source_blocker(blockers)
    source_satisfied = _source_authority_satisfied(attempts)
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
                "status": _stage_status(attempts, "dependency_generation"),
            }
        )
    target_proven = all((item or {}).get("status") == "proven" for item in artifacts or [])
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
    fresh_default_smoke: bool = False,
) -> list[dict]:
    blockers = [dict(item) for item in blockers or [] if isinstance(item, Mapping)]
    if not blockers:
        return []
    attempts = [dict(item) for item in attempts or [] if isinstance(item, Mapping)]
    artifacts = [dict(item) for item in artifacts or [] if isinstance(item, Mapping)]
    source_required = bool((contract.get("source_policy") or {}).get("authority_required", True))
    source_satisfied = _source_authority_satisfied(attempts)
    target_proven = bool(artifacts) and all(item.get("status") == "proven" for item in artifacts)
    runtime_policy = contract.get("runtime_proof") if isinstance(contract.get("runtime_proof"), Mapping) else {}
    runtime_required = runtime_policy.get("required") == "required"
    runtime_satisfied = (not runtime_required) or fresh_default_smoke
    final_contract_satisfied = target_proven and runtime_satisfied and ((not source_required) or source_satisfied)

    active = []
    for blocker in blockers:
        code = str(blocker.get("code") or "")
        if code == "external_dependency_source_provenance_unverified" and source_satisfied:
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
        item.get("result") == "success" and _attempt_has_signal(item, "source_authority")
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


def _latest_attempt_diagnostic_failure(attempts: Iterable[Mapping[str, object]]) -> dict | None:
    for attempt in reversed([dict(item) for item in attempts or [] if isinstance(item, Mapping)]):
        if _attempt_clears_prior_recovery_failure(attempt):
            return None
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
    if failure_class in {"runtime_link_failed", "runtime_default_path_unproven"}:
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
    if not evidence.terminal_success:
        return False
    command = str(evidence.command or "")
    artifact_text = str(artifact or "")
    if re.search(r"\|\|\s*true\b|;\s*true\b", command):
        return False
    return _command_has_default_smoke_artifact_segment(command, artifact_text, evidence.cwd)


def _default_compile_link_smoke(evidence: CommandEvidence, contract: Mapping[str, object]) -> bool:
    if not evidence.terminal_success:
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
    segments = split_unquoted_shell_command_segments(command)
    for index, segment in enumerate(segments):
        if not (
            _segment_invokes_required_artifact(segment, artifact_text, cwd)
            and re.search(r"\.(?:c|cc|cpp|cxx)\b", segment)
            and re.search(r"(?:^|\s)-o\s+\S+", segment)
        ):
            continue
        if _long_dependency_segment_may_mutate_artifact_scope(segment, artifact_text, cwd):
            continue
        if any(
            _long_dependency_segment_may_mutate_artifact_scope(later_segment, artifact_text, cwd)
            for later_segment in segments[index + 1 :]
        ):
            continue
        return True
    return False


def _segment_invokes_required_artifact(segment: object, artifact: object, cwd: object) -> bool:
    try:
        parts = shlex.split(str(segment or ""))
    except ValueError:
        parts = str(segment or "").split()
    command_token = _long_dependency_invoked_command_token(parts)
    return _segment_names_required_artifact(command_token, artifact, cwd)


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
    if list(missing or []):
        paths = ", ".join(str(item.get("path") or "") for item in missing if isinstance(item, Mapping))
        return f"terminal command evidence proves required artifact(s): {paths}"
    return "the blocker-specific command evidence is superseded by a successful terminal proof"


def _has_source_blocker(blockers: Iterable[Mapping[str, object]]) -> bool:
    return any("source" in str(item.get("code") or "") or "archive" in str(item.get("code") or "") for item in blockers or [])


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
