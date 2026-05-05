"""Replay validation for implement_v2 provider-native tool pairing."""

from __future__ import annotations

from dataclasses import dataclass

from .types import ToolCallEnvelope, ToolResultEnvelope, ToolResultStatus

ERROR_RESULT_STATUSES: frozenset[ToolResultStatus] = frozenset(
    {"failed", "denied", "invalid", "interrupted"}
)


@dataclass(frozen=True)
class PairingValidationResult:
    """Result of validating provider call/result pairing invariants."""

    valid: bool
    errors: tuple[str, ...] = ()
    call_count: int = 0
    result_count: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "errors": list(self.errors),
            "call_count": self.call_count,
            "result_count": self.result_count,
        }


def validate_tool_result_pairing(
    tool_calls: tuple[ToolCallEnvelope, ...] | list[ToolCallEnvelope],
    tool_results: tuple[ToolResultEnvelope, ...] | list[ToolResultEnvelope],
    *,
    expected_lane_attempt_id: str = "",
) -> PairingValidationResult:
    """Validate every provider tool call has exactly one matching result."""

    errors: list[str] = []
    calls_by_provider_id: dict[str, ToolCallEnvelope] = {}
    results_by_provider_id: dict[str, ToolResultEnvelope] = {}
    mew_call_ids: set[str] = set()

    for call in tool_calls:
        if expected_lane_attempt_id and call.lane_attempt_id != expected_lane_attempt_id:
            errors.append(f"tool_call_wrong_lane_attempt_id:{call.provider_call_id}")
        if not call.provider_call_id:
            errors.append(f"tool_call_missing_provider_call_id:{call.mew_tool_call_id}")
        if call.provider_call_id in calls_by_provider_id:
            errors.append(f"duplicate_provider_call_id:{call.provider_call_id}")
        else:
            calls_by_provider_id[call.provider_call_id] = call
        if call.mew_tool_call_id in mew_call_ids:
            errors.append(f"duplicate_mew_tool_call_id:{call.mew_tool_call_id}")
        mew_call_ids.add(call.mew_tool_call_id)

    for result in tool_results:
        if expected_lane_attempt_id and result.lane_attempt_id != expected_lane_attempt_id:
            errors.append(f"tool_result_wrong_lane_attempt_id:{result.provider_call_id}")
        if not result.provider_call_id:
            errors.append(f"tool_result_missing_provider_call_id:{result.mew_tool_call_id}")
        if result.provider_call_id in results_by_provider_id:
            errors.append(f"duplicate_result_for_provider_call_id:{result.provider_call_id}")
            continue
        results_by_provider_id[result.provider_call_id] = result

    for provider_call_id, call in calls_by_provider_id.items():
        result = results_by_provider_id.get(provider_call_id)
        if result is None:
            errors.append(f"missing_result_for_provider_call_id:{provider_call_id}")
            continue
        if result.lane_attempt_id != call.lane_attempt_id:
            errors.append(f"lane_attempt_id_mismatch:{provider_call_id}")
        if result.mew_tool_call_id != call.mew_tool_call_id:
            errors.append(f"mew_tool_call_id_mismatch:{provider_call_id}")
        if result.tool_name != call.tool_name:
            errors.append(f"tool_name_mismatch:{provider_call_id}")
        if result.status in ERROR_RESULT_STATUSES and not result.is_error:
            errors.append(f"error_status_without_is_error:{provider_call_id}:{result.status}")
        if result.status in {"running", "yielded"} and result.is_error:
            errors.append(f"nonterminal_result_marked_error:{provider_call_id}:{result.status}")

    for provider_call_id in results_by_provider_id:
        if provider_call_id not in calls_by_provider_id:
            errors.append(f"orphan_result_for_provider_call_id:{provider_call_id}")

    return PairingValidationResult(
        valid=not errors,
        errors=tuple(errors),
        call_count=len(tool_calls),
        result_count=len(tool_results),
    )


def validate_proof_manifest_pairing(manifest) -> PairingValidationResult:
    """Validate manifest calls/results against its declared lane attempt id."""

    return validate_tool_result_pairing(
        tuple(manifest.tool_calls),
        tuple(manifest.tool_results),
        expected_lane_attempt_id=str(manifest.lane_attempt_id),
    )


def build_invalid_tool_result(call: ToolCallEnvelope, *, reason: str) -> ToolResultEnvelope:
    """Build the paired model-visible invalid result for a rejected call."""

    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="invalid",
        is_error=True,
        content=({"reason": reason},),
    )


__all__ = [
    "PairingValidationResult",
    "build_invalid_tool_result",
    "validate_proof_manifest_pairing",
    "validate_tool_result_pairing",
]
