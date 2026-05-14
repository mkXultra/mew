import json
from pathlib import Path
import sys

from mew.implement_lane.native_fake_provider import NativeFakeProvider, fake_call, fake_finish
from mew.implement_lane.native_tool_harness import run_native_implement_v2
from mew.implement_lane.tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID
from mew.implement_lane.tool_result_renderer import (
    CODEX_APPLY_PATCH_RENDERER_ID,
    CODEX_FINISH_RENDERER_ID,
    CODEX_TERMINAL_RENDERER_ID,
)
from mew.implement_lane.tool_surface_ab_report import (
    build_tool_surface_ab_report,
    write_tool_surface_ab_report,
)
from mew.implement_lane.types import ImplementLaneInput


def _lane_input(
    workspace: Path,
    *,
    artifact_root: Path,
    profile_id: str,
) -> ImplementLaneInput:
    return ImplementLaneInput(
        work_session_id="ws-ab",
        task_id="task-ab",
        workspace=str(workspace),
        lane="implement_v2",
        model_backend="fake-native",
        model="fake-native-model",
        effort="high",
        task_contract={"goal": "change sample.txt and verify it"},
        lane_config={
            "allowed_read_roots": [str(workspace)],
            "allowed_write_roots": [str(workspace)],
            "allow_shell": True,
            "allow_verify": True,
            "auto_approve_writes": True,
            "artifact_dir": str(artifact_root),
            "tool_surface_profile_id": profile_id,
        },
    )


def _patch_text() -> str:
    return "\n".join(
        [
            "*** Begin Patch",
            "*** Update File: sample.txt",
            "@@",
            "-before",
            "+after",
            "*** End Patch",
        ]
    )


def _verify_command() -> str:
    return (
        f"{sys.executable} -c "
        "\"from pathlib import Path; assert Path('sample.txt').read_text().strip() == 'after'; print('ok')\""
    )


def _run_mew_legacy_artifact(workspace: Path, artifact_root: Path) -> None:
    workspace.mkdir()
    (workspace / "sample.txt").write_text("before\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call("read-1", "read_file", {"path": "sample.txt"}, output_index=0),
                fake_call("patch-1", "apply_patch", {"patch": _patch_text(), "apply": True}, output_index=1),
                fake_call(
                    "verify-1",
                    "run_command",
                    {"command": _verify_command(), "command_intent": "verify", "cwd": "."},
                    output_index=2,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=3),
            ]
        ]
    )
    result = run_native_implement_v2(
        _lane_input(workspace, artifact_root=artifact_root, profile_id=MEW_LEGACY_PROFILE_ID),
        provider=provider,
        artifact_root=artifact_root,
        max_turns=1,
    )
    assert result.status == "completed"


def _run_codex_hot_path_artifact(workspace: Path, artifact_root: Path) -> None:
    workspace.mkdir()
    (workspace / "sample.txt").write_text("before\n", encoding="utf-8")
    provider = NativeFakeProvider.from_item_batches(
        [
            [
                fake_call(
                    "probe-1",
                    "exec_command",
                    {"cmd": f"{sys.executable} -c \"print(open('sample.txt').read().strip())\""},
                    output_index=0,
                ),
                fake_call("patch-1", "apply_patch", {"patch": _patch_text(), "apply": True}, output_index=1),
                fake_call(
                    "verify-1",
                    "exec_command",
                    {"cmd": _verify_command(), "command_intent": "verify"},
                    output_index=2,
                ),
                fake_finish("finish-1", {"outcome": "completed", "summary": "done"}, output_index=3),
            ]
        ]
    )
    result = run_native_implement_v2(
        _lane_input(workspace, artifact_root=artifact_root, profile_id=CODEX_HOT_PATH_PROFILE_ID),
        provider=provider,
        artifact_root=artifact_root,
        max_turns=1,
    )
    assert result.status == "completed"


def _paired_artifacts(tmp_path: Path) -> tuple[Path, Path]:
    baseline_root = tmp_path / "baseline-artifacts"
    candidate_root = tmp_path / "candidate-artifacts"
    _run_mew_legacy_artifact(tmp_path / "baseline-workspace", baseline_root)
    _run_codex_hot_path_artifact(tmp_path / "candidate-workspace", candidate_root)
    return baseline_root, candidate_root


def test_tool_surface_ab_report_compares_profiles_on_same_snapshot(tmp_path: Path) -> None:
    baseline_root, candidate_root = _paired_artifacts(tmp_path)

    report = build_tool_surface_ab_report(
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id="ab-unit-1",
        workspace_snapshot_id="sha256:workspace",
        task_contract_hash="sha256:task",
        model="fake-native-model",
        effort="high",
        budget_profile="unit",
    )

    assert report["ab_comparable"] is True
    assert report["default_switch_evidence_included"] is True
    by_profile = {row["profile_id"]: row for row in report["rows"]}
    baseline = by_profile[MEW_LEGACY_PROFILE_ID]
    candidate = by_profile[CODEX_HOT_PATH_PROFILE_ID]
    assert baseline["ab_role"] == "baseline"
    assert candidate["ab_role"] == "candidate"
    assert candidate["provider_tool_names"] == ["apply_patch", "exec_command", "write_stdin", "finish"]
    assert set(candidate["renderer_ids"]) == {
        CODEX_APPLY_PATCH_RENDERER_ID,
        CODEX_FINISH_RENDERER_ID,
        CODEX_TERMINAL_RENDERER_ID,
    }
    assert candidate["every_call_has_exactly_one_output"] is True
    assert candidate["provider_visible_forbidden_scan_ok"] is True
    assert candidate["hidden_steering_markers"] == []
    assert candidate["sidecar_artifacts_present"] is True
    assert candidate["proof_replay_status"]["transcript_hash_matches_manifest"] is True
    assert candidate["probe_count_before_first_write"] == 1
    assert candidate["command_count_before_first_write"] == 1
    assert candidate["mutation_count"] == 1
    assert candidate["first_verifier_turn"] == 1
    assert report["comparison"]["candidate_render_leak_ok"] is True


def test_tool_surface_ab_report_excludes_mismatched_workspace_snapshot(tmp_path: Path) -> None:
    baseline_root, candidate_root = _paired_artifacts(tmp_path)

    report = build_tool_surface_ab_report(
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id="ab-unit-2",
        workspace_snapshot_id="sha256:workspace-a",
        task_contract_hash="sha256:task",
        candidate_tags={"workspace_snapshot_id": "sha256:workspace-b"},
    )

    assert report["ab_comparable"] is False
    assert report["default_switch_evidence_included"] is False
    assert "workspace_snapshot_mismatch" in report["exclusion_reasons"]


def test_tool_surface_ab_report_requires_identity_tags(tmp_path: Path) -> None:
    baseline_root, candidate_root = _paired_artifacts(tmp_path)

    report = build_tool_surface_ab_report(
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id="ab-unit-missing-tags",
    )

    assert report["ab_comparable"] is False
    assert "missing_workspace_snapshot_id" in report["exclusion_reasons"]
    assert "missing_task_contract_hash" in report["exclusion_reasons"]


def test_tool_surface_ab_report_rejects_missing_forbidden_field_report(tmp_path: Path) -> None:
    baseline_root, candidate_root = _paired_artifacts(tmp_path)
    inventory_path = candidate_root / "provider-request-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    for record in inventory["provider_request_inventory"]:
        record.pop("provider_visible_forbidden_fields", None)
    inventory_path.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = build_tool_surface_ab_report(
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id="ab-unit-missing-forbidden-report",
        workspace_snapshot_id="sha256:workspace",
        task_contract_hash="sha256:task",
    )

    candidate = {row["profile_id"]: row for row in report["rows"]}[CODEX_HOT_PATH_PROFILE_ID]
    assert report["ab_comparable"] is False
    assert "row_gate_failed" in report["exclusion_reasons"]
    assert candidate["provider_inventory_forbidden_ok"] is False


def test_write_tool_surface_ab_report_writes_report_artifact(tmp_path: Path) -> None:
    baseline_root, candidate_root = _paired_artifacts(tmp_path)
    output = tmp_path / "tool_surface_ab_report.json"

    report = write_tool_surface_ab_report(
        output,
        baseline_artifact_root=baseline_root,
        candidate_artifact_root=candidate_root,
        ab_pair_id="ab-unit-3",
        workspace_snapshot_id="sha256:workspace",
        task_contract_hash="sha256:task",
    )

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload == report
    assert payload["ab_comparable"] is True
