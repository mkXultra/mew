import hashlib
import shlex
import subprocess
import sys

import mew.implement_lane.read_runtime as read_runtime
from mew.implement_lane import (
    FakeProviderAdapter,
    FakeProviderToolCall,
    ImplementLaneInput,
    ImplementLaneProofManifest,
    ImplementLaneResult,
    ImplementLaneTranscriptEvent,
    ToolResultEnvelope,
    build_invalid_tool_result,
    build_implement_v2_prompt_sections,
    describe_implement_v1_adapter,
    describe_implement_v2_runtime,
    evaluate_m6_24_reentry_ab_gate,
    get_implement_lane_runtime_view,
    implement_v2_prompt_section_metrics,
    list_implement_lane_runtime_views,
    list_v2_base_tool_specs,
    list_v2_tool_specs_for_mode,
    run_fake_exec_implement_v2,
    run_fake_read_only_implement_v2,
    run_fake_write_implement_v2,
    run_unavailable_implement_v2,
    select_implement_lane_runtime,
    validate_proof_manifest_pairing,
    validate_tool_result_pairing,
)
from mew.work_lanes import IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE, TINY_LANE


def test_implementation_runtime_registry_keeps_v1_default_and_v2_default_off() -> None:
    runtimes = list_implement_lane_runtime_views()

    assert [runtime.lane for runtime in runtimes] == [IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE]
    assert runtimes[0].default is True
    assert runtimes[0].runtime_available is True
    assert runtimes[0].provider_native_tool_loop is False
    assert runtimes[1].default is False
    assert runtimes[1].runtime_available is False
    assert runtimes[1].provider_native_tool_loop is True


def test_legacy_tiny_and_unknown_lanes_resolve_to_implement_v1_runtime() -> None:
    for lane in (None, "", TINY_LANE, "unknown-lane"):
        assert get_implement_lane_runtime_view(lane).lane == IMPLEMENT_V1_LANE


def test_explicit_implement_v2_selection_returns_v2_even_when_unavailable() -> None:
    selected = select_implement_lane_runtime(requested_lane=IMPLEMENT_V2_LANE, allow_v2=True)

    assert selected.lane == IMPLEMENT_V2_LANE
    assert selected.runtime_available is False


def test_explicit_implement_v2_selection_does_not_silently_route_to_v1() -> None:
    selected = select_implement_lane_runtime(requested_lane=IMPLEMENT_V2_LANE)

    assert selected.lane == IMPLEMENT_V2_LANE
    assert selected.fallback_lane == IMPLEMENT_V1_LANE


def test_implementation_lane_contract_shapes_are_serializable() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V1_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"acceptance": "run tests"},
    )
    event = ImplementLaneTranscriptEvent(
        kind="tool_call",
        lane=IMPLEMENT_V1_LANE,
        turn_id="turn-1",
        event_id="event-1",
        payload={"tool": "read_file"},
    )
    result = ImplementLaneResult(
        status="needs_review",
        lane=IMPLEMENT_V1_LANE,
        proof_artifacts=("proof.json",),
        transcript=(event,),
    )

    assert lane_input.as_dict()["task_contract"] == {"acceptance": "run tests"}
    assert result.as_dict()["transcript"][0]["payload"] == {"tool": "read_file"}


def test_implement_v1_adapter_has_distinct_namespace_without_running_legacy_loop() -> None:
    descriptor = describe_implement_v1_adapter(work_session_id="ws 1", task_id="task/1")

    assert descriptor.lane == IMPLEMENT_V1_LANE
    assert descriptor.legacy_lane == TINY_LANE
    assert descriptor.runtime_id == "implement_v1_json_think_act"
    assert descriptor.artifact_namespace == "implement-lane/implement_v1/ws-1/task-1"


def test_implement_v2_scaffold_exposes_tools_but_returns_unavailable() -> None:
    description = describe_implement_v2_runtime(work_session_id="ws-1", task_id="task-1")
    result = run_unavailable_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace="/tmp/work",
            lane=IMPLEMENT_V2_LANE,
        )
    )

    assert description["lane"] == IMPLEMENT_V2_LANE
    assert description["runtime_available"] is False
    assert description["artifact_namespace"] == "implement-lane/implement_v2/ws-1/task-1"
    assert {tool["name"] for tool in description["tool_specs"]} == {
        "inspect_dir",
        "read_file",
        "search_text",
        "glob",
        "git_status",
        "git_diff",
        "run_command",
        "run_tests",
        "poll_command",
        "cancel_command",
        "read_command_output",
        "write_file",
        "edit_file",
        "apply_patch",
        "finish",
    }
    assert result.status == "unavailable"
    assert result.next_reentry_hint["fallback_lane"] == IMPLEMENT_V1_LANE
    assert result.next_reentry_hint["requires_separate_lane_attempt"] is True
    assert "fallback_lane" not in result.updated_lane_state


def test_v2_tool_policy_marks_write_and_execute_tools_approval_gated() -> None:
    specs = {spec.name: spec for spec in list_v2_base_tool_specs()}

    assert specs["inspect_dir"].approval_required is False
    assert specs["read_file"].approval_required is False
    assert specs["search_text"].approval_required is False
    assert specs["glob"].approval_required is False
    assert specs["git_status"].access == "read"
    assert specs["git_diff"].access == "read"
    assert specs["run_command"].approval_required is True
    assert specs["run_tests"].approval_required is True
    assert specs["poll_command"].approval_required is False
    assert specs["cancel_command"].approval_required is False
    assert specs["read_command_output"].access == "execute"
    assert specs["write_file"].approval_required is True
    assert specs["edit_file"].dry_run_supported is True
    assert specs["apply_patch"].dry_run_supported is True


def test_fake_provider_normalizes_tool_calls_and_transcript_events() -> None:
    adapter = FakeProviderAdapter()
    calls = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            FakeProviderToolCall(
                provider_call_id="provider-call-1",
                tool_name="read_file",
                arguments={"path": "README.md"},
                provider_message_id="message-1",
            ),
        ),
    )
    events = adapter.transcript_events_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        turn_id="turn-1",
        text="I will inspect the repo.",
        tool_calls=calls,
    )

    assert calls[0].provider == "fake"
    assert calls[0].provider_call_id == "provider-call-1"
    assert calls[0].mew_tool_call_id == "lane-v2-1:tool:1:1"
    assert calls[0].arguments == {"path": "README.md"}
    assert [event.kind for event in events] == ["model_message", "tool_call"]
    assert events[0].payload["lane_attempt_id"] == "lane-v2-1"
    assert events[0].event_id == "implement_v2:lane-v2-1:turn-1:model_message:0"
    assert events[1].payload["provider_call_id"] == "provider-call-1"
    assert events[1].event_id == "implement_v2:lane-v2-1:turn-1:tool_call:1"


def test_fake_provider_can_emit_finish_event_distinctly_from_tool_call() -> None:
    event = FakeProviderAdapter().finish_event_for_turn(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        turn_id="turn-1",
        finish_arguments={"outcome": "analysis_ready"},
    )

    assert event.kind == "finish"
    assert event.event_id == "implement_v2:lane-v2-1:turn-1:finish:0"
    assert event.payload["finish_arguments"] == {"outcome": "analysis_ready"}


def test_tool_result_pairing_validator_accepts_exactly_paired_results() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"text": "ok"},),
        content_refs=("artifact://content",),
    )

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert validation.as_dict()["errors"] == []
    assert payload["tool_result"]["tool_use_id"] == "call-1"
    assert payload["tool_result"]["is_error"] is False
    assert payload["tool_result"]["content"]["mew_status"] == "completed"


def test_tool_result_pairing_validator_rejects_unpaired_or_orphan_results() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    orphan = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="orphan",
        mew_tool_call_id="lane-v2-1:tool:1:99",
        tool_name="read_file",
        status="completed",
    )

    validation = validate_tool_result_pairing((call,), (orphan,))

    assert validation.valid is False
    assert "missing_result_for_provider_call_id:call-1" in validation.errors
    assert "orphan_result_for_provider_call_id:orphan" in validation.errors


def test_tool_result_pairing_validator_rejects_cross_attempt_result() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="attempt-a",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-b",
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
    )

    validation = validate_tool_result_pairing((call,), (result,))

    assert validation.valid is False
    assert "lane_attempt_id_mismatch:call-1" in validation.errors


def test_proof_manifest_pairing_validator_rejects_internally_paired_wrong_attempt() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="attempt-b",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-b",
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-a",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
    )

    validation = validate_proof_manifest_pairing(manifest)

    assert validation.valid is False
    assert "tool_call_wrong_lane_attempt_id:call-1" in validation.errors
    assert "tool_result_wrong_lane_attempt_id:call-1" in validation.errors


def test_invalid_tool_call_gets_paired_model_visible_error_result() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "unknown_tool"},),
    )[0]
    result = build_invalid_tool_result(call, reason="unknown tool")

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert result.status == "invalid"
    assert result.is_error is True
    assert payload["tool_result"]["content"]["mew_status"] == "invalid"


def test_nonterminal_result_is_provider_visible_content_not_protocol_error() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "run_command"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="yielded",
        is_error=False,
        content=({"command_run_id": "cmd-1"},),
        content_refs=("artifact://cmd-1-output",),
    )

    validation = validate_tool_result_pairing((call,), (result,))
    payload = FakeProviderAdapter().provider_tool_result_payload(result)

    assert validation.valid is True
    assert payload["tool_result"]["is_error"] is False
    assert payload["tool_result"]["content"]["mew_status"] == "yielded"
    assert payload["tool_result"]["content"]["acceptance_evidence"] is False


def test_proof_manifest_serializes_lane_attempt_calls_results_and_metrics() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=({"provider_call_id": "call-1", "tool_name": "read_file"},),
    )[0]
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        evidence_refs=("artifact://evidence",),
    )
    manifest = ImplementLaneProofManifest(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="lane-v2-1",
        artifact_namespace="implement-lane/implement_v2/ws/task",
        tool_calls=(call,),
        tool_results=(result,),
        metrics={"tool_calls": 1},
    )

    data = manifest.as_dict()

    assert data["lane"] == IMPLEMENT_V2_LANE
    assert data["tool_calls"][0]["provider_call_id"] == "call-1"
    assert data["tool_results"][0]["evidence_refs"] == ["artifact://evidence"]
    assert data["metrics"] == {"tool_calls": 1}


def test_implement_v2_prompt_metrics_are_memory_light_by_default() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "inspect only"},
        lane_config={"mode": "read_only"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}

    assert metrics["contract_version"] == "prompt_sections_v1"
    assert "implement_v2_lane_base" in by_id
    assert "implement_v2_tool_contract" in by_id
    assert "implement_v2_tool_surface" in by_id
    assert "implement_v2_task_contract" in by_id
    assert "implement_v2_lane_state" in by_id
    assert "implement_v2_memory_summary" not in by_id
    assert by_id["implement_v2_lane_base"]["cache_hint"] == "cacheable_prefix"
    assert by_id["implement_v2_lane_state"]["cache_hint"] == "dynamic"


def test_implement_v2_v0_filters_memory_even_when_memory_summary_exists() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        persisted_lane_state={
            "memory_summary": "Use the prior bounded repair only as read-only context.",
            "lane_memory_summary": "Do not include me.",
            "reentry_memory_refs": ["mem-1"],
            "lane_safe_resume_token": "resume-1",
        },
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    lane_state = next(section for section in sections if section.id == "implement_v2_lane_state")

    assert "implement_v2_memory_summary" not in by_id
    assert "memory_summary" not in lane_state.content
    assert "lane_memory_summary" not in lane_state.content
    assert "reentry_memory_refs" not in lane_state.content
    assert "lane_safe_resume_token" in lane_state.content


def test_implement_v2_prompt_read_only_mode_does_not_surface_exec_or_write_tools() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "read_only"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    tool_surface = next(section for section in sections if section.id == "implement_v2_tool_surface")

    assert "read_file" in tool_surface.content
    assert "search_text" in tool_surface.content
    assert "glob" in tool_surface.content
    assert "git_status" in tool_surface.content
    assert "finish" in tool_surface.content
    assert "run_command" not in tool_surface.content
    assert "write_file" not in tool_surface.content
    assert "apply_patch" not in tool_surface.content


def test_implement_v2_bypass_mode_fails_closed_until_explicit_policy_exists() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("bypass")}

    assert tools == {"inspect_dir", "read_file", "search_text", "glob", "git_status", "git_diff", "finish"}


def test_implement_v2_exec_mode_surfaces_lifecycle_tools() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("exec")}

    assert {"run_command", "run_tests", "poll_command", "cancel_command", "read_command_output"} <= tools
    assert "write_file" not in tools


def test_implement_v2_write_mode_surfaces_write_tools() -> None:
    tools = {spec.name for spec in list_v2_tool_specs_for_mode("write")}

    assert {"write_file", "edit_file", "apply_patch"} <= tools
    assert {"read_file", "finish"} <= tools
    assert "run_command" not in tools


def test_implement_v2_read_only_fake_runtime_can_inspect_workspace_and_finish_analysis(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def target():\n    return 'ok'\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "inspect_dir", "arguments": {"path": "."}},
            {"provider_call_id": "call-2", "tool_name": "read_file", "arguments": {"path": "src/main.py"}},
            {"provider_call_id": "call-3", "tool_name": "search_text", "arguments": {"query": "target", "path": "."}},
            {"provider_call_id": "call-4", "tool_name": "glob", "arguments": {"pattern": "**/*.py", "path": "."}},
        ),
        finish_arguments={
            "outcome": "analysis_ready",
            "kind": "diagnosis",
            "summary": "target function inspected",
            "open_questions": ["none"],
            "proposed_next_actions": ["run tests in a later write-capable phase"],
        },
    )

    read_only_result = result.updated_lane_state["read_only_result"]
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["replay_valid"] is True
    assert read_only_result["kind"] == "diagnosis"
    assert any(path.endswith("src/main.py") for path in read_only_result["inspected_paths"])
    assert [event.kind for event in result.transcript].count("tool_call") == 4
    assert manifest["lane"] == IMPLEMENT_V2_LANE
    assert len(manifest["tool_calls"]) == 4
    assert len(manifest["tool_results"]) == 4


def test_implement_v2_read_only_finish_cannot_claim_completed(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},),
        finish_arguments={"outcome": "task_complete", "summary": "done"},
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.next_reentry_hint["analysis_ready_is_completion"] is False
    assert result.user_visible_summary.startswith("implement_v2 read-only attempt ended with status=blocked:")


def test_implement_v2_read_only_rejects_path_traversal_and_pairs_error(tmp_path) -> None:
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "../outside-secret.txt"}},
            {"provider_call_id": "call-2", "tool_name": "write_file", "arguments": {"path": "README.md", "content": "mutate"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "errors inspected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    statuses = [item["status"] for item in manifest["tool_results"]]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert statuses == ["failed", "denied"]
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "hello\n"


def test_implement_v2_read_only_large_result_gets_content_ref(tmp_path) -> None:
    (tmp_path / "large.txt").write_text("x" * 20_000, encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "read_file",
                "arguments": {"path": "large.txt", "max_chars": 20_000},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "large file inspected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["content_refs"] == ["implement-v2-read://implement_v2:ws-1:task-1:read-only/call-1/content"]
    assert tool_result["content"][0]["mew_content_truncated"] is True


def test_implement_v2_read_only_git_tools_are_bounded_and_paired(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "tracked.txt").write_text("changed\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},
            {"provider_call_id": "call-2", "tool_name": "git_diff", "arguments": {"cwd": ".", "stat": True}},
        ),
        finish_arguments={"outcome": "analysis_ready", "kind": "plan", "summary": "git state inspected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "analysis_ready"
    assert result.metrics["replay_valid"] is True
    assert [tool_result["status"] for tool_result in manifest["tool_results"]] == ["completed", "completed"]
    assert manifest["tool_results"][1]["content"][0]["stat_forced"] is True
    assert "SECRET=1" not in str(manifest["tool_results"])
    assert result.updated_lane_state["read_only_result"]["kind"] == "plan"


def test_implement_v2_read_only_git_rejects_parent_repo_outside_allowed_root(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    workspace = tmp_path / "subdir"
    workspace.mkdir()

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(workspace),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "parent repo rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "git repository root is outside allowed read roots" in tool_result["content"][0]["reason"]


def test_implement_v2_read_only_git_nonzero_exit_blocks_analysis_ready(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "git_diff", "arguments": {"cwd": ".", "base": "missing-ref"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "invalid ref"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["content"][0]["exit_code"] != 0
    assert tool_result["content"][0]["reason"]


def test_implement_v2_read_only_git_timeout_still_pairs_result(tmp_path, monkeypatch) -> None:
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=15)

    monkeypatch.setattr(read_runtime, "_run_git_probe", raise_timeout)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "git timeout"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["provider_call_id"] == "call-1"


def test_implement_v2_read_only_git_redacts_sensitive_rename_paths(tmp_path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "mew"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "mew@example.invalid"], cwd=tmp_path, check=True)
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    subprocess.run(["git", "add", ".env"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "seed"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "mv", ".env", "public.env"], cwd=tmp_path, check=True)

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=({"provider_call_id": "call-1", "tool_name": "git_status", "arguments": {"cwd": "."}},),
        finish_arguments={"outcome": "analysis_ready", "kind": "diagnosis", "summary": "git status inspected"},
    )
    stdout = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["stdout"]

    assert "[sensitive path redacted]" in stdout
    assert ".env" not in stdout


def test_implement_v2_exec_short_command_finalizes_with_terminal_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "command evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["terminal_evidence_count"] == 1
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert "ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_nonzero_command_blocks_with_paired_failure(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import sys; print('bad'); sys.exit(7)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "failed command evidence"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "failed"
    assert tool_result["is_error"] is True
    assert tool_result["content"][0]["exit_code"] == 7


def test_implement_v2_exec_timeout_is_interrupted_failure_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; time.sleep(5)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 1, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "timed out"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert tool_result["content"][0]["timed_out"] is True


def test_implement_v2_exec_yield_poll_and_read_output(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.2); print('done', flush=True)",
        ]
    )
    lane_attempt_id = "implement_v2:ws-1:task-1:exec"
    command_run_id = _expected_command_run_id(lane_attempt_id=lane_attempt_id, provider_call_id="call-1")
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "poll_command",
                "arguments": {"command_run_id": command_run_id, "wait_seconds": 1},
            },
            {
                "provider_call_id": "call-3",
                "tool_name": "read_command_output",
                "arguments": {"command_run_id": command_run_id},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "polled command evidence ready"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first = manifest["tool_results"][0]
    run_id = first["content"][0]["command_run_id"]
    poll_result = manifest["tool_results"][1]
    read_result = manifest["tool_results"][2]

    assert first["status"] == "yielded"
    assert run_id == command_run_id
    assert poll_result["status"] == "completed"
    assert poll_result["evidence_refs"]
    assert read_result["status"] == "completed"
    assert "done" in read_result["content"][0]["content"]
    assert result.status == "analysis_ready"
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_exec_lifecycle_can_use_known_command_run_id(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    lane_attempt_id = "lane-v2-exec"
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path))
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.2); print('done', flush=True)",
        ]
    )
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
        ),
    )[0]
    start_result = runtime.execute(start_call)
    run_id = start_result.content[0]["command_run_id"]
    poll_call, read_call = adapter.normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=2,
        calls=(
            {"provider_call_id": "call-2", "tool_name": "poll_command", "arguments": {"command_run_id": run_id, "wait_seconds": 1}},
            {"provider_call_id": "call-3", "tool_name": "read_command_output", "arguments": {"command_run_id": run_id}},
        ),
    )

    poll_result = runtime.execute(poll_call)
    read_result = runtime.execute(read_call)

    assert start_result.status == "yielded"
    assert poll_result.status == "completed"
    assert poll_result.evidence_refs
    assert "done" in poll_result.content[0]["stdout"]
    assert read_result.status == "completed"
    assert "done" in read_result.content[0]["content"]


def test_implement_v2_exec_rejects_concurrent_side_effecting_command(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join([sys.executable, "-c", "import time; time.sleep(1)"])
    first_call, second_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 0.01},
            },
        ),
    )

    try:
        first = runtime.execute(first_call)
        second = runtime.execute(second_call)
    finally:
        runtime.runner.cancel("test cleanup")

    assert first.status == "yielded"
    assert second.status == "failed"
    assert "managed command is already running" in second.content[0]["reason"]


def test_implement_v2_exec_cancel_yielded_command_is_interrupted(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"])
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 10, "foreground_budget_seconds": 0.01},
            },
        ),
    )[0]
    start_result = runtime.execute(start_call)
    run_id = start_result.content[0]["command_run_id"]
    cancel_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=2,
        calls=({"provider_call_id": "call-2", "tool_name": "cancel_command", "arguments": {"command_run_id": run_id}},),
    )[0]

    cancel_result = runtime.execute(cancel_call)

    assert start_result.status == "yielded"
    assert cancel_result.status == "interrupted"
    assert cancel_result.is_error is True


def test_implement_v2_exec_rejects_resident_mew_loop_command(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": "./mew work --ai", "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "resident loop rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in tool_result["content"][0]["reason"]


def test_implement_v2_exec_rejects_shell_segment_resident_mew_loop_command(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": "echo ok && ./mew work --ai",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "resident loop rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in tool_result["content"][0]["reason"]


def test_implement_v2_run_tests_rejects_shell_orchestration(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "echo ok && echo verify",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "run_tests executes one argv command without a shell" in tool_result["content"][0]["reason"]


def test_implement_v2_run_tests_rejects_explicit_shell_interpreter(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "bash -lc 'echo ok && echo verify'",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "run_tests executes one argv command without a shell" in tool_result["content"][0]["reason"]


def test_implement_v2_run_tests_rejects_background_redirect_and_env_split_shell(tmp_path) -> None:
    commands = (
        "python -m pytest &",
        "python -m pytest > out.txt",
        "env -S 'bash -lc echo-ok'",
    )
    for index, command in enumerate(commands, start=1):
        result = run_fake_exec_implement_v2(
            ImplementLaneInput(
                work_session_id=f"ws-{index}",
                task_id="task-1",
                workspace=str(tmp_path),
                lane=IMPLEMENT_V2_LANE,
                lane_config={"mode": "exec"},
            ),
            provider_calls=(
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_tests",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ),
            finish_arguments={"outcome": "analysis_ready", "summary": "shell rejected"},
        )
        tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

        assert result.status == "blocked"
        assert tool_result["status"] == "failed"
        assert "run_tests executes one argv command without a shell" in tool_result["content"][0]["reason"]


def test_implement_v2_exec_task_complete_claim_is_blocked_even_with_terminal_evidence(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "task_complete", "summary": "done"},
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_exec_without_explicit_mode_does_not_run_side_effects(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "must not run"},
    )

    assert result.status == "blocked"
    assert result.metrics["exec_mode_enabled"] is False
    assert result.metrics["tool_calls"] == 0
    assert not (tmp_path / "side_effect.txt").exists()


def test_implement_v2_exec_cleans_up_unpolled_yielded_command(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(5)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 10, "foreground_budget_seconds": 0.01},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "not enough evidence"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "interrupted"
    assert tool_result["is_error"] is True
    assert tool_result["content"][0]["status"] == "killed"
    assert result.metrics["terminal_evidence_count"] == 0
    assert result.metrics["orphaned_command_cleanup_count"] == 1


def test_implement_v2_exec_rejects_duplicate_provider_call_ids_before_side_effects(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('side_effect.txt').write_text('bad', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "dup-call",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
            {
                "provider_call_id": "dup-call",
                "tool_name": "read_file",
                "arguments": {"path": "side_effect.txt"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "duplicate call ids rejected"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "failed"
    assert result.metrics["replay_valid"] is False
    assert [tool_result["status"] for tool_result in manifest["tool_results"]] == ["invalid", "invalid"]
    assert "duplicate_provider_call_id:dup-call" in result.metrics["replay_errors"]
    assert not (tmp_path / "side_effect.txt").exists()


def test_implement_v2_write_file_dry_run_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "out.txt", "content": "ok\n", "create": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "dry run ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert result.metrics["completion_credit"] is False
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert tool_result["content"][0]["written"] is False
    assert tool_result["content_refs"]
    assert not target.exists()


def test_implement_v2_write_file_approved_apply_records_mutation_evidence(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "ok\n"
    assert result.metrics["write_evidence_count"] == 1
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is False
    assert tool_result["content"][0]["written"] is True
    assert tool_result["evidence_refs"]
    assert tool_result["content"][0]["approval_id"] == "approval-1"
    assert tool_result["side_effects"][0]["approval_status"] == "approved"
    assert tool_result["side_effects"][0]["approval_id"] == "approval-1"


def test_implement_v2_write_file_provider_self_approval_is_ignored(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                    "approval": {"status": "approved", "approval_id": "self-approved"},
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "provider self-approval ignored"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "denied"
    assert "provider-supplied approval arguments are ignored" in tool_result["content"][0]["reason"]
    assert not target.exists()


def test_implement_v2_write_file_denied_approval_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "out.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "ok\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "denied",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write denied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "denied"
    assert tool_result["is_error"] is True
    assert not target.exists()


def test_implement_v2_write_mode_without_explicit_mode_does_not_mutate(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "allowed_write_roots": ["."],
                "approved_write_calls": [{"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"}],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "out.txt",
                    "content": "bad\n",
                    "create": True,
                    "apply": True,
                    "approval_status": "approved",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "must not run"},
    )

    assert result.status == "blocked"
    assert result.metrics["write_mode_enabled"] is False
    assert not (tmp_path / "out.txt").exists()


def test_implement_v2_write_rejects_paths_outside_allowed_write_roots(tmp_path) -> None:
    outside = tmp_path.parent / "outside.txt"

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": str(outside),
                    "content": "bad\n",
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "outside rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "outside allowed write roots" in tool_result["content"][0]["reason"]
    assert not outside.exists()


def test_implement_v2_edit_file_exact_old_dry_run_and_no_match_failure(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("alpha\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "alpha\n", "new": "beta\n"},
            },
            {
                "provider_call_id": "call-2",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "missing\n", "new": "nope\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "edit preview"},
    )
    manifest = result.updated_lane_state["proof_manifest"]

    assert result.status == "blocked"
    assert manifest["tool_results"][0]["status"] == "completed"
    assert manifest["tool_results"][0]["content"][0]["dry_run"] is True
    assert manifest["tool_results"][1]["status"] == "failed"
    assert target.read_text(encoding="utf-8") == "alpha\n"


def test_implement_v2_edit_file_ambiguous_match_fails_closed(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("same\nsame\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {"path": "README.md", "old": "same\n", "new": "other\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "ambiguous"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "old text matched 2 times" in tool_result["content"][0]["reason"]
    assert target.read_text(encoding="utf-8") == "same\nsame\n"


def test_implement_v2_apply_patch_parse_failure_pairs_error(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": "*** End Patch\n"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "parse failure"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "must start with *** Begin Patch" in tool_result["content"][0]["reason"]


def test_implement_v2_apply_patch_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )
    apply = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True, "approval_status": "approved"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["dry_run"] is True
    assert apply.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "new\n"
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_denied_approval_does_not_mutate(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True, "approval_status": "rejected"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch denied"},
    )

    assert result.status == "blocked"
    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "denied"
    assert target.read_text(encoding="utf-8") == "old\n"


def test_implement_v2_write_rejects_symlink_escape(tmp_path) -> None:
    outside = tmp_path.parent / "outside-link-target.txt"
    outside.write_text("outside\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(outside)

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "link.txt",
                    "content": "bad\n",
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "symlink rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert outside.read_text(encoding="utf-8") == "outside\n"


def test_implement_v2_write_rejects_governance_paths_by_default(tmp_path) -> None:
    target = tmp_path / "ROADMAP_STATUS.md"
    target.write_text("old\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "ROADMAP_STATUS.md", "content": "new\n"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "governance preview rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "governance write path is protected" in tool_result["content"][0]["reason"]
    assert target.read_text(encoding="utf-8") == "old\n"


def test_implement_v2_write_replay_rejects_mutation_without_independent_approval(tmp_path) -> None:
    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {"path": "out.txt", "content": "ok\n", "create": True, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "write applied"},
    )

    manifest = result.updated_lane_state["proof_manifest"]
    manifest["tool_results"][0]["side_effects"][0]["approval_id"] = ""
    from mew.implement_lane.replay import validate_proof_manifest_write_safety
    from mew.implement_lane.types import ImplementLaneProofManifest, ToolCallEnvelope, ToolResultEnvelope

    rebuilt_manifest = ImplementLaneProofManifest(
        lane=manifest["lane"],
        lane_attempt_id=manifest["lane_attempt_id"],
        artifact_namespace=manifest["artifact_namespace"],
        tool_calls=tuple(ToolCallEnvelope(**_without_schema_version(item)) for item in manifest["tool_calls"]),
        tool_results=tuple(ToolResultEnvelope(**_without_schema_version(item)) for item in manifest["tool_results"]),
    )
    validation = validate_proof_manifest_write_safety(rebuilt_manifest)

    assert validation.valid is False
    assert "write_side_effect_missing_approval_id:call-1:0" in validation.errors


def test_implement_v2_write_mode_rejects_run_command_hidden_mutation(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('out.txt').write_text('hidden', encoding='utf-8')",
        ]
    )

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "hidden mutation rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert tool_result["status"] == "invalid"
    assert "not available in implement_v2 write mode" in tool_result["content"][0]["reason"]
    assert not (tmp_path / "out.txt").exists()


def test_m6_24_reentry_gate_allows_explicit_lane_after_v2_replay_valid_probe(tmp_path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "README.md"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe ok"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V1_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "ready"
    assert gate.can_resume_m6_24 is True
    assert gate.reasons == ()
    assert gate.lane_decision["selected_lane"] == IMPLEMENT_V1_LANE
    assert gate.metrics["v2_replay_valid"] is True
    assert "implement_v1" in gate.v1_artifact_namespace
    assert "implement_v2" in gate.v2_artifact_namespace
    assert gate.v1_artifact_namespace != gate.v2_artifact_namespace


def test_m6_24_reentry_gate_blocks_missing_explicit_lane(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(),
        finish_arguments={"outcome": "analysis_ready", "summary": "no evidence"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane="",
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert gate.can_resume_m6_24 is False
    assert "explicit_supported_lane_selection_required" in gate.reasons


def test_m6_24_reentry_gate_blocks_invalid_v2_replay(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "dup", "tool_name": "inspect_dir", "arguments": {"path": "."}},
            {"provider_call_id": "dup", "tool_name": "read_file", "arguments": {"path": "README.md"}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "duplicate ids"},
    )

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V2_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert gate.can_resume_m6_24 is False
    assert "v2_probe_replay_not_valid" in gate.reasons


def test_m6_24_reentry_gate_blocks_artifact_namespace_collision(tmp_path) -> None:
    v2_probe = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "inspect_dir", "arguments": {"path": "."}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe ok"},
    ).as_dict()
    v1_namespace = describe_implement_v1_adapter(work_session_id="ws-1", task_id="task-1").artifact_namespace
    v2_probe["updated_lane_state"]["proof_manifest"]["artifact_namespace"] = v1_namespace

    gate = evaluate_m6_24_reentry_ab_gate(
        work_session_id="ws-1",
        task_id="task-1",
        selected_lane=IMPLEMENT_V2_LANE,
        v2_result=v2_probe,
        v1_baseline_valid=True,
    )

    assert gate.status == "blocked"
    assert "v1_v2_artifact_namespace_collision" in gate.reasons
    assert "v2_manifest_namespace_mismatch" in gate.reasons


def _expected_command_run_id(*, lane_attempt_id: str, provider_call_id: str) -> str:
    digest = hashlib.sha256(f"{lane_attempt_id}:{provider_call_id}".encode()).hexdigest()
    return f"{lane_attempt_id}:command:{provider_call_id}-{digest[:8]}"


def _write_lane_input(tmp_path, *, approved_write_calls=()) -> ImplementLaneInput:
    return ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        lane_config={
            "mode": "write",
            "allowed_write_roots": ["."],
            "approved_write_calls": list(approved_write_calls),
        },
    )


def _without_schema_version(item: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key != "schema_version"}
