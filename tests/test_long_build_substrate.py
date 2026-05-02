import shlex

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


def test_long_dependency_artifact_proof_allows_status_echo_after_strict_artifact_proof():
    command = (
        "set -euo pipefail\n"
        "test -f /tmp/FooCC/foocc\n"
        "test -x /tmp/FooCC/foocc\n"
        "printf 'artifact_exists=true path=/tmp/FooCC/foocc\\n'\n"
        "/tmp/FooCC/foocc --version\n"
        "stat -c 'artifact_stat path=%n size=%s mode=%a' /tmp/FooCC/foocc\n"
        "printf 'required_artifact_final_status=verified path=/tmp/FooCC/foocc kind=executable\\n'"
    )
    stdout = (
        "artifact_exists=true path=/tmp/FooCC/foocc\n"
        "FooCC version 1.0\n"
        "artifact_stat path=/tmp/FooCC/foocc size=123 mode=755\n"
        "required_artifact_final_status=verified path=/tmp/FooCC/foocc kind=executable\n"
    )
    call = _command_call(9, command, stdout=stdout)
    evidence = synthesize_command_evidence_from_tool_calls([call])[0]

    assert long_dependency_artifact_proven_by_call(call, "/tmp/FooCC/foocc")
    assert long_dependency_artifact_proven_by_command_evidence(evidence, "/tmp/FooCC/foocc")


@pytest.mark.parametrize(
    "probe_command",
    [
        "ls /tmp/FooCC/foocc",
        "stat /tmp/FooCC/foocc",
        "file /tmp/FooCC/foocc",
    ],
)
def test_long_dependency_artifact_proof_rejects_status_echo_after_metadata_probe_only(probe_command):
    command = (
        "set -e\n"
        f"{probe_command}\n"
        "printf '/tmp/FooCC/foocc exists=true executable\\n'"
    )
    stdout = "/tmp/FooCC/foocc exists=true executable\n"
    call = _command_call(9, command, stdout=stdout)
    evidence = synthesize_command_evidence_from_tool_calls([call])[0]

    assert not long_dependency_artifact_proven_by_call(call, "/tmp/FooCC/foocc")
    assert not long_dependency_artifact_proven_by_command_evidence(evidence, "/tmp/FooCC/foocc")


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
    assert state["recovery_decision"]["failure_class"] == "runtime_default_path_unproven"
    assert state["recovery_decision"]["allowed_next_action"]["stage"] == "default_runtime_smoke"
    assert "custom_runtime_path_only_proof" in state["recovery_decision"]["prohibited_repeated_actions"]


def test_recovery_decision_selects_artifact_proof_for_missing_non_compcert_cli():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:recover-cli:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(
                    1,
                    "cargo build --release",
                    stdout="built helper crates\n",
                ),
                "parameters": {"command": "cargo build --release", "cwd": "/tmp/WidgetCLI"},
                "result": {
                    "command": "cargo build --release",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "built helper crates\n",
                },
            }
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["current_failure"]["failure_class"] == "artifact_missing_or_unproven"
    assert state["recovery_decision_id"] == "work_session:recover-cli:long_build:1:recovery:1"
    assert state["recovery_decision"]["allowed_next_action"]["stage"] == "target_build_or_artifact_proof"
    assert state["recovery_decision"]["allowed_next_action"]["targets"] == ["/tmp/WidgetCLI/widget"]
    assert state["suggested_next"] == ""


def test_recovery_decision_selects_runtime_repair_for_non_compcert_toolchain_link_failure():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:recover-runtime:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
            _command_call(
                2,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe",
                stderr="/usr/bin/ld: cannot find -lfoocc-runtime\n",
                exit_code=1,
            ),
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["current_failure"]["failure_class"] == "runtime_link_failed"
    assert state["recovery_decision"]["allowed_next_action"]["stage"] == "runtime_build_or_install"
    assert "source_reacquisition" in state["recovery_decision"]["prohibited_repeated_actions"]
    assert state["recovery_decision"]["budget"]["reserve_seconds"] == 60


def test_later_default_smoke_success_clears_prior_runtime_link_recovery_decision():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:recover-runtime-clear:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
            _command_call(
                2,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe",
                stderr="/usr/bin/ld: cannot find -lfoocc-runtime\n",
                exit_code=1,
            ),
            _command_call(
                3,
                "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe",
                stdout="default smoke ok\n",
            ),
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["status"] == "ready_for_final_proof"
    assert state["current_failure"] is None
    assert state["recovery_decision"] is None


def test_later_artifact_proof_success_clears_prior_build_timeout_recovery_decision():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:recover-timeout-clear:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, "cargo build --release", timed_out=True, status="completed"),
                "parameters": {"command": "cargo build --release", "cwd": "/tmp/WidgetCLI"},
                "result": {
                    "command": "cargo build --release",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": None,
                    "timed_out": True,
                    "stdout": "still building\n",
                },
            },
            {
                **_command_call(2, "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"),
                "parameters": {
                    "command": "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                    "exit_code": 0,
                    "stdout": "Widget usage\n",
                },
            },
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["status"] == "ready_for_final_proof"
    assert state["current_failure"] is None
    assert state["recovery_decision"] is None


def test_recovery_decision_selects_target_surface_repair_for_non_compcert_runtime_target():
    contract = build_long_build_contract(
        "Under /tmp/BarVM, build the BarVM interpreter from source. "
        "Ensure /tmp/BarVM/barvm can compile and link a program by default.",
        ["/tmp/BarVM/barvm"],
        contract_id="work_session:recover-target:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(
                    1,
                    "make runtime/libbarvm.a",
                    stderr="make: *** No rule to make target 'runtime/libbarvm.a'. Stop.\n",
                    exit_code=2,
                ),
                "parameters": {"command": "make runtime/libbarvm.a", "cwd": "/tmp/BarVM"},
                "result": {
                    "command": "make runtime/libbarvm.a",
                    "cwd": "/tmp/BarVM",
                    "exit_code": 2,
                    "stderr": "make: *** No rule to make target 'runtime/libbarvm.a'. Stop.\n",
                },
            }
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["current_failure"]["failure_class"] == "build_system_target_surface_invalid"
    assert state["recovery_decision"]["allowed_next_action"]["stage"] == "build_system_target_surface_probe"
    assert "retry_invalid_parent_target_path" in state["recovery_decision"]["prohibited_repeated_actions"]


def test_recovery_decision_selects_bounded_resume_for_build_timeout():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can be invoked.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:recover-timeout:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "make -j2 foocc",
                stdout="still building\n",
                timed_out=True,
                status="completed",
            )
        ]
    )

    state = reduce_long_build_state(contract, build_attempts_from_command_evidence(evidence, contract), evidence)

    assert state["current_failure"]["failure_class"] == "build_timeout"
    assert state["recovery_decision"]["allowed_next_action"]["stage"] == "continue_or_resume_build"
    assert "repeat_same_timeout_without_budget_change" in state["recovery_decision"]["prohibited_repeated_actions"]


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


def test_default_smoke_rejects_if_wrapped_echoed_compile_command_text():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j2:long_build:1",
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
                "if echo /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then echo printed; fi",
                stdout="/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_negated_required_artifact_invocation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j4:long_build:1",
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
                "! /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe",
                stdout="compiler failed as expected\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_negated_required_artifact_invocation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j5:long_build:1",
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
                "if ! /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then echo expected failure; fi",
                stdout="expected failure\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_wrapped_without_failure_exit_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j6:long_build:1",
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
                "if /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then echo ok; fi",
                stdout="",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_wrapped_with_unrelated_printed_failure_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j6b:long_build:1",
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
                "printf 'else exit 1\\n'\nif /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then echo ok; fi",
                stdout="else exit 1\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_wrapped_with_unrelated_one_line_failure_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j6c:long_build:1",
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
                (
                    "if echo /tmp/x.c -o /tmp/x; then :; else :; exit 1; fi\n"
                    "if /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then echo ok; fi"
                ),
                stdout="",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_wrapped_with_nested_unrelated_failure_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j6d:long_build:1",
    )
    command = (
        "if /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then\n"
        "  if true; then\n"
        "    :\n"
        "  else\n"
        "    exit 1\n"
        "  fi\n"
        "fi"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, command, stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_if_wrapped_with_prefixed_nested_failure_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j6e:long_build:1",
    )
    command = (
        "if /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then\n"
        "  true && if true; then\n"
        "    :\n"
        "  else\n"
        "    exit 1\n"
        "  fi\n"
        "fi"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, command, stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_while_wrapped_required_artifact_invocation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j7:long_build:1",
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
                "while /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; do break; done",
                stdout="",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_unreachable_elif_wrapped_artifact_invocation():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j8:long_build:1",
    )
    command = (
        "if true; then\n"
        "  :\n"
        "elif /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; then\n"
        "  :\n"
        "else\n"
        "  exit 1\n"
        "fi"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, command, stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_after_or_short_circuit():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j9:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "true || /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe", stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_or_short_circuit_when_segment_text_was_printed_earlier():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j9b:long_build:1",
    )
    smoke = "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, f"printf '{smoke}\\n'\ntrue || {smoke}", stdout=f"{smoke}\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_after_and_short_circuit():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10ja:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "false && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe", stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_after_dynamic_and_guard():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jaa:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "test -f /tmp/missing && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; echo done"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_when_failure_is_masked():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jb:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe || true", stdout=""),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_when_semicolon_masks_failure():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jc:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe; echo done", stdout="done\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_required_artifact_when_pipe_masks_failure():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jd:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "set -e\n/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe | cat; echo done", stdout="done\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_and_chain_when_later_semicolon_masks_failure():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10je:long_build:1",
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
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe; echo done",
                stdout="done\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_and_chain_when_later_pipeline_masks_failure():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jf:long_build:1",
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
                "set -e\n"
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe | cat; echo done",
                stdout="done\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_allows_later_pipefail_metadata_pipeline_after_strict_smoke():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jf2:long_build:1",
    )
    source_command = (
        "set -e -o pipefail\n"
        "curl -fL https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz -o /tmp/foocc.tgz\n"
        "printf 'authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\\n'"
    )
    final_command = (
        "set -euo pipefail\n"
        "cd /tmp/FooCC\n"
        "make -j4 foocc\n"
        "test -f /tmp/FooCC/foocc\n"
        "test -x /tmp/FooCC/foocc\n"
        "/tmp/FooCC/foocc --version\n"
        "cat > /tmp/foocc-proof.c <<'EOF'\n"
        "int main(void) { return 0; }\n"
        "EOF\n"
        "/tmp/FooCC/foocc /tmp/foocc-proof.c -o /tmp/foocc-proof\n"
        "test -x /tmp/foocc-proof\n"
        "/tmp/foocc-proof\n"
        "stat -c 'artifact_stat path=%n size=%s mode=%a' /tmp/FooCC/foocc\n"
        "sha256sum /tmp/FooCC/foocc | sed 's/^/artifact_sha256=/'\n"
        "printf 'required_artifact_final_status=verified path=/tmp/FooCC/foocc\\n'"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                source_command,
                stdout="authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\n",
            ),
            _command_call(
                2,
                final_command,
                stdout=(
                    "FooCC version 1.0\n"
                    "artifact_stat path=/tmp/FooCC/foocc size=123 mode=755\n"
                    "artifact_sha256=abc  /tmp/FooCC/foocc\n"
                    "required_artifact_final_status=verified path=/tmp/FooCC/foocc\n"
                ),
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[-1]["stage"] == "default_smoke"
    assert attempts[-1]["produced_artifacts"] == [{"path": "/tmp/FooCC/foocc", "proof_evidence_id": 2}]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "target_built", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["current_failure"] is None
    assert state["status"] == "complete"


def test_default_smoke_rejects_backgrounded_artifact_compile():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jg:long_build:1",
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "curl -L -o /tmp/foocc.tar.gz https://example.test/foocc-1.0.tar.gz",
                stdout="official release archive\n",
            ),
            _command_call(2, "set -e\n/tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe & echo done", stdout="done\n"),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_rejects_backgrounded_followup_probe():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10jh:long_build:1",
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
                "set -e\n"
                "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe && /tmp/probe & echo done",
                stdout="done\n",
            ),
            _command_call(3, "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version", stdout="FooCC 1.0\n"),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "command"
    assert attempts[1]["produced_artifacts"] == []
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_default_path_unproven"


def test_default_smoke_does_not_clear_successful_if_with_runtime_link_failure_output():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure /tmp/FooCC/foocc can compile and link a program by default.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:10j3:long_build:1",
    )
    command = (
        "if /tmp/FooCC/foocc /tmp/probe.c -o /tmp/probe > /tmp/probe.log 2>&1; then\n"
        "  cat /tmp/probe.log\n"
        "else\n"
        "  cat /tmp/probe.log\n"
        "fi"
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
                command,
                stdout="/usr/bin/ld: cannot find -lfoocc: No such file or directory\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[1]["stage"] == "default_smoke"
    assert attempts[1]["diagnostics"][0]["failure_class"] == "runtime_link_failed"
    assert {"id": "default_smoke", "required": True, "status": "unknown"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "runtime_link_failed"


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


def test_source_authority_accepts_combined_final_proof_with_headers():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2:long_build:1",
    )
    command = (
        "set -e\n"
        "printf '== upstream source authority proof ==\\n'\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz\n"
        "printf 'authority_archive_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "printf 'remote_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_top=WidgetCLI-1.0.0\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "== upstream source authority proof ==\n"
        "authority_archive_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        "remote_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_top=WidgetCLI-1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]


def test_source_authority_accepts_validated_archive_loop_when_output_is_truncated():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2b:long_build:1",
    )
    source_command = (
        "set -eu\n"
        "rm -rf /tmp/WidgetCLI /tmp/widgetcli-extract /tmp/widgetcli-1.0.0.tgz\n"
        "mkdir -p /tmp/widgetcli-extract\n"
        "found=''\n"
        "for url in \\\n"
        "  https://example.test/not-found/widgetcli-1.0.0.tgz \\\n"
        "  https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        " do\n"
        "  rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "  if curl -fL --retry 2 -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "    if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "      found=\"$url\"\n"
        "      break\n"
        "    fi\n"
        "  fi\n"
        "done\n"
        "test -n \"$found\"\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
        "cd /tmp/WidgetCLI\n"
        "sed -n '1,20p' README.md || true\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                source_command,
                stdout=("download progress\n" * 200) + "WidgetCLI source extracted\n" + ("readme line\n" * 200),
            ),
            {
                **_command_call(
                    2,
                    "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    stdout="Widget usage\n",
                ),
                "parameters": {
                    "command": "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                    "cwd": "/tmp/WidgetCLI",
                },
                "result": {
                    "command": "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
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
    assert {"signal": "source_authority", "excerpt": "validated source archive acquisition"} in attempts[0]["diagnostics"]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert state["status"] == "complete"


def test_source_authority_accepts_validated_archive_loop_with_same_line_do_header():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2same:long_build:1",
    )
    command = (
        "set -eu\n"
        "mkdir -p /tmp/widgetcli-extract\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "  if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "    if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "      found=\"$url\"\n"
        "      break\n"
        "    fi\n"
        "  fi\n"
        "done\n"
        "test -n \"$found\"\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, command, stdout=("download progress\n" * 200) + "WidgetCLI source extracted\n"),
            _command_call(
                2,
                "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help",
                stdout="Widget usage\n",
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert {"signal": "source_authority", "excerpt": "validated source archive acquisition"} in attempts[0]["diagnostics"]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]


def test_source_authority_accepts_post_loop_validated_archive_fetch_with_later_build_failure():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2post:long_build:1",
    )
    command = (
        "set -eu\n"
        "rm -rf /tmp/widgetcli-fetch /tmp/WidgetCLI\n"
        "mkdir -p /tmp/widgetcli-fetch\n"
        "cd /tmp/widgetcli-fetch\n"
        "source_url=''\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  if curl -fL -o widgetcli-src.tar.gz \"$url\"; then\n"
        "    source_url=\"$url\"\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "test -n \"$source_url\"\n"
        "printf 'source_url=%s\\n' \"$source_url\"\n"
        "sha256sum widgetcli-src.tar.gz\n"
        "top=$(tar -tzf widgetcli-src.tar.gz | head -1 | cut -d/ -f1)\n"
        "tar -C /tmp -xzf widgetcli-src.tar.gz\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
        "cd /tmp/WidgetCLI\n"
        "make widget\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                command,
                exit_code=2,
                stdout=(
                    "source_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
                    "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  widgetcli-src.tar.gz\n"
                    "Error: later build failed\n"
                ),
                stderr="make: *** [widget] Error 2\n",
            )
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "target_built", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_post_loop_selected_fetch_without_clean_archive_path():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2postbad:long_build:1",
    )
    command = (
        "set -eu\n"
        "source_url=''\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  if curl -fL -o widgetcli-src.tar.gz \"$url\"; then\n"
        "    source_url=\"$url\"\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "test -n \"$source_url\"\n"
        "printf 'source_url=%s\\n' \"$source_url\"\n"
        "sha256sum widgetcli-src.tar.gz\n"
        "top=$(tar -tzf widgetcli-src.tar.gz | head -1 | cut -d/ -f1)\n"
        "tar -C /tmp -xzf widgetcli-src.tar.gz\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="source_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_failed_fetch_with_source_url_printed_before_download():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2post404:long_build:1",
    )
    command = (
        "set -eu\n"
        "printf 'source_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                command,
                exit_code=22,
                stdout="source_url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n",
                stderr="curl: (22) The requested URL returned error: 404\n",
            )
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "stdout",
    [
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  widgetcli-src.tar.gz\n",
    ],
)
def test_source_authority_rejects_failed_fetch_with_hash_marker_printed_before_download(stdout):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthash404:long_build:1",
    )
    command = (
        "set -eu\n"
        f"printf '%s' {shlex.quote(stdout)}\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                command,
                exit_code=22,
                stdout=stdout,
                stderr="curl: (22) The requested URL returned error: 404\n",
            )
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_nonzero_fetch_with_clipped_failure_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2postclip404:long_build:1",
    )
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "stdout",
    [
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  widgetcli-src.tar.gz\n",
    ],
)
def test_source_authority_rejects_nonzero_fetch_with_preprinted_hash_and_clipped_failure(stdout):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashclip:long_build:1",
    )
    command = (
        "set -eu\n"
        f"printf '%s' {shlex.quote(stdout)}\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o widgetcli-src.tar.gz "
        "2>/tmp/curl.err\n"
        "tar -tzf widgetcli-src.tar.gz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf widgetcli-src.tar.gz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_nonzero_fetch_with_preprinted_hash_and_later_static_hash_command():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashstatic:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        f"printf '%s' {shlex.quote(stdout)}\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    ("stdout", "print_command"),
    [
        (
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n",
            "printf '%s  /tmp/widgetcli-1.0.0.tgz\\n' \"$h\"\n",
        ),
        (
            "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n",
            "printf 'archive_sha256=%s\\n' \"$h\"\n",
        ),
    ],
)
def test_source_authority_rejects_nonzero_fetch_with_dynamic_preprinted_hash_and_later_static_hash_command(
    stdout,
    print_command,
):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashdynamic:long_build:1",
    )
    command = (
        "set -eu\n"
        "h=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        f"{print_command}"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    ("stdout", "heredoc_body"),
    [
        (
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n",
            "$h  /tmp/widgetcli-1.0.0.tgz\n",
        ),
        (
            "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n",
            "archive_sha256=$h\n",
        ),
    ],
)
def test_source_authority_rejects_nonzero_fetch_with_prefetch_heredoc_hash_and_later_static_hash_command(
    stdout,
    heredoc_body,
):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashheredoc:long_build:1",
    )
    command = (
        "set -eu\n"
        "h=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "cat <<EOF\n"
        f"{heredoc_body}"
        "EOF\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_nonzero_fetch_with_prefetch_python_hash_and_later_static_hash_command():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashpython:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "python3 -c 'print(\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  "
        "/tmp/widgetcli-1.0.0.tgz\")'\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_nonzero_fetch_with_prefetch_python_dynamic_hash_and_later_static_hash_command():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashpythondyn:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "python3 -c 'h=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"; "
        "p=\"/tmp/widgetcli-1.0.0.tgz\"; print(h, p)'\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz "
        "2>/tmp/curl.err\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=22, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_post_fetch_python_hash_before_later_hash_and_validation_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2postfetchhash:long_build:1",
    )
    stdout = (
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
        "make: *** [widget] Error 2\n"
    )
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "python3 -c 'h=\"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\"; "
        "p=\"/tmp/widgetcli-1.0.0.tgz\"; print(h, p)'\n"
        "make widget\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=2, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_same_line_stdout_before_fetch_with_later_ordered_source_proof():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2samecatfetch:long_build:1",
    )
    stdout = (
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
        "make: *** [widget] Error 2\n"
    )
    command = (
        "set -eu\n"
        "cat /tmp/precomputed-hash.txt; "
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
        "make widget\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=2, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_failable_setup_between_hash_and_later_validation_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashfailable:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "test -f /tmp/definitely-missing-source-proof-sentinel\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=1, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_failable_assignment_between_hash_and_later_validation_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashsubst:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "probe=$(false)\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=1, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_nounset_assignment_between_hash_and_later_validation_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashnounset:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "probe=$UNSET_SOURCE_PROOF_SENTINEL\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=1, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_failable_builtin_between_hash_and_later_validation_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2posthashexport:long_build:1",
    )
    stdout = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tgz\n"
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "sha256sum /tmp/widgetcli-1.0.0.tgz\n"
        "export -z\n"
        "top=$(tar -tzf /tmp/widgetcli-1.0.0.tgz | head -1 | cut -d/ -f1)\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp\n"
        "mv \"/tmp/$top\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, exit_code=2, stdout=stdout)]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_loop_without_archive_validation():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2c:long_build:1",
    )
    command = (
        "set -eu\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"\n"
        "done\n"
        "echo extracted\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert attempts[0]["stage"] == "source_acquisition"
    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_comment_only_authoritative_url_with_mirror_archive():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2d:long_build:1",
    )
    command = (
        "set -eu\n"
        "# https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        "curl -fL -o /tmp/widgetcli-1.0.0.tgz https://mirror.example.invalid/widgetcli-1.0.0.tgz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_loop_fetch_when_different_local_archive_is_validated():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2e:long_build:1",
    )
    command = (
        "set -eu\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  if curl -fL -o /tmp/fetched-widgetcli.tgz \"$url\"; then\n"
        "    found=\"$url\"\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "test -n \"$found\"\n"
        "tar -tzf /tmp/local-widgetcli.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_loop_no_download_probe():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2f:long_build:1",
    )
    command = (
        "set -eu\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  if curl -I \"$url\"; then\n"
        "    found=\"$url\"\n"
        "    break\n"
        "  fi\n"
        "done\n"
        "test -n \"$found\"\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "validation_line,extraction_line,move_line",
    [
        (
            "echo 'tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt'",
            "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract",
            "mv \"$root\" /tmp/WidgetCLI",
        ),
        (
            "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt",
            "echo 'tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract'",
            "mv \"$root\" /tmp/WidgetCLI",
        ),
        (
            "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt",
            "cat > /tmp/extract-note.txt <<'EOF'\ntar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\nEOF",
            "mv \"$root\" /tmp/WidgetCLI",
        ),
        (
            "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt",
            "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract",
            "echo 'mv \"$root\" /tmp/WidgetCLI'",
        ),
    ],
)
def test_source_authority_rejects_archive_validation_extract_or_move_text_only(validation_line, extraction_line, move_line):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2g:long_build:1",
    )
    command = (
        "set -eu\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        f"{validation_line}\n"
        f"{extraction_line}\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        f"{move_line}\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "sentinel_line",
    [
        "# found=\"$url\"",
        "echo 'found=\"$url\"'",
        "cat > /tmp/found-note.txt <<'EOF'\nfound=\"$url\"\nEOF",
    ],
)
def test_source_authority_rejects_loop_selected_url_sentinel_text_only(sentinel_line):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2h:long_build:1",
    )
    command = (
        "set -eu\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "  if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "    if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        f"      {sentinel_line}\n"
        "      break\n"
        "    fi\n"
        "  fi\n"
        "done\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_loop_fetch_without_stale_archive_removal():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2i:long_build:1",
    )
    command = (
        "set -eu\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "    if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "      found=\"$url\"\n"
        "      break\n"
        "    fi\n"
        "  fi\n"
        "done\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_candidate_loop_inside_unexecuted_heredoc():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2j:long_build:1",
    )
    command = (
        "set -eu\n"
        "cat > /tmp/fetch-script.sh <<'EOF'\n"
        "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "  rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "  if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "    if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "      found=\"$url\"\n"
        "      break\n"
        "    fi\n"
        "  fi\n"
        "done\n"
        "EOF\n"
        "# /tmp/fetch-script.sh is intentionally not executed\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_direct_fetch_inside_unexecuted_heredoc():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2k:long_build:1",
    )
    command = (
        "set -eu\n"
        "cat > /tmp/fetch-script.sh <<'EOF'\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "EOF\n"
        "# /tmp/fetch-script.sh is intentionally not executed\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "function_body",
    [
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz",
        (
            "for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
            "    rm -f /tmp/widgetcli-1.0.0.tgz\n"
            "    if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
            "      if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
            "        found=\"$url\"\n"
            "        break\n"
            "      fi\n"
            "    fi\n"
            "  done"
        ),
    ],
)
def test_source_authority_rejects_fetch_inside_unexecuted_shell_function(function_body):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2l:long_build:1",
    )
    command = (
        "set -eu\n"
        "fetch_src() {\n"
        f"  {function_body}\n"
        "}\n"
        "# fetch_src is intentionally not called\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_candidate_loop_inside_unexecuted_if_branch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2m:long_build:1",
    )
    command = (
        "set -eu\n"
        "if false; then\n"
        "  for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "    rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "    if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "      if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "        found=\"$url\"\n"
        "        break\n"
        "      fi\n"
        "    fi\n"
        "  done\n"
        "fi\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_direct_fetch_inside_unexecuted_if_branch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2n:long_build:1",
    )
    command = (
        "set -eu\n"
        "if false; then\n"
        "  curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "fi\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_direct_fetch_inside_multiline_unexecuted_if_branch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2n2:long_build:1",
    )
    command = (
        "set -eu\n"
        "if false\n"
        "then\n"
        "  curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "fi\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_direct_fetch_inside_prefixed_unexecuted_if_branch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2n3:long_build:1",
    )
    command = (
        "set -eu\n"
        ":; if false; then\n"
        "  curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        "fi\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "control_open,control_close",
    [
        ("while false; do", "done"),
        ("until true; do", "done"),
        ("while false\ndo", "done"),
        ("until true\ndo", "done"),
    ],
)
def test_source_authority_rejects_direct_fetch_inside_unexecuted_loop_body(control_open, control_close):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2o:long_build:1",
    )
    command = (
        "set -eu\n"
        f"{control_open}\n"
        "  curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli-1.0.0.tgz\n"
        f"{control_close}\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_candidate_loop_inside_unexecuted_loop_body():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2p:long_build:1",
    )
    command = (
        "set -eu\n"
        "while false; do\n"
        "  for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "    rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "    if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "      if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "        found=\"$url\"\n"
        "        break\n"
        "      fi\n"
        "    fi\n"
        "  done\n"
        "done\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_candidate_loop_inside_multiline_unexecuted_loop_body():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2q:long_build:1",
    )
    command = (
        "set -eu\n"
        "while false\n"
        "do\n"
        "  for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "    rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "    if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "      if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "        found=\"$url\"\n"
        "        break\n"
        "      fi\n"
        "    fi\n"
        "  done\n"
        "done\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_candidate_loop_inside_prefixed_unexecuted_if_branch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k2r:long_build:1",
    )
    command = (
        "set -eu\n"
        ":; if false; then\n"
        "  for url in https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz; do\n"
        "    rm -f /tmp/widgetcli-1.0.0.tgz\n"
        "    if curl -fL -o /tmp/widgetcli-1.0.0.tgz \"$url\"; then\n"
        "      if tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt; then\n"
        "        found=\"$url\"\n"
        "        break\n"
        "      fi\n"
        "    fi\n"
        "  done\n"
        "fi\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tgz >/tmp/widgetcli-tar-list.txt\n"
        "tar -xzf /tmp/widgetcli-1.0.0.tgz -C /tmp/widgetcli-extract\n"
        "root=$(find /tmp/widgetcli-extract -mindepth 1 -maxdepth 1 -type d | head -n 1)\n"
        "mv \"$root\" /tmp/WidgetCLI\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [_command_call(1, command, stdout="extracted\n")]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_accepts_saved_authority_page_with_archive_identity():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3:long_build:1",
    )
    command = (
        "set -eu\n"
        "archive=/tmp/widgetcli-1.0.0.tar.gz\n"
        "[ -s \"$archive\" ]\n"
        "printf 'archive_sha256='; sha256sum \"$archive\" | awk '{print $1}'\n"
        "root=\"$(tar -tzf \"$archive\" | sed -n '1s#/.*##p')\"\n"
        "printf 'archive_root=%s\\n' \"$root\"\n"
        "if [ -s /tmp/widgetcli-release.html ] && grep -q 'v1.0.0' /tmp/widgetcli-release.html; then\n"
        "  echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "else\n"
        "  curl --proto '=https' --tlsv1.2 -fsSL https://github.com/example/WidgetCLI/releases/tag/v1.0.0 -o /tmp/widgetcli-release.html\n"
        "  grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "  echo 'authority_page_fetched=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "fi\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert {"signal": "source_authority", "excerpt": "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0"} in attempts[0][
        "diagnostics"
    ]
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]


def test_source_authority_accepts_saved_authority_page_archive_readback():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3b:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "if [ -f /tmp/widgetcli-release.html ]; then\n"
        "  grep -Ei 'Earlier releases|Git repository|Source distribution' /tmp/widgetcli-release.html | sed -n '1,20p'\n"
        "fi\n"
        "if [ -f /tmp/widgetcli-tag.json ]; then\n"
        "  grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "fi\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  <a href="https://github.com/example/WidgetCLI/releases">Earlier releases</a>\n'
        '  "ref": "refs/tags/v1.0.0",\n'
        '    "sha": "abcdef0123456789abcdef0123456789abcdef01",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "WidgetCLI-1.0.0/README.md\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]


def test_source_authority_accepts_saved_tag_json_archive_readback():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3json:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        '    "sha": "abcdef0123456789abcdef0123456789abcdef01",\n'
        '    "url": "https://api.github.com/repos/example/WidgetCLI/git/commits/abcdef0123456789abcdef01"\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "WidgetCLI-1.0.0/README.md\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]


def test_source_authority_rejects_guarded_archive_readback_even_when_xtrace_like_output_exists():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3xtrace:long_build:1",
    )
    command = (
        "set -euxo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "if [ -f /tmp/widgetcli-1.0.0.tar.gz ]; then sha256sum /tmp/widgetcli-1.0.0.tar.gz; "
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz | sed -n '1,4p'; fi\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "+ sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "+ tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    stderr = (
        "+ sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "+ tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout, stderr=stderr),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout, "stderr": stderr},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_readback_without_real_archive_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3c:long_build:1",
    )
    command = (
        "set -eu\n"
        "grep -Ei 'Earlier releases|Git repository|Source distribution' /tmp/widgetcli-release.html | sed -n '1,20p'\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  <a href="https://github.com/example/WidgetCLI/releases">Earlier releases</a>\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_unexecuted_guarded_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3skip:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "if false; then sha256sum /tmp/widgetcli-1.0.0.tar.gz; tar -tzf /tmp/widgetcli-1.0.0.tar.gz; fi\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "+ sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "+ tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_unexecuted_loop_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3loopskip:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "while false; do sha256sum /tmp/widgetcli-1.0.0.tar.gz; "
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz; done\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_uncalled_function_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3funcskip:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "readback() { sha256sum /tmp/widgetcli-1.0.0.tar.gz; tar -tzf /tmp/widgetcli-1.0.0.tar.gz; }\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_redirected_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3redirect:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz >/tmp/hash.out\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz >/tmp/list.out\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_pipeline_redirected_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3piperedirect:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz | cat >/tmp/hash.out\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz | sed -n '1,4p' >/tmp/list.out\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_exec_redirected_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3execredirect:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "exec 3>&1\n"
        "exec >/tmp/readback.out\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "exec >&3\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "redirect_sequence",
    [
        "exec >&3 >/tmp/readback.out\n",
        "exec 1<>/tmp/readback.out\n",
    ],
)
def test_source_authority_rejects_exec_redirect_variants_before_archive_readback(redirect_sequence):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3execvariant:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "exec 3>&1\n"
        f"{redirect_sequence}"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        "exec >&3\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "open_token,close_token,redirection",
    [
        ("{", "}", ">"),
        ("(", ")", ">"),
        ("{", "}", "&>"),
        ("{", "}", "&>>"),
        ("time (", ")", ">"),
        ("time -p (", ")", ">"),
        ("time -p {", "}", ">"),
    ],
)
def test_source_authority_rejects_compound_redirected_archive_readback_with_printed_output(
    open_token, close_token, redirection
):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3compoundredirect:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        f"{open_token}\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz\n"
        f"{close_token} {redirection}/tmp/readback.out\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_backgrounded_archive_readback_with_printed_output():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3background:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -E '\"ref\"|\"sha\"|\"url\"' /tmp/widgetcli-tag.json | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz &\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz &\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  "ref": "refs/tags/v1.0.0",\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_readback_with_masked_archive_commands():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3masked:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -Ei 'Earlier releases|Git repository|Source distribution' /tmp/widgetcli-release.html | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz || true\n"
        "tar -tzf /tmp/widgetcli-1.0.0.tar.gz | sed -n '1,4p' || true\n"
        "printf '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\\n'\n"
        "printf 'WidgetCLI-1.0.0/\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  <a href="https://github.com/example/WidgetCLI/releases">Earlier releases</a>\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_readback_with_mismatched_archive_paths():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3d:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "grep -Ei 'Earlier releases|Git repository|Source distribution' /tmp/widgetcli-release.html | sed -n '1,20p'\n"
        "sha256sum /tmp/widgetcli-1.0.0.tar.gz\n"
        "tar -tzf /tmp/other-widgetcli-1.0.0.tar.gz | sed -n '1,4p'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help\n"
    )
    stdout = (
        '  <a href="https://github.com/example/WidgetCLI/releases">Earlier releases</a>\n'
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  /tmp/widgetcli-1.0.0.tar.gz\n"
        "WidgetCLI-1.0.0/\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_without_archive_identity():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k4:long_build:1",
    )
    command = (
        "set -eu\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_echoed_authority_page_without_page_readback_or_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k5:long_build:1",
    )
    command = (
        "set -eu\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_python_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k6:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3 <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlretrieve('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz', '/tmp/widgetcli.tgz')\n"
        "PY\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_aliased_python_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k7:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3 <<'PY'\n"
        "from urllib.request import urlretrieve\n"
        "urlretrieve('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz', '/tmp/widgetcli.tgz')\n"
        "PY\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_python_dash_c_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k8:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3 -c \"from urllib.request import urlretrieve; "
        "urlretrieve('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz', '/tmp/widgetcli.tgz')\"\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_versioned_python_dash_c_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k9:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3.11 -c \"from urllib.request import urlretrieve; "
        "urlretrieve('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz', '/tmp/widgetcli.tgz')\"\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_python_keyword_url_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10ka:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3 <<'PY'\n"
        "import requests\n"
        "requests.get(url='https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_saved_authority_page_after_python_keyword_url_variable_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10kb:long_build:1",
    )
    command = (
        "set -eu\n"
        "python3 <<'PY'\n"
        "import requests\n"
        "url = 'https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz'\n"
        "requests.get(url=url)\n"
        "PY\n"
        "printf 'archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\\n'\n"
        "printf 'archive_root=WidgetCLI-1.0.0\\n'\n"
        "grep -q 'v1.0.0' /tmp/widgetcli-release.html\n"
        "echo 'authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "archive_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\n"
        "archive_root=WidgetCLI-1.0.0\n"
        "authority_page_saved=https://github.com/example/WidgetCLI/releases/tag/v1.0.0\n"
        "Widget usage\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "stdout",
    [
        "local_sha256=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef\nWidget usage\n",
        "archive_top=WidgetCLI-1.0.0\nWidget usage\n",
    ],
)
def test_source_authority_rejects_local_identity_only_direct_output(stdout):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10k3:long_build:1",
    )
    command = (
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz\n"
        "sha256sum /tmp/widgetcli.tgz\n"
        "tar -tzf /tmp/widgetcli.tgz | sed -n '1p'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


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


def test_source_authority_rejects_local_printed_url_without_remote_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l2:long_build:1",
    )
    command = (
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "printf 'url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "url=https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_non_fetch_curl_command():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3:long_build:1",
    )
    command = (
        "curl --version\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "curl 8.5.0\nCHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_that_does_not_match_fetched_url():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3a:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://example.com/robots.txt -o /tmp/robots.txt\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_that_only_appears_in_curl_header():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3aa:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://example.com/robots.txt "
        "-H 'Referer: https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz' "
        "-o /tmp/robots.txt\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_that_only_appears_as_curl_output_path():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ab:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL -o https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz "
        "https://example.com/robots.txt\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "fetch_command",
    [
        "curl -fL -r 0-0 https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz",
        "curl -fL --range 0-0 https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz",
        "wget --header 'Range: bytes=0-0' https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -O /tmp/widgetcli.tgz",
    ],
)
def test_source_authority_rejects_partial_range_archive_fetch(fetch_command):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ac:long_build:1",
    )
    command = (
        "set -e\n"
        f"{fetch_command}\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


@pytest.mark.parametrize(
    "fetch_command",
    [
        "curl -XHEAD https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz",
        "curl -fLXHEAD https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz",
    ],
)
def test_source_authority_rejects_attached_head_request(fetch_command):
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ad:long_build:1",
    )
    command = (
        "set -e\n"
        f"{fetch_command}\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_masked_failed_curl_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3b:long_build:1",
    )
    command = (
        "curl -fL https://bad.example.invalid/widget.tgz -o /tmp/widgetcli.tgz || true\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_line_continued_masked_curl_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ba:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://bad.example.invalid/widget.tgz \\\n"
        "  -o /tmp/widgetcli.tgz || true\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_or_short_circuited_curl_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3bb:long_build:1",
    )
    command = (
        "set -e\n"
        "true || curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_and_short_circuited_curl_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3bc:long_build:1",
    )
    command = (
        "set -e\n"
        "false && curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_multiline_curl_without_errexit():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3c:long_build:1",
    )
    command = (
        "curl -fL https://bad.example.invalid/widget.tgz -o /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_when_errexit_starts_after_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3d:long_build:1",
    )
    command = (
        "curl -fL https://bad.example.invalid/widget.tgz -o /tmp/widgetcli.tgz\n"
        "set -e\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_errexit_disabled_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3e:long_build:1",
    )
    command = (
        "set -e\n"
        "set +e\n"
        "curl -fL https://bad.example.invalid/widget.tgz -o /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_errexit_disabled_with_set_o_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ea:long_build:1",
    )
    command = (
        "set -e\n"
        "set +o errexit\n"
        "curl -fL https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz -o /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_fetch_pipeline_without_pipefail():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3f:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://bad.example.invalid/widget.tgz | tar -xz -C /tmp\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_masked_gh_release_download():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3g:long_build:1",
    )
    command = (
        "set -e\n"
        "gh release download v1.0.0 -R example/WidgetCLI -p '*.tar.gz' || true\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_and_list_fetch_exception():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3h:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://bad.example.invalid/widget.tgz -o /tmp/widgetcli.tgz && echo fetched\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/local-widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_fake_pipefail_mention():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3i:long_build:1",
    )
    command = (
        "set -e\n"
        "printf 'pipefail\\n'\n"
        "curl -fL https://bad.example.invalid/widget.tgz | tar -xz -C /tmp\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "pipefail\nCHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_pipefail_disabled_before_pipeline():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3ia:long_build:1",
    )
    command = (
        "set -e -o pipefail\n"
        "set +o pipefail\n"
        "curl -fL https://bad.example.invalid/widget.tgz | cat > /tmp/widgetcli.tgz\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_pipefail_comment_on_set_line():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l3j:long_build:1",
    )
    command = (
        "set -e # pipefail mentioned only\n"
        "curl -fL https://bad.example.invalid/widget.tgz | tar -xz -C /tmp\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\nWidget usage\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_python_textual_fetch_spoof():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l4:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "# urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "if False:\n"
        "    urllib.request.urlopen()\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_python_triple_quoted_fetch_spoof():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l5:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "\"\"\"\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "\"\"\"\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_printed_url_after_swallowed_python_fetch_failure():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l6:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_before_swallowed_python_fetch_failure():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l7:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "    urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_dead_python_fetch_in_try():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l8:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    if False:\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_never_called_python_fetch_in_try():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10l9:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    def never_called():\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_lambda_python_fetch_in_try():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10la:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    never_called = lambda: urllib.request.urlopen("
        "'https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_top_level_never_called_python_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lb:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "def never_called():\n"
        "    urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_top_level_lambda_python_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lc:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "never_called = lambda: urllib.request.urlopen("
        "'https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_short_circuit_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10ld:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "False and urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_literal_true_else_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lh:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "if True:\n"
        "    pass\n"
        "else:\n"
        "    urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_empty_comprehension_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10le:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "[urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz') for _ in []]\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_short_circuit_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lf:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    False and urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_literal_true_else_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10li:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    if 1:\n"
        "        pass\n"
        "    else:\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_empty_if_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lj:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    if []:\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_empty_for_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lk:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    for _ in []:\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_empty_dict_for_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10ll:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    for _ in {}:\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_empty_string_for_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lm:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    for _ in '':\n"
        "        urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_unconditional_raise():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10ln:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    raise RuntimeError('skip')\n"
        "    urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_sys_exit_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lo:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import sys\n"
        "import urllib.request\n"
        "sys.exit(0)\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_shell_archive_print_after_failed_python_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://bad.example.invalid/widget.tgz')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(
                    1,
                    command,
                    stdout=stdout,
                    stderr="urllib.error.URLError: <urlopen error [Errno -3] Temporary failure in name resolution>\n",
                ),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_without_errexit_guard():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp2:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_with_errexit_masked_by_or_true():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp3:long_build:1",
    )
    command = (
        "set -e\n"
        "python3 - <<'PY' || true\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_with_pipeline_without_pipefail():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp4:long_build:1",
    )
    command = (
        "set -e\n"
        "python3 - <<'PY' | cat > /tmp/fetch.log\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_when_used_as_if_condition():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp5:long_build:1",
    )
    command = (
        "set -e\n"
        "if python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "then :; else true; fi\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_when_wrapped_as_if_condition():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp5b:long_build:1",
    )
    command = (
        "set -e\n"
        "if env python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "then :; else true; fi\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_inside_shell_function_condition():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp5c:long_build:1",
    )
    command = (
        "set -e\n"
        "fetch_src() {\n"
        "  python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "}\n"
        "if fetch_src; then :; else true; fi\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_python_fetch_archive_when_negated_by_shell():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lp6:long_build:1",
    )
    command = (
        "set -e\n"
        "! python3 - <<'PY'\n"
        "import urllib.request\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "PY\n"
        "printf 'ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\\n'\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_aliased_sys_exit_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lq:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "from sys import exit as done\n"
        "import urllib.request\n"
        "done(0)\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_module_alias_exit_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lr:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import sys as s\n"
        "import urllib.request\n"
        "s.exit(0)\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_python_ordinary_raising_call_before_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10ls:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "int('x')\n"
        "urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


def test_source_authority_rejects_archive_print_after_try_body_empty_comprehension_fetch():
    contract = build_long_build_contract(
        "Under /tmp/WidgetCLI, build the Widget CLI from source. "
        "Ensure /tmp/WidgetCLI/widget can be invoked.",
        ["/tmp/WidgetCLI/widget"],
        contract_id="work_session:10lg:long_build:1",
    )
    command = (
        "python3 - <<'PY'\n"
        "import urllib.request\n"
        "try:\n"
        "    [urllib.request.urlopen('https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz') for _ in []]\n"
        "    print('ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789')\n"
        "except Exception:\n"
        "    pass\n"
        "print('CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz')\n"
        "PY\n"
        "tar -xzf /tmp/widgetcli.tgz -C /tmp\n"
        "test -x /tmp/WidgetCLI/widget && /tmp/WidgetCLI/widget --help"
    )
    stdout = (
        "ARCHIVE /tmp/local.tgz bytes=12345 "
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "CHOSEN https://github.com/example/WidgetCLI/archive/refs/tags/v1.0.0.tar.gz\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            {
                **_command_call(1, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/WidgetCLI"},
                "result": {"command": command, "cwd": "/tmp/WidgetCLI", "exit_code": 0, "stdout": stdout},
            }
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(contract, attempts, evidence)

    assert not any(item.get("signal") == "source_authority" for item in attempts[0]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]


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


def test_reducer_clears_stale_strategy_blockers_after_final_contract_proof():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12b:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz -o /tmp/foocc.tgz\n"
        "printf 'authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\\n'\n"
        "printf 'remote_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'archive_top=FooCC-1.2.3\\n'\n"
        "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version\n"
        "cat > /tmp/foocc_smoke.c <<'EOF'\nint main(void) { return 0; }\nEOF\n"
        "/tmp/FooCC/foocc -o /tmp/foocc_smoke /tmp/foocc_smoke.c\n"
        "/tmp/foocc_smoke"
    )
    stdout = (
        "authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\n"
        "remote_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "archive_top=FooCC-1.2.3\n"
        "FooCC version 1.2.3\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "curl -L -o /tmp/foocc.tgz https://github.com/example/FooCC/archive/v1.2.3.tar.gz"),
            {
                **_command_call(2, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/FooCC"},
                "result": {"command": command, "cwd": "/tmp/FooCC", "exit_code": 0, "stdout": stdout},
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "external_dependency_source_provenance_unverified",
                "source_tool_call_id": 1,
                "excerpt": "generated VCS archive",
            },
            {
                "code": "vendored_dependency_patch_surgery_before_supported_branch",
                "source_tool_call_id": 1,
                "excerpt": "local proof surgery before supported branch",
            },
        ],
    )

    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "target_built", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["current_failure"] is None
    assert state["recovery_decision"] is None
    assert state["strategy_blockers"] == []
    assert [item["code"] for item in state["cleared_strategy_blockers"]] == [
        "external_dependency_source_provenance_unverified",
        "vendored_dependency_patch_surgery_before_supported_branch",
    ]
    assert state["status"] == "complete"


def test_reducer_clears_runtime_install_blocker_after_if_wrapped_default_smoke_and_direct_source_url():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc and is fully functional.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12c:long_build:1",
    )
    source_command = (
        "set -e\n"
        "curl -fL https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz -o /tmp/foocc.tgz\n"
        "printf 'authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\\n'\n"
        "printf 'remote_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "tar -xzf /tmp/foocc.tgz -C /tmp"
    )
    final_command = (
        "set -e\n"
        "printf 'Source/provenance\\n'\n"
        "cat /tmp/foocc-source-provenance.txt\n"
        "cd /tmp/FooCC\n"
        "test -x /tmp/FooCC/foocc\n"
        "make -C runtime libfoocc.a\n"
        "make install\n"
        "cat > /tmp/foocc_smoke.c <<'EOF'\n"
        "int main(void) { return 0; }\n"
        "EOF\n"
        "if /tmp/FooCC/foocc /tmp/foocc_smoke.c -o /tmp/foocc_smoke > /tmp/foocc-build.log 2>&1; then\n"
        "  cat /tmp/foocc-build.log\n"
        "else\n"
        "  cat /tmp/foocc-build.log\n"
        "  exit 1\n"
        "fi\n"
        "/tmp/foocc_smoke\n"
        "printf 'smoke_exit=0\\n'"
    )
    final_stdout = (
        "Source/provenance\n"
        "url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\n"
        "sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "FooCC version 1.2.3\n"
        "AR libfoocc.a\n"
        "install -m 0644 libfoocc.a /usr/local/lib/foocc\n"
        "smoke_exit=0\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                "make install",
                stdout="install: cannot stat 'libfoocc.a': No such file or directory\n",
                exit_code=2,
            ),
            _command_call(2, "make depend", stdout="Error: cannot determine dependency library\n", exit_code=2),
            _command_call(
                3,
                source_command,
                stdout=(
                    "authority_archive_url=https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz\n"
                    "remote_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
                ),
            ),
            _command_call(4, final_command, stdout=final_stdout),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "runtime_install_before_runtime_library_build",
                "source_tool_call_id": 1,
                "excerpt": "install: cannot stat 'libfoocc.a': No such file or directory",
            }
        ],
    )

    assert attempts[-1]["stage"] == "default_smoke"
    assert {"id": "source_authority", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "dependency_generation", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["current_failure"] is None
    assert state["strategy_blockers"] == []
    assert [item["code"] for item in state["cleared_strategy_blockers"]] == [
        "runtime_install_before_runtime_library_build",
    ]
    assert state["status"] == "complete"


def test_reducer_clears_non_source_strategy_blockers_after_target_and_runtime_proof():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc and is fully functional.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12d:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "cd /tmp/FooCC\n"
        "make -j4 foocc\n"
        "test -f /tmp/FooCC/foocc\n"
        "test -x /tmp/FooCC/foocc\n"
        "/tmp/FooCC/foocc --version\n"
        "printf 'int main(void){return 0;}\\n' > /tmp/foocc-proof.c\n"
        "/tmp/FooCC/foocc /tmp/foocc-proof.c -o /tmp/foocc-proof\n"
        "test -x /tmp/foocc-proof\n"
        "/tmp/foocc-proof\n"
        "printf 'required_artifact_final_status=verified path=/tmp/FooCC/foocc kind=executable\\n'"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(
                1,
                command,
                stdout=(
                    "FooCC version 1.0\n"
                    "required_artifact_final_status=verified path=/tmp/FooCC/foocc kind=executable\n"
                ),
            )
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "package_source_or_name_mismatch",
                "source_tool_call_id": 3,
                "excerpt": "E: Unable to locate package old-streams",
            },
            {
                "code": "compatibility_override_probe_missing",
                "source_tool_call_id": 4,
                "excerpt": "unsupported host branch",
            },
        ],
    )

    assert attempts[-1]["stage"] == "default_smoke"
    assert {"id": "source_authority", "required": True, "status": "unknown"} in state["stages"]
    assert {"id": "target_built", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert state["current_failure"] is None
    assert state["strategy_blockers"] == []
    assert [item["code"] for item in state["cleared_strategy_blockers"]] == [
        "package_source_or_name_mismatch",
        "compatibility_override_probe_missing",
    ]
    assert state["status"] == "ready_for_final_proof"


def test_reducer_surfaces_later_diagnostic_failure_instead_of_stale_non_source_blocker():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc and is fully functional.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12e:long_build:1",
    )
    proof_command = (
        "set -euo pipefail\n"
        "test -x /tmp/FooCC/foocc\n"
        "/tmp/FooCC/foocc --version\n"
        "printf 'int main(void){return 0;}\\n' > /tmp/foocc-proof.c\n"
        "/tmp/FooCC/foocc /tmp/foocc-proof.c -o /tmp/foocc-proof\n"
        "test -x /tmp/foocc-proof\n"
        "/tmp/foocc-proof"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, proof_command, stdout="FooCC version 1.0\n"),
            _command_call(
                2,
                "cc /tmp/other-proof.c -lmissing-runtime",
                stderr="ld: cannot find -lmissing-runtime\n",
                exit_code=1,
            ),
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "package_source_or_name_mismatch",
                "source_tool_call_id": 3,
                "excerpt": "E: Unable to locate package old-streams",
            }
        ],
    )

    assert attempts[-1]["diagnostics"][0]["failure_class"] == "runtime_link_failed"
    assert state["current_failure"]["failure_class"] == "runtime_link_failed"
    assert state["strategy_blockers"] == []
    assert [item["code"] for item in state["cleared_strategy_blockers"]] == [
        "package_source_or_name_mismatch",
    ]
    assert state["status"] == "blocked"


def test_reducer_preserves_source_archive_grounding_blocker_after_target_and_runtime_proof():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc and is fully functional.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12f:long_build:1",
    )
    command = (
        "set -euo pipefail\n"
        "test -x /tmp/FooCC/foocc\n"
        "/tmp/FooCC/foocc --version\n"
        "printf 'int main(void){return 0;}\\n' > /tmp/foocc-proof.c\n"
        "/tmp/FooCC/foocc /tmp/foocc-proof.c -o /tmp/foocc-proof\n"
        "test -x /tmp/foocc-proof\n"
        "/tmp/foocc-proof"
    )
    evidence = synthesize_command_evidence_from_tool_calls([_command_call(1, command, stdout="FooCC version 1.0\n")])
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "source_archive_version_grounding_too_strict",
                "source_tool_call_id": 3,
                "excerpt": "source archive version could not be grounded",
            }
        ],
    )

    assert {"id": "target_built", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "default_smoke", "required": True, "status": "satisfied"} in state["stages"]
    assert {"id": "source_authority", "required": True, "status": "blocked"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "source_authority_overconstrained"
    assert state["current_failure"]["legacy_code"] == "source_archive_version_grounding_too_strict"
    assert [item["code"] for item in state["strategy_blockers"]] == [
        "source_archive_version_grounding_too_strict",
    ]
    assert state["status"] == "blocked"


def test_reducer_does_not_clear_source_blocker_with_local_identity_only_output():
    contract = build_long_build_contract(
        "Under /tmp/FooCC, build the FooCC compiler from source. "
        "Ensure that FooCC can be invoked through /tmp/FooCC/foocc.",
        ["/tmp/FooCC/foocc"],
        contract_id="work_session:12c:long_build:1",
    )
    command = (
        "set -e\n"
        "curl -fL https://github.com/example/FooCC/archive/refs/tags/v1.2.3.tar.gz -o /tmp/foocc.tgz\n"
        "printf 'local_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\\n'\n"
        "printf 'archive_top=FooCC-1.2.3\\n'\n"
        "test -x /tmp/FooCC/foocc && /tmp/FooCC/foocc --version\n"
        "cat > /tmp/foocc_smoke.c <<'EOF'\nint main(void) { return 0; }\nEOF\n"
        "/tmp/FooCC/foocc -o /tmp/foocc_smoke /tmp/foocc_smoke.c\n"
        "/tmp/foocc_smoke"
    )
    stdout = (
        "local_sha256=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "archive_top=FooCC-1.2.3\n"
        "FooCC version 1.2.3\n"
    )
    evidence = synthesize_command_evidence_from_tool_calls(
        [
            _command_call(1, "curl -L -o /tmp/foocc.tgz https://github.com/example/FooCC/archive/v1.2.3.tar.gz"),
            {
                **_command_call(2, command, stdout=stdout),
                "parameters": {"command": command, "cwd": "/tmp/FooCC"},
                "result": {"command": command, "cwd": "/tmp/FooCC", "exit_code": 0, "stdout": stdout},
            },
        ]
    )
    attempts = build_attempts_from_command_evidence(evidence, contract)
    state = reduce_long_build_state(
        contract,
        attempts,
        evidence,
        strategy_blockers=[
            {
                "code": "external_dependency_source_provenance_unverified",
                "source_tool_call_id": 1,
                "excerpt": "generated VCS archive",
            }
        ],
    )

    assert not any(item.get("signal") == "source_authority" for item in attempts[-1]["diagnostics"])
    assert {"id": "source_authority", "required": True, "status": "blocked"} in state["stages"]
    assert state["current_failure"]["failure_class"] == "source_authority_unverified"
    assert [item["code"] for item in state["strategy_blockers"]] == [
        "external_dependency_source_provenance_unverified"
    ]
    assert state["status"] == "blocked"
