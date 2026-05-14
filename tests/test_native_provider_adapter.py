import json
from unittest.mock import patch

from mew.implement_lane.native_provider_adapter import (
    ENCRYPTED_REASONING_INCLUDE,
    NativeProviderCapabilities,
    build_custom_tool_call_output_input_item,
    build_function_call_output_input_item,
    build_reasoning_sidecar,
    build_reasoning_sidecar_entry,
    build_responses_request_descriptor,
    apply_previous_response_delta,
    call_codex_native_responses,
    call_codex_native_responses_websocket,
    parse_responses_stream_events,
    read_reasoning_sidecar,
    reasoning_carry_forward_refs,
    reasoning_sidecar_digest,
    responses_events_from_raw,
    validate_reasoning_sidecar_refs,
    write_reasoning_sidecar,
)
from mew.implement_lane.native_tool_schema import (
    lower_implement_lane_tool_specs,
    provider_tool_spec_hash,
)
from mew.implement_lane.native_transcript import (
    NativeTranscript,
    NativeTranscriptItem,
    native_transcript_hash,
)
from mew.implement_lane.tool_policy import list_v2_base_tool_specs
from mew.implement_lane.tool_registry import build_tool_surface_snapshot


def _input_item() -> dict[str, object]:
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": "Implement the task."}],
    }


def test_request_descriptor_records_native_transport_hashes_headers_and_reasoning_refs() -> (
    None
):
    entry = build_reasoning_sidecar_entry(
        response_id="resp-prev",
        provider_item_id="rs-prev",
        turn_id="turn-prev",
        encrypted_content="encrypted-blob",
    )
    sidecar = build_reasoning_sidecar(
        lane_attempt_id="attempt-1", provider="openai", items=[entry]
    )
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        reasoning={"effort": "medium"},
        reasoning_sidecar=sidecar,
        headers={
            "Authorization": "Bearer secret",
            "x-codex-turn-state": "sticky",
            "Cookie": "session=secret",
        },
        provider_request_id="req-test-1",
        prompt_cache_key="attempt-1",
    )
    request = descriptor["request_body"]

    assert descriptor["transport_change"] == "yes"
    assert descriptor["transport_kind"] == "provider_native"
    assert descriptor["provider_request_id"] == "req-test-1"
    assert request["store"] is False  # type: ignore[index]
    assert request["stream"] is True  # type: ignore[index]
    assert "previous_response_id" not in request
    assert descriptor["previous_response_id"] is None
    assert descriptor["previous_response_id_in_request_body"] is False
    assert request["include"] == [ENCRYPTED_REASONING_INCLUDE]  # type: ignore[index]
    assert descriptor["safe_headers"] == {"x-codex-turn-state": "sticky"}
    assert descriptor["excluded_unsafe_header_names"] == ["authorization", "cookie"]
    assert descriptor["reasoning_sidecar_refs_used"] == [entry["ref"]]
    assert descriptor["sidecar_digest_hash"] == reasoning_sidecar_digest(sidecar)
    assert str(descriptor["transcript_window_hash"]).startswith("sha256:")
    assert str(descriptor["request_hash"]).startswith("sha256:")
    assert str(descriptor["descriptor_hash"]).startswith("sha256:")
    assert descriptor["capability_decisions"]["provider_native_tool_loop"] is True  # type: ignore[index]
    assert descriptor["capability_decisions"]["apply_patch_transport"] == "custom"  # type: ignore[index]
    assert descriptor["tool_spec_hash"] == provider_tool_spec_hash(
        lower_implement_lane_tool_specs(list_v2_base_tool_specs())
    )


def test_request_descriptor_preserves_codex_like_tool_order_and_collapsed_descriptions() -> None:
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        tool_specs=list_v2_base_tool_specs(),
        provider_request_id="req-tool-order",
    )
    tools = descriptor["request_body"]["tools"]  # type: ignore[index]
    names = [str(tool.get("name") or "") for tool in tools]  # type: ignore[union-attr]
    descriptions = "\n".join(str(tool.get("description") or "") for tool in tools)  # type: ignore[union-attr]

    assert names[:5] == ["apply_patch", "edit_file", "write_file", "run_command", "run_tests"]
    assert names[-1] == "finish"
    assert "Primary source mutation tool" in descriptions
    assert "smallest runnable candidate" in descriptions
    assert "cheap probe" not in descriptions
    assert "fallback-probe" not in descriptions
    assert "frontier" not in descriptions


def test_request_descriptor_records_tool_surface_metadata_without_changing_tools() -> None:
    tool_specs = list_v2_base_tool_specs()
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=(),
        available_provider_tool_names=tuple(spec.name for spec in tool_specs),
    )
    baseline = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        tool_specs=snapshot.tool_specs,
        provider_request_id="req-tool-surface-baseline",
    )
    with_surface = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        tool_specs=snapshot.tool_specs,
        provider_request_id="req-tool-surface",
        tool_surface_snapshot=snapshot.request_metadata(),
    )

    assert (
        with_surface["request_body"]["tools"]  # type: ignore[index]
        == baseline["request_body"]["tools"]  # type: ignore[index]
    )
    assert with_surface["tool_surface_profile_id"] == "mew_legacy"
    assert with_surface["tool_surface_prompt_contract_id"] == "mew_legacy_prompt_v1"
    assert with_surface["tool_surface"]["descriptor_hash"] == snapshot.descriptor_hash  # type: ignore[index]
    assert with_surface["capability_decisions"]["tool_surface_profile_id"] == "mew_legacy"  # type: ignore[index]


def test_request_descriptor_normalizes_tool_surface_parallel_metadata_to_provider_caps() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=(),
    )
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        tool_specs=snapshot.tool_specs,
        capabilities=NativeProviderCapabilities(supports_parallel_tool_calls=False),
        provider_request_id="req-tool-surface-no-parallel",
        tool_surface_snapshot=snapshot.request_metadata(),
    )

    assert descriptor["request_body"]["parallel_tool_calls"] is False  # type: ignore[index]
    assert descriptor["tool_surface"]["parallel_tool_calls_requested"] is True  # type: ignore[index]
    assert descriptor["tool_surface"]["parallel_tool_calls_effective"] is False  # type: ignore[index]


def test_request_descriptor_records_apply_patch_json_fallback_when_custom_tools_unavailable() -> None:
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        transcript_window=[{"sequence": 1, "kind": "input_message"}],
        tool_specs=list_v2_base_tool_specs(),
        capabilities=NativeProviderCapabilities(supports_custom_freeform_tools=False),
        provider_request_id="req-tool-fallback",
    )
    tools = descriptor["request_body"]["tools"]  # type: ignore[index]
    apply_patch = next(tool for tool in tools if tool.get("name") == "apply_patch")  # type: ignore[union-attr]

    assert apply_patch["type"] == "function"
    assert apply_patch["strict"] is False
    assert descriptor["capability_decisions"]["apply_patch_transport"] == "json_fallback"  # type: ignore[index]
    assert descriptor["strict_false_reasons"] == {
        "apply_patch": "custom_freeform_apply_patch_not_supported"
    }


def test_previous_response_delta_uses_suffix_when_logical_prefix_matches() -> None:
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
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item(), call_item, output_item],
        provider_request_id="req-delta",
    )

    updated = apply_previous_response_delta(
        descriptor,
        previous_response_id="resp-prev",
        previous_logical_input_items=[_input_item()],
        previous_response_output_items=[call_item],
    )
    request = updated["request_body"]

    assert request["previous_response_id"] == "resp-prev"  # type: ignore[index]
    assert request["input"] == [output_item]  # type: ignore[index]
    assert updated["previous_response_id"] == "resp-prev"
    assert updated["previous_response_id_in_request_body"] is True
    assert updated["previous_response_delta_mode"] == "delta"
    assert updated["previous_response_prefix_item_count"] == 2
    assert updated["logical_input_item_count"] == 3
    assert updated["wire_input_item_count"] == 1
    assert updated["capability_decisions"]["request_previous_response_id"] == "resp-prev"  # type: ignore[index]


def test_previous_response_delta_allows_context_refresh_before_previous_prefix() -> None:
    previous_context = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task_contract": {"title": "Task"},
                        "compact_sidecar_digest": {"digest_hash": "old"},
                        "workspace": "/repo",
                        "lane": "implement_v2",
                    }
                ),
            }
        ],
    }
    refreshed_context = {
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": json.dumps(
                    {
                        "task_contract": {"title": "Task"},
                        "compact_sidecar_digest": {"digest_hash": "new"},
                        "workspace": "/repo",
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
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[refreshed_context, call_item, output_item],
        provider_request_id="req-refresh-delta",
    )

    updated = apply_previous_response_delta(
        descriptor,
        previous_response_id="resp-prev",
        previous_logical_input_items=[previous_context],
        previous_response_output_items=[call_item],
    )
    request = updated["request_body"]

    assert request["previous_response_id"] == "resp-prev"  # type: ignore[index]
    assert request["input"] == [refreshed_context, output_item]  # type: ignore[index]
    assert updated["logical_input_items"] == [refreshed_context, call_item, output_item]
    assert updated["suppressed_context_refresh_items"] == []
    assert updated["previous_response_delta_mode"] == "delta_with_context_refresh"
    assert updated["previous_response_prefix_item_count"] == 2
    assert updated["previous_response_leading_refresh_item_count"] == 1
    assert updated["previous_response_suppressed_context_refresh_item_count"] == 0
    assert updated["logical_input_item_count"] == 3
    assert updated["wire_input_item_count"] == 2


def test_previous_response_delta_falls_back_to_full_input_on_prefix_miss() -> None:
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        provider_request_id="req-full",
    )

    updated = apply_previous_response_delta(
        descriptor,
        previous_response_id="resp-prev",
        previous_logical_input_items=[{"role": "user", "content": []}],
        previous_response_output_items=[],
    )
    request = updated["request_body"]

    assert "previous_response_id" not in request
    assert request["input"] == [_input_item()]  # type: ignore[index]
    assert updated["previous_response_id"] is None
    assert updated["previous_response_id_in_request_body"] is False
    assert updated["previous_response_delta_mode"] == "prefix_miss"


def test_request_descriptor_omits_encrypted_reasoning_include_when_not_reasoning() -> (
    None
):
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        capabilities=NativeProviderCapabilities(supports_encrypted_reasoning=True),
    )

    assert "include" not in descriptor["request_body"]
    assert descriptor["capability_decisions"]["encrypted_reasoning_requested"] is False  # type: ignore[index]


def test_request_descriptor_omits_encrypted_reasoning_include_when_provider_cannot_support_it() -> (
    None
):
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        capabilities=NativeProviderCapabilities(supports_encrypted_reasoning=False),
        reasoning={"effort": "medium"},
    )

    request = descriptor["request_body"]
    assert request["reasoning"] == {"effort": "medium"}  # type: ignore[index]
    assert "include" not in request
    assert descriptor["capability_decisions"]["encrypted_reasoning_requested"] is False  # type: ignore[index]


def test_function_and_custom_tool_output_input_items_are_provider_native() -> None:
    assert build_function_call_output_input_item(
        call_id="call-read", output="read_file result: completed"
    ) == {
        "type": "function_call_output",
        "call_id": "call-read",
        "output": "read_file result: completed",
    }
    assert build_custom_tool_call_output_input_item(
        call_id="call-patch",
        name="apply_patch",
        output="apply_patch result: completed",
    ) == {
        "type": "custom_tool_call_output",
        "call_id": "call-patch",
        "name": "apply_patch",
        "output": "apply_patch result: completed",
    }


def test_reasoning_sidecar_round_trip_refs_hashes_and_descriptor_carry_forward(
    tmp_path,
) -> None:
    entry = build_reasoning_sidecar_entry(
        response_id="resp-1",
        provider_item_id="rs-1",
        turn_id="turn-1",
        encrypted_content="opaque-encrypted-content",
    )
    sidecar = build_reasoning_sidecar(
        lane_attempt_id="attempt-1", provider="openai", items=[entry]
    )
    sidecar_path = write_reasoning_sidecar(tmp_path / "reasoning_sidecar.json", sidecar)
    loaded = read_reasoning_sidecar(sidecar_path)
    transcript = NativeTranscript(
        lane_attempt_id="attempt-1",
        provider="openai",
        model="gpt-5.5",
        items=(
            NativeTranscriptItem(
                sequence=1,
                turn_id="turn-1",
                lane_attempt_id="attempt-1",
                provider="openai",
                model="gpt-5.5",
                kind="reasoning",
                provider_item_id="rs-1",
                encrypted_reasoning_ref=str(entry["ref"]),
            ),
        ),
    )

    validation = validate_reasoning_sidecar_refs(transcript, loaded)
    assert validation.valid is True
    assert validation.refs_resolved == (entry["ref"],)
    assert (
        entry["encrypted_content_sha256"]
        == loaded["items"][0]["encrypted_content_sha256"]
    )  # type: ignore[index]
    assert "opaque-encrypted-content" not in json.dumps(
        transcript.as_dict(), sort_keys=True
    )
    transcript_hash = native_transcript_hash(transcript)
    loaded["items"][0]["encrypted_content_bytes"] = "different-bytes"  # type: ignore[index]
    assert native_transcript_hash(transcript) == transcript_hash

    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        reasoning={"effort": "medium"},
        reasoning_sidecar=sidecar,
    )
    assert reasoning_carry_forward_refs(sidecar) == (entry["ref"],)
    assert descriptor["reasoning_sidecar_refs_used"] == [entry["ref"]]


def test_stream_parser_accumulates_function_call_arguments_and_usage() -> None:
    result = parse_responses_stream_events(
        [
            {
                "type": "response.created",
                "response": {"id": "resp-1", "metadata": {"request_id": "req-1"}},
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "fc-1",
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "read_file",
                },
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": '{"path":"',
            },
            {
                "type": "response.function_call_arguments.delta",
                "output_index": 0,
                "delta": 'src/mew/a.py"}',
            },
            {
                "type": "response.function_call_arguments.done",
                "output_index": 0,
                "arguments": '{"path":"src/mew/a.py"}',
            },
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "fc-1",
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "read_file",
                },
            },
            {
                "type": "response.completed",
                "response": {
                    "id": "resp-1",
                    "usage": {"input_tokens": 11, "output_tokens": 7},
                    "metadata": {"done": "yes"},
                },
            },
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )

    assert result.status == "completed"
    assert result.response_id == "resp-1"
    assert result.usage == {"input_tokens": 11, "output_tokens": 7}
    assert result.event_counts["response.function_call_arguments.delta"] == 2
    item = result.transcript.items[0]
    assert item.kind == "function_call"
    assert item.call_id == "call-1"
    assert item.tool_name == "read_file"
    assert item.arguments_json_text == '{"path":"src/mew/a.py"}'


def test_responses_events_from_raw_decodes_sse_events() -> None:
    raw = "\n".join(
        [
            'data: {"type":"response.created","response":{"id":"resp-sse"}}',
            'data: {"type":"response.completed","response":{"id":"resp-sse","usage":{"output_tokens":1}}}',
            "data: [DONE]",
        ]
    )

    events = responses_events_from_raw(raw, content_type="text/event-stream")

    assert [event["type"] for event in events] == ["response.created", "response.completed"]
    assert events[1]["response"] == {"id": "resp-sse", "usage": {"output_tokens": 1}}


def test_responses_events_from_raw_wraps_non_stream_response_payload() -> None:
    raw = json.dumps(
        {
            "id": "resp-json",
            "status": "completed",
            "output": [
                {
                    "id": "fc-1",
                    "type": "function_call",
                    "call_id": "call-1",
                    "name": "read_file",
                    "arguments": {"path": "README.md"},
                }
            ],
            "usage": {"input_tokens": 3},
        }
    )

    events = responses_events_from_raw(raw, content_type="application/json")
    result = parse_responses_stream_events(
        events,
        lane_attempt_id="attempt-json",
        model="gpt-5.5",
    )

    assert result.status == "completed"
    assert result.usage == {"input_tokens": 3}
    assert result.transcript.items[0].kind == "function_call"
    assert result.transcript.items[0].arguments_json_text == '{"path": "README.md"}'


def test_call_codex_native_responses_sends_descriptor_body_and_parses_items() -> None:
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        provider_request_id="req-native-call",
    )
    raw = json.dumps(
        {
            "id": "resp-native",
            "status": "completed",
            "output": [
                {
                    "id": "finish-1",
                    "type": "function_call",
                    "call_id": "call-finish",
                    "name": "finish",
                    "arguments": {"outcome": "completed", "summary": "done"},
                }
            ],
        }
    )

    with patch(
        "mew.implement_lane.native_provider_adapter._codex_api.call_codex_responses_raw",
        return_value=(raw, "application/json"),
    ) as call:
        result = call_codex_native_responses(
            auth={"access_token": "x"},
            descriptor=descriptor,
            base_url="https://example.invalid/api",
            timeout=10,
            lane_attempt_id="attempt-live",
            turn_id="turn-live-1",
        )

    call.assert_called_once()
    assert call.call_args.args[1] == descriptor["request_body"]
    assert result.status == "completed"
    item = result.transcript.items[0]
    assert item.kind == "finish_call"
    assert item.call_id == "call-finish"


def test_call_codex_native_responses_websocket_uses_session_events() -> None:
    descriptor = build_responses_request_descriptor(
        model="gpt-5.5",
        instructions="Native implement_v2 instructions.",
        input_items=[_input_item()],
        provider_request_id="req-native-ws",
    )

    class FakeWebSocketSession:
        def __init__(self) -> None:
            self.requests: list[dict[str, object]] = []

        def request(self, body, *, timeout=None, on_text_delta=None):
            self.requests.append(dict(body))
            if on_text_delta:
                on_text_delta("done")
            return (
                {"type": "response.created", "response": {"id": "resp-ws"}},
                {
                    "type": "response.output_item.done",
                    "output_index": 0,
                    "item": {
                        "id": "msg-1",
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "done"}],
                    },
                },
                {"type": "response.completed", "response": {"id": "resp-ws"}},
            )

    deltas: list[str] = []
    session = FakeWebSocketSession()
    result = call_codex_native_responses_websocket(
        auth={"access_token": "x"},
        descriptor=descriptor,
        base_url="https://example.invalid/api",
        timeout=10,
        lane_attempt_id="attempt-live",
        turn_id="turn-live-1",
        websocket_session=session,
        on_text_delta=deltas.append,
    )

    assert session.requests == [descriptor["request_body"]]
    assert deltas == ["done"]
    assert result.status == "completed"
    assert result.response_id == "resp-ws"
    assert result.transcript.items[0].kind == "assistant_message"


def test_stream_parser_accumulates_custom_tool_input_deltas() -> None:
    result = parse_responses_stream_events(
        [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {
                    "id": "ctc-1",
                    "type": "custom_tool_call",
                    "call_id": "call-patch",
                    "name": "apply_patch",
                },
            },
            {
                "type": "response.custom_tool_call_input.delta",
                "output_index": 0,
                "delta": "*** Begin Patch\n",
            },
            {
                "type": "response.custom_tool_call_input.delta",
                "output_index": 0,
                "delta": "*** End Patch\n",
            },
            {
                "type": "response.custom_tool_call_input.done",
                "output_index": 0,
                "input": "*** Begin Patch\n*** End Patch\n",
            },
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {
                    "id": "ctc-1",
                    "type": "custom_tool_call",
                    "call_id": "call-patch",
                    "name": "apply_patch",
                },
            },
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )

    item = result.transcript.items[0]
    assert item.kind == "custom_tool_call"
    assert item.call_id == "call-patch"
    assert item.custom_input_text == "*** Begin Patch\n*** End Patch\n"


def test_model_text_non_control_json_fixture_records_text_and_no_control_action() -> (
    None
):
    text = '{"tool_calls":[{"name":"read_file","arguments":{"path":"x.py"}}],"finish":{"summary":"done"}}'
    result = parse_responses_stream_events(
        [
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {"id": "msg-1", "type": "message", "role": "assistant"},
            },
            {
                "type": "response.content_part.added",
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text"},
            },
            {"type": "response.output_text.delta", "output_index": 0, "delta": text},
            {"type": "response.output_text.done", "output_index": 0, "text": text},
            {
                "type": "response.content_part.done",
                "output_index": 0,
                "content_index": 0,
                "part": {"type": "output_text"},
            },
            {
                "type": "response.output_item.done",
                "output_index": 0,
                "item": {"id": "msg-1", "type": "message", "role": "assistant"},
            },
            {"type": "response.metadata", "value": {"observed": True}},
            {
                "type": "response.completed",
                "response": {"id": "resp-text", "usage": {"total_tokens": 9}},
            },
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )

    assert [item.kind for item in result.transcript.items] == ["assistant_message"]
    assert result.transcript.items[0].output_text_or_ref == text
    assert result.control_actions == ()
    assert result.event_counts["response.content_part.added"] == 1
    assert result.event_counts["response.content_part.done"] == 1
    assert any(event["type"] == "response.metadata" for event in result.metadata_events)


def test_stream_parser_records_failed_and_incomplete_events_without_items() -> None:
    failed = parse_responses_stream_events(
        [
            {
                "type": "response.failed",
                "response": {
                    "id": "resp-failed",
                    "error": {"code": "rate_limit_exceeded", "message": "retry later"},
                    "metadata": {"request_id": "req-failed"},
                },
            }
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )
    incomplete = parse_responses_stream_events(
        [
            {
                "type": "response.incomplete",
                "response": {
                    "id": "resp-incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            }
        ],
        lane_attempt_id="attempt-1",
        model="gpt-5.5",
    )

    assert failed.status == "failed"
    assert failed.errors == ("retry later",)
    assert failed.transcript.items == ()
    assert incomplete.status == "incomplete"
    assert incomplete.errors == ("response.incomplete:max_output_tokens",)
