"""Replay validation for implement_v2 provider-native tool pairing."""

from __future__ import annotations

from dataclasses import dataclass

from .types import ToolCallEnvelope, ToolResultEnvelope, ToolResultStatus

ERROR_RESULT_STATUSES: frozenset[ToolResultStatus] = frozenset(
    {"failed", "denied", "invalid", "interrupted"}
)
WRITE_TOOL_NAMES = frozenset({"write_file", "edit_file", "apply_patch"})


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


def validate_proof_manifest_write_safety(manifest) -> PairingValidationResult:
    """Validate write-result safety invariants beyond provider call pairing."""

    errors: list[str] = []
    tool_calls = tuple(manifest.tool_calls)
    tool_results = tuple(manifest.tool_results)

    for result in tool_results:
        if result.tool_name not in WRITE_TOOL_NAMES:
            continue
        payload = result.content[0] if result.content and isinstance(result.content[0], dict) else {}
        side_effects = tuple(effect for effect in result.side_effects if isinstance(effect, dict))
        if side_effects and result.status != "completed":
            errors.append(f"write_side_effect_on_non_completed_result:{result.provider_call_id}:{result.status}")
        if side_effects and result.is_error:
            errors.append(f"write_side_effect_on_error_result:{result.provider_call_id}")
        if side_effects and not result.evidence_refs:
            errors.append(f"write_side_effect_missing_evidence_ref:{result.provider_call_id}")
        if payload.get("dry_run") is True and side_effects:
            errors.append(f"dry_run_result_has_side_effect:{result.provider_call_id}")
        if payload.get("written") and not side_effects:
            errors.append(f"written_payload_missing_side_effect:{result.provider_call_id}")
        if payload.get("dry_run") is False and payload.get("written") and result.status == "completed":
            approval_id = str(payload.get("approval_id") or "").strip()
            approval_source = str(payload.get("approval_source") or "").strip()
            if not approval_id or not approval_source:
                errors.append(f"write_apply_missing_independent_approval:{result.provider_call_id}")
        for index, effect in enumerate(side_effects):
            if effect.get("kind") != "file_write":
                errors.append(f"unknown_write_side_effect_kind:{result.provider_call_id}:{index}")
            if effect.get("dry_run") is not False:
                errors.append(f"write_side_effect_not_marked_non_dry_run:{result.provider_call_id}:{index}")
            if effect.get("written") is not True:
                errors.append(f"write_side_effect_not_marked_written:{result.provider_call_id}:{index}")
            if not str(effect.get("path") or "").strip():
                errors.append(f"write_side_effect_missing_path:{result.provider_call_id}:{index}")
            if not str(effect.get("approval_id") or "").strip():
                errors.append(f"write_side_effect_missing_approval_id:{result.provider_call_id}:{index}")
            if not str(effect.get("approval_source") or "").strip():
                errors.append(f"write_side_effect_missing_approval_source:{result.provider_call_id}:{index}")

    return PairingValidationResult(
        valid=not errors,
        errors=tuple(errors),
        call_count=len(tool_calls),
        result_count=len(tool_results),
    )


def build_invalid_tool_result(
    call: ToolCallEnvelope,
    *,
    reason: str,
    extra_content: dict[str, object] | None = None,
) -> ToolResultEnvelope:
    """Build the paired model-visible invalid result for a rejected call."""

    content: dict[str, object] = {"reason": reason}
    if extra_content:
        content.update({str(key): value for key, value in extra_content.items() if value not in (None, "", [], {})})
    return ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="invalid",
        is_error=True,
        content=(content,),
    )


__all__ = [
    "PairingValidationResult",
    "build_invalid_tool_result",
    "validate_proof_manifest_pairing",
    "validate_proof_manifest_write_safety",
    "validate_tool_result_pairing",
]
