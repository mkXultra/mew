import ast
import os
from pathlib import Path
import subprocess
import sys

from mew.lane_substrate import (
    ArtifactRef,
    LaneInput,
    LaneRuntimeSpec,
    TranscriptState,
)


class _ProviderAdapter:
    pass


class _ToolSurfaceResolver:
    pass


class _ToolDispatcher:
    pass


class _TranscriptStore:
    pass


class _ArtifactWriter:
    pass


class _CompletionPolicy:
    pass


class _ObservabilityPolicy:
    pass


def test_lane_substrate_runtime_spec_is_interface_level() -> None:
    spec = LaneRuntimeSpec(
        lane_id="research_fixture",
        runtime_id="research_native_fixture",
        provider_adapter=_ProviderAdapter(),
        tool_surface_resolver=_ToolSurfaceResolver(),
        tool_dispatcher=_ToolDispatcher(),
        transcript_store=_TranscriptStore(),
        artifact_writer=_ArtifactWriter(),
        completion_policy=_CompletionPolicy(),
        observability_policy=_ObservabilityPolicy(),
        metadata={"fixture": True},
    )
    lane_input = LaneInput(
        work_session_id="ws-research",
        task_id="task-research",
        workspace="/tmp/research",
        lane_config={"tool_profile": "research_fixture"},
    )
    state = TranscriptState(
        lane_attempt_id="attempt-research",
        sidecar_refs=(ArtifactRef(kind="digest", path="compact-sidecar.json", digest="abc123"),),
    )

    assert spec.lane_id == "research_fixture"
    assert spec.runtime_id == "research_native_fixture"
    assert lane_input.lane_config["tool_profile"] == "research_fixture"
    assert state.sidecar_refs[0].kind == "digest"


def test_lane_substrate_source_has_no_implement_lane_imports() -> None:
    root = Path(__file__).resolve().parents[1]
    package_root = root / "src" / "mew" / "lane_substrate"
    for path in package_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "mew.implement_lane" not in text
        assert "implement_lane" not in text
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                imported = [node.module or ""]
            else:
                continue
            assert not any(name.startswith("mew.implement_lane") for name in imported)


def test_lane_substrate_import_does_not_load_implement_native_runtime_modules() -> None:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    src_path = str(root / "src")
    env["PYTHONPATH"] = src_path + os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else src_path
    code = """
import sys
import mew.lane_substrate
blocked = [
    "mew.implement_lane.native_tool_harness",
    "mew.implement_lane.v2_runtime",
    "mew.implement_lane.workframe_variants",
    "mew.implement_lane.native_finish_gate",
    "mew.implement_lane.completion_resolver",
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
