import unittest

from mew.metrics import build_observation_metrics, format_observation_metrics
from mew.state import default_state


class MetricsTests(unittest.TestCase):
    def test_observation_metrics_summarize_reliability_and_latency(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Observe metrics", "kind": "coding", "status": "ready"})
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:00:20Z",
                "notes": [
                    {"created_at": "2026-04-19T00:00:14Z", "text": "Before the failed verification."},
                    {"created_at": "2026-04-19T00:00:17Z", "text": "Recovered manually after rollback."},
                    {"created_at": "2026-04-19T00:00:19Z", "text": "Later unrelated note."},
                ],
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:03Z",
                        "model_metrics": {
                            "context_chars": 12345,
                            "work_session_chars": 10000,
                            "resume_chars": 1000,
                            "tool_context_chars": 8000,
                            "model_turn_context_chars": 500,
                            "active_memory_chars": 456,
                            "active_memory_entries": 2,
                            "recent_read_window_chars": 789,
                            "recent_read_window_count": 1,
                            "think": {"prompt_chars": 111, "elapsed_seconds": 7.5},
                            "act": {"prompt_chars": 222, "elapsed_seconds": 2.0, "mode": "model"},
                            "total_model_seconds": 9.5,
                            "reasoning_effort": "medium",
                            "prompt_context_mode": "compact_memory",
                        },
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:08Z",
                        "finished_at": "2026-04-19T00:00:10Z",
                    },
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "read_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:04Z",
                        "finished_at": "2026-04-19T00:00:05Z",
                        "result": {},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "rejected",
                        "started_at": "2026-04-19T00:00:12Z",
                        "finished_at": "2026-04-19T00:00:13Z",
                        "parameters": {
                            "path": "tests/test_metrics.py",
                            "summary": "Try a speculative metrics assertion.",
                            "reason": "Exercise rejected dry-run diagnostics.",
                        },
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 3,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:15Z",
                        "finished_at": "2026-04-19T00:00:16Z",
                        "parameters": {"path": "src/mew/metrics.py"},
                        "result": {
                            "dry_run": False,
                            "written": True,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_metrics.py",
                                "stderr": "FAILED tests/test_metrics.py::MetricsTests::test_example",
                            },
                        },
                    },
                    {
                        "id": 4,
                        "tool": "run_tests",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:18Z",
                        "finished_at": "2026-04-19T00:00:18Z",
                        "result": {"verification_exit_code": "not-an-exit-code"},
                    },
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["sessions"]["total"], 1)
        self.assertEqual(metrics["reliability"]["completion_ratio"], 1.0)
        self.assertEqual(metrics["reliability"]["rates"]["approval_rejection"], 1.0)
        self.assertEqual(metrics["reliability"]["rates"]["verification_failure"], 1.0)
        self.assertEqual(metrics["reliability"]["rates"]["interventions_per_session"], 3.0)
        self.assertEqual(metrics["reliability"]["approvals"]["rejected"], 1)
        self.assertEqual(metrics["reliability"]["verification"]["failed"], 1)
        self.assertEqual(metrics["reliability"]["verification"]["rolled_back"], 1)
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["tool_call_id"], 3)
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["command"], "uv run pytest -q tests/test_metrics.py")
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["session_status"], "closed")
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["task_status"], "ready")
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["note_count"], 3)
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["related_note_count"], 1)
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["latest_note"], "Recovered manually after rollback.")
        self.assertEqual(metrics["diagnostics"]["approval_friction"][0]["tool_call_id"], 2)
        self.assertEqual(metrics["diagnostics"]["approval_friction"][0]["path"], "tests/test_metrics.py")
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["avg"], 3.0)
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["median"], 3.0)
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["p95"], 3.0)
        self.assertEqual(metrics["latency"]["model_to_tool_wait_seconds"]["avg"], 1.0)
        self.assertEqual(metrics["latency"]["tool_to_next_model_wait_seconds"]["avg"], 3.0)
        self.assertEqual(metrics["latency"]["model_resume_wait_seconds"]["avg"], 3.0)
        self.assertEqual(metrics["latency"]["approval_bound_wait_seconds"]["count"], 0)
        self.assertEqual(metrics["latency"]["perceived_idle_ratio"]["avg"], 0.588)
        self.assertEqual(metrics["self_hosting"]["first_think_latency_seconds"]["avg"], 7.5)
        self.assertEqual(metrics["self_hosting"]["first_edit_proposal_seconds"]["avg"], 11.0)
        self.assertEqual(metrics["self_hosting"]["context_chars"]["avg"], 12345.0)
        self.assertEqual(metrics["self_hosting"]["work_session_chars"]["avg"], 10000.0)
        self.assertEqual(metrics["self_hosting"]["resume_chars"]["avg"], 1000.0)
        self.assertEqual(metrics["self_hosting"]["tool_context_chars"]["avg"], 8000.0)
        self.assertEqual(metrics["self_hosting"]["model_turn_context_chars"]["avg"], 500.0)
        self.assertEqual(metrics["self_hosting"]["active_memory_chars"]["avg"], 456.0)
        self.assertEqual(metrics["self_hosting"]["active_memory_entries"]["avg"], 2.0)
        self.assertEqual(metrics["self_hosting"]["recent_read_window_chars"]["avg"], 789.0)
        self.assertEqual(metrics["self_hosting"]["recent_read_window_count"]["avg"], 1.0)
        self.assertEqual(metrics["self_hosting"]["think_prompt_chars"]["avg"], 111.0)
        self.assertEqual(metrics["self_hosting"]["act_prompt_chars"]["avg"], 222.0)
        self.assertEqual(metrics["self_hosting"]["total_model_seconds"]["avg"], 9.5)
        self.assertEqual(metrics["self_hosting"]["reasoning_efforts"], {"medium": 1})
        self.assertEqual(metrics["self_hosting"]["prompt_context_modes"], {"compact_memory": 1})
        signal_ids = {signal["id"] for signal in metrics["signals"]}
        self.assertIn("approval_friction", signal_ids)
        self.assertIn("verification_friction", signal_ids)

        text = format_observation_metrics(metrics)
        self.assertIn("Mew observation metrics", text)
        self.assertIn("interventions=3", text)
        self.assertIn("rates: completion=1.0 interventions_per_session=3.0", text)
        self.assertIn("perceived_idle_ratio: count=1 avg=0.588 median=0.588 p95=0.588 max=0.588", text)
        self.assertIn("self_hosting:", text)
        self.assertIn("reasoning_efforts: medium=1", text)
        self.assertIn("prompt_context_modes: compact_memory=1", text)
        self.assertIn("first_think_latency_seconds: count=1 avg=7.5", text)
        self.assertIn("first_edit_proposal_seconds: count=1 avg=11.0", text)
        self.assertIn("context_chars: count=1 avg=12345.0", text)
        self.assertIn("tool_context_chars: count=1 avg=8000.0", text)
        self.assertIn("recent_read_window_chars: count=1 avg=789.0", text)
        self.assertIn("recent_read_window_count: count=1 avg=1.0", text)
        self.assertIn("signals:", text)
        self.assertIn("verification failures are frequent", text)
        self.assertIn("diagnostics:", text)
        self.assertIn("verification_failures:", text)
        self.assertIn("approval_friction:", text)
        self.assertIn("uv run pytest -q tests/test_metrics.py", text)
        self.assertIn("latest_note: Recovered manually after rollback.", text)

    def test_observation_metrics_limit_uses_activity_time_not_cleanup_updated_at(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Old cleanup", "kind": "coding", "status": "done"})
        state["tasks"].append({"id": 2, "title": "Recent work", "kind": "coding", "status": "done"})
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-18T00:00:00Z",
                "updated_at": "2026-04-19T12:47:00Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "started_at": "2026-04-18T00:00:01Z",
                        "finished_at": "2026-04-18T00:00:02Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "read_file",
                        "status": "completed",
                        "started_at": "2026-04-18T00:00:03Z",
                        "finished_at": "2026-04-18T00:00:04Z",
                        "result": {},
                    }
                ],
            }
        )
        state["work_sessions"].append(
            {
                "id": 2,
                "task_id": 2,
                "status": "closed",
                "created_at": "2026-04-19T12:00:00Z",
                "updated_at": "2026-04-19T12:00:10Z",
                "model_turns": [
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T12:00:01Z",
                        "finished_at": "2026-04-19T12:00:09Z",
                    }
                ],
                "tool_calls": [],
            }
        )

        metrics = build_observation_metrics(state, kind="coding", limit=1)

        self.assertEqual(metrics["sessions"]["total"], 1)
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"], [])
        self.assertEqual(metrics["latency"]["perceived_idle_ratio"]["count"], 1)
        self.assertLess(metrics["latency"]["perceived_idle_ratio"]["max"], 0.9)

    def test_observation_metrics_include_latency_diagnostic_samples(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Observe latency", "kind": "coding", "status": "ready"})
        state["work_sessions"].append(
            {
                "id": 7,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:02:00Z",
                "notes": [{"text": "Manual implementation and verification happened outside recorded tools."}],
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:45Z",
                        "finished_at": "2026-04-19T00:00:46Z",
                    },
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "read_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "README.md"},
                        "result": {"path": "README.md", "text": "ok"},
                    }
                ],
            }
        )
        state["work_sessions"].append(
            {
                "id": 8,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:03:00Z",
                "model_turns": [],
                "tool_calls": [],
            }
        )
        state["work_sessions"].append(
            {
                "id": 9,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [
                    {
                        "id": 3,
                        "status": "completed",
                        "summary": "Long planning before first tool.",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 3,
                        "tool": "search_text",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:45Z",
                        "finished_at": "2026-04-19T00:00:46Z",
                        "parameters": {"path": "src/mew"},
                        "result": {},
                    }
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["latency"]["perceived_idle_ratio"]["count"], 2)
        self.assertEqual(metrics["diagnostics"]["slow_first_tools"][0]["session_id"], 9)
        self.assertEqual(metrics["diagnostics"]["slow_first_tools"][0]["first_tool_start_seconds"], 44.0)
        self.assertEqual(metrics["diagnostics"]["slow_first_tools"][0]["first_model_turn_id"], 3)
        self.assertIn("Long planning", metrics["diagnostics"]["slow_first_tools"][0]["first_model_summary"])
        self.assertEqual(metrics["diagnostics"]["slow_model_resumes"][0]["model_resume_wait_seconds"], 41.0)
        self.assertEqual(metrics["diagnostics"]["slow_model_resumes"][0]["wait_seconds"], 41.0)
        self.assertEqual(metrics["diagnostics"]["slow_model_resumes"][0]["next_model_turn_id"], 2)
        high_idle_session_ids = [sample["session_id"] for sample in metrics["diagnostics"]["high_idle_sessions"]]
        self.assertEqual(high_idle_session_ids[:2], [9, 7])
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][0]["idle_ratio"], 0.956)
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][0]["wall_scope"], "model_tool_loop")
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][1]["idle_ratio"], 0.933)
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][1]["tool_call_count"], 1)
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][1]["model_turn_count"], 2)
        self.assertEqual(metrics["diagnostics"]["high_idle_sessions"][1]["note_count"], 1)
        self.assertIn("Manual implementation", metrics["diagnostics"]["high_idle_sessions"][1]["latest_note"])

        text = format_observation_metrics(metrics)
        self.assertIn("slow_first_tools:", text)
        self.assertIn("first_tool_start=44.0s first_turn=#3", text)
        self.assertIn("first_model_summary: Long planning before first tool.", text)
        self.assertIn("slow_model_resumes:", text)
        self.assertIn("model_wait=41.0s raw_wait=41.0s", text)
        self.assertIn("high_idle_sessions:", text)
        self.assertIn("idle_ratio=0.956", text)
        self.assertIn("tools=1 turns=2 notes=1", text)
        self.assertIn("latest_note: Manual implementation", text)

    def test_observation_metrics_surface_slow_first_edit_proposal_samples(self):
        state = default_state()
        state["tasks"].append({"id": 42, "title": "Slow first edit", "kind": "coding", "status": "ready"})
        state["tasks"].append({"id": 43, "title": "Threshold first edit", "kind": "coding", "status": "ready"})
        state["work_sessions"].append(
            {
                "id": 77,
                "task_id": 42,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:30Z",
                "model_turns": [
                    {
                        "id": 101,
                        "status": "completed",
                        "summary": "Mapped telemetry before edit.",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:01:10Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 201,
                        "tool": "read_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/metrics.py"},
                        "result": {"path": "src/mew/metrics.py"},
                    },
                    {
                        "id": 202,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:01:21Z",
                        "finished_at": "2026-04-19T00:01:22Z",
                        "parameters": {"path": "src/mew/metrics.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                ],
            }
        )
        state["work_sessions"].append(
            {
                "id": 78,
                "task_id": 43,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:00:32Z",
                "model_turns": [
                    {
                        "id": 102,
                        "status": "completed",
                        "summary": "Reached exact threshold.",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:10Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 203,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:31Z",
                        "finished_at": "2026-04-19T00:00:32Z",
                        "parameters": {"path": "src/mew/metrics.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["self_hosting"]["first_edit_proposal_seconds"]["max"], 80.0)
        slow_samples = metrics["diagnostics"]["slow_first_edit_proposals"]
        self.assertEqual([item["session_id"] for item in slow_samples], [77])
        sample = slow_samples[0]
        self.assertEqual(sample["session_id"], 77)
        self.assertEqual(sample["task_id"], 42)
        self.assertEqual(sample["task_title"], "Slow first edit")
        self.assertEqual(sample["task_status"], "ready")
        self.assertEqual(sample["first_edit_proposal_seconds"], 80.0)
        self.assertEqual(sample["first_write_tool_call_id"], 202)
        self.assertEqual(sample["first_write_tool"], "edit_file")
        self.assertEqual(sample["first_write_path"], "src/mew/metrics.py")
        self.assertEqual(sample["started_at"], "2026-04-19T00:01:21Z")
        self.assertEqual(sample["first_model_turn_id"], 101)
        self.assertIn("Mapped telemetry", sample["first_model_summary"])

    def test_first_tool_latency_starts_at_first_model_turn_when_session_was_dormant(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Observe dormant session", "kind": "coding", "status": "ready"})
        state["work_sessions"].append(
            {
                "id": 12,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T02:00:10Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "started_at": "2026-04-19T02:00:00Z",
                        "finished_at": "2026-04-19T02:00:04Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "search_text",
                        "status": "completed",
                        "started_at": "2026-04-19T02:00:05Z",
                        "finished_at": "2026-04-19T02:00:06Z",
                        "parameters": {"path": "src/mew"},
                        "result": {},
                    }
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["avg"], 5.0)
        self.assertEqual(metrics["diagnostics"]["slow_first_tools"], [])
        self.assertNotIn("slow_first_tool", {signal["id"] for signal in metrics["signals"]})

    def test_observation_metrics_retire_historical_friction_after_later_success(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Retire old friction", "kind": "coding", "status": "done"})
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:40Z",
                        "finished_at": "2026-04-19T00:00:41Z",
                    }
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "rejected",
                        "rejected_at": "2026-04-19T00:00:30Z",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "tests/test_metrics.py", "reason": "Needs paired source."},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "tests/test_metrics.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_metrics.py",
                                "stdout": "FAILED tests/test_metrics.py::MetricsTests::old",
                            },
                        },
                    },
                ],
            }
        )
        state["work_sessions"].append(
            {
                "id": 2,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:02:00Z",
                "updated_at": "2026-04-19T00:02:10Z",
                "model_turns": [],
                "tool_calls": [
                    {
                        "id": 3,
                        "tool": "run_tests",
                        "status": "completed",
                        "started_at": "2026-04-19T00:02:01Z",
                        "finished_at": "2026-04-19T00:02:02Z",
                        "parameters": {"command": "uv run pytest -q tests/test_metrics.py"},
                        "result": {
                            "command": "uv run pytest -q tests/test_metrics.py",
                            "exit_code": 0,
                            "finished_at": "2026-04-19T00:02:02Z",
                        },
                    }
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertIsNone(metrics["reliability"]["rates"]["approval_rejection"])
        self.assertEqual(metrics["reliability"]["rates"]["verification_failure"], 0.0)
        self.assertEqual(metrics["diagnostics"]["approval_friction"], [])
        self.assertEqual(metrics["diagnostics"]["verification_failures"], [])
        self.assertEqual(metrics["diagnostics"]["approval_bound_waits"], [])
        self.assertEqual(metrics["latency"]["approval_bound_wait_seconds"]["count"], 0)
        self.assertEqual(metrics["diagnostics"]["retired_approval_friction"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["retired_verification_failures"][0]["tool_call_id"], 2)
        self.assertNotIn("approval_friction", {signal["id"] for signal in metrics["signals"]})
        self.assertNotIn("verification_friction", {signal["id"] for signal in metrics["signals"]})

    def test_observation_metrics_retire_same_task_user_reported_completion_verification(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Manual recovery", "kind": "coding", "status": "done"})
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:30Z",
                        "finished_at": "2026-04-19T00:00:31Z",
                    },
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "failed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/dogfood.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "src/mew/dogfood.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_dogfood.py -k m2_comparative",
                                "stdout": "FAILED tests/test_dogfood.py::DogfoodTests::old",
                            },
                        },
                    },
                ],
            }
        )
        state["verification_runs"].append(
            {
                "id": 1,
                "task_id": 1,
                "reason": "user-reported completion verification",
                "command": "user-reported",
                "exit_code": 0,
                "stdout": "Ran focused pytest and unittest; both passed.",
                "finished_at": "2026-04-19T00:02:00Z",
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertIsNone(metrics["reliability"]["rates"]["approval_rejection"])
        self.assertIsNone(metrics["reliability"]["rates"]["verification_failure"])
        self.assertEqual(metrics["diagnostics"]["approval_friction"], [])
        self.assertEqual(metrics["diagnostics"]["verification_failures"], [])
        self.assertEqual(metrics["diagnostics"]["retired_approval_friction"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["retired_verification_failures"][0]["tool_call_id"], 2)

    def test_observation_metrics_retire_same_task_done_validation_note(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Manual recovery",
                "kind": "coding",
                "status": "done",
                "notes": "Validation: focused dogfood passed; tests/test_brief.py passed; committed.",
                "updated_at": "2026-04-19T00:02:00Z",
            }
        )
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "notes": [
                    {"text": "Recovered manually after rollback."},
                    {"text": "Validated and committed in follow-up task chain."},
                ],
                "model_turns": [],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "failed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_brief.py",
                                "stdout": "FAILED tests/test_brief.py::BriefTests::old",
                            },
                        },
                    },
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertIsNone(metrics["reliability"]["rates"]["approval_rejection"])
        self.assertIsNone(metrics["reliability"]["rates"]["verification_failure"])
        self.assertEqual(metrics["diagnostics"]["approval_friction"], [])
        self.assertEqual(metrics["diagnostics"]["verification_failures"], [])
        self.assertEqual(metrics["diagnostics"]["retired_approval_friction"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["retired_verification_failures"][0]["tool_call_id"], 2)

    def test_observation_metrics_retire_same_task_done_task_chain_verification(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Manual recovery", "kind": "coding", "status": "done"})
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "failed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_brief.py",
                                "stdout": "FAILED tests/test_brief.py::BriefTests::old",
                            },
                        },
                    },
                ],
            }
        )
        state["verification_runs"].append(
            {
                "id": 1,
                "task_id": 1,
                "reason": "task-chain verification",
                "command": "user-reported",
                "exit_code": 0,
                "stdout": "Focused recovery checks passed.",
                "finished_at": "2026-04-19T00:02:00Z",
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertIsNone(metrics["reliability"]["rates"]["approval_rejection"])
        self.assertIsNone(metrics["reliability"]["rates"]["verification_failure"])
        self.assertEqual(metrics["diagnostics"]["approval_friction"], [])
        self.assertEqual(metrics["diagnostics"]["verification_failures"], [])
        self.assertEqual(metrics["diagnostics"]["retired_approval_friction"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["retired_verification_failures"][0]["tool_call_id"], 2)

    def test_observation_metrics_keep_done_task_friction_without_validation_note(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Manual recovery",
                "kind": "coding",
                "status": "done",
                "notes": "Closed after discussion; validation not run.",
                "updated_at": "2026-04-19T00:02:00Z",
            }
        )
        state["work_sessions"].append(
            {
                "id": 1,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "failed",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 2,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:05Z",
                        "finished_at": "2026-04-19T00:00:06Z",
                        "parameters": {"path": "src/mew/brief.py"},
                        "result": {
                            "dry_run": False,
                            "verification_exit_code": 1,
                            "rolled_back": True,
                            "verification": {
                                "command": "uv run pytest -q tests/test_brief.py",
                                "stdout": "FAILED tests/test_brief.py::BriefTests::old",
                            },
                        },
                    },
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["reliability"]["rates"]["approval_rejection"], 1.0)
        self.assertEqual(metrics["reliability"]["rates"]["verification_failure"], 1.0)
        self.assertEqual(metrics["diagnostics"]["approval_friction"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["verification_failures"][0]["tool_call_id"], 2)

    def test_observation_metrics_split_approval_bound_waits_from_model_resume(self):
        state = default_state()
        state["tasks"].append({"id": 1, "title": "Observe approval waits", "kind": "coding", "status": "ready"})
        state["work_sessions"].append(
            {
                "id": 11,
                "task_id": 1,
                "status": "closed",
                "created_at": "2026-04-19T00:00:00Z",
                "updated_at": "2026-04-19T00:01:00Z",
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:02Z",
                    },
                    {
                        "id": 2,
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:45Z",
                        "finished_at": "2026-04-19T00:00:46Z",
                    },
                ],
                "tool_calls": [
                    {
                        "id": 1,
                        "tool": "edit_file",
                        "status": "completed",
                        "approval_status": "applied",
                        "approved_at": "2026-04-19T00:00:50Z",
                        "started_at": "2026-04-19T00:00:03Z",
                        "finished_at": "2026-04-19T00:00:04Z",
                        "parameters": {"path": "src/mew/metrics.py"},
                        "result": {"dry_run": True, "changed": True},
                    }
                ],
            }
        )

        metrics = build_observation_metrics(state, kind="coding")

        self.assertEqual(metrics["latency"]["tool_to_next_model_wait_seconds"]["avg"], 41.0)
        self.assertEqual(metrics["latency"]["model_resume_wait_seconds"]["count"], 0)
        self.assertEqual(metrics["latency"]["approval_bound_wait_seconds"]["avg"], 41.0)
        self.assertEqual(metrics["diagnostics"]["slow_model_resumes"], [])
        self.assertEqual(metrics["diagnostics"]["approval_bound_waits"][0]["tool_call_id"], 1)
        self.assertEqual(metrics["diagnostics"]["approval_bound_waits"][0]["approval_bound_wait_seconds"], 41.0)
        signal_ids = {signal["id"] for signal in metrics["signals"]}
        self.assertNotIn("slow_model_resume", signal_ids)

        text = format_observation_metrics(metrics)
        self.assertIn("approval_bound_wait_seconds: count=1 avg=41.0", text)
        self.assertIn("approval_bound_waits:", text)
        self.assertIn("approval_wait=41.0s raw_wait=41.0s", text)


if __name__ == "__main__":
    unittest.main()
