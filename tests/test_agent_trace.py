from __future__ import annotations

import json

from mew.agent_trace import main, normalize_harbor_agent_trace


def write_jsonl(path, records, append=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(record) for record in records) + "\n"
    if append:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
    else:
        path.write_text(content, encoding="utf-8")


def test_normalize_codex_stdout_tool_calls_and_summary(tmp_path):
    task_dir = tmp_path / "task"
    stdout = task_dir / "codex.txt"
    stdout.parent.mkdir(parents=True, exist_ok=True)
    stdout.write_text("Reading additional input from stdin...\n", encoding="utf-8")
    write_jsonl(
        stdout,
        [
            {"type": "thread.started", "thread_id": "thread-1"},
            {
                "type": "item.started",
                "item": {"id": "cmd-1", "type": "command_execution", "command": "pytest -q"},
            },
            {
                "type": "item.completed",
                "item": {
                    "id": "cmd-1",
                    "type": "command_execution",
                    "command": "pytest -q",
                    "exit_code": 0,
                    "status": "completed",
                },
            },
            {"item": {"type": "agent_message", "text": "done"}},
            {"msg": {"type": "token_count", "input_tokens": 10, "output_tokens": 2}},
        ],
        append=True,
    )
    (task_dir / "raw").mkdir(parents=True, exist_ok=True)
    (task_dir / "raw" / "stderr.log").write_text("warning\n", encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(
        json.dumps({"exit_code": 0, "timed_out": False, "timeout_seconds": 600}),
        encoding="utf-8",
    )

    events, summary = normalize_harbor_agent_trace(agent="codex", task_dir=task_dir)

    assert [event["kind"] for event in events] == ["session", "tool_call", "tool_call", "message", "usage"]
    assert summary["agent"] == "codex"
    assert summary["tool_call_count"] == 2
    assert summary["command_event_count"] == 2
    assert summary["command_count"] == 1
    assert summary["verifier_event_count"] == 2
    assert summary["verifier_count"] == 1
    assert summary["message_count"] == 1
    assert summary["exit_code"] == 0
    assert summary["stderr_bytes"] == len("warning\n")


def test_normalize_claude_stdout_tool_use_and_result(tmp_path):
    task_dir = tmp_path / "task"
    stdout = task_dir / "claude-code.txt"
    write_jsonl(
        stdout,
        [
            {"type": "system", "session_id": "session-1"},
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {"type": "text", "text": "checking"},
                        {"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {"command": "pytest -q"}},
                    ]
                },
            },
            {
                "type": "user",
                "message": {
                    "content": [
                        {"type": "tool_result", "tool_use_id": "tool-1", "content": "passed", "is_error": False}
                    ]
                },
            },
            {"type": "result", "result": "done", "usage": {"input_tokens": 12}},
        ],
    )

    events, summary = normalize_harbor_agent_trace(agent="claude", task_dir=task_dir)

    assert [event["kind"] for event in events] == ["session", "message", "tool_call", "tool_call", "result"]
    assert events[2]["phase"] == "started"
    assert events[3]["phase"] == "completed"
    assert summary["agent"] == "claude"
    assert summary["tool_call_started_count"] == 1
    assert summary["tool_call_completed_count"] == 1
    assert summary["command_count"] == 1
    assert summary["verifier_event_count"] == 2
    assert summary["verifier_count"] == 1


def test_normalize_harbor_builtin_agent_log_path(tmp_path):
    task_dir = tmp_path / "task"
    write_jsonl(
        task_dir / "agent" / "claude-code.txt",
        [
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "id": "tool-1", "name": "Bash", "input": {}}]},
            }
        ],
    )

    events, summary = normalize_harbor_agent_trace(agent="claude", task_dir=task_dir)

    assert events[0]["tool"] == "Bash"
    assert summary["tool_call_started_count"] == 1


def test_normalize_atif_trajectory_timeline_and_summary(tmp_path):
    task_dir = tmp_path / "task"
    trajectory = {
        "steps": [
            {
                "step_id": 1,
                "timestamp": "2026-05-05T00:00:00.000Z",
                "source": "user",
                "message": "fix it",
            },
            {
                "step_id": 2,
                "timestamp": "2026-05-05T00:00:02.000Z",
                "source": "agent",
                "message": "Executed exec_command call-1",
                "tool_calls": [
                    {
                        "tool_call_id": "call-1",
                        "function_name": "exec_command",
                        "arguments": {"cmd": "pytest -q"},
                    }
                ],
                "observation": {
                    "results": [
                        {
                            "source_call_id": "call-1",
                            "content": "Wall time: 0.250 seconds\nProcess exited with code 0",
                        }
                    ]
                },
            },
            {
                "step_id": 3,
                "timestamp": "2026-05-05T00:00:05.000Z",
                "source": "agent",
                "message": "Executed apply_patch call-2",
                "tool_calls": [
                    {
                        "tool_call_id": "call-2",
                        "function_name": "apply_patch",
                        "arguments": {"input": "*** Begin Patch\n*** End Patch\n"},
                    }
                ],
                "extra": {"tool_metadata": {"exit_code": 0, "duration_seconds": 0.5}},
            },
        ]
    }
    trajectory_path = task_dir / "agent" / "trajectory.json"
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")

    events, summary = normalize_harbor_agent_trace(agent="codex", task_dir=task_dir)

    assert events[0]["kind"] == "input"
    command_completed = [event for event in events if event.get("tool") == "exec_command" and event.get("phase") == "completed"][0]
    assert command_completed["timestamp"] == "2026-05-05T00:00:02.000Z"
    assert command_completed["duration_ms"] == 250
    assert command_completed["elapsed_ms"] == 2000
    assert summary["total_seconds"] == 5.0
    assert summary["first_command_seconds"] == 1.75
    assert summary["first_edit_seconds"] == 4.5
    assert summary["first_verifier_seconds"] == 1.75
    assert summary["command_duration_seconds"] == 0.25
    assert summary["command_duration_observed_count"] == 1


def test_coqc_version_is_not_counted_as_verifier(tmp_path):
    task_dir = tmp_path / "task"
    trajectory = {
        "steps": [
            {"step_id": 1, "timestamp": "2026-05-05T00:00:00.000Z", "source": "user", "message": "fix"},
            {
                "step_id": 2,
                "timestamp": "2026-05-05T00:00:01.000Z",
                "source": "agent",
                "message": "Executed exec_command call-1",
                "tool_calls": [
                    {"tool_call_id": "call-1", "function_name": "exec_command", "arguments": {"cmd": "coqc --version"}}
                ],
            },
            {
                "step_id": 3,
                "timestamp": "2026-05-05T00:00:03.000Z",
                "source": "agent",
                "message": "Executed exec_command call-2",
                "tool_calls": [
                    {"tool_call_id": "call-2", "function_name": "exec_command", "arguments": {"cmd": "coqc plus.v"}}
                ],
            },
        ]
    }
    trajectory_path = task_dir / "agent" / "trajectory.json"
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")

    _, summary = normalize_harbor_agent_trace(agent="codex", task_dir=task_dir)

    assert summary["verifier_count"] == 1
    assert summary["first_verifier_seconds"] == 3.0


def test_normalize_mew_report_steps(tmp_path):
    task_dir = tmp_path / "task"
    report = {
        "work_report": {
            "steps": [
                {
                    "index": 1,
                    "status": "completed",
                    "action": {
                        "type": "run_command",
                        "command": "python -m pytest -q",
                        "execution_contract": {
                            "purpose": "verify",
                            "stage": "verification",
                            "risk_class": "read_only",
                            "proof_role": "acceptance",
                        },
                    },
                }
            ]
        }
    }
    (task_dir / "mew-report.json").parent.mkdir(parents=True, exist_ok=True)
    (task_dir / "mew-report.json").write_text(json.dumps(report), encoding="utf-8")

    events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert len(events) == 1
    assert events[0]["agent"] == "mew"
    assert events[0]["tool"] == "run_command"
    assert events[0]["execution_contract"]["purpose"] == "verify"
    assert summary["command_count"] == 1
    assert summary["verifier_count"] == 1


def test_agent_trace_cli_writes_outputs(tmp_path, capsys):
    task_dir = tmp_path / "task"
    write_jsonl(task_dir / "raw" / "stdout.jsonl", [{"item": {"type": "agent_message", "text": "ok"}}])
    out_dir = tmp_path / "out"

    assert main(["--agent", "codex", "--task-dir", str(task_dir), "--out", str(out_dir), "--json"]) == 0

    assert (out_dir / "agent_trace.jsonl").exists()
    assert (out_dir / "summary.json").exists()
    printed = json.loads(capsys.readouterr().out)
    assert printed["message_count"] == 1
