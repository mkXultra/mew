"""Implementation-lane runtime registry.

The work-lane registry answers "what lane is this todo on?". This module
answers the narrower M6.23.2 question: "which implementation runtime owns that
lane?" Keeping the mapping here prevents implement_v2 scaffolding from leaking
into the existing v1 work loop.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..work_lanes import IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE, TINY_LANE, WorkLaneView, get_work_lane_view
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID

IMPLEMENT_LANE_REGISTRY_VERSION = 1


@dataclass(frozen=True)
class ImplementLaneRuntimeView:
    """Derived runtime capabilities for an implementation lane."""

    lane: str
    runtime_id: str
    version: int
    default: bool
    runtime_available: bool
    provider_native_tool_loop: bool
    writes_allowed: bool
    fallback_lane: str
    work_lane: WorkLaneView


_IMPLEMENT_RUNTIMES: tuple[ImplementLaneRuntimeView, ...] = (
    ImplementLaneRuntimeView(
        lane=IMPLEMENT_V1_LANE,
        runtime_id="implement_v1_json_think_act",
        version=1,
        default=True,
        runtime_available=True,
        provider_native_tool_loop=False,
        writes_allowed=True,
        fallback_lane=TINY_LANE,
        work_lane=get_work_lane_view(IMPLEMENT_V1_LANE),
    ),
    ImplementLaneRuntimeView(
        lane=IMPLEMENT_V2_LANE,
        runtime_id=IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        version=2,
        default=False,
        runtime_available=True,
        provider_native_tool_loop=True,
        writes_allowed=True,
        fallback_lane=IMPLEMENT_V1_LANE,
        work_lane=get_work_lane_view(IMPLEMENT_V2_LANE),
    ),
)

_IMPLEMENT_RUNTIMES_BY_LANE = {runtime.lane: runtime for runtime in _IMPLEMENT_RUNTIMES}


def list_implement_lane_runtime_views() -> tuple[ImplementLaneRuntimeView, ...]:
    """Return implementation runtimes in stable registry order."""

    return _IMPLEMENT_RUNTIMES


def get_implement_lane_runtime_view(lane: object) -> ImplementLaneRuntimeView:
    """Return a runtime view for an implementation lane.

    Missing, empty, and legacy ``tiny`` lanes resolve to implement_v1 without
    rewriting the persisted todo lane. Unknown lanes also resolve to v1 so the
    current implementation path remains conservative.
    """

    lane_name = "" if lane is None else str(lane).strip()
    if lane_name in ("", TINY_LANE):
        return _IMPLEMENT_RUNTIMES_BY_LANE[IMPLEMENT_V1_LANE]
    runtime = _IMPLEMENT_RUNTIMES_BY_LANE.get(lane_name)
    if runtime is not None:
        return runtime
    return _IMPLEMENT_RUNTIMES_BY_LANE[IMPLEMENT_V1_LANE]


def select_implement_lane_runtime(*, requested_lane: object = None, allow_v2: bool = False) -> ImplementLaneRuntimeView:
    """Select the implementation runtime without changing v1 defaults.

    Missing, legacy, and unknown lanes still select v1. An explicit
    ``implement_v2`` request returns the v2 runtime view and must not be
    silently routed through v1.
    """

    return get_implement_lane_runtime_view(requested_lane)


__all__ = [
    "IMPLEMENT_LANE_REGISTRY_VERSION",
    "ImplementLaneRuntimeView",
    "get_implement_lane_runtime_view",
    "list_implement_lane_runtime_views",
    "select_implement_lane_runtime",
]
