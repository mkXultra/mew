"""Implement_v2 runtime substrates and live JSON tool loop."""

from __future__ import annotations

import json
from pathlib import Path
import time

from ..work_lanes import IMPLEMENT_V2_LANE
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .provider import FakeProviderAdapter, FakeProviderToolCall, JsonModelProviderAdapter
from ..prompt_sections import render_prompt_sections
from .prompt import build_implement_v2_prompt_sections, implement_v2_prompt_section_metrics
from .read_runtime import execute_read_only_tool_call, extract_inspected_paths
from .registry import get_implement_lane_runtime_view
from .replay import build_invalid_tool_result, validate_proof_manifest_pairing, validate_proof_manifest_write_safety
from .tool_policy import list_v2_base_tool_specs, list_v2_tool_specs_for_mode
from .transcript import lane_artifact_namespace
from .types import ImplementLaneInput, ImplementLaneProofManifest, ImplementLaneResult, ImplementLaneTranscriptEvent
from .types import ToolResultEnvelope
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime


def describe_implement_v2_runtime(*, work_session_id: object, task_id: object) -> dict[str, object]:
    """Describe v2 readiness without enabling the runtime."""

    runtime = get_implement_lane_runtime_view(IMPLEMENT_V2_LANE)
    return {
        "lane": runtime.lane,
        "runtime_id": runtime.runtime_id,
        "runtime_available": runtime.runtime_available,
        "provider_native_tool_loop": runtime.provider_native_tool_loop,
        "writes_allowed": runtime.writes_allowed,
        "fallback_lane": runtime.fallback_lane,
        "artifact_namespace": lane_artifact_namespace(
            work_session_id=work_session_id,
            task_id=task_id,
            lane=runtime.lane,
        ),
        "tool_specs": [spec.as_dict() for spec in list_v2_base_tool_specs()],
    }


def run_unavailable_implement_v2(lane_input: ImplementLaneInput) -> ImplementLaneResult:
    """Return a deterministic unavailable result until v2 is implemented."""

    runtime = get_implement_lane_runtime_view(IMPLEMENT_V2_LANE)
    return ImplementLaneResult(
        status="unavailable",
        lane=runtime.lane,
        user_visible_summary="implement_v2 is registered but not available yet.",
        next_reentry_hint={
            "reason": "implement_v2_runtime_unavailable",
            "fallback_lane": runtime.fallback_lane,
            "requires_separate_lane_attempt": True,
        },
        updated_lane_state={
            "runtime_available": runtime.runtime_available,
            "requested_task_id": lane_input.task_id,
        },
        metrics={
            "provider_native_tool_loop": runtime.provider_native_tool_loop,
            "tool_specs_count": len(list_v2_base_tool_specs()),
        },
    )


def run_live_json_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    model_auth: dict[str, object],
    base_url: str = "",
    timeout: float = 60.0,
    max_turns: int = 10,
    model_json_callable=None,
    progress=None,
) -> ImplementLaneResult:
    """Run a real implement_v2 attempt through the lane-local JSON tool loop.

    This is the first production v2 runtime. It is intentionally separate from
    the legacy v1 THINK/ACT action loop: the model returns provider-shaped tool
    calls, mew pairs every call with a ToolResultEnvelope, and the final result
    carries a v2 proof manifest. Provider-specific function-calling transport is
    still a later optimization; the transport is recorded as ``model_json`` so
    metrics do not confuse it with native provider tool calls.
    """

    if model_json_callable is None:
        from ..agent import call_model_json_with_retries as model_json_callable

    mode = str(lane_input.lane_config.get("mode") or "full").strip() or "full"
    lane_attempt_id = _lane_attempt_id(lane_input, mode=mode)
    adapter = JsonModelProviderAdapter()
    exec_runtime = ImplementV2ManagedExecRuntime(
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
    )
    transcript: list[ImplementLaneTranscriptEvent] = []
    tool_calls: list[object] = []
    tool_results: list[ToolResultEnvelope] = []
    history: list[dict[str, object]] = []
    finish_arguments: dict[str, object] = {}
    seen_provider_call_ids: set[str] = set()
    model_elapsed_seconds = 0.0
    prompt_chars_total = 0
    model_turns = 0
    cleanup_payloads: tuple[dict[str, object], ...] = ()

    try:
        for turn_index in range(1, max(1, int(max_turns)) + 1):
            model_turns = turn_index
            turn_id = f"turn-{turn_index}"
            prompt = _live_json_prompt(
                lane_input,
                lane_attempt_id=lane_attempt_id,
                turn_index=turn_index,
                max_turns=max_turns,
                history=tuple(history),
            )
            prompt_chars_total += len(prompt)
            if progress:
                progress(f"implement_v2 turn #{turn_index}: model_json start")
            started = time.monotonic()
            payload = model_json_callable(
                lane_input.model_backend,
                model_auth,
                prompt,
                lane_input.model,
                base_url,
                timeout,
                log_prefix=f"implement_v2 live_json session={lane_input.work_session_id} turn={turn_index}",
            )
            model_elapsed_seconds += time.monotonic() - started
            normalized = _normalize_live_json_payload(payload, turn_index=turn_index)
            finish_arguments = normalized.get("finish") or {}
            raw_tool_calls = normalized.get("tool_calls") or ()
            if not raw_tool_calls:
                transcript.extend(
                    adapter.transcript_events_for_turn(
                        lane=IMPLEMENT_V2_LANE,
                        lane_attempt_id=lane_attempt_id,
                        turn_id=turn_id,
                        text=str(normalized.get("summary") or ""),
                        tool_calls=(),
                    )
                )
                if finish_arguments:
                    transcript.append(
                        adapter.finish_event_for_turn(
                            lane=IMPLEMENT_V2_LANE,
                            lane_attempt_id=lane_attempt_id,
                            turn_id=turn_id,
                            finish_arguments=finish_arguments,
                        )
                    )
                    break
                finish_arguments = {
                    "outcome": "blocked",
                    "summary": "model returned no tool calls and no finish object",
                }
                break

            current_calls = adapter.normalize_tool_calls(
                lane_attempt_id=lane_attempt_id,
                turn_index=turn_index,
                calls=raw_tool_calls,
            )
            identity_errors = _tool_call_identity_errors(
                current_calls,
                expected_lane_attempt_id=lane_attempt_id,
                seen_provider_call_ids=seen_provider_call_ids,
            )
            if identity_errors:
                current_results = tuple(
                    build_invalid_tool_result(call, reason=f"tool_call_identity_invalid: {'; '.join(identity_errors)}")
                    for call in current_calls
                )
            else:
                approved_write_calls = _auto_approval_records(lane_input, current_calls)
                write_runtime = ImplementV2WriteRuntime(
                    workspace=lane_input.workspace,
                    allowed_write_roots=_allowed_write_roots(lane_input),
                    approved_write_calls=approved_write_calls,
                    allow_governance_writes=bool(lane_input.lane_config.get("allow_governance_writes")),
                )
                current_results = tuple(
                    _execute_live_json_tool(
                        call,
                        lane_input=lane_input,
                        exec_runtime=exec_runtime,
                        write_runtime=write_runtime,
                    )
                    for call in current_calls
                )
                seen_provider_call_ids.update(call.provider_call_id for call in current_calls if call.provider_call_id)
            tool_calls.extend(current_calls)
            tool_results.extend(current_results)
            transcript.extend(
                adapter.transcript_events_for_turn(
                    lane=IMPLEMENT_V2_LANE,
                    lane_attempt_id=lane_attempt_id,
                    turn_id=turn_id,
                    text=str(normalized.get("summary") or ""),
                    tool_calls=current_calls,
                )
            )
            transcript.extend(
                _tool_result_transcript_events(
                    lane_attempt_id=lane_attempt_id,
                    turn_id=turn_id,
                    tool_results=current_results,
                )
            )
            history.append(
                {
                    "turn": turn_index,
                    "summary": str(normalized.get("summary") or ""),
                    "tool_calls": [call.as_dict() for call in current_calls],
                    "tool_results": [
                        _provider_visible_tool_result_for_history(result) for result in current_results
                    ],
                }
            )
            if progress:
                progress(
                    f"implement_v2 turn #{turn_index}: "
                    f"{len(current_calls)} call(s), statuses={','.join(result.status for result in current_results)}"
                )
            if _finish_outcome(finish_arguments) not in {"", "continue"}:
                transcript.append(
                    adapter.finish_event_for_turn(
                        lane=IMPLEMENT_V2_LANE,
                        lane_attempt_id=lane_attempt_id,
                        turn_id=turn_id,
                        finish_arguments=finish_arguments,
                    )
                )
                break
        else:
            finish_arguments = {
                "outcome": "blocked",
                "summary": "implement_v2 reached max_turns before finish",
            }
    finally:
        cleanup_payloads = exec_runtime.cancel_active_commands(
            reason="implement_v2 live_json attempt closed before command finalized"
        )
    if cleanup_payloads:
        tool_results = list(_project_orphaned_command_cleanup(tuple(tool_results), cleanup_payloads))

    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=lane_artifact_namespace(
            work_session_id=lane_input.work_session_id,
            task_id=lane_input.task_id,
            lane=IMPLEMENT_V2_LANE,
        ),
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results),
        metrics={
            "mode": mode,
            "transport": adapter.provider,
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
            "model_turns": model_turns,
            "orphaned_command_cleanup_count": len(cleanup_payloads),
        },
    )
    validation = _validate_write_proof_manifest(manifest)
    status = _live_finish_status(
        finish_arguments,
        validation_valid=validation.valid,
        tool_results=tuple(tool_results),
    )
    prompt_metrics = implement_v2_prompt_section_metrics(lane_input)
    artifact_paths = _write_live_json_artifacts(
        lane_input,
        manifest=manifest,
        transcript=tuple(transcript),
        history=tuple(history),
    )
    summary = str(finish_arguments.get("summary") or "").strip() or _live_status_summary(status)
    return ImplementLaneResult(
        status=status,
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary=summary,
        proof_artifacts=tuple(artifact_paths) or (manifest.artifact_namespace,),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": mode,
            "status": status,
            "replay_valid": validation.valid,
            "transport": adapter.provider,
        },
        updated_lane_state={
            "lane_attempt_id": lane_attempt_id,
            "finish": dict(finish_arguments),
            "proof_manifest": manifest.as_dict(),
            "artifact_paths": list(artifact_paths),
        },
        metrics={
            "completion_credit": status == "completed",
            "mode": mode,
            "provider": adapter.provider,
            "provider_native_tool_loop": False,
            "runtime_id": "implement_v2_model_json_tool_loop",
            "replay_valid": validation.valid,
            "replay_errors": list(validation.errors),
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
            "model_turns": model_turns,
            "model_elapsed_seconds": round(model_elapsed_seconds, 3),
            "prompt_chars_total": prompt_chars_total,
            "prompt_sections": prompt_metrics,
            "write_evidence_count": _write_evidence_count(tool_results),
            "terminal_evidence_count": _terminal_evidence_count(tool_results),
            "orphaned_command_cleanup_count": len(cleanup_payloads),
        },
        transcript=tuple(transcript),
    )


def run_fake_read_only_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    provider_calls: tuple[FakeProviderToolCall | dict[str, object], ...] | list[FakeProviderToolCall | dict[str, object]],
    finish_arguments: dict[str, object],
    provider_message_text: str = "",
) -> ImplementLaneResult:
    """Run a deterministic read-only v2 attempt with the fake provider.

    This is the Phase 3 spike runtime. It is intentionally not wired into the
    production work loop and cannot produce implementation completion.
    """

    lane_attempt_id = _lane_attempt_id(lane_input, mode="read-only")
    turn_id = "turn-1"
    adapter = FakeProviderAdapter()
    tool_calls = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=provider_calls,
    )
    tool_results = tuple(
        execute_read_only_tool_call(
            call,
            workspace=lane_input.workspace,
            allowed_roots=_allowed_read_roots(lane_input),
        )
        for call in tool_calls
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=lane_artifact_namespace(
            work_session_id=lane_input.work_session_id,
            task_id=lane_input.task_id,
            lane=IMPLEMENT_V2_LANE,
        ),
        tool_calls=tool_calls,
        tool_results=tool_results,
        metrics={
            "mode": "read_only",
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
        },
    )
    validation = validate_proof_manifest_pairing(manifest)
    transcript = (
        *adapter.transcript_events_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            text=provider_message_text,
            tool_calls=tool_calls,
        ),
        *_tool_result_transcript_events(
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            tool_results=tool_results,
        ),
        adapter.finish_event_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            finish_arguments=dict(finish_arguments),
        ),
    )
    status = _read_only_finish_status(
        finish_arguments,
        validation_valid=validation.valid,
        tool_results=tool_results,
    )
    read_only_result = _read_only_result(
        finish_arguments=finish_arguments,
        inspected_paths=extract_inspected_paths(tool_results),
        tool_results=tool_results,
    )
    return ImplementLaneResult(
        status=status,
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary=_read_only_summary(status=status, read_only_result=read_only_result),
        proof_artifacts=(manifest.artifact_namespace,),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": "read_only",
            "status": status,
            "analysis_ready_is_completion": False,
            "replay_valid": validation.valid,
        },
        updated_lane_state={
            "read_only_result": read_only_result,
            "proof_manifest": manifest.as_dict(),
        },
        metrics={
            "analysis_ready": status == "analysis_ready",
            "completion_credit": False,
            "mode": "read_only",
            "provider": adapter.provider,
            "read_only_tool_names": [spec.name for spec in list_v2_tool_specs_for_mode("read_only")],
            "replay_valid": validation.valid,
            "replay_errors": list(validation.errors),
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
        },
        transcript=transcript,
    )


def run_fake_exec_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    provider_calls: tuple[FakeProviderToolCall | dict[str, object], ...] | list[FakeProviderToolCall | dict[str, object]],
    finish_arguments: dict[str, object] | None = None,
    provider_message_text: str = "",
) -> ImplementLaneResult:
    """Run a deterministic exec-mode v2 attempt with the fake provider."""

    lane_attempt_id = _lane_attempt_id(lane_input, mode="exec")
    if str(lane_input.lane_config.get("mode") or "").strip() != "exec":
        return _exec_mode_disabled_result(lane_input=lane_input, lane_attempt_id=lane_attempt_id)
    turn_id = "turn-1"
    adapter = FakeProviderAdapter()
    tool_calls = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=provider_calls,
    )
    call_errors = _tool_call_identity_errors(tool_calls, expected_lane_attempt_id=lane_attempt_id)
    if call_errors:
        tool_results = tuple(
            build_invalid_tool_result(call, reason=f"tool_call_identity_invalid: {'; '.join(call_errors)}")
            for call in tool_calls
        )
        cleanup_payloads: tuple[dict[str, object], ...] = ()
    else:
        exec_runtime = ImplementV2ManagedExecRuntime(
            workspace=lane_input.workspace,
            allowed_roots=_allowed_read_roots(lane_input),
        )
        try:
            tool_results = tuple(
                _execute_exec_or_read_tool(call, lane_input=lane_input, exec_runtime=exec_runtime) for call in tool_calls
            )
        finally:
            cleanup_payloads = exec_runtime.cancel_active_commands(
                reason="implement_v2 exec attempt closed before command finalized"
            )
        tool_results = _project_orphaned_command_cleanup(tool_results, cleanup_payloads)
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=lane_artifact_namespace(
            work_session_id=lane_input.work_session_id,
            task_id=lane_input.task_id,
            lane=IMPLEMENT_V2_LANE,
        ),
        tool_calls=tool_calls,
        tool_results=tool_results,
        metrics={
            "mode": "exec",
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
            "orphaned_command_cleanup_count": len(cleanup_payloads),
        },
    )
    validation = validate_proof_manifest_pairing(manifest)
    finish_arguments = dict(finish_arguments or {"outcome": "analysis_ready", "kind": "plan"})
    terminal_evidence_count = sum(1 for result in tool_results if result.evidence_refs and result.status == "completed")
    transcript = (
        *adapter.transcript_events_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            text=provider_message_text,
            tool_calls=tool_calls,
        ),
        *_tool_result_transcript_events(
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            tool_results=tool_results,
        ),
        adapter.finish_event_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            finish_arguments=finish_arguments,
        ),
    )
    status = _exec_finish_status(
        finish_arguments,
        validation_valid=validation.valid,
        terminal_evidence_count=terminal_evidence_count,
        tool_results=tool_results,
    )
    command_result = _command_result(
        finish_arguments=finish_arguments,
        terminal_evidence_count=terminal_evidence_count,
        tool_results=tool_results,
    )
    return ImplementLaneResult(
        status=status,
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary=_exec_summary(status=status, command_result=command_result),
        proof_artifacts=(manifest.artifact_namespace,),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": "exec",
            "status": status,
            "exec_ready_is_completion": False,
            "replay_valid": validation.valid,
        },
        updated_lane_state={
            "command_result": command_result,
            "proof_manifest": manifest.as_dict(),
        },
        metrics={
            "completion_credit": False,
            "mode": "exec",
            "provider": adapter.provider,
            "replay_valid": validation.valid,
            "replay_errors": list(validation.errors),
            "terminal_evidence_count": terminal_evidence_count,
            "orphaned_command_cleanup_count": len(cleanup_payloads),
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
        },
        transcript=transcript,
    )


def run_fake_write_implement_v2(
    lane_input: ImplementLaneInput,
    *,
    provider_calls: tuple[FakeProviderToolCall | dict[str, object], ...] | list[FakeProviderToolCall | dict[str, object]],
    finish_arguments: dict[str, object] | None = None,
    provider_message_text: str = "",
) -> ImplementLaneResult:
    """Run a deterministic write-mode v2 attempt with the fake provider."""

    lane_attempt_id = _lane_attempt_id(lane_input, mode="write")
    if str(lane_input.lane_config.get("mode") or "").strip() != "write":
        return _write_mode_disabled_result(lane_input=lane_input, lane_attempt_id=lane_attempt_id)
    turn_id = "turn-1"
    adapter = FakeProviderAdapter()
    tool_calls = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=provider_calls,
    )
    call_errors = _tool_call_identity_errors(tool_calls, expected_lane_attempt_id=lane_attempt_id)
    if call_errors:
        tool_results = tuple(
            build_invalid_tool_result(call, reason=f"tool_call_identity_invalid: {'; '.join(call_errors)}")
            for call in tool_calls
        )
        cleanup_payloads: tuple[dict[str, object], ...] = ()
    else:
        exec_runtime = ImplementV2ManagedExecRuntime(
            workspace=lane_input.workspace,
            allowed_roots=_allowed_read_roots(lane_input),
        )
        write_runtime = ImplementV2WriteRuntime(
            workspace=lane_input.workspace,
            allowed_write_roots=_allowed_write_roots(lane_input),
            approved_write_calls=_approved_write_calls(lane_input),
            allow_governance_writes=bool(lane_input.lane_config.get("allow_governance_writes")),
        )
        try:
            tool_results = tuple(
                _execute_write_exec_or_read_tool(
                    call,
                    lane_input=lane_input,
                    exec_runtime=exec_runtime,
                    write_runtime=write_runtime,
                )
                for call in tool_calls
            )
        finally:
            cleanup_payloads = exec_runtime.cancel_active_commands(
                reason="implement_v2 write attempt closed before command finalized"
            )
        tool_results = _project_orphaned_command_cleanup(tool_results, cleanup_payloads)
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=lane_artifact_namespace(
            work_session_id=lane_input.work_session_id,
            task_id=lane_input.task_id,
            lane=IMPLEMENT_V2_LANE,
        ),
        tool_calls=tool_calls,
        tool_results=tool_results,
        metrics={
            "mode": "write",
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
            "orphaned_command_cleanup_count": len(cleanup_payloads),
        },
    )
    validation = _validate_write_proof_manifest(manifest)
    finish_arguments = dict(finish_arguments or {"outcome": "analysis_ready", "kind": "plan"})
    write_evidence_count = sum(1 for result in tool_results if result.side_effects and result.status == "completed")
    transcript = (
        *adapter.transcript_events_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            text=provider_message_text,
            tool_calls=tool_calls,
        ),
        *_tool_result_transcript_events(
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            tool_results=tool_results,
        ),
        adapter.finish_event_for_turn(
            lane=IMPLEMENT_V2_LANE,
            lane_attempt_id=lane_attempt_id,
            turn_id=turn_id,
            finish_arguments=finish_arguments,
        ),
    )
    status = _write_finish_status(
        finish_arguments,
        validation_valid=validation.valid,
        tool_results=tool_results,
    )
    write_result = _write_result(
        finish_arguments=finish_arguments,
        write_evidence_count=write_evidence_count,
        tool_results=tool_results,
    )
    return ImplementLaneResult(
        status=status,
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary=_write_summary(status=status, write_result=write_result),
        proof_artifacts=(manifest.artifact_namespace,),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": "write",
            "status": status,
            "write_ready_is_completion": False,
            "replay_valid": validation.valid,
        },
        updated_lane_state={
            "write_result": write_result,
            "proof_manifest": manifest.as_dict(),
        },
        metrics={
            "completion_credit": False,
            "mode": "write",
            "provider": adapter.provider,
            "replay_valid": validation.valid,
            "replay_errors": list(validation.errors),
            "write_evidence_count": write_evidence_count,
            "orphaned_command_cleanup_count": len(cleanup_payloads),
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
        },
        transcript=transcript,
    )


def _exec_mode_disabled_result(*, lane_input: ImplementLaneInput, lane_attempt_id: str) -> ImplementLaneResult:
    return ImplementLaneResult(
        status="blocked",
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary="implement_v2 exec mode is not enabled for this lane attempt.",
        proof_artifacts=(
            lane_artifact_namespace(
                work_session_id=lane_input.work_session_id,
                task_id=lane_input.task_id,
                lane=IMPLEMENT_V2_LANE,
            ),
        ),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": "exec",
            "status": "blocked",
            "reason": "exec_mode_not_enabled",
            "exec_ready_is_completion": False,
        },
        updated_lane_state={
            "lane_attempt_id": lane_attempt_id,
            "command_result": {
                "kind": "command_lifecycle",
                "summary": "exec mode is disabled",
                "terminal_evidence_count": 0,
                "tool_statuses": [],
                "command_run_ids": [],
            },
        },
        metrics={
            "completion_credit": False,
            "mode": "exec",
            "exec_mode_enabled": False,
            "tool_calls": 0,
            "tool_results": 0,
        },
    )


def _write_mode_disabled_result(*, lane_input: ImplementLaneInput, lane_attempt_id: str) -> ImplementLaneResult:
    return ImplementLaneResult(
        status="blocked",
        lane=IMPLEMENT_V2_LANE,
        user_visible_summary="implement_v2 write mode is not enabled for this lane attempt.",
        proof_artifacts=(
            lane_artifact_namespace(
                work_session_id=lane_input.work_session_id,
                task_id=lane_input.task_id,
                lane=IMPLEMENT_V2_LANE,
            ),
        ),
        next_reentry_hint={
            "lane": IMPLEMENT_V2_LANE,
            "mode": "write",
            "status": "blocked",
            "reason": "write_mode_not_enabled",
            "write_ready_is_completion": False,
        },
        updated_lane_state={
            "lane_attempt_id": lane_attempt_id,
            "write_result": {
                "kind": "write_preview_or_apply",
                "summary": "write mode is disabled",
                "write_evidence_count": 0,
                "tool_statuses": [],
                "written_paths": [],
            },
        },
        metrics={
            "completion_credit": False,
            "mode": "write",
            "write_mode_enabled": False,
            "tool_calls": 0,
            "tool_results": 0,
        },
    )


def _project_orphaned_command_cleanup(
    tool_results: tuple[ToolResultEnvelope, ...],
    cleanup_payloads: tuple[dict[str, object], ...],
) -> tuple[ToolResultEnvelope, ...]:
    if not cleanup_payloads:
        return tool_results
    cleanup_by_run_id = {
        str(payload.get("command_run_id") or ""): dict(payload)
        for payload in cleanup_payloads
        if str(payload.get("command_run_id") or "").strip()
    }
    if not cleanup_by_run_id:
        return tool_results
    projected = []
    for result in tool_results:
        command_run_id = _result_command_run_id(result)
        cleanup_payload = cleanup_by_run_id.get(command_run_id)
        if result.status == "yielded" and cleanup_payload:
            projected.append(
                ToolResultEnvelope(
                    lane_attempt_id=result.lane_attempt_id,
                    provider_call_id=result.provider_call_id,
                    mew_tool_call_id=result.mew_tool_call_id,
                    tool_name=result.tool_name,
                    status="interrupted",
                    is_error=True,
                    content=(cleanup_payload,),
                    content_refs=result.content_refs,
                    evidence_refs=(),
                    side_effects=result.side_effects,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                )
            )
        else:
            projected.append(result)
    return tuple(projected)


def _result_command_run_id(result: ToolResultEnvelope) -> str:
    for item in result.content:
        if isinstance(item, dict) and item.get("command_run_id"):
            return str(item.get("command_run_id"))
    return ""


def _execute_write_exec_or_read_tool(
    call,
    *,
    lane_input: ImplementLaneInput,
    exec_runtime: ImplementV2ManagedExecRuntime,
    write_runtime: ImplementV2WriteRuntime,
):
    if call.tool_name in WRITE_TOOL_NAMES:
        return write_runtime.execute(call)
    if call.tool_name in EXEC_TOOL_NAMES:
        return build_invalid_tool_result(
            call,
            reason=(
                f"{call.tool_name} is not available in implement_v2 write mode; "
                "use exec mode for managed command execution and keep write mode mutation-gated"
            ),
        )
    return execute_read_only_tool_call(
        call,
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
    )


def _execute_exec_or_read_tool(
    call,
    *,
    lane_input: ImplementLaneInput,
    exec_runtime: ImplementV2ManagedExecRuntime,
):
    if call.tool_name in EXEC_TOOL_NAMES:
        return exec_runtime.execute(call)
    return execute_read_only_tool_call(
        call,
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
    )


def _execute_live_json_tool(
    call,
    *,
    lane_input: ImplementLaneInput,
    exec_runtime: ImplementV2ManagedExecRuntime,
    write_runtime: ImplementV2WriteRuntime,
):
    if call.tool_name in WRITE_TOOL_NAMES:
        if not _allowed_write_roots(lane_input):
            return build_invalid_tool_result(call, reason="write tools are disabled; pass --allow-write PATH")
        return write_runtime.execute(call)
    if call.tool_name in EXEC_TOOL_NAMES:
        if call.tool_name == "run_tests" and not bool(lane_input.lane_config.get("allow_verify")):
            return build_invalid_tool_result(call, reason="run_tests is disabled; pass --allow-verify")
        if call.tool_name == "run_command" and not bool(lane_input.lane_config.get("allow_shell")):
            return build_invalid_tool_result(call, reason="run_command is disabled; pass --allow-shell")
        return exec_runtime.execute(call)
    return execute_read_only_tool_call(
        call,
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
    )


def _tool_call_identity_errors(
    tool_calls,
    *,
    expected_lane_attempt_id: str,
    seen_provider_call_ids: set[str] | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    provider_ids: set[str] = set()
    mew_ids: set[str] = set()
    seen_provider_call_ids = set(seen_provider_call_ids or ())
    for call in tool_calls:
        if call.lane_attempt_id != expected_lane_attempt_id:
            errors.append(f"tool_call_wrong_lane_attempt_id:{call.provider_call_id}")
        if not call.provider_call_id:
            errors.append(f"tool_call_missing_provider_call_id:{call.mew_tool_call_id}")
        if call.provider_call_id and call.provider_call_id in seen_provider_call_ids:
            errors.append(f"duplicate_provider_call_id_across_turns:{call.provider_call_id}")
        if call.provider_call_id in provider_ids:
            errors.append(f"duplicate_provider_call_id:{call.provider_call_id}")
        provider_ids.add(call.provider_call_id)
        if call.mew_tool_call_id in mew_ids:
            errors.append(f"duplicate_mew_tool_call_id:{call.mew_tool_call_id}")
        mew_ids.add(call.mew_tool_call_id)
    return tuple(errors)


def _lane_attempt_id(lane_input: ImplementLaneInput, *, mode: str) -> str:
    safe_session = _safe_id_part(lane_input.work_session_id, "ws")
    safe_task = _safe_id_part(lane_input.task_id, "task")
    safe_mode = _safe_id_part(mode, "mode")
    return f"{IMPLEMENT_V2_LANE}:{safe_session}:{safe_task}:{safe_mode}"


def _allowed_read_roots(lane_input: ImplementLaneInput) -> tuple[str, ...]:
    raw_roots = lane_input.lane_config.get("allowed_read_roots")
    if isinstance(raw_roots, (list, tuple)):
        roots = [str(root) for root in raw_roots if str(root or "").strip()]
    else:
        roots = []
    return tuple(roots or [lane_input.workspace])


def _allowed_write_roots(lane_input: ImplementLaneInput) -> tuple[str, ...]:
    raw_roots = lane_input.lane_config.get("allowed_write_roots")
    if isinstance(raw_roots, (list, tuple)):
        return tuple(str(root) for root in raw_roots if str(root or "").strip())
    return ()


def _approved_write_calls(lane_input: ImplementLaneInput) -> tuple[object, ...]:
    raw_approvals = lane_input.lane_config.get("approved_write_calls")
    if isinstance(raw_approvals, (list, tuple)):
        return tuple(raw_approvals)
    return ()


def _validate_write_proof_manifest(manifest: ImplementLaneProofManifest):
    pairing = validate_proof_manifest_pairing(manifest)
    safety = validate_proof_manifest_write_safety(manifest)
    errors = (*pairing.errors, *safety.errors)
    if not errors and pairing.call_count == safety.call_count and pairing.result_count == safety.result_count:
        return pairing
    return type(pairing)(
        valid=not errors,
        errors=errors,
        call_count=pairing.call_count,
        result_count=pairing.result_count,
    )


def _tool_result_transcript_events(
    *,
    lane_attempt_id: str,
    turn_id: str,
    tool_results,
) -> tuple[ImplementLaneTranscriptEvent, ...]:
    from .transcript import build_transcript_event

    return tuple(
        build_transcript_event(
            kind="tool_result",
            lane=IMPLEMENT_V2_LANE,
            turn_id=turn_id,
            index=index,
            lane_attempt_id=lane_attempt_id,
            payload=result.as_dict(),
        )
        for index, result in enumerate(tool_results, start=100)
    )


def _read_only_finish_status(
    finish_arguments: dict[str, object],
    *,
    validation_valid: bool,
    tool_results,
) -> str:
    if not validation_valid:
        return "failed"
    outcome = str(finish_arguments.get("outcome") or "").strip()
    if outcome == "analysis_ready":
        if any(result.status == "completed" and not result.is_error for result in tool_results):
            return "analysis_ready"
        return "blocked"
    if outcome in {"completed", "task_complete"}:
        return "blocked"
    if outcome in {"blocked", "failed", "deferred"}:
        return outcome
    return "blocked"


def _read_only_result(
    *,
    finish_arguments: dict[str, object],
    inspected_paths: tuple[str, ...],
    tool_results,
) -> dict[str, object]:
    kind = str(finish_arguments.get("kind") or "diagnosis").strip()
    if kind not in {"diagnosis", "plan"}:
        kind = "diagnosis"
    return {
        "kind": kind,
        "summary": str(finish_arguments.get("summary") or ""),
        "inspected_paths": list(inspected_paths),
        "open_questions": _string_list(finish_arguments.get("open_questions")),
        "proposed_next_actions": _string_list(finish_arguments.get("proposed_next_actions")),
        "tool_statuses": [result.status for result in tool_results],
    }


def _read_only_summary(*, status: str, read_only_result: dict[str, object]) -> str:
    summary = str(read_only_result.get("summary") or "").strip()
    if summary and status == "analysis_ready":
        return summary
    if status == "analysis_ready":
        return "implement_v2 read-only analysis is ready."
    if summary:
        return f"implement_v2 read-only attempt ended with status={status}: {summary}"
    return f"implement_v2 read-only attempt ended with status={status}."


def _exec_finish_status(
    finish_arguments: dict[str, object],
    *,
    validation_valid: bool,
    terminal_evidence_count: int,
    tool_results,
) -> str:
    if not validation_valid:
        return "failed"
    if any(result.status in {"failed", "interrupted", "invalid", "denied"} for result in tool_results):
        return "blocked"
    outcome = str(finish_arguments.get("outcome") or "").strip()
    if outcome in {"completed", "task_complete"}:
        return "blocked"
    if outcome == "analysis_ready" and terminal_evidence_count > 0:
        return "analysis_ready"
    if outcome in {"blocked", "failed", "deferred"}:
        return outcome
    return "blocked"


def _write_finish_status(
    finish_arguments: dict[str, object],
    *,
    validation_valid: bool,
    tool_results,
) -> str:
    if not validation_valid:
        return "failed"
    if any(result.status in {"failed", "interrupted", "invalid", "denied"} for result in tool_results):
        return "blocked"
    outcome = str(finish_arguments.get("outcome") or "").strip()
    if outcome in {"completed", "task_complete"}:
        return "blocked"
    if outcome == "analysis_ready" and any(result.status == "completed" for result in tool_results):
        return "analysis_ready"
    if outcome in {"blocked", "failed", "deferred"}:
        return outcome
    return "blocked"


def _write_result(
    *,
    finish_arguments: dict[str, object],
    write_evidence_count: int,
    tool_results,
) -> dict[str, object]:
    return {
        "kind": "write_preview_or_apply",
        "summary": str(finish_arguments.get("summary") or ""),
        "write_evidence_count": write_evidence_count,
        "tool_statuses": [result.status for result in tool_results],
        "written_paths": [
            str(effect.get("path") or "")
            for result in tool_results
            for effect in result.side_effects
            if isinstance(effect, dict) and effect.get("path")
        ],
    }


def _write_summary(*, status: str, write_result: dict[str, object]) -> str:
    summary = str(write_result.get("summary") or "").strip()
    if summary and status == "analysis_ready":
        return summary
    if summary:
        return f"implement_v2 write attempt ended with status={status}: {summary}"
    return f"implement_v2 write attempt ended with status={status}."


def _command_result(
    *,
    finish_arguments: dict[str, object],
    terminal_evidence_count: int,
    tool_results,
) -> dict[str, object]:
    return {
        "kind": "command_lifecycle",
        "summary": str(finish_arguments.get("summary") or ""),
        "terminal_evidence_count": terminal_evidence_count,
        "tool_statuses": [result.status for result in tool_results],
        "command_run_ids": [
            str(item.get("command_run_id"))
            for result in tool_results
            for item in result.content
            if isinstance(item, dict) and item.get("command_run_id")
        ],
    }


def _exec_summary(*, status: str, command_result: dict[str, object]) -> str:
    summary = str(command_result.get("summary") or "").strip()
    if summary and status == "analysis_ready":
        return summary
    if summary:
        return f"implement_v2 exec attempt ended with status={status}: {summary}"
    return f"implement_v2 exec attempt ended with status={status}."


def _string_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value if str(item or "").strip()]


def _safe_id_part(value: object, default: str) -> str:
    text = str(value or "").strip() or default
    safe = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or default


def _live_json_prompt(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    turn_index: int,
    max_turns: int,
    history: tuple[dict[str, object], ...],
) -> str:
    sections = render_prompt_sections(build_implement_v2_prompt_sections(lane_input))
    response_contract = {
        "summary": "short natural-language summary of this turn",
        "tool_calls": [
            {
                "id": "stable-provider-call-id",
                "name": "read_file | search_text | inspect_dir | glob | git_status | git_diff | run_command | run_tests | poll_command | cancel_command | read_command_output | write_file | edit_file | apply_patch",
                "arguments": {"path": "relative/path"},
            }
        ],
        "finish": {
            "outcome": "continue | completed | blocked | failed",
            "summary": "why this attempt can stop",
            "acceptance_evidence": ["tool result or verifier evidence refs"],
        },
    }
    return (
        f"{sections}\n\n"
        "[section:implement_v2_live_json_transport version=v0 stability=dynamic cache_policy=dynamic]\n"
        "Implement V2 Live JSON Transport\n"
        "This run is a real implement_v2 lane attempt. Do not emit v1 THINK/ACT actions. "
        "Return exactly one JSON object. Use tool_calls for observations, edits, and commands. "
        "Use finish only when the task is completed, blocked, or failed. If more work is needed, "
        "set finish.outcome to continue or omit finish. For edits, prefer exact edit_file old/new "
        "(old_string/new_string aliases are accepted) or apply_patch. If the CLI grants accept-edits, you may request apply=true; mew supplies "
        "independent approval outside the model output. If tests or an external verifier matter, "
        "run a concrete run_command or run_tests before claiming completed.\n"
        f"lane_attempt_id: {lane_attempt_id}\n"
        f"turn: {turn_index}/{max_turns}\n"
        f"response_contract_json:\n{json.dumps(response_contract, ensure_ascii=False, indent=2)}\n"
        f"history_json:\n{json.dumps(list(history)[-8:], ensure_ascii=False, indent=2)}\n"
        "[/section:implement_v2_live_json_transport]"
    )


def _normalize_live_json_payload(payload: object, *, turn_index: int) -> dict[str, object]:
    if not isinstance(payload, dict):
        return {
            "summary": "invalid provider payload",
            "tool_calls": (),
            "finish": {"outcome": "failed", "summary": "model returned a non-object payload"},
        }
    summary = str(payload.get("summary") or payload.get("reason") or "")
    finish = payload.get("finish") if isinstance(payload.get("finish"), dict) else {}
    raw_calls = payload.get("tool_calls")
    if raw_calls is None:
        raw_calls = payload.get("tools")
    if raw_calls is None:
        raw_calls = payload.get("calls")
    if not isinstance(raw_calls, list):
        raw_calls = []
    if not raw_calls and isinstance(payload.get("action"), dict):
        action = dict(payload.get("action") or {})
        action_type = str(action.get("type") or "").strip()
        if action_type == "finish":
            finish = {key: value for key, value in action.items() if key != "type"}
            finish.setdefault("outcome", "completed")
        elif action_type:
            raw_calls = [action]
    calls: list[dict[str, object]] = []
    for index, raw in enumerate(raw_calls, start=1):
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or raw.get("tool_name") or raw.get("tool") or raw.get("type") or "").strip()
        if name == "finish":
            finish = dict(raw.get("arguments") if isinstance(raw.get("arguments"), dict) else raw)
            finish.pop("name", None)
            finish.pop("tool_name", None)
            finish.pop("tool", None)
            finish.pop("type", None)
            continue
        arguments = raw.get("arguments")
        if not isinstance(arguments, dict):
            arguments = raw.get("args") if isinstance(raw.get("args"), dict) else None
        if not isinstance(arguments, dict):
            arguments = {
                key: value
                for key, value in raw.items()
                if key not in {"id", "provider_call_id", "name", "tool_name", "tool", "type", "args", "arguments"}
            }
        provider_call_id = str(raw.get("provider_call_id") or raw.get("id") or f"turn-{turn_index}-call-{index}")
        calls.append({"provider_call_id": provider_call_id, "tool_name": name, "arguments": dict(arguments)})
    if finish:
        finish = dict(finish)
        outcome = _finish_outcome(finish)
        if not outcome:
            finish["outcome"] = "completed"
    return {"summary": summary, "tool_calls": tuple(calls), "finish": finish}


def _auto_approval_records(lane_input: ImplementLaneInput, tool_calls) -> tuple[dict[str, object], ...]:
    if not bool(lane_input.lane_config.get("auto_approve_writes")):
        return ()
    approvals = []
    for call in tool_calls:
        if call.tool_name not in WRITE_TOOL_NAMES:
            continue
        approvals.append(
            {
                "provider_call_id": call.provider_call_id,
                "mew_tool_call_id": call.mew_tool_call_id,
                "status": "approved",
                "source": "cli_accept_edits",
                "approval_id": f"cli_accept_edits:{call.provider_call_id}",
            }
        )
    return tuple(approvals)


def _provider_visible_tool_result_for_history(result: ToolResultEnvelope) -> dict[str, object]:
    content = result.provider_visible_content()
    return {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content": content,
    }


def _finish_outcome(finish_arguments: dict[str, object]) -> str:
    return str((finish_arguments or {}).get("outcome") or (finish_arguments or {}).get("status") or "").strip()


def _live_finish_status(
    finish_arguments: dict[str, object],
    *,
    validation_valid: bool,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> str:
    if not validation_valid:
        return "failed"
    outcome = _finish_outcome(finish_arguments)
    if outcome in {"completed", "task_complete", "done", "success"}:
        if _latest_acceptance_result_completed(tool_results):
            return "completed"
        return "blocked"
    if any(result.status in {"failed", "interrupted", "invalid", "denied"} for result in tool_results):
        return "blocked"
    if outcome in {"blocked", "failed", "deferred"}:
        return outcome
    return "blocked"


def _terminal_evidence_count(tool_results) -> int:
    return sum(
        1
        for result in tool_results
        if result.tool_name in EXEC_TOOL_NAMES and result.status == "completed" and bool(result.evidence_refs)
    )


def _write_evidence_count(tool_results) -> int:
    return sum(1 for result in tool_results if result.tool_name in WRITE_TOOL_NAMES and bool(result.side_effects))


def _latest_acceptance_result_completed(tool_results) -> bool:
    for result in reversed(tuple(tool_results)):
        if result.tool_name in EXEC_TOOL_NAMES:
            return result.status == "completed" and bool(result.evidence_refs)
        if result.tool_name in WRITE_TOOL_NAMES:
            return result.status == "completed" and bool(result.side_effects)
    return False


def _live_status_summary(status: str) -> str:
    if status == "completed":
        return "implement_v2 completed with paired tool evidence."
    return f"implement_v2 live_json attempt ended with status={status}."


def _write_live_json_artifacts(
    lane_input: ImplementLaneInput,
    *,
    manifest: ImplementLaneProofManifest,
    transcript: tuple[ImplementLaneTranscriptEvent, ...],
    history: tuple[dict[str, object], ...],
) -> tuple[str, ...]:
    artifact_dir = str(lane_input.lane_config.get("artifact_dir") or "").strip()
    if not artifact_dir:
        return ()
    root = Path(artifact_dir).expanduser().resolve(strict=False) / "implement_v2"
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "proof-manifest.json"
    transcript_path = root / "transcript.json"
    history_path = root / "history.json"
    manifest_path.write_text(json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    transcript_path.write_text(
        json.dumps([event.as_dict() for event in transcript], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    history_path.write_text(json.dumps(list(history), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return (str(manifest_path), str(transcript_path), str(history_path))


__all__ = [
    "describe_implement_v2_runtime",
    "run_live_json_implement_v2",
    "run_fake_exec_implement_v2",
    "run_fake_read_only_implement_v2",
    "run_fake_write_implement_v2",
    "run_unavailable_implement_v2",
]
