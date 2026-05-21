"""Diagnostic-only legacy finish acceptance bridge for old model-JSON replay."""

from __future__ import annotations

from ..acceptance import acceptance_done_gate_decision
from ..implement_lane.finish_acceptance_helpers import (
    _acceptance_tool_call_from_result,
    _finish_action_evidence_ref_items,
    _finish_outcome,
    _live_task_description,
    _merge_finish_acceptance_sidecar_checks,
    _merge_finish_action_evidence_refs,
    _source_grounding_finish_acceptance_checks,
    _structured_finish_acceptance_checks,
    _synthetic_finish_acceptance_checks,
    _typed_finish_evidence_refs,
    _with_finish_evidence_refs,
    finish_typed_evidence_snapshot_from_tool_results,
)
from ..implement_lane.types import ImplementLaneInput, ToolResultEnvelope


_COMPLETED_FINISH_OUTCOMES = {"completed", "task_complete", "done", "success"}


def _finish_acceptance_action(
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    task_description: str = "",
) -> dict[str, object]:
    action = dict(finish_arguments or {})
    action["task_done"] = _finish_outcome(action) in _COMPLETED_FINISH_OUTCOMES
    checks = action.get("acceptance_checks")
    acceptance_checks: list[object] = []
    if isinstance(checks, list):
        acceptance_checks = [
            _with_finish_evidence_refs(check, tool_results) if isinstance(check, dict) else check for check in checks
        ]
    if not acceptance_checks:
        acceptance_checks = _synthetic_finish_acceptance_checks(action, tool_results)
    sidecar_checks = [
        *_structured_finish_acceptance_checks(tool_results),
        *_source_grounding_finish_acceptance_checks(task_description, tool_results),
    ]
    acceptance_checks = _merge_finish_acceptance_sidecar_checks(acceptance_checks, sidecar_checks)
    action["acceptance_checks"] = acceptance_checks
    existing_refs = _finish_action_evidence_ref_items(action.get("evidence_refs") or action.get("evidence_ref"))
    typed_refs = _typed_finish_evidence_refs(
        tool_results,
        task_description=task_description,
        include_supplemental=not existing_refs,
    )
    merged_refs = _merge_finish_action_evidence_refs(existing_refs, typed_refs)
    if merged_refs:
        action["evidence_refs"] = merged_refs
    return action


def finish_acceptance_gate_decision(
    lane_input: ImplementLaneInput,
    finish_arguments: dict[str, object],
    tool_results: tuple[ToolResultEnvelope, ...],
) -> dict[str, object]:
    task_description = _live_task_description(lane_input)
    action = _finish_acceptance_action(
        finish_arguments,
        tool_results,
        task_description=task_description,
    )
    return acceptance_done_gate_decision(
        task_description,
        action,
        session=_acceptance_session_from_tool_results(tool_results, lane_input=lane_input),
    )


def _acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    session: dict[str, object] = {
        "tool_calls": [
            _acceptance_tool_call_from_result(index, result) for index, result in enumerate(tool_results, start=1)
        ]
    }
    typed_acceptance = _typed_acceptance_session_from_tool_results(tool_results, lane_input=lane_input)
    if typed_acceptance:
        session["typed_acceptance"] = typed_acceptance
    if lane_input is not None and isinstance(lane_input.task_contract, dict):
        compiler = lane_input.task_contract.get("task_contract_compiler")
        if isinstance(compiler, dict):
            session["task_contract_compiler"] = dict(compiler)
    return session


def _typed_acceptance_session_from_tool_results(
    tool_results: tuple[ToolResultEnvelope, ...],
    *,
    lane_input: ImplementLaneInput | None = None,
) -> dict[str, object]:
    return finish_typed_evidence_snapshot_from_tool_results(tool_results, lane_input=lane_input)


__all__ = [
    "_acceptance_session_from_tool_results",
    "_finish_acceptance_action",
    "_typed_acceptance_session_from_tool_results",
    "finish_acceptance_gate_decision",
]
