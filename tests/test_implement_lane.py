import hashlib
import json
import shlex
import subprocess
import sys
import time

import mew.implement_lane.read_runtime as read_runtime
from mew.errors import ModelBackendError
from mew.implement_lane import (
    FakeProviderAdapter,
    FakeProviderToolCall,
    ImplementLaneInput,
    ImplementLaneProofManifest,
    ImplementLaneResult,
    ImplementLaneTranscriptEvent,
    ToolCallEnvelope,
    ToolResultEnvelope,
    build_invalid_tool_result,
    build_implement_v2_prompt_sections,
    describe_implement_v1_adapter,
    describe_implement_v2_runtime,
    evaluate_m6_24_reentry_ab_gate,
    get_implement_lane_runtime_view,
    implement_v2_prompt_section_metrics,
    list_implement_lane_runtime_views,
    list_v2_base_tool_specs,
    list_v2_tool_specs_for_mode,
    run_fake_exec_implement_v2,
    run_fake_read_only_implement_v2,
    run_fake_write_implement_v2,
    run_live_json_implement_v2,
    run_unavailable_implement_v2,
    select_implement_lane_runtime,
    validate_proof_manifest_pairing,
    validate_tool_result_pairing,
)
from mew.implement_lane.v2_runtime import (
    ModelTurnInput,
    _auto_finish_from_structured_final_verifier,
    _call_model_turn,
    _command_has_verifier_surface,
    _finish_acceptance_action,
    _finish_evidence_refs,
    _finish_gate_history,
    _first_write_probe_threshold,
    _first_write_readiness_from_trace,
    _frontier_failure_payload,
    _hard_runtime_frontier_progress_signature,
    _hard_runtime_progress_continuation_signature,
    _hard_runtime_progress_continuation_turn_limit,
    _live_json_prompt,
    _model_visible_tool_specs_for_turn,
    _prewrite_write_tools_hidden_for_turn,
    _provider_visible_tool_call_for_history,
    _provider_visible_tool_result_for_history,
    _render_prompt_history_json,
    _shell_command_may_mutate_source_tree,
    _terminal_failure_reaction_turn_limit,
    _typed_finish_evidence_refs,
    _typed_retired_legacy_blockers_for_bundle,
    _write_result_covers_source_tree_mutation,
)
from mew.work_lanes import IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE, TINY_LANE


def test_implementation_runtime_registry_keeps_v1_default_and_v2_explicit() -> None:
    runtimes = list_implement_lane_runtime_views()

    assert [runtime.lane for runtime in runtimes] == [IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE]
    assert runtimes[0].default is True
    assert runtimes[0].runtime_available is True
    assert runtimes[0].provider_native_tool_loop is False
    assert runtimes[1].default is False
    assert runtimes[1].runtime_available is True
    assert runtimes[1].runtime_id == "implement_v2_model_json_tool_loop"
    assert runtimes[1].provider_native_tool_loop is False
    assert runtimes[1].writes_allowed is True


def test_legacy_tiny_and_unknown_lanes_resolve_to_implement_v1_runtime() -> None:
    for lane in (None, "", TINY_LANE, "unknown-lane"):
        assert get_implement_lane_runtime_view(lane).lane == IMPLEMENT_V1_LANE


def test_implement_v2_typed_retirement_is_family_specific() -> None:
    blockers = _typed_retired_legacy_blockers_for_bundle(
        {
            "obligations": [
                {"kind": "artifact_exists"},
                {"kind": "visual_similarity"},
            ]
        },
        task_description="Run the VM and compare the rendered frame to the reference image.",
    )

    assert "runtime_final_verifier_artifact_evidence" in blockers
    assert "runtime_visual_artifact_quality_evidence" in blockers
    assert "acceptance_constraints_unchecked" not in blockers


def test_implement_v2_typed_retirement_does_not_treat_dimensions_as_visual_quality() -> None:
    blockers = _typed_retired_legacy_blockers_for_bundle(
        {
            "obligations": [
                {"kind": "artifact_exists"},
                {"kind": "visual_dimension"},
            ]
        },
        task_description="Run the VM and compare the rendered frame to the reference image.",
    )

    assert "runtime_final_verifier_artifact_evidence" not in blockers
    assert "runtime_visual_artifact_quality_evidence" not in blockers


def test_explicit_implement_v2_selection_returns_v2_runtime() -> None:
    selected = select_implement_lane_runtime(requested_lane=IMPLEMENT_V2_LANE, allow_v2=True)

    assert selected.lane == IMPLEMENT_V2_LANE
    assert selected.runtime_available is True


def test_explicit_implement_v2_selection_does_not_silently_route_to_v1() -> None:
    selected = select_implement_lane_runtime(requested_lane=IMPLEMENT_V2_LANE)

    assert selected.lane == IMPLEMENT_V2_LANE
    assert selected.fallback_lane == IMPLEMENT_V1_LANE


def test_implementation_lane_contract_shapes_are_serializable() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V1_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"acceptance": "run tests"},
    )
    event = ImplementLaneTranscriptEvent(
        kind="tool_call",
        lane=IMPLEMENT_V1_LANE,
        turn_id="turn-1",
        event_id="event-1",
        payload={"tool": "read_file"},
    )
    result = ImplementLaneResult(
        status="needs_review",
        lane=IMPLEMENT_V1_LANE,
        proof_artifacts=("proof.json",),
        transcript=(event,),
    )

    assert lane_input.as_dict()["task_contract"] == {"acceptance": "run tests"}
    assert result.as_dict()["transcript"][0]["payload"] == {"tool": "read_file"}


def test_implement_v1_adapter_has_distinct_namespace_without_running_legacy_loop() -> None:
    descriptor = describe_implement_v1_adapter(work_session_id="ws 1", task_id="task/1")

    assert descriptor.lane == IMPLEMENT_V1_LANE
    assert descriptor.legacy_lane == TINY_LANE
    assert descriptor.runtime_id == "implement_v1_json_think_act"
    assert descriptor.artifact_namespace == "implement-lane/implement_v1/ws-1/task-1"


def test_implement_v2_descriptor_exposes_live_runtime_and_tools() -> None:
    description = describe_implement_v2_runtime(work_session_id="ws-1", task_id="task-1")
    result = run_unavailable_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace="/tmp/work",
            lane=IMPLEMENT_V2_LANE,
        )
    )

    assert description["lane"] == IMPLEMENT_V2_LANE
    assert description["runtime_available"] is True
    assert description["provider_native_tool_loop"] is False
    assert description["artifact_namespace"] == "implement-lane/implement_v2/ws-1/task-1"
    assert {tool["name"] for tool in description["tool_specs"]} == {
        "inspect_dir",
        "read_file",
        "search_text",
        "glob",
        "git_status",
        "git_diff",
        "run_command",
        "run_tests",
        "poll_command",
        "cancel_command",
        "read_command_output",
        "write_file",
        "edit_file",
        "apply_patch",
        "finish",
    }
    assert result.status == "unavailable"
    assert result.next_reentry_hint["fallback_lane"] == IMPLEMENT_V1_LANE
    assert result.next_reentry_hint["requires_separate_lane_attempt"] is True
    assert "fallback_lane" not in result.updated_lane_state


def test_implement_v2_live_json_runtime_can_edit_verify_and_finish(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    outputs = [
        {
            "summary": "inspect file",
            "tool_calls": [
                {"id": "read-1", "name": "read_file", "arguments": {"path": "sample.txt"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "apply exact edit",
            "tool_calls": [
                {
                    "id": "edit-1",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "observe a failing verifier before recovery",
            "tool_calls": [
                {
                    "id": "verify-bad-1",
                    "name": "run_command",
                    "arguments": {"command": "false", "cwd": ".", "use_shell": True, "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "verify behavior",
            "tool_calls": [
                {
                    "id": "verify-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "test \"$(cat sample.txt)\" = after",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "file edited and verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=4,
    )

    assert result.status == "completed"
    assert result.metrics["provider"] == "model_json"
    assert result.metrics["tool_calls"] == 4
    assert result.metrics["write_evidence_count"] == 1
    assert result.metrics["terminal_evidence_count"] == 1
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_blocks_unaccounted_run_command_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "completed", "summary": "source mutated"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    side_effect_kinds = {effect["kind"] for effect in tool_result["side_effects"]}

    assert result.status == "blocked"
    assert "source_tree_mutation" in side_effect_kinds
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_source_tree_mutation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_verifier_accounts_for_run_command_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "verify mutated source",
            "tool_calls": [
                {
                    "id": "verify-source",
                    "name": "run_command",
                    "arguments": {
                        "command": "test \"$(cat sample.txt)\" = after",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "execution_contract": {
                            "role": "verify",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "source mutated and verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    blocker_codes = {
        str(blocker.get("code") or "")
        for blocker in result.metrics["finish_gate_decision"].get("blockers", [])
        if isinstance(blocker, dict)
    }
    assert result.status == "blocked"
    assert "unaccounted_source_tree_mutation" not in blocker_codes
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_unrelated_write_does_not_account_for_shell_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write unrelated file",
            "tool_calls": [
                {
                    "id": "write-other",
                    "name": "write_file",
                    "arguments": {"path": "other.txt", "content": "ok\n"},
                },
            ],
            "finish": {"outcome": "completed", "summary": "unrelated write done"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_source_tree_mutation"
    assert target.read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "other.txt").read_text(encoding="utf-8") == "ok\n"


def test_implement_v2_live_json_keeps_earlier_unaccounted_shell_source_mutation(tmp_path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("before\n", encoding="utf-8")
    second.write_text("before\n", encoding="utf-8")
    mutate_first = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('first.py').write_text('after\\n', encoding='utf-8')",
        ]
    )
    mutate_second = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('second.py').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate first source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-first",
                    "name": "run_command",
                    "arguments": {"command": mutate_first, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "mutate second source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-second",
                    "name": "run_command",
                    "arguments": {"command": mutate_second, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "cover only second mutation",
            "tool_calls": [
                {
                    "id": "write-second",
                    "name": "write_file",
                    "arguments": {"path": "second.py", "content": "final\n"},
                },
            ],
            "finish": {"outcome": "completed", "summary": "covered latest mutation only"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    blocker = result.metrics["finish_gate_decision"]["blockers"][0]
    assert result.status == "blocked"
    assert blocker["code"] == "unaccounted_source_tree_mutation"
    assert blocker["changed_count"] == 1
    assert any(str(path).endswith("first.py") for path in blocker["changed_paths"])
    assert first.read_text(encoding="utf-8") == "after\n"
    assert second.read_text(encoding="utf-8") == "final\n"


def test_implement_v2_write_does_not_account_for_truncated_shell_source_mutation() -> None:
    mutation = {
        "changed_count": 41,
        "changes": [{"path": f"/workspace/src/file_{index}.py", "change": "modified"} for index in range(40)],
        "truncated": True,
    }
    write_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="write-many",
        mew_tool_call_id="mew-write-many",
        tool_name="write_file",
        status="completed",
        side_effects=tuple(
            {
                "kind": "file_write",
                "path": f"/workspace/src/file_{index}.py",
                "written": True,
            }
            for index in range(40)
        ),
    )

    assert _write_result_covers_source_tree_mutation(write_result, mutation) is False


def test_implement_v2_live_json_superficial_check_text_does_not_account_for_shell_source_mutation(
    tmp_path,
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    command = (
        shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
        + "; echo test"
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-check",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "use_shell": True, "timeout": 10},
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "source mutated",
                "acceptance_evidence": ["shell-write-check confirmed sample.txt"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_source_tree_mutation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_structured_label_without_verifier_evidence_does_not_account_for_shell_source_mutation(
    tmp_path,
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "fake verifier label",
            "tool_calls": [
                {
                    "id": "fake-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "execution_contract": {
                            "role": "verify",
                            "stage": "verification",
                            "proof_role": "default_smoke",
                            "acceptance_kind": "candidate_runtime_smoke",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "fake smoke passed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_source_tree_mutation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_verifier_surface_requires_command_boundary() -> None:
    assert _command_has_verifier_surface("echo test") is False
    assert _command_has_verifier_surface("echo pytest") is False
    assert _command_has_verifier_surface("printf ok; test -f sample.txt") is True
    assert _command_has_verifier_surface("uv run pytest tests/test_sample.py") is True
    assert _command_has_verifier_surface("python -m unittest tests.test_sample") is True
    assert _command_has_verifier_surface("cargo test") is True


def test_implement_v2_live_json_accept_edits_defaults_new_write_to_create_and_apply(tmp_path) -> None:
    target = tmp_path / "generated.txt"
    outputs = [
        {
            "summary": "write the implementation artifact",
            "tool_calls": [
                {
                    "id": "write-1",
                    "name": "write_file",
                    "arguments": {"path": "generated.txt", "content": "ok\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write for inspection"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_call = manifest["tool_calls"][0]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 1
    assert target.read_text(encoding="utf-8") == "ok\n"
    assert tool_call["arguments"]["apply"] is True
    assert tool_call["arguments"]["create"] is True
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is False
    assert tool_result["content"][0]["written"] is True
    assert tool_result["content"][0]["approval_source"] == "cli_accept_edits"


def test_implement_v2_records_first_write_frontier_stall_after_missing_target_timeout(tmp_path) -> None:
    outputs = [
        {
            "summary": "probe source and inspect target before writing",
            "tool_calls": [
                {
                    "id": "call-probe-source",
                    "name": "inspect_dir",
                    "arguments": {"path": "."},
                },
                {
                    "id": "call-read-target",
                    "name": "read_file",
                    "arguments": {"path": "generated.js"},
                },
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        raise ModelBackendError("request timed out")

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    stall = frontier["first_write_frontier_stall"]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert result.metrics["model_error"]["semantic_failure_class"] == "first_write_frontier_stall"
    assert stall["failure_class"] == "first_write_frontier_stall"
    assert stall["target_path"] == "generated.js"
    assert "write_file/edit_file/apply_patch" in stall["required_next_action"]
    assert "bounded run_command writer" in stall["required_next_action"]


def test_implement_v2_clears_first_write_frontier_stall_after_successful_write(tmp_path) -> None:
    target = tmp_path / "generated.js"
    outputs = [
        {
            "summary": "write the missing first target",
            "tool_calls": [
                {
                    "id": "call-write-target",
                    "name": "write_file",
                    "arguments": {"path": "generated.js", "content": "console.log('ok')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "schema_version": 1,
                    "status": "blocked",
                    "first_write_frontier_stall": {
                        "failure_class": "first_write_frontier_stall",
                        "target_path": "generated.js",
                    },
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert result.metrics["write_evidence_count"] == 1
    assert target.exists()
    assert "first_write_frontier_stall" not in frontier


def test_implement_v2_records_active_work_todo_first_write_due_after_probe_threshold(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert result.status == "blocked"
    assert readiness["status"] == "due"
    assert readiness["first_write_due"] is True
    assert readiness["probes_seen_without_write"] == 3
    assert readiness["probe_count_before_first_write"] == 3
    assert readiness["target_paths"] == ["sample.py"]
    assert "write_file/edit_file/apply_patch" in readiness["required_next_action"]
    assert "bounded run_command writer" in readiness["required_next_action"]
    assert result.metrics["first_write_due"] is True
    assert result.metrics["first_write_probe_count"] == 3


def test_implement_v2_first_write_threshold_defaults_to_deeper_hard_runtime_probe_budget(tmp_path) -> None:
    hard_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    normal_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-2",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Patch a Python bug and run tests."},
    )
    normal_node_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-node",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Fix a runtime bug in the provided Node project so stdout logs show the correct result."
        },
    )
    self_contained_source_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-self",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Build the provided self-contained source project and write a screenshot image."},
    )
    jvm_project_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-jvm",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Fix JVM image build in provided source project."},
    )
    configured_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-3",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"first_write_probe_threshold": 4},
    )

    assert _first_write_probe_threshold(hard_runtime_input) == 8
    assert _first_write_probe_threshold(normal_input) == 3
    assert _first_write_probe_threshold(normal_node_runtime_input) == 3
    assert _first_write_probe_threshold(self_contained_source_input) == 3
    assert _first_write_probe_threshold(jvm_project_input) == 3
    assert _first_write_probe_threshold(configured_input) == 4


def test_implement_v2_blocks_hard_runtime_write_before_deep_prewrite_probe_budget(tmp_path) -> None:
    (tmp_path / "doomgeneric_mips").write_bytes(b"\x7fELFfake")
    (tmp_path / "doomgeneric").mkdir()
    (tmp_path / "doomgeneric" / "i_video.c").write_text("void I_FinishUpdate(void) {}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap hard-runtime probes",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-elf", "name": "run_command", "arguments": {"command": "file doomgeneric_mips", "cwd": "."}},
                {"id": "probe-src", "name": "search_text", "arguments": {"query": "I_FinishUpdate", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write runtime too early and verify",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                },
                {"id": "verify", "name": "run_command", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    write_result = next(item for item in tool_results if item["provider_call_id"] == "write-vm")
    verify_result = next(item for item in tool_results if item["provider_call_id"] == "verify")
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert result.status == "blocked"
    assert not (tmp_path / "vm.js").exists()
    assert write_result["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in write_result["content"][0]["reason"]
    assert verify_result["status"] == "invalid"
    assert "blocked_by_deep_runtime_prewrite_probe_gate" in verify_result["content"][0]["reason"]
    assert readiness["probe_threshold"] == 8
    assert readiness["probe_count_before_first_write"] == 3
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "write_file"
    assert "first_source_mutation_turn" not in readiness


def test_implement_v2_allows_hard_runtime_write_after_more_probes_follow_blocked_write(tmp_path) -> None:
    (tmp_path / "doomgeneric_mips").write_bytes(b"\x7fELFfake")
    (tmp_path / "doomgeneric").mkdir()
    (tmp_path / "doomgeneric" / "i_video.c").write_text("void I_FinishUpdate(void) {}\n", encoding="utf-8")
    probe_command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "print('file readelf -s objdump -d ELF little endian main symbol "
                "syscall hook api open read write opcode instruction output frame')"
            ),
        ]
    )
    outputs = [
        {
            "summary": "initial cheap probes",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-elf", "name": "run_command", "arguments": {"command": "file doomgeneric_mips", "cwd": "."}},
                {"id": "probe-src", "name": "search_text", "arguments": {"query": "I_FinishUpdate", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "premature runtime write",
            "tool_calls": [
                {
                    "id": "write-too-early",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "additional source/runtime probes after blocked write",
            "tool_calls": [
                {"id": "probe-src-read", "name": "read_file", "arguments": {"path": "doomgeneric/i_video.c"}},
                {"id": "probe-glob", "name": "glob", "arguments": {"pattern": "**/*.c"}},
                {"id": "probe-command", "name": "run_command", "arguments": {"command": probe_command, "cwd": "."}},
                {"id": "probe-runtime-search", "name": "search_text", "arguments": {"query": "doomgeneric", "path": "."}},
                {"id": "probe-tree", "name": "inspect_dir", "arguments": {"path": "doomgeneric"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write after enough probes",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=4,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    premature_write = next(item for item in tool_results if item["provider_call_id"] == "write-too-early")
    final_write = next(item for item in tool_results if item["provider_call_id"] == "write-vm")
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert premature_write["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in premature_write["content"][0]["reason"]
    assert final_write["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "module.exports = {}\n"
    assert readiness["probe_threshold"] == 8
    assert readiness["probe_count_before_first_write"] == 8
    assert readiness["prewrite_probe_missing_categories"] == ()
    assert readiness["first_write_tool"] == "write_file"
    assert readiness["first_write_provider_call_id"] == "write-vm"


def test_implement_v2_blocks_hard_runtime_prewrite_even_without_active_work_todo(tmp_path) -> None:
    outputs = [
        {
            "summary": "write strict runtime immediately",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before write"},
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    write_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert write_result["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in write_result["content"][0]["reason"]
    assert "vm.js" in write_result["content"][0]["reason"]
    assert not (tmp_path / "vm.js").exists()


def test_implement_v2_blocks_hard_runtime_shell_writer_before_probe_coverage(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "open('vm.js','w').write('module.exports = {}\\n')"])
    outputs = [
        {
            "summary": "shell writer too early with self-declared verifier contract",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "execution_contract": {"role": "runtime", "proof_role": "verifier"},
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before shell writer"},
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    shell_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert shell_result["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in shell_result["content"][0]["reason"]
    assert readiness["first_write_attempt_tool"] == "run_command"
    assert readiness["probe_count_before_first_write"] == 0
    assert len(readiness["prewrite_probe_missing_categories"]) == 5
    assert not (tmp_path / "vm.js").exists()


def test_implement_v2_shell_writer_source_like_path_detection_is_artifact_safe() -> None:
    assert _shell_command_may_mutate_source_tree("cat > package.json <<'EOF'\n{}\nEOF")
    assert _shell_command_may_mutate_source_tree("cat > Makefile <<'EOF'\nall:\n\ttrue\nEOF")
    assert _shell_command_may_mutate_source_tree("python -c \"open('vm.js','w').write('x')\"")
    assert _shell_command_may_mutate_source_tree("python -c \"from pathlib import Path; Path('vm.js').write_text('x')\"")
    assert not _shell_command_may_mutate_source_tree("python -c \"open('/tmp/frame.txt','w').write('x')\"")
    assert not _shell_command_may_mutate_source_tree(
        "python -c \"from pathlib import Path; Path('/tmp/frame.txt').write_text('x')\""
    )
    assert not _shell_command_may_mutate_source_tree(
        "python -c \"from pathlib import Path; Path('/tmp/frame.txt').write_text('vm.js')\""
    )
    assert not _shell_command_may_mutate_source_tree("printf frame > frame.txt && test -s frame.txt")


def test_implement_v2_hides_write_tools_from_hard_runtime_prompt_before_probe_budget(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )

    specs = _model_visible_tool_specs_for_turn(lane_input, prior_tool_calls=(), prior_tool_results=())
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        tool_specs=specs,
        prewrite_write_tools_hidden=_prewrite_write_tools_hidden_for_turn(
            lane_input,
            prior_tool_calls=(),
            prior_tool_results=(),
        ),
        history=(),
    )
    response_contract = prompt.split("response_contract_json:\n", 1)[1].split("\nhistory_json:", 1)[0]

    assert {spec.name for spec in specs}.isdisjoint({"write_file", "edit_file", "apply_patch"})
    assert "write tools are temporarily hidden for this turn" in response_contract
    assert "source/output contract" in response_contract
    assert "write_file" not in response_contract
    assert "edit_file" not in response_contract
    assert "apply_patch" not in response_contract
    assert "finish" not in json.loads(response_contract)["tool_calls"][0]["name"]
    assert "run_command" in response_contract


def test_implement_v2_keeps_write_tools_hidden_after_many_shallow_source_probes(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=tuple(
            {
                "provider_call_id": f"probe-{index}",
                "tool_name": "read_file",
                "arguments": {"path": f"src/{index}.c"},
            }
            for index in range(8)
        ),
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=({"path": call.arguments["path"], "content": "int ordinary_source_probe(void) { return 0; }"},),
        )
        for call in calls
    )

    specs = _model_visible_tool_specs_for_turn(
        lane_input,
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
    )
    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["vm.js"]}},
        tool_calls=tuple(calls),
        tool_results=results,
        probe_threshold=8,
        requires_deep_runtime_coverage=True,
    )

    assert {"write_file", "edit_file", "apply_patch"}.isdisjoint({spec.name for spec in specs})
    assert readiness["probe_count_before_first_write"] == 8
    assert readiness["first_write_due"] is False
    assert "runtime_binary_layout" in readiness["prewrite_probe_missing_categories"]
    assert "implementation_feature_surface" in readiness["prewrite_probe_missing_categories"]


def test_implement_v2_does_not_label_exec_mode_as_prewrite_hidden(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "exec"},
    )
    specs = _model_visible_tool_specs_for_turn(lane_input, prior_tool_calls=(), prior_tool_results=())
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        tool_specs=specs,
        prewrite_write_tools_hidden=_prewrite_write_tools_hidden_for_turn(
            lane_input,
            prior_tool_calls=(),
            prior_tool_results=(),
        ),
        history=(),
    )
    response_contract = prompt.split("response_contract_json:\n", 1)[1].split("\nhistory_json:", 1)[0]

    assert {spec.name for spec in specs}.isdisjoint({"write_file", "edit_file", "apply_patch"})
    assert "tool_surface_note" not in response_contract


def test_implement_v2_reveals_write_tools_after_hard_runtime_probe_budget(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )
    probe_calls = (
        {"provider_call_id": "probe-src", "tool_name": "read_file", "arguments": {"path": "src/runtime.c"}},
        {
            "provider_call_id": "probe-binary",
            "tool_name": "run_command",
            "arguments": {"command": "file app.bin && readelf -h app.bin", "cwd": "."},
        },
        {
            "provider_call_id": "probe-symbols",
            "tool_name": "run_command",
            "arguments": {"command": "readelf -s app.bin | grep main", "cwd": "."},
        },
        {
            "provider_call_id": "probe-host",
            "tool_name": "search_text",
            "arguments": {"query": "syscall hook api open read write", "path": "."},
        },
        {
            "provider_call_id": "probe-features",
            "tool_name": "run_command",
            "arguments": {"command": "objdump -d app.bin | grep opcode", "cwd": "."},
        },
        {"provider_call_id": "probe-output", "tool_name": "search_text", "arguments": {"query": "output frame artifact", "path": "."}},
        {"provider_call_id": "probe-api", "tool_name": "search_text", "arguments": {"query": "entry callback interface", "path": "."}},
        {"provider_call_id": "probe-glob", "tool_name": "glob", "arguments": {"pattern": "**/*.[ch]"}},
    )
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=probe_calls,
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=({"content": json.dumps(call.arguments)},),
        )
        for call in calls
    )

    specs = _model_visible_tool_specs_for_turn(
        lane_input,
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
    )

    assert {"write_file", "edit_file", "apply_patch"} <= {spec.name for spec in specs}


def test_implement_v2_allows_normal_task_write_without_deep_prewrite_probe_budget(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "write normal patch immediately",
            "tool_calls": [
                {
                    "id": "write-sample",
                    "name": "write_file",
                    "arguments": {"path": "sample.py", "content": "print('done')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write"},
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-normal",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"goal": "Patch a Python file."},
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    write_result = next(item for item in tool_results if item["provider_call_id"] == "write-sample")

    assert write_result["status"] == "completed"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('done')\n"


def test_implement_v2_counts_shell_source_mutation_as_first_write(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.py').write_text('print(\"done\")\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write a large generated file through a bounded command writer",
            "tool_calls": [
                {
                    "id": "shell-write-sample",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after first source mutation"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert target.read_text(encoding="utf-8") == 'print("done")\n'
    assert readiness["status"] == "written"
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "run_command"
    assert readiness["first_write_tool"] == "run_command"
    assert readiness["first_write_latency_turns"] == 1
    assert readiness["write_attempt_count"] == 1
    assert result.metrics["write_evidence_count"] == 1


def test_implement_v2_counts_polled_shell_source_mutation_as_first_write() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    active_work_todo = {
        "id": "todo-1",
        "status": "drafting",
        "source": {"target_paths": ["generated.js"], "plan_item": "Generate runtime"},
    }
    calls = (
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="call-start-writer",
            mew_tool_call_id="mew-call-start-writer",
            tool_name="run_command",
            arguments={"command": "python - <<'PY'\nPY", "foreground_budget_seconds": 0.01},
            turn_index=2,
        ),
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="call-poll-writer",
            mew_tool_call_id="mew-call-poll-writer",
            tool_name="poll_command",
            arguments={"command_run_id": "command-1", "wait_seconds": 1},
            turn_index=3,
        ),
    )
    results = (
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="call-start-writer",
            mew_tool_call_id="mew-call-start-writer",
            tool_name="run_command",
            status="yielded",
            side_effects=(
                {
                    "kind": "command_run",
                    "record": {"command_run_id": "command-1", "status": "running"},
                },
            ),
        ),
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="call-poll-writer",
            mew_tool_call_id="mew-call-poll-writer",
            tool_name="poll_command",
            status="completed",
            side_effects=(
                {
                    "kind": "source_tree_mutation",
                    "record": {
                        "command_run_id": "command-1",
                        "provider_call_id": "call-start-writer",
                        "changed_count": 1,
                        "changes": [{"path": "/workspace/generated.js", "change": "added"}],
                    },
                },
            ),
        ),
    )

    readiness = _first_write_readiness_from_trace(
        active_work_todo,
        tool_calls=calls,
        tool_results=results,
        probe_threshold=1,
    )

    assert readiness["status"] == "written"
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "poll_command"
    assert readiness["first_write_tool"] == "poll_command"
    assert readiness["first_write_attempt_provider_call_id"] == "call-poll-writer"
    assert readiness["first_write_provider_call_id"] == "call-poll-writer"
    assert readiness["write_attempt_count"] == 1


def test_implement_v2_does_not_emit_first_write_due_without_active_work_todo(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes without active todo",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert "active_work_todo" not in result.updated_lane_state
    assert result.metrics["first_write_due"] is False
    assert result.metrics["first_write_probe_count"] is None


def test_implement_v2_failed_write_attempt_does_not_clear_first_write_due(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt a bad edit",
            "tool_calls": [
                {
                    "id": "bad-edit",
                    "name": "edit_file",
                    "arguments": {"path": "sample.py", "old": "missing\n", "new": "print('done')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "bad edit failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert target.read_text(encoding="utf-8") == "print('hello')\n"
    assert readiness["status"] == "due"
    assert readiness["first_write_due"] is True
    assert readiness["first_write_attempt_turn"] == 2
    assert readiness["first_write_attempt_latency_turns"] == 1
    assert "first_source_mutation_turn" not in readiness
    assert "first_write_latency_turns" not in readiness


def test_implement_v2_active_work_todo_records_generated_file_write_repair(tmp_path) -> None:
    target = tmp_path / "vm.js"
    outputs = [
        {
            "summary": "write generated runtime",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){return 0}\n"},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function sys(n){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "edit failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert target.read_text(encoding="utf-8") == "function sys(){return 0}\n"
    assert repair["status"] == "blocked"
    assert repair["failure_kind"] == "stale_exact_edit"
    assert repair["path"] == "vm.js"
    assert repair["path_previously_mutated_this_attempt"] is True
    assert "stale-edit" in repair["recent_failed_write_provider_call_ids"]
    assert "write_file overwrite" in repair["required_next_action"]
    assert "do not run verifier again until a write succeeds" in repair["required_next_action"]


def test_implement_v2_write_repair_lock_blocks_repeated_target_reads_and_verifiers(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "second read and verifier are blocked until write repair",
            "tool_calls": [
                {"id": "read-again", "name": "read_file", "arguments": {"path": "vm.js"}},
                {"id": "verify-too-soon", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked by repair lock"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    read_current = next(item for item in tool_results if item["provider_call_id"] == "read-current")
    read_again = next(item for item in tool_results if item["provider_call_id"] == "read-again")
    verify_too_soon = next(item for item in tool_results if item["provider_call_id"] == "verify-too-soon")
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert read_current["status"] == "completed"
    assert read_again["status"] == "invalid"
    assert "write_repair_lock_active" in read_again["content"][0]["reason"]
    assert verify_too_soon["status"] == "invalid"
    assert "blocked_by_write_repair_lock" in verify_too_soon["content"][0]["reason"]
    assert repair["failure_kind"] == "stale_exact_edit"


def test_implement_v2_write_repair_lock_allows_same_turn_write_then_verifier(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair write and verify",
            "tool_calls": [
                {
                    "id": "overwrite-current",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){let n=0;return n}\n"},
                },
                {"id": "verify-after-write", "name": "run_tests", "arguments": {"command": "test -f vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    overwrite = next(item for item in tool_results if item["provider_call_id"] == "overwrite-current")
    verify = next(item for item in tool_results if item["provider_call_id"] == "verify-after-write")

    assert overwrite["status"] == "completed"
    assert verify["status"] == "completed"
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "function sys(){let n=0;return n}\n"


def test_implement_v2_write_repair_lock_does_not_unlock_after_dry_run_write(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "dry-run write must not unlock verifier",
            "tool_calls": [
                {
                    "id": "dry-run-write",
                    "name": "write_file",
                    "arguments": {
                        "path": "vm.js",
                        "content": "function sys(){let n=0;return n}\n",
                        "dry_run": True,
                    },
                },
                {"id": "verify-after-dry-run", "name": "run_tests", "arguments": {"command": "test -f vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after dry-run"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    dry_run_write = next(item for item in tool_results if item["provider_call_id"] == "dry-run-write")
    verify = next(item for item in tool_results if item["provider_call_id"] == "verify-after-dry-run")

    assert dry_run_write["status"] == "completed"
    assert dry_run_write["side_effects"] == []
    assert verify["status"] == "invalid"
    assert "write_repair_lock_active" in verify["content"][0]["reason"]
    assert result.updated_lane_state["active_work_todo"]["write_repair"]["failure_kind"] == "stale_exact_edit"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "function sys(){return 0}\n"


def test_implement_v2_active_work_todo_clears_write_repair_after_apply_patch_side_effect_path(tmp_path) -> None:
    target = tmp_path / "vm.js"
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        "-function sys(){return 0}\n"
        "+function sys(){let n=R[2]>>>0;return n}\n"
        "*** End Patch\n"
    )
    outputs = [
        {
            "summary": "write generated runtime",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){return 0}\n"},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function sys(n){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair from current text",
            "tool_calls": [
                {
                    "id": "apply-repair",
                    "name": "apply_patch",
                    "arguments": {"patch": patch, "apply": True},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write repair"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    assert target.read_text(encoding="utf-8") == "function sys(){let n=R[2]>>>0;return n}\n"
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]


def test_implement_v2_active_work_todo_first_write_due_is_visible_next_turn(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "make first scoped write",
            "tool_calls": [
                {"id": "write-sample", "name": "write_file", "arguments": {"path": "sample.py", "content": "print('done')\n"}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after first write"},
        },
    ]
    prompts: list[str] = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert len(prompts) == 2
    assert '"first_write_due":true' in prompts[1]
    assert "Implement V2 Active Work Todo" in prompts[1]
    assert target.read_text(encoding="utf-8") == "print('done')\n"
    assert readiness["status"] == "written"
    assert readiness["first_write_attempt_turn"] == 2
    assert readiness["first_write_latency_turns"] == 1


def test_implement_v2_does_not_classify_tmp_artifact_missing_read_as_first_write_stall(tmp_path) -> None:
    outputs = [
        {
            "summary": "probe source and inspect missing external artifact",
            "tool_calls": [
                {"id": "call-probe-source", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "call-read-artifact", "name": "read_file", "arguments": {"path": "/tmp/frame.bmp"}},
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        raise ModelBackendError("request timed out")

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.metrics["model_error"]["failure_class"] == "model_timeout"
    assert "semantic_failure_class" not in result.metrics["model_error"]
    assert "lane_hard_runtime_frontier" not in result.updated_lane_state


def test_implement_v2_live_json_accept_edits_preserves_explicit_dry_run(tmp_path) -> None:
    target = tmp_path / "preview.txt"
    outputs = [
        {
            "summary": "preview the implementation artifact",
            "tool_calls": [
                {
                    "id": "write-1",
                    "name": "write_file",
                    "arguments": {"path": "preview.txt", "content": "ok\n", "create": True, "dry_run": True},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "preview only"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_call = manifest["tool_calls"][0]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert not target.exists()
    assert "apply" not in tool_call["arguments"]
    assert tool_call["arguments"]["dry_run"] is True
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert tool_result["content"][0]["written"] is False


def test_implement_v2_live_json_blocks_same_turn_calls_after_failed_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    side_effect = tmp_path / "verifier_ran.txt"
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('verifier_ran.txt').write_text('bad', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "patch and verify in one turn",
            "tool_calls": [
                {
                    "id": "edit-1",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "missing\n", "new": "after\n"},
                },
                {
                    "id": "verify-1",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "use_shell": True, "timeout": 5},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "write failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    edit_result = manifest["tool_results"][0]
    skipped_result = manifest["tool_results"][1]

    assert result.status == "blocked"
    assert edit_result["status"] == "failed"
    assert skipped_result["status"] == "invalid"
    assert "blocked_by_prior_failed_write_in_same_turn" in skipped_result["content"][0]["reason"]
    assert not side_effect.exists()


def test_implement_v2_model_turn_boundary_preserves_rendered_prompt_and_call_args(tmp_path) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
        },
    )
    expected_prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        turn_index=1,
        max_turns=1,
        base_max_turns=1,
        terminal_failure_reaction_turn_limit=1,
        tool_contract_recovery_turn_limit=1,
        history=(),
    )

    def fake_model(*args, **kwargs):
        calls.append((args, kwargs))
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no change"}}

    result = run_live_json_implement_v2(
        lane_input,
        model_auth={"path": "auth.json"},
        base_url="https://example.invalid",
        timeout=12.5,
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (
        "codex",
        {"path": "auth.json"},
        expected_prompt,
        "gpt-5.5",
        "https://example.invalid",
        12.5,
    )
    assert kwargs == {"log_prefix": "implement_v2 live_json session=ws-1 turn=1"}
    assert result.metrics["prompt_chars_total"] == len(expected_prompt)


def test_implement_v2_model_turn_boundary_error_descriptor_omits_raw_prompt() -> None:
    prompt = "secret prompt body should not be serialized"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )

    def fake_model(*_args, **_kwargs):
        raise ModelBackendError("request timed out after 5s")

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    serialized = json.dumps(output.observation, ensure_ascii=False, sort_keys=True)
    assert output.model_error["failure_class"] == "model_timeout"
    assert output.normalized_payload == {}
    assert "secret prompt body" not in serialized
    assert output.observation["prompt"] == {"chars": len(prompt), "sha256": "sha256:prompt"}


def test_implement_v2_model_turn_retries_transient_backend_error_once() -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")
        return {
            "summary": "retry succeeded",
            "tool_calls": [],
            "finish": {"outcome": "failed", "summary": "not done"},
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 2
    assert output.model_error == {}
    assert output.normalized_payload["summary"] == "retry succeeded"
    assert output.response_shape["retry_count"] == 1
    assert output.observation["model_retry_count"] == 1


def test_implement_v2_model_turn_transient_retry_uses_remaining_timeout(monkeypatch) -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    clock_values = iter([0.0, 1.0, 1.0, 1.1])
    observed_timeouts = []

    monkeypatch.setattr("mew.implement_lane.v2_runtime.time.monotonic", lambda: next(clock_values))

    def fake_model(*args, **_kwargs):
        observed_timeouts.append(args[5])
        if len(observed_timeouts) == 1:
            raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")
        return {
            "summary": "retry succeeded",
            "tool_calls": [],
            "finish": {"outcome": "failed", "summary": "not done"},
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert observed_timeouts == [5, 4.0]
    assert output.model_error == {}
    assert output.response_shape["retry_count"] == 1
    assert output.response_shape["transient_retry_count"] == 1


def test_implement_v2_model_turn_does_not_retry_transient_after_turn_timeout_exhausted(monkeypatch) -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=1,
        log_prefix="test",
    )
    clock_values = iter([0.0, 1.2, 1.2])
    calls = []

    monkeypatch.setattr("mew.implement_lane.v2_runtime.time.monotonic", lambda: next(clock_values))

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 1
    assert output.model_error["failure_class"] == "model_backend_error"
    assert output.model_error["retry_suppressed_reason"] == "model_turn_timeout_exhausted"
    assert "retry_count" not in output.response_shape


def test_implement_v2_model_turn_does_not_retry_json_parse_error() -> None:
    prompt = "bad JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        raise ModelBackendError('failed to parse JSON plan: Extra data; raw={"summary":"bad"} trailing')

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 1
    assert output.model_error["failure_class"] == "model_json_parse_error"


def test_implement_v2_model_turn_retries_recoverable_tool_call_json_parse_error() -> None:
    prompt = "tool call JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    prompts = []

    def fake_model(_backend, _auth, model_prompt, *_args, **_kwargs):
        prompts.append(model_prompt)
        if len(prompts) == 1:
            raise ModelBackendError(
                'failed to parse JSON plan: response did not contain valid JSON object; '
                'raw={"summary":"patch","tool_calls":[{"id":"call-1","name":"apply_patch","arguments":{"patch":"*** Begin Patch'
            )
        return {
            "summary": "retry ok",
            "tool_calls": [{"id": "call-1", "name": "inspect_dir", "arguments": {"path": "."}}],
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(prompts) == 2
    assert "implement_v2_json_repair_retry" in prompts[1]
    assert output.model_error == {}
    assert output.response_shape["parse_retry_count"] == 1
    assert output.observation["model_parse_retry_count"] == 1
    assert output.prompt_chars == output.observation["prompt"]["chars"]
    assert output.normalized_payload["summary"] == "retry ok"


def test_implement_v2_model_turn_parse_retry_does_not_consume_transient_retry_budget() -> None:
    prompt = "tool call JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ModelBackendError(
                'failed to parse JSON plan: response did not contain valid JSON object; '
                'raw={"summary":"patch","tool_calls":[{"id":"call-1","name":"apply_patch","arguments":{"patch":"*** Begin Patch'
            )
        if len(calls) == 2:
            raise ModelBackendError("Codex Web API error: IncompleteRead(42 bytes read)")
        return {
            "summary": "retry ok",
            "tool_calls": [{"id": "call-1", "name": "inspect_dir", "arguments": {"path": "."}}],
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 3
    assert output.model_error == {}
    assert output.response_shape["retry_count"] == 2
    assert output.response_shape["parse_retry_count"] == 1
    assert output.response_shape["transient_retry_count"] == 1


def test_implement_v2_prompt_history_render_helper_matches_existing_json_shape() -> None:
    history = tuple({"turn": index, "summary": f"履歴 {index}"} for index in range(1, 11))

    rendered = _render_prompt_history_json(history)
    projected = json.loads(rendered)

    assert '"summary": "履歴 1"' not in rendered
    assert '"summary": "履歴 2"' not in rendered
    assert '"summary": "履歴 3"' in rendered
    assert len(projected) == 8
    assert projected[0]["turn"] == 3
    assert projected[0]["history_compacted"] is True
    assert projected[-1] == {"turn": 10, "summary": "履歴 10"}


def test_implement_v2_prompt_sections_include_active_coding_rhythm() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    section = next(item for item in sections if item.id == "implement_v2_active_coding_rhythm")

    assert section.cache_policy == "cacheable"
    assert section.stability == "static"
    assert "cheap probe -> coherent patch/edit -> verifier -> latest-failure repair" in section.content
    assert "at most one focused diagnostic/read turn" in section.content
    assert "write_file, edit_file, or apply_patch" in section.content
    assert "bounded run_command writer" in section.content
    assert "source-tree mutation" in section.content
    assert "run_command otherwise for probes, builds, runtime execution, and verification" in section.content


def test_implement_v2_prompt_sections_include_active_work_todo_readiness() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {"target_paths": ["src/app.py"], "plan_item": "Patch app"},
                "first_write_readiness": {
                    "first_write_due": True,
                    "probes_seen_without_write": 3,
                    "required_next_action": "make one scoped source mutation",
                },
                "write_repair": {
                    "failure_kind": "stale_exact_edit",
                    "path": "src/app.py",
                    "required_next_action": "repair src/app.py before verifier",
                },
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    section = next(item for item in sections if item.id == "implement_v2_active_work_todo")

    assert section.cache_policy == "dynamic"
    assert section.stability == "dynamic"
    assert "current_work" in section.content
    assert "first_write_due" in section.content
    assert "required_next_action" in section.content
    assert "stale_exact_edit" in section.content
    assert '"target_paths":' in section.content
    assert '"src/app.py"' in section.content


def test_implement_v2_live_json_prompt_omits_frontier_update_contract_without_frontier(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Fix a focused Python bug and run the relevant test."},
        lane_config={"mode": "full"},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' not in prompt
    assert "implement_v2_hard_runtime_frontier_state" not in prompt
    assert '"evidence_refs"' in prompt
    assert '"oracle_refs": [\n      "oracle:..."\n    ]' in prompt
    assert '"acceptance_evidence"' not in prompt
    assert "do not rely on prose-only acceptance_evidence claims" in prompt


def test_implement_v2_finish_gate_history_projects_compact_recovery_card() -> None:
    history = _finish_gate_history(
        turn_index=2,
        decision={
            "decision": "block_continue",
            "reason": "missing typed evidence",
            "missing_obligations": ["oracle:task:frame_similarity"],
            "invalid_evidence_refs": ["ev:bad"],
            "blockers": [
                {
                    "code": "missing_typed_evidence",
                    "reason": "need final verifier",
                    "proof_object": {"large": "do-not-project"},
                }
            ],
            "proof_object": {"large": "do-not-project"},
        },
        continuation_prompt="run one verifier-shaped comparison and finish with its evidence id",
    )
    content = history["tool_results"][0]["content"]
    card = content["finish_gate_recovery_card"]
    rendered = json.dumps(history, sort_keys=True)

    assert "finish_gate" not in content
    assert card["finish_blocked"] is True
    assert card["missing"] == ["oracle:task:frame_similarity"]
    assert card["invalid_evidence_refs"] == ["ev:bad"]
    assert card["blockers"][0]["code"] == "missing_typed_evidence"
    assert card["next_action"] == "run one verifier-shaped comparison and finish with its evidence id"
    assert "do-not-project" not in rendered


def test_implement_v2_live_json_prompt_hides_frontier_update_contract_by_default_with_frontier(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a runtime artifact repair."},
        lane_config={"mode": "full"},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        hard_runtime_frontier_state={"schema_version": 1, "status": "active"},
        turn_index=2,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' not in prompt
    assert "mew derives the latest failure from paired tool results" not in prompt


def test_implement_v2_live_json_prompt_adds_frontier_update_contract_with_debug_opt_in(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a runtime artifact repair."},
        lane_config={"mode": "full", "debug_model_frontier_update": True},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        hard_runtime_frontier_state={"schema_version": 1, "status": "active"},
        turn_index=2,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' in prompt
    assert '"use_only_when": "a hard-runtime or compatibility frontier genuinely changed"' in prompt
    assert "mew derives the latest failure from paired tool results" in prompt
    assert '"latest_failure"' not in prompt
    assert '"latest_runtime_failure"' not in prompt
    assert '"latest_build_failure"' not in prompt
    assert '"next_verifier_shaped_command"' in prompt
    assert '"source_roles"' not in prompt


def test_implement_v2_live_json_ignores_model_frontier_update_by_default(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "try model-authored frontier",
            "frontier_state_update": {
                "status": "resolved",
                "final_artifact": {"path": "fabricated.txt", "kind": "file"},
            },
            "finish": {"outcome": "blocked", "summary": "state only"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Do not trust model-authored frontier state."},
            lane_config={"mode": "full"},
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert "lane_hard_runtime_frontier" not in result.updated_lane_state
    assert result.metrics["ignored_model_frontier_state_updates"] == 1


def test_implement_v2_integration_observation_summary_is_state_safe_by_default(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    secret = "SECRET_TASK_CONTEXT_SHOULD_NOT_BE_SERIALIZED"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": secret},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]
    hot_path = manifest["metrics"]["hot_path_projection"]
    sidecar = manifest["metrics"]["resident_sidecar_state"]
    serialized = json.dumps(observation, ensure_ascii=False, sort_keys=True)

    assert observation["detail_policy"] == "summary"
    assert observation["artifact_ref"] == ""
    assert observation["summary"]["model_turns"] == 1
    assert observation["summary"]["detail_written"] is False
    assert "model_turns" not in observation
    assert secret not in serialized
    assert len(serialized.encode("utf-8")) < 8192
    assert hot_path["phase"] == "m6_24_hot_path_collapse_phase_0"
    assert hot_path["normal_full_prompt_bytes"] > 0
    assert hot_path["normal_full_prompt_bytes"] >= hot_path["normal_prompt_section_bytes"]
    assert hot_path["provider_visible_tool_result_bytes"] == 0
    assert sidecar["phase"] == "m6_24_hot_path_collapse_phase_0"
    assert sidecar["surface"] == "resident_sidecar_state"
    assert sidecar["total_bytes"] > 0
    assert sidecar["per_turn_growth_bytes"] > 0
    assert set(sidecar["families"]) == {
        "frontier_todo_recovery_cards",
        "integration_observation_detail",
        "tool_call_result",
        "transcript_history",
    }
    assert not (artifact_dir / "implement_v2" / "integration-observation.json").exists()
    assert all(not path.endswith("integration-observation.json") for path in result.proof_artifacts)


def test_implement_v2_integration_observation_detail_sidecar_is_explicit_and_ref_backed(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    secret = "SECRET_PROMPT_BODY_SHOULD_STAY_HASHED"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": secret},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "write_integration_observation_detail": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]
    sidecar_path = artifact_dir / "implement_v2" / "integration-observation.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar_serialized = json.dumps(sidecar, ensure_ascii=False, sort_keys=True)
    turn = sidecar["turns"][0]
    projection = turn["history_projection"]

    assert observation["detail_policy"] == "sidecar"
    assert observation["artifact_ref"] == "integration-observation.json"
    assert observation["summary"]["detail_written"] is True
    assert str(sidecar_path) in result.proof_artifacts
    assert sidecar["lane_attempt_id"] == manifest["lane_attempt_id"]
    assert "model_turns" not in sidecar
    assert len(sidecar["turns"]) == 1
    assert turn["prompt"]["chars"] > 0
    assert turn["prompt"]["sha256"].startswith("sha256:")
    assert projection["future_projection_mode"] == "identity"
    assert projection["future_projection_sha256"] == projection["current_projection_sha256"]
    assert projection["future_projection_chars"] == projection["current_projection_chars"]
    assert projection["diff_summary"]["changed"] is False
    assert sidecar["totals"]["projection_savings_chars"] == 0
    assert sidecar["totals"]["projection_savings_ratio"] == 0.0
    assert secret not in sidecar_serialized


def test_implement_v2_integration_observation_detail_false_string_does_not_write_sidecar(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Inspect only."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "write_integration_observation_detail": "false",
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]

    assert observation["detail_policy"] == "summary"
    assert observation["artifact_ref"] == ""
    assert observation["summary"]["detail_written"] is False
    assert not (artifact_dir / "implement_v2" / "integration-observation.json").exists()
    assert all(not path.endswith("integration-observation.json") for path in result.proof_artifacts)


def test_implement_v2_live_json_rejects_cross_turn_duplicate_before_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    outputs = [
        {
            "summary": "read first",
            "tool_calls": [
                {"id": "duplicate-call", "name": "read_file", "arguments": {"path": "sample.txt"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "try duplicate id for write",
            "tool_calls": [
                {
                    "id": "duplicate-call",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert manifest["tool_results"][1]["status"] == "invalid"
    assert manifest["tool_results"][1]["provider_call_id"] == "duplicate-call-turn2-seq1"
    assert manifest["tool_calls"][1]["provider_call_id"] == "duplicate-call-turn2-seq1"
    assert "duplicate_provider_call_id_across_turns" in manifest["tool_results"][1]["content"][0]["reason"]


def test_implement_v2_live_json_rejects_missing_provider_call_id_before_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "try write without provider call id",
            "tool_calls": [
                {
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert manifest["tool_results"][0]["status"] == "invalid"
    assert manifest["tool_results"][0]["provider_call_id"] == "missing-provider-call-id-turn1-seq1"
    assert "tool_call_missing_provider_call_id" in manifest["tool_results"][0]["content"][0]["reason"]


def test_implement_v2_live_json_rejects_same_turn_duplicate_with_same_turn_reason(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "duplicate provider ids in one turn",
            "tool_calls": [
                {"id": "dup", "name": "read_file", "arguments": {"path": "sample.txt"}},
                {
                    "id": "dup",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert [item["status"] for item in manifest["tool_results"]] == ["invalid", "invalid"]
    assert manifest["tool_calls"][1]["provider_call_id"] == "dup-turn1-seq2"
    reason = manifest["tool_results"][1]["content"][0]["reason"]
    assert "duplicate_provider_call_id:dup" in reason
    assert "duplicate_provider_call_id_across_turns" not in reason


def test_implement_v2_live_json_blocks_format_only_visual_finish(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "print('saved /tmp/frame.bmp')\n"
                            "print('verified BMP 320x200 valid header')\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "frame was generated",
                "acceptance_evidence": [
                    "turn 1 visual-smoke: saved /tmp/frame.bmp and verified BMP 320x200 valid header"
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp and check the first "
                    "rendered frame against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_visual_artifact_quality_evidence"
    assert result.updated_lane_state["finish"]["outcome"] == "blocked"


def test_implement_v2_live_json_finish_gate_can_continue_then_complete(tmp_path) -> None:
    outputs = [
        {
            "summary": "run weak visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'saved /tmp/frame.bmp\\nvalid BMP header\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "format smoke passed",
                "acceptance_evidence": ["visual-smoke produced a valid /tmp/frame.bmp"],
            },
        },
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "visual-quality",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\nsaved /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed",
                "acceptance_evidence": [
                    (
                        "visual-quality confirmed expected dimensions 640x400 "
                        "and reference similarity for /tmp/frame.bmp"
                    )
                ],
            },
        },
        {
            "summary": "clean stale runtime artifact after preserving quality proof",
            "tool_calls": [
                {
                    "id": "clean-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "rm -f /tmp/frame.bmp && printf 'removed /tmp/frame.bmp\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed and stale artifact removed",
                "acceptance_evidence": [
                    (
                        "visual-quality confirmed expected dimensions 640x400 "
                        "and reference similarity for /tmp/frame.bmp; "
                        "clean-frame removed stale /tmp/frame.bmp"
                    )
                ],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp and check the first "
                    "rendered frame against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"
    assert any(event.payload.get("type") == "deterministic_finish_gate" for event in result.transcript)


def test_implement_v2_finish_gate_uses_structured_final_verifier_without_model_evidence(tmp_path) -> None:
    outputs = [
        {
            "summary": "run fresh final verifier with a scratch transcript",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp /tmp/mew-v2-vmout.txt; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n' "
                            "| tee /tmp/mew-v2-vmout.txt; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "/tmp/mew-v2-vmout.txt", "checks": [{"exists": True}, {"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Final verifier evidence is already present from the fresh runtime run.",
                "acceptance_checks": [],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_auto_completes_when_last_turn_final_verifier_passes(tmp_path) -> None:
    outputs = [
        {
            "summary": "run fresh final verifier as the last available turn",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp /tmp/mew-v2-vmout.txt; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "dimension check passed expected dimensions 640x400\\n' "
                            "| tee /tmp/mew-v2-vmout.txt; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "final-verifier",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "/tmp/mew-v2-vmout.txt", "checks": [{"exists": True}, {"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"
    assert result.updated_lane_state["finish"]["completion_source"] == "structured_final_verifier_pass"
    assert any(
        event.kind == "finish" and event.payload["finish_arguments"]["completion_source"] == "structured_final_verifier_pass"
        for event in result.transcript
    )


def test_implement_v2_auto_complete_ignores_old_final_verifier_after_later_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "first final verifier passes",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "final-verifier",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
        },
        {
            "summary": "a later terminal check fails after the verifier",
            "tool_calls": [
                {
                    "id": "late-failure",
                    "name": "run_command",
                    "arguments": {"command": "false", "cwd": ".", "use_shell": True},
                }
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        return {
            "summary": "stop after observing the later failure",
            "finish": {"outcome": "blocked", "summary": "late terminal failure"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Build and verify the runtime artifact."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.updated_lane_state["finish"].get("completion_source") != "structured_final_verifier_pass"


def test_implement_v2_auto_complete_skips_read_command_output_after_final_verifier() -> None:
    final_verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="final-verifier",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract": {
                    "role": "runtime",
                    "stage": "final-verifier",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
                "verifier_evidence": {"verdict": "pass"},
                "artifact_evidence": [
                    {"artifact_id": "frame000000.bmp", "path": "frame000000.bmp", "status": "passed"},
                ],
            },
        ),
        evidence_refs=("ev:final-verifier",),
    )
    output_read = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="read-output",
        mew_tool_call_id="tool-2",
        tool_name="read_command_output",
        status="completed",
        content=({"stdout_tail": "bounded tail"},),
        evidence_refs=("ev:read-output",),
    )

    finish = _auto_finish_from_structured_final_verifier(
        {"outcome": "blocked", "summary": "implement_v2 reached max_turns before finish"},
        (final_verifier, output_read),
    )

    assert finish["outcome"] == "completed"
    assert finish["completion_source"] == "structured_final_verifier_pass"


def test_implement_v2_finish_gate_rejects_structured_visual_sidecar_without_quality_marker(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final verifier that only proves frame existence and boot stdout",
            "tool_calls": [
                {
                    "id": "verify-frame-exists-only",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Frame artifact exists and boot stdout was observed.",
                "acceptance_checks": [],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "runtime_visual_artifact_quality_evidence" for blocker in blockers)


def test_implement_v2_finish_gate_prefers_structured_sidecar_over_unref_model_check(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final verifier with structured artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified.",
                "acceptance_checks": [
                    {
                        "constraint": "runtime visual artifact is correct",
                        "status": "verified",
                        "evidence": "The final runtime verifier generated and checked the rendered frame.",
                    }
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_finish_gate_keeps_structured_sidecar_inside_acceptance_window(tmp_path) -> None:
    weak_checks = [
        {
            "constraint": "runtime visual artifact is correct",
            "status": "verified",
            "evidence": f"unreferenced model claim {index}",
        }
        for index in range(8)
    ]
    outputs = [
        {
            "summary": "run final verifier with structured artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified.",
                "acceptance_checks": weak_checks,
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_finish_gate_keeps_uncovered_model_check_inside_acceptance_window(tmp_path) -> None:
    weak_checks = [
        {
            "constraint": "runtime visual artifact is correct",
            "status": "verified",
            "evidence": f"unreferenced duplicate model claim {index}",
        }
        for index in range(7)
    ]
    weak_checks.append(
        {
            "constraint": "program output is hello",
            "status": "verified",
            "evidence": "The program output is hello.",
        }
    )
    outputs = [
        {
            "summary": "run final verifier with structured visual artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified, unrelated behavior claimed.",
                "acceptance_checks": weak_checks,
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames. "
                    "Also make the program output hello."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_evidence_refs_missing" for blocker in blockers)


def test_implement_v2_finish_gate_source_sidecar_does_not_cover_unrelated_model_check(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "source.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    outputs = [
        {
            "summary": "read source but do not verify behavior",
            "tool_calls": [{"id": "read-source", "name": "read_file", "arguments": {"path": "src/source.c"}}],
            "finish": {
                "outcome": "completed",
                "summary": "Claim behavior without proof.",
                "acceptance_checks": [
                    {
                        "constraint": "program output is hello",
                        "status": "verified",
                        "evidence": "The program output is hello.",
                    }
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided src/source.c, the corresponding source code. "
                    "Make the program output hello."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_evidence_refs_missing" for blocker in blockers)


def test_implement_v2_finish_gate_rejects_intermediate_structured_artifact_without_finish_evidence(tmp_path) -> None:
    outputs = [
        {
            "summary": "build an intermediate artifact",
            "tool_calls": [
                {
                    "id": "build-intermediate",
                    "name": "run_command",
                    "arguments": {
                        "command": "mkdir -p build && printf intermediate > build/intermediate.bin",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "build",
                            "stage": "build",
                            "purpose": "build",
                            "proof_role": "target_build",
                            "acceptance_kind": "progress_only",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "build/intermediate.bin", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "The intermediate artifact exists.",
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the final runtime artifact and prove it works."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_decision"]["decision"] == "block_continue"


def test_implement_v2_live_json_finish_only_turn_uses_finish_gate(tmp_path) -> None:
    outputs = [
        {
            "summary": "run weak visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'saved /tmp/frame.bmp\\nvalid BMP header\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "finish from prior evidence",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "frame was generated",
                "acceptance_evidence": ["visual-smoke produced a valid /tmp/frame.bmp"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "runtime_visual_artifact_quality_evidence"


def test_implement_v2_live_json_finish_gate_does_not_link_ambiguous_alpha_call_id(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "run",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\nremoved /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed",
                "acceptance_evidence": [
                    "run completed and confirmed expected dimensions 640x400 with reference similarity"
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_final_verifier_artifact_evidence"


def test_implement_v2_finish_evidence_refs_ignore_ambiguous_alpha_call_id() -> None:
    results = (
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="run",
            mew_tool_call_id="attempt-1:tool:1:1",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="visual-quality",
            mew_tool_call_id="attempt-1:tool:1:2",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="1",
            mew_tool_call_id="attempt-1:tool:1:3",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
    )

    assert _finish_evidence_refs("run completed with expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("turn 1 confirmed expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("visual-quality confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality: confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality. confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality-extra confirmed expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("visual-quality.extra confirmed expected dimensions 640x400", results) == []


def test_implement_v2_live_json_finish_gate_does_not_link_numeric_turn_ids(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                },
                {
                    "id": "2",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'removed /tmp/frame.bmp\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed and stale artifact removed",
                "acceptance_evidence": [
                    (
                        "turn 1 confirmed expected dimensions 640x400 and reference similarity; "
                        "turn 2 removed /tmp/frame.bmp"
                    )
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_final_verifier_artifact_evidence"


def test_implement_v2_live_json_model_parse_error_is_replayable_lane_failure(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"

    def fake_model(*_args, **_kwargs):
        raise ModelBackendError('failed to parse JSON plan: Extra data; raw={"summary":"bad"} trailing')

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "failed"
    assert result.metrics["replay_valid"] is True
    assert result.metrics["model_error"]["failure_class"] == "model_json_parse_error"
    manifest = result.updated_lane_state["proof_manifest"]
    assert manifest["tool_calls"] == []
    assert manifest["tool_results"] == []
    history = json.loads((artifact_dir / "implement_v2" / "history.json").read_text(encoding="utf-8"))
    assert history[0]["model_error"]["failure_class"] == "model_json_parse_error"


def test_implement_v2_live_json_drains_active_command_at_max_turns(tmp_path) -> None:
    command = "printf 'start\\n'; sleep 0.2; printf done > done.txt; printf 'done\\n'"

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start final command",
            "tool_calls": [
                {
                    "id": "call-final",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert "done" in tool_result["content"][0]["stdout"]
    assert (tmp_path / "done.txt").read_text(encoding="utf-8") == "done"
    assert result.metrics["command_closeout_count"] == 1
    assert result.metrics["orphaned_command_cleanup_count"] == 0
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_caps_model_timeout_by_remaining_wall_budget(tmp_path) -> None:
    observed_timeouts = []

    def fake_model(_backend, _auth, _prompt, _model, _base_url, timeout_seconds, **_kwargs):
        observed_timeouts.append(timeout_seconds)
        return {
            "summary": "block after observing timeout",
            "finish": {"outcome": "blocked", "summary": "blocked intentionally"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert observed_timeouts
    assert 0 < observed_timeouts[0] <= 5
    assert result.metrics["wall_timeout"] == {}
    assert result.metrics["wall_elapsed_seconds"] >= 0


def test_implement_v2_stops_before_next_model_turn_when_wall_budget_exhausted(tmp_path) -> None:
    calls = 0

    def fake_model(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return {
            "summary": "continue until wall timeout",
            "tool_calls": [
                {
                    "id": f"inspect-{calls}",
                    "name": "inspect_dir",
                    "arguments": {"path": "."},
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.001},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=3,
    )

    assert calls == 1
    assert result.status == "blocked"
    assert result.user_visible_summary == "implement_v2 wall-clock budget exhausted before finish"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["wall_timeout"]["next_turn"] == 2
    assert "not enough wall-clock budget" in result.metrics["wall_timeout"]["reason"]


def test_implement_v2_default_model_callable_uses_work_timeout_guard(monkeypatch, tmp_path) -> None:
    import mew.work_loop as work_loop

    calls = []

    def fake_guarded_model(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "summary": "blocked through guarded default path",
            "finish": {"outcome": "blocked", "summary": "guarded default path"},
        }

    monkeypatch.setattr(work_loop, "call_model_json_with_retries", fake_guarded_model)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        timeout=60,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert len(calls) == 1
    assert calls[0]["args"][5] <= 5


def test_implement_v2_blocks_exec_tool_when_wall_budget_exhausted_after_model_turn(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        time.sleep(0.01)
        return {
            "summary": "try command after wall is gone",
            "tool_calls": [
                {
                    "id": "too-late-command",
                    "name": "run_command",
                    "arguments": {
                        "command": "sleep 0.1; printf done > should_not_exist.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "foreground_budget_seconds": 0.1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.001},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=3,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]
    assert result.status == "blocked"
    assert result.user_visible_summary == "implement_v2 wall-clock budget exhausted before tool execution"
    assert tool_result["status"] == "invalid"
    assert tool_result["content"][0]["reason"] == "implement_v2_wall_budget_exhausted_before_tool_execution"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["wall_timeout"]["reason"] == "not enough wall-clock budget remains for tool execution"
    assert not (tmp_path / "should_not_exist.txt").exists()


def test_implement_v2_live_json_extends_one_reaction_turn_after_final_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final compile attempt",
            "tool_calls": [
                {
                    "id": "compile-fail",
                    "name": "run_command",
                    "arguments": {"command": "printf 'compile failed\\n' >&2; exit 2", "cwd": ".", "use_shell": True},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "make the smallest terminal-failure repair and verify",
            "tool_calls": [
                {
                    "id": "repair-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf fixed > fixed.txt && test \"$(cat fixed.txt)\" = fixed",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "latest terminal failure repaired",
                "acceptance_evidence": ["repair-verify confirmed fixed.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify fixed.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[1]
    assert (tmp_path / "fixed.txt").read_text(encoding="utf-8") == "fixed"


def test_implement_v2_live_json_extends_after_final_closeout_failure(tmp_path) -> None:
    failing_command = "printf 'start\\n'; sleep 0.2; printf 'failed\\n' >&2; exit 2"
    outputs = [
        {
            "summary": "start final command that fails after foreground handoff",
            "tool_calls": [
                {
                    "id": "closeout-fail",
                    "name": "run_command",
                    "arguments": {
                        "command": failing_command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to the closeout failure",
            "tool_calls": [
                {
                    "id": "repair-after-closeout",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf closeout-repaired > closeout.txt "
                            "&& test \"$(cat closeout.txt)\" = closeout-repaired"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "closeout failure repaired",
                "acceptance_evidence": ["repair-after-closeout confirmed closeout.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify closeout.txt", "max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    assert result.status == "completed"
    assert manifest["tool_results"][0]["status"] == "failed"
    assert result.metrics["command_closeout_count"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[1]
    assert (tmp_path / "closeout.txt").read_text(encoding="utf-8") == "closeout-repaired"


def test_implement_v2_live_json_extends_after_final_diagnostic_of_prior_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "verifier fails before final budget turn",
            "tool_calls": [
                {
                    "id": "failed-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'runtime failed\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "diagnose the failure on the final base turn",
            "tool_calls": [
                {
                    "id": "diagnose-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf diagnostic > diagnostic.txt && test -f diagnostic.txt",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to the unresolved terminal failure",
            "tool_calls": [
                {
                    "id": "repair-after-diagnostic",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf repaired > repaired.txt && test \"$(cat repaired.txt)\" = repaired",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "prior terminal failure repaired after diagnostic",
                "acceptance_evidence": [
                    "diagnose-failure confirmed diagnostic.txt",
                    "repair-after-diagnostic confirmed repaired.txt",
                ],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Diagnose and repair terminal failure"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert (tmp_path / "diagnostic.txt").read_text(encoding="utf-8") == "diagnostic"
    assert (tmp_path / "repaired.txt").read_text(encoding="utf-8") == "repaired"


def test_implement_v2_live_json_extends_after_finish_gate_blocks_with_prior_terminal_failure(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("provided source\n", encoding="utf-8")
    outputs = [
        {
            "summary": "runtime verifier still misses the visual artifact",
            "tool_calls": [
                {
                    "id": "runtime-missing-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "read source then incorrectly finish from weak evidence",
            "tool_calls": [{"id": "ground-source", "name": "read_file", "arguments": {"path": "source.txt"}}],
            "finish": {
                "outcome": "completed",
                "summary": "source was grounded",
                "acceptance_evidence": ["ground-source read the provided source"],
            },
        },
        {
            "summary": "react to the prior runtime failure with verifier-shaped proof",
            "tool_calls": [
                {
                    "id": "visual-quality-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'saved /tmp/frame.bmp\\ndimension check passed expected dimensions 640x400\\nreference similarity passed\\n"
                            "removed /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "runtime visual proof completed",
                "acceptance_evidence": [
                    (
                        "visual-quality-proof confirmed expected dimensions 640x400, "
                        "reference similarity, saved /tmp/frame.bmp, and removed /tmp/frame.bmp"
                    )
                ],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert "finish gate blocked completion" in prompts[2]


def test_implement_v2_live_json_extends_after_finish_only_gate_blocks_with_prior_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "runtime verifier failed before any finish attempt",
            "tool_calls": [
                {
                    "id": "runtime-failed",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "incorrectly finish without new tool evidence",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "I reasoned about the prior failure",
                "acceptance_evidence": ["no new verifier evidence"],
            },
        },
        {
            "summary": "use the prior terminal failure reaction turn to verify behavior",
            "tool_calls": [
                {
                    "id": "runtime-repair-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf repaired > repaired.txt && test \"$(cat repaired.txt)\" = repaired",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "runtime failure repaired",
                "acceptance_evidence": ["runtime-repair-proof confirmed repaired.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Repair the failed runtime behavior."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["finish_gate_block_count"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert "finish gate blocked completion" in prompts[2]
    assert (tmp_path / "repaired.txt").read_text(encoding="utf-8") == "repaired"


def test_implement_v2_live_json_grants_progress_continuation_for_new_hard_runtime_frontier(tmp_path) -> None:
    runtime_contract = {
        "role": "runtime",
        "stage": "verification",
        "proof_role": "verifier",
        "acceptance_kind": "external_verifier",
        "expected_artifacts": [{"path": "frame.txt", "checks": [{"exists": True}, {"non_empty": True}]}],
    }
    outputs = [
        {
            "summary": "first runtime frontier still misses frame",
            "tool_calls": [
                {
                    "id": "runtime-miss-pc0",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "second runtime frontier made measurable progress",
            "tool_calls": [
                {
                    "id": "runtime-miss-pc40",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'Program terminated at PC=0x40c848\\nExecuted 4634462 instructions\\n'; exit 2"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair after progress continuation",
            "tool_calls": [
                {
                    "id": "runtime-repair",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf frame > frame.txt && test -s frame.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "frame artifact repaired",
                "acceptance_evidence": ["runtime-repair confirmed frame.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and a vm.js runtime harness. Build the source-backed "
                    "runtime artifact so node vm.js writes frame.txt."
                ),
                "final_artifact": "frame.txt",
                "max_wall_seconds": 1800,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 1,
                "hard_runtime_progress_continuation_turns": 1,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["terminal_failure_reaction_turn_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 2
    assert result.metrics["hard_runtime_progress_continuation_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 2/2" in prompts[2]
    assert (tmp_path / "frame.txt").read_text(encoding="utf-8") == "frame"


def test_implement_v2_live_json_blocks_progress_continuation_for_identical_hard_runtime_frontier(
    tmp_path,
) -> None:
    runtime_contract = {
        "role": "runtime",
        "stage": "verification",
        "proof_role": "verifier",
        "acceptance_kind": "external_verifier",
        "expected_artifacts": [{"path": "frame.txt", "checks": [{"exists": True}, {"non_empty": True}]}],
    }
    outputs = [
        {
            "summary": "first runtime frontier misses frame",
            "tool_calls": [
                {
                    "id": "runtime-miss-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "same runtime frontier repeats",
            "tool_calls": [
                {
                    "id": "runtime-miss-2",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and a vm.js runtime harness. Build the source-backed "
                    "runtime artifact so node vm.js writes frame.txt."
                ),
                "final_artifact": "frame.txt",
                "max_wall_seconds": 1800,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 1,
                "hard_runtime_progress_continuation_turns": 1,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["hard_runtime_progress_continuation_turns_used"] == 0
    assert result.metrics["model_turns"] == 2
    assert not (tmp_path / "frame.txt").exists()


def test_implement_v2_live_json_extends_after_final_failed_tool_claims_completed(tmp_path) -> None:
    outputs = [
        {
            "summary": "failed terminal result but claims done",
            "tool_calls": [
                {
                    "id": "failed-smoke",
                    "name": "run_command",
                    "arguments": {"command": "printf 'failed\\n' >&2; exit 2", "cwd": ".", "use_shell": True},
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "incorrectly claims completion",
                "acceptance_evidence": ["failed-smoke was enough"],
            },
        },
        {
            "summary": "repair after failed finish",
            "tool_calls": [
                {
                    "id": "repair-after-finish",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf finished > finish.txt && test \"$(cat finish.txt)\" = finished",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "failed finish repaired",
                "acceptance_evidence": ["repair-after-finish confirmed finish.txt"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify finish.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert (tmp_path / "finish.txt").read_text(encoding="utf-8") == "finished"


def test_implement_v2_live_json_tool_contract_recovery_extends_exactly_one_narrow_turn(tmp_path) -> None:
    outputs = [
        {
            "summary": "wrong verifier surface at final turn",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf recovered > recovered.txt && test \"$(cat recovered.txt)\" = recovered",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "retry exact verifier with run_command",
            "tool_calls": [
                {
                    "id": "corrected-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf recovered > recovered.txt && test \"$(cat recovered.txt)\" = recovered",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "tool contract recovered",
                "acceptance_evidence": ["corrected-verifier confirmed recovered.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify recovered.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first_result = manifest["tool_results"][0]

    assert result.status == "completed"
    assert first_result["status"] == "failed"
    assert first_result["content"][0]["failure_class"] == "tool_contract_misuse"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["tool_contract_recovery_turns_used"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert result.metrics["model_turns"] == 2
    assert "Tool-contract recovery turn" in prompts[1]
    assert "run_tests is argv-only" in prompts[1]
    assert "preserved_command: printf recovered > recovered.txt" in prompts[1]
    assert "If this is a terminal-failure reaction turn" not in prompts[1]
    assert "terminal_failure_reaction_turns_used: 0/" in prompts[1]
    assert (tmp_path / "recovered.txt").read_text(encoding="utf-8") == "recovered"


def test_implement_v2_live_json_tool_contract_recovery_does_not_extend_after_later_success(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "wrong verifier then corrected verifier in same turn",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > wrong.txt && test -f wrong.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "corrected-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf ok > ok.txt && test \"$(cat ok.txt)\" = ok",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "corrected verifier succeeded",
                "acceptance_evidence": ["corrected-verifier confirmed ok.txt"],
            },
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify ok.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert not (tmp_path / "wrong.txt").exists()
    assert (tmp_path / "ok.txt").read_text(encoding="utf-8") == "ok"


def test_implement_v2_live_json_tool_contract_misuse_does_not_use_terminal_failure_reaction(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "wrong verifier surface without shell permission",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > denied.txt && test -f denied.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Do not run shell verifier"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_verify": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert first_result["status"] == "failed"
    assert first_result["content"][0]["failure_class"] == "tool_contract_misuse"
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert result.metrics["turn_budget_limit"] == 1
    assert not (tmp_path / "denied.txt").exists()


def test_implement_v2_live_json_real_terminal_failure_takes_precedence_over_tool_contract_misuse(tmp_path) -> None:
    outputs = [
        {
            "summary": "real failure and wrong verifier surface in same final turn",
            "tool_calls": [
                {
                    "id": "real-terminal-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf real-fail >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > wrong.txt && test -f wrong.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to real terminal failure",
            "tool_calls": [
                {
                    "id": "repair-real-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf real-repaired > real.txt && test \"$(cat real.txt)\" = real-repaired",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "real failure repaired",
                "acceptance_evidence": ["repair-real-failure confirmed real.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Repair real terminal failure"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert "Tool-contract recovery turn" not in prompts[1]
    assert "If this is a terminal-failure reaction turn" in prompts[1]
    assert not (tmp_path / "wrong.txt").exists()
    assert (tmp_path / "real.txt").read_text(encoding="utf-8") == "real-repaired"


def test_implement_v2_closeout_preserves_command_timeout(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(3)"])

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start command with shorter command timeout than wall budget",
            "tool_calls": [
                {
                    "id": "call-timeout",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 1,
                        "foreground_budget_seconds": 0.001,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    content = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert content["timed_out"] is True
    assert content["timeout_seconds"] <= 1
    assert result.metrics["command_closeout_count"] == 1


def test_implement_v2_closeout_config_is_capped_by_remaining_wall_budget(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(3)"])

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start command with closeout config above wall budget",
            "tool_calls": [
                {
                    "id": "call-wall-cap",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.1},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "command_closeout_seconds": 5,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    content = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert content["timed_out"] is True
    assert content["timeout_seconds"] < 1
    assert result.metrics["command_closeout_count"] == 1


def test_v2_tool_policy_marks_write_and_execute_tools_approval_gated() -> None:
    specs = {spec.name: spec for spec in list_v2_base_tool_specs()}

    assert specs["inspect_dir"].approval_required is False
    assert specs["read_file"].approval_required is False
    assert specs["search_text"].approval_required is False
    assert specs["glob"].approval_required is False
    assert specs["git_status"].access == "read"
    assert specs["git_diff"].access == "read"
    assert specs["run_command"].approval_required is True
    assert specs["run_tests"].approval_required is True
    assert specs["poll_command"].approval_required is False
    assert specs["cancel_command"].approval_required is False
    assert specs["read_command_output"].access == "execute"
    assert specs["write_file"].approval_required is True
    assert specs["edit_file"].dry_run_supported is True
    assert specs["apply_patch"].dry_run_supported is True


def test_fake_provider_normalizes_tool_calls_and_transcript_events() -> None:
    adapter = FakeProviderAdapter()
    calls = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            FakeProviderToolCall(
                provider_call_id="provider-call-1",
                tool_name="read_file",
                arguments={"path": "README.md"},
                provider_message_id="message-1",
            ),
        ),
    )
    events = adapter.transcript_events_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        turn_id="turn-1",
        text="I will inspect the repo.",
        tool_calls=calls,
    )

    assert calls[0].provider == "fake"
    assert calls[0].provider_call_id == "provider-call-1"
    assert calls[0].mew_tool_call_id == "lane-v2-1:tool:1:1"
    assert calls[0].arguments == {"path": "README.md"}
    assert [event.kind for event in events] == ["model_message", "tool_call"]
    assert events[0].payload["lane_attempt_id"] == "lane-v2-1"
    assert events[0].event_id == "implement_v2:lane-v2-1:turn-1:model_message:0"
    assert events[1].payload["provider_call_id"] == "provider-call-1"
    assert events[1].event_id == "implement_v2:lane-v2-1:turn-1:tool_call:1"


def test_fake_provider_can_emit_finish_event_distinctly_from_tool_call() -> None:
    event = FakeProviderAdapter().finish_event_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        turn_id="turn-1",
        finish_arguments={"outcome": "analysis_ready"},
    )

    assert event.kind == "finish"
    assert event.event_id == "implement_v2:lane-v2-1:turn-1:finish:0"
    assert event.payload["finish_arguments"] == {"outcome": "analysis_ready"}


def test_tool_result_pairing_validator_accepts_exactly_paired_results() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"text": "ok"},),
        content_refs=("artifact://content",),
    )

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert validation.as_dict()["errors"] == []
    assert payload["tool_result"]["tool_use_id"] == "call-1"
    assert payload["tool_result"]["is_error"] is False
    assert payload["tool_result"]["content"]["mew_status"] == "completed"


def test_tool_result_pairing_validator_rejects_unpaired_or_orphan_results() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    orphan = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="orphan",
        mew_tool_call_id="lane-v2-1:tool:1:99",
        tool_name="read_file",
        status="completed",
    )

    validation = validate_tool_result_pairing((call,), (orphan,))

    assert validation.valid is False
    assert "missing_result_for_provider_call_id:call-1" in validation.errors
    assert "orphan_result_for_provider_call_id:orphan" in validation.errors


def test_tool_result_pairing_validator_rejects_cross_attempt_result() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="attempt-a",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-b",
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
    )

    validation = validate_tool_result_pairing((call,), (result,))

    assert validation.valid is False
    assert "lane_attempt_id_mismatch:call-1" in validation.errors


def test_proof_manifest_pairing_validator_rejects_internally_paired_wrong_attempt() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="attempt-b",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-b",
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-a",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
    )

    validation = validate_proof_manifest_pairing(manifest)

    assert validation.valid is False
    assert "tool_call_wrong_lane_attempt_id:call-1" in validation.errors
    assert "tool_result_wrong_lane_attempt_id:call-1" in validation.errors


def test_invalid_tool_call_gets_paired_model_visible_error_result() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "unknown_tool"},),
    )[0]
    result = build_invalid_tool_result(call, reason="unknown tool")

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert result.status == "invalid"
    assert result.is_error is True
    assert payload["tool_result"]["content"]["mew_status"] == "invalid"


def test_nonterminal_result_is_provider_visible_content_not_protocol_error() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "run_command"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="yielded",
        is_error=False,
        content=({"command_run_id": "cmd-1"},),
        content_refs=("artifact://cmd-1-output",),
    )

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert payload["tool_result"]["is_error"] is False
    assert payload["tool_result"]["content"]["mew_status"] == "yielded"
    assert payload["tool_result"]["content"]["acceptance_evidence"] is False


def test_implement_v2_history_compacts_large_tool_output_for_next_turn() -> None:
    large_output = "first error\n" + ("warning: noisy linker output\n" * 700) + "final linker error\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="read_command_output",
        status="completed",
        content=(
            {
                "command_run_id": "cmd-1",
                "output_path": "/tmp/output.log",
                "content": large_output,
                "chars": len(large_output),
                "truncated": False,
                "status": "completed",
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
    )

    visible = _provider_visible_tool_result_for_history(result)
    history_content = visible["content"]
    item = history_content["content"][0]

    assert history_content["history_compacted"] is True
    assert item["content_history_chars"] == len(large_output)
    assert item["content_history_truncated"] is True
    assert len(item["content"]) < 3000
    assert "first error" in item["content"]
    assert "final linker error" in item["content"]
    assert history_content["content_refs"] == ["implement-v2-exec://lane-v2-1/cmd-1/output"]


def test_implement_v2_history_projects_terminal_output_to_tails_for_next_turn() -> None:
    noisy_stdout = "first line\n" + ("compiler noise\n" * 600) + "final line\n"
    noisy_stderr = "warning\n" + ("linker warning\n" * 300) + "fatal linker error\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command_run_id": "cmd-1",
                "command": "make very-noisy-target",
                "output_ref": "lane-v2-1/cmd-1/output.log",
                "output_path": "/tmp/mew/hidden/output.log",
                "status": "failed",
                "exit_code": 2,
                "timed_out": False,
                "stdout": noisy_stdout,
                "stderr": noisy_stderr,
                "stdout_tail": "final line\n",
                "stderr_tail": "fatal linker error\n",
                "output_bytes": len(noisy_stdout) + len(noisy_stderr),
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
    )

    visible = _provider_visible_tool_result_for_history(result)
    history_content = visible["content"]
    item = history_content["content"][0]

    assert history_content["history_projected"] is True
    assert item["provider_history_projection"] == "terminal_result_v0"
    assert item["command_run_id"] == "cmd-1"
    assert item["output_ref"] == "lane-v2-1/cmd-1/output.log"
    assert item["exit_code"] == 2
    assert item["stdout_tail"] == "final line\n"
    assert item["stderr_tail"] == "fatal linker error\n"
    assert item["stdout_chars"] == len(noisy_stdout)
    assert item["stderr_chars"] == len(noisy_stderr)
    assert "stdout" not in item
    assert "stderr" not in item
    assert "output_path" not in item
    assert noisy_stdout not in json.dumps(visible)
    assert noisy_stderr not in json.dumps(visible)


def test_implement_v2_history_projects_terminal_side_effects_for_next_turn() -> None:
    noisy_preview = "first symbol\n" + ("large readelf output\n" * 500) + "final symbol\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-probe",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command_run_id": "cmd-1",
                "command": "readelf -s binary",
                "output_ref": "lane-v2-1/cmd-1/output.log",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "stdout": noisy_preview,
                "stdout_tail": "final symbol\n",
                "output_bytes": len(noisy_preview),
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
        side_effects=(
            {
                "kind": "tool_run_record",
                "record": {
                    "record_id": "tool-run-record:call-probe:1:completed:abc",
                    "command_run_id": "cmd-1",
                    "provider_call_id": "call-probe",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "duration_seconds": 0.12,
                    "stdout_ref": "implement-v2-exec://lane-v2-1/cmd-1/stdout",
                    "stderr_ref": "implement-v2-exec://lane-v2-1/cmd-1/stderr",
                    "combined_output_ref": "implement-v2-exec://lane-v2-1/cmd-1/output",
                    "stdout_preview": noisy_preview,
                    "stderr_preview": "",
                    "semantic_exit": {"ok": True, "category": "ok", "message": "any exit accepted"},
                },
            },
            {
                "kind": "failure_classification",
                "record": {
                    "classification_id": "failure:cmd-1",
                    "phase": "unknown",
                    "kind": "unknown_failure",
                    "class": "unknown_failure",
                    "summary": "no structured failure evidence",
                    "required_next_probe": "",
                },
            },
        ),
    )

    visible = _provider_visible_tool_result_for_history(result)
    content = visible["content"]
    serialized = json.dumps(visible)
    side_effects = content["side_effects"]
    tool_run_record = side_effects[0]["record"]

    assert content["side_effects_projected"] is True
    assert tool_run_record["command_run_id"] == "cmd-1"
    assert tool_run_record["stdout_ref"] == "implement-v2-exec://lane-v2-1/cmd-1/stdout"
    assert tool_run_record["semantic_exit"] == {"ok": True, "category": "ok"}
    assert "stdout_preview" not in tool_run_record
    assert "large readelf output" not in serialized
    assert len(serialized) < 5000


def test_implement_v2_history_compacts_older_turns_for_hot_path() -> None:
    large_read = "vm head\n" + ("generated vm body\n" * 600) + "vm tail\n"
    old_result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-read-old-vm",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=(
            {
                "path": "vm.js",
                "content": large_read,
                "chars": len(large_read),
                "summary": "Read file vm.js",
            },
        ),
        content_refs=("implement-v2-read://lane-v2-1/call-read-old-vm/content",),
        evidence_refs=("implement-v2-read://lane-v2-1/call-read-old-vm/evidence",),
    )
    old_call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-read-old-vm",
                "tool_name": "read_file",
                "arguments": {"path": "vm.js"},
            },
        ),
    )[0]
    history = [
        {
            "turn": 1,
            "summary": "Read generated VM after a verifier failure.",
            "tool_calls": [_provider_visible_tool_call_for_history(old_call)],
            "tool_results": [_provider_visible_tool_result_for_history(old_result)],
        }
    ]
    for turn in range(2, 7):
        history.append(
            {
                "turn": turn,
                "summary": f"Recent turn {turn}.",
                "tool_calls": [],
                "tool_results": [],
            }
        )

    rendered = _render_prompt_history_json(history)
    projected = json.loads(rendered)
    old_entry = projected[0]

    assert old_entry["history_compacted"] is True
    assert old_entry["tool_calls"][0]["arguments"] == {"path": "vm.js"}
    assert old_entry["tool_results"][0]["content_refs"] == [
        "implement-v2-read://lane-v2-1/call-read-old-vm/content"
    ]
    assert old_entry["tool_results"][0]["evidence_ref_count"] == 1
    assert "generated vm body" not in rendered
    assert "vm tail" not in rendered
    assert projected[-1]["summary"] == "Recent turn 6."


def test_implement_v2_history_projection_preserves_terminal_diagnostics_without_output() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "status": "failed",
                "reason": "run_command is disabled; pass --allow-shell",
                "error": "unknown command_run_id: cmd-missing",
                "failure_class": "tool_policy_denied",
            },
        ),
    )

    visible = _provider_visible_tool_result_for_history(result)
    item = visible["content"]["content"][0]

    assert item["provider_history_projection"] == "terminal_result_v0"
    assert item["status"] == "failed"
    assert item["reason"] == "run_command is disabled; pass --allow-shell"
    assert item["error"] == "unknown command_run_id: cmd-missing"
    assert item["failure_class"] == "tool_policy_denied"
    assert "stdout" not in item
    assert "stderr" not in item


def test_implement_v2_projects_large_source_mutation_tool_call_arguments_for_history() -> None:
    large_old = "old head\n" + ("old middle\n" * 400) + "old tail\n"
    large_new = "new head\n" + ("new middle\n" * 400) + "new tail\n"
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old_string": large_old, "new_string": large_new},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    args = projected["arguments"]

    assert args["arguments_projected_for_history"] is True
    assert args["old_string"]["history_text_omitted"] is True
    assert args["new_string"]["history_text_omitted"] is True
    assert args["old_string"]["sha256"] == "sha256:" + hashlib.sha256(large_old.encode()).hexdigest()
    assert args["new_string"]["sha256"] == "sha256:" + hashlib.sha256(large_new.encode()).hexdigest()
    assert large_old not in json.dumps(projected)
    assert large_new not in json.dumps(projected)


def test_implement_v2_projects_source_mutation_alias_arguments_for_history() -> None:
    large_old = "old head\n" + ("old alias middle\n" * 300) + "old tail\n"
    large_new = "new head\n" + ("new alias middle\n" * 300) + "new tail\n"
    large_patch = "*** Begin Patch\n*** Update File: vm.js\n" + ("-a\n+b\n" * 300) + "*** End Patch\n"
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit-alias",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old": large_old, "new": large_new},
            },
            {
                "provider_call_id": "call-patch-input",
                "tool_name": "apply_patch",
                "arguments": {"input": large_patch},
            },
        ),
    )

    edit_args = _provider_visible_tool_call_for_history(calls[0])["arguments"]
    patch_args = _provider_visible_tool_call_for_history(calls[1])["arguments"]

    assert edit_args["arguments_projected_for_history"] is True
    assert edit_args["old"]["history_text_omitted"] is True
    assert edit_args["new"]["history_text_omitted"] is True
    assert patch_args["arguments_projected_for_history"] is True
    assert patch_args["input"]["history_text_omitted"] is True
    projected_text = json.dumps({"edit": edit_args, "patch": patch_args})
    assert large_old not in projected_text
    assert large_new not in projected_text
    assert large_patch not in projected_text


def test_implement_v2_source_mutation_projection_respects_small_clip_limit() -> None:
    content = "A" * 950
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-write",
                "tool_name": "write_file",
                "arguments": {"path": "generated.py", "content": content},
            },
        ),
    )[0]

    args = _provider_visible_tool_call_for_history(call)["arguments"]
    excerpt = args["content"]["excerpt"]

    assert args["content"]["history_text_omitted"] is True
    assert len(excerpt) <= 900
    assert "history clipped -" not in excerpt
    assert args["content"]["sha256"] == "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def test_implement_v2_keeps_small_source_mutation_tool_call_arguments_visible() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old_string": "old();", "new_string": "new();"},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    args = projected["arguments"]

    assert args["old_string"] == "old();"
    assert args["new_string"] == "new();"
    assert "arguments_projected_for_history" not in args


def test_implement_v2_compacts_prompt_history_without_clipping_history_artifact(tmp_path) -> None:
    prompts: list[str] = []
    artifact_dir = tmp_path / "artifacts"
    outputs = [
        {
            "summary": "produce noisy output",
            "tool_calls": [
                {
                    "id": "call-noisy",
                    "name": "run_command",
                    "arguments": {
                        "command": shlex.join(
                            [
                                sys.executable,
                                "-c",
                                "print('first error'); print('warning: noisy output\\n' * 160); print('final linker error')",
                            ]
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "blocked after reading compacted history",
            "finish": {"outcome": "blocked", "summary": "enough evidence"},
        },
    ]

    def fake_model(_backend, _auth, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    history_path = next(path for path in result.proof_artifacts if path.endswith("history.json"))
    history = json.loads(open(history_path, encoding="utf-8").read())
    persisted_output = history[0]["tool_results"][0]["content"]["content"][0]["stdout"]

    assert result.status == "blocked"
    assert "history_projected" in prompts[1]
    assert "stdout_stderr_body_omitted" in prompts[1]
    assert persisted_output not in prompts[1]
    assert "history_projected" not in persisted_output
    assert "final linker error" in persisted_output
    assert "final linker error" in prompts[1]


def test_implement_v2_compacts_large_write_call_for_prompt_history_only(tmp_path) -> None:
    prompts: list[str] = []
    artifact_dir = tmp_path / "artifacts"
    middle_marker = "UNIQUE_MIDDLE_MARKER_SHOULD_NOT_REACH_NEXT_PROMPT"
    large_content = "module head\n" + ("x = 1\n" * 300) + middle_marker + "\n" + ("y = 2\n" * 300) + "module tail\n"
    outputs = [
        {
            "summary": "write a large generated source file",
            "tool_calls": [
                {
                    "id": "call-write-large",
                    "name": "write_file",
                    "arguments": {
                        "path": "generated.py",
                        "content": large_content,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "blocked after reading compacted write call",
            "finish": {"outcome": "blocked", "summary": "enough evidence"},
        },
    ]

    def fake_model(_backend, _auth, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    history_path = next(path for path in result.proof_artifacts if path.endswith("history.json"))
    history = json.loads(open(history_path, encoding="utf-8").read())
    persisted_content = history[0]["tool_calls"][0]["arguments"]["content"]

    assert result.status == "blocked"
    assert persisted_content == large_content
    assert "arguments_projected_for_history" in prompts[1]
    assert "history_text_omitted" in prompts[1]
    assert "sha256:" + hashlib.sha256(large_content.encode()).hexdigest() in prompts[1]
    assert middle_marker not in prompts[1]


def test_proof_manifest_serializes_lane_attempt_calls_results_and_metrics() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        evidence_refs=("artifact://evidence",),
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
        metrics={"tool_calls": 1},
    )

    data = manifest.as_dict()

    assert data["lane"] == IMPLEMENT_V2_LANE
    assert data["tool_calls"][0]["provider_call_id"] == "call-1"
    assert data["tool_results"][0]["evidence_refs"] == ["artifact://evidence"]
    assert data["metrics"] == {"tool_calls": 1}


def test_implement_v2_prompt_metrics_are_memory_light_by_default() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "inspect only"},
        lane_config={"mode": "read_only"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}

    assert metrics["contract_version"] == "prompt_sections_v1"
    assert "implement_v2_lane_base" in by_id
    assert "implement_v2_tool_contract" in by_id
    assert "implement_v2_execution_artifact_contract" in by_id
    assert "implement_v2_tool_surface" in by_id
    assert "implement_v2_compatibility_frontier" in by_id
    assert "implement_v2_task_contract" in by_id
    assert "implement_v2_lane_state" in by_id
    assert "implement_v2_memory_summary" not in by_id
    assert by_id["implement_v2_lane_base"]["cache_hint"] == "cacheable_prefix"
    assert by_id["implement_v2_execution_artifact_contract"]["cache_hint"] == "cacheable_prefix"
    assert by_id["implement_v2_compatibility_frontier"]["cache_hint"] == "cacheable_prefix"
    assert by_id["implement_v2_lane_state"]["cache_hint"] == "dynamic"


def test_implement_v2_prompt_metrics_include_hot_path_collapse_phase0_inventory() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "repair a runtime artifact"},
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {"target_paths": ["vm.js"]},
            },
            "lane_hard_runtime_frontier": {"schema_version": 1, "status": "active"},
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    collapse = metrics["hot_path_collapse"]
    inventory = {section["id"]: section for section in collapse["normal_section_inventory"]}

    assert collapse["schema_version"] == 1
    assert collapse["phase"] == "m6_24_hot_path_collapse_phase_0"
    assert collapse["surfaces"]["hot_path_projection"] == "hot_path_projection"
    assert collapse["surfaces"]["resident_sidecar_state"] == "resident_sidecar_state"
    assert collapse["surfaces"]["finish_replay_recovery"] == "finish_replay_recovery"
    assert "normal_full_prompt_bytes" not in collapse
    assert collapse["normal_prompt_section_bytes"] == metrics["total_chars"]
    assert collapse["normal_static_cacheable_bytes"] > 0
    assert collapse["ordinary_resident_summary_bytes"] > 0
    assert collapse["resident_model_visible_bytes"] == 0
    assert inventory["implement_v2_lane_base"]["surface"] == "hot_path_projection"
    assert inventory["implement_v2_active_work_todo"]["surface"] == "ordinary_resident_summary"
    assert inventory["implement_v2_hard_runtime_frontier_state"]["surface"] == "ordinary_resident_summary"
    assert inventory["implement_v2_execution_artifact_contract"]["surface"] == "finish_replay_recovery"
    ordinary_resident_bytes = sum(
        section["bytes"]
        for section in collapse["normal_section_inventory"]
        if section["surface"] == "ordinary_resident_summary"
    )
    assert ordinary_resident_bytes <= 1536


def test_implement_v2_active_coding_rhythm_requires_probe_fallbacks() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "inspect source cheaply"},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    section = next(item for item in sections if item.id == "implement_v2_active_coding_rhythm")

    assert "optional CLI such as rg" in section.content
    assert "source frontier as incomplete" in section.content
    assert "grep -R" in section.content
    assert "Do not mask a missing probe with `|| true`" in section.content


def test_implement_v2_prompt_explains_expected_artifact_contract() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "build and verify an artifact"},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    section = next(item for item in sections if item.id == "implement_v2_execution_artifact_contract")

    assert section.cache_policy == "cacheable"
    assert section.stability == "static"
    assert "expected_artifacts" in section.content
    assert "poll_command inherits the original command's contract" in section.content
    assert "do not introduce new artifact obligations only on a later poll" in section.content
    assert "Mew owns artifact checking" in section.content
    assert "stdout/stderr text markers" in section.content
    assert "evidence ids" in section.content


def test_implement_v2_v0_filters_memory_even_when_memory_summary_exists() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        persisted_lane_state={
            "memory_summary": "Use the prior bounded repair only as read-only context.",
            "lane_memory_summary": "Do not include me.",
            "reentry_memory_refs": ["mem-1"],
            "lane_safe_resume_token": "resume-1",
            "lane_safe_resume_payload": {"proof_manifest": {"tool_results": ["do-not-leak"]}},
            "lane_safe_scalar_list": ["resume-2", {"frontier": "do-not-leak"}],
        },
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    lane_state = next(section for section in sections if section.id == "implement_v2_lane_state")

    assert "implement_v2_memory_summary" not in by_id
    assert "memory_summary" not in lane_state.content
    assert "lane_memory_summary" not in lane_state.content
    assert "reentry_memory_refs" not in lane_state.content
    assert "lane_safe_resume_token" in lane_state.content
    assert "lane_safe_scalar_list" in lane_state.content
    assert "lane_safe_resume_payload" not in lane_state.content
    assert "do-not-leak" not in lane_state.content


def test_implement_v2_prompt_adds_dynamic_repair_history_section() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "lane_repair_history": {
                "task": "make-mips-interpreter",
                "avoid_repeated_repairs": ["rewriting vm.js before checking latest PC loop"],
                "next_generic_probe": "inspect latest runtime trace and artifact production path",
            }
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    repair_section = next(section for section in sections if section.id == "implement_v2_repair_history")
    lane_state = next(section for section in sections if section.id == "implement_v2_lane_state")

    assert by_id["implement_v2_repair_history"]["cache_hint"] == "dynamic"
    assert "repair_card" in repair_section.content
    assert "avoid_repeated_repairs" in repair_section.content
    assert "latest runtime trace" in repair_section.content
    assert "lane_repair_history" not in lane_state.content


def test_implement_v2_repair_history_section_is_bounded() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={"lane_repair_history": {"log": ['"quoted\\value"' * 2000]}},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    repair_section = next(section for section in sections if section.id == "implement_v2_repair_history")

    assert len(repair_section.content) <= 1536
    assert "__mew_truncated__" in repair_section.content
    assert "preview" not in repair_section.content
    assert "quoted" not in repair_section.content


def test_implement_v2_repair_history_omits_nested_summary_payloads() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "lane_repair_history": {
                "summary": {"proof_object": {"secret": "do-not-leak"}},
                "notes": [{"evidence": "do-not-leak"}],
                "avoid_repeated_repairs": [{"summary": {"proof_object": "do-not-leak"}}],
                "items": [{"summary": {"evidence": "do-not-leak"}, "failure_kind": "runtime"}],
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    repair_section = next(section for section in sections if section.id == "implement_v2_repair_history")

    assert "repair_card" in repair_section.content
    assert "runtime" in repair_section.content
    assert "proof_object" not in repair_section.content
    assert "evidence" not in repair_section.content
    assert "do-not-leak" not in repair_section.content


def test_implement_v2_active_work_todo_card_preserves_next_action_under_budget() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {
                    "plan_item": "inspect and patch " + ("nested runtime source " * 20),
                    "target_paths": [
                        "src/" + ("deep/" * 20) + "vm.js",
                        "tests/" + ("deep/" * 20) + "test_vm.py",
                        "docs/" + ("deep/" * 20) + "notes.md",
                        "extra/" + ("deep/" * 20) + "ignored.md",
                    ],
                    "verify_command": "python -m pytest " + ("--very-long-flag " * 20),
                },
                "first_write_readiness": {
                    "first_write_due": True,
                    "probes_seen_without_write": 4,
                    "required_next_action": "patch the runtime loader before another broad probe " * 10,
                },
                "write_repair": {
                    "failure_kind": "stale_exact_edit" * 20,
                    "path": "src/" + ("nested/" * 20) + "loader.py",
                    "required_next_action": "repair the failed edit against current file text " * 10,
                },
            },
            "lane_hard_runtime_frontier": {
                "latest_runtime_failure": {
                    "failure_class": "runtime_artifact_contract_mismatch" * 5,
                    "stderr_tail": "vm halted after malformed frame output " * 20,
                    "required_next_probe": "compare runtime artifact path and loader ABI " * 10,
                },
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    active_section = next(section for section in sections if section.id == "implement_v2_active_work_todo")

    assert len(active_section.content) <= 640
    assert "__mew_truncated__" not in active_section.content
    assert '"first_write_due":true' in active_section.content
    assert '"target_paths":' in active_section.content
    assert "required_next_action" in active_section.content
    assert "repair the failed edit" in active_section.content


def test_implement_v2_active_work_todo_omits_nested_next_action_payloads() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "active_work_todo": {
                "source": {
                    "plan_item": {"proof_object": "do-not-leak"},
                    "target_paths": [{"proof_object": "do-not-leak"}, "src/app.py"],
                    "verify_command": {"evidence": "do-not-leak"},
                },
                "blocker": {"recovery_action": {"proof_object": "do-not-leak"}},
                "first_write_readiness": {
                    "first_write_due": True,
                    "required_next_action": {"proof_object": "do-not-leak"},
                },
                "write_repair": {"required_next_action": {"evidence": "do-not-leak"}},
            },
            "lane_hard_runtime_frontier": {
                "latest_runtime_failure": {
                    "required_next_probe": {"frontier": "do-not-leak"},
                    "stderr_tail": "safe bounded failure tail",
                }
            },
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    active_section = next(section for section in sections if section.id == "implement_v2_active_work_todo")
    frontier_section = next(section for section in sections if section.id == "implement_v2_hard_runtime_frontier_state")

    assert '"first_write_due":true' in active_section.content
    assert "src/app.py" in active_section.content
    assert "safe bounded failure tail" in active_section.content
    assert "proof_object" not in active_section.content
    assert "evidence" not in active_section.content
    assert "frontier" not in active_section.content
    assert "do-not-leak" not in active_section.content
    assert '"frontier":"do-not-leak"' not in frontier_section.content
    assert "do-not-leak" not in frontier_section.content


def test_implement_v2_prompt_adds_hard_runtime_profile_for_vm_artifact_task() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": (
                "I provided /app/game source code and vm.js expects a game_mips ELF. "
                "Build the source so node vm.js prints stdout appropriately and writes "
                "/tmp/frame.bmp."
            )
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    by_id = {section.id: section for section in sections}

    assert "implement_v2_hard_runtime_profile" in by_id
    assert "handcrafted stub" in by_id["implement_v2_hard_runtime_profile"].content
    assert "provided source" in by_id["implement_v2_hard_runtime_profile"].content
    assert "run one verifier" in by_id["implement_v2_hard_runtime_profile"].content
    assert "fresh runtime/verifier evidence" in by_id["implement_v2_hard_runtime_profile"].content
    assert "implement_v2_hard_runtime_frontier_state" in by_id
    assert "Do not finish from this state alone" in by_id["implement_v2_hard_runtime_frontier_state"].content
    assert len(by_id["implement_v2_hard_runtime_frontier_state"].content) <= 1536


def test_implement_v2_hard_runtime_profile_expands_terminal_reaction_budget() -> None:
    hard_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": (
                "I provided /app/game source code and vm.js expects a game_mips ELF. "
                "Build the source so node vm.js prints stdout appropriately and writes "
                "/tmp/frame.bmp."
            ),
            "max_wall_seconds": 1800,
        },
        lane_config={"mode": "full"},
    )
    simple_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-2",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Fix a small Python unit test."},
        lane_config={"mode": "full"},
    )
    configured_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-3",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract=hard_runtime_input.task_contract,
        lane_config={"mode": "full", "terminal_failure_reaction_turns": 2},
    )
    persisted_frontier_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-4",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a task with persisted lane frontier.", "max_wall_seconds": 1800},
        lane_config={"mode": "full"},
        persisted_lane_state={"lane_hard_runtime_frontier": {"status": "active"}},
    )
    missing_wall_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-5",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": hard_runtime_input.task_contract["description"]},
        lane_config={"mode": "full"},
    )
    invalid_wall_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-6",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": hard_runtime_input.task_contract["description"], "max_wall_seconds": "later"},
        lane_config={"mode": "full"},
    )

    assert _terminal_failure_reaction_turn_limit(simple_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(hard_runtime_input, 24) == 8
    assert _terminal_failure_reaction_turn_limit(persisted_frontier_input, 24) == 8
    assert _terminal_failure_reaction_turn_limit(missing_wall_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(invalid_wall_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(configured_input, 24) == 2
    assert _hard_runtime_progress_continuation_turn_limit(hard_runtime_input, base_max_turns=24) == 4
    assert _hard_runtime_progress_continuation_turn_limit(simple_input, base_max_turns=24) == 0
    assert _hard_runtime_progress_continuation_turn_limit(missing_wall_input, base_max_turns=24) == 0


def test_implement_v2_hard_runtime_progress_signature_requires_runtime_artifact_progress() -> None:
    frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "final_artifact": {"path": "/tmp/frame.bmp", "status": "failed", "blocking": True},
        "latest_runtime_failure": {
            "failure_class": "runtime_artifact_missing",
            "failure_phase": "runtime",
            "failure_kind": "missing_artifact",
            "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        },
    }
    same_frontier = json.loads(json.dumps(frontier))
    moved_frontier = json.loads(json.dumps(frontier))
    moved_frontier["latest_runtime_failure"]["stdout_tail"] = "Program terminated at PC=0x40d000\nExecuted 5000000"
    artifact_validation_frontier = json.loads(json.dumps(frontier))
    artifact_validation_frontier["latest_runtime_failure"] = {
        "failure_class": "artifact_validation_failure",
        "failure_phase": "unknown",
        "failure_kind": "missing_artifact",
        "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        "required_next_probe": "Inspect the producing substep and artifact path before another rebuild.",
    }
    artifact_validation_build_phase = json.loads(json.dumps(artifact_validation_frontier))
    artifact_validation_build_phase["latest_runtime_failure"]["failure_phase"] = "build"
    nonblocking_artifact_validation = json.loads(json.dumps(artifact_validation_frontier))
    nonblocking_artifact_validation["final_artifact"] = {"path": "/tmp/frame.bmp", "status": "failed"}
    partial_artifact_validation = json.loads(json.dumps(artifact_validation_frontier))
    partial_artifact_validation["final_artifact"] = {"path": "/tmp/frame.bmp", "status": "partial", "blocking": True}
    build_only_frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "latest_build_failure": {"failure_class": "build_failure", "stderr_tail": "undefined reference"},
    }

    signature = _hard_runtime_frontier_progress_signature(frontier)

    assert signature
    assert _hard_runtime_frontier_progress_signature(same_frontier) == signature
    assert _hard_runtime_frontier_progress_signature(moved_frontier) != signature
    assert _hard_runtime_frontier_progress_signature(artifact_validation_frontier)
    assert _hard_runtime_frontier_progress_signature(artifact_validation_build_phase) == ""
    assert _hard_runtime_frontier_progress_signature(nonblocking_artifact_validation) == ""
    assert _hard_runtime_frontier_progress_signature(partial_artifact_validation) == ""
    assert _hard_runtime_frontier_progress_signature(build_only_frontier) == ""


def test_implement_v2_hard_runtime_progress_continuation_rejects_seen_signature() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": "Build provided VM source so node vm.js writes /tmp/frame.bmp.",
            "max_wall_seconds": 1800,
        },
        lane_config={"mode": "full", "terminal_failure_reaction_min_wall_seconds": 0},
    )
    tool_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        content=({"failure_class": "runtime_failure"},),
    )
    frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "final_artifact": {"path": "/tmp/frame.bmp", "status": "failed", "blocking": True},
        "latest_runtime_failure": {
            "failure_class": "runtime_artifact_missing",
            "failure_phase": "runtime",
            "failure_kind": "missing_artifact",
            "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        },
    }
    seen = {_hard_runtime_frontier_progress_signature(frontier)}

    assert (
        _hard_runtime_progress_continuation_signature(
            lane_input,
            (tool_result,),
            frontier,
            seen_signatures=seen,
            reaction_turns_used=8,
            reaction_turn_limit=8,
            progress_turns_used=0,
            progress_turn_limit=4,
            run_started=time.monotonic(),
        )
        == ""
    )
    assert _hard_runtime_progress_continuation_signature(
        lane_input,
        (tool_result,),
        {
            **frontier,
            "latest_runtime_failure": {
                **frontier["latest_runtime_failure"],
                "stdout_tail": "Program terminated at PC=0x40d000\nExecuted 5000000",
            },
        },
        seen_signatures=seen,
        reaction_turns_used=8,
        reaction_turn_limit=8,
        progress_turns_used=0,
        progress_turn_limit=4,
        run_started=time.monotonic(),
    )


def test_implement_v2_prompt_adds_dynamic_frontier_state_when_persisted() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Update docs only."},
        persisted_lane_state={
            "lane_hard_runtime_frontier": {
                "schema_version": 1,
                "status": "active",
                "objective": "preserve source-backed artifact proof",
                "source_roles": [{"path": "vm.js", "role": "runtime_harness", "state": "hypothesis"}],
                "runtime_artifact_contract_mismatch": {
                    "failure_class": "runtime_artifact_contract_mismatch",
                    "required_next_probe": "compare artifact ABI/ISA/endianness/entrypoint",
                },
            }
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    frontier_section = next(section for section in sections if section.id == "implement_v2_hard_runtime_frontier_state")
    lane_state = next(section for section in sections if section.id == "implement_v2_lane_state")

    assert "implement_v2_hard_runtime_profile" not in by_id
    assert by_id["implement_v2_hard_runtime_frontier_state"]["cache_hint"] == "dynamic"
    assert "lane_hard_runtime_frontier" not in lane_state.content
    assert "runtime_artifact_contract_mismatch" not in lane_state.content
    assert "preserve source-backed artifact proof" in frontier_section.content
    assert "vm.js" in frontier_section.content
    assert "runtime_artifact_contract_mismatch" in frontier_section.content
    assert "artifact ABI/ISA/endianness/entrypoint" in frontier_section.content
    assert len(frontier_section.content) <= 1536


def test_implement_v2_prompt_omits_hard_runtime_profile_for_simple_task() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Update the README wording and run markdown checks."},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)

    assert "implement_v2_hard_runtime_profile" not in {section.id for section in sections}
    assert "implement_v2_hard_runtime_frontier_state" not in {section.id for section in sections}


def test_implement_v2_prompt_read_only_mode_does_not_surface_exec_or_write_tools() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "read_only"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    tool_surface = next(section for section in sections if section.id == "implement_v2_tool_surface")

    assert "read_file" in tool_surface.content
    assert "search_text" in tool_surface.content
    assert "glob" in tool_surface.content
    assert "git_status" in tool_surface.content
    assert "finish" in tool_surface.content
    assert "run_command" not in tool_surface.content
    assert "write_file" not in tool_surface.content
    assert "apply_patch" not in tool_surface.content


def test_implement_v2_bypass_mode_fails_closed_until_explicit_policy_exists() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("bypass")}

    assert tools == {"inspect_dir", "read_file", "search_text", "glob", "git_status", "git_diff", "finish"}


def test_implement_v2_exec_mode_surfaces_lifecycle_tools() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("exec")}

    assert {"run_command", "run_tests", "poll_command", "cancel_command", "read_command_output"} <= tools
    assert "write_file" not in tools


def test_implement_v2_write_mode_surfaces_write_tools() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("write")}

    assert {"write_file", "edit_file", "apply_patch"} <= tools
    assert {"read_file", "finish"} <= tools
    assert "run_command" not in tools


def test_implement_v2_read_only_fake_runtime_can_inspect_workspace_and_finish_analysis(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def target():\n    return 'ok'\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "inspect_dir", "arguments": {"path": "."}},
            {"provider_call_id": "call-2", "tool_name": "read_file", "arguments": {"path": "src/main.py"}},
            {"provider_call_id": "call-3", "tool_name": "search_text", "arguments": {"query": "target", "path": "."}},
            {"provider_call_id": "call-4", "tool_name": "glob", "arguments": {"pattern": "**/*.py", "path": "."}},
        ),
        finish_arguments={
            "outcome": "analysis_ready",
            "kind": "diagnosis",
            "summary": "target function inspected",
            "open_questions": ["none"],
            "proposed_next_actions": ["run tests in a later write-capable phase"],
        },
    )

    read_only_result = result.updated_lane_state["read_only_result"]
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["replay_valid"] is True
    assert read_only_result["kind"] == "diagnosis"
    assert any(path.endswith("src/main.py") for path in read_only_result["inspected_paths"])
    assert [event.kind for event in result.transcript].count("tool_call") == 4
    assert manifest["lane"] == IMPLEMENT_V2_LANE
    assert len(manifest["tool_calls"]) == 4
    assert len(manifest["tool_results"]) == 4


def test_implement_v2_search_text_treats_lone_pattern_as_query_alias(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("void DG_DrawFrame(void) {}\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "search_text",
                "arguments": {"path": ".", "pattern": "DG_DrawFrame"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "search evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert any("DG_DrawFrame" in match for match in tool_result["content"][0]["matches"])


def test_implement_v2_read_only_finish_cannot_claim_completed(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},),
        finish_arguments={"outcome": "task_complete", "summary": "done"},
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.next_reentry_hint["analysis_ready_is_completion"] is False
    assert result.user_visible_summary.startswith("implement_v2 read-only attempt ended with status=blocked:")


def test_implement_v2_read_only_rejects_path_traversal_and_pairs_error(tmp_path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "../outside-secret.txt"}},
            {"provider_call_id": "call-2", "tool_name": "write_file", "arguments": {"path": "README.md", "content": "mutate"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "errors inspected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    statuses = [item["status"] for item in manifest["tool_results"]]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert statuses == ["failed", "denied"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "hello\n"


def test_implement_v2_read_only_large_result_gets_content_ref(tmp_path) -> None:
    (tmp_path / "large.txt").write_text("x" * 20_000, encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "read_file",
                "arguments": {"path": "large.txt", "max_chars": 20_000},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "large file inspected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["content_refs"] == ["implement-v2-read://implement_v2:ws-1:task-1:read-only/call-1/content"]
    assert tool_result["content"][0]["mew_content_truncated"] is True


def test_implement_v2_read_only_git_tools_are_bounded_and_paired(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},
            {"provider_call_id": "call-2", "tool_name": "git_diff", "arguments": {"cwd": ".", "stat": True}},
        ),
        finish_arguments={"outcome": "analysis_ready", "kind": "plan", "summary": "git state inspected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "analysis_ready"
    assert result.metrics["replay_valid"] is True
    assert [tool_result["status"] for tool_result in manifest["tool_results"]] == ["completed", "completed"]
    assert manifest["tool_results"][1]["content"][0]["stat_forced"] is True
    assert "SECRET=1" not in str(manifest["tool_results"])
    assert result.updated_lane_state["read_only_result"]["kind"] == "plan"


def test_implement_v2_read_only_git_rejects_parent_repo_outside_allowed_root(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    workspace = tmp_path / "subdir"
    workspace.mkdir()

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(workspace),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "parent repo rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "git repository root is outside allowed read roots" in tool_result["content"][0]["reason"]


def test_implement_v2_read_only_git_nonzero_exit_blocks_analysis_ready(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "git_diff", "arguments": {"cwd": ".", "base": "missing-ref"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "invalid ref"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["content"][0]["exit_code"] != 0
    assert tool_result["content"][0]["reason"]


def test_implement_v2_read_only_git_timeout_still_pairs_result(tmp_path, monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=15)

    monkeypatch.setattr(read_runtime, "_run_git_probe", raise_timeout)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "git timeout"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["provider_call_id"] == "call-1"


def test_implement_v2_read_only_git_redacts_sensitive_rename_paths(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "mew"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "mew@example.invalid"], cwd=tmp_path, check=True)
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "mv", ".env", "public.env"], cwd=tmp_path, check=True)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "git status inspected"},
    )
    stdout = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["stdout"]

    assert "[sensitive path redacted]" in stdout
    assert ".env" not in stdout


def test_implement_v2_exec_short_command_finalizes_with_terminal_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "command evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["terminal_evidence_count"] == 1
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert "ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_accepts_cmd_alias(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('cmd-ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"cmd": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "command evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["command_source"] == "cmd"
    assert "cmd-ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_no_contract_does_not_inherit_task_artifact_checks(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('diagnostic-ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            task_contract={"expected_artifacts": [{"id": "artifact"}]},
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "diagnostic",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "diagnostic evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert payload["artifact_evidence"] == []
    assert "diagnostic-ok" in payload["stdout"]


def test_implement_v2_exec_probe_intent_downgrades_artifact_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('probe-ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "probe-with-overdeclared-contract",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "command_intent": "probe",
                    "execution_contract": {
                        "id": "contract:overdeclared-probe",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert payload["command_intent"] == "probe"
    assert payload["execution_contract_downgraded"] is True
    assert payload["execution_contract_normalized"]["acceptance_kind"] == "not_acceptance"
    assert payload["execution_contract_normalized"]["proof_role"] == "none"
    assert payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert payload["artifact_evidence"] == []
    assert "probe-ok" in payload["stdout"]


def test_implement_v2_exec_probe_intent_downgrade_survives_poll(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('probe-start', flush=True); time.sleep(0.2); print('probe-done', flush=True)",
        ]
    )
    lane_attempt_id = "implement_v2:ws-1:task-1:exec"
    command_run_id = _expected_command_run_id(
        lane_attempt_id=lane_attempt_id,
        provider_call_id="probe-yield",
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "probe-yield",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 0.01,
                    "command_intent": "probe",
                    "execution_contract": {
                        "id": "contract:overdeclared-probe-yield",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
            {
                "provider_call_id": "probe-poll",
                "tool_name": "poll_command",
                "arguments": {"command_run_id": command_run_id, "wait_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe evidence ready"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first_payload = manifest["tool_results"][0]["content"][0]
    poll_payload = manifest["tool_results"][1]["content"][0]

    assert manifest["tool_results"][0]["status"] == "yielded"
    assert manifest["tool_results"][1]["status"] == "completed"
    assert first_payload["execution_contract_downgraded"] is True
    assert poll_payload["execution_contract_downgraded"] is True
    assert poll_payload["execution_contract_normalized"]["acceptance_kind"] == "not_acceptance"
    assert poll_payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert poll_payload["artifact_evidence"] == []
    assert "execution_contract" not in first_payload
    assert "execution_contract" not in poll_payload


def test_implement_v2_exec_plain_intent_does_not_downgrade_verifier_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('verifier output without artifact')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "plain-intent-verifier",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "intent": "diagnostic",
                    "execution_contract": {
                        "id": "contract:plain-intent-verifier",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "verifier evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload.get("execution_contract_downgraded") is not True
    assert payload["execution_contract_normalized"]["acceptance_kind"] == "external_verifier"
    assert payload["execution_contract_normalized"]["expected_artifacts"]
    assert payload["artifact_evidence"][0]["status"] == "failed"


def test_implement_v2_exec_accepts_stdout_expected_artifact_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ELF 32-bit MSB executable')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "stdout-contract",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout",
                        "role": "diagnostic",
                        "stage": "diagnostic",
                        "purpose": "diagnostic",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "ELF"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    artifact = payload["execution_contract_normalized"]["expected_artifacts"][0]

    assert tool_result["status"] == "completed"
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert artifact["kind"] == "stdout"
    assert artifact["target"] == {"type": "stream", "stream": "stdout"}
    assert artifact["path"] == ""


def test_implement_v2_exec_diagnostic_stdout_miss_stays_observational(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('different diagnostic output')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "stdout-diagnostic",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout-diagnostic",
                        "role": "diagnostic",
                        "stage": "diagnostic",
                        "purpose": "diagnostic",
                        "acceptance_kind": "not_acceptance",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "TRACE syscall"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout diagnostic evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["structured_finish_gate"]["blocked"] is True
    assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_progress_diagnostic_stdout_miss_stays_observational(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('progress diagnostic output')"])

    cases = (
        {"acceptance_kind": "progress_only", "proof_role": "progress"},
        {"acceptance_kind": "progress_only", "proof_role": "negative_diagnostic"},
    )
    for index, contract_case in enumerate(cases, start=1):
        result = run_fake_exec_implement_v2(
            ImplementLaneInput(
                work_session_id=f"ws-{index}",
                task_id="task-1",
                workspace=str(tmp_path),
                lane=IMPLEMENT_V2_LANE,
                lane_config={"mode": "exec"},
            ),
            provider_calls=(
                {
                    "provider_call_id": f"stdout-progress-diagnostic-{index}",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "id": f"contract:stdout-progress-diagnostic:{index}",
                            "role": "diagnostic",
                            "stage": "diagnostic",
                            "purpose": "diagnostic",
                            "acceptance_kind": contract_case["acceptance_kind"],
                            "proof_role": contract_case["proof_role"],
                            "expected_artifacts": [
                                {
                                    "target": "stdout",
                                    "checks": [
                                        {"kind": "non_empty"},
                                        {"kind": "text_contains", "value": "TRACE syscall"},
                                    ],
                                }
                            ],
                        },
                    },
                },
            ),
            finish_arguments={"outcome": "analysis_ready", "summary": "progress diagnostic evidence ready"},
        )
        tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
        payload = tool_result["content"][0]

        assert tool_result["status"] == "completed"
        assert tool_result["is_error"] is False
        assert payload["artifact_evidence"][0]["status"] == "failed"
        assert payload["structured_finish_gate"]["blocked"] is True
        assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_diagnostic_external_verifier_stdout_miss_still_blocks(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('different verifier output')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "stdout-diagnostic-verifier",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout-diagnostic-verifier",
                        "role": "diagnostic",
                        "stage": "verification",
                        "purpose": "verification",
                        "acceptance_kind": "external_verifier",
                        "proof_role": "verifier",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "VERIFIER PASS"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout verifier evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert tool_result["is_error"] is True
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["structured_finish_gate"]["blocked"] is True
    assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_accepts_argv_argument(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "argv": [sys.executable, "-c", "print('argv-ok')"],
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 2,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["command_source"] == "argv"
    assert tool_result["content"][0]["execution_mode"] == "argv"
    assert "argv-ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_compound_command_auto_uses_shell(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": "echo first && echo second > marker.txt",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 2,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["execution_mode"] == "shell"
    assert "first" in tool_result["content"][0]["stdout"]
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8").strip() == "second"


def test_implement_v2_exec_nonzero_command_blocks_with_paired_failure(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import sys; print('bad-stdout'); print('bad-stderr', file=sys.stderr); sys.exit(7)",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "failed command evidence"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["is_error"] is True
    assert tool_result["content"][0]["exit_code"] == 7
    assert "bad-stdout" in tool_result["content"][0]["stdout_tail"]
    assert "bad-stderr" in tool_result["content"][0]["stderr_tail"]


def test_implement_v2_exec_timeout_is_interrupted_failure_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; time.sleep(5)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 1, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "timed out"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert tool_result["content"][0]["timed_out"] is True


def test_implement_v2_exec_yield_poll_and_read_output(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.2); print('done', flush=True)",
        ]
    )
    lane_attempt_id = "implement_v2:ws-1:task-1:exec"
    command_run_id = _expected_command_run_id(lane_attempt_id=lane_attempt_id, provider_call_id="call-1")
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "poll_command",
                "arguments": {"command_run_id": command_run_id, "wait_seconds": 1},
            },
            {
                "provider_call_id": "call-3",
                "tool_name": "read_command_output",
                "arguments": {"command_run_id": command_run_id},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "polled command evidence ready"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first = manifest["tool_results"][0]
    run_id = first["content"][0]["command_run_id"]
    poll_result = manifest["tool_results"][1]
    read_result = manifest["tool_results"][2]

    assert first["status"] == "yielded"
    assert run_id == command_run_id
    assert poll_result["status"] == "completed"
    assert poll_result["evidence_refs"]
    assert read_result["status"] == "completed"
    assert "done" in read_result["content"][0]["content"]
    assert result.status == "analysis_ready"
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_exec_attaches_structured_artifact_evidence(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-pass",
                "tool_name": "run_command",
                "arguments": {
                    "command": "printf artifact-ok > artifact.txt",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:artifact-pass",
                        "role": "build",
                        "stage": "build",
                        "purpose": "build",
                        "proof_role": "target_build",
                        "acceptance_kind": "candidate_artifact_proof",
                        "expected_artifacts": [
                            {
                                "id": "artifact",
                                "kind": "file",
                                "path": "artifact.txt",
                                "freshness": "created_after_run_start",
                                "checks": [
                                    {"type": "exists", "severity": "blocking"},
                                    {"type": "text_contains", "text": "artifact-ok", "severity": "blocking"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    side_effect_kinds = {effect["kind"] for effect in tool_result["side_effects"]}

    assert tool_result["status"] == "completed"
    assert "implement-v2-evidence://" in " ".join(tool_result["evidence_refs"])
    assert payload["command_run"]["command_run_id"] == payload["tool_run_record"]["command_run_id"]
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert payload["verifier_evidence"]["verdict"] == "pass"
    assert payload["structured_finish_gate"]["blocked"] is False
    assert {
        "command_run",
        "tool_run_record",
        "artifact_evidence",
        "verifier_evidence",
        "failure_classification",
        "structured_finish_gate",
    } <= side_effect_kinds


def test_implement_v2_finish_gate_projects_prior_source_grounding_into_structured_finish(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source = source_dir / "source.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    outputs = [
        {
            "summary": "ground provided source before runtime proof",
            "tool_calls": [{"id": "read-source", "name": "read_file", "arguments": {"path": "src/source.c"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "final verifier proves the runtime artifact",
            "tool_calls": [
                {
                    "id": "final-runtime-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'FRAME_QUALITY_OK\\n' > frame.bmp",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "id": "contract:runtime-artifact",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [
                                        {"type": "exists", "severity": "blocking"},
                                        {"type": "text_contains", "text": "FRAME_QUALITY_OK", "severity": "blocking"},
                                    ],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "completed", "summary": "runtime artifact verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided src/source.c, the corresponding source code. "
                    "Build the source-backed runtime artifact so it writes frame.bmp."
                ),
                "final_artifact": "frame.bmp",
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["finish_gate_block_count"] == 0
    assert (tmp_path / "frame.bmp").read_text(encoding="utf-8") == "FRAME_QUALITY_OK\n"


def test_implement_v2_typed_finish_refs_reserve_source_grounding_slots() -> None:
    early_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"early-{index}",
            mew_tool_call_id=f"tool-early-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:early-{index}",
                            "artifact_id": f"early-{index}",
                            "path": f"early-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"path": "src/source.c", "summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )
    final_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="final-proof",
        mew_tool_call_id="tool-final",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract_normalized": {
                    "id": "contract:runtime-artifact",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "expected_artifacts": [
                        {"id": "frame", "path": "frame.bmp", "required": True},
                    ],
                    "verifier_required": True,
                },
                "artifact_evidence": [
                    {
                        "evidence_id": "artifact-evidence:frame",
                        "artifact_id": "frame",
                        "path": "frame.bmp",
                        "contract_id": "contract:runtime-artifact",
                        "status": "passed",
                        "blocking": False,
                    }
                ],
                "verifier_evidence": {
                    "verifier_id": "verifier:runtime-artifact",
                    "contract_id": "contract:runtime-artifact",
                    "verdict": "pass",
                },
            },
        ),
    )

    refs = _typed_finish_evidence_refs(
        (*early_results, source_result, final_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    ref_ids = {str(ref.get("id") or "") for ref in refs}
    assert "ev:artifact:artifact-evidence:frame" in ref_ids
    assert "ev:verifier:verifier:runtime-artifact" in ref_ids
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert len(refs) <= 16


def test_implement_v2_typed_finish_refs_reserve_source_grounding_slots_in_fallback() -> None:
    early_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"early-{index}",
            mew_tool_call_id=f"tool-early-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:early-{index}",
                            "artifact_id": f"early-{index}",
                            "path": f"early-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )

    refs = _typed_finish_evidence_refs(
        (*early_results, source_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    ref_ids = {str(ref.get("id") or "") for ref in refs}
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert len(refs) <= 16


def test_implement_v2_finish_action_merges_typed_refs_into_existing_model_refs() -> None:
    stale_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"stale-{index}",
            mew_tool_call_id=f"tool-stale-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:stale-{index}",
                            "artifact_id": f"stale-{index}",
                            "path": f"stale-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"path": "src/source.c", "summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )
    final_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="final-proof",
        mew_tool_call_id="tool-final",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract_normalized": {
                    "id": "contract:runtime-artifact",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "expected_artifacts": [
                        {"id": "frame", "path": "frame.bmp", "required": True},
                    ],
                    "verifier_required": True,
                },
                "artifact_evidence": [
                    {
                        "evidence_id": "artifact-evidence:frame",
                        "artifact_id": "frame",
                        "path": "frame.bmp",
                        "contract_id": "contract:runtime-artifact",
                        "status": "passed",
                        "blocking": False,
                    }
                ],
                "verifier_evidence": {
                    "verifier_id": "verifier:runtime-artifact",
                    "contract_id": "contract:runtime-artifact",
                    "verdict": "pass",
                },
            },
        ),
    )

    action = _finish_acceptance_action(
        {
            "outcome": "completed",
            "summary": "done",
            "evidence_refs": [
                {"kind": "evidence_event", "id": f"ev:artifact:artifact-evidence:stale-{index}"}
                for index in range(20)
            ],
        },
        (*stale_results, source_result, final_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    refs = action["evidence_refs"]
    ref_ids = [str(ref.get("id") or "") for ref in refs if isinstance(ref, dict)]
    assert "ev:artifact:artifact-evidence:frame" in ref_ids
    assert "ev:verifier:verifier:runtime-artifact" in ref_ids
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert "ev:artifact:artifact-evidence:stale-0" in ref_ids
    assert ref_ids.index("ev:artifact:artifact-evidence:frame") < ref_ids.index("ev:artifact:artifact-evidence:stale-0")
    assert len(refs) <= 16


def test_implement_v2_exec_missing_expected_artifact_blocks_result(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-missing",
                "tool_name": "run_command",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "any"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame.bmp",
                                "freshness": "created_after_run_start",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence missing"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["exit_code"] == 0
    assert payload["tool_run_record"]["semantic_exit"]["ok"] is True
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["verifier_evidence"]["verdict"] == "fail"
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"
    assert payload["structured_finish_gate"]["blocked"] is True


def test_implement_v2_exec_blocks_runtime_advertised_artifact_path_mismatch(tmp_path) -> None:
    external_path = tmp_path / "external" / "frame.bmp"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-path-mismatch",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'Frames will be saved to {external_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "freshness": "created_after_run_start",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact path mismatch"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    artifact_paths = [item["path"] for item in payload["artifact_evidence"]]

    assert tool_result["status"] == "failed"
    assert str(external_path) in artifact_paths
    assert payload["runtime_advertised_expected_artifacts"][0]["path"] == str(external_path)
    assert payload["artifact_evidence"][0]["path"].endswith("frame_000000.bmp")
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert payload["artifact_evidence"][1]["path"] == str(external_path)
    assert payload["artifact_evidence"][1]["status"] == "failed"
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"
    assert payload["structured_finish_gate"]["blocked"] is True


def test_implement_v2_exec_ignores_unrelated_advertised_artifact_suffix(tmp_path) -> None:
    log_path = tmp_path / "logs" / "runtime.log"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-path-log",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'debug log written to {log_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact path log ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "frame_000000.bmp")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_ignores_nonproducer_report_output_path(tmp_path) -> None:
    report_path = tmp_path / "reports" / "result.json"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "nonproducer-report-path",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'pytest report output: {report_path}\\n'; "
                        "printf '{\"ok\": true}' > result.json"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-report",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "result",
                                "kind": "json",
                                "path": "result.json",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "report output path ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "result.json")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_ignores_printf_template_advertised_artifact_path(tmp_path) -> None:
    template_path = tmp_path / "frames" / "frame_%06d.bmp"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "template-artifact-path",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf '%s\\n' 'Frames will be saved to {template_path}'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact-template",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "template path ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "frame_000000.bmp")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_blocks_stale_runtime_advertised_artifact(tmp_path) -> None:
    external_path = tmp_path / "external" / "frame.bmp"
    external_path.parent.mkdir()
    external_path.write_text("stale", encoding="utf-8")
    time.sleep(0.01)
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "stale-advertised-artifact",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'Frames will be saved to {external_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stale artifact path blocked"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    advertised = payload["artifact_evidence"][1]
    mtime_check = [check for check in advertised["checks"] if check["type"] == "mtime_after"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "failed"
    assert advertised["path"] == str(external_path)
    assert advertised["status"] == "failed"
    assert mtime_check["passed"] is False
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"


def test_implement_v2_provider_history_surfaces_structured_evidence_summary(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-missing",
                "tool_name": "run_command",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "any"},
                        "expected_artifacts": [{"id": "frame", "kind": "file", "path": "frame.bmp"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence missing"},
    )
    tool_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="artifact-missing",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"]),
        content_refs=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["content_refs"]),
        evidence_refs=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]),
        side_effects=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["side_effects"]),
    )

    history = _provider_visible_tool_result_for_history(tool_result)
    projected = history["content"]["content"][0]

    assert projected["latest_failure"]["class"] == "runtime_artifact_missing"
    assert projected["latest_failure"]["required_next_action"]
    assert projected["execution_evidence_digest"]["artifact_miss"][0]["artifact_id"] == "frame"
    assert projected["execution_evidence_digest"]["structured_finish_gate"]["blocked"] is True
    assert "structured_execution_evidence" not in projected
    assert "evidence_refs" not in projected["execution_evidence_digest"]["structured_finish_gate"]
    assert "stdout_stderr_body_omitted" not in projected["execution_evidence_digest"]


def test_implement_v2_prompt_history_keeps_only_latest_same_family_failure() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "first failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-1",
                                "output_ref": "out-1",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "old artifact miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "newer failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-2",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-2",
                                "output_ref": "out-2",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "new artifact miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    first_item = rendered[0]["tool_results"][0]["content"]["content"][0]
    second_item = rendered[1]["tool_results"][0]["content"]["content"][0]

    assert first_item["provider_history_projection"] == "terminal_result_replaced_by_latest_failure_v1"
    assert first_item["latest_failure_family"] == "runtime_artifact_missing:missing_artifact:artifact:frame:/tmp/frame.bmp"
    assert first_item["output_ref"] == "out-1"
    assert "latest_failure" not in first_item
    assert second_item["latest_failure"]["summary"] == "new artifact miss"
    assert prompt_history[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"] == "old artifact miss"


def test_implement_v2_prompt_history_keeps_different_artifact_failures() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "first artifact",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "frame miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "second artifact",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-2",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "log miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "log", "path": "/tmp/run.log"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))

    assert rendered[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"] == "frame miss"
    assert rendered[1]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"] == "log miss"


def test_implement_v2_exec_contract_accepted_nonzero_exit_can_complete(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "accepted-nonzero",
                "tool_name": "run_command",
                "arguments": {
                    "command": "exit 4",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:accepted-nonzero",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "code_set", "codes": [4]},
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "nonzero accepted"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["status"] == "failed"
    assert payload["tool_run_record"]["status"] == "failed"
    assert payload["tool_run_record"]["semantic_exit"]["ok"] is True
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_lifecycle_can_use_known_command_run_id(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    lane_attempt_id = "lane-v2-exec"
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path))
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.2); print('done', flush=True)",
        ]
    )
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
        ),
    )[0]
    start_result = runtime.execute(start_call)
    run_id = start_result.content[0]["command_run_id"]
    poll_call, read_call = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=2,
        calls=(
            {"provider_call_id": "call-2", "tool_name": "poll_command", "arguments": {"command_run_id": run_id, "wait_seconds": 1}},
            {"provider_call_id": "call-3", "tool_name": "read_command_output", "arguments": {"command_run_id": run_id}},
        ),
    )

    poll_result = runtime.execute(poll_call)
    read_result = runtime.execute(read_call)

    assert start_result.status == "yielded"
    assert poll_result.status == "completed"
    assert poll_result.evidence_refs
    assert "done" in poll_result.content[0]["stdout"]
    assert read_result.status == "completed"
    assert "done" in read_result.content[0]["content"]


def test_implement_v2_live_json_auto_polls_yielded_verifier_without_extra_model_turn(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 1,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert tool_result["status"] == "completed"
    assert payload["status"] == "completed"
    assert "done" in payload["stdout"]


def test_implement_v2_live_json_auto_poll_cancels_nonterminal_verifier_without_extra_model_turn(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(5); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run long verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert result.metrics["orphaned_command_cleanup_count"] == 0
    assert tool_result["status"] == "interrupted"
    assert payload["status"] == "killed"
    assert payload["reason"] == "implement_v2 verifier auto-poll budget exhausted before terminal evidence"
    assert payload["command_run_id"]


def test_implement_v2_live_json_does_not_auto_poll_plain_runtime_expected_exit(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start runtime command",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "run",
                            "purpose": "generic runtime command",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "runtime started"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 1,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.metrics["active_command_auto_poll_count"] == 0
    assert result.metrics["command_closeout_count"] == 1


def test_implement_v2_exec_warns_when_shell_masks_missing_probe_tool(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime, _component_command_warnings
    from mew.implement_lane.provider import FakeProviderAdapter

    source_warning = _component_command_warnings(
        {"command": "rg --files || true", "exit_code": 0, "stderr": "zsh:1: command not found: rg\n"}
    )[0]
    assert source_warning["failure_subclass"] == "source_frontier_probe_unavailable"
    assert "source frontier as incomplete" in source_warning["recommended_next_action"]
    sh_warning = _component_command_warnings(
        {"command": "rg --files || true", "exit_code": 0, "stderr": "/bin/sh: 1: rg: not found\n"}
    )[0]
    assert sh_warning["tool"] == "rg"
    assert sh_warning["failure_subclass"] == "source_frontier_probe_unavailable"
    assert (
        _component_command_warnings(
            {"command": "grep -R 'command not found: rg' . || true", "exit_code": 0, "stdout": "file.txt:command not found: rg\n"}
        )
        == []
    )

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path))
    missing_tool = "rg_missing_for_mew_test_zz"
    call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": f"{missing_tool} --files || true",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
    )[0]

    result = runtime.execute(call)
    payload = result.content[0]
    visible = _provider_visible_tool_result_for_history(result)
    projected = visible["content"]["content"][0]

    assert result.status == "completed"
    assert payload["exit_code"] == 0
    assert payload["component_warnings"][0]["failure_class"] == "tool_availability_gap"
    assert payload["component_warnings"][0]["failure_subclass"] == "command_component_unavailable"
    assert payload["component_warnings"][0]["tool"] == missing_tool
    assert payload["component_warnings"][0]["masked_by_success_exit"] is True
    assert payload["component_warnings"][0]["command_had_shell_recovery"] is True
    assert projected["component_warnings"][0]["recommended_next_action"]
    assert projected["latest_failure"]["class"] == "tool_availability_gap"
    assert projected["latest_failure"]["required_next_action"]


def test_implement_v2_exec_rejects_concurrent_side_effecting_command(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join([sys.executable, "-c", "import time; time.sleep(1)"])
    first_call, second_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
        ),
    )

    try:
        first = runtime.execute(first_call)
        second = runtime.execute(second_call)
    finally:
        runtime.runner.cancel("test cleanup")

    assert first.status == "yielded"
    assert second.status == "failed"
    assert "managed command is already running" in second.content[0]["reason"]


def test_implement_v2_exec_cancel_yielded_command_is_interrupted(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"])
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 10, "foreground_budget_seconds": 0.01},
            },
        ),
    )[0]
    start_result = runtime.execute(start_call)
    run_id = start_result.content[0]["command_run_id"]
    cancel_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=2,
        calls=({"provider_call_id": "call-2", "tool_name": "cancel_command", "arguments": {"command_run_id": run_id}},),
    )[0]

    cancel_result = runtime.execute(cancel_call)

    assert start_result.status == "yielded"
    assert cancel_result.status == "interrupted"
    assert cancel_result.is_error is True


def test_implement_v2_exec_rejects_resident_mew_loop_command(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": "./mew work --ai", "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "resident loop rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in tool_result["content"][0]["reason"]


def test_implement_v2_exec_rejects_shell_segment_resident_mew_loop_command(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": "echo ok && ./mew work --ai",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "resident loop rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in tool_result["content"][0]["reason"]


def test_implement_v2_run_tests_rejects_shell_orchestration(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "echo ok && echo verify",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    payload = tool_result["content"][0]
    assert "run_tests executes one argv command without a shell" in payload["reason"]
    assert payload["kind"] == "run_tests_shell_surface"
    assert payload["failure_class"] == "tool_contract_misuse"
    assert payload["failure_subclass"] == "run_tests_shell_surface"
    assert payload["tool_contract_recovery_eligible"] is True
    assert payload["terminal_failure_reaction_eligible"] is False
    assert payload["suggested_tool"] == "run_command"
    assert payload["suggested_use_shell"] is True
    assert set(payload["features"]) >= {"use_shell", "and_or"}


def test_implement_v2_run_tests_shell_orchestration_routes_to_run_command_when_shell_allowed(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "printf routed > routed.txt && test \"$(cat routed.txt)\" = routed",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell verifier routed"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.metrics["replay_valid"] is True
    assert manifest["tool_calls"][0]["tool_name"] == "run_tests"
    assert tool_result["tool_name"] == "run_tests"
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert payload["tool_name"] == "run_tests"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["execution_mode"] == "shell"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"
    assert payload["tool_contract_recovery"]["preserved_command_hash"].startswith("sha256:")
    assert (tmp_path / "routed.txt").read_text(encoding="utf-8") == "routed"


def test_implement_v2_routed_run_tests_shell_failure_preserves_terminal_failure(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "printf routed-fail >&2; exit 3",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell verifier routed and failed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"
    assert payload["exit_code"] == 3
    assert "routed-fail" in payload["stderr"]


def test_implement_v2_routed_run_tests_yielded_closeout_preserves_recovery_metadata(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time, pathlib; time.sleep(2); pathlib.Path('late.txt').write_text('late')",
        ]
    )
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": f"{command} && test -f late.txt",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 0,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "yielded shell verifier routed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "interrupted"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"


def test_implement_v2_live_json_does_not_route_run_tests_when_run_command_unavailable_for_mode(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "write mode should not execute verifier",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf routed > routed.txt && test -f routed.txt",
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "do not run verifier in write mode"},
            lane_config={
                "mode": "write",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "invalid"
    assert "not available in implement_v2 write mode" in payload["reason"]
    assert not (tmp_path / "routed.txt").exists()


def test_implement_v2_run_tests_simple_argv_command_still_runs(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": shlex.join([sys.executable, "-c", "print('ok')"]),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv test ran"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["execution_mode"] == "argv"
    assert "ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_run_tests_allows_quoted_shell_metacharacters(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": shlex.join([sys.executable, "-c", "print('a|b && c > d')"]),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "quoted shell chars are argv data"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "a|b && c > d" in tool_result["content"][0]["stdout"]


def test_implement_v2_run_tests_rejects_explicit_shell_interpreter(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "bash -lc 'echo ok && echo verify'",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    payload = tool_result["content"][0]
    assert "run_tests executes one argv command without a shell" in payload["reason"]
    assert payload["failure_class"] == "tool_contract_misuse"
    assert payload["failure_subclass"] == "run_tests_shell_surface"
    assert "explicit_shell_interpreter" in payload["features"]


def test_implement_v2_run_tests_rejects_shell_interpreter_argv(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "argv": ["bash", "-lc", "echo ok && echo verify"],
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload["failure_class"] == "tool_contract_misuse"
    assert "explicit_shell_interpreter" in payload["features"]


def test_implement_v2_run_tests_rejects_background_redirect_and_env_split_shell(tmp_path) -> None:
    cases = (
        ("python -m pytest &", "background"),
        ("python -m pytest > out.txt", "redirect"),
        ("printf ok | wc -c", "pipe"),
        ("printf ok || echo fallback", "and_or"),
        ("cat <<EOF\nok\nEOF", "heredoc"),
        ("python -m pytest\npython -m unittest", "newline"),
        ("env -S 'bash -lc echo-ok'", "explicit_shell_interpreter"),
    )
    for index, (command, expected_feature) in enumerate(cases, start=1):
        result = run_fake_exec_implement_v2(
            ImplementLaneInput(
                work_session_id=f"ws-{index}",
                task_id="task-1",
                workspace=str(tmp_path),
                lane=IMPLEMENT_V2_LANE,
                lane_config={"mode": "exec"},
            ),
            provider_calls=(
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_tests",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ),
            finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
        )
        tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

        assert result.status == "blocked"
        assert tool_result["status"] == "failed"
        payload = tool_result["content"][0]
        assert "run_tests executes one argv command without a shell" in payload["reason"]
        assert payload["failure_class"] == "tool_contract_misuse"
        assert payload["failure_subclass"] == "run_tests_shell_surface"
        assert payload["terminal_failure_reaction_eligible"] is False
        assert expected_feature in payload["features"]


def test_implement_v2_run_tests_resident_mew_loop_rejection_wins_before_tool_contract_payload(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "./mew work --ai && echo ok",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "resident loop rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in payload["reason"]
    assert "failure_class" not in payload


def test_implement_v2_frontier_drops_fabricated_refs_and_keeps_valid_refs(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "probe source frontier",
            "frontier_state_update": {
                "status": "active",
                "objective": "build source-backed artifact",
                "source_roles": [
                    {
                        "path": "doomgeneric_img.c",
                        "role": "primary_source",
                        "state": "grounded",
                        "evidence_refs": [
                            {"kind": "provider_call", "id": "probe-1"},
                            {"kind": "provider_call", "id": "fabricated"},
                        ],
                    },
                    {
                        "path": "fake.c",
                        "role": "primary_source",
                        "state": "grounded",
                        "evidence_refs": [{"kind": "command_run", "id": "missing-run"}],
                    },
                ],
            },
            "tool_calls": [
                {
                    "id": "probe-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf source-ok",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    by_path = {item["path"]: item for item in frontier["source_roles"]}

    assert frontier["schema_version"] == 1
    assert by_path["doomgeneric_img.c"]["state"] == "grounded"
    assert by_path["doomgeneric_img.c"]["evidence_refs"] == [{"kind": "provider_call", "id": "probe-1"}]
    assert by_path["fake.c"]["state"] == "hypothesis"
    assert by_path["fake.c"].get("evidence_refs", []) == []


def test_implement_v2_frontier_runtime_failure_overrides_model_claim(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = "import sys; sys.stderr.write('real linker error\\n'); sys.exit(2)"
        return {
            "summary": "build fails",
            "frontier_state_update": {
                "latest_build_failure": {
                    "command_run_id": "fabricated",
                    "exit_code": 99,
                    "stderr_tail": "fake failure",
                    "failure_summary": "fake",
                }
            },
            "tool_calls": [
                {
                    "id": "build-1",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "builder",
                            "target": "doomgeneric_mips",
                            "expected_artifact": {"path": "build/doomgeneric_mips", "kind": "executable"},
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "build failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    failure = result.updated_lane_state["lane_hard_runtime_frontier"]["latest_build_failure"]

    assert failure["command_run_id"] != "fabricated"
    assert "build-1" in failure["command_run_id"]
    assert failure["exit_code"] == 2
    assert "real linker error" in failure["stderr_tail"]
    assert result.updated_lane_state["lane_hard_runtime_frontier"]["build_target"]["target"] == "doomgeneric_mips"
    assert result.updated_lane_state["lane_hard_runtime_frontier"]["final_artifact"]["path"] == "build/doomgeneric_mips"


def test_implement_v2_frontier_demotes_marker_only_runtime_artifact_contract_mismatch(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('ELF Header: Data: 2\\'s complement, big endian'); "
            "print('Machine: MIPS R3000'); "
            "print('vm.js uses readUInt32LE for instruction fetch'); "
            "print('Execution error at PC=0x4002e8: Unknown opcode: 0x10'); "
            "sys.exit(1)"
        )
        return {
            "summary": "runtime artifact contract mismatch",
            "tool_calls": [
                {
                    "id": "vm-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "VM rejected the binary artifact"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    failure = frontier["latest_runtime_failure"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert failure["failure_class"] == "runtime_failure"
    assert failure["failure_confidence"] == "low"
    assert failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "Unknown opcode" in failure["stdout_tail"]
    assert "expected_artifacts" in failure["required_next_probe"]


def test_implement_v2_frontier_normalized_role_wins_over_raw_build_text(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = "import sys; sys.stderr.write('runtime failure after build-looking contract\\n'); sys.exit(2)"
        return {
            "summary": "runtime role should win over build-looking raw fields",
            "tool_calls": [
                {
                    "id": "runtime-role-build-text",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-role-build-text",
                            "role": "runtime",
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "target": "build/link/runtime artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime contract failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Build source for vm.js and run the runtime verifier so it writes /tmp/frame.bmp."
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "latest_build_failure" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_failure"


def test_implement_v2_frontier_does_not_classify_runtime_mismatch_from_command_text_only(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "diagnostic probe had search markers only in the command text",
            "tool_calls": [
                {
                    "id": "vm-marker-grep",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'no vm mismatch found\\n'; false # Unknown opcode readUInt32LE ELF",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "diagnostic",
                            "stage": "debug",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "diagnostic probe failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert frontier["latest_runtime_failure"]["failure_summary"] == "no vm mismatch found"


def test_implement_v2_frontier_classifies_observed_vm_timeout_as_runtime_failure(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('PATCHED vm.js JALR decode variables'); "
            "print('VM_RC=124'); "
            "print('--- vm stdout tail ---'); "
            "sys.exit(1)"
        )
        return {
            "summary": "compound build plus runtime verifier timed out",
            "tool_calls": [
                {
                    "id": "rebuild-and-vm-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all completed\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "VM timed out before artifact production"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert "latest_build_failure" not in frontier
    assert runtime_failure["failure_class"] == "runtime_failure"
    assert runtime_failure["failure_confidence"] == "low"
    assert runtime_failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "VM_RC=124" in runtime_failure["stdout_tail"]
    assert "expected_artifacts" in runtime_failure["required_next_probe"]


def test_implement_v2_frontier_classifies_observed_runtime_missing_artifact_over_build_text(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('=== link completed ==='); "
            "print('=== fresh vm verification ==='); "
            "print('vm_rc=0'); "
            "print('Program terminated at PC=0x0'); "
            "print('Executed 9 instructions'); "
            "print('NO_FRAME'); "
            "sys.stderr.write('linker warning: mixed ABI objects\\n'); "
            "sys.exit(4)"
        )
        return {
            "summary": "compound build plus runtime verifier produced no output artifact",
            "tool_calls": [
                {
                    "id": "rebuild-and-vm-no-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all completed\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "repair, build, link, and verification",
                            "stage": "build+verification",
                            "proof_role": "runtime",
                            "target": "runtime artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime exited without the required artifact"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert "latest_build_failure" not in frontier
    assert runtime_failure["failure_class"] == "unknown_failure"
    assert runtime_failure["failure_confidence"] == "low"
    assert runtime_failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "NO_FRAME" in runtime_failure["stdout_tail"]
    assert "structured execution_contract" in runtime_failure["required_next_probe"]


def test_implement_v2_frontier_prefers_structured_missing_runtime_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier exited without producing declared artifact",
            "tool_calls": [
                {
                    "id": "structured-runtime-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'runtime ended normally without markers\\n'",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:structured-runtime-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    runtime_failure = result.updated_lane_state["lane_hard_runtime_frontier"]["latest_runtime_failure"]

    assert runtime_failure["failure_class"] == "runtime_artifact_missing"
    assert runtime_failure["failure_kind"] == "missing_artifact"
    assert "NO_FRAME" not in runtime_failure["stdout_tail"]
    assert "producing substep" in runtime_failure["required_next_probe"]


def test_implement_v2_frontier_diagnostic_stream_miss_does_not_replace_runtime_failure(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier failed, then a diagnostic stream probe missed its marker",
            "tool_calls": [
                {
                    "id": "runtime-frame-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'vm failed before frame\\n'; exit 1",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-frame-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
                {
                    "id": "diagnostic-marker-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'diagnostic output without marker\\n'",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:diagnostic-marker-missing",
                            "role": "diagnostic",
                            "stage": "diagnostic",
                            "purpose": "diagnostic",
                            "acceptance_kind": "not_acceptance",
                            "expected_artifacts": [
                                {
                                    "target": "stdout",
                                    "checks": [
                                        {"kind": "non_empty"},
                                        {"kind": "text_contains", "value": "TRACE syscall"},
                                    ],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert frontier["final_artifact"]["path"].endswith("frame.bmp")
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"
    assert "latest_build_failure" not in frontier


def test_implement_v2_frontier_closeout_kill_preserves_prior_runtime_failure(tmp_path) -> None:
    calls = {"count": 0}
    long_command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(5)",
        ]
    )

    def frame_contract() -> dict[str, object]:
        return {
            "id": "contract:runtime-frame",
            "role": "runtime",
            "stage": "verification",
            "purpose": "verification",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "expected_exit": 0,
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "path": "frame.bmp",
                    "checks": [{"type": "exists", "severity": "blocking"}],
                }
            ],
        }

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "summary": "record the actionable runtime artifact miss",
                "tool_calls": [
                    {
                        "id": "runtime-frame-missing",
                        "name": "run_command",
                        "arguments": {
                            "command": "printf 'NO_FRAME\\n'; exit 1",
                            "cwd": ".",
                            "use_shell": True,
                            "timeout": 5,
                            "execution_contract": frame_contract(),
                        },
                    }
                ],
                "finish": {"outcome": "continue", "summary": "repair frame artifact"},
            }
        return {
            "summary": "start a final verifier that cannot close out usefully",
            "tool_calls": [
                {
                    "id": "final-verifier-yield",
                    "name": "run_command",
                    "arguments": {
                        "command": long_command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": frame_contract(),
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "wait for final verifier"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp.", "max_wall_seconds": 600},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "active_command_auto_poll_seconds": 0,
                "command_closeout_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert result.metrics["orphaned_command_cleanup_count"] == 1
    assert runtime_failure["failure_class"] == "runtime_artifact_missing"
    assert runtime_failure["failure_kind"] == "missing_artifact"
    assert "NO_FRAME" in runtime_failure["stdout_tail"]
    assert "killed" not in runtime_failure["failure_summary"]
    assert "latest_build_failure" not in frontier


def test_implement_v2_frontier_final_artifact_uses_blocking_runtime_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier produced logs and binary but missed final frame",
            "tool_calls": [
                {
                    "id": "runtime-multi-artifact",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'VERIFY START\\n' > verify.log\n"
                            "printf 'binary' > doomgeneric_mips\n"
                            "printf 'VM_RC=0\\nProgram terminated at PC=0x0\\nExecuted 34 instructions\\n' > vm.log\n"
                            "printf 'VM_RC=0\\nProgram terminated at PC=0x0\\nExecuted 34 instructions\\nBMP_MISSING\\n'\n"
                            "exit 1"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-multi-artifact",
                            "role": "generated_artifact",
                            "stage": "verification",
                            "purpose": "build and verify runtime artifact",
                            "proof_role": "final_verifier",
                            "acceptance_kind": "artifact_and_runtime_verification",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "verify.log", "checks": [{"kind": "exists"}]},
                                {"path": "doomgeneric_mips", "checks": [{"kind": "exists"}]},
                                {"path": "vm.log", "checks": [{"kind": "exists"}]},
                                {"path": "frame.bmp", "checks": [{"kind": "exists"}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "frame artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run a VM verifier that must produce frame.bmp."},
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "latest_build_failure": {"failure_summary": "stale broad rebuild failure"}
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert frontier["final_artifact"]["path"].endswith("/frame.bmp")
    assert frontier["final_artifact"]["blocking"] is True
    assert "latest_build_failure" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"
    assert "BMP_MISSING" in frontier["latest_runtime_failure"]["stdout_tail"]


def test_implement_v2_frontier_marker_only_without_contract_is_audit_only() -> None:
    failure = _frontier_failure_payload(
        {
            "command_run_id": "marker-only",
            "exit_code": 1,
            "stdout_tail": "VM_RC=124\nNO_FRAME\n",
            "stderr_tail": "",
        }
    )
    marker = failure["legacy_runtime_marker_fallback"]

    assert "failure_class" not in failure
    assert marker["kind"] == "runtime_execution_timeout"
    assert marker["active"] is False
    assert marker["confidence"] == "low"


def test_implement_v2_frontier_drops_stale_runtime_mismatch_key_after_contract_evidence(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "structured runtime verifier exited without producing declared artifact",
            "tool_calls": [
                {
                    "id": "structured-runtime-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:structured-runtime-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "runtime_artifact_contract_mismatch": {
                        "failure_class": "runtime_artifact_contract_mismatch",
                        "failure_summary": "stale marker bridge",
                    }
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"


def test_implement_v2_frontier_update_can_infer_same_turn_expected_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact then run verifier",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {
                    "id": "runtime-from-frontier",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "frontier artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert payload["artifact_evidence"][0]["artifact_id"] == "frame.bmp"
    assert payload["artifact_evidence"][0]["source"] == "runtime_inferred"
    assert tool_result["status"] == "failed"
    assert result.updated_lane_state["lane_hard_runtime_frontier"]["latest_runtime_failure"]["failure_class"] == (
        "artifact_validation_failure"
    )
    assert "latest_build_failure" not in result.updated_lane_state["lane_hard_runtime_frontier"]


def test_implement_v2_frontier_update_can_infer_with_read_only_evidence_plus_single_no_contract_exec(tmp_path) -> None:
    (tmp_path / "README.md").write_text("frame target\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact and read context before verifier",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {"id": "read-context", "name": "read_file", "arguments": {"path": "README.md"}},
                {
                    "id": "runtime-from-frontier",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {},
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "frontier artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    exec_payload = result.updated_lane_state["proof_manifest"]["tool_results"][1]["content"][0]

    assert exec_payload["artifact_evidence"][0]["artifact_id"] == "frame.bmp"
    assert exec_payload["execution_contract_normalized"]["expected_artifacts"][0]["path"] == "frame.bmp"


def test_implement_v2_frontier_update_does_not_infer_artifact_for_mixed_no_contract_exec_turn(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact but run mixed diagnostics",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {
                    "id": "diagnostic-one",
                    "name": "run_command",
                    "arguments": {"command": "true", "cwd": ".", "use_shell": True, "timeout": 5},
                },
                {
                    "id": "diagnostic-two",
                    "name": "run_command",
                    "arguments": {"command": "true", "cwd": ".", "use_shell": True, "timeout": 5},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "need more evidence"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    payloads = [item["content"][0] for item in result.updated_lane_state["proof_manifest"]["tool_results"]]

    assert [payload["artifact_evidence"] for payload in payloads] == [[], []]
    assert all(payload["execution_contract_normalized"]["expected_artifacts"] == [] for payload in payloads)


def test_implement_v2_frontier_does_not_classify_build_artifact_missing_as_runtime(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('Executed 7 build steps'); "
            "print('required build artifact was not created'); "
            "sys.stderr.write('link failed before binary existed\\n'); "
            "sys.exit(2)"
        )
        return {
            "summary": "build artifact missing before runtime",
            "tool_calls": [
                {
                    "id": "build-artifact-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all started\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "builder",
                            "target": "compiled artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "build artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "latest_runtime_failure" not in frontier
    assert frontier["latest_build_failure"]["failure_summary"] == "link failed before binary existed"


def test_implement_v2_frontier_drops_model_only_latest_failures_and_prefix_artifact_refs(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "model only frontier",
            "frontier_state_update": {
                "latest_build_failure": {
                    "command_run_id": "fabricated",
                    "exit_code": 99,
                    "stderr_tail": "fake failure",
                },
                "source_roles": [
                    {
                        "path": "manifest",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "implement-lane/implement_v2/ws-1/task-1/proof-manifest.json",
                            }
                        ],
                    },
                    {
                        "path": "evil",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "implement-lane/implement_v2/ws-1/task-1_evil/proof-manifest.json",
                            }
                        ],
                    },
                    {
                        "path": "traversal",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "../implement-lane/implement_v2/ws-1/task-1/proof-manifest.json",
                            }
                        ],
                    },
                ],
            },
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    by_path = {item["path"]: item for item in frontier["source_roles"]}

    assert "latest_build_failure" not in frontier
    assert by_path["manifest"]["state"] == "grounded"
    assert by_path["manifest"]["evidence_refs"] == [
        {"kind": "proof_artifact", "path": "implement-lane/implement_v2/ws-1/task-1/proof-manifest.json"}
    ]
    assert by_path["evil"]["state"] == "hypothesis"
    assert by_path["evil"].get("evidence_refs", []) == []
    assert by_path["traversal"]["state"] == "hypothesis"
    assert by_path["traversal"].get("evidence_refs", []) == []


def test_implement_v2_frontier_tracks_routed_tool_contract_next_verifier(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "final verifier through wrong tool",
            "tool_calls": [
                {
                    "id": "verify-1",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf ok > frame.txt && test -s frame.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "candidate_final_proof",
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    next_verifier = result.updated_lane_state["lane_hard_runtime_frontier"]["next_verifier_shaped_command"]

    assert next_verifier["tool"] == "run_command"
    assert next_verifier["use_shell"] is True
    assert "printf ok > frame.txt" in next_verifier["command"]
    assert next_verifier["execution_contract"]["proof_role"] == "verifier"
    assert next_verifier["evidence_refs"]


def test_implement_v2_frontier_state_does_not_satisfy_finish_gate_without_terminal_evidence(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "claim from state only",
            "frontier_state_update": {
                "status": "resolved",
                "final_artifact": {
                    "path": "/tmp/frame.bmp",
                    "kind": "image",
                    "freshness": "fresh verifier-shaped command",
                    "evidence_refs": [{"kind": "evidence_ref", "ref": "fabricated"}],
                },
            },
            "finish": {
                "outcome": "completed",
                "summary": "state says artifact exists",
                "acceptance_evidence": ["frontier says frame exists"],
            },
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert result.status == "blocked"
    assert result.metrics["terminal_evidence_count"] == 0
    assert frontier["final_artifact"].get("evidence_refs", []) == []
    assert result.metrics["finish_gate_decision"]["decision"] != "allow_complete"


def test_implement_v2_exec_task_complete_claim_is_blocked_even_with_terminal_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "task_complete", "summary": "done"},
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_exec_without_explicit_mode_does_not_run_side_effects(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "must not run"},
    )

    assert result.status == "blocked"
    assert result.metrics["exec_mode_enabled"] is False
    assert result.metrics["tool_calls"] == 0
    assert not (tmp_path / "side_effect.txt").exists()


def test_implement_v2_exec_cleans_up_unpolled_yielded_command(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 10, "foreground_budget_seconds": 0.01},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "not enough evidence"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "interrupted"
    assert tool_result["is_error"] is True
    assert tool_result["content"][0]["status"] == "killed"
    assert result.metrics["terminal_evidence_count"] == 0
    assert result.metrics["orphaned_command_cleanup_count"] == 1


def test_implement_v2_exec_rejects_duplicate_provider_call_ids_before_side_effects(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "dup-call",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
            {
                "provider_call_id": "dup-call",
                "tool_name": "read_file",
                "arguments": {"path": "side_effect.txt"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "duplicate call ids rejected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "failed"
    assert result.metrics["replay_valid"] is False
    assert [tool_result["status"] for tool_result in manifest["tool_results"]] == ["invalid", "invalid"]
    assert "duplicate_provider_call_id:dup-call" in result.metrics["replay_errors"]
    assert not (tmp_path / "side_effect.txt").exists()


def test_implement_v2_write_file_dry_run_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "out.txt", "content": "ok\n", "create": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "dry run ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert tool_result["content"][0]["written"] is False
    assert tool_result["content_refs"]
    assert not target.exists()


def test_implement_v2_write_file_approved_apply_records_mutation_evidence(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "ok\n"
    assert result.metrics["write_evidence_count"] == 1
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is False
    assert tool_result["content"][0]["written"] is True
    assert tool_result["evidence_refs"]
    assert tool_result["content"][0]["approval_id"] == "approval-1"
    assert tool_result["side_effects"][0]["approval_status"] == "approved"
    assert tool_result["side_effects"][0]["approval_id"] == "approval-1"


def test_implement_v2_write_file_provider_self_approval_is_ignored(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                    "approval": {"status": "approved", "approval_id": "self-approved"},
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "provider self-approval ignored"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "denied"
    assert "provider-supplied approval arguments are ignored" in tool_result["content"][0]["reason"]
    assert not target.exists()


def test_implement_v2_write_file_denied_approval_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "denied",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write denied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "denied"
    assert tool_result["is_error"] is True
    assert not target.exists()


def test_implement_v2_write_mode_without_explicit_mode_does_not_mutate(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "allowed_write_roots": ["."],
                "approved_write_calls": [{"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"}],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "bad\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "must not run"},
    )

    assert result.status == "blocked"
    assert result.metrics["write_mode_enabled"] is False
    assert not (tmp_path / "out.txt").exists()


def test_implement_v2_write_rejects_paths_outside_allowed_write_roots(tmp_path) -> None:
    outside = tmp_path.parent / "outside.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": str(outside),
                    "content": "bad\n",
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "outside rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "outside allowed write roots" in tool_result["content"][0]["reason"]
    assert not outside.exists()


def test_implement_v2_edit_file_exact_old_dry_run_and_no_match_failure(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("alpha\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "alpha\n", "new": "beta\n"},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "missing\n", "new": "nope\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "edit preview"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "blocked"
    assert manifest["tool_results"][0]["status"] == "completed"
    assert manifest["tool_results"][0]["content"][0]["dry_run"] is True
    assert manifest["tool_results"][1]["status"] == "failed"
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_implement_v2_edit_file_accepts_common_string_aliases(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("alpha\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {
                    "path": "README.md",
                    "old_string": "alpha\n",
                    "new_string": "beta\n",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "edit preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert "beta" in tool_result["content"][0]["diff"]
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_implement_v2_edit_file_ambiguous_match_fails_closed(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("same\nsame\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "same\n", "new": "other\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "ambiguous"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "old text matched 2 times" in tool_result["content"][0]["reason"]
    assert target.read_text(encoding="utf-8") == "same\nsame\n"


def test_implement_v2_apply_patch_parse_failure_pairs_error(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": "*** End Patch\n"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "parse failure"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "must start with *** Begin Patch" in tool_result["content"][0]["reason"]


def test_implement_v2_apply_patch_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    apply = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True, "approval_status": "approved"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["dry_run"] is True
    assert apply.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "new\n"
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_accepts_redundant_matching_path(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"path": "README.md", "patch": patch},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert result.status == "analysis_ready"
    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"


def test_implement_v2_apply_patch_rejects_mismatched_redundant_path(tmp_path) -> None:
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"path": "OTHER.md", "patch": patch},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "path argument must match" in tool_result["content"][0]["reason"]


def test_implement_v2_apply_patch_denied_approval_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True, "approval_status": "rejected"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch denied"},
    )

    assert result.status == "blocked"
    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "denied"
    assert target.read_text(encoding="utf-8") == "old\n"


def test_implement_v2_apply_patch_add_file_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "new.txt"
    patch = "*** Begin Patch\n*** Add File: new.txt\n+hello\n+world\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["patch_operation"] == "add_file"
    assert not target.exists()

    apply = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert apply.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_add_file_rejects_existing_target(tmp_path) -> None:
    (tmp_path / "new.txt").write_text("existing\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Add File: new.txt\n+replacement\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "already exists" in tool_result["content"][0]["reason"]
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "existing\n"


def test_implement_v2_apply_patch_delete_file_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "old.txt"
    target.write_text("remove me\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Delete File: old.txt\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["patch_operation"] == "delete_file"
    assert target.exists()

    apply = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert apply.status == "analysis_ready"
    assert not target.exists()
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_delete_file_rejects_symlink_path(tmp_path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("keep me\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    patch = "*** Begin Patch\n*** Delete File: link.txt\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "delete rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "refuses symlink paths" in tool_result["content"][0]["reason"]
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_implement_v2_apply_patch_add_file_rejects_dangling_symlink_target(tmp_path) -> None:
    link = tmp_path / "new.txt"
    link.symlink_to(tmp_path / "missing-target.txt")
    patch = "*** Begin Patch\n*** Add File: new.txt\n+replacement\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "add rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "already exists" in tool_result["content"][0]["reason"]
    assert link.is_symlink()


def test_implement_v2_write_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path.parent / "outside-link-target.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "link.txt",
                    "content": "bad\n",
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "symlink rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_implement_v2_write_rejects_governance_paths_by_default(tmp_path) -> None:
    target = tmp_path / "ROADMAP_STATUS.md"
    target.write_text("old\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "ROADMAP_STATUS.md", "content": "new\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "governance preview rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "governance write path is protected" in tool_result["content"][0]["reason"]
    assert target.read_text(encoding="utf-8") == "old\n"


def test_implement_v2_write_replay_rejects_mutation_without_independent_approval(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "out.txt", "content": "ok\n", "create": True, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write applied"},
    )

    manifest = result.updated_lane_state["proof_manifest"]
    manifest["tool_results"][0]["side_effects"][0]["approval_id"] = ""
    from mew.implement_lane.replay import validate_proof_manifest_write_safety
    from mew.implement_lane.types import ImplementLaneProofManifest, ToolCallEnvelope, ToolResultEnvelope

    rebuilt_manifest = ImplementLaneProofManifest(
        lane=manifest["lane"],
        lane_attempt_id=manifest["lane_attempt_id"],
        artifact_namespace=manifest["artifact_namespace"],
        tool_calls=tuple(ToolCallEnvelope(**_without_schema_version(item)) for item in manifest["tool_calls"]),
        tool_results=tuple(ToolResultEnvelope(**_without_schema_version(item)) for item in manifest["tool_results"]),
    )
    validation = validate_proof_manifest_write_safety(rebuilt_manifest)

    assert validation.valid is False
    assert "write_side_effect_missing_approval_id:call-1:0" in validation.errors


def test_implement_v2_write_mode_rejects_run_command_hidden_mutation(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('out.txt').write_text('hidden', encoding='utf-8')",
        ]
    )

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "hidden mutation rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "invalid"
    assert "not available in implement_v2 write mode" in tool_result["content"][0]["reason"]
    assert not (tmp_path / "out.txt").exists()


def test_m6_24_reentry_gate_allows_explicit_lane_after_v2_replay_valid_probe(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe ok"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V1_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "ready"
    assert gate.can_resume_m6_24 is True
    assert gate.reasons == ()
    assert gate.lane_decision["selected_lane"] == IMPLEMENT_V1_LANE
    assert gate.metrics["v2_replay_valid"] is True
    assert "implement_v1" in gate.v1_artifact_namespace
    assert "implement_v2" in gate.v2_artifact_namespace
    assert gate.v1_artifact_namespace != gate.v2_artifact_namespace


def test_m6_24_reentry_gate_blocks_missing_explicit_lane(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(),
        finish_arguments={"outcome": "analysis_ready", "summary": "no evidence"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane="",
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert gate.can_resume_m6_24 is False
    assert "explicit_supported_lane_selection_required" in gate.reasons


def test_m6_24_reentry_gate_blocks_invalid_v2_replay(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "dup", "tool_name": "inspect_dir", "arguments": {"path": "."}},
            {"provider_call_id": "dup", "tool_name": "read_file", "arguments": {"path": "README.md"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "duplicate ids"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V2_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert gate.can_resume_m6_24 is False
    assert "v2_probe_replay_not_valid" in gate.reasons


def test_m6_24_reentry_gate_blocks_artifact_namespace_collision(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "inspect_dir", "arguments": {"path": "."}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe ok"},
    ).as_dict()
    v1_namespace = describe_implement_v1_adapter(work_session_id="ws-1", task_id="task-1").artifact_namespace
    v2_probe["updated_lane_state"]["proof_manifest"]["artifact_namespace"] = v1_namespace

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V2_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert "v1_v2_artifact_namespace_collision" in gate.reasons
    assert "v2_manifest_namespace_mismatch" in gate.reasons


def _expected_command_run_id(*, lane_attempt_id: str, provider_call_id: str) -> str:
    digest = hashlib.sha256(f"{lane_attempt_id}:{provider_call_id}".encode()).hexdigest()
    return f"{lane_attempt_id}:command:{provider_call_id}-{digest[:8]}"


def _write_lane_input(tmp_path, *, approved_write_calls=()) -> ImplementLaneInput:
    return ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        lane_config={
            "mode": "write",
            "allowed_write_roots": ["."],
            "approved_write_calls": list(approved_write_calls),
        },
    )


def _without_schema_version(item: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key != "schema_version"}
