import os
import shlex
import sys
from io import StringIO
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from mew.agent import should_use_ai_for_event, think_phase
from mew.cli import main
from mew.errors import ModelBackendError
from mew.runtime import (
    apply_runtime_autonomy_controls,
    compact_agent_reflex_report,
    guidance_with_runtime_focus,
    native_work_skip_recovery_suggestion,
    record_runtime_native_work_step_skip,
    run_runtime_native_work_recovery_step,
    run_runtime_post_run_pipeline,
    select_runtime_native_work_step,
    should_defer_commit_for_user_message,
)
from mew.state import add_event, add_outbox_message, default_state, load_state, save_state, state_lock
from mew.work_session import create_work_session, mark_work_session_runtime_owned


class RuntimeTests(unittest.TestCase):
    def test_guidance_with_runtime_focus_appends_transient_focus(self):
        guidance = guidance_with_runtime_focus("Base guidance.", "Review current changes")

        self.assertIn("Base guidance.", guidance)
        self.assertIn("Immediate runtime focus:", guidance)
        self.assertIn("Review current changes", guidance)
        self.assertIn("Do not stop solely because an unrelated older question is waiting.", guidance)

    def test_compact_agent_reflex_report_drops_nested_previous_report(self):
        report = {
            "collected": [f"run #{index}" for index in range(7)],
            "runtime_status": {
                "state": "running",
                "last_agent_reflex_report": {"collected": ["old"]},
            },
        }

        compact = compact_agent_reflex_report(report, limit=3)

        self.assertEqual(compact["collected"], ["run #4", "run #5", "run #6"])
        self.assertEqual(compact["collected_omitted"], 4)
        self.assertEqual(compact["runtime_status"], {"state": "running"})

    def test_record_runtime_native_work_step_skip_keeps_bounded_history(self):
        runtime_status = {}

        for index in range(25):
            record_runtime_native_work_step_skip(
                runtime_status,
                f"reason-{index}",
                current_time=f"t-{index}",
                event_id=index,
                phase="select",
            )

        self.assertEqual(runtime_status["last_native_work_step_skip"], "reason-24")
        self.assertEqual(len(runtime_status["native_work_step_skips"]), 20)
        self.assertEqual(runtime_status["native_work_step_skips"][0]["reason"], "reason-5")
        self.assertEqual(runtime_status["native_work_step_skips"][-1]["event_id"], 24)

    def test_post_run_pipeline_uses_autonomy_gates(self):
        state = default_state()
        args = SimpleNamespace(
            agent_stale_minutes=7.0,
            agent_result_timeout=3.0,
            agent_start_timeout=5.0,
            review_model="reviewer",
        )
        autonomy = {
            "autonomous": True,
            "autonomy_level": "act",
            "allow_agent_run": True,
        }

        with patch("mew.runtime.sweep_agent_runs", return_value={"review_started": ["ok"]}) as sweep:
            report = run_runtime_post_run_pipeline(state, args, autonomy)

        self.assertEqual(report, {"review_started": ["ok"]})
        sweep.assert_called_once()
        _, kwargs = sweep.call_args
        self.assertTrue(kwargs["collect"])
        self.assertTrue(kwargs["start_reviews"])
        self.assertTrue(kwargs["followup"])
        self.assertEqual(kwargs["stale_minutes"], 7.0)
        self.assertEqual(kwargs["review_model"], "reviewer")
        self.assertEqual(kwargs["result_timeout"], 3.0)
        self.assertEqual(kwargs["start_timeout"], 5.0)

    def test_post_run_pipeline_does_not_start_reviews_below_act_level(self):
        state = default_state()
        args = SimpleNamespace(agent_stale_minutes=7.0, review_model="")
        autonomy = {
            "autonomous": True,
            "autonomy_level": "propose",
            "allow_agent_run": True,
        }

        with patch("mew.runtime.sweep_agent_runs", return_value={}) as sweep:
            run_runtime_post_run_pipeline(state, args, autonomy)

        _, kwargs = sweep.call_args
        self.assertTrue(kwargs["collect"])
        self.assertFalse(kwargs["start_reviews"])
        self.assertTrue(kwargs["followup"])

    def test_apply_runtime_autonomy_controls_gates_native_work_to_autonomous_cycle(self):
        state = default_state()
        args = SimpleNamespace(
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=False,
            allow_native_work=True,
            allow_native_advance=True,
            allow_verify=False,
            verify_command="",
            allow_write=False,
        )

        controls = apply_runtime_autonomy_controls(state, args, pending_user=False, current_time="now")
        blocked = apply_runtime_autonomy_controls(state, args, pending_user=True, current_time="later")

        self.assertTrue(controls["allow_native_work"])
        self.assertTrue(controls["allow_native_advance"])
        self.assertTrue(state["autonomy"]["allow_native_work"])
        self.assertFalse(blocked["allow_native_work"])
        self.assertFalse(blocked["allow_native_advance"])

    def test_select_runtime_native_work_step_uses_runtime_owned_session_defaults(self):
        state = default_state()
        task = {
            "id": 1,
            "title": "Improve mew",
            "description": "",
            "status": "ready",
            "kind": "coding",
            "plans": [],
            "runs": [],
        }
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(session, event_id=7, current_time="now")
        session["default_options"] = {
            "auth": "auth.json",
            "model_backend": "codex",
            "model": "gpt-5.4",
            "allow_read": ["."],
            "prompt_approval": True,
            "model_timeout": 120,
            "verify_timeout": 45,
            "tool_timeout": 30,
        }

        step, skip = select_runtime_native_work_step(state)

        self.assertIsNone(skip)
        self.assertEqual(step["session_id"], session["id"])
        self.assertEqual(step["task_id"], task["id"])
        self.assertIn("work 1 --live --auth auth.json", step["command"])
        self.assertIn("--model-backend codex", step["command"])
        self.assertIn("--model gpt-5.4", step["command"])
        self.assertIn("--allow-read .", step["command"])
        self.assertIn("--model-timeout 120", step["command"])
        self.assertIn("--verify-timeout 45", step["command"])
        self.assertIn("--timeout 30", step["command"])
        self.assertIn("--quiet", step["command"])
        self.assertIn("--compact-live", step["command"])
        self.assertIn("--no-prompt-approval", step["command"])
        self.assertNotIn("--prompt-approval", step["command"])
        self.assertIn("--max-steps 1", step["command"])

    def test_select_runtime_native_work_step_skips_human_session(self):
        state = default_state()
        task = {"id": 1, "title": "Human task", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        create_work_session(state, task)

        step, skip = select_runtime_native_work_step(state)

        self.assertIsNone(step)
        self.assertEqual(skip, "human_work_session_active")

    def test_select_runtime_native_work_step_skips_pending_write_approval(self):
        state = default_state()
        task = {"id": 1, "title": "Write task", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(session, event_id=7, current_time="now")
        session["tool_calls"].append(
            {
                "id": 1,
                "tool": "write_file",
                "status": "completed",
                "result": {"dry_run": True, "changed": True},
            }
        )

        step, skip = select_runtime_native_work_step(state)

        self.assertIsNone(step)
        self.assertEqual(skip, "pending_write_approval")

    def test_native_work_skip_recovery_suggests_pending_write_approval_controls(self):
        state = default_state()
        task = {"id": 1, "title": "Write task", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(session, event_id=7, current_time="now")
        session["tool_calls"].append(
            {
                "id": 1,
                "session_id": session["id"],
                "task_id": task["id"],
                "tool": "edit_file",
                "status": "completed",
                "parameters": {"path": "src/mew/example.py"},
                "result": {"dry_run": True, "changed": True, "diff": "-old\n+new\n"},
            }
        )

        _step, skip = select_runtime_native_work_step(state)
        recovery = native_work_skip_recovery_suggestion(state, skip)

        self.assertEqual(recovery["action"], "resolve_pending_write_approval")
        self.assertEqual(recovery["session_id"], session["id"])
        self.assertEqual(recovery["task_id"], task["id"])
        self.assertEqual(recovery["tool_call_id"], 1)
        self.assertIn("mew work 1 --session --resume --allow-read .", recovery["command"])
        self.assertIn("mew work 1 --approve-tool 1", recovery["blocked_command"])
        self.assertIn("--allow-unpaired-source-edit", recovery["override_command"])
        self.assertIn("mew work 1 --reject-tool 1", recovery["alternate_command"])
        self.assertIn("mew work 1 --session --resume --allow-read .", recovery["resume_command"])

    def test_native_work_skip_recovery_keeps_approve_primary_for_non_source_write(self):
        state = default_state()
        task = {"id": 1, "title": "Write task", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(session, event_id=7, current_time="now")
        session["tool_calls"].append(
            {
                "id": 1,
                "session_id": session["id"],
                "task_id": task["id"],
                "tool": "edit_file",
                "status": "completed",
                "parameters": {"path": "notes.md"},
                "result": {"dry_run": True, "changed": True, "diff": "-old\n+new\n"},
            }
        )

        _step, skip = select_runtime_native_work_step(state)
        recovery = native_work_skip_recovery_suggestion(state, skip)

        self.assertEqual(recovery["action"], "resolve_pending_write_approval")
        self.assertIn("mew work 1 --approve-tool 1", recovery["command"])
        self.assertNotIn("blocked_command", recovery)
        self.assertNotIn("override_command", recovery)
        self.assertIn("mew work 1 --reject-tool 1", recovery["alternate_command"])

    def test_select_runtime_native_work_step_skips_session_started_this_cycle(self):
        state = default_state()
        task = {"id": 1, "title": "New runtime task", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(session, event_id=7, current_time="now")

        step, skip = select_runtime_native_work_step(state, current_event_id=7)

        self.assertIsNone(step)
        self.assertEqual(skip, "session_started_this_cycle")

    def test_select_runtime_native_work_step_skips_unresolved_previous_failure(self):
        state = default_state()
        task = {"id": 1, "title": "Recover failure", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(
            session,
            event_id=7,
            current_time="2026-04-18T00:00:00Z",
        )
        state["runtime_status"]["last_native_work_step"] = {
            "finished_at": "2026-04-18T00:01:00Z",
            "session_id": session["id"],
            "task_id": task["id"],
            "outcome": "failed",
            "exit_code": 1,
        }
        session["updated_at"] = "2026-04-18T00:01:00Z"

        step, skip = select_runtime_native_work_step(state)

        self.assertIsNone(step)
        self.assertEqual(skip, "previous_native_work_step_failed")

    def test_select_runtime_native_work_step_allows_retry_after_new_session_activity(self):
        state = default_state()
        task = {"id": 1, "title": "Recover failure", "status": "ready", "plans": [], "runs": []}
        state["tasks"].append(task)
        session, _ = create_work_session(state, task)
        mark_work_session_runtime_owned(
            session,
            event_id=7,
            current_time="2026-04-18T00:00:00Z",
        )
        state["runtime_status"]["last_native_work_step"] = {
            "finished_at": "2026-04-18T00:01:00Z",
            "session_id": session["id"],
            "task_id": task["id"],
            "outcome": "failed",
            "exit_code": 1,
        }
        session.setdefault("notes", []).append(
            {
                "created_at": "2026-04-18T00:02:00Z",
                "source": "user",
                "text": "Reviewed failure; retry once.",
            }
        )
        session["updated_at"] = "2026-04-18T00:02:00Z"

        step, skip = select_runtime_native_work_step(state)

        self.assertIsNone(skip)
        self.assertEqual(step["session_id"], session["id"])

    def test_should_defer_commit_for_new_user_message(self):
        state = default_state()
        add_event(state, "user_message", "test", {"text": "urgent"})

        self.assertTrue(should_defer_commit_for_user_message(state, "startup"))
        self.assertFalse(
            should_defer_commit_for_user_message(state, "startup", precomputed_effects=True)
        )
        self.assertFalse(should_defer_commit_for_user_message(state, "user_input"))

    def test_runtime_reflex_runs_before_model_snapshot_and_echoes_outbox(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_sweep(state, *args, **kwargs):
                    state["memory"]["shallow"]["latest_task_summary"] = "reflex ran"
                    add_outbox_message(state, "info", "reflex message")
                    return {"collected": [f"run #{index}" for index in range(10)]}

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    self.assertEqual(
                        state_snapshot["memory"]["shallow"]["latest_task_summary"],
                        "reflex ran",
                    )
                    return (
                        {"summary": "after reflex", "decisions": []},
                        {"summary": "after reflex", "actions": []},
                    )

                with (
                    patch("mew.runtime.sweep_agent_runs", side_effect=fake_sweep),
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-agent-run",
                                "--echo-outbox",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertIn("reflex message", stdout.getvalue())
                with state_lock():
                    state = load_state()
                self.assertEqual(
                    state["runtime_status"]["last_agent_reflex_report"],
                    {
                        "collected": ["run #5", "run #6", "run #7", "run #8", "run #9"],
                        "collected_omitted": 5,
                    },
                )
                self.assertTrue(state["runtime_status"]["last_agent_reflex_at"])
            finally:
                os.chdir(old_cwd)

    def test_runtime_defers_passive_commit_when_user_message_arrives_during_planning(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_plan_runtime_event(_state_snapshot, _event_snapshot, *args, **_kwargs):
                    with state_lock():
                        state = load_state()
                        add_event(state, "user_message", "test", {"text": "urgent"})
                        save_state(state)
                    return (
                        {"summary": "stale passive", "decisions": []},
                        {
                            "summary": "stale passive",
                            "actions": [
                                {
                                    "type": "send_message",
                                    "message_type": "info",
                                    "text": "stale passive response",
                                }
                            ],
                        },
                    )

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--echo-outbox", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                self.assertIn("processed 0 event(s) reason=startup", stdout.getvalue())
                with state_lock():
                    state = load_state()
                self.assertEqual(state["outbox"], [])
                self.assertEqual([event["type"] for event in state["inbox"]], ["startup", "user_message"])
                self.assertIsNone(state["inbox"][0]["processed_at"])
                self.assertIsNone(state["inbox"][1]["processed_at"])
            finally:
                os.chdir(old_cwd)

    def test_runtime_records_effect_journal_for_cycle(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "journaled", "decisions": []},
                            {
                                "summary": "journaled",
                                "actions": [
                                    {
                                        "type": "send_message",
                                        "message_type": "info",
                                        "text": "journaled runtime effect",
                                    }
                                ],
                            },
                        ),
                    ),
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--echo-outbox", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                with state_lock():
                    state = load_state()
                self.assertEqual(len(state["runtime_effects"]), 1)
                effect = state["runtime_effects"][0]
                self.assertEqual(effect["status"], "applied")
                self.assertEqual(effect["summary"], "journaled")
                self.assertEqual(effect["outcome"], "journaled runtime effect")
                self.assertEqual(effect["action_types"], ["send_message"])
                self.assertEqual(effect["counts"]["messages"], 1)
                self.assertIsNotNone(effect["finished_at"])
                self.assertIsNone(state["runtime_status"]["current_effect_id"])
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_processes_passive_tick_first(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--passive-now", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                self.assertIn("processed 1 event(s) reason=passive_tick", stdout.getvalue())
                with state_lock():
                    state = load_state()
                self.assertEqual([event["type"] for event in state["inbox"]], ["passive_tick"])
                self.assertEqual(state["runtime_status"]["last_cycle_reason"], "passive_tick")
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_advances_runtime_owned_native_work(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="before")
                    session["default_options"] = {"allow_read": ["."], "auth": "auth.json"}
                    save_state(state)

                def fake_run_command(command, cwd=None, timeout=None, **kwargs):
                    with state_lock():
                        state = load_state()
                        state.setdefault("test_observations", {})["runner_acquired_state_lock"] = True
                        save_state(state)
                    return {
                        "command": command,
                        "argv": command.split(),
                        "cwd": cwd or ".",
                        "started_at": "start",
                        "finished_at": "finish",
                        "exit_code": 0,
                        "stdout": "ok",
                        "stderr": "",
                    }

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record", side_effect=fake_run_command) as runner,
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertIn("advancing native work session=#1 task=#1", stdout.getvalue())
                runner.assert_called_once()
                command = runner.call_args.args[0]
                self.assertIn("work 1 --live --auth auth.json", command)
                self.assertIn("--quiet", command)
                self.assertIn("--compact-live", command)
                self.assertIn("--no-prompt-approval", command)
                self.assertIn("--max-steps 1", command)
                with state_lock():
                    state = load_state()
                self.assertTrue(state["test_observations"]["runner_acquired_state_lock"])
                self.assertEqual(state["runtime_status"]["last_native_work_step"]["outcome"], "completed")
                self.assertIn("runtime passive advance step completed", state["work_sessions"][0]["notes"][-1]["text"])
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_does_not_blindly_retry_failed_native_work_step(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="before")
                    session["default_options"] = {"allow_read": ["."]}
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session["id"],
                            "task_id": task["id"],
                            "tool": "run_tests",
                            "status": "interrupted",
                            "parameters": {"command": "python -V", "cwd": "."},
                            "summary": "interrupted verifier",
                            "error": "Interrupted before the verifier completed.",
                            "started_at": "before",
                            "finished_at": "before",
                        }
                    )
                    save_state(state)

                def fake_failure(command, cwd=None, timeout=None, **kwargs):
                    return {
                        "command": command,
                        "argv": command.split(),
                        "cwd": cwd or ".",
                        "started_at": "start",
                        "finished_at": "finish",
                        "exit_code": 1,
                        "timed_out": False,
                        "stdout": "",
                        "stderr": "failed",
                    }

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record", side_effect=fake_failure) as first_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        first_code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(first_code, 0)
                first_runner.assert_called_once()

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as second_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        second_code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(second_code, 0)
                second_runner.assert_not_called()
                with state_lock():
                    state = load_state()
                self.assertEqual(
                    state["runtime_status"]["last_native_work_step_skip"],
                    "previous_native_work_step_failed",
                )
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "ask_user_seeded_question")
                self.assertEqual(recovery["reason"], "previous_native_work_step_failed")
                self.assertEqual(recovery["session_id"], 1)
                self.assertEqual(recovery["task_id"], 1)
                self.assertTrue(recovery["question_created"])
                self.assertIn("work 1 --session --resume --allow-read .", recovery["resume_command"])
                self.assertEqual(recovery["recovery_plan_action"], "retry_verification")
                self.assertIn("--allow-verify --verify-command", recovery["recovery_plan_command"])
                self.assertEqual(recovery["recovery_effect_classification"], "verify_pending")
                self.assertEqual(len(state["questions"]), 1)
                self.assertIn("Passive native work session #1", state["questions"][0]["text"])
                self.assertIn("exit_code=1", state["questions"][0]["text"])
                self.assertIn("Recovery plan suggests verification recovery", state["questions"][0]["text"])
                self.assertIn("effect=verify_pending", state["questions"][0]["text"])
                self.assertIn("--allow-verify --verify-command", state["questions"][0]["text"])
                self.assertIn("work 1 --live --allow-read . --max-steps 1", state["questions"][0]["text"])
                self.assertIn(
                    "runtime asked for recovery after failed passive native advance",
                    state["work_sessions"][0]["notes"][-1]["text"],
                )
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_records_skip_recovery_for_pending_approval(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Approve pending write",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="before")
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session["id"],
                            "task_id": task["id"],
                            "tool": "write_file",
                            "status": "completed",
                            "parameters": {"path": "src/mew/runtime_note.py"},
                            "result": {"dry_run": True, "changed": True, "diff": "+note\n"},
                            "started_at": "before",
                            "finished_at": "before",
                        }
                    )
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                runner.assert_not_called()
                with state_lock():
                    state = load_state()
                runtime = state["runtime_status"]
                self.assertEqual(runtime["last_native_work_step_skip"], "pending_write_approval")
                recovery = runtime["last_native_work_skip_recovery"]
                self.assertEqual(recovery["action"], "resolve_pending_write_approval")
                self.assertIn("mew work 1 --session --resume --allow-read .", recovery["command"])
                self.assertIn("mew work 1 --approve-tool 1", recovery["blocked_command"])
                self.assertIn("--allow-unpaired-source-edit", recovery["override_command"])
                self.assertIn("mew work 1 --reject-tool 1", recovery["alternate_command"])
                self.assertEqual(
                    runtime["native_work_step_skips"][-1]["recovery"]["action"],
                    "resolve_pending_write_approval",
                )
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_marks_timed_out_native_work_running_records_interrupted(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="before")
                    session["default_options"] = {"allow_read": ["."]}
                    save_state(state)

                def fake_timeout(command, cwd=None, timeout=None, **kwargs):
                    with state_lock():
                        state = load_state()
                        state["work_sessions"][0]["model_turns"].append({"id": 1, "status": "running"})
                        save_state(state)
                    return {
                        "command": command,
                        "argv": command.split(),
                        "cwd": cwd or ".",
                        "started_at": "start",
                        "finished_at": "finish",
                        "exit_code": None,
                        "timed_out": True,
                        "stdout": "",
                        "stderr": "timed out",
                    }

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record", side_effect=fake_timeout),
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                with state_lock():
                    state = load_state()
                turn = state["work_sessions"][0]["model_turns"][0]
                self.assertEqual(turn["status"], "interrupted")
                self.assertIn("Interrupted before the work model turn completed.", turn["error"])
                step = state["runtime_status"]["last_native_work_step"]
                self.assertEqual(step["outcome"], "failed")
                self.assertTrue(step["timed_out"])
                self.assertEqual(step["repairs"][0]["type"], "interrupted_work_model_turn")
            finally:
                os.chdir(old_cwd)

    def test_run_startup_repairs_incomplete_effects_without_touching_work_sessions(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["inbox"].append(
                        {
                            "id": 1,
                            "type": "passive_tick",
                            "source": "runtime",
                            "payload": {},
                            "created_at": "then",
                            "processed_at": "then",
                        }
                    )
                    state["runtime_effects"].append(
                        {
                            "id": 1,
                            "event_id": 1,
                            "reason": "passive_tick",
                            "status": "planning",
                            "phase": "planning",
                            "created_at": "then",
                            "updated_at": "then",
                            "finished_at": None,
                        }
                    )
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session.get("id"),
                            "task_id": task.get("id"),
                            "tool": "read_file",
                            "status": "running",
                            "parameters": {"path": "README.md"},
                            "result": None,
                            "summary": "",
                            "error": "",
                            "started_at": "then",
                            "finished_at": None,
                        }
                    )
                    session["last_tool_call_id"] = 1
                    state["next_ids"]["event"] = 2
                    state["next_ids"]["runtime_effect"] = 2
                    state["next_ids"]["work_tool_call"] = 2
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertIn("startup repaired 1 interrupted item(s)", stdout.getvalue())
                with state_lock():
                    state = load_state()
                old_effect = next(effect for effect in state["runtime_effects"] if effect.get("id") == 1)
                self.assertEqual(old_effect["status"], "interrupted")
                self.assertIn("no action was recorded", old_effect["recovery_hint"])
                tool_call = state["work_sessions"][0]["tool_calls"][0]
                self.assertEqual(tool_call["status"], "running")
                self.assertEqual(tool_call.get("error") or "", "")
                repairs = state["runtime_status"]["last_startup_repairs"]
                self.assertEqual(
                    [repair["type"] for repair in repairs],
                    ["interrupted_runtime_effect"],
                )
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_auto_recovers_interrupted_native_verifier(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f"{shlex.quote(sys.executable)} -c 'print(\"verify ok\")'"
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="2026-04-18T05:00:00Z")
                    session["default_options"] = {
                        "allow_read": ["."],
                        "allow_verify": True,
                        "verify_command": command,
                    }
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session.get("id"),
                            "task_id": task.get("id"),
                            "tool": "run_tests",
                            "status": "interrupted",
                            "parameters": {
                                "command": command,
                                "cwd": ".",
                                "allow_verify": True,
                                "timeout": 300,
                            },
                            "result": {"command": command, "cwd": ".", "timed_out": True},
                            "summary": "interrupted verifier",
                            "error": "Interrupted before the verifier completed.",
                            "started_at": "2026-04-18T05:00:00Z",
                            "finished_at": "2026-04-18T05:00:00Z",
                        }
                    )
                    session["last_tool_call_id"] = 1
                    state["next_ids"]["work_tool_call"] = 2
                    state.setdefault("runtime_status", {})["last_native_work_step"] = {
                        "finished_at": "2026-04-18T05:00:10Z",
                        "session_id": session.get("id"),
                        "task_id": task.get("id"),
                        "command": "mew work 1 --live --allow-read . --max-steps 1",
                        "exit_code": 1,
                        "timed_out": False,
                        "outcome": "failed",
                    }
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as native_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--allow-read",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                native_runner.assert_not_called()
                with state_lock():
                    state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(session["tool_calls"][0]["recovered_by_tool_call_id"], 2)
                self.assertEqual(session["tool_calls"][1]["status"], "completed")
                self.assertEqual(session["tool_calls"][1]["result"]["exit_code"], 0)
                self.assertIn("verify ok", session["tool_calls"][1]["result"]["stdout"])
                self.assertFalse(
                    [
                        question
                        for question in state.get("questions") or []
                        if str(question.get("related_task_id")) == "1"
                    ]
                )
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "auto_retry_verification_completed")
                self.assertEqual(recovery["source_tool_call_id"], 1)
                self.assertEqual(recovery["recovered_by_tool_call_id"], 2)
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_does_not_auto_recover_verifier_behind_side_effect(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f"{shlex.quote(sys.executable)} -c 'print(\"verify ok\")'"
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="2026-04-18T05:00:00Z")
                    session["default_options"] = {
                        "allow_read": ["."],
                        "allow_write": ["."],
                        "allow_verify": True,
                        "verify_command": command,
                    }
                    session["tool_calls"].extend(
                        [
                            {
                                "id": 1,
                                "session_id": session.get("id"),
                                "task_id": task.get("id"),
                                "tool": "write_file",
                                "status": "interrupted",
                                "parameters": {
                                    "path": "target.txt",
                                    "content": "changed",
                                    "apply": True,
                                    "allow_verify": True,
                                    "verify_command": command,
                                },
                                "result": {"path": "target.txt", "written": True, "applied": True},
                                "summary": "interrupted write",
                                "error": "Interrupted after the write may have started.",
                                "started_at": "2026-04-18T05:00:00Z",
                                "finished_at": "2026-04-18T05:00:00Z",
                            },
                            {
                                "id": 2,
                                "session_id": session.get("id"),
                                "task_id": task.get("id"),
                                "tool": "run_tests",
                                "status": "interrupted",
                                "parameters": {
                                    "command": command,
                                    "cwd": ".",
                                    "allow_verify": True,
                                    "timeout": 300,
                                },
                                "result": {"command": command, "cwd": ".", "timed_out": True},
                                "summary": "interrupted verifier",
                                "error": "Interrupted before the verifier completed.",
                                "started_at": "2026-04-18T05:00:01Z",
                                "finished_at": "2026-04-18T05:00:01Z",
                            },
                        ]
                    )
                    session["last_tool_call_id"] = 2
                    state["next_ids"]["work_tool_call"] = 3
                    state.setdefault("runtime_status", {})["last_native_work_step"] = {
                        "finished_at": "2026-04-18T05:00:10Z",
                        "session_id": session.get("id"),
                        "task_id": task.get("id"),
                        "command": "mew work 1 --live --allow-read . --max-steps 1",
                        "exit_code": 1,
                        "timed_out": False,
                        "outcome": "failed",
                    }
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as native_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--allow-read",
                                ".",
                                "--allow-verify",
                                "--verify-command",
                                command,
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                native_runner.assert_not_called()
                with state_lock():
                    state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(len(session["tool_calls"]), 2)
                self.assertNotIn("recovery_status", session["tool_calls"][1])
                self.assertTrue(
                    [
                        question
                        for question in state.get("questions") or []
                        if str(question.get("related_task_id")) == "1"
                    ]
                )
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "ask_user_seeded_question")
                self.assertEqual(recovery["recovery_plan_action"], "needs_user_review")
                self.assertEqual(recovery["recovery_effect_classification"], "verify_pending")
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_auto_recovers_interrupted_safe_read_tool(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with open("target.txt", "w", encoding="utf-8") as handle:
                    handle.write("safe read recovery\n")
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="2026-04-18T05:00:00Z")
                    session["default_options"] = {"allow_read": ["."]}
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session.get("id"),
                            "task_id": task.get("id"),
                            "tool": "read_file",
                            "status": "interrupted",
                            "parameters": {"path": "target.txt", "max_chars": 50000},
                            "result": None,
                            "summary": "interrupted read",
                            "error": "Interrupted before the read completed.",
                            "started_at": "2026-04-18T05:00:00Z",
                            "finished_at": "2026-04-18T05:00:00Z",
                        }
                    )
                    session["last_tool_call_id"] = 1
                    state["next_ids"]["work_tool_call"] = 2
                    state.setdefault("runtime_status", {})["last_native_work_step"] = {
                        "finished_at": "2026-04-18T05:00:10Z",
                        "session_id": session.get("id"),
                        "task_id": task.get("id"),
                        "command": "mew work 1 --live --allow-read . --max-steps 1",
                        "exit_code": 1,
                        "timed_out": False,
                        "outcome": "failed",
                    }
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as native_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--allow-read",
                                ".",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                native_runner.assert_not_called()
                with state_lock():
                    state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["tool_calls"][0]["recovery_status"], "superseded")
                self.assertEqual(session["tool_calls"][0]["recovered_by_tool_call_id"], 2)
                self.assertEqual(session["tool_calls"][1]["tool"], "read_file")
                self.assertEqual(session["tool_calls"][1]["status"], "completed")
                self.assertIn("safe read recovery", session["tool_calls"][1]["result"]["text"])
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "auto_retry_tool_completed")
                self.assertEqual(recovery["tool"], "read_file")
                self.assertEqual(recovery["source_tool_call_id"], 1)
                self.assertEqual(recovery["recovered_by_tool_call_id"], 2)
            finally:
                os.chdir(old_cwd)

    def test_run_once_passive_now_does_not_auto_recover_safe_read_without_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with open("target.txt", "w", encoding="utf-8") as handle:
                    handle.write("safe read recovery\n")
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    mark_work_session_runtime_owned(session, event_id=99, current_time="2026-04-18T05:00:00Z")
                    session["default_options"] = {"allow_read": ["."]}
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session.get("id"),
                            "task_id": task.get("id"),
                            "tool": "read_file",
                            "status": "interrupted",
                            "parameters": {"path": "target.txt", "max_chars": 50000},
                            "result": None,
                            "summary": "interrupted read",
                            "error": "Interrupted before the read completed.",
                            "started_at": "2026-04-18T05:00:00Z",
                            "finished_at": "2026-04-18T05:00:00Z",
                        }
                    )
                    session["last_tool_call_id"] = 1
                    state["next_ids"]["work_tool_call"] = 2
                    state.setdefault("runtime_status", {})["last_native_work_step"] = {
                        "finished_at": "2026-04-18T05:00:10Z",
                        "session_id": session.get("id"),
                        "task_id": task.get("id"),
                        "command": "mew work 1 --live --allow-read . --max-steps 1",
                        "exit_code": 1,
                        "timed_out": False,
                        "outcome": "failed",
                    }
                    save_state(state)

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "passive now", "decisions": []},
                            {"summary": "passive now", "actions": []},
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as native_runner,
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--passive-now",
                                "--autonomous",
                                "--autonomy-level",
                                "act",
                                "--allow-native-advance",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                native_runner.assert_not_called()
                with state_lock():
                    state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(len(session["tool_calls"]), 1)
                self.assertNotIn("recovery_status", session["tool_calls"][0])
                self.assertTrue(
                    [
                        question
                        for question in state.get("questions") or []
                        if str(question.get("related_task_id")) == "1"
                    ]
                )
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "ask_user_seeded_question")
                self.assertEqual(recovery["recovery_plan_action"], "retry_tool")
            finally:
                os.chdir(old_cwd)

    def test_runtime_native_work_recovery_marks_missing_recovery_call_failed(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                command = f"{shlex.quote(sys.executable)} -c 'print(\"verify ok\")'"
                with state_lock():
                    state = load_state()
                    task = {
                        "id": 1,
                        "title": "Improve mew",
                        "description": "",
                        "status": "ready",
                        "kind": "coding",
                        "plans": [],
                        "runs": [],
                    }
                    state["tasks"].append(task)
                    session, _ = create_work_session(state, task)
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "session_id": session.get("id"),
                            "task_id": task.get("id"),
                            "tool": "run_tests",
                            "status": "interrupted",
                            "parameters": {"command": command, "cwd": ".", "allow_verify": True},
                            "result": {"command": command, "cwd": "."},
                            "summary": "interrupted verifier",
                            "error": "Interrupted before the verifier completed.",
                            "started_at": "then",
                            "finished_at": "then",
                        }
                    )
                    session["last_tool_call_id"] = 1
                    state["next_ids"]["work_tool_call"] = 2
                    save_state(state)

                report = run_runtime_native_work_recovery_step(
                    {
                        "session_id": 1,
                        "task_id": 1,
                        "source_tool_call_id": 1,
                        "tool_call_id": 2,
                        "tool": "run_tests",
                        "parameters": {
                            "command": command,
                            "cwd": ".",
                            "allow_verify": True,
                            "recovered_from_tool_call_id": 1,
                        },
                        "command": command,
                        "cwd": ".",
                    },
                    SimpleNamespace(allow_read=["."]),
                )

                self.assertIn("work tool result could not be recorded", report["error"])
                with state_lock():
                    state = load_state()
                source_call = state["work_sessions"][0]["tool_calls"][0]
                self.assertEqual(source_call["recovery_status"], "retry_failed")
                self.assertEqual(source_call["recovered_by_tool_call_id"], 2)
                recovery = state["runtime_status"]["last_native_work_recovery"]
                self.assertEqual(recovery["action"], "auto_retry_verification_failed")
                self.assertEqual(recovery["status"], "failed")
                self.assertIn("work tool result could not be recorded", recovery["error"])
            finally:
                os.chdir(old_cwd)

    def test_run_echo_effects_prints_runtime_effect_summary(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "journaled", "decisions": []},
                            {
                                "summary": "journaled",
                                "actions": [
                                    {
                                        "type": "send_message",
                                        "message_type": "info",
                                        "text": "journaled runtime effect",
                                    }
                                ],
                            },
                        ),
                    ),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--echo-effects", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("processed 1 event(s) reason=startup", output)
                self.assertIn("effect #1 [applied] event=#1 reason=startup actions=send_message", output)
                self.assertIn("summary=journaled", output)
                self.assertIn("outcome=journaled runtime effect", output)
            finally:
                os.chdir(old_cwd)

    def test_runtime_marks_deferred_effect_when_user_message_arrives_during_planning(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_plan_runtime_event(_state_snapshot, _event_snapshot, *args, **_kwargs):
                    with state_lock():
                        state = load_state()
                        add_event(state, "user_message", "test", {"text": "urgent"})
                        save_state(state)
                    return (
                        {"summary": "stale passive", "decisions": []},
                        {
                            "summary": "stale passive",
                            "actions": [
                                {
                                    "type": "send_message",
                                    "message_type": "info",
                                    "text": "stale passive response",
                                }
                            ],
                        },
                    )

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                ):
                    with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                with state_lock():
                    state = load_state()
                self.assertEqual(len(state["runtime_effects"]), 1)
                effect = state["runtime_effects"][0]
                self.assertEqual(effect["status"], "deferred")
                self.assertTrue(effect["deferred"])
                self.assertEqual(effect["processed_count"], 0)
                self.assertEqual(effect["action_types"], ["send_message"])
            finally:
                os.chdir(old_cwd)

    def test_runtime_focus_is_passed_to_planner_guidance(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_plan_runtime_event(_state_snapshot, _event_snapshot, *args, **_kwargs):
                    guidance = args[7]
                    self.assertIn("Immediate runtime focus:", guidance)
                    self.assertIn("Make one tiny verified change", guidance)
                    return (
                        {"summary": "focused", "decisions": []},
                        {"summary": "focused", "actions": []},
                    )

                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event),
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--focus",
                                "Make one tiny verified change",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertIn("runtime focus: Make one tiny verified change", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_runtime_notify_command_receives_new_outbox_env(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_sweep(state, *args, **kwargs):
                    add_outbox_message(state, "question", "Need a decision?", requires_reply=True)
                    return {}

                with (
                    patch("mew.runtime.sweep_agent_runs", side_effect=fake_sweep),
                    patch("mew.runtime.plan_runtime_event", return_value=({"summary": "", "decisions": []}, {"summary": "", "actions": []})),
                    patch("mew.runtime.run_command_record", return_value={"exit_code": 0, "stderr": ""}) as notify,
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--autonomous",
                                "--notify-command",
                                "notify-tool",
                                "--notify-timeout",
                                "2",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertNotIn("Need a decision?", stdout.getvalue())
                notify.assert_called_once()
                _, kwargs = notify.call_args
                self.assertEqual(kwargs["timeout"], 2.0)
                self.assertEqual(kwargs["extra_env"]["MEW_OUTBOX_TYPE"], "question")
                self.assertEqual(kwargs["extra_env"]["MEW_OUTBOX_TEXT"], "Need a decision?")
                self.assertEqual(kwargs["extra_env"]["MEW_OUTBOX_REQUIRES_REPLY"], "1")
            finally:
                os.chdir(old_cwd)

    def test_runtime_does_not_echo_or_notify_quiet_passive_info(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with (
                    patch("mew.runtime.sweep_agent_runs", return_value={}),
                    patch(
                        "mew.runtime.plan_runtime_event",
                        return_value=(
                            {"summary": "routine", "decisions": []},
                            {
                                "summary": "routine",
                                "actions": [
                                    {
                                        "type": "send_message",
                                        "message_type": "info",
                                        "text": "Routine passive progress.",
                                    }
                                ],
                            },
                        ),
                    ),
                    patch("mew.runtime.run_command_record") as notify,
                ):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(
                            [
                                "run",
                                "--once",
                                "--echo-outbox",
                                "--notify-command",
                                "notify-tool",
                                "--poll-interval",
                                "0.01",
                            ]
                        )

                self.assertEqual(code, 0)
                self.assertNotIn("Routine passive progress.", stdout.getvalue())
                notify.assert_not_called()
                with state_lock():
                    state = load_state()
                self.assertEqual(state["outbox"][0]["type"], "info")
                self.assertIsNotNone(state["outbox"][0]["read_at"])
            finally:
                os.chdir(old_cwd)

    def test_runtime_processes_pending_external_event_without_waiting_for_passive_tick(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    add_event(state, "file_change", "watch", {"path": "src/mew/runtime.py"})
                    save_state(state)

                def fake_plan_runtime_event(state_snapshot, event_snapshot, *args, **kwargs):
                    self.assertEqual(event_snapshot["type"], "file_change")
                    return (
                        {"summary": "external event", "decisions": []},
                        {"summary": "external event", "actions": []},
                    )

                with patch("mew.runtime.plan_runtime_event", side_effect=fake_plan_runtime_event):
                    with redirect_stdout(StringIO()) as stdout, redirect_stderr(StringIO()):
                        code = main(["run", "--once", "--interval", "999", "--poll-interval", "0.01"])

                self.assertEqual(code, 0)
                self.assertIn("reason=external_event", stdout.getvalue())
                with state_lock():
                    state = load_state()
                self.assertIsNotNone(state["inbox"][0]["processed_at"])
            finally:
                os.chdir(old_cwd)

    def test_external_events_use_resident_ai_when_available(self):
        state = default_state()
        event = add_event(state, "github_webhook", "test", {"ref": "main"})

        with patch(
            "mew.agent.call_model_json",
            return_value={"summary": "handled webhook", "decisions": []},
        ) as call_model:
            plan = think_phase(
                state,
                event,
                "now",
                model_auth={"path": "auth.json"},
                model="model",
                base_url="base",
                timeout=1,
                ai_ticks=False,
                allow_task_execution=False,
                guidance="",
                policy="",
            )

        self.assertTrue(should_use_ai_for_event(event, "external_event", ai_ticks=False))
        call_model.assert_called_once()
        self.assertEqual(plan["summary"], "handled webhook")

    def test_think_phase_retries_transient_model_errors(self):
        state = default_state()
        event = add_event(state, "github_webhook", "test", {"ref": "main"})

        with patch(
            "mew.agent.call_model_json",
            side_effect=[
                ModelBackendError("HTTP 529 overloaded"),
                {"summary": "retried successfully", "decisions": []},
            ],
        ) as call_model:
            with patch("mew.agent.time.sleep") as sleep:
                with patch("mew.agent.append_log") as append_log:
                    plan = think_phase(
                        state,
                        event,
                        "now",
                        model_auth={"path": "auth.json"},
                        model="model",
                        base_url="base",
                        timeout=1,
                        ai_ticks=False,
                        allow_task_execution=False,
                        guidance="",
                        policy="",
                        log_phases=False,
                    )

        self.assertEqual(call_model.call_count, 2)
        sleep.assert_called_once_with(0.25)
        append_log.assert_not_called()
        self.assertEqual(plan["summary"], "retried successfully")

    def test_think_phase_retries_malformed_model_json_once(self):
        state = default_state()
        event = add_event(state, "github_webhook", "test", {"ref": "main"})

        with patch(
            "mew.agent.call_model_json",
            side_effect=[
                ModelBackendError("failed to parse JSON plan: Expecting ',' delimiter"),
                {"summary": "retried successfully", "decisions": []},
            ],
        ) as call_model:
            with patch("mew.agent.time.sleep") as sleep:
                plan = think_phase(
                    state,
                    event,
                    "now",
                    model_auth={"path": "auth.json"},
                    model="model",
                    base_url="base",
                    timeout=1,
                    ai_ticks=False,
                    allow_task_execution=False,
                    guidance="",
                    policy="",
                    log_phases=False,
                )

        self.assertEqual(call_model.call_count, 2)
        sleep.assert_called_once_with(0.25)
        self.assertEqual(plan["summary"], "retried successfully")


if __name__ == "__main__":
    unittest.main()
