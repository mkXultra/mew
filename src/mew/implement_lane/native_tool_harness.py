"""Phase 3 native implement_v2 harness over provider-native transcript items."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import time
from typing import Mapping

from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .native_fake_provider import PHASE3_TRANSPORT_CHANGE, NativeFakeProvider
from .native_provider_adapter import (
    NativeResponsesStreamParseResult,
    build_custom_tool_call_output_input_item,
    build_function_call_output_input_item,
    build_responses_request_descriptor,
    call_codex_native_responses,
)
from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    build_synthetic_error_output,
    native_transcript_hash,
    normalize_codex_response_items,
    validate_native_transcript_pairing,
    write_native_transcript_artifacts,
)
from .prompt import build_implement_v2_prompt_sections
from .read_runtime import READ_ONLY_TOOL_NAMES, execute_read_only_tool_call
from .tool_policy import list_v2_tool_specs_for_mode
from .types import ImplementLaneInput, ImplementLaneResult, ToolCallEnvelope, ToolResultEnvelope
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime
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

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []
        if self.responses is None:
            self.responses = []
        if not self.model:
            self.model = str(self.lane_input.model or "gpt-5.5")

    def next_response(self, request_descriptor: Mapping[str, object]) -> NativeResponsesStreamParseResult | None:
        descriptor = _live_responses_request_descriptor(
            self.lane_input,
            provider=self.provider,
            model=self.model,
            request_descriptor=request_descriptor,
        )
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
        if result.status in {"failed", "incomplete"} or (result.errors and not result.transcript.items):
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
            lane_input=lane_input,
            lane_attempt_id=lane_attempt_id,
            turn_index=turn_index,
            transcript_items=items,
        )
        response = provider.next_response(request_descriptor)
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
        **_native_surface_for_provider(provider),
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
        paths = _write_native_artifacts(Path(artifact_root), transcript, provider=provider)
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
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    turn_index: int,
    transcript_items: list[NativeTranscriptItem],
) -> dict[str, object]:
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native" if _provider_is_live(lane_input) else "fake_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": lane_attempt_id,
        "turn_index": turn_index,
        "input_item_count": len(transcript_items),
        "input_items": _responses_input_items(lane_input, transcript_items),
        "transcript_window": [item.as_dict() for item in transcript_items],
        "instructions": _native_instructions(lane_input),
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
        tool_specs=list_v2_tool_specs_for_mode(mode),
        transcript_window=request_descriptor.get("transcript_window") or (),
        reasoning=reasoning,
        provider_request_id=f"{request_descriptor.get('lane_attempt_id')}:turn:{request_descriptor.get('turn_index')}",
        prompt_cache_key=str(request_descriptor.get("lane_attempt_id") or ""),
    )


def _native_instructions(lane_input: ImplementLaneInput) -> str:
    return render_prompt_sections(build_implement_v2_prompt_sections(lane_input))


def _responses_input_items(
    lane_input: ImplementLaneInput,
    transcript_items: list[NativeTranscriptItem],
) -> list[dict[str, object]]:
    task_payload = {
        "task_contract": dict(lane_input.task_contract),
        "persisted_lane_state": dict(lane_input.persisted_lane_state),
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
        converted = _responses_input_item_from_transcript_item(item)
        if converted:
            items.append(converted)
    return items


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
    return ImplementLaneResult(
        status="failed",
        lane="implement_v2",
        user_visible_summary=f"implement_v2 native provider failed: {error}",
        proof_artifacts=(),
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
        },
    )


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


def _write_native_artifacts(root: Path, transcript: NativeTranscript, *, provider: object) -> dict[str, Path]:
    paths = write_native_transcript_artifacts(root, transcript)
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
