"""Shared implementation-lane contract types.

These dataclasses are deliberately small and serializable. They are the
boundary that lets implement_v1 and implement_v2 evolve independently while
still producing comparable artifacts for M6.24.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TranscriptEventKind = Literal[
    "model_message",
    "tool_call",
    "tool_result",
    "approval",
    "verifier",
    "finish",
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
    "ImplementLaneResult",
    "ImplementLaneTranscriptEvent",
    "TranscriptEventKind",
]
