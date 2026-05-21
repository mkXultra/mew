import ast
import json
import os
from pathlib import Path
import subprocess
import sys

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
    assert result.checks["default_tool_surface_profile_codex_hot_path"] is True
    assert result.checks["default_tool_surface_profile_default"] is True
    assert result.checks["planner_policy_default_enabled"] is True
    assert result.checks["legacy_tool_surface_explicit_opt_out"] is True
    assert result.checks["command_route_no_live_json_call"] is True
    assert result.checks["package_surface_exists"] is True
    assert result.checks["native_production_paths_exist"] is True
    assert result.checks["native_production_static_allowlist_explicit"] is True
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
    assert result.checks["package_surface_no_list_v2_base_tool_specs"] is True
    assert result.checks["package_surface_no_list_v2_tool_specs_for_mode"] is True
    assert result.checks["package_surface_no_list_v2_tool_specs_for_task"] is True
    assert result.checks["native_production_paths_no_direct_planner_config_reads"] is True
    assert result.checks["research_lane_no_implement_runtime_imports"] is True
    assert result.checks["fixture_pairing_valid"] is True
    scanned_paths = {item["path"] for item in result.details["native_production_paths"]}
    assert "src/mew/implement_lane/prompt.py" in scanned_paths
    assert "src/mew/lane_substrate/runtime.py" in scanned_paths
    assert "src/mew/research_lane/fixture.py" in scanned_paths
    research_boundary = result.details["research_lane_import_boundary"]
    assert any(item["path"] == "src/mew/research_lane/fixture.py" for item in research_boundary)
    assert not any(item["forbidden_import_hits"] for item in research_boundary)
    assert result.details["native_production_static_allowlist"]
    assert "src/mew/implement_lane/v2_runtime.py" not in scanned_paths


def test_commands_import_does_not_load_quarantined_legacy_model_json_runtime() -> None:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src_path
    code = """
import sys
import mew.commands
blocked = [
    "mew.legacy_experiments.model_json_runtime",
    "mew.legacy_experiments.model_json_provider",
]
loaded = [name for name in blocked if name in sys.modules]
print("\\n".join(loaded))
raise SystemExit(1 if loaded else 0)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


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


def test_native_loop_gate_allows_internal_helper_model_call_in_native_harness(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/provider.py": "",
        "src/mew/implement_lane/native_provider_adapter.py": "",
        "src/mew/implement_lane/native_tool_harness.py": "call_codex_json()\n",
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is True
    assert result.checks["native_production_paths_no_legacy_symbols"] is True
    production_paths = result.details["native_production_paths"]
    harness_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/native_tool_harness.py"
    )
    assert harness_scan["legacy_hits"] == {}


def test_native_loop_gate_rejects_legacy_symbols_in_native_production_paths(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_unavailable_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "LEGACY_IMPLEMENT_V2_MODEL_JSON_RUNTIME_ID\n",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/provider.py": "provider = \"model_json\"\n",
        "src/mew/implement_lane/native_provider_adapter.py": "run_live_json_implement_v2()\n",
        "src/mew/implement_lane/native_tool_harness.py": "from .v2_runtime import _finish_acceptance_action\n",
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
    assert provider_scan["legacy_hits"] == {"run_live_json_implement_v2": 1}
    harness_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/native_tool_harness.py"
    )
    assert harness_scan["legacy_hits"] == {
        "from .v2_runtime import": 1,
        "_finish_acceptance_action": 1,
    }


def test_native_loop_gate_scans_all_implement_lane_files_for_unallowlisted_symbols(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/diagnostic_but_not_allowed.py": "workframe_variants\n",
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["native_production_paths_no_legacy_symbols"] is False
    production_paths = result.details["native_production_paths"]
    diagnostic_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/diagnostic_but_not_allowed.py"
    )
    assert diagnostic_scan["legacy_hits"] == {"workframe_variants": 1}


def test_native_loop_gate_scans_research_lane_and_rejects_implement_runtime_imports(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/research_lane/__init__.py": "",
        "src/mew/research_lane/fixture.py": (
            "from mew.implement_lane.native_tool_harness import run_native_implement_v2\n"
        ),
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["research_lane_no_implement_runtime_imports"] is False
    scanned_paths = {item["path"] for item in result.details["native_production_paths"]}
    assert "src/mew/research_lane/fixture.py" in scanned_paths
    research_boundary = result.details["research_lane_import_boundary"]
    fixture_scan = next(
        item for item in research_boundary if item["path"] == "src/mew/research_lane/fixture.py"
    )
    assert fixture_scan["forbidden_import_hits"] == {"mew.implement_lane": 1}


def test_native_loop_gate_rejects_unallowlisted_legacy_projection_fields(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/new_projection.py": (
            "prompt = 'history_json:\\n{}'\n"
            "payload = {'frontier_state_update': {}}\n"
        ),
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["native_production_paths_no_legacy_symbols"] is False
    projection_scan = next(
        item for item in result.details["native_production_paths"] if item["path"] == "src/mew/implement_lane/new_projection.py"
    )
    assert projection_scan["legacy_hits"] == {
        "history_json:": 1,
        "frontier_state_update": 1,
    }


def test_native_loop_gate_rejects_retired_task_contract_and_acceptance_symbols(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/task_contract_leak.py": "compiled_task_contract = {}\n",
        "src/mew/implement_lane/acceptance_bridge_leak.py": (
            "finish_acceptance_gate_decision()\n"
            "_acceptance_session_from_tool_results()\n"
        ),
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["native_production_paths_no_legacy_symbols"] is False
    production_paths = result.details["native_production_paths"]
    task_contract_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/task_contract_leak.py"
    )
    acceptance_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/acceptance_bridge_leak.py"
    )
    assert task_contract_scan["legacy_hits"] == {"compiled_task_contract": 1}
    assert acceptance_scan["legacy_hits"] == {
        "finish_acceptance_gate_decision": 1,
        "_acceptance_session_from_tool_results": 1,
    }


def test_native_loop_gate_rejects_legacy_model_json_files_in_production_scan(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/legacy_model_json_runtime.py": "run_live_json_implement_v2()\n",
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    production_paths = result.details["native_production_paths"]
    legacy_scan = next(
        item for item in production_paths if item["path"] == "src/mew/implement_lane/legacy_model_json_runtime.py"
    )
    assert legacy_scan["legacy_hits"] == {"run_live_json_implement_v2": 1}
    assert legacy_scan["allowed_legacy_hits"] == {}


def test_native_loop_gate_rejects_direct_planner_config_reads_in_native_runtime(tmp_path) -> None:
    files = {
        "src/mew/commands.py": "run_live_native_implement_v2()\n",
        "src/mew/implement_lane/__init__.py": "",
        "src/mew/implement_lane/registry.py": "",
        "src/mew/implement_lane/provider.py": "",
        "src/mew/implement_lane/native_provider_adapter.py": "",
        "src/mew/implement_lane/native_tool_harness.py": (
            "def can_run(lane_config):\n"
            "    return lane_config.get(\"finish_verifier_planner_enabled\")\n"
        ),
    }
    for relative_path, text in files.items():
        path = tmp_path / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    result = validate_native_loop_gate(source_root=tmp_path)

    assert result.ok is False
    assert result.checks["native_production_paths_no_direct_planner_config_reads"] is False
    planner_scans = result.details["planner_policy_boundary_paths"]
    harness_scan = next(
        item for item in planner_scans if item["path"] == "src/mew/implement_lane/native_tool_harness.py"
    )
    assert harness_scan["planner_config_hits"] == {
        'lane_config.get("finish_verifier_planner_enabled")': 1
    }


def test_legacy_experiment_modules_are_labeled_as_diagnostic_legacy() -> None:
    root = Path(__file__).resolve().parents[1]
    package_root = root / "src" / "mew" / "legacy_experiments"
    module_paths = sorted(package_root.glob("*.py"))

    assert module_paths
    for path in module_paths:
        module = ast.parse(path.read_text(encoding="utf-8"))
        docstring = (ast.get_docstring(module) or "").lower()
        assert any(label in docstring for label in ("legacy", "diagnostic", "quarantined")), path
