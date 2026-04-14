import os
import shlex
import subprocess
from pathlib import Path

from .tasks import clip_output
from .timeutil import now_iso


def resolve_tool_cwd(cwd=None):
    path = Path(cwd or ".").expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"tool cwd does not exist: {resolved}")
    return resolved


def split_command_env(command):
    parts = shlex.split(command or "")
    env_overrides = {}
    while parts:
        head = parts[0]
        if "=" not in head:
            break
        key, value = head.split("=", 1)
        if not key.replace("_", "").isalnum() or key[:1].isdigit():
            break
        env_overrides[key] = value
        parts = parts[1:]
    return parts, env_overrides


def run_command_record(command, cwd=None, timeout=300):
    argv, env_overrides = split_command_env(command)
    if not argv:
        raise ValueError("command is empty")

    resolved_cwd = resolve_tool_cwd(cwd)
    started_at = now_iso()
    try:
        result = subprocess.run(
            argv,
            cwd=str(resolved_cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            env={**os.environ, **env_overrides},
        )
        return {
            "command": command,
            "argv": argv,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": result.returncode,
            "stdout": clip_output(result.stdout),
            "stderr": clip_output(result.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        return {
            "command": command,
            "argv": argv,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": None,
            "stdout": clip_output(stdout),
            "stderr": clip_output(stderr or f"command timed out after {timeout} second(s)"),
        }
    except OSError as exc:
        return {
            "command": command,
            "argv": argv,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": None,
            "stdout": "",
            "stderr": str(exc),
        }


def run_git_tool(action, cwd=None, limit=20):
    resolved_cwd = resolve_tool_cwd(cwd)
    if action == "status":
        command = "git status --short"
    elif action == "diff":
        command = "git diff --"
    elif action == "log":
        safe_limit = max(1, min(int(limit), 100))
        command = f"git log --oneline -n {safe_limit}"
    else:
        raise ValueError(f"unsupported git tool action: {action}")
    return run_command_record(command, cwd=str(resolved_cwd), timeout=30)


def format_command_record(record):
    lines = [
        f"command: {record.get('command')}",
        f"cwd: {record.get('cwd')}",
        f"exit_code: {record.get('exit_code')}",
    ]
    if record.get("stdout"):
        lines.extend(["stdout:", record["stdout"]])
    if record.get("stderr"):
        lines.extend(["stderr:", record["stderr"]])
    return "\n".join(lines)
