import os
import shlex
import signal
import subprocess
import threading
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


def _terminate_process_group(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass


def run_command_record(command, cwd=None, timeout=300, extra_env=None, kill_process_group=False):
    argv, env_overrides = split_command_env(command)
    if not argv:
        raise ValueError("command is empty")

    resolved_cwd = resolve_tool_cwd(cwd)
    started_at = now_iso()
    try:
        env = {**os.environ, **env_overrides, **(extra_env or {})}
        if kill_process_group:
            process = subprocess.Popen(
                argv,
                cwd=str(resolved_cwd),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                env=env,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                _terminate_process_group(process)
                stdout, stderr = process.communicate()
                stdout = stdout if isinstance(stdout, str) else (exc.stdout if isinstance(exc.stdout, str) else "")
                stderr = stderr if isinstance(stderr, str) else (exc.stderr if isinstance(exc.stderr, str) else "")
                return {
                    "command": command,
                    "argv": argv,
                    "cwd": str(resolved_cwd),
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "exit_code": None,
                    "timed_out": True,
                    "stdout": clip_output(stdout),
                    "stderr": clip_output(stderr or f"command timed out after {timeout} second(s)"),
                }
            return {
                "command": command,
                "argv": argv,
                "cwd": str(resolved_cwd),
                "started_at": started_at,
                "finished_at": now_iso(),
                "exit_code": process.returncode,
                "stdout": clip_output(stdout),
                "stderr": clip_output(stderr),
            }
        result = subprocess.run(
            argv,
            cwd=str(resolved_cwd),
            text=True,
            capture_output=True,
            timeout=timeout,
            shell=False,
            env=env,
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
            "timed_out": True,
            "stdout": clip_output(stdout),
            "stderr": clip_output(stderr or f"command timed out after {timeout} second(s)"),
        }
    except OSError as exc:
        stderr = f"executable not found: {argv[0]}" if isinstance(exc, FileNotFoundError) and argv else str(exc)
        return {
            "command": command,
            "argv": argv,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": None,
            "error_type": "executable_not_found" if isinstance(exc, FileNotFoundError) else exc.__class__.__name__,
            "stdout": "",
            "stderr": stderr,
        }


def run_command_record_streaming(command, cwd=None, timeout=300, extra_env=None, on_output=None):
    argv, env_overrides = split_command_env(command)
    if not argv:
        raise ValueError("command is empty")

    resolved_cwd = resolve_tool_cwd(cwd)
    started_at = now_iso()
    env = {**os.environ, **env_overrides, **(extra_env or {})}
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(resolved_cwd),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1,
            shell=False,
            env=env,
        )
    except OSError as exc:
        stderr = f"executable not found: {argv[0]}" if isinstance(exc, FileNotFoundError) and argv else str(exc)
        return {
            "command": command,
            "argv": argv,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": None,
            "error_type": "executable_not_found" if isinstance(exc, FileNotFoundError) else exc.__class__.__name__,
            "stdout": "",
            "stderr": stderr,
        }

    chunks = {"stdout": [], "stderr": []}

    def read_stream(name, stream):
        if stream is None:
            return
        for chunk in iter(lambda: stream.read(1024), ""):
            chunks[name].append(chunk)
            if on_output:
                on_output(name, chunk)
        stream.close()

    threads = [
        threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
        threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
    ]
    for thread in threads:
        thread.start()

    timed_out = False
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        process.wait()
        exit_code = None

    for thread in threads:
        thread.join(timeout=1)

    stdout = "".join(chunks["stdout"])
    stderr = "".join(chunks["stderr"])
    if timed_out:
        timeout_message = f"command timed out after {timeout} second(s)"
        if stderr and not stderr.endswith("\n"):
            stderr += "\n"
        stderr += timeout_message
        if on_output:
            on_output("stderr", timeout_message + "\n")

    return {
        "command": command,
        "argv": argv,
        "cwd": str(resolved_cwd),
        "started_at": started_at,
        "finished_at": now_iso(),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": clip_output(stdout),
        "stderr": clip_output(stderr),
    }


def validate_git_ref(ref):
    if not ref:
        return ""
    if ref.startswith("-"):
        raise ValueError("git ref must not start with '-'")
    if any(char.isspace() for char in ref):
        raise ValueError("git ref must not contain whitespace")
    return ref


def run_git_tool(action, cwd=None, limit=20, staged=False, stat=False, base=""):
    resolved_cwd = resolve_tool_cwd(cwd)
    if action == "status":
        command = "git status --short"
    elif action == "diff":
        base = validate_git_ref(base)
        if staged and base:
            raise ValueError("--staged and --base cannot be combined")
        parts = ["git", "diff"]
        if base:
            parts.append(f"{base}...HEAD")
        elif staged:
            parts.append("--staged")
        if stat:
            parts.append("--stat")
        parts.append("--")
        command = " ".join(parts)
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
