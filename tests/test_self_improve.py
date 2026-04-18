import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.cli import main
from mew.agent_runs import sync_task_with_agent_run
from mew.programmer import create_implementation_run_from_plan
from mew.self_improve import (
    build_self_improve_description,
    create_self_improve_task,
    ensure_self_improve_plan,
)
from mew.state import default_state, load_state
from mew.timeutil import now_iso


class SelfImproveTests(unittest.TestCase):
    def test_create_self_improve_task_and_plan(self):
        state = default_state()

        task, created = create_self_improve_task(state, focus="Improve next command", ready=True)
        plan, plan_created = ensure_self_improve_plan(state, task)

        self.assertTrue(created)
        self.assertTrue(plan_created)
        self.assertEqual(task["status"], "ready")
        self.assertEqual(task["latest_plan_id"], plan["id"])
        self.assertIn("Improve next command", task["description"])

    def test_self_improve_description_prioritizes_recent_commits(self):
        state = default_state()

        with patch("mew.self_improve.recent_git_commits", return_value="abc123 Fix latest thing"):
            description = build_self_improve_description(state, focus="Pick next")

        self.assertLess(
            description.index("Recently completed git commits"),
            description.index("Current coding focus:"),
        )
        self.assertIn("Do not repeat these topics", description)
        self.assertIn("abc123 Fix latest thing", description)

    def test_self_improve_description_uses_coding_focus(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 20,
                "title": "Research grants",
                "kind": "research",
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
                "created_at": "t",
                "updated_at": "t",
            }
        )

        with patch("mew.self_improve.recent_git_commits", return_value=""):
            description = build_self_improve_description(state, focus="Pick next")

        self.assertIn("Current coding focus:", description)
        self.assertIn("Mew focus (coding)", description)
        self.assertNotIn("Research grants", description)

    def test_self_improve_description_default_focus_uses_coding_next_move(self):
        state = default_state()
        state["tasks"].append(
            {
                "id": 20,
                "title": "Research grants",
                "kind": "research",
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
                "created_at": "t",
                "updated_at": "t",
            }
        )

        with patch("mew.self_improve.recent_git_commits", return_value=""):
            description = build_self_improve_description(state)

        self.assertIn("Focus:\nstart a native self-improvement session", description)
        self.assertNotIn("spend 10 minutes researching", description)

    def test_self_improve_reuses_open_task(self):
        state = default_state()

        first, created = create_self_improve_task(state)
        second, reused_created = create_self_improve_task(state)

        self.assertTrue(created)
        self.assertFalse(reused_created)
        self.assertEqual(first["id"], second["id"])

    def test_self_improve_replans_when_reused_task_changes_focus(self):
        state = default_state()

        task, created = create_self_improve_task(state, focus="First focus")
        first_plan, plan_created = ensure_self_improve_plan(state, task)
        task, reused_created = create_self_improve_task(state, focus="Second focus")
        second_plan, second_plan_created = ensure_self_improve_plan(state, task)

        self.assertTrue(created)
        self.assertTrue(plan_created)
        self.assertFalse(reused_created)
        self.assertTrue(second_plan_created)
        self.assertNotEqual(first_plan["id"], second_plan["id"])
        self.assertIn("Second focus", second_plan["implementation_prompt"])

    def test_self_improve_replans_after_dispatched_plan(self):
        state = default_state()

        task, _ = create_self_improve_task(state, focus="First cycle")
        first_plan, _ = ensure_self_improve_plan(state, task)
        create_implementation_run_from_plan(state, task, first_plan, dry_run=True)
        second_plan, second_plan_created = ensure_self_improve_plan(state, task)

        self.assertEqual(first_plan["status"], "dry_run")
        self.assertTrue(second_plan_created)
        self.assertNotEqual(first_plan["id"], second_plan["id"])
        self.assertEqual(second_plan["status"], "planned")

    def test_cli_self_improve_help_describes_native_work_flow(self):
        with redirect_stdout(StringIO()) as stdout:
            with self.assertRaises(SystemExit) as raised:
                main(["self-improve", "--help"])

        self.assertEqual(raised.exception.code, 0)
        output = stdout.getvalue()
        self.assertIn("Create or continue a mew self-improvement task.", output)
        self.assertIn("native mew work task without a programmer plan", output)
        self.assertIn("Native work-session flow:", output)
        self.assertIn("mew self-improve --start-session --focus", output)
        self.assertIn("mew work <task-id> --live --allow-read . --max-steps 1", output)
        self.assertIn("mew work <task-id> --follow --quiet --allow-read . --max-steps 3", output)
        self.assertIn("print generated implementation and review prompts", output)
        self.assertIn("prepare native mew work instead of a programmer-", output)
        self.assertIn("plan/ai-cli dispatch", output)

    def test_cli_self_improve_dry_run_dispatch(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "self-improve",
                            "--focus",
                            "Add a tiny improvement",
                            "--ready",
                            "--auto-execute",
                            "--dispatch",
                            "--dry-run",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("created dry-run self-improve run #1 from plan #1", stdout.getvalue())
                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertEqual(len(state["agent_runs"]), 1)
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_prompt_prints_generated_prompts(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["self-improve", "--focus", "Show generated prompts", "--prompt"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("created #1 [todo/normal/coding] Improve mew itself", output)
                self.assertIn("created plan #1", output)
                self.assertIn("implementation_prompt:", output)
                self.assertIn("Show generated prompts", output)
                self.assertIn("review_prompt:", output)
                state = load_state()
                self.assertEqual(state["tasks"][0]["latest_plan_id"], 1)
                self.assertEqual(state["agent_runs"], [])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_prompt_requires_plan_and_non_cycle(self):
        old_cwd = os.getcwd()
        cases = (
            (["--no-plan", "--prompt"], "--prompt requires a programmer plan"),
            (["--cycle", "--prompt"], "--prompt cannot be combined with --cycle"),
        )
        for extra_args, expected in cases:
            with self.subTest(extra_args=extra_args):
                with tempfile.TemporaryDirectory() as tmp:
                    os.chdir(tmp)
                    try:
                        with redirect_stderr(StringIO()) as stderr:
                            code = main(["self-improve", *extra_args])

                        self.assertEqual(code, 1)
                        self.assertIn(expected, stderr.getvalue())
                        state = load_state()
                        self.assertEqual(state["tasks"], [])
                        self.assertEqual(state["agent_runs"], [])
                    finally:
                        os.chdir(old_cwd)

    def test_cli_self_improve_native_skips_programmer_plan(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["self-improve", "--native", "--focus", "Use native work"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("start session: mew work 1 --start-session", output)
                self.assertIn(f"work cwd: {Path(tmp).resolve()}", output)
                self.assertIn("continue: mew work 1 --live --allow-read . --max-steps 1", output)
                self.assertIn("follow: mew work 1 --follow --quiet --allow-read . --max-steps 3", output)
                self.assertIn("resume: mew work 1 --session --resume --allow-read .", output)
                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertEqual(state["tasks"][0]["latest_plan_id"], None)
                self.assertEqual(state["tasks"][0]["plans"], [])
                self.assertEqual(len(state["agent_runs"]), 0)
                self.assertEqual(state["work_sessions"], [])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_native_rejects_dispatch(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["self-improve", "--native", "--dispatch"])

                self.assertEqual(code, 1)
                self.assertIn("--native/--start-session cannot be combined with --cycle or --dispatch", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_native_rejects_cycle(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stderr(StringIO()) as stderr:
                    code = main(["self-improve", "--native", "--cycle", "--dry-run"])

                self.assertEqual(code, 1)
                self.assertIn("--native/--start-session cannot be combined with --cycle or --dispatch", stderr.getvalue())
                state = load_state()
                self.assertEqual(state["tasks"], [])
                self.assertEqual(state["agent_runs"], [])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_native_rejects_prompt(self):
        old_cwd = os.getcwd()
        cases = (
            ["--native", "--prompt"],
            ["--start-session", "--prompt"],
        )
        for extra_args in cases:
            with self.subTest(extra_args=extra_args):
                with tempfile.TemporaryDirectory() as tmp:
                    os.chdir(tmp)
                    try:
                        with redirect_stderr(StringIO()) as stderr:
                            code = main(["self-improve", *extra_args])

                        self.assertEqual(code, 1)
                        self.assertIn(
                            "--native/--start-session cannot be combined with --prompt",
                            stderr.getvalue(),
                        )
                        state = load_state()
                        self.assertEqual(state["tasks"], [])
                        self.assertEqual(state["agent_runs"], [])
                        self.assertEqual(state["work_sessions"], [])
                    finally:
                        os.chdir(old_cwd)

    def test_cli_self_improve_start_session_rejects_dispatch_and_cycle(self):
        old_cwd = os.getcwd()
        cases = (
            ["--dispatch"],
            ["--cycle", "--dry-run"],
        )
        for extra_args in cases:
            with self.subTest(extra_args=extra_args):
                with tempfile.TemporaryDirectory() as tmp:
                    os.chdir(tmp)
                    try:
                        with redirect_stderr(StringIO()) as stderr:
                            code = main(["self-improve", "--start-session", *extra_args])

                        self.assertEqual(code, 1)
                        self.assertIn(
                            "--native/--start-session cannot be combined with --cycle or --dispatch",
                            stderr.getvalue(),
                        )
                        state = load_state()
                        self.assertEqual(state["tasks"], [])
                        self.assertEqual(state["agent_runs"], [])
                        self.assertEqual(state["work_sessions"], [])
                    finally:
                        os.chdir(old_cwd)

    def test_cli_self_improve_start_session_uses_native_work(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["self-improve", "--start-session", "--focus", "Start native work"])

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("started work session #1", output)
                self.assertNotIn("start session: mew work 1 --start-session", output)
                self.assertIn(f"work cwd: {Path(tmp).resolve()}", output)
                self.assertIn("continue: mew work 1 --live --allow-read . --max-steps 1", output)
                self.assertIn("follow: mew work 1 --follow --quiet --allow-read . --max-steps 3", output)
                self.assertIn("resume: mew work 1 --session --resume --allow-read .", output)
                state = load_state()
                self.assertEqual(state["tasks"][0]["plans"], [])
                self.assertEqual(state["work_sessions"][0]["task_id"], 1)
                self.assertEqual(state["work_sessions"][0]["status"], "active")
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_start_session_controls_use_task_cwd_read_root(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as workdir:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "self-improve",
                            "--start-session",
                            "--focus",
                            "Start native work elsewhere",
                            "--cwd",
                            workdir,
                        ]
                    )

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                resolved = str(Path(workdir).resolve())
                self.assertIn(f"work cwd: {resolved}", output)
                self.assertIn(f"continue: mew work 1 --live --allow-read {resolved} --max-steps 1", output)
                self.assertIn(f"follow: mew work 1 --follow --quiet --allow-read {resolved} --max-steps 3", output)
                self.assertIn(f"resume: mew work 1 --session --resume --allow-read {resolved}", output)
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_cycle_dry_run(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "self-improve",
                            "--cycle",
                            "--focus",
                            "Run a supervised dry run",
                            "--dry-run",
                        ]
                    )

                self.assertEqual(code, 0)
                self.assertIn("cycle 1/1: created dry-run self-improve run", stdout.getvalue())
                state = load_state()
                self.assertEqual(len(state["agent_runs"]), 1)
                self.assertEqual(state["agent_runs"][0]["status"], "dry_run")
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_cycle_waits_reviews_and_processes_pass(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                verify_calls = []

                class VerifyResult:
                    returncode = 0
                    stdout = "verified"
                    stderr = ""

                def fake_start_agent_run(state, run):
                    run["status"] = "running"
                    run["external_pid"] = 1000 + run["id"]
                    run["started_at"] = now_iso()
                    run["updated_at"] = run["started_at"]
                    return run

                def fake_wait_agent_run(state, run, timeout=None):
                    run["status"] = "completed"
                    run["finished_at"] = now_iso()
                    run["updated_at"] = run["finished_at"]
                    if run["purpose"] == "review":
                        run["result"] = json.dumps(
                            [
                                {
                                    "status": "completed",
                                    "agentOutput": {
                                        "message": (
                                            "STATUS: pass\n"
                                            "SUMMARY: ok\n"
                                            "FINDINGS:\n"
                                            "- none\n"
                                            "FOLLOW_UP:\n"
                                            "- none"
                                        )
                                    },
                                }
                            ]
                        )
                    else:
                        run["result"] = json.dumps(
                            [{"status": "completed", "agentOutput": {"message": "implemented"}}]
                        )
                    sync_task_with_agent_run(state, run, run["updated_at"])
                    return run

                def fake_verify_run(argv, **kwargs):
                    verify_calls.append((argv, kwargs))
                    return VerifyResult()

                with patch("mew.commands.start_agent_run", side_effect=fake_start_agent_run):
                    with patch("mew.commands.wait_agent_run", side_effect=fake_wait_agent_run):
                        with patch("mew.toolbox.subprocess.run", side_effect=fake_verify_run):
                            with redirect_stdout(StringIO()) as stdout:
                                code = main(
                                    [
                                        "self-improve",
                                        "--cycle",
                                        "--focus",
                                        "Run a supervised cycle",
                                        "--timeout",
                                        "1",
                                        "--verify-command",
                                        "CHECK=1 verifier --ok",
                                    ]
                                )

                self.assertEqual(code, 0)
                output = stdout.getvalue()
                self.assertIn("implementation run #1 status=completed", output)
                self.assertIn("verification exit_code=0", output)
                self.assertIn("review run #2 status=completed", output)
                self.assertIn("review status=pass", output)
                self.assertEqual(verify_calls[0][0], ["verifier", "--ok"])
                self.assertEqual(verify_calls[0][1]["env"]["CHECK"], "1")

                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertEqual(state["tasks"][0]["status"], "done")
                self.assertEqual(len(state["agent_runs"]), 2)
                self.assertEqual(state["agent_runs"][0]["supervisor_verification"]["exit_code"], 0)
                self.assertEqual(state["agent_runs"][0]["supervisor_verification"]["stdout"], "verified")
                self.assertEqual(state["agent_runs"][1]["purpose"], "review")
                self.assertEqual(state["agent_runs"][1]["review_status"], "pass")
                self.assertTrue(state["agent_runs"][1]["followup_processed_at"])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_cycle_stops_when_verification_fails(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                class VerifyResult:
                    returncode = 1
                    stdout = ""
                    stderr = "failed"

                def fake_start_agent_run(state, run):
                    run["status"] = "running"
                    run["external_pid"] = 3000 + run["id"]
                    return run

                def fake_wait_agent_run(state, run, timeout=None):
                    run["status"] = "completed"
                    run["finished_at"] = now_iso()
                    run["updated_at"] = run["finished_at"]
                    run["result"] = json.dumps(
                        [{"status": "completed", "agentOutput": {"message": "implemented"}}]
                    )
                    sync_task_with_agent_run(state, run, run["updated_at"])
                    return run

                with patch("mew.commands.start_agent_run", side_effect=fake_start_agent_run):
                    with patch("mew.commands.wait_agent_run", side_effect=fake_wait_agent_run):
                        with patch("mew.toolbox.subprocess.run", return_value=VerifyResult()):
                            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                                code = main(
                                    [
                                        "self-improve",
                                        "--cycle",
                                        "--focus",
                                        "Stop on failed verification",
                                        "--verify-command",
                                        "verifier",
                                    ]
                                )

                self.assertEqual(code, 1)
                state = load_state()
                self.assertEqual(len(state["agent_runs"]), 1)
                self.assertEqual(state["agent_runs"][0]["supervisor_verification"]["exit_code"], 1)
                self.assertEqual(state["tasks"][0]["status"], "blocked")
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_cycle_stops_on_unknown_review(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fake_start_agent_run(state, run):
                    run["status"] = "running"
                    run["external_pid"] = 2000 + run["id"]
                    return run

                def fake_wait_agent_run(state, run, timeout=None):
                    run["status"] = "completed"
                    run["finished_at"] = now_iso()
                    run["updated_at"] = run["finished_at"]
                    if run["purpose"] == "review":
                        run["result"] = json.dumps(
                            [{"status": "completed", "agentOutput": {"message": "No structured status"}}]
                        )
                    else:
                        run["result"] = json.dumps(
                            [{"status": "completed", "agentOutput": {"message": "implemented"}}]
                        )
                    sync_task_with_agent_run(state, run, run["updated_at"])
                    return run

                with patch("mew.commands.start_agent_run", side_effect=fake_start_agent_run):
                    with patch("mew.commands.wait_agent_run", side_effect=fake_wait_agent_run):
                        with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                            code = main(
                                [
                                    "self-improve",
                                    "--cycle",
                                    "--focus",
                                    "Stop on unknown review",
                                    "--timeout",
                                    "1",
                                ]
                            )

                self.assertEqual(code, 1)
                state = load_state()
                self.assertEqual(state["agent_runs"][1]["review_status"], "unknown")
                self.assertTrue(state["agent_runs"][1]["followup_processed_at"])
                self.assertEqual(len(state["tasks"]), 2)
                self.assertEqual(state["tasks"][0]["status"], "blocked")
                self.assertIn("did not return a parseable", state["tasks"][1]["description"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
