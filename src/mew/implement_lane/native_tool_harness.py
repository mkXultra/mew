"""Phase 3 native implement_v2 harness over provider-native transcript items."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import time
from typing import Mapping

from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .native_fake_provider import PHASE3_TRANSPORT_CHANGE, NativeFakeProvider
from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    build_synthetic_error_output,
    normalize_codex_response_items,
    validate_native_transcript_pairing,
    write_native_transcript_artifacts,
)
from .read_runtime import READ_ONLY_TOOL_NAMES, execute_read_only_tool_call
from .types import ImplementLaneInput, ImplementLaneResult, ToolCallEnvelope, ToolResultEnvelope
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
        task_contract=dict(lane_input.task_contract),
        source_mutation_roots=tuple(str(root) for root in lane_config.get("source_mutation_roots") or (str(workspace),)),
    )
    write_runtime = ImplementV2WriteRuntime(
        workspace=workspace,
        allowed_write_roots=allowed_write_roots,
        approved_write_calls=_approved_write_calls(lane_config),
        allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
    )

    items: list[NativeTranscriptItem] = []
    tool_results: list[ToolResultEnvelope] = []
    tool_latencies: list[dict[str, object]] = []
    first_write_metric: dict[str, object] | None = None
    first_verifier_metric: dict[str, object] | None = None
    start_monotonic = time.monotonic()
    status = "blocked"
    finish_summary = ""

    for turn_index in range(1, max_turns + 1):
        request_descriptor = _request_descriptor(
            lane_attempt_id=lane_attempt_id,
            turn_index=turn_index,
            transcript_items=items,
        )
        response = provider.next_response(request_descriptor)
        if response is None:
            break

        normalized = normalize_codex_response_items(
            response.items,
            lane_attempt_id=lane_attempt_id,
            provider=provider.provider,
            model=provider.model,
            turn_id=f"turn-{turn_index}",
        )
        turn_items = _renumber_items(normalized.items, start_sequence=len(items) + 1)
        items.extend(turn_items)

        calls = sorted(
            (item for item in turn_items if item.kind in CALL_ITEM_KINDS),
            key=lambda item: (item.output_index, item.sequence),
        )
        accepted_finish: NativeTranscriptItem | None = None
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
            )
            latency_finished = time.monotonic()
            output = _native_output_from_result(call, result, sequence=0)
            output_records.append(output)
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
            if call.kind == "finish_call" and result.status == "completed" and not result.is_error:
                accepted_finish = call
                status = "completed"
                finish_summary = _finish_summary(call)

        for output in output_records:
            items.append(replace(output, sequence=len(items) + 1))
        if accepted_finish is not None:
            break

    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider.provider,
        model=provider.model,
        items=tuple(items),
    )
    validation = validate_native_transcript_pairing(transcript)
    if not validation.valid:
        raise ValueError(f"invalid native transcript: {', '.join(validation.errors)}")

    metrics = {
        **PHASE3_NATIVE_SURFACE,
        "status": status,
        "turn_count": len(provider.requests),
        "tool_latency": tuple(tool_latencies),
        "first_write_latency": first_write_metric
        or {"turn_index": None, "call_id": "", "tool_name": "", "wall_seconds": None},
        "first_write_latency_turn": (first_write_metric or {}).get("turn_index"),
        "first_verifier_latency": first_verifier_metric
        or {"turn_index": None, "call_id": "", "tool_name": "", "wall_seconds": None},
        "pairing": validation.as_dict(),
    }
    proof_artifacts: tuple[str, ...] = ()
    if artifact_root is not None:
        paths = _write_phase3_native_artifacts(Path(artifact_root), transcript)
        proof_artifacts = tuple(str(path) for path in paths.values())
    return NativeImplementV2HarnessResult(
        status=status,
        transcript=transcript,
        proof_artifacts=proof_artifacts,
        metrics=metrics,
        finish_summary=finish_summary,
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
) -> ToolResultEnvelope:
    if not call.call_id:
        return _invalid_result(call, reason="native tool call is missing call_id")
    arguments, error = _arguments(call)
    if error:
        return _invalid_result(call, reason=error)
    envelope = ToolCallEnvelope(
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
    if call.kind == "finish_call":
        return _finish_result(envelope)
    if call.tool_name in READ_ONLY_TOOL_NAMES:
        return execute_read_only_tool_call(envelope, workspace=workspace, allowed_roots=allowed_read_roots)
    if call.tool_name in EXEC_TOOL_NAMES:
        return exec_runtime.execute(envelope)
    if call.tool_name in WRITE_TOOL_NAMES:
        if not _side_effect_id_valid(call):
            return _invalid_result(call, reason="side-effecting tool call has invalid provider id")
        if bool(lane_config.get("auto_approve_writes")):
            write_runtime = ImplementV2WriteRuntime(
                workspace=workspace,
                allowed_write_roots=allowed_write_roots,
                approved_write_calls=(
                    {"status": "approved", "provider_call_id": call.call_id, "source": "phase3-auto"},
                ),
                allow_governance_writes=bool(lane_config.get("allow_governance_writes")),
            )
        return write_runtime.execute(envelope)
    return _invalid_result(call, reason=f"unknown native tool: {call.tool_name}")


def _native_output_from_result(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    sequence: int,
) -> NativeTranscriptItem:
    if call.kind == "finish_call":
        output_kind = "finish_output"
    elif call.kind == "custom_tool_call":
        output_kind = "custom_tool_call_output"
    else:
        output_kind = "function_call_output"
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
        output_text_or_ref=result.natural_result_text(),
        status=_native_output_status(call, result),
        is_error=result.is_error,
        content_refs=result.content_refs,
        evidence_refs=result.evidence_refs,
    )


def _finish_result(call: ToolCallEnvelope) -> ToolResultEnvelope:
    outcome = str(call.arguments.get("outcome") or call.arguments.get("status") or "").strip().lower()
    task_done = call.arguments.get("task_done")
    blocked = outcome in {"blocked", "continue"} or task_done is False
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
        return {"input": call.custom_input_text}, ""
    return {}, ""


def _renumber_items(items: tuple[NativeTranscriptItem, ...], *, start_sequence: int) -> tuple[NativeTranscriptItem, ...]:
    return tuple(replace(item, sequence=start_sequence + index) for index, item in enumerate(items))


def _request_descriptor(
    *,
    lane_attempt_id: str,
    turn_index: int,
    transcript_items: list[NativeTranscriptItem],
) -> dict[str, object]:
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "fake_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": lane_attempt_id,
        "turn_index": turn_index,
        "input_item_count": len(transcript_items),
        "model_json_main_path_detected": False,
    }


def _approved_write_calls(lane_config: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    raw = lane_config.get("approved_write_calls")
    return tuple(dict(item) for item in raw) if isinstance(raw, list) else ()


def _side_effect_id_valid(call: NativeTranscriptItem) -> bool:
    return bool(call.call_id and call.provider_item_id)


def _result_is_write_like(result: ToolResultEnvelope) -> bool:
    if result.tool_name in WRITE_TOOL_NAMES and result.status == "completed" and not result.is_error:
        return True
    return any(str(effect.get("kind") or "") in {"file_write", "source_tree_delta"} for effect in result.side_effects)


def _result_is_verifier_like(result: ToolResultEnvelope) -> bool:
    if result.tool_name == "run_tests":
        return True
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return str(payload.get("command_intent") or "") == "verifier"


def _native_output_status(call: NativeTranscriptItem, result: ToolResultEnvelope) -> str:
    if call.kind == "finish_call":
        payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
        if result.is_error and str(payload.get("outcome") or "").strip().lower() in {"blocked", "continue"}:
            return "blocked"
    return result.status


def _call_order_key(call: NativeTranscriptItem) -> tuple[int, int]:
    return (call.output_index, call.sequence)


def _write_phase3_native_artifacts(root: Path, transcript: NativeTranscript) -> dict[str, Path]:
    paths = write_native_transcript_artifacts(root, transcript)
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
