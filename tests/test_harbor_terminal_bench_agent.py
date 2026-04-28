from __future__ import annotations

import asyncio
import importlib.util
import inspect
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
        self.exec_kwargs = []

    def exec_as_agent(self, command, **kwargs):
        self.commands.append(command)
        self.exec_kwargs.append(kwargs)
        return self.result


class FakeHarborEnvironment:
    def __init__(self, result):
        self.result = result
        self.commands = []
        self.exec_kwargs = []

    def exec(self, **kwargs):
        self.commands.append(kwargs["command"])
        self.exec_kwargs.append(kwargs)
        return self.result


class MetadataOnlyContext:
    def __init__(self, task_id, metadata=None):
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "metadata", metadata)

    def __setattr__(self, name, value):
        if name not in {"task_id", "metadata"}:
            raise ValueError(f"AgentContext object has no field {name}")
        object.__setattr__(self, name, value)


class SeamAgentMixin:
    def __init__(self, *args, **kwargs):
        self.installed_with = None
        self.seam_calls = []
        super().__init__(*args, **kwargs)

    async def install(self, environment):
        self.installed_with = environment
        result = super().install(environment)
        if inspect.isawaitable(result):
            await result

    async def _exec_as_agent(self, environment, command, *, env=None, cwd=None, timeout_sec=None):
        self.seam_calls.append((environment, command, {"env": env, "cwd": cwd, "timeout_sec": timeout_sec}))
        return environment.exec_as_agent(command, env=env, cwd=cwd, timeout_sec=timeout_sec)


def test_agent_imports_without_harbor_installed():
    module = load_agent_module()
    assert module.MewTerminalBenchAgent.__name__ == "MewTerminalBenchAgent"


def test_harbor_factory_kwargs_and_metadata_are_preserved(tmp_path):
    module = load_agent_module()

    agent = module.MewTerminalBenchAgent(
        logs_dir=tmp_path / "logs",
        model_name="test-model",
        extra_env={"MEW_TEST": "1"},
        version="test-version",
        prompt_template_path="prompt.txt",
        install_command="python -m pip install -e /mew",
        install_env={"PIP_DISABLE_PIP_VERSION_CHECK": "1"},
        command_cwd="/app",
        unknown_agent_kwarg="preserved",
    )

    assert module.MewTerminalBenchAgent.name() == "mew"
    assert callable(module.MewTerminalBenchAgent.name)
    assert agent.logs_dir == tmp_path / "logs"
    assert agent.artifact_root == tmp_path / "logs" / "terminal-bench-harbor-smoke"
    assert agent.model_name == "test-model"
    assert agent.extra_env == {"MEW_TEST": "1"}
    assert agent.prompt_template_path == "prompt.txt"
    assert agent._harbor_base_kwargs == {
        "logs_dir": tmp_path / "logs",
        "model_name": "test-model",
        "extra_env": {"MEW_TEST": "1"},
        "version": "test-version",
        "prompt_template_path": "prompt.txt",
    }
    assert agent._extra_agent_kwargs == {"unknown_agent_kwarg": "preserved"}
    assert agent.install_command == "python -m pip install -e /mew"
    assert agent.install_env == {"PIP_DISABLE_PIP_VERSION_CHECK": "1"}
    assert agent.command_cwd == "/app"


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
        install_command="python -m pip install -e /mew",
        install_env={"PIP_DISABLE_PIP_VERSION_CHECK": "1"},
    )
    environment = FakeEnvironment(
        SimpleNamespace(
            return_code=0,
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
    assert len(agent.seam_calls) == 2
    assert agent.seam_calls[0][0] is environment
    assert agent.seam_calls[0][1] == "python -m pip install -e /mew"
    assert agent.seam_calls[0][2] == {
        "env": {"PIP_DISABLE_PIP_VERSION_CHECK": "1"},
        "cwd": None,
        "timeout_sec": None,
    }
    assert agent.seam_calls[1][0] is environment
    assert agent.seam_calls[1][2] == {"env": None, "cwd": None, "timeout_sec": 17}
    assert environment.exec_kwargs == [
        {"env": {"PIP_DISABLE_PIP_VERSION_CHECK": "1"}, "cwd": None, "timeout_sec": None},
        {"env": None, "cwd": None, "timeout_sec": 17},
    ]
    assert "solve this task" in environment.commands[1]
    assert "--report" in environment.commands[1]

    instruction = json.loads((task_dir / "instruction.json").read_text(encoding="utf-8"))
    transcript = json.loads((task_dir / "command-transcript.json").read_text(encoding="utf-8"))
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert instruction["instruction"] == "solve this task"
    assert transcript["stdout"] == "mew stdout"
    assert transcript["stderr"] == "mew stderr"
    assert transcript["exit_code"] == 0
    assert transcript["timed_out"] is False
    assert transcript["timeout_seconds"] == 17
    assert transcript["cwd"] is None
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


def test_run_passes_configured_command_cwd_and_template_placeholder(tmp_path):
    module = load_agent_module()

    class Agent(SeamAgentMixin, module.MewTerminalBenchAgent):
        pass

    agent = Agent(
        command_template="mew work --oneshot --instruction {instruction_shell} --cwd {command_cwd_shell}",
        command_cwd="/app",
        artifact_root=tmp_path,
        timeout_seconds=19,
    )
    environment = FakeEnvironment((0, "out", "", False))
    context = SimpleNamespace(task_id="cwd-task")

    asyncio.run(agent.run("instruction", environment, context))

    assert agent.seam_calls[0][2] == {"env": None, "cwd": "/app", "timeout_sec": 19}
    assert "--cwd /app" in environment.commands[0]
    transcript = json.loads((tmp_path / "cwd-task" / "command-transcript.json").read_text(encoding="utf-8"))
    assert transcript["cwd"] == "/app"


def test_run_writes_harbor_agent_context_metadata_when_attributes_rejected(tmp_path):
    module = load_agent_module()
    agent = module.MewTerminalBenchAgent(
        command_template="mew-smoke {instruction_shell}",
        artifact_root=tmp_path,
        timeout_seconds=5,
    )
    environment = FakeEnvironment((0, "out", "", False))
    context = MetadataOnlyContext("metadata/task", metadata=None)

    stdout = asyncio.run(agent.run("instruction", environment, context))

    task_dir = tmp_path / "metadata-task"
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert stdout == "out"
    assert context.metadata == {
        "mew_terminal_bench_artifact_dir": str(task_dir),
        "mew_terminal_bench_summary": summary,
    }


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


def test_run_captures_nonzero_command_exit_without_harbor_exception(tmp_path):
    module = load_agent_module()
    stdout_report = {
        "summary": "work attempt ended with model error",
        "work_exit_code": 1,
        "work_report": {"stop_reason": "model_error"},
    }
    agent = module.MewTerminalBenchAgent(
        command_template="mew work --oneshot --instruction {instruction_shell}",
        artifact_root=tmp_path,
        timeout_seconds=5,
    )
    environment = FakeHarborEnvironment(
        SimpleNamespace(
            return_code=1,
            stdout=json.dumps(stdout_report),
            stderr="token expired",
        )
    )
    context = {"task_id": "nonzero-task"}

    stdout = asyncio.run(agent.run("instruction", environment, context))

    task_dir = tmp_path / "nonzero-task"
    transcript = json.loads((task_dir / "command-transcript.json").read_text(encoding="utf-8"))
    report = json.loads((task_dir / "mew-report.json").read_text(encoding="utf-8"))
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert stdout == json.dumps(stdout_report)
    assert environment.commands == ["set -o pipefail; mew work --oneshot --instruction instruction"]
    assert environment.exec_kwargs == [
        {
            "command": "set -o pipefail; mew work --oneshot --instruction instruction",
            "user": None,
            "env": None,
            "cwd": None,
            "timeout_sec": 5,
        }
    ]
    assert transcript["exit_code"] == 1
    assert transcript["stderr"] == "token expired"
    assert report == stdout_report
    assert summary["work_session_or_report_summary"] == "work attempt ended with model error"
    assert context["mew_terminal_bench_artifact_dir"] == str(task_dir)
    assert context["mew_terminal_bench_summary"] == summary


def test_stdout_report_fallback_writes_report_and_context_summary(tmp_path):
    module = load_agent_module()
    stdout_report = {
        "status": "smoke-complete",
        "summary": "stdout recovered summary",
        "verification": {
            "passed": None,
            "command": "mew-smoke",
            "reason": "Terminal-Bench verifier runs outside mew-smoke",
        },
    }
    agent = module.MewTerminalBenchAgent(
        command_template="mew-smoke {instruction_shell}",
        artifact_root=tmp_path,
        timeout_seconds=5,
    )
    environment = FakeEnvironment((0, json.dumps(stdout_report), "", False))
    context = {"task_id": "stdout-task"}

    stdout = asyncio.run(agent.run("instruction", environment, context))

    task_dir = tmp_path / "stdout-task"
    report = json.loads((task_dir / "mew-report.json").read_text(encoding="utf-8"))
    summary = json.loads((task_dir / "summary.json").read_text(encoding="utf-8"))

    assert stdout == json.dumps(stdout_report)
    assert report == stdout_report
    assert summary["work_session_or_report_summary"] == "stdout recovered summary"
    assert summary["verifier_result"] == stdout_report["verification"]
    assert summary["timeout_status"] == {"timed_out": False, "timeout_seconds": 5}
    assert context["mew_terminal_bench_artifact_dir"] == str(task_dir)
    assert context["mew_terminal_bench_summary"] == summary


def test_exec_as_agent_uses_harbor_timeout_sec_keyword(tmp_path, monkeypatch):
    module = load_agent_module()
    calls = []

    async def fake_exec_as_agent(self, environment, *, command, **kwargs):
        calls.append((environment, command, kwargs))
        assert "timeout" not in kwargs
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
    assert len(calls) == 1
    assert calls[0][0] is environment
    assert calls[0][2] == {"env": None, "cwd": None, "timeout_sec": 5}
    assert "instruction with spaces" in calls[0][1]
    assert transcript["stdout"] == "retry stdout"
    assert transcript["stderr"] == "retry stderr"
    assert summary["timeout_status"] == {"timed_out": False, "timeout_seconds": 5}
    assert context.mew_terminal_bench_artifact_dir == str(task_dir)
    assert context.mew_terminal_bench_summary == summary
