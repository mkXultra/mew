"""Transition-contract WorkFrame reducer variant for implement_v2.

This variant is deliberately a schema-compatible wrapper around the current
WorkFrame reducer. It adds a compact reducer-owned transition contract only
when the latest sidecar observation changes reducer state.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .workframe import (
    WorkFrame,
    WorkFrameInputs,
    WorkFrameInvariantReport,
    WorkFrameLatestActionable,
    WorkFrameRequiredNext,
    canonicalize_workframe_inputs,
    reduce_workframe,
    validate_workframe,
    workframe_output_hash,
)

VARIANT_NAME = "transition_contract"

_MAX_CONTRACT_REFS = 10
_MAX_CONTRACT_PATHS = 8
_MAX_SUMMARY_CHARS = 180
_MAX_REASON_CHARS = 420
_MAX_AFTER_CHARS = 360


def reduce_transition_contract_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce inputs and annotate state-changing observations with a contract."""

    workframe, base_report = reduce_workframe(inputs)
    events = _canonical_sidecar_events(inputs)
    if not events:
        return workframe, base_report

    latest_event = events[-1]
    previous_workframe, _previous_report = reduce_workframe(replace(inputs, sidecar_events=events[:-1]))
    if not _workframe_state_changed(previous_workframe, workframe):
        return workframe, base_report

    contract = _transition_contract(
        workframe=workframe,
        previous_workframe=previous_workframe,
        latest_event=latest_event,
    )
    updated = _apply_transition_contract(workframe, contract)
    updated = replace(updated, trace=replace(updated.trace, output_hash=workframe_output_hash(updated)))
    return updated, validate_workframe(updated, inputs=inputs)


def _canonical_sidecar_events(inputs: WorkFrameInputs) -> tuple[dict[str, object], ...]:
    canonical = canonicalize_workframe_inputs(inputs)
    payload = _mapping(canonical.get("payload"))
    events = payload.get("sidecar_events")
    if not isinstance(events, list):
        return ()
    return tuple(dict(event) for event in events if isinstance(event, dict))


def _workframe_state_changed(previous: WorkFrame, current: WorkFrame) -> bool:
    return _state_payload(previous) != _state_payload(current)


def _state_payload(workframe: WorkFrame) -> dict[str, object]:
    payload = workframe.as_dict()
    return {
        "current_phase": payload.get("current_phase"),
        "latest_actionable": payload.get("latest_actionable"),
        "required_next": payload.get("required_next"),
        "forbidden_next": payload.get("forbidden_next"),
        "changed_sources": payload.get("changed_sources"),
        "verifier_state": payload.get("verifier_state"),
        "finish_readiness": payload.get("finish_readiness"),
    }


def _transition_contract(
    *,
    workframe: WorkFrame,
    previous_workframe: WorkFrame,
    latest_event: dict[str, object],
) -> dict[str, object]:
    latest_refs = _event_evidence_refs(latest_event)
    current_refs = _workframe_evidence_refs(workframe)
    previous_refs = set(_workframe_evidence_refs(previous_workframe))
    new_refs = tuple(ref for ref in current_refs if ref not in previous_refs)
    provenance_refs = _stable_values(
        workframe.required_next.evidence_refs if workframe.required_next else (),
        latest_refs,
        (workframe.changed_sources.latest_mutation_ref,),
        new_refs,
    )
    rule_id, reason = _transition_rule(
        previous_phase=previous_workframe.current_phase,
        current_phase=workframe.current_phase,
        latest_event=latest_event,
    )
    latest_observation = {
        "source_ref": _event_ref(latest_event),
        "kind": _event_kind(latest_event),
        "status": _event_status(latest_event),
        "summary": _clip_text(_event_summary(latest_event), _MAX_SUMMARY_CHARS),
        "evidence_refs": list(_stable_values(latest_refs)),
    }
    sequence = _event_sequence(latest_event)
    if sequence >= 0:
        latest_observation["sequence"] = sequence

    evidence_delta: dict[str, object] = {
        "new_refs": list(_stable_values(new_refs, latest_refs)),
    }
    if workframe.changed_sources.latest_mutation_ref:
        evidence_delta["latest_mutation_ref"] = workframe.changed_sources.latest_mutation_ref
    if workframe.verifier_state.last_strict_verifier_ref:
        evidence_delta["latest_verifier_ref"] = workframe.verifier_state.last_strict_verifier_ref

    return {
        "latest_observation": latest_observation,
        "evidence_delta": evidence_delta,
        "state_transition": {
            "from_phase": previous_workframe.current_phase,
            "to_phase": workframe.current_phase,
            "rule_id": rule_id,
            "reason": reason,
            "provenance_refs": list(_stable_values(provenance_refs)),
        },
        "next_action_contract": _next_action_contract(workframe.required_next, provenance_refs),
    }


def _transition_rule(
    *,
    previous_phase: str,
    current_phase: str,
    latest_event: dict[str, object],
) -> tuple[str, str]:
    event_kind = _event_kind(latest_event)
    event_status = _event_status(latest_event)
    if (
        previous_phase == "verify_after_mutation"
        and current_phase == "repair_after_verifier_failure"
        and event_status in {"failed", "interrupted", "invalid"}
        and event_kind in {"strict_verifier", "verifier", "run_tests", "verifier_result"}
    ):
        return (
            "transition_contract.verifier_failure_after_mutation",
            "fresh verifier failure supersedes post-mutation verification and requires repair before finish",
        )
    if current_phase == "verify_after_mutation":
        return (
            "transition_contract.source_mutation_requires_verifier",
            "source mutation invalidates finish readiness until the configured verifier passes",
        )
    if current_phase == "repair_after_write_failure":
        return (
            "transition_contract.write_failure_requires_repair",
            "failed source mutation must be repaired before verifier or finish",
        )
    if current_phase == "repair_after_verifier_failure":
        return (
            "transition_contract.verifier_failure_requires_repair",
            "latest verifier failure requires one focused repair before finish",
        )
    if current_phase == "finish_ready":
        return (
            "transition_contract.fresh_verifier_allows_finish",
            "fresh passing verifier evidence satisfies finish readiness",
        )
    if current_phase == "finish_blocked":
        return (
            "transition_contract.finish_blocked_by_obligation",
            "finish remains blocked until missing obligations are evidenced",
        )
    if previous_phase != current_phase:
        return (
            f"transition_contract.{previous_phase}_to_{current_phase}",
            "latest observation changed WorkFrame phase",
        )
    return (
        "transition_contract.state_refresh",
        "latest observation changed WorkFrame state without changing phase",
    )


def _next_action_contract(
    required_next: WorkFrameRequiredNext | None,
    provenance_refs: tuple[str, ...],
) -> dict[str, object]:
    if required_next is None:
        return {}
    return {
        "kind": required_next.kind,
        "reason": _clip_text(required_next.reason, _MAX_REASON_CHARS),
        "target_paths": list(_stable_values(required_next.target_paths, limit=_MAX_CONTRACT_PATHS)),
        "after": required_next.after,
        "evidence_refs": list(_stable_values(required_next.evidence_refs, provenance_refs)),
        "inspection_target_paths": list(
            _stable_values(required_next.inspection_target_paths, limit=_MAX_CONTRACT_PATHS)
        ),
        "inspection_evidence_refs": list(_stable_values(required_next.inspection_evidence_refs)),
    }


def _apply_transition_contract(workframe: WorkFrame, contract: dict[str, object]) -> WorkFrame:
    required_next = _apply_required_next_contract(workframe.required_next, contract)
    latest_actionable = _apply_latest_actionable_contract(workframe.latest_actionable, contract)
    return replace(workframe, latest_actionable=latest_actionable, required_next=required_next)


def _apply_latest_actionable_contract(
    latest_actionable: WorkFrameLatestActionable | None,
    contract: dict[str, object],
) -> WorkFrameLatestActionable | None:
    if latest_actionable is None:
        return None
    recovery_hint = dict(latest_actionable.recovery_hint)
    recovery_hint["transition_contract"] = contract
    return replace(latest_actionable, recovery_hint=recovery_hint)


def _apply_required_next_contract(
    required_next: WorkFrameRequiredNext | None,
    contract: dict[str, object],
) -> WorkFrameRequiredNext | None:
    if required_next is None:
        return None
    transition = _mapping(contract.get("state_transition"))
    rule_id = str(transition.get("rule_id") or "").strip()
    provenance_refs = _stable_values(_list_value(transition.get("provenance_refs")))
    evidence_refs = _stable_values(required_next.evidence_refs, provenance_refs)
    reason = _contract_reason(required_next.reason, rule_id)
    after = _contract_after(required_next, rule_id=rule_id, provenance_refs=provenance_refs)
    return replace(required_next, reason=reason, after=after, evidence_refs=evidence_refs)


def _contract_reason(reason: str, rule_id: str) -> str:
    if not rule_id or f"transition_rule={rule_id}" in reason:
        return reason
    return _clip_text(f"{reason}; transition_rule={rule_id}", _MAX_REASON_CHARS)


def _contract_after(
    required_next: WorkFrameRequiredNext,
    *,
    rule_id: str,
    provenance_refs: tuple[str, ...],
) -> str:
    if required_next.kind == "finish" and not required_next.after:
        return required_next.after
    base_after = required_next.after or _default_after(required_next.kind)
    if not rule_id:
        return base_after
    details = f"transition_rule={rule_id}"
    if provenance_refs:
        details = f"{details}; provenance_refs={','.join(provenance_refs)}"
    if not base_after:
        return _clip_text(details, _MAX_AFTER_CHARS)
    if details in base_after:
        return base_after
    return _clip_text(f"{base_after}; {details}", _MAX_AFTER_CHARS)


def _default_after(kind: str) -> str:
    if kind == "patch_or_edit":
        return "run_configured_verifier"
    if kind == "run_verifier":
        return "finish_or_block"
    if kind == "inspect_latest_failure":
        return "patch_or_edit_or_block"
    return ""


def _workframe_evidence_refs(workframe: WorkFrame) -> tuple[str, ...]:
    return _stable_values(
        workframe.evidence_refs.typed,
        workframe.evidence_refs.sidecar,
        workframe.evidence_refs.replay,
    )


def _event_evidence_refs(event: dict[str, object]) -> tuple[str, ...]:
    refs: list[object] = []
    for key in ("evidence_ref", "event_ref", "command_run_id", "typed_evidence_id", "id", "event_id"):
        refs.append(event.get(key))
    refs.extend(_list_value(event.get("evidence_refs")))
    contract = _mapping(event.get("execution_contract"))
    contract.update(_mapping(event.get("execution_contract_normalized")))
    refs.append(contract.get("id") or contract.get("contract_id") or event.get("contract_id"))
    oracle = _mapping(event.get("oracle_bundle"))
    refs.append(oracle.get("id"))
    finish_gate = _mapping(event.get("finish_gate"))
    refs.append(finish_gate.get("id") or finish_gate.get("finish_gate_id"))
    return tuple(sorted(set(_stable_values(refs, limit=100))))


def _event_ref(event: dict[str, object]) -> str:
    for key in ("evidence_ref", "event_ref", "command_run_id", "typed_evidence_id", "id"):
        value = str(event.get(key) or "").strip()
        if value:
            return value
    for value in _list_value(event.get("evidence_refs")):
        text = str(value or "").strip()
        if text:
            return text
    return str(event.get("event_id") or "").strip()


def _event_kind(event: dict[str, object]) -> str:
    return str(event.get("kind") or event.get("type") or event.get("event_kind") or "").strip()


def _event_status(event: dict[str, object]) -> str:
    status = str(event.get("status") or event.get("outcome") or "").lower().strip()
    if status in {"pass", "passed", "success", "succeeded", "completed"}:
        return "passed"
    if status in {"fail", "failed", "failure", "nonzero", "rejected"}:
        return "failed"
    if status in {"interrupted", "killed", "timeout"}:
        return "interrupted"
    if status in {"invalid", "denied"}:
        return "invalid"
    return status or "unknown"


def _event_sequence(event: dict[str, object]) -> int:
    for key in ("event_sequence", "sequence"):
        try:
            value = event.get(key)
            if value is None or value == "":
                continue
            return int(value)
        except (TypeError, ValueError):
            continue
    return -1


def _event_summary(event: dict[str, object]) -> str:
    for key in ("summary", "message", "failure_summary", "reason", "stderr_tail", "stdout_tail", "diagnostic"):
        value = str(event.get(key) or "").strip()
        if value:
            return value
    return _event_status(event)


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _list_value(value: object) -> tuple[object, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(value)
    if value in (None, ""):
        return ()
    return (value,)


def _stable_values(*groups: Iterable[object], limit: int = _MAX_CONTRACT_REFS) -> tuple[str, ...]:
    values: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            values.append(text)
            if len(values) >= limit:
                return tuple(values)
    return tuple(values)


def _clip_text(value: object, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


__all__ = ["VARIANT_NAME", "reduce_transition_contract_workframe"]
