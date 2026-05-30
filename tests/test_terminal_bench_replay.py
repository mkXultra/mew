import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from mew.cli import build_parser
from mew.dogfood import (
    _write_expected_artifact_contract_emulator_fixture,
    _write_repository_test_tail_emulator_fixture,
    _write_runtime_artifact_latency_emulator_fixture,
    _write_runtime_producer_blocked_emulator_fixture,
    _write_terminal_bench_replay_fixture,
)
from mew.implement_lane.native_transcript import NativeTranscript, NativeTranscriptItem, write_native_transcript_artifacts
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

    def _write_native_transcript_replay_fixture(
        self,
        root,
        *,
        response_items_drift=False,
        stale_legacy_dir=False,
        empty_transcript=False,
        non_tool_only=False,
        invalid_manifest_pairing=False,
        missing_manifest_pairing=False,
    ):
        trial_dir = Path(root) / "job" / "make-mips-interpreter__nativefixture"
        agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        verifier_dir = trial_dir / "verifier"
        trace_dir = agent_dir / "normalized-trace"
        agent_dir.mkdir(parents=True)
        verifier_dir.mkdir(parents=True)
        trace_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps({"trial_name": "make-mips-interpreter__nativefixture", "verifier_result": {"reward": 0.0}}),
            encoding="utf-8",
        )
        (verifier_dir / "test-stdout.txt").write_text("VM fault: program halted before rendering a frame\n", encoding="utf-8")
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
                        "runtime_id": "implement_v2_native_transcript_loop",
                        "steps": [{"action": {"type": "implement_lane", "lane": "implement_v2"}}],
                        "implement_lane_result": {
                            "lane": "implement_v2",
                            "status": "blocked",
                            "metrics": {
                                "runtime_id": "implement_v2_native_transcript_loop",
                                "provider_native_tool_loop": True,
                                "transport_kind": "provider_native",
                                "model_json_main_path_detected": False,
                            },
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
        lane_attempt_id = "native-replay:task-1"
        transcript_items = ()
        if non_tool_only:
            transcript_items = (
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="input_message",
                    output_text_or_ref="task input",
                ),
                NativeTranscriptItem(
                    sequence=2,
                    turn_id="turn-1",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="assistant_message",
                    output_text_or_ref="I will inspect the task.",
                ),
            )
        elif not empty_transcript:
            transcript_items = (
                NativeTranscriptItem(
                    sequence=1,
                    turn_id="turn-1",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-read",
                    tool_name="read_file",
                    arguments_json_text='{"path":"vm.js"}',
                ),
                NativeTranscriptItem(
                    sequence=2,
                    turn_id="turn-1",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-read",
                    tool_name="read_file",
                    status="completed",
                    output_text_or_ref="read_file result: completed",
                ),
                NativeTranscriptItem(
                    sequence=3,
                    turn_id="turn-2",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-edit",
                    tool_name="edit_file",
                    arguments_json_text='{"path":"vm.js","old_string":"x","new_string":"y"}',
                ),
                NativeTranscriptItem(
                    sequence=4,
                    turn_id="turn-2",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-edit",
                    tool_name="edit_file",
                    status="completed",
                    output_text_or_ref="edit_file result: completed",
                ),
                NativeTranscriptItem(
                    sequence=5,
                    turn_id="turn-3",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call",
                    call_id="call-test",
                    tool_name="run_tests",
                    arguments_json_text='{"command":"node vm.js"}',
                ),
                NativeTranscriptItem(
                    sequence=6,
                    turn_id="turn-3",
                    lane_attempt_id=lane_attempt_id,
                    provider="openai",
                    model="gpt-5.5",
                    kind="function_call_output",
                    call_id="call-test",
                    tool_name="run_tests",
                    status="failed",
                    is_error=True,
                    output_text_or_ref="run_tests result: failed; exit_code=1; stderr_tail: VM fault",
                ),
            )
        transcript = NativeTranscript(
            lane_attempt_id=lane_attempt_id,
            provider="openai",
            model="gpt-5.5",
            items=transcript_items,
        )
        write_native_transcript_artifacts(agent_dir, transcript)
        (trace_dir / "summary.json").write_text(
            json.dumps({"turn_count": 3, "command_count": 1, "edit_count": 1, "verifier_count": 1, "parse_error_count": 0}),
            encoding="utf-8",
        )
        if response_items_drift:
            (agent_dir / "response_items.jsonl").write_text("", encoding="utf-8")
        if stale_legacy_dir:
            stale = agent_dir / "implement_v2"
            stale.mkdir()
            (stale / "proof-manifest.json").write_text(json.dumps({"tool_results": []}), encoding="utf-8")
            (stale / "history.json").write_text("[]", encoding="utf-8")
        if invalid_manifest_pairing:
            manifest_path = agent_dir / "proof-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["pairing"] = {"valid": False, "errors": ["forced_invalid"], "call_count": 0, "output_count": 0}
            manifest["metrics"]["pairing_valid"] = False
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        if missing_manifest_pairing:
            manifest_path = agent_dir / "proof-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.pop("pairing", None)
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
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

    def _write_implement_v2_external_artifact_mismatch_fixture(self, root):
        trial_dir = Path(root) / "job" / "make-mips-interpreter__v2externalartifact"
        agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
        v2_dir = agent_dir / "implement_v2"
        verifier_dir = trial_dir / "verifier"
        v2_dir.mkdir(parents=True)
        verifier_dir.mkdir(parents=True)
        (trial_dir / "result.json").write_text(
            json.dumps(
                {
                    "trial_name": "make-mips-interpreter__v2externalartifact",
                    "verifier_result": {"reward": 0.0},
                }
            ),
            encoding="utf-8",
        )
        (verifier_dir / "test-stdout.txt").write_text(
            "E FileNotFoundError: [Errno 2] No such file or directory: '/tmp/frame.bmp'\n",
            encoding="utf-8",
        )
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
                            }
                        ],
                        "implement_lane_result": {
                            "lane": "implement_v2",
                            "status": "blocked",
                            "metrics": {
                                "runtime_id": "implement_v2_model_json_tool_loop",
                                "replay_valid": True,
                                "terminal_evidence_count": 1,
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
                        "turn": 1,
                        "tool_calls": [
                            {
                                "tool_name": "run_command",
                                "arguments": {"command": "node vm.js && test -s /app/frame000000.bmp"},
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
                            "provider_call_id": "failed-hidden-path-probe",
                            "tool_name": "run_command",
                            "status": "failed",
                            "content": [
                                {
                                    "exit_code": 1,
                                    "stdout": "attempted /tmp/frame.bmp but failed before final verification\n",
                                    "execution_contract_normalized": {
                                        "role": "runtime",
                                        "stage": "verification",
                                        "purpose": "verification",
                                        "proof_role": "verifier",
                                        "acceptance_kind": "external_verifier",
                                    },
                                    "artifact_evidence": [
                                        {
                                            "evidence_id": "artifact-evidence:/tmp/frame.bmp",
                                            "artifact_id": "/tmp/frame.bmp",
                                            "path": "/tmp/frame.bmp",
                                            "status": "passed",
                                        }
                                    ],
                                    "verifier_evidence": {
                                        "verifier_id": "verifier:failed-hidden-path-probe",
                                        "verdict": "pass",
                                    },
                                }
                            ],
                        },
                        {
                            "provider_call_id": "verify-final-frame",
                            "tool_name": "run_command",
                            "status": "completed",
                            "content": [
                                {
                                    "exit_code": 0,
                                    "stdout": "FRAME_QUALITY_OK 640x400 saved frame000000.bmp\n",
                                    "execution_contract_normalized": {
                                        "role": "runtime",
                                        "stage": "verification",
                                        "purpose": "verification",
                                        "proof_role": "verifier",
                                        "acceptance_kind": "external_verifier",
                                    },
                                    "artifact_evidence": [
                                        {
                                            "evidence_id": "artifact-evidence:/tmp/vmout.txt",
                                            "artifact_id": "/tmp/vmout.txt",
                                            "path": "/tmp/vmout.txt",
                                            "status": "passed",
                                        },
                                        {
                                            "evidence_id": "artifact-evidence:/app/frame000000.bmp",
                                            "artifact_id": "/app/frame000000.bmp",
                                            "path": "/app/frame000000.bmp",
                                            "status": "passed",
                                        }
                                    ],
                                    "verifier_evidence": {
                                        "verifier_id": "verifier:verify-final-frame",
                                        "verdict": "pass",
                                    },
                                }
                            ],
                        }
                    ],
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

    def test_cli_replay_terminal_bench_json_asserts_source_output_contract_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_external_artifact_mismatch_fixture(tmp)
            manifest_path = (
                Path(job_dir)
                / "make-mips-interpreter__v2externalartifact"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
                / "proof-manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"].insert(
                0,
                {
                    "provider_call_id": "read-runtime-source",
                    "tool_name": "read_file",
                    "status": "completed",
                    "content": [
                        {
                            "mew_status": "completed",
                            "content": [
                                {
                                    "path": "src/runtime.c",
                                    "text": (
                                        'void render(void) { FILE *fp = fopen("/tmp/frame.bmp", "wb"); '
                                        "fwrite(buf, 1, n, fp); }"
                                    ),
                                }
                            ],
                        }
                    ],
                },
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            parser = build_parser()
            args = parser.parse_args(
                [
                    "replay",
                    "terminal-bench",
                    "--job-dir",
                    str(job_dir),
                    "--task",
                    "make-mips-interpreter",
                    "--assert-source-output-contract-path",
                    "/tmp/frame.bmp",
                    "--json",
                ]
            )
            stdout = io.StringIO()

            with contextlib.redirect_stdout(stdout):
                exit_code = args.func(args)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["status"], "pass")
            check_names = {check["name"] for check in payload["checks"]}
            self.assertIn("source_output_contract_path", check_names)

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

    def test_replay_terminal_bench_job_accepts_native_transcript_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(trial["current"]["recomputed"])
            self.assertEqual(current_v2["runtime_id"], "implement_v2_native_transcript_loop")
            self.assertEqual(current_v2["native_transcript"]["response_items_match"], True)
            self.assertEqual(current_v2["history_turn_count"], 3)
            self.assertEqual(current_v2["write_evidence_count"], 1)
            self.assertEqual(current_v2["latest_failure"]["tool_name"], "run_tests")
            self.assertIn("latest failed run_tests", trial["current"]["next_action"])

    def test_replay_terminal_bench_job_ignores_native_low_signal_active_closeout_for_prior_runtime_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp)
            agent_dir = next(Path(job_dir).rglob("unknown-task"))
            lane_attempt_id = "native-replay:task-1"
            transcript = NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider="openai",
                model="gpt-5.5",
                items=(
                    NativeTranscriptItem(
                        sequence=1,
                        turn_id="turn-1",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-runtime",
                        tool_name="run_tests",
                        arguments_json_text='{"command":"node vm.js"}',
                    ),
                    NativeTranscriptItem(
                        sequence=2,
                        turn_id="turn-1",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-runtime",
                        tool_name="run_tests",
                        status="yielded",
                        output_text_or_ref=(
                            "run_tests result: yielded; status=yielded; command_run_id=cmd-1; "
                            "stdout_tail: DoomGeneric initialized. Frames will be saved to /tmp/frame.bmp "
                            "Error: Unknown format specifier '%c'"
                        ),
                    ),
                    NativeTranscriptItem(
                        sequence=3,
                        turn_id="turn-2",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-poll",
                        tool_name="poll_command",
                        arguments_json_text='{"command_run_id":"cmd-1"}',
                    ),
                    NativeTranscriptItem(
                        sequence=4,
                        turn_id="turn-2",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-poll",
                        tool_name="poll_command",
                        status="yielded",
                        output_text_or_ref=(
                            "poll_command result: yielded; status=yielded; command_run_id=cmd-1; "
                            "stdout_tail: DoomGeneric initialized. Frames will be saved to /tmp/frame.bmp "
                            "Error: Unknown format specifier '%c'"
                        ),
                    ),
                    NativeTranscriptItem(
                        sequence=5,
                        turn_id="turn-3-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-active-command-closeout-003",
                        tool_name="poll_command",
                        arguments_json_text='{"command_run_id":"cmd-1","wait_seconds":26.0}',
                    ),
                    NativeTranscriptItem(
                        sequence=6,
                        turn_id="turn-3-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-active-command-closeout-003",
                        tool_name="poll_command",
                        status="failed",
                        is_error=True,
                        output_text_or_ref=(
                            "poll_command result: failed; error=true; status=timed_out; "
                            "command_run_id=cmd-1; stderr_tail: command timed out after 26 second(s)"
                        ),
                    ),
                ),
            )
            write_native_transcript_artifacts(agent_dir, transcript)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "call-poll")
            self.assertEqual(current_v2["latest_failure"]["source"], "native_transcript_prior_terminal_output")
            self.assertEqual(
                current_v2["latest_failure"]["suppressed_closeout_provider_call_id"],
                "call-active-command-closeout-003",
            )
            self.assertIn("Unknown format specifier", current_v2["latest_failure"]["stdout_tail"])
            self.assertFalse(current_v2["active_command_closeout_failed"])

    def test_replay_terminal_bench_job_keeps_native_active_closeout_when_no_prior_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp)
            agent_dir = next(Path(job_dir).rglob("unknown-task"))
            lane_attempt_id = "native-replay:task-1"
            transcript = NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider="openai",
                model="gpt-5.5",
                items=(
                    NativeTranscriptItem(
                        sequence=1,
                        turn_id="turn-1-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-active-command-closeout-001",
                        tool_name="poll_command",
                        arguments_json_text='{"command_run_id":"cmd-1","wait_seconds":0.01}',
                    ),
                    NativeTranscriptItem(
                        sequence=2,
                        turn_id="turn-1-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-active-command-closeout-001",
                        tool_name="poll_command",
                        status="failed",
                        is_error=True,
                        output_text_or_ref=(
                            "poll_command result: failed; error=true; status=timed_out; "
                            "command_run_id=cmd-1; stderr_tail: command timed out after 0.01 second(s)"
                        ),
                    ),
                ),
            )
            write_native_transcript_artifacts(agent_dir, transcript)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "call-active-command-closeout-001")
            self.assertTrue(current_v2["active_command_closeout_failed"])

    def test_replay_terminal_bench_job_keeps_native_closeout_when_prior_signal_is_different_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp)
            agent_dir = next(Path(job_dir).rglob("unknown-task"))
            lane_attempt_id = "native-replay:task-1"
            transcript = NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider="openai",
                model="gpt-5.5",
                items=(
                    NativeTranscriptItem(
                        sequence=1,
                        turn_id="turn-1",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-old-runtime",
                        tool_name="run_tests",
                        arguments_json_text='{"command":"node old.js"}',
                    ),
                    NativeTranscriptItem(
                        sequence=2,
                        turn_id="turn-1",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-old-runtime",
                        tool_name="run_tests",
                        status="yielded",
                        output_text_or_ref=(
                            "run_tests result: yielded; status=yielded; command_run_id=cmd-old; "
                            "stdout_tail: useful but unrelated runtime output"
                        ),
                    ),
                    NativeTranscriptItem(
                        sequence=3,
                        turn_id="turn-2-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-active-command-closeout-002",
                        tool_name="poll_command",
                        arguments_json_text='{"command_run_id":"cmd-new","wait_seconds":0.01}',
                    ),
                    NativeTranscriptItem(
                        sequence=4,
                        turn_id="turn-2-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-active-command-closeout-002",
                        tool_name="poll_command",
                        status="failed",
                        is_error=True,
                        output_text_or_ref=(
                            "poll_command result: failed; error=true; status=timed_out; "
                            "command_run_id=cmd-new; stderr_tail: command timed out after 0.01 second(s)"
                        ),
                    ),
                ),
            )
            write_native_transcript_artifacts(agent_dir, transcript)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "call-active-command-closeout-002")
            self.assertTrue(current_v2["active_command_closeout_failed"])

    def test_replay_terminal_bench_job_does_not_keep_stale_native_closeout_after_later_terminal_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp)
            agent_dir = next(Path(job_dir).rglob("unknown-task"))
            lane_attempt_id = "native-replay:task-1"
            transcript = NativeTranscript(
                lane_attempt_id=lane_attempt_id,
                provider="openai",
                model="gpt-5.5",
                items=(
                    NativeTranscriptItem(
                        sequence=1,
                        turn_id="turn-1-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-active-command-closeout-001",
                        tool_name="poll_command",
                        arguments_json_text='{"command_run_id":"cmd-1","wait_seconds":0.01}',
                    ),
                    NativeTranscriptItem(
                        sequence=2,
                        turn_id="turn-1-active-command-closeout",
                        lane_attempt_id=lane_attempt_id,
                        provider="native-controller",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-active-command-closeout-001",
                        tool_name="poll_command",
                        status="failed",
                        is_error=True,
                        output_text_or_ref=(
                            "poll_command result: failed; error=true; status=timed_out; "
                            "command_run_id=cmd-1; stderr_tail: command timed out after 0.01 second(s)"
                        ),
                    ),
                    NativeTranscriptItem(
                        sequence=3,
                        turn_id="turn-2",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call",
                        call_id="call-real-failure",
                        tool_name="run_tests",
                        arguments_json_text='{"command":"node vm.js"}',
                    ),
                    NativeTranscriptItem(
                        sequence=4,
                        turn_id="turn-2",
                        lane_attempt_id=lane_attempt_id,
                        provider="openai",
                        model="gpt-5.5",
                        kind="function_call_output",
                        call_id="call-real-failure",
                        tool_name="run_tests",
                        status="failed",
                        is_error=True,
                        output_text_or_ref="run_tests result: failed; exit_code=1; stderr_tail: real terminal failure",
                    ),
                ),
            )
            write_native_transcript_artifacts(agent_dir, transcript)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "call-real-failure")
            self.assertFalse(current_v2["active_command_closeout_failed"])

    def test_replay_terminal_bench_job_prefers_root_native_artifact_over_stale_legacy_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, stale_legacy_dir=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["runtime_id"], "implement_v2_native_transcript_loop")
            self.assertEqual(current_v2["native_transcript"]["item_count"], 6)

    def test_replay_terminal_bench_job_keeps_legacy_when_root_native_manifest_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            agent_dir = next(Path(job_dir).rglob("unknown-task"))
            (agent_dir / "response_transcript.json").write_text(
                json.dumps({"items": [{"sequence": 1, "kind": "assistant_message"}]}),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["runtime_id"], "implement_v2_model_json_tool_loop")
            self.assertEqual(current_v2["history_turn_count"], 1)

    def test_replay_terminal_bench_job_keeps_legacy_when_legacy_dir_has_stray_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            v2_dir = next(Path(job_dir).rglob("implement_v2"))
            (v2_dir / "response_transcript.json").write_text(
                json.dumps({"items": [{"sequence": 1, "kind": "assistant_message"}]}),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["runtime_id"], "implement_v2_model_json_tool_loop")
            self.assertEqual(current_v2["history_turn_count"], 1)

    def test_replay_terminal_bench_job_rejects_invalid_native_transcript_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, response_items_drift=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            trial = report["trials"][0]

            self.assertEqual(report["status"], "fail")
            self.assertFalse(trial["current"]["recomputed"])
            self.assertIn("replay_valid=false", trial["current"]["replay_error"])

    def test_replay_terminal_bench_job_rejects_empty_native_transcript_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, empty_transcript=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["trials"][0]["current"]["recomputed"])

    def test_replay_terminal_bench_job_rejects_non_tool_only_native_transcript_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, non_tool_only=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["trials"][0]["current"]["recomputed"])

    def test_replay_terminal_bench_job_rejects_invalid_native_manifest_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, invalid_manifest_pairing=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["trials"][0]["current"]["recomputed"])

    def test_replay_terminal_bench_job_rejects_missing_native_manifest_pairing(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_native_transcript_replay_fixture(tmp, missing_manifest_pairing=True)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )

            self.assertEqual(report["status"], "fail")
            self.assertFalse(report["trials"][0]["current"]["recomputed"])

    def test_replay_terminal_bench_job_recomputes_expected_artifact_classification(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_expected_artifact_contract_emulator_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                    "structured_execution_replay_required": True,
                    "structured_failure_class": "runtime_artifact_missing",
                    "structured_replay_mismatch_count": 0,
                },
            )
            text = format_terminal_bench_replay(report)
            trial = report["trials"][0]
            current_v2 = trial["current"]["implement_v2"]
            structured_replay = current_v2["structured_execution_replay"]
            latest = structured_replay["latest_failure_classification"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(structured_replay["classification_count"], 2)
            self.assertEqual(structured_replay["mismatch_count"], 0)
            self.assertEqual(latest["class"], "runtime_artifact_missing")
            self.assertEqual(current_v2["latest_failure"]["source"], "recomputed_structured_execution_evidence")
            self.assertIn("expected runtime artifact", trial["current"]["next_action"])
            self.assertIn("runtime_artifact_missing", text)

    def test_replay_terminal_bench_job_extracts_external_expected_artifact_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_external_artifact_mismatch_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["runtime_artifact_contract_mismatch"])
            self.assertEqual(current_v2["external_expected_artifact_missing"], ["/tmp/frame.bmp"])
            self.assertNotIn("/tmp/vmout.txt", current_v2["passed_structured_artifacts"])
            self.assertIn("/tmp/frame.bmp", next_action)
            self.assertIn("external verifier expected runtime artifact", next_action)

    def test_replay_terminal_bench_job_asserts_source_output_contract_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_external_artifact_mismatch_fixture(tmp)
            manifest_path = (
                Path(job_dir)
                / "make-mips-interpreter__v2externalartifact"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
                / "proof-manifest.json"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"].insert(
                0,
                {
                    "provider_call_id": "read-runtime-source",
                    "tool_name": "read_file",
                    "status": "completed",
                    "content": [
                        {
                            "mew_status": "completed",
                            "content": [
                                {
                                    "path": "src/runtime.c",
                                    "text": (
                                        'void render(void) { FILE *fp = fopen("/tmp/frame.bmp", "wb"); '
                                        "fwrite(buf, 1, n, fp); }"
                                    ),
                                }
                            ],
                        }
                    ],
                },
            )
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            replay = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={
                    "source_output_contract_path": "/tmp/frame.bmp",
                },
            )
            current_v2 = replay["trials"][0]["current"]["implement_v2"]

            self.assertEqual(replay["status"], "pass")
            self.assertEqual(current_v2["source_output_contract_path"], "/tmp/frame.bmp")

    def test_replay_terminal_bench_job_routes_runtime_producer_blocked_before_path_alignment(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_runtime_producer_blocked_emulator_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["external_expected_artifact_missing"], ["/tmp/frame.bmp"])
            self.assertEqual(current_v2["latest_failure"]["failure_class"], "runtime_artifact_missing")
            self.assertEqual(current_v2["passed_structured_artifacts"], [])
            self.assertIn("runtime producer/resource/syscall frontier", next_action)
            self.assertIn("/tmp/frame.bmp", next_action)
            self.assertNotIn("align the final runtime artifact contract", next_action)

    def test_replay_terminal_bench_job_prefers_raw_contract_when_stored_normalized_vocabulary_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_expected_artifact_contract_emulator_fixture(tmp)
            v2_dir = (
                Path(job_dir)
                / "make-doom-for-mips__expected-artifact-contract"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
            )
            manifest_path = v2_dir / "proof-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload = manifest["tool_results"][-1]["content"][0]
            artifact = payload["execution_contract_normalized"]["expected_artifacts"][0]
            stale_normalized = dict(payload["execution_contract_normalized"])
            stale_normalized.update(
                {
                    "role": "unknown",
                    "proof_role": "none",
                    "acceptance_kind": "not_acceptance",
                    "substeps": [],
                }
            )
            payload["execution_contract_normalized"] = stale_normalized
            payload["execution_contract"] = {
                "id": stale_normalized["id"],
                "role": "generated_artifact",
                "stage": "verification",
                "purpose": "verification",
                "proof_role": "final_verifier",
                "acceptance_kind": "artifact_and_runtime_verification",
                "expected_exit": {"mode": "any"},
                "expected_artifacts": [artifact],
            }
            payload["failure_classification"]["phase"] = "unknown"
            payload["failure_classification"]["class"] = "artifact_validation_failure"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                    "structured_execution_replay_required": True,
                    "structured_failure_class": "runtime_artifact_missing",
                    "structured_replay_mismatch_count": 1,
                },
            )
            structured_replay = report["trials"][0]["current"]["implement_v2"]["structured_execution_replay"]
            latest = structured_replay["latest_failure_classification"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(latest["class"], "runtime_artifact_missing")
            self.assertEqual(latest["phase"], "runtime")
            self.assertEqual(structured_replay["mismatches"][0]["stored"]["class"], "artifact_validation_failure")
            self.assertEqual(structured_replay["mismatches"][0]["recomputed"]["class"], "runtime_artifact_missing")

    def test_replay_terminal_bench_job_reports_stored_classification_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_expected_artifact_contract_emulator_fixture(tmp)
            v2_dir = (
                Path(job_dir)
                / "make-doom-for-mips__expected-artifact-contract"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
            )
            manifest_path = v2_dir / "proof-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"][-1]["content"][0]["failure_classification"]["class"] = "build_failure"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                    "structured_execution_replay_required": True,
                    "structured_failure_class": "runtime_artifact_missing",
                },
            )
            structured_replay = report["trials"][0]["current"]["implement_v2"]["structured_execution_replay"]
            failed_checks = [check for check in report["checks"] if not check["passed"]]

            self.assertEqual(report["status"], "fail")
            self.assertEqual(structured_replay["mismatch_count"], 1)
            self.assertEqual(structured_replay["mismatches"][0]["stored"]["class"], "build_failure")
            self.assertEqual(structured_replay["mismatches"][0]["recomputed"]["class"], "runtime_artifact_missing")
            self.assertTrue(
                any(check["name"].endswith(":structured_execution_classification_matches") for check in failed_checks)
            )

    def test_replay_terminal_bench_job_reports_stored_evidence_ref_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_expected_artifact_contract_emulator_fixture(tmp)
            v2_dir = (
                Path(job_dir)
                / "make-doom-for-mips__expected-artifact-contract"
                / "agent"
                / "terminal-bench-harbor-smoke"
                / "unknown-task"
                / "implement_v2"
            )
            manifest_path = v2_dir / "proof-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["tool_results"][-1]["content"][0]["failure_classification"]["evidence_refs"] = [
                {"kind": "artifact_evidence", "id": "stale-artifact-evidence"}
            ]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            report = replay_terminal_bench_job(
                job_dir,
                task="make-doom-for-mips",
                assertions={
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                    "structured_execution_replay_required": True,
                    "structured_failure_class": "runtime_artifact_missing",
                },
            )
            structured_replay = report["trials"][0]["current"]["implement_v2"]["structured_execution_replay"]

            self.assertEqual(report["status"], "fail")
            self.assertEqual(structured_replay["mismatch_count"], 1)
            self.assertEqual(
                structured_replay["mismatches"][0]["stored"]["evidence_refs"],
                [{"kind": "artifact_evidence", "id": "stale-artifact-evidence"}],
            )

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

    def test_replay_terminal_bench_job_routes_model_timeout_after_missing_target_to_first_write_stall(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_model_error_fixture(tmp)
            trial_dir = Path(job_dir) / "feal-differential-cryptanalysis__v2modelerror"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            verifier_dir = trial_dir / "verifier"
            v2_dir = agent_dir / "implement_v2"
            v2_dir.mkdir(parents=True)
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_report"]["implement_lane_result"] = {
                "lane": "implement_v2",
                "status": "blocked",
                "metrics": {
                    "runtime_id": "implement_v2_model_json_tool_loop",
                    "replay_valid": True,
                    "terminal_evidence_count": 1,
                    "write_evidence_count": 0,
                    "model_error": {
                        "failure_class": "model_timeout",
                        "error_type": "ModelBackendError",
                        "message": "request timed out",
                    },
                },
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            verifier_dir.joinpath("test-stdout.txt").write_text(
                "AssertionError: expected /tmp/frame.bmp but it does not exist\n",
                encoding="utf-8",
            )
            v2_dir.joinpath("history.json").write_text(
                json.dumps(
                    [
                        {
                            "turn": 1,
                            "summary": "probe source and then inspect missing target before patch",
                            "tool_calls": [
                                {
                                    "id": "call-probe-source",
                                    "name": "run_command",
                                    "arguments": {"command": "find . -maxdepth 2 -type f"},
                                },
                                {
                                    "id": "call-read-target",
                                    "name": "read_file",
                                    "arguments": {"path": "vm.js"},
                                },
                            ],
                        },
                        {"turn": 2, "summary": "model_json_error", "model_error": {"message": "request timed out"}},
                    ]
                ),
                encoding="utf-8",
            )
            v2_dir.joinpath("proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "call-probe-source",
                                "tool_name": "run_command",
                                "status": "completed",
                                "content": [{"exit_code": 0, "stdout": "main.c\n"}],
                            },
                            {
                                "provider_call_id": "call-read-target",
                                "tool_name": "read_file",
                                "status": "failed",
                                "content": [{"reason": "path does not exist: /app/vm.js"}],
                            },
                        ],
                        "metrics": {
                            "model_error": {
                                "failure_class": "model_timeout",
                                "error_type": "ModelBackendError",
                                "message": "request timed out",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="feal-differential-cryptanalysis",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["first_write_frontier_stall"]["detected"])
            self.assertEqual(current_v2["first_write_frontier_stall"]["target_path"], "vm.js")
            self.assertIn("first_write_frontier_stall", next_action)
            self.assertIn("write_file/edit_file/apply_patch", next_action)
            self.assertNotIn("external verifier expected runtime artifact", next_action)

    def test_replay_terminal_bench_job_does_not_route_tmp_artifact_missing_read_to_first_write_stall(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_model_error_fixture(tmp)
            trial_dir = Path(job_dir) / "feal-differential-cryptanalysis__v2modelerror"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            v2_dir = agent_dir / "implement_v2"
            v2_dir.mkdir(parents=True)
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_report"]["implement_lane_result"] = {
                "lane": "implement_v2",
                "status": "blocked",
                "metrics": {
                    "runtime_id": "implement_v2_model_json_tool_loop",
                    "replay_valid": True,
                    "terminal_evidence_count": 1,
                    "write_evidence_count": 0,
                    "model_error": {
                        "failure_class": "model_timeout",
                        "error_type": "ModelBackendError",
                        "message": "request timed out",
                    },
                },
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            v2_dir.joinpath("history.json").write_text(
                json.dumps(
                    [
                        {
                            "turn": 1,
                            "tool_calls": [
                                {"id": "call-probe-source", "name": "run_command", "arguments": {"command": "ls"}},
                                {
                                    "id": "call-read-artifact",
                                    "name": "read_file",
                                    "arguments": {"path": "/tmp/frame.bmp"},
                                },
                            ],
                        },
                        {"turn": 2, "summary": "model_json_error", "model_error": {"message": "request timed out"}},
                    ]
                ),
                encoding="utf-8",
            )
            v2_dir.joinpath("proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "call-probe-source",
                                "tool_name": "run_command",
                                "status": "completed",
                                "content": [{"exit_code": 0, "stdout": "main.c\n"}],
                            },
                            {
                                "provider_call_id": "call-read-artifact",
                                "tool_name": "read_file",
                                "status": "failed",
                                "content": [{"reason": "path does not exist: /tmp/frame.bmp"}],
                            },
                        ],
                        "metrics": {
                            "model_error": {
                                "failure_class": "model_timeout",
                                "error_type": "ModelBackendError",
                                "message": "request timed out",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="feal-differential-cryptanalysis",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["first_write_frontier_stall"], {})
            self.assertNotIn("first_write_frontier_stall", next_action)

    def test_replay_terminal_bench_job_recomputes_write_count_before_first_write_stall(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_model_error_fixture(tmp)
            trial_dir = Path(job_dir) / "feal-differential-cryptanalysis__v2modelerror"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            v2_dir = agent_dir / "implement_v2"
            v2_dir.mkdir(parents=True)
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_report"]["implement_lane_result"] = {
                "lane": "implement_v2",
                "status": "blocked",
                "metrics": {
                    "runtime_id": "implement_v2_model_json_tool_loop",
                    "replay_valid": True,
                    "terminal_evidence_count": 1,
                    "write_evidence_count": 0,
                    "model_error": {
                        "failure_class": "model_timeout",
                        "error_type": "ModelBackendError",
                        "message": "request timed out",
                    },
                },
            }
            report_path.write_text(json.dumps(report), encoding="utf-8")
            v2_dir.joinpath("history.json").write_text(
                json.dumps(
                    [
                        {
                            "turn": 1,
                            "tool_calls": [
                                {"id": "call-probe-source", "name": "run_command", "arguments": {"command": "ls"}},
                                {
                                    "id": "call-write-target",
                                    "name": "write_file",
                                    "arguments": {"path": "vm.js", "content": "ok\n"},
                                },
                                {"id": "call-read-target", "name": "read_file", "arguments": {"path": "vm.js"}},
                            ],
                        },
                        {"turn": 2, "summary": "model_json_error", "model_error": {"message": "request timed out"}},
                    ]
                ),
                encoding="utf-8",
            )
            v2_dir.joinpath("proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "call-probe-source",
                                "tool_name": "run_command",
                                "status": "completed",
                                "content": [{"exit_code": 0, "stdout": "main.c\n"}],
                            },
                            {
                                "provider_call_id": "call-write-target",
                                "tool_name": "write_file",
                                "status": "completed",
                                "content": [{"written": True}],
                                "side_effects": [{"kind": "file_write", "path": "vm.js", "dry_run": False}],
                            },
                            {
                                "provider_call_id": "call-read-target",
                                "tool_name": "read_file",
                                "status": "failed",
                                "content": [{"reason": "path does not exist: /app/vm.js"}],
                            },
                        ],
                        "metrics": {
                            "model_error": {
                                "failure_class": "model_timeout",
                                "error_type": "ModelBackendError",
                                "message": "request timed out",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="feal-differential-cryptanalysis",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["write_evidence_count"], 1)
            self.assertEqual(current_v2["first_write_frontier_stall"], {})

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

    def test_replay_terminal_bench_job_does_not_treat_product_timeout_summary_as_model_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            agent_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task"
            report_path = agent_dir / "mew-report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["work_report"]["implement_lane_result"]["updated_lane_state"] = {
                "lane_hard_runtime_frontier": {
                    "latest_runtime_failure": {"failure_summary": "VM_RC=124 no frame"}
                }
            }
            report["work_report"]["steps"] = [
                {
                    "status": "blocked",
                    "error": (
                        "node vm.js timed out with VM_RC=124 and /tmp/frame.bmp was not produced"
                    ),
                    "action": {
                        "type": "implement_lane",
                        "lane": "implement_v2",
                        "runtime_id": "implement_v2_model_json_tool_loop",
                    },
                    "model_turn": {
                        "status": "failed",
                        "error": "node vm.js timed out with VM_RC=124 and /tmp/frame.bmp was not produced",
                        "model_metrics": {
                            "runtime_id": "implement_v2_model_json_tool_loop",
                            "model_error": {},
                        },
                    },
                }
            ]
            report_path.write_text(json.dumps(report), encoding="utf-8")
            v2_dir = agent_dir / "implement_v2"
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "fix-vm-jalr-decode-and-verify",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [
                                    {
                                        "exit_code": 1,
                                        "stdout_tail": (
                                            "PATCHED vm.js JALR decode variables\n"
                                            "VM_RC=124\n"
                                            "--- vm stdout tail ---\n"
                                        ),
                                        "stderr_tail": "--- vm stderr tail ---\n",
                                    }
                                ],
                            }
                        ],
                        "metrics": {"model_error": {}},
                    }
                ),
                encoding="utf-8",
            )

            report = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 0.0},
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["model_error"], {})
            self.assertIn("latest failed run_command result", next_action)
            self.assertNotIn("model backend", next_action)

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

    def test_replay_terminal_bench_job_detects_budget_exhausted_closeout_only_gap(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "final-closeout",
                                "tool_name": "run_command",
                                "status": "interrupted",
                                "content": [
                                    {
                                        "command_run_id": "cmd-final",
                                        "reason": "implement_v2 active command closeout budget exhausted",
                                        "status": "killed",
                                        "kill_status": "process_group_terminated",
                                        "exit_code": None,
                                        "stdout": "",
                                        "stderr": "",
                                        "stdout_tail": "",
                                        "stderr_tail": "",
                                        "output_bytes": 0,
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
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "final-closeout")
            self.assertTrue(current_v2["active_command_closeout_failed"])
            self.assertIn("active command closeout", trial["current"]["next_action"])

    def test_replay_terminal_bench_job_keeps_closeout_gap_when_only_prior_failure_is_closeout(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "prior-closeout",
                                "tool_name": "run_command",
                                "status": "interrupted",
                                "content": [
                                    {
                                        "reason": "implement_v2 live_json attempt closed before command finalized",
                                        "kill_status": "process_group_terminated",
                                    }
                                ],
                            },
                            {
                                "provider_call_id": "final-budget-closeout",
                                "tool_name": "run_command",
                                "status": "interrupted",
                                "content": [
                                    {
                                        "command_run_id": "cmd-final",
                                        "reason": "implement_v2 active command closeout budget exhausted",
                                        "status": "killed",
                                        "exit_code": None,
                                        "stdout": "",
                                        "stderr": "",
                                        "stdout_tail": "",
                                        "stderr_tail": "",
                                        "output_bytes": 0,
                                    }
                                ],
                            },
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
            self.assertTrue(current_v2["active_command_closeout_failed"])
            self.assertIn("active command closeout", trial["current"]["next_action"])

    def test_replay_terminal_bench_job_ignores_low_signal_closeout_for_latest_runtime_frontier(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            (trial_dir / "verifier" / "test-stdout.txt").write_text(
                "FileNotFoundError: [Errno 2] No such file or directory: '/tmp/frame.bmp'\n",
                encoding="utf-8",
            )
            v2_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "implement_v2"
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "prior-runtime-missing",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [
                                    {
                                        "command_run_id": "cmd-prior",
                                        "exit_code": 1,
                                        "status": "failed",
                                        "stdout": "NO_FRAME\n",
                                        "stdout_tail": "NO_FRAME\n",
                                        "tool_run_record": {
                                            "record_id": "record-prior",
                                            "command_run_id": "cmd-prior",
                                            "status": "failed",
                                            "exit_code": 1,
                                            "semantic_exit": {"ok": False, "category": "nonzero_exit"},
                                            "stdout_preview": "NO_FRAME\n",
                                            "stderr_preview": "",
                                        },
                                        "execution_contract": {
                                            "role": "runtime",
                                            "stage": "verification",
                                            "purpose": "verification",
                                            "proof_role": "verifier",
                                            "acceptance_kind": "external_verifier",
                                            "expected_exit": 0,
                                            "expected_artifacts": [
                                                {
                                                    "path": "/tmp/frame.bmp",
                                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                                }
                                            ],
                                        },
                                        "artifact_evidence": [
                                            {
                                                "evidence_id": "artifact-prior",
                                                "path": "/tmp/frame.bmp",
                                                "status": "failed",
                                                "blocking": True,
                                                "checks": [
                                                    {
                                                        "type": "exists",
                                                        "passed": False,
                                                        "severity": "blocking",
                                                    }
                                                ],
                                            }
                                        ],
                                    }
                                ],
                            },
                            {
                                "provider_call_id": "final-closeout",
                                "tool_name": "run_command",
                                "status": "interrupted",
                                "content": [
                                    {
                                        "command_run_id": "cmd-final",
                                        "reason": "implement_v2 active command closeout budget exhausted",
                                        "status": "killed",
                                        "kill_status": "process_group_terminated",
                                        "exit_code": None,
                                        "stdout": "",
                                        "stderr": "",
                                        "stdout_tail": "",
                                        "stderr_tail": "",
                                        "output_bytes": 0,
                                        "tool_run_record": {
                                            "record_id": "record-final",
                                            "command_run_id": "cmd-final",
                                            "status": "killed",
                                            "exit_code": None,
                                            "interrupted": True,
                                            "semantic_exit": {"ok": False, "category": "interrupted"},
                                            "stdout_preview": "",
                                            "stderr_preview": "",
                                        },
                                        "execution_contract": {
                                            "role": "runtime",
                                            "stage": "final_verifier",
                                            "proof_role": "verifier",
                                            "acceptance_kind": "external_verifier",
                                            "expected_exit": 0,
                                            "expected_artifacts": [
                                                {
                                                    "path": "/tmp/frame.bmp",
                                                    "checks": [{"type": "exists", "severity": "blocking"}],
                                                }
                                            ],
                                        },
                                    }
                                ],
                            },
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
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["latest_failure"]["provider_call_id"], "prior-runtime-missing")
            self.assertEqual(current_v2["latest_failure"]["failure_class"], "runtime_artifact_missing")
            self.assertEqual(current_v2["latest_failure"]["failure_kind"], "missing_artifact")
            self.assertIn("NO_FRAME", current_v2["latest_failure"]["stdout_tail"])
            self.assertFalse(current_v2["active_command_closeout_failed"])
            self.assertIn("runtime producer", next_action)
            self.assertNotIn("active command closeout", next_action)

    def test_replay_terminal_bench_job_routes_run_tests_shell_surface_to_tool_contract_recovery(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "final-shell-verifier",
                                "tool_name": "run_tests",
                                "status": "failed",
                                "content": [
                                    {
                                        "failure_class": "tool_contract_misuse",
                                        "failure_subclass": "run_tests_shell_surface",
                                        "recoverable_tool_contract_misuse": True,
                                        "suggested_tool": "run_command",
                                        "suggested_use_shell": True,
                                        "preserved_command": "printf ok > frame.txt && test -s frame.txt",
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
            next_action = trial["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["tool_contract_shell_surface_misuse"])
            self.assertFalse(current_v2["tool_contract_recovery_observed"])
            self.assertIn("recover run_tests shell-surface verifier through run_command", next_action)
            self.assertNotIn("compiled/native source frontier", next_action)

    def test_replay_terminal_bench_job_routes_legacy_run_tests_shell_surface_reason(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "legacy-final-shell-verifier",
                                "tool_name": "run_tests",
                                "status": "failed",
                                "content": [
                                    {
                                        "reason": (
                                            "run_tests executes one argv command without a shell; "
                                            "use run_command for shell orchestration"
                                        )
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
            next_action = trial["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertTrue(current_v2["tool_contract_shell_surface_misuse"])
            self.assertTrue(current_v2["tool_contract_shell_surface_misuse_seen"])
            self.assertFalse(current_v2["tool_contract_recovery_observed"])
            self.assertIn("recover run_tests shell-surface verifier through run_command", next_action)

    def test_replay_terminal_bench_job_prefers_later_real_terminal_failure_over_old_tool_contract_misuse(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "old-shell-verifier",
                                "tool_name": "run_tests",
                                "status": "failed",
                                "content": [
                                    {
                                        "failure_class": "tool_contract_misuse",
                                        "failure_subclass": "run_tests_shell_surface",
                                        "recoverable_tool_contract_misuse": True,
                                        "suggested_tool": "run_command",
                                    }
                                ],
                            },
                            {
                                "provider_call_id": "later-real-failure",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [{"exit_code": 2, "stderr_tail": "real linker failure"}],
                            },
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
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertFalse(current_v2["tool_contract_shell_surface_misuse"])
            self.assertIn("latest failed run_command result", next_action)
            self.assertNotIn("recover run_tests shell-surface", next_action)

    def test_replay_terminal_bench_job_demotes_legacy_runtime_artifact_contract_mismatch(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "vm-verify",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [
                                    {
                                        "exit_code": 1,
                                        "stdout_tail": (
                                            "ELF Header: Data: 2's complement, big endian\n"
                                            "Machine: MIPS R3000\n"
                                            "vm.js reads instructions with readUInt32LE\n"
                                            "Execution error at PC=0x4002e8: Unknown opcode: 0x10\n"
                                        ),
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
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]
            marker_fallback = current_v2["legacy_runtime_marker_fallback"]

            self.assertEqual(report["status"], "pass")
            self.assertFalse(current_v2["runtime_artifact_contract_mismatch"])
            self.assertTrue(marker_fallback["detected"])
            self.assertFalse(marker_fallback["active"])
            self.assertEqual(marker_fallback["confidence"], "low")
            self.assertNotIn("artifact ABI/ISA/endianness/entrypoint", next_action)

    def test_replay_terminal_bench_job_uses_latest_failure_for_runtime_artifact_contract_mismatch(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "old-vm-verify",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [
                                    {
                                        "exit_code": 1,
                                        "stdout_tail": (
                                            "ELF Header: Data: 2's complement, big endian\n"
                                            "Execution error at PC=0x4002e8: Unknown opcode: 0x10\n"
                                        ),
                                    }
                                ],
                            },
                            {
                                "provider_call_id": "later-linker-failure",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [{"exit_code": 2, "stderr_tail": "undefined reference to StatDump"}],
                            },
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
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertFalse(current_v2["runtime_artifact_contract_mismatch"])
            self.assertIn("debug implement_v2 divergence", next_action)
            self.assertNotIn("artifact ABI/ISA/endianness/entrypoint", next_action)

    def test_replay_terminal_bench_job_ignores_runtime_mismatch_markers_in_command_text_only(self):
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
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "marker-grep-only",
                                "tool_name": "run_command",
                                "status": "failed",
                                "content": [
                                    {
                                        "command": (
                                            "grep -nE 'Unknown opcode|readUInt32LE|ELF|big endian' vm.js"
                                        ),
                                        "exit_code": 1,
                                        "stdout_tail": "no vm mismatch found",
                                        "stderr_tail": "",
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
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertFalse(current_v2["runtime_artifact_contract_mismatch"])
            self.assertNotIn("artifact ABI/ISA/endianness/entrypoint", next_action)

    def test_replay_terminal_bench_job_routes_external_runtime_artifact_lifecycle_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = _write_runtime_artifact_latency_emulator_fixture(tmp)

            report = replay_terminal_bench_job(
                job_dir,
                task="make-mips-interpreter",
                assertions={
                    "mew_exit_code": 1,
                    "external_reward": 0.0,
                    "next_action_contains": "runtime_artifact_latency_contract",
                    "structured_replay_mismatch_count": 0,
                },
            )
            current_v2 = report["trials"][0]["current"]["implement_v2"]
            next_action = report["trials"][0]["current"]["next_action"]

            self.assertEqual(report["status"], "pass")
            self.assertEqual(current_v2["external_verifier_missing_artifacts"], ["/tmp/frame.bmp"])
            self.assertEqual(current_v2["external_expected_artifact_missing"], [])
            self.assertIn("/tmp/frame.bmp", current_v2["passed_structured_artifacts"])
            self.assertIn("external-verifier-shaped lifecycle/cwd/latency proof", next_action)

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

    def test_replay_terminal_bench_job_projects_final_verifier_pass_after_saved_blocked_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            v2_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "implement_v2"
            (trial_dir / "result.json").write_text(
                json.dumps({"trial_name": "build-cython-ext__v2fixture", "verifier_result": {"reward": 1.0}}),
                encoding="utf-8",
            )
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "final-verifier-pass",
                                "tool_name": "run_command",
                                "status": "completed",
                                "content": [
                                    {
                                        "execution_contract": {
                                            "role": "runtime",
                                            "stage": "final-verifier",
                                            "proof_role": "verifier",
                                            "acceptance_kind": "external_verifier",
                                        },
                                        "verifier_evidence": {"verdict": "pass"},
                                        "artifact_evidence": [
                                            {
                                                "artifact_id": "/tmp/frame.bmp",
                                                "path": "/tmp/frame.bmp",
                                                "status": "passed",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            replay = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 1.0},
            )
            current_v2 = replay["trials"][0]["current"]["implement_v2"]
            next_action = replay["trials"][0]["current"]["next_action"]

            self.assertEqual(replay["status"], "pass")
            self.assertEqual(current_v2["lane_status"], "completed")
            self.assertIn("record implement_v2 pass", next_action)
            self.assertNotIn("debug implement_v2 divergence", next_action)

    def test_replay_terminal_bench_job_does_not_project_empty_artifact_id_as_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_dir = self._write_implement_v2_replay_fixture(tmp)
            trial_dir = Path(job_dir) / "build-cython-ext__v2fixture"
            v2_dir = trial_dir / "agent" / "terminal-bench-harbor-smoke" / "unknown-task" / "implement_v2"
            (trial_dir / "result.json").write_text(
                json.dumps({"trial_name": "build-cython-ext__v2fixture", "verifier_result": {"reward": 1.0}}),
                encoding="utf-8",
            )
            (v2_dir / "proof-manifest.json").write_text(
                json.dumps(
                    {
                        "tool_results": [
                            {
                                "provider_call_id": "final-verifier-pass",
                                "tool_name": "run_command",
                                "status": "completed",
                                "content": [
                                    {
                                        "execution_contract": {
                                            "role": "runtime",
                                            "stage": "final-verifier",
                                            "proof_role": "verifier",
                                            "acceptance_kind": "external_verifier",
                                        },
                                        "verifier_evidence": {"verdict": "pass"},
                                        "artifact_evidence": [
                                            {
                                                "artifact_id": "   ",
                                                "path": " /tmp/verifier-output.log ",
                                                "artifact_path": "",
                                                "status": "passed",
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            replay = replay_terminal_bench_job(
                job_dir,
                task="build-cython-ext",
                assertions={"mew_exit_code": 1, "external_reward": 1.0},
            )
            current_v2 = replay["trials"][0]["current"]["implement_v2"]

            self.assertEqual(replay["status"], "pass")
            self.assertEqual(current_v2["lane_status"], "blocked")

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
