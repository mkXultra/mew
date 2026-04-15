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
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch

from mew.cli import main
from mew.errors import MewError


class CommandTests(unittest.TestCase):
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

    def test_session_jsonl_handles_status_outbox_ack_and_message(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_outbox_message, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    add_outbox_message(state, "info", "hello from mew")
                    save_state(state)

                stdin = StringIO(
                    '{"id":"s","type":"status"}\n'
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
                self.assertEqual(responses[1]["counts"]["unread_outbox"], 1)
                self.assertEqual(responses[2]["type"], "outbox")
                self.assertEqual(responses[2]["messages"][0]["text"], "hello from mew")
                self.assertEqual(responses[3]["type"], "acknowledged")
                self.assertEqual(responses[3]["count"], 1)
                self.assertEqual(responses[4]["type"], "event_queued")
                self.assertEqual(responses[4]["event"]["payload"]["text"], "hello session")
                self.assertEqual(responses[5]["type"], "bye")

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
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["archive", "--keep-recent", "1", "--apply"])

                self.assertEqual(code, 0)
                self.assertIn("archived_inbox: 2", stdout.getvalue())
                self.assertIn("archived_outbox: 2", stdout.getvalue())
                self.assertIn("archived_agent_runs: 1", stdout.getvalue())
                self.assertIn("archived_verification_runs: 2", stdout.getvalue())
                self.assertIn("archived_write_runs: 2", stdout.getvalue())

                state = load_state()
                self.assertEqual(len(state["inbox"]), 2)
                self.assertEqual(len(state["outbox"]), 2)
                self.assertEqual([run["id"] for run in state["agent_runs"]], [2, 3, 4, 5, 6])
                self.assertEqual([run["id"] for run in state["verification_runs"]], [3])
                self.assertEqual([run["id"] for run in state["write_runs"]], [3])
                archives = list((Path(".mew") / "archive").glob("state-*.json"))
                self.assertEqual(len(archives), 1)
                archived = json.loads(archives[0].read_text(encoding="utf-8"))
                self.assertEqual(
                    archived["counts"],
                    {
                        "inbox": 2,
                        "outbox": 2,
                        "agent_runs": 1,
                        "verification_runs": 2,
                        "write_runs": 2,
                    },
                )
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
                from mew.state import add_event, load_state, save_state, state_lock

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
                from mew.state import add_event, load_state, save_state, state_lock

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
                from mew.state import load_state, save_state, state_lock

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
                    save_state(state)

                stdin = StringIO("/next\n/agents\n/verification\n/writes\n/thoughts details\nhello mew\n/exit\n")
                with (
                    patch("sys.stdin", stdin),
                    redirect_stdout(StringIO()) as stdout,
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("mew chat", output)
                self.assertIn("mew agent result 1", output)
                self.assertIn("#1 [running/implementation]", output)
                self.assertIn("#1 [passed]", output)
                self.assertIn("#1 [edit_file]", output)
                self.assertIn("#1 event=passive_tick#1", output)
                self.assertIn("open_threads:", output)
                self.assertIn("queued message event", output)

                state = load_state()
                self.assertEqual(state["inbox"][0]["payload"]["text"], "hello mew")
            finally:
                os.chdir(old_cwd)

    def test_chat_cockpit_commands_update_state(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                from mew.state import add_event, load_state, save_state, state_lock

                with state_lock():
                    state = load_state()
                    state["tasks"].append(
                        {
                            "id": 1,
                            "title": "Cockpit task",
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
                    save_state(state)

                stdin = StringIO(
                    "/add New cockpit task | Created inside chat\n"
                    "/show 2\n"
                    "/note 2 remember this detail\n"
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
                    redirect_stderr(StringIO()),
                ):
                    code = main(["chat", "--no-brief", "--no-unread", "--no-activity"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("created #2 [todo/normal] New cockpit task", output)
                self.assertIn("description: Created inside chat", output)
                self.assertIn("noted task #2", output)
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
                self.assertIn("created #1 [ready/normal] Improve mew itself", output)
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
