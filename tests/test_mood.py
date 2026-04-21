import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.mood import build_mood_view_model, format_mood_view, render_mood_markdown
from mew.state import add_question, load_state, save_state, state_lock


class MoodTests(unittest.TestCase):
    def test_build_mood_view_model_scores_state(self):
        state = {
            "tasks": [
                {"id": 1, "title": "Open work", "status": "ready"},
                {"id": 2, "title": "Done A", "status": "done"},
                {"id": 3, "title": "Done B", "status": "done"},
            ],
            "outbox": [{"id": 4, "question_id": 2, "requires_reply": True, "text": "What next?"}],
            "work_sessions": [{"id": 5, "status": "active", "goal": "Continue work", "phase": "idle"}],
            "verification_runs": [{"id": 1, "exit_code": 0}],
            "runtime_effects": [{"id": 6, "reason": "passive_tick", "status": "applied"}],
        }

        view = build_mood_view_model(state, explicit_date="2026-04-17")
        text = render_mood_markdown(view)
        plain = format_mood_view(view)

        self.assertEqual(view["label"], "steady")
        self.assertEqual(view["scores"]["energy"]["score"], 54)
        self.assertIn("2 recent done task(s) add momentum", view["scores"]["energy"]["reasons"])
        self.assertIn("open task: #1 Open work [ready]", view["signals"])
        self.assertIn("open question #2: What next?", view["signals"])
        self.assertIn("runtime effect #6: applied/passive_tick", view["signals"])
        self.assertIn("# Mew Mood 2026-04-17", text)
        self.assertIn("Current mood: **steady**", text)
        self.assertIn("signals:", plain)
        self.assertIn("- open task: #1 Open work [ready]", plain)
        self.assertIn("- open question #2: What next?", plain)

    def test_build_mood_uses_canonical_question_status_when_available(self):
        state = {
            "questions": [{"id": 1, "status": "deferred", "text": "Not now."}],
            "outbox": [{"id": 1, "question_id": 1, "requires_reply": True, "text": "Not now?"}],
        }

        view = build_mood_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["scores"]["worry"]["score"], 20)
        self.assertNotIn("open question #1: Not now?", view["signals"])

    def test_build_mood_treats_weak_work_continuity_as_worry_signal(self):
        state = {
            "tasks": [{"id": 1, "title": "Investigate handoff", "status": "ready"}],
            "work_sessions": [
                {
                    "id": 5,
                    "task_id": 1,
                    "status": "active",
                    "goal": "Continue work",
                    "phase": "idle",
                    "tool_calls": [
                        {
                            "id": 1,
                            "tool": "read_file",
                            "status": "completed",
                            "summary": "x" * 210_000,
                            "result": {"path": "src/mew/mood.py"},
                        }
                    ],
                }
            ],
        }

        view = build_mood_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["scores"]["worry"]["score"], 30)
        self.assertIn(
            "1 active work session(s) have weak continuity",
            view["scores"]["worry"]["reasons"],
        )
        self.assertTrue(
            any(
                "work session #5 task #1 continuity weak 6/9: refresh working memory" in signal
                for signal in view["signals"]
            )
        )

    def test_productive_but_watchful_when_joy_and_worry_are_both_high(self):
        state = {
            "tasks": [{"id": index, "title": f"Done {index}", "status": "done"} for index in range(1, 9)],
            "outbox": [
                {"id": index, "question_id": index, "requires_reply": True, "text": f"Question {index}"}
                for index in range(1, 5)
            ],
            "attention": {
                "items": [{"id": index, "status": "open", "title": f"Attention {index}"} for index in range(1, 4)]
            },
            "verification_runs": [{"id": index, "exit_code": 0} for index in range(1, 9)],
        }

        view = build_mood_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["label"], "productive but watchful")
        self.assertEqual(view["scores"]["worry"]["score"], 74)
        self.assertEqual(view["scores"]["joy"]["score"], 65)

    def test_mood_command_outputs_json_and_can_write_report(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["tasks"].append({"id": 1, "title": "Open work", "status": "ready"})
                    add_question(state, "Need input?")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["mood", "--date", "2026-04-17", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["date"], "2026-04-17")
                self.assertIn("energy", data["scores"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["mood", "--date", "2026-04-17", "--write", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                path = Path(data["path"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(path, Path(".mew/mood/2026-04-17.md"))
            self.assertTrue((Path(tmp) / path).exists())

    def test_mood_command_rejects_invalid_date_and_json_show(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["mood", "--date", "../../outside"]), 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["mood", "--json", "--show"]), 1)
        self.assertIn("--json and --show cannot be used together", stderr.getvalue())

    def test_mood_command_reports_write_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "not-a-dir"
            output_file.write_text("", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["mood", "--write", "--output-dir", str(output_file)]), 1)

        self.assertIn("failed to write report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
