"""Research-lane proof fixture built only on the shared lane substrate.

This module is intentionally small. It proves a future lane can compose the
substrate interfaces without importing implement-lane runtime modules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any

from ..lane_substrate import (
    ArtifactRef,
    CompletionDecision,
    LaneInput,
    LaneRunResult,
    LaneRuntimeContext,
    LaneRuntimeSpec,
    ProviderRequestDescriptor,
    ProviderResponseItems,
    ReplayValidationResult,
    ToolResultEnvelope,
    ToolSurfaceSnapshot,
    TranscriptAppendResult,
    TranscriptState,
)


RESEARCH_FIXTURE_LANE_ID = "research_fixture"
RESEARCH_FIXTURE_RUNTIME_ID = "research_fixture_native_substrate"
RESEARCH_FIXTURE_PROFILE_ID = "research_fixture_tools"


class ResearchFixtureProvider:
    """Fake provider returning one research-owned tool call."""

    provider = "research-fixture"
    model = "research-fixture-model"

    def respond(self, descriptor: ProviderRequestDescriptor) -> tuple[Mapping[str, Any], ...]:
        query = str(descriptor.metadata.get("task") or "substrate proof")
        return (
            {
                "kind": "message",
                "id": "msg-research-1",
                "text": f"Searching notes for {query}.",
            },
            {
                "kind": "tool_call",
                "call_id": "call-search-notes-1",
                "tool_name": "search_notes",
                "arguments": {"query": query},
            },
        )


class _ResearchProviderAdapter:
    def build_request_descriptor(
        self,
        lane_input: LaneInput,
        transcript_state: TranscriptState,
        tool_surface: ToolSurfaceSnapshot,
    ) -> ProviderRequestDescriptor:
        task = str(lane_input.task_contract.get("description") or lane_input.task_id)
        return ProviderRequestDescriptor(
            provider="research-fixture",
            model="research-fixture-model",
            request_id=f"request:{transcript_state.lane_attempt_id}:1",
            items=(
                {
                    "role": "user",
                    "content": task,
                    "lane": RESEARCH_FIXTURE_LANE_ID,
                },
            ),
            tool_descriptors=tool_surface.descriptors,
            metadata={
                "task": task,
                "profile_id": tool_surface.profile_id,
                "transcript_item_count": transcript_state.item_count,
            },
        )

    def parse_response_items(self, response: Any) -> ProviderResponseItems:
        if not isinstance(response, Sequence) or isinstance(response, (str, bytes)):
            raise ValueError("research fixture provider response must be a sequence")
        items = tuple(dict(item) for item in response if isinstance(item, Mapping))
        return ProviderResponseItems(
            response_id="response:research-fixture:1",
            items=items,
            metadata={"item_count": len(items)},
        )

    def apply_previous_response_delta(
        self,
        descriptor: ProviderRequestDescriptor,
        transcript_state: TranscriptState,
    ) -> ProviderRequestDescriptor:
        metadata = dict(descriptor.metadata)
        metadata["previous_response_id"] = transcript_state.response_id
        return replace(descriptor, metadata=metadata)


class _ResearchToolSurfaceResolver:
    def build_snapshot(
        self,
        lane_config: Mapping[str, Any],
        transcript_state: TranscriptState,
        provider_capabilities: Mapping[str, Any],
    ) -> ToolSurfaceSnapshot:
        descriptors = (
            {
                "name": "search_notes",
                "description": "Search the research fixture note index.",
                "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
            },
            {
                "name": "summarize_note",
                "description": "Summarize one research fixture note.",
                "input_schema": {"type": "object", "properties": {"note_id": {"type": "string"}}},
            },
        )
        route_records = tuple(
            {
                "declared_tool": descriptor["name"],
                "effective_tool": descriptor["name"],
                "tool_surface_profile_id": RESEARCH_FIXTURE_PROFILE_ID,
                "turn_item_count": transcript_state.item_count,
            }
            for descriptor in descriptors
        )
        return ToolSurfaceSnapshot(
            profile_id=RESEARCH_FIXTURE_PROFILE_ID,
            descriptors=descriptors,
            route_records=route_records,
            renderer_id="research_fixture_renderer",
            metadata={
                "lane_config_keys": sorted(str(key) for key in lane_config),
                "provider_capabilities": dict(provider_capabilities),
            },
        )


class _ResearchToolDispatcher:
    def dispatch(self, provider_call: Mapping[str, Any], runtime_context: LaneRuntimeContext) -> ToolResultEnvelope:
        call_id = str(provider_call.get("call_id") or "")
        tool_name = str(provider_call.get("tool_name") or "")
        arguments = provider_call.get("arguments") if isinstance(provider_call.get("arguments"), Mapping) else {}
        if tool_name == "search_notes":
            query = str(arguments.get("query") or "substrate proof")
            result = f"research note fixture: {query}"
            return ToolResultEnvelope(
                call_id=call_id,
                tool_name=tool_name,
                status="completed",
                provider_visible_text=result,
                evidence_refs=(f"research-evidence://{call_id}/note-search",),
                metadata={"query": query, "result_count": 1},
            )
        if tool_name == "summarize_note":
            note_id = str(arguments.get("note_id") or "fixture-note")
            return ToolResultEnvelope(
                call_id=call_id,
                tool_name=tool_name,
                status="completed",
                provider_visible_text=f"summary for {note_id}",
                evidence_refs=(f"research-evidence://{call_id}/summary",),
                metadata={"note_id": note_id},
            )
        return ToolResultEnvelope(
            call_id=call_id,
            tool_name=tool_name,
            status="invalid",
            is_error=True,
            provider_visible_text=f"unknown research fixture tool: {tool_name}",
        )


class _ResearchTranscriptStore:
    def __init__(self, lane_attempt_id: str) -> None:
        self._items: list[dict[str, Any]] = []
        self._pending_call_ids: list[str] = []
        self._state = TranscriptState(lane_attempt_id=lane_attempt_id)

    @property
    def state(self) -> TranscriptState:
        return self._state

    @property
    def items(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(dict(item) for item in self._items)

    def append_provider_items(self, items: Sequence[Mapping[str, Any]]) -> TranscriptAppendResult:
        for item in items:
            record = dict(item)
            self._items.append(record)
            if record.get("kind") == "tool_call":
                call_id = str(record.get("call_id") or "")
                if call_id:
                    self._pending_call_ids.append(call_id)
        response_id = "response:research-fixture:1" if items else self._state.response_id
        self._state = replace(
            self._state,
            turn_id="turn-research-1",
            response_id=response_id,
            item_count=len(self._items),
            pending_call_ids=tuple(self._pending_call_ids),
        )
        return TranscriptAppendResult(state=self._state)

    def append_tool_output(self, result: ToolResultEnvelope) -> TranscriptAppendResult:
        self._items.append(
            {
                "kind": "tool_output",
                "call_id": result.call_id,
                "tool_name": result.tool_name,
                "status": result.status,
                "text": result.provider_visible_text,
                "evidence_refs": list(result.evidence_refs),
            }
        )
        self._pending_call_ids = [call_id for call_id in self._pending_call_ids if call_id != result.call_id]
        self._state = replace(
            self._state,
            item_count=len(self._items),
            pending_call_ids=tuple(self._pending_call_ids),
        )
        return TranscriptAppendResult(state=self._state)

    def validate_pairing(self) -> ReplayValidationResult:
        call_ids = [str(item.get("call_id") or "") for item in self._items if item.get("kind") == "tool_call"]
        output_ids = [str(item.get("call_id") or "") for item in self._items if item.get("kind") == "tool_output"]
        errors = []
        for call_id in call_ids:
            if output_ids.count(call_id) != 1:
                errors.append(f"unpaired_call:{call_id}")
        for output_id in output_ids:
            if output_id not in call_ids:
                errors.append(f"orphan_output:{output_id}")
        return ReplayValidationResult(
            ok=not errors,
            checks={
                "tool_call_count": len(call_ids),
                "tool_output_count": len(output_ids),
                "pending_call_count": len(self._pending_call_ids),
            },
            errors=tuple(errors),
        )

    def write_response_transcript(self, artifact_root: Path) -> ArtifactRef:
        return _write_json_artifact(
            artifact_root / "response_transcript.json",
            {
                "lane_attempt_id": self._state.lane_attempt_id,
                "items": list(self.items),
                "pairing": self.validate_pairing().checks,
            },
            kind="response_transcript",
        )


class _ResearchArtifactWriter:
    def write_transcript(self, transcript_state: TranscriptState, artifact_root: Path) -> ArtifactRef:
        return _write_json_artifact(
            artifact_root / "transcript_state.json",
            _transcript_state_dict(transcript_state),
            kind="transcript_state",
        )

    def write_tool_results(self, results: Sequence[ToolResultEnvelope], artifact_root: Path) -> ArtifactRef:
        return _write_jsonl_artifact(
            artifact_root / "tool_results.jsonl",
            [_tool_result_dict(result) for result in results],
            kind="tool_results",
        )

    def write_provider_requests(
        self,
        descriptors: Sequence[ProviderRequestDescriptor],
        artifact_root: Path,
    ) -> ArtifactRef:
        return _write_jsonl_artifact(
            artifact_root / "provider_requests.jsonl",
            [_provider_request_dict(descriptor) for descriptor in descriptors],
            kind="provider_requests",
        )

    def write_route_records(self, snapshot: ToolSurfaceSnapshot, artifact_root: Path) -> ArtifactRef:
        return _write_jsonl_artifact(
            artifact_root / "tool_routes.jsonl",
            [dict(record) for record in snapshot.route_records],
            kind="tool_routes",
        )

    def write_proof_manifest(self, result: LaneRunResult, artifact_root: Path) -> ArtifactRef:
        manifest = {
            "lane_id": result.lane_id,
            "runtime_id": result.runtime_id,
            "status": result.status,
            "transcript_refs": [_artifact_ref_dict(ref) for ref in result.transcript_refs],
            "provider_request_refs": [_artifact_ref_dict(ref) for ref in result.provider_request_refs],
            "provider_response_refs": [_artifact_ref_dict(ref) for ref in result.provider_response_refs],
            "route_record_refs": [_artifact_ref_dict(ref) for ref in result.route_record_refs],
            "completion": result.completion.status if result.completion else "",
            "pairing_valid": bool(result.metadata.get("pairing_valid")),
        }
        return _write_json_artifact(artifact_root / "proof-manifest.json", manifest, kind="proof_manifest")

    def patch_manifest_sidecar_refs(self, manifest_ref: ArtifactRef, sidecar_refs: Sequence[ArtifactRef]) -> ArtifactRef:
        metadata = dict(manifest_ref.metadata)
        metadata["sidecar_refs"] = [_artifact_ref_dict(ref) for ref in sidecar_refs]
        return replace(manifest_ref, metadata=metadata)


class _ResearchObservabilityPolicy:
    def record_provider_request(self, descriptor: ProviderRequestDescriptor, artifact_root: Path) -> ArtifactRef:
        return _write_json_artifact(
            artifact_root / "provider_request_inventory.json",
            {
                "provider": descriptor.provider,
                "model": descriptor.model,
                "tool_count": len(descriptor.tool_descriptors),
                "request_id": descriptor.request_id,
            },
            kind="provider_request_inventory",
        )

    def record_provider_response(self, response_items: ProviderResponseItems, artifact_root: Path) -> ArtifactRef:
        return _write_json_artifact(
            artifact_root / "provider_response_inventory.json",
            {
                "response_id": response_items.response_id,
                "item_count": len(response_items.items),
            },
            kind="provider_response_inventory",
        )


class _ResearchCompletionPolicy:
    def maybe_build_done_candidate(self, transcript_state: TranscriptState) -> CompletionDecision:
        return CompletionDecision(
            status="candidate" if not transcript_state.pending_call_ids else "waiting_for_tools",
            done_candidate={"lane_attempt_id": transcript_state.lane_attempt_id},
        )

    def run_internal_closeout(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        return CompletionDecision(
            status="closed_out",
            sidecar_refs=(
                _write_json_artifact(
                    runtime_context.artifact_root / "research_closeout.json",
                    {"status": "closed_out", "lane_attempt_id": runtime_context.transcript_state.lane_attempt_id},
                    kind="research_closeout",
                ),
            ),
        )

    def resolve_completion(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        if runtime_context.transcript_state.pending_call_ids:
            return CompletionDecision(status="blocked", resume_signal={"reason": "pending_tool_calls"})
        return CompletionDecision(
            status="completed",
            sidecar_refs=(
                _write_json_artifact(
                    runtime_context.artifact_root / "research_completion.json",
                    {"status": "completed", "profile_id": runtime_context.tool_surface.profile_id},
                    kind="research_completion",
                ),
            ),
        )

    def build_resume_signal(self, runtime_context: LaneRuntimeContext) -> CompletionDecision:
        return CompletionDecision(status="resume", resume_signal={"pending": list(runtime_context.transcript_state.pending_call_ids)})


class _ResearchToolResultRenderer:
    def render(self, profile_id: str, result: ToolResultEnvelope) -> str:
        return f"[{profile_id}:{result.tool_name}:{result.status}] {result.provider_visible_text}"


class _ResearchReplayValidator:
    def validate(self, artifact_root: Path) -> ReplayValidationResult:
        manifest_path = artifact_root / "proof-manifest.json"
        transcript_path = artifact_root / "response_transcript.json"
        if not manifest_path.exists() or not transcript_path.exists():
            return ReplayValidationResult(ok=False, errors=("missing_manifest_or_transcript",))
        manifest = _read_json_object(manifest_path)
        transcript = _read_json_object(transcript_path)
        pairing = _validate_transcript_items(transcript.get("items") if isinstance(transcript, Mapping) else None)
        manifest_digest = _sha256(manifest_path.read_bytes())
        return ReplayValidationResult(
            ok=pairing.ok and manifest.get("pairing_valid") is True,
            checks={
                "manifest_exists": True,
                "transcript_exists": True,
                "pairing_valid": pairing.ok,
                "manifest_digest": f"sha256:{manifest_digest}",
            },
            errors=pairing.errors,
            artifact_refs=(ArtifactRef(kind="proof_manifest", path="proof-manifest.json", digest=f"sha256:{manifest_digest}"),),
        )


class ResearchFixtureRunner:
    """Tiny native-loop runner for the research fixture."""

    def run(
        self,
        spec: LaneRuntimeSpec,
        lane_input: LaneInput,
        provider: Any,
        artifact_root: Path,
        max_turns: int,
    ) -> LaneRunResult:
        del max_turns
        artifact_root.mkdir(parents=True, exist_ok=True)
        transcript_store = spec.transcript_store
        transcript_state = getattr(transcript_store, "state")
        tool_surface = spec.tool_surface_resolver.build_snapshot(
            lane_input.lane_config,
            transcript_state,
            {"native_tools": True},
        )
        descriptor = spec.provider_adapter.build_request_descriptor(lane_input, transcript_state, tool_surface)
        request_inventory_ref = spec.observability_policy.record_provider_request(descriptor, artifact_root)
        response = provider.respond(descriptor)
        response_items = spec.provider_adapter.parse_response_items(response)
        response_inventory_ref = spec.observability_policy.record_provider_response(response_items, artifact_root)
        transcript_store.append_provider_items(response_items.items)
        tool_results: list[ToolResultEnvelope] = []
        for item in response_items.items:
            if item.get("kind") != "tool_call":
                continue
            runtime_context = LaneRuntimeContext(
                lane_input=lane_input,
                artifact_root=artifact_root,
                transcript_state=getattr(transcript_store, "state"),
                tool_surface=tool_surface,
            )
            result = spec.tool_dispatcher.dispatch(item, runtime_context)
            if spec.tool_result_renderer is not None:
                result = replace(
                    result,
                    provider_visible_text=spec.tool_result_renderer.render(tool_surface.profile_id, result),
                )
            tool_results.append(result)
            transcript_store.append_tool_output(result)
        transcript_ref = transcript_store.write_response_transcript(artifact_root)
        state_ref = spec.artifact_writer.write_transcript(getattr(transcript_store, "state"), artifact_root)
        tool_results_ref = spec.artifact_writer.write_tool_results(tuple(tool_results), artifact_root)
        provider_requests_ref = spec.artifact_writer.write_provider_requests((descriptor,), artifact_root)
        route_records_ref = spec.artifact_writer.write_route_records(tool_surface, artifact_root)
        pairing = transcript_store.validate_pairing()
        completion_context = LaneRuntimeContext(
            lane_input=lane_input,
            artifact_root=artifact_root,
            transcript_state=getattr(transcript_store, "state"),
            tool_surface=tool_surface,
        )
        closeout = spec.completion_policy.run_internal_closeout(completion_context)
        completion = spec.completion_policy.resolve_completion(completion_context)
        completion = replace(completion, sidecar_refs=tuple((*closeout.sidecar_refs, *completion.sidecar_refs)))
        result = LaneRunResult(
            lane_id=spec.lane_id,
            runtime_id=spec.runtime_id,
            status=completion.status,
            transcript_refs=(transcript_ref, state_ref),
            provider_request_refs=(provider_requests_ref, request_inventory_ref),
            provider_response_refs=(response_inventory_ref,),
            route_record_refs=(route_records_ref,),
            completion=completion,
            metadata={
                "pairing_valid": pairing.ok,
                "tool_result_ref": _artifact_ref_dict(tool_results_ref),
            },
        )
        proof_ref = spec.artifact_writer.write_proof_manifest(result, artifact_root)
        return replace(result, proof_manifest_ref=proof_ref)


def build_research_fixture_spec() -> LaneRuntimeSpec:
    transcript_store = _ResearchTranscriptStore("research-fixture-attempt")
    return LaneRuntimeSpec(
        lane_id=RESEARCH_FIXTURE_LANE_ID,
        runtime_id=RESEARCH_FIXTURE_RUNTIME_ID,
        provider_adapter=_ResearchProviderAdapter(),
        tool_surface_resolver=_ResearchToolSurfaceResolver(),
        tool_dispatcher=_ResearchToolDispatcher(),
        transcript_store=transcript_store,
        artifact_writer=_ResearchArtifactWriter(),
        completion_policy=_ResearchCompletionPolicy(),
        observability_policy=_ResearchObservabilityPolicy(),
        tool_result_renderer=_ResearchToolResultRenderer(),
        replay_validator=_ResearchReplayValidator(),
        metadata={"fixture": True, "minimal_api": "LaneRuntimeSpec"},
    )


def run_research_fixture(artifact_root: str | Path, *, task: str = "Research substrate proof") -> LaneRunResult:
    spec = build_research_fixture_spec()
    lane_input = LaneInput(
        work_session_id="ws-research-fixture",
        task_id="task-research-fixture",
        workspace=str(Path(artifact_root).resolve(strict=False)),
        lane_config={"tool_profile": RESEARCH_FIXTURE_PROFILE_ID},
        task_contract={"description": task},
    )
    return ResearchFixtureRunner().run(
        spec,
        lane_input,
        provider=ResearchFixtureProvider(),
        artifact_root=Path(artifact_root),
        max_turns=1,
    )


def validate_research_fixture_artifacts(artifact_root: str | Path) -> ReplayValidationResult:
    return _ResearchReplayValidator().validate(Path(artifact_root))


def _validate_transcript_items(items: object) -> ReplayValidationResult:
    if not isinstance(items, list):
        return ReplayValidationResult(ok=False, errors=("transcript_items_not_list",))
    call_ids = [str(item.get("call_id") or "") for item in items if isinstance(item, Mapping) and item.get("kind") == "tool_call"]
    output_ids = [
        str(item.get("call_id") or "") for item in items if isinstance(item, Mapping) and item.get("kind") == "tool_output"
    ]
    errors = []
    for call_id in call_ids:
        if output_ids.count(call_id) != 1:
            errors.append(f"unpaired_call:{call_id}")
    for output_id in output_ids:
        if output_id not in call_ids:
            errors.append(f"orphan_output:{output_id}")
    return ReplayValidationResult(
        ok=not errors,
        checks={"tool_call_count": len(call_ids), "tool_output_count": len(output_ids)},
        errors=tuple(errors),
    )


def _write_json_artifact(path: Path, payload: Mapping[str, Any], *, kind: str) -> ArtifactRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    path.write_bytes(data)
    return ArtifactRef(kind=kind, path=path.name, digest=f"sha256:{_sha256(data)}")


def _write_jsonl_artifact(path: Path, rows: Sequence[Mapping[str, Any]], *, kind: str) -> ArtifactRef:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(dict(row), sort_keys=True) + "\n" for row in rows)
    data = text.encode("utf-8")
    path.write_bytes(data)
    return ArtifactRef(kind=kind, path=path.name, digest=f"sha256:{_sha256(data)}", metadata={"row_count": len(rows)})


def _read_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(value) if isinstance(value, Mapping) else {}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _artifact_ref_dict(ref: ArtifactRef) -> dict[str, Any]:
    return {
        "kind": ref.kind,
        "path": ref.path,
        "digest": ref.digest,
        "metadata": dict(ref.metadata),
    }


def _provider_request_dict(descriptor: ProviderRequestDescriptor) -> dict[str, Any]:
    return {
        "provider": descriptor.provider,
        "model": descriptor.model,
        "request_id": descriptor.request_id,
        "items": [dict(item) for item in descriptor.items],
        "tool_descriptors": [dict(item) for item in descriptor.tool_descriptors],
        "metadata": dict(descriptor.metadata),
    }


def _tool_result_dict(result: ToolResultEnvelope) -> dict[str, Any]:
    return {
        "call_id": result.call_id,
        "tool_name": result.tool_name,
        "status": result.status,
        "is_error": result.is_error,
        "provider_visible_text": result.provider_visible_text,
        "evidence_refs": list(result.evidence_refs),
        "metadata": dict(result.metadata),
    }


def _transcript_state_dict(state: TranscriptState) -> dict[str, Any]:
    return {
        "lane_attempt_id": state.lane_attempt_id,
        "turn_id": state.turn_id,
        "response_id": state.response_id,
        "item_count": state.item_count,
        "pending_call_ids": list(state.pending_call_ids),
    }
