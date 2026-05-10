"""Phase-0 WorkFrame substrate for implement_v2.

This module is intentionally runtime-adjacent, not yet runtime-active.  Phase 0
needs a deterministic schema, canonical fixture reducer, prompt inventory
checks, and baseline metric recording before any prompt cutover happens.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import posixpath
from typing import Iterable, Literal

WORKFRAME_SCHEMA_VERSION = 1
WORKFRAME_REDUCER_SCHEMA_VERSION = 1
WORKFRAME_CANONICALIZER_VERSION = 1
WORKFRAME_PHASE0_SCHEMA_VERSION = 1
WORKFRAME_TARGET_MAX_BYTES = 4096
WORKFRAME_RED_MAX_BYTES = 6144

WorkFramePhase = Literal[
    "orient",
    "cheap_probe",
    "prewrite_blocked",
    "ready_to_patch",
    "repair_after_write_failure",
    "verify_after_mutation",
    "repair_after_verifier_failure",
    "finish_ready",
    "finish_blocked",
    "controller_closeout",
    "blocked",
]

WorkFrameNextKind = Literal[
    "cheap_probe",
    "inspect_latest_failure",
    "patch_or_edit",
    "run_verifier",
    "finish",
    "blocked",
]

LEGACY_PROMPT_PROJECTION_IDS = (
    "implement_v2_active_work_todo",
    "implement_v2_hard_runtime_frontier_state",
    "implement_v2_repair_history",
)

WORKFRAME_DEBUG_BUNDLE_FILES = (
    "reducer_inputs.json",
    "reducer_output.workframe.json",
    "reducer_trace.jsonl",
    "invariant_report.json",
    "prompt_render_inventory.json",
    "prompt_visible_workframe.json",
    "workframe_diff.json",
    "evidence_ref_index.json",
    "workframe_cursor.json",
    "failure_taxonomy.json",
)

_VOLATILE_CANONICAL_KEYS = frozenset(
    {
        "timestamp",
        "created_at",
        "updated_at",
        "received_at",
        "started_at",
        "finished_at",
        "pid",
        "ppid",
        "hostname",
        "host",
        "user",
        "username",
        "mtime",
        "mtime_ns",
        "provider_latency",
        "provider_latency_ms",
        "latency_ms",
        "duration_ms",
        "elapsed_ms",
    }
)

_SOURCE_MUTATION_FAILURE_STATUSES = frozenset({"failed", "interrupted", "invalid", "blocked"})


@dataclass(frozen=True)
class WorkFrameTrace:
    attempt_id: str
    turn_id: str
    workframe_id: str
    input_hash: str
    output_hash: str = ""
    reducer_schema_version: int = WORKFRAME_REDUCER_SCHEMA_VERSION
    canonicalizer_version: int = WORKFRAME_CANONICALIZER_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "turn_id": self.turn_id,
            "workframe_id": self.workframe_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "reducer_schema_version": self.reducer_schema_version,
            "canonicalizer_version": self.canonicalizer_version,
        }


@dataclass(frozen=True)
class WorkFrameGoal:
    task_id: str
    objective: str
    success_contract_ref: str = ""
    constraints: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "objective": self.objective,
            "success_contract_ref": self.success_contract_ref,
            "constraints": list(self.constraints),
        }


@dataclass(frozen=True)
class WorkFrameLatestActionable:
    family: str
    summary: str
    generic_family: str = ""
    source_ref: str = ""
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "summary": self.summary,
            "generic_family": self.generic_family,
            "source_ref": self.source_ref,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class WorkFrameRequiredNext:
    kind: WorkFrameNextKind
    reason: str
    target_paths: tuple[str, ...] = ()
    after: str = ""
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "target_paths": list(self.target_paths),
            "after": self.after,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class WorkFrameForbiddenNext:
    kind: str
    reason: str
    evidence_refs: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass(frozen=True)
class WorkFrameChangedSources:
    paths: tuple[str, ...] = ()
    latest_mutation_ref: str = ""
    since_last_strict_verifier: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "paths": list(self.paths),
            "latest_mutation_ref": self.latest_mutation_ref,
            "since_last_strict_verifier": self.since_last_strict_verifier,
        }


@dataclass(frozen=True)
class WorkFrameVerifierState:
    configured_verifier_ref: str = ""
    last_strict_verifier_ref: str = ""
    status: str = "unknown"
    fresh_after_latest_source_mutation: bool = False
    budget_closeout_required: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "configured_verifier_ref": self.configured_verifier_ref,
            "last_strict_verifier_ref": self.last_strict_verifier_ref,
            "status": self.status,
            "fresh_after_latest_source_mutation": self.fresh_after_latest_source_mutation,
            "budget_closeout_required": self.budget_closeout_required,
        }


@dataclass(frozen=True)
class WorkFrameFinishReadiness:
    state: Literal["not_ready", "ready", "blocked"] = "not_ready"
    blockers: tuple[str, ...] = ()
    required_evidence_refs: tuple[str, ...] = ()
    missing_obligations: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "blockers": list(self.blockers),
            "required_evidence_refs": list(self.required_evidence_refs),
            "missing_obligations": list(self.missing_obligations),
        }


@dataclass(frozen=True)
class WorkFrameEvidenceRefs:
    typed: tuple[str, ...] = ()
    sidecar: tuple[str, ...] = ()
    replay: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "typed": list(self.typed),
            "sidecar": list(self.sidecar),
            "replay": list(self.replay),
        }


@dataclass(frozen=True)
class WorkFrame:
    trace: WorkFrameTrace
    goal: WorkFrameGoal
    current_phase: WorkFramePhase
    latest_actionable: WorkFrameLatestActionable | None = None
    required_next: WorkFrameRequiredNext | None = None
    forbidden_next: tuple[WorkFrameForbiddenNext, ...] = ()
    changed_sources: WorkFrameChangedSources = field(default_factory=WorkFrameChangedSources)
    verifier_state: WorkFrameVerifierState = field(default_factory=WorkFrameVerifierState)
    finish_readiness: WorkFrameFinishReadiness = field(default_factory=WorkFrameFinishReadiness)
    evidence_refs: WorkFrameEvidenceRefs = field(default_factory=WorkFrameEvidenceRefs)
    schema_version: int = WORKFRAME_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "trace": self.trace.as_dict(),
            "goal": self.goal.as_dict(),
            "current_phase": self.current_phase,
            "latest_actionable": self.latest_actionable.as_dict() if self.latest_actionable else None,
            "required_next": self.required_next.as_dict() if self.required_next else None,
            "forbidden_next": [item.as_dict() for item in self.forbidden_next],
            "changed_sources": self.changed_sources.as_dict(),
            "verifier_state": self.verifier_state.as_dict(),
            "finish_readiness": self.finish_readiness.as_dict(),
            "evidence_refs": self.evidence_refs.as_dict(),
        }


@dataclass(frozen=True)
class WorkFrameInputs:
    attempt_id: str
    turn_id: str
    task_id: str
    objective: str
    success_contract_ref: str = ""
    constraints: tuple[str, ...] = ()
    sidecar_events: tuple[dict[str, object], ...] = ()
    prompt_inventory: tuple[dict[str, object], ...] = ()
    baseline_metrics: dict[str, object] = field(default_factory=dict)
    previous_workframe_hash: str = ""
    workspace_root: str = ""
    artifact_root: str = ""
    schema_version: int = WORKFRAME_PHASE0_SCHEMA_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "attempt_id": self.attempt_id,
            "turn_id": self.turn_id,
            "task_id": self.task_id,
            "objective": self.objective,
            "success_contract_ref": self.success_contract_ref,
            "constraints": list(self.constraints),
            "sidecar_events": [dict(event) for event in self.sidecar_events],
            "prompt_inventory": [dict(item) for item in self.prompt_inventory],
            "baseline_metrics": dict(self.baseline_metrics),
            "previous_workframe_hash": self.previous_workframe_hash,
            "workspace_root": self.workspace_root,
            "artifact_root": self.artifact_root,
        }


@dataclass(frozen=True)
class WorkFrameInvariantReport:
    status: Literal["pass", "fail"]
    passed: tuple[str, ...] = ()
    failed: tuple[dict[str, object], ...] = ()
    warnings: tuple[dict[str, object], ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "passed": list(self.passed),
            "failed": [dict(item) for item in self.failed],
            "warnings": [dict(item) for item in self.warnings],
        }


def reduce_workframe(inputs: WorkFrameInputs) -> tuple[WorkFrame, WorkFrameInvariantReport]:
    """Reduce canonical sidecar fixture facts into one WorkFrame.

    This is deliberately fixture-only in Phase 0. Live runtime cutover belongs to
    later phases once prompt and replay fastchecks exist.
    """

    canonical = canonicalize_workframe_inputs(inputs)
    input_hash = _sha256_json(canonical)
    facts = _extract_facts(canonical)
    trace = WorkFrameTrace(
        attempt_id=inputs.attempt_id,
        turn_id=inputs.turn_id,
        workframe_id=f"wf-{input_hash[7:19]}",
        input_hash=input_hash,
    )
    goal = WorkFrameGoal(
        task_id=inputs.task_id,
        objective=inputs.objective,
        success_contract_ref=inputs.success_contract_ref,
        constraints=tuple(sorted(_string_set(inputs.constraints))),
    )
    changed_sources = WorkFrameChangedSources(
        paths=tuple(facts["changed_paths"]),
        latest_mutation_ref=str(facts["latest_mutation_ref"]),
        since_last_strict_verifier=bool(facts["source_changed_since_verifier"]),
    )
    verifier_state = WorkFrameVerifierState(
        configured_verifier_ref=str(facts["configured_verifier_ref"]),
        last_strict_verifier_ref=str(facts["last_verifier_ref"]),
        status=str(facts["verifier_status"]),
        fresh_after_latest_source_mutation=bool(facts["verifier_fresh"]),
        budget_closeout_required=bool(facts["budget_closeout_required"]),
    )
    latest_actionable = _latest_actionable_from_facts(facts)
    finish_readiness = _finish_readiness_from_facts(facts)
    required_next = _required_next_from_facts(facts, latest_actionable, finish_readiness)
    forbidden_next = tuple(_forbidden_next_from_facts(facts, finish_readiness))
    workframe = WorkFrame(
        trace=trace,
        goal=goal,
        current_phase=_phase_from_facts(facts, finish_readiness, required_next),
        latest_actionable=latest_actionable,
        required_next=required_next,
        forbidden_next=forbidden_next,
        changed_sources=changed_sources,
        verifier_state=verifier_state,
        finish_readiness=finish_readiness,
        evidence_refs=WorkFrameEvidenceRefs(
            typed=tuple(facts["typed_refs"]),
            sidecar=tuple(facts["sidecar_refs"]),
            replay=tuple(facts["replay_refs"]),
        ),
    )
    workframe = replace(workframe, trace=replace(workframe.trace, output_hash=workframe_output_hash(workframe)))
    return workframe, validate_workframe(workframe, inputs=inputs)


def canonicalize_workframe_inputs(inputs: WorkFrameInputs) -> dict[str, object]:
    """Return byte-stable reducer inputs suitable for hashing/replay."""

    workspace_root = _normalize_root(inputs.workspace_root)
    artifact_root = _normalize_root(inputs.artifact_root)
    events = [
        _canonical_event(event, index, workspace_root=workspace_root, artifact_root=artifact_root)
        for index, event in enumerate(inputs.sidecar_events)
    ]
    events.sort(key=lambda event: (int(event["event_sequence"]), str(event["event_id"])))
    return {
        "reducer_schema_version": WORKFRAME_REDUCER_SCHEMA_VERSION,
        "workframe_schema_version": WORKFRAME_SCHEMA_VERSION,
        "canonicalizer_version": WORKFRAME_CANONICALIZER_VERSION,
        "payload": {
            "schema_version": inputs.schema_version,
            "attempt_id": str(inputs.attempt_id),
            "turn_id": str(inputs.turn_id),
            "task_id": str(inputs.task_id),
            "objective": str(inputs.objective),
            "success_contract_ref": str(inputs.success_contract_ref),
            "constraints": sorted(_string_set(inputs.constraints)),
            "sidecar_events": events,
            "prompt_inventory": [
                _canonical_mapping(item, workspace_root=workspace_root, artifact_root=artifact_root)
                for item in inputs.prompt_inventory
            ],
            "baseline_metrics": _canonical_mapping(
                inputs.baseline_metrics,
                workspace_root=workspace_root,
                artifact_root=artifact_root,
            ),
            "previous_workframe_hash": str(inputs.previous_workframe_hash),
        },
    }


def validate_workframe(workframe: WorkFrame, *, inputs: WorkFrameInputs) -> WorkFrameInvariantReport:
    passed: list[str] = []
    failed: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    frame_bytes = len(canonical_json(workframe.as_dict()).encode("utf-8"))
    if frame_bytes <= WORKFRAME_RED_MAX_BYTES:
        passed.append("workframe_size_within_red_cap")
    else:
        failed.append({"code": "workframe_size_over_cap", "bytes": frame_bytes, "cap": WORKFRAME_RED_MAX_BYTES})
    if workframe.required_next and not workframe.required_next.reason:
        failed.append({"code": "required_next_unjustified", "field": "reason"})
    else:
        passed.append("required_next_has_reason_or_absent")
    if workframe.required_next and not workframe.required_next.evidence_refs and workframe.latest_actionable:
        failed.append({"code": "required_next_unjustified", "field": "evidence_refs"})
    else:
        passed.append("required_next_has_evidence_or_not_needed")
    if workframe.latest_actionable and _is_generic_actionable_summary(workframe.latest_actionable.summary):
        failed.append(
            {
                "code": "latest_actionable_generic",
                "family": workframe.latest_actionable.family,
                "generic_family": workframe.latest_actionable.generic_family,
                "summary": workframe.latest_actionable.summary,
            }
        )
    else:
        passed.append("latest_actionable_summary_is_specific_or_absent")
    if workframe.finish_readiness.state == "ready" and workframe.changed_sources.since_last_strict_verifier:
        failed.append({"code": "finish_false_positive", "reason": "source mutation lacks fresh verifier"})
    else:
        passed.append("finish_not_ready_when_verifier_stale")
    if workframe.current_phase == "finish_ready" and (
        not workframe.required_next or workframe.required_next.kind != "finish" or not workframe.required_next.evidence_refs
    ):
        failed.append({"code": "finish_ready_missing_evidence_refs"})
    else:
        passed.append("finish_ready_requires_evidence_refs")
    if _has_conflicting_event_sequences(inputs.sidecar_events):
        failed.append({"code": "reducer_input_conflicting_event_sequence"})
    else:
        passed.append("event_sequences_unique_or_identical")
    rejected_probe_proof_refs = _rejected_probe_proof_refs(
        [event for event in inputs.sidecar_events if isinstance(event, dict)]
    )
    if rejected_probe_proof_refs:
        failed.append(
            {
                "code": "cheap_probe_authored_proof_obligation",
                "evidence_refs": list(rejected_probe_proof_refs),
            }
        )
    else:
        passed.append("cheap_probes_do_not_author_completion_proof")
    if frame_bytes <= WORKFRAME_TARGET_MAX_BYTES:
        passed.append("workframe_size_within_target_cap")
    elif frame_bytes <= WORKFRAME_RED_MAX_BYTES:
        warnings.append(
            {
                "code": "workframe_size_yellow",
                "bytes": frame_bytes,
                "target_cap": WORKFRAME_TARGET_MAX_BYTES,
                "red_cap": WORKFRAME_RED_MAX_BYTES,
            }
        )
    if not inputs.objective.strip():
        warnings.append({"code": "workframe_goal_objective_empty"})
    return WorkFrameInvariantReport(
        status="fail" if failed else "pass",
        passed=tuple(passed),
        failed=tuple(failed),
        warnings=tuple(warnings),
    )


def check_phase0_prompt_inventory(
    inventory: Iterable[dict[str, object]],
    *,
    required_legacy_ids: Iterable[str] = LEGACY_PROMPT_PROJECTION_IDS,
) -> dict[str, object]:
    """Verify legacy prompt projections are detectable before Phase-1 cutover."""

    ordinary_ids = tuple(
        str(item.get("id") or "")
        for item in inventory
        if isinstance(item, dict) and str(item.get("visibility") or "ordinary") == "ordinary"
    )
    required = tuple(str(item) for item in required_legacy_ids if str(item))
    present = tuple(item for item in required if item in ordinary_ids)
    missing = tuple(item for item in required if item not in ordinary_ids)
    return {
        "schema_version": WORKFRAME_PHASE0_SCHEMA_VERSION,
        "status": "pass" if not missing else "fail",
        "required_legacy_ids": list(required),
        "present_legacy_ids": list(present),
        "missing_legacy_ids": list(missing),
        "ordinary_section_ids": list(ordinary_ids),
    }


def record_phase0_baseline_metrics(
    manifest: dict[str, object],
    history: Iterable[dict[str, object]],
    *,
    workframe: WorkFrame | None = None,
) -> dict[str, object]:
    """Record WorkFrame Phase-0 baseline metrics from a saved manifest/history."""

    metrics = _mapping(manifest.get("metrics"))
    hot_path = _mapping(metrics.get("hot_path_projection"))
    sidecar = _mapping(metrics.get("resident_sidecar_state"))
    history_items = [dict(item) for item in history if isinstance(item, dict)]
    first_edit = _first_tool_turn(history_items, {"write_file", "edit_file", "apply_patch"})
    first_verifier = _first_verifier_turn(history_items)
    tool_calls = _count_tool_calls(history_items)
    same_family_repeats = _same_family_repeats(history_items)
    workframe_bytes = len(canonical_json(workframe.as_dict()).encode("utf-8")) if workframe else 0
    baseline = {
        "schema_version": WORKFRAME_PHASE0_SCHEMA_VERSION,
        "B_prompt_normal_total": _first_int(
            hot_path.get("normal_full_prompt_bytes_total"),
            hot_path.get("normal_full_prompt_bytes"),
            hot_path.get("normal_prompt_section_bytes"),
        ),
        "B_prompt_dynamic_hot_path": _first_int(hot_path.get("normal_dynamic_hot_path_bytes")),
        "B_tool_result_p95": _first_int(hot_path.get("provider_visible_tool_result_bytes")),
        "B_sidecar_total": _first_int(sidecar.get("total_bytes")),
        "B_sidecar_per_turn_growth": _first_float(sidecar.get("per_turn_growth_bytes")),
        "B_first_edit_turn": first_edit["turn"],
        "B_first_edit_seconds": first_edit["seconds"],
        "B_first_verifier_turn": first_verifier["turn"],
        "B_first_verifier_seconds": first_verifier["seconds"],
        "B_model_turns_10m": len(history_items),
        "B_tool_calls_10m": tool_calls,
        "B_same_family_repeats_10m": same_family_repeats,
        "B_required_next_adherence": _first_float(hot_path.get("required_next_adherence")),
        "B_workframe_bytes": workframe_bytes,
    }
    zero_allowed = {"B_same_family_repeats_10m"}
    missing = [
        key
        for key, value in baseline.items()
        if key.startswith("B_") and (value in (None, "") or (key not in zero_allowed and value in (0, 0.0)))
    ]
    return {
        "schema_version": WORKFRAME_PHASE0_SCHEMA_VERSION,
        "status": "pass" if not missing else "fail",
        "baseline": baseline,
        "missing_fields": missing,
        "bands": phase0_baseline_bands(),
    }


def phase0_baseline_bands() -> dict[str, dict[str, object]]:
    return {
        "B_prompt_normal_total": {"green": "<=70% baseline", "yellow": "<=80% baseline", "red": ">80% baseline"},
        "B_prompt_dynamic_hot_path": {"green": "<=45% baseline", "yellow": "<=60% baseline", "red": ">60% baseline"},
        "B_tool_result_p95": {"green": "<=40% baseline", "yellow": "<=55% baseline", "red": ">55% baseline"},
        "B_sidecar_total": {"green": "<=110% baseline", "yellow": "<=125% baseline", "red": ">125% baseline"},
        "B_sidecar_per_turn_growth": {"green": "<=110% baseline", "yellow": "<=150% baseline", "red": ">150% baseline"},
        "B_first_edit_turn": {"green": "<=75% baseline", "yellow": "<=100% baseline", "red": ">100% baseline"},
        "B_first_edit_seconds": {"green": "<=75% baseline", "yellow": "<=100% baseline", "red": ">100% baseline"},
        "B_first_verifier_turn": {"green": "<=90% baseline", "yellow": "<=110% baseline", "red": ">110% baseline"},
        "B_first_verifier_seconds": {"green": "<=90% baseline", "yellow": "<=110% baseline", "red": ">110% baseline"},
        "B_model_turns_10m": {"green": "<=90% baseline", "yellow": "<=100% baseline", "red": ">100% baseline"},
        "B_tool_calls_10m": {"green": "<=100% baseline", "yellow": "<=115% baseline", "red": ">115% baseline"},
        "B_same_family_repeats_10m": {"green": "<=50% baseline", "yellow": "<=baseline", "red": ">baseline"},
        "B_required_next_adherence": {"green": ">=90%", "yellow": ">=75%", "red": "<75%"},
        "B_workframe_bytes": {"green": "<=4096", "yellow": "<=6144", "red": ">6144"},
    }


def workframe_debug_bundle_format() -> dict[str, object]:
    return {
        "schema_version": WORKFRAME_PHASE0_SCHEMA_VERSION,
        "root": "implement_v2/workframes/turn-XXXX/",
        "files": list(WORKFRAME_DEBUG_BUNDLE_FILES),
    }


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"


def workframe_output_hash(workframe: WorkFrame) -> str:
    """Hash a WorkFrame with trace.output_hash excluded from the preimage."""

    payload = workframe.as_dict()
    trace = _mapping(payload.get("trace"))
    trace["output_hash"] = ""
    payload["trace"] = trace
    return _sha256_json(payload)


def _extract_facts(canonical_inputs: dict[str, object]) -> dict[str, object]:
    payload = _mapping(canonical_inputs.get("payload"))
    events = [event for event in payload.get("sidecar_events") or [] if isinstance(event, dict)]
    evidence_index = _evidence_index(events)
    mutation = _latest_source_mutation_event(events)
    write_failure = _latest_source_mutation_failure_event(events)
    verifier = _latest_event(events, kinds={"strict_verifier", "verifier", "run_tests"})
    finish_proof = _latest_finish_proof_event(events)
    changed_paths = tuple(sorted(_event_paths(mutation))) if mutation else ()
    mutation_seq = _event_sequence(mutation) if mutation else -1
    verifier_seq = _event_sequence(finish_proof) if finish_proof else -1
    failure = _latest_failure_event(events, min_sequence=mutation_seq)
    failure_seq = _event_sequence(failure) if failure else -1
    verifier_status = _event_status(finish_proof) if finish_proof else (_event_status(verifier) if verifier else "unknown")
    failure_after_finish_proof = bool(finish_proof and failure_seq > verifier_seq)
    verifier_fresh = (
        verifier_seq >= mutation_seq and verifier_status == "passed" and not failure_after_finish_proof
        if finish_proof
        else False
    )
    source_changed_since_verifier = bool(
        mutation and (not finish_proof or mutation_seq > verifier_seq or verifier_status != "passed")
    )
    configured_verifier_ref = str(payload.get("success_contract_ref") or "")
    closeout_required = bool(source_changed_since_verifier and _has_low_budget_event(events))
    return {
        "events": events,
        "evidence_index": evidence_index,
        "latest_mutation_ref": _event_ref(mutation),
        "changed_paths": changed_paths,
        "last_verifier_ref": _event_ref(finish_proof) or _event_ref(verifier),
        "last_verifier_evidence_refs": _event_evidence_refs(finish_proof) if finish_proof else (),
        "finish_gate_support_refs": _finish_gate_support_refs(events, min_sequence=max(mutation_seq, verifier_seq)),
        "verifier_status": verifier_status,
        "verifier_fresh": verifier_fresh,
        "source_changed_since_verifier": source_changed_since_verifier,
        "configured_verifier_ref": configured_verifier_ref,
        "budget_closeout_required": closeout_required,
        "latest_failure": failure,
        "latest_write_failure_ref": _event_ref(write_failure),
        "latest_write_failure_sequence": _event_sequence(write_failure) if write_failure else -1,
        "latest_failure_sequence": failure_seq,
        "latest_mutation_sequence": mutation_seq,
        "last_verifier_sequence": verifier_seq,
        "typed_refs": tuple(ref for ref in evidence_index if ref.startswith("ev:")),
        "sidecar_refs": tuple(
            ref
            for ref in evidence_index
            if ref.startswith(("sidecar:", "cmd:", "contract:", "oracle:", "finish:"))
        ),
        "replay_refs": tuple(ref for ref in evidence_index if ref.startswith("replay:")),
        "missing_obligations": _missing_obligation_refs(events),
        "rejected_probe_proof_refs": _rejected_probe_proof_refs(events),
    }


def _latest_actionable_from_facts(facts: dict[str, object]) -> WorkFrameLatestActionable | None:
    failure = facts.get("latest_failure")
    if isinstance(failure, dict):
        evidence_refs = _event_evidence_refs(failure)
        raw_family = str(
            failure.get("family")
            or failure.get("failure_class")
            or failure.get("class")
            or failure.get("failure_kind")
            or "unknown"
        )
        return WorkFrameLatestActionable(
            family=raw_family,
            generic_family=_generic_failure_family(failure),
            summary=_actionable_summary(failure),
            source_ref=_event_ref(failure),
            evidence_refs=evidence_refs,
        )
    if facts.get("source_changed_since_verifier"):
        return WorkFrameLatestActionable(
            family="verifier_stale_after_mutation",
            summary="source changed without a fresh passing strict verifier",
            generic_family="verifier_stale_after_mutation",
            source_ref=str(facts.get("latest_mutation_ref") or ""),
            evidence_refs=(str(facts.get("latest_mutation_ref") or ""),),
        )
    return None


def _finish_readiness_from_facts(facts: dict[str, object]) -> WorkFrameFinishReadiness:
    missing_obligations = tuple(str(item) for item in facts.get("missing_obligations") or () if str(item))
    if missing_obligations:
        return WorkFrameFinishReadiness(
            state="blocked",
            blockers=("missing_typed_obligations",),
            missing_obligations=missing_obligations,
        )
    if facts.get("verifier_fresh"):
        refs = tuple(
            dict.fromkeys(
                [
                    *(str(ref) for ref in facts.get("last_verifier_evidence_refs") or () if str(ref)),
                    *(str(ref) for ref in facts.get("finish_gate_support_refs") or () if str(ref)),
                    str(facts.get("last_verifier_ref") or ""),
                ]
            )
        )
        refs = tuple(ref for ref in refs if ref)
        return WorkFrameFinishReadiness(
            state="ready",
            required_evidence_refs=refs,
            missing_obligations=missing_obligations,
        )
    blockers: list[str] = []
    if facts.get("source_changed_since_verifier"):
        blockers.append("verifier_stale_after_mutation")
    if facts.get("verifier_status") in {"failed", "interrupted", "invalid"}:
        blockers.append("verifier_failed")
    if missing_obligations:
        blockers.append("missing_typed_obligations")
    if not blockers:
        blockers.append("missing_passing_verifier")
    return WorkFrameFinishReadiness(
        state="not_ready",
        blockers=tuple(blockers),
        missing_obligations=missing_obligations,
    )


def _required_next_from_facts(
    facts: dict[str, object],
    latest_actionable: WorkFrameLatestActionable | None,
    finish_readiness: WorkFrameFinishReadiness,
) -> WorkFrameRequiredNext | None:
    if finish_readiness.state == "ready":
        return WorkFrameRequiredNext(
            kind="finish",
            reason="fresh passing verifier evidence is available",
            evidence_refs=finish_readiness.required_evidence_refs,
        )
    if finish_readiness.state == "blocked" and finish_readiness.missing_obligations:
        return WorkFrameRequiredNext(
            kind="run_verifier",
            reason="finish is blocked by missing typed obligations; collect and cite verifier evidence",
            after="finish_or_block",
            evidence_refs=finish_readiness.missing_obligations,
        )
    if latest_actionable and latest_actionable.family != "verifier_stale_after_mutation":
        next_kind = _required_next_kind_for_generic_family(latest_actionable.generic_family)
        return WorkFrameRequiredNext(
            kind=next_kind,
            reason=_required_next_reason_for_generic_family(latest_actionable.generic_family),
            target_paths=_paths_from_failure(facts.get("latest_failure")),
            after="run_configured_verifier" if next_kind == "patch_or_edit" else "patch_or_edit_or_block",
            evidence_refs=latest_actionable.evidence_refs or (latest_actionable.source_ref,),
        )
    if facts.get("budget_closeout_required"):
        return WorkFrameRequiredNext(
            kind="run_verifier",
            reason="latest source mutation has no fresh strict verifier and budget requires closeout",
            after="finish_or_block",
            evidence_refs=tuple(ref for ref in (str(facts.get("latest_mutation_ref") or ""),) if ref),
        )
    if facts.get("source_changed_since_verifier"):
        return WorkFrameRequiredNext(
            kind="run_verifier",
            reason="source changed and no fresh strict verifier is available",
            evidence_refs=tuple(ref for ref in (str(facts.get("latest_mutation_ref") or ""),) if ref),
        )
    return WorkFrameRequiredNext(kind="cheap_probe", reason="no actionable source or verifier evidence yet")


def _forbidden_next_from_facts(
    facts: dict[str, object],
    finish_readiness: WorkFrameFinishReadiness,
) -> list[WorkFrameForbiddenNext]:
    forbidden: list[WorkFrameForbiddenNext] = []
    if finish_readiness.state != "ready":
        forbidden.append(
            WorkFrameForbiddenNext(
                kind="finish",
                reason="finish requires fresh passing verifier evidence",
                evidence_refs=finish_readiness.required_evidence_refs,
            )
        )
    if _latest_failure_is_current(facts):
        forbidden.append(
            WorkFrameForbiddenNext(
                kind="broad_rediscovery",
                reason="latest_actionable already identifies a repair surface",
                evidence_refs=_event_evidence_refs(facts["latest_failure"]),
            )
        )
    return forbidden


def _phase_from_facts(
    facts: dict[str, object],
    finish_readiness: WorkFrameFinishReadiness,
    required_next: WorkFrameRequiredNext | None,
) -> WorkFramePhase:
    if finish_readiness.state == "ready":
        return "finish_ready"
    if finish_readiness.state == "blocked":
        return "finish_blocked"
    if required_next and required_next.kind == "run_verifier" and facts.get("budget_closeout_required"):
        return "controller_closeout"
    if required_next and required_next.kind == "run_verifier":
        return "verify_after_mutation"
    if _latest_failure_is_current(facts):
        if _event_ref(facts.get("latest_failure")) == facts.get("latest_write_failure_ref"):
            return "repair_after_write_failure"
        return "repair_after_verifier_failure"
    if required_next and required_next.kind == "cheap_probe":
        return "cheap_probe"
    return "orient"


def _canonical_event(
    event: dict[str, object],
    fallback_sequence: int,
    *,
    workspace_root: str = "",
    artifact_root: str = "",
) -> dict[str, object]:
    canonical = _canonical_mapping(event, workspace_root=workspace_root, artifact_root=artifact_root)
    sequence = _first_int(canonical.get("event_sequence"), canonical.get("sequence"), fallback_sequence + 1)
    canonical["event_sequence"] = sequence
    canonical.setdefault("event_id", f"event-{sequence}")
    return canonical


def _canonical_mapping(value: object, *, workspace_root: str = "", artifact_root: str = "") -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, object] = {}
    for key, item in sorted(value.items(), key=lambda pair: str(pair[0])):
        canonical_key = str(key)
        if canonical_key in _VOLATILE_CANONICAL_KEYS:
            continue
        result[canonical_key] = _canonical_value(
            item,
            key=canonical_key,
            workspace_root=workspace_root,
            artifact_root=artifact_root,
        )
    return result


def _canonical_value(value: object, *, key: str = "", workspace_root: str = "", artifact_root: str = "") -> object:
    if isinstance(value, dict):
        return _canonical_mapping(value, workspace_root=workspace_root, artifact_root=artifact_root)
    if isinstance(value, (list, tuple)):
        return [
            _canonical_value(item, key=key, workspace_root=workspace_root, artifact_root=artifact_root)
            for item in value
        ]
    if isinstance(value, str):
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        if _is_path_like_key(key) or _looks_like_path(normalized):
            return _normalize_path_value(normalized, workspace_root=workspace_root, artifact_root=artifact_root)
        return normalized
    if isinstance(value, float):
        return f"{value:.6f}"
    return value


def _sha256_json(value: object) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _string_set(values: Iterable[object]) -> set[str]:
    return {str(value).strip() for value in values if str(value).strip()}


def _event_sequence(event: object) -> int:
    if not isinstance(event, dict):
        return -1
    return _first_int(event.get("event_sequence"), event.get("sequence"), -1)


def _event_ref(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    for key in ("evidence_ref", "event_ref", "command_run_id", "typed_evidence_id", "id"):
        value = str(event.get(key) or "").strip()
        if value:
            return value
    raw_refs = event.get("evidence_refs")
    if isinstance(raw_refs, (list, tuple)):
        for item in raw_refs:
            value = str(item or "").strip()
            if value:
                return value
    event_id = str(event.get("event_id") or "").strip()
    if event_id:
        return event_id
    sequence = _event_sequence(event)
    return f"sidecar:event:{sequence}" if sequence >= 0 else ""


def _event_kind(event: dict[str, object]) -> str:
    return str(event.get("kind") or event.get("type") or event.get("event_kind") or "").strip()


def _event_status(event: object) -> str:
    if not isinstance(event, dict):
        return "unknown"
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


def _latest_event(events: list[dict[str, object]], *, kinds: set[str]) -> dict[str, object] | None:
    matches = [event for event in events if _event_kind(event) in kinds]
    return max(matches, key=_event_sequence) if matches else None


def _latest_successful_event(events: list[dict[str, object]], *, kinds: set[str]) -> dict[str, object] | None:
    matches = [
        event
        for event in events
        if _event_kind(event) in kinds and _event_status(event) not in {"failed", "interrupted", "invalid"}
    ]
    return max(matches, key=_event_sequence) if matches else None


def _latest_failed_event(events: list[dict[str, object]], *, kinds: set[str]) -> dict[str, object] | None:
    matches = [
        event
        for event in events
        if _event_kind(event) in kinds and _event_status(event) in {"failed", "interrupted", "invalid"}
    ]
    return max(matches, key=_event_sequence) if matches else None


def _latest_source_mutation_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    matches = [
        event
        for event in events
        if _event_is_source_mutation_surface(event) and not _event_source_mutation_failed(event)
    ]
    return max(matches, key=_event_sequence) if matches else None


def _latest_source_mutation_failure_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    matches = [
        event
        for event in events
        if _event_is_source_mutation_surface(event) and _event_source_mutation_failed(event)
    ]
    return max(matches, key=_event_sequence) if matches else None


def _event_is_source_mutation_surface(event: dict[str, object]) -> bool:
    if _event_kind(event) in {"source_mutation", "source_tree_mutation", "write", "edit", "apply_patch"}:
        return True
    return _event_has_shell_source_side_effect(event)


def _event_source_mutation_failed(event: dict[str, object]) -> bool:
    return _event_status(event) in _SOURCE_MUTATION_FAILURE_STATUSES


def _event_has_shell_source_side_effect(event: dict[str, object]) -> bool:
    if _event_kind(event) == "source_tree_mutation":
        return True
    if _event_kind(event) not in {"run_command", "run_tests", "command", "managed_command"}:
        return _event_has_nested_source_tree_mutation(event)
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
    source_mutation = event.get("source_mutation")
    if isinstance(source_mutation, dict) and source_mutation:
        return True
    source_mutations = event.get("source_mutations")
    if isinstance(source_mutations, (list, tuple)) and any(isinstance(item, dict) for item in source_mutations):
        return True
    return _event_has_nested_source_tree_mutation(event)


def _event_has_nested_source_tree_mutation(event: dict[str, object]) -> bool:
    record = event.get("record")
    if isinstance(record, dict) and _source_tree_record_has_changes(record):
        return True
    side_effects = event.get("side_effects")
    if not isinstance(side_effects, (list, tuple)):
        return False
    for effect in side_effects:
        if not isinstance(effect, dict):
            continue
        if str(effect.get("kind") or "") != "source_tree_mutation":
            continue
        record = effect.get("record")
        if isinstance(record, dict) and _source_tree_record_has_changes(record):
            return True
    return False


def _source_tree_record_has_changes(record: dict[str, object]) -> bool:
    if _first_int(record.get("changed_count")) > 0:
        return True
    changes = record.get("changes")
    return isinstance(changes, (list, tuple)) and any(isinstance(item, dict) for item in changes)


def _latest_failure_event(events: list[dict[str, object]], *, min_sequence: int = -1) -> dict[str, object] | None:
    failures = [
        event
        for event in events
        if (
            _event_kind(event)
            in {
                "failure",
                "latest_failure",
                "verifier",
                "strict_verifier",
                "run_tests",
                "verifier_result",
                "structured_finish_gate",
                "source_mutation",
                "source_tree_mutation",
                "write",
                "edit",
                "apply_patch",
            }
            or _event_has_shell_source_side_effect(event)
        )
        and (_event_status(event) in {"failed", "interrupted", "invalid"} or _event_source_mutation_failed(event))
        and _event_sequence(event) >= min_sequence
    ]
    return max(failures, key=_event_sequence) if failures else None


def _latest_finish_proof_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    matches = [event for event in events if _event_is_finish_proof(event)]
    return max(matches, key=_event_sequence) if matches else None


def _event_is_finish_proof(event: dict[str, object]) -> bool:
    if _event_status(event) != "passed":
        return False
    intent = _event_execution_intent(event)
    if intent not in {"verify", "finish_verifier"}:
        return False
    return _event_kind(event) in {
        "strict_verifier",
        "verifier",
        "run_tests",
        "typed_evidence",
        "verifier_result",
    }


def _event_execution_intent(event: dict[str, object]) -> str:
    command_intent = str(event.get("command_intent") or event.get("intent") or "").strip().casefold()
    contract = _event_execution_contract(event)
    role = _contract_enum(contract, "role")
    purpose = _contract_enum(contract, "purpose")
    stage = _contract_enum(contract, "stage")
    proof_role = _contract_enum(contract, "proof_role")
    acceptance_kind = _contract_enum(contract, "acceptance_kind")
    kind = _event_kind(event)
    non_acceptance = acceptance_kind in {"not_acceptance", "progress_only"} or proof_role in {
        "none",
        "progress",
        "negative_diagnostic",
    }
    if command_intent in {"probe", "cheap_probe", "read", "inspect", "search"}:
        return "cheap_probe"
    if command_intent in {"diagnostic", "debug"}:
        return "diagnostic"
    if non_acceptance and role in {"source", "dependency", "artifact_probe", "unknown"}:
        return "cheap_probe"
    if non_acceptance or role == "diagnostic" or purpose == "diagnostic" or stage == "diagnostic":
        return "diagnostic"
    if acceptance_kind == "external_verifier" or proof_role in {"verifier", "final_artifact"}:
        return "finish_verifier"
    if role in {"verify", "test"} or purpose == "verification" or stage == "verification":
        return "verify"
    if acceptance_kind in {"candidate_final_proof", "candidate_artifact_proof", "candidate_runtime_smoke"}:
        return "finish_verifier"
    if role == "runtime" or purpose in {"runtime_build", "runtime_install", "smoke"}:
        return "runtime"
    if role == "build" or purpose == "build" or stage == "build" or proof_role == "target_build":
        return "build"
    if command_intent in {"verify", "test", "verifier"}:
        return "verify"
    if kind in {"strict_verifier", "verifier", "run_tests", "verifier_result"}:
        return "verify"
    return "cheap_probe"


def _event_execution_contract(event: dict[str, object]) -> dict[str, object]:
    raw = event.get("execution_contract")
    normalized = event.get("execution_contract_normalized")
    merged: dict[str, object] = {}
    if isinstance(raw, dict):
        merged.update(raw)
    if isinstance(normalized, dict):
        merged.update(normalized)
    return merged


def _contract_enum(contract: dict[str, object], key: str) -> str:
    return str(contract.get(key) or "").strip().casefold()


def _event_authored_completion_proof(event: dict[str, object]) -> bool:
    contract = _event_execution_contract(event)
    if not contract:
        return False
    acceptance_kind = _contract_enum(contract, "acceptance_kind")
    proof_role = _contract_enum(contract, "proof_role")
    if acceptance_kind in {"candidate_artifact_proof", "candidate_runtime_smoke", "candidate_final_proof", "external_verifier"}:
        return True
    if proof_role in {"target_build", "runtime_install", "default_smoke", "custom_runtime_smoke", "final_artifact", "verifier"}:
        return True
    if acceptance_kind in {"not_acceptance", "progress_only"} or proof_role in {
        "none",
        "progress",
        "negative_diagnostic",
    }:
        return False
    return bool(_expected_artifact_refs(contract) or _obligation_refs_from_value(contract.get("oracle_obligations")))


def _rejected_probe_proof_refs(events: list[dict[str, object]]) -> tuple[str, ...]:
    refs = []
    for event in events:
        if _event_execution_intent(event) in {"cheap_probe", "diagnostic"} and _event_authored_completion_proof(event):
            refs.append(_event_ref(event))
    return tuple(ref for ref in refs if ref)


def _missing_obligation_refs(events: list[dict[str, object]]) -> tuple[str, ...]:
    refs: set[str] = set()
    for event in events:
        for key in ("missing_obligations", "required_obligations", "oracle_obligations"):
            refs.update(_obligation_refs_from_value(event.get(key)))
        finish_gate = event.get("finish_gate") if isinstance(event.get("finish_gate"), dict) else {}
        refs.update(_obligation_refs_from_value(finish_gate.get("missing_obligations")))
        typed = event.get("typed_acceptance") if isinstance(event.get("typed_acceptance"), dict) else {}
        digest = typed.get("digest") if isinstance(typed.get("digest"), dict) else {}
        refs.update(_obligation_refs_from_value(digest.get("missing_obligations")))
    return tuple(sorted(refs))


def _finish_gate_support_refs(events: list[dict[str, object]], *, min_sequence: int) -> tuple[str, ...]:
    refs: set[str] = set()
    for event in events:
        if _event_sequence(event) < min_sequence:
            continue
        if _event_kind(event) not in {"finish_gate", "structured_finish_gate"}:
            continue
        if _event_status(event) != "passed":
            continue
        refs.update(_event_evidence_refs(event))
    return tuple(sorted(refs))


def _obligation_refs_from_value(value: object) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, str) and value.strip():
        refs.add(value.strip())
    elif isinstance(value, dict):
        for key in ("id", "obligation_id", "ref"):
            ref = str(value.get(key) or "").strip()
            if ref:
                refs.add(ref)
        subject = value.get("subject")
        if isinstance(subject, dict):
            subject_ref = str(subject.get("id") or subject.get("artifact_id") or subject.get("contract_id") or "").strip()
            if subject_ref:
                refs.add(subject_ref)
    elif isinstance(value, (list, tuple)):
        for item in value:
            refs.update(_obligation_refs_from_value(item))
    return refs


def _expected_artifact_refs(contract: dict[str, object]) -> set[str]:
    refs: set[str] = set()
    raw = contract.get("expected_artifacts")
    if not isinstance(raw, (list, tuple)):
        return refs
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref = str(item.get("id") or item.get("artifact_id") or item.get("path") or "").strip()
        if ref:
            refs.add(ref)
    return refs


def _latest_failure_is_current(facts: dict[str, object]) -> bool:
    return bool(facts.get("latest_failure")) and int(facts.get("latest_failure_sequence") or -1) >= int(
        facts.get("latest_mutation_sequence") or -1
    )


def _event_paths(event: object) -> set[str]:
    if not isinstance(event, dict):
        return set()
    paths: set[str] = set()
    for key in ("path", "target_path", "source_path", "changed_path"):
        value = str(event.get(key) or "").strip()
        if value:
            paths.add(value)
    for key in ("paths", "target_paths", "changed_paths", "changed_files", "source_paths"):
        value = event.get(key)
        if isinstance(value, (list, tuple)):
            paths.update(str(item).strip() for item in value if str(item).strip())
    source_mutation = event.get("source_mutation")
    if isinstance(source_mutation, dict):
        paths.update(_event_paths(source_mutation))
    source_mutations = event.get("source_mutations")
    if isinstance(source_mutations, (list, tuple)):
        for item in source_mutations:
            paths.update(_event_paths(item))
    record = event.get("record")
    if isinstance(record, dict):
        paths.update(_source_tree_record_paths(record))
    side_effects = event.get("side_effects")
    if isinstance(side_effects, (list, tuple)):
        for effect in side_effects:
            if not isinstance(effect, dict) or str(effect.get("kind") or "") != "source_tree_mutation":
                continue
            effect_record = effect.get("record")
            if isinstance(effect_record, dict):
                paths.update(_source_tree_record_paths(effect_record))
    return paths


def _source_tree_record_paths(record: dict[str, object]) -> set[str]:
    paths: set[str] = set()
    changes = record.get("changes")
    if isinstance(changes, (list, tuple)):
        for change in changes:
            if not isinstance(change, dict):
                continue
            path = str(change.get("path") or "").strip()
            if path:
                paths.add(path)
    return paths


def _event_evidence_refs(event: object) -> tuple[str, ...]:
    if not isinstance(event, dict):
        return ()
    refs = set()
    for key in ("evidence_ref", "event_ref", "command_run_id", "typed_evidence_id", "id", "event_id"):
        value = str(event.get(key) or "").strip()
        if value:
            refs.add(value)
    raw = event.get("evidence_refs")
    if isinstance(raw, (list, tuple)):
        refs.update(str(item).strip() for item in raw if str(item).strip())
    contract = _event_execution_contract(event)
    contract_id = str(contract.get("id") or contract.get("contract_id") or "").strip()
    contract_id = contract_id or str(event.get("contract_id") or "").strip()
    if contract_id:
        refs.add(contract_id)
    oracle = event.get("oracle_bundle") if isinstance(event.get("oracle_bundle"), dict) else {}
    oracle_id = str(oracle.get("id") or "").strip()
    if oracle_id:
        refs.add(oracle_id)
    finish_gate = event.get("finish_gate") if isinstance(event.get("finish_gate"), dict) else {}
    finish_id = str(finish_gate.get("id") or finish_gate.get("finish_gate_id") or "").strip()
    if finish_id:
        refs.add(finish_id)
    return tuple(sorted(refs))


def _evidence_index(events: list[dict[str, object]]) -> tuple[str, ...]:
    refs = set()
    for event in events:
        refs.update(_event_evidence_refs(event))
        ref = _event_ref(event)
        if ref:
            refs.add(ref)
    return tuple(sorted(refs))


def _paths_from_failure(value: object) -> tuple[str, ...]:
    return tuple(sorted(_event_paths(value)))


def _generic_failure_family(event: dict[str, object]) -> str:
    status = _event_status(event)
    kind = _event_kind(event)
    exit_code = _first_int(event.get("exit_code"), event.get("returncode"), -1)
    family_text = " ".join(
        str(event.get(key) or "")
        for key in (
            "family",
            "failure_class",
            "class",
            "failure_kind",
            "kind",
            "reason",
            "terminal_status",
        )
    ).lower()
    detail_text = _event_detail_text(event).lower()
    combined = f"{family_text} {detail_text}"
    if "first_write_due" in combined or "write_repair_required" in combined:
        return "write_required"
    if _event_has_shell_source_side_effect(event) and _event_source_mutation_failed(event):
        return "write_failure"
    if kind in {"write", "edit", "apply_patch", "source_mutation", "source_tree_mutation"} and _event_source_mutation_failed(event):
        return "write_failure"
    if exit_code == 127 or "command not found" in combined or "executable not found" in combined:
        return "command_not_found"
    if "artifact" in combined and any(term in combined for term in ("missing", "not created", "not found", "absent")):
        return "artifact_missing"
    if status in {"interrupted"} or any(term in combined for term in ("killed", "timeout", "timed out", "no output")):
        return "command_no_output_or_interrupted"
    if any(term in combined for term in ("runtime", "traceback", "segmentation fault", "opcode", " pc=", "program terminated")):
        return "runtime_diagnostic"
    if exit_code > 0 or "nonzero" in combined or "exit code" in combined:
        return "command_nonzero"
    if kind in {"verifier", "strict_verifier", "run_tests"} and status == "failed":
        return "verifier_failure"
    if status == "failed":
        return "command_nonzero"
    return "unknown_failure"


def _required_next_kind_for_generic_family(generic_family: str) -> WorkFrameNextKind:
    if generic_family == "command_not_found":
        return "cheap_probe"
    if generic_family in {"command_nonzero", "command_no_output_or_interrupted", "artifact_missing"}:
        return "inspect_latest_failure"
    return "patch_or_edit"


def _required_next_reason_for_generic_family(generic_family: str) -> str:
    if generic_family == "command_not_found":
        return "latest command was unavailable; choose an available fallback probe before repair"
    if generic_family == "command_nonzero":
        return "latest command failed generically; inspect the concrete failure before patching"
    if generic_family == "command_no_output_or_interrupted":
        return "latest command ended without enough output; inspect bounded command evidence before patching"
    if generic_family == "artifact_missing":
        return "expected artifact is missing; inspect producer or artifact path before repair"
    return "latest actionable failure should drive one focused repair"


def _actionable_summary(event: dict[str, object]) -> str:
    generic_candidate = ""
    for key in ("summary", "message", "failure_summary", "reason", "status"):
        value = str(event.get(key) or "").strip()
        if not value:
            continue
        if not _is_generic_actionable_summary(value):
            return value
        generic_candidate = generic_candidate or value
    for key in ("stderr_tail", "stdout_tail", "required_next_action", "required_next_probe", "diagnostic"):
        value = str(event.get(key) or "").strip()
        if value and not _is_generic_actionable_summary(value):
            return value
    return generic_candidate or "failure without actionable detail"


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
    ):
        value = event.get(key)
        if isinstance(value, (str, int, float, bool)):
            parts.append(str(value))
    return "\n".join(parts)


def _is_generic_actionable_summary(summary: str) -> bool:
    text = str(summary or "").strip().lower()
    if not text:
        return True
    normalized = " ".join(text.replace("_", " ").replace("-", " ").split())
    generic = {
        "failed",
        "failure",
        "error",
        "unknown",
        "nonzero",
        "nonzero exit",
        "exit code 1",
        "exit status 1",
        "killed",
        "timeout",
        "timed out",
        "interrupted",
    }
    if normalized in generic:
        return True
    if normalized.startswith("exit code ") and len(normalized.split()) <= 3:
        return True
    return False


def _has_low_budget_event(events: list[dict[str, object]]) -> bool:
    for event in events:
        if str(event.get("budget_class") or "").lower() in {"low", "closeout"}:
            return True
        if bool(event.get("budget_closeout_required")):
            return True
    return False


def _has_conflicting_event_sequences(events: Iterable[dict[str, object]]) -> bool:
    seen: dict[int, str] = {}
    for index, event in enumerate(events):
        sequence = _event_sequence(event)
        if sequence < 0:
            continue
        fingerprint = canonical_json(_canonical_event(event, index))
        if sequence in seen and seen[sequence] != fingerprint:
            return True
        seen[sequence] = fingerprint
    return False


def _normalize_root(value: str) -> str:
    normalized = str(value or "").replace("\\", "/").rstrip("/")
    return normalized


def _is_path_like_key(key: str) -> bool:
    lowered = key.lower()
    return lowered in {"path", "cwd", "workspace", "artifact", "filename", "file"} or lowered.endswith(
        ("_path", "_paths", "_file", "_files", "_dir", "_root")
    )


def _looks_like_path(value: str) -> bool:
    if not value or "\n" in value:
        return False
    normalized = value.replace("\\", "/")
    return normalized.startswith("/") or normalized.startswith("./") or normalized.startswith("../")


def _normalize_path_value(value: str, *, workspace_root: str = "", artifact_root: str = "") -> str:
    normalized = value.replace("\\", "/")
    if workspace_root and (normalized == workspace_root or normalized.startswith(workspace_root + "/")):
        return _join_placeholder_path("$WORKSPACE", normalized.removeprefix(workspace_root).lstrip("/"))
    if artifact_root and (normalized == artifact_root or normalized.startswith(artifact_root + "/")):
        return _join_placeholder_path("$ARTIFACT", normalized.removeprefix(artifact_root).lstrip("/"))
    if normalized.startswith("/"):
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
        return _join_placeholder_path(f"$ABSOLUTE/{digest}", posixpath.basename(normalized.rstrip("/")))
    return posixpath.normpath(normalized) if "/" in normalized else normalized


def _join_placeholder_path(prefix: str, relative: str) -> str:
    if not relative:
        return prefix
    return prefix + "/" + posixpath.normpath(relative)


def _first_tool_turn(history: list[dict[str, object]], tools: set[str]) -> dict[str, object]:
    for fallback_index, entry in enumerate(history, start=1):
        turn = _first_int(entry.get("turn"), entry.get("turn_index"), fallback_index)
        for call in entry.get("tool_calls") or []:
            if isinstance(call, dict) and str(call.get("tool_name") or call.get("name") or "") in tools:
                return {"turn": turn, "seconds": _first_float(entry.get("elapsed_seconds"), call.get("elapsed_seconds"))}
    return {"turn": 0, "seconds": 0.0}


def _first_verifier_turn(history: list[dict[str, object]]) -> dict[str, object]:
    verifier_tools = {"run_tests"}
    for fallback_index, entry in enumerate(history, start=1):
        turn = _first_int(entry.get("turn"), entry.get("turn_index"), fallback_index)
        for call in entry.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            tool_name = str(call.get("tool_name") or call.get("name") or "")
            arguments = _mapping(call.get("arguments"))
            command = str(arguments.get("command") or arguments.get("cmd") or "").lower()
            intent = str(arguments.get("command_intent") or "").lower()
            if tool_name in verifier_tools or "verify" in intent or "test" in intent or "pytest" in command:
                return {"turn": turn, "seconds": _first_float(entry.get("elapsed_seconds"), call.get("elapsed_seconds"))}
    return {"turn": 0, "seconds": 0.0}


def _count_tool_calls(history: list[dict[str, object]]) -> int:
    return sum(len(entry.get("tool_calls") or []) for entry in history)


def _same_family_repeats(history: list[dict[str, object]]) -> int:
    families: list[str] = []
    for entry in history:
        for result in entry.get("tool_results") or []:
            if not isinstance(result, dict):
                continue
            content = result.get("content")
            if isinstance(content, dict):
                latest = content.get("latest_failure")
                if isinstance(latest, dict):
                    families.append(str(latest.get("class") or latest.get("family") or latest.get("kind") or "unknown"))
    counts: dict[str, int] = {}
    for family in families:
        counts[family] = counts.get(family, 0) + 1
    return sum(max(0, count - 1) for count in counts.values())


def _first_int(*values: object) -> int:
    for value in values:
        try:
            if value is None or value == "":
                continue
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _first_float(*values: object) -> float:
    for value in values:
        try:
            if value is None or value == "":
                continue
            return max(0.0, float(value))
        except (TypeError, ValueError):
            continue
    return 0.0


__all__ = [
    "LEGACY_PROMPT_PROJECTION_IDS",
    "WORKFRAME_CANONICALIZER_VERSION",
    "WORKFRAME_DEBUG_BUNDLE_FILES",
    "WORKFRAME_PHASE0_SCHEMA_VERSION",
    "WORKFRAME_REDUCER_SCHEMA_VERSION",
    "WORKFRAME_SCHEMA_VERSION",
    "WORKFRAME_TARGET_MAX_BYTES",
    "WORKFRAME_RED_MAX_BYTES",
    "WorkFrame",
    "WorkFrameChangedSources",
    "WorkFrameEvidenceRefs",
    "WorkFrameFinishReadiness",
    "WorkFrameForbiddenNext",
    "WorkFrameGoal",
    "WorkFrameInputs",
    "WorkFrameInvariantReport",
    "WorkFrameLatestActionable",
    "WorkFrameRequiredNext",
    "WorkFrameTrace",
    "canonical_json",
    "canonicalize_workframe_inputs",
    "check_phase0_prompt_inventory",
    "phase0_baseline_bands",
    "record_phase0_baseline_metrics",
    "reduce_workframe",
    "validate_workframe",
    "workframe_output_hash",
    "workframe_debug_bundle_format",
]
