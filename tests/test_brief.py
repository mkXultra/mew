import unittest

from mew.brief import build_brief, build_brief_data, next_move, review_runs_needing_followup
from mew.programmer import (
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_review_run_for_implementation,
    create_task_plan,
)
from mew.state import add_outbox_message, add_question, default_state, mark_question_deferred


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

    def test_next_move_ignores_deferred_question(self):
        state = default_state()
        add_task(state)
        question, _ = add_question(state, "What should I do?", related_task_id=1)
        mark_question_deferred(state, question, reason="later")

        self.assertEqual(next_move(state), "plan task #1 with `mew task plan 1`")

    def test_next_move_recommends_review_for_completed_implementation(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"

        self.assertEqual(next_move(state), "review implementation run #1 with `mew agent review 1`")
        self.assertIn("review needed: run #1", build_brief(state))

    def test_dry_run_review_does_not_hide_needed_real_review(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        implementation = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        implementation["status"] = "completed"
        review = create_review_run_for_implementation(state, task, implementation, plan=plan)
        review["status"] = "dry_run"

        self.assertEqual(next_move(state), "review implementation run #1 with `mew agent review 1`")
        self.assertIn("review needed: run #1", build_brief(state))

    def test_next_move_recommends_dispatch_for_ready_planned_task(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=True)
        create_task_plan(state, task)

        self.assertIn("mew task dispatch 1", next_move(state))
        self.assertIn("dispatchable: task #1", build_brief(state))

    def test_next_move_recommends_starting_buddy_dry_run(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=False)
        plan = create_task_plan(state, task)
        create_implementation_run_from_plan(state, task, plan, dry_run=True)

        self.assertEqual(next_move(state), "start dry-run task #1 with `mew buddy --task 1 --dispatch`")
        self.assertIn("dry-run ready: run #1 task=#1", build_brief(state))
        data = build_brief_data(state)
        self.assertEqual(data["programmer_queue"]["dry_run_ready"][0]["id"], 1)

    def test_next_move_recommends_plan_for_unplanned_task(self):
        state = default_state()
        add_task(state)

        self.assertEqual(next_move(state), "plan task #1 with `mew task plan 1`")

    def test_next_move_does_not_programmer_plan_admin_task(self):
        state = default_state()
        task = add_task(state)
        task["title"] = "Pay the electric bill"
        task["kind"] = "admin"

        self.assertEqual(
            next_move(state),
            "take one concrete admin step on task #1: Pay the electric bill",
        )

    def test_next_move_does_not_dispatch_admin_task_with_existing_plan(self):
        state = default_state()
        task = add_task(state, status="ready", auto_execute=True)
        task["title"] = "Pay the electric bill"
        task["kind"] = "admin"
        task["plans"] = [{"id": 1, "status": "planned"}]
        task["latest_plan_id"] = 1

        self.assertEqual(
            next_move(state),
            "take one concrete admin step on task #1: Pay the electric bill",
        )

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

    def test_brief_surfaces_recent_thought_journal(self):
        state = default_state()
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "at": "now",
                "summary": "Continue the self-improvement thread.",
                "open_threads": ["Check the verification result next."],
                "resolved_threads": [],
                "counts": {"actions": 1},
            }
        )

        brief = build_brief(state)

        self.assertIn("Thought journal", brief)
        self.assertIn("#1 passive_tick#2", brief)
        self.assertIn("open_threads=1", brief)

    def test_brief_surfaces_recent_activity(self):
        state = default_state()
        state["thought_journal"].append(
            {
                "id": 1,
                "event_id": 2,
                "event_type": "passive_tick",
                "at": "now",
                "summary": "Inspected the workspace.",
                "open_threads": [],
                "resolved_threads": [],
                "actions": [
                    {"type": "inspect_dir", "path": "/tmp/project"},
                    {"type": "read_file", "path": "/tmp/project/README.md"},
                ],
                "counts": {"actions": 2, "messages": 2},
            }
        )

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("Recent activity", brief)
        self.assertIn("inspect_dir /tmp/project", brief)
        self.assertEqual(data["recent_activity"][0]["summary"], "Inspected the workspace.")

    def test_brief_surfaces_project_snapshot(self):
        state = default_state()
        state["memory"]["deep"]["project_snapshot"] = {
            "updated_at": "now",
            "project_types": ["python"],
            "package": {"name": "mew"},
            "roots": [{"path": "/repo"}],
            "files": [{"path": "/repo/README.md"}],
        }

        brief = build_brief(state)
        data = build_brief_data(state)

        self.assertIn("project_snapshot: types=python package=mew roots=1 files=1", brief)
        self.assertEqual(data["memory"]["project_snapshot"]["package_name"], "mew")

    def test_brief_shows_latest_unread_messages_first(self):
        state = default_state()
        for index in range(7):
            add_outbox_message(state, "info", f"message {index + 1}")

        brief = build_brief(state, limit=3)
        data = build_brief_data(state, limit=3)

        self.assertIn("showing latest 3; 4 older unread omitted", brief)
        self.assertIn("#7 [info] message 7", brief)
        self.assertNotIn("#1 [info] message 1", brief)
        self.assertEqual([message["id"] for message in data["unread_outbox"]], [7, 6, 5])
        self.assertEqual(data["unread_outbox_count"], 7)

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
