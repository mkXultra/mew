import os
import signal
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.errors import MewError


class CommandTests(unittest.TestCase):
    def test_doctor_missing_optional_auth_still_succeeds(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.shutil.which", return_value="/usr/bin/tool"):
                    with patch("mew.commands.load_codex_oauth", side_effect=MewError("auth missing")):
                        with redirect_stdout(StringIO()) as stdout:
                            code = main(["doctor"])
                self.assertEqual(code, 0)
                self.assertIn("codex_auth: missing", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_doctor_can_require_auth(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.shutil.which", return_value="/usr/bin/tool"):
                    with patch("mew.commands.load_codex_oauth", side_effect=MewError("auth missing")):
                        with redirect_stdout(StringIO()) as stdout:
                            code = main(["doctor", "--require-auth"])
                self.assertEqual(code, 1)
                self.assertIn("codex_auth: error", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_ack_can_mark_multiple_and_all(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "one")
                    add_outbox_message(state, "info", "two")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["ack", "1", "2"]), 0)
                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "three")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["ack", "--all"]), 0)

                state = load_state()
                self.assertTrue(all(message.get("read_at") for message in state["outbox"]))
            finally:
                os.chdir(old_cwd)

    def test_attention_can_resolve_items(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_attention_item, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_attention_item(state, "test", "First", "one")
                    add_attention_item(state, "test", "Second", "two")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["attention", "--resolve", "1"]), 0)
                    self.assertEqual(main(["attention", "--resolve-all"]), 0)

                state = load_state()
                self.assertTrue(
                    all(item.get("status") == "resolved" for item in state["attention"]["items"])
                )
            finally:
                os.chdir(old_cwd)

    def test_run_autonomous_initializes_instruction_files(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["run", "--once", "--autonomous", "--poll-interval", "0.01"]),
                        0,
                    )

                self.assertTrue((Path(".mew") / "guidance.md").exists())
                self.assertTrue((Path(".mew") / "policy.md").exists())
                self.assertTrue((Path(".mew") / "self.md").exists())
                self.assertTrue((Path(".mew") / "desires.md").exists())
            finally:
                os.chdir(old_cwd)

    def test_stop_reports_when_no_runtime_is_active(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["stop"])

                self.assertEqual(code, 0)
                self.assertIn("No active runtime.", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_stop_signals_active_runtime_and_waits(self):
        with (
            patch("mew.commands.read_lock", return_value={"pid": 123}),
            patch("mew.commands.pid_alive", side_effect=[True, False]),
            patch("mew.commands.os.kill") as kill,
        ):
            with redirect_stdout(StringIO()) as stdout:
                code = main(["stop", "--timeout", "1", "--poll-interval", "0.01"])

        self.assertEqual(code, 0)
        kill.assert_called_once_with(123, signal.SIGTERM)
        self.assertIn("runtime stopped", stdout.getvalue())

    def test_tool_read_prints_non_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("notes.md").write_text("hello from mew tools", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "read", "notes.md"])

                self.assertEqual(code, 0)
                self.assertIn("hello from mew tools", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_read_refuses_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("auth.json").write_text('{"token":"secret"}', encoding="utf-8")

                with redirect_stderr(StringIO()) as stderr:
                    code = main(["tool", "read", "auth.json"])

                self.assertEqual(code, 1)
                self.assertIn("sensitive path", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_write_create_and_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "tool",
                            "write",
                            "notes.md",
                            "--content",
                            "hello\n",
                            "--create",
                            "--dry-run",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("dry_run: True", stdout.getvalue())
                self.assertFalse(Path("notes.md").exists())

                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "tool",
                            "write",
                            "notes.md",
                            "--content",
                            "hello\n",
                            "--create",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertEqual(Path("notes.md").read_text(encoding="utf-8"), "hello\n")
                self.assertIn("written: True", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_edit_replaces_one_match_and_refuses_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("notes.md").write_text("hello mew\n", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "edit", "notes.md", "--old", "mew", "--new", "shell"])

                self.assertEqual(code, 0)
                self.assertEqual(Path("notes.md").read_text(encoding="utf-8"), "hello shell\n")
                self.assertIn("edit_file", stdout.getvalue())

                Path("auth.json").write_text("secret", encoding="utf-8")
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["tool", "edit", "auth.json", "--old", "secret", "--new", "x"])

                self.assertEqual(code, 1)
                self.assertIn("sensitive path", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_test_runs_bounded_command_with_env(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f'FLAG=ok {sys.executable} -c "import os; print(os.environ[\\"FLAG\\"])"'

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "test", "--command", command, "--timeout", "5"])

                self.assertEqual(code, 0)
                self.assertIn("exit_code: 0", stdout.getvalue())
                self.assertIn("ok", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_test_returns_failure_status(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f'{sys.executable} -c "raise SystemExit(7)"'

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "test", "--command", command, "--timeout", "5"])

                self.assertEqual(code, 1)
                self.assertIn("exit_code: 7", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_git_diff_supports_staged_stat(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, text=True, capture_output=True)
                Path("example.txt").write_text("hello\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "git", "diff", "--staged", "--stat"])

                self.assertEqual(code, 0)
                self.assertIn("example.txt", stdout.getvalue())
                self.assertIn("git diff --staged --stat --", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_git_diff_supports_base_stat(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, text=True, capture_output=True)
                Path("example.txt").write_text("hello\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=mew",
                        "-c",
                        "user.email=mew@example.com",
                        "commit",
                        "-m",
                        "initial",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                Path("example.txt").write_text("hello\nmew\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=mew",
                        "-c",
                        "user.email=mew@example.com",
                        "commit",
                        "-m",
                        "change",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                )

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "git", "diff", "--base", "HEAD~1", "--stat"])

                self.assertEqual(code, 0)
                self.assertIn("git diff HEAD~1...HEAD --stat --", stdout.getvalue())
                self.assertIn("example.txt", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_verification_lists_recent_runs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["verification_runs"].append(
                        {
                            "id": 1,
                            "command": "python -m unittest",
                            "exit_code": 0,
                            "stdout": "OK",
                            "stderr": "",
                            "finished_at": "done",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["verification", "--details"])

                self.assertEqual(code, 0)
                self.assertIn("#1 [passed]", stdout.getvalue())
                self.assertIn("stdout:", stdout.getvalue())
                self.assertIn("OK", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_writes_lists_recent_runs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["write_runs"].append(
                        {
                            "id": 1,
                            "operation": "edit_file",
                            "path": "/tmp/notes.md",
                            "changed": True,
                            "dry_run": False,
                            "written": True,
                            "diff": "--- a\n+++ b\n",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["writes", "--details"])

                self.assertEqual(code, 0)
                self.assertIn("#1 [edit_file]", stdout.getvalue())
                self.assertIn("diff:", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_message_wait_prints_response_for_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                def respond_once_event_exists():
                    deadline = time.monotonic() + 2.0
                    while time.monotonic() < deadline:
                        with state_lock():
                            state = load_state()
                            if state["inbox"]:
                                event = state["inbox"][0]
                                add_outbox_message(
                                    state,
                                    "assistant",
                                    "hello from runtime",
                                    event_id=event["id"],
                                )
                                event["processed_at"] = "done"
                                save_state(state)
                                return
                        time.sleep(0.01)

                responder = threading.Thread(target=respond_once_event_exists)
                responder.start()
                with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    code = main(
                        [
                            "message",
                            "hello?",
                            "--wait",
                            "--timeout",
                            "2",
                            "--poll-interval",
                            "0.01",
                        ]
                    )
                responder.join(timeout=2)

                self.assertEqual(code, 0)
                self.assertIn("queued message event #1", stdout.getvalue())
                self.assertIn("hello from runtime", stdout.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
