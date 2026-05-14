from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_tool_surface_ab_diagnostic_dry_run_builds_paired_profile_commands(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_tool_surface_ab_diagnostic.py",
            "prove-plus-comm",
            "--output-root",
            str(tmp_path / "ab"),
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    baseline = payload["commands"]["baseline"]
    candidate = payload["commands"]["candidate"]
    assert payload["status"] == "dry_run"
    assert payload["workspace_snapshot_id"] == ""
    assert payload["task_contract_hash"] == ""
    assert "--tool-surface-profile-id" in baseline
    assert baseline[baseline.index("--tool-surface-profile-id") + 1] == "mew_legacy"
    assert candidate[candidate.index("--tool-surface-profile-id") + 1] == "codex_hot_path"
    assert baseline[baseline.index("--command-cwd") + 1] == "/workspace"
    assert candidate[candidate.index("--command-cwd") + 1] == "/workspace"
    assert str(tmp_path / "ab" / "baseline-mew-legacy") in baseline
    assert str(tmp_path / "ab" / "candidate-codex-hot-path") in candidate


def test_tool_surface_ab_diagnostic_rejects_multi_trial_modes(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_tool_surface_ab_diagnostic.py",
            "prove-plus-comm",
            "--mode",
            "proof-5",
            "--output-root",
            str(tmp_path / "ab"),
            "--dry-run",
            "--json",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    payload = json.loads(completed.stdout)
    assert payload == {
        "reason": "proof-5 multi-trial A/B is not supported by this one-pair wrapper",
        "status": "unsupported",
    }


def test_tool_surface_ab_diagnostic_blocks_gate_on_child_failures() -> None:
    module = _load_ab_diagnostic_module()
    gate = {
        "status": "ready",
        "can_switch_default": True,
        "reasons": [],
    }

    blocked = module._block_gate_for_child_failures(
        gate,
        baseline={"returncode": 0, "summary": {"external_reward": 1.0}},
        candidate={"returncode": 0, "summary": {"external_reward": 0.0}},
    )

    assert blocked["status"] == "blocked"
    assert blocked["can_switch_default"] is False
    assert "candidate_external_reward_not_one" in blocked["reasons"]


def test_tool_surface_ab_diagnostic_blocks_gate_on_missing_reward() -> None:
    module = _load_ab_diagnostic_module()
    gate = {
        "status": "ready",
        "can_switch_default": True,
        "reasons": [],
    }

    blocked = module._block_gate_for_child_failures(
        gate,
        baseline={"returncode": 1, "summary": {"external_reward": 1.0}},
        candidate={"returncode": 0, "summary": {}},
    )

    assert blocked["status"] == "blocked"
    assert "baseline_diagnostic_failed" in blocked["reasons"]
    assert "candidate_external_reward_missing" in blocked["reasons"]


def _load_ab_diagnostic_module():
    path = ROOT / "scripts" / "run_tool_surface_ab_diagnostic.py"
    spec = importlib.util.spec_from_file_location("run_tool_surface_ab_diagnostic", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
