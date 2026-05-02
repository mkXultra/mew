from __future__ import annotations

import inspect
import json
import shlex
from pathlib import Path
from types import SimpleNamespace
from typing import Any

try:  # Harbor is not installed in local unit tests.
    from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template
except Exception:  # pragma: no cover - exercised by import-without-Harbor tests.
    def with_prompt_template(func: Any) -> Any:
        return func

    class BaseInstalledAgent:  # type: ignore[no-redef]
        def __init__(self, logs_dir: str | Path | None = None, model_name: str | None = None, **kwargs: Any) -> None:
            self.logs_dir = logs_dir
            self.model_name = model_name
            self.extra_env = kwargs.pop("extra_env", None)
            self.prompt_template_path = kwargs.pop("prompt_template_path", None)
            self._version = kwargs.pop("version", "local")
            self._base_agent_kwargs = kwargs

        @staticmethod
        def version() -> str:
            return "local"

        async def install(self, environment: Any) -> None:
            return None

        async def exec_as_agent(
            self,
            environment: Any,
            command: str,
            env: dict[str, str] | None = None,
            cwd: str | Path | None = None,
            timeout_sec: int | None = None,
        ) -> Any:
            try:
                return environment.exec_as_agent(command, env=env, cwd=cwd, timeout_sec=timeout_sec)
            except TypeError:
                return environment.exec_as_agent(command, timeout=timeout_sec)


class MewTerminalBenchAgent(BaseInstalledAgent):
    """Minimal Harbor custom agent for Terminal-Bench smoke compatibility.

    Import with:
        --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent

    The wrapper intentionally records comparable artifacts only. Score-driven
    prompt/tool debugging belongs to the next milestone.
    """

    @staticmethod
    def name() -> str:
        return "mew"

    def __init__(
        self,
        logs_dir: str | Path | None = None,
        model_name: str | None = None,
        *,
        command_template: str = "mew-smoke --instruction {instruction_shell} --report {report_path} --artifacts {artifact_dir}",
        command_cwd: str | Path | None = None,
        artifact_root: str | Path | None = None,
        timeout_seconds: int | str | None = None,
        timeout_reserve_seconds: int | str | None = 60,
        install_command: str | None = None,
        install_env: dict[str, str] | None = None,
        capture_nonzero_command_exit: bool = True,
        container_repo_root: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        base_kwargs: dict[str, Any] = {}
        if logs_dir is not None:
            base_kwargs["logs_dir"] = logs_dir
        if model_name is not None:
            base_kwargs["model_name"] = model_name
        for name in ("extra_env", "version", "prompt_template_path"):
            if name in kwargs:
                base_kwargs[name] = kwargs.pop(name)

        super().__init__(**base_kwargs)
        if not hasattr(self, "logs_dir"):
            self.logs_dir = logs_dir
        if not hasattr(self, "model_name"):
            self.model_name = model_name
        self._harbor_base_kwargs = dict(base_kwargs)
        self._extra_agent_kwargs = dict(kwargs)
        self.command_template = command_template
        self.command_cwd = str(command_cwd) if command_cwd is not None else None
        resolved_logs_dir = getattr(self, "logs_dir", logs_dir)
        if artifact_root is None:
            if resolved_logs_dir is not None:
                artifact_root = Path(resolved_logs_dir) / "terminal-bench-harbor-smoke"
            else:
                artifact_root = Path("artifacts/terminal-bench-harbor-smoke")
        self.artifact_root = Path(artifact_root)
        self.timeout_seconds = self._parse_timeout_seconds(timeout_seconds)
        self.timeout_reserve_seconds = self._parse_timeout_seconds(timeout_reserve_seconds)
        self.install_command = install_command
        self.install_env = install_env
        self.capture_nonzero_command_exit = capture_nonzero_command_exit
        self.container_repo_root = str(container_repo_root) if container_repo_root is not None else None
        self._last_task_dir: Path | None = None
        self._last_summary: dict[str, Any] | None = None

    async def install(self, environment: Any) -> None:
        parent_install = getattr(super(), "install", None)
        if parent_install is not None:
            result = parent_install(environment)
            if inspect.isawaitable(result):
                await result
        if self.install_command:
            await self._exec_as_agent(environment, self.install_command, env=self.install_env, timeout_sec=None)
        return None

    @with_prompt_template
    async def run(self, instruction: str, environment: Any, context: Any) -> str:
        task_dir = self._task_dir(context)
        task_dir.mkdir(parents=True, exist_ok=True)
        report_path = task_dir / "mew-report.json"
        command_task_dir = self._container_visible_task_dir(task_dir)
        command_report_path = command_task_dir / "mew-report.json"
        command_instruction_path = command_task_dir / "instruction.json"

        self._write_json(
            task_dir / "instruction.json",
            {
                "task_id": self._context_get(context, "task_id"),
                "instruction": instruction,
            },
        )

        mew_max_wall_seconds = self._mew_max_wall_seconds()
        command = self.command_template.format(
            instruction=instruction,
            instruction_shell=shlex.quote(instruction),
            artifact_dir=shlex.quote(str(command_task_dir)),
            report_path=shlex.quote(str(command_report_path)),
            instruction_json=shlex.quote(str(command_instruction_path)),
            host_artifact_dir=shlex.quote(str(task_dir)),
            host_report_path=shlex.quote(str(report_path)),
            host_instruction_json=shlex.quote(str(task_dir / "instruction.json")),
            command_cwd=self.command_cwd or "",
            command_cwd_shell=shlex.quote(self.command_cwd or ""),
            timeout_seconds="" if self.timeout_seconds is None else str(self.timeout_seconds),
            mew_max_wall_seconds="" if mew_max_wall_seconds is None else str(mew_max_wall_seconds),
            max_wall_seconds_option=(
                ""
                if mew_max_wall_seconds is None
                else f"--max-wall-seconds {mew_max_wall_seconds}"
            ),
        )
        if self.capture_nonzero_command_exit:
            result = await self._exec_as_agent_capture(
                environment,
                command,
                cwd=self.command_cwd,
                timeout_sec=self.timeout_seconds,
            )
        else:
            result = await self._exec_as_agent(
                environment,
                command,
                cwd=self.command_cwd,
                timeout_sec=self.timeout_seconds,
            )
        exit_code, stdout, stderr, timed_out = self._normalize_result(result)

        self._write_json(
            task_dir / "command-transcript.json",
            {
                "command": command,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "timeout_seconds": self.timeout_seconds,
                "mew_max_wall_seconds": mew_max_wall_seconds,
                "timeout_reserve_seconds": self._timeout_reserve_for_shape(),
                "timeout_shape": self._timeout_shape({}),
                "cwd": self.command_cwd,
            },
        )

        self._last_task_dir = task_dir
        self.populate_context_post_run(context)
        return stdout

    def _container_visible_task_dir(self, task_dir: Path) -> Path:
        if not self.container_repo_root:
            return task_dir
        repo_root = Path.cwd().resolve(strict=False)
        try:
            relative_task_dir = task_dir.resolve(strict=False).relative_to(repo_root)
        except ValueError:
            if task_dir.is_absolute():
                return task_dir
            relative_task_dir = task_dir
        return Path(self.container_repo_root) / relative_task_dir

    async def _exec_as_agent(
        self,
        environment: Any,
        command: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        """Test seam around Harbor/BaseInstalledAgent exec_as_agent semantics."""
        helper = getattr(super(), "exec_as_agent", None)
        if helper is not None:
            result = helper(environment, command=command, env=env, cwd=cwd, timeout_sec=timeout_sec)
        else:
            result = environment.exec_as_agent(command=command, env=env, cwd=cwd, timeout_sec=timeout_sec)

        if inspect.isawaitable(result):
            return await result
        return result

    async def _exec_as_agent_capture(
        self,
        environment: Any,
        command: str,
        *,
        env: dict[str, str] | None = None,
        cwd: str | Path | None = None,
        timeout_sec: int | None = None,
    ) -> Any:
        """Run task commands while preserving nonzero exits as artifacts.

        Harbor's BaseInstalledAgent raises on nonzero command exits. That is
        right for setup failures, but too lossy for mew work attempts: a failed
        work session still needs a transcript, report, and benchmark verifier
        result so M6.20 can distinguish auth, loop, and task-quality failures.
        """
        raw_exec = getattr(environment, "exec", None)
        if raw_exec is None:
            return await self._exec_as_agent(
                environment,
                command,
                env=env,
                cwd=cwd,
                timeout_sec=timeout_sec,
            )

        merged_env = env
        extra_env = getattr(self, "_extra_env", None) or getattr(self, "extra_env", None)
        if extra_env:
            merged_env = dict(env) if env else {}
            merged_env.update(extra_env)

        try:
            result = raw_exec(
                command=f"set -o pipefail; {command}",
                user=None,
                env=merged_env,
                cwd=str(cwd) if cwd is not None else None,
                timeout_sec=timeout_sec,
            )
            if inspect.isawaitable(result):
                return await result
            return result
        except RuntimeError as exc:
            if self._is_command_timeout_exception(exc):
                return SimpleNamespace(
                    return_code=124,
                    stdout="",
                    stderr=str(exc),
                    timed_out=True,
                )
            raise

    def populate_context_post_run(self, context: Any) -> None:
        task_dir = self._last_task_dir
        if task_dir is None:
            return None

        transcript = self._read_json(task_dir / "command-transcript.json")
        report_path = task_dir / "mew-report.json"
        report = self._read_json(report_path)
        if not report:
            report = self._report_from_stdout(transcript)
        if not report:
            timeout_reason = (
                "outer_timeout_before_mew_report"
                if transcript.get("timed_out")
                else "mew_report_unavailable"
            )
            report = {
                "summary": "unavailable",
                "work_exit_code": transcript.get("exit_code"),
                "work_report": {"stop_reason": timeout_reason},
                "verification": {
                    "passed": False,
                    "reason": timeout_reason,
                },
            }
        timeout_shape = self._timeout_shape(report)
        report["timeout_shape"] = timeout_shape
        report["timeout_status"] = {
            "timed_out": transcript.get("timed_out", False),
            "timeout_seconds": transcript.get("timeout_seconds"),
        }
        self._write_json(report_path, report)
        transcript["timeout_shape"] = timeout_shape
        transcript["timeout_reserve_seconds"] = timeout_shape.get("timeout_reserve_seconds")
        self._write_json(task_dir / "command-transcript.json", transcript)
        summary = {
            "task_id": self._context_get(context, "task_id"),
            "artifact_dir": str(task_dir),
            "work_session_or_report_summary": report.get("summary", "unavailable"),
            "verifier_result": report.get("verification", "unavailable"),
            "timeout_status": {
                "timed_out": transcript.get("timed_out", False),
                "timeout_seconds": transcript.get("timeout_seconds"),
            },
            "timeout_shape": timeout_shape,
            "cost_token_metadata": report.get("usage", "unavailable"),
        }
        self._write_json(task_dir / "summary.json", summary)
        self._last_summary = summary
        self._context_set(context, "mew_terminal_bench_artifact_dir", str(task_dir))
        self._context_set(context, "mew_terminal_bench_summary", summary)
        return None

    def _task_dir(self, context: Any) -> Path:
        task_id = self._context_get(context, "task_id") or "unknown-task"
        safe_task_id = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in str(task_id)).strip("-")
        return self.artifact_root / (safe_task_id or "unknown-task")

    @staticmethod
    def _normalize_result(result: Any) -> tuple[int | None, str, str, bool]:
        if isinstance(result, tuple):
            exit_code = result[0] if len(result) > 0 else None
            stdout = result[1] if len(result) > 1 else ""
            stderr = result[2] if len(result) > 2 else ""
            timed_out = bool(result[3]) if len(result) > 3 else False
            return exit_code, str(stdout), str(stderr), timed_out
        exit_code = getattr(result, "exit_code", None)
        if exit_code is None:
            exit_code = getattr(result, "return_code", None)
        if exit_code is None:
            exit_code = getattr(result, "returncode", None)
        return (
            exit_code,
            str(getattr(result, "stdout", "")),
            str(getattr(result, "stderr", "")),
            bool(getattr(result, "timed_out", False)),
        )

    @staticmethod
    def _parse_timeout_seconds(value: int | str | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or stripped.lower() in {"none", "null", "off", "false"}:
                return None
            return int(float(stripped))
        return int(value)

    def _mew_max_wall_seconds(self) -> int | None:
        if self.timeout_seconds is None:
            return None
        timeout_seconds = max(1, int(self.timeout_seconds))
        configured_reserve = max(0, int(self.timeout_reserve_seconds or 0))
        proportional_reserve = max(1, int(timeout_seconds * 0.1))
        reserve = min(configured_reserve, proportional_reserve)
        return max(1, timeout_seconds - reserve)

    def _timeout_reserve_for_shape(self) -> int | None:
        if self.timeout_seconds is None:
            return None
        mew_max_wall_seconds = self._mew_max_wall_seconds()
        if mew_max_wall_seconds is None:
            return None
        return max(0, int(self.timeout_seconds) - int(mew_max_wall_seconds))

    def _timeout_shape(self, report: dict[str, Any]) -> dict[str, Any]:
        mew_max_wall_seconds = self._mew_max_wall_seconds()
        reserve = self._timeout_reserve_for_shape()
        latest_long_command = self._latest_long_command_from_report(report)
        return {
            "agent_timeout_seconds": self.timeout_seconds,
            "mew_max_wall_seconds": mew_max_wall_seconds,
            "timeout_reserve_seconds": reserve,
            "matched_outer_inner_timeout": bool(
                self.timeout_seconds is not None
                and mew_max_wall_seconds is not None
                and reserve is not None
                and mew_max_wall_seconds < self.timeout_seconds
            ),
            "diagnostic_timeout_shape": self.timeout_seconds is not None and mew_max_wall_seconds is not None,
            "latest_long_command_run_id": latest_long_command.get("latest_long_command_run_id"),
            "latest_long_command_status": latest_long_command.get("latest_long_command_status"),
        }

    @classmethod
    def _latest_long_command_from_report(cls, report: dict[str, Any]) -> dict[str, Any]:
        for candidate in cls._report_resume_candidates(report):
            long_build_state = candidate.get("long_build_state") if isinstance(candidate, dict) else {}
            if isinstance(long_build_state, dict) and long_build_state.get("latest_long_command_run_id"):
                return {
                    "latest_long_command_run_id": long_build_state.get("latest_long_command_run_id"),
                    "latest_long_command_status": long_build_state.get("latest_long_command_status"),
                }
        return {}

    @classmethod
    def _report_resume_candidates(cls, report: dict[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(report, dict):
            return []
        candidates: list[dict[str, Any]] = []
        for key in ("resume", "work_session_resume"):
            value = report.get(key)
            if isinstance(value, dict):
                candidates.append(value)
        for key in ("work_report", "work_session"):
            value = report.get(key)
            if isinstance(value, dict):
                resume = value.get("resume")
                if isinstance(resume, dict):
                    candidates.append(resume)
        return candidates

    @staticmethod
    def _is_command_timeout_exception(exc: RuntimeError) -> bool:
        text = str(exc).lower()
        return text.startswith("command timed out after")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _report_from_stdout(transcript: dict[str, Any]) -> dict[str, Any]:
        stdout = transcript.get("stdout", "")
        if not isinstance(stdout, str):
            return {}
        stdout = stdout.strip()
        if not stdout or stdout == "None":
            return {}

        candidates = [stdout]
        candidates.extend(line.strip() for line in reversed(stdout.splitlines()) if line.strip())
        seen = set()
        for candidate in candidates:
            if candidate in seen:
                continue
            seen.add(candidate)
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                return payload
        return {}

    @staticmethod
    def _context_get(context: Any, name: str, default: Any = None) -> Any:
        if isinstance(context, dict):
            return context.get(name, default)
        return getattr(context, name, default)

    @staticmethod
    def _context_set(context: Any, name: str, value: Any) -> None:
        if isinstance(context, dict):
            context[name] = value
            return

        metadata = getattr(context, "metadata", None)
        if isinstance(metadata, dict):
            metadata[name] = value
            return
        if hasattr(context, "metadata"):
            metadata = {}
            setattr(context, "metadata", metadata)
            metadata[name] = value
            return

        try:
            setattr(context, name, value)
        except (AttributeError, ValueError):
            metadata = getattr(context, "metadata", None)
            if metadata is None:
                metadata = {}
                setattr(context, "metadata", metadata)
            if isinstance(metadata, dict):
                metadata[name] = value
                return
            raise
