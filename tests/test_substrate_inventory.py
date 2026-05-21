from __future__ import annotations

import json
from pathlib import Path

from mew.implement_lane.substrate_inventory import build_substrate_inventory, render_inventory_markdown


def test_substrate_inventory_lists_current_tools_and_canonical_projection(tmp_path: Path) -> None:
    inventory = build_substrate_inventory(tmp_path)

    tools = inventory["tool_registry"]["tools"]
    projection = inventory["workframe_projection"]

    assert inventory["schema_version"] == 1
    tool_names = {tool["name"] for tool in tools}
    assert tool_names >= {"exec_command", "write_stdin", "apply_patch"}
    assert "finish" not in tool_names
    assert inventory["tool_registry"]["hash"].startswith("sha256:")
    assert projection["kind"] == "canonical_workframe"
    assert projection["selector_live"] is False
    assert projection["hash"].startswith("sha256:")


def test_substrate_inventory_reports_phase0_migration_gap(tmp_path: Path) -> None:
    inventory = build_substrate_inventory(tmp_path)

    missing = inventory["missing_for_offline_diagnosis"]
    assert {item["surface"] for item in missing} >= {
        "tool result index",
        "evidence ref index",
        "model turn index",
        "tool registry artifact",
        "natural transcript log",
    }
    assert inventory["schemas"]["workframe_projection"] == 1
    assert inventory["workframe_projection"]["historical_experiments_namespace"] == "mew.legacy_experiments"
    assert any(field["name"] == "sidecar_events" for field in inventory["workframe_inputs"]["fields"])


def test_substrate_inventory_detects_existing_index_artifacts(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "proof-artifacts" / "terminal-bench" / "sample"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "tool_result_index.json").write_text("{}", encoding="utf-8")

    inventory = build_substrate_inventory(tmp_path)

    coverage = inventory["artifact_coverage"]["index_coverage"]
    assert coverage["tool_result_index.json"]["exists"] is True
    assert coverage["evidence_ref_index.json"]["exists"] is False
    assert "tool result index" not in {item["surface"] for item in inventory["missing_for_offline_diagnosis"]}


def test_substrate_inventory_markdown_is_serializable(tmp_path: Path) -> None:
    inventory = build_substrate_inventory(tmp_path)
    rendered = render_inventory_markdown(inventory)

    assert "# M6.24 Phase 0 Substrate Inventory" in rendered
    assert "## Tool Surface" in rendered
    assert "canonical_workframe" in rendered
    assert "status | current source" in rendered
    json.dumps(inventory, sort_keys=True)
