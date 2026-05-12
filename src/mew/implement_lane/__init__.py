"""Implementation-lane boundary primitives.

Exports are resolved lazily so importing a boundary-only submodule such as
``mew.implement_lane.completion_resolver`` does not initialize execution
runtimes or the native harness.
"""

from __future__ import annotations

from importlib import import_module


_EXPORTS: dict[str, tuple[str, str]] = {
    "COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION": ("mew.implement_lane.workframe_variants", "COMMON_WORKFRAME_INPUTS_SCHEMA_VERSION"),
    "COMPLETION_RESOLVER_DECISIONS_FILE": ("mew.implement_lane.completion_resolver", "COMPLETION_RESOLVER_DECISIONS_FILE"),
    "COMPLETION_RESOLVER_POLICY_VERSION": ("mew.implement_lane.completion_resolver", "COMPLETION_RESOLVER_POLICY_VERSION"),
    "COMPLETION_RESOLVER_SCHEMA_VERSION": ("mew.implement_lane.completion_resolver", "COMPLETION_RESOLVER_SCHEMA_VERSION"),
    "DEFAULT_WORKFRAME_VARIANT": ("mew.implement_lane.workframe_variants", "DEFAULT_WORKFRAME_VARIANT"),
    "IMPLEMENT_LANE_REGISTRY_VERSION": ("mew.implement_lane.registry", "IMPLEMENT_LANE_REGISTRY_VERSION"),
    "IMPLEMENT_V2_NATIVE_RUNTIME_ID": ("mew.implement_lane.native_transcript", "IMPLEMENT_V2_NATIVE_RUNTIME_ID"),
    "WORKFRAME_FIXTURE_CONVERSION_VERSION": ("mew.implement_lane.workframe_variants", "WORKFRAME_FIXTURE_CONVERSION_VERSION"),
    "WORKFRAME_PROJECTION_SCHEMA_VERSION": ("mew.implement_lane.workframe_variants", "WORKFRAME_PROJECTION_SCHEMA_VERSION"),
    "CommonWorkFrameInputs": ("mew.implement_lane.workframe_variants", "CommonWorkFrameInputs"),
    "CompletionResolver": ("mew.implement_lane.completion_resolver", "CompletionResolver"),
    "CompletionResolverDecision": ("mew.implement_lane.completion_resolver", "CompletionResolverDecision"),
    "CompletionResolverInput": ("mew.implement_lane.completion_resolver", "CompletionResolverInput"),
    "FinishClaim": ("mew.implement_lane.completion_resolver", "FinishClaim"),
    "ImplementLaneInput": ("mew.implement_lane.types", "ImplementLaneInput"),
    "ImplementLaneProofManifest": ("mew.implement_lane.types", "ImplementLaneProofManifest"),
    "ImplementLaneResult": ("mew.implement_lane.types", "ImplementLaneResult"),
    "ImplementLaneRuntimeView": ("mew.implement_lane.registry", "ImplementLaneRuntimeView"),
    "ImplementLaneToolSpec": ("mew.implement_lane.tool_policy", "ImplementLaneToolSpec"),
    "ImplementLaneTranscriptEvent": ("mew.implement_lane.types", "ImplementLaneTranscriptEvent"),
    "ImplementV1AdapterDescriptor": ("mew.implement_lane.v1_adapter", "ImplementV1AdapterDescriptor"),
    "ImplementV2ManagedExecRuntime": ("mew.implement_lane.exec_runtime", "ImplementV2ManagedExecRuntime"),
    "ImplementV2WriteRuntime": ("mew.implement_lane.write_runtime", "ImplementV2WriteRuntime"),
    "M624ReentryABGateResult": ("mew.implement_lane.reentry_gate", "M624ReentryABGateResult"),
    "NativeTranscript": ("mew.implement_lane.native_transcript", "NativeTranscript"),
    "NativeTranscriptItem": ("mew.implement_lane.native_transcript", "NativeTranscriptItem"),
    "NativeTranscriptValidationResult": ("mew.implement_lane.native_transcript", "NativeTranscriptValidationResult"),
    "PairingValidationResult": ("mew.implement_lane.replay", "PairingValidationResult"),
    "ToolCallEnvelope": ("mew.implement_lane.types", "ToolCallEnvelope"),
    "ToolResultEnvelope": ("mew.implement_lane.types", "ToolResultEnvelope"),
    "UnknownWorkFrameVariantError": ("mew.implement_lane.workframe_variants", "UnknownWorkFrameVariantError"),
    "WorkFrame": ("mew.implement_lane.workframe", "WorkFrame"),
    "WorkFrameInputs": ("mew.implement_lane.workframe", "WorkFrameInputs"),
    "WorkFrameInvariantReport": ("mew.implement_lane.workframe", "WorkFrameInvariantReport"),
    "WorkFrameProjectionResult": ("mew.implement_lane.workframe_variants", "WorkFrameProjectionResult"),
    "WorkFrameReducerVariant": ("mew.implement_lane.workframe_variants", "WorkFrameReducerVariant"),
    "WorkFrameTrace": ("mew.implement_lane.workframe", "WorkFrameTrace"),
    "build_implement_v2_prompt_sections": ("mew.implement_lane.prompt", "build_implement_v2_prompt_sections"),
    "build_invalid_tool_result": ("mew.implement_lane.replay", "build_invalid_tool_result"),
    "build_synthetic_error_output": ("mew.implement_lane.native_transcript", "build_synthetic_error_output"),
    "build_transcript_event": ("mew.implement_lane.transcript", "build_transcript_event"),
    "canonicalize_common_workframe_inputs": ("mew.implement_lane.workframe_variants", "canonicalize_common_workframe_inputs"),
    "canonicalize_workframe_inputs": ("mew.implement_lane.workframe", "canonicalize_workframe_inputs"),
    "check_phase0_prompt_inventory": ("mew.implement_lane.workframe", "check_phase0_prompt_inventory"),
    "common_workframe_input_hash": ("mew.implement_lane.workframe_variants", "common_workframe_input_hash"),
    "common_workframe_inputs_from_workframe_inputs": (
        "mew.implement_lane.workframe_variants",
        "common_workframe_inputs_from_workframe_inputs",
    ),
    "completion_resolver_manifest_fields": ("mew.implement_lane.completion_resolver", "completion_resolver_manifest_fields"),
    "describe_implement_v1_adapter": ("mew.implement_lane.v1_adapter", "describe_implement_v1_adapter"),
    "describe_implement_v2_runtime": ("mew.implement_lane.v2_runtime", "describe_implement_v2_runtime"),
    "describe_workframe_variant": ("mew.implement_lane.workframe_variants", "describe_workframe_variant"),
    "evaluate_m6_24_reentry_ab_gate": ("mew.implement_lane.reentry_gate", "evaluate_m6_24_reentry_ab_gate"),
    "execute_read_only_tool_call": ("mew.implement_lane.read_runtime", "execute_read_only_tool_call"),
    "extract_inspected_paths": ("mew.implement_lane.read_runtime", "extract_inspected_paths"),
    "get_implement_lane_runtime_view": ("mew.implement_lane.registry", "get_implement_lane_runtime_view"),
    "implement_v2_prompt_section_metrics": ("mew.implement_lane.prompt", "implement_v2_prompt_section_metrics"),
    "lane_artifact_namespace": ("mew.implement_lane.transcript", "lane_artifact_namespace"),
    "list_implement_lane_runtime_views": ("mew.implement_lane.registry", "list_implement_lane_runtime_views"),
    "list_v2_base_tool_specs": ("mew.implement_lane.tool_policy", "list_v2_base_tool_specs"),
    "list_v2_tool_specs_for_mode": ("mew.implement_lane.tool_policy", "list_v2_tool_specs_for_mode"),
    "list_workframe_variants": ("mew.implement_lane.workframe_variants", "list_workframe_variants"),
    "native_artifact_contract": ("mew.implement_lane.native_transcript", "native_artifact_contract"),
    "native_proof_manifest_from_transcript": ("mew.implement_lane.native_transcript", "native_proof_manifest_from_transcript"),
    "native_transcript_hash": ("mew.implement_lane.native_transcript", "native_transcript_hash"),
    "native_transcript_indexes": ("mew.implement_lane.native_transcript", "native_transcript_indexes"),
    "native_transcript_metrics": ("mew.implement_lane.native_transcript", "native_transcript_metrics"),
    "native_transcript_sidecar_events": ("mew.implement_lane.native_transcript", "native_transcript_sidecar_events"),
    "normalize_claude_tool_events": ("mew.implement_lane.native_transcript", "normalize_claude_tool_events"),
    "normalize_codex_response_items": ("mew.implement_lane.native_transcript", "normalize_codex_response_items"),
    "normalize_workframe_variant": ("mew.implement_lane.workframe_variants", "normalize_workframe_variant"),
    "project_workframe_with_variant": ("mew.implement_lane.workframe_variants", "project_workframe_with_variant"),
    "record_phase0_baseline_metrics": ("mew.implement_lane.workframe", "record_phase0_baseline_metrics"),
    "reduce_workframe": ("mew.implement_lane.workframe", "reduce_workframe"),
    "reduce_workframe_with_variant": ("mew.implement_lane.workframe_variants", "reduce_workframe_with_variant"),
    "run_live_native_implement_v2": ("mew.implement_lane.native_tool_harness", "run_live_native_implement_v2"),
    "run_native_implement_v2": ("mew.implement_lane.native_tool_harness", "run_native_implement_v2"),
    "run_unavailable_native_implement_v2": ("mew.implement_lane.native_tool_harness", "run_unavailable_native_implement_v2"),
    "select_implement_lane_runtime": ("mew.implement_lane.registry", "select_implement_lane_runtime"),
    "validate_native_transcript_pairing": ("mew.implement_lane.native_transcript", "validate_native_transcript_pairing"),
    "validate_proof_manifest_pairing": ("mew.implement_lane.replay", "validate_proof_manifest_pairing"),
    "validate_tool_result_pairing": ("mew.implement_lane.replay", "validate_tool_result_pairing"),
    "validate_workframe_variant_name": ("mew.implement_lane.workframe_variants", "validate_workframe_variant_name"),
    "workframe_debug_bundle_format": ("mew.implement_lane.workframe", "workframe_debug_bundle_format"),
    "workframe_output_hash": ("mew.implement_lane.workframe", "workframe_output_hash"),
    "write_completion_resolver_artifacts": ("mew.implement_lane.completion_resolver", "write_completion_resolver_artifacts"),
    "write_native_transcript_artifacts": ("mew.implement_lane.native_transcript", "write_native_transcript_artifacts"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> object:
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
