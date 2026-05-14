from mew.implement_lane.apply_patch_affordance import (
    build_apply_patch_affordance_descriptor,
    run_apply_patch_affordance_check,
)
from mew.implement_lane.native_provider_adapter import parse_responses_stream_events


def _provider_with_tool(tool_name: str, *, kind: str = "function"):
    def call_provider(**kwargs):
        if kind == "custom":
            item = {
                "id": "ctc-1",
                "type": "custom_tool_call",
                "call_id": "call-1",
                "name": tool_name,
                "input": "*** Begin Patch\n*** End Patch\n",
            }
        else:
            item = {
                "id": "fc-1",
                "type": "function_call",
                "call_id": "call-1",
                "name": tool_name,
                "arguments": '{"cmd":"printf x"}',
            }
        return parse_responses_stream_events(
            (
                {"type": "response.created", "response": {"id": "resp-1"}},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": {"id": "resp-1"}},
            ),
            lane_attempt_id=str(kwargs["lane_attempt_id"]),
            model="gpt-5.5",
            turn_id=str(kwargs["turn_id"]),
        )

    return call_provider


def test_apply_patch_affordance_descriptor_uses_codex_hot_path_tools() -> None:
    descriptor = build_apply_patch_affordance_descriptor(model="gpt-5.5")
    request = descriptor["request_body"]
    tools = request["tools"]  # type: ignore[index]
    names = [tool.get("name") for tool in tools]  # type: ignore[union-attr]

    assert names == ["apply_patch", "exec_command", "write_stdin", "finish"]
    assert descriptor["tool_surface_profile_id"] == "codex_hot_path"
    assert "previous_response_id" not in request  # type: ignore[operator]


def test_apply_patch_affordance_passes_on_apply_patch_custom_call() -> None:
    result = run_apply_patch_affordance_check(
        call_provider=_provider_with_tool("apply_patch", kind="custom"),
    )

    assert result.status == "pass"
    assert result.first_tool_name == "apply_patch"
    assert result.first_tool_kind == "custom_tool_call"


def test_apply_patch_affordance_fails_on_exec_command() -> None:
    result = run_apply_patch_affordance_check(
        call_provider=_provider_with_tool("exec_command"),
    )

    assert result.status == "fail"
    assert result.first_tool_name == "exec_command"
