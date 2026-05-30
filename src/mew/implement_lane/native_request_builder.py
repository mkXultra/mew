"""Provider request descriptor builder for native implement_v2."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
from dataclasses import replace
from typing import Iterable, Mapping

from .native_provider_adapter import (
    build_custom_tool_call_output_input_item,
    build_function_call_output_input_item,
    build_responses_request_descriptor,
)
from .native_sidecar_projection import build_compact_native_sidecar_digest
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID, NativeTranscript, NativeTranscriptItem
from .native_workframe_projection import (
    build_native_prompt_input_inventory,
    build_provider_visible_forbidden_fields_report,
)
from .prompt import build_implement_v2_prompt_sections
from .tool_guidance import hide_unavailable_write_file_guidance
from .tool_profiles.codex_hot_path import codex_hot_path_developer_contract
from .tool_registry import (
    CODEX_HOT_PATH_PROFILE_ID,
    ToolSurfaceSnapshot,
    build_tool_surface_snapshot,
    tool_surface_profile_id,
)
from .tool_specs import ImplementLaneToolSpec
from .types import ImplementLaneInput
from ..config import DEFAULT_CODEX_REASONING_EFFORT
from ..prompt_sections import render_prompt_sections

_TASK_PATH_TOKEN_RE = re.compile(
    r"(?<![\w./\\:-])(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\."
    r"(?:js|mjs|cjs|ts|tsx|jsx|py|pyx|c|h|cc|cpp|hpp|rs|go|java|sh|rb|php|pl|lua|json|yaml|yml|toml|md|txt|html|css|"
    r"wasm|bin|out|so|dylib|exe|png|ppm|bmp|jpg|jpeg|gif|svg))"
    r"(?![\w.-])"
)


def build_request_descriptor(
    *,
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    turn_index: int,
    transcript_items: list[NativeTranscriptItem],
    loop_signals: Mapping[str, object] | None = None,
) -> dict[str, object]:
    loop_signals = loop_signals or {}
    provider_visible_transcript_items = [
        provider_visible_native_item(item, lane_input=lane_input)
        for item in transcript_items
        if native_item_provider_visible(item)
    ]
    compact_sidecar_digest = compact_sidecar_digest_for_request(
        lane_input=lane_input,
        lane_attempt_id=lane_attempt_id,
        transcript_items=provider_visible_transcript_items,
        loop_signals=loop_signals,
    )
    tool_surface = tool_surface_snapshot_for_request(
        lane_input,
        provider_visible_transcript_items,
    )
    tool_specs = tool_surface.tool_specs
    developer_contract = (
        codex_hot_path_developer_contract(tool_specs=tool_surface.tool_specs)
        if tool_surface.profile_id == CODEX_HOT_PATH_PROFILE_ID
        else None
    )
    input_items = responses_input_items(
        lane_input,
        provider_visible_transcript_items,
        compact_sidecar_digest=compact_sidecar_digest,
        tool_surface=tool_surface,
    )
    instructions = native_instructions(
        lane_input,
        tool_specs=tool_specs,
        tool_surface=tool_surface,
    )
    forbidden_fields_report = build_provider_visible_forbidden_fields_report(
        input_items=input_items,
        instructions=instructions,
        compact_sidecar_digest=compact_sidecar_digest,
        compact_sidecar_digest_wire_visible=False,
        developer_contract_texts=(developer_contract.rendered_text,) if developer_contract else (),
        developer_contract_forbidden_terms=developer_contract.forbidden_terms if developer_contract else (),
    )
    provider_request_inventory = build_native_prompt_input_inventory(
        compact_sidecar_digest=compact_sidecar_digest,
        provider_visible_forbidden_fields=forbidden_fields_report,
        diagnostic_only_fields=loop_signals.keys(),
        diagnostic_loop_signals=loop_signals,
        compact_sidecar_digest_wire_visible=False,
    )
    provider_request_inventory["tool_surface"] = tool_surface.request_metadata()
    developer_transport = profile_developer_transport(lane_input, tool_surface)
    if developer_transport["developer_contract_id"]:
        provider_request_inventory.update(
            {
                "developer_contract_id": developer_transport["developer_contract_id"],
                "developer_contract_version": developer_transport["developer_contract_version"],
                "developer_contract_hash": developer_transport["developer_contract_hash"],
                "developer_contract_transport": developer_transport["developer_contract_transport"],
                "developer_contract_wire_visible": developer_transport["developer_contract_wire_visible"],
                "developer_contract_fallback_reason": developer_transport["developer_contract_fallback_reason"],
            }
        )
        sections = list(provider_request_inventory.get("model_visible_sections") or ())
        leading_sections = (
            ["profile_developer_contract", "raw_task"]
            if developer_transport["developer_contract_transport"] == "role_developer_input"
            else ["raw_task"]
        )
        provider_request_inventory["model_visible_sections"] = [*leading_sections, *sections]
    return {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native" if provider_is_live(lane_input) else "fake_native",
        "native_transport_kind": "provider_native",
        "lane_attempt_id": lane_attempt_id,
        "turn_index": turn_index,
        "input_item_count": len(transcript_items),
        "input_items": input_items,
        "transcript_window": [item.as_dict() for item in provider_visible_transcript_items],
        "compact_sidecar_digest": dict(compact_sidecar_digest),
        "provider_request_inventory": provider_request_inventory,
        "tool_surface": tool_surface.request_metadata(),
        "tool_surface_profile_id": tool_surface.profile_id,
        "tool_surface_profile_default": tool_surface.profile_default,
        "tool_surface_profile_selection_source": tool_surface.profile_selection_source,
        "tool_surface_profile_version": tool_surface.profile_version,
        "tool_surface_profile_hash": tool_surface.profile_hash,
        "tool_surface_descriptor_hash": tool_surface.descriptor_hash,
        "tool_surface_route_table_hash": tool_surface.route_table_hash,
        "tool_surface_render_policy_hash": tool_surface.render_policy_hash,
        "tool_surface_prompt_contract_id": tool_surface.prompt_contract_id,
        "provider_tool_names": [spec.name for spec in tool_specs],
        "instructions": instructions,
        "model_json_main_path_detected": False,
    }


def build_live_responses_request_descriptor(
    lane_input: ImplementLaneInput,
    *,
    provider: str,
    model: str,
    request_descriptor: Mapping[str, object],
) -> dict[str, object]:
    del provider
    reasoning = reasoning_config(lane_input)
    tool_specs = tool_specs_from_request_descriptor(lane_input, request_descriptor)
    return build_responses_request_descriptor(
        model=model,
        instructions=str(
            request_descriptor.get("instructions")
            or native_instructions(lane_input, tool_specs=tool_specs)
        ),
        input_items=provider_safe_input_items(request_descriptor.get("input_items")),
        tool_specs=tool_specs,
        transcript_window=request_descriptor.get("transcript_window") or (),
        reasoning=reasoning,
        provider_request_id=f"{request_descriptor.get('lane_attempt_id')}:turn:{request_descriptor.get('turn_index')}",
        prompt_cache_key=str(request_descriptor.get("lane_attempt_id") or ""),
        tool_surface_snapshot=mapping_from_request_descriptor(
            request_descriptor.get("tool_surface")
        ),
    )


def tool_specs_from_request_descriptor(
    lane_input: ImplementLaneInput,
    request_descriptor: Mapping[str, object],
) -> tuple[ImplementLaneToolSpec, ...]:
    names = {
        str(name or "").strip()
        for name in (request_descriptor.get("provider_tool_names") or ())
        if str(name or "").strip()
    }
    snapshot = tool_surface_snapshot_for_request(
        lane_input,
        (),
        available_provider_tool_names=tuple(sorted(names)) if names else None,
    )
    return snapshot.tool_specs


def native_instructions(
    lane_input: ImplementLaneInput,
    *,
    tool_specs: tuple[ImplementLaneToolSpec, ...] | None = None,
    tool_surface: ToolSurfaceSnapshot | None = None,
) -> str:
    if tool_specs is None:
        tool_specs = native_tool_specs_for_request(lane_input, ())
    if tool_surface is None:
        tool_surface = tool_surface_snapshot_for_request(lane_input, ())
    sections = [
        section
        for section in build_implement_v2_prompt_sections(
            lane_input,
            tool_specs=tool_specs,
        )
        if section.id
        not in {
            "implement_v2_workframe",
            "implement_v2_task_contract",
            "implement_v2_lane_state",
        }
    ]
    if tool_surface_profile_id(lane_input.lane_config) == CODEX_HOT_PATH_PROFILE_ID:
        sections = [
            section
            for section in sections
            if section.id
            not in {
                "implement_v2_coding_contract",
                "implement_v2_environment_context",
            }
        ]
    rendered = render_prompt_sections(sections)
    if tool_surface.profile_id == CODEX_HOT_PATH_PROFILE_ID and not profile_developer_role_supported(lane_input):
        contract = codex_hot_path_developer_contract(tool_specs=tool_surface.tool_specs)
        rendered = f"{rendered.rstrip()}\n\n{contract.rendered_text}" if rendered.strip() else contract.rendered_text
    if not any(spec.name == "write_file" for spec in tool_specs):
        return hide_unavailable_write_file_guidance(rendered)
    return rendered


def native_tool_specs_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
) -> tuple[ImplementLaneToolSpec, ...]:
    return tool_surface_snapshot_for_request(lane_input, transcript_items).tool_specs


def tool_surface_snapshot_for_request(
    lane_input: ImplementLaneInput,
    transcript_items: object,
    *,
    available_provider_tool_names: tuple[str, ...] | None = None,
) -> ToolSurfaceSnapshot:
    return build_tool_surface_snapshot(
        lane_config=lane_input.lane_config,
        task_contract=lane_input.task_contract,
        transcript_items=transcript_items,
        available_provider_tool_names=available_provider_tool_names,
    )


def responses_input_items(
    lane_input: ImplementLaneInput,
    transcript_items: list[NativeTranscriptItem],
    *,
    compact_sidecar_digest: Mapping[str, object],
    tool_surface: ToolSurfaceSnapshot,
) -> list[dict[str, object]]:
    del compact_sidecar_digest
    task_facts = provider_visible_task_facts(lane_input)
    if tool_surface_profile_id(lane_input.lane_config) == CODEX_HOT_PATH_PROFILE_ID:
        items = [
            *profile_developer_input_items(lane_input, tool_surface),
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": raw_task_provider_visible_text(lane_input),
                    }
                ],
            },
        ]
    else:
        task_payload = {
            "task_contract": dict(lane_input.task_contract),
            "task_facts": task_facts,
            "workspace": lane_input.workspace,
            "lane": lane_input.lane,
        }
        items = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": task_first_provider_visible_text(lane_input, task_facts=task_facts),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": json.dumps(task_payload, ensure_ascii=False),
                    }
                ],
            },
        ]
    for item in transcript_items:
        converted = responses_input_item_from_transcript_item(
            provider_visible_native_item(item, lane_input=lane_input),
        )
        if converted:
            items.append(converted)
    return items


def profile_developer_input_items(
    lane_input: ImplementLaneInput,
    tool_surface: ToolSurfaceSnapshot,
) -> list[dict[str, object]]:
    if tool_surface.profile_id != CODEX_HOT_PATH_PROFILE_ID:
        return []
    if not profile_developer_role_supported(lane_input):
        return []
    contract = codex_hot_path_developer_contract(tool_specs=tool_surface.tool_specs)
    return [
        {
            "role": "developer",
            "content": [
                {
                    "type": "input_text",
                    "text": contract.rendered_text,
                }
            ],
        }
    ]


def profile_developer_transport(
    lane_input: ImplementLaneInput,
    tool_surface: ToolSurfaceSnapshot,
) -> dict[str, object]:
    if tool_surface.profile_id != CODEX_HOT_PATH_PROFILE_ID:
        return {
            "developer_contract_id": "",
            "developer_contract_version": "",
            "developer_contract_hash": "",
            "developer_contract_transport": "",
            "developer_contract_wire_visible": False,
            "developer_contract_fallback_reason": "",
        }
    role_supported = profile_developer_role_supported(lane_input)
    return {
        "developer_contract_id": tool_surface.developer_contract_id,
        "developer_contract_version": tool_surface.developer_contract_version,
        "developer_contract_hash": tool_surface.developer_contract_hash,
        "developer_contract_transport": "role_developer_input" if role_supported else "instructions_folded",
        "developer_contract_wire_visible": True,
        "developer_contract_fallback_reason": "" if role_supported else "provider_lacks_developer_role",
    }


def profile_developer_role_supported(lane_input: ImplementLaneInput) -> bool:
    value = lane_input.lane_config.get("supports_developer_role_input", True)
    if isinstance(value, str):
        return value.strip().casefold() not in {"0", "false", "no", "off"}
    return bool(value)


def raw_task_provider_visible_text(lane_input: ImplementLaneInput) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    for key in ("description", "prompt", "task", "objective", "goal", "title"):
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Complete the requested coding task in the current workspace."


def task_first_provider_visible_text(
    lane_input: ImplementLaneInput,
    *,
    task_facts: Mapping[str, object],
) -> str:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    lines = ["Task"]
    title = str(contract.get("title") or "").strip()
    if title:
        lines.append(f"Title: {title}")
    objective = task_contract_objective_text(contract)
    if objective:
        lines.append(f"Objective: {objective}")
    guidance = str(contract.get("guidance") or "").strip()
    if guidance:
        lines.append(f"Guidance: {guidance}")
    verify_command = str(contract.get("verify_command") or "").strip()
    if verify_command:
        lines.append(f"Verifier: {verify_command}")
    criteria = contract.get("completion_criteria")
    if isinstance(criteria, list):
        rendered_criteria = [str(item or "").strip() for item in criteria if str(item or "").strip()]
        if rendered_criteria:
            lines.append("Completion criteria:")
            lines.extend(f"- {item}" for item in rendered_criteria[:8])
    expected_artifacts = contract.get("expected_artifacts")
    if isinstance(expected_artifacts, list):
        rendered_artifacts = []
        for item in expected_artifacts[:8]:
            if not isinstance(item, Mapping):
                continue
            path = str(item.get("path") or "").strip()
            kind = str(item.get("kind") or "file").strip()
            artifact_id = str(item.get("id") or path or kind).strip()
            rendered_artifacts.append(f"- {artifact_id}: {kind}" + (f" at {path}" if path else ""))
        if rendered_artifacts:
            lines.append("Expected artifacts:")
            lines.extend(rendered_artifacts)
    constraints = contract.get("acceptance_constraints")
    if isinstance(constraints, list):
        rendered_constraints = [str(item or "").strip() for item in constraints if str(item or "").strip()]
        if rendered_constraints:
            lines.append("Acceptance constraints:")
            lines.extend(f"- {item}" for item in rendered_constraints)
    for key, label in (
        ("missing_workspace_paths", "Missing task paths"),
        ("existing_workspace_paths", "Existing task paths"),
        ("verify_command_paths", "Verifier paths"),
    ):
        raw_paths = task_facts.get(key)
        paths = [str(item).strip() for item in raw_paths if str(item).strip()] if isinstance(raw_paths, list) else []
        if paths:
            lines.append(f"{label}: {', '.join(paths)}")
    lines.append("Supporting JSON facts follow in the next input item.")
    return "\n".join(lines)


def task_contract_objective_text(contract: Mapping[str, object]) -> str:
    for key in ("objective", "description", "goal", "task", "prompt"):
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def provider_visible_task_facts(lane_input: ImplementLaneInput) -> dict[str, object]:
    contract = lane_input.task_contract if isinstance(lane_input.task_contract, dict) else {}
    verify_command = str(contract.get("verify_command") or "").strip()
    text_sources = [
        verify_command,
        str(contract.get("description") or ""),
        str(contract.get("title") or ""),
        str(contract.get("guidance") or ""),
    ]
    constraints = contract.get("acceptance_constraints")
    if isinstance(constraints, list):
        text_sources.extend(str(item or "") for item in constraints)

    verify_paths = task_paths_from_text(verify_command, workspace=lane_input.workspace)
    mentioned_paths = dedupe_task_paths(
        path for source in text_sources for path in task_paths_from_text(source, workspace=lane_input.workspace)
    )
    existing_paths = [
        path
        for path in mentioned_paths
        if task_path_has_safe_segments(path) and (Path(lane_input.workspace) / path).exists()
    ]
    missing_paths = [
        path
        for path in mentioned_paths
        if task_path_is_safe_relative(path) and not (Path(lane_input.workspace) / path).exists()
    ]
    facts = {
        "verify_command_paths": verify_paths,
        "mentioned_workspace_paths": mentioned_paths,
        "existing_workspace_paths": existing_paths,
        "missing_workspace_paths": missing_paths,
    }
    return {key: value for key, value in facts.items() if value}


def task_paths_from_text(text: object, *, workspace: str | Path | None = None) -> list[str]:
    raw = str(text or "")
    if not raw.strip():
        return []
    paths: list[str] = []
    try:
        tokens = shlex.split(raw, posix=False)
    except ValueError:
        tokens = []
    for token in tokens:
        candidate = normalize_task_path_token(token, workspace=workspace)
        if candidate:
            paths.append(candidate)
    paths.extend(
        normalize_task_path_token(match.group("path"), workspace=workspace)
        for match in _TASK_PATH_TOKEN_RE.finditer(raw)
    )
    return dedupe_task_paths(path for path in paths if path)


def normalize_task_path_token(token: object, *, workspace: str | Path | None = None) -> str:
    text = str(token or "").strip().strip("`'\"()[]{}<>").rstrip(".,:;").rstrip("/")
    if not text:
        return ""
    if "\\" in text or re.match(r"^[A-Za-z]:", text):
        return ""
    if text.startswith("-"):
        return ""
    if "://" in text:
        return ""
    if text.startswith("/") and workspace:
        workspace_path = Path(workspace).resolve()
        try:
            relative = Path(text).resolve().relative_to(workspace_path)
        except (OSError, ValueError):
            return ""
        text = relative.as_posix()
    if text.startswith(("/", "../", "/tmp/", "/var/tmp/")):
        return ""
    while text.startswith("./"):
        text = text[2:]
    if not task_path_is_safe_relative(text):
        if workspace and task_path_has_safe_segments(text) and (Path(workspace) / text).exists():
            return text
        return ""
    return text


def task_path_has_safe_segments(path: object) -> bool:
    text = str(path or "").strip()
    if not text or "\\" in text or re.match(r"^[A-Za-z]:", text):
        return False
    if text.startswith(("/", "../")) or "/../" in text:
        return False
    parts = text.split("/")
    return not any(part in {"", ".", ".."} or part.startswith("..") for part in parts)


def task_path_is_safe_relative(path: object) -> bool:
    text = str(path or "").strip()
    if not task_path_has_safe_segments(text):
        return False
    return bool(_TASK_PATH_TOKEN_RE.fullmatch(text))


def dedupe_task_paths(paths: Iterable[object]) -> list[str]:
    result: list[str] = []
    for path in paths:
        text = str(path or "").strip()
        if text and text not in result:
            result.append(text)
        if len(result) >= 12:
            break
    return result


def compact_sidecar_digest_for_request(
    *,
    lane_input: ImplementLaneInput,
    lane_attempt_id: str,
    transcript_items: list[NativeTranscriptItem],
    loop_signals: Mapping[str, object],
) -> dict[str, object]:
    del loop_signals
    transcript = NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider="codex" if provider_is_live(lane_input) else "fake_native",
        model=str(lane_input.model or "gpt-5.5"),
        items=tuple(provider_visible_native_item(item, lane_input=lane_input) for item in transcript_items),
    )
    return build_compact_native_sidecar_digest(transcript)


def responses_input_item_from_transcript_item(item: NativeTranscriptItem) -> dict[str, object]:
    if item.kind == "input_message":
        return {"role": "user", "content": [{"type": "input_text", "text": item.output_text_or_ref}]}
    if item.kind == "assistant_message":
        return {"role": "assistant", "content": [{"type": "output_text", "text": item.output_text_or_ref}]}
    if item.kind == "reasoning":
        return {}
    if item.kind in {"function_call", "finish_call"}:
        return {
            "type": "function_call",
            "id": item.provider_item_id,
            "call_id": item.call_id,
            "name": item.tool_name,
            "arguments": item.arguments_json_text or "{}",
        }
    if item.kind == "custom_tool_call":
        return {
            "type": "custom_tool_call",
            "id": item.provider_item_id,
            "call_id": item.call_id,
            "name": item.tool_name,
            "input": item.custom_input_text,
        }
    if item.kind == "custom_tool_call_output":
        return build_custom_tool_call_output_input_item(
            call_id=item.call_id,
            name=item.tool_name,
            output=item.output_text_or_ref,
        )
    if item.kind in {"function_call_output", "finish_output"}:
        return build_function_call_output_input_item(call_id=item.call_id, output=item.output_text_or_ref)
    return {}


def provider_visible_native_item(
    item: NativeTranscriptItem,
    *,
    lane_input: ImplementLaneInput,
) -> NativeTranscriptItem:
    if native_tool_available("write_file", lane_input=lane_input, lane_config=lane_input.lane_config):
        return item
    output_text = hide_unavailable_write_file_guidance(item.output_text_or_ref)
    if item.tool_name != "write_file":
        if output_text == item.output_text_or_ref:
            return item
        return replace(item, output_text_or_ref=output_text)
    if item.kind in {"function_call", "custom_tool_call"}:
        return replace(
            item,
            tool_name="unavailable_write_tool",
            arguments_json_text='{"unavailable_tool":true,"redacted_arguments":true}',
            custom_input_text="",
            output_text_or_ref=output_text,
        )
    return replace(
        item,
        tool_name="unavailable_write_tool",
        output_text_or_ref=output_text,
    )


def native_tool_available(
    tool_name: object,
    *,
    lane_input: ImplementLaneInput,
    lane_config: Mapping[str, object],
) -> bool:
    try:
        snapshot = build_tool_surface_snapshot(
            lane_config=lane_config,
            task_contract=lane_input.task_contract,
            transcript_items=(),
            available_provider_tool_names=(str(tool_name or ""),),
        )
    except ValueError:
        return False
    return str(tool_name or "") in set(snapshot.provider_tool_names)


def native_item_provider_visible(item: NativeTranscriptItem) -> bool:
    if str(item.call_id or "").startswith("call-final-verifier-closeout"):
        return False
    return True


def mapping_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def provider_safe_input_items(value: object) -> list[dict[str, object]]:
    items = []
    for item in mapping_list(value):
        if item.get("type") == "reasoning" and not item.get("encrypted_content"):
            continue
        items.append(item)
    return items


def reasoning_config(lane_input: ImplementLaneInput) -> dict[str, object] | bool:
    effort = str(lane_input.effort or os.environ.get("MEW_CODEX_REASONING_EFFORT", DEFAULT_CODEX_REASONING_EFFORT))
    effort = effort.strip()
    if not effort or effort.lower() in {"none", "off", "false"}:
        return False
    return {"effort": effort}


def provider_is_live(lane_input: ImplementLaneInput) -> bool:
    return str(lane_input.model_backend or "").strip().lower() in {"codex", "openai"}


def mapping_from_request_descriptor(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


__all__ = [
    "build_live_responses_request_descriptor",
    "build_request_descriptor",
    "tool_specs_from_request_descriptor",
]
