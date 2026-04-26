"""Work lane registry primitives.

This module is intentionally data-only for the first lane-registry slice. It
lets callers inspect lane capabilities without changing existing WorkTodo lane
normalization or mutating todo dictionaries.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

TINY_LANE = "tiny"
MIRROR_LANE = "mirror"
DELIBERATION_LANE = "deliberation"

LANE_LAYOUT_LEGACY = "legacy"
LANE_LAYOUT_LANE_SCOPED = "lane_scoped"
LANE_LAYOUT_UNSUPPORTED = "unsupported"

LANE_ROLE_AUTHORITATIVE = "authoritative"
LANE_ROLE_MIRROR = "mirror"
LANE_ROLE_SHADOW = "shadow"
LANE_ROLE_UNSUPPORTED = "unsupported"


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
    )


def get_work_todo_lane_view(todo: Mapping[str, object] | None) -> WorkLaneView:
    """Return a lane view for a WorkTodo-like mapping without mutating it."""

    if not isinstance(todo, Mapping):
        return get_work_lane_view(None)
    return get_work_lane_view(todo.get("lane"))


__all__ = [
    "DELIBERATION_LANE",
    "LANE_LAYOUT_LANE_SCOPED",
    "LANE_LAYOUT_LEGACY",
    "LANE_LAYOUT_UNSUPPORTED",
    "LANE_ROLE_AUTHORITATIVE",
    "LANE_ROLE_MIRROR",
    "LANE_ROLE_SHADOW",
    "LANE_ROLE_UNSUPPORTED",
    "MIRROR_LANE",
    "TINY_LANE",
    "WorkLaneView",
    "get_work_lane_view",
    "get_work_todo_lane_view",
    "list_supported_work_lanes",
]
