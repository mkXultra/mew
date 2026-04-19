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
                "model_turns": [
                    {
                        "id": 1,
                        "status": "completed",
                        "tool_call_id": 1,
                        "started_at": "2026-04-19T00:00:01Z",
                        "finished_at": "2026-04-19T00:00:03Z",
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
                        "result": {"dry_run": True, "changed": True},
                    },
                    {
                        "id": 3,
                        "tool": "edit_file",
                        "status": "completed",
                        "started_at": "2026-04-19T00:00:15Z",
                        "finished_at": "2026-04-19T00:00:16Z",
                        "result": {
                            "dry_run": False,
                            "written": True,
                            "verification_exit_code": 1,
                            "rolled_back": True,
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
        self.assertEqual(metrics["reliability"]["approvals"]["rejected"], 1)
        self.assertEqual(metrics["reliability"]["verification"]["failed"], 1)
        self.assertEqual(metrics["reliability"]["verification"]["rolled_back"], 1)
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["avg"], 4.0)
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["median"], 4.0)
        self.assertEqual(metrics["latency"]["first_tool_start_seconds"]["p95"], 4.0)
        self.assertEqual(metrics["latency"]["model_to_tool_wait_seconds"]["avg"], 1.0)
        self.assertEqual(metrics["latency"]["tool_to_next_model_wait_seconds"]["avg"], 3.0)
        self.assertEqual(metrics["latency"]["perceived_idle_ratio"]["avg"], 0.65)
        signal_ids = {signal["id"] for signal in metrics["signals"]}
        self.assertIn("approval_friction", signal_ids)
        self.assertIn("verification_friction", signal_ids)

        text = format_observation_metrics(metrics)
        self.assertIn("Mew observation metrics", text)
        self.assertIn("interventions=3", text)
        self.assertIn("perceived_idle_ratio: count=1 avg=0.65 median=0.65 p95=0.65 max=0.65", text)
        self.assertIn("signals:", text)
        self.assertIn("verification failures are frequent", text)


if __name__ == "__main__":
    unittest.main()
