"""V1 implementation-lane adapter metadata.

M6.23.2 does not move the existing v1 work loop. This adapter gives callers a
stable descriptor for the legacy implementation runtime so v2 can be added
beside it instead of inside it.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..work_lanes import IMPLEMENT_V1_LANE, TINY_LANE
from .registry import get_implement_lane_runtime_view
from .transcript import lane_artifact_namespace


@dataclass(frozen=True)
class ImplementV1AdapterDescriptor:
    lane: str
    legacy_lane: str
    runtime_id: str
    artifact_namespace: str
    behavior: str = "existing_json_think_act_loop"

    def as_dict(self) -> dict[str, object]:
        return {
            "lane": self.lane,
            "legacy_lane": self.legacy_lane,
            "runtime_id": self.runtime_id,
            "artifact_namespace": self.artifact_namespace,
            "behavior": self.behavior,
        }


def describe_implement_v1_adapter(*, work_session_id: object, task_id: object) -> ImplementV1AdapterDescriptor:
    """Describe the v1 adapter without executing the legacy loop."""

    runtime = get_implement_lane_runtime_view(IMPLEMENT_V1_LANE)
    return ImplementV1AdapterDescriptor(
        lane=runtime.lane,
        legacy_lane=TINY_LANE,
        runtime_id=runtime.runtime_id,
        artifact_namespace=lane_artifact_namespace(
            work_session_id=work_session_id,
            task_id=task_id,
            lane=runtime.lane,
        ),
    )


__all__ = ["ImplementV1AdapterDescriptor", "describe_implement_v1_adapter"]
