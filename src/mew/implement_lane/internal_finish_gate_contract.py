"""Static contracts for moving implement_v2 finish out of the live tool loop.

Phase 0 intentionally does not change live behavior.  It gives later phases a
small, deterministic leak gate for provider-visible tool descriptors and
sidecar records before the production finish tool is removed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


INTERNAL_FINISH_GATE_BOUNDARY_ANCHORS: tuple[str, ...] = (
    "done_candidate_detected",
    "internal_finish_gate_launched",
    "ng_resume_signal_appended",
    "provider_visible_finish_absent",
)

PROVIDER_VISIBLE_FINISH_TOOL_NAMES: tuple[str, ...] = ("finish",)

PROVIDER_VISIBLE_TOOL_ID_KEYS: tuple[str, ...] = (
    "access",
    "family",
    "internal_kernel",
    "name",
    "provider_name",
    "render_policy_id",
    "renderer_id",
    "route",
    "tool_name",
)

FORBIDDEN_FINISH_SCHEMA_FIELDS: tuple[str, ...] = (
    "closeout_refs",
    "evidence_refs",
    "final_status",
    "finish_gate",
    "finish_status",
    "missing_obligations",
    "oracle_obligation_refs",
    "resolver_decision",
    "summary",
    "task_done",
    "task_contract",
    "budget_blockers",
    "unsafe_blockers",
)

DONE_CANDIDATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "done_candidate_id",
    "lane_attempt_id",
    "turn_id",
    "assistant_message_item_ids",
    "final_response_text_ref",
    "transcript_hash_before_gate",
    "compact_sidecar_digest_hash",
    "detector_version",
)

DONE_CANDIDATE_FORBIDDEN_FIELDS: tuple[str, ...] = (
    "finish_call_id",
    "finish_tool_call_id",
    "provider_call_id",
)


@dataclass(frozen=True)
class FinishSurfaceGateViolation:
    code: str
    surface: str
    detail: str
    path: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "surface": self.surface,
            "detail": self.detail,
            "path": list(self.path),
        }


@dataclass(frozen=True)
class FinishSurfaceGateResult:
    surface: str
    violations: tuple[FinishSurfaceGateViolation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "surface": self.surface,
            "violations": [violation.as_dict() for violation in self.violations],
        }


def scan_provider_tool_descriptors_for_finish_leaks(
    descriptors: object,
    *,
    surface: str = "provider_tool_descriptors",
) -> FinishSurfaceGateResult:
    """Detect provider-visible finish descriptors or finish schema fields."""

    return _scan_finish_surface(descriptors, surface=surface)


def scan_tool_surface_metadata_for_finish_leaks(
    metadata: object,
    *,
    surface: str = "tool_surface_metadata",
) -> FinishSurfaceGateResult:
    """Detect finish route/render metadata that could leak after tool removal."""

    return _scan_finish_surface(metadata, surface=surface)


def validate_done_candidate_record(
    record: object,
    *,
    surface: str = "done_candidate_record",
) -> FinishSurfaceGateResult:
    """Validate the replay-canonical done-candidate sidecar row shape."""

    violations: list[FinishSurfaceGateViolation] = []
    if not isinstance(record, dict):
        return FinishSurfaceGateResult(
            surface=surface,
            violations=(
                FinishSurfaceGateViolation(
                    code="invalid_done_candidate_record",
                    surface=surface,
                    detail=f"expected object, got {type(record).__name__}",
                ),
            ),
        )

    for field in DONE_CANDIDATE_REQUIRED_FIELDS:
        if field not in record:
            violations.append(
                FinishSurfaceGateViolation(
                    code="missing_done_candidate_field",
                    surface=surface,
                    detail=f"missing required field: {field}",
                    path=(field,),
                )
            )
    for field in DONE_CANDIDATE_FORBIDDEN_FIELDS:
        if field in record:
            violations.append(
                FinishSurfaceGateViolation(
                    code="legacy_finish_field_in_done_candidate",
                    surface=surface,
                    detail=f"forbidden legacy finish field: {field}",
                    path=(field,),
                )
            )
    return FinishSurfaceGateResult(surface=surface, violations=tuple(violations))


def merge_finish_surface_gate_results(
    *results: FinishSurfaceGateResult,
    surface: str = "provider_visible_finish_absent",
) -> FinishSurfaceGateResult:
    violations: list[FinishSurfaceGateViolation] = []
    for result in results:
        violations.extend(result.violations)
    return FinishSurfaceGateResult(surface=surface, violations=tuple(violations))


def _scan_finish_surface(payload: object, *, surface: str) -> FinishSurfaceGateResult:
    violations: list[FinishSurfaceGateViolation] = []
    _scan_value(payload, surface=surface, path=(), violations=violations)
    return FinishSurfaceGateResult(surface=surface, violations=tuple(violations))


def _scan_value(
    value: object,
    *,
    surface: str,
    path: tuple[str, ...],
    violations: list[FinishSurfaceGateViolation],
) -> None:
    if isinstance(value, dict):
        _scan_mapping(value, surface=surface, path=path, violations=violations)
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            item_path = (*path, str(index))
            if _is_finish_identifier(item):
                violations.append(
                    FinishSurfaceGateViolation(
                        code="provider_visible_finish_tool",
                        surface=surface,
                        detail=f"finish identifier in list item: {item}",
                        path=item_path,
                    )
                )
            if _is_forbidden_schema_field(item):
                violations.append(
                    FinishSurfaceGateViolation(
                        code="provider_visible_finish_schema_field",
                        surface=surface,
                        detail=f"forbidden finish schema field: {item}",
                        path=item_path,
                    )
                )
            _scan_value(item, surface=surface, path=item_path, violations=violations)


def _scan_mapping(
    mapping: dict[Any, Any],
    *,
    surface: str,
    path: tuple[str, ...],
    violations: list[FinishSurfaceGateViolation],
) -> None:
    for raw_key, item in mapping.items():
        key = str(raw_key)
        item_path = (*path, key)
        if _is_finish_identifier(key):
            violations.append(
                FinishSurfaceGateViolation(
                    code="provider_visible_finish_tool",
                    surface=surface,
                    detail=f"finish identifier in key: {key}",
                    path=item_path,
                )
            )
        if key in PROVIDER_VISIBLE_TOOL_ID_KEYS and _is_finish_identifier(item):
            violations.append(
                FinishSurfaceGateViolation(
                    code="provider_visible_finish_tool",
                    surface=surface,
                    detail=f"finish identifier in {key}: {item}",
                    path=item_path,
                )
            )
        if key in FORBIDDEN_FINISH_SCHEMA_FIELDS:
            violations.append(
                FinishSurfaceGateViolation(
                    code="provider_visible_finish_schema_field",
                    surface=surface,
                    detail=f"forbidden finish schema field: {key}",
                    path=item_path,
                )
            )
        _scan_value(item, surface=surface, path=item_path, violations=violations)


def _is_finish_identifier(value: object) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower()
    return normalized == "finish" or "finish" in normalized


def _is_forbidden_schema_field(value: object) -> bool:
    return isinstance(value, str) and value in FORBIDDEN_FINISH_SCHEMA_FIELDS


__all__ = [
    "DONE_CANDIDATE_FORBIDDEN_FIELDS",
    "DONE_CANDIDATE_REQUIRED_FIELDS",
    "FORBIDDEN_FINISH_SCHEMA_FIELDS",
    "INTERNAL_FINISH_GATE_BOUNDARY_ANCHORS",
    "FinishSurfaceGateResult",
    "FinishSurfaceGateViolation",
    "merge_finish_surface_gate_results",
    "scan_provider_tool_descriptors_for_finish_leaks",
    "scan_tool_surface_metadata_for_finish_leaks",
    "validate_done_candidate_record",
]
