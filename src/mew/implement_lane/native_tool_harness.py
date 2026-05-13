"""Phase 3 native implement_v2 harness over provider-native transcript items."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
import time
from typing import Mapping

from .completion_resolver import (
    CompletionResolver,
    CompletionResolverDecision,
    CompletionResolverInput,
    FinishClaim,
    write_completion_resolver_artifacts,
)
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .native_fake_provider import PHASE3_TRANSPORT_CHANGE, NativeFakeProvider
from .native_provider_adapter import (
    NativeResponsesStreamParseResult,
    build_custom_tool_call_output_input_item,
    build_function_call_output_input_item,
    build_responses_request_descriptor,
    call_codex_native_responses,
)
from .native_sidecar_projection import build_compact_native_sidecar_digest
from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    OUTPUT_ITEM_KINDS,
    build_synthetic_error_output,
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
from .tool_policy import (
    hide_unavailable_write_file_guidance,
    is_hard_runtime_artifact_task,
    list_v2_tool_specs_for_mode,
    list_v2_tool_specs_for_task,
)
from .tool_routes import route_records_from_results, with_tool_route_decision
from .types import ImplementLaneInput, ImplementLaneResult, ToolCallEnvelope, ToolResultEnvelope
from .v2_runtime import (
    _acceptance_session_from_tool_results,
    _finish_acceptance_action,
)
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime
from ..acceptance import acceptance_done_gate_decision
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
_SOURCE_MUTATION_COMMAND_INTENTS = frozenset(
    {"implement", "implementation", "write", "edit", "mutation", "source_mutation"}
)
_COMMAND_RUN_ID_RE = re.compile(r"(?:^|[\s;,])command_run_id=(?P<id>[^\s;,]+)")
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
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    unsafe_blockers: tuple[str, ...] = ()
    budget_blockers: tuple[str, ...] = ()

    def merge(self, other: "_NativeCloseoutContext") -> "_NativeCloseoutContext":
        return _NativeCloseoutContext(
            closeout_refs=tuple(dict.fromkeys((*self.closeout_refs, *other.closeout_refs))),
            fresh_verifier_refs=tuple(dict.fromkeys((*self.fresh_verifier_refs, *other.fresh_verifier_refs))),
            blockers=tuple(dict.fromkeys((*self.blockers, *other.blockers))),
            missing_obligations=tuple(dict.fromkeys((*self.missing_obligations, *other.missing_obligations))),
            unsafe_blockers=tuple(dict.fromkeys((*self.unsafe_blockers, *other.unsafe_blockers))),
            budget_blockers=tuple(dict.fromkeys((*self.budget_blockers, *other.budget_blockers))),
        )


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

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []
        if self.responses is None:
            self.responses = []
        if self.rejected_responses is None:
            self.rejected_responses = []
        if not self.model:
            self.model = str(self.lane_input.model or "gpt-5.5")

    def next_response(self, request_descriptor: Mapping[str, object]) -> NativeResponsesStreamParseResult | None:
        descriptor = _live_responses_request_descriptor(
            self.lane_input,
            provider=self.provider,
            model=self.model,
            request_descriptor=request_descriptor,
        )
        descriptor["provider_request_inventory"] = dict(
            request_descriptor.get("provider_request_inventory") or {}
        )
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
            result = call_codex_native_responses(
                auth=self.auth,
                descriptor=descriptor,
                base_url=self.base_url,
                timeout=self.timeout,
                lane_attempt_id=str(request_descriptor.get("lane_attempt_id") or ""),
                turn_id=f"turn-{request_descriptor.get('turn_index')}",
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
        return result


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
            "native_transport_kind": "provider_native",
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
    resolver_decisions: list[CompletionResolverDecision] = []
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
                status = "blocked"
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
        accepted_finish: NativeTranscriptItem | None = None
        terminal_blocked_finish: NativeTranscriptItem | None = None
        output_records: list[NativeTranscriptItem] = []
        for call in calls:
            if accepted_finish is not None and _call_order_key(call) > _call_order_key(accepted_finish):
                output_records.append(
                    build_synthetic_error_output(
                        call,
                        sequence=0,
                        reason=f"cancelled because finish call {accepted_finish.call_id} completed earlier in the same response",
                    )
                )
                continue
            if terminal_blocked_finish is not None and _call_order_key(call) > _call_order_key(terminal_blocked_finish):
                output_records.append(
                    build_synthetic_error_output(
                        call,
                        sequence=0,
                        reason=(
                            "cancelled because finish call "
                            f"{terminal_blocked_finish.call_id} returned control to supervisor"
                        ),
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
            if call.kind == "finish_call" and _native_finish_resolver_lane_status(result) == "completed":
                accepted_finish = call
                status = "completed"
                finish_summary = _finish_summary(call)
            elif call.kind == "finish_call" and _native_finish_resolver_lane_status(result) == "blocked_return":
                terminal_blocked_finish = call
                status = "blocked"
                finish_summary = _native_finish_resolver_reason(result)

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
        "completion_resolver_decision_count": len(resolver_decisions),
        "completion_resolver_latest_decision": resolver_decisions[-1].as_dict() if resolver_decisions else {},
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
    if call.tool_name in READ_ONLY_TOOL_NAMES:
        return with_tool_route_decision(
            envelope,
            execute_read_only_tool_call(envelope, workspace=workspace, allowed_roots=allowed_read_roots),
        )
    if call.tool_name in EXEC_TOOL_NAMES:
        return with_tool_route_decision(envelope, exec_runtime.execute(envelope))
    if call.tool_name in WRITE_TOOL_NAMES:
        if not _side_effect_id_valid(call):
            return with_tool_route_decision(
                envelope,
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
        return with_tool_route_decision(envelope, write_runtime.execute(envelope))
    return with_tool_route_decision(envelope, _invalid_result(call, reason=f"unknown native tool: {call.tool_name}"))


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
    if not pending_mutation:
        return tuple(events), context
    no_run_context = _native_final_verifier_closeout_no_run_context(
        lane_input,
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
    lane_config: Mapping[str, object],
    start_monotonic: float,
) -> _NativeCloseoutContext | None:
    if not _native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return _NativeCloseoutContext(
            unsafe_blockers=("closeout_verifier_not_permitted",),
            missing_obligations=("strict_verifier_evidence",),
        )
    if not _configured_native_final_verifier_command(lane_input):
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
        return _NativeCloseoutContext(closeout_refs=refs, fresh_verifier_refs=refs)
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
    refs = tuple(ref for ref in result.evidence_refs if str(ref).strip())
    if refs:
        return refs
    return (f"native-closeout://{call.call_id}",)


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
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    pending_mutation = _latest_native_source_mutation_without_later_verifier(
        tool_calls,
        tool_results,
        source_mutation_roots=_native_source_mutation_roots(lane_input, workspace),
    )
    if not pending_mutation:
        return None
    if not _native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return None
    command = _configured_native_final_verifier_command(lane_input)
    if not command:
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
        command=command,
        timeout_seconds=budget,
        pending_mutation=pending_mutation,
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
    mode = str(lane_config.get("mode") or "full").strip().casefold()
    tool_names = {tool.name for tool in list_v2_tool_specs_for_mode(mode)}
    if "run_command" not in tool_names:
        return False
    return bool(lane_input.workspace)


def _configured_native_final_verifier_command(lane_input: ImplementLaneInput) -> str:
    for source in (lane_input.lane_config, lane_input.task_contract):
        command = str(source.get("verify_command") or "").strip()
        if command:
            return command
    return ""


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
    command: str,
    timeout_seconds: float,
    pending_mutation: Mapping[str, object],
) -> NativeTranscriptItem:
    call_id = f"call-final-verifier-closeout-{turn_index:03d}"
    arguments = {
        "command": command,
        "cwd": ".",
        "use_shell": True,
        "timeout": round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
        "foreground_budget_seconds": round(max(_FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
        "command_intent": "verifier",
        "execution_contract": {
            "role": "runtime",
            "stage": "final-verifier",
            "purpose": "verify the latest source mutation before native closeout",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "verifier_required": True,
            "expected_exit": 0,
            "latest_source_mutation_provider_call_id": pending_mutation.get("provider_call_id") or "",
            "latest_source_mutation_path": pending_mutation.get("path") or "",
        },
    }
    return NativeTranscriptItem(
        sequence=0,
        turn_id=f"turn-{turn_index}-final-verifier-closeout",
        lane_attempt_id=lane_attempt_id,
        provider=str(getattr(provider, "provider", "") or "native-controller"),
        model=str(getattr(provider, "model", "") or lane_input.model or ""),
        response_id=f"native-final-verifier-closeout-{turn_index}",
        provider_item_id=f"item-{call_id}",
        output_index=0,
        kind="function_call",
        call_id=call_id,
        tool_name="run_command",
        arguments_json_text=json.dumps(arguments, sort_keys=True),
    )


def _latest_native_source_mutation_without_later_verifier(
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> dict[str, object]:
    latest_mutation: dict[str, object] = {}
    latest_verifier_index = 0
    verifier_command_run_ids: set[str] = set()
    for index, (call, result) in enumerate(zip(tool_calls, tool_results), start=1):
        if _native_call_is_verifier(call):
            command_run_id = _command_run_id_from_result(result)
            if command_run_id:
                verifier_command_run_ids.add(command_run_id)
        if _native_result_is_terminal_verifier(call, result, verifier_command_run_ids=verifier_command_run_ids):
            latest_verifier_index = index
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
                "latest_verifier_index": latest_verifier_index,
            }
    if not latest_mutation:
        return {}
    if int(latest_mutation.get("result_index") or 0) <= latest_verifier_index:
        return {}
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
    output_text = result.natural_result_text()
    if not _native_tool_available("write_file", lane_input=lane_input, lane_config=lane_config):
        output_text = hide_unavailable_write_file_guidance(output_text)
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
        content_refs=result.content_refs,
        evidence_refs=result.evidence_refs,
        sidecar_refs=(str(result.route_decision.get("ref")),) if result.route_decision.get("ref") else (),
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
        str(contract.get("description") or "").strip(),
        str(contract.get("guidance") or "").strip(),
        str(contract.get("verify_command") or "").strip(),
    ]
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
    blockers.extend(_finish_arg_strings(arguments.get("blockers")))
    missing.extend(_finish_arg_strings(arguments.get("missing_obligations")))
    unsafe_blockers.extend(_finish_arg_strings(arguments.get("unsafe_blockers")))
    budget_blockers.extend(_finish_arg_strings(arguments.get("budget_blockers")))
    blockers.extend(closeout_context.blockers)
    missing.extend(closeout_context.missing_obligations)
    unsafe_blockers.extend(closeout_context.unsafe_blockers)
    budget_blockers.extend(closeout_context.budget_blockers)
    if gate and gate.get("decision") != "allow_complete":
        blockers.append("finish_gate_blocked")
        blockers.extend(_finish_gate_blocker_codes(gate))
        missing.extend(_finish_gate_missing_obligations(gate))
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
        typed_evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *_finish_arg_strings(arguments.get("evidence_refs"))))),
        fresh_verifier_refs=tuple(closeout_context.fresh_verifier_refs),
        missing_obligations=tuple(dict.fromkeys(missing)),
        closeout_refs=tuple(
            dict.fromkeys((*_finish_arg_strings(arguments.get("closeout_refs")), *closeout_context.closeout_refs))
        ),
        blockers=tuple(dict.fromkeys(blockers)),
        unsafe_blockers=tuple(dict.fromkeys(unsafe_blockers)),
        budget_blockers=tuple(dict.fromkeys(budget_blockers)),
        verifier_required=bool(gate and gate.get("decision") != "allow_complete"),
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
    return replace(
        result,
        status="invalid",
        is_error=True,
        content=(payload,),
        evidence_refs=tuple(dict.fromkeys((*result.evidence_refs, *decision.evidence_refs))),
    )


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


def _finish_gate_missing_obligations(gate: Mapping[str, object]) -> tuple[str, ...]:
    missing: list[str] = []
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
    input_items = _responses_input_items(
        lane_input,
        provider_visible_transcript_items,
        compact_sidecar_digest=compact_sidecar_digest,
    )
    instructions = _native_instructions(lane_input)
    forbidden_fields_report = build_provider_visible_forbidden_fields_report(
        input_items=input_items,
        instructions=instructions,
        compact_sidecar_digest=compact_sidecar_digest,
    )
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native" if _provider_is_live(lane_input) else "fake_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": lane_attempt_id,
        "turn_index": turn_index,
        "input_item_count": len(transcript_items),
        "input_items": input_items,
        "transcript_window": [item.as_dict() for item in provider_visible_transcript_items],
        "provider_request_inventory": build_native_prompt_input_inventory(
            compact_sidecar_digest=compact_sidecar_digest,
            provider_visible_forbidden_fields=forbidden_fields_report,
            diagnostic_only_fields=loop_signals.keys(),
            diagnostic_loop_signals=loop_signals,
        ),
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
    mode = str(lane_input.lane_config.get("mode") or "full").strip() or "full"
    reasoning = _reasoning_config(lane_input)
    return build_responses_request_descriptor(
        model=model,
        instructions=str(request_descriptor.get("instructions") or _native_instructions(lane_input)),
        input_items=_provider_safe_input_items(request_descriptor.get("input_items")),
        tool_specs=list_v2_tool_specs_for_task(mode, task_contract=lane_input.task_contract),
        transcript_window=request_descriptor.get("transcript_window") or (),
        reasoning=reasoning,
        provider_request_id=f"{request_descriptor.get('lane_attempt_id')}:turn:{request_descriptor.get('turn_index')}",
        prompt_cache_key=str(request_descriptor.get("lane_attempt_id") or ""),
    )


def _native_instructions(lane_input: ImplementLaneInput) -> str:
    tool_specs = list_v2_tool_specs_for_task(
        lane_input.lane_config.get("mode") or "full",
        task_contract=lane_input.task_contract,
    )
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


def _responses_input_items(
    lane_input: ImplementLaneInput,
    transcript_items: list[NativeTranscriptItem],
    *,
    compact_sidecar_digest: Mapping[str, object],
) -> list[dict[str, object]]:
    task_payload = {
        "task_contract": dict(lane_input.task_contract),
        "compact_sidecar_digest": dict(compact_sidecar_digest),
        "workspace": lane_input.workspace,
        "lane": lane_input.lane,
    }
    items: list[dict[str, object]] = [
        {
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": json.dumps(task_payload, ensure_ascii=False, sort_keys=True),
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
    if item.tool_name != "run_command":
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
    return match.group("id").strip()


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
    if item.tool_name != "run_command":
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
    route_records = route_records_from_results(tool_results)
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
) -> dict[str, Path]:
    paths = write_native_transcript_artifacts(root, transcript)
    route_records = route_records_from_results(tool_results)
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
