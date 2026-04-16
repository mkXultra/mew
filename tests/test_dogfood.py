import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from mew.config import LOG_FILE, MODEL_TRACE_FILE, STATE_DIR, STATE_FILE
from mew.dogfood import (
    active_agent_run_ids,
    agent_reflex_sweep_timeout,
    build_dogfood_report,
    build_runtime_command,
    copy_source_workspace,
    format_dogfood_loop_report,
    format_dogfood_report,
    injected_message_status,
    prepopulate_project_snapshot,
    prepare_dogfood_workspace,
    queued_message_event_id,
    run_dogfood,
    run_dogfood_loop,
    run_post_wait_agent_reflex,
    seed_ready_coding_task,
    suppress_processed_injected_dropped_threads,
    tail_lines,
    wait_for_active_agent_runs,
)
from mew.state import add_event, add_outbox_message, default_state


class DogfoodTests(unittest.TestCase):
    def test_prepare_workspace_creates_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, created = prepare_dogfood_workspace(Path(tmp) / "dog")

            self.assertFalse(created)
            self.assertTrue((workspace / "README.md").exists())

    def test_build_runtime_command_keeps_ai_optional(self):
        args = SimpleNamespace(
            interval=3,
            poll_interval=0.2,
            autonomy_level="act",
            model_timeout=45,
            ai=False,
            auth=None,
            model_backend="codex",
            model="",
            base_url="",
            allow_write=False,
            allow_verify=False,
            execute_tasks=False,
            allow_agent_run=False,
            agent_stale_minutes=None,
            agent_result_timeout=None,
            agent_start_timeout=None,
            review_model=None,
            verify_command="",
            verify_interval_minutes=0.05,
        )

        command = build_runtime_command(args, Path("/tmp/work"))

        self.assertIn("--autonomous", command)
        self.assertNotIn("--ai", command)

    def test_build_runtime_command_resolves_relative_auth_before_workspace_cwd(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                args = SimpleNamespace(
                    interval=3,
                    poll_interval=0.2,
                    autonomy_level="act",
                    model_timeout=45,
                    ai=True,
                    auth="auth.json",
                    model_backend="codex",
                    model="",
                    base_url="",
                    allow_write=False,
                    allow_verify=False,
                    execute_tasks=False,
                    allow_agent_run=False,
                    agent_stale_minutes=None,
                    agent_result_timeout=None,
                    agent_start_timeout=None,
                    review_model=None,
                    verify_command="",
                    verify_interval_minutes=0.05,
                )

                command = build_runtime_command(args, Path("/tmp/work"))

                self.assertEqual(command[command.index("--auth") + 1], str((Path(tmp) / "auth.json").resolve()))
            finally:
                os.chdir(old_cwd)

    def test_build_runtime_command_can_enable_programmer_gates(self):
        args = SimpleNamespace(
            interval=3,
            poll_interval=0.2,
            autonomy_level="act",
            model_timeout=45,
            ai=False,
            auth=None,
            model_backend="codex",
            model="",
            base_url="",
            allow_write=False,
            allow_verify=False,
            execute_tasks=True,
            allow_agent_run=True,
            agent_stale_minutes=3.0,
            agent_result_timeout=4.0,
            agent_start_timeout=5.0,
            review_model="codex-ultra",
            verify_command="",
            verify_interval_minutes=0.05,
            trace_model=True,
        )

        command = build_runtime_command(args, Path("/tmp/work"))

        self.assertIn("--execute-tasks", command)
        self.assertIn("--allow-agent-run", command)
        self.assertEqual(command[command.index("--agent-stale-minutes") + 1], "3.0")
        self.assertEqual(command[command.index("--agent-result-timeout") + 1], "4.0")
        self.assertEqual(command[command.index("--agent-start-timeout") + 1], "5.0")
        self.assertEqual(command[command.index("--review-model") + 1], "codex-ultra")
        self.assertIn("--trace-model", command)

    def test_copy_source_workspace_skips_sensitive_state_and_large_files(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as workspace_tmp:
            source = Path(source_tmp)
            workspace = Path(workspace_tmp)
            (source / "src").mkdir()
            (source / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (source / "auth.json").write_text("secret", encoding="utf-8")
            (source / ".mew").mkdir()
            (source / ".mew" / "state.json").write_text("{}", encoding="utf-8")
            (source / "large.txt").write_text("x" * 200, encoding="utf-8")

            result = copy_source_workspace(source, workspace, max_file_bytes=100)

            self.assertEqual(result["copied_files"], 1)
            self.assertTrue((workspace / "src" / "app.py").exists())
            self.assertFalse((workspace / "auth.json").exists())
            self.assertFalse((workspace / ".mew").exists())
            self.assertFalse((workspace / "large.txt").exists())

    def test_build_report_summarizes_state_and_runtime_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".mew").mkdir()
            state = default_state()
            state["runtime_status"]["last_cycle_reason"] = "passive_tick"
            state["runtime_status"]["last_cycle_duration_seconds"] = 1.25
            state["runtime_status"]["last_processed_count"] = 1
            event = add_event(state, "passive_tick", "runtime")
            event["processed_at"] = "done"
            event["decision_plan"] = {
                "summary": "x",
                "schema_issues": [{"level": "warning", "path": "decisions[0].type", "message": "unsupported"}],
            }
            add_outbox_message(state, "info", "hello", event_id=event["id"])
            read_message = add_outbox_message(
                state,
                "info",
                f"Read file {workspace / 'README.md'} and saved the observation to memory.",
                event_id=event["id"],
            )
            read_message["read_at"] = "read"
            add_outbox_message(
                state,
                "info",
                f"Skipped repeated read_file for {workspace / 'README.md'}; recent context already contains that inspection.",
                event_id=event["id"],
            )
            state["thought_journal"].append(
                {
                    "id": 1,
                    "event_id": event["id"],
                    "event_type": "passive_tick",
                    "summary": "Inspected workspace.",
                    "actions": [{"type": "inspect_dir", "path": str(workspace)}],
                    "counts": {"actions": 1, "messages": 1},
                    "open_threads": [],
                    "resolved_threads": [],
                    "dropped_threads": [],
                }
            )
            state["agent_runs"].append(
                {
                    "id": 1,
                    "task_id": 1,
                    "plan_id": 2,
                    "purpose": "implementation",
                    "status": "running",
                    "model": "codex-ultra",
                    "external_pid": 123,
                }
            )
            state["agent_runs"].append(
                {
                    "id": 2,
                    "task_id": 1,
                    "plan_id": 2,
                    "purpose": "review",
                    "status": "completed",
                    "followup_processed_at": "done",
                    "followup_task_id": 3,
                }
            )
            state["memory"]["deep"]["project_snapshot"] = {
                "updated_at": "now",
                "project_types": ["python"],
                "roots": [],
                "files": [],
                "searches": [],
                "package": {"name": "mew"},
            }
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            (workspace / LOG_FILE).write_text(
                "- now: think_phase codex ok event=1\n- now: act_phase codex ok event=1\n",
                encoding="utf-8",
            )
            (workspace / MODEL_TRACE_FILE).write_text(
                json.dumps(
                    {
                        "at": "now",
                        "phase": "think",
                        "event_id": event["id"],
                        "event_type": event["type"],
                        "status": "ok",
                        "backend": "codex",
                        "model": "test",
                        "prompt_chars": 12,
                        "prompt_sha256": "abc",
                        "prompt": "hidden in report",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            runtime_out_path = workspace / STATE_DIR / "dogfood-runtime.out"
            runtime_out_path.write_text(
                "mew runtime started pid=1\nprocessed 1 event(s) reason=startup\nmew runtime stopped\n",
                encoding="utf-8",
            )

            report = build_dogfood_report(workspace, ["mew", "run"], 0, 1.5)
            report["agent_reflex_results"] = [
                {
                    "phase": "review_wait",
                    "agent_wait_results": [
                        {
                            "run_id": 9,
                            "exit_code": 1,
                            "timed_out": True,
                            "stdout_tail": [],
                            "stderr_tail": ["wait timed out"],
                        }
                    ],
                }
            ]
            text = format_dogfood_report(report)

            self.assertEqual(report["events"]["processed"], 1)
            self.assertEqual(report["model_phases"]["think_ok"], 1)
            self.assertEqual(report["model_traces"]["total"], 1)
            self.assertNotIn("prompt", report["model_traces"]["latest"][0])
            self.assertEqual(report["runtime_status"]["last_cycle_reason"], "passive_tick")
            self.assertEqual(report["actions"], {"inspect_dir": 1})
            self.assertEqual(report["read_inspection"]["read_progress_messages"], 1)
            self.assertEqual(report["read_inspection"]["read_progress_unread"], 0)
            self.assertEqual(report["read_inspection"]["repeated_read_skips"], 1)
            self.assertEqual(report["read_inspection"]["repeated_read_skips_unread"], 0)
            self.assertEqual(report["agent_runs"]["total"], 2)
            self.assertEqual(report["agent_runs"]["by_status"], {"completed": 1, "running": 1})
            self.assertEqual(report["programmer_loop"]["implementation_runs"], 1)
            self.assertEqual(report["programmer_loop"]["review_runs"], 1)
            self.assertEqual(report["programmer_loop"]["reviews_with_followup_processed"], 1)
            self.assertEqual(report["programmer_loop"]["followup_task_ids"], [3])
            self.assertEqual(report["plan_schema_issues"]["count"], 1)
            self.assertEqual(report["project_snapshot"]["project_types"], ["python"])
            self.assertEqual(report["active_dropped_threads"]["thought_count"], 0)
            self.assertIn("Recent activity", text)
            self.assertIn("model_traces", text)
            self.assertIn("Project snapshot", text)
            self.assertIn("runtime_cycle:", text)
            self.assertIn("read_inspection:", text)
            self.assertIn("agent_runs:", text)
            self.assertIn("programmer_loop:", text)
            self.assertIn("agent_reflex_results: 1", text)
            self.assertIn("run #9 exit=1 timed_out=True", text)
            self.assertEqual(len(report["runtime_output_tail"]), 3)
            self.assertIn("Runtime output (last lines)", text)
            self.assertIn("mew runtime stopped", text)
            self.assertIn("plan_schema_issues", text)

    def test_injected_message_status_reports_unprocessed_messages(self):
        state = default_state()
        processed = add_event(state, "user_message", "user", {"text": "handled"})
        processed["processed_at"] = "done"
        add_event(state, "user_message", "user", {"text": "pending"})

        status = injected_message_status(state, ["handled", "pending", "missing"])

        self.assertEqual(status["total"], 3)
        self.assertEqual(status["matched"], 2)
        self.assertEqual(status["processed"], 1)
        self.assertEqual(status["unprocessed"], 2)
        self.assertEqual(status["unmatched"], ["missing"])

    def test_injected_message_status_prefers_event_ids(self):
        state = default_state()
        old = add_event(state, "user_message", "user", {"text": "same"})
        old["processed_at"] = "done"
        new = add_event(state, "user_message", "user", {"text": "same"})

        status = injected_message_status(state, ["same"], event_ids=[new["id"]])

        self.assertEqual(status["matched"], 1)
        self.assertEqual(status["processed"], 0)
        self.assertEqual(status["unprocessed"], 1)
        self.assertEqual(status["events"][0]["id"], new["id"])

    def test_queued_message_event_id_parses_message_output(self):
        self.assertEqual(queued_message_event_id("queued message event #42\n"), 42)
        self.assertIsNone(queued_message_event_id("no id"))

    def test_format_dogfood_report_warns_for_unprocessed_injected_messages(self):
        report = {
            "generated_at": "now",
            "workspace": "/tmp/dog",
            "exit_code": 0,
            "duration_seconds": 1.0,
            "events": {"processed": 1, "total": 2, "by_type": {"startup": 1, "user_message": 1}},
            "runtime_status": {},
            "model_phases": {},
            "outbox": {"total": 0, "unread": 0, "by_type": {}},
            "actions": {},
            "read_inspection": {},
            "tasks": {},
            "agent_runs": {},
            "programmer_loop": {},
            "verification_runs": 0,
            "write_runs": 0,
            "injected_messages": {"total": 1, "processed": 0, "unprocessed": 1},
            "model_enabled": True,
            "next_move": "inspect",
        }

        text = format_dogfood_report(report)

        self.assertIn("injected_messages: processed=0/1 unprocessed=1", text)
        self.assertIn("warning: injected user message(s) were left unprocessed", text)
        self.assertIn("model_enabled: True", text)

    def test_suppress_processed_injected_dropped_threads(self):
        report = {
            "injected_messages": {
                "events": [
                    {"text": "handled request", "processed": True},
                    {"text": "pending request", "processed": False},
                ]
            },
            "active_dropped_threads": {
                "thought_count": 2,
                "latest": [
                    "User request context: handled request",
                    "User request context: pending request",
                ],
                "thought_id": 7,
            },
        }

        suppress_processed_injected_dropped_threads(report)

        self.assertEqual(report["active_dropped_threads"]["thought_count"], 1)
        self.assertEqual(report["active_dropped_threads"]["latest"], ["User request context: pending request"])

    def test_prepopulate_project_snapshot_writes_dogfood_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "src").mkdir()
            (workspace / "tests").mkdir()
            (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
            (workspace / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

            report = prepopulate_project_snapshot(workspace)
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))

            self.assertEqual(len(report["read_files"]), 2)
            self.assertEqual(state["memory"]["deep"]["project_snapshot"]["package"]["name"], "demo")
            self.assertEqual(state["dogfood"]["pre_snapshot"]["path"], str(workspace.resolve()))

    def test_seed_ready_coding_task_creates_dispatchable_planned_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)

            summary = seed_ready_coding_task(workspace)
            second = seed_ready_coding_task(workspace)
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))

            self.assertEqual(summary["status"], "ready")
            self.assertTrue(summary["auto_execute"])
            self.assertEqual(second["id"], summary["id"])
            self.assertEqual(len(state["tasks"]), 1)
            task = state["tasks"][0]
            self.assertEqual(task["kind"], "coding")
            self.assertEqual(task["status"], "ready")
            self.assertTrue(task["auto_execute"])
            self.assertGreaterEqual(len(task["plans"]), 1)
            self.assertEqual(task["latest_plan_id"], second["plan_id"])

    def test_seed_ready_coding_task_clears_stale_shell_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            seed_ready_coding_task(workspace)
            state_path = workspace / STATE_FILE
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["tasks"][0]["command"] = "echo stale"
            state["tasks"][0]["agent_run_id"] = 99
            state_path.write_text(json.dumps(state), encoding="utf-8")

            seed_ready_coding_task(workspace)
            state = json.loads(state_path.read_text(encoding="utf-8"))

            self.assertEqual(state["tasks"][0]["command"], "")
            self.assertIsNone(state["tasks"][0]["agent_run_id"])

    def test_seed_ready_coding_task_preserves_active_agent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            seed_ready_coding_task(workspace)
            state_path = workspace / STATE_FILE
            state = json.loads(state_path.read_text(encoding="utf-8"))
            task = state["tasks"][0]
            initial_plan_count = len(task["plans"])
            state["agent_runs"].append(
                {
                    "id": 7,
                    "task_id": task["id"],
                    "plan_id": task["latest_plan_id"],
                    "purpose": "implementation",
                    "status": "running",
                }
            )
            task["status"] = "running"
            task["agent_run_id"] = 7
            state_path.write_text(json.dumps(state), encoding="utf-8")

            summary = seed_ready_coding_task(workspace)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            task = state["tasks"][0]

            self.assertEqual(summary["active_run_id"], 7)
            self.assertEqual(task["status"], "running")
            self.assertEqual(task["agent_run_id"], 7)
            self.assertEqual(len(task["plans"]), initial_plan_count)

    def test_wait_for_active_agent_runs_invokes_agent_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            state["agent_runs"].append({"id": 8, "status": "completed"})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            class Result:
                returncode = 0
                stdout = "waited\n"
                stderr = ""

            collect = {"command": ["mew"], "exit_code": 0, "stdout": "line1\nline2\n", "stderr": ""}
            with patch(
                "mew.dogfood.run_command",
                return_value=collect,
            ) as collector:
                with patch("mew.dogfood.subprocess.run", return_value=Result()) as waiter:
                    results = wait_for_active_agent_runs(workspace, 5.0, env={"PYTHONPATH": "src"})

            self.assertEqual(active_agent_run_ids(workspace), [7])
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["run_id"], 7)
            wait_command = waiter.call_args.args[0]
            self.assertEqual(wait_command[:3], ["ai-cli", "wait", "123"])
            self.assertIn("--timeout", wait_command)
            collect_command = collector.call_args.args[0]
            self.assertEqual(collect_command[2:5], ["mew", "agent", "result"])
            self.assertIn("7", collect_command)
            self.assertEqual(results[0]["stdout_tail"], ["waited"])
            self.assertEqual(results[0]["collect_result"]["stdout_tail"], ["line1", "line2"])

    def test_tail_lines_clips_long_report_lines(self):
        text = "short\n" + ("x" * 1200)

        self.assertEqual(tail_lines(text, limit=2)[0], "short")
        self.assertTrue(tail_lines(text, limit=2)[1].endswith("...<truncated>"))
        self.assertLessEqual(len(tail_lines(text, limit=2)[1]), 1014)

    def test_wait_for_active_agent_runs_timeout_leaves_state_uncollected(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            with patch("mew.dogfood.subprocess.run", side_effect=subprocess.TimeoutExpired(["ai-cli"], 1)):
                with patch("mew.dogfood.run_command") as collector:
                    results = wait_for_active_agent_runs(workspace, 0.01)

            self.assertTrue(results[0]["timed_out"])
            collector.assert_not_called()
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))
            self.assertEqual(state["agent_runs"][0]["status"], "running")

    def test_wait_for_active_agent_runs_marks_ai_cli_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / STATE_DIR).mkdir()
            state = default_state()
            state["agent_runs"].append({"id": 7, "status": "running", "external_pid": 123})
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")

            class Result:
                returncode = 1
                stdout = ""
                stderr = "Timed out after 180 seconds waiting for processes"

            with patch("mew.dogfood.subprocess.run", return_value=Result()):
                with patch("mew.dogfood.run_command") as collector:
                    results = wait_for_active_agent_runs(workspace, 5.0)

            self.assertTrue(results[0]["timed_out"])
            collector.assert_not_called()

    def test_post_wait_agent_reflex_runs_sweeps_around_review_wait(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            args = SimpleNamespace(
                allow_agent_run=True,
                wait_agent_runs=5.0,
                review_model="codex-ultra",
                agent_stale_minutes=3.0,
                agent_result_timeout=4.0,
                agent_start_timeout=6.0,
            )
            command_result = {"command": ["mew"], "exit_code": 0, "stdout": "swept\n", "stderr": ""}
            with patch("mew.dogfood.run_command", return_value=command_result) as runner:
                with patch(
                    "mew.dogfood.wait_for_active_agent_runs",
                    return_value=[{"run_id": 9, "exit_code": 0}],
                ) as waiter:
                    results = run_post_wait_agent_reflex(workspace, args, env={"PYTHONPATH": "src"})

            self.assertEqual([result["phase"] for result in results], ["post_wait_sweep", "review_wait", "post_review_sweep"])
            self.assertEqual(waiter.call_count, 1)
            self.assertEqual(runner.call_count, 2)
            first_command = runner.call_args_list[0].args[0]
            self.assertEqual(first_command[:5], [sys.executable, "-m", "mew", "agent", "sweep"])
            self.assertIn("--start-reviews", first_command)
            self.assertEqual(first_command[first_command.index("--agent-model") + 1], "codex-ultra")
            self.assertEqual(first_command[first_command.index("--stale-minutes") + 1], "3.0")
            self.assertEqual(first_command[first_command.index("--agent-result-timeout") + 1], "4.0")
            self.assertEqual(first_command[first_command.index("--agent-start-timeout") + 1], "6.0")
            self.assertEqual(runner.call_args_list[0].kwargs["timeout"], 60.0)

    def test_agent_reflex_sweep_timeout_honors_large_agent_timeouts(self):
        args = SimpleNamespace(agent_result_timeout=90.0, agent_start_timeout=45.0)

        self.assertEqual(agent_reflex_sweep_timeout(args), 165.0)

    def test_run_dogfood_skips_cleanup_when_agent_run_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "dog"
            workspace.mkdir()
            args = SimpleNamespace(
                workspace=None,
                source_workspace=None,
                pre_snapshot=False,
                seed_ready_coding_task=False,
                cleanup=True,
            )
            report = {"agent_runs": {"by_status": {"running": 1}}, "kept": False}

            with patch("mew.dogfood.prepare_dogfood_workspace", return_value=(workspace, True)):
                with patch("mew.dogfood._run_dogfood_in_workspace", return_value=report):
                    result = run_dogfood(args)

            self.assertTrue(workspace.exists())
            self.assertTrue(result["kept"])
            self.assertEqual(result["cleanup_skipped_reason"], "active_agent_runs")

    def test_run_dogfood_loop_keeps_workspace_on_exception_with_active_agent_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "dog"
            workspace.mkdir()
            args = SimpleNamespace(
                workspace=None,
                source_workspace=None,
                pre_snapshot=False,
                seed_ready_coding_task=False,
                cleanup=True,
                cycles=2,
                cycle_gap=0,
            )
            report = {"agent_runs": {"by_status": {"running": 1}}, "kept": False}

            with patch("mew.dogfood.prepare_dogfood_workspace", return_value=(workspace, True)):
                with patch("mew.dogfood._run_dogfood_in_workspace", side_effect=[report, RuntimeError("boom")]):
                    with self.assertRaises(RuntimeError):
                        run_dogfood_loop(args)

            self.assertTrue(workspace.exists())

    def test_format_dogfood_loop_report_summarizes_cycles(self):
        text = format_dogfood_loop_report(
            {
                "generated_at": "now",
                "workspace": "/tmp/dog",
                "cycle_count": 2,
                "exit_codes": [0, 0],
                "final_events": {"processed": 3, "total": 3},
                "final_model_phases": {"think_ok": 2, "act_ok": 2},
                "final_runtime_status": {
                    "last_cycle_reason": "passive_tick",
                    "last_cycle_duration_seconds": 1.2,
                    "last_processed_count": 3,
                },
                "final_plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                "final_agent_runs": {"total": 1, "by_status": {"running": 1}},
                "final_dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                "final_active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                "final_next_move": "keep going",
                "final_project_snapshot": {"updated_at": "now", "project_types": ["python"]},
                "cycles": [
                    {
                        "cycle": 1,
                        "exit_code": 0,
                        "duration_seconds": 1.2,
                        "events": {"processed": 1, "total": 1},
                        "model_phases": {"think_ok": 1, "act_ok": 1},
                        "dropped_threads": {"thought_count": 0, "latest": []},
                        "active_dropped_threads": {"thought_count": 0, "latest": []},
                        "plan_schema_issues": {"count": 0, "by_level": {}, "latest": []},
                        "agent_runs": {"total": 0},
                        "next_move": "cycle one",
                    },
                    {
                        "cycle": 2,
                        "exit_code": 0,
                        "duration_seconds": 1.4,
                        "events": {"processed": 3, "total": 3},
                        "model_phases": {"think_ok": 2, "act_ok": 2},
                        "dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                        "active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                        "plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                        "agent_runs": {"total": 1},
                        "agent_wait_results": [{"run_id": 1, "exit_code": 0, "stdout_tail": ["done"]}],
                        "next_move": "keep going",
                    },
                ],
            }
        )

        self.assertIn("cycles: 2", text)
        self.assertIn("Cycle summaries", text)
        self.assertIn("final_dropped_threads", text)
        self.assertIn("final_active_dropped_threads", text)
        self.assertIn("dropped_threads=1", text)
        self.assertIn("active_dropped_threads=1", text)
        self.assertIn("schema_issues=1", text)
        self.assertIn("final_plan_schema_issues", text)
        self.assertIn("final_agent_runs", text)
        self.assertIn("agent_runs=1", text)
        self.assertIn("agent_waits=1", text)
        self.assertIn("wait run #1", text)
        self.assertIn("final_runtime_cycle", text)
        self.assertIn("Final project snapshot", text)
        self.assertIn("Final next useful move: keep going", text)


if __name__ == "__main__":
    unittest.main()
