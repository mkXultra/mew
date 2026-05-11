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


def test_normalize_mew_native_response_transcript_counts_tools(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "mew-report.json").write_text(json.dumps({"work_report": {"steps": []}}), encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(
        json.dumps({"exit_code": 1, "timed_out": False, "timeout_seconds": 660}),
        encoding="utf-8",
    )
    items = [
        {"sequence": 1, "kind": "reasoning", "turn_id": "turn-1"},
        {
            "sequence": 2,
            "kind": "function_call",
            "turn_id": "turn-1",
            "call_id": "call-read",
            "tool_name": "inspect_dir",
            "arguments_json_text": "{\"path\":\".\",\"max_entries\":50}",
            "output_index": 1,
        },
        {
            "sequence": 3,
            "kind": "function_call_output",
            "turn_id": "turn-1",
            "call_id": "call-read",
            "tool_name": "inspect_dir",
            "status": "completed",
            "output_text_or_ref": "inspect_dir result: completed",
        },
        {
            "sequence": 4,
            "kind": "function_call",
            "turn_id": "turn-2",
            "call_id": "call-write",
            "tool_name": "write_file",
            "arguments_json_text": "{\"path\":\"output.txt\"}",
            "output_index": 1,
        },
        {
            "sequence": 5,
            "kind": "function_call_output",
            "turn_id": "turn-2",
            "call_id": "call-write",
            "tool_name": "write_file",
            "status": "completed",
            "output_text_or_ref": "write_file result: completed",
        },
        {
            "sequence": 6,
            "kind": "function_call",
            "turn_id": "turn-3",
            "call_id": "call-test",
            "tool_name": "run_tests",
            "arguments_json_text": "{\"command\":\"grep -qx OK output.txt\"}",
            "output_index": 1,
        },
        {
            "sequence": 7,
            "kind": "function_call_output",
            "turn_id": "turn-3",
            "call_id": "call-test",
            "tool_name": "run_tests",
            "status": "completed",
            "output_text_or_ref": "run_tests result: completed; exit_code=0",
        },
    ]
    (task_dir / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (task_dir / "proof-manifest.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "tool_latency": [
                        {"call_id": "call-read", "tool_name": "inspect_dir", "started_ms": 1000, "finished_ms": 2},
                        {"call_id": "call-write", "tool_name": "write_file", "started_ms": 2000, "finished_ms": 3},
                        {"call_id": "call-test", "tool_name": "run_tests", "started_ms": 3000, "finished_ms": 4},
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["tool_call_count"] == 6
    assert summary["edit_count"] == 1
    assert summary["verifier_count"] == 1
    assert summary["first_tool_seconds"] == 1.0
    assert summary["first_edit_seconds"] == 2.0
    assert summary["first_verifier_seconds"] == 3.0
    assert any(event.get("exit_code") == 0 for event in events)


def test_normalize_mew_native_response_transcript_reports_pairing_errors(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "mew-report.json").write_text(json.dumps({"work_report": {"steps": []}}), encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(json.dumps({}), encoding="utf-8")
    (task_dir / "response_transcript.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "kind": "function_call",
                        "turn_id": "turn-1",
                        "call_id": "call-bad",
                        "tool_name": "read_file",
                        "arguments_json_text": "{not json",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (task_dir / "proof-manifest.json").write_text(json.dumps({}), encoding="utf-8")

    events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["parse_error_count"] == 3
    assert summary["tool_call_started_count"] == 1
    assert summary["tool_call_completed_count"] == 0
    assert any("invalid native tool arguments JSON" in event.get("summary", "") for event in events)
    assert any("missing native tool output" in event.get("summary", "") for event in events)


def test_normalize_mew_native_response_transcript_excludes_read_command_output_from_commands(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "mew-report.json").write_text(json.dumps({"work_report": {"steps": []}}), encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(json.dumps({}), encoding="utf-8")
    items = [
        {
            "kind": "function_call",
            "turn_id": "turn-1",
            "call_id": "call-poll",
            "tool_name": "read_command_output",
            "arguments_json_text": "{\"command_id\":\"cmd-1\"}",
        },
        {
            "kind": "function_call_output",
            "turn_id": "turn-1",
            "call_id": "call-poll",
            "tool_name": "read_command_output",
            "status": "completed",
            "output_text_or_ref": "still running",
        },
    ]
    (task_dir / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (task_dir / "proof-manifest.json").write_text(json.dumps({}), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["tool_call_count"] == 2
    assert summary["command_count"] == 0


def test_normalize_mew_native_response_transcript_flags_duplicate_call_ids(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "mew-report.json").write_text(json.dumps({"work_report": {"steps": []}}), encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(json.dumps({}), encoding="utf-8")
    items = [
        {
            "kind": "function_call",
            "turn_id": "turn-1",
            "call_id": "call-dup",
            "tool_name": "inspect_dir",
            "arguments_json_text": "{\"path\":\".\"}",
        },
        {
            "kind": "function_call",
            "turn_id": "turn-2",
            "call_id": "call-dup",
            "tool_name": "read_file",
            "arguments_json_text": "{\"path\":\"main.c\"}",
        },
        {
            "kind": "function_call_output",
            "turn_id": "turn-2",
            "call_id": "call-dup",
            "tool_name": "inspect_dir",
            "status": "completed",
            "output_text_or_ref": "ok",
        },
    ]
    (task_dir / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (task_dir / "proof-manifest.json").write_text(json.dumps({}), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["parse_error_count"] >= 1
    assert summary["tool_call_started_count"] == 2
    assert summary["tool_call_completed_count"] == 1


def test_normalize_mew_native_response_transcript_flags_call_output_kind_mismatch(tmp_path):
    task_dir = tmp_path / "task"
    task_dir.mkdir(parents=True)
    (task_dir / "mew-report.json").write_text(json.dumps({"work_report": {"steps": []}}), encoding="utf-8")
    (task_dir / "command-transcript.json").write_text(json.dumps({}), encoding="utf-8")
    items = [
        {
            "kind": "function_call",
            "turn_id": "turn-1",
            "call_id": "call-kind",
            "tool_name": "inspect_dir",
            "arguments_json_text": "{\"path\":\".\"}",
        },
        {
            "kind": "custom_tool_call_output",
            "turn_id": "turn-1",
            "call_id": "call-kind",
            "tool_name": "inspect_dir",
            "status": "completed",
            "output_text_or_ref": "ok",
        },
    ]
    (task_dir / "response_transcript.json").write_text(json.dumps({"items": items}), encoding="utf-8")
    (task_dir / "proof-manifest.json").write_text(json.dumps({}), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["parse_error_count"] >= 1
    assert summary["tool_call_started_count"] == 1
    assert summary["tool_call_completed_count"] == 0


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


def test_normalize_mew_implement_v2_history_tool_calls_and_summary(tmp_path):
    task_dir = tmp_path / "task"
    report = {
        "work_report": {
            "steps": [
                {
                    "index": 1,
                    "status": "blocked",
                    "action": {"type": "implement_lane", "lane": "implement_v2"},
                    "model_turn": {"started_at": "2026-05-08T00:00:00Z"},
                }
            ]
        }
    }
    (task_dir / "mew-report.json").parent.mkdir(parents=True, exist_ok=True)
    (task_dir / "mew-report.json").write_text(json.dumps(report), encoding="utf-8")
    impl_dir = task_dir / "implement_v2"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "integration-observation.json").write_text(
        json.dumps(
            {
                "turns": [
                    {"turn_index": 1, "elapsed_seconds": 1.0},
                    {"turn_index": 2, "elapsed_seconds": 2.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    (impl_dir / "history.json").write_text(
        json.dumps(
            [
                {
                    "turn": 1,
                    "summary": "Inspect the task.",
                    "tool_calls": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "inspect_dir",
                            "arguments": {"path": "."},
                        }
                    ],
                    "tool_results": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "inspect_dir",
                            "status": "completed",
                            "content": {"content": [{"summary": "Inspected directory"}], "side_effects": []},
                        }
                    ],
                },
                {
                    "turn": 2,
                    "summary": "Write and verify.",
                    "tool_calls": [
                        {
                            "provider_call_id": "call-2",
                            "tool_name": "write_file",
                            "arguments": {"path": "vm.js", "content": "console.log(1)"},
                        },
                        {
                            "provider_call_id": "call-3",
                            "tool_name": "run_command",
                            "arguments": {
                                "cmd": "node vm.js",
                                "execution_contract": {"proof_role": "verifier", "expected_exit": 0},
                            },
                        },
                    ],
                    "tool_results": [
                        {
                            "provider_call_id": "call-2",
                            "tool_name": "write_file",
                            "status": "completed",
                            "content": {
                                "content": [
                                    {
                                        "operation": "write_file",
                                        "path": "/app/vm.js",
                                        "started_at": "2026-05-08T00:00:03Z",
                                        "finished_at": "2026-05-08T00:00:03Z",
                                    }
                                ],
                                "side_effects": [{"kind": "file_write", "path": "/app/vm.js"}],
                            },
                        },
                        {
                            "provider_call_id": "call-3",
                            "tool_name": "run_command",
                            "status": "completed",
                            "content": {
                                "side_effects": [
                                    {
                                        "kind": "tool_run_record",
                                        "record": {
                                            "record_id": "run-1",
                                            "provider_call_id": "call-3",
                                            "started_at": "2026-05-08T00:00:04Z",
                                            "finished_at": "2026-05-08T00:00:05Z",
                                            "duration_seconds": 1.0,
                                            "status": "completed",
                                            "exit_code": 0,
                                        },
                                    },
                                    {
                                        "kind": "command_run",
                                        "record": {"terminal_record_id": "run-1", "status": "completed"},
                                    },
                                ]
                            },
                        },
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )

    events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["message_count"] == 2
    assert summary["tool_call_started_count"] == 3
    assert summary["tool_call_completed_count"] == 3
    assert summary["command_count"] == 1
    assert summary["edit_count"] == 1
    assert summary["verifier_count"] == 1
    assert summary["first_tool_seconds"] == 1.0
    assert summary["first_edit_seconds"] == 3.0
    assert summary["first_command_seconds"] == 4.0
    assert summary["first_verifier_seconds"] == 4.0
    assert summary["command_duration_seconds"] == 1.0
    write_started = [event for event in events if event.get("tool") == "write_file" and event.get("phase") == "started"][0]
    assert write_started["arguments"]["content_chars"] == len("console.log(1)")
    assert "content" not in write_started["arguments"]


def test_normalize_mew_implement_v2_history_command_metadata_without_side_effects(tmp_path):
    task_dir = tmp_path / "task"
    report = {"work_report": {"steps": [{"model_turn": {"started_at": "2026-05-08T00:00:00Z"}}]}}
    (task_dir / "mew-report.json").parent.mkdir(parents=True, exist_ok=True)
    (task_dir / "mew-report.json").write_text(json.dumps(report), encoding="utf-8")
    impl_dir = task_dir / "implement_v2"
    impl_dir.mkdir(parents=True, exist_ok=True)
    (impl_dir / "history.json").write_text(
        json.dumps(
            [
                {
                    "turn": 1,
                    "tool_calls": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "run_command",
                            "arguments": {
                                "cmd": "pytest -q",
                                "execution_contract": {"proof_role": "verifier"},
                            },
                        }
                    ],
                    "tool_results": [
                        {
                            "provider_call_id": "call-1",
                            "tool_name": "run_command",
                            "status": "completed",
                            "content": {
                                "content": [
                                    {
                                        "command": "pytest -q",
                                        "started_at": "2026-05-08T00:00:02Z",
                                        "finished_at": "2026-05-08T00:00:02.250Z",
                                        "duration_seconds": 0.25,
                                        "status": "completed",
                                        "exit_code": 0,
                                    }
                                ],
                                "side_effects": [],
                            },
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )

    events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["command_count"] == 1
    assert summary["verifier_count"] == 1
    assert summary["first_verifier_seconds"] == 2.0
    assert summary["command_duration_observed_count"] == 1
    assert summary["command_duration_seconds"] == 0.25
    completed = [event for event in events if event.get("tool") == "run_command" and event.get("phase") == "completed"][0]
    assert completed["exit_code"] == 0
    assert completed["status"] == "completed"


def test_summarize_trace_reports_frontier_anchor_to_patch_and_broad_cycles(tmp_path):
    task_dir = tmp_path / "task"
    report = {
        "work_report": {
            "steps": [
                {
                    "index": 1,
                    "status": "completed",
                    "action": {
                        "type": "search_text",
                        "query": "same-family anchor",
                        "reason": "active compatibility frontier anchor search",
                    },
                    "elapsed_ms": 1000,
                },
                {
                    "index": 2,
                    "status": "completed",
                    "action": {
                        "type": "run_tests",
                        "command": "pytest -q",
                        "reason": "active compatibility frontier broad verifier cycle",
                    },
                    "elapsed_ms": 3000,
                },
                {
                    "index": 3,
                    "status": "completed",
                    "action": {
                        "type": "edit_file",
                        "path": "src/widget.py",
                        "reason": "patch same-family frontier candidate",
                    },
                    "elapsed_ms": 7000,
                },
            ]
        }
    }
    (task_dir / "mew-report.json").parent.mkdir(parents=True, exist_ok=True)
    (task_dir / "mew-report.json").write_text(json.dumps(report), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["frontier_first_anchor_seconds"] == 1.0
    assert summary["frontier_first_patch_seconds"] == 7.0
    assert summary["time_from_first_anchor_to_first_patch_seconds"] == 6.0
    assert summary["same_frontier_broad_cycle_count"] == 1


def test_summarize_trace_counts_structured_broad_cycle_without_frontier_words(tmp_path):
    task_dir = tmp_path / "task"
    report = {
        "work_report": {
            "steps": [
                {
                    "index": 1,
                    "status": "completed",
                    "action": {"type": "search_text", "query": "WidgetError"},
                    "elapsed_ms": 1000,
                },
                {
                    "index": 2,
                    "status": "completed",
                    "action": {"type": "run_tests", "command": "pytest -q", "reason": "rerun broad suite"},
                    "model_turn": {
                        "metrics": {
                            "active_compatibility_frontier_guard": {
                                "blocked_action_kind": "broad_verifier",
                                "original_action_type": "run_tests",
                                "replacement_action_type": "read_file",
                            }
                        }
                    },
                    "elapsed_ms": 3000,
                },
                {
                    "index": 3,
                    "status": "completed",
                    "action": {"type": "edit_file", "path": "src/widget.py"},
                    "elapsed_ms": 7000,
                },
            ]
        }
    }
    (task_dir / "mew-report.json").parent.mkdir(parents=True, exist_ok=True)
    (task_dir / "mew-report.json").write_text(json.dumps(report), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="mew", task_dir=task_dir)

    assert summary["frontier_first_anchor_seconds"] == 1.0
    assert summary["frontier_first_patch_seconds"] == 7.0
    assert summary["time_from_first_anchor_to_first_patch_seconds"] == 6.0
    assert summary["same_frontier_broad_cycle_count"] == 1


def test_summarize_reference_style_trace_counts_anchor_patch_and_broad_cycle(tmp_path):
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
                    {"tool_call_id": "call-1", "function_name": "exec_command", "arguments": {"cmd": "rg WidgetError src"}}
                ],
            },
            {
                "step_id": 3,
                "timestamp": "2026-05-05T00:00:03.000Z",
                "source": "agent",
                "message": "Executed exec_command call-2",
                "tool_calls": [
                    {"tool_call_id": "call-2", "function_name": "exec_command", "arguments": {"cmd": "pytest -q"}}
                ],
            },
            {
                "step_id": 4,
                "timestamp": "2026-05-05T00:00:07.000Z",
                "source": "agent",
                "message": "Executed apply_patch call-3",
                "tool_calls": [
                    {"tool_call_id": "call-3", "function_name": "apply_patch", "arguments": {"input": "*** Begin Patch\n*** End Patch\n"}}
                ],
            },
        ]
    }
    trajectory_path = task_dir / "agent" / "trajectory.json"
    trajectory_path.parent.mkdir(parents=True, exist_ok=True)
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")

    _events, summary = normalize_harbor_agent_trace(agent="codex", task_dir=task_dir)

    assert summary["frontier_first_anchor_seconds"] == 1.0
    assert summary["frontier_first_patch_seconds"] == 7.0
    assert summary["time_from_first_anchor_to_first_patch_seconds"] == 6.0
    assert summary["same_frontier_broad_cycle_count"] == 1


def test_agent_trace_cli_writes_outputs(tmp_path, capsys):
    task_dir = tmp_path / "task"
    write_jsonl(task_dir / "raw" / "stdout.jsonl", [{"item": {"type": "agent_message", "text": "ok"}}])
    out_dir = tmp_path / "out"

    assert main(["--agent", "codex", "--task-dir", str(task_dir), "--out", str(out_dir), "--json"]) == 0

    assert (out_dir / "agent_trace.jsonl").exists()
    assert (out_dir / "summary.json").exists()
    printed = json.loads(capsys.readouterr().out)
    assert printed["message_count"] == 1
