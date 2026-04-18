import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli_command import mew_command
from mew.cli import main
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
        )

        self.assertEqual(thinking["pet_state"], "thinking")
        self.assertEqual(precomputing["pet_state"], "thinking")
        self.assertEqual(committing["pet_state"], "typing")
        self.assertEqual(typing["pet_state"], "typing")
        self.assertEqual(typing["focus"], "Working on: Continue work")
        self.assertEqual(typing["primary_action"]["kind"], "resume_work")
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
            typing["details"]["active_work_sessions"][0]["command"],
            mew_command("work", "--session", "--resume", "--allow-read", "."),
        )

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
            }
        )

        self.assertIn("Mew desk 2026-04-17", text)
        self.assertIn("pet_state: sleeping", text)
        self.assertIn("primary_action: Open task #1", text)
        self.assertIn(f"primary_command: {mew_command('task', 'show', 1)}", text)
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

    def test_desk_command_rejects_invalid_date(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["desk", "--date", "../../outside"])

        self.assertEqual(code, 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
