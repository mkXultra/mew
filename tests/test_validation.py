import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from mew.cli import main
from mew.state import default_state, read_last_state_effect, save_state, state_digest
from mew.validation import format_validation_issues, validate_state, validation_errors


class ValidationTests(unittest.TestCase):
    def test_default_state_validates(self):
        issues = validate_state(default_state())

        self.assertEqual(validation_errors(issues), [])
        self.assertEqual(format_validation_issues(issues), "state_validation: ok")

    def test_duplicate_task_id_is_error(self):
        state = default_state()
        state["tasks"].extend(
            [
                {"id": 1, "title": "one", "status": "todo", "plans": []},
                {"id": 1, "title": "two", "status": "todo", "plans": []},
            ]
        )
        state["next_ids"]["task"] = 2

        issues = validate_state(state)

        self.assertIn("duplicate id 1", format_validation_issues(issues))
        self.assertTrue(validation_errors(issues))

    def test_save_state_rejects_invalid_state(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                state["tasks"].append({"id": 1, "title": "", "status": "todo", "plans": []})
                state["next_ids"]["task"] = 2

                with self.assertRaises(ValueError):
                    save_state(state)
            finally:
                os.chdir(old_cwd)

    def test_save_state_writes_effect_checkpoint(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                save_state(state)

                record = read_last_state_effect()

                self.assertEqual(record["type"], "state_saved")
                self.assertEqual(record["state_sha256"], state_digest(state))
                self.assertEqual(record["counts"]["tasks"], 0)
            finally:
                os.chdir(old_cwd)

    def test_doctor_prints_state_validation(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["doctor"])
                self.assertEqual(code, 0)
                self.assertIn("state_validation: ok", stdout.getvalue())
                self.assertIn("last_state_effect:", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_doctor_can_print_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["doctor", "--json"])
                data = json.loads(stdout.getvalue())

                self.assertEqual(code, 0)
                self.assertTrue(data["ok"])
                self.assertTrue(data["state"]["ok"])
                self.assertEqual(data["state"]["validation_issues"], [])
                self.assertIn("ai-cli", data["tools"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
