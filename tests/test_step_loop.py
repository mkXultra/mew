import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.state import add_event, add_outbox_message, add_question, default_state, load_state, next_id
from mew.step_loop import (
    MAX_STEP_EFFECTS,
    collect_step_effects,
    filter_step_action_plan,
    load_state_readonly,
    run_step_loop,
)


class StepLoopTests(unittest.TestCase):
    def test_filter_step_action_plan_skips_writes_and_agent_runs(self):
        action_plan = {
            "summary": "Try unsafe work.",
            "actions": [
                {"type": "read_file", "path": "README.md"},
                {"type": "write_file", "path": "README.md", "content": "bad"},
                {"type": "execute_task", "task_id": 1},
                {"type": "complete_task", "task_id": 1},
                {"type": "dispatch_task", "task_id": 1},
                {"type": "run_verification", "reason": "check"},
            ],
        }

        filtered = filter_step_action_plan(action_plan)

        self.assertEqual([action["type"] for action in filtered["actions"]], ["read_file"])
        self.assertEqual(
            [action["type"] for action in filtered["skipped_actions"]],
            ["write_file", "execute_task", "complete_task", "dispatch_task", "run_verification"],
        )

    def test_filter_step_action_plan_can_allow_verification(self):
        action_plan = {
            "summary": "Verify.",
            "actions": [{"type": "run_verification", "reason": "check"}],
        }

        filtered = filter_step_action_plan(action_plan, allow_verify=True)

        self.assertEqual(filtered["actions"][0]["type"], "run_verification")

    def test_dry_run_step_does_not_write_state(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                before = load_state()
                report = run_step_loop(max_steps=1, dry_run=True)
                after = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertTrue(report["dry_run"])
        self.assertEqual(before, after)

    def test_dry_run_step_does_not_create_state_directory(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                report = run_step_loop(max_steps=1, dry_run=True)
                state_dir_exists = Path(".mew").exists()
            finally:
                os.chdir(old_cwd)

        self.assertTrue(report["dry_run"])
        self.assertFalse(state_dir_exists)

    def test_ai_dry_run_step_does_not_create_state_directory(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch(
                    "mew.agent.call_model_json",
                    side_effect=[
                        {
                            "summary": "Think safely.",
                            "decisions": [{"type": "remember", "summary": "Think safely."}],
                        },
                        {
                            "summary": "Act safely.",
                            "actions": [{"type": "record_memory", "summary": "Act safely."}],
                        },
                    ],
                ):
                    report = run_step_loop(max_steps=1, dry_run=True, model_auth={"ok": True})
                state_dir_exists = Path(".mew").exists()
            finally:
                os.chdir(old_cwd)

        self.assertTrue(report["dry_run"])
        self.assertFalse(state_dir_exists)

    def test_readonly_state_loader_does_not_create_state_directory(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = load_state_readonly()
                state_dir_exists = Path(".mew").exists()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(state["inbox"], [])
        self.assertFalse(state_dir_exists)

    def test_step_applies_filtered_action_and_records_thought(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                fake_decision = {
                    "summary": "Remember one thing.",
                    "open_threads": [],
                    "resolved_threads": [],
                    "agent_status": {},
                    "decisions": [{"type": "remember", "summary": "Remember one thing."}],
                }
                fake_actions = {
                    "summary": "Remember one thing.",
                    "actions": [
                        {"type": "record_memory", "summary": "Remember one thing."},
                        {"type": "write_file", "path": "README.md", "content": "bad"},
                    ],
                }
                with patch("mew.step_loop.plan_event", return_value=(fake_decision, fake_actions)):
                    report = run_step_loop(max_steps=1)
                state = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(report["steps"][0]["counts"]["actions"], 1)
        self.assertEqual(report["steps"][0]["skipped_actions"][0]["type"], "write_file")
        self.assertEqual(len(state["inbox"]), 1)
        self.assertEqual(state["inbox"][0]["processed_at"], state["thought_journal"][0]["at"])
        self.assertEqual(state["thought_journal"][0]["actions"][0]["type"], "record_memory")
        self.assertEqual(state["step_runs"][0]["event_id"], state["inbox"][0]["id"])
        self.assertEqual(state["step_runs"][0]["skipped_actions"][0]["type"], "write_file")

    def test_step_run_records_visible_effects(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                fake_decision = {
                    "summary": "Ask one thing.",
                    "open_threads": ["Need user input."],
                    "resolved_threads": [],
                    "agent_status": {},
                    "decisions": [{"type": "ask_user", "question": "Which task should I handle?"}],
                }
                fake_actions = {
                    "summary": "Ask one thing.",
                    "actions": [{"type": "ask_user", "question": "Which task should I handle?"}],
                }
                with patch("mew.step_loop.plan_event", return_value=(fake_decision, fake_actions)):
                    report = run_step_loop(max_steps=1)
                state = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(report["stop_reason"], "waiting_for_user")
        effects = state["step_runs"][0]["effects"]
        self.assertEqual([effect["type"] for effect in effects], ["message", "question"])
        self.assertEqual(effects[0]["message_type"], "question")
        self.assertEqual(effects[0]["question_id"], state["questions"][0]["id"])
        self.assertEqual(effects[1]["text"], "Which task should I handle?")

    def test_collect_step_effects_keeps_linked_question_with_message(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        add_outbox_message(state, "info", "first", event_id=event["id"])
        question, _created = add_question(state, "Need input?", event_id=event["id"])
        add_outbox_message(state, "info", "third", event_id=event["id"])

        effects = collect_step_effects(state, event["id"])

        self.assertEqual([effect["type"] for effect in effects], ["message", "message", "question", "message"])
        self.assertEqual(effects[2]["id"], question["id"])
        self.assertEqual(effects[2]["text"], "Need input?")

    def test_collect_step_effects_preserves_important_effects_when_capped(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        for index in range(MAX_STEP_EFFECTS + 5):
            add_outbox_message(state, "info", f"message {index}", event_id=event["id"])
        question, _created = add_question(state, "Need input?", event_id=event["id"])
        state["verification_runs"].append(
            {
                "id": next_id(state, "verification_run"),
                "event_id": event["id"],
                "exit_code": 1,
                "reason": "important",
                "created_at": "verify-time",
            }
        )
        state["write_runs"].append(
            {
                "id": next_id(state, "write_run"),
                "event_id": event["id"],
                "action_type": "edit_file",
                "path": "README.md",
                "created_at": "write-time",
            }
        )

        effects = collect_step_effects(state, event["id"])

        self.assertEqual(len(effects), MAX_STEP_EFFECTS)
        effect_pairs = [(effect["type"], effect["id"]) for effect in effects]
        self.assertIn(("message", question["outbox_message_id"]), effect_pairs)
        self.assertIn(("question", question["id"]), effect_pairs)
        self.assertIn("verification_run", [effect["type"] for effect in effects])
        self.assertIn("write_run", [effect["type"] for effect in effects])

    def test_step_does_not_expose_unprocessed_manual_event_while_planning(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_plan(_state, _event, *_args, **_kwargs):
                    self.assertEqual(load_state()["inbox"], [])
                    return (
                        {
                            "summary": "Remember one thing.",
                            "open_threads": [],
                            "resolved_threads": [],
                            "agent_status": {},
                            "decisions": [{"type": "remember", "summary": "Remember one thing."}],
                        },
                        {
                            "summary": "Remember one thing.",
                            "actions": [{"type": "record_memory", "summary": "Remember one thing."}],
                        },
                    )

                with patch("mew.step_loop.plan_event", side_effect=fake_plan):
                    run_step_loop(max_steps=1)
                state = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(len(state["inbox"]), 1)
        self.assertIsNotNone(state["inbox"][0]["processed_at"])

    def test_step_processed_at_is_not_before_created_at_after_slow_planning(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def slow_plan(_state, _event, *_args, **_kwargs):
                    time.sleep(1.2)
                    return (
                        {
                            "summary": "Remember one thing.",
                            "open_threads": [],
                            "resolved_threads": [],
                            "agent_status": {},
                            "decisions": [{"type": "remember", "summary": "Remember one thing."}],
                        },
                        {
                            "summary": "Remember one thing.",
                            "actions": [{"type": "record_memory", "summary": "Remember one thing."}],
                        },
                    )

                with patch("mew.step_loop.plan_event", side_effect=slow_plan):
                    run_step_loop(max_steps=1)
                state = load_state()
            finally:
                os.chdir(old_cwd)

        event = state["inbox"][0]
        self.assertGreaterEqual(event["processed_at"], event["created_at"])


if __name__ == "__main__":
    unittest.main()
