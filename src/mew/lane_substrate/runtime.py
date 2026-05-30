"""Interface-level substrate contracts for provider-native lane runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence


JSONMapping = Mapping[str, Any]


@dataclass(frozen=True)
class ArtifactRef:
    """Stable reference to a persisted lane artifact or sidecar."""

    kind: str
    path: str
    digest: str = ""
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class LaneInput:
    """Provider-neutral lane input visible to the shared runtime boundary."""

    work_session_id: str
    task_id: str
    workspace: str
    lane_config: JSONMapping = field(default_factory=dict)
    task_contract: JSONMapping = field(default_factory=dict)
    persisted_lane_state: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptState:
    """Opaque transcript summary passed between substrate components."""

    lane_attempt_id: str
    turn_id: str = ""
    response_id: str = ""
    item_count: int = 0
    pending_call_ids: tuple[str, ...] = ()
    sidecar_refs: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True)
class TranscriptAppendResult:
    """Result of appending provider or tool items to a transcript store."""

    state: TranscriptState
    artifact_refs: tuple[ArtifactRef, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderRequestDescriptor:
    """Serializable description of one provider request."""

    provider: str
    model: str
    request_id: str = ""
    items: tuple[JSONMapping, ...] = ()
    tool_descriptors: tuple[JSONMapping, ...] = ()
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponseItems:
    """Provider-native response items after adapter parsing."""

    response_id: str
    items: tuple[JSONMapping, ...] = ()
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class ToolSurfaceSnapshot:
    """Provider-visible tool surface plus route metadata."""

    profile_id: str
    descriptors: tuple[JSONMapping, ...] = ()
    route_records: tuple[JSONMapping, ...] = ()
    renderer_id: str = ""
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResultEnvelope:
    """Provider-neutral result envelope returned by a lane tool dispatcher."""

    call_id: str
    tool_name: str
    status: str
    is_error: bool = False
    provider_visible_text: str = ""
    content_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    sidecar_refs: tuple[ArtifactRef, ...] = ()
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class CompletionDecision:
    """Lane-owned completion policy output consumed opaquely by substrate."""

    status: str
    done_candidate: JSONMapping | None = None
    resume_signal: JSONMapping | None = None
    sidecar_refs: tuple[ArtifactRef, ...] = ()
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class ReplayValidationResult:
    """Replay validation status for transcript and artifact invariants."""

    ok: bool
    checks: JSONMapping = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    artifact_refs: tuple[ArtifactRef, ...] = ()


@dataclass(frozen=True)
class LaneRunResult:
    """Provider-native loop result returned through the shared substrate."""

    lane_id: str
    runtime_id: str
    status: str
    transcript_refs: tuple[ArtifactRef, ...] = ()
    provider_request_refs: tuple[ArtifactRef, ...] = ()
    provider_response_refs: tuple[ArtifactRef, ...] = ()
    route_record_refs: tuple[ArtifactRef, ...] = ()
    proof_manifest_ref: ArtifactRef | None = None
    completion: CompletionDecision | None = None
    metadata: JSONMapping = field(default_factory=dict)


@dataclass(frozen=True)
class LaneRuntimeContext:
    """Runtime context passed to tool dispatch and completion components."""

    lane_input: LaneInput
    artifact_root: Path
    transcript_state: TranscriptState
    tool_surface: ToolSurfaceSnapshot
    metadata: JSONMapping = field(default_factory=dict)


class NativeTranscriptStore(Protocol):
    """Append and validate provider-native transcript items."""

    def append_provider_items(self, items: Sequence[JSONMapping]) -> TranscriptAppendResult:
        ...

    def append_tool_output(self, result: ToolResultEnvelope) -> TranscriptAppendResult:
        ...

    def validate_pairing(self) -> ReplayValidationResult:
        ...

    def write_response_transcript(self, artifact_root: Path) -> ArtifactRef:
        ...


class ProviderNativeAdapter(Protocol):
    """Provider-owned request and response conversion boundary."""

    def build_request_descriptor(
        self,
        lane_input: LaneInput,
        transcript_state: TranscriptState,
        tool_surface: ToolSurfaceSnapshot,
    ) -> ProviderRequestDescriptor:
        ...

    def parse_response_items(self, response: Any) -> ProviderResponseItems:
        ...

    def apply_previous_response_delta(
        self,
        descriptor: ProviderRequestDescriptor,
        transcript_state: TranscriptState,
    ) -> ProviderRequestDescriptor:
        ...


class ToolSurfaceResolver(Protocol):
    """Build the provider-visible tool surface for one lane turn."""

    def build_snapshot(
        self,
        lane_config: JSONMapping,
        transcript_state: TranscriptState,
        provider_capabilities: JSONMapping,
    ) -> ToolSurfaceSnapshot:
        ...


class ToolDispatcher(Protocol):
    """Dispatch one provider-native tool call."""

    def dispatch(self, provider_call: JSONMapping, runtime_context: LaneRuntimeContext) -> ToolResultEnvelope:
        ...


class ToolResultRenderer(Protocol):
    """Render a tool result into provider-visible text."""

    def render(self, profile_id: str, result: ToolResultEnvelope) -> str:
        ...


class ArtifactWriter(Protocol):
    """Persist transcript, request, route, proof, and sidecar artifacts."""

    def write_transcript(self, transcript_state: TranscriptState, artifact_root: Path) -> ArtifactRef:
        ...

    def write_tool_results(self, results: Sequence[ToolResultEnvelope], artifact_root: Path) -> ArtifactRef:
        ...

    def write_provider_requests(self, descriptors: Sequence[ProviderRequestDescriptor], artifact_root: Path) -> ArtifactRef:
        ...

    def write_route_records(self, snapshot: ToolSurfaceSnapshot, artifact_root: Path) -> ArtifactRef:
        ...

    def write_proof_manifest(self, result: LaneRunResult, artifact_root: Path) -> ArtifactRef:
        ...

    def patch_manifest_sidecar_refs(self, manifest_ref: ArtifactRef, sidecar_refs: Sequence[ArtifactRef]) -> ArtifactRef:
        ...


class ObservabilityPolicy(Protocol):
    """Lane-neutral hook for native request/response inventories."""

    def record_provider_request(self, descriptor: ProviderRequestDescriptor, artifact_root: Path) -> ArtifactRef:
        ...

    def record_provider_response(self, response_items: ProviderResponseItems, artifact_root: Path) -> ArtifactRef:
        ...


class CompletionPolicyProtocol(Protocol):
    """Lane-owned completion policy consumed opaquely by substrate."""

    def maybe_build_done_candidate(self, transcript_state: TranscriptState) -> CompletionDecision:
        ...

    def run_internal_closeout(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        ...

    def resolve_completion(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        ...

    def build_resume_signal(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        ...


class ReplayValidator(Protocol):
    """Validate replayable transcript and artifact invariants."""

    def validate(self, artifact_root: Path) -> ReplayValidationResult:
        ...


@dataclass(frozen=True)
class LaneRuntimeSpec:
    """Composition root for one provider-native lane runtime."""

    lane_id: str
    runtime_id: str
    provider_adapter: ProviderNativeAdapter
    tool_surface_resolver: ToolSurfaceResolver
    tool_dispatcher: ToolDispatcher
    transcript_store: NativeTranscriptStore
    artifact_writer: ArtifactWriter
    completion_policy: CompletionPolicyProtocol
    observability_policy: ObservabilityPolicy
    tool_result_renderer: ToolResultRenderer | None = None
    replay_validator: ReplayValidator | None = None
    metadata: JSONMapping = field(default_factory=dict)


class NativeLoopRunner(Protocol):
    """Shared provider-native loop runner protocol."""

    def run(
        self,
        spec: LaneRuntimeSpec,
        lane_input: LaneInput,
        provider: Any,
        artifact_root: Path,
        max_turns: int,
    ) -> LaneRunResult:
        ...
