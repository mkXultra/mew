import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.agent import (
    act_phase,
    apply_action_plan,
    build_context,
    deterministic_decision_plan,
    think_phase,
)
from mew.read_tools import read_file
from mew.state import add_attention_item, add_event, default_state, migrate_state
from mew.thoughts import format_thought_entry
from mew.timeutil import now_iso


def add_planned_ready_task(state):
    current_time = now_iso()
    task = {
        "id": 1,
        "title": "Verify mew",
        "description": "",
        "status": "ready",
        "priority": "normal",
        "notes": "",
        "command": "python -m unittest",
        "cwd": ".",
        "auto_execute": False,
        "agent_backend": "",
        "agent_model": "",
        "agent_prompt": "",
        "agent_run_id": None,
        "plans": [{"id": 1, "status": "planned"}],
        "latest_plan_id": 1,
        "runs": [],
        "created_at": current_time,
        "updated_at": current_time,
    }
    state["tasks"].append(task)
    return task


class AutonomyTests(unittest.TestCase):
    def test_migration_adds_autonomy_defaults(self):
        state = default_state()
        state.pop("autonomy")
        state.pop("thought_journal")
        state["next_ids"].pop("thought")

        migrated = migrate_state(state)

        self.assertIn("autonomy", migrated)
        self.assertFalse(migrated["autonomy"]["enabled"])
        self.assertEqual(migrated["autonomy"]["level"], "off")
        self.assertEqual(migrated["autonomy"]["cycles"], 0)
        self.assertEqual(migrated["thought_journal"], [])
        self.assertEqual(migrated["next_ids"]["thought"], 1)

    def test_action_plan_records_thought_journal_threads(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "continue"})

        apply_action_plan(
            state,
            event,
            {
                "summary": "Need to keep working memory.",
                "open_threads": ["Investigate task #1 next."],
                "decisions": [{"type": "remember", "summary": "Need to keep working memory."}],
            },
            {
                "summary": "Recorded continuity.",
                "resolved_threads": ["Old question answered."],
                "actions": [{"type": "record_memory", "summary": "Recorded continuity."}],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )

        self.assertEqual(len(state["thought_journal"]), 1)
        thought = state["thought_journal"][0]
        self.assertEqual(thought["event_id"], event["id"])
        self.assertEqual(thought["cycle_reason"], "user_input")
        self.assertEqual(thought["summary"], "Recorded continuity.")
        self.assertEqual(thought["open_threads"], ["Investigate task #1 next."])
        self.assertEqual(thought["resolved_threads"], ["Old question answered."])
        self.assertEqual(thought["actions"][0]["type"], "record_memory")

        context = build_context(state, event, "later")
        self.assertEqual(context["thought_journal"][0]["summary"], "Recorded continuity.")
        self.assertEqual(context["perception"]["observations"][1]["status"], "disabled")

    def test_thought_journal_records_dropped_threads(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            first,
            {"summary": "start", "open_threads": ["Investigate task #1", "Check run #2"]},
            {"summary": "start", "actions": [{"type": "record_memory", "summary": "start"}]},
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        second = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            second,
            {"summary": "continue", "open_threads": ["Investigate task #1"]},
            {"summary": "continue", "actions": [{"type": "record_memory", "summary": "continue"}]},
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        thought = state["thought_journal"][-1]
        self.assertEqual(thought["dropped_threads"], ["Check run #2"])
        self.assertEqual(thought["dropped_thread_ratio"], 0.5)

        context = build_context(state, second, "later")
        self.assertEqual(context["thought_thread_warning"]["dropped_threads"], ["Check run #2"])
        self.assertIn("dropped_threads:", format_thought_entry(thought, details=True))

    def test_thought_journal_does_not_drop_resolved_threads(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            first,
            {"summary": "start", "open_threads": ["Check run #2"]},
            {"summary": "start", "actions": [{"type": "record_memory", "summary": "start"}]},
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        second = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            second,
            {"summary": "done", "resolved_threads": ["Check run #2"]},
            {"summary": "done", "actions": [{"type": "record_memory", "summary": "done"}]},
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(state["thought_journal"][-1]["dropped_threads"], [])
        context = build_context(state, second, "later")
        self.assertIsNone(context["thought_thread_warning"])

    def test_thought_journal_keeps_equivalent_waiting_question_thread(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            first,
            {"summary": "ask", "decisions": [{"type": "ask_user", "task_id": 1}]},
            {
                "summary": "ask",
                "actions": [
                    {
                        "type": "ask_user",
                        "task_id": 1,
                        "question": "Task #1 is todo. Should I make it ready?",
                    }
                ],
            },
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        second = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            second,
            {"summary": "wait", "decisions": [{"type": "wait_for_user", "task_id": 1}]},
            {
                "summary": "wait",
                "actions": [
                    {
                        "type": "wait_for_user",
                        "task_id": 1,
                        "reason": "Question #1 is still unanswered.",
                    }
                ],
            },
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(state["thought_journal"][-1]["dropped_threads"], [])
        self.assertIsNone(build_context(state, second, "later")["thought_thread_warning"])

    def test_think_phase_uses_model_backend_adapter(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                event = add_event(state, "user_message", "test", {"text": "hello"})
                auth = {"access_token": "token"}
                with patch(
                    "mew.agent.call_model_json",
                    return_value={
                        "summary": "adapter summary",
                        "decisions": [{"type": "remember", "summary": "adapter summary"}],
                    },
                ) as call:
                    plan = think_phase(
                        state,
                        event,
                        now_iso(),
                        auth,
                        "test-model",
                        "https://example.invalid",
                        5,
                        False,
                        False,
                        "",
                        "",
                        model_backend="codex",
                    )

                self.assertEqual(plan["summary"], "adapter summary")
                self.assertEqual(call.call_args.args[0], "codex")
                self.assertEqual(call.call_args.args[1], auth)
            finally:
                os.chdir(old_cwd)

    def test_act_phase_uses_model_backend_adapter(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                event = add_event(state, "user_message", "test", {"text": "hello"})
                auth = {"access_token": "token"}
                decision_plan = {
                    "summary": "decide",
                    "decisions": [{"type": "send_message", "message_type": "info", "text": "hello"}],
                }
                with patch(
                    "mew.agent.call_model_json",
                    return_value={
                        "summary": "adapter action",
                        "actions": [{"type": "send_message", "message_type": "info", "text": "hello"}],
                    },
                ) as call:
                    plan = act_phase(
                        state,
                        event,
                        decision_plan,
                        now_iso(),
                        auth,
                        "test-model",
                        "https://example.invalid",
                        5,
                        False,
                        False,
                        "",
                        model_backend="codex",
                    )

                self.assertEqual(plan["summary"], "adapter action")
                self.assertEqual(call.call_args.args[0], "codex")
                self.assertEqual(call.call_args.args[1], auth)
            finally:
                os.chdir(old_cwd)

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

    def test_observe_level_defers_self_review_task_proposal_quietly(self):
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
                        "type": "self_review",
                        "summary": "No user work yet.",
                        "proposed_task_title": "Monitor for first actionable input",
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
        self.assertEqual(state["outbox"], [])
        self.assertIn(
            "Deferred self-review task proposal",
            state["memory"]["deep"]["decisions"][-1],
        )

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

    def test_autonomous_act_schedules_configured_verification_when_due(self):
        state = default_state()
        add_planned_ready_task(state)

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_verify=True,
            verify_command="python -m unittest",
        )

        self.assertIn("run_verification", [decision["type"] for decision in plan["decisions"]])

    def test_autonomous_verification_is_not_blocked_by_unplanned_tasks(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Unplanned work",
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
            autonomy_level="act",
            allow_verify=True,
            verify_command="python -m unittest",
        )

        decision_types = [decision["type"] for decision in plan["decisions"]]
        self.assertIn("run_verification", decision_types)
        self.assertNotIn("plan_task", decision_types)

    def test_autonomous_verification_can_run_without_open_tasks(self):
        state = default_state()

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_verify=True,
            verify_command="python -m unittest",
        )

        self.assertIn("run_verification", [decision["type"] for decision in plan["decisions"]])

    def test_autonomous_verification_respects_interval(self):
        state = default_state()
        current_time = now_iso()
        add_planned_ready_task(state)
        state["verification_runs"].append(
            {
                "id": 1,
                "command": "python -m unittest",
                "exit_code": 0,
                "updated_at": current_time,
            }
        )

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            current_time,
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_verify=True,
            verify_command="python -m unittest",
            verify_interval_seconds=3600,
        )

        self.assertNotIn("run_verification", [decision["type"] for decision in plan["decisions"]])

    def test_autonomous_verification_failure_attention_proposes_repair_task(self):
        state = default_state()
        add_attention_item(
            state,
            "verification",
            "Verification run #7 failed",
            "python -m unittest\nexit_code=1",
            priority="high",
        )

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
        )

        proposed = [decision for decision in plan["decisions"] if decision["type"] == "propose_task"]
        self.assertEqual(len(proposed), 1)
        self.assertEqual(proposed[0]["title"], "Fix Verification run #7 failed")
        self.assertEqual(proposed[0]["priority"], "high")
        self.assertIn("exit_code=1", proposed[0]["description"])

    def test_autonomous_verification_repair_task_is_not_duplicated(self):
        state = default_state()
        current_time = now_iso()
        add_attention_item(
            state,
            "verification",
            "Verification run #7 failed",
            "python -m unittest\nexit_code=1",
            priority="high",
        )
        state["tasks"].append(
            {
                "id": 1,
                "title": "Fix Verification run #7 failed",
                "description": "",
                "status": "todo",
                "priority": "high",
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

        titles = [
            decision.get("title")
            for decision in plan["decisions"]
            if decision["type"] == "propose_task"
        ]
        self.assertNotIn("Fix Verification run #7 failed", titles)


if __name__ == "__main__":
    unittest.main()
