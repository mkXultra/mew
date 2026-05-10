"""Implementation-lane boundary primitives."""

from .registry import (
    IMPLEMENT_LANE_REGISTRY_VERSION,
    ImplementLaneRuntimeView,
    get_implement_lane_runtime_view,
    list_implement_lane_runtime_views,
    select_implement_lane_runtime,
)
from .exec_runtime import ImplementV2ManagedExecRuntime
from .provider import FakeProviderAdapter, FakeProviderToolCall, JsonModelProviderAdapter
from .prompt import build_implement_v2_prompt_sections, implement_v2_prompt_section_metrics
from .read_runtime import execute_read_only_tool_call, extract_inspected_paths
from .reentry_gate import M624ReentryABGateResult, evaluate_m6_24_reentry_ab_gate
from .replay import (
    PairingValidationResult,
    build_invalid_tool_result,
    validate_proof_manifest_pairing,
    validate_tool_result_pairing,
)
from .tool_policy import ImplementLaneToolSpec, list_v2_base_tool_specs, list_v2_tool_specs_for_mode
from .transcript import build_transcript_event, lane_artifact_namespace
from .types import (
    ImplementLaneInput,
    ImplementLaneProofManifest,
    ImplementLaneResult,
    ImplementLaneTranscriptEvent,
    ToolCallEnvelope,
    ToolResultEnvelope,
)
from .v1_adapter import ImplementV1AdapterDescriptor, describe_implement_v1_adapter
from .v2_runtime import (
    describe_implement_v2_runtime,
    run_live_json_implement_v2,
    run_fake_exec_implement_v2,
    run_fake_read_only_implement_v2,
    run_fake_write_implement_v2,
    run_unavailable_implement_v2,
)
from .workframe import (
    WorkFrame,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    WorkFrameTrace,
    canonicalize_workframe_inputs,
    check_phase0_prompt_inventory,
    record_phase0_baseline_metrics,
    reduce_workframe,
    workframe_output_hash,
    workframe_debug_bundle_format,
)
from .write_runtime import ImplementV2WriteRuntime

__all__ = [
    "IMPLEMENT_LANE_REGISTRY_VERSION",
    "FakeProviderAdapter",
    "FakeProviderToolCall",
    "ImplementLaneInput",
    "ImplementLaneProofManifest",
    "ImplementLaneResult",
    "ImplementLaneRuntimeView",
    "ImplementLaneTranscriptEvent",
    "ImplementLaneToolSpec",
    "ImplementV1AdapterDescriptor",
    "ImplementV2ManagedExecRuntime",
    "ImplementV2WriteRuntime",
    "JsonModelProviderAdapter",
    "M624ReentryABGateResult",
    "PairingValidationResult",
    "ToolCallEnvelope",
    "ToolResultEnvelope",
    "WorkFrame",
    "WorkFrameInputs",
    "WorkFrameInvariantReport",
    "WorkFrameTrace",
    "build_implement_v2_prompt_sections",
    "build_transcript_event",
    "build_invalid_tool_result",
    "canonicalize_workframe_inputs",
    "check_phase0_prompt_inventory",
    "describe_implement_v1_adapter",
    "describe_implement_v2_runtime",
    "evaluate_m6_24_reentry_ab_gate",
    "execute_read_only_tool_call",
    "extract_inspected_paths",
    "get_implement_lane_runtime_view",
    "lane_artifact_namespace",
    "list_implement_lane_runtime_views",
    "list_v2_base_tool_specs",
    "list_v2_tool_specs_for_mode",
    "implement_v2_prompt_section_metrics",
    "record_phase0_baseline_metrics",
    "reduce_workframe",
    "run_fake_exec_implement_v2",
    "run_fake_read_only_implement_v2",
    "run_fake_write_implement_v2",
    "run_live_json_implement_v2",
    "run_unavailable_implement_v2",
    "select_implement_lane_runtime",
    "validate_proof_manifest_pairing",
    "validate_tool_result_pairing",
    "workframe_output_hash",
    "workframe_debug_bundle_format",
]
