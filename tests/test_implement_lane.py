import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

import mew.implement_lane.read_runtime as read_runtime
import mew.implement_lane.exec_runtime as exec_runtime
import mew.implement_lane.v2_runtime as v2_runtime
import pytest
from mew.errors import ModelBackendError
from mew.implement_lane.exec_runtime import _source_like_mutation_paths
from mew.implement_lane import (
    DEFAULT_WORKFRAME_VARIANT,
    IMPLEMENT_V2_NATIVE_RUNTIME_ID,
    ImplementLaneInput,
    ImplementLaneProofManifest,
    ImplementLaneResult,
    ImplementLaneTranscriptEvent,
    ToolCallEnvelope,
    ToolResultEnvelope,
    WorkFrameInputs,
    build_invalid_tool_result,
    build_implement_v2_prompt_sections,
    common_workframe_inputs_from_workframe_inputs,
    describe_implement_v1_adapter,
    describe_implement_v2_runtime,
    evaluate_m6_24_reentry_ab_gate,
    get_implement_lane_runtime_view,
    implement_v2_prompt_section_metrics,
    describe_workframe_variant,
    list_implement_lane_runtime_views,
    list_workframe_variants,
    list_v2_base_tool_specs,
    list_v2_tool_specs_for_mode,
    project_workframe_with_variant,
    select_implement_lane_runtime,
    normalize_workframe_variant,
    validate_proof_manifest_pairing,
    validate_tool_result_pairing,
    validate_workframe_variant_name,
)
from mew.implement_lane.tool_policy import list_v2_tool_specs_for_task
from mew.implement_lane.provider import FakeProviderAdapter, FakeProviderToolCall
from mew.implement_lane.legacy_shell_edit_bridge import bridge_registry_manifest
from mew.implement_lane.v2_runtime import (
    ModelTurnInput,
    _auto_finish_from_structured_final_verifier,
    _call_model_turn,
    _command_has_verifier_surface,
    _deep_runtime_prewrite_probe_readiness,
    _deep_runtime_prewrite_probe_gate_result,
    _deep_runtime_prewrite_missing_probe,
    _finish_acceptance_action,
    _finish_evidence_refs,
    _finish_gate_history,
    _first_write_probe_threshold,
    _first_write_readiness_from_trace,
    _frontier_evidence_registry,
    _frontier_failure_payload,
    _frontier_state_from_execution_contracts,
    _hard_runtime_frontier_progress_signature,
    _hard_runtime_progress_continuation_signature,
    _hard_runtime_progress_continuation_turn_limit,
    _has_completed_source_tree_mutation,
    _live_json_prompt,
    _model_visible_tool_specs_for_turn,
    _post_failure_source_mutation_count,
    _PROVIDER_HISTORY_SOURCE_MUTATION_KEYS,
    _provider_visible_tool_call_for_history,
    _provider_visible_tool_result_for_history,
    _render_prompt_history_json,
    _resident_sidecar_state_metrics,
    _required_patch_model_turn_budget_block,
    _shell_command_may_mutate_source_tree,
    _source_output_contract_from_tool_results,
    _source_output_contract_probe_candidate_from_trace,
    _source_mutation_roots,
    _terminal_failure_reaction_turn_limit,
    _typed_finish_evidence_refs,
    _typed_retired_legacy_blockers_for_bundle,
    _workframe_sidecar_events_from_tool_results,
    _write_result_covers_source_tree_mutation,
    run_fake_exec_implement_v2,
    run_fake_read_only_implement_v2,
    run_fake_write_implement_v2,
    run_live_json_implement_v2,
    run_unavailable_implement_v2,
)
from mew.implement_lane.prompt import build_implement_v2_workframe_debug_bundle
from mew.implement_lane.shell_metadata import classify_shell_command_metadata
from mew.implement_lane.tool_routes import build_tool_route_decision
from mew.read_tools import read_file
from mew.work_lanes import IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE, TINY_LANE


def test_implementation_runtime_registry_keeps_v1_default_and_v2_explicit() -> None:
    runtimes = list_implement_lane_runtime_views()

    assert [runtime.lane for runtime in runtimes] == [IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE]
    assert runtimes[0].default is True
    assert runtimes[0].runtime_available is True
    assert runtimes[0].provider_native_tool_loop is False
    assert runtimes[1].default is False
    assert runtimes[1].runtime_available is True
    assert runtimes[1].runtime_id == IMPLEMENT_V2_NATIVE_RUNTIME_ID
    assert runtimes[1].provider_native_tool_loop is True
    assert runtimes[1].writes_allowed is True


def test_legacy_tiny_and_unknown_lanes_resolve_to_implement_v1_runtime() -> None:
    for lane in (None, "", TINY_LANE, "unknown-lane"):
        assert get_implement_lane_runtime_view(lane).lane == IMPLEMENT_V1_LANE


def test_implement_v2_typed_retirement_is_family_specific() -> None:
    blockers = _typed_retired_legacy_blockers_for_bundle(
        {
            "obligations": [
                {"kind": "artifact_exists"},
                {"kind": "visual_similarity"},
            ]
        },
        task_description="Run the VM and compare the rendered frame to the reference image.",
    )

    assert "runtime_final_verifier_artifact_evidence" in blockers
    assert "runtime_visual_artifact_quality_evidence" in blockers
    assert "acceptance_constraints_unchecked" not in blockers


def test_implement_v2_typed_retirement_does_not_treat_dimensions_as_visual_quality() -> None:
    blockers = _typed_retired_legacy_blockers_for_bundle(
        {
            "obligations": [
                {"kind": "artifact_exists"},
                {"kind": "visual_dimension"},
            ]
        },
        task_description="Run the VM and compare the rendered frame to the reference image.",
    )

    assert "runtime_final_verifier_artifact_evidence" not in blockers
    assert "runtime_visual_artifact_quality_evidence" not in blockers


def test_explicit_implement_v2_selection_returns_v2_runtime() -> None:
    selected = select_implement_lane_runtime(requested_lane=IMPLEMENT_V2_LANE, allow_v2=True)

    assert selected.lane == IMPLEMENT_V2_LANE
    assert selected.runtime_available is True


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


def test_implement_v2_descriptor_exposes_live_runtime_and_tools() -> None:
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
    assert description["runtime_available"] is True
    assert description["provider_native_tool_loop"] is True
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


def test_workframe_variant_registry_exposes_current_alias_and_transition_contract_default() -> None:
    variants = list_workframe_variants()

    assert [variant.name for variant in variants] == [
        "current",
        "minimal",
        "transcript_first",
        "transcript_tool_nav",
        "transition_contract",
    ]
    assert DEFAULT_WORKFRAME_VARIANT == "transition_contract"
    assert normalize_workframe_variant(None) == "transition_contract"
    assert normalize_workframe_variant("") == "transition_contract"
    assert normalize_workframe_variant("   ") == "transition_contract"
    assert describe_workframe_variant().name == "transition_contract"
    assert validate_workframe_variant_name("current") == "current"
    assert "Current M6.24" in variants[0].description


def test_workframe_debug_bundle_defaults_to_transition_contract_when_variant_omitted_or_blank() -> None:
    omitted = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "Repair the workspace."},
    )
    blank = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"workframe_variant": " "},
        task_contract={"objective": "Repair the workspace."},
    )

    omitted_bundle = build_implement_v2_workframe_debug_bundle(omitted, turn_id="turn-variant")
    blank_bundle = build_implement_v2_workframe_debug_bundle(blank, turn_id="turn-variant")

    assert omitted_bundle["workframe_variant"] == "transition_contract"
    assert omitted_bundle["reducer_inputs"]["workframe_variant"] == "transition_contract"
    assert omitted_bundle["workframe_cursor"]["workframe_variant"] == "transition_contract"
    assert blank_bundle["workframe_variant"] == "transition_contract"
    assert blank_bundle["reducer_inputs"]["workframe_variant"] == "transition_contract"
    assert blank_bundle["workframe_cursor"]["workframe_variant"] == "transition_contract"


def test_workframe_debug_bundle_records_variant() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"workframe_variant": "current"},
        task_contract={"objective": "Repair the workspace."},
    )

    bundle = build_implement_v2_workframe_debug_bundle(lane_input, turn_id="turn-variant")

    assert bundle["workframe_variant"] == "current"
    assert bundle["reducer_inputs"]["workframe_variant"] == "current"
    assert bundle["workframe_cursor"]["workframe_variant"] == "current"


def test_workframe_projection_keeps_shared_substrate_hash_stable_across_variants() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-variant",
        turn_id="turn-variant",
        task_id="task-variant",
        objective="Repair the workspace.",
        sidecar_events=(
            {
                "kind": "verifier",
                "event_id": "tool-result:verify",
                "event_sequence": 1,
                "status": "failed",
                "family": "runtime_failure",
                "summary": "TypeError: undefined",
                "evidence_refs": ["ev:verify"],
            },
        ),
    )
    common = common_workframe_inputs_from_workframe_inputs(inputs)

    current = project_workframe_with_variant(common, variant="current")
    minimal = project_workframe_with_variant(common, variant="minimal")

    assert current.shared_substrate_hash == minimal.shared_substrate_hash
    assert current.projection_hash != minimal.projection_hash
    assert current.common_inputs.as_dict()["indexes"]["model_turn_index_usage"] == "debug_plateau_recovery_only"


def test_workframe_debug_bundle_records_common_substrate_and_static_shape() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"workframe_variant": "minimal"},
        task_contract={"objective": "Repair the workspace."},
    )

    bundle = build_implement_v2_workframe_debug_bundle(lane_input, turn_id="turn-variant")
    reducer_inputs = bundle["reducer_inputs"]
    cursor = bundle["workframe_cursor"]
    render_inventory = bundle["prompt_render_inventory"]

    assert reducer_inputs["schema_version"] == 2
    assert reducer_inputs["common_workframe_inputs_schema_version"] == 1
    assert reducer_inputs["shared_substrate_hash"] == cursor["shared_substrate_hash"]
    assert reducer_inputs["canonical"]["payload"]["indexes"]["model_turn_index_usage"] == "debug_plateau_recovery_only"
    assert render_inventory["static_shape"] == [
        "static_instructions",
        "task_contract_digest",
        "natural_transcript_tail",
        "one_workframe_projection",
    ]
    assert render_inventory["projection_hash"] == cursor["projection_hash"]


def test_workframe_debug_bundle_keeps_prompt_inventory_out_of_shared_substrate_hash() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"workframe_variant": "minimal"},
        task_contract={"objective": "Repair the workspace."},
    )
    without_inventory = build_implement_v2_workframe_debug_bundle(lane_input, turn_id="turn-variant")
    with_inventory = build_implement_v2_workframe_debug_bundle(
        lane_input,
        turn_id="turn-variant",
        prompt_inventory=(
            {
                "id": "implement_v2_workframe",
                "chars": 999,
                "variant_rendered_section": True,
            },
        ),
    )

    assert (
        without_inventory["reducer_inputs"]["shared_substrate_hash"]
        == with_inventory["reducer_inputs"]["shared_substrate_hash"]
    )
    assert with_inventory["reducer_inputs"]["common_workframe_inputs"]["current_workframe_inputs"]["prompt_inventory"] == []
    assert with_inventory["prompt_render_inventory"]["source_prompt_inventory"][0]["id"] == "implement_v2_workframe"


def test_transcript_tool_nav_projects_advisory_tool_context_without_default_flip() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-nav",
        task_id="task-nav",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full", "workframe_variant": "transcript_tool_nav"},
        task_contract={"objective": "Repair the runtime failure."},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:runtime",
            "event_sequence": 1,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "TypeError: cannot read property 'pc' of undefined",
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:runtime"],
        },
    )

    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=runtime_events)
    workframe = bundle["reducer_output"]
    visible_workframe = bundle["prompt_visible_workframe"]["workframe"]
    tool_context = workframe["tool_context"]

    assert DEFAULT_WORKFRAME_VARIANT == "transition_contract"
    assert workframe["schema_version"] == 3
    assert workframe["variant"]["name"] == "transcript_tool_nav"
    assert visible_workframe["variant"]["name"] == "transcript_tool_nav"
    assert visible_workframe["tool_context"]["recommended_tool_refs"]
    assert workframe["required_next"] is None
    assert workframe["latest_actionable"]["summary"] == "TypeError: cannot read property 'pc' of undefined"
    assert "tool:finish" in {item["tool_ref"] for item in tool_context["disabled_tool_refs"]}
    assert {"tool:apply_patch", "tool:edit_file"} & {
        item["tool_ref"] for item in tool_context["recommended_tool_refs"]
    }
    assert tool_context["model_turn_search"]["usage"] == "debug_plateau_recovery_only"
    rendered_tool_context = json.dumps(tool_context).lower()
    assert "parameters" not in rendered_tool_context
    assert "implementation" not in rendered_tool_context


def test_transcript_tool_nav_uses_active_mode_tool_surface_for_recommendations() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-nav",
        task_id="task-nav",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"workframe_variant": "transcript_tool_nav"},
        task_contract={"objective": "Repair the runtime failure."},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:runtime",
            "event_sequence": 1,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "TypeError: cannot read property 'pc' of undefined",
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:runtime"],
        },
    )

    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=runtime_events)
    tool_context = bundle["reducer_output"]["tool_context"]
    active_refs = set(tool_context["active_tool_refs"])
    recommended_refs = {item["tool_ref"] for item in tool_context["recommended_tool_refs"]}

    assert "tool:apply_patch" not in active_refs
    assert "tool:edit_file" not in active_refs
    assert "tool:write_file" not in active_refs
    assert not (recommended_refs & {"tool:apply_patch", "tool:edit_file", "tool:write_file"})
    assert "tool:read_file" in recommended_refs


def test_transcript_tool_nav_respects_explicit_prompt_tool_surface_override() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-nav",
        task_id="task-nav",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full", "workframe_variant": "transcript_tool_nav"},
        task_contract={"objective": "Repair the runtime failure."},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:runtime",
            "event_sequence": 1,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "TypeError: cannot read property 'pc' of undefined",
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:runtime"],
        },
    )
    sections = build_implement_v2_prompt_sections(lane_input, tool_specs=list_v2_tool_specs_for_mode("read_only"))
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        sidecar_events=runtime_events,
        provider_tool_names=tuple(spec.name for spec in list_v2_tool_specs_for_mode("read_only")),
    )
    workframe_prompt = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_workframe" not in {section.id for section in sections}
    assert "tool:read_file" in workframe_prompt
    assert "tool:apply_patch" not in workframe_prompt
    assert "tool:edit_file" not in workframe_prompt
    assert "tool:write_file" not in workframe_prompt


def test_transcript_tool_nav_preserves_missing_obligation_controller_required_next() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-nav",
        task_id="task-nav",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full", "workframe_variant": "transcript_tool_nav"},
        task_contract={"objective": "Do not finish with missing typed obligations."},
    )
    verifier_events = (
        {
            "kind": "strict_verifier",
            "event_sequence": 1,
            "event_id": "verify-1",
            "status": "passed",
            "typed_evidence_id": "ev:verify-1",
            "execution_contract_normalized": {
                "id": "contract:verify-1",
                "role": "verify",
                "proof_role": "verifier",
                "acceptance_kind": "external_verifier",
            },
            "missing_obligations": ["oracle:artifact-fresh"],
        },
    )

    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=verifier_events)
    workframe = bundle["reducer_output"]

    assert workframe["finish_readiness"]["state"] == "blocked"
    assert workframe["required_next"]["kind"] == "run_verifier"
    assert workframe["required_next"]["evidence_refs"] == ["oracle:artifact-fresh"]
    assert workframe["obligations"]["missing_or_stale_refs"] == ["oracle:artifact-fresh"]


def test_workframe_variant_is_not_rendered_in_lane_state_prompt() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-variant",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full", "workframe_variant": "current"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_lane_state" not in {section.id for section in sections}
    assert "workframe_variant" not in rendered


def test_workframe_variant_is_not_rendered_from_task_contract_prompt() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-variant-task",
        task_id="task-variant",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "goal": "ship the implementation",
            "workframe_variant": "current",
            "nested": {"required_next_action": "patch vm.js"},
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "ship the implementation" in rendered
    assert "workframe_variant" not in rendered
    assert "required_next_action" not in rendered
    assert "patch vm.js" not in rendered


def test_implement_v2_live_json_runtime_can_edit_verify_and_finish(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    outputs = [
        {
            "summary": "inspect file",
            "tool_calls": [
                {"id": "read-1", "name": "read_file", "arguments": {"path": "sample.txt"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "apply exact edit",
            "tool_calls": [
                {
                    "id": "edit-1",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "observe a failing verifier before recovery",
            "tool_calls": [
                {
                    "id": "verify-bad-1",
                    "name": "run_command",
                    "arguments": {"command": "false", "cwd": ".", "use_shell": True, "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "verify behavior",
            "tool_calls": [
                {
                    "id": "verify-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "test \"$(cat sample.txt)\" = after",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "file edited and verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=4,
    )

    assert result.status == "completed"
    assert result.metrics["provider"] == "model_json"
    assert result.metrics["tool_calls"] == 4
    assert result.metrics["write_evidence_count"] == 1
    assert result.metrics["terminal_evidence_count"] == 1
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_blocks_unaccounted_run_command_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "completed", "summary": "source mutated"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    side_effect_kinds = {effect["kind"] for effect in tool_result["side_effects"]}

    assert result.status == "blocked"
    assert "process_source_observation" in side_effect_kinds
    assert "source_tree_mutation" not in side_effect_kinds
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_process_source_observation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_verifier_accounts_for_run_command_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "verify mutated source",
            "tool_calls": [
                {
                    "id": "verify-source",
                    "name": "run_command",
                    "arguments": {
                        "command": "test \"$(cat sample.txt)\" = after",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "execution_contract": {
                            "role": "verify",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "source mutated and verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    blocker_codes = {
        str(blocker.get("code") or "")
        for blocker in result.metrics["finish_gate_decision"].get("blockers", [])
        if isinstance(blocker, dict)
    }
    assert result.status == "blocked"
    assert "unaccounted_source_tree_mutation" not in blocker_codes
    assert "unaccounted_process_source_observation" not in blocker_codes
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_unrelated_write_does_not_account_for_shell_source_mutation(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write unrelated file",
            "tool_calls": [
                {
                    "id": "write-other",
                    "name": "write_file",
                    "arguments": {"path": "other.txt", "content": "ok\n"},
                },
            ],
            "finish": {"outcome": "completed", "summary": "unrelated write done"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_process_source_observation"
    assert target.read_text(encoding="utf-8") == "after\n"
    assert (tmp_path / "other.txt").read_text(encoding="utf-8") == "ok\n"


def test_implement_v2_live_json_keeps_earlier_unaccounted_shell_source_mutation(tmp_path) -> None:
    first = tmp_path / "first.py"
    second = tmp_path / "second.py"
    first.write_text("before\n", encoding="utf-8")
    second.write_text("before\n", encoding="utf-8")
    mutate_first = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('first.py').write_text('after\\n', encoding='utf-8')",
        ]
    )
    mutate_second = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('second.py').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate first source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-first",
                    "name": "run_command",
                    "arguments": {"command": mutate_first, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "mutate second source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-second",
                    "name": "run_command",
                    "arguments": {"command": mutate_second, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "cover only second mutation",
            "tool_calls": [
                {
                    "id": "write-second",
                    "name": "write_file",
                    "arguments": {"path": "second.py", "content": "final\n"},
                },
            ],
            "finish": {"outcome": "completed", "summary": "covered latest mutation only"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    blocker = result.metrics["finish_gate_decision"]["blockers"][0]
    assert result.status == "blocked"
    assert blocker["code"] == "unaccounted_process_source_observation"
    assert blocker["changed_count"] == 1
    assert any(str(path).endswith("first.py") for path in blocker["changed_paths"])
    assert first.read_text(encoding="utf-8") == "after\n"
    assert second.read_text(encoding="utf-8") == "final\n"


def test_implement_v2_write_does_not_account_for_truncated_shell_source_mutation() -> None:
    mutation = {
        "changed_count": 41,
        "changes": [{"path": f"/workspace/src/file_{index}.py", "change": "modified"} for index in range(40)],
        "truncated": True,
    }
    write_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="write-many",
        mew_tool_call_id="mew-write-many",
        tool_name="write_file",
        status="completed",
        side_effects=tuple(
            {
                "kind": "file_write",
                "path": f"/workspace/src/file_{index}.py",
                "written": True,
            }
            for index in range(40)
        ),
    )

    assert _write_result_covers_source_tree_mutation(write_result, mutation) is False


def test_implement_v2_live_json_superficial_check_text_does_not_account_for_shell_source_mutation(
    tmp_path,
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    command = (
        shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
        + "; echo test"
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write-check",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "use_shell": True, "timeout": 10},
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "source mutated",
                "acceptance_evidence": ["shell-write-check confirmed sample.txt"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_process_source_observation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_live_json_structured_label_without_verifier_evidence_does_not_account_for_shell_source_mutation(
    tmp_path,
) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    mutate_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.txt').write_text('after\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "mutate source through shell",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {"command": mutate_command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "fake verifier label",
            "tool_calls": [
                {
                    "id": "fake-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "execution_contract": {
                            "role": "verify",
                            "stage": "verification",
                            "proof_role": "default_smoke",
                            "acceptance_kind": "candidate_runtime_smoke",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                },
            ],
            "finish": {"outcome": "completed", "summary": "fake smoke passed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "unaccounted_process_source_observation"
    assert target.read_text(encoding="utf-8") == "after\n"


def test_implement_v2_verifier_surface_requires_command_boundary() -> None:
    assert _command_has_verifier_surface("echo test") is False
    assert _command_has_verifier_surface("echo pytest") is False
    assert _command_has_verifier_surface("printf ok; test -f sample.txt") is True
    assert _command_has_verifier_surface("uv run pytest tests/test_sample.py") is True
    assert _command_has_verifier_surface("python -m unittest tests.test_sample") is True
    assert _command_has_verifier_surface("cargo test") is True


def test_implement_v2_live_json_accept_edits_defaults_new_write_to_create_and_apply(tmp_path) -> None:
    target = tmp_path / "generated.txt"
    outputs = [
        {
            "summary": "write the implementation artifact",
            "tool_calls": [
                {
                    "id": "write-1",
                    "name": "write_file",
                    "arguments": {"path": "generated.txt", "content": "ok\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write for inspection"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_call = manifest["tool_calls"][0]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 1
    assert target.read_text(encoding="utf-8") == "ok\n"
    assert tool_call["arguments"]["apply"] is True
    assert tool_call["arguments"]["create"] is True
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is False
    assert tool_result["content"][0]["written"] is True
    assert tool_result["content"][0]["approval_source"] == "cli_accept_edits"


def test_implement_v2_records_first_write_frontier_stall_after_missing_target_timeout(tmp_path) -> None:
    outputs = [
        {
            "summary": "probe source and inspect target before writing",
            "tool_calls": [
                {
                    "id": "call-probe-source",
                    "name": "inspect_dir",
                    "arguments": {"path": "."},
                },
                {
                    "id": "call-read-target",
                    "name": "read_file",
                    "arguments": {"path": "generated.js"},
                },
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        raise ModelBackendError("request timed out")

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    stall = frontier["first_write_frontier_stall"]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert result.metrics["model_error"]["semantic_failure_class"] == "first_write_frontier_stall"
    assert stall["failure_class"] == "first_write_frontier_stall"
    assert stall["target_path"] == "generated.js"
    assert "write_file/edit_file/apply_patch" in stall["required_next_action"]
    assert "keep run_command for build, runtime, verifier commands" in stall["required_next_action"]
    manifest = result.updated_lane_state["proof_manifest"]
    synthetic_result = manifest["tool_results"][-1]
    assert synthetic_result["tool_name"] == "model_response_error"
    assert synthetic_result["content"][0]["failure_class"] == "first_write_frontier_stall"
    assert synthetic_result["content"][0]["raw_failure_class"] == "model_timeout"


def test_implement_v2_clears_first_write_frontier_stall_after_successful_write(tmp_path) -> None:
    target = tmp_path / "generated.js"
    outputs = [
        {
            "summary": "write the missing first target",
            "tool_calls": [
                {
                    "id": "call-write-target",
                    "name": "write_file",
                    "arguments": {"path": "generated.js", "content": "console.log('ok')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "schema_version": 1,
                    "status": "blocked",
                    "first_write_frontier_stall": {
                        "failure_class": "first_write_frontier_stall",
                        "target_path": "generated.js",
                    },
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert result.metrics["write_evidence_count"] == 1
    assert target.exists()
    assert "first_write_frontier_stall" not in frontier


def test_implement_v2_records_active_work_todo_first_write_due_after_probe_threshold(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert result.status == "blocked"
    assert readiness["status"] == "due"
    assert readiness["first_write_due"] is True
    assert readiness["probes_seen_without_write"] == 3
    assert readiness["probe_count_before_first_write"] == 3
    assert readiness["target_paths"] == ["sample.py"]
    assert "write_file/edit_file/apply_patch" in readiness["required_next_action"]
    assert "rather than shell writers" in readiness["required_next_action"]
    assert result.metrics["first_write_due"] is True
    assert result.metrics["first_write_probe_count"] == 3


def test_implement_v2_first_write_threshold_defaults_to_deeper_hard_runtime_probe_budget(tmp_path) -> None:
    hard_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    normal_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-2",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Patch a Python bug and run tests."},
    )
    normal_node_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-node",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Fix a runtime bug in the provided Node project so stdout logs show the correct result."
        },
    )
    self_contained_source_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-self",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Build the provided self-contained source project and write a screenshot image."},
    )
    jvm_project_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-jvm",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Fix JVM image build in provided source project."},
    )
    configured_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-3",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"first_write_probe_threshold": 4},
    )

    assert _first_write_probe_threshold(hard_runtime_input) == 8
    assert _first_write_probe_threshold(normal_input) == 3
    assert _first_write_probe_threshold(normal_node_runtime_input) == 3
    assert _first_write_probe_threshold(self_contained_source_input) == 3
    assert _first_write_probe_threshold(jvm_project_input) == 3
    assert _first_write_probe_threshold(configured_input) == 4


def test_implement_v2_blocks_hard_runtime_write_before_deep_prewrite_probe_budget(tmp_path) -> None:
    (tmp_path / "doomgeneric_mips").write_bytes(b"\x7fELFfake")
    (tmp_path / "doomgeneric").mkdir()
    (tmp_path / "doomgeneric" / "i_video.c").write_text("void I_FinishUpdate(void) {}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap hard-runtime probes",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-elf", "name": "run_command", "arguments": {"command": "file doomgeneric_mips", "cwd": "."}},
                {"id": "probe-src", "name": "search_text", "arguments": {"query": "I_FinishUpdate", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write runtime too early and verify",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                },
                {"id": "verify", "name": "run_command", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    write_result = next(item for item in tool_results if item["provider_call_id"] == "write-vm")
    verify_result = next(item for item in tool_results if item["provider_call_id"] == "verify")
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert result.status == "blocked"
    assert not (tmp_path / "vm.js").exists()
    assert write_result["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in write_result["content"][0]["reason"]
    assert verify_result["status"] == "invalid"
    assert "blocked_by_deep_runtime_prewrite_probe_gate" in verify_result["content"][0]["reason"]
    assert readiness["probe_threshold"] == 8
    assert readiness["probe_count_before_first_write"] == 3
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "write_file"
    assert "first_source_mutation_turn" not in readiness


def test_implement_v2_prewrite_block_suggests_source_output_read_from_prior_glob(tmp_path) -> None:
    (tmp_path / "doomgeneric_mips").write_bytes(b"\x7fELFfake")
    source_dir = tmp_path / "doomgeneric" / "doomgeneric"
    source_dir.mkdir(parents=True)
    (source_dir / "doomgeneric_img.c").write_text("void DG_DrawFrame(void) {}\n", encoding="utf-8")
    probe_command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "print('file readelf ELF little endian main symbol syscall hook api "
                "open read write opcode instruction')"
            ),
        ]
    )
    outputs = [
        {
            "summary": "find cheap source/runtime surfaces",
            "tool_calls": [
                {"id": "probe-sources", "name": "glob", "arguments": {"path": ".", "pattern": "doomgeneric/**/*"}},
                {"id": "probe-binary", "name": "run_command", "arguments": {"command": probe_command, "cwd": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write before source output contract read",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before source output read"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
                "first_write_probe_threshold": 2,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    write_result = next(item for item in tool_results if item["provider_call_id"] == "write-vm")
    payload = write_result["content"][0]

    assert result.status == "blocked"
    assert not (tmp_path / "vm.js").exists()
    assert write_result["status"] == "invalid"
    assert payload["failure_subclass"] == "deep_runtime_source_output_contract_missing"
    assert payload["suggested_next_probe"]["tool"] == "read_file"
    assert payload["suggested_next_probe"]["arguments"]["path"] == "doomgeneric/doomgeneric/doomgeneric_img.c"
    assert "read_file doomgeneric/doomgeneric/doomgeneric_img.c" in payload["required_next_probe"]
    assert payload["latest_failure"]["failure_kind"] == "source_output_contract_missing"


def test_implement_v2_source_output_probe_candidate_reads_inspect_dir_entry_names(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-hard-runtime:full",
        provider="test",
        provider_call_id="inspect-source-dir",
        mew_tool_call_id="mew-inspect-source-dir",
        tool_name="inspect_dir",
        arguments={"path": "doomgeneric/doomgeneric"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": str(tmp_path / "doomgeneric" / "doomgeneric"),
                "entries": [
                    {"name": "LICENSE", "type": "file"},
                    {"name": "doomgeneric_img.c", "type": "file"},
                ],
            },
        ),
    )

    candidate = _source_output_contract_probe_candidate_from_trace(
        lane_input=lane_input,
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
    )

    assert candidate["path"] == "doomgeneric/doomgeneric/doomgeneric_img.c"
    assert candidate["tool_name"] == "inspect_dir"


def test_implement_v2_source_output_probe_candidate_prefers_concrete_glob_path_over_bare_symbol(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    glob_call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-hard-runtime:full",
        provider="test",
        provider_call_id="glob-source",
        mew_tool_call_id="mew-glob-source",
        tool_name="glob",
        arguments={"path": ".", "pattern": "doomgeneric/**/*"},
        turn_index=1,
    )
    shell_call = ToolCallEnvelope(
        lane_attempt_id=glob_call.lane_attempt_id,
        provider="test",
        provider_call_id="strings-probe",
        mew_tool_call_id="mew-strings-probe",
        tool_name="run_command",
        arguments={"command": "strings -a doomgeneric_mips | rg frame"},
        turn_index=1,
    )
    glob_result = ToolResultEnvelope(
        lane_attempt_id=glob_call.lane_attempt_id,
        provider_call_id=glob_call.provider_call_id,
        mew_tool_call_id=glob_call.mew_tool_call_id,
        tool_name=glob_call.tool_name,
        status="completed",
        content=({"matches": [str(tmp_path / "doomgeneric" / "doomgeneric" / "doomgeneric_img.c")]},),
    )
    shell_result = ToolResultEnvelope(
        lane_attempt_id=shell_call.lane_attempt_id,
        provider_call_id=shell_call.provider_call_id,
        mew_tool_call_id=shell_call.mew_tool_call_id,
        tool_name=shell_call.tool_name,
        status="completed",
        content=({"stdout": "frame output symbol doomgeneric_img.c\n", "exit_code": 0},),
    )

    candidate = _source_output_contract_probe_candidate_from_trace(
        lane_input=lane_input,
        prior_tool_calls=(glob_call, shell_call),
        prior_tool_results=(glob_result, shell_result),
    )

    assert candidate["path"] == "doomgeneric/doomgeneric/doomgeneric_img.c"
    assert candidate["tool_name"] == "glob"


def test_implement_v2_source_output_probe_does_not_invent_path_from_search_location_colon(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-hard-runtime:full",
        provider="test",
        provider_call_id="search-source",
        mew_tool_call_id="mew-search-source",
        tool_name="search_text",
        arguments={"path": "doomgeneric/doomgeneric", "pattern": "OUTPUT|frame"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "matches": [
                    "/app/doomgeneric/doomgeneric/Makefile.sdl:28:OUTPUT=doomgeneric_mips",
                    "/app/doomgeneric/doomgeneric/Makefile:14:SRC_DOOM = dummy.o am_map.o dstrings.o",
                    "/app/doomgeneric/doomgeneric/Makefile:39:OUTPUT=doomgeneric_mips",
                ],
            },
        ),
    )

    candidate = _source_output_contract_probe_candidate_from_trace(
        lane_input=lane_input,
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
    )

    assert candidate == {}


def test_implement_v2_prewrite_missing_probe_prefers_source_output_candidate_when_available(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-hard-runtime:full",
        provider="test",
        provider_call_id="probe-sources",
        mew_tool_call_id="mew-probe-sources",
        tool_name="glob",
        arguments={"path": ".", "pattern": "doomgeneric/**/*"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"matches": [str(tmp_path / "doomgeneric" / "doomgeneric" / "doomgeneric_img.c")]},),
    )

    missing_probe = _deep_runtime_prewrite_missing_probe(
        lane_input=lane_input,
        readiness={"missing_categories": ("source_output_contract", "runtime_binary_layout")},
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
    )

    assert missing_probe["failure_kind"] == "source_output_contract_missing"
    assert "read_file" in missing_probe["required_next_probe"]


def test_implement_v2_prewrite_generic_search_suggestions_use_regex(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )

    source_contract_probe = _deep_runtime_prewrite_missing_probe(
        lane_input=lane_input,
        readiness={"missing_categories": ("source_output_contract",)},
        prior_tool_calls=(),
        prior_tool_results=(),
    )
    host_interface_probe = _deep_runtime_prewrite_missing_probe(
        lane_input=lane_input,
        readiness={"missing_categories": ("host_interface_surface",)},
        prior_tool_calls=(),
        prior_tool_results=(),
    )

    for probe in (source_contract_probe, host_interface_probe):
        suggestion = probe["suggested_next_probe"]
        assert suggestion["tool"] == "search_text"
        assert suggestion["arguments"]["regex"] is True
        assert "|" in suggestion["arguments"]["query"]


def test_implement_v2_allows_hard_runtime_patch_after_more_probes_follow_blocked_write(tmp_path) -> None:
    (tmp_path / "doomgeneric_mips").write_bytes(b"\x7fELFfake")
    (tmp_path / "doomgeneric").mkdir()
    (tmp_path / "doomgeneric" / "i_video.c").write_text("void I_FinishUpdate(void) {}\n", encoding="utf-8")
    probe_command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "print('file readelf -s objdump -d ELF little endian main symbol "
                "syscall hook api open read write opcode instruction output frame "
                "fopen(\"/tmp/frame.bmp\", \"wb\")')"
            ),
        ]
    )
    outputs = [
        {
            "summary": "initial cheap probes",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-elf", "name": "run_command", "arguments": {"command": "file doomgeneric_mips", "cwd": "."}},
                {"id": "probe-src", "name": "search_text", "arguments": {"query": "I_FinishUpdate", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "premature runtime write",
            "tool_calls": [
                {
                    "id": "write-too-early",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "additional source/runtime probes after blocked write",
            "tool_calls": [
                {"id": "probe-src-read", "name": "read_file", "arguments": {"path": "doomgeneric/i_video.c"}},
                {"id": "probe-glob", "name": "glob", "arguments": {"pattern": "**/*.c"}},
                {"id": "probe-command", "name": "run_command", "arguments": {"command": probe_command, "cwd": "."}},
                {"id": "probe-runtime-search", "name": "search_text", "arguments": {"query": "doomgeneric", "path": "."}},
                {"id": "probe-tree", "name": "inspect_dir", "arguments": {"path": "doomgeneric"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "patch after enough probes",
            "tool_calls": [
                {
                    "id": "patch-vm",
                    "name": "apply_patch",
                    "arguments": {
                        "patch_lines": [
                            "*** Begin Patch",
                            "*** Add File: vm.js",
                            "+module.exports = {}",
                            "*** End Patch",
                        ],
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "stop after patch"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=4,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    premature_write = next(item for item in tool_results if item["provider_call_id"] == "write-too-early")
    final_patch = next(item for item in tool_results if item["provider_call_id"] == "patch-vm")
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert premature_write["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in premature_write["content"][0]["reason"]
    assert final_patch["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "module.exports = {}\n"
    assert readiness["probe_threshold"] == 8
    assert readiness["probe_count_before_first_write"] == 8
    assert readiness["prewrite_probe_missing_categories"] == ()
    assert readiness["first_write_tool"] == "apply_patch"
    assert readiness["first_write_provider_call_id"] == "patch-vm"


def test_implement_v2_blocks_hard_runtime_prewrite_even_without_active_work_todo(tmp_path) -> None:
    outputs = [
        {
            "summary": "write strict runtime immediately",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {}\n"},
                }
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before write"},
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    write_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert write_result["status"] == "invalid"
    assert "deep_runtime_prewrite_probe_budget_not_met" in write_result["content"][0]["reason"]
    assert "vm.js" in write_result["content"][0]["reason"]
    assert not (tmp_path / "vm.js").exists()


def test_implement_v2_observes_hard_runtime_shell_writer_without_prewrite_classifier(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "open('vm.js','w').write('module.exports = {}\\n')"])
    outputs = [
        {
            "summary": "shell writer too early with self-declared verifier contract",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "execution_contract": {"role": "runtime", "proof_role": "verifier"},
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before shell writer"},
        },
        {"summary": "stop after observed shell writer", "finish": {"outcome": "blocked", "summary": "observed"}},
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-hard-runtime",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
            },
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    shell_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert shell_result["status"] in {"completed", "failed"}
    assert shell_result["content"][0]["tool_route"] == "process_runner"
    assert shell_result["content"][0]["process_source_observations"][0]["changed_count"] == 1
    assert readiness["first_write_attempt_tool"] == "run_command"
    assert readiness["probe_count_before_first_write"] == 0
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_shell_writer_source_like_path_detection_is_artifact_safe() -> None:
    assert _shell_command_may_mutate_source_tree("cat > package.json <<'EOF'\n{}\nEOF")
    assert _shell_command_may_mutate_source_tree("cat > Makefile <<'EOF'\nall:\n\ttrue\nEOF")
    assert _shell_command_may_mutate_source_tree("python -c \"open('vm.js','w').write('x')\"")
    assert _shell_command_may_mutate_source_tree("python -c \"from pathlib import Path; Path('vm.js').write_text('x')\"")
    assert not _shell_command_may_mutate_source_tree("python -c \"open('/tmp/frame.txt','w').write('x')\"")
    assert not _shell_command_may_mutate_source_tree(
        "python -c \"from pathlib import Path; Path('/tmp/frame.txt').write_text('x')\""
    )
    assert not _shell_command_may_mutate_source_tree(
        "python -c \"from pathlib import Path; Path('/tmp/frame.txt').write_text('vm.js')\""
    )
    assert not _shell_command_may_mutate_source_tree("printf frame > frame.txt && test -s frame.txt")


def test_implement_v2_surfaces_patch_tools_from_hard_runtime_prompt_before_probe_budget(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )

    specs = _model_visible_tool_specs_for_turn(lane_input, prior_tool_calls=(), prior_tool_results=())
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        tool_specs=specs,
        prewrite_probe_readiness=_deep_runtime_prewrite_probe_readiness(
            prior_tool_calls=(),
            prior_tool_results=(),
            probe_threshold=_first_write_probe_threshold(lane_input),
            source_mutation_roots=(),
        ),
        history=(),
    )
    response_contract = prompt.split("response_contract_json:\n", 1)[1].split("\nhistory_json:", 1)[0]

    spec_names = {spec.name for spec in specs}
    assert {"edit_file", "apply_patch"}.issubset(spec_names)
    assert "write_file" not in spec_names
    assert "apply_patch or edit_file" in prompt
    assert "edit_file/apply_patch" not in prompt
    assert "write_file/edit_file/apply_patch" not in prompt
    assert "write tools are temporarily hidden for this turn" not in response_contract
    assert "write tools are available" not in response_contract
    assert "first source mutation is execution-gated" not in response_contract
    assert "source/output contract" not in response_contract
    assert "write_file" not in response_contract
    assert "edit_file" in response_contract
    assert "apply_patch" in response_contract
    response_shape = json.loads(response_contract)
    assert "bulk_transport" not in response_shape
    assert "patch_lines" not in response_contract
    assert "patch_lines" in prompt
    assert "finish" not in response_shape["tool_calls"][0]["name"]
    assert "run_command" in response_contract


def test_implement_v2_tool_surface_keeps_write_file_for_generic_artifact_task(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-generic-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "goal": "Create a small JSON report artifact at /tmp/output.json from the provided task summary."
        },
        lane_config={"mode": "full"},
    )

    specs = _model_visible_tool_specs_for_turn(
        lane_input,
        active_work_todo_state={},
        prior_tool_calls=(),
        prior_tool_results=(),
    )

    assert {"write_file", "edit_file", "apply_patch"} <= {spec.name for spec in specs}


def test_implement_v2_keeps_patch_tools_visible_after_many_shallow_source_probes(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=tuple(
            {
                "provider_call_id": f"probe-{index}",
                "tool_name": "read_file",
                "arguments": {"path": f"src/{index}.c"},
            }
            for index in range(8)
        ),
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=({"path": call.arguments["path"], "content": "int ordinary_source_probe(void) { return 0; }"},),
        )
        for call in calls
    )

    specs = _model_visible_tool_specs_for_turn(
        lane_input,
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
    )
    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["vm.js"]}},
        tool_calls=tuple(calls),
        tool_results=results,
        probe_threshold=8,
        requires_deep_runtime_coverage=True,
    )

    spec_names = {spec.name for spec in specs}
    assert {"edit_file", "apply_patch"}.issubset(spec_names)
    assert "write_file" not in spec_names
    assert readiness["probe_count_before_first_write"] == 8
    assert readiness["first_write_due"] is False
    assert "runtime_binary_layout" in readiness["prewrite_probe_missing_categories"]
    assert "implementation_feature_surface" in readiness["prewrite_probe_missing_categories"]


def test_implement_v2_prewrite_gate_reports_coverage_not_budget_when_count_met(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
    )
    probe_calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-coverage",
        turn_index=1,
        calls=tuple(
            {
                "provider_call_id": f"probe-{index}",
                "tool_name": "run_command",
                "arguments": {
                    "command": f"{shlex.quote(sys.executable)} -c \"open('src/{index}.c').read()\"",
                    "cwd": ".",
                },
            }
            for index in range(8)
        ),
    )
    probe_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=(
                {
                    "command": call.arguments["command"],
                    "text": (
                        'ELF machine ABI entry main symbol host hook api open read write '
                        'fopen("/tmp/frame.bmp", "wb")'
                    ),
                    "stdout": (
                        'ELF machine ABI entry main symbol host hook api open read write '
                        'fopen("/tmp/frame.bmp", "wb")'
                    ),
                    "exit_code": 0,
                },
            ),
        )
        for call in probe_calls
    )
    write_call = ToolCallEnvelope(
        lane_attempt_id="lane-v2-coverage",
        provider="test",
        provider_call_id="write-runtime",
        mew_tool_call_id="mew-write-runtime",
        tool_name="write_file",
        arguments={"path": "vm.js", "content": "module.exports = {}\n"},
        turn_index=2,
    )

    result = _deep_runtime_prewrite_probe_gate_result(
        write_call,
        lane_input=lane_input,
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        prior_tool_calls=tuple(probe_calls),
        prior_tool_results=probe_results,
        probe_threshold=8,
    )

    assert result is not None
    reason = result.content[0]["reason"]
    assert "deep_runtime_prewrite_probe_coverage_not_met" in reason
    assert "observed 8/8" in reason
    assert "deep_runtime_prewrite_probe_budget_not_met" not in reason
    assert "Required next probe" in reason
    assert "implementation-feature" in result.content[0]["failure_subclass"].replace("_", "-")


def test_implement_v2_counts_shell_source_read_probe_toward_deep_runtime_categories() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-source-shell",
        mew_tool_call_id="mew-probe-source-shell",
        tool_name="run_command",
        arguments={"command": "sed -n '1,240p' src/runtime_backend.c", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "command": call.arguments["command"],
                "stdout": (
                    "int main(void) { host_api_open(); host_api_write(); }\n"
                    "void draw_frame(void) { /* output frame artifact */ }\n"
                    "switch (opcode) { case 1: instruction(); }\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]
    assert "entry_symbol_surface" in readiness["covered_categories"]
    assert "host_interface_surface" in readiness["covered_categories"]
    assert "implementation_feature_surface" in readiness["covered_categories"]
    assert "runtime_binary_layout" in readiness["missing_categories"]


def test_implement_v2_does_not_count_syscall_only_disassembly_as_feature_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-syscall-only-disassembly",
        mew_tool_call_id="mew-probe-syscall-only-disassembly",
        tool_name="run_command",
        arguments={"cmd": "llvm-objdump -d app.bin | rg -n -C 4 syscall", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "cmd": call.arguments["cmd"],
                "stdout": (
                    "120:  400510:\t0000000c \tsyscall\n"
                    "121:  400514:\t03e00008 \tjr $ra\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "host_interface_surface" in readiness["covered_categories"]
    assert "implementation_feature_surface" not in readiness["covered_categories"]
    assert "implementation_feature_surface" in readiness["missing_categories"]


def test_implement_v2_counts_broad_disassembly_inventory_as_feature_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-disassembly-feature-inventory",
        mew_tool_call_id="mew-probe-disassembly-feature-inventory",
        tool_name="run_command",
        arguments={
            "cmd": "llvm-objdump -d app.bin | rg -n 'clz|seb|seh|ext|ins|wsbh|lwl|lwr|sdc1|ldc1'",
            "cwd": ".",
        },
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "cmd": call.arguments["cmd"],
                "stdout": (
                    "44:  4010a0:\t7c0420a0 \tseb $4, $4\n"
                    "87:  401140:\t88050000 \tlwl $5, 0($0)\n"
                    "91:  401154:\tf7a60010 \tsdc1 $f6, 16($29)\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "implementation_feature_surface" in readiness["covered_categories"]


def test_implement_v2_counts_common_broad_disassembly_forms_as_feature_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=(
            {
                "provider_call_id": "probe-native-disassembly",
                "tool_name": "run_command",
                "arguments": {"cmd": "objdump -dr app.bin | head -200", "cwd": "."},
            },
            {
                "provider_call_id": "probe-wasm-disassembly",
                "tool_name": "run_command",
                "arguments": {"cmd": "wasm-objdump -d module.wasm | head -200", "cwd": "."},
            },
        ),
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=({"cmd": call.arguments["cmd"], "stdout": "", "exit_code": 0},),
        )
        for call in calls
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 2
    assert readiness["category_provider_call_ids"]["implementation_feature_surface"] == [
        "probe-native-disassembly",
        "probe-wasm-disassembly",
    ]


def test_implement_v2_does_not_count_symbol_or_classpath_probes_as_disassembly_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id=lane_attempt_id,
        turn_index=1,
        calls=(
            {
                "provider_call_id": "probe-dynamic-symbols",
                "tool_name": "run_command",
                "arguments": {"cmd": "objdump --dynamic-syms app.bin | head -80", "cwd": "."},
            },
            {
                "provider_call_id": "probe-demangled-symbols",
                "tool_name": "run_command",
                "arguments": {"cmd": "objdump --demangle --syms app.bin | head -80", "cwd": "."},
            },
            {
                "provider_call_id": "probe-javap-classpath",
                "tool_name": "run_command",
                "arguments": {"cmd": "javap -classpath build/classes com.example.Main", "cwd": "."},
            },
        ),
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=({"cmd": call.arguments["cmd"], "stdout": "", "exit_code": 0},),
        )
        for call in calls
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 3
    assert "implementation_feature_surface" not in readiness["covered_categories"]
    assert "entry_symbol_surface" in readiness["covered_categories"]


def test_implement_v2_does_not_count_readelf_hex_as_feature_surface_without_feature_output() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-readelf-hex",
        mew_tool_call_id="mew-probe-readelf-hex",
        tool_name="run_command",
        arguments={"cmd": "readelf -x .text app.bin | head -80", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "cmd": call.arguments["cmd"],
                "stdout": (
                    "Hex dump of section '.text':\n"
                    "0x00001000 01020304 05060708 090a0b0c 0d0e0f10\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "runtime_binary_layout" in readiness["covered_categories"]
    assert "implementation_feature_surface" not in readiness["covered_categories"]


def test_implement_v2_read_file_dispatch_source_counts_as_feature_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-dispatch-source",
        mew_tool_call_id="mew-read-dispatch-source",
        tool_name="read_file",
        arguments={"path": "src/interpreter.py"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/src/interpreter.py",
                "text": (
                    "def execute(bytecode):\n"
                    "    instruction = decode(bytecode)\n"
                    "    return dispatch(instruction)\n"
                ),
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "implementation_feature_surface" in readiness["covered_categories"]


def test_implement_v2_cmd_alias_source_read_counts_for_deep_runtime_categories() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-source-shell-cmd-alias",
        mew_tool_call_id="mew-probe-source-shell-cmd-alias",
        tool_name="run_command",
        arguments={"cmd": "sed -n '1,240p' src/runtime_backend.c", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "cmd": call.arguments["cmd"],
                "stdout": (
                    "int main(void) { host api open write; }\n"
                    "switch (opcode) { case 1: instruction(); }\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "entry_symbol_surface" in readiness["covered_categories"]
    assert "host_interface_surface" in readiness["covered_categories"]
    assert "implementation_feature_surface" in readiness["covered_categories"]


def test_implement_v2_does_not_treat_broad_find_as_source_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-find",
        mew_tool_call_id="mew-probe-find",
        tool_name="run_command",
        arguments={"command": "find . -maxdepth 3 -type f", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "command": call.arguments["command"],
                "stdout": "./src/runtime_backend.c\n./README.md\n",
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_counts_shell_source_output_path_toward_source_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-rg-src",
        mew_tool_call_id="mew-probe-rg-src",
        tool_name="run_command",
        arguments={"command": "rg -n 'draw_frame|output' src", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "command": call.arguments["command"],
                "stdout": (
                    'src/runtime_backend.c:42:void draw_frame(void) { FILE *fp = fopen("/tmp/frame.bmp", "wb"); '
                    "fwrite(framebuffer, 1, len, fp); }\n"
                ),
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" in readiness["covered_categories"]


def test_implement_v2_counts_build_output_declaration_toward_source_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-makefile",
        mew_tool_call_id="mew-read-makefile",
        tool_name="read_file",
        arguments={"path": "doomgeneric/doomgeneric/Makefile"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/doomgeneric/doomgeneric/Makefile",
                "text": "SRC_DOOM = dummy.o am_map.o dstrings.o\nOUTPUT=doomgeneric_mips\n",
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "source_output_contract" in readiness["covered_categories"]


def test_implement_v2_read_file_preserves_medium_source_body_for_source_output_contract(tmp_path) -> None:
    source = tmp_path / "doomgeneric_img.c"
    prefix = "/* BMP header and runtime scaffolding */\n" + ("int header_padding = 0;\n" * 320)
    source.write_text(
        prefix
        + "\nvoid DG_DrawFrame(void) {\n"
        + '    FILE *fp = fopen("/tmp/frame.bmp", "wb");\n'
        + "    fwrite(framebuffer, 1, frame_bytes, fp);\n"
        + "}\n",
        encoding="utf-8",
    )
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        provider="test",
        provider_call_id="read-img-source",
        mew_tool_call_id="mew-read-img-source",
        tool_name="read_file",
        arguments={"path": str(source)},
        turn_index=1,
    )

    result = read_runtime.execute_read_only_tool_call(
        call,
        workspace=tmp_path,
        allowed_roots=(str(tmp_path),),
        result_max_chars=12_000,
    )
    payload = result.content[0]
    assert isinstance(payload, dict)
    assert payload.get("text")
    assert len(str(payload.get("text") or "")) > 7_000
    assert "/tmp/frame.bmp" in str(payload.get("text") or "")
    assert payload.get("mew_content_truncated") is not True
    assert str(payload.get("summary") or "").count("\n") == 0
    assert payload.get("summary_body_omitted") is True

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" in readiness["covered_categories"]


def test_implement_v2_counts_read_source_output_surface_without_artifact_path() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-output-surface",
        mew_tool_call_id="mew-read-output-surface",
        tool_name="read_file",
        arguments={"path": "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c",
                "text": (
                    "void DG_DrawFrame(void) {\n"
                    "  SDL_UpdateTexture(texture, NULL, DG_ScreenBuffer, DOOMGENERIC_RESX * sizeof(uint32_t));\n"
                    "  SDL_RenderPresent(renderer);\n"
                    "}\n"
                ),
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )
    source_contract = _source_output_contract_from_tool_results((result,), {})

    assert readiness["probe_count"] == 1
    assert "source_output_contract" in readiness["covered_categories"]
    assert source_contract == {}


def test_implement_v2_does_not_count_doc_output_surface_as_prewrite_coverage() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-readme",
        mew_tool_call_id="mew-read-readme",
        tool_name="read_file",
        arguments={"path": "/app/README.md"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/README.md",
                "text": "The demo calls renderFrame(buffer) to show a screen image in the browser.",
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_count_generic_syscall_write_as_source_output_surface() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-syscalls",
        mew_tool_call_id="mew-read-syscalls",
        tool_name="read_file",
        arguments={"path": "/app/src/syscalls.c"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/src/syscalls.c",
                "text": "int sys_write(int fd, const char *buffer, int len) { return write(fd, buffer, len); }\n",
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_reprobe_source_output_candidate_after_same_basename_read(tmp_path) -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace="/app",
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Implement a runtime that saves rendered frames."},
    )
    search_call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="search-output-surface",
        mew_tool_call_id="mew-search-output-surface",
        tool_name="search_text",
        arguments={"path": "/app/doomgeneric", "query": "DG_DrawFrame|SDL|frame"},
        turn_index=1,
    )
    search_result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=search_call.provider_call_id,
        mew_tool_call_id=search_call.mew_tool_call_id,
        tool_name=search_call.tool_name,
        status="completed",
        content=(
            {
                "matches": [
                    "doomgeneric_sdl.c:117:void DG_DrawFrame(void) {",
                    "doomgeneric_sdl.c:122:  SDL_RenderPresent(renderer);",
                ],
                "summary": "Searched /app/doomgeneric; matches=2",
            },
        ),
    )
    read_call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-output-surface",
        mew_tool_call_id="mew-read-output-surface",
        tool_name="read_file",
        arguments={"path": "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c"},
        turn_index=2,
    )
    read_result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=read_call.provider_call_id,
        mew_tool_call_id=read_call.mew_tool_call_id,
        tool_name=read_call.tool_name,
        status="completed",
        content=(
            {
                "path": "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c",
                "text": "void DG_DrawFrame(void) { SDL_RenderPresent(renderer); }\n",
            },
        ),
    )

    candidate = _source_output_contract_probe_candidate_from_trace(
        lane_input=lane_input,
        prior_tool_calls=(search_call, read_call),
        prior_tool_results=(search_result, read_result),
    )

    assert candidate == {}


def test_implement_v2_keeps_longer_source_output_candidate_after_shorter_basename_read() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace="/app",
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={"goal": "Implement a runtime that saves rendered frames."},
    )
    read_call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="read-short",
        mew_tool_call_id="mew-read-short",
        tool_name="read_file",
        arguments={"path": "doomgeneric_sdl.c"},
        turn_index=1,
    )
    read_result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=read_call.provider_call_id,
        mew_tool_call_id=read_call.mew_tool_call_id,
        tool_name=read_call.tool_name,
        status="completed",
        content=({"path": "doomgeneric_sdl.c", "text": "int helper(void) { return 0; }\n"},),
    )
    search_call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="search-output-surface",
        mew_tool_call_id="mew-search-output-surface",
        tool_name="search_text",
        arguments={"path": "/app/doomgeneric", "query": "DG_DrawFrame|SDL|frame"},
        turn_index=2,
    )
    search_result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=search_call.provider_call_id,
        mew_tool_call_id=search_call.mew_tool_call_id,
        tool_name=search_call.tool_name,
        status="completed",
        content=(
            {
                "matches": [
                    "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c:117:void DG_DrawFrame(void) {",
                    "/app/doomgeneric/doomgeneric/doomgeneric_sdl.c:122:  SDL_RenderPresent(renderer);",
                ],
                "summary": "Searched /app/doomgeneric; matches=2",
            },
        ),
    )

    candidate = _source_output_contract_probe_candidate_from_trace(
        lane_input=lane_input,
        prior_tool_calls=(read_call, search_call),
        prior_tool_results=(read_result, search_result),
    )

    assert candidate["path"] == "doomgeneric/doomgeneric/doomgeneric_sdl.c"


def test_implement_v2_clipped_search_preserves_source_output_contract_matches(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    for index in range(30):
        (source_dir / f"frame_output_{index:02d}.c").write_text(
            "\n".join(
                [
                    "void render_frame(void) {",
                    '    FILE *fp = fopen("/tmp/frame.bmp", "wb");',
                    "    fwrite(framebuffer, 1, frame_bytes, fp);",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    call = ToolCallEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        provider="test",
        provider_call_id="probe-output-contract",
        mew_tool_call_id="mew-probe-output-contract",
        tool_name="search_text",
        arguments={"path": ".", "pattern": "fopen|fwrite|frame"},
        turn_index=1,
    )

    result = read_runtime.execute_read_only_tool_call(
        call,
        workspace=tmp_path,
        allowed_roots=(str(tmp_path),),
        result_max_chars=1_200,
    )
    payload = result.content[0]
    assert isinstance(payload, dict)
    assert payload.get("mew_content_truncated") is True
    assert payload.get("matches")
    assert int(payload.get("matches_original_count") or 0) > len(payload.get("matches") or [])
    assert any("/tmp/frame.bmp" in str(match) for match in payload.get("matches") or [])

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" in readiness["covered_categories"]


def test_implement_v2_does_not_count_broad_source_search_as_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    calls = (
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="probe-dir-app",
            mew_tool_call_id="mew-probe-dir-app",
            tool_name="inspect_dir",
            arguments={"path": "/app"},
            turn_index=1,
        ),
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="probe-doom-source-files",
            mew_tool_call_id="mew-probe-doom-source-files",
            tool_name="glob",
            arguments={"pattern": "/app/doomgeneric/**/*"},
            turn_index=1,
        ),
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="probe-syscall-source",
            mew_tool_call_id="mew-probe-syscall-source",
            tool_name="search_text",
            arguments={
                "path": "/app/doomgeneric",
                "pattern": "open|read|write|lseek|mmap|munmap|ioctl|gettimeofday|clock_gettime|fopen|fwrite",
            },
            turn_index=1,
        ),
    )
    results = (
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="probe-dir-app",
            mew_tool_call_id="mew-probe-dir-app",
            tool_name="inspect_dir",
            status="completed",
            content=({"path": "/app", "entries": ["doomgeneric", "README.md"]},),
        ),
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="probe-doom-source-files",
            mew_tool_call_id="mew-probe-doom-source-files",
            tool_name="glob",
            status="completed",
            content=({"matches": ["/app/doomgeneric/LICENSE", "/app/doomgeneric/doomgeneric.c"]},),
        ),
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="probe-syscall-source",
            mew_tool_call_id="mew-probe-syscall-source",
            tool_name="search_text",
            status="completed",
            content=(
                {
                    "matches": [
                        "/app/doomgeneric/LICENSE:100: You may copy and distribute verbatim copies.",
                        "/app/doomgeneric/LICENSE:106: This license applies to source output distributions.",
                    ],
                    "summary": "Searched /app/doomgeneric; matches=50 (truncated)",
                },
            ),
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=calls,
        prior_tool_results=results,
        probe_threshold=3,
    )

    assert readiness["probe_count"] == 3
    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_count_search_location_path_as_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-fixture-output",
        mew_tool_call_id="mew-probe-fixture-output",
        tool_name="search_text",
        arguments={"path": "/app", "pattern": "output artifact"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "matches": [
                    "/app/tests/fixtures/output.txt:1: expected output artifact fixture",
                ],
                "summary": "Searched /app; matches=1",
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_count_search_snippet_path_field_as_output_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-fixture-snippet",
        mew_tool_call_id="mew-probe-fixture-snippet",
        tool_name="search_text",
        arguments={"path": "/app", "pattern": "output artifact"},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "snippets": [
                    {
                        "path": "/app/tests/fixtures/output.txt",
                        "line": "expected output artifact fixture",
                    }
                ],
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_count_source_like_search_pattern_as_path_operand() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-rg-readme",
        mew_tool_call_id="mew-probe-rg-readme",
        tool_name="run_command",
        arguments={"command": "rg -n src README.md", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "command": call.arguments["command"],
                "stdout": "README.md:1:src is mentioned here\n",
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_count_tmp_source_directory_probe_as_source_contract() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    call = ToolCallEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider="test",
        provider_call_id="probe-tmp-src",
        mew_tool_call_id="mew-probe-tmp-src",
        tool_name="run_command",
        arguments={"command": "cat /tmp/src/runtime_backend.c", "cwd": "."},
        turn_index=1,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=(
            {
                "command": call.arguments["command"],
                "stdout": "void draw_frame(void) { /* output frame artifact */ }\n",
                "exit_code": 0,
            },
        ),
    )

    readiness = _deep_runtime_prewrite_probe_readiness(
        prior_tool_calls=(call,),
        prior_tool_results=(result,),
        probe_threshold=1,
    )

    assert readiness["probe_count"] == 1
    assert "source_output_contract" not in readiness["covered_categories"]
    assert "source_output_contract" in readiness["missing_categories"]


def test_implement_v2_does_not_label_exec_mode_as_prewrite_hidden(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "exec"},
    )
    specs = _model_visible_tool_specs_for_turn(lane_input, prior_tool_calls=(), prior_tool_results=())
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        tool_specs=specs,
        history=(),
    )
    response_contract = prompt.split("response_contract_json:\n", 1)[1].split("\nhistory_json:", 1)[0]

    assert {spec.name for spec in specs}.isdisjoint({"write_file", "edit_file", "apply_patch"})
    assert "tool_surface_note" not in response_contract


def test_implement_v2_reveals_patch_tools_after_hard_runtime_probe_budget(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )
    probe_calls = (
        {"provider_call_id": "probe-src", "tool_name": "read_file", "arguments": {"path": "src/runtime.c"}},
        {
            "provider_call_id": "probe-binary",
            "tool_name": "run_command",
            "arguments": {"command": "file app.bin && readelf -h app.bin", "cwd": "."},
        },
        {
            "provider_call_id": "probe-symbols",
            "tool_name": "run_command",
            "arguments": {"command": "readelf -s app.bin | grep main", "cwd": "."},
        },
        {
            "provider_call_id": "probe-host",
            "tool_name": "search_text",
            "arguments": {"query": "syscall hook api open read write", "path": "."},
        },
        {
            "provider_call_id": "probe-features",
            "tool_name": "run_command",
            "arguments": {"command": "objdump -d app.bin | grep opcode", "cwd": "."},
        },
        {"provider_call_id": "probe-output", "tool_name": "search_text", "arguments": {"query": "output frame artifact", "path": "."}},
        {"provider_call_id": "probe-api", "tool_name": "search_text", "arguments": {"query": "entry callback interface", "path": "."}},
        {"provider_call_id": "probe-glob", "tool_name": "glob", "arguments": {"pattern": "**/*.[ch]"}},
    )
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=probe_calls,
    )
    results = tuple(
        ToolResultEnvelope(
            lane_attempt_id=call.lane_attempt_id,
            provider_call_id=call.provider_call_id,
            mew_tool_call_id=call.mew_tool_call_id,
            tool_name=call.tool_name,
            status="completed",
            content=(
                (
                    {
                        "matches": [
                            'src/runtime.c:42:void draw_frame(void) { FILE *fp = fopen("/tmp/frame.bmp", "wb"); }'
                        ],
                    }
                    if call.provider_call_id == "probe-output"
                    else {"content": json.dumps(call.arguments)}
                ),
            ),
        )
        for call in calls
    )

    specs = _model_visible_tool_specs_for_turn(
        lane_input,
        prior_tool_calls=tuple(calls),
        prior_tool_results=results,
    )

    spec_names = {spec.name for spec in specs}
    assert {"edit_file", "apply_patch"} <= spec_names
    assert "write_file" not in spec_names


def test_implement_v2_allows_normal_task_write_without_deep_prewrite_probe_budget(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "write normal patch immediately",
            "tool_calls": [
                {
                    "id": "write-sample",
                    "name": "write_file",
                    "arguments": {"path": "sample.py", "content": "print('done')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write"},
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-normal",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"goal": "Patch a Python file."},
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    write_result = next(item for item in tool_results if item["provider_call_id"] == "write-sample")

    assert write_result["status"] == "completed"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('done')\n"


def test_implement_v2_counts_shell_source_mutation_as_first_write(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('sample.py').write_text('print(\"done\")\\n', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write a large generated file through a bounded command writer",
            "tool_calls": [
                {
                    "id": "shell-write-sample",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "timeout": 10},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after first source mutation"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert target.read_text(encoding="utf-8") == 'print("done")\n'
    assert readiness["status"] == "written"
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "run_command"
    assert readiness["first_write_tool"] == "run_command"
    assert readiness["first_write_latency_turns"] == 1
    assert readiness["write_attempt_count"] == 1
    assert result.metrics["write_evidence_count"] == 0
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    shell_write = next(item for item in tool_results if item["provider_call_id"] == "shell-write-sample")
    assert any(effect["kind"] == "process_source_observation" for effect in shell_write["side_effects"])
    assert not any(effect["kind"] == "source_tree_mutation" for effect in shell_write["side_effects"])


def test_implement_v2_counts_polled_shell_source_mutation_as_first_write() -> None:
    lane_attempt_id = "implement_v2:ws-1:task-1:full"
    active_work_todo = {
        "id": "todo-1",
        "status": "drafting",
        "source": {"target_paths": ["generated.js"], "plan_item": "Generate runtime"},
    }
    calls = (
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="call-start-writer",
            mew_tool_call_id="mew-call-start-writer",
            tool_name="run_command",
            arguments={"command": "python - <<'PY'\nPY", "foreground_budget_seconds": 0.01},
            turn_index=2,
        ),
        ToolCallEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider="test",
            provider_call_id="call-poll-writer",
            mew_tool_call_id="mew-call-poll-writer",
            tool_name="poll_command",
            arguments={"command_run_id": "command-1", "wait_seconds": 1},
            turn_index=3,
        ),
    )
    results = (
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="call-start-writer",
            mew_tool_call_id="mew-call-start-writer",
            tool_name="run_command",
            status="yielded",
            side_effects=(
                {
                    "kind": "command_run",
                    "record": {"command_run_id": "command-1", "status": "running"},
                },
            ),
        ),
        ToolResultEnvelope(
            lane_attempt_id=lane_attempt_id,
            provider_call_id="call-poll-writer",
            mew_tool_call_id="mew-call-poll-writer",
            tool_name="poll_command",
            status="completed",
            side_effects=(
                {
                    "kind": "source_tree_mutation",
                    "record": {
                        "command_run_id": "command-1",
                        "provider_call_id": "call-start-writer",
                        "changed_count": 1,
                        "changes": [{"path": "/workspace/generated.js", "change": "added"}],
                    },
                },
            ),
        ),
    )

    readiness = _first_write_readiness_from_trace(
        active_work_todo,
        tool_calls=calls,
        tool_results=results,
        probe_threshold=1,
    )

    assert readiness["status"] == "written"
    assert readiness["first_write_due"] is False
    assert readiness["first_write_attempt_tool"] == "poll_command"
    assert readiness["first_write_tool"] == "poll_command"
    assert readiness["first_write_attempt_provider_call_id"] == "call-poll-writer"
    assert readiness["first_write_provider_call_id"] == "call-poll-writer"
    assert readiness["write_attempt_count"] == 1


def test_implement_v2_does_not_emit_first_write_due_without_active_work_todo(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes without active todo",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert "active_work_todo" not in result.updated_lane_state
    assert result.metrics["first_write_due"] is False
    assert result.metrics["first_write_probe_count"] is None


def test_implement_v2_failed_write_attempt_does_not_clear_first_write_due(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt a bad edit",
            "tool_calls": [
                {
                    "id": "bad-edit",
                    "name": "edit_file",
                    "arguments": {"path": "sample.py", "old": "missing\n", "new": "print('done')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "bad edit failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert target.read_text(encoding="utf-8") == "print('hello')\n"
    assert readiness["status"] == "due"
    assert readiness["first_write_due"] is True
    assert readiness["first_write_attempt_turn"] == 2
    assert readiness["first_write_attempt_latency_turns"] == 1
    assert "first_source_mutation_turn" not in readiness
    assert "first_write_latency_turns" not in readiness


def test_implement_v2_active_work_todo_records_generated_file_write_repair(tmp_path) -> None:
    target = tmp_path / "vm.js"
    outputs = [
        {
            "summary": "write generated runtime",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){return 0}\n"},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function sys(n){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "edit failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert target.read_text(encoding="utf-8") == "function sys(){return 0}\n"
    assert repair["status"] == "blocked"
    assert repair["failure_kind"] == "stale_exact_edit"
    assert repair["path"] == "vm.js"
    assert repair["path_previously_mutated_this_attempt"] is True
    assert "stale-edit" in repair["recent_failed_write_provider_call_ids"]
    assert "write_file overwrite" in repair["required_next_action"]
    assert "do not run verifier again until a write succeeds" in repair["required_next_action"]


def test_implement_v2_write_repair_lock_blocks_repeated_target_reads_and_verifiers(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "second read and verifier are blocked until write repair",
            "tool_calls": [
                {"id": "read-again", "name": "read_file", "arguments": {"path": "vm.js"}},
                {"id": "verify-too-soon", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked by repair lock"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    read_current = next(item for item in tool_results if item["provider_call_id"] == "read-current")
    read_again = next(item for item in tool_results if item["provider_call_id"] == "read-again")
    verify_too_soon = next(item for item in tool_results if item["provider_call_id"] == "verify-too-soon")
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert read_current["status"] == "completed"
    assert read_again["status"] == "invalid"
    assert "write_repair_lock_active" in read_again["content"][0]["reason"]
    assert verify_too_soon["status"] == "invalid"
    assert "blocked_by_write_repair_lock" in verify_too_soon["content"][0]["reason"]
    assert repair["failure_kind"] == "stale_exact_edit"


def test_implement_v2_source_patch_shell_surface_is_observed_without_write_repair_lock(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    shell_patch = (
        "node - <<'NODE'\n"
        "const fs = require('fs');\n"
        "const p = 'vm.js';\n"
        "let s = fs.readFileSync(p, 'utf8');\n"
        "fs.writeFileSync(p, s.replace('old', 'new'));\n"
        "NODE\n"
    )
    outputs = [
        {
            "summary": "attempt shell source patch",
            "tool_calls": [
                {
                    "id": "shell-patch",
                    "name": "run_command",
                    "arguments": {
                        "command": shell_patch,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    shell_result = next(item for item in tool_results if item["provider_call_id"] == "shell-patch")

    assert shell_result["status"] == "completed"
    assert shell_result["content"][0]["tool_route"] == "process_runner"
    assert shell_result["content"][0]["process_source_observations"][0]["changed_count"] == 1
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_write_repair_lock_allows_same_turn_write_then_verifier(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair write and verify",
            "tool_calls": [
                {
                    "id": "overwrite-current",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){let n=0;return n}\n"},
                },
                {"id": "verify-after-write", "name": "run_tests", "arguments": {"command": "test -f vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    overwrite = next(item for item in tool_results if item["provider_call_id"] == "overwrite-current")
    verify = next(item for item in tool_results if item["provider_call_id"] == "verify-after-write")

    assert overwrite["status"] == "completed"
    assert verify["status"] == "completed"
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "function sys(){let n=0;return n}\n"


def test_implement_v2_unreadable_source_write_projects_repair_guidance(tmp_path) -> None:
    long_line = "const generated = '" + ("x" * 5000) + "';\n"
    prompts: list[str] = []
    outputs = [
        {
            "summary": "write generated source as one line",
            "tool_calls": [
                {
                    "id": "write-one-line",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": long_line, "create": True},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "try verifier too early",
            "tool_calls": [
                {"id": "verify-too-early", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked by repair lock"},
        },
    ]

    def fake_model(_backend, _auth, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement generated runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    first_write = next(item for item in tool_results if item["provider_call_id"] == "write-one-line")
    verifier = next(item for item in tool_results if item["provider_call_id"] == "verify-too-early")
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert first_write["status"] == "failed"
    assert first_write["content"][0]["failure_class"] == "source_mutation_unreadable_long_line"
    assert verifier["status"] == "invalid"
    assert "write_repair_lock_active" in verifier["content"][0]["reason"]
    assert "readable multi-line code" in verifier["content"][0]["reason"]
    assert repair["failure_kind"] == "source_mutation_unreadable_long_line"
    assert repair["preferred_tool"] == "write_file"
    assert "readable multi-line code" in repair["required_next_action"]
    assert "source_mutation_unreadable_long_line" in prompts[1]
    assert "readable multi-line code" in prompts[1]
    assert not (tmp_path / "vm.js").exists()


def test_implement_v2_unreadable_apply_patch_failure_preserves_target_path_for_lock(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old');\n", encoding="utf-8")
    long_line = "const generated = '" + ("x" * 5000) + "';\n"
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        "-console.log('old');\n"
        f"+{long_line}"
        "*** End Patch\n"
    )
    outputs = [
        {
            "summary": "patch source as one line",
            "tool_calls": [{"id": "patch-one-line", "name": "apply_patch", "arguments": {"patch": patch}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "try verifier too early",
            "tool_calls": [
                {"id": "verify-too-early", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked by repair lock"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Patch generated runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    patch_result = next(item for item in tool_results if item["provider_call_id"] == "patch-one-line")
    verifier = next(item for item in tool_results if item["provider_call_id"] == "verify-too-early")
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert patch_result["status"] == "failed"
    assert repair["path"].endswith("/vm.js")
    assert repair["preferred_tool"] == "apply_patch"
    assert verifier["status"] == "invalid"
    assert "source_mutation_unreadable_long_line repair is pending for" in verifier["content"][0]["reason"]
    assert "vm.js" in verifier["content"][0]["reason"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('old');\n"


def test_implement_v2_unreadable_write_repair_survives_skipped_same_turn_write(tmp_path) -> None:
    long_line = "const generated = '" + ("x" * 5000) + "';\n"
    outputs = [
        {
            "summary": "write bad source and another write in same turn",
            "tool_calls": [
                {
                    "id": "write-one-line",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": long_line, "create": True},
                },
                {
                    "id": "write-other",
                    "name": "write_file",
                    "arguments": {"path": "other.js", "content": "console.log('other')\n", "create": True},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "try verifier too early",
            "tool_calls": [
                {"id": "verify-too-early", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "blocked by repair lock"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement generated runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    first_write = next(item for item in tool_results if item["provider_call_id"] == "write-one-line")
    skipped_write = next(item for item in tool_results if item["provider_call_id"] == "write-other")
    verifier = next(item for item in tool_results if item["provider_call_id"] == "verify-too-early")
    repair = result.updated_lane_state["active_work_todo"]["write_repair"]

    assert first_write["status"] == "failed"
    assert skipped_write["status"] == "invalid"
    assert "blocked_by_prior_failed_write_in_same_turn" in skipped_write["content"][0]["reason"]
    assert repair["failure_kind"] == "source_mutation_unreadable_long_line"
    assert repair["path"] == "vm.js"
    assert verifier["status"] == "invalid"
    assert "source_mutation_unreadable_long_line repair is pending for vm.js" in verifier["content"][0]["reason"]
    assert not (tmp_path / "vm.js").exists()
    assert not (tmp_path / "other.js").exists()


def test_implement_v2_unreadable_source_write_allows_same_target_multiline_repair(tmp_path) -> None:
    long_line = "const generated = '" + ("x" * 5000) + "';\n"
    multiline_source = "function run() {\n  return 0;\n}\nconsole.log(run());\n"
    outputs = [
        {
            "summary": "write generated source as one line",
            "tool_calls": [
                {
                    "id": "write-one-line",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": long_line, "create": True},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "rewrite generated source as multiline then verify",
            "tool_calls": [
                {
                    "id": "write-multiline",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": multiline_source, "create": True},
                },
                {"id": "verify-after-repair", "name": "run_tests", "arguments": {"command": "node vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement generated runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    first_write = next(item for item in tool_results if item["provider_call_id"] == "write-one-line")
    second_write = next(item for item in tool_results if item["provider_call_id"] == "write-multiline")
    verifier = next(item for item in tool_results if item["provider_call_id"] == "verify-after-repair")

    assert first_write["status"] == "failed"
    assert second_write["status"] == "completed"
    assert verifier["status"] == "completed"
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == multiline_source


def test_implement_v2_post_first_write_verifier_gate_blocks_probe_and_second_write(tmp_path) -> None:
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "probe and rewrite before verifier",
            "tool_calls": [
                {"id": "probe-after-write", "name": "glob", "arguments": {"path": ".", "pattern": "**/*.js"}},
                {
                    "id": "rewrite-before-verify",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('second')\n"},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "blocked before verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    first_write = next(item for item in tool_results if item["provider_call_id"] == "write-vm")
    probe = next(item for item in tool_results if item["provider_call_id"] == "probe-after-write")
    rewrite = next(item for item in tool_results if item["provider_call_id"] == "rewrite-before-verify")

    assert first_write["status"] == "completed"
    assert probe["status"] == "invalid"
    assert "post_first_write_verifier_required" in probe["content"][0]["reason"]
    assert rewrite["status"] == "invalid"
    assert "blocked_by_post_first_write_verifier_gate" in rewrite["content"][0]["reason"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('first')\n"


def test_implement_v2_post_first_write_verifier_gate_allows_terminal_then_followup_read(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ok')"])
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "run verifier",
            "tool_calls": [
                {
                    "id": "verify-after-write",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "execution_contract": {
                            "role": "verify",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "read after verifier evidence",
            "tool_calls": [{"id": "read-after-verify", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "blocked", "summary": "stop after read"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    verify = next(item for item in tool_results if item["provider_call_id"] == "verify-after-write")
    followup_read = next(item for item in tool_results if item["provider_call_id"] == "read-after-verify")

    assert verify["status"] == "completed"
    assert followup_read["status"] == "completed"
    assert "console.log('first')" in json.dumps(followup_read["content"], sort_keys=True)


def test_implement_v2_post_first_write_verifier_gate_does_not_unlock_on_preexec_command_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "empty command then probe",
            "tool_calls": [
                {"id": "empty-command", "name": "run_command", "arguments": {"command": "", "cwd": "."}},
                {"id": "read-after-empty-command", "name": "read_file", "arguments": {"path": "vm.js"}},
            ],
            "finish": {"outcome": "blocked", "summary": "empty command did not produce terminal feedback"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        if not outputs:
            return {"summary": "stop", "finish": {"outcome": "blocked"}}
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    empty_command = next(item for item in tool_results if item["provider_call_id"] == "empty-command")
    read_after_empty = next(item for item in tool_results if item["provider_call_id"] == "read-after-empty-command")

    assert empty_command["status"] == "failed"
    assert "command is empty" in empty_command["content"][0]["reason"]
    assert "command_run_id" not in empty_command["content"][0]
    assert read_after_empty["status"] == "invalid"
    assert "post_first_write_verifier_required" in read_after_empty["content"][0]["reason"]


def test_implement_v2_post_first_write_verifier_gate_allows_patch_text_same_target(tmp_path) -> None:
    patch = "*** Begin Patch\n*** Update File: vm.js\n@@\n-console.log('first')\n+console.log('second')\n*** End Patch\n"
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "patch same target",
            "tool_calls": [{"id": "patch-vm", "name": "apply_patch", "arguments": {"patch": patch}}],
            "finish": {"outcome": "blocked", "summary": "stop after patch"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    patch_result = next(item for item in tool_results if item["provider_call_id"] == "patch-vm")

    assert patch_result["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('second')\n"


def test_implement_v2_post_first_write_verifier_gate_allows_patch_lines_same_target(tmp_path) -> None:
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: vm.js",
        "@@",
        "-console.log('first')",
        "+console.log('second')",
        "*** End Patch",
    ]
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "patch same target with line-array transport",
            "tool_calls": [{"id": "patch-vm-lines", "name": "apply_patch", "arguments": {"patch_lines": patch_lines}}],
            "finish": {"outcome": "blocked", "summary": "stop after patch"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    patch_result = next(item for item in tool_results if item["provider_call_id"] == "patch-vm-lines")

    assert patch_result["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('second')\n"


def test_implement_v2_post_first_write_verifier_gate_blocks_same_target_delete_patch(tmp_path) -> None:
    patch = "*** Begin Patch\n*** Delete File: vm.js\n*** End Patch\n"
    outputs = [
        {
            "summary": "write first implementation",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "console.log('first')\n"},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "delete same target before verifier",
            "tool_calls": [{"id": "delete-vm", "name": "apply_patch", "arguments": {"patch": patch}}],
            "finish": {"outcome": "blocked", "summary": "delete blocked before verifier"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Implement the runtime"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    delete_result = next(item for item in tool_results if item["provider_call_id"] == "delete-vm")

    assert delete_result["status"] == "invalid"
    assert "post_first_write_verifier_required" in delete_result["content"][0]["reason"]
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('first')\n"


def test_implement_v2_live_json_prompt_surfaces_post_first_write_verifier_gate(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        lane_config={"mode": "full"},
    )
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=2,
        max_turns=8,
        base_max_turns=8,
        post_first_write_verifier_state={
            "active": True,
            "first_write_path": "vm.js",
            "required_next_action": "run one terminal verifier command",
        },
        history=(),
    )
    response_contract = prompt.split("response_contract_json:\n", 1)[1].split("\nhistory_json:", 1)[0]

    assert "vm.js was written successfully" not in response_contract
    assert "Run one terminal verifier command now" not in response_contract


def test_implement_v2_live_json_prompt_hides_terminal_reaction_frontier_pressure(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        lane_config={"mode": "full"},
    )
    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=3,
        max_turns=8,
        base_max_turns=8,
        terminal_failure_reaction_turns_used=1,
        terminal_failure_reaction_turn_limit=2,
        hard_runtime_frontier_state={
            "latest_runtime_failure": {
                "failure_class": "runtime_artifact_missing",
                "required_next_probe": "inspect artifact path before retry",
            },
            "first_write_frontier_stall": {
                "target_path": "vm.js",
                "required_next_action": "patch vm.js now",
            },
        },
        history=(),
    )

    assert "terminal_failure_reaction_turns_used: 1/2" in prompt
    assert "Hard-runtime frontier continuation gate" not in prompt
    assert "First-write frontier stall" not in prompt
    assert "lane_hard_runtime_frontier" not in prompt
    assert "required_next_probe" not in prompt
    assert "required_next_action" not in prompt


def test_implement_v2_write_repair_lock_does_not_unlock_after_dry_run_write(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("function sys(){return 0}\n", encoding="utf-8")
    outputs = [
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function missing(){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "one exact target read is allowed",
            "tool_calls": [{"id": "read-current", "name": "read_file", "arguments": {"path": "vm.js"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "dry-run write must not unlock verifier",
            "tool_calls": [
                {
                    "id": "dry-run-write",
                    "name": "write_file",
                    "arguments": {
                        "path": "vm.js",
                        "content": "function sys(){let n=0;return n}\n",
                        "dry_run": True,
                    },
                },
                {"id": "verify-after-dry-run", "name": "run_tests", "arguments": {"command": "test -f vm.js", "cwd": "."}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after dry-run"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    dry_run_write = next(item for item in tool_results if item["provider_call_id"] == "dry-run-write")
    verify = next(item for item in tool_results if item["provider_call_id"] == "verify-after-dry-run")

    assert dry_run_write["status"] == "completed"
    assert dry_run_write["side_effects"] == []
    assert verify["status"] == "invalid"
    assert "write_repair_lock_active" in verify["content"][0]["reason"]
    assert result.updated_lane_state["active_work_todo"]["write_repair"]["failure_kind"] == "stale_exact_edit"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "function sys(){return 0}\n"


def test_implement_v2_active_work_todo_clears_write_repair_after_apply_patch_side_effect_path(tmp_path) -> None:
    target = tmp_path / "vm.js"
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        "-function sys(){return 0}\n"
        "+function sys(){let n=R[2]>>>0;return n}\n"
        "*** End Patch\n"
    )
    outputs = [
        {
            "summary": "write generated runtime",
            "tool_calls": [
                {
                    "id": "write-vm",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "function sys(){return 0}\n"},
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "attempt stale exact edit",
            "tool_calls": [
                {
                    "id": "stale-edit",
                    "name": "edit_file",
                    "arguments": {
                        "path": "vm.js",
                        "old": "function sys(n){",
                        "new": "function sys(){let n=R[2]>>>0;",
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair from current text",
            "tool_calls": [
                {
                    "id": "apply-repair",
                    "name": "apply_patch",
                    "arguments": {"patch": patch, "apply": True},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after write repair"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["vm.js"], "plan_item": "Repair generated VM"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    assert target.read_text(encoding="utf-8") == "function sys(){let n=R[2]>>>0;return n}\n"
    assert "write_repair" not in result.updated_lane_state["active_work_todo"]


def test_implement_v2_active_work_todo_first_write_due_is_visible_next_turn(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('hello')\n", encoding="utf-8")
    outputs = [
        {
            "summary": "cheap source probes before first write",
            "tool_calls": [
                {"id": "probe-dir", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "probe-file", "name": "read_file", "arguments": {"path": "sample.py"}},
                {"id": "probe-search", "name": "search_text", "arguments": {"query": "hello", "path": "."}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "make first scoped write",
            "tool_calls": [
                {"id": "write-sample", "name": "write_file", "arguments": {"path": "sample.py", "content": "print('done')\n"}},
            ],
            "finish": {"outcome": "blocked", "summary": "stop after first write"},
        },
    ]
    prompts: list[str] = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            persisted_lane_state={
                "active_work_todo": {
                    "id": "todo-1",
                    "status": "drafting",
                    "source": {"target_paths": ["sample.py"], "plan_item": "Patch sample.py"},
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
                "first_write_probe_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    readiness = result.updated_lane_state["active_work_todo"]["first_write_readiness"]

    assert len(prompts) == 2
    assert "first_write_due" not in prompts[1]
    assert '"kind":"patch_or_edit"' not in prompts[1]
    assert "Implement V2 WorkFrame" not in prompts[1]
    assert target.read_text(encoding="utf-8") == "print('done')\n"
    assert readiness["status"] == "written"
    assert readiness["first_write_attempt_turn"] == 2
    assert readiness["first_write_latency_turns"] == 1


def test_implement_v2_does_not_classify_tmp_artifact_missing_read_as_first_write_stall(tmp_path) -> None:
    outputs = [
        {
            "summary": "probe source and inspect missing external artifact",
            "tool_calls": [
                {"id": "call-probe-source", "name": "inspect_dir", "arguments": {"path": "."}},
                {"id": "call-read-artifact", "name": "read_file", "arguments": {"path": "/tmp/frame.bmp"}},
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        raise ModelBackendError("request timed out")

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.metrics["model_error"]["failure_class"] == "model_timeout"
    assert "semantic_failure_class" not in result.metrics["model_error"]
    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})
    assert "latest_build_failure" not in frontier
    assert "fake failure" not in json.dumps(frontier, sort_keys=True)


def test_implement_v2_runs_configured_final_verifier_closeout_before_low_budget_model_turn(tmp_path) -> None:
    target = tmp_path / "sample.py"
    target.write_text("print('old')\n", encoding="utf-8")
    verify_command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "assert Path('sample.py').read_text(encoding='utf-8') == \"print('done')\\n\"; "
                "Path('ok.txt').write_text('ok', encoding='utf-8')"
            ),
        ]
    )
    model_calls = 0

    def fake_model(*_args, **_kwargs):
        nonlocal model_calls
        model_calls += 1
        if model_calls > 1:
            raise ModelBackendError("request timed out")
        return {
            "summary": "write the implementation, then let deterministic closeout verify when budget is low",
            "tool_calls": [
                {
                    "id": "write-sample",
                    "name": "write_file",
                    "arguments": {"path": "sample.py", "content": "print('done')\n"},
                },
                {
                    "id": "diagnostic-after-write",
                    "name": "run_command",
                    "arguments": {"command": "printf 'diagnostic\\n'", "cwd": ".", "use_shell": True},
                },
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Patch sample.py and verify ok.txt exists.",
                "verify_command": verify_command,
                "expected_artifacts": [{"path": "ok.txt", "kind": "file"}],
                "max_wall_seconds": 10,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "auto_approve_writes": True,
                "verify_command": verify_command,
                "final_verifier_closeout_trigger_seconds": 10,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=5,
        max_turns=2,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    verifier_result = manifest["tool_results"][-1]

    assert model_calls == 1
    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["model_turns"] == 1
    assert result.metrics["final_verifier_closeout_count"] == 1
    assert verifier_result["provider_call_id"] == "call-final-verifier-closeout-002"
    assert verifier_result["status"] == "completed"
    assert (tmp_path / "ok.txt").read_text(encoding="utf-8") == "ok"
    assert result.updated_lane_state["finish"]["completion_source"] == "structured_final_verifier_pass"
    assert any(
        event.kind == "finish"
        and event.turn_id == "turn-2-final-verifier-closeout"
        and event.payload["finish_arguments"]["completion_source"] == "structured_final_verifier_pass"
        for event in result.transcript
    )


def test_implement_v2_live_json_accept_edits_preserves_explicit_dry_run(tmp_path) -> None:
    target = tmp_path / "preview.txt"
    outputs = [
        {
            "summary": "preview the implementation artifact",
            "tool_calls": [
                {
                    "id": "write-1",
                    "name": "write_file",
                    "arguments": {"path": "preview.txt", "content": "ok\n", "create": True, "dry_run": True},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "preview only"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_call = manifest["tool_calls"][0]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert result.metrics["write_evidence_count"] == 0
    assert not target.exists()
    assert "apply" not in tool_call["arguments"]
    assert tool_call["arguments"]["dry_run"] is True
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert tool_result["content"][0]["written"] is False


def test_implement_v2_live_json_blocks_same_turn_calls_after_failed_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    side_effect = tmp_path / "verifier_ran.txt"
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('verifier_ran.txt').write_text('bad', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "patch and verify in one turn",
            "tool_calls": [
                {
                    "id": "edit-1",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "missing\n", "new": "after\n"},
                },
                {
                    "id": "verify-1",
                    "name": "run_command",
                    "arguments": {"command": command, "cwd": ".", "use_shell": True, "timeout": 5},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "write failed"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    edit_result = manifest["tool_results"][0]
    skipped_result = manifest["tool_results"][1]

    assert result.status == "blocked"
    assert edit_result["status"] == "failed"
    assert skipped_result["status"] == "invalid"
    assert "blocked_by_prior_failed_write_in_same_turn" in skipped_result["content"][0]["reason"]
    assert not side_effect.exists()


def test_implement_v2_live_json_observes_same_turn_shell_patch_and_verifier(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    side_effect = tmp_path / "verifier_ran.txt"
    verify_command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; Path('verifier_ran.txt').write_text('bad', encoding='utf-8')",
        ]
    )
    outputs = [
        {
            "summary": "shell patch and verify in one turn",
            "tool_calls": [
                {
                    "id": "shell-patch",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "p=Path('vm.js')\n"
                            "s=p.read_text()\n"
                            "p.write_text(s.replace('old','new'))\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "verify-1",
                    "name": "run_command",
                    "arguments": {"command": verify_command, "cwd": ".", "use_shell": True, "timeout": 5},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "observed shell patch"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    patch_result = manifest["tool_results"][0]
    skipped_result = manifest["tool_results"][1]

    assert result.status == "blocked"
    assert patch_result["status"] == "completed"
    assert patch_result["content"][0]["tool_route"] == "process_runner"
    assert patch_result["content"][0]["process_source_observations"][0]["changed_count"] == 1
    assert skipped_result["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"
    assert side_effect.exists()


def test_implement_v2_run_command_source_patch_misuse_detects_string_variable_paths(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    command = (
        "node - <<'NODE'\n"
        "const fs = require('fs');\n"
        "const p = 'vm.js';\n"
        "let s = fs.readFileSync(p, 'utf8');\n"
        "fs.writeFileSync(p, s.replace('old', 'new'));\n"
        "NODE\n"
        "node --check vm.js"
    )

    outputs = [
        {
            "summary": "shell patch through a string path variable",
            "tool_calls": [
                {
                    "id": "shell-patch",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "source patch misuse"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.status == "blocked"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_source_patch_misuse_detects_reassigned_string_variable_paths(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    (tmp_path / "scratch.txt").write_text("scratch\n", encoding="utf-8")
    command = (
        "node - <<'NODE'\n"
        "const fs = require('fs');\n"
        "let p = 'scratch.txt';\n"
        "p = 'vm.js';\n"
        "let s = fs.readFileSync(p, 'utf8');\n"
        "fs.writeFileSync(p, s.replace('old', 'new'));\n"
        "NODE\n"
        "node --check vm.js"
    )

    outputs = [
        {
            "summary": "shell patch through a reassigned string path variable",
            "tool_calls": [
                {
                    "id": "shell-patch",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "source patch misuse"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.status == "blocked"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_source_writer_variable_path_routes_to_process_observer(tmp_path) -> None:
    command = (
        f"{shlex.quote(sys.executable)} - <<'PY'\n"
        "p = 'generated.py'\n"
        "open(p, 'w').write('print(1)\\n')\n"
        "PY"
    )

    outputs = [
        {
            "summary": "bounded source writer through a variable path",
            "tool_calls": [
                {
                    "id": "shell-writer",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert first_result["status"] == "completed"
    assert first_result["content"][0]["tool_route"] == "process_runner"
    assert first_result["content"][0]["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "generated.py").exists()


def test_implement_v2_run_command_source_mutation_classifier_uses_copy_destinations() -> None:
    assert _source_like_mutation_paths("cp vm.js /tmp/vm.js") == ()
    assert _source_like_mutation_paths("install -m 0644 vm.js /tmp/vm.js") == ()
    assert _source_like_mutation_paths("cp vm.js generated.js") == ("generated.js",)
    assert _source_like_mutation_paths("install -m 0644 vm.js generated.js") == ("generated.js",)
    assert _source_like_mutation_paths("mv vm.js /tmp/vm.js") == ("vm.js",)
    assert _source_like_mutation_paths("cp /tmp/generated.js .") == ("generated.js",)
    assert _source_like_mutation_paths("cp /tmp/generated.js src/") == ("src/generated.js",)
    assert _source_like_mutation_paths("cp -t src /tmp/generated.js") == ("src/generated.js",)


def test_implement_v2_run_command_source_mutation_classifier_uses_existing_directory_targets(tmp_path) -> None:
    (tmp_path / "src").mkdir()

    assert _source_like_mutation_paths("cp /tmp/generated.py src", cwd=tmp_path) == ("src/generated.py",)
    assert _source_like_mutation_paths("install -m 0644 /tmp/generated.py src", cwd=tmp_path) == (
        "src/generated.py",
    )


def test_implement_v2_run_command_source_mutation_classifier_ignores_heredoc_assignment_body() -> None:
    command = "python3 - <<'PY'\ncp = 'generated.py'\nPY"

    assert _source_like_mutation_paths(command) == ()


def test_implement_v2_run_command_source_mutation_classifier_unwraps_explicit_shell_interpreter() -> None:
    command = shlex.join(["bash", "-lc", "printf 'ok\\n' > generated.py"])

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_shell_options_before_c() -> None:
    command = shlex.join(["bash", "-e", "-c", "printf 'ok\\n' > generated.py"])

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_shell_o_option_before_c() -> None:
    command = shlex.join(["bash", "-euo", "pipefail", "-c", "printf 'ok\\n' > generated.py"])

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_long_shell_options_before_c() -> None:
    command = shlex.join(["bash", "--noprofile", "--posix", "-c", "printf 'ok\\n' > generated.py"])

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_shell_long_options_with_args() -> None:
    command = shlex.join(["bash", "--rcfile", "rc", "-c", "printf 'ok\\n' > generated.py"])

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_multiple_shell_scripts() -> None:
    command = "bash -c 'echo ok' && bash -c 'printf ok > generated.py'"

    assert _source_like_mutation_paths(command) == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_handles_background_and_grouped_file_commands() -> None:
    assert _source_like_mutation_paths("sleep 0 & cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("bash -c '( cp source.tmp generated.py )'") == ("generated.py",)
    assert _source_like_mutation_paths("sleep 0&cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("(cp source.tmp generated.py)") == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_env_options() -> None:
    assert _source_like_mutation_paths("env -i cp /tmp/generated.py generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("/usr/bin/env -i cp /tmp/generated.py generated.py") == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_unwraps_env_tee() -> None:
    assert _source_like_mutation_paths("env -i tee generated.py < source.tmp") == ("generated.py",)
    assert _source_like_mutation_paths("/usr/bin/env -i tee generated.py < source.tmp") == ("generated.py",)
    assert _source_like_mutation_paths("tee /tmp/out.log < vm.py") == ()
    assert _source_like_mutation_paths("tee < source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("sleep 0 & tee generated.py < source.tmp") == ("generated.py",)
    assert _source_like_mutation_paths("(tee generated.py < source.tmp)") == ("generated.py",)
    assert _source_like_mutation_paths("tee generated.py<source.tmp") == ("generated.py",)


def test_implement_v2_run_command_source_mutation_classifier_ignores_redirection_operands_for_file_commands() -> None:
    assert _source_like_mutation_paths("cp source.tmp generated.py<input.txt") == ("generated.py",)
    assert _source_like_mutation_paths("< input.txt cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("touch generated.py<input.txt") == ("generated.py",)
    assert _source_like_mutation_paths("< input.txt touch generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("cp source.tmp generated.py >> /tmp/out.log") == ("generated.py",)
    assert _source_like_mutation_paths("2>/tmp/err.log cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("2>&1 cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("1>/tmp/out 2>&1 cp source.tmp generated.py") == ("generated.py",)
    assert _source_like_mutation_paths("bash -lc 'printf ok >& generated.py'") == ("generated.py",)
    assert _source_like_mutation_paths("bash -lc 'printf ok >&1'") == ()


def test_implement_v2_run_command_open_default_read_patch_routes_to_process_observer(
    tmp_path,
) -> None:
    (tmp_path / "vm.py").write_text("print('old')\n", encoding="utf-8")
    command = (
        f"{shlex.quote(sys.executable)} - <<'PY'\n"
        "p = 'vm.py'\n"
        "s = open(p, encoding='utf-8').read()\n"
        "open(p, mode='w', encoding='utf-8').write(s.replace('old', 'new'))\n"
        "PY"
    )

    outputs = [
        {
            "summary": "shell patch through Python open default read mode",
            "tool_calls": [
                {
                    "id": "shell-patch",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "source patch misuse"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.status == "blocked"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.py").read_text(encoding="utf-8") == "print('new')\n"


def test_implement_v2_model_turn_boundary_preserves_rendered_prompt_and_call_args(tmp_path) -> None:
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
        },
    )
    expected_prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        turn_index=1,
        max_turns=1,
        base_max_turns=1,
        terminal_failure_reaction_turn_limit=1,
        tool_contract_recovery_turn_limit=1,
        history=(),
    )

    def fake_model(*args, **kwargs):
        calls.append((args, kwargs))
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no change"}}

    result = run_live_json_implement_v2(
        lane_input,
        model_auth={"path": "auth.json"},
        base_url="https://example.invalid",
        timeout=12.5,
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args == (
        "codex",
        {"path": "auth.json"},
        expected_prompt,
        "gpt-5.5",
        "https://example.invalid",
        12.5,
    )
    assert kwargs == {"log_prefix": "implement_v2 live_json session=ws-1 turn=1"}
    assert result.metrics["prompt_chars_total"] == len(expected_prompt)


def test_implement_v2_model_turn_boundary_error_descriptor_omits_raw_prompt() -> None:
    prompt = "secret prompt body should not be serialized"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )

    def fake_model(*_args, **_kwargs):
        raise ModelBackendError("request timed out after 5s")

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    serialized = json.dumps(output.observation, ensure_ascii=False, sort_keys=True)
    assert output.model_error["failure_class"] == "model_timeout"
    assert output.normalized_payload == {}
    assert "secret prompt body" not in serialized
    assert output.observation["prompt"] == {"chars": len(prompt), "sha256": "sha256:prompt"}


def test_implement_v2_model_turn_retries_transient_backend_error_once() -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")
        return {
            "summary": "retry succeeded",
            "tool_calls": [],
            "finish": {"outcome": "failed", "summary": "not done"},
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 2
    assert output.model_error == {}
    assert output.normalized_payload["summary"] == "retry succeeded"
    assert output.response_shape["retry_count"] == 1
    assert output.observation["model_retry_count"] == 1


def test_implement_v2_model_turn_transient_retry_uses_remaining_timeout(monkeypatch) -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    clock_values = iter([0.0, 1.0, 1.0, 1.1])
    observed_timeouts = []

    monkeypatch.setattr("mew.implement_lane.v2_runtime.time.monotonic", lambda: next(clock_values))

    def fake_model(*args, **_kwargs):
        observed_timeouts.append(args[5])
        if len(observed_timeouts) == 1:
            raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")
        return {
            "summary": "retry succeeded",
            "tool_calls": [],
            "finish": {"outcome": "failed", "summary": "not done"},
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert observed_timeouts == [5, 4.0]
    assert output.model_error == {}
    assert output.response_shape["retry_count"] == 1
    assert output.response_shape["transient_retry_count"] == 1


def test_implement_v2_model_turn_does_not_retry_transient_after_turn_timeout_exhausted(monkeypatch) -> None:
    prompt = "return a small JSON action"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=1,
        log_prefix="test",
    )
    clock_values = iter([0.0, 1.2, 1.2])
    calls = []

    monkeypatch.setattr("mew.implement_lane.v2_runtime.time.monotonic", lambda: next(clock_values))

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        raise ModelBackendError("Codex Web API error: IncompleteRead(5188 bytes read)")

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 1
    assert output.model_error["failure_class"] == "model_backend_error"
    assert output.model_error["retry_suppressed_reason"] == "model_turn_timeout_exhausted"
    assert "retry_count" not in output.response_shape


def test_implement_v2_model_turn_does_not_retry_json_parse_error() -> None:
    prompt = "bad JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        raise ModelBackendError('failed to parse JSON plan: Extra data; raw={"summary":"bad"} trailing')

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 1
    assert output.model_error["failure_class"] == "model_json_parse_error"


def test_implement_v2_model_turn_retries_recoverable_tool_call_json_parse_error() -> None:
    prompt = "tool call JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    prompts = []

    def fake_model(_backend, _auth, model_prompt, *_args, **_kwargs):
        prompts.append(model_prompt)
        if len(prompts) == 1:
            raise ModelBackendError(
                'failed to parse JSON plan: response did not contain valid JSON object; '
                'raw={"summary":"patch","tool_calls":[{"id":"call-1","name":"apply_patch","arguments":{"patch":"*** Begin Patch'
            )
        return {
            "summary": "retry ok",
            "tool_calls": [{"id": "call-1", "name": "inspect_dir", "arguments": {"path": "."}}],
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(prompts) == 2
    assert "implement_v2_json_repair_retry" in prompts[1]
    assert output.model_error == {}
    assert output.response_shape["parse_retry_count"] == 1
    assert output.observation["model_parse_retry_count"] == 1
    assert output.prompt_chars == output.observation["prompt"]["chars"]
    assert output.normalized_payload["summary"] == "retry ok"


def test_implement_v2_model_turn_parse_retry_does_not_consume_transient_retry_budget() -> None:
    prompt = "tool call JSON response"
    turn_input = ModelTurnInput(
        lane=IMPLEMENT_V2_LANE,
        lane_attempt_id="attempt-1",
        turn_id="turn-1",
        turn_index=1,
        transport="model_json",
        model_backend="codex",
        model="gpt-5.5",
        rendered_prompt=prompt,
        current_projection_bytes=b"[]",
        prompt_descriptor={"chars": len(prompt), "sha256": "sha256:prompt"},
        projection_descriptor={"current_projection_chars": 2, "current_projection_sha256": "sha256:projection"},
        timeout_seconds=5,
        log_prefix="test",
    )
    calls = []

    def fake_model(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise ModelBackendError(
                'failed to parse JSON plan: response did not contain valid JSON object; '
                'raw={"summary":"patch","tool_calls":[{"id":"call-1","name":"apply_patch","arguments":{"patch":"*** Begin Patch'
            )
        if len(calls) == 2:
            raise ModelBackendError("Codex Web API error: IncompleteRead(42 bytes read)")
        return {
            "summary": "retry ok",
            "tool_calls": [{"id": "call-1", "name": "inspect_dir", "arguments": {"path": "."}}],
        }

    output = _call_model_turn(
        turn_input,
        model_json_callable=fake_model,
        model_auth={"path": "auth.json"},
        base_url="",
    )

    assert len(calls) == 3
    assert output.model_error == {}
    assert output.response_shape["retry_count"] == 2
    assert output.response_shape["parse_retry_count"] == 1
    assert output.response_shape["transient_retry_count"] == 1


def test_implement_v2_prompt_history_render_helper_matches_existing_json_shape() -> None:
    history = tuple({"turn": index, "summary": f"履歴 {index}"} for index in range(1, 11))

    rendered = _render_prompt_history_json(history)
    projected = json.loads(rendered)

    assert '"summary": "履歴 1"' not in rendered
    assert '"summary": "履歴 2"' not in rendered
    assert '"summary": "履歴 3"' in rendered
    assert len(projected) == 8
    assert projected[0]["turn"] == 3
    assert projected[0]["history_compacted"] is True
    assert projected[-1] == {"turn": 10, "summary": "履歴 10"}


def test_implement_v2_prompt_sections_include_compact_coding_contract() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    section = next(item for item in sections if item.id == "implement_v2_coding_contract")
    section_ids = {item.id for item in sections}

    assert section.cache_policy == "cacheable"
    assert section.stability == "static"
    assert "Inspect enough context to understand the smallest coherent change" in section.content
    assert "Make source changes with apply_patch or edit_file" in section.content
    assert "Use run_command or run_tests to build, run, and verify" in section.content
    assert "cheap probe" not in section.content
    assert "first_write" not in section.content
    assert "required_next" not in section.content
    assert "implement_v2_active_coding_rhythm" not in section_ids


def test_implement_v2_prompt_sections_hide_workframe_state_but_keep_debug_bundle() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {"target_paths": ["src/app.py"], "plan_item": "Patch app"},
                "first_write_readiness": {
                    "first_write_due": True,
                    "probes_seen_without_write": 3,
                    "required_next_action": "make one scoped source mutation",
                },
                "write_repair": {
                    "failure_kind": "stale_exact_edit",
                    "path": "src/app.py",
                    "required_next_action": "repair src/app.py before verifier",
                },
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    by_id = {section.id: section for section in sections}
    dynamic_sections = [section for section in sections if section.stability == "dynamic"]
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    debug_rendered = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert dynamic_sections == []
    assert "implement_v2_workframe" not in by_id
    assert "implement_v2_active_work_todo" not in by_id
    assert "implement_v2_repair_history" not in by_id
    assert "implement_v2_hard_runtime_frontier_state" not in by_id
    assert '"workframe":' in debug_rendered
    assert '"required_next":' in debug_rendered
    assert "stale_exact_edit" in debug_rendered
    assert '"src/app.py"' in debug_rendered


def test_implement_v2_live_json_prompt_omits_frontier_update_contract_without_frontier(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Fix a focused Python bug and run the relevant test."},
        lane_config={"mode": "full"},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=1,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' not in prompt
    assert "implement_v2_hard_runtime_frontier_state" not in prompt
    assert "implement_v2_active_work_todo" not in prompt
    assert "implement_v2_repair_history" not in prompt
    assert "sidecar:active_work_todo" not in prompt
    assert "sidecar:lane_hard_runtime_frontier" not in prompt
    assert "sidecar:lane_repair_history" not in prompt
    assert '"evidence_refs"' in prompt
    assert '"oracle_refs": [\n      "oracle:..."\n    ]' in prompt
    assert '"acceptance_evidence"' not in prompt
    assert "do not rely on prose-only acceptance_evidence claims" in prompt


def test_implement_v2_live_json_prompt_hides_prewrite_required_next_probe(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=3,
        max_turns=8,
        base_max_turns=8,
        tool_specs=list_v2_tool_specs_for_mode("full"),
        prewrite_probe_readiness={
            "ready": False,
            "missing_categories": ("source_output_contract",),
        },
        prewrite_missing_probe={
            "required_next_probe": (
                "read_file doomgeneric/doomgeneric/doomgeneric_img.c "
                "to confirm the source-declared output artifact before writing"
            )
        },
        history=(),
    )

    assert "Required next probe" not in prompt
    assert "required_next_probe" not in prompt
    assert "read_file doomgeneric/doomgeneric/doomgeneric_img.c" not in prompt


def test_implement_v2_hard_runtime_live_json_prompt_hides_write_file_guidance(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-hard-runtime",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "goal": "Implement a MIPS ELF interpreter/runtime in node and write a frame image from provided source."
        },
        lane_config={"mode": "full"},
    )
    tool_specs = list_v2_tool_specs_for_task("full", task_contract=lane_input.task_contract)

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        turn_index=4,
        max_turns=8,
        base_max_turns=8,
        tool_specs=tool_specs,
        active_work_todo_state={
            "id": "todo-1",
            "status": "drafting",
            "source": {"target_paths": ["vm.js"]},
            "first_write_readiness": {
                "first_write_due": True,
                "required_next_action": (
                    "make one scoped source mutation with write_file/edit_file/apply_patch before more probes"
                ),
            },
        },
        history=(),
    )

    assert "apply_patch or edit_file" in prompt
    assert "edit_file/apply_patch" not in prompt
    assert "write_file/edit_file/apply_patch" not in prompt


def test_implement_v2_finish_gate_history_projects_compact_recovery_card() -> None:
    history = _finish_gate_history(
        turn_index=2,
        decision={
            "decision": "block_continue",
            "reason": "missing typed evidence",
            "missing_obligations": ["oracle:task:frame_similarity"],
            "invalid_evidence_refs": ["ev:bad"],
            "blockers": [
                {
                    "code": "missing_typed_evidence",
                    "reason": "need final verifier",
                    "proof_object": {"large": "do-not-project"},
                }
            ],
            "proof_object": {"large": "do-not-project"},
        },
        continuation_prompt="run one verifier-shaped comparison and finish with its evidence id",
    )
    content = history["tool_results"][0]["content"]
    card = content["finish_gate_recovery_card"]
    rendered = json.dumps(history, sort_keys=True)

    assert "finish_gate" not in content
    assert card["finish_blocked"] is True
    assert card["missing"] == ["oracle:task:frame_similarity"]
    assert card["invalid_evidence_refs"] == ["ev:bad"]
    assert card["blockers"][0]["code"] == "missing_typed_evidence"
    assert card["next_action"] == "run one verifier-shaped comparison and finish with its evidence id"
    assert "do-not-project" not in rendered


def test_implement_v2_live_json_prompt_hides_frontier_update_contract_by_default_with_frontier(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a runtime artifact repair."},
        lane_config={"mode": "full"},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        hard_runtime_frontier_state={"schema_version": 1, "status": "active"},
        turn_index=2,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' not in prompt
    assert "mew derives the latest failure from paired tool results" not in prompt


def test_implement_v2_live_json_prompt_hides_frontier_update_contract_even_with_legacy_debug_opt_in(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a runtime artifact repair."},
        lane_config={"mode": "full", "debug_model_frontier_update": True},
    )

    prompt = _live_json_prompt(
        lane_input,
        lane_attempt_id="attempt-1",
        hard_runtime_frontier_state={"schema_version": 1, "status": "active"},
        turn_index=2,
        max_turns=8,
        base_max_turns=8,
        history=(),
    )

    assert '"frontier_state_update"' not in prompt
    assert '"use_only_when": "a hard-runtime or compatibility frontier genuinely changed"' not in prompt
    assert "mew derives the latest failure from paired tool results" not in prompt
    assert '"latest_failure"' not in prompt
    assert '"latest_runtime_failure"' not in prompt
    assert '"latest_build_failure"' not in prompt
    assert '"next_verifier_shaped_command"' not in prompt
    assert '"source_roles"' not in prompt


def test_implement_v2_live_json_ignores_model_frontier_update_by_default(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "try model-authored frontier",
            "frontier_state_update": {
                "status": "resolved",
                "final_artifact": {"path": "fabricated.txt", "kind": "file"},
            },
            "finish": {"outcome": "blocked", "summary": "state only"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Do not trust model-authored frontier state."},
            lane_config={"mode": "full"},
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})
    assert "latest_build_failure" not in frontier
    assert "fake failure" not in json.dumps(frontier, sort_keys=True)
    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    detail_turn = result.updated_lane_state["proof_manifest"]["metrics"]["integration_observation"]["summary"]
    assert detail_turn["model_turns"] == 1


def test_implement_v2_integration_observation_summary_is_state_safe_by_default(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    secret = "SECRET_TASK_CONTEXT_SHOULD_NOT_BE_SERIALIZED"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": secret},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]
    hot_path = manifest["metrics"]["hot_path_projection"]
    sidecar = manifest["metrics"]["resident_sidecar_state"]
    serialized = json.dumps(observation, ensure_ascii=False, sort_keys=True)

    assert observation["detail_policy"] == "summary"
    assert observation["artifact_ref"] == ""
    assert observation["summary"]["model_turns"] == 1
    assert observation["summary"]["detail_written"] is False
    assert "model_turns" not in observation
    assert secret not in serialized
    assert len(serialized.encode("utf-8")) < 8192
    assert hot_path["phase"] == "m6_24_affordance_collapse_phase_1"
    assert hot_path["normal_full_prompt_bytes"] > 0
    assert hot_path["normal_full_prompt_bytes"] >= hot_path["normal_prompt_section_bytes"]
    assert hot_path["provider_visible_tool_result_bytes"] == 0
    assert sidecar["phase"] == "m6_24_workframe_redesign_phase_1"
    assert sidecar["surface"] == "resident_sidecar_state"
    assert sidecar["total_bytes"] > 0
    assert sidecar["per_turn_growth_bytes"] > 0
    assert set(sidecar["families"]) == {
        "frontier_todo_recovery_cards",
        "integration_observation_detail",
        "tool_call_result",
        "transcript_history",
    }
    assert not (artifact_dir / "implement_v2" / "integration-observation.json").exists()
    assert all(not path.endswith("integration-observation.json") for path in result.proof_artifacts)


def test_implement_v2_resident_sidecar_metrics_compact_large_tool_payloads() -> None:
    large_lines = [f"const value{index} = {index};" for index in range(1200)]
    huge_stdout = "Program output line\n" + ("x" * 120_000)
    call = ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="model_json",
        provider_call_id="call-write-large-source",
        mew_tool_call_id="tool-1",
        tool_name="write_file",
        arguments={"path": "vm.js", "content_lines": large_lines},
    )
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-run-huge-output",
        mew_tool_call_id="tool-2",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "stdout": huge_stdout,
                "stderr": huge_stdout,
                "pre_run_source_tree_snapshot": {
                    "files": {f"/app/src/file{index}.c": {"size": index} for index in range(300)}
                },
            },
        ),
    )
    transcript_event = ImplementLaneTranscriptEvent(
        kind="tool_call",
        lane=IMPLEMENT_V2_LANE,
        turn_id="turn-1",
        event_id="event-1",
        payload={"tool_calls": [call.as_dict()], "raw": huge_stdout},
    )
    history = [
        {
            "turn": 1,
            "summary": huge_stdout,
            "tool_calls": [call.as_dict()],
            "tool_results": [result.as_dict()],
        }
    ]

    metrics = _resident_sidecar_state_metrics(
        transcript=(transcript_event,),
        history=tuple(history),
        tool_calls=(call,),
        tool_results=(result,),
        active_work_todo_state={},
        hard_runtime_frontier_state={},
        model_turn_observations=(),
        model_turns=1,
    )

    assert metrics["surface"] == "resident_sidecar_state"
    assert metrics["families"]["transcript_history"] < 30_000
    assert metrics["families"]["tool_call_result"] < 30_000
    assert metrics["total_bytes"] < 80_000

    history[0]["model_error"] = {"message": huge_stdout}
    with_error = _resident_sidecar_state_metrics(
        transcript=(transcript_event,),
        history=tuple(history),
        tool_calls=(call,),
        tool_results=(result,),
        active_work_todo_state={},
        hard_runtime_frontier_state={},
        model_turn_observations=(),
        model_turns=1,
    )

    assert with_error["families"]["transcript_history"] > metrics["families"]["transcript_history"]
    assert with_error["families"]["transcript_history"] < 40_000


def test_implement_v2_integration_observation_detail_sidecar_is_explicit_and_ref_backed(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"
    secret = "SECRET_PROMPT_BODY_SHOULD_STAY_HASHED"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": secret},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "write_integration_observation_detail": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]
    sidecar_path = artifact_dir / "implement_v2" / "integration-observation.json"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    sidecar_serialized = json.dumps(sidecar, ensure_ascii=False, sort_keys=True)
    turn = sidecar["turns"][0]
    projection = turn["history_projection"]

    assert observation["detail_policy"] == "sidecar"
    assert observation["artifact_ref"] == "integration-observation.json"
    assert observation["summary"]["detail_written"] is True
    assert str(sidecar_path) in result.proof_artifacts
    assert sidecar["lane_attempt_id"] == manifest["lane_attempt_id"]
    assert "model_turns" not in sidecar
    assert len(sidecar["turns"]) == 1
    assert turn["prompt"]["chars"] > 0
    assert turn["prompt"]["sha256"].startswith("sha256:")
    assert projection["future_projection_mode"] == "identity"
    assert projection["future_projection_sha256"] == projection["current_projection_sha256"]
    assert projection["future_projection_chars"] == projection["current_projection_chars"]
    assert projection["diff_summary"]["changed"] is False
    assert sidecar["totals"]["projection_savings_chars"] == 0
    assert sidecar["totals"]["projection_savings_ratio"] == 0.0
    assert secret not in sidecar_serialized


def test_implement_v2_integration_observation_detail_false_string_does_not_write_sidecar(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"

    def fake_model(*_args, **_kwargs):
        return {"summary": "stop", "finish": {"outcome": "blocked", "summary": "no material change"}}

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Inspect only."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "write_integration_observation_detail": "false",
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    observation = manifest["metrics"]["integration_observation"]

    assert observation["detail_policy"] == "summary"
    assert observation["artifact_ref"] == ""
    assert observation["summary"]["detail_written"] is False
    assert not (artifact_dir / "implement_v2" / "integration-observation.json").exists()
    assert all(not path.endswith("integration-observation.json") for path in result.proof_artifacts)


def test_implement_v2_live_json_rejects_cross_turn_duplicate_before_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")
    outputs = [
        {
            "summary": "read first",
            "tool_calls": [
                {"id": "duplicate-call", "name": "read_file", "arguments": {"path": "sample.txt"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "try duplicate id for write",
            "tool_calls": [
                {
                    "id": "duplicate-call",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert manifest["tool_results"][1]["status"] == "invalid"
    assert manifest["tool_results"][1]["provider_call_id"] == "duplicate-call-turn2-seq1"
    assert manifest["tool_calls"][1]["provider_call_id"] == "duplicate-call-turn2-seq1"
    assert "duplicate_provider_call_id_across_turns" in manifest["tool_results"][1]["content"][0]["reason"]


def test_implement_v2_live_json_duplicate_verifier_id_does_not_poison_sibling_write(tmp_path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text("before\n", encoding="utf-8")
    target = tmp_path / "vm.js"
    outputs = [
        {
            "summary": "establish prior provider id",
            "tool_calls": [
                {"id": "verify-existing", "name": "read_file", "arguments": {"path": "sample.txt"}},
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "write fix then accidentally reuse verifier id",
            "tool_calls": [
                {
                    "id": "write-vm-new",
                    "name": "write_file",
                    "arguments": {"path": "vm.js", "content": "module.exports = {};\n", "create": True},
                },
                {
                    "id": "verify-existing",
                    "name": "run_tests",
                    "arguments": {"command": "node vm.js", "cwd": "."},
                },
            ],
            "finish": {"outcome": "completed", "summary": "write should survive duplicate verifier id"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "module.exports = {};\n"
    assert [item["status"] for item in manifest["tool_results"]] == ["completed", "completed", "invalid"]
    assert manifest["tool_results"][1]["provider_call_id"] == "write-vm-new"
    assert "tool_call_identity_invalid" not in str(manifest["tool_results"][1]["content"][0])
    assert manifest["tool_results"][2]["provider_call_id"] == "verify-existing-turn2-seq2"
    assert "duplicate_provider_call_id_across_turns" in manifest["tool_results"][2]["content"][0]["reason"]


def test_implement_v2_live_json_rejects_missing_provider_call_id_before_write(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "try write without provider call id",
            "tool_calls": [
                {
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert manifest["tool_results"][0]["status"] == "invalid"
    assert manifest["tool_results"][0]["provider_call_id"] == "missing-provider-call-id-turn1-seq1"
    assert "tool_call_missing_provider_call_id" in manifest["tool_results"][0]["content"][0]["reason"]


def test_implement_v2_live_json_rejects_same_turn_duplicate_with_same_turn_reason(tmp_path) -> None:
    target = tmp_path / "sample.txt"
    target.write_text("before\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "duplicate provider ids in one turn",
            "tool_calls": [
                {"id": "dup", "name": "read_file", "arguments": {"path": "sample.txt"}},
                {
                    "id": "dup",
                    "name": "edit_file",
                    "arguments": {"path": "sample.txt", "old": "before\n", "new": "after\n", "apply": True},
                },
            ],
            "finish": {"outcome": "completed", "summary": "should not mutate"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["replay_valid"] is True
    assert target.read_text(encoding="utf-8") == "before\n"
    manifest = result.updated_lane_state["proof_manifest"]
    assert [item["status"] for item in manifest["tool_results"]] == ["completed", "invalid"]
    assert manifest["tool_calls"][1]["provider_call_id"] == "dup-turn1-seq2"
    reason = manifest["tool_results"][1]["content"][0]["reason"]
    assert "duplicate_provider_call_id:dup" in reason
    assert "duplicate_provider_call_id_across_turns" not in reason


def test_implement_v2_live_json_blocks_format_only_visual_finish(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "print('saved /tmp/frame.bmp')\n"
                            "print('verified BMP 320x200 valid header')\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "frame was generated",
                "acceptance_evidence": [
                    "turn 1 visual-smoke: saved /tmp/frame.bmp and verified BMP 320x200 valid header"
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp and check the first "
                    "rendered frame against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_visual_artifact_quality_evidence"
    assert result.updated_lane_state["finish"]["outcome"] == "blocked"


def test_implement_v2_live_json_finish_gate_can_continue_then_complete(tmp_path) -> None:
    outputs = [
        {
            "summary": "run weak visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'saved /tmp/frame.bmp\\nvalid BMP header\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "format smoke passed",
                "acceptance_evidence": ["visual-smoke produced a valid /tmp/frame.bmp"],
            },
        },
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "visual-quality",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\nsaved /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed",
                "acceptance_evidence": [
                    (
                        "visual-quality confirmed expected dimensions 640x400 "
                        "and reference similarity for /tmp/frame.bmp"
                    )
                ],
            },
        },
        {
            "summary": "clean stale runtime artifact after preserving quality proof",
            "tool_calls": [
                {
                    "id": "clean-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "rm -f /tmp/frame.bmp && printf 'removed /tmp/frame.bmp\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed and stale artifact removed",
                "acceptance_evidence": [
                    (
                        "visual-quality confirmed expected dimensions 640x400 "
                        "and reference similarity for /tmp/frame.bmp; "
                        "clean-frame removed stale /tmp/frame.bmp"
                    )
                ],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp and check the first "
                    "rendered frame against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"
    assert any(event.payload.get("type") == "deterministic_finish_gate" for event in result.transcript)


def test_implement_v2_live_json_stops_repeated_finish_gate_without_tool_progress(tmp_path) -> None:
    outputs = [
        {
            "summary": "claim completion without proof",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        {
            "summary": "repeat the same completion claim",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        pytest.fail,
    ]

    def fake_model(*_args, **_kwargs):
        item = outputs.pop(0)
        if callable(item):
            item("model should not receive a third turn after repeated finish gate block")
        return item

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the requested implementation and verify it."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    assert result.status == "blocked"
    assert result.metrics["model_turns"] == 2
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["finish_gate_repeat_plateau_count"] == 1
    assert result.updated_lane_state["finish"]["failure_class"] == "finish_gate_repeat_plateau"


def test_implement_v2_live_json_finish_gate_repeat_resets_after_tool_progress(tmp_path) -> None:
    outputs = [
        {
            "summary": "claim completion without proof",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        {
            "summary": "make observable progress before trying again",
            "tool_calls": [
                {
                    "id": "progress-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'observable progress\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        {
            "summary": "repeat the same completion claim after progress",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        pytest.fail,
    ]

    def fake_model(*_args, **_kwargs):
        item = outputs.pop(0)
        if callable(item):
            item("model should not plateau immediately after real tool progress")
        return item

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the requested implementation and verify it."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    assert result.metrics["model_turns"] == 3
    assert result.metrics["finish_gate_block_count"] == 3
    assert result.metrics["finish_gate_repeat_plateau_count"] == 0
    assert result.updated_lane_state["finish"].get("failure_class") != "finish_gate_repeat_plateau"


def test_implement_v2_live_json_invalid_tool_call_does_not_reset_finish_gate_repeat(tmp_path) -> None:
    outputs = [
        {
            "summary": "claim completion without proof",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        {
            "summary": "try to avoid the finish gate with an invalid tool call",
            "tool_calls": [
                {
                    "id": "fake-progress",
                    "name": "not_a_mew_tool",
                    "arguments": {},
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        pytest.fail,
    ]

    def fake_model(*_args, **_kwargs):
        item = outputs.pop(0)
        if callable(item):
            item("invalid tool calls must not bypass the finish-gate repeat plateau")
        return item

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the requested implementation and verify it."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    assert result.status == "blocked"
    assert result.metrics["model_turns"] == 2
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["finish_gate_repeat_plateau_count"] == 1
    assert result.updated_lane_state["finish"]["failure_class"] == "finish_gate_repeat_plateau"
    assert any(event.kind == "finish" for event in result.transcript)


def test_implement_v2_live_json_pre_execution_failed_tool_does_not_reset_finish_gate_repeat(tmp_path) -> None:
    outputs = [
        {
            "summary": "claim completion without proof",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        {
            "summary": "try to avoid the finish gate with a pre-execution command failure",
            "tool_calls": [
                {
                    "id": "empty-command",
                    "name": "run_command",
                    "arguments": {
                        "command": "",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "done",
                "acceptance_evidence": ["I inspected it mentally"],
            },
        },
        pytest.fail,
    ]

    def fake_model(*_args, **_kwargs):
        item = outputs.pop(0)
        if callable(item):
            item("pre-execution failed tool calls must not bypass finish-gate repeat plateau")
        return item

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the requested implementation and verify it."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    assert result.status == "blocked"
    assert result.metrics["model_turns"] == 2
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["finish_gate_repeat_plateau_count"] == 1
    assert result.updated_lane_state["finish"]["failure_class"] == "finish_gate_repeat_plateau"


def test_implement_v2_finish_gate_uses_structured_final_verifier_without_model_evidence(tmp_path) -> None:
    outputs = [
        {
            "summary": "run fresh final verifier with a scratch transcript",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp /tmp/mew-v2-vmout.txt; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n' "
                            "| tee /tmp/mew-v2-vmout.txt; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "/tmp/mew-v2-vmout.txt", "checks": [{"exists": True}, {"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Final verifier evidence is already present from the fresh runtime run.",
                "acceptance_checks": [],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_auto_completes_when_last_turn_final_verifier_passes(tmp_path) -> None:
    outputs = [
        {
            "summary": "run fresh final verifier as the last available turn",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp /tmp/mew-v2-vmout.txt; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "dimension check passed expected dimensions 640x400\\n' "
                            "| tee /tmp/mew-v2-vmout.txt; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "final-verifier",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "/tmp/mew-v2-vmout.txt", "checks": [{"exists": True}, {"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"
    assert result.updated_lane_state["finish"]["completion_source"] == "structured_final_verifier_pass"
    assert any(
        event.kind == "finish" and event.payload["finish_arguments"]["completion_source"] == "structured_final_verifier_pass"
        for event in result.transcript
    )


def test_implement_v2_auto_complete_ignores_old_final_verifier_after_later_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "first final verifier passes",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "final-verifier",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
        },
        {
            "summary": "a later terminal check fails after the verifier",
            "tool_calls": [
                {
                    "id": "late-failure",
                    "name": "run_command",
                    "arguments": {"command": "false", "cwd": ".", "use_shell": True},
                }
            ],
        },
    ]

    def fake_model(*_args, **_kwargs):
        if outputs:
            return outputs.pop(0)
        return {
            "summary": "stop after observing the later failure",
            "finish": {"outcome": "blocked", "summary": "late terminal failure"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Build and verify the runtime artifact."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path), "/tmp"],
                "allowed_write_roots": [str(tmp_path), "/tmp"],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.updated_lane_state["finish"].get("completion_source") != "structured_final_verifier_pass"


def test_implement_v2_auto_complete_skips_read_command_output_after_final_verifier() -> None:
    final_verifier = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="final-verifier",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract": {
                    "role": "runtime",
                    "stage": "final-verifier",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                },
                "verifier_evidence": {"verdict": "pass"},
                "artifact_evidence": [
                    {"artifact_id": "frame000000.bmp", "path": "frame000000.bmp", "status": "passed"},
                ],
            },
        ),
        evidence_refs=("ev:final-verifier",),
    )
    output_read = ToolResultEnvelope(
        lane_attempt_id="attempt",
        provider_call_id="read-output",
        mew_tool_call_id="tool-2",
        tool_name="read_command_output",
        status="completed",
        content=({"stdout_tail": "bounded tail"},),
        evidence_refs=("ev:read-output",),
    )

    finish = _auto_finish_from_structured_final_verifier(
        {"outcome": "blocked", "summary": "implement_v2 reached max_turns before finish"},
        (final_verifier, output_read),
    )

    assert finish["outcome"] == "completed"
    assert finish["completion_source"] == "structured_final_verifier_pass"


def test_implement_v2_finish_gate_rejects_structured_visual_sidecar_without_quality_marker(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final verifier that only proves frame existence and boot stdout",
            "tool_calls": [
                {
                    "id": "verify-frame-exists-only",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Frame artifact exists and boot stdout was observed.",
                "acceptance_checks": [],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "runtime_visual_artifact_quality_evidence" for blocker in blockers)


def test_implement_v2_finish_gate_prefers_structured_sidecar_over_unref_model_check(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final verifier with structured artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified.",
                "acceptance_checks": [
                    {
                        "constraint": "runtime visual artifact is correct",
                        "status": "verified",
                        "evidence": "The final runtime verifier generated and checked the rendered frame.",
                    }
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    assert result.status == "completed"
    assert result.metrics["completion_credit"] is True
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_finish_gate_keeps_structured_sidecar_inside_acceptance_window(tmp_path) -> None:
    weak_checks = [
        {
            "constraint": "runtime visual artifact is correct",
            "status": "verified",
            "evidence": f"unreferenced model claim {index}",
        }
        for index in range(8)
    ]
    outputs = [
        {
            "summary": "run final verifier with structured artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified.",
                "acceptance_checks": weak_checks,
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames and check the first rendered frame "
                    "against expected dimensions 640x400."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["finish_gate_block_count"] == 0
    assert result.metrics["finish_gate_decision"]["decision"] == "allow_complete"


def test_implement_v2_finish_gate_keeps_uncovered_model_check_inside_acceptance_window(tmp_path) -> None:
    weak_checks = [
        {
            "constraint": "runtime visual artifact is correct",
            "status": "verified",
            "evidence": f"unreferenced duplicate model claim {index}",
        }
        for index in range(7)
    ]
    weak_checks.append(
        {
            "constraint": "program output is hello",
            "status": "verified",
            "evidence": "The program output is hello.",
        }
    )
    outputs = [
        {
            "summary": "run final verifier with structured visual artifact evidence",
            "tool_calls": [
                {
                    "id": "verify-final-runtime",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "rm -f frame000000.bmp; "
                            "printf 'I_InitGraphics: framebuffer: x_res: 640, y_res: 400\\n"
                            "saved frame000000.bmp\\n"
                            "dimension check passed expected dimensions 640x400\\n'; "
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('frame000000.bmp').write_bytes(b'BM' + b'0' * 256)\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"stream": "stdout", "checks": [{"non_empty": True}]},
                                {"path": "frame000000.bmp", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "Runtime artifact verified, unrelated behavior claimed.",
                "acceptance_checks": weak_checks,
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames. "
                    "Also make the program output hello."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_evidence_refs_missing" for blocker in blockers)


def test_implement_v2_finish_gate_source_sidecar_does_not_cover_unrelated_model_check(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "source.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    outputs = [
        {
            "summary": "read source but do not verify behavior",
            "tool_calls": [{"id": "read-source", "name": "read_file", "arguments": {"path": "src/source.c"}}],
            "finish": {
                "outcome": "completed",
                "summary": "Claim behavior without proof.",
                "acceptance_checks": [
                    {
                        "constraint": "program output is hello",
                        "status": "verified",
                        "evidence": "The program output is hello.",
                    }
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided src/source.c, the corresponding source code. "
                    "Make the program output hello."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert any(blocker["code"] == "acceptance_evidence_refs_missing" for blocker in blockers)


def test_implement_v2_finish_gate_rejects_intermediate_structured_artifact_without_finish_evidence(tmp_path) -> None:
    outputs = [
        {
            "summary": "build an intermediate artifact",
            "tool_calls": [
                {
                    "id": "build-intermediate",
                    "name": "run_command",
                    "arguments": {
                        "command": "mkdir -p build && printf intermediate > build/intermediate.bin",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": {
                            "role": "build",
                            "stage": "build",
                            "purpose": "build",
                            "proof_role": "target_build",
                            "acceptance_kind": "progress_only",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "build/intermediate.bin", "checks": [{"exists": True}, {"non_empty": True}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "The intermediate artifact exists.",
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create the final runtime artifact and prove it works."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_decision"]["decision"] == "block_continue"


def test_implement_v2_live_json_finish_only_turn_uses_finish_gate(tmp_path) -> None:
    outputs = [
        {
            "summary": "run weak visual smoke",
            "tool_calls": [
                {
                    "id": "visual-smoke",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'saved /tmp/frame.bmp\\nvalid BMP header\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "finish from prior evidence",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "frame was generated",
                "acceptance_evidence": ["visual-smoke produced a valid /tmp/frame.bmp"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    assert result.metrics["finish_gate_decision"]["blockers"][0]["code"] == "runtime_visual_artifact_quality_evidence"


def test_implement_v2_live_json_finish_gate_does_not_link_ambiguous_alpha_call_id(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "run",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\nremoved /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed",
                "acceptance_evidence": [
                    "run completed and confirmed expected dimensions 640x400 with reference similarity"
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_final_verifier_artifact_evidence"


def test_implement_v2_finish_evidence_refs_ignore_ambiguous_alpha_call_id() -> None:
    results = (
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="run",
            mew_tool_call_id="attempt-1:tool:1:1",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="visual-quality",
            mew_tool_call_id="attempt-1:tool:1:2",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
        ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id="1",
            mew_tool_call_id="attempt-1:tool:1:3",
            tool_name="run_command",
            status="completed",
            content=({"stdout": "dimension check passed expected dimensions 640x400\nreference similarity passed\n"},),
        ),
    )

    assert _finish_evidence_refs("run completed with expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("turn 1 confirmed expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("visual-quality confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality: confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality. confirmed expected dimensions 640x400", results) == [
        {"kind": "tool_call", "id": 2}
    ]
    assert _finish_evidence_refs("visual-quality-extra confirmed expected dimensions 640x400", results) == []
    assert _finish_evidence_refs("visual-quality.extra confirmed expected dimensions 640x400", results) == []


def test_implement_v2_live_json_finish_gate_does_not_link_numeric_turn_ids(tmp_path) -> None:
    outputs = [
        {
            "summary": "run visual quality smoke",
            "tool_calls": [
                {
                    "id": "1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'dimension check passed expected dimensions 640x400\\nreference similarity passed\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                },
                {
                    "id": "2",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'removed /tmp/frame.bmp\\n'",
                        "cwd": ".",
                        "use_shell": True,
                    },
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "quality smoke passed and stale artifact removed",
                "acceptance_evidence": [
                    (
                        "turn 1 confirmed expected dimensions 640x400 and reference similarity; "
                        "turn 2 removed /tmp/frame.bmp"
                    )
                ],
            },
        }
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["completion_credit"] is False
    assert result.metrics["finish_gate_block_count"] == 1
    blockers = result.metrics["finish_gate_decision"]["blockers"]
    assert blockers[0]["code"] == "runtime_final_verifier_artifact_evidence"


def test_implement_v2_live_json_model_parse_error_is_replayable_lane_failure(tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts"

    def fake_model(*_args, **_kwargs):
        raise ModelBackendError('failed to parse JSON plan: Extra data; raw={"summary":"bad"} trailing')

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "failed"
    assert result.metrics["replay_valid"] is True
    assert result.metrics["model_error"]["failure_class"] == "model_json_parse_error"
    manifest = result.updated_lane_state["proof_manifest"]
    assert len(manifest["tool_calls"]) == 1
    assert len(manifest["tool_results"]) == 1
    assert manifest["tool_calls"][0]["tool_name"] == "model_response_error"
    assert manifest["tool_results"][0]["tool_name"] == "model_response_error"
    assert manifest["tool_results"][0]["status"] == "invalid"
    assert manifest["tool_results"][0]["is_error"] is True
    history = json.loads((artifact_dir / "implement_v2" / "history.json").read_text(encoding="utf-8"))
    assert history[0]["model_error"]["failure_class"] == "model_json_parse_error"
    assert history[0]["tool_results"][0]["content"]["natural_result_text"].startswith(
        "model_response_error result: invalid"
    )
    result_index = json.loads((artifact_dir / "implement_v2" / "tool_result_index.json").read_text(encoding="utf-8"))
    assert "model-response-error-1" in result_index["by_provider_call_id"]


def test_implement_v2_live_json_drains_active_command_at_max_turns(tmp_path) -> None:
    command = "printf 'start\\n'; sleep 0.2; printf done > done.txt; printf 'done\\n'"

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start final command",
            "tool_calls": [
                {
                    "id": "call-final",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert "done" in tool_result["content"][0]["stdout"]
    assert (tmp_path / "done.txt").read_text(encoding="utf-8") == "done"
    assert result.metrics["command_closeout_count"] == 1
    assert result.metrics["orphaned_command_cleanup_count"] == 0
    assert result.metrics["terminal_evidence_count"] == 1


def test_implement_v2_caps_model_timeout_by_remaining_wall_budget(tmp_path) -> None:
    observed_timeouts = []

    def fake_model(_backend, _auth, _prompt, _model, _base_url, timeout_seconds, **_kwargs):
        observed_timeouts.append(timeout_seconds)
        return {
            "summary": "block after observing timeout",
            "finish": {"outcome": "blocked", "summary": "blocked intentionally"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert observed_timeouts
    assert 0 < observed_timeouts[0] <= 5
    assert result.metrics["wall_timeout"] == {}
    assert result.metrics["wall_elapsed_seconds"] >= 0


def test_implement_v2_stops_before_next_model_turn_when_wall_budget_exhausted(tmp_path) -> None:
    calls = 0

    def fake_model(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        time.sleep(0.01)
        return {
            "summary": "continue until wall timeout",
            "tool_calls": [
                {
                    "id": f"inspect-{calls}",
                    "name": "inspect_dir",
                    "arguments": {"path": "."},
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.001},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=3,
    )

    assert calls == 1
    assert result.status == "blocked"
    assert result.user_visible_summary == "implement_v2 wall-clock budget exhausted before finish"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["wall_timeout"]["next_turn"] == 2
    assert "not enough wall-clock budget" in result.metrics["wall_timeout"]["reason"]


def test_implement_v2_default_model_callable_uses_work_timeout_guard(monkeypatch, tmp_path) -> None:
    import mew.work_loop as work_loop

    calls = []

    def fake_guarded_model(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {
            "summary": "blocked through guarded default path",
            "finish": {"outcome": "blocked", "summary": "guarded default path"},
        }

    monkeypatch.setattr(work_loop, "call_model_json_with_retries", fake_guarded_model)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
            },
        ),
        model_auth={"path": "auth.json"},
        timeout=60,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert len(calls) == 1
    assert calls[0]["args"][5] <= 5


def test_implement_v2_blocks_exec_tool_when_wall_budget_exhausted_after_model_turn(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        time.sleep(0.01)
        return {
            "summary": "try command after wall is gone",
            "tool_calls": [
                {
                    "id": "too-late-command",
                    "name": "run_command",
                    "arguments": {
                        "command": "sleep 0.1; printf done > should_not_exist.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "foreground_budget_seconds": 0.1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.001},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=3,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]
    assert result.status == "blocked"
    assert result.user_visible_summary == "implement_v2 wall-clock budget exhausted before tool execution"
    assert tool_result["status"] == "invalid"
    assert tool_result["content"][0]["reason"] == "implement_v2_wall_budget_exhausted_before_tool_execution"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["wall_timeout"]["reason"] == "not enough wall-clock budget remains for tool execution"
    assert not (tmp_path / "should_not_exist.txt").exists()


def test_implement_v2_blocks_under_budget_required_patch_turn(tmp_path) -> None:
    calls = 0

    def fake_model(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {
            "summary": "surface runtime failure",
            "tool_calls": [
                {
                    "id": "runtime-fail",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "python - <<'PY'\n"
                            "raise RuntimeError('unsupported runtime opcode')\n"
                            "PY"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a VM runtime from provided source that produces frame.bmp.",
                "max_wall_seconds": 0.2,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "required_patch_model_turn_min_seconds": 0.5,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        timeout=60,
        max_turns=3,
    )

    block = result.metrics["model_turn_budget_block"]
    assert calls == 1
    assert result.status == "blocked"
    assert result.updated_lane_state["finish"]["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert block["required_next"]["kind"] == "patch_or_edit"
    assert block["active_model_timeout_seconds"] < block["minimum_required_model_timeout_seconds"]
    assert result.metrics["model_turns"] == 1


def test_implement_v2_allows_near_threshold_required_patch_turn(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    runtime_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-node-vm-js",
        mew_tool_call_id="tool-verify-node-vm-js",
        tool_name="run_tests",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": "Error: unsupported MIPS syscall 83 at 0x0043da48\n    at VM.syscall (/app/vm.js:564:11)",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "unsupported MIPS syscall 83",
                },
            },
        ),
        evidence_refs=("ev:verify-node-vm-js",),
    )

    near_threshold_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(runtime_failure,),
        run_started=time.monotonic() - 371,
        next_turn=2,
        next_model_timeout_seconds=289,
        requested_timeout=600,
    )
    barely_below_old_threshold_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(runtime_failure,),
        run_started=time.monotonic() - 393,
        next_turn=2,
        next_model_timeout_seconds=267,
        requested_timeout=600,
    )
    material_shortfall_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(runtime_failure,),
        run_started=time.monotonic() - 461,
        next_turn=2,
        next_model_timeout_seconds=199,
        requested_timeout=600,
    )
    generic_runtime_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-generic",
        mew_tool_call_id="tool-verify-generic",
        tool_name="run_tests",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "medium",
                    "summary": "exit code 1",
                },
            },
        ),
        evidence_refs=("ev:verify-generic",),
    )
    generic_material_shortfall_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(generic_runtime_failure,),
        run_started=time.monotonic() - 461,
        next_turn=2,
        next_model_timeout_seconds=199,
        requested_timeout=600,
    )
    generic_runtime_diagnostic_blocks = []
    for summary in ("Runtime failure: exit code 1", "test failed", "verifier failed", "error", "runtime error"):
        generic_runtime_diagnostic = ToolResultEnvelope(
            lane_attempt_id="attempt-1",
            provider_call_id=f"verify-generic-{summary.replace(' ', '-')}",
            mew_tool_call_id=f"tool-verify-generic-{summary.replace(' ', '-')}",
            tool_name="run_tests",
            status="failed",
            is_error=True,
            content=(
                {
                    "command": "node vm.js",
                    "status": "failed",
                    "exit_code": 1,
                    "failure_classification": {
                        "phase": "runtime",
                        "kind": "nonzero_exit",
                        "class": "runtime_failure",
                        "confidence": "medium",
                        "summary": summary,
                    },
                },
            ),
            evidence_refs=(f"ev:{summary}",),
        )
        generic_runtime_diagnostic_blocks.append(
            _required_patch_model_turn_budget_block(
                lane_input,
                lane_attempt_id="attempt-1",
                active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
                hard_runtime_frontier_state={},
                tool_results=(generic_runtime_diagnostic,),
                run_started=time.monotonic() - 461,
                next_turn=2,
                next_model_timeout_seconds=199,
                requested_timeout=600,
            )
        )
    too_short_focused_runtime_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(runtime_failure,),
        run_started=time.monotonic() - 561,
        next_turn=2,
        next_model_timeout_seconds=99,
        requested_timeout=600,
    )

    assert near_threshold_block == {}
    assert barely_below_old_threshold_block == {}
    assert material_shortfall_block == {}
    assert generic_material_shortfall_block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert generic_material_shortfall_block["minimum_required_model_timeout_seconds"] == 300.0
    assert generic_material_shortfall_block["minimum_enforced_model_timeout_seconds"] == 240.0
    assert all(block["failure_class"] == "model_budget_insufficient_for_required_patch" for block in generic_runtime_diagnostic_blocks)
    assert {block["minimum_enforced_model_timeout_seconds"] for block in generic_runtime_diagnostic_blocks} == {240.0}
    assert too_short_focused_runtime_block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert too_short_focused_runtime_block["minimum_enforced_model_timeout_seconds"] == 120.0


def test_implement_v2_allows_short_syntax_error_repair_patch_turn(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    syntax_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-node-vm-js",
        mew_tool_call_id="tool-verify-node-vm-js",
        tool_name="run_tests",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": (
                    "/app/vm.js:464\n"
                    "    let addr = this.sym('DG_ScreenBuffer') || this.sym('screenbuffer') "
                    "|| this.sym'I_VideoBuffer');\n"
                    "                                                                                  ^^^^^^^^^^^^^^^\n"
                    "\n"
                    "SyntaxError: Unexpected string\n"
                    "    at internalCompileFunction (node:internal/vm:76:18)\n"
                ),
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
            },
        ),
        evidence_refs=("ev:verify-node-vm-js",),
    )

    block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(syntax_failure,),
        run_started=time.monotonic() - 424,
        next_turn=9,
        next_model_timeout_seconds=176,
        requested_timeout=600,
    )

    assert block == {}


def test_implement_v2_allows_short_throw_new_error_runtime_repair_patch_turn(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a runtime that produces an output artifact.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    thrown_error_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-node-vm-js",
        mew_tool_call_id="tool-verify-node-vm-js",
        tool_name="run_tests",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": (
                    "if (this.frames < DEFAULT_MAX_FRAMES) "
                    "throw new Error(`program exited before saving a frame; frames=${this.frames}`);"
                ),
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "program exited before saving a frame",
                },
            },
        ),
        evidence_refs=("ev:verify-node-vm-js",),
    )

    block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(thrown_error_failure,),
        run_started=time.monotonic() - 451,
        next_turn=10,
        next_model_timeout_seconds=208,
        requested_timeout=600,
    )

    assert block == {}


@pytest.mark.parametrize(
    "diagnostic",
    [
        "invalid",
        "cannot",
        "panic",
        "assert",
        "traceback",
        "Error:",
        "Exception:",
        "Runtime Error:",
        "throw new Error();",
        pytest.param("no fault injection\ninvalid", id="banner-fault-then-invalid"),
    ],
)
def test_implement_v2_blocks_short_low_detail_runtime_diagnostic_patch_turn(tmp_path, diagnostic: str) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    vague_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-node-vm-js",
        mew_tool_call_id="tool-verify-node-vm-js",
        tool_name="run_tests",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": f"checking runtime output\n{diagnostic}\n",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "medium",
                    "summary": "exit code 1",
                },
            },
        ),
        evidence_refs=("ev:verify-node-vm-js",),
    )

    block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(vague_failure,),
        run_started=time.monotonic() - 424,
        next_turn=9,
        next_model_timeout_seconds=176,
        requested_timeout=600,
    )

    assert block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert block["minimum_enforced_model_timeout_seconds"] == 240.0


def test_implement_v2_allows_short_inspected_artifact_missing_repair_patch_turn(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    write_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="write-vm",
        mew_tool_call_id="tool-write-vm",
        tool_name="write_file",
        status="completed",
        content=({"path": "vm.js", "summary": "source written"},),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": "vm.js",
                "written": True,
            },
        ),
        evidence_refs=("ev:write-vm",),
    )
    no_output_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="verify-node-vm-js",
        mew_tool_call_id="tool-verify-node-vm-js",
        tool_name="run_tests",
        status="interrupted",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "killed",
                "exit_code": None,
                "reason": "implement_v2 hard-runtime verifier had no observable output or expected-artifact progress",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "missing_artifact",
                    "class": "runtime_artifact_missing",
                    "confidence": "high",
                    "summary": "expected artifact missing after no-output verifier",
                    "secondary_kinds": ["interrupted"],
                },
                "execution_contract_normalized": {
                    "role": "runtime",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "affected_paths": ["vm.js"],
                    "expected_artifacts": [{"path": "frame.bmp", "kind": "file", "required": True}],
                },
            },
        ),
        evidence_refs=("ev:verify-node-vm-js",),
    )
    inspect_output = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="inspect-verifier-output",
        mew_tool_call_id="tool-inspect-verifier-output",
        tool_name="read_command_output",
        status="completed",
        content=({"command_run_id": "verify-node-vm-js", "content": "", "status": "completed"},),
        evidence_refs=("ev:inspect-output",),
    )
    read_producer = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="read-vm",
        mew_tool_call_id="tool-read-vm",
        tool_name="read_file",
        status="completed",
        content=({"path": "vm.js", "summary": "Read file vm.js size=100 chars"},),
        evidence_refs=("ev:read-vm",),
    )

    block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={"source": {"target_paths": ["vm.js"]}},
        hard_runtime_frontier_state={},
        tool_results=(write_result, no_output_failure, inspect_output, read_producer),
        run_started=time.monotonic() - 409,
        next_turn=11,
        next_model_timeout_seconds=191,
        requested_timeout=600,
    )

    assert block == {}


def test_implement_v2_allows_short_recovery_hint_write_failure_patch_turn(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    patch_anchor_mismatch = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="patch-anchor-miss",
        mew_tool_call_id="tool-patch-anchor-miss",
        tool_name="apply_patch",
        status="failed",
        is_error=True,
        content=(
            {
                "reason": "edit hunk #1 old text was not found; confirm the exact existing text before retrying",
                "failure_class": "patch_anchor_mismatch",
                "failure_subclass": "patch_exact_match_miss",
                "path": "/app/vm.js",
                "suggested_tool": "read_file/apply_patch/edit_file",
                "suggested_next_action": "retry with exact current source context from patch_anchor_windows",
                "patch_anchor_windows": [
                    {
                        "hunk_index": 1,
                        "nearest_existing_windows": [
                            {
                                "line_start": 32,
                                "line_end": 42,
                                "similarity": 0.42,
                                "text": "chk(a,n){ if ((a>>>0) + n > this.size) throw new Error(); }",
                            }
                        ],
                    }
                ],
                "suggested_recovery_calls": [
                    {
                        "tool_name": "read_file",
                        "path": "/app/vm.js",
                        "offset": 1156,
                        "max_chars": 1120,
                        "reason": "bounded patch anchor recovery; do not read the whole file",
                    }
                ],
            },
        ),
        evidence_refs=("ev:patch-anchor-miss",),
    )

    short_recovery_turn_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={},
        hard_runtime_frontier_state={},
        tool_results=(patch_anchor_mismatch,),
        run_started=time.monotonic() - 468,
        next_turn=21,
        next_model_timeout_seconds=192,
        requested_timeout=600,
    )
    too_short_recovery_turn_block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={},
        hard_runtime_frontier_state={},
        tool_results=(patch_anchor_mismatch,),
        run_started=time.monotonic() - 568,
        next_turn=21,
        next_model_timeout_seconds=92,
        requested_timeout=600,
    )

    assert short_recovery_turn_block == {}
    assert too_short_recovery_turn_block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert too_short_recovery_turn_block["minimum_enforced_model_timeout_seconds"] == 120.0


def test_implement_v2_keeps_full_patch_budget_for_unbounded_write_recovery_hint(tmp_path) -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        model_backend="codex",
        model="gpt-5.5",
        task_contract={
            "description": "Implement a VM runtime from provided source that produces frame.bmp.",
            "max_wall_seconds": 660,
        },
        lane_config={
            "mode": "full",
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "allow_shell": True,
        },
    )
    unbounded_write_failure = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="unbounded-write-fail",
        mew_tool_call_id="tool-unbounded-write-fail",
        tool_name="write_file",
        status="failed",
        is_error=True,
        content=(
            {
                "reason": "write_file would create an unreadable generated source line",
                "failure_class": "source_mutation_unreadable_long_line",
                "failure_subclass": "long_line",
                "path": "/app/vm.js",
                "suggested_tool": "write_file/edit_file",
                "suggested_next_action": "rewrite into readable multi-line source before retrying",
            },
        ),
        evidence_refs=("ev:unbounded-write-fail",),
    )

    block = _required_patch_model_turn_budget_block(
        lane_input,
        lane_attempt_id="attempt-1",
        active_work_todo_state={},
        hard_runtime_frontier_state={},
        tool_results=(unbounded_write_failure,),
        run_started=time.monotonic() - 468,
        next_turn=21,
        next_model_timeout_seconds=192,
        requested_timeout=600,
    )

    assert block["failure_class"] == "model_budget_insufficient_for_required_patch"
    assert block["minimum_enforced_model_timeout_seconds"] == 240.0


def test_implement_v2_live_json_extends_one_reaction_turn_after_final_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "run final compile attempt",
            "tool_calls": [
                {
                    "id": "compile-fail",
                    "name": "run_command",
                    "arguments": {"command": "printf 'compile failed\\n' >&2; exit 2", "cwd": ".", "use_shell": True},
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "make the smallest terminal-failure repair and verify",
            "tool_calls": [
                {
                    "id": "repair-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf fixed > fixed.txt && test \"$(cat fixed.txt)\" = fixed",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "latest terminal failure repaired",
                "acceptance_evidence": ["repair-verify confirmed fixed.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify fixed.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[1]
    assert (tmp_path / "fixed.txt").read_text(encoding="utf-8") == "fixed"


def test_implement_v2_live_json_extends_after_final_closeout_failure(tmp_path) -> None:
    failing_command = "printf 'start\\n'; sleep 0.2; printf 'failed\\n' >&2; exit 2"
    outputs = [
        {
            "summary": "start final command that fails after foreground handoff",
            "tool_calls": [
                {
                    "id": "closeout-fail",
                    "name": "run_command",
                    "arguments": {
                        "command": failing_command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 0,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to the closeout failure",
            "tool_calls": [
                {
                    "id": "repair-after-closeout",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf closeout-repaired > closeout.txt "
                            "&& test \"$(cat closeout.txt)\" = closeout-repaired"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "closeout failure repaired",
                "acceptance_evidence": ["repair-after-closeout confirmed closeout.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify closeout.txt", "max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    manifest = result.updated_lane_state["proof_manifest"]
    assert result.status == "completed"
    assert manifest["tool_results"][0]["status"] == "failed"
    assert result.metrics["command_closeout_count"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[1]
    assert (tmp_path / "closeout.txt").read_text(encoding="utf-8") == "closeout-repaired"


def test_implement_v2_live_json_extends_after_final_diagnostic_of_prior_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "verifier fails before final budget turn",
            "tool_calls": [
                {
                    "id": "failed-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'runtime failed\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "diagnose the failure on the final base turn",
            "tool_calls": [
                {
                    "id": "diagnose-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf diagnostic > diagnostic.txt && test -f diagnostic.txt",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to the unresolved terminal failure",
            "tool_calls": [
                {
                    "id": "repair-after-diagnostic",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf repaired > repaired.txt && test \"$(cat repaired.txt)\" = repaired",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "prior terminal failure repaired after diagnostic",
                "acceptance_evidence": [
                    "diagnose-failure confirmed diagnostic.txt",
                    "repair-after-diagnostic confirmed repaired.txt",
                ],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Diagnose and repair terminal failure"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert (tmp_path / "diagnostic.txt").read_text(encoding="utf-8") == "diagnostic"
    assert (tmp_path / "repaired.txt").read_text(encoding="utf-8") == "repaired"


def test_implement_v2_live_json_extends_after_finish_gate_blocks_with_prior_terminal_failure(tmp_path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("provided source\n", encoding="utf-8")
    outputs = [
        {
            "summary": "runtime verifier still misses the visual artifact",
            "tool_calls": [
                {
                    "id": "runtime-missing-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "read source then incorrectly finish from weak evidence",
            "tool_calls": [{"id": "ground-source", "name": "read_file", "arguments": {"path": "source.txt"}}],
            "finish": {
                "outcome": "completed",
                "summary": "source was grounded",
                "acceptance_evidence": ["ground-source read the provided source"],
            },
        },
        {
            "summary": "react to the prior runtime failure with verifier-shaped proof",
            "tool_calls": [
                {
                    "id": "visual-quality-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'saved /tmp/frame.bmp\\ndimension check passed expected dimensions 640x400\\nreference similarity passed\\n"
                            "removed /tmp/frame.bmp\\n'"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "runtime visual proof completed",
                "acceptance_evidence": [
                    (
                        "visual-quality-proof confirmed expected dimensions 640x400, "
                        "reference similarity, saved /tmp/frame.bmp, and removed /tmp/frame.bmp"
                    )
                ],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Run the VM so it saves rendered frames to /tmp/frame.bmp. "
                    "I will check that the first rendered frame is correct."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "blocked"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["finish_gate_block_count"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert "finish gate blocked completion" in prompts[2]


def test_implement_v2_live_json_extends_after_finish_only_gate_blocks_with_prior_terminal_failure(tmp_path) -> None:
    outputs = [
        {
            "summary": "runtime verifier failed before any finish attempt",
            "tool_calls": [
                {
                    "id": "runtime-failed",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\n' >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "incorrectly finish without new tool evidence",
            "tool_calls": [],
            "finish": {
                "outcome": "completed",
                "summary": "I reasoned about the prior failure",
                "acceptance_evidence": ["no new verifier evidence"],
            },
        },
        {
            "summary": "use the prior terminal failure reaction turn to verify behavior",
            "tool_calls": [
                {
                    "id": "runtime-repair-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf repaired > repaired.txt && test \"$(cat repaired.txt)\" = repaired",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "runtime failure repaired",
                "acceptance_evidence": ["runtime-repair-proof confirmed repaired.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Repair the failed runtime behavior."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 2
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["finish_gate_block_count"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 1/1" in prompts[2]
    assert "finish gate blocked completion" in prompts[2]
    assert (tmp_path / "repaired.txt").read_text(encoding="utf-8") == "repaired"


def test_implement_v2_live_json_grants_progress_continuation_for_new_hard_runtime_frontier(tmp_path) -> None:
    runtime_contract = {
        "role": "runtime",
        "stage": "verification",
        "proof_role": "verifier",
        "acceptance_kind": "external_verifier",
        "expected_artifacts": [{"path": "frame.txt", "checks": [{"exists": True}, {"non_empty": True}]}],
    }
    outputs = [
        {
            "summary": "first runtime frontier still misses frame",
            "tool_calls": [
                {
                    "id": "runtime-miss-pc0",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "second runtime frontier made measurable progress",
            "tool_calls": [
                {
                    "id": "runtime-miss-pc40",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'Program terminated at PC=0x40c848\\nExecuted 4634462 instructions\\n'; exit 2"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "repair after progress continuation",
            "tool_calls": [
                {
                    "id": "runtime-repair",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf frame > frame.txt && test -s frame.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "frame artifact repaired",
                "acceptance_evidence": ["runtime-repair confirmed frame.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and a vm.js runtime harness. Build the source-backed "
                    "runtime artifact so node vm.js writes frame.txt."
                ),
                "final_artifact": "frame.txt",
                "max_wall_seconds": 1800,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 1,
                "hard_runtime_progress_continuation_turns": 1,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 3
    assert result.metrics["terminal_failure_reaction_turn_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 2
    assert result.metrics["hard_runtime_progress_continuation_turns_used"] == 1
    assert result.metrics["model_turns"] == 3
    assert "terminal_failure_reaction_turns_used: 2/2" in prompts[2]
    assert (tmp_path / "frame.txt").read_text(encoding="utf-8") == "frame"


def test_implement_v2_live_json_blocks_progress_continuation_for_identical_hard_runtime_frontier(
    tmp_path,
) -> None:
    runtime_contract = {
        "role": "runtime",
        "stage": "verification",
        "proof_role": "verifier",
        "acceptance_kind": "external_verifier",
        "expected_artifacts": [{"path": "frame.txt", "checks": [{"exists": True}, {"non_empty": True}]}],
    }
    outputs = [
        {
            "summary": "first runtime frontier misses frame",
            "tool_calls": [
                {
                    "id": "runtime-miss-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "same runtime frontier repeats",
            "tool_calls": [
                {
                    "id": "runtime-miss-2",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'Program terminated at PC=0x0\\nExecuted 8 instructions\\n'; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "execution_contract": runtime_contract,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and a vm.js runtime harness. Build the source-backed "
                    "runtime artifact so node vm.js writes frame.txt."
                ),
                "final_artifact": "frame.txt",
                "max_wall_seconds": 1800,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 1,
                "hard_runtime_progress_continuation_turns": 1,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "blocked"
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["hard_runtime_progress_continuation_turns_used"] == 0
    assert result.metrics["model_turns"] == 2
    assert not (tmp_path / "frame.txt").exists()


def test_implement_v2_live_json_extends_after_final_failed_tool_claims_completed(tmp_path) -> None:
    outputs = [
        {
            "summary": "failed terminal result but claims done",
            "tool_calls": [
                {
                    "id": "failed-smoke",
                    "name": "run_command",
                    "arguments": {"command": "printf 'failed\\n' >&2; exit 2", "cwd": ".", "use_shell": True},
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "incorrectly claims completion",
                "acceptance_evidence": ["failed-smoke was enough"],
            },
        },
        {
            "summary": "repair after failed finish",
            "tool_calls": [
                {
                    "id": "repair-after-finish",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf finished > finish.txt && test \"$(cat finish.txt)\" = finished",
                        "cwd": ".",
                        "use_shell": True,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "failed finish repaired",
                "acceptance_evidence": ["repair-after-finish confirmed finish.txt"],
            },
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify finish.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert result.metrics["model_turns"] == 2
    assert (tmp_path / "finish.txt").read_text(encoding="utf-8") == "finished"


def test_implement_v2_live_json_tool_contract_recovery_extends_exactly_one_narrow_turn(tmp_path) -> None:
    outputs = [
        {
            "summary": "wrong verifier surface at final turn",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf recovered > recovered.txt && test \"$(cat recovered.txt)\" = recovered",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "retry exact verifier with run_command",
            "tool_calls": [
                {
                    "id": "corrected-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf recovered > recovered.txt && test \"$(cat recovered.txt)\" = recovered",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "tool contract recovered",
                "acceptance_evidence": ["corrected-verifier confirmed recovered.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify recovered.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first_result = manifest["tool_results"][0]

    assert result.status == "completed"
    assert first_result["status"] == "failed"
    assert first_result["content"][0]["failure_class"] == "tool_contract_misuse"
    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 2
    assert result.metrics["tool_contract_recovery_turns_used"] == 1
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert result.metrics["model_turns"] == 2
    assert "Tool-contract recovery turn" in prompts[1]
    assert "run_tests is argv-only" in prompts[1]
    assert "preserved_command: printf recovered > recovered.txt" in prompts[1]
    assert "If this is a terminal-failure reaction turn" not in prompts[1]
    assert "terminal_failure_reaction_turns_used: 0/" in prompts[1]
    assert (tmp_path / "recovered.txt").read_text(encoding="utf-8") == "recovered"


def test_implement_v2_live_json_run_tests_source_mutation_prompt_requires_split_action(tmp_path) -> None:
    outputs = [
        {
            "summary": "tries to patch through verifier",
            "tool_calls": [
                {
                    "id": "patch-and-verify-in-run-tests",
                    "name": "run_tests",
                    "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('vm.js').write_text('console.log(1)')\n"
                            "PY\n"
                            "node -c vm.js"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {"summary": "saw split-action instruction", "finish": {"outcome": "blocked", "summary": "needs split action"}},
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify vm.js"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = first_result["content"][0]

    assert first_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert len(prompts) == 2
    assert "run_tests_source_mutation" not in prompts[1]
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_live_json_run_tests_source_mutation_does_not_spend_reaction_turn(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "tries to patch through verifier at final turn",
            "tool_calls": [
                {
                    "id": "patch-and-verify-in-run-tests",
                    "name": "run_tests",
                    "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('vm.js').write_text('console.log(1)')\n"
                            "PY\n"
                            "node -c vm.js"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify vm.js"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.metrics["model_turns"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    assert first_result["status"] == "completed"
    assert first_result["content"][0]["tool_route"] == "process_runner"
    assert first_result["content"][0]["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_live_json_run_command_compound_mutation_does_not_spend_reaction_turn(tmp_path) -> None:
    command = "cat > vm.js <<'EOF'\nconsole.log(1)\nEOF\ntest -s vm.js"

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "tries to patch and verify through one run_command",
            "tool_calls": [
                {
                    "id": "patch-and-verify-in-run-command",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "role": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify vm.js"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = first_result["content"][0]

    assert result.metrics["model_turns"] == 1
    assert first_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_live_json_source_scanner_runs_as_process_metadata_not_recovery(tmp_path) -> None:
    (tmp_path / "vm.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    scanner = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('.'):\n"
        "    for name in files:\n"
        "        if name.endswith(('.c', '.h')):\n"
        "            path = os.path.join(root, name)\n"
        "            print(path, open(path).read()[:200])\n"
        "PY"
    )
    outputs = [
        {
            "summary": "tries broad source scanner",
            "tool_calls": [
                {
                    "id": "broad-source-scanner",
                    "name": "run_command",
                    "arguments": {
                        "command": scanner,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Inspect vm.c and patch if needed"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first_result = manifest["tool_results"][0]
    payload = first_result["content"][0]

    assert result.metrics["base_max_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert first_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True
    assert len(manifest["tool_results"]) == 1
    assert len(prompts) == 1


def test_implement_v2_live_json_tool_contract_recovery_does_not_extend_after_later_success(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "wrong verifier then corrected verifier in same turn",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > wrong.txt && test -f wrong.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "corrected-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf ok > ok.txt && test \"$(cat ok.txt)\" = ok",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {
                "outcome": "completed",
                "summary": "corrected verifier succeeded",
                "acceptance_evidence": ["corrected-verifier confirmed ok.txt"],
            },
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Create and verify ok.txt"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["model_turns"] == 1
    assert result.metrics["turn_budget_limit"] == 1
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert not (tmp_path / "wrong.txt").exists()
    assert (tmp_path / "ok.txt").read_text(encoding="utf-8") == "ok"


def test_implement_v2_live_json_tool_contract_misuse_does_not_use_terminal_failure_reaction(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "wrong verifier surface without shell permission",
            "tool_calls": [
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > denied.txt && test -f denied.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Do not run shell verifier"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_verify": True,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    first_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert first_result["status"] == "failed"
    assert first_result["content"][0]["failure_class"] == "tool_contract_misuse"
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 0
    assert result.metrics["turn_budget_limit"] == 1
    assert not (tmp_path / "denied.txt").exists()


def test_implement_v2_live_json_real_terminal_failure_takes_precedence_over_tool_contract_misuse(tmp_path) -> None:
    outputs = [
        {
            "summary": "real failure and wrong verifier surface in same final turn",
            "tool_calls": [
                {
                    "id": "real-terminal-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf real-fail >&2; exit 2",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "wrong-tool-verifier",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf should-not-run > wrong.txt && test -f wrong.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "react to real terminal failure",
            "tool_calls": [
                {
                    "id": "repair-real-failure",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf real-repaired > real.txt && test \"$(cat real.txt)\" = real-repaired",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {
                "outcome": "completed",
                "summary": "real failure repaired",
                "acceptance_evidence": ["repair-real-failure confirmed real.txt"],
            },
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Repair real terminal failure"},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
                "route_run_tests_shell_surface": False,
                "terminal_failure_reaction_min_wall_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.status == "completed"
    assert result.metrics["tool_contract_recovery_turns_used"] == 0
    assert result.metrics["terminal_failure_reaction_turns_used"] == 1
    assert "Tool-contract recovery turn" not in prompts[1]
    assert "If this is a terminal-failure reaction turn" not in prompts[1]
    assert not (tmp_path / "wrong.txt").exists()
    assert (tmp_path / "real.txt").read_text(encoding="utf-8") == "real-repaired"


def test_implement_v2_closeout_preserves_command_timeout(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(3)"])

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start command with shorter command timeout than wall budget",
            "tool_calls": [
                {
                    "id": "call-timeout",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 1,
                        "foreground_budget_seconds": 0.001,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 5},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    content = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert content["timed_out"] is True
    assert content["timeout_seconds"] <= 1
    assert result.metrics["command_closeout_count"] == 1


def test_implement_v2_closeout_config_is_capped_by_remaining_wall_budget(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "import time; print('start', flush=True); time.sleep(3)"])

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start command with closeout config above wall budget",
            "tool_calls": [
                {
                    "id": "call-wall-cap",
                    "name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"max_wall_seconds": 0.1},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "command_closeout_seconds": 5,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    content = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert content["timed_out"] is True
    assert content["timeout_seconds"] < 1
    assert result.metrics["command_closeout_count"] == 1


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
    assert "small complete file" in specs["write_file"].description
    assert "Prefer apply_patch or edit_file" in specs["write_file"].description
    assert specs["edit_file"].dry_run_supported is True
    assert specs["apply_patch"].dry_run_supported is True
    assert specs["apply_patch"].input_transport == "json_line_array"
    assert specs["apply_patch"].preferred_bulk_argument == "patch_lines"
    assert specs["apply_patch"].fallback_bulk_arguments == ("patch", "input")
    assert specs["apply_patch"].provider_native_input_kind == "freeform_apply_patch"


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


def test_implement_v2_history_compacts_large_tool_output_for_next_turn() -> None:
    large_output = "first error\n" + ("warning: noisy linker output\n" * 700) + "final linker error\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="read_command_output",
        status="completed",
        content=(
            {
                "command_run_id": "cmd-1",
                "output_path": "/tmp/output.log",
                "content": large_output,
                "chars": len(large_output),
                "truncated": False,
                "status": "completed",
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
    )

    visible = _provider_visible_tool_result_for_history(result)
    history_content = visible["content"]
    item = history_content["content"][0]

    assert history_content["history_compacted"] is True
    assert item["content_history_chars"] == len(large_output)
    assert item["content_history_truncated"] is True
    assert len(item["content"]) < 3000
    assert "first error" in item["content"]
    assert "final linker error" in item["content"]
    assert history_content["content_refs"] == ["implement-v2-exec://lane-v2-1/cmd-1/output"]


def test_implement_v2_history_projects_terminal_output_to_tails_for_next_turn() -> None:
    noisy_stdout = "first line\n" + ("compiler noise\n" * 600) + "final line\n"
    noisy_stderr = "warning\n" + ("linker warning\n" * 300) + "fatal linker error\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command_run_id": "cmd-1",
                "command": "make very-noisy-target",
                "output_ref": "lane-v2-1/cmd-1/output.log",
                "output_path": "/tmp/mew/hidden/output.log",
                "status": "failed",
                "exit_code": 2,
                "timed_out": False,
                "stdout": noisy_stdout,
                "stderr": noisy_stderr,
                "stdout_tail": "final line\n",
                "stderr_tail": "fatal linker error\n",
                "output_bytes": len(noisy_stdout) + len(noisy_stderr),
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
    )

    visible = _provider_visible_tool_result_for_history(result)
    history_content = visible["content"]
    item = history_content["content"][0]

    assert history_content["history_projected"] is True
    assert item["provider_history_projection"] == "terminal_result_v0"
    assert item["command_run_id"] == "cmd-1"
    assert item["output_ref"] == "lane-v2-1/cmd-1/output.log"
    assert item["exit_code"] == 2
    assert item["stdout_tail"] == "final line\n"
    assert item["stderr_tail"] == "fatal linker error\n"
    assert item["stdout_chars"] == len(noisy_stdout)
    assert item["stderr_chars"] == len(noisy_stderr)
    assert "stdout" not in item
    assert "stderr" not in item
    assert "output_path" not in item
    assert noisy_stdout not in json.dumps(visible)
    assert noisy_stderr not in json.dumps(visible)


def test_implement_v2_history_projects_terminal_side_effects_for_next_turn() -> None:
    noisy_preview = "first symbol\n" + ("large readelf output\n" * 500) + "final symbol\n"
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-probe",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command_run_id": "cmd-1",
                "command": "readelf -s binary",
                "output_ref": "lane-v2-1/cmd-1/output.log",
                "status": "completed",
                "exit_code": 0,
                "timed_out": False,
                "stdout": noisy_preview,
                "stdout_tail": "final symbol\n",
                "output_bytes": len(noisy_preview),
            },
        ),
        content_refs=("implement-v2-exec://lane-v2-1/cmd-1/output",),
        side_effects=(
            {
                "kind": "tool_run_record",
                "record": {
                    "record_id": "tool-run-record:call-probe:1:completed:abc",
                    "command_run_id": "cmd-1",
                    "provider_call_id": "call-probe",
                    "status": "completed",
                    "exit_code": 0,
                    "timed_out": False,
                    "duration_seconds": 0.12,
                    "stdout_ref": "implement-v2-exec://lane-v2-1/cmd-1/stdout",
                    "stderr_ref": "implement-v2-exec://lane-v2-1/cmd-1/stderr",
                    "combined_output_ref": "implement-v2-exec://lane-v2-1/cmd-1/output",
                    "stdout_preview": noisy_preview,
                    "stderr_preview": "",
                    "semantic_exit": {"ok": True, "category": "ok", "message": "any exit accepted"},
                },
            },
            {
                "kind": "failure_classification",
                "record": {
                    "classification_id": "failure:cmd-1",
                    "phase": "unknown",
                    "kind": "unknown_failure",
                    "class": "unknown_failure",
                    "summary": "no structured failure evidence",
                    "required_next_probe": "",
                },
            },
        ),
    )

    visible = _provider_visible_tool_result_for_history(result)
    content = visible["content"]
    serialized = json.dumps(visible)
    side_effects = content["side_effects"]
    tool_run_record = side_effects[0]["record"]

    assert content["side_effects_projected"] is True
    assert tool_run_record["command_run_id"] == "cmd-1"
    assert tool_run_record["stdout_ref"] == "implement-v2-exec://lane-v2-1/cmd-1/stdout"
    assert tool_run_record["semantic_exit"] == {"ok": True, "category": "ok"}
    assert "stdout_preview" not in tool_run_record
    assert "large readelf output" not in serialized
    assert len(serialized) < 5000


def test_implement_v2_history_compacts_older_turns_for_hot_path() -> None:
    large_read = "vm head\n" + ("generated vm body\n" * 600) + "vm tail\n"
    old_result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-read-old-vm",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="read_file",
        status="completed",
        content=(
            {
                "path": "vm.js",
                "content": large_read,
                "chars": len(large_read),
                "summary": "Read file vm.js",
            },
        ),
        content_refs=("implement-v2-read://lane-v2-1/call-read-old-vm/content",),
        evidence_refs=("implement-v2-read://lane-v2-1/call-read-old-vm/evidence",),
    )
    old_call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-read-old-vm",
                "tool_name": "read_file",
                "arguments": {"path": "vm.js"},
            },
        ),
    )[0]
    history = [
        {
            "turn": 1,
            "summary": "Read generated VM after a verifier failure.",
            "tool_calls": [_provider_visible_tool_call_for_history(old_call)],
            "tool_results": [_provider_visible_tool_result_for_history(old_result)],
        }
    ]
    for turn in range(2, 7):
        history.append(
            {
                "turn": turn,
                "summary": f"Recent turn {turn}.",
                "tool_calls": [],
                "tool_results": [],
            }
        )

    rendered = _render_prompt_history_json(history)
    projected = json.loads(rendered)
    old_entry = projected[0]

    assert old_entry["history_compacted"] is True
    assert "tool_calls" not in old_entry
    assert old_entry["tool_results"][0]["content_refs"] == [
        "implement-v2-read://lane-v2-1/call-read-old-vm/content"
    ]
    assert old_entry["tool_results"][0]["evidence_ref_count"] == 1
    assert "generated vm body" not in rendered
    assert "vm tail" not in rendered
    assert projected[-1]["summary"] == "Recent turn 6."


def test_implement_v2_history_projection_preserves_terminal_diagnostics_without_output() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-1",
        provider_call_id="call-1",
        mew_tool_call_id="lane-v2-1:tool:1:1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "status": "failed",
                "reason": "run_command is disabled; pass --allow-shell",
                "error": "unknown command_run_id: cmd-missing",
                "failure_class": "tool_policy_denied",
            },
        ),
    )

    visible = _provider_visible_tool_result_for_history(result)
    item = visible["content"]["content"][0]

    assert item["provider_history_projection"] == "terminal_result_v0"
    assert item["status"] == "failed"
    assert item["reason"] == "run_command is disabled; pass --allow-shell"
    assert item["error"] == "unknown command_run_id: cmd-missing"
    assert item["failure_class"] == "tool_policy_denied"
    assert "stdout" not in item
    assert "stderr" not in item


def test_implement_v2_projects_large_source_mutation_tool_call_arguments_for_history() -> None:
    large_old = "old head\n" + ("old middle\n" * 400) + "old tail\n"
    large_new = "new head\n" + ("new middle\n" * 400) + "new tail\n"
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old_string": large_old, "new_string": large_new},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    args = projected["arguments"]

    assert "patch_lines" not in _PROVIDER_HISTORY_SOURCE_MUTATION_KEYS
    assert args["arguments_projected_for_history"] is True
    assert args["old_string"]["history_text_omitted"] is True
    assert args["new_string"]["history_text_omitted"] is True
    assert args["old_string"]["sha256"] == "sha256:" + hashlib.sha256(large_old.encode()).hexdigest()
    assert args["new_string"]["sha256"] == "sha256:" + hashlib.sha256(large_new.encode()).hexdigest()
    assert large_old not in json.dumps(projected)
    assert large_new not in json.dumps(projected)


def test_implement_v2_projects_source_mutation_alias_arguments_for_history() -> None:
    large_old = "old head\n" + ("old alias middle\n" * 300) + "old tail\n"
    large_new = "new head\n" + ("new alias middle\n" * 300) + "new tail\n"
    large_patch = "*** Begin Patch\n*** Update File: vm.js\n" + ("-a\n+b\n" * 300) + "*** End Patch\n"
    calls = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit-alias",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old": large_old, "new": large_new},
            },
            {
                "provider_call_id": "call-patch-input",
                "tool_name": "apply_patch",
                "arguments": {"input": large_patch},
            },
        ),
    )

    edit_args = _provider_visible_tool_call_for_history(calls[0])["arguments"]
    patch_args = _provider_visible_tool_call_for_history(calls[1])["arguments"]

    assert edit_args["arguments_projected_for_history"] is True
    assert edit_args["old"]["history_text_omitted"] is True
    assert edit_args["new"]["history_text_omitted"] is True
    assert patch_args["arguments_projected_for_history"] is True
    assert patch_args["input"]["history_text_omitted"] is True
    projected_text = json.dumps({"edit": edit_args, "patch": patch_args})
    assert large_old not in projected_text
    assert large_new not in projected_text
    assert large_patch not in projected_text


def test_implement_v2_projects_apply_patch_lines_as_hash_only_for_history() -> None:
    patch_lines = ["*** Begin Patch", "*** Update File: vm.js", "@@"] + ["-old();", "+new();"] * 300 + [
        "*** End Patch"
    ]
    patch_text = "\n".join(patch_lines) + "\n"
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-patch-lines",
                "tool_name": "apply_patch",
                "arguments": {"path": "vm.js", "patch_lines": patch_lines},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    rendered = _render_prompt_history_json(
        [
            {
                "turn": 1,
                "summary": "patch via line-array transport",
                "tool_calls": [projected],
                "tool_results": [],
            }
        ]
    )
    args = projected["arguments"]

    assert args["arguments_projected_for_history"] is True
    expected_projection = {
        "history_text_omitted": True,
        "field": "patch_lines",
        "transport": "patch_lines",
        "operation": "apply_patch",
        "patch_operation": "update_file",
        "paths": ["vm.js"],
        "format": "exact_update_patch_v0",
        "line_count": len(patch_lines),
        "chars": len(patch_text),
        "hash": "sha256:" + hashlib.sha256(patch_text.encode()).hexdigest(),
        "sha256": "sha256:" + hashlib.sha256(patch_text.encode()).hexdigest(),
    }
    for key, value in expected_projection.items():
        assert args["patch_lines"][key] == value
    assert "-old();" not in json.dumps(projected)
    assert "+new();" not in rendered


def test_implement_v2_projects_legacy_apply_patch_string_as_metadata_only_for_history() -> None:
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        + ("-old();\n+new();\n" * 300)
        + "*** End Patch\n"
    )
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-legacy-patch",
                "tool_name": "apply_patch",
                "arguments": {"patch": patch},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    args = projected["arguments"]
    patch_projection = args["patch"]
    rendered = _render_prompt_history_json(
        [
            {
                "turn": 1,
                "summary": "legacy patch string transport",
                "tool_calls": [projected],
                "tool_results": [],
            }
        ]
    )

    assert args["arguments_projected_for_history"] is True
    assert patch_projection["history_text_omitted"] is True
    assert patch_projection["transport"] == "legacy_patch_string"
    assert patch_projection["operation"] == "apply_patch"
    assert patch_projection["patch_operation"] == "update_file"
    assert patch_projection["paths"] == ["vm.js"]
    assert patch_projection["format"] == "exact_update_patch_v0"
    assert patch_projection["line_count"] == len(patch.splitlines())
    assert patch_projection["hash"] == "sha256:" + hashlib.sha256(patch.encode()).hexdigest()
    assert patch_projection["sha256"] == "sha256:" + hashlib.sha256(patch.encode()).hexdigest()
    assert "excerpt" not in patch_projection
    assert "-old();" not in rendered
    assert "+new();" not in json.dumps(projected)


def test_implement_v2_source_mutation_projection_respects_small_clip_limit() -> None:
    content = "A" * 950
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-write",
                "tool_name": "write_file",
                "arguments": {"path": "generated.py", "content": content},
            },
        ),
    )[0]

    args = _provider_visible_tool_call_for_history(call)["arguments"]
    excerpt = args["content"]["excerpt"]

    assert args["content"]["history_text_omitted"] is True
    assert len(excerpt) <= 900
    assert "history clipped -" not in excerpt
    assert args["content"]["sha256"] == "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def test_implement_v2_keeps_small_source_mutation_tool_call_arguments_visible() -> None:
    call = FakeProviderAdapter().normalize_tool_calls(
        lane_attempt_id="lane-v2-1",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-edit",
                "tool_name": "edit_file",
                "arguments": {"path": "vm.js", "old_string": "old();", "new_string": "new();"},
            },
        ),
    )[0]

    projected = _provider_visible_tool_call_for_history(call)
    args = projected["arguments"]

    assert args["old_string"] == "old();"
    assert args["new_string"] == "new();"
    assert "arguments_projected_for_history" not in args


def test_implement_v2_compacts_prompt_history_without_clipping_history_artifact(tmp_path) -> None:
    prompts: list[str] = []
    artifact_dir = tmp_path / "artifacts"
    outputs = [
        {
            "summary": "produce noisy output",
            "tool_calls": [
                {
                    "id": "call-noisy",
                    "name": "run_command",
                    "arguments": {
                        "command": shlex.join(
                            [
                                sys.executable,
                                "-c",
                                "print('first error'); print('warning: noisy output\\n' * 160); print('final linker error')",
                            ]
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "blocked after reading compacted history",
            "finish": {"outcome": "blocked", "summary": "enough evidence"},
        },
    ]

    def fake_model(_backend, _auth, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "artifact_dir": str(artifact_dir),
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    history_path = next(path for path in result.proof_artifacts if path.endswith("history.json"))
    history = json.loads(open(history_path, encoding="utf-8").read())
    persisted_output = history[0]["tool_results"][0]["content"]["content"][0]["stdout"]

    assert result.status == "blocked"
    assert "history_projected" in prompts[1]
    assert "stdout_stderr_body_omitted" in prompts[1]
    assert persisted_output not in prompts[1]
    assert "history_projected" not in persisted_output
    assert "final linker error" in persisted_output
    assert "final linker error" in prompts[1]


def test_implement_v2_compacts_large_write_call_for_prompt_history_only(tmp_path) -> None:
    prompts: list[str] = []
    artifact_dir = tmp_path / "artifacts"
    middle_marker = "UNIQUE_MIDDLE_MARKER_SHOULD_NOT_REACH_NEXT_PROMPT"
    large_content = "module head\n" + ("x = 1\n" * 300) + middle_marker + "\n" + ("y = 2\n" * 300) + "module tail\n"
    outputs = [
        {
            "summary": "write a large generated source file",
            "tool_calls": [
                {
                    "id": "call-write-large",
                    "name": "write_file",
                    "arguments": {
                        "path": "generated.py",
                        "content": large_content,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "blocked after reading compacted write call",
            "finish": {"outcome": "blocked", "summary": "enough evidence"},
        },
    ]

    def fake_model(_backend, _auth, prompt, *_args, **_kwargs):
        prompts.append(prompt)
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "artifact_dir": str(artifact_dir),
                "auto_approve_writes": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    history_path = next(path for path in result.proof_artifacts if path.endswith("history.json"))
    history = json.loads(open(history_path, encoding="utf-8").read())
    persisted_content = history[0]["tool_calls"][0]["arguments"]["content"]

    assert result.status == "blocked"
    assert persisted_content == large_content
    assert "arguments_projected_for_history" not in prompts[1]
    assert "history_text_omitted" not in prompts[1]
    assert "sha256:" + hashlib.sha256(large_content.encode()).hexdigest() not in prompts[1]
    assert middle_marker not in prompts[1]


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
    assert "implement_v2_coding_contract" in by_id
    assert "implement_v2_task_contract" in by_id
    assert "implement_v2_execution_artifact_contract" not in by_id
    assert "implement_v2_tool_surface" not in by_id
    assert "implement_v2_compatibility_frontier" not in by_id
    assert "implement_v2_lane_state" not in by_id
    assert "implement_v2_workframe" not in by_id
    assert "implement_v2_memory_summary" not in by_id
    assert by_id["implement_v2_lane_base"]["cache_hint"] == "cacheable_prefix"
    assert by_id["implement_v2_coding_contract"]["cache_hint"] == "cacheable_prefix"


def test_implement_v2_prompt_metrics_include_workframe_phase1_inventory() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "repair a runtime artifact"},
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {"target_paths": ["vm.js"]},
            },
            "lane_hard_runtime_frontier": {"schema_version": 1, "status": "active"},
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    collapse = metrics["hot_path_collapse"]
    inventory = {section["id"]: section for section in collapse["normal_section_inventory"]}

    assert collapse["schema_version"] == 1
    assert collapse["phase"] == "m6_24_affordance_collapse_phase_1"
    assert collapse["surfaces"]["hot_path_projection"] == "hot_path_projection"
    assert collapse["surfaces"]["resident_sidecar_state"] == "resident_sidecar_state"
    assert collapse["surfaces"]["finish_replay_recovery"] == "finish_replay_recovery"
    assert "normal_full_prompt_bytes" not in collapse
    assert collapse["normal_prompt_section_bytes"] == metrics["total_chars"]
    assert collapse["normal_static_cacheable_bytes"] > 0
    assert collapse["ordinary_resident_summary_bytes"] == 0
    assert collapse["resident_model_visible_bytes"] == 0
    assert inventory["implement_v2_lane_base"]["surface"] == "hot_path_projection"
    assert inventory["implement_v2_coding_contract"]["surface"] == "hot_path_projection"
    assert "implement_v2_workframe" not in inventory
    assert "implement_v2_active_work_todo" not in inventory
    assert "implement_v2_hard_runtime_frontier_state" not in inventory
    assert "implement_v2_repair_history" not in inventory
    assert "implement_v2_execution_artifact_contract" not in inventory
    ordinary_resident_bytes = sum(
        section["bytes"]
        for section in collapse["normal_section_inventory"]
        if section["surface"] == "ordinary_resident_summary"
    )
    assert ordinary_resident_bytes == 0


def test_implement_v2_prompt_sections_omit_probe_fallback_pressure() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "inspect source cheaply"},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_active_coding_rhythm" not in {section.id for section in sections}
    assert "optional CLI such as rg" not in rendered
    assert "source frontier as incomplete" not in rendered
    assert "Use Python fallback only for bounded non-recursive probes" not in rendered
    assert "do not use run_command to generate broad recursive source scanners" not in rendered
    assert "Do not mask a missing probe with `|| true`" not in rendered


def test_implement_v2_prompt_omits_expected_artifact_contract_profile() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"objective": "build and verify an artifact"},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_execution_artifact_contract" not in {section.id for section in sections}
    assert "expected_artifacts" not in rendered
    assert "poll_command inherits the original command's contract" not in rendered
    assert "Mew owns artifact checking" not in rendered


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
            "lane_safe_resume_payload": {"proof_manifest": {"tool_results": ["do-not-leak"]}},
            "lane_safe_scalar_list": ["resume-2", {"frontier": "do-not-leak"}],
        },
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_memory_summary" not in by_id
    assert "implement_v2_lane_state" not in by_id
    assert "memory_summary" not in rendered
    assert "lane_memory_summary" not in rendered
    assert "reentry_memory_refs" not in rendered
    assert "lane_safe_resume_token" not in rendered
    assert "lane_safe_scalar_list" not in rendered
    assert "lane_safe_resume_payload" not in rendered
    assert "do-not-leak" not in rendered


def test_implement_v2_prompt_folds_repair_history_into_workframe_section() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "lane_repair_history": {
                "task": "make-mips-interpreter",
                "avoid_repeated_repairs": ["rewriting vm.js before checking latest PC loop"],
                "next_generic_probe": "inspect latest runtime trace and artifact production path",
            }
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_repair_history" not in by_id
    assert "implement_v2_workframe" not in by_id
    assert "implement_v2_lane_state" not in {section.id for section in sections}
    assert "repair_history" in workframe_debug
    assert "latest runtime trace" in workframe_debug


def test_implement_v2_workframe_section_is_bounded_with_large_repair_history() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={"lane_repair_history": {"log": ['"quoted\\value"' * 2000]}},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_workframe" not in {section.id for section in sections}
    assert len(workframe_debug) <= 4096
    assert "quoted" not in workframe_debug


def test_implement_v2_workframe_omits_nested_repair_history_payloads() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "lane_repair_history": {
                "summary": {"proof_object": {"secret": "do-not-leak"}},
                "notes": [{"evidence": "do-not-leak"}],
                "avoid_repeated_repairs": [{"summary": {"proof_object": "do-not-leak"}}],
                "items": [{"summary": {"evidence": "do-not-leak"}, "failure_kind": "runtime"}],
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_workframe" not in {section.id for section in sections}
    assert "repair_history" in workframe_debug
    assert "proof_object" not in workframe_debug
    assert "do-not-leak" not in workframe_debug


def test_implement_v2_workframe_preserves_active_work_next_action_under_budget() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "active_work_todo": {
                "id": "todo-1",
                "status": "drafting",
                "source": {
                    "plan_item": "inspect and patch " + ("nested runtime source " * 20),
                    "target_paths": [
                        "src/" + ("deep/" * 20) + "vm.js",
                        "tests/" + ("deep/" * 20) + "test_vm.py",
                        "docs/" + ("deep/" * 20) + "notes.md",
                        "extra/" + ("deep/" * 20) + "ignored.md",
                    ],
                    "verify_command": "python -m pytest " + ("--very-long-flag " * 20),
                },
                "first_write_readiness": {
                    "first_write_due": True,
                    "probes_seen_without_write": 4,
                    "required_next_action": "patch the runtime loader before another broad probe " * 10,
                },
                "write_repair": {
                    "failure_kind": "stale_exact_edit" * 20,
                    "path": "src/" + ("nested/" * 20) + "loader.py",
                    "required_next_action": "repair the failed edit against current file text " * 10,
                },
            },
            "lane_hard_runtime_frontier": {
                "latest_runtime_failure": {
                    "failure_class": "runtime_artifact_contract_mismatch" * 5,
                    "stderr_tail": "vm halted after malformed frame output " * 20,
                    "required_next_probe": "compare runtime artifact path and loader ABI " * 10,
                },
            }
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    by_id = {section.id: section for section in sections}
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_active_work_todo" not in by_id
    assert "implement_v2_workframe" not in by_id
    assert len(workframe_debug) <= 4096
    assert "required_next" in workframe_debug
    assert "stale_exact_edit" in workframe_debug
    assert "repair the failed edit" in workframe_debug


def test_implement_v2_workframe_omits_nested_active_work_payloads() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the latest runtime failure."},
        persisted_lane_state={
            "active_work_todo": {
                "source": {
                    "plan_item": {"proof_object": "do-not-leak"},
                    "target_paths": [{"proof_object": "do-not-leak"}, "src/app.py"],
                    "verify_command": {"evidence": "do-not-leak"},
                },
                "blocker": {"recovery_action": {"proof_object": "do-not-leak"}},
                "first_write_readiness": {
                    "first_write_due": True,
                    "required_next_action": {"proof_object": "do-not-leak"},
                },
                "write_repair": {"required_next_action": {"evidence": "do-not-leak"}},
            },
            "lane_hard_runtime_frontier": {
                "latest_runtime_failure": {
                    "required_next_probe": {"frontier": "do-not-leak"},
                    "stderr_tail": "safe bounded failure tail",
                }
            },
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    by_id = {section.id: section for section in sections}
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_active_work_todo" not in by_id
    assert "implement_v2_hard_runtime_frontier_state" not in by_id
    assert "implement_v2_workframe" not in by_id
    assert "safe bounded failure tail" in workframe_debug
    assert "proof_object" not in workframe_debug
    assert "do-not-leak" not in workframe_debug


def test_implement_v2_workframe_omits_full_execution_contract_payloads() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair without exposing sidecar proof payloads."},
        persisted_lane_state={
            "active_work_todo": {
                "source": {
                    "target_paths": ["src/app.py"],
                    "execution_contract": {
                        "id": "contract:do-not-project",
                        "expected_artifacts": [{"id": "artifact:secret", "path": "secret.out"}],
                    },
                },
                "first_write_readiness": {
                    "first_write_due": True,
                    "required_next_action": "patch src/app.py",
                },
            },
            "lane_hard_runtime_frontier": {
                "latest_runtime_failure": {
                    "failure_class": "runtime_failure",
                    "summary": "safe failure summary",
                    "execution_contract": {
                        "id": "contract:frontier-secret",
                        "expected_artifacts": [{"id": "artifact:frontier-secret", "path": "frontier.out"}],
                    },
                }
            },
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_workframe" not in {section.id for section in sections}
    assert "safe failure summary" in workframe_debug
    assert '"execution_contract"' not in workframe_debug
    assert "expected_artifacts" not in workframe_debug
    assert "artifact:secret" not in workframe_debug
    assert "artifact:frontier-secret" not in workframe_debug


def test_implement_v2_prompt_omits_hard_runtime_profile_for_vm_artifact_task() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": (
                "I provided /app/game source code and vm.js expects a game_mips ELF. "
                "Build the source so node vm.js prints stdout appropriately and writes "
                "/tmp/frame.bmp."
            )
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    by_id = {section.id: section for section in sections}

    rendered = "\n".join(section.content for section in sections)
    assert "implement_v2_hard_runtime_profile" not in by_id
    assert "handcrafted stub" not in rendered
    assert "probe only enough ABI/symbol/syscall/output evidence" not in rendered
    assert "implement_v2_hard_runtime_frontier_state" not in by_id
    assert "implement_v2_workframe" not in by_id


def test_implement_v2_hard_runtime_profile_expands_terminal_reaction_budget() -> None:
    hard_runtime_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": (
                "I provided /app/game source code and vm.js expects a game_mips ELF. "
                "Build the source so node vm.js prints stdout appropriately and writes "
                "/tmp/frame.bmp."
            ),
            "max_wall_seconds": 1800,
        },
        lane_config={"mode": "full"},
    )
    simple_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-2",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Fix a small Python unit test."},
        lane_config={"mode": "full"},
    )
    configured_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-3",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract=hard_runtime_input.task_contract,
        lane_config={"mode": "full", "terminal_failure_reaction_turns": 2},
    )
    persisted_frontier_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-4",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Continue a task with persisted lane frontier.", "max_wall_seconds": 1800},
        lane_config={"mode": "full"},
        persisted_lane_state={"lane_hard_runtime_frontier": {"status": "active"}},
    )
    missing_wall_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-5",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": hard_runtime_input.task_contract["description"]},
        lane_config={"mode": "full"},
    )
    invalid_wall_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-6",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": hard_runtime_input.task_contract["description"], "max_wall_seconds": "later"},
        lane_config={"mode": "full"},
    )

    assert _terminal_failure_reaction_turn_limit(simple_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(hard_runtime_input, 24) == 8
    assert _terminal_failure_reaction_turn_limit(persisted_frontier_input, 24) == 8
    assert _terminal_failure_reaction_turn_limit(missing_wall_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(invalid_wall_input, 24) == 3
    assert _terminal_failure_reaction_turn_limit(configured_input, 24) == 2
    assert _hard_runtime_progress_continuation_turn_limit(hard_runtime_input, base_max_turns=24) == 4
    assert _hard_runtime_progress_continuation_turn_limit(simple_input, base_max_turns=24) == 0
    assert _hard_runtime_progress_continuation_turn_limit(missing_wall_input, base_max_turns=24) == 0


def test_implement_v2_hard_runtime_progress_signature_requires_runtime_artifact_progress() -> None:
    frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "final_artifact": {"path": "/tmp/frame.bmp", "status": "failed", "blocking": True},
        "latest_runtime_failure": {
            "failure_class": "runtime_artifact_missing",
            "failure_phase": "runtime",
            "failure_kind": "missing_artifact",
            "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        },
    }
    same_frontier = json.loads(json.dumps(frontier))
    moved_frontier = json.loads(json.dumps(frontier))
    moved_frontier["latest_runtime_failure"]["stdout_tail"] = "Program terminated at PC=0x40d000\nExecuted 5000000"
    artifact_validation_frontier = json.loads(json.dumps(frontier))
    artifact_validation_frontier["latest_runtime_failure"] = {
        "failure_class": "artifact_validation_failure",
        "failure_phase": "unknown",
        "failure_kind": "missing_artifact",
        "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        "required_next_probe": "Inspect the producing substep and artifact path before another rebuild.",
    }
    artifact_validation_build_phase = json.loads(json.dumps(artifact_validation_frontier))
    artifact_validation_build_phase["latest_runtime_failure"]["failure_phase"] = "build"
    nonblocking_artifact_validation = json.loads(json.dumps(artifact_validation_frontier))
    nonblocking_artifact_validation["final_artifact"] = {"path": "/tmp/frame.bmp", "status": "failed"}
    partial_artifact_validation = json.loads(json.dumps(artifact_validation_frontier))
    partial_artifact_validation["final_artifact"] = {"path": "/tmp/frame.bmp", "status": "partial", "blocking": True}
    build_only_frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "latest_build_failure": {"failure_class": "build_failure", "stderr_tail": "undefined reference"},
    }

    signature = _hard_runtime_frontier_progress_signature(frontier)

    assert signature
    assert _hard_runtime_frontier_progress_signature(same_frontier) == signature
    assert _hard_runtime_frontier_progress_signature(moved_frontier) != signature
    assert _hard_runtime_frontier_progress_signature(artifact_validation_frontier)
    assert _hard_runtime_frontier_progress_signature(artifact_validation_build_phase) == ""
    assert _hard_runtime_frontier_progress_signature(nonblocking_artifact_validation) == ""
    assert _hard_runtime_frontier_progress_signature(partial_artifact_validation) == ""
    assert _hard_runtime_frontier_progress_signature(build_only_frontier) == ""


def test_implement_v2_hard_runtime_progress_continuation_rejects_seen_signature() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": "Build provided VM source so node vm.js writes /tmp/frame.bmp.",
            "max_wall_seconds": 1800,
        },
        lane_config={"mode": "full", "terminal_failure_reaction_min_wall_seconds": 0},
    )
    tool_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        content=({"failure_class": "runtime_failure"},),
    )
    frontier = {
        "build_target": {"artifact_path": "/app/game_mips"},
        "final_artifact": {"path": "/tmp/frame.bmp", "status": "failed", "blocking": True},
        "latest_runtime_failure": {
            "failure_class": "runtime_artifact_missing",
            "failure_phase": "runtime",
            "failure_kind": "missing_artifact",
            "stdout_tail": "Program terminated at PC=0x40c848\nExecuted 4634462 instructions",
        },
    }
    seen = {_hard_runtime_frontier_progress_signature(frontier)}

    assert (
        _hard_runtime_progress_continuation_signature(
            lane_input,
            (tool_result,),
            frontier,
            seen_signatures=seen,
            reaction_turns_used=8,
            reaction_turn_limit=8,
            progress_turns_used=0,
            progress_turn_limit=4,
            run_started=time.monotonic(),
        )
        == ""
    )
    assert _hard_runtime_progress_continuation_signature(
        lane_input,
        (tool_result,),
        {
            **frontier,
            "latest_runtime_failure": {
                **frontier["latest_runtime_failure"],
                "stdout_tail": "Program terminated at PC=0x40d000\nExecuted 5000000",
            },
        },
        seen_signatures=seen,
        reaction_turns_used=8,
        reaction_turn_limit=8,
        progress_turns_used=0,
        progress_turn_limit=4,
        run_started=time.monotonic(),
    )


def test_implement_v2_prompt_folds_persisted_frontier_state_into_workframe() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Update docs only."},
        persisted_lane_state={
            "lane_hard_runtime_frontier": {
                "schema_version": 1,
                "status": "active",
                "objective": "preserve source-backed artifact proof",
                "source_roles": [{"path": "vm.js", "role": "runtime_harness", "state": "hypothesis"}],
                "runtime_artifact_contract_mismatch": {
                    "failure_class": "runtime_artifact_contract_mismatch",
                    "required_next_probe": "compare artifact ABI/ISA/endianness/entrypoint",
                },
            }
        },
        lane_config={"mode": "full"},
    )

    metrics = implement_v2_prompt_section_metrics(lane_input)
    by_id = {section["id"]: section for section in metrics["sections"]}
    sections = build_implement_v2_prompt_sections(lane_input)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_hard_runtime_profile" not in by_id
    assert "implement_v2_hard_runtime_frontier_state" not in by_id
    assert "implement_v2_workframe" not in by_id
    assert "implement_v2_lane_state" not in by_id
    assert "lane_hard_runtime_frontier" not in rendered
    assert "runtime_artifact_contract_mismatch" not in rendered
    assert "artifact ABI/ISA/endianness/entrypoint" in workframe_debug
    assert "wf:frontier_failure" in workframe_debug
    assert len(workframe_debug) <= 4096


def test_implement_v2_workframe_uses_runtime_sidecar_before_prompt_frontier() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Implement a VM and satisfy the runtime verifier."},
        lane_config={"mode": "full"},
    )
    runtime_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-runtime-verifier",
        mew_tool_call_id="tool-runtime-verifier",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "latest_failure": {"summary": "exit status 1"},
                "stderr_tail": (
                    "Loaded runtime\n"
                    "Error: memory access 0x00000000+4 outside mapped range\n"
                    "    at CPU.step (/app/vm.js:240:26)\n"
                ),
                "failure_classification": {
                    "class": "runtime_failure",
                    "kind": "nonzero_exit",
                    "summary": "exit code 1",
                },
                "execution_contract_normalized": {
                    "role": "runtime",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "affected_paths": ["vm.js"],
                },
            },
        ),
        evidence_refs=("ev:runtime-verifier",),
        content_refs=("cmd:runtime-output",),
    )
    generic_frontier = {
        "latest_failure": {
            "failure_class": "runtime_failure",
            "summary": "failed",
        }
    }

    runtime_events = _workframe_sidecar_events_from_tool_results((runtime_result,))
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        hard_runtime_frontier=generic_frontier,
        sidecar_events=runtime_events,
    )
    workframe = bundle["reducer_output"]

    assert bundle["invariant_report"]["status"] == "pass"
    assert bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"][0]["event_id"] == (
        "tool-result:call-runtime-verifier"
    )
    assert "prompt-frontier-failure" not in json.dumps(bundle["reducer_inputs"], sort_keys=True)
    assert "memory access 0x00000000+4 outside mapped range" in workframe["latest_actionable"]["summary"]
    assert workframe["required_next"]["kind"] == "patch_or_edit"


def test_implement_v2_workframe_prefers_actionable_terminal_error_line() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    runtime_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-runtime-verifier",
        mew_tool_call_id="tool-runtime-verifier",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": (
                    "/app/vm.js:464\n"
                    "    let addr = this.sym('DG_ScreenBuffer') || this.sym('screenbuffer') "
                    "|| this.sym'I_VideoBuffer');\n"
                    "                                                                                  ^^^^^^^^^^^^^^^\n"
                    "\n"
                    "SyntaxError: Unexpected string\n"
                    "    at internalCompileFunction (node:internal/vm:76:18)\n"
                ),
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
                "execution_contract_normalized": {
                    "role": "runtime",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "affected_paths": ["vm.js"],
                },
            },
        ),
        evidence_refs=("ev:runtime-verifier",),
        content_refs=("cmd:runtime-output",),
    )

    events = _workframe_sidecar_events_from_tool_results((runtime_result,))
    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=events)
    workframe = bundle["reducer_output"]

    assert events[0]["summary"] == "SyntaxError: Unexpected string"
    assert workframe["latest_actionable"]["summary"] == "SyntaxError: Unexpected string"
    assert workframe["required_next"]["kind"] == "patch_or_edit"


def test_implement_v2_workframe_keeps_runtime_failure_after_prompt_recovery() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:runtime",
            "event_sequence": 1,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "TypeError: cannot read property 'pc' of undefined",
            "observable_output": True,
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:runtime"],
        },
    )
    repair_history = {
        "failure_class": "repair_history",
        "required_next_action": "Run one scoped producer/artifact diagnostic before editing again.",
    }

    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        repair_history=repair_history,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert sidecar_events[-1]["event_id"] == "tool-result:runtime"
    assert "Run one scoped producer/artifact diagnostic" in json.dumps(sidecar_events)
    assert workframe["latest_actionable"]["summary"] == "TypeError: cannot read property 'pc' of undefined"
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_extracts_missing_write_target_path() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="patch-missing-target",
        mew_tool_call_id="tool-patch-missing-target",
        tool_name="apply_patch",
        status="failed",
        is_error=True,
        content=(
            {
                "reason": "path does not exist: /app/vm.js; use write_file with --create/create=True to create new files",
            },
        ),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "apply_patch"
    assert events[0]["path"] == "/app/vm.js"
    assert events[0]["target_paths"] == ["/app/vm.js"]
    assert "path does not exist" in events[0]["summary"]


def test_implement_v2_workframe_projects_apply_patch_compact_metadata_only() -> None:
    patch_body = "*** Begin Patch\n*** Update File: vm.js\n@@\n-old();\n+new();\n*** End Patch\n"
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="patch-lines",
        mew_tool_call_id="tool-patch-lines",
        tool_name="apply_patch",
        status="completed",
        is_error=False,
        content=(
            {
                "operation": "apply_patch",
                "path": "/app/vm.js",
                "patch_transport": {
                    "transport": "patch_lines",
                    "operation": "apply_patch",
                    "paths": ["/app/vm.js"],
                    "sha256": "sha256:" + hashlib.sha256(patch_body.encode()).hexdigest(),
                    "line_count": len(patch_body.splitlines()),
                },
            },
        ),
        evidence_refs=("ev:patch-lines",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))
    rendered = json.dumps(events, sort_keys=True)

    assert events[0]["source_mutation"] == {
        "operation": "apply_patch",
        "status": "completed",
        "paths": ["/app/vm.js"],
        "transport": "patch_lines",
        "hash": "sha256:" + hashlib.sha256(patch_body.encode()).hexdigest(),
        "sha256": "sha256:" + hashlib.sha256(patch_body.encode()).hexdigest(),
        "line_count": len(patch_body.splitlines()),
    }
    assert "-old();" not in rendered
    assert "+new();" not in rendered


def test_implement_v2_workframe_projects_patch_anchor_recovery_hint() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current patch failure."},
        lane_config={"mode": "full"},
    )
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="patch-anchor-miss",
        mew_tool_call_id="tool-patch-anchor-miss",
        tool_name="apply_patch",
        status="failed",
        is_error=True,
        content=(
            {
                "reason": "edit hunk #1 old text was not found; confirm the exact existing text before retrying",
                "failure_class": "patch_anchor_mismatch",
                "failure_subclass": "patch_exact_match_miss",
                "path": "/app/vm.js",
                "suggested_tool": "read_file/apply_patch/edit_file",
                "suggested_next_action": (
                    "retry with exact current source context from patch_anchor_windows; if more context is needed, "
                    "run the first suggested_recovery_calls read_file window instead of reading the whole file"
                ),
                "patch_anchor_windows": [
                    {
                        "hunk_index": 1,
                        "nearest_existing_windows": [
                            {
                                "line_start": 405,
                                "line_end": 412,
                                "similarity": 0.276,
                                "text": "case 0x1c: { const funct = ins & 0x3f; }",
                            }
                        ],
                    }
                ],
                "suggested_recovery_calls": [
                    {
                        "tool_name": "read_file",
                        "path": "/app/vm.js",
                        "offset": 18270,
                        "max_chars": 1120,
                        "reason": "bounded patch anchor recovery; do not read the whole file",
                        "line_hint": {"line_start": 385, "line_count": 48},
                    }
                ],
            },
        ),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))
    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=events)
    workframe = bundle["reducer_output"]
    hint = workframe["latest_actionable"]["recovery_hint"]

    assert bundle["invariant_report"]["status"] == "pass"
    assert workframe["latest_actionable"]["family"] == "patch_anchor_mismatch"
    assert workframe["latest_actionable"]["generic_family"] == "write_failure"
    assert hint["failure_subclass"] == "patch_exact_match_miss"
    assert hint["suggested_recovery_call"]["tool_name"] == "read_file"
    assert hint["suggested_recovery_call"]["offset"] == 18270
    assert hint["suggested_recovery_call"]["line_hint"]["line_start"] == 385
    assert hint["current_window"]["line_start"] == 405
    assert "case 0x1c" in hint["current_window"]["text"]
    assert "recovery_hint" in workframe["required_next"]["reason"]


def test_implement_v2_workframe_projects_completed_read_as_inspection() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="read-producer",
        mew_tool_call_id="tool-read-producer",
        tool_name="read_file",
        status="completed",
        is_error=False,
        content=(
            {
                "mew_status": "completed",
                "content": [
                    {
                        "path": "/app/vm.js",
                        "summary": "Read file /app/vm.js size=100 chars",
                    }
                ],
            },
        ),
        evidence_refs=("ev:read-producer",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "inspection"
    assert events[0]["summary"] == "Read file /app/vm.js size=100 chars"
    assert events[0]["target_paths"] == ["/app/vm.js"]
    assert events[0]["evidence_refs"] == ["ev:read-producer"]


def test_implement_v2_workframe_projects_completed_read_command_output_as_inspection() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="read-command-output",
        mew_tool_call_id="tool-read-command-output",
        tool_name="read_command_output",
        status="completed",
        is_error=False,
        content=(
            {
                "mew_status": "completed",
                "content": [
                    {
                        "command_run_id": "cmd-1",
                        "content": "frame_missing=/tmp/frame.bmp",
                        "status": "completed",
                    }
                ],
            },
        ),
        evidence_refs=("ev:read-command-output",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "inspection"
    assert events[0]["summary"] == "read_command_output cmd-1"
    assert events[0]["evidence_refs"] == ["ev:read-command-output"]


def test_implement_v2_workframe_projects_failed_diagnostic_command_as_runtime_failure() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Implement a runtime that writes an artifact."},
        lane_config={"mode": "full"},
    )
    diagnostic_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="diagnose-runtime",
        mew_tool_call_id="tool-diagnose-runtime",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "node vm.js --trace",
                "command_intent": "diagnostic",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": "syscall 1 pc 0x0043adf0\n",
                "stdout_tail": "checked runtime trace\n",
                "execution_contract_normalized": {
                    "id": "contract:diagnose-runtime",
                    "role": "diagnostic",
                    "stage": "diagnostic",
                    "purpose": "diagnostic",
                    "proof_role": "negative_diagnostic",
                    "acceptance_kind": "not_acceptance",
                    "affected_paths": ["vm.js"],
                    "expected_exit": {"mode": "any"},
                },
            },
        ),
        evidence_refs=("ev:diagnose-runtime",),
        content_refs=("cmd:diagnose-runtime",),
    )

    events = _workframe_sidecar_events_from_tool_results((diagnostic_result,))
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        sidecar_events=(
            {
                "kind": "write",
                "event_sequence": 1,
                "event_id": "tool-result:write-vm",
                "status": "completed",
                "path": "vm.js",
                "target_paths": ["vm.js"],
                "evidence_refs": ["ev:write-vm"],
            },
            {
                "kind": "verifier",
                "event_sequence": 2,
                "event_id": "tool-result:verify-vm",
                "status": "failed",
                "family": "runtime_artifact_missing",
                "failure_kind": "missing_artifact",
                "summary": "required artifact /tmp/frame.bmp failed structured checks",
                "evidence_refs": ["ev:verify-vm"],
            },
            {
                "kind": "inspection",
                "event_sequence": 3,
                "event_id": "tool-result:read-vm",
                "status": "completed",
                "target_paths": ["vm.js"],
                "evidence_refs": ["ev:read-vm"],
                "summary": "Read file vm.js",
            },
        )
        + events,
    )
    workframe = bundle["reducer_output"]

    assert events[0]["kind"] == "latest_failure"
    assert events[0]["status"] == "failed"
    assert events[0]["family"] == "runtime_diagnostic"
    assert events[0]["failure_kind"] == "diagnostic_runtime_signal"
    assert events[0]["summary"] == "syscall 1 pc 0x0043adf0"
    assert events[0]["command_intent"] == "diagnostic"
    assert events[0]["target_paths"] == ["vm.js"]
    assert events[0]["evidence_refs"] == ["ev:diagnose-runtime"]
    assert workframe["latest_actionable"]["generic_family"] == "runtime_diagnostic"
    assert workframe["latest_actionable"]["summary"] == "syscall 1 pc 0x0043adf0"
    assert workframe["required_next"]["kind"] == "patch_or_edit"
    assert workframe["required_next"]["target_paths"] == ["vm.js"]


def test_implement_v2_workframe_projects_failed_exception_diagnostic_command_as_runtime_failure() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="diagnose-runtime-exception",
        mew_tool_call_id="tool-diagnose-runtime-exception",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "node vm.js --trace",
                "command_intent": "diagnostic",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": "TypeError: broken runtime state\n",
                "execution_contract_normalized": {
                    "id": "contract:diagnose-runtime-exception",
                    "role": "diagnostic",
                    "stage": "diagnostic",
                    "purpose": "diagnostic",
                    "proof_role": "negative_diagnostic",
                    "acceptance_kind": "not_acceptance",
                    "affected_paths": ["vm.js"],
                    "expected_exit": {"mode": "any"},
                },
            },
        ),
        evidence_refs=("ev:diagnose-runtime-exception",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "latest_failure"
    assert events[0]["status"] == "failed"
    assert events[0]["family"] == "runtime_diagnostic"
    assert events[0]["failure_kind"] == "diagnostic_runtime_signal"
    assert events[0]["summary"] == "TypeError: broken runtime state"
    assert events[0]["target_paths"] == ["vm.js"]


def test_implement_v2_workframe_projects_successful_diagnostic_command_as_inspection() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="diagnose-producer",
        mew_tool_call_id="tool-diagnose-producer",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "node inspect-producer.js",
                "command_intent": "diagnostic",
                "status": "completed",
                "exit_code": 0,
                "stdout_tail": "producer branch inspected; frame writer is reachable\n",
                "execution_contract_normalized": {
                    "id": "contract:diagnose-producer",
                    "role": "diagnostic",
                    "stage": "diagnostic",
                    "purpose": "diagnostic",
                    "proof_role": "negative_diagnostic",
                    "acceptance_kind": "not_acceptance",
                    "affected_paths": ["vm.js"],
                },
            },
        ),
        evidence_refs=("ev:diagnose-producer",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "inspection"
    assert events[0]["status"] == "completed"
    assert events[0]["command_intent"] == "diagnostic"
    assert events[0]["target_paths"] == ["vm.js"]
    assert "producer branch inspected" in events[0]["summary"]


def test_implement_v2_workframe_keeps_progress_build_mutation_as_run_command() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="progress-build",
        mew_tool_call_id="tool-progress-build",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "python generate.py",
                "status": "completed",
                "summary": "generated runtime source",
                "execution_contract_normalized": {
                    "id": "contract:progress-build",
                    "role": "build",
                    "stage": "build",
                    "purpose": "build",
                    "proof_role": "target_build",
                    "acceptance_kind": "progress_only",
                    "affected_paths": ["vm.js"],
                },
            },
        ),
        side_effects=(
            {
                "kind": "source_tree_mutation",
                "record": {
                    "changed_count": 1,
                    "changes": [{"path": "vm.js"}],
                },
            },
        ),
        evidence_refs=("ev:progress-build",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "run_command"
    assert events[0]["target_paths"] == ["vm.js"]
    assert events[0]["summary"] == "generated runtime source"


def test_implement_v2_workframe_surfaces_process_source_observation_paths() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="process-build",
        mew_tool_call_id="tool-process-build",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "python generate.py",
                "status": "completed",
                "summary": "generated runtime source",
                "process_source_observations": [
                    {
                        "kind": "process_source_observation",
                        "changed_count": 1,
                        "changes": [{"path": "vm.js"}],
                        "source_diff_ref": "implement-v2-source-observer://attempt-1/command/source-diff",
                    }
                ],
            },
        ),
        side_effects=(
            {
                "kind": "process_source_observation",
                "record": {
                    "kind": "process_source_observation",
                    "changed_count": 1,
                    "changes": [{"path": "vm.js"}],
                    "source_diff_ref": "implement-v2-source-observer://attempt-1/command/source-diff",
                },
            },
        ),
        evidence_refs=("ev:process-build",),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "run_command"
    assert events[0]["target_paths"] == ["vm.js"]
    assert events[0]["process_source_observation"]["changed_count"] == 1
    assert events[0]["process_source_observation"]["changed_paths"] == ["vm.js"]


def test_implement_v2_workframe_requires_failure_tied_artifact_missing_inspection_before_patch() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Implement a runtime that writes an artifact."},
        lane_config={"mode": "full"},
    )
    base_events = (
        {
            "kind": "write",
            "event_sequence": 1,
            "event_id": "tool-result:write-vm",
            "status": "completed",
            "path": "vm.js",
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:write-vm"],
        },
        {
            "kind": "verifier",
            "event_sequence": 2,
            "event_id": "tool-result:verify-vm",
            "status": "interrupted",
            "family": "runtime_artifact_missing",
            "failure_kind": "missing_artifact",
            "summary": "expected artifact missing after no-output verifier",
            "evidence_refs": ["ev:verify-vm"],
        },
    )
    unrelated_read = {
        "kind": "inspection",
        "event_sequence": 3,
        "event_id": "tool-result:read-readme",
        "status": "completed",
        "target_paths": ["README.md"],
        "evidence_refs": ["ev:read-readme"],
        "summary": "Read file README.md",
    }
    unrelated_bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        sidecar_events=base_events + (unrelated_read,),
    )

    assert unrelated_bundle["reducer_output"]["required_next"]["kind"] == "inspect_latest_failure"

    related_read = {
        "kind": "inspection",
        "event_sequence": 4,
        "event_id": "tool-result:read-vm",
        "status": "completed",
        "target_paths": ["vm.js"],
        "evidence_refs": ["ev:read-vm"],
        "summary": "Read file vm.js",
    }
    related_bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        sidecar_events=base_events + (unrelated_read, related_read),
    )
    required_next = related_bundle["reducer_output"]["required_next"]

    assert required_next["kind"] == "patch_or_edit"
    assert required_next["target_paths"] == ["vm.js"]
    assert required_next["inspection_target_paths"] == ["vm.js"]
    assert required_next["inspection_evidence_refs"] == ["ev:read-vm", "tool-result:read-vm"]


def test_implement_v2_workframe_does_not_extract_missing_path_reason_for_non_write() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="read-missing-target",
        mew_tool_call_id="tool-read-missing-target",
        tool_name="read_file",
        status="failed",
        is_error=True,
        content=(
            {
                "reason": "path does not exist: /app/vm.js",
            },
        ),
    )

    events = _workframe_sidecar_events_from_tool_results((result,))

    assert events[0]["kind"] == "latest_failure"
    assert "target_paths" not in events[0]


def test_implement_v2_workframe_does_not_prompt_override_blocked_write_failure() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    active_work_todo = {
        "write_repair": {
            "schema_version": 1,
            "status": "blocked",
            "failure_kind": "stale_exact_edit",
            "path": "vm.js",
            "required_next_action": "repair vm.js from exact current text",
        }
    }
    runtime_events = (
        {
            "kind": "edit",
            "event_sequence": 1,
            "event_id": "tool-result:edit-miss",
            "status": "failed",
            "family": "edit_exact_match_miss",
            "summary": "old text was not found; confirm the exact existing text before retrying",
            "path": "$WORKSPACE/vm.js",
            "target_paths": ["$WORKSPACE/vm.js"],
            "evidence_refs": ["ev:edit-miss"],
        },
        {
            "kind": "verifier",
            "event_sequence": 2,
            "event_id": "tool-result:verifier-skipped",
            "status": "invalid",
            "family": "runtime_failure",
            "summary": (
                "blocked_by_prior_failed_write_in_same_turn: "
                "edit_file#call-edit-miss ended with status=failed"
            ),
            "evidence_refs": ["ev:invalid-verifier"],
        },
    )

    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        active_work_todo=active_work_todo,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert "prompt-write-repair" not in json.dumps(sidecar_events, sort_keys=True)
    assert workframe["latest_actionable"]["source_ref"] == "ev:edit-miss"
    assert workframe["latest_actionable"]["generic_family"] == "write_failure"
    assert "old text was not found" in workframe["latest_actionable"]["summary"]
    assert workframe["required_next"]["target_paths"] == ["vm.js"]
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_keeps_passing_verifier_after_prompt_recovery() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:passing-verifier",
            "event_sequence": 1,
            "status": "completed",
            "summary": "pytest passed",
            "command_intent": "verify",
            "evidence_refs": ["ev:passing-verifier"],
        },
    )
    repair_history = {
        "failure_class": "repair_history",
        "required_next_action": "Run one scoped producer/artifact diagnostic before editing again.",
    }

    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        repair_history=repair_history,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert sidecar_events[-1]["event_id"] == "tool-result:passing-verifier"
    assert workframe["current_phase"] == "finish_ready"
    assert workframe["latest_actionable"] is None
    assert workframe["required_next"]["kind"] == "finish"
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_keeps_completed_write_after_prompt_recovery() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    write_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-write-file",
        mew_tool_call_id="tool-write-file",
        tool_name="write_file",
        status="completed",
        content=({"path": "vm.js", "summary": "source written"},),
        evidence_refs=("ev:write-file",),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": "vm.js",
                "written": True,
            },
        ),
    )
    repair_history = {
        "failure_class": "repair_history",
        "required_next_action": "Run one scoped producer/artifact diagnostic before editing again.",
    }

    runtime_events = _workframe_sidecar_events_from_tool_results((write_result,))
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        repair_history=repair_history,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert sidecar_events[-1]["kind"] == "write"
    assert sidecar_events[-1]["event_id"] == "tool-result:call-write-file"
    assert workframe["current_phase"] == "verify_after_mutation"
    assert workframe["required_next"]["kind"] == "run_verifier"
    assert workframe["changed_sources"]["paths"] == ["vm.js"]
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_keeps_shell_source_mutation_after_prompt_recovery() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    command_result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-shell-mutation",
        mew_tool_call_id="tool-shell-mutation",
        tool_name="run_command",
        status="completed",
        content=({"command": "python generate.py", "status": "completed", "summary": "generated source"},),
        evidence_refs=("ev:shell-mutation",),
        side_effects=(
            {
                "kind": "source_tree_mutation",
                "record": {
                    "changed_count": 1,
                    "changes": [{"path": "vm.js"}],
                },
            },
        ),
    )
    repair_history = {
        "failure_class": "repair_history",
        "required_next_action": "Run one scoped producer/artifact diagnostic before editing again.",
    }

    runtime_events = _workframe_sidecar_events_from_tool_results((command_result,))
    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        repair_history=repair_history,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert sidecar_events[-1]["kind"] == "run_command"
    assert sidecar_events[-1]["event_id"] == "tool-result:call-shell-mutation"
    assert workframe["current_phase"] == "verify_after_mutation"
    assert workframe["required_next"]["kind"] == "run_verifier"
    assert workframe["changed_sources"]["paths"] == ["vm.js"]
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_allows_recovery_after_trailing_no_output_failure() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair the current verifier failure."},
        lane_config={"mode": "full"},
    )
    runtime_events = (
        {
            "kind": "source_mutation",
            "event_id": "tool-result:source-mutation",
            "event_sequence": 1,
            "status": "completed",
            "path": "vm.js",
            "evidence_refs": ["ev:source-mutation"],
        },
        {
            "kind": "verifier",
            "event_id": "tool-result:no-output-verifier",
            "event_sequence": 2,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "hard-runtime verifier had no observable output",
            "evidence_refs": ["ev:no-output-verifier"],
        },
    )
    repair_history = {
        "failure_class": "no_output_verifier_recovery",
        "required_next_action": "Run one scoped producer/artifact diagnostic before editing again.",
    }

    bundle = build_implement_v2_workframe_debug_bundle(
        lane_input,
        repair_history=repair_history,
        sidecar_events=runtime_events,
    )
    sidecar_events = bundle["reducer_inputs"]["workframe_inputs"]["sidecar_events"]
    workframe = bundle["reducer_output"]

    assert sidecar_events[-1]["event_id"] == "prompt-repair-history"
    assert "Run one scoped producer/artifact diagnostic" in workframe["latest_actionable"]["summary"]
    assert bundle["invariant_report"]["status"] == "pass"


def test_implement_v2_workframe_debug_bundle_accepts_runtime_sidecar_events() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Repair a runtime failure."},
        lane_config={"mode": "full"},
    )
    runtime_events = (
        {
            "kind": "verifier",
            "event_id": "tool-result:call-runtime-verifier",
            "event_sequence": 1,
            "status": "failed",
            "family": "runtime_failure",
            "summary": "Error: memory access 0x00000000+4 outside mapped range",
            "target_paths": ["vm.js"],
            "evidence_refs": ["ev:runtime-verifier"],
        },
    )

    sections = build_implement_v2_prompt_sections(lane_input, workframe_sidecar_events=runtime_events)
    bundle = build_implement_v2_workframe_debug_bundle(lane_input, sidecar_events=runtime_events)
    workframe_debug = json.dumps(bundle["prompt_visible_workframe"], sort_keys=True)

    assert "implement_v2_workframe" not in {section.id for section in sections}
    assert "memory access 0x00000000+4 outside mapped range" in workframe_debug
    assert "wf:frontier_failure" not in workframe_debug
    assert len(workframe_debug) <= 4096


def test_implement_v2_prompt_omits_hard_runtime_profile_for_simple_task() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={"description": "Update the README wording and run markdown checks."},
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)

    assert "implement_v2_hard_runtime_profile" not in {section.id for section in sections}
    assert "implement_v2_hard_runtime_frontier_state" not in {section.id for section in sections}
    assert "implement_v2_workframe" not in {section.id for section in sections}


def test_implement_v2_hard_runtime_profile_not_provider_visible_for_runtime_unknowns() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        task_contract={
            "description": "Implement vm.js so a provided runtime binary writes frame.bmp.",
        },
        lane_config={"mode": "full"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_hard_runtime_profile" not in {section.id for section in sections}
    assert "fail fast" not in rendered
    assert "unsupported opcode/syscall/ABI" not in rendered
    assert "explicit PC/code" not in rendered


def test_implement_v2_prompt_read_only_mode_omits_tool_surface_section() -> None:
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="/tmp/work",
        lane=IMPLEMENT_V2_LANE,
        lane_config={"mode": "read_only"},
    )

    sections = build_implement_v2_prompt_sections(lane_input)
    rendered = "\n".join(section.content for section in sections)

    assert "implement_v2_tool_surface" not in {section.id for section in sections}
    assert "read_file" not in rendered
    assert "search_text" not in rendered
    assert "glob" not in rendered
    assert "git_status" not in rendered
    assert "write_file" not in rendered
    assert "apply_patch" not in rendered


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


def test_implement_v2_search_text_treats_lone_pattern_as_query_alias(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("void DG_DrawFrame(void) {}\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "search_text",
                "arguments": {"path": ".", "pattern": "DG_DrawFrame"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "search evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert any("DG_DrawFrame" in match for match in tool_result["content"][0]["matches"])


def test_implement_v2_search_text_treats_lone_regex_pattern_as_query_alias(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text(
        "void DG_DrawFrame(void) {}\nFILE *fp = fopen(\"/tmp/frame.bmp\", \"wb\");\nfwrite(buf, 1, n, fp);\n",
        encoding="utf-8",
    )

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "search_text",
                "arguments": {"path": ".", "pattern": "DG_|fopen|fwrite"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "regex search evidence ready"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["regex"] is True
    assert any("DG_DrawFrame" in match for match in payload["matches"])
    assert any("/tmp/frame.bmp" in match for match in payload["matches"])


def test_implement_v2_search_text_auto_regexes_regex_like_query(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text(
        "void DG_DrawFrame(void) {}\nFILE *fp = fopen(\"/tmp/frame.bmp\", \"wb\");\nfwrite(buf, 1, n, fp);\n",
        encoding="utf-8",
    )

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "search_text",
                "arguments": {"path": ".", "query": "DG_DrawFrame|fopen|fwrite", "regex": False},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "regex search evidence ready"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["regex"] is True
    assert any("DG_DrawFrame" in match for match in payload["matches"])
    assert any("/tmp/frame.bmp" in match for match in payload["matches"])


def test_implement_v2_search_text_keeps_plain_plus_query_fixed_string(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.txt").write_text("C++ runtime notes\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "search_text",
                "arguments": {"path": ".", "query": "C++"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "literal search evidence ready"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["regex"] is False
    assert payload["matches"] == [f"{tmp_path}/src/main.txt:1:C++ runtime notes"]


def test_implement_v2_glob_accepts_absolute_glob_in_path_argument(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "glob",
                "arguments": {"path": f"{tmp_path}/**/*.c"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "glob evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert any(str(match.get("path")).endswith("src/main.c") for match in tool_result["content"][0]["matches"])


def test_implement_v2_glob_path_alias_still_rejects_outside_workspace(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.c").write_text("int secret(void) { return 1; }\n", encoding="utf-8")

    result = run_fake_read_only_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "read_only"},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "glob",
                "arguments": {"path": f"{outside}/**/*.c"},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "outside glob rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "failed"
    assert tool_result["is_error"] is True
    assert "outside allowed read roots" in tool_result["content"][0]["reason"]


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


def test_implement_v2_exec_attaches_simple_shell_metadata_to_route(tmp_path) -> None:
    command = "printf ok && ls ."

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1, "use_shell": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell metadata ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    classification = payload["command_classification"]
    route_classification = payload["tool_route_decision"]["command_classification"]

    assert tool_result["status"] == "completed"
    assert classification["result"] == "simple"
    assert classification["features"]["base_commands"] == ["printf", "ls"]
    assert classification["features"]["connectors"] == ["&&"]
    assert classification["features"]["read_search_list_hint"] == "list"
    assert classification["not_source_mutation_classifier"] is True
    assert route_classification == classification
    assert payload["tool_route"] == "process_runner"


def test_implement_v2_exec_complex_shell_metadata_fails_closed_without_typed_mutation(tmp_path) -> None:
    command = "printf \"$(date)\""

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1, "use_shell": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "complex shell metadata ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    classification = payload["command_classification"]

    assert tool_result["status"] == "completed"
    assert classification["result"] == "too_complex"
    assert classification["reason"] == "shell_expansion"
    assert classification["shortcut_consumers_enabled"] is False
    assert payload["tool_route"] == "process_runner"
    assert payload["tool_route_decision"]["bridge_registry_id"] == ""
    assert not any("source-mutation" in str(ref) for ref in tool_result.get("evidence_refs", []))


@pytest.mark.parametrize("command", ("echo $FOO", "cat *.py", "echo {a,b}", "cd ~/tmp", "cat <(printf ok)"))
def test_implement_v2_exec_shell_expansion_metadata_fails_closed(tmp_path, command: str) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 1, "foreground_budget_seconds": 0, "use_shell": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "expansion metadata ready"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    classification = payload["command_classification"]

    assert classification["result"] == "too_complex"
    assert classification["reason"] == "shell_expansion"
    assert classification["shortcut_consumers_enabled"] is False


def test_implement_v2_exec_argv_shell_metacharacters_are_metadata_not_shell(tmp_path) -> None:
    command = [sys.executable, "-c", "print('a|b && c > d')"]

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
                "arguments": {"argv": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv metadata ready"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    classification = payload["command_classification"]

    assert payload["command_source"] == "argv"
    assert classification["result"] == "simple"
    assert classification["features"]["use_shell"] is False
    assert classification["features"]["base_commands"] == [Path(sys.executable).name]
    assert "a|b && c > d" in payload["stdout"]


def test_implement_v2_route_bridge_requires_simple_shell_metadata() -> None:
    call = ToolCallEnvelope(
        lane_attempt_id="lane-1",
        provider="fake",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        arguments={"command": "apply_patch <<'PATCH'\n*** Begin Patch\n*** End Patch\nPATCH"},
    )
    result = ToolResultEnvelope(
        lane_attempt_id="lane-1",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        content=(
            {
                "bridge_registry_id": "shell_invoked_apply_patch",
                "command_classification": {
                    "schema_version": 1,
                    "result": "too_complex",
                    "parser": "shell_words",
                    "reason": "heredoc",
                    "command_hash": "sha256:abc",
                    "features": {},
                    "not_source_mutation_classifier": True,
                    "shortcut_consumers_enabled": True,
                },
            },
        ),
    )

    decision = build_tool_route_decision(call, result)
    classification = decision.command_classification.as_dict() if decision.command_classification is not None else {}

    assert decision.tool_route == "invalid_tool_contract"
    assert classification["result"] == "too_complex"
    assert classification["shortcut_consumers_enabled"] is False


@pytest.mark.parametrize(
    "classification_update",
    (
        {"result": "simple", "shortcut_consumers_enabled": "False"},
        {"result": "simple", "schema_version": "bad"},
        {"result": "simple", "schema_version": 1.5},
        {"result": "simple", "schema_version": True},
    ),
)
def test_implement_v2_route_bridge_fails_closed_for_malformed_shell_metadata(
    classification_update: dict[str, object],
) -> None:
    classification = {
        "schema_version": 1,
        "result": "simple",
        "parser": "shell_words",
        "reason": "parsed_plain_command_sequence",
        "command_hash": "sha256:abc",
        "features": {},
        "not_source_mutation_classifier": True,
        "shortcut_consumers_enabled": True,
    }
    classification.update(classification_update)
    call = ToolCallEnvelope(
        lane_attempt_id="lane-1",
        provider="fake",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        arguments={"command": "apply_patch <<'PATCH'\n*** Begin Patch\n*** End Patch\nPATCH"},
    )
    result = ToolResultEnvelope(
        lane_attempt_id="lane-1",
        provider_call_id="call-1",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        content=(
            {
                "bridge_registry_id": "shell_invoked_apply_patch",
                "command_classification": classification,
            },
        ),
    )

    decision = build_tool_route_decision(call, result)

    assert decision.tool_route == "invalid_tool_contract"


def _run_shell_apply_patch_bridge(tmp_path, command: str, *, patch_args: dict[str, object] | None = None):
    args = {
        "command": command,
        "cwd": ".",
        "timeout": 5,
        "foreground_budget_seconds": 1,
    }
    args.update(patch_args or {})
    return run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_write_roots": [str(tmp_path)],
                "auto_approve_writes": True,
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-bridge",
                "tool_name": "run_command",
                "arguments": args,
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "bridge checked"},
    )


def test_implement_v2_shell_apply_patch_bridge_success_routes_typed_mutation(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    route_decision = payload["tool_route_decision"]

    assert tool_result["tool_name"] == "run_command"
    assert tool_result["status"] == "completed"
    assert payload["tool_route"] == "legacy_shell_edit_bridge"
    assert payload["bridge_registry_id"] == "shell_invoked_apply_patch"
    assert payload["bridge_status"] == "applied"
    assert route_decision["declared_tool"] == "run_command"
    assert route_decision["effective_tool"] == "apply_patch"
    assert payload["source_diff_ref"]
    assert payload["typed_evidence_refs"] == tool_result["evidence_refs"]
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('new')\n"


def test_implement_v2_shell_apply_patch_bridge_manifest_has_only_bootstrap_entry() -> None:
    manifest = bridge_registry_manifest()
    bridges = manifest["bridges"]

    assert [bridge["id"] for bridge in bridges] == ["shell_invoked_apply_patch"]


def test_implement_v2_shell_apply_patch_bridge_invalid_patch_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    command = "apply_patch <<'PATCH'\n*** End Patch\nPATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_registry_id"] == "shell_invoked_apply_patch"
    assert payload["bridge_status"] == "rejected"
    assert payload["suggested_tool"] == "apply_patch|edit_file|write_file"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


def test_implement_v2_shell_apply_patch_bridge_ambiguous_multi_file_patch_fails_closed(tmp_path) -> None:
    (tmp_path / "a.py").write_text("a = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("b = 1\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: a.py\n"
        "@@\n"
        "-a = 1\n"
        "+a = 2\n"
        "*** Update File: b.py\n"
        "@@\n"
        "-b = 1\n"
        "+b = 2\n"
        "*** End Patch\n"
    )
    command = f"apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "a.py").read_text(encoding="utf-8") == "a = 1\n"
    assert (tmp_path / "b.py").read_text(encoding="utf-8") == "b = 1\n"


def test_implement_v2_shell_apply_patch_bridge_complex_command_fails_closed_without_shell_execution(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"apply_patch <<'PATCH'\n{patch}PATCH\n&& touch should-not-exist"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"
    assert not (tmp_path / "should-not-exist").exists()


def test_implement_v2_shell_apply_patch_bridge_nested_complex_segment_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"cd . && apply_patch <<'PATCH'\n{patch}PATCH\n&& touch should-not-exist"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"
    assert not (tmp_path / "should-not-exist").exists()


def test_implement_v2_shell_apply_patch_bridge_env_prefixed_segment_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"env FOO=1 apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


def test_implement_v2_shell_apply_patch_bridge_env_unset_segment_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"env -u FOO apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


def test_implement_v2_shell_apply_patch_bridge_path_qualified_segment_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"./apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


@pytest.mark.parametrize("tool_word", ("apply_patch", "./apply_patch"))
def test_implement_v2_shell_apply_patch_bridge_assignment_prefixed_segment_fails_closed(
    tmp_path, tool_word: str
) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"FOO=1 {tool_word} <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


@pytest.mark.parametrize(
    "command_template",
        (
            "( apply_patch <<'PATCH'\n{patch}PATCH )",
            "{{ apply_patch <<'PATCH'\n{patch}PATCH; }}",
            "if true; then apply_patch <<'PATCH'\n{patch}PATCH\nfi",
        ),
)
def test_implement_v2_shell_apply_patch_bridge_grouped_or_control_segment_fails_closed(
    tmp_path, command_template: str
) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = command_template.format(patch=patch)

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


def test_implement_v2_shell_apply_patch_bridge_ignores_heredoc_body_mentions(tmp_path) -> None:
    result = _run_shell_apply_patch_bridge(tmp_path, "cat <<'EOF'\napply_patch\nEOF")
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert "apply_patch" in payload["stdout"]


def test_implement_v2_shell_apply_patch_bridge_parser_unavailable_fails_closed(tmp_path) -> None:
    (tmp_path / "sample.py").write_text("print('old')\n", encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: sample.py\n"
        "@@\n"
        "-print('old')\n"
        "+print('new')\n"
        "*** End Patch\n"
    )
    command = f"apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command, patch_args={"bridge_parser_available": False})
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert payload["command_classification"]["result"] == "unavailable"
    assert (tmp_path / "sample.py").read_text(encoding="utf-8") == "print('old')\n"


def test_implement_v2_shell_apply_patch_bridge_policy_rejection_fails_closed(tmp_path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.py"
    patch = (
        "*** Begin Patch\n"
        f"*** Add File: ../{outside.name}\n"
        "+print('outside')\n"
        "*** End Patch\n"
    )
    command = f"apply_patch <<'PATCH'\n{patch}PATCH"

    result = _run_shell_apply_patch_bridge(tmp_path, command)
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["bridge_status"] == "rejected"
    assert "outside allowed write roots" in payload["reason"]
    assert not outside.exists()


def test_implement_v2_shell_metadata_unavailable_is_not_read_or_edit_safe() -> None:
    classification = classify_shell_command_metadata(
        "rg TODO src",
        command_source="command",
        use_shell=True,
        parser_available=False,
    )

    assert classification["result"] == "unavailable"
    assert classification["reason"] == "parser_not_installed"
    assert classification["shortcut_consumers_enabled"] is False
    assert classification["features"]["read_search_list_hint"] == "unknown"
    assert classification["features"]["process_lifecycle_hint"] == "unknown"
    assert classification["not_source_mutation_classifier"] is True


def test_implement_v2_exec_accepts_cmd_alias(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('cmd-ok')"])

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
                "arguments": {"cmd": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 2},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "command evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["command_source"] == "cmd"
    assert "cmd-ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_no_contract_does_not_inherit_task_artifact_checks(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('diagnostic-ok')"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            task_contract={"expected_artifacts": [{"id": "artifact"}]},
            lane_config={"mode": "exec"},
        ),
        provider_calls=(
            {
                "provider_call_id": "diagnostic",
                "tool_name": "run_command",
                "arguments": {"command": command, "cwd": ".", "timeout": 5, "foreground_budget_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "diagnostic evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert payload["artifact_evidence"] == []
    assert "diagnostic-ok" in payload["stdout"]


def test_implement_v2_exec_probe_intent_downgrades_artifact_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('probe-ok')"])

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
                "provider_call_id": "probe-with-overdeclared-contract",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "command_intent": "probe",
                    "execution_contract": {
                        "id": "contract:overdeclared-probe",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert payload["command_intent"] == "probe"
    assert payload["execution_contract_downgraded"] is True
    assert payload["execution_contract_normalized"]["acceptance_kind"] == "not_acceptance"
    assert payload["execution_contract_normalized"]["proof_role"] == "none"
    assert payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert payload["artifact_evidence"] == []
    assert "probe-ok" in payload["stdout"]


def test_implement_v2_exec_probe_intent_downgrade_survives_poll(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('probe-start', flush=True); time.sleep(0.2); print('probe-done', flush=True)",
        ]
    )
    lane_attempt_id = "implement_v2:ws-1:task-1:exec"
    command_run_id = _expected_command_run_id(
        lane_attempt_id=lane_attempt_id,
        provider_call_id="probe-yield",
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
                "provider_call_id": "probe-yield",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 0.01,
                    "command_intent": "probe",
                    "execution_contract": {
                        "id": "contract:overdeclared-probe-yield",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
            {
                "provider_call_id": "probe-poll",
                "tool_name": "poll_command",
                "arguments": {"command_run_id": command_run_id, "wait_seconds": 1},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "probe evidence ready"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    first_payload = manifest["tool_results"][0]["content"][0]
    poll_payload = manifest["tool_results"][1]["content"][0]

    assert manifest["tool_results"][0]["status"] == "yielded"
    assert manifest["tool_results"][1]["status"] == "completed"
    assert first_payload["execution_contract_downgraded"] is True
    assert poll_payload["execution_contract_downgraded"] is True
    assert poll_payload["execution_contract_normalized"]["acceptance_kind"] == "not_acceptance"
    assert poll_payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert poll_payload["artifact_evidence"] == []
    assert "execution_contract" not in first_payload
    assert "execution_contract" not in poll_payload


def test_implement_v2_exec_poll_checks_runtime_tmp_advertised_artifact(tmp_path) -> None:
    artifact = Path("/tmp") / f"mew-test-{tmp_path.name}-frame.bmp"
    artifact.unlink(missing_ok=True)
    command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import pathlib, time; "
                "p=pathlib.Path(%r); "
                "time.sleep(0.05); "
                "p.write_bytes(b'BMpayload'); "
                "print(f'saved to {p}', flush=True)"
            )
            % str(artifact),
        ]
    )
    lane_attempt_id = "implement_v2:ws-1:task-1:exec"
    command_run_id = _expected_command_run_id(
        lane_attempt_id=lane_attempt_id,
        provider_call_id="tmp-artifact-yield",
    )

    try:
        result = run_fake_exec_implement_v2(
            ImplementLaneInput(
                work_session_id="ws-1",
                task_id="task-1",
                workspace=str(tmp_path),
                lane=IMPLEMENT_V2_LANE,
                lane_config={
                    "mode": "exec",
                    "allow_shell": True,
                    "allowed_read_roots": [str(tmp_path)],
                },
            ),
            provider_calls=(
                {
                    "provider_call_id": "tmp-artifact-yield",
                    "tool_name": "run_tests",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "id": "contract:tmp-runtime-artifact",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                        },
                    },
                },
                {
                    "provider_call_id": "tmp-artifact-poll",
                    "tool_name": "poll_command",
                    "arguments": {"command_run_id": command_run_id, "wait_seconds": 1},
                },
            ),
            finish_arguments={"outcome": "analysis_ready", "summary": "tmp artifact verified"},
        )
    finally:
        artifact.unlink(missing_ok=True)

    manifest = result.updated_lane_state["proof_manifest"]
    first_payload = manifest["tool_results"][0]["content"][0]
    poll_result = manifest["tool_results"][1]
    poll_payload = poll_result["content"][0]

    assert manifest["tool_results"][0]["status"] == "yielded"
    assert poll_result["status"] == "completed"
    assert first_payload["artifact_evidence"] == []
    assert poll_payload["runtime_advertised_expected_artifacts"][0]["path"] == str(artifact)
    assert poll_payload["artifact_evidence"][0]["path"] == str(artifact.resolve(strict=False))
    assert poll_payload["artifact_evidence"][0]["status"] == "passed"
    assert poll_payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_plain_intent_does_not_downgrade_verifier_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('verifier output without artifact')"])

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
                "provider_call_id": "plain-intent-verifier",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "intent": "diagnostic",
                    "execution_contract": {
                        "id": "contract:plain-intent-verifier",
                        "role": "verify",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [{"id": "missing", "kind": "file", "path": "missing.txt"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "verifier evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload.get("execution_contract_downgraded") is not True
    assert payload["execution_contract_normalized"]["acceptance_kind"] == "external_verifier"
    assert payload["execution_contract_normalized"]["expected_artifacts"]
    assert payload["artifact_evidence"][0]["status"] == "failed"


def test_implement_v2_exec_accepts_stdout_expected_artifact_contract(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('ELF 32-bit MSB executable')"])

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
                "provider_call_id": "stdout-contract",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout",
                        "role": "diagnostic",
                        "stage": "diagnostic",
                        "purpose": "diagnostic",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "ELF"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    artifact = payload["execution_contract_normalized"]["expected_artifacts"][0]

    assert tool_result["status"] == "completed"
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert artifact["kind"] == "stdout"
    assert artifact["target"] == {"type": "stream", "stream": "stdout"}
    assert artifact["path"] == ""


def test_implement_v2_exec_diagnostic_stdout_miss_stays_observational(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('different diagnostic output')"])

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
                "provider_call_id": "stdout-diagnostic",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout-diagnostic",
                        "role": "diagnostic",
                        "stage": "diagnostic",
                        "purpose": "diagnostic",
                        "acceptance_kind": "not_acceptance",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "TRACE syscall"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout diagnostic evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["is_error"] is False
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["structured_finish_gate"]["blocked"] is True
    assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_progress_diagnostic_stdout_miss_stays_observational(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('progress diagnostic output')"])

    cases = (
        {"acceptance_kind": "progress_only", "proof_role": "progress"},
        {"acceptance_kind": "progress_only", "proof_role": "negative_diagnostic"},
    )
    for index, contract_case in enumerate(cases, start=1):
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
                    "provider_call_id": f"stdout-progress-diagnostic-{index}",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "id": f"contract:stdout-progress-diagnostic:{index}",
                            "role": "diagnostic",
                            "stage": "diagnostic",
                            "purpose": "diagnostic",
                            "acceptance_kind": contract_case["acceptance_kind"],
                            "proof_role": contract_case["proof_role"],
                            "expected_artifacts": [
                                {
                                    "target": "stdout",
                                    "checks": [
                                        {"kind": "non_empty"},
                                        {"kind": "text_contains", "value": "TRACE syscall"},
                                    ],
                                }
                            ],
                        },
                    },
                },
            ),
            finish_arguments={"outcome": "analysis_ready", "summary": "progress diagnostic evidence ready"},
        )
        tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
        payload = tool_result["content"][0]

        assert tool_result["status"] == "completed"
        assert tool_result["is_error"] is False
        assert payload["artifact_evidence"][0]["status"] == "failed"
        assert payload["structured_finish_gate"]["blocked"] is True
        assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_diagnostic_external_verifier_stdout_miss_still_blocks(tmp_path) -> None:
    command = shlex.join([sys.executable, "-c", "print('different verifier output')"])

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
                "provider_call_id": "stdout-diagnostic-verifier",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:stdout-diagnostic-verifier",
                        "role": "diagnostic",
                        "stage": "verification",
                        "purpose": "verification",
                        "acceptance_kind": "external_verifier",
                        "proof_role": "verifier",
                        "expected_artifacts": [
                            {
                                "target": "stdout",
                                "checks": [
                                    {"kind": "non_empty"},
                                    {"kind": "text_contains", "value": "VERIFIER PASS"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stdout verifier evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert tool_result["is_error"] is True
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["structured_finish_gate"]["blocked"] is True
    assert payload["failure_classification"]["class"] == "artifact_validation_failure"


def test_implement_v2_exec_accepts_argv_argument(tmp_path) -> None:
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
                    "argv": [sys.executable, "-c", "print('argv-ok')"],
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 2,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["command_source"] == "argv"
    assert tool_result["content"][0]["execution_mode"] == "argv"
    assert "argv-ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_exec_compound_command_auto_uses_shell(tmp_path) -> None:
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
                    "command": "echo first && echo second > marker.txt",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 2,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["execution_mode"] == "shell"
    assert "first" in tool_result["content"][0]["stdout"]
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8").strip() == "second"


def test_implement_v2_exec_nonzero_command_blocks_with_paired_failure(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import sys; print('bad-stdout'); print('bad-stderr', file=sys.stderr); sys.exit(7)",
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
    assert "bad-stdout" in tool_result["content"][0]["stdout_tail"]
    assert "bad-stderr" in tool_result["content"][0]["stderr_tail"]


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


def test_implement_v2_exec_attaches_structured_artifact_evidence(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-pass",
                "tool_name": "run_command",
                "arguments": {
                    "command": "printf artifact-ok > artifact.txt",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:artifact-pass",
                        "role": "build",
                        "stage": "build",
                        "purpose": "build",
                        "proof_role": "target_build",
                        "acceptance_kind": "candidate_artifact_proof",
                        "expected_artifacts": [
                            {
                                "id": "artifact",
                                "kind": "file",
                                "path": "artifact.txt",
                                "freshness": "created_after_run_start",
                                "checks": [
                                    {"type": "exists", "severity": "blocking"},
                                    {"text_contains": "artifact-ok", "severity": "blocking"},
                                ],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    side_effect_kinds = {effect["kind"] for effect in tool_result["side_effects"]}

    assert tool_result["status"] == "completed"
    assert "implement-v2-evidence://" in " ".join(tool_result["evidence_refs"])
    assert payload["command_run"]["command_run_id"] == payload["tool_run_record"]["command_run_id"]
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert payload["verifier_evidence"]["verdict"] == "pass"
    assert payload["structured_finish_gate"]["blocked"] is False
    assert {
        "command_run",
        "tool_run_record",
        "artifact_evidence",
        "verifier_evidence",
        "failure_classification",
        "structured_finish_gate",
    } <= side_effect_kinds


def test_implement_v2_finish_gate_projects_prior_source_grounding_into_structured_finish(tmp_path) -> None:
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    source = source_dir / "source.c"
    source.write_text("int main(void) { return 0; }\n", encoding="utf-8")
    outputs = [
        {
            "summary": "ground provided source before runtime proof",
            "tool_calls": [{"id": "read-source", "name": "read_file", "arguments": {"path": "src/source.c"}}],
            "finish": {"outcome": "continue"},
        },
        {
            "summary": "final verifier proves the runtime artifact",
            "tool_calls": [
                {
                    "id": "final-runtime-proof",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'FRAME_QUALITY_OK\\n' > frame.bmp",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "id": "contract:runtime-artifact",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [
                                        {"type": "exists", "severity": "blocking"},
                                        {"type": "text_contains", "text": "FRAME_QUALITY_OK", "severity": "blocking"},
                                    ],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "completed", "summary": "runtime artifact verified"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided src/source.c, the corresponding source code. "
                    "Build the source-backed runtime artifact so it writes frame.bmp."
                ),
                "final_artifact": "frame.bmp",
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert result.status == "completed"
    assert result.metrics["finish_gate_block_count"] == 0
    assert (tmp_path / "frame.bmp").read_text(encoding="utf-8") == "FRAME_QUALITY_OK\n"


def test_implement_v2_typed_finish_refs_reserve_source_grounding_slots() -> None:
    early_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"early-{index}",
            mew_tool_call_id=f"tool-early-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:early-{index}",
                            "artifact_id": f"early-{index}",
                            "path": f"early-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"path": "src/source.c", "summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )
    final_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="final-proof",
        mew_tool_call_id="tool-final",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract_normalized": {
                    "id": "contract:runtime-artifact",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "expected_artifacts": [
                        {"id": "frame", "path": "frame.bmp", "required": True},
                    ],
                    "verifier_required": True,
                },
                "artifact_evidence": [
                    {
                        "evidence_id": "artifact-evidence:frame",
                        "artifact_id": "frame",
                        "path": "frame.bmp",
                        "contract_id": "contract:runtime-artifact",
                        "status": "passed",
                        "blocking": False,
                    }
                ],
                "verifier_evidence": {
                    "verifier_id": "verifier:runtime-artifact",
                    "contract_id": "contract:runtime-artifact",
                    "verdict": "pass",
                },
            },
        ),
    )

    refs = _typed_finish_evidence_refs(
        (*early_results, source_result, final_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    ref_ids = {str(ref.get("id") or "") for ref in refs}
    assert "ev:artifact:artifact-evidence:frame" in ref_ids
    assert "ev:verifier:verifier:runtime-artifact" in ref_ids
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert len(refs) <= 16


def test_implement_v2_typed_finish_refs_reserve_source_grounding_slots_in_fallback() -> None:
    early_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"early-{index}",
            mew_tool_call_id=f"tool-early-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:early-{index}",
                            "artifact_id": f"early-{index}",
                            "path": f"early-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )

    refs = _typed_finish_evidence_refs(
        (*early_results, source_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    ref_ids = {str(ref.get("id") or "") for ref in refs}
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert len(refs) <= 16


def test_implement_v2_finish_action_merges_typed_refs_into_existing_model_refs() -> None:
    stale_results = tuple(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id=f"stale-{index}",
            mew_tool_call_id=f"tool-stale-{index}",
            tool_name="run_command",
            status="completed",
            content=(
                {
                    "artifact_evidence": [
                        {
                            "evidence_id": f"artifact-evidence:stale-{index}",
                            "artifact_id": f"stale-{index}",
                            "path": f"stale-{index}.txt",
                            "status": "passed",
                            "blocking": False,
                        }
                    ]
                },
            ),
        )
        for index in range(20)
    )
    source_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="read-source",
        mew_tool_call_id="tool-source",
        tool_name="read_file",
        status="completed",
        content=({"path": "src/source.c", "summary": "read src/source.c", "text": "int main(void) { return 0; }\n"},),
    )
    final_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="final-proof",
        mew_tool_call_id="tool-final",
        tool_name="run_command",
        status="completed",
        content=(
            {
                "execution_contract_normalized": {
                    "id": "contract:runtime-artifact",
                    "role": "runtime",
                    "stage": "verification",
                    "proof_role": "verifier",
                    "acceptance_kind": "external_verifier",
                    "expected_artifacts": [
                        {"id": "frame", "path": "frame.bmp", "required": True},
                    ],
                    "verifier_required": True,
                },
                "artifact_evidence": [
                    {
                        "evidence_id": "artifact-evidence:frame",
                        "artifact_id": "frame",
                        "path": "frame.bmp",
                        "contract_id": "contract:runtime-artifact",
                        "status": "passed",
                        "blocking": False,
                    }
                ],
                "verifier_evidence": {
                    "verifier_id": "verifier:runtime-artifact",
                    "contract_id": "contract:runtime-artifact",
                    "verdict": "pass",
                },
            },
        ),
    )

    action = _finish_acceptance_action(
        {
            "outcome": "completed",
            "summary": "done",
            "evidence_refs": [
                {"kind": "evidence_event", "id": f"ev:artifact:artifact-evidence:stale-{index}"}
                for index in range(20)
            ],
        },
        (*stale_results, source_result, final_result),
        task_description=(
            "I provided src/source.c, the corresponding source code. "
            "Build the source-backed runtime artifact so it writes frame.bmp."
        ),
    )

    refs = action["evidence_refs"]
    ref_ids = [str(ref.get("id") or "") for ref in refs if isinstance(ref, dict)]
    assert "ev:artifact:artifact-evidence:frame" in ref_ids
    assert "ev:verifier:verifier:runtime-artifact" in ref_ids
    assert "ev:source:src/source.c:read-source" in ref_ids
    assert "ev:artifact:artifact-evidence:stale-0" in ref_ids
    assert ref_ids.index("ev:artifact:artifact-evidence:frame") < ref_ids.index("ev:artifact:artifact-evidence:stale-0")
    assert len(refs) <= 16


def test_implement_v2_exec_missing_expected_artifact_blocks_result(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-missing",
                "tool_name": "run_command",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "any"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame.bmp",
                                "freshness": "created_after_run_start",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence missing"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["exit_code"] == 0
    assert payload["tool_run_record"]["semantic_exit"]["ok"] is True
    assert payload["artifact_evidence"][0]["status"] == "failed"
    assert payload["verifier_evidence"]["verdict"] == "fail"
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"
    assert payload["structured_finish_gate"]["blocked"] is True


def test_implement_v2_exec_runs_when_expected_artifact_is_outside_allowed_roots(tmp_path) -> None:
    outside = tmp_path.parent / "outside-frame.bmp"
    command = shlex.join([sys.executable, "-c", "import sys; print('runtime-ran'); sys.exit(7)"])

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "final_artifact": {"path": str(outside), "kind": "file"},
                }
            },
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "outside-artifact-verifier",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-outside-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": str(outside),
                                "freshness": "created_after_run_start",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "runtime evidence ready"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["exit_code"] == 7
    assert "runtime-ran" in payload["stdout"]
    assert payload["execution_contract_normalized"]["expected_artifacts"] == []
    assert payload["artifact_evidence"] == []
    assert payload["unchecked_expected_artifacts"][0]["path"] == str(outside)
    assert "outside allowed roots" in payload["unchecked_expected_artifacts"][0]["reason"]
    assert payload["failure_classification"]["class"] == "runtime_failure"

    projected = _provider_visible_tool_result_for_history(
        ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id="outside-artifact-verifier",
            mew_tool_call_id="tool-1",
            tool_name="run_command",
            status=tool_result["status"],
            is_error=tool_result["is_error"],
            content=tuple(tool_result["content"]),
            content_refs=tuple(tool_result["content_refs"]),
            evidence_refs=tuple(tool_result["evidence_refs"]),
            side_effects=tuple(tool_result["side_effects"]),
        )
    )["content"]["content"][0]
    unchecked = projected["execution_evidence_digest"]["unchecked_expected_artifacts"][0]
    assert unchecked["path"] == str(outside)
    assert "required_next_action" not in unchecked


def test_implement_v2_exec_blocks_runtime_advertised_artifact_path_mismatch(tmp_path) -> None:
    external_path = tmp_path / "external" / "frame.bmp"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-path-mismatch",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'Frames will be saved to {external_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "freshness": "created_after_run_start",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact path mismatch"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]
    artifact_paths = [item["path"] for item in payload["artifact_evidence"]]

    assert tool_result["status"] == "failed"
    assert str(external_path) in artifact_paths
    assert payload["runtime_advertised_expected_artifacts"][0]["path"] == str(external_path)
    assert payload["artifact_evidence"][0]["path"].endswith("frame_000000.bmp")
    assert payload["artifact_evidence"][0]["status"] == "passed"
    assert payload["artifact_evidence"][1]["path"] == str(external_path)
    assert payload["artifact_evidence"][1]["status"] == "failed"
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"
    assert payload["structured_finish_gate"]["blocked"] is True


def test_implement_v2_exec_ignores_unrelated_advertised_artifact_suffix(tmp_path) -> None:
    log_path = tmp_path / "logs" / "runtime.log"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-path-log",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'debug log written to {log_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact path log ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "frame_000000.bmp")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_ignores_nonproducer_report_output_path(tmp_path) -> None:
    report_path = tmp_path / "reports" / "result.json"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "nonproducer-report-path",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'pytest report output: {report_path}\\n'; "
                        "printf '{\"ok\": true}' > result.json"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-report",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "result",
                                "kind": "json",
                                "path": "result.json",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "report output path ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "result.json")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_ignores_printf_template_advertised_artifact_path(tmp_path) -> None:
    template_path = tmp_path / "frames" / "frame_%06d.bmp"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "template-artifact-path",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf '%s\\n' 'Frames will be saved to {template_path}'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact-template",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "template path ignored"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"
    assert payload.get("runtime_advertised_expected_artifacts") is None
    assert [item["path"] for item in payload["artifact_evidence"]] == [str(tmp_path / "frame_000000.bmp")]
    assert payload["structured_finish_gate"]["blocked"] is False


def test_implement_v2_exec_blocks_stale_runtime_advertised_artifact(tmp_path) -> None:
    external_path = tmp_path / "external" / "frame.bmp"
    external_path.parent.mkdir()
    external_path.write_text("stale", encoding="utf-8")
    time.sleep(0.01)
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "stale-advertised-artifact",
                "tool_name": "run_command",
                "arguments": {
                    "command": (
                        f"printf 'Frames will be saved to {external_path}\\n'; "
                        "printf 'BMpayload' > frame_000000.bmp"
                    ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "zero"},
                        "expected_artifacts": [
                            {
                                "id": "frame",
                                "kind": "file",
                                "path": "frame_000000.bmp",
                                "checks": [{"type": "exists", "severity": "blocking"}],
                            }
                        ],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stale artifact path blocked"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    advertised = payload["artifact_evidence"][1]
    mtime_check = [check for check in advertised["checks"] if check["type"] == "mtime_after"][0]

    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "failed"
    assert advertised["path"] == str(external_path)
    assert advertised["status"] == "failed"
    assert mtime_check["passed"] is False
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"


def test_implement_v2_provider_history_surfaces_structured_evidence_summary(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "artifact-missing",
                "tool_name": "run_command",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:runtime-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "any"},
                        "expected_artifacts": [{"id": "frame", "kind": "file", "path": "frame.bmp"}],
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact evidence missing"},
    )
    tool_result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="artifact-missing",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"]),
        content_refs=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["content_refs"]),
        evidence_refs=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]),
        side_effects=tuple(result.updated_lane_state["proof_manifest"]["tool_results"][0]["side_effects"]),
    )

    history = _provider_visible_tool_result_for_history(tool_result)
    projected = history["content"]["content"][0]

    assert projected["latest_failure"]["class"] == "runtime_artifact_missing"
    assert "required_next_action" not in projected["latest_failure"]
    assert projected["execution_evidence_digest"]["artifact_miss"][0]["artifact_id"] == "frame"
    assert projected["execution_evidence_digest"]["structured_finish_gate"]["blocked"] is True
    assert "structured_execution_evidence" not in projected
    assert "evidence_refs" not in projected["execution_evidence_digest"]["structured_finish_gate"]
    assert "stdout_stderr_body_omitted" not in projected["execution_evidence_digest"]


def test_implement_v2_provider_history_uses_terminal_diagnostic_for_generic_runtime_failure() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-runtime-fail",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr": (
                    "TypeError: this.check is not a function\n"
                    "    at m.write32 (/app/vm.js:182:37)\n"
                    "    at MIPSVM.setupStack (/app/vm.js:191:23)\n"
                ),
                "stderr_tail": (
                    "TypeError: this.check is not a function\n"
                    "    at m.write32 (/app/vm.js:182:37)\n"
                ),
                "output_ref": "cmd/output",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    projected = history["content"]["content"][0]
    latest_failure = projected["latest_failure"]

    assert latest_failure["class"] == "runtime_failure"
    assert latest_failure["summary"] == "TypeError: this.check is not a function"
    assert "required_next_action" not in latest_failure
    assert projected["stderr_tail"].startswith("TypeError: this.check is not a function")


def test_implement_v2_provider_history_skips_traceback_context_for_runtime_summary() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-python-runtime-fail",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "python verify.py",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": (
                    "Traceback (most recent call last):\n"
                    "  File \"/app/verify.py\", line 2, in <module>\n"
                    "    foo()\n"
                    "TypeError: broken runtime state\n"
                ),
                "output_ref": "cmd/output",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    latest_failure = history["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "TypeError: broken runtime state"


def test_implement_v2_provider_history_uses_full_stderr_when_tail_is_only_stack_context() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-tail-stack-only",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr": (
                    "RuntimeError: root cause before long stack\n"
                    "    at generated (/app/vm.js:1:1)\n"
                ),
                "stderr_tail": "    at finalFrame (/app/vm.js:999:1)\n    at node:internal/main\n",
                "output_ref": "cmd/output",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    latest_failure = history["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "RuntimeError: root cause before long stack"


def test_implement_v2_provider_history_skips_banner_before_runtime_diagnostic() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-banner-before-error",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "node vm.js",
                "status": "failed",
                "exit_code": 1,
                "stderr_tail": (
                    "MIPS ELF entry=0x00400110 endian=le DG_DrawFrame=0x004395e4\n"
                    "Error: unsupported special fn 52 ins 0x00e001f4 at 0x00439e3c\n"
                    "    at step (/app/vm.js:306:24)\n"
                ),
                "output_ref": "cmd/output",
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "nonzero_exit",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "exit code 1",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    latest_failure = history["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "Error: unsupported special fn 52 ins 0x00e001f4 at 0x00439e3c"


def test_implement_v2_provider_history_uses_artifact_miss_for_killed_runtime_verifier() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-killed-runtime",
        mew_tool_call_id="tool-1",
        tool_name="run_tests",
        status="interrupted",
        is_error=True,
        content=(
            {
                "command": "MAX_FRAMES=1 node vm.js",
                "status": "killed",
                "stderr_tail": "MIPS ELF entry=0x00400110 endian=le\n",
                "reason": "verifier auto-poll budget exhausted before terminal evidence",
                "artifact_evidence": [
                    {
                        "artifact_id": "/app/frames/frame_000000.ppm",
                        "path": "/app/frames/frame_000000.ppm",
                        "kind": "file",
                        "status": "failed",
                        "blocking": True,
                    }
                ],
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "killed",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "tool run tool-run-record:call-killed-runtime:2:interrupted ended with killed",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    latest_failure = history["content"]["content"][0]["latest_failure"]

    assert latest_failure["class"] == "runtime_failure"
    assert latest_failure["summary"] == "required artifact missing: /app/frames/frame_000000.ppm"
    assert latest_failure["path"] == "/app/frames/frame_000000.ppm"
    assert "required_next_action" not in latest_failure


def test_implement_v2_provider_history_prefers_error_over_artifact_miss_for_killed_runtime() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-killed-runtime-with-error",
        mew_tool_call_id="tool-1",
        tool_name="run_tests",
        status="interrupted",
        is_error=True,
        content=(
            {
                "command": "MAX_FRAMES=1 node vm.js",
                "status": "killed",
                "stderr_tail": (
                    "MIPS ELF entry=0x00400110 endian=le\n"
                    "Error: unsupported syscall 4242 at 0x00401000\n"
                ),
                "artifact_evidence": [
                    {
                        "artifact_id": "/app/frames/frame_000000.ppm",
                        "path": "/app/frames/frame_000000.ppm",
                        "kind": "file",
                        "status": "failed",
                        "blocking": True,
                    }
                ],
                "failure_classification": {
                    "phase": "runtime",
                    "kind": "killed",
                    "class": "runtime_failure",
                    "confidence": "high",
                    "summary": "tool run tool-run-record:call-killed-runtime:2:interrupted ended with killed",
                },
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=("evidence/runtime",),
    )

    history = _provider_visible_tool_result_for_history(result)
    latest_failure = history["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "Error: unsupported syscall 4242 at 0x00401000"
    assert latest_failure["path"] == "/app/frames/frame_000000.ppm"
    assert "required_next_action" not in latest_failure


def test_implement_v2_prompt_history_does_not_project_generic_runtime_exit_code_only() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "runtime verifier failed",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-fail",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-1",
                                "output_ref": "out-1",
                                "stderr_tail": (
                                    "Error: unsupported opcode=58 at pc=0x00400110\n"
                                    "    at MIPSVM.fail (/app/vm.js:178:11)\n"
                                ),
                                "failure_classification": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "confidence": "high",
                                    "summary": "exit code 1",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    latest_failure = rendered[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "Error: unsupported opcode=58 at pc=0x00400110"
    assert latest_failure["summary"] != "exit code 1"


def test_implement_v2_prompt_history_does_not_project_generic_killed_runtime_only() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "runtime verifier was interrupted",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-killed",
                    "tool_name": "run_tests",
                    "status": "interrupted",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-1",
                                "output_ref": "out-1",
                                "stderr_tail": "MIPS ELF entry=0x00400110 endian=le\n",
                                "artifact_evidence": [
                                    {
                                        "artifact_id": "/app/frames/frame_000000.ppm",
                                        "path": "/app/frames/frame_000000.ppm",
                                        "kind": "file",
                                        "status": "failed",
                                        "blocking": True,
                                    }
                                ],
                                "failure_classification": {
                                    "phase": "runtime",
                                    "kind": "killed",
                                    "class": "runtime_failure",
                                    "confidence": "high",
                                    "summary": (
                                        "tool run tool-run-record:call-runtime-killed:2:interrupted ended with killed"
                                    ),
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    latest_failure = rendered[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]

    assert latest_failure["summary"] == "required artifact missing: /app/frames/frame_000000.ppm"
    assert "ended with killed" not in latest_failure["summary"]
    assert latest_failure["path"] == "/app/frames/frame_000000.ppm"


def test_implement_v2_prompt_history_keeps_only_latest_same_family_failure() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "first failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-1",
                                "output_ref": "out-1",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "old artifact miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "newer failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-2",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-2",
                                "output_ref": "out-2",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "new artifact miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    first_result = rendered[0]["tool_results"][0]
    second_item = rendered[1]["tool_results"][0]["content"]["content"][0]

    assert rendered[0]["history_compacted"] is True
    assert "content" not in first_result
    assert "latest_failures" not in first_result
    assert second_item["latest_failure"]["summary"] == "new artifact miss"
    assert prompt_history[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"] == "old artifact miss"


def test_implement_v2_prompt_history_keeps_only_latest_turn_full() -> None:
    prompt_history = [
        {
            "turn": turn,
            "summary": f"turn {turn}",
            "tool_calls": [
                {
                    "provider_call_id": f"call-{turn}",
                    "tool_name": "run_command",
                    "arguments": {"command": "python - <<'PY'\nprint('large probe')\nPY"},
                }
            ],
            "tool_results": [
                {
                    "provider_call_id": f"call-{turn}",
                    "tool_name": "run_command",
                    "status": "completed",
                    "is_error": False,
                    "content": {
                        "content_refs": [f"out-{turn}"],
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": f"cmd-{turn}",
                                "output_ref": f"out-{turn}",
                                "stdout_tail": "probe output",
                            }
                        ],
                    },
                }
            ],
        }
        for turn in range(1, 6)
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))

    assert [entry["turn"] for entry in rendered] == [1, 2, 3, 4, 5]
    assert [entry.get("history_compacted", False) for entry in rendered] == [True, True, True, True, False]
    assert rendered[0]["tool_results"][0]["content_refs"] == ["out-1"]
    assert "content" not in rendered[0]["tool_results"][0]
    assert rendered[-1]["tool_results"][0]["content"]["content"][0]["stdout_tail"] == "probe output"


def test_implement_v2_prompt_history_keeps_different_artifact_failures() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "first artifact",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "frame miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "frame", "path": "/tmp/frame.bmp"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "second artifact",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-2",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "latest_failure": {
                                    "class": "runtime_artifact_missing",
                                    "kind": "missing_artifact",
                                    "summary": "log miss",
                                },
                                "execution_evidence_digest": {
                                    "artifact_miss": [{"artifact_id": "log", "path": "/tmp/run.log"}]
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))

    assert rendered[0]["history_compacted"] is True
    assert rendered[0]["tool_results"][0]["latest_failures"][0]["summary"] == "frame miss"
    assert rendered[1]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"] == "log miss"


def test_implement_v2_prompt_history_preserves_family_identity_for_compacted_artifact_failures() -> None:
    def artifact_failure(provider_call_id: str, artifact_id: str, path: str) -> dict[str, object]:
        return {
            "provider_call_id": provider_call_id,
            "tool_name": "run_command",
            "status": "failed",
            "content": {
                "content": [
                    {
                        "provider_history_projection": "terminal_result_v0",
                        "latest_failure": {
                            "class": "runtime_failure",
                            "kind": "nonzero_exit",
                            "summary": "Error: memory access 0x00000000+4 outside mapped range",
                        },
                        "execution_evidence_digest": {
                            "artifact_miss": [{"artifact_id": artifact_id, "path": path}]
                        },
                    }
                ]
            },
        }

    prompt_history = [
        {
            "turn": 1,
            "summary": "first artifact",
            "tool_calls": [],
            "tool_results": [artifact_failure("call-frame", "frame", "/tmp/frame.bmp")],
        },
        {
            "turn": 2,
            "summary": "second artifact",
            "tool_calls": [],
            "tool_results": [artifact_failure("call-log", "log", "/tmp/run.log")],
        },
        {
            "turn": 3,
            "summary": "latest artifact",
            "tool_calls": [],
            "tool_results": [artifact_failure("call-json", "json", "/tmp/result.json")],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))

    assert rendered[0]["tool_results"][0]["latest_failures"][0]["provider_family_identity"] == (
        "artifact:frame:/tmp/frame.bmp"
    )
    assert rendered[1]["tool_results"][0]["latest_failures"][0]["provider_family_identity"] == (
        "artifact:log:/tmp/run.log"
    )
    assert (
        rendered[2]["tool_results"][0]["content"]["content"][0]["latest_failure"]["summary"]
        == "Error: memory access 0x00000000+4 outside mapped range"
    )


def test_implement_v2_prompt_history_projects_raw_structured_failure_classification() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "raw full-history terminal failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-run-verifier",
                    "tool_name": "run_command",
                    "status": "failed",
                    "is_error": True,
                    "content": {
                        "content": [
                            {
                                "command_run_id": "cmd-1",
                                "output_ref": "out-1",
                                "artifact_evidence": [
                                    {
                                        "artifact_id": "/tmp/frame.bmp",
                                        "path": "/tmp/frame.bmp",
                                        "status": "failed",
                                        "blocking": True,
                                    }
                                ],
                                "failure_classification": {
                                    "phase": "runtime",
                                    "kind": "missing_artifact",
                                    "class": "runtime_artifact_missing",
                                    "confidence": "high",
                                    "summary": "required artifact /tmp/frame.bmp failed structured checks",
                                    "required_next_probe": "Inspect the producer path.",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    latest_failure = rendered[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]

    assert latest_failure["class"] == "runtime_artifact_missing"
    assert latest_failure["kind"] == "missing_artifact"
    assert "required_next_action" not in latest_failure
    assert "required_next_probe" not in latest_failure


def test_implement_v2_prompt_history_projects_raw_tool_failure_class() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "raw write failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-write",
                    "tool_name": "write_file",
                    "status": "failed",
                    "is_error": True,
                    "content": {
                        "content": [
                            {
                                "operation": "write_file",
                                "failure_class": "source_mutation_unreadable_long_line",
                                "failure_subclass": "source_mutation_single_line_diagnostic_risk",
                                "path": "/app/vm.js",
                                "reason": "write_file would create a 11966 character line",
                                "suggested_next_action": "rewrite source mutations as readable multi-line code",
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    latest_failure = rendered[0]["tool_results"][0]["content"]["content"][0]["latest_failure"]

    assert latest_failure["class"] == "source_mutation_unreadable_long_line"
    assert latest_failure["kind"] == "source_mutation_single_line_diagnostic_risk"
    assert latest_failure["path"] == "/app/vm.js"
    assert "required_next_action" not in latest_failure
    assert "suggested_next_action" not in latest_failure


def test_implement_v2_prompt_history_strips_canonical_pressure_fields_from_raw_history() -> None:
    prompt_history = [
        {
            "turn": 1,
            "summary": "raw legacy state should be stripped",
            "frontier_state_update": {"status": "do-not-leak"},
            "tool_calls": [{"provider_call_id": "call-1", "tool_name": "read_file", "arguments": {"path": "vm.js"}}],
            "tool_results": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "workframe": {"required_next": {"kind": "patch_or_edit"}},
                                "proof_state": {"status": "do-not-leak"},
                                "active_work_todo": {"status": "drafting"},
                                "hard_runtime_frontier": {"status": "active"},
                                "model_authored_frontier": {"status": "do-not-leak"},
                                "frontier_state_update": {"status": "do-not-leak"},
                                "failure_class": "runtime_failure",
                                "reason": "TypeError: broken",
                                "suggested_next_action": "patch vm.js",
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = _render_prompt_history_json(prompt_history)

    for forbidden in (
        "tool_calls",
        "frontier_state_update",
        "workframe",
        "required_next",
        "proof_state",
        "active_work_todo",
        "hard_runtime_frontier",
        "model_authored_frontier",
        "suggested_next_action",
    ):
        assert forbidden not in rendered
    assert "runtime_failure" in rendered
    assert "TypeError: broken" in rendered


def test_implement_v2_prompt_history_collapses_raw_tool_failure_by_path() -> None:
    def raw_write_failure(path: str, reason: str) -> dict[str, object]:
        return {
            "operation": "write_file",
            "failure_class": "source_mutation_unreadable_long_line",
            "failure_subclass": "source_mutation_single_line_diagnostic_risk",
            "path": path,
            "reason": reason,
            "suggested_next_action": "rewrite source mutations as readable multi-line code",
        }

    prompt_history = [
        {
            "turn": 1,
            "summary": "old raw write failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-old-write",
                    "tool_name": "write_file",
                    "status": "failed",
                    "content": {"content": [raw_write_failure("/app/vm.js", "line length 9000")]},
                }
            ],
        },
        {
            "turn": 2,
            "summary": "new raw write failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-new-write",
                    "tool_name": "write_file",
                    "status": "failed",
                    "content": {"content": [raw_write_failure("/app/vm.js", "line length 11966")]},
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    first_result = rendered[0]["tool_results"][0]
    second_item = rendered[1]["tool_results"][0]["content"]["content"][0]

    assert "latest_failures" not in first_result
    assert second_item["latest_failure"]["summary"] == "line length 11966"


def test_implement_v2_prompt_history_keeps_raw_tool_failures_for_different_paths() -> None:
    def raw_write_failure(path: str) -> dict[str, object]:
        return {
            "operation": "write_file",
            "failure_class": "source_mutation_unreadable_long_line",
            "failure_subclass": "source_mutation_single_line_diagnostic_risk",
            "path": path,
            "reason": "write_file would create an unreadable generated source line",
            "suggested_next_action": "rewrite source mutations as readable multi-line code",
        }

    prompt_history = [
        {
            "turn": 1,
            "summary": "first raw write failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-vm-write",
                    "tool_name": "write_file",
                    "status": "failed",
                    "content": {"content": [raw_write_failure("/app/vm.js")]},
                }
            ],
        },
        {
            "turn": 2,
            "summary": "second raw write failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-helper-write",
                    "tool_name": "write_file",
                    "status": "failed",
                    "content": {"content": [raw_write_failure("/app/helper.js")]},
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))

    assert rendered[0]["tool_results"][0]["latest_failures"][0]["path"] == "/app/vm.js"
    assert rendered[1]["tool_results"][0]["content"]["content"][0]["latest_failure"]["path"] == "/app/helper.js"


def test_implement_v2_prompt_history_collapses_raw_same_artifact_failures() -> None:
    def raw_failure(summary: str) -> dict[str, object]:
        return {
            "command_run_id": "cmd",
            "output_ref": "out",
            "artifact_evidence": [
                {
                    "artifact_id": "/tmp/frame.bmp",
                    "path": "/tmp/frame.bmp",
                    "status": "failed",
                    "blocking": True,
                }
            ],
            "failure_classification": {
                "phase": "runtime",
                "kind": "missing_artifact",
                "class": "runtime_artifact_missing",
                "confidence": "high",
                "summary": summary,
                "required_next_probe": "Inspect the producer path.",
            },
        }

    prompt_history = [
        {
            "turn": 1,
            "summary": "old raw failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-old",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {"content": [raw_failure("old frame artifact miss")]},
                }
            ],
        },
        {
            "turn": 2,
            "summary": "new raw failure",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-new",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {"content": [raw_failure("new frame artifact miss")]},
                }
            ],
        },
    ]

    rendered = json.loads(_render_prompt_history_json(prompt_history))
    first_result = rendered[0]["tool_results"][0]
    second_item = rendered[1]["tool_results"][0]["content"]["content"][0]

    assert "latest_failures" not in first_result
    assert second_item["latest_failure"]["summary"] == "new frame artifact miss"


def test_implement_v2_terminal_projection_summarizes_long_line_streams() -> None:
    long_line = "x" * 1200
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-long-output",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="completed",
        is_error=False,
        content=(
            {
                "command": "python diagnose.py",
                "status": "completed",
                "exit_code": 0,
                "stdout": f"node_check_exit=0\n{long_line}\nshort tail\n",
                "stdout_tail": f"{long_line}\nshort tail\n",
                "output_ref": "cmd/output",
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=(),
        side_effects=(),
    )

    history = _provider_visible_tool_result_for_history(result)
    projected = history["content"]["content"][0]
    rendered = json.dumps(projected)

    assert projected["stdout_tail"].startswith("[stdout summarized for hot-path history:")
    assert projected["stdout_summary"]["projection"] == "long_line_stream_summary_v0"
    assert projected["stdout_summary"]["longest_line_chars"] == 1200
    assert long_line not in rendered
    assert projected["output_ref"] == "cmd/output"


def test_implement_v2_terminal_projection_preserves_short_tail_when_full_stream_has_long_line() -> None:
    long_line = "x" * 1200
    result = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="call-short-tail",
        mew_tool_call_id="tool-1",
        tool_name="run_command",
        status="failed",
        is_error=True,
        content=(
            {
                "command": "python diagnose.py",
                "status": "failed",
                "exit_code": 1,
                "stdout": f"{long_line}\nFINAL_ERROR: missing artifact\n",
                "stdout_tail": "FINAL_ERROR: missing artifact\n",
                "output_ref": "cmd/output",
            },
        ),
        content_refs=("cmd/output",),
        evidence_refs=(),
        side_effects=(),
    )

    history = _provider_visible_tool_result_for_history(result)
    projected = history["content"]["content"][0]

    assert projected["stdout_tail"] == "FINAL_ERROR: missing artifact\n"
    assert "stdout_summary" not in projected
    assert projected["output_ref"] == "cmd/output"


def test_implement_v2_exec_contract_accepted_nonzero_exit_can_complete(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "accepted-nonzero",
                "tool_name": "run_command",
                "arguments": {
                    "command": "exit 4",
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "id": "contract:accepted-nonzero",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_exit": {"mode": "code_set", "codes": [4]},
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "nonzero accepted"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["status"] == "failed"
    assert payload["tool_run_record"]["status"] == "failed"
    assert payload["tool_run_record"]["semantic_exit"]["ok"] is True
    assert payload["structured_finish_gate"]["blocked"] is False


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


def test_implement_v2_live_json_auto_polls_yielded_verifier_without_extra_model_turn(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 1,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert tool_result["status"] == "completed"
    assert payload["status"] == "completed"
    assert "done" in payload["stdout"]


def test_implement_v2_live_json_auto_poll_cancels_nonterminal_verifier_without_extra_model_turn(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(5); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run long verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert result.metrics["orphaned_command_cleanup_count"] == 0
    assert tool_result["status"] == "interrupted"
    assert payload["status"] == "killed"
    assert payload["reason"] == "implement_v2 verifier auto-poll budget exhausted before terminal evidence"
    assert payload["command_run_id"]


def test_implement_v2_hard_runtime_auto_poll_allows_silent_artifact_progress(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(0.05); open('frame.bmp', 'w', encoding='utf-8').write('frame')",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run silent runtime verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 1,
                "hard_runtime_verifier_no_progress_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert tool_result["status"] == "completed"
    assert payload["status"] == "completed"
    assert (tmp_path / "frame.bmp").read_text(encoding="utf-8") == "frame"


def test_implement_v2_cancels_hard_runtime_verifier_after_auto_poll_budget_with_no_output_or_artifact(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        return {
            "summary": "run silent runtime verifier",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert calls["count"] == 1
    assert result.metrics["model_turns"] == 1
    assert result.metrics["active_command_auto_poll_count"] == 1
    assert result.metrics["active_command_auto_poll_terminal_count"] == 1
    assert result.metrics["orphaned_command_cleanup_count"] == 0
    assert tool_result["status"] == "interrupted"
    assert payload["status"] == "killed"
    assert (
        payload["reason"]
        == "implement_v2 hard-runtime verifier had no observable output or expected-artifact progress after auto-poll budget"
    )
    assert payload["failure_classification"]["class"] == "runtime_artifact_missing"
    assert payload["failure_classification"]["kind"] == "missing_artifact"
    assert "interrupted" in payload["failure_classification"]["secondary_kinds"]
    assert "producing substep" in payload["failure_classification"]["required_next_probe"]


def test_implement_v2_no_output_verifier_recovery_collapses_after_source_probe(tmp_path) -> None:
    (tmp_path / "producer.c").write_text(
        'void DG_DrawFrame(void) { /* writes /tmp/frame.bmp from framebuffer */ }\n',
        encoding="utf-8",
    )
    silent_command = shlex.join([sys.executable, "-c", "import time; time.sleep(5)"])
    outputs = [
        {
            "summary": "run silent runtime verifier",
            "tool_calls": [
                {
                    "id": "silent-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": silent_command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "observe verifier result"},
        },
        {
            "summary": "inspect the producer surface once",
            "tool_calls": [
                {
                    "id": "search-producer",
                    "name": "search_text",
                    "arguments": {
                        "path": ".",
                        "query": "DG_DrawFrame|frame.bmp",
                        "regex": True,
                        "context_lines": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "producer surface inspected"},
        },
        {
            "summary": "stop after checking recovery prompt",
            "finish": {"outcome": "blocked", "summary": "test stops before mutation"},
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so the verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    latest_failure = frontier["latest_runtime_failure"]

    assert latest_failure["recovery_mode"] == "no_output_verifier_recovery"
    assert latest_failure["post_failure_probe_count"] == 1
    assert "Run one scoped producer/artifact diagnostic" not in prompts[1]
    assert "Run one scoped producer/artifact diagnostic" not in prompts[2]


def test_implement_v2_no_output_verifier_recovery_counts_current_run_after_persisted_failure(tmp_path) -> None:
    (tmp_path / "producer.c").write_text(
        'void DG_DrawFrame(void) { /* writes /tmp/frame.bmp from framebuffer */ }\n',
        encoding="utf-8",
    )
    persisted_frontier = {
        "status": "blocked",
        "final_artifact": {"path": "frame.bmp", "kind": "file", "status": "failed", "blocking": True},
        "latest_runtime_failure": {
            "provider_call_id": "old-verifier",
            "terminal_status": "killed",
            "failure_class": "runtime_artifact_missing",
            "failure_kind": "missing_artifact",
            "failure_phase": "runtime",
            "recovery_mode": "no_output_verifier_recovery",
            "required_next_action": "Run one scoped producer/artifact diagnostic for frame.bmp.",
        },
    }
    outputs = [
        {
            "summary": "inspect the producer surface after a persisted verifier failure",
            "tool_calls": [
                {
                    "id": "search-producer",
                    "name": "search_text",
                    "arguments": {
                        "path": ".",
                        "query": "DG_DrawFrame|frame.bmp",
                        "regex": True,
                        "context_lines": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "producer surface inspected"},
        },
        {
            "summary": "stop after checking persisted recovery prompt",
            "finish": {"outcome": "blocked", "summary": "test stops before mutation"},
        },
    ]
    prompts = []

    def fake_model(*args, **_kwargs):
        prompts.append(args[2])
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so the verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            persisted_lane_state={"lane_hard_runtime_frontier": persisted_frontier},
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    latest_failure = result.updated_lane_state["lane_hard_runtime_frontier"]["latest_runtime_failure"]

    assert "Run one scoped producer/artifact diagnostic" not in prompts[0]
    assert latest_failure["post_failure_probe_count"] == 1
    assert "Patch/edit the producer or runtime path" not in prompts[1]


def test_implement_v2_post_failure_mutation_count_requires_real_side_effect() -> None:
    dry_run_write = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="dry-run-write",
        mew_tool_call_id="tool-1",
        tool_name="write_file",
        status="completed",
        content=({"path": "vm.js", "written": False, "dry_run": True},),
        side_effects=(),
    )
    real_write = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="real-write",
        mew_tool_call_id="tool-2",
        tool_name="write_file",
        status="completed",
        content=({"path": "vm.js", "written": True, "dry_run": False},),
        side_effects=(
            {
                "kind": "file_write",
                "path": "vm.js",
                "written": True,
                "dry_run": False,
            },
        ),
    )
    shell_mutation = ToolResultEnvelope(
        lane_attempt_id="lane",
        provider_call_id="shell-write",
        mew_tool_call_id="tool-3",
        tool_name="run_command",
        status="completed",
        content=({"status": "completed"},),
        side_effects=(
            {
                "kind": "source_tree_mutation",
                "record": {"changed_count": 1, "changes": [{"path": "vm.js"}]},
            },
        ),
    )

    assert _post_failure_source_mutation_count((dry_run_write,)) == 0
    assert _post_failure_source_mutation_count((real_write,)) == 1
    assert _post_failure_source_mutation_count((shell_mutation,)) == 1


def test_implement_v2_shortens_repeated_silent_hard_runtime_verifier_auto_poll(tmp_path) -> None:
    calls = {"count": 0}
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        attempt = calls["count"]
        return {
            "summary": f"run silent runtime verifier attempt {attempt}",
            "tool_calls": [
                {
                    "provider_call_id": f"call-{attempt}",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "retry verifier"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.2,
                "hard_runtime_repeated_no_progress_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    first_payload = tool_results[0]["content"][0]
    second_payload = tool_results[1]["content"][0]

    assert calls["count"] == 2
    assert first_payload["status"] == "killed"
    assert "hard_runtime_verifier_budget_adjustment" not in first_payload
    assert second_payload["status"] == "killed"
    assert second_payload["hard_runtime_verifier_budget_adjustment"] == {
        "reason": "repeated_silent_runtime_artifact_verifier",
        "auto_poll_seconds": 0.01,
    }
    assert second_payload["duration_seconds"] < first_payload["duration_seconds"]


def test_implement_v2_keeps_normal_auto_poll_for_repeated_verifier_with_output(tmp_path) -> None:
    calls = {"count": 0}
    silent_command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )
    noisy_command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('booted', flush=True); time.sleep(5)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        attempt = calls["count"]
        return {
            "summary": f"run runtime verifier attempt {attempt}",
            "tool_calls": [
                {
                    "provider_call_id": f"call-{attempt}",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": silent_command if attempt == 1 else noisy_command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "retry verifier"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.2,
                "hard_runtime_repeated_no_progress_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    second_payload = tool_results[1]["content"][0]

    assert calls["count"] == 2
    assert second_payload["status"] == "killed"
    assert second_payload["stdout_tail"].strip() == "booted"
    assert "hard_runtime_verifier_budget_adjustment" not in second_payload
    assert second_payload["reason"] == "implement_v2 verifier auto-poll budget exhausted before terminal evidence"


def test_implement_v2_keeps_terminal_payload_from_short_repeated_verifier_poll(tmp_path) -> None:
    calls = {"count": 0}
    silent_command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )
    terminal_command = shlex.join(
        [
            sys.executable,
            "-c",
            "print('booted', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        attempt = calls["count"]
        return {
            "summary": f"run runtime verifier attempt {attempt}",
            "tool_calls": [
                {
                    "provider_call_id": f"call-{attempt}",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": silent_command if attempt == 1 else terminal_command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "retry verifier"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.2,
                "hard_runtime_repeated_no_progress_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]
    second_payload = tool_results[1]["content"][0]

    assert calls["count"] == 2
    assert second_payload["status"] == "completed"
    assert second_payload["stdout_tail"].strip() == "booted"
    assert "hard_runtime_verifier_budget_adjustment" not in second_payload


def test_implement_v2_fast_cancel_treats_unchanged_existing_artifact_as_no_progress(tmp_path) -> None:
    (tmp_path / "frame.bmp").write_text("stale", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "run silent runtime verifier with stale artifact present",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "mtime_after", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["status"] == "killed"
    assert (
        payload["reason"]
        == "implement_v2 hard-runtime verifier had no observable output or expected-artifact progress after auto-poll budget"
    )


def test_implement_v2_fast_cancel_ignores_glob_and_mixed_artifact_contracts(tmp_path) -> None:
    (tmp_path / "unrelated.bmp").write_text("unrelated", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; time.sleep(5)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "run silent runtime verifier with broad glob artifact contract",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 10,
                        "foreground_budget_seconds": 0.02,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                },
                                {
                                    "id": "any-bmp",
                                    "kind": "glob",
                                    "path": "*.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "verifier observed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source project for an emulator runtime interpreter "
                    "that must write frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 0.01,
                "hard_runtime_verifier_no_progress_seconds": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=3,
    )

    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["status"] == "killed"
    assert payload["reason"] == "implement_v2 verifier auto-poll budget exhausted before terminal evidence"


def test_implement_v2_live_json_does_not_auto_poll_plain_runtime_expected_exit(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('start', flush=True); time.sleep(0.05); print('done', flush=True)",
        ]
    )

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "start runtime command",
            "tool_calls": [
                {
                    "provider_call_id": "call-1",
                    "tool_name": "run_command",
                    "arguments": {
                        "command": command,
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "run",
                            "purpose": "generic runtime command",
                            "expected_exit": 0,
                        },
                    },
                }
            ],
            "finish": {"outcome": "analysis_ready", "summary": "runtime started"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allow_shell": True,
                "allowed_read_roots": [str(tmp_path)],
                "active_command_auto_poll_seconds": 1,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    assert result.metrics["active_command_auto_poll_count"] == 0
    assert result.metrics["command_closeout_count"] == 1


def test_implement_v2_exec_warns_when_shell_masks_missing_probe_tool(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime, _component_command_warnings
    from mew.implement_lane.provider import FakeProviderAdapter

    source_warning = _component_command_warnings(
        {"command": "rg --files || true", "exit_code": 0, "stderr": "zsh:1: command not found: rg\n"}
    )[0]
    assert source_warning["failure_subclass"] == "source_frontier_probe_unavailable"
    assert "source frontier as incomplete" in source_warning["recommended_next_action"]
    sh_warning = _component_command_warnings(
        {"command": "rg --files || true", "exit_code": 0, "stderr": "/bin/sh: 1: rg: not found\n"}
    )[0]
    assert sh_warning["tool"] == "rg"
    assert sh_warning["failure_subclass"] == "source_frontier_probe_unavailable"
    assert (
        _component_command_warnings(
            {"command": "grep -R 'command not found: rg' . || true", "exit_code": 0, "stdout": "file.txt:command not found: rg\n"}
        )
        == []
    )

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path))
    missing_tool = "rg_missing_for_mew_test_zz"
    call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": f"{missing_tool} --files || true",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
    )[0]

    result = runtime.execute(call)
    payload = result.content[0]
    visible = _provider_visible_tool_result_for_history(result)
    projected = visible["content"]["content"][0]

    assert result.status == "completed"
    assert payload["exit_code"] == 0
    assert payload["component_warnings"][0]["failure_class"] == "tool_availability_gap"
    assert payload["component_warnings"][0]["failure_subclass"] == "command_component_unavailable"
    assert payload["component_warnings"][0]["tool"] == missing_tool
    assert payload["component_warnings"][0]["masked_by_success_exit"] is True
    assert payload["component_warnings"][0]["command_had_shell_recovery"] is True
    assert "recommended_next_action" not in projected["component_warnings"][0]
    assert projected["latest_failure"]["class"] == "tool_availability_gap"
    assert "required_next_action" not in projected["latest_failure"]


def test_implement_v2_provider_history_redacts_controller_pressure_text() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="lane-v2-history",
        provider_call_id="write-1",
        mew_tool_call_id="mew-write-1",
        tool_name="write_file",
        status="failed",
        content=(
            {
                "reason": (
                    "blocked_by_deep_runtime_prewrite_probe_gate: write_file#write-1 must satisfy "
                    "the prewrite hard-runtime probe gate before source mutation; "
                    "Required next probe: read_file vm.js before the first source write."
                ),
                "natural_result_text": (
                    "Required next action: run one verifier after the first source write "
                    "before more reads, probes, or full rewrites."
                ),
                "path_specific_post_write": (
                    "vm.js was written successfully, but no terminal verifier command has run after it. "
                    "Run one verifier-shaped terminal command before more reads, probes, or full rewrites."
                ),
                "write_repair_lock": (
                    "write_repair_lock_active: failed; post-failure target reads used 0/1. "
                    "Apply a same-path write_file/edit_file/apply_patch repair before more reads, probes, or verifiers."
                ),
            },
        ),
        is_error=True,
    )

    rendered = json.dumps(_provider_visible_tool_result_for_history(result), ensure_ascii=False)

    assert "prewrite hard-runtime probe gate" not in rendered
    assert "Required next probe" not in rendered
    assert "Required next action" not in rendered
    assert "first source write" not in rendered
    assert "probes, or full rewrites" not in rendered
    assert "verifier-shaped terminal command" not in rendered
    assert "post-failure target reads used" not in rendered
    assert "Apply a same-path" not in rendered
    assert "controller-side diagnostic redacted" in rendered


def test_implement_v2_prompt_history_redacts_raw_legacy_pressure_text() -> None:
    history = [
        {
            "turn": 1,
            "tool_results": [
                {
                    "provider_call_id": "write-1",
                    "tool_name": "write_file",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "reason": (
                                    "must satisfy the prewrite hard-runtime probe gate before source mutation; "
                                    "Required next probe: read_file vm.js before the first source write."
                                ),
                                "natural_result_text": (
                                    "Required next action: run one verifier after the first source write "
                                    "before more reads, probes, or full rewrites."
                                ),
                                "path_specific_post_write": (
                                    "vm.js was written successfully, but no terminal verifier command has run after it. "
                                    "Run one verifier-shaped terminal command before more reads, probes, or full rewrites."
                                ),
                                "write_repair_lock": (
                                    "write_repair_lock_active: failed; post-failure target reads used 0/1. "
                                    "Apply a same-path write_file/edit_file/apply_patch repair before more reads, probes, or verifiers."
                                ),
                            }
                        ]
                    },
                }
            ],
        }
    ]

    rendered = _render_prompt_history_json(history)

    assert "prewrite hard-runtime probe gate" not in rendered
    assert "Required next probe" not in rendered
    assert "Required next action" not in rendered
    assert "first source write" not in rendered
    assert "probes, or full rewrites" not in rendered
    assert "verifier-shaped terminal command" not in rendered
    assert "post-failure target reads used" not in rendered
    assert "Apply a same-path" not in rendered
    assert "controller-side diagnostic redacted" in rendered


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
    command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import time; from pathlib import Path; "
                "Path('vm.js').write_text('cancelled', encoding='utf-8'); "
                "print('start', flush=True); time.sleep(5)"
            ),
        ]
    )
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
    time.sleep(0.1)
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
    assert cancel_result.content[0]["source_observer"]["post_snapshot_id"].startswith("snapshot:source:")
    assert cancel_result.content[0]["source_observer"]["observed_source_side_effect"] is True
    assert cancel_result.content[0]["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert not any(effect["kind"] == "source_tree_mutation" for effect in cancel_result.side_effects)


def test_implement_v2_exec_yielded_command_preserves_pre_snapshot_until_poll(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; from pathlib import Path; Path('vm.js').write_text('ok', encoding='utf-8'); time.sleep(0.2)",
        ]
    )
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
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
    read_call, poll_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=2,
        calls=(
            {"provider_call_id": "call-2", "tool_name": "read_command_output", "arguments": {"command_run_id": run_id}},
            {
                "provider_call_id": "call-3",
                "tool_name": "poll_command",
                "arguments": {"command_run_id": run_id, "wait_seconds": 1},
            },
        ),
    )

    read_result = runtime.execute(read_call)
    poll_result = runtime.execute(poll_call)
    start_observer = start_result.content[0]["source_observer"]
    read_observer = read_result.content[0]["source_observer"]
    poll_payload = poll_result.content[0]

    assert start_result.status == "yielded"
    assert start_observer["pre_snapshot_id"].startswith("snapshot:source:")
    assert start_observer["post_snapshot_id"] == ""
    assert "pre_run_source_tree_snapshot" not in start_result.content[0]
    assert read_observer["pre_snapshot_id"] == start_observer["pre_snapshot_id"]
    assert "source_tree_mutations" not in read_result.content[0]
    assert "process_source_observations" not in read_result.content[0]
    assert poll_result.status == "completed"
    assert "pre_run_source_tree_snapshot" not in poll_payload
    assert poll_payload["source_observer"]["post_snapshot_id"].startswith("snapshot:source:")
    assert poll_payload["source_observer"]["observed_source_side_effect"] is True
    assert poll_payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert any(effect["kind"] == "process_source_observation" for effect in poll_result.side_effects)
    assert not any(effect["kind"] == "source_tree_mutation" for effect in poll_result.side_effects)


def test_implement_v2_exec_finalize_closeout_projects_process_source_observer(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; from pathlib import Path; Path('vm.js').write_text('done', encoding='utf-8'); time.sleep(0.1)",
        ]
    )
    start_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
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

    closeout_payloads = runtime.finalize_active_commands(timeout_seconds=1)
    projected_result = runtime.project_result_payload(start_result, closeout_payloads[0])
    payload = projected_result.content[0]

    assert start_result.status == "yielded"
    assert projected_result.status == "completed"
    assert payload["source_observer"]["post_snapshot_id"].startswith("snapshot:source:")
    assert payload["source_observer"]["diff_status"] == "changed"
    assert payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert any(effect["kind"] == "process_source_observation" for effect in projected_result.side_effects)
    assert not any(effect["kind"] == "source_tree_mutation" for effect in projected_result.side_effects)
    assert not any("/source_tree_mutation/" in str(ref) for ref in projected_result.evidence_refs)


def test_implement_v2_exec_cancel_unknown_command_is_concise(tmp_path) -> None:
    from mew.implement_lane.exec_runtime import ImplementV2ManagedExecRuntime
    from mew.implement_lane.provider import FakeProviderAdapter

    adapter = FakeProviderAdapter()
    runtime = ImplementV2ManagedExecRuntime(workspace=str(tmp_path), max_active=1)
    cancel_call = adapter.normalize_tool_calls(
        lane_attempt_id="lane-v2-exec",
        turn_index=1,
        calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "cancel_command",
                "arguments": {"command_run_id": "missing"},
            },
        ),
    )[0]

    cancel_result = runtime.execute(cancel_call)

    assert cancel_result.status == "failed"
    assert cancel_result.is_error is True
    assert cancel_result.content[0]["reason"] == "unknown command_run_id: missing"
    assert cancel_result.side_effects == ()


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
    payload = tool_result["content"][0]
    assert "run_tests executes one argv command without a shell" in payload["reason"]
    assert payload["kind"] == "run_tests_shell_surface"
    assert payload["failure_class"] == "tool_contract_misuse"
    assert payload["failure_subclass"] == "run_tests_shell_surface"
    assert payload["tool_contract_recovery_eligible"] is True
    assert payload["terminal_failure_reaction_eligible"] is False
    assert payload["suggested_tool"] == "run_command"
    assert payload["suggested_use_shell"] is True
    assert set(payload["features"]) >= {"use_shell", "and_or"}


def test_implement_v2_run_tests_shell_orchestration_routes_to_run_command_when_shell_allowed(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "printf routed > routed.txt && test \"$(cat routed.txt)\" = routed",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell verifier routed"},
    )
    manifest = result.updated_lane_state["proof_manifest"]
    tool_result = manifest["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.metrics["replay_valid"] is True
    assert manifest["tool_calls"][0]["tool_name"] == "run_tests"
    assert tool_result["tool_name"] == "run_tests"
    assert tool_result["status"] == "completed"
    assert tool_result["evidence_refs"]
    assert payload["tool_name"] == "run_tests"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["execution_mode"] == "shell"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"
    assert payload["tool_contract_recovery"]["preserved_command_hash"].startswith("sha256:")
    assert (tmp_path / "routed.txt").read_text(encoding="utf-8") == "routed"


def test_implement_v2_run_tests_shell_source_mutation_routes_to_process_observer(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                        "command": (
                            "python3 - <<'PY'\n"
                            "from pathlib import Path\n"
                            "Path('vm.js').write_text('console.log(1)')\n"
                            "PY\n"
                            "test -s vm.js"
                        ),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source mutation observed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_run_tests_shell_surface_wins_when_shell_routing_disabled(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True, "route_run_tests_shell_surface": False},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": (
                        "python3 - <<'PY'\n"
                        "from pathlib import Path\n"
                        "Path('vm.js').write_text('console.log(1)')\n"
                        "PY"
                    ),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell surface rejected first"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["failure_subclass"] == "run_tests_shell_surface"
    assert payload["tool_contract_recovery_eligible"] is True
    assert not (tmp_path / "vm.js").exists()


def test_implement_v2_run_tests_plain_argv_source_mutation_uses_process_route(tmp_path) -> None:
    (tmp_path / "fixture.py").write_text("print('fixture')\n", encoding="utf-8")
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "cp fixture.py vm.js",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "plain argv process route"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_run_tests_named_source_file_shell_mutation_routes_to_observer(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "touch Makefile && test -f Makefile",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "named source mutation observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "Makefile").exists()


@pytest.mark.parametrize(
    "execution_contract",
    (
        {"role": "verify", "proof_role": "verifier", "acceptance_kind": "external_verifier"},
        {"proof_role": "final_verifier"},
        {"verifier_required": True},
        {"substeps": [{"id": "verify", "verifier_required": True}]},
    ),
)
def test_implement_v2_run_command_verifier_compound_source_mutation_routes_to_process_observer(
    tmp_path, execution_contract: dict[str, object]
) -> None:
    command = "cat > vm.js <<'EOF'\nconsole.log(1)\nEOF\ntest -s vm.js"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": execution_contract,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "compound observed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] in {"completed", "failed"}
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").exists()


def test_implement_v2_run_command_allows_bounded_source_writer_without_verifier_contract(tmp_path) -> None:
    command = "cat > vm.js <<'EOF'\nconsole.log(1)\nEOF"
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source writer allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert "source_tree_mutations" not in payload
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert payload["source_observer"]["observed_source_side_effect"] is True
    assert payload["source_diff_ref"] == payload["source_observer"]["source_diff_refs"][0]
    assert payload["process_source_observations"][0]["diff_ref"] == payload["source_diff_ref"]
    assert payload["source_observer"]["pre_snapshot_id"].startswith("snapshot:source:")
    assert payload["source_observer"]["post_snapshot_id"].startswith("snapshot:source:")
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log(1)\n"
    assert not any("source-mutation" in str(ref) for ref in tool_result.get("evidence_refs", []))
    assert not any("/source_tree_mutation/" in str(ref) for ref in tool_result.get("evidence_refs", []))
    assert any(effect["kind"] == "process_source_observation" for effect in tool_result["side_effects"])
    assert not any(effect["kind"] == "source_tree_mutation" for effect in tool_result["side_effects"])


def test_implement_v2_live_routes_do_not_call_old_shell_mutation_classifiers(tmp_path, monkeypatch) -> None:
    def bomb(*_args, **_kwargs):
        raise AssertionError("old shell mutation classifier must not run on live native routes")

    for name in (
        "_run_tests_source_mutation_misuse",
        "_run_command_source_mutation_verifier_compound_misuse",
        "_run_command_source_patch_misuse",
        "_run_command_source_creation_shell_surface_misuse",
        "_run_command_source_exploration_shell_surface_misuse",
        "_source_like_mutation_paths",
    ):
        monkeypatch.setattr(exec_runtime, name, bomb)
    monkeypatch.setattr(v2_runtime, "_shell_command_may_mutate_source_tree", bomb)
    monkeypatch.setattr(v2_runtime, "_source_patch_shell_repair_from_result", bomb)

    outputs = [
        {
            "summary": "source writes through execute-route tools are observed, not classified",
            "tool_calls": [
                {
                    "id": "shell-write",
                    "name": "run_command",
                    "arguments": {
                        "command": "cat > vm.js <<'EOF'\nconsole.log(1)\nEOF",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
                {
                    "id": "run-tests-write",
                    "name": "run_tests",
                    "arguments": {
                        "command": "touch Makefile && test -f Makefile",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                },
            ],
            "finish": {"outcome": "continue"},
        },
        {"summary": "stop after live classifier guard", "finish": {"outcome": "blocked", "summary": "done"}},
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )
    tool_results = result.updated_lane_state["proof_manifest"]["tool_results"]

    assert [item["status"] for item in tool_results[:2]] == ["completed", "completed"]
    assert all(item["content"][0]["tool_route"] == "process_runner" for item in tool_results[:2])
    assert all(item["content"][0]["process_source_observations"] for item in tool_results[:2])


@pytest.mark.parametrize("tool_name", ("run_command", "run_tests"))
def test_implement_v2_execute_route_rejects_edit_shaped_args(tmp_path, tool_name: str) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True, "allow_verify": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": tool_name,
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "patch": "*** Begin Patch\n*** End Patch\n",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "edit shaped args rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["tool_route"] == "invalid_tool_contract"
    assert payload["failure_subclass"] == "explicit_edit_shaped_execute_args"
    assert not (tmp_path / "true").exists()


def test_implement_v2_source_mutation_roots_default_to_workspace_not_all_write_roots(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    scratch = tmp_path / "scratch"
    workspace.mkdir()
    scratch.mkdir()
    command = shlex.join(
        [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(scratch / 'diag.txt')!r}).write_text('diag', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(workspace),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(workspace), str(scratch)],
                "allowed_write_roots": [str(workspace), str(scratch)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": str(workspace),
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "scratch diagnostic written"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert (scratch / "diag.txt").read_text(encoding="utf-8") == "diag"
    assert payload["process_source_observations"] == []
    assert payload["source_observer"]["observed_source_side_effect"] is False
    assert payload["source_observer"]["diff_status"] == "unchanged"
    assert not any(effect["kind"] == "source_tree_mutation" for effect in tool_result["side_effects"])


def test_implement_v2_process_source_observer_ignores_build_output_roots(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "from pathlib import Path; "
                "Path('build').mkdir(exist_ok=True); Path('dist').mkdir(exist_ok=True); "
                "[Path('build', f'generated_{i}.py').write_text('pass\\n', encoding='utf-8') for i in range(25)]; "
                "[Path('dist', f'packed_{i}.py').write_text('pass\\n', encoding='utf-8') for i in range(25)]; "
                "Path('vm.py').write_text('tracked\\n', encoding='utf-8')"
            ),
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "tracked source observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["process_source_observations"][0]["changed_count"] == 1
    changed_paths = payload["process_source_observations"][0]["changes"]
    assert changed_paths[0]["path"].endswith("/vm.py")
    assert not any("/build/" in item["path"] or "/dist/" in item["path"] for item in changed_paths)


def test_implement_v2_process_source_observer_reports_truncated_snapshot(tmp_path) -> None:
    for index in range(505):
        (tmp_path / f"source_{index}.py").write_text("pass\n", encoding="utf-8")

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "snapshot truncation observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["source_observer"]["snapshot_status"] == "truncated"
    assert payload["source_observer"]["diff_status"] == "unchanged"
    assert payload["process_source_observations"] == []


def test_implement_v2_run_tests_process_observer_records_unchanged_snapshot(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_verify": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "true",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "run_tests observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["effective_tool_name"] == "run_tests"
    assert payload["source_observer"]["pre_snapshot_id"].startswith("snapshot:source:")
    assert payload["source_observer"]["post_snapshot_id"].startswith("snapshot:source:")
    assert payload["source_observer"]["diff_status"] == "unchanged"
    assert payload["process_source_observations"] == []


def test_implement_v2_write_tool_scratch_side_effect_is_not_source_mutation(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    scratch = tmp_path / "scratch"
    workspace.mkdir()
    scratch.mkdir()
    scratch_file = scratch / "diag.txt"
    call = ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="fake",
        provider_call_id="call-write-scratch",
        mew_tool_call_id="tool-write-scratch",
        tool_name="write_file",
        arguments={"path": str(scratch_file), "content": "diag", "apply": True},
        turn_index=2,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"path": str(scratch_file), "written": True},),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": str(scratch_file),
                "written": True,
            },
        ),
    )

    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["vm.js"]}},
        tool_calls=(call,),
        tool_results=(result,),
        probe_threshold=1,
        source_mutation_roots=(str(workspace),),
    )

    assert readiness["status"] == "not_due"
    assert readiness["first_write_attempt_tool"] == "write_file"
    assert readiness.get("first_write_tool") in (None, "")
    assert readiness["write_attempt_count"] == 1
    assert not _has_completed_source_tree_mutation((result,), source_mutation_roots=(str(workspace),))


def test_implement_v2_write_tool_workspace_side_effect_is_source_mutation(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_file = workspace / "vm.js"
    call = ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="fake",
        provider_call_id="call-write-source",
        mew_tool_call_id="tool-write-source",
        tool_name="write_file",
        arguments={"path": str(source_file), "content": "source", "apply": True},
        turn_index=2,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"path": str(source_file), "written": True},),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": str(source_file),
                "written": True,
            },
        ),
    )

    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["vm.js"]}},
        tool_calls=(call,),
        tool_results=(result,),
        probe_threshold=1,
        source_mutation_roots=(str(workspace),),
    )

    assert readiness["status"] == "written"
    assert readiness["first_write_tool"] == "write_file"
    assert readiness["write_attempt_count"] == 1
    assert _has_completed_source_tree_mutation((result,), source_mutation_roots=(str(workspace),))


def test_implement_v2_write_tool_dry_run_content_path_is_not_source_mutation(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source_file = workspace / "vm.js"
    call = ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="fake",
        provider_call_id="call-dry-run-source",
        mew_tool_call_id="tool-dry-run-source",
        tool_name="write_file",
        arguments={"path": str(source_file), "content": "source"},
        turn_index=2,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"path": str(source_file), "written": False, "dry_run": True},),
        side_effects=(),
    )

    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["vm.js"]}},
        tool_calls=(call,),
        tool_results=(result,),
        probe_threshold=1,
        source_mutation_roots=(str(workspace),),
    )

    assert readiness["status"] == "not_due"
    assert readiness["first_write_attempt_tool"] == "write_file"
    assert readiness.get("first_write_tool") in (None, "")
    assert not _has_completed_source_tree_mutation((result,), source_mutation_roots=(str(workspace),))


def test_implement_v2_relative_source_mutation_roots_resolve_from_workspace(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    source_root = workspace / "src"
    source_root.mkdir(parents=True)
    source_file = source_root / "vm.js"
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(workspace),
        lane=IMPLEMENT_V2_LANE,
        lane_config={"source_mutation_roots": ["src"]},
    )
    call = ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="fake",
        provider_call_id="call-write-source",
        mew_tool_call_id="tool-write-source",
        tool_name="write_file",
        arguments={"path": str(source_file), "content": "source", "apply": True},
        turn_index=2,
    )
    result = ToolResultEnvelope(
        lane_attempt_id=call.lane_attempt_id,
        provider_call_id=call.provider_call_id,
        mew_tool_call_id=call.mew_tool_call_id,
        tool_name=call.tool_name,
        status="completed",
        content=({"path": str(source_file), "written": True},),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": str(source_file),
                "written": True,
            },
        ),
    )

    roots = _source_mutation_roots(lane_input)
    readiness = _first_write_readiness_from_trace(
        {"id": "todo-1", "source": {"target_paths": ["src/vm.js"]}},
        tool_calls=(call,),
        tool_results=(result,),
        probe_threshold=1,
        source_mutation_roots=roots,
    )

    assert roots == (str(source_root.resolve(strict=False)),)
    assert readiness["status"] == "written"
    assert _has_completed_source_tree_mutation((result,), source_mutation_roots=roots)


def test_implement_v2_default_source_mutation_root_resolves_relative_workspace(tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    workspace = project / "workspace"
    workspace.mkdir(parents=True)
    source_file = workspace / "vm.js"
    monkeypatch.chdir(project)
    lane_input = ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace="workspace",
        lane=IMPLEMENT_V2_LANE,
        lane_config={},
    )
    result = ToolResultEnvelope(
        lane_attempt_id="attempt-1",
        provider_call_id="call-write-source",
        mew_tool_call_id="tool-write-source",
        tool_name="write_file",
        status="completed",
        content=({"path": str(source_file), "written": True},),
        side_effects=(
            {
                "kind": "file_write",
                "operation": "write_file",
                "path": str(source_file),
                "written": True,
            },
        ),
    )

    roots = _source_mutation_roots(lane_input)

    assert roots == (str(workspace.resolve(strict=False)),)
    assert _has_completed_source_tree_mutation((result,), source_mutation_roots=roots)


def test_implement_v2_explicit_source_mutation_roots_track_non_workspace_source(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    generated_source = tmp_path / "generated-source"
    workspace.mkdir()
    generated_source.mkdir()
    command = shlex.join(
        [
            sys.executable,
            "-c",
            f"from pathlib import Path; Path({str(generated_source / 'vm.js')!r}).write_text('source', encoding='utf-8')",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(workspace),
            lane=IMPLEMENT_V2_LANE,
            lane_config={
                "mode": "exec",
                "allow_shell": True,
                "allowed_read_roots": [str(workspace), str(generated_source)],
                "allowed_write_roots": [str(workspace), str(generated_source)],
                "source_mutation_roots": [str(generated_source)],
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": str(workspace),
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "external source written"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")


def test_implement_v2_run_command_same_path_source_patch_routes_to_process_observer(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "p=Path('vm.js')\n"
        "s=p.read_text()\n"
        "p.write_text(s.replace('old','new'))\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source patch observed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_same_path_source_patch_relative_variants_observed(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "s=Path('./vm.js').read_text()\n"
        "Path('vm.js').write_text(s.replace('old','new'))\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source patch observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_source_patch_routes_to_process_observer(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log('old')\n", encoding="utf-8")

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                        "command": (
                            f"{shlex.quote(sys.executable)} -c "
                            "\"from pathlib import Path; "
                            "p=Path('vm.js'); "
                            "p.write_text(p.read_text().replace('old','new'))\""
                        ),
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source patch observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_allows_write_only_source_writer_without_readback(tmp_path) -> None:
    command = (
        "python3 - <<'PY'\n"
        "from pathlib import Path\n"
        "Path('vm.js').write_text(\"console.log('new')\\n\", encoding='utf-8')\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source writer allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log('new')\n"


def test_implement_v2_run_command_broad_python_source_scanner_runs_as_process_metadata(tmp_path) -> None:
    (tmp_path / "vm.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('.'):\n"
        "    for name in files:\n"
        "        if name.endswith(('.c', '.h', '.py')):\n"
        "            path = os.path.join(root, name)\n"
        "            print(path)\n"
        "            print(open(path).read()[:500])\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "broad scanner observed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True


def test_implement_v2_run_command_absolute_python_source_scanner_runs_as_process_metadata(tmp_path) -> None:
    (tmp_path / "vm.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    command = (
        f"/usr/bin/env {shlex.quote(sys.executable)} - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('.'):\n"
        "    for name in files:\n"
        "        if name.endswith(('.c', '.h')):\n"
        "            print(open(os.path.join(root, name)).read()[:120])\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "absolute python scanner observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True


def test_implement_v2_run_command_source_scanner_with_verifier_contract_runs_as_process_metadata(tmp_path) -> None:
    (tmp_path / "vm.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('.'):\n"
        "    for name in files:\n"
        "        if name.endswith(('.c', '.h')):\n"
        "            print(open(os.path.join(root, name)).read()[:120])\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "role": "verify",
                        "stage": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "verifier-labeled source scanner observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True


def test_implement_v2_run_command_workspace_wide_python_content_scanner_runs_as_process_metadata(tmp_path) -> None:
    (tmp_path / "README").write_text("source-ish content\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('.'):\n"
        "    for name in files:\n"
        "        path = os.path.join(root, name)\n"
        "        print(path, open(path, errors='ignore').read()[:500])\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "workspace scanner observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True


def test_implement_v2_run_command_source_root_python_content_scanner_runs_as_process_metadata(tmp_path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "README").write_text("source-ish content\n", encoding="utf-8")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('src'):\n"
        "    for name in files:\n"
        "        path = os.path.join(root, name)\n"
        "        print(path, open(path, errors='ignore').read()[:500])\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "source root scanner observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["command_classification"]["not_source_mutation_classifier"] is True


def test_implement_v2_run_command_allows_bounded_python_file_probe(tmp_path) -> None:
    (tmp_path / "vm.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "from pathlib import Path; print('main' in Path('vm.c').read_text(encoding='utf-8'))",
        ]
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "bounded source probe allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "True" in tool_result["content"][0]["stdout"]


def test_implement_v2_run_command_allows_recursive_artifact_verifier_probe(tmp_path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "frame.bmp").write_bytes(b"BMdata")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('out'):\n"
        "    for name in files:\n"
        "        if name.endswith('.bmp'):\n"
        "            print(os.path.join(root, name))\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "role": "verify",
                        "stage": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact verifier allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "out/frame.bmp" in tool_result["content"][0]["stdout"]


def test_implement_v2_run_command_allows_recursive_artifact_verifier_content_probe(tmp_path) -> None:
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "frame.bmp").write_bytes(b"BMdata")
    command = (
        "python3 - <<'PY'\n"
        "import os\n"
        "for root, _dirs, files in os.walk('out'):\n"
        "    for name in files:\n"
        "        if name.endswith('.bmp'):\n"
        "            path = os.path.join(root, name)\n"
        "            print(path, open(path, 'rb').read(2))\n"
        "PY"
    )

    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_command",
                "arguments": {
                    "command": command,
                    "cwd": ".",
                    "use_shell": True,
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "execution_contract": {
                        "role": "verify",
                        "stage": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                    },
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "artifact content verifier allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "b'BM'" in tool_result["content"][0]["stdout"]


@pytest.mark.parametrize(
    "command,target",
    (
        ("printf 'console.log(1)' >> vm.js", "vm.js"),
        ("printf 'console.log(1)' 1>vm.js", "vm.js"),
        ("printf 'console.log(1)' >| vm.js", "vm.js"),
        ("printf 'console.log(1)' > 'vm.js'", "vm.js"),
        ("printf 'all:' | tee -a Makefile", "Makefile"),
        ("printf 'all:' | tee results.json Makefile", "Makefile"),
        ("printf 'all:' | tee -a results.json Makefile", "Makefile"),
        ("printf 'all:' | command tee Makefile", "Makefile"),
        ("printf 'all:' | LC_ALL=C tee Makefile", "Makefile"),
        ("printf 'all:' | env LC_ALL=C tee Makefile", "Makefile"),
    ),
)
def test_implement_v2_run_tests_source_redirection_mutation_routes_to_process_observer(
    tmp_path, command: str, target: str
) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
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
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "redirection source mutation observed"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["tool_route"] == "process_runner"
    assert payload["process_source_observations"][0]["changed_count"] >= 1
    changed_paths = {
        str(change.get("path") or "")
        for change in payload["process_source_observations"][0]["changes"]
        if isinstance(change, dict)
    }
    assert any(path.endswith(f"/{target}") for path in changed_paths)
    assert (tmp_path / target).exists()


def test_implement_v2_run_tests_quoted_tee_text_is_not_source_mutation(tmp_path) -> None:
    quoted_tee_command = shlex.join([sys.executable, "-c", 'print("| tee Makefile")'])
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": quoted_tee_command,
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "quoted tee text allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "| tee Makefile" in tool_result["content"][0]["stdout"]
    assert not (tmp_path / "Makefile").exists()


def test_implement_v2_run_tests_readonly_open_source_file_is_allowed(tmp_path) -> None:
    (tmp_path / "package.json").write_text('{"scripts": {}}\n', encoding="utf-8")
    read_package_command = shlex.join([sys.executable, "-c", "open('package.json').read()"])
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": f"{read_package_command} && echo ok",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "read-only verifier allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"


def test_implement_v2_run_tests_readonly_path_and_json_artifact_write_is_allowed(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.log(1)\n", encoding="utf-8")
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": (
                        "python3 - <<'PY'\n"
                        "from pathlib import Path\n"
                        "assert Path('vm.js').exists()\n"
                        "Path('results.json').write_text('{}')\n"
                        "PY\n"
                        "test -s results.json"
                    ),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "path read plus artifact write allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert (tmp_path / "results.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "vm.js").read_text(encoding="utf-8") == "console.log(1)\n"


def test_implement_v2_run_tests_json_artifact_redirect_is_allowed(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "printf '{}' > results.json && test -s results.json",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "json artifact verifier allowed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert (tmp_path / "results.json").read_text(encoding="utf-8") == "{}"


def test_implement_v2_routed_run_tests_tracks_effective_run_command_source_mutation(tmp_path) -> None:
    hidden_source_write = shlex.join(
        [
            sys.executable,
            "-c",
            (
                "import pathlib; "
                "name=chr(118)+chr(109)+chr(46)+chr(106)+chr(115); "
                "pathlib.Path(name).write_text('console.log(1)')"
            ),
        ]
    )
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": f"{hidden_source_write} && test -f vm.js",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "hidden source mutation tracked"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["process_source_observations"][0]["changed_count"] == 1
    assert payload["process_source_observations"][0]["changes"][0]["path"].endswith("/vm.js")
    assert any(effect["kind"] == "process_source_observation" for effect in tool_result["side_effects"])
    assert not any(effect["kind"] == "source_tree_mutation" for effect in tool_result["side_effects"])


def test_implement_v2_routed_run_tests_shell_failure_preserves_terminal_failure(tmp_path) -> None:
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": "printf routed-fail >&2; exit 3",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "shell verifier routed and failed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "failed"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"
    assert payload["exit_code"] == 3
    assert "routed-fail" in payload["stderr"]


def test_implement_v2_routed_run_tests_yielded_closeout_preserves_recovery_metadata(tmp_path) -> None:
    command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time, pathlib; time.sleep(2); pathlib.Path('late.txt').write_text('late')",
        ]
    )
    result = run_fake_exec_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            lane_config={"mode": "exec", "allow_shell": True},
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "run_tests",
                "arguments": {
                    "command": f"{command} && test -f late.txt",
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 0,
                    "use_shell": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "yielded shell verifier routed"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "interrupted"
    assert payload["effective_tool_name"] == "run_command"
    assert payload["tool_contract_recovery"]["kind"] == "run_tests_shell_surface_routed_to_run_command"


def test_implement_v2_live_json_does_not_route_run_tests_when_run_command_unavailable_for_mode(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "write mode should not execute verifier",
            "tool_calls": [
                {
                    "id": "call-1",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf routed > routed.txt && test -f routed.txt",
                        "cwd": ".",
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "use_shell": True,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "do not run verifier in write mode"},
            lane_config={
                "mode": "write",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "invalid"
    assert "not available in implement_v2 write mode" in payload["reason"]
    assert not (tmp_path / "routed.txt").exists()


def test_implement_v2_run_tests_simple_argv_command_still_runs(tmp_path) -> None:
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
                    "command": shlex.join([sys.executable, "-c", "print('ok')"]),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv test ran"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["execution_mode"] == "argv"
    assert "ok" in tool_result["content"][0]["stdout"]


def test_implement_v2_run_tests_command_array_aliases_argv(tmp_path) -> None:
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
                    "command": [sys.executable, "-c", "print('ok-array')"],
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "command array ran"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert tool_result["status"] == "completed"
    assert payload["execution_mode"] == "argv"
    assert payload["command_source"] == "command_argv"
    assert "ok-array" in payload["stdout"]


def test_implement_v2_run_tests_allows_quoted_shell_metacharacters(tmp_path) -> None:
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
                    "command": shlex.join([sys.executable, "-c", "print('a|b && c > d')"]),
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "quoted shell chars are argv data"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert tool_result["status"] == "completed"
    assert "a|b && c > d" in tool_result["content"][0]["stdout"]


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
    payload = tool_result["content"][0]
    assert "run_tests executes one argv command without a shell" in payload["reason"]
    assert payload["failure_class"] == "tool_contract_misuse"
    assert payload["failure_subclass"] == "run_tests_shell_surface"
    assert "explicit_shell_interpreter" in payload["features"]


def test_implement_v2_run_tests_rejects_shell_interpreter_argv(tmp_path) -> None:
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
                    "argv": ["bash", "-lc", "echo ok && echo verify"],
                    "cwd": ".",
                    "timeout": 5,
                    "foreground_budget_seconds": 1,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "argv shell rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload["failure_class"] == "tool_contract_misuse"
    assert "explicit_shell_interpreter" in payload["features"]


def test_implement_v2_run_tests_rejects_background_redirect_and_env_split_shell(tmp_path) -> None:
    cases = (
        ("python -m pytest &", "background"),
        ("python -m pytest > out.txt", "redirect"),
        ("printf ok | wc -c", "pipe"),
        ("printf ok || echo fallback", "and_or"),
        ("cat <<EOF\nok\nEOF", "heredoc"),
        ("python -m pytest\npython -m unittest", "newline"),
        ("env -S 'bash -lc echo-ok'", "explicit_shell_interpreter"),
    )
    for index, (command, expected_feature) in enumerate(cases, start=1):
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
        payload = tool_result["content"][0]
        assert "run_tests executes one argv command without a shell" in payload["reason"]
        assert payload["failure_class"] == "tool_contract_misuse"
        assert payload["failure_subclass"] == "run_tests_shell_surface"
        assert payload["terminal_failure_reaction_eligible"] is False
        assert expected_feature in payload["features"]


def test_implement_v2_run_tests_resident_mew_loop_rejection_wins_before_tool_contract_payload(tmp_path) -> None:
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
                    "command": "./mew work --ai && echo ok",
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
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "resident mew loops" in payload["reason"]
    assert "failure_class" not in payload


def test_implement_v2_ignores_model_frontier_update_even_with_tool_calls(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "probe source frontier",
            "frontier_state_update": {
                "status": "active",
                "objective": "build source-backed artifact",
                "source_roles": [
                    {
                        "path": "doomgeneric_img.c",
                        "role": "primary_source",
                        "state": "grounded",
                        "evidence_refs": [
                            {"kind": "provider_call", "id": "probe-1"},
                            {"kind": "provider_call", "id": "fabricated"},
                        ],
                    },
                    {
                        "path": "fake.c",
                        "role": "primary_source",
                        "state": "grounded",
                        "evidence_refs": [{"kind": "command_run", "id": "missing-run"}],
                    },
                ],
            },
            "tool_calls": [
                {
                    "id": "probe-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf source-ok",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})

    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    assert result.metrics["legacy_projection_field_rejected_count"] == 1
    assert "source_roles" not in frontier
    assert "doomgeneric_img.c" not in json.dumps(frontier, sort_keys=True)
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    assert tool_result["status"] == "invalid"
    assert tool_result["content"][0]["failure_class"] == "legacy_projection_field_rejected"


def test_implement_v2_frontier_runtime_failure_overrides_model_claim(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = "import sys; sys.stderr.write('real linker error\\n'); sys.exit(2)"
        return {
            "summary": "build fails",
            "frontier_state_update": {
                "latest_build_failure": {
                    "command_run_id": "fabricated",
                    "exit_code": 99,
                    "stderr_tail": "fake failure",
                    "failure_summary": "fake",
                }
            },
            "tool_calls": [
                {
                    "id": "build-1",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "builder",
                            "target": "doomgeneric_mips",
                            "expected_artifact": {"path": "build/doomgeneric_mips", "kind": "executable"},
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "build failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})
    assert "latest_build_failure" not in frontier
    assert "fake failure" not in json.dumps(frontier, sort_keys=True)
    assert result.metrics["legacy_projection_field_rejected_count"] == 1
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    assert tool_result["status"] == "invalid"
    assert tool_result["content"][0]["failure_class"] == "legacy_projection_field_rejected"


def test_implement_v2_frontier_demotes_marker_only_runtime_artifact_contract_mismatch(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('ELF Header: Data: 2\\'s complement, big endian'); "
            "print('Machine: MIPS R3000'); "
            "print('vm.js uses readUInt32LE for instruction fetch'); "
            "print('Execution error at PC=0x4002e8: Unknown opcode: 0x10'); "
            "sys.exit(1)"
        )
        return {
            "summary": "runtime artifact contract mismatch",
            "tool_calls": [
                {
                    "id": "vm-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "VM rejected the binary artifact"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    failure = frontier["latest_runtime_failure"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert failure["failure_class"] == "runtime_failure"
    assert failure["failure_confidence"] == "low"
    assert failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "Unknown opcode" in failure["stdout_tail"]
    assert "expected_artifacts" in failure["required_next_probe"]


def test_implement_v2_frontier_normalized_role_wins_over_raw_build_text(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = "import sys; sys.stderr.write('runtime failure after build-looking contract\\n'); sys.exit(2)"
        return {
            "summary": "runtime role should win over build-looking raw fields",
            "tool_calls": [
                {
                    "id": "runtime-role-build-text",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-role-build-text",
                            "role": "runtime",
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "target": "build/link/runtime artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime contract failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Build source for vm.js and run the runtime verifier so it writes /tmp/frame.bmp."
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "latest_build_failure" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_failure"


def test_implement_v2_frontier_does_not_classify_runtime_mismatch_from_command_text_only(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "diagnostic probe had search markers only in the command text",
            "tool_calls": [
                {
                    "id": "vm-marker-grep",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'no vm mismatch found\\n'; false # Unknown opcode readUInt32LE ELF",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "diagnostic",
                            "stage": "debug",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "diagnostic probe failed"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert frontier["latest_runtime_failure"]["failure_summary"] == "no vm mismatch found"


def test_implement_v2_frontier_classifies_observed_vm_timeout_as_runtime_failure(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('PATCHED vm.js JALR decode variables'); "
            "print('VM_RC=124'); "
            "print('--- vm stdout tail ---'); "
            "sys.exit(1)"
        )
        return {
            "summary": "compound build plus runtime verifier timed out",
            "tool_calls": [
                {
                    "id": "rebuild-and-vm-verify",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all completed\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "runtime",
                            "target": "vm artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "VM timed out before artifact production"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert "latest_build_failure" not in frontier
    assert runtime_failure["failure_class"] == "runtime_failure"
    assert runtime_failure["failure_confidence"] == "low"
    assert runtime_failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "VM_RC=124" in runtime_failure["stdout_tail"]
    assert "expected_artifacts" in runtime_failure["required_next_probe"]


def test_implement_v2_frontier_classifies_observed_runtime_missing_artifact_over_build_text(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('=== link completed ==='); "
            "print('=== fresh vm verification ==='); "
            "print('vm_rc=0'); "
            "print('Program terminated at PC=0x0'); "
            "print('Executed 9 instructions'); "
            "print('NO_FRAME'); "
            "sys.stderr.write('linker warning: mixed ABI objects\\n'); "
            "sys.exit(4)"
        )
        return {
            "summary": "compound build plus runtime verifier produced no output artifact",
            "tool_calls": [
                {
                    "id": "rebuild-and-vm-no-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all completed\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "repair, build, link, and verification",
                            "stage": "build+verification",
                            "proof_role": "runtime",
                            "target": "runtime artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime exited without the required artifact"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert "latest_build_failure" not in frontier
    assert runtime_failure["failure_class"] == "unknown_failure"
    assert runtime_failure["failure_confidence"] == "low"
    assert runtime_failure["legacy_marker_authority"] == "inactive_contract_backed"
    assert "NO_FRAME" in runtime_failure["stdout_tail"]
    assert "structured execution_contract" in runtime_failure["required_next_probe"]


def test_implement_v2_frontier_prefers_structured_missing_runtime_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier exited without producing declared artifact",
            "tool_calls": [
                {
                    "id": "structured-runtime-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'runtime ended normally without markers\\n'",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:structured-runtime-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    runtime_failure = result.updated_lane_state["lane_hard_runtime_frontier"]["latest_runtime_failure"]

    assert runtime_failure["failure_class"] == "runtime_artifact_missing"
    assert runtime_failure["failure_kind"] == "missing_artifact"
    assert "NO_FRAME" not in runtime_failure["stdout_tail"]
    assert "producing substep" in runtime_failure["required_next_probe"]


def test_implement_v2_blocks_repeated_runtime_artifact_failure_plateau(tmp_path) -> None:
    (tmp_path / "vm.js").write_text("console.error('initial missing frame'); process.exit(1);\n", encoding="utf-8")
    calls = {"count": 0}

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        attempt = calls["count"]
        return {
            "summary": f"attempt {attempt} patches and verifies the runtime artifact",
            "tool_calls": [
                {
                    "id": f"write-vm-{attempt}",
                    "name": "write_file",
                    "arguments": {
                        "path": "vm.js",
                        "content": f"console.error('NO_FRAME attempt {attempt}'); process.exit(1);\\n",
                    },
                },
                {
                    "id": f"verify-frame-{attempt}",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": f"contract:verify-frame-{attempt}",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "continue", "summary": "repair and verify again"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
                "runtime_artifact_failure_plateau_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    plateau = result.updated_lane_state["lane_hard_runtime_frontier"]["runtime_artifact_failure_plateau"]

    assert calls["count"] == 3
    assert result.status == "blocked"
    assert "runtime artifact failure plateau" in result.user_visible_summary
    assert result.updated_lane_state["lane_hard_runtime_frontier"]["status"] == "blocked"
    assert plateau["failure_class"] == "runtime_artifact_failure_plateau"
    assert plateau["repeat_count"] == 3
    assert plateau["artifact_path"].endswith("frame.bmp")
    assert result.metrics["runtime_artifact_failure_plateau"]["repeat_count"] == 3


def test_implement_v2_runtime_artifact_failure_plateau_does_not_collapse_distinct_runtime_errors(
    tmp_path,
) -> None:
    (tmp_path / "vm.js").write_text("console.error('initial missing frame'); process.exit(1);\n", encoding="utf-8")
    calls = {"count": 0}

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        attempt = calls["count"]
        runtime_error = (
            "Traceback (most recent call last):\nRuntimeError: unsupported op=0x11"
            if attempt == 1
            else "Traceback (most recent call last):\nRuntimeError: unsupported SPECIAL funct 10"
        )
        return {
            "summary": f"attempt {attempt} moves to a different runtime error",
            "tool_calls": [
                {
                    "id": f"write-vm-{attempt}",
                    "name": "write_file",
                    "arguments": {
                        "path": "vm.js",
                        "content": f"console.error({json.dumps(runtime_error)}); process.exit(1);\n",
                        "apply": True,
                        "create": True,
                    },
                },
                {
                    "id": f"verify-frame-{attempt}",
                    "name": "run_command",
                    "arguments": {
                        "command": "node vm.js",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": f"contract:verify-frame-{attempt}",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "continue", "summary": "runtime error changed; keep repairing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
                "runtime_artifact_failure_plateau_threshold": 2,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    assert calls["count"] == 2
    assert result.metrics["runtime_artifact_failure_plateau"] == {}
    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier") or {}
    assert "runtime_artifact_failure_plateau" not in frontier


def test_implement_v2_runtime_artifact_failure_plateau_resets_after_passing_artifact(tmp_path) -> None:
    outputs = [
        {
            "summary": "first verifier misses runtime artifact",
            "tool_calls": [
                {
                    "id": "verify-frame-1",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-1",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "repair artifact path"},
        },
        {
            "summary": "second verifier misses runtime artifact",
            "tool_calls": [
                {
                    "id": "verify-frame-2",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-2",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "repair artifact path"},
        },
        {
            "summary": "third same-shape precheck is followed by a passing verifier",
            "tool_calls": [
                {
                    "id": "verify-frame-3-precheck",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-3-precheck",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
                {
                    "id": "create-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c \"from pathlib import Path; Path('frame.bmp').write_bytes(b'BM')\"",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                },
                {
                    "id": "verify-frame-3-pass",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-3-pass",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "stop after passing artifact proof"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "status": "blocked",
                    "final_artifact": {"path": "frame.bmp", "kind": "file"},
                    "latest_runtime_failure": {
                        "failure_class": "runtime_artifact_missing",
                        "failure_kind": "missing_artifact",
                        "failure_summary": "stale runtime artifact miss",
                    },
                    "runtime_artifact_failure_plateau": {
                        "failure_class": "runtime_artifact_failure_plateau",
                        "artifact_path": "frame.bmp",
                        "repeat_count": 3,
                    },
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
                "runtime_artifact_failure_plateau_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    assert result.metrics["runtime_artifact_failure_plateau"] == {}
    assert "runtime_artifact_failure_plateau" not in result.updated_lane_state["lane_hard_runtime_frontier"]
    assert "latest_runtime_failure" not in result.updated_lane_state["lane_hard_runtime_frontier"]
    assert result.updated_lane_state["lane_hard_runtime_frontier"]["status"] != "blocked"


def test_implement_v2_runtime_artifact_failure_plateau_keeps_later_missing_after_earlier_pass(tmp_path) -> None:
    outputs = [
        {
            "summary": "first verifier passes artifact",
            "tool_calls": [
                {
                    "id": "create-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c \"from pathlib import Path; Path('frame.bmp').write_bytes(b'BM')\"",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                },
                {
                    "id": "verify-frame-pass",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-pass",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "continue", "summary": "later regression check"},
        },
        {
            "summary": "later verifier misses the same artifact",
            "tool_calls": [
                {
                    "id": "delete-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "rm -f frame.bmp",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                },
                {
                    "id": "verify-frame-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:verify-frame-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "later artifact regression is still unresolved"},
        },
        {
            "summary": "stop after recording later artifact regression",
            "finish": {"outcome": "blocked", "summary": "later artifact regression is still unresolved"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "status": "blocked",
                    "final_artifact": {"path": "frame.bmp", "kind": "file"},
                    "runtime_artifact_failure_plateau": {
                        "failure_class": "runtime_artifact_failure_plateau",
                        "artifact_path": "frame.bmp",
                        "repeat_count": 3,
                    },
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
                "runtime_artifact_failure_plateau_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=10,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_failure_plateau" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"


def test_implement_v2_runtime_artifact_failure_plateau_clears_stale_but_keeps_same_turn_later_missing(
    tmp_path,
) -> None:
    def frame_contract(contract_id: str) -> dict[str, object]:
        return {
            "id": contract_id,
            "role": "runtime",
            "stage": "verification",
            "purpose": "verification",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "expected_exit": {"mode": "any"},
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "path": "frame.bmp",
                    "checks": [{"type": "exists", "severity": "blocking"}],
                }
            ],
        }

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "same turn passes artifact then regresses it",
            "tool_calls": [
                {
                    "id": "create-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": f"{shlex.quote(sys.executable)} -c \"from pathlib import Path; Path('frame.bmp').write_bytes(b'BM')\"",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                },
                {
                    "id": "verify-frame-pass",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": frame_contract("contract:verify-frame-pass"),
                    },
                },
                {
                    "id": "delete-frame",
                    "name": "run_command",
                    "arguments": {
                        "command": "rm -f frame.bmp",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                },
                {
                    "id": "verify-frame-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": frame_contract("contract:verify-frame-missing"),
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "later artifact regression is still unresolved"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Implement a runtime interpreter so verifier writes frame.bmp.",
                "max_wall_seconds": 600,
            },
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "status": "blocked",
                    "final_artifact": {"path": "frame.bmp", "kind": "file"},
                    "runtime_artifact_failure_plateau": {
                        "failure_class": "runtime_artifact_failure_plateau",
                        "artifact_path": "frame.bmp",
                        "repeat_count": 3,
                    },
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
                "runtime_artifact_failure_plateau_threshold": 3,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_failure_plateau" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"


def test_implement_v2_frontier_retains_source_output_contract_over_model_artifact(tmp_path) -> None:
    source_output = tmp_path / "expected-output.dat"
    model_artifact = tmp_path / "generated.ppm"
    outputs = [
        {
            "summary": "read source output contract",
            "tool_calls": [
                {
                    "id": "source-output-probe",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf '%s\\n' "
                            + shlex.quote(
                                f'src/runtime.c:42: FILE *fp = fopen("{source_output}", "wb"); fwrite(buf, 1, n, fp);'
                            )
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "source output path found"},
        },
        {
            "summary": "run verifier with a conflicting model artifact contract",
            "tool_calls": [
                {
                    "id": "conflicting-runtime-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": f"printf 'missing output artifact {model_artifact}\\n'",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:conflicting-model-artifact",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "zero"},
                            "expected_artifacts": [
                                {
                                    "id": "model-artifact",
                                    "kind": "image",
                                    "path": str(model_artifact),
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "wrong artifact missing"},
        },
    ]

    def fake_model(*_args, **_kwargs):
        return outputs.pop(0)

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Given provided source for a runtime interpreter, implement it so it writes "
                    f"the /tmp-style output artifact {source_output}."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert frontier["source_output_contract"]["path"] == str(source_output)
    assert frontier["final_artifact"]["path"] == str(source_output)
    assert frontier["runtime_artifact_contract_mismatch"]["failure_class"] == "runtime_artifact_contract_mismatch"
    assert frontier["runtime_artifact_contract_mismatch"]["model_declared_path"] == str(model_artifact)
    assert str(source_output) in frontier["runtime_artifact_contract_mismatch"]["required_next_action"]


def test_implement_v2_frontier_does_not_rehydrate_raw_unchecked_expected_artifact() -> None:
    artifact = {"id": "frame", "kind": "file", "path": "/freebsd.png"}
    raw_aliases = (
        {"expected_artifacts": [artifact]},
        {"expected_artifact": artifact},
        {"final_artifact": artifact},
        {"artifacts": [artifact]},
    )
    for raw_alias in raw_aliases:
        result = ToolResultEnvelope(
            lane_attempt_id="lane",
            provider_call_id="outside-artifact-verifier",
            mew_tool_call_id="tool-1",
            tool_name="run_command",
            status="failed",
            content=(
                {
                    "execution_contract": {
                        "id": "contract:runtime-outside-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        **raw_alias,
                    },
                    "execution_contract_normalized": {
                        "id": "contract:runtime-outside-artifact",
                        "role": "runtime",
                        "stage": "verification",
                        "purpose": "verification",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                        "expected_artifacts": [],
                    },
                    "unchecked_expected_artifacts": [
                        {
                            "id": "frame",
                            "path": "/freebsd.png",
                            "reason": "artifact path is outside allowed roots",
                        }
                    ],
                },
            ),
        )

        registry = _frontier_evidence_registry((result,), artifact_namespace="proof-artifacts/test")
        frontier = _frontier_state_from_execution_contracts((result,), registry)

        assert "final_artifact" not in frontier


def test_implement_v2_frontier_reads_source_output_contract_from_nested_tool_payload(tmp_path) -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        provider_call_id="read-runtime-source",
        mew_tool_call_id="mew-read-runtime-source",
        tool_name="read_file",
        status="completed",
        content=(
            {
                "mew_status": "completed",
                "content": [
                    {
                        "path": "src/runtime.c",
                        "text": 'void render(void) { FILE *fp = fopen("/tmp/frame.bmp", "wb"); fwrite(buf, 1, n, fp); }',
                    }
                ],
            },
        ),
        evidence_refs=("implement-v2-read://read-runtime-source/evidence",),
    )
    registry = _frontier_evidence_registry((result,), artifact_namespace="proof-artifacts/test")

    contract = _source_output_contract_from_tool_results((result,), registry)

    assert contract["path"] == "/tmp/frame.bmp"
    assert contract["source_label"] == "read_file:src/runtime.c"
    assert contract["confidence"] == "high"


def test_implement_v2_frontier_does_not_promote_nested_verifier_output_as_source_contract() -> None:
    result = ToolResultEnvelope(
        lane_attempt_id="implement_v2:ws-1:task-1:full",
        provider_call_id="runtime-verifier",
        mew_tool_call_id="mew-runtime-verifier",
        tool_name="run_command",
        status="failed",
        content=(
            {
                "mew_status": "failed",
                "content": [
                    {
                        "command": "node vm.js",
                        "stdout": "saved /tmp/frame.bmp\n",
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                        },
                    }
                ],
            },
        ),
    )
    registry = _frontier_evidence_registry((result,), artifact_namespace="proof-artifacts/test")

    contract = _source_output_contract_from_tool_results((result,), registry)

    assert contract == {}


def test_implement_v2_frontier_ignores_broad_existing_directory_runtime_artifact(tmp_path) -> None:
    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": "Build provided runtime source for an interpreter so node vm.js writes /tmp/frame.bmp."
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=lambda *_args, **_kwargs: {
            "summary": "run verifier with broad directory artifact",
            "tool_calls": [
                {
                    "id": "broad-directory-verifier",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "role": "runtime",
                            "stage": "verify",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "path": str(tmp_path),
                                    "kind": "directory",
                                    "freshness": "exists_before_or_after",
                                    "checks": [{"type": "exists"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "needs concrete artifact"},
        },
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})

    assert frontier["schema_version"] == 1
    assert "final_artifact" not in frontier


def test_implement_v2_frontier_diagnostic_stream_miss_does_not_replace_runtime_failure(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier failed, then a diagnostic stream probe missed its marker",
            "tool_calls": [
                {
                    "id": "runtime-frame-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'vm failed before frame\\n'; exit 1",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-frame-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                },
                {
                    "id": "diagnostic-marker-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "printf 'diagnostic output without marker\\n'",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:diagnostic-marker-missing",
                            "role": "diagnostic",
                            "stage": "diagnostic",
                            "purpose": "diagnostic",
                            "acceptance_kind": "not_acceptance",
                            "expected_artifacts": [
                                {
                                    "target": "stdout",
                                    "checks": [
                                        {"kind": "non_empty"},
                                        {"kind": "text_contains", "value": "TRACE syscall"},
                                    ],
                                }
                            ],
                        },
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert frontier["final_artifact"]["path"].endswith("frame.bmp")
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_failure"
    assert frontier["latest_runtime_failure"]["failure_kind"] == "nonzero_exit"
    assert "latest_build_failure" not in frontier


def test_implement_v2_frontier_closeout_kill_preserves_prior_runtime_failure(tmp_path) -> None:
    calls = {"count": 0}
    long_command = shlex.join(
        [
            sys.executable,
            "-c",
            "import time; print('started', flush=True); time.sleep(5)",
        ]
    )

    def frame_contract() -> dict[str, object]:
        return {
            "id": "contract:runtime-frame",
            "role": "runtime",
            "stage": "verification",
            "purpose": "verification",
            "proof_role": "verifier",
            "acceptance_kind": "external_verifier",
            "expected_exit": 0,
            "expected_artifacts": [
                {
                    "id": "frame",
                    "kind": "file",
                    "path": "frame.bmp",
                    "checks": [{"type": "exists", "severity": "blocking"}],
                }
            ],
        }

    def fake_model(*_args, **_kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            return {
                "summary": "record the actionable runtime artifact miss",
                "tool_calls": [
                    {
                        "id": "runtime-frame-missing",
                        "name": "run_command",
                        "arguments": {
                            "command": "printf 'NO_FRAME\\n'; exit 1",
                            "cwd": ".",
                            "use_shell": True,
                            "timeout": 5,
                            "execution_contract": frame_contract(),
                        },
                    }
                ],
                "finish": {"outcome": "continue", "summary": "repair frame artifact"},
            }
        return {
            "summary": "start a final verifier that cannot close out usefully",
            "tool_calls": [
                {
                    "id": "final-verifier-yield",
                    "name": "run_command",
                    "arguments": {
                        "command": long_command,
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 10,
                        "foreground_budget_seconds": 0.001,
                        "execution_contract": frame_contract(),
                    },
                }
            ],
            "finish": {"outcome": "continue", "summary": "wait for final verifier"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp.", "max_wall_seconds": 600},
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "active_command_auto_poll_seconds": 0,
                "command_closeout_seconds": 0,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=2,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]
    runtime_failure = frontier["latest_runtime_failure"]

    assert result.metrics["orphaned_command_cleanup_count"] == 1
    assert runtime_failure["failure_class"] == "runtime_artifact_missing"
    assert runtime_failure["failure_kind"] == "missing_artifact"
    assert "NO_FRAME" in runtime_failure["stdout_tail"]
    assert "killed" not in runtime_failure["failure_summary"]
    assert "latest_build_failure" not in frontier


def test_implement_v2_frontier_final_artifact_uses_blocking_runtime_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "runtime verifier produced logs and binary but missed final frame",
            "tool_calls": [
                {
                    "id": "runtime-multi-artifact",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            "printf 'VERIFY START\\n' > verify.log\n"
                            "printf 'binary' > doomgeneric_mips\n"
                            "printf 'VM_RC=0\\nProgram terminated at PC=0x0\\nExecuted 34 instructions\\n' > vm.log\n"
                            "printf 'VM_RC=0\\nProgram terminated at PC=0x0\\nExecuted 34 instructions\\nBMP_MISSING\\n'\n"
                            "exit 1"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:runtime-multi-artifact",
                            "role": "generated_artifact",
                            "stage": "verification",
                            "purpose": "build and verify runtime artifact",
                            "proof_role": "final_verifier",
                            "acceptance_kind": "artifact_and_runtime_verification",
                            "expected_exit": 0,
                            "expected_artifacts": [
                                {"path": "verify.log", "checks": [{"kind": "exists"}]},
                                {"path": "doomgeneric_mips", "checks": [{"kind": "exists"}]},
                                {"path": "vm.log", "checks": [{"kind": "exists"}]},
                                {"path": "frame.bmp", "checks": [{"kind": "exists"}]},
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "frame artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run a VM verifier that must produce frame.bmp."},
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "latest_build_failure": {"failure_summary": "stale broad rebuild failure"}
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert frontier["final_artifact"]["path"].endswith("/frame.bmp")
    assert frontier["final_artifact"]["blocking"] is True
    assert "latest_build_failure" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_failure"
    assert frontier["latest_runtime_failure"]["failure_kind"] == "nonzero_exit"
    assert "BMP_MISSING" in frontier["latest_runtime_failure"]["stdout_tail"]


def test_implement_v2_frontier_marker_only_without_contract_is_audit_only() -> None:
    failure = _frontier_failure_payload(
        {
            "command_run_id": "marker-only",
            "exit_code": 1,
            "stdout_tail": "VM_RC=124\nNO_FRAME\n",
            "stderr_tail": "",
        }
    )
    marker = failure["legacy_runtime_marker_fallback"]

    assert "failure_class" not in failure
    assert marker["kind"] == "runtime_execution_timeout"
    assert marker["active"] is False
    assert marker["confidence"] == "low"


def test_implement_v2_frontier_drops_stale_runtime_mismatch_key_after_contract_evidence(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "structured runtime verifier exited without producing declared artifact",
            "tool_calls": [
                {
                    "id": "structured-runtime-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "id": "contract:structured-runtime-missing",
                            "role": "runtime",
                            "stage": "verification",
                            "purpose": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "external_verifier",
                            "expected_exit": {"mode": "any"},
                            "expected_artifacts": [
                                {
                                    "id": "frame",
                                    "kind": "file",
                                    "path": "frame.bmp",
                                    "freshness": "created_after_run_start",
                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                }
                            ],
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "runtime artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={"description": "Run verifier so it writes frame.bmp."},
            persisted_lane_state={
                "lane_hard_runtime_frontier": {
                    "runtime_artifact_contract_mismatch": {
                        "failure_class": "runtime_artifact_contract_mismatch",
                        "failure_summary": "stale marker bridge",
                    }
                }
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "runtime_artifact_contract_mismatch" not in frontier
    assert frontier["latest_runtime_failure"]["failure_class"] == "runtime_artifact_missing"


def test_implement_v2_model_frontier_update_no_longer_infers_same_turn_expected_artifact(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact then run verifier",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {
                    "id": "runtime-from-frontier",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "frontier artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    assert result.metrics["legacy_projection_field_rejected_count"] == 1
    assert payload["failure_class"] == "legacy_projection_field_rejected"
    assert tool_result["status"] == "invalid"
    assert "lane_hard_runtime_frontier" not in result.updated_lane_state


def test_implement_v2_model_frontier_update_no_longer_infers_from_read_only_plus_exec(tmp_path) -> None:
    (tmp_path / "README.md").write_text("frame target\n", encoding="utf-8")

    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact and read context before verifier",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {"id": "read-context", "name": "read_file", "arguments": {"path": "README.md"}},
                {
                    "id": "runtime-from-frontier",
                    "name": "run_command",
                    "arguments": {
                        "command": "true",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {},
                    },
                },
            ],
            "finish": {"outcome": "blocked", "summary": "frontier artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    exec_payload = result.updated_lane_state["proof_manifest"]["tool_results"][1]["content"][0]

    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    assert result.metrics["legacy_projection_field_rejected_count"] == 1
    assert exec_payload["failure_class"] == "legacy_projection_field_rejected"


def test_implement_v2_frontier_update_does_not_infer_artifact_for_mixed_no_contract_exec_turn(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "declare final artifact but run mixed diagnostics",
            "frontier_state_update": {
                "final_artifact": {"path": "frame.bmp", "kind": "file"},
            },
            "tool_calls": [
                {
                    "id": "diagnostic-one",
                    "name": "run_command",
                    "arguments": {"command": "true", "cwd": ".", "use_shell": True, "timeout": 5},
                },
                {
                    "id": "diagnostic-two",
                    "name": "run_command",
                    "arguments": {"command": "true", "cwd": ".", "use_shell": True, "timeout": 5},
                },
            ],
            "finish": {"outcome": "blocked", "summary": "need more evidence"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )
    payloads = [item["content"][0] for item in result.updated_lane_state["proof_manifest"]["tool_results"]]

    assert [payload["failure_class"] for payload in payloads] == [
        "legacy_projection_field_rejected",
        "legacy_projection_field_rejected",
    ]
    assert result.metrics["legacy_projection_field_rejected_count"] == 1


def test_implement_v2_frontier_does_not_classify_build_artifact_missing_as_runtime(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        failure_script = (
            "import sys; "
            "print('Executed 7 build steps'); "
            "print('required build artifact was not created'); "
            "sys.stderr.write('link failed before binary existed\\n'); "
            "sys.exit(2)"
        )
        return {
            "summary": "build artifact missing before runtime",
            "tool_calls": [
                {
                    "id": "build-artifact-missing",
                    "name": "run_command",
                    "arguments": {
                        "command": (
                            f"printf 'make all started\\n'; "
                            f"{shlex.quote(sys.executable)} -c {shlex.quote(failure_script)}"
                        ),
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "execution_contract": {
                            "purpose": "build",
                            "stage": "build",
                            "proof_role": "builder",
                            "target": "compiled artifact",
                        },
                    },
                }
            ],
            "finish": {"outcome": "blocked", "summary": "build artifact missing"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "Build the provided source for vm.js so the emulator writes /tmp/frame.bmp "
                    "from the runtime artifact."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "terminal_failure_reaction_turns": 0,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state["lane_hard_runtime_frontier"]

    assert "latest_runtime_failure" not in frontier
    assert frontier["latest_build_failure"]["failure_summary"] == "link failed before binary existed"


def test_implement_v2_ignores_model_only_frontier_failures_and_artifact_refs(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "model only frontier",
            "frontier_state_update": {
                "latest_build_failure": {
                    "command_run_id": "fabricated",
                    "exit_code": 99,
                    "stderr_tail": "fake failure",
                },
                "source_roles": [
                    {
                        "path": "manifest",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "implement-lane/implement_v2/ws-1/task-1/proof-manifest.json",
                            }
                        ],
                    },
                    {
                        "path": "evil",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "implement-lane/implement_v2/ws-1/task-1_evil/proof-manifest.json",
                            }
                        ],
                    },
                    {
                        "path": "traversal",
                        "role": "test_harness",
                        "state": "grounded",
                        "evidence_refs": [
                            {
                                "kind": "proof_artifact",
                                "path": "../implement-lane/implement_v2/ws-1/task-1/proof-manifest.json",
                            }
                        ],
                    },
                ],
            },
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})

    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    assert "latest_build_failure" not in frontier
    assert "source_roles" not in frontier
    assert "implement-lane/implement_v2/ws-1/task-1" not in json.dumps(frontier, sort_keys=True)


def test_implement_v2_frontier_tracks_routed_tool_contract_next_verifier(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "final verifier through wrong tool",
            "tool_calls": [
                {
                    "id": "verify-1",
                    "name": "run_tests",
                    "arguments": {
                        "command": "printf ok > frame.txt && test -s frame.txt",
                        "cwd": ".",
                        "use_shell": True,
                        "timeout": 5,
                        "foreground_budget_seconds": 1,
                        "execution_contract": {
                            "purpose": "verification",
                            "stage": "verification",
                            "proof_role": "verifier",
                            "acceptance_kind": "candidate_final_proof",
                        },
                    },
                }
            ],
            "finish": {"outcome": "continue"},
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "allow_verify": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    next_verifier = result.updated_lane_state["lane_hard_runtime_frontier"]["next_verifier_shaped_command"]

    assert next_verifier["tool"] == "run_command"
    assert next_verifier["use_shell"] is True
    assert "printf ok > frame.txt" in next_verifier["command"]
    assert next_verifier["execution_contract"]["proof_role"] == "verifier"
    assert next_verifier["evidence_refs"]


def test_implement_v2_frontier_state_does_not_satisfy_finish_gate_without_terminal_evidence(tmp_path) -> None:
    def fake_model(*_args, **_kwargs):
        return {
            "summary": "claim from state only",
            "frontier_state_update": {
                "status": "resolved",
                "final_artifact": {
                    "path": "/tmp/frame.bmp",
                    "kind": "image",
                    "freshness": "fresh verifier-shaped command",
                    "evidence_refs": [{"kind": "evidence_ref", "ref": "fabricated"}],
                },
            },
            "finish": {
                "outcome": "completed",
                "summary": "state says artifact exists",
                "acceptance_evidence": ["frontier says frame exists"],
            },
        }

    result = run_live_json_implement_v2(
        ImplementLaneInput(
            work_session_id="ws-1",
            task_id="task-1",
            workspace=str(tmp_path),
            lane=IMPLEMENT_V2_LANE,
            model_backend="codex",
            model="gpt-5.5",
            task_contract={
                "description": (
                    "I provided source code and vm.js expects a binary. Build the source "
                    "so node vm.js writes /tmp/frame.bmp."
                )
            },
            lane_config={
                "mode": "full",
                "allowed_read_roots": [str(tmp_path)],
                "allowed_write_roots": [str(tmp_path)],
                "allow_shell": True,
                "debug_model_frontier_update": True,
            },
        ),
        model_auth={"path": "auth.json"},
        model_json_callable=fake_model,
        max_turns=1,
    )

    frontier = result.updated_lane_state.get("lane_hard_runtime_frontier", {})

    assert result.status == "blocked"
    assert result.metrics["terminal_evidence_count"] == 0
    assert result.metrics["ignored_model_frontier_state_updates"] == 1
    assert result.metrics["legacy_projection_field_rejected_count"] == 1
    assert "final_artifact" not in frontier
    assert result.metrics["finish_gate_decision"].get("decision") != "allow_complete"


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
            artifact_dir=tmp_path / "artifacts",
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
    assert tool_result["content_refs"]
    mutation = tool_result["content"][0]["typed_source_mutation"]
    assert mutation["kind"] == "typed_source_mutation"
    assert mutation["tool_route"] == "typed_source_mutation"
    assert mutation["diff_ref"] == tool_result["content"][0]["source_diff_ref"]
    assert mutation["snapshots"]["pre"]["existed"] is False
    assert mutation["snapshots"]["post"]["sha256"]
    assert tool_result["evidence_refs"] == [mutation["mutation_ref"]]
    assert "out.txt" in Path(mutation["diff_ref"]).read_text(encoding="utf-8")
    assert tool_result["content"][0]["source_snapshot_refs"]["pre"] in tool_result["content_refs"]
    assert tool_result["content"][0]["source_snapshot_refs"]["post"] in tool_result["content_refs"]
    assert tool_result["side_effects"][0]["record"]["mutation_ref"] == mutation["mutation_ref"]
    assert tool_result["side_effects"][0]["diff_ref"] == mutation["diff_ref"]
    assert tool_result["content"][0]["approval_id"] == "approval-1"
    assert tool_result["side_effects"][0]["approval_status"] == "approved"
    assert tool_result["side_effects"][0]["approval_id"] == "approval-1"


def test_implement_v2_hard_runtime_write_file_is_unavailable_for_source_mutation(tmp_path) -> None:
    target = tmp_path / "vm.js"

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
            task_contract={
                "goal": (
                    "Build a MIPS ELF interpreter runtime from provided source and write "
                    "a /tmp/frame.bmp artifact."
                )
            },
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "write_file",
                "arguments": {
                    "path": "vm.js",
                    "content_lines": ["console.log('bad');"],
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "hard runtime write rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "invalid"
    assert tool_result["is_error"] is True
    assert "write_file is not available" in payload["reason"]
    assert not target.exists()
    assert result.metrics.get("write_evidence_count", 0) == 0


def test_implement_v2_write_file_rejects_large_single_line_source(tmp_path) -> None:
    target = tmp_path / "vm.js"
    single_line_source = "const fs = require('fs');" + ("x" * 5000)

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
                    "path": "vm.js",
                    "content": single_line_source,
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "single-line source rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload["failure_class"] == "source_mutation_unreadable_long_line"
    assert payload["line_chars"] > payload["max_line_chars"]
    assert "readable multi-line code" in payload["suggested_next_action"]
    assert not target.exists()


def test_implement_v2_write_file_allows_large_multiline_source(tmp_path) -> None:
    target = tmp_path / "vm.js"
    multiline_source = "\n".join(f"const value{index} = {index};" for index in range(400)) + "\n"

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
                    "path": "vm.js",
                    "content": multiline_source,
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "multiline source applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == multiline_source


def test_implement_v2_write_file_accepts_content_lines_for_large_source(tmp_path) -> None:
    target = tmp_path / "vm.js"
    content_lines = [f"const value{index} = {index};" for index in range(400)]
    expected = "\n".join(content_lines) + "\n"

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
                    "path": "vm.js",
                    "content_lines": content_lines,
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "content_lines source applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == expected


def test_implement_v2_write_file_allows_large_single_line_non_source(tmp_path) -> None:
    target = tmp_path / "data.txt"
    one_line_data = "x" * 5000

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
                    "path": "data.txt",
                    "content": one_line_data,
                    "create": True,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "large data line applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == one_line_data


def test_implement_v2_edit_file_rejects_new_large_single_line_source(tmp_path) -> None:
    target = tmp_path / "vm.js"
    target.write_text("console.log('old');\n", encoding="utf-8")
    long_line = "const generated = '" + ("x" * 5000) + "';\n"

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
                "tool_name": "edit_file",
                "arguments": {
                    "path": "vm.js",
                    "old_string": "console.log('old');\n",
                    "new_string": long_line,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "single-line edit rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload["failure_class"] == "source_mutation_unreadable_long_line"
    assert payload["reason"]
    assert target.read_text(encoding="utf-8") == "console.log('old');\n"


def test_implement_v2_edit_file_allows_unchanged_large_line_context(tmp_path) -> None:
    target = tmp_path / "vm.js"
    long_line = "const fixture = '" + ("x" * 5000) + "';\n"
    old_text = long_line + "console.log('old');\n"
    new_text = long_line + "console.log('new');\n"
    target.write_text(old_text, encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
            ),
            artifact_dir=tmp_path / "artifacts",
        ),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {
                    "path": "vm.js",
                    "old_string": old_text,
                    "new_string": new_text,
                    "apply": True,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "small edit with long context applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == new_text
    mutation = tool_result["content"][0]["typed_source_mutation"]
    assert mutation["operation"] == "edit_file"
    assert mutation["snapshots"]["pre"]["sha256"] != mutation["snapshots"]["post"]["sha256"]
    assert mutation["diff_ref"] in tool_result["content_refs"]
    assert tool_result["evidence_refs"] == [mutation["mutation_ref"]]
    assert "vm.js" in Path(mutation["diff_ref"]).read_text(encoding="utf-8")


def test_implement_v2_apply_patch_rejects_new_large_single_line_source(tmp_path) -> None:
    target = tmp_path / "vm.js"
    target.write_text("console.log('old');\n", encoding="utf-8")
    long_line = "const generated = '" + ("x" * 5000) + "';\n"
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        "-console.log('old');\n"
        f"+{long_line}"
        "*** End Patch\n"
    )

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
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "single-line patch rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert payload["failure_class"] == "source_mutation_unreadable_long_line"
    assert target.read_text(encoding="utf-8") == "console.log('old');\n"


def test_implement_v2_apply_patch_allows_unchanged_large_line_context(tmp_path) -> None:
    target = tmp_path / "vm.js"
    long_line = "const fixture = '" + ("x" * 5000) + "';\n"
    old_text = long_line + "console.log('old');\n"
    new_text = long_line + "console.log('new');\n"
    target.write_text(old_text, encoding="utf-8")
    patch = (
        "*** Begin Patch\n"
        "*** Update File: vm.js\n"
        "@@\n"
        f" {long_line}"
        "-console.log('old');\n"
        "+console.log('new');\n"
        "*** End Patch\n"
    )

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
                "tool_name": "apply_patch",
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "small patch with long context applied"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert target.read_text(encoding="utf-8") == new_text


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
                    "expected_pre_sha256": hashlib.sha256(b"irrelevant").hexdigest(),
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "outside rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert tool_result["content"][0]["failure_class"] == "path_policy_failure"
    assert tool_result["content"][0]["failure_subclass"] == "write_path_policy_rejected"
    assert tool_result["content"][0]["recoverable"] is True
    assert "outside allowed write roots" in tool_result["content"][0]["reason"]
    assert not outside.exists()


def test_implement_v2_write_rejects_stale_precondition_without_mutation_evidence(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    stale_sha = hashlib.sha256("old\n".encode()).hexdigest()
    target.write_text("changed elsewhere\n", encoding="utf-8")

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
                    "path": "README.md",
                    "content": "new\n",
                    "apply": True,
                    "expected_pre_sha256": stale_sha,
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "stale write rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]
    payload = tool_result["content"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert not tool_result["evidence_refs"]
    assert payload["failure_class"] == "stale_source_precondition"
    assert payload["failure_subclass"] == "pre_snapshot_sha_mismatch"
    assert payload["expected_pre_sha256"] == stale_sha
    assert target.read_text(encoding="utf-8") == "changed elsewhere\n"


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


def test_implement_v2_edit_file_exact_miss_returns_nearest_existing_windows(tmp_path) -> None:
    target = tmp_path / "worker.txt"
    target.write_text(
        "".join(f"commonIdentifier filler {index}\n" for index in range(120))
        + "commonIdentifier actualCall rareWidget\n",
        encoding="utf-8",
    )

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {
                    "path": "worker.txt",
                    "old_string": "commonIdentifier missingCall rareWidget",
                    "new_string": "commonIdentifier replacementCall rareWidget",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "exact miss recovery"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["failure_class"] == "edit_exact_match_miss"
    assert payload["recoverable"] is True
    assert payload["suggested_tool"] == "read_file/edit_file/apply_patch"
    assert payload["old_string_preview"] == "commonIdentifier missingCall rareWidget"
    assert "commonIdentifier actualCall rareWidget" in payload["nearest_existing_windows"][0]["text"]
    assert payload["suggested_recovery_calls"][0]["tool_name"] == "read_file"
    assert payload["suggested_recovery_calls"][0]["path"].endswith("worker.txt")
    assert payload["suggested_recovery_calls"][0]["max_chars"] <= 2000
    assert "whole file" in payload["suggested_recovery_calls"][0]["reason"]
    assert "line_start" not in payload["suggested_recovery_calls"][0]
    recovery_read = read_file(
        payload["suggested_recovery_calls"][0]["path"],
        [tmp_path],
        offset=payload["suggested_recovery_calls"][0]["offset"],
        max_chars=payload["suggested_recovery_calls"][0]["max_chars"],
    )
    assert "commonIdentifier actualCall rareWidget" in recovery_read["text"]
    assert target.read_text(encoding="utf-8").endswith("commonIdentifier actualCall rareWidget\n")


def test_implement_v2_edit_file_accepts_common_string_aliases(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("alpha\n", encoding="utf-8")

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "edit_file",
                "arguments": {
                    "path": "README.md",
                    "old_string": "alpha\n",
                    "new_string": "beta\n",
                },
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "edit preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "analysis_ready"
    assert tool_result["status"] == "completed"
    assert tool_result["content"][0]["dry_run"] is True
    assert "beta" in tool_result["content"][0]["diff"]
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


def test_implement_v2_apply_patch_exact_miss_returns_anchor_windows(tmp_path) -> None:
    target = tmp_path / "worker.txt"
    target.write_text(
        "function actualCall() {\n  return rareWidget;\n}\n",
        encoding="utf-8",
    )
    patch = (
        "*** Begin Patch\n"
        "*** Update File: worker.txt\n"
        "@@\n"
        "-function missingCall() {\n"
        "-  return rareWidget;\n"
        "-}\n"
        "+function replacementCall() {\n"
        "+  return rareWidget;\n"
        "+}\n"
        "*** End Patch\n"
    )

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch exact miss recovery"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["failure_class"] == "patch_anchor_mismatch"
    assert payload["failure_subclass"] == "patch_exact_match_miss"
    assert payload["recoverable"] is True
    assert payload["suggested_tool"] == "read_file/apply_patch/edit_file"
    assert payload["patch_anchor_windows"][0]["hunk_index"] == 1
    assert "actualCall" in payload["patch_anchor_windows"][0]["nearest_existing_windows"][0]["text"]
    assert payload["suggested_recovery_calls"][0]["tool_name"] == "read_file"
    assert payload["suggested_recovery_calls"][0]["path"].endswith("worker.txt")
    assert payload["suggested_recovery_calls"][0]["max_chars"] <= 2000
    assert "line_start" not in payload["suggested_recovery_calls"][0]
    recovery_read = read_file(
        payload["suggested_recovery_calls"][0]["path"],
        [tmp_path],
        offset=payload["suggested_recovery_calls"][0]["offset"],
        max_chars=payload["suggested_recovery_calls"][0]["max_chars"],
    )
    assert "actualCall" in recovery_read["text"]
    assert target.read_text(encoding="utf-8").startswith("function actualCall")


def test_implement_v2_apply_patch_lines_exact_miss_returns_anchor_windows(tmp_path) -> None:
    target = tmp_path / "worker.txt"
    target.write_text(
        "function actualCall() {\n  return rareWidget;\n}\n",
        encoding="utf-8",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: worker.txt",
        "@@",
        "-function missingCall() {",
        "-  return rareWidget;",
        "-}",
        "+function replacementCall() {",
        "+  return rareWidget;",
        "+}",
        "*** End Patch",
    ]

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-lines", "tool_name": "apply_patch", "arguments": {"patch_lines": patch_lines}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch lines exact miss recovery"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["failure_class"] == "patch_anchor_mismatch"
    assert payload["failure_subclass"] == "patch_exact_match_miss"
    assert payload["patch_transport"]["transport"] == "patch_lines"
    assert payload["patch_transport"]["line_count"] == len(patch_lines)
    assert payload["patch_anchor_windows"][0]["hunk_index"] == 1
    assert "actualCall" in payload["patch_anchor_windows"][0]["nearest_existing_windows"][0]["text"]
    assert payload["suggested_recovery_calls"][0]["tool_name"] == "read_file"


def test_implement_v2_apply_patch_ambiguous_match_returns_matching_windows(tmp_path) -> None:
    target = tmp_path / "worker.txt"
    target.write_text(
        "same();\nalpha();\nsame();\nbeta();\n",
        encoding="utf-8",
    )
    patch = (
        "*** Begin Patch\n"
        "*** Update File: worker.txt\n"
        "@@\n"
        "-same();\n"
        "+different();\n"
        "*** End Patch\n"
    )

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch ambiguous recovery"},
    )
    payload = result.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert payload["failure_class"] == "patch_anchor_mismatch"
    assert payload["failure_subclass"] == "patch_ambiguous_anchor"
    assert payload["patch_anchor_windows"][0]["hunk_index"] == 1
    assert len(payload["patch_anchor_windows"][0]["matching_existing_windows"]) == 2
    assert payload["suggested_recovery_calls"][0]["tool_name"] == "read_file"
    assert payload["suggested_recovery_calls"][0]["path"].endswith("worker.txt")
    recovery_read = read_file(
        payload["suggested_recovery_calls"][0]["path"],
        [tmp_path],
        offset=payload["suggested_recovery_calls"][0]["offset"],
        max_chars=payload["suggested_recovery_calls"][0]["max_chars"],
    )
    assert "same();" in recovery_read["text"]
    assert "old text matched 2 times" in payload["reason"]
    assert target.read_text(encoding="utf-8") == "same();\nalpha();\nsame();\nbeta();\n"


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
    payload = tool_result["content"][0]
    assert "must start with *** Begin Patch" in payload["reason"]
    assert payload["failure_class"] == "patch_parse_error"
    assert payload["recoverable"] is True
    assert payload["suggested_tool"] == "apply_patch/edit_file"
    assert payload["patch_transport"]["line_count"] == 1
    assert payload["patch_transport"]["hash"] == "sha256:" + hashlib.sha256("*** End Patch\n".encode()).hexdigest()
    assert payload["patch_transport"]["sha256"] == "sha256:" + hashlib.sha256("*** End Patch\n".encode()).hexdigest()


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
            artifact_dir=tmp_path / "artifacts",
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
    dry_payload = dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    assert dry_payload["dry_run"] is True
    assert dry_payload["patch_transport"]["transport"] == "legacy_patch_string"
    assert apply.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "new\n"
    apply_result = apply.updated_lane_state["proof_manifest"]["tool_results"][0]
    mutation = apply_result["content"][0]["typed_source_mutation"]
    assert apply_result["evidence_refs"] == [mutation["mutation_ref"]]
    assert mutation["operation"] == "apply_patch"
    assert mutation["diff_ref"] in apply_result["content_refs"]
    assert "README.md" in Path(mutation["diff_ref"]).read_text(encoding="utf-8")
    assert apply_result["content"][0]["source_snapshot_refs"]["pre"] in apply_result["content_refs"]
    assert apply_result["content"][0]["source_snapshot_refs"]["post"] in apply_result["content_refs"]


def test_implement_v2_apply_patch_lines_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch_lines = ["*** Begin Patch", "*** Update File: README.md", "@@", "-old", "+new", "*** End Patch"]
    patch_text = "\n".join(patch_lines) + "\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-lines",
                "tool_name": "apply_patch",
                "arguments": {"patch_lines": patch_lines},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch lines preview"},
    )

    dry_payload = dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]
    assert dry_run.status == "analysis_ready"
    assert dry_payload["dry_run"] is True
    assert dry_payload["patch_transport"]["transport"] == "patch_lines"
    assert dry_payload["patch_transport"]["paths"] == ["README.md"]
    assert dry_payload["patch_transport"]["line_count"] == len(patch_lines)
    assert dry_payload["patch_transport"]["hash"] == "sha256:" + hashlib.sha256(patch_text.encode()).hexdigest()
    assert dry_payload["patch_transport"]["sha256"] == "sha256:" + hashlib.sha256(patch_text.encode()).hexdigest()
    assert target.read_text(encoding="utf-8") == "old\n"

    apply = run_fake_write_implement_v2(
        _write_lane_input(
            tmp_path,
            approved_write_calls=(
                {"provider_call_id": "call-lines", "status": "approved", "approval_id": "approval-lines"},
            ),
        ),
        provider_calls=(
            {
                "provider_call_id": "call-lines",
                "tool_name": "apply_patch",
                "arguments": {"patch_lines": patch_lines, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch lines applied"},
    )

    apply_payload = apply.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]

    assert target.read_text(encoding="utf-8") == "new\n"
    assert apply.status == "analysis_ready"
    assert apply_payload["dry_run"] is False
    assert apply_payload["patch_operation"] == "update_file"


def test_implement_v2_apply_patch_accepts_redundant_matching_path(tmp_path) -> None:
    target = tmp_path / "README.md"
    target.write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"path": "README.md", "patch": patch},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert result.status == "analysis_ready"
    assert result.updated_lane_state["proof_manifest"]["tool_results"][0]["status"] == "completed"


def test_implement_v2_apply_patch_rejects_mismatched_redundant_path(tmp_path) -> None:
    (tmp_path / "README.md").write_text("old\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Update File: README.md\n@@\n-old\n+new\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {
                "provider_call_id": "call-1",
                "tool_name": "apply_patch",
                "arguments": {"path": "OTHER.md", "patch": patch},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "path argument must match" in tool_result["content"][0]["reason"]


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


def test_implement_v2_apply_patch_add_file_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "new.txt"
    patch = "*** Begin Patch\n*** Add File: new.txt\n+hello\n+world\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["patch_operation"] == "add_file"
    assert not target.exists()

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
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert apply.status == "analysis_ready"
    assert target.read_text(encoding="utf-8") == "hello\nworld\n"
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_add_file_rejects_existing_target(tmp_path) -> None:
    (tmp_path / "new.txt").write_text("existing\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Add File: new.txt\n+replacement\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "already exists" in tool_result["content"][0]["reason"]
    assert (tmp_path / "new.txt").read_text(encoding="utf-8") == "existing\n"


def test_implement_v2_apply_patch_delete_file_dry_run_and_approved_apply(tmp_path) -> None:
    target = tmp_path / "old.txt"
    target.write_text("remove me\n", encoding="utf-8")
    patch = "*** Begin Patch\n*** Delete File: old.txt\n*** End Patch\n"

    dry_run = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch preview"},
    )

    assert dry_run.status == "analysis_ready"
    assert dry_run.updated_lane_state["proof_manifest"]["tool_results"][0]["content"][0]["patch_operation"] == "delete_file"
    assert target.exists()

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
                "arguments": {"patch": patch, "apply": True},
            },
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "patch applied"},
    )

    assert apply.status == "analysis_ready"
    assert not target.exists()
    assert apply.updated_lane_state["proof_manifest"]["tool_results"][0]["evidence_refs"]


def test_implement_v2_apply_patch_delete_file_rejects_symlink_path(tmp_path) -> None:
    target = tmp_path / "real.txt"
    target.write_text("keep me\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)
    patch = "*** Begin Patch\n*** Delete File: link.txt\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "delete rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "refuses symlink paths" in tool_result["content"][0]["reason"]
    assert link.is_symlink()
    assert target.read_text(encoding="utf-8") == "keep me\n"


def test_implement_v2_apply_patch_add_file_rejects_dangling_symlink_target(tmp_path) -> None:
    link = tmp_path / "new.txt"
    link.symlink_to(tmp_path / "missing-target.txt")
    patch = "*** Begin Patch\n*** Add File: new.txt\n+replacement\n*** End Patch\n"

    result = run_fake_write_implement_v2(
        _write_lane_input(tmp_path),
        provider_calls=(
            {"provider_call_id": "call-1", "tool_name": "apply_patch", "arguments": {"patch": patch}},
        ),
        finish_arguments={"outcome": "analysis_ready", "summary": "add rejected"},
    )
    tool_result = result.updated_lane_state["proof_manifest"]["tool_results"][0]

    assert result.status == "blocked"
    assert tool_result["status"] == "failed"
    assert "already exists" in tool_result["content"][0]["reason"]
    assert link.is_symlink()


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


def _write_lane_input(
    tmp_path,
    *,
    approved_write_calls=(),
    task_contract: dict[str, object] | None = None,
    artifact_dir=None,
) -> ImplementLaneInput:
    lane_config = {
        "mode": "write",
        "allowed_write_roots": ["."],
        "approved_write_calls": list(approved_write_calls),
    }
    if artifact_dir is not None:
        lane_config["artifact_dir"] = str(artifact_dir)
    return ImplementLaneInput(
        work_session_id="ws-1",
        task_id="task-1",
        workspace=str(tmp_path),
        lane=IMPLEMENT_V2_LANE,
        lane_config=lane_config,
        task_contract=task_contract or {},
    )


def _without_schema_version(item: dict[str, object]) -> dict[str, object]:
    return {key: value for key, value in item.items() if key != "schema_version"}
