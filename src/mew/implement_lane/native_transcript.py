"""Provider-native transcript substrate for implement_v2.

This module is Phase 0-1 scaffolding for the native tool/function-calling
runtime.  It is intentionally not wired into the live runtime yet: the purpose
is to freeze transcript authority, pairing, artifact, and replay invariants
before adapter or CLI integration work starts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Iterable, Literal, Mapping

NATIVE_TRANSCRIPT_SCHEMA_VERSION = 1
NATIVE_TRANSCRIPT_ITEM_SCHEMA_VERSION = 1
NATIVE_TRANSCRIPT_ARTIFACT_CONTRACT_VERSION = 1
IMPLEMENT_V2_NATIVE_RUNTIME_ID = "implement_v2_native_transcript_loop"
LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID = "implement_v2_model_json_tool_loop"

NativeTranscriptItemKind = Literal[
    "input_message",
    "assistant_message",
    "reasoning",
    "function_call",
    "custom_tool_call",
    "function_call_output",
    "custom_tool_call_output",
    "finish_call",
    "finish_output",
]

NativeTranscriptOutputStatus = Literal[
    "completed",
    "failed",
    "denied",
    "invalid",
    "interrupted",
    "synthetic_error",
    "blocked",
]

CALL_ITEM_KINDS = frozenset({"function_call", "custom_tool_call", "finish_call"})
OUTPUT_ITEM_KINDS = frozenset({"function_call_output", "custom_tool_call_output", "finish_output"})
NON_TOOL_ITEM_KINDS = frozenset({"input_message", "assistant_message", "reasoning"})
WRITE_LIKE_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})
LARGE_NATIVE_FUNCTION_CALL_ARGUMENT_CHARS = 16_000

AUTHORITATIVE_NATIVE_TRANSCRIPT_FILES = (
    "response_transcript.json",
    "response_items.jsonl",
)
DERIVED_NATIVE_TRANSCRIPT_FILES = (
    "transcript_window.jsonl",
    "request_descriptor.json",
    "provider_requests.jsonl",
    "provider_events.jsonl",
    "reasoning_sidecar.json",
    "native_turn_observation.json",
    "native-evidence-observation.json",
    "call_result_pairing.json",
    "transcript_metrics.json",
    "proof-manifest.json",
)


@dataclass(frozen=True)
class NativeTranscriptItem:
    """One normalized provider-native transcript item.

    The item is the durable authority for provider chronology.  Large/raw
    provider payloads should be stored behind refs; hashes include refs and
    content hashes, not raw encrypted reasoning blob bytes.
    """

    sequence: int
    turn_id: str
    kind: NativeTranscriptItemKind
    lane_attempt_id: str = ""
    provider: str = ""
    model: str = ""
    response_id: str = ""
    provider_item_id: str = ""
    output_index: int = 0
    call_id: str = ""
    tool_name: str = ""
    arguments_json_text: str = ""
    custom_input_text: str = ""
    output_text_or_ref: str = ""
    status: str = ""
    is_error: bool = False
    raw_ref: str = ""
    encrypted_reasoning_ref: str = ""
    metrics_ref: str = ""
    content_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    sidecar_refs: tuple[str, ...] = ()
    schema_version: int = field(default=NATIVE_TRANSCRIPT_ITEM_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        payload = {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "turn_id": self.turn_id,
            "kind": self.kind,
            "lane_attempt_id": self.lane_attempt_id,
            "provider": self.provider,
            "model": self.model,
            "response_id": self.response_id,
            "provider_item_id": self.provider_item_id,
            "output_index": self.output_index,
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "arguments_json_text": self.arguments_json_text,
            "custom_input_text": self.custom_input_text,
            "output_text_or_ref": self.output_text_or_ref,
            "status": self.status,
            "is_error": self.is_error,
            "raw_ref": self.raw_ref,
            "encrypted_reasoning_ref": self.encrypted_reasoning_ref,
            "metrics_ref": self.metrics_ref,
            "content_refs": list(self.content_refs),
            "evidence_refs": list(self.evidence_refs),
            "sidecar_refs": list(self.sidecar_refs),
        }
        return {key: value for key, value in payload.items() if value not in ("", [], {}, None)}

    def hash_dict(self) -> dict[str, object]:
        """Return the deterministic hash preimage for this item."""

        payload = self.as_dict()
        payload.pop("raw_ref", None)
        # encrypted_reasoning_ref and sidecar refs remain in the hash preimage;
        # encrypted blob bytes never live in the item itself.
        return payload


@dataclass(frozen=True)
class NativeTranscript:
    """Authoritative transcript for an implement_v2 native lane attempt."""

    lane_attempt_id: str
    provider: str
    model: str
    items: tuple[NativeTranscriptItem, ...] = ()
    schema_version: int = field(default=NATIVE_TRANSCRIPT_SCHEMA_VERSION, init=False)

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "lane_attempt_id": self.lane_attempt_id,
            "provider": self.provider,
            "model": self.model,
            "items": [item.as_dict() for item in self.items],
            "indexes": native_transcript_indexes(self),
            "hash": native_transcript_hash(self),
        }

    def with_items(self, items: Iterable[NativeTranscriptItem]) -> "NativeTranscript":
        return NativeTranscript(
            lane_attempt_id=self.lane_attempt_id,
            provider=self.provider,
            model=self.model,
            items=tuple(items),
        )


@dataclass(frozen=True)
class NativeTranscriptValidationResult:
    """Validation result for native transcript invariants."""

    valid: bool
    errors: tuple[str, ...] = ()
    call_count: int = 0
    output_count: int = 0
    non_tool_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "call_count": self.call_count,
            "output_count": self.output_count,
            "non_tool_count": self.non_tool_count,
        }


def native_artifact_contract() -> dict[str, object]:
    """Return the Phase 0 artifact contract for native implement_v2."""

    return {
        "schema_version": NATIVE_TRANSCRIPT_ARTIFACT_CONTRACT_VERSION,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "authoritative_files": list(AUTHORITATIVE_NATIVE_TRANSCRIPT_FILES),
        "derived_files": list(DERIVED_NATIVE_TRANSCRIPT_FILES),
        "source_of_truth": "response_transcript.json",
        "forbidden_main_path_runtime_id": LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID,
        "sidecars_are_derived": True,
        "model_json_main_path_allowed": False,
    }


def validate_native_transcript_pairing(transcript: NativeTranscript | Iterable[NativeTranscriptItem]) -> NativeTranscriptValidationResult:
    """Validate one-call-one-output pairing and transcript chronology."""

    items = transcript.items if isinstance(transcript, NativeTranscript) else tuple(transcript)
    errors: list[str] = []
    calls_by_id: dict[str, NativeTranscriptItem] = {}
    outputs_by_id: dict[str, NativeTranscriptItem] = {}
    seen_sequences: set[int] = set()
    call_count = 0
    output_count = 0
    non_tool_count = 0
    previous_sequence: int | None = None

    for item in items:
        if previous_sequence is not None and item.sequence <= previous_sequence:
            errors.append(f"non_monotonic_sequence:{previous_sequence}->{item.sequence}")
        previous_sequence = item.sequence
        if item.sequence in seen_sequences:
            errors.append(f"duplicate_sequence:{item.sequence}")
        seen_sequences.add(item.sequence)
        if item.kind in NON_TOOL_ITEM_KINDS:
            non_tool_count += 1
            if item.call_id:
                errors.append(f"non_tool_item_has_call_id:{item.sequence}:{item.call_id}")
            continue
        if item.kind in CALL_ITEM_KINDS:
            call_count += 1
            if not item.call_id:
                errors.append(f"call_missing_call_id:{item.sequence}:{item.kind}")
                continue
            if item.call_id in calls_by_id:
                errors.append(f"duplicate_call_id:{item.call_id}")
            else:
                calls_by_id[item.call_id] = item
            continue
        if item.kind in OUTPUT_ITEM_KINDS:
            output_count += 1
            if not item.call_id:
                errors.append(f"output_missing_call_id:{item.sequence}:{item.kind}")
                continue
            if item.call_id in outputs_by_id:
                errors.append(f"duplicate_output_for_call_id:{item.call_id}")
            else:
                outputs_by_id[item.call_id] = item
            if item.status in {"failed", "denied", "invalid", "interrupted", "synthetic_error", "blocked"} and not item.is_error:
                errors.append(f"error_status_without_is_error:{item.call_id}:{item.status}")
            continue
        errors.append(f"unknown_item_kind:{item.sequence}:{item.kind}")

    for call_id, call in calls_by_id.items():
        output = outputs_by_id.get(call_id)
        if output is None:
            errors.append(f"missing_output_for_call_id:{call_id}")
            continue
        if not _call_output_kinds_match(call.kind, output.kind):
            errors.append(f"call_output_kind_mismatch:{call_id}:{call.kind}:{output.kind}")
        if output.tool_name and call.tool_name and output.tool_name != call.tool_name:
            errors.append(f"tool_name_mismatch:{call_id}:{call.tool_name}:{output.tool_name}")
        if output.sequence < call.sequence:
            errors.append(f"output_before_call:{call_id}")

    for call_id in outputs_by_id:
        if call_id not in calls_by_id:
            errors.append(f"orphan_output_for_call_id:{call_id}")

    return NativeTranscriptValidationResult(
        valid=not errors,
        errors=tuple(errors),
        call_count=call_count,
        output_count=output_count,
        non_tool_count=non_tool_count,
    )


def build_synthetic_error_output(
    call: NativeTranscriptItem,
    *,
    sequence: int,
    status: NativeTranscriptOutputStatus = "synthetic_error",
    reason: str,
) -> NativeTranscriptItem:
    """Build a paired synthetic error output for a rejected native call."""

    if call.kind not in CALL_ITEM_KINDS:
        raise ValueError(f"cannot build synthetic output for non-call item: {call.kind}")
    if call.kind == "custom_tool_call":
        output_kind: NativeTranscriptItemKind = "custom_tool_call_output"
    elif call.kind == "finish_call":
        output_kind = "finish_output"
    else:
        output_kind = "function_call_output"
    return NativeTranscriptItem(
        sequence=sequence,
        turn_id=call.turn_id,
        lane_attempt_id=call.lane_attempt_id,
        provider=call.provider,
        response_id=call.response_id,
        provider_item_id=f"synthetic-output-for-{call.provider_item_id or call.call_id}",
        output_index=call.output_index,
        kind=output_kind,
        call_id=call.call_id,
        tool_name=call.tool_name,
        output_text_or_ref=reason,
        status=status,
        is_error=True,
    )


def native_transcript_hash(transcript: NativeTranscript) -> str:
    """Return a stable hash for the authoritative transcript."""

    preimage = {
        "schema_version": transcript.schema_version,
        "lane_attempt_id": transcript.lane_attempt_id,
        "provider": transcript.provider,
        "model": transcript.model,
        "items": [item.hash_dict() for item in transcript.items],
    }
    return hashlib.sha256(_canonical_json(preimage).encode("utf-8")).hexdigest()


def native_transcript_indexes(transcript: NativeTranscript) -> dict[str, object]:
    """Build compact indexes used by proof and replay artifacts."""

    calls = [item for item in transcript.items if item.kind in CALL_ITEM_KINDS]
    outputs = [item for item in transcript.items if item.kind in OUTPUT_ITEM_KINDS]
    return {
        "call_ids": [item.call_id for item in calls if item.call_id],
        "output_call_ids": [item.call_id for item in outputs if item.call_id],
        "items_by_kind": _count_by_kind(transcript.items),
        "call_count": len(calls),
        "output_count": len(outputs),
        "non_tool_count": sum(1 for item in transcript.items if item.kind in NON_TOOL_ITEM_KINDS),
    }


def native_proof_manifest_from_transcript(transcript: NativeTranscript) -> dict[str, object]:
    """Build the Phase 1 derived proof manifest from a native transcript."""

    validation = validate_native_transcript_pairing(transcript)
    return {
        "schema_version": 1,
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "lane_attempt_id": transcript.lane_attempt_id,
        "provider": transcript.provider,
        "model": transcript.model,
        "transcript_hash": native_transcript_hash(transcript),
        "pairing": validation.as_dict(),
        "metrics": native_transcript_metrics(transcript),
    }


def native_transcript_metrics(transcript: NativeTranscript) -> dict[str, object]:
    validation = validate_native_transcript_pairing(transcript)
    return {
        "transport_kind": "provider_native",
        "provider_native_tool_loop": True,
        "model_json_main_path_detected": False,
        "item_count": len(transcript.items),
        "call_count": validation.call_count,
        "output_count": validation.output_count,
        "non_tool_count": validation.non_tool_count,
        "pairing_valid": validation.valid,
        "pairing_error_count": len(validation.errors),
        "function_call_arguments": native_function_call_argument_metrics(transcript),
    }


def native_function_call_argument_metrics(transcript: NativeTranscript) -> dict[str, object]:
    """Summarize function-call argument size from the authoritative transcript.

    Native tool loops can spend most wall time generating a huge tool-call JSON
    payload rather than executing the tool.  These metrics make that visible in
    proof artifacts without treating it as a verifier failure.
    """

    calls = tuple(item for item in transcript.items if item.kind in CALL_ITEM_KINDS)
    call_summaries: list[dict[str, object]] = []
    write_summaries: list[dict[str, object]] = []
    total_chars = 0
    large_calls: list[dict[str, object]] = []

    for item in calls:
        arg_text = item.arguments_json_text or item.custom_input_text or ""
        arg_chars = len(arg_text)
        total_chars += arg_chars
        summary = {
            "turn_id": item.turn_id,
            "sequence": item.sequence,
            "call_id": item.call_id,
            "tool_name": item.tool_name,
            "argument_chars": arg_chars,
            **_native_write_argument_shape(item, arg_text),
        }
        call_summaries.append(summary)
        if item.tool_name in WRITE_LIKE_TOOL_NAMES:
            write_summaries.append(summary)
        if arg_chars >= LARGE_NATIVE_FUNCTION_CALL_ARGUMENT_CHARS:
            large_calls.append(summary)

    max_call = max(call_summaries, key=lambda row: int(row.get("argument_chars") or 0), default={})
    max_write = max(write_summaries, key=lambda row: int(row.get("argument_chars") or 0), default={})
    first_write = write_summaries[0] if write_summaries else {}
    return {
        "large_argument_threshold_chars": LARGE_NATIVE_FUNCTION_CALL_ARGUMENT_CHARS,
        "total_argument_chars": total_chars,
        "max_argument_chars": int(max_call.get("argument_chars") or 0),
        "max_argument_call": max_call,
        "large_argument_count": len(large_calls),
        "large_arguments": large_calls[:10],
        "write_call_count": len(write_summaries),
        "max_write_argument_chars": int(max_write.get("argument_chars") or 0),
        "max_write_call": max_write,
        "first_write_argument_chars": int(first_write.get("argument_chars") or 0),
        "first_write_call": first_write,
        "large_write_argument_count": sum(
            1 for row in write_summaries if int(row.get("argument_chars") or 0) >= LARGE_NATIVE_FUNCTION_CALL_ARGUMENT_CHARS
        ),
        "large_write_generation_suspected": any(
            int(row.get("argument_chars") or 0) >= LARGE_NATIVE_FUNCTION_CALL_ARGUMENT_CHARS for row in write_summaries
        ),
    }


def _native_write_argument_shape(item: NativeTranscriptItem, arg_text: str) -> dict[str, object]:
    if item.tool_name not in WRITE_LIKE_TOOL_NAMES:
        return {}
    shape: dict[str, object] = {
        "path": "",
        "content_chars": 0,
        "content_lines_count": 0,
        "old_string_chars": 0,
        "new_string_chars": 0,
    }
    try:
        payload = json.loads(arg_text) if arg_text else {}
    except json.JSONDecodeError:
        return {**shape, "argument_json_valid": False}
    if not isinstance(payload, Mapping):
        return {**shape, "argument_json_valid": False}
    content = payload.get("content")
    content_lines = payload.get("content_lines")
    old_string = payload.get("old_string")
    new_string = payload.get("new_string")
    return {
        **shape,
        "argument_json_valid": True,
        "path": str(payload.get("path") or ""),
        "content_chars": len(content) if isinstance(content, str) else 0,
        "content_lines_count": len(content_lines) if isinstance(content_lines, list) else 0,
        "old_string_chars": len(old_string) if isinstance(old_string, str) else 0,
        "new_string_chars": len(new_string) if isinstance(new_string, str) else 0,
    }


def native_transcript_sidecar_events(transcript: NativeTranscript) -> tuple[dict[str, object], ...]:
    """Project native output items into WorkFrame-compatible sidecar events."""

    events: list[dict[str, object]] = []
    for item in transcript.items:
        if item.kind not in OUTPUT_ITEM_KINDS:
            continue
        evidence_refs = tuple(dict.fromkeys((*item.evidence_refs, *item.content_refs, *item.sidecar_refs)))
        event: dict[str, object] = {
            "event_sequence": item.sequence,
            "event_id": f"native-output:{item.call_id or item.sequence}",
            "kind": item.tool_name or item.kind,
            "native_transcript_kind": item.kind,
            "status": item.status or "completed",
            "tool_name": item.tool_name,
            "provider_call_id": item.call_id,
            "transcript_item_sequence": item.sequence,
            "transcript_hash": native_transcript_hash(transcript),
            "evidence_refs": list(evidence_refs),
            "content_refs": list(item.content_refs),
            "sidecar_refs": list(item.sidecar_refs),
        }
        if item.output_text_or_ref:
            event["summary"] = item.output_text_or_ref
            event["observable_output"] = True
        if item.is_error:
            event["is_error"] = True
            event["family"] = item.status or "tool_error"
        events.append(event)
    return tuple(events)


def build_native_evidence_observation(
    transcript: NativeTranscript,
    *,
    resolver_decisions: Iterable[Mapping[str, object] | object] = (),
) -> dict[str, object]:
    """Build a debugger-facing evidence observation from native artifacts.

    The authoritative data remains ``response_transcript.json``.  This derived
    artifact intentionally excludes finish output echoes from the known evidence
    index, so a finish claim only counts as resolved when it cites evidence
    produced by a previous tool result.
    """

    known_by_ref: dict[str, list[dict[str, object]]] = {}
    finish_output_by_call: dict[str, NativeTranscriptItem] = {}
    finish_claims: list[dict[str, object]] = []
    decision_by_finish_call = {
        _text(decision.get("finish_call_id") if isinstance(decision, Mapping) else getattr(decision, "finish_call_id", "")): _decision_dict(decision)
        for decision in resolver_decisions
    }

    for item in transcript.items:
        if item.kind == "finish_output" and item.call_id:
            finish_output_by_call[item.call_id] = item

    for item in transcript.items:
        if item.kind in OUTPUT_ITEM_KINDS and item.kind != "finish_output":
            for ref in item.evidence_refs:
                ref_text = _text(ref).strip()
                if not ref_text:
                    continue
                known_by_ref.setdefault(ref_text, []).append(_evidence_origin(item))
            continue
        if item.kind != "finish_call":
            continue
        args = _json_object(item.arguments_json_text)
        cited_refs = _strings(args.get("evidence_refs") or args.get("evidence_ref"))
        output = finish_output_by_call.get(item.call_id)
        resolver_decision = decision_by_finish_call.get(item.call_id, {})
        prior_known_by_ref = {ref: list(origins) for ref, origins in known_by_ref.items()}
        unresolved_refs = tuple(ref for ref in cited_refs if ref not in known_by_ref)
        finish_claims.append(
            {
                "turn_id": item.turn_id,
                "finish_call_id": item.call_id,
                "outcome": _text(args.get("outcome") or args.get("final_status") or args.get("status")),
                "summary": _bounded(_text(args.get("summary")), limit=600),
                "cited_evidence_refs": list(cited_refs),
                "resolved_cited_evidence_refs": [ref for ref in cited_refs if ref in known_by_ref],
                "unresolved_cited_evidence_refs": list(unresolved_refs),
                "known_tool_evidence_ref_count_before_finish": len(prior_known_by_ref),
                "finish_output_status": output.status if output else "",
                "finish_output_is_error": bool(output.is_error) if output else False,
                "finish_output_evidence_refs": list(output.evidence_refs) if output else [],
                "resolver_decision": resolver_decision,
                "resolver_blockers": list(resolver_decision.get("blockers") or [])
                if isinstance(resolver_decision.get("blockers"), list)
                else [],
                "resolver_missing_obligations": list(resolver_decision.get("missing_obligations") or [])
                if isinstance(resolver_decision.get("missing_obligations"), list)
                else [],
            }
        )

    unresolved_count = sum(len(claim["unresolved_cited_evidence_refs"]) for claim in finish_claims)
    cited_count = sum(len(claim["cited_evidence_refs"]) for claim in finish_claims)
    resolver_rows = tuple(_decision_dict(decision) for decision in resolver_decisions)
    summary = {
        "finish_claim_count": len(finish_claims),
        "known_tool_evidence_ref_count": len(known_by_ref),
        "cited_evidence_ref_count": cited_count,
        "resolved_cited_evidence_ref_count": cited_count - unresolved_count,
        "unresolved_cited_evidence_ref_count": unresolved_count,
        "resolver_decision_count": len(resolver_rows),
        "resolver_block_count": sum(1 for row in resolver_rows if _text(row.get("result")) == "block"),
        "resolver_allow_count": sum(1 for row in resolver_rows if _text(row.get("result")) == "allow"),
    }
    return {
        "schema_version": 1,
        "observation_kind": "native_evidence_observation",
        "runtime_id": IMPLEMENT_V2_NATIVE_RUNTIME_ID,
        "transport_kind": "provider_native",
        "source_of_truth": "response_transcript.json",
        "lane_attempt_id": transcript.lane_attempt_id,
        "provider": transcript.provider,
        "model": transcript.model,
        "transcript_hash": native_transcript_hash(transcript),
        "summary": summary,
        "finish_claims": finish_claims,
        "known_tool_evidence_refs": {
            ref: origins for ref, origins in sorted(known_by_ref.items(), key=lambda item: item[0])
        },
        "resolver_decisions": list(resolver_rows),
    }


def write_native_evidence_observation(
    root: Path | str,
    transcript: NativeTranscript,
    *,
    resolver_decisions: Iterable[Mapping[str, object] | object] = (),
    proof_manifest_path: str | Path | None = None,
) -> dict[str, Path]:
    """Write native evidence observation and mirror its summary into manifest."""

    artifact_root = Path(root)
    path = artifact_root / "native-evidence-observation.json"
    payload = build_native_evidence_observation(transcript, resolver_decisions=resolver_decisions)
    _write_json(path, payload)
    if proof_manifest_path is not None:
        _patch_manifest_with_native_evidence_observation(
            Path(proof_manifest_path),
            observation_path=path,
            payload=payload,
        )
    return {"native_evidence_observation": path}


def write_native_transcript_artifacts(root: Path | str, transcript: NativeTranscript) -> dict[str, Path]:
    """Write authoritative and Phase 1 derived native transcript artifacts."""

    artifact_root = Path(root)
    artifact_root.mkdir(parents=True, exist_ok=True)
    validation = validate_native_transcript_pairing(transcript)
    if not validation.valid:
        raise ValueError(f"invalid native transcript: {', '.join(validation.errors)}")
    transcript_path = artifact_root / "response_transcript.json"
    items_path = artifact_root / "response_items.jsonl"
    pairing_path = artifact_root / "call_result_pairing.json"
    metrics_path = artifact_root / "transcript_metrics.json"
    manifest_path = artifact_root / "proof-manifest.json"

    _write_json(transcript_path, transcript.as_dict())
    _write_jsonl(items_path, [item.as_dict() for item in transcript.items])
    _write_json(pairing_path, validation.as_dict())
    _write_json(metrics_path, native_transcript_metrics(transcript))
    _write_json(manifest_path, native_proof_manifest_from_transcript(transcript))
    return {
        "response_transcript": transcript_path,
        "response_items": items_path,
        "call_result_pairing": pairing_path,
        "transcript_metrics": metrics_path,
        "proof_manifest": manifest_path,
    }


def normalize_codex_response_items(
    response_items: Iterable[Mapping[str, object]],
    *,
    lane_attempt_id: str,
    provider: str = "codex",
    model: str = "",
    turn_id: str = "turn-1",
) -> NativeTranscript:
    """Normalize Codex/OpenAI Responses items into NativeTranscript."""

    normalized: list[NativeTranscriptItem] = []
    for index, raw in enumerate(response_items, 1):
        item_type = _text(raw.get("type") or raw.get("kind"))
        name = _text(raw.get("name"))
        call_id = _text(raw.get("call_id"))
        provider_item_id = _text(raw.get("id") or raw.get("item_id"))
        if item_type in {"function_call", "response.function_call"} or raw.get("arguments") is not None:
            kind: NativeTranscriptItemKind = "finish_call" if name == "finish" else "function_call"
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    response_id=_text(raw.get("response_id")),
                    provider_item_id=provider_item_id,
                    output_index=_int(raw.get("output_index"), default=index - 1),
                    kind=kind,
                    call_id=call_id,
                    tool_name=name,
                    arguments_json_text=_json_text(raw.get("arguments")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if item_type in {"custom_tool_call", "custom_call"}:
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    response_id=_text(raw.get("response_id")),
                    provider_item_id=provider_item_id,
                    output_index=_int(raw.get("output_index"), default=index - 1),
                    kind="custom_tool_call",
                    call_id=call_id,
                    tool_name=name,
                    custom_input_text=_text(raw.get("input") or raw.get("content")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if item_type in {"custom_tool_call_output", "custom_output"}:
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    response_id=_text(raw.get("response_id")),
                    provider_item_id=provider_item_id,
                    output_index=_int(raw.get("output_index"), default=index - 1),
                    kind="custom_tool_call_output",
                    call_id=call_id,
                    tool_name=name,
                    output_text_or_ref=_text(raw.get("output") or raw.get("content")),
                    status=_text(raw.get("status") or "completed"),
                    is_error=bool(raw.get("is_error")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if item_type in {"function_call_output", "tool_output"} or raw.get("output") is not None:
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    response_id=_text(raw.get("response_id")),
                    provider_item_id=provider_item_id,
                    output_index=_int(raw.get("output_index"), default=index - 1),
                    kind="finish_output" if name == "finish" else "function_call_output",
                    call_id=call_id,
                    tool_name=name,
                    output_text_or_ref=_text(raw.get("output") or raw.get("content")),
                    status=_text(raw.get("status") or "completed"),
                    is_error=bool(raw.get("is_error")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if item_type == "reasoning":
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    response_id=_text(raw.get("response_id")),
                    provider_item_id=_text(raw.get("id") or raw.get("item_id")),
                    output_index=_int(raw.get("output_index"), default=index - 1),
                    kind="reasoning",
                    output_text_or_ref=_text(raw.get("summary") or raw.get("content")),
                    encrypted_reasoning_ref=_text(raw.get("encrypted_reasoning_ref")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        role = _text(raw.get("role"))
        normalized.append(
            NativeTranscriptItem(
                sequence=index,
                turn_id=turn_id,
                lane_attempt_id=lane_attempt_id,
                provider=provider,
                model=model,
                response_id=_text(raw.get("response_id")),
                provider_item_id=_text(raw.get("id") or raw.get("item_id")),
                output_index=_int(raw.get("output_index"), default=index - 1),
                kind="input_message" if role == "user" else "assistant_message",
                output_text_or_ref=_text(raw.get("text") or raw.get("content")),
                raw_ref=_text(raw.get("raw_ref")),
            )
        )
    return NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        items=tuple(normalized),
    )


def normalize_claude_tool_events(
    events: Iterable[Mapping[str, object]],
    *,
    lane_attempt_id: str,
    provider: str = "claude",
    model: str = "",
    turn_id: str = "turn-1",
) -> NativeTranscript:
    """Normalize Claude content-block tool_use/tool_result events."""

    normalized: list[NativeTranscriptItem] = []
    for index, raw in enumerate(events, 1):
        event_type = _text(raw.get("type") or raw.get("kind"))
        if event_type == "tool_use":
            name = _text(raw.get("name"))
            call_id = _text(raw.get("id") or raw.get("tool_use_id") or raw.get("call_id"))
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    provider_item_id=call_id,
                    output_index=index - 1,
                    kind="finish_call" if name == "finish" else "function_call",
                    call_id=call_id,
                    tool_name=name,
                    arguments_json_text=_json_text(raw.get("input")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if event_type == "tool_result":
            name = _text(raw.get("name"))
            call_id = _text(raw.get("tool_use_id") or raw.get("call_id"))
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    provider_item_id=_text(raw.get("id") or raw.get("item_id")),
                    output_index=index - 1,
                    kind="finish_output" if name == "finish" else "function_call_output",
                    call_id=call_id,
                    tool_name=name,
                    output_text_or_ref=_text(raw.get("content")),
                    status="completed" if not raw.get("is_error") else "failed",
                    is_error=bool(raw.get("is_error")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        if event_type == "thinking":
            normalized.append(
                NativeTranscriptItem(
                    sequence=index,
                    turn_id=turn_id,
                    lane_attempt_id=lane_attempt_id,
                    provider=provider,
                    model=model,
                    provider_item_id=_text(raw.get("id")),
                    output_index=index - 1,
                    kind="reasoning",
                    output_text_or_ref=_text(raw.get("content") or raw.get("text")),
                    raw_ref=_text(raw.get("raw_ref")),
                )
            )
            continue
        normalized.append(
            NativeTranscriptItem(
                sequence=index,
                turn_id=turn_id,
                lane_attempt_id=lane_attempt_id,
                provider=provider,
                model=model,
                provider_item_id=_text(raw.get("id")),
                output_index=index - 1,
                kind="assistant_message",
                output_text_or_ref=_text(raw.get("content") or raw.get("text")),
                raw_ref=_text(raw.get("raw_ref")),
            )
        )
    return NativeTranscript(
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        items=tuple(normalized),
    )


def _call_output_kinds_match(call_kind: str, output_kind: str) -> bool:
    return (
        (call_kind == "function_call" and output_kind == "function_call_output")
        or (call_kind == "custom_tool_call" and output_kind == "custom_tool_call_output")
        or (call_kind == "finish_call" and output_kind == "finish_output")
    )


def _count_by_kind(items: Iterable[NativeTranscriptItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.kind] = counts.get(item.kind, 0) + 1
    return dict(sorted(counts.items()))


def _write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, records: Iterable[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(record, ensure_ascii=False, sort_keys=True) for record in records]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _patch_manifest_with_native_evidence_observation(
    manifest_path: Path,
    *,
    observation_path: Path,
    payload: Mapping[str, object],
) -> None:
    manifest: dict[str, object] = {}
    if manifest_path.exists():
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            manifest = loaded
    metrics = manifest.get("metrics") if isinstance(manifest.get("metrics"), dict) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    manifest["native_evidence_observation_ref"] = observation_path.name
    manifest["native_evidence_observation_sha256"] = _file_sha256(observation_path)
    metrics["native_evidence_observation"] = {
        "artifact_ref": observation_path.name,
        "artifact_sha256": _file_sha256(observation_path),
        **summary,
    }
    manifest["metrics"] = metrics
    _write_json(manifest_path, manifest)


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_text(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_object(text: object) -> dict[str, object]:
    if not isinstance(text, str) or not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if not isinstance(value, (list, tuple, set)):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _int(value: object, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _bounded(value: str, *, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 3)].rstrip() + "..."


def _decision_dict(decision: Mapping[str, object] | object) -> dict[str, object]:
    if isinstance(decision, Mapping):
        return dict(decision)
    as_dict = getattr(decision, "as_dict", None)
    if callable(as_dict):
        loaded = as_dict()
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def _evidence_origin(item: NativeTranscriptItem) -> dict[str, object]:
    return {
        "sequence": item.sequence,
        "turn_id": item.turn_id,
        "kind": item.kind,
        "tool_name": item.tool_name,
        "call_id": item.call_id,
        "status": item.status,
        "is_error": item.is_error,
    }


__all__ = [
    "AUTHORITATIVE_NATIVE_TRANSCRIPT_FILES",
    "CALL_ITEM_KINDS",
    "DERIVED_NATIVE_TRANSCRIPT_FILES",
    "IMPLEMENT_V2_NATIVE_RUNTIME_ID",
    "LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID",
    "NATIVE_TRANSCRIPT_ARTIFACT_CONTRACT_VERSION",
    "NATIVE_TRANSCRIPT_ITEM_SCHEMA_VERSION",
    "NATIVE_TRANSCRIPT_SCHEMA_VERSION",
    "NON_TOOL_ITEM_KINDS",
    "OUTPUT_ITEM_KINDS",
    "NativeTranscript",
    "NativeTranscriptItem",
    "NativeTranscriptItemKind",
    "NativeTranscriptOutputStatus",
    "NativeTranscriptValidationResult",
    "build_synthetic_error_output",
    "build_native_evidence_observation",
    "native_artifact_contract",
    "native_function_call_argument_metrics",
    "native_proof_manifest_from_transcript",
    "native_transcript_hash",
    "native_transcript_indexes",
    "native_transcript_metrics",
    "native_transcript_sidecar_events",
    "normalize_claude_tool_events",
    "normalize_codex_response_items",
    "validate_native_transcript_pairing",
    "write_native_evidence_observation",
    "write_native_transcript_artifacts",
]
