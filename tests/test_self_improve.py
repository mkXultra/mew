import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from mew.cli import main
from mew.self_improve import create_self_improve_task, ensure_self_improve_plan
from mew.state import default_state, load_state


class SelfImproveTests(unittest.TestCase):
    def test_create_self_improve_task_and_plan(self):
        state = default_state()

        task, created = create_self_improve_task(state, focus="Improve next command", ready=True)
        plan, plan_created = ensure_self_improve_plan(state, task)

        self.assertTrue(created)
        self.assertTrue(plan_created)
        self.assertEqual(task["status"], "ready")
        self.assertEqual(task["latest_plan_id"], plan["id"])
        self.assertIn("Improve next command", task["description"])

    def test_self_improve_reuses_open_task(self):
        state = default_state()

        first, created = create_self_improve_task(state)
        second, reused_created = create_self_improve_task(state)

        self.assertTrue(created)
        self.assertFalse(reused_created)
        self.assertEqual(first["id"], second["id"])

    def test_cli_self_improve_dry_run_dispatch(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "self-improve",
                            "--focus",
                            "Add a tiny improvement",
                            "--ready",
                            "--auto-execute",
                            "--dispatch",
                            "--dry-run",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("created dry-run self-improve run", stdout.getvalue())
                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertEqual(len(state["agent_runs"]), 1)
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
