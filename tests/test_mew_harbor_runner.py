from __future__ import annotations

import datetime as dt
import json

from mew.mew_harbor_runner import (
    DEFAULT_WORK_GUIDANCE,
    MewHarborRun,
    RUN_MODE_DEFAULTS,
    build_parser,
    build_harbor_command,
    build_mew_work_command_template,
    collect_mew_trial_summary,
    extract_harbor_reward,
    make_jobs_dir,
    observer_detail_missing,
    step_budget_preempted,
    summarize_latest_run,
    work_guidance_with_workframe_variant,
)


def _config(tmp_path, **overrides):
    values = {
        "task_name": "make-mips-interpreter",
        "dataset": "terminal-bench/terminal-bench-2",
        "jobs_dir": tmp_path / "jobs",
        "repo_root": tmp_path / "repo",
        "codex_auth_json": tmp_path / "auth.json",
        "k": 1,
        "n": 1,
        "model": "gpt-5.5",
        "model_timeout": 300,
        "max_steps": 30,
        "timeout_seconds": 660,
        "timeout_reserve_seconds": 60,
        "agent_timeout_multiplier": 2,
        "work_guidance": DEFAULT_WORK_GUIDANCE,
        "install_command": "python3 -m pip install -e /mew",
        "run_mode": "step-check-10min",
    }
    values.update(overrides)
    return MewHarborRun(**values)


def test_mew_command_template_enables_implement_v2_and_observer_detail(tmp_path):
    template = build_mew_work_command_template(_config(tmp_path))

    assert "selected_lane=implement_v2 write_integration_observation_detail=true" in template
    assert "--auth /codex-auth/auth.json" in template
    assert "--model gpt-5.5" in template
    assert "{max_wall_seconds_option}" in template
    assert "--report {report_path}" in template
    assert "--artifacts {artifact_dir}" in template


def test_run_mode_defaults_have_diagnostic_step_budgets():
    assert RUN_MODE_DEFAULTS["step-check-10min"].max_steps == 90
    assert RUN_MODE_DEFAULTS["speed-proof"].max_steps == 120
    assert RUN_MODE_DEFAULTS["proof-5"].max_steps == 120


def test_parser_leaves_max_steps_to_selected_mode_default():
    args = build_parser().parse_args(["make-mips-interpreter", "--dry-run"])

    assert args.max_steps is None


def test_mew_command_template_can_pass_workframe_variant(tmp_path):
    template = build_mew_work_command_template(_config(tmp_path, workframe_variant="transcript_first"))

    assert "workframe_variant=transcript_first" in template


def test_work_guidance_with_workframe_variant_preserves_existing_choice():
    guidance = work_guidance_with_workframe_variant(
        "selected_lane=implement_v2 workframe_variant=transition_contract",
        "minimal",
    )

    assert guidance == "selected_lane=implement_v2 workframe_variant=transition_contract"


def test_work_guidance_with_current_workframe_variant_is_explicit_override():
    guidance = work_guidance_with_workframe_variant("selected_lane=implement_v2", "current")

    assert guidance == "selected_lane=implement_v2 workframe_variant=current"


def test_build_harbor_command_uses_mew_wrapper_mounts_and_timeout_shape(tmp_path):
    config = _config(tmp_path)

    command = build_harbor_command(config)

    assert command[:7] == [
        "harbor",
        "run",
        "-d",
        "terminal-bench/terminal-bench-2",
        "-i",
        "terminal-bench/make-mips-interpreter",
        "-k",
    ]
    assert command[command.index("--agent-import-path") + 1] == "mew_terminal_bench_agent:MewTerminalBenchAgent"
    assert "--agent" not in command
    assert "timeout_seconds=660" in command
    assert "timeout_reserve_seconds=60" in command
    mounts = json.loads(command[command.index("--mounts-json") + 1])
    assert mounts == [
        {"type": "bind", "source": str(tmp_path / "repo"), "target": "/mew"},
        {"type": "bind", "source": str(tmp_path / "auth.json"), "target": "/codex-auth/auth.json"},
    ]


def test_make_jobs_dir_is_stable_and_human_readable(tmp_path):
    jobs_dir = make_jobs_dir(
        "terminal-bench/make-mips-interpreter",
        tmp_path,
        now=dt.datetime(2026, 5, 8, 17, 30, 0),
    )

    assert jobs_dir == tmp_path / "mew-make-mips-interpreter-step-check-10min-20260508-173000"


def test_make_jobs_dir_includes_run_mode(tmp_path):
    jobs_dir = make_jobs_dir(
        "make-mips-interpreter",
        tmp_path,
        now=dt.datetime(2026, 5, 8, 17, 30, 0),
        run_mode="proof-5",
    )

    assert jobs_dir == tmp_path / "mew-make-mips-interpreter-proof-5-20260508-173000"


def test_make_jobs_dir_includes_non_current_workframe_variant(tmp_path):
    jobs_dir = make_jobs_dir(
        "make-mips-interpreter",
        tmp_path,
        now=dt.datetime(2026, 5, 8, 17, 30, 0),
        workframe_variant="transcript_first",
    )

    assert jobs_dir == tmp_path / "mew-make-mips-interpreter-step-check-10min-wf-transcript-first-20260508-173000"


def test_make_jobs_dir_includes_current_workframe_variant_when_explicit(tmp_path):
    jobs_dir = make_jobs_dir(
        "make-mips-interpreter",
        tmp_path,
        now=dt.datetime(2026, 5, 8, 17, 30, 0),
        workframe_variant="current",
    )

    assert jobs_dir == tmp_path / "mew-make-mips-interpreter-step-check-10min-wf-current-20260508-173000"


def test_collect_mew_trial_summary_reports_observer_detail(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    manifest_path = unknown_task / "implement_v2" / "proof-manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "model_turns": 3,
                    "tool_calls": 4,
                    "tool_results": 4,
                    "wall_elapsed_seconds": 12.5,
                    "workframe": {"variant": "transcript_first"},
                    "integration_observation": {
                        "debug_detail_enabled": True,
                        "artifact_ref": "integration-observation.json",
                        "summary": {
                            "detail_written": True,
                            "prompt_chars": 123,
                            "model_elapsed_seconds": 9.5,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    detail_path = unknown_task / "implement_v2" / "integration-observation.json"
    detail_path.write_text("{}", encoding="utf-8")
    (unknown_task / "mew-report.json").write_text(
        json.dumps({"work_exit_code": 1, "work_report": {"stop_reason": "implement_v2_blocked"}}),
        encoding="utf-8",
    )
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["observer_detail_enabled"] is True
    assert summary["observer_detail_written"] is True
    assert summary["observer_detail_exists"] is True
    assert summary["observer_detail_path"] == str(detail_path)
    assert summary["proof_manifest_path"] == str(manifest_path)
    assert summary["history_path"] == str(manifest_path.parent / "history.json")
    assert summary["transcript_path"] == str(manifest_path.parent / "transcript.json")
    assert summary["mew_report_path"] == str(unknown_task / "mew-report.json")
    assert summary["result_path"] == str(task_dir / "result.json")
    assert summary["command_transcript_path"] == str(unknown_task / "command-transcript.json")
    assert summary["verifier_stdout_path"] == str(task_dir / "verifier" / "test-stdout.txt")
    assert summary["verifier_reward_path"] == str(task_dir / "verifier" / "reward.txt")
    assert summary["model_turns"] == 3
    assert summary["workframe_variant"] == "transcript_first"
    assert summary["prompt_chars"] == 123
    assert observer_detail_missing([summary]) is False


def test_collect_mew_trial_summary_accepts_native_artifacts_at_task_root(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    manifest_path = unknown_task / "proof-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
                "metrics": {
                    "pairing_valid": True,
                    "provider_native_tool_loop": True,
                    "model_json_main_path_detected": False,
                    "native_evidence_observation": {
                        "artifact_ref": "native-evidence-observation.json",
                        "finish_claim_count": 1,
                        "cited_evidence_ref_count": 2,
                        "unresolved_cited_evidence_ref_count": 1,
                        "resolver_block_count": 1,
                    },
                },
                "native_evidence_observation_ref": "native-evidence-observation.json",
            }
        ),
        encoding="utf-8",
    )
    response_items = [
        {"kind": "function_call", "call_id": "call-1", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-1", "status": "completed"},
    ]
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": response_items}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in response_items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "provider-request-inventory.json").write_text(
        json.dumps(
            {
                "request_count": 1,
                "provider_request_inventory": [
                    {"model_visible_sections": ["native_transcript_window", "compact_sidecar_digest"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "native-evidence-observation.json").write_text(
        json.dumps({"summary": {"unresolved_cited_evidence_ref_count": 1}}),
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(
        json.dumps({"work_exit_code": 1, "work_report": {"stop_reason": "implement_v2_blocked"}}),
        encoding="utf-8",
    )
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["proof_manifest_path"] == str(manifest_path)
    assert summary["transcript_path"] == str(unknown_task / "response_transcript.json")
    assert summary["native_observation_present"] is True
    assert summary["native_pairing_valid"] is True
    assert summary["provider_request_inventory_present"] is True
    assert summary["native_evidence_observation_present"] is True
    assert summary["native_evidence_observation_path"] == str(unknown_task / "native-evidence-observation.json")
    assert summary["native_evidence_finish_claim_count"] == 1
    assert summary["native_evidence_unresolved_cited_ref_count"] == 1
    assert observer_detail_missing([summary]) is False


def test_collect_mew_trial_summary_rejects_empty_native_artifacts(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    manifest_path = unknown_task / "proof-manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text("", encoding="utf-8")
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["proof_manifest_path"] == str(manifest_path)
    assert summary["native_observation_present"] is False
    assert summary["native_observation_reason"] == "empty_transcript"
    assert observer_detail_missing([summary]) is True


def test_collect_mew_trial_summary_accepts_request_inventory_for_pre_response_failure(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    (unknown_task / "proof-manifest.json").write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 0, "output_count": 0, "errors": []},
                "metrics": {"turn_count": 1, "provider_request_inventory_available": True},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": []}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text("", encoding="utf-8")
    (unknown_task / "provider-request-inventory.json").write_text(
        json.dumps(
            {
                "request_count": 1,
                "provider_request_inventory": [
                    {"model_visible_sections": ["native_transcript_window", "compact_sidecar_digest"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["native_observation_present"] is False
    assert summary["native_observation_reason"] == "empty_transcript"
    assert summary["provider_request_inventory_present"] is True
    assert observer_detail_missing([summary]) is False


def test_collect_mew_trial_summary_rejects_empty_request_inventory(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    (unknown_task / "proof-manifest.json").write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
            }
        ),
        encoding="utf-8",
    )
    items = [
        {"kind": "function_call", "call_id": "call-1", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-1", "status": "completed"},
    ]
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "provider-request-inventory.json").write_text(
        json.dumps({"request_count": 1, "provider_request_inventory": []}),
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["native_observation_present"] is True
    assert summary["provider_request_inventory_exists"] is True
    assert summary["provider_request_inventory_present"] is False
    assert summary["provider_request_inventory_reason"] == "empty_inventory"
    assert observer_detail_missing([summary]) is True


def test_collect_mew_trial_summary_rejects_mismatched_native_jsonl(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    items = [
        {"kind": "function_call", "call_id": "call-1", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-1", "status": "completed"},
    ]
    (unknown_task / "proof-manifest.json").write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    mismatched_items = [
        {"kind": "function_call", "call_id": "different", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "different", "status": "completed"},
    ]
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in mismatched_items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["native_observation_present"] is False
    assert summary["native_observation_reason"] == "response_items_mismatch"
    assert observer_detail_missing([summary]) is True


def test_collect_mew_trial_summary_rejects_non_strict_native_pairing(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    items = [
        {"kind": "function_call", "call_id": "call-1", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-1", "status": "completed"},
    ]
    (unknown_task / "proof-manifest.json").write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": ["stale"]},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["native_observation_present"] is False
    assert summary["native_observation_reason"] == "manifest_pairing_errors"


def test_collect_mew_trial_summary_rejects_unknown_native_item_kind(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    unknown_task.mkdir(parents=True)
    items = [
        {"kind": "function_call", "call_id": "call-1", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-1", "status": "completed"},
        {"kind": "unexpected_future_item"},
    ]
    (unknown_task / "proof-manifest.json").write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["native_observation_present"] is False
    assert summary["native_observation_reason"] == "unknown_native_item_kind"


def test_collect_mew_trial_summary_prefers_valid_native_root_over_stale_legacy(tmp_path):
    task_dir = tmp_path / "run" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    legacy = unknown_task / "implement_v2"
    legacy.mkdir(parents=True)
    (legacy / "proof-manifest.json").write_text(
        json.dumps({"metrics": {"tool_calls": 99, "tool_results": 99}}),
        encoding="utf-8",
    )
    unknown_task.mkdir(parents=True, exist_ok=True)
    response_items = [
        {"kind": "function_call", "call_id": "call-native", "tool_name": "inspect_dir"},
        {"kind": "function_call_output", "call_id": "call-native", "status": "completed"},
    ]
    root_manifest = unknown_task / "proof-manifest.json"
    root_manifest.write_text(
        json.dumps(
            {
                "runtime_id": "implement_v2_native_transcript_loop",
                "transport_kind": "provider_native",
                "pairing": {"valid": True, "call_count": 1, "output_count": 1, "errors": []},
                "metrics": {"turn_count": 1, "call_count": 1, "output_count": 1},
            }
        ),
        encoding="utf-8",
    )
    (unknown_task / "response_transcript.json").write_text(json.dumps({"items": response_items}), encoding="utf-8")
    (unknown_task / "response_items.jsonl").write_text(
        "\n".join(json.dumps(item) for item in response_items) + "\n",
        encoding="utf-8",
    )
    (unknown_task / "mew-report.json").write_text(json.dumps({"work_exit_code": 1}), encoding="utf-8")
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")

    summary = collect_mew_trial_summary(task_dir)

    assert summary["proof_manifest_path"] == str(root_manifest)
    assert summary["native_observation_present"] is True
    assert summary["tool_calls"] == 1


def test_extract_harbor_reward_reads_terminal_bench_v2_shape():
    assert extract_harbor_reward({"verifier_result": {"rewards": {"reward": 0.0}}}) == 0.0
    assert extract_harbor_reward({"reward": 1.0}) == 1.0


def test_step_budget_preempted_detects_turn_budget_before_wall_budget():
    assert step_budget_preempted(
        {
            "external_reward": 0.0,
            "model_turns": 30,
            "normalized_trace": {"total_seconds": 209.7, "timed_out": False},
        },
        max_steps=30,
        timeout_seconds=660,
    )


def test_step_budget_preempted_ignores_pass_wall_timeout_and_under_budget():
    assert not step_budget_preempted(
        {
            "external_reward": 1.0,
            "model_turns": 30,
            "normalized_trace": {"total_seconds": 209.7, "timed_out": False},
        },
        max_steps=30,
        timeout_seconds=660,
    )
    assert not step_budget_preempted(
        {
            "external_reward": 0.0,
            "model_turns": 30,
            "normalized_trace": {"total_seconds": 209.7, "timed_out": True},
        },
        max_steps=30,
        timeout_seconds=660,
    )
    assert not step_budget_preempted(
        {
            "external_reward": 0.0,
            "model_turns": 29,
            "normalized_trace": {"total_seconds": 209.7, "timed_out": False},
        },
        max_steps=30,
        timeout_seconds=660,
    )


def test_summarize_latest_run_normalizes_nested_mew_unknown_task_trace(tmp_path):
    config = _config(tmp_path)
    task_dir = config.jobs_dir / "2026-05-09__07-30-24" / "trial"
    unknown_task = task_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
    manifest_dir = unknown_task / "implement_v2"
    manifest_dir.mkdir(parents=True)
    (task_dir / "result.json").write_text(json.dumps({"reward": 0.0}), encoding="utf-8")
    (unknown_task / "mew-report.json").write_text(
        json.dumps({"work_exit_code": 1, "work_report": {"steps": []}}),
        encoding="utf-8",
    )
    (unknown_task / "command-transcript.json").write_text(json.dumps({}), encoding="utf-8")
    (manifest_dir / "proof-manifest.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "tool_calls": 1,
                    "tool_results": 1,
                    "integration_observation": {"summary": {"detail_written": True}},
                }
            }
        ),
        encoding="utf-8",
    )
    (manifest_dir / "integration-observation.json").write_text(
        json.dumps({"turns": [{"turn_index": 1, "elapsed_seconds": 1.25}]}),
        encoding="utf-8",
    )
    (manifest_dir / "history.json").write_text(
        json.dumps(
            [
                {
                    "turn": 1,
                    "summary": "run a verifier",
                    "tool_calls": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "run_command",
                            "arguments": {"cmd": "pytest -q"},
                        }
                    ],
                    "tool_results": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "run_command",
                            "status": "completed",
                            "content": {"content": [{"exit_code": 0}]},
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    summary = summarize_latest_run(config)[0]

    assert summary["trace_dir"] == str(task_dir / "normalized-trace")
    assert summary["normalized_trace"]["command_count"] == 1
    assert summary["normalized_trace"]["message_count"] == 1
    assert summary["configured_max_steps"] == 30
    assert summary["configured_timeout_seconds"] == 660
    assert summary["step_budget_preempted"] is False
    assert (task_dir / "normalized-trace" / "summary.json").exists()


def test_observer_detail_missing_detects_summary_only_run():
    assert observer_detail_missing(
        [
            {
                "observer_detail_enabled": True,
                "observer_detail_written": False,
                "observer_detail_exists": False,
            }
        ]
    )
