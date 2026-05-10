from mew.implement_lane.workframe import WorkFrameInputs, reduce_workframe, workframe_output_hash
from mew.implement_lane.workframe_variant_minimal import VARIANT_NAME, reduce_minimal_workframe


def test_minimal_runtime_failure_keeps_actionable_without_repair_required_next() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-3",
        task_id="task-1",
        objective="Repair the workspace to satisfy the configured verifier.",
        success_contract_ref="task-contract:verify",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "patch-1",
                "path": "src/runtime.py",
                "evidence_refs": ["sidecar:patch-1"],
            },
            {
                "kind": "strict_verifier",
                "event_sequence": 2,
                "event_id": "verify-2",
                "status": "failed",
                "family": "runtime_verifier_failure",
                "summary": "RuntimeError: loader rejected generated artifact header",
                "target_paths": ["src/runtime.py"],
                "typed_evidence_id": "ev:verify-2",
                "execution_contract_normalized": {
                    "id": "contract:verify-2",
                    "role": "verify",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
            },
        ),
    )

    current, current_report = reduce_workframe(inputs)
    workframe, report = reduce_minimal_workframe(inputs)

    assert VARIANT_NAME == "minimal"
    assert current_report.status == "pass"
    assert current.required_next
    assert current.required_next.kind == "patch_or_edit"
    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_verifier_failure"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "runtime_verifier_failure"
    assert workframe.latest_actionable.summary == "RuntimeError: loader rejected generated artifact header"
    assert workframe.required_next is None
    assert workframe.finish_readiness.state == "not_ready"
    assert "verifier_failed" in workframe.finish_readiness.blockers
    assert "finish" in [item.kind for item in workframe.forbidden_next]
    assert workframe.trace.output_hash == workframe_output_hash(workframe)


def test_minimal_preserves_verifier_required_next_when_mutation_makes_finish_stale() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-4",
        task_id="task-1",
        objective="Do not finish when source changed after verifier evidence.",
        success_contract_ref="task-contract:verify",
        sidecar_events=(
            {
                "kind": "strict_verifier",
                "event_sequence": 1,
                "event_id": "verify-1",
                "status": "passed",
                "typed_evidence_id": "ev:verify-1",
                "execution_contract_normalized": {
                    "id": "contract:verify-1",
                    "role": "verify",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
            },
            {
                "kind": "source_mutation",
                "event_sequence": 2,
                "event_id": "patch-2",
                "path": "src/runtime.py",
                "evidence_refs": ["sidecar:patch-2"],
            },
        ),
    )

    workframe, report = reduce_minimal_workframe(inputs)

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.changed_sources.since_last_strict_verifier is True
    assert workframe.verifier_state.fresh_after_latest_source_mutation is False
    assert workframe.finish_readiness.state == "not_ready"
    assert "verifier_stale_after_mutation" in workframe.finish_readiness.blockers
    assert workframe.latest_actionable
    assert workframe.latest_actionable.generic_family == "verifier_stale_after_mutation"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.evidence_refs == ("sidecar:patch-2",)
    assert "finish" in [item.kind for item in workframe.forbidden_next]


def test_minimal_preserves_finish_required_next_with_evidence_refs_when_ready() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-5",
        task_id="task-1",
        objective="Finish only after fresh verifier evidence.",
        success_contract_ref="task-contract:verify",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "patch-1",
                "path": "src/runtime.py",
                "evidence_refs": ["sidecar:patch-1"],
            },
            {
                "kind": "strict_verifier",
                "event_sequence": 2,
                "event_id": "verify-2",
                "status": "passed",
                "typed_evidence_id": "ev:verify-2",
                "execution_contract_normalized": {
                    "id": "contract:verify-2",
                    "role": "verify",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
            },
            {
                "kind": "structured_finish_gate",
                "event_sequence": 3,
                "id": "finish:gate-2",
                "status": "passed",
                "observed": {"blocked": False},
            },
        ),
    )

    current, current_report = reduce_workframe(inputs)
    workframe, report = reduce_minimal_workframe(inputs)

    assert current_report.status == "pass"
    assert current.required_next
    assert current.required_next.kind == "finish"
    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.finish_readiness.state == "ready"
    assert workframe.changed_sources.since_last_strict_verifier is False
    assert workframe.verifier_state.fresh_after_latest_source_mutation is True
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"
    assert "ev:verify-2" in workframe.required_next.evidence_refs
    assert "finish:gate-2" in workframe.required_next.evidence_refs
