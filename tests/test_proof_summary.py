import json
import tempfile
import unittest
from pathlib import Path

from mew.cli import build_parser
from mew.proof_summary import format_proof_summary, summarize_proof_artifacts


class ProofSummaryTests(unittest.TestCase):
    def test_summarize_resident_loop_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "summary.txt").write_text(
                "\n".join(
                    [
                        "container: mew-proof-real-4h",
                        "image: mew-proof:real-4h",
                        "status: exited",
                        "exit_code: 0",
                        "started_at: 2026-04-20T04:11:52Z",
                        "finished_at: 2026-04-20T08:11:55Z",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (artifact_dir / "stdout.log").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-20T08:11:55Z",
                        "scenario": "resident-loop",
                        "status": "pass",
                        "scenarios": [
                            {
                                "name": "resident-loop",
                                "status": "pass",
                                "artifacts": {
                                    "requested_duration_seconds": 14400.0,
                                    "requested_interval_seconds": 60.0,
                                    "time_dilation": 1.0,
                                    "processed_events": 240,
                                    "passive_events": 239,
                                    "open_questions": 1,
                                    "deferred_questions": 0,
                                    "passive_span_seconds": 14282.0,
                                    "passive_gaps_seconds": [60.0, 61.0, 60.0],
                                },
                                "checks": [
                                    {"name": "resident_loop_starts_and_stops", "passed": True},
                                    {"name": "resident_loop_reentry_context_saves_checkpoint", "passed": True},
                                ],
                            }
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["container"]["exit_code"], "0")
        self.assertEqual(summary["dogfood"]["scenario"], "resident-loop")
        self.assertEqual(summary["resident_loop"]["processed_events"], 240)
        self.assertEqual(summary["resident_loop"]["passive_gaps"]["count"], 3)
        self.assertEqual(summary["resident_loop"]["passive_gaps"]["outside_expected_by_more_than_2s"], 0)
        self.assertEqual(summary["checks"]["passed"], 2)
        self.assertIn("checks: 2/2 passed", format_proof_summary(summary))

    def test_summarize_failed_check_marks_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "summary.txt").write_text("exit_code: 0\n", encoding="utf-8")
            (artifact_dir / "stdout.log").write_text(
                json.dumps(
                    {
                        "scenario": "resident-loop",
                        "status": "pass",
                        "scenarios": [
                            {
                                "name": "resident-loop",
                                "status": "pass",
                                "checks": [
                                    {"name": "resident_loop_starts_and_stops", "passed": True},
                                    {"name": "resident_loop_processes_multiple_events", "passed": False},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertFalse(summary["ok"])
        self.assertEqual(summary["checks"]["failed"], ["resident_loop_processes_multiple_events"])
        self.assertIn("failed_checks: resident_loop_processes_multiple_events", format_proof_summary(summary))

    def test_cli_proof_summary_parses(self):
        parser = build_parser()

        args = parser.parse_args(["proof-summary", "proof-artifacts/example", "--json", "--strict"])

        self.assertEqual(args.artifact_dir, "proof-artifacts/example")
        self.assertTrue(args.json)
        self.assertTrue(args.strict)

