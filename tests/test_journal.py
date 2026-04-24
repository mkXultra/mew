import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.journal import build_journal_view_model, render_journal_markdown
from mew.state import add_question, load_state, save_state, state_lock


class JournalTests(unittest.TestCase):
    def test_build_journal_view_model_summarizes_state(self):
        state = {
            "tasks": [
                {"id": 1, "title": "Open work", "status": "ready", "kind": "coding"},
                {
                    "id": 2,
                    "title": "Done work",
                    "status": "done",
                    "notes": "2026-04-17 done: shipped the first report",
                },
            ],
            "outbox": [{"id": 4, "question_id": 2, "requires_reply": True, "text": "What next?"}],
            "work_sessions": [
                {"id": 5, "task_id": 1, "status": "active", "goal": "Continue work", "phase": "idle"}
            ],
            "runtime_effects": [
                {
                    "id": 6,
                    "reason": "passive_tick",
                    "status": "applied",
                    "action_types": ["ask_user"],
                    "summary": "Asked one question",
                }
            ],
        }

        view = build_journal_view_model(state, explicit_date="2026-04-17")
        text = render_journal_markdown(view)

        self.assertEqual(view["date"], "2026-04-17")
        self.assertIn("#2 Done work [done]: shipped the first report", view["completed"])
        self.assertIn("#1 Open work [ready/coding]", view["active"])
        self.assertIn("Question #2: What next?", view["questions"])
        self.assertEqual(len(view["sessions"]), 1)
        self.assertIn("Work session #5 task #1: Open work is idle: Continue work", view["sessions"][0])
        self.assertIn("continuity: 7/9 usable", view["sessions"][0])
        self.assertIn("repair:", view["sessions"][0])
        self.assertIn(
            "next: continue the work session with /continue in chat or ./mew work 1 --live --max-steps 1",
            view["sessions"][0],
        )
        self.assertIn("effect #6 [applied/passive_tick] actions=ask_user: Asked one question", view["runtime_effects"])
        self.assertIn("# Mew Journal 2026-04-17", text)
        self.assertIn(
            "### Yesterday\n- #2 Done work [done]: shipped the first report\n- effect #6 [applied/passive_tick] actions=ask_user: Asked one question",
            text,
        )
        self.assertIn("## Morning", text)
        self.assertIn("## Evening", text)

    def test_journal_uses_canonical_question_status_when_available(self):
        state = {
            "questions": [{"id": 1, "status": "deferred", "text": "Not now."}],
            "outbox": [{"id": 1, "question_id": 1, "requires_reply": True, "text": "Not now?"}],
        }

        view = build_journal_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["questions"], [])
        self.assertIn("No active work is recorded", view["mew_note"])

    def test_journal_skips_done_task_work_session(self):
        state = {
            "tasks": [{"id": 1, "title": "Done task", "status": "done"}],
            "work_session": {"id": 1, "task_id": 1, "status": "active", "goal": "Stale done session"},
        }

        view = build_journal_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["sessions"], [])

    def test_journal_filters_dated_completed_work_and_effects_to_report_day(self):
        state = {
            "tasks": [
                {"id": 1, "title": "Old done", "status": "done", "updated_at": "2026-04-16T00:00:00Z"},
                {"id": 2, "title": "Today done", "status": "done", "updated_at": "2026-04-17T00:00:00Z"},
            ],
            "runtime_effects": [
                {"id": 1, "status": "applied", "reason": "passive_tick", "finished_at": "2026-04-16T00:00:00Z"},
                {"id": 2, "status": "applied", "reason": "passive_tick", "finished_at": "2026-04-17T00:00:00Z"},
            ],
        }

        view = build_journal_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["completed"], ["#2 Today done [done]"])
        self.assertEqual(view["runtime_effects"], ["effect #2 [applied/passive_tick] actions=-"])

    def test_journal_command_outputs_json_and_can_write_report(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["tasks"].append({"id": 1, "title": "Open work", "status": "ready"})
                    add_question(state, "Need input?")
                    state["work_sessions"] = [
                        {"id": 2, "task_id": 1, "status": "active", "goal": "Continue work", "phase": "idle"}
                    ]
                    state["runtime_effects"] = [
                        {
                            "id": 3,
                            "reason": "passive_tick",
                            "status": "applied",
                            "action_types": ["ask_user"],
                            "summary": "Asked one question",
                            "finished_at": "2026-04-17T00:00:00Z",
                        }
                    ]
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["journal", "--date", "2026-04-17", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["date"], "2026-04-17")
                self.assertEqual(data["counts"]["questions"], 1)
                self.assertEqual(data["counts"]["active"], 1)
                self.assertEqual(data["counts"]["sessions"], 1)
                self.assertEqual(data["counts"]["runtime_effects"], 1)
                self.assertEqual(data["counts"]["tomorrow_hints"], 3)
                self.assertEqual(data["completed"], [])
                self.assertEqual(data["active"], ["#1 Open work [ready]"])
                self.assertEqual(data["questions"], ["Question #1: Need input?"])
                self.assertEqual(len(data["sessions"]), 1)
                self.assertIn("Work session #2 task #1: Open work is idle: Continue work", data["sessions"][0])
                self.assertEqual(
                    data["runtime_effects"],
                    ["effect #3 [applied/passive_tick] actions=ask_user: Asked one question"],
                )
                self.assertEqual(len(data["tomorrow_hints"]), 3)
                self.assertEqual(
                    data["tomorrow_hints"][0],
                    "Answer or close: Question #1: Need input?",
                )
                resume_hint = data["tomorrow_hints"][1]
                self.assertTrue(
                    resume_hint.startswith(
                        "Resume: Work session #2 task #1: Open work is idle: Continue work"
                    )
                )
                self.assertIn("continuity:", resume_hint)
                self.assertIn("repair:", resume_hint)
                self.assertIn("next:", resume_hint)
                self.assertEqual(
                    data["tomorrow_hints"][2],
                    "Move forward: #1 Open work [ready]",
                )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["journal", "--date", "2026-04-17", "--write", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                path = Path(data["path"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(path, Path(".mew/journal/2026-04-17.md"))
            self.assertTrue((Path(tmp) / path).exists())

    def test_journal_command_rejects_invalid_date_and_json_show(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["journal", "--date", "../../outside"]), 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["journal", "--json", "--show"]), 1)
        self.assertIn("--json and --show cannot be used together", stderr.getvalue())

    def test_journal_command_reports_write_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "not-a-dir"
            output_file.write_text("", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["journal", "--write", "--output-dir", str(output_file)]), 1)

        self.assertIn("failed to write report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
