import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli_command import mew_command
from mew.cli import main
from mew.brief import coding_self_improve_focus_from_friction
from mew.desk import build_desk_view_model, format_desk_view
from mew.state import add_outbox_message, load_state, save_state, state_lock


class DeskTests(unittest.TestCase):
    def test_build_desk_view_model_alerts_on_open_question(self):
        state = {
            "tasks": [{"id": 1, "title": "Build desk", "status": "ready", "kind": "coding"}],
            "outbox": [{"id": 1, "requires_reply": True, "text": "Need input?", "related_task_id": 1}],
        }

        view = build_desk_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["pet_state"], "alerting")
        self.assertEqual(view["focus"], "Waiting for reply: Need input?")
        self.assertEqual(view["counts"]["open_tasks"], 1)
        self.assertEqual(view["counts"]["open_questions"], 1)
        self.assertEqual(view["primary_action"]["kind"], "reply")
        self.assertEqual(view["primary_action"]["command"], mew_command("reply", 1, "<reply>"))
        self.assertEqual(view["primary_action"]["reason"], "open question requires a reply")
        self.assertEqual([action["kind"] for action in view["actions"]], ["reply", "open_task"])
        self.assertEqual(view["actions"][0]["command"], mew_command("reply", 1, "<reply>"))
        self.assertEqual(view["actions"][1]["command"], mew_command("code", 1))
        self.assertEqual(view["details"]["questions"][0]["label"], "Question #1")
        self.assertEqual(view["details"]["questions"][0]["summary"], "Need input?")
        self.assertEqual(view["details"]["questions"][0]["command"], mew_command("reply", 1, "<reply>"))
        self.assertEqual(view["details"]["questions"][0]["task_id"], 1)
        self.assertEqual(view["details"]["tasks"][0]["label"], "Task #1")
        self.assertEqual(view["details"]["tasks"][0]["command"], mew_command("code", 1))

    def test_build_desk_view_model_uses_canonical_question_status_when_available(self):
        deferred = {
            "questions": [{"id": 1, "status": "deferred", "text": "Not now."}],
            "outbox": [{"id": 1, "question_id": 1, "requires_reply": True, "text": "Not now?"}],
        }
        reopened = {
            "questions": [{"id": 1, "status": "open", "text": "Reopened?"}],
            "outbox": [
                {
                    "id": 1,
                    "question_id": 1,
                    "requires_reply": True,
                    "answered_at": "2026-04-17T00:00:00Z",
                    "text": "Old outbox text",
                }
            ],
        }

        deferred_view = build_desk_view_model(deferred, explicit_date="2026-04-17")
        reopened_view = build_desk_view_model(reopened, explicit_date="2026-04-17")

        self.assertEqual(deferred_view["pet_state"], "sleeping")
        self.assertEqual(deferred_view["counts"]["open_questions"], 0)
        self.assertEqual(reopened_view["pet_state"], "alerting")
        self.assertEqual(reopened_view["focus"], "Waiting for reply: Reopened?")
        self.assertEqual(reopened_view["primary_action"]["command"], mew_command("reply", 1, "<reply>"))

    def test_build_desk_view_model_tracks_runtime_and_work_session(self):
        thinking = build_desk_view_model(
            {"runtime_status": {"state": "running", "current_phase": "planning"}},
            explicit_date="2026-04-17",
        )
        precomputing = build_desk_view_model(
            {"runtime_status": {"state": "running", "current_phase": "precomputing"}},
            explicit_date="2026-04-17",
        )
        committing = build_desk_view_model(
            {"runtime_status": {"state": "running", "current_phase": "committing"}},
            explicit_date="2026-04-17",
        )
        typing = build_desk_view_model(
            {
                "work_sessions": [
                    {
                        "id": 1,
                        "status": "active",
                        "goal": "Continue work",
                        "tool_calls": [
                            {
                                "id": 1,
                                "tool": "read_file",
                                "status": "completed",
                                "started_at": "2026-04-17T00:00:00Z",
                                "finished_at": "2026-04-17T00:00:01Z",
                            }
                        ],
                        "model_turns": [
                            {
                                "id": 1,
                                "status": "completed",
                                "started_at": "2026-04-17T00:00:01Z",
                                "finished_at": "2026-04-17T00:00:03Z",
                            }
                        ],
                    }
                ]
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T00:00:04Z",
        )

        self.assertEqual(thinking["pet_state"], "thinking")
        self.assertEqual(precomputing["pet_state"], "thinking")
        self.assertEqual(committing["pet_state"], "typing")
        self.assertEqual(typing["pet_state"], "typing")
        self.assertEqual(typing["focus"], "Working on: Continue work")
        self.assertEqual(typing["primary_action"]["kind"], "resume_work")
        self.assertEqual(typing["actions"][0]["kind"], "resume_work")
        self.assertEqual(typing["actions"][0]["reason"], "active work session can be resumed")
        self.assertEqual(typing["actions"][0]["effort_summary"], "effort=low steps=2/30 failures=0")
        self.assertEqual(
            typing["primary_action"]["command"],
            mew_command("work", "--session", "--resume", "--allow-read", "."),
        )
        self.assertEqual(typing["details"]["active_work_sessions"][0]["label"], "Work session #1")
        self.assertEqual(typing["details"]["active_work_sessions"][0]["effort"]["steps"]["used"], 2)
        self.assertEqual(
            typing["details"]["active_work_sessions"][0]["effort_summary"],
            "effort=low steps=2/30 failures=0",
        )
        self.assertEqual(
            typing["details"]["active_work_sessions"][0]["continuity_summary"],
            "continuity: 8/9 status=usable missing=working_memory_survived",
        )
        self.assertIn(
            "refresh working memory",
            typing["details"]["active_work_sessions"][0]["continuity_next"],
        )
        self.assertEqual(
            typing["details"]["active_work_sessions"][0]["command"],
            mew_command("work", "--session", "--resume", "--allow-read", "."),
        )
        self.assertIn("continuity: 8/9 status=usable", format_desk_view(typing))

    def test_build_desk_view_model_dedupes_sessions_and_skips_done_task_session(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": 1, "title": "Done work", "status": "done"},
                    {"id": 2, "title": "Open work", "status": "ready"},
                ],
                "work_session": {"id": 10, "task_id": 2, "status": "active", "goal": "Open session"},
                "work_sessions": [
                    {"id": 9, "task_id": 1, "status": "active", "goal": "Done session"},
                    {"id": 10, "task_id": 2, "status": "active", "goal": "Open session"},
                ],
            },
            explicit_date="2026-04-17",
        )

        self.assertEqual(view["pet_state"], "typing")
        self.assertEqual(view["counts"]["active_work_sessions"], 1)
        self.assertEqual(view["focus"], "Working on: Open session")

    def test_build_desk_view_model_alerts_on_open_attention(self):
        view = build_desk_view_model(
            {"attention": {"items": [{"id": 1, "status": "open", "title": "Needs review"}]}},
            explicit_date="2026-04-17",
        )

        self.assertEqual(view["pet_state"], "alerting")
        self.assertEqual(view["counts"]["open_attention"], 1)
        self.assertEqual(view["primary_action"]["kind"], "review_attention")
        self.assertEqual(view["actions"][0]["command"], mew_command("attention"))
        self.assertEqual(view["details"]["attention"][0]["label"], "Attention #1")
        self.assertEqual(view["details"]["attention"][0]["summary"], "Needs review")
        self.assertEqual(view["details"]["attention"][0]["command"], mew_command("attention"))

    def test_build_desk_view_model_limits_and_compacts_details(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": index, "title": "Task " + ("A" * 180), "status": "ready", "kind": "research"}
                    for index in range(1, 6)
                ]
            },
            explicit_date="2026-04-17",
        )

        self.assertEqual(len(view["details"]["tasks"]), 3)
        self.assertTrue(view["details"]["tasks"][0]["summary"].endswith("..."))
        self.assertEqual(view["details"]["tasks"][0]["command"], mew_command("task", "show", 1))

    def test_desk_actions_skip_duplicate_attention_and_active_task(self):
        view = build_desk_view_model(
            {
                "questions": [{"id": "1", "status": "open", "text": "Need input?"}],
                "tasks": [
                    {
                        "id": 3,
                        "title": "Active task",
                        "status": "ready",
                        "kind": "coding",
                        "updated_at": "2026-04-17T00:30:00Z",
                    },
                    {
                        "id": 4,
                        "title": "Next task",
                        "status": "ready",
                        "kind": "research",
                        "updated_at": "2026-04-17T00:15:00Z",
                    },
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": "3",
                        "status": "active",
                        "goal": "Active task",
                        "updated_at": "2026-04-17T00:45:00Z",
                    }
                ],
                "attention": {
                    "items": [
                        {"id": 1, "status": "open", "title": "Duplicate question", "question_id": 1},
                        {
                            "id": 2,
                            "status": "open",
                            "title": "Independent attention",
                            "created_at": "2026-04-17T00:20:00Z",
                        },
                    ]
                },
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
        )

        labels = [action["label"] for action in view["actions"]]

        self.assertEqual(labels, ["Reply to question #1", "Resume task #3", "Review attention #2", "Open task #4"])
        self.assertNotIn("Open task #3", labels)
        by_label = {action["label"]: action for action in view["actions"]}
        self.assertEqual(by_label["Resume task #3"]["stale_for_seconds"], 900)
        self.assertEqual(by_label["Review attention #2"]["stale_for_seconds"], 2400)
        self.assertEqual(by_label["Open task #4"]["stale_for_seconds"], 2700)

    def test_work_session_action_uses_last_execution_activity_for_staleness(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {
                        "id": 3,
                        "title": "Execution-stale task",
                        "status": "ready",
                        "kind": "coding",
                        "updated_at": "2026-04-17T00:59:00Z",
                    }
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Execution-stale task",
                        "updated_at": "2026-04-17T00:59:00Z",
                        "tool_calls": [
                            {
                                "id": 1,
                                "tool": "read_file",
                                "status": "completed",
                                "finished_at": "2026-04-17T00:45:00Z",
                            }
                        ],
                    }
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
        )

        self.assertEqual(view["primary_action"]["label"], "Resume task #3")
        self.assertEqual(view["primary_action"]["stale_for_seconds"], 900)

    def test_build_desk_view_model_prefers_session_with_newer_execution_activity(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": 3, "title": "Older execution", "status": "ready", "kind": "coding"},
                    {"id": 4, "title": "Newer execution", "status": "ready", "kind": "coding"},
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Older execution",
                        "updated_at": "2026-04-17T00:59:00Z",
                        "tool_calls": [
                            {
                                "id": 1,
                                "tool": "read_file",
                                "status": "completed",
                                "finished_at": "2026-04-17T00:20:00Z",
                            }
                        ],
                    },
                    {
                        "id": 9,
                        "task_id": 4,
                        "status": "active",
                        "goal": "Newer execution",
                        "updated_at": "2026-04-17T00:30:00Z",
                        "model_turns": [
                            {
                                "id": 3,
                                "status": "completed",
                                "finished_at": "2026-04-17T00:50:00Z",
                            }
                        ],
                    },
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
            kind="coding",
        )

        self.assertEqual(view["primary_action"]["label"], "Resume task #4")
        self.assertEqual(view["actions"][0]["label"], "Resume task #4")
        self.assertEqual(view["actions"][1]["label"], "Resume task #3")

    def test_build_desk_view_model_marks_stale_work_session_not_current_signal(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": 3, "title": "Old resident speech", "status": "ready", "kind": "coding"},
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Old resident speech",
                        "updated_at": "2026-04-17T00:30:00Z",
                        "tool_calls": [
                            {
                                "id": 1,
                                "tool": "read_file",
                                "status": "completed",
                                "finished_at": "2026-04-17T00:45:00Z",
                            }
                        ],
                    }
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T07:00:00Z",
            kind="coding",
        )

        action = view["primary_action"]
        detail = view["details"]["active_work_sessions"][0]

        self.assertEqual(view["pet_state"], "alerting")
        self.assertEqual(view["focus"], "Resumable stale work: Old resident speech")
        self.assertEqual(action["kind"], "resume_work")
        self.assertTrue(action["is_stale"])
        self.assertFalse(action["is_current_signal"])
        self.assertEqual(action["freshness"], "stale")
        self.assertEqual(action["reason"], "stale active work session can be resumed; not current live work")
        self.assertTrue(detail["is_stale"])
        self.assertFalse(detail["is_current_signal"])
        self.assertEqual(detail["freshness"], "stale")
        self.assertEqual(detail["last_active_at"], "2026-04-17T00:45:00Z")

    def test_build_desk_view_model_keeps_recent_work_session_current_signal(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": 3, "title": "Fresh resident speech", "status": "ready", "kind": "coding"},
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Fresh resident speech",
                        "updated_at": "2026-04-17T00:55:00Z",
                    }
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
            kind="coding",
        )

        self.assertEqual(view["pet_state"], "typing")
        self.assertEqual(view["focus"], "Working on: Fresh resident speech")
        self.assertFalse(view["primary_action"]["is_stale"])
        self.assertTrue(view["primary_action"]["is_current_signal"])
        self.assertEqual(view["primary_action"]["freshness"], "recent")

    def test_build_desk_view_model_surfaces_paused_active_work_session(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {"id": 3, "title": "Paused debug target", "status": "ready", "kind": "coding"},
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Paused debug target",
                        "stop_requested_at": "2026-04-17T00:55:00Z",
                        "stop_reason": "paused debug target",
                        "updated_at": "2026-04-17T00:59:00Z",
                    }
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
            kind="coding",
        )

        self.assertEqual(view["focus"], "Paused: Paused debug target")
        self.assertEqual(view["primary_action"]["kind"], "paused_work")
        self.assertEqual(view["primary_action"]["label"], "Paused task #3")
        self.assertEqual(view["primary_action"]["reason"], "active work session is intentionally paused")
        self.assertEqual(view["details"]["active_work_sessions"][0]["status"], "paused")

    def test_build_desk_view_model_skips_active_work_for_blocked_task(self):
        view = build_desk_view_model(
            {
                "tasks": [
                    {
                        "id": 3,
                        "title": "Blocked task",
                        "status": "blocked",
                        "kind": "coding",
                        "updated_at": "2026-04-17T00:30:00Z",
                    },
                    {
                        "id": 4,
                        "title": "Ready task",
                        "status": "ready",
                        "kind": "coding",
                        "updated_at": "2026-04-17T00:15:00Z",
                    },
                ],
                "work_sessions": [
                    {
                        "id": 8,
                        "task_id": 3,
                        "status": "active",
                        "goal": "Blocked task",
                        "updated_at": "2026-04-17T00:45:00Z",
                    }
                ],
            },
            explicit_date="2026-04-17",
            current_time="2026-04-17T01:00:00Z",
            kind="coding",
        )

        labels = [action["label"] for action in view["actions"]]

        self.assertNotIn("Resume task #3", labels)
        self.assertEqual(view["primary_action"]["label"], "Open task #4")
        self.assertEqual(view["counts"]["active_work_sessions"], 0)

    def test_build_desk_view_model_kind_filter_scopes_related_backlog(self):
        view = build_desk_view_model(
            {
                "questions": [
                    {"id": 2, "status": "open", "text": "Which city?", "related_task_id": 2},
                    {"id": 1, "status": "open", "text": "Which file?", "related_task_id": 1},
                ],
                "tasks": [
                    {"id": 1, "title": "Fix code", "status": "ready", "kind": "coding"},
                    {"id": 2, "title": "Research grants", "status": "ready", "kind": "research"},
                ],
                "work_sessions": [
                    {"id": 7, "task_id": 1, "status": "active", "goal": "Fix code"},
                    {"id": 8, "task_id": 2, "status": "active", "goal": "Research grants"},
                ],
                "attention": {
                    "items": [
                        {"id": 1, "status": "open", "title": "Coding attention", "related_task_id": 1},
                        {"id": 2, "status": "open", "title": "Research attention", "related_task_id": 2},
                    ]
                },
            },
            explicit_date="2026-04-17",
            kind="coding",
        )

        self.assertEqual(view["kind"], "coding")
        self.assertEqual(view["pet_state"], "alerting")
        self.assertEqual(view["focus"], "Waiting for reply: Which file?")
        self.assertEqual(view["counts"]["open_tasks"], 1)
        self.assertEqual(view["counts"]["open_questions"], 1)
        self.assertEqual(view["counts"]["active_work_sessions"], 1)
        self.assertEqual(view["counts"]["open_attention"], 1)
        self.assertEqual(view["primary_action"]["task_id"], 1)
        labels = [action["label"] for action in view["actions"]]
        self.assertEqual(labels, ["Reply to question #1", "Resume task #1", "Review attention #1"])
        self.assertEqual(view["details"]["tasks"][0]["label"], "Task #1")
        self.assertEqual(view["details"]["questions"][0]["label"], "Question #1")

    def test_build_desk_view_model_suggests_ready_self_improve_for_empty_coding_queue(self):
        view = build_desk_view_model({"tasks": [], "questions": [], "work_sessions": []}, kind="coding")
        focus = coding_self_improve_focus_from_friction({}, kind="coding")

        self.assertEqual(view["primary_action"]["kind"], "start_self_improve")
        self.assertEqual(
            view["primary_action"]["command"],
            mew_command(
                "self-improve",
                "--start-session",
                "--focus",
                focus,
            ),
        )

    def test_build_desk_view_model_skips_blocked_task_for_primary_action(self):
        state = {
            "tasks": [
                {
                    "id": 1,
                    "title": "Wait for long proof",
                    "status": "blocked",
                    "kind": "coding",
                    "effective_kind": "coding",
                }
            ],
            "questions": [],
            "work_sessions": [],
        }

        with patch(
            "mew.desk.coding_self_improve_focus_from_friction",
            return_value="Advance M5 audited self-improvement loop",
        ):
            view = build_desk_view_model(state, kind="coding")

        self.assertEqual(view["counts"]["open_tasks"], 1)
        self.assertEqual(view["focus"], "Blocked: #1 Wait for long proof [blocked]")
        self.assertEqual(view["primary_action"]["kind"], "start_self_improve")
        self.assertEqual(view["details"]["tasks"][0]["status"], "blocked")

    def test_build_desk_view_model_surfaces_context_checkpoint(self):
        with (
            patch(
                "mew.desk.latest_context_checkpoint",
                return_value={
                    "name": "Dogfood checkpoint",
                    "created_at": "2026-04-19T00:00:00Z",
                    "reentry_note": "Continue the saved plan.",
                },
            ),
            patch(
                "mew.desk.current_git_reentry_state",
                return_value={"status": "clean", "head": "abc123"},
            ),
        ):
            view = build_desk_view_model({"tasks": [], "questions": [], "work_sessions": []}, kind="coding")

        self.assertEqual(view["latest_context_checkpoint"]["name"], "Dogfood checkpoint")
        self.assertEqual(view["current_git"]["status"], "clean")
        self.assertNotIn("text", view["latest_context_checkpoint"])

    def test_build_desk_view_model_does_not_suggest_self_improve_outside_mew_project(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                view = build_desk_view_model({"tasks": [], "questions": [], "work_sessions": []}, kind="coding")
            finally:
                os.chdir(old_cwd)

        self.assertIsNone(view["primary_action"])
        self.assertEqual(view["actions"], [])

    def test_format_desk_view(self):
        text = format_desk_view(
            {
                "date": "2026-04-17",
                "pet_state": "sleeping",
                "focus": "No active work recorded",
                "primary_action": {"label": "Open task #1", "command": mew_command("task", "show", 1)},
                "counts": {
                    "open_tasks": 0,
                    "open_questions": 0,
                    "active_work_sessions": 0,
                    "open_attention": 0,
                },
                "details": {
                    "tasks": [
                        {
                            "label": "Task #1",
                            "summary": "Review desk",
                            "command": mew_command("task", "show", 1),
                        }
                    ]
                },
                "latest_context_checkpoint": {
                    "name": "Desk checkpoint",
                    "created_at": "2026-04-19T00:00:00Z",
                },
                "current_git": {"status": "clean", "head": "abc123"},
                "actions": [
                    {
                        "label": "Open task #1",
                        "command": mew_command("task", "show", 1),
                        "reason": "open task is available",
                        "stale_for_seconds": 60,
                    },
                    {
                        "label": "Review attention #2",
                        "command": mew_command("attention"),
                        "reason": "independent attention item is open",
                        "stale_for_seconds": 120,
                    },
                ],
            }
        )

        self.assertIn("Mew desk 2026-04-17", text)
        self.assertIn("pet_state: sleeping", text)
        self.assertIn("primary_action: Open task #1", text)
        self.assertIn(f"primary_command: {mew_command('task', 'show', 1)}", text)
        self.assertIn("checkpoint: Desk checkpoint (2026-04-19T00:00:00Z)", text)
        self.assertIn("checkpoint_git: clean head=abc123", text)
        self.assertIn("actions:", text)
        self.assertIn(
            f"- Review attention #2: independent attention item is open stale_for=2m -> {mew_command('attention')}",
            text,
        )
        self.assertEqual(text.count("Open task #1"), 1)
        self.assertIn("tasks:", text)
        self.assertIn(f"- Task #1: Review desk -> {mew_command('task', 'show', 1)}", text)

    def test_build_desk_view_model_action_for_coding_task(self):
        view = build_desk_view_model(
            {"tasks": [{"id": 3, "title": "Fix unit test failure", "status": "ready", "kind": ""}]},
            explicit_date="2026-04-17",
        )

        self.assertEqual(view["focus"], "Next: #3 Fix unit test failure [ready]")
        self.assertEqual(view["primary_action"]["kind"], "open_task")
        self.assertEqual(view["primary_action"]["command"], mew_command("code", 3))

    def test_desk_command_outputs_json_and_can_write_files(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "question", "Need input?", requires_reply=True)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["desk", "--date", "2026-04-17", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["pet_state"], "alerting")
                self.assertIn("reply 1", data["primary_action"]["command"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["desk", "--date", "2026-04-17", "--write", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                json_path = Path(data["paths"]["json"])
                markdown_path = Path(data["paths"]["markdown"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(json_path, Path(".mew/desk/2026-04-17.json"))
            self.assertEqual(markdown_path, Path(".mew/desk/2026-04-17.md"))
            self.assertTrue((Path(tmp) / json_path).exists())
            self.assertTrue((Path(tmp) / markdown_path).exists())

    def test_desk_command_accepts_kind_filter(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["tasks"].extend(
                        [
                            {"id": 1, "title": "Fix code", "status": "ready", "kind": "coding"},
                            {"id": 2, "title": "Research grants", "status": "ready", "kind": "research"},
                        ]
                    )
                    state["questions"].extend(
                        [
                            {"id": 1, "status": "open", "text": "Which file?", "related_task_id": 1},
                            {"id": 2, "status": "open", "text": "Which city?", "related_task_id": 2},
                        ]
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["desk", "--kind", "coding", "--json"]), 0)
                data = json.loads(stdout.getvalue())
            finally:
                os.chdir(old_cwd)

        self.assertEqual(data["kind"], "coding")
        self.assertEqual(data["counts"]["open_tasks"], 1)
        self.assertEqual(data["counts"]["open_questions"], 1)
        self.assertEqual(data["focus"], "Waiting for reply: Which file?")
        self.assertEqual(data["primary_action"]["task_id"], 1)

    def test_desk_command_rejects_invalid_date(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["desk", "--date", "../../outside"])

        self.assertEqual(code, 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
