"""Prompt section assembly for the default-off implement_v2 lane."""

from __future__ import annotations

import json

from ..prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_DYNAMIC,
    CACHE_POLICY_SESSION,
    STABILITY_DYNAMIC,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    PromptSection,
    prompt_section_metrics,
)
from .tool_policy import ImplementLaneToolSpec, list_v2_tool_specs_for_mode
from .types import ImplementLaneInput


def build_implement_v2_prompt_sections(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
) -> list[PromptSection]:
    """Build provider-neutral v2 prompt sections without provider cache transport."""

    mode = str(lane_input.lane_config.get("mode") or "read_only")
    specs = tool_specs if tool_specs is not None else list_v2_tool_specs_for_mode(mode)
    sections = [
        PromptSection(
            id="implement_v2_lane_base",
            version="v0",
            title="Implement V2 Lane Base",
            content=(
                "You are running inside the default-off implement_v2 lane. "
                "Use provider-native tool calls, preserve paired tool results, "
                "and finish only through deterministic mew acceptance evidence."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_tool_contract",
            version="v0",
            title="Implement V2 Tool Contract",
            content=(
                "Every provider tool call must receive exactly one paired tool result. "
                "Unknown, invalid, denied, interrupted, or failed calls still receive "
                "model-visible results. Running/yielded command states are content "
                "inside normal tool results, not provider protocol states."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_tool_surface",
            version="v0",
            title="Implement V2 Tool Surface",
            content=_tool_surface_json(specs),
            stability=STABILITY_SEMI_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_task_contract",
            version="v0",
            title="Implement V2 Task Contract",
            content=_stable_json(lane_input.task_contract),
            stability=STABILITY_SEMI_STATIC,
            cache_policy=CACHE_POLICY_SESSION,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_lane_state",
            version="v0",
            title="Implement V2 Lane State",
            content=_stable_json(
                {
                    "work_session_id": lane_input.work_session_id,
                    "task_id": lane_input.task_id,
                    "lane": lane_input.lane,
                    "model_backend": lane_input.model_backend,
                    "model": lane_input.model,
                    "effort": lane_input.effort,
                    "lane_config": lane_input.lane_config,
                    "lane_local_state": _lane_local_state(lane_input.persisted_lane_state),
                }
            ),
            stability=STABILITY_DYNAMIC,
            cache_policy=CACHE_POLICY_DYNAMIC,
            profile="implement_v2",
        ),
    ]
    return sections


def implement_v2_prompt_section_metrics(lane_input: ImplementLaneInput) -> dict[str, object]:
    """Return prompt-section metrics for v2 prompt assembly."""

    return prompt_section_metrics(build_implement_v2_prompt_sections(lane_input))


def _tool_surface_json(tool_specs: tuple[ImplementLaneToolSpec, ...]) -> str:
    return _stable_json({"tools": [spec.as_dict() for spec in tool_specs]})


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2)


def _lane_local_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    allowed_prefixes = ("lane_", "reentry_", "resume_")
    blocked_terms = ("memory", "typed", "durable", "repair_memory")
    filtered = {}
    for key, value in persisted_lane_state.items():
        key_text = str(key)
        normalized = key_text.lower()
        if not key_text.startswith(allowed_prefixes):
            continue
        if any(term in normalized for term in blocked_terms):
            continue
        filtered[key_text] = value
    return filtered


__all__ = ["build_implement_v2_prompt_sections", "implement_v2_prompt_section_metrics"]
