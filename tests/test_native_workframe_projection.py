import copy

from mew.implement_lane.native_sidecar_projection import build_native_evidence_sidecar
from mew.implement_lane.native_workframe_projection import (
    build_native_prompt_input_inventory,
    build_native_workframe_debug_bundle,
    build_native_workframe_inputs,
    build_native_workframe_sidecar_events,
    native_workframe_projection_policy,
)


def _native_transcript_dict() -> dict[str, object]:
    return {
        "schema_version": 1,
        "lane_attempt_id": "attempt-native-1",
        "provider": "codex",
        "model": "gpt-5.5",
        "active_work_todo": {"status": "model-authored"},
        "items": [
            {
                "sequence": 1,
                "turn_id": "turn-1",
                "kind": "function_call",
                "call_id": "call-write",
                "tool_name": "apply_patch",
                "arguments_json_text": '{"path":"src/app.py"}',
            },
            {
                "sequence": 2,
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
            },
            {
                "sequence": 3,
                "turn_id": "turn-2",
                "kind": "function_call",
                "call_id": "call-test",
                "tool_name": "run_tests",
                "arguments_json_text": '{"command":"pytest tests/test_app.py"}',
            },
            {
                "sequence": 4,
                "turn_id": "turn-2",
                "kind": "function_call_output",
                "call_id": "call-test",
                "tool_name": "run_tests",
                "status": "completed",
                "output_text_or_ref": "pytest passed",
                "content_refs": ["sidecar:pytest-output"],
                "evidence_refs": ["ev:verify-pass"],
            },
        ],
    }


def test_native_workframe_sidecar_events_are_projected_from_transcript_outputs() -> None:
    transcript = _native_transcript_dict()
    events = build_native_workframe_sidecar_events(transcript)

    assert [event["event_id"] for event in events] == ["native-output:call-write", "native-output:call-test"]
    assert events[0]["kind"] == "apply_patch"
    assert events[0]["target_paths"] == ["src/app.py"]
    assert "implement-v2-write://attempt-native-1/call-write/mutation" in events[0]["evidence_refs"]
    assert events[1]["kind"] == "run_tests"
    assert events[1]["intent"] == "verify"


def test_native_workframe_debug_bundle_replays_from_transcript_with_stable_hashes() -> None:
    transcript = _native_transcript_dict()
    evidence_sidecar = build_native_evidence_sidecar(transcript)

    first = build_native_workframe_debug_bundle(
        transcript,
        task_id="task-1",
        objective="Patch src/app.py and verify it.",
        success_contract_ref="pytest",
        evidence_sidecar=evidence_sidecar,
        variant="current",
    )
    regenerated = build_native_workframe_debug_bundle(
        transcript,
        task_id="task-1",
        objective="Patch src/app.py and verify it.",
        success_contract_ref="pytest",
        evidence_sidecar=evidence_sidecar,
        variant="current",
    )

    assert first["bundle_hash"] == regenerated["bundle_hash"]
    assert first["source_of_truth"] == "response_transcript.json"
    assert first["projection_policy"]["runtime_wired"] is False
    assert first["projection_policy"]["tool_execution_authority"] is False
    workframe = first["reducer_output"]
    assert workframe["current_phase"] == "finish_ready"
    assert workframe["required_next"]["kind"] == "finish"
    assert workframe["finish_readiness"]["state"] == "ready"
    assert first["invariant_report"]["status"] == "pass"
    assert first["workframe_cursor"]["input_hash"] == workframe["trace"]["input_hash"]
    assert first["workframe_cursor"]["output_hash"] == workframe["trace"]["output_hash"]


def test_native_prompt_inventory_exposes_only_window_and_compact_sidecar_digest() -> None:
    inventory = build_native_prompt_input_inventory(
        compact_sidecar_digest={"digest_hash": "sha256:digest"},
        source_prompt_inventory=[{"id": "native-window"}],
    )

    assert inventory["model_visible_sections"] == ["native_transcript_window", "compact_sidecar_digest"]
    assert inventory["ordinary_model_visible_state"] == {
        "frontier": False,
        "todo": False,
        "proof": False,
        "evidence_object": False,
    }
    assert inventory["compact_sidecar_digest_hash"] == "sha256:digest"


def test_native_workframe_projection_ignores_model_authored_state_fields() -> None:
    transcript = _native_transcript_dict()
    mutated = copy.deepcopy(transcript)
    mutated["active_work_todo"] = {"status": "changed-by-model"}
    mutated["frontier_state_update"] = {"status": "changed-by-model"}
    mutated["items"][1]["todo"] = {"status": "changed-by-model"}  # type: ignore[index]

    first = build_native_workframe_debug_bundle(
        transcript,
        task_id="task-1",
        objective="Patch src/app.py and verify it.",
        success_contract_ref="pytest",
        variant="current",
    )
    second = build_native_workframe_debug_bundle(
        mutated,
        task_id="task-1",
        objective="Patch src/app.py and verify it.",
        success_contract_ref="pytest",
        variant="current",
    )

    assert first["bundle_hash"] == second["bundle_hash"]
    assert first["workframe_cursor"]["output_hash"] == second["workframe_cursor"]["output_hash"]


def test_native_workframe_inputs_preserve_projection_only_policy() -> None:
    inputs = build_native_workframe_inputs(
        _native_transcript_dict(),
        task_id="task-1",
        objective="Patch src/app.py and verify it.",
        success_contract_ref="pytest",
    )
    policy = native_workframe_projection_policy("current")

    assert "native_transcript_projection" in inputs.constraints
    assert inputs.turn_id == "turn-2"
    assert policy["role"] == "projection_policy_analyzer"
    assert policy["provider_request_authority"] is False
    assert policy["model_authored_state_authority"] is False
