import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.dream import build_dream_view_model, render_dream_markdown
from mew.state import load_state, save_state, state_lock


class DreamTests(unittest.TestCase):
    def test_build_dream_view_model_collects_tasks_sessions_and_learnings(self):
        state = {
            "tasks": [
                {"id": 1, "title": "Open work", "status": "ready"},
                {"id": 2, "title": "Done work", "status": "done", "notes": "2026 done: learned one thing"},
            ],
            "work_sessions": [
                {
                    "id": 3,
                    "task_id": 1,
                    "status": "active",
                    "goal": "Continue work",
                    "phase": "think",
                    "next_action": "run tests",
                }
            ],
        }

        view = build_dream_view_model(state, explicit_date="2026-04-17")
        text = render_dream_markdown(view)

        self.assertEqual(view["active_tasks"], ["#1 Open work [ready]"])
        self.assertIn(
            "#3 task #1: Open work: Continue work [think]; continuity: 7/9 usable; repair: refresh working memory with a hypothesis, next step, or verified state; next: run tests",
            view["active_work_sessions"],
        )
        self.assertEqual(view["learnings"], ["learned one thing"])
        self.assertIn("# Mew Dream 2026-04-17", text)

    def test_dream_command_outputs_json_and_can_write_report(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["tasks"].append({"id": 1, "title": "Open work", "status": "ready"})
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["dream", "--date", "2026-04-17", "--write", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                path = Path(data["path"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(path, Path(".mew/dreams/2026-04-17.md"))
            self.assertTrue((Path(tmp) / path).exists())

    def test_dream_command_rejects_invalid_date_json_show_and_write_error(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["dream", "--date", "../../outside"]), 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["dream", "--json", "--show"]), 1)
        self.assertIn("--json and --show cannot be used together", stderr.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "not-a-dir"
            output_file.write_text("", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["dream", "--write", "--output-dir", str(output_file)]), 1)
        self.assertIn("failed to write report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
