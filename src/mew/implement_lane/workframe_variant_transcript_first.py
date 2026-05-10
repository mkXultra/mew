"""Transcript-first WorkFrame reducer variant for implement_v2 experiments."""

from __future__ import annotations

from dataclasses import replace

from .workframe import (
    WorkFrame,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    reduce_workframe,
    validate_workframe,
    workframe_output_hash,
)

VARIANT_NAME = "transcript_first"


def reduce_transcript_first_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce WorkFrame inputs with transcript/tool results as short-horizon authority.

    This variant preserves the current reducer for schema, finish readiness, and
    invariant enforcement. It only replaces short-horizon action selection when
    the current frame is driven by prompt-projection fallback despite concrete
    runtime/tool sidecar evidence being available in the same input.
    """

    current_workframe, current_report = reduce_workframe(inputs)
    prompt_events = tuple(event for event in inputs.sidecar_events if _is_prompt_projection_event(event))
    transcript_events = tuple(event for event in inputs.sidecar_events if _is_transcript_sidecar_event(event))
    if not prompt_events or not transcript_events:
        return current_workframe, current_report
    if not _short_horizon_has_prompt_projection(current_workframe):
        return current_workframe, current_report

    transcript_inputs = replace(
        inputs,
        sidecar_events=tuple(event for event in inputs.sidecar_events if not _is_prompt_projection_event(event)),
    )
    transcript_workframe, _transcript_report = reduce_workframe(transcript_inputs)
    if not _should_use_transcript_short_horizon(current_workframe, transcript_workframe):
        return current_workframe, current_report

    adjusted = replace(
        current_workframe,
        current_phase=transcript_workframe.current_phase,
        latest_actionable=transcript_workframe.latest_actionable,
        required_next=transcript_workframe.required_next,
        forbidden_next=transcript_workframe.forbidden_next,
    )
    adjusted = replace(adjusted, trace=replace(adjusted.trace, output_hash=workframe_output_hash(adjusted)))
    return adjusted, validate_workframe(adjusted, inputs=inputs)


def _should_use_transcript_short_horizon(current: WorkFrame, transcript: WorkFrame) -> bool:
    if current.finish_readiness.state == "blocked":
        return False
    if current.finish_readiness.state == "ready" and transcript.finish_readiness.state != "ready":
        return False
    if transcript.required_next and transcript.required_next.kind == "finish":
        return current.finish_readiness.state == "ready"
    return _short_horizon_has_transcript_sidecar(transcript)


def _short_horizon_has_prompt_projection(workframe: WorkFrame) -> bool:
    return any(_is_prompt_projection_ref(ref) for ref in _short_horizon_refs(workframe))


def _short_horizon_has_transcript_sidecar(workframe: WorkFrame) -> bool:
    return any(_is_transcript_sidecar_ref(ref) for ref in _short_horizon_refs(workframe))


def _short_horizon_refs(workframe: WorkFrame) -> tuple[str, ...]:
    refs: list[str] = []
    if workframe.latest_actionable:
        refs.append(workframe.latest_actionable.source_ref)
        refs.extend(workframe.latest_actionable.evidence_refs)
    if workframe.required_next:
        refs.extend(workframe.required_next.evidence_refs)
        refs.extend(workframe.required_next.inspection_evidence_refs)
    return tuple(ref for ref in refs if ref)


def _is_prompt_projection_event(event: object) -> bool:
    if not isinstance(event, dict):
        return False
    event_id = str(event.get("event_id") or event.get("id") or "").strip()
    if event_id.startswith("prompt-"):
        return True
    refs = _event_refs(event)
    return bool(refs) and all(_is_prompt_projection_ref(ref) for ref in refs)


def _is_transcript_sidecar_event(event: object) -> bool:
    if not isinstance(event, dict) or _is_prompt_projection_event(event):
        return False
    event_id = str(event.get("event_id") or event.get("id") or "").strip()
    if event_id.startswith("tool-result:"):
        return True
    if str(event.get("provider_call_id") or "").strip() or str(event.get("tool_name") or "").strip():
        return True
    return any(_is_transcript_sidecar_ref(ref) for ref in _event_refs(event))


def _event_refs(event: dict[str, object]) -> tuple[str, ...]:
    refs: list[str] = []
    for key in ("evidence_ref", "event_ref", "command_run_id", "typed_evidence_id", "id", "event_id"):
        value = str(event.get(key) or "").strip()
        if value:
            refs.append(value)
    raw_refs = event.get("evidence_refs")
    if isinstance(raw_refs, (list, tuple)):
        refs.extend(str(item).strip() for item in raw_refs if str(item).strip())
    return tuple(dict.fromkeys(refs))


def _is_prompt_projection_ref(ref: str) -> bool:
    return ref.startswith("wf:") or ref.startswith("prompt-")


def _is_transcript_sidecar_ref(ref: str) -> bool:
    return ref.startswith(("tool-result:", "ev:", "cmd:", "sidecar:"))


__all__ = ["VARIANT_NAME", "reduce_transcript_first_workframe"]
