import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from mew.cli import main
from mew.config import EFFECT_LOG_FILE, STATE_FILE, STATE_VERSION
from mew.state import default_state, load_state, read_last_state_effect, save_state, state_digest
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

    def test_write_verification_links_are_validated(self):
        state = default_state()
        state["verification_runs"].append({"id": 1, "exit_code": 0})
        state["write_runs"].extend(
            [
                {
                    "id": 1,
                    "written": True,
                    "dry_run": False,
                    "verification_run_id": 99,
                    "verification_exit_code": 0,
                },
                {
                    "id": 2,
                    "written": True,
                    "dry_run": False,
                    "verification_run_id": 1,
                    "verification_exit_code": 1,
                },
                {
                    "id": 3,
                    "written": True,
                    "dry_run": False,
                },
            ]
        )
        state["next_ids"]["verification_run"] = 2
        state["next_ids"]["write_run"] = 4

        issues = validate_state(state)
        formatted = format_validation_issues(issues)

        self.assertEqual(validation_errors(issues), [])
        self.assertIn("references missing verification run 99", formatted)
        self.assertIn("does not match verification run 1 exit_code 0", formatted)
        self.assertIn("written non-dry-run should link a verification run", formatted)

    def test_runtime_effect_links_are_validated(self):
        state = default_state()
        state["verification_runs"].append({"id": 1, "exit_code": 0})
        state["write_runs"].append({"id": 1, "written": True, "dry_run": False})
        state["runtime_effects"].extend(
            [
                {
                    "id": 1,
                    "status": "verified",
                    "finished_at": "done",
                    "verification_run_ids": [99],
                    "write_run_ids": [1],
                },
                {
                    "id": 2,
                    "status": "applied",
                    "verification_run_ids": [1],
                    "write_run_ids": [42],
                },
                {
                    "id": 3,
                    "status": "planning",
                    "finished_at": "done",
                },
            ]
        )
        state["next_ids"]["verification_run"] = 2
        state["next_ids"]["write_run"] = 2
        state["next_ids"]["runtime_effect"] = 4

        issues = validate_state(state)
        formatted = format_validation_issues(issues)

        self.assertEqual(validation_errors(issues), [])
        self.assertIn("references missing verification run 99", formatted)
        self.assertIn("references missing write run 42", formatted)
        self.assertIn("terminal status 'applied' should have finished_at", formatted)
        self.assertIn("incomplete status 'planning' should not be finished", formatted)

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

    def test_load_state_migrates_legacy_status_and_reflex_defaults(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(
                    json.dumps(
                        {
                            "version": 0,
                            "agent_status": {
                                "state": "running",
                                "pid": 123,
                                "last_action": "legacy action",
                                "last_evaluated_at": "2026-01-01T00:00:00+00:00",
                                "last_user_interaction_at": "2026-01-01T00:01:00+00:00",
                            },
                            "user_status": {
                                "state": "focused",
                                "updated_at": "2026-01-01T00:02:00+00:00",
                            },
                            "tasks": [
                                {
                                    "id": 7,
                                    "title": "legacy task",
                                    "status": "todo",
                                }
                            ],
                            "inbox": [],
                            "outbox": [],
                            "knowledge": {
                                "shallow": {
                                    "latest_task_summary": "legacy summary",
                                    "recent_events": ["old event"],
                                }
                            },
                            "next_ids": {
                                "task": 1,
                                "event": 1,
                                "message": 1,
                            },
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

                state = load_state()
                persisted = json.loads(STATE_FILE.read_text(encoding="utf-8"))

                self.assertEqual(state["version"], STATE_VERSION)
                self.assertEqual(persisted["version"], STATE_VERSION)
                self.assertEqual(state["runtime_status"]["state"], "running")
                self.assertEqual(state["runtime_status"]["pid"], 123)
                self.assertIsNone(state["runtime_status"]["last_agent_reflex_at"])
                self.assertEqual(state["runtime_status"]["last_agent_reflex_report"], {})
                self.assertEqual(state["agent_status"]["mode"], "idle")
                self.assertEqual(state["agent_status"]["last_thought"], "legacy action")
                self.assertEqual(state["user_status"]["mode"], "focused")
                self.assertEqual(
                    state["user_status"]["last_interaction_at"],
                    "2026-01-01T00:01:00+00:00",
                )
                self.assertEqual(
                    state["memory"]["shallow"]["latest_task_summary"],
                    "legacy summary",
                )
                self.assertEqual(state["tasks"][0]["plans"], [])
                self.assertEqual(state["next_ids"]["task"], 8)
                self.assertEqual(read_last_state_effect()["state_version"], STATE_VERSION)
            finally:
                os.chdir(old_cwd)

    def test_load_state_adds_new_runtime_fields_to_existing_runtime_status(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                legacy_state = default_state()
                legacy_state["version"] = 0
                del legacy_state["runtime_status"]["last_agent_reflex_at"]
                del legacy_state["runtime_status"]["last_agent_reflex_report"]
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text(json.dumps(legacy_state) + "\n", encoding="utf-8")

                state = load_state()

                self.assertIn("last_agent_reflex_at", state["runtime_status"])
                self.assertIn("last_agent_reflex_report", state["runtime_status"])
                self.assertIsNone(state["runtime_status"]["last_agent_reflex_at"])
                self.assertEqual(state["runtime_status"]["last_agent_reflex_report"], {})
                self.assertEqual(read_last_state_effect()["state_version"], STATE_VERSION)
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
                self.assertIn("current_sha256", data["state"])
                self.assertTrue(data["state"]["last_effect_matches_current"])
                self.assertIn("ai-cli", data["tools"])
            finally:
                os.chdir(old_cwd)

    def test_repair_can_print_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair", "--json"])
                data = json.loads(stdout.getvalue())

                self.assertEqual(code, 0)
                self.assertTrue(data["ok"])
                self.assertIn("after_sha256", data)
                self.assertEqual(data["validation_issues"], [])
            finally:
                os.chdir(old_cwd)

    def test_repair_marks_incomplete_runtime_effect_interrupted(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                add_runtime_effect(state, event, "passive_tick", "planning", "then")
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair"])
                repaired = load_state()

                self.assertEqual(code, 0)
                self.assertIn("interrupted_runtime_effect effect=#1 event=#1 planning->interrupted", stdout.getvalue())
                self.assertEqual(repaired["runtime_effects"][0]["status"], "interrupted")
                self.assertTrue(repaired["runtime_effects"][0]["finished_at"])
            finally:
                os.chdir(old_cwd)

    def test_effects_command_reads_state_checkpoints(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                save_state(default_state())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["effects", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(len(data["effects"]), 1)
                self.assertEqual(data["effects"][0]["type"], "state_saved")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["effects"]), 0)
                self.assertIn("state_saved", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["effects", "--limit", "0", "--json"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["effects"], [])
            finally:
                os.chdir(old_cwd)

    def test_runtime_effects_command_lists_journal(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect, complete_runtime_effect

                state = default_state()
                event = add_event(state, "startup", "runtime", {})
                effect = add_runtime_effect(state, event, "startup", "planning", "then")
                effect["action_types"] = ["send_message"]
                complete_runtime_effect(
                    state,
                    effect["id"],
                    "done",
                    "applied",
                    processed_count=1,
                    counts={"messages": 1},
                )
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["runtime-effects"]), 0)
                output = stdout.getvalue()
                self.assertIn("#1 [applied] event=#1 reason=startup", output)
                self.assertIn("actions=send_message", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["runtime-effects", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["runtime_effects"][0]["status"], "applied")
            finally:
                os.chdir(old_cwd)

    def test_repair_refuses_active_runtime_without_force(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.runtime_is_active", return_value=True):
                    with redirect_stderr(StringIO()) as stderr:
                        code = main(["repair"])

                self.assertEqual(code, 1)
                self.assertIn("runtime is active", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_repair_active_runtime_json_stays_structured(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.runtime_is_active", return_value=True):
                    with redirect_stdout(StringIO()) as stdout:
                        code = main(["repair", "--json"])
                data = json.loads(stdout.getvalue())

                self.assertEqual(code, 1)
                self.assertFalse(data["ok"])
                self.assertEqual(data["validation_issues"][0]["path"], "runtime_lock")
            finally:
                os.chdir(old_cwd)

    def test_repair_malformed_state_returns_validation_data(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
                STATE_FILE.write_text('{"next_ids": "bad"}\n', encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair", "--json"])
                data = json.loads(stdout.getvalue())

                self.assertEqual(code, 1)
                self.assertFalse(data["ok"])
                self.assertIn("unable to load or repair state", data["validation_issues"][0]["message"])
            finally:
                os.chdir(old_cwd)

    def test_effects_treats_non_object_json_as_corrupt(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                EFFECT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                EFFECT_LOG_FILE.write_text("[]\n", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["effects"]), 0)

                self.assertIn("corrupt_effect_record", stdout.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
