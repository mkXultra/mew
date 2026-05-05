import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.toolbox import ManagedCommandRunner, run_command_record, run_command_record_streaming


class ToolboxTests(unittest.TestCase):
    def test_run_command_record_can_kill_process_group_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "grandchild-survived.txt"
            child_code = (
                "import pathlib, time; "
                "time.sleep(0.7); "
                f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
            )
            parent_code = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "time.sleep(10)"
            )
            command = shlex.join([sys.executable, "-c", parent_code])

            result = run_command_record(command, cwd=tmp, timeout=0.2, kill_process_group=True)
            time.sleep(1.0)

            self.assertTrue(result["timed_out"])
            self.assertFalse(marker.exists())

    def test_run_command_record_streaming_can_kill_process_group_on_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "streaming-grandchild-survived.txt"
            child_code = (
                "import pathlib, time; "
                "time.sleep(0.7); "
                f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
            )
            parent_code = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "time.sleep(10)"
            )
            command = shlex.join([sys.executable, "-c", parent_code])

            result = run_command_record_streaming(command, cwd=tmp, timeout=0.2, kill_process_group=True)
            time.sleep(1.0)

            self.assertTrue(result["timed_out"])
            self.assertFalse(marker.exists())

    def test_run_command_record_streaming_drains_stderr_without_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.stderr.write('.' * 200000); sys.stderr.flush()",
                ]
            )
            streamed = []

            result = run_command_record_streaming(
                command,
                cwd=tmp,
                timeout=1,
                on_output=lambda name, chunk: streamed.append((name, chunk)),
            )

            self.assertFalse(result["timed_out"])
            self.assertEqual(result["exit_code"], 0)
            self.assertGreaterEqual(result["duration_seconds"], 0)
            self.assertIn(".", result["stderr"])
            self.assertTrue(any(name == "stderr" and chunk for name, chunk in streamed))

    def test_run_command_record_streaming_records_timeout_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join(
                [
                    sys.executable,
                    "-c",
                    (
                        "import sys, time; "
                        "print('hello-out', flush=True); "
                        "print('hello-err', file=sys.stderr, flush=True); "
                        "time.sleep(5)"
                    ),
                ]
            )

            result = run_command_record_streaming(command, cwd=tmp, timeout=0.3)

            self.assertTrue(result["timed_out"])
            self.assertIsNone(result["exit_code"])
            self.assertEqual(result["timeout_seconds"], 0.3)
            self.assertTrue(result["kill_status"])
            self.assertIn("hello-out", result["stdout_tail"])
            self.assertIn("hello-err", result["stderr_tail"])
            self.assertIn("command timed out after 0.3 second(s)", result["stderr"])

    def test_run_command_record_streaming_uses_devnull_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join([sys.executable, "-c", "print('ok')"])
            seen = {}
            real_popen = subprocess.Popen

            def wrapped_popen(*args, **kwargs):
                seen["stdin"] = kwargs.get("stdin")
                return real_popen(*args, **kwargs)

            with patch("mew.toolbox.subprocess.Popen", side_effect=wrapped_popen):
                result = run_command_record_streaming(command, cwd=tmp, timeout=1)

            self.assertEqual(seen["stdin"], subprocess.DEVNULL)
            self.assertEqual(result["exit_code"], 0)

    def test_run_command_record_sets_macos_objc_fork_safety_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import os; print(os.environ.get('OBJC_DISABLE_INITIALIZE_FORK_SAFETY', ''))",
                ]
            )
            with patch("mew.toolbox.sys.platform", "darwin"):
                result = run_command_record(command, cwd=tmp, timeout=1)

            self.assertEqual(result["exit_code"], 0)
            self.assertEqual(result["stdout"].strip(), "YES")

    def test_managed_command_runner_yields_then_finalizes_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "managed-output.log"
            command = shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import time; print('started', flush=True); time.sleep(0.5); print('done', flush=True)",
                ]
            )
            runner = ManagedCommandRunner()

            handle = runner.start(
                command,
                cwd=tmp,
                timeout=1,
                kill_process_group=True,
                command_run_id="work_session:1:command_run:1",
                output_ref="work-session/1/command/1/output.log",
                output_path=str(output_path),
            )
            running = runner.poll(wait_seconds=0.2)
            final = runner.finalize(timeout=1)

            self.assertEqual(handle.pid, handle.process_group_id)
            self.assertEqual(running["command_run_id"], "work_session:1:command_run:1")
            self.assertEqual(running["output_ref"], "work-session/1/command/1/output.log")
            self.assertEqual(running["output_path"], str(output_path))
            self.assertEqual(running["status"], "running")
            self.assertIsNone(running["exit_code"])
            self.assertGreater(running["duration_seconds"], 0)
            self.assertIn("started", running["stdout"])
            self.assertEqual(final["exit_code"], 0)
            self.assertFalse(final["timed_out"])
            self.assertGreaterEqual(final["duration_seconds"], running["duration_seconds"])
            self.assertIn("done", final["stdout"])
            self.assertIn("started", output_path.read_text(encoding="utf-8"))
            self.assertIn("done", output_path.read_text(encoding="utf-8"))

    def test_managed_command_runner_finalizes_nonzero_after_yield(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join(
                [
                    sys.executable,
                    "-c",
                    "import sys, time; print('before-fail', flush=True); time.sleep(0.1); sys.exit(7)",
                ]
            )
            runner = ManagedCommandRunner()

            runner.start(command, cwd=tmp, timeout=1)
            running = runner.poll(wait_seconds=0.02)
            final = runner.finalize(timeout=1)

            self.assertEqual(running["status"], "running")
            self.assertEqual(final["exit_code"], 7)
            self.assertIn("before-fail", final["stdout"])

    def test_managed_command_runner_timeout_kills_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "managed-grandchild-survived.txt"
            child_code = (
                "import pathlib, time; "
                "time.sleep(0.7); "
                f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
            )
            parent_code = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "print('parent-started', flush=True); "
                "time.sleep(10)"
            )
            command = shlex.join([sys.executable, "-c", parent_code])
            runner = ManagedCommandRunner()

            runner.start(command, cwd=tmp, timeout=0.2, kill_process_group=True)
            result = runner.finalize()
            time.sleep(1.0)

            self.assertTrue(result["timed_out"])
            self.assertTrue(result["kill_status"])
            self.assertIn("parent-started", result["stdout"])
            self.assertFalse(marker.exists())

    def test_managed_command_runner_poll_enforces_command_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join([sys.executable, "-c", "import time; print('started', flush=True); time.sleep(10)"])
            runner = ManagedCommandRunner()

            runner.start(command, cwd=tmp, timeout=0.1, kill_process_group=True)
            result = runner.poll(wait_seconds=1.0)

            self.assertTrue(result["timed_out"])
            self.assertIsNone(result["exit_code"])
            self.assertIn("started", result["stdout"])

    def test_managed_command_runner_rejects_second_active_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            command = shlex.join([sys.executable, "-c", "import time; time.sleep(0.2)"])
            runner = ManagedCommandRunner()

            runner.start(command, cwd=tmp, timeout=1)
            with self.assertRaisesRegex(RuntimeError, "already running"):
                runner.start(command, cwd=tmp, timeout=1)
            runner.finalize(timeout=1)

    def test_managed_command_runner_cancel_cleans_active_process_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "managed-cancel-grandchild-survived.txt"
            child_code = (
                "import pathlib, time; "
                "time.sleep(0.7); "
                f"pathlib.Path({str(marker)!r}).write_text('alive', encoding='utf-8')"
            )
            parent_code = (
                "import subprocess, sys, time; "
                f"subprocess.Popen([sys.executable, '-c', {child_code!r}]); "
                "print('cancel-started', flush=True); "
                "time.sleep(10)"
            )
            command = shlex.join([sys.executable, "-c", parent_code])
            runner = ManagedCommandRunner()

            runner.start(command, cwd=tmp, timeout=10, kill_process_group=True)
            result = runner.cancel("test cleanup")
            time.sleep(1.0)

            self.assertEqual(result["status"], "killed")
            self.assertTrue(result["kill_status"])
            self.assertEqual(result["reason"], "test cleanup")
            self.assertFalse(marker.exists())
            with self.assertRaisesRegex(RuntimeError, "no managed command is active"):
                runner.finalize(timeout=0)
