import json
from pathlib import Path
from dataclasses import replace
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
from mew.implement_lane.types import ImplementLaneInput


def _lane_input(tmp_path: Path, **lane_config: object) -> ImplementLaneInput:
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
    )


def _command_run_id(call_id: str) -> str:
    import hashlib

    lane_attempt_id = "ws-native:task-native:implement_v2:native"
    digest = hashlib.sha256(f"{lane_attempt_id}:{call_id}".encode()).hexdigest()
    return f"{lane_attempt_id}:command:{call_id}-{digest[:8]}"


def _task_payload(request: dict[str, object]) -> dict[str, object]:
    first = request["input_items"][0]  # type: ignore[index]
    return json.loads(first["content"][0]["text"])  # type: ignore[index]


def _compact_sidecar_digest(request: dict[str, object]) -> dict[str, object]:
    return _task_payload(request)["compact_sidecar_digest"]


def _loop_signals(request: dict[str, object]) -> dict[str, object]:
    digest = _compact_sidecar_digest(request)
    return digest["workframe_projection"]["loop_signals"]


def _verifier_state(request: dict[str, object]) -> dict[str, object]:
    digest = _compact_sidecar_digest(request)
    return digest["workframe_projection"]["verifier_state"]


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
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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
    assert inventory_payload["provider_request_inventory"][0]["model_visible_sections"] == [
        "native_transcript_window",
        "compact_sidecar_digest",
    ]


def test_live_native_provider_failure_writes_request_inventory_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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
    assert inventory_payload["request_count"] == 1
    assert inventory_payload["provider_request_inventory"][0]["model_visible_sections"] == [
        "native_transcript_window",
        "compact_sidecar_digest",
    ]


def test_live_native_first_turn_value_error_writes_failure_artifacts(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    lane_input = _lane_input(tmp_path, artifact_dir=str(artifact_root))

    with patch(
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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
    request_payload = json.loads((artifact_root / "native-provider-requests.json").read_text(encoding="utf-8"))
    assert request_payload["status"] == "failed_before_native_response"
    assert request_payload["request_count"] == 2


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
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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
        "mew.implement_lane.native_tool_harness.call_codex_native_responses",
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

    assert result.status == "completed"
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
    assert all(item.status in {"completed", "yielded", "interrupted"} for item in outputs)
    assert result.metrics["first_write_latency"]["call_id"] == "write-1"
    assert result.metrics["first_write_latency_turn"] == 1
    assert "first_write_latency_turns" not in result.metrics
    assert len(result.metrics["tool_latency"]) == 7


def test_native_harness_invalid_arguments_get_paired_output(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [[fake_call("bad-args", "read_file", "{not-json", output_index=0), fake_finish("finish-1", output_index=1)]]
    )

    result = run_native_implement_v2(_lane_input(tmp_path), provider=provider)

    bad_output = next(item for item in result.transcript.items if item.call_id == "bad-args" and item.kind.endswith("_output"))
    assert bad_output.status == "invalid"
    assert bad_output.is_error is True
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
    assert manifest == expected


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
        "compact_sidecar_digest",
    ]
    assert second_request["provider_request_inventory"]["compact_sidecar_digest_hash"] == payload["compact_sidecar_digest"]["digest_hash"]
    signals = _loop_signals(second_request)
    assert signals["first_write_due"] is True
    assert signals["probe_count_without_write"] == 10
    assert "next_action_policy" not in json.dumps(_compact_sidecar_digest(second_request), sort_keys=True)


def test_native_harness_blocks_more_probes_after_prewrite_plateau(tmp_path: Path) -> None:
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
    blocked = next(item for item in result.transcript.items if item.call_id == "read-too-late" and item.kind.endswith("_output"))
    assert blocked.status == "invalid"
    assert blocked.is_error is True
    assert "prewrite probe plateau" in blocked.output_text_or_ref
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "patched\n"


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


def test_native_harness_runs_final_verifier_closeout_after_latest_source_mutation(tmp_path: Path) -> None:
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

    assert result.status == "completed"
    assert result.finish_summary == "native final verifier closeout passed; completing without another model turn"
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert result.metrics["final_verifier_closeout_provider_call_id"] == "call-final-verifier-closeout-002"
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
            ]
        ]
    )

    result = run_native_implement_v2(
        _lane_input(tmp_path, allow_verify=True, verify_command="test -f vm.js"),
        provider=provider,
        max_turns=1,
    )

    assert result.metrics["final_verifier_closeout_count"] == 0
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_failed_final_verifier_closeout_remains_blocked(tmp_path: Path) -> None:
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
            verify_command="test -f missing-output.bin",
            final_verifier_closeout_seconds=3,
        ),
        provider=provider,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["final_verifier_closeout_count"] == 1
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "failed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_semantic_final_verifier_closeout_remains_blocked(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "write-1",
                    "write_file",
                    {"path": "vm.js", "content": "console.log('almost')\n", "apply": True, "create": True},
                    output_index=0,
                )
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
    assert result.finish_summary == ""
    assert result.metrics["final_verifier_closeout_count"] == 1
    closeout_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-final-verifier-closeout-002" and item.kind.endswith("_output")
    )
    assert closeout_output.status == "completed"
    assert "vm finished exit=1" in closeout_output.output_text_or_ref
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_completed_finish_without_later_verifier_is_downgraded_by_closeout(tmp_path: Path) -> None:
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
    assert result.finish_summary == "native active verifier closeout passed; completing without another model turn"
    assert result.metrics["active_command_closeout_count"] == 1
    assert result.metrics["active_command_closeout_provider_call_id"] == "call-active-command-closeout-002"
    assert result.metrics["final_verifier_closeout_count"] == 0
    assert not any("final-verifier-closeout" in item.call_id for item in result.transcript.items if item.call_id)
    active_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-active-command-closeout-002" and item.kind.endswith("_output")
    )
    assert active_output.status == "completed"
    assert validate_native_transcript_pairing(result.transcript).valid is True


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
    active_output = next(
        item
        for item in result.transcript.items
        if item.call_id == "call-active-command-closeout-002" and item.kind.endswith("_output")
    )
    assert active_output.status == "interrupted"
    assert "budget exhausted" in active_output.output_text_or_ref
    assert not any("a managed command is already running" in item.output_text_or_ref for item in result.transcript.items)
    assert validate_native_transcript_pairing(result.transcript).valid is True


def test_native_harness_final_verifier_closeout_detects_run_command_source_mutation(tmp_path: Path) -> None:
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "generate-source",
                    "run_command",
                    {
                        "command": "printf 'print(1)\\n' > generated.py",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 3,
                        "foreground_budget_seconds": 3,
                    },
                    output_index=0,
                )
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
