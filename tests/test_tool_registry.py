from pathlib import Path

from mew.implement_lane.native_transcript import NativeTranscriptItem
from mew.implement_lane.native_tool_schema import stable_json_hash
from mew.implement_lane.tool_registry import (
    CODEX_HOT_PATH_PROFILE_ID,
    MEW_LEGACY_PROFILE_ID,
    build_tool_surface_snapshot,
)
from mew.implement_lane.tool_profiles.codex_hot_path import (
    CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID,
    codex_hot_path_developer_contract,
    codex_hot_path_tool_specs,
)


def test_mew_legacy_profile_preserves_default_tool_order_without_lifecycle() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full"},
        task_contract={},
        transcript_items=(),
    )
    expected = [
        "apply_patch",
        "edit_file",
        "write_file",
        "run_command",
        "run_tests",
        "read_file",
        "search_text",
        "glob",
        "inspect_dir",
        "git_status",
        "git_diff",
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
    assert snapshot.developer_contract_id == CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID
    assert snapshot.developer_contract_version == "v1"
    assert snapshot.developer_contract_hash.startswith("sha256:")
    assert snapshot.developer_contract_transport_policy == "role_developer_input_or_provider_fallback"
    assert snapshot.developer_contract_provider_tool_names == snapshot.provider_tool_names
    assert snapshot.descriptor_hash == stable_json_hash([spec.as_dict() for spec in snapshot.tool_specs])
    assert snapshot.provider_tool_names == (
        "apply_patch",
        "exec_command",
        "write_stdin",
    )
    assert "finish" not in snapshot.provider_tool_names
    assert "run_command" not in snapshot.provider_tool_names
    assert "read_file" not in snapshot.provider_tool_names
    descriptions = "\n".join(spec.description for spec in snapshot.tool_specs)
    assert "Use the `apply_patch` tool to edit files" in descriptions
    assert "Runs a command, returning output or a command_id" in descriptions
    assert "Primary source mutation tool" not in descriptions
    assert "smallest runnable candidate" not in descriptions
    route_by_name = {entry.provider_name: entry.as_dict() for entry in snapshot.entries}
    assert route_by_name["exec_command"]["internal_kernel"] == "run_command"
    assert route_by_name["write_stdin"]["internal_kernel"] == "poll_command"
    assert route_by_name["write_stdin"]["availability_class"] == "active_session"
    metadata = snapshot.request_metadata()
    assert metadata["developer_contract_id"] == CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID
    assert metadata["developer_contract_hash"] == snapshot.developer_contract_hash
    assert metadata["developer_contract_provider_tool_names"] == list(snapshot.provider_tool_names)


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
    assert snapshot.developer_contract_provider_tool_names == snapshot.provider_tool_names
    route_by_name = {entry.provider_name: entry.as_dict() for entry in snapshot.entries}
    assert route_by_name["list_dir"]["internal_kernel"] == "inspect_dir"


def test_phase6d0_codex_hot_path_developer_contract_fixture_matches_tools() -> None:
    specs = codex_hot_path_tool_specs(enable_list_dir=False)
    contract = codex_hot_path_developer_contract(tool_specs=specs)

    assert contract.profile_id == CODEX_HOT_PATH_PROFILE_ID
    assert contract.contract_id == CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID
    assert contract.provider_tool_names == tuple(spec.name for spec in specs)
    assert "Use apply_patch for manual source edits." in contract.rendered_text
    assert (
        "Use exec_command for inspection, builds, tests, probes, package-manager setup, and verification."
        in contract.rendered_text
    )
    assert "Do not create or edit source files with shell heredocs" in contract.rendered_text
    assert "shell is not the manual source editing API." in contract.rendered_text
    assert "preserve the existing program structure" not in contract.rendered_text
    assert "nearest compiler, linker, test, or runtime diagnostic" not in contract.rendered_text
    assert "standalone surrogate unless the task explicitly asks" not in contract.rendered_text
    assert "list_dir" not in contract.rendered_text
    expected_forbidden_terms = (
        "finish",
        "final_status",
        "summary",
        "evidence_refs",
        "task_done",
        "run_tests",
        "run_command",
        "read_file",
        "search_text",
        "glob",
        "inspect_dir",
        "WorkFrame",
        "next_action",
        "required_next",
        "first_write",
        "sidecar",
        "proof_manifest",
        "native_finish_gate",
        "make-doom-for-mips",
        "doomgeneric_mips",
        "/tmp/frame.bmp",
        "Terminal-Bench",
    )
    assert contract.forbidden_terms == expected_forbidden_terms
    for forbidden in expected_forbidden_terms:
        assert forbidden not in contract.rendered_text


def test_phase6d0_codex_hot_path_developer_contract_tracks_list_dir_option() -> None:
    specs = codex_hot_path_tool_specs(enable_list_dir=True)
    contract = codex_hot_path_developer_contract(tool_specs=specs)

    assert contract.provider_tool_names == tuple(spec.name for spec in specs)
    assert "list_dir" in contract.provider_tool_names
    assert (
        "Use list_dir only for bounded directory listings; use exec_command for normal terminal inspection when shell access is available."
        in contract.rendered_text
    )


def test_phase6d0_legacy_profile_does_not_import_codex_developer_contract() -> None:
    legacy_profile = Path("src/mew/implement_lane/tool_profiles/mew_legacy.py").read_text(
        encoding="utf-8"
    )

    assert "CODEX_HOT_PATH_DEVELOPER_CONTRACT_ID" not in legacy_profile
    assert "codex_hot_path_developer_contract" not in legacy_profile


def test_phase6d1_codex_hot_path_profile_hash_covers_developer_contract() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full", "tool_surface_profile_id": CODEX_HOT_PATH_PROFILE_ID},
        task_contract={},
        transcript_items=(),
    )
    changed_profile_payload = {
        **snapshot.profile.as_dict(),
        "developer_contract_hash": "sha256:changed",
        "developer_contract_provider_tool_names": list(snapshot.provider_tool_names),
    }

    assert snapshot.profile_hash != stable_json_hash(snapshot.profile.as_dict())
    assert snapshot.profile_hash != stable_json_hash(changed_profile_payload)


def test_phase6d1_mew_legacy_has_no_codex_developer_contract_metadata() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"mode": "full", "tool_surface_profile_id": MEW_LEGACY_PROFILE_ID},
        task_contract={},
        transcript_items=(),
    )

    assert snapshot.developer_contract_id == ""
    assert snapshot.developer_contract_version == ""
    assert snapshot.developer_contract_hash == ""
    assert snapshot.developer_contract_transport_policy == ""
    assert snapshot.developer_contract_provider_tool_names == ()


def test_phase6a_tool_registry_does_not_import_legacy_policy_for_descriptors() -> None:
    source = Path("src/mew/implement_lane/tool_registry.py").read_text(encoding="utf-8")

    assert "tool_" + "policy" not in source
    assert "list_v2_tool_specs_for_task" not in source


def test_phase6c_legacy_policy_module_removed_from_implement_lane() -> None:
    assert not Path("src/mew/implement_lane/" + "tool_" + "policy.py").exists()

    live_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/mew/implement_lane").glob("*.py")
        if path.name not in {"native_boundary_audit.py"}
    )
    assert "tool_" + "policy" not in live_sources
