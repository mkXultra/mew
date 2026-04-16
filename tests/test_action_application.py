import unittest

from mew.action_application import (
    public_action_plan,
    should_skip_outbox_send,
    suppress_done_task_wait_actions,
)
from mew.state import default_state


class ActionApplicationTests(unittest.TestCase):
    def test_public_action_plan_strips_private_action_fields(self):
        plan = {
            "summary": "Run checks",
            "actions": [
                {
                    "type": "run_verification",
                    "command": "uv run pytest -q",
                    "_precomputed_verification": {"exit_code": 0},
                }
            ],
        }

        public = public_action_plan(plan)

        self.assertEqual(public["actions"][0]["type"], "run_verification")
        self.assertNotIn("_precomputed_verification", public["actions"][0])

    def test_should_skip_outbox_send_deduplicates_same_event_and_unread_warnings(self):
        state = default_state()
        state["outbox"].append({"id": 1, "type": "info", "text": "same", "event_id": 7})
        state["outbox"].append({"id": 2, "type": "warning", "text": "warn", "event_id": 8})

        self.assertTrue(should_skip_outbox_send(state, "info", "same", 7))
        self.assertTrue(should_skip_outbox_send(state, "warning", "warn", 9))
        self.assertFalse(should_skip_outbox_send(state, "info", "same", 9))

    def test_suppress_done_task_wait_actions_removes_only_done_task_waits(self):
        state = default_state()
        state["tasks"].extend(
            [
                {"id": 1, "status": "done"},
                {"id": 2, "status": "todo"},
            ]
        )
        plan = {
            "actions": [
                {"type": "wait_for_user", "task_id": 1},
                {"type": "ask_user", "task_id": 2},
                {"type": "send_message", "text": "keep"},
            ]
        }

        filtered = suppress_done_task_wait_actions(state, plan)

        self.assertEqual(
            filtered["actions"],
            [
                {"type": "ask_user", "task_id": 2},
                {"type": "send_message", "text": "keep"},
            ],
        )
