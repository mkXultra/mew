import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.agent import (
    act_phase,
    apply_action_plan,
    apply_event_plans,
    build_act_prompt,
    build_context,
    build_think_prompt,
    deterministic_action_plan,
    deterministic_decision_plan,
    normalize_action_plan,
    normalize_decision_plan,
    plan_event,
    process_events,
    think_phase,
)
from mew.read_tools import read_file
from mew.state import (
    add_attention_item,
    add_event,
    add_outbox_message,
    add_question,
    default_state,
    has_open_question,
    migrate_state,
)
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

    def test_migration_resolves_waiting_attention_covered_by_open_question(self):
        state = default_state()
        add_question(state, "Which option should I use?", related_task_id=1)
        waiting = add_attention_item(
            state,
            "waiting",
            "Waiting for user",
            "Which option should I use?",
            related_task_id=1,
        )

        migrated = migrate_state(state)
        open_attention = [
            item for item in migrated["attention"]["items"] if item.get("status") == "open"
        ]

        self.assertEqual(waiting["status"], "resolved")
        self.assertEqual(len(open_attention), 1)
        self.assertEqual(open_attention[0]["kind"], "question")

    def test_migration_keeps_distinct_waiting_attention_for_same_task(self):
        state = default_state()
        add_question(state, "Which option should I use?", related_task_id=1)
        waiting = add_attention_item(
            state,
            "waiting",
            "Waiting for user",
            "Need a separate deployment window.",
            related_task_id=1,
        )

        migrated = migrate_state(state)

        self.assertEqual(waiting["status"], "open")
        self.assertIn(waiting["id"], [item["id"] for item in migrated["attention"]["items"]])

    def test_migration_keeps_same_text_waiting_attention_for_different_task(self):
        state = default_state()
        add_question(state, "Which option should I use?", related_task_id=1)
        waiting = add_attention_item(
            state,
            "waiting",
            "Waiting for user",
            "Which option should I use?",
            related_task_id=2,
        )

        migrated = migrate_state(state)

        self.assertEqual(waiting["status"], "open")
        self.assertIn(waiting["id"], [item["id"] for item in migrated["attention"]["items"]])

    def test_migration_keeps_task_waiting_attention_when_question_is_taskless(self):
        state = default_state()
        add_question(state, "Need approval?")
        waiting = add_attention_item(
            state,
            "waiting",
            "Waiting for user",
            "Need approval?",
            related_task_id=2,
        )

        migrated = migrate_state(state)

        self.assertEqual(waiting["status"], "open")
        self.assertIn(waiting["id"], [item["id"] for item in migrated["attention"]["items"]])

    def test_has_open_question_checks_question_state_after_outbox_read(self):
        state = default_state()
        question, _created = add_question(state, "Should I keep observing?")
        for message in state["outbox"]:
            if message.get("question_id") == question["id"]:
                message["read_at"] = "already-seen"

        self.assertTrue(has_open_question(state, "Should I keep observing?"))

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

    def test_thought_journal_keeps_task_threads_when_wording_changes(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Review recent workspace changes",
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
        first = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            first,
            {
                "summary": "start",
                "open_threads": [
                    "Review recent workspace changes by reading a small amount of one recently changed file."
                ],
            },
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
            {
                "summary": "continue",
                "open_threads": [
                    "Review recent workspace changes for task #1 by reading one more recent allowed file."
                ],
            },
            {"summary": "continue", "actions": [{"type": "record_memory", "summary": "continue"}]},
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(state["thought_journal"][-1]["dropped_threads"], [])

    def test_thought_journal_removes_threads_resolved_in_same_cycle(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            event,
            {
                "summary": "done",
                "open_threads": ["Read README next.", "Keep monitoring."],
                "resolved_threads": ["Read README next."],
            },
            {"summary": "done", "actions": [{"type": "record_memory", "summary": "done"}]},
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(state["thought_journal"][-1]["open_threads"], ["Keep monitoring."])

    def test_passive_info_messages_are_created_read(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")

        apply_action_plan(
            state,
            event,
            {"summary": "routine", "decisions": []},
            {
                "summary": "routine",
                "actions": [
                    {
                        "type": "send_message",
                        "message_type": "info",
                        "text": "Routine passive progress.",
                    }
                ],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(len(state["outbox"]), 1)
        self.assertIsNotNone(state["outbox"][0]["read_at"])

    def test_non_autonomous_passive_idle_does_not_ask_for_new_task(self):
        state = default_state()
        event = {"id": 1, "type": "passive_tick"}

        plan = deterministic_decision_plan(
            state,
            event,
            now_iso(),
            allow_task_execution=False,
        )

        self.assertNotIn("ask_user", [decision["type"] for decision in plan["decisions"]])
        waits = [decision for decision in plan["decisions"] if decision["type"] == "wait_for_user"]
        self.assertEqual(waits[0]["reason"], "No actionable task.")
        apply_action_plan(
            state,
            event,
            plan,
            {"summary": plan["summary"], "actions": waits},
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )
        self.assertEqual(state["agent_status"]["mode"], "idle")
        self.assertIsNone(state["agent_status"]["pending_question"])

    def test_user_info_and_passive_warnings_stay_unread(self):
        state = default_state()
        user_event = add_event(state, "user_message", "test", {"text": "status?"})
        passive_event = add_event(state, "passive_tick", "test")

        apply_action_plan(
            state,
            user_event,
            {"summary": "reply", "decisions": []},
            {
                "summary": "reply",
                "actions": [
                    {
                        "type": "send_message",
                        "message_type": "info",
                        "text": "User-visible status.",
                    }
                ],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )
        apply_action_plan(
            state,
            passive_event,
            {"summary": "warn", "decisions": []},
            {
                "summary": "warn",
                "actions": [
                    {
                        "type": "send_message",
                        "message_type": "warning",
                        "text": "Action required.",
                    }
                ],
            },
            "later",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertIsNone(state["outbox"][0]["read_at"])
        self.assertIsNone(state["outbox"][1]["read_at"])

    def test_external_event_info_stays_unread(self):
        state = default_state()
        event = add_event(state, "file_change", "watch", {"path": "README.md"})

        apply_action_plan(
            state,
            event,
            {"summary": "external", "decisions": []},
            {
                "summary": "external",
                "actions": [
                    {
                        "type": "send_message",
                        "message_type": "info",
                        "text": "External event handled.",
                    }
                ],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="external_event",
        )

        self.assertEqual(len(state["outbox"]), 1)
        self.assertIsNone(state["outbox"][0]["read_at"])

    def test_wait_for_user_does_not_duplicate_question_attention(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        second = add_event(state, "passive_tick", "test")
        question = "Which option should I use?"

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
                        "question": question,
                    }
                ],
            },
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )
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
                        "question": question,
                    }
                ],
            },
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        open_attention = [item for item in state["attention"]["items"] if item["status"] == "open"]
        self.assertEqual(len(open_attention), 1)
        self.assertEqual(open_attention[0]["kind"], "question")

    def test_same_text_wait_for_user_on_different_task_creates_question(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        second = add_event(state, "passive_tick", "test")
        question = "Need approval?"

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
                        "question": question,
                    }
                ],
            },
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )
        apply_action_plan(
            state,
            second,
            {"summary": "wait", "decisions": [{"type": "wait_for_user", "task_id": 2}]},
            {
                "summary": "wait",
                "actions": [
                    {
                        "type": "wait_for_user",
                        "task_id": 2,
                        "question": question,
                    }
                ],
            },
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(
            [(item["text"], item["related_task_id"]) for item in state["questions"]],
            [(question, 1), (question, 2)],
        )

    def test_low_intent_user_message_does_not_create_ready_research_routing_question(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "dogfood no-op check"})
        task = add_planned_ready_task(state)
        task["title"] = "補助金について調べる"
        task["kind"] = "research"
        task["command"] = ""
        task["agent_backend"] = ""
        question = "Task #1 is ready but has no command. What should I execute for it?"

        counts = apply_action_plan(
            state,
            event,
            {
                "summary": "wait",
                "agent_status": {"pending_question": question},
                "decisions": [{"type": "wait_for_user", "task_id": 1}],
            },
            {
                "summary": "wait",
                "actions": [
                    {
                        "type": "wait_for_user",
                        "task_id": 1,
                    }
                ],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )

        self.assertEqual(counts["messages"], 0)
        self.assertEqual(state["questions"], [])
        self.assertEqual(state["attention"]["items"], [])
        self.assertNotEqual(state["agent_status"].get("mode"), "waiting_for_user")
        self.assertFalse(state["agent_status"].get("pending_question"))
        self.assertEqual(state["user_status"].get("mode"), "idle")

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

    def test_user_message_preserves_previous_autonomous_thread(self):
        state = default_state()
        first = add_event(state, "passive_tick", "test")
        apply_action_plan(
            state,
            first,
            {"summary": "start", "open_threads": ["Continue workspace inspection."]},
            {"summary": "start", "actions": [{"type": "record_memory", "summary": "start"}]},
            "first",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        second = add_event(state, "user_message", "user", {"text": "status?"})
        apply_action_plan(
            state,
            second,
            {"summary": "answer"},
            {
                "summary": "answer",
                "actions": [{"type": "send_message", "text": "ok"}],
            },
            "second",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )

        thought = state["thought_journal"][-1]
        self.assertIn("Continue workspace inspection.", thought["open_threads"])
        self.assertEqual(thought["dropped_threads"], [])

    def test_user_status_clears_waiting_after_response(self):
        state = default_state()
        state["user_status"]["mode"] = "waiting_for_agent"
        event = add_event(state, "user_message", "user", {"text": "status?"})

        apply_action_plan(
            state,
            event,
            {"summary": "answer"},
            {"summary": "answer", "actions": [{"type": "send_message", "text": "ok"}]},
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )

        self.assertEqual(state["user_status"]["mode"], "idle")

    def test_user_status_needs_user_when_response_asks_question(self):
        state = default_state()
        state["user_status"]["mode"] = "waiting_for_agent"
        event = add_event(state, "user_message", "user", {"text": "status?"})

        apply_action_plan(
            state,
            event,
            {"summary": "ask"},
            {"summary": "ask", "actions": [{"type": "ask_user", "question": "Which task?"}]},
            "now",
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="user_input",
        )

        self.assertEqual(state["user_status"]["mode"], "needs_user")

    def test_user_status_clears_waiting_after_processed_without_response(self):
        state = default_state()
        state["user_status"]["mode"] = "waiting_for_agent"
        event = add_event(state, "user_message", "user", {"text": "status?"})

        apply_event_plans(
            state,
            event["id"],
            {"summary": "no response", "decisions": []},
            {"summary": "no response", "actions": []},
            "now",
            reason="user_input",
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(state["user_status"]["mode"], "idle")

    def test_build_context_compacts_large_task_and_agent_run_payloads(self):
        state = default_state()
        current_time = now_iso()
        long_text = "large-context-payload " * 1000
        task = {
            "id": 1,
            "title": "Compress context",
            "description": long_text,
            "status": "todo",
            "priority": "high",
            "notes": long_text,
            "command": "python -m unittest",
            "cwd": ".",
            "auto_execute": False,
            "agent_backend": "ai-cli",
            "agent_model": "claude-ultra",
            "agent_prompt": long_text,
            "agent_run_id": 1,
            "plans": [
                {
                    "id": 1,
                    "status": "planned",
                    "backend": "ai-cli",
                    "model": "claude-ultra",
                    "cwd": ".",
                    "objective": long_text,
                    "approach": long_text,
                    "implementation_prompt": long_text,
                    "review_prompt": long_text,
                    "created_at": current_time,
                    "updated_at": current_time,
                }
            ],
            "latest_plan_id": 1,
            "runs": [
                {
                    "command": "python -m unittest",
                    "cwd": ".",
                    "exit_code": 1,
                    "stdout": long_text,
                    "stderr": long_text,
                    "started_at": current_time,
                    "finished_at": current_time,
                }
            ],
            "created_at": current_time,
            "updated_at": current_time,
        }
        state["tasks"].append(task)
        state["agent_runs"].append(
            {
                "id": 1,
                "task_id": 1,
                "purpose": "implementation",
                "status": "completed",
                "backend": "ai-cli",
                "model": "claude-ultra",
                "cwd": ".",
                "prompt": long_text,
                "command": ["ai-cli", "run", "--prompt", long_text],
                "stdout": long_text,
                "stderr": long_text,
                "result": long_text,
                "review_report": {
                    "status": "needs_fix",
                    "summary": long_text,
                    "findings": [long_text] * 8,
                    "follow_up": [long_text] * 8,
                },
                "created_at": current_time,
                "updated_at": current_time,
            }
        )
        event = add_event(state, "user_message", "test", {"text": long_text})

        context = build_context(state, event, "later")
        context_json = json.dumps(context, ensure_ascii=False)

        self.assertLess(len(context_json), 40000)
        self.assertNotIn("implementation_prompt", context["todo"][0]["latest_plan"])
        self.assertNotIn("review_prompt", context["todo"][0]["latest_plan"])
        self.assertNotIn("prompt", context["agent_runs"][0])
        self.assertIn("prompt_chars", context["agent_runs"][0])
        self.assertLessEqual(len(context["agent_runs"][0]["result_tail"]), 620)
        self.assertLessEqual(len(context["agent_runs"][0]["review_report"]["summary"]), 620)
        self.assertEqual(len(context["agent_runs"][0]["review_report"]["findings"]), 5)
        self.assertLessEqual(len(context["agent_runs"][0]["review_report"]["findings"][0]), 620)
        self.assertEqual(context["context_stats"]["source_counts"]["agent_runs"], 1)
        self.assertGreater(context["context_stats"]["section_chars"]["todo"], 0)
        self.assertGreater(context["context_stats"]["section_chars"]["agent_runs"], 0)

    def test_build_context_includes_bounded_conversation_history(self):
        state = default_state()
        long_text = "conversation detail " * 200
        first = add_event(state, "user_message", "test", {"text": "first user message"})
        add_outbox_message(state, "assistant", "first assistant response", event_id=first["id"])
        add_outbox_message(state, "info", "internal progress without event")
        add_outbox_message(state, "assistant", "unlinked assistant")
        add_outbox_message(state, "question", "unlinked question")
        second = add_event(state, "user_message", "test", {"text": long_text})
        add_outbox_message(state, "info", "direct user reply", event_id=second["id"])
        add_outbox_message(state, "question", "Need a decision?", event_id=second["id"], requires_reply=True)

        context = build_context(state, second, "later")

        self.assertEqual([item["role"] for item in context["conversation"]], ["user", "mew", "user", "mew", "mew"])
        self.assertEqual(context["conversation"][0]["text"], "first user message")
        self.assertEqual(context["conversation"][1]["text"], "first assistant response")
        self.assertEqual(context["conversation"][3]["text"], "direct user reply")
        self.assertEqual(context["conversation"][4]["kind"], "question")
        self.assertTrue(context["conversation"][4]["requires_reply"])
        self.assertNotIn(
            "internal progress without event",
            [item["text"] for item in context["conversation"]],
        )
        self.assertNotIn(
            "unlinked assistant",
            [item["text"] for item in context["conversation"]],
        )
        self.assertNotIn(
            "unlinked question",
            [item["text"] for item in context["conversation"]],
        )
        self.assertLessEqual(len(context["conversation"][2]["text"]), 1020)
        self.assertEqual(context["context_stats"]["source_counts"]["conversation_items"], 5)
        self.assertEqual(context["context_stats"]["included_counts"]["conversation_items"], 5)

    def test_build_context_excludes_future_pending_conversation_turns(self):
        state = default_state()
        first = add_event(state, "user_message", "test", {"text": "first turn"})
        second = add_event(state, "user_message", "test", {"text": "second pending turn"})
        add_outbox_message(state, "assistant", "future response", event_id=second["id"])
        add_outbox_message(state, "assistant", "unlinked future assistant")

        context = build_context(state, first, "later")
        texts = [item["text"] for item in context["conversation"]]

        self.assertIn("first turn", texts)
        self.assertNotIn("second pending turn", texts)
        self.assertNotIn("future response", texts)
        self.assertNotIn("unlinked future assistant", texts)

    def test_build_context_clips_write_run_actual_fields(self):
        state = default_state()
        state["write_runs"].append(
            {
                "id": 1,
                "action_type": "edit_file",
                "path": "/tmp/example.py",
                "dry_run": False,
                "changed": True,
                "written": True,
                "rolled_back": True,
                "verification_run_id": 9,
                "verification_exit_code": 1,
                "rollback_error": "rollback detail " * 100,
                "diff": "-old\n+new\n" * 200,
                "reason": "Update example",
                "created_at": "now",
                "updated_at": "later",
            }
        )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")
        write_run = context["write_runs"][0]

        self.assertEqual(write_run["action_type"], "edit_file")
        self.assertTrue(write_run["changed"])
        self.assertTrue(write_run["written"])
        self.assertTrue(write_run["rolled_back"])
        self.assertEqual(write_run["verification_run_id"], 9)
        self.assertEqual(write_run["verification_exit_code"], 1)
        self.assertIn("rollback detail", write_run["rollback_error"])
        self.assertLessEqual(len(write_run["diff_tail"]), 620)

    def test_build_context_includes_recent_runtime_effects(self):
        state = default_state()
        for index in range(12):
            state["runtime_effects"].append(
                {
                    "id": index + 1,
                    "event_id": index + 10,
                    "event_type": "passive_tick",
                    "reason": "passive_tick",
                    "status": "verified",
                    "summary": "runtime effect " + ("detail " * 200),
                    "outcome": "outcome " + str(index),
                    "action_types": ["run_verification"],
                    "processed_count": 1,
                    "counts": {"actions": 1},
                    "verification_run_ids": [index + 100],
                    "write_run_ids": [],
                    "deferred": False,
                    "error": "",
                    "recovery_hint": "Retry this effect" if index == 11 else "",
                }
            )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        self.assertEqual(len(context["runtime_effects"]), 10)
        self.assertEqual(context["runtime_effects"][0]["id"], 3)
        self.assertEqual(context["runtime_effects"][-1]["verification_run_ids"], [111])
        self.assertEqual(context["runtime_effects"][-1]["outcome"], "outcome 11")
        self.assertEqual(context["runtime_effects"][-1]["recovery_hint"], "Retry this effect")
        self.assertLessEqual(len(context["runtime_effects"][0]["summary"]), 1220)
        self.assertEqual(context["context_stats"]["source_counts"]["runtime_effects"], 12)
        self.assertEqual(context["context_stats"]["included_counts"]["runtime_effects"], 10)
        self.assertEqual(context["context_stats"]["omitted_counts"]["runtime_effects"], 2)

    def test_build_context_includes_recent_step_runs(self):
        state = default_state()
        for index in range(7):
            state["step_runs"].append(
                {
                    "id": index + 1,
                    "at": f"t{index}",
                    "event_id": index + 10,
                    "summary": "step summary " + ("detail " * 300),
                    "stop_reason": "max_steps",
                    "actions": [{"type": "read_file", "path": f"file-{index}.md"}],
                    "skipped_actions": [{"type": "write_file", "path": f"file-{index}.md"}],
                    "effects": [
                        {
                            "type": "message",
                            "id": index + 20,
                            "message_type": "info",
                            "text": f"effect {index}",
                        }
                    ],
                    "counts": {"actions": 1},
                }
            )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        self.assertEqual(len(context["step_runs"]), 5)
        self.assertEqual(context["step_runs"][-1]["id"], 7)
        self.assertEqual(context["step_runs"][-1]["stop_reason"], "max_steps")
        self.assertEqual(context["step_runs"][-1]["actions"][0]["type"], "read_file")
        self.assertEqual(context["step_runs"][-1]["effects"][0]["text"], "effect 6")
        self.assertEqual(context["context_stats"]["source_counts"]["step_runs"], 7)
        self.assertEqual(context["context_stats"]["included_counts"]["step_runs"], 5)
        self.assertEqual(context["context_stats"]["omitted_counts"]["step_runs"], 2)

    def test_build_context_preserves_important_step_effects_when_capped(self):
        state = default_state()
        state["step_runs"].append(
            {
                "id": 1,
                "at": "now",
                "event_id": 2,
                "summary": "many effects",
                "stop_reason": "max_steps",
                "actions": [{"type": "read_file", "path": "README.md"}],
                "skipped_actions": [],
                "effects": [
                    {"type": "message", "id": index + 1, "text": f"message {index}"}
                    for index in range(12)
                ]
                + [
                    {
                        "type": "message",
                        "id": 90,
                        "message_type": "question",
                        "question_id": 91,
                        "text": "Need input?",
                    },
                    {"type": "question", "id": 91, "text": "Need input?"},
                    {"type": "verification_run", "id": 99, "exit_code": 1},
                    {"type": "write_run", "id": 100, "action_type": "edit_file"},
                ],
                "counts": {"actions": 1},
            }
        )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        effects = context["step_runs"][0]["effects"]
        self.assertEqual(len(effects), 8)
        self.assertIn(("message", 90), [(effect["type"], effect["id"]) for effect in effects])
        self.assertIn(("question", 91), [(effect["type"], effect["id"]) for effect in effects])
        self.assertIn("verification_run", [effect["type"] for effect in effects])
        self.assertIn("write_run", [effect["type"] for effect in effects])

    def test_build_context_preserves_attention_reason(self):
        state = default_state()
        long_reason = "verification failed because " + ("stderr detail " * 500)
        add_attention_item(
            state,
            "verification",
            "Verification failed",
            long_reason,
            related_task_id=3,
            question_id=4,
            priority="high",
        )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")
        attention = context["attention"][0]

        self.assertEqual(attention["title"], "Verification failed")
        self.assertEqual(attention["related_task_id"], 3)
        self.assertEqual(attention["question_id"], 4)
        self.assertIn("verification failed because", attention["reason"])
        self.assertLessEqual(len(attention["reason"]), 1220)

    def test_build_context_caps_and_clips_unanswered_questions(self):
        state = default_state()
        long_text = "question detail " * 500
        for index in range(60):
            state["questions"].append(
                {
                    "id": index + 1,
                    "text": f"Question {index} {long_text}",
                    "source": "agent",
                    "event_id": index + 1,
                    "related_task_id": index + 1,
                    "blocks": [f"block-{block}-{long_text}" for block in range(25)],
                    "status": "open",
                    "created_at": now_iso(),
                    "answered_at": None,
                    "answer_event_id": None,
                    "acknowledged_at": None,
                }
            )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        self.assertEqual(len(context["unanswered_questions"]), 20)
        self.assertEqual(context["unanswered_questions"][0]["id"], 41)
        self.assertEqual(context["unanswered_questions"][-1]["id"], 60)
        self.assertEqual(context["unanswered_questions_omitted_count"], 40)
        self.assertLessEqual(len(context["unanswered_questions"][0]["text"]), 1220)
        self.assertEqual(len(context["unanswered_questions"][0]["blocks"]), 5)
        self.assertEqual(context["unanswered_questions"][0]["blocks_omitted_count"], 20)
        self.assertEqual(context["context_stats"]["omitted_counts"]["unanswered_questions"], 40)

    def test_build_context_keeps_high_priority_attention_before_old_normal_items(self):
        state = default_state()
        for index in range(30):
            add_attention_item(
                state,
                "waiting",
                f"Normal item {index}",
                f"normal reason {index}",
                priority="normal",
            )
        high = add_attention_item(
            state,
            "verification",
            "Latest high priority failure",
            "critical verification reason",
            priority="high",
        )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")
        attention_ids = [item["id"] for item in context["attention"]]

        self.assertEqual(context["attention"][0]["id"], high["id"])
        self.assertIn(high["id"], attention_ids)
        self.assertEqual(context["attention_omitted_count"], 6)

    def test_build_context_preserves_old_active_agent_runs(self):
        state = default_state()
        current_time = now_iso()
        for run_id in range(1, 3):
            state["agent_runs"].append(
                {
                    "id": run_id,
                    "task_id": run_id,
                    "purpose": "implementation",
                    "status": "running",
                    "backend": "ai-cli",
                    "model": "codex-ultra",
                    "cwd": ".",
                    "created_at": current_time,
                    "updated_at": current_time,
                }
            )
        for run_id in range(3, 13):
            state["agent_runs"].append(
                {
                    "id": run_id,
                    "task_id": run_id,
                    "purpose": "implementation",
                    "status": "completed",
                    "backend": "ai-cli",
                    "model": "codex-ultra",
                    "cwd": ".",
                    "created_at": current_time,
                    "updated_at": current_time,
                }
            )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")
        run_ids = [run["id"] for run in context["agent_runs"]]

        self.assertIn(1, run_ids)
        self.assertIn(2, run_ids)
        self.assertEqual(len(run_ids), 8)
        self.assertEqual(context["context_stats"]["omitted_counts"]["agent_runs"], 4)

    def test_build_context_caps_many_active_agent_runs(self):
        state = default_state()
        current_time = now_iso()
        for run_id in range(1, 13):
            state["agent_runs"].append(
                {
                    "id": run_id,
                    "task_id": run_id,
                    "purpose": "implementation",
                    "status": "running",
                    "backend": "ai-cli",
                    "model": "codex-ultra",
                    "cwd": ".",
                    "created_at": current_time,
                    "updated_at": current_time,
                }
            )
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        self.assertEqual(len(context["agent_runs"]), 8)
        self.assertNotIn(1, [run["id"] for run in context["agent_runs"]])
        self.assertIn(12, [run["id"] for run in context["agent_runs"]])
        self.assertEqual(context["agent_runs_active_omitted_count"], 4)
        self.assertEqual(context["context_stats"]["omitted_counts"]["active_agent_runs"], 4)

    def test_build_context_clips_deep_memory_entries(self):
        state = default_state()
        state["memory"]["deep"]["decisions"].append("important decision " + ("detail " * 1000))
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")
        decision = context["memory"]["deep"]["decisions"][0]

        self.assertIn("important decision", decision)
        self.assertLessEqual(len(decision), 820)
        self.assertEqual(context["context_stats"]["limits"]["memory_chars"], 800)

    def test_build_context_clips_persisted_status_text(self):
        state = default_state()
        long_text = "large persisted user request " * 500
        state["runtime_status"]["last_action"] = long_text
        state["agent_status"]["current_focus"] = long_text
        state["agent_status"]["pending_question"] = long_text
        state["agent_status"]["last_thought"] = long_text
        state["user_status"]["current_focus"] = long_text
        state["user_status"]["last_request"] = [long_text for _ in range(8)]
        state["autonomy"]["last_desire"] = long_text
        event = add_event(state, "passive_tick", "test")

        context = build_context(state, event, "later")

        self.assertLessEqual(len(context["runtime_status"]["last_action"]), 1220)
        self.assertLessEqual(len(context["agent_status"]["current_focus"]), 1220)
        self.assertLessEqual(len(context["agent_status"]["pending_question"]), 1220)
        self.assertLessEqual(len(context["agent_status"]["last_thought"]), 1220)
        self.assertLessEqual(len(context["user_status"]["current_focus"]), 1220)
        self.assertEqual(len(context["user_status"]["last_request"]), 5)
        self.assertLessEqual(len(context["user_status"]["last_request"][0]), 1220)
        self.assertLessEqual(len(context["autonomy"]["last_desire"]), 1220)

    def test_resident_prompt_text_is_capped_and_not_duplicated_in_context(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        self_text = "SELF_START " + ("self body " * 1000) + "SELF_END"
        desires = "DESIRE_START " + ("desire body " * 1000) + "DESIRE_END"
        guidance = "GUIDANCE_START " + ("guidance body " * 1000) + "GUIDANCE_END"

        context = build_context(
            state,
            event,
            "later",
            self_text=self_text,
            desires=desires,
        )
        think_prompt = build_think_prompt(
            state,
            event,
            "later",
            False,
            guidance,
            "policy",
            self_text=self_text,
            desires=desires,
        )
        act_prompt = build_act_prompt(
            state,
            event,
            {"summary": "decide", "decisions": []},
            "later",
            False,
            "policy",
            self_text=self_text,
            desires=desires,
        )

        self.assertEqual(context["self"]["chars"], len(self_text))
        self.assertTrue(context["self"]["truncated_for_prompt"])
        self.assertEqual(context["desires"]["chars"], len(desires))
        self.assertTrue(context["desires"]["truncated_for_prompt"])
        for prompt in (think_prompt, act_prompt):
            self.assertEqual(prompt.count("SELF_START"), 1)
            self.assertEqual(prompt.count("DESIRE_START"), 1)
            self.assertNotIn("SELF_END", prompt)
            self.assertNotIn("DESIRE_END", prompt)
        self.assertEqual(think_prompt.count("GUIDANCE_START"), 1)
        self.assertNotIn("GUIDANCE_END", think_prompt)
        self.assertIn("record_memory, update_memory, self_review, or propose_task", act_prompt)
        self.assertIn("prefer closing the loop with send_message", think_prompt)
        self.assertIn("Do not turn a report request into an open-ended passive investigation.", act_prompt)
        self.assertIn('"type": "refine_task"', think_prompt)
        self.assertIn('"type": "refine_task"', act_prompt)
        self.assertNotIn("memory/self_review", act_prompt)
        self.assertNotIn("record/self_review", act_prompt)

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

    def test_act_phase_skips_model_when_think_phase_failed(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "hello"})
        decision_plan = {
            "summary": "fallback",
            "model_error": True,
            "decisions": [
                {
                    "type": "send_message",
                    "message_type": "warning",
                    "text": "Codex Web API THINK error: DNS failed",
                }
            ],
        }

        with patch("mew.agent.call_model_json") as call:
            plan = act_phase(
                state,
                event,
                decision_plan,
                now_iso(),
                {"access_token": "token"},
                "test-model",
                "https://example.invalid",
                5,
                False,
                False,
                "",
                model_backend="codex",
            )

        call.assert_not_called()
        self.assertEqual(plan["actions"], decision_plan["decisions"])

    def test_think_phase_preserves_required_guardrail_decisions(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Needs a plan",
                "kind": "coding",
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
        event = add_event(state, "passive_tick", "test")
        auth = {"access_token": "token"}

        with patch(
            "mew.agent.call_model_json",
            return_value={
                "summary": "inspect first",
                "decisions": [{"type": "read_file", "path": "README.md"}],
            },
        ):
            plan = think_phase(
                state,
                event,
                current_time,
                auth,
                "test-model",
                "https://example.invalid",
                5,
                False,
                False,
                "",
                "",
                autonomous=True,
                autonomy_level="propose",
                model_backend="codex",
            )

        decision_types = [decision["type"] for decision in plan["decisions"]]
        self.assertIn("read_file", decision_types)
        self.assertIn("plan_task", decision_types)
        plan_tasks = [decision for decision in plan["decisions"] if decision["type"] == "plan_task"]
        self.assertEqual(plan_tasks[0]["task_id"], 1)

    def test_think_phase_does_not_programmer_plan_admin_task(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Pay the electric bill",
                "kind": "admin",
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
        event = add_event(state, "passive_tick", "test")
        auth = {"access_token": "token"}

        with patch(
            "mew.agent.call_model_json",
            return_value={
                "summary": "remember only",
                "decisions": [{"type": "remember", "summary": "No user-visible change."}],
            },
        ):
            plan = think_phase(
                state,
                event,
                current_time,
                auth,
                "test-model",
                "https://example.invalid",
                5,
                False,
                False,
                "",
                "",
                autonomous=True,
                autonomy_level="propose",
                model_backend="codex",
            )

        self.assertNotIn("plan_task", [decision["type"] for decision in plan["decisions"]])

    def test_autonomous_task_actions_do_not_interrupt_running_task(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].extend(
            [
                {
                    "id": 1,
                    "title": "Implement later unplanned task",
                    "kind": "coding",
                    "description": "",
                    "status": "ready",
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
                },
                {
                    "id": 2,
                    "title": "Implement active task",
                    "kind": "coding",
                    "description": "",
                    "status": "running",
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
                },
                {
                    "id": 3,
                    "title": "Implement later dispatchable task",
                    "kind": "coding",
                    "description": "",
                    "status": "ready",
                    "priority": "normal",
                    "notes": "",
                    "command": "",
                    "cwd": ".",
                    "auto_execute": True,
                    "agent_backend": "ai-cli",
                    "agent_model": "codex-ultra",
                    "agent_prompt": "",
                    "agent_run_id": None,
                    "plans": [{"id": 1, "status": "planned"}],
                    "latest_plan_id": 1,
                    "runs": [],
                    "created_at": current_time,
                    "updated_at": current_time,
                },
            ]
        )

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            current_time,
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=True,
        )

        decision_types = [decision["type"] for decision in plan["decisions"]]
        self.assertNotIn("plan_task", decision_types)
        self.assertNotIn("dispatch_task", decision_types)

    def test_think_phase_deferred_question_does_not_block_programmer_plan(self):
        from mew.state import add_question, mark_question_deferred

        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Implement wait_outbox fix",
                "kind": "coding",
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
        question, _created = add_question(state, "Should this wait?", related_task_id=1)
        mark_question_deferred(state, question, reason="not now")
        event = add_event(state, "passive_tick", "test")
        auth = {"access_token": "token"}

        with patch(
            "mew.agent.call_model_json",
            return_value={"summary": "remember", "decisions": [{"type": "remember", "summary": "No change."}]},
        ):
            plan = think_phase(
                state,
                event,
                current_time,
                auth,
                "test-model",
                "https://example.invalid",
                5,
                False,
                False,
                "",
                "",
                autonomous=True,
                autonomy_level="propose",
                model_backend="codex",
            )

        plan_tasks = [decision for decision in plan["decisions"] if decision["type"] == "plan_task"]
        self.assertEqual(plan_tasks[0]["task_id"], 1)

    def test_think_phase_preserves_self_directed_task_guardrail(self):
        state = default_state()
        current_time = now_iso()
        event = add_event(state, "startup", "test")
        auth = {"access_token": "token"}

        with patch(
            "mew.agent.call_model_json",
            return_value={
                "summary": "inspect first",
                "decisions": [{"type": "read_file", "path": "README.md"}],
            },
        ):
            plan = think_phase(
                state,
                event,
                current_time,
                auth,
                "test-model",
                "https://example.invalid",
                5,
                False,
                False,
                "",
                "",
                autonomous=True,
                autonomy_level="act",
                model_backend="codex",
            )

        self_reviews = [decision for decision in plan["decisions"] if decision["type"] == "self_review"]
        self.assertEqual(len(self_reviews), 1)
        self.assertEqual(self_reviews[0]["proposed_task_title"], "Define the next useful mew task")

    def test_decision_plan_records_schema_issues(self):
        plan = normalize_decision_plan(
            {
                "summary": "bad plan",
                "decisions": [
                    {"type": "propose_task"},
                    {"type": "unknown_action", "summary": "x"},
                    "not an object",
                ],
            },
            "fallback",
        )

        messages = [issue["message"] for issue in plan["schema_issues"]]
        self.assertIn("required for this type", messages)
        self.assertIn("unsupported type 'unknown_action'", messages)
        self.assertIn("must be an object", messages)

    def test_action_plan_records_schema_issues(self):
        plan = normalize_action_plan(
            {
                "summary": "bad action",
                "actions": [
                    {"type": "send_message"},
                    {"type": "unknown_action"},
                    "not an object",
                ],
            },
            {"summary": "fallback", "actions": [{"type": "record_memory", "summary": "fallback"}]},
        )

        messages = [issue["message"] for issue in plan["schema_issues"]]
        self.assertIn("required for this type", messages)
        self.assertIn("unsupported type 'unknown_action'", messages)
        self.assertIn("must be an object", messages)
        self.assertEqual(plan["actions"], [{"type": "send_message"}])

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

    def test_process_events_reuses_prompt_context_for_think_and_act(self):
        state = default_state()
        add_event(state, "user_message", "test", {"text": "hello"})
        responses = [
            {
                "summary": "adapter summary",
                "decisions": [{"type": "remember", "summary": "adapter summary"}],
            },
            {
                "summary": "adapter action",
                "actions": [{"type": "record_memory", "summary": "adapter action"}],
            },
        ]

        with (
            patch("mew.agent.call_model_json", side_effect=responses),
            patch("mew.agent.build_context", wraps=build_context) as build,
        ):
            processed = process_events(
                state,
                "user_input",
                model_auth={"access_token": "token"},
                model="test-model",
                base_url="https://example.invalid",
                timeout=5,
                create_internal_event=False,
                model_backend="codex",
            )

        self.assertEqual(processed, 1)
        self.assertEqual(build.call_count, 1)

    def test_plan_event_can_reflexively_observe_before_acting(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("hello from reflex observation\n", encoding="utf-8")
                state = default_state()
                event = add_event(state, "user_message", "test", {"text": "inspect first"})
                responses = [
                    {
                        "summary": "Need to read first.",
                        "decisions": [{"type": "read_file", "path": "README.md", "max_chars": 200}],
                    },
                    {
                        "summary": "Saw the reflex observation.",
                        "decisions": [
                            {
                                "type": "send_message",
                                "message_type": "assistant",
                                "text": "README mentions reflex observation.",
                            }
                        ],
                    },
                    {
                        "summary": "Reply with observation.",
                        "actions": [
                            {
                                "type": "send_message",
                                "message_type": "assistant",
                                "text": "README mentions reflex observation.",
                            }
                        ],
                    },
                ]

                with patch("mew.agent.call_model_json", side_effect=responses) as call:
                    decision_plan, action_plan = plan_event(
                        state,
                        event,
                        now_iso(),
                        model_auth={"access_token": "token"},
                        model="test-model",
                        base_url="https://example.invalid",
                        timeout=5,
                        ai_ticks=False,
                        allowed_read_roots=[tmp],
                        model_backend="codex",
                        max_reflex_rounds=1,
                    )

                second_think_prompt = call.call_args_list[1].args[2]
                act_prompt = call.call_args_list[2].args[2]
                self.assertEqual(call.call_count, 3)
                self.assertEqual(decision_plan["summary"], "Saw the reflex observation.")
                self.assertEqual(decision_plan["reflex_rounds"], 1)
                self.assertIn("hello from reflex observation", decision_plan["reflex_observations"][0]["result"])
                self.assertIn("reflex_observations", second_think_prompt)
                self.assertIn("hello from reflex observation", second_think_prompt)
                self.assertIn("hello from reflex observation", act_prompt)
                self.assertEqual(action_plan["actions"][0]["type"], "send_message")
            finally:
                os.chdir(old_cwd)

    def test_reflex_observation_uses_repeat_read_guard(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("should not be re-read\n", encoding="utf-8")
                state = default_state()
                state["step_runs"].append(
                    {
                        "id": 1,
                        "actions": [{"type": "read_file", "path": "README.md"}],
                    }
                )
                event = add_event(state, "passive_tick", "test")
                responses = [
                    {
                        "summary": "Try repeated read.",
                        "decisions": [{"type": "read_file", "path": "README.md"}],
                    },
                    {
                        "summary": "Saw repeated-read skip.",
                        "decisions": [{"type": "remember", "summary": "Use existing context."}],
                    },
                    {
                        "summary": "Act after skip.",
                        "actions": [{"type": "record_memory", "summary": "Act after skip."}],
                    },
                ]

                with patch("mew.agent.call_model_json", side_effect=responses):
                    decision_plan, _action_plan = plan_event(
                        state,
                        event,
                        now_iso(),
                        model_auth={"access_token": "token"},
                        model="test-model",
                        base_url="https://example.invalid",
                        timeout=5,
                        autonomous=True,
                        autonomy_level="act",
                        allowed_read_roots=[tmp],
                        model_backend="codex",
                        max_reflex_rounds=1,
                    )
            finally:
                os.chdir(old_cwd)

        observation = decision_plan["reflex_observations"][0]
        self.assertEqual(observation["status"], "skipped")
        self.assertIn("recent context", observation["error"])
        self.assertNotIn("result", observation)

    def test_reflex_observation_treats_os_errors_as_refusals(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "inspect"})
        responses = [
            {
                "summary": "Read file.",
                "decisions": [{"type": "read_file", "path": "README.md"}],
            },
            {
                "summary": "Read was refused.",
                "decisions": [{"type": "remember", "summary": "Read was refused."}],
            },
            {
                "summary": "Act after refusal.",
                "actions": [{"type": "record_memory", "summary": "Act after refusal."}],
            },
        ]

        with (
            patch("mew.agent.call_model_json", side_effect=responses),
            patch("mew.agent.read_file", side_effect=PermissionError("permission denied")),
        ):
            decision_plan, _action_plan = plan_event(
                state,
                event,
                now_iso(),
                model_auth={"access_token": "token"},
                model="test-model",
                base_url="https://example.invalid",
                timeout=5,
                allowed_read_roots=["."],
                model_backend="codex",
                max_reflex_rounds=1,
            )

        observation = decision_plan["reflex_observations"][0]
        self.assertEqual(observation["status"], "refused")
        self.assertIn("permission denied", observation["error"])

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
        self.assertEqual(state["tasks"][0]["kind"], "")
        self.assertEqual(state["tasks"][0]["status"], "todo")
        self.assertGreaterEqual(counts["messages"], 1)
        self.assertIn("Self review:", state["memory"]["deep"]["decisions"][0])

    def test_self_review_defers_task_proposal_when_open_tasks_exist(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Existing autonomous task",
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
                        "summary": "Another idea.",
                        "proposed_task_title": "Second autonomous task",
                    }
                ],
            },
            current_time,
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(len(state["tasks"]), 1)
        self.assertIn("Deferred self-review task proposal", state["memory"]["deep"]["decisions"][-1])

    def test_complete_task_can_finish_self_proposed_task_at_act_level(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        task = add_planned_ready_task(state)
        task["status"] = "todo"
        task["notes"] = "Proposed by mew from event #1."
        add_question(state, "Should I mark task #1 done?", related_task_id=task["id"])

        counts = apply_action_plan(
            state,
            event,
            {"summary": "complete"},
            {
                "summary": "complete",
                "actions": [
                    {
                        "type": "complete_task",
                        "task_id": task["id"],
                        "summary": "Inspection objective is satisfied.",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(task["status"], "done")
        self.assertIn("complete_task", task["notes"])
        self.assertEqual(state["questions"][0]["status"], "answered")
        self.assertEqual(state["attention"]["items"][0]["status"], "resolved")
        self.assertEqual(counts["messages"], 1)

    def test_send_message_skips_same_event_duplicate_outbox_text(self):
        state = default_state()
        event = add_event(state, "user_message", "test")
        task = add_planned_ready_task(state)
        task["status"] = "todo"

        counts = apply_action_plan(
            state,
            event,
            {"summary": "complete"},
            {
                "summary": "complete",
                "actions": [
                    {
                        "type": "complete_task",
                        "task_id": task["id"],
                        "summary": "User confirmed done.",
                    },
                    {
                        "type": "send_message",
                        "text": "Completed task #1: Verify mew",
                    },
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(counts["messages"], 1)
        self.assertEqual(
            [message["text"] for message in state["outbox"]],
            ["Completed task #1: Verify mew"],
        )

    def test_send_message_skips_repeated_unread_warning(self):
        state = default_state()
        first = add_event(state, "passive_tick", "first")
        second = add_event(state, "passive_tick", "second")
        warning_action = {
            "summary": "warn",
            "actions": [
                {
                    "type": "send_message",
                    "message_type": "warning",
                    "text": "Codex Web API THINK error: DNS failed",
                }
            ],
        }

        first_counts = apply_action_plan(
            state,
            first,
            {"summary": "warn"},
            warning_action,
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )
        second_counts = apply_action_plan(
            state,
            second,
            {"summary": "warn"},
            warning_action,
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(first_counts["messages"], 1)
        self.assertEqual(second_counts["messages"], 0)
        self.assertEqual(len(state["outbox"]), 1)

    def test_wait_action_for_done_task_does_not_reopen_completion_question(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        task = add_planned_ready_task(state)
        task["status"] = "done"

        counts = apply_action_plan(
            state,
            event,
            {"summary": "stale closeout"},
            {
                "summary": "stale closeout",
                "actions": [
                    {
                        "type": "ask_user",
                        "task_id": task["id"],
                        "question": "Anything else you'd like help with?",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(counts["messages"], 0)
        self.assertEqual(state["questions"], [])
        self.assertEqual(state["attention"]["items"], [])
        self.assertNotEqual(state["agent_status"]["mode"], "waiting_for_user")

    def test_passive_tick_does_not_repeat_answered_task_question(self):
        state = default_state()
        task = add_planned_ready_task(state)
        task["status"] = "ready"
        task["command"] = ""
        task["agent_backend"] = ""
        question, _ = add_question(
            state,
            "Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?",
            related_task_id=task["id"],
        )
        question["status"] = "answered"
        state["outbox"][0]["read_at"] = "now"
        state["outbox"][0]["answered_at"] = "now"

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            now_iso(),
            allow_task_execution=False,
        )

        self.assertNotIn("ask_user", [decision["type"] for decision in plan["decisions"]])

    def test_passive_tick_refreshes_stale_task_question_once(self):
        state = default_state()
        task = add_planned_ready_task(state)
        task["kind"] = "coding"
        task["status"] = "ready"
        task["command"] = ""
        task["agent_backend"] = ""
        old_question, _ = add_question(
            state,
            "Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?",
            related_task_id=task["id"],
        )
        old_question["created_at"] = "2026-04-17T00:00:00Z"
        old_question["updated_at"] = "2026-04-17T00:00:00Z"
        state["outbox"][0]["created_at"] = "2026-04-17T00:00:00Z"

        event = {"id": 1, "type": "passive_tick"}
        current_time = "2026-04-18T12:00:00Z"
        plan = deterministic_decision_plan(
            state,
            event,
            current_time,
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
        )

        ask_actions = [decision for decision in plan["decisions"] if decision["type"] == "ask_user"]
        self.assertEqual(len(ask_actions), 1)
        self.assertEqual(ask_actions[0]["supersedes_question_id"], old_question["id"])
        self.assertNotIn("wait_for_user", [decision["type"] for decision in plan["decisions"]])

        counts = apply_action_plan(
            state,
            event,
            plan,
            deterministic_action_plan(plan),
            current_time,
            allow_task_execution=False,
            task_timeout=1,
            cycle_reason="passive_tick",
        )

        self.assertEqual(counts["messages"], 1)
        self.assertEqual(state["questions"][0]["status"], "deferred")
        self.assertIn("unanswered for", state["questions"][0]["defer_reason"])
        self.assertIsNotNone(state["outbox"][0]["read_at"])
        self.assertEqual(state["attention"]["items"][0]["status"], "resolved")
        self.assertEqual(state["questions"][1]["status"], "open")
        self.assertEqual(state["questions"][1]["related_task_id"], task["id"])
        self.assertIsNone(state["outbox"][-1]["read_at"])

    def test_passive_tick_uses_question_update_time_for_stale_refresh(self):
        state = default_state()
        task = add_planned_ready_task(state)
        task["kind"] = "coding"
        task["status"] = "ready"
        task["command"] = ""
        task["agent_backend"] = ""
        question, _ = add_question(
            state,
            "Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?",
            related_task_id=task["id"],
        )
        question["created_at"] = "2026-04-17T00:00:00Z"
        question["updated_at"] = "2026-04-18T11:30:00Z"

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            "2026-04-18T12:00:00Z",
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertNotIn("ask_user", [decision["type"] for decision in plan["decisions"]])
        waits = [decision for decision in plan["decisions"] if decision["type"] == "wait_for_user"]
        self.assertEqual(waits[0]["reason"], f"Question #{question['id']} is still unanswered.")

    def test_passive_tick_keeps_waiting_on_fresh_task_question(self):
        state = default_state()
        task = add_planned_ready_task(state)
        task["kind"] = "coding"
        task["status"] = "ready"
        task["command"] = ""
        task["agent_backend"] = ""
        question, _ = add_question(
            state,
            "Task #1 is ready but has no command or agent backend. Should I dispatch it to an agent, add a command, or block it?",
            related_task_id=task["id"],
        )
        question["created_at"] = "2026-04-18T11:00:00Z"

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            "2026-04-18T12:00:00Z",
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertNotIn("ask_user", [decision["type"] for decision in plan["decisions"]])
        waits = [decision for decision in plan["decisions"] if decision["type"] == "wait_for_user"]
        self.assertEqual(waits[0]["reason"], f"Question #{question['id']} is still unanswered.")

    def test_passive_tick_does_not_question_ready_task_while_task_running(self):
        state = default_state()
        ready_task = add_planned_ready_task(state)
        ready_task["command"] = ""
        ready_task["agent_backend"] = ""
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 2,
                "title": "Implement active task",
                "description": "",
                "status": "running",
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
        )

        self.assertNotIn("ask_user", [decision["type"] for decision in plan["decisions"]])
        waits = [decision for decision in plan["decisions"] if decision.get("type") == "wait_for_user"]
        self.assertEqual(
            waits[0]["reason"],
            "Next: advance coding task #2: Implement active task",
        )

    def test_complete_task_records_user_reported_passing_verification(self):
        state = default_state()
        event = add_event(state, "user_message", "test")
        task = add_planned_ready_task(state)
        task["status"] = "todo"

        apply_action_plan(
            state,
            event,
            {"summary": "complete"},
            {
                "summary": "complete",
                "actions": [
                    {
                        "type": "complete_task",
                        "task_id": task["id"],
                        "summary": "Ran python -m pytest -q; result: 3 passed.",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(len(state["verification_runs"]), 1)
        run = state["verification_runs"][0]
        self.assertEqual(run["task_id"], task["id"])
        self.assertEqual(run["command"], "user-reported")
        self.assertEqual(run["exit_code"], 0)
        self.assertIn("3 passed", run["stdout"])

    def test_complete_task_does_not_record_failed_user_report_as_passed(self):
        state = default_state()
        event = add_event(state, "user_message", "test")
        task = add_planned_ready_task(state)
        task["status"] = "todo"

        apply_action_plan(
            state,
            event,
            {"summary": "complete"},
            {
                "summary": "complete",
                "actions": [
                    {
                        "type": "complete_task",
                        "task_id": task["id"],
                        "summary": "Ran pytest and one test failed.",
                    }
                ],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
        )

        self.assertEqual(state["verification_runs"], [])

    def test_complete_task_refuses_user_task_during_autonomous_cycle(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        task = add_planned_ready_task(state)
        task["status"] = "todo"
        task["notes"] = "Created by user."

        apply_action_plan(
            state,
            event,
            {"summary": "complete"},
            {
                "summary": "complete",
                "actions": [{"type": "complete_task", "task_id": task["id"]}],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(task["status"], "todo")
        self.assertIn("Refused complete_task", state["outbox"][0]["text"])

    def test_autonomous_refine_task_updates_self_proposed_task_and_resets_plan(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        task = add_planned_ready_task(state)
        task["title"] = "Define the next useful mew task"
        task["description"] = "Generic next step."
        task["notes"] = "Proposed by mew from event #1."
        state["next_ids"]["plan"] = 2
        old_plan = task["plans"][0]

        counts = apply_action_plan(
            state,
            event,
            {"summary": "refine"},
            {
                "summary": "refine",
                "actions": [
                    {
                        "type": "refine_task",
                        "task_id": task["id"],
                        "title": "Persist concrete next-step hints",
                        "description": "Let mew turn synthesis into task motion.",
                        "kind": "coding",
                        "priority": "high",
                        "notes": "Refined from dogfood synthesis.",
                        "reset_plan": True,
                        "objective": "Implement concrete next-step persistence.",
                    }
                ],
            },
            "now",
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(counts["messages"], 1)
        self.assertEqual(task["title"], "Persist concrete next-step hints")
        self.assertEqual(task["description"], "Let mew turn synthesis into task motion.")
        self.assertEqual(task["priority"], "high")
        self.assertIn("refine_task", task["notes"])
        self.assertEqual(old_plan["status"], "superseded")
        self.assertEqual(task["latest_plan_id"], 2)
        self.assertEqual(task["plans"][-1]["objective"], "Implement concrete next-step persistence.")
        self.assertIn("Refined task", state["outbox"][0]["text"])

    def test_autonomous_refine_task_refuses_user_task(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        task = add_planned_ready_task(state)
        task["notes"] = "Created by user."

        apply_action_plan(
            state,
            event,
            {"summary": "refine"},
            {
                "summary": "refine",
                "actions": [{"type": "refine_task", "task_id": task["id"], "title": "New title"}],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertNotEqual(task["title"], "New title")
        self.assertIn("Refused refine_task", state["outbox"][0]["text"])

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

    def test_autonomous_propose_task_defers_when_open_tasks_exist(self):
        state = default_state()
        current_time = now_iso()
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
        event = add_event(state, "passive_tick", "test")

        apply_action_plan(
            state,
            event,
            {"summary": "propose"},
            {
                "summary": "propose",
                "actions": [
                    {
                        "type": "propose_task",
                        "title": "Another normal task",
                        "priority": "normal",
                    }
                ],
            },
            current_time,
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(len(state["tasks"]), 1)
        self.assertIn("Deferred propose_task", state["memory"]["deep"]["decisions"][-1])

    def test_repeated_autonomous_propose_task_defer_is_not_recorded_twice(self):
        state = default_state()
        current_time = now_iso()
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

        for index in range(2):
            event = add_event(state, "passive_tick", f"test-{index}")
            apply_action_plan(
                state,
                event,
                {"summary": "propose"},
                {
                    "summary": "propose",
                    "actions": [
                        {
                            "type": "propose_task",
                            "title": "Another normal task",
                            "priority": "normal",
                        }
                    ],
                },
                current_time,
                allow_task_execution=False,
                task_timeout=1,
                autonomous=True,
                autonomy_level="act",
            )

        decisions = state["memory"]["deep"]["decisions"]
        self.assertEqual(
            len([item for item in decisions if "Deferred propose_task because open tasks already exist" in item]),
            1,
        )

    def test_self_direction_proposal_waits_until_no_open_tasks(self):
        state = default_state()
        current_time = now_iso()
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

        self.assertNotIn(
            "Review mew self direction",
            [decision.get("title") for decision in plan["decisions"] if decision.get("type") == "propose_task"],
        )

    def test_non_ai_user_message_reply_uses_next_move(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Implement CLI polish",
                "kind": "coding",
                "description": "",
                "status": "ready",
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
            {"id": 1, "type": "user_message", "payload": {"text": "What should I do next?"}},
            current_time,
            allow_task_execution=False,
        )

        messages = [decision for decision in plan["decisions"] if decision.get("type") == "send_message"]
        self.assertEqual(messages[0]["text"], "Next: enter coding cockpit for task #1 with `./mew code 1`")

    def test_non_ai_passive_wait_surfaces_next_move(self):
        state = default_state()
        current_time = now_iso()
        state["tasks"].append(
            {
                "id": 1,
                "title": "Implement CLI polish",
                "kind": "coding",
                "description": "",
                "status": "ready",
                "priority": "normal",
                "notes": "",
                "command": "",
                "cwd": ".",
                "auto_execute": False,
                "agent_backend": "acm",
                "agent_model": "",
                "agent_prompt": "",
                "agent_run_id": None,
                "plans": [{"id": 1, "status": "dry_run"}],
                "latest_plan_id": 1,
                "runs": [],
                "created_at": current_time,
                "updated_at": current_time,
            }
        )
        state["agent_runs"].append(
            {
                "id": 1,
                "task_id": 1,
                "purpose": "implementation",
                "status": "dry_run",
                "created_at": current_time,
                "updated_at": current_time,
            }
        )

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            current_time,
            allow_task_execution=False,
        )

        waits = [decision for decision in plan["decisions"] if decision.get("type") == "wait_for_user"]
        self.assertEqual(
            waits[0]["reason"],
            'Next: dispatch dry-run task #1 for real with `./mew buddy --task 1 --dispatch`',
        )

    def test_autonomous_high_priority_propose_task_can_interrupt_open_tasks(self):
        state = default_state()
        current_time = now_iso()
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
        event = add_event(state, "passive_tick", "test")

        apply_action_plan(
            state,
            event,
            {"summary": "repair"},
            {
                "summary": "repair",
                "actions": [
                    {
                        "type": "propose_task",
                        "title": "Fix verification failure",
                        "priority": "high",
                    }
                ],
            },
            current_time,
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
        )

        self.assertEqual(len(state["tasks"]), 2)
        self.assertEqual(state["tasks"][-1]["title"], "Fix verification failure")

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

    def test_mew_internal_file_read_is_refused_inside_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            internal = Path(tmp) / ".mew"
            internal.mkdir()
            state_file = internal / "state.json"
            state_file.write_text("{}", encoding="utf-8")

            with self.assertRaises(ValueError):
                read_file(str(state_file), [tmp])

    def test_user_requested_read_action_updates_project_snapshot(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "inspect repo"})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

            apply_action_plan(
                state,
                event,
                {"summary": "inspect"},
                {
                    "summary": "inspect",
                    "actions": [
                        {
                            "type": "inspect_dir",
                            "path": str(root),
                        }
                    ],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                allowed_read_roots=[tmp],
                autonomous=False,
                autonomy_level="off",
            )

        snapshot = state["memory"]["deep"]["project_snapshot"]
        self.assertEqual(snapshot["project_types"], ["python"])
        self.assertEqual(snapshot["roots"][0]["key_dirs"], ["src", "tests"])

    def test_autonomous_read_action_marks_progress_message_read(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "README.md"
            target.write_text("hello", encoding="utf-8")

            apply_action_plan(
                state,
                event,
                {"summary": "read"},
                {
                    "summary": "read",
                    "actions": [{"type": "read_file", "path": str(target)}],
                },
                "read-time",
                allow_task_execution=False,
                task_timeout=1,
                allowed_read_roots=[tmp],
                autonomous=True,
                autonomy_level="act",
            )

        self.assertIn("Read file", state["outbox"][0]["text"])
        self.assertEqual(state["outbox"][0]["read_at"], "read-time")

    def test_autonomous_read_action_skips_recent_duplicate(self):
        state = default_state()
        event = add_event(state, "passive_tick", "test")
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "README.md"
            target.write_text("hello", encoding="utf-8")
            state["thought_journal"].append(
                {"actions": [{"type": "read_file", "path": str(target)}]}
            )

            counts = apply_action_plan(
                state,
                event,
                {"summary": "read"},
                {
                    "summary": "read",
                    "actions": [{"type": "read_file", "path": str(target)}],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                allowed_read_roots=[tmp],
                autonomous=True,
                autonomy_level="act",
            )

        self.assertEqual(counts["messages"], 1)
        self.assertIn("Skipped repeated read_file", state["outbox"][0]["text"])
        self.assertIsNotNone(state["outbox"][0]["read_at"])
        self.assertIn("Choose a different target", state["memory"]["shallow"]["current_context"])
        self.assertIn("Skipped repeated read_file", state["memory"]["deep"]["decisions"][0])
        self.assertEqual(state["memory"]["deep"]["project"], [])

    def test_user_requested_read_action_can_repeat_recent_read(self):
        state = default_state()
        event = add_event(state, "user_message", "test", {"text": "read it again"})
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "README.md"
            target.write_text("hello", encoding="utf-8")
            state["thought_journal"].append(
                {"actions": [{"type": "read_file", "path": str(target)}]}
            )

            apply_action_plan(
                state,
                event,
                {"summary": "read"},
                {
                    "summary": "read",
                    "actions": [{"type": "read_file", "path": str(target)}],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                allowed_read_roots=[tmp],
                autonomous=False,
                autonomy_level="off",
            )

        self.assertIn("Read file", state["outbox"][0]["text"])
        self.assertIsNone(state["outbox"][0]["read_at"])
        self.assertTrue(state["memory"]["deep"]["project"])

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
