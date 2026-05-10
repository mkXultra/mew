import json

from mew.implement_lane.workframe import (
    LEGACY_PROMPT_PROJECTION_IDS,
    WorkFrameInputs,
    canonicalize_workframe_inputs,
    check_phase0_prompt_inventory,
    record_phase0_baseline_metrics,
    reduce_workframe,
    workframe_debug_bundle_format,
    workframe_output_hash,
)


def _workframe_inputs() -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-3",
        task_id="task-1",
        objective="Repair the workspace to satisfy the configured verifier.",
        success_contract_ref="task-contract:verify",
        constraints=("use_workspace_tools", "no_task_specific_solver"),
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "vm.js",
                "evidence_refs": ["sidecar:write:1"],
                "timestamp": "volatile",
            },
            {
                "kind": "strict_verifier",
                "event_sequence": 2,
                "event_id": "cmd-2",
                "status": "failed",
                "family": "runtime_verifier_failure",
                "summary": "TypeError: this.check is not a function",
                "target_paths": ["vm.js"],
                "command_run_id": "cmd:run-2",
                "evidence_refs": ["ev:verifier:run-2"],
            },
        ),
    )


def test_workframe_reducer_is_deterministic_and_evidence_referenced() -> None:
    inputs = _workframe_inputs()

    first, first_report = reduce_workframe(inputs)
    second, second_report = reduce_workframe(inputs)

    assert first_report.status == "pass"
    assert second_report.status == "pass"
    assert first.as_dict() == second.as_dict()
    assert first.current_phase == "repair_after_verifier_failure"
    assert first.latest_actionable
    assert first.latest_actionable.family == "runtime_verifier_failure"
    assert first.required_next
    assert first.required_next.kind == "patch_or_edit"
    assert first.required_next.target_paths == ("vm.js",)
    assert "finish" in [item.kind for item in first.forbidden_next]
    assert first.changed_sources.since_last_strict_verifier is True
    assert first.verifier_state.status == "failed"
    assert "ev:verifier:run-2" in first.evidence_refs.typed
    assert first.trace.output_hash == workframe_output_hash(first)
    serialized = first.as_dict()
    assert set(serialized) >= {
        "latest_actionable",
        "required_next",
        "forbidden_next",
        "changed_sources",
        "verifier_state",
        "finish_readiness",
        "evidence_refs",
    }


def test_workframe_canonicalization_removes_volatile_fields_and_is_stable() -> None:
    inputs = _workframe_inputs()
    canonical = canonicalize_workframe_inputs(inputs)
    serialized = json.dumps(canonical, sort_keys=True)

    assert "volatile" not in serialized
    assert canonical["reducer_schema_version"] == 1
    events = canonical["payload"]["sidecar_events"]
    assert [event["event_sequence"] for event in events] == [1, 2]


def test_workframe_canonicalization_normalizes_nested_volatility_and_roots() -> None:
    left = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        workspace_root="/tmp/work-a",
        artifact_root="/tmp/artifacts-a",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "payload": {
                    "path": "/tmp/work-a/src/vm.js",
                    "pid": 111,
                    "nested": {"mtime": 123, "provider_latency_ms": 9.0},
                },
                "artifact_path": "/tmp/artifacts-a/run/output.log",
            },
        ),
    )
    right = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        workspace_root="/var/work-b",
        artifact_root="/var/artifacts-b",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "payload": {
                    "path": "/var/work-b/src/vm.js",
                    "pid": 222,
                    "nested": {"mtime": 999, "provider_latency_ms": 42.0},
                },
                "artifact_path": "/var/artifacts-b/run/output.log",
            },
        ),
    )

    assert canonicalize_workframe_inputs(left) == canonicalize_workframe_inputs(right)
    serialized = json.dumps(canonicalize_workframe_inputs(left), sort_keys=True)
    assert "/tmp/work-a" not in serialized
    assert "$WORKSPACE/src/vm.js" in serialized
    assert "$ARTIFACT/run/output.log" in serialized
    assert "provider_latency" not in serialized


def test_workframe_canonicalization_preserves_distinct_unrooted_absolute_paths() -> None:
    left = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "/tmp/a/out.log",
            },
        ),
    )
    right = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair.",
        sidecar_events=(
            {
                "kind": "source_mutation",
                "event_sequence": 1,
                "event_id": "write-1",
                "path": "/var/b/out.log",
            },
        ),
    )

    left_serialized = json.dumps(canonicalize_workframe_inputs(left), sort_keys=True)
    right_serialized = json.dumps(canonicalize_workframe_inputs(right), sort_keys=True)

    assert left_serialized != right_serialized
    assert "/tmp/a/out.log" not in left_serialized
    assert "/var/b/out.log" not in right_serialized
    assert "$ABSOLUTE/" in left_serialized
    assert "$ABSOLUTE/" in right_serialized


def test_workframe_failed_write_is_not_counted_as_source_mutation() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Repair failed write handling.",
        sidecar_events=(
            {
                "kind": "write",
                "event_sequence": 1,
                "event_id": "write-1",
                "status": "failed",
                "family": "write_payload_invalid",
                "summary": "write_file payload was invalid",
                "path": "vm.js",
                "evidence_refs": ["ev:write-failed"],
            },
        ),
    )

    workframe, report = reduce_workframe(inputs)

    assert report.status == "pass"
    assert workframe.current_phase == "repair_after_write_failure"
    assert workframe.changed_sources.paths == ()
    assert workframe.changed_sources.since_last_strict_verifier is False
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "write_payload_invalid"
    assert workframe.required_next
    assert workframe.required_next.kind == "patch_or_edit"


def test_workframe_ignores_stale_verifier_failure_after_source_mutation() -> None:
    inputs = WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-2",
        task_id="task-1",
        objective="Repair stale verifier handling.",
        sidecar_events=(
            {
                "kind": "strict_verifier",
                "event_sequence": 1,
                "event_id": "verify-1",
                "status": "failed",
                "family": "old_runtime_failure",
                "summary": "old failure before patch",
                "evidence_refs": ["ev:old-failure"],
            },
            {
                "kind": "source_mutation",
                "event_sequence": 2,
                "event_id": "patch-2",
                "path": "vm.js",
                "evidence_refs": ["sidecar:patch-2"],
            },
        ),
    )

    workframe, report = reduce_workframe(inputs)

    assert report.status == "pass"
    assert workframe.current_phase == "verify_after_mutation"
    assert workframe.latest_actionable
    assert workframe.latest_actionable.family == "verifier_stale_after_mutation"
    assert workframe.required_next
    assert workframe.required_next.kind == "run_verifier"
    assert "old_runtime_failure" not in json.dumps(workframe.as_dict(), sort_keys=True)


def test_workframe_phase0_prompt_inventory_checker_detects_legacy_projection_presence() -> None:
    inventory = [
        {"id": section_id, "visibility": "ordinary", "bytes": 32}
        for section_id in LEGACY_PROMPT_PROJECTION_IDS
    ]

    passing = check_phase0_prompt_inventory(inventory)
    assert passing["status"] == "pass"
    assert passing["missing_legacy_ids"] == []

    failing_inventory = [item for item in inventory if item["id"] != LEGACY_PROMPT_PROJECTION_IDS[0]]
    failing = check_phase0_prompt_inventory(failing_inventory)
    assert failing["status"] == "fail"
    assert failing["missing_legacy_ids"] == [LEGACY_PROMPT_PROJECTION_IDS[0]]


def test_workframe_phase0_baseline_metrics_record_required_fields() -> None:
    workframe, report = reduce_workframe(_workframe_inputs())
    assert report.status == "pass"
    manifest = {
        "metrics": {
            "hot_path_projection": {
                "normal_full_prompt_bytes_total": 20000,
                "normal_dynamic_hot_path_bytes": 8000,
                "provider_visible_tool_result_bytes": 1500,
                "required_next_adherence": 0.91,
            },
            "resident_sidecar_state": {
                "total_bytes": 120000,
                "per_turn_growth_bytes": 4000,
            },
        }
    }
    history = [
        {
            "turn": 1,
            "elapsed_seconds": 10,
            "tool_calls": [{"tool_name": "read_file"}],
            "tool_results": [],
        },
        {
            "turn": 2,
            "elapsed_seconds": 20,
            "tool_calls": [{"tool_name": "apply_patch"}],
            "tool_results": [],
        },
        {
            "turn": 3,
            "elapsed_seconds": 40,
            "tool_calls": [{"tool_name": "run_tests"}],
            "tool_results": [
                {"content": {"latest_failure": {"class": "runtime_failure", "kind": "nonzero_exit"}}}
            ],
        },
    ]

    result = record_phase0_baseline_metrics(manifest, history, workframe=workframe)

    assert result["status"] == "pass"
    baseline = result["baseline"]
    assert baseline["B_prompt_normal_total"] == 20000
    assert baseline["B_first_edit_turn"] == 2
    assert baseline["B_first_verifier_turn"] == 3
    assert baseline["B_model_turns_10m"] == 3
    assert baseline["B_tool_calls_10m"] == 3
    assert baseline["B_workframe_bytes"] > 0
    assert "B_workframe_bytes" in result["bands"]


def test_workframe_debug_bundle_format_lists_required_phase0_files() -> None:
    bundle = workframe_debug_bundle_format()

    assert bundle["root"] == "implement_v2/workframes/turn-XXXX/"
    assert "reducer_inputs.json" in bundle["files"]
    assert "invariant_report.json" in bundle["files"]
    assert "prompt_render_inventory.json" in bundle["files"]
