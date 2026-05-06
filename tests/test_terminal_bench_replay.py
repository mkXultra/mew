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
    def _write_implement_v2_replay_fixture(self, root):
        trial_dir = Path(root) / "job" / "build-cython-ext__v2fixture"
        agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        v2_dir = agent_dir / "implement_v2"
        verifier_dir = trial_dir / "verifier"
        v2_dir.mkdir(parents=True)
        verifier_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps({"trial_name": "build-cython-ext__v2fixture", "verifier_result": {"reward": 0.0}}),
            encoding="utf-8",
        )
        (verifier_dir / "test-stdout.txt").write_text("FAILED test_ccomplexity - np.int\n", encoding="utf-8")
        (agent_dir / "command-transcript.json").write_text(
            json.dumps({"exit_code": 1, "timed_out": False}),
            encoding="utf-8",
        )
        (agent_dir / "mew-report.json").write_text(
            json.dumps(
                {
                    "work_exit_code": 1,
                    "resume": {},
                    "work_report": {
                        "stop_reason": "implement_v2_blocked",
                        "selected_lane": "implement_v2",
                        "steps": [{"action": {"type": "implement_lane", "lane": "implement_v2"}}],
                        "implement_lane_result": {
                            "lane": "implement_v2",
                            "status": "blocked",
                            "metrics": {
                                "runtime_id": "implement_v2_model_json_tool_loop",
                                "replay_valid": True,
                                "terminal_evidence_count": 2,
                                "write_evidence_count": 1,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (v2_dir / "history.json").write_text(
            json.dumps(
                [
                    {
                        "turn": 1,
                        "tool_calls": [
                            {
                                "tool_name": "run_command",
                                "arguments": {"command": "python - <<'PY'\nPath('/repo').rglob('*.py')\nPY"},
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        (v2_dir / "proof-manifest.json").write_text(
            json.dumps(
                {
                    "tool_results": [
                        {
                            "provider_call_id": "patch-numpy-aliases",
                            "tool_name": "run_command",
                            "status": "failed",
                            "content": [{"exit_code": 1, "stderr": "No module named pytest"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        return trial_dir.parent

    def _write_implement_v2_model_error_fixture(self, root):
        trial_dir = Path(root) / "job" / "feal-differential-cryptanalysis__v2modelerror"
        agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        verifier_dir = trial_dir / "verifier"
        agent_dir.mkdir(parents=True)
        verifier_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps(
                {
                    "trial_name": "feal-differential-cryptanalysis__v2modelerror",
                    "verifier_result": {"reward": 0.0},
                }
            ),
            encoding="utf-8",
        )
        (verifier_dir / "test-stdout.txt").write_text(
            "ModuleNotFoundError: No module named 'attack'\n",
            encoding="utf-8",
        )
        (agent_dir / "command-transcript.json").write_text(
            json.dumps({"exit_code": 1, "timed_out": False}),
            encoding="utf-8",
        )
        parse_error = 'failed to parse JSON plan: Extra data; raw={"summary":"bad"} trailing'
        (agent_dir / "mew-report.json").write_text(
            json.dumps(
                {
                    "work_exit_code": 1,
                    "resume": {},
                    "work_report": {
                        "stop_reason": "implement_v2_failed",
                        "runtime_id": "implement_v2_model_json_tool_loop",
                        "selected_lane": "implement_v2",
                        "steps": [
                            {
                                "status": "failed",
                                "action": {
                                    "type": "implement_lane",
                                    "lane": "implement_v2",
                                    "runtime_id": "implement_v2_model_json_tool_loop",
                                },
                                "error": parse_error,
                                "model_turn": {
                                    "status": "failed",
                                    "model_metrics": {
                                        "runtime_id": "implement_v2_model_json_tool_loop",
                                        "error": parse_error,
                                    },
                                },
                            }
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        return trial_dir.parent

    def _write_implement_v2_max_turns_fixture(self, root):
        trial_dir = Path(root) / "job" / "make-doom-for-mips__v2maxturns"
        agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        v2_dir = agent_dir / "implement_v2"
        verifier_dir = trial_dir / "verifier"
        v2_dir.mkdir(parents=True)
        verifier_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps(
                {
                    "trial_name": "make-doom-for-mips__v2maxturns",
                    "verifier_result": {"reward": 0.0},
                }
            ),
            encoding="utf-8",
        )
        (verifier_dir / "test-stdout.txt").write_text(
            "FAILED test_vm_execution - Timeout waiting for expected stdout\n",
            encoding="utf-8",
        )
        (agent_dir / "command-transcript.json").write_text(
            json.dumps({"exit_code": 1, "timed_out": False}),
            encoding="utf-8",
        )
        max_turns_error = "implement_v2 reached max_turns before finish"
        (agent_dir / "mew-report.json").write_text(
            json.dumps(
                {
                    "work_exit_code": 1,
                    "resume": {},
                    "work_report": {
                        "stop_reason": "implement_v2_blocked",
                        "runtime_id": "implement_v2_model_json_tool_loop",
                        "selected_lane": "implement_v2",
                        "steps": [
                            {
                                "status": "blocked",
                                "action": {
                                    "type": "implement_lane",
                                    "lane": "implement_v2",
                                    "runtime_id": "implement_v2_model_json_tool_loop",
                                },
                                "error": max_turns_error,
                                "model_turn": {
                                    "status": "failed",
                                    "model_metrics": {
                                        "runtime_id": "implement_v2_model_json_tool_loop",
                                        "error": max_turns_error,
                                    },
                                },
                            }
                        ],
                        "implement_lane_result": {
                            "lane": "implement_v2",
                            "status": "blocked",
                            "metrics": {
                                "runtime_id": "implement_v2_model_json_tool_loop",
                                "replay_valid": True,
                                "terminal_evidence_count": 16,
                                "write_evidence_count": 0,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        (v2_dir / "history.json").write_text(
            json.dumps(
                [
                    {
                        "turn": 24,
                        "tool_calls": [
                            {
                                "tool_name": "run_command",
                                "arguments": {"command": "make -f Makefile.mips -j2 && node vm.js"},
                            }
                        ],
                    }
                ]
            ),
            encoding="utf-8",
        )
        (v2_dir / "proof-manifest.json").write_text(
            json.dumps(
                {
                    "tool_results": [
                        {
                            "provider_call_id": "call-rebuild-runtime-t24",
                            "tool_name": "run_command",
                            "status": "failed",
                            "content": [
                                {
                                    "exit_code": 2,
                                    "stderr": "m_misc.c:82:25: error: 'EISDIR' undeclared\nmake: *** [Makefile.mips:13: build-mips/m_misc.o] Error 1\n",
                                    "stdout": "mipsel-linux-gnu-gcc -Os -c m_misc.c -o build-mips/m_misc.o\n",
                                }
                            ],
                        }
                    ],
                    "metrics": {"model_error": {}},
                }
            ),
            encoding="utf-8",
        )
        return trial_dir.parent

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

    def test_replay_terminal_bench_job_accepts_implement_v2_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            text = format_terminal_bench_replay(report)
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(trial["current"]["recomputed"])
            self.assertEqual(current_v2["runtime_id"], "implement_v2_model_json_tool_loop")
            self.assertFalse(current_v2["compiled_source_frontier_observed"])
            self.assertIn("compiled/native source frontier", trial["current"]["next_action"])
            self.assertIn("implement_v2:", text)

    def test_replay_terminal_bench_job_accepts_implement_v2_model_parse_error_without_tool_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_model_error_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="feal-differential-cryptanalysis",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(trial["current"]["recomputed"])
            self.assertEqual(current_v2["model_error"]["failure_class"], "model_json_parse_error")
            self.assertIn("model_json parse failure", trial["current"]["next_action"])

    def test_replay_terminal_bench_job_routes_implement_v2_max_turns_to_latest_terminal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_max_turns_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]
            next_action = trial["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["model_error"]["failure_class"], "max_turns_before_finish")
            self.assertEqual(current_v2["model_error"]["error_type"], "ImplementV2LoopLimit")
            self.assertIn("EISDIR", current_v2["latest_failure"]["stderr_tail"])
            self.assertIn("max-turn limit", next_action)
            self.assertIn("latest failed run_command result", next_action)
            self.assertNotIn("model backend", next_action)
            self.assertNotIn("compiled/native source frontier", next_action)

    def test_replay_terminal_bench_job_prefers_terminal_failure_for_implement_v2_max_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_max_turns_fixture(tmp)
            manifest_path = next(Path(job_dir).rglob("proof-manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"].append(
                {
                    "provider_call_id": "call-read-after-terminal-failure",
                    "tool_name": "read_file",
                    "status": "failed",
                    "content": [{"reason": "missing file after compile failed"}],
                }
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["tool_name"], "run_command")
            self.assertIn("EISDIR", current_v2["latest_failure"]["stderr_tail"])
            self.assertIn("latest failed run_command result", next_action)

    def test_replay_terminal_bench_job_prioritizes_active_command_closeout_over_max_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_max_turns_fixture(tmp)
            manifest_path = next(Path(job_dir).rglob("proof-manifest.json"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"] = [
                {
                    "provider_call_id": "call-final-command",
                    "tool_name": "run_command",
                    "status": "interrupted",
                    "content": [
                        {
                            "reason": "implement_v2 live_json attempt closed before command finalized",
                            "kill_status": "process_group_terminated",
                        }
                    ],
                }
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["active_command_closeout_failed"])
            self.assertIn("active command closeout", next_action)
            self.assertNotIn("max-turn limit", next_action)

    def test_replay_terminal_bench_job_detects_implement_v2_active_command_closeout_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            v2_dir = (
                Path(job_dir)
                / "build-cython-ext__v2fixture"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
            )
            (v2_dir / "history.json").write_text(
                json.dumps(
                    [
                        {
                            "turn": 1,
                            "tool_calls": [
                                {
                                    "tool_name": "glob",
                                    "arguments": {"path": "/app/pyknotid", "pattern": "**/*.pyx"},
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "final-command",
                                "tool_name": "run_command",
                                "status": "interrupted",
                                "content": [
                                    {
                                        "command_run_id": "command-final",
                                        "reason": "implement_v2 live_json attempt closed before command finalized",
                                        "kill_status": "process_group_terminated",
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["compiled_source_frontier_observed"])
            self.assertTrue(current_v2["active_command_closeout_failed"])
            self.assertIn("active command closeout", trial["current"]["next_action"])

    def test_replay_terminal_bench_job_does_not_debug_completed_implement_v2_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_exit_code"] = 0
            report["work_report"]["stop_reason"] = "finish"
            report["work_report"]["implement_lane_result"]["status"] = "completed"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            (trial_dir / "result.json").write_text(
                json.dumps({"trial_name": "build-cython-ext__v2fixture", "verifier_result": {"reward": 1.0}}),
                encoding="utf-8",
            )

            replay = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 0, "external_reward": 1.0},
            )
            next_action = replay["trials"][0]["current"]["next_action"]

            self.assertEqual(replay["status"], "pass")
            self.assertIn("record implement_v2 pass", next_action)
            self.assertNotIn("debug implement_v2 divergence", next_action)

    def test_replay_terminal_bench_job_debugs_completed_implement_v2_with_zero_reward(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_exit_code"] = 0
            report["work_report"]["stop_reason"] = "finish"
            report["work_report"]["implement_lane_result"]["status"] = "completed"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            (trial_dir / "result.json").write_text(
                json.dumps({"trial_name": "build-cython-ext__v2fixture", "verifier_result": {"reward": 0.0}}),
                encoding="utf-8",
            )

            replay = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 0, "external_reward": 0.0},
            )
            next_action = replay["trials"][0]["current"]["next_action"]

            self.assertEqual(replay["status"], "pass")
            self.assertIn("external verifier reward 0 after v2 completed", next_action)
            self.assertIn("finish acceptance gate", next_action)
            self.assertNotIn("record implement_v2 pass", next_action)

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
