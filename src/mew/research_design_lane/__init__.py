"""Research-design lane bootstrap.

This first slice intentionally clones the live ``implement_v2`` native path
behind an independent lane id. Later slices can replace the prompt, tools, and
completion policy with paper-reading and hypothesis-to-design behavior without
touching the implementation lane route.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

from ..implement_lane import IMPLEMENT_V2_NATIVE_RUNTIME_ID, ImplementLaneInput, ImplementLaneResult
from ..implement_lane import run_live_native_implement_v2 as _run_live_native_implement_v2
from ..work_lanes import IMPLEMENT_V2_LANE, RESEARCH_DESIGN_LANE


RESEARCH_DESIGN_NATIVE_RUNTIME_ID = "research_design_native_implement_v2_clone"


def run_live_native_research_design(
    lane_input: ImplementLaneInput,
    *,
    model_auth: Mapping[str, object],
    base_url: str = "",
    timeout: float = 60.0,
    max_turns: int = 10,
    progress=None,
) -> ImplementLaneResult:
    """Run the initial research-design lane through the cloned v2 native path."""

    lane_config = dict(lane_input.lane_config)
    lane_config.setdefault("clone_source_lane", IMPLEMENT_V2_LANE)
    lane_config.setdefault("clone_source_runtime_id", IMPLEMENT_V2_NATIVE_RUNTIME_ID)
    lane_config.setdefault("target_output_kind", "research_design_document")
    cloned_input = replace(
        lane_input,
        lane=RESEARCH_DESIGN_LANE,
        lane_config=lane_config,
    )
    result = _run_live_native_implement_v2(
        cloned_input,
        model_auth=model_auth,
        base_url=base_url,
        timeout=timeout,
        max_turns=max_turns,
        progress=progress,
    )
    return _with_research_design_identity(result)


def _with_research_design_identity(result: ImplementLaneResult) -> ImplementLaneResult:
    metrics = dict(result.metrics)
    metrics.setdefault("clone_source_lane", IMPLEMENT_V2_LANE)
    metrics.setdefault("clone_source_runtime_id", IMPLEMENT_V2_NATIVE_RUNTIME_ID)
    metrics["runtime_id"] = RESEARCH_DESIGN_NATIVE_RUNTIME_ID
    updated_lane_state = dict(result.updated_lane_state)
    updated_lane_state.setdefault("clone_source_lane", IMPLEMENT_V2_LANE)
    updated_lane_state.setdefault("clone_source_runtime_id", IMPLEMENT_V2_NATIVE_RUNTIME_ID)
    updated_lane_state["runtime_id"] = RESEARCH_DESIGN_NATIVE_RUNTIME_ID
    next_reentry_hint = dict(result.next_reentry_hint)
    next_reentry_hint.setdefault("fallback_lane", IMPLEMENT_V2_LANE)
    return ImplementLaneResult(
        status=result.status,
        lane=RESEARCH_DESIGN_LANE,
        user_visible_summary=result.user_visible_summary,
        proof_artifacts=tuple(result.proof_artifacts),
        next_reentry_hint=next_reentry_hint,
        updated_lane_state=updated_lane_state,
        metrics=metrics,
        transcript=tuple(result.transcript),
    )


__all__ = [
    "RESEARCH_DESIGN_NATIVE_RUNTIME_ID",
    "run_live_native_research_design",
]
