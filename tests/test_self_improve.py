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
from mew.state import default_state, load_state, save_state
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
        self.assertIn("inspect sibling code paths on the same surface", description)

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
        self.assertIn("prints concrete continue/follow/status/resume/cells/active-memory/chat controls", output)
        self.assertIn("mew self-improve --start-session --json --focus", output)
        self.assertIn(
            "returns controls.continue, controls.follow, controls.status, controls.resume, controls.cells, controls.active_memory, controls.chat",
            output,
        )
        self.assertIn("mew work <task-id> --live --allow-read . --compact-live --max-steps 1", output)
        self.assertIn("mew work <task-id> --follow --allow-read . --compact-live --quiet --max-steps 10", output)
        self.assertIn("mew work <task-id> --session --resume --allow-read .", output)
        self.assertIn("mew work <task-id> --cells", output)
        self.assertIn("mew memory --active --task-id <task-id>", output)
        self.assertIn("mew work <task-id> --follow-status --json", output)
        self.assertIn("mew chat", output)
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

    def test_cli_self_improve_dispatch_surfaces_failed_start_detail(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                def fail_start(_state, run):
                    run["status"] = "failed"
                    run["stderr"] = "spawn failed"

                with (
                    patch("mew.commands.start_agent_run", side_effect=fail_start),
                    redirect_stdout(StringIO()) as stdout,
                ):
                    code = main(["self-improve", "--focus", "Failing implementation run", "--dispatch"])

                self.assertEqual(code, 1)
                output = stdout.getvalue()
                self.assertIn("started self-improve run #1 status=failed", output)
                self.assertIn("mew: self-improve run #1 status=failed: spawn failed", output)
                state = load_state()
                self.assertEqual(state["agent_runs"][0]["status"], "failed")
                self.assertEqual(state["agent_runs"][0]["stderr"], "spawn failed")
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
                self.assertIn("start session: mew work 1 --start-session --allow-read . --compact-live", output)
                self.assertIn(f"work cwd: {Path(tmp).resolve()}", output)
                self.assertIn("continue: mew work 1 --live --allow-read . --compact-live --max-steps 1", output)
                self.assertIn("follow: mew work 1 --follow --allow-read . --compact-live --quiet --max-steps 10", output)
                self.assertIn("status: mew work 1 --follow-status --json", output)
                self.assertIn("resume: mew work 1 --session --resume --allow-read .", output)
                self.assertIn("cells: mew work 1 --cells", output)
                self.assertIn("active memory: mew memory --active --task-id 1", output)
                self.assertIn("chat: mew chat", output)
                state = load_state()
                self.assertEqual(len(state["tasks"]), 1)
                self.assertEqual(state["tasks"][0]["latest_plan_id"], None)
                self.assertEqual(state["tasks"][0]["plans"], [])
                self.assertEqual(len(state["agent_runs"]), 0)
                self.assertEqual(state["work_sessions"], [])

                with redirect_stdout(StringIO()) as start_stdout:
                    start_code = main(["work", "1", "--start-session", "--allow-read", ".", "--compact-live", "--json"])

                self.assertEqual(start_code, 0)
                start_data = json.loads(start_stdout.getvalue())
                defaults = start_data["work_session"]["default_options"]
                self.assertEqual(defaults["allow_read"], ["."])
                self.assertTrue(defaults["compact_live"])
                notes = start_data["work_session"]["notes"]
                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0]["source"], "system")
                self.assertIn("Native self-improve reentry prepared.", notes[0]["text"])
                self.assertIn("mew work 1 --live", notes[0]["text"])
                self.assertIn("--allow-read . --compact-live --max-steps 1", notes[0]["text"])
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

    def test_cli_self_improve_native_rejects_force_plan(self):
        old_cwd = os.getcwd()
        cases = (
            ["--native", "--force-plan"],
            ["--start-session", "--force-plan"],
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
                            "--native/--start-session cannot be combined with --force-plan",
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
                self.assertIn("continue: mew work 1 --live --allow-read . --compact-live --max-steps 1", output)
                self.assertIn("follow: mew work 1 --follow --allow-read . --compact-live --quiet --max-steps 10", output)
                self.assertIn("status: mew work 1 --follow-status --json", output)
                self.assertIn("resume: mew work 1 --session --resume --allow-read .", output)
                self.assertIn("cells: mew work 1 --cells", output)
                self.assertIn("active memory: mew memory --active --task-id 1", output)
                self.assertIn("audit: mew self-improve --audit 1", output)
                self.assertIn("chat: mew chat", output)
                state = load_state()
                self.assertEqual(state["tasks"][0]["status"], "ready")
                self.assertEqual(state["tasks"][0]["plans"], [])
                self.assertEqual(state["work_sessions"][0]["task_id"], 1)
                self.assertEqual(state["work_sessions"][0]["status"], "active")
                defaults = state["work_sessions"][0]["default_options"]
                self.assertEqual(defaults["allow_read"], ["."])
                self.assertTrue(defaults["compact_live"])
                audit = state["work_sessions"][0]["m5_self_improve_audit"]
                self.assertEqual(audit["schema_version"], 1)
                self.assertEqual(audit["frozen_permission_context"]["allow_read"], ["."])
                self.assertEqual(audit["effect_budget"]["continue_max_steps"], 1)
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_start_session_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["self-improve", "--start-session", "--focus", "Start native work", "--json"])

                self.assertEqual(code, 0)
                data = json.loads(stdout.getvalue())
                self.assertTrue(data["created"])
                self.assertTrue(data["session_created"])
                self.assertTrue(data["native"])
                self.assertEqual(data["task"]["id"], 1)
                self.assertEqual(data["task"]["status"], "ready")
                self.assertEqual(data["work_session"]["id"], 1)
                self.assertEqual(data["work_session"]["task_id"], 1)
                self.assertEqual(data["work_session"]["default_options"]["allow_read"], ["."])
                self.assertTrue(data["work_session"]["default_options"]["compact_live"])
                notes = data["work_session"]["notes"]
                self.assertEqual(len(notes), 1)
                self.assertEqual(notes[0]["source"], "system")
                self.assertIn("Native self-improve reentry prepared.", notes[0]["text"])
                self.assertIn("mew work 1 --live --allow-read . --compact-live --max-steps 1", notes[0]["text"])
                self.assertIn("mew work 1 --session --resume --allow-read .", notes[0]["text"])
                self.assertIn("mew self-improve --audit 1", notes[0]["text"])
                audit = data["work_session"]["m5_self_improve_audit"]
                self.assertEqual(audit["loop_credit_status"], "not_counted_until_closed_with_no_rescue_review")
                self.assertFalse(audit["permission_context_drift"])
                self.assertEqual(data["controls"]["work_cwd"], str(Path(tmp).resolve()))
                self.assertEqual(
                    data["controls"]["continue"],
                    "mew work 1 --live --allow-read . --compact-live --max-steps 1",
                )
                self.assertEqual(
                    data["controls"]["follow"],
                    "mew work 1 --follow --allow-read . --compact-live --quiet --max-steps 10",
                )
                self.assertEqual(data["controls"]["status"], "mew work 1 --follow-status --json")
                self.assertEqual(data["controls"]["resume"], "mew work 1 --session --resume --allow-read .")
                self.assertEqual(data["controls"]["cells"], "mew work 1 --cells")
                self.assertEqual(data["controls"]["active_memory"], "mew memory --active --task-id 1")
                self.assertEqual(data["controls"]["audit"], "mew self-improve --audit 1")
                self.assertEqual(data["controls"]["chat"], "mew chat")
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_audit_outputs_m5_bundle(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    code = main(["self-improve", "--start-session", "--focus", "Start native work"])
                self.assertEqual(code, 0)
                state = load_state()
                session = state["work_sessions"][0]
                session["tool_calls"].append(
                    {
                        "id": 50,
                        "tool": "edit_file",
                        "status": "completed",
                        "result": {
                            "verification": {
                                "command": "uv run pytest -q",
                                "exit_code": 0,
                                "started_at": now_iso(),
                                "finished_at": now_iso(),
                            }
                        },
                    }
                )
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    audit_code = main(["self-improve", "--audit", "1", "--json"])

                self.assertEqual(audit_code, 0)
                bundle = json.loads(stdout.getvalue())
                self.assertEqual(bundle["status"], "ready")
                self.assertEqual(bundle["task"]["id"], 1)
                self.assertEqual(bundle["work_session"]["id"], 1)
                self.assertEqual(bundle["permission_context"]["frozen"]["allow_read"], ["."])
                self.assertEqual(bundle["effect_budget"]["follow_max_steps"], 10)
                self.assertEqual(bundle["human_intervention"]["classification"], "none_recorded")
                self.assertEqual(
                    bundle["human_intervention"]["m5_credit"],
                    "not_counted_until_human_review_confirms_no_rescue_edits",
                )
                self.assertEqual(
                    bundle["human_intervention"]["no_rescue_review_status"],
                    "pending_human_review",
                )
                self.assertEqual(bundle["verification"]["status"], "passed")
                self.assertEqual(bundle["verification"]["latest"]["source"], "work_tool")
                self.assertEqual(bundle["verification"]["latest"]["tool_call_id"], 50)
                self.assertEqual(bundle["verification"]["latest"]["exit_code"], 0)

                state = load_state()
                state["work_sessions"][0]["notes"].append(
                    {
                        "created_at": now_iso(),
                        "source": "user",
                        "text": "No supervisor file patch was used; approvals only.",
                    }
                )
                save_state(state)

                with redirect_stdout(StringIO()) as reviewed_stdout:
                    reviewed_code = main(["self-improve", "--audit", "1", "--json"])

                self.assertEqual(reviewed_code, 0)
                reviewed_bundle = json.loads(reviewed_stdout.getvalue())
                self.assertEqual(
                    reviewed_bundle["human_intervention"]["no_rescue_review_status"],
                    "no_rescue_review_recorded",
                )
                self.assertEqual(
                    reviewed_bundle["human_intervention"]["m5_credit"],
                    "candidate_no_rescue_reviewed_pending_m3",
                )
                self.assertEqual(
                    reviewed_bundle["loop_credit_status"],
                    "candidate_no_rescue_reviewed_pending_m3",
                )

                with redirect_stdout(StringIO()) as text_stdout:
                    text_code = main(["self-improve", "--audit", "1"])

                self.assertEqual(text_code, 0)
                self.assertIn("verification: passed exit_code=0", text_stdout.getvalue())
                self.assertIn("no_rescue_review=no_rescue_review_recorded", text_stdout.getvalue())
                self.assertIn(
                    "loop_credit_status: candidate_no_rescue_reviewed_pending_m3",
                    text_stdout.getvalue(),
                )

                state = load_state()
                state["work_sessions"][0]["notes"].append(
                    {
                        "created_at": now_iso(),
                        "source": "user",
                        "text": "Supervisor rescue: manual patch applied after a failed paired edit.",
                    }
                )
                save_state(state)

                with redirect_stdout(StringIO()) as rescue_stdout:
                    rescue_code = main(["self-improve", "--audit", "1", "--json"])

                self.assertEqual(rescue_code, 0)
                rescue_bundle = json.loads(rescue_stdout.getvalue())
                self.assertEqual(
                    rescue_bundle["human_intervention"]["rescue_edit_status"],
                    "rescue_recorded",
                )
                self.assertEqual(
                    rescue_bundle["human_intervention"]["no_rescue_review_status"],
                    "rescue_recorded",
                )
                self.assertEqual(
                    rescue_bundle["human_intervention"]["m5_credit"],
                    "not_counted_due_to_rescue",
                )
                self.assertEqual(
                    rescue_bundle["loop_credit_status"],
                    "not_counted_due_to_rescue",
                )
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_audit_missing_task_text_is_concise(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    audit_code = main(["self-improve", "--audit", "999"])

                self.assertEqual(audit_code, 1)
                output = stdout.getvalue()
                self.assertIn("M5 self-improve audit", output)
                self.assertIn("status: missing_task", output)
                self.assertIn("task_ref: 999", output)
                self.assertNotIn("#None", output)
                self.assertNotIn("None None", output)
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_start_session_seeds_mew_project_write_defaults(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "mew").mkdir(parents=True)
            (root / "tests").mkdir()
            (root / "pyproject.toml").touch()
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(["self-improve", "--start-session", "--focus", "Start native work", "--json"])

                self.assertEqual(code, 0)
                data = json.loads(stdout.getvalue())
                defaults = data["work_session"]["default_options"]
                self.assertEqual(defaults["allow_read"], ["."])
                self.assertEqual(defaults["allow_write"], ["src/mew", "tests"])
                self.assertTrue(defaults["allow_verify"])
                self.assertEqual(defaults["verify_command"], "uv run pytest -q")
                self.assertIn("--allow-write src/mew --allow-write tests", data["controls"]["follow"])
                self.assertIn("--allow-verify --verify-command 'uv run pytest -q'", data["controls"]["follow"])
                self.assertIn("--allow-write src/mew --allow-write tests", data["work_session"]["notes"][0]["text"])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_start_session_refreshes_reused_session_goal(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    first_code = main(["self-improve", "--start-session", "--focus", "First focus"])
                self.assertEqual(first_code, 0)

                with redirect_stdout(StringIO()) as stdout:
                    second_code = main(["self-improve", "--start-session", "--focus", "Second focus", "--json"])

                self.assertEqual(second_code, 0)
                data = json.loads(stdout.getvalue())
                self.assertFalse(data["created"])
                self.assertFalse(data["session_created"])
                self.assertIn("Second focus", data["task"]["description"])
                self.assertIn("Second focus", data["work_session"]["goal"])
                self.assertNotIn("First focus", data["work_session"]["goal"])
                state = load_state()
                self.assertIn("Second focus", state["work_sessions"][0]["goal"])
            finally:
                os.chdir(old_cwd)

    def test_cli_self_improve_start_session_seeds_defaults_on_reused_session(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    first_code = main(["self-improve", "--start-session", "--focus", "First focus"])
                self.assertEqual(first_code, 0)

                state = load_state()
                state["work_sessions"][0]["default_options"] = {
                    "auth": "auth.json",
                    "model_backend": "codex",
                    "allow_read": ["README.md"],
                    "allow_write": ["src/mew", "tests"],
                    "allow_verify": True,
                    "verify_command": "uv run pytest -q",
                    "act_mode": "deterministic",
                    "compact_live": False,
                    "quiet": True,
                }
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    second_code = main(["self-improve", "--start-session", "--focus", "Second focus", "--json"])

                self.assertEqual(second_code, 0)
                data = json.loads(stdout.getvalue())
                self.assertFalse(data["session_created"])
                defaults = data["work_session"]["default_options"]
                self.assertEqual(defaults["allow_read"], ["README.md", "."])
                self.assertTrue(defaults["compact_live"])
                self.assertEqual(
                    data["controls"]["continue"],
                    (
                        "mew work 1 --live --auth auth.json --model-backend codex "
                        "--allow-read README.md --allow-read . --allow-write src/mew --allow-write tests "
                        "--allow-verify --verify-command 'uv run pytest -q' --act-mode deterministic "
                        "--compact-live --quiet --max-steps 1"
                    ),
                )
                self.assertEqual(
                    data["controls"]["follow"],
                    data["controls"]["continue"].replace("--live", "--follow").replace("--max-steps 1", "--max-steps 10"),
                )
                self.assertEqual(
                    data["controls"]["resume"],
                    "mew work 1 --session --resume --allow-read README.md --allow-read .",
                )
                state = load_state()
                self.assertEqual(state["work_sessions"][0]["default_options"]["allow_read"], ["README.md", "."])
                self.assertTrue(state["work_sessions"][0]["default_options"]["compact_live"])
                notes = state["work_sessions"][0]["notes"]
                self.assertEqual(
                    1,
                    sum(
                        1
                        for note in notes
                        if note["text"].startswith("Native self-improve reentry prepared.")
                    ),
                )
                self.assertIn("--auth auth.json --model-backend codex", notes[-1]["text"])
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
                self.assertIn(f"continue: mew work 1 --live --allow-read {resolved} --compact-live --max-steps 1", output)
                self.assertIn(f"follow: mew work 1 --follow --allow-read {resolved} --compact-live --quiet --max-steps 10", output)
                self.assertIn("status: mew work 1 --follow-status --json", output)
                self.assertIn(f"resume: mew work 1 --session --resume --allow-read {resolved}", output)
                self.assertIn("cells: mew work 1 --cells", output)
                self.assertIn("active memory: mew memory --active --task-id 1", output)
                self.assertIn("chat: mew chat", output)
                state = load_state()
                defaults = state["work_sessions"][0]["default_options"]
                self.assertEqual(defaults["allow_read"], [resolved])
                self.assertTrue(defaults["compact_live"])
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
