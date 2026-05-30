"""Phase 3 native implement_v2 harness over provider-native transcript items."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Iterable, Mapping

from . import finish_verifier_planner as _finish_planner
from . import native_completion_policy as _completion_policy
from . import native_artifact_writer as _artifact_writer
from . import native_request_builder as _request_builder
from . import native_finish_closeout_policy as _closeout_policy
from . import native_finish_gate as _finish_gate
from .completion_resolver import (
    CompletionResolver,
    CompletionResolverDecision,
)
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .finish_verifier_planner_policy import finish_verifier_planner_policy
from .finish_acceptance_helpers import finish_typed_evidence_refs
from .native_fake_provider import PHASE3_TRANSPORT_CHANGE, NativeFakeProvider
from .native_finish_gate import (
    NativeFinishGateDecision,
)
from .native_provider_adapter import (
    NativeResponsesStreamParseResult,
    apply_previous_response_delta,
    call_codex_native_responses,
    call_codex_native_responses_websocket,
)
from .native_done_candidate import (
    NativeDoneCandidate,
    build_native_done_candidate,
)
from .native_ng_resume import (
    NativeNgResumeSignal,
    build_native_ng_resume_signal,
    native_ng_resume_input_item,
)
from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    OUTPUT_ITEM_KINDS,
    native_transcript_hash,
    normalize_codex_response_items,
    validate_native_transcript_pairing,
)
from .read_runtime import READ_ONLY_TOOL_NAMES, execute_read_only_tool_call
from .tool_guidance import (
    hide_unavailable_write_file_guidance,
    is_hard_runtime_artifact_task,
)
from .tool_registry import (
    CODEX_HOT_PATH_PROFILE_ID,
    ToolSurfaceSnapshot,
    build_tool_surface_snapshot,
    tool_surface_profile_id,
)
from .tool_specs import ImplementLaneToolSpec
from .tool_result_renderer import render_tool_result_for_profile
from .tool_routes import with_tool_route_decision
from .types import ImplementLaneInput, ImplementLaneResult, ToolCallEnvelope, ToolResultEnvelope
from .. import codex_api as _codex_api
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime


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
_NG_CONTINUE_CONSECUTIVE_LIMIT = 2
_NG_DECISION_TOTAL_LIMIT = 3
_INTERNAL_CLOSEOUT_CALL_PREFIXES = ("call-final-verifier-closeout-", "call-active-command-closeout-")
_NATIVE_MODEL_TIMEOUT_RESERVE_SECONDS = 10.0
_NATIVE_MODEL_TIMEOUT_MIN_SECONDS = 30.0
_SOURCE_MUTATION_COMMAND_INTENTS = frozenset(
    {"implement", "implementation", "write", "edit", "mutation", "source_mutation"}
)
_COMMAND_RUN_ID_RE = re.compile(
    r"(?:^|[\s;,])command_run_id=(?P<id>[^\s;,]+)"
    r"|Process running with command_id (?P<command_id>[^\s]+)"
    r"|Process running with session ID (?P<session>[^\s]+)"
)
_COMMAND_OUTPUT_REF_RE = re.compile(r"implement-v2-exec://[^/\s]+/(?P<id>[^/\s]+)/output")
_TASK_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./\\:-])(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:js|mjs|cjs|ts|tsx|jsx|py|pyx|c|h|cc|cpp|hpp|rs|go|java|sh|rb|php|pl|lua|json|yaml|yml|toml|md|txt|html|css|"
    r"wasm|bin|out|so|dylib|exe|png|ppm|bmp|jpg|jpeg|gif|svg))"
    r"(?![\w.-])"
)
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
    lane: str = "implement_v2"

    def as_lane_result(self) -> ImplementLaneResult:
        return ImplementLaneResult(
            status=self.status,
            lane=self.lane,
            user_visible_summary=self.finish_summary,
            proof_artifacts=self.proof_artifacts,
            metrics=self.metrics,
        )


_NativeCloseoutEvent = _closeout_policy.NativeCloseoutEvent
_NativeCloseoutContext = _closeout_policy.NativeCloseoutContext


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
            default=300.0,
        )
        prompt = _finish_planner.finish_verifier_planner_prompt(request)
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
        max_active=_native_exec_max_active(lane_config),
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
    done_candidates: list[NativeDoneCandidate] = []
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
    no_tool_repeat_done_candidate_count = 0
    latest_no_tool_continuation: dict[str, object] = {}
    last_no_tool_continuation_progress_fingerprint = ""
    ng_continue_total_count = 0
    ng_continue_consecutive_count = 0
    ng_continue_consecutive_max = 0
    repeat_plateau_count = 0
    last_ng_progress_fingerprint = ""
    last_ng_plateau_signature = ""
    latest_ng_plateau_signature = ""
    resolver_decisions: list[CompletionResolverDecision] = []
    native_finish_gate_decisions: list[NativeFinishGateDecision] = []
    ng_resume_signals: list[NativeNgResumeSignal] = []
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

    def run_internal_finish_gate_for_done_candidate(
        done_candidate: NativeDoneCandidate,
        *,
        turn_index: int,
    ) -> NativeFinishGateDecision:
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
            done_candidate_id=done_candidate.done_candidate_id,
        )
        for closeout_event in closeout_events:
            append_closeout_event(closeout_event)
        return _finish_gate.finish_gate_decision_from_done_candidate(
            done_candidate,
            lane_input=lane_input,
            lane_config=lane_config,
            provider=provider,
            turn_index=turn_index,
            transcript_items=tuple(items),
            closeout_events=closeout_events,
            closeout_context=closeout_context,
        )

    for turn_index in range(1, max_turns + 1):
        turn_timeout = _native_next_model_timeout_seconds(
            lane_input,
            run_started=start_monotonic,
            requested_timeout=getattr(provider, "timeout", None),
        )
        if turn_timeout is not None:
            if turn_timeout < _NATIVE_MODEL_TIMEOUT_MIN_SECONDS:
                active_closeouts = _closeout_policy.native_active_command_closeouts(
                    lane_input,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    exec_runtime=exec_runtime,
                    start_monotonic=start_monotonic,
                )
                for active_call, active_result, active_latency in active_closeouts:
                    append_closeout_event(
                        _NativeCloseoutEvent(
                            kind="active_command",
                            call=active_call,
                            result=active_result,
                            latency=active_latency,
                            reason="native active command closeout ran before low-budget provider turn",
                        )
                    )
                if active_closeouts:
                    active_result = active_closeouts[-1][1]
                    final_closeout = None
                    if active_result.status == "completed" and not _closeout_policy.native_active_command_run_id(exec_runtime):
                        final_closeout = _closeout_policy.native_final_verifier_closeout(
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
                        closeout_context = _closeout_policy.native_closeout_context_from_result(closeout_call, closeout_result)
                        native_decision = _finish_gate.finish_gate_decision_from_controller_closeout_event(
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
                done_candidates=tuple(done_candidates),
                native_finish_gate_decisions=tuple(native_finish_gate_decisions),
                ng_resume_signals=tuple(ng_resume_signals),
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
            model_progress_fingerprint = _native_model_tool_progress_fingerprint(tuple(tool_results))
            no_tool_reason = (
                "no_tool_repeat"
                if last_no_tool_continuation_progress_fingerprint
                and last_no_tool_continuation_progress_fingerprint == model_progress_fingerprint
                else "assistant_message_without_tool_call"
            )
            transcript_before_gate = NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider=provider.provider,
                model=provider.model,
                items=tuple(items),
            )
            done_candidate = build_native_done_candidate(
                transcript_before_gate,
                turn_items,
                compact_sidecar_digest_hash=_request_compact_sidecar_digest_hash(request_descriptor),
                reason=no_tool_reason,
            )
            if done_candidate is not None:
                assistant_final_text = _native_final_assistant_response_text(turn_items)
                done_candidates.append(done_candidate)
                native_decision = run_internal_finish_gate_for_done_candidate(
                    done_candidate,
                    turn_index=turn_index,
                )
                if no_tool_reason == "no_tool_repeat" or native_decision.lane_status == "blocked_continue":
                    ng_plateau_signature = _native_ng_plateau_signature(
                        native_decision,
                        tool_results=tuple(tool_results),
                    )
                    latest_ng_plateau_signature = ng_plateau_signature
                    native_decision, repeat_increment = _native_apply_ng_resume_policy(
                        native_decision,
                        no_tool_reason=no_tool_reason,
                        ng_continue_total_count=ng_continue_total_count,
                        ng_continue_consecutive_count=ng_continue_consecutive_count,
                        current_progress_fingerprint=model_progress_fingerprint,
                        last_progress_fingerprint=last_ng_progress_fingerprint,
                        current_plateau_signature=ng_plateau_signature,
                        last_plateau_signature=last_ng_plateau_signature,
                    )
                    repeat_plateau_count += repeat_increment
                native_finish_gate_decisions.append(native_decision)
                finish_gate_decision = native_decision.as_dict()
                if native_decision.result == "block":
                    finish_gate_block_count += 1
                if native_decision.lane_status == "completed":
                    status = "completed"
                    finish_summary = assistant_final_text or native_decision.reason
                    break
                if no_tool_reason == "no_tool_repeat":
                    no_tool_repeat_done_candidate_count += 1
                    latest_no_tool_continuation = {
                        "turn_index": turn_index,
                        "assistant_text": _native_first_assistant_text(turn_items),
                        "continuation": "",
                        "done_candidate_id": done_candidate.done_candidate_id,
                        "reason": "no_tool_repeat",
                    }
                    status = "blocked"
                    finish_summary = native_decision.reason or (
                        "native model returned repeated assistant text without a tool call after continuation"
                    )
                    break
                if native_decision.lane_status == "blocked_return":
                    status = "blocked"
                    finish_summary = native_decision.reason
                    break
                if native_decision.lane_status == "blocked_continue":
                    ng_resume = build_native_ng_resume_signal(native_decision)
                    ng_resume_signals.append(ng_resume)
                    continuation = native_ng_resume_input_item(
                        ng_resume,
                        sequence=len(items) + 1,
                        provider=provider.provider,
                        model=provider.model,
                    )
                    items.append(continuation)
                    no_tool_continuation_count += 1
                    latest_no_tool_continuation = {
                        "turn_index": turn_index,
                        "assistant_text": _native_first_assistant_text(turn_items),
                        "continuation": continuation.output_text_or_ref,
                        "done_candidate_id": done_candidate.done_candidate_id,
                        "reason": "ng_resume_signal",
                    }
                    finish_summary = finish_summary or ng_resume.concise_reason
                    ng_continue_total_count += 1
                    ng_continue_consecutive_count += 1
                    ng_continue_consecutive_max = max(ng_continue_consecutive_max, ng_continue_consecutive_count)
                    last_ng_progress_fingerprint = model_progress_fingerprint
                    last_ng_plateau_signature = latest_ng_plateau_signature
                    last_no_tool_continuation_progress_fingerprint = model_progress_fingerprint
                    continue
            if (
                last_no_tool_continuation_progress_fingerprint
                and last_no_tool_continuation_progress_fingerprint == model_progress_fingerprint
            ):
                no_tool_repeat_done_candidate_count += 1
                latest_no_tool_continuation = {
                    "turn_index": turn_index,
                    "assistant_text": _native_first_assistant_text(turn_items),
                    "continuation": "",
                    "done_candidate_id": done_candidate.done_candidate_id if done_candidate else "",
                    "reason": "no_tool_repeat",
                }
                status = "blocked"
                finish_summary = (
                    "native model returned repeated assistant text without a tool call after continuation"
                )
                break
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
            last_no_tool_continuation_progress_fingerprint = model_progress_fingerprint
            latest_no_tool_continuation = {
                "turn_index": turn_index,
                "assistant_text": _native_first_assistant_text(turn_items),
                "continuation": continuation.output_text_or_ref,
                "done_candidate_id": done_candidate.done_candidate_id if done_candidate else "",
                "reason": "assistant_message_without_tool_call",
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
            if call.kind == "finish_call" and not (
                _native_finish_protocol_error(result) or _native_provider_visible_finish_unavailable(result)
            ):
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
                native_decision = _finish_gate.finish_gate_decision_from_closeout_events(
                    call,
                    result,
                    lane_input=lane_input,
                    lane_config=lane_config,
                    transcript_items=tuple(items),
                    compact_sidecar_digest_hash=_request_compact_sidecar_digest_hash(request_descriptor),
                    closeout_events=closeout_events,
                    closeout_context=closeout_context,
                )
                if native_decision is not None:
                    native_finish_gate_decisions.append(native_decision)
                    finish_gate_decision = native_decision.as_dict()
                    result = _finish_gate.finish_result_with_native_finish_gate_decision(result, native_decision)
                else:
                    arguments, _ = _arguments(call)
                    outcome = _native_finish_outcome(arguments)
                    gate: dict[str, object] = {}
                    finish_evidence_refs = _completion_policy.finish_arg_strings(arguments.get("evidence_refs"))
                    finish_closeout_refs = _completion_policy.finish_arg_strings(arguments.get("closeout_refs"))
                    finish_closeout_context = _closeout_policy.native_finish_supplied_closeout_context(
                        tuple(dict.fromkeys((*finish_evidence_refs, *finish_closeout_refs))),
                        tuple(tool_results),
                        source_mutation_roots=_closeout_policy.native_source_mutation_roots(
                            lane_input,
                            Path(lane_input.workspace or "."),
                        ),
                    )
                    decision = resolver.resolve(
                        _completion_policy.build_completion_resolver_input_from_finish(
                            call,
                            result,
                            lane_input=lane_input,
                            transcript_items=tuple(items),
                            arguments=arguments,
                            outcome=outcome,
                            gate=gate,
                            compact_sidecar_digest_hash=_request_compact_sidecar_digest_hash(request_descriptor),
                            closeout_context=closeout_context,
                            finish_closeout_context=finish_closeout_context,
                        )
                    )
                    resolver_decisions.append(decision)
                    result = _finish_result_with_resolver_decision(result, decision)
                result = with_tool_route_decision(
                    _finish_tool_call_envelope(call, _arguments(call)[0]),
                    result,
                    effective_tool="legacy_provider_visible_finish",
                )
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
                finish_gate_decision = _legacy_finish_gate_payload(result)
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

    finish_verifier_planner_decisions = _finish_planner.provider_finish_verifier_planner_decisions(provider)
    finish_verifier_planner_requests = _finish_planner.provider_finish_verifier_planner_requests(provider)
    planner_policy = finish_verifier_planner_policy(lane_config)
    finish_verifier_planner_selection_source = _finish_planner.native_finish_verifier_planner_selection_source(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tuple(tool_results),
        decisions=finish_verifier_planner_decisions,
        configured_verifier_precedence=bool(_configured_native_final_verifier_command(lane_input)),
        policy=planner_policy,
    )
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
        "done_candidate_count": len(done_candidates),
        "latest_done_candidate": done_candidates[-1].as_dict() if done_candidates else {},
        "ng_resume_signal_count": len(ng_resume_signals),
        "latest_ng_resume_signal": ng_resume_signals[-1].as_dict() if ng_resume_signals else {},
        "ng_continue_total_count": ng_continue_total_count,
        "ng_continue_consecutive_max": ng_continue_consecutive_max,
        "repeat_plateau_count": repeat_plateau_count,
        "latest_ng_plateau_signature": latest_ng_plateau_signature,
        "no_tool_continuation_count": no_tool_continuation_count,
        "no_tool_repeat_done_candidate_count": no_tool_repeat_done_candidate_count,
        "latest_no_tool_continuation": latest_no_tool_continuation,
        "completion_resolver_decision_count": len(resolver_decisions),
        "completion_resolver_latest_decision": resolver_decisions[-1].as_dict() if resolver_decisions else {},
        "native_finish_gate_decision_count": len(native_finish_gate_decisions),
        "native_finish_gate_latest_decision": (
            native_finish_gate_decisions[-1].as_dict() if native_finish_gate_decisions else {}
        ),
        "finish_verifier_planner_decision_count": len(finish_verifier_planner_decisions),
        "finish_verifier_planner_request_count": len(finish_verifier_planner_requests),
        "finish_verifier_planner_enabled": planner_policy.enabled,
        "finish_verifier_planner_request_enabled": planner_policy.enabled,
        "finish_verifier_planner_selection_source": finish_verifier_planner_selection_source,
        "planner_selection_source": finish_verifier_planner_selection_source,
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
            lane_input=lane_input,
            tool_results=tuple(tool_results),
            provider=provider,
            status=status,
            resolver_decisions=tuple(resolver_decisions),
            native_finish_gate_decisions=tuple(native_finish_gate_decisions),
            done_candidates=tuple(done_candidates),
            ng_resume_signals=tuple(ng_resume_signals),
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
        lane=_lane_name(lane_input),
    )


def _native_exec_max_active(lane_config: Mapping[str, object]) -> int:
    raw = lane_config.get("exec_max_active") or lane_config.get("max_active_commands")
    try:
        parsed = int(raw) if raw not in (None, "") else 5
    except (TypeError, ValueError):
        parsed = 5
    return max(1, min(parsed, 8))


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
        lane=_lane_name(lane_input),
        user_visible_summary=(
            f"{_lane_name(lane_input)} native transcript loop is selected but live provider transport is not wired yet."
        ),
        proof_artifacts=(),
        updated_lane_state={
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "transport_kind": "provider_native_unavailable",
            "provider_native_tool_loop": True,
            "model_json_main_path_detected": False,
            "requested_task_id": lane_input.task_id,
        },
        next_reentry_hint={
            "reason": f"{_safe_lane_name(_lane_name(lane_input))}_native_provider_not_wired",
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
    if call.kind == "finish_call" and not _legacy_provider_visible_finish_enabled(lane_config):
        reason = "provider-visible finish is not available in production native implement_v2"
        return with_tool_route_decision(
            _finish_tool_call_envelope(call, {}),
            _provider_visible_finish_unavailable_result(call, reason=reason),
            effective_tool="unavailable_provider_visible_finish",
        )
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
            effective_tool="legacy_provider_visible_finish",
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
        command_id = str(
            args.get("command_id") or args.get("session_id") or args.get("command_run_id") or ""
        ).strip()
        if not command_id:
            return call, args, "write_stdin command_id is required"
        mapped = {
            "command_id": command_id,
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
    try:
        snapshot = build_tool_surface_snapshot(
            lane_config=lane_config,
            task_contract=lane_input.task_contract,
            transcript_items=(),
            available_provider_tool_names=(str(tool_name or ""),),
        )
    except ValueError:
        return False
    return str(tool_name or "") in set(snapshot.provider_tool_names)


def _legacy_provider_visible_finish_enabled(lane_config: Mapping[str, object]) -> bool:
    """Return whether quarantined legacy fixtures may still emit finish calls."""

    return lane_config.get("allow_legacy_provider_visible_finish") is True


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
    done_candidate_id: str = "",
) -> tuple[tuple[_NativeCloseoutEvent, ...], _NativeCloseoutContext]:
    return _closeout_policy.run_finish_time_closeouts(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        workspace=workspace,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        lane_config=lane_config,
        tool_calls=tool_calls,
        tool_results=tool_results,
        start_monotonic=start_monotonic,
        done_candidate_id=done_candidate_id,
    )

def _native_final_verifier_closeout_no_run_context(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    tool_results: tuple[ToolResultEnvelope, ...],
    lane_config: Mapping[str, object],
    start_monotonic: float,
) -> _NativeCloseoutContext | None:
    return _closeout_policy.native_final_verifier_closeout_no_run_context(
        lane_input,
        provider=provider,
        tool_results=tool_results,
        lane_config=lane_config,
        start_monotonic=start_monotonic,
    )


def _native_closeout_context_from_result(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
) -> _NativeCloseoutContext:
    return _closeout_policy.native_closeout_context_from_result(call, result)


def _native_closeout_refs(call: NativeTranscriptItem, result: ToolResultEnvelope) -> tuple[str, ...]:
    return _closeout_policy.native_closeout_refs(call, result)


def _native_call_uses_finish_verifier_planner(call: NativeTranscriptItem) -> bool:
    return _closeout_policy.native_call_uses_finish_verifier_planner(call)


def _native_closeout_ref_is_completion_evidence(value: object) -> bool:
    return _closeout_policy.native_closeout_ref_is_completion_evidence(value)


_NATIVE_FINISH_RESOLVABLE_CLOSEOUT_BLOCKERS = frozenset(
    {
        "closeout_verifier_command_missing",
        "closeout_verifier_not_run",
    }
)

_NATIVE_EXPLICIT_ACCEPTANCE_PASS_RE = re.compile(
    r"(?im)^\s*(?:acceptance:\s*pass|acceptance_ok|final_acceptance_ok)\b"
)


def _native_active_command_closeout(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: ImplementV2ManagedExecRuntime,
    start_monotonic: float,
    closeout_index: int = 0,
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    return _closeout_policy.native_active_command_closeout(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        start_monotonic=start_monotonic,
        closeout_index=closeout_index,
    )


def _native_active_command_closeouts(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: ImplementV2ManagedExecRuntime,
    start_monotonic: float,
) -> tuple[tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]], ...]:
    return _closeout_policy.native_active_command_closeouts(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        start_monotonic=start_monotonic,
    )


def _native_active_command_run_id(exec_runtime: ImplementV2ManagedExecRuntime) -> str:
    return _closeout_policy.native_active_command_run_id(exec_runtime)


def _native_active_command_closeout_call(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    command_run_id: str,
    timeout_seconds: float,
    closeout_index: int = 0,
) -> NativeTranscriptItem:
    return _closeout_policy.native_active_command_closeout_call(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        turn_index=turn_index,
        command_run_id=command_run_id,
        timeout_seconds=timeout_seconds,
        closeout_index=closeout_index,
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
    done_candidate_id: str = "",
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    return _closeout_policy.native_final_verifier_closeout(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        exec_runtime=exec_runtime,
        workspace=workspace,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        lane_config=lane_config,
        tool_calls=tool_calls,
        tool_results=tool_results,
        start_monotonic=start_monotonic,
        pending_mutation=pending_mutation,
        done_candidate_id=done_candidate_id,
    )


def _native_final_verifier_closeout_allowed(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
) -> bool:
    return _closeout_policy.native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config)


def _native_final_verifier_tool_name(
    lane_input: ImplementLaneInput,
    *,
    lane_config: Mapping[str, object],
) -> str:
    return _closeout_policy.native_final_verifier_tool_name(lane_input, lane_config=lane_config)


def _canonical_native_verify_command_source(value: object, *, default: str = "") -> str:
    return _closeout_policy.canonical_native_verify_command_source(value, default=default)


def _native_final_verifier_command_candidate(
    lane_input: ImplementLaneInput,
    *,
    wanted_source: str,
) -> _finish_planner.FinishVerifierPlan | None:
    return _closeout_policy.native_final_verifier_command_candidate(lane_input, wanted_source=wanted_source)


def _configured_native_final_verifier_command(lane_input: ImplementLaneInput) -> str:
    return _closeout_policy.configured_native_final_verifier_command(lane_input)


def _auto_detected_native_final_verifier_command(lane_input: ImplementLaneInput) -> _finish_planner.FinishVerifierPlan | None:
    return _closeout_policy.auto_detected_native_final_verifier_command(lane_input)


def _native_final_verifier_closeout_plan(
    lane_input: ImplementLaneInput,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    done_candidate_id: str = "",
) -> _finish_planner.FinishVerifierPlan | None:
    return _closeout_policy.native_final_verifier_closeout_plan(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
        done_candidate_id=done_candidate_id,
    )


def _safe_auto_detected_finish_verifier_fallback(
    lane_input: ImplementLaneInput,
    *,
    request: Mapping[str, object],
) -> tuple[_finish_planner.FinishVerifierPlan | None, Mapping[str, object] | None]:
    return _closeout_policy.safe_auto_detected_finish_verifier_fallback(lane_input, request=request)


def _native_final_verifier_closeout_budget_seconds(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
) -> float:
    return _closeout_policy.native_final_verifier_closeout_budget_seconds(lane_input, run_started=run_started)


def _native_remaining_wall_budget_seconds(lane_input: ImplementLaneInput, *, run_started: float) -> float | None:
    return _closeout_policy.native_remaining_wall_budget_seconds(lane_input, run_started=run_started)


def _native_next_model_timeout_seconds(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
    requested_timeout: object,
) -> float | None:
    return _closeout_policy.native_next_model_timeout_seconds(
        lane_input,
        run_started=run_started,
        requested_timeout=requested_timeout,
    )


def _native_final_verifier_closeout_call(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    lane_config: Mapping[str, object],
    plan: _finish_planner.FinishVerifierPlan,
    timeout_seconds: float,
    pending_mutation: Mapping[str, object],
) -> NativeTranscriptItem:
    return _closeout_policy.native_final_verifier_closeout_call(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        turn_index=turn_index,
        lane_config=lane_config,
        plan=plan,
        timeout_seconds=timeout_seconds,
        pending_mutation=pending_mutation,
    )


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
    typed_refs = finish_typed_evidence_refs(
        prior_tool_results,
        task_description=_native_task_description(lane_input),
        task_contract=lane_input.task_contract,
    )
    evidence_refs = tuple(
        text
        for ref in typed_refs
        if isinstance(ref, Mapping) and (text := str(ref.get("id") or "").strip())
    )
    status = "invalid" if blocked else "completed"
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="finish",
        status=status,
        is_error=blocked,
        content=({"summary": str(call.arguments.get("summary") or ""), "outcome": outcome or status},),
        evidence_refs=evidence_refs if status == "completed" else (),
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


def _provider_visible_finish_unavailable_result(call: NativeTranscriptItem, *, reason: str) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name="finish",
        status="invalid",
        is_error=True,
        content=(
            {
                "reason": reason,
                "summary": reason,
                "outcome": "invalid_tool_contract",
                "provider_visible_finish_unavailable": {"reason": reason},
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


def _native_task_description(lane_input: ImplementLaneInput) -> str:
    return _finish_gate.native_task_description(lane_input)


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
    if text.startswith("oracle:completion_obligation:verifier"):
        return "completion_obligation_verifier:fresh"
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


def _native_provider_visible_finish_unavailable(result: ToolResultEnvelope) -> bool:
    if result.tool_name != "finish":
        return False
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return isinstance(payload.get("provider_visible_finish_unavailable"), dict)


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


def _native_finish_gate_blocked(result: ToolResultEnvelope) -> bool:
    if result.tool_name != "finish" or not result.is_error:
        return False
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return isinstance(payload.get("finish_gate"), dict)


def _legacy_finish_gate_payload(result: ToolResultEnvelope) -> dict[str, object]:
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
        lane=_lane_name(lane_input),
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
    return _request_builder.build_request_descriptor(
        lane_input=lane_input,
        lane_attempt_id=lane_attempt_id,
        turn_index=turn_index,
        transcript_items=transcript_items,
        loop_signals=(
            loop_signals
            if loop_signals is not None
            else _native_loop_control_state(
                transcript_items,
                current_turn_index=turn_index,
                lane_input=lane_input,
            )
        ),
    )


def _live_responses_request_descriptor(
    lane_input: ImplementLaneInput,
    *,
    provider: str,
    model: str,
    request_descriptor: Mapping[str, object],
) -> dict[str, object]:
    return _request_builder.build_live_responses_request_descriptor(
        lane_input,
        provider=provider,
        model=model,
        request_descriptor=request_descriptor,
    )


def _native_instructions(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
    tool_surface: ToolSurfaceSnapshot | None = None,
) -> str:
    return _request_builder.native_instructions(
        lane_input,
        tool_specs=tool_specs,
        tool_surface=tool_surface,
    )


def _tool_specs_from_request_descriptor(
    lane_input: ImplementLaneInput,
    request_descriptor: Mapping[str, object],
) -> tuple[ImplementLaneToolSpec, ...]:
    return _request_builder.tool_specs_from_request_descriptor(
        lane_input,
        request_descriptor,
    )


def _native_tool_specs_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
) -> tuple[ImplementLaneToolSpec, ...]:
    return _request_builder.native_tool_specs_for_request(lane_input, transcript_items)


def _tool_surface_snapshot_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
    *,
    available_provider_tool_names: tuple[str, ...] | None = None,
) -> ToolSurfaceSnapshot:
    return _request_builder.tool_surface_snapshot_for_request(
        lane_input,
        transcript_items,
        available_provider_tool_names=available_provider_tool_names,
    )


def _mapping_from_request_descriptor(value: object) -> Mapping[str, object]:
    return _request_builder.mapping_from_request_descriptor(value)


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


def _command_run_ids_from_output_item(item: NativeTranscriptItem) -> set[str]:
    command_run_ids: set[str] = set()
    command_run_id = _command_run_id_from_output_text(item.output_text_or_ref)
    if command_run_id:
        command_run_ids.add(command_run_id)
    for ref in item.content_refs:
        match = _COMMAND_OUTPUT_REF_RE.search(str(ref or ""))
        if match:
            command_run_ids.add(match.group("id"))
    return command_run_ids


def _responses_input_items(
    lane_input: ImplementLaneInput,
    transcript_items: list[NativeTranscriptItem],
    *,
    compact_sidecar_digest: Mapping[str, object],
    tool_surface: ToolSurfaceSnapshot,
) -> list[dict[str, object]]:
    return _request_builder.responses_input_items(
        lane_input,
        transcript_items,
        compact_sidecar_digest=compact_sidecar_digest,
        tool_surface=tool_surface,
    )


def _profile_developer_input_items(
    lane_input: ImplementLaneInput,
    tool_surface: ToolSurfaceSnapshot,
) -> list[dict[str, object]]:
    return _request_builder.profile_developer_input_items(lane_input, tool_surface)


def _profile_developer_transport(
    lane_input: ImplementLaneInput,
    tool_surface: ToolSurfaceSnapshot,
) -> dict[str, object]:
    return _request_builder.profile_developer_transport(lane_input, tool_surface)


def _profile_developer_role_supported(lane_input: ImplementLaneInput) -> bool:
    return _request_builder.profile_developer_role_supported(lane_input)


def _raw_task_provider_visible_text(lane_input: ImplementLaneInput) -> str:
    return _request_builder.raw_task_provider_visible_text(lane_input)


def _task_first_provider_visible_text(
    lane_input: ImplementLaneInput,
    *,
    task_facts: Mapping[str, object],
) -> str:
    return _request_builder.task_first_provider_visible_text(lane_input, task_facts=task_facts)


def _task_contract_objective_text(contract: Mapping[str, object]) -> str:
    return _request_builder.task_contract_objective_text(contract)


def _provider_visible_task_facts(lane_input: ImplementLaneInput) -> dict[str, object]:
    return _request_builder.provider_visible_task_facts(lane_input)


def _task_paths_from_text(text: object, *, workspace: str | Path | None = None) -> list[str]:
    return _request_builder.task_paths_from_text(text, workspace=workspace)


def _normalize_task_path_token(token: object, *, workspace: str | Path | None = None) -> str:
    return _request_builder.normalize_task_path_token(token, workspace=workspace)


def _task_path_has_safe_segments(path: object) -> bool:
    return _request_builder.task_path_has_safe_segments(path)


def _task_path_is_safe_relative(path: object) -> bool:
    return _request_builder.task_path_is_safe_relative(path)


def _dedupe_task_paths(paths: Iterable[object]) -> list[str]:
    return _request_builder.dedupe_task_paths(paths)


def _compact_sidecar_digest_for_request(
    *,
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    transcript_items: list[NativeTranscriptItem],
    loop_signals: Mapping[str, object],
) -> dict[str, object]:
    return _request_builder.compact_sidecar_digest_for_request(
        lane_input=lane_input,
        lane_attempt_id=lane_attempt_id or _lane_attempt_id(lane_input),
        transcript_items=transcript_items,
        loop_signals=loop_signals,
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
    if item.tool_name not in EXEC_TOOL_NAMES and item.tool_name != "exec_command":
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
    return item.tool_name in READ_ONLY_TOOL_NAMES or item.tool_name in EXEC_TOOL_NAMES or item.tool_name == "exec_command"


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
        command_run_ids.update(_command_run_ids_from_output_item(item))
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
    if call is None or call.tool_name not in {"poll_command", "cancel_command", "write_stdin"}:
        return False
    return _command_run_id_from_call(call) in verifier_command_run_ids


def _command_run_id_from_call(item: NativeTranscriptItem) -> str:
    arguments, error = _arguments(item)
    if error:
        return ""
    return str(
        arguments.get("command_id")
        or arguments.get("command_run_id")
        or arguments.get("session_id")
        or ""
    ).strip()


def _command_run_id_from_output_text(value: str) -> str:
    match = _COMMAND_RUN_ID_RE.search(str(value or ""))
    if not match:
        return ""
    return str(match.group("id") or match.group("command_id") or match.group("session") or "").strip()


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
    return _request_builder.responses_input_item_from_transcript_item(item)


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
    return _request_builder.provider_visible_native_item(item, lane_input=lane_input)


def _native_item_provider_visible(item: NativeTranscriptItem) -> bool:
    return _request_builder.native_item_provider_visible(item)


def _mapping_list(value: object) -> list[dict[str, object]]:
    return _request_builder.mapping_list(value)


def _provider_safe_input_items(value: object) -> list[dict[str, object]]:
    return _request_builder.provider_safe_input_items(value)


def _reasoning_config(lane_input: ImplementLaneInput) -> dict[str, object] | bool:
    return _request_builder.reasoning_config(lane_input)


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
    finish_verifier_planner_decisions = _finish_planner.provider_finish_verifier_planner_decisions(provider)
    finish_verifier_planner_requests = _finish_planner.provider_finish_verifier_planner_requests(provider)
    proof_artifacts = _write_live_failure_artifacts(
        lane_input,
        transcript=transcript,
        provider=provider,
        error=error,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )
    return ImplementLaneResult(
        status="failed",
        lane=_lane_name(lane_input),
        user_visible_summary=f"{_lane_name(lane_input)} native provider failed: {error}",
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
            "finish_verifier_planner_decision_count": len(finish_verifier_planner_decisions),
            "finish_verifier_planner_request_count": len(finish_verifier_planner_requests),
            "finish_verifier_planner_latest_decision": (
                dict(finish_verifier_planner_decisions[-1]) if finish_verifier_planner_decisions else {}
            ),
        },
    )


def _partial_failure_harness_result(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    provider: object,
    items: list[NativeTranscriptItem],
    tool_results: tuple[ToolResultEnvelope, ...],
    done_candidates: tuple[NativeDoneCandidate, ...],
    artifact_root: str | Path | None,
    error: str,
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    ng_resume_signals: tuple[NativeNgResumeSignal, ...] = (),
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
    finish_verifier_planner_decisions = _finish_planner.provider_finish_verifier_planner_decisions(provider)
    finish_verifier_planner_requests = _finish_planner.provider_finish_verifier_planner_requests(provider)
    metrics = {
        **_native_surface_for_provider(provider),
        "status": "failed",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transcript_hash": native_transcript_hash(transcript),
        "error": error,
        "turn_count": len(getattr(provider, "requests", []) or ()),
        "provider_request_inventory_available": bool(getattr(provider, "requests", []) or ()),
        "done_candidate_count": len(done_candidates),
        "latest_done_candidate": done_candidates[-1].as_dict() if done_candidates else {},
        "ng_resume_signal_count": len(ng_resume_signals),
        "latest_ng_resume_signal": ng_resume_signals[-1].as_dict() if ng_resume_signals else {},
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
    proof_artifacts: tuple[str, ...] = ()
    if artifact_root is not None:
        if isinstance(provider, NativeCodexResponsesProvider):
            proof_artifacts = _write_live_failure_artifacts(
                lane_input,
                transcript=transcript,
                provider=provider,
                tool_results=tool_results,
                done_candidates=done_candidates,
                native_finish_gate_decisions=native_finish_gate_decisions,
                ng_resume_signals=ng_resume_signals,
                finish_verifier_planner_decisions=finish_verifier_planner_decisions,
                finish_verifier_planner_requests=finish_verifier_planner_requests,
                error=error,
                artifact_root=Path(artifact_root),
            )
        else:
            paths = _write_native_artifacts(
                Path(artifact_root),
                transcript,
                lane_input=lane_input,
                tool_results=tool_results,
                provider=provider,
                done_candidates=done_candidates,
                native_finish_gate_decisions=native_finish_gate_decisions,
                ng_resume_signals=ng_resume_signals,
                finish_verifier_planner_decisions=finish_verifier_planner_decisions,
                finish_verifier_planner_requests=finish_verifier_planner_requests,
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
        lane=_lane_name(lane_input),
    )


def _write_live_failure_artifacts(
    lane_input: ImplementLaneInput,
    *,
    transcript: NativeTranscript,
    provider: NativeCodexResponsesProvider,
    tool_results: tuple[ToolResultEnvelope, ...] = (),
    done_candidates: tuple[NativeDoneCandidate, ...] = (),
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    ng_resume_signals: tuple[NativeNgResumeSignal, ...] = (),
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...] = (),
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
    error: str,
    artifact_root: Path | None = None,
) -> tuple[str, ...]:
    root_path = artifact_root or _artifact_root(lane_input)
    if root_path is None:
        return ()
    root = Path(root_path)
    root.mkdir(parents=True, exist_ok=True)
    return _artifact_writer.write_live_failure_artifacts(
        root,
        lane_input=lane_input,
        transcript=transcript,
        provider=provider,
        tool_results=tool_results,
        done_candidates=done_candidates,
        native_finish_gate_decisions=native_finish_gate_decisions,
        ng_resume_signals=ng_resume_signals,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
        error=error,
    )

def _route_records_with_tool_surface(
    route_records: tuple[dict[str, object], ...],
    *,
    provider: object,
) -> tuple[dict[str, object], ...]:
    return _artifact_writer.route_records_with_tool_surface(route_records, provider=provider)


def _provider_tool_surface_metadata_by_turn(provider: object) -> dict[int, Mapping[str, object]]:
    return _artifact_writer.provider_tool_surface_metadata_by_turn(provider)


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


def _native_apply_ng_resume_policy(
    decision: NativeFinishGateDecision,
    *,
    no_tool_reason: str,
    ng_continue_total_count: int,
    ng_continue_consecutive_count: int,
    current_progress_fingerprint: str,
    last_progress_fingerprint: str,
    current_plateau_signature: str,
    last_plateau_signature: str,
) -> tuple[NativeFinishGateDecision, int]:
    return _closeout_policy.apply_ng_resume_policy(
        decision,
        no_tool_reason=no_tool_reason,
        ng_continue_total_count=ng_continue_total_count,
        ng_continue_consecutive_count=ng_continue_consecutive_count,
        current_progress_fingerprint=current_progress_fingerprint,
        last_progress_fingerprint=last_progress_fingerprint,
        current_plateau_signature=current_plateau_signature,
        last_plateau_signature=last_plateau_signature,
    )


def _native_ng_return_decision(
    decision: NativeFinishGateDecision,
    *,
    blocker: str,
    reason: str,
) -> NativeFinishGateDecision:
    return _closeout_policy.ng_return_decision(decision, blocker=blocker, reason=reason)

def _native_model_tool_progress_fingerprint(tool_results: tuple[ToolResultEnvelope, ...]) -> str:
    records = [
        _native_tool_progress_record(result)
        for result in tool_results
        if not _native_result_is_internal_closeout(result)
    ]
    return "sha256:" + hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _native_ng_plateau_signature(
    decision: NativeFinishGateDecision,
    *,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> str:
    payload = {
        "policy_version": decision.policy_version,
        "blockers": sorted(set(decision.blockers)),
        "missing_obligations": sorted(set(decision.missing_obligations)),
        "closeout_status": decision.closeout.status,
        "closeout_timed_out": decision.closeout.timed_out,
        "closeout_exit_class": _native_closeout_exit_class(decision.closeout.tool_result),
        "source_mutation_hash": _native_source_mutation_fingerprint(tool_results),
        "artifact_hash": _native_artifact_fingerprint(tool_results),
        "evidence_refs": sorted(set(decision.evidence_refs)),
        "closeout_refs": sorted(set(decision.closeout_refs)),
        "terminal_exit": _native_latest_terminal_exit_class(tool_results),
    }
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _native_result_is_internal_closeout(result: ToolResultEnvelope) -> bool:
    return str(result.provider_call_id or "").startswith(_INTERNAL_CLOSEOUT_CALL_PREFIXES)


def _native_tool_progress_record(result: ToolResultEnvelope) -> dict[str, object]:
    payload = _native_result_payload(result)
    return {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content_refs": list(result.content_refs),
        "evidence_refs": list(result.evidence_refs),
        "side_effects": list(result.side_effects),
        "command_run_id": str(payload.get("command_run_id") or ""),
        "exit_code": payload.get("exit_code"),
        "terminal_status": payload.get("status"),
    }


def _native_source_mutation_fingerprint(tool_results: tuple[ToolResultEnvelope, ...]) -> str:
    records: list[object] = []
    for result in tool_results:
        if _native_result_is_internal_closeout(result):
            continue
        payload = _native_result_payload(result)
        side_effects = [
            effect
            for effect in result.side_effects
            if str(effect.get("kind") or "") in {"file_write", "file_edit", "source_mutation"}
        ]
        if side_effects or payload.get("source_mutation_refs") or payload.get("changed_paths"):
            records.append(
                {
                    "provider_call_id": result.provider_call_id,
                    "tool_name": result.tool_name,
                    "side_effects": side_effects,
                    "source_mutation_refs": payload.get("source_mutation_refs") or (),
                    "changed_paths": payload.get("changed_paths") or (),
                }
            )
    return "sha256:" + hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _native_artifact_fingerprint(tool_results: tuple[ToolResultEnvelope, ...]) -> str:
    records: list[object] = []
    for result in tool_results:
        if _native_result_is_internal_closeout(result):
            continue
        payload = _native_result_payload(result)
        artifact_refs = payload.get("artifact_refs") or payload.get("output_refs") or ()
        if artifact_refs or result.content_refs:
            records.append(
                {
                    "provider_call_id": result.provider_call_id,
                    "tool_name": result.tool_name,
                    "content_refs": list(result.content_refs),
                    "artifact_refs": artifact_refs,
                }
            )
    return "sha256:" + hashlib.sha256(
        json.dumps(records, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":")).encode()
    ).hexdigest()


def _native_latest_terminal_exit_class(tool_results: tuple[ToolResultEnvelope, ...]) -> str:
    for result in reversed(tool_results):
        if _native_result_is_internal_closeout(result):
            continue
        if result.tool_name not in EXEC_TOOL_NAMES and result.tool_name not in _PROCESS_LIFECYCLE_TOOL_NAMES:
            continue
        payload = _native_result_payload(result)
        return f"{payload.get('status') or result.status}:{payload.get('exit_code')}"
    return "none"


def _native_closeout_exit_class(tool_result: object | None) -> str:
    if not isinstance(tool_result, ToolResultEnvelope):
        return "none"
    payload = _native_result_payload(tool_result)
    return f"{payload.get('status') or tool_result.status}:{payload.get('exit_code')}"


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
        "If the task is complete, provide a concise final response after a concrete verifier or requested artifact exists.",
        "If it is not complete, call a tool to verify or repair from the latest concrete result.",
        "A repeated prose-only response will stop the loop for supervisor review.",
    ]
    if latest_resolver_decision is not None and latest_resolver_decision.lane_status == "blocked_continue":
        lines.append(_provider_safe_blocked_completion_summary(latest_resolver_decision))
    assistant_text = _native_first_assistant_text(items)
    if assistant_text:
        lines.append("Last assistant response was not accepted as completion.")
    return NativeTranscriptItem(
        sequence=sequence,
        turn_id=f"turn-{turn_index}-continuation",
        kind="input_message",
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        output_text_or_ref="\n".join(lines),
    )


def _provider_safe_blocked_completion_summary(decision: CompletionResolverDecision) -> str:
    joined = " ".join(
        (
            *[str(item or "") for item in decision.blockers],
            *[str(item or "") for item in decision.missing_obligations],
        )
    ).casefold()
    if "verifier" in joined or "evidence" in joined or "oracle" in joined:
        return (
            "Previous completion attempt was not accepted: run a concrete verification "
            "command or inspect the requested artifact before responding again."
        )
    if "unsafe" in joined:
        return "Previous completion attempt was not accepted: repair the unsafe change before responding again."
    if "budget" in joined:
        return "Previous completion attempt needs supervisor review or more budget."
    return "Previous completion attempt was not accepted: call a tool to verify or repair before responding again."


def _native_first_assistant_text(items: tuple[NativeTranscriptItem, ...]) -> str:
    for item in items:
        if item.kind == "assistant_message":
            return _finish_block_clip(item.output_text_or_ref, limit=160)
    return ""


def _native_final_assistant_response_text(items: tuple[NativeTranscriptItem, ...]) -> str:
    texts = [item.output_text_or_ref for item in items if item.kind == "assistant_message" and item.output_text_or_ref]
    return "\n\n".join(texts)


def _call_order_key(call: NativeTranscriptItem) -> tuple[int, int]:
    return (call.output_index, call.sequence)


def _write_native_artifacts(
    root: Path,
    transcript: NativeTranscript,
    *,
    lane_input: ImplementLaneInput | None = None,
    tool_results: tuple[ToolResultEnvelope, ...],
    provider: object,
    status: str = "",
    error: str = "",
    resolver_decisions: tuple[CompletionResolverDecision, ...] = (),
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    done_candidates: tuple[NativeDoneCandidate, ...] = (),
    ng_resume_signals: tuple[NativeNgResumeSignal, ...] = (),
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...] = (),
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Path]:
    return _artifact_writer.write_native_artifacts(
        root,
        transcript,
        lane_input=lane_input,
        tool_results=tool_results,
        provider=provider,
        status=status,
        error=error,
        resolver_decisions=resolver_decisions,
        native_finish_gate_decisions=native_finish_gate_decisions,
        done_candidates=done_candidates,
        ng_resume_signals=ng_resume_signals,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )


def _patch_native_default_observability(
    paths: Mapping[str, Path],
    *,
    provider: object,
    lane_input: ImplementLaneInput | None,
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...],
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...],
) -> None:
    _artifact_writer.patch_native_default_observability(
        paths,
        provider=provider,
        lane_input=lane_input,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )


def _native_default_observability_facts(
    provider: object,
    *,
    lane_input: ImplementLaneInput | None,
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...],
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    return _artifact_writer.native_default_observability_facts(
        provider,
        lane_input=lane_input,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )


def _mapping_or_empty(value: object) -> dict[str, object]:
    return _artifact_writer.mapping_or_empty(value)


def _latest_tool_surface_metadata(provider: object) -> dict[str, object]:
    return _artifact_writer.latest_tool_surface_metadata(provider)


def _write_native_tool_result_sidecars(
    root: Path,
    *,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, Path]:
    return _artifact_writer.write_native_tool_result_sidecars(root, tool_results=tool_results)


def _write_native_render_output_sidecar(root: Path, transcript: NativeTranscript) -> dict[str, Path]:
    return _artifact_writer.write_native_render_output_sidecar(root, transcript)


def _provider_request_records(provider: object) -> tuple[dict[str, object], ...]:
    return _artifact_writer.provider_request_records(provider)


def _write_provider_request_artifacts(
    root: Path,
    *,
    provider: object,
    status: str = "",
    error: str = "",
) -> dict[str, Path]:
    return _artifact_writer.write_provider_request_artifacts(root, provider=provider, status=status, error=error)


def _finish_summary(call: NativeTranscriptItem) -> str:
    arguments, _ = _arguments(call)
    return str(arguments.get("summary") or "native implement_v2 finished")


def _turn_number(turn_id: str) -> int:
    try:
        return int(str(turn_id).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _lane_attempt_id(lane_input: ImplementLaneInput) -> str:
    return f"{lane_input.work_session_id}:{lane_input.task_id}:{_safe_lane_name(_lane_name(lane_input))}:native"


def _lane_name(lane_input: ImplementLaneInput) -> str:
    return str(lane_input.lane or "implement_v2").strip() or "implement_v2"


def _safe_lane_name(lane: object) -> str:
    text = str(lane or "").strip()
    safe = []
    for char in text:
        if char.isalnum() or char in ("-", "_", "."):
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or "implement_v2"
