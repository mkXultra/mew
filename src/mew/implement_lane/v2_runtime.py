"""Implement_v2 runtime substrates and live JSON tool loop."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path, PurePosixPath
import re
import time
from dataclasses import dataclass, replace

from ..acceptance import (
    acceptance_done_gate_decision,
    implementation_contract_source_requirements,
    implementation_source_ref_matches_text,
    is_runtime_visual_artifact_task,
)
from ..errors import ModelBackendError
from ..work_lanes import IMPLEMENT_V2_LANE
from .execution_evidence import (
    build_oracle_bundle,
    evidence_events_from_tool_payload,
    normalize_execution_contract,
    recommend_finish_evidence_refs,
)
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
_PROVIDER_HISTORY_TOOL_ARG_TEXT_LIMIT = 1200
_PROVIDER_HISTORY_SOURCE_MUTATION_TEXT_LIMIT = 900
_PROVIDER_HISTORY_LIST_LIMIT = 24
_PROVIDER_HISTORY_SOURCE_MUTATION_KEYS = frozenset(
    {
        "content",
        "old",
        "new",
        "old_string",
        "new_string",
        "old_text",
        "new_text",
        "patch",
        "input",
    }
)
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
_HARD_RUNTIME_PROGRESS_CONTINUATION_DEFAULT_LIMIT = 4
_IMPLEMENT_V2_MIN_MODEL_TURN_TIMEOUT_SECONDS = 0.001
_IMPLEMENT_V2_TRANSIENT_MODEL_RETRY_DELAYS = (0.0,)
_IMPLEMENT_V2_TRANSIENT_MODEL_ERROR_MARKERS = (
    "incompleteread",
    "connection reset",
    "connection aborted",
    "connection broken",
    "connection",
    "temporarily",
    "temporary",
    "rate limit",
    "429",
    "500",
    "502",
    "503",
    "504",
    "529",
    "overload",
)


@dataclass(frozen=True)
class ModelTurnInput:
    """In-memory-only model turn call boundary for implement_v2.

    Raw prompts and payloads may pass through this object but must not be
    serialized into proof manifests, lane state, or observations by default.
    """

    lane: str
    lane_attempt_id: str
    turn_id: str
    turn_index: int
    transport: str
    model_backend: str
    model: str
    rendered_prompt: str
    current_projection_bytes: bytes
    prompt_descriptor: dict[str, object]
    projection_descriptor: dict[str, object]
    timeout_seconds: float
    log_prefix: str


@dataclass(frozen=True)
class ModelTurnOutput:
    """In-memory-only model turn result boundary for implement_v2."""

    payload: object
    normalized_payload: dict[str, object]
    elapsed_seconds: float
    prompt_chars: int
    response_shape: dict[str, object]
    model_error: dict[str, object]
    observation: dict[str, object]


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
        from ..work_loop import call_model_json_with_retries as model_json_callable

    mode = str(lane_input.lane_config.get("mode") or "full").strip() or "full"
    lane_attempt_id = _lane_attempt_id(lane_input, mode=mode)
    artifact_namespace = lane_artifact_namespace(
        work_session_id=lane_input.work_session_id,
        task_id=lane_input.task_id,
        lane=IMPLEMENT_V2_LANE,
    )
    hard_runtime_frontier_state = _initial_hard_runtime_frontier_state(lane_input)
    hard_runtime_frontier_enabled = bool(hard_runtime_frontier_state) or is_hard_runtime_artifact_task(
        lane_input.task_contract
    )
    adapter = JsonModelProviderAdapter()
    exec_runtime = ImplementV2ManagedExecRuntime(
        workspace=lane_input.workspace,
        allowed_roots=_allowed_read_roots(lane_input),
        allow_shell=bool(lane_input.lane_config.get("allow_shell")),
        run_command_available=_v2_tool_available(lane_input, "run_command"),
        route_run_tests_shell_surface=_route_run_tests_shell_surface(lane_input),
        task_contract=lane_input.task_contract,
        frontier_state=hard_runtime_frontier_state,
    )
    transcript: list[ImplementLaneTranscriptEvent] = []
    tool_calls: list[object] = []
    tool_results: list[ToolResultEnvelope] = []
    history: list[dict[str, object]] = []
    prompt_history: list[dict[str, object]] = []
    model_turn_observations: list[dict[str, object]] = []
    finish_arguments: dict[str, object] = {}
    seen_provider_call_ids: set[str] = set()
    model_elapsed_seconds = 0.0
    prompt_chars_total = 0
    model_turns = 0
    model_error: dict[str, object] = {}
    cleanup_payloads: tuple[dict[str, object], ...] = ()
    closeout_payloads: tuple[dict[str, object], ...] = ()
    auto_poll_payloads: tuple[dict[str, object], ...] = ()
    finish_gate_decision: dict[str, object] = {}
    finish_gate_block_count = 0
    wall_timeout: dict[str, object] = {}
    run_started = time.monotonic()
    base_max_turns = max(1, int(max_turns))
    turn_budget_limit = base_max_turns
    terminal_failure_reaction_turn_limit = _terminal_failure_reaction_turn_limit(lane_input, base_max_turns)
    terminal_failure_reaction_turns_used = 0
    hard_runtime_progress_continuation_turn_limit = _hard_runtime_progress_continuation_turn_limit(
        lane_input,
        base_max_turns=base_max_turns,
    )
    hard_runtime_progress_continuation_turns_used = 0
    hard_runtime_progress_signatures_seen: set[str] = set()
    tool_contract_recovery_turn_limit = _tool_contract_recovery_turn_limit(lane_input)
    tool_contract_recovery_turns_used = 0
    tool_contract_recovery_instruction = ""
    turn_index = 0

    def extend_for_terminal_failure_reaction_if_available(
        tool_result_slice: tuple[ToolResultEnvelope, ...],
        *,
        reason: str,
    ) -> bool:
        nonlocal terminal_failure_reaction_turns_used, turn_budget_limit
        nonlocal terminal_failure_reaction_turn_limit, hard_runtime_progress_continuation_turns_used
        progress_signature = _hard_runtime_frontier_progress_signature(hard_runtime_frontier_state)
        if _should_extend_for_terminal_failure_reaction(
            lane_input,
            tool_result_slice,
            turn_index=turn_index,
            turn_budget_limit=turn_budget_limit,
            reaction_turns_used=terminal_failure_reaction_turns_used,
            reaction_turn_limit=terminal_failure_reaction_turn_limit,
            run_started=run_started,
        ):
            if progress_signature:
                hard_runtime_progress_signatures_seen.add(progress_signature)
        else:
            progress_signature = _hard_runtime_progress_continuation_signature(
                lane_input,
                tool_result_slice,
                hard_runtime_frontier_state,
                seen_signatures=hard_runtime_progress_signatures_seen,
                reaction_turns_used=terminal_failure_reaction_turns_used,
                reaction_turn_limit=terminal_failure_reaction_turn_limit,
                progress_turns_used=hard_runtime_progress_continuation_turns_used,
                progress_turn_limit=hard_runtime_progress_continuation_turn_limit,
                run_started=run_started,
            )
            if not progress_signature:
                return False
            hard_runtime_progress_continuation_turns_used += 1
            terminal_failure_reaction_turn_limit += 1
            hard_runtime_progress_signatures_seen.add(progress_signature)
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

    def finish_gate_terminal_failure_reaction_summary(
        current_results: tuple[ToolResultEnvelope, ...],
    ) -> str:
        if extend_for_terminal_failure_reaction_if_available(
            current_results,
            reason="finish_gate_terminal_failure",
        ):
            return "terminal failure reaction turn reserved after finish gate blocked completion"
        if _has_terminal_failure_result(current_results):
            return ""
        if extend_for_terminal_failure_reaction_if_available(
            tuple(tool_results),
            reason="finish_gate_unresolved_prior_terminal_failure",
        ):
            return (
                "terminal failure reaction turn reserved after finish gate blocked completion "
                "with an unresolved prior terminal failure"
            )
        return ""

    def append_finish_gate_history(
        *,
        decision: dict[str, object],
        continuation_prompt: str,
    ) -> None:
        history.append(
            _finish_gate_history(
                turn_index=turn_index,
                decision=decision,
                continuation_prompt=continuation_prompt,
            )
        )
        prompt_history.append(dict(history[-1]))

    try:
        while turn_index < turn_budget_limit:
            model_timeout_seconds = _model_turn_timeout_seconds(
                lane_input,
                run_started=run_started,
                requested_timeout=timeout,
            )
            if model_timeout_seconds <= 0:
                wall_timeout = _implement_v2_wall_timeout(
                    lane_input,
                    run_started=run_started,
                    reason="not enough wall-clock budget remains for another model turn",
                    next_turn=turn_index + 1,
                    requested_model_timeout=timeout,
                )
                finish_arguments = {
                    "outcome": "blocked",
                    "summary": "implement_v2 wall-clock budget exhausted before finish",
                }
                break
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
            model_turn_input = ModelTurnInput(
                lane=IMPLEMENT_V2_LANE,
                lane_attempt_id=lane_attempt_id,
                turn_id=turn_id,
                turn_index=turn_index,
                transport=adapter.provider,
                model_backend=lane_input.model_backend,
                model=lane_input.model,
                rendered_prompt=prompt,
                current_projection_bytes=_render_prompt_history_json(prompt_history).encode("utf-8"),
                prompt_descriptor=_prompt_descriptor(prompt),
                projection_descriptor=_current_projection_descriptor(prompt_history),
                timeout_seconds=model_timeout_seconds,
                log_prefix=f"implement_v2 live_json session={lane_input.work_session_id} turn={turn_index}",
            )
            model_turn_output = _call_model_turn(
                model_turn_input,
                model_json_callable=model_json_callable,
                model_auth=model_auth,
                base_url=base_url,
                progress=progress,
            )
            prompt_chars_total += model_turn_output.prompt_chars
            model_elapsed_seconds += model_turn_output.elapsed_seconds
            model_turn_observations.append(dict(model_turn_output.observation))
            if model_turn_output.model_error:
                model_error = dict(model_turn_output.model_error)
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
                break
            normalized = dict(model_turn_output.normalized_payload)
            finish_arguments = normalized.get("finish") or {}
            frontier_state_update = (
                normalized.get("frontier_state_update") if isinstance(normalized.get("frontier_state_update"), dict) else {}
            )
            if frontier_state_update:
                hard_runtime_frontier_enabled = True
            raw_tool_calls = normalized.get("tool_calls") or ()
            if raw_tool_calls and frontier_state_update:
                hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
                    existing=hard_runtime_frontier_state,
                    update=frontier_state_update,
                    tool_results=tuple(tool_results),
                    artifact_namespace=artifact_namespace,
                )
                if hard_runtime_frontier_state.get("final_artifact") and _single_no_contract_exec_call(raw_tool_calls):
                    hard_runtime_frontier_state["_same_turn_model_declared_final_artifact"] = True
                exec_runtime.frontier_state = dict(hard_runtime_frontier_state)
            if not raw_tool_calls:
                if hard_runtime_frontier_enabled or frontier_state_update:
                    hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
                        existing=hard_runtime_frontier_state,
                        update=frontier_state_update,
                        tool_results=tuple(tool_results),
                        artifact_namespace=artifact_namespace,
                    )
                    exec_runtime.frontier_state = dict(hard_runtime_frontier_state)
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
                            append_finish_gate_history(
                                decision=finish_gate_decision,
                                continuation_prompt=continuation_prompt,
                            )
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
                        reaction_summary = finish_gate_terminal_failure_reaction_summary(())
                        if reaction_summary:
                            append_finish_gate_history(
                                decision=finish_gate_decision,
                                continuation_prompt=continuation_prompt,
                            )
                            finish_arguments = {
                                "outcome": "continue",
                                "summary": reaction_summary,
                                "finish_gate": finish_gate_decision,
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
            current_calls = _normalize_accept_edits_write_calls(lane_input, current_calls)
            identity_errors = _tool_call_identity_errors(
                current_calls,
                expected_lane_attempt_id=lane_attempt_id,
                seen_provider_call_ids=seen_provider_call_ids,
            ) + provider_call_id_repairs
            wall_blocked_tool_execution = False
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
                executed_calls = []
                current_results_list = []
                for call_index, call in enumerate(current_calls):
                    capped_call, block_result, block_timeout = _wall_budget_gate_tool_call(
                        call,
                        lane_input=lane_input,
                        run_started=run_started,
                    )
                    if block_timeout:
                        wall_timeout = dict(block_timeout)
                    if block_result is not None:
                        executed_calls.append(capped_call)
                        current_results_list.append(block_result)
                        wall_blocked_tool_execution = True
                        break
                    executed_calls.append(capped_call)
                    current_results_list.append(
                        _execute_live_json_tool(
                            capped_call,
                            lane_input=lane_input,
                            exec_runtime=exec_runtime,
                            write_runtime=write_runtime,
                        )
                    )
                    blocking_result = current_results_list[-1]
                    if _same_turn_write_failure_blocks_remaining_calls(blocking_result):
                        for skipped_call in current_calls[call_index + 1 :]:
                            executed_calls.append(skipped_call)
                            current_results_list.append(
                                build_invalid_tool_result(
                                    skipped_call,
                                    reason=(
                                        "blocked_by_prior_failed_write_in_same_turn: "
                                        f"{capped_call.tool_name}#{capped_call.provider_call_id} "
                                        f"ended with status={blocking_result.status}; "
                                        "retry after observing the write failure"
                                    ),
                                )
                            )
                        break
                current_calls = tuple(executed_calls)
                current_results = tuple(current_results_list)
            auto_poll_chunk = _auto_poll_yielded_verifier_commands(
                current_results,
                exec_runtime=exec_runtime,
                lane_input=lane_input,
                run_started=run_started,
            )
            if auto_poll_chunk:
                auto_poll_payloads += auto_poll_chunk
                current_results = _project_command_closeouts(
                    current_results,
                    closeout_payloads=auto_poll_chunk,
                    cleanup_payloads=(),
                    exec_runtime=exec_runtime,
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
                    exec_runtime=exec_runtime,
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
                exec_runtime.frontier_state = dict(hard_runtime_frontier_state)
            elif _has_structured_frontier_evidence(current_results):
                hard_runtime_frontier_enabled = True
                hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
                    existing=hard_runtime_frontier_state,
                    update={},
                    tool_results=tuple(tool_results),
                    artifact_namespace=artifact_namespace,
                )
                exec_runtime.frontier_state = dict(hard_runtime_frontier_state)
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
                "tool_calls": [_provider_visible_tool_call_for_history(call) for call in current_calls],
                "tool_results": [_provider_visible_tool_result_for_history(result) for result in current_results],
            }
            history.append(history_entry)
            prompt_history.append(prompt_history_entry)
            if progress:
                progress(
                    f"implement_v2 turn #{turn_index}: "
                    f"{len(current_calls)} call(s), statuses={','.join(result.status for result in current_results)}"
                )
            if wall_blocked_tool_execution:
                finish_arguments = {
                    "outcome": "blocked",
                    "summary": "implement_v2 wall-clock budget exhausted before tool execution",
                }
                break
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
                        append_finish_gate_history(
                            decision=finish_gate_decision,
                            continuation_prompt=continuation_prompt,
                        )
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
                    reaction_summary = finish_gate_terminal_failure_reaction_summary(current_results)
                    if reaction_summary:
                        append_finish_gate_history(
                            decision=finish_gate_decision,
                            continuation_prompt=continuation_prompt,
                        )
                        finish_arguments = {
                            "outcome": "continue",
                            "summary": reaction_summary,
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
                exec_runtime=exec_runtime,
            )
        )
    if hard_runtime_frontier_enabled or hard_runtime_frontier_state:
        hard_runtime_frontier_state = _merge_hard_runtime_frontier_state(
            existing=hard_runtime_frontier_state,
            update={},
            tool_results=tuple(tool_results),
            artifact_namespace=artifact_namespace,
        )
        exec_runtime.frontier_state = dict(hard_runtime_frontier_state)

    integration_observation = _integration_observation_summary(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        artifact_namespace=artifact_namespace,
        transport=adapter.provider,
        model_turn_observations=tuple(model_turn_observations),
        model_elapsed_seconds=model_elapsed_seconds,
        artifact_ref=(
            "integration-observation.json"
            if _should_write_integration_observation_detail(lane_input)
            and str(lane_input.lane_config.get("artifact_dir") or "").strip()
            else ""
        ),
    )
    typed_acceptance_snapshot = _typed_acceptance_session_from_tool_results(tuple(tool_results), lane_input=lane_input)
    typed_metrics = _typed_acceptance_metrics(typed_acceptance_snapshot, finish_gate_decision)
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
            "hard_runtime_progress_continuation_turn_limit": hard_runtime_progress_continuation_turn_limit,
            "hard_runtime_progress_continuation_turns_used": hard_runtime_progress_continuation_turns_used,
            "tool_contract_recovery_turn_limit": tool_contract_recovery_turn_limit,
            "tool_contract_recovery_turns_used": tool_contract_recovery_turns_used,
            "command_closeout_count": len(closeout_payloads),
            "active_command_auto_poll_count": len(auto_poll_payloads),
            "active_command_auto_poll_terminal_count": _terminal_auto_poll_payload_count(auto_poll_payloads),
            "orphaned_command_cleanup_count": len(cleanup_payloads),
            "finish_gate_block_count": finish_gate_block_count,
            "finish_gate_decision": dict(finish_gate_decision),
            **typed_metrics,
            "wall_timeout": dict(wall_timeout),
            "wall_elapsed_seconds": round(max(0.0, time.monotonic() - run_started), 3),
            "integration_observation": integration_observation,
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
        integration_observation_detail=tuple(model_turn_observations),
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
            "hard_runtime_progress_continuation_turn_limit": hard_runtime_progress_continuation_turn_limit,
            "hard_runtime_progress_continuation_turns_used": hard_runtime_progress_continuation_turns_used,
            "tool_contract_recovery_turn_limit": tool_contract_recovery_turn_limit,
            "tool_contract_recovery_turns_used": tool_contract_recovery_turns_used,
            "finish_gate_block_count": finish_gate_block_count,
            "finish_gate_decision": dict(finish_gate_decision),
            **typed_metrics,
            "wall_timeout": dict(wall_timeout),
            "wall_elapsed_seconds": round(max(0.0, time.monotonic() - run_started), 3),
            "prompt_chars_total": prompt_chars_total,
            "prompt_sections": prompt_metrics,
            "write_evidence_count": _write_evidence_count(tool_results),
            "terminal_evidence_count": _terminal_evidence_count(tool_results),
            "command_closeout_count": len(closeout_payloads),
            "active_command_auto_poll_count": len(auto_poll_payloads),
            "active_command_auto_poll_terminal_count": _terminal_auto_poll_payload_count(auto_poll_payloads),
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
            task_contract=lane_input.task_contract,
            frontier_state=_initial_hard_runtime_frontier_state(lane_input),
        )
        try:
            tool_results = tuple(
                _execute_exec_or_read_tool(call, lane_input=lane_input, exec_runtime=exec_runtime) for call in tool_calls
            )
        finally:
            cleanup_payloads = exec_runtime.cancel_active_commands(
                reason="implement_v2 exec attempt closed before command finalized"
            )
        tool_results = _project_orphaned_command_cleanup(tool_results, cleanup_payloads, exec_runtime=exec_runtime)
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
            task_contract=lane_input.task_contract,
            frontier_state=_initial_hard_runtime_frontier_state(lane_input),
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
        tool_results = _project_orphaned_command_cleanup(tool_results, cleanup_payloads, exec_runtime=exec_runtime)
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
    exec_runtime: ImplementV2ManagedExecRuntime | None = None,
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
            if exec_runtime is not None:
                projected.append(exec_runtime.project_result_payload(result, payload))
            else:
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
    *,
    exec_runtime: ImplementV2ManagedExecRuntime | None = None,
) -> tuple[ToolResultEnvelope, ...]:
    return _project_command_closeouts(
        tool_results,
        closeout_payloads=(),
        cleanup_payloads=cleanup_payloads,
        exec_runtime=exec_runtime,
    )


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


def _auto_poll_yielded_verifier_commands(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    exec_runtime: ImplementV2ManagedExecRuntime,
    lane_input: ImplementLaneInput,
    run_started: float,
) -> tuple[dict[str, object], ...]:
    if not any(_is_auto_pollable_yielded_verifier_result(result) for result in tool_results):
        return ()
    budget = _active_command_auto_poll_budget_seconds(lane_input, run_started=run_started)
    if budget <= 0:
        return ()
    payloads = exec_runtime.poll_active_commands(wait_seconds=budget)
    terminal_payloads = tuple(payload for payload in payloads if _is_terminal_auto_poll_payload(payload))
    if terminal_payloads:
        return terminal_payloads
    if payloads:
        return exec_runtime.cancel_active_commands(
            reason="implement_v2 verifier auto-poll budget exhausted before terminal evidence"
        )
    return ()


def _is_auto_pollable_yielded_verifier_result(result: ToolResultEnvelope) -> bool:
    if result.tool_name not in {"run_command", "run_tests", "poll_command"} or result.status != "yielded":
        return False
    payload = _first_result_payload(result)
    normalized_contract = payload.get("execution_contract_normalized")
    raw_contract = payload.get("execution_contract")
    contract = normalized_contract if isinstance(normalized_contract, dict) else {}
    if not contract and isinstance(raw_contract, dict):
        contract = raw_contract
    if not contract:
        return False
    proof_role = str(contract.get("proof_role") or "").strip().lower()
    acceptance_kind = str(contract.get("acceptance_kind") or "").strip().lower()
    stage = str(contract.get("stage") or "").strip().lower()
    purpose = str(contract.get("purpose") or "").strip().lower()
    if proof_role in {"verifier", "verification"}:
        return True
    if acceptance_kind in {"external_verifier", "final_verifier", "verifier"}:
        return True
    if "verif" in stage or "verif" in purpose:
        return True
    return False


def _first_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    for item in result.content:
        if isinstance(item, dict):
            return item
    return {}


def _active_command_auto_poll_budget_seconds(lane_input: ImplementLaneInput, *, run_started: float) -> float:
    configured = lane_input.lane_config.get("active_command_auto_poll_seconds")
    try:
        configured_budget = float(configured) if configured not in (None, "") else 60.0
    except (TypeError, ValueError):
        configured_budget = 0.0
    budget = max(0.0, min(120.0, configured_budget))
    wall_remaining = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if wall_remaining is None:
        return budget
    return min(budget, wall_remaining)


def _terminal_auto_poll_payload_count(payloads: tuple[dict[str, object], ...]) -> int:
    return sum(
        1
        for payload in payloads
        if _projected_command_closeout_status(payload) in {"completed", "failed", "interrupted"}
    )


def _is_terminal_auto_poll_payload(payload: dict[str, object]) -> bool:
    status = str(payload.get("status") or "").strip()
    return (
        status in {"completed", "failed", "timed_out", "killed", "orphaned"}
        or payload.get("exit_code") is not None
        or bool(payload.get("timed_out"))
    )


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


def _model_turn_timeout_seconds(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
    requested_timeout: float,
) -> float:
    try:
        timeout = max(0.0, float(requested_timeout))
    except (TypeError, ValueError):
        timeout = 0.0
    remaining_wall = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining_wall is None:
        return timeout
    if remaining_wall <= 0:
        return 0.0
    if timeout <= 0:
        return max(_IMPLEMENT_V2_MIN_MODEL_TURN_TIMEOUT_SECONDS, remaining_wall)
    return min(timeout, max(_IMPLEMENT_V2_MIN_MODEL_TURN_TIMEOUT_SECONDS, remaining_wall))


def _wall_budget_gate_tool_call(
    call: ToolCallEnvelope,
    *,
    lane_input: ImplementLaneInput,
    run_started: float,
) -> tuple[ToolCallEnvelope, ToolResultEnvelope | None, dict[str, object]]:
    if call.tool_name not in {"run_command", "run_tests", "poll_command"}:
        return call, None, {}
    remaining_wall = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining_wall is None:
        return call, None, {}
    if remaining_wall <= 0:
        wall_timeout = _implement_v2_wall_timeout(
            lane_input,
            run_started=run_started,
            reason="not enough wall-clock budget remains for tool execution",
            next_turn=call.turn_index,
            requested_model_timeout=0.0,
        )
        return (
            call,
            build_invalid_tool_result(
                call,
                reason="implement_v2_wall_budget_exhausted_before_tool_execution",
            ),
            wall_timeout,
        )
    args = dict(call.arguments)
    if call.tool_name in {"run_command", "run_tests"}:
        args["foreground_budget_seconds"] = _cap_optional_seconds(
            args.get("foreground_budget_seconds"),
            default=min(15.0, max(0.0, remaining_wall)),
            cap=remaining_wall,
        )
        if args.get("timeout") not in (None, ""):
            args["timeout"] = _cap_optional_seconds(args.get("timeout"), default=remaining_wall, cap=remaining_wall)
    elif call.tool_name == "poll_command":
        args["wait_seconds"] = _cap_optional_seconds(args.get("wait_seconds"), default=0.0, cap=remaining_wall)
    return replace(call, arguments=args), None, {}


def _cap_optional_seconds(value: object, *, default: float, cap: float) -> float:
    try:
        seconds = float(value) if value not in (None, "") else float(default)
    except (TypeError, ValueError):
        seconds = float(default)
    return max(0.0, min(max(0.0, float(cap)), seconds))


def _implement_v2_wall_timeout(
    lane_input: ImplementLaneInput,
    *,
    run_started: float,
    reason: str,
    next_turn: int,
    requested_model_timeout: float,
) -> dict[str, object]:
    elapsed = max(0.0, time.monotonic() - run_started)
    max_wall = lane_input.task_contract.get("max_wall_seconds")
    try:
        max_wall_seconds = float(max_wall) if max_wall not in (None, "") else None
    except (TypeError, ValueError):
        max_wall_seconds = None
    remaining = None if max_wall_seconds is None else max(0.0, max_wall_seconds - elapsed)
    return {
        "elapsed_seconds": round(elapsed, 3),
        "max_wall_seconds": max_wall_seconds,
        "next_turn": int(next_turn),
        "remaining_seconds": None if remaining is None else round(remaining, 3),
        "requested_model_timeout_seconds": round(max(0.0, float(requested_model_timeout or 0.0)), 3),
        "reason": reason,
    }


def _terminal_failure_reaction_turn_limit(lane_input: ImplementLaneInput, base_max_turns: int) -> int:
    configured = lane_input.lane_config.get("terminal_failure_reaction_turns")
    if configured not in (None, ""):
        try:
            return max(0, min(12, int(configured)))
        except (TypeError, ValueError):
            return 0
    default_limit = max(1, min(3, int(base_max_turns) // 8 or 1))
    if _uses_expanded_hard_runtime_reaction_budget(lane_input, base_max_turns=base_max_turns):
        return max(default_limit, min(8, max(4, int(base_max_turns) // 3 or 1)))
    return default_limit


def _uses_expanded_hard_runtime_reaction_budget(lane_input: ImplementLaneInput, *, base_max_turns: int) -> bool:
    if int(base_max_turns) < 8:
        return False
    if not is_hard_runtime_artifact_task(lane_input.task_contract):
        frontier = lane_input.persisted_lane_state.get("lane_hard_runtime_frontier")
        if not isinstance(frontier, dict) or str(frontier.get("status") or "") not in {"active", "blocked"}:
            return False
    max_wall = lane_input.task_contract.get("max_wall_seconds")
    if max_wall in (None, ""):
        return False
    try:
        return float(max_wall) >= 600.0
    except (TypeError, ValueError):
        return False


def _hard_runtime_progress_continuation_turn_limit(
    lane_input: ImplementLaneInput,
    *,
    base_max_turns: int,
) -> int:
    configured = lane_input.lane_config.get("hard_runtime_progress_continuation_turns")
    if configured not in (None, ""):
        try:
            return max(0, min(8, int(configured)))
        except (TypeError, ValueError):
            return 0
    if not _uses_expanded_hard_runtime_reaction_budget(lane_input, base_max_turns=base_max_turns):
        return 0
    return _HARD_RUNTIME_PROGRESS_CONTINUATION_DEFAULT_LIMIT


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


def _hard_runtime_progress_continuation_signature(
    lane_input: ImplementLaneInput,
    tool_results: tuple[ToolResultEnvelope, ...],
    frontier_state: dict[str, object],
    *,
    seen_signatures: set[str],
    reaction_turns_used: int,
    reaction_turn_limit: int,
    progress_turns_used: int,
    progress_turn_limit: int,
    run_started: float,
) -> str:
    if reaction_turns_used < reaction_turn_limit:
        return ""
    if progress_turns_used >= progress_turn_limit:
        return ""
    if not _has_terminal_failure_result(tool_results):
        return ""
    remaining_wall = _remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining_wall is not None:
        configured_minimum = lane_input.lane_config.get("terminal_failure_reaction_min_wall_seconds")
        try:
            minimum_wall = float(configured_minimum) if configured_minimum not in (None, "") else 30.0
        except (TypeError, ValueError):
            minimum_wall = 30.0
        if remaining_wall < max(0.0, minimum_wall):
            return ""
    signature = _hard_runtime_frontier_progress_signature(frontier_state)
    if not signature or signature in seen_signatures:
        return ""
    return signature


def _hard_runtime_frontier_progress_signature(frontier_state: dict[str, object] | None) -> str:
    """Return a stable signature only for actionable hard-runtime frontier progress."""

    if not isinstance(frontier_state, dict):
        return ""
    runtime_failure = frontier_state.get("latest_runtime_failure")
    if not isinstance(runtime_failure, dict):
        return ""
    final_artifact = frontier_state.get("final_artifact")
    final_artifact_map = final_artifact if isinstance(final_artifact, dict) else {}
    build_target = frontier_state.get("build_target")
    build_target_map = build_target if isinstance(build_target, dict) else {}
    artifact_path = str(final_artifact_map.get("path") or "").strip()
    build_artifact_path = str(
        build_target_map.get("artifact_path") or build_target_map.get("target") or build_target_map.get("path") or ""
    ).strip()
    failure_class = str(runtime_failure.get("failure_class") or "").strip()
    failure_kind = str(runtime_failure.get("failure_kind") or "").strip()
    failure_phase = str(runtime_failure.get("failure_phase") or "").strip()
    if not artifact_path and not build_artifact_path:
        return ""
    artifact_status = str(final_artifact_map.get("status") or "").strip()
    artifact_blocking = bool(final_artifact_map.get("blocking"))
    runtime_failure_classes = {"runtime_artifact_missing", "runtime_failure", "verification_failure"}
    artifact_progress_failure = (
        failure_class == "artifact_validation_failure"
        and failure_kind == "missing_artifact"
        and artifact_blocking
        and artifact_status == "failed"
        and failure_phase in {"", "unknown", "runtime", "verification"}
    )
    if failure_phase and failure_phase != "runtime" and not artifact_progress_failure:
        return ""
    if failure_class and failure_class not in runtime_failure_classes and not artifact_progress_failure:
        return ""
    stdout_tail = str(runtime_failure.get("stdout_tail") or "").strip()
    stderr_tail = str(runtime_failure.get("stderr_tail") or "").strip()
    if not (stdout_tail or stderr_tail or artifact_status):
        return ""
    payload = {
        "artifact_path": artifact_path,
        "artifact_status": artifact_status,
        "build_artifact_path": build_artifact_path,
        "failure_class": failure_class,
        "failure_kind": failure_kind,
        "failure_phase": failure_phase,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8", errors="replace")
    return hashlib.sha256(encoded).hexdigest()[:24]


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
        if failure_key == "latest_runtime_failure":
            merged.pop("latest_build_failure", None)
        elif failure_key == "latest_build_failure":
            merged.pop("latest_runtime_failure", None)

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
        "legacy_runtime_marker_fallback",
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
        contract = _payload_execution_contract(payload)
        if not contract:
            continue
        if not _execution_contract_updates_hard_runtime_frontier(contract):
            continue
        refs = _frontier_result_refs(result, registry)
        expected_artifact = _frontier_expected_artifact_from_contract(contract, payload=payload)
        if expected_artifact and "final_artifact" not in derived:
            final_artifact = _resolve_frontier_mapping_refs(expected_artifact, registry)
            if refs:
                final_artifact["evidence_refs"] = refs
            derived["final_artifact"] = final_artifact
        if _execution_contract_is_build_like(contract) and "build_target" not in derived:
            build_target = _frontier_build_target_from_contract(contract, payload, expected_artifact)
            if refs:
                build_target["evidence_refs"] = refs
            derived["build_target"] = _resolve_frontier_mapping_refs(build_target, registry)
    return derived


def _frontier_result_refs(result: ToolResultEnvelope, registry: dict[str, object]) -> list[dict[str, object]]:
    return _resolve_frontier_refs([*result.evidence_refs, *result.content_refs], registry)


def _frontier_expected_artifact_from_contract(
    contract: dict[str, object],
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    if payload and _execution_contract_is_verifier_like(contract):
        blocking_artifact = _frontier_blocking_artifact_from_payload(payload)
        if blocking_artifact:
            return blocking_artifact
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


def _frontier_blocking_artifact_from_payload(payload: dict[str, object]) -> dict[str, object]:
    artifacts = payload.get("artifact_evidence")
    if not isinstance(artifacts, list):
        return {}
    for artifact in artifacts:
        if isinstance(artifact, dict) and bool(artifact.get("blocking")):
            return _frontier_artifact_from_evidence(artifact)
    for artifact in artifacts:
        if isinstance(artifact, dict) and str(artifact.get("status") or "").strip().lower() == "failed":
            return _frontier_artifact_from_evidence(artifact)
    return {}


def _frontier_artifact_from_evidence(artifact: dict[str, object]) -> dict[str, object]:
    return _drop_empty_frontier_values(
        {
            "path": _frontier_clip_text(artifact.get("path"), limit=400),
            "kind": _frontier_clip_text(artifact.get("kind"), limit=120),
            "freshness": _frontier_clip_text(artifact.get("freshness")),
            "status": _frontier_clip_text(artifact.get("status"), limit=120),
            "blocking": bool(artifact.get("blocking")),
            "source": _frontier_clip_text(artifact.get("source"), limit=160),
        }
    )


def _first_contract_list_item(value: object) -> object:
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return None


def _payload_execution_contract(payload: dict[str, object]) -> dict[str, object]:
    raw = payload.get("execution_contract")
    raw_contract = raw if isinstance(raw, dict) else {}
    normalized = payload.get("execution_contract_normalized")
    normalized_contract = normalized if isinstance(normalized, dict) else {}
    merged = {**normalized_contract, **raw_contract}
    if not merged:
        return {}
    contract = normalize_execution_contract(merged).as_dict()
    for source in (normalized_contract, raw_contract):
        for key, value in source.items():
            if key not in contract:
                contract[key] = value
    return contract


def _execution_contract_enum(contract: dict[str, object], key: str) -> str:
    return str(contract.get(key) or "").strip().lower()


def _execution_contract_is_build_like(contract: dict[str, object]) -> bool:
    role = _execution_contract_enum(contract, "role")
    if role in {"runtime", "test", "verify", "artifact_probe"}:
        return False
    return (
        role == "build"
        or _execution_contract_enum(contract, "purpose") in {"build", "runtime_build"}
        or _execution_contract_enum(contract, "stage") in {"build", "runtime_build"}
        or _execution_contract_enum(contract, "proof_role") == "target_build"
    )


def _execution_contract_is_runtime_like(contract: dict[str, object]) -> bool:
    role = _execution_contract_enum(contract, "role")
    if role == "build":
        return False
    return (
        role == "runtime"
        or _execution_contract_enum(contract, "purpose") in {"runtime_build", "runtime_install", "smoke", "verification"}
        or _execution_contract_enum(contract, "stage")
        in {"runtime_build", "runtime_install", "default_smoke", "custom_runtime_smoke", "verification"}
        or _execution_contract_enum(contract, "proof_role")
        in {"runtime_install", "default_smoke", "custom_runtime_smoke", "verifier"}
        or _execution_contract_enum(contract, "acceptance_kind") == "external_verifier"
    )


def _execution_contract_is_verifier_like(contract: dict[str, object]) -> bool:
    return (
        _execution_contract_is_runtime_like(contract)
        or _execution_contract_enum(contract, "purpose") in {"artifact_proof", "verification"}
        or _execution_contract_enum(contract, "stage") in {"artifact_proof", "verification"}
        or _execution_contract_enum(contract, "proof_role") in {"final_artifact", "verifier"}
        or _execution_contract_enum(contract, "acceptance_kind") in {"candidate_final_proof", "external_verifier"}
    )


def _execution_contract_updates_hard_runtime_frontier(contract: dict[str, object]) -> bool:
    role = _execution_contract_enum(contract, "role")
    acceptance_kind = _execution_contract_enum(contract, "acceptance_kind")
    proof_role = _execution_contract_enum(contract, "proof_role")
    if (
        role == "diagnostic"
        and acceptance_kind in {"not_acceptance", "progress_only"}
        and proof_role in {"none", "progress", "negative_diagnostic"}
    ):
        return False
    return True


def _legacy_frontier_marker_fallback_allowed(payload: dict[str, object]) -> bool:
    return not bool(_payload_execution_contract(payload))


def _execution_contract_bridge_failure_class(contract: dict[str, object]) -> str:
    if _execution_contract_is_runtime_like(contract):
        return "runtime_failure"
    if _execution_contract_is_build_like(contract):
        return "build_failure"
    return "unknown_failure"


def _execution_contract_bridge_required_next_probe(contract: dict[str, object]) -> str:
    if _execution_contract_is_runtime_like(contract):
        return (
            "Attach execution_contract.expected_artifacts and rerun the runtime verifier so mew can classify "
            "artifact evidence structurally."
        )
    if _execution_contract_is_build_like(contract):
        return (
            "Attach execution_contract.expected_artifacts or target_build evidence before treating command text "
            "as a build artifact proof."
        )
    return "Attach structured execution_contract evidence before classifying this terminal failure."


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
        contract = _payload_execution_contract(payload)
        if contract and not _execution_contract_updates_hard_runtime_frontier(contract):
            continue
        key = _frontier_failure_key_from_payload(payload)
        return key, _frontier_failure_payload(payload)
    return None


def _has_structured_frontier_evidence(tool_results: tuple[ToolResultEnvelope, ...]) -> bool:
    for result in tool_results:
        payload = next((item for item in result.content if isinstance(item, dict)), {})
        if _structured_failure_classification(payload):
            return True
    return False


def _frontier_failure_key_from_payload(payload: dict[str, object]) -> str:
    structured = _structured_failure_classification(payload)
    if structured:
        failure_class = str(structured.get("class") or structured.get("failure_class") or "")
        phase = str(structured.get("phase") or "")
        if failure_class in {"build_failure", "build_artifact_missing"} or phase in {"build", "dependency"}:
            return "latest_build_failure"
        if failure_class in {"runtime_failure", "runtime_artifact_missing"} or phase == "runtime":
            return "latest_runtime_failure"
        if failure_class == "artifact_validation_failure":
            if _structured_runtime_inferred_artifact_obligation(payload):
                return "latest_runtime_failure"
            return "latest_runtime_failure" if phase in {"runtime", "verification"} else "latest_build_failure"
        if failure_class == "verification_failure":
            return "latest_runtime_failure"
    contract = _payload_execution_contract(payload)
    if contract:
        failure_class = _execution_contract_bridge_failure_class(contract)
        if failure_class == "build_failure":
            return "latest_build_failure"
        return "latest_runtime_failure"
    return "latest_runtime_failure"


def _frontier_failure_payload(payload: dict[str, object]) -> dict[str, object]:
    structured = _structured_failure_classification(payload)
    contract = _payload_execution_contract(payload)
    evidence_text = _frontier_failure_evidence_text(payload)
    failure = {
        "command_run_id": _frontier_clip_text(payload.get("command_run_id"), limit=160),
        "exit_code": payload.get("exit_code"),
        "stdout_tail": _frontier_clip_text(payload.get("stdout_tail") or payload.get("stdout")),
        "stderr_tail": _frontier_clip_text(payload.get("stderr_tail") or payload.get("stderr")),
        "failure_summary": _frontier_failure_summary(payload),
    }
    if structured:
        failure["failure_class"] = _frontier_clip_text(
            structured.get("class") or structured.get("failure_class"),
            limit=160,
        )
        failure["failure_kind"] = _frontier_clip_text(structured.get("kind"), limit=160)
        failure["failure_phase"] = _frontier_clip_text(structured.get("phase"), limit=160)
        if structured.get("summary"):
            failure["failure_summary"] = _frontier_clip_text(structured.get("summary"))
        if structured.get("required_next_probe"):
            failure["required_next_probe"] = _frontier_clip_text(
                structured.get("required_next_probe"),
                limit=400,
            )
        evidence_refs = structured.get("evidence_refs")
        if isinstance(evidence_refs, list):
            failure["evidence_refs"] = _frontier_compact_value(evidence_refs, key="evidence_refs")
    elif contract:
        failure["failure_class"] = _execution_contract_bridge_failure_class(contract)
        failure["failure_confidence"] = "low"
        failure["legacy_marker_authority"] = "inactive_contract_backed"
        failure["required_next_probe"] = _execution_contract_bridge_required_next_probe(contract)
    else:
        legacy_marker = _legacy_runtime_marker_audit(payload, evidence_text=evidence_text)
        if legacy_marker:
            failure["legacy_runtime_marker_fallback"] = legacy_marker
    if payload.get("output_ref"):
        failure["output_ref"] = _frontier_clip_text(payload.get("output_ref"), limit=240)
    return _drop_empty_frontier_values(failure)


def _structured_failure_classification(payload: dict[str, object]) -> dict[str, object]:
    value = payload.get("failure_classification")
    if not isinstance(value, dict):
        return {}
    artifact_evidence = payload.get("artifact_evidence")
    if not isinstance(artifact_evidence, list) or not artifact_evidence:
        return {}
    failure_class = str(value.get("class") or value.get("failure_class") or "")
    if not failure_class or failure_class == "unknown_failure":
        return {}
    return dict(value)


def _structured_runtime_inferred_artifact_obligation(payload: dict[str, object]) -> bool:
    artifacts = payload.get("artifact_evidence")
    if not isinstance(artifacts, list):
        return False
    for item in artifacts:
        if isinstance(item, dict) and str(item.get("source") or "") == "runtime_inferred":
            return True
    return False


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


def _legacy_runtime_marker_audit(payload: dict[str, object], *, evidence_text: str) -> dict[str, object]:
    if not _legacy_frontier_marker_fallback_allowed(payload):
        return {}
    kind = ""
    if _frontier_runtime_artifact_contract_mismatch(evidence_text):
        kind = "runtime_artifact_contract_mismatch"
    elif _frontier_runtime_execution_timeout(evidence_text):
        kind = "runtime_execution_timeout"
    elif _frontier_runtime_artifact_missing(evidence_text):
        kind = "runtime_artifact_missing"
    if not kind:
        return {}
    return {
        "detected": True,
        "kind": kind,
        "confidence": "low",
        "active": False,
        "inactive_reason": "marker_only_not_authoritative",
    }


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
        contract = _payload_execution_contract(payload)
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
    response_contract: dict[str, object] = {
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
            "evidence_refs": [{"kind": "evidence_event", "id": "ev:..."}],
            "acceptance_evidence": ["optional human-readable evidence summary"],
        },
    }
    if hard_runtime_frontier_state:
        response_contract["frontier_state_update"] = {
            "optional": True,
            "use_only_when": "a hard-runtime or compatibility frontier genuinely changed",
            "derived_failure_note": (
                "Do not author latest_runtime_failure/latest_build_failure; "
                "mew derives the latest failure from paired tool results."
            ),
            "status": "active | blocked | resolved",
            "objective": "short objective when it prevents rediscovery or false completion",
            "next_verifier_shaped_command": {
                "tool": "run_command",
                "cwd": ".",
                "command": "short verifier command",
                "use_shell": True,
            },
        }
    recovery_instruction_section = ""
    if tool_contract_recovery_instruction:
        recovery_instruction_section = f"tool_contract_recovery_instruction:\n{tool_contract_recovery_instruction}"
    terminal_reaction_guidance = ""
    if terminal_failure_reaction_turns_used > 0 and not tool_contract_recovery_instruction:
        terminal_reaction_guidance = _terminal_failure_reaction_guidance(
            hard_runtime_frontier_state=hard_runtime_frontier_state,
        )
    return (
        f"{sections}\n\n"
        "[section:implement_v2_live_json_transport version=v0 stability=dynamic cache_policy=dynamic]\n"
        "Implement V2 Live JSON Transport\n"
        "This run is a real implement_v2 lane attempt. Do not emit v1 THINK/ACT actions. "
        "Return exactly one JSON object. Use tool_calls for observations, edits, and commands. "
        "Use finish only when the task is completed, blocked, or failed. If more work is needed, "
        "set finish.outcome to continue or omit finish. For edits, prefer exact edit_file old/new "
        "(old_string/new_string aliases are accepted) or apply_patch. If the CLI grants accept-edits, "
        "write/edit/apply_patch calls without dry_run=true or apply=false are intended to mutate; "
        "mew defaults omitted apply to true and supplies independent approval outside the model output. "
        "For a missing write_file target, mew also defaults omitted create to true. If tests or an external verifier matter, "
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
        f"history_json:\n{_render_prompt_history_json(history)}\n"
        "[/section:implement_v2_live_json_transport]"
    )


def _terminal_failure_reaction_guidance(*, hard_runtime_frontier_state: dict[str, object] | None) -> str:
    guidance = (
        "If this is a terminal-failure reaction turn, do not broaden the task: make the smallest "
        "repair/check that directly responds to the latest failed terminal result, or finish blocked "
        "with the exact blocker.\n"
    )
    if not hard_runtime_frontier_state:
        return guidance
    latest_failure = hard_runtime_frontier_state.get("latest_runtime_failure")
    if not isinstance(latest_failure, dict):
        latest_failure = hard_runtime_frontier_state.get("latest_build_failure")
    if not isinstance(latest_failure, dict):
        latest_failure = {}
    required_next_probe = _frontier_clip_text(latest_failure.get("required_next_probe"), limit=360)
    failure_class = _frontier_clip_text(latest_failure.get("failure_class"), limit=120)
    verifier = hard_runtime_frontier_state.get("next_verifier_shaped_command")
    verifier_hint = ""
    if isinstance(verifier, dict):
        verifier_hint = f" latest_verifier_shaped_command={json.dumps(verifier, ensure_ascii=True, sort_keys=True)[:500]}"
    next_probe_hint = f" required_next_probe={required_next_probe}" if required_next_probe else ""
    class_hint = f" latest_failure_class={failure_class}" if failure_class else ""
    return (
        guidance
        + "Hard-runtime frontier continuation gate: continue from lane_hard_runtime_frontier instead of "
        "rediscovering the whole task. Inspect the producing substep/artifact path, make the smallest "
        "source/runtime repair, then run one verifier-shaped command tied to the expected runtime artifact. "
        "If mutating source/config, prefer write_file/edit_file/apply_patch; keep run_command for build, "
        "runtime, and verification."
        f"{class_hint}{next_probe_hint}{verifier_hint}\n"
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


def _single_no_contract_exec_call(tool_calls: object) -> bool:
    if not isinstance(tool_calls, (list, tuple)):
        return False
    exec_calls = [
        call
        for call in tool_calls
        if isinstance(call, dict)
        and str(call.get("tool_name") or "").strip() in {"run_command", "run_tests", "poll_command"}
    ]
    if len(exec_calls) != 1:
        return False
    arguments = exec_calls[0].get("arguments")
    if not isinstance(arguments, dict):
        return True
    contract = arguments.get("execution_contract")
    return not (isinstance(contract, dict) and bool(contract))


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


def _live_json_model_error_retryable(model_error: dict[str, object]) -> bool:
    if str(model_error.get("failure_class") or "") != "model_backend_error":
        return False
    message = str(model_error.get("message") or "").casefold()
    return any(marker in message for marker in _IMPLEMENT_V2_TRANSIENT_MODEL_ERROR_MARKERS)


def _live_json_parse_error_retryable(model_error: dict[str, object]) -> bool:
    if str(model_error.get("failure_class") or "") != "model_json_parse_error":
        return False
    raw = str(model_error.get("raw_excerpt") or "").strip().casefold()
    return raw.startswith("{") and ('"tool_calls"' in raw or '"finish"' in raw)


def _append_live_json_parse_retry_instruction(prompt: str, model_error: dict[str, object]) -> str:
    raw_excerpt = str(model_error.get("raw_excerpt") or "").strip()
    if len(raw_excerpt) > 700:
        raw_excerpt = raw_excerpt[:700] + "...[truncated]"
    return (
        f"{prompt}\n\n"
        "[section:implement_v2_json_repair_retry version=v0 stability=dynamic cache_policy=dynamic]\n"
        "Your previous response was not parseable as one complete JSON object, but it appeared to contain "
        "an implement_v2 action. Retry the same turn now.\n"
        "- Return exactly one complete JSON object, no markdown and no trailing prose.\n"
        "- Escape every newline inside string values as \\n.\n"
        "- For large source changes, prefer a smaller exact edit_file old/new or a compact apply_patch hunk; "
        "do not stream a half-written patch string.\n"
        "- Preserve the same immediate repair intent; do not restart broad exploration.\n"
        f"previous_raw_excerpt: {json.dumps(raw_excerpt, ensure_ascii=False)}\n"
        "[/section:implement_v2_json_repair_retry]"
    )


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


def _normalize_accept_edits_write_calls(
    lane_input: ImplementLaneInput,
    tool_calls: tuple[ToolCallEnvelope, ...],
) -> tuple[ToolCallEnvelope, ...]:
    if not bool(lane_input.lane_config.get("auto_approve_writes")):
        return tool_calls
    if not _allowed_write_roots(lane_input):
        return tool_calls
    return tuple(_normalize_accept_edits_write_call(lane_input, call) for call in tool_calls)


def _normalize_accept_edits_write_call(lane_input: ImplementLaneInput, call: ToolCallEnvelope) -> ToolCallEnvelope:
    if call.tool_name not in WRITE_TOOL_NAMES:
        return call
    args = dict(call.arguments)
    changed = False
    if "apply" not in args and "dry_run" not in args:
        args["apply"] = True
        changed = True
    if call.tool_name == "write_file" and "create" not in args and _write_file_target_is_missing(lane_input, args):
        args["create"] = True
        changed = True
    if not changed:
        return call
    return replace(call, arguments=args)


def _write_file_target_is_missing(lane_input: ImplementLaneInput, args: dict[str, object]) -> bool:
    raw_path = str(args.get("path") or "").strip()
    if not raw_path:
        return False
    target = Path(raw_path).expanduser()
    if not target.is_absolute():
        target = Path(str(lane_input.workspace or ".")).expanduser().resolve(strict=False) / target
    return not target.exists()


def _same_turn_write_failure_blocks_remaining_calls(result: ToolResultEnvelope) -> bool:
    if result.tool_name not in WRITE_TOOL_NAMES:
        return False
    return result.status in {"failed", "denied", "invalid", "interrupted"} or bool(result.is_error)


def _provider_visible_tool_call_for_history(call: ToolCallEnvelope) -> dict[str, object]:
    """Return a next-turn tool-call projection without bulky source text."""

    projected = call.as_dict()
    arguments = projected.get("arguments")
    if isinstance(arguments, dict):
        projected["arguments"] = _project_provider_history_tool_arguments(call.tool_name, arguments)
    return projected


def _project_provider_history_tool_arguments(tool_name: str, arguments: dict[str, object]) -> dict[str, object]:
    projected: dict[str, object] = {}
    projected_any = False
    for key, value in arguments.items():
        projected_value, projected_key = _project_provider_history_tool_argument(tool_name, str(key), value)
        projected[str(key)] = projected_value
        projected_any = projected_any or projected_key
    if projected_any:
        projected["arguments_projected_for_history"] = True
        projected["projection_note"] = (
            "large source-mutation arguments are stored in full history/proof artifacts; "
            "next-turn history keeps hashes, sizes, and bounded excerpts"
        )
    return projected


def _project_provider_history_tool_argument(tool_name: str, key: str, value: object) -> tuple[object, bool]:
    if key == "execution_contract" and isinstance(value, dict):
        return _frontier_compact_mapping(value), False
    if isinstance(value, str):
        if tool_name in WRITE_TOOL_NAMES and key in _PROVIDER_HISTORY_SOURCE_MUTATION_KEYS:
            projected = _project_source_mutation_text_argument(value, key=key)
            return projected, isinstance(projected, dict)
        if key == "command":
            return _clip_provider_history_text(value, limit=_FRONTIER_COMMAND_TEXT_LIMIT)[0], False
        compacted, clipped = _clip_provider_history_text(value, limit=_PROVIDER_HISTORY_TOOL_ARG_TEXT_LIMIT)
        if clipped:
            return _project_clipped_argument(value, key=key, limit=_PROVIDER_HISTORY_TOOL_ARG_TEXT_LIMIT), True
        return compacted, False
    if isinstance(value, list):
        compacted_items = []
        projected = len(value) > _PROVIDER_HISTORY_LIST_LIMIT
        for item in value[:_PROVIDER_HISTORY_LIST_LIMIT]:
            compacted_item, item_projected = _project_provider_history_tool_argument(tool_name, key, item)
            compacted_items.append(compacted_item)
            projected = projected or item_projected
        if len(value) > _PROVIDER_HISTORY_LIST_LIMIT:
            compacted_items.append(
                {
                    "history_list_truncated": True,
                    "omitted_items": len(value) - _PROVIDER_HISTORY_LIST_LIMIT,
                }
            )
        return compacted_items, projected
    if isinstance(value, dict):
        compacted_mapping: dict[str, object] = {}
        projected = False
        for item_key, item in value.items():
            compacted_item, item_projected = _project_provider_history_tool_argument(
                tool_name,
                str(item_key),
                item,
            )
            compacted_mapping[str(item_key)] = compacted_item
            projected = projected or item_projected
        return compacted_mapping, projected
    return value, False


def _project_source_mutation_text_argument(value: str, *, key: str) -> str | dict[str, object]:
    if len(value) <= _PROVIDER_HISTORY_SOURCE_MUTATION_TEXT_LIMIT:
        return value
    excerpt, _ = _clip_provider_history_text(value, limit=_PROVIDER_HISTORY_SOURCE_MUTATION_TEXT_LIMIT)
    return {
        "history_text_omitted": True,
        "field": key,
        "chars": len(value),
        "sha256": _sha256_text(value),
        "excerpt": excerpt,
    }


def _project_clipped_argument(value: str, *, key: str, limit: int) -> dict[str, object]:
    excerpt, _ = _clip_provider_history_text(value, limit=limit)
    return {
        "history_text_omitted": True,
        "field": key,
        "chars": len(value),
        "sha256": _sha256_text(value),
        "excerpt": excerpt,
    }


def _provider_visible_tool_result_for_history(result: ToolResultEnvelope) -> dict[str, object]:
    visible = result.provider_visible_content()
    if result.tool_name in _PROVIDER_HISTORY_TERMINAL_TOOL_NAMES:
        visible = _project_terminal_result_for_provider_history(visible)
    content = _compact_provider_visible_content_for_history(visible)
    projected = {
        "provider_call_id": result.provider_call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "content": content,
    }
    typed_digest = _typed_evidence_digest_for_result(result)
    if typed_digest:
        projected["typed_evidence"] = typed_digest
    return projected


def _typed_evidence_digest_for_result(result: ToolResultEnvelope) -> list[dict[str, object]]:
    payload = _first_result_payload(result)
    if not payload:
        return []
    events = evidence_events_from_tool_payload(
        tool_index=0,
        tool_name=result.tool_name,
        tool_status=result.status,
        provider_call_id=result.provider_call_id,
        payload=payload,
    )
    digest: list[dict[str, object]] = []
    for event in events[:8]:
        observed = dict(event.observed)
        compact_observed = {
            key: observed.get(key)
            for key in ("artifact_id", "path", "kind", "status", "verdict", "reason", "failure_class", "phase")
            if observed.get(key) not in (None, "", [], {})
        }
        digest.append(
            {
                "id": event.id,
                "kind": event.kind,
                "status": event.status,
                "obligation_id": event.obligation_id,
                "observed": compact_observed,
            }
        )
    return digest


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
    structured_summary = _structured_execution_summary_for_provider_history(payload)
    if structured_summary:
        projected["structured_execution_evidence"] = structured_summary
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


def _structured_execution_summary_for_provider_history(payload: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    tool_run = payload.get("tool_run_record")
    if isinstance(tool_run, dict):
        summary["tool_run_record"] = _drop_empty_frontier_values(
            {
                "record_id": tool_run.get("record_id"),
                "command_run_id": tool_run.get("command_run_id"),
                "contract_id": tool_run.get("contract_id"),
                "status": tool_run.get("status"),
                "semantic_exit": tool_run.get("semantic_exit"),
            }
        )
    artifacts = payload.get("artifact_evidence")
    if isinstance(artifacts, list):
        compact_artifacts = []
        for artifact in artifacts[:_PROVIDER_HISTORY_LIST_LIMIT]:
            if not isinstance(artifact, dict):
                continue
            compact_artifacts.append(
                _drop_empty_frontier_values(
                    {
                        "evidence_id": artifact.get("evidence_id"),
                        "artifact_id": artifact.get("artifact_id"),
                        "status": artifact.get("status"),
                        "blocking": artifact.get("blocking"),
                        "source": artifact.get("source"),
                        "confidence": artifact.get("confidence"),
                        "path": artifact.get("path"),
                    }
                )
            )
        if compact_artifacts:
            summary["artifact_evidence"] = compact_artifacts
    verifier = payload.get("verifier_evidence")
    if isinstance(verifier, dict):
        summary["verifier_evidence"] = _drop_empty_frontier_values(
            {
                "verifier_id": verifier.get("verifier_id"),
                "contract_id": verifier.get("contract_id"),
                "verdict": verifier.get("verdict"),
                "reason": verifier.get("reason"),
            }
        )
    classification = payload.get("failure_classification")
    if isinstance(classification, dict):
        summary["failure_classification"] = _drop_empty_frontier_values(
            {
                "classification_id": classification.get("classification_id"),
                "phase": classification.get("phase"),
                "kind": classification.get("kind"),
                "class": classification.get("class") or classification.get("failure_class"),
                "summary": classification.get("summary"),
                "required_next_probe": classification.get("required_next_probe"),
            }
        )
    finish_gate = payload.get("structured_finish_gate")
    if isinstance(finish_gate, dict):
        summary["structured_finish_gate"] = _drop_empty_frontier_values(
            {
                "blocked": finish_gate.get("blocked"),
                "reasons": finish_gate.get("reasons"),
                "evidence_refs": finish_gate.get("evidence_refs"),
            }
        )
    return _drop_empty_frontier_values(summary)


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
    marker_template = "\n...[history clipped {omitted} chars; full content remains in artifact refs]...\n"
    if limit <= len(marker_template.format(omitted=len(text))):
        return f"...[history clipped {len(text)} chars; full content remains in artifact refs]...", True
    omitted = len(text)
    head_len = 0
    tail_len = 0
    for _ in range(3):
        marker = marker_template.format(omitted=omitted)
        body_budget = max(0, limit - len(marker))
        head_len = max(1, min(len(text), body_budget * 2 // 3))
        tail_len = max(0, min(len(text) - head_len, body_budget - head_len))
        omitted = max(0, len(text) - head_len - tail_len)
    head = text[:head_len]
    tail = text[-tail_len:] if tail_len else ""
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
        _finish_acceptance_action(finish_arguments, tool_results, task_description=_live_task_description(lane_input)),
        session=_acceptance_session_from_tool_results(tool_results, lane_input=lane_input),
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
    *,
    task_description: str = "",
) -> dict[str, object]:
    action = dict(finish_arguments or {})
    action["task_done"] = _finish_outcome(action) in _COMPLETED_FINISH_OUTCOMES
    checks = action.get("acceptance_checks")
    acceptance_checks: list[object] = []
    if isinstance(checks, list):
        acceptance_checks = [
            _with_finish_evidence_refs(check, tool_results) if isinstance(check, dict) else check for check in checks
        ]
    if not acceptance_checks:
        acceptance_checks = _synthetic_finish_acceptance_checks(action, tool_results)
    sidecar_checks = [
        *_structured_finish_acceptance_checks(tool_results),
        *_source_grounding_finish_acceptance_checks(task_description, tool_results),
    ]
    acceptance_checks = _merge_finish_acceptance_sidecar_checks(acceptance_checks, sidecar_checks)
    action["acceptance_checks"] = acceptance_checks
    existing_refs = _finish_action_evidence_ref_items(action.get("evidence_refs") or action.get("evidence_ref"))
    typed_refs = _typed_finish_evidence_refs(
        tool_results,
        task_description=task_description,
        include_supplemental=not existing_refs,
    )
    merged_refs = _merge_finish_action_evidence_refs(existing_refs, typed_refs)
    if merged_refs:
        action["evidence_refs"] = merged_refs
    return action


def _merge_finish_action_evidence_refs(
    existing: object,
    typed_refs: list[dict[str, object]],
    *,
    limit: int = 16,
) -> list[dict[str, object]]:
    """Merge model refs with obligation-driven refs, keeping required refs first."""

    merged: list[dict[str, object]] = []
    seen: set[str] = set()
    for ref in [*typed_refs, *_finish_action_evidence_ref_items(existing)]:
        key = json.dumps(ref, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
        if len(merged) >= limit:
            break
    return merged


def _finish_action_evidence_ref_items(value: object) -> list[dict[str, object]]:
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return [dict(item) for item in value if item]
    if isinstance(value, dict):
        candidates = [value]
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    elif isinstance(value, str):
        candidates = [value]
    else:
        candidates = []
    refs: list[dict[str, object]] = []
    for item in candidates:
        if isinstance(item, dict):
            if item:
                refs.append(dict(item))
            continue
        if isinstance(item, str) and item.strip():
            refs.append({"kind": "evidence_event", "id": item.strip()})
    return refs


def _typed_finish_evidence_refs(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    include_supplemental: bool = True,
    task_description: object = "",
) -> list[dict[str, object]]:
    source_refs: list[dict[str, object]] = []
    for requirement in implementation_contract_source_requirements(task_description):
        if not isinstance(requirement, dict):
            continue
        source_ref = str(requirement.get("path") or "").strip()
        match = _source_grounding_tool_result(source_ref, tool_results)
        if match is None:
            continue
        tool_index, result = match
        ref = {"kind": "evidence_event", "id": f"ev:source:{source_ref}:{result.provider_call_id or tool_index}"}
        if ref not in source_refs:
            source_refs.append(ref)
    ref_limit = 16
    typed_acceptance = _typed_acceptance_session_from_tool_results(tool_results, lane_input=None)
    recommended = recommend_finish_evidence_refs(
        typed_acceptance.get("oracle_bundle") if isinstance(typed_acceptance.get("oracle_bundle"), dict) else None,
        tuple(item for item in typed_acceptance.get("evidence_events") or () if isinstance(item, dict)),
        include_supplemental=include_supplemental,
        limit=max(0, ref_limit - len(source_refs)),
    )
    if recommended:
        refs = [dict(ref) for ref in recommended]
        for ref in source_refs:
            if ref not in refs:
                refs.append(ref)
        return refs[:ref_limit]
    if not include_supplemental:
        return source_refs[:ref_limit]
    refs: list[dict[str, object]] = []
    fallback_limit = max(0, ref_limit - len(source_refs))
    for index, result in enumerate(tool_results, start=1):
        if len(refs) >= fallback_limit:
            break
        payload = _first_result_payload(result)
        if not payload:
            continue
        for event in evidence_events_from_tool_payload(
            tool_index=index,
            tool_name=result.tool_name,
            tool_status=result.status,
            provider_call_id=result.provider_call_id,
            payload=payload,
        ):
            if event.status != "passed":
                continue
            if event.kind not in {"artifact_check", "verifier_result", "oracle_check", "source_grounding"}:
                continue
            ref = {"kind": "evidence_event", "id": event.id}
            if ref not in refs:
                refs.append(ref)
            if len(refs) >= fallback_limit:
                break
    for ref in source_refs:
        if ref not in refs:
            refs.append(ref)
    return refs[:ref_limit]


def _merge_finish_acceptance_sidecar_checks(
    acceptance_checks: list[object],
    sidecar_checks: list[dict[str, object]],
) -> list[object]:
    if not sidecar_checks:
        return acceptance_checks
    for check in sidecar_checks:
        check.setdefault("source", "finish_sidecar")
    merged: list[object] = []
    for check in sidecar_checks:
        if not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    terminal_sidecars = [check for check in sidecar_checks if _acceptance_check_has_terminal_ref(check)]
    demoted_covered_checks: list[object] = []
    for check in acceptance_checks:
        demoted = _demote_unreferenced_model_check_when_sidecar_covers(check, terminal_sidecars)
        if demoted is not check:
            demoted_covered_checks.append(demoted)
            continue
        if not isinstance(check, dict) or not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    for check in demoted_covered_checks:
        if not isinstance(check, dict) or not _acceptance_check_equivalent_exists(merged, check):
            merged.append(check)
    return merged


def _acceptance_check_equivalent_exists(checks: list[object], candidate: dict[str, object]) -> bool:
    candidate_constraint = str(candidate.get("constraint") or "").casefold().strip()
    candidate_evidence = str(candidate.get("evidence") or "").casefold().strip()
    for check in checks:
        if not isinstance(check, dict):
            continue
        if str(check.get("constraint") or "").casefold().strip() != candidate_constraint:
            continue
        if str(check.get("evidence") or "").casefold().strip() == candidate_evidence:
            return True
    return False


def _acceptance_check_has_terminal_ref(check: object) -> bool:
    if not isinstance(check, dict):
        return False
    refs = check.get("evidence_refs")
    if not isinstance(refs, list):
        return False
    return any(isinstance(ref, dict) and str(ref.get("kind") or "tool_call") == "tool_call" for ref in refs)


def _demote_unreferenced_model_check_when_sidecar_covers(
    check: object,
    terminal_sidecars: list[dict[str, object]],
) -> object:
    if not isinstance(check, dict):
        return check
    if str(check.get("source") or "").endswith("_sidecar"):
        return check
    if str(check.get("status") or "").casefold() not in {"pass", "passed", "satisfied", "verified", "ok"}:
        return check
    if _acceptance_check_has_terminal_ref(check):
        return check
    if not any(_sidecar_constraint_covers_check(sidecar, check) for sidecar in terminal_sidecars):
        return check
    demoted = dict(check)
    demoted["status"] = "unknown"
    demoted["mew_demoted_reason"] = "unreferenced_model_acceptance_check_replaced_by_structured_sidecar"
    return demoted


def _sidecar_constraint_covers_check(sidecar: dict[str, object], check: dict[str, object]) -> bool:
    sidecar_constraint = _normalized_acceptance_constraint(sidecar.get("constraint"))
    check_constraint = _normalized_acceptance_constraint(check.get("constraint"))
    return bool(sidecar_constraint and check_constraint and sidecar_constraint == check_constraint)


def _normalized_acceptance_constraint(value: object) -> str:
    return " ".join(str(value or "").casefold().strip().split())


def _source_grounding_finish_acceptance_checks(
    task_description: object,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    for requirement in implementation_contract_source_requirements(task_description):
        source_ref = str(requirement.get("path") or "").strip()
        if not source_ref:
            continue
        match = _source_grounding_tool_result(source_ref, tool_results)
        if match is None:
            continue
        index, result = match
        provider_call_id = str(result.provider_call_id or "").strip()
        checks.append(
            {
                "constraint": f"provided source or artifact {source_ref} is grounded",
                "status": "verified",
                "source": "source_grounding_sidecar",
                "evidence": (
                    f"{provider_call_id or f'Tool #{index}'} completed {result.tool_name} evidence "
                    f"grounding {source_ref}"
                ),
                "evidence_refs": [{"kind": "tool_call", "id": index}],
            }
        )
    return checks


def _source_grounding_tool_result(
    source_ref: object,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> tuple[int, ToolResultEnvelope] | None:
    for index, result in enumerate(tool_results, start=1):
        if result.status != "completed" or result.tool_name not in {"glob", "read_file", "run_command", "search_text"}:
            continue
        evidence_text = "\n".join(
            chunk
            for chunk in (
                str(result.provider_call_id or ""),
                result.tool_name,
                _tool_result_content_text(result),
            )
            if chunk
        )
        if implementation_source_ref_matches_text(source_ref, evidence_text):
            return index, result
    return None


def _structured_finish_acceptance_checks(tool_results: tuple[ToolResultEnvelope, ...]) -> list[dict[str, object]]:
    for index, result in reversed(tuple(enumerate(tool_results, start=1))):
        check = _structured_finish_acceptance_check(index, result)
        if check:
            return [check]
    return []


def _structured_finish_acceptance_check(index: int, result: ToolResultEnvelope) -> dict[str, object]:
    if result.status != "completed" or result.tool_name not in EXEC_TOOL_NAMES:
        return {}
    payload = next((item for item in result.content if isinstance(item, dict)), {})
    if not isinstance(payload, dict):
        return {}
    verifier = payload.get("verifier_evidence")
    if not isinstance(verifier, dict) or str(verifier.get("verdict") or "").casefold() != "pass":
        return {}
    contract = payload.get("execution_contract_normalized")
    if not isinstance(contract, dict):
        contract = payload.get("execution_contract")
    if not _structured_finish_contract_is_final_verifier(contract):
        return {}
    artifacts = payload.get("artifact_evidence")
    if not isinstance(artifacts, list):
        return {}
    artifact_ids: list[str] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        if str(item.get("status") or "").casefold() != "passed":
            continue
        artifact_id = str(item.get("artifact_id") or item.get("path") or "").strip()
        if not artifact_id or _is_verifier_scratch_artifact_id(artifact_id):
            continue
        if artifact_id not in artifact_ids:
            artifact_ids.append(artifact_id)
    if not artifact_ids:
        return {}
    evidence_text = _structured_finish_evidence_text(result, artifact_ids)
    return {
        "constraint": _structured_finish_constraint(artifact_ids),
        "status": "verified",
        "source": "structured_finish_sidecar",
        "evidence": evidence_text,
        "evidence_refs": [{"kind": "tool_call", "id": index}],
    }


def _structured_finish_contract_is_final_verifier(contract: object) -> bool:
    if not isinstance(contract, dict):
        return False
    proof_role = str(contract.get("proof_role") or "").casefold()
    acceptance_kind = str(contract.get("acceptance_kind") or "").casefold()
    stage = str(contract.get("stage") or "").casefold()
    purpose = str(contract.get("purpose") or "").casefold()
    role = str(contract.get("role") or "").casefold()
    if acceptance_kind not in {"external_verifier", "candidate_final_proof"}:
        return False
    if proof_role not in {"verifier", "final_artifact", "custom_runtime_smoke", "default_smoke"}:
        return False
    return (
        stage in {"verification", "artifact_proof", "custom_runtime_smoke", "default_smoke"}
        or purpose in {"verification", "artifact_proof", "smoke"}
        or role in {"verify", "runtime", "test"}
    )


def _is_verifier_scratch_artifact_id(value: str) -> bool:
    lowered = value.casefold()
    if not lowered.startswith("/tmp/"):
        return False
    if not lowered.endswith((".log", ".txt", ".out", ".stdout", ".stderr")):
        return False
    name = lowered.rsplit("/", 1)[-1]
    return any(token in name for token in ("log", "out", "stdout", "stderr", "trace", "transcript"))


def _structured_finish_constraint(artifact_ids: list[str]) -> str:
    if any(_artifact_id_is_visual_runtime_output(artifact) for artifact in artifact_ids):
        return "runtime visual artifact is correct"
    return "final verifier structured evidence passed"


def _artifact_id_is_visual_runtime_output(value: str) -> bool:
    lowered = value.casefold()
    return any(marker in lowered for marker in ("frame", "image", "screenshot", ".bmp", ".png", ".jpg", ".jpeg"))


def _structured_finish_evidence_text(result: ToolResultEnvelope, artifact_ids: list[str]) -> str:
    payload = next((item for item in result.content if isinstance(item, dict)), {})
    previews: list[str] = []
    if isinstance(payload, dict):
        for key in ("stdout_tail", "stdout", "stderr_tail", "stderr"):
            value = str(payload.get(key) or "")
            if not value:
                continue
            for marker in (
                "reference similarity",
                "similarity passed",
                "SSIM passed",
            ):
                if marker.casefold() in value.casefold() and marker not in previews:
                    previews.append(marker)
            for line in value.splitlines():
                lowered_line = line.casefold()
                if not re.search(r"\b\d{2,5}\s*(?:x|×|by)\s*\d{2,5}\b", line):
                    continue
                if not any(
                    token in lowered_line
                    for token in ("dimension", "dimensions", "resolution", "screen size", "framebuffer")
                ):
                    continue
                if any(
                    token in lowered_line
                    for token in ("actual", "different", "error", "failed", "mismatch", "not", "wrong")
                ):
                    continue
                if not any(
                    token in lowered_line for token in ("confirmed", "matches", "ok", "passed", "same", "verified")
                ):
                    continue
                preview = line.strip()
                if len(preview) > 120:
                    preview = preview[:117] + "..."
                if preview and preview not in previews:
                    previews.append(preview)
    artifacts = ", ".join(artifact_ids[:4])
    provider_call_id = str(result.provider_call_id or "").strip()
    pieces = [
        f"{provider_call_id or 'structured-final-verifier'} passed structured final verifier evidence",
        f"artifacts: {artifacts}",
    ]
    if previews:
        pieces.append("quality markers: " + ", ".join(previews[:4]))
    return "; ".join(pieces)


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


def _acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    session: dict[str, object] = {
        "tool_calls": [
            _acceptance_tool_call_from_result(index, result)
            for index, result in enumerate(tool_results, start=1)
        ]
    }
    typed_acceptance = _typed_acceptance_session_from_tool_results(tool_results, lane_input=lane_input)
    if typed_acceptance:
        session["typed_acceptance"] = typed_acceptance
    return session


def _typed_acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    events = []
    execution_contracts: list[dict[str, object]] = []
    verifier_evidence: list[dict[str, object]] = []
    artifact_evidence: list[dict[str, object]] = []
    source_grounding_refs: list[dict[str, object]] = []
    for index, result in enumerate(tool_results, start=1):
        payload = _first_result_payload(result)
        if not payload:
            continue
        events.extend(
            event.as_dict()
            for event in evidence_events_from_tool_payload(
                tool_index=index,
                tool_name=result.tool_name,
                tool_status=result.status,
                provider_call_id=result.provider_call_id,
                payload=payload,
            )
        )
        contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
        if isinstance(contract, dict):
            execution_contracts.append(dict(contract))
        verifier = payload.get("verifier_evidence")
        if isinstance(verifier, dict):
            verifier_evidence.append(dict(verifier))
        artifacts = payload.get("artifact_evidence")
        if isinstance(artifacts, list):
            artifact_evidence.extend(dict(item) for item in artifacts if isinstance(item, dict))
    if lane_input is not None:
        task_description = _live_task_description(lane_input)
        for requirement in implementation_contract_source_requirements(task_description):
            if isinstance(requirement, dict):
                source_grounding_refs.append(dict(requirement))
                source_ref = str(requirement.get("path") or "").strip()
                match = _source_grounding_tool_result(source_ref, tool_results)
                if match is not None:
                    tool_index, result = match
                    events.append(
                        {
                            "schema_version": 1,
                            "id": f"ev:source:{source_ref}:{result.provider_call_id or tool_index}",
                            "kind": "source_grounding",
                            "status": "passed",
                            "observed": {"path": source_ref, "grounded": True},
                            "refs": [{"kind": "tool_call", "id": tool_index}],
                            "provider_call_id": result.provider_call_id,
                        }
                    )
    task_contract = lane_input.task_contract if lane_input is not None and isinstance(lane_input.task_contract, dict) else {}
    oracle_bundle = build_oracle_bundle(
        task_contract=task_contract,
        execution_contracts=execution_contracts,
        verifier_evidence=verifier_evidence,
        artifact_evidence=artifact_evidence,
        source_grounding_refs=source_grounding_refs,
    )
    if not events and oracle_bundle is None:
        return {}
    typed: dict[str, object] = {
        "evidence_events": events,
        "digest": _typed_acceptance_digest(events, oracle_bundle.as_dict() if oracle_bundle is not None else {}),
    }
    if oracle_bundle is not None:
        typed["oracle_bundle"] = oracle_bundle.as_dict()
        typed["retired_legacy_blockers"] = _typed_retired_legacy_blockers_for_bundle(
            oracle_bundle.as_dict(),
            task_description=_live_task_description(lane_input) if lane_input is not None else "",
        )
    return typed


def _typed_retired_legacy_blockers_for_bundle(
    oracle_bundle: dict[str, object],
    *,
    task_description: object = "",
) -> list[str]:
    obligations = oracle_bundle.get("obligations") if isinstance(oracle_bundle, dict) else []
    if not isinstance(obligations, list) or not obligations:
        return []
    kinds = {
        str(obligation.get("kind") or "")
        for obligation in obligations
        if isinstance(obligation, dict)
    }
    retired: set[str] = set()
    visual_quality_covered = "visual_similarity" in kinds
    artifact_covered = bool(kinds.intersection({"artifact_exists", "artifact_fresh"}))
    if visual_quality_covered:
        retired.add("runtime_visual_artifact_quality_evidence")
    if artifact_covered and (visual_quality_covered or not is_runtime_visual_artifact_task(task_description)):
        retired.add("runtime_final_verifier_artifact_evidence")
    if "artifact_fresh" in kinds and (visual_quality_covered or not is_runtime_visual_artifact_task(task_description)):
        retired.add("runtime_artifact_freshness_unchecked")
    return sorted(retired)


def _typed_acceptance_digest(events: list[dict[str, object]], oracle_bundle: dict[str, object]) -> dict[str, object]:
    obligations = oracle_bundle.get("obligations") if isinstance(oracle_bundle, dict) else []
    missing = []
    if isinstance(obligations, list):
        event_text = "\n".join(str(event.get("id") or "") + "\n" + str(event.get("observed") or {}) for event in events)
        for obligation in obligations:
            if not isinstance(obligation, dict):
                continue
            obligation_id = str(obligation.get("id") or "")
            subject = str(obligation.get("subject") or "")
            if obligation_id and (obligation_id not in event_text and subject not in event_text):
                missing.append(obligation_id)
    return {
        "typed_evidence_event_count": len(events),
        "oracle_obligation_count": len(obligations) if isinstance(obligations, list) else 0,
        "missing_obligations": missing[:12],
        "evidence": [
            {
                "id": event.get("id"),
                "kind": event.get("kind"),
                "status": event.get("status"),
                "obligation_id": event.get("obligation_id"),
            }
            for event in events[:12]
            if isinstance(event, dict)
        ],
    }


def _typed_acceptance_metrics(
    typed_acceptance: dict[str, object],
    finish_gate_decision: dict[str, object],
) -> dict[str, object]:
    events = typed_acceptance.get("evidence_events") if isinstance(typed_acceptance, dict) else []
    bundle = typed_acceptance.get("oracle_bundle") if isinstance(typed_acceptance, dict) else {}
    obligations = bundle.get("obligations") if isinstance(bundle, dict) else []
    gate_source = str(finish_gate_decision.get("gate_source") or "")
    decision = str(finish_gate_decision.get("decision") or "")
    blockers = finish_gate_decision.get("blockers")
    return {
        "typed_evidence_event_count": len(events) if isinstance(events, list) else 0,
        "oracle_obligation_count": len(obligations) if isinstance(obligations, list) else 0,
        "typed_evidence_gate_block_count": 1 if gate_source == "typed_evidence" and decision == "block_continue" else 0,
        "missing_typed_evidence_count": _missing_typed_evidence_count(finish_gate_decision),
        "legacy_string_gate_block_count": 1 if gate_source != "typed_evidence" and decision == "block_continue" else 0,
        "model_claim_without_refs_count": _model_claim_without_refs_count(finish_gate_decision),
        "typed_coverage_gap_count": _typed_coverage_gap_count(blockers),
    }


def _missing_typed_evidence_count(finish_gate_decision: dict[str, object]) -> int:
    missing = finish_gate_decision.get("missing_obligations")
    if isinstance(missing, list):
        return len(missing)
    return 0


def _model_claim_without_refs_count(finish_gate_decision: dict[str, object]) -> int:
    blockers = finish_gate_decision.get("blockers")
    if not isinstance(blockers, list):
        return 0
    return sum(
        1
        for blocker in blockers
        if isinstance(blocker, dict)
        and str(blocker.get("code") or "").casefold() in {"missing_typed_evidence", "missing_evidence_ref"}
    )


def _typed_coverage_gap_count(blockers: object) -> int:
    if not isinstance(blockers, list):
        return 0
    return sum(
        1
        for blocker in blockers
        if isinstance(blocker, dict) and str(blocker.get("code") or "").casefold() == "typed_coverage_gap"
    )


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
    for key in (
        "execution_contract",
        "execution_contract_normalized",
        "artifact_evidence",
        "verifier_evidence",
        "command_run",
        "tool_run_record",
    ):
        value = primary.get(key)
        if value:
            result_payload[key] = value
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


def _call_model_turn(
    turn_input: ModelTurnInput,
    *,
    model_json_callable,
    model_auth: dict[str, object],
    base_url: str,
    progress=None,
) -> ModelTurnOutput:
    """Call the existing model_json transport behind a behavior-preserving boundary."""

    if progress:
        progress(f"implement_v2 turn #{turn_input.turn_index}: model_json start")
    started = time.monotonic()
    total_retry_count = 0
    transient_retry_count = 0
    parse_retry_count = 0
    current_turn_input = turn_input
    pending_delay = 0.0
    while True:
        delay = pending_delay
        pending_delay = 0.0
        if delay:
            time.sleep(delay)
        try:
            payload = model_json_callable(
                current_turn_input.model_backend,
                model_auth,
                current_turn_input.rendered_prompt,
                current_turn_input.model,
                base_url,
                current_turn_input.timeout_seconds,
                log_prefix=current_turn_input.log_prefix,
            )
            break
        except ModelBackendError as exc:
            elapsed = time.monotonic() - started
            model_error = _live_json_model_error(exc)
            if parse_retry_count == 0 and _live_json_parse_error_retryable(model_error):
                parse_retry_count += 1
                total_retry_count += 1
                retry_prompt = _append_live_json_parse_retry_instruction(turn_input.rendered_prompt, model_error)
                current_turn_input = replace(
                    turn_input,
                    rendered_prompt=retry_prompt,
                    prompt_descriptor=_prompt_descriptor(retry_prompt),
                )
                if progress:
                    progress(
                        f"implement_v2 turn #{turn_input.turn_index}: model_json parse failure "
                        f"retry={parse_retry_count}"
                    )
                continue
            should_retry = _live_json_model_error_retryable(model_error) and transient_retry_count < len(
                _IMPLEMENT_V2_TRANSIENT_MODEL_RETRY_DELAYS
            )
            if should_retry:
                pending_delay = _IMPLEMENT_V2_TRANSIENT_MODEL_RETRY_DELAYS[transient_retry_count]
                transient_retry_count += 1
                total_retry_count += 1
                if progress:
                    progress(
                        f"implement_v2 turn #{turn_input.turn_index}: model_json transient failure "
                        f"class={model_error.get('failure_class')} retry={transient_retry_count}"
                    )
                continue
            if total_retry_count:
                model_error["retry_count"] = total_retry_count
            if transient_retry_count:
                model_error["transient_retry_count"] = transient_retry_count
            if parse_retry_count:
                model_error["parse_retry_count"] = parse_retry_count
            if progress:
                progress(
                    f"implement_v2 turn #{turn_input.turn_index}: model_json failed "
                    f"class={model_error.get('failure_class')}"
            )
            response_shape = _model_response_shape({}, model_error=model_error)
            if total_retry_count:
                response_shape["retry_count"] = total_retry_count
            if transient_retry_count:
                response_shape["transient_retry_count"] = transient_retry_count
            if parse_retry_count:
                response_shape["parse_retry_count"] = parse_retry_count
            observation = _model_turn_observation(current_turn_input, {}, elapsed_seconds=elapsed, model_error=model_error)
            if total_retry_count:
                observation["model_retry_count"] = total_retry_count
            if transient_retry_count:
                observation["model_transient_retry_count"] = transient_retry_count
            if parse_retry_count:
                observation["model_parse_retry_count"] = parse_retry_count
            return ModelTurnOutput(
                payload={},
                normalized_payload={},
                elapsed_seconds=elapsed,
                prompt_chars=len(current_turn_input.rendered_prompt),
                response_shape=response_shape,
                model_error=model_error,
                observation=observation,
            )

    elapsed = time.monotonic() - started
    normalized = _normalize_live_json_payload(payload, turn_index=current_turn_input.turn_index)
    response_shape = _model_response_shape(normalized, model_error={})
    observation = _model_turn_observation(current_turn_input, normalized, elapsed_seconds=elapsed, model_error={})
    if total_retry_count:
        response_shape["retry_count"] = total_retry_count
        observation["model_retry_count"] = total_retry_count
    if transient_retry_count:
        response_shape["transient_retry_count"] = transient_retry_count
        observation["model_transient_retry_count"] = transient_retry_count
    if parse_retry_count:
        response_shape["parse_retry_count"] = parse_retry_count
        observation["model_parse_retry_count"] = parse_retry_count
    return ModelTurnOutput(
        payload=payload,
        normalized_payload=normalized,
        elapsed_seconds=elapsed,
        prompt_chars=len(current_turn_input.rendered_prompt),
        response_shape=response_shape,
        model_error={},
        observation=observation,
    )


def _model_turn_observation(
    turn_input: ModelTurnInput,
    normalized_payload: dict[str, object],
    *,
    elapsed_seconds: float,
    model_error: dict[str, object],
) -> dict[str, object]:
    """Build a serializable descriptor without raw prompt, history, or payload."""

    return {
        "schema_version": 1,
        "turn_id": turn_input.turn_id,
        "turn_index": turn_input.turn_index,
        "transport": turn_input.transport,
        "prompt": dict(turn_input.prompt_descriptor),
        "history_projection": dict(turn_input.projection_descriptor),
        "response": _model_response_shape(normalized_payload, model_error=model_error),
        "elapsed_seconds": round(elapsed_seconds, 3),
    }


def _model_response_shape(normalized_payload: dict[str, object], *, model_error: dict[str, object]) -> dict[str, object]:
    tool_calls = normalized_payload.get("tool_calls") if isinstance(normalized_payload, dict) else ()
    if not isinstance(tool_calls, (list, tuple)):
        tool_calls = ()
    finish = normalized_payload.get("finish") if isinstance(normalized_payload, dict) else {}
    frontier_update = normalized_payload.get("frontier_state_update") if isinstance(normalized_payload, dict) else {}
    return {
        "payload_kind": "model_error" if model_error else "object",
        "tool_call_count": len(tool_calls),
        "tool_names": [
            str(call.get("tool_name") or call.get("name") or "")
            for call in tool_calls
            if isinstance(call, dict) and str(call.get("tool_name") or call.get("name") or "")
        ],
        "has_finish": bool(finish),
        "finish_outcome": str(finish.get("outcome") or "") if isinstance(finish, dict) else "",
        "frontier_update_keys": sorted(str(key) for key in frontier_update) if isinstance(frontier_update, dict) else [],
        "model_error_class": str(model_error.get("failure_class") or "") if model_error else "",
    }


def _prompt_descriptor(prompt: str) -> dict[str, object]:
    return {"chars": len(prompt), "sha256": _sha256_text(prompt)}


def _current_projection_descriptor(prompt_history: tuple[dict[str, object], ...] | list[dict[str, object]]) -> dict[str, object]:
    projection = _render_prompt_history_json(prompt_history)
    projection_sha256 = _sha256_text(projection)
    projection_chars = len(projection)
    return {
        "current_projection_schema": "provider_history_projection_v0",
        "current_projection_sha256": projection_sha256,
        "current_projection_chars": projection_chars,
        "future_projection_schema": "provider_history_projection_candidate_v0",
        "future_projection_sha256": projection_sha256,
        "future_projection_chars": projection_chars,
        "future_projection_mode": "identity",
        "diff_summary": {
            "changed": False,
            "omitted_large_outputs": 0,
            "truncated_fields": [],
            "preserved_refs": [],
        },
        "history_turns_included": len(list(prompt_history)[-8:]),
    }


def _render_prompt_history_json(prompt_history: tuple[dict[str, object], ...] | list[dict[str, object]]) -> str:
    """Render the exact history_json bytes used by _live_json_prompt."""

    return json.dumps(list(prompt_history)[-8:], ensure_ascii=False, indent=2)


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _integration_observation_summary(
    lane_input: ImplementLaneInput,
    *,
    lane_attempt_id: str,
    artifact_namespace: str,
    transport: str,
    model_turn_observations: tuple[dict[str, object], ...],
    model_elapsed_seconds: float,
    artifact_ref: str = "",
) -> dict[str, object]:
    prompt_chars = 0
    tool_call_count = 0
    turns_with_model_error = 0
    current_projection_chars_total = 0
    future_projection_chars_total = 0
    for observation in model_turn_observations:
        prompt = observation.get("prompt") if isinstance(observation.get("prompt"), dict) else {}
        response = observation.get("response") if isinstance(observation.get("response"), dict) else {}
        projection = (
            observation.get("history_projection") if isinstance(observation.get("history_projection"), dict) else {}
        )
        prompt_chars += _nonnegative_int(prompt.get("chars"))
        tool_call_count += _nonnegative_int(response.get("tool_call_count"))
        if response.get("model_error_class"):
            turns_with_model_error += 1
        current_projection_chars_total += _nonnegative_int(projection.get("current_projection_chars"))
        future_projection_chars_total += _nonnegative_int(projection.get("future_projection_chars"))
    projection_savings_chars = current_projection_chars_total - future_projection_chars_total
    projection_savings_ratio = (
        round(projection_savings_chars / current_projection_chars_total, 6) if current_projection_chars_total > 0 else 0.0
    )
    return {
        "schema_version": 1,
        "runtime_id": "implement_v2_model_json_tool_loop",
        "transport": transport,
        "lane_attempt_id": lane_attempt_id,
        "artifact_namespace": artifact_namespace,
        "detail_policy": "sidecar" if artifact_ref else "summary",
        "artifact_ref": artifact_ref,
        "summary": {
            "model_turns": len(model_turn_observations),
            "prompt_chars": prompt_chars,
            "model_elapsed_seconds": round(model_elapsed_seconds, 3),
            "tool_call_count": tool_call_count,
            "turns_with_projection_truncation": 0,
            "turns_with_model_error": turns_with_model_error,
            "current_projection_chars_total": current_projection_chars_total,
            "future_projection_chars_total": future_projection_chars_total,
            "projection_savings_chars": projection_savings_chars,
            "projection_savings_ratio": projection_savings_ratio,
            "detail_written": bool(artifact_ref),
            "state_safe": True,
        },
        "state_note": "summary_only; full per-turn detail is never persisted in updated_lane_state",
        "debug_detail_enabled": _should_write_integration_observation_detail(lane_input),
    }


def _integration_observation_detail_payload(
    manifest: ImplementLaneProofManifest,
    model_turn_observations: tuple[dict[str, object], ...],
) -> dict[str, object]:
    summary = manifest.metrics.get("integration_observation")
    if isinstance(summary, dict):
        totals = dict(summary.get("summary") if isinstance(summary.get("summary"), dict) else {})
    else:
        totals = {}
    return {
        "schema_version": 1,
        "runtime_id": "implement_v2_model_json_tool_loop",
        "transport": str(manifest.metrics.get("transport") or ""),
        "lane_attempt_id": manifest.lane_attempt_id,
        "artifact_namespace": manifest.artifact_namespace,
        "turns": [dict(observation) for observation in model_turn_observations],
        "totals": totals,
    }


def _should_write_integration_observation_detail(lane_input: ImplementLaneInput) -> bool:
    value = lane_input.lane_config.get("write_integration_observation_detail")
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "on"}


def _nonnegative_int(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, number)


def _write_live_json_artifacts(
    lane_input: ImplementLaneInput,
    *,
    manifest: ImplementLaneProofManifest,
    transcript: tuple[ImplementLaneTranscriptEvent, ...],
    history: tuple[dict[str, object], ...],
    integration_observation_detail: tuple[dict[str, object], ...] = (),
) -> tuple[str, ...]:
    artifact_dir = str(lane_input.lane_config.get("artifact_dir") or "").strip()
    if not artifact_dir:
        return ()
    root = Path(artifact_dir).expanduser().resolve(strict=False) / "implement_v2"
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "proof-manifest.json"
    transcript_path = root / "transcript.json"
    history_path = root / "history.json"
    integration_observation_path = root / "integration-observation.json"
    manifest_path.write_text(json.dumps(manifest.as_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    transcript_path.write_text(
        json.dumps([event.as_dict() for event in transcript], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    history_path.write_text(json.dumps(list(history), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths = [str(manifest_path), str(transcript_path), str(history_path)]
    if _should_write_integration_observation_detail(lane_input):
        integration_observation_path.write_text(
            json.dumps(
                _integration_observation_detail_payload(manifest, integration_observation_detail),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        paths.append(str(integration_observation_path))
    return tuple(paths)


__all__ = [
    "describe_implement_v2_runtime",
    "run_live_json_implement_v2",
    "run_fake_exec_implement_v2",
    "run_fake_read_only_implement_v2",
    "run_fake_write_implement_v2",
    "run_unavailable_implement_v2",
]
