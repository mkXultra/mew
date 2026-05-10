"""Transition-contract WorkFrame reducer variant for implement_v2.

This variant is deliberately a schema-compatible wrapper around the current
WorkFrame reducer. It adds a compact reducer-owned transition contract only
when the latest sidecar observation changes reducer state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import replace
from typing import Iterable

from .workframe import (
    WorkFrame,
    WorkFrameForbiddenNext,
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
_RUNTIME_ARTIFACT_REPEAT_BUDGET = 3


@dataclass(frozen=True)
class _RuntimeArtifactFailure:
    event: dict[str, object]
    sequence: int
    family: str
    subfamily: str
    status: str
    artifact_path: str
    failed_checks: tuple[str, ...]
    command_run_id: str
    verifier_id: str
    artifact_evidence_id: str
    producer_paths: tuple[str, ...]
    latest_mutation_ref: str
    latest_mutation_sequence: int
    observable_progress: bool
    repeat_key: str
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True)
class _RuntimeArtifactDecision:
    failure: _RuntimeArtifactFailure
    rule_id: str
    reason: str
    required_next_kind: str
    target_paths: tuple[str, ...] = ()
    inspection_target_paths: tuple[str, ...] = ()
    inspection_evidence_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    forbidden_next: tuple[str, ...] = ()
    repeat_count: int = 0
    threshold: int = _RUNTIME_ARTIFACT_REPEAT_BUDGET


def reduce_transition_contract_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce inputs and annotate state-changing observations with a contract."""

    workframe, base_report = reduce_workframe(inputs)
    events = _canonical_sidecar_events(inputs)
    if not events:
        return workframe, base_report

    latest_event = events[-1]
    previous_workframe, _previous_report = reduce_workframe(replace(inputs, sidecar_events=events[:-1]))
    runtime_decision = _runtime_artifact_decision(workframe=workframe, events=events)
    if runtime_decision:
        latest_event = runtime_decision.failure.event
        workframe = _apply_runtime_artifact_decision(workframe, runtime_decision)
    elif not _workframe_state_changed(previous_workframe, workframe):
        return workframe, base_report

    contract = _transition_contract(
        workframe=workframe,
        previous_workframe=previous_workframe,
        latest_event=latest_event,
    )
    if runtime_decision:
        contract = _apply_runtime_artifact_decision_to_contract(contract, runtime_decision)
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


def _runtime_artifact_decision(
    *,
    workframe: WorkFrame,
    events: tuple[dict[str, object], ...],
) -> _RuntimeArtifactDecision | None:
    failures = _normalized_runtime_artifact_failures(events)
    if not failures:
        return None
    latest = failures[-1]
    if _runtime_failure_resolved_by_later_event(workframe=workframe, events=events, failure=latest):
        return None
    same_key = tuple(failure for failure in failures if failure.repeat_key == latest.repeat_key)
    repeat_count = len(same_key)
    all_post_failure_inspections = tuple(
        event
        for event in events
        if _event_sequence(event) > latest.sequence and _event_kind(event) in {"inspection", "diagnostic"}
    )
    post_failure_inspections = tuple(
        event for event in all_post_failure_inspections if _inspection_tied_to_runtime_failure(event, latest)
    )
    post_failure_inspection_refs = _stable_values(
        *(_event_evidence_refs(event) for event in post_failure_inspections),
        limit=4,
    )
    post_failure_inspection_paths = _stable_values(
        *(_event_paths(event) for event in post_failure_inspections),
        limit=_MAX_CONTRACT_PATHS,
    )
    current_required = workframe.required_next
    current_target_paths = current_required.target_paths if current_required else ()
    current_inspection_paths = current_required.inspection_target_paths if current_required else ()
    current_inspection_refs = current_required.inspection_evidence_refs if current_required else ()
    evidence_refs = _stable_values(
        latest.evidence_refs,
        post_failure_inspection_refs,
        current_inspection_refs,
        (latest.artifact_evidence_id,),
        (latest.command_run_id,),
        limit=4,
    )
    producer_paths = latest.producer_paths or post_failure_inspection_paths or tuple(workframe.changed_sources.paths)
    if not producer_paths and current_required and current_required.kind == "patch_or_edit":
        producer_paths = current_target_paths
    if not latest.latest_mutation_ref and not current_inspection_refs:
        producer_paths = ()
    inspection_paths = _stable_values(
        producer_paths,
        current_inspection_paths,
        (latest.artifact_path,),
        limit=_MAX_CONTRACT_PATHS,
    )
    if repeat_count > _RUNTIME_ARTIFACT_REPEAT_BUDGET:
        return _RuntimeArtifactDecision(
            failure=latest,
            rule_id="transition_contract.runtime_artifact_missing.repeat_budget_exhausted",
            reason="same runtime artifact miss repeated beyond budget without decisive new evidence",
            required_next_kind="blocked",
            target_paths=producer_paths,
            inspection_target_paths=inspection_paths,
            inspection_evidence_refs=current_inspection_refs,
            evidence_refs=evidence_refs,
            forbidden_next=("patch_or_edit", "run_verifier", "finish"),
            repeat_count=repeat_count,
        )
    if all_post_failure_inspections and not post_failure_inspections:
        return _RuntimeArtifactDecision(
            failure=latest,
            rule_id="transition_contract.runtime_artifact_missing.unrelated_inspection_requires_tied_inspection",
            reason="unrelated inspection does not resolve the runtime artifact miss; inspect exact producer/artifact evidence",
            required_next_kind="inspect_latest_failure",
            target_paths=(),
            inspection_target_paths=inspection_paths,
            inspection_evidence_refs=current_inspection_refs or evidence_refs,
            evidence_refs=evidence_refs,
            forbidden_next=("run_verifier", "finish"),
            repeat_count=repeat_count,
        )
    if post_failure_inspections:
        if producer_paths:
            return _RuntimeArtifactDecision(
                failure=latest,
                rule_id="transition_contract.runtime_artifact_missing.inspection_enables_patch",
                reason=(
                    "producer/artifact inspection evidence is available after the miss; "
                    "patch or edit the producer path before another verifier"
                ),
                required_next_kind="patch_or_edit",
                target_paths=producer_paths,
                inspection_target_paths=inspection_paths,
                inspection_evidence_refs=post_failure_inspection_refs or current_inspection_refs,
                evidence_refs=evidence_refs,
                forbidden_next=("finish",),
                repeat_count=repeat_count,
            )
        return _RuntimeArtifactDecision(
            failure=latest,
            rule_id="transition_contract.runtime_artifact_missing.inspection_without_path_requires_decision",
            reason=(
                "producer/artifact inspection has already run; use the latest diagnostic evidence to choose a "
                "producer patch path or finish blocked with the missing path"
            ),
            required_next_kind="inspect_latest_failure",
            target_paths=producer_paths,
            inspection_target_paths=inspection_paths,
            inspection_evidence_refs=post_failure_inspection_refs or current_inspection_refs,
            evidence_refs=evidence_refs,
            forbidden_next=("run_verifier", "finish"),
            repeat_count=repeat_count,
        )
    if repeat_count >= 2 or not producer_paths:
        rule_id = (
            "transition_contract.runtime_artifact_missing.repeat_requires_inspection"
            if repeat_count >= 2
            else "transition_contract.runtime_artifact_missing.producer_unknown_requires_inspection"
        )
        reason = (
            "same runtime artifact miss repeated; inspect exact producer and artifact evidence before another verifier"
            if repeat_count >= 2
            else (
                "Run one scoped producer/artifact diagnostic for the missing expected artifact; "
                "inspect exact producer/artifact evidence first"
            )
        )
        return _RuntimeArtifactDecision(
            failure=latest,
            rule_id=rule_id,
            reason=reason,
            required_next_kind="inspect_latest_failure",
            target_paths=producer_paths,
            inspection_target_paths=inspection_paths,
            inspection_evidence_refs=current_inspection_refs or evidence_refs,
            evidence_refs=evidence_refs,
            forbidden_next=("run_verifier", "finish"),
            repeat_count=repeat_count,
        )
    return _RuntimeArtifactDecision(
        failure=latest,
        rule_id="transition_contract.runtime_artifact_missing.patch_known_producer",
        reason="runtime artifact miss has a known producer mutation path; patch the producer then run the verifier",
        required_next_kind="patch_or_edit",
        target_paths=producer_paths,
        inspection_target_paths=inspection_paths,
        inspection_evidence_refs=current_inspection_refs,
        evidence_refs=evidence_refs,
        forbidden_next=("finish",),
        repeat_count=repeat_count,
    )


def _runtime_failure_resolved_by_later_event(
    *,
    workframe: WorkFrame,
    events: tuple[dict[str, object], ...],
    failure: _RuntimeArtifactFailure,
) -> bool:
    if workframe.finish_readiness.state == "ready":
        return True
    if workframe.required_next and workframe.required_next.kind == "finish":
        return True
    for event in events:
        if _event_sequence(event) <= failure.sequence:
            continue
        if _event_is_passing_verifier(event):
            return True
        if _event_is_source_mutation(event):
            # A source mutation after the miss already answered the repair
            # instruction. Preserve the base WorkFrame's verifier-next state
            # until a fresh verifier result creates a new runtime miss.
            return True
    return False


def _event_is_passing_verifier(event: dict[str, object]) -> bool:
    return _event_status(event) in {"completed", "passed", "pass", "success", "succeeded"} and _event_kind(event) in {
        "verifier",
        "strict_verifier",
        "run_tests",
        "verifier_result",
    }


def _event_is_source_mutation(event: dict[str, object]) -> bool:
    if _event_kind(event) in {"source_mutation", "source_tree_mutation", "write", "edit", "apply_patch"}:
        return True
    if _event_kind(event) in {"run_command", "run_tests", "command", "managed_command"}:
        for key in (
            "source_side_effect",
            "source_mutation_detected",
            "source_tree_mutation",
            "shell_source_side_effect",
            "writes_source",
            "mutates_source",
            "policy_blocked_source_mutation",
        ):
            if bool(event.get(key)):
                return True
    if isinstance(event.get("source_mutation"), dict):
        return True
    source_mutations = event.get("source_mutations")
    if isinstance(source_mutations, (list, tuple)) and any(isinstance(item, dict) for item in source_mutations):
        return True
    record = event.get("record")
    if isinstance(record, dict) and _source_tree_record_has_changes(record):
        return True
    for record in _side_effect_records(event, kind="source_tree_mutation"):
        if _source_tree_record_has_changes(record):
            return True
    return False


def _source_tree_record_has_changes(record: dict[str, object]) -> bool:
    try:
        if int(record.get("changed_count") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    changes = record.get("changes")
    return isinstance(changes, (list, tuple)) and any(isinstance(item, dict) for item in changes)


def _inspection_tied_to_runtime_failure(event: dict[str, object], failure: _RuntimeArtifactFailure) -> bool:
    artifact = _model_visible_path(failure.artifact_path)
    artifact_name = artifact.rsplit("/", 1)[-1]
    artifact_stem = artifact_name.rsplit(".", 1)[0]
    path_keys = {
        _model_visible_path(path).casefold()
        for path in _event_paths(event)
        if _model_visible_path(path)
    }
    expected_path_keys = {
        _model_visible_path(path).casefold()
        for path in (artifact, artifact_name, *failure.producer_paths)
        if _model_visible_path(path)
    }
    if path_keys & expected_path_keys:
        return True
    haystack = " ".join(
        item.casefold()
        for item in (
            _event_detail_text(event),
            " ".join(_event_paths(event)),
            " ".join(_event_evidence_refs(event)),
        )
        if item
    )
    if not haystack:
        return False
    tokens = [
        artifact,
        artifact_name,
        *failure.producer_paths,
    ]
    if len(artifact_stem) >= 8:
        tokens.append(artifact_stem)
    return any(_haystack_contains_runtime_token(haystack, token) for token in tokens)


def _haystack_contains_runtime_token(haystack: str, token: str) -> bool:
    normalized = _model_visible_path(token).casefold()
    if len(normalized) <= 2:
        return False
    candidates = [normalized]
    if "/" in normalized:
        candidates.append(normalized.rsplit("/", 1)[-1])
    for candidate in candidates:
        if not candidate or len(candidate) <= 2:
            continue
        if re.search(rf"(?<![A-Za-z0-9_./-]){re.escape(candidate)}(?![A-Za-z0-9_./-])", haystack):
            return True
    return False



def _normalized_runtime_artifact_failures(
    events: tuple[dict[str, object], ...],
) -> tuple[_RuntimeArtifactFailure, ...]:
    failures: list[_RuntimeArtifactFailure] = []
    for index, event in enumerate(events):
        normalized = _normalized_runtime_artifact_failure(event, events[:index])
        if normalized:
            failures.append(normalized)
    return tuple(failures)


def _normalized_runtime_artifact_failure(
    event: dict[str, object],
    prior_events: tuple[dict[str, object], ...],
) -> _RuntimeArtifactFailure | None:
    family, subfamily = _runtime_artifact_family(event)
    if not family:
        return None
    artifact_path = _runtime_artifact_path(event)
    if not artifact_path:
        return None
    sequence = _event_sequence(event)
    mutation = _latest_source_mutation_event(prior_events)
    mutation_paths = tuple(_model_visible_path(path) for path in _event_paths(mutation) if _model_visible_path(path))
    mutation_ref = _event_ref(mutation) if mutation else ""
    mutation_sequence = _event_sequence(mutation) if mutation else -1
    failed_checks = _runtime_failed_checks(event)
    command_run_id = _runtime_command_run_id(event)
    artifact_evidence_id = _runtime_artifact_evidence_id(event)
    verifier_id = _runtime_verifier_id(event)
    repeat_key = "|".join(
        item
        for item in (
            "runtime_artifact_missing",
            _model_visible_path(artifact_path),
            ",".join(failed_checks),
        )
        if item
    )
    return _RuntimeArtifactFailure(
        event=event,
        sequence=sequence,
        family=family,
        subfamily=subfamily,
        status=_event_status(event),
        artifact_path=_model_visible_path(artifact_path),
        failed_checks=failed_checks,
        command_run_id=command_run_id,
        verifier_id=verifier_id,
        artifact_evidence_id=artifact_evidence_id,
        producer_paths=tuple(dict.fromkeys(path for path in mutation_paths if path)),
        latest_mutation_ref=mutation_ref,
        latest_mutation_sequence=mutation_sequence,
        observable_progress=bool(event.get("observable_output")),
        repeat_key=repeat_key,
        evidence_refs=_stable_values(_event_evidence_refs(event), (artifact_evidence_id,), (command_run_id,)),
    )


def _runtime_artifact_family(event: dict[str, object]) -> tuple[str, str]:
    family = str(event.get("family") or event.get("failure_class") or "").strip()
    if family == "runtime_artifact_missing":
        subfamily = "silent_verifier_repeat" if _event_is_silent(event) else "missing_artifact"
        return family, subfamily
    for record in _side_effect_records(event, kind="failure_classification"):
        record_family = str(record.get("class") or record.get("failure_class") or "").strip()
        record_kind = str(record.get("kind") or "").strip()
        if record_family == "runtime_artifact_missing" or (
            record_family in {"runtime_failure", "verification_failure", "artifact_validation_failure"}
            and record_kind == "missing_artifact"
        ):
            subfamily = "silent_verifier_repeat" if _event_is_silent(event) else (record_kind or "missing_artifact")
            return "runtime_artifact_missing", subfamily
        secondary_classes = record.get("secondary_classes")
        secondary_kinds = record.get("secondary_kinds")
        if (
            isinstance(secondary_classes, (list, tuple))
            and "runtime_artifact_missing" in {str(item) for item in secondary_classes}
        ) or (
            isinstance(secondary_kinds, (list, tuple)) and "missing_artifact" in {str(item) for item in secondary_kinds}
        ):
            return "runtime_artifact_missing", "missing_artifact"
    return "", ""


def _event_is_silent(event: dict[str, object]) -> bool:
    if bool(event.get("observable_output")):
        return False
    detail = _event_detail_text(event).casefold()
    return any(term in detail for term in ("no observable output", "no output", "interrupted", "killed"))


def _event_detail_text(event: dict[str, object]) -> str:
    parts: list[str] = []
    for key in (
        "summary",
        "message",
        "failure_summary",
        "reason",
        "stderr_tail",
        "stdout_tail",
        "required_next_action",
        "required_next_probe",
        "diagnostic",
        "status",
    ):
        value = event.get(key)
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
    return "\n".join(parts)


def _runtime_artifact_path(event: dict[str, object]) -> str:
    for record in _side_effect_records(event, kind="artifact_evidence"):
        path = str(record.get("path") or record.get("artifact_id") or "").strip()
        if path:
            return path
    contract = _mapping(event.get("execution_contract"))
    for item in _list_of_mappings(contract.get("expected_artifacts")):
        path = str(item.get("path") or item.get("id") or "").strip()
        if path:
            return path
    for path in _event_paths(event):
        if _looks_like_runtime_artifact(path):
            return path
    return ""


def _runtime_failed_checks(event: dict[str, object]) -> tuple[str, ...]:
    checks: list[str] = []
    for record in _side_effect_records(event, kind="artifact_evidence"):
        for check in _list_of_mappings(record.get("checks")):
            if check.get("passed") is True:
                continue
            check_type = str(check.get("type") or check.get("id") or "").strip()
            if check_type:
                checks.append(check_type)
    return tuple(dict.fromkeys(checks)) or ("missing_artifact",)


def _runtime_command_run_id(event: dict[str, object]) -> str:
    value = str(event.get("command_run_id") or "").strip()
    if value:
        return value
    for record in _side_effect_records(event, kind="command_run"):
        value = str(record.get("command_run_id") or "").strip()
        if value:
            return value
    for record in _side_effect_records(event, kind="tool_run_record"):
        value = str(record.get("command_run_id") or "").strip()
        if value:
            return value
    return ""


def _runtime_artifact_evidence_id(event: dict[str, object]) -> str:
    for record in _side_effect_records(event, kind="artifact_evidence"):
        value = str(record.get("evidence_id") or record.get("artifact_id") or "").strip()
        if value:
            return value
    return ""


def _runtime_verifier_id(event: dict[str, object]) -> str:
    for record in _side_effect_records(event, kind="verifier_evidence"):
        value = str(record.get("verifier_id") or "").strip()
        if value:
            return value
    contract = _mapping(event.get("execution_contract"))
    contract_id = str(contract.get("id") or "").strip()
    return f"verifier:{contract_id}" if contract_id else ""


def _side_effect_records(event: dict[str, object], *, kind: str) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    side_effects = event.get("side_effects")
    if not isinstance(side_effects, (list, tuple)):
        return ()
    for effect in side_effects:
        if not isinstance(effect, dict) or str(effect.get("kind") or "") != kind:
            continue
        record = effect.get("record")
        if isinstance(record, dict):
            records.append(record)
    return tuple(records)


def _latest_source_mutation_event(events: Iterable[dict[str, object]]) -> dict[str, object] | None:
    matches = [event for event in events if _event_is_source_mutation(event)]
    return max(matches, key=_event_sequence) if matches else None


def _event_paths(event: object) -> tuple[str, ...]:
    if not isinstance(event, dict):
        return ()
    paths: list[str] = []
    for key in ("path", "target_path", "source_path", "changed_path"):
        value = str(event.get(key) or "").strip()
        if value:
            paths.append(value)
    for key in ("paths", "target_paths", "changed_paths", "changed_files", "source_paths"):
        raw = event.get(key)
        if isinstance(raw, (list, tuple)):
            paths.extend(str(item).strip() for item in raw if str(item).strip())
    mutation = event.get("source_mutation")
    if isinstance(mutation, dict):
        paths.extend(_event_paths(mutation))
    source_mutations = event.get("source_mutations")
    if isinstance(source_mutations, (list, tuple)):
        for item in source_mutations:
            paths.extend(_event_paths(item))
    record = event.get("record")
    if isinstance(record, dict):
        paths.extend(_source_tree_record_paths(record))
    side_effects = event.get("side_effects")
    if isinstance(side_effects, (list, tuple)):
        for effect in side_effects:
            if not isinstance(effect, dict) or str(effect.get("kind") or "") != "source_tree_mutation":
                continue
            effect_record = effect.get("record")
            if isinstance(effect_record, dict):
                paths.extend(_source_tree_record_paths(effect_record))
    return tuple(dict.fromkeys(path for path in paths if path))


def _source_tree_record_paths(record: dict[str, object]) -> tuple[str, ...]:
    paths: list[str] = []
    for key in ("path", "target_path", "source_path", "changed_path"):
        value = str(record.get(key) or "").strip()
        if value:
            paths.append(value)
    changes = record.get("changes")
    if isinstance(changes, (list, tuple)):
        for change in changes:
            if isinstance(change, dict):
                paths.extend(_event_paths(change))
    return tuple(paths)


def _model_visible_path(value: object) -> str:
    path = str(value or "").strip()
    if path.startswith("$WORKSPACE/"):
        return path.removeprefix("$WORKSPACE/").strip("/")
    if path.startswith("/app/"):
        return path.removeprefix("/app/").strip("/")
    return path.strip("/")


def _looks_like_runtime_artifact(value: object) -> bool:
    path = _model_visible_path(value).casefold()
    return bool(path) and any(term in path for term in ("frame", "artifact", ".ppm", ".bmp", "acceptance"))


def _list_of_mappings(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


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


def _apply_runtime_artifact_decision(
    workframe: WorkFrame,
    decision: _RuntimeArtifactDecision,
) -> WorkFrame:
    latest_actionable = _runtime_decision_latest_actionable(workframe.latest_actionable, decision)
    required_next = WorkFrameRequiredNext(
        kind=decision.required_next_kind,  # type: ignore[arg-type]
        reason=decision.reason,
        target_paths=decision.target_paths,
        after=_runtime_decision_after(decision),
        evidence_refs=decision.evidence_refs,
        inspection_target_paths=decision.inspection_target_paths,
        inspection_evidence_refs=decision.inspection_evidence_refs,
    )
    forbidden = list(workframe.forbidden_next)
    existing = {item.kind for item in forbidden}
    for kind in decision.forbidden_next:
        if kind in existing:
            continue
        forbidden.append(
            WorkFrameForbiddenNext(
                kind=kind,
                reason=f"forbidden by {decision.rule_id}",
                evidence_refs=decision.evidence_refs,
            )
        )
    phase = "blocked" if decision.required_next_kind == "blocked" else workframe.current_phase
    return replace(
        workframe,
        current_phase=phase,  # type: ignore[arg-type]
        latest_actionable=latest_actionable,
        required_next=required_next,
        forbidden_next=tuple(forbidden),
    )


def _runtime_decision_latest_actionable(
    latest_actionable: WorkFrameLatestActionable | None,
    decision: _RuntimeArtifactDecision,
) -> WorkFrameLatestActionable:
    hint = dict(latest_actionable.recovery_hint) if latest_actionable else {}
    return WorkFrameLatestActionable(
        family=decision.failure.family,
        generic_family="artifact_missing",
        summary=decision.reason,
        source_ref=_event_ref(decision.failure.event),
        evidence_refs=decision.evidence_refs,
        recovery_hint=hint,
    )


def _runtime_decision_after(decision: _RuntimeArtifactDecision) -> str:
    if decision.required_next_kind == "patch_or_edit":
        return "run_configured_verifier"
    if decision.required_next_kind == "inspect_latest_failure":
        return "patch_or_edit_or_block"
    return ""


def _runtime_decision_payload(decision: _RuntimeArtifactDecision) -> dict[str, object]:
    failure = decision.failure
    return _drop_empty(
        {
            "schema_version": 1,
            "family": failure.family,
            "subfamily": failure.subfamily,
            "status": failure.status,
            "artifact_path": failure.artifact_path,
            "failed_checks": list(failure.failed_checks),
            "command_run_id": failure.command_run_id,
            "verifier_id": failure.verifier_id,
            "artifact_evidence_id": failure.artifact_evidence_id,
            "producer_paths": list(failure.producer_paths),
            "latest_mutation_ref": failure.latest_mutation_ref,
            "latest_mutation_sequence": failure.latest_mutation_sequence,
            "observable_progress": failure.observable_progress,
            "repeat_key": failure.repeat_key,
            "repeat_count": decision.repeat_count,
            "threshold": decision.threshold,
            "rule_id": decision.rule_id,
            "required_next": decision.required_next_kind,
            "target_paths": list(decision.target_paths),
            "inspection_target_paths": list(decision.inspection_target_paths),
            "inspection_evidence_refs": list(decision.inspection_evidence_refs),
            "evidence_refs": list(decision.evidence_refs),
        }
    )


def _apply_runtime_artifact_decision_to_contract(
    contract: dict[str, object],
    decision: _RuntimeArtifactDecision,
) -> dict[str, object]:
    updated = dict(contract)
    latest_observation = _mapping(updated.get("latest_observation"))
    latest_observation["evidence_refs"] = list(
        _stable_values(_list_value(latest_observation.get("evidence_refs")), limit=4)
    )
    updated["latest_observation"] = latest_observation
    evidence_delta = _mapping(updated.get("evidence_delta"))
    evidence_delta["new_refs"] = list(_stable_values(_list_value(evidence_delta.get("new_refs")), limit=4))
    updated["evidence_delta"] = evidence_delta
    transition = _mapping(updated.get("state_transition"))
    transition["rule_id"] = decision.rule_id
    transition["reason"] = decision.reason
    transition["provenance_refs"] = list(
        _stable_values(_list_value(transition.get("provenance_refs")), decision.evidence_refs, limit=4)
    )
    updated["state_transition"] = transition
    updated["runtime_artifact_transition"] = _runtime_decision_payload(decision)
    updated["next_action_contract"] = _next_action_contract(
        WorkFrameRequiredNext(
            kind=decision.required_next_kind,  # type: ignore[arg-type]
            reason=decision.reason,
            target_paths=decision.target_paths,
            after=_runtime_decision_after(decision),
            evidence_refs=decision.evidence_refs,
            inspection_target_paths=decision.inspection_target_paths,
            inspection_evidence_refs=decision.inspection_evidence_refs,
        ),
        decision.evidence_refs,
    )
    return updated


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
    ref_limit = 4 if rule_id.startswith("transition_contract.runtime_artifact_missing.") else _MAX_CONTRACT_REFS
    provenance_refs = _stable_values(_list_value(transition.get("provenance_refs")), limit=ref_limit)
    evidence_refs = _stable_values(required_next.evidence_refs, provenance_refs, limit=ref_limit)
    reason = _contract_reason(required_next.reason, rule_id)
    after = _contract_after(required_next, rule_id=rule_id, provenance_refs=provenance_refs)
    return replace(required_next, reason=reason, after=after, evidence_refs=evidence_refs)


def _contract_reason(reason: str, rule_id: str) -> str:
    if not rule_id or f"transition_rule={rule_id}" in reason:
        return reason
    if rule_id.startswith("transition_contract.runtime_artifact_missing."):
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
    if provenance_refs and not rule_id.startswith("transition_contract.runtime_artifact_missing."):
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


def _drop_empty(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if item not in (None, "", [], {})}


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
