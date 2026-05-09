"""Prompt section assembly for the default-off implement_v2 lane."""

from __future__ import annotations

import json
import re

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

HOT_PATH_PROJECTION_SURFACE = "hot_path_projection"
ORDINARY_RESIDENT_SUMMARY_SURFACE = "ordinary_resident_summary"
RESIDENT_SIDECAR_STATE_SURFACE = "resident_sidecar_state"
FINISH_REPLAY_RECOVERY_SURFACE = "finish_replay_recovery"

_HOT_PATH_SECTION_IDS = frozenset(
    {
        "implement_v2_lane_base",
        "implement_v2_tool_contract",
        "implement_v2_active_coding_rhythm",
        "implement_v2_tool_surface",
        "implement_v2_task_contract",
        "implement_v2_lane_state",
    }
)
_ORDINARY_RESIDENT_SUMMARY_SECTION_IDS = frozenset(
    {
        "implement_v2_active_work_todo",
        "implement_v2_hard_runtime_frontier_state",
        "implement_v2_hard_runtime_profile",
        "implement_v2_repair_history",
    }
)
_RESIDENT_SIDECAR_SECTION_IDS = frozenset()
_FINISH_RECOVERY_SECTION_IDS = frozenset({"implement_v2_execution_artifact_contract"})
_ORDINARY_RESIDENT_SUMMARY_BYTE_CAP = 1536
_ACTIVE_WORK_CARD_BYTE_CAP = 640
_REPAIR_HISTORY_CARD_BYTE_CAP = 256
_HARD_RUNTIME_PROFILE_BYTE_CAP = 360
_HARD_RUNTIME_FRONTIER_CARD_BYTE_CAP = 416


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
                "Use provider-shaped tool calls through the selected v2 transport, "
                "preserve paired tool results, "
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
            id="implement_v2_active_coding_rhythm",
            version="v0",
            title="Implement V2 Active Coding Rhythm",
            content=(
                "Keep the normal coding hot path small and transcript-driven: cheap probe -> coherent "
                "patch/edit -> verifier -> latest-failure repair. Use read/search/inspect/run_command "
                "for cheap source, environment, ABI, or verifier probes; then move to write_file, "
                "edit_file, or apply_patch once the compatibility surface is known. After a concrete "
                "runtime, verifier, or artifact failure yields an actionable hypothesis, spend at most "
                "one focused diagnostic/read turn before a patch/edit plus verifier, or finish blocked "
                "with the exact missing information. Do not keep re-reading generated source or full "
                "proof objects when the latest command exit, bounded stdout/stderr tail, artifact miss, "
                "and blocker class are enough to act. Keep source mutation on write_file/edit_file/"
                "apply_patch paths by default, including large generated files. Use a bounded "
                "run_command writer only as a fallback after a concrete write-tool payload, parser, "
                "or transport failure makes the write path unavailable; if you use that fallback, "
                "immediately run a syntax check or verifier. Use run_command otherwise for probes, "
                "builds, runtime execution, and verification. "
                "When a cheap probe depends on an optional CLI such as rg, fd, ag, readelf, objdump, "
                "file, or nm, either preflight it with command -v or include an available fallback in "
                "the same cheap turn. If output says command not found or executable not found, treat "
                "the source frontier as incomplete and retry with glob/search_text, grep -R, find, "
                "Python, or another available fallback before the first edit. Do not mask a missing "
                "probe with `|| true` unless the same command also runs a fallback that produces the "
                "needed evidence."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
        PromptSection(
            id="implement_v2_execution_artifact_contract",
            version="v0",
            title="Implement V2 Execution Artifact Contract",
            content=(
                "For run_command and run_tests, attach an execution_contract when the command is intended to build, "
                "run, verify, or prove an artifact. poll_command inherits the original command's contract by "
                "command_run_id; do not introduce new artifact obligations only on a later poll. Declare role, "
                "stage, purpose, proof_role, "
                "acceptance_kind, expected_exit, and expected_artifacts. Expected artifacts should name path or "
                "stream targets plus cheap checks such as exists, non_empty, kind, size_between, text_contains, "
                "or regex. Use execution role values only: setup, source, dependency, build, test, runtime, "
                "artifact_probe, verify, cleanup, diagnostic, compound, unknown. Do not reuse source/frontier "
                "roles like generated_artifact as execution_contract.role; a verifier command that should create "
                "or validate a runtime artifact should normally use role=runtime, proof_role=verifier, and "
                "acceptance_kind=external_verifier. Mew owns artifact checking at runtime; do not treat stdout/stderr text markers as proof "
                "when an artifact contract exists. A finish claim should cite structured evidence ids, artifact "
                "evidence ids, verifier evidence, or blocker classes from the latest tool result instead of only "
                "describing terminal output. If task or frontier state already declares a final artifact, a "
                "verifier-shaped command may rely on mew to runtime-infer that artifact, but explicit "
                "expected_artifacts are preferred. For cheap probes or diagnostics that are not acceptance proof, "
                "omit execution_contract or set command_intent=probe|diagnostic; mew will keep those commands as "
                "non-acceptance sidecar evidence even if a detailed artifact contract is accidentally supplied."
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
            id="implement_v2_compatibility_frontier",
            version="v0",
            title="Implement V2 Compatibility Frontier",
            content=(
                "When a runtime/build failure points to dependency, language-version, or ABI compatibility, "
                "broaden the edit frontier before finishing. Search sibling source surfaces that can carry the "
                "same compatibility bug instead of patching only the first traceback file. For Python native, "
                "compiled, or Cython extension tasks, include Python and compiled-source surfaces such as "
                "`*.py`, `*.pyx`, `*.pxd`, `setup.py`, `pyproject.toml`, extension modules, and focused tests. "
                "An import-only smoke proves loadability, not behavior; run a small behavior smoke or focused "
                "test that exercises the repaired extension path before claiming completion."
            ),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement_v2",
        ),
    ]
    hard_runtime_profile_active = is_hard_runtime_artifact_task(lane_input.task_contract)
    active_work_todo = _active_work_todo_state(lane_input.persisted_lane_state)
    hard_runtime_frontier = _hard_runtime_frontier_state(lane_input.persisted_lane_state)
    repair_history = _repair_history_state(lane_input.persisted_lane_state)
    if active_work_todo:
        sections.append(
            PromptSection(
                id="implement_v2_active_work_todo",
                version="v0",
                title="Implement V2 Active Work Todo",
                content=_active_work_hot_path_content(active_work_todo, hard_runtime_frontier),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement_v2",
            )
        )
    if hard_runtime_profile_active:
        sections.append(
            PromptSection(
                id="implement_v2_hard_runtime_profile",
                version="v0",
                title="Implement V2 Hard Runtime Profile",
                content=_clip_text(
                    "Hard-runtime: no handcrafted stub; preserve provided source/runtime. "
                    "Probe ABI/symbol/syscall/output before first write. Patch once, run one verifier, "
                    "finish with fresh runtime/verifier evidence. Generated runtimes/interpreters must fail fast on "
                    "unsupported opcode/syscall/ABI with explicit PC/code; only ignore/noop when source proves harmless.",
                    _HARD_RUNTIME_PROFILE_BYTE_CAP,
                ),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="implement_v2",
            )
        )
    if repair_history:
        sections.append(
            PromptSection(
                id="implement_v2_repair_history",
                version="v0",
                title="Implement V2 Repair History",
                content=_bounded_compact_json(
                        {
                            "repair_card": _repair_history_hot_path_card(repair_history),
                        },
                    max_chars=_REPAIR_HISTORY_CARD_BYTE_CAP,
                ),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement_v2",
            )
        )
    if hard_runtime_profile_active or hard_runtime_frontier:
        sections.append(
            PromptSection(
                id="implement_v2_hard_runtime_frontier_state",
                version="v0",
                title="Implement V2 Hard Runtime Frontier State",
                content=_bounded_compact_json(
                    {
                        "rule": "Do not finish from this state alone.",
                        "frontier_card": _hard_runtime_frontier_hot_path_card(
                            hard_runtime_frontier
                            or {"schema_version": 1, "status": "active", "source": "not_yet_populated"}
                        ),
                    },
                    max_chars=_HARD_RUNTIME_FRONTIER_CARD_BYTE_CAP,
                ),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement_v2",
            )
        )
    sections.extend(
        [
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
    )
    return sections


def implement_v2_prompt_section_metrics(lane_input: ImplementLaneInput) -> dict[str, object]:
    """Return prompt-section metrics for v2 prompt assembly."""

    metrics = prompt_section_metrics(build_implement_v2_prompt_sections(lane_input))
    metrics["hot_path_collapse"] = _hot_path_collapse_prompt_metrics(metrics)
    return metrics


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
        "phase": "m6_24_hot_path_collapse_phase_0",
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
                        or failure.get("stderr_tail")
                        or failure.get("stdout_tail")
                        or failure.get("required_next_probe"),
                        140,
                    ),
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


def is_hard_runtime_artifact_task(task_contract: object) -> bool:
    text = _contract_text(task_contract)
    if not text:
        return False
    runtime_markers = (
        "vm",
        "emulator",
        "interpreter",
        "elf",
        "binary",
        "cross-compile",
        "cross compile",
        "runtime",
        "node ",
    )
    artifact_markers = (
        "/tmp/",
        "frame",
        "screenshot",
        "image",
        "bmp",
        "stdout",
        "boot",
        "log",
        "socket",
        "pid file",
    )
    source_markers = (
        "provided",
        "source",
        "source code",
        "build",
        "compile",
        "make",
        "project",
        "repository",
    )
    return (
        any(marker in text for marker in runtime_markers)
        and any(marker in text for marker in artifact_markers)
        and any(marker in text for marker in source_markers)
    )


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
    "build_implement_v2_prompt_sections",
    "FINISH_REPLAY_RECOVERY_SURFACE",
    "HOT_PATH_PROJECTION_SURFACE",
    "implement_v2_prompt_section_metrics",
    "ORDINARY_RESIDENT_SUMMARY_SURFACE",
    "RESIDENT_SIDECAR_STATE_SURFACE",
    "is_deep_probe_hard_runtime_task",
    "is_hard_runtime_artifact_task",
]
