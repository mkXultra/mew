import json

from mew.implement_lane.native_fake_provider import NativeFakeProvider, fake_finish
from mew.implement_lane.native_tool_harness import run_native_implement_v2
from mew.implement_lane.native_validation import validate_native_loop_gate
from mew.implement_lane.types import ImplementLaneInput


def _lane_input(tmp_path):
    return ImplementLaneInput(
        work_session_id="ws-native-gate",
        task_id="task-native-gate",
        workspace=str(tmp_path),
        lane="implement_v2",
        model_backend="fake-native",
        model="fake-native-model",
        lane_config={
            "allowed_read_roots": [str(tmp_path)],
            "allowed_write_roots": [str(tmp_path)],
            "auto_approve_writes": True,
        },
    )


def test_native_loop_gate_passes_static_route_and_fixture() -> None:
    result = validate_native_loop_gate()

    assert result.ok is True
    assert result.checks["registry_native_runtime_id"] is True
    assert result.checks["registry_provider_native_loop"] is True
    assert result.checks["command_route_no_live_json_call"] is True
    assert result.checks["package_surface_exists"] is True
    assert result.checks["native_production_paths_exist"] is True
    assert result.checks["native_production_paths_no_legacy_symbols"] is True
    assert result.checks["package_surface_no_run_live_json_implement_v2"] is True
    assert result.checks["package_surface_no_run_fake_exec_implement_v2"] is True
    assert result.checks["package_surface_no_run_fake_read_only_implement_v2"] is True
    assert result.checks["package_surface_no_run_fake_write_implement_v2"] is True
    assert result.checks["package_surface_no_run_unavailable_implement_v2"] is True
    assert result.checks["package_surface_no_JsonModelProviderAdapter"] is True
    assert result.checks["package_surface_no_FakeProviderAdapter"] is True
    assert result.checks["package_surface_no_FakeProviderToolCall"] is True
    assert result.checks["package_surface_no_LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID"] is True
    assert result.checks["fixture_pairing_valid"] is True


def test_native_loop_gate_accepts_native_artifact(tmp_path) -> None:
    provider = NativeFakeProvider.from_item_batches([[fake_finish("finish-1")]])
    run_native_implement_v2(_lane_input(tmp_path), provider=provider, artifact_root=tmp_path / "artifact")

    result = validate_native_loop_gate(artifact=tmp_path / "artifact")

    assert result.ok is True
    assert result.checks["artifact_native_runtime_id"] is True
    assert result.checks["artifact_native_transport"] is True
    assert result.checks["artifact_pairing_valid"] is True
    assert result.checks["artifact_authoritative_transcript_present"] is True
    assert result.checks["artifact_authoritative_pairing_valid"] is True
    assert result.checks["artifact_transcript_hash_matches"] is True
    assert result.checks["artifact_manifest_recomputes"] is True
    assert result.checks["artifact_model_json_main_path_not_detected"] is True


def test_native_loop_gate_rejects_native_looking_manifest_without_authoritative_transcript(tmp_path) -> None:
    path = tmp_path / "implement_v2" / "proof-manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "transcript_hash": "fake",
                "pairing": {"valid": True},
                "metrics": {
                    "provider_native_tool_loop": True,
                    "model_json_main_path_detected": False,
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_native_loop_gate(artifact=tmp_path)

    assert result.ok is False
    assert result.checks["artifact_authoritative_transcript_present"] is False
    assert result.checks["artifact_authoritative_pairing_valid"] is False
    assert result.checks["artifact_manifest_recomputes"] is False


def test_native_loop_gate_rejects_legacy_model_json_artifact(tmp_path) -> None:
    manifest = {
        "runtime_id": "implement_v2_model_json_tool_loop",
        "transport_kind": "model_json",
        "pairing": {"valid": True},
        "metrics": {
            "provider_native_tool_loop": False,
            "model_json_main_path_detected": True,
        },
    }
    path = tmp_path / "implement_v2" / "proof-manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_native_loop_gate(artifact=tmp_path)

    assert result.ok is False
    assert result.checks["artifact_native_runtime_id"] is False
    assert result.checks["artifact_native_transport"] is False
    assert result.checks["artifact_model_json_main_path_not_detected"] is False


def test_native_loop_gate_requires_positive_native_command_route(tmp_path) -> None:
    commands_path = tmp_path / "src" / "mew" / "commands.py"
    commands_path.parent.mkdir(parents=True)
    commands_path.write_text(
        "def selected_v2_route():\n    return 'no old json literal, but also no native runner'\n",
        encoding="utf-8",
    )

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["command_route_no_live_json_call"] is True
    assert result.checks["command_route_has_native_runner"] is False


def test_native_loop_gate_rejects_legacy_symbols_in_native_production_paths(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_unavailable_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID\n",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/native_provider_adapter.py": "call_codex_json()\n",
        "src/mew/implement_lane/native_tool_harness.py": "",
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["native_production_paths_exist"] is True
    assert result.checks["native_production_paths_no_legacy_symbols"] is False
    production_paths = result.details["native_production_paths"]
    provider_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/native_provider_adapter.py"
    )
    assert provider_scan["legacy_hits"] == {"call_codex_json": 1}
