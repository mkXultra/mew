import json
import os
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.config import EFFECT_LOG_FILE, STATE_FILE, STATE_VERSION
from mew.state import default_state, load_state, read_last_state_effect, save_state, state_digest, state_lock
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

    def test_save_state_rotates_previous_state_backup(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                first = default_state()
                first["memory"]["shallow"]["latest_task_summary"] = "before"
                save_state(first)

                second = default_state()
                second["memory"]["shallow"]["latest_task_summary"] = "after"
                save_state(second)

                backup = STATE_FILE.with_name(f"{STATE_FILE.name}.bak")
                self.assertTrue(backup.exists())
                backup_state = json.loads(backup.read_text(encoding="utf-8"))
                current_state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                self.assertEqual(backup_state["memory"]["shallow"]["latest_task_summary"], "before")
                self.assertEqual(current_state["memory"]["shallow"]["latest_task_summary"], "after")
            finally:
                os.chdir(old_cwd)

    def test_state_lock_serializes_threads_in_process(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                entered = threading.Event()
                attempting = threading.Event()
                release = threading.Event()
                acquired = threading.Event()

                def holder():
                    with state_lock():
                        entered.set()
                        release.wait(timeout=2.0)

                def contender():
                    attempting.set()
                    with state_lock():
                        acquired.set()

                with patch("mew.state.fcntl.flock"):
                    holder_thread = threading.Thread(target=holder)
                    contender_thread = threading.Thread(target=contender)
                    holder_thread.start()
                    self.assertTrue(entered.wait(timeout=2.0))
                    contender_thread.start()
                    self.assertTrue(attempting.wait(timeout=2.0))
                    self.assertFalse(acquired.wait(timeout=0.05))
                    release.set()
                    holder_thread.join(timeout=2.0)
                    contender_thread.join(timeout=2.0)
                self.assertFalse(holder_thread.is_alive())
                self.assertFalse(contender_thread.is_alive())
                self.assertTrue(acquired.is_set())
            finally:
                release.set()
                os.chdir(old_cwd)

    def test_state_lock_allows_nested_same_thread_entry(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.state.fcntl.flock") as flock:
                    with state_lock():
                        with state_lock():
                            pass

                self.assertEqual(flock.call_count, 2)
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
                self.assertIn("decision: rerun_event effect=no_action_committed safety=safe_to_replan", stdout.getvalue())
                self.assertIn("followup: requeue_event status=already_pending command=mew run --once", stdout.getvalue())
                self.assertIn("next: Re-run event #1; no action was recorded as committed.", stdout.getvalue())
                self.assertEqual(repaired["runtime_effects"][0]["status"], "interrupted")
                self.assertEqual(repaired["runtime_effects"][0]["recovery_decision"]["action"], "rerun_event")
                self.assertEqual(repaired["runtime_effects"][0]["recovery_followup"]["action"], "requeue_event")
                self.assertEqual(repaired["runtime_effects"][0]["recovery_followup"]["status"], "already_pending")
                self.assertEqual(
                    repaired["runtime_effects"][0]["recovery_hint"],
                    "Re-run event #1; no action was recorded as committed.",
                )
                self.assertTrue(repaired["runtime_effects"][0]["finished_at"])
            finally:
                os.chdir(old_cwd)

    def test_repair_requeues_processed_precommit_runtime_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "user_message", "cli", {"text": "hello"})
                event["processed_at"] = "then"
                add_runtime_effect(state, event, "user_input", "planned", "then")
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair", "--json"])
                data = json.loads(stdout.getvalue())
                repaired = load_state()
                effect = repaired["runtime_effects"][0]
                event = repaired["inbox"][0]

                self.assertEqual(code, 0)
                self.assertTrue(data["ok"])
                self.assertIsNone(event["processed_at"])
                self.assertEqual(event["requeued_from_effect_id"], 1)
                self.assertEqual(effect["recovery_followup"]["action"], "requeue_event")
                self.assertEqual(effect["recovery_followup"]["status"], "requeued")
                self.assertEqual(data["repairs"][0]["recovery_followup"]["command"], "mew run --once")
            finally:
                os.chdir(old_cwd)

    def test_doctor_previews_incomplete_runtime_effect_recovery(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect["action_types"] = ["write_file"]
                effect["write_run_ids"] = [7]
                effect["runtime_write_intents"] = [{"path": "missing.md"}]
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["doctor", "--json"])
                data = json.loads(stdout.getvalue())

                self.assertEqual(code, 1)
                self.assertFalse(data["ok"])
                item = data["runtime_effects"]["incomplete_items"][0]
                self.assertEqual(item["recovery_decision"]["action"], "review_writes")
                self.assertEqual(item["recovery_decision"]["effect_classification"], "write_may_have_started")
                self.assertEqual(item["recovery_followup"]["action"], "ask_user_review")
                self.assertEqual(item["recovery_followup"]["command"], "mew writes")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["doctor"])
                self.assertEqual(code, 1)
                self.assertIn(
                    "runtime_effect_recovery: #1 status=committing "
                    "action=review_writes effect=write_may_have_started safety=needs_user_review",
                    stdout.getvalue(),
                )
                self.assertIn(
                    "runtime_effect_followup: #1 action=ask_user_review "
                    "status=needs_user_review command=mew writes",
                    stdout.getvalue(),
                )
            finally:
                os.chdir(old_cwd)

    def test_repair_classifies_committing_runtime_write_effect(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect["action_types"] = ["write_file"]
                effect["write_run_ids"] = [7]
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair", "--json"])
                data = json.loads(stdout.getvalue())
                repaired = load_state()
                decision = repaired["runtime_effects"][0]["recovery_decision"]

                self.assertEqual(code, 0)
                self.assertTrue(data["ok"])
                self.assertEqual(data["repairs"][0]["recovery_decision"]["action"], "review_writes")
                self.assertEqual(data["repairs"][0]["recovery_followup"]["action"], "ask_user_review")
                self.assertEqual(data["repairs"][0]["recovery_followup"]["command"], "mew writes")
                self.assertEqual(data["repairs"][0]["recovery_followup"]["question_id"], 1)
                self.assertTrue(data["repairs"][0]["recovery_followup"]["question_created"])
                self.assertEqual(decision["effect_classification"], "write_may_have_started")
                self.assertEqual(decision["safety"], "needs_user_review")
                self.assertEqual(decision["write_run_ids"], [7])
                self.assertEqual(repaired["runtime_effects"][0]["recovery_followup"]["status"], "needs_user_review")
                self.assertEqual(len(repaired["questions"]), 1)
                self.assertEqual(repaired["questions"][0]["source"], "runtime")
                self.assertEqual(repaired["questions"][0]["event_id"], 1)
                self.assertIn(
                    "Runtime effect #1 for event #1 stopped while committing write_file",
                    repaired["questions"][0]["text"],
                )
                self.assertIn("Inspect with `mew writes`", repaired["questions"][0]["text"])
                self.assertIn("write_may_have_started", repaired["runtime_effects"][0]["recovery_hint"])
            finally:
                os.chdir(old_cwd)

    def test_repair_routes_committing_runtime_verification_effect_to_verification_review(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect["action_types"] = ["run_verification"]
                effect["verification_run_ids"] = [4]
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["repair", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                repaired = load_state()
                followup = data["repairs"][0]["recovery_followup"]

                self.assertEqual(data["repairs"][0]["recovery_decision"]["action"], "review_verification")
                self.assertEqual(followup["action"], "ask_user_review")
                self.assertIn("verification --details --limit 5", followup["command"])
                self.assertEqual(followup["question_id"], 1)
                self.assertIn("verification --details --limit 5", repaired["questions"][0]["text"])
            finally:
                os.chdir(old_cwd)

    def test_repair_requeues_runtime_write_intent_when_target_not_started(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect
                from mew.write_tools import build_write_intent

                Path("notes.md").write_text("old\n", encoding="utf-8")
                intent = build_write_intent(
                    "edit_file",
                    {
                        "path": "notes.md",
                        "old": "old\n",
                        "new": "new\n",
                        "apply": True,
                        "allowed_write_roots": ["."],
                        "verify_command": "python -m pytest",
                    },
                )
                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                event["processed_at"] = "then"
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect["action_types"] = ["edit_file"]
                effect["runtime_write_intents"] = [intent]
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["repair", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                repaired = load_state()
                decision = data["repairs"][0]["recovery_decision"]
                followup = data["repairs"][0]["recovery_followup"]

                self.assertEqual(decision["action"], "rerun_event")
                self.assertEqual(decision["effect_classification"], "runtime_write_not_started")
                self.assertEqual(decision["safety"], "safe_to_replan")
                self.assertEqual(decision["runtime_write_world_states"][0]["state"], "not_started")
                self.assertEqual(followup["action"], "requeue_event")
                self.assertEqual(followup["status"], "requeued")
                self.assertIsNone(repaired["inbox"][0]["processed_at"])
                self.assertEqual(repaired["questions"], [])
            finally:
                os.chdir(old_cwd)

    def test_repair_reviews_runtime_write_intent_when_target_changed(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect
                from mew.write_tools import build_write_intent

                Path("notes.md").write_text("old\n", encoding="utf-8")
                intent = build_write_intent(
                    "edit_file",
                    {
                        "path": "notes.md",
                        "old": "old\n",
                        "new": "new\n",
                        "apply": True,
                        "allowed_write_roots": ["."],
                        "verify_command": "python -m pytest",
                    },
                )
                Path("notes.md").write_text("new\n", encoding="utf-8")
                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                event["processed_at"] = "then"
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect["action_types"] = ["edit_file"]
                effect["runtime_write_intents"] = [intent]
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["repair", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                repaired = load_state()
                decision = data["repairs"][0]["recovery_decision"]
                followup = data["repairs"][0]["recovery_followup"]

                self.assertEqual(decision["action"], "review_writes")
                self.assertEqual(decision["effect_classification"], "runtime_write_completed_externally")
                self.assertEqual(decision["runtime_write_world_states"][0]["state"], "completed_externally")
                self.assertEqual(followup["action"], "ask_user_review")
                self.assertIn("runtime-effects --limit 5", followup["command"])
                self.assertEqual(followup["question_id"], 1)
                self.assertIn("Write states: completed_externally", repaired["questions"][0]["text"])
                self.assertIn("notes.md", repaired["questions"][0]["text"])
            finally:
                os.chdir(old_cwd)

    def test_repair_marks_running_work_items_interrupted(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                state["tasks"].append(
                    {
                        "id": 1,
                        "title": "Repair work session",
                        "status": "todo",
                        "priority": "normal",
                        "kind": "coding",
                        "plans": [],
                    }
                )
                state["work_sessions"].append(
                    {
                        "id": 1,
                        "task_id": 1,
                        "status": "active",
                        "title": "Repair work session",
                        "goal": "Recover stale work state.",
                        "created_at": "then",
                        "updated_at": "then",
                        "last_tool_call_id": 1,
                        "last_model_turn_id": 1,
                        "tool_calls": [
                            {
                                "id": 1,
                                "session_id": 1,
                                "task_id": 1,
                                "tool": "read_file",
                                "status": "running",
                                "parameters": {"path": "README.md"},
                                "result": None,
                                "summary": "",
                                "error": "",
                                "started_at": "then",
                                "finished_at": None,
                            }
                        ],
                        "model_turns": [
                            {
                                "id": 1,
                                "session_id": 1,
                                "task_id": 1,
                                "status": "running",
                                "decision_plan": {},
                                "action_plan": {},
                                "action": {"type": "read_file", "path": "README.md"},
                                "tool_call_id": 1,
                                "summary": "",
                                "error": "",
                                "started_at": "then",
                                "finished_at": None,
                            }
                        ],
                    }
                )
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["repair"])
                repaired = load_state()
                session = repaired["work_sessions"][0]

                self.assertEqual(code, 0)
                self.assertIn("interrupted_work_tool_call session=#1 tool_call=#1 running->interrupted", stdout.getvalue())
                self.assertIn("interrupted_work_model_turn session=#1 model_turn=#1 running->interrupted", stdout.getvalue())
                self.assertEqual(session["tool_calls"][0]["status"], "interrupted")
                self.assertEqual(session["model_turns"][0]["status"], "interrupted")
                self.assertTrue(session["tool_calls"][0]["finished_at"])
                self.assertIn("verify world state", session["tool_calls"][0]["recovery_hint"])
                with redirect_stdout(StringIO()) as resume_stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume = json.loads(resume_stdout.getvalue())["resume"]
                self.assertEqual(resume["phase"], "interrupted")
                self.assertIn("verify the world", resume["next_action"])
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
                effect["outcome"] = "hello from mew"
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
                self.assertIn("outcome=hello from mew", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["runtime-effects", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["runtime_effects"][0]["status"], "applied")
            finally:
                os.chdir(old_cwd)

    def test_runtime_effects_command_surfaces_recovery_decision_and_followup(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect

                state = default_state()
                event = add_event(state, "passive_tick", "runtime", {})
                effect = add_runtime_effect(state, event, "passive_tick", "committing", "then")
                effect.update(
                    {
                        "status": "interrupted",
                        "finished_at": "done",
                        "action_types": ["write_file"],
                        "recovery_decision": {
                            "action": "review_writes",
                            "effect_classification": "write_may_have_started",
                            "safety": "needs_user_review",
                            "runtime_write_world_states": [
                                {
                                    "state": "completed_externally",
                                    "path": "notes.md",
                                }
                            ],
                        },
                        "recovery_followup": {
                            "action": "ask_user_review",
                            "status": "needs_user_review",
                            "command": "mew writes",
                            "question_id": 3,
                        },
                    }
                )
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["runtime-effects"]), 0)
                output = stdout.getvalue()
                self.assertIn("recovery=review_writes effect=write_may_have_started safety=needs_user_review", output)
                self.assertIn("write_world=completed_externally:notes.md", output)
                self.assertIn("followup=ask_user_review status=needs_user_review command=mew writes question=#3", output)
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
