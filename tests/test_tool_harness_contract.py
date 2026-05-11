from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.provider import FakeProviderAdapter
from mew.implement_lane.tool_harness_contract import (
    build_tool_policy_index_artifact,
    build_tool_registry_artifact,
    build_tool_result_index_artifact,
    tool_ref_for_name,
)
from mew.implement_lane.tool_policy import list_v2_tool_specs_for_mode
from mew.implement_lane.types import ImplementLaneInput, ImplementLaneProofManifest, ToolResultEnvelope
from mew.implement_lane.v2_runtime import _tool_result_transcript_events, _write_live_json_artifacts
from mew.work_lanes import IMPLEMENT_V2_LANE


def test_tool_result_provider_content_includes_natural_text_and_output_refs() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "exit_code": 2,
                "stderr_tail": "line 1\nfatal error",
                "output_ref": "exec://attempt-1/cmd/output",
                "failure_class": "compile_error",
            },
        ),
        content_refs=("exec://attempt-1/cmd/output",),
        evidence_refs=("ev:compile-error",),
    )

    visible = result.provider_visible_content()

    assert visible["output_refs"] == ["exec://attempt-1/cmd/output"]
    assert "run_command result: failed" in visible["natural_result_text"]
    assert "exit_code=2" in visible["natural_result_text"]
    assert "fatal error" in visible["natural_result_text"]
    assert "ev:compile-error" in visible["natural_result_text"]


def test_tool_registry_and_result_index_artifacts_are_stable() -> None:
    registry = build_tool_registry_artifact(
        provider="model_json",
        tool_specs=tuple(spec for spec in list_v2_tool_specs_for_mode("read_only") if spec.name in {"read_file", "finish"}),
    )
    policy = build_tool_policy_index_artifact(registry)
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="attempt-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=({"path": "README.md", "text": "hello"},),
        content_refs=("file://README.md",),
    )
    index = build_tool_result_index_artifact(
        (result,),
        tool_registry_ref=str(registry["tool_registry_ref"]),
        provider_tool_spec_hash=str(registry["provider_tool_spec_hash"]),
    )

    assert registry["tool_registry_hash"] == registry["provider_tool_spec_hash"]
    assert {"read_file", "finish", "model_response_error"}.issubset(set(registry["by_tool_name"]))
    assert policy["by_tool"]["read_file"]["tool_ref"] == tool_ref_for_name("read_file")
    assert policy["by_tool_ref"][tool_ref_for_name("read_file")]["tool_name"] == "read_file"
    assert policy["by_tool_ref"][tool_ref_for_name("model_response_error")]["access"] == "internal"
    assert index["by_provider_call_id"]["call-1"]["ref"] == "tool-result:call-1"
    assert index["by_provider_call_id"]["call-1"]["tool_ref"] == tool_ref_for_name("read_file")
    assert index["by_provider_call_id"]["call-1"]["output_refs"] == ["file://README.md"]
    assert index["index_hash"].startswith("sha256:")


def test_live_artifact_writer_emits_phase1_tool_harness_files(tmp_path: Path) -> None:
    adapter = FakeProviderAdapter()
    call = adapter.normalize_tool_calls(
        lane_attempt_id="attempt-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name="read_file",
        status="completed",
        content=({"path": "README.md", "text": "hello"},),
        content_refs=("file://README.md",),
    )
    transcript = adapter.transcript_events_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        text="reading",
        tool_calls=(call,),
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
        metrics={"transport": "model_json", "provider_tool_names": ["read_file", "finish"]},
    )
    lane_input = ImplementLaneInput(
        work_session_id="ws",
        task_id="task",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        lane_config={"artifact_dir": str(tmp_path / "artifacts")},
    )

    paths = _write_live_json_artifacts(
        lane_input,
        manifest=manifest,
        transcript=(
            *transcript,
            *_tool_result_transcript_events(
                lane_attempt_id="attempt-1",
                turn_id="turn-1",
                tool_results=(result,),
            ),
        ),
        history=(),
    )
    artifact_root = tmp_path / "artifacts" / "implement_v2"

    assert str(artifact_root / "tool_registry.json") in paths
    assert str(artifact_root / "tool_policy_index.json") in paths
    assert str(artifact_root / "natural_transcript.jsonl") in paths
    assert str(artifact_root / "tool_results.jsonl") in paths
    assert str(artifact_root / "tool_result_index.json") in paths

    registry = json.loads((artifact_root / "tool_registry.json").read_text(encoding="utf-8"))
    result_index = json.loads((artifact_root / "tool_result_index.json").read_text(encoding="utf-8"))
    transcript_lines = (artifact_root / "natural_transcript.jsonl").read_text(encoding="utf-8").splitlines()
    result_lines = (artifact_root / "tool_results.jsonl").read_text(encoding="utf-8").splitlines()

    assert registry["provider"] == "model_json"
    assert {"read_file", "finish", "model_response_error"}.issubset(set(registry["by_tool_name"]))
    assert result_index["by_provider_call_id"]["call-1"]["tool_name"] == "read_file"
    assert result_index["by_provider_call_id"]["call-1"]["tool_ref"] == tool_ref_for_name("read_file")
    result_event_payloads = [
        json.loads(line)["payload"] for line in transcript_lines if json.loads(line)["kind"] == "tool_result"
    ]
    assert result_event_payloads[0]["natural_result_text"].startswith("read_file result: completed")
    assert len(result_lines) == 1
    assert json.loads(result_lines[0])["natural_result_text"].startswith("read_file result: completed")
