import unittest
from unittest.mock import patch

from mew.agent_runs import sync_task_with_agent_run
from mew.programmer import (
    create_implementation_run_from_plan,
    create_review_run_for_implementation,
    create_task_plan,
)
from mew.state import default_state
from mew.sweep import format_sweep_report, sweep_agent_runs
from mew.timeutil import now_iso


def add_task(state):
    task = {
        "id": 1,
        "title": "Sweep agent lifecycle",
        "description": "Exercise sweep.",
        "status": "todo",
        "priority": "normal",
        "notes": "",
        "command": "",
        "cwd": ".",
        "auto_execute": False,
        "agent_backend": "",
        "agent_model": "",
        "agent_prompt": "",
        "agent_run_id": None,
        "plans": [],
        "latest_plan_id": None,
        "runs": [],
        "created_at": "t",
        "updated_at": "t",
    }
    state["tasks"].append(task)
    return task


class SweepTests(unittest.TestCase):
    def test_sweep_reports_review_needed(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"

        report = sweep_agent_runs(state, collect=False, followup=False)

        self.assertEqual(report["review_needed"], ["run #1 task=1"])
        self.assertIn("Review needed", format_sweep_report(report))

    def test_sweep_can_start_review(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"
        task["status"] = "done"

        def fake_start_agent_run(state_arg, review_run, timeout=None):
            review_run["status"] = "running"
            review_run["external_pid"] = 99
            sync_task_with_agent_run(state_arg, review_run, now_iso())
            return review_run

        with patch("mew.sweep.start_agent_run", side_effect=fake_start_agent_run):
            report = sweep_agent_runs(state, collect=False, start_reviews=True)

        self.assertEqual(len(state["agent_runs"]), 2)
        self.assertEqual(state["agent_runs"][1]["purpose"], "review")
        self.assertEqual(task["status"], "done")
        self.assertIn("review run #2", report["review_started"][0])

    def test_sweep_processes_review_followup_once(self):
        state = default_state()
        task = add_task(state)
        review = create_review_run_for_implementation(
            state,
            task,
            {"id": 1, "status": "completed", "result": "done"},
        )
        review["status"] = "completed"
        review["result"] = "STATUS: needs_fix\nFOLLOW_UP:\n- Add sweep regression test"

        report = sweep_agent_runs(state, collect=False)
        second = sweep_agent_runs(state, collect=False)

        self.assertEqual(len(state["tasks"]), 2)
        self.assertIn("task #2", report["followup_created"][0])
        self.assertEqual(second["followup_created"], [])

    def test_sweep_marks_stale_running_run(self):
        state = default_state()
        task = add_task(state)
        run = create_implementation_run_from_plan(state, task, create_task_plan(state, task), dry_run=True)
        run["status"] = "running"
        run["started_at"] = "2020-01-01T00:00:00Z"

        report = sweep_agent_runs(state, collect=False, stale_minutes=1)

        self.assertIn("run #1", report["stale"][0])
        self.assertEqual(state["attention"]["items"][0]["kind"], "agent_run_stale")


if __name__ == "__main__":
    unittest.main()
