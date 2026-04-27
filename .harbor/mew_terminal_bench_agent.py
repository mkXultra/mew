from __future__ import annotations

import inspect
import json
import shlex
from pathlib import Path
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
        artifact_root: str | Path | None = None,
        timeout_seconds: int | None = 900,
        install_command: str | None = None,
        install_env: dict[str, str] | None = None,
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
        resolved_logs_dir = getattr(self, "logs_dir", logs_dir)
        if artifact_root is None:
            if resolved_logs_dir is not None:
                artifact_root = Path(resolved_logs_dir) / "terminal-bench-harbor-smoke"
            else:
                artifact_root = Path("artifacts/terminal-bench-harbor-smoke")
        self.artifact_root = Path(artifact_root)
        self.timeout_seconds = timeout_seconds
        self.install_command = install_command
        self.install_env = install_env
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

        self._write_json(
            task_dir / "instruction.json",
            {
                "task_id": self._context_get(context, "task_id"),
                "instruction": instruction,
            },
        )

        command = self.command_template.format(
            instruction=instruction,
            instruction_shell=shlex.quote(instruction),
            artifact_dir=shlex.quote(str(task_dir)),
            report_path=shlex.quote(str(report_path)),
            instruction_json=shlex.quote(str(task_dir / "instruction.json")),
        )
        result = await self._exec_as_agent(environment, command, timeout_sec=self.timeout_seconds)
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
            },
        )

        self._last_task_dir = task_dir
        self.populate_context_post_run(context)
        return stdout

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

    def populate_context_post_run(self, context: Any) -> None:
        task_dir = self._last_task_dir
        if task_dir is None:
            return None

        transcript = self._read_json(task_dir / "command-transcript.json")
        report_path = task_dir / "mew-report.json"
        report = self._read_json(report_path)
        if not report:
            report = self._report_from_stdout(transcript)
            if report:
                self._write_json(report_path, report)
        summary = {
            "task_id": self._context_get(context, "task_id"),
            "artifact_dir": str(task_dir),
            "work_session_or_report_summary": report.get("summary", "unavailable"),
            "verifier_result": report.get("verification", "unavailable"),
            "timeout_status": {
                "timed_out": transcript.get("timed_out", False),
                "timeout_seconds": transcript.get("timeout_seconds"),
            },
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
