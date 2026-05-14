from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import threading

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
    assert str(payload["workspace_snapshot_id"]).startswith("git:")
    assert str(payload["task_contract_hash"]).startswith("sha256:")
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


def test_tool_surface_ab_diagnostic_runs_profile_children_in_parallel(monkeypatch) -> None:
    module = _load_ab_diagnostic_module()
    barrier = threading.Barrier(2)
    seen: list[str] = []

    def fake_run(command):
        seen.append(command[0])
        barrier.wait(timeout=1)
        return {
            "artifact_root": f"/tmp/{command[0]}",
            "returncode": 0,
            "summary": {"external_reward": 1.0},
        }

    monkeypatch.setattr(module, "_run_diagnostic", fake_run)

    baseline, candidate = module._run_profile_diagnostics(
        {
            "baseline": ["baseline"],
            "candidate": ["candidate"],
        }
    )

    assert baseline["artifact_root"] == "/tmp/baseline"
    assert candidate["artifact_root"] == "/tmp/candidate"
    assert sorted(seen) == ["baseline", "candidate"]


def test_tool_surface_ab_diagnostic_profile_commands_use_isolated_auth_paths(tmp_path: Path) -> None:
    module = _load_ab_diagnostic_module()
    args = module.build_parser().parse_args(
        [
            "prove-plus-comm",
            "--output-root",
            str(tmp_path / "ab"),
        ]
    )
    auth_paths = {
        "baseline": tmp_path / "baseline.auth.json",
        "candidate": tmp_path / "candidate.auth.json",
    }

    commands = module._profile_commands(args, root=tmp_path / "ab", auth_json_paths=auth_paths)

    baseline = commands["baseline"]
    candidate = commands["candidate"]
    assert baseline[baseline.index("--codex-auth-json") + 1] == str(auth_paths["baseline"])
    assert candidate[candidate.index("--codex-auth-json") + 1] == str(auth_paths["candidate"])
    assert auth_paths["baseline"] != auth_paths["candidate"]


def test_tool_surface_ab_diagnostic_copies_parallel_auth_files_without_refresh(tmp_path: Path, monkeypatch) -> None:
    module = _load_ab_diagnostic_module()
    source = tmp_path / "auth.json"
    source.write_text('{"tokens":{"access_token":"a","refresh_token":"r"}}\n', encoding="utf-8")

    def fail_refresh(*_args, **_kwargs):
        raise AssertionError("auth refresh should not be called by the A/B wrapper")

    monkeypatch.setattr(module, "refresh_codex_oauth", fail_refresh, raising=False)

    paths = module._copy_parallel_auth_files(tmp_path / "tmp-auth", source)

    assert set(paths) == {"baseline", "candidate"}
    assert paths["baseline"] != paths["candidate"]
    assert paths["baseline"].read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    assert paths["candidate"].read_text(encoding="utf-8") == source.read_text(encoding="utf-8")


def test_tool_surface_ab_diagnostic_child_exception_becomes_failure_payload(monkeypatch) -> None:
    module = _load_ab_diagnostic_module()

    def fake_run(command):
        if command[0] == "candidate":
            raise RuntimeError("boom")
        return {
            "artifact_root": "/tmp/baseline",
            "returncode": 0,
            "summary": {"external_reward": 1.0},
        }

    monkeypatch.setattr(module, "_run_diagnostic", fake_run)

    baseline, candidate = module._run_profile_diagnostics(
        {
            "baseline": ["baseline", "--codex-auth-json", "/secret/auth.json"],
            "candidate": ["candidate", "--codex-auth-json", "/secret/auth.json"],
        }
    )

    assert baseline["artifact_root"] == "/tmp/baseline"
    assert candidate["returncode"] == 1
    assert candidate["artifact_root"] == ""
    assert candidate["error"]["type"] == "RuntimeError"
    assert candidate["error"]["command"] == ["candidate", "--codex-auth-json", "<isolated-auth-json>"]


def _load_ab_diagnostic_module():
    path = ROOT / "scripts" / "run_tool_surface_ab_diagnostic.py"
    spec = importlib.util.spec_from_file_location("run_tool_surface_ab_diagnostic", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
