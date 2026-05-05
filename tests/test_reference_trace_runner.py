from __future__ import annotations

import datetime as dt

from mew.reference_trace_runner import ReferenceTraceRun, build_harbor_command, make_jobs_dir


def test_build_codex_harbor_command_includes_defaults(tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("CLAUDE_CODE_OAUTH_TOKEN=unused\n", encoding="utf-8")
    auth_json = tmp_path / "auth.json"
    auth_json.write_text("{}", encoding="utf-8")
    config = ReferenceTraceRun(
        task_name="prove-plus-comm",
        agent="codex",
        dataset="terminal-bench/terminal-bench-2",
        jobs_dir=tmp_path / "jobs",
        k=1,
        n=1,
        model="gpt-5.5",
        reasoning_effort="high",
        env_file=env_file,
        codex_auth_json=auth_json,
    )

    command = build_harbor_command(config)

    assert command[:7] == [
        "harbor",
        "run",
        "-d",
        "terminal-bench/terminal-bench-2",
        "-i",
        "terminal-bench/prove-plus-comm",
        "-k",
    ]
    assert "--agent" in command
    assert command[command.index("--agent") + 1] == "codex"
    assert "--env-file" in command
    assert f"CODEX_AUTH_JSON_PATH={auth_json}" in command


def test_build_claude_command_uses_claude_code_agent_without_codex_auth(tmp_path):
    config = ReferenceTraceRun(
        task_name="terminal-bench/prove-plus-comm",
        agent="claude-code",
        dataset="terminal-bench/terminal-bench-2",
        jobs_dir=tmp_path / "jobs",
        k=2,
        n=3,
        model="sonnet",
        reasoning_effort="medium",
        env_file=None,
        codex_auth_json=tmp_path / "auth.json",
    )

    command = build_harbor_command(config)

    assert command[command.index("-i") + 1] == "terminal-bench/prove-plus-comm"
    assert command[command.index("--agent") + 1] == "claude-code"
    assert command[command.index("-k") + 1] == "2"
    assert command[command.index("-n") + 1] == "3"
    assert "--env-file" not in command
    assert not any(item.startswith("CODEX_AUTH_JSON_PATH=") for item in command)


def test_make_jobs_dir_is_stable_and_human_readable(tmp_path):
    jobs_dir = make_jobs_dir(
        "claude-code",
        "terminal-bench/prove-plus-comm",
        tmp_path,
        now=dt.datetime(2026, 5, 5, 12, 34, 56),
    )

    assert jobs_dir == tmp_path / "claude-code-prove-plus-comm-20260505-123456"
