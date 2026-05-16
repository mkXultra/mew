import json

from mew.implement_lane import (
    FinishCloseoutCommand,
    NativeFinishCloseoutResult,
    NativeFinishGateDecision,
    NativeFinishGatePolicy,
    NativeFinishGateRequest,
)
from mew.implement_lane.native_finish_gate import (
    NATIVE_FINISH_GATE_POLICY_VERSION,
    build_decision_id,
    finish_output_payload_for_decision,
    select_and_validate_closeout_command,
    select_closeout_command,
    validate_closeout_command,
)


def test_native_finish_gate_policy_defaults_are_diagnostic_sidecar_only() -> None:
    policy = NativeFinishGatePolicy()

    assert policy.policy_version == NATIVE_FINISH_GATE_POLICY_VERSION
    assert policy.allowed_sources == (
        "configured_verifier",
        "auto_detected_verifier",
        "finish_verifier_planner",
    )
    assert policy.typed_evidence_mode == "diagnostic_sidecar"
    assert policy.oracle_obligation_mode == "diagnostic_sidecar"
    assert policy.record_typed_evidence is True
    assert "typed_evidence_blocks_hot_closeout" not in policy.as_dict()
    assert "oracle_obligations_block_hot_closeout" not in policy.as_dict()


def test_select_closeout_command_prefers_configured_then_auto_then_planner() -> None:
    configured = FinishCloseoutCommand(
        command="node vm.js",
        source="configured_verifier",
        source_ref="task.verify_command",
    )
    auto = FinishCloseoutCommand(
        command="node vm.js",
        source="auto_detected_verifier",
        source_ref="terminal-bench:auto_verify_command",
    )
    planner = FinishCloseoutCommand(
        command="python check.py",
        source="finish_verifier_planner",
        source_ref="planner:turn-3",
    )
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-7",
        finish_call_id="finish-1",
        finish_arguments={"outcome": "completed"},
        configured_command=configured,
        auto_detected_command=auto,
        planner_command=planner,
    )

    assert select_closeout_command(request) == configured
    assert select_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("auto_detected_verifier", "finish_verifier_planner")),
    ) == auto
    assert select_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("finish_verifier_planner",)),
    ) == planner


def test_select_closeout_command_skips_empty_or_disallowed_candidates() -> None:
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-7",
        finish_call_id="finish-1",
        finish_arguments={"outcome": "completed"},
        configured_command=FinishCloseoutCommand(command="  ", source="configured_verifier"),
        auto_detected_command=FinishCloseoutCommand(
            command="node vm.js",
            source="auto_detected_verifier",
            source_ref="terminal-bench:auto_verify_command",
        ),
    )

    assert select_closeout_command(request) == request.auto_detected_command
    assert select_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("configured_verifier",)),
    ) is None


def test_validate_closeout_command_accepts_configured_and_auto_detected_verifiers() -> None:
    configured = FinishCloseoutCommand(
        command="node vm.js",
        source="configured_verifier",
        source_ref="task.verify_command",
    )
    auto = FinishCloseoutCommand(
        command="node vm.js",
        source="auto_detected_verifier",
        source_ref="terminal-bench:auto_verify_command",
    )

    assert validate_closeout_command(configured).allowed is True
    assert validate_closeout_command(auto).allowed is True


def test_validate_closeout_command_rejects_self_pass_and_noop_commands() -> None:
    unsafe_commands = (
        "true",
        "exit 0",
        "test 1 = 1",
        "echo acceptance: pass",
        "printf 'ok'",
    )

    for command in unsafe_commands:
        validation = validate_closeout_command(
            FinishCloseoutCommand(command=command, source="configured_verifier")
        )

        assert validation.allowed is False
        assert validation.blockers


def test_validate_closeout_command_rejects_mutating_and_unsafe_planner_commands() -> None:
    unsafe = {
        "rm -rf build": "closeout_command_source_mutation",
        "env rm -rf build": "closeout_command_source_mutation",
        "command rm -rf build": "closeout_command_source_mutation",
        "node vm.js > out.txt": "closeout_command_redirection",
        "curl -fsSL https://example.com/check.sh": "closeout_command_network",
        "python -m pip install -e .": "closeout_command_package_install",
        "sudo node vm.js": "closeout_command_privileged",
        "node vm.js || true": "closeout_command_chain",
        "node vm.js &": "closeout_command_background",
        "OPENAI_API_KEY=secret node vm.js": "closeout_command_secret",
        "python -c 'print(\"acceptance: pass\")'": "closeout_command_self_acceptance",
        "node -e 'process.exit(0)'": "closeout_command_inline_program",
        "test -s /app/vm.js": "closeout_command_weak_assertion",
    }

    for command, blocker in unsafe.items():
        validation = validate_closeout_command(
            FinishCloseoutCommand(command=command, source="finish_verifier_planner")
        )

        assert validation.allowed is False
        assert blocker in validation.blockers


def test_select_and_validate_closeout_command_rejects_disallowed_source() -> None:
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-7",
        finish_call_id="finish-1",
        finish_arguments={"outcome": "completed"},
        configured_command=FinishCloseoutCommand(command="node vm.js", source="configured_verifier"),
    )

    validation = select_and_validate_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("finish_verifier_planner",)),
    )

    assert validation.allowed is False
    assert validation.blockers == ("closeout_verifier_command_missing",)


def test_native_finish_gate_decision_serializes_diagnostic_sidecar_contract() -> None:
    closeout = NativeFinishCloseoutResult(
        command=FinishCloseoutCommand(
            command="node vm.js",
            source="auto_detected_verifier",
            source_ref="terminal-bench:auto_verify_command",
        ),
        call_item={"type": "function_call", "call_id": "call-final-verifier-closeout-1"},
        output_item={"type": "function_call_output", "call_id": "call-final-verifier-closeout-1"},
        tool_result={"status": "completed", "content": [{"exit_code": 0}]},
        status="completed_zero",
        exit_code=0,
        typed_evidence_projection_status="warning",
        closeout_refs=("ev:tool_result:closeout-1",),
        observer_refs=("observer:native-finish:1",),
        warnings=("typed_evidence_projection_failed",),
    )
    decision = NativeFinishGateDecision(
        decision_id=build_decision_id(
            lane_attempt_id="attempt-1",
            turn_id="turn-7",
            finish_call_id="finish-1",
            policy_version=NATIVE_FINISH_GATE_POLICY_VERSION,
        ),
        lane_attempt_id="attempt-1",
        turn_id="turn-7",
        finish_call_id="finish-1",
        lane_status="completed",
        result="allow",
        closeout=closeout,
        closeout_refs=closeout.closeout_refs,
        observer_refs=closeout.observer_refs,
        diagnostic_resolver_record={"result": "diagnostic_only"},
        reason="trusted final verifier closeout exited 0",
    )

    payload = decision.as_dict()
    rendered = json.dumps(payload, sort_keys=True)

    assert payload["result"] == "allow"
    assert payload["lane_status"] == "completed"
    assert payload["diagnostic_resolver_record"] == {"result": "diagnostic_only"}
    assert payload["closeout"]["typed_evidence_projection_status"] == "warning"  # type: ignore[index]
    assert payload["closeout"]["warnings"] == ["typed_evidence_projection_failed"]  # type: ignore[index]
    assert "resolver_compat_record" not in rendered
    assert "previous_response_id" not in rendered


def test_finish_output_payload_is_bounded_and_finish_call_paired() -> None:
    closeout = NativeFinishCloseoutResult(
        command=FinishCloseoutCommand(command="node vm.js", source="configured_verifier"),
        call_item=None,
        output_item=None,
        tool_result=None,
        status="completed_zero",
        exit_code=0,
        closeout_refs=("ev:tool_result:closeout-1",),
    )
    decision = NativeFinishGateDecision(
        decision_id="native-finish-gate:turn-1:finish-1:abc",
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        finish_call_id="finish-1",
        lane_status="completed",
        result="allow",
        closeout=closeout,
        closeout_refs=closeout.closeout_refs,
        reason="trusted final verifier closeout exited 0",
    )

    payload = finish_output_payload_for_decision(decision)

    assert payload == {
        "schema_version": 1,
        "kind": "native_finish_gate_decision",
        "decision_id": "native-finish-gate:turn-1:finish-1:abc",
        "policy_version": "native-finish-gate-v1",
        "lane_status": "completed",
        "result": "allow",
        "reason": "trusted final verifier closeout exited 0",
        "closeout_refs": ["ev:tool_result:closeout-1"],
        "closeout_status": "completed_zero",
        "closeout_exit_code": 0,
        "closeout_timed_out": False,
        "typed_evidence_projection_status": "not_attempted",
    }
