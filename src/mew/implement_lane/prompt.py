"""Prompt section assembly for the default-off implement_v2 lane."""

from __future__ import annotations

import json
import re

from ..prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_SESSION,
    STABILITY_DYNAMIC,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    PromptSection,
    prompt_section_metrics,
)
from .tool_policy import (
    ImplementLaneToolSpec,
    is_hard_runtime_artifact_task,
    list_v2_tool_specs_for_mode,
    list_v2_tool_specs_for_task,
)
from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, tool_surface_profile_id
from .types import ImplementLaneInput
from .affordance_visibility import CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS
from .workframe import WorkFrameInputs
from .workframe_variants import (
    DEFAULT_WORKFRAME_VARIANT,
    canonicalize_common_workframe_inputs,
    common_workframe_inputs_from_workframe_inputs,
    project_workframe_with_variant,
    validate_workframe_variant_name,
)

HOT_PATH_PROJECTION_SURFACE = "hot_path_projection"
ORDINARY_RESIDENT_SUMMARY_SURFACE = "ordinary_resident_summary"
RESIDENT_SIDECAR_STATE_SURFACE = "resident_sidecar_state"
FINISH_REPLAY_RECOVERY_SURFACE = "finish_replay_recovery"

_HOT_PATH_SECTION_IDS = frozenset(
    {
        "implement_v2_lane_base",
        "implement_v2_tool_contract",
        "implement_v2_coding_contract",
        "implement_v2_task_contract",
        "implement_v2_codex_hot_path_base",
    }
)
_ORDINARY_RESIDENT_SUMMARY_SECTION_IDS = frozenset()
_RESIDENT_SIDECAR_SECTION_IDS = frozenset()
_FINISH_RECOVERY_SECTION_IDS = frozenset()
_ORDINARY_RESIDENT_SUMMARY_BYTE_CAP = 1536
_ACTIVE_WORK_CARD_BYTE_CAP = 640
_REPAIR_HISTORY_CARD_BYTE_CAP = 256
_HARD_RUNTIME_PROFILE_BYTE_CAP = 760
_HARD_RUNTIME_FRONTIER_CARD_BYTE_CAP = 768


def build_implement_v2_prompt_sections(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
    workframe_sidecar_events: tuple[dict[str, object], ...] = (),
) -> list[PromptSection]:
    """Build provider-neutral v2 prompt sections without provider cache transport."""

    mode = str(lane_input.lane_config.get("mode") or "read_only")
    specs = (
        tool_specs
        if tool_specs is not None
        else list_v2_tool_specs_for_task(mode, task_contract=lane_input.task_contract)
    )
    tool_names = {spec.name for spec in specs}
    if _is_codex_hot_path_profile(lane_input):
        return _build_codex_hot_path_prompt_sections(lane_input, tool_names=tool_names)
    if {"apply_patch", "edit_file"} & tool_names and "write_file" in tool_names:
        mutation_sentence = (
            "Create complete new files with write_file when the target path is missing; "
            "modify existing source with apply_patch or edit_file. "
        )
    elif {"apply_patch", "edit_file"} & tool_names:
        mutation_sentence = "Make source changes with apply_patch or edit_file. "
    else:
        mutation_sentence = "Use the available read-only tools to inspect repository state. "
    if {"run_command", "run_tests"} & tool_names:
        verify_sentence = "Use run_command or run_tests to build, run, and verify. "
    else:
        verify_sentence = "Use available observations as fresh evidence. "
    sections = [
        PromptSection(
            id="implement_v2_lane_base",
            version="v0",
            title="Implement V2 Lane Base",
            content=(
                "You are implementing in a repository through native tool calls. "
                "Use the provider-native transcript as the live history, preserve "
                "paired tool results, and finish only with fresh tool evidence."
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
            id="implement_v2_coding_contract",
            version="v2",
            title="Implement V2 Coding Contract",
            content=(
                "Inspect only enough context to choose a minimal runnable candidate. "
                f"{mutation_sentence}"
                f"{verify_sentence}"
                "When the task asks for a new file or artifact and the target path is known, "
                "create the smallest runnable version early, then run it and repair from concrete failures. "
                "If the task or verify command names a missing source or artifact path, "
                "treat that as the target path and create the smallest runnable file before extended reverse engineering. "
                "If task_facts.missing_workspace_paths is present, use those factual missing paths as target-path context; "
                "prefer a minimal runnable artifact at the named path over extended archaeology. "
                "Treat task_facts.existing_workspace_paths as provided inputs or references, not replacement deliverables; "
                "do not rebuild or substitute provided artifacts unless the task explicitly asks for that rebuild. "
                "Repair from the latest concrete failure shown in the transcript. "
                "Finish only with fresh evidence from the tools."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
    ]
    sections.extend(
        [
            PromptSection(
                id="implement_v2_task_contract",
                version="v0",
                title="Implement V2 Task Contract",
                content=_stable_json(_model_visible_task_contract(lane_input.task_contract)),
                stability=STABILITY_SEMI_STATIC,
                cache_policy=CACHE_POLICY_SESSION,
                profile="implement_v2",
            ),
        ]
    )
    return sections


def _is_codex_hot_path_profile(lane_input: ImplementLaneInput) -> bool:
    return tool_surface_profile_id(lane_input.lane_config) == CODEX_HOT_PATH_PROFILE_ID


def _build_codex_hot_path_prompt_sections(
    lane_input: ImplementLaneInput,
    *,
    tool_names: set[str],
) -> list[PromptSection]:
    if "apply_patch" in tool_names:
        mutation_sentence = "Prefer apply_patch for source changes. "
    elif {"edit_file", "write_file"} & tool_names:
        mutation_sentence = "Use the available file mutation tool for source changes. "
    else:
        mutation_sentence = "Use the available tools to inspect the workspace. "
    if {"exec_command", "run_command", "run_tests"} & tool_names:
        verify_sentence = "Run the verifier or closest relevant command, then repair concrete failures. "
    else:
        verify_sentence = "Use fresh tool observations as evidence. "
    return [
        PromptSection(
            id="implement_v2_codex_hot_path_base",
            version="v0",
            title="Codex Hot Path Base",
            content=(
                "You are a coding agent running in a terminal workspace. Be precise, safe, and direct. "
                "Inspect just enough context to identify the target change. "
                f"{mutation_sentence}"
                f"{verify_sentence}"
                "When the task or verifier names a missing source or artifact path, create the smallest runnable "
                "implementation at that path once the necessary evidence is available. "
                "Do not rebuild or replace provided artifacts unless the task explicitly asks for that rebuild. "
                "Use finish only after a fresh tool result demonstrates the requested behavior or a concrete blocker."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_task_contract",
            version="v0",
            title="Implement V2 Task Contract",
            content=_stable_json(_model_visible_task_contract(lane_input.task_contract)),
            stability=STABILITY_SEMI_STATIC,
            cache_policy=CACHE_POLICY_SESSION,
            profile="implement_v2",
        ),
    ]


def implement_v2_prompt_section_metrics(lane_input: ImplementLaneInput) -> dict[str, object]:
    """Return prompt-section metrics for v2 prompt assembly."""

    metrics = prompt_section_metrics(build_implement_v2_prompt_sections(lane_input))
    metrics["hot_path_collapse"] = _hot_path_collapse_prompt_metrics(metrics)
    return metrics


def build_implement_v2_workframe_debug_bundle(
    lane_input: ImplementLaneInput,
    *,
    active_work_todo: dict[str, object] | None = None,
    hard_runtime_frontier: dict[str, object] | None = None,
    repair_history: dict[str, object] | None = None,
    sidecar_events: tuple[dict[str, object], ...] = (),
    prompt_inventory: tuple[dict[str, object], ...] = (),
    provider_tool_names: tuple[str, ...] = (),
    turn_id: str = "prompt",
) -> dict[str, object]:
    """Build the WorkFrame replay/debug bundle from the same reducer used by the prompt."""

    todo = _active_work_todo_state(lane_input.persisted_lane_state) if active_work_todo is None else dict(active_work_todo)
    frontier = (
        _hard_runtime_frontier_state(lane_input.persisted_lane_state)
        if hard_runtime_frontier is None
        else dict(hard_runtime_frontier)
    )
    history = _repair_history_state(lane_input.persisted_lane_state) if repair_history is None else dict(repair_history)
    runtime_events = tuple(dict(event) for event in sidecar_events if isinstance(event, dict))
    prompt_events = _workframe_prompt_sidecar_events(
        active_work_todo=todo,
        hard_runtime_frontier=frontier,
        repair_history=history,
    )
    inputs = WorkFrameInputs(
        attempt_id=lane_input.work_session_id or "implement-v2-prompt",
        turn_id=turn_id,
        task_id=lane_input.task_id,
        objective=_task_objective(lane_input),
        success_contract_ref=_success_contract_ref(lane_input),
        constraints=("model_visible_workframe_only",),
        sidecar_events=_merge_workframe_sidecar_events(runtime_events=runtime_events, prompt_events=prompt_events),
        baseline_metrics=_workframe_baseline_metrics(lane_input, provider_tool_names=provider_tool_names),
        prompt_inventory=(),
        workspace_root=lane_input.workspace,
        artifact_root=str(lane_input.lane_config.get("artifact_dir") or ""),
    )
    workframe_variant = _workframe_variant(lane_input)
    common_inputs = common_workframe_inputs_from_workframe_inputs(inputs)
    projection = project_workframe_with_variant(common_inputs, variant=workframe_variant)
    workframe = projection.workframe
    report = projection.invariant_report
    visible = _workframe_visible_payload(workframe.as_dict())
    return {
        "schema_version": 1,
        "turn_id": turn_id,
        "workframe_variant": workframe_variant,
        "reducer_inputs": {
            "schema_version": 2,
            "workframe_variant": workframe_variant,
            "common_workframe_inputs_schema_version": common_inputs.schema_version,
            "workframe_inputs": inputs.as_dict(),
            "common_workframe_inputs": common_inputs.as_dict(),
            "canonical": canonicalize_common_workframe_inputs(common_inputs),
            "shared_substrate_hash": projection.shared_substrate_hash,
        },
        "reducer_output": workframe.as_dict(),
        "invariant_report": report.as_dict(),
        "prompt_visible_workframe": visible,
        "prompt_render_inventory": {
            "schema_version": 2,
            "static_shape": [
                "static_instructions",
                "task_contract_digest",
                "natural_transcript_tail",
                "one_workframe_projection",
            ],
            "workframe_variant": workframe_variant,
            "shared_substrate_hash": projection.shared_substrate_hash,
            "projection_hash": projection.projection_hash,
            "source_prompt_inventory": [dict(item) for item in prompt_inventory],
            "sections": [dict(item) for item in prompt_inventory],
        },
        "workframe_cursor": {
            "schema_version": 2,
            "attempt_id": inputs.attempt_id,
            "turn_id": turn_id,
            "workframe_id": workframe.trace.workframe_id,
            "workframe_variant": workframe_variant,
            "shared_substrate_hash": projection.shared_substrate_hash,
            "projection_hash": projection.projection_hash,
            "input_hash": workframe.trace.input_hash,
            "output_hash": workframe.trace.output_hash,
            "reducer_schema_version": workframe.trace.reducer_schema_version,
            "canonicalizer_version": workframe.trace.canonicalizer_version,
            "previous_workframe_hash": inputs.previous_workframe_hash,
        },
    }


def _workframe_variant(lane_input: ImplementLaneInput) -> str:
    return validate_workframe_variant_name(
        lane_input.lane_config.get("workframe_variant")
        or lane_input.task_contract.get("workframe_variant")
        or DEFAULT_WORKFRAME_VARIANT
    )


def _model_visible_lane_config(lane_config: dict[str, object]) -> dict[str, object]:
    visible = dict(lane_config)
    visible.pop("workframe_variant", None)
    visible.pop("work_frame_variant", None)
    return visible


def _model_visible_task_contract(task_contract: dict[str, object]) -> dict[str, object]:
    return _strip_task_contract_internal_fields(task_contract)


def _strip_task_contract_internal_fields(value: object) -> object:
    internal_fields = set(CANONICAL_FORBIDDEN_PROVIDER_VISIBLE_FIELDS) | {"workframe_variant", "work_frame_variant"}
    if isinstance(value, dict):
        return {
            str(key): _strip_task_contract_internal_fields(item)
            for key, item in value.items()
            if str(key) not in internal_fields
        }
    if isinstance(value, list):
        return [_strip_task_contract_internal_fields(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_task_contract_internal_fields(item) for item in value]
    return value


def _hot_path_collapse_prompt_metrics(metrics: dict[str, object]) -> dict[str, object]:
    sections = metrics.get("sections") if isinstance(metrics.get("sections"), list) else []
    inventory: list[dict[str, object]] = []
    normal_static_cacheable_bytes = 0
    normal_dynamic_hot_path_bytes = 0
    normal_dynamic_recovery_bytes = 0
    ordinary_resident_summary_bytes = 0
    resident_model_visible_bytes = 0
    finish_replay_recovery_bytes = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "")
        chars = _safe_section_chars(section.get("chars"))
        surface = _section_surface(section_id)
        visibility = "ordinary"
        if surface == RESIDENT_SIDECAR_STATE_SURFACE:
            resident_model_visible_bytes += chars
        if surface == ORDINARY_RESIDENT_SUMMARY_SURFACE:
            ordinary_resident_summary_bytes += chars
        if surface == FINISH_REPLAY_RECOVERY_SURFACE:
            finish_replay_recovery_bytes += chars
        if section.get("cache_policy") == CACHE_POLICY_CACHEABLE:
            normal_static_cacheable_bytes += chars
        if section.get("stability") == STABILITY_DYNAMIC and surface == HOT_PATH_PROJECTION_SURFACE:
            normal_dynamic_hot_path_bytes += chars
        if section.get("stability") == STABILITY_DYNAMIC and surface != HOT_PATH_PROJECTION_SURFACE:
            normal_dynamic_recovery_bytes += chars
        inventory.append(
            {
                "id": section_id,
                "bytes": chars,
                "surface": surface,
                "visibility": visibility,
                "stability": section.get("stability"),
                "cache_policy": section.get("cache_policy"),
            }
        )
    total_chars = _safe_section_chars(metrics.get("total_chars"))
    return {
        "schema_version": 1,
        "measurement_scope": "prompt_sections_only",
        "surfaces": {
            "hot_path_projection": HOT_PATH_PROJECTION_SURFACE,
            "ordinary_resident_summary": ORDINARY_RESIDENT_SUMMARY_SURFACE,
            "resident_sidecar_state": RESIDENT_SIDECAR_STATE_SURFACE,
            "finish_replay_recovery": FINISH_REPLAY_RECOVERY_SURFACE,
        },
        "normal_prompt_section_bytes": total_chars,
        "normal_section_inventory": inventory,
        "normal_static_cacheable_bytes": normal_static_cacheable_bytes,
        "normal_dynamic_hot_path_bytes": normal_dynamic_hot_path_bytes,
        "normal_dynamic_recovery_bytes": normal_dynamic_recovery_bytes,
        "ordinary_resident_summary_bytes": ordinary_resident_summary_bytes,
        "resident_model_visible_bytes": resident_model_visible_bytes,
        "finish_replay_recovery_bytes": finish_replay_recovery_bytes,
        "provider_visible_tool_result_bytes": 0,
        "phase": "m6_24_affordance_collapse_phase_1",
    }


def _section_surface(section_id: str) -> str:
    if section_id in _RESIDENT_SIDECAR_SECTION_IDS:
        return RESIDENT_SIDECAR_STATE_SURFACE
    if section_id in _ORDINARY_RESIDENT_SUMMARY_SECTION_IDS:
        return ORDINARY_RESIDENT_SUMMARY_SURFACE
    if section_id in _FINISH_RECOVERY_SECTION_IDS:
        return FINISH_REPLAY_RECOVERY_SURFACE
    if section_id in _HOT_PATH_SECTION_IDS:
        return HOT_PATH_PROJECTION_SURFACE
    return HOT_PATH_PROJECTION_SURFACE


def _workframe_section_content(
    lane_input: ImplementLaneInput,
    *,
    active_work_todo: dict[str, object],
    hard_runtime_frontier: dict[str, object],
    repair_history: dict[str, object],
    sidecar_events: tuple[dict[str, object], ...] = (),
    provider_tool_names: tuple[str, ...] = (),
) -> str:
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        active_work_todo=active_work_todo,
        hard_runtime_frontier=hard_runtime_frontier,
        repair_history=repair_history,
        sidecar_events=sidecar_events,
        provider_tool_names=provider_tool_names,
    )
    return _bounded_compact_json(
        bundle["prompt_visible_workframe"],
        max_chars=4096,
    )


def _workframe_visible_payload(workframe: dict[str, object]) -> dict[str, object]:
    prompt_workframe = _compact_prompt_workframe(workframe)
    return {
        "workframe": prompt_workframe,
        "rule": (
            "This is the only ordinary dynamic state object. Follow required_next, "
            "avoid forbidden_next, and cite evidence refs when finishing."
        ),
    }


def _compact_prompt_workframe(workframe: dict[str, object]) -> dict[str, object]:
    """Keep prompt WorkFrame actionable while leaving full state in sidecar artifacts."""

    return _drop_empty_dict_values(
        {
            "schema_version": workframe.get("schema_version"),
            "trace": _compact_workframe_trace(workframe.get("trace")),
            "goal": _compact_workframe_goal(workframe.get("goal")),
            "current_phase": _clip_text(workframe.get("current_phase"), 80),
            "latest_actionable": _compact_workframe_latest_actionable(workframe.get("latest_actionable")),
            "required_next": _compact_workframe_required_next(workframe.get("required_next")),
            "forbidden_next": _compact_workframe_forbidden_next(workframe.get("forbidden_next")),
            "changed_sources": _compact_workframe_changed_sources(workframe.get("changed_sources")),
            "verifier_state": _compact_workframe_verifier_state(workframe.get("verifier_state")),
            "finish_readiness": _compact_workframe_finish_readiness(workframe.get("finish_readiness")),
            "variant": _compact_workframe_variant(workframe.get("variant")),
            "tool_context": _compact_workframe_tool_context(workframe.get("tool_context")),
            "obligations": _compact_workframe_obligations(workframe.get("obligations")),
            "repair_loop": _compact_workframe_repair_loop(workframe.get("repair_loop")),
        }
    )


def _workframe_baseline_metrics(
    lane_input: ImplementLaneInput,
    *,
    provider_tool_names: tuple[str, ...] = (),
) -> dict[str, object]:
    mode = str(lane_input.lane_config.get("mode") or "read_only")
    names = list(provider_tool_names) if provider_tool_names else [spec.name for spec in list_v2_tool_specs_for_mode(mode)]
    return {
        "provider_tool_names": names,
    }


def _compact_workframe_trace(value: object) -> dict[str, object]:
    trace = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "turn_id": _clip_text(trace.get("turn_id"), 80),
            "workframe_id": _clip_text(trace.get("workframe_id"), 80),
            "output_hash": _clip_text(trace.get("output_hash"), 96),
        }
    )


def _compact_workframe_goal(value: object) -> dict[str, object]:
    goal = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "task_id": _clip_text(goal.get("task_id"), 120),
            "objective": _clip_text(goal.get("objective"), 240),
            "success_contract_ref": _clip_text(goal.get("success_contract_ref"), 160),
        }
    )


def _compact_workframe_latest_actionable(value: object) -> dict[str, object]:
    latest = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "family": _clip_text(latest.get("family"), 120),
            "generic_family": _clip_text(latest.get("generic_family"), 120),
            "summary": _clip_text(latest.get("summary"), 240),
            "source_ref": _clip_text(latest.get("source_ref"), 160),
            "evidence_refs": _compact_workframe_refs(latest.get("evidence_refs")),
            "transition_contract": _compact_workframe_transition_contract(
                (latest.get("recovery_hint") if isinstance(latest.get("recovery_hint"), dict) else {}).get(
                    "transition_contract"
                )
            ),
        }
    )


def _compact_workframe_required_next(value: object) -> dict[str, object]:
    required = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "kind": _clip_text(required.get("kind"), 80),
            "reason": _clip_text(required.get("reason"), 260),
            "target_paths": _clip_string_list(required.get("target_paths"), max_items=4, max_chars=120),
            "after": _clip_text(required.get("after"), 160),
            "evidence_refs": _compact_workframe_refs(required.get("evidence_refs")),
            "inspection_target_paths": _clip_string_list(
                required.get("inspection_target_paths"), max_items=4, max_chars=120
            ),
            "inspection_evidence_refs": _compact_workframe_refs(required.get("inspection_evidence_refs")),
        }
    )


def _compact_workframe_refs(value: object, *, max_items: int = 3, max_chars: int = 96) -> list[object]:
    if not isinstance(value, (list, tuple)):
        return []
    clipped: list[object] = []
    for item in value[:max_items]:
        if isinstance(item, dict):
            ref: dict[str, object] = {}
            for key in ("kind", "id", "ref"):
                if key in item:
                    ref[key] = _clip_text(item.get(key), max_chars)
            if ref:
                clipped.append(ref)
        elif isinstance(item, str):
            clipped.append(_clip_text(item, max_chars))
        elif isinstance(item, (int, float, bool)):
            clipped.append(item)
    if len(value) > max_items:
        clipped.append({"omitted_ref_count": len(value) - max_items})
    return clipped


def _compact_workframe_forbidden_next(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, object]] = []
    for item in value[:4]:
        if not isinstance(item, dict):
            continue
        compact = _drop_empty_dict_values(
            {
                "kind": _clip_text(item.get("kind"), 80),
                "reason": _clip_text(item.get("reason"), 180),
            }
        )
        if compact:
            items.append(compact)
    return items


def _compact_workframe_transition_contract(value: object) -> dict[str, object]:
    contract = value if isinstance(value, dict) else {}
    state_transition = contract.get("state_transition") if isinstance(contract.get("state_transition"), dict) else {}
    runtime_transition = (
        contract.get("runtime_artifact_transition")
        if isinstance(contract.get("runtime_artifact_transition"), dict)
        else {}
    )
    next_action = (
        contract.get("next_action_contract") if isinstance(contract.get("next_action_contract"), dict) else {}
    )
    return _drop_empty_dict_values(
        {
            "rule_id": _clip_text(state_transition.get("rule_id"), 160),
            "transition_reason": _clip_text(state_transition.get("reason"), 220),
            "runtime_artifact_transition": _drop_empty_dict_values(
                {
                    "rule_id": _clip_text(runtime_transition.get("rule_id"), 160),
                    "artifact_path": _clip_text(runtime_transition.get("artifact_path"), 160),
                    "repeat_key": _clip_text(runtime_transition.get("repeat_key"), 180),
                    "repeat_count": runtime_transition.get("repeat_count"),
                    "required_next": _clip_text(runtime_transition.get("required_next"), 80),
                }
            ),
            "next_action_contract": _drop_empty_dict_values(
                {
                    "kind": _clip_text(next_action.get("kind"), 80),
                    "reason": _clip_text(next_action.get("reason"), 220),
                    "target_paths": _clip_string_list(next_action.get("target_paths"), max_items=4, max_chars=120),
                    "after": _clip_text(next_action.get("after"), 160),
                }
            ),
        }
    )


def _compact_workframe_changed_sources(value: object) -> dict[str, object]:
    changed = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "paths": _clip_string_list(changed.get("paths"), max_items=4, max_chars=120),
            "latest_mutation_ref": _clip_text(changed.get("latest_mutation_ref"), 160),
            "since_last_strict_verifier": changed.get("since_last_strict_verifier"),
        }
    )


def _compact_workframe_verifier_state(value: object) -> dict[str, object]:
    verifier = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "last_strict_verifier_ref": _clip_text(verifier.get("last_strict_verifier_ref"), 160),
            "status": _clip_text(verifier.get("status"), 80),
            "fresh_after_latest_source_mutation": verifier.get("fresh_after_latest_source_mutation"),
            "budget_closeout_required": verifier.get("budget_closeout_required"),
        }
    )


def _compact_workframe_finish_readiness(value: object) -> dict[str, object]:
    readiness = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "state": _clip_text(readiness.get("state"), 80),
            "blockers": _clip_string_list(readiness.get("blockers"), max_items=4, max_chars=120),
            "missing_obligations": _clip_string_list(
                readiness.get("missing_obligations"), max_items=4, max_chars=120
            ),
        }
    )


def _compact_workframe_variant(value: object) -> dict[str, object]:
    variant = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "name": _clip_text(variant.get("name"), 80),
            "schema_version": variant.get("schema_version"),
            "policy": _clip_text(variant.get("policy"), 120),
            "required_next_policy": _clip_text(variant.get("required_next_policy"), 120),
        }
    )


def _compact_workframe_tool_context(value: object) -> dict[str, object]:
    context = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "schema_version": context.get("schema_version"),
            "registry_ref": _clip_text(context.get("registry_ref"), 120),
            "active_tool_refs": _compact_workframe_refs(context.get("active_tool_refs"), max_items=12, max_chars=80),
            "recommended_tool_refs": _compact_tool_ref_entries(
                context.get("recommended_tool_refs"),
                ref_key="evidence_refs",
                max_items=4,
            ),
            "disabled_tool_refs": _compact_tool_ref_entries(
                context.get("disabled_tool_refs"),
                ref_key="until_evidence_refs",
                max_items=6,
            ),
            "policy_refs": _compact_workframe_refs(context.get("policy_refs"), max_items=4, max_chars=120),
            "fetchable_refs": _compact_workframe_refs(context.get("fetchable_refs"), max_items=4, max_chars=120),
            "tool_result_search": _compact_workframe_search_policy(context.get("tool_result_search")),
            "model_turn_search": _compact_workframe_search_policy(context.get("model_turn_search")),
        }
    )


def _compact_tool_ref_entries(value: object, *, ref_key: str, max_items: int) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, object]] = []
    for item in value[:max_items]:
        if not isinstance(item, dict):
            continue
        compact = _drop_empty_dict_values(
            {
                "tool_ref": _clip_text(item.get("tool_ref"), 80),
                "reason": _clip_text(item.get("reason"), 180),
                ref_key: _compact_workframe_refs(item.get(ref_key), max_items=3, max_chars=96),
            }
        )
        if compact:
            items.append(compact)
    if len(value) > max_items:
        items.append({"omitted_tool_ref_count": len(value) - max_items})
    return items


def _compact_workframe_search_policy(value: object) -> dict[str, object]:
    policy = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "index_ref": _clip_text(policy.get("index_ref"), 120),
            "primary": policy.get("primary"),
            "usage": _clip_text(policy.get("usage"), 120),
            "query_hints": _clip_string_list(policy.get("query_hints"), max_items=6, max_chars=80),
        }
    )


def _compact_workframe_obligations(value: object) -> dict[str, object]:
    obligations = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "schema_version": obligations.get("schema_version"),
            "artifact_obligation_refs": _compact_workframe_refs(
                obligations.get("artifact_obligation_refs"),
                max_items=4,
                max_chars=120,
            ),
            "missing_or_stale_refs": _compact_workframe_refs(
                obligations.get("missing_or_stale_refs"),
                max_items=4,
                max_chars=120,
            ),
            "finish_blockers": _clip_string_list(obligations.get("finish_blockers"), max_items=4, max_chars=120),
        }
    )


def _compact_workframe_repair_loop(value: object) -> dict[str, object]:
    loop = value if isinstance(value, dict) else {}
    return _drop_empty_dict_values(
        {
            "schema_version": loop.get("schema_version"),
            "state": _clip_text(loop.get("state"), 80),
            "signature_ref": _clip_text(loop.get("signature_ref"), 120),
            "disabled_action_families": _clip_string_list(
                loop.get("disabled_action_families"),
                max_items=4,
                max_chars=80,
            ),
        }
    )


def _merge_workframe_sidecar_events(
    *,
    runtime_events: tuple[dict[str, object], ...],
    prompt_events: tuple[dict[str, object], ...],
) -> tuple[dict[str, object], ...]:
    """Use runtime facts as authoritative and prompt projections only as fallback.

    WorkFrame is allowed to summarize resident prompt projections, but live
    reducer state must not let a generic prompt-frontier failure override
    concrete tool-result evidence from the same attempt.
    """

    if runtime_events:
        prompt_recovery_events = tuple(
            event for event in prompt_events if not _is_generic_prompt_frontier_event(event)
        )
        if _has_passing_runtime_verifier_event(runtime_events):
            return _renumber_workframe_events(runtime_events)
        if _latest_runtime_event_blocked_by_prior_failed_write(runtime_events):
            return _renumber_workframe_events(runtime_events)
        if _latest_runtime_event_needs_prompt_recovery(runtime_events):
            return _renumber_workframe_events((*runtime_events, *prompt_recovery_events))
        return _renumber_workframe_events((*prompt_recovery_events, *runtime_events))
    return _renumber_workframe_events(prompt_events)


def _is_generic_prompt_frontier_event(event: dict[str, object]) -> bool:
    event_id = str(event.get("event_id") or "")
    if not event_id.startswith("prompt-"):
        return False
    return _is_generic_workframe_summary(event.get("summary"))


def _latest_runtime_event_needs_prompt_recovery(events: tuple[dict[str, object], ...]) -> bool:
    for event in reversed(events):
        status = str(event.get("status") or "").strip().casefold()
        kind = str(event.get("kind") or "").strip()
        if status in {"failed", "interrupted", "invalid"} and kind in {
            "verifier",
            "strict_verifier",
            "run_tests",
            "latest_failure",
        }:
            return not bool(event.get("observable_output"))
        return False
    return False


def _latest_runtime_event_blocked_by_prior_failed_write(events: tuple[dict[str, object], ...]) -> bool:
    if not events:
        return False
    event = events[-1]
    status = str(event.get("status") or "").strip().casefold()
    if status != "invalid":
        return False
    detail = " ".join(
        str(event.get(key) or "")
        for key in (
            "summary",
            "reason",
            "failure_class",
            "failure_kind",
            "family",
        )
    ).casefold()
    return "blocked_by_prior_failed_write" in detail


def _has_passing_runtime_verifier_event(events: tuple[dict[str, object], ...]) -> bool:
    for event in events:
        status = str(event.get("status") or "").strip().casefold()
        kind = str(event.get("kind") or "").strip()
        if status in {"completed", "passed", "pass", "success", "succeeded"} and kind in {
            "verifier",
            "strict_verifier",
            "run_tests",
        }:
            return True
    return False


def _is_generic_workframe_summary(value: object) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return True
    normalized = " ".join(text.replace("_", " ").replace("-", " ").split())
    generic = {
        "failed",
        "failure",
        "error",
        "unknown",
        "nonzero",
        "nonzero exit",
        "exit code 1",
        "exit status 1",
        "killed",
        "timeout",
        "timed out",
        "interrupted",
        "command failed",
        "tool failed",
        "latest runtime frontier failure",
        "runtime failure",
    }
    if normalized in generic:
        return True
    return bool(re.fullmatch(r"exit code \d+", normalized))


def _renumber_workframe_events(events: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    renumbered: list[dict[str, object]] = []
    for index, event in enumerate(events, start=1):
        item = dict(event)
        item["event_sequence"] = index
        renumbered.append(item)
    return tuple(renumbered)


def _workframe_prompt_sidecar_events(
    *,
    active_work_todo: dict[str, object],
    hard_runtime_frontier: dict[str, object],
    repair_history: dict[str, object],
) -> tuple[dict[str, object], ...]:
    events: list[dict[str, object]] = []
    sequence = 1
    write_repair = active_work_todo.get("write_repair") if isinstance(active_work_todo.get("write_repair"), dict) else {}
    has_write_repair_signal = bool(
        _clip_text(write_repair.get("failure_kind"), 120)
        or _clip_text(write_repair.get("path"), 240)
        or _clip_text(write_repair.get("required_next_action"), 240)
    )
    if has_write_repair_signal:
        events.append(
            {
                "kind": "write",
                "event_sequence": sequence,
                "event_id": "prompt-write-repair",
                "status": "failed",
                "family": _clip_text(write_repair.get("failure_kind") or "write_repair_required", 120),
                "summary": _clip_text(write_repair.get("required_next_action") or "repair failed source mutation", 240),
                "path": _clip_text(write_repair.get("path"), 240),
                "evidence_refs": ["wf:write_repair"],
            }
        )
        sequence += 1
    failure = _frontier_latest_failure_card(hard_runtime_frontier)
    if failure and not has_write_repair_signal:
        required_next_action = _frontier_required_next_action(hard_runtime_frontier)
        events.append(
            {
                "kind": "failure",
                "event_sequence": sequence,
                "event_id": "prompt-frontier-failure",
                "status": "failed",
                "family": _clip_text(
                    failure.get("failure_class")
                    or failure.get("failure_kind")
                    or failure.get("class")
                    or "runtime_failure",
                    120,
                ),
                "summary": _clip_text(
                    required_next_action or failure.get("required_next_action") or failure.get("summary")
                    or "latest runtime frontier failure",
                    240,
                ),
                "target_paths": _active_work_todo_target_paths(active_work_todo),
                "evidence_refs": ["wf:frontier_failure"],
            }
        )
        sequence += 1
    readiness = (
        active_work_todo.get("first_write_readiness")
        if isinstance(active_work_todo.get("first_write_readiness"), dict)
        else {}
    )
    if readiness and bool(readiness.get("first_write_due")) and not events:
        events.append(
            {
                "kind": "latest_failure",
                "event_sequence": sequence,
                "event_id": "prompt-first-write-due",
                "status": "failed",
                "family": "first_write_due",
                "summary": _clip_text(readiness.get("required_next_action") or "make one scoped source mutation", 240),
                "target_paths": _active_work_todo_target_paths(active_work_todo),
                "evidence_refs": ["wf:first_write_readiness"],
            }
        )
        sequence += 1
    if repair_history and not events:
        events.append(
            {
                "kind": "latest_failure",
                "event_sequence": sequence,
                "event_id": "prompt-repair-history",
                "status": "failed",
                "family": _clip_text(
                    repair_history.get("failure_class") or repair_history.get("failure_kind") or "repair_history",
                    120,
                ),
                "summary": _clip_text(
                    repair_history.get("required_next_action")
                    or repair_history.get("next_generic_probe")
                    or repair_history.get("summary")
                    or repair_history.get("notes")
                    or "continue from repair history",
                    240,
                ),
                "evidence_refs": ["wf:repair_history"],
            }
        )
    return tuple(events)


def _task_objective(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract
    for key in ("objective", "description", "goal", "task", "prompt"):
        value = contract.get(key) if isinstance(contract, dict) else None
        if isinstance(value, str) and value.strip():
            return _clip_text(value, 360)
    return _clip_text(_contract_text(contract), 360) or "Repair the workspace to satisfy the configured verifier."


def _success_contract_ref(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract
    if isinstance(contract, dict):
        for key in ("verify_command", "acceptance", "success_contract_ref"):
            value = contract.get(key)
            if isinstance(value, str) and value.strip():
                return _clip_text(value, 160)
    return ""


def _active_work_todo_target_paths(active_work_todo: dict[str, object]) -> list[str]:
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    return _clip_string_list(source.get("target_paths"), max_items=4, max_chars=240)


def _active_work_hot_path_card(
    active_work_todo: dict[str, object], hard_runtime_frontier: dict[str, object]
) -> dict[str, object]:
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    readiness = (
        active_work_todo.get("first_write_readiness")
        if isinstance(active_work_todo.get("first_write_readiness"), dict)
        else {}
    )
    write_repair = active_work_todo.get("write_repair") if isinstance(active_work_todo.get("write_repair"), dict) else {}
    blocker = active_work_todo.get("blocker") if isinstance(active_work_todo.get("blocker"), dict) else {}
    target_paths = _clip_string_list(source.get("target_paths"), max_items=2, max_chars=72)
    required_next_action = _first_nonempty_scalar_text(
        (
            write_repair.get("required_next_action"),
            readiness.get("required_next_action"),
            blocker.get("recovery_action"),
            _frontier_required_next_action(hard_runtime_frontier),
        ),
        limit=220,
    )
    return _drop_empty_dict_values(
        {
            "current_step": _clip_text(
                source.get("plan_item") or active_work_todo.get("status") or active_work_todo.get("id"),
                80,
            ),
            "target_paths": target_paths,
            "verify_command": _clip_text(source.get("verify_command"), 80),
            "first_write_due": bool(readiness.get("first_write_due")) if readiness else None,
            "probes_seen_without_write": _safe_numeric(readiness.get("probes_seen_without_write")),
            "write_repair": _drop_empty_dict_values(
                {
                    "failure_kind": _clip_text(write_repair.get("failure_kind"), 80),
                    "path": _clip_text(write_repair.get("path"), 120),
                }
            ),
            "latest_failure": _frontier_latest_failure_card(hard_runtime_frontier),
            "required_next_action": _clip_text(required_next_action, 160),
        }
    )


def _active_work_hot_path_content(
    active_work_todo: dict[str, object], hard_runtime_frontier: dict[str, object]
) -> str:
    card = _active_work_hot_path_card(active_work_todo, hard_runtime_frontier)
    required = _drop_empty_dict_values(
        {
            "first_write_due": card.get("first_write_due"),
            "target_paths": card.get("target_paths"),
            "required_next_action": card.get("required_next_action"),
        }
    )
    optional_keys = (
        "current_step",
        "probes_seen_without_write",
        "write_repair",
        "latest_failure",
        "verify_command",
    )
    compact_card: dict[str, object] = dict(required)
    for key in optional_keys:
        value = card.get(key)
        if value in (None, "", [], {}):
            continue
        candidate_card = {**compact_card, key: value}
        candidate = {"current_work": candidate_card}
        if len(_compact_json(candidate)) <= _ACTIVE_WORK_CARD_BYTE_CAP:
            compact_card = candidate_card
    return _bounded_compact_json({"current_work": compact_card}, max_chars=_ACTIVE_WORK_CARD_BYTE_CAP)


def _hard_runtime_frontier_hot_path_card(frontier: dict[str, object]) -> dict[str, object]:
    latest_failure = _frontier_latest_failure_card(frontier)
    final_artifact = frontier.get("final_artifact") if isinstance(frontier.get("final_artifact"), dict) else {}
    source_output_contract = (
        frontier.get("source_output_contract") if isinstance(frontier.get("source_output_contract"), dict) else {}
    )
    verifier = (
        frontier.get("next_verifier_shaped_command")
        if isinstance(frontier.get("next_verifier_shaped_command"), dict)
        else {}
    )
    source_roles = frontier.get("source_roles") if isinstance(frontier.get("source_roles"), list) else []
    source_paths = _clip_string_list(
        [item.get("path") for item in source_roles if isinstance(item, dict)], max_items=4, max_chars=96
    )
    return _drop_empty_dict_values(
        {
            "status": _clip_text(frontier.get("status"), 80),
            "objective": _clip_text(frontier.get("objective"), 160),
            "source_paths": source_paths,
            "latest_failure": latest_failure,
            "required_next_action": _frontier_required_next_action(frontier),
            "final_artifact_path": _clip_text(final_artifact.get("path"), 120),
            "source_output_contract_path": _clip_text(source_output_contract.get("path"), 120),
            "next_verifier": _drop_empty_dict_values(
                {
                    "tool": _clip_text(verifier.get("tool"), 40),
                    "cwd": _clip_text(verifier.get("cwd"), 120),
                    "command": _clip_text(verifier.get("command"), 220),
                }
            ),
        }
    )


def _repair_history_hot_path_card(repair_history: dict[str, object]) -> dict[str, object]:
    items = repair_history.get("items") if isinstance(repair_history.get("items"), list) else []
    log = repair_history.get("log") if isinstance(repair_history.get("log"), list) else []
    hints: dict[str, object] = {}
    safe_hint_keys = {
        "task",
        "summary",
        "notes",
        "avoid_repeated_repairs",
        "next_generic_probe",
        "required_next_action",
        "required_next_probe",
        "failure_class",
        "failure_kind",
        "path",
    }
    for key, value in repair_history.items():
        if key in {"items", "log"}:
            continue
        if key not in safe_hint_keys:
            continue
        if isinstance(value, str) and value.strip():
            hints[str(key)] = _clip_text(value, 240)
        elif isinstance(value, list):
            if key.endswith("refs"):
                hints[str(key)] = _clip_refs(value)
            else:
                clipped_items: list[object] = []
                for item in value[:2]:
                    if isinstance(item, (str, int, float, bool)):
                        clipped_items.append(_clip_text(item, 120))
                    elif isinstance(item, dict):
                        card = _repair_history_entry_card(item)
                        if card:
                            clipped_items.append(card)
                if clipped_items:
                    hints[str(key)] = clipped_items
        elif isinstance(value, (int, float, bool)):
            hints[str(key)] = value
    latest = [_repair_history_entry_card(item) for item in (items[-2:] if items else log[-2:])]
    return _drop_empty_dict_values(
        {
            "latest": latest,
            "hints": hints,
            "notes": _clip_text(repair_history.get("notes"), 240),
            "summary": _clip_text(repair_history.get("summary"), 240),
        }
    )


def _repair_history_entry_card(item: object) -> dict[str, object]:
    if isinstance(item, dict):
        return _drop_empty_dict_values(
            {
                "summary": _clip_text(item.get("summary") or item.get("message") or item.get("failure_summary"), 160),
                "failure_kind": _clip_text(item.get("failure_kind"), 80),
                "failure_class": _clip_text(item.get("failure_class"), 80),
                "path": _clip_text(item.get("path") or item.get("target_path"), 120),
                "required_next_action": _clip_text(
                    item.get("required_next_action") or item.get("required_next_probe") or item.get("recovery_action"),
                    180,
                ),
                "refs": _clip_refs(item.get("refs") or item.get("evidence_refs")),
            }
        )
    return {"summary": _clip_text(item, 180)}


def _clip_refs(value: object) -> list[object]:
    if not isinstance(value, list):
        return []
    clipped: list[object] = []
    for item in value[:5]:
        if isinstance(item, dict):
            clipped.append({str(key): _clip_text(val, 160) for key, val in item.items() if key in {"kind", "id", "ref"}})
        elif isinstance(item, str):
            clipped.append(_clip_text(item, 160))
    return clipped


def _frontier_latest_failure_card(frontier: dict[str, object]) -> dict[str, object]:
    for key in (
        "latest_runtime_failure",
        "latest_build_failure",
        "runtime_artifact_contract_mismatch",
        "first_write_frontier_stall",
    ):
        failure = frontier.get(key)
        if isinstance(failure, dict) and failure:
            return _drop_empty_dict_values(
                {
                    "source": key,
                    "failure_class": _clip_text(failure.get("failure_class"), 80),
                    "failure_kind": _clip_text(failure.get("failure_kind"), 80),
                    "summary": _clip_text(
                        failure.get("failure_summary")
                        or failure.get("summary")
                        or failure.get("message")
                        or failure.get("required_next_action")
                        or failure.get("stderr_tail")
                        or failure.get("stdout_tail")
                        or failure.get("required_next_probe"),
                        140,
                    ),
                    "required_next_action": _clip_text(
                        failure.get("required_next_action")
                        or failure.get("required_next_probe")
                        or failure.get("recovery_action"),
                        220,
                    ),
                    "recovery_mode": _clip_text(failure.get("recovery_mode"), 80),
                    "post_failure_probe_count": _safe_numeric(failure.get("post_failure_probe_count")),
                }
            )
    return {}


def _frontier_required_next_action(frontier: dict[str, object]) -> str:
    for key in (
        "latest_runtime_failure",
        "latest_build_failure",
        "runtime_artifact_contract_mismatch",
        "first_write_frontier_stall",
    ):
        failure = frontier.get(key)
        if not isinstance(failure, dict):
            continue
        action = _first_nonempty_scalar_text(
            (
                failure.get("required_next_action"),
                failure.get("required_next_probe"),
                failure.get("recovery_action"),
            ),
            limit=220,
        )
        if action:
            return action
    return ""


def _first_nonempty_scalar_text(values: tuple[object, ...], *, limit: int) -> str:
    for value in values:
        text = _clip_text(value, limit)
        if text:
            return text
    return ""


def _clip_string_list(value: object, *, max_items: int, max_chars: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _clip_text(item, max_chars)
        if text:
            items.append(text)
        if len(items) >= max_items:
            break
    return items


def _safe_numeric(value: object) -> int | float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _clip_text(value: object, limit: int) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _safe_section_chars(value: object) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _tool_surface_json(tool_specs: tuple[ImplementLaneToolSpec, ...]) -> str:
    return _stable_json({"tools": [spec.as_dict() for spec in tool_specs]})


def _stable_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2)


def _bounded_stable_json(value: object, *, max_chars: int = 6000) -> str:
    text = _stable_json(value)
    if len(text) <= max_chars:
        return text
    base = {"__mew_truncated__": "true: section exceeded bounded prompt budget", "preview": ""}
    if len(_stable_json(base)) > max_chars:
        return '{"__mew_truncated__":"true"}'
    high = max(0, min(len(text), max_chars))
    low = 0
    best = _stable_json(base)
    while low <= high:
        mid = (low + high) // 2
        candidate = _stable_json({**base, "preview": text[:mid].rstrip()})
        if len(candidate) <= max_chars:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


def _compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _bounded_compact_json(value: object, *, max_chars: int) -> str:
    text = _compact_json(value)
    if len(text) <= max_chars:
        return text
    marker = _compact_json({"__mew_truncated__": "true: compact card exceeded bounded prompt budget"})
    if len(marker) <= max_chars:
        return marker
    return '{"__mew_truncated__":"true"}'


def is_deep_probe_hard_runtime_task(task_contract: object) -> bool:
    text = _contract_text(task_contract)
    if not text:
        return False
    strong_runtime_markers = (
        "vm",
        "emulator",
        "interpreter",
        "elf",
        "binary",
        "cross-compile",
        "cross compile",
        "mips",
        "qemu",
    )
    artifact_markers = (
        "/tmp/",
        "frame",
        "screenshot",
        "image",
        "bmp",
        "boot",
    )
    source_markers = (
        "provided",
        "source",
        "source code",
        "build",
        "compile",
        "make",
    )
    return (
        any(_contract_has_marker(text, marker) for marker in strong_runtime_markers)
        and any(_contract_has_marker(text, marker) for marker in artifact_markers)
        and any(_contract_has_marker(text, marker) for marker in source_markers)
    )


def _contract_has_marker(text: str, marker: str) -> bool:
    if not marker:
        return False
    if re.fullmatch(r"[a-z0-9_-]+", marker):
        return re.search(rf"(?<![a-z0-9]){re.escape(marker)}(?![a-z0-9])", text) is not None
    return marker in text


def _contract_text(task_contract: object) -> str:
    if task_contract is None:
        return ""
    if isinstance(task_contract, str):
        return task_contract.lower()
    try:
        return json.dumps(task_contract, ensure_ascii=True, sort_keys=True).lower()
    except TypeError:
        return str(task_contract).lower()


def _lane_local_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    allowed_prefixes = ("lane_", "reentry_", "resume_")
    blocked_terms = (
        "memory",
        "typed",
        "durable",
        "repair_memory",
        "repair_history",
        "context_capsule",
        "frontier",
        "proof",
        "evidence",
        "oracle",
        "todo",
        "active_work",
    )
    filtered = {}
    for key, value in persisted_lane_state.items():
        key_text = str(key)
        normalized = key_text.lower()
        if not key_text.startswith(allowed_prefixes):
            continue
        if any(term in normalized for term in blocked_terms):
            continue
        safe_value = _lane_state_safe_value(value)
        if safe_value is not None:
            filtered[key_text] = safe_value
    return filtered


def _lane_state_safe_value(value: object) -> object | None:
    if isinstance(value, str):
        text = _clip_text(value, 240)
        return text if text else None
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        items = [_clip_text(item, 120) for item in value if isinstance(item, (str, int, float, bool))]
        return [item for item in items if item][:5] or None
    return None


def _active_work_todo_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    value = persisted_lane_state.get("active_work_todo")
    if not isinstance(value, dict):
        return {}
    source = value.get("source") if isinstance(value.get("source"), dict) else {}
    blocker = value.get("blocker") if isinstance(value.get("blocker"), dict) else {}
    attempts = value.get("attempts") if isinstance(value.get("attempts"), dict) else {}
    readiness = value.get("first_write_readiness") if isinstance(value.get("first_write_readiness"), dict) else {}
    write_repair = value.get("write_repair") if isinstance(value.get("write_repair"), dict) else {}
    cached_refs = value.get("cached_window_refs") if isinstance(value.get("cached_window_refs"), list) else []
    projected = {
        "id": _clip_text(value.get("id"), 120),
        "lane": _clip_text(value.get("lane"), 80),
        "status": _clip_text(value.get("status"), 80),
        "source": {
            "plan_item": _clip_text(source.get("plan_item"), 240),
            "target_paths": _clip_string_list(source.get("target_paths"), max_items=8, max_chars=240),
            "verify_command": _clip_text(source.get("verify_command"), 360),
        },
        "attempts": {str(key): item for key, item in attempts.items() if item not in (None, "", [], {})},
        "blocker": {
            "code": _clip_text(blocker.get("code"), 120),
            "recovery_action": _clip_text(blocker.get("recovery_action"), 240),
            "path": _clip_text(blocker.get("path"), 240),
        },
        "cached_window_refs": [
            {
                "path": str(ref.get("path") or "").strip(),
                "line_start": ref.get("line_start"),
                "line_end": ref.get("line_end"),
            }
            for ref in cached_refs[:6]
            if isinstance(ref, dict)
        ],
        "first_write_readiness": readiness,
        "write_repair": write_repair,
    }
    return _drop_empty_dict_values(projected)


def _hard_runtime_frontier_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    value = persisted_lane_state.get("lane_hard_runtime_frontier")
    return dict(value) if isinstance(value, dict) else {}


def _repair_history_state(persisted_lane_state: dict[str, object]) -> dict[str, object]:
    for key in ("lane_repair_history", "lane_context_capsule", "reentry_repair_history", "resume_repair_history"):
        value = persisted_lane_state.get(key)
        if isinstance(value, dict):
            return dict(value)
        if isinstance(value, list):
            return {"items": list(value)}
        text = str(value or "").strip()
        if text:
            return {"notes": text}
    return {}


def _drop_empty_dict_values(value: dict[str, object]) -> dict[str, object]:
    dropped: dict[str, object] = {}
    for key, item in value.items():
        if isinstance(item, dict):
            item = _drop_empty_dict_values(item)
        if item not in (None, "", [], {}):
            dropped[key] = item
    return dropped


__all__ = [
    "build_implement_v2_workframe_debug_bundle",
    "build_implement_v2_prompt_sections",
    "FINISH_REPLAY_RECOVERY_SURFACE",
    "HOT_PATH_PROJECTION_SURFACE",
    "implement_v2_prompt_section_metrics",
    "ORDINARY_RESIDENT_SUMMARY_SURFACE",
    "RESIDENT_SIDECAR_STATE_SURFACE",
    "is_deep_probe_hard_runtime_task",
    "is_hard_runtime_artifact_task",
]
