"""Finish-verifier planner component for the native implement lane."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import shlex
from typing import Literal, Mapping

from .finish_verifier_planner_policy import FinishVerifierPlannerPolicy, finish_verifier_planner_policy
from .native_finish_gate import (
    FinishCloseoutCommand,
    FinishCloseoutCommandValidation,
    NativeFinishGatePolicy,
    validate_closeout_command,
)
from .types import ImplementLaneInput, ToolResultEnvelope


FINISH_VERIFIER_PLANNER_DECISIONS_FILE = "finish_verifier_planner_decisions.jsonl"
FINISH_VERIFIER_PLANNER_REQUESTS_FILE = "finish_verifier_planner_requests.jsonl"

_FINISH_VERIFIER_PLANNER_DECISIONS_ATTR = "_mew_finish_verifier_planner_decisions"
_FINISH_VERIFIER_PLANNER_REQUESTS_ATTR = "_mew_finish_verifier_planner_requests"
_RAW_FINISH_VERIFIER_PLAN_MISSING = object()


@dataclass(frozen=True)
class FinishVerifierPlan:
    command: str
    cwd: str = "."
    source: str = "configured"
    reason: str = ""
    confidence: str = ""
    raw: Mapping[str, object] | None = None


@dataclass(frozen=True)
class FinishVerifierPlanCoercion:
    plan: FinishVerifierPlan | None
    status: str
    reject_reason: str = ""
    reject_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierCommandSafetyResult:
    allowed: bool
    reason: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierPlannerLoopPolicy:
    enabled: bool
    selection_source: str = ""
    max_turns: int = 3
    max_wall_seconds: float = 300.0
    max_file_reads: int = 12
    max_searches: int = 8
    max_bytes_per_file: int = 20_000
    max_total_read_bytes: int = 120_000
    allowed_tools: tuple[str, ...] = ("inspect_dir", "read_file", "search_text", "glob")
    allowed_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierPlannerEligibility:
    policy: FinishVerifierPlannerPolicy
    can_run: bool
    selection_source: str


@dataclass(frozen=True)
class FinishVerifierPlannerLoopRequest:
    lane_attempt_id: str
    turn_id: str
    task_id: str
    task_description: str
    task_contract: Mapping[str, object]
    latest_mutation: Mapping[str, object]
    recent_tool_results: tuple[Mapping[str, object], ...]
    candidate_paths: tuple[str, ...]
    policy: FinishVerifierPlannerLoopPolicy
    finish_call_id: str = ""
    done_candidate_id: str = ""
    legacy_request: Mapping[str, object] | None = None

    def as_planner_request(self) -> dict[str, object]:
        base = dict(self.legacy_request or {})
        requirement_source = dict(base)
        requirement_source["task"] = {
            "task_id": self.task_id,
            "description": self.task_description,
            "contract": dict(self.task_contract),
        }
        base.update(
            {
                "schema_version": 1,
                "component": "FinishVerifierPlannerLoop",
                "role": "independent_read_only_finish_verifier_planner",
                "lane_attempt_id": self.lane_attempt_id,
                "turn_id": self.turn_id,
                "task": {
                    "task_id": self.task_id,
                    "description": self.task_description,
                    "contract": dict(self.task_contract),
                    "verify_command_source": (
                        dict(base.get("task") or {}).get("verify_command_source")
                        if isinstance(base.get("task"), Mapping)
                        else ""
                    ),
                },
                "latest_mutation": dict(self.latest_mutation),
                "recent_tool_results": [dict(item) for item in self.recent_tool_results],
                "read_policy": {
                    "enabled": self.policy.enabled,
                    "selection_source": self.policy.selection_source,
                    "allowed_tools": list(self.policy.allowed_tools),
                    "allowed_roots": list(self.policy.allowed_roots),
                    "max_turns": self.policy.max_turns,
                    "max_file_reads": self.policy.max_file_reads,
                    "max_searches": self.policy.max_searches,
                    "max_bytes_per_file": self.policy.max_bytes_per_file,
                    "max_total_read_bytes": self.policy.max_total_read_bytes,
                    "candidate_paths": list(self.candidate_paths),
                },
                "command_policy": {
                    "available_execution_surface": "run_command",
                    "allow_shell_execution": True,
                    "shell_composition_blocked": True,
                    "observable_requirements": list(finish_verifier_observable_requirements(requirement_source)),
                },
                "output_contract": {
                    "json_object": True,
                    "required": ["status", "command", "cwd", "confidence", "rationale"],
                    "meaning": "one non-mutating command that verifies current task completion",
                },
            }
        )
        if self.done_candidate_id:
            base["done_candidate_id"] = self.done_candidate_id
            base.pop("finish_call_id", None)
        elif self.finish_call_id:
            base["finish_call_id"] = self.finish_call_id
        return base


@dataclass(frozen=True)
class FinishVerifierPlannerLoopResult:
    status: Literal["selected", "no_plan", "rejected", "error", "timed_out"]
    plan: FinishVerifierPlan | None
    record: Mapping[str, object]
    blockers: tuple[str, ...] = ()
    reason: str = ""


def build_finish_verifier_planner_loop_request(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    done_candidate_id: str = "",
) -> FinishVerifierPlannerLoopRequest:
    legacy_request = finish_verifier_planner_request(lane_input, tool_results)
    task = legacy_request.get("task") if isinstance(legacy_request.get("task"), Mapping) else {}
    read_policy = legacy_request.get("read_policy") if isinstance(legacy_request.get("read_policy"), Mapping) else {}
    allowed_roots = lane_config.get("allowed_read_roots")
    if not isinstance(allowed_roots, (list, tuple)):
        allowed_roots = (lane_input.workspace,)
    planner_policy = finish_verifier_planner_policy(lane_config)
    latest_mutation = latest_mutation_for_finish_verifier_planner(tool_results)
    task_contract = dict(lane_input.task_contract)
    legacy_contract = task.get("contract")
    if isinstance(legacy_contract, Mapping):
        task_contract.update(dict(legacy_contract))
    return FinishVerifierPlannerLoopRequest(
        lane_attempt_id=lane_attempt_id(lane_input),
        turn_id="finish-verifier-planner",
        finish_call_id="" if done_candidate_id else "finish",
        done_candidate_id=done_candidate_id,
        task_id=str(task.get("task_id") or lane_input.task_id),
        task_description=str(task.get("description") or native_task_description(lane_input)),
        task_contract=task_contract,
        latest_mutation=latest_mutation,
        recent_tool_results=tuple(
            item for item in legacy_request.get("recent_tool_results", ()) if isinstance(item, Mapping)
        ),
        candidate_paths=finish_verifier_planner_candidate_paths(
            lane_input,
            latest_mutation=latest_mutation,
            legacy_read_policy=read_policy,
            tool_results=tool_results,
        ),
        policy=FinishVerifierPlannerLoopPolicy(
            enabled=planner_policy.enabled,
            selection_source=planner_policy.selection_source,
            max_turns=planner_bounded_int(lane_config.get("finish_verifier_planner_max_turns"), 3, 1, 8),
            max_wall_seconds=safe_float(
                lane_config.get("finish_verifier_planner_timeout_seconds"),
                default=300.0,
            ),
            allowed_roots=tuple(str(root) for root in allowed_roots if str(root).strip()),
        ),
        legacy_request=legacy_request,
    )


def run_finish_verifier_planner_loop(
    request: FinishVerifierPlannerLoopRequest,
    *,
    planner_provider: object,
    read_dispatcher: object | None = None,
    artifact_sink: object | None = None,
) -> FinishVerifierPlannerLoopResult:
    """Run the finish-verifier planner component against a planner provider."""

    del read_dispatcher, artifact_sink
    planner_request = request.as_planner_request()
    request_hash = finish_verifier_planner_request_hash(planner_request)
    record_finish_verifier_planner_request(planner_provider, planner_request, request_hash=request_hash)
    if not request.policy.enabled:
        record = finish_verifier_planner_decision_record(
            status="no_plan",
            request_hash=request_hash,
            reject_reason="finish verifier planner loop is disabled",
            reject_blockers=("planner_loop_disabled",),
        )
        record = finish_verifier_planner_record_with_authority(record, planner_request)
        return FinishVerifierPlannerLoopResult(
            status="no_plan",
            plan=None,
            record=record,
            blockers=("planner_loop_disabled",),
            reason="finish verifier planner loop is disabled",
        )
    planner = getattr(planner_provider, "plan_finish_verifier_command", None)
    if not callable(planner):
        record = finish_verifier_planner_decision_record(
            status="no_plan",
            request_hash=request_hash,
            reject_reason="planner provider has no plan_finish_verifier_command",
            reject_blockers=("planner_provider_missing",),
        )
        record = finish_verifier_planner_record_with_authority(record, planner_request)
        return FinishVerifierPlannerLoopResult(
            status="no_plan",
            plan=None,
            record=record,
            blockers=("planner_provider_missing",),
            reason="planner provider has no plan_finish_verifier_command",
        )
    try:
        raw_plan = planner(planner_request)
    except Exception as exc:
        record = finish_verifier_planner_decision_record(
            status="error",
            request_hash=request_hash,
            error=str(exc),
        )
        record = finish_verifier_planner_record_with_authority(record, planner_request)
        return FinishVerifierPlannerLoopResult(
            status="error",
            plan=None,
            record=record,
            blockers=("planner_provider_error",),
            reason=str(exc),
        )
    forbidden = finish_verifier_planner_forbidden_tool_attempts(raw_plan, request.policy)
    if forbidden:
        record = finish_verifier_planner_decision_record(
            status="rejected",
            request_hash=request_hash,
            raw_plan=raw_plan,
            reject_reason="planner attempted forbidden tool",
            reject_blockers=forbidden,
        )
        record = finish_verifier_planner_record_with_authority(record, planner_request)
        return FinishVerifierPlannerLoopResult(
            status="rejected",
            plan=None,
            record=record,
            blockers=forbidden,
            reason="planner attempted forbidden tool",
        )
    coercion = coerce_finish_verifier_plan_with_diagnostics(raw_plan, request=planner_request)
    if coercion.plan is None:
        record = finish_verifier_planner_decision_record(
            status=coercion.status or "rejected",
            request_hash=request_hash,
            raw_plan=raw_plan,
            reject_reason=coercion.reject_reason,
            reject_blockers=coercion.reject_blockers,
        )
        record = finish_verifier_planner_record_with_authority(record, planner_request)
        return FinishVerifierPlannerLoopResult(
            status="rejected" if coercion.status != "no_plan" else "no_plan",
            plan=None,
            record=record,
            blockers=coercion.reject_blockers,
            reason=coercion.reject_reason,
        )
    record = finish_verifier_planner_decision_record(
        status="accepted",
        request_hash=request_hash,
        raw_plan=raw_plan,
        plan=coercion.plan,
    )
    record = finish_verifier_planner_record_with_authority(record, planner_request)
    return FinishVerifierPlannerLoopResult(
        status="selected",
        plan=coercion.plan,
        record=record,
        reason=coercion.plan.reason,
    )


def native_finish_verifier_planner_can_run(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> bool:
    return native_finish_verifier_planner_eligibility(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    ).can_run


def native_finish_verifier_planner_eligibility(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    configured_verifier_precedence: bool = False,
    policy: FinishVerifierPlannerPolicy | None = None,
) -> FinishVerifierPlannerEligibility:
    del lane_input
    planner_policy = policy or finish_verifier_planner_policy(lane_config)
    if not planner_policy.enabled:
        return FinishVerifierPlannerEligibility(
            policy=planner_policy,
            can_run=False,
            selection_source=planner_policy.selection_source,
        )
    if configured_verifier_precedence:
        return FinishVerifierPlannerEligibility(
            policy=planner_policy,
            can_run=False,
            selection_source="configured_verifier_precedence",
        )
    if not tool_results:
        return FinishVerifierPlannerEligibility(
            policy=planner_policy,
            can_run=False,
            selection_source="not_eligible",
        )
    if not callable(getattr(provider, "plan_finish_verifier_command", None)):
        return FinishVerifierPlannerEligibility(
            policy=planner_policy,
            can_run=False,
            selection_source="provider_missing",
        )
    return FinishVerifierPlannerEligibility(
        policy=planner_policy,
        can_run=True,
        selection_source=planner_policy.selection_source,
    )


def native_finish_verifier_planner_selection_source(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    decisions: tuple[Mapping[str, object], ...],
    configured_verifier_precedence: bool,
    policy: FinishVerifierPlannerPolicy | None = None,
) -> str:
    if decisions:
        decision_source = str(decisions[-1].get("selection_source") or "").strip()
        if decision_source:
            return decision_source
    eligibility = native_finish_verifier_planner_eligibility(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
        configured_verifier_precedence=configured_verifier_precedence,
        policy=policy,
    )
    return eligibility.selection_source


def latest_mutation_for_finish_verifier_planner(
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    for result in reversed(tool_results):
        if result.status != "completed" or result.is_error:
            continue
        if result.tool_name not in {"write_file", "edit_file", "apply_patch", "run_command", "exec_command"}:
            continue
        payload = native_result_payload(result)
        paths: list[str] = []
        for key in ("path", "target", "file", "output_path"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                paths.append(value)
        return {
            "provider_call_id": result.provider_call_id,
            "tool_name": result.tool_name,
            "status": result.status,
            "paths": paths[:8],
            "summary": result.natural_result_text(limit=500),
        }
    return {}


def finish_verifier_planner_candidate_paths(
    lane_input: ImplementLaneInput,
    *,
    latest_mutation: Mapping[str, object],
    legacy_read_policy: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> tuple[str, ...]:
    workspace = Path(str(lane_input.workspace or ".")).expanduser().resolve(strict=False)
    paths: list[str] = []
    extend_unique_paths(paths, legacy_read_policy.get("candidate_paths"), workspace=workspace, structured=True)
    extend_unique_paths(paths, latest_mutation.get("paths"), workspace=workspace, structured=True)
    extend_unique_paths(
        paths,
        task_contract_candidate_paths(lane_input.task_contract, workspace=workspace),
        workspace=workspace,
        structured=True,
    )
    for result in reversed(tool_results[-8:]):
        if result.status != "completed" or result.is_error:
            continue
        payload = native_result_payload(result)
        extend_unique_paths(
            paths,
            payload_candidate_paths(payload, workspace=workspace),
            workspace=workspace,
            structured=True,
        )
    return tuple(paths[:24])


def task_contract_candidate_paths(task_contract: object, *, workspace: Path) -> tuple[str, ...]:
    if not isinstance(task_contract, Mapping):
        return ()
    paths: list[str] = []
    for key in ("expected_artifact", "expected_artifacts", "artifact", "artifacts"):
        extend_unique_paths(paths, task_contract.get(key), workspace=workspace, structured=True)
    for key in ("verify_command", "description", "guidance"):
        extend_unique_paths(paths, task_contract.get(key), workspace=workspace, structured=False)
    return tuple(paths)


def payload_candidate_paths(payload: Mapping[str, object], *, workspace: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("changed_paths", "path", "target", "file", "output_path"):
        extend_unique_paths(paths, payload.get(key), workspace=workspace, structured=True)
    typed = payload.get("typed_source_mutation") if isinstance(payload.get("typed_source_mutation"), Mapping) else {}
    extend_unique_paths(paths, typed.get("changed_paths"), workspace=workspace, structured=True)
    card = payload.get("mutation_output_card") if isinstance(payload.get("mutation_output_card"), Mapping) else {}
    extend_unique_paths(paths, card.get("changed_paths"), workspace=workspace, structured=True)
    for key in (
        "cwd",
        "command",
        "stdout",
        "stderr",
        "stdout_tail",
        "stderr_tail",
    ):
        extend_unique_paths(paths, payload.get(key), workspace=workspace, structured=False)
    return tuple(paths)


def extract_paths_from_value(value: object, *, workspace: Path, structured: bool) -> tuple[str, ...]:
    found: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key in ("path", "target", "file", "output_path", "name", "command", "cmd"):
                visit(item.get(key))
            return
        if isinstance(item, (list, tuple)):
            for child in item:
                visit(child)
            return
        if not isinstance(item, str):
            return
        if structured:
            cleaned = normalize_finish_verifier_candidate_path(item, workspace=workspace, structured=True)
            if cleaned:
                found.append(cleaned)
            return
        for match in _PATH_LIKE_TOKEN_RE.findall(item):
            cleaned = normalize_finish_verifier_candidate_path(match, workspace=workspace, structured=False)
            if cleaned:
                found.append(cleaned)

    visit(value)
    return tuple(dict.fromkeys(found))


def extend_unique_paths(paths: list[str], value: object, *, workspace: Path, structured: bool = False) -> None:
    for path in extract_paths_from_value(value, workspace=workspace, structured=structured):
        if path not in paths:
            paths.append(path)


def normalize_finish_verifier_candidate_path(path: str, *, workspace: Path, structured: bool) -> str:
    path = path.strip().strip("'\"`.,:;()[]{}")
    if not path or len(path) > 240:
        return ""
    if path in {".", "..", "/", "/tmp", "/app"}:
        return ""
    if path.startswith(("http://", "https://", "file://")):
        return ""
    if "\x00" in path or "\n" in path or "\r" in path:
        return ""
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        try:
            normalized = candidate.resolve(strict=False).relative_to(workspace).as_posix()
        except ValueError:
            normalized = candidate.as_posix()
    else:
        normalized = Path(path).as_posix()
    if normalized in {".", "..", "/", "/tmp", "/app"}:
        return ""
    if normalized.startswith("../") or normalized == "..":
        return ""
    if structured:
        return normalized
    return normalized if any(char in normalized for char in ("/", ".")) or normalized.startswith("/tmp/") else ""


def finish_verifier_planner_forbidden_tool_attempts(
    value: object,
    policy: FinishVerifierPlannerLoopPolicy,
) -> tuple[str, ...]:
    attempts = finish_verifier_planner_tool_names(value)
    if not attempts:
        return ()
    allowed = set(policy.allowed_tools)
    blockers: list[str] = []
    for tool_name in attempts:
        if tool_name not in allowed:
            blockers.append(f"planner_forbidden_tool:{tool_name}")
    return tuple(dict.fromkeys(blockers))


def finish_verifier_planner_tool_names(value: object) -> tuple[str, ...]:
    names: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            candidate = item.get("tool_name") or item.get("name") or item.get("tool") or item.get("function_name")
            if isinstance(candidate, str) and candidate.strip():
                names.append(candidate.strip())
            for key in ("tool_calls", "tool_call", "function_call", "calls", "actions"):
                nested = item.get(key)
                if isinstance(nested, (list, tuple)):
                    for child in nested:
                        visit(child)
                elif isinstance(nested, Mapping):
                    visit(nested)
            function = item.get("function")
            if isinstance(function, Mapping):
                visit(function)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return tuple(dict.fromkeys(names))


def coerce_finish_verifier_plan(
    value: object,
    *,
    request: Mapping[str, object] | None = None,
) -> FinishVerifierPlan | None:
    return coerce_finish_verifier_plan_with_diagnostics(value, request=request).plan


def coerce_finish_verifier_plan_with_diagnostics(
    value: object,
    *,
    request: Mapping[str, object] | None = None,
) -> FinishVerifierPlanCoercion:
    if not isinstance(value, Mapping):
        return FinishVerifierPlanCoercion(
            plan=None,
            status="rejected",
            reject_reason="planner output was not a JSON object",
            reject_blockers=("planner_plan_not_mapping",),
        )
    command = str(value.get("command") or value.get("cmd") or "").strip()
    safety = finish_verifier_command_safety(
        command,
        request=request,
        require_observable_assertions=False,
    )
    if not safety.allowed:
        return FinishVerifierPlanCoercion(
            plan=None,
            status="rejected",
            reject_reason=safety.reason,
            reject_blockers=safety.blockers,
        )
    cwd = str(value.get("cwd") or ".").strip() or "."
    if "\x00" in cwd or "\n" in cwd:
        cwd = "."
    return FinishVerifierPlanCoercion(
        plan=FinishVerifierPlan(
            command=command,
            cwd=cwd,
            source="finish_verifier_planner",
            reason=str(value.get("reason") or value.get("rationale") or "").strip(),
            confidence=str(value.get("confidence") or "").strip(),
            raw=dict(value),
        ),
        status="accepted",
    )


def finish_verifier_command_safe(
    command: object,
    *,
    request: Mapping[str, object] | None = None,
) -> bool:
    return finish_verifier_command_safety(command, request=request).allowed


def finish_verifier_command_safety(
    command: object,
    *,
    request: Mapping[str, object] | None = None,
    require_observable_assertions: bool = True,
) -> FinishVerifierCommandSafetyResult:
    text = str(command or "").strip()
    validation = validate_closeout_command(
        FinishCloseoutCommand(command=text, source="finish_verifier_planner"),
        NativeFinishGatePolicy(allowed_sources=("finish_verifier_planner",)),
    )
    requirements = finish_verifier_observable_requirements(request)
    if not validation.allowed:
        mapped_blockers = tuple(planner_safety_blocker(blocker) for blocker in validation.blockers)
        if (
            set(mapped_blockers) == {"finish_verifier_weak_assertion"}
            and finish_verifier_command_asserts_observables(text, requirements)
        ):
            validation = FinishCloseoutCommandValidation(
                allowed=True,
                command=validation.command,
                reason="nontrivial observable assertion command",
            )
        else:
            return FinishVerifierCommandSafetyResult(
                allowed=False,
                reason=validation.reason,
                blockers=mapped_blockers,
            )
    if (
        require_observable_assertions
        and requirements
        and not finish_verifier_command_asserts_observables(text, requirements)
    ):
        return FinishVerifierCommandSafetyResult(
            allowed=False,
            reason="finish verifier command does not assert required task-visible observables",
            blockers=("finish_verifier_observable_assertions_missing",),
        )
    if _FINISH_VERIFIER_GENERIC_TEST_RE.search(text):
        return FinishVerifierCommandSafetyResult(allowed=True, reason="generic test command")
    if request is None:
        return FinishVerifierCommandSafetyResult(allowed=True, reason="no request subject to check")
    if not finish_verifier_command_mentions_task_subject(text, request):
        return FinishVerifierCommandSafetyResult(
            allowed=False,
            reason="finish verifier command does not mention a task subject",
            blockers=("finish_verifier_task_subject_missing",),
        )
    return FinishVerifierCommandSafetyResult(allowed=True, reason="mentions task subject")


def finish_verifier_observable_requirements(request: Mapping[str, object] | None) -> tuple[str, ...]:
    if not isinstance(request, Mapping):
        return ()
    command_policy = request.get("command_policy")
    if isinstance(command_policy, Mapping):
        explicit = command_policy.get("observable_requirements")
        if isinstance(explicit, (list, tuple)):
            values = tuple(str(item).strip() for item in explicit if str(item).strip())
            if values:
                return tuple(dict.fromkeys(values))
    requirements: list[str] = []
    task = request.get("task")
    task_contract: Mapping[str, object] = {}
    task_text = ""
    if isinstance(task, Mapping):
        task_text = str(task.get("description") or "")
        contract = task.get("contract")
        if isinstance(contract, Mapping):
            task_contract = contract
    haystack = " ".join(
        item
        for item in (
            task_text,
            json.dumps(json_safe_native(task_contract), ensure_ascii=False, sort_keys=True),
            json.dumps(json_safe_native(request.get("recent_tool_results") or ()), ensure_ascii=False, sort_keys=True),
        )
        if item
    )
    if _FINISH_VERIFIER_STDOUT_REQUIREMENT_RE.search(haystack):
        requirements.append("stdout")
    if _FINISH_VERIFIER_STDERR_REQUIREMENT_RE.search(haystack):
        requirements.append("stderr")
    if _FINISH_VERIFIER_IMAGE_REQUIREMENT_RE.search(haystack):
        requirements.append("image_artifact")
    if _FINISH_VERIFIER_FILE_REQUIREMENT_RE.search(haystack):
        requirements.append("file_artifact")
    if isinstance(task_contract, Mapping):
        for key in ("expected_artifact", "expected_artifacts", "artifact", "artifacts"):
            if task_contract.get(key) not in (None, "", [], (), {}):
                requirements.append("file_artifact")
                break
    return tuple(dict.fromkeys(requirements))


def finish_verifier_command_asserts_observables(command: str, requirements: tuple[str, ...]) -> bool:
    if not requirements:
        return finish_verifier_nontrivial_test_command(command)
    if _FINISH_VERIFIER_GENERIC_TEST_RE.search(command):
        return True
    if _FINISH_VERIFIER_ASSERTION_COMMAND_RE.search(command):
        return True
    if finish_verifier_nontrivial_test_command(command) and any(
        item in {"file_artifact", "image_artifact"} for item in requirements
    ):
        return True
    return False


def finish_verifier_nontrivial_test_command(command: str) -> bool:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0] == "[" and tokens[-1:] == ["]"]:
        tokens = ["test", *tokens[1:-1]]
    if tokens[0] != "test":
        return False
    if len(tokens) < 3:
        return False
    expression = tokens[1:]
    joined = " ".join(expression).strip()
    if joined in {"1 = 1", "1 == 1"}:
        return False
    file_predicates = {"-e", "-f", "-s", "-r", "-x", "-d"}
    if any(token in file_predicates for token in expression):
        return any(_PATH_LIKE_TOKEN_RE.search(token) for token in expression if token not in file_predicates)
    return any(_PATH_LIKE_TOKEN_RE.search(token) for token in expression)


def planner_safety_blocker(blocker: str) -> str:
    return {
        "closeout_verifier_command_missing": "finish_verifier_command_empty",
        "closeout_command_empty": "finish_verifier_command_empty",
        "closeout_command_noop_success": "finish_verifier_noop_success",
        "closeout_command_self_acceptance": "finish_verifier_self_acceptance_marker",
        "closeout_command_weak_assertion": "finish_verifier_weak_assertion",
        "closeout_command_inline_program": "finish_verifier_inline_evaluator",
        "closeout_command_shell_disallowed": "finish_verifier_shell_disallowed",
        "closeout_command_source_mutation": "finish_verifier_mutating_command",
        "closeout_command_package_install": "finish_verifier_package_install",
        "closeout_command_network": "finish_verifier_network",
        "closeout_command_privileged": "finish_verifier_privileged",
        "closeout_command_background": "finish_verifier_background_process",
        "closeout_command_redirection": "finish_verifier_redirection",
        "closeout_command_chain": "finish_verifier_shell_composition",
        "closeout_command_secret": "finish_verifier_secret",
        "closeout_command_multiline": "finish_verifier_command_newline",
    }.get(blocker, blocker)


def record_finish_verifier_planner_decision(provider: object, record: Mapping[str, object]) -> None:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, None)
    if not isinstance(existing, list):
        existing = []
        try:
            setattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, existing)
        except Exception:
            return
    existing.append(dict(record))


def record_finish_verifier_planner_request(
    provider: object,
    request: Mapping[str, object],
    *,
    request_hash: str,
) -> None:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_REQUESTS_ATTR, None)
    if not isinstance(existing, list):
        existing = []
        try:
            setattr(provider, _FINISH_VERIFIER_PLANNER_REQUESTS_ATTR, existing)
        except Exception:
            return
    existing.append({"request_hash": request_hash, "request": json_safe_native(dict(request))})


def provider_finish_verifier_planner_decisions(provider: object) -> tuple[Mapping[str, object], ...]:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, ())
    if not isinstance(existing, list):
        return ()
    return tuple(item for item in existing if isinstance(item, Mapping))


def provider_finish_verifier_planner_requests(provider: object) -> tuple[Mapping[str, object], ...]:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_REQUESTS_ATTR, ())
    if not isinstance(existing, list):
        return ()
    return tuple(item for item in existing if isinstance(item, Mapping))


def finish_verifier_planner_request_hash(request: Mapping[str, object]) -> str:
    encoded = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def finish_verifier_planner_record_with_authority(
    record: Mapping[str, object],
    request: Mapping[str, object],
) -> dict[str, object]:
    item = dict(record)
    read_policy = request.get("read_policy") if isinstance(request.get("read_policy"), Mapping) else {}
    selection_source = str(read_policy.get("selection_source") or "").strip()
    if selection_source:
        item.setdefault("selection_source", selection_source)
    if "enabled" in read_policy:
        item.setdefault("request_enabled", bool(read_policy.get("enabled")))
    done_candidate_id = str(request.get("done_candidate_id") or "").strip()
    finish_call_id = str(request.get("finish_call_id") or "").strip()
    if done_candidate_id:
        item["done_candidate_id"] = done_candidate_id
        item.pop("finish_call_id", None)
    elif finish_call_id:
        item["finish_call_id"] = finish_call_id
    return item


def finish_verifier_planner_value_hash(value: object) -> str:
    encoded = json.dumps(json_safe_native(value), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def finish_verifier_planner_decision_record(
    *,
    status: str,
    request_hash: str,
    raw_plan: object = _RAW_FINISH_VERIFIER_PLAN_MISSING,
    plan: FinishVerifierPlan | None = None,
    reject_reason: str = "",
    reject_blockers: tuple[str, ...] = (),
    fallback: FinishVerifierPlan | None = None,
    error: str = "",
) -> dict[str, object]:
    record: dict[str, object] = {
        "status": status,
        "request_hash": request_hash,
    }
    if raw_plan is not _RAW_FINISH_VERIFIER_PLAN_MISSING:
        record["raw_plan"] = json_safe_native(raw_plan)
        record["raw_plan_hash"] = finish_verifier_planner_value_hash(raw_plan)
    if plan is not None:
        record["accepted_plan"] = finish_verifier_plan_payload(plan)
    if reject_reason:
        record["reject_reason"] = reject_reason
    if reject_blockers:
        record["reject_blockers"] = list(reject_blockers)
    if error:
        record["error"] = error
    if fallback is not None:
        record["fallback"] = finish_verifier_plan_payload(fallback)
        record["fallback_source"] = fallback.source
    else:
        record["fallback"] = {}
        record["fallback_source"] = ""
    return record


def finish_verifier_plan_with_planner_fallback(
    plan: FinishVerifierPlan | None,
    planner_decision: Mapping[str, object],
) -> FinishVerifierPlan | None:
    if plan is None:
        return None
    raw = dict(plan.raw or {})
    raw["fallback_after_finish_verifier_planner"] = {
        key: value
        for key, value in planner_decision.items()
        if key
        in {
            "status",
            "request_hash",
            "raw_plan",
            "reject_reason",
            "reject_blockers",
            "error",
            "fallback_source",
        }
    }
    return replace(plan, raw=raw)


def finish_verifier_plan_source(plan: FinishVerifierPlan | None) -> str:
    return plan.source if plan is not None else "none"


def finish_verifier_plan_payload(plan: FinishVerifierPlan) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": plan.command,
        "cwd": plan.cwd,
        "source": plan.source,
        "reason": plan.reason,
        "confidence": plan.confidence,
    }
    if plan.raw:
        payload["raw"] = json_safe_native(dict(plan.raw))
    return {key: value for key, value in payload.items() if value not in ("", {}, [], ())}


def write_finish_verifier_planner_artifacts(
    root: Path,
    *,
    proof_manifest_path: Path | None,
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...],
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Path]:
    if not finish_verifier_planner_decisions:
        return {}
    paths: dict[str, Path] = {}
    planner_requests_path: Path | None = None
    if finish_verifier_planner_requests:
        planner_requests_path = root / FINISH_VERIFIER_PLANNER_REQUESTS_FILE
        planner_requests_path.write_text(
            "".join(
                json.dumps(json_safe_native(dict(record)), ensure_ascii=False, sort_keys=True) + "\n"
                for record in finish_verifier_planner_requests
            ),
            encoding="utf-8",
        )
        paths["finish_verifier_planner_requests"] = planner_requests_path
    planner_decisions_path = root / FINISH_VERIFIER_PLANNER_DECISIONS_FILE
    planner_decisions_path.write_text(
        "".join(
            json.dumps(json_safe_native(dict(record)), ensure_ascii=False, sort_keys=True) + "\n"
            for record in finish_verifier_planner_decisions
        ),
        encoding="utf-8",
    )
    paths["finish_verifier_planner_decisions"] = planner_decisions_path
    if proof_manifest_path is not None:
        patch_proof_manifest_with_finish_verifier_planner_decisions(
            proof_manifest_path,
            decision_path=planner_decisions_path,
            records=finish_verifier_planner_decisions,
            request_path=planner_requests_path,
            request_records=finish_verifier_planner_requests,
        )
    return paths


def patch_proof_manifest_with_finish_verifier_planner_decisions(
    manifest_path: Path,
    *,
    decision_path: Path,
    records: tuple[Mapping[str, object], ...],
    request_path: Path | None = None,
    request_records: tuple[Mapping[str, object], ...] = (),
) -> None:
    manifest: dict[str, object] = {}
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
    digest = file_sha256_native(decision_path)
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    manifest["finish_verifier_planner_decisions_ref"] = decision_path.name
    manifest["finish_verifier_planner_decisions_sha256"] = digest
    request_digest = ""
    if request_path is not None:
        request_digest = file_sha256_native(request_path)
        manifest["finish_verifier_planner_requests_ref"] = request_path.name
        manifest["finish_verifier_planner_requests_sha256"] = request_digest
    metrics["finish_verifier_planner_decisions"] = {
        "artifact_ref": decision_path.name,
        "artifact_sha256": digest,
        "decision_count": len(records),
        "accepted_count": sum(1 for record in records if record.get("status") == "accepted"),
        "rejected_count": sum(1 for record in records if record.get("status") == "rejected"),
        "error_count": sum(1 for record in records if record.get("status") == "error"),
        "fallback_count": sum(1 for record in records if record.get("fallback_source")),
    }
    if request_path is not None:
        metrics["finish_verifier_planner_requests"] = {
            "artifact_ref": request_path.name,
            "artifact_sha256": request_digest,
            "request_count": len(request_records),
        }
    manifest["metrics"] = metrics
    manifest_path.write_text(
        json.dumps(json_safe_native(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finish_verifier_command_mentions_task_subject(command: str, request: Mapping[str, object]) -> bool:
    terms = finish_verifier_subject_terms(request)
    if not terms:
        return True
    lowered = command.casefold()
    return any(term in lowered for term in terms)


def finish_verifier_subject_terms(request: Mapping[str, object]) -> tuple[str, ...]:
    haystack = json.dumps(dict(request), ensure_ascii=False, sort_keys=True)
    terms = []
    for match in _FINISH_VERIFIER_SUBJECT_RE.finditer(haystack):
        term = str(match.group(0) or "").strip().casefold()
        if not term or term.startswith("/"):
            continue
        basename = term.rsplit("/", 1)[-1]
        for candidate in (term, basename):
            if len(candidate) >= 4 and candidate not in terms:
                terms.append(candidate)
    for source in finish_verifier_semantic_subject_sources(request):
        for match in _FINISH_VERIFIER_IDENTIFIER_SUBJECT_RE.finditer(source):
            candidate = str(match.group(0) or "").strip().casefold()
            if candidate in _FINISH_VERIFIER_GENERIC_SUBJECT_WORDS:
                continue
            if len(candidate) >= 4 and candidate not in terms:
                terms.append(candidate)
    return tuple(terms[:80])


def finish_verifier_semantic_subject_sources(request: Mapping[str, object]) -> tuple[str, ...]:
    task = request.get("task")
    if not isinstance(task, Mapping):
        return ()
    sources: list[str] = []
    for key in ("description", "goal", "objective"):
        value = task.get(key)
        if isinstance(value, str) and value.strip():
            sources.append(value)
    for key in ("completion_criteria", "legacy_acceptance_constraints"):
        values = task.get(key)
        if isinstance(values, (list, tuple)):
            sources.extend(str(item) for item in values if str(item).strip())
    contract = task.get("contract")
    if isinstance(contract, Mapping):
        for key in ("goal", "objective"):
            value = contract.get(key)
            if isinstance(value, str) and value.strip():
                sources.append(value)
        for key in ("completion_criteria", "acceptance_constraints"):
            values = contract.get(key)
            if isinstance(values, (list, tuple)):
                sources.extend(str(item) for item in values if str(item).strip())
    return tuple(sources)


def finish_verifier_planner_request(
    lane_input: ImplementLaneInput,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "role": "independent_finish_verifier_planner",
        "task": {
            "task_id": lane_input.task_id,
            "description": native_task_description(lane_input),
            "contract": small_jsonable_mapping(lane_input.task_contract),
            "verify_command_source": canonical_native_verify_command_source(
                (lane_input.lane_config or {}).get("verify_command_source")
                or (lane_input.task_contract or {}).get("verify_command_source"),
                default="",
            ),
        },
        "workspace": ".",
        "recent_tool_results": [
            finish_verifier_planner_tool_result_summary(index, result)
            for index, result in enumerate(tool_results[-8:], start=max(1, len(tool_results) - 7))
        ],
        "output_contract": {
            "json_object": True,
            "required": ["command"],
            "optional": ["cwd", "reason", "confidence"],
            "meaning": "one non-mutating command that verifies task completion from the current workspace",
        },
        "forbidden": [
            "Do not trust the implement agent's finish claim.",
            "Do not output echo/printf/true/exit-0 self-acceptance commands.",
            "Do not modify source files.",
            "Return exactly one JSON object.",
        ],
    }


def finish_verifier_planner_tool_result_summary(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    payload = native_result_payload(result)
    return {
        "index": index,
        "tool_name": result.tool_name,
        "status": result.status,
        "exit_code": payload.get("exit_code"),
        "command": str(payload.get("command") or "")[:500],
        "command_intent": str(payload.get("command_intent") or "")[:80],
        "summary": result.natural_result_text(limit=1200),
        "content_refs": list(result.content_refs[:6]),
        "evidence_refs": list(result.evidence_refs[:6]),
    }


def finish_verifier_planner_prompt(request: Mapping[str, object]) -> str:
    return (
        "You are an independent verifier-planner agent for a coding task. "
        "You are not the implementer and must not trust an implementer's finish claim.\n\n"
        "Given the task and recent tool results, return one JSON object describing the smallest "
        "non-mutating terminal command that should verify whether the task is complete.\n\n"
        "Rules:\n"
        "- Return JSON only.\n"
        "- Required key: command.\n"
        "- Optional keys: cwd, reason, confidence.\n"
        "- The command must test the real task outcome, not print a self-acceptance marker.\n"
        "- Do not use echo/printf/true/exit 0 as the verifier.\n"
        "- Prefer task-provided tests, exact verifier commands, build/test commands, or a focused runtime smoke.\n"
        "- If using python -c, keep it read-only and safety-compatible: no import aliases, no from-imports, "
        "no getattr/importlib.import_module/eval/exec/exit, no helper lambdas/functions, no command variables, "
        "and subprocess calls must use literal argv lists.\n"
        "- If no safe verifier exists, return {\"command\":\"\", \"reason\":\"no safe verifier\"}.\n\n"
        "Input:\n"
        f"{json.dumps(dict(request), ensure_ascii=False, sort_keys=True)}"
    )


def native_task_description(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    chunks = [
        str(contract.get("title") or "").strip(),
        str(contract.get("goal") or "").strip(),
        str(contract.get("objective") or "").strip(),
        str(contract.get("description") or "").strip(),
        str(contract.get("guidance") or "").strip(),
        str(contract.get("verify_command") or "").strip(),
    ]
    criteria = contract.get("completion_criteria")
    if isinstance(criteria, list):
        chunks.extend(str(item or "").strip() for item in criteria)
    constraints = contract.get("acceptance_constraints")
    if isinstance(constraints, list):
        chunks.extend(str(item or "").strip() for item in constraints)
    return "\n".join(chunk for chunk in chunks if chunk)


def canonical_native_verify_command_source(value: object, *, default: str = "") -> str:
    text = str(value or "").strip().casefold()
    if text in {"auto", "auto_detected", "auto-detected", "auto_detected_verifier"}:
        return "auto_detected_verifier"
    if text in {"explicit", "configured", "configured_verifier", "manual", "user", "cli", "task", "task_contract"}:
        return "configured_verifier"
    return default


def native_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    if not result.content:
        return {}
    payload = result.content[0]
    if isinstance(payload, Mapping):
        return dict(payload)
    return {}


def small_jsonable_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    allowed = {}
    for key in (
        "title",
        "description",
        "guidance",
        "acceptance_constraints",
        "verify_command",
        "max_wall_seconds",
    ):
        item = value.get(key)
        if item not in (None, ""):
            allowed[key] = item
    return allowed


def json_safe_native(value: object) -> object:
    try:
        json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return repr(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_native(item) for item in value]
    return value


def file_sha256_native(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def lane_attempt_id(lane_input: ImplementLaneInput) -> str:
    return str(lane_input.lane_config.get("lane_attempt_id") or lane_input.task_id or "implement-v2")


def safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def planner_bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


_FINISH_VERIFIER_GENERIC_TEST_RE = re.compile(
    r"(?i)(?:^|[\s;&|()])(?:pytest|npm\s+test|pnpm\s+test|yarn\s+test|cargo\s+test|go\s+test|make\s+(?:test|check)|"
    r"prove|coqc|coqchk|mvn\s+test|gradle\s+test|tox|ruff\s+check|python\s+-m\s+pytest)(?:$|[\s;&|()])"
)
_FINISH_VERIFIER_STDOUT_REQUIREMENT_RE = re.compile(
    r"(?i)\b(?:stdout|standard\s+output|terminal\s+output|expected\s+output|print(?:ed)?\s+output)\b"
)
_FINISH_VERIFIER_STDERR_REQUIREMENT_RE = re.compile(r"(?i)\b(?:stderr|standard\s+error|error\s+output)\b")
_FINISH_VERIFIER_IMAGE_REQUIREMENT_RE = re.compile(
    r"(?i)\b(?:frame|screenshot|image|bitmap)\b|\.(?:bmp|png|jpe?g|ppm|gif|svg)\b"
)
_FINISH_VERIFIER_FILE_REQUIREMENT_RE = re.compile(
    r"(?i)\b(?:expected\s+artifact|artifact\s+path|output\s+file|created\s+file|saved\s+file)\b"
)
_FINISH_VERIFIER_ASSERTION_COMMAND_RE = re.compile(
    r"(?i)(?:^|[\s;&|()])(?:grep|rg|awk|diff|cmp|stat|file|identify|sha(?:1|256)sum|wc)(?:$|[\s;&|()])"
)
_FINISH_VERIFIER_SUBJECT_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])(?:[A-Za-z0-9_.@+-]+/)*[A-Za-z0-9_.@+-]+"
    r"\.(?:py|pyx|pxd|js|ts|tsx|jsx|c|h|cc|cpp|hpp|rs|go|java|rb|php|lua|v|vo|ml|mli|sh|json|toml|yaml|yml|"
    r"txt|md|so|dylib|dll|exe|o|a|bmp|png|jpe?g|ppm|gif|svg)(?![A-Za-z0-9_./-])"
)
_FINISH_VERIFIER_IDENTIFIER_SUBJECT_RE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z][A-Za-z0-9_-]{3,}(?![A-Za-z0-9_-])")
_FINISH_VERIFIER_GENERIC_SUBJECT_WORDS = frozenset(
    {
        "acceptance",
        "address",
        "artifact",
        "artifacts",
        "assert",
        "build",
        "buildable",
        "called",
        "command",
        "complete",
        "completion",
        "contain",
        "contains",
        "create",
        "criteria",
        "expected",
        "exposes",
        "file",
        "files",
        "float",
        "floats",
        "function",
        "host",
        "hosted",
        "hosting",
        "http",
        "https",
        "index",
        "install",
        "installable",
        "installed",
        "localhost",
        "local",
        "locally",
        "must",
        "number",
        "numbers",
        "objective",
        "output",
        "package",
        "possible",
        "prompt",
        "python",
        "required",
        "returns",
        "root",
        "schema",
        "server",
        "should",
        "simple",
        "source",
        "task",
        "test",
        "tests",
        "that",
        "their",
        "this",
        "using",
        "version",
        "with",
    }
)
_PATH_LIKE_TOKEN_RE = re.compile(
    r"(?:/[\w@+.,:=~%/-]+|[\w@+.,:=~%-]+/[\w@+.,:=~%/-]+|"
    r"(?<![A-Za-z0-9_./-])[\w@+.-]+\."
    r"(?:py|pyx|pxd|js|ts|tsx|jsx|c|h|cc|cpp|hpp|rs|go|java|rb|php|lua|v|vo|ml|mli|sh|json|toml|yaml|yml|"
    r"txt|md|so|dylib|dll|exe|o|a|bmp|png|jpe?g|ppm|gif|svg)(?![A-Za-z0-9_./-]))"
)


__all__ = [
    "FinishVerifierCommandSafetyResult",
    "FinishVerifierPlan",
    "FinishVerifierPlanCoercion",
    "FinishVerifierPlannerEligibility",
    "FinishVerifierPlannerLoopPolicy",
    "FinishVerifierPlannerLoopRequest",
    "FinishVerifierPlannerLoopResult",
    "build_finish_verifier_planner_loop_request",
    "coerce_finish_verifier_plan",
    "coerce_finish_verifier_plan_with_diagnostics",
    "finish_verifier_command_safe",
    "finish_verifier_command_safety",
    "finish_verifier_plan_payload",
    "finish_verifier_plan_source",
    "finish_verifier_plan_with_planner_fallback",
    "finish_verifier_planner_prompt",
    "finish_verifier_planner_request_hash",
    "native_finish_verifier_planner_can_run",
    "native_finish_verifier_planner_eligibility",
    "native_finish_verifier_planner_selection_source",
    "provider_finish_verifier_planner_decisions",
    "provider_finish_verifier_planner_requests",
    "record_finish_verifier_planner_decision",
    "record_finish_verifier_planner_request",
    "run_finish_verifier_planner_loop",
    "write_finish_verifier_planner_artifacts",
]
