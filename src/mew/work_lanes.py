"""Work lane registry primitives.

This module is intentionally data-only for the first lane-registry slice. It
lets callers inspect lane capabilities without changing existing WorkTodo lane
normalization or mutating todo dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

TINY_LANE = "tiny"
IMPLEMENT_V1_LANE = "implement_v1"
IMPLEMENT_V2_LANE = "implement_v2"
MIRROR_LANE = "mirror"
DELIBERATION_LANE = "deliberation"

LANE_LAYOUT_LEGACY = "legacy"
LANE_LAYOUT_LANE_SCOPED = "lane_scoped"
LANE_LAYOUT_UNSUPPORTED = "unsupported"

LANE_ROLE_AUTHORITATIVE = "authoritative"
LANE_ROLE_MIRROR = "mirror"
LANE_ROLE_SHADOW = "shadow"
LANE_ROLE_UNSUPPORTED = "unsupported"

LANE_ATTEMPT_EVENT = "lane_attempt"
LANE_DISPLAY_IMPLEMENTATION = "implementation"
LANE_DISPLAY_UNSUPPORTED = "unsupported"

_LANE_DISPLAY_NAMES_BY_LANE = {
    TINY_LANE: LANE_DISPLAY_IMPLEMENTATION,
    IMPLEMENT_V1_LANE: "implementation_v1",
    IMPLEMENT_V2_LANE: "implementation_v2",
    MIRROR_LANE: MIRROR_LANE,
    DELIBERATION_LANE: DELIBERATION_LANE,
}


@dataclass(frozen=True)
class WorkLaneView:
    """Derived capabilities for a work lane lookup."""

    name: str
    supported: bool
    authoritative: bool
    write_capable: bool
    layout: str
    role: str
    requires_model_binding: bool = False
    fallback_lane: str = TINY_LANE
    runtime_available: bool = True


@dataclass(frozen=True)
class LaneAttemptTelemetryV0:
    """Minimum persisted v0 lane-attempt telemetry payload."""

    task_id: object
    session_id: object
    task_kind: str
    lane: str
    lane_display_name: str
    task_shape: str = ""
    blocker_code: str = ""
    model_backend: str = ""
    model: str = ""
    effort: str = ""
    timeout_seconds: object | None = None
    budget_reserved: object | None = None
    budget_spent_or_estimated: object | None = None
    first_output_latency_seconds: object | None = None
    first_edit_latency_seconds: object | None = None
    approval_rejected: bool = False
    verifier_failed: bool = False
    fallback_taken: bool = False
    rescue_edit_used: bool = False
    reviewer_decision: str = ""
    outcome: str = ""
    later_reuse_value: str = "unknown"
    event: str = field(default=LANE_ATTEMPT_EVENT, init=False)

    def as_event(self) -> dict[str, object]:
        """Return the stable v0 event dictionary."""

        return {
            "event": self.event,
            "task_id": self.task_id,
            "session_id": self.session_id,
            "task_kind": self.task_kind,
            "lane": self.lane,
            "lane_display_name": self.lane_display_name,
            "task_shape": self.task_shape,
            "blocker_code": self.blocker_code,
            "model_backend": self.model_backend,
            "model": self.model,
            "effort": self.effort,
            "timeout_seconds": self.timeout_seconds,
            "budget_reserved": self.budget_reserved,
            "budget_spent_or_estimated": self.budget_spent_or_estimated,
            "first_output_latency_seconds": self.first_output_latency_seconds,
            "first_edit_latency_seconds": self.first_edit_latency_seconds,
            "approval_rejected": self.approval_rejected,
            "verifier_failed": self.verifier_failed,
            "fallback_taken": self.fallback_taken,
            "rescue_edit_used": self.rescue_edit_used,
            "reviewer_decision": self.reviewer_decision,
            "outcome": self.outcome,
            "later_reuse_value": self.later_reuse_value,
        }


_SUPPORTED_WORK_LANES: tuple[WorkLaneView, ...] = (
    WorkLaneView(
        name=TINY_LANE,
        supported=True,
        authoritative=True,
        write_capable=True,
        layout=LANE_LAYOUT_LEGACY,
        role=LANE_ROLE_AUTHORITATIVE,
    ),
    WorkLaneView(
        name=IMPLEMENT_V1_LANE,
        supported=True,
        authoritative=True,
        write_capable=True,
        layout=LANE_LAYOUT_LANE_SCOPED,
        role=LANE_ROLE_AUTHORITATIVE,
        fallback_lane=TINY_LANE,
    ),
    WorkLaneView(
        name=IMPLEMENT_V2_LANE,
        supported=True,
        authoritative=True,
        write_capable=True,
        layout=LANE_LAYOUT_LANE_SCOPED,
        role=LANE_ROLE_AUTHORITATIVE,
        requires_model_binding=True,
        fallback_lane=IMPLEMENT_V1_LANE,
        runtime_available=True,
    ),
    WorkLaneView(
        name=MIRROR_LANE,
        supported=True,
        authoritative=False,
        write_capable=False,
        layout=LANE_LAYOUT_LANE_SCOPED,
        role=LANE_ROLE_MIRROR,
    ),
    WorkLaneView(
        name=DELIBERATION_LANE,
        supported=True,
        authoritative=False,
        write_capable=False,
        layout=LANE_LAYOUT_LANE_SCOPED,
        role=LANE_ROLE_SHADOW,
        requires_model_binding=True,
    ),
)

_WORK_LANES_BY_NAME = {lane.name: lane for lane in _SUPPORTED_WORK_LANES}


def _canonical_lane_name(lane: object) -> str:
    lane_name = "" if lane is None else str(lane).strip()
    return lane_name or TINY_LANE


def list_supported_work_lanes() -> tuple[WorkLaneView, ...]:
    """Return supported work lanes in registry order."""

    return _SUPPORTED_WORK_LANES


def get_work_lane_view(lane: object) -> WorkLaneView:
    """Return a derived view for a lane name.

    Unknown lane strings are represented as unsupported views instead of being
    rewritten. Missing or empty lane values follow the legacy tiny default.
    """

    lane_name = _canonical_lane_name(lane)
    supported_lane = _WORK_LANES_BY_NAME.get(lane_name)
    if supported_lane is not None:
        return supported_lane
    return WorkLaneView(
        name=lane_name,
        supported=False,
        authoritative=False,
        write_capable=False,
        layout=LANE_LAYOUT_UNSUPPORTED,
        role=LANE_ROLE_UNSUPPORTED,
        runtime_available=False,
    )


def get_work_todo_lane_view(todo: Mapping[str, object] | None) -> WorkLaneView:
    """Return a lane view for a WorkTodo-like mapping without mutating it."""

    if not isinstance(todo, Mapping):
        return get_work_lane_view(None)
    return get_work_lane_view(todo.get("lane"))


def _lane_display_name(lane: WorkLaneView) -> str:
    if not lane.supported:
        return LANE_DISPLAY_UNSUPPORTED
    return _LANE_DISPLAY_NAMES_BY_LANE.get(lane.name, lane.name)


def build_lane_attempt_event(
    *,
    task_id: object,
    session_id: object,
    task_kind: str,
    lane: object = None,
    task_shape: str = "",
    blocker_code: str = "",
    model_backend: str = "",
    model: str = "",
    effort: str = "",
    timeout_seconds: object | None = None,
    budget_reserved: object | None = None,
    budget_spent_or_estimated: object | None = None,
    first_output_latency_seconds: object | None = None,
    first_edit_latency_seconds: object | None = None,
    approval_rejected: bool = False,
    verifier_failed: bool = False,
    fallback_taken: bool = False,
    rescue_edit_used: bool = False,
    reviewer_decision: str = "",
    outcome: str = "",
    later_reuse_value: str = "unknown",
) -> dict[str, object]:
    """Build the minimum v0 lane_attempt telemetry event without side effects."""

    lane_view = get_work_lane_view(lane)
    return LaneAttemptTelemetryV0(
        task_id=task_id,
        session_id=session_id,
        task_kind=task_kind,
        lane=lane_view.name,
        lane_display_name=_lane_display_name(lane_view),
        task_shape=task_shape,
        blocker_code=blocker_code,
        model_backend=model_backend,
        model=model,
        effort=effort,
        timeout_seconds=timeout_seconds,
        budget_reserved=budget_reserved,
        budget_spent_or_estimated=budget_spent_or_estimated,
        first_output_latency_seconds=first_output_latency_seconds,
        first_edit_latency_seconds=first_edit_latency_seconds,
        approval_rejected=approval_rejected,
        verifier_failed=verifier_failed,
        fallback_taken=fallback_taken,
        rescue_edit_used=rescue_edit_used,
        reviewer_decision=reviewer_decision,
        outcome=outcome,
        later_reuse_value=later_reuse_value,
    ).as_event()


__all__ = [
    "DELIBERATION_LANE",
    "IMPLEMENT_V1_LANE",
    "IMPLEMENT_V2_LANE",
    "LANE_ATTEMPT_EVENT",
    "LANE_DISPLAY_IMPLEMENTATION",
    "LANE_DISPLAY_UNSUPPORTED",
    "LANE_LAYOUT_LANE_SCOPED",
    "LANE_LAYOUT_LEGACY",
    "LANE_LAYOUT_UNSUPPORTED",
    "LANE_ROLE_AUTHORITATIVE",
    "LANE_ROLE_MIRROR",
    "LANE_ROLE_SHADOW",
    "LANE_ROLE_UNSUPPORTED",
    "MIRROR_LANE",
    "TINY_LANE",
    "LaneAttemptTelemetryV0",
    "WorkLaneView",
    "build_lane_attempt_event",
    "get_work_lane_view",
    "get_work_todo_lane_view",
    "list_supported_work_lanes",
]
