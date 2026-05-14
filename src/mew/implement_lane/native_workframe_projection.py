"""WorkFrame projections derived from native implement_v2 transcripts.

These helpers keep WorkFrame in the Phase 4 role described by the native
transcript rebuild design: a deterministic projection and policy analyzer over
transcript/evidence sidecars, not runtime authority and not a second prompt
state channel.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .affordance_visibility import fields_from_forbidden_violations, scan_forbidden_provider_visible
from .native_sidecar_projection import (
    NATIVE_RESPONSE_ITEMS_SOURCE_OF_TRUTH,
    NATIVE_SIDECAR_TRANSPORT_CHANGE,
    NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
    PROVIDER_VISIBLE_STEERING_KEYS,
    build_compact_native_sidecar_digest,
    build_native_evidence_ref_index,
    build_native_evidence_sidecar,
    build_native_model_turn_index,
    build_native_tool_result_index,
    native_projection_transcript_hash,
    stable_json_hash,
)
from .native_transcript import IMPLEMENT_V2_NATIVE_RUNTIME_ID, NativeTranscript, NativeTranscriptItem, OUTPUT_ITEM_KINDS
from .workframe import WorkFrameInputs, canonicalize_workframe_inputs
from .workframe_variants import (
    DEFAULT_WORKFRAME_VARIANT,
    common_workframe_inputs_from_workframe_inputs,
    canonicalize_common_workframe_inputs,
    project_workframe_with_variant,
    validate_workframe_variant_name,
)

NATIVE_WORKFRAME_PROJECTION_SCHEMA_VERSION = 1
NATIVE_PROMPT_INPUT_INVENTORY_SCHEMA_VERSION = 1
NATIVE_PROVIDER_VISIBLE_FORBIDDEN_FIELDS_SCHEMA_VERSION = 1


def build_native_workframe_sidecar_events(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    evidence_sidecar: Mapping[str, object] | None = None,
) -> tuple[dict[str, object], ...]:
    """Project transcript outputs into WorkFrame reducer sidecar events."""

    transcript_hash = native_projection_transcript_hash(transcript)
    events: list[dict[str, object]] = []
    for index, output in enumerate(
        [item for item in _normalized_items(transcript) if _text(item.get("kind")) in OUTPUT_ITEM_KINDS],
        start=1,
    ):
        events.append(_workframe_event_from_output(output, index=index, transcript_hash=transcript_hash))
    if isinstance(evidence_sidecar, Mapping):
        raw_events = evidence_sidecar.get("events")
        if isinstance(raw_events, (list, tuple)):
            for event in raw_events:
                if not isinstance(event, Mapping):
                    continue
                projected = _workframe_event_from_evidence_event(event, transcript_hash=transcript_hash)
                if projected:
                    events.append(projected)
    return tuple(_dedupe_events(events))


def build_native_workframe_inputs(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    task_id: str,
    objective: str,
    success_contract_ref: str = "",
    evidence_sidecar: Mapping[str, object] | None = None,
    sidecar_events: Iterable[Mapping[str, object]] = (),
    prompt_inventory: Iterable[Mapping[str, object]] = (),
    baseline_metrics: Mapping[str, object] | None = None,
    previous_workframe_hash: str = "",
    workspace_root: str = "",
    artifact_root: str = "",
    turn_id: str = "",
) -> WorkFrameInputs:
    """Build stable WorkFrameInputs from a native transcript and sidecars."""

    generated_events = build_native_workframe_sidecar_events(transcript, evidence_sidecar=evidence_sidecar)
    merged_events = _dedupe_events([*generated_events, *(dict(event) for event in sidecar_events if isinstance(event, Mapping))])
    context = _transcript_context(transcript)
    return WorkFrameInputs(
        attempt_id=context["lane_attempt_id"] or "native-transcript-attempt",
        turn_id=turn_id or _latest_turn_id(transcript),
        task_id=task_id,
        objective=objective,
        success_contract_ref=success_contract_ref,
        constraints=("native_transcript_projection", "sidecar_digest_only_provider_context"),
        sidecar_events=tuple(merged_events),
        prompt_inventory=tuple(dict(item) for item in prompt_inventory if isinstance(item, Mapping)),
        baseline_metrics={
            "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
            "transport_kind": "provider_native",
            "transport_change": NATIVE_SIDECAR_TRANSPORT_CHANGE,
            "transcript_hash": context["transcript_hash"],
            **dict(baseline_metrics or {}),
        },
        previous_workframe_hash=previous_workframe_hash,
        workspace_root=workspace_root,
        artifact_root=artifact_root,
    )


def build_native_workframe_debug_bundle(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    task_id: str,
    objective: str,
    success_contract_ref: str = "",
    evidence_sidecar: Mapping[str, object] | None = None,
    tool_result_index: Mapping[str, object] | None = None,
    evidence_ref_index: Mapping[str, object] | None = None,
    model_turn_index: Mapping[str, object] | None = None,
    compact_sidecar_digest: Mapping[str, object] | None = None,
    sidecar_events: Iterable[Mapping[str, object]] = (),
    prompt_inventory: Iterable[Mapping[str, object]] = (),
    variant: object = DEFAULT_WORKFRAME_VARIANT,
    workspace_root: str = "",
    artifact_root: str = "",
    turn_id: str = "",
) -> dict[str, object]:
    """Build the derived WorkFrame debug bundle from native transcript data."""

    workframe_variant = validate_workframe_variant_name(variant)
    tool_index = dict(tool_result_index or build_native_tool_result_index(transcript))
    evidence = dict(evidence_sidecar or build_native_evidence_sidecar(transcript, tool_result_index=tool_index))
    evidence_index = dict(evidence_ref_index or build_native_evidence_ref_index(evidence))
    turn_index = dict(model_turn_index or build_native_model_turn_index(transcript))
    digest = dict(
        compact_sidecar_digest
        or build_compact_native_sidecar_digest(
            transcript,
            evidence_sidecar=evidence,
            tool_result_index=tool_index,
            evidence_ref_index=evidence_index,
            model_turn_index=turn_index,
        )
    )
    inputs = build_native_workframe_inputs(
        transcript,
        task_id=task_id,
        objective=objective,
        success_contract_ref=success_contract_ref,
        evidence_sidecar=evidence,
        sidecar_events=sidecar_events,
        prompt_inventory=prompt_inventory,
        baseline_metrics={
            "tool_result_index_hash": tool_index.get("index_hash") or "",
            "evidence_sidecar_hash": evidence.get("sidecar_hash") or "",
            "evidence_ref_index_hash": evidence_index.get("index_hash") or "",
            "model_turn_index_hash": turn_index.get("index_hash") or "",
            "compact_sidecar_digest_hash": digest.get("digest_hash") or "",
        },
        workspace_root=workspace_root,
        artifact_root=artifact_root,
        turn_id=turn_id,
    )
    context = _transcript_context(transcript)
    common_inputs = common_workframe_inputs_from_workframe_inputs(
        inputs,
        transcript={
            "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
            "response_items_source_of_truth": NATIVE_RESPONSE_ITEMS_SOURCE_OF_TRUTH,
            "transcript_hash": context["transcript_hash"],
            "latest_tool_call_ref": _latest_provider_call_ref(tool_index),
            "latest_tool_result_ref": _latest_tool_result_ref(tool_index),
            "paired_call_result_index_ref": tool_index.get("index_hash") or "",
        },
        sidecars={
            "typed_evidence_delta_ref": evidence.get("sidecar_ref") or "",
            "evidence_ref_index_ref": evidence_index.get("index_hash") or "",
            "verifier_freshness_ref": stable_json_hash(evidence.get("verifier_freshness") or {}),
            "compact_sidecar_digest_hash": digest.get("digest_hash") or "",
        },
        indexes={
            "tool_result_index_ref": tool_index.get("index_hash") or "",
            "evidence_search_index_ref": evidence_index.get("index_hash") or "",
            "model_turn_index_ref": turn_index.get("index_hash") or "",
            "model_turn_index_usage": "debug_plateau_recovery_only",
        },
        replay={
            "workframe_cursor_ref": "",
            "replay_manifest_ref": context["transcript_hash"],
        },
        migration={
            "native_phase": "phase4_derived_projection",
            "transport_change": NATIVE_SIDECAR_TRANSPORT_CHANGE,
        },
    )
    projection = project_workframe_with_variant(common_inputs, variant=workframe_variant)
    workframe = projection.workframe
    report = projection.invariant_report
    bundle: dict[str, object] = {
        "schema_version": NATIVE_WORKFRAME_PROJECTION_SCHEMA_VERSION,
        "bundle_kind": "native_transcript_workframe_debug_projection",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "transport_change": NATIVE_SIDECAR_TRANSPORT_CHANGE,
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "turn_id": inputs.turn_id,
        "workframe_variant": workframe_variant,
        "projection_policy": native_workframe_projection_policy(workframe_variant),
        "transcript_hash": context["transcript_hash"],
        "sidecar_digest_hash": digest.get("digest_hash") or "",
        "reducer_inputs": {
            "schema_version": 1,
            "workframe_inputs": inputs.as_dict(),
            "canonical": canonicalize_workframe_inputs(inputs),
            "common_workframe_inputs": common_inputs.as_dict(),
            "common_canonical": canonicalize_common_workframe_inputs(common_inputs),
            "shared_substrate_hash": projection.shared_substrate_hash,
        },
        "reducer_output": workframe.as_dict(),
        "invariant_report": report.as_dict(),
        "prompt_visible_workframe": _prompt_visible_workframe(workframe.as_dict()),
        "prompt_render_inventory": build_native_prompt_input_inventory(
            compact_sidecar_digest=digest,
            source_prompt_inventory=prompt_inventory,
        ),
        "workframe_cursor": {
            "schema_version": 1,
            "attempt_id": inputs.attempt_id,
            "turn_id": inputs.turn_id,
            "workframe_id": workframe.trace.workframe_id,
            "workframe_variant": workframe_variant,
            "shared_substrate_hash": projection.shared_substrate_hash,
            "projection_hash": projection.projection_hash,
            "input_hash": workframe.trace.input_hash,
            "output_hash": workframe.trace.output_hash,
            "previous_workframe_hash": inputs.previous_workframe_hash,
        },
    }
    bundle["bundle_hash"] = stable_json_hash({key: value for key, value in bundle.items() if key != "bundle_hash"})
    return bundle


def build_native_prompt_input_inventory(
    *,
    compact_sidecar_digest: Mapping[str, object],
    source_prompt_inventory: Iterable[Mapping[str, object]] = (),
    provider_visible_forbidden_fields: Mapping[str, object] | None = None,
    diagnostic_only_fields: Iterable[object] = (),
    diagnostic_loop_signals: Mapping[str, object] | None = None,
    previous_response_delta_mode: str = "none",
    previous_response_suppressed_context_refresh_item_count: int = 0,
    compact_sidecar_digest_wire_visible: bool = True,
) -> dict[str, object]:
    """Describe the native provider input inventory for Phase 4 tests."""

    diagnostic_fields = sorted(str(item) for item in diagnostic_only_fields if str(item).strip())
    diagnostic_signals = dict(diagnostic_loop_signals or {})
    suppressed_refresh_count = max(0, int(previous_response_suppressed_context_refresh_item_count or 0))
    digest_wire_visible = bool(compact_sidecar_digest_wire_visible) and suppressed_refresh_count == 0
    model_visible_sections = ["native_transcript_window"]
    if digest_wire_visible:
        model_visible_sections.append("compact_sidecar_digest")
    else:
        model_visible_sections.append("task_context_refresh")
    return {
        "schema_version": NATIVE_PROMPT_INPUT_INVENTORY_SCHEMA_VERSION,
        "input_contract": "native_transcript_window_plus_compact_sidecar_digest",
        "model_visible_sections": model_visible_sections,
        "ordinary_model_visible_state": {
            "frontier": False,
            "todo": False,
            "proof": False,
            "evidence_object": False,
        },
        "debug_only_sections": ["workframe_debug_bundle", "model_turn_index", "native_loop_signals"],
        "diagnostic_only_fields": diagnostic_fields,
        "diagnostic_loop_signals": diagnostic_signals,
        "diagnostic_only_fields_report": {
            "schema_version": 1,
            "report_kind": "diagnostic_only_fields",
            "ok": True,
            "provider_visible": False,
            "fields": diagnostic_fields,
            "source_sections": ["provider_request_inventory", "observer_detail"],
        },
        "provider_visible_forbidden_fields": dict(
            provider_visible_forbidden_fields
            or {
                "schema_version": NATIVE_PROVIDER_VISIBLE_FORBIDDEN_FIELDS_SCHEMA_VERSION,
                "report_kind": "provider_visible_forbidden_fields",
                "ok": True,
                "detected": [],
                "checked": sorted(PROVIDER_VISIBLE_STEERING_KEYS),
            }
        ),
        "compact_sidecar_digest_hash": compact_sidecar_digest.get("digest_hash") or "",
        "compact_sidecar_digest_wire_visible": digest_wire_visible,
        "previous_response_delta_mode": previous_response_delta_mode or "none",
        "previous_response_suppressed_context_refresh_item_count": suppressed_refresh_count,
        "source_prompt_inventory": [dict(item) for item in source_prompt_inventory if isinstance(item, Mapping)],
    }


def build_provider_visible_forbidden_fields_report(
    *,
    input_items: Iterable[Mapping[str, object]],
    instructions: str,
    compact_sidecar_digest: Mapping[str, object],
    compact_sidecar_digest_wire_visible: bool = True,
) -> dict[str, object]:
    """Report steering/control fields visible to the provider request hot path."""

    provider_visible_payload = {
        "input_items": [dict(item) for item in input_items if isinstance(item, Mapping)],
        "instructions": instructions,
        "compact_sidecar_digest": dict(compact_sidecar_digest)
        if compact_sidecar_digest_wire_visible
        else {},
    }
    violations = scan_forbidden_provider_visible(provider_visible_payload, surface="provider_request")
    detected = fields_from_forbidden_violations(violations)
    return {
        "schema_version": NATIVE_PROVIDER_VISIBLE_FORBIDDEN_FIELDS_SCHEMA_VERSION,
        "report_kind": "provider_visible_forbidden_fields",
        "ok": not detected,
        "detected": detected,
        "checked": sorted(PROVIDER_VISIBLE_STEERING_KEYS),
        "violations": violations,
        "payload_sha256": stable_json_hash(provider_visible_payload),
    }


def native_workframe_projection_policy(variant: object = DEFAULT_WORKFRAME_VARIANT) -> dict[str, object]:
    """Return the Phase 4 WorkFrame role for a variant."""

    return {
        "variant": validate_workframe_variant_name(variant),
        "role": "projection_policy_analyzer",
        "runtime_wired": False,
        "tool_execution_authority": False,
        "evidence_schema_authority": False,
        "provider_request_authority": False,
        "model_authored_state_authority": False,
    }


def _workframe_event_from_output(output: Mapping[str, object], *, index: int, transcript_hash: str) -> dict[str, object]:
    call_id = _text(output.get("call_id")) or f"output-{index}"
    tool_name = _text(output.get("tool_name") or output.get("kind"))
    evidence_refs = _dedupe(
        (
            *_strings(output.get("evidence_refs")),
            *_strings(output.get("content_refs")),
            *_strings(output.get("sidecar_refs")),
        )
    )
    event: dict[str, object] = {
        "event_sequence": _safe_int(output.get("sequence"), default=index),
        "event_id": f"native-output:{call_id}",
        "kind": tool_name,
        "native_transcript_kind": _text(output.get("kind")),
        "status": _text(output.get("status") or "completed"),
        "tool_name": tool_name,
        "provider_call_id": call_id,
        "transcript_item_sequence": _safe_int(output.get("sequence"), default=index),
        "transcript_hash": transcript_hash,
        "evidence_refs": evidence_refs,
        "content_refs": _strings(output.get("content_refs")),
        "sidecar_refs": _strings(output.get("sidecar_refs")),
        "summary": _bounded_text(output.get("output_text_or_ref"), limit=300),
    }
    paths = _paths_from_output(output)
    if paths:
        event["target_paths"] = paths
        event["paths"] = paths
    if bool(output.get("is_error")):
        event["is_error"] = True
        event["family"] = _text(output.get("status") or "tool_error")
    if tool_name in {"run_tests", "verifier", "strict_verifier"}:
        event.setdefault("intent", "verify")
        event.setdefault(
            "execution_contract_normalized",
            {"role": "verify", "proof_role": "verifier", "acceptance_kind": "external_verifier"},
        )
    return event


def _workframe_event_from_evidence_event(event: Mapping[str, object], *, transcript_hash: str) -> dict[str, object]:
    kind = _text(event.get("kind"))
    if kind == "tool_result":
        return {}
    if kind not in {
        "source_mutation",
        "source_tree_mutation",
        "strict_verifier",
        "verifier",
        "verifier_result",
        "run_tests",
        "artifact_check",
        "oracle_check",
        "failure_classification",
        "structured_finish_gate",
    }:
        return {}
    observed = event.get("observed") if isinstance(event.get("observed"), Mapping) else {}
    refs = event.get("refs") if isinstance(event.get("refs"), (list, tuple)) else ()
    evidence_refs = _dedupe(
        _text(ref.get("id") or ref.get("ref"))
        for ref in refs
        if isinstance(ref, Mapping) and _text(ref.get("id") or ref.get("ref"))
    )
    projected = {
        "event_sequence": _safe_int(event.get("transcript_item_sequence"), default=0),
        "event_id": _text(event.get("id")),
        "kind": kind,
        "status": _text(event.get("status") or "unknown"),
        "provider_call_id": _text(event.get("provider_call_id")),
        "transcript_hash": transcript_hash,
        "evidence_refs": evidence_refs,
        "summary": _bounded_text(observed.get("summary") or event.get("summary"), limit=300),
    }
    paths = _paths_from_observed(observed)
    if paths:
        projected["target_paths"] = paths
        projected["paths"] = paths
    if kind in {"strict_verifier", "verifier", "verifier_result", "run_tests"}:
        projected.setdefault("intent", "verify")
        projected.setdefault(
            "execution_contract_normalized",
            {"role": "verify", "proof_role": "verifier", "acceptance_kind": "external_verifier"},
        )
    return projected


def _prompt_visible_workframe(workframe: Mapping[str, object]) -> dict[str, object]:
    finish_readiness = workframe.get("finish_readiness") if isinstance(workframe.get("finish_readiness"), Mapping) else {}
    trace = workframe.get("trace") if isinstance(workframe.get("trace"), Mapping) else {}
    return {
        "schema_version": 1,
        "projection_kind": "native_workframe_sidecar_debug_ref",
        "provider_visible": False,
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "workframe": {
            "finish_readiness": {
                "missing_evidence_refs": list(finish_readiness.get("required_evidence_refs") or [])
                if isinstance(finish_readiness.get("required_evidence_refs"), list)
                else [],
            },
            "trace": {
                "input_hash": trace.get("input_hash") or "",
                "output_hash": trace.get("output_hash") or "",
            },
        },
    }


def _latest_provider_call_ref(tool_result_index: Mapping[str, object]) -> str:
    ordered = tool_result_index.get("ordered_refs") if isinstance(tool_result_index.get("ordered_refs"), list) else []
    if not ordered:
        return ""
    return str(ordered[-1]).removeprefix("tool-result:")


def _latest_tool_result_ref(tool_result_index: Mapping[str, object]) -> str:
    ordered = tool_result_index.get("ordered_refs") if isinstance(tool_result_index.get("ordered_refs"), list) else []
    return str(ordered[-1]) if ordered else ""


def _transcript_context(transcript: NativeTranscript | Mapping[str, object]) -> dict[str, str]:
    if isinstance(transcript, NativeTranscript):
        return {
            "lane_attempt_id": transcript.lane_attempt_id,
            "provider": transcript.provider,
            "model": transcript.model,
            "transcript_hash": native_projection_transcript_hash(transcript),
        }
    return {
        "lane_attempt_id": _text(transcript.get("lane_attempt_id")),
        "provider": _text(transcript.get("provider")),
        "model": _text(transcript.get("model")),
        "transcript_hash": native_projection_transcript_hash(transcript),
    }


def _normalized_items(transcript: NativeTranscript | Mapping[str, object]) -> list[dict[str, object]]:
    if isinstance(transcript, NativeTranscript):
        raw_items: Iterable[NativeTranscriptItem | Mapping[str, object]] = transcript.items
    else:
        raw = transcript.get("items")
        raw_items = raw if isinstance(raw, (list, tuple)) else ()
    items: list[dict[str, object]] = []
    for index, raw_item in enumerate(raw_items, start=1):
        if isinstance(raw_item, NativeTranscriptItem):
            item = raw_item.as_dict()
        elif isinstance(raw_item, Mapping):
            item = dict(raw_item)
        else:
            continue
        item.setdefault("sequence", index)
        items.append(item)
    items.sort(key=lambda item: (_safe_int(item.get("sequence"), default=0), _safe_int(item.get("output_index"), default=0)))
    return items


def _latest_turn_id(transcript: NativeTranscript | Mapping[str, object]) -> str:
    items = _normalized_items(transcript)
    if not items:
        return "turn-1"
    return _text(items[-1].get("turn_id")) or "turn-1"


def _dedupe_events(events: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    by_id: dict[str, dict[str, object]] = {}
    anonymous: list[dict[str, object]] = []
    for index, event in enumerate(events, start=1):
        payload = dict(event)
        event_id = _text(payload.get("event_id") or payload.get("id"))
        payload.setdefault("event_sequence", index)
        if not event_id:
            anonymous.append(payload)
            continue
        payload["event_id"] = event_id
        by_id[event_id] = payload
    return sorted([*by_id.values(), *anonymous], key=lambda event: (_safe_int(event.get("event_sequence"), default=0), _text(event.get("event_id"))))


def _paths_from_output(output: Mapping[str, object]) -> list[str]:
    paths = output.get("paths")
    if isinstance(paths, (list, tuple)):
        return _dedupe(_text(path) for path in paths if _text(path))
    path = _text(output.get("path"))
    return [path] if path else []


def _paths_from_observed(observed: Mapping[str, object]) -> list[str]:
    paths = observed.get("paths")
    if isinstance(paths, (list, tuple)):
        return _dedupe(_text(path) for path in paths if _text(path))
    path = _text(observed.get("path"))
    return [path] if path else []


def _bounded_text(value: object, *, limit: int) -> str:
    text = " ".join(_text(value).split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _strings(value: object) -> list[str]:
    if isinstance(value, (list, tuple)):
        return _dedupe(_text(item) for item in value if _text(item))
    text = _text(value)
    return [text] if text else []


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _safe_int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


__all__ = [
    "NATIVE_PROMPT_INPUT_INVENTORY_SCHEMA_VERSION",
    "NATIVE_WORKFRAME_PROJECTION_SCHEMA_VERSION",
    "build_native_prompt_input_inventory",
    "build_native_workframe_debug_bundle",
    "build_native_workframe_inputs",
    "build_native_workframe_sidecar_events",
    "native_workframe_projection_policy",
]
