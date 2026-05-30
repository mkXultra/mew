"""Native finish-gate contracts for implement_v2.

This module is intentionally a boundary module first.  Phase 1 does not switch
live completion behavior; it freezes the public data shapes and pure helpers
that later phases will wire into the native harness.

The core design decision is pre-release and intentionally not backward
compatible with the legacy hot completion path: typed evidence, oracle
obligations, and resolver records are diagnostics/sidecars after a trusted final
verifier closeout exits 0.  They are not the hot completion authority.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field, replace
import hashlib
import json
from pathlib import Path
import posixpath
import re
import shlex
from typing import Literal, Mapping
from urllib.parse import urlparse

from .native_transcript import NativeTranscript, NativeTranscriptItem, native_transcript_hash
from .types import ToolResultEnvelope


NATIVE_FINISH_GATE_SCHEMA_VERSION = 1
NATIVE_FINISH_GATE_POLICY_VERSION = "native-finish-gate-v1"
NATIVE_FINISH_GATE_DECISIONS_FILE = "native_finish_gate_decisions.jsonl"

FinishVerifierSource = Literal[
    "configured_verifier",
    "auto_detected_verifier",
    "finish_verifier_planner",
]
FinishGateStatus = Literal["completed", "blocked_continue", "blocked_return"]
FinishGateResult = Literal["allow", "block"]
FinishCloseoutStatus = Literal[
    "not_run",
    "completed_zero",
    "completed_nonzero",
    "timed_out",
    "unsafe",
    "missing_command",
    "active_command_running",
    "budget_insufficient",
    "runtime_error",
]
TypedEvidenceProjectionStatus = Literal["not_attempted", "passed", "warning", "failed"]

DEFAULT_ALLOWED_SOURCES: tuple[FinishVerifierSource, ...] = (
    "configured_verifier",
    "finish_verifier_planner",
    "auto_detected_verifier",
)


@dataclass(frozen=True)
class NativeFinishGatePolicy:
    """Policy for native finish closeout.

    `typed_evidence_mode` and `oracle_obligation_mode` are fixed to
    `diagnostic_sidecar` on purpose.  A trusted final verifier closeout is the
    hot completion authority; resolver/evidence projections remain observable
    but lower authority.
    """

    policy_version: str = NATIVE_FINISH_GATE_POLICY_VERSION
    allowed_sources: tuple[FinishVerifierSource, ...] = DEFAULT_ALLOWED_SOURCES
    min_closeout_seconds: float = 5.0
    default_closeout_seconds: float = 60.0
    max_closeout_seconds: float = 3600.0
    allow_shell: bool = False
    require_no_unexpected_source_mutation: bool = True
    record_typed_evidence: bool = True
    typed_evidence_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"
    oracle_obligation_mode: Literal["diagnostic_sidecar"] = "diagnostic_sidecar"

    def as_dict(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "allowed_sources": list(self.allowed_sources),
            "min_closeout_seconds": self.min_closeout_seconds,
            "default_closeout_seconds": self.default_closeout_seconds,
            "max_closeout_seconds": self.max_closeout_seconds,
            "allow_shell": self.allow_shell,
            "require_no_unexpected_source_mutation": self.require_no_unexpected_source_mutation,
            "record_typed_evidence": self.record_typed_evidence,
            "typed_evidence_mode": self.typed_evidence_mode,
            "oracle_obligation_mode": self.oracle_obligation_mode,
        }


@dataclass(frozen=True)
class FinishCloseoutCommandValidation:
    """Validation result for a selected final-verifier command."""

    allowed: bool
    command: FinishCloseoutCommand | None = None
    blockers: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "allowed": self.allowed,
                "command": self.command.as_dict() if self.command else {},
                "blockers": list(self.blockers),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True)
class FinishCloseoutCommand:
    """One trusted final-verifier command candidate."""

    command: str
    cwd: str = "."
    source: FinishVerifierSource = "configured_verifier"
    source_ref: str = ""
    reason: str = ""
    confidence: str = ""
    raw: Mapping[str, object] = field(default_factory=dict)

    def normalized_command(self) -> str:
        return self.command.strip()

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "command": self.command,
                "cwd": self.cwd,
                "source": self.source,
                "source_ref": self.source_ref,
                "reason": self.reason,
                "confidence": self.confidence,
                "raw": dict(self.raw),
            }
        )


@dataclass(frozen=True)
class NativeFinishGateRequest:
    """Pre-extracted request facts for a native finish decision."""

    lane_attempt_id: str
    turn_id: str
    finish_call_id: str = ""
    finish_arguments: Mapping[str, object] = field(default_factory=dict)
    done_candidate_id: str = ""
    task_id: str = ""
    task_description: str = ""
    task_contract: Mapping[str, object] = field(default_factory=dict)
    lane_config: Mapping[str, object] = field(default_factory=dict)
    workspace: str = ""
    allowed_read_roots: tuple[str, ...] = ()
    allowed_write_roots: tuple[str, ...] = ()
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    latest_source_mutation: Mapping[str, object] = field(default_factory=dict)
    prior_tool_summary: tuple[Mapping[str, object], ...] = ()
    configured_command: FinishCloseoutCommand | None = None
    auto_detected_command: FinishCloseoutCommand | None = None
    planner_command: FinishCloseoutCommand | None = None
    remaining_wall_seconds: float | None = None


@dataclass(frozen=True)
class NativeFinishCloseoutResult:
    """Result of the final verifier closeout path.

    Phase 1 serializes opaque tool/transcript objects defensively.  Later phases
    will replace those objects with native transcript items from the harness.
    """

    command: FinishCloseoutCommand | None
    call_item: object | None
    output_item: object | None
    tool_result: object | None
    status: FinishCloseoutStatus
    exit_code: int | None = None
    timed_out: bool = False
    observed_unexpected_source_mutation: bool = False
    typed_evidence_projection_status: TypedEvidenceProjectionStatus = "not_attempted"
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        return _drop_empty(
            {
                "command": self.command.as_dict() if self.command else {},
                "call_item": _json_safe(self.call_item),
                "output_item": _json_safe(self.output_item),
                "tool_result": _json_safe(self.tool_result),
                "status": self.status,
                "exit_code": self.exit_code,
                "timed_out": self.timed_out,
                "observed_unexpected_source_mutation": self.observed_unexpected_source_mutation,
                "typed_evidence_projection_status": self.typed_evidence_projection_status,
                "evidence_refs": list(self.evidence_refs),
                "closeout_refs": list(self.closeout_refs),
                "observer_refs": list(self.observer_refs),
                "blockers": list(self.blockers),
                "warnings": list(self.warnings),
                "reason": self.reason,
            }
        )


@dataclass(frozen=True)
class NativeFinishGateDecision:
    """Authoritative native finish-gate decision record."""

    decision_id: str
    lane_attempt_id: str
    turn_id: str
    finish_call_id: str
    lane_status: FinishGateStatus
    result: FinishGateResult
    closeout: NativeFinishCloseoutResult
    done_candidate_id: str = ""
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
    transcript_hash_before_decision: str = ""
    compact_sidecar_digest_hash: str = ""
    transcript_items_to_append: tuple[object, ...] = ()
    finish_output_payload: Mapping[str, object] = field(default_factory=dict)
    diagnostic_resolver_record: Mapping[str, object] = field(default_factory=dict)
    reason: str = ""
    policy_version: str = NATIVE_FINISH_GATE_POLICY_VERSION
    schema_version: int = NATIVE_FINISH_GATE_SCHEMA_VERSION

    def as_dict(self, *, include_finish_output_payload: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "policy_version": self.policy_version,
            "lane_attempt_id": self.lane_attempt_id,
            "turn_id": self.turn_id,
            "finish_call_id": self.finish_call_id,
            "done_candidate_id": self.done_candidate_id,
            "lane_status": self.lane_status,
            "result": self.result,
            "closeout": self.closeout.as_dict(),
            "blockers": list(self.blockers),
            "missing_obligations": list(self.missing_obligations),
            "evidence_refs": list(self.evidence_refs),
            "closeout_refs": list(self.closeout_refs),
            "observer_refs": list(self.observer_refs),
            "transcript_hash_before_decision": self.transcript_hash_before_decision,
            "compact_sidecar_digest_hash": self.compact_sidecar_digest_hash,
            "transcript_items_to_append": [_json_safe(item) for item in self.transcript_items_to_append],
            "diagnostic_resolver_record": dict(self.diagnostic_resolver_record),
            "reason": self.reason,
        }
        if include_finish_output_payload:
            payload["finish_output_payload"] = finish_output_payload_for_decision(self)
        return _drop_empty(payload)


def select_closeout_command(
    request: NativeFinishGateRequest,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommand | None:
    """Select the highest-precedence allowed closeout command candidate."""

    active_policy = policy or NativeFinishGatePolicy()
    allowed = set(active_policy.allowed_sources)
    for command in (request.configured_command, request.planner_command, request.auto_detected_command):
        if command is None:
            continue
        if command.source not in allowed:
            continue
        if not command.normalized_command():
            continue
        return command
    return None


def validate_closeout_command(
    command: FinishCloseoutCommand | None,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommandValidation:
    """Validate a final-verifier command before dispatch.

    This validator is intentionally conservative for configured/auto-detected
    commands. Planner-generated verifiers are intentionally looser: the planner
    is expected to generate a useful verifier, while this layer only blocks
    clearly dangerous commands.
    """

    active_policy = policy or NativeFinishGatePolicy()
    if command is None:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=None,
            blockers=("closeout_verifier_command_missing",),
            reason="no final verifier closeout command was selected",
        )
    normalized = command.normalized_command()
    if not normalized:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=("closeout_command_empty",),
            reason="final verifier closeout command is empty",
        )
    if command.source not in set(active_policy.allowed_sources):
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=("closeout_command_source_disallowed",),
            reason=f"command source {command.source!r} is not allowed by policy",
        )

    blockers = _unsafe_command_blockers(
        normalized,
        allow_shell=active_policy.allow_shell,
        allow_planner_blacklist_inline_python=command.source == "finish_verifier_planner",
    )
    if blockers:
        return FinishCloseoutCommandValidation(
            allowed=False,
            command=command,
            blockers=blockers,
            reason="final verifier closeout command failed safety validation",
        )
    return FinishCloseoutCommandValidation(
        allowed=True,
        command=command,
        reason="final verifier closeout command passed provenance validation",
    )


def select_and_validate_closeout_command(
    request: NativeFinishGateRequest,
    policy: NativeFinishGatePolicy | None = None,
) -> FinishCloseoutCommandValidation:
    """Select the highest-precedence command and validate it."""

    active_policy = policy or NativeFinishGatePolicy()
    return validate_closeout_command(select_closeout_command(request, active_policy), active_policy)


def finish_output_payload_for_decision(decision: NativeFinishGateDecision) -> dict[str, object]:
    """Build the bounded payload paired with the provider-native finish call."""

    if decision.finish_output_payload:
        return dict(decision.finish_output_payload)
    return _drop_empty(
        {
            "schema_version": decision.schema_version,
            "kind": "native_finish_gate_decision",
            "decision_id": decision.decision_id,
            "policy_version": decision.policy_version,
            "done_candidate_id": decision.done_candidate_id,
            "lane_status": decision.lane_status,
            "result": decision.result,
            "reason": decision.reason,
            "blockers": list(decision.blockers),
            "missing_obligations": list(decision.missing_obligations),
            "evidence_refs": list(decision.evidence_refs),
            "closeout_refs": list(decision.closeout_refs),
            "observer_refs": list(decision.observer_refs),
            "transcript_hash_before_decision": decision.transcript_hash_before_decision,
            "compact_sidecar_digest_hash": decision.compact_sidecar_digest_hash,
            "closeout_status": decision.closeout.status,
            "closeout_exit_code": decision.closeout.exit_code,
            "closeout_timed_out": decision.closeout.timed_out,
            "typed_evidence_projection_status": decision.closeout.typed_evidence_projection_status,
            "diagnostic_resolver_record": dict(decision.diagnostic_resolver_record),
        }
    )


def decide_native_finish_from_closeout(
    request: NativeFinishGateRequest,
    closeout: NativeFinishCloseoutResult,
    policy: NativeFinishGatePolicy | None = None,
) -> NativeFinishGateDecision:
    """Return the authoritative native finish decision for a closeout result.

    A trusted final verifier closeout that exits 0 is the hot completion
    authority.  Typed evidence and oracle projection warnings stay observable
    on the closeout result, but they do not become blockers here.
    """

    active_policy = policy or NativeFinishGatePolicy()
    decision_id = build_decision_id(
        lane_attempt_id=request.lane_attempt_id,
        turn_id=request.turn_id,
        policy_version=active_policy.policy_version,
        finish_call_id=request.finish_call_id,
        done_candidate_id=request.done_candidate_id,
    )
    blockers = tuple(dict.fromkeys(closeout.blockers))
    missing: tuple[str, ...] = ()
    lane_status: FinishGateStatus = "blocked_continue"
    result: FinishGateResult = "block"
    reason = closeout.reason or "final verifier closeout did not allow completion"

    if closeout.status == "completed_zero" and not closeout.timed_out:
        if active_policy.require_no_unexpected_source_mutation and closeout.observed_unexpected_source_mutation:
            blockers = tuple(dict.fromkeys((*blockers, "closeout_unexpected_source_mutation")))
            reason = "trusted final verifier passed but closeout mutated source unexpectedly"
        else:
            blockers = ()
            lane_status = "completed"
            result = "allow"
            reason = "trusted final verifier closeout exited 0"
    elif closeout.status == "missing_command":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_command_missing")))
        missing = ("final_verifier_closeout",)
        reason = closeout.reason or "final verifier closeout command is missing"
    elif closeout.status == "budget_insufficient":
        lane_status = "blocked_return"
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_budget_insufficient")))
        missing = ("final_verifier_closeout",)
        reason = closeout.reason or "insufficient budget for final verifier closeout"
    elif closeout.status == "timed_out" or closeout.timed_out:
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_timeout")))
        reason = closeout.reason or "final verifier closeout timed out"
    elif closeout.status == "active_command_running":
        blockers = tuple(dict.fromkeys((*blockers, "active_command_running")))
        reason = closeout.reason or "active command is still running before final verifier closeout"
    elif closeout.status == "unsafe":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_command_unsafe")))
        reason = closeout.reason or "final verifier closeout command was unsafe"
    elif closeout.status == "completed_nonzero":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_failed")))
        reason = "final verifier closeout exited nonzero"
    elif closeout.status == "runtime_error":
        blockers = tuple(dict.fromkeys((*blockers, "closeout_verifier_runtime_error")))
        reason = closeout.reason or "final verifier closeout runtime error"

    return NativeFinishGateDecision(
        decision_id=decision_id,
        policy_version=active_policy.policy_version,
        lane_attempt_id=request.lane_attempt_id,
        turn_id=request.turn_id,
        finish_call_id=request.finish_call_id,
        done_candidate_id=request.done_candidate_id,
        lane_status=lane_status,
        result=result,
        closeout=closeout,
        blockers=blockers,
        missing_obligations=missing,
        evidence_refs=closeout.evidence_refs,
        closeout_refs=closeout.closeout_refs,
        observer_refs=closeout.observer_refs,
        transcript_hash_before_decision=request.transcript_hash_before_decision,
        compact_sidecar_digest_hash=request.compact_sidecar_digest_hash,
        reason=reason,
    )


def finish_gate_decision_from_closeout_events(
    call: NativeTranscriptItem,
    result: ToolResultEnvelope,
    *,
    lane_input: object,
    lane_config: Mapping[str, object],
    transcript_items: tuple[NativeTranscriptItem, ...],
    compact_sidecar_digest_hash: str,
    closeout_events: tuple[object, ...],
    closeout_context: object,
) -> NativeFinishGateDecision | None:
    if result.tool_name != "finish":
        return None
    arguments, error = arguments_from_native_call(call)
    if error:
        return None
    if native_finish_outcome(arguments) != "completed" or arguments.get("task_done") is False:
        return None
    final_event = next((event for event in reversed(closeout_events) if getattr(event, "kind", "") == "final_verifier"), None)
    if final_event is None:
        return None
    closeout = finish_closeout_result_from_event(final_event, closeout_context=closeout_context)
    if closeout.status != "completed_zero":
        return None
    request = NativeFinishGateRequest(
        lane_attempt_id=call.lane_attempt_id,
        turn_id=call.turn_id,
        finish_call_id=call.call_id,
        finish_arguments=dict(arguments),
        task_id=str(getattr(lane_input, "task_id", "") or ""),
        task_description=native_task_description(lane_input),
        task_contract=dict(getattr(lane_input, "task_contract", {}) or {}),
        lane_config=dict(lane_config),
        workspace=str(getattr(lane_input, "workspace", "") or ""),
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
        compact_sidecar_digest_hash=compact_sidecar_digest_hash,
    )
    return decide_native_finish_from_closeout(request, closeout)


def finish_gate_decision_from_done_candidate(
    done_candidate: object,
    *,
    lane_input: object,
    lane_config: Mapping[str, object],
    provider: object,
    turn_index: int,
    transcript_items: tuple[NativeTranscriptItem, ...],
    closeout_events: tuple[object, ...],
    closeout_context: object,
) -> NativeFinishGateDecision:
    final_event = next((event for event in reversed(closeout_events) if getattr(event, "kind", "") == "final_verifier"), None)
    if final_event is not None:
        closeout = finish_closeout_result_from_event(final_event, closeout_context=closeout_context)
    else:
        closeout = finish_closeout_result_from_context(closeout_context)
    lane_attempt_id = str(getattr(done_candidate, "lane_attempt_id", "") or "")
    turn_id = str(getattr(done_candidate, "turn_id", "") or f"turn-{turn_index}")
    request = NativeFinishGateRequest(
        lane_attempt_id=lane_attempt_id,
        turn_id=turn_id,
        done_candidate_id=str(getattr(done_candidate, "done_candidate_id", "") or ""),
        task_id=str(getattr(lane_input, "task_id", "") or ""),
        task_description=native_task_description(lane_input),
        task_contract=dict(getattr(lane_input, "task_contract", {}) or {}),
        lane_config=dict(lane_config),
        workspace=str(getattr(lane_input, "workspace", "") or ""),
        allowed_read_roots=tuple(str(root) for root in lane_config.get("allowed_read_roots") or ()),
        allowed_write_roots=tuple(str(root) for root in lane_config.get("allowed_write_roots") or ()),
        transcript_hash_before_decision=native_transcript_hash(
            NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider=str(getattr(provider, "provider", "")),
                model=str(getattr(provider, "model", "")),
                items=transcript_items,
            )
        ),
        compact_sidecar_digest_hash=str(getattr(done_candidate, "compact_sidecar_digest_hash", "") or ""),
    )
    return decide_native_finish_from_closeout(request, closeout)


def finish_gate_decision_from_controller_closeout_event(
    event: object,
    *,
    lane_input: object,
    lane_config: Mapping[str, object],
    transcript_items: tuple[NativeTranscriptItem, ...],
    closeout_context: object,
) -> NativeFinishGateDecision:
    call = getattr(event, "call")
    closeout = finish_closeout_result_from_event(event, closeout_context=closeout_context)
    request = NativeFinishGateRequest(
        lane_attempt_id=call.lane_attempt_id,
        turn_id=call.turn_id,
        finish_call_id=call.call_id,
        finish_arguments={
            "outcome": "completed",
            "summary": "deterministic final verifier closeout",
            "controller_closeout": True,
        },
        task_id=str(getattr(lane_input, "task_id", "") or ""),
        task_description=native_task_description(lane_input),
        task_contract=dict(getattr(lane_input, "task_contract", {}) or {}),
        lane_config=dict(lane_config),
        workspace=str(getattr(lane_input, "workspace", "") or ""),
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
    )
    return decide_native_finish_from_closeout(request, closeout)


def finish_closeout_result_from_context(context: object) -> NativeFinishCloseoutResult:
    blockers = tuple(
        dict.fromkeys(
            (
                *context_text_tuple(context, "blockers"),
                *context_text_tuple(context, "unsafe_blockers"),
                *context_text_tuple(context, "budget_blockers"),
            )
        )
    )
    status: FinishCloseoutStatus = "not_run"
    reason = "final verifier closeout did not run"
    context_blockers = context_text_tuple(context, "blockers")
    budget_blockers = context_text_tuple(context, "budget_blockers")
    unsafe_blockers = context_text_tuple(context, "unsafe_blockers")
    if "closeout_verifier_command_missing" in context_blockers:
        status = "missing_command"
        reason = "final verifier closeout command is missing"
    elif "closeout_verifier_budget_or_timeout" in budget_blockers:
        status = "timed_out"
        reason = "final verifier closeout timed out"
    elif budget_blockers:
        status = "budget_insufficient"
        reason = "insufficient budget for final verifier closeout"
    elif unsafe_blockers:
        status = "unsafe"
        reason = "final verifier closeout is not permitted"
    elif "closeout_verifier_failed" in context_blockers:
        status = "completed_nonzero"
        reason = "final verifier closeout exited nonzero"
    elif "closeout_verifier_not_run" in context_blockers:
        status = "not_run"
        reason = "final verifier closeout was not run"
    return NativeFinishCloseoutResult(
        command=None,
        call_item=None,
        output_item=None,
        tool_result=None,
        status=status,
        evidence_refs=context_text_tuple(context, "fresh_verifier_refs"),
        closeout_refs=context_text_tuple(context, "closeout_refs"),
        blockers=blockers,
        reason=reason,
    )


def finish_closeout_result_from_event(
    event: object,
    *,
    closeout_context: object,
) -> NativeFinishCloseoutResult:
    result = getattr(event, "result")
    call = getattr(event, "call")
    payload = native_result_payload(result)
    exit_code = native_exit_code(payload)
    timed_out = native_result_timed_out(result, payload)
    if result.status == "completed" and not result.is_error and exit_code == 0 and not timed_out:
        status: FinishCloseoutStatus = "completed_zero"
    elif timed_out:
        status = "timed_out"
    elif result.status in {"completed", "failed"} and exit_code not in (None, 0):
        status = "completed_nonzero"
    elif result.status in {"yielded", "running"}:
        status = "active_command_running"
    else:
        status = "runtime_error"
    warnings = native_closeout_projection_warnings(result)
    return NativeFinishCloseoutResult(
        command=finish_closeout_command_from_call(call),
        call_item=call,
        output_item=None,
        tool_result=result,
        status=status,
        exit_code=exit_code,
        timed_out=timed_out,
        observed_unexpected_source_mutation=native_closeout_observed_source_mutation(result),
        typed_evidence_projection_status="warning" if warnings else "passed",
        evidence_refs=tuple(result.evidence_refs),
        closeout_refs=context_text_tuple(closeout_context, "closeout_refs"),
        warnings=warnings,
        reason=str(getattr(event, "reason", "") or ""),
    )


def finish_closeout_command_from_call(call: NativeTranscriptItem) -> FinishCloseoutCommand | None:
    arguments, error = arguments_from_native_call(call)
    if error:
        return None
    command = str(arguments.get("command") or "").strip()
    if not command:
        return None
    plan = arguments.get("finish_verifier_plan")
    source: FinishVerifierSource = "configured_verifier"
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
        source=source,
        source_ref=source_ref,
        reason=reason,
        confidence=confidence,
        raw=dict(arguments),
    )


def native_task_description(lane_input: object) -> str:
    contract = getattr(lane_input, "task_contract", {}) if isinstance(getattr(lane_input, "task_contract", {}), dict) else {}
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


def native_finish_outcome(arguments: Mapping[str, object]) -> str:
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


def native_result_payload(result: ToolResultEnvelope) -> dict[str, object]:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return dict(payload) if isinstance(payload, dict) else {}


def native_exit_code(payload: Mapping[str, object]) -> int | None:
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


def native_result_timed_out(result: ToolResultEnvelope, payload: Mapping[str, object]) -> bool:
    if payload.get("timed_out") is True:
        return True
    status = str(payload.get("status") or result.status or "").strip().casefold()
    return status in {"timeout", "timed_out"}


def native_closeout_projection_warnings(result: ToolResultEnvelope) -> tuple[str, ...]:
    payload = native_result_payload(result)
    warnings: list[str] = []
    unchecked = payload.get("unchecked_expected_artifacts")
    if isinstance(unchecked, list) and unchecked:
        warnings.append("unchecked_expected_artifacts")
    if payload.get("typed_evidence_projection_status") in {"warning", "failed"}:
        warnings.append("typed_evidence_projection_warning")
    return tuple(dict.fromkeys(warnings))


def native_closeout_observed_source_mutation(result: ToolResultEnvelope) -> bool:
    payload = native_result_payload(result)
    if payload.get("observed_source_side_effect") is True:
        return True
    observations = payload.get("process_source_observations")
    if isinstance(observations, list):
        for observation in observations:
            if isinstance(observation, Mapping) and positive_intish(observation.get("changed_count")):
                return True
    for effect in result.side_effects:
        if str(effect.get("kind") or "") in {"source_tree_mutation", "source_tree_delta"}:
            record = effect.get("record")
            if isinstance(record, Mapping) and positive_intish(record.get("changed_count")):
                return True
    return False


def positive_intish(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return int(value or 0) > 0
    except (TypeError, ValueError):
        return False


def context_text_tuple(context: object, name: str) -> tuple[str, ...]:
    value = getattr(context, name, ())
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(text for item in value if (text := str(item or "").strip()))


def finish_result_with_native_finish_gate_decision(
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


def write_native_finish_gate_artifacts(
    root: str | Path,
    decisions: tuple[NativeFinishGateDecision, ...] | list[NativeFinishGateDecision],
    *,
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write native finish-gate decisions and mirror their ref/hash into manifest."""

    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    decision_path = artifact_root / NATIVE_FINISH_GATE_DECISIONS_FILE
    records = [decision.as_dict(include_finish_output_payload=False) for decision in decisions]
    _write_jsonl(decision_path, records)
    digest = _file_sha256(decision_path)
    if proof_manifest_path is not None:
        _patch_proof_manifest(
            Path(proof_manifest_path),
            decision_path=decision_path,
            digest=digest,
            records=records,
        )
    return {"native_finish_gate_decisions": decision_path}


def native_finish_gate_manifest_fields(path: str | Path) -> dict[str, object]:
    decision_path = Path(path)
    return {
        "native_finish_gate_decisions_ref": decision_path.name,
        "native_finish_gate_decisions_sha256": _file_sha256(decision_path),
    }


def build_decision_id(
    *,
    lane_attempt_id: str,
    turn_id: str,
    policy_version: str,
    finish_call_id: str = "",
    done_candidate_id: str = "",
) -> str:
    """Return a deterministic decision id for sidecar/replay records."""

    authority_id = done_candidate_id or finish_call_id
    if done_candidate_id:
        hash_payload = {
            "done_candidate_id": done_candidate_id,
            "lane_attempt_id": lane_attempt_id,
            "policy_version": policy_version,
            "turn_id": turn_id,
        }
    else:
        hash_payload = {
            "finish_call_id": finish_call_id,
            "lane_attempt_id": lane_attempt_id,
            "policy_version": policy_version,
            "turn_id": turn_id,
        }
    digest = hashlib.sha256(
        json.dumps(
            hash_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"native-finish-gate:{turn_id}:{authority_id}:{digest}"


_NOOP_COMMANDS = frozenset(
    {
        ":",
        "true",
        "/bin/true",
        "exit 0",
        "test 1 = 1",
        "test 1 == 1",
        "[ 1 = 1 ]",
        "[[ 1 == 1 ]]",
    }
)
_SHELL_TOKENS = frozenset({"bash", "sh", "zsh", "/bin/bash", "/bin/sh", "/bin/zsh"})
_SELF_ACCEPTANCE_TOKENS = frozenset({"echo", "printf"})
_WEAK_ASSERTION_TOKENS = frozenset({"test", "[", "[["})
_INLINE_EVALUATOR_TOKENS = frozenset({"node", "python", "python3", "ruby"})
_READ_ONLY_INLINE_PYTHON_IMPORT_ROOTS = frozenset(
    {
        "collections",
        "csv",
        "hashlib",
        "importlib",
        "inspect",
        "json",
        "math",
        "os",
        "pathlib",
        "re",
        "statistics",
        "subprocess",
        "sys",
    }
)
_UNSAFE_INLINE_PYTHON_CALLS = frozenset(
    {
        "__import__",
        "builtins.open",
        "compile",
        "eval",
        "exec",
        "getattr",
        "importlib.import_module",
        "mkdir",
        "os.chmod",
        "os.chown",
        "os.makedirs",
        "os.mkdir",
        "os.open",
        "os.popen",
        "os.remove",
        "os.rename",
        "os.replace",
        "os.rmdir",
        "os.system",
        "os.truncate",
        "os.unlink",
        "object.__getattribute__",
        "pathlib.Path.mkdir",
        "pathlib.Path.rename",
        "pathlib.Path.replace",
        "pathlib.Path.rmdir",
        "pathlib.Path.touch",
        "pathlib.Path.unlink",
        "pathlib.Path.write_bytes",
        "pathlib.Path.write_text",
        "remove",
        "rename",
        "replace",
        "rmdir",
        "shutil.copy",
        "shutil.copy2",
        "shutil.copyfile",
        "shutil.copytree",
        "shutil.move",
        "shutil.rmtree",
        "touch",
        "unlink",
        "vars",
        "write",
        "write_bytes",
        "write_text",
    }
)
_UNSAFE_INLINE_PYTHON_GIT_SUBCOMMANDS = frozenset(
    {
        "add",
        "am",
        "apply",
        "checkout",
        "cherry-pick",
        "clean",
        "clone",
        "commit",
        "fetch",
        "merge",
        "mv",
        "pull",
        "push",
        "rebase",
        "reset",
        "restore",
        "revert",
        "rm",
        "switch",
    }
)
_WRAPPER_TOKENS = frozenset({"command", "env"})
_SOURCE_MUTATION_TOKENS = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "install",
        "ln",
        "mkdir",
        "mv",
        "rm",
        "rsync",
        "sed",
        "tee",
        "touch",
        "truncate",
    }
)
_PACKAGE_INSTALL_TOKENS = frozenset(
    {"apt", "apt-get", "brew", "dnf", "npm", "pip", "pip3", "pipenv", "pnpm", "poetry", "uv", "yarn"}
)
_NETWORK_TOKENS = frozenset({"curl", "git", "hg", "scp", "ssh", "svn", "wget"})
_BACKGROUND_TOKENS = frozenset({"daemon", "nohup"})
_PRIVILEGED_TOKENS = frozenset({"doas", "sudo", "su"})
_SECRET_MARKERS = (
    "API_KEY",
    "AUTH_TOKEN",
    "BEARER",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


def _unsafe_command_blockers(
    command: str,
    *,
    allow_shell: bool,
    allow_planner_blacklist_inline_python: bool = False,
) -> tuple[str, ...]:
    if _contains_unquoted_control(command, ("\n", "\r")) and not allow_planner_blacklist_inline_python:
        return ("closeout_command_multiline",)
    trimmed = command.strip()
    normalized = " ".join(trimmed.split())
    tokens = _split_command_tokens(trimmed)
    semantic_tokens = _semantic_tokens(tokens)
    if allow_planner_blacklist_inline_python:
        return _dangerous_planner_command_blockers(trimmed, tokens, semantic_tokens)

    blockers: list[str] = []
    if normalized in _NOOP_COMMANDS:
        blockers.append("closeout_command_noop_success")

    first = _basename(semantic_tokens[0]) if semantic_tokens else ""
    if first in _SELF_ACCEPTANCE_TOKENS:
        blockers.append("closeout_command_self_acceptance")
    if first in _WEAK_ASSERTION_TOKENS:
        blockers.append("closeout_command_weak_assertion")
    if first in _INLINE_EVALUATOR_TOKENS and any(token in {"-c", "-e"} for token in semantic_tokens):
        if not (
            allow_planner_blacklist_inline_python
            and not _python_asserts_disabled(tokens)
            and _planner_inline_python_has_no_dangerous_ops(semantic_tokens)
        ):
            blockers.append("closeout_command_inline_program")
    if first in _SHELL_TOKENS and not allow_shell:
        blockers.append("closeout_command_shell_disallowed")
    semantic_basenames = {_basename(token) for token in semantic_tokens}
    if semantic_basenames & _SOURCE_MUTATION_TOKENS:
        blockers.append("closeout_command_source_mutation")
    if semantic_basenames & _PACKAGE_INSTALL_TOKENS and "install" in semantic_tokens:
        blockers.append("closeout_command_package_install")
    if semantic_basenames & _NETWORK_TOKENS:
        blockers.append("closeout_command_network")
    if semantic_basenames & _PRIVILEGED_TOKENS:
        blockers.append("closeout_command_privileged")
    if semantic_basenames & _BACKGROUND_TOKENS:
        blockers.append("closeout_command_background")

    if _contains_unquoted_control(command, (">", "<")):
        blockers.append("closeout_command_redirection")
    if _contains_chain_operator(command):
        blockers.append("closeout_command_chain")
    if _contains_background_operator(command):
        blockers.append("closeout_command_background")
    if any(marker in command.upper() for marker in _SECRET_MARKERS):
        blockers.append("closeout_command_secret")
    if _contains_self_pass_marker(command):
        blockers.append("closeout_command_self_acceptance")
    return tuple(dict.fromkeys(blockers))


_DANGEROUS_PLANNER_COMMAND_TOKENS = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "dd",
        "install",
        "kill",
        "killall",
        "ln",
        "mkfs",
        "mount",
        "mv",
        "pkill",
        "reboot",
        "rm",
        "rmdir",
        "rsync",
        "shutdown",
        "shred",
        "touch",
        "truncate",
        "umount",
    }
)
_DANGEROUS_PLANNER_GIT_SUBCOMMANDS = _UNSAFE_INLINE_PYTHON_GIT_SUBCOMMANDS


def _dangerous_planner_command_blockers(
    command: str,
    tokens: tuple[str, ...],
    semantic_tokens: tuple[str, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    shell_tokens = _planner_shell_tokens(command)
    if not shell_tokens:
        if _command_string_mentions_dangerous_operation(command):
            blockers.append("closeout_command_dangerous")
        if _planner_string_mentions_network(command):
            blockers.append("closeout_command_network")
        if _planner_string_mentions_package_install(command):
            blockers.append("closeout_command_package_install")
        if any(marker in command.upper() for marker in _SECRET_MARKERS):
            blockers.append("closeout_command_secret")
        return tuple(dict.fromkeys(blockers))
    if _planner_tokens_contain_background_operator(shell_tokens):
        blockers.append("closeout_command_background")
    for segment in _planner_command_segments(shell_tokens):
        blockers.extend(_dangerous_planner_segment_blockers(segment))
    if any(marker in command.upper() for marker in _SECRET_MARKERS):
        blockers.append("closeout_command_secret")
    heredoc_blocker = _planner_heredoc_inline_program_blocker(command)
    if heredoc_blocker:
        blockers.append(heredoc_blocker)
    return tuple(dict.fromkeys(blockers))


def _planner_shell_tokens(command: str) -> tuple[str, ...]:
    normalized = command
    if _contains_unquoted_control(command, ("\n", "\r")):
        normalized = command.replace("\r", "\n").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(normalized, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = "#"
        return tuple(str(token) for token in lexer)
    except ValueError:
        return ()


def _planner_command_segments(tokens: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    segments: list[tuple[str, ...]] = []
    current: list[str] = []
    for token in tokens:
        if token in {"&&", "||", ";", "|"}:
            if current:
                segments.append(tuple(current))
                current = []
            continue
        current.append(token)
    if current:
        segments.append(tuple(current))
    return tuple(segments)


def _planner_tokens_contain_background_operator(tokens: tuple[str, ...]) -> bool:
    return any(token == "&" for token in tokens)


def _planner_heredoc_inline_program_blocker(command: str) -> str:
    if "<<" not in command:
        return ""
    first_line = command.splitlines()[0] if command.splitlines() else command
    try:
        first_tokens = tuple(shlex.split(first_line))
    except ValueError:
        return "closeout_command_inline_program"
    semantic = _semantic_tokens(first_tokens)
    if not semantic or _basename(semantic[0]) not in _INLINE_EVALUATOR_TOKENS:
        return ""
    body = _extract_heredoc_body(command)
    if body is None:
        return "closeout_command_inline_program"
    first = _basename(semantic[0])
    if first in {"python", "python3"}:
        return "" if _planner_inline_python_code_has_no_dangerous_ops(body) else "closeout_command_inline_program"
    return "closeout_command_inline_program" if _command_string_mentions_dangerous_operation(body) else ""


def _extract_heredoc_body(command: str) -> str | None:
    match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\n(.*?)\n\1(?:\n|$)", command, re.S)
    if not match:
        return None
    return match.group(2)


def _dangerous_planner_segment_blockers(segment: tuple[str, ...]) -> tuple[str, ...]:
    semantic = _semantic_tokens(segment)
    if not semantic:
        return ()
    first = _basename(semantic[0])
    blockers: list[str] = []
    if first.startswith("$") or "${" in first:
        blockers.append("closeout_command_dangerous")
    if first in _SHELL_TOKENS:
        nested = _shell_inline_script(semantic)
        if nested:
            blockers.extend(_dangerous_planner_command_blockers(nested, _split_command_tokens(nested), ()))
        return tuple(dict.fromkeys(blockers))
    if first in _INLINE_EVALUATOR_TOKENS and any(token in {"-c", "-e"} for token in semantic):
        if _python_asserts_disabled(segment) or _planner_inline_program_mentions_dangerous_operation(semantic):
            blockers.append("closeout_command_inline_program")
    if first in {"rm", "rmdir"} and _planner_rm_segment_is_safe_temp_cleanup(semantic):
        pass
    elif first in _DANGEROUS_PLANNER_COMMAND_TOKENS:
        blockers.append("closeout_command_dangerous")
    if first == "sed" and any(token == "-i" or token.startswith("-i") for token in semantic):
        blockers.append("closeout_command_dangerous")
    if first == "find" and any(token == "-delete" for token in semantic):
        blockers.append("closeout_command_dangerous")
    if first == "find" and "-exec" in semantic and any(
        _basename(token) in _DANGEROUS_PLANNER_COMMAND_TOKENS for token in semantic
    ):
        blockers.append("closeout_command_dangerous")
    if first == "xargs" and any(_basename(token) in _DANGEROUS_PLANNER_COMMAND_TOKENS for token in semantic[1:]):
        blockers.append("closeout_command_dangerous")
    if first in _PACKAGE_INSTALL_TOKENS and _segment_mentions_package_install(semantic):
        blockers.append("closeout_command_package_install")
    if first == "python" or first == "python3":
        if _python_module_invocation_mentions_package_install(semantic):
            blockers.append("closeout_command_package_install")
    if first in (_NETWORK_TOKENS - {"git"}):
        blockers.append("closeout_command_network")
    if first in _PRIVILEGED_TOKENS:
        blockers.append("closeout_command_privileged")
    if first in _BACKGROUND_TOKENS:
        blockers.append("closeout_command_background")
    if first == "git":
        subcommand = _first_git_subcommand([_basename(token) for token in semantic[1:]])
        if subcommand in _DANGEROUS_PLANNER_GIT_SUBCOMMANDS:
            blockers.append("closeout_command_dangerous")
        if subcommand in {"archive", "clone", "fetch", "ls-remote", "pull", "push", "remote", "submodule"}:
            blockers.append("closeout_command_network")
    return tuple(dict.fromkeys(blockers))


def _planner_rm_segment_is_safe_temp_cleanup(segment: tuple[str, ...]) -> bool:
    """Allow planner verifiers to reset their own literal /tmp output dirs."""

    if not segment:
        return False
    first = _basename(segment[0])
    if first not in {"rm", "rmdir"}:
        return False
    operands: list[str] = []
    end_of_options = False
    for token in segment[1:]:
        if not token:
            return False
        if not end_of_options and token == "--":
            end_of_options = True
            continue
        if not end_of_options and token.startswith("-"):
            allowed_flag_chars = set("rfvId")
            if token == "-" or any(char not in allowed_flag_chars for char in token[1:]):
                return False
            continue
        operands.append(token)
    if not operands:
        return False
    return all(_planner_rm_operand_is_safe_temp_cleanup_path(operand) for operand in operands)


def _planner_rm_operand_is_safe_temp_cleanup_path(path: str) -> bool:
    if any(marker in path for marker in ("*", "?", "[", "]", "{", "}", "$", "`", "~")):
        return False
    if path.endswith(("/", "\\")):
        return False
    if posixpath.normpath(path) != path:
        return False
    if not path.startswith("/tmp/"):
        return False
    relative = path.removeprefix("/tmp/")
    if not relative or relative in {".", ".."} or "/" in relative:
        return False
    return True


def _token_after_flag(tokens: tuple[str, ...], flag: str) -> str:
    for index, token in enumerate(tokens[:-1]):
        if token == flag:
            return tokens[index + 1]
    return ""


def _shell_inline_script(tokens: tuple[str, ...]) -> str:
    for index, token in enumerate(tokens[:-1]):
        if token == "-c":
            return tokens[index + 1]
        if token.startswith("-") and "c" in token[1:]:
            return tokens[index + 1]
    return ""


def _segment_mentions_package_install(tokens: tuple[str, ...]) -> bool:
    return any(token in {"add", "i", "install", "uninstall"} for token in tokens[1:])


def _python_module_invocation_mentions_package_install(tokens: tuple[str, ...]) -> bool:
    for index, token in enumerate(tokens[:-2]):
        if token == "-m" and tokens[index + 1] in {"pip", "pip3"}:
            if _python_tokens_are_read_only_package_probe(list(tokens[index:])):
                return False
            return any(item in {"install", "uninstall"} for item in tokens[index + 2 :])
    return False


def _planner_inline_program_mentions_dangerous_operation(tokens: tuple[str, ...]) -> bool:
    if not tokens:
        return False
    first = _basename(tokens[0])
    if first in {"python", "python3"} and any(token in {"-c", "-e"} for token in tokens):
        return not _planner_inline_python_has_no_dangerous_ops(tokens)
    if first in {"node", "ruby"} and any(token in {"-c", "-e"} for token in tokens):
        code = _inline_python_code(tokens)
        return _command_string_mentions_dangerous_operation(code)
    return False


def _planner_inline_python_has_no_dangerous_ops(tokens: tuple[str, ...]) -> bool:
    if not tokens or _basename(tokens[0]) not in {"python", "python3"}:
        return False
    if _python_asserts_disabled(tokens):
        return False
    code = _inline_python_code(tokens)
    if not code:
        return False
    return _planner_inline_python_code_has_no_dangerous_ops(code)


def _planner_inline_python_code_has_no_dangerous_ops(code: str) -> bool:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    aliases = _python_import_aliases(tree)
    aliases.update(_python_assignment_aliases(tree, aliases))
    value_aliases = _python_assignment_string_sequences(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Subscript):
                return False
            call_name = _python_call_name(node.func, aliases)
            if _python_call_is_local_network_probe(call_name, node, aliases):
                continue
            if _python_call_name_is_unsafe(call_name):
                return False
            method_open = call_name.endswith(".open") and call_name not in {"builtins.open", "__builtins__.open"}
            if (call_name == "open" or call_name.endswith(".open")) and _python_open_call_can_write(
                node,
                method_open=method_open,
            ):
                return False
            if call_name.startswith("subprocess.") and (
                _python_subprocess_call_uses_shell(node)
                or _python_subprocess_call_mentions_mutating_command(node, value_aliases)
            ):
                return False
        elif isinstance(node, ast.Assign):
            if _python_assignment_value_is_unsafe(node.value, aliases):
                return False
        elif isinstance(node, ast.AnnAssign):
            if _python_assignment_value_is_unsafe(node.value, aliases):
                return False
    return True


def _inline_python_code(tokens: tuple[str, ...]) -> str:
    for index, token in enumerate(tokens[:-1]):
        if token in {"-c", "-e"}:
            return tokens[index + 1]
    return ""


def _python_asserts_disabled(tokens: tuple[str, ...]) -> bool:
    for token in tokens:
        if token.startswith("PYTHONOPTIMIZE=") and token.split("=", 1)[1] not in {"", "0"}:
            return True
        if not token.startswith("-"):
            continue
        if token in {"-c", "-e", "-B"}:
            continue
        if "O" in token:
            return True
    return False


def _python_import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                aliases[alias.asname or root] = root
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = f"{module}.{alias.name}" if module else alias.name
                aliases[alias.asname or alias.name] = name
    return aliases


def _python_assignment_aliases(tree: ast.AST, aliases: Mapping[str, str]) -> dict[str, str]:
    assigned: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        name = _python_call_name(node.value, {**aliases, **assigned})
        if name:
            assigned[target.id] = name
    return assigned


def _python_assignment_string_sequences(tree: ast.AST) -> dict[str, list[str]]:
    assigned: dict[str, list[str]] = {}
    body = getattr(tree, "body", ())
    for node in body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            tokens = _python_static_string_sequence(node.value, assigned)
            if tokens is not None:
                assigned[node.targets[0].id] = tokens
            continue
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            current = assigned.get(node.target.id)
            addition = _python_static_string_sequence(node.value, assigned)
            if current is not None and addition is not None:
                assigned[node.target.id] = [*current, *addition]
            else:
                assigned.pop(node.target.id, None)
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            _python_apply_string_sequence_mutation(node.value, assigned)
    return assigned


def _python_apply_string_sequence_mutation(call: ast.Call, assigned: dict[str, list[str]]) -> None:
    if not isinstance(call.func, ast.Attribute) or not isinstance(call.func.value, ast.Name):
        return
    name = call.func.value.id
    current = assigned.get(name)
    if current is None:
        return
    method = call.func.attr
    if method == "append" and len(call.args) == 1:
        addition = _python_static_string_sequence(call.args[0], assigned)
        if addition is not None and len(addition) == 1:
            assigned[name] = [*current, addition[0]]
            return
    if method == "extend" and len(call.args) == 1:
        addition = _python_static_string_sequence(call.args[0], assigned)
        if addition is not None:
            assigned[name] = [*current, *addition]
            return
    assigned.pop(name, None)


def _python_static_string_sequence(node: ast.AST, assigned: Mapping[str, list[str]]) -> list[str] | None:
    if isinstance(node, ast.Name):
        return assigned.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            return shlex.split(node.value)
        except ValueError:
            return node.value.split()
    if isinstance(node, (ast.List, ast.Tuple)):
        tokens: list[str] = []
        for element in node.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                tokens.append(element.value)
            else:
                nested = _python_static_string_sequence(element, assigned)
                if nested is None:
                    return None
                tokens.extend(nested)
        return tokens
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        if (
            isinstance(node.left, ast.Constant)
            and isinstance(node.left.value, str)
            and isinstance(node.right, ast.Constant)
            and isinstance(node.right.value, str)
        ):
            return [node.left.value + node.right.value]
        left = _python_static_string_sequence(node.left, assigned)
        right = _python_static_string_sequence(node.right, assigned)
        if left is None or right is None:
            return None
        return [*left, *right]
    if isinstance(node, ast.Call):
        name = _python_call_name(node.func)
        if name in {"list", "tuple"} and len(node.args) == 1:
            return _python_static_string_sequence(node.args[0], assigned)
    return None


def _python_call_name(node: ast.AST, aliases: Mapping[str, str] | None = None) -> str:
    if isinstance(node, ast.Name):
        return (aliases or {}).get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        parent = _python_call_name(node.value, aliases)
        return f"{parent}.{node.attr}" if parent else node.attr
    if isinstance(node, ast.Call):
        return _python_call_name(node.func, aliases)
    return ""


def _python_call_name_is_unsafe(call_name: str) -> bool:
    if call_name in _UNSAFE_INLINE_PYTHON_CALLS:
        return True
    if call_name.startswith("builtins.") and call_name.split(".", 1)[1] in _UNSAFE_INLINE_PYTHON_CALLS:
        return True
    if call_name.startswith("__builtins__.") and call_name.split(".", 1)[1] in _UNSAFE_INLINE_PYTHON_CALLS:
        return True
    if call_name.startswith(("http.client.", "requests.", "socket.", "urllib.request.", "urllib3.")):
        return True
    unsafe_suffixes = (
        ".mkdir",
        ".remove",
        ".rename",
        ".replace",
        ".rmdir",
        ".touch",
        ".unlink",
        ".write",
        ".write_bytes",
        ".write_text",
    )
    return any(call_name.endswith(suffix) for suffix in unsafe_suffixes)


def _python_call_is_local_network_probe(call_name: str, node: ast.Call, aliases: Mapping[str, str]) -> bool:
    if call_name == "urllib.request.urlopen":
        return _python_call_has_local_url_arg(node)
    if not call_name.startswith("urllib.request.urlopen."):
        return False
    methods = call_name.removeprefix("urllib.request.urlopen.").split(".")
    if any(method not in {"read", "decode"} for method in methods):
        return False
    urlopen_children = [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call) and _python_call_name(child.func, aliases) == "urllib.request.urlopen"
    ]
    if not urlopen_children:
        return True
    return any(
        _python_call_has_local_url_arg(child)
        for child in urlopen_children
    )


def _python_call_has_local_url_arg(node: ast.Call) -> bool:
    url_node: ast.AST | None = node.args[0] if node.args else None
    for keyword in node.keywords:
        if keyword.arg in {"url", "fullurl"}:
            url_node = keyword.value
            break
    if not isinstance(url_node, ast.Constant) or not isinstance(url_node.value, str):
        return False
    return _is_local_http_url(url_node.value)


def _python_open_call_can_write(node: ast.Call, *, method_open: bool) -> bool:
    mode = ""
    if method_open and node.args:
        if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            return True
        mode = node.args[0].value
    if len(node.args) >= 2:
        if not isinstance(node.args[1], ast.Constant) or not isinstance(node.args[1].value, str):
            return True
        mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode":
            if not isinstance(keyword.value, ast.Constant) or not isinstance(keyword.value.value, str):
                return True
            mode = keyword.value.value
    if not mode:
        return False
    return any(marker in mode for marker in ("w", "a", "x", "+"))


def _python_assignment_value_is_unsafe(value: ast.AST | None, aliases: Mapping[str, str] | None = None) -> bool:
    if value is None:
        return False
    if isinstance(value, ast.Attribute):
        return _python_call_name_is_unsafe(_python_call_name(value, aliases))
    if isinstance(value, ast.Name):
        return _python_call_name_is_unsafe(_python_call_name(value, aliases))
    if isinstance(value, ast.Call):
        call_name = _python_call_name(value.func, aliases)
        if _python_call_is_local_network_probe(call_name, value, aliases or {}):
            return False
        return _python_call_name_is_unsafe(_python_call_name(value.func, aliases))
    return False


def _python_subprocess_call_uses_shell(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
            return bool(keyword.value.value)
    return False


def _python_subprocess_call_mentions_mutating_command(
    node: ast.Call,
    value_aliases: Mapping[str, list[str]] | None = None,
) -> bool:
    command_arg: ast.AST | None = node.args[0] if node.args else None
    for keyword in node.keywords:
        if keyword.arg == "args":
            command_arg = keyword.value
            break
    if command_arg is None:
        return False
    if isinstance(command_arg, ast.Constant) and isinstance(command_arg.value, str):
        return _python_string_mentions_mutating_command(command_arg.value)
    if isinstance(command_arg, ast.Name):
        tokens = (value_aliases or {}).get(command_arg.id)
        return True if tokens is None else _python_tokens_mention_mutating_command(tokens)
    if isinstance(command_arg, (ast.List, ast.Tuple)):
        tokens = _python_static_string_sequence(command_arg, value_aliases or {})
        if tokens is None:
            return True
        return _python_tokens_mention_mutating_command(tokens)
    tokens = _python_static_string_sequence(command_arg, value_aliases or {})
    if tokens is not None:
        return _python_tokens_mention_mutating_command(tokens)
    return True


def _python_string_mentions_mutating_command(value: str) -> bool:
    try:
        tokens = shlex.split(value)
    except ValueError:
        tokens = value.split()
    return _python_tokens_mention_mutating_command(tokens)


def _command_string_mentions_dangerous_operation(value: str) -> bool:
    try:
        tokens = shlex.split(value)
    except ValueError:
        tokens = value.split()
    regex_tokens = re.findall(r"[A-Za-z0-9_./+-]+", value)
    return (
        _python_tokens_mention_mutating_command(tokens)
        or _python_tokens_mention_mutating_command(regex_tokens)
        or _planner_string_mentions_network(value)
    )


def _planner_string_mentions_network(value: str) -> bool:
    lowered = value.lower()
    if "http://" in lowered or "https://" in lowered:
        return True
    if "net/http" in lowered or "net::http" in lowered or "require('http')" in lowered or 'require("http")' in lowered:
        return True
    if "require('https')" in lowered or 'require("https")' in lowered:
        return True
    words = {_basename(token) for token in re.findall(r"[A-Za-z0-9_./+-]+", value)}
    return bool(words & ((_NETWORK_TOKENS - {"git"}) | {"ls-remote"}))


def _planner_string_mentions_package_install(value: str) -> bool:
    words = {_basename(token) for token in re.findall(r"[A-Za-z0-9_./+-]+", value)}
    return bool(words & _PACKAGE_INSTALL_TOKENS and words & {"add", "i", "install", "uninstall"})


def _python_tokens_mention_mutating_command(tokens: list[str]) -> bool:
    if not tokens:
        return False
    basenames = [_basename(token) for token in tokens]
    if _python_tokens_are_read_only_package_probe(tokens):
        return False
    if set(basenames) & (
        _SOURCE_MUTATION_TOKENS
        | _PACKAGE_INSTALL_TOKENS
        | (_NETWORK_TOKENS - {"git"})
        | _BACKGROUND_TOKENS
        | _SHELL_TOKENS
        | _PRIVILEGED_TOKENS
    ):
        return True
    for index, token in enumerate(basenames):
        if token != "git":
            continue
        subcommand = _first_git_subcommand(basenames[index + 1 :])
        if subcommand in _UNSAFE_INLINE_PYTHON_GIT_SUBCOMMANDS:
            return True
    return False


def _python_tokens_are_read_only_package_probe(tokens: list[str]) -> bool:
    basenames = [_basename(token) for token in tokens]
    if "--dry-run" not in basenames:
        return False
    if not any(item in {"install", "i"} for item in basenames):
        return False
    if _python_tokens_include_pip_write_flag(tokens):
        return False
    if not _python_tokens_use_local_package_source(tokens):
        return False
    if basenames and basenames[0] in {"pip", "pip3"}:
        return True
    for index, token in enumerate(basenames[:-2]):
        if token == "-m" and basenames[index + 1] in {"pip", "pip3"}:
            return True
    return False


def _python_tokens_include_pip_write_flag(tokens: list[str]) -> bool:
    write_flags = {
        "--cache-dir",
        "--log",
        "--prefix",
        "--report",
        "--root",
        "--src",
        "--target",
    }
    return any(token in write_flags or any(token.startswith(f"{flag}=") for flag in write_flags) for token in tokens)


def _python_tokens_use_local_package_source(tokens: list[str]) -> bool:
    if any(_is_remote_package_reference(token) for token in tokens):
        return False
    source_values: list[str] = []
    for flag in ("--index-url", "-i", "--extra-index-url", "--find-links", "-f"):
        for index, token in enumerate(tokens):
            if token == flag and index + 1 < len(tokens):
                source_values.append(tokens[index + 1])
            elif token.startswith(f"{flag}="):
                source_values.append(token.split("=", 1)[1])
    if any(value and not _is_local_package_source(value) for value in source_values):
        return False
    if source_values:
        return True
    return "--no-index" in tokens


def _is_local_package_source(value: str) -> bool:
    if _is_local_http_url(value):
        return True
    parsed = urlparse(value)
    if parsed.scheme in {"", "file"}:
        return True
    return False


def _is_remote_package_reference(value: str) -> bool:
    candidate = str(value or "")
    if candidate.startswith("--") and "=" in candidate:
        candidate = candidate.split("=", 1)[1]
    elif candidate.startswith(("-r", "-c")) and not candidate.startswith("--") and len(candidate) > 2:
        candidate = candidate[2:]
    parsed = urlparse(value)
    if candidate != value:
        parsed = urlparse(candidate)
    if not parsed.scheme:
        return False
    if parsed.scheme in {"http", "https"}:
        return not _is_local_http_url(candidate)
    if parsed.scheme == "file":
        return False
    return "://" in candidate


def _is_local_http_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return False
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _first_git_subcommand(tokens: list[str]) -> str:
    options_with_values = {
        "-C",
        "-c",
        "--exec-path",
        "--git-dir",
        "--namespace",
        "--super-prefix",
        "--work-tree",
    }
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token in options_with_values:
            index += 2
            continue
        if any(token.startswith(f"{option}=") for option in options_with_values if option.startswith("--")):
            index += 1
            continue
        if token.startswith("-"):
            index += 1
            continue
        return token
    return ""


def _split_command_tokens(command: str) -> tuple[str, ...]:
    try:
        return tuple(shlex.split(command))
    except ValueError:
        return ()


def _basename(token: str) -> str:
    return token.rsplit("/", 1)[-1] if token else ""


def _semantic_tokens(tokens: tuple[str, ...]) -> tuple[str, ...]:
    remaining = list(tokens)
    while remaining:
        first = _basename(remaining[0])
        if first == "env":
            remaining.pop(0)
            while remaining and _looks_like_assignment(remaining[0]):
                remaining.pop(0)
            continue
        if first == "command":
            remaining.pop(0)
            continue
        if _looks_like_assignment(remaining[0]):
            remaining.pop(0)
            continue
        break
    return tuple(remaining)


def _looks_like_assignment(token: str) -> bool:
    if "=" not in token or token.startswith("="):
        return False
    name = token.split("=", 1)[0]
    return name.replace("_", "").isalnum()


def _contains_self_pass_marker(command: str) -> bool:
    normalized = command.lower().replace(" ", "")
    return any(
        marker in normalized
        for marker in (
            "acceptance:pass",
            "process.exit(0)",
            "sys.exit(0)",
            "exit(0)",
        )
    )


def _contains_chain_operator(command: str) -> bool:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        return any(str(token) in {"&&", "||", ";", "|"} for token in lexer)
    except ValueError:
        return _contains_unquoted_control(command, (";", "|"))


def _contains_unquoted_control(command: str, controls: tuple[str, ...]) -> bool:
    in_single = False
    in_double = False
    escaped = False
    for char in command:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if not in_single and not in_double and char in controls:
            return True
    return False


def _contains_background_operator(command: str) -> bool:
    if "&&" in command:
        command = command.replace("&&", "")
    return _contains_unquoted_control(command, ("&",))


def _drop_empty(payload: Mapping[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in payload.items():
        if value in ("", None, (), [], {}):
            continue
        result[key] = value
    return result


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        return _json_safe(as_dict())
    return repr(value)


def _patch_proof_manifest(
    path: Path,
    *,
    decision_path: Path,
    digest: str,
    records: list[Mapping[str, object]],
) -> None:
    payload: dict[str, object] = {}
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            payload = loaded
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    summary = _decision_summary(records)
    payload["native_finish_gate_decisions_ref"] = decision_path.name
    payload["native_finish_gate_decisions_sha256"] = digest
    metrics["native_finish_gate_decisions"] = {
        "artifact_ref": decision_path.name,
        "artifact_sha256": digest,
        **summary,
    }
    payload["metrics"] = metrics
    _write_json(path, payload)


def _decision_summary(records: list[Mapping[str, object]]) -> dict[str, object]:
    return {
        "decision_count": len(records),
        "allow_count": sum(1 for record in records if record.get("result") == "allow"),
        "block_count": sum(1 for record in records if record.get("result") == "block"),
        "completed_count": sum(1 for record in records if record.get("lane_status") == "completed"),
        "done_candidate_count": sum(1 for record in records if record.get("done_candidate_id")),
        "legacy_finish_call_count": sum(
            1 for record in records if record.get("finish_call_id") and not record.get("done_candidate_id")
        ),
        "closeout_ref_count": sum(len(_strings(record.get("closeout_refs"))) for record in records),
        "observer_ref_count": sum(len(_strings(record.get("observer_refs"))) for record in records),
        "typed_evidence_warning_count": sum(
            1
            for record in records
            if _text(_mapping(record.get("closeout")).get("typed_evidence_projection_status")) == "warning"
        ),
        "unexpected_source_mutation_block_count": sum(
            1 for record in records if "closeout_unexpected_source_mutation" in _strings(record.get("blockers"))
        ),
    }


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)
