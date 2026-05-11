"""Offline provider-native Responses adapter substrate for implement_v2.

Phase 2 deliberately stops at request descriptors, streamed event parsing, and
sidecar persistence.  This module never calls a live model and never executes a
tool.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path

from .native_tool_schema import (
    NativeToolSchemaCapabilities,
    lowered_tool_descriptor_metadata,
    lower_implement_lane_tool_specs,
    provider_tool_spec_hash,
    provider_tool_specs,
    stable_json_hash,
    strict_false_reasons,
)
from .native_transcript import NativeTranscript, NativeTranscriptItem
from .tool_policy import ImplementLaneToolSpec, list_v2_base_tool_specs

NATIVE_PROVIDER_ADAPTER_SCHEMA_VERSION = 1
REASONING_SIDECAR_SCHEMA_VERSION = 1
ENCRYPTED_REASONING_INCLUDE = "reasoning.encrypted_content"

_SAFE_RESPONSE_HEADER_NAMES = frozenset(
    {
        "traceparent",
        "tracestate",
        "x-codex-beta-features",
        "x-codex-turn-metadata",
        "x-codex-turn-state",
    }
)
_UNSAFE_HEADER_TOKENS = (
    "authorization",
    "api-key",
    "apikey",
    "cookie",
    "token",
    "secret",
)


@dataclass(frozen=True)
class NativeProviderCapabilities:
    """Provider-native Responses capability decisions for Phase 2 descriptors."""

    provider: str = "openai"
    supports_native_tool_calls: bool = True
    supports_streaming: bool = True
    supports_custom_freeform_tools: bool = True
    supports_encrypted_reasoning: bool = True
    supports_parallel_tool_calls: bool = True

    def as_dict(self) -> dict[str, object]:
        provider_native_tool_loop = (
            self.supports_native_tool_calls and self.supports_streaming
        )
        return {
            "provider": self.provider,
            "supports_native_tool_calls": self.supports_native_tool_calls,
            "supports_streaming": self.supports_streaming,
            "supports_custom_freeform_tools": self.supports_custom_freeform_tools,
            "supports_encrypted_reasoning": self.supports_encrypted_reasoning,
            "supports_parallel_tool_calls": self.supports_parallel_tool_calls,
            "provider_native_tool_loop": provider_native_tool_loop,
        }


@dataclass(frozen=True)
class ReasoningSidecarValidationResult:
    """Validation result for transcript refs into reasoning_sidecar.json."""

    valid: bool
    errors: tuple[str, ...] = ()
    refs_resolved: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "refs_resolved": list(self.refs_resolved),
        }


@dataclass(frozen=True)
class NativeResponsesStreamParseResult:
    """Result of parsing one streamed Responses turn."""

    transcript: NativeTranscript
    response_id: str = ""
    status: str = ""
    usage: Mapping[str, object] = field(default_factory=dict)
    event_counts: Mapping[str, int] = field(default_factory=dict)
    metadata_events: tuple[dict[str, object], ...] = ()
    errors: tuple[str, ...] = ()
    control_actions: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "response_id": self.response_id,
            "status": self.status,
            "usage": dict(self.usage),
            "event_counts": dict(self.event_counts),
            "metadata_events": list(self.metadata_events),
            "errors": list(self.errors),
            "control_actions": list(self.control_actions),
            "transcript": self.transcript.as_dict(),
        }


def build_responses_request_descriptor(
    *,
    model: str,
    instructions: str,
    input_items: Iterable[Mapping[str, object]],
    tool_specs: Iterable[ImplementLaneToolSpec] | None = None,
    capabilities: NativeProviderCapabilities | None = None,
    reasoning: Mapping[str, object] | bool | None = None,
    transcript_window: object | None = None,
    reasoning_sidecar: Mapping[str, object] | None = None,
    reasoning_sidecar_refs: Iterable[str] | None = None,
    headers: Mapping[str, object] | None = None,
    provider_request_id: str = "",
    prompt_cache_key: str = "",
) -> dict[str, object]:
    """Build an auditable offline Responses request descriptor.

    The returned ``request_body`` is the provider-native request shape for this
    phase.  It always uses local state (`store=false`) and deliberately omits
    ``previous_response_id`` from the request body.
    """

    caps = capabilities or NativeProviderCapabilities()
    schema_caps = NativeToolSchemaCapabilities(
        supports_custom_freeform_tools=caps.supports_custom_freeform_tools
    )
    lowered_tools = lower_implement_lane_tool_specs(
        tuple(tool_specs if tool_specs is not None else list_v2_base_tool_specs()),
        capabilities=schema_caps,
    )
    input_payload = [dict(item) for item in input_items]
    request_body: dict[str, object] = {
        "model": model,
        "instructions": instructions,
        "input": input_payload,
        "tools": list(provider_tool_specs(lowered_tools)),
        "tool_choice": "auto",
        "parallel_tool_calls": caps.supports_parallel_tool_calls,
        "stream": True,
        "store": False,
    }
    if prompt_cache_key:
        request_body["prompt_cache_key"] = prompt_cache_key
    if _model_reasoning_requested(model=model, reasoning=reasoning):
        if isinstance(reasoning, Mapping):
            request_body["reasoning"] = dict(reasoning)
        elif reasoning is True:
            request_body["reasoning"] = {"effort": "medium"}
        if caps.supports_encrypted_reasoning:
            request_body["include"] = [ENCRYPTED_REASONING_INCLUDE]

    safe_headers, excluded_headers = sanitize_responses_headers(headers or {})
    tool_hash = provider_tool_spec_hash(lowered_tools)
    request_hash = stable_json_hash(request_body)
    transcript_hash = stable_json_hash(
        transcript_window if transcript_window is not None else input_payload
    )
    sidecar_digest_hash = (
        reasoning_sidecar_digest(reasoning_sidecar)
        if reasoning_sidecar
        else stable_json_hash({})
    )
    refs_used = tuple(
        reasoning_sidecar_refs
        if reasoning_sidecar_refs is not None
        else reasoning_carry_forward_refs(reasoning_sidecar)
    )
    provider_request_id = (
        provider_request_id or f"offline-{request_hash.removeprefix('sha256:')[:16]}"
    )
    tool_hashes = {
        lowered.name: stable_json_hash(lowered.provider_tool)
        for lowered in lowered_tools
    }
    capability_decisions = {
        **caps.as_dict(),
        "request_uses_stream": True,
        "request_store": False,
        "request_previous_response_id": None,
        "encrypted_reasoning_requested": ENCRYPTED_REASONING_INCLUDE
        in request_body.get("include", []),
        "stateless_reasoning_carry_forward": bool(refs_used),
        "apply_patch_transport": _apply_patch_transport(lowered_tools),
    }
    descriptor: dict[str, object] = {
        "schema_version": NATIVE_PROVIDER_ADAPTER_SCHEMA_VERSION,
        "transport_change": "yes",
        "transport_kind": "provider_native",
        "request_kind": "openai_responses",
        "provider": caps.provider,
        "model": model,
        "provider_request_id": provider_request_id,
        "request_body": request_body,
        "request_hash": request_hash,
        "store": False,
        "previous_response_id": None,
        "previous_response_id_in_request_body": "previous_response_id" in request_body,
        "stream": True,
        "safe_headers": safe_headers,
        "excluded_unsafe_header_names": list(excluded_headers),
        "tool_spec_hash": tool_hash,
        "tool_spec_hashes": tool_hashes,
        "tool_specs": list(lowered_tool_descriptor_metadata(lowered_tools)),
        "strict_false_reasons": strict_false_reasons(lowered_tools),
        "transcript_window_hash": transcript_hash,
        "sidecar_digest_hash": sidecar_digest_hash,
        "reasoning_sidecar_refs_used": list(refs_used),
        "capability_decisions": capability_decisions,
    }
    descriptor["descriptor_hash"] = stable_json_hash(
        {key: value for key, value in descriptor.items() if key != "descriptor_hash"}
    )
    return descriptor


def write_request_descriptor(
    path: Path | str, descriptor: Mapping[str, object]
) -> Path:
    """Persist a request descriptor artifact."""

    descriptor_path = Path(path)
    descriptor_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor_path.write_text(
        json.dumps(descriptor, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return descriptor_path


def build_function_call_output_input_item(
    *,
    call_id: str,
    output: str,
) -> dict[str, object]:
    """Build the next-turn Responses input item for a function-call result."""

    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output,
    }


def build_custom_tool_call_output_input_item(
    *,
    call_id: str,
    name: str,
    output: str,
) -> dict[str, object]:
    """Build the next-turn Responses input item for a custom/freeform result."""

    return {
        "type": "custom_tool_call_output",
        "call_id": call_id,
        "name": name,
        "output": output,
    }


def build_reasoning_sidecar_entry(
    *,
    response_id: str,
    provider_item_id: str,
    turn_id: str,
    encrypted_content: str,
    include_in_next_request: bool = True,
) -> dict[str, object]:
    """Build one reasoning sidecar entry from provider encrypted content."""

    digest = _sha256_text(encrypted_content)
    return {
        "ref": f"reasoning_sidecar.json#sha256:{digest}",
        "response_id": response_id,
        "provider_item_id": provider_item_id,
        "turn_id": turn_id,
        "encrypted_content_sha256": digest,
        "encrypted_content_bytes": encrypted_content,
        "include_in_next_request": include_in_next_request,
    }


def build_reasoning_sidecar(
    *,
    lane_attempt_id: str,
    provider: str,
    items: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    """Build a reasoning_sidecar.json payload."""

    payload = {
        "schema_version": REASONING_SIDECAR_SCHEMA_VERSION,
        "lane_attempt_id": lane_attempt_id,
        "provider": provider,
        "items": [dict(item) for item in items],
    }
    payload["sidecar_digest_hash"] = reasoning_sidecar_digest(payload)
    return payload


def write_reasoning_sidecar(path: Path | str, sidecar: Mapping[str, object]) -> Path:
    """Persist reasoning_sidecar.json."""

    sidecar_path = Path(path)
    sidecar_path.parent.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return sidecar_path


def read_reasoning_sidecar(path: Path | str) -> dict[str, object]:
    """Read reasoning_sidecar.json."""

    return json.loads(Path(path).read_text(encoding="utf-8"))


def reasoning_sidecar_digest(sidecar: Mapping[str, object] | None) -> str:
    """Return a stable sidecar digest that excludes encrypted blob bytes."""

    if not sidecar:
        return stable_json_hash({})
    items = sidecar.get("items") if isinstance(sidecar.get("items"), list) else []
    digest_items = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        digest_item = {
            key: value
            for key, value in item.items()
            if key != "encrypted_content_bytes"
        }
        digest_items.append(digest_item)
    return stable_json_hash(
        {
            "schema_version": sidecar.get("schema_version"),
            "lane_attempt_id": sidecar.get("lane_attempt_id"),
            "provider": sidecar.get("provider"),
            "items": digest_items,
        }
    )


def reasoning_carry_forward_refs(
    sidecar: Mapping[str, object] | None,
) -> tuple[str, ...]:
    """Return sidecar refs that should be carried into the next request."""

    if not sidecar:
        return ()
    refs: list[str] = []
    items = sidecar.get("items") if isinstance(sidecar.get("items"), list) else []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        ref = str(item.get("ref") or "")
        if ref and bool(item.get("include_in_next_request")):
            refs.append(ref)
    return tuple(refs)


def validate_reasoning_sidecar_refs(
    transcript: NativeTranscript,
    sidecar: Mapping[str, object],
) -> ReasoningSidecarValidationResult:
    """Validate transcript encrypted_reasoning_ref values against the sidecar."""

    items = sidecar.get("items") if isinstance(sidecar.get("items"), list) else []
    by_ref = {
        str(item.get("ref")): item
        for item in items
        if isinstance(item, Mapping) and item.get("ref")
    }
    errors: list[str] = []
    refs_resolved: list[str] = []
    for item in transcript.items:
        if not item.encrypted_reasoning_ref:
            continue
        sidecar_item = by_ref.get(item.encrypted_reasoning_ref)
        if sidecar_item is None:
            errors.append(
                f"missing_reasoning_sidecar_ref:{item.encrypted_reasoning_ref}"
            )
            continue
        encrypted_content = str(sidecar_item.get("encrypted_content_bytes") or "")
        expected_hash = str(sidecar_item.get("encrypted_content_sha256") or "")
        actual_hash = _sha256_text(encrypted_content)
        if expected_hash != actual_hash:
            errors.append(
                f"encrypted_reasoning_hash_mismatch:{item.encrypted_reasoning_ref}"
            )
            continue
        refs_resolved.append(item.encrypted_reasoning_ref)
    return ReasoningSidecarValidationResult(
        valid=not errors, errors=tuple(errors), refs_resolved=tuple(refs_resolved)
    )


def sanitize_responses_headers(
    headers: Mapping[str, object],
) -> tuple[dict[str, str], tuple[str, ...]]:
    """Return headers safe for descriptor persistence plus excluded names."""

    safe: dict[str, str] = {}
    excluded: list[str] = []
    for raw_name, raw_value in headers.items():
        name = str(raw_name).strip().lower()
        if not name:
            continue
        if name in _SAFE_RESPONSE_HEADER_NAMES and not any(
            token in name for token in _UNSAFE_HEADER_TOKENS
        ):
            safe[name] = str(raw_value)
        else:
            excluded.append(name)
    return dict(sorted(safe.items())), tuple(sorted(excluded))


def parse_responses_stream_events(
    events: Iterable[Mapping[str, object]],
    *,
    lane_attempt_id: str,
    provider: str = "openai",
    model: str = "",
    turn_id: str = "turn-1",
) -> NativeResponsesStreamParseResult:
    """Parse native Responses stream events into a native transcript turn."""

    parser = _ResponsesStreamParser(
        lane_attempt_id=lane_attempt_id,
        provider=provider,
        model=model,
        turn_id=turn_id,
    )
    for event in events:
        parser.feed(event)
    return parser.finish()


class _ResponsesStreamParser:
    def __init__(
        self, *, lane_attempt_id: str, provider: str, model: str, turn_id: str
    ) -> None:
        self.lane_attempt_id = lane_attempt_id
        self.provider = provider
        self.model = model
        self.turn_id = turn_id
        self.response_id = ""
        self.status = ""
        self.usage: dict[str, object] = {}
        self.event_counts: dict[str, int] = {}
        self.metadata_events: list[dict[str, object]] = []
        self.errors: list[str] = []
        self.items: list[NativeTranscriptItem] = []
        self.slots: dict[str, dict[str, object]] = {}

    def feed(self, event: Mapping[str, object]) -> None:
        event_type = _event_type(event)
        if not event_type:
            self.errors.append("event_missing_type")
            return
        self.event_counts[event_type] = self.event_counts.get(event_type, 0) + 1
        if event_type == "response.created":
            self._record_response(event, status="created")
            return
        if event_type == "response.output_item.added":
            item = _mapping(event.get("item"))
            if item:
                self._slot_for(event, item).update({"item": item})
            return
        if event_type in {"response.content_part.added", "response.content_part.done"}:
            slot = self._slot_for(event, _mapping(event.get("item")))
            parts = _list(slot.setdefault("content_parts", []))
            parts.append(
                {
                    "event_type": event_type,
                    "content_index": event.get("content_index"),
                    "part": event.get("part"),
                }
            )
            self.metadata_events.append(
                {"type": event_type, "output_index": event.get("output_index")}
            )
            return
        if event_type == "response.output_text.delta":
            self._append_slot_text(event, "text_parts")
            return
        if event_type == "response.output_text.done":
            slot = self._slot_for(event, _mapping(event.get("item")))
            slot["output_text_done"] = _text(event.get("text") or event.get("delta"))
            return
        if event_type == "response.function_call_arguments.delta":
            self._append_slot_text(event, "argument_parts")
            return
        if event_type == "response.function_call_arguments.done":
            slot = self._slot_for(event, _mapping(event.get("item")))
            slot["arguments_done"] = _text(event.get("arguments") or event.get("delta"))
            return
        if event_type == "response.custom_tool_call_input.delta":
            self._append_slot_text(event, "custom_input_parts")
            return
        if event_type in {
            "response.custom_tool_call_input.done",
            "response.custom_tool_call_input.completed",
        }:
            slot = self._slot_for(event, _mapping(event.get("item")))
            slot["custom_input_done"] = _text(event.get("input") or event.get("delta"))
            return
        if event_type == "response.output_item.done":
            item = _mapping(event.get("item"))
            if item:
                self._finalize_item(event, item)
            return
        if event_type == "response.completed":
            self._record_response(event, status="completed")
            return
        if event_type == "response.failed":
            self._record_response(event, status="failed")
            response = _mapping(event.get("response"))
            error = _mapping(response.get("error")) if response else {}
            self.errors.append(
                _text(error.get("message") or error.get("code") or "response.failed")
            )
            return
        if event_type == "response.incomplete":
            self._record_response(event, status="incomplete")
            response = _mapping(event.get("response"))
            incomplete = (
                _mapping(response.get("incomplete_details")) if response else {}
            )
            self.errors.append(
                "response.incomplete:" + _text(incomplete.get("reason") or "unknown")
            )
            return
        self.metadata_events.append({"type": event_type, "event": dict(event)})

    def finish(self) -> NativeResponsesStreamParseResult:
        transcript = NativeTranscript(
            lane_attempt_id=self.lane_attempt_id,
            provider=self.provider,
            model=self.model,
            items=tuple(self.items),
        )
        return NativeResponsesStreamParseResult(
            transcript=transcript,
            response_id=self.response_id,
            status=self.status,
            usage=self.usage,
            event_counts=dict(sorted(self.event_counts.items())),
            metadata_events=tuple(self.metadata_events),
            errors=tuple(self.errors),
            control_actions=(),
        )

    def _record_response(self, event: Mapping[str, object], *, status: str) -> None:
        response = _mapping(event.get("response"))
        if response:
            self.response_id = _text(response.get("id") or self.response_id)
            usage = response.get("usage")
            if isinstance(usage, Mapping):
                self.usage = dict(usage)
            metadata = response.get("metadata")
            if isinstance(metadata, Mapping):
                self.metadata_events.append(
                    {"type": _event_type(event), "metadata": dict(metadata)}
                )
        self.status = status

    def _slot_for(
        self, event: Mapping[str, object], item: Mapping[str, object] | None
    ) -> dict[str, object]:
        key = _slot_key(event, item)
        slot = self.slots.setdefault(key, {"key": key})
        if item:
            slot.setdefault("item", dict(item))
        return slot

    def _append_slot_text(self, event: Mapping[str, object], field_name: str) -> None:
        slot = self._slot_for(event, _mapping(event.get("item")))
        parts = _list(slot.setdefault(field_name, []))
        parts.append(_text(event.get("delta")))

    def _finalize_item(
        self, event: Mapping[str, object], item: Mapping[str, object]
    ) -> None:
        slot = self._slot_for(event, item)
        slot_item = _mapping(slot.get("item"))
        merged_item = {**slot_item, **dict(item)}
        item_type = _text(merged_item.get("type") or merged_item.get("kind"))
        name = _text(merged_item.get("name"))
        sequence = len(self.items) + 1
        response_id = _text(merged_item.get("response_id") or self.response_id)
        provider_item_id = _text(
            merged_item.get("id") or merged_item.get("item_id") or event.get("item_id")
        )
        output_index = _int(
            event.get("output_index"),
            _int(merged_item.get("output_index"), sequence - 1),
        )
        call_id = _text(merged_item.get("call_id") or event.get("call_id"))
        if (
            item_type in {"function_call", "response.function_call"}
            or merged_item.get("arguments") is not None
        ):
            arguments = _joined_or_done(slot, "argument_parts", "arguments_done")
            if not arguments:
                arguments = _json_text(merged_item.get("arguments"))
            self.items.append(
                NativeTranscriptItem(
                    sequence=sequence,
                    turn_id=self.turn_id,
                    lane_attempt_id=self.lane_attempt_id,
                    provider=self.provider,
                    model=self.model,
                    response_id=response_id,
                    provider_item_id=provider_item_id,
                    output_index=output_index,
                    kind="finish_call" if name == "finish" else "function_call",
                    call_id=call_id,
                    tool_name=name,
                    arguments_json_text=arguments,
                )
            )
            return
        if item_type in {"custom_tool_call", "custom_call"}:
            custom_input = _joined_or_done(
                slot, "custom_input_parts", "custom_input_done"
            ) or _text(merged_item.get("input") or merged_item.get("content"))
            self.items.append(
                NativeTranscriptItem(
                    sequence=sequence,
                    turn_id=self.turn_id,
                    lane_attempt_id=self.lane_attempt_id,
                    provider=self.provider,
                    model=self.model,
                    response_id=response_id,
                    provider_item_id=provider_item_id,
                    output_index=output_index,
                    kind="custom_tool_call",
                    call_id=call_id,
                    tool_name=name,
                    custom_input_text=custom_input,
                )
            )
            return
        if item_type == "reasoning":
            encrypted_content = _text(merged_item.get("encrypted_content"))
            encrypted_ref = _text(merged_item.get("encrypted_reasoning_ref"))
            if encrypted_content and not encrypted_ref:
                encrypted_ref = (
                    f"reasoning_sidecar.json#sha256:{_sha256_text(encrypted_content)}"
                )
            self.items.append(
                NativeTranscriptItem(
                    sequence=sequence,
                    turn_id=self.turn_id,
                    lane_attempt_id=self.lane_attempt_id,
                    provider=self.provider,
                    model=self.model,
                    response_id=response_id,
                    provider_item_id=provider_item_id,
                    output_index=output_index,
                    kind="reasoning",
                    output_text_or_ref=_reasoning_summary_text(merged_item),
                    encrypted_reasoning_ref=encrypted_ref,
                )
            )
            return
        if item_type in {"custom_tool_call_output", "custom_output"}:
            self.items.append(
                NativeTranscriptItem(
                    sequence=sequence,
                    turn_id=self.turn_id,
                    lane_attempt_id=self.lane_attempt_id,
                    provider=self.provider,
                    model=self.model,
                    response_id=response_id,
                    provider_item_id=provider_item_id,
                    output_index=output_index,
                    kind="custom_tool_call_output",
                    call_id=call_id,
                    tool_name=name,
                    output_text_or_ref=_text(
                        merged_item.get("output") or merged_item.get("content")
                    ),
                    status=_text(merged_item.get("status") or "completed"),
                    is_error=bool(merged_item.get("is_error")),
                )
            )
            return
        if (
            item_type in {"function_call_output", "tool_output"}
            or merged_item.get("output") is not None
        ):
            self.items.append(
                NativeTranscriptItem(
                    sequence=sequence,
                    turn_id=self.turn_id,
                    lane_attempt_id=self.lane_attempt_id,
                    provider=self.provider,
                    model=self.model,
                    response_id=response_id,
                    provider_item_id=provider_item_id,
                    output_index=output_index,
                    kind="finish_output"
                    if name == "finish"
                    else "function_call_output",
                    call_id=call_id,
                    tool_name=name,
                    output_text_or_ref=_text(
                        merged_item.get("output") or merged_item.get("content")
                    ),
                    status=_text(merged_item.get("status") or "completed"),
                    is_error=bool(merged_item.get("is_error")),
                )
            )
            return
        self.items.append(
            NativeTranscriptItem(
                sequence=sequence,
                turn_id=self.turn_id,
                lane_attempt_id=self.lane_attempt_id,
                provider=self.provider,
                model=self.model,
                response_id=response_id,
                provider_item_id=provider_item_id,
                output_index=output_index,
                kind="assistant_message",
                output_text_or_ref=_assistant_text(merged_item, slot),
            )
        )


def _apply_patch_transport(lowered_tools: Iterable[object]) -> str:
    for lowered in lowered_tools:
        provider_tool = getattr(lowered, "provider_tool", {})
        if (
            isinstance(provider_tool, Mapping)
            and provider_tool.get("name") == "apply_patch"
        ):
            return _text(provider_tool.get("type"))
    return "unavailable"


def _model_reasoning_requested(
    *, model: str, reasoning: Mapping[str, object] | bool | None
) -> bool:
    if reasoning is None or reasoning is False:
        return False
    if reasoning is True:
        return True
    effort = (
        str(reasoning.get("effort") or reasoning.get("summary") or "").strip().lower()
    )
    if effort in {"", "none", "disabled", "off"}:
        return False
    return bool(model.strip())


def _event_type(event: Mapping[str, object]) -> str:
    return _text(event.get("type") or event.get("event") or event.get("kind"))


def _slot_key(event: Mapping[str, object], item: Mapping[str, object] | None) -> str:
    output_index = event.get("output_index")
    if output_index is None and item:
        output_index = item.get("output_index")
    if output_index is not None:
        return f"output_index:{output_index}"
    item_id = event.get("item_id")
    if item_id is None and item:
        item_id = item.get("id") or item.get("item_id")
    if item_id:
        return f"item_id:{item_id}"
    call_id = event.get("call_id")
    if call_id is None and item:
        call_id = item.get("call_id")
    if call_id:
        return f"call_id:{call_id}"
    return "output_index:0"


def _assistant_text(item: Mapping[str, object], slot: Mapping[str, object]) -> str:
    text = _joined_or_done(slot, "text_parts", "output_text_done")
    if text:
        return text
    content = item.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes)):
        parts: list[str] = []
        for part in content:
            if isinstance(part, Mapping):
                parts.append(_text(part.get("text") or part.get("content")))
            else:
                parts.append(_text(part))
        return "".join(parts)
    return _text(item.get("text"))


def _reasoning_summary_text(item: Mapping[str, object]) -> str:
    summary = item.get("summary")
    if isinstance(summary, str):
        return summary
    if isinstance(summary, Sequence) and not isinstance(summary, (str, bytes)):
        return "".join(
            _text(part.get("text") if isinstance(part, Mapping) else part)
            for part in summary
        )
    content = item.get("content")
    if isinstance(content, str):
        return content
    return ""


def _joined_or_done(
    slot: Mapping[str, object], parts_field: str, done_field: str
) -> str:
    done = _text(slot.get(done_field))
    if done:
        return done
    parts = slot.get(parts_field)
    if isinstance(parts, Sequence) and not isinstance(parts, (str, bytes)):
        return "".join(_text(part) for part in parts)
    return ""


def _json_text(value: object) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


__all__ = [
    "ENCRYPTED_REASONING_INCLUDE",
    "NATIVE_PROVIDER_ADAPTER_SCHEMA_VERSION",
    "REASONING_SIDECAR_SCHEMA_VERSION",
    "NativeProviderCapabilities",
    "NativeResponsesStreamParseResult",
    "ReasoningSidecarValidationResult",
    "build_custom_tool_call_output_input_item",
    "build_function_call_output_input_item",
    "build_reasoning_sidecar",
    "build_reasoning_sidecar_entry",
    "build_responses_request_descriptor",
    "parse_responses_stream_events",
    "read_reasoning_sidecar",
    "reasoning_carry_forward_refs",
    "reasoning_sidecar_digest",
    "sanitize_responses_headers",
    "validate_reasoning_sidecar_refs",
    "write_reasoning_sidecar",
    "write_request_descriptor",
]
