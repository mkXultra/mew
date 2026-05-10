from __future__ import annotations

from mew.implement_lane.workframe import WorkFrameInputs, reduce_workframe
from mew.implement_lane.workframe_variant_transcript_first import (
    VARIANT_NAME,
    reduce_transcript_first_workframe,
)


def _inputs(sidecar_events: tuple[dict[str, object], ...]) -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-transcript-first",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair the workspace using the latest concrete tool result.",
        success_contract_ref="task-contract:verify",
        sidecar_events=sidecar_events,
    )


def test_transcript_first_prefers_runtime_failure_over_trailing_prompt_repair() -> None:
    inputs = _inputs(
        (
            {
                "kind": "latest_failure",
                "event_sequence": 1,
                "event_id": "tool-result:runtime-verifier",
                "status": "failed",
                "tool_name": "run_command",
                "provider_call_id": "runtime-verifier",
                "command_run_id": "cmd:runtime-verifier",
                "family": "runtime_failure",
                "summary": "RuntimeError: unsupported opcode 0x1c at pc 0x00400200",
                "target_paths": ["src/runtime.py"],
                "evidence_refs": ["ev:runtime-verifier"],
            },
            {
                "kind": "latest_failure",
                "event_sequence": 2,
                "event_id": "prompt-repair-history",
                "status": "failed",
                "family": "repair_history",
                "summary": "Run one scoped producer/artifact diagnostic before patching",
                "evidence_refs": ["wf:repair_history"],
            },
        )
    )

    current, current_report = reduce_workframe(inputs)
    workframe, report = reduce_transcript_first_workframe(inputs)

    assert VARIANT_NAME == "transcript_first"
    assert current_report.status == "pass"
    assert current.latest_actionable
    assert current.latest_actionable.source_ref == "wf:repair_history"
    assert report.status == "pass"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.source_ref == "cmd:runtime-verifier"
    assert workframe.latest_actionable.summary == "RuntimeError: unsupported opcode 0x1c at pc 0x00400200"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"
    assert workframe.required_next.target_paths == ("src/runtime.py",)
    assert "ev:runtime-verifier" in workframe.required_next.evidence_refs


def test_transcript_first_prefers_completed_write_result_over_prompt_fallback_required_next() -> None:
    inputs = _inputs(
        (
            {
                "kind": "write",
                "event_sequence": 1,
                "event_id": "tool-result:write-file",
                "status": "completed",
                "tool_name": "write_file",
                "provider_call_id": "write-file",
                "path": "src/runtime.py",
                "evidence_refs": ["sidecar:write-file"],
            },
            {
                "kind": "latest_failure",
                "event_sequence": 2,
                "event_id": "prompt-frontier-failure",
                "status": "failed",
                "family": "runtime_failure",
                "summary": "stale prompt projection says patch the old runtime failure",
                "target_paths": ["src/old_runtime.py"],
                "evidence_refs": ["wf:frontier_failure"],
            },
        )
    )

    current, _current_report = reduce_workframe(inputs)
    workframe, report = reduce_transcript_first_workframe(inputs)

    assert current.required_next
    assert current.required_next.kind == "patch_or_edit"
    assert current.required_next.target_paths == ("src/old_runtime.py",)
    assert report.status == "pass"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "verifier_stale_after_mutation"
    assert workframe.latest_actionable.source_ref == "sidecar:write-file"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert workframe.required_next.evidence_refs == ("sidecar:write-file",)
    assert workframe.current_phase == "verify_after_mutation"


def test_transcript_first_finish_safety_stays_strict_after_mutation_with_stale_verifier() -> None:
    inputs = _inputs(
        (
            {
                "kind": "strict_verifier",
                "event_sequence": 1,
                "event_id": "tool-result:verify-before-write",
                "status": "passed",
                "tool_name": "run_tests",
                "provider_call_id": "verify-before-write",
                "typed_evidence_id": "ev:verify-before-write",
                "execution_contract_normalized": {
                    "id": "contract:verify-before-write",
                    "role": "verify",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
            },
            {
                "kind": "write",
                "event_sequence": 2,
                "event_id": "tool-result:write-after-verify",
                "status": "completed",
                "tool_name": "edit_file",
                "provider_call_id": "write-after-verify",
                "path": "src/runtime.py",
                "evidence_refs": ["sidecar:write-after-verify"],
            },
            {
                "kind": "latest_failure",
                "event_sequence": 3,
                "event_id": "prompt-repair-history",
                "status": "failed",
                "family": "repair_history",
                "summary": "stale repair history from before the write",
                "evidence_refs": ["wf:repair_history"],
            },
        )
    )

    workframe, report = reduce_transcript_first_workframe(inputs)

    assert report.status == "pass"
    assert workframe.finish_readiness.state == "not_ready"
    assert workframe.verifier_state.fresh_after_latest_source_mutation is False
    assert workframe.changed_sources.since_last_strict_verifier is True
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert "finish" in [item.kind for item in workframe.forbidden_next]


def test_transcript_first_preserves_current_reducer_when_no_competing_prompt_projection_exists() -> None:
    runtime_only_inputs = _inputs(
        (
            {
                "kind": "strict_verifier",
                "event_sequence": 1,
                "event_id": "tool-result:verify-runtime",
                "status": "failed",
                "tool_name": "run_command",
                "provider_call_id": "verify-runtime",
                "family": "runtime_failure",
                "summary": "RuntimeError: invalid memory access at pc 0x00400100",
                "target_paths": ["src/runtime.py"],
                "evidence_refs": ["ev:verify-runtime"],
            },
        )
    )
    prompt_only_inputs = _inputs(
        (
            {
                "kind": "latest_failure",
                "event_sequence": 1,
                "event_id": "prompt-first-write-due",
                "status": "failed",
                "family": "first_write_due",
                "summary": "make one scoped source mutation",
                "target_paths": ["src/runtime.py"],
                "evidence_refs": ["wf:first_write_readiness"],
            },
        )
    )

    for inputs in (runtime_only_inputs, prompt_only_inputs):
        current, current_report = reduce_workframe(inputs)
        workframe, report = reduce_transcript_first_workframe(inputs)

        assert report.as_dict() == current_report.as_dict()
        assert workframe.as_dict() == current.as_dict()


def test_transcript_first_is_deterministic_for_competing_prompt_projection() -> None:
    inputs = _inputs(
        (
            {
                "kind": "latest_failure",
                "event_sequence": 1,
                "event_id": "tool-result:runtime-verifier",
                "status": "failed",
                "tool_name": "run_command",
                "provider_call_id": "runtime-verifier",
                "command_run_id": "cmd:runtime-verifier",
                "family": "runtime_failure",
                "summary": "RuntimeError: bad syscall at pc 0x00400300",
                "target_paths": ["src/runtime.py"],
                "evidence_refs": ["ev:runtime-verifier"],
            },
            {
                "kind": "latest_failure",
                "event_sequence": 2,
                "event_id": "prompt-frontier-failure",
                "status": "failed",
                "family": "runtime_failure",
                "summary": "stale prompt projection",
                "evidence_refs": ["wf:frontier_failure"],
            },
        )
    )

    first, first_report = reduce_transcript_first_workframe(inputs)
    second, second_report = reduce_transcript_first_workframe(inputs)

    assert first_report.as_dict() == second_report.as_dict()
    assert first.as_dict() == second.as_dict()
