from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


MODULE_PATH = Path(__file__).resolve().parents[1] / ".harbor" / "mew_terminal_bench_agent.py"


def load_agent_module():
    spec = importlib.util.spec_from_file_location("mew_terminal_bench_agent", MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeEnvironment:
    def __init__(self, result):
        self.result = result
        self.commands = []
        self.timeouts = []

    def exec_as_agent(self, command, timeout=None):
        self.commands.append(command)
        self.timeouts.append(timeout)
        return self.result


class SeamAgentMixin:
    def __init__(self, *args, **kwargs):
        self.installed_with = None
        self.seam_calls = []
        super().__init__(*args, **kwargs)

    async def install(self, environment):
        self.installed_with = environment

    async def _exec_as_agent(self, environment, command, timeout=None):
        self.seam_calls.append((environment, command, timeout))
        return environment.exec_as_agent(command, timeout=timeout)


def test_agent_imports_without_harbor_installed():
    module = load_agent_module()
    assert module.MewTerminalBenchAgent.__name__ == "MewTerminalBenchAgent"


def test_async_install_and_run_record_required_artifact_contract(tmp_path):
    module = load_agent_module()

    class Agent(SeamAgentMixin, module.MewTerminalBenchAgent):
        pass

    report_path = tmp_path / "artifacts" / "task-1" / "mew-report.json"
    command_template = (
        "mew-smoke --instruction {instruction_shell} "
        "--report {report_path} --artifacts {artifact_dir}"
    )
    agent = Agent(
        command_template=command_template,
        artifact_root=tmp_path / "artifacts",
        timeout_seconds=17,
    )
    environment = FakeEnvironment(
        SimpleNamespace(
            exit_code=0,
            stdout="mew stdout",
            stderr="mew stderr",
        )
    )
    context = SimpleNamespace(task_id="task/1")

    task_dir = tmp_path / "artifacts" / "task-1"
    task_dir.mkdir(parents=True)
    report_path.write_text(
        json.dumps(
            {
                "summary": "session summary",
                "verification": {"passed": True, "command": "pytest smoke"},
                "usage": {"input_tokens": 11, "output_tokens": 7, "cost": 0.03},
            }
        ),
        encoding="utf-8",
    )

    async def exercise():
        await agent.install(environment)
        return await agent.run("solve this task", environment, context)

    stdout = asyncio.run(exercise())

    assert stdout == "mew stdout"
    assert agent.installed_with is environment
    assert len(agent.seam_calls) == 1
    assert agent.seam_calls[0][0] is environment
    assert agent.seam_calls[0][2] == 17
    assert environment.timeouts == [17]
    assert "solve this task" in environment.commands[0]
    assert "--report" in environment.commands[0]

    instruction = json.loads((task_dir / "instruction.json").read_text(encoding="utf-8"))
    transcript = json.loads((task_dir / "command-transcript.json").read_text(encoding="utf-8"))
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert instruction["instruction"] == "solve this task"
    assert transcript["stdout"] == "mew stdout"
    assert transcript["stderr"] == "mew stderr"
    assert transcript["exit_code"] == 0
    assert transcript["timed_out"] is False
    assert transcript["timeout_seconds"] == 17
    assert summary["work_session_or_report_summary"] == "session summary"
    assert summary["verifier_result"] == {"passed": True, "command": "pytest smoke"}
    assert summary["timeout_status"] == {"timed_out": False, "timeout_seconds": 17}
    assert summary["cost_token_metadata"] == {
        "input_tokens": 11,
        "output_tokens": 7,
        "cost": 0.03,
    }
    assert context.mew_terminal_bench_artifact_dir == str(task_dir)
    assert context.mew_terminal_bench_summary == summary


def test_missing_optional_metadata_is_unavailable_and_context_dict_supported(tmp_path):
    module = load_agent_module()
    agent = module.MewTerminalBenchAgent(
        command_template="mew-smoke {instruction_shell}",
        artifact_root=tmp_path,
        timeout_seconds=5,
    )
    environment = FakeEnvironment((2, "out", "err", True))
    context = {"task_id": "plain-task"}

    stdout = asyncio.run(agent.run("instruction", environment, context))

    task_dir = tmp_path / "plain-task"
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    transcript = json.loads((task_dir / "command-transcript.json").read_text(encoding="utf-8"))

    assert stdout == "out"
    assert transcript["stderr"] == "err"
    assert transcript["exit_code"] == 2
    assert summary["work_session_or_report_summary"] == "unavailable"
    assert summary["verifier_result"] == "unavailable"
    assert summary["timeout_status"] == {"timed_out": True, "timeout_seconds": 5}
    assert summary["cost_token_metadata"] == "unavailable"
    assert context["mew_terminal_bench_artifact_dir"] == str(task_dir)
    assert context["mew_terminal_bench_summary"] == summary


def test_exec_as_agent_retries_base_helper_without_timeout_keyword(tmp_path, monkeypatch):
    module = load_agent_module()
    calls = []

    async def fake_exec_as_agent(self, environment, *, command, **kwargs):
        calls.append((environment, command, kwargs))
        if "timeout" in kwargs:
            raise TypeError("unexpected keyword argument 'timeout'")
        return SimpleNamespace(exit_code=0, stdout="retry stdout", stderr="retry stderr")

    monkeypatch.setattr(module.BaseInstalledAgent, "exec_as_agent", fake_exec_as_agent, raising=False)
    agent = module.MewTerminalBenchAgent(
        command_template="mew-smoke {instruction_shell}",
        artifact_root=tmp_path,
        timeout_seconds=5,
    )
    environment = object()
    context = SimpleNamespace(task_id="retry-task")

    stdout = asyncio.run(agent.run("instruction with spaces", environment, context))

    task_dir = tmp_path / "retry-task"
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))
    transcript = json.loads((task_dir / "command-transcript.json").read_text(encoding="utf-8"))

    assert stdout == "retry stdout"
    assert len(calls) == 2
    assert calls[0][0] is environment
    assert calls[0][2] == {"timeout": 5}
    assert calls[1][0] is environment
    assert calls[1][1] == calls[0][1]
    assert calls[1][2] == {}
    assert "instruction with spaces" in calls[1][1]
    assert transcript["stdout"] == "retry stdout"
    assert transcript["stderr"] == "retry stderr"
    assert summary["timeout_status"] == {"timed_out": False, "timeout_seconds": 5}
    assert context.mew_terminal_bench_artifact_dir == str(task_dir)
    assert context.mew_terminal_bench_summary == summary
