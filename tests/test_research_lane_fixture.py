import ast
import json
import os
from pathlib import Path
import subprocess
import sys

from mew.lane_substrate import LaneRuntimeSpec
from mew.research_lane import (
    build_research_fixture_spec,
    run_research_fixture,
    validate_research_fixture_artifacts,
)


BLOCKED_RESEARCH_IMPORT_MODULES = (
    "mew.implement_lane.native_tool_harness",
    "mew.implement_lane.v2_runtime",
    "mew.implement_lane.workframe_variants",
    "mew.implement_lane.workframe_variant_transition_contract",
    "mew.implement_lane.workframe_variant_transcript_first",
    "mew.implement_lane.workframe_variant_transcript_tool_nav",
    "mew.implement_lane.native_finish_gate",
    "mew.implement_lane.native_finish_closeout_policy",
    "mew.implement_lane.finish_acceptance_helpers",
)


def test_research_lane_fixture_runs_substrate_artifact_proof(tmp_path: Path) -> None:
    result = run_research_fixture(tmp_path, task="summarize substrate notes")
    validation = validate_research_fixture_artifacts(tmp_path)

    assert result.lane_id == "research_fixture"
    assert result.runtime_id == "research_fixture_native_substrate"
    assert result.status == "completed"
    assert result.proof_manifest_ref is not None
    assert result.metadata["pairing_valid"] is True
    assert validation.ok is True
    assert validation.checks["pairing_valid"] is True
    assert (tmp_path / "response_transcript.json").exists()
    assert (tmp_path / "provider_requests.jsonl").exists()
    assert (tmp_path / "tool_results.jsonl").exists()
    assert (tmp_path / "tool_routes.jsonl").exists()
    assert (tmp_path / "proof-manifest.json").exists()

    manifest = json.loads((tmp_path / "proof-manifest.json").read_text(encoding="utf-8"))
    assert manifest["lane_id"] == "research_fixture"
    assert manifest["runtime_id"] == "research_fixture_native_substrate"
    assert manifest["pairing_valid"] is True
    transcript = json.loads((tmp_path / "response_transcript.json").read_text(encoding="utf-8"))
    assert [item["kind"] for item in transcript["items"]] == ["message", "tool_call", "tool_output"]


def test_research_lane_fixture_uses_lane_substrate_spec_with_research_owned_components() -> None:
    spec = build_research_fixture_spec()

    assert isinstance(spec, LaneRuntimeSpec)
    assert spec.lane_id == "research_fixture"
    assert spec.replay_validator is not None
    component_modules = {
        spec.provider_adapter.__class__.__module__,
        spec.tool_surface_resolver.__class__.__module__,
        spec.tool_dispatcher.__class__.__module__,
        spec.transcript_store.__class__.__module__,
        spec.artifact_writer.__class__.__module__,
        spec.completion_policy.__class__.__module__,
        spec.observability_policy.__class__.__module__,
        spec.tool_result_renderer.__class__.__module__ if spec.tool_result_renderer is not None else "",
        spec.replay_validator.__class__.__module__,
    }
    assert component_modules == {"mew.research_lane.fixture"}


def test_research_lane_fixture_source_has_no_implement_lane_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    package_root = root / "src" / "mew" / "research_lane"
    forbidden_tokens = (
        "mew.implement_lane",
        "implement_lane.native_tool_harness",
        "implement_lane.v2_runtime",
        "workframe_variants",
        "workframe_variant_",
        "native_finish_gate",
        "native_finish_closeout",
        "finish_acceptance_helpers",
    )

    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert not any(name.startswith("mew.implement_lane") for name in imported)


def test_research_lane_fixture_import_does_not_load_implement_runtime_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src_path
    blocked_literal = ", ".join(repr(name) for name in BLOCKED_RESEARCH_IMPORT_MODULES)
    code = f"""
import sys
import mew.research_lane
spec = mew.research_lane.build_research_fixture_spec()
assert spec.lane_id == "research_fixture"
blocked = [{blocked_literal}]
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
