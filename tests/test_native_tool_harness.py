import json
from pathlib import Path
from dataclasses import replace
import sys
from unittest.mock import patch

import pytest

from mew.implement_lane.native_fake_provider import (
    NativeFakeProvider,
    fake_call,
    fake_finish,
    fake_message,
    fake_reasoning,
    model_json_text_non_control_item,
)
from mew.implement_lane.native_provider_adapter import NativeResponsesStreamParseResult
from mew.implement_lane.native_tool_harness import (
    NativeCodexResponsesProvider,
    PHASE3_NATIVE_SURFACE,
    _NativeFinishVerifierPlan,
    _NativeCloseoutContext,
    _completion_resolver_input_from_finish,
    _finish_gate_block_resolved_by_closeout,
    _finish_gate_missing_obligations,
    _native_final_verifier_closeout_call,
    _native_finish_supplied_closeout_context,
    run_live_native_implement_v2,
    run_native_implement_v2,
    run_unavailable_native_implement_v2,
)
from mew.implement_lane.native_transcript import (
    NativeTranscript,
    NativeTranscriptItem,
    native_proof_manifest_from_transcript,
    validate_native_transcript_pairing,
)
from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID
from mew.implement_lane.types import ImplementLaneInput, ToolResultEnvelope


def _lane_input(
    tmp_path: Path,
    *,
    task_contract: dict[str, object] | None = None,
    **lane_config: object,
) -> ImplementLaneInput:
    config = {
        "allowed_read_roots": [str(tmp_path)],
        "allowed_write_roots": [str(tmp_path)],
        "allow_shell": True,
        "auto_approve_writes": True,
    }
    config.update(lane_config)
    return ImplementLaneInput(
        work_session_id="ws-native",
        task_id="task-native",
        workspace=str(tmp_path),
        lane="implement_v2",
        model_backend="fake-native",
        model="fake-native-model",
        lane_config=config,
        task_contract=task_contract or {},
    )


def _command_run_id(call_id: str) -> str:
    import hashlib

    lane_attempt_id = "ws-native:task-native:implement_v2:native"
    digest = hashlib.sha256(f"{lane_attempt_id}:{call_id}".encode()).hexdigest()
    return f"{lane_attempt_id}:command:{call_id}-{digest[:8]}"


def _task_payload(request: dict[str, object]) -> dict[str, object]:
    for item in request["input_items"]:  # type: ignore[index]
        for chunk in item["content"]:  # type: ignore[index]
            try:
                decoded = json.loads(chunk["text"])  # type: ignore[index]
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict) and "task_contract" in decoded:
                return decoded
    raise AssertionError("task payload not found")


def _compact_sidecar_digest(request: dict[str, object]) -> dict[str, object]:
    hidden_digest = request.get("compact_sidecar_digest")
    if isinstance(hidden_digest, dict):
        return hidden_digest
    return _task_payload(request)["compact_sidecar_digest"]


def _loop_signals(request: dict[str, object]) -> dict[str, object]:
    inventory = request.get("provider_request_inventory")
    assert isinstance(inventory, dict)
    signals = inventory.get("diagnostic_loop_signals")
    assert isinstance(signals, dict)
    return signals


def test_unavailable_native_runtime_keeps_native_identity(tmp_path: Path) -> None:
    result = run_unavailable_native_implement_v2(_lane_input(tmp_path))

    assert result.status == "unavailable"
    assert result.metrics["runtime_id"] == "implement_v2_native_transcript_loop"
    assert result.metrics["transport_kind"] == "provider_native_unavailable"
    assert result.metrics["provider_native_tool_loop"] is True
    assert result.metrics["model_json_main_path_detected"] is False
    assert result.updated_lane_state["runtime_id"] == "implement_v2_native_transcript_loop"


def test_native_harness_read_finish_and_artifacts(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("hello\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_message('{"tool_calls":[{"id":"ignored"}],"finish":{"outcome":"completed"}}'),
                fake_call("read-1", "read_file", {"path": "sample.txt"}, output_index=1),
                fake_finish("finish-1", {"outcome": "completed", "summary": "read done"}, output_index=2),
            ]
        ]
    )
    artifact_root = tmp_path / "artifacts"

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, artifact_root=artifact_root)

    assert result.status == "completed"
    assert result.metrics["transport_change"] == "yes"
    assert result.metrics["model_json_main_path_detected"] is False
    assert validate_native_transcript_pairing(result.transcript).valid is True
    assert [item.kind for item in result.transcript.items] == [
        "assistant_message",
        "function_call",
        "finish_call",
        "function_call_output",
        "finish_output",
    ]
    assert (artifact_root / "response_transcript.json").exists()
    manifest = json.loads((artifact_root / "proof-manifest.json").read_text(encoding="utf-8"))
    assert manifest["runtime_id"] == "implement_v2_native_transcript_loop"
    assert manifest["transport_kind"] == "fake_native"
    assert manifest["native_transport_kind"] == "provider_native"
    assert manifest["metrics"]["transport_kind"] == "fake_native"
    assert manifest["metrics"]["native_transport_kind"] == "provider_native"
    assert manifest["resolver_decisions_ref"] == "resolver_decisions.jsonl"
    tool_route_rows = [
        json.loads(line) for line in (artifact_root / "tool_routes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["tool_route"] for row in tool_route_rows] == ["read", "finish"]
    assert tool_route_rows[0]["tool_surface_profile_id"] == "mew_legacy"
    assert str(tool_route_rows[0]["tool_surface_route_table_hash"]).startswith("sha256:")
    assert tool_route_rows[0]["declared_tool"] == "read_file"
    assert tool_route_rows[1]["declared_tool"] == "finish"
    finish_output = next(item for item in result.transcript.items if item.kind == "finish_output")
    assert set(tool_route_rows[1]["typed_evidence_refs"]) == set(finish_output.evidence_refs)
    resolver_rows = [
        json.loads(line)
        for line in (artifact_root / "resolver_decisions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert resolver_rows[0]["lane_status"] == "completed"
    assert resolver_rows[0]["finish_call_id"] == "finish-1"


def test_native_harness_search_text_output_includes_model_visible_anchors(tmp_path: Path) -> None:
    source = tmp_path / "src" / "my_stdlib.c"
    source.parent.mkdir()
    source.write_text("int syscall_60(void) { return 0; }\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("search-1", "search_text", {"path": ".", "query": "syscall_60"}, output_index=0),
                fake_finish("finish-1", {"outcome": "completed", "summary": "search done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    output = next(item for item in result.transcript.items if item.call_id == "search-1" and item.kind.endswith("_output"))
    assert output.status == "completed"
    assert "matches=1" in output.output_text_or_ref
    assert "search_anchors:" in output.output_text_or_ref
    assert "my_stdlib.c:1:int syscall_60" in output.output_text_or_ref


def test_live_native_runtime_calls_responses_provider_and_writes_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    live_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-live-1",
                    provider_item_id="item-finish",
                    output_index=0,
                    kind="finish_call",
                    call_id="finish-live",
                    tool_name="finish",
                    arguments_json_text='{"outcome":"completed","summary":"live done"}',
                ),
            ),
        ),
        response_id="resp-live-1",
        status="completed",
    )
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=live_turn,
    ) as call:
        result = run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=2,
        )

    assert result.status == "completed"
    assert result.metrics["transport_kind"] == "provider_native"
    assert result.metrics["runtime_id"] == "implement_v2_native_transcript_loop"
    assert result.metrics["provider_native_tool_loop"] is True
    assert result.metrics["provider_request_inventory_available"] is True
    assert result.metrics["provider_request_count"] == 1
    descriptor = call.call_args.kwargs["descriptor"]
    assert descriptor["request_body"]["store"] is False
    assert descriptor["request_body"]["stream"] is True
    assert descriptor["request_body"]["input"][0]["role"] == "user"
    assert (artifact_root / "response_transcript.json").exists()
    transcript_payload = json.loads((artifact_root / "response_transcript.json").read_text(encoding="utf-8"))
    assert transcript_payload["items"][0]["kind"] == "finish_call"
    assert transcript_payload["items"][1]["kind"] == "finish_output"
    manifest = json.loads((artifact_root / "proof-manifest.json").read_text(encoding="utf-8"))
    assert manifest["transport_kind"] == "provider_native"
    assert manifest["metrics"]["transport_kind"] == "provider_native"
    request_payload = json.loads((artifact_root / "native-provider-requests.json").read_text(encoding="utf-8"))
    inventory_payload = json.loads((artifact_root / "provider-request-inventory.json").read_text(encoding="utf-8"))
    assert request_payload["status"] == "completed"
    assert request_payload["request_count"] == 1
    assert request_payload["requests"][0]["compact_sidecar_digest"]["digest_hash"]
    assert inventory_payload["provider_request_inventory"][0]["model_visible_sections"] == [
        "native_transcript_window",
        "task_context_refresh",
    ]
    assert inventory_payload["provider_request_inventory"][0]["compact_sidecar_digest_wire_visible"] is False
    forbidden = inventory_payload["provider_request_inventory"][0]["provider_visible_forbidden_fields"]
    assert forbidden["ok"] is True
    assert forbidden["detected"] == []


def test_live_native_request_keeps_write_file_for_hard_runtime_artifact_task(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    live_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-live-1",
                    provider_item_id="item-finish",
                    output_index=0,
                    kind="finish_call",
                    call_id="finish-live",
                    tool_name="finish",
                    arguments_json_text='{"outcome":"blocked","summary":"surface checked"}',
                ),
            ),
        ),
        response_id="resp-live-1",
        status="completed",
    )
    lane_input = _lane_input(
        tmp_path,
        artifact_dir=str(artifact_root),
        mode="full",
        task_contract={
            "goal": (
                "Build a MIPS ELF interpreter runtime from provided source and write "
                "a /tmp/frame.bmp artifact."
            )
        },
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=live_turn,
    ) as call:
        run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=1,
        )

    descriptor = call.call_args.kwargs["descriptor"]
    tool_names = {str(tool.get("name") or "") for tool in descriptor["request_body"]["tools"]}
    assert {"write_file", "edit_file", "apply_patch"} <= tool_names
    assert {"poll_command", "cancel_command", "read_command_output"}.isdisjoint(tool_names)
    instructions = str(descriptor["request_body"]["instructions"])
    assert "apply_patch or edit_file" in instructions


def test_native_provider_hides_process_lifecycle_tools_until_command_is_open(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "run-1",
                    "run_command",
                    {
                        "command": "sleep 0.2; echo done",
                        "cwd": ".",
                        "timeout_ms": 2000,
                        "foreground_budget_seconds": 0.001,
                        "command_intent": "probe",
                    },
                    output_index=0,
                )
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    assert provider.requests[0]["tool_surface_profile_id"] == "mew_legacy"
    assert provider.requests[0]["tool_surface_prompt_contract_id"] == "mew_legacy_prompt_v1"
    assert provider.requests[0]["provider_request_inventory"]["tool_surface"]["profile_id"] == "mew_legacy"  # type: ignore[index]
    assert {"poll_command", "cancel_command", "read_command_output"}.isdisjoint(provider.requests[0]["provider_tool_names"])
    assert {"poll_command", "cancel_command", "read_command_output"} <= set(provider.requests[1]["provider_tool_names"])


def test_native_provider_exposes_read_command_output_after_completed_command(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "run-1",
                    "run_command",
                    {"argv": [sys.executable, "-c", "print('done')"], "cwd": "."},
                    output_index=0,
                )
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    assert {"poll_command", "cancel_command", "read_command_output"}.isdisjoint(
        provider.requests[0]["provider_tool_names"]
    )
    assert "read_command_output" in provider.requests[1]["provider_tool_names"]
    assert "poll_command" not in provider.requests[1]["provider_tool_names"]
    assert "cancel_command" not in provider.requests[1]["provider_tool_names"]


def test_live_native_descriptor_preserves_requested_lifecycle_tools(tmp_path: Path) -> None:
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "description": "Build and run the artifact.",
            "acceptance_constraints": ["Verifier output must pass."],
        },
    )
    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth={"access_token": "token"},
        base_url="https://example.invalid",
        timeout=10,
        model="gpt-5.5",
    )
    completed = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
        ),
        response_id="resp-1",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=completed,
    ):
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 2,
                "input_items": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "{}"}],
                    }
                ],
                "instructions": "test",
                "transcript_window": [],
                "provider_tool_names": [
                    "apply_patch",
                    "edit_file",
                    "run_command",
                    "run_tests",
                    "read_command_output",
                    "read_file",
                    "finish",
                ],
            }
        )

    tool_names = {
        tool.get("name") or dict(tool.get("function") or {}).get("name")
        for tool in provider.requests[0]["request_body"]["tools"]  # type: ignore[index]
    }
    assert "read_command_output" in tool_names


def test_live_native_descriptor_preserves_codex_hot_path_tools(tmp_path: Path) -> None:
    lane_input = _lane_input(
        tmp_path,
        tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID,
    )
    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth={"access_token": "token"},
        base_url="https://example.invalid",
        timeout=10,
        model="gpt-5.5",
    )
    completed = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
        ),
        response_id="resp-1",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=completed,
    ):
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 1,
                "input_items": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "{}"}],
                    }
                ],
                "instructions": "test",
                "transcript_window": [],
                "provider_tool_names": [
                    "apply_patch",
                    "exec_command",
                    "write_stdin",
                    "finish",
                ],
                "tool_surface": {
                    "profile_id": CODEX_HOT_PATH_PROFILE_ID,
                    "profile_version": "v0",
                },
            }
        )

    tool_names = [
        tool.get("name") or dict(tool.get("function") or {}).get("name")
        for tool in provider.requests[0]["request_body"]["tools"]  # type: ignore[index]
    ]
    assert tool_names == ["apply_patch", "exec_command", "write_stdin", "finish"]


def test_codex_hot_path_exec_command_routes_to_managed_exec(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "exec-1",
                    "exec_command",
                    {"cmd": f"{sys.executable} -c \"print('ok')\"", "yield_time_ms": 1000},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        artifact_root=tmp_path / "artifacts-codex-hot-path",
        max_turns=1,
    )

    assert provider.requests[0]["provider_tool_names"] == [
        "apply_patch",
        "exec_command",
        "write_stdin",
        "finish",
    ]
    output = next(item for item in result.transcript.items if item.kind == "function_call_output")
    assert output.tool_name == "exec_command"
    assert output.status == "completed"
    assert "Exit code: 0" in output.output_text_or_ref
    assert "Chunk ID:" not in output.output_text_or_ref
    assert "Original token count:" not in output.output_text_or_ref
    assert "Output:" in output.output_text_or_ref
    assert "ok" in output.output_text_or_ref
    assert "run_command result" not in output.output_text_or_ref
    finish_output = next(item for item in result.transcript.items if item.kind == "finish_output")
    assert "finish blocked:" in finish_output.output_text_or_ref
    assert "completion_resolver" not in finish_output.output_text_or_ref
    render_rows = [
        json.loads(line)
        for line in (tmp_path / "artifacts-codex-hot-path" / "tool_render_outputs.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert render_rows[0]["renderer_id"] == "codex_terminal_text_v1"
    assert render_rows[0]["leak_ok"] is True
    routes = [
        json.loads(line)
        for line in (tmp_path / "artifacts-codex-hot-path" / "tool_routes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert routes[0]["declared_tool"] == "exec_command"
    assert routes[0]["effective_tool"] == "run_command"
    assert routes[0]["tool_route"] == "process_runner"


def test_codex_hot_path_exec_command_matching_verifier_preserves_verify_intent(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "exec-verify",
                    "exec_command",
                    {"cmd": "test -f done.txt", "yield_time_ms": 1000},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID,
            verify_command="test -f done.txt",
        ),
        provider=provider,
        max_turns=1,
    )

    exec_output = next(item for item in result.transcript.items if item.kind == "function_call_output")
    assert exec_output.tool_name == "exec_command"
    assert any("structured_finish_gate" in ref for ref in exec_output.evidence_refs)


def test_codex_hot_path_write_stdin_empty_chars_polls_session(tmp_path: Path) -> None:
    command_id = _command_run_id("exec-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "exec-1",
                    "exec_command",
                    {
                        "cmd": f"{sys.executable} -c \"print('done')\"",
                        "yield_time_ms": 0,
                    },
                    output_index=0,
                )
            ],
            [
                fake_call(
                    "stdin-1",
                    "write_stdin",
                    {"session_id": command_id, "chars": "", "yield_time_ms": 1000},
                    output_index=0,
                )
            ],
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=2,
    )

    output = result.transcript.items[-1]
    assert output.tool_name == "write_stdin"
    assert output.status == "completed"
    assert "Exit code: 0" in output.output_text_or_ref


def test_codex_hot_path_write_stdin_non_empty_chars_fails_poll_only(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "stdin-1",
                    "write_stdin",
                    {"session_id": "session-1", "chars": "q"},
                    output_index=0,
                )
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.kind == "function_call_output")
    assert output.tool_name == "write_stdin"
    assert output.status == "invalid"
    assert "poll_only" in output.output_text_or_ref
    assert "Exit code: 1" in output.output_text_or_ref


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected"),
    [
        ("exec_command", {"cmd": ""}, "exec_command adapter error: cmd is required"),
        (
            "exec_command",
            {"cmd": "echo ok", "tty": True},
            "exec_command adapter error: tty is not supported",
        ),
        (
            "exec_command",
            {"cmd": "echo ok", "login": True},
            "exec_command adapter error: login shells are not supported",
        ),
        ("write_stdin", {"session_id": "missing", "chars": ""}, "no managed command is active"),
    ],
)
def test_codex_hot_path_adapter_failures_use_terminal_renderer(
    tmp_path: Path,
    tool_name: str,
    arguments: dict[str, object],
    expected: str,
) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("call-1", tool_name, arguments, output_index=0)]]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.kind == "function_call_output")
    assert output.tool_name == tool_name
    assert output.status in {"failed", "invalid"}
    assert "Exit code: 1" in output.output_text_or_ref
    assert expected in output.output_text_or_ref
    assert "run_command result" not in output.output_text_or_ref


def test_codex_hot_path_exec_command_yielded_uses_terminal_session_shape(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "exec-yield",
                    "exec_command",
                    {
                        "cmd": f"{sys.executable} -c \"import time; print('start'); time.sleep(2)\"",
                        "yield_time_ms": 0,
                    },
                    output_index=0,
                )
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.kind == "function_call_output")
    assert output.tool_name == "exec_command"
    assert output.status in {"yielded", "running", "completed", "failed", "interrupted"}
    assert "Process running with session ID" in output.output_text_or_ref
    assert "run_command result" not in output.output_text_or_ref


def test_codex_hot_path_apply_patch_success_uses_patch_renderer(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    patch_text = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: sample.txt",
            "@@",
            "-before",
            "+after",
            "*** End Patch",
        ]
    )
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("patch-1", "apply_patch", {"patch": patch_text, "apply": True}, output_index=0),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.call_id == "patch-1" and item.kind.endswith("_output"))
    assert output.status == "completed"
    assert output.output_text_or_ref.startswith("Success. Updated files:")
    assert "M sample.txt" in output.output_text_or_ref
    assert "suggested_next_action" not in output.output_text_or_ref
    assert target.read_text(encoding="utf-8") == "after\n"


def test_codex_hot_path_malformed_apply_patch_uses_patch_failure_renderer(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("patch-bad", "apply_patch", {"patch": "not a patch", "apply": True}, output_index=0)]]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.call_id == "patch-bad" and item.kind.endswith("_output"))
    assert output.status == "failed"
    assert output.output_text_or_ref.startswith("apply_patch failed:")
    assert "suggested_next_action" not in output.output_text_or_ref


def test_codex_hot_path_synthetic_cancel_output_uses_profile_renderer(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_finish("finish-1", {"outcome": "blocked_return", "summary": "return"}, output_index=0),
                fake_call("exec-after", "exec_command", {"cmd": "echo late"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        max_turns=1,
    )

    output = next(item for item in result.transcript.items if item.call_id == "exec-after" and item.kind.endswith("_output"))
    assert output.metrics_ref
    assert "Exit code: 1" in output.output_text_or_ref
    assert "cancelled because finish call finish-1" in output.output_text_or_ref
    assert "run_command result" not in output.output_text_or_ref


def test_native_provider_input_surfaces_missing_verify_path_as_factual_task_fact(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "description": "Implement a runtime called vm.js.",
            "verify_command": "node vm.js",
            "acceptance_constraints": ["Running node vm.js should save a frame."],
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    payload = _task_payload(provider.requests[0])
    task_facts = payload["task_facts"]
    assert task_facts["verify_command_paths"] == ["vm.js"]
    assert task_facts["mentioned_workspace_paths"] == ["vm.js"]
    assert task_facts["missing_workspace_paths"] == ["vm.js"]
    rendered = json.dumps(task_facts, sort_keys=True)
    assert "next_action" not in rendered
    assert "required_next" not in rendered
    assert "first_write" not in rendered


def test_native_provider_input_is_task_first_before_support_json(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "title": "Build a small runtime",
            "description": "Implement vm.js.",
            "verify_command": "node vm.js",
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    input_items = provider.requests[0]["input_items"]
    first_text = input_items[0]["content"][0]["text"]  # type: ignore[index]
    second_text = input_items[1]["content"][0]["text"]  # type: ignore[index]
    support_payload = json.loads(second_text)

    assert first_text.startswith("Task\n")
    assert "Title: Build a small runtime" in first_text
    assert "Objective: Implement vm.js." in first_text
    assert "Verifier: node vm.js" in first_text
    assert "Missing task paths: vm.js" in first_text
    assert "compact_sidecar_digest" not in first_text
    assert list(support_payload) == [
        "task_contract",
        "task_facts",
        "workspace",
        "lane",
    ]
    assert "compact_sidecar_digest" not in support_payload
    assert provider.requests[0]["compact_sidecar_digest"]["digest_hash"]
    assert provider.requests[0]["provider_request_inventory"]["compact_sidecar_digest_wire_visible"] is False


@pytest.mark.parametrize("objective_key", ["objective", "goal", "task", "prompt"])
def test_native_provider_task_first_text_uses_common_objective_keys(tmp_path: Path, objective_key: str) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            objective_key: "Patch a Python bug and run tests.",
            "verify_command": "pytest -q",
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    first_text = provider.requests[0]["input_items"][0]["content"][0]["text"]  # type: ignore[index]
    assert "Objective: Patch a Python bug and run tests." in first_text
    assert "Verifier: pytest -q" in first_text


def test_native_provider_input_does_not_mark_existing_verify_path_missing(tmp_path: Path) -> None:
    (tmp_path / "vm.js").write_text("console.log('ok')\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(tmp_path, task_contract={"verify_command": "node vm.js"})

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    task_facts = _task_payload(provider.requests[0])["task_facts"]
    assert task_facts["verify_command_paths"] == ["vm.js"]
    assert task_facts["mentioned_workspace_paths"] == ["vm.js"]
    assert task_facts["existing_workspace_paths"] == ["vm.js"]
    assert "missing_workspace_paths" not in task_facts


def test_native_provider_input_task_facts_relativize_workspace_absolute_paths(tmp_path: Path) -> None:
    (tmp_path / "doomgeneric_mips").write_text("elf", encoding="utf-8")
    (tmp_path / "doomgeneric").mkdir()
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "description": (
                f"I have provided {tmp_path / 'doomgeneric_mips'}, a MIPS elf file, "
                "along with doomgeneric/, the corresponding source code. Implement vm.js."
            ),
            "verify_command": "node vm.js",
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    task_facts = _task_payload(provider.requests[0])["task_facts"]
    assert "doomgeneric_mips" in task_facts["mentioned_workspace_paths"]
    assert "doomgeneric" in task_facts["mentioned_workspace_paths"]
    assert "vm.js" in task_facts["missing_workspace_paths"]
    assert task_facts["existing_workspace_paths"] == ["doomgeneric_mips", "doomgeneric"]


def test_native_provider_input_task_facts_normalize_dot_slash_and_reject_unsafe_paths(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "description": "Ignore ../secret.py, ..\\secret.py, and C:\\tmp\\foo.py; implement ./vm.js.",
            "verify_command": "node ./vm.js",
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    task_facts = _task_payload(provider.requests[0])["task_facts"]
    assert task_facts["verify_command_paths"] == ["vm.js"]
    assert task_facts["mentioned_workspace_paths"] == ["vm.js"]
    assert task_facts["missing_workspace_paths"] == ["vm.js"]
    rendered = json.dumps(task_facts, sort_keys=True)
    assert "secret.py" not in rendered
    assert "foo.py" not in rendered


@pytest.mark.parametrize("verify_command", ["node src\\vm.js", "node .\\vm.js", "python pkg\\module.py"])
def test_native_provider_input_task_facts_reject_backslash_paths(tmp_path: Path, verify_command: str) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(tmp_path, task_contract={"verify_command": verify_command})

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    payload = _task_payload(provider.requests[0])
    assert "task_facts" not in payload or not payload["task_facts"]


def test_native_provider_hides_poll_cancel_after_terminal_poll_supersedes_yield(tmp_path: Path) -> None:
    command_id = _command_run_id("run-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "run-1",
                    "run_command",
                    {
                        "command": "sleep 0.1; echo done",
                        "cwd": ".",
                        "timeout_ms": 2000,
                        "foreground_budget_seconds": 0.001,
                    },
                    output_index=0,
                )
            ],
            [
                fake_call(
                    "poll-1",
                    "poll_command",
                    {"command_run_id": command_id, "wait_seconds": 1},
                    output_index=0,
                )
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert {"poll_command", "cancel_command", "read_command_output"} <= set(
        provider.requests[1]["provider_tool_names"]
    )
    assert "read_command_output" in provider.requests[2]["provider_tool_names"]
    assert "poll_command" not in provider.requests[2]["provider_tool_names"]
    assert "cancel_command" not in provider.requests[2]["provider_tool_names"]


def test_native_provider_hides_poll_cancel_after_cancel_supersedes_yield(tmp_path: Path) -> None:
    command_id = _command_run_id("run-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "run-1",
                    "run_command",
                    {
                        "command": "sleep 3",
                        "cwd": ".",
                        "timeout_ms": 5000,
                        "foreground_budget_seconds": 0.001,
                    },
                    output_index=0,
                )
            ],
            [
                fake_call(
                    "cancel-1",
                    "cancel_command",
                    {"command_run_id": command_id, "reason": "stop diagnostic"},
                    output_index=0,
                )
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert {"poll_command", "cancel_command", "read_command_output"} <= set(
        provider.requests[1]["provider_tool_names"]
    )
    assert "read_command_output" in provider.requests[2]["provider_tool_names"]
    assert "poll_command" not in provider.requests[2]["provider_tool_names"]
    assert "cancel_command" not in provider.requests[2]["provider_tool_names"]


def test_native_run_command_respects_provider_visible_output_budget(tmp_path: Path) -> None:
    script = "import sys; [print(f'line-{i:03d}') for i in range(350)]"
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "run-wide-output",
                    "run_command",
                    {
                        "argv": [sys.executable, "-c", script],
                        "cwd": ".",
                        "max_output_tokens": 3000,
                    },
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=1)

    output = next(
        item
        for item in result.transcript.items
        if item.kind.endswith("_output") and item.call_id == "run-wide-output"
    )
    assert len(output.output_text_or_ref) > 1200
    assert "line-000" in output.output_text_or_ref
    assert "line-349" in output.output_text_or_ref
    assert "command_intent" not in output.output_text_or_ref


def test_native_hard_runtime_allows_write_file_source_creation(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "bad\n", "create": True, "apply": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "surface checked"}, output_index=1),
            ]
        ]
    )
    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            mode="full",
            task_contract={
                "goal": (
                    "Build a MIPS ELF interpreter runtime from provided source and write "
                    "a /tmp/frame.bmp artifact."
                )
            },
        ),
        provider=provider,
    )

    output = next(item for item in result.transcript.items if item.call_id == "write-1" and item.kind.endswith("_output"))
    assert output.status == "completed"
    assert output.is_error is False
    assert "write_file result: completed" in output.output_text_or_ref
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "bad\n"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_hard_runtime_sanitizes_missing_target_edit_guidance(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "edit-1",
                    "edit_file",
                    {"path": "vm.js", "old_string": "old", "new_string": "new", "apply": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "blocked", "summary": "surface checked"}, output_index=1),
            ]
        ]
    )
    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            mode="full",
            task_contract={
                "goal": (
                    "Build a MIPS ELF interpreter runtime from provided source and write "
                    "a /tmp/frame.bmp artifact."
                )
            },
        ),
        provider=provider,
    )

    output = next(item for item in result.transcript.items if item.call_id == "edit-1" and item.kind.endswith("_output"))
    assert output.status == "failed"
    assert output.is_error is True
    assert "create=True" in output.output_text_or_ref
    assert "write_file" in output.output_text_or_ref
    assert not (tmp_path / "vm.js").exists()


def test_native_hard_runtime_carry_forward_preserves_write_file_call(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "bad\n", "create": True, "apply": True},
                    output_index=0,
                )
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "surface checked"}, output_index=0)],
        ]
    )
    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            mode="full",
            task_contract={
                "goal": (
                    "Build the provided emulator runtime from source and write "
                    "a /tmp/output.png image artifact."
                )
            },
        ),
        provider=provider,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert len(provider.requests) == 2
    second_request = json.dumps(provider.requests[1], ensure_ascii=False, sort_keys=True)
    assert "unavailable_write_tool" not in second_request
    assert "write_file" in second_request
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "bad\n"


def test_live_native_provider_failure_writes_request_inventory_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=RuntimeError("request timed out"),
    ):
        result = run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=1,
        )

    assert result.status == "failed"
    assert result.metrics["provider_request_inventory_available"] is True
    assert result.metrics["turn_count"] == 1
    assert result.updated_lane_state["runtime_id"] == "implement_v2_native_transcript_loop"
    assert result.updated_lane_state["transport_kind"] == "provider_native"
    request_path = artifact_root / "native-provider-requests.json"
    inventory_path = artifact_root / "provider-request-inventory.json"
    assert request_path.exists()
    assert inventory_path.exists()
    request_payload = json.loads(request_path.read_text(encoding="utf-8"))
    inventory_payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    assert request_payload["request_count"] == 1
    assert request_payload["requests"][0]["compact_sidecar_digest"]["digest_hash"]
    assert inventory_payload["request_count"] == 1
    assert inventory_payload["provider_request_inventory"][0]["model_visible_sections"] == [
        "native_transcript_window",
        "task_context_refresh",
    ]
    assert inventory_payload["provider_request_inventory"][0]["compact_sidecar_digest_wire_visible"] is False


def test_live_native_first_turn_value_error_writes_failure_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=ValueError("malformed provider payload"),
    ):
        result = run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=1,
        )

    assert result.status == "failed"
    assert "malformed provider payload" in result.user_visible_summary
    assert result.updated_lane_state["runtime_id"] == "implement_v2_native_transcript_loop"
    assert (artifact_root / "response_transcript.json").exists()
    request_payload = json.loads((artifact_root / "native-provider-requests.json").read_text(encoding="utf-8"))
    assert request_payload["error"] == "malformed provider payload"
    assert request_payload["request_count"] == 1


def test_live_native_provider_failure_preserves_partial_transcript_artifacts(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("hello\n", encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))
    first_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-live-1",
                    provider_item_id="item-read",
                    output_index=0,
                    kind="function_call",
                    call_id="read-live",
                    tool_name="read_file",
                    arguments_json_text='{"path":"sample.txt"}',
                ),
            ),
        ),
        response_id="resp-live-1",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=[first_turn, RuntimeError("request timed out")],
    ):
        result = run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=2,
        )

    assert result.status == "failed"
    assert result.metrics["turn_count"] == 2
    assert result.metrics["pairing"]["valid"] is True
    transcript_payload = json.loads((artifact_root / "response_transcript.json").read_text(encoding="utf-8"))
    item_kinds = [item["kind"] for item in transcript_payload["items"]]
    assert item_kinds == ["function_call", "function_call_output"]
    assert (artifact_root / "response_items.jsonl").read_text(encoding="utf-8").strip()
    tool_route_rows = [
        json.loads(line) for line in (artifact_root / "tool_routes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert tool_route_rows[0]["tool_route"] == "read"
    assert tool_route_rows[0]["declared_tool"] == "read_file"
    request_payload = json.loads((artifact_root / "native-provider-requests.json").read_text(encoding="utf-8"))
    assert request_payload["status"] == "failed_before_native_response"
    assert request_payload["request_count"] == 2
    assert request_payload["response_count"] == 1
    assert request_payload["rejected_response_count"] == 0


def test_live_native_provider_requires_completed_terminal_event_before_tool_execution(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))
    incomplete_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-live-1",
                    provider_item_id="item-write",
                    output_index=0,
                    kind="function_call",
                    call_id="write-live",
                    tool_name="write_file",
                    arguments_json_text='{"path":"created.txt","content":"bad\\n","create":true}',
                ),
            ),
        ),
        response_id="resp-live-1",
        status="created",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=incomplete_turn,
    ):
        result = run_live_native_implement_v2(
            lane_input,
            model_auth={"access_token": "x"},
            base_url="https://example.invalid",
            timeout=3,
            max_turns=1,
        )

    assert result.status == "failed"
    assert "did not complete before stream ended" in result.user_visible_summary
    assert not (tmp_path / "created.txt").exists()
    transcript_payload = json.loads((artifact_root / "response_transcript.json").read_text(encoding="utf-8"))
    assert transcript_payload["items"] == []
    request_payload = json.loads((artifact_root / "native-provider-requests.json").read_text(encoding="utf-8"))
    assert request_payload["status"] == "failed_before_completed_native_response"
    assert request_payload["response_count"] == 1
    assert request_payload["rejected_response_count"] == 1
    rejected_response = request_payload["rejected_responses"][0]
    assert rejected_response["status"] == "created"
    assert rejected_response["transcript"]["items"][0]["tool_name"] == "write_file"
    inventory_payload = json.loads((artifact_root / "provider-request-inventory.json").read_text(encoding="utf-8"))
    assert inventory_payload["provider_response_statuses"] == ["created"]
    assert inventory_payload["rejected_provider_response_statuses"] == ["created"]


def test_live_native_provider_failure_rejects_invalid_partial_transcript(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))
    invalid_first_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-live-1",
                    provider_item_id="output-without-call",
                    output_index=0,
                    kind="function_call_output",
                    call_id="missing-call",
                    tool_name="read_file",
                    output_text_or_ref="orphan output",
                ),
            ),
        ),
        response_id="resp-live-1",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=[invalid_first_turn, RuntimeError("request timed out")],
    ):
        with pytest.raises(ValueError, match="invalid native transcript"):
            run_live_native_implement_v2(
                lane_input,
                model_auth={"access_token": "x"},
                base_url="https://example.invalid",
                timeout=3,
                max_turns=2,
            )


def test_native_harness_blocks_before_provider_turn_when_wall_budget_is_too_low(tmp_path: Path) -> None:
    lane_input = replace(_lane_input(tmp_path), task_contract={"max_wall_seconds": 10})
    provider = NativeFakeProvider.from_item_batches([])
    provider.timeout = 60.0  # type: ignore[attr-defined]

    result = run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    assert result.status == "blocked"
    assert result.finish_summary == "native wall-clock budget exhausted before next provider turn"
    assert provider.requests == []
    block = result.metrics["native_model_turn_budget_block"]
    assert block["failure_class"] == "native_model_budget_insufficient"
    assert block["active_model_timeout_seconds"] < block["minimum_required_model_timeout_seconds"]


def test_native_harness_closes_active_command_before_low_budget_provider_turn(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "sleep 0.05; true",
                        "cwd": ".",
                        "foreground_budget_seconds": 0,
                        "timeout": 3,
                    },
                    output_index=0,
                )
            ]
        ]
    )

    with patch(
        "mew.implement_lane.native_tool_harness._native_next_model_timeout_seconds",
        side_effect=[30.0, 20.0],
    ):
        result = run_native_implement_v2(_lane_input(tmp_path, allow_verify=True), provider=provider, max_turns=2)

    assert result.status == "blocked"
    assert result.finish_summary == "native wall-clock budget exhausted before next provider turn"
    assert result.metrics["active_command_closeout_count"] == 1
    assert result.metrics["active_command_closeout_reason"] == (
        "native active command closeout ran before low-budget provider turn"
    )
    assert result.metrics["active_command_closeout_provider_call_id"] == "call-active-command-closeout-002"
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-active-command-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "completed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_live_native_input_carry_forward_omits_reasoning_refs_without_sidecar_bytes(tmp_path: Path) -> None:
    lane_input = _lane_input(tmp_path)
    descriptor = {
        "lane_attempt_id": "ws-native:task-native:implement_v2:native",
        "turn_index": 2,
        "input_items": [
            {
                "type": "reasoning",
                "id": "rs-1",
                "summary": "local summary",
                "encrypted_reasoning_ref": "reasoning_sidecar.json#sha256:abc",
            }
        ],
        "instructions": "test",
        "transcript_window": [],
    }
    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth={"access_token": "x"},
        base_url="https://example.invalid",
        timeout=3,
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        return_value=NativeResponsesStreamParseResult(
            transcript=NativeTranscript(
                lane_attempt_id="ws-native:task-native:implement_v2:native",
                provider="openai",
                model="gpt-5.5",
            ),
            status="completed",
        ),
    ):
        provider.next_response(descriptor)

    sent_input = provider.requests[0]["request_body"]["input"]
    assert all(item.get("type") != "reasoning" for item in sent_input)


def test_live_native_provider_uses_previous_response_id_delta_after_prefix_match(tmp_path: Path) -> None:
    lane_input = _lane_input(tmp_path)
    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth={"access_token": "x"},
        base_url="https://example.invalid",
        timeout=3,
    )
    first_input = {
        "role": "user",
        "content": [{"type": "input_text", "text": "task"}],
    }
    call_item = {
        "type": "function_call",
        "id": "item-read",
        "call_id": "call-read",
        "name": "read_file",
        "arguments": '{"path":"README.md"}',
    }
    output_item = {
        "type": "function_call_output",
        "call_id": "call-read",
        "output": "read_file result: completed",
    }
    first_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-1",
                    provider_item_id="item-read",
                    output_index=0,
                    kind="function_call",
                    call_id="call-read",
                    tool_name="read_file",
                    arguments_json_text='{"path":"README.md"}',
                ),
            ),
        ),
        response_id="resp-1",
        status="completed",
    )
    second_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
        ),
        response_id="resp-2",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=[first_turn, second_turn],
    ):
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 1,
                "input_items": [first_input],
                "instructions": "test",
                "transcript_window": [],
            }
        )
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 2,
                "input_items": [first_input, call_item, output_item],
                "instructions": "test",
                "transcript_window": [],
            }
        )

    first_request = provider.requests[0]["request_body"]
    second_request = provider.requests[1]["request_body"]
    assert "previous_response_id" not in first_request
    assert second_request["previous_response_id"] == "resp-1"
    assert second_request["input"] == [output_item]
    assert provider.requests[1]["previous_response_delta_mode"] == "delta"
    assert provider.requests[1]["logical_input_item_count"] == 3
    assert provider.requests[1]["wire_input_item_count"] == 1


def test_live_native_provider_uses_previous_response_id_with_task_first_context_refresh(tmp_path: Path) -> None:
    lane_input = _lane_input(tmp_path)
    provider = NativeCodexResponsesProvider(
        lane_input=lane_input,
        auth={"access_token": "x"},
        base_url="https://example.invalid",
        timeout=3,
    )
    task_item = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": "Task\nObjective: Implement vm.js.\nSupporting JSON facts follow in the next input item.",
            }
        ],
    }
    old_context_item = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task_contract": {"title": "Task"},
                        "task_facts": {"missing_workspace_paths": ["vm.js"]},
                        "compact_sidecar_digest": {"digest_hash": "old"},
                        "workspace": str(tmp_path),
                        "lane": "implement_v2",
                    }
                ),
            }
        ],
    }
    new_context_item = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task_contract": {"title": "Task"},
                        "task_facts": {"missing_workspace_paths": ["vm.js"]},
                        "compact_sidecar_digest": {"digest_hash": "new"},
                        "workspace": str(tmp_path),
                        "lane": "implement_v2",
                    }
                ),
            }
        ],
    }
    call_item = {
        "type": "function_call",
        "id": "item-read",
        "call_id": "call-read",
        "name": "read_file",
        "arguments": '{"path":"README.md"}',
    }
    output_item = {
        "type": "function_call_output",
        "call_id": "call-read",
        "output": "read_file result: completed",
    }
    first_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
            items=(
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id="ws-native:task-native:implement_v2:native",
                    provider="openai",
                    model="gpt-5.5",
                    response_id="resp-1",
                    provider_item_id="item-read",
                    output_index=0,
                    kind="function_call",
                    call_id="call-read",
                    tool_name="read_file",
                    arguments_json_text='{"path":"README.md"}',
                ),
            ),
        ),
        response_id="resp-1",
        status="completed",
    )
    second_turn = NativeResponsesStreamParseResult(
        transcript=NativeTranscript(
            lane_attempt_id="ws-native:task-native:implement_v2:native",
            provider="openai",
            model="gpt-5.5",
        ),
        response_id="resp-2",
        status="completed",
    )

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses_websocket",
        side_effect=[first_turn, second_turn],
    ):
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 1,
                "input_items": [task_item, old_context_item],
                "instructions": "test",
                "transcript_window": [],
            }
        )
        provider.next_response(
            {
                "lane_attempt_id": "ws-native:task-native:implement_v2:native",
                "turn_index": 2,
                "input_items": [task_item, new_context_item, call_item, output_item],
                "instructions": "test",
                "transcript_window": [],
            }
        )

    second_request = provider.requests[1]["request_body"]
    assert second_request["previous_response_id"] == "resp-1"
    assert second_request["input"] == [task_item, new_context_item, output_item]
    assert provider.requests[1]["previous_response_delta_mode"] == "delta_with_context_refresh"
    assert provider.requests[1]["previous_response_leading_refresh_item_count"] == 2
    assert provider.requests[1]["logical_input_item_count"] == 4
    assert provider.requests[1]["wire_input_item_count"] == 3


def test_native_harness_write_apply_patch_exec_poll_cancel_and_read_output(tmp_path: Path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    command_id = _command_run_id("exec-sleep")
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: sample.txt",
            "@@",
            "-after write",
            "+after patch",
            "*** End Patch",
        ]
    )
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "sample.txt", "content": "after write\n", "apply": True},
                    output_index=0,
                ),
                fake_call("patch-1", "apply_patch", {"patch": patch, "apply": True}, output_index=1),
                fake_call(
                    "exec-sleep",
                    "run_command",
                    {
                        "command": "printf native-output; sleep 2",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                    output_index=2,
                ),
                fake_call("poll-1", "poll_command", {"command_run_id": command_id, "wait_seconds": 0}, output_index=3),
                fake_call("read-output-1", "read_command_output", {"command_run_id": command_id}, output_index=4),
                fake_call("cancel-1", "cancel_command", {"command_run_id": command_id}, output_index=5),
                fake_finish("finish-1", {"outcome": "completed"}, output_index=6),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert result.status == "blocked"
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_return"
    assert result.metrics["completion_resolver_latest_decision"]["blockers"]
    assert target.read_text(encoding="utf-8") == "after patch\n"
    outputs = [item for item in result.transcript.items if item.kind.endswith("_output")]
    assert [item.call_id for item in outputs] == [
        "write-1",
        "patch-1",
        "exec-sleep",
        "poll-1",
        "read-output-1",
        "cancel-1",
        "finish-1",
    ]
    assert all(item.status in {"blocked", "completed", "yielded", "interrupted"} for item in outputs)
    assert result.metrics["first_write_latency"]["call_id"] == "write-1"
    assert result.metrics["first_write_latency_turn"] == 1
    assert "first_write_latency_turns" not in result.metrics
    assert len(result.metrics["tool_latency"]) == 7


def test_native_harness_custom_apply_patch_mutates_when_writes_are_auto_approved(tmp_path: Path) -> None:
    target = tmp_path / "created.txt"
    patch = "\n".join(
        [
            "*** Begin Patch",
            "*** Add File: created.txt",
            "+created from custom patch",
            "*** End Patch",
        ]
    )
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                {
                    "type": "custom_tool_call",
                    "id": "item-custom-patch",
                    "call_id": "custom-patch-1",
                    "name": "apply_patch",
                    "input": patch,
                    "output_index": 0,
                },
                fake_finish("finish-1", {"outcome": "completed", "summary": "patched"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert target.read_text(encoding="utf-8") == "created from custom patch\n"
    output = next(
        item
        for item in result.transcript.items
        if item.call_id == "custom-patch-1" and item.kind == "custom_tool_call_output"
    )
    assert output.status == "completed"


def test_native_harness_invalid_arguments_get_paired_output(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("bad-args", "read_file", "{not-json", output_index=0), fake_finish("finish-1", output_index=1)]]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    bad_output = next(item for item in result.transcript.items if item.call_id == "bad-args" and item.kind.endswith("_output"))
    assert bad_output.status == "invalid"
    assert bad_output.is_error is True
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_invalid_finish_args_pairs_protocol_error_without_resolver(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [fake_call("finish-json", "finish", "{not-json", output_index=0)],
            [fake_finish("finish-bad", {"summary": ["not", "a", "string"]}, output_index=0)],
            [fake_finish("finish-ok", {"outcome": "completed", "summary": "retried"}, output_index=0)],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert result.status == "completed"
    json_output = next(item for item in result.transcript.items if item.call_id == "finish-json" and item.kind == "finish_output")
    assert json_output.status == "invalid"
    assert json_output.is_error is True
    assert "invalid JSON arguments" in json_output.output_text_or_ref
    bad_output = next(item for item in result.transcript.items if item.call_id == "finish-bad" and item.kind == "finish_output")
    assert bad_output.status == "invalid"
    assert bad_output.is_error is True
    assert "finish_protocol_error" not in bad_output.output_text_or_ref
    assert "must be a string" in bad_output.output_text_or_ref
    assert result.metrics["completion_resolver_decision_count"] == 1
    assert result.metrics["completion_resolver_latest_decision"]["finish_call_id"] == "finish-ok"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_with_siblings_cancels_later_calls(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("read-before", "read_file", {"path": "missing.txt"}, output_index=0),
                fake_finish("finish-1", {"outcome": "completed"}, output_index=1),
                fake_call(
                    "write-after",
                    "write_file",
                    {"path": "should-not-exist.txt", "content": "no\n", "apply": True},
                    output_index=2,
                ),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert result.status == "completed"
    assert not (tmp_path / "should-not-exist.txt").exists()
    cancelled = next(item for item in result.transcript.items if item.call_id == "write-after" and item.kind.endswith("_output"))
    assert cancelled.status == "synthetic_error"
    assert cancelled.is_error is True


def test_native_harness_blocked_finish_continues_and_non_tool_siblings_need_no_pairing(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_reasoning("thinking", item_id="r1"),
                fake_finish("finish-blocked", {"outcome": "blocked", "summary": "not enough proof"}, output_index=1),
                fake_message("plain context", item_id="m1"),
            ],
            [fake_finish("finish-ok", {"outcome": "completed", "summary": "done"}, output_index=0)],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert result.status == "completed"
    assert provider.requests[-1]["input_item_count"] == 4
    assert [item.kind for item in result.transcript.items[:3]] == ["reasoning", "finish_call", "assistant_message"]
    blocked = next(item for item in result.transcript.items if item.call_id == "finish-blocked" and item.kind == "finish_output")
    assert blocked.status == "blocked"
    assert blocked.is_error is True
    assert "finish result: invalid" in blocked.output_text_or_ref
    assert result.metrics["completion_resolver_decision_count"] == 2
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_blocked_return_preserves_pair_and_stops_provider_requests(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_finish(
                    "finish-return",
                    {"outcome": "blocked_return", "summary": "supervisor needed"},
                    output_index=0,
                )
            ],
            [fake_finish("finish-late", {"outcome": "completed", "summary": "should not run"}, output_index=0)],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    assert result.status == "blocked"
    assert len(provider.requests) == 1
    output = next(item for item in result.transcript.items if item.call_id == "finish-return" and item.kind == "finish_output")
    assert output.status == "blocked"
    assert output.is_error is True
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_return"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_completed_finish_runs_acceptance_gate(tmp_path: Path) -> None:
    lane_input = replace(
        _lane_input(tmp_path),
        task_contract={
            "title": "runtime task",
            "description": "Make node vm.js boot correctly. I will check that it prints booted and writes output.",
            "acceptance_constraints": [
                "I will check that it prints booted and writes output.",
            ],
        },
    )
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_finish(
                    "finish-early",
                    {"summary": "artifact exists", "evidence_refs": [], "final_status": "done"},
                    output_index=0,
                )
            ]
        ]
    )

    result = run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_constraints_unchecked" for blocker in blockers)
    finish_output = next(item for item in result.transcript.items if item.kind == "finish_output")
    assert finish_output.status == "blocked"
    assert finish_output.is_error is True
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_continue"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_unknown_completion_status_still_runs_acceptance_gate(tmp_path: Path) -> None:
    lane_input = replace(
        _lane_input(tmp_path),
        task_contract={
            "description": "The output should include hello.",
            "acceptance_constraints": ["The output should include hello."],
        },
    )
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-unknown", {"summary": "done", "final_status": "finished"}, output_index=0)]]
    )

    result = run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_constraints_unchecked" for blocker in blockers)


def test_native_harness_failed_finish_status_does_not_complete(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_finish("finish-failed", {"summary": "failed", "final_status": "failed"}, output_index=0)]]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=1)

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 0
    finish_output = next(item for item in result.transcript.items if item.kind == "finish_output")
    assert finish_output.status == "blocked"
    assert finish_output.is_error is True


def test_native_harness_model_json_text_is_not_control(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches([[model_json_text_non_control_item(), fake_finish("finish-1")]])

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert [item.kind for item in result.transcript.items].count("function_call") == 0
    assert any(item.kind == "assistant_message" and "tool_calls" in item.output_text_or_ref for item in result.transcript.items)
    assert result.status == "completed"


def test_phase3_surface_declares_transport_change_yes() -> None:
    assert PHASE3_NATIVE_SURFACE["transport_change"] == "yes"
    assert PHASE3_NATIVE_SURFACE["transport_kind"] == "fake_native"
    assert PHASE3_NATIVE_SURFACE["native_transport_kind"] == "provider_native"
    assert PHASE3_NATIVE_SURFACE["provider_native_tool_loop"] is True


def test_native_harness_dispatches_and_cancels_by_provider_output_index(tmp_path: Path) -> None:
    (tmp_path / "source.txt").write_text("before\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_finish("finish-early-sequence", {"outcome": "completed"}, output_index=2),
                fake_call("read-earlier-index", "read_file", {"path": "source.txt"}, output_index=0),
                fake_call(
                    "write-later-index",
                    "write_file",
                    {"path": "later.txt", "content": "no\n", "apply": True},
                    output_index=3,
                ),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    outputs = [item for item in result.transcript.items if item.kind.endswith("_output")]
    assert [item.call_id for item in outputs] == ["read-earlier-index", "finish-early-sequence", "write-later-index"]
    assert outputs[0].status == "completed"
    assert outputs[1].kind == "finish_output"
    assert outputs[2].status == "synthetic_error"
    assert not (tmp_path / "later.txt").exists()


def test_native_harness_first_verifier_latency_metric_for_run_tests(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "verify-1",
                    "run_tests",
                    {"argv": ["true"], "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
                    output_index=0,
                ),
                fake_finish("finish-1", output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    assert result.metrics["first_verifier_latency"]["call_id"] == "verify-1"
    assert result.metrics["first_verifier_latency"]["tool_name"] == "run_tests"
    assert result.metrics["first_verifier_latency"]["turn_index"] == 1


def test_native_harness_approval_denied_write_pairs_without_mutation(tmp_path: Path) -> None:
    target = tmp_path / "denied.txt"
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-denied",
                    "write_file",
                    {"path": "denied.txt", "content": "no\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path, auto_approve_writes=False), provider=provider)

    output = next(item for item in result.transcript.items if item.call_id == "write-denied" and item.kind.endswith("_output"))
    assert output.status == "denied"
    assert output.is_error is True
    assert not target.exists()
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_invalid_side_effect_provider_id_blocks_before_execution(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                {
                    "type": "function_call",
                    "call_id": "write-no-provider-item-id",
                    "name": "write_file",
                    "arguments": {"path": "invalid-id.txt", "content": "no\n", "apply": True, "create": True},
                    "output_index": 0,
                },
                fake_finish("finish-1", output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    output = next(
        item for item in result.transcript.items if item.call_id == "write-no-provider-item-id" and item.kind.endswith("_output")
    )
    assert output.status == "invalid"
    assert output.is_error is True
    assert not (tmp_path / "invalid-id.txt").exists()
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_disallowed_write_root_pairs_failed_without_creation(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-outside-root",
                    "write_file",
                    {"path": "outside.txt", "content": "no\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, allowed_write_roots=[str(allowed)]),
        provider=provider,
    )

    output = next(item for item in result.transcript.items if item.call_id == "write-outside-root" and item.kind.endswith("_output"))
    assert output.status == "failed"
    assert output.is_error is True
    assert not (tmp_path / "outside.txt").exists()


def test_native_harness_proof_manifest_replays_from_response_transcript(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("hello\n", encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("read-1", "read_file", {"path": "sample.txt"}, output_index=0), fake_finish("finish-1", output_index=1)]]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, artifact_root=artifact_root)

    transcript_payload = json.loads((artifact_root / "response_transcript.json").read_text(encoding="utf-8"))
    replayed = NativeTranscript(
        lane_attempt_id=str(transcript_payload["lane_attempt_id"]),
        provider=str(transcript_payload["provider"]),
        model=str(transcript_payload["model"]),
        items=tuple(_native_item_from_payload(item) for item in transcript_payload["items"]),
    )
    expected = native_proof_manifest_from_transcript(replayed)
    expected["transport_kind"] = "fake_native"
    expected["native_transport_kind"] = "provider_native"
    expected["metrics"]["transport_kind"] = "fake_native"
    expected["metrics"]["native_transport_kind"] = "provider_native"

    manifest = json.loads((artifact_root / "proof-manifest.json").read_text(encoding="utf-8"))
    assert manifest["resolver_decisions_ref"] == "resolver_decisions.jsonl"
    assert str(manifest["resolver_decisions_sha256"]).startswith("sha256:")
    assert manifest["native_evidence_observation_ref"] == "native-evidence-observation.json"
    assert str(manifest["native_evidence_observation_sha256"]).startswith("sha256:")
    assert (artifact_root / "native-evidence-observation.json").exists()
    manifest_without_resolver = dict(manifest)
    manifest_without_resolver.pop("resolver_decisions_ref")
    manifest_without_resolver.pop("resolver_decisions_sha256")
    manifest_without_resolver.pop("native_evidence_observation_ref")
    manifest_without_resolver.pop("native_evidence_observation_sha256")
    manifest_without_resolver["metrics"] = dict(manifest_without_resolver["metrics"])
    manifest_without_resolver["metrics"].pop("native_evidence_observation")
    assert manifest_without_resolver == expected


def test_native_harness_adds_first_write_control_after_probe_budget(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(10)
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    second_request = provider.requests[1]
    assert "native_loop_control" not in json.dumps(second_request["input_items"], sort_keys=True)
    payload = _task_payload(second_request)
    assert "persisted_lane_state" not in payload
    assert second_request["provider_request_inventory"]["model_visible_sections"] == [
        "native_transcript_window",
        "task_context_refresh",
    ]
    assert "compact_sidecar_digest" not in payload
    assert (
        second_request["provider_request_inventory"]["compact_sidecar_digest_hash"]
        == _compact_sidecar_digest(second_request)["digest_hash"]
    )
    assert second_request["provider_request_inventory"]["compact_sidecar_digest_wire_visible"] is False
    assert second_request["provider_request_inventory"]["provider_visible_forbidden_fields"]["ok"] is True
    assert "first_write_due" not in json.dumps(_compact_sidecar_digest(second_request), sort_keys=True)
    assert "prewrite_probe_plateau" not in json.dumps(_compact_sidecar_digest(second_request), sort_keys=True)
    assert "workframe_projection" not in _compact_sidecar_digest(second_request)
    signals = _loop_signals(second_request)
    assert signals["first_write_due"] is True
    assert signals["probe_count_without_write"] == 10
    diagnostic_report = second_request["provider_request_inventory"]["diagnostic_only_fields_report"]
    assert diagnostic_report["ok"] is True
    assert diagnostic_report["provider_visible"] is False
    assert "first_write_due" in diagnostic_report["fields"]
    assert "next_action_policy" not in json.dumps(_compact_sidecar_digest(second_request), sort_keys=True)


def test_native_hard_runtime_allows_deeper_prewrite_probe_budget(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(10)
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "goal": (
                "Implement a MIPS ELF interpreter from provided source code "
                "and write the rendered frame to /tmp/frame.bmp."
            )
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=2)

    signals = _loop_signals(provider.requests[1])
    assert signals["first_write_due"] is False
    assert signals["probe_count_without_write"] == 10
    assert signals["first_write_probe_threshold"] == 18
    assert signals["first_write_turn_threshold"] == 10_000


def test_native_hard_runtime_first_write_due_ignores_turn_count_before_plateau(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=0)]
            for index in range(9)
        ]
        + [[fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)]]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "goal": (
                "Implement a MIPS ELF interpreter from provided source code "
                "and write the rendered frame to /tmp/frame.bmp."
            )
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=10)

    signals = _loop_signals(provider.requests[9])
    assert signals["probe_count_without_write"] == 9
    assert signals["first_write_due"] is False
    assert signals["first_write_due_overrun"] is False


def test_native_hard_runtime_first_write_due_still_uses_probe_budget(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(18)
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )
    lane_input = _lane_input(
        tmp_path,
        task_contract={
            "goal": (
                "Implement a MIPS ELF interpreter from provided source code "
                "and write the rendered frame to /tmp/frame.bmp."
            )
        },
    )

    run_native_implement_v2(lane_input, provider=provider, max_turns=2)

    signals = _loop_signals(provider.requests[1])
    assert signals["probe_count_without_write"] == 18
    assert signals["first_write_due"] is True
    assert signals["first_write_due_overrun"] is False


def test_native_harness_observes_prewrite_plateau_without_blocking_live_probes(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(30)
            ],
            [fake_call("read-too-late", "read_file", {"path": "still-probing.txt"}, output_index=0)],
            [
                fake_call(
                    "write-after-plateau",
                    "write_file",
                    {"path": "vm.js", "content": "patched\n", "apply": True, "create": True},
                    output_index=0,
                )
            ],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    second_signals = _loop_signals(provider.requests[1])
    assert second_signals["first_write_due"] is True
    assert second_signals["prewrite_probe_plateau"] is True
    assert second_signals["max_additional_probe_turns"] == 0
    first_batch_outputs = [
        item
        for item in result.transcript.items
        if item.kind.endswith("_output") and item.call_id.startswith("read-") and item.call_id != "read-too-late"
    ]
    assert len(first_batch_outputs) == 30
    assert all("prewrite probe plateau" not in item.output_text_or_ref for item in first_batch_outputs)
    late_probe = next(
        item for item in result.transcript.items if item.call_id == "read-too-late" and item.kind.endswith("_output")
    )
    assert "prewrite probe plateau" not in late_probe.output_text_or_ref
    assert "perform a source mutation" not in late_probe.output_text_or_ref
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "patched\n"


def test_native_harness_observes_first_write_due_without_blocking_live_probes(tmp_path: Path) -> None:
    for index in range(10):
        (tmp_path / f"missing-{index}.txt").write_text(f"seed {index}\n", encoding="utf-8")
    for index in range(5):
        (tmp_path / f"extra-missing-{index}.txt").write_text(f"extra {index}\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(10)
            ],
            [
                fake_call(
                    f"extra-read-{index}",
                    "read_file",
                    {"path": f"extra-missing-{index}.txt"},
                    output_index=index,
                )
                for index in range(5)
            ],
            [fake_call("read-too-late", "search_text", {"path": ".", "query": "more"}, output_index=0)],
            [
                fake_call(
                    "write-after-overrun",
                    "write_file",
                    {"path": "vm.js", "content": "patched\n", "apply": True, "create": True},
                    output_index=0,
                )
            ],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=4)

    third_signals = _loop_signals(provider.requests[2])
    assert third_signals["first_write_due"] is True
    assert third_signals["first_write_due_overrun"] is True
    assert third_signals["max_additional_probe_turns"] == 0
    due_turn_outputs = [
        item
        for item in result.transcript.items
        if item.kind.endswith("_output") and item.call_id.startswith("extra-read-")
    ]
    assert [item.status for item in due_turn_outputs] == ["completed", "completed", "completed", "completed", "completed"]
    assert all("first-write due overrun" not in item.output_text_or_ref for item in due_turn_outputs)
    late_probe = next(
        item for item in result.transcript.items if item.call_id == "read-too-late" and item.kind.endswith("_output")
    )
    assert "first-write due overrun" not in late_probe.output_text_or_ref
    assert "perform a source mutation" not in late_probe.output_text_or_ref
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "patched\n"


def test_native_harness_observes_run_command_source_creation_as_process_side_effect(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(f"read-{index}", "read_file", {"path": f"missing-{index}.txt"}, output_index=index)
                for index in range(10)
            ],
            [
                fake_call(
                    "generate-source",
                    "run_command",
                    {
                        "command": "printf 'ok\\n' > generated.py",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 3,
                        "foreground_budget_seconds": 3,
                        "command_intent": "source_mutation",
                    },
                    output_index=0,
                )
            ],
            [fake_call("read-generated", "read_file", {"path": "generated.py"}, output_index=0)],
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider, artifact_root=artifact_root, max_turns=2)

    output = next(
        item for item in result.transcript.items if item.call_id == "generate-source" and item.kind.endswith("_output")
    )
    assert output.status == "completed"
    assert output.is_error is False
    assert (tmp_path / "generated.py").read_text(encoding="utf-8") == "ok\n"
    tool_route_rows = [
        json.loads(line) for line in (artifact_root / "tool_routes.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    source_creation_route = next(row for row in tool_route_rows if row["provider_call_id"] == "generate-source")
    assert source_creation_route["tool_route"] == "process_runner"


def test_native_harness_instructions_do_not_leak_persisted_lane_state(tmp_path: Path) -> None:
    lane_input = replace(
        _lane_input(tmp_path),
        persisted_lane_state={
            "active_work_todo": {"status": "must-not-leak-active-work-todo"},
            "lane_hard_runtime_frontier": {"status": "must-not-leak-frontier"},
            "lane_repair_history": {"log": ["must-not-leak-repair-history"]},
        },
    )
    provider = NativeFakeProvider.from_item_batches([[fake_finish("finish-1", {"outcome": "blocked"})]])

    run_native_implement_v2(lane_input, provider=provider, max_turns=1)

    request = provider.requests[0]
    assert "must-not-leak" not in request["instructions"]
    assert "implement_v2_workframe" not in request["instructions"]
    assert "implement_v2_lane_state" not in request["instructions"]
    assert "persisted_lane_state" not in json.dumps(request["input_items"], sort_keys=True)


def test_native_harness_first_write_control_does_not_treat_improve_probe_as_verifier(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    f"probe-{index}",
                    "run_command",
                    {"command": "printf self_improve", "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
                    output_index=index,
                )
                for index in range(10)
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    signals = _loop_signals(provider.requests[1])
    assert signals["first_write_due"] is True
    assert signals["verifier_count"] == 0


def test_native_harness_first_write_control_suppressed_by_explicit_verifier_intent(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    f"verify-{index}",
                    "run_command",
                    {
                        "command": "true",
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "command_intent": "verify",
                    },
                    output_index=index,
                )
                for index in range(10)
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=2)

    assert "native_loop_control" not in json.dumps(provider.requests[1]["input_items"], sort_keys=True)
    assert _loop_signals(provider.requests[1])["first_write_due"] is False


def test_native_harness_adds_repair_control_after_failed_verifier_probe_budget(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {"command": "false", "cwd": ".", "command_intent": "verifier"},
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "read-failure",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call(
                    "probe-after-failure",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=1,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    third_request = provider.requests[2]
    signals = _loop_signals(third_request)
    assert signals["verifier_repair_due"] is True
    assert signals["first_write_due"] is False
    assert signals["post_failure_probe_count"] == 2
    assert signals["post_failure_write_count"] == 0
    assert signals["latest_failed_verifier"]["call_id"] == "verify-1"
    assert "next_action_policy" not in json.dumps(_compact_sidecar_digest(third_request), sort_keys=True)


def test_native_harness_treats_semantic_artifact_gap_as_failed_verifier(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "almost\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "printf 'vm finished exit=1 frames=0\n'",
                        "cwd": ".",
                        "command_intent": "verifier",
                    },
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "read-semantic-gap",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call(
                    "probe-after-semantic-gap",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=1,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    signals = _loop_signals(provider.requests[2])
    assert signals["verifier_repair_due"] is True
    assert signals["latest_failed_verifier"]["call_id"] == "verify-1"
    assert signals["latest_failed_verifier"]["status"] == "completed"
    assert signals["latest_failed_verifier"]["semantic_failure"] is True


def test_native_harness_does_not_treat_benign_completed_output_as_failed_verifier(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "ok\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "printf 'vm finished exit=0 frames=0\nno output expected\n'",
                        "cwd": ".",
                        "command_intent": "verifier",
                    },
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "read-benign-output",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call(
                    "probe-after-benign-output",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=1,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert "native_loop_control" not in json.dumps(provider.requests[2]["input_items"], sort_keys=True)


def test_native_harness_adds_repair_control_after_yielded_verifier_poll_failure(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "sleep 0.2; false",
                        "cwd": ".",
                        "command_intent": "verifier",
                        "foreground_budget_seconds": 0.01,
                    },
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "poll-failure",
                    "poll_command",
                    {"command_run_id": command_run_id, "wait_seconds": 1},
                    output_index=0,
                )
            ],
            [
                fake_call(
                    "read-failure",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call(
                    "probe-after-failure",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=1,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=4)

    signals = _loop_signals(provider.requests[3])
    assert signals["verifier_repair_due"] is True
    assert signals["latest_failed_verifier"]["call_id"] == "poll-failure"
    assert signals["latest_failed_verifier"]["status"] == "failed"


def test_native_harness_marks_interrupted_verifier_repair_after_one_probe(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_command",
                    {
                        "command": "printf native-output; sleep 2",
                        "cwd": ".",
                        "command_intent": "verifier",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "cancel-verify",
                    "cancel_command",
                    {"command_run_id": command_run_id, "reason": "verifier stuck"},
                    output_index=0,
                ),
            ],
            [
                fake_call(
                    "probe-after-cancel",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=0,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=4)

    signals = _loop_signals(provider.requests[3])
    assert signals["verifier_repair_due"] is True
    assert signals["post_failure_probe_count"] == 1
    assert signals["failed_verifier_repair_probe_threshold"] == 1
    assert signals["latest_failed_verifier"]["call_id"] == "cancel-verify"
    assert signals["latest_failed_verifier"]["status"] == "interrupted"


def test_native_harness_repair_control_suppressed_after_later_passing_verifier(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {"command": "false", "cwd": ".", "command_intent": "verifier"},
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "verify-2",
                    "run_tests",
                    {"command": "true", "cwd": ".", "command_intent": "verifier"},
                    output_index=0,
                ),
                fake_call(
                    "read-old-failure",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=1,
                ),
                fake_call(
                    "probe-after-pass",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=2,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert "native_loop_control" not in json.dumps(provider.requests[2]["input_items"], sort_keys=True)


def test_native_harness_run_command_verifier_intent_triggers_repair_control(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_command",
                    {"command": "false", "cwd": ".", "command_intent": "verifier"},
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "read-failure",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call(
                    "probe-after-failure",
                    "run_command",
                    {"command": "printf diagnose", "cwd": ".", "command_intent": "diagnostic"},
                    output_index=1,
                ),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    signals = _loop_signals(provider.requests[2])
    assert signals["verifier_repair_due"] is True
    assert signals["latest_failed_verifier"]["call_id"] == "verify-1"


def test_native_harness_repair_control_suppressed_after_failed_verifier_write(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("write-1", "write_file", {"path": "vm.js", "content": "bad\n"}, output_index=0),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {"command": "false", "cwd": ".", "command_intent": "verifier"},
                    output_index=1,
                ),
            ],
            [
                fake_call(
                    "read-failure",
                    "read_command_output",
                    {"command_run_id": command_run_id, "max_chars": 2000},
                    output_index=0,
                ),
                fake_call("write-2", "edit_file", {"path": "vm.js", "old": "bad", "new": "good"}, output_index=1),
            ],
            [fake_finish("finish-1", {"outcome": "blocked", "summary": "stop"}, output_index=0)],
        ]
    )

    run_native_implement_v2(_lane_input(tmp_path), provider=provider, max_turns=3)

    assert "native_loop_control" not in json.dumps(provider.requests[2]["input_items"], sort_keys=True)


def test_native_harness_runs_finish_time_final_verifier_closeout_after_latest_source_mutation(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["final_verifier_closeout_provider_call_id"] == "call-final-verifier-closeout-002"
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "completed"
    assert result.metrics["completion_resolver_latest_decision"]["closeout_refs"]
    closeout_call = next(item for item in result.transcript.items if item.call_id == "call-final-verifier-closeout-002")
    closeout_args = json.loads(closeout_call.arguments_json_text)
    assert closeout_args["command"] == "test -f vm.js"
    assert closeout_args["execution_contract"]["stage"] == "final-verifier"
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "completed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_no_finish_does_not_run_completion_closeout(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                )
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_decision_count"] == 0
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_after_mutation_without_verifier_command_blocks_without_dispatch(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(_lane_input(tmp_path, allow_verify=True), provider=provider, max_turns=1)

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_continue"
    assert "closeout_verifier_command_missing" in result.metrics["completion_resolver_latest_decision"]["blockers"]
    assert "strict_verifier_evidence" in result.metrics["completion_resolver_latest_decision"]["missing_obligations"]
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_verifier_planner_runs_as_separate_agent(tmp_path: Path) -> None:
    class PlanningProvider(NativeFakeProvider):
        planner_requests: list[dict[str, object]]

        def __init__(self) -> None:
            super().__init__(
                NativeFakeProvider.from_item_batches(
                    [
                        [
                            fake_call(
                                "write-1",
                                "write_file",
                                {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                                output_index=0,
                            ),
                            fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
                        ]
                    ]
                ).responses
            )
            self.planner_requests = []

        def plan_finish_verifier_command(self, request: dict[str, object]) -> dict[str, object]:
            self.planner_requests.append(dict(request))
            return {
                "command": "test -f vm.js",
                "cwd": ".",
                "reason": "verify the file created by the implementation",
                "confidence": "high",
            }

    provider = PlanningProvider()

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            experimental_finish_verifier_planner=True,
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "completed"
    assert provider.planner_requests
    assert provider.planner_requests[0]["role"] == "independent_finish_verifier_planner"
    assert "finish claim" in "\n".join(provider.planner_requests[0]["forbidden"])  # type: ignore[index]
    assert result.metrics["final_verifier_closeout_count"] == 1
    closeout_call = next(item for item in result.transcript.items if item.call_id == "call-final-verifier-closeout-002")
    closeout_args = json.loads(closeout_call.arguments_json_text)
    assert closeout_args["command"] == "test -f vm.js"
    assert closeout_args["finish_verifier_plan"]["source"] == "finish_verifier_planner"
    assert closeout_args["finish_verifier_plan"]["separate_agent"] is True
    assert closeout_args["execution_contract"]["acceptance_kind"] == "external_verifier"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_verifier_planner_exit_zero_satisfies_acceptance_constraints(tmp_path: Path) -> None:
    class PlanningProvider(NativeFakeProvider):
        def __init__(self) -> None:
            super().__init__(
                NativeFakeProvider.from_item_batches(
                    [
                        [
                            fake_call(
                                "write-1",
                                "write_file",
                                {"path": "vm.js", "content": "console.log('booted')\n", "apply": True, "create": True},
                                output_index=0,
                            ),
                            fake_finish(
                                "finish-1",
                                {"outcome": "completed", "summary": "done"},
                                output_index=1,
                            ),
                        ]
                    ]
                ).responses
            )

        def plan_finish_verifier_command(self, request: dict[str, object]) -> dict[str, object]:
            return {
                "command": "test -f vm.js",
                "cwd": ".",
                "reason": "verify the implemented task artifact independently",
                "confidence": "high",
            }

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            task_contract={
                "description": "Create vm.js for the runtime task.",
                "acceptance_constraints": ["The runtime task should create vm.js."],
            },
            allow_verify=True,
            experimental_finish_verifier_planner=True,
            final_verifier_closeout_seconds=3,
        ),
        provider=PlanningProvider(),
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "completed"
    assert result.metrics["completion_resolver_latest_decision"]["result"] == "allow"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_configured_verifier_exit_zero_does_not_satisfy_acceptance_constraints(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('booted')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            task_contract={
                "description": "Create vm.js for the runtime task.",
                "acceptance_constraints": ["The runtime task should create vm.js."],
            },
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["finish_gate_block_count"] == 1
    decision = result.metrics["completion_resolver_latest_decision"]
    assert decision["lane_status"] == "blocked_continue"
    assert "acceptance_constraints_unchecked" in decision["blockers"]
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_codex_hot_path_finish_verifier_planner_uses_exec_command_surface(tmp_path: Path) -> None:
    lane_input = _lane_input(
        tmp_path,
        allow_verify=True,
        experimental_finish_verifier_planner=True,
        final_verifier_closeout_seconds=3,
        tool_surface_profile_id=CODEX_HOT_PATH_PROFILE_ID,
    )
    provider = NativeFakeProvider.from_item_batches([])

    closeout_call = _native_final_verifier_closeout_call(
        lane_input,
        lane_attempt_id="attempt-1",
        provider=provider,
        turn_index=2,
        lane_config=lane_input.lane_config,
        plan=_NativeFinishVerifierPlan(
            command="test -f vm.js",
            cwd=".",
            source="finish_verifier_planner",
            reason="verify the file created by the implementation",
        ),
        timeout_seconds=3,
        pending_mutation={"provider_call_id": "write-1", "path": str(tmp_path / "vm.js")},
    )

    assert closeout_call.tool_name == "exec_command"
    assert closeout_call.provider_item_id.startswith("fc_")
    closeout_args = json.loads(closeout_call.arguments_json_text)
    assert closeout_args["cmd"] == "test -f vm.js"
    assert closeout_args["command"] == "test -f vm.js"
    assert closeout_args["finish_verifier_plan"]["source"] == "finish_verifier_planner"
    assert closeout_args["execution_contract"]["acceptance_kind"] == "external_verifier"


@pytest.mark.parametrize(
    "unsafe_command",
    (
        "echo ACCEPTANCE_OK",
        "python -c 'print(\"ACCEPTANCE_OK\")'",
        "true # verifier",
        "test 1 = 1",
        "pytest || true",
        "python -m pytest || exit 0",
        "test -f vm.js; true",
        "pytest | cat",
        "test -f vm.js | cat",
        "pytest & true",
        "test -f vm.js & true",
        "pytest\ntrue",
        "test -f vm.js\ntrue",
        "touch verified && test -f verified",
        "sed -i s/ok/bad/ vm.js && test -f vm.js",
    ),
)
def test_native_harness_finish_verifier_planner_rejects_unsafe_command(
    tmp_path: Path,
    unsafe_command: str,
) -> None:
    class UnsafePlanningProvider(NativeFakeProvider):
        def __init__(self) -> None:
            super().__init__(
                NativeFakeProvider.from_item_batches(
                    [
                        [
                            fake_call(
                                "write-1",
                                "write_file",
                                {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                                output_index=0,
                            ),
                            fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
                        ]
                    ]
                ).responses
            )

        def plan_finish_verifier_command(self, request: dict[str, object]) -> dict[str, object]:
            return {"command": unsafe_command, "reason": "unsafe verifier plan"}

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            experimental_finish_verifier_planner=True,
            final_verifier_closeout_seconds=3,
        ),
        provider=UnsafePlanningProvider(),
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert "closeout_verifier_not_run" in result.metrics["completion_resolver_latest_decision"]["blockers"]
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_time_final_verifier_no_permission_blocks_return_without_dispatch(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_shell=False,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_return"
    assert "closeout_verifier_not_permitted" in result.metrics["completion_resolver_latest_decision"]["blockers"]
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_time_final_verifier_budget_blocks_return_without_dispatch(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=0.01,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_return"
    assert "closeout_verifier_budget_insufficient" in result.metrics["completion_resolver_latest_decision"]["blockers"]
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_suppresses_final_verifier_closeout_after_later_verifier(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_call(
                    "verify-1",
                    "run_command",
                    {"command": "test -f vm.js", "cwd": ".", "command_intent": "verifier"},
                    output_index=1,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=2),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, allow_verify=True, verify_command="test -f vm.js"),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "completed"
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_failed_finish_time_final_verifier_closeout_blocks_resolver(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f missing-output.bin",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_continue"
    assert "closeout_verifier_failed" in result.metrics["completion_resolver_latest_decision"]["blockers"]
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "failed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_semantic_finish_time_final_verifier_closeout_blocks_resolver(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('almost')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="printf 'vm finished exit=1 frames=0\n' >&2",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_continue"
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "completed"
    assert "vm finished exit=1" in closeout_output.output_text_or_ref
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finish_time_closeout_blocks_completion_before_resolver_allows(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f missing-output.bin",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_continue"
    assert any(item.call_id == "finish-1" and item.kind == "finish_output" for item in result.transcript.items)
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "failed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_yielded_verifier_successful_poll_suppresses_closeout(tmp_path: Path) -> None:
    command_run_id = _command_run_id("verify-1")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "sleep 0.2; true",
                        "cwd": ".",
                        "command_intent": "verifier",
                        "foreground_budget_seconds": 0.01,
                    },
                    output_index=1,
                ),
            ],
            [fake_call("poll-verify", "poll_command", {"command_run_id": command_run_id, "wait_seconds": 1}, output_index=0)],
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, allow_verify=True, verify_command="test -f vm.js"),
        provider=provider,
        max_turns=2,
    )

    assert result.metrics["final_verifier_closeout_count"] == 0
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_finalizes_active_verifier_before_deterministic_closeout(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "sleep 0.05; test -f vm.js",
                        "cwd": ".",
                        "command_intent": "verifier",
                        "foreground_budget_seconds": 0,
                        "timeout": 3,
                    },
                    output_index=1,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=2),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=2,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["active_command_closeout_count"] == 1
    assert result.metrics["active_command_closeout_provider_call_id"] == "call-active-command-closeout-002"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "completed"
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    active_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-active-command-closeout-002" and item.kind.endswith("_output")
    )
    assert active_output.status == "completed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_closeout_resolves_only_verifier_typed_gate_missing_obligations() -> None:
    closeout = _NativeCloseoutContext(fresh_verifier_refs=("implement-v2-evidence://attempt/verifier_evidence/run",))
    planner_closeout = _NativeCloseoutContext(
        fresh_verifier_refs=("implement-v2-evidence://attempt/verifier_evidence/planner-run",),
        planner_verified_finish_refs=("implement-v2-evidence://attempt/verifier_evidence/planner-run",),
    )

    assert _finish_gate_missing_obligations(
        {
            "missing_obligations": [
                {"id": "oracle:contract:run:verifier_pass", "kind": "verifier_pass"},
            ],
        }
    ) == ("oracle:contract:run:verifier_pass",)
    assert _finish_gate_block_resolved_by_closeout(
        ("missing_typed_obligation",),
        ("oracle:contract:run:verifier_pass",),
        gate={"missing_obligations": [{"id": "oracle:contract:run:verifier_pass", "kind": "verifier_pass"}]},
        closeout_context=closeout,
    )
    assert not _finish_gate_block_resolved_by_closeout(
        ("missing_typed_obligation",),
        ("oracle:source:doomgeneric_mips",),
        gate={"missing_obligations": [{"id": "oracle:source:doomgeneric_mips", "kind": "source_grounding"}]},
        closeout_context=closeout,
    )
    assert not _finish_gate_block_resolved_by_closeout(
        ("missing_typed_obligation",),
        ("oracle:source:verifier-py",),
        gate={"missing_obligations": [{"id": "oracle:source:verifier-py", "kind": "source_grounding"}]},
        closeout_context=closeout,
    )
    assert not _finish_gate_block_resolved_by_closeout(
        ("failed_typed_evidence_ref",),
        (),
        gate={"failed_evidence_refs": [{"id": "ev:artifact:frame", "kind": "artifact_check"}], "missing_obligations": []},
        closeout_context=closeout,
    )
    assert not _finish_gate_block_resolved_by_closeout(
        ("failed_typed_evidence_ref",),
        (),
        gate={"failed_evidence_refs": [{"id": "ev:artifact:frame", "kind": "artifact_check"}], "missing_obligations": []},
        closeout_context=planner_closeout,
    )
    assert _finish_gate_block_resolved_by_closeout(
        ("acceptance_constraints_unchecked",),
        (),
        gate={"blockers": [{"code": "acceptance_constraints_unchecked"}], "missing_obligations": []},
        closeout_context=planner_closeout,
    )
    assert not _finish_gate_block_resolved_by_closeout(
        ("acceptance_constraints_unchecked",),
        (),
        gate={"blockers": [{"code": "acceptance_constraints_unchecked"}], "missing_obligations": []},
        closeout_context=closeout,
    )


def test_native_finish_tool_result_alias_resolves_verifier_closeout_context() -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="verify-call",
        mew_tool_call_id="native:verify-call",
        tool_name="exec_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "execution_contract": {
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
                "verifier_evidence": {"verdict": "pass"},
            },
        ),
        evidence_refs=(
            "implement-v2-exec://attempt/command-verify/terminal",
            "implement-v2-evidence://attempt/command_run/command-verify",
            "implement-v2-evidence://attempt/verifier_evidence/verifier-verify",
            "implement-v2-evidence://attempt/structured_finish_gate/finish-gate",
        ),
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:verify-call",),
        (verifier,),
    )

    assert context.fresh_verifier_refs == (
        "implement-v2-exec://attempt/command-verify/terminal",
        "implement-v2-evidence://attempt/command_run/command-verify",
        "implement-v2-evidence://attempt/verifier_evidence/verifier-verify",
    )
    assert "structured_finish_gate" not in " ".join(context.fresh_verifier_refs)


def test_native_finish_tool_result_alias_resolves_unknown_verdict_verify_command() -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="exec-verify",
        mew_tool_call_id="native:exec-verify",
        tool_name="exec_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "command_intent": "verify",
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        evidence_refs=(
            "implement-v2-exec://attempt/command-exec-verify/terminal",
            "implement-v2-evidence://attempt/verifier_evidence/verifier-exec-verify",
        ),
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:exec-verify",),
        (verifier,),
    )

    assert context.fresh_verifier_refs == (
        "implement-v2-exec://attempt/command-exec-verify/terminal",
        "implement-v2-evidence://attempt/verifier_evidence/verifier-exec-verify",
    )


def test_native_finish_tool_route_alias_resolves_polled_acceptance_pass() -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="poll-verify",
        mew_tool_call_id="native:poll-verify",
        tool_name="write_stdin",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout_tail": "Modules were successfully checked\nACCEPTANCE: PASS final verifier succeeded",
                "execution_contract_normalized": {
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "stage": "command",
                },
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        content_refs=("implement-v2-exec://attempt/command-poll/output",),
        evidence_refs=(
            "implement-v2-exec://attempt/command-poll/terminal",
            "implement-v2-evidence://attempt/command_run/command-poll",
            "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
            "implement-v2-evidence://attempt/failure_classification/failure-poll",
            "implement-v2-evidence://attempt/structured_finish_gate/finish-gate",
        ),
        route_decision={"ref": "tool-route:poll-verify"},
    )

    context = _native_finish_supplied_closeout_context(
        ("tool-route:poll-verify",),
        (verifier,),
    )

    assert context.fresh_verifier_refs == (
        "implement-v2-exec://attempt/command-poll/output",
        "implement-v2-exec://attempt/command-poll/terminal",
        "implement-v2-evidence://attempt/command_run/command-poll",
        "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
    )
    joined = " ".join(context.fresh_verifier_refs)
    assert "failure_classification" not in joined
    assert "structured_finish_gate" not in joined


def test_native_finish_tool_result_alias_resolves_polled_acceptance_ok_marker() -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="poll-verify",
        mew_tool_call_id="native:poll-verify",
        tool_name="write_stdin",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout_tail": "ACCEPTANCE_OK: verifier rebuilt the artifact and final checks passed",
                "execution_contract_normalized": {
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "stage": "command",
                },
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        content_refs=("implement-v2-exec://attempt/command-poll/output",),
        evidence_refs=(
            "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
        ),
        route_decision={"ref": "tool-route:poll-verify", "tool_route": "process_lifecycle"},
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:poll-verify",),
        (verifier,),
    )

    assert context.fresh_verifier_refs == (
        "implement-v2-exec://attempt/command-poll/output",
        "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
    )


def test_native_finish_tool_result_alias_rejects_polled_output_without_acceptance_pass() -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="poll-verify",
        mew_tool_call_id="native:poll-verify",
        tool_name="write_stdin",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout_tail": "command finished without an explicit verifier pass marker",
                "execution_contract_normalized": {
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "stage": "command",
                },
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        content_refs=("implement-v2-exec://attempt/command-poll/output",),
        evidence_refs=(
            "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
        ),
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:poll-verify",),
        (verifier,),
    )

    assert context == _NativeCloseoutContext()


@pytest.mark.parametrize(
    "stdout_tail",
    (
        "NOT ACCEPTANCE_OK: final verifier failed",
        "final acceptance okay: not a strict marker",
        "FINAL_ACCEPTANCE_OKAY but still reviewing",
        "noise output_tail: ACCEPTANCE_OK",
    ),
)
def test_native_finish_tool_result_alias_rejects_negated_or_extended_acceptance_marker(stdout_tail: str) -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="poll-verify",
        mew_tool_call_id="native:poll-verify",
        tool_name="write_stdin",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout_tail": stdout_tail,
                "execution_contract_normalized": {
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "stage": "command",
                },
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        content_refs=("implement-v2-exec://attempt/command-poll/output",),
        evidence_refs=(
            "implement-v2-evidence://attempt/verifier_evidence/verifier-poll",
        ),
        route_decision={"ref": "tool-route:poll-verify", "tool_route": "process_lifecycle"},
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:poll-verify",),
        (verifier,),
    )

    assert context == _NativeCloseoutContext()


def test_native_finish_tool_result_alias_rejects_non_lifecycle_acceptance_text() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="generic-pass",
        mew_tool_call_id="native:generic-pass",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "stdout_tail": "ACCEPTANCE: PASS ordinary command output",
                "execution_contract_normalized": {
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "stage": "command",
                },
                "verifier_evidence": {"verdict": "unknown"},
            },
        ),
        content_refs=("implement-v2-exec://attempt/generic/output",),
        evidence_refs=(
            "implement-v2-evidence://attempt/verifier_evidence/generic",
        ),
        route_decision={"ref": "tool-route:generic-pass", "tool_route": "process_runner"},
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:generic-pass",),
        (result,),
    )

    assert context == _NativeCloseoutContext()


def test_native_finish_tool_result_alias_does_not_resolve_non_verifier_result() -> None:
    read_result = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="read-call",
        mew_tool_call_id="native:read-call",
        tool_name="read_file",
        status="completed",
        content=({"path": "plus_comm.v", "text": "Theorem plus_comm..."},),
        evidence_refs=(
            "implement-v2-evidence://attempt/tool_run_record/read-call",
            "implement-v2-evidence://attempt/verifier_evidence/spurious-read-ref",
        ),
    )

    context = _native_finish_supplied_closeout_context(
        ("ev:tool_result:read-call",),
        (read_result,),
    )

    assert context == _NativeCloseoutContext()


def test_native_completion_resolver_accepts_finish_cited_verifier_alias_after_missing_closeout_command(
    tmp_path: Path,
) -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="verify-call",
        mew_tool_call_id="native:verify-call",
        tool_name="exec_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "execution_contract": {
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
                "verifier_evidence": {"verdict": "pass"},
            },
        ),
        evidence_refs=(
            "implement-v2-exec://attempt/command-verify/terminal",
            "implement-v2-evidence://attempt/command_run/command-verify",
            "implement-v2-evidence://attempt/verifier_evidence/verifier-verify",
        ),
    )
    finish_call = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt",
        provider="codex",
        model="gpt-5.5",
        kind="finish_call",
        call_id="finish-call",
        tool_name="finish",
        arguments_json_text=json.dumps(
            {
                "outcome": "completed",
                "summary": "verified",
                "evidence_refs": ["ev:tool_result:verify-call"],
            }
        ),
    )
    finish_result = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="finish-call",
        mew_tool_call_id="native:finish-call",
        tool_name="finish",
        status="completed",
        content=({"summary": "verified", "outcome": "completed"},),
        evidence_refs=("native-finish://accepted",),
    )

    resolver_input = _completion_resolver_input_from_finish(
        finish_call,
        finish_result,
        lane_input=_lane_input(tmp_path),
        transcript_items=(finish_call,),
        request_descriptor={},
        prior_tool_results=(verifier,),
        closeout_context=_NativeCloseoutContext(
            blockers=("closeout_verifier_command_missing",),
            missing_obligations=("strict_verifier_evidence",),
        ),
    )

    assert "closeout_verifier_command_missing" not in resolver_input.blockers
    assert "strict_verifier_evidence" not in resolver_input.missing_obligations
    assert resolver_input.fresh_verifier_refs == (
        "implement-v2-exec://attempt/command-verify/terminal",
        "implement-v2-evidence://attempt/command_run/command-verify",
        "implement-v2-evidence://attempt/verifier_evidence/verifier-verify",
    )


def test_native_completion_resolver_rejects_finish_cited_stale_verifier_before_later_mutation(
    tmp_path: Path,
) -> None:
    verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="verify-call",
        mew_tool_call_id="native:verify-call",
        tool_name="exec_command",
        status="completed",
        content=(
            {
                "exit_code": 0,
                "execution_contract": {
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
                "verifier_evidence": {"verdict": "pass"},
            },
        ),
        evidence_refs=(
            "implement-v2-exec://attempt/command-verify/terminal",
            "implement-v2-evidence://attempt/command_run/command-verify",
            "implement-v2-evidence://attempt/verifier_evidence/verifier-verify",
        ),
    )
    later_mutation = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="write-after-verify",
        mew_tool_call_id="native:write-after-verify",
        tool_name="write_file",
        status="completed",
        content=({"path": str(tmp_path / "plus_comm.v"), "written": True},),
        side_effects=(
            {
                "kind": "source_tree_mutation",
                "record": {
                    "changed_count": 1,
                    "changes": [{"path": str(tmp_path / "plus_comm.v"), "change": "modified"}],
                },
            },
        ),
    )
    finish_call = NativeTranscriptItem(
        sequence=1,
        turn_id="turn-1",
        lane_attempt_id="attempt",
        provider="codex",
        model="gpt-5.5",
        kind="finish_call",
        call_id="finish-call",
        tool_name="finish",
        arguments_json_text=json.dumps(
            {
                "outcome": "completed",
                "summary": "verified",
                "evidence_refs": ["ev:tool_result:verify-call"],
            }
        ),
    )
    finish_result = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="finish-call",
        mew_tool_call_id="native:finish-call",
        tool_name="finish",
        status="completed",
        content=({"summary": "verified", "outcome": "completed"},),
        evidence_refs=("native-finish://accepted",),
    )

    resolver_input = _completion_resolver_input_from_finish(
        finish_call,
        finish_result,
        lane_input=_lane_input(tmp_path),
        transcript_items=(finish_call,),
        request_descriptor={},
        prior_tool_results=(verifier, later_mutation),
        closeout_context=_NativeCloseoutContext(
            blockers=("closeout_verifier_command_missing",),
            missing_obligations=("strict_verifier_evidence",),
        ),
    )

    assert resolver_input.fresh_verifier_refs == ()
    assert "closeout_verifier_command_missing" in resolver_input.blockers
    assert "strict_verifier_evidence" in resolver_input.missing_obligations


def test_native_harness_active_verifier_closeout_cancels_when_budget_exhausted(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('ok')\n", "apply": True, "create": True},
                    output_index=0,
                ),
                fake_call(
                    "verify-1",
                    "run_tests",
                    {
                        "command": "sleep 5; test -f vm.js",
                        "cwd": ".",
                        "command_intent": "verifier",
                        "foreground_budget_seconds": 0,
                        "timeout": 5,
                    },
                    output_index=1,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=2),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="test -f vm.js",
            final_verifier_closeout_seconds=0.01,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["active_command_closeout_count"] == 1
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "blocked_return"
    active_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-active-command-closeout-002" and item.kind.endswith("_output")
    )
    assert active_output.status == "interrupted"
    assert "budget exhausted" in active_output.output_text_or_ref
    assert not any("a managed command is already running" in item.output_text_or_ref for item in result.transcript.items)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_final_verifier_closeout_detects_write_file_source_mutation(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "generate-source",
                    "write_file",
                    {"path": "generated.py", "content": "print(1)\n", "create": True, "apply": True},
                    output_index=0,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=1),
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(
            tmp_path,
            allow_verify=True,
            verify_command="python generated.py",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["first_write_latency"]["call_id"] == "generate-source"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["completion_resolver_latest_decision"]["lane_status"] == "completed"
    assert any(item.call_id == "call-final-verifier-closeout-002" for item in result.transcript.items)


def _native_item_from_payload(payload: dict[str, object]) -> NativeTranscriptItem:
    fields = {
        "sequence",
        "turn_id",
        "kind",
        "lane_attempt_id",
        "provider",
        "model",
        "response_id",
        "provider_item_id",
        "output_index",
        "call_id",
        "tool_name",
        "arguments_json_text",
        "custom_input_text",
        "output_text_or_ref",
        "status",
        "is_error",
        "raw_ref",
        "encrypted_reasoning_ref",
        "metrics_ref",
        "content_refs",
        "evidence_refs",
        "sidecar_refs",
    }
    kwargs = {key: payload[key] for key in fields if key in payload}
    for key in ("content_refs", "evidence_refs", "sidecar_refs"):
        if key in kwargs:
            kwargs[key] = tuple(kwargs[key])
    return NativeTranscriptItem(**kwargs)
