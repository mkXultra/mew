import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import mew.commands as commands_module
from mew.cli import main
from mew.work_session import (
    add_work_session_todo,
    format_work_session_todos,
    format_work_session_resume,
    list_work_session_todos,
    update_work_session_todo,
)


class WorkSessionTodoTests(unittest.TestCase):
    def test_work_session_todos_guard_duplicate_open_items_and_single_in_progress(self):
        session = {"id": 7}

        first, error = add_work_session_todo(session, "Read source/test pair", status="in_progress")
        self.assertFalse(error)
        self.assertEqual(first["id"], "work-todo-7-1")

        duplicate, error = add_work_session_todo(session, "  read   source/test pair  ")
        self.assertEqual(duplicate, {})
        self.assertIn("duplicate open work todo", error)

        second, error = add_work_session_todo(session, "Draft one bounded patch", status="in_progress")
        self.assertEqual(second, {})
        self.assertIn("already in_progress", error)

        updated, error = update_work_session_todo(session, first["id"], status="done")
        self.assertFalse(error)
        self.assertEqual(updated["status"], "done")

        second, error = add_work_session_todo(session, "Draft one bounded patch", status="in_progress")
        self.assertFalse(error)
        self.assertEqual(second["status"], "in_progress")

        text = format_work_session_todos(list_work_session_todos(session))
        self.assertIn("work-todo-7-1 [done] Read source/test pair", text)
        self.assertIn("work-todo-7-2 [in_progress] Draft one bounded patch", text)

        resume_text = format_work_session_resume(
            {
                "session_id": 7,
                "task_id": 1,
                "status": "active",
                "phase": "idle",
                "updated_at": "now",
                "work_todos": list_work_session_todos(session),
            }
        )
        self.assertIn("work_todos:", resume_text)
        self.assertIn("work-todo-7-2 [in_progress] Draft one bounded patch", resume_text)

    def test_work_todo_cli_adds_updates_lists_session_items(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["task", "add", "M6.10 Todo D1", "--kind", "coding", "--json"])
                self.assertEqual(code, 0)
                task_id = str(json.loads(stdout.getvalue())["task"]["id"])

                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "work",
                            task_id,
                            "--todo-add",
                            "Read source/test pair",
                            "--todo-status",
                            "in_progress",
                            "--json",
                        ]
                    )
                self.assertEqual(code, 0)
                added = json.loads(stdout.getvalue())["todo"]
                self.assertEqual(added["status"], "in_progress")

                with redirect_stderr(StringIO()) as stderr:
                    code = main(["work", task_id, "--todo-add", "Read source/test pair"])
                self.assertEqual(code, 1)
                self.assertIn("duplicate open work todo", stderr.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["work", task_id, "--todo-update", added["id"], "--todo-status", "done", "--json"])
                self.assertEqual(code, 0)
                updated = json.loads(stdout.getvalue())["todo"]
                self.assertEqual(updated["status"], "done")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["work", task_id, "--todo-list"])
                self.assertEqual(code, 0)
                self.assertIn("Work todos", stdout.getvalue())
                self.assertIn("[done] Read source/test pair", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["task", "done", task_id])
                self.assertEqual(code, 0)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["work", task_id, "--todo-list"])
                self.assertEqual(code, 0)
                self.assertIn("[done] Read source/test pair", stdout.getvalue())

                state = commands_module.load_state()
                session = state["work_sessions"][0]
            finally:
                os.chdir(old_cwd)

        self.assertEqual(session["work_todos"][0]["status"], "done")


if __name__ == "__main__":
    unittest.main()
