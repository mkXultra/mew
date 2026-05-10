import json
from pathlib import Path

import pytest

from mew.implement_lane.hot_path_fastcheck import run_hot_path_fastcheck
from mew.implement_lane.workframe import WorkFrameInputs, canonicalize_workframe_inputs, reduce_workframe


def _write_artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "artifact"
    implement_v2 = artifact / "implement_v2"
    implement_v2.mkdir(parents=True)
    manifest = {
        "lane": "implement_v2",
        "metrics": {
            "hot_path_projection": {
                "phase": "m6_24_workframe_redesign_phase_1",
                "normal_full_prompt_bytes": 1024,
                "normal_full_prompt_bytes_total": 2048,
                "provider_visible_tool_result_bytes": 128,
                "normal_section_inventory": [
                    {
                        "id": "implement_v2_workframe",
                        "visibility": "ordinary",
                        "stability": "dynamic",
                        "cache_policy": "dynamic",
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
            "workframe": {
                "schema_version": 1,
                "phase": "m6_24_workframe_redesign_phase_6",
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
    workframe = _write_workframe_bundle(implement_v2 / "workframes" / "turn-1")
    manifest["metrics"]["workframe"]["input_hash"] = workframe.trace.input_hash
    manifest["metrics"]["workframe"]["output_hash"] = workframe.trace.output_hash
    (implement_v2 / "proof-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (implement_v2 / "history.json").write_text(json.dumps(history), encoding="utf-8")
    return artifact


def _workframe_inputs(
    *,
    summary: str = "TypeError: missing opcode handler",
    success_contract_ref: str = "",
    sidecar_events: tuple[dict[str, object], ...] | None = None,
) -> WorkFrameInputs:
    return WorkFrameInputs(
        attempt_id="attempt-1",
        turn_id="turn-1",
        task_id="task-1",
        objective="Repair the workspace.",
        success_contract_ref=success_contract_ref,
        constraints=("model_visible_workframe_only",),
        sidecar_events=sidecar_events
        or (
            {
                "kind": "verifier",
                "event_sequence": 1,
                "event_id": "verify-1",
                "status": "failed",
                "family": "runtime_verifier_failure",
                "summary": summary,
                "evidence_refs": ["ev:verify-1"],
            },
        ),
        prompt_inventory=(
            {
                "id": "implement_v2_workframe",
                "visibility": "ordinary",
                "stability": "dynamic",
                "cache_policy": "dynamic",
                "bytes": 256,
            },
        ),
    )


def _write_workframe_bundle(root: Path, inputs: WorkFrameInputs | None = None):
    root.mkdir(parents=True, exist_ok=True)
    inputs = inputs or _workframe_inputs()
    workframe, report = reduce_workframe(inputs)
    files = {
        "reducer_inputs.json": {
            "schema_version": 1,
            "workframe_inputs": inputs.as_dict(),
            "canonical": canonicalize_workframe_inputs(inputs),
        },
        "reducer_output.workframe.json": workframe.as_dict(),
        "invariant_report.json": report.as_dict(),
        "prompt_visible_workframe.json": {
            "workframe": workframe.as_dict(),
            "rule": "This is the only ordinary dynamic state object.",
        },
        "prompt_render_inventory.json": {
            "schema_version": 1,
            "sections": list(inputs.prompt_inventory),
        },
        "workframe_cursor.json": {
            "schema_version": 1,
            "attempt_id": inputs.attempt_id,
            "turn_id": inputs.turn_id,
            "workframe_id": workframe.trace.workframe_id,
            "input_hash": workframe.trace.input_hash,
            "output_hash": workframe.trace.output_hash,
        },
    }
    for filename, payload in files.items():
        (root / filename).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return workframe


def _set_manifest_workframe_hashes(artifact: Path, workframe, *, bundle_root: str = "") -> None:
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["input_hash"] = workframe.trace.input_hash
    manifest["metrics"]["workframe"]["output_hash"] = workframe.trace.output_hash
    if bundle_root:
        manifest["metrics"]["workframe"]["bundle_root"] = bundle_root
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


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


def test_hot_path_fastcheck_binds_micro_fixture_to_workframe_hash(tmp_path):
    artifact = _write_artifact(tmp_path)
    fixture_path = tmp_path / "micro.json"
    calls = []

    def first_model(prompt):
        calls.append(prompt)
        return {"category": "patch/edit", "reason": "first frame"}

    first = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=first_model,
    )

    assert first["status"] == "pass"
    assert first["micro_next_action_refresh"]["mode"] == "refreshed"

    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(summary="ReferenceError: missing helper after patch"),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    def second_model(prompt):
        calls.append(prompt)
        assert "ReferenceError: missing helper after patch" in prompt
        return {"category": "patch/edit", "reason": "refreshed frame"}

    second = run_hot_path_fastcheck(
        artifact,
        micro_next_action=fixture_path,
        expected_categories=("patch/edit",),
        micro_model_callable=second_model,
    )

    assert second["status"] == "pass"
    assert second["micro_next_action_refresh"]["mode"] == "refreshed"
    assert len(calls) == 2


def test_hot_path_fastcheck_uses_manifest_workframe_bundle_root(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["bundle_root"] = "workframes/turn-selected"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    selected = _write_workframe_bundle(artifact / "implement_v2" / "workframes" / "turn-selected")
    _set_manifest_workframe_hashes(artifact, selected, bundle_root="workframes/turn-selected")
    bad_root = artifact / "implement_v2" / "workframes" / "turn-z-stale"
    _write_workframe_bundle(bad_root)
    output_path = bad_root / "reducer_output.workframe.json"
    output = json.loads(output_path.read_text(encoding="utf-8"))
    output["trace"]["output_hash"] = "sha256:stale"
    output_path.write_text(json.dumps(output), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "selected bundle"},
    )

    assert result["status"] == "pass"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["bundle_dir"].endswith("turn-selected")


def test_hot_path_fastcheck_rejects_manifest_workframe_hash_mismatch(tmp_path):
    artifact = _write_artifact(tmp_path)
    manifest_path = artifact / "implement_v2" / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["metrics"]["workframe"]["output_hash"] = "sha256:wrong"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "unused"},
    )

    assert result["status"] == "fail"
    replay = [check for check in result["checks"] if check["name"] == "workframe_replay"][0]
    assert replay["details"]["manifest_output_hash_matches"] is False


def test_hot_path_fastcheck_resolves_configured_verifier_ref(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            success_contract_ref="task-contract:pytest",
            sidecar_events=(
                {
                    "kind": "source_mutation",
                    "event_sequence": 1,
                    "event_id": "write-1",
                    "path": "src/app.py",
                    "evidence_refs": ["sidecar:write-1"],
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("run_verifier",),
        micro_model_callable=lambda _prompt: {"category": "run_verifier", "reason": "verify changed source"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


def test_hot_path_fastcheck_resolves_paired_finish_gate_support_refs(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            sidecar_events=(
                {
                    "kind": "strict_verifier",
                    "event_sequence": 1,
                    "event_id": "verify-1",
                    "status": "passed",
                    "evidence_refs": ["ev:verifier:1"],
                    "execution_contract_normalized": {
                        "id": "contract:verify",
                        "role": "verify",
                        "proof_role": "verifier",
                        "acceptance_kind": "external_verifier",
                    },
                },
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 2,
                    "event_id": "finish-gate-1",
                    "status": "passed",
                    "finish_gate": {"id": "finish:gate-1"},
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("finish_with_evidence",),
        micro_model_callable=lambda _prompt: {"category": "finish_with_evidence", "reason": "fresh verifier"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


def test_hot_path_fastcheck_resolves_nested_missing_obligation_refs(tmp_path):
    artifact = _write_artifact(tmp_path)
    workframe = _write_workframe_bundle(
        artifact / "implement_v2" / "workframes" / "turn-1",
        _workframe_inputs(
            sidecar_events=(
                {
                    "kind": "structured_finish_gate",
                    "event_sequence": 1,
                    "event_id": "finish-gate-1",
                    "status": "failed",
                    "reason": "finish is blocked until artifact freshness oracle obligation resolves",
                    "finish_gate": {"missing_obligations": [{"id": "oracle:artifact-fresh"}]},
                },
            ),
        ),
    )
    _set_manifest_workframe_hashes(artifact, workframe)

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("run_verifier",),
        micro_model_callable=lambda _prompt: {"category": "run_verifier", "reason": "missing obligation"},
    )

    assert result["status"] == "pass"
    evidence = [check for check in result["checks"] if check["name"] == "workframe_evidence_ref_policy"][0]
    assert evidence["status"] == "pass"


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


def test_hot_path_fastcheck_allows_same_summary_failures_with_distinct_paths(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"
    history = [
        {
            "turn": 1,
            "summary": "runtime verifier failed before artifact contract",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-before",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime-before",
                                "output_ref": "out-runtime-before",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "Error: memory access 0x00000000+4 outside mapped range",
                                },
                            }
                        ]
                    },
                }
            ],
        },
        {
            "turn": 2,
            "summary": "runtime verifier failed with artifact contract",
            "tool_calls": [],
            "tool_results": [
                {
                    "provider_call_id": "call-runtime-after",
                    "tool_name": "run_command",
                    "status": "failed",
                    "content": {
                        "content": [
                            {
                                "provider_history_projection": "terminal_result_v0",
                                "command_run_id": "cmd-runtime-after",
                                "output_ref": "out-runtime-after",
                                "latest_failure": {
                                    "phase": "runtime",
                                    "kind": "nonzero_exit",
                                    "class": "runtime_failure",
                                    "summary": "Error: memory access 0x00000000+4 outside mapped range",
                                    "path": "/tmp/frame.bmp",
                                },
                            }
                        ]
                    },
                }
            ],
        },
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "repair latest runtime failure"},
    )

    assert result["status"] == "pass"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["status"] == "pass"
    assert latest_failure["details"]["duplicate_families"] == []


def test_hot_path_fastcheck_allows_same_summary_failures_with_distinct_artifact_identities(tmp_path):
    artifact = _write_artifact(tmp_path)
    history_path = artifact / "implement_v2" / "history.json"

    def runtime_failure(provider_call_id: str, artifact_id: str, path: str) -> dict[str, object]:
        return {
            "provider_call_id": provider_call_id,
            "tool_name": "run_command",
            "status": "failed",
            "content": {
                "content": [
                    {
                        "provider_history_projection": "terminal_result_v0",
                        "command_run_id": f"cmd-{provider_call_id}",
                        "output_ref": f"out-{provider_call_id}",
                        "latest_failure": {
                            "phase": "runtime",
                            "kind": "nonzero_exit",
                            "class": "runtime_failure",
                            "summary": "Error: memory access 0x00000000+4 outside mapped range",
                        },
                        "execution_evidence_digest": {
                            "artifact_miss": [{"artifact_id": artifact_id, "path": path}]
                        },
                    }
                ]
            },
        }

    history = [
        {
            "turn": 1,
            "summary": "first artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-frame", "frame", "/tmp/frame.bmp")],
        },
        {
            "turn": 2,
            "summary": "second artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-log", "log", "/tmp/run.log")],
        },
        {
            "turn": 3,
            "summary": "third artifact verifier failed",
            "tool_calls": [],
            "tool_results": [runtime_failure("call-runtime-json", "json", "/tmp/result.json")],
        },
    ]
    history_path.write_text(json.dumps(history), encoding="utf-8")

    result = run_hot_path_fastcheck(
        artifact,
        micro_next_action=tmp_path / "micro.json",
        expected_categories=("patch/edit",),
        micro_model_callable=lambda _prompt: {"category": "patch/edit", "reason": "repair latest artifact failure"},
    )

    assert result["status"] == "pass"
    latest_failure = [check for check in result["checks"] if check["name"] == "latest_actionable_failure_shape"][0]
    assert latest_failure["status"] == "pass"
    assert latest_failure["details"]["duplicate_families"] == []


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
