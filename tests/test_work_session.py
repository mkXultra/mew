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
                self.assertIn("phase=idle", text)
                self.assertIn("tool_calls=2", text)
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
                self.assertIn("-old text", details)
                self.assertIn("+new text", details)
                self.assertIn("verification_exit_code=0", details)
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
                command = f"{sys.executable} -c \"print('resume ok')\""
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
                self.assertEqual(resume["phase"], "awaiting_approval")
                self.assertEqual(resume["pending_approvals"][0]["tool_call_id"], 3)
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
                self.assertIn("#3 edit_file", text)
                self.assertIn("approve: /work-session approve 3", text)
                self.assertIn("reject: /work-session reject 3", text)
                self.assertIn("Context pressure", text)
                self.assertIn("pressure=low tool_calls=3", text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work-session resume --allow-read .", {}), "continue")
                chat_world_text = stdout.getvalue()
                self.assertIn("World state", chat_world_text)
                self.assertIn("git_status exit=", chat_world_text)
                self.assertIn("README.md", chat_world_text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--allow-read", ".", "--json"]), 0)
                world_resume = json.loads(stdout.getvalue())["resume"]
                self.assertIn("exit_code", world_resume["world_state"]["git_status"])
                self.assertTrue(world_resume["world_state"]["files"][0]["exists"])
            finally:
                os.chdir(old_cwd)

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
                self.assertEqual(json.loads(stdout.getvalue())["resume"]["phase"], "stop_requested")

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
                self.assertIn("mew work 1 --live --auth auth.json --model-backend codex --allow-read .", output)
                self.assertIn("--max-steps 3", output)
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

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume"]), 0)
                self.assertIn("Recovery plan", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--recover-session", "--allow-read", ".", "--json"]), 0)
                report = json.loads(stdout.getvalue())

                self.assertEqual(report["recovery"]["action"], "retry_tool")
                self.assertEqual(report["recovery"]["source_tool_call_id"], 1)
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

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, on_text_delta=None):
                    if on_text_delta:
                        on_text_delta("model delta")
                    return {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}}

                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
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

    def test_work_think_prompt_guides_independent_reads_to_batch(self):
        from mew.work_loop import build_work_think_prompt

        prompt = build_work_think_prompt({"work_session": {"tool_calls": []}})
        self.assertIn("prefer one batch action", prompt)
        self.assertIn('"type": "batch|inspect_dir', prompt)
        self.assertIn('"max_chars": "optional read_file cap"', prompt)
        self.assertIn('"stat": "optional git_diff diffstat', prompt)

    def test_work_model_actions_default_to_small_reads_and_diffstat(self):
        from mew.work_loop import work_tool_parameters_from_action

        read_parameters = work_tool_parameters_from_action({"type": "read_file", "path": "README.md"})
        self.assertEqual(read_parameters["max_chars"], 12000)

        explicit_read_parameters = work_tool_parameters_from_action(
            {"type": "read_file", "path": "README.md", "max_chars": 24000}
        )
        self.assertEqual(explicit_read_parameters["max_chars"], 24000)

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

                model_outputs = [
                    {"summary": "read README", "action": {"type": "read_file", "path": "README.md"}},
                ]
                with patch("mew.commands.load_model_auth", return_value={"path": "auth.json"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=model_outputs):
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
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 action", output)
                self.assertIn("action: read_file", output)
                self.assertIn("tool_call: #1", output)
                self.assertIn("reason: read README", output)
                self.assertIn("path: README.md", output)
                self.assertIn("Work live step #1 resume", output)
                self.assertLess(output.index("Work live step #1 action"), output.index("Work live step #1 resume"))
                self.assertIn("Work resume #1 [active] task=#1", output)
                self.assertIn("mew work ai: 1/1 step(s) stop=max_steps", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew work 1 --live", output)
                self.assertIn("mew work 1 --session --resume --allow-read .", output)
                self.assertIn("ACT deterministic action=read_file", stderr.getvalue())
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
                                        "--act-mode",
                                        "deterministic",
                                    ]
                                ),
                                0,
                            )
                output = stdout.getvalue()
                self.assertIn("Work live step #1 action", output)
                self.assertIn("action: finish", output)
                self.assertIn("Work live step #1 resume", output)
                self.assertIn("Work resume #1 [closed] task=#1", output)
                self.assertIn("phase: closed", output)
                self.assertIn("Next CLI controls", output)
                self.assertIn("mew work 1 --session --resume", output)
                self.assertIn("Work session finished: finished live", load_state()["tasks"][0]["notes"])
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
                self.assertIn("/continue --allow-read .", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

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
                self.assertIn("Work live step #1 resume", output)
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
                self.assertIn("action: read_file", output)
                self.assertIn("Next controls", output)
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
                                    "/continue --auth auth.json --allow-read . --act-mode deterministic",
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
                    "--auth auth.json --allow-read . --act-mode deterministic",
                )
                self.assertIn("focus on the README summary", prompts[-1])
                self.assertIn("Next controls", output)
                self.assertIn("/continue <guidance>", output)
                self.assertIn("/work-session resume 1", output)
                self.assertIn("Work session finished: guidance followed", load_state()["tasks"][0]["notes"])
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
