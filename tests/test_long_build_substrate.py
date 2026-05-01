import pytest

from mew.acceptance_evidence import long_dependency_artifact_proven_by_call, tool_call_terminal_success
from mew.long_build_substrate import (
    BuildAttempt,
    CommandEvidence,
    LONG_BUILD_SCHEMA_VERSION,
    LongBuildContract,
    LongBuildState,
    RecoveryDecision,
    command_evidence_to_tool_call,
    fresh_long_dependency_artifact_evidence,
    long_dependency_artifact_proven_by_command_evidence,
    summarize_env,
    synthesize_command_evidence_from_tool_calls,
)


TASK_TEXT = (
    "Under /tmp/FooCC/, build the FooCC C compiler toolchain from source. "
    "Ensure that FooCC can be invoked through /tmp/FooCC/foocc."
)


def _command_call(call_id, command, *, stdout="", stderr="", exit_code=0, timed_out=False, status="completed"):
    return {
        "id": call_id,
        "tool": "run_command",
        "status": status,
        "parameters": {"command": command, "cwd": "/tmp/FooCC"},
        "result": {
            "command": command,
            "cwd": "/tmp/FooCC",
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": stdout,
            "stderr": stderr,
        },
    }


@pytest.mark.parametrize(
    "call",
    [
        _command_call(1, "true", exit_code=0),
        _command_call(2, "false", exit_code=1),
        _command_call(3, "sleep 60", exit_code=0, timed_out=True),
        {"id": 4, "tool": "run_tests", "status": "completed", "result": {"exit_code": 0, "stdout": "passed\n"}},
        {"id": 5, "tool": "run_tests", "status": "failed", "error": "tool crashed"},
    ],
)
def test_command_evidence_terminal_success_matches_tool_call_semantics(call):
    evidence = synthesize_command_evidence_from_tool_calls([call])[0]

    assert evidence.schema_version == LONG_BUILD_SCHEMA_VERSION
    assert evidence.source == "synthesized_fixture"
    assert evidence.ref == {"kind": "command_evidence", "id": 1}
    assert evidence.terminal_success == tool_call_terminal_success(call)


def test_command_evidence_synthesis_ignores_write_tools_and_verify_command_fields():
    calls = [
        {
            "id": 1,
            "tool": "write_file",
            "status": "completed",
            "parameters": {"path": "README.md", "verify_command": "test -x /tmp/FooCC/foocc"},
            "result": {"path": "README.md", "changed": True},
        },
        {
            "id": 2,
            "tool": "edit_file",
            "status": "completed",
            "parameters": {"path": "README.md", "verify_command": "test -x /tmp/FooCC/foocc"},
            "result": {"changed": True},
        },
        _command_call(3, "test -x /tmp/FooCC/foocc", stdout="ok\n"),
    ]

    evidences = synthesize_command_evidence_from_tool_calls(calls)

    assert len(evidences) == 1
    assert evidences[0].source_tool_call_id == 3
    assert evidences[0].command == "test -x /tmp/FooCC/foocc"


@pytest.mark.parametrize(
    "name,call,expected",
    [
        (
            "clean proof",
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            True,
        ),
        (
            "timed out proof",
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
                timed_out=True,
            ),
            False,
        ),
        (
            "masked proof",
            _command_call(9, "test -x /tmp/FooCC/foocc || true", stdout="ignored\n"),
            False,
        ),
        (
            "spoofed proof",
            _command_call(9, "echo '/tmp/FooCC/foocc exists=true executable'", stdout="/tmp/FooCC/foocc exists=true\n"),
            False,
        ),
        (
            "path prefix proof",
            _command_call(9, "test -x /tmp/FooCC/foocc-old && /tmp/FooCC/foocc-old --version", stdout="old\n"),
            False,
        ),
        (
            "same command post proof mutation",
            _command_call(9, "test -x /tmp/FooCC/foocc && rm /tmp/FooCC/foocc", stdout="removed\n"),
            False,
        ),
    ],
)
def test_long_dependency_artifact_proof_matches_existing_helper_for_safety_cases(name, call, expected):
    evidence = synthesize_command_evidence_from_tool_calls([call])[0]

    assert long_dependency_artifact_proven_by_call(call, "/tmp/FooCC/foocc") is expected, name
    assert long_dependency_artifact_proven_by_command_evidence(evidence, "/tmp/FooCC/foocc") is expected
    assert long_dependency_artifact_proven_by_call(
        command_evidence_to_tool_call(evidence), "/tmp/FooCC/foocc"
    ) is expected


def test_fresh_artifact_evidence_rejects_later_artifact_scope_mutation():
    evidences = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            _command_call(10, "rm /tmp/FooCC/foocc", stdout="removed\n"),
        ]
    )

    assert fresh_long_dependency_artifact_evidence(evidences, "/tmp/FooCC/foocc") is None


def test_fresh_artifact_evidence_rejects_parent_glob_mutation():
    evidences = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            _command_call(10, "rm /tmp/FooCC/*", stdout="removed\n"),
        ]
    )

    assert fresh_long_dependency_artifact_evidence(evidences, "/tmp/FooCC/foocc") is None


def test_fresh_artifact_evidence_rejects_cwd_relative_mutation():
    evidences = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            _command_call(10, "rm foocc", stdout="removed\n"),
        ]
    )

    assert fresh_long_dependency_artifact_evidence(evidences, "/tmp/FooCC/foocc") is None


def test_command_evidence_preserves_non_stdout_output_surfaces_used_by_existing_helpers():
    call = {
        "id": 9,
        "tool": "run_command",
        "status": "completed",
        "parameters": {"command": "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", "cwd": "/tmp/FooCC"},
        "result": {
            "exit_code": 0,
            "summary": "/tmp/FooCC/foocc exists=true\n",
            "output": "FooCC version 1.0\n",
        },
    }
    evidence = synthesize_command_evidence_from_tool_calls([call])[0]

    assert "/tmp/FooCC/foocc exists=true" in evidence.output_tail
    assert "FooCC version 1.0" in evidence.output_tail
    assert long_dependency_artifact_proven_by_command_evidence(evidence, "/tmp/FooCC/foocc")


def test_command_evidence_terminal_success_is_required_for_artifact_proof():
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                9,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            )
        ]
    )[0]
    malformed = evidence.to_dict()
    malformed["terminal_success"] = False

    assert not long_dependency_artifact_proven_by_command_evidence(malformed, "/tmp/FooCC/foocc")


def test_schema_helpers_have_versioned_minimum_shapes():
    command = CommandEvidence.from_dict(
        {
            "schema_version": 1,
            "id": 3,
            "source": "synthesized_fixture",
            "tool": "run_command",
            "command": "true",
            "status": "completed",
            "terminal_success": True,
        }
    )
    contract = LongBuildContract(
        schema_version=1,
        id="work_session:1:long_build:1",
        authority_source="task_text",
        required_artifacts=[{"path": "/tmp/FooCC/foocc"}],
        source_policy={"authority_required": True},
        dependency_policy={"prefer_source_provided_compatibility_branch": True},
        build_policy={"prefer_shortest_final_target": True},
        runtime_proof={"required": "required"},
        budget={"wall_seconds": None, "final_proof_reserve_seconds": 60},
        final_proof={"evidence_kinds": ["command_evidence"]},
    )
    attempt = BuildAttempt(
        schema_version=1,
        id="work_session:1:long_build:1:attempt:1",
        contract_id=contract.id,
        command_evidence_ref=command.ref,
        stage="build",
        selected_target="foocc",
        requested_timeout_seconds=None,
        effective_timeout_seconds=None,
        wall_budget_before_seconds=None,
        wall_budget_after_seconds=None,
        result="success",
        produced_artifacts=[],
        mutation_refs=[],
        diagnostics=[],
    )
    state = LongBuildState(
        schema_version=1,
        kind="long_build_state",
        contract_id=contract.id,
        status="in_progress",
        stages=[{"id": "target_built", "required": True, "status": "unknown"}],
        artifacts=[{"path": "/tmp/FooCC/foocc", "status": "missing_or_unproven", "proof_evidence_id": None}],
        attempt_ids=[attempt.id],
        latest_attempt_id=attempt.id,
        current_failure={"failure_class": "artifact_missing"},
        recovery_decision_id=None,
    )
    decision = RecoveryDecision(
        schema_version=1,
        id="work_session:1:long_build:1:recovery:1",
        contract_id=contract.id,
        state_status="blocked",
        failure_class="runtime_link_failed",
        prerequisites=["target_built"],
        clear_condition="default compile/link smoke succeeds",
        allowed_next_action={"kind": "command", "stage": "runtime_build_or_install"},
        prohibited_repeated_actions=["source_reacquisition", "clean_rebuild"],
        budget={
            "remaining_seconds": None,
            "reserve_seconds": 60,
            "may_spend_reserve": False,
            "attempts_for_failure_class": 1,
            "max_attempts_for_failure_class": 2,
        },
        decision="continue",
    )

    assert command.to_dict()["ref"] == {"kind": "command_evidence", "id": 3}
    assert contract.to_dict()["schema_version"] == 1
    assert attempt.to_dict()["command_evidence_ref"] == {"kind": "command_evidence", "id": 3}
    assert state.to_dict()["kind"] == "long_build_state"
    assert decision.to_dict()["budget"]["reserve_seconds"] == 60


def test_env_summary_omits_secrets_and_clips_whitelisted_values():
    summary = summarize_env(
        {
            "CC": "clang",
            "MAKEFLAGS": "-j" + "8" * 200,
            "OPENAI_API_KEY": "secret",
            "UNRELATED": "value",
        }
    )

    assert summary["policy"] == "env_summary_v1"
    assert {"name": "CC", "value": "clang"} in summary["items"]
    assert [item["name"] for item in summary["items"]] == ["CC", "MAKEFLAGS"]
    assert len(summary["items"][1]["value"]) == 120
