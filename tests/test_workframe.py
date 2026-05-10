import json

import pytest

from mew.implement_lane.workframe import (
    LEGACY_PROMPT_PROJECTION_IDS,
    WorkFrameInputs,
    canonicalize_workframe_inputs,
    check_phase0_prompt_inventory,
    record_phase0_baseline_metrics,
    reduce_workframe,
    workframe_debug_bundle_format,
    workframe_output_hash,
)


def _workframe_inputs() -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-3",
        task_id="task-1",
        objective="Repair the workspace to satisfy the configured verifier.",
        success_contract_ref="task-contract:verify",
        constraints=("use_workspace_tools", "no_task_specific_solver"),
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "vm.js",
                "evidence_refs": ["sidecar:write:1"],
                "timestamp": "volatile",
            },
            {
                "kind": "strict_verifier",
                "event_sequence": 2,
                "event_id": "cmd-2",
                "status": "failed",
                "family": "runtime_verifier_failure",
                "summary": "TypeError: this.check is not a function",
                "target_paths": ["vm.js"],
                "command_run_id": "cmd:run-2",
                "evidence_refs": ["ev:verifier:run-2"],
            },
        ),
    )


def test_workframe_reducer_is_deterministic_and_evidence_referenced() -> None:
    inputs = _workframe_inputs()

    first, first_report = reduce_workframe(inputs)
    second, second_report = reduce_workframe(inputs)

    assert first_report.status == "pass"
    assert second_report.status == "pass"
    assert first.as_dict() == second.as_dict()
    assert first.current_phase == "repair_after_verifier_failure"
    assert first.latest_actionable
    assert first.latest_actionable.family == "runtime_verifier_failure"
    assert first.required_next
    assert first.required_next.kind == "patch_or_edit"
    assert first.required_next.target_paths == ("vm.js",)
    assert "finish" in [item.kind for item in first.forbidden_next]
    assert first.changed_sources.since_last_strict_verifier is True
    assert first.verifier_state.status == "failed"
    assert "ev:verifier:run-2" in first.evidence_refs.typed
    assert first.trace.output_hash == workframe_output_hash(first)
    serialized = first.as_dict()
    assert set(serialized) >= {
        "latest_actionable",
        "required_next",
        "forbidden_next",
        "changed_sources",
        "verifier_state",
        "finish_readiness",
        "evidence_refs",
    }


def test_workframe_canonicalization_removes_volatile_fields_and_is_stable() -> None:
    inputs = _workframe_inputs()
    canonical = canonicalize_workframe_inputs(inputs)
    serialized = json.dumps(canonical, sort_keys=True)

    assert "volatile" not in serialized
    assert canonical["reducer_schema_version"] == 1
    events = canonical["payload"]["sidecar_events"]
    assert [event["event_sequence"] for event in events] == [1, 2]


def test_workframe_canonicalization_normalizes_nested_volatility_and_roots() -> None:
    left = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        workspace_root="/tmp/work-a",
        artifact_root="/tmp/artifacts-a",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "payload": {
                    "path": "/tmp/work-a/src/vm.js",
                    "pid": 111,
                    "nested": {"mtime": 123, "provider_latency_ms": 9.0},
                },
                "artifact_path": "/tmp/artifacts-a/run/output.log",
            },
        ),
    )
    right = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        workspace_root="/var/work-b",
        artifact_root="/var/artifacts-b",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "payload": {
                    "path": "/var/work-b/src/vm.js",
                    "pid": 222,
                    "nested": {"mtime": 999, "provider_latency_ms": 42.0},
                },
                "artifact_path": "/var/artifacts-b/run/output.log",
            },
        ),
    )

    assert canonicalize_workframe_inputs(left) == canonicalize_workframe_inputs(right)
    serialized = json.dumps(canonicalize_workframe_inputs(left), sort_keys=True)
    assert "/tmp/work-a" not in serialized
    assert "$WORKSPACE/src/vm.js" in serialized
    assert "$ARTIFACT/run/output.log" in serialized
    assert "provider_latency" not in serialized


def test_workframe_canonicalization_preserves_distinct_unrooted_absolute_paths() -> None:
    left = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "/tmp/a/out.log",
            },
        ),
    )
    right = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "/var/b/out.log",
            },
        ),
    )

    left_serialized = json.dumps(canonicalize_workframe_inputs(left), sort_keys=True)
    right_serialized = json.dumps(canonicalize_workframe_inputs(right), sort_keys=True)

    assert left_serialized != right_serialized
    assert "/tmp/a/out.log" not in left_serialized
    assert "/var/b/out.log" not in right_serialized
    assert "$ABSOLUTE/" in left_serialized
    assert "$ABSOLUTE/" in right_serialized


def test_workframe_failed_write_is_not_counted_as_source_mutation() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Repair failed write handling.",
        sidecar_events=(
            {
                "kind": "write",
                "event_sequence": 1,
                "event_id": "write-1",
                "status": "failed",
                "family": "write_payload_invalid",
                "summary": "write_file payload was invalid",
                "path": "vm.js",
                "evidence_refs": ["ev:write-failed"],
            },
        ),
    )

    workframe, report = reduce_workframe(inputs)

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_write_failure"
    assert workframe.changed_sources.paths == ()
    assert workframe.changed_sources.since_last_strict_verifier is False
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "write_payload_invalid"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"


def test_workframe_ignores_stale_verifier_failure_after_source_mutation() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Repair stale verifier handling.",
        sidecar_events=(
            {
                "kind": "strict_verifier",
                "event_sequence": 1,
                "event_id": "verify-1",
                "status": "failed",
                "family": "old_runtime_failure",
                "summary": "old failure before patch",
                "evidence_refs": ["ev:old-failure"],
            },
            {
                "kind": "source_mutation",
                "event_sequence": 2,
                "event_id": "patch-2",
                "path": "vm.js",
                "evidence_refs": ["sidecar:patch-2"],
            },
        ),
    )

    workframe, report = reduce_workframe(inputs)

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "verifier_stale_after_mutation"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert "old_runtime_failure" not in json.dumps(workframe.as_dict(), sort_keys=True)


def test_workframe_phase4_shell_source_side_effect_counts_as_mutation() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Verify after shell source side effects.",
            sidecar_events=(
                {
                    "kind": "run_command",
                    "event_sequence": 1,
                    "event_id": "cmd-shell-write",
                    "status": "passed",
                    "command_run_id": "cmd:shell-write",
                    "source_side_effect": True,
                    "source_mutation": {"path": "src/generated.py"},
                    "evidence_refs": ["sidecar:shell-source-mutation"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.changed_sources.paths == ("src/generated.py",)
    assert workframe.changed_sources.since_last_strict_verifier is True
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert "finish" in [item.kind for item in workframe.forbidden_next]


def test_workframe_phase4_source_tree_mutation_record_after_verifier_blocks_finish() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Do not finish after a source_tree_mutation record.",
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
                    "kind": "source_tree_mutation",
                    "event_sequence": 2,
                    "event_id": "mutation-2",
                    "record": {
                        "changed_count": 1,
                        "changes": [{"path": "src/generated.py", "change": "modified"}],
                    },
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.changed_sources.paths == ("src/generated.py",)
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"


def test_workframe_phase4_nested_side_effect_source_tree_mutation_counts_as_mutation() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Represent nested side effect mutation facts.",
            sidecar_events=(
                {
                    "kind": "run_command",
                    "event_sequence": 1,
                    "event_id": "cmd-1",
                    "status": "passed",
                    "side_effects": [
                        {
                            "kind": "source_tree_mutation",
                            "record": {
                                "changed_count": 1,
                                "changes": [{"path": "src/generated.py", "change": "added"}],
                            },
                        }
                    ],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.changed_sources.paths == ("src/generated.py",)
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"


def test_workframe_phase4_shell_source_side_effect_with_later_verifier_can_finish() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Finish after verifier covers shell source side effects.",
            sidecar_events=(
                {
                    "kind": "run_command",
                    "event_sequence": 1,
                    "event_id": "cmd-shell-write",
                    "status": "passed",
                    "source_tree_mutation": True,
                    "changed_files": ["src/generated.py"],
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
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.changed_sources.paths == ("src/generated.py",)
    assert workframe.verifier_state.fresh_after_latest_source_mutation is True
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"


def test_workframe_phase4_blocked_shell_source_mutation_projects_write_repair() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Repair blocked shell source mutation.",
            sidecar_events=(
                {
                    "kind": "run_command",
                    "event_sequence": 1,
                    "event_id": "cmd-blocked-shell-write",
                    "status": "invalid",
                    "policy_blocked_source_mutation": True,
                    "source_mutation": {"path": "src/generated.py"},
                    "family": "run_command_source_mutation_verifier_compound",
                    "summary": "shell command mixed source mutation and verifier in one action",
                    "evidence_refs": ["ev:shell-mutation-blocked"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_write_failure"
    assert workframe.changed_sources.paths == ()
    assert workframe.latest_actionable
    assert workframe.latest_actionable.generic_family == "write_failure"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"


def test_workframe_phase4_blocked_status_projects_write_repair_not_verify() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Blocked shell source mutation should be repaired, not verified.",
            sidecar_events=(
                {
                    "kind": "run_command",
                    "event_sequence": 1,
                    "event_id": "cmd-blocked-shell-write",
                    "status": "blocked",
                    "policy_blocked_source_mutation": True,
                    "source_mutation": {"path": "src/generated.py"},
                    "summary": "shell source mutation was blocked by policy",
                    "evidence_refs": ["ev:shell-mutation-blocked"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_write_failure"
    assert workframe.changed_sources.paths == ()
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"


@pytest.mark.parametrize(
    ("event", "expected_generic", "expected_next"),
    [
        (
            {
                "kind": "verifier",
                "status": "failed",
                "exit_code": 127,
                "stderr_tail": "sh: rg: command not found",
            },
            "command_not_found",
            "cheap_probe",
        ),
        (
            {
                "kind": "verifier",
                "status": "failed",
                "exit_code": 2,
                "stderr_tail": "unit test failed in parser fixture",
            },
            "command_nonzero",
            "inspect_latest_failure",
        ),
        (
            {
                "kind": "verifier",
                "status": "killed",
                "reason": "no observable output before managed command budget",
            },
            "command_no_output_or_interrupted",
            "inspect_latest_failure",
        ),
        (
            {
                "kind": "verifier",
                "status": "failed",
                "stderr_tail": "Program terminated at PC=0x40c848 after unsupported opcode",
            },
            "runtime_diagnostic",
            "patch_or_edit",
        ),
        (
            {
                "kind": "verifier",
                "status": "failed",
                "failure_class": "artifact_validation_failure",
                "summary": "expected artifact frame.bmp was missing after verifier",
            },
            "artifact_missing",
            "inspect_latest_failure",
        ),
        (
            {
                "kind": "write",
                "status": "failed",
                "summary": "edit_file old text did not match current source",
                "path": "vm.js",
            },
            "write_failure",
            "patch_or_edit",
        ),
    ],
)
def test_workframe_phase2_latest_actionable_reduces_to_generic_category(
    event: dict[str, object], expected_generic: str, expected_next: str
) -> None:
    event = {
        "event_sequence": 1,
        "event_id": "event-1",
        "evidence_refs": ["ev:event-1"],
        **event,
    }

    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Repair the current failure.",
            sidecar_events=(event,),
        )
    )

    assert report.status == "pass"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.generic_family == expected_generic
    assert workframe.required_next
    assert workframe.required_next.kind == expected_next
    assert workframe.required_next.evidence_refs == ("ev:event-1", "event-1")


def test_workframe_phase2_verifier_pass_reduces_to_finish_ready() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Finish after a passing verifier.",
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "passed",
                    "evidence_refs": ["ev:verify-1"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.latest_actionable is None
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"
    assert workframe.finish_readiness.state == "ready"


def test_workframe_phase2_fastcheck_rejects_generic_latest_actionable_summary() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Repair the current failure.",
            sidecar_events=(
                {
                    "kind": "verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "failed",
                    "summary": "exit code 1",
                    "evidence_refs": ["ev:verify-1"],
                },
            ),
        )
    )

    assert workframe.latest_actionable
    assert workframe.latest_actionable.summary == "exit code 1"
    assert report.status == "fail"
    assert {item["code"] for item in report.failed} == {"latest_actionable_generic"}


def test_workframe_phase2_generic_family_fallback_does_not_emit_task_specific_name() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Handle an invalid failure record.",
            sidecar_events=(
                {
                    "kind": "failure",
                    "event_sequence": 1,
                    "event_id": "failure-1",
                    "status": "invalid",
                    "family": "compile_compcert_special_case",
                    "summary": "failure record was malformed but current",
                    "evidence_refs": ["ev:failure-1"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "compile_compcert_special_case"
    assert workframe.latest_actionable.generic_family == "unknown_failure"


def test_workframe_phase3_cheap_probe_cannot_satisfy_finish_proof() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Do not let a cheap probe finish the task.",
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "probe-1",
                    "status": "passed",
                    "command_intent": "probe",
                    "execution_contract_normalized": {
                        "id": "contract:probe-1",
                        "role": "source",
                        "proof_role": "none",
                        "acceptance_kind": "not_acceptance",
                    },
                    "typed_evidence_id": "ev:probe-1",
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "cheap_probe"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "cheap_probe"
    assert "ev:probe-1" in workframe.evidence_refs.typed
    assert "contract:probe-1" in workframe.evidence_refs.sidecar


def test_workframe_phase3_rejects_probe_authored_completion_obligation() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Reject model-authored proof obligations on probes.",
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "probe-1",
                    "status": "passed",
                    "command_intent": "probe",
                    "execution_contract": {
                        "id": "contract:model-authored-probe",
                        "role": "source",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "artifact:result", "path": "result.txt"}],
                    },
                    "typed_evidence_id": "ev:probe-1",
                },
            ),
        )
    )

    assert workframe.finish_readiness.state == "not_ready"
    assert report.status == "fail"
    assert {item["code"] for item in report.failed} == {"cheap_probe_authored_proof_obligation"}


def test_workframe_phase3_strict_verifier_keeps_refs_without_contract_payload() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Finish from typed verifier evidence.",
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "passed",
                    "command_run_id": "cmd:verify-1",
                    "typed_evidence_id": "ev:verify-1",
                    "execution_contract_normalized": {
                        "id": "contract:verify-1",
                        "role": "verify",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "artifact:answer", "path": "answer.txt"}],
                    },
                    "finish_gate": {"id": "finish:gate-1", "blocked": False},
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.finish_readiness.state == "ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"
    assert "ev:verify-1" in workframe.required_next.evidence_refs
    assert "finish:gate-1" in workframe.required_next.evidence_refs
    assert "ev:verify-1" in workframe.evidence_refs.typed
    assert "contract:verify-1" in workframe.evidence_refs.sidecar
    serialized = json.dumps(workframe.as_dict(), sort_keys=True)
    assert "execution_contract" not in serialized
    assert "expected_artifacts" not in serialized
    assert "artifact:answer" not in serialized


def test_workframe_phase3_later_failed_verifier_blocks_earlier_finish_proof() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Repair after the latest verifier failure.",
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
                    "kind": "strict_verifier",
                    "event_sequence": 2,
                    "event_id": "verify-2",
                    "status": "failed",
                    "summary": "latest verifier reports parser regression",
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
    )

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_verifier_failure"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.source_ref == "ev:verify-2"


def test_workframe_phase3_real_typed_evidence_event_can_drive_finish_readiness() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Finish from a typed EvidenceEvent record.",
            sidecar_events=(
                {
                    "kind": "verifier_result",
                    "event_sequence": 1,
                    "id": "ev:verifier:cmd-1",
                    "status": "passed",
                    "contract_id": "contract:verify-typed",
                    "observed": {"verdict": "pass"},
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"
    assert "ev:verifier:cmd-1" in workframe.evidence_refs.typed
    assert "contract:verify-typed" in workframe.evidence_refs.sidecar


def test_workframe_phase3_standalone_finish_gate_cannot_drive_finish_readiness() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Do not finish from a finish gate without verifier evidence.",
            sidecar_events=(
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 1,
                    "id": "ev:finish-gate:1",
                    "status": "passed",
                    "observed": {"blocked": False},
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "cheap_probe"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "cheap_probe"


def test_workframe_phase3_diagnostic_with_finish_gate_remains_non_proof() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Diagnostic sidecars and finish gates are not proof.",
            sidecar_events=(
                {
                    "kind": "verifier",
                    "event_sequence": 1,
                    "event_id": "diagnostic-1",
                    "status": "passed",
                    "command_intent": "diagnostic",
                    "execution_contract_normalized": {
                        "id": "contract:diagnostic-1",
                        "role": "diagnostic",
                        "proof_role": "negative_diagnostic",
                        "acceptance_kind": "not_acceptance",
                    },
                },
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 2,
                    "id": "ev:finish-gate:1",
                    "status": "passed",
                    "observed": {"blocked": False},
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "cheap_probe"


def test_workframe_phase3_finish_gate_supports_paired_verifier_proof() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Finish from verifier evidence with finish-gate support.",
            sidecar_events=(
                {
                    "kind": "verifier_result",
                    "event_sequence": 1,
                    "id": "ev:verifier:cmd-1",
                    "status": "passed",
                    "contract_id": "contract:verify-typed",
                    "observed": {"verdict": "pass"},
                },
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 2,
                    "id": "ev:finish-gate:1",
                    "status": "passed",
                    "observed": {"blocked": False},
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "finish"
    assert "ev:verifier:cmd-1" in workframe.required_next.evidence_refs
    assert "ev:finish-gate:1" in workframe.required_next.evidence_refs


def test_workframe_phase3_missing_obligations_block_fresh_verifier_finish() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Do not finish with missing typed obligations.",
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
                    "missing_obligations": ["oracle:artifact-fresh"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_blocked"
    assert workframe.finish_readiness.state == "blocked"
    assert workframe.finish_readiness.blockers == ("missing_typed_obligations",)
    assert workframe.finish_readiness.missing_obligations == ("oracle:artifact-fresh",)
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.evidence_refs == ("oracle:artifact-fresh",)


def test_workframe_phase3_diagnostic_artifact_contract_is_non_proof_sidecar() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Allow observational diagnostic artifact checks without finish proof.",
            sidecar_events=(
                {
                    "kind": "verifier",
                    "event_sequence": 1,
                    "event_id": "diagnostic-1",
                    "status": "passed",
                    "command_intent": "diagnostic",
                    "execution_contract_normalized": {
                        "id": "contract:diagnostic-1",
                        "role": "diagnostic",
                        "proof_role": "negative_diagnostic",
                        "acceptance_kind": "not_acceptance",
                        "expected_artifacts": [{"id": "artifact:diagnostic-log", "path": "diag.log"}],
                    },
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.required_next
    assert workframe.required_next.kind == "cheap_probe"
    assert "contract:diagnostic-1" in workframe.evidence_refs.sidecar
    assert "artifact:diagnostic-log" not in json.dumps(workframe.as_dict(), sort_keys=True)


def test_workframe_phase3_projects_missing_obligation_refs_only() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-1",
            task_id="task-1",
            objective="Expose missing obligations without proof payloads.",
            sidecar_events=(
                {
                    "kind": "finish_gate",
                    "event_sequence": 1,
                    "event_id": "finish-1",
                    "status": "failed",
                    "finish_gate": {
                        "id": "finish:gate-1",
                        "missing_obligations": [
                            {
                                "id": "oracle:verify-pass",
                                "kind": "verifier_pass",
                                "subject": {"contract_id": "contract:verify"},
                            }
                        ],
                    },
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "finish_blocked"
    assert workframe.finish_readiness.state == "blocked"
    assert workframe.finish_readiness.missing_obligations == ("contract:verify", "oracle:verify-pass")
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.evidence_refs == ("contract:verify", "oracle:verify-pass")
    serialized = json.dumps(workframe.as_dict(), sort_keys=True)
    assert "verifier_pass" not in serialized
    assert "missing_obligations" in serialized


def test_workframe_phase5_low_budget_source_mutation_schedules_controller_closeout() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Close out source mutation under low budget.",
            success_contract_ref="task-contract:pytest",
            sidecar_events=(
                {
                    "kind": "source_mutation",
                    "event_sequence": 1,
                    "event_id": "patch-1",
                    "status": "passed",
                    "path": "src/app.py",
                    "budget_class": "low",
                    "evidence_refs": ["sidecar:patch-1"],
                },
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "controller_closeout"
    assert workframe.verifier_state.configured_verifier_ref == "task-contract:pytest"
    assert workframe.verifier_state.budget_closeout_required is True
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.after == "finish_or_block"
    assert workframe.required_next.evidence_refs == ("sidecar:patch-1",)
    assert "finish" in [item.kind for item in workframe.forbidden_next]


def test_workframe_phase5_low_budget_does_not_mask_later_verifier_failure() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
            attempt_id="attempt-1",
            turn_id="turn-2",
            task_id="task-1",
            objective="Repair the real verifier failure before closeout.",
            success_contract_ref="task-contract:pytest",
            sidecar_events=(
                {
                    "kind": "source_mutation",
                    "event_sequence": 1,
                    "event_id": "patch-1",
                    "status": "passed",
                    "path": "src/app.py",
                    "budget_class": "low",
                    "evidence_refs": ["sidecar:patch-1"],
                },
                {
                    "kind": "strict_verifier",
                    "event_sequence": 2,
                    "event_id": "verify-2",
                    "status": "failed",
                    "summary": "pytest reports assertion failure in test_app",
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
    )

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_verifier_failure"
    assert workframe.verifier_state.budget_closeout_required is True
    assert workframe.latest_actionable
    assert workframe.latest_actionable.source_ref == "ev:verify-2"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"


def test_workframe_phase5_non_low_budget_source_mutation_requires_configured_verifier() -> None:
    workframe, report = reduce_workframe(
        WorkFrameInputs(
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
            ),
        )
    )

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.verifier_state.configured_verifier_ref == "task-contract:pytest"
    assert workframe.verifier_state.budget_closeout_required is False
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.evidence_refs == ("sidecar:patch-1",)


def test_workframe_phase0_prompt_inventory_checker_detects_legacy_projection_presence() -> None:
    inventory = [
        {"id": section_id, "visibility": "ordinary", "bytes": 32}
        for section_id in LEGACY_PROMPT_PROJECTION_IDS
    ]

    passing = check_phase0_prompt_inventory(inventory)
    assert passing["status"] == "pass"
    assert passing["missing_legacy_ids"] == []

    failing_inventory = [item for item in inventory if item["id"] != LEGACY_PROMPT_PROJECTION_IDS[0]]
    failing = check_phase0_prompt_inventory(failing_inventory)
    assert failing["status"] == "fail"
    assert failing["missing_legacy_ids"] == [LEGACY_PROMPT_PROJECTION_IDS[0]]


def test_workframe_phase0_baseline_metrics_record_required_fields() -> None:
    workframe, report = reduce_workframe(_workframe_inputs())
    assert report.status == "pass"
    manifest = {
        "metrics": {
            "hot_path_projection": {
                "normal_full_prompt_bytes_total": 20000,
                "normal_dynamic_hot_path_bytes": 8000,
                "provider_visible_tool_result_bytes": 1500,
                "required_next_adherence": 0.91,
            },
            "resident_sidecar_state": {
                "total_bytes": 120000,
                "per_turn_growth_bytes": 4000,
            },
        }
    }
    history = [
        {
            "turn": 1,
            "elapsed_seconds": 10,
            "tool_calls": [{"tool_name": "read_file"}],
            "tool_results": [],
        },
        {
            "turn": 2,
            "elapsed_seconds": 20,
            "tool_calls": [{"tool_name": "apply_patch"}],
            "tool_results": [],
        },
        {
            "turn": 3,
            "elapsed_seconds": 40,
            "tool_calls": [{"tool_name": "run_tests"}],
            "tool_results": [
                {"content": {"latest_failure": {"class": "runtime_failure", "kind": "nonzero_exit"}}}
            ],
        },
    ]

    result = record_phase0_baseline_metrics(manifest, history, workframe=workframe)

    assert result["status"] == "pass"
    baseline = result["baseline"]
    assert baseline["B_prompt_normal_total"] == 20000
    assert baseline["B_first_edit_turn"] == 2
    assert baseline["B_first_verifier_turn"] == 3
    assert baseline["B_model_turns_10m"] == 3
    assert baseline["B_tool_calls_10m"] == 3
    assert baseline["B_workframe_bytes"] > 0
    assert "B_workframe_bytes" in result["bands"]


def test_workframe_debug_bundle_format_lists_required_phase0_files() -> None:
    bundle = workframe_debug_bundle_format()

    assert bundle["root"] == "implement_v2/workframes/turn-XXXX/"
    assert "reducer_inputs.json" in bundle["files"]
    assert "invariant_report.json" in bundle["files"]
    assert "prompt_render_inventory.json" in bundle["files"]
