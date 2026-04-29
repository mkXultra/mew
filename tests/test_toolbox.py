import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.toolbox import run_command_record, run_command_record_streaming


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
