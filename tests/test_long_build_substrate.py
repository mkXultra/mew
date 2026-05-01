import pytest

from mew.acceptance_evidence import long_dependency_artifact_proven_by_call, tool_call_terminal_success
from mew.long_build_substrate import (
    BuildAttempt,
    CommandEvidence,
    LONG_BUILD_SCHEMA_VERSION,
    LongBuildContract,
    LongBuildState,
    RecoveryDecision,
    build_attempts_from_command_evidence,
    build_long_build_contract,
    command_evidence_from_tool_call,
    command_evidence_to_tool_call,
    fresh_long_dependency_artifact_evidence,
    long_dependency_artifact_proven_by_command_evidence,
    reduce_long_build_state,
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


def test_native_command_evidence_records_wall_timeout_ceiling_fields():
    call = {
        "id": 9,
        "tool": "run_command",
        "status": "completed",
        "parameters": {
            "command": "make -j2 foocc",
            "cwd": "/tmp/FooCC",
            "timeout": 840,
            "wall_timeout_ceiling": {
                "remaining_seconds": 900.4,
                "requested_timeout_seconds": 1800,
                "capped_timeout_seconds": 840,
            },
        },
        "result": {
            "command": "make -j2 foocc",
            "cwd": "/tmp/FooCC",
            "exit_code": 0,
            "duration_seconds": 100.8,
            "stdout": "built\n",
        },
    }

    evidence = command_evidence_from_tool_call(
        call,
        evidence_id=2,
        start_order=3,
        finish_order=4,
    )

    assert evidence is not None
    assert evidence.source == "native_command"
    assert evidence.requested_timeout_seconds == 1800
    assert evidence.effective_timeout_seconds == 840
    assert evidence.wall_budget_before_seconds == 900
    assert evidence.wall_budget_after_seconds == 799


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


def test_contract_and_state_reduce_non_compcert_toolchain_artifact():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can be invoked.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:7:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc.tar.gz", stdout="official release archive\n"),
            _command_call(2, "./configure && make depend && make -j2 foocc", stdout="make depend\nbuilt foocc\n"),
            _command_call(
                3,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC compiler 1.0\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)

    state = reduce_long_build_state(contract, attempts, evidence)

    assert contract["runtime_proof"]["required"] == "required"
    assert attempts[0]["stage"] == "source_acquisition"
    assert attempts[1]["stage"] == "dependency_generation"
    assert attempts[2]["stage"] == "artifact_proof"
    assert state["kind"] == "long_build_state"
    assert state["status"] == "blocked"
    assert state["artifacts"][0]["status"] == "proven"
    assert state["artifacts"][0]["proof_evidence_id"] == 3
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_contract_marks_ordinary_cli_runtime_proof_not_required():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:8:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/widgetcli.tar.gz https://example.test/widgetcli-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            }
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert contract["runtime_proof"]["required"] == "not_required"
    assert {"id": "default_smoke", "required": False, "status": "not_required"} in state["stages"]
    assert state["status"] == "complete"


def test_runtime_required_contract_rejects_custom_runtime_path_as_completion():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:9:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            _command_call(
                2,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc -L /tmp/FooCC/runtime /tmp/probe.c -o /tmp/probe",
                stdout="custom runtime path smoke ok\n",
            ),
        ]
    )
    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert build_attempts_from_command_evidence(evidence, contract)[1]["stage"] == "custom_runtime_smoke"
    assert contract["runtime_proof"]["required"] == "required"
    assert {"id": "default_smoke", "required": True, "status": "blocked"} in state["stages"]
    assert state["status"] == "blocked"
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_runtime_required_contract_accepts_default_compile_link_smoke():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version",
                stdout="FooCC version 1.0\n",
            ),
            _command_call(
                3,
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="default smoke ok\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[2]["stage"] == "default_smoke"
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"
    assert state["current_failure"] is None


def test_default_compile_link_smoke_rejects_basename_from_unrelated_cwd():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10b:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(
                    1,
                    "foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                    stdout="PATH smoke ok\n",
                ),
                "parameters": {"command": "foocc /tmp/probe.c -o /tmp/probe && /tmp/probe", "cwd": "/workspace"},
                "result": {
                    "command": "foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                    "cwd": "/workspace",
                    "exit_code": 0,
                    "stdout": "PATH smoke ok\n",
                },
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "command"
    assert state["artifacts"][0]["status"] == "missing_or_unproven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "artifact_missing_or_unproven"


def test_default_compile_link_smoke_accepts_basename_from_artifact_parent_cwd():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10c:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="parent cwd smoke ok\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"


def test_default_compile_link_smoke_accepts_dot_slash_basename_from_artifact_parent_cwd():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10d:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "./foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="parent cwd smoke ok\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"


def test_default_compile_link_smoke_rejects_later_artifact_mutation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10e:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe && rm -f /tmp/FooCC/foocc",
                stdout="smoke ok, then mutated artifact\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert state["artifacts"][0]["status"] == "missing_or_unproven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "artifact_missing_or_unproven"


def test_default_compile_link_smoke_rejects_opaque_wrapper_artifact_mutation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10f:long_build:1",
    )
    command = "bash -c '/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe && rm -f /tmp/FooCC/foocc'"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, command, stdout="wrapped smoke ok, then mutated artifact\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert state["artifacts"][0]["status"] == "missing_or_unproven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "artifact_missing_or_unproven"


def test_default_compile_link_smoke_rejects_later_command_artifact_mutation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10g:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="default smoke ok\n",
            ),
            _command_call(3, "rm -f /tmp/FooCC/foocc", stdout="removed\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert state["artifacts"][0]["status"] == "missing_or_unproven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "blocked"
    assert state["current_failure"]["failure_class"] == "artifact_missing_or_unproven"


def test_default_smoke_must_be_fresh_after_later_artifact_mutation_and_reproof():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10h:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(
                2,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="default smoke ok\n",
            ),
            _command_call(3, "rm -f /tmp/FooCC/foocc", stdout="removed\n"),
            _command_call(4, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="rebuilt\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "blocked"
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_requires_compile_link_artifact_segment_not_marker_text():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10i:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "echo 'default link path verified'", stdout="default link path verified\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert attempts[1]["produced_artifacts"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "blocked"
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_echoed_compile_command_text():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "echo '/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe'", stdout="printed only\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_source_authority_signal_is_preserved_and_required_for_completion():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k:long_build:1",
    )
    evidence_without_authority = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(
                    1,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            }
        ]
    )

    state_without_authority = reduce_long_build_state(
        contract,
        build_attempts_from_command_evidence(evidence_without_authority, contract),
        evidence_without_authority,
    )

    assert state_without_authority["status"] == "ready_for_final_proof"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state_without_authority["stages"]

    evidence_with_authority = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/widgetcli.tar.gz https://example.test/widgetcli-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence_with_authority, contract)
    state_with_authority = reduce_long_build_state(contract, attempts, evidence_with_authority)

    assert attempts[0]["stage"] == "source_acquisition"
    assert {"signal": "source_authority", "excerpt": "official release archive"} in attempts[0]["diagnostics"]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state_with_authority["stages"]
    assert state_with_authority["status"] == "complete"


def test_source_authority_rejects_echoed_model_assertion():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "echo 'official release archive'", stdout="official release archive\n"),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "command"
    assert attempts[0]["diagnostics"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "ready_for_final_proof"


def test_source_authority_accepts_package_manager_metadata_probe():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10m:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "npm view widgetcli dist.tarball", stdout="package-manager metadata\n"),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert {"signal": "source_authority", "excerpt": "package-manager metadata"} in attempts[0]["diagnostics"]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"


@pytest.mark.parametrize(
    ("command", "stdout", "excerpt"),
    [
        ("npm view widgetcli dist.tarball", "https://registry.npmjs.org/widgetcli/-/widgetcli.tgz\n", "https://registry.npmjs.org/widgetcli/-/widgetcli.tgz"),
        ("npm view widgetcli dist.integrity", "sha512-deadbeef\n", "sha512-deadbeef"),
        ("npm view widgetcli dist", "tarball: 'https://registry.npmjs.org/widgetcli/-/widgetcli.tgz'\nintegrity: 'sha512-deadbeef'\n", "tarball: 'https://registry.npmjs.org/widgetcli/-/widgetcli.tgz'"),
        ("apt-cache show widgetcli", "Package: widgetcli\nVersion: 1.0\n", "Package: widgetcli"),
        ("python -m pip index versions widgetcli", "widgetcli (1.0)\nAvailable versions: 1.0, 0.9\n", "Available versions: 1.0, 0.9"),
    ],
)
def test_source_authority_accepts_realistic_package_metadata_outputs(command, stdout, excerpt):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10n:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, command, stdout=stdout),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert {"signal": "source_authority", "excerpt": excerpt} in attempts[0]["diagnostics"]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"


@pytest.mark.parametrize(
    ("command", "stdout"),
    [
        ("npm pack widgetcli", "npm notice integrity: sha512-deadbeef\nwidgetcli-1.0.0.tgz\n"),
        ("pip download widgetcli", "Saved ./widgetcli-1.0.tar.gz\nSuccessfully downloaded widgetcli\n"),
    ],
)
def test_source_authority_rejects_download_pack_outputs_as_metadata_authority(command, stdout):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10o:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, command, stdout=stdout),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["diagnostics"] == []
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "ready_for_final_proof"


def test_source_authority_rejects_mixed_echo_assertion_with_metadata_probe():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10p:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "echo 'official release archive' && npm view widgetcli version",
                stdout="official release archive\n",
            ),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert attempts[0]["diagnostics"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "ready_for_final_proof"


def test_source_authority_rejects_wrapped_assertion_with_metadata_probe():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10q:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "bash -c \"echo official release archive\" && npm view widgetcli version",
                stdout="official release archive\n",
            ),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert attempts[0]["diagnostics"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "ready_for_final_proof"


@pytest.mark.parametrize(
    ("assertion"),
    [
        "https://registry.npmjs.org/widgetcli/-/widgetcli.tgz",
        "sha512-deadbeef",
    ],
)
def test_source_authority_rejects_mixed_echo_metadata_output_assertion(assertion):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10r:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                f"echo '{assertion}' && npm view widgetcli version",
                stdout=f"{assertion}\n",
            ),
            {
                **_command_call(
                    2,
                    "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "cargo build --release && test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["diagnostics"] == []
    assert state["artifacts"][0]["status"] == "proven"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert state["status"] == "ready_for_final_proof"


def test_lowercase_ls_dash_l_is_not_custom_runtime_path_proof():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can be invoked.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:11:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, "ls -l /tmp/FooCC/foocc && test -x /tmp/FooCC/foocc", stdout="ok\n")]
    )

    assert build_attempts_from_command_evidence(evidence, contract)[0]["stage"] != "custom_runtime_smoke"


def test_reducer_maps_legacy_blocker_codes_to_generic_failure_class():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can be invoked.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(7, "curl -L -o /tmp/foocc.tar.gz https://github.com/example/FooCC/archive/v1.2.3.tar.gz")]
    )

    state = reduce_long_build_state(
        contract,
        build_attempts_from_command_evidence(evidence, contract),
        evidence,
        strategy_blockers=[
            {
                "code": "external_dependency_source_provenance_unverified",
                "source_tool_call_id": 7,
                "excerpt": "generated VCS archive",
            }
        ],
    )

    assert state["current_failure"]["failure_class"] == "source_authority_unverified"
    assert state["current_failure"]["legacy_code"] == "external_dependency_source_provenance_unverified"
    assert state["current_failure"]["evidence_id"] == 1
    assert {"id": "source_authority", "required": True, "status": "blocked"} in state["stages"]
