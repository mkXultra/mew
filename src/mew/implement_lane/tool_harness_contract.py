"""Shared tool-harness contract artifacts for implement_v2."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable

from .tool_policy import ImplementLaneToolSpec, list_v2_base_tool_specs
from .types import ImplementLaneTranscriptEvent, ToolResultEnvelope

TOOL_HARNESS_CONTRACT_SCHEMA_VERSION = 1
TOOL_REGISTRY_ARTIFACT_SCHEMA_VERSION = 1
TOOL_RESULT_INDEX_SCHEMA_VERSION = 1


def tool_ref_for_name(name: str) -> str:
    """Return the stable provider-neutral ref for a tool name."""

    normalized = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(name or "").strip())
    return f"implement_v2_tool:{normalized or 'unknown'}:v1"


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def build_tool_registry_artifact(
    *,
    provider: str,
    tool_specs: Iterable[ImplementLaneToolSpec] | None = None,
) -> dict[str, object]:
    """Build the provider-neutral tool registry artifact."""

    specs = tuple(tool_specs if tool_specs is not None else list_v2_base_tool_specs())
    tools = []
    for spec in specs:
        payload = spec.as_dict()
        payload["tool_ref"] = tool_ref_for_name(spec.name)
        tools.append(payload)
    tools_hash = stable_json_hash(tools)
    synthetic_tools = {
        "model_response_error": {
            "name": "model_response_error",
            "tool_ref": tool_ref_for_name("model_response_error"),
            "kind": "synthetic_model_error_result",
            "access": "internal",
            "approval_required": False,
            "dry_run_supported": False,
            "input_transport": "synthetic",
            "provider_native_input_kind": "synthetic_model_error",
        }
    }
    by_tool_ref = {str(tool["tool_ref"]): tool for tool in tools}
    by_tool_ref.update({str(tool["tool_ref"]): tool for tool in synthetic_tools.values()})
    by_tool_name = {str(tool["name"]): tool for tool in tools}
    by_tool_name.update(synthetic_tools)
    return {
        "schema_version": TOOL_REGISTRY_ARTIFACT_SCHEMA_VERSION,
        "provider": provider,
        "tool_registry_ref": f"tool-registry:{tools_hash.removeprefix('sha256:')[:16]}",
        "tool_registry_hash": tools_hash,
        "provider_tool_spec_hash": tools_hash,
        "tools": tools,
        "by_tool_ref": by_tool_ref,
        "by_tool_name": by_tool_name,
        "synthetic_tool_refs": synthetic_tools,
    }


def build_tool_policy_index_artifact(registry: dict[str, object]) -> dict[str, object]:
    """Build a compact tool policy index from a registry artifact."""

    tools = registry.get("tools") if isinstance(registry.get("tools"), list) else []
    by_tool: dict[str, object] = {}
    by_tool_ref: dict[str, object] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        tool_ref = str(tool.get("tool_ref") or tool_ref_for_name(name))
        policy = {
            "access": tool.get("access"),
            "approval_required": bool(tool.get("approval_required")),
            "dry_run_supported": bool(tool.get("dry_run_supported")),
            "input_transport": tool.get("input_transport"),
            "preferred_bulk_argument": tool.get("preferred_bulk_argument") or "",
            "fallback_bulk_arguments": list(tool.get("fallback_bulk_arguments") or []),
            "provider_native_input_kind": tool.get("provider_native_input_kind") or "",
        }
        by_tool[name] = dict(policy, tool_ref=tool_ref)
        by_tool_ref[tool_ref] = dict(policy, tool_name=name)
    synthetic_tools = registry.get("synthetic_tool_refs") if isinstance(registry.get("synthetic_tool_refs"), dict) else {}
    for name, tool in synthetic_tools.items():
        if not isinstance(tool, dict):
            continue
        tool_ref = str(tool.get("tool_ref") or tool_ref_for_name(str(name)))
        policy = {
            "access": tool.get("access") or "internal",
            "approval_required": bool(tool.get("approval_required")),
            "dry_run_supported": bool(tool.get("dry_run_supported")),
            "input_transport": tool.get("input_transport") or "synthetic",
            "preferred_bulk_argument": "",
            "fallback_bulk_arguments": [],
            "provider_native_input_kind": tool.get("provider_native_input_kind") or "synthetic_model_error",
        }
        by_tool[str(name)] = dict(policy, tool_ref=tool_ref)
        by_tool_ref[tool_ref] = dict(policy, tool_name=str(name))
    return {
        "schema_version": TOOL_HARNESS_CONTRACT_SCHEMA_VERSION,
        "tool_registry_ref": registry.get("tool_registry_ref") or "",
        "tool_registry_hash": registry.get("tool_registry_hash") or "",
        "provider_tool_spec_hash": registry.get("provider_tool_spec_hash") or "",
        "by_tool": by_tool,
        "by_tool_ref": by_tool_ref,
    }


def build_tool_result_index_artifact(
    tool_results: Iterable[ToolResultEnvelope],
    *,
    tool_registry_ref: str = "",
    provider_tool_spec_hash: str = "",
) -> dict[str, object]:
    """Build a compact call-id keyed index over tool results."""

    by_provider_call_id: dict[str, object] = {}
    ordered_refs: list[str] = []
    for index, result in enumerate(tool_results, start=1):
        provider_call_id = result.provider_call_id or f"result-{index}"
        result_ref = f"tool-result:{provider_call_id}"
        tool_ref = tool_ref_for_name(result.tool_name)
        ordered_refs.append(result_ref)
        by_provider_call_id[provider_call_id] = {
            "ref": result_ref,
            "tool_ref": tool_ref,
            "mew_tool_call_id": result.mew_tool_call_id,
            "tool_name": result.tool_name,
            "status": result.status,
            "is_error": result.is_error,
            "content_refs": list(result.content_refs),
            "output_refs": list(result.content_refs),
            "evidence_refs": list(result.evidence_refs),
            "side_effect_count": len(result.side_effects),
            "natural_result_text": result.natural_result_text(),
        }
    return {
        "schema_version": TOOL_RESULT_INDEX_SCHEMA_VERSION,
        "tool_registry_ref": tool_registry_ref,
        "provider_tool_spec_hash": provider_tool_spec_hash,
        "ordered_refs": ordered_refs,
        "by_provider_call_id": by_provider_call_id,
        "index_hash": stable_json_hash(by_provider_call_id),
    }


def transcript_jsonl_lines(events: Iterable[ImplementLaneTranscriptEvent]) -> tuple[str, ...]:
    return tuple(json.dumps(event.as_dict(), ensure_ascii=False, sort_keys=True) for event in events)


def tool_results_jsonl_lines(results: Iterable[ToolResultEnvelope]) -> tuple[str, ...]:
    lines = []
    for result in results:
        payload = result.as_dict()
        payload["natural_result_text"] = result.natural_result_text()
        payload["output_refs"] = list(result.content_refs)
        lines.append(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return tuple(lines)


def write_jsonl(path, lines: Iterable[str]) -> None:
    text = "\n".join(lines)
    path.write_text((text + "\n") if text else "", encoding="utf-8")


__all__ = [
    "TOOL_HARNESS_CONTRACT_SCHEMA_VERSION",
    "TOOL_REGISTRY_ARTIFACT_SCHEMA_VERSION",
    "TOOL_RESULT_INDEX_SCHEMA_VERSION",
    "build_tool_policy_index_artifact",
    "build_tool_registry_artifact",
    "build_tool_result_index_artifact",
    "stable_json_hash",
    "tool_ref_for_name",
    "tool_results_jsonl_lines",
    "transcript_jsonl_lines",
    "write_jsonl",
]
