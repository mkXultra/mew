from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Iterable, Mapping

from .acceptance_evidence import (
    COMMAND_EVIDENCE_TOOLS,
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
