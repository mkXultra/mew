"""Provider-neutral implement_v2 tool route metadata.

Phase 1 of the command/edit boundary redesign introduces route decisions as
diagnostic/artifact metadata. These helpers must not become a shell mutation
classifier. They describe the selected tool route; they do not prove whether a
shell command mutates source.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Iterable, Literal, Mapping

from .types import ToolCallEnvelope, ToolResultEnvelope

TOOL_ROUTE_SCHEMA_VERSION = 1
COMMAND_CLASSIFICATION_SCHEMA_VERSION = 1

ToolRoute = Literal[
    "read",
    "process_runner",
    "process_lifecycle",
    "typed_source_mutation",
    "legacy_shell_edit_bridge",
    "finish",
    "invalid_tool_contract",
]

CommandClassificationStatus = Literal["simple", "too_complex", "unavailable"]

TOOL_ROUTE_VALUES: tuple[str, ...] = (
    "read",
    "process_runner",
    "process_lifecycle",
    "typed_source_mutation",
    "legacy_shell_edit_bridge",
    "finish",
    "invalid_tool_contract",
)
COMMAND_CLASSIFICATION_VALUES: tuple[str, ...] = ("simple", "too_complex", "unavailable")

READ_TOOL_NAMES = frozenset({"inspect_dir", "read_file", "search_text", "glob", "git_status", "git_diff"})
PROCESS_RUNNER_TOOL_NAMES = frozenset({"run_command", "run_tests"})
PROCESS_LIFECYCLE_TOOL_NAMES = frozenset({"poll_command", "cancel_command", "read_command_output"})
TYPED_SOURCE_MUTATION_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})


@dataclass(frozen=True)
class CommandClassificationResult:
    """Conservative shell metadata placeholder.

    Phase 1 emits `unavailable` until Phase 3 attaches parser-backed metadata.
    The result is intentionally not a source mutation decision.
    """

    result: CommandClassificationStatus
    parser: str = ""
    reason: str = ""
    command_hash: str = ""
    features: Mapping[str, object] | tuple[str, ...] = ()
    shortcut_consumers_enabled: bool | None = None
    schema_version: int = COMMAND_CLASSIFICATION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        features: object
        if isinstance(self.features, Mapping):
            features = dict(self.features)
        else:
            features = list(self.features)
        requested_shortcut = self.result == "simple" if self.shortcut_consumers_enabled is None else bool(
            self.shortcut_consumers_enabled
        )
        shortcut_enabled = self.result == "simple" and requested_shortcut
        return {
            "schema_version": self.schema_version,
            "result": self.result,
            "parser": self.parser,
            "reason": self.reason,
            "command_hash": self.command_hash,
            "features": features,
            "not_source_mutation_classifier": True,
            "shortcut_consumers_enabled": shortcut_enabled,
        }


@dataclass(frozen=True)
class ToolRouteDecision:
    """One provider-neutral route decision for a paired tool output."""

    tool_route: ToolRoute
    declared_tool: str
    effective_tool: str
    provider_call_id: str
    mew_tool_call_id: str
    route_reason: str
    native_transcript_refs: tuple[str, ...] = ()
    typed_evidence_refs: tuple[str, ...] = ()
    command_classification: CommandClassificationResult | None = None
    bridge_registry_id: str = ""
    schema_version: int = TOOL_ROUTE_SCHEMA_VERSION

    @property
    def ref(self) -> str:
        return f"tool-route:{_safe_ref(self.provider_call_id or self.mew_tool_call_id or self.declared_tool)}"

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": self.schema_version,
            "ref": self.ref,
            "tool_route": self.tool_route,
            "declared_tool": self.declared_tool,
            "effective_tool": self.effective_tool,
            "provider_call_id": self.provider_call_id,
            "mew_tool_call_id": self.mew_tool_call_id,
            "route_reason": self.route_reason,
            "native_transcript_refs": list(self.native_transcript_refs),
            "typed_evidence_refs": list(self.typed_evidence_refs),
            "bridge_registry_id": self.bridge_registry_id,
        }
        if self.command_classification is not None:
            payload["command_classification"] = self.command_classification.as_dict()
        return payload


def build_tool_route_decision(
    call: ToolCallEnvelope,
    result: ToolResultEnvelope,
    *,
    effective_tool: str = "",
) -> ToolRouteDecision:
    """Build route metadata for one call/result pair."""

    declared_tool = str(call.tool_name or result.tool_name or "")
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    resolved_effective_tool = str(
        effective_tool
        or (payload.get("effective_tool") if isinstance(payload, dict) else "")
        or (payload.get("effective_tool_name") if isinstance(payload, dict) else "")
        or result.tool_name
        or declared_tool
    )
    route, reason = _route_for_result(declared_tool, result)
    classification = None
    if route in {"process_runner", "process_lifecycle", "invalid_tool_contract"}:
        classification = _command_classification_from_payload(payload) or CommandClassificationResult(
            result="unavailable",
            parser="not-yet-attached",
            reason="Phase 1 route metadata only; Phase 3 owns parser-backed shell metadata",
            command_hash=_command_hash(call.arguments),
        )
    return ToolRouteDecision(
        tool_route=route,  # type: ignore[arg-type]
        declared_tool=declared_tool,
        effective_tool=resolved_effective_tool,
        provider_call_id=str(call.provider_call_id or result.provider_call_id or ""),
        mew_tool_call_id=str(call.mew_tool_call_id or result.mew_tool_call_id or ""),
        route_reason=reason,
        native_transcript_refs=_native_transcript_refs(call.provider_call_id or result.provider_call_id),
        typed_evidence_refs=tuple(str(ref) for ref in result.evidence_refs if str(ref).strip()),
        command_classification=classification,
        bridge_registry_id=_bridge_registry_id(result),
    )


def with_tool_route_decision(
    call: ToolCallEnvelope,
    result: ToolResultEnvelope,
    *,
    effective_tool: str = "",
) -> ToolResultEnvelope:
    """Return `result` with Phase 1 route metadata attached.

    This does not change execution status or side effects.
    """

    decision = build_tool_route_decision(call, result, effective_tool=effective_tool)
    content = _content_with_route_metadata(result.content, decision)
    return replace(result, content=content, route_decision=decision.as_dict())


def route_records_from_results(results: Iterable[ToolResultEnvelope]) -> tuple[dict[str, object], ...]:
    """Return tool route records for provider-neutral tool results."""

    records: list[dict[str, object]] = []
    for index, result in enumerate(results, start=1):
        decision = _decision_from_result(result)
        if decision:
            record = dict(decision)
        else:
            call = ToolCallEnvelope(
                lane_attempt_id=result.lane_attempt_id,
                provider="artifact",
                provider_call_id=result.provider_call_id or f"result-{index}",
                mew_tool_call_id=result.mew_tool_call_id,
                tool_name=result.tool_name,
            )
            record = build_tool_route_decision(call, result).as_dict()
        record.setdefault("record_index", index)
        records.append(record)
    return tuple(records)


def tool_route_artifact_from_results(results: Iterable[ToolResultEnvelope]) -> dict[str, object]:
    """Build a sidecar artifact for route decisions."""

    records = list(route_records_from_results(results))
    counts: dict[str, int] = {route: 0 for route in TOOL_ROUTE_VALUES}
    for record in records:
        route = str(record.get("tool_route") or "")
        if route in counts:
            counts[route] += 1
    return {
        "schema_version": TOOL_ROUTE_SCHEMA_VERSION,
        "artifact_kind": "implement_v2_tool_routes",
        "canonical_tool_routes": list(TOOL_ROUTE_VALUES),
        "records": records,
        "counts": counts,
        "record_count": len(records),
        "route_hash": _stable_hash(records),
    }


def route_records_from_native_transcript_items(items: Iterable[Mapping[str, object]]) -> tuple[dict[str, object], ...]:
    """Build route records from native transcript item dictionaries."""

    calls: dict[str, Mapping[str, object]] = {}
    records: list[dict[str, object]] = []
    for item in items:
        kind = str(item.get("kind") or "")
        call_id = str(item.get("call_id") or "")
        if not call_id:
            continue
        if kind.endswith("_call") or kind in {"function_call", "custom_tool_call"}:
            calls[call_id] = item
            continue
        if kind.endswith("_output") or kind in {"function_call_output", "custom_tool_call_output"}:
            call = calls.get(call_id, {})
            tool_name = str(call.get("tool_name") or item.get("tool_name") or "")
            route, reason = _route_for_tool_name(tool_name, status=str(item.get("status") or ""))
            record = {
                "schema_version": TOOL_ROUTE_SCHEMA_VERSION,
                "ref": f"tool-route:{_safe_ref(call_id)}",
                "tool_route": route,
                "declared_tool": tool_name,
                "effective_tool": tool_name,
                "provider_call_id": call_id,
                "mew_tool_call_id": f"native:{call_id}",
                "route_reason": reason,
                "native_transcript_refs": _native_transcript_refs(call_id),
                "typed_evidence_refs": [str(ref) for ref in item.get("evidence_refs") or [] if str(ref).strip()],
                "bridge_registry_id": "",
            }
            if route in {"process_runner", "process_lifecycle", "invalid_tool_contract"}:
                record["command_classification"] = CommandClassificationResult(
                    result="unavailable",
                    parser="not-yet-attached",
                    reason="Phase 1 route metadata only; Phase 3 owns parser-backed shell metadata",
                ).as_dict()
            records.append(record)
    return tuple(records)


def _route_for_result(tool_name: str, result: ToolResultEnvelope) -> tuple[str, str]:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    bridge_registry_id = _bridge_registry_id(result)
    if bridge_registry_id and _bridge_classification_allows_route(payload):
        return "legacy_shell_edit_bridge", "named legacy bridge result"
    if bridge_registry_id:
        return "invalid_tool_contract", "bridge parser metadata did not fail open"
    if _invalid_tool_contract_payload(payload):
        return "invalid_tool_contract", "explicit tool contract misuse payload"
    return _route_for_tool_name(tool_name, status=result.status)


def _route_for_tool_name(tool_name: str, *, status: str = "") -> tuple[str, str]:
    if tool_name in READ_TOOL_NAMES:
        return "read", "read-only tool"
    if tool_name in PROCESS_RUNNER_TOOL_NAMES:
        return "process_runner", "execute-route process runner"
    if tool_name in PROCESS_LIFECYCLE_TOOL_NAMES:
        return "process_lifecycle", "execute-route lifecycle tool"
    if tool_name in TYPED_SOURCE_MUTATION_TOOL_NAMES:
        return "typed_source_mutation", "typed source mutation tool"
    if tool_name == "finish":
        return "finish", "finish tool"
    return "invalid_tool_contract", f"unknown or unavailable tool status={status or 'unknown'}"


def _invalid_tool_contract_payload(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    failure_class = str(payload.get("failure_class") or "")
    kind = str(payload.get("kind") or "")
    reason = str(payload.get("reason") or "")
    return (
        failure_class == "tool_contract_misuse"
        or "tool_contract_misuse" in kind
        or "tool-contract" in reason
        or "not available" in reason
        or "unknown native tool" in reason
        or "unknown read-only tool" in reason
    )


def _bridge_registry_id(result: ToolResultEnvelope) -> str:
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    return str(payload.get("bridge_registry_id") or "") if isinstance(payload, dict) else ""


def _bridge_classification_allows_route(payload: object) -> bool:
    if not isinstance(payload, dict) or str(payload.get("bridge_status") or "") != "applied":
        return False
    classification = _command_classification_from_payload(payload)
    return classification is not None and classification.result == "simple" and classification.as_dict().get(
        "shortcut_consumers_enabled"
    ) is True


def _command_classification_from_payload(payload: object) -> CommandClassificationResult | None:
    if not isinstance(payload, dict):
        return None
    raw = payload.get("command_classification")
    if not isinstance(raw, dict):
        return None
    result = str(raw.get("result") or "")
    if result not in COMMAND_CLASSIFICATION_VALUES:
        return None
    features = raw.get("features")
    shortcut_raw = raw.get("shortcut_consumers_enabled") if "shortcut_consumers_enabled" in raw else None
    schema_version = _classification_schema_version(raw.get("schema_version"))
    if schema_version is None:
        return None
    return CommandClassificationResult(
        result=result,  # type: ignore[arg-type]
        parser=str(raw.get("parser") or ""),
        reason=str(raw.get("reason") or ""),
        command_hash=str(raw.get("command_hash") or ""),
        features=dict(features) if isinstance(features, Mapping) else tuple(str(item) for item in features or ()),
        shortcut_consumers_enabled=shortcut_raw is True,
        schema_version=schema_version,
    )


def _classification_schema_version(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value == COMMAND_CLASSIFICATION_SCHEMA_VERSION:
        return value
    return None


def _content_with_route_metadata(
    content: tuple[object, ...],
    decision: ToolRouteDecision,
) -> tuple[object, ...]:
    metadata = {
        "tool_route": decision.tool_route,
        "tool_route_ref": decision.ref,
        "tool_route_decision": decision.as_dict(),
    }
    if content and isinstance(content[0], dict):
        first = dict(content[0])
        first.update(metadata)
        return (first, *content[1:])
    return (metadata, *content)


def _decision_from_result(result: ToolResultEnvelope) -> dict[str, object]:
    if isinstance(result.route_decision, dict) and result.route_decision:
        return dict(result.route_decision)
    payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
    decision = payload.get("tool_route_decision") if isinstance(payload, dict) else {}
    return dict(decision) if isinstance(decision, dict) and decision else {}


def _native_transcript_refs(provider_call_id: object) -> tuple[str, ...]:
    value = str(provider_call_id or "").strip()
    if not value:
        return ()
    return (f"native-call:{value}", f"native-output:{value}")


def _command_hash(arguments: Mapping[str, object]) -> str:
    for key in ("command", "cmd", "argv"):
        value = arguments.get(key)
        if value not in (None, "", [], {}):
            return _stable_hash(value)
    return ""


def _stable_hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _safe_ref(value: object) -> str:
    text = str(value or "").strip()
    return "".join(ch if ch.isalnum() or ch in {"_", "-", ".", ":"} else "_" for ch in text) or "unknown"


__all__ = [
    "COMMAND_CLASSIFICATION_VALUES",
    "TOOL_ROUTE_VALUES",
    "CommandClassificationResult",
    "ToolRoute",
    "ToolRouteDecision",
    "build_tool_route_decision",
    "route_records_from_native_transcript_items",
    "route_records_from_results",
    "tool_route_artifact_from_results",
    "with_tool_route_decision",
]
