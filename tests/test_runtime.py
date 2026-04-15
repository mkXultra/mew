import os
from io import StringIO
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from mew.cli import main
from mew.runtime import run_runtime_post_run_pipeline
from mew.state import add_outbox_message, default_state


class RuntimeTests(unittest.TestCase):
    def test_post_run_pipeline_uses_autonomy_gates(self):
        state = default_state()
        args = SimpleNamespace(
            agent_stale_minutes=7.0,
            agent_result_timeout=3.0,
            agent_start_timeout=5.0,
            review_model="reviewer",
        )
        autonomy = {
            "autonomous": True,
            "autonomy_level": "act",
            "allow_agent_run": True,
        }

        with patch("mew.runtime.sweep_agent_runs", return_value={"review_started": ["ok"]}) as sweep:
            report = run_runtime_post_run_pipeline(state, args, autonomy)

        self.assertEqual(report, {"review_started": ["ok"]})
        sweep.assert_called_once()
        _, kwargs = sweep.call_args
        self.assertTrue(kwargs["collect"])
        self.assertTrue(kwargs["start_reviews"])
        self.assertTrue(kwargs["followup"])
        self.assertEqual(kwargs["stale_minutes"], 7.0)
        self.assertEqual(kwargs["review_model"], "reviewer")
        self.assertEqual(kwargs["result_timeout"], 3.0)
        self.assertEqual(kwargs["start_timeout"], 5.0)

    def test_post_run_pipeline_does_not_start_reviews_below_act_level(self):
        state = default_state()
        args = SimpleNamespace(agent_stale_minutes=7.0, review_model="")
        autonomy = {
            "autonomous": True,
            "autonomy_level": "propose",
            "allow_agent_run": True,
        }

        with patch("mew.runtime.sweep_agent_runs", return_value={}) as sweep:
            run_runtime_post_run_pipeline(state, args, autonomy)

        _, kwargs = sweep.call_args
        self.assertTrue(kwargs["collect"])
        self.assertFalse(kwargs["start_reviews"])
        self.assertTrue(kwargs["followup"])

    def test_runtime_reflex_runs_before_model_snapshot_and_echoes_outbox(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_sweep(state, *args, **kwargs):
                    state["memory"]["shallow"]["latest_task_summary"] = "reflex ran"
                    add_outbox_message(state, "info", "reflex message")
                    return {"collected": ["run #1 running -> completed"]}

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    self.assertEqual(
                        state_snapshot["memory"]["shallow"]["latest_task_summary"],
                        "reflex ran",
                    )
                    return (
                        {"summary": "after reflex", "decisions": []},
                        {"summary": "after reflex", "actions": []},
                    )

                with (
                    patch("mew.runtime.sweep_agent_runs", side_effect=fake_sweep),
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-agent-run",
                                "--echo-outbox",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertIn("reflex message", stdout.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
