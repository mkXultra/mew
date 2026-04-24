import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.cli import build_parser
from mew.work_replay import PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON
from mew.proof_summary import (
    format_proof_summary,
    summarize_m6_11_replay_calibration,
    summarize_proof_artifacts,
)


class ProofSummaryTests(unittest.TestCase):
    @staticmethod
    def _write_json(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

    @staticmethod
    def _build_mixed_replay_bundles(replay_root):
        replay_root = Path(replay_root)
        compiler_root = replay_root / "2026-04-22" / "session-1" / "todo-compiler"
        for attempt in range(1, 4):
            attempt_dir = compiler_root / f"attempt-{attempt}"
            code = "patch_valid"
            ProofSummaryTests._write_json(
                attempt_dir / "validator_result.json",
                {"code": code},
            )
            ProofSummaryTests._write_json(
                attempt_dir / "replay_metadata.json",
                {
                    "bundle": "patch_draft_compiler",
                    "files": {"validator_result": "validator_result.json"},
                },
            )

        unknown_root = replay_root / "2026-04-22" / "session-2" / "todo-failed-timeout"
        for attempt in range(1, 4):
            attempt_dir = unknown_root / f"attempt-{attempt}"
            ProofSummaryTests._write_json(
                attempt_dir / "report.json",
                {
                    "bundle": "work-loop-model-failure",
                    "failure": {"code": "model_failed_timeout"},
                    "git_head": "",
                },
            )

        dominant_root = replay_root / "2026-04-22" / "session-3" / "todo-failed-refusal"
        for attempt in range(1, 3):
            attempt_dir = dominant_root / f"attempt-{attempt}"
            ProofSummaryTests._write_json(
                attempt_dir / "report.json",
                {
                    "bundle": "work-loop-model-failure",
                    "failure": {"code": "model_input_rejected"},
                },
            )

    @staticmethod
    def _write_relevant_compiler_bundle(
        attempt_root,
        attempt,
        code,
        *,
        git_head="",
        bucket_tag=None,
        blocker_code=None,
    ):
        attempt_dir = Path(attempt_root) / f"attempt-{attempt}"
        metadata = {
            "bundle": "patch_draft_compiler",
            "files": {"validator_result": "validator_result.json"},
        }
        if git_head is not None:
            metadata["git_head"] = git_head
        if bucket_tag is not None:
            metadata["bucket_tag"] = bucket_tag
        if blocker_code is not None:
            metadata["blocker_code"] = blocker_code
        ProofSummaryTests._write_json(
            attempt_dir / "validator_result.json",
            {"code": code},
        )
        ProofSummaryTests._write_json(attempt_dir / "replay_metadata.json", metadata)

    @staticmethod
    def _write_model_failure_bundle(
        attempt_root,
        attempt,
        code="model_failed_timeout",
        *,
        git_head="",
        bucket_tag=None,
        blocker_code=None,
    ):
        attempt_dir = Path(attempt_root) / f"attempt-{attempt}"
        payload = {
            "bundle": "work-loop-model-failure",
            "failure": {"code": code},
        }
        if git_head is not None:
            payload["git_head"] = git_head
        if bucket_tag is not None:
            payload["bucket_tag"] = bucket_tag
        if blocker_code is not None:
            payload["blocker_code"] = blocker_code
        ProofSummaryTests._write_json(
            attempt_dir / "report.json",
            payload,
        )

    @staticmethod
    def _write_legacy_report_bundle(
        attempt_root,
        attempt,
        bundle_name="legacy-work-loop-failure",
    ):
        attempt_dir = Path(attempt_root) / f"attempt-{attempt}"
        ProofSummaryTests._write_json(
            attempt_dir / "report.json",
            {"bundle": bundle_name, "failure": {"code": "model_failed_timeout"}, "git_head": "legacy"},
        )

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
        self.assertEqual(summary["resident_loop"]["expected_passive_events_min"], 238)
        self.assertEqual(summary["resident_loop"]["passive_gaps"]["count"], 3)
        self.assertEqual(summary["resident_loop"]["passive_gaps"]["outside_expected_by_more_than_2s"], 0)
        self.assertEqual(summary["checks"]["passed"], 2)
        self.assertIn("checks: 2/2 passed", format_proof_summary(summary))
        self.assertIn("expected_passive_min=238", format_proof_summary(summary))

    def test_summarize_prefers_report_json_over_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "summary.txt").write_text("exit_code: 0\n", encoding="utf-8")
            (artifact_dir / "stdout.log").write_text("not json\n", encoding="utf-8")
            (artifact_dir / "report.json").write_text(
                json.dumps(
                    {
                        "generated_at": "2026-04-20T10:11:55Z",
                        "scenario": "m6-daemon-loop",
                        "status": "pass",
                        "scenarios": [
                            {
                                "name": "m6-daemon-loop",
                                "status": "pass",
                                "artifacts": {
                                    "requested_duration_seconds": 14400.0,
                                    "requested_interval_seconds": 60.0,
                                    "processed_events": 241,
                                    "passive_events": 240,
                                    "passive_gaps_seconds": [60.0, 60.0, 60.0],
                                },
                                "checks": [
                                    {"name": "m6_daemon_loop_starts_reports_and_stops", "passed": True},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["dogfood"]["scenario"], "m6-daemon-loop")
        self.assertEqual(summary["dogfood"]["report_source"], str(artifact_dir / "report.json"))

    def test_summarize_marks_low_passive_count_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "summary.txt").write_text("exit_code: 0\n", encoding="utf-8")
            (artifact_dir / "report.json").write_text(
                json.dumps(
                    {
                        "scenario": "m6-daemon-loop",
                        "status": "pass",
                        "scenarios": [
                            {
                                "name": "m6-daemon-loop",
                                "status": "pass",
                                "artifacts": {
                                    "requested_duration_seconds": 14400.0,
                                    "requested_interval_seconds": 60.0,
                                    "processed_events": 3,
                                    "passive_events": 2,
                                },
                                "checks": [
                                    {"name": "m6_daemon_loop_starts_reports_and_stops", "passed": True},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertFalse(summary["ok"])
        self.assertIn("passive event count below expected cadence: 2 < 238", summary["errors"])
        self.assertIn("passive event count below expected cadence", format_proof_summary(summary))

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

    def test_summarize_uses_inspect_when_summary_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "inspect.json").write_text(
                json.dumps(
                    [
                        {
                            "Name": "/mew-proof-sample",
                            "Config": {"Image": "mew-proof:latest"},
                            "State": {
                                "Status": "exited",
                                "ExitCode": 0,
                                "StartedAt": "2026-04-20T10:10:06Z",
                                "FinishedAt": "2026-04-20T14:10:10Z",
                            },
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (artifact_dir / "report.json").write_text(
                json.dumps(
                    {
                        "scenario": "m6-daemon-loop",
                        "status": "pass",
                        "scenarios": [
                            {
                                "name": "m6-daemon-loop",
                                "status": "pass",
                                "artifacts": {
                                    "requested_duration_seconds": 14400.0,
                                    "requested_interval_seconds": 60.0,
                                    "processed_events": 241,
                                    "passive_events": 239,
                                    "passive_gaps_seconds": [60.0, 60.0, 61.0],
                                },
                                "checks": [
                                    {"name": "m6_daemon_loop_starts_reports_and_stops", "passed": True},
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["container"]["name"], "mew-proof-sample")
        self.assertEqual(summary["container"]["exit_code"], "0")

    def test_summarize_normalizes_long_daemon_watcher_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            artifact_dir = Path(tmp)
            (artifact_dir / "summary.txt").write_text("exit_code: 1\n", encoding="utf-8")
            (artifact_dir / "report.json").write_text(
                json.dumps(
                    {
                        "scenario": "m6-daemon-loop",
                        "status": "fail",
                        "scenarios": [
                            {
                                "name": "m6-daemon-loop",
                                "status": "fail",
                                "artifacts": {
                                    "requested_duration_seconds": 14400.0,
                                    "requested_interval_seconds": 60.0,
                                    "processed_events": 241,
                                    "passive_events": 239,
                                    "passive_gaps_seconds": [60.0, 60.0, 61.0],
                                },
                                "checks": [
                                    {
                                        "name": "m6_daemon_loop_starts_reports_and_stops",
                                        "passed": True,
                                    },
                                    {
                                        "name": "m6_daemon_loop_watcher_processes_file_event",
                                        "passed": False,
                                        "observed": {
                                            "processed_event": {
                                                "id": 2,
                                                "type": "file_change",
                                                "source": "daemon_watch",
                                                "processed_at": "2026-04-20T10:10:10Z",
                                            },
                                            "external_effect": None,
                                        },
                                    },
                                ],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_proof_artifacts(artifact_dir)

        self.assertTrue(summary["ok"])
        self.assertEqual(summary["checks"]["failed"], [])
        self.assertEqual(summary["checks"]["passed"], 2)

    def test_cli_proof_summary_parses(self):
        parser = build_parser()

        args = parser.parse_args(["proof-summary", "proof-artifacts/example", "--json", "--strict"])

        self.assertEqual(args.artifact_dir, "proof-artifacts/example")
        self.assertTrue(args.json)
        self.assertTrue(args.strict)
        self.assertFalse(args.m6_11_phase2_calibration)

    def test_cli_proof_summary_parses_m6_11_phase2_calibration(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "proof-summary",
                "proof-artifacts/replays",
                "--m6_11-phase2-calibration",
                "--measurement-head",
                "HEAD-MEASURE",
            ]
        )

        self.assertEqual(args.artifact_dir, "proof-artifacts/replays")
        self.assertTrue(args.m6_11_phase2_calibration)
        self.assertEqual(args.measurement_head, "HEAD-MEASURE")

    def test_cli_proof_summary_accepts_measurement_head_without_calibration_mode(self):
        parser = build_parser()

        args = parser.parse_args(
            ["proof-summary", "proof-artifacts/example", "--measurement-head", "HEAD-MEASURE"]
        )

        self.assertEqual(args.artifact_dir, "proof-artifacts/example")
        self.assertFalse(args.m6_11_phase2_calibration)
        self.assertEqual(args.measurement_head, "HEAD-MEASURE")

    def test_summarize_m6_11_calibration_mixed_distribution_can_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            for attempt in range(1, 5):
                self._write_relevant_compiler_bundle(replay_root / "compiler", attempt, "patch_valid")
            for attempt in range(1, 4):
                self._write_model_failure_bundle(
                    replay_root / "failure_timeout",
                    attempt,
                    "model_failed_timeout",
                )
            for attempt in range(1, 4):
                self._write_model_failure_bundle(
                    replay_root / "failure_rejected",
                    attempt,
                    "model_input_rejected",
                )
            summary = summarize_m6_11_replay_calibration(replay_root)

        self.assertTrue(summary["ok"])
        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 10)
        self.assertEqual(
            calibration["bundle_type_counts"],
            {
                "patch_draft_compiler.other": 4,
                "work-loop-model-failure.model_failed_timeout": 3,
                "work-loop-model-failure.model_input_rejected": 3,
            },
        )
        self.assertEqual(calibration["off_schema_count"], 0)
        self.assertEqual(calibration["off_schema_denominator"], 4)
        self.assertAlmostEqual(calibration["off_schema_rate"], 0.0, places=6)
        self.assertEqual(calibration["refusal_count"], 0)
        self.assertAlmostEqual(calibration["refusal_rate"], 0.0, places=6)
        self.assertEqual(calibration["malformed_bundle_count"], 0)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 0)
        self.assertTrue(calibration["thresholds"]["off_schema_rate_ok"])
        self.assertTrue(calibration["thresholds"]["refusal_rate_ok"])
        self.assertTrue(calibration["thresholds"]["failure_mode_concentration_ok"])
        self.assertEqual(calibration["dominant_bundle_share"], 0.4)
        self.assertIn("work-loop-model-failure.model_failed_timeout", calibration["bundle_type_counts"])
        self.assertTrue(calibration["thresholds"]["malformed_relevant_bundles_ok"])

    def test_summarize_m6_11_calibration_patch_draft_compiler_validated_without_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            compiler_root = replay_root / "compiler"
            compiler_root.mkdir(parents=True)
            attempt_dir = compiler_root / "attempt-1"
            ProofSummaryTests._write_json(
                attempt_dir / "validator_result.json",
                {"kind": "patch_draft", "status": "validated"},
            )
            ProofSummaryTests._write_json(
                attempt_dir / "replay_metadata.json",
                {"bundle": "patch_draft_compiler", "files": {"validator_result": "validator_result.json"}},
            )
            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 1)
        self.assertEqual(calibration["bundle_type_counts"], {"patch_draft_compiler.other": 1})
        self.assertEqual(calibration["malformed_bundle_count"], 0)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 0)
        self.assertEqual(len(summary["errors"]), 0)

    def test_summarize_m6_11_calibration_non_counted_compiler_bundle_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(replay_root / "counted", 1, "patch_valid")
            non_counted_root = replay_root / "non_counted" / "attempt-1"
            non_counted_root.parent.mkdir(parents=True, exist_ok=True)
            ProofSummaryTests._write_json(
                non_counted_root / "replay_metadata.json",
                {
                    "bundle": "patch_draft_compiler",
                    "files": {"validator_result": "validator_result.json"},
                    "calibration_counted": False,
                    "calibration_exclusion_reason": "reviewer rejected",
                },
            )
            (non_counted_root / "validator_result.json").write_text(
                "{",
                encoding="utf-8",
            )
            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 1)
        self.assertEqual(calibration["compiler_bundles"], 1)
        self.assertEqual(calibration["relevant_bundles"], 1)
        self.assertEqual(calibration["malformed_bundle_count"], 0)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 0)
        self.assertEqual(len(summary["errors"]), 0)
        self.assertEqual(calibration["thresholds"]["malformed_relevant_bundles_ok"], True)
        self.assertEqual(calibration["non_counted_bundle_count"], 1)
        self.assertEqual(calibration["non_counted_bundle_reasons"], {"reviewer rejected": 1})

    def test_summarize_m6_11_calibration_non_counted_model_failure_bundle_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(replay_root / "counted", 1, "patch_valid")
            attempt_dir = replay_root / "non_counted_failure" / "attempt-1"
            ProofSummaryTests._write_json(
                attempt_dir / "report.json",
                {
                    "bundle": "work-loop-model-failure",
                    "failure": {"code": "request_timed_out"},
                    "calibration_counted": False,
                    "calibration_exclusion_reason": "reviewer superseded",
                },
            )

            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 1)
        self.assertEqual(calibration["bundle_type_counts"], {"patch_draft_compiler.other": 1})
        self.assertEqual(calibration["non_counted_bundle_count"], 1)
        self.assertEqual(calibration["non_counted_bundle_reasons"], {"reviewer superseded": 1})

    def test_summarize_m6_11_calibration_current_head_excludes_auto_non_native_patch_blocker(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            with patch("mew.proof_summary._current_git_head", return_value="HEAD-ONLY"):
                self._write_relevant_compiler_bundle(
                    replay_root / "counted",
                    1,
                    "patch_valid",
                    git_head="HEAD-ONLY",
                )
                non_counted_root = replay_root / "non_counted" / "attempt-1"
                non_counted_root.parent.mkdir(parents=True, exist_ok=True)
                ProofSummaryTests._write_json(
                    non_counted_root / "validator_result.json",
                    {"kind": "patch_blocker", "code": "insufficient_cached_window_text"},
                )
                ProofSummaryTests._write_json(
                    non_counted_root / "replay_metadata.json",
                    {
                        "bundle": "patch_draft_compiler",
                        "files": {"validator_result": "validator_result.json"},
                        "git_head": "HEAD-ONLY",
                        "calibration_counted": False,
                        "calibration_exclusion_reason": PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON,
                    },
                )
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        current_head = calibration["cohorts"]["current_head"]
        self.assertEqual(calibration["total_bundles"], 1)
        self.assertEqual(calibration["compiler_bundles"], 1)
        self.assertEqual(calibration["relevant_bundles"], 1)
        self.assertEqual(current_head["total_bundles"], 1)
        self.assertEqual(current_head["compiler_bundles"], 1)
        self.assertEqual(current_head["non_counted_bundle_count"], 1)
        self.assertEqual(
            current_head["non_counted_bundle_reasons"],
            {PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON: 1},
        )
        self.assertEqual(calibration["non_counted_bundle_count"], 1)
        self.assertEqual(
            calibration["non_counted_bundle_reasons"],
            {PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON: 1},
        )

    def test_summarize_m6_11_calibration_legacy_bundles_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            for attempt in range(1, 3):
                self._write_relevant_compiler_bundle(replay_root / "compiler", attempt, "patch_valid")
            for attempt in range(1, 3):
                self._write_model_failure_bundle(replay_root / "failure_timeout", attempt)
            for attempt in range(1, 2):
                self._write_model_failure_bundle(
                    replay_root / "failure_rejected",
                    attempt,
                    "model_input_rejected",
                )
            for attempt in range(1, 5):
                self._write_legacy_report_bundle(replay_root / "legacy", attempt)
            self._write_legacy_report_bundle(
                replay_root / "ignored",
                1,
                bundle_name="work-loop-model-failure-retry",
            )
            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 5)
        self.assertEqual(
            calibration["bundle_type_counts"],
            {
                "patch_draft_compiler.other": 2,
                "work-loop-model-failure.model_failed_timeout": 2,
                "work-loop-model-failure.model_input_rejected": 1,
            },
        )
        self.assertEqual(calibration["relevant_bundles"], 5)
        self.assertEqual(calibration["malformed_bundle_count"], 5)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 0)
        self.assertTrue(calibration["thresholds"]["failure_mode_concentration_ok"])
        self.assertIn("ignored_legacy-work-loop-failure", calibration["malformed_bundle_counts"])
        self.assertIn(
            "ignored_work-loop-model-failure-retry",
            calibration["malformed_bundle_counts"],
        )

    def test_summarize_m6_11_calibration_splits_by_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            with patch("mew.proof_summary._current_git_head", return_value="HEAD-CURRENT"):
                for attempt in range(1, 5):
                    self._write_relevant_compiler_bundle(
                        replay_root / "current_head_compiler",
                        attempt,
                        "patch_valid",
                        git_head="HEAD-CURRENT",
                    )
                for attempt in range(1, 3):
                    self._write_model_failure_bundle(
                        replay_root / "current_head_timeout",
                        attempt,
                        "model_failed_timeout",
                        git_head="HEAD-CURRENT",
                    )
                self._write_model_failure_bundle(
                    replay_root / "legacy_timeout",
                    1,
                    "model_failed_timeout",
                    git_head="HEAD-LEGACY",
                )
                self._write_relevant_compiler_bundle(
                    replay_root / "unknown_compiler",
                    1,
                    "patch_valid",
                    git_head="",
                )
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 8)
        cohorts = calibration["cohorts"]
        self.assertEqual(cohorts["current_head"]["total_bundles"], 6)
        self.assertEqual(cohorts["legacy"]["total_bundles"], 1)
        self.assertEqual(cohorts["unknown"]["total_bundles"], 1)
        self.assertEqual(
            cohorts["current_head"]["bundle_type_counts"],
            {
                "patch_draft_compiler.other": 4,
                "work-loop-model-failure.model_failed_timeout": 2,
            },
        )
        self.assertEqual(
            cohorts["legacy"]["bundle_type_counts"],
            {"work-loop-model-failure.model_failed_timeout": 1},
        )
        self.assertEqual(
            cohorts["unknown"]["bundle_type_counts"],
            {"patch_draft_compiler.other": 1},
        )

    def test_summarize_m6_11_calibration_adds_measurement_head_cohort_without_relabeling_current_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            with patch("mew.proof_summary._current_git_head", return_value="HEAD-CURRENT"):
                self._write_relevant_compiler_bundle(
                    replay_root / "current_head_compiler",
                    1,
                    "patch_valid",
                    git_head="HEAD-CURRENT",
                )
                self._write_model_failure_bundle(
                    replay_root / "measurement_timeout",
                    1,
                    "model_failed_timeout",
                    git_head="HEAD-MEASURE",
                )
                summary = summarize_m6_11_replay_calibration(
                    replay_root,
                    measurement_head="HEAD-MEASURE",
                )

        self.assertEqual(summary["measurement_head"], "HEAD-MEASURE")
        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 2)
        cohorts = calibration["cohorts"]
        self.assertEqual(cohorts["current_head"]["total_bundles"], 1)
        self.assertEqual(
            cohorts["current_head"]["bundle_type_counts"],
            {"patch_draft_compiler.other": 1},
        )
        self.assertEqual(cohorts["legacy"]["total_bundles"], 1)
        self.assertEqual(cohorts["unknown"]["total_bundles"], 0)
        self.assertEqual(cohorts["measurement_head"]["total_bundles"], 1)
        self.assertEqual(
            cohorts["measurement_head"]["bundle_type_counts"],
            {"work-loop-model-failure.model_failed_timeout": 1},
        )

    def test_summarize_m6_11_calibration_blocker_code_counts_split_by_current_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            with patch("mew.proof_summary._current_git_head", return_value="HEAD-CURRENT"):
                self._write_relevant_compiler_bundle(
                    replay_root / "current_head_compiler",
                    1,
                    "patch_valid",
                    git_head="HEAD-CURRENT",
                    blocker_code="CH-COMP",
                )
                self._write_model_failure_bundle(
                    replay_root / "current_head_timeout",
                    1,
                    "model_failed_timeout",
                    git_head="HEAD-CURRENT",
                    blocker_code="CH-TIMEOUT",
                )
                self._write_relevant_compiler_bundle(
                    replay_root / "legacy_compiler",
                    1,
                    "patch_valid",
                    git_head="HEAD-LEGACY",
                    blocker_code="LG-COMP",
                )
                self._write_model_failure_bundle(
                    replay_root / "legacy_timeout",
                    1,
                    "model_failed_timeout",
                    git_head="HEAD-LEGACY",
                    blocker_code="LG-TIMEOUT",
                )
                self._write_relevant_compiler_bundle(
                    replay_root / "unknown_compiler",
                    1,
                    "patch_valid",
                    git_head="",
                    blocker_code="UNK-COMP",
                )
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        cohorts = calibration["cohorts"]
        self.assertEqual(
            calibration["blocker_code_counts"],
            {
                "CH-COMP": 1,
                "CH-TIMEOUT": 1,
                "LG-COMP": 1,
                "LG-TIMEOUT": 1,
                "UNK-COMP": 1,
            },
        )
        self.assertEqual(
            cohorts["current_head"]["blocker_code_counts"],
            {"CH-COMP": 1, "CH-TIMEOUT": 1},
        )
        self.assertEqual(
            cohorts["legacy"]["blocker_code_counts"],
            {"LG-COMP": 1, "LG-TIMEOUT": 1},
        )
        self.assertEqual(
            cohorts["unknown"]["blocker_code_counts"],
            {"UNK-COMP": 1},
        )

    def test_summarize_m6_11_calibration_unknown_when_summary_head_lookup_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(
                replay_root / "compiler",
                1,
                "patch_valid",
                git_head="SAVED-HEAD",
            )
            self._write_model_failure_bundle(
                replay_root / "failure",
                1,
                "model_failed_timeout",
                git_head="SAVED-HEAD",
            )
            with patch("mew.proof_summary._current_git_head", return_value=""):
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["cohorts"]["unknown"]["total_bundles"], 2)
        self.assertEqual(calibration["cohorts"]["legacy"]["total_bundles"], 0)
        self.assertEqual(calibration["cohorts"]["current_head"]["total_bundles"], 0)

    def test_summarize_m6_11_calibration_non_git_head_lookup_fallback_is_non_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(
                replay_root / "compiler",
                1,
                "patch_valid",
                git_head="SAVED-HEAD",
            )
            with patch(
                "mew.proof_summary.subprocess.run",
                side_effect=OSError("not a git repo"),
            ):
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["cohorts"]["unknown"]["total_bundles"], 1)

    def test_summarize_m6_11_calibration_current_head_matches_top_level_threshold_math(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            with patch("mew.proof_summary._current_git_head", return_value="HEAD-ONLY"):
                for attempt in range(1, 3):
                    self._write_relevant_compiler_bundle(
                        replay_root / "compiler",
                        attempt,
                        "patch_valid",
                        git_head="HEAD-ONLY",
                    )
                for attempt in range(1, 4):
                    self._write_model_failure_bundle(
                        replay_root / "failure_timeout",
                        attempt,
                        "model_failed_timeout",
                        git_head="HEAD-ONLY",
                    )
                for attempt in range(1, 4):
                    self._write_model_failure_bundle(
                        replay_root / "failure_refused",
                        attempt,
                        "model_input_rejected",
                        git_head="HEAD-ONLY",
                    )
                summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        current_head = calibration["cohorts"]["current_head"]
        self.assertEqual(calibration["total_bundles"], current_head["total_bundles"])
        self.assertEqual(
            calibration["bundle_type_counts"],
            {
                "patch_draft_compiler.other": 2,
                "work-loop-model-failure.model_failed_timeout": 3,
                "work-loop-model-failure.model_input_rejected": 3,
            },
        )
        self.assertEqual(
            calibration["dominant_bundle_type"],
            current_head["dominant_bundle_type"],
        )
        self.assertAlmostEqual(
            calibration["dominant_bundle_share"],
            current_head["dominant_bundle_share"],
        )
        self.assertEqual(
            calibration["thresholds"]["off_schema_rate_ok"],
            current_head["thresholds"]["off_schema_rate_ok"],
        )
        self.assertEqual(
            calibration["thresholds"]["refusal_rate_ok"],
            current_head["thresholds"]["refusal_rate_ok"],
        )
        self.assertEqual(
            calibration["thresholds"]["failure_mode_concentration_ok"],
            current_head["thresholds"]["failure_mode_concentration_ok"],
        )

    def test_summarize_m6_11_calibration_off_schema_uses_compiler_denom(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            compiler_root = replay_root / "compiler"
            self._write_relevant_compiler_bundle(compiler_root, 1, "model_returned_non_schema")
            self._write_relevant_compiler_bundle(compiler_root, 2, "patch_valid")
            for attempt in range(1, 21):
                self._write_legacy_report_bundle(replay_root / "legacy", attempt)
            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(calibration["compiler_bundles"], 2)
        self.assertEqual(calibration["total_bundles"], 2)
        self.assertEqual(calibration["off_schema_count"], 1)
        self.assertEqual(calibration["off_schema_denominator"], 2)
        self.assertAlmostEqual(calibration["off_schema_rate"], 0.5, places=6)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 0)
        self.assertFalse(calibration["thresholds"]["off_schema_rate_ok"])

    def test_summarize_m6_11_calibration_threshold_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            failure_root = replay_root / "2026-04-22" / "session-1" / "todo-fail"
            for attempt in range(1, 11):
                attempt_dir = failure_root / f"attempt-{attempt}"
                ProofSummaryTests._write_json(
                    attempt_dir / "replay_metadata.json",
                    {"bundle": "patch_draft_compiler", "files": {"validator_result": "validator_result.json"}},
                )
                ProofSummaryTests._write_json(
                    attempt_dir / "validator_result.json",
                    {"code": "model_returned_non_schema"},
                )
            report_root = replay_root / "2026-04-22" / "session-2" / "todo-refusal"
            report_path = report_root / "attempt-1" / "report.json"
            ProofSummaryTests._write_json(
                report_path,
                {"bundle": "work-loop-model-failure", "failure": {"code": "model_refused"}},
            )
            summary = summarize_m6_11_replay_calibration(replay_root)

        self.assertFalse(summary["ok"])
        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 11)
        self.assertEqual(calibration["off_schema_count"], 10)
        self.assertEqual(calibration["refusal_count"], 1)
        self.assertFalse(calibration["thresholds"]["off_schema_rate_ok"])
        self.assertFalse(calibration["thresholds"]["refusal_rate_ok"])
        self.assertFalse(calibration["thresholds"]["failure_mode_concentration_ok"])
        self.assertTrue(summary["calibration"]["thresholds"]["has_bundles"])

    def test_summarize_m6_11_calibration_malformed_relevant_bundle_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            compiler_root = replay_root / "compiler"
            self._write_relevant_compiler_bundle(compiler_root, 1, "patch_valid")
            malformed_path = compiler_root / "attempt-2" / "replay_metadata.json"
            malformed_path.parent.mkdir(parents=True, exist_ok=True)
            malformed_path.write_text("{", encoding="utf-8")
            summary = summarize_m6_11_replay_calibration(replay_root)

        self.assertFalse(summary["ok"])
        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 1)
        self.assertEqual(calibration["compiler_bundles"], 1)
        self.assertEqual(calibration["malformed_bundle_count"], 1)
        self.assertEqual(calibration["malformed_relevant_bundle_count"], 1)
        self.assertFalse(calibration["thresholds"]["malformed_relevant_bundles_ok"])
        self.assertEqual(len(summary["errors"]), 1)
        self.assertIn("invalid compiler metadata JSON", summary["errors"][0])

    def test_format_m6_11_calibration_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._build_mixed_replay_bundles(replay_root)
            summary = summarize_m6_11_replay_calibration(replay_root)
            rendered = format_proof_summary(summary)

        self.assertIn("mode: m6.11 phase2/phase3 calibration", rendered)
        self.assertIn("calibration_bundles: total=8", rendered)
        self.assertIn("calibration_bundle_types:", rendered)
        self.assertIn("calibration_thresholds:", rendered)
        self.assertIn("off_schema_ok=True", rendered)
        self.assertIn("failure_mode_concentration_ok=True", rendered)
        self.assertIn("malformed_relevant_ok=True", rendered)
        self.assertIn("malformed_bundles:", rendered)
        self.assertIn("cohort[current_head]:", rendered)
        self.assertIn("cohort[legacy]:", rendered)
        self.assertIn("cohort[unknown]:", rendered)
        self.assertIn("cohort[current_head]_rates:", rendered)
        self.assertIn("cohort[current_head]_thresholds:", rendered)

    def test_format_m6_11_calibration_output_includes_measurement_head_cohort(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_model_failure_bundle(
                replay_root / "measurement_timeout",
                1,
                "model_failed_timeout",
                git_head="HEAD-MEASURE",
            )
            summary = summarize_m6_11_replay_calibration(
                replay_root,
                measurement_head="HEAD-MEASURE",
            )
            rendered = format_proof_summary(summary)

        self.assertIn("cohort[measurement_head]: total=1", rendered)
        self.assertIn("cohort[measurement_head]_rates:", rendered)
        self.assertIn("cohort[measurement_head]_thresholds:", rendered)

    def test_format_m6_11_calibration_refusal_breakdown_uses_real_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(replay_root / "compiler", 1, "model_returned_refusal")
            self._write_relevant_compiler_bundle(replay_root / "compiler", 2, "patch_valid")
            self._write_model_failure_bundle(
                replay_root / "failure_refused",
                1,
                "model_refused",
            )
            self._write_model_failure_bundle(
                replay_root / "failure_timeout",
                1,
                "model_failed_timeout",
            )
            summary = summarize_m6_11_replay_calibration(replay_root)
            rendered = format_proof_summary(summary)

        calibration = summary["calibration"]
        self.assertEqual(
            calibration["refusal_by_type"],
            {
                "patch_draft_compiler.refusal": 1,
                "work-loop-model-failure.model_refused": 1,
            },
        )
        self.assertIn("refusal_breakdown=patch_draft_compiler.refusal=1", rendered)
        self.assertIn(
            "work-loop-model-failure.model_refused=1",
            rendered,
        )

    def test_summarize_m6_11_calibration_blocker_code_counts_are_additive(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(
                replay_root / "compiler_other",
                1,
                "patch_valid",
                blocker_code="BK-A",
            )
            self._write_relevant_compiler_bundle(
                replay_root / "compiler_other",
                2,
                "patch_valid",
                blocker_code="BK-B",
            )
            summary = summarize_m6_11_replay_calibration(replay_root)

        calibration = summary["calibration"]
        self.assertEqual(
            calibration["bundle_type_counts"],
            {"patch_draft_compiler.other": 2},
        )
        self.assertEqual(
            calibration["blocker_code_counts"],
            {"BK-A": 1, "BK-B": 1},
        )
        unknown_cohort = calibration["cohorts"]["unknown"]
        self.assertEqual(
            unknown_cohort["bundle_type_counts"],
            {"patch_draft_compiler.other": 2},
        )
        self.assertEqual(
            unknown_cohort["blocker_code_counts"],
            {"BK-A": 1, "BK-B": 1},
        )

    def test_format_m6_11_calibration_blocker_code_breakdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            self._write_relevant_compiler_bundle(
                replay_root / "compiler",
                1,
                "patch_valid",
                blocker_code="CK-1",
            )
            self._write_relevant_compiler_bundle(
                replay_root / "compiler",
                2,
                "patch_valid",
                blocker_code="",
            )
            self._write_model_failure_bundle(
                replay_root / "failure_refused",
                1,
                "model_refused",
                blocker_code="MK-R",
            )
            self._write_model_failure_bundle(
                replay_root / "failure_timeout",
                1,
                "model_failed_timeout",
                blocker_code="MK-T",
            )
            summary = summarize_m6_11_replay_calibration(replay_root)
            rendered = format_proof_summary(summary)

        self.assertEqual(
            summary["calibration"]["blocker_code_counts"],
            {"CK-1": 1, "MK-R": 1, "MK-T": 1},
        )
        self.assertIn(
            "blocker_code_breakdown=CK-1=1, MK-R=1, MK-T=1",
            rendered,
        )
        self.assertIn(
            (
                "cohort[unknown]_rates: "
                "off_schema=0.0000 (0/2) refusal=0.2500 (1/4) "
                "blocker_code_breakdown=CK-1=1, MK-R=1, MK-T=1 "
                "refusal_breakdown=work-loop-model-failure.model_refused=1"
            ),
            rendered,
        )

    def test_summarize_m6_11_calibration_compiler_monoculture_fails_concentration_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            replay_root = Path(tmp)
            for attempt in range(1, 11):
                self._write_relevant_compiler_bundle(replay_root / "compiler", attempt, "patch_valid")
            summary = summarize_m6_11_replay_calibration(replay_root)

        self.assertFalse(summary["ok"])
        calibration = summary["calibration"]
        self.assertEqual(calibration["total_bundles"], 10)
        self.assertEqual(calibration["dominant_bundle_type"], "patch_draft_compiler.other")
        self.assertEqual(calibration["dominant_bundle_share"], 1.0)
        self.assertFalse(calibration["thresholds"]["failure_mode_concentration_ok"])
