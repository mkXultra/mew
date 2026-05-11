"""Shared implementation-lane contract types.

These dataclasses are deliberately small and serializable. They are the
boundary that lets implement_v1 and implement_v2 evolve independently while
still producing comparable artifacts for M6.24.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TOOL_CALL_SCHEMA_VERSION = 1
TOOL_RESULT_SCHEMA_VERSION = 1
PROOF_MANIFEST_SCHEMA_VERSION = 1

TranscriptEventKind = Literal[
    "model_message",
    "tool_call",
    "tool_result",
    "approval",
    "verifier",
    "finish",
]

ToolCallStatus = Literal["received", "validated", "rejected", "executing", "completed"]
ToolResultStatus = Literal[
    "completed",
    "failed",
    "denied",
    "invalid",
    "interrupted",
    "running",
    "yielded",
]


@dataclass(frozen=True)
class ImplementLaneInput:
    """Minimum input passed into an implementation lane runtime."""

    work_session_id: str
    task_id: str
    workspace: str
    lane: str
    model_backend: str = ""
    model: str = ""
    effort: str = ""
    task_contract: dict[str, object] = field(default_factory=dict)
    lane_config: dict[str, object] = field(default_factory=dict)
    persisted_lane_state: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "work_session_id": self.work_session_id,
            "task_id": self.task_id,
            "workspace": self.workspace,
            "lane": self.lane,
            "model_backend": self.model_backend,
            "model": self.model,
            "effort": self.effort,
            "task_contract": dict(self.task_contract),
            "lane_config": dict(self.lane_config),
            "persisted_lane_state": dict(self.persisted_lane_state),
        }


@dataclass(frozen=True)
class ToolCallEnvelope:
    """Provider-neutral representation of one provider-native tool call."""

    lane_attempt_id: str
    provider: str
    provider_call_id: str
    mew_tool_call_id: str
    tool_name: str
    arguments: dict[str, object] = field(default_factory=dict)
    provider_message_id: str = ""
    turn_index: int = 0
    sequence_index: int = 0
    raw_arguments_ref: str = ""
    received_at: str = ""
    status: ToolCallStatus = "received"
    schema_version: int = field(default=TOOL_CALL_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane_attempt_id": self.lane_attempt_id,
            "provider": self.provider,
            "provider_message_id": self.provider_message_id,
            "provider_call_id": self.provider_call_id,
            "mew_tool_call_id": self.mew_tool_call_id,
            "turn_index": self.turn_index,
            "sequence_index": self.sequence_index,
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "raw_arguments_ref": self.raw_arguments_ref,
            "received_at": self.received_at,
            "status": self.status,
        }


@dataclass(frozen=True)
class ToolResultEnvelope:
    """Provider-neutral representation of the paired result for a tool call."""

    lane_attempt_id: str
    provider_call_id: str
    mew_tool_call_id: str
    tool_name: str
    status: ToolResultStatus
    is_error: bool = False
    content: tuple[object, ...] = ()
    content_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    side_effects: tuple[dict[str, object], ...] = ()
    started_at: str = ""
    finished_at: str = ""
    schema_version: int = field(default=TOOL_RESULT_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane_attempt_id": self.lane_attempt_id,
            "provider_call_id": self.provider_call_id,
            "mew_tool_call_id": self.mew_tool_call_id,
            "tool_name": self.tool_name,
            "status": self.status,
            "is_error": self.is_error,
            "content": list(self.content),
            "content_refs": list(self.content_refs),
            "evidence_refs": list(self.evidence_refs),
            "side_effects": [dict(effect) for effect in self.side_effects],
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    def provider_visible_content(self) -> dict[str, object]:
        """Return content suitable for provider tool_result payloads."""

        return {
            "mew_status": self.status,
            "acceptance_evidence": bool(self.evidence_refs) and self.status == "completed",
            "natural_result_text": self.natural_result_text(),
            "content": list(self.content),
            "content_refs": list(self.content_refs),
            "output_refs": list(self.content_refs),
            "evidence_refs": list(self.evidence_refs),
            "side_effects": [dict(effect) for effect in self.side_effects],
        }

    def natural_result_text(self, *, limit: int = 1200) -> str:
        """Return a compact natural-language result for the next model turn."""

        parts = [f"{self.tool_name or 'tool'} result: {self.status}"]
        if self.is_error:
            parts.append("error=true")
        payload = self.content[0] if self.content and isinstance(self.content[0], dict) else {}
        if payload:
            for key in (
                "summary",
                "reason",
                "status",
                "exit_code",
                "path",
                "command_run_id",
                "output_ref",
                "failure_class",
                "failure_kind",
            ):
                value = payload.get(key)
                if value not in (None, "", [], {}):
                    parts.append(f"{key}={value}")
            for key in ("stderr_tail", "stdout_tail", "text", "content"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    compact = " ".join(value.strip().split())
                    parts.append(f"{key}: {compact}")
                    break
        if self.content_refs:
            parts.append("output_refs=" + ",".join(self.content_refs[:4]))
        if self.evidence_refs:
            parts.append("evidence_refs=" + ",".join(self.evidence_refs[:4]))
        text = "; ".join(str(part) for part in parts if str(part).strip())
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."


@dataclass(frozen=True)
class ImplementLaneTranscriptEvent:
    """Replayable transcript event emitted by an implementation lane."""

    kind: TranscriptEventKind
    lane: str
    turn_id: str
    event_id: str
    payload: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "lane": self.lane,
            "turn_id": self.turn_id,
            "event_id": self.event_id,
            "payload": dict(self.payload),
        }


@dataclass(frozen=True)
class ImplementLaneProofManifest:
    """Minimum v2 proof manifest shape for replay and M6.24 attribution."""

    lane: str
    lane_attempt_id: str
    artifact_namespace: str
    tool_calls: tuple[ToolCallEnvelope, ...] = ()
    tool_results: tuple[ToolResultEnvelope, ...] = ()
    metrics: dict[str, object] = field(default_factory=dict)
    schema_version: int = field(default=PROOF_MANIFEST_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane": self.lane,
            "lane_attempt_id": self.lane_attempt_id,
            "artifact_namespace": self.artifact_namespace,
            "tool_calls": [call.as_dict() for call in self.tool_calls],
            "tool_results": [result.as_dict() for result in self.tool_results],
            "metrics": dict(self.metrics),
        }


@dataclass(frozen=True)
class ImplementLaneResult:
    """Comparable result shape for implementation lane runtimes."""

    status: str
    lane: str
    user_visible_summary: str = ""
    proof_artifacts: tuple[str, ...] = ()
    next_reentry_hint: dict[str, object] = field(default_factory=dict)
    updated_lane_state: dict[str, object] = field(default_factory=dict)
    metrics: dict[str, object] = field(default_factory=dict)
    transcript: tuple[ImplementLaneTranscriptEvent, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "lane": self.lane,
            "user_visible_summary": self.user_visible_summary,
            "proof_artifacts": list(self.proof_artifacts),
            "next_reentry_hint": dict(self.next_reentry_hint),
            "updated_lane_state": dict(self.updated_lane_state),
            "metrics": dict(self.metrics),
            "transcript": [event.as_dict() for event in self.transcript],
        }


__all__ = [
    "ImplementLaneInput",
    "ImplementLaneProofManifest",
    "ImplementLaneResult",
    "ImplementLaneTranscriptEvent",
    "PROOF_MANIFEST_SCHEMA_VERSION",
    "TOOL_CALL_SCHEMA_VERSION",
    "TOOL_RESULT_SCHEMA_VERSION",
    "TranscriptEventKind",
    "ToolCallEnvelope",
    "ToolCallStatus",
    "ToolResultEnvelope",
    "ToolResultStatus",
]
