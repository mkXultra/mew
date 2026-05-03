import contextlib
import io
import json
import tempfile
import unittest

from mew.cli import build_parser
from mew.dogfood import _write_terminal_bench_replay_fixture
from mew.terminal_bench_replay import format_terminal_bench_replay, replay_terminal_bench_job


class TerminalBenchReplayTests(unittest.TestCase):
    def test_replay_terminal_bench_job_recomputes_current_resume_from_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_terminal_bench_replay_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="compile-compcert",
                assertions={
                    "long_build_status": "blocked",
                    "blockers": ["compatibility_override_probe_missing"],
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                },
            )
            text = format_terminal_bench_replay(report)
            trial = report["trials"][0]
            current_long = trial["current"]["long_build_state"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(report["trial_count"], 1)
            self.assertTrue(trial["current"]["recomputed"])
            self.assertEqual(current_long["status"], "blocked")
            self.assertIn("compatibility_override_probe_missing", current_long["strategy_blockers"])
            self.assertIn("terminal-bench replay: pass", text)

    def test_cli_replay_terminal_bench_json_returns_success_on_matching_assertions(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_terminal_bench_replay_fixture(tmp)
            parser = build_parser()
            args = parser.parse_args(
                [
                    "replay",
                    "terminal-bench",
                    "--job-dir",
                    str(job_dir),
                    "--task",
                    "compile-compcert",
                    "--assert-long-build-status",
                    "blocked",
                    "--assert-blocker",
                    "compatibility_override_probe_missing",
                    "--assert-mew-exit-code",
                    "1",
                    "--assert-external-reward",
                    "0",
                    "--json",
                ]
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = args.func(args)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["trial_count"], 1)


if __name__ == "__main__":
    unittest.main()
