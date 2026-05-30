"""Native finish closeout policy state and small policy adapters."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Mapping

from . import finish_verifier_planner as _finish_planner
from .exec_runtime import EXEC_TOOL_NAMES
from .native_finish_gate import NativeFinishGateDecision
from .native_transcript import NativeTranscriptItem
from .tool_registry import build_tool_surface_snapshot
from .tool_routes import with_tool_route_decision
from .types import ToolCallEnvelope, ToolResultEnvelope


NG_CONTINUE_CONSECUTIVE_LIMIT = 2
NG_DECISION_TOTAL_LIMIT = 3
FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS = 1.0
NATIVE_MODEL_TIMEOUT_RESERVE_SECONDS = 10.0
NATIVE_MODEL_TIMEOUT_MIN_SECONDS = 30.0
SOURCE_MUTATION_COMMAND_INTENTS = frozenset(
    {"implement", "implementation", "write", "edit", "mutation", "source_mutation"}
)
EXPLICIT_ACCEPTANCE_PASS_RE = re.compile(
    r"(?im)^\s*(?:acceptance:\s*pass|acceptance_ok|final_acceptance_ok)\b"
)
SEMANTIC_VERIFIER_FAILURE_PATTERNS = (
    re.compile(r"\bvm\s+(?:finished|stopped)\s+exit=(?!0\b)\d+\b", re.IGNORECASE),
    re.compile(r"\bmissing\s+expected\s+(?:artifact|frame|output)\b", re.IGNORECASE),
    re.compile(
        r"\bexpected\s+(?:artifact|frame|output)\s+(?:missing|not\s+found|not\s+created|not\s+produced)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bno\s+(?:artifact|frame|output)\s+produced\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class NativeCloseoutEvent:
    kind: str
    call: object
    result: object
    latency: dict[str, object]
    reason: str


@dataclass(frozen=True)
class NativeCloseoutContext:
    closeout_refs: tuple[str, ...] = ()
    fresh_verifier_refs: tuple[str, ...] = ()
    planner_verified_finish_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    unsafe_blockers: tuple[str, ...] = ()
    budget_blockers: tuple[str, ...] = ()

    def merge(self, other: "NativeCloseoutContext") -> "NativeCloseoutContext":
        return NativeCloseoutContext(
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


def run_finish_time_closeouts(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: object,
    workspace: Path,
    allowed_read_roots: tuple[str, ...],
    allowed_write_roots: tuple[str, ...],
    lane_config: Mapping[str, object],
    tool_calls: tuple[object, ...],
    tool_results: tuple[object, ...],
    start_monotonic: float,
    done_candidate_id: str = "",
) -> tuple[tuple[NativeCloseoutEvent, ...], NativeCloseoutContext]:
    events: list[NativeCloseoutEvent] = []
    context = NativeCloseoutContext()
    scoped_calls = list(tool_calls)
    scoped_results = list(tool_results)

    def append_active_closeouts(reason: str) -> None:
        nonlocal context
        for active_call, active_result, active_latency in native_active_command_closeouts(
            lane_input,
            lane_attempt_id=lane_attempt_id,
            provider=provider,
            exec_runtime=exec_runtime,
            start_monotonic=start_monotonic,
        ):
            events.append(
                NativeCloseoutEvent(
                    kind="active_command",
                    call=active_call,
                    result=active_result,
                    latency=active_latency,
                    reason=reason,
                )
            )
            context = context.merge(native_closeout_context_from_result(active_call, active_result))

    source_roots = native_source_mutation_roots(lane_input, workspace)
    pending_mutation = latest_native_source_mutation_without_later_verifier(
        tuple(scoped_calls),
        tuple(scoped_results),
        source_mutation_roots=source_roots,
    )
    latest_mutation = pending_mutation or latest_native_source_mutation(
        tuple(scoped_calls),
        tuple(scoped_results),
        source_mutation_roots=source_roots,
    )
    if not latest_mutation:
        append_active_closeouts("native active command closeout ran during finish-time resolver evidence collection")
        return tuple(events), context
    no_run_context = native_final_verifier_closeout_no_run_context(
        lane_input,
        provider=provider,
        tool_results=tuple(scoped_results),
        lane_config=lane_config,
        start_monotonic=start_monotonic,
    )
    if no_run_context is not None:
        append_active_closeouts("native active command closeout ran during finish-time resolver evidence collection")
        return tuple(events), context.merge(no_run_context)

    closeout = native_final_verifier_closeout(
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
        done_candidate_id=done_candidate_id,
    )
    if closeout is None:
        append_active_closeouts("native active command closeout ran during finish-time resolver evidence collection")
        return tuple(events), context.merge(
            NativeCloseoutContext(
                blockers=("closeout_verifier_not_run",),
                missing_obligations=("strict_verifier_evidence",),
            )
        )
    closeout_call, closeout_result, closeout_latency = closeout
    events.append(
        NativeCloseoutEvent(
            kind="final_verifier",
            call=closeout_call,
            result=closeout_result,
            latency=closeout_latency,
            reason="native final verifier closeout ran during finish-time resolver evidence collection",
        )
    )
    closeout_context = native_closeout_context_from_result(closeout_call, closeout_result)
    if closeout_context.fresh_verifier_refs:
        return tuple(events), context.merge(closeout_context)
    append_active_closeouts("native active command closeout ran after final verifier evidence was inconclusive")
    return tuple(events), context.merge(closeout_context)


def native_closeout_context_from_result(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
) -> NativeCloseoutContext:
    refs = native_closeout_refs(call, result)
    if native_final_verifier_passed(result):
        return NativeCloseoutContext(
            closeout_refs=refs,
            fresh_verifier_refs=refs,
            planner_verified_finish_refs=refs if native_call_uses_finish_verifier_planner(call) else (),
        )
    payload = native_result_payload(result)
    status = str(payload.get("status") or result.status or "").casefold()
    reason_text = result.natural_result_text().casefold()
    if status in {"interrupted", "timeout", "timed_out", "yielded"} or "budget" in reason_text:
        return NativeCloseoutContext(
            closeout_refs=refs,
            budget_blockers=("closeout_verifier_budget_or_timeout",),
            missing_obligations=("strict_verifier_evidence",),
        )
    return NativeCloseoutContext(
        closeout_refs=refs,
        blockers=("closeout_verifier_failed",),
        missing_obligations=("strict_verifier_evidence",),
    )


def native_closeout_refs(call: NativeTranscriptItem, result: ToolResultEnvelope) -> tuple[str, ...]:
    refs = tuple(ref for ref in result.evidence_refs if native_closeout_ref_is_completion_evidence(ref))
    if refs:
        return refs
    return (f"native-closeout://{call.call_id}",)


def native_call_uses_finish_verifier_planner(call: NativeTranscriptItem) -> bool:
    arguments, error = arguments_from_native_call(call)
    if error:
        return False
    plan = arguments.get("finish_verifier_plan")
    if not isinstance(plan, Mapping):
        return False
    return str(plan.get("source") or "").strip() == "finish_verifier_planner"


def native_closeout_ref_is_completion_evidence(value: object) -> bool:
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


def native_active_command_closeouts(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: object,
    start_monotonic: float,
) -> tuple[tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]], ...]:
    closeouts: list[tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]]] = []
    closeout_index = 0
    while native_active_command_run_id(exec_runtime):
        closeout = native_active_command_closeout(
            lane_input,
            lane_attempt_id=lane_attempt_id,
            provider=provider,
            exec_runtime=exec_runtime,
            start_monotonic=start_monotonic,
            closeout_index=closeout_index,
        )
        if closeout is None:
            break
        closeouts.append(closeout)
        closeout_index += 1
    return tuple(closeouts)


def native_active_command_closeout(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: object,
    start_monotonic: float,
    closeout_index: int = 0,
) -> tuple[NativeTranscriptItem, ToolResultEnvelope, dict[str, object]] | None:
    command_run_id = native_active_command_run_id(exec_runtime)
    if not command_run_id:
        return None
    budget = native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    turn_index = len(getattr(provider, "requests", []) or ()) + 1
    call = native_active_command_closeout_call(
        lane_input,
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        turn_index=turn_index,
        command_run_id=command_run_id,
        timeout_seconds=budget,
        closeout_index=closeout_index,
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
    if budget < FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        payload = exec_runtime.cancel_command(
            command_run_id,
            reason="native active command closeout budget exhausted before deterministic final verifier",
        )
    else:
        payload = exec_runtime.finalize_command(command_run_id, timeout_seconds=budget)
    result = with_tool_route_decision(
        tool_call_envelope_from_native_call(call, {"command_run_id": command_run_id}),
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


def native_active_command_run_id(exec_runtime: object) -> str:
    active = getattr(getattr(exec_runtime, "runner", None), "active", None)
    return str(getattr(active, "command_run_id", "") or "").strip()


def native_active_command_closeout_call(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    command_run_id: str,
    timeout_seconds: float,
    closeout_index: int = 0,
) -> NativeTranscriptItem:
    suffix = f"-{closeout_index + 1}" if closeout_index else ""
    call_id = f"call-active-command-closeout-{turn_index:03d}{suffix}"
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
        model=str(getattr(provider, "model", "") or getattr(lane_input, "model", "") or ""),
        response_id=f"native-active-command-closeout-{turn_index}{suffix}",
        provider_item_id=f"item-{call_id}",
        output_index=0,
        kind="function_call",
        call_id=call_id,
        tool_name="poll_command",
        arguments_json_text=json.dumps(arguments, sort_keys=True),
    )


def native_final_verifier_closeout_no_run_context(
    lane_input: object,
    *,
    provider: object,
    tool_results: tuple[ToolResultEnvelope, ...],
    lane_config: Mapping[str, object],
    start_monotonic: float,
) -> NativeCloseoutContext | None:
    if not native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return NativeCloseoutContext(
            unsafe_blockers=("closeout_verifier_not_permitted",),
            missing_obligations=("strict_verifier_evidence",),
        )
    has_configured = bool(configured_native_final_verifier_command(lane_input))
    has_planner = _finish_planner.native_finish_verifier_planner_can_run(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    )
    has_auto = auto_detected_native_final_verifier_command(lane_input) is not None
    if not has_configured and not has_planner and not has_auto:
        return NativeCloseoutContext(
            blockers=("closeout_verifier_command_missing",),
            missing_obligations=("strict_verifier_evidence",),
        )
    budget = native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    if budget < FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        return NativeCloseoutContext(
            budget_blockers=("closeout_verifier_budget_insufficient",),
            missing_obligations=("strict_verifier_evidence",),
        )
    return None


def native_final_verifier_closeout(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    exec_runtime: object,
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
    effective_mutation = dict(pending_mutation or {})
    if not effective_mutation:
        effective_mutation = latest_native_source_mutation_without_later_verifier(
            tool_calls,
            tool_results,
            source_mutation_roots=native_source_mutation_roots(lane_input, workspace),
        )
    if not effective_mutation:
        effective_mutation = latest_native_source_mutation(
            tool_calls,
            tool_results,
            source_mutation_roots=native_source_mutation_roots(lane_input, workspace),
        )
    if not effective_mutation:
        return None
    if not native_final_verifier_closeout_allowed(lane_input, lane_config=lane_config):
        return None
    plan = native_final_verifier_closeout_plan(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
        done_candidate_id=done_candidate_id,
    )
    if plan is None:
        return None
    budget = native_final_verifier_closeout_budget_seconds(lane_input, run_started=start_monotonic)
    if budget < FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS:
        return None
    turn_index = len(getattr(provider, "requests", []) or ()) + 1
    call = native_final_verifier_closeout_call(
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
    result = execute_native_closeout_call(
        call,
        lane_input=lane_input,
        workspace=workspace,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        lane_config=lane_config,
        exec_runtime=exec_runtime,
    )
    if result.status == "yielded":
        command_run_id = command_run_id_from_result(result)
        if command_run_id:
            payload = exec_runtime.finalize_command(command_run_id, timeout_seconds=budget)
            result = with_tool_route_decision(
                tool_call_envelope_from_native_call(call, arguments_from_native_call(call)[0]),
                exec_runtime.project_result_payload(result, payload),
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


def native_final_verifier_closeout_allowed(
    lane_input: object,
    *,
    lane_config: Mapping[str, object],
) -> bool:
    if not bool(lane_config.get("allow_verify")):
        return False
    if not bool(lane_config.get("allow_shell") or lane_config.get("run_command_available")):
        return False
    return bool(getattr(lane_input, "workspace", "")) and bool(
        native_final_verifier_tool_name(lane_input, lane_config=lane_config)
    )


def native_final_verifier_tool_name(
    lane_input: object,
    *,
    lane_config: Mapping[str, object],
) -> str:
    for candidate in ("exec_command", "run_command"):
        if native_tool_available(candidate, lane_input=lane_input, lane_config=lane_config):
            return candidate
    return ""


def native_tool_available(
    tool_name: object,
    *,
    lane_input: object,
    lane_config: Mapping[str, object],
) -> bool:
    try:
        snapshot = build_tool_surface_snapshot(
            lane_config=lane_config,
            task_contract=getattr(lane_input, "task_contract", {}),
            transcript_items=(),
            available_provider_tool_names=(str(tool_name or ""),),
        )
    except ValueError:
        return False
    return str(tool_name or "") in set(snapshot.provider_tool_names)


def canonical_native_verify_command_source(value: object, *, default: str = "") -> str:
    text = str(value or "").strip().casefold()
    if text in {"auto", "auto_detected", "auto-detected", "auto_detected_verifier"}:
        return "auto_detected_verifier"
    if text in {"explicit", "configured", "configured_verifier", "manual", "user", "cli", "task", "task_contract"}:
        return "configured_verifier"
    return default


def native_final_verifier_command_candidate(
    lane_input: object,
    *,
    wanted_source: str,
) -> _finish_planner.FinishVerifierPlan | None:
    lane_config = getattr(lane_input, "lane_config", {}) or {}
    task_contract = getattr(lane_input, "task_contract", {}) or {}
    lane_command = str(lane_config.get("verify_command") or "").strip()
    lane_source = canonical_native_verify_command_source(
        lane_config.get("verify_command_source"),
        default="configured_verifier" if lane_command else "",
    )
    for source_ref, source in (("lane_config.verify_command", lane_config), ("task_contract.verify_command", task_contract)):
        command = str((source or {}).get("verify_command") or "").strip()
        if not command:
            continue
        command_source = canonical_native_verify_command_source(
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
        return _finish_planner.FinishVerifierPlan(
            command=command,
            source=command_source,
            raw={"source_ref": source_ref, "verify_command_source": command_source},
        )
    return None


def configured_native_final_verifier_command(lane_input: object) -> str:
    candidate = native_final_verifier_command_candidate(lane_input, wanted_source="configured_verifier")
    return candidate.command if candidate else ""


def auto_detected_native_final_verifier_command(lane_input: object) -> _finish_planner.FinishVerifierPlan | None:
    return native_final_verifier_command_candidate(lane_input, wanted_source="auto_detected_verifier")


def native_final_verifier_closeout_plan(
    lane_input: object,
    *,
    provider: object,
    lane_config: Mapping[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    done_candidate_id: str = "",
) -> _finish_planner.FinishVerifierPlan | None:
    configured = native_final_verifier_command_candidate(lane_input, wanted_source="configured_verifier")
    if configured is not None:
        return configured
    if not _finish_planner.native_finish_verifier_planner_can_run(
        lane_input,
        provider=provider,
        lane_config=lane_config,
        tool_results=tool_results,
    ):
        return auto_detected_native_final_verifier_command(lane_input)
    loop_request = _finish_planner.build_finish_verifier_planner_loop_request(
        lane_input,
        lane_config=lane_config,
        tool_results=tool_results,
        done_candidate_id=done_candidate_id,
    )
    request_hash = _finish_planner.finish_verifier_planner_request_hash(loop_request.as_planner_request())
    loop_result = _finish_planner.run_finish_verifier_planner_loop(
        loop_request,
        planner_provider=provider,
    )
    if loop_result.status == "error":
        fallback, fallback_rejection = safe_auto_detected_finish_verifier_fallback(
            lane_input,
            request=loop_request.as_planner_request(),
        )
        decision = dict(loop_result.record)
        decision.setdefault("status", "error")
        decision.setdefault("request_hash", request_hash)
        if fallback is not None:
            decision["fallback"] = _finish_planner.finish_verifier_plan_payload(fallback)
            decision["fallback_source"] = fallback.source
        elif fallback_rejection:
            decision["fallback_rejection"] = dict(fallback_rejection)
        else:
            decision.setdefault("fallback", {})
            decision.setdefault("fallback_source", "")
        _finish_planner.record_finish_verifier_planner_decision(provider, decision)
        emit_progress(
            getattr(provider, "progress", None),
            f"finish_verifier_planner failed: {loop_result.reason or 'unknown'}; "
            f"fallback={_finish_planner.finish_verifier_plan_source(fallback)}",
        )
        return _finish_planner.finish_verifier_plan_with_planner_fallback(fallback, decision)
    if loop_result.status == "selected" and loop_result.plan is not None:
        _finish_planner.record_finish_verifier_planner_decision(provider, loop_result.record)
        return loop_result.plan
    fallback, fallback_rejection = safe_auto_detected_finish_verifier_fallback(
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
        decision["fallback"] = _finish_planner.finish_verifier_plan_payload(fallback)
        decision["fallback_source"] = fallback.source
    elif fallback_rejection:
        decision["fallback_rejection"] = dict(fallback_rejection)
    else:
        decision.setdefault("fallback", {})
        decision.setdefault("fallback_source", "")
    _finish_planner.record_finish_verifier_planner_decision(provider, decision)
    emit_progress(
        getattr(provider, "progress", None),
        "finish_verifier_planner rejected plan: "
        f"{loop_result.reason or 'unknown'}; fallback={_finish_planner.finish_verifier_plan_source(fallback)}",
    )
    return _finish_planner.finish_verifier_plan_with_planner_fallback(fallback, decision)


def safe_auto_detected_finish_verifier_fallback(
    lane_input: object,
    *,
    request: Mapping[str, object],
) -> tuple[_finish_planner.FinishVerifierPlan | None, Mapping[str, object] | None]:
    fallback = auto_detected_native_final_verifier_command(lane_input)
    if fallback is None:
        return None, None
    safety = _finish_planner.finish_verifier_command_safety(
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


def native_final_verifier_closeout_budget_seconds(
    lane_input: object,
    *,
    run_started: float,
) -> float:
    remaining = native_remaining_wall_budget_seconds(lane_input, run_started=run_started)
    lane_config = getattr(lane_input, "lane_config", {}) or {}
    if remaining is None:
        remaining = float(lane_config.get("final_verifier_closeout_seconds") or 60.0)
    configured = lane_config.get("final_verifier_closeout_seconds")
    if configured not in (None, ""):
        try:
            remaining = min(remaining, max(0.0, float(configured)))
        except (TypeError, ValueError):
            return 0.0
    return max(0.0, min(3600.0, remaining))


def native_remaining_wall_budget_seconds(lane_input: object, *, run_started: float) -> float | None:
    task_contract = getattr(lane_input, "task_contract", {}) or {}
    max_wall = task_contract.get("max_wall_seconds")
    if max_wall in (None, ""):
        return None
    try:
        remaining = float(max_wall) - max(0.0, time.monotonic() - run_started)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(600.0, remaining))


def native_next_model_timeout_seconds(
    lane_input: object,
    *,
    run_started: float,
    requested_timeout: object,
) -> float | None:
    remaining = native_remaining_wall_budget_seconds(lane_input, run_started=run_started)
    if remaining is None:
        return None
    try:
        requested = float(requested_timeout) if requested_timeout not in (None, "") else remaining
    except (TypeError, ValueError):
        requested = remaining
    if requested <= 0:
        return requested
    reserve = min(
        NATIVE_MODEL_TIMEOUT_RESERVE_SECONDS,
        max(0.0, remaining - NATIVE_MODEL_TIMEOUT_MIN_SECONDS),
    )
    available = remaining - reserve
    return max(0.0, min(requested, available))


def native_final_verifier_closeout_call(
    lane_input: object,
    *,
    lane_attempt_id: str,
    provider: object,
    turn_index: int,
    lane_config: Mapping[str, object],
    plan: _finish_planner.FinishVerifierPlan,
    timeout_seconds: float,
    pending_mutation: Mapping[str, object],
) -> NativeTranscriptItem:
    call_id = f"call-final-verifier-closeout-{turn_index:03d}"
    arguments = {
        "command": plan.command,
        "cwd": plan.cwd or ".",
        "use_shell": True,
        "controller_closeout": True,
        "timeout": round(max(FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
        "foreground_budget_seconds": round(max(FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds), 3),
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
    tool_name = native_final_verifier_tool_name(lane_input, lane_config=lane_config) or "run_command"
    if tool_name == "exec_command":
        arguments = {
            **arguments,
            "cmd": plan.command,
            "timeout_ms": int(round(max(FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds) * 1000)),
            "yield_time_ms": int(round(max(FINAL_VERIFIER_CLOSEOUT_MIN_SECONDS, timeout_seconds) * 1000)),
        }
    return NativeTranscriptItem(
        sequence=0,
        turn_id=f"turn-{turn_index}-final-verifier-closeout",
        lane_attempt_id=lane_attempt_id,
        provider=str(getattr(provider, "provider", "") or "native-controller"),
        model=str(getattr(provider, "model", "") or getattr(lane_input, "model", "") or ""),
        response_id=f"native-final-verifier-closeout-{turn_index}",
        provider_item_id=f"fc_mew_final_verifier_closeout_{turn_index:03d}",
        output_index=0,
        kind="function_call",
        call_id=call_id,
        tool_name=tool_name,
        arguments_json_text=json.dumps(arguments, sort_keys=True),
    )


def execute_native_closeout_call(
    call: NativeTranscriptItem,
    *,
    lane_input: object,
    workspace: Path,
    allowed_read_roots: tuple[str, ...],
    allowed_write_roots: tuple[str, ...],
    lane_config: Mapping[str, object],
    exec_runtime: object,
) -> ToolResultEnvelope:
    del workspace, allowed_read_roots, allowed_write_roots, lane_config
    arguments, error = arguments_from_native_call(call)
    if error:
        return invalid_closeout_result(call, reason=error)
    provider_envelope = tool_call_envelope_from_native_call(call, arguments)
    adapted_call, adapted_arguments = adapt_closeout_call(call, arguments, lane_input=lane_input)
    envelope = provider_envelope
    if adapted_call is not call or adapted_arguments != arguments:
        envelope = tool_call_envelope_from_native_call(adapted_call, adapted_arguments)
    if adapted_call.tool_name not in EXEC_TOOL_NAMES:
        return with_tool_route_decision(
            provider_envelope,
            invalid_closeout_result(call, reason=f"unknown native closeout tool: {call.tool_name}"),
        )
    result = result_with_provider_tool_name(
        exec_runtime.execute(envelope),
        provider_tool_name=call.tool_name,
        internal_tool_name=adapted_call.tool_name,
    )
    return with_tool_route_decision(
        provider_envelope,
        result,
        effective_tool=adapted_call.tool_name,
    )


def adapt_closeout_call(
    call: NativeTranscriptItem,
    arguments: Mapping[str, object],
    *,
    lane_input: object,
) -> tuple[NativeTranscriptItem, dict[str, object]]:
    if call.tool_name != "exec_command":
        return call, dict(arguments)
    mapped = dict(arguments)
    if mapped.get("command") in (None, "") and mapped.get("cmd") not in (None, ""):
        mapped["command"] = mapped["cmd"]
    if mapped.get("cwd") in (None, "") and mapped.get("workdir") not in (None, ""):
        mapped["cwd"] = mapped["workdir"]
    if mapped.get("foreground_budget_seconds") in (None, "") and mapped.get("yield_time_ms") not in (None, ""):
        mapped["foreground_budget_seconds"] = max(
            0.0,
            safe_float(mapped.get("yield_time_ms"), default=0.0) / 1000.0,
        )
    if matches_verify_command(mapped, lane_input=lane_input):
        mapped.setdefault("command_intent", "verify")
    return replace(call, tool_name="run_command"), mapped


def result_with_provider_tool_name(
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


def invalid_closeout_result(call: NativeTranscriptItem, *, reason: str) -> ToolResultEnvelope:
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name=call.tool_name,
        status="invalid",
        is_error=True,
        content=({"reason": reason},),
    )


def tool_call_envelope_from_native_call(
    call: NativeTranscriptItem,
    arguments: Mapping[str, object],
) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        provider_call_id=call.call_id,
        mew_tool_call_id=f"native:{call.call_id}",
        tool_name=call.tool_name,
        arguments=dict(arguments),
        provider_message_id=call.provider_item_id,
        turn_index=turn_number(call.turn_id),
        sequence_index=call.output_index,
        status="validated",
    )


def arguments_from_native_call(call: NativeTranscriptItem) -> tuple[dict[str, object], str]:
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


def matches_verify_command(args: Mapping[str, object], *, lane_input: object) -> bool:
    lane_config = getattr(lane_input, "lane_config", {}) or {}
    task_contract = getattr(lane_input, "task_contract", {}) or {}
    verify_command = str(
        lane_config.get("verify_command")
        or task_contract.get("verify_command")
        or ""
    ).strip()
    if not verify_command:
        return False
    command = str(args.get("command") or args.get("cmd") or "").strip()
    return command == verify_command


def safe_float(value: object, *, default: float) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def turn_number(turn_id: str) -> int:
    try:
        return int(str(turn_id).rsplit("-", 1)[-1])
    except ValueError:
        return 0


def native_finish_supplied_closeout_context(
    refs: tuple[str, ...],
    prior_tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...] = (),
) -> NativeCloseoutContext:
    cited_refs = tuple(dict.fromkeys(str(ref or "").strip() for ref in refs if str(ref or "").strip()))
    if not cited_refs:
        return NativeCloseoutContext()
    completion_refs: list[str] = []
    latest_mutation_index = latest_native_source_mutation_result_index(
        prior_tool_results,
        source_mutation_roots=source_mutation_roots,
    )
    for index, result in enumerate(prior_tool_results, start=1):
        if latest_mutation_index and index < latest_mutation_index:
            continue
        if not native_prior_result_can_satisfy_verifier_evidence(result):
            continue
        result_completion_refs = native_completion_refs_from_result(result)
        if not result_completion_refs:
            continue
        if native_finish_refs_cite_tool_result(cited_refs, result, result_completion_refs):
            completion_refs.extend(result_completion_refs)
    refs_tuple = tuple(dict.fromkeys(completion_refs))
    if not refs_tuple:
        return NativeCloseoutContext()
    return NativeCloseoutContext(
        closeout_refs=refs_tuple,
        fresh_verifier_refs=refs_tuple,
    )


def latest_native_source_mutation_result_index(
    prior_tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> int:
    latest = 0
    for index, result in enumerate(prior_tool_results, start=1):
        if result.status == "completed" and native_result_has_source_mutation(
            result,
            source_mutation_roots=source_mutation_roots,
        ):
            latest = index
    return latest


def native_prior_result_can_satisfy_verifier_evidence(result: ToolResultEnvelope) -> bool:
    verifier_passed = native_final_verifier_passed(result)
    explicit_acceptance_pass = native_result_has_explicit_acceptance_pass(result)
    if not verifier_passed and not explicit_acceptance_pass:
        return False
    payload = native_result_payload(result)
    verifier = payload.get("verifier_evidence")
    if isinstance(verifier, Mapping):
        verdict = str(verifier.get("verdict") or "").casefold()
        if verdict == "pass":
            return True
        if verdict in {"fail", "failed", "partial"}:
            return False
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    if native_execution_contract_is_verifier_like(contract):
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
        and native_result_has_verifier_evidence_ref(result)
        and native_result_is_process_lifecycle_continuation(result)
    ):
        return True
    return False


def native_completion_refs_from_result(result: ToolResultEnvelope) -> tuple[str, ...]:
    refs = (*result.content_refs, *result.evidence_refs)
    return tuple(ref for ref in refs if native_closeout_ref_is_completion_evidence(ref))


def native_result_has_explicit_acceptance_pass(result: ToolResultEnvelope) -> bool:
    payload = native_result_payload(result)
    if result.status != "completed" or result.is_error:
        return False
    if payload.get("exit_code") not in (0, "0"):
        return False
    for key in ("stdout_tail", "stdout", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and EXPLICIT_ACCEPTANCE_PASS_RE.search(value):
            return True
    return False


def native_result_has_verifier_evidence_ref(result: ToolResultEnvelope) -> bool:
    refs = " ".join(str(ref or "") for ref in (*result.content_refs, *result.evidence_refs)).casefold()
    return "verifier_evidence" in refs or "/verifier/" in refs


def native_result_is_process_lifecycle_continuation(result: ToolResultEnvelope) -> bool:
    payload = native_result_payload(result)
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


def native_finish_refs_cite_tool_result(
    refs: tuple[str, ...],
    result: ToolResultEnvelope,
    result_completion_refs: tuple[str, ...],
) -> bool:
    aliases = native_tool_result_ref_aliases(result)
    result_ref_set = set(result_completion_refs)
    for ref in refs:
        if ref in aliases or ref in result_ref_set:
            return True
    return False


def native_tool_result_ref_aliases(result: ToolResultEnvelope) -> set[str]:
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


def latest_native_source_mutation_without_later_verifier(
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> dict[str, object]:
    latest_mutation = latest_native_source_mutation(
        tool_calls,
        tool_results,
        source_mutation_roots=source_mutation_roots,
    )
    latest_verifier_index = 0
    verifier_command_run_ids: set[str] = set()
    for index, (call, result) in enumerate(zip(tool_calls, tool_results), start=1):
        if native_call_is_verifier(call):
            command_run_id = command_run_id_from_result(result)
            if command_run_id:
                verifier_command_run_ids.add(command_run_id)
        if native_result_is_terminal_verifier(call, result, verifier_command_run_ids=verifier_command_run_ids):
            latest_verifier_index = index
    if not latest_mutation:
        return {}
    latest_mutation["latest_verifier_index"] = latest_verifier_index
    if int(latest_mutation.get("result_index") or 0) <= latest_verifier_index:
        return {}
    return latest_mutation


def latest_native_source_mutation(
    tool_calls: tuple[NativeTranscriptItem, ...],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    source_mutation_roots: tuple[str, ...],
) -> dict[str, object]:
    latest_mutation: dict[str, object] = {}
    for index, (call, result) in enumerate(zip(tool_calls, tool_results), start=1):
        if result.status == "completed" and native_result_has_source_mutation(
            result,
            source_mutation_roots=source_mutation_roots,
        ):
            latest_mutation = {
                "result_index": index,
                "provider_call_id": call.call_id or result.provider_call_id,
                "tool_name": call.tool_name or result.tool_name,
                "path": native_write_result_path(result),
                "turn_index": turn_number(call.turn_id),
            }
    return latest_mutation


def native_result_is_terminal_verifier(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    verifier_command_run_ids: set[str],
) -> bool:
    if result.status not in {"completed", "failed", "interrupted", "invalid"}:
        return False
    command_run_id = command_run_id_from_result(result)
    if command_run_id and command_run_id in verifier_command_run_ids:
        return True
    if native_call_is_verifier(call):
        return True
    payload = native_result_payload(result)
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    if not native_execution_contract_is_verifier_like(contract):
        return False
    verifier = payload.get("verifier_evidence")
    if not isinstance(verifier, dict):
        return True
    return str(verifier.get("verdict") or "").casefold() in {"pass", "fail", "partial"}


def native_result_has_source_mutation(
    result: ToolResultEnvelope,
    *,
    source_mutation_roots: tuple[str, ...],
) -> bool:
    for effect in result.side_effects:
        kind = str(effect.get("kind") or "")
        if kind == "file_write" and native_path_in_roots(effect.get("path"), source_mutation_roots):
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


def native_write_result_path(result: ToolResultEnvelope) -> str:
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


def native_path_in_roots(path: object, roots: tuple[str, ...]) -> bool:
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


def native_source_mutation_roots(lane_input: object, workspace: Path) -> tuple[str, ...]:
    lane_config = getattr(lane_input, "lane_config", {}) or {}
    raw_roots = lane_config.get("source_mutation_roots")
    if isinstance(raw_roots, list):
        roots = tuple(str(root) for root in raw_roots if str(root or "").strip())
    else:
        roots = ()
    return roots or (str(workspace),)


def native_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def native_execution_contract_is_verifier_like(contract: object) -> bool:
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


def native_final_verifier_passed(result: ToolResultEnvelope) -> bool:
    if result.status != "completed" or result.is_error:
        return False
    if tool_result_has_semantic_verifier_failure(result):
        return False
    payload = native_result_payload(result)
    verifier = payload.get("verifier_evidence")
    if isinstance(verifier, dict):
        verdict = str(verifier.get("verdict") or "").casefold()
        if verdict == "pass":
            return True
        if verdict in {"fail", "failed", "partial"}:
            return False
        return native_completed_verifier_exit_zero(result)
    return True


def native_completed_verifier_exit_zero(result: ToolResultEnvelope) -> bool:
    payload = native_result_payload(result)
    if payload.get("exit_code") not in (0, "0"):
        return False
    if str(payload.get("tool_name") or "").strip() == "run_tests":
        return True
    contract = payload.get("execution_contract_normalized") or payload.get("execution_contract")
    return native_execution_contract_is_verifier_like(contract) or str(
        payload.get("command_intent") or ""
    ).strip().casefold() in {"verify", "verifier", "verification", "finish_verifier", "test", "acceptance"}


def command_run_id_from_result(result: ToolResultEnvelope) -> str:
    payload = native_result_payload(result)
    return str(payload.get("command_run_id") or "").strip()


def native_call_is_verifier(item: NativeTranscriptItem) -> bool:
    if item.tool_name == "run_tests":
        return True
    if item.tool_name not in {"run_command", "exec_command"}:
        return False
    arguments, _ = arguments_from_native_call(item)
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


def tool_result_has_semantic_verifier_failure(result: ToolResultEnvelope) -> bool:
    if str(result.status or "").strip().casefold() not in {"completed", "failed"}:
        return False
    return semantic_verifier_failure_text_matches(result.natural_result_text(limit=5000))


def semantic_verifier_failure_text_matches(value: str) -> bool:
    text = str(value or "")
    if not text:
        return False
    return any(pattern.search(text) for pattern in SEMANTIC_VERIFIER_FAILURE_PATTERNS)


def emit_progress(progress, line: str) -> None:
    if progress:
        progress(line)


def apply_ng_resume_policy(
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
    if no_tool_reason == "no_tool_repeat":
        return (
            ng_return_decision(
                decision,
                blocker="ng_repeat_plateau",
                reason=(
                    "native model returned repeated assistant text without tool progress "
                    "after an NG resume signal"
                ),
            ),
            1,
        )
    if (
        last_progress_fingerprint
        and last_progress_fingerprint == current_progress_fingerprint
        and last_plateau_signature
        and last_plateau_signature == current_plateau_signature
    ):
        return (
            ng_return_decision(
                decision,
                blocker="ng_repeat_plateau",
                reason="internal finish gate repeated the same blocker plateau without model tool progress",
            ),
            1,
        )
    if ng_continue_consecutive_count >= NG_CONTINUE_CONSECUTIVE_LIMIT:
        return (
            ng_return_decision(
                decision,
                blocker="ng_continue_consecutive_cap",
                reason="internal finish gate NG continue hard cap reached",
            ),
            0,
        )
    if ng_continue_total_count >= NG_DECISION_TOTAL_LIMIT - 1:
        return (
            ng_return_decision(
                decision,
                blocker="ng_decision_total_cap",
                reason="internal finish gate total NG decision cap reached",
            ),
            0,
        )
    return decision, 0


def ng_return_decision(
    decision: NativeFinishGateDecision,
    *,
    blocker: str,
    reason: str,
) -> NativeFinishGateDecision:
    return replace(
        decision,
        result="block",
        lane_status="blocked_return",
        reason=reason,
        blockers=tuple(dict.fromkeys((*decision.blockers, blocker))),
    )


__all__ = [
    "NativeCloseoutContext",
    "NativeCloseoutEvent",
    "apply_ng_resume_policy",
    "ng_return_decision",
    "native_final_verifier_closeout_call",
    "native_finish_supplied_closeout_context",
    "native_source_mutation_roots",
    "run_finish_time_closeouts",
]
