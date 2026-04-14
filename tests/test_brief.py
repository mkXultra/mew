import unittest

from mew.brief import build_brief, next_move, review_runs_needing_followup
from mew.programmer import create_follow_up_task_from_review, create_implementation_run_from_plan, create_task_plan
from mew.state import add_question, default_state


def add_task(state, status="todo", auto_execute=False):
    task = {
        "id": 1,
        "title": "Implement next move",
        "description": "Make brief actionable.",
        "status": status,
        "priority": "normal",
        "notes": "",
        "command": "",
        "cwd": ".",
        "auto_execute": auto_execute,
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


class BriefTests(unittest.TestCase):
    def test_next_move_prefers_open_question(self):
        state = default_state()
        add_task(state)
        add_question(state, "What should I do?", related_task_id=1)

        self.assertIn("mew reply", next_move(state))

    def test_next_move_recommends_review_for_completed_implementation(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"

        self.assertEqual(next_move(state), "review implementation run #1 with `mew agent review 1`")
        self.assertIn("review needed: run #1", build_brief(state))

    def test_next_move_recommends_dispatch_for_ready_planned_task(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=True)
        create_task_plan(state, task)

        self.assertIn("mew task dispatch 1", next_move(state))
        self.assertIn("dispatchable: task #1", build_brief(state))

    def test_next_move_recommends_plan_for_unplanned_task(self):
        state = default_state()
        add_task(state)

        self.assertEqual(next_move(state), "plan task #1 with `mew task plan 1`")

    def test_processed_review_does_not_keep_needing_followup(self):
        state = default_state()
        task = add_task(state)
        review = {
            "id": 2,
            "task_id": task["id"],
            "purpose": "review",
            "status": "completed",
            "result": "STATUS: pass\nFOLLOW_UP:\n- none",
            "stdout": "",
            "followup_task_id": None,
        }

        create_follow_up_task_from_review(state, task, review)
        state["agent_runs"].append(review)

        self.assertEqual(review_runs_needing_followup(state), [])

    def test_brief_surfaces_recent_verification(self):
        state = default_state()
        state["verification_runs"].append(
            {
                "id": 1,
                "command": "python -m unittest",
                "exit_code": 0,
                "finished_at": "done",
            }
        )

        brief = build_brief(state)

        self.assertIn("Recent verification", brief)
        self.assertIn("#1 [passed]", brief)

    def test_next_move_surfaces_latest_failed_verification(self):
        state = default_state()
        state["verification_runs"].append(
            {
                "id": 2,
                "command": "python -m unittest",
                "exit_code": 1,
                "finished_at": "done",
            }
        )

        self.assertEqual(next_move(state), "inspect verification run #2 with `mew verification`")


if __name__ == "__main__":
    unittest.main()
