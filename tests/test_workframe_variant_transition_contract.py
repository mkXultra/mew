import json
from pathlib import Path

from mew.implement_lane.workframe import WORKFRAME_RED_MAX_BYTES, WorkFrameInputs, reduce_workframe, workframe_output_hash
from mew.implement_lane.workframe_variants import DEFAULT_WORKFRAME_VARIANT, reduce_workframe_with_variant
from mew.implement_lane.workframe_variant_transition_contract import (
    VARIANT_NAME,
    reduce_transition_contract_workframe,
)


FIXTURES = Path(__file__).parent / "fixtures" / "implement_v2"


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


def _runtime_artifact_repeat_fixture() -> tuple[WorkFrameInputs, dict[str, object]]:
    payload = json.loads((FIXTURES / "transition_contract_runtime_artifact_missing.json").read_text())
    raw = payload["workframe_inputs"]
    return (
        WorkFrameInputs(
            attempt_id=raw["attempt_id"],
            turn_id=raw["turn_id"],
            task_id=raw["task_id"],
            objective=raw["objective"],
            success_contract_ref=raw["success_contract_ref"],
            sidecar_events=tuple(raw["sidecar_events"]),
        ),
        payload["expected"],
    )


def test_transition_contract_fixture_identifies_runtime_artifact_repeat() -> None:
    inputs, expected = _runtime_artifact_repeat_fixture()

    workframe, report = reduce_transition_contract_workframe(inputs)

    assert report.status == "pass"
    assert workframe.required_next
    assert workframe.required_next.kind == expected["required_next_kind"]
    assert workframe.required_next.inspection_target_paths == ("vm.js", "first_frame.ppm")
    assert "forbidden by transition_contract.runtime_artifact_missing.repeat_requires_inspection" in {
        item.reason for item in workframe.forbidden_next
    }
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    runtime_transition = contract["runtime_artifact_transition"]
    assert runtime_transition["rule_id"] == expected["rule_id"]
    assert runtime_transition["artifact_path"] == expected["artifact_path"]
    assert runtime_transition["producer_paths"] == [expected["producer_path"]]
    assert runtime_transition["repeat_count"] == expected["repeat_count"]
    assert runtime_transition["repeat_key"] == expected["repeat_key"]


def test_transition_contract_keeps_runtime_artifact_repeat_under_workframe_cap() -> None:
    inputs, expected = _runtime_artifact_repeat_fixture()
    events: list[dict[str, object]] = []
    for index, event in enumerate(inputs.sidecar_events):
        updated = dict(event)
        updated["evidence_refs"] = [
            (
                "contract:implement_v2:attempt:turn:full:command:"
                f"call-{index}-very-long-command-name-for-runtime-artifact-repeat-{index:02d}-abcdef1234567890"
            ),
            (
                "implement-v2-evidence://implement_v2:attempt:turn:full/tool_run_record/"
                f"tool-run-record-call-{index}-runtime-artifact-repeat-yielded-abcdef1234567890"
            ),
        ]
        events.append(updated)
    for sequence in range(6, 15):
        events.insert(
            -1,
            {
                "kind": "verifier",
                "event_sequence": sequence,
                "event_id": f"probe-{sequence}",
                "status": "failed",
                "summary": f"prior verifier failure {sequence}",
                "evidence_refs": [
                    (
                        "contract:implement_v2:attempt:turn:full:command:"
                        f"call-{sequence}-probe-runtime-context-long-ref-abcdef1234567890"
                    )
                ],
                "execution_contract_normalized": {
                    "id": (
                        "contract:implement_v2:attempt:turn:full:command:"
                        f"call-{sequence}-probe-runtime-context-long-ref-abcdef1234567890"
                    )
                },
            },
        )

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert len(json.dumps(workframe.as_dict(), ensure_ascii=False, sort_keys=True)) < WORKFRAME_RED_MAX_BYTES
    assert workframe.required_next
    assert workframe.required_next.kind == expected["required_next_kind"]
    assert workframe.required_next.target_paths == ("vm.js",)
    assert workframe.required_next.evidence_refs
    assert any(str(ref).startswith("artifact-evidence:") for ref in workframe.required_next.evidence_refs)
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    runtime_transition = contract["runtime_artifact_transition"]
    assert runtime_transition["rule_id"] == expected["rule_id"]
    assert runtime_transition["artifact_path"] == expected["artifact_path"]
    assert runtime_transition["producer_paths"] == [expected["producer_path"]]
    assert "evidence_refs" not in runtime_transition


def test_transition_contract_blocks_runtime_artifact_repeat_beyond_budget() -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events)
    for sequence in (51, 52):
        repeated = dict(events[-1])
        repeated["event_id"] = f"tool-result:call-{sequence}-verify-first-frame"
        repeated["event_sequence"] = sequence
        repeated["command_run_id"] = f"command:call-{sequence}"
        repeated["evidence_refs"] = [
            f"tool-run-record:call-{sequence}:interrupted",
            f"artifact-evidence:/app/first_frame.ppm:call-{sequence}",
        ]
        events.append(repeated)

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "blocked"
    assert workframe.required_next
    assert workframe.required_next.kind == "blocked"
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    runtime_transition = contract["runtime_artifact_transition"]
    assert runtime_transition["rule_id"] == "transition_contract.runtime_artifact_missing.repeat_budget_exhausted"
    assert runtime_transition["repeat_count"] == 4
    assert {"patch_or_edit", "run_verifier", "finish"} <= {item.kind for item in workframe.forbidden_next}


def test_transition_contract_does_not_reopen_runtime_artifact_miss_after_passing_verifier() -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events[:2])
    events.append(
        {
            "event_id": "tool-result:call-48-fix-producer",
            "event_sequence": 48,
            "evidence_refs": ["implement-v2-write://attempt/call-48/mutation"],
            "kind": "apply_patch",
            "path": "$WORKSPACE/vm.js",
            "status": "completed",
            "target_paths": ["$WORKSPACE/vm.js"],
        }
    )
    events.append(
        {
            "event_id": "tool-result:call-49-verify-first-frame",
            "event_sequence": 49,
            "evidence_refs": ["ev:verify-pass"],
            "kind": "strict_verifier",
            "status": "passed",
            "typed_evidence_id": "ev:verify-pass",
            "execution_contract_normalized": {
                "id": "contract:call-49",
                "role": "verify",
                "proof_role": "verifier",
                "acceptance_kind": "external_verifier",
            },
        }
    )

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"


def test_transition_contract_does_not_reopen_runtime_artifact_miss_after_shell_source_mutation() -> None:
    _assert_runtime_miss_resolved_by_source_mutation(
        {
            "event_id": "tool-result:call-48-generate-vm",
            "event_sequence": 48,
            "evidence_refs": ["command:call-48", "source-tree-mutation:call-48"],
            "kind": "run_command",
            "status": "passed",
            "source_tree_mutation": True,
            "changed_files": ["$WORKSPACE/vm.js"],
            "summary": "generated vm.js from shell command",
        }
    )


def test_transition_contract_does_not_reopen_runtime_artifact_miss_after_truthy_shell_mutation_payload() -> None:
    _assert_runtime_miss_resolved_by_source_mutation(
        {
            "event_id": "tool-result:call-48-generate-vm",
            "event_sequence": 48,
            "evidence_refs": ["command:call-48", "source-tree-mutation:call-48"],
            "kind": "run_command",
            "status": "passed",
            "source_tree_mutation": {"path": "$WORKSPACE/vm.js"},
            "summary": "generated vm.js from shell command",
        }
    )


def test_transition_contract_does_not_reopen_runtime_artifact_miss_after_source_mutations_list() -> None:
    _assert_runtime_miss_resolved_by_source_mutation(
        {
            "event_id": "tool-result:call-48-generate-vm",
            "event_sequence": 48,
            "evidence_refs": ["command:call-48", "source-tree-mutation:call-48"],
            "kind": "run_command",
            "status": "passed",
            "source_mutations": [{"path": "$WORKSPACE/vm.js"}],
            "summary": "generated vm.js from shell command",
        }
    )


def _assert_runtime_miss_resolved_by_source_mutation(mutation_event: dict[str, object]) -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events[:2])
    events.append(mutation_event)

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"


def test_transition_contract_ignores_unrelated_post_failure_inspection() -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events[:2])
    events.append(
        {
            "event_id": "tool-result:call-48-read-readme",
            "event_sequence": 48,
            "evidence_refs": ["inspect:readme"],
            "kind": "inspection",
            "status": "completed",
            "summary": "read README.md for unrelated setup notes",
            "target_paths": ["$WORKSPACE/README.md"],
        }
    )

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert workframe.required_next
    assert workframe.required_next.kind == "inspect_latest_failure"
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    runtime_transition = contract["runtime_artifact_transition"]
    assert runtime_transition["rule_id"] == "transition_contract.runtime_artifact_missing.unrelated_inspection_requires_tied_inspection"
    assert "README" not in workframe.required_next.reason


def test_transition_contract_does_not_match_unrelated_short_artifact_stem() -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events[:2])
    events.append(
        {
            "event_id": "tool-result:call-48-read-framework-notes",
            "event_sequence": 48,
            "evidence_refs": ["inspect:framework-notes"],
            "kind": "inspection",
            "status": "completed",
            "summary": "read framework setup notes from README.md",
            "target_paths": ["$WORKSPACE/README.md"],
        }
    )

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    assert workframe.required_next
    assert workframe.required_next.kind == "inspect_latest_failure"
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    assert (
        contract["runtime_artifact_transition"]["rule_id"]
        == "transition_contract.runtime_artifact_missing.unrelated_inspection_requires_tied_inspection"
    )


def test_transition_contract_ties_workspace_prefixed_artifact_inspection_by_path_key() -> None:
    inputs, _expected = _runtime_artifact_repeat_fixture()
    events = list(inputs.sidecar_events[:2])
    events.append(
        {
            "event_id": "tool-result:call-48-read-first-frame",
            "event_sequence": 48,
            "evidence_refs": ["inspect:first-frame"],
            "kind": "inspection",
            "status": "completed",
            "summary": "read file",
            "target_paths": ["$WORKSPACE/first_frame.ppm"],
        }
    )

    workframe, report = reduce_transition_contract_workframe(
        WorkFrameInputs(
            attempt_id=inputs.attempt_id,
            turn_id=inputs.turn_id,
            task_id=inputs.task_id,
            objective=inputs.objective,
            success_contract_ref=inputs.success_contract_ref,
            sidecar_events=tuple(events),
        )
    )

    assert report.status == "pass"
    contract = workframe.latest_actionable.recovery_hint["transition_contract"]
    runtime_transition = contract["runtime_artifact_transition"]
    assert runtime_transition["rule_id"] == "transition_contract.runtime_artifact_missing.inspection_enables_patch"
    assert "first_frame.ppm" in workframe.required_next.inspection_target_paths
