import unittest

from mew.action_application import (
    public_action_plan,
    should_skip_outbox_send,
    suppress_done_task_wait_actions,
    suppress_low_intent_task_wait_actions,
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

    def test_suppress_low_intent_research_routing_question(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 20,
                "title": "補助金について調べる",
                "kind": "research",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )
        event = {"type": "user_message", "payload": {"text": "dogfood no-op check"}}
        plan = {
            "actions": [
                {
                    "type": "ask_user",
                    "task_id": 20,
                    "question": "Task #20 is ready but has no command. What should I execute for it?",
                }
            ]
        }

        filtered = suppress_low_intent_task_wait_actions(state, event, plan)

        self.assertEqual(filtered["actions"][0]["type"], "record_memory")
        self.assertEqual(
            filtered["skipped_actions"][0]["skip_reason"],
            "low_intent_research_task_routing",
        )

    def test_suppress_low_intent_research_routing_keeps_real_user_question(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 20,
                "title": "補助金について調べる",
                "kind": "research",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )
        event = {"type": "user_message", "payload": {"text": "What should task 20 do next?"}}
        plan = {
            "actions": [
                {
                    "type": "ask_user",
                    "task_id": 20,
                    "question": "Task #20 is ready research work. Should I assign it to an agent, add research criteria, or block it?",
                }
            ]
        }

        filtered = suppress_low_intent_task_wait_actions(state, event, plan)

        self.assertEqual(filtered["actions"], plan["actions"])

    def test_suppress_low_intent_research_routing_checks_fallback_before_reason(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 20,
                "title": "補助金について調べる",
                "kind": "research",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )
        event = {"type": "passive_tick", "source": "manual_step_planning", "payload": {}}
        plan = {
            "actions": [
                {
                    "type": "wait_for_user",
                    "task_id": 20,
                    "reason": "Need user input.",
                }
            ]
        }

        filtered = suppress_low_intent_task_wait_actions(
            state,
            event,
            plan,
            fallback_question="Task #20 is ready but has no command. What should I execute for it?",
        )

        self.assertEqual(filtered["actions"][0]["type"], "record_memory")
        self.assertEqual(
            filtered["skipped_actions"][0]["skip_reason"],
            "low_intent_research_task_routing",
        )
