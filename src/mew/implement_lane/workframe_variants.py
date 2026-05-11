"""WorkFrame reducer variant registry for implement_v2 experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re

from .workframe import (
    WORKFRAME_CANONICALIZER_VERSION,
    WORKFRAME_REDUCER_SCHEMA_VERSION,
    WORKFRAME_SCHEMA_VERSION,
    WorkFrame,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    canonical_json,
    canonicalize_workframe_inputs,
    reduce_workframe,
)
from .workframe_variant_minimal import reduce_minimal_workframe
from .workframe_variant_transcript_first import reduce_transcript_first_workframe
from .workframe_variant_transition_contract import reduce_transition_contract_workframe

COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION = 1
CURRENT_WORKFRAME_VARIANT = "current"
DEFAULT_WORKFRAME_VARIANT = "transition_contract"
WORKFRAME_FIXTURE_CONVERSION_VERSION = 1
WORKFRAME_PROJECTION_SCHEMA_VERSION = 3
_VARIANT_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


@dataclass(frozen=True)
class WorkFrameReducerVariant:
    name: str
    description: str


@dataclass(frozen=True)
class CommonWorkFrameInputs:
    """Shared, variant-neutral WorkFrame projection substrate.

    Phase 3 keeps existing reducers on WorkFrameInputs, but every projection is
    now anchored to this common wrapper so variant switches can prove they used
    identical tool/result/evidence substrate.
    """

    current_workframe_inputs: WorkFrameInputs
    attempt: dict[str, object]
    transcript: dict[str, object] = field(default_factory=dict)
    tool_registry: dict[str, object] = field(default_factory=dict)
    sidecars: dict[str, object] = field(default_factory=dict)
    indexes: dict[str, object] = field(default_factory=dict)
    replay: dict[str, object] = field(default_factory=dict)
    migration: dict[str, object] = field(default_factory=dict)
    schema_version: int = COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt": dict(self.attempt),
            "transcript": dict(self.transcript),
            "tool_registry": dict(self.tool_registry),
            "sidecars": dict(self.sidecars),
            "indexes": dict(self.indexes),
            "replay": dict(self.replay),
            "migration": dict(self.migration),
            "current_workframe_inputs": self.current_workframe_inputs.as_dict(),
        }


@dataclass(frozen=True)
class WorkFrameProjectionResult:
    """Variant projection plus hashes needed for replay and benchmark A/B."""

    variant: str
    common_inputs: CommonWorkFrameInputs
    workframe: WorkFrame
    invariant_report: WorkFrameInvariantReport
    shared_substrate_hash: str
    projection_hash: str
    schema_version: int = WORKFRAME_PROJECTION_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "variant": self.variant,
            "shared_substrate_hash": self.shared_substrate_hash,
            "projection_hash": self.projection_hash,
            "workframe": self.workframe.as_dict(),
            "invariant_report": self.invariant_report.as_dict(),
        }


class UnknownWorkFrameVariantError(ValueError):
    """Raised when a requested WorkFrame reducer variant is not registered."""


_VARIANTS: dict[str, WorkFrameReducerVariant] = {
    CURRENT_WORKFRAME_VARIANT: WorkFrameReducerVariant(
        name=CURRENT_WORKFRAME_VARIANT,
        description="Current M6.24 WorkFrame reducer behavior.",
    ),
    "minimal": WorkFrameReducerVariant(
        name="minimal",
        description="Thin WorkFrame reducer that preserves finish and verifier safety gates.",
    ),
    "transcript_first": WorkFrameReducerVariant(
        name="transcript_first",
        description="Prefers fresh paired transcript/tool evidence over stale prompt-projection fallback.",
    ),
    "transition_contract": WorkFrameReducerVariant(
        name="transition_contract",
        description="Adds a compact reducer-owned transition contract when fresh observations change state.",
    ),
}


def normalize_workframe_variant(value: object) -> str:
    """Normalize a requested WorkFrame variant name."""

    text = str(value or "").strip().lower().replace("-", "_")
    return text or DEFAULT_WORKFRAME_VARIANT


def validate_workframe_variant_name(value: object) -> str:
    """Return a normalized registered WorkFrame variant name or raise."""

    name = normalize_workframe_variant(value)
    if not _VARIANT_NAME_RE.fullmatch(name):
        raise UnknownWorkFrameVariantError(f"invalid WorkFrame variant name: {value!r}")
    if name not in _VARIANTS:
        available = ", ".join(sorted(_VARIANTS))
        raise UnknownWorkFrameVariantError(f"unknown WorkFrame variant {name!r}; available: {available}")
    return name


def list_workframe_variants() -> tuple[WorkFrameReducerVariant, ...]:
    return tuple(_VARIANTS[name] for name in sorted(_VARIANTS))


def describe_workframe_variant(value: object = DEFAULT_WORKFRAME_VARIANT) -> WorkFrameReducerVariant:
    return _VARIANTS[validate_workframe_variant_name(value)]


def common_workframe_inputs_from_workframe_inputs(
    inputs: WorkFrameInputs,
    *,
    transcript: dict[str, object] | None = None,
    tool_registry: dict[str, object] | None = None,
    sidecars: dict[str, object] | None = None,
    indexes: dict[str, object] | None = None,
    replay: dict[str, object] | None = None,
    migration: dict[str, object] | None = None,
) -> CommonWorkFrameInputs:
    """Adapt existing WorkFrameInputs into the Phase-3 common substrate."""

    return CommonWorkFrameInputs(
        current_workframe_inputs=inputs,
        attempt={
            "attempt_id": inputs.attempt_id,
            "turn_id": inputs.turn_id,
            "task_id": inputs.task_id,
            "objective": inputs.objective,
            "success_contract_ref": inputs.success_contract_ref,
            "constraints": list(inputs.constraints),
            "budget_class": _string_from_metrics(inputs.baseline_metrics, "budget_class"),
        },
        transcript={
            "natural_transcript_tail_ref": "",
            "transcript_tail_hash": "",
            "latest_tool_call_ref": _latest_event_value(inputs.sidecar_events, "provider_call_id"),
            "latest_tool_result_ref": _latest_event_value(inputs.sidecar_events, "event_id"),
            "paired_call_result_index_ref": "",
            **(transcript or {}),
        },
        tool_registry={
            "registry_ref": _string_from_metrics(inputs.baseline_metrics, "tool_registry_ref"),
            "registry_hash": _string_from_metrics(inputs.baseline_metrics, "tool_registry_hash"),
            "active_tool_refs": _list_from_metrics(inputs.baseline_metrics, "provider_tool_names"),
            "provider_tool_spec_hash": _string_from_metrics(inputs.baseline_metrics, "provider_tool_spec_hash"),
            "tool_policy_index_ref": "",
            **(tool_registry or {}),
        },
        sidecars={
            "observation_event_log_ref": "",
            "typed_evidence_delta_ref": "",
            "evidence_ref_index_ref": "",
            "artifact_obligation_index_ref": "",
            "verifier_freshness_ref": "",
            "repair_loop_state_ref": "",
            "source_mutation_index_ref": "",
            **(sidecars or {}),
        },
        indexes={
            "tool_result_index_ref": "",
            "evidence_search_index_ref": "",
            "model_turn_index_ref": "",
            "model_turn_index_usage": "debug_plateau_recovery_only",
            **(indexes or {}),
        },
        replay={
            "workframe_cursor_ref": "",
            "previous_workframe_hash": inputs.previous_workframe_hash,
            "replay_manifest_ref": "",
            "compression_cursor_ref": "",
            **(replay or {}),
        },
        migration={
            "source_workframe_schema_version": inputs.schema_version,
            "fixture_conversion_version": WORKFRAME_FIXTURE_CONVERSION_VERSION,
            "canonicalizer_version": WORKFRAME_CANONICALIZER_VERSION,
            "workframe_reducer_schema_version": WORKFRAME_REDUCER_SCHEMA_VERSION,
            "target_workframe_schema_version": WORKFRAME_SCHEMA_VERSION,
            **(migration or {}),
        },
    )


def canonicalize_common_workframe_inputs(inputs: CommonWorkFrameInputs) -> dict[str, object]:
    """Return byte-stable common substrate inputs for replay and A/B."""

    payload = inputs.as_dict()
    payload["current_workframe_inputs"] = canonicalize_workframe_inputs(inputs.current_workframe_inputs)
    return _canonical_mapping(
        {
            "schema_version": COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION,
            "canonicalizer_version": WORKFRAME_CANONICALIZER_VERSION,
            "payload": payload,
        }
    )


def common_workframe_input_hash(inputs: CommonWorkFrameInputs) -> str:
    return _sha256_json(canonicalize_common_workframe_inputs(inputs))


def project_workframe_with_variant(
    inputs: CommonWorkFrameInputs | WorkFrameInputs,
    *,
    variant: object = DEFAULT_WORKFRAME_VARIANT,
) -> WorkFrameProjectionResult:
    """Project a WorkFrame variant over common substrate inputs."""

    common = (
        common_workframe_inputs_from_workframe_inputs(inputs)
        if isinstance(inputs, WorkFrameInputs)
        else inputs
    )
    name = validate_workframe_variant_name(variant)
    workframe, report = _reduce_workframe_variant(common.current_workframe_inputs, name=name)
    substrate_hash = common_workframe_input_hash(common)
    projection_hash = _sha256_json(
        {
            "schema_version": WORKFRAME_PROJECTION_SCHEMA_VERSION,
            "variant": name,
            "shared_substrate_hash": substrate_hash,
            "workframe": workframe.as_dict(),
            "invariant_report_status": report.status,
        }
    )
    return WorkFrameProjectionResult(
        variant=name,
        common_inputs=common,
        workframe=workframe,
        invariant_report=report,
        shared_substrate_hash=substrate_hash,
        projection_hash=projection_hash,
    )


def reduce_workframe_with_variant(
    inputs: WorkFrameInputs,
    *,
    variant: object = DEFAULT_WORKFRAME_VARIANT,
) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce WorkFrame inputs with a registered variant.

    Variants live in separate modules while sharing the same inputs, artifact
    format, fastchecks, and step-shape analyzer.
    """

    result = project_workframe_with_variant(inputs, variant=variant)
    return result.workframe, result.invariant_report


def _reduce_workframe_variant(
    inputs: WorkFrameInputs,
    *,
    name: str,
) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    if name == CURRENT_WORKFRAME_VARIANT:
        return reduce_workframe(inputs)
    if name == "minimal":
        return reduce_minimal_workframe(inputs)
    if name == "transcript_first":
        return reduce_transcript_first_workframe(inputs)
    if name == "transition_contract":
        return reduce_transition_contract_workframe(inputs)
    raise UnknownWorkFrameVariantError(f"unimplemented WorkFrame variant {name!r}")


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_mapping(value: object) -> dict[str, object]:
    return json.loads(canonical_json(value))


def _latest_event_value(events: tuple[dict[str, object], ...], key: str) -> str:
    for event in reversed(events):
        if not isinstance(event, dict):
            continue
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _list_from_metrics(metrics: dict[str, object], key: str) -> list[str]:
    value = metrics.get(key)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _string_from_metrics(metrics: dict[str, object], key: str) -> str:
    value = metrics.get(key)
    if isinstance(value, str):
        return value
    return ""


__all__ = [
    "COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION",
    "DEFAULT_WORKFRAME_VARIANT",
    "WORKFRAME_FIXTURE_CONVERSION_VERSION",
    "WORKFRAME_PROJECTION_SCHEMA_VERSION",
    "CommonWorkFrameInputs",
    "UnknownWorkFrameVariantError",
    "WorkFrameProjectionResult",
    "WorkFrameReducerVariant",
    "canonicalize_common_workframe_inputs",
    "common_workframe_input_hash",
    "common_workframe_inputs_from_workframe_inputs",
    "describe_workframe_variant",
    "list_workframe_variants",
    "normalize_workframe_variant",
    "project_workframe_with_variant",
    "reduce_workframe_with_variant",
    "validate_workframe_variant_name",
]
