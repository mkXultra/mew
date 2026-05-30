import json

from mew.implement_lane.tool_profiles.mew_legacy import list_v2_tool_specs_for_mode
from mew.implement_lane.workframe import WorkFrameInputs
from mew.legacy_experiments.workframe_variants import project_workframe_with_variant


def _project(events: tuple[dict[str, object], ...], *, provider_tool_names: tuple[str, ...] = ()) -> dict[str, object]:
    inputs = WorkFrameInputs(
        attempt_id="attempt-nav",
        turn_id="turn-nav",
        task_id="task-nav",
        objective="Repair the runtime failure.",
        sidecar_events=events,
        baseline_metrics={"provider_tool_names": list(provider_tool_names)} if provider_tool_names else {},
    )
    return project_workframe_with_variant(inputs, variant="transcript_tool_nav").workframe.as_dict()


def test_transcript_tool_nav_projects_advisory_tool_context_without_default_flip() -> None:
    workframe = _project(
        (
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
    )
    tool_context = workframe["tool_context"]

    assert workframe["schema_version"] == 3
    assert workframe["variant"]["name"] == "transcript_tool_nav"
    assert tool_context["recommended_tool_refs"]
    assert workframe["required_next"] is None
    assert workframe["latest_actionable"]["summary"] == "TypeError: cannot read property 'pc' of undefined"
    assert "tool:finish" in {item["tool_ref"] for item in tool_context["disabled_tool_refs"]}
    assert {"tool:apply_patch", "tool:edit_file"} & {
        item["tool_ref"] for item in tool_context["recommended_tool_refs"]
    }
    assert tool_context["model_turn_search"]["usage"] == "debug_plateau_recovery_only"
    assert "parameters" not in json.dumps(tool_context).lower()
    assert "implementation" not in json.dumps(tool_context).lower()


def test_transcript_tool_nav_uses_active_tool_surface_for_recommendations() -> None:
    workframe = _project(
        (
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
        ),
        provider_tool_names=tuple(spec.name for spec in list_v2_tool_specs_for_mode("read_only")),
    )
    tool_context = workframe["tool_context"]
    active_refs = set(tool_context["active_tool_refs"])
    recommended_refs = {item["tool_ref"] for item in tool_context["recommended_tool_refs"]}

    assert "tool:apply_patch" not in active_refs
    assert "tool:edit_file" not in active_refs
    assert "tool:write_file" not in active_refs
    assert not (recommended_refs & {"tool:apply_patch", "tool:edit_file", "tool:write_file"})
    assert "tool:read_file" in recommended_refs


def test_transcript_tool_nav_preserves_missing_obligation_controller_required_next() -> None:
    workframe = _project(
        (
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
    )

    assert workframe["finish_readiness"]["state"] == "blocked"
    assert workframe["required_next"]["kind"] == "run_verifier"
    assert workframe["required_next"]["evidence_refs"] == ["oracle:artifact-fresh"]
    assert workframe["obligations"]["missing_or_stale_refs"] == ["oracle:artifact-fresh"]
