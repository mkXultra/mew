import json
from types import SimpleNamespace

import pytest

from mew.implement_lane import (
    FinishCloseoutCommand,
    NativeFinishCloseoutResult,
    NativeFinishGateDecision,
    NativeFinishGatePolicy,
    NativeFinishGateRequest,
)
from mew.implement_lane.native_tool_harness import (
    _NativeFinishVerifierPlan,
    _native_final_verifier_closeout_call,
)
from mew.implement_lane.native_finish_gate import (
    NATIVE_FINISH_GATE_POLICY_VERSION,
    build_decision_id,
    decide_native_finish_from_closeout,
    finish_output_payload_for_decision,
    select_and_validate_closeout_command,
    select_closeout_command,
    validate_closeout_command,
    write_native_finish_gate_artifacts,
)
from mew.implement_lane.types import ImplementLaneInput
from mew.implement_lane.exec_runtime import (
    _drop_uncheckable_expected_artifacts,
    _normalize_runtime_contract,
)
from mew.implement_lane.execution_evidence import normalize_execution_contract


def test_native_finish_gate_policy_defaults_are_diagnostic_sidecar_only() -> None:
    policy = NativeFinishGatePolicy()

    assert policy.policy_version == NATIVE_FINISH_GATE_POLICY_VERSION
    assert policy.allowed_sources == (
        "configured_verifier",
        "finish_verifier_planner",
        "auto_detected_verifier",
    )
    assert policy.typed_evidence_mode == "diagnostic_sidecar"
    assert policy.oracle_obligation_mode == "diagnostic_sidecar"
    assert policy.record_typed_evidence is True
    assert "typed_evidence_blocks_hot_closeout" not in policy.as_dict()
    assert "oracle_obligations_block_hot_closeout" not in policy.as_dict()


def test_select_closeout_command_prefers_configured_then_planner_then_auto() -> None:
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
    ) == planner
    assert select_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("finish_verifier_planner",)),
    ) == planner
    assert select_closeout_command(
        request,
        NativeFinishGatePolicy(allowed_sources=("auto_detected_verifier",)),
    ) == auto


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
        "pytest\ntrue": "closeout_command_multiline",
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


def test_validate_closeout_command_allows_planner_read_only_inline_python() -> None:
    command = (
        "python3 -B -c \"import json, subprocess; "
        "assert json.loads('[1]') == [1]; "
        "assert subprocess.run(['git', 'status', '--short']).returncode == 0\""
    )

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is True


def test_validate_closeout_command_allows_planner_local_import_with_dash_b() -> None:
    command = (
        "python3 -B -c \"import json, subprocess, algo; "
        "assert subprocess.check_output(['git', 'status', '--porcelain'], text=True) == ''; "
        "data=json.load(open('/app/examples.json')); "
        "assert callable(algo.map); "
        "assert all(algo.map(c['input']) == c['output'] for c in data)\""
    )

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is True


def test_validate_closeout_command_allows_planner_local_import_without_dash_b() -> None:
    command = "python3 -c \"import algo; assert callable(algo.map)\""

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is True


def test_validate_closeout_command_allows_planner_quoted_multiline_python() -> None:
    command = "python3 -B -c 'import json\nassert json.loads(\"[1]\") == [1]\n'"

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is True


def test_validate_closeout_command_rejects_unquoted_multiline_command() -> None:
    command = "python3 -B -c 'assert True'\nrm -rf build"

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is False
    assert "closeout_command_multiline" in validation.blockers


def test_validate_closeout_command_rejects_planner_inline_python_writes() -> None:
    command = "python3 -B -c \"import os; os.remove('/tmp/marker')\""

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is False
    assert "closeout_command_inline_program" in validation.blockers


def test_validate_closeout_command_rejects_planner_inline_python_mutating_subprocess() -> None:
    command = "python3 -B -c \"import subprocess; subprocess.run(['git', 'commit', '-m', 'done'])\""

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is False
    assert "closeout_command_inline_program" in validation.blockers


@pytest.mark.parametrize(
    "command",
    (
        "python3 -B -c \"import os as o; o.remove('/tmp/marker')\"",
        "python3 -B -c \"from os import remove as r; r('/tmp/marker')\"",
        "python3 -B -c \"import pathlib; p = pathlib.Path('/tmp/marker'); p.write_text('x')\"",
        "python3 -B -c \"import importlib; importlib.import_module('os').remove('/tmp/marker')\"",
        "python3 -B -c \"import subprocess as sp; sp.run(['git', 'commit', '-m', 'done'])\"",
        "python3 -B -c \"import os; r = os.remove; r('/tmp/marker')\"",
        "python3 -B -c \"import os; getattr(os, 'remove')('/tmp/marker')\"",
        "python3 -B -c \"from builtins import getattr as g; import os; g(os, 'remove')('/tmp/marker')\"",
        "python3 -B -c \"import os; e = __builtins__.exec; e('os.remove(\\'/tmp/marker\\')')\"",
        "python3 -B -c \"import os; g = __builtins__.getattr; g(os, 'remove')('/tmp/marker')\"",
        "python3 -B -c \"import sys; sys.path.insert(0, '/tmp'); import algo\"",
        "python3 -B -c \"import sys; sys.path.append('/tmp'); import algo\"",
        "python3 -B -c \"import pathlib; p = pathlib.Path('/tmp/marker'); w = p.write_text; w('x')\"",
        "python3 -B -c \"import pathlib; pathlib.Path('/tmp/marker').open('w')\"",
        "python3 -B -c \"import pathlib; p = pathlib.Path('/tmp/marker'); p.open('w')\"",
        "python3 -B -c \"m = 'w'; open('/tmp/marker', m)\"",
        "python3 -B -c \"import pathlib; m = 'w'; pathlib.Path('/tmp/marker').open(m)\"",
        "python3 -B -c \"import subprocess; cmd = ['git', 'commit', '-m', 'done']; subprocess.run(cmd)\"",
        "python3 -B -c \"import subprocess; subprocess.run(args=['git', 'commit', '-m', 'done'])\"",
        "python3 -B -c \"import subprocess; subprocess.run(['curl', 'https://example.com'])\"",
        "python3 -B -c \"import subprocess; subprocess.run(['cu' + 'rl', 'https://example.com'])\"",
        "python3 -B -c \"import subprocess; subprocess.run(['git'] + ['commit', '-m', 'done'])\"",
        "python3 -B -c \"import subprocess; subprocess.run(tuple(['git', 'commit', '-m', 'done']))\"",
        "python3 -B -c \"import subprocess; subprocess.run(['sh', '-c', 'rm -rf build'])\"",
        "python3 -B -c \"f = open; f('/tmp/marker', 'w')\"",
        "python3 -B -c \"import subprocess; subprocess.run(['git', '-c', 'user.name=x', 'commit', '-m', 'done'])\"",
        "python3 -B -c \"import subprocess; subprocess.run(['git', '--git-dir', '.git', 'commit', '-m', 'done'])\"",
        "python3 -B -c \"import sys; sys.exit()\"",
        "python3 -B -c \"exit()\"",
        "python3 -O -c \"assert False\"",
        "python3 -OB -c \"assert False\"",
        "PYTHONOPTIMIZE=1 python3 -c \"assert False\"",
    ),
)
def test_validate_closeout_command_rejects_planner_inline_python_bypasses(command: str) -> None:
    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is False
    assert "closeout_command_inline_program" in validation.blockers


def test_validate_closeout_command_allows_planner_inline_python_data_words() -> None:
    command = (
        "python3 -B -c \"import json; "
        "data = json.loads('{\\\"merge\\\": 1, \\\"commit\\\": 2}'); "
        "assert data['merge'] == 1 and data['commit'] == 2\""
    )

    validation = validate_closeout_command(
        FinishCloseoutCommand(command=command, source="finish_verifier_planner")
    )

    assert validation.allowed is True


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


def test_native_finish_closeout_exit_zero_allows_despite_projection_warnings() -> None:
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        finish_call_id="finish-1",
        finish_arguments={"outcome": "completed", "summary": "done"},
    )
    closeout = NativeFinishCloseoutResult(
        command=None,
        call_item=None,
        output_item=None,
        tool_result=None,
        status="completed_zero",
        exit_code=0,
        typed_evidence_projection_status="warning",
        evidence_refs=("ev:typed:diagnostic",),
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
        warnings=("invalid_typed_evidence_ref", "oracle:task_contract:compiled:verifier_pass"),
    )

    decision = decide_native_finish_from_closeout(request, closeout)

    assert decision.result == "allow"
    assert decision.lane_status == "completed"
    assert decision.blockers == ()
    assert decision.missing_obligations == ()
    assert decision.closeout_refs == ("implement-v2-exec://attempt/final-verifier/terminal",)


def test_native_finish_gate_can_key_decision_by_done_candidate_id() -> None:
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        done_candidate_id="done-candidate:turn-9:abc123",
    )
    closeout = NativeFinishCloseoutResult(
        command=None,
        call_item=None,
        output_item=None,
        tool_result=None,
        status="completed_zero",
        exit_code=0,
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
    )

    decision = decide_native_finish_from_closeout(request, closeout)
    payload = decision.as_dict()

    assert decision.result == "allow"
    assert decision.done_candidate_id == "done-candidate:turn-9:abc123"
    assert decision.finish_call_id == ""
    assert "done-candidate:turn-9:abc123" in decision.decision_id
    assert payload["done_candidate_id"] == "done-candidate:turn-9:abc123"
    assert "finish_call_id" not in payload


def test_done_candidate_decision_id_ignores_legacy_finish_call_id() -> None:
    first = build_decision_id(
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        policy_version=NATIVE_FINISH_GATE_POLICY_VERSION,
        done_candidate_id="done-candidate:turn-9:abc123",
        finish_call_id="legacy-finish-a",
    )
    second = build_decision_id(
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        policy_version=NATIVE_FINISH_GATE_POLICY_VERSION,
        done_candidate_id="done-candidate:turn-9:abc123",
        finish_call_id="legacy-finish-b",
    )

    assert first == second


def test_legacy_finish_call_decision_id_stays_stable_after_done_candidate_migration() -> None:
    legacy = build_decision_id(
        lane_attempt_id="attempt-1",
        turn_id="turn-7",
        finish_call_id="finish-1",
        policy_version=NATIVE_FINISH_GATE_POLICY_VERSION,
    )

    assert legacy == "native-finish-gate:turn-7:finish-1:fb5eb9acd0989d6d"


def test_native_finish_gate_manifest_summarizes_done_candidate_keyed_rows(tmp_path) -> None:
    manifest_path = tmp_path / "proof-manifest.json"
    manifest_path.write_text('{"metrics":{"existing":true}}\n', encoding="utf-8")
    closeout = NativeFinishCloseoutResult(
        command=None,
        call_item=None,
        output_item=None,
        tool_result=None,
        status="completed_zero",
        exit_code=0,
    )
    decision = NativeFinishGateDecision(
        decision_id=build_decision_id(
            lane_attempt_id="attempt-1",
            turn_id="turn-9",
            policy_version=NATIVE_FINISH_GATE_POLICY_VERSION,
            done_candidate_id="done-candidate:turn-9:abc123",
        ),
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        finish_call_id="",
        done_candidate_id="done-candidate:turn-9:abc123",
        lane_status="completed",
        result="allow",
        closeout=closeout,
    )

    paths = write_native_finish_gate_artifacts(
        tmp_path,
        (decision,),
        proof_manifest_path=manifest_path,
    )

    assert paths["native_finish_gate_decisions"] == tmp_path / "native_finish_gate_decisions.jsonl"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary = manifest["metrics"]["native_finish_gate_decisions"]
    assert summary["done_candidate_count"] == 1
    assert summary["legacy_finish_call_count"] == 0
    assert manifest["metrics"]["existing"] is True


def test_native_finish_closeout_exit_zero_blocks_unexpected_source_mutation() -> None:
    request = NativeFinishGateRequest(
        lane_attempt_id="attempt-1",
        turn_id="turn-9",
        finish_call_id="finish-1",
        finish_arguments={"outcome": "completed", "summary": "done"},
    )
    closeout = NativeFinishCloseoutResult(
        command=None,
        call_item=None,
        output_item=None,
        tool_result=None,
        status="completed_zero",
        exit_code=0,
        observed_unexpected_source_mutation=True,
        closeout_refs=("implement-v2-exec://attempt/final-verifier/terminal",),
    )

    decision = decide_native_finish_from_closeout(request, closeout)

    assert decision.result == "block"
    assert decision.lane_status == "blocked_continue"
    assert "closeout_unexpected_source_mutation" in decision.blockers


def test_finish_verifier_runtime_contract_does_not_import_task_artifact_obligations() -> None:
    contract = _normalize_runtime_contract(
        {
            "id": "contract:final-verifier",
            "role": "runtime",
            "stage": "final-verifier",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "expected_exit": 0,
        },
        task_contract={
            "expected_artifacts": [
                {
                    "id": "rendered_frames",
                    "kind": "file",
                    "required": True,
                }
            ]
        },
        frontier_state={
            "final_artifact": {
                "id": "model_declared_artifact",
                "kind": "file",
                "path": "/tmp/model-output",
            }
        },
        fallback_id="contract:fallback",
        command_intent="finish_verifier",
        declared_tool_name="run_command",
    )

    assert contract.id == "contract:final-verifier"
    assert contract.proof_role == "verifier"
    assert contract.acceptance_kind == "external_verifier"
    assert contract.expected_artifacts == ()


def test_native_final_verifier_closeout_call_uses_minimal_finish_verifier_intent(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane="implement_v2",
        task_contract={
            "expected_artifacts": [
                {
                    "id": "rendered_frames",
                    "kind": "file",
                    "required": True,
                }
            ]
        },
        lane_config={"mode": "full", "allow_verify": True, "allow_shell": True},
    )
    call = _native_final_verifier_closeout_call(
        lane_input,
        lane_attempt_id="attempt-1",
        provider=SimpleNamespace(provider="fake-native", model="fake-model"),
        turn_index=3,
        lane_config=lane_input.lane_config,
        plan=_NativeFinishVerifierPlan(command="node vm.js", source="configured"),
        timeout_seconds=30.0,
        pending_mutation={"provider_call_id": "call-write-1", "path": "vm.js"},
    )

    arguments = json.loads(call.arguments_json_text)
    contract = _normalize_runtime_contract(
        arguments["execution_contract"],
        task_contract=lane_input.task_contract,
        frontier_state={
            "final_artifact": {
                "id": "frontier_artifact",
                "kind": "file",
                "path": str(tmp_path / "frontier.out"),
            }
        },
        fallback_id="contract:fallback",
        command_intent=arguments["command_intent"],
        declared_tool_name=call.tool_name,
    )

    assert arguments["command_intent"] == "finish_verifier"
    assert contract.stage == "verification"
    assert contract.expected_artifacts == ()


def test_pathless_expected_artifact_is_unchecked_before_artifact_checks(tmp_path) -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:bad-artifact",
            "role": "runtime",
            "stage": "final-verifier",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "expected_artifacts": [
                {
                    "id": "rendered_frames",
                    "kind": "file",
                    "required": True,
                }
            ],
        },
        task_contract=None,
        frontier_state=None,
    )

    checked, unchecked = _drop_uncheckable_expected_artifacts(
        contract,
        workspace=tmp_path,
        allowed_roots=(tmp_path,),
    )

    assert checked.expected_artifacts == ()
    assert unchecked == (
        {
            "id": "rendered_frames",
            "path": "",
            "kind": "file",
            "source": "model_declared",
            "reason": "artifact rendered_frames has no path target",
            "required_next_action": (
                "The command may still run, but mew cannot perform internal artifact checks for this path. "
                "Use a shell-level verifier assertion or write/check an artifact inside the allowed roots."
            ),
        },
    )
