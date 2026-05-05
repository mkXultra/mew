"""M6.24 reentry A/B gate for implementation lanes."""

from __future__ import annotations

from dataclasses import dataclass

from ..work_lanes import IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE
from .transcript import lane_artifact_namespace
from .types import ImplementLaneResult
from .v1_adapter import describe_implement_v1_adapter

SUPPORTED_M6_24_REENTRY_LANES = frozenset({IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE})


@dataclass(frozen=True)
class M624ReentryABGateResult:
    """Deterministic decision record for resuming M6.24 after lane isolation."""

    status: str
    selected_lane: str
    can_resume_m6_24: bool
    reasons: tuple[str, ...]
    v1_artifact_namespace: str
    v2_artifact_namespace: str
    lane_decision: dict[str, object]
    metrics: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "selected_lane": self.selected_lane,
            "can_resume_m6_24": self.can_resume_m6_24,
            "reasons": list(self.reasons),
            "v1_artifact_namespace": self.v1_artifact_namespace,
            "v2_artifact_namespace": self.v2_artifact_namespace,
            "lane_decision": dict(self.lane_decision),
            "metrics": dict(self.metrics),
        }


def evaluate_m6_24_reentry_ab_gate(
    *,
    work_session_id: object,
    task_id: object,
    selected_lane: object,
    v2_result: ImplementLaneResult | dict[str, object] | None,
    v1_baseline_valid: bool,
    v1_lane_attempt_id: object = "",
) -> M624ReentryABGateResult:
    """Return whether M6.24 may resume with explicit lane attribution."""

    selected = str(selected_lane or "").strip()
    v1_descriptor = describe_implement_v1_adapter(work_session_id=work_session_id, task_id=task_id)
    v1_namespace = v1_descriptor.artifact_namespace
    v2_namespace = lane_artifact_namespace(work_session_id=work_session_id, task_id=task_id, lane=IMPLEMENT_V2_LANE)
    v2 = _result_dict(v2_result)
    v2_metrics = _dict_at(v2, "metrics")
    v2_state = _dict_at(v2, "updated_lane_state")
    v2_manifest = _dict_at(v2_state, "proof_manifest")
    v2_manifest_namespace = str(v2_manifest.get("artifact_namespace") or "")
    v2_manifest_lane = str(v2_manifest.get("lane") or "")
    v2_manifest_attempt_id = str(v2_manifest.get("lane_attempt_id") or "")
    v2_replay_valid = v2_metrics.get("replay_valid") is True
    artifact_collision = v1_namespace == v2_namespace or (bool(v2_manifest_namespace) and v2_manifest_namespace == v1_namespace)

    reasons: list[str] = []
    if selected not in SUPPORTED_M6_24_REENTRY_LANES:
        reasons.append("explicit_supported_lane_selection_required")
    if not v1_baseline_valid:
        reasons.append("v1_baseline_not_valid")
    if artifact_collision:
        reasons.append("v1_v2_artifact_namespace_collision")
    if not v2:
        reasons.append("v2_probe_result_required")
    if v2 and str(v2.get("lane") or "") != IMPLEMENT_V2_LANE:
        reasons.append("v2_probe_result_wrong_lane")
    if v2 and not v2_replay_valid:
        reasons.append("v2_probe_replay_not_valid")
    if v2 and v2_manifest_lane != IMPLEMENT_V2_LANE:
        reasons.append("v2_manifest_wrong_lane")
    if v2 and not v2_manifest_attempt_id:
        reasons.append("v2_manifest_missing_lane_attempt_id")
    if v2 and v2_manifest_namespace != v2_namespace:
        reasons.append("v2_manifest_namespace_mismatch")

    can_resume = not reasons
    selected_lane_attempt_id = (
        str(v1_lane_attempt_id or f"{IMPLEMENT_V1_LANE}:{work_session_id}:{task_id}:baseline")
        if selected == IMPLEMENT_V1_LANE
        else v2_manifest_attempt_id
    )
    selected_namespace = v1_namespace if selected == IMPLEMENT_V1_LANE else v2_manifest_namespace
    lane_decision = {
        "milestone": "M6.24",
        "selected_lane": selected,
        "selected_lane_attempt_id": selected_lane_attempt_id,
        "selected_artifact_namespace": selected_namespace,
        "requires_explicit_lane_in_future_proofs": True,
        "fallback_execution_counted": False,
        "m6_24_may_resume": can_resume,
    }
    metrics = {
        "v1_baseline_valid": bool(v1_baseline_valid),
        "v1_runtime_id": v1_descriptor.runtime_id,
        "v2_probe_present": bool(v2),
        "v2_replay_valid": bool(v2_replay_valid),
        "v2_status": str(v2.get("status") or "") if v2 else "",
        "artifact_collision": artifact_collision,
        "selected_lane_supported": selected in SUPPORTED_M6_24_REENTRY_LANES,
    }
    return M624ReentryABGateResult(
        status="ready" if can_resume else "blocked",
        selected_lane=selected,
        can_resume_m6_24=can_resume,
        reasons=tuple(reasons),
        v1_artifact_namespace=v1_namespace,
        v2_artifact_namespace=v2_namespace,
        lane_decision=lane_decision,
        metrics=metrics,
    )


def _result_dict(result: ImplementLaneResult | dict[str, object] | None) -> dict[str, object]:
    if result is None:
        return {}
    if isinstance(result, ImplementLaneResult):
        return result.as_dict()
    if isinstance(result, dict):
        return dict(result)
    return {}


def _dict_at(data: dict[str, object], key: str) -> dict[str, object]:
    value = data.get(key)
    return dict(value) if isinstance(value, dict) else {}


__all__ = [
    "M624ReentryABGateResult",
    "SUPPORTED_M6_24_REENTRY_LANES",
    "evaluate_m6_24_reentry_ab_gate",
]
