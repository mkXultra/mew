import tempfile
import unittest
from pathlib import Path

from mew.agent import apply_action_plan, deterministic_decision_plan
from mew.read_tools import read_file
from mew.state import add_event, default_state, migrate_state
from mew.timeutil import now_iso


class AutonomyTests(unittest.TestCase):
    def test_migration_adds_autonomy_defaults(self):
        state = default_state()
        state.pop("autonomy")

        migrated = migrate_state(state)

        self.assertIn("autonomy", migrated)
        self.assertFalse(migrated["autonomy"]["enabled"])
        self.assertEqual(migrated["autonomy"]["level"], "off")
        self.assertEqual(migrated["autonomy"]["cycles"], 0)

    def test_self_review_can_propose_task_at_propose_level(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")

        counts = apply_action_plan(
            state,
            event,
            {"summary": "review"},
            {
                "summary": "review",
                "actions": [
                    {
                        "type": "self_review",
                        "summary": "No tasks; choose one useful next move.",
                        "proposed_task_title": "Define next useful task",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertEqual(len(state["tasks"]), 1)
        self.assertEqual(state["tasks"][0]["title"], "Define next useful task")
        self.assertEqual(state["tasks"][0]["status"], "todo")
        self.assertGreaterEqual(counts["messages"], 1)
        self.assertIn("Self review:", state["memory"]["deep"]["decisions"][0])

    def test_observe_level_refuses_task_proposal(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")

        apply_action_plan(
            state,
            event,
            {"summary": "review"},
            {
                "summary": "review",
                "actions": [
                    {
                        "type": "propose_task",
                        "title": "Should not be created",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="observe",
        )

        self.assertEqual(state["tasks"], [])
        self.assertIn("Refused propose_task", state["outbox"][0]["text"])

    def test_read_actions_require_act_level_unless_user_requested(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        with tempfile.TemporaryDirectory() as tmp:
            apply_action_plan(
                state,
                event,
                {"summary": "inspect"},
                {
                    "summary": "inspect",
                    "actions": [
                        {
                            "type": "inspect_dir",
                            "path": tmp,
                        }
                    ],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                allowed_read_roots=[tmp],
                autonomous=True,
                autonomy_level="propose",
            )

        self.assertIn("Refused inspect_dir", state["outbox"][0]["text"])
        self.assertEqual(state["memory"]["deep"]["project"], [])

    def test_sensitive_file_read_is_refused_inside_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            auth_file = Path(tmp) / "auth.json"
            auth_file.write_text('{"access": "secret"}', encoding="utf-8")

            with self.assertRaises(ValueError):
                read_file(str(auth_file), [tmp])

    def test_autonomous_self_review_has_cooldown(self):
        state = default_state()
        current_time = now_iso()
        state["autonomy"]["last_self_review_at"] = current_time
        state["tasks"].append(
            {
                "id": 1,
                "title": "Existing task",
                "description": "",
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
                "created_at": current_time,
                "updated_at": current_time,
            }
        )

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            current_time,
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertNotIn("self_review", [decision["type"] for decision in plan["decisions"]])


if __name__ == "__main__":
    unittest.main()
