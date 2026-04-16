import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
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
                self.assertIn("tool_calls=2", text)
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
                self.assertIn("-old text", details)
                self.assertIn("+new text", details)
                self.assertIn("verification_exit_code=0", details)
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
                self.assertIn("exit_code=None", call["error"])
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
                        return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}
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
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual([turn["status"] for turn in session["model_turns"]], ["completed", "completed"])
                self.assertEqual([call["tool"] for call in session["tool_calls"]], ["read_file"])
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
                self.assertEqual(len(session["model_turns"]), 2)
                self.assertEqual(len(session["tool_calls"]), 1)
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
            finally:
                os.chdir(old_cwd)
