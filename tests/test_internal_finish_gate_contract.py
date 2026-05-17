from mew.implement_lane.internal_finish_gate_contract import (
    merge_finish_surface_gate_results,
    scan_provider_tool_descriptors_for_finish_leaks,
    scan_tool_surface_metadata_for_finish_leaks,
    validate_done_candidate_record,
)
from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, build_tool_surface_snapshot


def test_provider_tool_descriptor_without_finish_passes_gate() -> None:
    result = scan_provider_tool_descriptors_for_finish_leaks(
        [
            {
                "type": "function",
                "function": {
                    "name": "exec_command",
                    "parameters": {
                        "type": "object",
                        "properties": {"cmd": {"type": "string"}},
                        "required": ["cmd"],
                    },
                },
            }
        ]
    )

    assert result.ok, result.as_dict()


def test_provider_tool_descriptor_with_finish_tool_fails_gate() -> None:
    result = scan_provider_tool_descriptors_for_finish_leaks(
        [
            {
                "type": "function",
                "function": {
                    "name": "finish",
                    "parameters": {
                        "type": "object",
                        "properties": {"summary": {"type": "string"}},
                    },
                },
            }
        ]
    )

    assert not result.ok
    assert {violation.code for violation in result.violations} == {
        "provider_visible_finish_tool",
        "provider_visible_finish_schema_field",
    }


def test_provider_tool_descriptor_with_finish_schema_fields_fails_gate() -> None:
    result = scan_provider_tool_descriptors_for_finish_leaks(
        {
            "function": {
                "name": "respond",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "final_status": {"type": "string"},
                        "unsafe_blockers": {"type": "array"},
                    },
                    "required": ["final_status", "budget_blockers"],
                },
            }
        }
    )

    assert not result.ok
    assert all(
        violation.code == "provider_visible_finish_schema_field"
        for violation in result.violations
    )


def test_provider_tool_name_list_with_finish_fails_gate() -> None:
    result = scan_tool_surface_metadata_for_finish_leaks(
        {"provider_tool_names": ["apply_patch", "finish"]}
    )

    assert not result.ok
    assert any(
        violation.code == "provider_visible_finish_tool" for violation in result.violations
    )


def test_provider_tool_descriptor_key_named_finish_fails_gate() -> None:
    result = scan_provider_tool_descriptors_for_finish_leaks(
        {"tools": {"finish": {"type": "function"}}}
    )

    assert not result.ok
    assert any(
        violation.code == "provider_visible_finish_tool" for violation in result.violations
    )


def test_current_codex_hot_path_snapshot_still_leaks_finish_until_phase_1() -> None:
    snapshot = build_tool_surface_snapshot(
        lane_config={"tool_surface_profile_id": CODEX_HOT_PATH_PROFILE_ID},
        task_contract={},
        transcript_items=(),
    )

    result = scan_tool_surface_metadata_for_finish_leaks(snapshot.request_metadata())

    assert not result.ok
    assert any(
        violation.code == "provider_visible_finish_tool" for violation in result.violations
    )


def test_future_no_finish_tool_surface_snapshot_passes_gate() -> None:
    result = scan_tool_surface_metadata_for_finish_leaks(
        {
            "profile_id": "codex_hot_path",
            "provider_tool_names": ["apply_patch", "exec_command", "write_stdin"],
            "entries": [
                {
                    "provider_name": "apply_patch",
                    "internal_kernel": "apply_patch",
                    "route": "apply_patch",
                    "render_policy_id": "codex_apply_patch_text_v1",
                },
                {
                    "provider_name": "exec_command",
                    "internal_kernel": "run_command",
                    "route": "run_command",
                    "render_policy_id": "codex_terminal_text_v1",
                },
            ],
        }
    )

    assert result.ok, result.as_dict()


def test_done_candidate_record_schema_passes_for_new_authority_shape() -> None:
    result = validate_done_candidate_record(
        {
            "schema_version": 1,
            "done_candidate_id": "done-candidate:turn-7:response-abc",
            "lane_attempt_id": "attempt-1",
            "turn_id": "turn-7",
            "assistant_message_item_ids": ["msg-1"],
            "final_response_text_ref": "native-transcript://attempt-1/turn-7/final-text",
            "transcript_hash_before_gate": "sha256:transcript",
            "compact_sidecar_digest_hash": "sha256:sidecar",
            "detector_version": "done_candidate_detector_v1",
        }
    )

    assert result.ok, result.as_dict()


def test_done_candidate_record_schema_rejects_legacy_finish_authority() -> None:
    result = validate_done_candidate_record(
        {
            "schema_version": 1,
            "done_candidate_id": "done-candidate:turn-7:response-abc",
            "lane_attempt_id": "attempt-1",
            "turn_id": "turn-7",
            "assistant_message_item_ids": ["msg-1"],
            "final_response_text_ref": "native-transcript://attempt-1/turn-7/final-text",
            "transcript_hash_before_gate": "sha256:transcript",
            "compact_sidecar_digest_hash": "sha256:sidecar",
            "detector_version": "done_candidate_detector_v1",
            "finish_call_id": "call-finish-1",
        }
    )

    assert not result.ok
    assert any(
        violation.code == "legacy_finish_field_in_done_candidate"
        for violation in result.violations
    )


def test_merged_finish_surface_gate_result_collects_all_violations() -> None:
    merged = merge_finish_surface_gate_results(
        scan_provider_tool_descriptors_for_finish_leaks(
            [{"function": {"name": "finish", "parameters": {"type": "object"}}}]
        ),
        validate_done_candidate_record({"done_candidate_id": "missing-fields"}),
    )

    assert not merged.ok
    assert len(merged.violations) > 1
