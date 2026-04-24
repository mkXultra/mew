import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.self_memory import build_self_memory_view_model, render_self_memory_markdown
from mew.state import load_state, save_state, state_lock


class SelfMemoryTests(unittest.TestCase):
    def test_build_self_memory_view_model_collects_traits_learnings_and_cues(self):
        state = {
            "traits": ["prefers small verified slices"],
            "learnings": ["journal helps reentry"],
            "tasks": [
                {
                    "id": 1,
                    "title": "Done work",
                    "status": "done",
                    "notes": "2026-04-17 done: report surfaces should be generated locally",
                },
                {"id": 2, "title": "Open work", "status": "ready"},
            ],
            "work_sessions": [
                {
                    "id": 3,
                    "task_id": 2,
                    "status": "active",
                    "phase": "think",
                    "goal": "Continue report work",
                    "next_action": "run tests",
                }
            ],
        }

        view = build_self_memory_view_model(state, explicit_date="2026-04-17")
        text = render_self_memory_markdown(view)

        self.assertIn("prefers small verified slices", view["traits"])
        self.assertIn("journal helps reentry", view["learnings"])
        self.assertIn("report surfaces should be generated locally", view["learnings"])
        self.assertIn(
            "Work session #3 task #2: Open work is think: Continue report work; continuity: 7/9 usable; repair: refresh working memory with a hypothesis, next step, verified state, or durable planning fields like plan_items, target_paths, or open_questions; next: run tests",
            view["continuity_cues"],
        )
        self.assertIn("# Mew Self Memory 2026-04-17", text)

    def test_self_memory_command_outputs_json_and_can_write_report(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["learnings"] = ["remember small reports"]
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["self-memory", "--date", "2026-04-17", "--write", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                path = Path(data["path"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(path, Path(".mew/self/learned-2026-04-17.md"))
            self.assertTrue((Path(tmp) / path).exists())

    def test_build_self_memory_view_model_ignores_malformed_tasks_container(self):
        state = {
            "traits": ["prefers small verified slices"],
            "learnings": ["journal helps reentry"],
            "tasks": 42,
        }

        view = build_self_memory_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["traits"], ["prefers small verified slices"])
        self.assertEqual(view["learnings"], ["journal helps reentry"])
        self.assertEqual(view["continuity_cues"], [])

    def test_self_memory_command_rejects_invalid_date_json_show_and_write_error(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["self-memory", "--date", "../../outside"]), 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["self-memory", "--json", "--show"]), 1)
        self.assertIn("--json and --show cannot be used together", stderr.getvalue())

        with tempfile.TemporaryDirectory() as tmp:
            output_file = Path(tmp) / "not-a-dir"
            output_file.write_text("", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["self-memory", "--write", "--output-dir", str(output_file)]), 1)
        self.assertIn("failed to write report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
