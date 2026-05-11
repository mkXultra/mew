"""Transcript-tool navigation WorkFrame reducer variant for implement_v2."""

from __future__ import annotations

from dataclasses import replace

from .tool_policy import list_v2_base_tool_specs
from .workframe import (
    WorkFrame,
    WorkFrameForbiddenNext,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    WorkFrameRequiredNext,
    reduce_workframe,
    validate_workframe,
    workframe_output_hash,
)

VARIANT_NAME = "transcript_tool_nav"
_MAX_RECOMMENDED_TOOLS = 4
_MAX_DISABLED_TOOLS = 6


def reduce_transcript_tool_nav_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Project a transcript-authoritative WorkFrame with compact tool navigation.

    The underlying reducer still owns safety, verifier freshness, finish
    readiness, and evidence extraction. This variant only weakens ordinary
    repair `required_next` into advisory tool navigation while keeping
    controller-required transitions strict.
    """

    workframe, _base_report = reduce_workframe(inputs)
    required_next = _controller_required_next(workframe)
    tool_context = _tool_context(workframe, inputs=inputs, required_next=required_next)
    obligations = _obligations(workframe)
    repair_loop = _repair_loop(workframe, inputs=inputs)
    projected = replace(
        workframe,
        schema_version=3,
        required_next=required_next,
        variant={
            "name": VARIANT_NAME,
            "schema_version": 1,
            "policy": "natural_transcript_tool_navigation",
            "required_next_policy": "controller_required_only",
        },
        tool_context=tool_context,
        obligations=obligations,
        repair_loop=repair_loop,
    )
    projected = replace(projected, trace=replace(projected.trace, output_hash=workframe_output_hash(projected)))
    return projected, validate_workframe(projected, inputs=inputs)


def _controller_required_next(workframe: WorkFrame) -> WorkFrameRequiredNext | None:
    required_next = workframe.required_next
    if required_next is None:
        return None
    if required_next.kind == "finish":
        return required_next if workframe.finish_readiness.state == "ready" else None
    if required_next.kind == "blocked":
        return required_next
    if required_next.kind == "run_verifier":
        if workframe.finish_readiness.state == "blocked" and workframe.finish_readiness.missing_obligations:
            return required_next
        if workframe.verifier_state.budget_closeout_required:
            return required_next
        if workframe.changed_sources.since_last_strict_verifier and not _ordinary_repair_failure_present(workframe):
            return required_next
    return None


def _ordinary_repair_failure_present(workframe: WorkFrame) -> bool:
    return bool(
        workframe.latest_actionable
        and workframe.latest_actionable.generic_family
        not in {"", "verifier_stale_after_mutation", "missing_passing_verifier"}
    )


def _tool_context(
    workframe: WorkFrame,
    *,
    inputs: WorkFrameInputs,
    required_next: WorkFrameRequiredNext | None,
) -> dict[str, object]:
    active_refs = _active_tool_refs(inputs)
    recommended = _recommended_tool_refs(workframe, required_next=required_next, active_refs=active_refs)
    disabled = _disabled_tool_refs(workframe, active_refs=active_refs)
    return {
        "schema_version": 1,
        "registry_ref": _metric_string(inputs, "tool_registry_ref"),
        "registry_hash": _metric_string(inputs, "tool_registry_hash"),
        "active_tool_refs": list(active_refs),
        "recommended_tool_refs": recommended[:_MAX_RECOMMENDED_TOOLS],
        "disabled_tool_refs": disabled[:_MAX_DISABLED_TOOLS],
        "policy_refs": ["tool-policy:mutation-boundary:v1", "tool-policy:finish-safety:v1"],
        "fetchable_refs": _fetchable_refs(workframe),
        "tool_result_search": {
            "index_ref": _metric_string(inputs, "tool_result_index_ref"),
            "primary": True,
            "query_hints": ["call_id", "tool_ref", "target_path", "output_ref"],
        },
        "model_turn_search": {
            "index_ref": _metric_string(inputs, "model_turn_index_ref"),
            "usage": "debug_plateau_recovery_only",
        },
    }


def _recommended_tool_refs(
    workframe: WorkFrame,
    *,
    required_next: WorkFrameRequiredNext | None,
    active_refs: tuple[str, ...],
) -> list[dict[str, object]]:
    base_required = workframe.required_next
    if base_required is None:
        return []
    if required_next and required_next.kind == base_required.kind:
        return []
    evidence_refs = _current_evidence_refs(workframe)
    entries: list[dict[str, object]] = []
    if base_required.kind in {"cheap_probe", "inspect_latest_failure"}:
        entries.extend(
            _recommend(
                active_refs,
                ("read_file", "search_text", "run_command"),
                reason="latest result supports bounded source or output inspection before mutation",
                evidence_refs=evidence_refs,
            )
        )
    elif base_required.kind == "patch_or_edit":
        entries.extend(
            _recommend(
                active_refs,
                ("apply_patch", "edit_file", "write_file", "read_file"),
                reason="latest result is actionable; inspect if needed, then apply a coherent source mutation",
                evidence_refs=evidence_refs,
            )
        )
    elif base_required.kind == "run_verifier":
        entries.extend(
            _recommend(
                active_refs,
                ("run_tests", "run_command"),
                reason="fresh verifier evidence is needed after the latest mutation or obligation state",
                evidence_refs=evidence_refs,
            )
        )
    return _dedupe_tool_entries(entries)


def _disabled_tool_refs(workframe: WorkFrame, *, active_refs: tuple[str, ...]) -> list[dict[str, object]]:
    evidence_refs = _current_evidence_refs(workframe)
    disabled: list[dict[str, object]] = []
    if workframe.finish_readiness.state != "ready" and "tool:finish" in active_refs:
        clear_refs = list(workframe.finish_readiness.required_evidence_refs or evidence_refs)
        disabled.append(
            {
                "tool_ref": "tool:finish",
                "reason": "finish requires fresh accepted verifier evidence and satisfied obligations",
                "until_evidence_refs": clear_refs,
            }
        )
    if workframe.changed_sources.since_last_strict_verifier:
        disabled.append(
            {
                "tool_ref": "action:finish",
                "reason": "source changed after the latest strict verifier",
                "until_evidence_refs": list(workframe.finish_readiness.required_evidence_refs or evidence_refs),
            }
        )
    for item in workframe.forbidden_next:
        disabled.append(_disabled_from_forbidden_next(item))
    return _dedupe_tool_entries(disabled)


def _disabled_from_forbidden_next(item: WorkFrameForbiddenNext) -> dict[str, object]:
    tool_ref = "tool:finish" if item.kind == "finish" else f"action:{item.kind}"
    return {
        "tool_ref": tool_ref,
        "reason": item.reason,
        "until_evidence_refs": list(item.evidence_refs),
    }


def _recommend(
    active_refs: tuple[str, ...],
    tool_names: tuple[str, ...],
    *,
    reason: str,
    evidence_refs: tuple[str, ...],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for name in tool_names:
        tool_ref = f"tool:{name}"
        if tool_ref not in active_refs:
            continue
        entries.append(
            {
                "tool_ref": tool_ref,
                "reason": reason,
                "evidence_refs": list(evidence_refs),
            }
        )
    return entries


def _dedupe_tool_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    by_ref: dict[str, dict[str, object]] = {}
    for entry in entries:
        tool_ref = str(entry.get("tool_ref") or "")
        if not tool_ref:
            continue
        if tool_ref not in by_ref:
            by_ref[tool_ref] = dict(entry)
            continue
        existing_refs = list(by_ref[tool_ref].get("evidence_refs") or by_ref[tool_ref].get("until_evidence_refs") or [])
        incoming_refs = list(entry.get("evidence_refs") or entry.get("until_evidence_refs") or [])
        merged_refs = list(dict.fromkeys([str(ref) for ref in existing_refs + incoming_refs if str(ref)]))
        if "evidence_refs" in by_ref[tool_ref]:
            by_ref[tool_ref]["evidence_refs"] = merged_refs
        else:
            by_ref[tool_ref]["until_evidence_refs"] = merged_refs
    return list(by_ref.values())


def _obligations(workframe: WorkFrame) -> dict[str, object]:
    missing = list(workframe.finish_readiness.missing_obligations)
    return {
        "schema_version": 1,
        "artifact_obligation_refs": missing,
        "missing_or_stale_refs": missing,
        "finish_blockers": list(workframe.finish_readiness.blockers),
    }


def _repair_loop(workframe: WorkFrame, *, inputs: WorkFrameInputs) -> dict[str, object]:
    state = "none"
    if any(item.kind == "broad_rediscovery" for item in workframe.forbidden_next):
        state = "warn"
    if workframe.finish_readiness.state == "blocked":
        state = "blocked"
    return {
        "schema_version": 1,
        "state": state,
        "signature_ref": _latest_event_ref(inputs),
        "disabled_action_families": [
            item.kind for item in workframe.forbidden_next if item.kind != "finish"
        ],
    }


def _current_evidence_refs(workframe: WorkFrame) -> tuple[str, ...]:
    refs: list[str] = []
    if workframe.latest_actionable:
        refs.append(workframe.latest_actionable.source_ref)
        refs.extend(workframe.latest_actionable.evidence_refs)
    refs.extend(workframe.evidence_refs.typed)
    refs.extend(workframe.evidence_refs.sidecar)
    return tuple(dict.fromkeys(ref for ref in refs if ref))


def _fetchable_refs(workframe: WorkFrame) -> list[str]:
    refs = _current_evidence_refs(workframe)
    return [ref for ref in refs if ref.startswith(("out:", "cmd:", "tool-result:"))][:4]


def _active_tool_refs(inputs: WorkFrameInputs) -> tuple[str, ...]:
    names = inputs.baseline_metrics.get("provider_tool_names")
    if not isinstance(names, list) or not names:
        names = [spec.name for spec in list_v2_base_tool_specs()]
    refs = [f"tool:{name}" for name in names if str(name)]
    return tuple(dict.fromkeys(refs))


def _metric_string(inputs: WorkFrameInputs, key: str) -> str:
    value = inputs.baseline_metrics.get(key)
    return value if isinstance(value, str) else ""


def _latest_event_ref(inputs: WorkFrameInputs) -> str:
    for event in reversed(inputs.sidecar_events):
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("event_id") or event.get("id") or "").strip()
        if event_id:
            return event_id
    return ""


__all__ = ["VARIANT_NAME", "reduce_transcript_tool_nav_workframe"]
