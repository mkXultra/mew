"""Native implement_v2 artifact writer component."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from .completion_resolver import CompletionResolverDecision, write_completion_resolver_artifacts
from .finish_verifier_planner import write_finish_verifier_planner_artifacts
from .finish_verifier_planner_policy import finish_verifier_planner_policy
from .native_done_candidate import NativeDoneCandidate, write_native_done_candidate_artifacts
from .native_fake_provider import NativeFakeProvider
from .native_finish_gate import NativeFinishGateDecision, write_native_finish_gate_artifacts
from .native_ng_resume import NativeNgResumeSignal, write_native_ng_resume_signal_artifacts
from .native_transcript import (
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    OUTPUT_ITEM_KINDS,
    write_native_evidence_observation,
    write_native_transcript_artifacts,
)
from .tool_harness_contract import (
    build_evidence_ref_index_artifact,
    build_evidence_sidecar_artifact,
    build_tool_result_index_artifact,
    tool_results_jsonl_lines,
    write_jsonl,
)
from .tool_result_renderer import render_observability_record
from .tool_registry import build_tool_surface_snapshot
from .tool_routes import route_records_from_results
from .types import ImplementLaneInput, ToolResultEnvelope


def write_native_artifacts(
    root: Path,
    transcript: NativeTranscript,
    *,
    lane_input: ImplementLaneInput | None = None,
    tool_results: tuple[ToolResultEnvelope, ...],
    provider: object,
    status: str = "",
    error: str = "",
    resolver_decisions: tuple[CompletionResolverDecision, ...] = (),
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    done_candidates: tuple[NativeDoneCandidate, ...] = (),
    ng_resume_signals: tuple[NativeNgResumeSignal, ...] = (),
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...] = (),
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
) -> dict[str, Path]:
    paths = write_native_transcript_artifacts(root, transcript)
    paths.update(write_native_tool_result_sidecars(root, tool_results=tool_results))
    paths.update(write_native_render_output_sidecar(root, transcript))
    route_records = route_records_with_tool_surface(
        route_records_from_results(tool_results),
        provider=provider,
    )
    tool_routes_path = root / "tool_routes.jsonl"
    tool_routes_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in route_records),
        encoding="utf-8",
    )
    paths["tool_routes"] = tool_routes_path
    if resolver_decisions:
        paths.update(
            write_completion_resolver_artifacts(
                root,
                resolver_decisions,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if native_finish_gate_decisions:
        paths.update(
            write_native_finish_gate_artifacts(
                root,
                native_finish_gate_decisions,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if done_candidates:
        paths.update(
            write_native_done_candidate_artifacts(
                root,
                done_candidates,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if ng_resume_signals:
        paths.update(
            write_native_ng_resume_signal_artifacts(
                root,
                ng_resume_signals,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    paths.update(
        write_finish_verifier_planner_artifacts(
            root,
            proof_manifest_path=paths.get("proof_manifest"),
            finish_verifier_planner_decisions=finish_verifier_planner_decisions,
            finish_verifier_planner_requests=finish_verifier_planner_requests,
        )
    )
    paths.update(
        write_native_evidence_observation(
            root,
            transcript,
            resolver_decisions=resolver_decisions,
            proof_manifest_path=paths.get("proof_manifest"),
        )
    )
    paths.update(write_provider_request_artifacts(root, provider=provider, status=status, error=error))
    if isinstance(provider, NativeFakeProvider):
        for key in ("transcript_metrics", "proof_manifest"):
            path = paths[key]
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["transport_kind"] = "fake_native"
            payload["native_transport_kind"] = "provider_native"
            if isinstance(payload.get("metrics"), dict):
                payload["metrics"]["transport_kind"] = "fake_native"
                payload["metrics"]["native_transport_kind"] = "provider_native"
            path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    patch_native_default_observability(
        paths,
        provider=provider,
        lane_input=lane_input,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )
    return paths


def write_live_failure_artifacts(
    root: Path,
    *,
    lane_input: ImplementLaneInput,
    transcript: NativeTranscript,
    provider: object,
    tool_results: tuple[ToolResultEnvelope, ...] = (),
    done_candidates: tuple[NativeDoneCandidate, ...] = (),
    native_finish_gate_decisions: tuple[NativeFinishGateDecision, ...] = (),
    ng_resume_signals: tuple[NativeNgResumeSignal, ...] = (),
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...] = (),
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...] = (),
    error: str,
) -> tuple[str, ...]:
    paths = write_native_transcript_artifacts(root, transcript)
    paths.update(write_native_tool_result_sidecars(root, tool_results=tool_results))
    paths.update(write_native_render_output_sidecar(root, transcript))
    route_records = route_records_with_tool_surface(
        route_records_from_results(tool_results),
        provider=provider,
    )
    tool_routes_path = root / "tool_routes.jsonl"
    tool_routes_path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in route_records),
        encoding="utf-8",
    )
    paths["tool_routes"] = tool_routes_path
    if done_candidates:
        paths.update(
            write_native_done_candidate_artifacts(
                root,
                done_candidates,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if native_finish_gate_decisions:
        paths.update(
            write_native_finish_gate_artifacts(
                root,
                native_finish_gate_decisions,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    if ng_resume_signals:
        paths.update(
            write_native_ng_resume_signal_artifacts(
                root,
                ng_resume_signals,
                proof_manifest_path=paths.get("proof_manifest"),
            )
        )
    paths.update(
        write_finish_verifier_planner_artifacts(
            root,
            proof_manifest_path=paths.get("proof_manifest"),
            finish_verifier_planner_decisions=finish_verifier_planner_decisions,
            finish_verifier_planner_requests=finish_verifier_planner_requests,
        )
    )
    request_path = root / "native-provider-requests.json"
    inventory_path = root / "provider-request-inventory.json"
    responses = getattr(provider, "responses", ())
    rejected_responses = getattr(provider, "rejected_responses", ())
    requests = getattr(provider, "requests", ())
    response_count = len(responses) if isinstance(responses, list) else 0
    rejected_response_count = len(rejected_responses) if isinstance(rejected_responses, list) else 0
    request_count = len(requests) if isinstance(requests, list) else 0
    failure_status = "failed_before_completed_native_response" if rejected_response_count else "failed_before_native_response"
    request_payload = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "status": failure_status,
        "error": str(error),
        "request_count": request_count,
        "response_count": response_count,
        "rejected_response_count": rejected_response_count,
        "requests": list(requests) if isinstance(requests, list) else [],
        "responses": list(responses) if isinstance(responses, list) else [],
        "rejected_responses": list(rejected_responses) if isinstance(rejected_responses, list) else [],
    }
    inventory_payload = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "status": failure_status,
        "error": str(error),
        "request_count": request_count,
        "response_count": response_count,
        "rejected_response_count": rejected_response_count,
        "provider_request_inventory": [
            request.get("provider_request_inventory")
            for request in requests
            if isinstance(request, Mapping) and isinstance(request.get("provider_request_inventory"), dict)
        ]
        if isinstance(requests, list)
        else [],
        "provider_response_statuses": [
            response.get("status")
            for response in responses
            if isinstance(response, dict)
        ]
        if isinstance(responses, list)
        else [],
        "rejected_provider_response_statuses": [
            response.get("status")
            for response in rejected_responses
            if isinstance(response, dict)
        ]
        if isinstance(rejected_responses, list)
        else [],
    }
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    patch_native_default_observability(
        paths,
        provider=provider,
        lane_input=lane_input,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )
    return tuple(str(path) for path in (*paths.values(), request_path, inventory_path))


def provider_request_records(provider: object) -> tuple[dict[str, object], ...]:
    requests = getattr(provider, "requests", None)
    if not isinstance(requests, list):
        return ()
    return tuple(dict(request) for request in requests if isinstance(request, Mapping))


def route_records_with_tool_surface(
    route_records: tuple[dict[str, object], ...],
    *,
    provider: object,
) -> tuple[dict[str, object], ...]:
    metadata_by_turn = provider_tool_surface_metadata_by_turn(provider)
    if not metadata_by_turn:
        return route_records
    augmented: list[dict[str, object]] = []
    for record in route_records:
        turn_index = safe_int(record.get("turn_index"), default=0)
        metadata = metadata_by_turn.get(turn_index) or metadata_by_turn.get(-1) or {}
        item = dict(record)
        item["tool_surface_profile_id"] = metadata.get("profile_id", "")
        item["tool_surface_profile_hash"] = metadata.get("profile_hash", "")
        item["tool_surface_route_table_hash"] = metadata.get("route_table_hash", "")
        item["tool_surface_descriptor_hash"] = metadata.get("descriptor_hash", "")
        augmented.append(item)
    return tuple(augmented)


def provider_tool_surface_metadata_by_turn(provider: object) -> dict[int, Mapping[str, object]]:
    requests = getattr(provider, "requests", None)
    if not isinstance(requests, list):
        return {}
    by_turn: dict[int, Mapping[str, object]] = {}
    for request in reversed(requests):
        if not isinstance(request, Mapping):
            continue
        tool_surface = request.get("tool_surface")
        if isinstance(tool_surface, Mapping):
            turn_index = safe_int(request.get("turn_index"), default=0)
            if turn_index:
                by_turn.setdefault(turn_index, tool_surface)
            by_turn.setdefault(-1, tool_surface)
    return by_turn


def write_native_tool_result_sidecars(
    root: Path,
    *,
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, Path]:
    tool_results_path = root / "tool_results.jsonl"
    tool_result_index_path = root / "tool_result_index.json"
    evidence_sidecar_path = root / "evidence_sidecar.json"
    evidence_ref_index_path = root / "evidence_ref_index.json"
    write_jsonl(tool_results_path, tool_results_jsonl_lines(tool_results))
    tool_result_index = build_tool_result_index_artifact(tool_results)
    evidence_sidecar = build_evidence_sidecar_artifact(tool_results)
    evidence_ref_index = build_evidence_ref_index_artifact(evidence_sidecar)
    tool_result_index_path.write_text(
        json.dumps(tool_result_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence_sidecar_path.write_text(
        json.dumps(evidence_sidecar, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    evidence_ref_index_path.write_text(
        json.dumps(evidence_ref_index, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "tool_results": tool_results_path,
        "tool_result_index": tool_result_index_path,
        "evidence_sidecar": evidence_sidecar_path,
        "evidence_ref_index": evidence_ref_index_path,
    }


def write_native_render_output_sidecar(root: Path, transcript: NativeTranscript) -> dict[str, Path]:
    records: list[dict[str, object]] = []
    for item in transcript.items:
        if item.kind not in OUTPUT_ITEM_KINDS or not item.metrics_ref:
            continue
        records.append(
            render_observability_record(
                metrics_ref=item.metrics_ref,
                tool_name=item.tool_name,
                call_id=item.call_id,
                output_text=item.output_text_or_ref,
            )
        )
    if not records:
        return {}
    path = root / "tool_render_outputs.jsonl"
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    return {"tool_render_outputs": path}


def write_provider_request_artifacts(
    root: Path,
    *,
    provider: object,
    status: str = "",
    error: str = "",
) -> dict[str, Path]:
    requests = provider_request_records(provider)
    if not requests:
        return {}
    request_path = root / "native-provider-requests.json"
    inventory_path = root / "provider-request-inventory.json"
    request_payload: dict[str, object] = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "status": status or "unknown",
        "request_count": len(requests),
        "requests": list(requests),
    }
    if error:
        request_payload["error"] = str(error)
    inventory_payload: dict[str, object] = {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "native_transport_kind": "provider_native",
        "status": status or "unknown",
        "request_count": len(requests),
        "provider_request_inventory": [
            request.get("provider_request_inventory")
            for request in requests
            if isinstance(request.get("provider_request_inventory"), dict)
        ],
    }
    if error:
        inventory_payload["error"] = str(error)
    request_path.write_text(json.dumps(request_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    inventory_path.write_text(json.dumps(inventory_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "native_provider_requests": request_path,
        "provider_request_inventory": inventory_path,
    }


def patch_native_default_observability(
    paths: Mapping[str, Path],
    *,
    provider: object,
    lane_input: ImplementLaneInput | None,
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...],
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...],
) -> None:
    facts = native_default_observability_facts(
        provider,
        lane_input=lane_input,
        finish_verifier_planner_decisions=finish_verifier_planner_decisions,
        finish_verifier_planner_requests=finish_verifier_planner_requests,
    )
    for key in ("proof_manifest", "transcript_metrics"):
        path = paths.get(key)
        if path is None or not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload.update(
            {
                field: facts[field]
                for field in (
                    "native_transport_kind",
                    "tool_surface_profile_id",
                    "tool_surface_profile_selection_source",
                    "tool_surface_profile_default",
                    "tool_surface_profile_hash",
                    "developer_contract_transport",
                )
                if field in facts
            }
        )
        metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
        metrics.update(facts)
        payload["metrics"] = metrics
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def native_default_observability_facts(
    provider: object,
    *,
    lane_input: ImplementLaneInput | None,
    finish_verifier_planner_decisions: tuple[Mapping[str, object], ...],
    finish_verifier_planner_requests: tuple[Mapping[str, object], ...],
) -> dict[str, object]:
    requests = provider_request_records(provider)
    latest_request = requests[-1] if requests else {}
    latest_inventory = mapping_or_empty(latest_request.get("provider_request_inventory"))
    tool_surface = latest_tool_surface_metadata(provider)
    if not tool_surface and lane_input is not None:
        tool_surface = build_tool_surface_snapshot(
            lane_config=lane_input.lane_config,
            task_contract=lane_input.task_contract,
            transcript_items=(),
        ).request_metadata()
    planner_policy = finish_verifier_planner_policy(lane_input.lane_config if lane_input is not None else {})
    latest_planner_request = (
        mapping_or_empty(finish_verifier_planner_requests[-1].get("request"))
        if finish_verifier_planner_requests
        else {}
    )
    latest_read_policy = mapping_or_empty(latest_planner_request.get("read_policy"))
    facts: dict[str, object] = {
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "native_transport_kind": "provider_native",
        "provider_native_tool_loop": True,
        "model_json_main_path_detected": False,
        "provider_request_inventory_available": bool(requests),
        "provider_request_count": len(requests),
        "finish_verifier_planner_enabled": bool(latest_read_policy.get("enabled", planner_policy.enabled)),
        "finish_verifier_planner_selection_source": str(
            latest_read_policy.get("selection_source") or planner_policy.selection_source
        ),
        "finish_verifier_planner_request_count": len(finish_verifier_planner_requests),
        "finish_verifier_planner_decision_count": len(finish_verifier_planner_decisions),
        "previous_response_delta_mode": str(latest_request.get("previous_response_delta_mode") or "none"),
        "previous_response_prefix_item_count": safe_int(latest_request.get("input_item_count"), default=0),
    }
    if tool_surface:
        facts.update(
            {
                "tool_surface_profile_id": str(tool_surface.get("profile_id") or ""),
                "tool_surface_profile_selection_source": str(tool_surface.get("profile_selection_source") or ""),
                "tool_surface_profile_default": bool(tool_surface.get("profile_default")),
                "tool_surface_profile_hash": str(tool_surface.get("profile_hash") or ""),
                "tool_surface_descriptor_hash": str(tool_surface.get("descriptor_hash") or ""),
                "tool_surface_route_table_hash": str(tool_surface.get("route_table_hash") or ""),
                "tool_surface_render_policy_hash": str(tool_surface.get("render_policy_hash") or ""),
                "developer_contract_transport": str(
                    latest_inventory.get("developer_contract_transport")
                    or tool_surface.get("developer_contract_transport")
                    or tool_surface.get("developer_contract_transport_policy")
                    or ""
                ),
            }
        )
    return facts


def mapping_or_empty(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def latest_tool_surface_metadata(provider: object) -> dict[str, object]:
    for request in reversed(provider_request_records(provider)):
        tool_surface = request.get("tool_surface")
        if isinstance(tool_surface, Mapping):
            return dict(tool_surface)
        inventory = request.get("provider_request_inventory")
        if isinstance(inventory, Mapping) and isinstance(inventory.get("tool_surface"), Mapping):
            return dict(inventory["tool_surface"])  # type: ignore[index]
    return {}


def safe_int(value: object, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


__all__ = [
    "provider_request_records",
    "route_records_with_tool_surface",
    "write_live_failure_artifacts",
    "write_native_artifacts",
    "write_native_render_output_sidecar",
    "write_native_tool_result_sidecars",
    "write_provider_request_artifacts",
]
