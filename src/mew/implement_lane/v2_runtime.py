"""Default-off implement_v2 runtime scaffold."""

from __future__ import annotations

from ..work_lanes import IMPLEMENT_V2_LANE
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .provider import FakeProviderAdapter, FakeProviderToolCall
from .read_runtime import execute_read_only_tool_call, extract_inspected_paths
from .registry import get_implement_lane_runtime_view
from .replay import build_invalid_tool_result, validate_proof_manifest_pairing
from .tool_policy import list_v2_base_tool_specs, list_v2_tool_specs_for_mode
from .transcript import lane_artifact_namespace
from .types import ImplementLaneInput, ImplementLaneProofManifest, ImplementLaneResult, ImplementLaneTranscriptEvent
from .types import ToolResultEnvelope


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


def _tool_call_identity_errors(tool_calls, *, expected_lane_attempt_id: str) -> tuple[str, ...]:
    errors: list[str] = []
    provider_ids: set[str] = set()
    mew_ids: set[str] = set()
    for call in tool_calls:
        if call.lane_attempt_id != expected_lane_attempt_id:
            errors.append(f"tool_call_wrong_lane_attempt_id:{call.provider_call_id}")
        if not call.provider_call_id:
            errors.append(f"tool_call_missing_provider_call_id:{call.mew_tool_call_id}")
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


__all__ = [
    "describe_implement_v2_runtime",
    "run_fake_exec_implement_v2",
    "run_fake_read_only_implement_v2",
    "run_unavailable_implement_v2",
]
