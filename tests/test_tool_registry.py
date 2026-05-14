from mew.implement_lane.native_transcript import NativeTranscriptItem
from mew.implement_lane.tool_policy import list_v2_tool_specs_for_task
from mew.implement_lane.tool_registry import (
    CODEX_HOT_PATH_PROFILE_ID,
    MEW_LEGACY_PROFILE_ID,
    build_tool_surface_snapshot,
)


def test_mew_legacy_profile_preserves_default_tool_order_without_lifecycle() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=(),
    )
    expected = [
        spec.name
        for spec in list_v2_tool_specs_for_task("full")
        if spec.name not in {"poll_command", "cancel_command", "read_command_output"}
    ]

    assert snapshot.profile_id == MEW_LEGACY_PROFILE_ID
    assert snapshot.provider_tool_names == tuple(expected)
    assert [spec.name for spec in snapshot.tool_specs] == expected
    assert snapshot.prompt_contract_id == "mew_legacy_prompt_v1"
    assert snapshot.profile_hash.startswith("sha256:")
    assert snapshot.descriptor_hash.startswith("sha256:")
    assert snapshot.route_table_hash.startswith("sha256:")
    assert snapshot.render_policy_hash.startswith("sha256:")
    first_entry = snapshot.entries[0].as_dict()
    assert first_entry["availability_class"] == "permission_mode"
    assert first_entry["descriptor_adapter_id"] == "mew_legacy_descriptor_v1"
    assert first_entry["argument_adapter_id"] == "mew_legacy_arguments_identity_v1"
    assert str(first_entry["route_hash"]).startswith("sha256:")
    assert snapshot.request_metadata()["entries"][0]["provider_name"] == expected[0]  # type: ignore[index]


def test_mew_legacy_profile_exposes_lifecycle_tools_for_open_command() -> None:
    transcript_items = (
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            kind="function_call_output",
            call_id="run-1",
            tool_name="run_command",
            output_text_or_ref="command_run_id=cmd-1 status=running",
            status="yielded",
        ),
    )

    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=transcript_items,
    )

    assert {"poll_command", "cancel_command", "read_command_output"} <= set(
        snapshot.provider_tool_names
    )


def test_mew_legacy_profile_exposes_output_reader_for_completed_command() -> None:
    transcript_items = (
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            kind="function_call_output",
            call_id="run-1",
            tool_name="run_command",
            output_text_or_ref="command_run_id=cmd-1 command_output_ref=spool:cmd-1",
            status="completed",
        ),
    )

    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=transcript_items,
    )

    assert "read_command_output" in snapshot.provider_tool_names
    assert "poll_command" not in snapshot.provider_tool_names
    assert "cancel_command" not in snapshot.provider_tool_names


def test_mew_legacy_profile_reads_completed_command_from_content_ref_only() -> None:
    transcript_items = (
        NativeTranscriptItem(
            sequence=1,
            turn_id="turn-1",
            kind="function_call_output",
            call_id="run-1",
            tool_name="run_command",
            output_text_or_ref="run_command result: completed",
            status="completed",
            content_refs=(
                "implement-v2-exec://attempt-1/attempt-1:command:run-1-abcd1234/output",
            ),
        ),
    )

    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=transcript_items,
    )

    assert "read_command_output" in snapshot.provider_tool_names
    assert "poll_command" not in snapshot.provider_tool_names
    assert "cancel_command" not in snapshot.provider_tool_names


def test_unknown_tool_surface_profile_fails_closed() -> None:
    try:
        build_tool_surface_snapshot(
            lane_config={"tool_surface_profile_id": "missing"},
            task_contract={},
            transcript_items=(),
        )
    except ValueError as exc:
        assert "unsupported tool_surface_profile_id: missing" in str(exc)
    else:
        raise AssertionError("unknown profile must fail closed")


def test_codex_hot_path_profile_exposes_codex_like_tools_only() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full", "tool_surface_profile_id": CODEX_HOT_PATH_PROFILE_ID},
        task_contract={},
        transcript_items=(),
    )

    assert snapshot.profile_id == CODEX_HOT_PATH_PROFILE_ID
    assert snapshot.prompt_contract_id == "codex_hot_path_prompt_v1"
    assert snapshot.provider_tool_names == (
        "apply_patch",
        "exec_command",
        "write_stdin",
        "finish",
    )
    assert "run_command" not in snapshot.provider_tool_names
    assert "read_file" not in snapshot.provider_tool_names
    route_by_name = {entry.provider_name: entry.as_dict() for entry in snapshot.entries}
    assert route_by_name["exec_command"]["internal_kernel"] == "run_command"
    assert route_by_name["write_stdin"]["internal_kernel"] == "poll_command"
    assert route_by_name["write_stdin"]["availability_class"] == "active_session"


def test_codex_hot_path_profile_gates_list_dir_option() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={
            "mode": "full",
            "tool_surface_profile_id": CODEX_HOT_PATH_PROFILE_ID,
            "tool_surface_profile_options": {"enable_list_dir": True},
        },
        task_contract={},
        transcript_items=(),
    )

    assert "list_dir" in snapshot.provider_tool_names
    route_by_name = {entry.provider_name: entry.as_dict() for entry in snapshot.entries}
    assert route_by_name["list_dir"]["internal_kernel"] == "inspect_dir"
