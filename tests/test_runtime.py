import os
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
    compact_agent_reflex_report,
    guidance_with_runtime_focus,
    run_runtime_post_run_pipeline,
    should_defer_commit_for_user_message,
)
from mew.state import add_event, add_outbox_message, default_state, load_state, save_state, state_lock


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
