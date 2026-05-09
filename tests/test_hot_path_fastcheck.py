import json
from pathlib import Path

import pytest

from mew.implement_lane.hot_path_fastcheck import run_hot_path_fastcheck


def _write_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    implement_v2 = artifact / "implement_v2"
    implement_v2.mkdir(parents=True)
    manifest = {
        "lane": "implement_v2",
        "metrics": {
            "hot_path_projection": {
                "phase": "m6_24_hot_path_collapse_phase_0",
                "normal_full_prompt_bytes": 1024,
                "normal_full_prompt_bytes_total": 2048,
                "provider_visible_tool_result_bytes": 128,
                "normal_section_inventory": [
                    {
                        "id": "implement_v2_active_work_todo",
                        "visibility": "ordinary",
                        "bytes": 256,
                    }
                ],
            },
            "resident_sidecar_state": {
                "surface": "resident_sidecar_state",
                "total_bytes": 4096,
                "per_turn_growth_bytes": 256,
                "families": {"tool_results": 1},
            },
        },
    }
    history = [
        {
            "turn": 1,
            "summary": "Probe source and prepare first patch.",
            "tool_calls": [],
            "tool_results": [],
        }
    ]
    (implement_v2 / "proof-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (implement_v2 / "history.json").write_text(json.dumps(history), encoding="utf-8")
    return artifact


def test_hot_path_fastcheck_refreshes_and_reuses_micro_fixture(tmp_path):
    artifact = _write_artifact(tmp_path)
    fixture_path = tmp_path / "micro.json"
    calls = []

    def fake_model(prompt):
        calls.append(prompt)
        return {
            "category": "patch/edit",
            "reason": "history has enough source evidence for first write",
        }

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=fake_model,
    )

    assert result["status"] == "pass"
    assert result["micro_next_action_refresh"]["mode"] == "refreshed"
    assert fixture_path.is_file()
    assert len(calls) == 1

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    reused = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=fail_if_called,
    )

    assert reused["status"] == "pass"
    assert reused["micro_next_action_refresh"]["mode"] == "reused"


def test_hot_path_fastcheck_rejects_wrong_micro_category(tmp_path):
    artifact = _write_artifact(tmp_path)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "cheap_probe", "reason": "more reading"},
    )

    assert result["status"] == "fail"
    micro = [check for check in result["checks"] if check["name"] == "micro_next_action"][0]
    assert micro["status"] == "fail"


def test_hot_path_fastcheck_rejects_model_supplied_unknown_category(tmp_path):
    artifact = _write_artifact(tmp_path)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {
            "category": "invented_category",
            "expected_categories": ["invented_category"],
        },
    )

    assert result["status"] == "fail"
    assert result["metrics"]["micro_next_action"]["category"] == "invalid"


def test_hot_path_fastcheck_rejects_generic_runtime_exit_code_projection(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier failed",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime",
                                "output_ref": "out-runtime",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "exit code 1",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
    )

    assert result["status"] == "fail"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["details"]["generic_runtime_failures"][0]["summary"] == "exit code 1"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_rejects_generic_runtime_killed_projection(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier killed",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-killed",
                    "tool_name": "run_tests",
                    "status": "interrupted",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime",
                                "output_ref": "out-runtime",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "killed",
                                    "class": "runtime_failure",
                                    "summary": "tool run tool-run-record:call-runtime:2:interrupted ended with killed",
                                },
                            }
                        ]
                    },
                }
            ],
        }
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
    )

    assert result["status"] == "fail"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["details"]["generic_runtime_failures"][0]["summary"].endswith("ended with killed")
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_skips_live_micro_when_static_checks_fail(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 999999
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def fail_if_called(prompt):
        raise AssertionError(f"unexpected live call: {prompt[:80]}")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=fail_if_called,
        max_sidecar_total_bytes=1024,
    )

    assert result["status"] == "fail"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_uses_phase0_baseline_for_sidecar_caps(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 900000
    manifest["metrics"]["resident_sidecar_state"]["per_turn_growth_bytes"] = 50000
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "resident_sidecar_state": {
                        "total_bytes": 800000,
                        "per_turn_growth_bytes": 40000,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(
        artifact,
        baseline=baseline_path,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "ready"},
    )

    assert result["status"] == "pass"
    sidecar = [check for check in result["checks"] if check["name"] == "resident_sidecar_metrics"][0]
    assert sidecar["details"]["cap_source"] == "phase0_baseline"
    assert sidecar["details"]["total_band"] == "yellow"


def test_hot_path_fastcheck_rejects_artifact_sidecar_cap_tampering(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["resident_sidecar_state"]["total_bytes"] = 1_100_000
    manifest["metrics"]["resident_sidecar_state"]["per_turn_growth_bytes"] = 50_000
    manifest["metrics"]["resident_sidecar_state"]["cap_bands"] = {
        "yellow_total_ratio": 99.0,
        "red_per_turn_growth_ratio": 99.0,
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "metrics": {
                    "resident_sidecar_state": {
                        "total_bytes": 800000,
                        "per_turn_growth_bytes": 40000,
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = run_hot_path_fastcheck(
        artifact,
        baseline=baseline_path,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "ready"},
    )

    assert result["status"] == "fail"
    sidecar = [check for check in result["checks"] if check["name"] == "resident_sidecar_metrics"][0]
    assert sidecar["details"]["max_total_bytes"] == 1_000_000
    assert sidecar["details"]["total_band"] == "red"
    assert result["micro_next_action_refresh"]["mode"] == "skipped"


def test_hot_path_fastcheck_missing_configured_baseline_is_not_silent(tmp_path):
    artifact = _write_artifact(tmp_path)

    with pytest.raises(FileNotFoundError):
        run_hot_path_fastcheck(artifact, baseline=tmp_path / "missing-baseline.json")
