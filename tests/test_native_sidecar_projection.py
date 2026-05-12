import copy
import json

from mew.commands import _merge_work_session_active_work_todo_readiness
from mew.implement_lane.native_sidecar_projection import (
    build_compact_native_sidecar_digest,
    build_native_evidence_ref_index,
    build_native_evidence_sidecar,
    build_native_model_turn_index,
    build_native_tool_result_index,
    build_native_updated_lane_state,
    native_projection_transcript_hash,
    tool_ref_for_name,
)


def _native_transcript_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "lane_attempt_id": "attempt-native-1",
        "provider": "codex",
        "model": "gpt-5.5",
        "frontier_state_update": {"model": "must-not-authority"},
        "active_work_todo": {"status": "model-authored"},
        "items": [
            {
                "sequence": 1,
                "turn_id": "turn-1",
                "kind": "assistant_message",
                "output_text_or_ref": "I will patch and verify.",
                "frontier_state_update": {"bad": True},
            },
            {
                "sequence": 2,
                "turn_id": "turn-1",
                "kind": "function_call",
                "call_id": "call-write",
                "tool_name": "apply_patch",
                "arguments_json_text": '{"path":"src/app.py"}',
            },
            {
                "sequence": 3,
                "turn_id": "turn-1",
                "kind": "function_call_output",
                "call_id": "call-write",
                "tool_name": "apply_patch",
                "status": "completed",
                "output_text_or_ref": "patched src/app.py",
                "path": "src/app.py",
                "content_refs": ["sidecar:patch-output"],
                "evidence_refs": ["implement-v2-write://attempt-native-1/call-write/mutation"],
                "side_effects": [
                    {
                        "kind": "file_write",
                        "operation": "apply_patch",
                        "path": "src/app.py",
                        "written": True,
                    }
                ],
                "proof": {"model": "must-not-authority"},
            },
            {
                "sequence": 4,
                "turn_id": "turn-2",
                "kind": "function_call",
                "call_id": "call-test",
                "tool_name": "run_tests",
                "arguments_json_text": '{"command":"pytest tests/test_app.py"}',
            },
            {
                "sequence": 5,
                "turn_id": "turn-2",
                "kind": "function_call_output",
                "call_id": "call-test",
                "tool_name": "run_tests",
                "status": "completed",
                "output_text_or_ref": "pytest passed",
                "content_refs": ["sidecar:pytest-output"],
                "evidence_refs": ["ev:verify-pass"],
            },
            {
                "sequence": 6,
                "turn_id": "turn-2",
                "kind": "finish_call",
                "call_id": "call-finish",
                "tool_name": "finish",
                "arguments_json_text": '{"outcome":"completed","evidence_refs":["ev:verify-pass"]}',
            },
            {
                "sequence": 7,
                "turn_id": "turn-2",
                "kind": "finish_output",
                "call_id": "call-finish",
                "tool_name": "finish",
                "status": "completed",
                "output_text_or_ref": "accepted",
                "evidence_refs": ["ev:verify-pass"],
            },
        ],
    }


def test_native_sidecar_hashes_regenerate_stably_without_model_authored_state_authority() -> None:
    transcript = _native_transcript_dict()
    mutated = copy.deepcopy(transcript)
    mutated["frontier_state_update"] = {"model": "changed"}
    mutated["active_work_todo"] = {"status": "changed"}
    mutated["items"][2]["proof"] = {"model": "changed"}  # type: ignore[index]

    first_tool_index = build_native_tool_result_index(transcript)
    first_sidecar = build_native_evidence_sidecar(transcript, tool_result_index=first_tool_index)
    first_ref_index = build_native_evidence_ref_index(first_sidecar)
    first_turn_index = build_native_model_turn_index(transcript)
    first_digest = build_compact_native_sidecar_digest(
        transcript,
        evidence_sidecar=first_sidecar,
        tool_result_index=first_tool_index,
        evidence_ref_index=first_ref_index,
        model_turn_index=first_turn_index,
    )

    second_tool_index = build_native_tool_result_index(mutated)
    second_sidecar = build_native_evidence_sidecar(mutated, tool_result_index=second_tool_index)
    second_ref_index = build_native_evidence_ref_index(second_sidecar)
    second_turn_index = build_native_model_turn_index(mutated)
    second_digest = build_compact_native_sidecar_digest(
        mutated,
        evidence_sidecar=second_sidecar,
        tool_result_index=second_tool_index,
        evidence_ref_index=second_ref_index,
        model_turn_index=second_turn_index,
    )

    assert native_projection_transcript_hash(transcript) == native_projection_transcript_hash(mutated)
    assert first_tool_index["index_hash"] == second_tool_index["index_hash"]
    assert first_sidecar["sidecar_hash"] == second_sidecar["sidecar_hash"]
    assert first_ref_index["index_hash"] == second_ref_index["index_hash"]
    assert first_turn_index["index_hash"] == second_turn_index["index_hash"]
    assert first_digest["digest_hash"] == second_digest["digest_hash"]


def test_native_sidecar_indexes_paired_tool_outputs_and_evidence_refs() -> None:
    transcript = _native_transcript_dict()
    tool_index = build_native_tool_result_index(transcript)
    sidecar = build_native_evidence_sidecar(transcript, tool_result_index=tool_index)
    ref_index = build_native_evidence_ref_index(sidecar)
    turn_index = build_native_model_turn_index(transcript)

    write_entry = tool_index["by_provider_call_id"]["call-write"]
    assert write_entry["call_sequence"] == 2
    assert write_entry["output_sequence"] == 3
    assert write_entry["tool_ref"] == tool_ref_for_name("apply_patch")
    assert write_entry["output_refs"] == ["sidecar:patch-output"]
    assert "call-write" in ref_index["by_provider_call_id"]
    assert "src/app.py" in ref_index["by_path"]
    assert "implement-v2-write://attempt-native-1/call-write/mutation" in ref_index["by_mutation_ref"]
    assert "sidecar:pytest-output" in ref_index["by_output_ref"]
    assert turn_index["index_kind"] == "debug_recovery_only"
    assert turn_index["hot_path_model_turn_search_allowed"] is False
    assert turn_index["by_provider_call_id"]["call-test"] == "turn-2"


def test_compact_sidecar_digest_is_provider_request_context_not_state_object() -> None:
    transcript = _native_transcript_dict()
    digest = build_compact_native_sidecar_digest(transcript)
    serialized = json.dumps(digest, sort_keys=True)

    assert digest["provider_input_authority"] == "transcript_window_plus_compact_sidecar_digest"
    assert "native_sidecar_digest=" in digest["digest_text"]
    assert len(digest) <= 16
    assert len(serialized.encode("utf-8")) <= 6144
    assert "workframe_projection" in digest
    assert len(digest["workframe_projection"]) <= 8
    assert digest["workframe_projection"]["current_phase"] == "orient"
    assert "required_next_kind" not in serialized
    assert "frontier_state_update" not in serialized
    assert '"active_work_todo"' not in serialized
    assert '"proof"' not in serialized


def test_compact_sidecar_digest_preserves_loop_signals_without_policy_text() -> None:
    digest = build_compact_native_sidecar_digest(
        _native_transcript_dict(),
        loop_signals={
            "first_write_due": True,
            "verifier_repair_due": False,
            "probe_count_without_write": 10,
            "latest_failed_verifier": {"call_id": "verify-" + ("v" * 8000), "status": "completed"},
            "next_action_policy": "must-not-leak",
        },
    )
    serialized = json.dumps(digest, sort_keys=True)
    projection = digest["workframe_projection"]
    signals = projection["loop_signals"]

    assert signals["first_write_due"] is True
    assert signals["probe_count_without_write"] == 10
    assert signals["latest_failed_verifier"]["call_id"].startswith("verify-")
    assert len(signals["latest_failed_verifier"]["call_id"]) <= 120
    assert projection["current_phase"] == "prewrite_blocked"
    assert "must-not-leak" not in serialized
    assert "next_action_policy" not in serialized


def test_compact_sidecar_digest_bounds_long_refs() -> None:
    transcript = _native_transcript_dict()
    transcript["lane_attempt_id"] = "attempt-" + ("a" * 8000)
    transcript["items"][2]["evidence_refs"] = ["ev:" + ("x" * 2000)] * 12  # type: ignore[index]
    transcript["items"][2]["content_refs"] = ["sidecar:" + ("y" * 2000)] * 12  # type: ignore[index]
    for index in range(8, 14):
        transcript["items"].append(  # type: ignore[union-attr]
            {
                "sequence": index,
                "turn_id": "turn-overflow",
                "kind": "function_call_output",
                "call_id": "call-" + ("z" * 2000) + str(index),
                "tool_name": "run_command",
                "status": "completed",
                "output_text_or_ref": "output " + ("o" * 2000),
                "content_refs": ["sidecar:" + ("c" * 2000)] * 12,
                "evidence_refs": ["ev:" + ("e" * 2000)] * 12,
            }
        )

    digest = build_compact_native_sidecar_digest(transcript)
    serialized = json.dumps(digest, sort_keys=True)

    assert len(digest) <= 16
    assert len(serialized.encode("utf-8")) <= 6144
    assert len(digest["lane_attempt_id"]) <= 160
    assert all(len(item["ref"]) <= 120 for item in digest["latest_tool_results"])
    for item in digest["latest_tool_results"]:
        assert all(len(ref) <= 160 for ref in item["evidence_refs"])
        assert all(len(ref) <= 160 for ref in item["output_refs"])
    assert "a" * 1000 not in serialized
    assert "z" * 1000 not in serialized


def test_updated_lane_state_is_derived_and_keeps_active_work_todo_readiness_shape() -> None:
    transcript = _native_transcript_dict()
    workframe_bundle = {
        "workframe_variant": "current",
        "reducer_output": {
            "current_phase": "finish_ready",
            "trace": {"output_hash": "sha256:workframe"},
            "required_next": {"kind": "finish", "evidence_refs": ["ev:verify-pass"]},
            "finish_readiness": {"state": "ready", "required_evidence_refs": ["ev:verify-pass"]},
        },
        "invariant_report": {"status": "pass"},
    }
    sidecar = build_native_evidence_sidecar(transcript)
    state = build_native_updated_lane_state(
        transcript,
        evidence_sidecar=sidecar,
        workframe_bundle=workframe_bundle,
        artifact_paths={"proof_manifest": "proof-manifest.json"},
        proof_manifest_ref="proof-manifest.json",
    )

    assert state["finish_status"] == "completed"
    assert state["derived_from"]["transcript_hash"] == native_projection_transcript_hash(transcript)
    assert "id" not in state["active_work_todo"]
    assert state["active_work_todo"]["status"] == "finish_ready"
    readiness = state["active_work_todo"]["first_write_readiness"]
    assert readiness["state"] == "ready"
    assert readiness["required_next"] == "finish"
    assert readiness["evidence_refs"] == ["ev:verify-pass"]


def test_updated_lane_state_readiness_merges_with_existing_command_todo_id() -> None:
    transcript = _native_transcript_dict()
    workframe_bundle = {
        "workframe_variant": "current",
        "reducer_output": {
            "current_phase": "finish_ready",
            "trace": {"output_hash": "sha256:workframe"},
            "required_next": {"kind": "finish", "evidence_refs": ["ev:verify-pass"]},
            "finish_readiness": {"state": "ready", "required_evidence_refs": ["ev:verify-pass"]},
        },
        "invariant_report": {"status": "pass"},
    }
    state = build_native_updated_lane_state(transcript, workframe_bundle=workframe_bundle)
    session = {
        "active_work_todo": {
            "id": "canonical-todo-1",
            "lane": "implement_v2",
            "status": "drafting",
            "source": {"plan_item": "Patch src/app.py", "target_paths": ["src/app.py"]},
        },
        "resume": {
            "active_work_todo": {
                "id": "canonical-todo-1",
                "lane": "implement_v2",
                "status": "drafting",
            }
        },
    }

    assert "id" not in state["active_work_todo"]
    assert _merge_work_session_active_work_todo_readiness(session, state) is True
    assert session["active_work_todo"]["id"] == "canonical-todo-1"
    assert session["active_work_todo"]["source"]["plan_item"] == "Patch src/app.py"
    assert session["active_work_todo"]["first_write_readiness"]["state"] == "ready"
    assert session["active_work_todo"]["first_write_readiness"]["derived_from"]["transcript_hash"]
    assert session["active_work_todo"]["first_write_readiness"]["derived_from"]["workframe_output_hash"] == "sha256:workframe"
    assert session["resume"]["active_work_todo"]["id"] == "canonical-todo-1"
    assert session["resume"]["active_work_todo"]["first_write_readiness"] == session["active_work_todo"][
        "first_write_readiness"
    ]
