import json
import os
import signal
import subprocess
import sys
import threading
import time
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import mew.commands as commands_module
from mew.cli import main
from mew.errors import MewError


class CommandTests(unittest.TestCase):
    def test_step_focus_is_injected_into_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                report = {"steps": [], "stop_reason": "max_steps", "dry_run": True, "max_steps": 1}
                with patch("mew.commands.run_step_loop", return_value=report) as run_step:
                    with redirect_stdout(StringIO()):
                        code = main(["step", "--dry-run", "--focus", "Review current mew changes"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        guidance = run_step.call_args.kwargs["guidance"]
        self.assertIn("Immediate step focus:", guidance)
        self.assertIn("Review current mew changes", guidance)
        self.assertIn("Do not stop solely because an unrelated older question is waiting.", guidance)

    def test_step_allow_read_injects_evidence_gathering_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                report = {"steps": [], "stop_reason": "max_steps", "dry_run": True, "max_steps": 1}
                with patch("mew.commands.run_step_loop", return_value=report) as run_step:
                    with redirect_stdout(StringIO()):
                        code = main(["step", "--dry-run", "--allow-read", ".", "--focus", "Plan implementation"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        guidance = run_step.call_args.kwargs["guidance"]
        self.assertIn("Manual step read permission:", guidance)
        self.assertIn("prefer one small targeted inspect_dir, read_file, or search_text", guidance)

    def test_step_allow_write_enables_gated_write_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                report = {"steps": [], "stop_reason": "max_steps", "dry_run": True, "max_steps": 1}
                with patch("mew.commands.run_step_loop", return_value=report) as run_step:
                    with redirect_stdout(StringIO()):
                        code = main(
                            [
                                "step",
                                "--dry-run",
                                "--allow-write",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                f"{sys.executable} -c \"print('ok')\"",
                            ]
                        )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        guidance = run_step.call_args.kwargs["guidance"]
        self.assertIn("Manual step write permission:", guidance)
        self.assertIn("Omitting dry_run is treated as dry_run=true.", guidance)
        self.assertTrue(run_step.call_args.kwargs["allow_write"])
        self.assertEqual(run_step.call_args.kwargs["allowed_write_roots"], ["."])
        self.assertTrue(run_step.call_args.kwargs["allow_verify"])

    def test_step_help_describes_model_flags(self):
        with redirect_stdout(StringIO()) as stdout:
            with self.assertRaises(SystemExit) as raised:
                main(["step", "--help"])

        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("resident model override", output)
        self.assertIn("resident model API base URL override", output)

    def test_interval_flags_must_be_positive(self):
        cases = (
            (["run", "--interval", "0"], "--interval must be positive"),
            (["run", "--interval-minutes", "-1"], "--interval-minutes must be positive"),
            (["run", "--poll-interval", "0"], "--poll-interval must be positive"),
            (["dogfood", "--poll-interval", "-0.1"], "--poll-interval must be positive"),
        )
        for argv, message in cases:
            with self.subTest(argv=argv):
                with redirect_stderr(StringIO()) as stderr:
                    with self.assertRaises(SystemExit) as raised:
                        main(argv)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn(message, stderr.getvalue())

    def test_doctor_missing_optional_auth_still_succeeds(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.shutil.which", return_value="/usr/bin/tool"):
                    with patch("mew.commands.load_codex_oauth", side_effect=MewError("auth missing")):
                        with redirect_stdout(StringIO()) as stdout:
                            code = main(["doctor"])
                self.assertEqual(code, 0)
                self.assertIn("codex_auth: missing", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_doctor_can_require_auth(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.shutil.which", return_value="/usr/bin/tool"):
                    with patch("mew.commands.load_codex_oauth", side_effect=MewError("auth missing")):
                        with redirect_stdout(StringIO()) as stdout:
                            code = main(["doctor", "--require-auth"])
                self.assertEqual(code, 1)
                self.assertIn("codex_auth: error", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_doctor_flags_stale_runtime_incomplete_cycle(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["runtime_status"]["state"] = "running"
                    state["runtime_status"]["pid"] = 999
                    state["runtime_status"]["current_phase"] = "planning"
                    state["runtime_status"]["current_event_id"] = 1
                    state["runtime_status"]["current_reason"] = "passive_tick"
                    state["runtime_status"]["cycle_started_at"] = "then"
                    save_state(state)

                with (
                    patch("mew.commands.shutil.which", return_value="/usr/bin/tool"),
                    patch("mew.commands.load_codex_oauth", return_value={"path": "auth.json"}),
                    patch("mew.commands.read_lock", return_value={"pid": 999}),
                    patch("mew.commands.pid_alive", return_value=False),
                ):
                    with redirect_stdout(StringIO()) as stdout:
                        code = main(["doctor"])

                self.assertEqual(code, 1)
                output = stdout.getvalue()
                self.assertIn("runtime_lock: stale pid=999", output)
                self.assertIn("phase=planning", output)
                self.assertIn("incomplete_cycle=True", output)
            finally:
                os.chdir(old_cwd)

    def test_doctor_flags_incomplete_runtime_effect_without_active_lock(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_runtime_effect, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    event = add_event(state, "passive_tick", "runtime", {})
                    add_runtime_effect(state, event, "passive_tick", "planning", "now")
                    save_state(state)

                with (
                    patch("mew.commands.shutil.which", return_value="/usr/bin/tool"),
                    patch("mew.commands.load_codex_oauth", return_value={"path": "auth.json"}),
                    patch("mew.commands.read_lock", return_value=None),
                ):
                    with redirect_stdout(StringIO()) as stdout:
                        code = main(["doctor"])

                self.assertEqual(code, 1)
                output = stdout.getvalue()
                self.assertIn("runtime_effects: total=1 incomplete=1", output)
                self.assertIn("latest=#1 status=planning", output)
            finally:
                os.chdir(old_cwd)

    def test_task_without_subcommand_lists_tasks(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task"]), 0)
            finally:
                os.chdir(old_cwd)

        self.assertIn("No tasks.", stdout.getvalue())

    def test_task_add_ready_shortcut(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "add", "Implement thing", "--kind", "coding", "--ready"]), 0)
                self.assertIn("#1 [ready/normal/coding] Implement thing", stdout.getvalue())

                state = load_state()
                self.assertEqual(state["tasks"][0]["status"], "ready")
            finally:
                os.chdir(old_cwd)

    def test_task_done_resolves_related_open_questions(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, save_state, state_lock

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Finish docs"]), 0)
                with state_lock():
                    state = load_state()
                    add_question(state, "Should I mark task #1 done?", related_task_id=1)
                    state["agent_status"]["mode"] = "waiting_for_user"
                    state["agent_status"]["current_focus"] = "task #1 completion confirmation"
                    state["agent_status"]["active_task_id"] = 1
                    state["agent_status"]["pending_question"] = "Should I mark task #1 done?"
                    state["user_status"]["mode"] = "needs_user"
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "done", "1"]), 0)

                state = load_state()
                self.assertEqual(state["tasks"][0]["status"], "done")
                self.assertEqual(state["questions"][0]["status"], "answered")
                self.assertIsNotNone(state["outbox"][0]["answered_at"])
                self.assertEqual(state["attention"]["items"][0]["status"], "resolved")
                self.assertEqual(state["agent_status"]["mode"], "idle")
                self.assertIsNone(state["agent_status"]["active_task_id"])
                self.assertIsNone(state["agent_status"]["pending_question"])
                self.assertEqual(state["user_status"]["mode"], "idle")
            finally:
                os.chdir(old_cwd)

    def test_task_done_summary_records_user_reported_verification(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Finish docs"]), 0)
                with state_lock():
                    state = load_state()
                    state["memory"]["shallow"]["current_context"] = "1 open task(s) (ready: 1)"
                    state["agent_status"]["mode"] = "reviewing_tasks"
                    state["agent_status"]["active_task_id"] = 1
                    add_outbox_message(state, "info", "Next: plan task #1 with `mew task plan 1`")
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "task",
                                "done",
                                "1",
                                "--summary",
                                "Ran python -m pytest -q; result: 2 passed.",
                            ]
                        ),
                        0,
                    )

                state = load_state()
                self.assertEqual(state["tasks"][0]["status"], "done")
                self.assertIn("2 passed", state["tasks"][0]["notes"])
                self.assertIn("Task #1 completed", state["memory"]["shallow"]["current_context"])
                self.assertEqual(state["agent_status"]["mode"], "idle")
                self.assertIn("Task #1 completed", state["agent_status"]["last_thought"])
                self.assertIsNotNone(state["outbox"][0]["read_at"])
                self.assertEqual(len(state["verification_runs"]), 1)
                self.assertEqual(state["verification_runs"][0]["command"], "user-reported")
                self.assertEqual(state["verification_runs"][0]["exit_code"], 0)
            finally:
                os.chdir(old_cwd)

    def test_ack_can_mark_multiple_and_all(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "one")
                    add_outbox_message(state, "info", "two")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["ack", "1", "2"]), 0)
                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "three")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["ack", "--all"]), 0)

                state = load_state()
                self.assertTrue(all(message.get("read_at") for message in state["outbox"]))
            finally:
                os.chdir(old_cwd)

    def test_ack_routine_marks_only_info_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    user_event = add_event(state, "user_message", "test", {"text": "status?"})
                    external_event = add_event(state, "file_change", "watch", {"path": "README.md"})
                    add_outbox_message(state, "info", "Agent run #1 completed.", agent_run_id=1)
                    add_outbox_message(state, "info", "User-visible status.", event_id=user_event["id"])
                    add_outbox_message(state, "info", "External event handled.", event_id=external_event["id"])
                    add_outbox_message(state, "warning", "check this")
                    add_outbox_message(state, "assistant", "visible reply")
                    add_outbox_message(state, "question", "answer this", requires_reply=True)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["ack", "--routine"]), 0)

                self.assertIn("acknowledged 1 routine message(s)", stdout.getvalue())
                state = load_state()
                by_text = {message["text"]: message for message in state["outbox"]}
                self.assertIsNotNone(by_text["Agent run #1 completed."]["read_at"])
                self.assertIsNone(by_text["User-visible status."]["read_at"])
                self.assertIsNone(by_text["External event handled."]["read_at"])
                self.assertIsNone(by_text["check this"]["read_at"])
                self.assertIsNone(by_text["visible reply"]["read_at"])
                self.assertIsNone(by_text["answer this"]["read_at"])
            finally:
                os.chdir(old_cwd)

    def test_ack_routine_marks_historical_task_status_info(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(
                        state,
                        "info",
                        "2 open task(s) (ready: 1, todo: 1). Next candidate: #7 Investigate docs.",
                    )
                    add_outbox_message(state, "info", "No open tasks.")
                    add_outbox_message(state, "assistant", "2 open task(s) should stay visible.")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["ack", "--routine"]), 0)

                self.assertIn("acknowledged 2 routine message(s)", stdout.getvalue())
                state = load_state()
                by_text = {message["text"]: message for message in state["outbox"]}
                self.assertIsNotNone(
                    by_text["2 open task(s) (ready: 1, todo: 1). Next candidate: #7 Investigate docs."]["read_at"]
                )
                self.assertIsNotNone(by_text["No open tasks."]["read_at"])
                self.assertIsNone(by_text["2 open task(s) should stay visible."]["read_at"])
            finally:
                os.chdir(old_cwd)

    def test_ack_routine_dry_run_verbose_does_not_mark_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "No open tasks.")
                    add_outbox_message(state, "warning", "Needs attention.")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["ack", "--routine", "--dry-run", "--verbose"]), 0)

                output = stdout.getvalue()
                self.assertIn("would acknowledge 1 routine message(s)", output)
                self.assertIn("#1 [info] No open tasks.", output)
                state = load_state()
                self.assertTrue(all(message.get("read_at") is None for message in state["outbox"]))
            finally:
                os.chdir(old_cwd)

    def test_ack_all_dry_run_does_not_mark_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "one")
                    add_outbox_message(state, "info", "two")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["ack", "--all", "--dry-run"]), 0)

                self.assertIn("would acknowledge 2 message(s)", stdout.getvalue())
                state = load_state()
                self.assertTrue(all(message.get("read_at") is None for message in state["outbox"]))
            finally:
                os.chdir(old_cwd)

    def test_repair_refreshes_stale_research_task_command_question(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 20,
                            "title": "補助金について調べる",
                            "description": "利用可能な補助金を調査する。",
                            "kind": "",
                            "status": "ready",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": "",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    add_question(
                        state,
                        "Task #20 is ready but has no command. What should I execute for it?",
                        related_task_id=20,
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["repair"]), 0)

                self.assertIn("repairs: 1", stdout.getvalue())
                state = load_state()
                question = state["questions"][0]
                message = state["outbox"][0]
                attention = state["attention"]["items"][0]
                self.assertIn("ready research work", question["text"])
                self.assertIn("research criteria", question["text"])
                self.assertEqual(message["text"], question["text"])
                self.assertEqual(attention["reason"], question["text"])
            finally:
                os.chdir(old_cwd)

    def test_outbox_limit_shows_recent_matching_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "one")
                    add_outbox_message(state, "info", "two")
                    add_outbox_message(state, "info", "three")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["outbox", "--limit", "2"]), 0)

                output = stdout.getvalue()
                self.assertIn("showing last 2 of 3 message(s)", output)
                self.assertNotIn("one", output)
                self.assertIn("two", output)
                self.assertIn("three", output)
            finally:
                os.chdir(old_cwd)

    def test_outbox_limit_must_be_positive(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["outbox", "--limit", "0"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 1)
        self.assertIn("--limit must be positive", stderr.getvalue())

    def test_status_reports_routine_unread_cleanup_hint(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "Agent run #1 completed.", agent_run_id=1)
                    add_outbox_message(state, "warning", "Needs attention.")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["status"]), 0)
                output = stdout.getvalue()
                self.assertIn("routine_unread_info: 1", output)
                self.assertIn("routine_cleanup: mew ack --routine", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["status", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["counts"]["routine_unread_info"], 1)
            finally:
                os.chdir(old_cwd)

    def test_wait_outbox_skips_quiet_read_event_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import wait_for_event_messages
                from mew.state import add_event, add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    event = add_event(state, "startup", "runtime")
                    add_outbox_message(state, "info", "Routine startup progress.", event_id=event["id"])
                    event["processed_at"] = "done"
                    save_state(state)

                result = wait_for_event_messages(event["id"], timeout=0)

                self.assertEqual(result["status"], "processed_without_response")
                self.assertEqual(result["messages"], [])
            finally:
                os.chdir(old_cwd)

    def test_live_outbox_stream_skips_quiet_read_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import emit_new_outbox
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    quiet = add_outbox_message(state, "info", "routine", quiet=True)
                    warning = add_outbox_message(state, "warning", "check this")
                    save_state(state)

                seen = set()
                with redirect_stdout(StringIO()) as stdout:
                    count = emit_new_outbox(seen, mark_read=False)

                self.assertEqual(count, 1)
                self.assertNotIn("routine", stdout.getvalue())
                self.assertIn("check this", stdout.getvalue())
                self.assertIn(str(quiet["id"]), seen)
                self.assertIn(str(warning["id"]), seen)
            finally:
                os.chdir(old_cwd)

    def test_session_jsonl_handles_status_outbox_ack_and_message(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "hello from mew")
                    add_question(state, "What should happen next?", related_task_id=1)
                    save_state(state)

                stdin = StringIO(
                    '{"id":"s","type":"status"}\n'
                    '{"id":"f","type":"focus"}\n'
                    '{"id":"d","type":"daily"}\n'
                    '{"id":"q","type":"questions"}\n'
                    '{"id":"t","type":"attention"}\n'
                    '{"id":"o","type":"outbox"}\n'
                    '{"id":"a","type":"ack","message_ids":[1]}\n'
                    '{"id":"m","type":"message","text":"hello session"}\n'
                    '{"id":"x","type":"stop"}\n'
                )
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout:
                    code = main(["session"])

                self.assertEqual(code, 0)
                responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
                self.assertEqual(responses[0]["type"], "ready")
                self.assertEqual(responses[0]["protocol"], "mew.session.v1")
                self.assertEqual(responses[1]["type"], "status")
                self.assertEqual(responses[1]["counts"]["unread_outbox"], 2)
                self.assertEqual(responses[2]["type"], "focus")
                self.assertEqual(responses[2]["focus"]["open_questions"][0]["text"], "What should happen next?")
                self.assertEqual(responses[3]["type"], "daily")
                self.assertEqual(responses[3]["daily"]["open_questions"][0]["text"], "What should happen next?")
                self.assertEqual(responses[4]["type"], "questions")
                self.assertEqual(responses[4]["questions"][0]["text"], "What should happen next?")
                self.assertEqual(responses[5]["type"], "attention")
                self.assertEqual(responses[5]["attention"][0]["title"], "Question #1 needs a reply")
                self.assertEqual(responses[6]["type"], "outbox")
                self.assertEqual(responses[6]["messages"][0]["text"], "hello from mew")
                self.assertEqual(responses[7]["type"], "acknowledged")
                self.assertEqual(responses[7]["count"], 1)
                self.assertEqual(responses[8]["type"], "event_queued")
                self.assertEqual(responses[8]["event"]["payload"]["text"], "hello session")
                self.assertEqual(responses[9]["type"], "bye")

                state = load_state()
                self.assertEqual(state["inbox"][0]["payload"]["text"], "hello session")
                self.assertIsNotNone(state["outbox"][0]["read_at"])
            finally:
                os.chdir(old_cwd)

    def test_session_jsonl_reports_errors_and_keeps_running(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                stdin = StringIO(
                    "{bad json}\n"
                    '{"id":"u","type":"unknown"}\n'
                    '{"id":"s","type":"status"}\n'
                    '{"id":"x","type":"stop"}\n'
                )
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout:
                    code = main(["session"])

                self.assertEqual(code, 0)
                responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
                self.assertEqual(responses[1]["type"], "error")
                self.assertIn("invalid json", responses[1]["error"])
                self.assertEqual(responses[2]["type"], "error")
                self.assertEqual(responses[2]["id"], "u")
                self.assertEqual(responses[3]["type"], "status")
                self.assertEqual(responses[3]["id"], "s")
                self.assertEqual(responses[4]["type"], "bye")
            finally:
                os.chdir(old_cwd)

    def test_session_wait_outbox_returns_event_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    event = add_event(state, "user_message", "test", {"text": "hello"})
                    add_outbox_message(state, "assistant", "event response", event_id=event["id"])
                    save_state(state)

                stdin = StringIO(
                    '{"id":"w","type":"wait_outbox","event_id":1,"timeout":0,"mark_read":true}\n'
                    '{"id":"x","type":"stop"}\n'
                )
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout:
                    code = main(["session"])

                self.assertEqual(code, 0)
                responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
                self.assertEqual(responses[1]["type"], "event_result")
                self.assertEqual(responses[1]["status"], "messages")
                self.assertEqual(responses[1]["messages"][0]["text"], "event response")
                state = load_state()
                self.assertIsNotNone(state["outbox"][0]["read_at"])
            finally:
                os.chdir(old_cwd)

    def test_session_reply_rejects_already_answered_question(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, mark_question_answered, save_state, state_lock

                with state_lock():
                    state = load_state()
                    question, _created = add_question(state, "answer me")
                    mark_question_answered(state, question, "old answer")
                    save_state(state)

                stdin = StringIO(
                    '{"id":"r","type":"reply","question_id":1,"text":"new answer"}\n'
                    '{"id":"x","type":"stop"}\n'
                )
                with patch("sys.stdin", stdin), redirect_stdout(StringIO()) as stdout:
                    code = main(["session"])

                self.assertEqual(code, 0)
                responses = [json.loads(line) for line in stdout.getvalue().splitlines()]
                self.assertEqual(responses[1]["type"], "error")
                self.assertEqual(responses[1]["id"], "r")
                self.assertIn("already answered", responses[1]["error"])

                state = load_state()
                self.assertEqual(state["inbox"], [])
                self.assertEqual(len(state["replies"]), 1)
            finally:
                os.chdir(old_cwd)

    def test_questions_can_defer_reopen_and_reply(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_question(state, "Can this wait?", related_task_id=1)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["questions", "--defer", "1", "--reason", "not now"]), 0)
                self.assertIn("deferred 1 question", stdout.getvalue())
                state = load_state()
                self.assertEqual(state["questions"][0]["status"], "deferred")
                self.assertEqual(state["questions"][0]["defer_reason"], "not now")
                self.assertEqual(state["attention"]["items"][0]["status"], "resolved")
                self.assertIsNotNone(state["outbox"][0]["read_at"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["questions"]), 0)
                self.assertIn("No questions.", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["questions", "--reopen", "1"]), 0)
                self.assertIn("reopened 1 question", stdout.getvalue())
                state = load_state()
                self.assertEqual(state["questions"][0]["status"], "open")
                self.assertIsNone(state["questions"][0].get("acknowledged_at"))
                self.assertIsNone(state["outbox"][0].get("read_at"))

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["outbox"]), 0)
                self.assertIn("#1 [question/unread] Can this wait?", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["reply", "1", "yes"]), 0)
                self.assertIn("answered question #1", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_core_queues_can_print_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_question(state, "What should happen next?", related_task_id=1)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["questions", "--json"]), 0)
                questions_data = json.loads(stdout.getvalue())
                self.assertEqual(questions_data["count"], 1)
                self.assertEqual(questions_data["questions"][0]["text"], "What should happen next?")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["outbox", "--json"]), 0)
                outbox_data = json.loads(stdout.getvalue())
                self.assertEqual(outbox_data["count"], 1)
                self.assertEqual(outbox_data["messages"][0]["type"], "question")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["attention", "--json"]), 0)
                attention_data = json.loads(stdout.getvalue())
                self.assertEqual(attention_data["count"], 1)
                self.assertEqual(attention_data["attention"][0]["kind"], "question")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["questions", "--defer", "1", "--reason", "later", "--json"]), 0)
                defer_data = json.loads(stdout.getvalue())
                self.assertEqual(defer_data["action"], "deferred")
                self.assertEqual(defer_data["questions"][0]["status"], "deferred")
            finally:
                os.chdir(old_cwd)

    def test_task_list_can_filter_by_kind(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement API client", "--kind", "coding"]), 0)
                    self.assertEqual(main(["task", "add", "Pay invoice", "--kind", "admin"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "list", "--kind", "coding"]), 0)
                output = stdout.getvalue()
                self.assertIn("Implement API client", output)
                self.assertNotIn("Pay invoice", output)
            finally:
                os.chdir(old_cwd)

    def test_task_classify_can_report_and_apply_mismatches(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "補助金について調べる", "--kind", "coding"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "classify", "--mismatches"]), 0)
                output = stdout.getvalue()
                self.assertIn("stored=coding inferred=research mismatch", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "classify", "1", "--apply"]), 0)
                self.assertIn("changed 1 task", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "show", "1"]), 0)
                output = stdout.getvalue()
                self.assertIn("kind: research", output)
                self.assertIn("kind_override: research", output)
            finally:
                os.chdir(old_cwd)

    def test_workbench_summarizes_task_resume_surface(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.programmer import create_task_plan
                from mew.state import add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Implement workbench",
                        "kind": "coding",
                        "description": "Show the coding task resume state.",
                        "status": "ready",
                        "priority": "normal",
                        "notes": "",
                        "command": "",
                        "cwd": ".",
                        "auto_execute": False,
                        "agent_backend": "",
                        "agent_model": "",
                        "agent_prompt": "",
                        "agent_run_id": None,
                        "plans": [],
                        "latest_plan_id": None,
                        "runs": [],
                        "created_at": "now",
                        "updated_at": "now",
                    }
                    state["tasks"].append(task)
                    create_task_plan(state, task)
                    state["agent_runs"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "plan_id": 1,
                            "purpose": "implementation",
                            "status": "completed",
                            "model": "codex-ultra",
                        }
                    )
                    state["verification_runs"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "command": "uv run pytest",
                            "exit_code": 0,
                        }
                    )
                    state["write_runs"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "operation": "edit_file",
                            "path": "src/mew/commands.py",
                            "changed": True,
                            "rolled_back": False,
                        }
                    )
                    add_question(state, "Need scope?", related_task_id=1)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1"]), 0)
                output = stdout.getvalue()
                self.assertIn("Work task #1: Implement workbench", output)
                self.assertIn("plan #1 task=#1", output)
                self.assertIn("#1 [completed/implementation]", output)
                self.assertIn("#1 [passed] uv run pytest", output)
                self.assertIn("#1 [edit_file] src/mew/commands.py changed=True", output)
                self.assertIn("mew reply 1", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work"]), 0)
                self.assertIn("Work task #1: Implement workbench", stdout.getvalue())

                from mew.commands import run_chat_slash_command

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(run_chat_slash_command("/work", {}), "continue")
                self.assertIn("Work task #1: Implement workbench", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_workbench_defaults_to_running_task_over_stale_question_focus(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["agent_status"]["active_task_id"] = 1
                    state["tasks"].extend(
                        [
                            {
                                "id": 1,
                                "title": "Implement later task",
                                "kind": "coding",
                                "description": "",
                                "status": "ready",
                                "priority": "normal",
                                "notes": "",
                                "command": "",
                                "cwd": ".",
                                "auto_execute": False,
                                "agent_backend": "",
                                "agent_model": "",
                                "agent_prompt": "",
                                "agent_run_id": None,
                                "plans": [],
                                "latest_plan_id": None,
                                "runs": [],
                                "created_at": "now",
                                "updated_at": "now",
                            },
                            {
                                "id": 2,
                                "title": "Implement active task",
                                "kind": "coding",
                                "description": "",
                                "status": "running",
                                "priority": "high",
                                "notes": "",
                                "command": "",
                                "cwd": ".",
                                "auto_execute": False,
                                "agent_backend": "",
                                "agent_model": "",
                                "agent_prompt": "",
                                "agent_run_id": None,
                                "plans": [],
                                "latest_plan_id": None,
                                "runs": [],
                                "created_at": "now",
                                "updated_at": "now",
                            },
                        ]
                    )
                    add_question(state, "Should I handle task #1?", related_task_id=1)
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["task"]["id"], 2)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["task"]["id"], 1)
                self.assertEqual(data["open_questions"][0]["related_task_id"], 1)
            finally:
                os.chdir(old_cwd)

    def test_next_json_and_workbench_json_include_actionable_effective_task_data(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "A high running task",
                            "description": "",
                            "status": "running",
                            "priority": "high",
                            "notes": "",
                            "command": "",
                            "cwd": ".",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["next", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["command"], "mew work 1")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["task"]["kind"], "unknown")
                self.assertEqual(data["kind"], "unknown")
            finally:
                os.chdir(old_cwd)

    def test_workbench_without_tasks_is_not_an_error(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work"]), 0)
                self.assertEqual(stdout.getvalue(), "No tasks.\n")
            finally:
                os.chdir(old_cwd)

    def test_workbench_recommends_real_dispatch_after_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "task",
                                "add",
                                "Implement dispatch prompt",
                                "--kind",
                                "coding",
                                "--ready",
                                "--auto-execute",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(main(["buddy", "--task", "1"]), 0)
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work"]), 0)
                output = stdout.getvalue()

                self.assertIn("#1 [dry_run/implementation]", output)
                self.assertIn("Next action\nmew buddy --task 1 --dispatch", output)
            finally:
                os.chdir(old_cwd)

    def test_workbench_done_task_does_not_recommend_dispatch(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "task",
                                "add",
                                "Implement dispatch prompt",
                                "--kind",
                                "coding",
                                "--ready",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(main(["buddy", "--task", "1"]), 0)
                    self.assertEqual(main(["task", "done", "1"]), 0)
                    self.assertEqual(main(["task", "add", "Other task", "--kind", "coding", "--ready"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1"]), 0)
                output = stdout.getvalue()

                self.assertIn("#1 [done/normal/coding]", output)
                self.assertIn("Next action\nwait for the next user request", output)
                self.assertNotIn("mew buddy --task 1 --dispatch", output)
            finally:
                os.chdir(old_cwd)

    def test_task_plan_refuses_non_coding_task(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Pay invoice", "--kind", "admin"]), 0)

                with redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["task", "plan", "1"]), 1)
                self.assertIn("is not a coding task", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_buddy_creates_plan_and_dry_run_dispatch(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["task", "add", "Implement buddy test", "--kind", "coding", "--ready"]),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["buddy", "--task", "1"]), 0)
                output = stdout.getvalue()
                self.assertIn("buddy task #1", output)
                self.assertIn("created plan #1", output)
                self.assertIn("dispatch with `mew buddy --task 1 --dispatch --dry-run`", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)
                output = stdout.getvalue()
                self.assertIn("created dry-run implementation run #1", output)
                self.assertIn("command: ai-cli run", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)
                output = stdout.getvalue()
                self.assertIn("reused implementation run #1 status=dry_run", output)
                self.assertIn("command: ai-cli run", output)

                from mew.state import load_state

                state = load_state()
                self.assertEqual(state["tasks"][0]["latest_plan_id"], 1)
                self.assertEqual(len(state["agent_runs"]), 1)
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
            finally:
                os.chdir(old_cwd)

    def test_buddy_reports_start_failure(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement failing start", "--kind", "coding", "--ready"]), 0)

                def fail_start(_state, run):
                    run["status"] = "failed"
                    run["stderr"] = "ai-cli unavailable"
                    run["updated_at"] = "now"
                    return run

                with patch("mew.commands.start_agent_run", side_effect=fail_start):
                    with redirect_stderr(StringIO()) as stderr:
                        self.assertEqual(main(["buddy", "--task", "1", "--dispatch"]), 1)
                self.assertIn("failed to start: ai-cli unavailable", stderr.getvalue())

                from mew.state import load_state

                state = load_state()
                self.assertEqual(state["agent_runs"][0]["status"], "failed")
            finally:
                os.chdir(old_cwd)

    def test_buddy_saves_dispatch_before_review_status_error(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement running review guard", "--kind", "coding", "--ready"]), 0)

                def start_running(_state, run):
                    run["status"] = "running"
                    run["external_pid"] = 123
                    run["updated_at"] = "now"
                    return run

                with patch("mew.commands.start_agent_run", side_effect=start_running):
                    with redirect_stderr(StringIO()) as stderr:
                        self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--review"]), 1)
                self.assertIn("use --force-review", stderr.getvalue())

                from mew.state import load_state

                state = load_state()
                self.assertEqual(state["agent_runs"][0]["status"], "running")
                self.assertEqual(state["agent_runs"][0]["external_pid"], 123)
            finally:
                os.chdir(old_cwd)

    def test_buddy_creates_dry_run_review_for_completed_implementation(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement review preview", "--kind", "coding", "--ready"]), 0)
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)

                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["agent_runs"][0]["status"] = "completed"
                    state["agent_runs"][0]["result"] = "Implemented safely."
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["buddy", "--task", "1", "--review", "--dry-run"]), 0)
                output = stdout.getvalue()
                self.assertIn("created dry-run review run #2", output)
                self.assertIn("start review for real with `mew buddy --task 1 --review`", output)

                state = load_state()
                self.assertEqual(state["agent_runs"][1]["purpose"], "review")
                self.assertEqual(state["agent_runs"][1]["status"], "dry_run")
            finally:
                os.chdir(old_cwd)

    def test_buddy_review_uses_implementation_run_plan(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement plan-specific review", "--kind", "coding", "--ready"]), 0)
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)

                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["agent_runs"][0]["status"] = "completed"
                    state["agent_runs"][0]["result"] = "Implemented plan one."
                    save_state(state)

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["buddy", "--task", "1", "--force-plan"]), 0)
                    self.assertEqual(main(["buddy", "--task", "1", "--review", "--dry-run"]), 0)

                state = load_state()
                self.assertEqual(state["tasks"][0]["latest_plan_id"], 2)
                self.assertEqual(state["agent_runs"][1]["purpose"], "review")
                self.assertEqual(state["agent_runs"][1]["plan_id"], 1)
            finally:
                os.chdir(old_cwd)

    def test_buddy_forced_review_hint_keeps_force_review(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Implement forced review hint", "--kind", "coding", "--ready"]), 0)
                    self.assertEqual(main(["buddy", "--task", "1", "--dispatch", "--dry-run"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["buddy", "--task", "1", "--review", "--dry-run", "--force-review"]), 0)
                output = stdout.getvalue()
                self.assertIn("created dry-run review run #2", output)
                self.assertIn("command: ai-cli run", output)
                self.assertIn("start review for real with `mew buddy --task 1 --review --force-review`", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_can_classify_and_run_buddy_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "補助金について調べる", "--kind", "coding"]), 0)
                    self.assertEqual(main(["task", "add", "Implement chat buddy", "--kind", "coding", "--ready"]), 0)

                stdin = StringIO(
                    "/classify 1 apply\n"
                    "/buddy 2\n"
                    "/buddy 2 dispatch dry-run\n"
                    "/exit\n"
                )
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()) as stderr,
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                self.assertEqual(stderr.getvalue(), "")
                output = stdout.getvalue()
                self.assertIn("effective=research stored=research inferred=research", output)
                self.assertIn("buddy task #2", output)
                self.assertIn("created dry-run implementation run #1", output)
            finally:
                os.chdir(old_cwd)

    def test_chat_classify_and_buddy_handle_bad_quotes(self):
        stdin = StringIO('/classify "unterminated\n/buddy "unterminated\n/exit\n')
        with (
            patch("sys.stdin", stdin),
            redirect_stdout(StringIO()) as stdout,
            redirect_stderr(StringIO()) as stderr,
        ):
            code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertGreaterEqual(stdout.getvalue().count("No closing quotation"), 2)

    def test_task_run_refuses_non_coding_task(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Pay invoice", "--kind", "admin"]), 0)

                with redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["task", "run", "1", "--dry-run"]), 1)
                self.assertIn("is not a coding task", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_attention_can_resolve_items(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_attention_item, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_attention_item(state, "test", "First", "one")
                    add_attention_item(state, "test", "Second", "two")
                    save_state(state)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["attention", "--resolve", "1"]), 0)
                    self.assertEqual(main(["attention", "--resolve-all"]), 0)

                state = load_state()
                self.assertTrue(
                    all(item.get("status") == "resolved" for item in state["attention"]["items"])
                )
            finally:
                os.chdir(old_cwd)

    def test_archive_compacts_processed_and_read_records(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    for index in range(3):
                        event = add_event(state, "user_message", "test", {"index": index})
                        event["processed_at"] = f"done-{index}"
                    add_event(state, "user_message", "test", {"index": "open"})
                    for index in range(3):
                        message = add_outbox_message(state, "info", f"read {index}")
                        message["read_at"] = f"read-{index}"
                    add_outbox_message(state, "info", "unread")
                    state["agent_runs"].extend(
                        [
                            {
                                "id": 1,
                                "task_id": 1,
                                "purpose": "implementation",
                                "status": "completed",
                            },
                            {
                                "id": 2,
                                "task_id": 1,
                                "purpose": "review",
                                "status": "completed",
                                "review_of_run_id": 1,
                                "followup_processed_at": "done",
                            },
                            {
                                "id": 3,
                                "task_id": 2,
                                "purpose": "implementation",
                                "status": "completed",
                            },
                            {
                                "id": 4,
                                "task_id": 3,
                                "purpose": "implementation",
                                "status": "running",
                            },
                            {
                                "id": 5,
                                "task_id": 4,
                                "purpose": "implementation",
                                "status": "failed",
                            },
                            {
                                "id": 6,
                                "task_id": 5,
                                "purpose": "implementation",
                                "status": "failed",
                            },
                        ]
                    )
                    for index in range(3):
                        state["verification_runs"].append({"id": index + 1, "exit_code": index})
                        state["write_runs"].append({"id": index + 1, "operation": "write_file"})
                    state["work_sessions"].extend(
                        [
                            {"id": 1, "status": "closed"},
                            {"id": 2, "status": "closed"},
                            {"id": 3, "status": "active"},
                        ]
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["archive", "--keep-recent", "1", "--apply"])

                self.assertEqual(code, 0)
                self.assertIn("archived_inbox: 2", stdout.getvalue())
                self.assertIn("archived_outbox: 2", stdout.getvalue())
                self.assertIn("archived_agent_runs: 1", stdout.getvalue())
                self.assertIn("archived_verification_runs: 2", stdout.getvalue())
                self.assertIn("archived_write_runs: 2", stdout.getvalue())
                self.assertIn("archived_work_sessions: 1", stdout.getvalue())

                state = load_state()
                self.assertEqual(len(state["inbox"]), 2)
                self.assertEqual(len(state["outbox"]), 2)
                self.assertEqual([run["id"] for run in state["agent_runs"]], [2, 3, 4, 5, 6])
                self.assertEqual([run["id"] for run in state["verification_runs"]], [3])
                self.assertEqual([run["id"] for run in state["write_runs"]], [3])
                self.assertEqual([session["id"] for session in state["work_sessions"]], [2, 3])
                archives = list((Path(".mew") / "archive").glob("state-*.json"))
                self.assertEqual(len(archives), 1)
                archived = json.loads(archives[0].read_text(encoding="utf-8"))
                effect_count = archived["counts"].pop("effects")
                self.assertEqual(
                    archived["counts"],
                    {
                        "inbox": 2,
                        "outbox": 2,
                        "agent_runs": 1,
                        "verification_runs": 2,
                        "write_runs": 2,
                        "work_sessions": 1,
                    },
                )
                self.assertGreaterEqual(effect_count, 1)
            finally:
                os.chdir(old_cwd)

    def test_archive_compacts_effect_log(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.archive import archive_state_records
                from mew.config import EFFECT_LOG_FILE
                from mew.state import default_state

                EFFECT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
                EFFECT_LOG_FILE.write_text(
                    "\n".join(
                        json.dumps({"type": "state_saved", "seq": index})
                        for index in range(5)
                    )
                    + "\n",
                    encoding="utf-8",
                )

                state = default_state()
                result = archive_state_records(
                    state,
                    keep_recent=2,
                    dry_run=False,
                    current_time="2026-04-15T00:00:00Z",
                )

                self.assertEqual(result["archived"]["effects"], 3)
                self.assertEqual(result["remaining"]["effects"], 2)
                remaining = EFFECT_LOG_FILE.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(remaining), 2)
                self.assertIn('"seq": 3', remaining[0])
                archives = list((Path(".mew") / "archive").glob("state-*.json"))
                self.assertEqual(len(archives), 1)
                archived = json.loads(archives[0].read_text(encoding="utf-8"))
                self.assertEqual(archived["counts"]["effects"], 3)
                self.assertEqual([record["seq"] for record in archived["effects"]], [0, 1, 2])
            finally:
                os.chdir(old_cwd)

    def test_archive_agent_runs_preserves_open_lifecycle(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.archive import archive_state_records
                from mew.state import default_state

                state = default_state()
                state["agent_runs"].extend(
                    [
                        {
                            "id": 1,
                            "purpose": "implementation",
                            "status": "completed",
                        },
                        {
                            "id": 2,
                            "purpose": "review",
                            "status": "completed",
                            "review_of_run_id": 1,
                            "followup_processed_at": "done",
                        },
                        {
                            "id": 3,
                            "purpose": "implementation",
                            "status": "completed",
                        },
                        {
                            "id": 4,
                            "purpose": "review",
                            "status": "running",
                            "review_of_run_id": 3,
                        },
                        {
                            "id": 5,
                            "purpose": "implementation",
                            "status": "failed",
                        },
                        {
                            "id": 6,
                            "purpose": "implementation",
                            "status": "running",
                            "parent_run_id": 5,
                        },
                        {
                            "id": 7,
                            "purpose": "implementation",
                            "status": "failed",
                        },
                        {
                            "id": 8,
                            "purpose": "implementation",
                            "status": "dry_run",
                        },
                    ]
                )

                result = archive_state_records(state, keep_recent=0, dry_run=False, current_time="2026-04-15T00:00:00Z")

                self.assertEqual(result["archived"]["agent_runs"], 4)
                self.assertEqual([run["id"] for run in state["agent_runs"]], [3, 4, 6, 7])
            finally:
                os.chdir(old_cwd)

    def test_run_auto_archive_compacts_processed_and_read_records(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    for index in range(3):
                        event = add_event(state, "user_message", "test", {"index": index})
                        event["processed_at"] = f"done-{index}"
                    for index in range(3):
                        message = add_outbox_message(state, "info", f"read {index}")
                        message["read_at"] = f"read-{index}"
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "run",
                            "--once",
                            "--poll-interval",
                            "0.01",
                            "--auto-archive",
                            "--archive-keep-recent",
                            "1",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("archived", stdout.getvalue())
                state = load_state()
                self.assertEqual(len([event for event in state["inbox"] if event.get("processed_at")]), 1)
                self.assertEqual(len([message for message in state["outbox"] if message.get("read_at")]), 1)
                self.assertEqual(len(list((Path(".mew") / "archive").glob("state-*.json"))), 1)
            finally:
                os.chdir(old_cwd)

    def test_run_autonomous_initializes_instruction_files(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(["run", "--once", "--autonomous", "--poll-interval", "0.01"]),
                        0,
                    )

                self.assertTrue((Path(".mew") / "guidance.md").exists())
                self.assertTrue((Path(".mew") / "policy.md").exists())
                self.assertTrue((Path(".mew") / "self.md").exists())
                self.assertTrue((Path(".mew") / "desires.md").exists())
            finally:
                os.chdir(old_cwd)

    def test_run_releases_state_lock_while_planning_model_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import queue_user_message
                from mew.state import load_state

                planning_started = threading.Event()
                release_planning = threading.Event()
                runtime_result = []
                errors = []

                def fake_plan_runtime_event(*args, **kwargs):
                    planning_started.set()
                    if not release_planning.wait(2):
                        errors.append("planning was not released")
                    return (
                        {
                            "summary": "startup remembered",
                            "decisions": [{"type": "remember", "summary": "startup remembered"}],
                        },
                        {
                            "summary": "startup remembered",
                            "actions": [{"type": "record_memory", "summary": "startup remembered"}],
                        },
                    )

                def run_once():
                    with (
                        patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                        patch("mew.runtime.signal.signal", return_value=None),
                    ):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            runtime_result.append(main(["run", "--once", "--poll-interval", "0.01"]))

                runtime_thread = threading.Thread(target=run_once)
                runtime_thread.start()
                self.assertTrue(planning_started.wait(2))

                queued = []
                queue_thread = threading.Thread(
                    target=lambda: queued.append(queue_user_message("hello while model is thinking")["id"])
                )
                queue_thread.start()
                queue_thread.join(0.5)
                blocked = queue_thread.is_alive()

                release_planning.set()
                queue_thread.join(2)
                runtime_thread.join(3)

                self.assertFalse(blocked, "message queue blocked while runtime was planning")
                self.assertFalse(runtime_thread.is_alive())
                self.assertEqual(runtime_result, [0])
                self.assertEqual(errors, [])

                state = load_state()
                user_events = [event for event in state["inbox"] if event.get("type") == "user_message"]
                self.assertEqual(len(user_events), 1)
                self.assertEqual(user_events[0]["payload"]["text"], "hello while model is thinking")
                self.assertIsNone(user_events[0].get("processed_at"))
            finally:
                release_planning.set()
                os.chdir(old_cwd)

    def test_run_prefers_pending_user_message_over_stale_internal_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    internal = add_event(state, "passive_tick", "test")
                    user = add_event(state, "user_message", "test", {"text": "process me first"})
                    save_state(state)

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    return (
                        {
                            "summary": event_snapshot["type"],
                            "decisions": [{"type": "remember", "summary": event_snapshot["type"]}],
                        },
                        {
                            "summary": event_snapshot["type"],
                            "actions": [{"type": "record_memory", "summary": event_snapshot["type"]}],
                        },
                    )

                with patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                state = load_state()
                by_id = {event["id"]: event for event in state["inbox"]}
                self.assertIsNone(by_id[internal["id"]].get("processed_at"))
                self.assertIsNotNone(by_id[user["id"]].get("processed_at"))
                self.assertEqual(by_id[user["id"]]["decision_plan"]["summary"], "user_message")
            finally:
                os.chdir(old_cwd)

    def test_run_does_not_apply_stale_plan_if_event_was_processed_before_commit(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    queued = add_event(state, "user_message", "test", {"text": "hello"})
                    save_state(state)

                planning_started = threading.Event()
                release_planning = threading.Event()
                runtime_result = []

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    self.assertEqual(event_snapshot["id"], queued["id"])
                    planning_started.set()
                    release_planning.wait(2)
                    return (
                        {
                            "summary": "stale plan",
                            "decisions": [{"type": "send_message", "text": "stale"}],
                        },
                        {
                            "summary": "stale plan",
                            "actions": [
                                {
                                    "type": "send_message",
                                    "message_type": "assistant",
                                    "text": "stale response",
                                }
                            ],
                        },
                    )

                def run_once():
                    with (
                        patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                        patch("mew.runtime.signal.signal", return_value=None),
                    ):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            runtime_result.append(main(["run", "--once", "--poll-interval", "0.01"]))

                runtime_thread = threading.Thread(target=run_once)
                runtime_thread.start()
                self.assertTrue(planning_started.wait(2))

                with state_lock():
                    state = load_state()
                    event = next(event for event in state["inbox"] if event["id"] == queued["id"])
                    event["processed_at"] = "external"
                    event["decision_plan"] = {"summary": "external", "decisions": []}
                    event["action_plan"] = {"summary": "external", "actions": []}
                    save_state(state)

                release_planning.set()
                runtime_thread.join(3)

                self.assertFalse(runtime_thread.is_alive())
                self.assertEqual(runtime_result, [0])

                state = load_state()
                event = next(event for event in state["inbox"] if event["id"] == queued["id"])
                self.assertEqual(event["processed_at"], "external")
                self.assertEqual(event["action_plan"]["summary"], "external")
                self.assertEqual(state["outbox"], [])
                self.assertEqual(state["thought_journal"], [])
                self.assertEqual(state["runtime_status"]["last_processed_count"], 0)
            finally:
                release_planning.set()
                os.chdir(old_cwd)

    def test_run_does_not_precompute_verification_for_stale_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    queued = add_event(state, "user_message", "test", {"text": "verify"})
                    save_state(state)

                planning_started = threading.Event()
                release_planning = threading.Event()
                runtime_result = []
                verification_calls = []

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    self.assertEqual(event_snapshot["id"], queued["id"])
                    planning_started.set()
                    release_planning.wait(2)
                    return (
                        {
                            "summary": "verify",
                            "decisions": [{"type": "run_verification", "reason": "check"}],
                        },
                        {
                            "summary": "verify",
                            "actions": [{"type": "run_verification", "reason": "check"}],
                        },
                    )

                def fake_run_command_record(*args, **kwargs):
                    verification_calls.append(args)
                    return {"exit_code": 0, "stdout": "", "stderr": ""}

                def run_once():
                    with (
                        patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                        patch("mew.runtime.run_command_record", side_effect=fake_run_command_record),
                        patch("mew.runtime.signal.signal", return_value=None),
                    ):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            runtime_result.append(
                                main(
                                    [
                                        "run",
                                        "--once",
                                        "--allow-verify",
                                        "--verify-command",
                                        "echo ok",
                                        "--poll-interval",
                                        "0.01",
                                    ]
                                )
                            )

                runtime_thread = threading.Thread(target=run_once)
                runtime_thread.start()
                self.assertTrue(planning_started.wait(2))

                with state_lock():
                    state = load_state()
                    event = next(event for event in state["inbox"] if event["id"] == queued["id"])
                    event["processed_at"] = "external"
                    event["decision_plan"] = {"summary": "external", "decisions": []}
                    event["action_plan"] = {"summary": "external", "actions": []}
                    save_state(state)

                release_planning.set()
                runtime_thread.join(3)

                self.assertFalse(runtime_thread.is_alive())
                self.assertEqual(runtime_result, [0])
                self.assertEqual(verification_calls, [])

                state = load_state()
                self.assertEqual(state["verification_runs"], [])
                self.assertEqual(state["outbox"], [])
                self.assertEqual(state["runtime_status"]["last_processed_count"], 0)
            finally:
                release_planning.set()
                os.chdir(old_cwd)

    def test_run_releases_state_lock_while_precomputing_verification(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.commands import queue_user_message
                from mew.state import load_state

                verification_started = threading.Event()
                release_verification = threading.Event()
                runtime_result = []

                def fake_plan_runtime_event(*args, **kwargs):
                    return (
                        {
                            "summary": "verify",
                            "decisions": [{"type": "run_verification", "reason": "check"}],
                        },
                        {
                            "summary": "verify",
                            "actions": [{"type": "run_verification", "reason": "check"}],
                        },
                    )

                def fake_run_command_record(command, cwd=None, timeout=300):
                    verification_started.set()
                    release_verification.wait(2)
                    return {
                        "command": command,
                        "argv": ["echo", "ok"],
                        "cwd": str(Path(".").resolve()),
                        "started_at": "start",
                        "finished_at": "finish",
                        "exit_code": 0,
                        "stdout": "ok\n",
                        "stderr": "",
                    }

                def run_once():
                    with (
                        patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                        patch("mew.runtime.run_command_record", side_effect=fake_run_command_record),
                        patch("mew.runtime.signal.signal", return_value=None),
                    ):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            runtime_result.append(
                                main(
                                    [
                                        "run",
                                        "--once",
                                        "--autonomous",
                                        "--autonomy-level",
                                        "act",
                                        "--allow-verify",
                                        "--verify-command",
                                        "echo ok",
                                        "--poll-interval",
                                        "0.01",
                                    ]
                                )
                            )

                runtime_thread = threading.Thread(target=run_once)
                runtime_thread.start()
                self.assertTrue(verification_started.wait(2))

                queued = []
                queue_thread = threading.Thread(
                    target=lambda: queued.append(queue_user_message("hello during verification")["id"])
                )
                queue_thread.start()
                queue_thread.join(0.5)
                blocked = queue_thread.is_alive()

                release_verification.set()
                queue_thread.join(2)
                runtime_thread.join(3)

                self.assertFalse(blocked, "message queue blocked while runtime verification was running")
                self.assertFalse(runtime_thread.is_alive())
                self.assertEqual(runtime_result, [0])

                state = load_state()
                self.assertEqual(len(state["verification_runs"]), 1)
                self.assertEqual(state["verification_runs"][0]["exit_code"], 0)
                processed = next(event for event in state["inbox"] if event.get("type") == "startup")
                self.assertNotIn(
                    "_precomputed_verification",
                    processed["action_plan"]["actions"][0],
                )
                user_events = [event for event in state["inbox"] if event.get("type") == "user_message"]
                self.assertEqual(user_events[0]["payload"]["text"], "hello during verification")
            finally:
                release_verification.set()
                os.chdir(old_cwd)

    def test_run_reports_precomputed_verification_error(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state

                def fake_plan_runtime_event(*args, **kwargs):
                    return (
                        {
                            "summary": "verify",
                            "decisions": [{"type": "run_verification", "reason": "check"}],
                        },
                        {
                            "summary": "verify",
                            "actions": [{"type": "run_verification", "reason": "check"}],
                        },
                    )

                def fake_run_command_record(*args, **kwargs):
                    raise ValueError("bad verification command")

                with (
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                    patch("mew.runtime.run_command_record", side_effect=fake_run_command_record),
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-verify",
                                "--verify-command",
                                "bad command",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                state = load_state()
                self.assertEqual(state["verification_runs"], [])
                self.assertIn("bad verification command", state["outbox"][-1]["text"])
                processed = next(event for event in state["inbox"] if event.get("type") == "startup")
                self.assertNotIn(
                    "_precomputed_verification_error",
                    processed["action_plan"]["actions"][0],
                )
            finally:
                os.chdir(old_cwd)

    def test_start_spawns_background_runtime_and_waits(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                process = Mock()
                process.pid = 456
                process.poll.return_value = None
                with (
                    patch("mew.commands.runtime_is_active", side_effect=[False, True]),
                    patch("mew.commands.subprocess.Popen", return_value=process) as popen,
                ):
                    with redirect_stdout(StringIO()) as stdout:
                        code = main(["start", "--", "--autonomous"])

                self.assertEqual(code, 0)
                self.assertIn("started runtime pid=456", stdout.getvalue())
                self.assertIn("runtime is active", stdout.getvalue())
                command = popen.call_args.args[0]
                self.assertEqual(command[-2:], ["run", "--autonomous"])
                env = popen.call_args.kwargs["env"]
                source_root = Path(commands_module.__file__).resolve().parents[1]
                self.assertIn(str(source_root), env["PYTHONPATH"])
                self.assertTrue((Path(".mew") / "runtime.out").exists())
            finally:
                os.chdir(old_cwd)

    def test_stop_reports_when_no_runtime_is_active(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["stop"])

                self.assertEqual(code, 0)
                self.assertIn("No active runtime.", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_stop_signals_active_runtime_and_waits(self):
        with (
            patch("mew.commands.read_lock", return_value={"pid": 123}),
            patch("mew.commands.pid_alive", side_effect=[True, False]),
            patch("mew.commands.os.kill") as kill,
        ):
            with redirect_stdout(StringIO()) as stdout:
                code = main(["stop", "--timeout", "1", "--poll-interval", "0.01"])

        self.assertEqual(code, 0)
        kill.assert_called_once_with(123, signal.SIGTERM)
        self.assertIn("runtime stopped", stdout.getvalue())

    def test_status_brief_and_next_support_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "JSON interface",
                            "description": "",
                            "status": "todo",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": ".",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    state["thought_journal"].append(
                        {
                            "id": 1,
                            "event_id": 2,
                            "event_type": "passive_tick",
                            "summary": "Checked the workspace.",
                            "actions": [{"type": "inspect_dir", "path": "."}],
                            "counts": {"actions": 1, "messages": 1},
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["status", "--json"]), 0)
                status = json.loads(stdout.getvalue())
                self.assertEqual(status["counts"]["open_tasks"], 1)
                self.assertIn("last_cycle_duration_seconds", status["runtime_status"])
                self.assertIn("last_processed_count", status["runtime_status"])
                self.assertIn("next_move", status)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["brief", "--json"]), 0)
                brief = json.loads(stdout.getvalue())
                self.assertEqual(brief["open_tasks"][0]["title"], "JSON interface")
                self.assertIn("programmer_queue", brief)
                self.assertIn("recent_activity", brief)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["activity", "--json"]), 0)
                activity = json.loads(stdout.getvalue())
                self.assertEqual(activity["recent_activity"][0]["summary"], "Checked the workspace.")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["context", "--json"]), 0)
                context = json.loads(stdout.getvalue())
                self.assertIn("context_stats", context)
                self.assertIn("section_chars", context["context_stats"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["next", "--json"]), 0)
                next_data = json.loads(stdout.getvalue())
                self.assertIn("next_move", next_data)
                self.assertEqual(next_data["command"], "mew task plan 1")
            finally:
                os.chdir(old_cwd)

    def test_activity_command_prints_text(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["thought_journal"].append(
                        {
                            "id": 1,
                            "event_id": 2,
                            "event_type": "passive_tick",
                            "summary": "Read README.",
                            "actions": [{"type": "read_file", "path": "README.md"}],
                            "counts": {"actions": 1},
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["activity"]), 0)

                self.assertIn("Read README", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_trace_command_reads_model_trace_records(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.model_trace import append_model_trace

                append_model_trace(
                    at="now",
                    phase="think",
                    event={"id": 7, "type": "passive_tick"},
                    backend="codex",
                    model="test-model",
                    status="ok",
                    prompt="trace prompt",
                    plan={"summary": "ok", "decisions": [{"type": "remember"}]},
                )
                append_model_trace(
                    at="later",
                    phase="act",
                    event={"id": 7, "type": "passive_tick"},
                    backend="codex",
                    model="test-model",
                    status="skipped",
                    reason="model backend not enabled for this event",
                    plan={"summary": "fallback", "actions": [{"type": "record_memory"}]},
                    include_prompt=False,
                )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["trace"]), 0)
                output = stdout.getvalue()
                self.assertIn("think ok event=#7/passive_tick", output)
                self.assertIn("decisions=1", output)
                self.assertIn("reason: model backend not enabled for this event", output)
                self.assertNotIn("trace prompt", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["trace", "--json", "--prompt"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["traces"][0]["prompt"], "trace prompt")
                self.assertEqual(data["traces"][1]["reason"], "model backend not enabled for this event")
            finally:
                os.chdir(old_cwd)

    def test_focus_and_daily_show_quiet_next_action_view(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Pay the electric bill",
                            "kind": "admin",
                            "description": "",
                            "status": "todo",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": "",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["focus"]), 0)
                output = stdout.getvalue()
                self.assertIn("Mew focus", output)
                self.assertIn("take one concrete admin step", output)
                self.assertIn("[admin/todo/normal] Pay the electric bill", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["daily", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["tasks"][0]["kind"], "admin")
                self.assertEqual(data["tasks"][0]["title"], "Pay the electric bill")
            finally:
                os.chdir(old_cwd)

    def test_context_command_prints_diagnostics(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["context", "--send-message", "hello"]), 0)

                output = stdout.getvalue()
                self.assertIn("Mew context", output)
                self.assertIn("approx_chars:", output)
                self.assertIn("Largest sections", output)
            finally:
                os.chdir(old_cwd)

    def test_snapshot_command_refreshes_project_snapshot(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("src").mkdir()
                Path("tests").mkdir()
                Path("README.md").write_text("# Demo\n", encoding="utf-8")
                Path("pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["snapshot", "--allow-read", "."]), 0)

                output = stdout.getvalue()
                self.assertIn("project_types: python", output)
                self.assertIn("package: name=demo", output)
            finally:
                os.chdir(old_cwd)

    def test_snapshot_command_requires_allow_read(self):
        with redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["snapshot"]), 1)

        self.assertIn("--allow-read", stderr.getvalue())

    def test_dogfood_command_uses_report_runner(self):
        report = {
            "generated_at": "now",
            "workspace": "/tmp/dog",
            "command": ["mew", "run"],
            "exit_code": 0,
            "duration_seconds": 1.0,
            "events": {"processed": 1, "total": 1, "by_type": {"startup": 1}},
            "model_phases": {"think_ok": 0, "think_error": 0, "act_ok": 0, "act_error": 0},
            "outbox": {"total": 0, "unread": 0, "by_type": {}},
            "actions": {},
            "tasks": {},
            "verification_runs": 0,
            "write_runs": 0,
            "dropped_threads": {"thought_count": 0, "latest": []},
            "recent_activity": [],
            "next_move": "ask the user what to track next",
            "log_tail": [],
        }
        with patch("mew.commands.run_dogfood", return_value=report) as runner:
            with redirect_stdout(StringIO()) as stdout:
                code = main(["dogfood", "--duration", "0", "--send-message", "hello"])

        self.assertEqual(code, 0)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0].send_message, ["hello"])
        self.assertIn("Mew dogfood report", stdout.getvalue())

    def test_dogfood_command_can_write_report_file(self):
        report = {
            "generated_at": "now",
            "workspace": "/tmp/dog",
            "command": ["mew", "run"],
            "exit_code": 0,
            "duration_seconds": 1.0,
            "events": {"processed": 1, "total": 1, "by_type": {"startup": 1}},
            "model_phases": {"think_ok": 0, "think_error": 0, "act_ok": 0, "act_error": 0},
            "outbox": {"total": 0, "unread": 0, "by_type": {}},
            "actions": {},
            "tasks": {},
            "verification_runs": 0,
            "write_runs": 0,
            "dropped_threads": {"thought_count": 0, "latest": []},
            "recent_activity": [],
            "next_move": "ask the user what to track next",
            "log_tail": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "dogfood-report.json"
            with patch("mew.commands.run_dogfood", return_value=report):
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["dogfood", "--duration", "0", "--report", str(report_path)])

            self.assertEqual(code, 0)
            self.assertIn(f"report_path: {report_path}", stdout.getvalue())
            written = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(written["workspace"], "/tmp/dog")
            self.assertEqual(written["report_path"], str(report_path))

    def test_dogfood_requires_verify_command_when_verify_enabled(self):
        with redirect_stderr(StringIO()) as stderr:
            code = main(["dogfood", "--allow-verify"])

        self.assertEqual(code, 1)
        self.assertIn("--allow-verify requires --verify-command", stderr.getvalue())

    def test_dogfood_rejects_sensitive_workspace_without_traceback(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["dogfood", "--workspace", ".mew/acm-use-test/dog"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 1)
        self.assertIn("dogfood workspace is inside a sensitive path", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_agent_without_subcommand_lists_runs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["agent"])
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        self.assertIn("No agent runs.", stdout.getvalue())

    def test_agent_sweep_passes_timeout_flags(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.sweep_agent_runs", return_value={}) as sweep:
                    with redirect_stdout(StringIO()):
                        code = main(
                            [
                                "agent",
                                "sweep",
                                "--agent-result-timeout",
                                "4",
                                "--agent-start-timeout",
                                "6",
                            ]
                        )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        _, kwargs = sweep.call_args
        self.assertEqual(kwargs["result_timeout"], 4.0)
        self.assertEqual(kwargs["start_timeout"], 6.0)

    def test_event_command_queues_external_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "event",
                            "github_webhook",
                            "--source",
                            "test",
                            "--payload",
                            '{"ref":"main"}',
                            "--text",
                            "push received",
                        ]
                    )
                from mew.state import load_state

                state = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        self.assertIn("queued github_webhook event #1", stdout.getvalue())
        self.assertEqual(state["inbox"][0]["type"], "github_webhook")
        self.assertEqual(state["inbox"][0]["source"], "test")
        self.assertEqual(state["inbox"][0]["payload"]["ref"], "main")
        self.assertEqual(state["inbox"][0]["payload"]["text"], "push received")

    def test_event_command_rejects_invalid_payload_without_traceback(self):
        with redirect_stderr(StringIO()) as stderr:
            code = main(["event", "github_webhook", "--payload", "["])

        self.assertEqual(code, 1)
        self.assertIn("invalid JSON payload", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_event_command_rejects_reserved_event_type(self):
        with redirect_stderr(StringIO()) as stderr:
            code = main(["event", "user_message", "--payload", '{"text":"hi"}'])

        self.assertEqual(code, 1)
        self.assertIn("event type is reserved: user_message", stderr.getvalue())

    def test_event_command_can_wait_for_response(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.wait_for_event_response", return_value=0) as waiter:
                    with redirect_stdout(StringIO()):
                        code = main(
                            [
                                "event",
                                "file_change",
                                "--wait",
                                "--timeout",
                                "2",
                                "--poll-interval",
                                "0.1",
                                "--mark-read",
                            ]
                        )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        waiter.assert_called_once()
        self.assertEqual(waiter.call_args.args[0], 1)
        self.assertEqual(waiter.call_args.kwargs["timeout"], 2.0)
        self.assertEqual(waiter.call_args.kwargs["poll_interval"], 0.1)
        self.assertTrue(waiter.call_args.kwargs["mark_read"])
        self.assertEqual(waiter.call_args.kwargs["event_label"], "file_change event")

    def test_top_level_message_shortcut_can_wait_for_response(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch("mew.commands.wait_for_event_response", return_value=0) as waiter:
                    with redirect_stdout(StringIO()):
                        code = main(
                            [
                                "-m",
                                "hello",
                                "--wait",
                                "--timeout",
                                "2",
                                "--poll-interval",
                                "0.1",
                                "--mark-read",
                            ]
                        )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(code, 0)
        waiter.assert_called_once()
        self.assertEqual(waiter.call_args.args[0], 1)
        self.assertEqual(waiter.call_args.kwargs["timeout"], 2.0)
        self.assertEqual(waiter.call_args.kwargs["poll_interval"], 0.1)
        self.assertTrue(waiter.call_args.kwargs["mark_read"])

    def test_webhook_queues_external_event(self):
        from mew.commands import make_webhook_handler

        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), make_webhook_handler())
                server.timeout = 1
                thread = threading.Thread(target=server.handle_request)
                thread.daemon = True
                thread.start()
                try:
                    body = b'{"ref":"main"}'
                    request = Request(
                        f"http://127.0.0.1:{server.server_port}/event/github_webhook?source=test",
                        data=body,
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(request, timeout=5) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                finally:
                    server.server_close()
                    thread.join(timeout=5)

                from mew.state import load_state

                state = load_state()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(payload["event_type"], "github_webhook")
        self.assertEqual(state["inbox"][0]["source"], "test")
        self.assertEqual(state["inbox"][0]["payload"], {"ref": "main"})

    def test_webhook_rejects_bad_token(self):
        from mew.commands import make_webhook_handler

        server = ThreadingHTTPServer(("127.0.0.1", 0), make_webhook_handler(token="secret"))
        server.timeout = 1
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/event/github_webhook",
                data=b"{}",
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
        finally:
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 401)

    def test_webhook_rejects_invalid_utf8_body(self):
        from mew.commands import make_webhook_handler

        server = ThreadingHTTPServer(("127.0.0.1", 0), make_webhook_handler())
        server.timeout = 1
        thread = threading.Thread(target=server.handle_request)
        thread.daemon = True
        thread.start()
        try:
            request = Request(
                f"http://127.0.0.1:{server.server_port}/event/github_webhook",
                data=b"\xff",
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
        finally:
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual(raised.exception.code, 400)

    def test_webhook_requires_token_for_non_loopback_hosts(self):
        with redirect_stderr(StringIO()) as stderr:
            code = main(["webhook", "--host", "0.0.0.0", "--port", "0", "--once"])

        self.assertEqual(code, 1)
        self.assertIn("webhook token is required", stderr.getvalue())

    def test_webhook_handler_sets_socket_timeout_before_headers(self):
        from mew.commands import make_webhook_handler

        handler = make_webhook_handler(read_timeout=3.5)

        self.assertEqual(handler.timeout, 3.5)

    def test_perceive_command_supports_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with patch(
                    "mew.perception.run_command_record",
                    return_value={
                        "cwd": str(Path(tmp).resolve()),
                        "exit_code": 0,
                        "stdout": "## main\n M file.py\n",
                        "stderr": "",
                    },
                ):
                    with redirect_stdout(StringIO()) as stdout:
                        code = main(["perceive", "--allow-read", ".", "--json"])

                self.assertEqual(code, 0)
                data = json.loads(stdout.getvalue())
                git = next(item for item in data["observations"] if item["type"] == "git_status")
                self.assertEqual(git["branch"], "main")
            finally:
                os.chdir(old_cwd)

    def test_chat_handles_slash_commands_and_messages(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import (
                    add_event,
                    add_runtime_effect,
                    complete_runtime_effect,
                    load_state,
                    save_state,
                    state_lock,
                )

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Chat interface",
                            "description": "",
                            "status": "todo",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": ".",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    state["agent_runs"].append(
                        {
                            "id": 1,
                            "task_id": 1,
                            "purpose": "implementation",
                            "status": "running",
                            "backend": "ai-cli",
                            "model": "codex-ultra",
                            "external_pid": 123,
                        }
                    )
                    state["verification_runs"].append(
                        {
                            "id": 1,
                            "command": "python -m unittest",
                            "exit_code": 0,
                            "finished_at": "done",
                        }
                    )
                    state["write_runs"].append(
                        {
                            "id": 1,
                            "operation": "edit_file",
                            "path": "/tmp/example.py",
                            "changed": True,
                            "dry_run": True,
                            "written": False,
                        }
                    )
                    state["thought_journal"].append(
                        {
                            "id": 1,
                            "event_id": 1,
                            "event_type": "passive_tick",
                            "at": "thought-time",
                            "summary": "Remember the current loop.",
                            "open_threads": ["Keep checking the task."],
                            "resolved_threads": [],
                            "actions": [{"type": "record_memory", "summary": "Remember"}],
                            "counts": {"actions": 1},
                        }
                    )
                    event = add_event(state, "passive_tick", "runtime", {})
                    effect = add_runtime_effect(state, event, "passive_tick", "planning", "effect-start")
                    effect["action_types"] = ["send_message"]
                    complete_runtime_effect(
                        state,
                        effect["id"],
                        "effect-done",
                        "applied",
                        processed_count=1,
                        counts={"messages": 1},
                    )
                    save_state(state)

                stdin = StringIO(
                    "/focus\n/next\n/agents\n/verification\n/writes\n/runtime-effects\n/thoughts details\n"
                    "hello mew\n/exit\n"
                )
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()) as stderr,
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                self.assertIn("no active runtime", stderr.getvalue())
                self.assertIn("mew run --once", stderr.getvalue())
                self.assertIn("mew step --ai --auth auth.json --max-steps 1", stderr.getvalue())
                output = stdout.getvalue()
                self.assertIn("mew chat", output)
                self.assertIn("Mew focus", output)
                self.assertIn("mew agent result 1", output)
                self.assertIn("#1 [running/implementation]", output)
                self.assertIn("#1 [passed]", output)
                self.assertIn("#1 [edit_file]", output)
                self.assertIn("#1 [applied] event=#1 reason=passive_tick", output)
                self.assertIn("#1 event=passive_tick#1", output)
                self.assertIn("open_threads:", output)
                self.assertIn("queued message event", output)

                state = load_state()
                self.assertEqual(state["inbox"][-1]["payload"]["text"], "hello mew")
            finally:
                os.chdir(old_cwd)

    def test_chat_health_slash_commands_delegate_to_existing_commands(self):
        from mew.commands import run_chat_slash_command

        with (
            patch("mew.commands.build_doctor_data", return_value={"ok": True}) as build_doctor,
            patch("mew.commands.format_doctor_data", return_value="doctor output"),
            redirect_stdout(StringIO()) as stdout,
        ):
            self.assertEqual(run_chat_slash_command("/doctor", {}), "continue")
        self.assertIn("doctor output", stdout.getvalue())
        self.assertIsNone(build_doctor.call_args.args[0].auth)

        with (
            patch("mew.commands.cmd_repair", return_value=0) as repair,
            redirect_stdout(StringIO()),
        ):
            self.assertEqual(run_chat_slash_command("/repair --force", {}), "continue")
        self.assertTrue(repair.call_args.args[0].force)

    def test_chat_cockpit_commands_update_state(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, add_question, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Cockpit task",
                            "kind": "coding",
                            "description": "Exercise chat controls.",
                            "status": "todo",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": ".",
                            "auto_execute": False,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    event = add_event(state, "passive_tick", "runtime")
                    event["processed_at"] = "processed"
                    event["decision_plan"] = {
                        "summary": "Choose a small useful next move.",
                        "decisions": [{"type": "propose_task", "title": "Cockpit task"}],
                    }
                    event["action_plan"] = {
                        "summary": "Proposed a task.",
                        "actions": [{"type": "propose_task", "title": "Cockpit task"}],
                    }
                    add_question(state, "Can this wait?", related_task_id=1)
                    save_state(state)

                stdin = StringIO(
                    "/add New cockpit task | Created inside chat\n"
                    "/show 2\n"
                    "/note 2 remember this detail\n"
                    "/kind #2 admin\n"
                    "/defer 1 later\n"
                    "/questions\n"
                    "/reopen 1\n"
                    "/why\n"
                    "/digest\n"
                    "/pause testing\n"
                    "/mode act\n"
                    "/ready 1\n"
                    "/approve 1\n"
                    "/plan 1 prompt\n"
                    "/dispatch 1 dry-run\n"
                    "/block 1\n"
                    "/done 1\n"
                    "/resume\n"
                    "/exit\n"
                )
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()) as stderr,
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                self.assertEqual(stderr.getvalue(), "")
                output = stdout.getvalue()
                self.assertIn("created #2 [todo/normal/unknown] New cockpit task", output)
                self.assertIn("description: Created inside chat", output)
                self.assertIn("noted task #2", output)
                self.assertIn("task #2 kind=admin", output)
                self.assertIn("deferred question #1", output)
                self.assertIn("reopened question #1", output)
                self.assertIn("Latest processed event", output)
                self.assertIn("Digest since", output)
                self.assertIn("autonomy paused", output)
                self.assertIn("mode override: act", output)
                self.assertIn("task #1 status=ready", output)
                self.assertIn("approved task #1", output)
                self.assertIn("created plan #1", output)
                self.assertIn("implementation_prompt:", output)
                self.assertIn("created dry-run implementation run", output)
                self.assertIn("task #1 status=blocked", output)
                self.assertIn("task #1 status=done", output)
                self.assertIn("autonomy resumed", output)

                state = load_state()
                self.assertFalse(state["autonomy"]["paused"])
                self.assertEqual(state["autonomy"]["level_override"], "act")
                self.assertEqual(state["tasks"][0]["status"], "done")
                self.assertTrue(state["tasks"][0]["auto_execute"])
                self.assertEqual(state["tasks"][1]["title"], "New cockpit task")
                self.assertIn("remember this detail", state["tasks"][1]["notes"])
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
            finally:
                os.chdir(old_cwd)

    def test_chat_resolves_attention_items(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_attention_item, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_attention_item(state, "test", "One", "first")
                    add_attention_item(state, "test", "Two", "second")
                    save_state(state)

                stdin = StringIO("/attention\n/resolve 1\n/resolve all\n/attention all\n/exit\n")
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("#1 [open/normal] One: first", output)
                self.assertIn("resolved 1 attention item(s)", output)
                self.assertIn("#1 [resolved/normal] One: first", output)
                self.assertIn("#2 [resolved/normal] Two: second", output)

                state = load_state()
                self.assertTrue(all(item.get("status") == "resolved" for item in state["attention"]["items"]))
            finally:
                os.chdir(old_cwd)

    def test_chat_programmer_loop_commands(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Programmer loop",
                            "description": "Exercise chat programmer commands.",
                            "status": "ready",
                            "priority": "normal",
                            "notes": "",
                            "command": "",
                            "cwd": ".",
                            "auto_execute": True,
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": 3,
                            "plans": [{"id": 1, "status": "planned", "cwd": ".", "model": "codex-ultra"}],
                            "latest_plan_id": 1,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    state["agent_runs"].extend(
                        [
                            {
                                "id": 1,
                                "task_id": 1,
                                "purpose": "implementation",
                                "plan_id": 1,
                                "status": "completed",
                                "backend": "ai-cli",
                                "model": "codex-ultra",
                                "cwd": str(Path(".").resolve()),
                                "prompt": "implemented",
                                "prompt_file": "",
                                "external_pid": 111,
                                "result": "implemented",
                                "stdout": "",
                                "stderr": "",
                            },
                            {
                                "id": 2,
                                "task_id": 1,
                                "purpose": "review",
                                "plan_id": 1,
                                "review_of_run_id": 1,
                                "status": "completed",
                                "backend": "ai-cli",
                                "model": "gpt-5.1-codex-mini",
                                "cwd": str(Path(".").resolve()),
                                "prompt": "review",
                                "prompt_file": "",
                                "external_pid": 222,
                                "result": "STATUS: needs_fix\nSUMMARY: x\nFOLLOW_UP:\n- Add a regression test",
                                "stdout": "",
                                "stderr": "",
                            },
                            {
                                "id": 3,
                                "task_id": 1,
                                "purpose": "implementation",
                                "plan_id": 1,
                                "status": "failed",
                                "backend": "ai-cli",
                                "model": "codex-ultra",
                                "cwd": str(Path(".").resolve()),
                                "prompt": "failed",
                                "prompt_file": "",
                                "external_pid": 333,
                                "result": "failed",
                                "stdout": "",
                                "stderr": "",
                            },
                        ]
                    )
                    save_state(state)

                def fake_get_result(state, run, verbose=False):
                    run["status"] = "completed"
                    run["result"] = run.get("result") or "collected"
                    return run

                def fake_wait(state, run, timeout=None):
                    run["status"] = "completed"
                    run["result"] = run.get("result") or "waited"
                    return run

                stdin = StringIO(
                    "/result 1\n"
                    "/wait 1 1\n"
                    "/review 1 dry-run\n"
                    "/followup 2\n"
                    "/retry 3 dry-run\n"
                    "/sweep dry-run\n"
                    "/exit\n"
                )
                with (
                    patch("sys.stdin", stdin),
                    patch("mew.commands.get_agent_run_result", side_effect=fake_get_result),
                    patch("mew.commands.wait_agent_run", side_effect=fake_wait),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("agent run #1 status=completed", output)
                self.assertIn("created dry-run review run", output)
                self.assertIn("review run #2 status=needs_fix", output)
                self.assertIn("Follow up review #2 for task #1", output)
                self.assertIn("created dry-run retry run", output)
                self.assertIn("Review needed", output)

                state = load_state()
                purposes = [run.get("purpose") for run in state["agent_runs"]]
                self.assertGreaterEqual(purposes.count("review"), 2)
                self.assertEqual(state["tasks"][-1]["title"], "Follow up review #2 for task #1")
                self.assertEqual(state["agent_runs"][-1]["status"], "dry_run")
            finally:
                os.chdir(old_cwd)

    def test_agent_followup_ack_does_not_create_task(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Existing task",
                            "description": "",
                            "status": "doing",
                            "priority": "medium",
                            "source": "test",
                            "notes": "",
                            "agent_backend": "",
                            "agent_model": "",
                            "agent_prompt": "",
                            "agent_run_id": None,
                            "plans": [],
                            "latest_plan_id": None,
                            "runs": [],
                            "created_at": "now",
                            "updated_at": "now",
                        }
                    )
                    state["agent_runs"].append(
                        {
                            "id": 2,
                            "task_id": 1,
                            "purpose": "review",
                            "status": "completed",
                            "result": "STATUS: needs_fix\nSUMMARY: x\nFOLLOW_UP:\n- Already fixed",
                            "stdout": "",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["agent", "followup", "2", "--ack", "--note", "fixed later"]), 0)

                self.assertIn("follow-up acknowledged without creating a task", stdout.getvalue())
                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertTrue(state["agent_runs"][0]["followup_processed_at"])
                self.assertIn("fixed later", state["tasks"][0]["notes"])
            finally:
                os.chdir(old_cwd)

    def test_chat_verify_runs_and_records_failure_attention(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state

                def fake_run_command(command, cwd=None, timeout=300):
                    return {
                        "command": command,
                        "argv": ["python", "-m", "unittest"],
                        "cwd": str(Path(".").resolve()),
                        "started_at": "start",
                        "finished_at": "end",
                        "exit_code": 1,
                        "stdout": "some stdout",
                        "stderr": "FAILED",
                    }

                stdin = StringIO("/verify python -m unittest\n/verification\n/exit\n")
                with (
                    patch("sys.stdin", stdin),
                    patch("mew.commands.run_command_record", side_effect=fake_run_command),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("#1 [failed]", output)
                self.assertIn("exit_code: 1", output)
                self.assertIn("FAILED", output)

                state = load_state()
                self.assertEqual(len(state["verification_runs"]), 1)
                self.assertEqual(state["verification_runs"][0]["command"], "python -m unittest")
                self.assertEqual(state["verification_runs"][0]["exit_code"], 1)
                self.assertEqual(state["verification_runs"][0]["reason"], "manual chat verification")
                self.assertEqual(len(state["attention"]["items"]), 1)
                self.assertEqual(state["attention"]["items"][0]["kind"], "verification")
                self.assertEqual(state["attention"]["items"][0]["priority"], "high")
                self.assertIn("FAILED", state["attention"]["items"][0]["reason"])
            finally:
                os.chdir(old_cwd)

    def test_chat_self_improve_creates_plan_and_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state

                stdin = StringIO("/self dry-run prompt improve chat self loop\n/exit\n")
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("created #1 [ready/normal/coding] Improve mew itself", output)
                self.assertIn("created plan #1", output)
                self.assertIn("implementation_prompt:", output)
                self.assertIn("created dry-run self-improve run #1", output)

                state = load_state()
                self.assertEqual(state["tasks"][0]["title"], "Improve mew itself")
                self.assertEqual(state["tasks"][0]["status"], "ready")
                self.assertIn("improve chat self loop", state["tasks"][0]["description"])
                self.assertEqual(state["tasks"][0]["latest_plan_id"], 1)
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
            finally:
                os.chdir(old_cwd)

    def test_runtime_autonomy_controls_respect_pause_and_mode_override(self):
        from argparse import Namespace

        from mew.runtime import apply_runtime_autonomy_controls
        from mew.state import default_state

        state = default_state()
        args = Namespace(
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=True,
            allow_verify=True,
            verify_command="python -m unittest",
            allow_write=False,
        )
        state["autonomy"]["paused"] = True

        controls = apply_runtime_autonomy_controls(state, args, pending_user=False, current_time="now")

        self.assertFalse(controls["autonomous"])
        self.assertEqual(controls["autonomy_level"], "off")
        self.assertFalse(state["autonomy"]["enabled"])
        self.assertTrue(state["autonomy"]["requested_enabled"])

        state["autonomy"]["paused"] = False
        state["autonomy"]["level_override"] = "observe"
        controls = apply_runtime_autonomy_controls(state, args, pending_user=False, current_time="later")

        self.assertTrue(controls["autonomous"])
        self.assertEqual(controls["autonomy_level"], "observe")
        self.assertEqual(state["autonomy"]["level"], "observe")
        self.assertTrue(controls["allow_agent_run"])

    def test_tool_read_prints_non_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("notes.md").write_text("hello from mew tools", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "read", "notes.md"])

                self.assertEqual(code, 0)
                self.assertIn("hello from mew tools", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_read_refuses_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("auth.json").write_text('{"token":"secret"}', encoding="utf-8")

                with redirect_stderr(StringIO()) as stderr:
                    code = main(["tool", "read", "auth.json"])

                self.assertEqual(code, 1)
                self.assertIn("sensitive path", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_read_refuses_mew_internal_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path(".mew").mkdir()
                Path(".mew/state.json").write_text("{}", encoding="utf-8")

                with redirect_stderr(StringIO()) as stderr:
                    code = main(["tool", "read", ".mew/state.json"])

                self.assertEqual(code, 1)
                self.assertIn("sensitive path", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_list_hides_sensitive_entries(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path(".mew").mkdir()
                Path("auth.json").write_text("secret", encoding="utf-8")
                Path("notes.md").write_text("hello", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "list", "."])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("notes.md", output)
                self.assertNotIn(".mew", output)
                self.assertNotIn("auth.json", output)
            finally:
                os.chdir(old_cwd)

    def test_tool_write_create_and_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "tool",
                            "write",
                            "notes.md",
                            "--content",
                            "hello\n",
                            "--create",
                            "--dry-run",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("dry_run: True", stdout.getvalue())
                self.assertFalse(Path("notes.md").exists())

                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "tool",
                            "write",
                            "notes.md",
                            "--content",
                            "hello\n",
                            "--create",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertEqual(Path("notes.md").read_text(encoding="utf-8"), "hello\n")
                self.assertIn("written: True", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_edit_replaces_one_match_and_refuses_sensitive_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("notes.md").write_text("hello mew\n", encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "edit", "notes.md", "--old", "mew", "--new", "shell"])

                self.assertEqual(code, 0)
                self.assertEqual(Path("notes.md").read_text(encoding="utf-8"), "hello shell\n")
                self.assertIn("edit_file", stdout.getvalue())

                Path("auth.json").write_text("secret", encoding="utf-8")
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["tool", "edit", "auth.json", "--old", "secret", "--new", "x"])

                self.assertEqual(code, 1)
                self.assertIn("sensitive path", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_test_runs_bounded_command_with_env(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f'FLAG=ok {sys.executable} -c "import os; print(os.environ[\\"FLAG\\"])"'

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "test", "--command", command, "--timeout", "5"])

                self.assertEqual(code, 0)
                self.assertIn("exit_code: 0", stdout.getvalue())
                self.assertIn("ok", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_test_returns_failure_status(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f'{sys.executable} -c "raise SystemExit(7)"'

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "test", "--command", command, "--timeout", "5"])

                self.assertEqual(code, 1)
                self.assertIn("exit_code: 7", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_status_tolerates_non_git_workspace(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "status"])

                self.assertEqual(code, 0)
                self.assertIn("git: unavailable (not a git repository)", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "status", "--json"])

                self.assertEqual(code, 0)
                data = json.loads(stdout.getvalue())
                self.assertFalse(data["git"]["available"])
                self.assertEqual(data["git"]["reason"], "not a git repository")
            finally:
                os.chdir(old_cwd)

    def test_tool_git_diff_supports_staged_stat(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, text=True, capture_output=True)
                Path("example.txt").write_text("hello\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "git", "diff", "--staged", "--stat"])

                self.assertEqual(code, 0)
                self.assertIn("example.txt", stdout.getvalue())
                self.assertIn("git diff --staged --stat --", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_tool_git_diff_supports_base_stat(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                subprocess.run(["git", "init"], check=True, text=True, capture_output=True)
                Path("example.txt").write_text("hello\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=mew",
                        "-c",
                        "user.email=mew@example.com",
                        "commit",
                        "-m",
                        "initial",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                )
                Path("example.txt").write_text("hello\nmew\n", encoding="utf-8")
                subprocess.run(["git", "add", "example.txt"], check=True, text=True, capture_output=True)
                subprocess.run(
                    [
                        "git",
                        "-c",
                        "user.name=mew",
                        "-c",
                        "user.email=mew@example.com",
                        "commit",
                        "-m",
                        "change",
                    ],
                    check=True,
                    text=True,
                    capture_output=True,
                )

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["tool", "git", "diff", "--base", "HEAD~1", "--stat"])

                self.assertEqual(code, 0)
                self.assertIn("git diff HEAD~1...HEAD --stat --", stdout.getvalue())
                self.assertIn("example.txt", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_verification_lists_recent_runs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["verification_runs"].append(
                        {
                            "id": 1,
                            "command": "python -m unittest",
                            "exit_code": 0,
                            "stdout": "OK",
                            "stderr": "",
                            "finished_at": "done",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["verification", "--details"])

                self.assertEqual(code, 0)
                self.assertIn("#1 [passed]", stdout.getvalue())
                self.assertIn("stdout:", stdout.getvalue())
                self.assertIn("OK", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_writes_lists_recent_runs(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["write_runs"].append(
                        {
                            "id": 1,
                            "operation": "edit_file",
                            "path": "/tmp/notes.md",
                            "changed": True,
                            "dry_run": False,
                            "written": True,
                            "rolled_back": True,
                            "verification_run_id": 3,
                            "verification_exit_code": 1,
                            "rollback": {
                                "path": "/tmp/notes.md",
                                "restored": True,
                                "removed_created_file": False,
                                "restored_at": "done",
                            },
                            "diff": "--- a\n+++ b\n",
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["writes", "--details"])

                self.assertEqual(code, 0)
                self.assertIn("#1 [edit_file]", stdout.getvalue())
                self.assertIn("rolled_back=True", stdout.getvalue())
                self.assertIn("verification=#3 exit=1", stdout.getvalue())
                self.assertIn("diff:", stdout.getvalue())
                self.assertIn("rollback:", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_message_wait_prints_response_for_event(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                def respond_once_event_exists():
                    deadline = time.monotonic() + 2.0
                    while time.monotonic() < deadline:
                        with state_lock():
                            state = load_state()
                            if state["inbox"]:
                                event = state["inbox"][0]
                                add_outbox_message(
                                    state,
                                    "assistant",
                                    "hello from runtime",
                                    event_id=event["id"],
                                )
                                event["processed_at"] = "done"
                                save_state(state)
                                return
                        time.sleep(0.01)

                responder = threading.Thread(target=respond_once_event_exists)
                responder.start()
                with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                    code = main(
                        [
                            "message",
                            "hello?",
                            "--wait",
                            "--timeout",
                            "2",
                            "--poll-interval",
                            "0.01",
                        ]
                    )
                responder.join(timeout=2)

                self.assertEqual(code, 0)
                self.assertIn("queued message event #1", stdout.getvalue())
                self.assertIn("hello from runtime", stdout.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
