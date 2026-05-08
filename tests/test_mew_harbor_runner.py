from __future__ import annotations

import datetime as dt
import json

from mew.mew_harbor_runner import (
    MewHarborRun,
    build_harbor_command,
    build_mew_work_command_template,
    collect_mew_trial_summary,
    make_jobs_dir,
    observer_detail_missing,
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
        "work_guidance": "selected_lane=implement_v2 write_integration_observation_detail=true",
        "install_command": "python3 -m pip install -e /mew",
        "run_mode": "step-check-10min",
    }
    values.update(overrides)
    return MewHarborRun(**values)


def test_mew_command_template_enables_implement_v2_and_observer_detail(tmp_path):
    template = build_mew_work_command_template(_config(tmp_path))

    assert "--work-guidance 'selected_lane=implement_v2 write_integration_observation_detail=true'" in template
    assert "--auth /codex-auth/auth.json" in template
    assert "--model gpt-5.5" in template
    assert "{max_wall_seconds_option}" in template
    assert "--report {report_path}" in template
    assert "--artifacts {artifact_dir}" in template


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
    assert summary["model_turns"] == 3
    assert summary["prompt_chars"] == 123
    assert observer_detail_missing([summary]) is False


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
