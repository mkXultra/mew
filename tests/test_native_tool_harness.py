import json
from pathlib import Path
from unittest.mock import patch

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
    assert second_request["input_items"][-1]["role"] == "user"
    control_items = [
        item
        for item in second_request["input_items"]
        if isinstance(item, dict)
        and item.get("role") == "user"
        and "native_loop_control" in json.dumps(item, sort_keys=True)
    ]
    assert control_items
    payload = json.loads(control_items[-1]["content"][0]["text"])
    assert payload["native_loop_control"]["first_write_due"] is True
    assert payload["native_loop_control"]["probe_count_without_write"] == 10
    assert payload["native_loop_control"]["next_action_policy"] == "source_mutation_or_verifier_or_blocked_finish"


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

    control_text = provider.requests[1]["input_items"][-1]["content"][0]["text"]
    payload = json.loads(control_text)
    assert payload["native_loop_control"]["first_write_due"] is True
    assert payload["native_loop_control"]["verifier_count"] == 0


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
