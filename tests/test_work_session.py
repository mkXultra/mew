import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mew.cli import main
from mew.commands import format_work_live_step_result
from mew.state import load_state, save_state, state_lock


def add_coding_task(state):
    task = {
        "id": 1,
        "title": "Build native hands",
        "description": "Exercise a native work session.",
        "status": "todo",
        "priority": "normal",
        "kind": "coding",
        "notes": "",
        "command": "",
        "cwd": ".",
        "auto_execute": False,
        "agent_backend": "",
        "agent_model": "",
        "agent_prompt": "",
        "agent_run_id": None,
        "plans": [],
        "latest_plan_id": None,
        "runs": [],
        "created_at": "now",
        "updated_at": "now",
    }
    state["tasks"].append(task)
    return task


class WorkSessionTests(unittest.TestCase):
    def test_live_work_progress_flushes_stdout_before_stderr(self):
        from mew.commands import work_ai_progress

        class FlushSpy(StringIO):
            def __init__(self):
                super().__init__()
                self.flush_count = 0

            def flush(self):
                self.flush_count += 1
                super().flush()

        stdout = FlushSpy()
        stderr = StringIO()
        args = SimpleNamespace(live=True, progress=False, json=False)

        with redirect_stdout(stdout), redirect_stderr(stderr):
            work_ai_progress(args)("THINK ok")

        self.assertEqual(stdout.flush_count, 1)
        self.assertIn("mew work ai: THINK ok", stderr.getvalue())

    def test_work_live_step_result_groups_sections_and_tool_duration(self):
        text = format_work_live_step_result(
            {
                "status": "completed",
                "action": {"type": "run_command"},
                "tool_call": {
                    "id": 7,
                    "tool": "run_command",
                    "status": "completed",
                    "started_at": "2026-04-17T00:00:00Z",
                    "finished_at": "2026-04-17T00:00:02Z",
                    "parameters": {"command": "echo hi"},
                    "result": {
                        "command": "echo hi",
                        "cwd": ".",
                        "exit_code": 0,
                        "stdout": "hi\n",
                    },
                },
            },
            resume={
                "phase": "idle",
                "context": {"pressure": "low", "tool_calls": 1, "model_turns": 1},
                "working_memory": {
                    "hypothesis": "Command output proves the tool path works.",
                    "next_step": "Continue with the focused verifier.",
                    "last_verified_state": "echo passed",
                },
            },
        )

        self.assertIn("outcome:\n  status: completed", text)
        self.assertIn("tools:\n  tool #7 [completed] run_command exit=0 duration=2.0s echo hi", text)
        self.assertIn("\n  cwd: .", text)
        self.assertNotIn("\ncwd: .", text)
        self.assertNotIn("summary: command:", text)
        self.assertIn("stdout:\n    hi", text)
        self.assertIn("session:\n  phase: idle", text)
        self.assertIn("memory_hypothesis: Command output proves the tool path works.", text)
        self.assertIn("memory_next: Continue with the focused verifier.", text)
        self.assertIn("memory_verified: echo passed", text)

    def test_work_live_step_result_marks_stale_working_memory(self):
        text = format_work_live_step_result(
            {"status": "completed", "action": {"type": "remember"}, "summary": "noted"},
            resume={
                "phase": "idle",
                "working_memory": {
                    "next_step": "Use the old plan.",
                    "stale_after_tool_call_id": 9,
                    "stale_after_tool": "run_tests",
                },
            },
        )

        self.assertIn("memory: stale; refresh before relying on next_step", text)
        self.assertIn("stale_memory_next: Use the old plan.", text)
        self.assertNotIn("  memory_next: Use the old plan.", text.splitlines())

    def test_work_live_step_result_surfaces_recurring_failure_ribbon(self):
        text = format_work_live_step_result(
            {"status": "failed", "action": {"type": "run_tests"}, "summary": "verification failed"},
            resume={
                "phase": "failed",
                "recurring_failures": [
                    {
                        "tool": "run_tests",
                        "target": "uv run pytest -q",
                        "error": "verification failed with exit_code=1",
                        "count": 3,
                        "last_tool_call_id": 9,
                    }
                ],
            },
        )

        self.assertIn(
            "repeat: run_tests uv run pytest -q failed 3x "
            "(same error: verification failed with exit_code=1); last_tool=#9",
            text,
        )

    def test_work_session_resume_detects_recurring_failures(self):
        from mew.work_session import build_work_session_resume, format_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Repeat",
            "goal": "Detect repeated failures.",
            "updated_at": "now",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "run_tests",
                    "status": "failed",
                    "parameters": {"command": "uv run pytest -q"},
                    "result": {"command": "uv run pytest -q", "exit_code": 1, "stderr": "same failure\n"},
                    "error": "verification failed with exit_code=1",
                },
                {
                    "id": 2,
                    "tool": "run_tests",
                    "status": "failed",
                    "parameters": {"command": "uv run pytest -q"},
                    "result": {"command": "uv run pytest -q", "exit_code": 1, "stderr": "same failure\n"},
                    "error": "verification failed with exit_code=1",
                },
            ],
            "model_turns": [],
        }

        resume = build_work_session_resume(session)
        self.assertEqual(resume["recurring_failures"][0]["count"], 2)
        self.assertEqual(resume["recurring_failures"][0]["last_tool_call_id"], 2)
        text = format_work_session_resume(resume)
        self.assertIn("Recurring failures", text)
        self.assertIn("run_tests uv run pytest -q failed 2x", text)

    def test_work_session_runs_read_only_tools_and_journals_results(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello native hands\n", encoding="utf-8")
                Path("src").mkdir()
                Path("src/app.py").write_text("print('hi')\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--start-session", "--json"]), 0)
                created = json.loads(stdout.getvalue())
                self.assertTrue(created["created"])
                self.assertEqual(created["work_session"]["task_id"], 1)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "README.md",
                                "--allow-read",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                read_result = json.loads(stdout.getvalue())
                self.assertEqual(read_result["tool_call"]["status"], "completed")
                self.assertIn("hello native hands", read_result["tool_call"]["result"]["text"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "glob",
                                "--pattern",
                                "*.py",
                                "--path",
                                ".",
                                "--allow-read",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                glob_result = json.loads(stdout.getvalue())
                self.assertEqual(glob_result["tool_call"]["status"], "completed")
                self.assertTrue(
                    any(match["path"].endswith("src/app.py") for match in glob_result["tool_call"]["result"]["matches"])
                )

                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["status"], "active")
                self.assertEqual([call["tool"] for call in session["tool_calls"]], ["read_file", "glob"])
                self.assertEqual(session["tool_calls"][0]["status"], "completed")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1"]), 0)
                text = stdout.getvalue()
                self.assertIn("Work session", text)
                self.assertIn("phase=idle", text)
                self.assertIn("tool_calls=2", text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                session_text = stdout.getvalue()
                self.assertIn("Read file", session_text)
                self.assertIn("matches=1", session_text)
                self.assertNotIn("hello native hands", session_text)
            finally:
                os.chdir(old_cwd)

    def test_work_glob_skips_cache_and_virtualenv_dirs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("src").mkdir()
                Path("src/app.py").write_text("print('app')\n", encoding="utf-8")
                Path(".pytest_cache").mkdir()
                Path(".pytest_cache/README.py").write_text("cache\n", encoding="utf-8")
                Path(".venv").mkdir()
                Path(".venv/generated.py").write_text("venv\n", encoding="utf-8")
                Path("__pycache__").mkdir()
                Path("__pycache__/cached.py").write_text("cache\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "glob",
                                "--pattern",
                                "*.py",
                                "--path",
                                ".",
                                "--allow-read",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )

                data = json.loads(stdout.getvalue())
                paths = [match["path"] for match in data["tool_call"]["result"]["matches"]]
                self.assertTrue(any(path.endswith("src/app.py") for path in paths))
                self.assertFalse(any(".pytest_cache" in path for path in paths))
                self.assertFalse(any(".venv" in path for path in paths))
                self.assertFalse(any("__pycache__" in path for path in paths))
            finally:
                os.chdir(old_cwd)

    def test_work_session_read_file_default_handles_larger_source_files(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                marker = "tail marker after old six kilobyte limit"
                Path("large.py").write_text("x" * 7000 + marker, encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "large.py",
                                "--allow-read",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                result = data["tool_call"]["result"]
                self.assertFalse(result["truncated"])
                self.assertIn(marker, result["text"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "large.py",
                                "--allow-read",
                                ".",
                                "--max-chars",
                                "12",
                                "--offset",
                                "7000",
                                "--json",
                            ]
                        ),
                        0,
                    )
                page = json.loads(stdout.getvalue())["tool_call"]["result"]
                self.assertEqual(page["offset"], 7000)
                self.assertEqual(page["next_offset"], 7012)
                self.assertEqual(page["text"], marker[:12])
            finally:
                os.chdir(old_cwd)

    def test_work_session_read_file_can_target_lines_from_search_results(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("app.py").write_text(
                    "line one\nline two\nline three\nline four\nline five\n",
                    encoding="utf-8",
                )
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "app.py",
                                "--allow-read",
                                ".",
                                "--line-start",
                                "3",
                                "--line-count",
                                "2",
                                "--json",
                            ]
                        ),
                        0,
                    )

                result = json.loads(stdout.getvalue())["tool_call"]["result"]
                self.assertEqual(result["line_start"], 3)
                self.assertEqual(result["line_end"], 4)
                self.assertEqual(result["next_line"], 5)
                self.assertTrue(result["has_more_lines"])
                self.assertFalse(result["truncated"])
                self.assertEqual(result["text"], "line three\nline four\n")
                self.assertNotIn("line two", result["text"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                session_output = stdout.getvalue()
                self.assertIn("lines=3-4 next_line=5", session_output)
                self.assertNotIn("lines=3-4 next_line=5 (truncated)", session_output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_read_file_line_start_reports_invalid_and_eof(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("app.py").write_text("one\ntwo\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "app.py",
                                "--allow-read",
                                ".",
                                "--line-start",
                                "0",
                                "--json",
                            ]
                        ),
                        1,
                    )
                failed = json.loads(stdout.getvalue())["tool_call"]
                self.assertEqual(failed["status"], "failed")
                self.assertIn("line_start must be >= 1", failed["error"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "read_file",
                                "--path",
                                "app.py",
                                "--allow-read",
                                ".",
                                "--line-start",
                                "99",
                                "--line-count",
                                "2",
                                "--json",
                            ]
                        ),
                        0,
                    )
                result = json.loads(stdout.getvalue())["tool_call"]["result"]
                self.assertTrue(result["eof"])
                self.assertIsNone(result["line_end"])
                self.assertEqual(result["message"], "line_start 99 is beyond EOF at line 2")
                self.assertEqual(result["text"], "")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                session_text = stdout.getvalue()
                self.assertIn("lines=99-EOF", session_text)
                self.assertIn("line_start 99 is beyond EOF at line 2", session_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--timeline"]), 0)
                timeline_output = stdout.getvalue()
                self.assertIn("read_file failed: line_start must be >= 1", timeline_output)
                self.assertNotIn("read_file failed: read_file failed", timeline_output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_controls_prefer_local_mew_executable(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                local_mew = Path("mew")
                local_mew.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                local_mew.chmod(0o755)
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)

                output = stdout.getvalue()
                self.assertIn("./mew work 1 --live --model-backend codex --allow-read . --max-steps 1", output)
                self.assertIn("./mew chat", output)
            finally:
                os.chdir(old_cwd)

    def test_work_tool_requires_active_session_and_read_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--tool", "read_file", "--path", "README.md"]),
                        1,
                    )
                self.assertIn("work tool #1 [failed] read_file", stdout.getvalue())
                self.assertIn("read access is disabled", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_tool_saves_running_call_before_execution(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                def fake_execute(tool, parameters, allowed_read_roots):
                    state = load_state()
                    call = state["work_sessions"][0]["tool_calls"][0]
                    self.assertEqual(call["status"], "running")
                    self.assertEqual(call["tool"], "read_file")
                    return {"path": str(Path("README.md").resolve()), "type": "file", "text": "ok", "truncated": False}

                with patch("mew.commands.execute_work_tool", side_effect=fake_execute):
                    with redirect_stdout(StringIO()) as stdout:
                        self.assertEqual(
                            main(["work", "1", "--tool", "read_file", "--path", "README.md", "--allow-read", "."]),
                            0,
                        )
                self.assertIn("work tool #1 [completed] read_file", stdout.getvalue())
                state = load_state()
                self.assertEqual(state["work_sessions"][0]["tool_calls"][0]["status"], "completed")
            finally:
                os.chdir(old_cwd)

    def test_work_session_runs_tests_behind_verify_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                "python -c \"print('ok')\"",
                            ]
                        ),
                        1,
                    )
                self.assertIn("verification is disabled", stdout.getvalue())

                command = f"{os.environ.get('PYTHON', 'python3')} -c \"print('ok')\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                command,
                                "--allow-verify",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["tool_call"]["status"], "completed")
                self.assertEqual(data["tool_call"]["result"]["exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_work_session_marks_failed_tests_and_summarizes_failure(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = (
                    f"{sys.executable} -c "
                    "\"import sys; print('stdout context'); print('stderr context', file=sys.stderr); sys.exit(1)\""
                )
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                command,
                                "--allow-verify",
                                "--json",
                            ]
                        ),
                        1,
                    )
                data = json.loads(stdout.getvalue())
                call = data["tool_call"]
                self.assertEqual(call["status"], "failed")
                self.assertIn("verification failed with exit_code=1", call["error"])
                self.assertIn("stderr context", call["summary"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--details"]), 0)
                details = stdout.getvalue()
                self.assertIn("Verification failures", details)
                self.assertIn("#1 [failed] run_tests verification failed with exit_code=1", details)
                self.assertIn("exit_code: 1", details)
                self.assertIn("stderr context", details)
                self.assertIn("stdout context", details)
            finally:
                os.chdir(old_cwd)

    def test_run_tests_missing_executable_reports_not_found(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                "mew-missing-test-command --version",
                                "--allow-verify",
                                "--json",
                            ]
                        ),
                        1,
                    )
                call = json.loads(stdout.getvalue())["tool_call"]
                self.assertEqual(call["status"], "failed")
                self.assertIn("executable not found: mew-missing-test-command", call["error"])
                self.assertIn("exit_code: unavailable", call["summary"])
                self.assertIn("failure: executable not found: mew-missing-test-command", call["summary"])
                self.assertIn("stderr:\nexecutable not found: mew-missing-test-command", call["summary"])
                self.assertNotIn("[Errno 2]", call["summary"])
                self.assertIsNone(call["result"]["exit_code"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                resume_text = stdout.getvalue()
                self.assertIn("exit=unavailable", resume_text)
                self.assertNotIn("exit=None", resume_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--commands"]), 0)
                command_text = stdout.getvalue()
                self.assertIn("exit=unavailable", command_text)
                self.assertIn("executable not found: mew-missing-test-command", command_text)
                self.assertNotIn("exit=None", command_text)
                self.assertNotIn("[Errno 2]", command_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--tests"]), 0)
                tests_text = stdout.getvalue()
                self.assertIn("exit=unavailable", tests_text)
                self.assertNotIn("exit=None", tests_text)
            finally:
                os.chdir(old_cwd)

    def test_work_session_runs_command_behind_shell_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = f"{os.environ.get('PYTHON', 'python3')} -c \"print('shell ok')\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_command", "--command", command]),
                        1,
                    )
                self.assertIn("shell command execution is disabled", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_command",
                                "--command",
                                command,
                                "--allow-shell",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["tool_call"]["status"], "completed")
                self.assertIn("shell ok", data["tool_call"]["result"]["stdout"])

                failing_command = f"{os.environ.get('PYTHON', 'python3')} -c \"import sys; sys.exit(2)\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_command",
                                "--command",
                                failing_command,
                                "--allow-shell",
                                "--json",
                            ]
                        ),
                        0,
                    )
                failed_data = json.loads(stdout.getvalue())
                self.assertEqual(failed_data["tool_call"]["status"], "completed")
                self.assertEqual(failed_data["tool_call"]["result"]["exit_code"], 2)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                resume = stdout.getvalue()
                self.assertIn("Failures", resume)
                self.assertIn(f"#{failed_data['tool_call']['id']} run_command exit=2", resume)
                self.assertIn("phase: failed", resume)
            finally:
                os.chdir(old_cwd)

    def test_work_session_git_tools_are_read_only_and_gated(self):
        if not shutil.which("git"):
            self.skipTest("git not found")
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                Path("app.py").write_text("print('old')\n", encoding="utf-8")
                subprocess.run(["git", "add", "app.py"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.email=mew@example.invalid",
                        "-c",
                        "user.name=mew",
                        "commit",
                        "-m",
                        "init",
                    ],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                Path("app.py").write_text("print('new')\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--tool", "git_status", "--json"]), 1)
                self.assertIn("git inspection is disabled", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--tool", "git_status", "--allow-read", ".", "--json"]),
                        0,
                    )
                status_data = json.loads(stdout.getvalue())
                self.assertEqual(status_data["tool_call"]["status"], "completed")
                self.assertIn(" M app.py", status_data["tool_call"]["result"]["stdout"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--tool", "git_diff", "--allow-read", ".", "--json"]),
                        0,
                    )
                diff_data = json.loads(stdout.getvalue())
                diff_text = diff_data["tool_call"]["result"]["stdout"]
                self.assertIn("-print('old')", diff_text)
                self.assertIn("+print('new')", diff_text)
            finally:
                os.chdir(old_cwd)

    def test_work_tool_progress_streams_command_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = (
                    f"{sys.executable} -c "
                    "\"import sys; print('stream stdout', flush=True); "
                    "print('stream stderr', file=sys.stderr, flush=True)\""
                )
                with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                command,
                                "--allow-verify",
                                "--progress",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["tool_call"]["status"], "completed")
                progress = stderr.getvalue()
                self.assertIn("mew work: tool #1 run_tests start", progress)
                self.assertIn("mew work: tool #1 stdout: stream stdout", progress)
                self.assertIn("mew work: tool #1 stderr: stream stderr", progress)
                self.assertIn("mew work: tool #1 completed", progress)
            finally:
                os.chdir(old_cwd)

    def test_work_session_write_tools_default_to_dry_run_and_can_apply_with_verification(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("old text\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "old",
                                "--new",
                                "new",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                dry_run = json.loads(stdout.getvalue())
                self.assertTrue(dry_run["tool_call"]["result"]["dry_run"])
                self.assertFalse(dry_run["tool_call"]["result"]["written"])
                self.assertEqual(target.read_text(encoding="utf-8"), "old text\n")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "old",
                                "--new",
                                "new",
                                "--allow-write",
                                ".",
                                "--apply",
                                "--json",
                            ]
                        ),
                        1,
                    )
                refused = json.loads(stdout.getvalue())
                self.assertEqual(refused["tool_call"]["status"], "failed")
                self.assertIn("applied writes require", refused["tool_call"]["error"])
                self.assertEqual(target.read_text(encoding="utf-8"), "old text\n")

                command = f"{sys.executable} -c \"print('verify ok')\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "old",
                                "--new",
                                "new",
                                "--allow-write",
                                ".",
                                "--apply",
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--json",
                            ]
                        ),
                        0,
                    )
                applied = json.loads(stdout.getvalue())
                self.assertFalse(applied["tool_call"]["result"]["dry_run"])
                self.assertTrue(applied["tool_call"]["result"]["written"])
                self.assertEqual(applied["tool_call"]["result"]["verification_exit_code"], 0)
                self.assertEqual(target.read_text(encoding="utf-8"), "new text\n")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--details"]), 0)
                details = stdout.getvalue()
                self.assertIn("Recent diffs", details)
                self.assertIn("Diff preview (+1 -1)", details)
                self.assertIn("-old text", details)
                self.assertIn("+new text", details)
                self.assertIn("verification_exit_code=0", details)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--diffs"]), 0)
                diffs = stdout.getvalue()
                self.assertIn("Work diffs #1 [active] task=#1", diffs)
                self.assertIn("Diff preview (+1 -1)", diffs)
                self.assertIn("-old text", diffs)
                self.assertIn("+new text", diffs)
                self.assertIn("verification_exit_code=0", diffs)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--diffs", "--json"]), 0)
                diff_data = json.loads(stdout.getvalue())
                self.assertEqual(diff_data["diffs"][0]["diff_stats"], {"added": 1, "removed": 1})

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--tests"]), 0)
                tests_output = stdout.getvalue()
                self.assertIn("Work tests #1 [active] task=#1", tests_output)
                self.assertIn("[passed] edit_file_verification", tests_output)
                self.assertIn("verify ok", tests_output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--tests", "--json"]), 0)
                tests_data = json.loads(stdout.getvalue())
                self.assertEqual(tests_data["tests"][0]["kind"], "edit_file_verification")
                self.assertEqual(tests_data["tests"][0]["exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_work_session_resume_bundle_summarizes_reentry_context(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", "README.md", "--allow-read", "."]), 0)
                command = f"{sys.executable} -c \"import sys; print('resume ok'); print('resume err', file=sys.stderr)\""
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_tests", "--command", command, "--allow-verify"]),
                        0,
                    )
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "README.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                            ]
                        ),
                        0,
                    )

                from mew.work_loop import build_work_model_context

                state = load_state()
                session = state["work_sessions"][0]
                task = state["tasks"][0]
                context = build_work_model_context(state, session, task, "now")
                self.assertEqual(context["work_session"]["resume"]["pending_approvals"][0]["tool_call_id"], 3)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(resume["session_id"], 1)
                self.assertIn("README.md", resume["files_touched"][0])
                self.assertEqual(resume["commands"][0]["tool"], "run_tests")
                self.assertEqual(resume["commands"][0]["exit_code"], 0)
                self.assertIn("resume ok", resume["commands"][0]["stdout"])
                self.assertIn("resume err", resume["commands"][0]["stderr"])
                self.assertEqual(resume["phase"], "awaiting_approval")
                self.assertEqual(resume["pending_approvals"][0]["tool_call_id"], 3)
                self.assertEqual(resume["pending_approvals"][0]["diff_stats"], {"added": 1, "removed": 1})
                self.assertIn("Diff preview (+1 -1)", resume["pending_approvals"][0]["diff_preview"])
                self.assertIn("-before", resume["pending_approvals"][0]["diff_preview"])
                self.assertIn("+after", resume["pending_approvals"][0]["diff_preview"])
                self.assertIn("/work-session approve 3", resume["pending_approvals"][0]["approve_hint"])
                self.assertIn(shlex.quote(command), resume["pending_approvals"][0]["approve_hint"])
                self.assertIn("/work-session reject 3", resume["pending_approvals"][0]["reject_hint"])
                self.assertEqual(resume["context"]["tool_calls"], 3)
                self.assertEqual(resume["context"]["pressure"], "low")
                self.assertGreater(resume["context"]["total_session_chars"], 0)
                self.assertEqual(resume["next_action"], "approve or reject pending write tool calls")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session resume", {}), "continue")
                text = stdout.getvalue()
                self.assertIn("Work resume #1 [active] task=#1", text)
                self.assertIn("phase: awaiting_approval", text)
                self.assertIn("Pending approvals", text)
                self.assertIn("stdout:", text)
                self.assertIn("resume ok", text)
                self.assertIn("stderr:", text)
                self.assertIn("resume err", text)
                self.assertIn("#3 edit_file", text)
                self.assertIn("Diff preview (+1 -1)", text)
                self.assertIn("-before", text)
                self.assertIn("+after", text)
                self.assertIn("approve: /work-session approve 3", text)
                self.assertIn("reject: /work-session reject 3", text)
                self.assertIn("Context pressure", text)
                self.assertIn("pressure=low tool_calls=3", text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session diffs", {}), "continue")
                diff_text = stdout.getvalue()
                self.assertIn("Work diffs #1 [active] task=#1", diff_text)
                self.assertIn("Diff preview (+1 -1)", diff_text)
                self.assertIn("-before", diff_text)
                self.assertIn("+after", diff_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session tests", {}), "continue")
                tests_text = stdout.getvalue()
                self.assertIn("Work tests #1 [active] task=#1", tests_text)
                self.assertIn("[passed] run_tests", tests_text)
                self.assertIn("resume ok", tests_text)
                self.assertIn("resume err", tests_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session resume --allow-read .", {}), "continue")
                chat_world_text = stdout.getvalue()
                self.assertIn("World state", chat_world_text)
                self.assertIn("git_status exit=", chat_world_text)
                git_status_line = next(line for line in chat_world_text.splitlines() if line.startswith("git_status exit="))
                self.assertNotIn("exit=128 (clean)", git_status_line)
                self.assertIn("README.md", chat_world_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", ".", "--json"]), 0)
                world_resume = json.loads(stdout.getvalue())["resume"]
                self.assertIn("exit_code", world_resume["world_state"]["git_status"])
                self.assertTrue(world_resume["world_state"]["files"][0]["exists"])
            finally:
                os.chdir(old_cwd)

    def test_run_tests_default_path_does_not_touch_dot(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("sample.py").write_text("print('ok')\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_tests",
                                "--command",
                                f"{sys.executable} -m py_compile sample.py",
                                "--allow-verify",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(resume["files_touched"], [])
                self.assertNotIn("path", load_state()["work_sessions"][0]["tool_calls"][0]["parameters"])
            finally:
                os.chdir(old_cwd)

    def test_work_session_commands_pane_surfaces_command_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "run_command",
                                "--command",
                                f"{sys.executable} -c \"print('command ok')\"",
                                "--allow-shell",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--commands"]), 0)
                output = stdout.getvalue()
                self.assertIn("Work commands #1 [active] task=#1", output)
                self.assertIn("[completed] run_command exit=0", output)
                self.assertIn("command ok", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--commands", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["commands"][0]["tool"], "run_command")
                self.assertEqual(data["commands"][0]["exit_code"], 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session commands", {}), "continue")
                chat_output = stdout.getvalue()
                self.assertIn("Work commands #1 [active] task=#1", chat_output)
                self.assertIn("command ok", chat_output)
            finally:
                os.chdir(old_cwd)

    def test_clip_tail_starts_truncated_output_on_line_boundary(self):
        from mew.work_session import clip_tail

        text = "alpha line\nbeta line\ngamma line\n"

        clipped = clip_tail(text, max_chars=18)

        self.assertEqual(clipped, "[...snip...]\ngamma line\n")
        self.assertNotIn("ne\ngamma", clipped)

    def test_work_model_turn_guidance_surfaces_in_reentry_views(self):
        from mew.work_loop import build_work_model_context, work_model_turn_for_model
        from mew.work_session import (
            build_work_session_resume,
            build_work_session_timeline,
            finish_work_model_turn,
            format_work_session_resume,
            format_work_session_timeline,
            start_work_model_turn,
        )

        state = {"next_ids": {"work_model_turn": 1}, "work_sessions": []}
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Guidance",
            "goal": "Remember one-shot guidance.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [],
            "model_turns": [],
        }
        state["work_sessions"].append(session)

        turn = start_work_model_turn(
            state,
            session,
            {"summary": "read first"},
            {"summary": "read first"},
            {"type": "read_file", "path": "README.md", "reason": "read before finish"},
            guidance="Freshly inspect README before deciding.",
        )
        turn = finish_work_model_turn(state, 1, turn["id"])

        resume = build_work_session_resume(session)
        self.assertEqual(resume["recent_decisions"][0]["guidance_snapshot"], "Freshly inspect README before deciding.")
        self.assertIn("guidance: Freshly inspect README before deciding.", format_work_session_resume(resume))
        self.assertEqual(build_work_session_timeline(session)[0]["guidance_snapshot"], "Freshly inspect README before deciding.")
        self.assertIn("guidance=Freshly inspect README before deciding.", format_work_session_timeline(session))
        self.assertEqual(work_model_turn_for_model(turn)["guidance_snapshot"], "Freshly inspect README before deciding.")
        self.assertNotIn("guidance", work_model_turn_for_model(turn))

        context = build_work_model_context(
            state,
            session,
            {"id": 1, "title": "Guidance", "description": "Remember one-shot guidance.", "status": "todo"},
            "now",
            guidance="",
        )
        self.assertEqual(context["guidance"], "")
        self.assertEqual(
            context["work_session"]["resume"]["recent_decisions"][0]["guidance_snapshot"],
            "Freshly inspect README before deciding.",
        )
        self.assertEqual(
            context["work_session"]["model_turns"][0]["guidance_snapshot"],
            "Freshly inspect README before deciding.",
        )
        self.assertNotIn("guidance", context["work_session"]["model_turns"][0])

    def test_work_session_resume_clips_guidance_on_word_boundary(self):
        from mew.work_loop import build_work_model_context
        from mew.work_session import (
            build_work_session_resume,
            finish_work_model_turn,
            format_work_session_resume,
            start_work_model_turn,
        )

        long_guidance = " ".join(f"word{i:03d}" for i in range(80))
        state = {"next_ids": {"work_model_turn": 1}, "work_sessions": []}
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Guidance",
            "goal": "Clip one-shot guidance.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [],
            "model_turns": [],
        }
        state["work_sessions"].append(session)

        turn = start_work_model_turn(
            state,
            session,
            {"summary": "remember"},
            {"summary": "remember"},
            {"type": "remember", "note": "keep guidance readable"},
            guidance=long_guidance,
        )
        finish_work_model_turn(state, 1, turn["id"])

        resume = build_work_session_resume(session)
        guidance = resume["recent_decisions"][0]["guidance_snapshot"]
        self.assertTrue(guidance.endswith(" ... output truncated ..."))
        self.assertNotIn("\n", guidance)
        prefix = guidance.removesuffix(" ... output truncated ...")
        self.assertRegex(prefix.split()[-1], r"^word\d{3}$")
        self.assertIn(f"guidance: {guidance}", format_work_session_resume(resume))

        context = build_work_model_context(
            state,
            session,
            {"id": 1, "title": "Guidance", "description": "Clip one-shot guidance.", "status": "todo"},
            "now",
            guidance="",
        )
        model_guidance = context["work_session"]["model_turns"][0]["guidance_snapshot"]
        self.assertNotIn("\n... output truncated ...", model_guidance)

    def test_work_session_resume_surfaces_working_memory(self):
        from mew.work_loop import build_work_model_context
        from mew.work_session import (
            build_work_session_resume,
            finish_work_model_turn,
            format_work_session_resume,
            start_work_model_turn,
        )

        state = {"next_ids": {"work_model_turn": 1}, "work_sessions": []}
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Memory",
            "goal": "Reenter with a compact hypothesis.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [],
            "model_turns": [],
        }
        state["work_sessions"].append(session)
        decision_plan = {
            "summary": "continue approval UX",
            "working_memory": {
                "hypothesis": "Approval UX still needs command output visibility.",
                "next_step": "Add a focused command-output pane.",
                "open_questions": ["Should chat expose the same pane?"],
                "last_verified_state": "full suite passed before this slice",
            },
        }

        turn = start_work_model_turn(
            state,
            session,
            decision_plan,
            {"summary": "continue approval UX"},
            {"type": "finish", "reason": "next slice is clear"},
        )
        finish_work_model_turn(state, 1, turn["id"])

        resume = build_work_session_resume(session)
        memory = resume["working_memory"]
        self.assertEqual(memory["hypothesis"], "Approval UX still needs command output visibility.")
        self.assertEqual(memory["next_step"], "Add a focused command-output pane.")
        self.assertEqual(memory["open_questions"], ["Should chat expose the same pane?"])
        self.assertEqual(memory["last_verified_state"], "full suite passed before this slice")
        self.assertEqual(memory["source"], "think")
        self.assertEqual(memory["model_turn_id"], 1)

        text = format_work_session_resume(resume)
        self.assertIn("Working memory", text)
        self.assertIn("hypothesis: Approval UX still needs command output visibility.", text)
        self.assertIn("next_step: Add a focused command-output pane.", text)
        self.assertIn("- Should chat expose the same pane?", text)

        context = build_work_model_context(
            state,
            session,
            {"id": 1, "title": "Memory", "description": "Reenter with a compact hypothesis.", "status": "todo"},
            "now",
        )
        self.assertEqual(
            context["work_session"]["resume"]["working_memory"]["next_step"],
            "Add a focused command-output pane.",
        )

    def test_work_session_working_memory_prefers_observed_verification_and_marks_stale(self):
        from mew.work_session import (
            build_work_session_resume,
            finish_work_model_turn,
            format_work_session_resume,
            start_work_model_turn,
        )

        state = {"next_ids": {"work_model_turn": 1}, "work_sessions": []}
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Observed memory",
            "goal": "Do not trust stale model verification claims.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "run_tests",
                    "status": "failed",
                    "parameters": {"command": "uv run pytest -q"},
                    "result": {"command": "uv run pytest -q", "exit_code": 1},
                    "summary": "tests failed",
                }
            ],
            "model_turns": [],
        }
        state["work_sessions"].append(session)

        first_turn = start_work_model_turn(
            state,
            session,
            {
                "summary": "old claim",
                "working_memory": {
                    "hypothesis": "Feature is ready.",
                    "next_step": "Ship it.",
                    "last_verified_state": "model claimed tests passed",
                },
            },
            {"summary": "old claim"},
            {"type": "finish", "reason": "old reason"},
        )
        finish_work_model_turn(state, 1, first_turn["id"])
        second_turn = start_work_model_turn(
            state,
            session,
            {"summary": "later turn without memory"},
            {"summary": "later turn without memory"},
            {"type": "finish", "reason": "later reason"},
        )
        finish_work_model_turn(state, 1, second_turn["id"])

        resume = build_work_session_resume(session)
        memory = resume["working_memory"]
        self.assertEqual(memory["last_verified_state"], "last verification failed exit=1: uv run pytest -q")
        self.assertEqual(memory["model_turn_id"], 1)
        self.assertEqual(memory["stale_after_model_turn_id"], 1)
        self.assertEqual(memory["latest_model_turn_id"], 2)
        self.assertEqual(memory["stale_turns"], 1)
        text = format_work_session_resume(resume)
        self.assertIn("last_verified_state: last verification failed exit=1: uv run pytest -q", text)
        self.assertIn("stale_next_step: Ship it.", text)
        self.assertNotIn("\nnext_step: Ship it.", text)
        self.assertIn("stale_after_model_turn: #1 (1 later turn(s) without working_memory; latest=#2)", text)

    def test_work_session_resume_falls_back_to_latest_turn_and_verification_state(self):
        from mew.work_session import (
            build_work_session_resume,
            finish_work_model_turn,
            format_work_session_resume,
            start_work_model_turn,
        )

        state = {"next_ids": {"work_model_turn": 1}, "work_sessions": []}
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Fallback memory",
            "goal": "Infer reentry memory from old turns.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "run_tests",
                    "status": "completed",
                    "parameters": {"command": "uv run pytest -q"},
                    "result": {"command": "uv run pytest -q", "exit_code": 0},
                    "summary": "tests passed",
                }
            ],
            "model_turns": [],
        }
        state["work_sessions"].append(session)

        turn = start_work_model_turn(
            state,
            session,
            {"summary": "Need a warm reentry contract."},
            {"summary": "Need a warm reentry contract."},
            {"type": "finish", "reason": "Next, persist a compact resume digest."},
        )
        finish_work_model_turn(state, 1, turn["id"])

        resume = build_work_session_resume(session)
        memory = resume["working_memory"]
        self.assertEqual(memory["hypothesis"], "Need a warm reentry contract.")
        self.assertEqual(memory["next_step"], "Next, persist a compact resume digest.")
        self.assertEqual(memory["last_verified_state"], "last verification passed exit=0: uv run pytest -q")
        self.assertEqual(memory["source"], "fallback")
        self.assertIn("last_verified_state: last verification passed exit=0: uv run pytest -q", format_work_session_resume(resume))

    def test_work_session_resume_does_not_create_memory_from_unrun_task_command(self):
        from mew.work_session import build_work_session_resume, format_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "No memory yet",
            "goal": "Avoid noisy resume memory.",
            "created_at": "then",
            "updated_at": "then",
            "tool_calls": [],
            "model_turns": [],
        }
        task = {"id": 1, "title": "No memory yet", "description": "", "status": "todo", "command": "uv run pytest -q"}

        resume = build_work_session_resume(session, task=task)

        self.assertEqual(resume["working_memory"], {})
        self.assertNotIn("Working memory", format_work_session_resume(resume))

    def test_work_session_stop_request_is_consumed_before_model_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--stop-session", "--stop-reason", "pause after this boundary", "--json"]),
                        0,
                    )
                stopped = json.loads(stdout.getvalue())["work_session"]
                self.assertTrue(stopped["stop_requested_at"])
                self.assertEqual(stopped["stop_reason"], "pause after this boundary")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(resume["phase"], "stop_requested")
                self.assertEqual(resume["stop_request"]["reason"], "pause after this boundary")

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries") as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(main(["work", "1", "--ai", "--auth", "auth.json", "--json"]), 0)
                report = json.loads(stdout.getvalue())
                self.assertEqual(report["stop_reason"], "stop_requested")
                self.assertEqual(report["stop_request"]["reason"], "pause after this boundary")
                self.assertEqual(report["steps"], [])
                call_model.assert_not_called()

                session = load_state()["work_sessions"][0]
                self.assertNotIn("stop_requested_at", session)
                self.assertEqual(session["last_stop_request"]["reason"], "pause after this boundary")
                self.assertTrue(session["stop_acknowledged_at"])
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(resume["last_stop_request"]["reason"], "pause after this boundary")
            finally:
                os.chdir(old_cwd)

    def test_work_session_note_records_user_note(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session-note", "prefer small verified steps", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["work_note"]["source"], "user")
                self.assertEqual(data["work_note"]["text"], "prefer small verified steps")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                text = stdout.getvalue()
                self.assertIn("Work notes", text)
                self.assertIn("[user] prefer small verified steps", text)
            finally:
                os.chdir(old_cwd)

    def test_work_session_show_without_active_lists_recent_sessions(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--session"]), 0)
                output = stdout.getvalue()

                self.assertIn("No active work session.", output)
                self.assertIn("Recent work sessions", output)
                self.assertIn("resume: mew work 1 --session --resume", output)
                self.assertIn("mew work <task-id> --start-session", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--session", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertIsNone(data["work_session"])
                self.assertEqual(data["recent_work_sessions"][0]["task_id"], 1)
                self.assertEqual(data["recent_work_sessions"][0]["resume_command"], "mew work 1 --session --resume")
                self.assertEqual(data["recent_work_sessions"][0]["chat_resume_command"], "/work-session resume 1")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--session", "--resume"]), 0)
                output = stdout.getvalue()
                self.assertIn("No active work session.", output)
                self.assertIn("Recent work sessions", output)
                self.assertIn("resume: mew work 1 --session --resume", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--session", "--resume", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertIsNone(data["resume"])
                self.assertEqual(data["recent_work_sessions"][0]["chat_resume_command"], "/work-session resume 1")
            finally:
                os.chdir(old_cwd)

    def test_work_session_show_active_includes_next_cli_controls(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()

                self.assertIn("Work session #1 [active] task=#1", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew work 1 --live --model-backend codex --allow-read .", output)
                self.assertIn("mew work 1 --follow --model-backend codex --allow-read .", output)
                self.assertNotIn("--auth auth.json", output)
                self.assertIn("--max-steps 3", output)
                self.assertIn("--max-steps 10", output)
                self.assertIn("mew chat", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertIn("mew chat", data["next_cli_controls"])
                self.assertTrue(any(command.startswith("mew work 1 --live") for command in data["next_cli_controls"]))

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["resume"]["session_id"], 1)
                self.assertIn("mew chat", data["next_cli_controls"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                output = stdout.getvalue()
                self.assertIn("Work resume #1 [active] task=#1", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew chat", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_recovers_interrupted_read_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("recover me\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Recover read.",
                            "created_at": "then",
                            "updated_at": "then",
                            "last_tool_call_id": 1,
                            "last_model_turn_id": 1,
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "tool": "read_file",
                                    "status": "running",
                                    "parameters": {"path": "README.md"},
                                    "result": None,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": None,
                                }
                            ],
                            "model_turns": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "status": "running",
                                    "decision_plan": {},
                                    "action_plan": {},
                                    "action": {"type": "read_file", "path": "README.md"},
                                    "tool_call_id": 1,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": None,
                                }
                            ],
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["repair", "--force", "--json"]), 0)
                self.assertEqual(load_state()["work_sessions"][0]["tool_calls"][0]["status"], "interrupted")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                interrupted_resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(interrupted_resume["phase"], "interrupted")
                self.assertEqual(interrupted_resume["recovery_plan"]["items"][0]["action"], "retry_tool")
                self.assertIn("recover-session", interrupted_resume["recovery_plan"]["items"][0]["hint"])
                self.assertIn("--auto-recover-safe", interrupted_resume["recovery_plan"]["items"][0]["auto_hint"])
                self.assertIn("--auto-recover-safe", interrupted_resume["recovery_plan"]["items"][0]["chat_auto_hint"])
                self.assertIn("--auto-recover-safe", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                text_resume = stdout.getvalue()
                self.assertIn("Recovery plan", text_resume)
                self.assertIn("auto: mew work 1 --session --resume --allow-read <path> --auto-recover-safe", text_resume)
                self.assertIn("chat_auto: /work-session resume 1 --allow-read <path> --auto-recover-safe", text_resume)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--recover-session", "--allow-read", ".", "--json"]), 0)
                report = json.loads(stdout.getvalue())

                self.assertEqual(report["recovery"]["action"], "retry_tool")
                self.assertEqual(report["recovery"]["source_tool_call_id"], 1)
                self.assertIn("world_state_before", report["recovery"])
                self.assertEqual(report["tool_call"]["tool"], "read_file")
                self.assertIn("recover me", report["tool_call"]["result"]["text"])
                session = load_state()["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(session["tool_calls"][0]["recovered_by_tool_call_id"], 2)
                self.assertEqual(session["model_turns"][0]["recovery_status"], "superseded")
                self.assertEqual(session["model_turns"][0]["recovered_by_tool_call_id"], 2)
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["resume"]["phase"], "idle")
            finally:
                os.chdir(old_cwd)

    def test_work_session_resume_auto_recovers_safe_read_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("auto recover me\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Auto recover read.",
                            "created_at": "then",
                            "updated_at": "then",
                            "last_tool_call_id": 1,
                            "last_model_turn_id": 1,
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "tool": "read_file",
                                    "status": "interrupted",
                                    "parameters": {"path": "README.md"},
                                    "result": None,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": "then",
                                }
                            ],
                            "model_turns": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "status": "interrupted",
                                    "decision_plan": {},
                                    "action_plan": {},
                                    "action": {"type": "read_file", "path": "README.md"},
                                    "tool_call_id": 1,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": "then",
                                }
                            ],
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["work", "1", "--session", "--resume", "--allow-read", ".", "--auto-recover-safe", "--json"]),
                        0,
                    )
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["auto_recovery"]["recovery"]["action"], "retry_tool")
                self.assertIn("world_state_before", payload["auto_recovery"]["recovery"])
                self.assertEqual(payload["auto_recovery"]["tool_call"]["status"], "completed")
                self.assertEqual(payload["resume"]["phase"], "idle")
                self.assertIn("auto recover me", payload["auto_recovery"]["tool_call"]["result"]["text"])

                session = load_state()["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(session["tool_calls"][0]["recovered_by_tool_call_id"], 2)
                self.assertEqual(session["model_turns"][0]["recovery_status"], "superseded")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", "."]), 0)
                self.assertNotIn("Recovery plan", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_session_resume_auto_recovery_requires_read_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("auto recover me\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Auto recover read.",
                            "created_at": "then",
                            "updated_at": "then",
                            "last_tool_call_id": 1,
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "tool": "read_file",
                                    "status": "interrupted",
                                    "parameters": {"path": "README.md"},
                                    "result": None,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": "then",
                                }
                            ],
                            "model_turns": [],
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--auto-recover-safe", "--json"]), 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["auto_recovery"]["recovery"]["action"], "needs_read_gate")
                self.assertEqual(payload["resume"]["phase"], "interrupted")
                self.assertEqual(len(load_state()["work_sessions"][0]["tool_calls"]), 1)
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_resume_auto_recovers_safe_read_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("chat auto recover me\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Chat auto recover read.",
                            "created_at": "then",
                            "updated_at": "then",
                            "last_tool_call_id": 1,
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "tool": "read_file",
                                    "status": "interrupted",
                                    "parameters": {"path": "README.md"},
                                    "result": None,
                                    "summary": "",
                                    "error": "",
                                    "started_at": "then",
                                    "finished_at": "then",
                                }
                            ],
                            "model_turns": [],
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        run_chat_slash_command("/work-session resume --allow-read . --auto-recover-safe", {}),
                        "continue",
                    )
                output = stdout.getvalue()
                self.assertIn("Auto recovery", output)
                self.assertIn("recovered work tool #1 -> #2 [completed] read_file", output)
                self.assertIn("phase: idle", output)
                self.assertIn("World state", output)
                session = load_state()["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(session["tool_calls"][1]["status"], "completed")
            finally:
                os.chdir(old_cwd)

    def test_chat_auto_recovery_hint_keeps_task_scope_with_multiple_sessions(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("one.md").write_text("one session\n", encoding="utf-8")
                Path("two.md").write_text("two session\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    second = dict(state["tasks"][0])
                    second["id"] = 2
                    second["title"] = "Second task"
                    state["tasks"].append(second)
                    state["work_sessions"].extend(
                        [
                            {
                                "id": 1,
                                "task_id": 1,
                                "status": "active",
                                "title": "First session",
                                "goal": "Recover first.",
                                "created_at": "then",
                                "updated_at": "then",
                                "last_tool_call_id": 1,
                                "tool_calls": [
                                    {
                                        "id": 1,
                                        "session_id": 1,
                                        "task_id": 1,
                                        "tool": "read_file",
                                        "status": "interrupted",
                                        "parameters": {"path": "one.md"},
                                        "started_at": "then",
                                        "finished_at": "then",
                                    }
                                ],
                                "model_turns": [],
                            },
                            {
                                "id": 2,
                                "task_id": 2,
                                "status": "active",
                                "title": "Second session",
                                "goal": "Recover second.",
                                "created_at": "then",
                                "updated_at": "then",
                                "last_tool_call_id": 2,
                                "tool_calls": [
                                    {
                                        "id": 2,
                                        "session_id": 2,
                                        "task_id": 2,
                                        "tool": "read_file",
                                        "status": "interrupted",
                                        "parameters": {"path": "two.md"},
                                        "started_at": "then",
                                        "finished_at": "then",
                                    }
                                ],
                                "model_turns": [],
                            },
                        ]
                    )
                    state["next_ids"]["work_tool_call"] = 3
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session 1", {}), "continue")
                self.assertIn("/work-session resume 1 --allow-read . --auto-recover-safe", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        run_chat_slash_command("/work-session resume 1 --allow-read . --auto-recover-safe", {}),
                        "continue",
                    )
                output = stdout.getvalue()
                self.assertIn("Work resume #1 [active] task=#1", output)
                self.assertIn("one session", load_state()["work_sessions"][0]["tool_calls"][1]["result"]["text"])
                state = load_state()
                self.assertEqual(state["work_sessions"][0]["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(state["work_sessions"][1]["tool_calls"][0]["status"], "interrupted")
            finally:
                os.chdir(old_cwd)

    def test_work_recovery_plan_deduplicates_turn_for_interrupted_tool(self):
        from mew.work_session import build_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Recover duplicated interruption.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {"id": 1, "tool": "read_file", "status": "interrupted", "parameters": {"path": "README.md"}},
            ],
            "model_turns": [
                {"id": 1, "status": "interrupted", "action": {"type": "read_file"}, "tool_call_id": 1},
                {"id": 2, "status": "interrupted", "action": {"type": "planning"}, "tool_call_id": None},
            ],
        }

        items = build_work_session_resume(session)["recovery_plan"]["items"]

        self.assertEqual([item["kind"] for item in items], ["tool_call", "model_turn"])
        self.assertEqual(items[0]["action"], "retry_tool")
        self.assertEqual(items[1]["action"], "replan")

    def test_work_recovery_plan_does_not_override_pending_approval_next_action(self):
        from mew.work_session import build_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Prefer approval.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {"id": 1, "tool": "read_file", "status": "interrupted", "parameters": {"path": "README.md"}},
                {
                    "id": 2,
                    "tool": "edit_file",
                    "status": "completed",
                    "parameters": {"path": "README.md"},
                    "result": {"dry_run": True, "changed": True, "path": "README.md"},
                },
            ],
            "model_turns": [],
        }

        resume = build_work_session_resume(session)

        self.assertEqual(resume["phase"], "awaiting_approval")
        self.assertEqual(resume["next_action"], "approve or reject pending write tool calls")
        self.assertEqual(resume["recovery_plan"]["items"][0]["action"], "retry_tool")

    def test_work_recovery_plan_hints_only_latest_recoverable_tool(self):
        from mew.work_session import build_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Recover latest.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {"id": 1, "tool": "read_file", "status": "interrupted", "parameters": {"path": "a.md"}},
                {"id": 2, "tool": "glob", "status": "interrupted", "parameters": {"path": ".", "pattern": "*.py"}},
            ],
            "model_turns": [],
        }

        items = build_work_session_resume(session)["recovery_plan"]["items"]

        self.assertNotIn("hint", items[0])
        self.assertIn("recover-session", items[1]["hint"])

    def test_work_recovery_plan_includes_side_effect_review_context(self):
        from mew.work_session import build_work_session_resume, format_work_session_resume

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Recover side effects.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "run_tests",
                    "status": "interrupted",
                    "parameters": {"command": "python mutate.py", "cwd": "."},
                },
                {
                    "id": 2,
                    "tool": "edit_file",
                    "status": "interrupted",
                    "parameters": {"path": "README.md"},
                },
            ],
            "model_turns": [],
        }

        resume = build_work_session_resume(session)
        items = resume["recovery_plan"]["items"]

        self.assertEqual(resume["commands"][0]["command"], "python mutate.py")
        self.assertEqual(resume["commands"][0]["cwd"], ".")
        self.assertEqual(items[0]["action"], "needs_user_review")
        self.assertEqual(items[0]["safety"], "command")
        self.assertEqual(items[0]["command"], "python mutate.py")
        self.assertIn("--session --resume --allow-read", items[0]["review_hint"])
        self.assertIn("idempotent", " ".join(items[0]["review_steps"]))
        self.assertEqual(items[1]["safety"], "write")
        self.assertEqual(items[1]["path"], "README.md")
        self.assertIn("git status/diff", " ".join(items[1]["review_steps"]))

        text = format_work_session_resume(resume)
        self.assertIn("review: ./mew work 1 --session --resume --allow-read <path>", text)
        self.assertIn("command: python mutate.py", text)
        self.assertIn("path: README.md", text)

    def test_work_recover_session_reports_review_context_for_side_effects(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Recover command.",
                            "created_at": "then",
                            "updated_at": "then",
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "tool": "run_tests",
                                    "status": "interrupted",
                                    "parameters": {"command": "python mutate.py"},
                                }
                            ],
                            "model_turns": [],
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--recover-session", "--json"]), 0)

                report = json.loads(stdout.getvalue())
                self.assertEqual(report["recovery"]["action"], "needs_user")
                review = report["recovery"]["review_item"]
                self.assertEqual(review["tool_call_id"], 1)
                self.assertEqual(review["command"], "python mutate.py")
                self.assertIn("--session --resume --allow-read", review["review_hint"])
                self.assertIn("idempotent", " ".join(review["review_steps"]))

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--recover-session"]), 0)
                text = stdout.getvalue()
                self.assertIn("command: python mutate.py", text)
                self.assertIn("review: mew work 1 --session --resume --allow-read <path>", text)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_report_includes_stop_request_reason(self):
        from mew.commands import format_work_ai_report

        text = format_work_ai_report(
            {
                "steps": [],
                "max_steps": 1,
                "stop_reason": "stop_requested",
                "session_id": 1,
                "task_id": 1,
                "stop_request": {"reason": "pause here"},
            }
        )

        self.assertIn("stop=stop_requested", text)
        self.assertIn("stop_request: pause here", text)

    def test_work_ai_report_includes_inline_approval_status(self):
        from mew.commands import format_work_ai_report

        text = format_work_ai_report(
            {
                "steps": [
                    {
                        "index": 1,
                        "status": "completed",
                        "action": {"type": "edit_file"},
                        "tool_call": {"id": 7, "summary": "previewed edit"},
                        "inline_approval": "rejected",
                    }
                ],
                "max_steps": 1,
                "stop_reason": "max_steps",
                "session_id": 1,
                "task_id": 1,
            }
        )

        self.assertIn("#1 [completed] edit_file tool_call=#7 inline_approval=rejected", text)

    def test_work_session_resume_next_action_uses_latest_tool_status(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("ok\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", ".", "--allow-read", "."]), 1)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--tool", "inspect_dir", "--path", ".", "--allow-read", "."]), 0)
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                self.assertEqual(len(resume["failures"]), 1)
                self.assertEqual(
                    resume["next_action"],
                    "continue the work session with /continue in chat or mew work --live",
                )
            finally:
                os.chdir(old_cwd)

    def test_work_session_can_approve_and_reject_dry_run_write_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                dry_run = json.loads(stdout.getvalue())
                self.assertEqual(dry_run["tool_call"]["id"], 1)
                self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

                command = f"{sys.executable} -c \"from pathlib import Path; assert Path('notes.md').read_text() == 'after\\n'\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--approve-tool",
                                "1",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--json",
                            ]
                        ),
                        0,
                    )
                approved = json.loads(stdout.getvalue())
                self.assertEqual(approved["approved_tool_call"]["approval_status"], "applied")
                self.assertEqual(approved["tool_call"]["parameters"]["approved_from_tool_call_id"], 1)
                self.assertTrue(approved["tool_call"]["result"]["written"])
                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--approve-tool",
                                "1",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                command,
                            ]
                        ),
                        1,
                    )
                self.assertIn("already applied", stderr.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "after",
                                "--new",
                                "never",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                second_dry_run = json.loads(stdout.getvalue())
                self.assertEqual(second_dry_run["tool_call"]["id"], 3)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--reject-tool",
                                "3",
                                "--reject-reason",
                                "not needed",
                                "--json",
                            ]
                        ),
                        0,
                    )
                rejected = json.loads(stdout.getvalue())
                self.assertEqual(rejected["rejected_tool_call"]["approval_status"], "rejected")
                self.assertEqual(rejected["rejected_tool_call"]["rejection_reason"], "not needed")
                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            finally:
                os.chdir(old_cwd)

    def test_work_session_approve_reuses_latest_verification_command(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = (
                    f"{sys.executable} -c "
                    "\"from pathlib import Path; assert Path('notes.md').read_text() == 'after\\n'\""
                )
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--tool", "run_tests", "--command", command, "--allow-verify"]), 1)
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--approve-tool", "2", "--allow-write", ".", "--json"]), 0)
                approved = json.loads(stdout.getvalue())

                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
                self.assertEqual(approved["tool_call"]["result"]["verification"]["command"], command)
                self.assertEqual(approved["tool_call"]["result"]["verification"]["exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_work_session_approve_reuses_default_verification_command(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                command = (
                    f"{sys.executable} -c "
                    "\"from pathlib import Path; assert Path('notes.md').read_text() == 'after\\n'\""
                )
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--start-session",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                command,
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--approve-tool", "1", "--allow-write", ".", "--json"]), 0)
                approved = json.loads(stdout.getvalue())

                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
                self.assertEqual(approved["tool_call"]["parameters"]["verify_command"], command)
                self.assertTrue(approved["tool_call"]["parameters"]["allow_verify"])
                self.assertEqual(approved["tool_call"]["result"]["verification_exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_work_session_approve_allows_exact_new_file_write_root(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("new_notes.md")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "write_file",
                                "--path",
                                str(target),
                                "--content",
                                "created\n",
                                "--create",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                dry_run = json.loads(stdout.getvalue())
                self.assertEqual(dry_run["tool_call"]["id"], 1)
                self.assertFalse(target.exists())

                command = (
                    f"{sys.executable} -c "
                    "\"from pathlib import Path; assert Path('new_notes.md').read_text() == 'created\\n'\""
                )
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--approve-tool",
                                "1",
                                "--allow-write",
                                str(target),
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--json",
                            ]
                        ),
                        0,
                    )
                approved = json.loads(stdout.getvalue())

                self.assertEqual(target.read_text(encoding="utf-8"), "created\n")
                self.assertEqual(approved["approved_tool_call"]["approval_status"], "applied")
                self.assertTrue(approved["tool_call"]["result"]["written"])
                self.assertEqual(approved["tool_call"]["result"]["verification"]["exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_workbench_surfaces_closed_work_session_writes_and_verifications(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                test_command = f"{sys.executable} -c \"print('session verify ok')\""
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_tests", "--command", test_command, "--allow-verify"]),
                        0,
                    )
                write_verify = (
                    f"{sys.executable} -c "
                    "\"from pathlib import Path; assert Path('generated.md').read_text() == 'generated\\n'\""
                )
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "write_file",
                                "--path",
                                "generated.md",
                                "--content",
                                "generated\n",
                                "--create",
                                "--allow-write",
                                ".",
                                "--apply",
                                "--allow-verify",
                                "--verify-command",
                                write_verify,
                            ]
                        ),
                        0,
                    )
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1"]), 0)
                output = stdout.getvalue()

                self.assertIn("Verification", output)
                self.assertIn("work1#1 [passed]", output)
                self.assertIn("session verify ok", output)
                self.assertIn("work1#2.verify [passed]", output)
                self.assertIn("generated.md", output)
                self.assertIn("Writes", output)
                self.assertIn("work1#2 [write_file]", output)
                self.assertIn("written=True", output)
                self.assertIn("verification_exit=0", output)
                self.assertIn("Work session", output)
                self.assertIn("#1 [closed]", output)
                self.assertNotIn("mew work 1 --live", output)
                self.assertIn("mew work 1 --start-session", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["verification", "--details"]), 0)
                verification_output = stdout.getvalue()
                self.assertIn("work1#1 [passed]", verification_output)
                self.assertIn("work1#2.verify [passed]", verification_output)
                self.assertIn("stdout:", verification_output)
                self.assertIn("session verify ok", verification_output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["verification", "--json"]), 0)
                verification_data = json.loads(stdout.getvalue())
                self.assertTrue(any(item["id"] == "work:1:1" for item in verification_data))
                self.assertTrue(any(item["id"] == "work:1:2:verify" for item in verification_data))
                self.assertTrue(all(item.get("source") for item in verification_data))

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["writes", "--details"]), 0)
                writes_output = stdout.getvalue()
                self.assertIn("work1#2 [write_file]", writes_output)
                self.assertIn("generated.md", writes_output)
                self.assertIn("verification_exit=0", writes_output)
                self.assertIn("diff:", writes_output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["writes", "--json"]), 0)
                writes_data = json.loads(stdout.getvalue())
                self.assertTrue(any(item["id"] == "work:1:2" for item in writes_data))
                self.assertTrue(all(item.get("source") for item in writes_data))
            finally:
                os.chdir(old_cwd)

    def test_global_verification_labels_include_work_session_id(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                command = f"{sys.executable} -c \"print('ok')\""
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_tests", "--command", command, "--allow-verify"]),
                        0,
                    )
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_tests", "--command", command, "--allow-verify"]),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["verification", "--json", "--all"]), 0)
                labels = [item.get("label") for item in json.loads(stdout.getvalue())]

                self.assertIn("work1#1", labels)
                self.assertIn("work2#2", labels)
            finally:
                os.chdir(old_cwd)

    def test_work_session_rolls_back_failed_applied_write(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = f"{sys.executable} -c \"import sys; sys.exit(1)\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                                "--apply",
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--json",
                            ]
                        ),
                        1,
                    )
                data = json.loads(stdout.getvalue())
                call = data["tool_call"]
                self.assertEqual(call["status"], "failed")
                self.assertIn("verification failed", call["error"])
                self.assertTrue(call["result"]["written"])
                self.assertTrue(call["result"]["rolled_back"])
                self.assertEqual(call["result"]["verification_exit_code"], 1)
                self.assertEqual(target.read_text(encoding="utf-8"), "before\n")
            finally:
                os.chdir(old_cwd)

    def test_work_session_records_rollback_failure(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                command = f"{sys.executable} -c \"import sys; sys.exit(1)\""
                with patch("mew.work_session.restore_write_snapshot", side_effect=OSError("rollback boom")):
                    with redirect_stdout(StringIO()) as stdout:
                        self.assertEqual(
                            main(
                                [
                                    "work",
                                    "1",
                                    "--tool",
                                    "edit_file",
                                    "--path",
                                    "notes.md",
                                    "--old",
                                    "before",
                                    "--new",
                                    "after",
                                    "--allow-write",
                                    ".",
                                    "--apply",
                                    "--allow-verify",
                                    "--verify-command",
                                    command,
                                    "--json",
                                ]
                            ),
                            1,
                        )
                data = json.loads(stdout.getvalue())
                call = data["tool_call"]
                self.assertEqual(call["status"], "failed")
                self.assertIn("rollback failed", call["error"])
                self.assertFalse(call["result"]["rolled_back"])
                self.assertEqual(call["result"]["rollback_error"], "rollback boom")
                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            finally:
                os.chdir(old_cwd)

    def test_work_session_treats_missing_verifier_as_failed(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                                "--apply",
                                "--allow-verify",
                                "--verify-command",
                                "mew-missing-verifier-command",
                                "--json",
                            ]
                        ),
                        1,
                    )
                data = json.loads(stdout.getvalue())
                call = data["tool_call"]
                self.assertEqual(call["status"], "failed")
                self.assertIn("executable not found: mew-missing-verifier-command", call["error"])
                self.assertIsNone(call["result"]["verification_exit_code"])
                self.assertTrue(call["result"]["rolled_back"])
                self.assertEqual(target.read_text(encoding="utf-8"), "before\n")
            finally:
                os.chdir(old_cwd)

    def test_work_ai_runs_model_selected_tool_and_journals_turn(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello model hands\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--allow-read", ".", "--json"]),
                                0,
                            )

                data = json.loads(stdout.getvalue())
                self.assertEqual(call_model.call_count, 2)
                self.assertEqual(data["steps"][0]["action"]["type"], "read_file")
                self.assertEqual(data["steps"][0]["tool_call"]["status"], "completed")
                self.assertIn("hello model hands", data["steps"][0]["tool_call"]["result"]["text"])

                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["model_turns"][0]["status"], "completed")
                self.assertEqual(session["model_turns"][0]["tool_call_id"], session["tool_calls"][0]["id"])
                self.assertEqual(session["tool_calls"][0]["tool"], "read_file")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--details"]), 0)
                text = stdout.getvalue()
                self.assertIn("Files", text)
                self.assertIn("Model turns", text)
                self.assertIn("README.md", text)
                self.assertIn("read_file tool_call=#1", text)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_persists_think_working_memory_to_resume(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello reentry memory\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_output = {
                    "summary": "read README",
                    "working_memory": {
                        "hypothesis": "README is the next evidence source.",
                        "next_step": "Read README.md before editing.",
                        "open_questions": ["Does README mention the target behavior?"],
                        "last_verified_state": "not verified yet",
                    },
                    "action": {"type": "read_file", "path": "README.md"},
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output) as call_model:
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                        "--json",
                                    ]
                                ),
                                0,
                            )

                data = json.loads(stdout.getvalue())
                self.assertEqual(call_model.call_count, 1)
                self.assertEqual(data["steps"][0]["tool_call"]["status"], "completed")
                session = load_state()["work_sessions"][0]
                self.assertEqual(
                    session["model_turns"][0]["decision_plan"]["working_memory"]["hypothesis"],
                    "README is the next evidence source.",
                )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(stdout.getvalue())["resume"]
                memory = resume["working_memory"]
                self.assertEqual(memory["hypothesis"], "README is the next evidence source.")
                self.assertEqual(memory["next_step"], "Read README.md before editing.")
                self.assertEqual(memory["open_questions"], ["Does README mention the target behavior?"])
                self.assertEqual(memory["source"], "think")
                self.assertEqual(memory["latest_tool_call_id"], 1)
                self.assertIn("latest tool #1 completed read_file", memory["latest_tool_state"])
                self.assertEqual(memory["stale_after_tool_call_id"], 1)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                text = stdout.getvalue()
                self.assertIn("Working memory", text)
                self.assertIn("hypothesis: README is the next evidence source.", text)
                self.assertIn("stale_next_step: Read README.md before editing.", text)
                self.assertNotIn("\nnext_step: Read README.md before editing.", text)
                self.assertIn("latest_tool_state: latest tool #1 completed read_file", text)
                self.assertIn("stale_after_tool_call: #1", text)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_progress_streams_model_and_tool_events(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("progress content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--progress",
                                        "--json",
                                    ]
                                ),
                                0,
                            )
                progress = stderr.getvalue()
                self.assertIn("THINK start", progress)
                self.assertIn("ACT ok action=read_file", progress)
                self.assertIn("tool #1 read_file start", progress)
                self.assertIn("tool #1 completed", progress)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_journals_running_model_turn_during_think(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("journal planning\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    from mew.work_session import build_work_session_resume

                    with state_lock():
                        state = load_state()
                        session = state["work_sessions"][0]
                        self.assertEqual(session["model_turns"][0]["status"], "running")
                        self.assertEqual(session["model_turns"][0]["action"]["type"], "planning")
                        self.assertEqual(build_work_session_resume(session, task=state["tasks"][0])["phase"], "planning")
                    prompt_context = json.loads(prompt.split("Context JSON:\n", 1)[1])
                    self.assertEqual(prompt_context["work_session"]["model_turns"], [])
                    return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                        "--json",
                                    ]
                                ),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["steps"][0]["action"]["type"], "read_file")
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(len(session["model_turns"]), 1)
                self.assertEqual(session["model_turns"][0]["status"], "completed")
                self.assertEqual(session["model_turns"][0]["tool_call_id"], 1)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_stop_requested_during_model_call_prevents_tool_start(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("should not be read\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    from mew.work_session import request_work_session_stop

                    with state_lock():
                        state = load_state()
                        request_work_session_stop(state["work_sessions"][0], "pause during model")
                        save_state(state)
                    return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                        "--json",
                                    ]
                                ),
                                0,
                            )

                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "stop_requested")
                self.assertEqual(data["steps"][0]["status"], "stopped")
                self.assertEqual(data["steps"][0]["stop_request"]["reason"], "pause during model")
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["tool_calls"], [])
                self.assertEqual(session["model_turns"][0]["status"], "completed")
                self.assertEqual(session["model_turns"][0]["stop_request"]["reason"], "pause during model")
                self.assertIn("stopped before tool execution", session["model_turns"][0]["summary"])
            finally:
                os.chdir(old_cwd)

    def test_work_ai_stop_requested_between_batch_tools_prevents_next_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("one.md").write_text("one\n", encoding="utf-8")
                Path("two.md").write_text("two\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_output = {
                    "summary": "batch read",
                    "action": {
                        "type": "batch",
                        "tools": [
                            {"type": "read_file", "path": "one.md"},
                            {"type": "read_file", "path": "two.md"},
                        ],
                    },
                }
                calls = []

                def fake_execute(tool, parameters, allowed_read_roots, output_progress=None):
                    from mew.work_session import request_work_session_stop

                    calls.append(parameters.get("path"))
                    if len(calls) == 1:
                        with state_lock():
                            state = load_state()
                            request_work_session_stop(state["work_sessions"][0], "pause between batch tools")
                            save_state(state)
                    return {"path": parameters.get("path"), "text": "ok\n", "offset": 0, "truncated": False}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with patch("mew.commands.execute_work_tool_with_output", side_effect=fake_execute):
                            with redirect_stdout(StringIO()) as stdout:
                                self.assertEqual(
                                    main(
                                        [
                                            "work",
                                            "1",
                                            "--ai",
                                            "--auth",
                                            "auth.json",
                                            "--allow-read",
                                            ".",
                                            "--act-mode",
                                            "deterministic",
                                            "--json",
                                        ]
                                    ),
                                    0,
                                )

                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "stop_requested")
                self.assertEqual(data["steps"][0]["status"], "stopped")
                self.assertEqual(calls, ["one.md"])
                session = load_state()["work_sessions"][0]
                self.assertEqual([call["parameters"]["path"] for call in session["tool_calls"]], ["one.md"])
                self.assertEqual(session["model_turns"][0]["tool_call_ids"], [1])
                self.assertEqual(session["model_turns"][0]["stop_request"]["reason"], "pause between batch tools")
            finally:
                os.chdir(old_cwd)

    def test_work_ai_can_stream_model_deltas_to_progress(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("stream model content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(
                    model_backend,
                    model_auth,
                    prompt,
                    model,
                    base_url,
                    timeout,
                    log_prefix=None,
                    on_text_delta=None,
                ):
                    if on_text_delta:
                        on_text_delta("model delta")
                    return {
                        "summary": "read README",
                        "action": {"type": "read_file", "path": "README.md"},
                    }

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--stream-model",
                                        "--progress",
                                        "--json",
                                    ]
                                ),
                                0,
                            )
                progress = stderr.getvalue()
                self.assertIn("THINK delta model delta", progress)
                self.assertIn("ACT delta model delta", progress)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_send_message_action_adds_outbox_message(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "report finding",
                        "action": {
                            "type": "send_message",
                            "message_type": "assistant",
                            "text": "I found the next step.",
                        },
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "send_message")
                self.assertEqual(data["steps"][0]["summary"], "I found the next step.")
                self.assertEqual(data["steps"][0]["outbox_message"]["text"], "I found the next step.")
                self.assertEqual(data["steps"][0]["outbox_message"]["related_task_id"], 1)
                state = load_state()
                self.assertEqual(state["outbox"][0]["type"], "assistant")
                self.assertEqual(state["work_sessions"][0]["model_turns"][0]["outbox_message_id"], 1)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_ask_user_action_adds_question(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "need direction",
                        "action": {
                            "type": "ask_user",
                            "question": "Which file should I change?",
                        },
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "ask_user")
                self.assertEqual(data["steps"][0]["summary"], "Which file should I change?")
                self.assertEqual(data["steps"][0]["question"]["text"], "Which file should I change?")
                self.assertEqual(data["steps"][0]["question"]["related_task_id"], 1)
                state = load_state()
                self.assertEqual(state["questions"][0]["status"], "open")
                self.assertEqual(state["outbox"][0]["type"], "question")
                self.assertEqual(state["work_sessions"][0]["model_turns"][0]["question_id"], 1)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_remember_action_records_work_note(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "remember observation",
                        "action": {"type": "remember", "note": "config lookup is the likely risk"},
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "remember")
                self.assertEqual(data["steps"][0]["work_note"]["text"], "config lookup is the likely risk")
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["notes"][0]["source"], "model")
                self.assertEqual(session["notes"][0]["text"], "config lookup is the likely risk")
                self.assertEqual(session["model_turns"][0]["work_note"]["text"], "config lookup is the likely risk")
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                self.assertIn("Work notes", stdout.getvalue())
                self.assertIn("config lookup is the likely risk", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_ai_progress_streams_command_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                command = (
                    f"{sys.executable} -c "
                    "\"import sys; print('ai stdout', flush=True); "
                    "print('ai stderr', file=sys.stderr, flush=True)\""
                )
                model_outputs = [
                    {"summary": "run tests", "action": {"type": "run_tests", "command": command}},
                    {"summary": "run tests", "action": {"type": "run_tests", "command": command}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-verify",
                                        "--progress",
                                        "--json",
                                    ]
                                ),
                                0,
                            )
                progress = stderr.getvalue()
                self.assertIn("tool #1 run_tests start", progress)
                self.assertIn("tool #1 stdout: ai stdout", progress)
                self.assertIn("tool #1 stderr: ai stderr", progress)
                self.assertIn("tool #1 completed", progress)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_batch_runs_multiple_read_only_tools_in_one_turn(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("batch content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "collect context",
                        "action": {
                            "type": "batch",
                            "tools": [
                                {"type": "inspect_dir", "path": "."},
                                {"type": "read_file", "path": "README.md"},
                            ],
                        },
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--allow-read", ".", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["steps"][0]["action"]["type"], "batch")
                self.assertEqual([call["tool"] for call in data["steps"][0]["tool_calls"]], ["inspect_dir", "read_file"])
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(len(session["model_turns"]), 1)
                self.assertEqual(session["model_turns"][0]["tool_call_ids"], [1, 2])
                self.assertEqual([call["tool"] for call in session["tool_calls"]], ["inspect_dir", "read_file"])
                self.assertEqual(session["tool_calls"][1]["parameters"]["max_chars"], 12000)
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--details"]), 0)
                self.assertIn("batch tool_calls=#1,#2", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_ai_stops_multi_step_loop_for_pending_write_approval(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("old text\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "preview edit",
                        "action": {
                            "type": "edit_file",
                            "path": "README.md",
                            "old": "old text",
                            "new": "new text",
                        },
                    },
                    {"summary": "should not run", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--allow-write",
                                        ".",
                                        "--max-steps",
                                        "2",
                                        "--act-mode",
                                        "deterministic",
                                        "--json",
                                    ]
                                ),
                                0,
                            )

                report = json.loads(stdout.getvalue())
                self.assertEqual(report["stop_reason"], "pending_approval")
                self.assertEqual(call_model.call_count, 1)
                self.assertEqual(len(report["steps"]), 1)
                state = load_state()
                self.assertEqual(len(state["work_sessions"][0]["tool_calls"]), 1)
                self.assertEqual(Path("README.md").read_text(encoding="utf-8"), "old text\n")
            finally:
                os.chdir(old_cwd)

    def test_work_live_prompt_approval_can_reject_dry_run_write_inline(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("old text\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "preview edit",
                        "action": {
                            "type": "edit_file",
                            "path": "README.md",
                            "old": "old text",
                            "new": "new text",
                        },
                    },
                ]
                verify_command = f"{sys.executable} -c \"print('verify ok')\""
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with patch("sys.stdin", StringIO("n\n")):
                            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                                self.assertEqual(
                                    main(
                                        [
                                            "work",
                                            "1",
                                            "--live",
                                            "--auth",
                                            "auth.json",
                                            "--allow-read",
                                            ".",
                                            "--allow-write",
                                            ".",
                                            "--allow-verify",
                                            "--verify-command",
                                            verify_command,
                                            "--prompt-approval",
                                            "--max-steps",
                                            "1",
                                            "--act-mode",
                                            "deterministic",
                                        ]
                                    ),
                                    0,
                                )

                output = stdout.getvalue()
                self.assertIn("Diff preview (+1 -1)", output)
                self.assertIn("-old text", output)
                self.assertIn("+new text", output)
                self.assertIn(f"Verify on approval: {verify_command}", output)
                self.assertIn("Apply dry-run work tool #1 edit_file", output)
                self.assertIn("README.md? [y/N/q]:", output)
                self.assertIn("rejected work tool #1", output)
                self.assertIn("inline_approval=rejected", output)
                self.assertEqual(Path("README.md").read_text(encoding="utf-8"), "old text\n")
                rejected = load_state()["work_sessions"][0]["tool_calls"][0]
                self.assertEqual(rejected["approval_status"], "rejected")
                self.assertEqual(rejected["rejection_reason"], "inline approval rejected")
            finally:
                os.chdir(old_cwd)

    def test_work_think_prompt_guides_independent_reads_to_batch(self):
        from mew.work_loop import build_work_think_prompt

        prompt = build_work_think_prompt({"work_session": {"tool_calls": []}})
        self.assertIn("Treat guidance as the user's current instruction", prompt)
        self.assertIn("do not finish solely because older notes", prompt)
        self.assertIn("guidance_snapshot", prompt)
        self.assertIn("not current instructions", prompt)
        self.assertIn("capabilities object as current and authoritative", prompt)
        self.assertIn("prefer search_text for symbols or option names before broad read_file", prompt)
        self.assertIn("line_start and line_count", prompt)
        self.assertIn("prefer one batch action", prompt)
        self.assertIn("Do not use run_tests to invoke resident mew loops", prompt)
        self.assertIn("run_command is parsed with shlex and executed without a shell", prompt)
        self.assertIn("include the concrete conclusion in action.summary or action.reason", prompt)
        self.assertIn("Include a compact working_memory object", prompt)
        self.assertIn('"working_memory": {"hypothesis"', prompt)
        self.assertIn('"next_step": "what to do after reentry"', prompt)
        self.assertIn('"type": "batch|inspect_dir', prompt)
        self.assertIn('"summary": "optional concrete result', prompt)
        self.assertIn('"max_chars": "optional read_file cap"', prompt)
        self.assertIn('"line_start": "optional 1-based read_file starting line', prompt)
        self.assertIn('"stat": "optional git_diff diffstat', prompt)

    def test_work_model_rejects_resident_loop_as_verification_command(self):
        from mew.work_loop import normalize_work_model_action

        for command in (
            "mew do 1 --read-only",
            "./mew chat",
            "python -m mew run",
            "uv run mew work 1 --live",
        ):
            action = normalize_work_model_action(
                {"summary": "verify", "action": {"type": "run_tests", "command": command}}
            )
            self.assertEqual(action["type"], "wait", command)
            self.assertIn("resident mew loop", action["reason"])

        action = normalize_work_model_action(
            {"summary": "verify", "action": {"type": "run_tests", "command": "uv run pytest -q"}}
        )
        self.assertEqual(action["type"], "run_tests")
        self.assertEqual(action["command"], "uv run pytest -q")

    def test_work_model_actions_default_to_small_reads_and_diffstat(self):
        from mew.work_loop import normalize_work_model_action, work_tool_parameters_from_action

        read_parameters = work_tool_parameters_from_action({"type": "read_file", "path": "README.md"})
        self.assertEqual(read_parameters["max_chars"], 12000)

        explicit_read_parameters = work_tool_parameters_from_action(
            {"type": "read_file", "path": "README.md", "max_chars": 24000}
        )
        self.assertEqual(explicit_read_parameters["max_chars"], 24000)

        line_action = normalize_work_model_action(
            {"action": {"type": "read_file", "path": "README.md", "start_line": "42", "line_count": "12"}}
        )
        line_parameters = work_tool_parameters_from_action(line_action)
        self.assertEqual(line_parameters["line_start"], 42)
        self.assertEqual(line_parameters["line_count"], 12)

        diff_parameters = work_tool_parameters_from_action({"type": "git_diff"})
        self.assertTrue(diff_parameters["stat"])

        explicit_diff_parameters = work_tool_parameters_from_action({"type": "git_diff", "stat": False})
        self.assertFalse(explicit_diff_parameters["stat"])

    def test_work_model_context_digests_older_tool_calls(self):
        from mew.work_loop import build_work_model_context

        tool_calls = []
        for index in range(1, 19):
            tool_calls.append(
                {
                    "id": index,
                    "tool": "read_file",
                    "status": "completed",
                    "parameters": {"path": f"file{index}.py"},
                    "result": {"path": f"file{index}.py", "text": f"secret content {index}\n", "offset": 0},
                    "summary": f"read file{index}",
                }
            )
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Digest older context.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": tool_calls,
            "model_turns": [],
        }
        task = {"id": 1, "title": "Digest", "description": "Digest older context.", "status": "todo", "kind": "coding"}

        context = build_work_model_context({}, session, task, "now")
        work_context = context["work_session"]
        knowledge_text = json.dumps(work_context["session_knowledge"], ensure_ascii=False)

        self.assertEqual(len(work_context["tool_calls"]), 12)
        self.assertEqual(work_context["tool_calls"][0]["id"], 7)
        self.assertEqual(len(work_context["session_knowledge"]), 6)
        self.assertIn("read_file file6.py", work_context["session_knowledge"][0]["summary"])
        self.assertIn("read_file file1.py", knowledge_text)
        self.assertNotIn("secret content 1", knowledge_text)
        self.assertLess(len(knowledge_text), 3000)

    def test_work_model_context_keeps_recent_task_notes_tail(self):
        from mew.work_loop import build_work_model_context

        old_note = "old recommendation: implement stale command output"
        recent_note = "recent recommendation: improve live reasoning status"
        task = {
            "id": 1,
            "title": "Improve mew",
            "description": "Keep recent notes.",
            "status": "todo",
            "kind": "coding",
            "notes": old_note + "\n" + ("filler line\n" * 3000) + recent_note,
        }
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Keep recent notes.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [],
            "model_turns": [],
        }

        context = build_work_model_context({}, session, task, "now")

        notes = context["task"]["notes"]
        self.assertIn("[...older task notes omitted...]", notes)
        self.assertNotIn(old_note, notes)
        self.assertIn(recent_note, notes)

    def test_work_model_context_clips_recent_read_file_text_with_resume_offset(self):
        from mew.work_loop import WORK_READ_FILE_CONTEXT_TEXT_LIMIT, build_work_model_context

        text = "x" * (WORK_READ_FILE_CONTEXT_TEXT_LIMIT + 100)
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Clip recent read context.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "read_file",
                    "status": "completed",
                    "parameters": {"path": "big.py", "offset": 200},
                    "result": {"path": "big.py", "text": text, "offset": 200, "truncated": False},
                    "summary": "read big file",
                }
            ],
            "model_turns": [],
        }
        task = {"id": 1, "title": "Clip", "description": "Clip recent read context.", "status": "todo", "kind": "coding"}

        context = build_work_model_context({}, session, task, "now")
        result = context["work_session"]["tool_calls"][0]["result"]

        self.assertTrue(result["context_truncated"])
        self.assertFalse(result["source_truncated"])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["visible_chars"], WORK_READ_FILE_CONTEXT_TEXT_LIMIT)
        self.assertEqual(result["source_text_chars"], WORK_READ_FILE_CONTEXT_TEXT_LIMIT + 100)
        self.assertEqual(result["next_offset"], 200 + WORK_READ_FILE_CONTEXT_TEXT_LIMIT)
        self.assertLess(len(result["text"]), len(text))

    def test_work_model_context_under_budget_keeps_recent_window(self):
        from mew.work_loop import build_work_model_context

        tool_calls = [
            {
                "id": index + 1,
                "tool": "read_file",
                "status": "completed",
                "parameters": {"path": f"file{index}.py"},
                "result": {"path": f"file{index}.py", "text": "small\n", "offset": 0},
                "summary": f"read file{index}",
            }
            for index in range(10)
        ]
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Keep normal context.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": tool_calls,
            "model_turns": [],
        }
        task = {"id": 1, "title": "Budget", "description": "Keep normal context.", "status": "todo", "kind": "coding"}

        work_context = build_work_model_context({}, session, task, "now")["work_session"]

        self.assertNotIn("context_compaction", work_context)
        self.assertEqual(len(work_context["tool_calls"]), 10)
        self.assertEqual(work_context["tool_calls"][0]["id"], 1)

    def test_work_model_context_over_budget_compacts_recent_window(self):
        from mew.work_loop import WORK_CONTEXT_BUDGET, build_work_model_context

        text = "x" * 50000
        tool_calls = [
            {
                "id": index + 1,
                "tool": "read_file",
                "status": "completed",
                "parameters": {"path": f"file{index}.py"},
                "result": {"path": f"file{index}.py", "text": text, "offset": 0},
                "summary": f"read file{index}",
            }
            for index in range(60)
        ]
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Compact long context.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": tool_calls,
            "model_turns": [],
        }
        task = {"id": 1, "title": "Budget", "description": "Compact long context.", "status": "todo", "kind": "coding"}

        work_context = build_work_model_context({}, session, task, "now")["work_session"]

        self.assertTrue(work_context["context_compaction"]["compacted"])
        self.assertLess(len(work_context["tool_calls"]), 12)
        self.assertEqual(work_context["tool_calls"][-1]["id"], 60)
        self.assertIn("read_file file51.py", json.dumps(work_context["session_knowledge"], ensure_ascii=False))
        self.assertLessEqual(len(json.dumps(work_context, ensure_ascii=False)), WORK_CONTEXT_BUDGET)

    def test_work_model_context_clips_large_search_matches(self):
        from mew.work_loop import WORK_CONTEXT_BUDGET, build_work_model_context

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Clip large search result.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "search_text",
                    "status": "completed",
                    "parameters": {"path": ".", "query": "needle"},
                    "result": {"path": ".", "query": "needle", "matches": ["x" * 200000], "truncated": False},
                    "summary": "large search",
                }
            ],
            "model_turns": [],
        }
        task = {"id": 1, "title": "Search", "description": "Clip large search result.", "status": "todo", "kind": "coding"}

        work_context = build_work_model_context({}, session, task, "now")["work_session"]
        match = work_context["tool_calls"][0]["result"]["matches"][0]

        self.assertLess(len(match), 200000)
        self.assertIn("output truncated", match)
        self.assertLessEqual(len(json.dumps(work_context, ensure_ascii=False)), WORK_CONTEXT_BUDGET)

    def test_work_model_context_includes_search_snippets(self):
        from mew.work_loop import build_work_model_context

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "goal": "Use search context.",
            "created_at": "then",
            "updated_at": "now",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "search_text",
                    "status": "completed",
                    "parameters": {"path": ".", "query": "needle"},
                    "result": {
                        "path": ".",
                        "query": "needle",
                        "matches": ["README.md:2:needle"],
                        "snippets": [
                            {
                                "path": "README.md",
                                "line": 2,
                                "start_line": 1,
                                "end_line": 3,
                                "lines": [
                                    {"line": 1, "text": "before", "match": False},
                                    {"line": 2, "text": "needle", "match": True},
                                    {"line": 3, "text": "after", "match": False},
                                ],
                            }
                        ],
                    },
                    "summary": "search with snippet",
                }
            ],
            "model_turns": [],
        }
        task = {"id": 1, "title": "Search", "description": "Use search context.", "status": "todo", "kind": "coding"}

        work_context = build_work_model_context({}, session, task, "now")["work_session"]

        snippets = work_context["tool_calls"][0]["result"]["snippets"]
        self.assertEqual(snippets[0]["lines"][1]["text"], "needle")

    def test_work_model_context_includes_bounded_world_state_when_read_allowed(self):
        from mew.work_loop import build_work_model_context

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                for index in range(10):
                    Path(f"file{index}.py").write_text(f"print({index})\n", encoding="utf-8")
                tool_calls = [
                    {
                        "id": index + 1,
                        "tool": "read_file",
                        "status": "completed",
                        "parameters": {"path": f"file{index}.py"},
                        "result": {"path": f"file{index}.py", "text": f"print({index})\n", "offset": 0},
                        "summary": f"read file{index}",
                    }
                    for index in range(10)
                ]
                session = {
                    "id": 1,
                    "task_id": 1,
                    "status": "active",
                    "goal": "Revalidate live files.",
                    "created_at": "then",
                    "updated_at": "now",
                    "tool_calls": tool_calls,
                    "model_turns": [],
                }
                task = {
                    "id": 1,
                    "title": "World",
                    "description": "Revalidate live files.",
                    "status": "todo",
                    "kind": "coding",
                }

                context = build_work_model_context({}, session, task, "now", allowed_read_roots=["."])
                world = context["work_session"]["world_state"]

                self.assertIn("exit_code", world["git_status"])
                self.assertEqual(len(world["files"]), 8)
                self.assertEqual(world["files"][0]["path"], "file2.py")
                self.assertEqual(world["files"][-1]["path"], "file9.py")
                self.assertTrue(world["files"][0]["exists"])
                self.assertEqual(world["files"][0]["type"], "file")
                self.assertNotIn("print(9)", json.dumps(world, ensure_ascii=False))
            finally:
                os.chdir(old_cwd)

    def test_work_ai_batch_skips_read_tools_without_required_parameters(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "collect context",
                        "action": {
                            "type": "batch",
                            "tools": [
                                {"type": "inspect_dir", "path": "."},
                                {"type": "read_file"},
                            ],
                        },
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--allow-read", ".", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertEqual([call["tool"] for call in data["steps"][0]["tool_calls"]], ["inspect_dir"])
                self.assertEqual(load_state()["work_sessions"][0]["model_turns"][0]["tool_call_ids"], [1])
            finally:
                os.chdir(old_cwd)

    def test_work_live_prints_resume_after_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("live content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_calls = []

                def fake_model(
                    model_backend,
                    model_auth,
                    prompt,
                    model,
                    base_url,
                    timeout,
                    log_prefix=None,
                    on_text_delta=None,
                ):
                    model_calls.append(prompt)
                    if on_text_delta:
                        on_text_delta("raw model json delta")
                    return {
                        "summary": "read README",
                        "action": {"type": "read_file", "path": "README.md"},
                    }

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                    ]
                                ),
                                0,
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 thinking", output)
                self.assertIn("progress: step=1/1 session=#1 task=#1", output)
                self.assertIn("phase=thinking", output)
                self.assertIn("elapsed=", output)
                self.assertIn("summary: read README", output)
                self.assertIn("planned_action: read_file", output)
                self.assertIn("Work live step #1 action", output)
                self.assertIn("action: read_file", output)
                self.assertIn("tool_call: #1", output)
                self.assertIn("reason: read README", output)
                self.assertIn("path: README.md", output)
                self.assertIn("Work live step #1 result", output)
                self.assertIn("outcome:", output)
                self.assertIn("tools:", output)
                self.assertIn("session:", output)
                self.assertIn("tool #1 [completed] read_file", output)
                result_block = output.split("Work live step #1 result", 1)[1].split("Work live step #1 resume", 1)[0]
                self.assertIn("summary: Read file", result_block)
                self.assertNotIn("live content", result_block)
                self.assertNotIn("live content", output)
                self.assertIn("phase: idle", output)
                self.assertIn("context: pressure=low", output)
                self.assertIn("Work live step #1 resume", output)
                self.assertLess(output.index("Work live step #1 thinking"), output.index("Work live step #1 action"))
                self.assertLess(output.index("Work live step #1 action"), output.index("Work live step #1 result"))
                self.assertLess(output.index("Work live step #1 result"), output.index("Work live step #1 resume"))
                self.assertIn("Work resume #1 [active] task=#1", output)
                self.assertIn("mew work ai: 1/1 step(s) stop=max_steps", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew work 1 --live", output)
                self.assertIn("mew work 1 --session --resume --allow-read .", output)
                self.assertEqual(len(model_calls), 1)
                self.assertIn("ACT deterministic action=read_file", stderr.getvalue())
                self.assertNotIn("raw model json delta", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_live_without_tool_gates_preflights_before_model_call(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries") as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(main(["work", "1", "--live", "--auth", "auth.json"]), 1)

                call_model.assert_not_called()
                output = stdout.getvalue()
                self.assertIn("stop=missing_gates", output)
                self.assertIn("No work tool gates are enabled", output)
                self.assertIn("mew work 1 --live --auth auth.json --model-backend codex --allow-read .", output)
                self.assertIn("skipping model call", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_live_compact_skips_per_step_resume(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("compact content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_output = {
                    "summary": "read README",
                    "action": {"type": "read_file", "path": "README.md"},
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--compact-live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertIn("Work live step #1 thinking", output)
                self.assertIn("progress: step=1/1 session=#1 task=#1", output)
                self.assertIn("Work live step #1 result", output)
                self.assertNotIn("Work live step #1 resume", output)
                self.assertNotIn("Work resume #1", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("--compact-live", output)
            finally:
                os.chdir(old_cwd)

    def test_work_live_compact_report_omits_command_output_reprint(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                command = f"{sys.executable} -c \"import sys; print('compact stdout'); print('compact stderr', file=sys.stderr)\""
                model_output = {
                    "summary": "run command",
                    "action": {"type": "run_command", "command": command, "reason": "inspect command output"},
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--compact-live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-shell",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                result_block = output.split("Work live step #1 result", 1)[1].split(
                    "mew work ai: 1/1 step(s)",
                    1,
                )[0]
                report_block = output.split("mew work ai: 1/1 step(s)", 1)[1]
                self.assertIn("  compact stdout", result_block)
                self.assertIn("  compact stderr", result_block)
                self.assertNotIn("stdout:", report_block)
                self.assertNotIn("stderr:", report_block)
            finally:
                os.chdir(old_cwd)

    def test_work_live_prints_resume_after_finish(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "done", "action": {"type": "finish", "reason": "finished live"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 thinking", output)
                self.assertIn("planned_action: finish", output)
                self.assertIn("Work live step #1 action", output)
                self.assertIn("action: finish", output)
                self.assertIn("Work live step #1 result", output)
                self.assertIn("status: completed", output)
                self.assertIn("phase: closed", output)
                self.assertIn("Work live step #1 resume", output)
                self.assertIn("Work resume #1 [closed] task=#1", output)
                self.assertIn("phase: closed", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew work 1 --session --resume", output)
                self.assertIn("Work session finished: finished live", load_state()["tasks"][0]["notes"])
                self.assertEqual(load_state()["tasks"][0]["status"], "todo")
            finally:
                os.chdir(old_cwd)

    def test_work_live_result_pane_shows_command_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                command = f"{sys.executable} -c \"import sys; print('live stdout'); print('live stderr', file=sys.stderr)\""
                model_output = {
                    "summary": "run command",
                    "action": {"type": "run_command", "command": command, "reason": "inspect command output"},
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-shell",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertIn("Work live step #1 result", output)
                self.assertIn("tool #1 [completed] run_command exit=0", output)
                result_block = output.split("Work live step #1 result", 1)[1].split("Work live step #1 resume", 1)[0]
                self.assertIn("tools:", result_block)
                self.assertNotIn("summary: command:", result_block)
                self.assertIn("cwd:", result_block)
                self.assertIn("stdout:", result_block)
                self.assertEqual(result_block.count("  live stdout"), 1)
                self.assertIn("stderr:", result_block)
                self.assertEqual(result_block.count("  live stderr"), 1)
            finally:
                os.chdir(old_cwd)

    def test_work_live_result_pane_shows_search_matches(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("alpha needle\nbeta\nneedle gamma\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_output = {
                    "summary": "search README",
                    "action": {"type": "search_text", "path": ".", "query": "needle"},
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                result_block = output.split("Work live step #1 result", 1)[1].split("Work live step #1 resume", 1)[0]
                self.assertIn("tool #1 [completed] search_text", result_block)
                self.assertIn("snippets:", result_block)
                self.assertIn("> 1: alpha needle", result_block)
                self.assertIn("  2: beta", result_block)
                self.assertIn("> 3: needle gamma", result_block)
            finally:
                os.chdir(old_cwd)

    def test_work_finish_can_mark_task_done_when_requested(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {
                        "summary": "done",
                        "action": {
                            "type": "finish",
                            "reason": "implemented and verified",
                            "task_done": True,
                            "completion_summary": "resident completed the task",
                        },
                    },
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                self.assertIn("action: finish", stdout.getvalue())
                state = load_state()
                task = state["tasks"][0]
                self.assertEqual(task["status"], "done")
                self.assertIn("Work session finished: implemented and verified", task["notes"])
                self.assertIn("done: resident completed the task", task["notes"])
                self.assertEqual(
                    state["memory"]["shallow"]["latest_task_summary"],
                    "Task #1 completed: Build native hands. resident completed the task",
                )
            finally:
                os.chdir(old_cwd)

    def test_work_finish_note_prefers_summary_over_reason(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_output = {
                    "summary": "outer summary",
                    "action": {
                        "type": "finish",
                        "summary": "useful conclusion for reentry",
                        "reason": "stopping because this is the final follow step",
                    },
                }
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                notes = load_state()["tasks"][0]["notes"]
                self.assertIn("Work session finished: useful conclusion for reentry", notes)
                self.assertNotIn("Work session finished: stopping because this is the final follow step", notes)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_feeds_tool_result_into_next_model_turn(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello second turn\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None):
                    prompts.append(prompt)
                    if len(prompts) <= 2:
                        return {
                            "summary": "read README",
                            "analysis_notes": "remember that README content is the evidence source",
                            "action": {"type": "read_file", "path": "README.md"},
                        }
                    return {"summary": "enough context", "action": {"type": "finish", "reason": "read result observed"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--max-steps",
                                        "2",
                                        "--json",
                                    ]
                                ),
                                0,
                            )

                data = json.loads(stdout.getvalue())
                self.assertEqual(data["stop_reason"], "finish")
                self.assertEqual(len(data["steps"]), 2)
                self.assertIn("hello second turn", prompts[2])
                self.assertIn("README content is the evidence source", prompts[2])
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["status"], "closed")
                self.assertEqual([turn["status"] for turn in session["model_turns"]], ["completed", "completed"])
                self.assertEqual(session["model_turns"][-1]["finished_note"], "read result observed")
                self.assertEqual([call["tool"] for call in session["tool_calls"]], ["read_file"])
                self.assertIn("Work session finished: read result observed", state["tasks"][0]["notes"])
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                resume_text = stdout.getvalue()
                self.assertIn("Work resume #1 [closed] task=#1", resume_text)
                self.assertIn("read result observed", resume_text)
                self.assertIn("review this closed work session", resume_text)
            finally:
                os.chdir(old_cwd)

    def test_work_ai_resumes_existing_session_across_invocations(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("resume content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                first_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=first_outputs):
                        with redirect_stdout(StringIO()):
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--allow-read", ".", "--json"]),
                                0,
                            )

                resumed_prompts = []

                def fake_resume(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None):
                    resumed_prompts.append(prompt)
                    return {
                        "summary": "resume complete",
                        "action": {"type": "finish", "reason": "previous read is visible"},
                    }

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_resume):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "1", "--ai", "--auth", "auth.json", "--allow-read", ".", "--json"]),
                                0,
                            )

                data = json.loads(stdout.getvalue())
                self.assertFalse(data["created"])
                self.assertEqual(data["stop_reason"], "finish")
                self.assertIn("resume content", resumed_prompts[0])
                state = load_state()
                self.assertEqual(len(state["work_sessions"]), 1)
                session = state["work_sessions"][0]
                self.assertEqual(session["status"], "closed")
                self.assertEqual(len(session["model_turns"]), 2)
                self.assertEqual(len(session["tool_calls"]), 1)
                self.assertIn("Work session finished: previous read is visible", state["tasks"][0]["notes"])
            finally:
                os.chdir(old_cwd)

    def test_work_ai_without_task_id_prefers_active_work_session(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("active.md").write_text("active session content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    second = dict(state["tasks"][0])
                    second["id"] = 2
                    second["title"] = "Active session task"
                    second["description"] = "Continue this active session."
                    state["tasks"].append(second)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "2", "--start-session"]), 0)

                model_outputs = [
                    {"summary": "read active", "action": {"type": "read_file", "path": "active.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout:
                            self.assertEqual(
                                main(["work", "--ai", "--auth", "auth.json", "--allow-read", ".", "--act-mode", "deterministic", "--json"]),
                                0,
                            )
                data = json.loads(stdout.getvalue())
                self.assertFalse(data["created"])
                self.assertEqual(data["task_id"], 2)
                self.assertEqual(data["session_id"], 1)
                self.assertEqual(data["steps"][0]["tool_call"]["task_id"], 2)
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_can_start_and_show_session(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session start 1", {}), "continue")
                self.assertIn("created work session #1", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session", {}), "continue")
                self.assertIn("Work session #1 [active] task=#1", stdout.getvalue())
                self.assertIn("phase: idle", stdout.getvalue())
                self.assertIn("Next controls", stdout.getvalue())
                self.assertIn("Primary", stdout.getvalue())
                self.assertIn("Inspect", stdout.getvalue())
                self.assertIn("Manage", stdout.getvalue())
                self.assertIn("/continue --allow-read .", stdout.getvalue())
                self.assertIn("/c --allow-read .", stdout.getvalue())
                self.assertIn("/follow --allow-read . --max-steps 10", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_inspect_controls_reuse_read_defaults(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("sample").mkdir()
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "sample"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session", {}), "continue")

                output = stdout.getvalue()
                self.assertIn("- /work-session resume --allow-read sample", output)
                self.assertIn("- /work-session recover --allow-read sample", output)
                self.assertNotIn("- /work-session resume --allow-read .", output)
                self.assertNotIn("- /work-session recover --allow-read .", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_resume_controls_reuse_explicit_read_root(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("sample").mkdir()
                Path("sample/README.md").write_text("scoped\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", "sample/README.md", "--allow-read", "sample"]), 0)

                chat_state = {}
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        run_chat_slash_command("/work-session resume 1 --allow-read sample", chat_state),
                        "continue",
                    )

                output = stdout.getvalue()
                self.assertIn("- /c --allow-read sample", output)
                self.assertIn("- /work-session resume --allow-read sample", output)
                self.assertIn("- /work-session live --allow-read sample --max-steps 3", output)
                self.assertIn("- /work-session recover --allow-read sample", output)
                self.assertNotIn("- /c --allow-read .", output)
                self.assertEqual(chat_state["work_continue_options"], "--allow-read sample")
            finally:
                os.chdir(old_cwd)

    def test_workbench_surfaces_work_session_reentry_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    task = add_coding_task(state)
                    task["notes"] = "\n".join(
                        [
                            "older note",
                            "Work session finished: stale closure",
                            "Work session finished: duplicate closure",
                            "Work session finished: latest closure",
                        ]
                    )
                    state["work_sessions"] = [
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Build native hands",
                            "goal": "Make the front door useful.",
                            "created_at": "then",
                            "updated_at": "now",
                            "notes": [
                                {
                                    "created_at": "now",
                                    "source": "system",
                                    "text": "Follow reached max_steps=1 after 1 step(s). Last action: glob. Resume with /c.",
                                },
                                {"created_at": "now", "source": "user", "text": "Use the workbench first."},
                                {"created_at": "now", "source": "model", "text": "Resume from the latest evidence."},
                            ],
                            "tool_calls": [
                                {
                                    "id": 1,
                                    "tool": "run_tests",
                                    "status": "failed",
                                    "parameters": {"command": "uv run pytest -q"},
                                    "result": {"command": "uv run pytest -q", "exit_code": 1, "stderr": "same failure\n"},
                                    "error": "verification failed with exit_code=1",
                                },
                                {
                                    "id": 2,
                                    "tool": "run_tests",
                                    "status": "failed",
                                    "parameters": {"command": "uv run pytest -q"},
                                    "result": {"command": "uv run pytest -q", "exit_code": 1, "stderr": "same failure\n"},
                                    "error": "verification failed with exit_code=1",
                                },
                            ],
                            "model_turns": [
                                {
                                    "id": 1,
                                    "session_id": 1,
                                    "task_id": 1,
                                    "status": "completed",
                                    "decision_plan": {
                                        "summary": "remember",
                                        "working_memory": {
                                            "hypothesis": "The workbench should be enough to reenter.",
                                            "next_step": "Continue from the workbench without hunting through details.",
                                            "open_questions": ["Does the front door show notes?"],
                                            "last_verified_state": "not yet verified",
                                        },
                                    },
                                    "action_plan": {"summary": "remember"},
                                    "action": {"type": "remember", "note": "front door context"},
                                    "summary": "recorded reentry guidance",
                                    "guidance_snapshot": "Keep this visible on reentry.",
                                    "started_at": "then",
                                    "finished_at": "now",
                                }
                            ],
                        }
                    ]
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1"]), 0)
                output = stdout.getvalue()
                self.assertIn("Reentry", output)
                self.assertIn("hypothesis: The workbench should be enough to reenter.", output)
                self.assertIn("next_step: Continue from the workbench without hunting through details.", output)
                self.assertIn("note[user]: Use the workbench first.", output)
                self.assertIn("note[model]: Resume from the latest evidence.", output)
                self.assertNotIn("note[system]: Follow reached max_steps", output)
                self.assertIn("repeat: run_tests uv run pytest -q failed 2x", output)
                self.assertIn("latest_decision: #1 remember recorded reentry guidance", output)
                self.assertIn("guidance: Keep this visible on reentry.", output)
                self.assertIn("[...2 older work-session finish notes omitted...]", output)
                self.assertNotIn("Work session finished: stale closure", output)
                self.assertNotIn("Work session finished: duplicate closure", output)
                self.assertIn("Work session finished: latest closure", output)
                self.assertIn("resume:", output)
                self.assertIn("chat: /work-session resume 1", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_timeline_surfaces_model_and_tool_events(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("timeline content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read timeline file", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--ai",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                        "--json",
                                    ]
                                ),
                                0,
                            )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--timeline"]), 0)
                output = stdout.getvalue()
                self.assertIn("Work timeline #1 [active] task=#1", output)
                self.assertIn("model#1 [completed] read_file tool_call=#1", output)
                self.assertIn("tool#1 [completed] read_file", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--timeline", "--json"]), 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["timeline"][0]["kind"], "model_turn")
                self.assertEqual(payload["timeline"][1]["kind"], "tool_call")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session timeline", {}), "continue")
                self.assertIn("Work timeline #1 [active] task=#1", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_work_session_timeline_keeps_events_one_line(self):
        from mew.work_session import build_work_session_timeline

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "model_turns": [],
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "git_status",
                    "status": "completed",
                    "started_at": "now",
                    "result": {"command": "git status --short", "cwd": ".", "exit_code": 0, "stdout": " M a.py\n"},
                }
            ],
        }

        timeline = build_work_session_timeline(session)

        self.assertEqual(len(timeline), 1)
        self.assertNotIn("\n", timeline[0]["summary"])
        self.assertIn("git status --short", timeline[0]["summary"])

    def test_work_session_timeline_honors_non_positive_limit(self):
        from mew.work_session import build_work_session_timeline

        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "model_turns": [],
            "tool_calls": [
                {"id": 1, "tool": "read_file", "status": "completed", "started_at": "now", "result": {"path": "a.md"}}
            ],
        }

        self.assertEqual(build_work_session_timeline(session, limit=0), [])
        self.assertEqual(build_work_session_timeline(session, limit=-1), [])

    def test_chat_work_session_show_without_active_lists_recent_sessions(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session", {}), "continue")
                output = stdout.getvalue()

                self.assertIn("No active work session.", output)
                self.assertIn("Recent work sessions", output)
                self.assertIn("resume: mew work 1 --session --resume", output)
                self.assertIn("chat: /work-session resume 1", output)
                self.assertIn("mew work <task-id> --start-session", output)
                self.assertIn("/work-session start <task-id>", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session resume --allow-read .", {}), "continue")
                output = stdout.getvalue()
                self.assertIn("No active work session.", output)
                self.assertIn("Recent work sessions", output)
                self.assertIn("chat: /work-session resume 1", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_accepts_task_first_resume_order(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("resume me\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", "README.md", "--allow-read", "."]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session 1 resume --allow-read .", {}), "continue")
                output = stdout.getvalue()

                self.assertIn("Work resume #1 [closed] task=#1", output)
                self.assertIn("World state", output)
                self.assertIn("README.md", output)
                self.assertIn("Next controls", output)
                self.assertIn("/work-session resume 1", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_startup_surfaces_active_work_session_controls(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                stdin = StringIO("/exit\n")
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    self.assertEqual(main(["chat", "--no-unread", "--no-activity"]), 0)
                output = stdout.getvalue()

                self.assertIn("mew chat. Type /help", output)
                self.assertIn("Next controls", output)
                self.assertIn("/continue --allow-read .", output)
                self.assertIn("/work-session live --allow-read . --max-steps 3", output)
                self.assertIn("/work-session resume", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_startup_surfaces_active_controls_even_without_brief(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                stdin = StringIO("/exit\n")
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    self.assertEqual(main(["chat", "--no-brief", "--no-unread", "--no-activity"]), 0)
                output = stdout.getvalue()

                self.assertNotIn("Mew focus", output)
                self.assertIn("Next controls", output)
                self.assertIn("/continue --allow-read .", output)
            finally:
                os.chdir(old_cwd)

    def test_scripted_chat_defers_startup_controls_to_scoped_work_command(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("sample").mkdir()
                Path("sample/README.md").write_text("scoped startup\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", "sample/README.md", "--allow-read", "sample"]), 0)

                stdin = StringIO("/work-session resume 1 --allow-read sample\n/exit\n")
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    self.assertEqual(main(["chat", "--no-brief", "--no-unread", "--no-activity"]), 0)
                output = stdout.getvalue()

                self.assertEqual(output.count("Next controls"), 1)
                self.assertIn("- /c --allow-read sample", output)
                self.assertIn("- /work-session resume --allow-read sample", output)
                self.assertNotIn("- /c --allow-read .", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_reentry_controls_reuse_live_options(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("remember gates\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--allow-write",
                                        ".",
                                        "--allow-verify",
                                        "--verify-command",
                                        "uv run pytest -q",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--allow-read .", output)
                self.assertIn("--allow-write .", output)
                self.assertIn("--allow-verify", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
                self.assertIn("--act-mode deterministic", output)

                stdin = StringIO("/exit\n")
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    self.assertEqual(main(["chat", "--no-brief", "--no-unread", "--no-activity"]), 0)
                output = stdout.getvalue()
                self.assertIn("/work-session live --auth auth.json", output)
                self.assertIn("--allow-write .", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
                self.assertIn("--max-steps 3", output)
            finally:
                os.chdir(old_cwd)

    def test_work_live_current_tool_gates_override_saved_defaults_in_next_controls(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("read-only controls\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "seed broad gates", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "read with narrow gates", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--allow-write",
                                        ".",
                                        "--allow-shell",
                                        "--allow-verify",
                                        "--verify-command",
                                        "uv run pytest -q",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--compact-live",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )
                output = stdout.getvalue()
                self.assertIn("Next CLI controls", output)
                controls_block = output.split("Next CLI controls", 1)[1]
                self.assertIn("--allow-read .", controls_block)
                self.assertNotIn("--allow-write .", controls_block)
                self.assertNotIn("--allow-shell", controls_block)
                self.assertNotIn("--allow-verify", controls_block)
                self.assertNotIn("--verify-command", controls_block)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--allow-write .", output)
                self.assertIn("--allow-shell", output)
                self.assertIn("--allow-verify", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_start_can_seed_reentry_options(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--start-session",
                                "--allow-read",
                                ".",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                "uv run pytest -q",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--allow-read .", output)
                self.assertIn("--allow-write .", output)
                self.assertIn("--allow-verify", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--allow-write .", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_reentry_options_preserve_existing_gates_when_partially_updated(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("src").mkdir()
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--start-session",
                                "--auth",
                                "custom-auth.json",
                                "--model-backend",
                                "openai",
                                "--model",
                                "gpt-test",
                                "--base-url",
                                "http://127.0.0.1:9999",
                                "--allow-read",
                                ".",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                "uv run pytest -q",
                                "--act-mode",
                                "deterministic",
                                "--prompt-approval",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "src"]), 0)

                defaults = load_state()["work_sessions"][0]["default_options"]
                self.assertEqual(defaults["auth"], "custom-auth.json")
                self.assertEqual(defaults["model_backend"], "openai")
                self.assertEqual(defaults["model"], "gpt-test")
                self.assertEqual(defaults["base_url"], "http://127.0.0.1:9999")
                self.assertEqual(defaults["allow_read"], [".", "src"])
                self.assertEqual(defaults["allow_write"], ["."])
                self.assertTrue(defaults["allow_verify"])
                self.assertEqual(defaults["verify_command"], "uv run pytest -q")
                self.assertEqual(defaults["act_mode"], "deterministic")
                self.assertTrue(defaults["prompt_approval"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--auth custom-auth.json", output)
                self.assertIn("--model-backend openai", output)
                self.assertIn("--model gpt-test", output)
                self.assertIn("--base-url http://127.0.0.1:9999", output)
                self.assertIn("--allow-read . --allow-read src", output)
                self.assertIn("--allow-write .", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
                self.assertIn("--act-mode deterministic", output)
                self.assertIn("--prompt-approval", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_reentry_options_preserve_no_prompt_approval(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["work", "1", "--start-session", "--allow-read", ".", "--prompt-approval"]),
                        0,
                    )
                    self.assertEqual(main(["work", "1", "--start-session", "--no-prompt-approval"]), 0)

                defaults = load_state()["work_sessions"][0]["default_options"]
                self.assertTrue(defaults["no_prompt_approval"])
                self.assertFalse(defaults["prompt_approval"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--no-prompt-approval", output)
                self.assertNotIn("--prompt-approval", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_restart_from_closed_session_preserves_defaults(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--start-session",
                                "--allow-read",
                                ".",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                "uv run pytest -q",
                                "--act-mode",
                                "deterministic",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(main(["work", "1", "--close-session"]), 0)
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                state = load_state()
                self.assertEqual(len(state["work_sessions"]), 2)
                self.assertEqual(state["work_sessions"][0]["status"], "closed")
                defaults = state["work_sessions"][1]["default_options"]
                self.assertEqual(defaults["allow_read"], ["."])
                self.assertEqual(defaults["allow_write"], ["."])
                self.assertTrue(defaults["allow_verify"])
                self.assertEqual(defaults["verify_command"], "uv run pytest -q")
                self.assertEqual(defaults["act_mode"], "deterministic")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn("--allow-write .", output)
                self.assertIn("--verify-command 'uv run pytest -q'", output)
                self.assertIn("--act-mode deterministic", output)
            finally:
                os.chdir(old_cwd)

    def test_work_session_world_state_hides_mew_internal_git_noise(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, capture_output=True, text=True)
                Path("README.md").write_text("world state\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                    self.assertEqual(main(["work", "1", "--tool", "read_file", "--path", "README.md", "--allow-read", "."]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", "."]), 0)
                output = stdout.getvalue()
                self.assertIn("git_status exit=0", output)
                self.assertIn("README.md", output)
                self.assertNotIn(".mew", output)
            finally:
                os.chdir(old_cwd)

    def test_work_world_state_snapshots_allowed_root_before_files_touched(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("scratch world\n", encoding="utf-8")
                Path("sample").mkdir()
                Path("sample/app.py").write_text("print('hi')\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", "."]), 0)
                output = stdout.getvalue()
                self.assertIn("git_status exit=128", output)
                self.assertIn("README.md", output)
                self.assertIn("sample", output)
                self.assertNotIn("(no files)", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", ".", "--json"]), 0)
                files = json.loads(stdout.getvalue())["resume"]["world_state"]["files"]
                self.assertEqual(files[0]["source"], "workspace_snapshot")
                self.assertTrue(any(item["path"] == "README.md" for item in files))
                self.assertTrue(any(item["path"] == "sample" for item in files))
            finally:
                os.chdir(old_cwd)

    def test_work_world_state_uses_allowed_read_root_for_git_status(self):
        from mew.work_world import build_work_world_state

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            outside = Path(tmp) / "outside"
            repo.mkdir()
            outside.mkdir()
            subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True, text=True)
            (repo / "README.md").write_text("world root\n", encoding="utf-8")
            os.chdir(outside)
            try:
                world = build_work_world_state(
                    {"files_touched": [str(repo / "README.md")]},
                    [str(repo)],
                )

                self.assertEqual(world["git_status"]["exit_code"], 0)
                self.assertEqual(Path(world["git_status"]["cwd"]), repo.resolve())
                self.assertEqual(world["files"][0]["path"], str(repo / "README.md"))
                self.assertTrue(world["files"][0]["exists"])
            finally:
                os.chdir(old_cwd)

    def test_successful_run_tests_refreshes_session_verify_default(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                stale_command = "python -m pytest -q"
                command = f"{sys.executable} -c \"print('ok')\""
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--start-session",
                                "--allow-read",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                stale_command,
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(["work", "1", "--tool", "run_tests", "--command", command, "--allow-verify"]),
                        0,
                    )

                state = load_state()
                defaults = state["work_sessions"][0]["default_options"]
                self.assertEqual(defaults["verify_command"], command)
                self.assertTrue(defaults["allow_verify"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session"]), 0)
                output = stdout.getvalue()
                self.assertIn(f"--verify-command {shlex.quote(command)}", output)
                self.assertNotIn(shlex.quote(stale_command), output)
            finally:
                os.chdir(old_cwd)

    def test_chat_continue_uses_persisted_session_options_after_reentry(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("fresh continue\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "."]), 0)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    prompts.append(prompt)
                    return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(run_chat_slash_command("/continue inspect README after reentry", {}), "continue")

                output = stdout.getvalue()
                self.assertIn("Work live step #1 action", output)
                self.assertIn("fresh continue", load_state()["work_sessions"][0]["tool_calls"][0]["result"]["text"])
                self.assertIn("inspect README after reentry", prompts[0])
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_can_run_ai_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("chat ai content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/work-session ai 1 --auth auth.json --allow-read . --max-steps 1 --act-mode deterministic",
                                    {},
                                ),
                                "continue",
                            )
                self.assertEqual(call_model.call_count, 1)
                output = stdout.getvalue()
                self.assertIn("mew work ai: 1/1 step(s) stop=max_steps", output)
                self.assertIn("#1 [completed] read_file tool_call=#1", output)
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["tool"], "read_file")
                self.assertIn("chat ai content", session["tool_calls"][0]["result"]["text"])
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_live_alias_runs_live_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("chat live content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/work-session live 1 --auth auth.json --allow-read . --max-steps 1 --act-mode deterministic",
                                    {},
                                ),
                                "continue",
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 action", output)
                self.assertIn("Work live step #1 result", output)
                self.assertIn("Work live step #1 resume", output)
                self.assertIn("tool #1 [completed] read_file", output)
                self.assertIn("action: read_file", output)
                self.assertIn("Next controls", output)
                self.assertIn("/continue <guidance>", output)
                self.assertNotIn("Next CLI controls", output)
                self.assertIn("chat live content", load_state()["work_sessions"][0]["tool_calls"][0]["result"]["text"])
                self.assertIn("THINK start", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_chat_continue_runs_active_work_session_live_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("continue content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/continue --auth auth.json --allow-read . --act-mode deterministic",
                                    {},
                                ),
                                "continue",
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 action", output)
                self.assertIn("Work live step #1 result", output)
                self.assertIn("action: read_file", output)
                self.assertIn("Next controls", output)
                self.assertIn("/help work for details", output)
                self.assertNotIn("Advanced", output)
                self.assertNotIn("/work-session tests", output)
                self.assertIn("continue content", load_state()["work_sessions"][0]["tool_calls"][0]["result"]["text"])
            finally:
                os.chdir(old_cwd)

    def test_chat_continue_reuses_options_and_treats_plain_text_as_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("guided continue content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    prompts.append(prompt)
                    if len(prompts) == 1:
                        return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}
                    return {"summary": "done", "action": {"type": "finish", "reason": "guidance followed"}}

                chat_state = {}
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/continue --auth auth.json --allow-read . --act-mode deterministic --prompt-approval",
                                    chat_state,
                                ),
                                "continue",
                            )
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/continue focus on the README summary",
                                    chat_state,
                                ),
                                "continue",
                            )
                output = stdout.getvalue()
                self.assertEqual(
                    chat_state["work_continue_options"],
                    "--auth auth.json --allow-read . --act-mode deterministic --prompt-approval",
                )
                self.assertIn("focus on the README summary", prompts[-1])
                self.assertIn("Next controls", output)
                self.assertIn("/c --auth auth.json --allow-read . --act-mode deterministic --prompt-approval", output)
                self.assertIn("/continue <guidance>", output)
                self.assertIn("--prompt-approval", output)
                self.assertIn("/work-session resume 1", output)
                self.assertIn("Work session finished: guidance followed", load_state()["tasks"][0]["notes"])
            finally:
                os.chdir(old_cwd)

    def test_chat_continue_does_not_cache_failed_live_options(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command
                from mew.errors import MewError

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "."]), 0)

                chat_state = {"work_continue_options": "--allow-read ."}
                with patch("mew.commands.load_model_auth", side_effect=MewError("auth file not found: bad.json")):
                    with patch("mew.work_loop.call_model_json_with_retries") as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                run_chat_slash_command("/continue --auth bad.json --allow-read .", chat_state),
                                "continue",
                            )

                call_model.assert_not_called()
                self.assertEqual(chat_state["work_continue_options"], "--allow-read .")
                output = stdout.getvalue()
                self.assertIn("Next controls", output)
                self.assertIn("/c --allow-read .", output)
                self.assertNotIn("bad.json", output)
                self.assertIn("auth file not found: bad.json", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_chat_continue_accepts_options_followed_by_plain_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("option guidance content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    prompts.append(prompt)
                    return {"summary": "done", "action": {"type": "finish", "reason": "guided"}}

                chat_state = {}
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/continue --auth auth.json --allow-read . inspect the README summary",
                                    chat_state,
                                ),
                                "continue",
                            )

                self.assertEqual(chat_state["work_continue_options"], "--auth auth.json --allow-read .")
                self.assertIn("inspect the README summary", prompts[-1])
            finally:
                os.chdir(old_cwd)

    def test_chat_work_mode_treats_text_and_blank_as_continue(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("work mode content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "."]), 0)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    prompts.append(prompt)
                    if len(prompts) == 1:
                        return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}
                    return {"summary": "done", "action": {"type": "finish", "reason": "blank continued"}}

                stdin = StringIO("inspect README from work mode\n\n/exit\n")
                with patch("sys.stdin", stdin):
                    with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                        with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model) as call_model:
                            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                                self.assertEqual(
                                    main(["chat", "--work-mode", "--no-brief", "--no-unread", "--no-activity"]),
                                    0,
                                )

                output = stdout.getvalue()
                self.assertEqual(call_model.call_count, 2)
                self.assertIn("work-mode: on", output)
                self.assertIn("Work live step #1 action", output)
                self.assertIn("work mode content", load_state()["work_sessions"][0]["tool_calls"][0]["result"]["text"])
                self.assertIn("inspect README from work mode", prompts[0])
                self.assertIn("Work session finished: blank continued", load_state()["tasks"][0]["notes"])
            finally:
                os.chdir(old_cwd)

    def test_chat_work_mode_initial_blank_does_not_continue(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("blank safety content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session", "--allow-read", "."]), 0)

                stdin = StringIO("\n/exit\n")
                with patch("sys.stdin", stdin):
                    with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                        with patch("mew.work_loop.call_model_json_with_retries") as call_model:
                            with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                                self.assertEqual(
                                    main(["chat", "--work-mode", "--no-brief", "--no-unread", "--no-activity"]),
                                    0,
                                )

                self.assertEqual(call_model.call_count, 0)
                output = stdout.getvalue()
                self.assertIn("work-mode: blank ignored until one /c, /follow, or text-guided work step runs", output)
                self.assertEqual(load_state()["work_sessions"][0]["tool_calls"], [])
            finally:
                os.chdir(old_cwd)

    def test_chat_records_input_transcript_and_chat_log_reads_it(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                stdin = StringIO("hello mew\n/transcript 10\n/exit\n")
                with patch("sys.stdin", stdin):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        self.assertEqual(main(["chat", "--no-brief", "--no-unread", "--no-activity"]), 0)

                output = stdout.getvalue()
                self.assertIn("Chat transcript", output)
                self.assertIn("message: hello mew", output)
                self.assertIn("slash: /transcript 10", output)

                with redirect_stdout(StringIO()) as log_stdout:
                    self.assertEqual(main(["chat-log", "--limit", "10"]), 0)
                log_output = log_stdout.getvalue()
                self.assertIn("start: chat started", log_output)
                self.assertIn("message: hello mew", log_output)
                self.assertIn("slash: /exit", log_output)

                with redirect_stdout(StringIO()) as json_stdout:
                    self.assertEqual(main(["chat-log", "--limit", "2", "--json"]), 0)
                records = json.loads(json_stdout.getvalue())
                self.assertEqual(records[-1]["type"], "slash")
                self.assertEqual(records[-1]["text"], "/exit")
            finally:
                os.chdir(old_cwd)

    def test_work_follow_runs_compact_multi_step_live_loop(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("follow content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "done", "action": {"type": "finish", "reason": "follow complete"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertEqual(call_model.call_count, 2)
                self.assertIn("Work live step #1 thinking", output)
                self.assertIn("progress: step=1/10", output)
                self.assertIn("Work live step #2 thinking", output)
                self.assertIn("mew work ai: 2/10 step(s) stop=finish", output)
                self.assertNotIn("Work live step #1 resume", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("Work session finished: follow complete", load_state()["tasks"][0]["notes"])
            finally:
                os.chdir(old_cwd)

    def test_work_follow_streams_model_deltas_by_default(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("follow stream content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(
                    model_backend,
                    model_auth,
                    prompt,
                    model,
                    base_url,
                    timeout,
                    log_prefix=None,
                    on_text_delta=None,
                ):
                    if on_text_delta:
                        on_text_delta("follow ")
                        on_text_delta("model ")
                        on_text_delta("delta")
                    return {"summary": "done", "action": {"type": "finish", "reason": "stream observed"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()) as stderr:
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                progress = stderr.getvalue()
                self.assertIn("THINK start", progress)
                self.assertNotIn("THINK delta", progress)
                output = stdout.getvalue()
                self.assertIn("model_delta: THINK follow model delta", output)
                self.assertEqual(output.count("model_delta: THINK"), 1)
                self.assertIn("model_stream: THINK chunks=3", output)
                self.assertNotIn("stream_preview: follow model delta", output)
                self.assertLess(output.index("model_delta: THINK"), output.index("model_stream: THINK"))
            finally:
                os.chdir(old_cwd)

    def test_work_follow_renders_json_model_deltas_as_prose(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("json stream content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(
                    model_backend,
                    model_auth,
                    prompt,
                    model,
                    base_url,
                    timeout,
                    log_prefix=None,
                    on_text_delta=None,
                ):
                    if on_text_delta:
                        on_text_delta('{"summary":"Inspect')
                        on_text_delta(' roadmap","action":{"type":"finish","reason":"Done')
                        on_text_delta(' now"}}')
                    return {
                        "summary": "Inspect roadmap",
                        "action": {"type": "finish", "reason": "Done now"},
                    }

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertIn("model_summary_delta: THINK Inspect roadmap", output)
                self.assertIn("model_reason_delta: THINK Done now", output)
                self.assertIn("model_action_delta: THINK finish", output)
                self.assertNotIn('model_delta: THINK {"summary"', output)
            finally:
                os.chdir(old_cwd)

    def test_work_follow_honors_explicit_one_step_bound(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("follow one content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "should not run", "action": {"type": "finish", "reason": "too many"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--max-steps",
                                        "1",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertEqual(call_model.call_count, 1)
                self.assertIn("progress: step=1/1", output)
                self.assertIn("mew work ai: 1/1 step(s) stop=max_steps", output)
                self.assertIn("max_steps_note: Follow reached max_steps=1", output)
                self.assertNotIn("Work live step #2", output)
                session = load_state()["work_sessions"][0]
                self.assertIn("Follow reached max_steps=1", session["notes"][-1]["text"])
                self.assertIn("Last action: read_file", session["notes"][-1]["text"])
                self.assertNotIn("follow one content", session["notes"][-1]["text"])
                self.assertNotIn("Resume with /c", session["notes"][-1]["text"])
            finally:
                os.chdir(old_cwd)

    def test_max_steps_note_replaces_older_boundary_notes(self):
        from mew.commands import record_max_steps_reentry_note

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    state["work_sessions"] = [
                        {
                            "id": 1,
                            "task_id": 1,
                            "status": "active",
                            "title": "Loop",
                            "goal": "Keep notes calm.",
                            "created_at": "then",
                            "updated_at": "then",
                            "notes": [
                                {
                                    "created_at": "old",
                                    "source": "system",
                                    "text": "Follow reached max_steps=1 after 1 step(s). Last action: glob.",
                                },
                                {"created_at": "old", "source": "user", "text": "Keep this note."},
                            ],
                            "tool_calls": [],
                            "model_turns": [],
                        }
                    ]
                    save_state(state)

                note_text = record_max_steps_reentry_note(
                    1,
                    {
                        "max_steps": 2,
                        "steps": [
                            {
                                "index": 2,
                                "action": {"type": "read_file"},
                                "summary": "observed " + "very long " * 80,
                            }
                        ],
                    },
                )

                session = load_state()["work_sessions"][0]
                system_notes = [note for note in session["notes"] if note.get("source") == "system"]
                self.assertEqual(len(system_notes), 1)
                self.assertIn("Follow reached max_steps=2", system_notes[0]["text"])
                self.assertIn("Last action: read_file", system_notes[0]["text"])
                self.assertNotIn("Resume with /c", system_notes[0]["text"])
                self.assertLess(len(note_text), 380)
                self.assertTrue(any(note.get("text") == "Keep this note." for note in session["notes"]))
            finally:
                os.chdir(old_cwd)

    def test_work_live_multi_step_max_steps_records_reentry_note(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("live max note content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                model_outputs = [
                    {"summary": "read README first", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "read README second", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--live",
                                        "--max-steps",
                                        "2",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )

                output = stdout.getvalue()
                self.assertIn("mew work ai: 2/2 step(s) stop=max_steps", output)
                self.assertIn("max_steps_note: Live run reached max_steps=2", output)
                session = load_state()["work_sessions"][0]
                self.assertIn("Live run reached max_steps=2", session["notes"][-1]["text"])
                self.assertIn("Last action: read_file", session["notes"][-1]["text"])
                self.assertNotIn("live max note content", session["notes"][-1]["text"])
            finally:
                os.chdir(old_cwd)

    def test_work_follow_final_step_adds_reentry_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("follow final guidance content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                prompts = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    prompts.append(prompt)
                    return {"summary": "pause with context", "action": {"type": "wait", "reason": "bounded pause"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model) as call_model:
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--max-steps",
                                        "1",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                        "--work-guidance",
                                        "base guidance",
                                    ]
                                ),
                                0,
                            )

                self.assertEqual(call_model.call_count, 1)
                prompt_context = json.loads(prompts[0].split("Context JSON:\n", 1)[1])
                self.assertIn("base guidance", prompt_context["guidance"])
                self.assertIn("final allowed --follow step", prompt_context["guidance"])
                self.assertIn("durable note", prompt_context["guidance"])
                turn_guidance = load_state()["work_sessions"][0]["model_turns"][0]["guidance_snapshot"]
                self.assertIn("base guidance", turn_guidance)
                self.assertIn("final allowed --follow step", turn_guidance)
            finally:
                os.chdir(old_cwd)

    def test_work_follow_keyboard_interrupt_marks_session_recoverable(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("interrupt content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    raise KeyboardInterrupt

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                main(
                                    [
                                        "work",
                                        "1",
                                        "--follow",
                                        "--max-steps",
                                        "3",
                                        "--auth",
                                        "auth.json",
                                        "--allow-read",
                                        ".",
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                130,
                            )

                output = stdout.getvalue()
                self.assertIn("stop=user_interrupt", output)
                self.assertIn("interrupted_step: 1", output)
                self.assertIn("Resume with /c", output)
                self.assertIn("Next CLI controls", output)
                session = load_state()["work_sessions"][0]
                self.assertNotIn("stop_requested_at", session)
                self.assertEqual(session["model_turns"][0]["status"], "interrupted")
                self.assertEqual(session["last_user_interrupt"]["step"], 1)
                self.assertIn("Resume with /c", session["notes"][-1]["text"])
            finally:
                os.chdir(old_cwd)

    def test_chat_follow_keyboard_interrupt_keeps_continue_options(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("chat interrupt content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    raise KeyboardInterrupt

                chat_state = {}
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/follow --auth auth.json --allow-read . --act-mode deterministic",
                                    chat_state,
                                ),
                                "continue",
                            )

                output = stdout.getvalue()
                self.assertIn("stop=user_interrupt", output)
                self.assertIn("Primary", output)
                self.assertIn("--allow-read .", chat_state["work_continue_options"])
                self.assertIn("--act-mode deterministic", chat_state["work_continue_options"])
            finally:
                os.chdir(old_cwd)

    def test_chat_follow_runs_bounded_live_loop(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                Path("README.md").write_text("chat follow content\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                    {"summary": "pause", "action": {"type": "wait", "reason": "chat follow pause"}},
                ]
                chat_state = {}
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs) as call_model:
                        with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                            self.assertEqual(
                                run_chat_slash_command(
                                    "/follow --auth auth.json --allow-read . --act-mode deterministic",
                                    chat_state,
                                ),
                                "continue",
                            )

                output = stdout.getvalue()
                self.assertEqual(call_model.call_count, 2)
                self.assertEqual(chat_state["work_continue_options"], "--auth auth.json --allow-read . --act-mode deterministic")
                self.assertIn("Work live step #2 thinking", output)
                self.assertIn("mew work ai: 2/10 step(s) stop=wait", output)
                self.assertIn("/follow --auth auth.json --allow-read . --act-mode deterministic", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_can_request_stop(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session stop pause soon", {}), "continue")
                output = stdout.getvalue()
                self.assertIn("requested stop for work session #1: pause soon", output)
                self.assertIn("Next controls", output)
                session = load_state()["work_sessions"][0]
                self.assertEqual(session["stop_reason"], "pause soon")
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_can_record_note(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session note keep edits tiny", {}), "continue")
                output = stdout.getvalue()
                self.assertIn("recorded work session note #1: keep edits tiny", output)
                self.assertIn("Next controls", output)
                self.assertEqual(load_state()["work_sessions"][0]["notes"][0]["text"], "keep edits tiny")
            finally:
                os.chdir(old_cwd)

    def test_chat_work_session_can_approve_and_reject_tool_changes(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import run_chat_slash_command

                target = Path("notes.md")
                target.write_text("before\n", encoding="utf-8")
                with state_lock():
                    state = load_state()
                    add_coding_task(state)
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "before",
                                "--new",
                                "after",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                dry_run = json.loads(stdout.getvalue())
                self.assertEqual(dry_run["tool_call"]["id"], 1)
                self.assertEqual(target.read_text(encoding="utf-8"), "before\n")

                command = f"{sys.executable} -c \"from pathlib import Path; assert Path('notes.md').read_text() == 'after\\n'\""
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        run_chat_slash_command(
                            f"/work-session approve 1 --allow-write . --verify-command {shlex.quote(command)}",
                            {},
                        ),
                        "continue",
                    )
                self.assertIn("approved work tool #1 -> #2 [completed]", stdout.getvalue())
                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                "1",
                                "--tool",
                                "edit_file",
                                "--path",
                                "notes.md",
                                "--old",
                                "after",
                                "--new",
                                "never",
                                "--allow-write",
                                ".",
                                "--json",
                            ]
                        ),
                        0,
                    )
                second_dry_run = json.loads(stdout.getvalue())
                self.assertEqual(second_dry_run["tool_call"]["id"], 3)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        run_chat_slash_command("/work-session reject 3 not needed", {}),
                        "continue",
                    )
                self.assertIn("rejected work tool #3", stdout.getvalue())
                state = load_state()
                rejected = state["work_sessions"][0]["tool_calls"][2]
                self.assertEqual(rejected["approval_status"], "rejected")
                self.assertEqual(rejected["rejection_reason"], "not needed")
                self.assertEqual(target.read_text(encoding="utf-8"), "after\n")
            finally:
                os.chdir(old_cwd)
