"""Derived sidecar projections for the native implement_v2 transcript.

Phase 4 keeps these helpers pure and runtime-unwired: the authoritative input is
the provider-native transcript, while indexes, evidence sidecars, compact
provider digests, and compatibility lane state are rebuilt projections.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Iterable, Mapping

from .native_transcript import (
    CALL_ITEM_KINDS,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    NativeTranscript,
    NativeTranscriptItem,
    OUTPUT_ITEM_KINDS,
    native_transcript_hash,
)

NATIVE_SIDECAR_PROJECTION_SCHEMA_VERSION = 1
NATIVE_TOOL_RESULT_INDEX_SCHEMA_VERSION = 1
NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION = 1
NATIVE_EVIDENCE_REF_INDEX_SCHEMA_VERSION = 1
NATIVE_MODEL_TURN_INDEX_SCHEMA_VERSION = 1
NATIVE_COMPACT_SIDECAR_DIGEST_SCHEMA_VERSION = 1
NATIVE_UPDATED_LANE_STATE_SCHEMA_VERSION = 1

NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH = "response_transcript.json"
NATIVE_RESPONSE_ITEMS_SOURCE_OF_TRUTH = "response_items.jsonl"
NATIVE_SIDECAR_TRANSPORT_CHANGE = "sidecar-only"
MODEL_AUTHORED_STATE_KEYS = frozenset(
    {
        "active_work_todo",
        "frontier",
        "frontier_state",
        "frontier_state_update",
        "hard_runtime_frontier",
        "model_authored_frontier",
        "model_authored_proof",
        "model_authored_todo",
        "proof",
        "proof_state",
        "repair_history",
        "todo",
    }
)

_ITEM_HASH_KEYS = frozenset(
    {
        "schema_version",
        "sequence",
        "turn_id",
        "kind",
        "lane_attempt_id",
        "provider",
        "model",
        "response_id",
        "provider_item_id",
        "output_index",
        "call_id",
        "tool_name",
        "arguments_json_text",
        "custom_input_text",
        "output_text_or_ref",
        "status",
        "is_error",
        "encrypted_reasoning_ref",
        "metrics_ref",
        "content_refs",
        "evidence_refs",
        "sidecar_refs",
    }
)


def native_projection_transcript_hash(transcript: NativeTranscript | Mapping[str, object]) -> str:
    """Return the stable projection hash for a native transcript-like value."""

    if isinstance(transcript, NativeTranscript):
        return native_transcript_hash(transcript)
    payload = _transcript_projection_payload(transcript)
    return stable_json_hash(payload).removeprefix("sha256:")


def build_native_tool_result_index(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    tool_registry_ref: str = "",
    provider_tool_spec_hash: str = "",
) -> dict[str, object]:
    """Build a call-id keyed tool-result index from paired native output items."""

    context = _transcript_context(transcript)
    items = _normalized_items(transcript)
    calls = {
        _text(item.get("call_id")): item
        for item in items
        if _text(item.get("kind")) in CALL_ITEM_KINDS and _text(item.get("call_id"))
    }
    outputs = [item for item in items if _text(item.get("kind")) in OUTPUT_ITEM_KINDS]
    outputs.sort(key=_item_order)
    by_provider_call_id: dict[str, object] = {}
    ordered_refs: list[str] = []
    for index, output in enumerate(outputs, start=1):
        call_id = _text(output.get("call_id")) or f"output-{_text(output.get('sequence')) or index}"
        call = calls.get(call_id, {})
        tool_name = _text(output.get("tool_name") or call.get("tool_name") or output.get("kind"))
        result_ref = f"tool-result:{_safe_ref_part(call_id, f'output-{index}')}"
        ordered_refs.append(result_ref)
        by_provider_call_id[call_id] = {
            "ref": result_ref,
            "call_ref": f"native-call:{_safe_ref_part(call_id, f'call-{index}')}",
            "tool_ref": tool_ref_for_name(tool_name),
            "provider_call_id": call_id,
            "tool_name": tool_name,
            "status": _text(output.get("status") or "completed"),
            "is_error": bool(output.get("is_error")),
            "turn_id": _text(output.get("turn_id") or call.get("turn_id")),
            "call_sequence": _safe_int(call.get("sequence"), default=0),
            "output_sequence": _safe_int(output.get("sequence"), default=index),
            "call_kind": _text(call.get("kind")),
            "output_kind": _text(output.get("kind")),
            "arguments_hash": stable_json_hash(_text(call.get("arguments_json_text") or call.get("custom_input_text"))),
            "content_refs": _strings(output.get("content_refs")),
            "output_refs": _dedupe((*_strings(output.get("content_refs")), *_strings(output.get("sidecar_refs")))),
            "evidence_refs": _strings(output.get("evidence_refs")),
            "sidecar_refs": _strings(output.get("sidecar_refs")),
            "natural_result_text": _bounded_text(output.get("output_text_or_ref"), limit=1200),
        }
    payload = {
        "schema_version": NATIVE_TOOL_RESULT_INDEX_SCHEMA_VERSION,
        "index_kind": "native_transcript_tool_result_index",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "lane_attempt_id": context["lane_attempt_id"],
        "provider": context["provider"],
        "model": context["model"],
        "transcript_hash": context["transcript_hash"],
        "tool_registry_ref": tool_registry_ref,
        "provider_tool_spec_hash": provider_tool_spec_hash,
        "ordered_refs": ordered_refs,
        "by_provider_call_id": by_provider_call_id,
    }
    payload["index_hash"] = stable_json_hash(
        {
            "ordered_refs": ordered_refs,
            "by_provider_call_id": by_provider_call_id,
            "transcript_hash": context["transcript_hash"],
        }
    )
    return payload


def build_native_evidence_sidecar(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    task_contract: Mapping[str, object] | None = None,
    verifier_sidecar: Mapping[str, object] | None = None,
    tool_result_index: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build typed-evidence sidecar events from native paired output items."""

    context = _transcript_context(transcript)
    items = _normalized_items(transcript)
    index = dict(tool_result_index or build_native_tool_result_index(transcript))
    events: list[dict[str, object]] = []
    by_tool_result_ref: dict[str, list[str]] = {}
    known_output_refs: list[str] = []
    known_result_evidence_refs: list[str] = []
    known_mutation_refs: list[str] = []
    for output_index, output in enumerate(
        [item for item in items if _text(item.get("kind")) in OUTPUT_ITEM_KINDS],
        start=1,
    ):
        event = _generic_output_evidence_event(output, output_index=output_index, transcript_hash=context["transcript_hash"])
        events.append(event)
        event_ids = [_text(event.get("id"))]
        tool_result_ref = _text(event.get("provenance", {}).get("tool_result_ref") if isinstance(event.get("provenance"), dict) else "")
        for ref in _strings(output.get("content_refs")):
            _append_unique(known_output_refs, ref)
        for ref in _strings(output.get("sidecar_refs")):
            _append_unique(known_output_refs, ref)
        for ref in _strings(output.get("evidence_refs")):
            _append_unique(known_result_evidence_refs, ref)
        for mutation_event in _source_mutation_events_from_output(output, output_index=output_index, tool_result_ref=tool_result_ref):
            events.append(mutation_event)
            event_ids.append(_text(mutation_event.get("id")))
            for ref in mutation_event.get("refs") if isinstance(mutation_event.get("refs"), list) else []:
                if isinstance(ref, dict) and ref.get("kind") == "mutation_ref":
                    _append_unique(known_mutation_refs, _text(ref.get("id")))
        if tool_result_ref:
            by_tool_result_ref[tool_result_ref] = [event_id for event_id in event_ids if event_id]
    verifier_events = _verifier_events_from_sidecar(verifier_sidecar)
    events.extend(verifier_events)
    sidecar: dict[str, object] = {
        "schema_version": NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION,
        "sidecar_kind": "native_transcript_evidence_projection",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "lane_attempt_id": context["lane_attempt_id"],
        "provider": context["provider"],
        "model": context["model"],
        "transcript_hash": context["transcript_hash"],
        "tool_result_index_hash": _text(index.get("index_hash")),
        "task_contract_ref": _task_contract_ref(task_contract),
        "events": events,
        "event_count": len(events),
        "by_tool_result_ref": by_tool_result_ref,
        "known_output_refs": known_output_refs,
        "known_result_evidence_refs": known_result_evidence_refs,
        "known_mutation_refs": known_mutation_refs,
        "verifier_freshness": _verifier_freshness(events),
        "projection_authority": {
            "authoritative": False,
            "derived_from": [NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH, NATIVE_RESPONSE_ITEMS_SOURCE_OF_TRUTH],
            "model_authored_state_accepted": False,
        },
    }
    return _with_self_hash(sidecar, hash_field="sidecar_hash", ref_field="sidecar_ref", ref_prefix="native-evidence-sidecar")


def build_native_evidence_ref_index(evidence_sidecar: Mapping[str, object]) -> dict[str, object]:
    """Build compact evidence-ref lookup indexes from a native evidence sidecar."""

    events = [dict(event) for event in evidence_sidecar.get("events") if isinstance(event, dict)] if isinstance(evidence_sidecar.get("events"), list) else []
    by_evidence_ref: dict[str, object] = {}
    by_kind: dict[str, list[str]] = defaultdict(list)
    by_status: dict[str, list[str]] = defaultdict(list)
    by_provider_call_id: dict[str, list[str]] = defaultdict(list)
    by_path: dict[str, list[str]] = defaultdict(list)
    by_output_ref: dict[str, list[str]] = defaultdict(list)
    by_tool_ref: dict[str, list[str]] = defaultdict(list)
    by_mutation_ref: dict[str, list[str]] = defaultdict(list)
    by_result_evidence_ref: dict[str, list[str]] = defaultdict(list)
    aliases: dict[str, list[str]] = defaultdict(list)
    for event in events:
        event_id = _text(event.get("id"))
        if not event_id:
            continue
        observed = event.get("observed") if isinstance(event.get("observed"), dict) else {}
        by_evidence_ref[event_id] = {
            "kind": _text(event.get("kind")),
            "status": _text(event.get("status")),
            "provider_call_id": _text(event.get("provider_call_id")),
            "path": _text(observed.get("path")),
            "paths": _strings(observed.get("paths")),
            "refs": list(event.get("refs") or []) if isinstance(event.get("refs"), list) else [],
        }
        _append_unique(by_kind[_text(event.get("kind"))], event_id)
        _append_unique(by_status[_text(event.get("status"))], event_id)
        provider_call_id = _text(event.get("provider_call_id"))
        if provider_call_id:
            _append_unique(by_provider_call_id[provider_call_id], event_id)
            _append_unique(aliases[provider_call_id], event_id)
        for path in _observed_paths(observed):
            _append_unique(by_path[path], event_id)
            _append_unique(aliases[path], event_id)
        for ref in event.get("refs") if isinstance(event.get("refs"), list) else []:
            if not isinstance(ref, dict):
                continue
            ref_kind = _text(ref.get("kind"))
            ref_id = _text(ref.get("id") or ref.get("ref"))
            if not ref_id:
                continue
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
            else:
                _append_unique(aliases[ref_id], event_id)
        _append_unique(aliases[event_id], event_id)
    payload: dict[str, object] = {
        "schema_version": NATIVE_EVIDENCE_REF_INDEX_SCHEMA_VERSION,
        "index_kind": "native_transcript_evidence_ref_index",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "sidecar_ref": evidence_sidecar.get("sidecar_ref") or "",
        "sidecar_hash": evidence_sidecar.get("sidecar_hash") or "",
        "transcript_hash": evidence_sidecar.get("transcript_hash") or "",
        "hot_path_model_turn_search_allowed": False,
        "by_evidence_ref": by_evidence_ref,
        "by_kind": dict(by_kind),
        "by_status": dict(by_status),
        "by_provider_call_id": dict(by_provider_call_id),
        "by_path": dict(by_path),
        "by_output_ref": dict(by_output_ref),
        "by_tool_ref": dict(by_tool_ref),
        "by_mutation_ref": dict(by_mutation_ref),
        "by_result_evidence_ref": dict(by_result_evidence_ref),
        "aliases": dict(aliases),
        "unresolved_evidence_refs": _unresolved_evidence_refs(
            events,
            known_refs_by_kind={
                "evidence_event": set(by_evidence_ref),
                "tool_result_ref": set(evidence_sidecar.get("by_tool_result_ref") or {}),
                "output_ref": set(str(ref) for ref in evidence_sidecar.get("known_output_refs") or []),
                "mutation_ref": set(str(ref) for ref in evidence_sidecar.get("known_mutation_refs") or []),
                "evidence_ref": set(str(ref) for ref in evidence_sidecar.get("known_result_evidence_refs") or []),
            },
        ),
    }
    payload["index_hash"] = stable_json_hash({key: value for key, value in payload.items() if key != "index_hash"})
    return payload


def build_native_model_turn_index(transcript: NativeTranscript | Mapping[str, object]) -> dict[str, object]:
    """Build a debug/recovery-only model turn index from native transcript items."""

    context = _transcript_context(transcript)
    items = _normalized_items(transcript)
    turns_by_id: dict[str, list[dict[str, object]]] = defaultdict(list)
    for item in items:
        turns_by_id[_text(item.get("turn_id")) or "turn-unknown"].append(item)
    turns: list[dict[str, object]] = []
    by_turn: dict[str, object] = {}
    by_provider_call_id: dict[str, str] = {}
    for turn_number, turn_id in enumerate(sorted(turns_by_id, key=_turn_sort_key), start=1):
        turn_items = sorted(turns_by_id[turn_id], key=_item_order)
        call_ids = [_text(item.get("call_id")) for item in turn_items if _text(item.get("kind")) in CALL_ITEM_KINDS and _text(item.get("call_id"))]
        output_call_ids = [
            _text(item.get("call_id"))
            for item in turn_items
            if _text(item.get("kind")) in OUTPUT_ITEM_KINDS and _text(item.get("call_id"))
        ]
        response_ids = _dedupe(_text(item.get("response_id")) for item in turn_items if _text(item.get("response_id")))
        entry = {
            "turn": turn_number,
            "turn_id": turn_id,
            "sequence_start": _safe_int(turn_items[0].get("sequence"), default=0) if turn_items else 0,
            "sequence_end": _safe_int(turn_items[-1].get("sequence"), default=0) if turn_items else 0,
            "item_count": len(turn_items),
            "assistant_message_count": sum(1 for item in turn_items if _text(item.get("kind")) == "assistant_message"),
            "reasoning_count": sum(1 for item in turn_items if _text(item.get("kind")) == "reasoning"),
            "tool_call_count": len(call_ids),
            "tool_result_count": len(output_call_ids),
            "provider_call_ids": call_ids,
            "output_call_ids": output_call_ids,
            "response_ids": response_ids,
        }
        turns.append(entry)
        by_turn[turn_id] = entry
        for call_id in (*call_ids, *output_call_ids):
            by_provider_call_id[call_id] = turn_id
    payload: dict[str, object] = {
        "schema_version": NATIVE_MODEL_TURN_INDEX_SCHEMA_VERSION,
        "index_kind": "debug_recovery_only",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "transcript_hash": context["transcript_hash"],
        "hot_path_model_turn_search_allowed": False,
        "turns": turns,
        "by_turn": by_turn,
        "by_provider_call_id": by_provider_call_id,
    }
    payload["index_hash"] = stable_json_hash({key: value for key, value in payload.items() if key != "index_hash"})
    return payload


def build_compact_native_sidecar_digest(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    evidence_sidecar: Mapping[str, object] | None = None,
    tool_result_index: Mapping[str, object] | None = None,
    evidence_ref_index: Mapping[str, object] | None = None,
    model_turn_index: Mapping[str, object] | None = None,
    workframe_bundle: Mapping[str, object] | None = None,
    max_tool_results: int = 6,
) -> dict[str, object]:
    """Build compact sidecar context suitable for future provider requests."""

    context = _transcript_context(transcript)
    tool_index = dict(tool_result_index or build_native_tool_result_index(transcript))
    evidence = dict(evidence_sidecar or build_native_evidence_sidecar(transcript, tool_result_index=tool_index))
    evidence_index = dict(evidence_ref_index or build_native_evidence_ref_index(evidence))
    turn_index = dict(model_turn_index or build_native_model_turn_index(transcript))
    workframe = _workframe_digest(workframe_bundle)
    ordered_refs = [str(ref) for ref in tool_index.get("ordered_refs") or []]
    by_call = tool_index.get("by_provider_call_id") if isinstance(tool_index.get("by_provider_call_id"), dict) else {}
    latest_tool_results = [
        _compact_tool_result_for_digest(by_call.get(str(ref).removeprefix("tool-result:")), ref)
        for ref in ordered_refs[-max_tool_results:]
    ]
    payload: dict[str, object] = {
        "schema_version": NATIVE_COMPACT_SIDECAR_DIGEST_SCHEMA_VERSION,
        "digest_kind": "native_transcript_compact_sidecar_digest",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "transport_change": NATIVE_SIDECAR_TRANSPORT_CHANGE,
        "provider_input_authority": "transcript_window_plus_compact_sidecar_digest",
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "model_authored_state_accepted": False,
        "lane_attempt_id": context["lane_attempt_id"],
        "provider": context["provider"],
        "model": context["model"],
        "transcript_hash": context["transcript_hash"],
        "sidecar_hashes": {
            "tool_result_index": tool_index.get("index_hash") or "",
            "evidence_sidecar": evidence.get("sidecar_hash") or "",
            "evidence_ref_index": evidence_index.get("index_hash") or "",
            "model_turn_index": turn_index.get("index_hash") or "",
            "workframe": _text(workframe.get("output_hash")),
        },
        "counts": {
            "tool_results": len(ordered_refs),
            "evidence_events": int(evidence.get("event_count") or 0),
            "turns": len(turn_index.get("turns") or []),
        },
        "latest_tool_results": [item for item in latest_tool_results if item],
        "latest_evidence_refs": [str(ref) for ref in list((evidence_index.get("by_evidence_ref") or {}).keys())[-max_tool_results:]],
        "workframe": workframe,
        "provider_request_note": "Use with a native transcript window; this digest is not a standalone state object.",
    }
    payload = _strip_model_authored_state(payload)
    digest_hash = stable_json_hash(payload)
    payload["digest_hash"] = digest_hash
    payload["digest_text"] = _digest_text(payload)
    return payload


def build_native_updated_lane_state(
    transcript: NativeTranscript | Mapping[str, object],
    *,
    evidence_sidecar: Mapping[str, object] | None = None,
    verifier_sidecar: Mapping[str, object] | None = None,
    workframe_bundle: Mapping[str, object] | None = None,
    artifact_paths: Mapping[str, object] | None = None,
    proof_manifest_ref: str = "",
    active_work_todo_id: str = "",
) -> dict[str, object]:
    """Emit command-compatible lane state as a transcript-derived projection."""

    context = _transcript_context(transcript)
    evidence = dict(evidence_sidecar or build_native_evidence_sidecar(transcript, verifier_sidecar=verifier_sidecar))
    workframe = _workframe_digest(workframe_bundle)
    finish_status = _finish_status(transcript)
    active_work_todo = _derived_active_work_todo(
        lane_attempt_id=context["lane_attempt_id"],
        transcript_hash=context["transcript_hash"],
        evidence_sidecar_hash=_text(evidence.get("sidecar_hash")),
        workframe=workframe,
        active_work_todo_id=active_work_todo_id,
    )
    return {
        "schema_version": NATIVE_UPDATED_LANE_STATE_SCHEMA_VERSION,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "source_of_truth": NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH,
        "lane_attempt_id": context["lane_attempt_id"],
        "finish_status": finish_status,
        "proof_manifest": {
            "ref": proof_manifest_ref,
            "transcript_hash": context["transcript_hash"],
            "evidence_sidecar_hash": evidence.get("sidecar_hash") or "",
        },
        "artifact_paths": dict(artifact_paths or {}),
        "active_work_todo": active_work_todo,
        "derived_from": {
            "transcript_hash": context["transcript_hash"],
            "evidence_sidecar_hash": evidence.get("sidecar_hash") or "",
            "workframe_output_hash": workframe.get("output_hash") or "",
        },
    }


def stable_json_hash(value: object) -> str:
    """Return a stable sha256: hash for JSON-compatible values."""

    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def tool_ref_for_name(name: object) -> str:
    normalized = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(name or "").strip())
    return f"implement_v2_tool:{normalized or 'unknown'}:v1"


def _transcript_context(transcript: NativeTranscript | Mapping[str, object]) -> dict[str, str]:
    if isinstance(transcript, NativeTranscript):
        return {
            "lane_attempt_id": transcript.lane_attempt_id,
            "provider": transcript.provider,
            "model": transcript.model,
            "transcript_hash": native_transcript_hash(transcript),
        }
    return {
        "lane_attempt_id": _text(transcript.get("lane_attempt_id")),
        "provider": _text(transcript.get("provider")),
        "model": _text(transcript.get("model")),
        "transcript_hash": native_projection_transcript_hash(transcript),
    }


def _transcript_projection_payload(transcript: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": transcript.get("schema_version") or 1,
        "lane_attempt_id": _text(transcript.get("lane_attempt_id")),
        "provider": _text(transcript.get("provider")),
        "model": _text(transcript.get("model")),
        "items": [_item_hash_payload(item) for item in _normalized_items(transcript)],
    }


def _item_hash_payload(item: Mapping[str, object]) -> dict[str, object]:
    return {
        key: _strip_model_authored_state(value)
        for key, value in sorted(item.items())
        if key in _ITEM_HASH_KEYS and value not in ("", [], {}, None)
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
            item = _strip_model_authored_state(dict(raw_item))
        else:
            continue
        item.setdefault("sequence", index)
        items.append(item)
    items.sort(key=_item_order)
    return items


def _generic_output_evidence_event(output: Mapping[str, object], *, output_index: int, transcript_hash: str) -> dict[str, object]:
    call_id = _text(output.get("call_id")) or f"output-{output_index}"
    tool_name = _text(output.get("tool_name") or output.get("kind"))
    tool_result_ref = f"tool-result:{_safe_ref_part(call_id, f'output-{output_index}')}"
    refs = [
        {"kind": "tool_result_ref", "id": tool_result_ref},
        {"kind": "tool_ref", "id": tool_ref_for_name(tool_name)},
        {"kind": "native_transcript_item", "id": f"seq:{_text(output.get('sequence')) or output_index}"},
    ]
    refs.extend({"kind": "output_ref", "id": ref} for ref in _strings(output.get("content_refs")))
    refs.extend({"kind": "output_ref", "id": ref} for ref in _strings(output.get("sidecar_refs")))
    refs.extend({"kind": "evidence_ref", "id": ref} for ref in _strings(output.get("evidence_refs")))
    return {
        "schema_version": NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION,
        "id": f"ev:tool_result:{_safe_ref_part(call_id, f'output-{output_index}')}",
        "kind": "tool_result",
        "status": _event_status_from_output(output),
        "observed": {
            "tool_name": tool_name,
            "tool_status": _text(output.get("status") or "completed"),
            "native_transcript_kind": _text(output.get("kind")),
            "is_error": bool(output.get("is_error")),
            "content_refs": _strings(output.get("content_refs")),
            "evidence_refs": _strings(output.get("evidence_refs")),
            "sidecar_refs": _strings(output.get("sidecar_refs")),
            "summary": _bounded_text(output.get("output_text_or_ref"), limit=300),
        },
        "refs": refs,
        "provider_call_id": call_id,
        "tool_call_id": f"native:{call_id}",
        "transcript_item_sequence": _safe_int(output.get("sequence"), default=output_index),
        "transcript_hash": transcript_hash,
        "provenance": {"tool_result_ref": tool_result_ref, "tool_name": tool_name},
    }


def _source_mutation_events_from_output(
    output: Mapping[str, object],
    *,
    output_index: int,
    tool_result_ref: str,
) -> tuple[dict[str, object], ...]:
    events: list[dict[str, object]] = []
    call_id = _text(output.get("call_id")) or f"output-{output_index}"
    tool_name = _text(output.get("tool_name") or output.get("kind"))
    side_effects = output.get("side_effects") if isinstance(output.get("side_effects"), (list, tuple)) else ()
    mutation_refs = [ref for ref in _strings(output.get("evidence_refs")) if "mutation" in ref]
    for effect_index, effect in enumerate(side_effects, start=1):
        if not isinstance(effect, Mapping) or not _is_source_mutation_effect(effect):
            continue
        mutation_ref = _mutation_ref_for_effect(output, effect, effect_index=effect_index, tool_result_ref=tool_result_ref)
        events.append(_source_mutation_event(output, effect, mutation_ref=mutation_ref, tool_result_ref=tool_result_ref, effect_index=effect_index))
    if not events and mutation_refs:
        events.append(
            {
                "schema_version": NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION,
                "id": f"ev:source_mutation:{_stable_token(mutation_refs[0])}",
                "kind": "source_mutation",
                "status": _event_status_from_output(output),
                "observed": {
                    "path": _first_path_from_output(output),
                    "paths": _paths_from_output(output),
                    "operation": tool_name,
                },
                "refs": [
                    {"kind": "tool_result_ref", "id": tool_result_ref},
                    {"kind": "tool_ref", "id": tool_ref_for_name(tool_name)},
                    {"kind": "mutation_ref", "id": mutation_refs[0]},
                ],
                "provider_call_id": call_id,
                "tool_call_id": f"native:{call_id}",
            }
        )
    return tuple(events)


def _source_mutation_event(
    output: Mapping[str, object],
    effect: Mapping[str, object],
    *,
    mutation_ref: str,
    tool_result_ref: str,
    effect_index: int,
) -> dict[str, object]:
    record = effect.get("record") if isinstance(effect.get("record"), Mapping) else {}
    changes = record.get("changes") if isinstance(record.get("changes"), (list, tuple)) else ()
    changed_paths = [
        _text(change.get("path"))
        for change in changes
        if isinstance(change, Mapping) and _text(change.get("path"))
    ]
    path = _text(effect.get("path")) or (changed_paths[0] if changed_paths else "")
    call_id = _text(output.get("call_id")) or f"output-{effect_index}"
    tool_name = _text(output.get("tool_name") or output.get("kind"))
    return {
        "schema_version": NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION,
        "id": f"ev:source_mutation:{_stable_token(mutation_ref or path or str(effect_index))}",
        "kind": "source_mutation",
        "status": _event_status_from_output(output),
        "observed": {
            "path": path,
            "paths": changed_paths or ([path] if path else []),
            "operation": _text(effect.get("operation") or effect.get("kind") or tool_name),
            "written": bool(effect.get("written", True)),
            "changed_count": record.get("changed_count") or "",
        },
        "refs": [
            {"kind": "tool_result_ref", "id": tool_result_ref},
            {"kind": "tool_ref", "id": tool_ref_for_name(tool_name)},
            {"kind": "mutation_ref", "id": mutation_ref},
        ],
        "provider_call_id": call_id,
        "tool_call_id": f"native:{call_id}",
    }


def _verifier_events_from_sidecar(verifier_sidecar: Mapping[str, object] | None) -> list[dict[str, object]]:
    if not isinstance(verifier_sidecar, Mapping):
        return []
    raw_events = verifier_sidecar.get("events")
    if not isinstance(raw_events, (list, tuple)):
        return []
    events = []
    for index, event in enumerate(raw_events, start=1):
        if not isinstance(event, Mapping):
            continue
        payload = _strip_model_authored_state(dict(event))
        payload.setdefault("schema_version", NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION)
        payload.setdefault("id", f"ev:verifier:{index}")
        payload.setdefault("kind", "strict_verifier")
        payload.setdefault("status", "unknown")
        events.append(payload)
    return events


def _verifier_freshness(events: list[dict[str, object]]) -> dict[str, object]:
    verifier_events = [
        event
        for event in events
        if _text(event.get("kind")) in {"strict_verifier", "verifier", "run_tests", "verifier_result"}
    ]
    return {
        "schema_version": 1,
        "latest_event_ids": [_text(event.get("id")) for event in verifier_events[-12:] if _text(event.get("id"))],
        "failed_event_ids": [
            _text(event.get("id"))
            for event in verifier_events
            if _text(event.get("status")) in {"failed", "partial", "unknown", "invalid", "interrupted"}
        ],
    }


def _event_status_from_output(output: Mapping[str, object]) -> str:
    status = _text(output.get("status") or "completed").lower()
    if status in {"completed", "passed", "pass", "success"} and not output.get("is_error"):
        return "passed"
    if status in {"running", "yielded", "partial"}:
        return "partial"
    if status in {"failed", "denied", "invalid", "interrupted", "synthetic_error", "blocked"} or output.get("is_error"):
        return "failed"
    return "unknown"


def _is_source_mutation_effect(effect: Mapping[str, object]) -> bool:
    kind = _text(effect.get("kind"))
    if kind == "file_write":
        return effect.get("written") is True
    if kind == "source_tree_mutation":
        record = effect.get("record") if isinstance(effect.get("record"), Mapping) else {}
        return bool(record.get("changed_count"))
    return False


def _mutation_ref_for_effect(
    output: Mapping[str, object],
    effect: Mapping[str, object],
    *,
    effect_index: int,
    tool_result_ref: str,
) -> str:
    kind = _text(effect.get("kind"))
    if kind == "source_tree_mutation":
        record = effect.get("record") if isinstance(effect.get("record"), Mapping) else {}
        identifier = _text(record.get("command_run_id") or record.get("provider_call_id") or output.get("call_id"))
        if identifier:
            lane_attempt_id = _text(output.get("lane_attempt_id")) or "attempt"
            return f"implement-v2-evidence://{lane_attempt_id}/source_tree_mutation/{_safe_ref_part(identifier, 'source-tree-mutation')}"
    for ref in _strings(output.get("evidence_refs")):
        if "mutation" in ref:
            return ref
    return f"{tool_result_ref}:mutation:{effect_index}"


def _unresolved_evidence_refs(events: list[dict[str, object]], *, known_refs_by_kind: dict[str, set[str]]) -> list[dict[str, object]]:
    unresolved: list[dict[str, object]] = []
    for event in events:
        refs = event.get("refs") if isinstance(event.get("refs"), list) else []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_kind = _text(ref.get("kind"))
            if ref_kind not in known_refs_by_kind:
                continue
            ref_id = _text(ref.get("id") or ref.get("ref"))
            if ref_id and ref_id not in known_refs_by_kind[ref_kind]:
                unresolved.append({"event_id": event.get("id") or "", "missing_ref": ref_id})
    return unresolved


def _workframe_digest(workframe_bundle: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(workframe_bundle, Mapping):
        return {}
    output = workframe_bundle.get("reducer_output") if isinstance(workframe_bundle.get("reducer_output"), Mapping) else {}
    trace = output.get("trace") if isinstance(output.get("trace"), Mapping) else {}
    required_next = output.get("required_next") if isinstance(output.get("required_next"), Mapping) else {}
    finish_readiness = output.get("finish_readiness") if isinstance(output.get("finish_readiness"), Mapping) else {}
    return {
        "variant": _text(workframe_bundle.get("workframe_variant")),
        "current_phase": _text(output.get("current_phase")),
        "input_hash": _text(trace.get("input_hash")),
        "output_hash": _text(trace.get("output_hash")),
        "required_next_kind": _text(required_next.get("kind")),
        "required_next_evidence_refs": _strings(required_next.get("evidence_refs")),
        "finish_readiness_state": _text(finish_readiness.get("state")),
        "finish_required_evidence_refs": _strings(finish_readiness.get("required_evidence_refs")),
        "invariant_status": _text(
            (workframe_bundle.get("invariant_report") or {}).get("status")
            if isinstance(workframe_bundle.get("invariant_report"), Mapping)
            else ""
        ),
    }


def _compact_tool_result_for_digest(entry: object, ref: str) -> dict[str, object]:
    if not isinstance(entry, Mapping):
        return {}
    return {
        "ref": _text(entry.get("ref") or ref),
        "tool_name": _text(entry.get("tool_name")),
        "status": _text(entry.get("status")),
        "is_error": bool(entry.get("is_error")),
        "evidence_refs": _strings(entry.get("evidence_refs"))[:4],
        "output_refs": _strings(entry.get("output_refs"))[:4],
        "summary": _bounded_text(entry.get("natural_result_text"), limit=240),
    }


def _digest_text(payload: Mapping[str, object]) -> str:
    sidecar_hashes = payload.get("sidecar_hashes") if isinstance(payload.get("sidecar_hashes"), Mapping) else {}
    counts = payload.get("counts") if isinstance(payload.get("counts"), Mapping) else {}
    workframe = payload.get("workframe") if isinstance(payload.get("workframe"), Mapping) else {}
    parts = [
        f"native_sidecar_digest={payload.get('digest_hash')}",
        f"transcript_hash={payload.get('transcript_hash')}",
        f"tool_results={counts.get('tool_results', 0)}",
        f"evidence_events={counts.get('evidence_events', 0)}",
        f"workframe_phase={workframe.get('current_phase') or 'unknown'}",
        f"workframe_output_hash={workframe.get('output_hash') or ''}",
        f"evidence_sidecar_hash={sidecar_hashes.get('evidence_sidecar') or ''}",
    ]
    return "; ".join(part for part in parts if str(part).strip())


def _derived_active_work_todo(
    *,
    lane_attempt_id: str,
    transcript_hash: str,
    evidence_sidecar_hash: str,
    workframe: Mapping[str, object],
    active_work_todo_id: str = "",
) -> dict[str, object]:
    required_next_kind = _text(workframe.get("required_next_kind"))
    finish_state = _text(workframe.get("finish_readiness_state"))
    if finish_state == "ready":
        status = "finish_ready"
    elif required_next_kind:
        status = f"needs_{required_next_kind}"
    else:
        status = _text(workframe.get("current_phase")) or "unknown"
    refs = _dedupe(
        (
            *_strings(workframe.get("required_next_evidence_refs")),
            *_strings(workframe.get("finish_required_evidence_refs")),
        )
    )
    todo = {
        "status": status,
        "source": {
            "kind": "native_transcript_projection",
            "transcript_hash": transcript_hash,
            "evidence_sidecar_hash": evidence_sidecar_hash,
            "workframe_output_hash": _text(workframe.get("output_hash")),
        },
        "first_write_readiness": {
            "state": finish_state or "unknown",
            "current_phase": _text(workframe.get("current_phase")),
            "required_next": required_next_kind,
            "evidence_refs": refs,
            "derived_from": {
                "transcript_hash": transcript_hash,
                "evidence_sidecar_hash": evidence_sidecar_hash,
                "workframe_output_hash": _text(workframe.get("output_hash")),
            },
        },
    }
    # Readiness-only updates must merge into the current command/session todo
    # without inventing a second todo identity. A caller that already knows the
    # canonical command todo id may pass it explicitly for compatibility.
    if _text(active_work_todo_id):
        todo["id"] = _text(active_work_todo_id)
    return todo


def _finish_status(transcript: NativeTranscript | Mapping[str, object]) -> str:
    finish_outputs = [
        item for item in _normalized_items(transcript) if _text(item.get("kind")) == "finish_output"
    ]
    if finish_outputs:
        latest = max(finish_outputs, key=_item_order)
        return _text(latest.get("status") or "completed")
    finish_calls = [item for item in _normalized_items(transcript) if _text(item.get("kind")) == "finish_call"]
    return "pending" if finish_calls else "not_requested"


def _strip_model_authored_state(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_model_authored_state(item)
            for key, item in value.items()
            if str(key) not in MODEL_AUTHORED_STATE_KEYS
        }
    if isinstance(value, list):
        return [_strip_model_authored_state(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_model_authored_state(item) for item in value]
    return value


def _with_self_hash(payload: dict[str, object], *, hash_field: str, ref_field: str, ref_prefix: str) -> dict[str, object]:
    hashed = dict(payload)
    digest = stable_json_hash(hashed)
    hashed[hash_field] = digest
    hashed[ref_field] = f"{ref_prefix}:{digest.removeprefix('sha256:')[:16]}"
    return hashed


def _task_contract_ref(task_contract: Mapping[str, object] | None) -> str:
    if not isinstance(task_contract, Mapping) or not task_contract:
        return ""
    value = task_contract.get("id") or task_contract.get("task_id") or task_contract.get("objective") or task_contract
    return "task-contract:" + stable_json_hash(value).removeprefix("sha256:")[:16]


def _first_path_from_output(output: Mapping[str, object]) -> str:
    paths = _paths_from_output(output)
    return paths[0] if paths else ""


def _paths_from_output(output: Mapping[str, object]) -> list[str]:
    paths = output.get("paths")
    if isinstance(paths, (list, tuple)):
        return _dedupe(_text(path) for path in paths if _text(path))
    path = _text(output.get("path"))
    return [path] if path else []


def _observed_paths(observed: Mapping[str, object]) -> tuple[str, ...]:
    paths = observed.get("paths")
    if isinstance(paths, (list, tuple)):
        values = tuple(dict.fromkeys(_text(path) for path in paths if _text(path)))
        if values:
            return values
    path = _text(observed.get("path"))
    return (path,) if path else ()


def _item_order(item: Mapping[str, object]) -> tuple[int, int, str]:
    return (
        _safe_int(item.get("sequence"), default=0),
        _safe_int(item.get("output_index"), default=0),
        _text(item.get("provider_item_id") or item.get("call_id")),
    )


def _turn_sort_key(turn_id: str) -> tuple[int, str]:
    if turn_id.startswith("turn-"):
        return (_safe_int(turn_id.removeprefix("turn-"), default=0), turn_id)
    return (0, turn_id)


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


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


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


def _stable_token(value: object) -> str:
    return hashlib.sha256(_text(value).encode("utf-8")).hexdigest()[:16]


def _safe_ref_part(value: object, default: str) -> str:
    text = _text(value).strip() or default
    safe = []
    for char in text:
        if char.isalnum() or char in {"-", "_", "."}:
            safe.append(char)
        else:
            safe.append("-")
    return "".join(safe).strip("-") or default


__all__ = [
    "MODEL_AUTHORED_STATE_KEYS",
    "NATIVE_COMPACT_SIDECAR_DIGEST_SCHEMA_VERSION",
    "NATIVE_EVIDENCE_REF_INDEX_SCHEMA_VERSION",
    "NATIVE_EVIDENCE_SIDECAR_SCHEMA_VERSION",
    "NATIVE_MODEL_TURN_INDEX_SCHEMA_VERSION",
    "NATIVE_RESPONSE_ITEMS_SOURCE_OF_TRUTH",
    "NATIVE_SIDECAR_PROJECTION_SCHEMA_VERSION",
    "NATIVE_SIDECAR_TRANSPORT_CHANGE",
    "NATIVE_TOOL_RESULT_INDEX_SCHEMA_VERSION",
    "NATIVE_TRANSCRIPT_SOURCE_OF_TRUTH",
    "NATIVE_UPDATED_LANE_STATE_SCHEMA_VERSION",
    "build_compact_native_sidecar_digest",
    "build_native_evidence_ref_index",
    "build_native_evidence_sidecar",
    "build_native_model_turn_index",
    "build_native_tool_result_index",
    "build_native_updated_lane_state",
    "native_projection_transcript_hash",
    "stable_json_hash",
    "tool_ref_for_name",
]
