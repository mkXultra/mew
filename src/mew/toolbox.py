from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .tasks import clip_output
from .timeutil import now_iso


_SHELL_WRAPPER_RE = re.compile(r"^(?P<env>(?:[A-Za-z_][A-Za-z0-9_]*=\S+\s+)*)?(?P<shell>\S+)\s+(?P<flag>-[lc]{1,2})\s+(?P<script>.*)\Z", re.DOTALL)
COMMAND_OUTPUT_SPOOL_MAX_BYTES = 1_000_000
COMMAND_OUTPUT_TAIL_MAX_CHARS = 65_536


def resolve_tool_cwd(cwd=None):
    path = Path(cwd or ".").expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"tool cwd does not exist: {resolved}")
    return resolved


def _split_shell_wrapper_literal(command):
    text = str(command or "").strip()
    match = _SHELL_WRAPPER_RE.match(text)
    if not match:
        return None
    shell = match.group("shell")
    executable = Path(shell).name
    if executable not in {"bash", "sh", "zsh"}:
        return None
    flag = match.group("flag")
    if flag not in {"-c", "-lc", "-cl"}:
        return None
    script = (match.group("script") or "").strip()
    if len(script) >= 2 and script[0] == script[-1] and script[0] in {"'", '"'}:
        script = script[1:-1]
    if not script:
        return None
    env_overrides = {}
    env_text = (match.group("env") or "").strip()
    if env_text:
        try:
            env_parts = shlex.split(env_text)
        except ValueError:
            return None
        for part in env_parts:
            if "=" not in part:
                return None
            key, value = part.split("=", 1)
            if not key.replace("_", "").isalnum() or key[:1].isdigit():
                return None
            env_overrides[key] = value
    return [shell, flag, script], env_overrides


def split_command_env(command):
    try:
        parts = shlex.split(command or "")
    except ValueError:
        shell_wrapper = _split_shell_wrapper_literal(command)
        if shell_wrapper is None:
            raise
        return shell_wrapper
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


def _can_kill_process_group():
    return os.name == "posix" and hasattr(os, "killpg")


def _popen_process_group_kwargs(kill_process_group=False):
    if kill_process_group and _can_kill_process_group():
        return {"start_new_session": True}
    return {}


def _terminate_process(process, *, kill_process_group=False, grace_seconds=2):
    if process.poll() is not None:
        return "already_exited"
    if kill_process_group and _can_kill_process_group():
        return _terminate_process_group(process, grace_seconds=grace_seconds)
    try:
        process.terminate()
    except OSError:
        return "kill_failed"
    try:
        process.wait(timeout=grace_seconds)
        return "terminated"
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
    except OSError:
        return "kill_failed"
    try:
        process.wait(timeout=grace_seconds)
        return "killed_after_grace"
    except subprocess.TimeoutExpired:
        return "kill_failed"


def _terminate_process_group(process, *, grace_seconds=2):
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return "kill_failed"
    try:
        process.wait(timeout=grace_seconds)
        return "process_group_terminated"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            return "kill_failed"
    try:
        process.wait(timeout=grace_seconds)
        return "process_group_killed_after_grace"
    except subprocess.TimeoutExpired:
        return "kill_failed"


def _tail_output(text, max_chars=2000, max_lines=20):
    if not text:
        return ""
    lines = text.splitlines()
    if len(lines) > max_lines:
        text = "\n".join(lines[-max_lines:])
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def _default_shell_argv(command):
    shell = os.environ.get("SHELL") or ""
    candidates = [shell, "/bin/bash", "/bin/sh"]
    for candidate in candidates:
        if not candidate:
            continue
        executable = Path(candidate).name
        if executable not in {"bash", "sh", "zsh"}:
            continue
        if Path(candidate).is_absolute() and not Path(candidate).exists():
            continue
        return [candidate, "-lc", command]
    return ["sh", "-lc", command]


def _subprocess_env(extra_env=None):
    env = {**os.environ, **(extra_env or {})}
    if sys.platform == "darwin":
        env.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")
    return env


def run_command_record(command, cwd=None, timeout=300, extra_env=None, kill_process_group=False, use_shell=False):
    if use_shell:
        argv = _default_shell_argv(command or "")
        env_overrides = {}
    else:
        argv, env_overrides = split_command_env(command)
    if not argv or (use_shell and not str(command or "").strip()):
        raise ValueError("command is empty")

    resolved_cwd = resolve_tool_cwd(cwd)
    started_at = now_iso()
    execution_mode = "shell" if use_shell else "argv"
    try:
        shell_guard_env = {"MEW_WORK_COMMAND_GUARD": "1"} if use_shell else {}
        env = _subprocess_env({**env_overrides, **shell_guard_env, **(extra_env or {})})
        if kill_process_group:
            process = subprocess.Popen(
                argv,
                cwd=str(resolved_cwd),
                text=True,
                encoding="utf-8",
                errors="replace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                shell=False,
                env=env,
                **_popen_process_group_kwargs(kill_process_group=True),
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                kill_status = _terminate_process(process, kill_process_group=True)
                stdout, stderr = process.communicate()
                stdout = stdout if isinstance(stdout, str) else (exc.stdout if isinstance(exc.stdout, str) else "")
                stderr = stderr if isinstance(stderr, str) else (exc.stderr if isinstance(exc.stderr, str) else "")
                return {
                    "command": command,
                    "argv": argv,
                    "execution_mode": execution_mode,
                    "cwd": str(resolved_cwd),
                    "started_at": started_at,
                    "finished_at": now_iso(),
                    "exit_code": None,
                    "timed_out": True,
                    "stdout": clip_output(stdout),
                    "stderr": clip_output(stderr or f"command timed out after {timeout} second(s)"),
                    "kill_status": kill_status,
                }
            return {
                "command": command,
                "argv": argv,
                "execution_mode": execution_mode,
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
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            shell=False,
            env=env,
        )
        return {
            "command": command,
            "argv": argv,
            "execution_mode": execution_mode,
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
            "execution_mode": execution_mode,
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
            "execution_mode": execution_mode,
            "cwd": str(resolved_cwd),
            "started_at": started_at,
            "finished_at": now_iso(),
            "exit_code": None,
            "error_type": "executable_not_found" if isinstance(exc, FileNotFoundError) else exc.__class__.__name__,
            "stdout": "",
            "stderr": stderr,
        }


def run_command_record_streaming(
    command,
    cwd=None,
    timeout=300,
    extra_env=None,
    on_output=None,
    use_shell=False,
    kill_process_group=False,
):
    if use_shell:
        argv = _default_shell_argv(command or "")
        env_overrides = {}
    else:
        argv, env_overrides = split_command_env(command)
    if not argv or (use_shell and not str(command or "").strip()):
        raise ValueError("command is empty")

    resolved_cwd = resolve_tool_cwd(cwd)
    started_at = now_iso()
    started_monotonic = time.monotonic()
    execution_mode = "shell" if use_shell else "argv"
    shell_guard_env = {"MEW_WORK_COMMAND_GUARD": "1"} if use_shell else {}
    env = _subprocess_env({**env_overrides, **shell_guard_env, **(extra_env or {})})
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(resolved_cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=1,
            shell=False,
            env=env,
            **_popen_process_group_kwargs(kill_process_group=kill_process_group),
        )
    except OSError as exc:
        stderr = f"executable not found: {argv[0]}" if isinstance(exc, FileNotFoundError) and argv else str(exc)
        return {
            "command": command,
            "argv": argv,
            "execution_mode": execution_mode,
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
        kill_status = _terminate_process(process, kill_process_group=kill_process_group)
        exit_code = None

    for thread in threads:
        thread.join(timeout=1)

    stdout = "".join(chunks["stdout"])
    stderr = "".join(chunks["stderr"])
    finished_at = now_iso()
    duration_seconds = max(0.0, time.monotonic() - started_monotonic)
    stdout_tail = _tail_output(stdout)
    stderr_tail = _tail_output(stderr)
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
        "execution_mode": execution_mode,
        "cwd": str(resolved_cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_seconds, 3),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "stdout": clip_output(stdout),
        "stderr": clip_output(stderr),
        "kill_status": kill_status,
        "stdout_tail": stdout_tail,
        "stderr_tail": stderr_tail,
        "timeout_seconds": timeout if timed_out else None,
    }


@dataclass
class ManagedCommandHandle:
    command: str
    argv: list[str]
    execution_mode: str
    cwd: str
    command_run_id: str
    output_ref: str
    output_path: str
    started_at: str
    started_monotonic: float
    timeout: float
    process: subprocess.Popen
    kill_process_group: bool = False
    chunks: dict[str, list[str]] = field(default_factory=lambda: {"stdout": [], "stderr": []})
    threads: list[threading.Thread] = field(default_factory=list)
    finalized: bool = False
    final_result: dict | None = None
    output_bytes: int = 0
    output_truncated: bool = False
    output_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def pid(self):
        return self.process.pid

    @property
    def process_group_id(self):
        return self.process.pid if self.kill_process_group else None

    def snapshot(self, *, status="running"):
        stdout = "".join(self.chunks["stdout"])
        stderr = "".join(self.chunks["stderr"])
        duration_seconds = max(0.0, time.monotonic() - self.started_monotonic)
        return {
            "command": self.command,
            "argv": self.argv,
            "execution_mode": self.execution_mode,
            "cwd": self.cwd,
            "command_run_id": self.command_run_id,
            "output_ref": self.output_ref,
            "output_path": self.output_path,
            "started_at": self.started_at,
            "finished_at": None,
            "duration_seconds": round(duration_seconds, 3),
            "status": status,
            "pid": self.pid,
            "process_group_id": self.process_group_id,
            "exit_code": None,
            "timed_out": False,
            "stdout": clip_output(stdout),
            "stderr": clip_output(stderr),
            "stdout_tail": _tail_output(stdout),
            "stderr_tail": _tail_output(stderr),
            "output_bytes": self.output_bytes,
            "output_truncated": self.output_truncated,
        }

    def is_running(self):
        return self.process.poll() is None

    def poll(self, wait_seconds=0):
        if self.finalized and self.final_result is not None:
            return dict(self.final_result)
        wait = max(0.0, float(wait_seconds or 0))
        remaining_timeout = self.timeout - max(0.0, time.monotonic() - self.started_monotonic)
        if remaining_timeout <= 0:
            return self.finalize(timeout=0)
        wait = min(wait, remaining_timeout)
        if wait:
            try:
                self.process.wait(timeout=wait)
            except subprocess.TimeoutExpired:
                pass
        if time.monotonic() - self.started_monotonic >= self.timeout and self.process.poll() is None:
            return self.finalize(timeout=0)
        if self.process.poll() is None:
            return self.snapshot(status="running")
        return self.finalize(timeout=0)

    def finalize(self, timeout=None):
        if self.finalized and self.final_result is not None:
            return dict(self.final_result)
        timed_out = False
        kill_status = ""
        try:
            exit_code = self.process.wait(timeout=self.timeout if timeout is None else timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_status = _terminate_process(self.process, kill_process_group=self.kill_process_group)
            exit_code = None
        for thread in self.threads:
            thread.join(timeout=1)
        stdout = "".join(self.chunks["stdout"])
        stderr = "".join(self.chunks["stderr"])
        finished_at = now_iso()
        duration_seconds = max(0.0, time.monotonic() - self.started_monotonic)
        if timed_out:
            timeout_seconds = self.timeout if timeout is None else timeout
            timeout_message = f"command timed out after {timeout_seconds} second(s)"
            if stderr and not stderr.endswith("\n"):
                stderr += "\n"
            stderr += timeout_message
        result = {
            "command": self.command,
            "argv": self.argv,
            "execution_mode": self.execution_mode,
            "cwd": self.cwd,
            "command_run_id": self.command_run_id,
            "output_ref": self.output_ref,
            "output_path": self.output_path,
            "started_at": self.started_at,
            "finished_at": finished_at,
            "duration_seconds": round(duration_seconds, 3),
            "status": "timed_out" if timed_out else ("completed" if exit_code == 0 else "failed"),
            "exit_code": exit_code,
            "timed_out": timed_out,
            "stdout": clip_output(stdout),
            "stderr": clip_output(stderr),
            "kill_status": kill_status,
            "stdout_tail": _tail_output(stdout),
            "stderr_tail": _tail_output(stderr),
            "timeout_seconds": (self.timeout if timeout is None else timeout) if timed_out else None,
            "output_bytes": self.output_bytes,
            "output_truncated": self.output_truncated,
        }
        self.finalized = True
        self.final_result = result
        return dict(result)

    def append_output(self, stream_name, chunk):
        if not chunk:
            return
        self.chunks[stream_name].append(chunk)
        current = "".join(self.chunks[stream_name])
        if len(current) > COMMAND_OUTPUT_TAIL_MAX_CHARS:
            self.chunks[stream_name] = [current[-COMMAND_OUTPUT_TAIL_MAX_CHARS:]]
        if not self.output_path:
            return
        encoded = chunk.encode("utf-8", errors="replace")
        with self.output_lock:
            if self.output_bytes + len(encoded) > COMMAND_OUTPUT_SPOOL_MAX_BYTES:
                self.output_truncated = True
                remaining = max(0, COMMAND_OUTPUT_SPOOL_MAX_BYTES - self.output_bytes)
                if remaining <= 0:
                    self.output_bytes += len(encoded)
                    return
                chunk_to_write = encoded[:remaining].decode("utf-8", errors="replace")
                self.output_truncated = True
            else:
                chunk_to_write = chunk
            try:
                path = Path(self.output_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8", errors="replace") as handle:
                    handle.write(chunk_to_write)
            except OSError:
                self.output_truncated = True
            finally:
                self.output_bytes += len(encoded)


class ManagedCommandRunner:
    """Bounded managed command registry used by the work loop."""

    def __init__(self, *, max_active=1):
        self.max_active = max(1, int(max_active or 1))
        self.active: ManagedCommandHandle | None = None
        self.handles: dict[str, ManagedCommandHandle] = {}

    def _running_handles(self):
        return [handle for handle in self.handles.values() if handle.is_running()]

    def _handle_key(self, command_run_id=""):
        key = str(command_run_id or "").strip()
        if key:
            return key
        if self.active is not None:
            return self.active.command_run_id
        if len(self.handles) == 1:
            return next(iter(self.handles))
        return ""

    def _get_handle(self, command_run_id=""):
        key = self._handle_key(command_run_id)
        if not key or key not in self.handles:
            raise RuntimeError("no managed command is active")
        return key, self.handles[key]

    def _drop_finalized(self, key, handle):
        if handle.finalized:
            self.handles.pop(key, None)
            if self.active is handle:
                self.active = next(iter(self.handles.values()), None)

    def start(
        self,
        command,
        cwd=None,
        timeout=300,
        extra_env=None,
        on_output=None,
        use_shell=False,
        kill_process_group=False,
        command_run_id="",
        output_ref="",
        output_path="",
    ):
        if len(self._running_handles()) >= self.max_active:
            raise RuntimeError("a managed command is already running")
        if use_shell:
            argv = _default_shell_argv(command or "")
            env_overrides = {}
        else:
            argv, env_overrides = split_command_env(command)
        if not argv or (use_shell and not str(command or "").strip()):
            raise ValueError("command is empty")

        resolved_cwd = resolve_tool_cwd(cwd)
        started_at = now_iso()
        execution_mode = "shell" if use_shell else "argv"
        shell_guard_env = {"MEW_WORK_COMMAND_GUARD": "1"} if use_shell else {}
        env = _subprocess_env({**env_overrides, **shell_guard_env, **(extra_env or {})})
        process = subprocess.Popen(
            argv,
            cwd=str(resolved_cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            bufsize=1,
            shell=False,
            env=env,
            **_popen_process_group_kwargs(kill_process_group=kill_process_group),
        )
        handle = ManagedCommandHandle(
            command=command,
            argv=argv,
            execution_mode=execution_mode,
            cwd=str(resolved_cwd),
            command_run_id=str(command_run_id or ""),
            output_ref=str(output_ref or ""),
            output_path=str(output_path or ""),
            started_at=started_at,
            started_monotonic=time.monotonic(),
            timeout=float(timeout),
            process=process,
            kill_process_group=kill_process_group,
        )
        if not handle.command_run_id:
            handle.command_run_id = f"pid:{process.pid}"

        def read_stream(name, stream):
            if stream is None:
                return
            for chunk in iter(stream.readline, ""):
                handle.append_output(name, chunk)
                if on_output:
                    on_output(name, chunk)
            stream.close()

        handle.threads = [
            threading.Thread(target=read_stream, args=("stdout", process.stdout), daemon=True),
            threading.Thread(target=read_stream, args=("stderr", process.stderr), daemon=True),
        ]
        for thread in handle.threads:
            thread.start()
        self.active = handle
        self.handles[handle.command_run_id] = handle
        return handle

    def poll(self, wait_seconds=0, command_run_id=""):
        key, handle = self._get_handle(command_run_id)
        result = handle.poll(wait_seconds=wait_seconds)
        self._drop_finalized(key, handle)
        return result

    def finalize(self, timeout=None, command_run_id=""):
        key, handle = self._get_handle(command_run_id)
        result = handle.finalize(timeout=timeout)
        self.handles.pop(key, None)
        if self.active is handle:
            self.active = next(iter(self.handles.values()), None)
        return result

    def cancel(self, reason="cancelled", command_run_id=""):
        try:
            key, handle = self._get_handle(command_run_id)
        except RuntimeError:
            return {
                "status": "orphaned",
                "kill_status": "",
                "exit_code": None,
                "reason": str(reason or "cancelled"),
            }
        kill_status = _terminate_process(handle.process, kill_process_group=handle.kill_process_group)
        for thread in handle.threads:
            thread.join(timeout=1)
        result = {
            **handle.snapshot(status="killed"),
            "finished_at": now_iso(),
            "timed_out": False,
            "exit_code": None,
            "kill_status": kill_status,
            "reason": str(reason or "cancelled"),
        }
        handle.finalized = True
        handle.final_result = result
        self.handles.pop(key, None)
        if self.active is handle:
            self.active = next(iter(self.handles.values()), None)
        return result


def validate_git_ref(ref):
    if not ref:
        return ""
    if ref.startswith("-"):
        raise ValueError("git ref must not start with '-'")
    if any(char.isspace() for char in ref):
        raise ValueError("git ref must not contain whitespace")
    return ref


def run_git_tool(action, cwd=None, limit=20, staged=False, stat=False, base="", pathspec=""):
    resolved_cwd = resolve_tool_cwd(cwd)
    pathspec = str(pathspec or "").strip()
    if action == "status":
        command = "git status --short"
        if pathspec:
            command += f" -- {shlex.quote(pathspec)}"
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
        if pathspec:
            parts.append(shlex.quote(pathspec))
        command = " ".join(parts)
    elif action == "log":
        safe_limit = max(1, min(int(limit), 100))
        command = f"git log --oneline -n {safe_limit}"
        if pathspec:
            command += f" -- {shlex.quote(pathspec)}"
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
