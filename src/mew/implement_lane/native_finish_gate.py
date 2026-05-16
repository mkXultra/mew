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

from dataclasses import dataclass, field
import hashlib
import json
from typing import Literal, Mapping


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
    "auto_detected_verifier",
    "finish_verifier_planner",
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
    finish_call_id: str
    finish_arguments: Mapping[str, object]
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
    blockers: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    closeout_refs: tuple[str, ...] = ()
    observer_refs: tuple[str, ...] = ()
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
            "lane_status": self.lane_status,
            "result": self.result,
            "closeout": self.closeout.as_dict(),
            "blockers": list(self.blockers),
            "missing_obligations": list(self.missing_obligations),
            "evidence_refs": list(self.evidence_refs),
            "closeout_refs": list(self.closeout_refs),
            "observer_refs": list(self.observer_refs),
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
    for command in (request.configured_command, request.auto_detected_command, request.planner_command):
        if command is None:
            continue
        if command.source not in allowed:
            continue
        if not command.normalized_command():
            continue
        return command
    return None


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
            "lane_status": decision.lane_status,
            "result": decision.result,
            "reason": decision.reason,
            "blockers": list(decision.blockers),
            "missing_obligations": list(decision.missing_obligations),
            "evidence_refs": list(decision.evidence_refs),
            "closeout_refs": list(decision.closeout_refs),
            "observer_refs": list(decision.observer_refs),
            "closeout_status": decision.closeout.status,
            "closeout_exit_code": decision.closeout.exit_code,
            "closeout_timed_out": decision.closeout.timed_out,
            "typed_evidence_projection_status": decision.closeout.typed_evidence_projection_status,
            "diagnostic_resolver_record": dict(decision.diagnostic_resolver_record),
        }
    )


def build_decision_id(*, lane_attempt_id: str, turn_id: str, finish_call_id: str, policy_version: str) -> str:
    """Return a deterministic decision id for sidecar/replay records."""

    digest = hashlib.sha256(
        json.dumps(
            {
                "finish_call_id": finish_call_id,
                "lane_attempt_id": lane_attempt_id,
                "policy_version": policy_version,
                "turn_id": turn_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"native-finish-gate:{turn_id}:{finish_call_id}:{digest}"


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
