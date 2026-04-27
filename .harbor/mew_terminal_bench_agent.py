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
        async def install(self, environment: Any) -> None:
            return None

        async def exec_as_agent(self, environment: Any, command: str, timeout: int | None = None) -> Any:
            return environment.exec_as_agent(command, timeout=timeout)


class MewTerminalBenchAgent(BaseInstalledAgent):
    """Minimal Harbor custom agent for Terminal-Bench smoke compatibility.

    Import with:
        --agent-import-path mew_terminal_bench_agent:MewTerminalBenchAgent

    The wrapper intentionally records comparable artifacts only. Score-driven
    prompt/tool debugging belongs to the next milestone.
    """

    def __init__(
        self,
        *,
        command_template: str = "mew-smoke --instruction {instruction_shell} --report {report_path} --artifacts {artifact_dir}",
        artifact_root: str | Path = "artifacts/terminal-bench-harbor-smoke",
        timeout_seconds: int | None = 900,
    ) -> None:
        super().__init__()
        self.command_template = command_template
        self.artifact_root = Path(artifact_root)
        self.timeout_seconds = timeout_seconds
        self._last_task_dir: Path | None = None
        self._last_summary: dict[str, Any] | None = None

    async def install(self, environment: Any) -> None:
        parent_install = getattr(super(), "install", None)
        if parent_install is None:
            return None
        result = parent_install(environment)
        if inspect.isawaitable(result):
            await result
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
        result = await self._exec_as_agent(environment, command, timeout=self.timeout_seconds)
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

    async def _exec_as_agent(self, environment: Any, command: str, timeout: int | None = None) -> Any:
        """Test seam around Harbor/BaseInstalledAgent exec_as_agent semantics."""
        helper = getattr(super(), "exec_as_agent", None)

        async def invoke(*, include_timeout: bool) -> Any:
            if helper is not None:
                if include_timeout:
                    result = helper(environment, command=command, timeout=timeout)
                else:
                    result = helper(environment, command=command)
            elif include_timeout:
                result = environment.exec_as_agent(command=command, timeout=timeout)
            else:
                result = environment.exec_as_agent(command=command)

            if inspect.isawaitable(result):
                return await result
            return result

        try:
            return await invoke(include_timeout=True)
        except TypeError:
            if timeout is None:
                raise
            return await invoke(include_timeout=False)

    def populate_context_post_run(self, context: Any) -> None:
        task_dir = self._last_task_dir
        if task_dir is None:
            return None

        transcript = self._read_json(task_dir / "command-transcript.json")
        report = self._read_json(task_dir / "mew-report.json")
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
        return (
            getattr(result, "exit_code", getattr(result, "returncode", None)),
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
    def _context_get(context: Any, name: str, default: Any = None) -> Any:
        if isinstance(context, dict):
            return context.get(name, default)
        return getattr(context, name, default)

    @staticmethod
    def _context_set(context: Any, name: str, value: Any) -> None:
        if isinstance(context, dict):
            context[name] = value
        else:
            setattr(context, name, value)
