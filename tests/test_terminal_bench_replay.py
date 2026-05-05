import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from mew.cli import build_parser
from mew.dogfood import _write_repository_test_tail_emulator_fixture, _write_terminal_bench_replay_fixture
from mew.terminal_bench_replay import (
    format_terminal_bench_replay,
    replay_terminal_bench_job,
    terminal_bench_llm_action_fixture_contexts,
)


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

    def test_terminal_bench_llm_action_fixture_contexts_extract_model_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_terminal_bench_replay_fixture(tmp)

            contexts = terminal_bench_llm_action_fixture_contexts(job_dir, task="compile-compcert")

            self.assertGreaterEqual(len(contexts), 1)
            first = contexts[0]
            self.assertEqual(first["trial_name"], "compile-compcert__fixture")
            self.assertEqual(first["fixture"]["raw_action"]["type"], "run_command")
            self.assertIn("session", first)
            self.assertIn("task", first)

    def test_replay_terminal_bench_job_asserts_frontier_signature_and_next_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_repository_test_tail_emulator_fixture(tmp, task="generic-compatibility")

            report = replay_terminal_bench_job(
                job_dir,
                task="generic-compatibility",
                assertions={
                    "external_reward": 0.0,
                    "frontier_signature_required": True,
                    "frontier_next_action_required": True,
                    "frontier_open_candidate_count_min": 1,
                    "frontier_signature_matches_stored": True,
                    "frontier_family_key_matches_stored": True,
                    "frontier_next_action_matches_stored": True,
                    "frontier_open_candidate_ids_match_stored": True,
                    "frontier_evidence_ref_count_matches_stored": True,
                },
            )
            trial = report["trials"][0]
            frontier = trial["current"]["active_compatibility_frontier"]
            stored_frontier = trial["stored"]["active_compatibility_frontier"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(frontier["signature"])
            self.assertTrue(frontier["next_action"])
            self.assertGreaterEqual(frontier["open_candidate_count"], 1)
            self.assertEqual(frontier["signature"], stored_frontier["signature"])
            self.assertEqual(frontier["next_action"], stored_frontier["next_action"])
            self.assertEqual(frontier["open_candidate_ids"], stored_frontier["open_candidate_ids"])

    def test_replay_terminal_bench_job_fails_if_frontier_reduced_to_summary_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_repository_test_tail_emulator_fixture(tmp, task="generic-compatibility")
            report_path = next(Path(job_dir).rglob("mew-report.json"))
            payload = json.loads(report_path.read_text(encoding="utf-8"))
            payload["resume"].pop("active_compatibility_frontier", None)
            payload["resume"]["next_action"] = "frontier summary says repository test tail remains"
            payload["work_report"]["steps"] = []
            report_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="generic-compatibility",
                assertions={
                    "frontier_signature_required": True,
                    "frontier_next_action_required": True,
                    "frontier_open_candidate_count_min": 1,
                },
            )

            self.assertEqual(report["status"], "fail")
            failed = [check["name"] for check in report["checks"] if not check["passed"]]
            self.assertIn("frontier_signature_required", failed)


if __name__ == "__main__":
    unittest.main()
