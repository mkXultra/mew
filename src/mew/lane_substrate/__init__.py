"""Shared lane runtime substrate interfaces.

This package is intentionally interface-only. Concrete lane behavior belongs
in lane-owned packages.
"""

from __future__ import annotations

from .runtime import (
    ArtifactRef,
    ArtifactWriter,
    CompletionDecision,
    CompletionPolicyProtocol,
    LaneInput,
    LaneRunResult,
    LaneRuntimeContext,
    LaneRuntimeSpec,
    NativeLoopRunner,
    NativeTranscriptStore,
    ObservabilityPolicy,
    ProviderNativeAdapter,
    ProviderRequestDescriptor,
    ProviderResponseItems,
    ReplayValidationResult,
    ReplayValidator,
    ToolDispatcher,
    ToolResultEnvelope,
    ToolResultRenderer,
    ToolSurfaceResolver,
    ToolSurfaceSnapshot,
    TranscriptAppendResult,
    TranscriptState,
)

__all__ = [
    "ArtifactRef",
    "ArtifactWriter",
    "CompletionDecision",
    "CompletionPolicyProtocol",
    "LaneInput",
    "LaneRunResult",
    "LaneRuntimeContext",
    "LaneRuntimeSpec",
    "NativeLoopRunner",
    "NativeTranscriptStore",
    "ObservabilityPolicy",
    "ProviderNativeAdapter",
    "ProviderRequestDescriptor",
    "ProviderResponseItems",
    "ReplayValidationResult",
    "ReplayValidator",
    "ToolDispatcher",
    "ToolResultEnvelope",
    "ToolResultRenderer",
    "ToolSurfaceResolver",
    "ToolSurfaceSnapshot",
    "TranscriptAppendResult",
    "TranscriptState",
]
