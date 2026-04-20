import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mew.cli import main
from mew.daemon import build_daemon_status, format_daemon_status, tail_daemon_log
from mew.state import load_state, save_state, state_lock


class DaemonTests(unittest.TestCase):
    def test_build_daemon_status_reports_uptime_watchers_and_safety(self):
        state = {
            "runtime_status": {
                "state": "running",
                "started_at": "2026-04-20T00:00:00Z",
                "last_woke_at": "2026-04-20T00:01:00Z",
                "last_cycle_reason": "passive_tick",
                "last_processed_count": 1,
                "last_cycle_duration_seconds": 0.25,
                "watchers": [
                    {"name": "repo", "kind": "git", "status": "active"},
                    {"name": "notes", "kind": "file", "status": "paused"},
                ],
            },
            "autonomy": {
                "enabled": True,
                "level": "act",
                "paused": False,
                "allow_agent_run": True,
                "allow_native_work": True,
                "allow_write": False,
                "allow_verify": True,
            },
        }

        status = build_daemon_status(
            state,
            {"pid": 123, "started_at": "2026-04-20T00:00:00Z"},
            lambda pid: pid == 123,
            current_time="2026-04-20T00:02:00Z",
        )

        self.assertEqual(status["state"], "running")
        self.assertEqual(status["uptime_seconds"], 120.0)
        self.assertEqual(status["last_tick"]["age_seconds"], 60.0)
        self.assertEqual(status["watchers"]["count"], 2)
        self.assertEqual(status["watchers"]["active_count"], 1)
        self.assertTrue(status["safety"]["autonomy_enabled"])
        self.assertIn("watchers_active: 1", format_daemon_status(status))

    def test_daemon_status_json_uses_runtime_state(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["runtime_status"]["state"] = "running"
                    state["runtime_status"]["started_at"] = "2026-04-20T00:00:00Z"
                    state["runtime_status"]["last_woke_at"] = "2026-04-20T00:01:00Z"
                    state["runtime_status"]["last_cycle_reason"] = "passive_tick"
                    state["runtime_status"]["last_processed_count"] = 1
                    state["runtime_status"]["watchers"] = [{"name": "repo", "kind": "git", "status": "active"}]
                    save_state(state)

                with patch("mew.commands.read_lock", return_value={"pid": 456, "started_at": "2026-04-20T00:00:00Z"}):
                    with patch("mew.commands.pid_alive", return_value=True):
                        with redirect_stdout(StringIO()) as stdout:
                            code = main(["daemon", "status", "--json"])

                self.assertEqual(code, 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["state"], "running")
                self.assertEqual(data["pid"], 456)
                self.assertEqual(data["watchers"]["active_count"], 1)
                self.assertEqual(data["last_tick"]["reason"], "passive_tick")
                self.assertIn("mew daemon stop", data["controls"]["stop"])
            finally:
                os.chdir(old_cwd)

    def test_daemon_logs_tails_runtime_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path(".mew").mkdir()
                Path(".mew/runtime.out").write_text("one\ntwo\nthree\n", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["daemon", "logs", "--lines", "2"])

                self.assertEqual(code, 0)
                self.assertEqual(stdout.getvalue().strip().splitlines(), ["two", "three"])
                self.assertEqual(tail_daemon_log(lines=1)["lines"], ["three"])
                self.assertEqual(tail_daemon_log(lines=0)["lines"], [])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
