from mew.implement_lane.workframe import WorkFrameInputs, reduce_workframe, workframe_output_hash
from mew.implement_lane.workframe_variants import DEFAULT_WORKFRAME_VARIANT, reduce_workframe_with_variant
from mew.implement_lane.workframe_variant_transition_contract import (
    VARIANT_NAME,
    reduce_transition_contract_workframe,
)


def _verifier_failure_after_mutation_inputs() -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Repair the workspace to satisfy the configured verifier.",
        success_contract_ref="task-contract:pytest",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "patch-1",
                "status": "passed",
                "path": "src/app.py",
                "evidence_refs": ["sidecar:patch-1"],
            },
            {
                "kind": "strict_verifier",
                "event_sequence": 2,
                "event_id": "verify-2",
                "status": "failed",
                "family": "verifier_failure",
                "summary": "pytest reports assertion failure in test_app",
                "target_paths": ["src/app.py"],
                "typed_evidence_id": "ev:verify-2",
                "evidence_refs": ["tool-result:verify-2"],
                "execution_contract_normalized": {
                    "id": "contract:verify-2",
                    "role": "verify",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
            },
        ),
    )


def test_transition_contract_marks_verifier_failure_after_source_mutation() -> None:
    workframe, report = reduce_transition_contract_workframe(_verifier_failure_after_mutation_inputs())

    assert VARIANT_NAME == "transition_contract"
    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_verifier_failure"
    assert workframe.latest_actionable
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"
    assert workframe.required_next.target_paths == ("src/app.py",)
    assert "sidecar:patch-1" in workframe.required_next.evidence_refs
    assert "ev:verify-2" in workframe.required_next.evidence_refs
    assert "contract:verify-2" in workframe.required_next.evidence_refs
    assert workframe.required_next.after.startswith("run_configured_verifier")
    assert "transition_rule=transition_contract.verifier_failure_after_mutation" in workframe.required_next.after
    assert "provenance_refs=" in workframe.required_next.after
    assert "finish" in {item.kind for item in workframe.forbidden_next}

    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    assert contract["latest_observation"]["source_ref"] == "ev:verify-2"
    assert contract["latest_observation"]["kind"] == "strict_verifier"
    assert contract["evidence_delta"]["latest_mutation_ref"] == "sidecar:patch-1"
    assert contract["state_transition"]["from_phase"] == "verify_after_mutation"
    assert contract["state_transition"]["to_phase"] == "repair_after_verifier_failure"
    assert contract["state_transition"]["rule_id"] == "transition_contract.verifier_failure_after_mutation"
    assert "sidecar:patch-1" in contract["state_transition"]["provenance_refs"]
    assert contract["next_action_contract"]["kind"] == "patch_or_edit"
    assert "ev:verify-2" in contract["next_action_contract"]["evidence_refs"]


def test_transition_contract_leaves_non_state_changing_latest_event_current_compatible() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Verify source mutation before finish.",
        success_contract_ref="task-contract:pytest",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "patch-1",
                "status": "passed",
                "path": "src/app.py",
                "evidence_refs": ["sidecar:patch-1"],
            },
            {
                "kind": "context_compression",
                "event_sequence": 2,
                "event_id": "compression-2",
                "status": "completed",
                "summary": "replayed current WorkFrame without new tool evidence",
                "evidence_refs": ["replay:compression-2"],
            },
        ),
    )

    current, current_report = reduce_workframe(inputs)
    variant, variant_report = reduce_transition_contract_workframe(inputs)

    assert current_report.status == "pass"
    assert variant_report.status == "pass"
    assert variant.as_dict() == current.as_dict()


def test_transition_contract_output_hash_is_deterministic_across_replay() -> None:
    inputs = _verifier_failure_after_mutation_inputs()

    first, first_report = reduce_transition_contract_workframe(inputs)
    second, second_report = reduce_transition_contract_workframe(inputs)
    third, third_report = reduce_transition_contract_workframe(inputs)

    assert first_report.status == "pass"
    assert second_report.status == "pass"
    assert third_report.status == "pass"
    assert first.as_dict() == second.as_dict() == third.as_dict()
    assert first.trace.output_hash == second.trace.output_hash == third.trace.output_hash
    assert first.trace.output_hash == workframe_output_hash(first)


def test_default_variant_dispatches_transition_contract_and_current_alias_dispatches_current() -> None:
    inputs = _verifier_failure_after_mutation_inputs()

    default, default_report = reduce_workframe_with_variant(inputs)
    transition, transition_report = reduce_transition_contract_workframe(inputs)
    explicit_current, explicit_current_report = reduce_workframe_with_variant(inputs, variant="current")
    current, current_report = reduce_workframe(inputs)

    assert DEFAULT_WORKFRAME_VARIANT == "transition_contract"
    assert default_report.status == "pass"
    assert transition_report.status == "pass"
    assert explicit_current_report.status == "pass"
    assert current_report.status == "pass"
    assert default.as_dict() == transition.as_dict()
    assert explicit_current.as_dict() == current.as_dict()
