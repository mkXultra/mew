"""Phase 3 native implement_v2 harness over provider-native transcript items."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import time
from typing import Iterable, Literal, Mapping

from .completion_resolver import (
    CompletionResolver,
    CompletionResolverDecision,
    CompletionResolverInput,
    FinishClaim,
    write_completion_resolver_artifacts,
)
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .native_fake_provider import PHASE3_TRANSPORT_CHANGE, NativeFakeProvider
from .native_finish_gate import (
    FinishCloseoutCommand,
    FinishCloseoutCommandValidation,
    NativeFinishCloseoutResult,
    NativeFinishGateDecision,
    NativeFinishGatePolicy,
    NativeFinishGateRequest,
    decide_native_finish_from_closeout,
    validate_closeout_command,
    write_native_finish_gate_artifacts,
)
from .native_provider_adapter import (
    NativeResponsesStreamParseResult,
    apply_previous_response_delta,
    build_custom_tool_call_output_input_item,
    build_function_call_output_input_item,
    build_responses_request_descriptor,
    call_codex_native_responses,
    call_codex_native_responses_websocket,
)
from .native_sidecar_projection import build_compact_native_sidecar_digest
from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    OUTPUT_ITEM_KINDS,
    native_transcript_hash,
    normalize_codex_response_items,
    validate_native_transcript_pairing,
    write_native_evidence_observation,
    write_native_transcript_artifacts,
)
from .native_workframe_projection import (
    build_native_prompt_input_inventory,
    build_provider_visible_forbidden_fields_report,
)
from .prompt import build_implement_v2_prompt_sections
from .read_runtime import READ_ONLY_TOOL_NAMES, execute_read_only_tool_call
from .tool_harness_contract import (
    build_evidence_ref_index_artifact,
    build_evidence_sidecar_artifact,
    build_tool_result_index_artifact,
    tool_results_jsonl_lines,
    write_jsonl,
)
from .tool_policy import (
    ImplementLaneToolSpec,
    hide_unavailable_write_file_guidance,
    is_hard_runtime_artifact_task,
    list_v2_tool_specs_for_task,
)
from .tool_registry import (
    CODEX_HOT_PATH_PROFILE_ID,
    ToolSurfaceSnapshot,
    build_tool_surface_snapshot,
    tool_surface_profile_id,
)
from .tool_result_renderer import render_observability_record, render_tool_result_for_profile
from .tool_routes import route_records_from_results, with_tool_route_decision
from .types import ImplementLaneInput, ImplementLaneResult, ToolCallEnvelope, ToolResultEnvelope
from .v2_runtime import (
    _acceptance_session_from_tool_results,
    _finish_acceptance_action,
)
from .. import codex_api as _codex_api
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime
from ..acceptance import (
    acceptance_done_gate_decision,
    implementation_contract_source_requirements,
    implementation_source_ref_matches_text,
)
from ..config import DEFAULT_CODEX_REASONING_EFFORT
from ..prompt_sections import render_prompt_sections


PHASE3_NATIVE_TOOL_HARNESS_ID = "phase3_native_tool_harness_with_fake_provider"
PHASE3_NATIVE_SURFACE = {
    "phase": "3",
    "name": "Native Tool Harness Loop With Fake Provider",
    "transport_change": PHASE3_TRANSPORT_CHANGE,
    "transport_kind": "fake_native",
    "native_transport_kind": "provider_native",
    "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    "provider_native_tool_loop": True,
    "model_json_main_path_detected": False,
}
_FIRST_WRITE_DUE_PROBE_THRESHOLD = 10
_FIRST_WRITE_DUE_TURN_THRESHOLD = 6
_FIRST_WRITE_DUE_GRACE_PROBE_CALLS = 1
_PROCESS_LIFECYCLE_TOOL_NAMES = frozenset({"poll_command", "cancel_command", "read_command_output"})
_PREWRITE_PROBE_PLATEAU_THRESHOLD = 30
_FIRST_WRITE_DUE_HARD_RUNTIME_PROBE_THRESHOLD = 18
# Hard-runtime tasks often need a long source/binary probe pass before a coherent patch.
# Do not force first write by turn count; use probe evidence to carry the guardrail.
_FIRST_WRITE_DUE_HARD_RUNTIME_TURN_THRESHOLD = 10_000
_FAILED_VERIFIER_REPAIR_PROBE_THRESHOLD = 2
_CONTROL_FAILURE_SUMMARY_LIMIT = 700
_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS = 1.0
_NATIVE_MODEL_TIMEOUT_RESERVE_SECONDS = 10.0
_NATIVE_MODEL_TIMEOUT_MIN_SECONDS = 30.0
_FINISH_VERIFIER_PLANNER_DECISIONS_ATTR = "_mew_finish_verifier_planner_decisions"
_FINISH_VERIFIER_PLANNER_DECISIONS_FILE = "finish_verifier_planner_decisions.jsonl"
_FINISH_VERIFIER_PLANNER_REQUESTS_ATTR = "_mew_finish_verifier_planner_requests"
_FINISH_VERIFIER_PLANNER_REQUESTS_FILE = "finish_verifier_planner_requests.jsonl"
_RAW_FINISH_VERIFIER_PLAN_MISSING = object()
_SOURCE_MUTATION_COMMAND_INTENTS = frozenset(
    {"implement", "implementation", "write", "edit", "mutation", "source_mutation"}
)
_COMMAND_RUN_ID_RE = re.compile(
    r"(?:^|[\s;,])command_run_id=(?P<id>[^\s;,]+)"
    r"|Process running with session ID (?P<session>[^\s]+)"
)
_COMMAND_OUTPUT_REF_RE = re.compile(r"implement-v2-exec://[^/\s]+/(?P<id>[^/\s]+)/output")
_TASK_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./\\:-])(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:js|mjs|cjs|ts|tsx|jsx|py|pyx|c|h|cc|cpp|hpp|rs|go|java|sh|rb|php|pl|lua|json|yaml|yml|toml|md|txt|html|css|"
    r"wasm|bin|out|so|dylib|exe|png|ppm|bmp|jpg|jpeg|gif|svg))"
    r"(?![\w.-])"
)
_SOURCE_FACT_NESTED_MATCH_MAX_DEPTH = 8
_SOURCE_FACT_NESTED_MATCH_MAX_DIRS = 256
_SEMANTIC_VERIFIER_FAILURE_PATTERNS = (
    re.compile(r"\bvm\s+(?:finished|stopped)\s+exit=(?!0\b)\d+\b", re.IGNORECASE),
    re.compile(r"\bmissing\s+expected\s+(?:artifact|frame|output)\b", re.IGNORECASE),
    re.compile(
        r"\bexpected\s+(?:artifact|frame|output)\s+(?:missing|not\s+found|not\s+created|not\s+produced)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bno\s+(?:artifact|frame|output)\s+produced\b", re.IGNORECASE),
)


class InvalidNativeTranscriptError(ValueError):
    """Raised when the native transcript itself violates pairing invariants."""


@dataclass(frozen=True)
class NativeImplementV2HarnessResult:
    status: str
    transcript: NativeTranscript
    proof_artifacts: tuple[str, ...]
    metrics: dict[str, object]
    finish_summary: str = ""

    def as_lane_result(self) -> ImplementLaneResult:
        return ImplementLaneResult(
            status=self.status,
            lane="implement_v2",
            user_visible_summary=self.finish_summary,
            proof_artifacts=self.proof_artifacts,
            metrics=self.metrics,
        )


@dataclass(frozen=True)
class _NativeCloseoutEvent:
    kind: str
    call: NativeTranscriptItem
    result: ToolResultEnvelope
    latency: dict[str, object]
    reason: str


@dataclass(frozen=True)
class _NativeCloseoutContext:
    closeout_refs: tuple[str, ...] = ()
    fresh_verifier_refs: tuple[str, ...] = ()
    planner_verified_finish_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    unsafe_blockers: tuple[str, ...] = ()
    budget_blockers: tuple[str, ...] = ()

    def merge(self, other: "_NativeCloseoutContext") -> "_NativeCloseoutContext":
        return _NativeCloseoutContext(
            closeout_refs=tuple(dict.fromkeys((*self.closeout_refs, *other.closeout_refs))),
            fresh_verifier_refs=tuple(dict.fromkeys((*self.fresh_verifier_refs, *other.fresh_verifier_refs))),
            planner_verified_finish_refs=tuple(
                dict.fromkeys((*self.planner_verified_finish_refs, *other.planner_verified_finish_refs))
            ),
            blockers=tuple(dict.fromkeys((*self.blockers, *other.blockers))),
            missing_obligations=tuple(dict.fromkeys((*self.missing_obligations, *other.missing_obligations))),
            unsafe_blockers=tuple(dict.fromkeys((*self.unsafe_blockers, *other.unsafe_blockers))),
            budget_blockers=tuple(dict.fromkeys((*self.budget_blockers, *other.budget_blockers))),
        )


@dataclass(frozen=True)
class _NativeFinishVerifierPlan:
    command: str
    cwd: str = "."
    source: str = "configured"
    reason: str = ""
    confidence: str = ""
    raw: Mapping[str, object] | None = None


@dataclass(frozen=True)
class _NativeFinishVerifierPlanCoercion:
    plan: _NativeFinishVerifierPlan | None
    status: str
    reject_reason: str = ""
    reject_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class _FinishVerifierCommandSafetyResult:
    allowed: bool
    reason: str
    blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierPlannerLoopPolicy:
    enabled: bool
    max_turns: int = 3
    max_wall_seconds: float = 30.0
    max_file_reads: int = 12
    max_searches: int = 8
    max_bytes_per_file: int = 20_000
    max_total_read_bytes: int = 120_000
    allowed_tools: tuple[str, ...] = ("inspect_dir", "read_file", "search_text", "glob")
    allowed_roots: tuple[str, ...] = ()


@dataclass(frozen=True)
class FinishVerifierPlannerLoopRequest:
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    task_id: str
    task_description: str
    task_contract: Mapping[str, object]
    latest_mutation: Mapping[str, object]
    recent_tool_results: tuple[Mapping[str, object], ...]
    candidate_paths: tuple[str, ...]
    policy: FinishVerifierPlannerLoopPolicy
    external_verifier_failure: Mapping[str, object] | None = None
    legacy_request: Mapping[str, object] | None = None

    def as_planner_request(self) -> dict[str, object]:
        base = dict(self.legacy_request or {})
        requirement_source = dict(base)
        requirement_source["task"] = {
            "task_id": self.task_id,
            "description": self.task_description,
            "contract": dict(self.task_contract),
        }
        if self.external_verifier_failure:
            requirement_source["external_verifier_failure"] = dict(self.external_verifier_failure)
        base.update(
            {
                "schema_version": 1,
                "component": "FinishVerifierPlannerLoop",
                "role": "independent_read_only_finish_verifier_planner",
                "lane_attempt_id": self.lane_attempt_id,
                "turn_id": self.turn_id,
                "finish_call_id": self.finish_call_id,
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
                    "observable_requirements": list(_finish_verifier_observable_requirements(requirement_source)),
                },
                "output_contract": {
                    "json_object": True,
                    "required": ["status", "command", "cwd", "confidence", "rationale"],
                    "meaning": "one non-mutating command that verifies current task completion",
                },
            }
        )
        if self.external_verifier_failure:
            base["external_verifier_failure"] = dict(self.external_verifier_failure)
        return base


@dataclass(frozen=True)
class FinishVerifierPlannerLoopResult:
    status: Literal["selected", "no_plan", "rejected", "error", "timed_out"]
    plan: _NativeFinishVerifierPlan | None
    record: Mapping[str, object]
    blockers: tuple[str, ...] = ()
    reason: str = ""


@dataclass
class NativeCodexResponsesProvider:
    """Live Codex Responses provider for the native implement_v2 harness."""

    lane_input: ImplementLaneInput
    auth: Mapping[str, object]
    base_url: str
    timeout: float
    provider: str = "openai"
    model: str = ""
    supports_native_tool_calls: bool = True
    progress: object | None = None
    requests: list[dict[str, object]] = None  # type: ignore[assignment]
    responses: list[dict[str, object]] = None  # type: ignore[assignment]
    rejected_responses: list[dict[str, object]] = None  # type: ignore[assignment]
    previous_response_id: str = ""
    previous_logical_input_items: list[dict[str, object]] = None  # type: ignore[assignment]
    previous_response_output_items: list[dict[str, object]] = None  # type: ignore[assignment]
    use_websocket: bool = True
    websocket_session: object | None = None

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []
        if self.responses is None:
            self.responses = []
        if self.rejected_responses is None:
            self.rejected_responses = []
        if self.previous_logical_input_items is None:
            self.previous_logical_input_items = []
        if self.previous_response_output_items is None:
            self.previous_response_output_items = []
        if not self.model:
            self.model = str(self.lane_input.model or "gpt-5.5")

    def next_response(self, request_descriptor: Mapping[str, object]) -> NativeResponsesStreamParseResult | None:
        descriptor = _live_responses_request_descriptor(
            self.lane_input,
            provider=self.provider,
            model=self.model,
            request_descriptor=request_descriptor,
        )
        if isinstance(request_descriptor.get("compact_sidecar_digest"), Mapping):
            descriptor["compact_sidecar_digest"] = dict(request_descriptor["compact_sidecar_digest"])  # type: ignore[index]
        logical_input_items = _mapping_list(dict(descriptor.get("request_body") or {}).get("input"))
        if self.previous_response_id:
            descriptor = apply_previous_response_delta(
                descriptor,
                previous_response_id=self.previous_response_id,
                previous_logical_input_items=self.previous_logical_input_items,
                previous_response_output_items=self.previous_response_output_items,
            )
        inventory = dict(request_descriptor.get("provider_request_inventory") or {})
        suppressed_refresh_count = int(
            descriptor.get("previous_response_suppressed_context_refresh_item_count")
            or 0
        )
        inventory["previous_response_delta_mode"] = descriptor.get(
            "previous_response_delta_mode"
        ) or "none"
        inventory["previous_response_suppressed_context_refresh_item_count"] = (
            suppressed_refresh_count
        )
        inventory["previous_response_leading_refresh_item_count"] = int(
            descriptor.get("previous_response_leading_refresh_item_count") or 0
        )
        digest_wire_visible = bool(
            inventory.get("compact_sidecar_digest_wire_visible", True)
        )
        if suppressed_refresh_count:
            sections = inventory.get("model_visible_sections")
            if isinstance(sections, list):
                visible_sections = [
                    section
                    for section in sections
                    if section != "compact_sidecar_digest"
                ]
                if inventory["previous_response_leading_refresh_item_count"]:
                    visible_sections.append("task_context_refresh")
                inventory["model_visible_sections"] = visible_sections
            inventory["compact_sidecar_digest_wire_visible"] = False
        else:
            inventory["compact_sidecar_digest_wire_visible"] = digest_wire_visible
        descriptor["provider_request_inventory"] = inventory
        descriptor["input_item_count"] = request_descriptor.get("input_item_count")
        descriptor["turn_index"] = request_descriptor.get("turn_index")
        self.requests.append(dict(descriptor))
        _emit_progress(
            self.progress,
            (
                "native_response start "
                f"turn={request_descriptor.get('turn_index')} timeout_seconds={self.timeout}"
            ),
        )
        try:
            lane_attempt_id = str(request_descriptor.get("lane_attempt_id") or "")
            turn_id = f"turn-{request_descriptor.get('turn_index')}"
            if self.use_websocket:
                if self.websocket_session is None:
                    self.websocket_session = _codex_api.CodexResponsesWebSocketSession(
                        auth=self.auth,
                        base_url=self.base_url,
                        timeout=self.timeout,
                        conversation_id=lane_attempt_id,
                    )
                descriptor["transport_kind"] = "provider_native_websocket"
                descriptor["native_transport_kind"] = "provider_native_websocket"
                result = call_codex_native_responses_websocket(
                    auth=self.auth,
                    descriptor=descriptor,
                    base_url=self.base_url,
                    timeout=self.timeout,
                    lane_attempt_id=lane_attempt_id,
                    turn_id=turn_id,
                    websocket_session=self.websocket_session,
                )
            else:
                result = call_codex_native_responses(
                    auth=self.auth,
                    descriptor=descriptor,
                    base_url=self.base_url,
                    timeout=self.timeout,
                    lane_attempt_id=lane_attempt_id,
                    turn_id=turn_id,
                )
        except Exception:
            _emit_progress(self.progress, "native_response failed")
            raise
        _emit_progress(self.progress, "native_response done")
        self.responses.append(result.as_dict())
        if result.status != "completed":
            self.rejected_responses.append(result.as_dict())
            detail = "; ".join(result.errors) or f"status={result.status or 'unknown'}"
            raise RuntimeError(
                "native provider response did not complete before stream ended: "
                f"{detail}; parsed_items={len(result.transcript.items)}"
            )
        if result.errors and not result.transcript.items:
            raise RuntimeError("native provider response failed: " + "; ".join(result.errors or (result.status,)))
        if result.response_id:
            self.previous_response_id = result.response_id
            self.previous_logical_input_items = logical_input_items
            self.previous_response_output_items = _response_output_input_items(
                result.transcript.items
            )
        return result

    def plan_finish_verifier_command(self, request: Mapping[str, object]) -> Mapping[str, object]:
        """Ask a separate planner session for one finish verifier command.

        This deliberately does not reuse the implement loop transcript or
        previous_response_id. The planner is a separate agent whose only job is
        to propose a command contract; the deterministic finish gate still
        decides whether the executed result is acceptable.
        """

        lane_config = self.lane_input.lane_config if isinstance(self.lane_input.lane_config, Mapping) else {}
        model = str(lane_config.get("finish_verifier_planner_model") or self.model or "gpt-5.5")
        timeout = _safe_float(
            lane_config.get("finish_verifier_planner_timeout_seconds"),
            default=min(max(self.timeout, 1.0), 30.0),
        )
        prompt = _finish_verifier_planner_prompt(request)
        return _codex_api.call_codex_json(
            self.auth,
            prompt,
            model,
            self.base_url,
            timeout,
        )


def run_live_native_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    model_auth: Mapping[str, object],
    base_url: str = "",
    timeout: float = 60.0,
    max_turns: int = 10,
    progress=None,
) -> ImplementLaneResult:
    """Run implement_v2 through live provider-native Responses tool calls."""

    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth=model_auth,
        base_url=base_url,
        timeout=timeout,
        model=str(lane_input.model or "gpt-5.5"),
        progress=progress,
    )
    artifact_root = _artifact_root(lane_input)
    try:
        result = run_native_implement_v2(
            lane_input,
            provider=provider,  # type: ignore[arg-type]
            artifact_root=artifact_root,
            max_turns=max_turns,
        )
    except InvalidNativeTranscriptError:
        raise
    except Exception as exc:
        return _live_failure_lane_result(lane_input, error=str(exc), provider=provider)
    lane_result = result.as_lane_result()
    lane_result.metrics.update(
        {
            "transport_kind": "provider_native",
            "native_transport_kind": "provider_native_websocket"
            if provider.use_websocket
            else "provider_native",
            "provider": provider.provider,
            "model": provider.model,
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
        }
    )
    return lane_result


def run_native_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    provider: NativeFakeProvider,
    artifact_root: str | Path | None = None,
    max_turns: int = 8,
) -> NativeImplementV2HarnessResult:
    """Run the Phase 3 native fake-provider harness.

    This is a native transcript/runtime entry point only; it is intentionally
    not registered as the live CLI route in Phase 3.
    """

    if not provider.supports_native_tool_calls:
        return _unavailable_result(lane_input, provider=provider)

    lane_attempt_id = _lane_attempt_id(lane_input)
    workspace = Path(str(lane_input.workspace or ".")).expanduser().resolve(strict=False)
    lane_config = dict(lane_input.lane_config)
    allowed_read_roots = tuple(str(root) for root in lane_config.get("allowed_read_roots") or (str(workspace),))
    allowed_write_roots = tuple(str(root) for root in lane_config.get("allowed_write_roots") or (str(workspace),))
    exec_runtime = ImplementV2ManagedExecRuntime(
        workspace=workspace,
        allowed_roots=allowed_read_roots,
        allow_shell=bool(lane_config.get("allow_shell")),
        run_command_available=bool(lane_config.get("allow_shell") or lane_config.get("run_command_available")),
        source_write_tools_available=_native_tool_available("write_file", lane_input=lane_input, lane_config=lane_config),
        task_contract=dict(lane_input.task_contract),
        source_mutation_roots=tuple(str(root) for root in lane_config.get("source_mutation_roots") or (str(workspace),)),
        allowed_write_roots=allowed_write_roots,
        approved_write_calls=_approved_write_calls(lane_config),
        auto_approve_writes=bool(lane_config.get("auto_approve_writes")),
        allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
        artifact_dir=lane_config.get("artifact_dir"),
    )
    write_runtime = ImplementV2WriteRuntime(
        workspace=workspace,
        allowed_write_roots=allowed_write_roots,
        approved_write_calls=_approved_write_calls(lane_config),
        allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
        artifact_dir=lane_config.get("artifact_dir"),
    )

    items: list[NativeTranscriptItem] = []
    tool_calls: list[NativeTranscriptItem] = []
    tool_results: list[ToolResultEnvelope] = []
    tool_latencies: list[dict[str, object]] = []
    first_write_metric: dict[str, object] | None = None
    first_verifier_metric: dict[str, object] | None = None
    final_verifier_closeout_count = 0
    final_verifier_closeout_reason = ""
    final_verifier_closeout_provider_call_id = ""
    active_command_closeout_count = 0
    active_command_closeout_reason = ""
    active_command_closeout_provider_call_id = ""
    finish_gate_block_count = 0
    finish_gate_decision: dict[str, object] = {}
    no_tool_continuation_count = 0
    latest_no_tool_continuation: dict[str, object] = {}
    resolver_decisions: list[CompletionResolverDecision] = []
    native_finish_gate_decisions: list[NativeFinishGateDecision] = []
    native_model_budget_block: dict[str, object] | None = None
    start_monotonic = time.monotonic()
    status = "blocked"
    finish_summary = ""
    resolver = CompletionResolver()

    def append_closeout_event(closeout_event: _NativeCloseoutEvent) -> None:
        nonlocal active_command_closeout_count
        nonlocal active_command_closeout_reason
        nonlocal active_command_closeout_provider_call_id
        nonlocal final_verifier_closeout_count
        nonlocal final_verifier_closeout_reason
        nonlocal final_verifier_closeout_provider_call_id
        nonlocal first_verifier_metric

        if closeout_event.kind == "active_command":
            active_command_closeout_count += 1
            active_command_closeout_reason = closeout_event.reason
            active_command_closeout_provider_call_id = closeout_event.call.call_id
        elif closeout_event.kind == "final_verifier":
            final_verifier_closeout_count += 1
            final_verifier_closeout_reason = closeout_event.reason
            final_verifier_closeout_provider_call_id = closeout_event.call.call_id
        items.append(replace(closeout_event.call, sequence=len(items) + 1))
        items.append(
            replace(
                _native_output_from_result(
                    closeout_event.call,
                    closeout_event.result,
                    sequence=0,
                    lane_input=lane_input,
                    lane_config=lane_config,
                ),
                sequence=len(items) + 1,
            )
        )
        tool_calls.append(closeout_event.call)
        tool_results.append(closeout_event.result)
        tool_latencies.append(closeout_event.latency)
        if first_verifier_metric is None and _result_is_verifier_like(closeout_event.result):
            first_verifier_metric = {
                "turn_index": _turn_number(closeout_event.call.turn_id),
                "call_id": closeout_event.call.call_id,
                "tool_name": closeout_event.call.tool_name,
                "wall_seconds": closeout_event.latency["started_ms"] / 1000,
            }

    for turn_index in range(1, max_turns + 1):
        turn_timeout = _native_next_model_timeout_seconds(
            lane_input,
            run_started=start_monotonic,
            requested_timeout=getattr(provider, "timeout", None),
        )
        if turn_timeout is not None:
            if turn_timeout < _NATIVE_MODEL_TIMEOUT_MIN_SECONDS:
                active_closeout = _native_active_command_closeout(
                    lane_input,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    exec_runtime=exec_runtime,
                    start_monotonic=start_monotonic,
                )
                if active_closeout is not None:
                    active_call, active_result, active_latency = active_closeout
                    append_closeout_event(
                        _NativeCloseoutEvent(
                            kind="active_command",
                            call=active_call,
                            result=active_result,
                            latency=active_latency,
                            reason="native active command closeout ran before low-budget provider turn",
                        )
                    )
                    final_closeout = None
                    if active_result.status == "completed" and not _native_active_command_run_id(exec_runtime):
                        final_closeout = _native_final_verifier_closeout(
                            lane_input,
                            lane_attempt_id=lane_attempt_id,
                            provider=provider,
                            exec_runtime=exec_runtime,
                            workspace=workspace,
                            allowed_read_roots=allowed_read_roots,
                            allowed_write_roots=allowed_write_roots,
                            lane_config=lane_config,
                            tool_calls=tuple(tool_calls),
                            tool_results=tuple(tool_results),
                            start_monotonic=start_monotonic,
                        )
                    if final_closeout is not None:
                        closeout_call, closeout_result, closeout_latency = final_closeout
                        final_event = _NativeCloseoutEvent(
                            kind="final_verifier",
                            call=closeout_call,
                            result=closeout_result,
                            latency=closeout_latency,
                            reason="native final verifier closeout ran after low-budget active command closeout",
                        )
                        append_closeout_event(final_event)
                        closeout_context = _native_closeout_context_from_result(closeout_call, closeout_result)
                        native_decision = _native_finish_gate_decision_from_controller_closeout_event(
                            final_event,
                            lane_input=lane_input,
                            lane_config=lane_config,
                            transcript_items=tuple(items),
                            closeout_context=closeout_context,
                        )
                        finish_gate_decision = native_decision.as_dict()
                        if native_decision.lane_status == "completed":
                            status = "completed"
                            finish_summary = native_decision.reason
                            break
                        if native_decision.lane_status == "blocked_return":
                            status = "blocked"
                            finish_summary = native_decision.reason
                            break
                        status = "blocked"
                        finish_summary = native_decision.reason
                status = "blocked"
                if not finish_summary:
                    finish_summary = "native wall-clock budget exhausted before next provider turn"
                native_model_budget_block = {
                    "failure_class": "native_model_budget_insufficient",
                    "turn_index": turn_index,
                    "active_model_timeout_seconds": round(max(0.0, turn_timeout), 3),
                    "minimum_required_model_timeout_seconds": _NATIVE_MODEL_TIMEOUT_MIN_SECONDS,
                }
                break
            if hasattr(provider, "timeout"):
                provider.timeout = turn_timeout
        turn_entry_loop_signals = _native_loop_control_state(
            items,
            current_turn_index=turn_index,
            lane_input=lane_input,
        )
        request_descriptor = _request_descriptor(
            lane_input=lane_input,
            lane_attempt_id=lane_attempt_id,
            turn_index=turn_index,
            transcript_items=items,
            loop_signals=turn_entry_loop_signals,
        )
        try:
            response = provider.next_response(request_descriptor)
        except Exception as exc:
            if not items:
                raise
            return _partial_failure_harness_result(
                lane_input,
                lane_attempt_id=lane_attempt_id,
                provider=provider,
                items=items,
                tool_results=tuple(tool_results),
                artifact_root=artifact_root,
                error=str(exc),
            )
        if response is None:
            break

        if isinstance(response, NativeResponsesStreamParseResult):
            turn_source_items = response.transcript.items
        else:
            normalized = normalize_codex_response_items(
                response.items,
                lane_attempt_id=lane_attempt_id,
                provider=provider.provider,
                model=provider.model,
                turn_id=f"turn-{turn_index}",
            )
            turn_source_items = normalized.items
        turn_items = _renumber_items(turn_source_items, start_sequence=len(items) + 1)
        items.extend(turn_items)

        calls = sorted(
            (item for item in turn_items if item.kind in CALL_ITEM_KINDS),
            key=lambda item: (item.output_index, item.sequence),
        )
        if not calls and _native_turn_has_assistant_message(turn_items):
            continuation = _native_no_tool_continuation_item(
                turn_items,
                lane_attempt_id=lane_attempt_id,
                provider=provider.provider,
                model=provider.model,
                turn_index=turn_index,
                sequence=len(items) + 1,
                latest_resolver_decision=resolver_decisions[-1] if resolver_decisions else None,
            )
            items.append(continuation)
            no_tool_continuation_count += 1
            latest_no_tool_continuation = {
                "turn_index": turn_index,
                "assistant_text": _native_first_assistant_text(turn_items),
                "continuation": continuation.output_text_or_ref,
            }
            finish_summary = finish_summary or "native model returned assistant text without a tool call; continuation requested"
            continue
        accepted_finish: NativeTranscriptItem | None = None
        terminal_blocked_finish: NativeTranscriptItem | None = None
        output_records: list[NativeTranscriptItem] = []
        for call in calls:
            if accepted_finish is not None and _call_order_key(call) > _call_order_key(accepted_finish):
                output_records.append(
                    replace(
                        _native_output_from_result(
                            call,
                            _invalid_result(
                                call,
                                reason=(
                                    f"cancelled because finish call {accepted_finish.call_id} "
                                    "completed earlier in the same response"
                                ),
                            ),
                            sequence=0,
                            lane_input=lane_input,
                            lane_config=lane_config,
                        ),
                        status="synthetic_error",
                    )
                )
                continue
            if terminal_blocked_finish is not None and _call_order_key(call) > _call_order_key(terminal_blocked_finish):
                output_records.append(
                    replace(
                        _native_output_from_result(
                            call,
                            _invalid_result(
                                call,
                                reason=(
                                    "cancelled because finish call "
                                    f"{terminal_blocked_finish.call_id} returned control to supervisor"
                                ),
                            ),
                            sequence=0,
                            lane_input=lane_input,
                            lane_config=lane_config,
                        ),
                        status="synthetic_error",
                    )
                )
                continue

            latency_start = time.monotonic()
            result = _execute_native_call(
                call,
                lane_input=lane_input,
                workspace=workspace,
                allowed_read_roots=allowed_read_roots,
                allowed_write_roots=allowed_write_roots,
                lane_config=lane_config,
                exec_runtime=exec_runtime,
                write_runtime=write_runtime,
                prior_tool_results=tuple(tool_results),
            )
            if call.kind == "finish_call" and not _native_finish_protocol_error(result):
                closeout_events, closeout_context = _run_native_finish_time_closeouts(
                    lane_input,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    exec_runtime=exec_runtime,
                    workspace=workspace,
                    allowed_read_roots=allowed_read_roots,
                    allowed_write_roots=allowed_write_roots,
                    lane_config=lane_config,
                    tool_calls=tuple(tool_calls),
                    tool_results=tuple(tool_results),
                    start_monotonic=start_monotonic,
                )
                for closeout_event in closeout_events:
                    append_closeout_event(closeout_event)
                native_decision = _native_finish_gate_decision_from_closeout_events(
                    call,
                    result,
                    lane_input=lane_input,
                    lane_config=lane_config,
                    transcript_items=tuple(items),
                    request_descriptor=request_descriptor,
                    closeout_events=closeout_events,
                    closeout_context=closeout_context,
                )
                if native_decision is not None:
                    native_finish_gate_decisions.append(native_decision)
                    finish_gate_decision = native_decision.as_dict()
                    result = _finish_result_with_native_finish_gate_decision(result, native_decision)
                else:
                    decision = resolver.resolve(
                        _completion_resolver_input_from_finish(
                            call,
                            result,
                            lane_input=lane_input,
                            transcript_items=tuple(items),
                            request_descriptor=request_descriptor,
                            prior_tool_results=tuple(tool_results),
                            closeout_context=closeout_context,
                        )
                    )
                    resolver_decisions.append(decision)
                    result = _finish_result_with_resolver_decision(result, decision)
                result = with_tool_route_decision(_finish_tool_call_envelope(call, _arguments(call)[0]), result)
            latency_finished = time.monotonic()
            output = _native_output_from_result(
                call,
                result,
                sequence=0,
                lane_input=lane_input,
                lane_config=lane_config,
            )
            output_records.append(output)
            tool_calls.append(call)
            tool_results.append(result)
            tool_latencies.append(
                {
                    "call_id": call.call_id,
                    "tool_name": call.tool_name,
                    "turn_index": turn_index,
                    "queued_ms": 0,
                    "started_ms": round((latency_start - start_monotonic) * 1000, 3),
                    "first_output_ms": round((latency_finished - latency_start) * 1000, 3),
                    "finished_ms": round((latency_finished - latency_start) * 1000, 3),
                }
            )
            if first_write_metric is None and _result_is_write_like(result):
                first_write_metric = {
                    "turn_index": turn_index,
                    "call_id": call.call_id,
                    "tool_name": call.tool_name,
                    "wall_seconds": round(latency_finished - start_monotonic, 6),
                }
            if first_verifier_metric is None and _result_is_verifier_like(result):
                first_verifier_metric = {
                    "turn_index": turn_index,
                    "call_id": call.call_id,
                    "tool_name": call.tool_name,
                    "wall_seconds": round(latency_finished - start_monotonic, 6),
                }
            if call.kind == "finish_call" and _native_finish_gate_blocked(result):
                finish_gate_block_count += 1
                finish_gate_decision = _native_finish_gate_decision_payload(result)
            if call.kind == "finish_call" and _native_finish_authority_lane_status(result) == "completed":
                accepted_finish = call
                status = "completed"
                finish_summary = _finish_summary(call)
            elif call.kind == "finish_call" and _native_finish_authority_lane_status(result) == "blocked_return":
                terminal_blocked_finish = call
                status = "blocked"
                finish_summary = _native_finish_authority_reason(result)

        for output in output_records:
            items.append(replace(output, sequence=len(items) + 1))
        if accepted_finish is not None or terminal_blocked_finish is not None:
            break

    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider.provider,
        model=provider.model,
        items=tuple(items),
    )
    validation = validate_native_transcript_pairing(transcript)
    if not validation.valid:
        raise InvalidNativeTranscriptError(f"invalid native transcript: {', '.join(validation.errors)}")

    finish_verifier_planner_decisions = _provider_finish_verifier_planner_decisions(provider)
    finish_verifier_planner_requests = _provider_finish_verifier_planner_requests(provider)
    metrics = {
        **_native_surface_for_provider(provider),
        "status": status,
        "turn_count": len(provider.requests),
        "provider_request_inventory_available": bool(_provider_request_records(provider)),
        "provider_request_count": len(_provider_request_records(provider)),
        "tool_latency": tuple(tool_latencies),
        "first_write_latency": first_write_metric
        or {"turn_index": None, "call_id": "", "tool_name": "", "wall_seconds": None},
        "first_write_latency_turn": (first_write_metric or {}).get("turn_index"),
        "first_verifier_latency": first_verifier_metric
        or {"turn_index": None, "call_id": "", "tool_name": "", "wall_seconds": None},
        "final_verifier_closeout_count": final_verifier_closeout_count,
        "final_verifier_closeout_reason": final_verifier_closeout_reason,
        "final_verifier_closeout_provider_call_id": final_verifier_closeout_provider_call_id,
        "active_command_closeout_count": active_command_closeout_count,
        "active_command_closeout_reason": active_command_closeout_reason,
        "active_command_closeout_provider_call_id": active_command_closeout_provider_call_id,
        "finish_gate_block_count": finish_gate_block_count,
        "finish_gate_decision": finish_gate_decision,
        "no_tool_continuation_count": no_tool_continuation_count,
        "latest_no_tool_continuation": latest_no_tool_continuation,
        "completion_resolver_decision_count": len(resolver_decisions),
        "completion_resolver_latest_decision": resolver_decisions[-1].as_dict() if resolver_decisions else {},
        "native_finish_gate_decision_count": len(native_finish_gate_decisions),
        "native_finish_gate_latest_decision": (
            native_finish_gate_decisions[-1].as_dict() if native_finish_gate_decisions else {}
        ),
        "finish_verifier_planner_decision_count": len(finish_verifier_planner_decisions),
        "finish_verifier_planner_request_count": len(finish_verifier_planner_requests),
        "finish_verifier_planner_latest_decision": (
            dict(finish_verifier_planner_decisions[-1]) if finish_verifier_planner_decisions else {}
        ),
        "pairing": validation.as_dict(),
    }
    if native_model_budget_block is not None:
        metrics["native_model_turn_budget_block"] = native_model_budget_block
    proof_artifacts: tuple[str, ...] = ()
    if artifact_root is not None:
        paths = _write_native_artifacts(
            Path(artifact_root),
            transcript,
            tool_results=tuple(tool_results),
            provider=provider,
            status=status,
            resolver_decisions=tuple(resolver_decisions),
            native_finish_gate_decisions=tuple(native_finish_gate_decisions),
            finish_verifier_planner_decisions=tuple(finish_verifier_planner_decisions),
            finish_verifier_planner_requests=tuple(finish_verifier_planner_requests),
        )
        proof_artifacts = tuple(str(path) for path in paths.values())
    return NativeImplementV2HarnessResult(
        status=status,
        transcript=transcript,
        proof_artifacts=proof_artifacts,
        metrics=metrics,
        finish_summary=finish_summary,
    )


def run_unavailable_native_implement_v2(lane_input: ImplementLaneInput) -> ImplementLaneResult:
    """Return the production native-v2 unavailable result.

    Phase 5 switches selected v2 away from the legacy model-JSON transport even
    before the live provider-native adapter is wired. This result keeps the
    runtime identity and proof metrics native so command integration cannot
    silently fall back to the old main path.
    """

    provider = NativeFakeProvider.from_item_batches(
        (),
        provider="provider-native-unavailable",
        model=str(lane_input.model or ""),
    )
    lane_attempt_id = _lane_attempt_id(lane_input)
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider.provider,
        model=provider.model,
    )
    return ImplementLaneResult(
        status="unavailable",
        lane="implement_v2",
        user_visible_summary="implement_v2 native transcript loop is selected but live provider transport is not wired yet.",
        proof_artifacts=(),
        updated_lane_state={
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "transport_kind": "provider_native_unavailable",
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
            "requested_task_id": lane_input.task_id,
        },
        next_reentry_hint={
            "reason": "implement_v2_native_provider_not_wired",
            "fallback_lane": "implement_v1",
            "requires_separate_lane_attempt": True,
        },
        metrics={
            **PHASE3_NATIVE_SURFACE,
            "status": "unavailable",
            "transport_kind": "provider_native_unavailable",
            "native_transport_kind": "provider_native",
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "provider": provider.provider,
            "model": provider.model,
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
            "transcript_hash": native_transcript_hash(transcript),
            "unavailable_reason": "live_provider_native_transport_not_wired",
        },
    )


def _execute_native_call(
    call: NativeTranscriptItem,
    *,
    lane_input: ImplementLaneInput,
    workspace: Path,
    allowed_read_roots: tuple[str, ...],
    allowed_write_roots: tuple[str, ...],
    lane_config: Mapping[str, object],
    exec_runtime: ImplementV2ManagedExecRuntime,
    write_runtime: ImplementV2WriteRuntime,
    prior_tool_results: tuple[ToolResultEnvelope, ...] = (),
) -> ToolResultEnvelope:
    if not call.call_id:
        if call.kind == "finish_call":
            return _finish_protocol_error_result(
                _finish_tool_call_envelope(call, {}),
                reason="native finish call is missing call_id",
            )
        return _invalid_result(call, reason="native tool call is missing call_id")
    arguments, error = _arguments(call)
    if error:
        if call.kind == "finish_call":
            return _finish_protocol_error_result(
                _finish_tool_call_envelope(call, {}),
                reason=error,
            )
        return _invalid_result(call, reason=error)
    if call.kind == "finish_call":
        envelope = _finish_tool_call_envelope(call, arguments)
    else:
        envelope = _tool_call_envelope_from_native_call(call, arguments)
    if call.kind == "finish_call":
        return with_tool_route_decision(
            envelope,
            _finish_result(envelope, lane_input=lane_input, prior_tool_results=prior_tool_results),
        )
    if not _native_tool_available(call.tool_name, lane_input=lane_input, lane_config=lane_config):
        return with_tool_route_decision(
            envelope,
            _invalid_result(
                call,
                reason=(
                    f"{call.tool_name} is not available in implement_v2 "
                    f"{str(lane_config.get('mode') or 'full')} mode"
                ),
            ),
        )
    adapted_call, adapted_arguments, adapter_error = _adapt_codex_hot_path_call(
        call,
        arguments,
        lane_input=lane_input,
        lane_config=lane_config,
    )
    if adapter_error:
        return with_tool_route_decision(
            envelope,
            _invalid_result(call, reason=adapter_error),
        )
    provider_envelope = envelope
    if adapted_call is not call or adapted_arguments != arguments:
        envelope = _tool_call_envelope_from_native_call(adapted_call, adapted_arguments)
    if adapted_call.tool_name in READ_ONLY_TOOL_NAMES:
        result = _result_with_provider_tool_name(
            execute_read_only_tool_call(envelope, workspace=workspace, allowed_roots=allowed_read_roots),
            provider_tool_name=call.tool_name,
            internal_tool_name=adapted_call.tool_name,
        )
        return with_tool_route_decision(
            provider_envelope,
            result,
            effective_tool=adapted_call.tool_name,
        )
    if adapted_call.tool_name in EXEC_TOOL_NAMES:
        result = _result_with_provider_tool_name(
            exec_runtime.execute(envelope),
            provider_tool_name=call.tool_name,
            internal_tool_name=adapted_call.tool_name,
        )
        return with_tool_route_decision(
            provider_envelope,
            result,
            effective_tool=adapted_call.tool_name,
        )
    if adapted_call.tool_name in WRITE_TOOL_NAMES:
        if not _side_effect_id_valid(call):
            return with_tool_route_decision(
                provider_envelope,
                _invalid_result(call, reason="side-effecting tool call has invalid provider id"),
            )
        if bool(lane_config.get("auto_approve_writes")):
            write_runtime = ImplementV2WriteRuntime(
                workspace=workspace,
                allowed_write_roots=allowed_write_roots,
                approved_write_calls=(
                    {"status": "approved", "provider_call_id": call.call_id, "source": "phase3-auto"},
                ),
                allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
                artifact_dir=lane_config.get("artifact_dir"),
            )
        result = _result_with_provider_tool_name(
            write_runtime.execute(envelope),
            provider_tool_name=call.tool_name,
            internal_tool_name=adapted_call.tool_name,
        )
        return with_tool_route_decision(
            provider_envelope,
            result,
            effective_tool=adapted_call.tool_name,
        )
    return with_tool_route_decision(
        envelope,
        _invalid_result(call, reason=f"unknown native tool: {call.tool_name}"),
    )


def _result_with_provider_tool_name(
    result: ToolResultEnvelope,
    *,
    provider_tool_name: str,
    internal_tool_name: str,
) -> ToolResultEnvelope:
    if provider_tool_name == internal_tool_name:
        return result
    content = []
    for item in result.content:
        if isinstance(item, Mapping):
            payload = dict(item)
            payload["provider_tool_name"] = provider_tool_name
            payload["internal_kernel"] = internal_tool_name
            if payload.get("tool_name") == internal_tool_name:
                payload["tool_name"] = provider_tool_name
            if payload.get("effective_tool_name") == internal_tool_name:
                payload["effective_tool_name"] = internal_tool_name
            content.append(payload)
        else:
            content.append(item)
    return replace(result, tool_name=provider_tool_name, content=tuple(content))


def _adapt_codex_hot_path_call(
    call: NativeTranscriptItem,
    arguments: Mapping[str, object],
    *,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
) -> tuple[NativeTranscriptItem, dict[str, object], str]:
    if tool_surface_profile_id(lane_config) != CODEX_HOT_PATH_PROFILE_ID:
        return call, dict(arguments), ""
    args = dict(arguments)
    if call.tool_name == "exec_command":
        error = _codex_exec_command_adapter_error(args)
        if error:
            return call, args, error
        mapped = _codex_exec_command_arguments(args, lane_input=lane_input)
        return replace(call, tool_name="run_command"), mapped, ""
    if call.tool_name == "write_stdin":
        chars = str(args.get("chars") or "")
        if chars:
            return call, args, "write_stdin non-empty chars are not supported in poll_only mode"
        session_id = str(args.get("session_id") or args.get("command_run_id") or "").strip()
        if not session_id:
            return call, args, "write_stdin session_id is required"
        mapped = {
            "command_run_id": session_id,
            "wait_seconds": max(0.0, _safe_float(args.get("yield_time_ms"), default=0.0) / 1000.0),
        }
        for key in ("max_output_chars", "max_output_tokens"):
            if args.get(key) not in (None, ""):
                mapped[key] = args[key]
        return replace(call, tool_name="poll_command"), mapped, ""
    if call.tool_name == "list_dir":
        mapped = {
            "path": args.get("path") or ".",
            "max_entries": args.get("max_entries"),
        }
        return replace(call, tool_name="inspect_dir"), mapped, ""
    return call, args, ""


def _codex_exec_command_adapter_error(args: Mapping[str, object]) -> str:
    if args.get("tty") not in (None, "", False):
        return "exec_command adapter error: tty is not supported"
    if args.get("login") not in (None, "", False):
        return "exec_command adapter error: login shells are not supported"
    has_command = any(args.get(key) not in (None, "", []) for key in ("cmd", "command", "argv"))
    if not has_command:
        return "exec_command adapter error: cmd is required"
    return ""


def _codex_exec_command_arguments(
    args: dict[str, object],
    *,
    lane_input: ImplementLaneInput,
) -> dict[str, object]:
    mapped = dict(args)
    if mapped.get("command") in (None, "") and mapped.get("cmd") not in (None, ""):
        mapped["command"] = mapped["cmd"]
    if mapped.get("cwd") in (None, "") and mapped.get("workdir") not in (None, ""):
        mapped["cwd"] = mapped["workdir"]
    if mapped.get("foreground_budget_seconds") in (None, "") and mapped.get("yield_time_ms") not in (None, ""):
        mapped["foreground_budget_seconds"] = max(
            0.0,
            _safe_float(mapped.get("yield_time_ms"), default=0.0) / 1000.0,
        )
    if _matches_verify_command(mapped, lane_input=lane_input):
        mapped.setdefault("command_intent", "verify")
    return mapped


def _matches_verify_command(
    args: Mapping[str, object],
    *,
    lane_input: ImplementLaneInput,
) -> bool:
    verify_command = str(
        (lane_input.lane_config or {}).get("verify_command")
        or (lane_input.task_contract or {}).get("verify_command")
        or ""
    ).strip()
    if not verify_command:
        return False
    command = str(args.get("command") or args.get("cmd") or "").strip()
    return command == verify_command


def _safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _planner_bounded_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _tool_call_envelope_from_native_call(
    call: NativeTranscriptItem,
    arguments: dict[str, object],
) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name=call.tool_name,
        arguments=arguments,
        provider_message_id=call.provider_item_id,
        turn_index=_turn_number(call.turn_id),
        sequence_index=call.output_index,
        status="validated",
    )


def _native_tool_available(
    tool_name: object,
    *,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
) -> bool:
    if tool_surface_profile_id(lane_config) == CODEX_HOT_PATH_PROFILE_ID:
        try:
            snapshot = build_tool_surface_snapshot(
                lane_config=lane_config,
                task_contract=lane_input.task_contract,
                transcript_items=(),
            )
        except ValueError:
            return False
        return str(tool_name or "") in set(snapshot.provider_tool_names)
    mode = str(lane_config.get("mode") or "full").strip() or "full"
    return str(tool_name or "") in {
        spec.name
        for spec in list_v2_tool_specs_for_task(
            mode,
            task_contract=lane_input.task_contract,
        )
    }


def _run_native_finish_time_closeouts(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: ImplementV2ManagedExecRuntime,
    workspace: Path,
    allowed_read_roots: tuple[str, ...],
    allowed_write_roots: tuple[str, ...],
    lane_config: Mapping[str, object],
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    start_monotonic: float,
) -> tuple[tuple[_NativeCloseoutEvent, ...], _NativeCloseoutContext]:
    events: list[_NativeCloseoutEvent] = []
    context = _NativeCloseoutContext()
    scoped_calls = list(tool_calls)
    scoped_results = list(tool_results)

    active_closeout = _native_active_command_closeout(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        start_monotonic=start_monotonic,
    )
    if active_closeout is not None:
        active_call, active_result, active_latency = active_closeout
        event = _NativeCloseoutEvent(
            kind="active_command",
            call=active_call,
            result=active_result,
            latency=active_latency,
            reason="native active command closeout ran during finish-time resolver evidence collection",
        )
        events.append(event)
        scoped_calls.append(active_call)
        scoped_results.append(active_result)
        context = context.merge(_native_closeout_context_from_result(active_call, active_result))

    pending_mutation = _latest_native_source_mutation_without_later_verifier(
        tuple(scoped_calls),
        tuple(scoped_results),
        source_mutation_roots=_native_source_mutation_roots(lane_input, workspace),
    )
    latest_mutation = pending_mutation or _latest_native_source_mutation(
        tuple(scoped_calls),
        tuple(scoped_results),
        source_mutation_roots=_native_source_mutation_roots(lane_input, workspace),
    )
    if not latest_mutation:
        return tuple(events), context
    no_run_context = _native_final_verifier_closeout_no_run_context(
        lane_input,
        provider=provider,
        tool_results=tuple(scoped_results),
        lane_config=lane_config,
        start_monotonic=start_monotonic,
    )
    if no_run_context is not None:
        return tuple(events), context.merge(no_run_context)

    closeout = _native_final_verifier_closeout(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        workspace=workspace,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        lane_config=lane_config,
        tool_calls=tuple(scoped_calls),
        tool_results=tuple(scoped_results),
        start_monotonic=start_monotonic,
        pending_mutation=latest_mutation,
    )
    if closeout is None:
        return tuple(events), context.merge(
            _NativeCloseoutContext(
                blockers=("closeout_verifier_not_run",),
                missing_obligations=("strict_verifier_evidence",),
            )
        )
    closeout_call, closeout_result, closeout_latency = closeout
    events.append(
        _NativeCloseoutEvent(
            kind="final_verifier",
            call=closeout_call,
            result=closeout_result,
            latency=closeout_latency,
            reason="native final verifier closeout ran during finish-time resolver evidence collection",
        )
    )
    return tuple(events), context.merge(_native_closeout_context_from_result(closeout_call, closeout_result))


def _native_final_verifier_closeout_no_run_context(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    tool_results: tuple[ToolResultEnvelope, ...],
    lane_config: Mapping[str, object],
    start_monotonic: float,
) -> _NativeCloseoutContext | None:
    if not _native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return _NativeCloseoutContext(
            unsafe_blockers=("closeout_verifier_not_permitted",),
            missing_obligations=("strict_verifier_evidence",),
        )
    has_configured = bool(_configured_native_final_verifier_command(lane_input))
    has_planner = _native_finish_verifier_planner_can_run(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    )
    has_auto = _auto_detected_native_final_verifier_command(lane_input) is not None
    if not has_configured and not has_planner and not has_auto:
        return _NativeCloseoutContext(
            blockers=("closeout_verifier_command_missing",),
            missing_obligations=("strict_verifier_evidence",),
        )
    budget = _native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    if budget < _FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        return _NativeCloseoutContext(
            budget_blockers=("closeout_verifier_budget_insufficient",),
            missing_obligations=("strict_verifier_evidence",),
        )
    return None


def _native_closeout_context_from_result(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
) -> _NativeCloseoutContext:
    refs = _native_closeout_refs(call, result)
    if _native_final_verifier_passed(result):
        return _NativeCloseoutContext(
            closeout_refs=refs,
            fresh_verifier_refs=refs,
            planner_verified_finish_refs=refs if _native_call_uses_finish_verifier_planner(call) else (),
        )
    blocker = "closeout_verifier_failed"
    payload = _native_result_payload(result)
    status = str(payload.get("status") or result.status or "").casefold()
    reason_text = result.natural_result_text().casefold()
    if status in {"interrupted", "timeout", "timed_out", "yielded"} or "budget" in reason_text:
        return _NativeCloseoutContext(
            closeout_refs=refs,
            budget_blockers=("closeout_verifier_budget_or_timeout",),
            missing_obligations=("strict_verifier_evidence",),
        )
    return _NativeCloseoutContext(
        closeout_refs=refs,
        blockers=(blocker,),
        missing_obligations=("strict_verifier_evidence",),
    )


def _native_closeout_refs(call: NativeTranscriptItem, result: ToolResultEnvelope) -> tuple[str, ...]:
    refs = tuple(ref for ref in result.evidence_refs if _native_closeout_ref_is_completion_evidence(ref))
    if refs:
        return refs
    return (f"native-closeout://{call.call_id}",)


def _native_call_uses_finish_verifier_planner(call: NativeTranscriptItem) -> bool:
    arguments, error = _arguments(call)
    if error:
        return False
    plan = arguments.get("finish_verifier_plan")
    if not isinstance(plan, Mapping):
        return False
    return str(plan.get("source") or "").strip() == "finish_verifier_planner"


def _native_closeout_ref_is_completion_evidence(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text.startswith("implement-v2-exec://"):
        return True
    if "/command_run/" in text or "/tool_run_record/" in text or "/verifier_evidence/" in text:
        return True
    if "/failure_classification/" in text or "/structured_finish_gate/" in text:
        return False
    return False


_NATIVE_FINISH_RESOLVABLE_CLOSEOUT_BLOCKERS = frozenset(
    {
        "closeout_verifier_command_missing",
        "closeout_verifier_not_run",
    }
)

_NATIVE_EXPLICIT_ACCEPTANCE_PASS_RE = re.compile(
    r"(?im)^\s*(?:acceptance:\s*pass|acceptance_ok|final_acceptance_ok)\b"
)


def _native_finish_supplied_closeout_context(
    refs: tuple[str, ...],
    prior_tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...] = (),
) -> _NativeCloseoutContext:
    cited_refs = tuple(dict.fromkeys(str(ref or "").strip() for ref in refs if str(ref or "").strip()))
    if not cited_refs:
        return _NativeCloseoutContext()
    completion_refs: list[str] = []
    latest_mutation_index = _latest_native_source_mutation_result_index(
        prior_tool_results,
        source_mutation_roots=source_mutation_roots,
    )
    for index, result in enumerate(prior_tool_results, start=1):
        if latest_mutation_index and index < latest_mutation_index:
            continue
        if not _native_prior_result_can_satisfy_verifier_evidence(result):
            continue
        result_completion_refs = _native_completion_refs_from_result(result)
        if not result_completion_refs:
            continue
        if _native_finish_refs_cite_tool_result(cited_refs, result, result_completion_refs):
            completion_refs.extend(result_completion_refs)
    refs_tuple = tuple(dict.fromkeys(completion_refs))
    if not refs_tuple:
        return _NativeCloseoutContext()
    return _NativeCloseoutContext(
        closeout_refs=refs_tuple,
        fresh_verifier_refs=refs_tuple,
    )


def _latest_native_source_mutation_result_index(
    prior_tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> int:
    latest = 0
    for index, result in enumerate(prior_tool_results, start=1):
        if result.status == "completed" and _native_result_has_source_mutation(
            result,
            source_mutation_roots=source_mutation_roots,
        ):
            latest = index
    return latest


def _native_closeout_context_resolved_by_finish_evidence(
    closeout_context: _NativeCloseoutContext,
    finish_context: _NativeCloseoutContext,
) -> _NativeCloseoutContext:
    if not finish_context.fresh_verifier_refs:
        return closeout_context
    merged = closeout_context.merge(finish_context)
    blockers = tuple(
        blocker
        for blocker in merged.blockers
        if blocker not in _NATIVE_FINISH_RESOLVABLE_CLOSEOUT_BLOCKERS
    )
    removed_missing_closeout_blocker = len(blockers) != len(merged.blockers)
    if removed_missing_closeout_blocker:
        missing = tuple(item for item in merged.missing_obligations if item != "strict_verifier_evidence")
    else:
        missing = merged.missing_obligations
    return _NativeCloseoutContext(
        closeout_refs=merged.closeout_refs,
        fresh_verifier_refs=merged.fresh_verifier_refs,
        planner_verified_finish_refs=merged.planner_verified_finish_refs,
        blockers=blockers,
        missing_obligations=missing,
        unsafe_blockers=merged.unsafe_blockers,
        budget_blockers=merged.budget_blockers,
    )


def _native_prior_result_can_satisfy_verifier_evidence(result: ToolResultEnvelope) -> bool:
    verifier_passed = _native_final_verifier_passed(result)
    explicit_acceptance_pass = _native_result_has_explicit_acceptance_pass(result)
    if not verifier_passed and not explicit_acceptance_pass:
        return False
    payload = _native_result_payload(result)
    verifier = payload.get("verifier_evidence")
    if isinstance(verifier, Mapping):
        verdict = str(verifier.get("verdict") or "").casefold()
        if verdict == "pass":
            return True
        if verdict in {"fail", "failed", "partial"}:
            return False
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    if _native_execution_contract_is_verifier_like(contract):
        return True
    if result.tool_name == "run_tests":
        return True
    if str(payload.get("command_intent") or "").strip().casefold() in {
        "verify",
        "verifier",
        "verification",
        "finish_verifier",
        "test",
        "acceptance",
    }:
        return True
    if (
        explicit_acceptance_pass
        and _native_result_has_verifier_evidence_ref(result)
        and _native_result_is_process_lifecycle_continuation(result)
    ):
        return True
    return False


def _native_completion_refs_from_result(result: ToolResultEnvelope) -> tuple[str, ...]:
    refs = (*result.content_refs, *result.evidence_refs)
    return tuple(ref for ref in refs if _native_closeout_ref_is_completion_evidence(ref))


def _native_result_has_explicit_acceptance_pass(result: ToolResultEnvelope) -> bool:
    payload = _native_result_payload(result)
    if result.status != "completed" or result.is_error:
        return False
    if payload.get("exit_code") not in (0, "0"):
        return False
    for key in ("stdout_tail", "stdout", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and _NATIVE_EXPLICIT_ACCEPTANCE_PASS_RE.search(value):
            return True
    return False


def _native_result_has_verifier_evidence_ref(result: ToolResultEnvelope) -> bool:
    refs = " ".join(str(ref or "") for ref in (*result.content_refs, *result.evidence_refs)).casefold()
    return "verifier_evidence" in refs or "/verifier/" in refs


def _native_result_is_process_lifecycle_continuation(result: ToolResultEnvelope) -> bool:
    payload = _native_result_payload(result)
    route = result.route_decision.get("tool_route") if isinstance(result.route_decision, Mapping) else ""
    if str(route or "").strip() == "process_lifecycle" and result.tool_name in {
        "write_stdin",
        "poll_command",
        "cancel_command",
    }:
        return True
    return result.tool_name in {"write_stdin", "poll_command"} or str(
        payload.get("internal_kernel") or payload.get("effective_tool_name") or ""
    ).strip() == "poll_command"


def _native_finish_refs_cite_tool_result(
    refs: tuple[str, ...],
    result: ToolResultEnvelope,
    result_completion_refs: tuple[str, ...],
) -> bool:
    aliases = _native_tool_result_ref_aliases(result)
    result_ref_set = set(result_completion_refs)
    for ref in refs:
        if ref in aliases or ref in result_ref_set:
            return True
    return False


def _native_tool_result_ref_aliases(result: ToolResultEnvelope) -> set[str]:
    aliases: set[str] = set()
    for raw_id in (result.provider_call_id, result.mew_tool_call_id):
        text = str(raw_id or "").strip()
        if not text:
            continue
        aliases.add(text)
        aliases.add(f"ev:tool_result:{text}")
        aliases.add(f"tool-result:{text}")
        aliases.add(f"tool_result:{text}")
        aliases.add(f"tool-route:{text}")
    provider_call_id = str(result.provider_call_id or "").strip()
    if provider_call_id:
        aliases.add(f"native:{provider_call_id}")
    route_ref = result.route_decision.get("ref") if isinstance(result.route_decision, Mapping) else ""
    route_ref_text = str(route_ref or "").strip()
    if route_ref_text:
        aliases.add(route_ref_text)
    return aliases


def _native_active_command_closeout(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: ImplementV2ManagedExecRuntime,
    start_monotonic: float,
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    command_run_id = _native_active_command_run_id(exec_runtime)
    if not command_run_id:
        return None
    budget = _native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    turn_index = len(getattr(provider, "requests", []) or ()) + 1
    call = _native_active_command_closeout_call(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        turn_index=turn_index,
        command_run_id=command_run_id,
        timeout_seconds=budget,
    )
    prior = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name="poll_command",
        status="yielded",
        is_error=False,
        content=({"command_run_id": command_run_id, "status": "yielded"},),
    )
    latency_start = time.monotonic()
    if budget < _FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        payloads = exec_runtime.cancel_active_commands(
            reason="native active command closeout budget exhausted before deterministic final verifier"
        )
    else:
        payloads = exec_runtime.finalize_active_commands(timeout_seconds=budget)
    payload = next(
        (item for item in payloads if str(item.get("command_run_id") or "") == command_run_id),
        payloads[0] if payloads else {"command_run_id": command_run_id, "status": "orphaned"},
    )
    result = with_tool_route_decision(
        _tool_call_envelope_from_native_call(call, {"command_run_id": command_run_id}),
        exec_runtime.project_result_payload(prior, payload),
    )
    latency_finished = time.monotonic()
    latency = {
        "call_id": call.call_id,
        "tool_name": call.tool_name,
        "turn_index": turn_index,
        "queued_ms": 0,
        "started_ms": round((latency_start - start_monotonic) * 1000, 3),
        "first_output_ms": round((latency_finished - latency_start) * 1000, 3),
        "finished_ms": round((latency_finished - latency_start) * 1000, 3),
    }
    return call, result, latency


def _native_active_command_run_id(exec_runtime: ImplementV2ManagedExecRuntime) -> str:
    active = getattr(getattr(exec_runtime, "runner", None), "active", None)
    return str(getattr(active, "command_run_id", "") or "").strip()


def _native_active_command_closeout_call(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    command_run_id: str,
    timeout_seconds: float,
) -> NativeTranscriptItem:
    call_id = f"call-active-command-closeout-{turn_index:03d}"
    arguments = {
        "command_run_id": command_run_id,
        "wait_seconds": round(max(0.0, timeout_seconds), 3),
        "purpose": "finalize active managed command before starting any deterministic final verifier",
    }
    return NativeTranscriptItem(
        sequence=0,
        turn_id=f"turn-{turn_index}-active-command-closeout",
        lane_attempt_id=lane_attempt_id,
        provider=str(getattr(provider, "provider", "") or "native-controller"),
        model=str(getattr(provider, "model", "") or lane_input.model or ""),
        response_id=f"native-active-command-closeout-{turn_index}",
        provider_item_id=f"item-{call_id}",
        output_index=0,
        kind="function_call",
        call_id=call_id,
        tool_name="poll_command",
        arguments_json_text=json.dumps(arguments, sort_keys=True),
    )


def _native_final_verifier_closeout(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: ImplementV2ManagedExecRuntime,
    workspace: Path,
    allowed_read_roots: tuple[str, ...],
    allowed_write_roots: tuple[str, ...],
    lane_config: Mapping[str, object],
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    start_monotonic: float,
    pending_mutation: Mapping[str, object] | None = None,
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    effective_mutation = dict(pending_mutation or {})
    if not effective_mutation:
        effective_mutation = _latest_native_source_mutation_without_later_verifier(
            tool_calls,
            tool_results,
            source_mutation_roots=_native_source_mutation_roots(lane_input, workspace),
        )
    if not effective_mutation:
        effective_mutation = _latest_native_source_mutation(
            tool_calls,
            tool_results,
            source_mutation_roots=_native_source_mutation_roots(lane_input, workspace),
        )
    if not effective_mutation:
        return None
    if not _native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return None
    plan = _native_final_verifier_closeout_plan(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    )
    if plan is None:
        return None
    budget = _native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    if budget < _FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        return None
    turn_index = len(getattr(provider, "requests", []) or ()) + 1
    call = _native_final_verifier_closeout_call(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        turn_index=turn_index,
        lane_config=lane_config,
        plan=plan,
        timeout_seconds=budget,
        pending_mutation=effective_mutation,
    )
    latency_start = time.monotonic()
    result = _execute_native_call(
        call,
        lane_input=lane_input,
        workspace=workspace,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        lane_config=lane_config,
        exec_runtime=exec_runtime,
        write_runtime=ImplementV2WriteRuntime(
            workspace=workspace,
            allowed_write_roots=allowed_write_roots,
            approved_write_calls=(),
            allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
            artifact_dir=lane_config.get("artifact_dir"),
        ),
    )
    if result.status == "yielded":
        finalized = exec_runtime.finalize_active_commands(timeout_seconds=budget)
        for payload in finalized:
            if str(payload.get("command_run_id") or "") == _command_run_id_from_result(result):
                result = with_tool_route_decision(
                    _tool_call_envelope_from_native_call(call, _arguments(call)[0]),
                    exec_runtime.project_result_payload(result, payload),
                )
                break
    latency_finished = time.monotonic()
    latency = {
        "call_id": call.call_id,
        "tool_name": call.tool_name,
        "turn_index": turn_index,
        "queued_ms": 0,
        "started_ms": round((latency_start - start_monotonic) * 1000, 3),
        "first_output_ms": round((latency_finished - latency_start) * 1000, 3),
        "finished_ms": round((latency_finished - latency_start) * 1000, 3),
    }
    return call, result, latency


def _native_final_verifier_closeout_allowed(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
) -> bool:
    if not bool(lane_config.get("allow_verify")):
        return False
    if not bool(lane_config.get("allow_shell") or lane_config.get("run_command_available")):
        return False
    return bool(lane_input.workspace) and bool(_native_final_verifier_tool_name(lane_input, lane_config=lane_config))


def _native_final_verifier_tool_name(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
) -> str:
    for candidate in ("exec_command", "run_command"):
        if _native_tool_available(candidate, lane_input=lane_input, lane_config=lane_config):
            return candidate
    return ""


def _canonical_native_verify_command_source(value: object, *, default: str = "") -> str:
    text = str(value or "").strip().casefold()
    if text in {"auto", "auto_detected", "auto-detected", "auto_detected_verifier"}:
        return "auto_detected_verifier"
    if text in {"explicit", "configured", "configured_verifier", "manual", "user", "cli", "task", "task_contract"}:
        return "configured_verifier"
    return default


def _native_final_verifier_command_candidate(
    lane_input: ImplementLaneInput,
    *,
    wanted_source: str,
) -> _NativeFinishVerifierPlan | None:
    lane_command = str((lane_input.lane_config or {}).get("verify_command") or "").strip()
    lane_source = _canonical_native_verify_command_source(
        (lane_input.lane_config or {}).get("verify_command_source"),
        default="configured_verifier" if lane_command else "",
    )
    for source_ref, source in (("lane_config.verify_command", lane_input.lane_config), ("task_contract.verify_command", lane_input.task_contract)):
        command = str((source or {}).get("verify_command") or "").strip()
        if not command:
            continue
        command_source = _canonical_native_verify_command_source(
            (source or {}).get("verify_command_source"),
            default="configured_verifier",
        )
        if (
            source_ref == "task_contract.verify_command"
            and "verify_command_source" not in (source or {})
            and lane_command
            and command == lane_command
            and lane_source == "auto_detected_verifier"
        ):
            command_source = "auto_detected_verifier"
        if command_source != wanted_source:
            continue
        return _NativeFinishVerifierPlan(
            command=command,
            source=command_source,
            raw={"source_ref": source_ref, "verify_command_source": command_source},
        )
    return None


def _configured_native_final_verifier_command(lane_input: ImplementLaneInput) -> str:
    candidate = _native_final_verifier_command_candidate(lane_input, wanted_source="configured_verifier")
    return candidate.command if candidate else ""


def _auto_detected_native_final_verifier_command(lane_input: ImplementLaneInput) -> _NativeFinishVerifierPlan | None:
    return _native_final_verifier_command_candidate(lane_input, wanted_source="auto_detected_verifier")


def _native_final_verifier_closeout_plan(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> _NativeFinishVerifierPlan | None:
    configured = _native_final_verifier_command_candidate(lane_input, wanted_source="configured_verifier")
    if configured is not None:
        return configured
    if not _native_finish_verifier_planner_can_run(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    ):
        return _auto_detected_native_final_verifier_command(lane_input)
    loop_request = _finish_verifier_planner_loop_request(
        lane_input,
        lane_config=lane_config,
        tool_results=tool_results,
    )
    request_hash = _finish_verifier_planner_request_hash(loop_request.as_planner_request())
    loop_result = run_finish_verifier_planner_loop(
        loop_request,
        planner_provider=provider,
    )
    if loop_result.status == "error":
        fallback, fallback_rejection = _safe_auto_detected_finish_verifier_fallback(
            lane_input,
            request=loop_request.as_planner_request(),
        )
        decision = dict(loop_result.record)
        decision.setdefault("status", "error")
        decision.setdefault("request_hash", request_hash)
        if fallback is not None:
            decision["fallback"] = _native_finish_verifier_plan_payload(fallback)
            decision["fallback_source"] = fallback.source
        elif fallback_rejection:
            decision["fallback_rejection"] = dict(fallback_rejection)
        else:
            decision.setdefault("fallback", {})
            decision.setdefault("fallback_source", "")
        _record_finish_verifier_planner_decision(provider, decision)
        _emit_progress(
            getattr(provider, "progress", None),
            f"finish_verifier_planner failed: {loop_result.reason or 'unknown'}; "
            f"fallback={_native_finish_verifier_plan_source(fallback)}",
        )
        return _native_finish_verifier_plan_with_planner_fallback(fallback, decision)
    if loop_result.status == "selected" and loop_result.plan is not None:
        _record_finish_verifier_planner_decision(provider, loop_result.record)
        return loop_result.plan
    fallback, fallback_rejection = _safe_auto_detected_finish_verifier_fallback(
        lane_input,
        request=loop_request.as_planner_request(),
    )
    decision = dict(loop_result.record)
    decision.setdefault("status", loop_result.status or "rejected")
    decision.setdefault("request_hash", request_hash)
    if loop_result.reason:
        decision.setdefault("reject_reason", loop_result.reason)
    if loop_result.blockers:
        decision.setdefault("reject_blockers", list(loop_result.blockers))
    if fallback is not None:
        decision["fallback"] = _native_finish_verifier_plan_payload(fallback)
        decision["fallback_source"] = fallback.source
    elif fallback_rejection:
        decision["fallback_rejection"] = dict(fallback_rejection)
    else:
        decision.setdefault("fallback", {})
        decision.setdefault("fallback_source", "")
    _record_finish_verifier_planner_decision(provider, decision)
    _emit_progress(
        getattr(provider, "progress", None),
        "finish_verifier_planner rejected plan: "
        f"{loop_result.reason or 'unknown'}; fallback={_native_finish_verifier_plan_source(fallback)}",
    )
    return _native_finish_verifier_plan_with_planner_fallback(fallback, decision)


def _safe_auto_detected_finish_verifier_fallback(
    lane_input: ImplementLaneInput,
    *,
    request: Mapping[str, object],
) -> tuple[_NativeFinishVerifierPlan | None, Mapping[str, object] | None]:
    fallback = _auto_detected_native_final_verifier_command(lane_input)
    if fallback is None:
        return None, None
    safety = _finish_verifier_command_safety(
        fallback.command,
        request=request,
        require_observable_assertions=True,
    )
    if safety.allowed:
        return fallback, None
    return None, {
        "source": fallback.source,
        "command": fallback.command,
        "reason": safety.reason,
        "blockers": list(safety.blockers),
    }


def run_finish_verifier_planner_loop(
    request: FinishVerifierPlannerLoopRequest,
    *,
    planner_provider: object,
    read_dispatcher: object | None = None,
    artifact_sink: object | None = None,
) -> FinishVerifierPlannerLoopResult:
    """Run the v0 finish-verifier planner component.

    Phase 1 deliberately wraps the existing single-shot planner provider behind
    the component contract. Later phases can replace the provider internals with
    a multi-turn read-only tool loop without changing the harness boundary.
    """

    del read_dispatcher, artifact_sink
    planner_request = request.as_planner_request()
    request_hash = _finish_verifier_planner_request_hash(planner_request)
    _record_finish_verifier_planner_request(planner_provider, planner_request, request_hash=request_hash)
    if not request.policy.enabled:
        record = _finish_verifier_planner_decision_record(
            status="no_plan",
            request_hash=request_hash,
            reject_reason="finish verifier planner loop is disabled",
            reject_blockers=("planner_loop_disabled",),
        )
        return FinishVerifierPlannerLoopResult(
            status="no_plan",
            plan=None,
            record=record,
            blockers=("planner_loop_disabled",),
            reason="finish verifier planner loop is disabled",
        )
    planner = getattr(planner_provider, "plan_finish_verifier_command", None)
    if not callable(planner):
        record = _finish_verifier_planner_decision_record(
            status="no_plan",
            request_hash=request_hash,
            reject_reason="planner provider has no plan_finish_verifier_command",
            reject_blockers=("planner_provider_missing",),
        )
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
        record = _finish_verifier_planner_decision_record(
            status="error",
            request_hash=request_hash,
            error=str(exc),
        )
        return FinishVerifierPlannerLoopResult(
            status="error",
            plan=None,
            record=record,
            blockers=("planner_provider_error",),
            reason=str(exc),
        )
    forbidden = _finish_verifier_planner_forbidden_tool_attempts(raw_plan, request.policy)
    if forbidden:
        record = _finish_verifier_planner_decision_record(
            status="rejected",
            request_hash=request_hash,
            raw_plan=raw_plan,
            reject_reason="planner attempted forbidden tool",
            reject_blockers=forbidden,
        )
        return FinishVerifierPlannerLoopResult(
            status="rejected",
            plan=None,
            record=record,
            blockers=forbidden,
            reason="planner attempted forbidden tool",
        )
    coercion = _coerce_native_finish_verifier_plan_with_diagnostics(
        raw_plan,
        request=planner_request,
    )
    if coercion.plan is None:
        record = _finish_verifier_planner_decision_record(
            status=coercion.status or "rejected",
            request_hash=request_hash,
            raw_plan=raw_plan,
            reject_reason=coercion.reject_reason,
            reject_blockers=coercion.reject_blockers,
        )
        return FinishVerifierPlannerLoopResult(
            status="rejected" if coercion.status != "no_plan" else "no_plan",
            plan=None,
            record=record,
            blockers=coercion.reject_blockers,
            reason=coercion.reject_reason,
        )
    record = _finish_verifier_planner_decision_record(
        status="accepted",
        request_hash=request_hash,
        raw_plan=raw_plan,
        plan=coercion.plan,
    )
    return FinishVerifierPlannerLoopResult(
        status="selected",
        plan=coercion.plan,
        record=record,
        reason=coercion.plan.reason,
    )


def _native_finish_verifier_planner_can_run(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> bool:
    if not bool(lane_config.get("experimental_finish_verifier_planner")):
        return False
    if not tool_results:
        return False
    return callable(getattr(provider, "plan_finish_verifier_command", None))


def _finish_verifier_planner_loop_request(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> FinishVerifierPlannerLoopRequest:
    legacy_request = _finish_verifier_planner_request(lane_input, tool_results)
    task = legacy_request.get("task") if isinstance(legacy_request.get("task"), Mapping) else {}
    read_policy = legacy_request.get("read_policy") if isinstance(legacy_request.get("read_policy"), Mapping) else {}
    allowed_roots = lane_config.get("allowed_read_roots")
    if not isinstance(allowed_roots, (list, tuple)):
        allowed_roots = (lane_input.workspace,)
    latest_mutation = _latest_mutation_for_finish_verifier_planner(tool_results)
    task_contract = dict(lane_input.task_contract)
    legacy_contract = task.get("contract")
    if isinstance(legacy_contract, Mapping):
        task_contract.update(dict(legacy_contract))
    external_failure = lane_config.get("finish_verifier_external_failure")
    if not isinstance(external_failure, Mapping):
        external_failure = None
    return FinishVerifierPlannerLoopRequest(
        lane_attempt_id=_lane_attempt_id(lane_input),
        turn_id="finish-verifier-planner",
        finish_call_id="finish",
        task_id=str(task.get("task_id") or lane_input.task_id),
        task_description=str(task.get("description") or _native_task_description(lane_input)),
        task_contract=task_contract,
        latest_mutation=latest_mutation,
        recent_tool_results=tuple(
            item for item in legacy_request.get("recent_tool_results", ()) if isinstance(item, Mapping)
        ),
        candidate_paths=_finish_verifier_planner_candidate_paths(
            lane_input,
            latest_mutation=latest_mutation,
            legacy_read_policy=read_policy,
            tool_results=tool_results,
        ),
        policy=FinishVerifierPlannerLoopPolicy(
            enabled=bool(lane_config.get("experimental_finish_verifier_planner")),
            max_turns=_planner_bounded_int(lane_config.get("finish_verifier_planner_max_turns"), 3, 1, 8),
            max_wall_seconds=_safe_float(
                lane_config.get("finish_verifier_planner_timeout_seconds"),
                default=30.0,
            ),
            allowed_roots=tuple(str(root) for root in allowed_roots if str(root).strip()),
        ),
        external_verifier_failure=dict(external_failure) if isinstance(external_failure, Mapping) else None,
        legacy_request=legacy_request,
    )


def _latest_mutation_for_finish_verifier_planner(
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    for result in reversed(tool_results):
        if result.status != "completed" or result.is_error:
            continue
        if result.tool_name not in {"write_file", "edit_file", "apply_patch", "run_command", "exec_command"}:
            continue
        payload = _native_result_payload(result)
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


def _finish_verifier_planner_candidate_paths(
    lane_input: ImplementLaneInput,
    *,
    latest_mutation: Mapping[str, object],
    legacy_read_policy: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> tuple[str, ...]:
    workspace = Path(str(lane_input.workspace or ".")).expanduser().resolve(strict=False)
    paths: list[str] = []
    _extend_unique_paths(paths, legacy_read_policy.get("candidate_paths"), workspace=workspace, structured=True)
    _extend_unique_paths(paths, latest_mutation.get("paths"), workspace=workspace, structured=True)
    _extend_unique_paths(
        paths,
        _task_contract_candidate_paths(lane_input.task_contract, workspace=workspace),
        workspace=workspace,
        structured=True,
    )
    for result in reversed(tool_results[-8:]):
        if result.status != "completed" or result.is_error:
            continue
        payload = _native_result_payload(result)
        _extend_unique_paths(
            paths,
            _payload_candidate_paths(payload, workspace=workspace),
            workspace=workspace,
            structured=True,
        )
    return tuple(paths[:24])


def _task_contract_candidate_paths(task_contract: object, *, workspace: Path) -> tuple[str, ...]:
    if not isinstance(task_contract, Mapping):
        return ()
    paths: list[str] = []
    for key in ("expected_artifact", "expected_artifacts", "artifact", "artifacts", "source_requirements"):
        _extend_unique_paths(paths, task_contract.get(key), workspace=workspace, structured=True)
    compiled = _mapping_from_request_descriptor(task_contract.get("compiled_task_contract"))
    _extend_unique_paths(paths, compiled.get("source_requirements"), workspace=workspace, structured=True)
    for key in ("verify_command", "description", "guidance"):
        _extend_unique_paths(paths, task_contract.get(key), workspace=workspace, structured=False)
    return tuple(paths)


def _payload_candidate_paths(payload: Mapping[str, object], *, workspace: Path) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("changed_paths", "path", "target", "file", "output_path"):
        _extend_unique_paths(paths, payload.get(key), workspace=workspace, structured=True)
    typed = payload.get("typed_source_mutation") if isinstance(payload.get("typed_source_mutation"), Mapping) else {}
    _extend_unique_paths(paths, typed.get("changed_paths"), workspace=workspace, structured=True)
    card = payload.get("mutation_output_card") if isinstance(payload.get("mutation_output_card"), Mapping) else {}
    _extend_unique_paths(paths, card.get("changed_paths"), workspace=workspace, structured=True)
    for key in (
        "cwd",
        "command",
        "stdout",
        "stderr",
        "stdout_tail",
        "stderr_tail",
    ):
        _extend_unique_paths(paths, payload.get(key), workspace=workspace, structured=False)
    return tuple(paths)


def _extract_paths_from_value(value: object, *, workspace: Path, structured: bool) -> tuple[str, ...]:
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
            cleaned = _normalize_finish_verifier_candidate_path(item, workspace=workspace, structured=True)
            if cleaned:
                found.append(cleaned)
            return
        for match in _PATH_LIKE_TOKEN_RE.findall(item):
            cleaned = _normalize_finish_verifier_candidate_path(match, workspace=workspace, structured=False)
            if cleaned:
                found.append(cleaned)

    visit(value)
    return tuple(dict.fromkeys(found))


def _extend_unique_paths(paths: list[str], value: object, *, workspace: Path, structured: bool = False) -> None:
    for path in _extract_paths_from_value(value, workspace=workspace, structured=structured):
        if path not in paths:
            paths.append(path)


def _normalize_finish_verifier_candidate_path(path: str, *, workspace: Path, structured: bool) -> str:
    path = path.strip().strip("'\"`.,:;()[]{}")
    if not path or len(path) > 240:
        return ""
    if path in {".", "..", "/", "/tmp", "/app"}:
        return ""
    if path.startswith(("http://", "https://", "file://")):
        return ""
    if "\x00" in path or "\n" in path or "\r" in path:
        return ""
    normalized = path
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        try:
            resolved = candidate.resolve(strict=False)
            normalized = resolved.relative_to(workspace).as_posix()
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


def _finish_verifier_planner_forbidden_tool_attempts(
    value: object,
    policy: FinishVerifierPlannerLoopPolicy,
) -> tuple[str, ...]:
    attempts = _finish_verifier_planner_tool_names(value)
    if not attempts:
        return ()
    allowed = set(policy.allowed_tools)
    blockers: list[str] = []
    for tool_name in attempts:
        if tool_name not in allowed:
            blockers.append(f"planner_forbidden_tool:{tool_name}")
    return tuple(dict.fromkeys(blockers))


def _finish_verifier_planner_tool_names(value: object) -> tuple[str, ...]:
    names: list[str] = []

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            candidate = (
                item.get("tool_name")
                or item.get("name")
                or item.get("tool")
                or item.get("function_name")
            )
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


def _coerce_native_finish_verifier_plan(
    value: object,
    *,
    request: Mapping[str, object] | None = None,
) -> _NativeFinishVerifierPlan | None:
    return _coerce_native_finish_verifier_plan_with_diagnostics(value, request=request).plan


def _coerce_native_finish_verifier_plan_with_diagnostics(
    value: object,
    *,
    request: Mapping[str, object] | None = None,
) -> _NativeFinishVerifierPlanCoercion:
    if not isinstance(value, Mapping):
        return _NativeFinishVerifierPlanCoercion(
            plan=None,
            status="rejected",
            reject_reason="planner output was not a JSON object",
            reject_blockers=("planner_plan_not_mapping",),
        )
    command = str(value.get("command") or value.get("cmd") or "").strip()
    safety = _finish_verifier_command_safety(
        command,
        request=request,
        require_observable_assertions=_finish_verifier_requires_observable_assertions(request),
    )
    if not safety.allowed:
        return _NativeFinishVerifierPlanCoercion(
            plan=None,
            status="rejected",
            reject_reason=safety.reason,
            reject_blockers=safety.blockers,
        )
    cwd = str(value.get("cwd") or ".").strip() or "."
    if "\x00" in cwd or "\n" in cwd or cwd.startswith("/"):
        cwd = "."
    return _NativeFinishVerifierPlanCoercion(
        plan=_NativeFinishVerifierPlan(
            command=command,
            cwd=cwd,
            source="finish_verifier_planner",
            reason=str(value.get("reason") or value.get("rationale") or "").strip(),
            confidence=str(value.get("confidence") or "").strip(),
            raw=dict(value),
        ),
        status="accepted",
    )


def _finish_verifier_requires_observable_assertions(request: Mapping[str, object] | None) -> bool:
    if not isinstance(request, Mapping):
        return False
    external_failure = request.get("external_verifier_failure")
    if isinstance(external_failure, Mapping) and external_failure:
        return True
    return False


def _finish_verifier_external_failure(request: Mapping[str, object] | None) -> Mapping[str, object]:
    if not isinstance(request, Mapping):
        return {}
    value = request.get("external_verifier_failure")
    return dict(value) if isinstance(value, Mapping) else {}


def _external_failure_assertion_blockers_allowed(command: str, blockers: tuple[str, ...]) -> bool:
    allowed = {
        "finish_verifier_weak_assertion",
        "finish_verifier_shell_composition",
    }
    return (
        bool(blockers)
        and set(blockers).issubset(allowed)
        and _finish_verifier_external_assertion_command_shape_safe(command)
    )


_FINISH_VERIFIER_NOOP_COMMAND_RE = re.compile(
    r"(?is)^\s*(?:true|:|exit\s+0|test\s+1\s*={1,2}\s*1|\[\s*1\s*={1,2}\s*1\s*\])\s*$"
)
_FINISH_VERIFIER_SELF_ACCEPTANCE_RE = re.compile(
    r"(?i)\b(?:acceptance_ok|final_acceptance_ok|acceptance\s*:\s*pass)\b"
)
_FINISH_VERIFIER_MUTATION_RE = re.compile(
    r"(?is)(?:^|[;&|]\s*)(?:rm|mv|cp|touch|mkdir|chmod|chown|truncate|install|tee)\b"
    r"|\b(?:sed\s+-i|perl\s+-pi)\b"
    r"|(?:^|[^<])>{1,2}(?!&)"
)
_FINISH_VERIFIER_GENERIC_TEST_RE = re.compile(
    r"(?i)(?:^|[\s;&|()])(?:pytest|npm\s+test|pnpm\s+test|yarn\s+test|cargo\s+test|go\s+test|make\s+(?:test|check)|"
    r"prove|coqc|coqchk|mvn\s+test|gradle\s+test|tox|ruff\s+check|python\s+-m\s+pytest)(?:$|[\s;&|()])"
)
_FINISH_VERIFIER_STDOUT_REQUIREMENT_RE = re.compile(
    r"(?i)\b(?:stdout|standard\s+output|terminal\s+output|expected\s+output|print(?:ed)?\s+output)\b"
)
_FINISH_VERIFIER_STDERR_REQUIREMENT_RE = re.compile(
    r"(?i)\b(?:stderr|standard\s+error|error\s+output)\b"
)
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
_PATH_LIKE_TOKEN_RE = re.compile(
    r"(?:/[\w@+.,:=~%/-]+|[\w@+.,:=~%-]+/[\w@+.,:=~%/-]+|"
    r"(?<![A-Za-z0-9_./-])[\w@+.-]+\."
    r"(?:py|pyx|pxd|js|ts|tsx|jsx|c|h|cc|cpp|hpp|rs|go|java|rb|php|lua|v|vo|ml|mli|sh|json|toml|yaml|yml|"
    r"txt|md|so|dylib|dll|exe|o|a|bmp|png|jpe?g|ppm|gif|svg)(?![A-Za-z0-9_./-]))"
)


def _finish_verifier_command_safe(
    command: object,
    *,
    request: Mapping[str, object] | None = None,
) -> bool:
    return _finish_verifier_command_safety(command, request=request).allowed


def _finish_verifier_command_safety(
    command: object,
    *,
    request: Mapping[str, object] | None = None,
    require_observable_assertions: bool = True,
) -> _FinishVerifierCommandSafetyResult:
    text = str(command or "").strip()
    validation = validate_closeout_command(
        FinishCloseoutCommand(command=text, source="finish_verifier_planner"),
        NativeFinishGatePolicy(allowed_sources=("finish_verifier_planner",)),
    )
    requirements = _finish_verifier_observable_requirements(request)
    external_failure = _finish_verifier_external_failure(request)
    external_failure_assertion = _finish_verifier_command_asserts_external_failure(text, external_failure)
    if not validation.allowed:
        mapped_blockers = tuple(_planner_safety_blocker(blocker) for blocker in validation.blockers)
        if (
            set(mapped_blockers) == {"finish_verifier_weak_assertion"}
            and _finish_verifier_command_asserts_observables(text, requirements)
        ):
            validation = FinishCloseoutCommandValidation(
                allowed=True,
                command=validation.command,
                reason="nontrivial observable assertion command",
            )
        elif external_failure and external_failure_assertion and _external_failure_assertion_blockers_allowed(text, mapped_blockers):
            validation = FinishCloseoutCommandValidation(
                allowed=True,
                command=validation.command,
                reason="concrete external verifier failure assertion command",
            )
        else:
            return _FinishVerifierCommandSafetyResult(
                allowed=False,
                reason=validation.reason,
                blockers=mapped_blockers,
            )
    if external_failure:
        if not external_failure_assertion:
            return _FinishVerifierCommandSafetyResult(
                allowed=False,
                reason="finish verifier command does not assert the prior external verifier failure shape",
                blockers=("finish_verifier_external_failure_shape_missing",),
            )
        return _FinishVerifierCommandSafetyResult(allowed=True, reason="asserts prior external verifier failure shape")
    if (
        require_observable_assertions
        and requirements
        and not _finish_verifier_command_asserts_observables(text, requirements)
    ):
        return _FinishVerifierCommandSafetyResult(
            allowed=False,
            reason="finish verifier command does not assert required task-visible observables",
            blockers=("finish_verifier_observable_assertions_missing",),
        )
    if require_observable_assertions and requirements and _finish_verifier_command_asserts_observables(text, requirements):
        return _FinishVerifierCommandSafetyResult(allowed=True, reason="asserts external verifier observables")
    if _FINISH_VERIFIER_GENERIC_TEST_RE.search(text):
        return _FinishVerifierCommandSafetyResult(allowed=True, reason="generic test command")
    if request is None:
        return _FinishVerifierCommandSafetyResult(allowed=True, reason="no request subject to check")
    if not _finish_verifier_command_mentions_task_subject(text, request):
        return _FinishVerifierCommandSafetyResult(
            allowed=False,
            reason="finish verifier command does not mention a task subject",
            blockers=("finish_verifier_task_subject_missing",),
        )
    return _FinishVerifierCommandSafetyResult(allowed=True, reason="mentions task subject")


def _finish_verifier_observable_requirements(request: Mapping[str, object] | None) -> tuple[str, ...]:
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
            json.dumps(_json_safe_native(task_contract), ensure_ascii=False, sort_keys=True),
            json.dumps(
                _json_safe_native(request.get("recent_tool_results") or ()),
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(_json_safe_native(request.get("external_verifier_failure") or {}), ensure_ascii=False, sort_keys=True),
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


def _finish_verifier_command_asserts_observables(command: str, requirements: tuple[str, ...]) -> bool:
    if not requirements:
        return _finish_verifier_nontrivial_test_command(command)
    if _FINISH_VERIFIER_GENERIC_TEST_RE.search(command):
        return True
    if _FINISH_VERIFIER_ASSERTION_COMMAND_RE.search(command):
        return True
    if _finish_verifier_nontrivial_test_command(command) and any(
        item in {"file_artifact", "image_artifact"} for item in requirements
    ):
        return True
    return False


def _finish_verifier_nontrivial_test_command(command: str) -> bool:
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


def _finish_verifier_command_asserts_external_failure(
    command: str,
    external_failure: Mapping[str, object],
) -> bool:
    if not external_failure:
        return False
    expected_terms = _external_failure_expected_stdout_terms(external_failure)
    artifact_paths = _external_failure_artifact_path_terms(external_failure)
    if not expected_terms and not artifact_paths:
        return False
    executable_terms = _finish_verifier_command_executable_terms(command)
    normalized_command = " ".join(executable_terms).casefold()
    if expected_terms and not any(term.casefold() in normalized_command for term in expected_terms):
        return False
    command_paths = {path.casefold() for path in _external_failure_command_path_terms(executable_terms)}
    if artifact_paths and not any(path.casefold() in command_paths for path in artifact_paths):
        return False
    if artifact_paths and not _external_failure_artifact_paths_asserted(executable_terms, artifact_paths):
        return False
    if expected_terms and not _external_failure_stdout_assertion_has_runtime_target(
        executable_terms,
        expected_terms,
        artifact_paths,
        external_failure,
    ):
        return False
    if not _finish_verifier_external_assertion_command_semantic(command):
        return False
    return True


def _finish_verifier_external_assertion_command_shape_safe(command: str) -> bool:
    if re.search(r"\$\(|`|\|\||;|(?<!\|)\|(?!\|)|(?<!&)&(?!&)|[<>]", command):
        return False
    return True


def _finish_verifier_external_assertion_command_semantic(command: str) -> bool:
    return _FINISH_VERIFIER_ASSERTION_COMMAND_RE.search(command) is not None or _finish_verifier_nontrivial_test_command(command)


def _finish_verifier_command_executable_terms(command: str) -> tuple[str, ...]:
    try:
        tokens = shlex.split(command, comments=True)
    except ValueError:
        return tuple(command.split())
    return tuple(tokens)


def _external_failure_command_path_terms(executable_terms: tuple[str, ...]) -> tuple[str, ...]:
    paths: list[str] = []
    for term in executable_terms:
        for match in _PATH_LIKE_TOKEN_RE.finditer(term):
            value = str(match.group(0) or "").strip().strip("'\"`.,:;()[]{}")
            if value and value not in paths:
                paths.append(value)
    return tuple(paths)


def _external_failure_stdout_assertion_has_runtime_target(
    executable_terms: tuple[str, ...],
    expected_terms: tuple[str, ...],
    artifact_paths: tuple[str, ...],
    external_failure: Mapping[str, object],
) -> bool:
    artifact_set = {path.casefold() for path in artifact_paths}
    for segment in _external_failure_assertion_segments(executable_terms):
        segment_text = " ".join(segment).casefold()
        if not any(term.casefold() in segment_text for term in expected_terms):
            continue
        if not _external_failure_stdout_assertion_tool(segment):
            continue
        has_runtime_target = False
        for path in (path.casefold() for path in _external_failure_command_path_terms(segment)):
            if path in artifact_set:
                continue
            if not _external_failure_runtime_stdout_path(path, external_failure):
                return False
            has_runtime_target = True
        if has_runtime_target:
            return True
    return False


def _external_failure_assertion_segments(executable_terms: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for term in executable_terms:
        if term == "&&":
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(term)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _external_failure_artifact_paths_asserted(
    executable_terms: tuple[str, ...],
    artifact_paths: tuple[str, ...],
) -> bool:
    artifact_set = {path.casefold() for path in artifact_paths}
    asserted: set[str] = set()
    for segment in _external_failure_assertion_segments(executable_terms):
        segment_paths = {path.casefold() for path in _external_failure_command_path_terms(segment)}
        for artifact_path in artifact_set.intersection(segment_paths):
            if _external_failure_artifact_segment_asserts_path(segment, artifact_path):
                asserted.add(artifact_path)
    return bool(artifact_set) and artifact_set.issubset(asserted)


def _external_failure_artifact_segment_asserts_path(segment: tuple[str, ...], artifact_path: str) -> bool:
    if not segment:
        return False
    segment_paths = {path.casefold() for path in _external_failure_command_path_terms(segment)}
    if artifact_path not in segment_paths:
        return False
    first = Path(segment[0]).name.casefold()
    if first in {"stat", "identify"}:
        return True
    if first not in {"test", "[", "[["}:
        return False
    if "!" in segment or "-o" in segment:
        return False
    file_predicates = {"-e", "-f", "-s", "-r", "-x", "-d"}
    lowered = tuple(term.casefold() for term in segment)
    return any(
        term in file_predicates and index + 1 < len(lowered) and lowered[index + 1] == artifact_path
        for index, term in enumerate(lowered)
    )


def _external_failure_stdout_assertion_tool(segment: tuple[str, ...]) -> bool:
    if not segment:
        return False
    first = Path(segment[0]).name.casefold()
    return first in {"grep", "rg"} and not _external_failure_stdout_assertion_inverted(segment)


def _external_failure_stdout_assertion_inverted(segment: tuple[str, ...]) -> bool:
    for term in segment[1:]:
        lowered = term.casefold()
        if lowered == "--invert-match":
            return True
        if lowered == "--files-without-match":
            return True
        if lowered == "-v":
            return True
        if term == "-L":
            return True
        if lowered.startswith("-") and not lowered.startswith("--") and "v" in lowered[1:]:
            return True
        if term.startswith("-") and not term.startswith("--") and "L" in term[1:]:
            return True
    return False


def _external_failure_oracle_source_path(path: str) -> bool:
    normalized = path.replace("\\", "/").casefold()
    if "/tests/" in normalized or normalized.startswith("/app/test") or normalized.startswith("tests/"):
        return True
    name = Path(normalized).name
    return name.startswith("test_") or name.endswith("_test.py") or name.endswith("_tests.py")


def _external_failure_runtime_stdout_path(path: str, external_failure: Mapping[str, object]) -> bool:
    normalized = path.replace("\\", "/").casefold()
    source_path = str(external_failure.get("source_path") or "").replace("\\", "/").casefold()
    if source_path and normalized == source_path:
        return False
    if "/verifier/test-stdout" in normalized or normalized.endswith("/test-stdout.txt"):
        return False
    if _external_failure_oracle_source_path(normalized):
        return False
    suffix = Path(normalized).suffix
    if suffix in {
        ".py",
        ".pyx",
        ".pxd",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".rs",
        ".go",
        ".java",
        ".rb",
        ".php",
        ".lua",
        ".sh",
    }:
        return False
    name = Path(normalized).name
    if any(marker in name for marker in ("stdout", "stderr", "output", "actual", "capture", "transcript", "log")):
        return True
    return suffix in {".txt", ".log", ".out"}


def _external_failure_expected_stdout_terms(external_failure: Mapping[str, object]) -> tuple[str, ...]:
    values = external_failure.get("expected_stdout_substrings")
    if not isinstance(values, (list, tuple)):
        return ()
    terms: list[str] = []
    for item in values:
        term = " ".join(str(item or "").split()).strip()
        if len(term) >= 4 and term not in terms:
            terms.append(term)
    return tuple(terms[:8])


def _external_failure_artifact_path_terms(external_failure: Mapping[str, object]) -> tuple[str, ...]:
    values = external_failure.get("artifact_paths")
    if not isinstance(values, (list, tuple)):
        return ()
    paths: list[str] = []
    for item in values:
        path = str(item or "").strip()
        if len(path) >= 4 and _PATH_LIKE_TOKEN_RE.search(path) and path not in paths:
            paths.append(path)
    return tuple(paths[:20])


def _planner_safety_blocker(blocker: str) -> str:
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


def _record_finish_verifier_planner_decision(provider: object, record: Mapping[str, object]) -> None:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, None)
    if not isinstance(existing, list):
        existing = []
        try:
            setattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, existing)
        except Exception:
            return
    existing.append(dict(record))


def _record_finish_verifier_planner_request(
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
    existing.append({"request_hash": request_hash, "request": _json_safe_native(dict(request))})


def _provider_finish_verifier_planner_decisions(provider: object) -> tuple[Mapping[str, object], ...]:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_DECISIONS_ATTR, ())
    if not isinstance(existing, list):
        return ()
    return tuple(item for item in existing if isinstance(item, Mapping))


def _provider_finish_verifier_planner_requests(provider: object) -> tuple[Mapping[str, object], ...]:
    existing = getattr(provider, _FINISH_VERIFIER_PLANNER_REQUESTS_ATTR, ())
    if not isinstance(existing, list):
        return ()
    return tuple(item for item in existing if isinstance(item, Mapping))


def _finish_verifier_planner_request_hash(request: Mapping[str, object]) -> str:
    encoded = json.dumps(dict(request), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _finish_verifier_planner_value_hash(value: object) -> str:
    encoded = json.dumps(_json_safe_native(value), ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _finish_verifier_planner_decision_record(
    *,
    status: str,
    request_hash: str,
    raw_plan: object = _RAW_FINISH_VERIFIER_PLAN_MISSING,
    plan: _NativeFinishVerifierPlan | None = None,
    reject_reason: str = "",
    reject_blockers: tuple[str, ...] = (),
    fallback: _NativeFinishVerifierPlan | None = None,
    error: str = "",
) -> dict[str, object]:
    record: dict[str, object] = {
        "status": status,
        "request_hash": request_hash,
    }
    if raw_plan is not _RAW_FINISH_VERIFIER_PLAN_MISSING:
        record["raw_plan"] = _json_safe_native(raw_plan)
        record["raw_plan_hash"] = _finish_verifier_planner_value_hash(raw_plan)
    if plan is not None:
        record["accepted_plan"] = _native_finish_verifier_plan_payload(plan)
    if reject_reason:
        record["reject_reason"] = reject_reason
    if reject_blockers:
        record["reject_blockers"] = list(reject_blockers)
    if error:
        record["error"] = error
    if fallback is not None:
        record["fallback"] = _native_finish_verifier_plan_payload(fallback)
        record["fallback_source"] = fallback.source
    else:
        record["fallback"] = {}
        record["fallback_source"] = ""
    return record


def _native_finish_verifier_plan_with_planner_fallback(
    plan: _NativeFinishVerifierPlan | None,
    planner_decision: Mapping[str, object],
) -> _NativeFinishVerifierPlan | None:
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


def _native_finish_verifier_plan_source(plan: _NativeFinishVerifierPlan | None) -> str:
    return plan.source if plan is not None else "none"


def _native_finish_verifier_plan_payload(plan: _NativeFinishVerifierPlan) -> dict[str, object]:
    payload: dict[str, object] = {
        "command": plan.command,
        "cwd": plan.cwd,
        "source": plan.source,
        "reason": plan.reason,
        "confidence": plan.confidence,
    }
    if plan.raw:
        payload["raw"] = _json_safe_native(dict(plan.raw))
    return {key: value for key, value in payload.items() if value not in ("", {}, [], ())}


def _json_safe_native(value: object) -> object:
    try:
        json.dumps(value, sort_keys=True, default=str)
    except TypeError:
        return repr(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe_native(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_native(item) for item in value]
    return value


def _patch_proof_manifest_with_finish_verifier_planner_decisions(
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
    digest = _file_sha256_native(decision_path)
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    manifest["finish_verifier_planner_decisions_ref"] = decision_path.name
    manifest["finish_verifier_planner_decisions_sha256"] = digest
    request_digest = ""
    if request_path is not None:
        request_digest = _file_sha256_native(request_path)
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
        json.dumps(_json_safe_native(manifest), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256_native(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _finish_verifier_command_mentions_task_subject(command: str, request: Mapping[str, object]) -> bool:
    terms = _finish_verifier_subject_terms(request)
    if not terms:
        return True
    lowered = command.casefold()
    return any(term in lowered for term in terms)


def _finish_verifier_subject_terms(request: Mapping[str, object]) -> tuple[str, ...]:
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
    return tuple(terms[:80])


def _finish_verifier_planner_request(
    lane_input: ImplementLaneInput,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "role": "independent_finish_verifier_planner",
        "task": {
            "task_id": lane_input.task_id,
            "description": _native_task_description(lane_input),
            "contract": _small_jsonable_mapping(lane_input.task_contract),
            "verify_command_source": _canonical_native_verify_command_source(
                (lane_input.lane_config or {}).get("verify_command_source")
                or (lane_input.task_contract or {}).get("verify_command_source"),
                default="",
            ),
        },
        "workspace": ".",
        "recent_tool_results": [
            _finish_verifier_planner_tool_result_summary(index, result)
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


def _finish_verifier_planner_tool_result_summary(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    payload = _native_result_payload(result)
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


def _small_jsonable_mapping(value: object) -> dict[str, object]:
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


def _finish_verifier_planner_prompt(request: Mapping[str, object]) -> str:
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
        "- If external_verifier_failure is present, choose a verifier that checks the same externally observed "
        "failure shape instead of only running the candidate program to completion.\n"
        "- If no safe verifier exists, return {\"command\":\"\", \"reason\":\"no safe verifier\"}.\n\n"
        "Input:\n"
        f"{json.dumps(dict(request), ensure_ascii=False, sort_keys=True)}"
    )


def _native_final_verifier_closeout_budget_seconds(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
) -> float:
    remaining = _native_remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining is None:
        remaining = float(lane_input.lane_config.get("final_verifier_closeout_seconds") or 60.0)
    configured = lane_input.lane_config.get("final_verifier_closeout_seconds")
    if configured not in (None, ""):
        try:
            remaining = min(remaining, max(0.0, float(configured)))
        except (TypeError, ValueError):
            return 0.0
    return max(0.0, min(3600.0, remaining))


def _native_remaining_wall_budget_seconds(lane_input: ImplementLaneInput, *, run_started: float) -> float | None:
    max_wall = lane_input.task_contract.get("max_wall_seconds")
    if max_wall in (None, ""):
        return None
    try:
        remaining = float(max_wall) - max(0.0, time.monotonic() - run_started)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(600.0, remaining))


def _native_next_model_timeout_seconds(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
    requested_timeout: object,
) -> float | None:
    remaining = _native_remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining is None:
        return None
    try:
        requested = float(requested_timeout) if requested_timeout not in (None, "") else remaining
    except (TypeError, ValueError):
        requested = remaining
    if requested <= 0:
        return requested
    reserve = min(
        _NATIVE_MODEL_TIMEOUT_RESERVE_SECONDS,
        max(0.0, remaining - _NATIVE_MODEL_TIMEOUT_MIN_SECONDS),
    )
    available = remaining - reserve
    return max(0.0, min(requested, available))


def _native_final_verifier_closeout_call(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    lane_config: Mapping[str, object],
    plan: _NativeFinishVerifierPlan,
    timeout_seconds: float,
    pending_mutation: Mapping[str, object],
) -> NativeTranscriptItem:
    call_id = f"call-final-verifier-closeout-{turn_index:03d}"
    arguments = {
        "command": plan.command,
        "cwd": plan.cwd or ".",
        "use_shell": True,
        "timeout": round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
        "foreground_budget_seconds": round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
        "command_intent": "finish_verifier",
        "finish_verifier_plan": {
            "source": plan.source,
            "reason": plan.reason,
            "confidence": plan.confidence,
            "separate_agent": plan.source == "finish_verifier_planner",
            **({"provenance": dict(plan.raw)} if plan.raw else {}),
        },
        "execution_contract": {
            "role": "verify",
            "stage": "verification",
            "purpose": "verify the latest source mutation before native closeout",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "verifier_required": True,
            "expected_exit": 0,
            "latest_source_mutation_provider_call_id": pending_mutation.get("provider_call_id") or "",
            "latest_source_mutation_path": pending_mutation.get("path") or "",
        },
    }
    tool_name = _native_final_verifier_tool_name(lane_input, lane_config=lane_config) or "run_command"
    if tool_name == "exec_command":
        arguments = {
            **arguments,
            "cmd": plan.command,
            "timeout_ms": int(round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds) * 1000)),
            "yield_time_ms": int(round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds) * 1000)),
        }
    return NativeTranscriptItem(
        sequence=0,
        turn_id=f"turn-{turn_index}-final-verifier-closeout",
        lane_attempt_id=lane_attempt_id,
        provider=str(getattr(provider, "provider", "") or "native-controller"),
        model=str(getattr(provider, "model", "") or lane_input.model or ""),
        response_id=f"native-final-verifier-closeout-{turn_index}",
        provider_item_id=f"fc_mew_final_verifier_closeout_{turn_index:03d}",
        output_index=0,
        kind="function_call",
        call_id=call_id,
        tool_name=tool_name,
        arguments_json_text=json.dumps(arguments, sort_keys=True),
    )


def _latest_native_source_mutation_without_later_verifier(
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> dict[str, object]:
    latest_mutation = _latest_native_source_mutation(
        tool_calls,
        tool_results,
        source_mutation_roots=source_mutation_roots,
    )
    latest_verifier_index = 0
    verifier_command_run_ids: set[str] = set()
    for index, (call, result) in enumerate(zip(tool_calls, tool_results), start=1):
        if _native_call_is_verifier(call):
            command_run_id = _command_run_id_from_result(result)
            if command_run_id:
                verifier_command_run_ids.add(command_run_id)
        if _native_result_is_terminal_verifier(call, result, verifier_command_run_ids=verifier_command_run_ids):
            latest_verifier_index = index
    if not latest_mutation:
        return {}
    latest_mutation["latest_verifier_index"] = latest_verifier_index
    if int(latest_mutation.get("result_index") or 0) <= latest_verifier_index:
        return {}
    return latest_mutation


def _latest_native_source_mutation(
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> dict[str, object]:
    latest_mutation: dict[str, object] = {}
    for index, (call, result) in enumerate(zip(tool_calls, tool_results), start=1):
        if result.status == "completed" and _native_result_has_source_mutation(
            result,
            source_mutation_roots=source_mutation_roots,
        ):
            latest_mutation = {
                "result_index": index,
                "provider_call_id": call.call_id or result.provider_call_id,
                "tool_name": call.tool_name or result.tool_name,
                "path": _native_write_result_path(result),
                "turn_index": _turn_number(call.turn_id),
            }
    return latest_mutation


def _native_result_is_terminal_verifier(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    verifier_command_run_ids: set[str],
) -> bool:
    if result.status not in {"completed", "failed", "interrupted", "invalid"}:
        return False
    command_run_id = _command_run_id_from_result(result)
    if command_run_id and command_run_id in verifier_command_run_ids:
        return True
    if _native_call_is_verifier(call):
        return True
    payload = _native_result_payload(result)
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    if not _native_execution_contract_is_verifier_like(contract):
        return False
    verifier = payload.get("verifier_evidence")
    if not isinstance(verifier, dict):
        return True
    return str(verifier.get("verdict") or "").casefold() in {"pass", "fail", "partial"}


def _native_result_has_source_mutation(
    result: ToolResultEnvelope,
    *,
    source_mutation_roots: tuple[str, ...],
) -> bool:
    for effect in result.side_effects:
        kind = str(effect.get("kind") or "")
        if kind == "file_write" and _native_path_in_roots(effect.get("path"), source_mutation_roots):
            return True
        if kind in {"source_tree_mutation", "source_tree_delta"}:
            record = effect.get("record")
            if isinstance(record, dict) and record.get("changed_count"):
                return True
        if kind == "process_source_observation":
            record = effect.get("record")
            if isinstance(record, dict) and record.get("changed_count"):
                return True
    return False


def _native_write_result_path(result: ToolResultEnvelope) -> str:
    for effect in result.side_effects:
        if str(effect.get("kind") or "") == "file_write":
            path = str(effect.get("path") or "").strip()
            if path:
                return path
        if str(effect.get("kind") or "") in {"source_tree_mutation", "source_tree_delta"}:
            record = effect.get("record")
            if not isinstance(record, dict):
                continue
            changes = record.get("changes")
            if isinstance(changes, list):
                for change in changes:
                    if isinstance(change, dict) and change.get("path"):
                        return str(change.get("path") or "")
    return ""


def _native_path_in_roots(path: object, roots: tuple[str, ...]) -> bool:
    text = str(path or "").strip()
    if not text:
        return False
    candidate = Path(text).expanduser()
    for root in roots:
        root_path = Path(root).expanduser().resolve(strict=False)
        resolved = candidate.resolve(strict=False) if candidate.is_absolute() else (root_path / candidate).resolve(strict=False)
        try:
            resolved.relative_to(root_path)
            return True
        except ValueError:
            continue
    return False


def _native_source_mutation_roots(lane_input: ImplementLaneInput, workspace: Path) -> tuple[str, ...]:
    raw_roots = lane_input.lane_config.get("source_mutation_roots")
    if isinstance(raw_roots, list):
        roots = tuple(str(root) for root in raw_roots if str(root or "").strip())
    else:
        roots = ()
    return roots or (str(workspace),)


def _native_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def _native_execution_contract_is_verifier_like(contract: object) -> bool:
    if not isinstance(contract, dict):
        return False
    proof_role = str(contract.get("proof_role") or "").casefold()
    acceptance_kind = str(contract.get("acceptance_kind") or "").casefold()
    stage = str(contract.get("stage") or "").casefold()
    purpose = str(contract.get("purpose") or "").casefold()
    role = str(contract.get("role") or "").casefold()
    return (
        proof_role == "verifier"
        or acceptance_kind in {"external_verifier", "candidate_final_proof"}
        or stage == "final-verifier"
        or "verifier" in purpose
        or role in {"verify", "test"}
    )


def _native_final_verifier_passed(result: ToolResultEnvelope) -> bool:
    if result.status != "completed" or result.is_error:
        return False
    if _tool_result_has_semantic_verifier_failure(result):
        return False
    payload = _native_result_payload(result)
    verifier = payload.get("verifier_evidence")
    if isinstance(verifier, dict):
        verdict = str(verifier.get("verdict") or "").casefold()
        if verdict == "pass":
            return True
        if verdict in {"fail", "failed", "partial"}:
            return False
        return _native_completed_verifier_exit_zero(result)
    return True


def _native_completed_verifier_exit_zero(result: ToolResultEnvelope) -> bool:
    payload = _native_result_payload(result)
    if payload.get("exit_code") not in (0, "0"):
        return False
    if str(payload.get("tool_name") or "").strip() == "run_tests":
        return True
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    return _native_execution_contract_is_verifier_like(contract) or str(
        payload.get("command_intent") or ""
    ).strip().casefold() in {"verify", "verifier", "verification", "finish_verifier", "test", "acceptance"}


def _command_run_id_from_result(result: ToolResultEnvelope) -> str:
    payload = _native_result_payload(result)
    return str(payload.get("command_run_id") or "").strip()


def _native_output_from_result(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    sequence: int,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
) -> NativeTranscriptItem:
    if call.kind == "finish_call":
        output_kind = "finish_output"
    elif call.kind == "custom_tool_call":
        output_kind = "custom_tool_call_output"
    else:
        output_kind = "function_call_output"
    rendered = render_tool_result_for_profile(
        result,
        profile_id=tool_surface_profile_id(lane_config),
    )
    output_text = rendered.text
    if not _native_tool_available("write_file", lane_input=lane_input, lane_config=lane_config):
        output_text = hide_unavailable_write_file_guidance(output_text)
    route_ref = str(result.route_decision.get("ref") or "")
    return NativeTranscriptItem(
        sequence=sequence,
        turn_id=call.turn_id,
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        model=call.model,
        response_id=call.response_id,
        provider_item_id=f"output-{call.call_id}",
        output_index=call.output_index,
        kind=output_kind,
        call_id=call.call_id,
        tool_name=call.tool_name,
        output_text_or_ref=output_text,
        status=_native_output_status(call, result),
        is_error=result.is_error,
        metrics_ref=rendered.metrics_ref(lane_attempt_id=call.lane_attempt_id, call_id=call.call_id),
        content_refs=result.content_refs,
        evidence_refs=result.evidence_refs,
        sidecar_refs=(route_ref,) if route_ref else (),
    )


def _finish_result(
    call: ToolCallEnvelope,
    *,
    lane_input: ImplementLaneInput,
    prior_tool_results: tuple[ToolResultEnvelope, ...],
) -> ToolResultEnvelope:
    protocol_error = _finish_protocol_error(call.arguments)
    if protocol_error:
        return _finish_protocol_error_result(call, reason=protocol_error)
    outcome = _native_finish_outcome(call.arguments)
    task_done = call.arguments.get("task_done")
    blocked = outcome in {"blocked", "blocked_return", "continue"} or task_done is False
    if not blocked:
        finish_arguments = dict(call.arguments)
        finish_arguments["outcome"] = outcome
        gate = _native_finish_gate_decision(
            lane_input,
            finish_arguments,
            prior_tool_results,
        )
        if gate.get("decision") != "allow_complete":
            return _finish_gate_block_result(call, gate)
    status = "invalid" if blocked else "completed"
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="finish",
        status=status,
        is_error=blocked,
        content=({"summary": str(call.arguments.get("summary") or ""), "outcome": outcome or status},),
        evidence_refs=("native-finish://accepted",) if status == "completed" else (),
    )


def _finish_tool_call_envelope(call: NativeTranscriptItem, arguments: Mapping[str, object]) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name="finish",
        arguments=dict(arguments),
        provider_message_id=call.provider_item_id,
        turn_index=_turn_number(call.turn_id),
        sequence_index=call.output_index,
        status="validated",
    )


_ALLOWED_FINISH_ARGUMENT_KEYS = frozenset(
    {
        "blockers",
        "budget_blockers",
        "closeout_refs",
        "evidence_refs",
        "final_status",
        "missing_obligations",
        "outcome",
        "reason",
        "return_to_supervisor",
        "status",
        "summary",
        "task_done",
        "unsafe_blockers",
        "unsafe_to_continue",
    }
)


def _finish_protocol_error(arguments: Mapping[str, object]) -> str:
    unknown = sorted(str(key) for key in arguments if str(key) not in _ALLOWED_FINISH_ARGUMENT_KEYS)
    if unknown:
        return "finish arguments contain unsupported keys: " + ", ".join(unknown)
    for key in ("summary", "reason", "outcome", "status", "final_status"):
        value = arguments.get(key)
        if value is not None and not isinstance(value, str):
            return f"finish argument {key!r} must be a string"
    task_done = arguments.get("task_done")
    if task_done is not None and not isinstance(task_done, bool):
        return "finish argument 'task_done' must be a boolean"
    for key in ("evidence_refs", "closeout_refs", "blockers", "missing_obligations", "unsafe_blockers", "budget_blockers"):
        value = arguments.get(key)
        if value is not None and not _finish_string_list_like(value):
            return f"finish argument {key!r} must be a string or list of strings"
    for key in ("return_to_supervisor", "unsafe_to_continue"):
        value = arguments.get(key)
        if value is not None and not isinstance(value, bool):
            return f"finish argument {key!r} must be a boolean"
    return ""


def _finish_string_list_like(value: object) -> bool:
    if isinstance(value, str):
        return True
    if not isinstance(value, (list, tuple)):
        return False
    return all(isinstance(item, str) for item in value)


def _finish_protocol_error_result(call: ToolCallEnvelope, *, reason: str) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="finish",
        status="invalid",
        is_error=True,
        content=(
            {
                "summary": reason,
                "outcome": "protocol_error",
                "finish_protocol_error": {"reason": reason},
            },
        ),
    )


def _native_finish_outcome(arguments: Mapping[str, object]) -> str:
    raw = str(
        arguments.get("outcome")
        or arguments.get("status")
        or arguments.get("final_status")
        or ""
    ).strip().lower()
    if not raw:
        return "completed"
    if raw in {"complete", "completed", "done", "success", "succeeded", "ok"}:
        return "completed"
    if raw in {"blocked_return", "return", "supervisor_return", "needs_supervisor"}:
        return "blocked_return"
    if raw in {"block", "blocked", "continue", "needs_work", "incomplete", "fail", "failed", "failure", "error"}:
        return "blocked" if raw != "continue" else "continue"
    return "completed"


def _native_finish_gate_decision(
    lane_input: ImplementLaneInput,
    finish_arguments: dict[str, object],
    prior_tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    action = _finish_acceptance_action(
        finish_arguments,
        prior_tool_results,
        task_description=_native_task_description(lane_input),
    )
    return acceptance_done_gate_decision(
        _native_task_description(lane_input),
        action,
        session=_acceptance_session_from_tool_results(prior_tool_results, lane_input=lane_input),
    )


def _native_task_description(lane_input: ImplementLaneInput) -> str:
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


def _finish_gate_block_result(call: ToolCallEnvelope, gate: Mapping[str, object]) -> ToolResultEnvelope:
    continuation = str(gate.get("continuation_prompt") or gate.get("reason") or "finish gate blocked completion")
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="finish",
        status="invalid",
        is_error=True,
        content=(
            {
                "summary": continuation,
                "outcome": "continue",
                "finish_gate": dict(gate),
            },
        ),
    )


def _completion_resolver_input_from_finish(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    lane_input: ImplementLaneInput,
    transcript_items: tuple[NativeTranscriptItem, ...],
    request_descriptor: Mapping[str, object],
    prior_tool_results: tuple[ToolResultEnvelope, ...],
    closeout_context: _NativeCloseoutContext,
) -> CompletionResolverInput:
    arguments, _ = _arguments(call)
    outcome = _native_finish_outcome(arguments)
    gate: dict[str, object] = {}
    if outcome == "completed" and arguments.get("task_done") is not False:
        finish_arguments = dict(arguments)
        finish_arguments["outcome"] = outcome
        gate = _native_finish_gate_decision(lane_input, finish_arguments, prior_tool_results)
    blockers: list[str] = []
    missing: list[str] = []
    unsafe_blockers: list[str] = []
    budget_blockers: list[str] = []
    if outcome in {"blocked", "continue"} or arguments.get("task_done") is False:
        blockers.append("finish_claim_not_completed")
    if outcome == "blocked_return" or arguments.get("return_to_supervisor") is True:
        budget_blockers.append("finish_requested_supervisor_return")
    if arguments.get("unsafe_to_continue") is True:
        unsafe_blockers.append("finish_marked_unsafe_to_continue")
    finish_evidence_refs = _finish_arg_strings(arguments.get("evidence_refs"))
    finish_closeout_refs = _finish_arg_strings(arguments.get("closeout_refs"))
    finish_closeout_context = _native_finish_supplied_closeout_context(
        tuple(dict.fromkeys((*finish_evidence_refs, *finish_closeout_refs))),
        prior_tool_results,
        source_mutation_roots=_native_source_mutation_roots(lane_input, Path(lane_input.workspace or ".")),
    )
    effective_closeout_context = _native_closeout_context_resolved_by_finish_evidence(
        closeout_context,
        finish_closeout_context,
    )
    blockers.extend(_finish_arg_strings(arguments.get("blockers")))
    missing.extend(_finish_arg_strings(arguments.get("missing_obligations")))
    unsafe_blockers.extend(_finish_arg_strings(arguments.get("unsafe_blockers")))
    budget_blockers.extend(_finish_arg_strings(arguments.get("budget_blockers")))
    blockers.extend(effective_closeout_context.blockers)
    missing.extend(effective_closeout_context.missing_obligations)
    unsafe_blockers.extend(effective_closeout_context.unsafe_blockers)
    budget_blockers.extend(effective_closeout_context.budget_blockers)
    gate_codes = _finish_gate_blocker_codes(gate) if gate else ()
    gate_missing = _finish_gate_missing_obligations(gate) if gate else ()
    if (
        gate
        and gate.get("decision") != "allow_complete"
        and not _finish_gate_block_resolved_by_closeout(
            gate_codes,
            gate_missing,
            gate=gate,
            closeout_context=effective_closeout_context,
        )
    ):
        blockers.append("finish_gate_blocked")
        blockers.extend(gate_codes)
        missing.extend(gate_missing)
    return CompletionResolverInput(
        finish_claim=FinishClaim(
            lane_attempt_id=call.lane_attempt_id,
            turn_id=call.turn_id,
            finish_call_id=call.call_id,
            finish_output_call_id=call.call_id,
            outcome=outcome,
            summary=str(arguments.get("summary") or ""),
            arguments=dict(arguments),
        ),
        transcript_hash_before_decision=native_transcript_hash(
            NativeTranscript(
                lane_attempt_id=call.lane_attempt_id,
                provider=call.provider,
                model=call.model,
                items=transcript_items,
            )
        ),
        compact_sidecar_digest_hash=_request_compact_sidecar_digest_hash(request_descriptor),
        typed_evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *finish_evidence_refs))),
        fresh_verifier_refs=tuple(effective_closeout_context.fresh_verifier_refs),
        missing_obligations=tuple(dict.fromkeys(missing)),
        closeout_refs=tuple(dict.fromkeys((*finish_closeout_refs, *effective_closeout_context.closeout_refs))),
        blockers=tuple(dict.fromkeys(blockers)),
        unsafe_blockers=tuple(dict.fromkeys(unsafe_blockers)),
        budget_blockers=tuple(dict.fromkeys(budget_blockers)),
        verifier_required=bool(gate and gate.get("decision") != "allow_complete"),
    )


def _native_finish_gate_decision_from_closeout_events(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
    transcript_items: tuple[NativeTranscriptItem, ...],
    request_descriptor: Mapping[str, object],
    closeout_events: tuple[_NativeCloseoutEvent, ...],
    closeout_context: _NativeCloseoutContext,
) -> NativeFinishGateDecision | None:
    if result.tool_name != "finish":
        return None
    arguments, error = _arguments(call)
    if error:
        return None
    if _native_finish_outcome(arguments) != "completed" or arguments.get("task_done") is False:
        return None
    final_event = next((event for event in reversed(closeout_events) if event.kind == "final_verifier"), None)
    if final_event is None:
        return None
    closeout = _native_finish_closeout_result_from_event(final_event, closeout_context=closeout_context)
    if closeout.status != "completed_zero":
        return None
    request = NativeFinishGateRequest(
        lane_attempt_id=call.lane_attempt_id,
        turn_id=call.turn_id,
        finish_call_id=call.call_id,
        finish_arguments=dict(arguments),
        task_id=str(lane_input.task_id or ""),
        task_description=_native_task_description(lane_input),
        task_contract=dict(lane_input.task_contract),
        lane_config=dict(lane_config),
        workspace=str(lane_input.workspace or ""),
        allowed_read_roots=tuple(str(root) for root in lane_config.get("allowed_read_roots") or ()),
        allowed_write_roots=tuple(str(root) for root in lane_config.get("allowed_write_roots") or ()),
        transcript_hash_before_decision=native_transcript_hash(
            NativeTranscript(
                lane_attempt_id=call.lane_attempt_id,
                provider=call.provider,
                model=call.model,
                items=transcript_items,
            )
        ),
        compact_sidecar_digest_hash=_request_compact_sidecar_digest_hash(request_descriptor),
    )
    return decide_native_finish_from_closeout(request, closeout)


def _native_finish_gate_decision_from_controller_closeout_event(
    event: _NativeCloseoutEvent,
    *,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
    transcript_items: tuple[NativeTranscriptItem, ...],
    closeout_context: _NativeCloseoutContext,
) -> NativeFinishGateDecision:
    closeout = _native_finish_closeout_result_from_event(event, closeout_context=closeout_context)
    request = NativeFinishGateRequest(
        lane_attempt_id=event.call.lane_attempt_id,
        turn_id=event.call.turn_id,
        finish_call_id=event.call.call_id,
        finish_arguments={
            "outcome": "completed",
            "summary": "deterministic final verifier closeout",
            "controller_closeout": True,
        },
        task_id=str(lane_input.task_id or ""),
        task_description=_native_task_description(lane_input),
        task_contract=dict(lane_input.task_contract),
        lane_config=dict(lane_config),
        workspace=str(lane_input.workspace or ""),
        allowed_read_roots=tuple(str(root) for root in lane_config.get("allowed_read_roots") or ()),
        allowed_write_roots=tuple(str(root) for root in lane_config.get("allowed_write_roots") or ()),
        transcript_hash_before_decision=native_transcript_hash(
            NativeTranscript(
                lane_attempt_id=event.call.lane_attempt_id,
                provider=event.call.provider,
                model=event.call.model,
                items=transcript_items,
            )
        ),
    )
    return decide_native_finish_from_closeout(request, closeout)


def _native_finish_closeout_result_from_event(
    event: _NativeCloseoutEvent,
    *,
    closeout_context: _NativeCloseoutContext,
) -> NativeFinishCloseoutResult:
    payload = _native_result_payload(event.result)
    exit_code = _native_exit_code(payload)
    timed_out = _native_result_timed_out(event.result, payload)
    if event.result.status == "completed" and not event.result.is_error and exit_code == 0 and not timed_out:
        status = "completed_zero"
    elif timed_out:
        status = "timed_out"
    elif event.result.status in {"completed", "failed"} and exit_code not in (None, 0):
        status = "completed_nonzero"
    elif event.result.status in {"yielded", "running"}:
        status = "active_command_running"
    else:
        status = "runtime_error"
    return NativeFinishCloseoutResult(
        command=_finish_closeout_command_from_call(event.call),
        call_item=event.call,
        output_item=None,
        tool_result=event.result,
        status=status,
        exit_code=exit_code,
        timed_out=timed_out,
        observed_unexpected_source_mutation=_native_closeout_observed_source_mutation(event.result),
        typed_evidence_projection_status="warning" if _native_closeout_projection_warnings(event.result) else "passed",
        evidence_refs=tuple(event.result.evidence_refs),
        closeout_refs=tuple(closeout_context.closeout_refs),
        warnings=_native_closeout_projection_warnings(event.result),
        reason=event.reason,
    )


def _finish_closeout_command_from_call(call: NativeTranscriptItem) -> FinishCloseoutCommand | None:
    arguments, error = _arguments(call)
    if error:
        return None
    command = str(arguments.get("command") or "").strip()
    if not command:
        return None
    plan = arguments.get("finish_verifier_plan")
    source = "configured_verifier"
    source_ref = "native_final_verifier_closeout"
    reason = ""
    confidence = ""
    if isinstance(plan, Mapping):
        plan_source = str(plan.get("source") or "").strip()
        if plan_source == "finish_verifier_planner":
            source = plan_source
        elif plan_source in {"auto_detected", "auto_detected_verifier"}:
            source = "auto_detected_verifier"
        elif plan_source in {"configured", "configured_verifier", "explicit"}:
            source = "configured_verifier"
        reason = str(plan.get("reason") or "")
        confidence = str(plan.get("confidence") or "")
    return FinishCloseoutCommand(
        command=command,
        cwd=str(arguments.get("cwd") or "."),
        source=source,  # type: ignore[arg-type]
        source_ref=source_ref,
        reason=reason,
        confidence=confidence,
        raw=dict(arguments),
    )


def _native_exit_code(payload: Mapping[str, object]) -> int | None:
    value = payload.get("exit_code")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _native_result_timed_out(result: ToolResultEnvelope, payload: Mapping[str, object]) -> bool:
    if payload.get("timed_out") is True:
        return True
    status = str(payload.get("status") or result.status or "").strip().casefold()
    return status in {"timeout", "timed_out"}


def _native_closeout_projection_warnings(result: ToolResultEnvelope) -> tuple[str, ...]:
    payload = _native_result_payload(result)
    warnings: list[str] = []
    unchecked = payload.get("unchecked_expected_artifacts")
    if isinstance(unchecked, list) and unchecked:
        warnings.append("unchecked_expected_artifacts")
    if payload.get("typed_evidence_projection_status") in {"warning", "failed"}:
        warnings.append("typed_evidence_projection_warning")
    return tuple(dict.fromkeys(warnings))


def _native_closeout_observed_source_mutation(result: ToolResultEnvelope) -> bool:
    payload = _native_result_payload(result)
    if payload.get("observed_source_side_effect") is True:
        return True
    observations = payload.get("process_source_observations")
    if isinstance(observations, list):
        for observation in observations:
            if isinstance(observation, Mapping) and _positive_intish(observation.get("changed_count")):
                return True
    for effect in result.side_effects:
        if str(effect.get("kind") or "") in {"source_tree_mutation", "source_tree_delta"}:
            record = effect.get("record")
            if isinstance(record, Mapping) and _positive_intish(record.get("changed_count")):
                return True
    return False


def _positive_intish(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def _finish_result_with_native_finish_gate_decision(
    result: ToolResultEnvelope,
    decision: NativeFinishGateDecision,
) -> ToolResultEnvelope:
    payload = dict(result.content[0]) if result.content and isinstance(result.content[0], dict) else {}
    payload["native_finish_gate_decision"] = decision.as_dict()
    payload["native_finish_gate_decision_id"] = decision.decision_id
    payload["lane_status"] = decision.lane_status
    if decision.result == "allow":
        payload.pop("finish_gate", None)
        payload.pop("blockers", None)
        payload.pop("missing_obligations", None)
        payload["summary"] = payload.get("summary") or decision.reason
        payload["outcome"] = "completed"
        return replace(
            result,
            status="completed",
            is_error=False,
            content=(payload,),
            evidence_refs=tuple(
                dict.fromkeys((*result.evidence_refs, *decision.evidence_refs, *decision.closeout_refs))
            ),
        )
    payload["summary"] = decision.reason
    payload["outcome"] = decision.lane_status
    payload["blockers"] = list(decision.blockers)
    payload["missing_obligations"] = list(decision.missing_obligations)
    return replace(
        result,
        status="invalid",
        is_error=True,
        content=(payload,),
        evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *decision.evidence_refs))),
    )


def _finish_result_with_resolver_decision(
    result: ToolResultEnvelope,
    decision: CompletionResolverDecision,
) -> ToolResultEnvelope:
    payload = dict(result.content[0]) if result.content and isinstance(result.content[0], dict) else {}
    payload["completion_resolver"] = decision.as_dict()
    payload["resolver_decision_id"] = decision.decision_id
    payload["lane_status"] = decision.lane_status
    if decision.result == "allow":
        payload.pop("finish_gate", None)
        payload["summary"] = payload.get("summary") or decision.reason
        payload["outcome"] = "completed"
        return replace(
            result,
            status="completed",
            is_error=False,
            content=(payload,),
            evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *decision.evidence_refs))),
        )
    payload["summary"] = decision.reason
    payload["outcome"] = decision.lane_status
    payload["blockers"] = list(decision.blockers)
    payload["missing_obligations"] = list(decision.missing_obligations)
    payload["summary"] = _finish_block_model_visible_summary(decision)
    return replace(
        result,
        status="invalid",
        is_error=True,
        content=(payload,),
        evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *decision.evidence_refs))),
    )


def _finish_block_model_visible_summary(decision: CompletionResolverDecision) -> str:
    """Compact resolver facts into the finish output visible to the model."""

    blockers = _bounded_finish_block_items(decision.blockers, limit=4)
    missing = _bounded_finish_block_items(
        (_compact_finish_missing_obligation(item) for item in decision.missing_obligations),
        limit=6,
    )
    lines = [_finish_block_headline(blockers, missing)]
    if blockers:
        lines.append("blockers: " + ", ".join(blockers))
    if missing:
        lines.append("missing: " + ", ".join(missing))
    repair = _finish_block_repair_hint(blockers, missing)
    if repair:
        lines.append("repair: " + repair)
    return "\n".join(lines)


def _finish_block_headline(blockers: tuple[str, ...], missing: tuple[str, ...]) -> str:
    joined = " ".join((*blockers, *missing)).casefold()
    if "verifier" in joined or "strict_verifier_evidence" in joined:
        return "missing verifier/task-contract evidence"
    if "unsafe" in joined:
        return "unsafe finish claim"
    if "budget" in joined:
        return "finish needs supervisor or more budget"
    return "finish claim is not yet supported by typed evidence"


def _finish_block_repair_hint(blockers: tuple[str, ...], missing: tuple[str, ...]) -> str:
    joined = " ".join((*blockers, *missing)).casefold()
    if "verifier" in joined or "strict_verifier_evidence" in joined:
        return "run or cite a fresh task verifier that satisfies the typed task contract"
    if "invalid_typed_evidence_ref" in joined:
        return "cite completed tool evidence refs, not only prose summaries"
    if missing:
        return "satisfy the missing typed obligations before finishing"
    if blockers:
        return "repair the blocker and finish again with concrete evidence"
    return ""


def _compact_finish_missing_obligation(item: object) -> str:
    text = str(item or "").strip()
    if not text:
        return ""
    if text.startswith("oracle:task_contract:compiled:"):
        parts = text.split(":")
        if len(parts) >= 5:
            return f"{parts[3]}:{parts[4]}"
    if text.startswith("oracle:task_contract_compiler:verifier"):
        return "task_contract_verifier:fresh"
    if text.startswith("oracle:contract:") and "/app/" in text:
        suffix = text[text.find("/app/") :]
        return _finish_block_clip(suffix, limit=120)
    return _finish_block_clip(text, limit=120)


def _bounded_finish_block_items(items: Iterable[object], *, limit: int) -> tuple[str, ...]:
    compact: list[str] = []
    for item in items:
        text = _finish_block_clip(item, limit=120)
        if text and text not in compact:
            compact.append(text)
        if len(compact) >= limit:
            break
    return tuple(compact)


def _finish_block_clip(value: object, *, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _native_finish_protocol_error(result: ToolResultEnvelope) -> bool:
    if result.tool_name != "finish":
        return False
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return isinstance(payload.get("finish_protocol_error"), dict)


def _native_finish_resolver_decision_payload(result: ToolResultEnvelope) -> dict[str, object]:
    if result.tool_name != "finish":
        return {}
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    decision = payload.get("completion_resolver")
    return dict(decision) if isinstance(decision, dict) else {}


def _native_finish_resolver_lane_status(result: ToolResultEnvelope) -> str:
    return str(_native_finish_resolver_decision_payload(result).get("lane_status") or "").strip()


def _native_finish_resolver_reason(result: ToolResultEnvelope) -> str:
    return str(_native_finish_resolver_decision_payload(result).get("reason") or "").strip()


def _native_finish_gate_authority_decision_payload(result: ToolResultEnvelope) -> dict[str, object]:
    if result.tool_name != "finish":
        return {}
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    decision = payload.get("native_finish_gate_decision")
    return dict(decision) if isinstance(decision, dict) else {}


def _native_finish_authority_lane_status(result: ToolResultEnvelope) -> str:
    native_decision = _native_finish_gate_authority_decision_payload(result)
    if native_decision:
        return str(native_decision.get("lane_status") or "").strip()
    return _native_finish_resolver_lane_status(result)


def _native_finish_authority_reason(result: ToolResultEnvelope) -> str:
    native_decision = _native_finish_gate_authority_decision_payload(result)
    if native_decision:
        return str(native_decision.get("reason") or "").strip()
    return _native_finish_resolver_reason(result)


def _request_compact_sidecar_digest_hash(request_descriptor: Mapping[str, object]) -> str:
    inventory = request_descriptor.get("provider_request_inventory")
    if isinstance(inventory, Mapping):
        return str(inventory.get("compact_sidecar_digest_hash") or "").strip()
    return ""


def _finish_arg_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item or "").strip()))


def _finish_gate_blocker_codes(gate: Mapping[str, object]) -> tuple[str, ...]:
    codes: list[str] = []
    blockers = gate.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if isinstance(blocker, Mapping):
                code = str(blocker.get("code") or blocker.get("family") or blocker.get("message") or "").strip()
                if code:
                    codes.append(code)
            else:
                text = str(blocker or "").strip()
                if text:
                    codes.append(text)
    return tuple(dict.fromkeys(codes))


def _finish_gate_block_resolved_by_closeout(
    gate_codes: tuple[str, ...],
    gate_missing: tuple[str, ...],
    *,
    gate: Mapping[str, object],
    closeout_context: _NativeCloseoutContext,
) -> bool:
    if not closeout_context.fresh_verifier_refs:
        return False
    top_level_missing = gate.get("missing_obligations")
    runtime_artifact_codes = {"runtime_final_verifier_artifact_evidence"}
    if gate_codes and all(code in runtime_artifact_codes for code in gate_codes):
        return not gate_missing and (not isinstance(top_level_missing, list) or not top_level_missing)
    closeout_resolvable_codes = {
        "failed_typed_evidence_ref",
        "invalid_typed_evidence_ref",
        "missing_typed_evidence",
        "missing_typed_obligation",
    }
    planner_verified = bool(closeout_context.planner_verified_finish_refs)
    if planner_verified:
        planner_only_codes = {"acceptance_constraints_unchecked"}
        if gate_codes and all(code in planner_only_codes for code in gate_codes):
            top_level_missing = gate.get("missing_obligations")
            if not gate_missing and (not isinstance(top_level_missing, list) or not top_level_missing):
                return True
    if any(code not in closeout_resolvable_codes for code in gate_codes):
        return False
    if isinstance(top_level_missing, list):
        return bool(top_level_missing) and all(_finish_gate_missing_obligation_is_verifier(item) for item in top_level_missing)
    if not gate_missing:
        return False
    return all(
        not missing
        or missing == "strict_verifier_evidence"
        or missing == "verifier_pass"
        or missing.endswith(":verifier_pass")
        for missing in gate_missing
    )


def _finish_gate_missing_obligation_is_verifier(value: object) -> bool:
    if isinstance(value, Mapping):
        kind = str(value.get("kind") or "").strip()
        if kind:
            return kind == "verifier_pass"
        text = str(value.get("id") or value.get("missing_obligation") or value.get("obligation") or "").strip()
    else:
        text = str(value or "").strip()
    return text in {"strict_verifier_evidence", "verifier_pass"} or text.endswith(":verifier_pass")


def _finish_gate_missing_obligations(gate: Mapping[str, object]) -> tuple[str, ...]:
    missing: list[str] = []
    top_level_missing = gate.get("missing_obligations")
    if isinstance(top_level_missing, list):
        for item in top_level_missing:
            text = _finish_gate_missing_obligation_text(item)
            if text:
                missing.append(text)
    blockers = gate.get("blockers")
    if isinstance(blockers, list):
        for blocker in blockers:
            if not isinstance(blocker, Mapping):
                continue
            for key in ("required_evidence_ref", "missing_obligation", "obligation"):
                value = str(blocker.get(key) or "").strip()
                if value:
                    missing.append(value)
    return tuple(dict.fromkeys(missing))


def _finish_gate_missing_obligation_text(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("id", "kind", "missing_obligation", "obligation", "required_evidence_ref"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return json.dumps(value, sort_keys=True, default=str)
    return str(value or "").strip()


def _native_finish_gate_blocked(result: ToolResultEnvelope) -> bool:
    if result.tool_name != "finish" or not result.is_error:
        return False
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return isinstance(payload.get("finish_gate"), dict)


def _native_finish_gate_decision_payload(result: ToolResultEnvelope) -> dict[str, object]:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    gate = payload.get("finish_gate")
    return dict(gate) if isinstance(gate, dict) else {}


def _invalid_result(call: NativeTranscriptItem, *, reason: str) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name=call.tool_name,
        status="invalid",
        is_error=True,
        content=({"reason": reason},),
    )


def _unavailable_result(
    lane_input: ImplementLaneInput,
    *,
    provider: NativeFakeProvider,
) -> NativeImplementV2HarnessResult:
    transcript = NativeTranscript(
        lane_attempt_id=_lane_attempt_id(lane_input),
        provider=provider.provider,
        model=provider.model,
    )
    return NativeImplementV2HarnessResult(
        status="unavailable",
        transcript=transcript,
        proof_artifacts=(),
        metrics={**PHASE3_NATIVE_SURFACE, "fallback_lane": "implement_v1", "provider_native_tool_loop": False},
    )


def _arguments(call: NativeTranscriptItem) -> tuple[dict[str, object], str]:
    if call.arguments_json_text:
        try:
            decoded = json.loads(call.arguments_json_text)
        except json.JSONDecodeError as exc:
            return {}, f"invalid JSON arguments: {exc.msg}"
        if not isinstance(decoded, dict):
            return {}, "native tool arguments must decode to an object"
        return dict(decoded), ""
    if call.custom_input_text:
        arguments: dict[str, object] = {"input": call.custom_input_text}
        if call.kind == "custom_tool_call" and call.tool_name == "apply_patch":
            arguments["apply"] = True
        return arguments, ""
    return {}, ""


def _renumber_items(items: tuple[NativeTranscriptItem, ...], *, start_sequence: int) -> tuple[NativeTranscriptItem, ...]:
    return tuple(replace(item, sequence=start_sequence + index) for index, item in enumerate(items))


def _request_descriptor(
    *,
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    turn_index: int,
    transcript_items: list[NativeTranscriptItem],
    loop_signals: Mapping[str, object] | None = None,
) -> dict[str, object]:
    loop_signals = loop_signals or _native_loop_control_state(
        transcript_items,
        current_turn_index=turn_index,
        lane_input=lane_input,
    )
    provider_visible_transcript_items = [
        _provider_visible_native_item(item, lane_input=lane_input)
        for item in transcript_items
    ]
    compact_sidecar_digest = _compact_sidecar_digest_for_request(
        lane_input=lane_input,
        lane_attempt_id=lane_attempt_id,
        transcript_items=provider_visible_transcript_items,
        loop_signals=loop_signals,
    )
    tool_surface = _tool_surface_snapshot_for_request(
        lane_input,
        provider_visible_transcript_items,
    )
    tool_specs = tool_surface.tool_specs
    input_items = _responses_input_items(
        lane_input,
        provider_visible_transcript_items,
        compact_sidecar_digest=compact_sidecar_digest,
    )
    instructions = _native_instructions(lane_input, tool_specs=tool_specs)
    forbidden_fields_report = build_provider_visible_forbidden_fields_report(
        input_items=input_items,
        instructions=instructions,
        compact_sidecar_digest=compact_sidecar_digest,
        compact_sidecar_digest_wire_visible=False,
    )
    provider_request_inventory = build_native_prompt_input_inventory(
        compact_sidecar_digest=compact_sidecar_digest,
        provider_visible_forbidden_fields=forbidden_fields_report,
        diagnostic_only_fields=loop_signals.keys(),
        diagnostic_loop_signals=loop_signals,
        compact_sidecar_digest_wire_visible=False,
    )
    provider_request_inventory["tool_surface"] = tool_surface.request_metadata()
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native" if _provider_is_live(lane_input) else "fake_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": lane_attempt_id,
        "turn_index": turn_index,
        "input_item_count": len(transcript_items),
        "input_items": input_items,
        "transcript_window": [item.as_dict() for item in provider_visible_transcript_items],
        "compact_sidecar_digest": dict(compact_sidecar_digest),
        "provider_request_inventory": provider_request_inventory,
        "tool_surface": tool_surface.request_metadata(),
        "tool_surface_profile_id": tool_surface.profile_id,
        "tool_surface_profile_version": tool_surface.profile_version,
        "tool_surface_profile_hash": tool_surface.profile_hash,
        "tool_surface_descriptor_hash": tool_surface.descriptor_hash,
        "tool_surface_route_table_hash": tool_surface.route_table_hash,
        "tool_surface_render_policy_hash": tool_surface.render_policy_hash,
        "tool_surface_prompt_contract_id": tool_surface.prompt_contract_id,
        "provider_tool_names": [spec.name for spec in tool_specs],
        "instructions": instructions,
        "model_json_main_path_detected": False,
    }


def _live_responses_request_descriptor(
    lane_input: ImplementLaneInput,
    *,
    provider: str,
    model: str,
    request_descriptor: Mapping[str, object],
) -> dict[str, object]:
    reasoning = _reasoning_config(lane_input)
    tool_specs = _tool_specs_from_request_descriptor(lane_input, request_descriptor)
    return build_responses_request_descriptor(
        model=model,
        instructions=str(request_descriptor.get("instructions") or _native_instructions(lane_input, tool_specs=tool_specs)),
        input_items=_provider_safe_input_items(request_descriptor.get("input_items")),
        tool_specs=tool_specs,
        transcript_window=request_descriptor.get("transcript_window") or (),
        reasoning=reasoning,
        provider_request_id=f"{request_descriptor.get('lane_attempt_id')}:turn:{request_descriptor.get('turn_index')}",
        prompt_cache_key=str(request_descriptor.get("lane_attempt_id") or ""),
        tool_surface_snapshot=_mapping_from_request_descriptor(
            request_descriptor.get("tool_surface")
        ),
    )


def _native_instructions(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
) -> str:
    if tool_specs is None:
        tool_specs = _native_tool_specs_for_request(lane_input, ())
    sections = [
        section
        for section in build_implement_v2_prompt_sections(
            lane_input,
            tool_specs=tool_specs,
        )
        if section.id
        not in {
            "implement_v2_workframe",
            "implement_v2_task_contract",
            "implement_v2_lane_state",
        }
    ]
    rendered = render_prompt_sections(sections)
    if not any(spec.name == "write_file" for spec in tool_specs):
        return hide_unavailable_write_file_guidance(rendered)
    return rendered


def _tool_specs_from_request_descriptor(
    lane_input: ImplementLaneInput,
    request_descriptor: Mapping[str, object],
) -> tuple[ImplementLaneToolSpec, ...]:
    names = {
        str(name or "").strip()
        for name in (request_descriptor.get("provider_tool_names") or ())
        if str(name or "").strip()
    }
    if tool_surface_profile_id(lane_input.lane_config) == CODEX_HOT_PATH_PROFILE_ID:
        snapshot = _tool_surface_snapshot_for_request(
            lane_input,
            (),
            available_provider_tool_names=tuple(sorted(names)) if names else None,
        )
        return snapshot.tool_specs
    specs = list_v2_tool_specs_for_task(
        lane_input.lane_config.get("mode") or "full",
        task_contract=lane_input.task_contract,
    )
    if not names:
        return _native_tool_specs_for_request(lane_input, ())
    return tuple(spec for spec in specs if spec.name in names)


def _native_tool_specs_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
) -> tuple[ImplementLaneToolSpec, ...]:
    return _tool_surface_snapshot_for_request(lane_input, transcript_items).tool_specs


def _tool_surface_snapshot_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
    *,
    available_provider_tool_names: tuple[str, ...] | None = None,
) -> ToolSurfaceSnapshot:
    return build_tool_surface_snapshot(
        lane_config=lane_input.lane_config,
        task_contract=lane_input.task_contract,
        transcript_items=transcript_items,
        available_provider_tool_names=available_provider_tool_names,
    )


def _mapping_from_request_descriptor(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _native_has_open_command(transcript_items: object) -> bool:
    return any(
        state["is_open"]
        for state in _native_latest_command_lifecycle_states(transcript_items).values()
    )


def _native_has_completed_command_output(transcript_items: object) -> bool:
    return any(
        (not state["is_open"]) and state["has_output_ref"]
        for state in _native_latest_command_lifecycle_states(transcript_items).values()
    )


def _native_latest_command_lifecycle_states(transcript_items: object) -> dict[str, dict[str, object]]:
    if not isinstance(transcript_items, (list, tuple)):
        return {}
    states: dict[str, dict[str, object]] = {}
    for item in transcript_items:
        if not isinstance(item, NativeTranscriptItem):
            continue
        if item.kind not in OUTPUT_ITEM_KINDS:
            continue
        if item.tool_name not in {
            "exec_command",
            "write_stdin",
            "run_command",
            "run_tests",
            "poll_command",
            "cancel_command",
        }:
            continue
        command_run_id = _command_run_id_from_output_item(item)
        if not command_run_id:
            continue
        previous = states.get(command_run_id)
        if previous and int(previous.get("sequence") or -1) > item.sequence:
            continue
        status = str(item.status or "").strip().casefold()
        states[command_run_id] = {
            "sequence": item.sequence,
            "status": status,
            "is_open": status in {"yielded", "running", "pending"},
            "has_output_ref": bool(item.content_refs)
            or bool(_command_run_id_from_output_text(item.output_text_or_ref)),
        }
    return states


def _command_run_id_from_output_item(item: NativeTranscriptItem) -> str:
    command_run_id = _command_run_id_from_output_text(item.output_text_or_ref)
    if command_run_id:
        return command_run_id
    for ref in item.content_refs:
        match = _COMMAND_OUTPUT_REF_RE.search(str(ref or ""))
        if match:
            return match.group("id")
    return ""


def _responses_input_items(
    lane_input: ImplementLaneInput,
    transcript_items: list[NativeTranscriptItem],
    *,
    compact_sidecar_digest: Mapping[str, object],
) -> list[dict[str, object]]:
    if tool_surface_profile_id(lane_input.lane_config) == CODEX_HOT_PATH_PROFILE_ID:
        raw_task = _raw_task_provider_visible_text(lane_input)
        task_facts = _provider_visible_task_facts(
            lane_input,
            text_sources=(raw_task,),
            include_contract_source_requirements=False,
            include_verify_command_paths=False,
        )
        items: list[dict[str, object]] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": raw_task,
                    }
                ],
            }
        ]
        if source_capsule := _codex_hot_path_source_facts_text(task_facts):
            items.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": source_capsule,
                        }
                    ],
                }
            )
    else:
        task_facts = _provider_visible_task_facts(lane_input)
        task_payload = {
            "task_contract": dict(lane_input.task_contract),
            "task_facts": task_facts,
            "workspace": lane_input.workspace,
            "lane": lane_input.lane,
        }
        items = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _task_first_provider_visible_text(lane_input, task_facts=task_facts),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(task_payload, ensure_ascii=False),
                    }
                ],
            }
        ]
    for item in transcript_items:
        converted = _responses_input_item_from_transcript_item(
            _provider_visible_native_item(item, lane_input=lane_input),
        )
        if converted:
            items.append(converted)
    return items


def _raw_task_provider_visible_text(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    for key in ("description", "prompt", "task", "objective", "goal", "title"):
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Complete the requested coding task in the current workspace."


def _task_first_provider_visible_text(
    lane_input: ImplementLaneInput,
    *,
    task_facts: Mapping[str, object],
) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    lines = ["Task"]
    title = str(contract.get("title") or "").strip()
    if title:
        lines.append(f"Title: {title}")
    objective = _task_contract_objective_text(contract)
    if objective:
        lines.append(f"Objective: {objective}")
    guidance = str(contract.get("guidance") or "").strip()
    if guidance:
        lines.append(f"Guidance: {guidance}")
    verify_command = str(contract.get("verify_command") or "").strip()
    if verify_command:
        lines.append(f"Verifier: {verify_command}")
    criteria = contract.get("completion_criteria")
    if isinstance(criteria, list):
        rendered_criteria = [str(item or "").strip() for item in criteria if str(item or "").strip()]
        if rendered_criteria:
            lines.append("Completion criteria:")
            lines.extend(f"- {item}" for item in rendered_criteria[:8])
    expected_artifacts = contract.get("expected_artifacts")
    if isinstance(expected_artifacts, list):
        rendered_artifacts = []
        for item in expected_artifacts[:8]:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "").strip()
            kind = str(item.get("kind") or "file").strip()
            artifact_id = str(item.get("id") or path or kind).strip()
            rendered_artifacts.append(f"- {artifact_id}: {kind}" + (f" at {path}" if path else ""))
        if rendered_artifacts:
            lines.append("Expected artifacts:")
            lines.extend(rendered_artifacts)
    constraints = contract.get("acceptance_constraints")
    if isinstance(constraints, list):
        rendered_constraints = [str(item or "").strip() for item in constraints if str(item or "").strip()]
        if rendered_constraints:
            lines.append("Acceptance constraints:")
            lines.extend(f"- {item}" for item in rendered_constraints)
    for key, label in (
        ("missing_workspace_paths", "Missing task paths"),
        ("existing_workspace_paths", "Existing task paths"),
        ("verify_command_paths", "Verifier paths"),
    ):
        raw_paths = task_facts.get(key)
        paths = [str(item).strip() for item in raw_paths if str(item).strip()] if isinstance(raw_paths, list) else []
        if paths:
            lines.append(f"{label}: {', '.join(paths)}")
    lines.append("Supporting JSON facts follow in the next input item.")
    return "\n".join(lines)


def _task_contract_objective_text(contract: Mapping[str, object]) -> str:
    for key in ("objective", "description", "goal", "task", "prompt"):
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _provider_visible_task_facts(
    lane_input: ImplementLaneInput,
    *,
    text_sources: Iterable[object] | None = None,
    include_contract_source_requirements: bool = True,
    include_verify_command_paths: bool = True,
) -> dict[str, object]:
    """Return factual task/path context without prescribing the next action."""

    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    verify_command = str(contract.get("verify_command") or "").strip()
    if text_sources is None:
        text_sources = [
            verify_command,
            str(contract.get("description") or ""),
            str(contract.get("title") or ""),
            str(contract.get("guidance") or ""),
        ]
        constraints = contract.get("acceptance_constraints")
        if isinstance(constraints, list):
            text_sources.extend(str(item or "") for item in constraints)
    else:
        text_sources = list(text_sources)

    source_requirements = _provider_visible_source_requirements(
        contract,
        text_sources=text_sources,
        include_contract_source_requirements=include_contract_source_requirements,
    )
    verify_paths = _task_paths_from_text(verify_command, workspace=lane_input.workspace) if include_verify_command_paths else []
    mentioned_paths = _dedupe_task_paths(
        path for source in text_sources for path in _task_paths_from_text(source, workspace=lane_input.workspace)
    )
    existing_paths, resolved_nested_tokens = _provider_visible_existing_workspace_paths(
        mentioned_paths,
        source_requirements,
        workspace=Path(lane_input.workspace),
    )
    missing_paths = [
        path
        for path in mentioned_paths
        if _task_path_is_safe_relative(path) and not (Path(lane_input.workspace) / path).exists()
        and path not in resolved_nested_tokens
    ]
    facts = {
        "source_requirement_paths": [item["path"] for item in source_requirements],
        "verify_command_paths": verify_paths,
        "mentioned_workspace_paths": mentioned_paths,
        "existing_workspace_paths": existing_paths,
        "missing_workspace_paths": missing_paths,
    }
    return {key: value for key, value in facts.items() if value}


def _provider_visible_source_requirements(
    contract: Mapping[str, object],
    *,
    text_sources: Iterable[object],
    include_contract_source_requirements: bool = True,
) -> list[dict[str, str]]:
    """Return source refs grounded in the provider-visible raw task text."""

    raw_text = "\n".join(str(source or "") for source in text_sources if str(source or "").strip())
    requirements = list(implementation_contract_source_requirements(raw_text))
    if not include_contract_source_requirements:
        return requirements[:6]
    compiled = _mapping_from_request_descriptor(contract.get("compiled_task_contract"))
    for container in (contract.get("source_requirements"), compiled.get("source_requirements")):
        for item in container if isinstance(container, list) else ():
            source_req = item if isinstance(item, Mapping) else {}
            path = str(source_req.get("path") or "").strip()
            if not path or not implementation_source_ref_matches_text(path, raw_text):
                continue
            if any(existing.get("path") == path for existing in requirements):
                continue
            requirements.append({"path": path, "sentence": str(source_req.get("reason") or "")})
            if len(requirements) >= 6:
                return requirements
    return requirements[:6]


def _codex_hot_path_source_facts_text(task_facts: Mapping[str, object]) -> str:
    """Render compact raw-task source context without exposing task_contract."""

    source_paths = _source_fact_path_list(task_facts.get("source_requirement_paths"))
    existing_paths = _source_fact_path_list(task_facts.get("existing_workspace_paths"))
    missing_paths = _source_fact_missing_path_list(task_facts.get("missing_workspace_paths"))
    verify_paths = _source_fact_path_list(task_facts.get("verify_command_paths"))
    if not any((source_paths, existing_paths, missing_paths, verify_paths)):
        return ""
    lines = ["Task source facts:"]
    if source_paths:
        lines.append(f"- Provided source/artifact refs from the task: {', '.join(source_paths)}")
    if existing_paths:
        lines.append(f"- Existing workspace paths named by the task: {', '.join(existing_paths)}")
    if missing_paths:
        lines.append(f"- Output or target paths named by the task but not present yet: {', '.join(missing_paths)}")
    if verify_paths:
        lines.append(f"- Verifier command paths named by the task: {', '.join(verify_paths)}")
    if source_paths or existing_paths:
        lines.append(
            "- The task text identifies the refs above as provided inputs."
        )
    if source_paths:
        lines.append(
            "- Source-use obligation inferred from the task text: treat the provided refs above as required "
            "inputs; build, modify, or verify through them. Do not replace or bypass them with a standalone "
            "synthetic artifact unless the task explicitly permits it."
        )
    return "\n".join(lines)


def _source_fact_path_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= 8:
            break
    return result


def _source_fact_missing_path_list(value: object) -> list[str]:
    return [
        path
        for path in _source_fact_path_list(value)
        if "/" in path or path.startswith("/")
    ]


def _provider_visible_existing_workspace_paths(
    mentioned_paths: Iterable[object],
    source_requirements: Iterable[Mapping[str, str]],
    *,
    workspace: Path,
) -> tuple[list[str], set[str]]:
    workspace = workspace.expanduser().resolve(strict=False)
    existing: list[str] = []
    resolved_nested_tokens: set[str] = set()
    normalized_mentions = _dedupe_task_paths(mentioned_paths)
    for path in normalized_mentions:
        if _task_path_has_safe_segments(path) and (workspace / path).exists():
            existing.append(path)

    source_roots = _source_fact_existing_source_roots(source_requirements, workspace=workspace)
    for path in normalized_mentions:
        if not _task_path_is_safe_relative(path) or "/" in path or (workspace / path).exists():
            continue
        matches = _source_fact_nested_matches(path, source_roots, workspace=workspace)
        if not matches:
            continue
        resolved_nested_tokens.add(path)
        for match in matches:
            if match not in existing:
                existing.append(match)
            if len(existing) >= 12:
                return existing, resolved_nested_tokens
    return existing[:12], resolved_nested_tokens


def _source_fact_existing_source_roots(
    source_requirements: Iterable[Mapping[str, str]],
    *,
    workspace: Path,
) -> tuple[Path, ...]:
    roots: list[Path] = []
    for requirement in source_requirements:
        raw_path = str(requirement.get("path") or "").strip()
        if not raw_path:
            continue
        candidates: list[Path] = []
        source_path = Path(raw_path.rstrip("/"))
        if source_path.is_absolute():
            try:
                candidates.append(workspace / source_path.resolve(strict=False).relative_to(workspace))
            except ValueError:
                if raw_path.startswith("/app/"):
                    candidates.append(workspace / raw_path.removeprefix("/app/").rstrip("/"))
        else:
            candidates.append(workspace / raw_path)
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve(strict=False)
                resolved.relative_to(workspace)
            except ValueError:
                continue
            if resolved.exists() and resolved.is_dir() and resolved not in roots:
                roots.append(resolved)
            if len(roots) >= 6:
                return tuple(roots)
    return tuple(roots)


def _source_fact_nested_matches(token: str, source_roots: Iterable[Path], *, workspace: Path) -> list[str]:
    name = Path(token).name
    if not name or name in {".", ".."}:
        return []
    matches: list[str] = []
    for root in source_roots:
        visited_dirs = 0
        for dirpath, dirnames, filenames in os.walk(root):
            visited_dirs += 1
            if visited_dirs > _SOURCE_FACT_NESTED_MATCH_MAX_DIRS:
                break
            dirnames.sort()
            filenames.sort()
            current_dir = Path(dirpath)
            try:
                depth = len(current_dir.relative_to(root).parts)
            except ValueError:
                dirnames[:] = []
                continue
            if depth >= _SOURCE_FACT_NESTED_MATCH_MAX_DEPTH:
                dirnames[:] = []
            if name not in filenames:
                continue
            match = current_dir / name
            try:
                if not match.is_file():
                    continue
                rel = match.resolve(strict=False).relative_to(workspace).as_posix()
            except (OSError, ValueError):
                continue
            if rel not in matches:
                matches.append(rel)
            if len(matches) >= 4:
                return matches
    return matches


def _task_paths_from_text(text: object, *, workspace: str | Path | None = None) -> list[str]:
    raw = str(text or "")
    if not raw.strip():
        return []
    paths: list[str] = []
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError:
        tokens = []
    for token in tokens:
        candidate = _normalize_task_path_token(token, workspace=workspace)
        if candidate:
            paths.append(candidate)
    paths.extend(
        _normalize_task_path_token(match.group("path"), workspace=workspace) for match in _TASK_PATH_TOKEN_RE.finditer(raw)
    )
    return _dedupe_task_paths(path for path in paths if path)


def _normalize_task_path_token(token: object, *, workspace: str | Path | None = None) -> str:
    text = str(token or "").strip().strip("`'\"()[]{}<>").rstrip(".,:;").rstrip("/")
    if not text:
        return ""
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        return ""
    if text.startswith("-"):
        return ""
    if "://" in text:
        return ""
    if text.startswith("/") and workspace:
        workspace_path = Path(workspace).resolve()
        try:
            relative = Path(text).resolve().relative_to(workspace_path)
        except (OSError, ValueError):
            return ""
        text = relative.as_posix()
    if text.startswith(("/", "../", "/tmp/", "/var/tmp/")):
        return ""
    while text.startswith("./"):
        text = text[2:]
    if not _task_path_is_safe_relative(text):
        if workspace and _task_path_has_safe_segments(text) and (Path(workspace) / text).exists():
            return text
        return ""
    return text


def _task_path_has_safe_segments(path: object) -> bool:
    text = str(path or "").strip()
    if not text or "\\" in text or re.match(r"^[A-Za-z]:", text):
        return False
    if text.startswith(("/", "../")) or "/../" in text:
        return False
    parts = text.split("/")
    return not any(part in {"", ".", ".."} or part.startswith("..") for part in parts)


def _task_path_is_safe_relative(path: object) -> bool:
    text = str(path or "").strip()
    if not _task_path_has_safe_segments(text):
        return False
    return bool(_TASK_PATH_TOKEN_RE.fullmatch(text))


def _dedupe_task_paths(paths: Iterable[object]) -> list[str]:
    result: list[str] = []
    for path in paths:
        text = str(path or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= 12:
            break
    return result


def _compact_sidecar_digest_for_request(
    *,
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    transcript_items: list[NativeTranscriptItem],
    loop_signals: Mapping[str, object],
) -> dict[str, object]:
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id or _lane_attempt_id(lane_input),
        provider="codex" if _provider_is_live(lane_input) else "fake_native",
        model=str(lane_input.model or "gpt-5.5"),
        items=tuple(_provider_visible_native_item(item, lane_input=lane_input) for item in transcript_items),
    )
    return build_compact_native_sidecar_digest(
        transcript,
    )


def _native_loop_control_state(
    transcript_items: list[NativeTranscriptItem],
    *,
    current_turn_index: int,
    lane_input: ImplementLaneInput | None = None,
    task_contract: Mapping[str, object] | None = None,
) -> dict[str, object]:
    calls = [item for item in transcript_items if item.kind in CALL_ITEM_KINDS]
    write_count = sum(1 for item in calls if item.tool_name in WRITE_TOOL_NAMES or _native_call_is_source_mutating_exec(item))
    verifier_count = sum(1 for item in calls if _native_call_is_verifier(item))
    probe_count = sum(1 for item in calls if _native_call_is_probe_or_exec(item))
    command_count = sum(1 for item in calls if item.tool_name in EXEC_TOOL_NAMES)
    read_output_count = sum(1 for item in calls if item.tool_name == "read_command_output")
    turn_count = len({item.turn_id for item in transcript_items if item.turn_id})
    latest_failed_verifier = _latest_failed_verifier_output(transcript_items)
    post_failure_calls = _calls_after_sequence(calls, latest_failed_verifier.sequence if latest_failed_verifier else 0)
    post_failure_write_count = sum(1 for item in post_failure_calls if item.tool_name in WRITE_TOOL_NAMES)
    post_failure_probe_count = sum(1 for item in post_failure_calls if _native_call_is_probe_or_exec(item))
    post_failure_verifier_count = sum(1 for item in post_failure_calls if _native_call_is_verifier(item))
    first_write_probe_threshold, first_write_turn_threshold = _first_write_due_thresholds(
        lane_input,
        task_contract=task_contract,
    )
    first_write_due = bool(
        write_count == 0
        and verifier_count == 0
        and (
            probe_count >= first_write_probe_threshold
            or current_turn_index >= first_write_turn_threshold
        )
    )
    first_write_due_entry_turn = _first_write_due_entry_turn(
        transcript_items,
        current_turn_index=current_turn_index,
        probe_threshold=first_write_probe_threshold,
        turn_threshold=first_write_turn_threshold,
    )
    first_write_due_overrun = bool(
        first_write_due
        and first_write_due_entry_turn is not None
        and current_turn_index > first_write_due_entry_turn
    )
    prewrite_probe_plateau = bool(
        write_count == 0
        and verifier_count == 0
        and probe_count >= _PREWRITE_PROBE_PLATEAU_THRESHOLD
    )
    failed_verifier_probe_threshold = _failed_verifier_repair_probe_threshold(latest_failed_verifier)
    verifier_repair_due = bool(
        latest_failed_verifier
        and post_failure_write_count == 0
        and post_failure_probe_count >= failed_verifier_probe_threshold
    )
    return {
        "schema_version": 1,
        "surface": "native_loop_signals",
        "current_turn_index": current_turn_index,
        "observed_turn_count": turn_count,
        "tool_call_count": len(calls),
        "probe_count_without_write": probe_count if write_count == 0 else 0,
        "first_write_probe_threshold": first_write_probe_threshold,
        "first_write_turn_threshold": first_write_turn_threshold,
        "command_count_without_write": command_count if write_count == 0 else 0,
        "read_output_count_without_write": read_output_count if write_count == 0 else 0,
        "write_count": write_count,
        "verifier_count": verifier_count,
        "first_write_due": first_write_due,
        "first_write_due_entry_turn": first_write_due_entry_turn,
        "first_write_due_overrun": first_write_due_overrun,
        "first_write_grace_probe_calls": _FIRST_WRITE_DUE_GRACE_PROBE_CALLS if first_write_due else None,
        "prewrite_probe_plateau": prewrite_probe_plateau,
        "verifier_repair_due": verifier_repair_due,
        "latest_failed_verifier": _failed_verifier_payload(latest_failed_verifier),
        "post_failure_probe_count": post_failure_probe_count,
        "post_failure_verifier_count": post_failure_verifier_count,
        "post_failure_write_count": post_failure_write_count,
        "failed_verifier_repair_probe_threshold": failed_verifier_probe_threshold,
        "max_additional_probe_turns": (
            0
            if (verifier_repair_due or prewrite_probe_plateau or first_write_due_overrun)
            else (0 if first_write_due else None)
        ),
    }


def _first_write_due_entry_turn(
    transcript_items: list[NativeTranscriptItem],
    *,
    current_turn_index: int,
    probe_threshold: int = _FIRST_WRITE_DUE_PROBE_THRESHOLD,
    turn_threshold: int = _FIRST_WRITE_DUE_TURN_THRESHOLD,
) -> int | None:
    for turn_index in range(1, max(1, current_turn_index) + 1):
        prior_calls = [
            item
            for item in transcript_items
            if item.kind in CALL_ITEM_KINDS and _turn_number(item.turn_id) < turn_index
        ]
        write_count = sum(
            1 for item in prior_calls if item.tool_name in WRITE_TOOL_NAMES or _native_call_is_source_mutating_exec(item)
        )
        verifier_count = sum(1 for item in prior_calls if _native_call_is_verifier(item))
        if write_count or verifier_count:
            return None
        probe_count = sum(1 for item in prior_calls if _native_call_is_probe_or_exec(item))
        if probe_count >= probe_threshold or turn_index >= turn_threshold:
            return turn_index
    return current_turn_index if current_turn_index >= turn_threshold else None


def _first_write_due_thresholds(
    lane_input: ImplementLaneInput | None,
    *,
    task_contract: Mapping[str, object] | None = None,
) -> tuple[int, int]:
    candidate = lane_input.task_contract if lane_input is not None else task_contract
    if is_hard_runtime_artifact_task(candidate):
        return _FIRST_WRITE_DUE_HARD_RUNTIME_PROBE_THRESHOLD, _FIRST_WRITE_DUE_HARD_RUNTIME_TURN_THRESHOLD
    return _FIRST_WRITE_DUE_PROBE_THRESHOLD, _FIRST_WRITE_DUE_TURN_THRESHOLD


def _native_call_is_prewrite_probe(item: NativeTranscriptItem) -> bool:
    if item.tool_name in READ_ONLY_TOOL_NAMES:
        return True
    if item.tool_name not in EXEC_TOOL_NAMES:
        return False
    if _native_call_is_source_mutating_exec(item):
        return False
    if item.tool_name in {"poll_command", "cancel_command", "read_command_output"}:
        return False
    if item.tool_name == "run_tests":
        return True
    arguments, _ = _arguments(item)
    command_intent = str(arguments.get("command_intent") or arguments.get("intent") or "").strip().casefold()
    return command_intent in {"", "probe", "diagnostic", "inspect", "read", "analysis"}


def _native_call_is_source_mutating_exec(item: NativeTranscriptItem) -> bool:
    if item.tool_name not in {"run_command", "exec_command"}:
        return False
    arguments, _ = _arguments(item)
    command_intent = str(arguments.get("command_intent") or arguments.get("intent") or "").strip().casefold()
    return command_intent in _SOURCE_MUTATION_COMMAND_INTENTS


def _failed_verifier_repair_probe_threshold(item: NativeTranscriptItem | None) -> int:
    if item is None:
        return _FAILED_VERIFIER_REPAIR_PROBE_THRESHOLD
    status = str(item.status or "").strip().casefold()
    if status in {"interrupted", "killed", "timed_out", "orphaned"}:
        return 1
    return _FAILED_VERIFIER_REPAIR_PROBE_THRESHOLD


def _native_call_is_probe_or_exec(item: NativeTranscriptItem) -> bool:
    if _native_call_is_source_mutating_exec(item):
        return False
    return item.tool_name in READ_ONLY_TOOL_NAMES or item.tool_name in EXEC_TOOL_NAMES


def _calls_after_sequence(calls: list[NativeTranscriptItem], sequence: int) -> list[NativeTranscriptItem]:
    if sequence <= 0:
        return []
    return [item for item in calls if item.sequence > sequence]


def _latest_failed_verifier_output(transcript_items: list[NativeTranscriptItem]) -> NativeTranscriptItem | None:
    calls_by_id = {
        item.call_id: item
        for item in transcript_items
        if item.kind in CALL_ITEM_KINDS and item.call_id and _native_call_is_verifier(item)
    }
    verifier_command_run_ids = _verifier_command_run_ids(transcript_items, verifier_call_ids=set(calls_by_id))
    all_calls_by_id = {
        item.call_id: item
        for item in transcript_items
        if item.kind in CALL_ITEM_KINDS and item.call_id
    }
    for item in reversed(transcript_items):
        if item.kind not in OUTPUT_ITEM_KINDS:
            continue
        if not _output_belongs_to_verifier(
            item,
            verifier_call_ids=set(calls_by_id),
            verifier_command_run_ids=verifier_command_run_ids,
            calls_by_id=all_calls_by_id,
        ):
            continue
        if not _native_output_is_terminal(item):
            continue
        return item if _native_output_is_failure(item) else None
    return None


def _verifier_command_run_ids(
    transcript_items: list[NativeTranscriptItem],
    *,
    verifier_call_ids: set[str],
) -> set[str]:
    command_run_ids: set[str] = set()
    for item in transcript_items:
        if item.kind not in OUTPUT_ITEM_KINDS or item.call_id not in verifier_call_ids:
            continue
        command_run_id = _command_run_id_from_output_text(item.output_text_or_ref)
        if command_run_id:
            command_run_ids.add(command_run_id)
    return command_run_ids


def _output_belongs_to_verifier(
    item: NativeTranscriptItem,
    *,
    verifier_call_ids: set[str],
    verifier_command_run_ids: set[str],
    calls_by_id: Mapping[str, NativeTranscriptItem],
) -> bool:
    if item.call_id in verifier_call_ids:
        return True
    call = calls_by_id.get(item.call_id)
    if call is None or call.tool_name not in {"poll_command", "cancel_command"}:
        return False
    return _command_run_id_from_call(call) in verifier_command_run_ids


def _command_run_id_from_call(item: NativeTranscriptItem) -> str:
    arguments, error = _arguments(item)
    if error:
        return ""
    return str(arguments.get("command_run_id") or "").strip()


def _command_run_id_from_output_text(value: str) -> str:
    match = _COMMAND_RUN_ID_RE.search(str(value or ""))
    if not match:
        return ""
    return str(match.group("id") or match.group("session") or "").strip()


def _native_output_is_terminal(item: NativeTranscriptItem) -> bool:
    status = str(item.status or "").strip().casefold()
    return bool(status and status not in {"yielded", "running", "pending"})


def _native_output_is_failure(item: NativeTranscriptItem) -> bool:
    status = str(item.status or "").strip().casefold()
    return bool(
        item.is_error
        or status in {"failed", "interrupted", "invalid", "blocked", "timed_out", "killed", "orphaned"}
        or _native_output_has_semantic_verifier_failure(item)
    )


def _native_output_has_semantic_verifier_failure(item: NativeTranscriptItem) -> bool:
    if str(item.status or "").strip().casefold() not in {"completed", "failed"}:
        return False
    return _semantic_verifier_failure_text_matches(item.output_text_or_ref)


def _tool_result_has_semantic_verifier_failure(result: ToolResultEnvelope) -> bool:
    if str(result.status or "").strip().casefold() not in {"completed", "failed"}:
        return False
    return _semantic_verifier_failure_text_matches(result.natural_result_text(limit=5000))


def _semantic_verifier_failure_text_matches(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    return any(pattern.search(text) for pattern in _SEMANTIC_VERIFIER_FAILURE_PATTERNS)


def _failed_verifier_payload(item: NativeTranscriptItem | None) -> dict[str, object] | None:
    if item is None:
        return None
    return {
        "turn_id": item.turn_id,
        "call_id": item.call_id,
        "tool_name": item.tool_name,
        "status": item.status,
        "semantic_failure": _native_output_has_semantic_verifier_failure(item),
        "summary": _truncate_control_text(item.output_text_or_ref),
        "evidence_refs": list(item.evidence_refs[:6]),
    }


def _truncate_control_text(value: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= _CONTROL_FAILURE_SUMMARY_LIMIT:
        return text
    return text[: _CONTROL_FAILURE_SUMMARY_LIMIT - 1].rstrip() + "…"


def _native_call_is_verifier(item: NativeTranscriptItem) -> bool:
    if item.tool_name == "run_tests":
        return True
    if item.tool_name not in {"run_command", "exec_command"}:
        return False
    arguments, _ = _arguments(item)
    command_intent = str(arguments.get("command_intent") or arguments.get("intent") or "").strip().casefold()
    if command_intent in {"verify", "verifier", "verification", "finish_verifier", "test", "acceptance"}:
        return True
    command = str(arguments.get("command") or arguments.get("cmd") or "")
    lowered = command.casefold()
    return bool(
        re.search(
            r"(?:^|[\s;&|()])(?:pytest|npm\s+test|cargo\s+test|go\s+test|prove|verifier)(?:$|[\s;&|()])",
            lowered,
        )
    )


def _responses_input_item_from_transcript_item(item: NativeTranscriptItem) -> dict[str, object]:
    if item.kind == "input_message":
        return {"role": "user", "content": [{"type": "input_text", "text": item.output_text_or_ref}]}
    if item.kind == "assistant_message":
        return {"role": "assistant", "content": [{"type": "output_text", "text": item.output_text_or_ref}]}
    if item.kind == "reasoning":
        # Do not synthesize invalid stateless Responses reasoning input from a
        # local ref. A later reasoning-sidecar slice can carry encrypted
        # provider content forward when the bytes are persisted.
        return {}
    if item.kind in {"function_call", "finish_call"}:
        return {
            "type": "function_call",
            "id": item.provider_item_id,
            "call_id": item.call_id,
            "name": item.tool_name,
            "arguments": item.arguments_json_text or "{}",
        }
    if item.kind == "custom_tool_call":
        return {
            "type": "custom_tool_call",
            "id": item.provider_item_id,
            "call_id": item.call_id,
            "name": item.tool_name,
            "input": item.custom_input_text,
        }
    if item.kind == "custom_tool_call_output":
        return build_custom_tool_call_output_input_item(
            call_id=item.call_id,
            name=item.tool_name,
            output=item.output_text_or_ref,
        )
    if item.kind in {"function_call_output", "finish_output"}:
        return build_function_call_output_input_item(call_id=item.call_id, output=item.output_text_or_ref)
    return {}


def _response_output_input_items(
    transcript_items: tuple[NativeTranscriptItem, ...],
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in transcript_items:
        if item.kind not in {"assistant_message", "reasoning", "function_call", "custom_tool_call", "finish_call"}:
            continue
        converted = _responses_input_item_from_transcript_item(item)
        if converted:
            items.append(converted)
    return items


def _provider_visible_native_item(
    item: NativeTranscriptItem,
    *,
    lane_input: ImplementLaneInput,
) -> NativeTranscriptItem:
    if _native_tool_available("write_file", lane_input=lane_input, lane_config=lane_input.lane_config):
        return item
    output_text = hide_unavailable_write_file_guidance(item.output_text_or_ref)
    if item.tool_name != "write_file":
        if output_text == item.output_text_or_ref:
            return item
        return replace(item, output_text_or_ref=output_text)
    if item.kind in {"function_call", "custom_tool_call"}:
        return replace(
            item,
            tool_name="unavailable_write_tool",
            arguments_json_text='{"unavailable_tool":true,"redacted_arguments":true}',
            custom_input_text="",
            output_text_or_ref=output_text,
        )
    return replace(
        item,
        tool_name="unavailable_write_tool",
        output_text_or_ref=output_text,
    )


def _mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _provider_safe_input_items(value: object) -> list[dict[str, object]]:
    items = []
    for item in _mapping_list(value):
        if item.get("type") == "reasoning" and not item.get("encrypted_content"):
            continue
        items.append(item)
    return items


def _reasoning_config(lane_input: ImplementLaneInput) -> dict[str, object] | bool:
    effort = str(lane_input.effort or os.environ.get("MEW_CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT))
    effort = effort.strip()
    if not effort or effort.lower() in {"none", "off", "false"}:
        return False
    return {"effort": effort}


def _native_surface_for_provider(provider: object) -> dict[str, object]:
    live = not isinstance(provider, NativeFakeProvider)
    surface = dict(PHASE3_NATIVE_SURFACE)
    if live:
        surface.update(
            {
                "transport_kind": "provider_native",
                "native_transport_kind": "provider_native",
                "provider_native_tool_loop": True,
                "provider": str(getattr(provider, "provider", "openai")),
                "model": str(getattr(provider, "model", "")),
            }
        )
    return surface


def _provider_is_live(lane_input: ImplementLaneInput) -> bool:
    return str(lane_input.model_backend or "").strip().lower() in {"codex", "openai"}


def _artifact_root(lane_input: ImplementLaneInput) -> Path | None:
    raw = str(lane_input.lane_config.get("artifact_dir") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve(strict=False)


def _emit_progress(progress, line: str) -> None:
    if progress:
        progress(line)


def _live_failure_lane_result(
    lane_input: ImplementLaneInput,
    *,
    error: str,
    provider: NativeCodexResponsesProvider,
) -> ImplementLaneResult:
    lane_attempt_id = _lane_attempt_id(lane_input)
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider.provider,
        model=provider.model,
    )
    proof_artifacts = _write_live_failure_artifacts(
        lane_input,
        transcript=transcript,
        provider=provider,
        error=error,
    )
    return ImplementLaneResult(
        status="failed",
        lane="implement_v2",
        user_visible_summary=f"implement_v2 native provider failed: {error}",
        proof_artifacts=proof_artifacts,
        updated_lane_state={
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "transport_kind": "provider_native",
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
            "requested_task_id": lane_input.task_id,
        },
        metrics={
            **_native_surface_for_provider(provider),
            "status": "failed",
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "provider": provider.provider,
            "model": provider.model,
            "transcript_hash": native_transcript_hash(transcript),
            "error": error,
            "turn_count": len(provider.requests),
            "provider_request_inventory_available": bool(provider.requests),
        },
    )


def _partial_failure_harness_result(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    items: list[NativeTranscriptItem],
    tool_results: tuple[ToolResultEnvelope, ...],
    artifact_root: str | Path | None,
    error: str,
) -> NativeImplementV2HarnessResult:
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=str(getattr(provider, "provider", "")),
        model=str(getattr(provider, "model", "")),
        items=tuple(items),
    )
    validation = validate_native_transcript_pairing(transcript)
    if not validation.valid:
        raise InvalidNativeTranscriptError(f"invalid native transcript: {', '.join(validation.errors)}")
    metrics = {
        **_native_surface_for_provider(provider),
        "status": "failed",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transcript_hash": native_transcript_hash(transcript),
        "error": error,
        "turn_count": len(getattr(provider, "requests", []) or ()),
        "provider_request_inventory_available": bool(getattr(provider, "requests", []) or ()),
        "pairing": validation.as_dict(),
    }
    proof_artifacts: tuple[str, ...] = ()
    if artifact_root is not None:
        if isinstance(provider, NativeCodexResponsesProvider):
            proof_artifacts = _write_live_failure_artifacts(
                lane_input,
                transcript=transcript,
                provider=provider,
                tool_results=tool_results,
                error=error,
                artifact_root=Path(artifact_root),
            )
        else:
            paths = _write_native_artifacts(
                Path(artifact_root),
                transcript,
                tool_results=tool_results,
                provider=provider,
                status="failed",
                error=error,
            )
            proof_artifacts = tuple(str(path) for path in paths.values())
    return NativeImplementV2HarnessResult(
        status="failed",
        transcript=transcript,
        proof_artifacts=proof_artifacts,
        metrics=metrics,
        finish_summary=f"native provider failed: {error}",
    )


def _write_live_failure_artifacts(
    lane_input: ImplementLaneInput,
    *,
    transcript: NativeTranscript,
    provider: NativeCodexResponsesProvider,
    tool_results: tuple[ToolResultEnvelope, ...] = (),
    error: str,
    artifact_root: Path | None = None,
) -> tuple[str, ...]:
    root_path = artifact_root or _artifact_root(lane_input)
    if root_path is None:
        return ()
    root = Path(root_path)
    root.mkdir(parents=True, exist_ok=True)
    paths = write_native_transcript_artifacts(root, transcript)
    paths.update(_write_native_tool_result_sidecars(root, tool_results=tool_results))
    paths.update(_write_native_render_output_sidecar(root, transcript))
    route_records = _route_records_with_tool_surface(
        route_records_from_results(tool_results),
        provider=provider,
    )
    tool_routes_path = root / "tool_routes.jsonl"
    tool_routes_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in route_records),
        encoding="utf-8",
    )
    paths["tool_routes"] = tool_routes_path
    request_path = root / "native-provider-requests.json"
    inventory_path = root / "provider-request-inventory.json"
    response_count = len(provider.responses)
    rejected_response_count = len(provider.rejected_responses)
    failure_status = (
        "failed_before_completed_native_response"
        if rejected_response_count
        else "failed_before_native_response"
    )
    request_payload = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "status": failure_status,
        "error": str(error),
        "request_count": len(provider.requests),
        "response_count": response_count,
        "rejected_response_count": rejected_response_count,
        "requests": list(provider.requests),
        "responses": list(provider.responses),
        "rejected_responses": list(provider.rejected_responses),
    }
    inventory_payload = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "status": failure_status,
        "error": str(error),
        "request_count": len(provider.requests),
        "response_count": response_count,
        "rejected_response_count": rejected_response_count,
        "provider_request_inventory": [
            request.get("provider_request_inventory")
            for request in provider.requests
            if isinstance(request.get("provider_request_inventory"), dict)
        ],
        "provider_response_statuses": [
            response.get("status")
            for response in provider.responses
            if isinstance(response, dict)
        ],
        "rejected_provider_response_statuses": [
            response.get("status")
            for response in provider.rejected_responses
            if isinstance(response, dict)
        ],
    }
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return tuple(str(path) for path in (*paths.values(), request_path, inventory_path))


def _route_records_with_tool_surface(
    route_records: tuple[dict[str, object], ...],
    *,
    provider: object,
) -> tuple[dict[str, object], ...]:
    metadata_by_turn = _provider_tool_surface_metadata_by_turn(provider)
    if not metadata_by_turn:
        return route_records
    augmented: list[dict[str, object]] = []
    for record in route_records:
        turn_index = _safe_int(record.get("turn_index"), default=0)
        metadata = metadata_by_turn.get(turn_index) or metadata_by_turn.get(-1) or {}
        item = dict(record)
        item["tool_surface_profile_id"] = metadata.get("profile_id", "")
        item["tool_surface_profile_hash"] = metadata.get("profile_hash", "")
        item["tool_surface_route_table_hash"] = metadata.get("route_table_hash", "")
        item["tool_surface_descriptor_hash"] = metadata.get("descriptor_hash", "")
        augmented.append(item)
    return tuple(augmented)


def _provider_tool_surface_metadata_by_turn(provider: object) -> dict[int, Mapping[str, object]]:
    requests = getattr(provider, "requests", None)
    if not isinstance(requests, list):
        return {}
    by_turn: dict[int, Mapping[str, object]] = {}
    for request in reversed(requests):
        if not isinstance(request, Mapping):
            continue
        tool_surface = request.get("tool_surface")
        if isinstance(tool_surface, Mapping):
            turn_index = _safe_int(request.get("turn_index"), default=0)
            if turn_index:
                by_turn.setdefault(turn_index, tool_surface)
            by_turn.setdefault(-1, tool_surface)
    return by_turn


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _approved_write_calls(lane_config: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    raw = lane_config.get("approved_write_calls")
    return tuple(dict(item) for item in raw) if isinstance(raw, list) else ()


def _side_effect_id_valid(call: NativeTranscriptItem) -> bool:
    return bool(call.call_id and call.provider_item_id)


def _result_is_write_like(result: ToolResultEnvelope) -> bool:
    if result.tool_name in WRITE_TOOL_NAMES and result.status == "completed" and not result.is_error:
        return True
    return any(
        str(effect.get("kind") or "") in {"file_write", "source_tree_delta", "source_tree_mutation"}
        for effect in result.side_effects
    )


def _result_is_verifier_like(result: ToolResultEnvelope) -> bool:
    if result.tool_name == "run_tests":
        return True
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return str(payload.get("command_intent") or "") == "verifier"


def _native_output_status(call: NativeTranscriptItem, result: ToolResultEnvelope) -> str:
    if call.kind == "finish_call":
        payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
        if result.is_error and str(payload.get("outcome") or "").strip().lower() in {
            "blocked",
            "blocked_continue",
            "blocked_return",
            "continue",
        }:
            return "blocked"
    return result.status


def _native_turn_has_assistant_message(items: tuple[NativeTranscriptItem, ...]) -> bool:
    return any(item.kind == "assistant_message" and item.output_text_or_ref.strip() for item in items)


def _native_no_tool_continuation_item(
    items: tuple[NativeTranscriptItem, ...],
    *,
    lane_attempt_id: str,
    provider: str,
    model: str,
    turn_index: int,
    sequence: int,
    latest_resolver_decision: CompletionResolverDecision | None,
) -> NativeTranscriptItem:
    lines = [
        "Continue with native tool calls.",
        "Assistant text is not a completion signal for this implement_v2 lane.",
        "If the task is complete, call finish with fresh verifier/artifact evidence.",
        "If it is not complete, call a tool to verify or repair from the latest concrete result.",
    ]
    if latest_resolver_decision is not None and latest_resolver_decision.lane_status == "blocked_continue":
        blockers = _bounded_finish_block_items(latest_resolver_decision.blockers, limit=4)
        missing = _bounded_finish_block_items(
            (_compact_finish_missing_obligation(item) for item in latest_resolver_decision.missing_obligations),
            limit=6,
        )
        lines.append(f"Previous finish was blocked: {_finish_block_headline(blockers, missing)}.")
        if missing:
            lines.append("Missing evidence: " + ", ".join(missing) + ".")
    assistant_text = _native_first_assistant_text(items)
    if assistant_text:
        lines.append(f"Last assistant text was not accepted as completion: {assistant_text}")
    return NativeTranscriptItem(
        sequence=sequence,
        turn_id=f"turn-{turn_index}-continuation",
        kind="input_message",
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        output_text_or_ref="\n".join(lines),
    )


def _native_first_assistant_text(items: tuple[NativeTranscriptItem, ...]) -> str:
    for item in items:
        if item.kind == "assistant_message":
            return _finish_block_clip(item.output_text_or_ref, limit=160)
    return ""


def _call_order_key(call: NativeTranscriptItem) -> tuple[int, int]:
    return (call.output_index, call.sequence)


def _write_native_artifacts(
    root: Path,
    transcript: NativeTranscript,
    *,
    tool_results: tuple[ToolResultEnvelope, ...],
    provider: object,
    status: str = "",
    error: str = "",
    resolver_decisions: tuple[CompletionResolverDecision, ...] = (),
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...] = (),
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Path]:
    paths = write_native_transcript_artifacts(root, transcript)
    paths.update(_write_native_tool_result_sidecars(root, tool_results=tool_results))
    paths.update(_write_native_render_output_sidecar(root, transcript))
    route_records = _route_records_with_tool_surface(
        route_records_from_results(tool_results),
        provider=provider,
    )
    tool_routes_path = root / "tool_routes.jsonl"
    tool_routes_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in route_records),
        encoding="utf-8",
    )
    paths["tool_routes"] = tool_routes_path
    if resolver_decisions:
        paths.update(
            write_completion_resolver_artifacts(
                root,
                resolver_decisions,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if native_finish_gate_decisions:
        paths.update(
            write_native_finish_gate_artifacts(
                root,
                native_finish_gate_decisions,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if finish_verifier_planner_decisions:
        planner_requests_path: Path | None = None
        if finish_verifier_planner_requests:
            planner_requests_path = root / _FINISH_VERIFIER_PLANNER_REQUESTS_FILE
            planner_requests_path.write_text(
                "".join(
                    json.dumps(_json_safe_native(dict(record)), ensure_ascii=False, sort_keys=True) + "\n"
                    for record in finish_verifier_planner_requests
                ),
                encoding="utf-8",
            )
            paths["finish_verifier_planner_requests"] = planner_requests_path
        planner_decisions_path = root / _FINISH_VERIFIER_PLANNER_DECISIONS_FILE
        planner_decisions_path.write_text(
            "".join(
                json.dumps(_json_safe_native(dict(record)), ensure_ascii=False, sort_keys=True) + "\n"
                for record in finish_verifier_planner_decisions
            ),
            encoding="utf-8",
        )
        paths["finish_verifier_planner_decisions"] = planner_decisions_path
        if paths.get("proof_manifest") is not None:
            _patch_proof_manifest_with_finish_verifier_planner_decisions(
                paths["proof_manifest"],
                decision_path=planner_decisions_path,
                records=finish_verifier_planner_decisions,
                request_path=planner_requests_path,
                request_records=finish_verifier_planner_requests,
            )
    paths.update(
        write_native_evidence_observation(
            root,
            transcript,
            resolver_decisions=resolver_decisions,
            proof_manifest_path=paths.get("proof_manifest"),
        )
    )
    paths.update(_write_provider_request_artifacts(root, provider=provider, status=status, error=error))
    if not isinstance(provider, NativeFakeProvider):
        return paths
    for key in ("transcript_metrics", "proof_manifest"):
        path = paths[key]
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["transport_kind"] = "fake_native"
        payload["native_transport_kind"] = "provider_native"
        if isinstance(payload.get("metrics"), dict):
            payload["metrics"]["transport_kind"] = "fake_native"
            payload["metrics"]["native_transport_kind"] = "provider_native"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


def _write_native_tool_result_sidecars(
    root: Path,
    *,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, Path]:
    """Write derived tool-result sidecars for native transcript artifacts."""

    tool_results_path = root / "tool_results.jsonl"
    tool_result_index_path = root / "tool_result_index.json"
    evidence_sidecar_path = root / "evidence_sidecar.json"
    evidence_ref_index_path = root / "evidence_ref_index.json"
    write_jsonl(tool_results_path, tool_results_jsonl_lines(tool_results))
    tool_result_index = build_tool_result_index_artifact(tool_results)
    evidence_sidecar = build_evidence_sidecar_artifact(tool_results)
    evidence_ref_index = build_evidence_ref_index_artifact(evidence_sidecar)
    tool_result_index_path.write_text(
        json.dumps(tool_result_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence_sidecar_path.write_text(
        json.dumps(evidence_sidecar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence_ref_index_path.write_text(
        json.dumps(evidence_ref_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "tool_results": tool_results_path,
        "tool_result_index": tool_result_index_path,
        "evidence_sidecar": evidence_sidecar_path,
        "evidence_ref_index": evidence_ref_index_path,
    }


def _write_native_render_output_sidecar(root: Path, transcript: NativeTranscript) -> dict[str, Path]:
    """Write renderer observability for provider-visible paired outputs."""

    records: list[dict[str, object]] = []
    for item in transcript.items:
        if item.kind not in OUTPUT_ITEM_KINDS or not item.metrics_ref:
            continue
        records.append(
            render_observability_record(
                metrics_ref=item.metrics_ref,
                tool_name=item.tool_name,
                call_id=item.call_id,
                output_text=item.output_text_or_ref,
            )
        )
    if not records:
        return {}
    path = root / "tool_render_outputs.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return {"tool_render_outputs": path}


def _provider_request_records(provider: object) -> tuple[dict[str, object], ...]:
    requests = getattr(provider, "requests", None)
    if not isinstance(requests, list):
        return ()
    return tuple(dict(request) for request in requests if isinstance(request, Mapping))


def _write_provider_request_artifacts(
    root: Path,
    *,
    provider: object,
    status: str = "",
    error: str = "",
) -> dict[str, Path]:
    requests = _provider_request_records(provider)
    if not requests:
        return {}
    request_path = root / "native-provider-requests.json"
    inventory_path = root / "provider-request-inventory.json"
    request_payload: dict[str, object] = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "status": status or "unknown",
        "request_count": len(requests),
        "requests": list(requests),
    }
    if error:
        request_payload["error"] = str(error)
    inventory_payload: dict[str, object] = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "status": status or "unknown",
        "request_count": len(requests),
        "provider_request_inventory": [
            request.get("provider_request_inventory")
            for request in requests
            if isinstance(request.get("provider_request_inventory"), dict)
        ],
    }
    if error:
        inventory_payload["error"] = str(error)
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "native_provider_requests": request_path,
        "provider_request_inventory": inventory_path,
    }


def _finish_summary(call: NativeTranscriptItem) -> str:
    arguments, _ = _arguments(call)
    return str(arguments.get("summary") or "native implement_v2 finished")


def _turn_number(turn_id: str) -> int:
    try:
        return int(str(turn_id).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _lane_attempt_id(lane_input: ImplementLaneInput) -> str:
    return f"{lane_input.work_session_id}:{lane_input.task_id}:implement_v2:native"
