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


def _resident_loop_python_module_args(parts):
    index = 1
    while index < len(parts):
        token = parts[index]
        if token == "-m" and index + 1 < len(parts):
            if parts[index + 1] == "mew":
                return parts[index + 2 :]
            return []
        if token in {"-c", "-"}:
            return []
        if not token.startswith("-"):
            return []
        if token in {"-W", "-X"} and index + 1 < len(parts):
            index += 2
            continue
        index += 1
    return []


def _resident_loop_unwrap_command(parts):
    parts = list(parts or [])
    while parts:
        executable = Path(parts[0]).name
        if executable == "env":
            index = 1
            split_string_parts = None
            while index < len(parts):
                token = parts[index]
                if token == "--":
                    index += 1
                    break
                if token in {"-i", "--ignore-environment", "-0", "--null"}:
                    index += 1
                    continue
                if token in {"-u", "--unset", "-C", "--chdir"}:
                    index += 2
                    continue
                if token.startswith("-u") and token != "-u":
                    index += 1
                    continue
                if token.startswith("-C") and token != "-C":
                    index += 1
                    continue
                if token.startswith("--unset=") or token.startswith("--chdir="):
                    index += 1
                    continue
                if token in {"-S", "--split-string"} and index + 1 < len(parts):
                    try:
                        split_string_parts = shlex.split(parts[index + 1] or "")
                    except ValueError:
                        return []
                    index += 2
                    break
                if token.startswith("-S") and token != "-S":
                    try:
                        split_string_parts = shlex.split(token[2:] or "")
                    except ValueError:
                        return []
                    index += 1
                    break
                if token.startswith("--split-string="):
                    try:
                        split_string_parts = shlex.split(token.split("=", 1)[1] or "")
                    except ValueError:
                        return []
                    index += 1
                    break
                if "=" in token and not token.startswith("-"):
                    index += 1
                    continue
                break
            if split_string_parts is not None:
                parts = split_string_parts + parts[index:]
                continue
            parts = parts[index:]
            continue
        if executable == "uv" and len(parts) >= 2 and parts[1] == "run":
            index = 2
            while index < len(parts) and parts[index].startswith("-"):
                token = parts[index]
                index += 1
                if token in {
                    "--with",
                    "--python",
                    "--project",
                    "--directory",
                    "--env-file",
                    "--index",
                    "--default-index",
                    "--extra-index-url",
                    "--find-links",
                } and index < len(parts):
                    index += 1
            parts = parts[index:]
            continue
        break
    return parts


def is_resident_mew_loop_command(command):
    try:
        parts, _ = split_command_env(command or "")
    except ValueError:
        return False
    parts = _resident_loop_unwrap_command(parts)
    if not parts:
        return False
    executable = Path(parts[0]).name
    if executable == "mew":
        trailing = parts[1:]
    elif executable.startswith("python"):
        trailing = _resident_loop_python_module_args(parts)
    else:
        return False
    if not trailing:
        return False
    subcommand = trailing[0]
    if subcommand in {"attach", "chat", "do", "run", "session"}:
        return True
    if subcommand == "work":
        trailing = trailing[1:]
        if "--ai" in trailing or "--live" in trailing:
            return True
    return False


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


def _tail_output(text, max_chars=2000, max_lines=20):
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        text = "\n".join(lines[-max_lines:])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


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
                stdin=subprocess.DEVNULL,
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
            stdin=subprocess.DEVNULL,
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
            stdin=subprocess.DEVNULL,
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
    kill_status = ""
    try:
        exit_code = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            process.terminate()
            kill_status = "terminated"
        except OSError:
            kill_status = "kill_failed"
        if kill_status != "kill_failed":
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                    kill_status = "killed_after_grace"
                except OSError:
                    kill_status = "kill_failed"
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    kill_status = "kill_failed"
        exit_code = None

    for thread in threads:
        thread.join(timeout=1)

    stdout = "".join(chunks["stdout"])
    stderr = "".join(chunks["stderr"])
    stdout_tail = _tail_output(stdout) if timed_out else ""
    stderr_tail = _tail_output(stderr) if timed_out else ""
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
        "kill_status": kill_status,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "timeout_seconds": timeout if timed_out else None,
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
