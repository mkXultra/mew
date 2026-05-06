"""Implement_v2 runtime substrates and live JSON tool loop."""

from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import re
import time
from dataclasses import replace

from ..acceptance import acceptance_done_gate_decision
from ..errors import ModelBackendError
from ..work_lanes import IMPLEMENT_V2_LANE
from .exec_runtime import EXEC_TOOL_NAMES, ImplementV2ManagedExecRuntime
from .provider import FakeProviderAdapter, FakeProviderToolCall, JsonModelProviderAdapter
from ..prompt_sections import render_prompt_sections
from .prompt import build_implement_v2_prompt_sections, implement_v2_prompt_section_metrics, is_hard_runtime_artifact_task
from .read_runtime import execute_read_only_tool_call, extract_inspected_paths
from .registry import get_implement_lane_runtime_view
from .replay import build_invalid_tool_result, validate_proof_manifest_pairing, validate_proof_manifest_write_safety
from .tool_policy import list_v2_base_tool_specs, list_v2_tool_specs_for_mode
from .transcript import lane_artifact_namespace
from .types import ImplementLaneInput, ImplementLaneProofManifest, ImplementLaneResult, ImplementLaneTranscriptEvent
from .types import ToolCallEnvelope
from .types import ToolResultEnvelope
from .write_runtime import WRITE_TOOL_NAMES, ImplementV2WriteRuntime

_COMPLETED_FINISH_OUTCOMES = {"completed", "task_complete", "done", "success"}
_EVIDENCE_PROVIDER_CALL_RE = re.compile(r"\bcall-[A-Za-z0-9_.:-]+\b")
_PROVIDER_ID_TOKEN_RE = re.compile(r"[A-Za-z0-9_.:-]+")
_PROVIDER_HISTORY_TEXT_LIMIT = 2400
_PROVIDER_HISTORY_TEXT_HEAD = 1200
_PROVIDER_HISTORY_TEXT_TAIL = 900
_PROVIDER_HISTORY_LIST_LIMIT = 24
_PROVIDER_HISTORY_CLIP_KEYS = {
    "command",
    "content",
    "diff",
    "stderr",
    "stderr_tail",
    "stdout",
    "stdout_tail",
    "summary",
    "text",
}
_PROVIDER_HISTORY_TERMINAL_TOOL_NAMES = {"run_command", "run_tests", "poll_command", "cancel_command"}
_PROVIDER_HISTORY_TERMINAL_DIAGNOSTIC_KEYS = (
    "reason",
    "error",
    "message",
    "failure_class",
    "diagnostic",
    "diagnostics",
    "validation_error",
    "blocked_reason",
)
_HARD_RUNTIME_FRONTIER_SCHEMA_VERSION = 1
_FRONTIER_LIST_LIMIT = 8
_FRONTIER_TEXT_LIMIT = 500
_FRONTIER_COMMAND_TEXT_LIMIT = 1200


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
    artifact_namespace = lane_artifact_namespace(
        work_session_id=lane_input.work_session_id,
        task_id=lane_input.task_id,
        lane=IMPLEMENT_V2_LANE,
    )
    adapter = JsonModelProviderAdapter()
    exec_runtime = ImplementV2ManagedExecRuntime(
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
        allow_shell=bool(lane_input.lane_config.get("allow_shell")),
        run_command_available=_v2_tool_available(lane_input, "run_command"),
        route_run_tests_shell_surface=_route_run_tests_shell_surface(lane_input),
    )
    transcript: list[ImplementLaneTranscriptEvent] = []
    tool_calls: list[object] = []
    tool_results: list[ToolResultEnvelope] = []
    history: list[dict[str, object]] = []
    prompt_history: list[dict[str, object]] = []
    finish_arguments: dict[str, object] = {}
    seen_provider_call_ids: set[str] = set()
    model_elapsed_seconds = 0.0
    prompt_chars_total = 0
    model_turns = 0
    model_error: dict[str, object] = {}
    cleanup_payloads: tuple[dict[str, object], ...] = ()
    closeout_payloads: tuple[dict[str, object], ...] = ()
    finish_gate_decision: dict[str, object] = {}
    finish_gate_block_count = 0
    run_started = time.monotonic()
    base_max_turns = max(1, int(max_turns))
    turn_budget_limit = base_max_turns
    terminal_failure_reaction_turn_limit = _terminal_failure_reaction_turn_limit(lane_input, base_max_turns)
    terminal_failure_reaction_turns_used = 0
    tool_contract_recovery_turn_limit = _tool_contract_recovery_turn_limit(lane_input)
    tool_contract_recovery_turns_used = 0
    tool_contract_recovery_instruction = ""
    hard_runtime_frontier_state = _initial_hard_runtime_frontier_state(lane_input)
    hard_runtime_frontier_enabled = bool(hard_runtime_frontier_state) or is_hard_runtime_artifact_task(
        lane_input.task_contract
    )
    turn_index = 0

    def extend_for_terminal_failure_reaction_if_available(
        tool_result_slice: tuple[ToolResultEnvelope, ...],
        *,
        reason: str,
    ) -> bool:
        nonlocal terminal_failure_reaction_turns_used, turn_budget_limit
        if not _should_extend_for_terminal_failure_reaction(
            lane_input,
            tool_result_slice,
            turn_index=turn_index,
            turn_budget_limit=turn_budget_limit,
            reaction_turns_used=terminal_failure_reaction_turns_used,
            reaction_turn_limit=terminal_failure_reaction_turn_limit,
            run_started=run_started,
        ):
            return False
        terminal_failure_reaction_turns_used += 1
        turn_budget_limit += 1
        if progress:
            progress(
                "implement_v2 extending one terminal-failure reaction turn "
                f"({terminal_failure_reaction_turns_used}/{terminal_failure_reaction_turn_limit}) "
                f"reason={reason}"
            )
        return True

    def extend_for_tool_contract_recovery_if_available(
        tool_result_slice: tuple[ToolResultEnvelope, ...],
        *,
        reason: str,
    ) -> bool:
        nonlocal tool_contract_recovery_turns_used, turn_budget_limit, tool_contract_recovery_instruction
        if not _should_extend_for_tool_contract_recovery(
            lane_input,
            tool_result_slice,
            turn_index=turn_index,
            turn_budget_limit=turn_budget_limit,
            recovery_turns_used=tool_contract_recovery_turns_used,
            recovery_turn_limit=tool_contract_recovery_turn_limit,
            run_started=run_started,
        ):
            return False
        result = _latest_tool_contract_misuse_result(tool_result_slice)
        tool_contract_recovery_turns_used += 1
        turn_budget_limit += 1
        tool_contract_recovery_instruction = _tool_contract_recovery_instruction(result)
        if progress:
            progress(
                "implement_v2 extending one tool-contract recovery turn "
                f"({tool_contract_recovery_turns_used}/{tool_contract_recovery_turn_limit}) "
                f"reason={reason}"
            )
        return True

    try:
        while turn_index < turn_budget_limit:
            turn_index += 1
            model_turns = turn_index
            turn_id = f"turn-{turn_index}"
            prompt = _live_json_prompt(
                lane_input,
                lane_attempt_id=lane_attempt_id,
                hard_runtime_frontier_state=hard_runtime_frontier_state,
                turn_index=turn_index,
                max_turns=turn_budget_limit,
                base_max_turns=base_max_turns,
                terminal_failure_reaction_turns_used=terminal_failure_reaction_turns_used,
                terminal_failure_reaction_turn_limit=terminal_failure_reaction_turn_limit,
                tool_contract_recovery_turns_used=tool_contract_recovery_turns_used,
                tool_contract_recovery_turn_limit=tool_contract_recovery_turn_limit,
                tool_contract_recovery_instruction=tool_contract_recovery_instruction,
                history=tuple(prompt_history),
            )
            tool_contract_recovery_instruction = ""
            prompt_chars_total += len(prompt)
            if progress:
                progress(f"implement_v2 turn #{turn_index}: model_json start")
            started = time.monotonic()
            try:
                payload = model_json_callable(
                    lane_input.model_backend,
                    model_auth,
                    prompt,
                    lane_input.model,
                    base_url,
                    timeout,
                    log_prefix=f"implement_v2 live_json session={lane_input.work_session_id} turn={turn_index}",
                )
            except ModelBackendError as exc:
                model_elapsed_seconds += time.monotonic() - started
                model_error = _live_json_model_error(exc)
                finish_arguments = {
                    "outcome": "failed",
                    "summary": str(model_error.get("message") or "model_json call failed"),
                    "failure_class": model_error.get("failure_class") or "model_backend_error",
                }
                transcript.extend(
                    adapter.transcript_events_for_turn(
                        lane=IMPLEMENT_V2_LANE,
                        lane_attempt_id=lane_attempt_id,
                        turn_id=turn_id,
                        text=str(model_error.get("message") or ""),
                        tool_calls=(),
                    )
                )
                transcript.append(
                    adapter.finish_event_for_turn(
                        lane=IMPLEMENT_V2_LANE,
                        lane_attempt_id=lane_attempt_id,
                        turn_id=turn_id,
                        finish_arguments=finish_arguments,
                    )
                )
                history.append(
                    {
                        "turn": turn_index,
                        "summary": "model_json_error",
                        "model_error": dict(model_error),
                        "tool_calls": [],
                        "tool_results": [],
                    }
                )
                prompt_history.append(dict(history[-1]))
                if progress:
                    progress(
                        f"implement_v2 turn #{turn_index}: model_json failed "
                        f"class={model_error.get('failure_class')}"
                    )
                break
            model_elapsed_seconds += time.monotonic() - started
            normalized = _normalize_live_json_payload(payload, turn_index=turn_index)
            finish_arguments = normalized.get("finish") or {}
            frontier_state_update = (
                normalized.get("frontier_state_update") if isinstance(normalized.get("frontier_state_update"), dict) else {}
            )
            if frontier_state_update:
                hard_runtime_frontier_enabled = True
            raw_tool_calls = normalized.get("tool_calls") or ()
            if not raw_tool_calls:
                if hard_runtime_frontier_enabled or frontier_state_update:
                    hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
                        existing=hard_runtime_frontier_state,
                        update=frontier_state_update,
                        tool_results=tuple(tool_results),
                        artifact_namespace=artifact_namespace,
                    )
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
                    finish_gate_decision = _live_acceptance_done_gate(
                        lane_input,
                        finish_arguments,
                        tuple(tool_results),
                    )
                    if (
                        _finish_outcome(finish_arguments) in _COMPLETED_FINISH_OUTCOMES
                        and finish_gate_decision.get("decision") != "allow_complete"
                    ):
                        finish_gate_block_count += 1
                        continuation_prompt = _finish_gate_continuation_text(finish_gate_decision)
                        transcript.append(
                            _finish_gate_transcript_event(
                                lane_attempt_id=lane_attempt_id,
                                turn_id=turn_id,
                                decision=finish_gate_decision,
                            )
                        )
                        if turn_index < turn_budget_limit:
                            history.append(
                                _finish_gate_history(
                                    turn_index=turn_index,
                                    decision=finish_gate_decision,
                                    continuation_prompt=continuation_prompt,
                                )
                            )
                            prompt_history.append(dict(history[-1]))
                            finish_arguments = {
                                "outcome": "continue",
                                "summary": continuation_prompt,
                                "finish_gate": finish_gate_decision,
                            }
                            continue
                        finish_arguments = {
                            "outcome": "blocked",
                            "summary": continuation_prompt,
                            "finish_gate": finish_gate_decision,
                        }
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
            current_calls, provider_call_id_repairs = _repair_live_json_provider_call_ids_for_replay(
                current_calls,
                seen_provider_call_ids=seen_provider_call_ids,
            )
            identity_errors = _tool_call_identity_errors(
                current_calls,
                expected_lane_attempt_id=lane_attempt_id,
                seen_provider_call_ids=seen_provider_call_ids,
            ) + provider_call_id_repairs
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
            finish_gate_tool_results = tuple(tool_results) + tuple(current_results)
            if _should_closeout_for_terminal_failure_reaction(
                current_results,
                turn_index=turn_index,
                turn_budget_limit=turn_budget_limit,
            ):
                closeout_chunk, cleanup_chunk = _closeout_active_commands(
                    exec_runtime,
                    lane_input=lane_input,
                    run_started=run_started,
                )
                closeout_payloads += closeout_chunk
                cleanup_payloads += cleanup_chunk
                current_results = _project_command_closeouts(
                    current_results,
                    closeout_payloads=closeout_chunk,
                    cleanup_payloads=cleanup_chunk,
                )
            tool_calls.extend(current_calls)
            tool_results.extend(current_results)
            if hard_runtime_frontier_enabled or frontier_state_update:
                hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
                    existing=hard_runtime_frontier_state,
                    update=frontier_state_update,
                    tool_results=tuple(tool_results),
                    artifact_namespace=artifact_namespace,
                )
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
            history_entry = {
                "turn": turn_index,
                "summary": str(normalized.get("summary") or ""),
                "tool_calls": [call.as_dict() for call in current_calls],
                "tool_results": [_full_tool_result_for_history(result) for result in current_results],
            }
            prompt_history_entry = {
                "turn": history_entry["turn"],
                "summary": history_entry["summary"],
                "tool_calls": history_entry["tool_calls"],
                "tool_results": [_provider_visible_tool_result_for_history(result) for result in current_results],
            }
            history.append(history_entry)
            prompt_history.append(prompt_history_entry)
            if progress:
                progress(
                    f"implement_v2 turn #{turn_index}: "
                    f"{len(current_calls)} call(s), statuses={','.join(result.status for result in current_results)}"
                )
            if _finish_outcome(finish_arguments) not in {"", "continue"}:
                finish_gate_decision = _live_acceptance_done_gate(
                    lane_input,
                    finish_arguments,
                    finish_gate_tool_results,
                )
                if (
                    _finish_outcome(finish_arguments) in _COMPLETED_FINISH_OUTCOMES
                    and finish_gate_decision.get("decision") != "allow_complete"
                ):
                    finish_gate_block_count += 1
                    continuation_prompt = _finish_gate_continuation_text(finish_gate_decision)
                    transcript.append(
                        _finish_gate_transcript_event(
                            lane_attempt_id=lane_attempt_id,
                            turn_id=turn_id,
                            decision=finish_gate_decision,
                        )
                    )
                    if turn_index < turn_budget_limit:
                        history.append(
                            _finish_gate_history(
                                turn_index=turn_index,
                                decision=finish_gate_decision,
                                continuation_prompt=continuation_prompt,
                            )
                        )
                        prompt_history.append(dict(history[-1]))
                        finish_arguments = {
                            "outcome": "continue",
                            "summary": continuation_prompt,
                            "finish_gate": finish_gate_decision,
                        }
                        continue
                    finish_arguments = {
                        "outcome": "blocked",
                        "summary": continuation_prompt,
                        "finish_gate": finish_gate_decision,
                    }
                    if extend_for_tool_contract_recovery_if_available(
                        current_results,
                        reason="finish_gate_tool_contract_misuse",
                    ):
                        finish_arguments = {
                            "outcome": "continue",
                            "summary": "tool-contract recovery turn reserved after finish gate blocked completion",
                            "finish_gate": finish_gate_decision,
                        }
                        continue
                    if extend_for_terminal_failure_reaction_if_available(
                        current_results,
                        reason="finish_gate_terminal_failure",
                    ):
                        finish_arguments = {
                            "outcome": "continue",
                            "summary": "terminal failure reaction turn reserved after finish gate blocked completion",
                            "finish_gate": finish_gate_decision,
                        }
                        continue
                elif extend_for_tool_contract_recovery_if_available(
                    current_results,
                    reason="finish_with_tool_contract_misuse",
                ):
                    finish_arguments = {
                        "outcome": "continue",
                        "summary": "tool-contract recovery turn reserved before accepting finish",
                    }
                    continue
                elif extend_for_terminal_failure_reaction_if_available(
                    current_results,
                    reason="finish_with_terminal_failure",
                ):
                    finish_arguments = {
                        "outcome": "continue",
                        "summary": "terminal failure reaction turn reserved before accepting finish",
                    }
                    continue
                transcript.append(
                    adapter.finish_event_for_turn(
                        lane=IMPLEMENT_V2_LANE,
                        lane_attempt_id=lane_attempt_id,
                        turn_id=turn_id,
                        finish_arguments=finish_arguments,
                    )
                )
                break
            if extend_for_tool_contract_recovery_if_available(
                current_results,
                reason="continue_tool_contract_misuse",
            ):
                continue
            if extend_for_terminal_failure_reaction_if_available(
                current_results,
                reason="continue_terminal_failure",
            ):
                continue
            if (
                not _has_terminal_failure_result(current_results)
                and extend_for_terminal_failure_reaction_if_available(
                    tuple(tool_results),
                    reason="continue_unresolved_prior_terminal_failure",
                )
            ):
                continue
        else:
            finish_arguments = {
                "outcome": "blocked",
                "summary": "implement_v2 reached max_turns before finish",
            }
    except BaseException:
        cleanup_payloads = exec_runtime.cancel_active_commands(
            reason="implement_v2 live_json attempt closed before command finalized"
        )
        raise
    final_closeout_payloads, final_cleanup_payloads = _closeout_active_commands(
        exec_runtime,
        lane_input=lane_input,
        run_started=run_started,
    )
    closeout_payloads += final_closeout_payloads
    cleanup_payloads += final_cleanup_payloads
    if final_closeout_payloads or final_cleanup_payloads:
        tool_results = list(
            _project_command_closeouts(
                tuple(tool_results),
                closeout_payloads=final_closeout_payloads,
                cleanup_payloads=final_cleanup_payloads,
            )
        )
    if hard_runtime_frontier_enabled or hard_runtime_frontier_state:
        hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
            existing=hard_runtime_frontier_state,
            update={},
            tool_results=tuple(tool_results),
            artifact_namespace=artifact_namespace,
        )

    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=artifact_namespace,
        tool_calls=tuple(tool_calls),
        tool_results=tuple(tool_results),
        metrics={
            "mode": mode,
            "transport": adapter.provider,
            "tool_calls": len(tool_calls),
            "tool_results": len(tool_results),
            "model_turns": model_turns,
            "model_error": dict(model_error),
            "base_max_turns": base_max_turns,
            "turn_budget_limit": turn_budget_limit,
            "terminal_failure_reaction_turn_limit": terminal_failure_reaction_turn_limit,
            "terminal_failure_reaction_turns_used": terminal_failure_reaction_turns_used,
            "tool_contract_recovery_turn_limit": tool_contract_recovery_turn_limit,
            "tool_contract_recovery_turns_used": tool_contract_recovery_turns_used,
            "command_closeout_count": len(closeout_payloads),
            "orphaned_command_cleanup_count": len(cleanup_payloads),
            "finish_gate_block_count": finish_gate_block_count,
            "finish_gate_decision": dict(finish_gate_decision),
        },
    )
    validation = _validate_write_proof_manifest(manifest)
    status = _live_finish_status(
        finish_arguments,
        validation_valid=validation.valid,
        tool_results=tuple(tool_results),
    )
    prompt_metrics = implement_v2_prompt_section_metrics(
        _lane_input_with_hard_runtime_frontier(lane_input, hard_runtime_frontier_state)
    )
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
            "finish_gate_decision": dict(finish_gate_decision),
        },
        updated_lane_state={
            "lane_attempt_id": lane_attempt_id,
            "finish": dict(finish_arguments),
            "finish_gate": dict(finish_gate_decision),
            "proof_manifest": manifest.as_dict(),
            "artifact_paths": list(artifact_paths),
            **({"lane_hard_runtime_frontier": dict(hard_runtime_frontier_state)} if hard_runtime_frontier_state else {}),
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
            "model_error": dict(model_error),
            "model_elapsed_seconds": round(model_elapsed_seconds, 3),
            "base_max_turns": base_max_turns,
            "turn_budget_limit": turn_budget_limit,
            "terminal_failure_reaction_turn_limit": terminal_failure_reaction_turn_limit,
            "terminal_failure_reaction_turns_used": terminal_failure_reaction_turns_used,
            "tool_contract_recovery_turn_limit": tool_contract_recovery_turn_limit,
            "tool_contract_recovery_turns_used": tool_contract_recovery_turns_used,
            "finish_gate_block_count": finish_gate_block_count,
            "finish_gate_decision": dict(finish_gate_decision),
            "prompt_chars_total": prompt_chars_total,
            "prompt_sections": prompt_metrics,
            "write_evidence_count": _write_evidence_count(tool_results),
            "terminal_evidence_count": _terminal_evidence_count(tool_results),
            "command_closeout_count": len(closeout_payloads),
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
            allow_shell=bool(lane_input.lane_config.get("allow_shell")),
            run_command_available=_v2_tool_available(lane_input, "run_command"),
            route_run_tests_shell_surface=_route_run_tests_shell_surface(lane_input),
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
            allow_shell=bool(lane_input.lane_config.get("allow_shell")),
            run_command_available=_v2_tool_available(lane_input, "run_command"),
            route_run_tests_shell_surface=_route_run_tests_shell_surface(lane_input),
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


def _project_command_closeouts(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    closeout_payloads: tuple[dict[str, object], ...],
    cleanup_payloads: tuple[dict[str, object], ...],
) -> tuple[ToolResultEnvelope, ...]:
    if not closeout_payloads and not cleanup_payloads:
        return tool_results
    closeout_by_run_id = {
        str(payload.get("command_run_id") or ""): dict(payload)
        for payload in closeout_payloads
        if str(payload.get("command_run_id") or "").strip()
    }
    cleanup_by_run_id = {
        str(payload.get("command_run_id") or ""): dict(payload)
        for payload in cleanup_payloads
        if str(payload.get("command_run_id") or "").strip()
    }
    if not closeout_by_run_id and not cleanup_by_run_id:
        return tool_results
    projected = []
    for result in tool_results:
        command_run_id = _result_command_run_id(result)
        closeout_payload = closeout_by_run_id.get(command_run_id)
        cleanup_payload = cleanup_by_run_id.get(command_run_id)
        payload = closeout_payload or cleanup_payload
        if result.status == "yielded" and payload:
            payload = _preserve_result_command_context(result, payload)
            status = _projected_command_closeout_status(payload)
            evidence_refs = result.evidence_refs
            if status == "completed" and result.tool_name in EXEC_TOOL_NAMES and not evidence_refs:
                evidence_refs = (f"implement-v2-exec://{result.lane_attempt_id}/{command_run_id}/terminal",)
            projected.append(
                ToolResultEnvelope(
                    lane_attempt_id=result.lane_attempt_id,
                    provider_call_id=result.provider_call_id,
                    mew_tool_call_id=result.mew_tool_call_id,
                    tool_name=result.tool_name,
                    status=status,
                    is_error=status in {"failed", "interrupted"},
                    content=(payload,),
                    content_refs=result.content_refs,
                    evidence_refs=evidence_refs,
                    side_effects=result.side_effects,
                    started_at=result.started_at,
                    finished_at=result.finished_at,
                )
            )
        else:
            projected.append(result)
    return tuple(projected)


def _preserve_result_command_context(result: ToolResultEnvelope, payload: dict[str, object]) -> dict[str, object]:
    preserved = dict(payload)
    previous_payload = next((item for item in result.content if isinstance(item, dict)), {})
    for key in ("tool_name", "effective_tool_name", "command_source", "execution_contract", "tool_contract_recovery"):
        if key in previous_payload and key not in preserved:
            value = previous_payload.get(key)
            preserved[key] = dict(value) if isinstance(value, dict) else value
    return preserved


def _project_orphaned_command_cleanup(
    tool_results: tuple[ToolResultEnvelope, ...],
    cleanup_payloads: tuple[dict[str, object], ...],
) -> tuple[ToolResultEnvelope, ...]:
    return _project_command_closeouts(tool_results, closeout_payloads=(), cleanup_payloads=cleanup_payloads)


def _closeout_active_commands(
    exec_runtime: ImplementV2ManagedExecRuntime,
    *,
    lane_input: ImplementLaneInput,
    run_started: float,
) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    budget = _active_command_closeout_budget_seconds(lane_input, run_started=run_started)
    if budget <= 0:
        cleanup_payloads = exec_runtime.cancel_active_commands(
            reason="implement_v2 active command closeout budget exhausted"
        )
        return (), cleanup_payloads
    closeout_payloads = exec_runtime.finalize_active_commands(timeout_seconds=budget)
    return closeout_payloads, ()


def _active_command_closeout_budget_seconds(lane_input: ImplementLaneInput, *, run_started: float) -> float:
    wall_remaining = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    configured = lane_input.lane_config.get("command_closeout_seconds")
    if configured not in (None, ""):
        try:
            configured_budget = max(0.0, min(3600.0, float(configured)))
        except (TypeError, ValueError):
            return 0.0
        if wall_remaining is None:
            return configured_budget
        return min(configured_budget, wall_remaining)
    if wall_remaining is None:
        return 60.0
    return wall_remaining


def _remaining_wall_budget_seconds(lane_input: ImplementLaneInput, *, run_started: float) -> float | None:
    max_wall = lane_input.task_contract.get("max_wall_seconds")
    if max_wall in (None, ""):
        return None
    try:
        remaining = float(max_wall) - max(0.0, time.monotonic() - run_started)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(600.0, remaining))


def _terminal_failure_reaction_turn_limit(lane_input: ImplementLaneInput, base_max_turns: int) -> int:
    configured = lane_input.lane_config.get("terminal_failure_reaction_turns")
    if configured not in (None, ""):
        try:
            return max(0, min(5, int(configured)))
        except (TypeError, ValueError):
            return 0
    return max(1, min(3, int(base_max_turns) // 8 or 1))


def _tool_contract_recovery_turn_limit(lane_input: ImplementLaneInput) -> int:
    configured = lane_input.lane_config.get("tool_contract_recovery_turns")
    if configured not in (None, ""):
        try:
            return 1 if int(configured) > 0 else 0
        except (TypeError, ValueError):
            return 0
    return 1


def _route_run_tests_shell_surface(lane_input: ImplementLaneInput) -> bool:
    configured = lane_input.lane_config.get("route_run_tests_shell_surface")
    if configured is None:
        configured = lane_input.lane_config.get("auto_route_run_tests_shell_surface")
    if configured in (None, ""):
        return True
    if isinstance(configured, str):
        return configured.strip().lower() not in {"0", "false", "no", "off"}
    return bool(configured)


def _should_extend_for_terminal_failure_reaction(
    lane_input: ImplementLaneInput,
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    turn_index: int,
    turn_budget_limit: int,
    reaction_turns_used: int,
    reaction_turn_limit: int,
    run_started: float,
) -> bool:
    if turn_index < turn_budget_limit:
        return False
    if reaction_turns_used >= reaction_turn_limit:
        return False
    if not _has_terminal_failure_result(tool_results):
        return False
    remaining_wall = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining_wall is None:
        return True
    configured_minimum = lane_input.lane_config.get("terminal_failure_reaction_min_wall_seconds")
    try:
        minimum_wall = float(configured_minimum) if configured_minimum not in (None, "") else 30.0
    except (TypeError, ValueError):
        minimum_wall = 30.0
    return remaining_wall >= max(0.0, minimum_wall)


def _should_closeout_for_terminal_failure_reaction(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    turn_index: int,
    turn_budget_limit: int,
) -> bool:
    if turn_index < turn_budget_limit:
        return False
    return any(
        result.tool_name in {"run_command", "run_tests", "poll_command"} and result.status == "yielded"
        for result in tool_results
    )


def _has_terminal_failure_result(tool_results: tuple[ToolResultEnvelope, ...]) -> bool:
    return any(
        result.tool_name in {"run_command", "run_tests", "poll_command"}
        and result.status in {"failed", "interrupted"}
        and not _is_tool_contract_misuse_result(result)
        for result in tool_results
    )


def _should_extend_for_tool_contract_recovery(
    lane_input: ImplementLaneInput,
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    turn_index: int,
    turn_budget_limit: int,
    recovery_turns_used: int,
    recovery_turn_limit: int,
    run_started: float,
) -> bool:
    if turn_index < turn_budget_limit:
        return False
    if recovery_turns_used >= recovery_turn_limit:
        return False
    result = _latest_terminal_exec_result(tool_results)
    if result is None or not _is_tool_contract_misuse_result(result):
        return False
    if _has_real_terminal_failure_result(tool_results):
        return False
    if not bool(lane_input.lane_config.get("allow_shell")):
        return False
    if not _v2_tool_available(lane_input, "run_command"):
        return False
    remaining_wall = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining_wall is None:
        return True
    configured_minimum = lane_input.lane_config.get("terminal_failure_reaction_min_wall_seconds")
    try:
        minimum_wall = float(configured_minimum) if configured_minimum not in (None, "") else 30.0
    except (TypeError, ValueError):
        minimum_wall = 30.0
    return remaining_wall >= max(0.0, minimum_wall)


def _latest_tool_contract_misuse_result(tool_results: tuple[ToolResultEnvelope, ...]) -> ToolResultEnvelope | None:
    result = _latest_terminal_exec_result(tool_results)
    if result is not None and _is_tool_contract_misuse_result(result):
        return result
    return None


def _has_real_terminal_failure_result(tool_results: tuple[ToolResultEnvelope, ...]) -> bool:
    return any(
        result.tool_name in {"run_command", "run_tests", "poll_command"}
        and result.status in {"failed", "interrupted"}
        and not _is_tool_contract_misuse_result(result)
        for result in tool_results
    )


def _latest_terminal_exec_result(tool_results: tuple[ToolResultEnvelope, ...]) -> ToolResultEnvelope | None:
    for result in reversed(tool_results):
        if result.tool_name in {"run_command", "run_tests", "poll_command"} and result.status in {
            "completed",
            "failed",
            "interrupted",
        }:
            return result
    return None


def _is_tool_contract_misuse_result(result: ToolResultEnvelope) -> bool:
    if result.tool_name != "run_tests" or result.status not in {"failed", "interrupted"}:
        return False
    for item in result.content:
        if not isinstance(item, dict):
            continue
        if (
            item.get("failure_class") == "tool_contract_misuse"
            and item.get("failure_subclass") == "run_tests_shell_surface"
            and item.get("recoverable_tool_contract_misuse") is True
            and item.get("tool_contract_recovery_eligible") is True
            and item.get("terminal_failure_reaction_eligible") is False
            and item.get("preserved_command")
            and item.get("suggested_tool") == "run_command"
            and item.get("suggested_use_shell") is True
        ):
            return True
    return False


def _tool_contract_recovery_instruction(result: ToolResultEnvelope | None) -> str:
    payload = next((item for item in (result.content if result is not None else ()) if isinstance(item, dict)), {})
    command = _clip_recovery_command(payload.get("preserved_command"))
    if not command:
        return ""
    cwd = str(payload.get("cwd") or ".")
    return (
        "Tool-contract recovery turn: the last action failed only because run_tests is argv-only. "
        "Re-run the exact preserved command with run_command/use_shell=true from the same cwd and keep the same "
        "execution_contract. Do not broaden source investigation or invent a new surrogate. "
        "If it cannot be run safely, finish blocked with the exact blocker.\n"
        f"cwd: {cwd}\n"
        f"preserved_command: {command}\n"
    )


def _clip_recovery_command(command: object, *, limit: int = 1000) -> str:
    text = str(command or "")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 40]}...<truncated {len(text) - (limit - 40)} chars>"


def _projected_command_closeout_status(payload: dict[str, object]) -> str:
    status = str(payload.get("status") or "")
    if status == "completed" or payload.get("exit_code") == 0:
        return "completed"
    if status == "killed":
        return "interrupted"
    if status in {"failed", "timed_out", "orphaned"} or payload.get("exit_code") is not None or payload.get("timed_out"):
        return "failed"
    return "interrupted"


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
    if not _v2_tool_available(lane_input, call.tool_name):
        return build_invalid_tool_result(
            call,
            reason=f"{call.tool_name} is not available in implement_v2 {str(lane_input.lane_config.get('mode') or 'full')} mode",
        )
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


def _v2_tool_available(lane_input: ImplementLaneInput, tool_name: object) -> bool:
    mode = lane_input.lane_config.get("mode") or "full"
    return str(tool_name or "") in {spec.name for spec in list_v2_tool_specs_for_mode(mode)}


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


def _repair_live_json_provider_call_ids_for_replay(
    tool_calls: tuple[ToolCallEnvelope, ...],
    *,
    seen_provider_call_ids: set[str] | None = None,
) -> tuple[tuple[ToolCallEnvelope, ...], tuple[str, ...]]:
    """Keep invalid provider-id reuse replayable by assigning internal ids.

    Provider call ids are model-authored. If the model reuses one, the tool call
    must still be rejected before side effects, but the proof manifest should
    remain pairable so replay/dogfood can classify the real failure that came
    next.
    """

    used_ids = set(seen_provider_call_ids or ())
    current_ids: set[str] = set()
    repaired: list[ToolCallEnvelope] = []
    errors: list[str] = []

    for call in tool_calls:
        provider_call_id = str(call.provider_call_id or "")
        repair_reason = ""
        if not provider_call_id:
            repair_reason = f"tool_call_missing_provider_call_id:{call.mew_tool_call_id}"
            provider_call_id = "missing-provider-call-id"
        elif provider_call_id in current_ids:
            repair_reason = f"duplicate_provider_call_id:{provider_call_id}"
        elif provider_call_id in used_ids:
            repair_reason = f"duplicate_provider_call_id_across_turns:{provider_call_id}"

        if repair_reason:
            errors.append(repair_reason)
            provider_call_id = _unique_repaired_provider_call_id(provider_call_id, call=call, used_ids=used_ids | current_ids)
            call = replace(call, provider_call_id=provider_call_id)

        repaired.append(call)
        current_ids.add(str(call.provider_call_id or ""))
        used_ids.add(str(call.provider_call_id or ""))

    return tuple(repaired), tuple(errors)


def _unique_repaired_provider_call_id(
    provider_call_id: str,
    *,
    call: ToolCallEnvelope,
    used_ids: set[str],
) -> str:
    base = _safe_id_part(provider_call_id, "provider-call")
    candidate = f"{base}-turn{int(call.turn_index or 0)}-seq{int(call.sequence_index or 0)}"
    if candidate not in used_ids:
        return candidate
    suffix = 2
    while f"{candidate}-{suffix}" in used_ids:
        suffix += 1
    return f"{candidate}-{suffix}"


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


def _lane_input_with_hard_runtime_frontier(
    lane_input: ImplementLaneInput,
    frontier_state: dict[str, object] | None,
) -> ImplementLaneInput:
    if not frontier_state:
        return lane_input
    persisted_lane_state = dict(lane_input.persisted_lane_state)
    persisted_lane_state["lane_hard_runtime_frontier"] = dict(frontier_state)
    return replace(lane_input, persisted_lane_state=persisted_lane_state)


def _initial_hard_runtime_frontier_state(lane_input: ImplementLaneInput) -> dict[str, object]:
    value = lane_input.persisted_lane_state.get("lane_hard_runtime_frontier")
    return _compact_hard_runtime_frontier_state(value) if isinstance(value, dict) else {}


def _merge_hard_runtime_frontier_state(
    *,
    existing: dict[str, object],
    update: object,
    tool_results: tuple[ToolResultEnvelope, ...],
    artifact_namespace: str,
) -> dict[str, object]:
    update_state = _compact_hard_runtime_frontier_state(update) if isinstance(update, dict) else {}
    merged = _compact_hard_runtime_frontier_state(existing)
    for key in (
        "status",
        "objective",
        "source_roles",
        "harness_runtime_source",
        "build_target",
        "final_artifact",
        "prohibited_surrogates",
        "next_verifier_shaped_command",
    ):
        if key in update_state:
            merged[key] = update_state[key]

    registry = _frontier_evidence_registry(tool_results, artifact_namespace=artifact_namespace)
    for key in ("source_roles", "harness_runtime_source"):
        merged[key] = _resolve_frontier_entry_list(merged.get(key), registry)
    for key in ("build_target", "final_artifact", "next_verifier_shaped_command"):
        if isinstance(merged.get(key), dict):
            merged[key] = _resolve_frontier_mapping_refs(merged[key], registry)
    for key, value in _frontier_state_from_execution_contracts(tool_results, registry).items():
        merged[key] = value

    contract_verifier = _latest_tool_contract_verifier_command(tool_results)
    if contract_verifier:
        merged["next_verifier_shaped_command"] = _resolve_frontier_mapping_refs(contract_verifier, registry)

    runtime_failure = _latest_runtime_frontier_failure(tool_results)
    if runtime_failure is not None:
        failure_key, failure_value = runtime_failure
        merged[failure_key] = failure_value

    merged["schema_version"] = _HARD_RUNTIME_FRONTIER_SCHEMA_VERSION
    status = str(merged.get("status") or "active").strip().lower()
    merged["status"] = status if status in {"active", "blocked", "resolved"} else "active"
    return _drop_empty_frontier_values(merged)


def _compact_hard_runtime_frontier_state(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, object] = {}
    for key in (
        "schema_version",
        "status",
        "objective",
        "source_roles",
        "harness_runtime_source",
        "build_target",
        "final_artifact",
        "prohibited_surrogates",
        "latest_build_failure",
        "latest_runtime_failure",
        "runtime_artifact_contract_mismatch",
        "next_verifier_shaped_command",
    ):
        if key in value:
            compact[key] = _frontier_compact_value(value[key], key=key)
    return _drop_empty_frontier_values(compact)


def _frontier_compact_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): _frontier_compact_value(item, key=str(key))
        for key, item in value.items()
        if item not in (None, "", [], {})
    }


def _frontier_compact_value(value: object, *, key: str = "", depth: int = 0) -> object:
    if depth > 3:
        return _frontier_clip_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): _frontier_compact_value(item, key=str(item_key), depth=depth + 1)
            for item_key, item in value.items()
            if item not in (None, "", [], {})
        }
    if isinstance(value, (list, tuple)):
        return [
            _frontier_compact_value(item, key=key, depth=depth + 1)
            for item in list(value)[:_FRONTIER_LIST_LIMIT]
            if item not in (None, "", [], {})
        ]
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    limit = _FRONTIER_COMMAND_TEXT_LIMIT if key in {"command", "preserved_command"} else _FRONTIER_TEXT_LIMIT
    return _frontier_clip_text(value, limit=limit)


def _frontier_clip_text(value: object, *, limit: int = _FRONTIER_TEXT_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 35)]}...<truncated {len(text) - max(0, limit - 35)} chars>"


def _drop_empty_frontier_values(value: dict[str, object]) -> dict[str, object]:
    return {str(key): item for key, item in value.items() if item not in (None, "", [], {})}


def _frontier_evidence_registry(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    artifact_namespace: str,
) -> dict[str, object]:
    output_refs: set[str] = set()
    command_run_ids: set[str] = set()
    for result in tool_results:
        for item in result.content:
            if not isinstance(item, dict):
                continue
            if item.get("command_run_id"):
                command_run_ids.add(str(item.get("command_run_id")))
            if item.get("output_ref"):
                output_refs.add(str(item.get("output_ref")))
    return {
        "tool_call_ids": set(range(1, len(tool_results) + 1)),
        "provider_call_ids": {result.provider_call_id for result in tool_results if result.provider_call_id},
        "command_run_ids": command_run_ids,
        "output_refs": output_refs,
        "content_refs": {ref for result in tool_results for ref in result.content_refs},
        "evidence_refs": {ref for result in tool_results for ref in result.evidence_refs},
        "artifact_namespace": artifact_namespace,
    }


def _resolve_frontier_entry_list(value: object, registry: dict[str, object]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    entries = []
    for item in value[:_FRONTIER_LIST_LIMIT]:
        if not isinstance(item, dict):
            continue
        entry = _resolve_frontier_mapping_refs(item, registry)
        state = str(entry.get("state") or "hypothesis").strip().lower()
        entry["state"] = state if state in {"hypothesis", "grounded"} else "hypothesis"
        if not entry.get("evidence_refs"):
            entry["state"] = "hypothesis"
        entries.append(entry)
    return entries


def _resolve_frontier_mapping_refs(value: object, registry: dict[str, object]) -> dict[str, object]:
    mapping = _frontier_compact_mapping(value)
    if "evidence_refs" in mapping:
        mapping["evidence_refs"] = _resolve_frontier_refs(mapping.get("evidence_refs"), registry)
    return mapping


def _resolve_frontier_refs(value: object, registry: dict[str, object]) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in value[: _FRONTIER_LIST_LIMIT * 2]:
        normalized = _normalize_frontier_ref(item, registry)
        if not normalized:
            continue
        key = json.dumps(normalized, ensure_ascii=True, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        refs.append(normalized)
        if len(refs) >= _FRONTIER_LIST_LIMIT:
            break
    return refs


def _normalize_frontier_ref(item: object, registry: dict[str, object]) -> dict[str, object] | None:
    if isinstance(item, dict):
        kind = str(item.get("kind") or "").strip()
        if kind == "tool_call":
            try:
                tool_id = int(item.get("id"))
            except (TypeError, ValueError):
                return None
            return {"kind": "tool_call", "id": tool_id} if tool_id in registry["tool_call_ids"] else None
        if kind == "provider_call":
            provider_id = str(item.get("id") or "").strip()
            return {"kind": "provider_call", "id": provider_id} if provider_id in registry["provider_call_ids"] else None
        if kind == "command_run":
            command_run_id = str(item.get("id") or "").strip()
            return {"kind": "command_run", "id": command_run_id} if command_run_id in registry["command_run_ids"] else None
        if kind == "command_output":
            output_ref = str(item.get("ref") or "").strip()
            return {"kind": "command_output", "ref": output_ref} if output_ref in registry["output_refs"] else None
        if kind == "content_ref":
            content_ref = str(item.get("ref") or "").strip()
            return {"kind": "content_ref", "ref": content_ref} if content_ref in registry["content_refs"] else None
        if kind == "evidence_ref":
            evidence_ref = str(item.get("ref") or "").strip()
            return {"kind": "evidence_ref", "ref": evidence_ref} if evidence_ref in registry["evidence_refs"] else None
        if kind == "proof_artifact":
            path = str(item.get("path") or "").strip()
            namespace = str(registry.get("artifact_namespace") or "")
            if _proof_artifact_ref_resolves(path, namespace=namespace):
                return {"kind": "proof_artifact", "path": path}
            return None
        return None
    if isinstance(item, str):
        ref = item.strip()
        if ref in registry["content_refs"]:
            return {"kind": "content_ref", "ref": ref}
        if ref in registry["evidence_refs"]:
            return {"kind": "evidence_ref", "ref": ref}
        if ref in registry["output_refs"]:
            return {"kind": "command_output", "ref": ref}
    return None


def _proof_artifact_ref_resolves(path: str, *, namespace: str) -> bool:
    if not path or not namespace:
        return False
    normalized_text = path.replace("\\", "/")
    while normalized_text.startswith("./"):
        normalized_text = normalized_text[2:]
    normalized = PurePosixPath(normalized_text)
    namespace_path = PurePosixPath(namespace)
    if normalized.is_absolute() or ".." in normalized.parts or ".." in namespace_path.parts:
        return False
    namespace_parts = namespace_path.parts
    return (
        len(normalized.parts) > len(namespace_parts)
        and normalized.parts[: len(namespace_parts)] == namespace_parts
    )


def _frontier_state_from_execution_contracts(
    tool_results: tuple[ToolResultEnvelope, ...],
    registry: dict[str, object],
) -> dict[str, object]:
    derived: dict[str, object] = {}
    for result in reversed(tool_results):
        if result.tool_name not in {"run_command", "run_tests", "poll_command"}:
            continue
        payload = next((item for item in result.content if isinstance(item, dict)), {})
        contract = payload.get("execution_contract") if isinstance(payload.get("execution_contract"), dict) else {}
        if not contract:
            continue
        refs = _frontier_result_refs(result, registry)
        expected_artifact = _frontier_expected_artifact_from_contract(contract)
        if expected_artifact and "final_artifact" not in derived:
            final_artifact = _resolve_frontier_mapping_refs(expected_artifact, registry)
            if refs:
                final_artifact["evidence_refs"] = refs
            derived["final_artifact"] = final_artifact
        if _execution_contract_is_build_like(contract, payload) and "build_target" not in derived:
            build_target = _frontier_build_target_from_contract(contract, payload, expected_artifact)
            if refs:
                build_target["evidence_refs"] = refs
            derived["build_target"] = _resolve_frontier_mapping_refs(build_target, registry)
    return derived


def _frontier_result_refs(result: ToolResultEnvelope, registry: dict[str, object]) -> list[dict[str, object]]:
    return _resolve_frontier_refs([*result.evidence_refs, *result.content_refs], registry)


def _frontier_expected_artifact_from_contract(contract: dict[str, object]) -> dict[str, object]:
    raw_artifact = (
        contract.get("expected_artifact")
        or contract.get("final_artifact")
        or _first_contract_list_item(contract.get("expected_artifacts"))
        or _first_contract_list_item(contract.get("artifacts"))
    )
    if isinstance(raw_artifact, dict):
        path = (
            raw_artifact.get("path")
            or raw_artifact.get("artifact_path")
            or raw_artifact.get("target_path")
            or raw_artifact.get("file")
        )
        artifact = {
            "path": _frontier_clip_text(path, limit=400),
            "kind": _frontier_clip_text(raw_artifact.get("kind") or raw_artifact.get("type"), limit=120),
            "freshness": _frontier_clip_text(
                raw_artifact.get("freshness") or "must be created by final verifier-shaped command"
            ),
        }
    else:
        artifact = {
            "path": _frontier_clip_text(raw_artifact, limit=400),
            "freshness": "must be created by final verifier-shaped command",
        }
    return _drop_empty_frontier_values(artifact)


def _first_contract_list_item(value: object) -> object:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _execution_contract_is_build_like(contract: dict[str, object], payload: dict[str, object]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            contract.get("purpose"),
            contract.get("stage"),
            contract.get("proof_role"),
            contract.get("target"),
            contract.get("build_target"),
            payload.get("command"),
        )
    ).lower()
    return any(marker in text for marker in ("build", "compile", "link", "toolchain", "make "))


def _execution_contract_is_verifier_like(contract: dict[str, object]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            contract.get("purpose"),
            contract.get("stage"),
            contract.get("proof_role"),
            contract.get("acceptance_kind"),
        )
    ).lower()
    return any(marker in text for marker in ("verify", "verification", "proof", "acceptance", "test"))


def _frontier_build_target_from_contract(
    contract: dict[str, object],
    payload: dict[str, object],
    expected_artifact: dict[str, object],
) -> dict[str, object]:
    target = (
        contract.get("target")
        or contract.get("build_target")
        or contract.get("declared_target")
        or contract.get("declared_target_ref")
    )
    artifact_path = expected_artifact.get("path") if isinstance(expected_artifact, dict) else ""
    return _drop_empty_frontier_values(
        {
            "cwd": _frontier_clip_text(payload.get("cwd") or "."),
            "target": _frontier_clip_text(target, limit=240),
            "command": _frontier_clip_text(payload.get("command"), limit=_FRONTIER_COMMAND_TEXT_LIMIT),
            "artifact_path": _frontier_clip_text(artifact_path, limit=400),
        }
    )


def _latest_runtime_frontier_failure(
    tool_results: tuple[ToolResultEnvelope, ...],
) -> tuple[str, dict[str, object]] | None:
    for result in reversed(tool_results):
        if result.tool_name not in {"run_command", "run_tests", "poll_command"}:
            continue
        if result.status not in {"failed", "interrupted"} or _is_tool_contract_misuse_result(result):
            continue
        payload = next((item for item in result.content if isinstance(item, dict)), {})
        if not payload:
            continue
        key = _frontier_failure_key_from_payload(payload)
        return key, _frontier_failure_payload(payload)
    return None


def _frontier_failure_key_from_payload(payload: dict[str, object]) -> str:
    contract = payload.get("execution_contract") if isinstance(payload.get("execution_contract"), dict) else {}
    text = " ".join(
        str(value or "")
        for value in (
            contract.get("purpose"),
            contract.get("stage"),
            contract.get("proof_role"),
            payload.get("command"),
        )
    ).lower()
    evidence_text = _frontier_failure_evidence_text(payload)
    if _frontier_runtime_artifact_contract_mismatch(evidence_text):
        return "runtime_artifact_contract_mismatch"
    if _frontier_runtime_execution_timeout(evidence_text):
        return "latest_runtime_failure"
    if _frontier_runtime_artifact_missing(evidence_text):
        return "latest_runtime_failure"
    if any(marker in text for marker in ("build", "compile", "link", "toolchain", "make ")):
        return "latest_build_failure"
    return "latest_runtime_failure"


def _frontier_failure_payload(payload: dict[str, object]) -> dict[str, object]:
    evidence_text = _frontier_failure_evidence_text(payload)
    failure = {
        "command_run_id": _frontier_clip_text(payload.get("command_run_id"), limit=160),
        "exit_code": payload.get("exit_code"),
        "stdout_tail": _frontier_clip_text(payload.get("stdout_tail") or payload.get("stdout")),
        "stderr_tail": _frontier_clip_text(payload.get("stderr_tail") or payload.get("stderr")),
        "failure_summary": _frontier_failure_summary(payload),
    }
    if _frontier_runtime_artifact_contract_mismatch(evidence_text):
        failure["failure_class"] = "runtime_artifact_contract_mismatch"
        failure["required_next_probe"] = (
            "Compare the generated artifact ABI/ISA/endianness/entrypoint with the runtime loader or "
            "emulator contract before rebuilding or finishing."
        )
    elif _frontier_runtime_execution_timeout(evidence_text):
        failure["failure_class"] = "runtime_execution_timeout"
        failure["required_next_probe"] = (
            "Inspect runtime progress, timeout point, and expected artifact production before another rebuild."
        )
    elif _frontier_runtime_artifact_missing(evidence_text):
        failure["failure_class"] = "runtime_artifact_missing"
        failure["required_next_probe"] = (
            "Inspect runtime progress, termination point, and expected output artifact production before another rebuild."
        )
    if payload.get("output_ref"):
        failure["output_ref"] = _frontier_clip_text(payload.get("output_ref"), limit=240)
    return _drop_empty_frontier_values(failure)


def _frontier_failure_evidence_text(payload: dict[str, object]) -> str:
    parts = []
    for key in (
        "reason",
        "failure_class",
        "failure_subclass",
        "stdout_tail",
        "stderr_tail",
        "stdout",
        "stderr",
    ):
        value = payload.get(key)
        if value not in (None, ""):
            parts.append(str(value))
    return "\n".join(parts).casefold()


def _frontier_runtime_artifact_contract_mismatch(evidence_text: str) -> bool:
    """Detect generic VM/emulator artifact-contract failures without task recipes."""

    text = str(evidence_text or "").casefold()
    runtime_marker = any(
        marker in text
        for marker in (
            "unknown opcode",
            "illegal instruction",
            "exec format error",
            "bad cpu type",
            "invalid instruction",
            "unhandled instruction",
        )
    )
    artifact_contract_marker = any(
        marker in text
        for marker in (
            "elf",
            "readelf",
            "objdump",
            "machine:",
            "entry point",
            "readuint32le",
            "readuint32be",
            "big endian",
            "little endian",
            "emulator",
            " vm.",
            " vm)",
        )
    )
    return runtime_marker and artifact_contract_marker


def _frontier_runtime_execution_timeout(evidence_text: str) -> bool:
    """Detect observed VM/emulator/runtime timeout evidence in compound commands."""

    text = str(evidence_text or "").casefold()
    return any(
        marker in text
        for marker in (
            "vm_rc=124",
            "vm rc=124",
            "vm exit 124",
            "runtime timed out",
            "emulator timed out",
            "execution timed out",
        )
    )


def _frontier_runtime_artifact_missing(evidence_text: str) -> bool:
    """Detect verifier-observed runtime execution that produced no required artifact."""

    text = str(evidence_text or "").casefold()
    runtime_marker = any(
        marker in text
        for marker in (
            "vm_rc=",
            "vm rc=",
            "vm exit ",
            "program terminated at pc=",
            "emulator",
            "executed instructions",
        )
    )
    missing_artifact_marker = any(
        marker in text
        for marker in (
            "no_frame",
            "no frame",
            "no output artifact",
            "missing output artifact",
            "artifact missing",
            "missing artifact",
            "did not create",
            "not created",
        )
    )
    return runtime_marker and missing_artifact_marker


def _frontier_failure_summary(payload: dict[str, object]) -> str:
    for key in ("stderr_tail", "stderr", "stdout_tail", "stdout"):
        text = str(payload.get(key) or "").strip()
        if text:
            return _frontier_clip_text(next((line.strip() for line in text.splitlines() if line.strip()), text))
    status = str(payload.get("status") or "failed")
    exit_code = payload.get("exit_code")
    return f"{status} exit_code={exit_code}"


def _latest_tool_contract_verifier_command(tool_results: tuple[ToolResultEnvelope, ...]) -> dict[str, object]:
    for result in reversed(tool_results):
        if result.tool_name not in {"run_command", "run_tests"}:
            continue
        payload = next((item for item in result.content if isinstance(item, dict)), {})
        if not payload:
            continue
        recovery = payload.get("tool_contract_recovery") if isinstance(payload.get("tool_contract_recovery"), dict) else {}
        if not recovery and not _is_tool_contract_misuse_result(result):
            continue
        command = str(payload.get("preserved_command") or payload.get("command") or "").strip()
        if not command:
            continue
        contract = payload.get("execution_contract") if isinstance(payload.get("execution_contract"), dict) else {}
        if contract and not _execution_contract_is_verifier_like(contract):
            continue
        verifier: dict[str, object] = {
            "tool": "run_command",
            "cwd": _frontier_clip_text(payload.get("cwd") or "."),
            "command": _frontier_clip_text(command, limit=_FRONTIER_COMMAND_TEXT_LIMIT),
            "use_shell": True,
        }
        if contract:
            verifier["execution_contract"] = _frontier_compact_mapping(contract)
        evidence_refs: list[object] = []
        if result.evidence_refs:
            evidence_refs.append(result.evidence_refs[0])
        if result.content_refs:
            evidence_refs.append(result.content_refs[0])
        if evidence_refs:
            verifier["evidence_refs"] = evidence_refs
        return verifier
    return {}


def _live_json_prompt(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    hard_runtime_frontier_state: dict[str, object] | None = None,
    turn_index: int,
    max_turns: int,
    base_max_turns: int | None = None,
    terminal_failure_reaction_turns_used: int = 0,
    terminal_failure_reaction_turn_limit: int = 0,
    tool_contract_recovery_turns_used: int = 0,
    tool_contract_recovery_turn_limit: int = 0,
    tool_contract_recovery_instruction: str = "",
    history: tuple[dict[str, object], ...],
) -> str:
    sections = render_prompt_sections(
        build_implement_v2_prompt_sections(_lane_input_with_hard_runtime_frontier(lane_input, hard_runtime_frontier_state))
    )
    response_contract = {
        "summary": "short natural-language summary of this turn",
        "frontier_state_update": {
            "status": "active | blocked | resolved",
            "objective": "short hard-runtime objective when relevant",
            "source_roles": [
                {
                    "path": "relative/source/path",
                    "role": "primary_source | runtime_harness | build_file | generated_artifact | test_harness | toolchain_probe",
                    "state": "hypothesis | grounded",
                    "evidence_refs": [{"kind": "provider_call", "id": "stable-provider-call-id"}],
                }
            ],
            "next_verifier_shaped_command": {
                "tool": "run_command",
                "cwd": ".",
                "command": "short command",
                "use_shell": True,
                "execution_contract": {"purpose": "verification", "stage": "verification"},
            },
        },
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
    recovery_instruction_section = ""
    if tool_contract_recovery_instruction:
        recovery_instruction_section = f"tool_contract_recovery_instruction:\n{tool_contract_recovery_instruction}"
    terminal_reaction_guidance = ""
    if terminal_failure_reaction_turns_used > 0 and not tool_contract_recovery_instruction:
        terminal_reaction_guidance = (
            "If this is a terminal-failure reaction turn, do not broaden the task: make the smallest "
            "repair/check that directly responds to the latest failed terminal result, or finish blocked "
            "with the exact blocker.\n"
        )
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
        f"{terminal_reaction_guidance}"
        f"lane_attempt_id: {lane_attempt_id}\n"
        f"turn: {turn_index}/{max_turns}\n"
        f"base_max_turns: {base_max_turns if base_max_turns is not None else max_turns}\n"
        f"terminal_failure_reaction_turns_used: {terminal_failure_reaction_turns_used}/"
        f"{terminal_failure_reaction_turn_limit}\n"
        f"tool_contract_recovery_turns_used: {tool_contract_recovery_turns_used}/"
        f"{tool_contract_recovery_turn_limit}\n"
        f"{recovery_instruction_section}"
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
    frontier_state_update = (
        dict(payload.get("frontier_state_update")) if isinstance(payload.get("frontier_state_update"), dict) else {}
    )
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
        provider_call_id = str(raw.get("provider_call_id") or raw.get("id") or "")
        calls.append({"provider_call_id": provider_call_id, "tool_name": name, "arguments": dict(arguments)})
    if finish:
        finish = dict(finish)
        outcome = _finish_outcome(finish)
        if not outcome:
            finish["outcome"] = "completed"
    return {
        "summary": summary,
        "frontier_state_update": frontier_state_update,
        "tool_calls": tuple(calls),
        "finish": finish,
    }


def _live_json_model_error(exc: BaseException) -> dict[str, object]:
    message = str(exc)
    lowered = message.casefold()
    if "failed to parse json plan" in lowered or "response did not contain json" in lowered:
        failure_class = "model_json_parse_error"
    elif "request timed out" in lowered or "timed out" in lowered or "timeout" in lowered:
        failure_class = "model_timeout"
    else:
        failure_class = "model_backend_error"
    return {
        "failure_class": failure_class,
        "error_type": exc.__class__.__name__,
        "message": message,
        "raw_excerpt": _extract_raw_excerpt_from_model_error(message),
    }


def _extract_raw_excerpt_from_model_error(message: str, limit: int = 500) -> str:
    marker = "raw="
    index = message.find(marker)
    if index == -1:
        return ""
    return message[index + len(marker) : index + len(marker) + limit]


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
    visible = result.provider_visible_content()
    if result.tool_name in _PROVIDER_HISTORY_TERMINAL_TOOL_NAMES:
        visible = _project_terminal_result_for_provider_history(visible)
    content = _compact_provider_visible_content_for_history(visible)
    return {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content": content,
    }


def _full_tool_result_for_history(result: ToolResultEnvelope) -> dict[str, object]:
    return {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content": result.provider_visible_content(),
    }


def _project_terminal_result_for_provider_history(content: dict[str, object]) -> dict[str, object]:
    """Keep terminal turn history small while preserving actionable evidence.

    Full stdout/stderr can be tens of thousands of characters and is already
    persisted through output_ref/content_refs. The next model turn only needs
    lifecycle metadata plus bounded tails; it can call read_command_output when
    it intentionally needs more.
    """

    projected = dict(content)
    projected_items = []
    for item in projected.get("content") if isinstance(projected.get("content"), list) else []:
        if not isinstance(item, dict):
            projected_items.append(item)
            continue
        projected_items.append(_project_terminal_payload_for_provider_history(item))
    if projected_items:
        projected["content"] = projected_items
        projected["history_projected"] = True
        projected["history_projection_note"] = (
            "terminal stdout/stderr body omitted from next-turn history; "
            "use command_run_id/output_ref/read_command_output for full output"
        )
    return projected


def _project_terminal_payload_for_provider_history(payload: dict[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {
        "provider_history_projection": "terminal_result_v0",
    }
    for key in (
        "tool_name",
        "command_run_id",
        "status",
        "exit_code",
        "timed_out",
        "timeout_seconds",
        "duration_seconds",
        "output_bytes",
        "output_truncated",
        "output_ref",
        "command_source",
        "kill_status",
    ):
        if key in payload:
            projected[key] = payload.get(key)
    for key in _PROVIDER_HISTORY_TERMINAL_DIAGNOSTIC_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value in (None, ""):
            continue
        projected_value, clipped = _compact_provider_history_value(value, key=key)
        projected[key] = projected_value
        if clipped:
            projected[f"{key}_history_truncated"] = True
    command = str(payload.get("command") or "")
    if command:
        projected["command_excerpt"] = _clip_provider_history_text(command, limit=900)[0]
    stdout = str(payload.get("stdout") or "")
    stderr = str(payload.get("stderr") or "")
    stdout_tail = str(payload.get("stdout_tail") or "")
    stderr_tail = str(payload.get("stderr_tail") or "")
    if stdout_tail or stdout:
        projected["stdout_tail"] = stdout_tail or _clip_provider_history_text(stdout, limit=900)[0]
    if stderr_tail or stderr:
        projected["stderr_tail"] = stderr_tail or _clip_provider_history_text(stderr, limit=900)[0]
    if stdout or stderr:
        projected["stdout_stderr_body_omitted"] = True
        projected["stdout_chars"] = len(stdout)
        projected["stderr_chars"] = len(stderr)
    return projected


def _compact_provider_visible_content_for_history(content: dict[str, object]) -> dict[str, object]:
    compacted = dict(content)
    clipped = False
    compacted_items = []
    for item in compacted.get("content") if isinstance(compacted.get("content"), list) else []:
        compacted_item, item_clipped = _compact_provider_history_value(item)
        compacted_items.append(compacted_item)
        clipped = clipped or item_clipped
    if compacted_items:
        compacted["content"] = compacted_items
    if clipped:
        compacted["history_compacted"] = True
        compacted["history_compaction_note"] = (
            "large provider-visible tool output was clipped for the next model turn; "
            "use content_refs/evidence_refs/read_command_output for full artifacts"
        )
    return compacted


def _compact_provider_history_value(value: object, *, key: str = "", depth: int = 0) -> tuple[object, bool]:
    if isinstance(value, str):
        limit = _PROVIDER_HISTORY_TEXT_LIMIT if key in _PROVIDER_HISTORY_CLIP_KEYS or not key else 4000
        return _clip_provider_history_text(value, limit=limit)
    if isinstance(value, dict):
        clipped = False
        output: dict[str, object] = {}
        for item_key, item_value in value.items():
            compacted, item_clipped = _compact_provider_history_value(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            output[str(item_key)] = compacted
            clipped = clipped or item_clipped
            if item_clipped and isinstance(item_value, str):
                output[f"{item_key}_history_chars"] = len(item_value)
                output[f"{item_key}_history_truncated"] = True
        return output, clipped
    if isinstance(value, list):
        clipped = len(value) > _PROVIDER_HISTORY_LIST_LIMIT
        compacted_list = []
        for item in value[:_PROVIDER_HISTORY_LIST_LIMIT]:
            compacted, item_clipped = _compact_provider_history_value(item, key=key, depth=depth + 1)
            compacted_list.append(compacted)
            clipped = clipped or item_clipped
        if len(value) > _PROVIDER_HISTORY_LIST_LIMIT:
            compacted_list.append(
                {
                    "history_list_truncated": True,
                    "omitted_items": len(value) - _PROVIDER_HISTORY_LIST_LIMIT,
                }
            )
        return compacted_list, clipped
    return value, False


def _clip_provider_history_text(text: str, *, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    head = text[:_PROVIDER_HISTORY_TEXT_HEAD]
    tail = text[-_PROVIDER_HISTORY_TEXT_TAIL:]
    omitted = len(text) - len(head) - len(tail)
    return (
        f"{head}\n"
        f"...[history clipped {omitted} chars; full content remains in artifact refs]...\n"
        f"{tail}",
        True,
    )


def _finish_outcome(finish_arguments: dict[str, object]) -> str:
    return str((finish_arguments or {}).get("outcome") or (finish_arguments or {}).get("status") or "").strip()


def _live_acceptance_done_gate(
    lane_input: ImplementLaneInput,
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    outcome = _finish_outcome(finish_arguments)
    if outcome not in _COMPLETED_FINISH_OUTCOMES:
        return {
            "decision": "allow_complete",
            "reason": "",
            "blockers": [],
            "invalid_evidence_refs": [],
            "continuation_prompt": "",
        }
    return acceptance_done_gate_decision(
        _live_task_description(lane_input),
        _finish_acceptance_action(finish_arguments, tool_results),
        session=_acceptance_session_from_tool_results(tool_results),
    )


def _live_task_description(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    chunks = [
        str(contract.get("title") or "").strip(),
        str(contract.get("description") or "").strip(),
        str(contract.get("guidance") or "").strip(),
        str(contract.get("verify_command") or "").strip(),
    ]
    return "\n".join(chunk for chunk in chunks if chunk)


def _finish_acceptance_action(
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    action = dict(finish_arguments or {})
    action["task_done"] = _finish_outcome(action) in _COMPLETED_FINISH_OUTCOMES
    checks = action.get("acceptance_checks")
    if isinstance(checks, list):
        action["acceptance_checks"] = [
            _with_finish_evidence_refs(check, tool_results) if isinstance(check, dict) else check for check in checks
        ]
        return action
    action["acceptance_checks"] = _synthetic_finish_acceptance_checks(action, tool_results)
    return action


def _synthetic_finish_acceptance_checks(
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    evidence_items = finish_arguments.get("acceptance_evidence")
    if isinstance(evidence_items, str):
        items = [evidence_items]
    elif isinstance(evidence_items, (list, tuple)):
        items = list(evidence_items)
    else:
        items = []
    checks: list[dict[str, object]] = []
    for item in items[:8]:
        evidence = str(item or "").strip()
        if not evidence:
            continue
        check: dict[str, object] = {
            "constraint": _finish_constraint_from_evidence(evidence),
            "status": "verified",
            "evidence": evidence,
        }
        refs = _finish_evidence_refs(evidence, tool_results)
        if refs:
            check["evidence_refs"] = refs
        checks.append(check)
    return checks


def _with_finish_evidence_refs(
    check: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    enriched = dict(check)
    if enriched.get("evidence_refs") or enriched.get("evidence_ref"):
        return enriched
    evidence = "\n".join(str(enriched.get(key) or "") for key in ("constraint", "evidence", "proof"))
    refs = _finish_evidence_refs(evidence, tool_results)
    if refs:
        enriched["evidence_refs"] = refs
    return enriched


def _finish_constraint_from_evidence(evidence: str) -> str:
    lowered = evidence.casefold()
    if any(marker in lowered for marker in ("frame", "screenshot", "image", "render")):
        return "runtime visual artifact is correct"
    if any(marker in lowered for marker in ("stdout", "stderr", "exit_code", "command")):
        return "command behavior is verified"
    return "finish acceptance evidence"


def _finish_evidence_refs(
    evidence: str,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    provider_to_tool_id = {
        result.provider_call_id: index
        for index, result in enumerate(tool_results, start=1)
        if str(result.provider_call_id or "").strip()
    }
    for provider_call_id, tool_id in provider_to_tool_id.items():
        if _provider_call_id_mentioned(evidence, provider_call_id):
            ref = {"kind": "tool_call", "id": tool_id}
            if ref not in refs:
                refs.append(ref)
    for match in _EVIDENCE_PROVIDER_CALL_RE.finditer(evidence):
        provider_call_id = match.group(0)
        tool_id = provider_to_tool_id.get(provider_call_id)
        if tool_id is not None:
            ref = {"kind": "tool_call", "id": tool_id}
            if ref not in refs:
                refs.append(ref)
    for index, result in enumerate(tool_results, start=1):
        if any(str(ref or "") and str(ref or "") in evidence for ref in result.evidence_refs):
            ref = {"kind": "tool_call", "id": index}
            if ref not in refs:
                refs.append(ref)
    return refs


def _provider_call_id_mentioned(evidence: str, provider_call_id: object) -> bool:
    provider_id = str(provider_call_id or "").strip()
    if not provider_id:
        return False
    if len(provider_id) < 4:
        return False
    if provider_id.isalpha() or provider_id.isdigit():
        return False
    if not any(char.isalpha() for char in provider_id):
        return False
    if not any(char in "-_.:" for char in provider_id):
        return False
    for match in _PROVIDER_ID_TOKEN_RE.finditer(evidence):
        token = match.group(0)
        if token == provider_id:
            return True
        if token.rstrip(".,:;") == provider_id:
            return True
    return False


def _acceptance_session_from_tool_results(tool_results: tuple[ToolResultEnvelope, ...]) -> dict[str, object]:
    return {
        "tool_calls": [
            _acceptance_tool_call_from_result(index, result)
            for index, result in enumerate(tool_results, start=1)
        ]
    }


def _acceptance_tool_call_from_result(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    content_items = [item for item in result.content if isinstance(item, dict)]
    primary = dict(content_items[0]) if content_items else {}
    command = str(primary.get("command") or "").strip()
    argv = primary.get("argv")
    if not command and isinstance(argv, list):
        command = " ".join(str(item) for item in argv)
    text = _tool_result_content_text(result)
    result_payload: dict[str, object] = {
        "text": text,
        "stdout": str(primary.get("stdout") or ""),
        "stderr": str(primary.get("stderr") or ""),
        "summary": text[:500],
        "output": text,
        "command": command,
    }
    if "exit_code" in primary:
        result_payload["exit_code"] = primary.get("exit_code")
    elif result.tool_name in EXEC_TOOL_NAMES:
        result_payload["exit_code"] = 0 if result.status == "completed" else 1
    if "timed_out" in primary:
        result_payload["timed_out"] = bool(primary.get("timed_out"))
    elif result.tool_name in EXEC_TOOL_NAMES:
        result_payload["timed_out"] = False
    parameters: dict[str, object] = {}
    if command:
        parameters["command"] = command
    if primary.get("cwd"):
        parameters["cwd"] = primary.get("cwd")
    return {
        "id": index,
        "tool": result.tool_name,
        "status": result.status,
        "parameters": parameters,
        "result": result_payload,
        "summary": text[:500],
    }


def _tool_result_content_text(result: ToolResultEnvelope) -> str:
    chunks: list[str] = []
    for item in result.content:
        if isinstance(item, dict):
            for key in ("command", "stdout", "stderr", "text", "summary", "output", "reason"):
                value = item.get(key)
                if value:
                    chunks.append(str(value))
            argv = item.get("argv")
            if isinstance(argv, list):
                chunks.append(" ".join(str(part) for part in argv))
        elif item:
            chunks.append(str(item))
    return "\n".join(chunks)


def _finish_gate_transcript_event(
    *,
    lane_attempt_id: str,
    turn_id: str,
    decision: dict[str, object],
) -> ImplementLaneTranscriptEvent:
    return ImplementLaneTranscriptEvent(
        kind="verifier",
        lane=IMPLEMENT_V2_LANE,
        turn_id=turn_id,
        event_id=f"{turn_id}:finish-gate",
        payload={
            "lane_attempt_id": lane_attempt_id,
            "type": "deterministic_finish_gate",
            "decision": dict(decision),
        },
    )


def _finish_gate_continuation_text(decision: dict[str, object]) -> str:
    return str(
        decision.get("continuation_prompt")
        or decision.get("reason")
        or "finish blocked by deterministic done gate"
    ).strip()


def _finish_gate_history(
    *,
    turn_index: int,
    decision: dict[str, object],
    continuation_prompt: str,
) -> dict[str, object]:
    return {
        "turn": turn_index,
        "summary": "finish gate blocked completion; continue the same task",
        "tool_calls": [],
        "tool_results": [
            {
                "tool_name": "finish_gate",
                "status": "failed",
                "is_error": True,
                "content": {
                    "mew_status": "failed",
                    "finish_gate": decision,
                    "continuation_prompt": continuation_prompt,
                },
            }
        ],
    }


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
