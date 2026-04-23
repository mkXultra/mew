import unittest

from mew.tasks import (
    infer_task_kind,
    normalize_task_id,
    normalize_task_scope,
    task_kind,
    task_kind_report,
    task_needs_programmer_plan,
    task_question,
    task_scope_target_paths,
    task_sort_key,
)


class TaskKindTests(unittest.TestCase):
    def test_normalize_task_id_accepts_display_ids(self):
        self.assertEqual(normalize_task_id("#12"), 12)
        self.assertEqual(normalize_task_id(" 12 "), 12)
        self.assertIsNone(normalize_task_id("#abc"))

    def test_infer_task_kind_handles_collision_words(self):
        self.assertEqual(infer_task_kind("Research API pricing"), "research")
        self.assertEqual(infer_task_kind("Pay API invoice"), "admin")
        self.assertEqual(infer_task_kind("Review tax documents"), "admin")
        self.assertEqual(infer_task_kind("補助金について調べる"), "research")
        self.assertEqual(infer_task_kind("Fix the broken kitchen faucet"), "unknown")
        self.assertEqual(infer_task_kind("Implement API client"), "coding")
        self.assertEqual(infer_task_kind("Implement tax calculator"), "coding")
        self.assertEqual(infer_task_kind("Implement email parser"), "coding")
        self.assertEqual(infer_task_kind("Investigate a mew CLI test failure in wait_outbox"), "coding")
        self.assertEqual(infer_task_kind("Fix unit test failure"), "coding")
        self.assertEqual(infer_task_kind("Return JSON from API"), "coding")

    def test_infer_task_kind_does_not_let_housekeeping_notes_dominate(self):
        self.assertEqual(
            infer_task_kind(
                "補助金について調べる",
                description="利用可能な補助金を調査する。",
                notes="Proposed by mew from event #1.",
            ),
            "research",
        )

    def test_task_kind_prefers_explicit_override(self):
        task = {
            "title": "Research API pricing",
            "kind": "coding",
        }

        self.assertEqual(task_kind(task), "coding")

    def test_task_kind_report_detects_explicit_mismatch(self):
        report = task_kind_report({"id": 1, "title": "補助金について調べる", "kind": "coding", "status": "todo"})

        self.assertEqual(report["stored_kind"], "coding")
        self.assertEqual(report["inferred_kind"], "research")
        self.assertEqual(report["effective_kind"], "coding")
        self.assertTrue(report["mismatch"])

    def test_task_kind_report_does_not_treat_unknown_inference_as_mismatch(self):
        report = task_kind_report({"id": 1, "title": "Ambiguous thing", "kind": "coding", "status": "todo"})

        self.assertEqual(report["inferred_kind"], "unknown")
        self.assertFalse(report["mismatch"])

    def test_normalize_task_scope_requires_matching_source_test_pair(self):
        self.assertEqual(
            normalize_task_scope({"target_paths": ["tests/test_commands.py", "./src/mew/commands.py"]}),
            {"target_paths": ["src/mew/commands.py", "tests/test_commands.py"]},
        )
        self.assertEqual(
            normalize_task_scope({"target_paths": ["src/mew/commands.py", "tests/test_work_session.py"]}),
            {},
        )

    def test_task_scope_target_paths_returns_normalized_pair(self):
        self.assertEqual(
            task_scope_target_paths({"scope": {"target_paths": ["./tests/test_tasks.py", "src/mew/tasks.py"]}}),
            ["src/mew/tasks.py", "tests/test_tasks.py"],
        )

    def test_running_tasks_sort_before_ready_tasks(self):
        tasks = [
            {"id": 1, "status": "ready", "priority": "high", "created_at": "1"},
            {"id": 2, "status": "running", "priority": "normal", "created_at": "2"},
        ]

        self.assertEqual([task["id"] for task in sorted(tasks, key=task_sort_key)], [2, 1])

    def test_task_needs_programmer_plan_uses_resolvable_latest_plan(self):
        task = {
            "title": "Implement API client",
            "kind": "coding",
            "status": "todo",
            "plans": [],
            "latest_plan_id": 99,
        }
        self.assertTrue(task_needs_programmer_plan(task))

        task["plans"] = [{"id": 1, "status": "planned"}]
        self.assertFalse(task_needs_programmer_plan(task))

    def test_ready_research_task_question_does_not_ask_for_command_execution(self):
        question = task_question(
            {
                "id": 20,
                "title": "補助金について調べる",
                "kind": "research",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )

        self.assertIn("ready research work", question)
        self.assertIn("research criteria", question)
        self.assertNotIn("What should I execute", question)

    def test_ready_coding_task_question_points_to_coding_cockpit(self):
        question = task_question(
            {
                "id": 21,
                "title": "Implement runtime cleanup",
                "kind": "coding",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )

        self.assertIn("ready coding work", question)
        self.assertIn("./mew code 21", question)
        self.assertIn("add constraints", question)
        self.assertNotIn("dispatch it to an agent", question)


if __name__ == "__main__":
    unittest.main()
