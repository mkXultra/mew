import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.desk import build_desk_view_model, format_desk_view
from mew.state import add_outbox_message, load_state, save_state, state_lock


class DeskTests(unittest.TestCase):
    def test_build_desk_view_model_alerts_on_open_question(self):
        state = {
            "tasks": [{"id": 1, "title": "Build desk", "status": "ready"}],
            "outbox": [{"id": 1, "requires_reply": True, "text": "Need input?"}],
        }

        view = build_desk_view_model(state, explicit_date="2026-04-17")

        self.assertEqual(view["pet_state"], "alerting")
        self.assertEqual(view["focus"], "Waiting for reply: Need input?")
        self.assertEqual(view["counts"]["open_tasks"], 1)
        self.assertEqual(view["counts"]["open_questions"], 1)

    def test_build_desk_view_model_tracks_runtime_and_work_session(self):
        thinking = build_desk_view_model(
            {"runtime_status": {"state": "running", "current_phase": "planning"}},
            explicit_date="2026-04-17",
        )
        typing = build_desk_view_model(
            {"work_sessions": [{"id": 1, "status": "active", "goal": "Continue work"}]},
            explicit_date="2026-04-17",
        )

        self.assertEqual(thinking["pet_state"], "thinking")
        self.assertEqual(typing["pet_state"], "typing")
        self.assertEqual(typing["focus"], "Working on: Continue work")

    def test_format_desk_view(self):
        text = format_desk_view(
            {
                "date": "2026-04-17",
                "pet_state": "sleeping",
                "focus": "No active work recorded",
                "counts": {
                    "open_tasks": 0,
                    "open_questions": 0,
                    "active_work_sessions": 0,
                    "open_attention": 0,
                },
            }
        )

        self.assertIn("Mew desk 2026-04-17", text)
        self.assertIn("pet_state: sleeping", text)

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


if __name__ == "__main__":
    unittest.main()
