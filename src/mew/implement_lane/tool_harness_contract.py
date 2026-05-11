"""Shared tool-harness contract artifacts for implement_v2."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable

from .execution_evidence import build_oracle_bundle, evidence_events_from_tool_payload
from .tool_policy import ImplementLaneToolSpec, list_v2_base_tool_specs
from .types import ImplementLaneTranscriptEvent, ToolResultEnvelope

TOOL_HARNESS_CONTRACT_SCHEMA_VERSION = 1
TOOL_REGISTRY_ARTIFACT_SCHEMA_VERSION = 1
TOOL_RESULT_INDEX_SCHEMA_VERSION = 1
EVIDENCE_SIDECAR_SCHEMA_VERSION = 1
EVIDENCE_REF_INDEX_SCHEMA_VERSION = 1
MODEL_TURN_INDEX_SCHEMA_VERSION = 1


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


def build_evidence_sidecar_artifact(
    tool_results: Iterable[ToolResultEnvelope],
    *,
    task_contract: dict[str, object] | None = None,
    finish_gate_decision: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build the shared typed-evidence sidecar from tool result payloads."""

    events: list[dict[str, object]] = []
    execution_contracts: list[dict[str, object]] = []
    artifact_evidence: list[dict[str, object]] = []
    verifier_evidence: list[dict[str, object]] = []
    by_tool_result_ref: dict[str, list[str]] = {}
    known_output_refs: list[str] = []
    known_result_evidence_refs: list[str] = []
    known_mutation_refs: list[str] = []
    for index, result in enumerate(tool_results, start=1):
        tool_result_ref = f"tool-result:{result.provider_call_id or index}"
        for ref in result.content_refs:
            _append_unique(known_output_refs, str(ref))
        for ref in result.evidence_refs:
            _append_unique(known_result_evidence_refs, str(ref))
        for effect_index, effect in enumerate(result.side_effects, start=1):
            if not _is_source_mutation_effect(effect):
                continue
            mutation_ref = _source_mutation_ref_for_effect(
                result,
                effect,
                tool_result_ref=tool_result_ref,
                effect_index=effect_index,
            )
            _append_unique(known_mutation_refs, mutation_ref)
        generic_event = _generic_tool_result_event(result, index=index, tool_result_ref=tool_result_ref)
        events.append(generic_event)
        event_ids = [str(generic_event["id"])]
        for mutation_event in _source_mutation_events_from_result(result, tool_result_ref=tool_result_ref):
            events.append(mutation_event)
            event_ids.append(str(mutation_event["id"]))
        payload = _first_mapping(result.content)
        if not payload:
            by_tool_result_ref[tool_result_ref] = event_ids
            continue
        result_events = evidence_events_from_tool_payload(
            tool_index=index,
            tool_name=result.tool_name,
            tool_status=result.status,
            provider_call_id=result.provider_call_id,
            payload=payload,
        )
        for event in result_events:
            event_payload = event.as_dict()
            event_payload.setdefault("provenance", {})
            if isinstance(event_payload["provenance"], dict):
                event_payload["provenance"].setdefault("tool_result_ref", tool_result_ref)
                event_payload["provenance"].setdefault("tool_name", result.tool_name)
            events.append(event_payload)
            event_ids.append(event.id)
        if event_ids:
            by_tool_result_ref[tool_result_ref] = event_ids
        contract = payload.get("execution_contract_normalized")
        if isinstance(contract, dict):
            execution_contracts.append(dict(contract))
        for artifact in payload.get("artifact_evidence") if isinstance(payload.get("artifact_evidence"), list) else []:
            if isinstance(artifact, dict):
                artifact_evidence.append(dict(artifact))
        verifier = payload.get("verifier_evidence")
        if isinstance(verifier, dict):
            verifier_evidence.append(dict(verifier))
    oracle_bundle = build_oracle_bundle(
        task_contract=task_contract or {},
        execution_contracts=execution_contracts,
        verifier_evidence=verifier_evidence,
        artifact_evidence=artifact_evidence,
    )
    sidecar: dict[str, object] = {
        "schema_version": EVIDENCE_SIDECAR_SCHEMA_VERSION,
        "sidecar_kind": "implement_v2_typed_evidence",
        "events": events,
        "event_count": len(events),
        "by_tool_result_ref": by_tool_result_ref,
        "known_output_refs": known_output_refs,
        "known_result_evidence_refs": known_result_evidence_refs,
        "known_mutation_refs": known_mutation_refs,
        "execution_contracts": execution_contracts,
        "artifact_obligations": (
            oracle_bundle.as_dict() if oracle_bundle is not None else {"obligations": [], "provenance_refs": []}
        ),
        "verifier_freshness": _verifier_freshness_sidecar(events),
        "repair_loop": _repair_loop_sidecar(events, finish_gate_decision or {}),
        "finish_gate_decision": dict(finish_gate_decision or {}),
    }
    sidecar["sidecar_hash"] = stable_json_hash(sidecar)
    sidecar["sidecar_ref"] = f"evidence-sidecar:{str(sidecar['sidecar_hash']).removeprefix('sha256:')[:16]}"
    return sidecar


def build_evidence_ref_index_artifact(evidence_sidecar: dict[str, object]) -> dict[str, object]:
    """Build compact indexes over typed evidence refs for hot-path lookup."""

    raw_events = evidence_sidecar.get("events")
    events = [dict(event) for event in raw_events if isinstance(event, dict)] if isinstance(raw_events, list) else []
    by_evidence_ref: dict[str, object] = {}
    by_kind: dict[str, list[str]] = defaultdict(list)
    by_status: dict[str, list[str]] = defaultdict(list)
    by_provider_call_id: dict[str, list[str]] = defaultdict(list)
    by_command_run_id: dict[str, list[str]] = defaultdict(list)
    by_obligation_id: dict[str, list[str]] = defaultdict(list)
    by_path: dict[str, list[str]] = defaultdict(list)
    by_failure_family: dict[str, list[str]] = defaultdict(list)
    by_output_ref: dict[str, list[str]] = defaultdict(list)
    by_tool_ref: dict[str, list[str]] = defaultdict(list)
    by_mutation_ref: dict[str, list[str]] = defaultdict(list)
    by_result_evidence_ref: dict[str, list[str]] = defaultdict(list)
    by_external_ref: dict[str, list[str]] = defaultdict(list)
    aliases: dict[str, list[str]] = defaultdict(list)
    for event in events:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        kind = str(event.get("kind") or "")
        status = str(event.get("status") or "")
        observed = event.get("observed") if isinstance(event.get("observed"), dict) else {}
        by_evidence_ref[event_id] = _compact_evidence_index_entry(event)
        _append_unique(by_kind[kind], event_id)
        _append_unique(by_status[status], event_id)
        for key, index in (
            ("provider_call_id", by_provider_call_id),
            ("command_run_id", by_command_run_id),
            ("obligation_id", by_obligation_id),
        ):
            value = str(event.get(key) or "")
            if value:
                _append_unique(index[value], event_id)
                _append_unique(aliases[value], event_id)
        for path in _observed_paths(observed):
            _append_unique(by_path[path], event_id)
            _append_unique(aliases[path], event_id)
        failure_family = str(observed.get("class") or observed.get("failure_class") or "")
        if failure_family:
            _append_unique(by_failure_family[failure_family], event_id)
        for ref in event.get("refs") if isinstance(event.get("refs"), list) else []:
            if not isinstance(ref, dict):
                continue
            ref_kind = str(ref.get("kind") or "")
            ref_id = str(ref.get("id") or ref.get("ref") or "")
            if not ref_id:
                continue
            _append_unique(by_external_ref[f"{ref_kind}:{ref_id}"], event_id)
            if ref_kind == "output_ref":
                _append_unique(by_output_ref[ref_id], event_id)
                _append_unique(aliases[ref_id], event_id)
            elif ref_kind == "tool_ref":
                _append_unique(by_tool_ref[ref_id], event_id)
                _append_unique(aliases[ref_id], event_id)
            elif ref_kind == "mutation_ref":
                _append_unique(by_mutation_ref[ref_id], event_id)
                _append_unique(aliases[ref_id], event_id)
            elif ref_kind == "evidence_ref":
                _append_unique(by_result_evidence_ref[ref_id], event_id)
            elif ref_kind != "evidence_event":
                _append_unique(aliases[ref_id], event_id)
        _append_unique(aliases[event_id], event_id)
    unresolved = _unresolved_evidence_refs(
        events,
        known_refs_by_kind={
            "evidence_event": set(by_evidence_ref),
            "tool_result_ref": set(evidence_sidecar.get("by_tool_result_ref") or {}),
            "output_ref": set(str(ref) for ref in evidence_sidecar.get("known_output_refs") or []),
            "mutation_ref": set(str(ref) for ref in evidence_sidecar.get("known_mutation_refs") or []),
            "evidence_ref": set(str(ref) for ref in evidence_sidecar.get("known_result_evidence_refs") or []),
        },
    )
    index: dict[str, object] = {
        "schema_version": EVIDENCE_REF_INDEX_SCHEMA_VERSION,
        "sidecar_ref": evidence_sidecar.get("sidecar_ref") or "",
        "sidecar_hash": evidence_sidecar.get("sidecar_hash") or "",
        "hot_path_model_turn_search_allowed": False,
        "by_evidence_ref": by_evidence_ref,
        "by_kind": dict(by_kind),
        "by_status": dict(by_status),
        "by_provider_call_id": dict(by_provider_call_id),
        "by_command_run_id": dict(by_command_run_id),
        "by_obligation_id": dict(by_obligation_id),
        "by_path": dict(by_path),
        "by_failure_family": dict(by_failure_family),
        "by_output_ref": dict(by_output_ref),
        "by_tool_ref": dict(by_tool_ref),
        "by_mutation_ref": dict(by_mutation_ref),
        "by_result_evidence_ref": dict(by_result_evidence_ref),
        "by_external_ref": dict(by_external_ref),
        "aliases": dict(aliases),
        "unresolved_evidence_refs": unresolved,
    }
    index["index_hash"] = stable_json_hash(index)
    return index


def build_model_turn_index_artifact(
    *,
    history: Iterable[dict[str, object]],
    transcript: Iterable[ImplementLaneTranscriptEvent],
) -> dict[str, object]:
    """Build a debug/recovery-only model-turn lookup index."""

    events_by_turn: dict[str, list[str]] = defaultdict(list)
    for event in transcript:
        event_payload = event.as_dict()
        events_by_turn[str(event_payload.get("turn_id") or "")].append(str(event_payload.get("event_id") or ""))
    turns: list[dict[str, object]] = []
    by_turn: dict[str, object] = {}
    by_provider_call_id: dict[str, int] = {}
    for raw_entry in history:
        if not isinstance(raw_entry, dict):
            continue
        turn = _safe_int(raw_entry.get("turn"), default=len(turns) + 1)
        turn_id = f"turn-{turn}" if turn > 0 else f"history-{len(turns) + 1}"
        tool_calls = [dict(item) for item in raw_entry.get("tool_calls") if isinstance(item, dict)] if isinstance(raw_entry.get("tool_calls"), list) else []
        tool_results = (
            [dict(item) for item in raw_entry.get("tool_results") if isinstance(item, dict)]
            if isinstance(raw_entry.get("tool_results"), list)
            else []
        )
        provider_call_ids = [
            str(item.get("provider_call_id") or "")
            for item in (*tool_calls, *tool_results)
            if str(item.get("provider_call_id") or "")
        ]
        model_error = raw_entry.get("model_error") if isinstance(raw_entry.get("model_error"), dict) else {}
        entry = {
            "turn": turn,
            "turn_id": turn_id,
            "summary": str(raw_entry.get("summary") or ""),
            "model_error_class": str(model_error.get("failure_class") or ""),
            "tool_call_count": len(tool_calls),
            "tool_result_count": len(tool_results),
            "provider_call_ids": provider_call_ids,
            "transcript_event_ids": events_by_turn.get(turn_id, []),
        }
        turns.append(entry)
        by_turn[str(turn)] = entry
        for provider_call_id in provider_call_ids:
            by_provider_call_id[provider_call_id] = turn
    index: dict[str, object] = {
        "schema_version": MODEL_TURN_INDEX_SCHEMA_VERSION,
        "index_kind": "debug_recovery_only",
        "hot_path_model_turn_search_allowed": False,
        "turns": turns,
        "by_turn": by_turn,
        "by_provider_call_id": by_provider_call_id,
    }
    index["index_hash"] = stable_json_hash(index)
    return index


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


def _first_mapping(values: tuple[object, ...]) -> dict[str, object]:
    if not values:
        return {}
    first = values[0]
    return dict(first) if isinstance(first, dict) else {}


def _generic_tool_result_event(
    result: ToolResultEnvelope,
    *,
    index: int,
    tool_result_ref: str,
) -> dict[str, object]:
    status = _event_status_from_result_status(result.status, result.is_error)
    refs = [
        {"kind": "tool_result_ref", "id": tool_result_ref},
        {"kind": "tool_ref", "id": tool_ref_for_name(result.tool_name)},
    ]
    refs.extend({"kind": "output_ref", "id": str(ref)} for ref in result.content_refs if str(ref).strip())
    refs.extend({"kind": "evidence_ref", "id": str(ref)} for ref in result.evidence_refs if str(ref).strip())
    return {
        "schema_version": EVIDENCE_SIDECAR_SCHEMA_VERSION,
        "id": f"ev:tool_result:{result.provider_call_id or index}",
        "kind": "tool_result",
        "status": status,
        "observed": {
            "tool_name": result.tool_name,
            "tool_status": result.status,
            "is_error": result.is_error,
            "content_refs": list(result.content_refs),
            "evidence_refs": list(result.evidence_refs),
            "side_effect_count": len(result.side_effects),
        },
        "refs": refs,
        "provider_call_id": result.provider_call_id,
        "tool_call_id": result.mew_tool_call_id,
        "provenance": {"tool_result_ref": tool_result_ref, "tool_name": result.tool_name},
    }


def _source_mutation_events_from_result(
    result: ToolResultEnvelope,
    *,
    tool_result_ref: str,
) -> tuple[dict[str, object], ...]:
    events = []
    for index, effect in enumerate(result.side_effects, start=1):
        if not _is_source_mutation_effect(effect):
            continue
        mutation_ref = _source_mutation_ref_for_effect(
            result,
            effect,
            tool_result_ref=tool_result_ref,
            effect_index=index,
        )
        path = str(effect.get("path") or "")
        record = effect.get("record") if isinstance(effect.get("record"), dict) else {}
        changes = record.get("changes") if isinstance(record.get("changes"), list) else []
        changed_paths = [str(change.get("path") or "") for change in changes if isinstance(change, dict) and str(change.get("path") or "")]
        if not path and changes:
            path = changed_paths[0] if changed_paths else ""
        events.append(
            {
                "schema_version": EVIDENCE_SIDECAR_SCHEMA_VERSION,
                "id": f"ev:source_mutation:{_stable_token(mutation_ref or path or str(index))}",
                "kind": "source_mutation",
                "status": "passed" if result.status == "completed" and not result.is_error else "failed",
                "observed": {
                    "path": path,
                    "paths": changed_paths or ([path] if path else []),
                    "operation": effect.get("operation") or effect.get("kind") or result.tool_name,
                    "approval_status": effect.get("approval_status") or "",
                    "written": bool(effect.get("written", True)),
                    "changed_count": record.get("changed_count") or "",
                },
                "refs": [
                    {"kind": "tool_result_ref", "id": tool_result_ref},
                    {"kind": "tool_ref", "id": tool_ref_for_name(result.tool_name)},
                    {"kind": "mutation_ref", "id": mutation_ref},
                ],
                "provider_call_id": result.provider_call_id,
                "tool_call_id": result.mew_tool_call_id,
                "provenance": {"tool_result_ref": tool_result_ref, "tool_name": result.tool_name},
            }
        )
    return tuple(events)


def _event_status_from_result_status(status: str, is_error: bool) -> str:
    if status in {"completed"} and not is_error:
        return "passed"
    if status in {"running", "yielded"}:
        return "partial"
    if status in {"failed", "denied", "invalid", "interrupted"} or is_error:
        return "failed"
    return "unknown"


def _is_source_mutation_effect(effect: object) -> bool:
    if not isinstance(effect, dict):
        return False
    kind = str(effect.get("kind") or "")
    if kind == "file_write":
        return effect.get("written") is True
    if kind == "source_tree_mutation":
        record = effect.get("record") if isinstance(effect.get("record"), dict) else {}
        changed_count = record.get("changed_count")
        return bool(changed_count)
    return False


def _source_mutation_ref_for_effect(
    result: ToolResultEnvelope,
    effect: object,
    *,
    tool_result_ref: str,
    effect_index: int,
) -> str:
    if not isinstance(effect, dict):
        return f"{tool_result_ref}:mutation:{effect_index}"
    kind = str(effect.get("kind") or "")
    if kind == "source_tree_mutation":
        record = effect.get("record") if isinstance(effect.get("record"), dict) else {}
        identifier = str(record.get("command_run_id") or record.get("provider_call_id") or "")
        if identifier:
            return f"implement-v2-evidence://{result.lane_attempt_id}/source_tree_mutation/{_safe_ref_part(identifier, 'source-tree-mutation')}"
    for ref in result.evidence_refs:
        text = str(ref)
        if "mutation" in text:
            return text
    return f"{tool_result_ref}:mutation:{effect_index}"


def _observed_paths(observed: dict[str, object]) -> tuple[str, ...]:
    paths = observed.get("paths")
    if isinstance(paths, list):
        values = tuple(dict.fromkeys(str(path) for path in paths if str(path).strip()))
        if values:
            return values
    path = str(observed.get("path") or "").strip()
    return (path,) if path else ()


def _verifier_freshness_sidecar(events: list[dict[str, object]]) -> dict[str, object]:
    verifier_events = [
        event
        for event in events
        if str(event.get("kind") or "") in {"verifier_result", "artifact_check", "oracle_check"}
    ]
    return {
        "schema_version": 1,
        "latest_event_ids": [str(event.get("id") or "") for event in verifier_events[-12:] if str(event.get("id") or "")],
        "failed_event_ids": [
            str(event.get("id") or "")
            for event in verifier_events
            if str(event.get("status") or "") in {"failed", "partial", "unknown"}
        ],
    }


def _repair_loop_sidecar(events: list[dict[str, object]], finish_gate_decision: dict[str, object]) -> dict[str, object]:
    families: dict[str, list[str]] = defaultdict(list)
    for event in events:
        if str(event.get("kind") or "") not in {"failure_classification", "structured_finish_gate"}:
            continue
        observed = event.get("observed") if isinstance(event.get("observed"), dict) else {}
        family = str(observed.get("class") or observed.get("failure_class") or observed.get("code") or event.get("kind") or "")
        if family:
            _append_unique(families[family], str(event.get("id") or ""))
    return {
        "schema_version": 1,
        "by_failure_family": dict(families),
        "finish_gate_blockers": list(finish_gate_decision.get("blockers") or [])
        if isinstance(finish_gate_decision.get("blockers"), list)
        else [],
    }


def _compact_evidence_index_entry(event: dict[str, object]) -> dict[str, object]:
    observed = event.get("observed") if isinstance(event.get("observed"), dict) else {}
    return {
        "kind": event.get("kind") or "",
        "status": event.get("status") or "",
        "provider_call_id": event.get("provider_call_id") or "",
        "command_run_id": event.get("command_run_id") or "",
        "obligation_id": event.get("obligation_id") or "",
        "path": observed.get("path") or "",
        "failure_family": observed.get("class") or observed.get("failure_class") or "",
        "refs": list(event.get("refs") or []) if isinstance(event.get("refs"), list) else [],
    }


def _unresolved_evidence_refs(
    events: list[dict[str, object]],
    *,
    known_refs_by_kind: dict[str, set[str]],
) -> list[dict[str, object]]:
    unresolved = []
    for event in events:
        refs = event.get("refs") if isinstance(event.get("refs"), list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_kind = str(ref.get("kind") or "")
            if ref_kind not in known_refs_by_kind:
                continue
            ref_id = str(ref.get("id") or ref.get("ref") or "")
            if ref_id and ref_id not in known_refs_by_kind[ref_kind]:
                unresolved.append({"event_id": event.get("id") or "", "missing_ref": ref_id})
    return unresolved


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _stable_token(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _safe_ref_part(value: object, default: str) -> str:
    text = str(value or "").strip() or default
    safe = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or default


__all__ = [
    "TOOL_HARNESS_CONTRACT_SCHEMA_VERSION",
    "TOOL_REGISTRY_ARTIFACT_SCHEMA_VERSION",
    "TOOL_RESULT_INDEX_SCHEMA_VERSION",
    "build_tool_policy_index_artifact",
    "build_evidence_ref_index_artifact",
    "build_evidence_sidecar_artifact",
    "build_model_turn_index_artifact",
    "build_tool_registry_artifact",
    "build_tool_result_index_artifact",
    "EVIDENCE_REF_INDEX_SCHEMA_VERSION",
    "EVIDENCE_SIDECAR_SCHEMA_VERSION",
    "MODEL_TURN_INDEX_SCHEMA_VERSION",
    "stable_json_hash",
    "tool_ref_for_name",
    "tool_results_jsonl_lines",
    "transcript_jsonl_lines",
    "write_jsonl",
]
