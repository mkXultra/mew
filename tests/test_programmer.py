import json
import unittest
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from mew.agent import apply_action_plan, deterministic_decision_plan
from mew.agent_runs import (
    extract_ai_cli_session_id,
    get_agent_run_result,
    parse_ai_cli_status,
    parse_ai_cli_pid,
    sync_task_with_agent_run,
    wait_agent_run,
)
from mew.cli import main
from mew.programmer import (
    build_review_prompt,
    create_follow_up_task_from_review,
    create_implementation_run_from_plan,
    create_retry_run_for_implementation,
    create_review_run_for_implementation,
    create_task_plan,
    extract_review_text,
    parse_review_status,
)
from mew.state import add_attention_item, add_question, default_state, load_state, migrate_state, save_state
from mew.tasks import execute_task_action
from mew.timeutil import now_iso


def add_task(state):
    task = {
        "id": 1,
        "title": "Implement programmer loop",
        "description": "Add planning and review flow.",
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
        "created_at": "t",
        "updated_at": "t",
    }
    state["tasks"].append(task)
    return task


class ProgrammerTests(unittest.TestCase):
    def test_task_plan_sets_prompt_and_latest_plan(self):
        state = default_state()
        task = add_task(state)

        plan = create_task_plan(state, task, model="codex-ultra")

        self.assertEqual(task["latest_plan_id"], plan["id"])
        self.assertIn("Implement programmer loop", plan["implementation_prompt"])
        self.assertEqual(task["agent_model"], "codex-ultra")
        self.assertEqual(task["agent_prompt"], plan["implementation_prompt"])

    def test_task_plan_prompt_advertises_safe_tool_layer(self):
        state = default_state()
        task = add_task(state)

        plan = create_task_plan(state, task)

        self.assertIn("Safe local tool layer:", plan["implementation_prompt"])
        self.assertIn("uv run mew tool status", plan["implementation_prompt"])
        self.assertIn("uv run mew tool read", plan["implementation_prompt"])
        self.assertIn("uv run mew tool test --command", plan["implementation_prompt"])

    def test_dispatch_run_is_implementation_and_syncs_task(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)

        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "completed"
        sync_task_with_agent_run(state, run, "done-at")

        self.assertEqual(run["purpose"], "implementation")
        self.assertEqual(run["plan_id"], plan["id"])
        self.assertEqual(task["status"], "done")

    def test_review_run_does_not_sync_task_status(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        implementation = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        self.assertEqual(task["agent_run_id"], implementation["id"])
        task["status"] = "done"

        review = create_review_run_for_implementation(state, task, implementation, plan=plan)
        review["status"] = "failed"
        sync_task_with_agent_run(state, review, "review-at")

        self.assertEqual(review["purpose"], "review")
        self.assertEqual(review["review_of_run_id"], implementation["id"])
        self.assertEqual(task["status"], "done")
        self.assertEqual(task["agent_run_id"], implementation["id"])

    def test_review_prompt_includes_supervisor_verification(self):
        state = default_state()
        task = add_task(state)
        implementation = {
            "id": 4,
            "status": "completed",
            "result": "implemented",
            "stderr": "",
            "supervisor_verification": {
                "command": "python -m unittest",
                "exit_code": 0,
                "stdout": "OK",
                "stderr": "",
            },
        }

        prompt = build_review_prompt(task, implementation)

        self.assertIn("Supervisor verification:", prompt)
        self.assertIn('"command": "python -m unittest"', prompt)
        self.assertIn('"exit_code": 0', prompt)

    def test_retry_run_is_implementation_with_parent_context(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        failed = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        failed["status"] = "failed"
        failed["result"] = "tests failed"

        retry = create_retry_run_for_implementation(state, task, failed, plan=plan, dry_run=True)

        self.assertEqual(retry["purpose"], "implementation")
        self.assertEqual(retry["parent_run_id"], failed["id"])
        self.assertEqual(task["agent_run_id"], retry["id"])
        self.assertIn("Retry context", retry["prompt"])

    def test_followup_task_from_review_result(self):
        state = default_state()
        task = add_task(state)
        task["status"] = "done"
        review = {
            "id": 7,
            "task_id": task["id"],
            "purpose": "review",
            "result": "STATUS: needs_fix\nSUMMARY: x\nFOLLOW_UP:\n- Add tests for programmer loop",
            "stdout": "",
        }

        followup, status = create_follow_up_task_from_review(state, task, review)

        self.assertEqual(status, "needs_fix")
        self.assertIsNotNone(followup)
        self.assertIn("Add tests", followup["description"])
        self.assertEqual(task["status"], "blocked")
        self.assertTrue(review["followup_processed_at"])

    def test_review_status_uses_agent_message_not_prompt_template(self):
        state = default_state()
        task = add_task(state)
        review = {
            "id": 8,
            "task_id": task["id"],
            "purpose": "review",
            "result": json.dumps(
                [
                    {
                        "prompt": "Return STATUS: pass|needs_fix|unknown",
                        "agentOutput": {"message": None},
                    }
                ]
            ),
            "stdout": "",
        }

        followup, status = create_follow_up_task_from_review(state, task, review)

        self.assertIsNone(followup)
        self.assertEqual(status, "unknown")
        self.assertEqual(review["review_status"], "unknown")
        self.assertTrue(review["followup_processed_at"])

    def test_review_status_reads_nested_agent_message(self):
        review = {
            "result": json.dumps(
                [
                    {
                        "prompt": "Return STATUS: pass|needs_fix|unknown",
                        "agentOutput": {
                            "message": "STATUS: needs_fix\nSUMMARY: x\nFOLLOW_UP:\n- Tighten review parsing"
                        },
                    }
                ]
            ),
            "stdout": "",
        }

        self.assertIn("Tighten review parsing", extract_review_text(review))

    def test_parse_review_status(self):
        self.assertEqual(parse_review_status("STATUS: pass"), "pass")
        self.assertEqual(parse_review_status("STATUS: needs_fix"), "needs_fix")
        self.assertEqual(parse_review_status("STATUS: needs fix"), "needs_fix")
        self.assertEqual(parse_review_status("STATUS: pass|needs_fix|unknown"), "unknown")
        self.assertEqual(parse_review_status("no explicit status"), "unknown")

    def test_parse_ai_cli_pid_does_not_accept_unlabeled_numbers(self):
        self.assertEqual(parse_ai_cli_pid('{"pid": 12345}'), 12345)
        self.assertEqual(parse_ai_cli_pid("started pid=12345"), 12345)
        self.assertIsNone(parse_ai_cli_pid("Error 404 on line 12"))

    def test_extract_ai_cli_session_id_from_nested_result(self):
        self.assertEqual(
            extract_ai_cli_session_id('{"agentOutput": {"session_id": "abc-123"}}'),
            "abc-123",
        )
        self.assertEqual(extract_ai_cli_session_id('{"result": {"sessionId": "def-456"}}'), "def-456")
        self.assertIsNone(extract_ai_cli_session_id("not json"))

    def test_parse_ai_cli_status_from_nested_result(self):
        self.assertEqual(parse_ai_cli_status('{"agentOutput": {"state": "completed"}}'), "completed")
        self.assertEqual(parse_ai_cli_status('{"result": {"status": "running"}}'), "running")
        self.assertIsNone(parse_ai_cli_status('{"review_status": "pass"}'))

    def test_sync_task_with_agent_run_tolerates_string_task_id(self):
        state = default_state()
        task = add_task(state)
        run = {
            "id": 3,
            "task_id": str(task["id"]),
            "purpose": "implementation",
            "status": "completed",
        }

        sync_task_with_agent_run(state, run, "done-at")

        self.assertEqual(task["status"], "done")
        self.assertEqual(task["agent_run_id"], run["id"])
        self.assertEqual(task["updated_at"], "done-at")

    def test_unparseable_agent_result_fails_run_instead_of_polling_forever(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        run = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        run["status"] = "running"
        run["external_pid"] = 12345

        class Result:
            returncode = 0
            stdout = "completed but not json"
            stderr = ""

        with patch("mew.agent_runs.subprocess.run", return_value=Result()):
            get_agent_run_result(state, run)

        self.assertEqual(run["status"], "failed")
        self.assertIn("could not parse", run["result"])
        self.assertEqual(task["status"], "blocked")
        self.assertIn("no parseable status", state["outbox"][-1]["text"])

    def test_agent_result_os_error_finalizes_linked_task_and_attention(self):
        state = default_state()
        task = add_task(state)
        run = create_implementation_run_from_plan(state, task, create_task_plan(state, task), dry_run=True)
        run["status"] = "running"
        run["external_pid"] = 12345
        add_attention_item(state, "agent_run", "Agent run #1 is running", "still running", agent_run_id=str(run["id"]))

        with patch("mew.agent_runs.subprocess.run", side_effect=OSError("ai-cli missing")):
            get_agent_run_result(state, run)

        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["result"], "ai-cli missing")
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(state["attention"]["items"][0]["status"], "resolved")

    def test_agent_wait_os_error_finalizes_linked_task_and_attention(self):
        state = default_state()
        task = add_task(state)
        run = create_implementation_run_from_plan(state, task, create_task_plan(state, task), dry_run=True)
        run["status"] = "running"
        run["external_pid"] = 12345
        add_attention_item(state, "agent_run", "Agent run #1 is running", "still running", agent_run_id=run["id"])

        with patch("mew.agent_runs.subprocess.run", side_effect=OSError("ai-cli missing")):
            wait_agent_run(state, run)

        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["result"], "ai-cli missing")
        self.assertEqual(task["status"], "blocked")
        self.assertEqual(state["attention"]["items"][0]["status"], "resolved")

    def test_autonomous_plan_task_action_creates_plan(self):
        state = default_state()
        task = add_task(state)
        event = {"id": 1, "type": "passive_tick"}

        apply_action_plan(
            state,
            event,
            {"summary": "plan task", "decisions": []},
            {"summary": "plan task", "actions": [{"type": "plan_task", "task_id": task["id"]}]},
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertEqual(len(task["plans"]), 1)
        self.assertEqual(task["latest_plan_id"], task["plans"][0]["id"])

    def test_autonomous_dispatch_requires_allow_agent_run(self):
        state = default_state()
        task = add_task(state)
        task["status"] = "ready"
        task["auto_execute"] = True
        plan = create_task_plan(state, task)
        event = {"id": 1, "type": "passive_tick"}

        apply_action_plan(
            state,
            event,
            {"summary": "dispatch task", "decisions": []},
            {
                "summary": "dispatch task",
                "actions": [{"type": "dispatch_task", "task_id": task["id"], "plan_id": plan["id"]}],
            },
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=False,
        )

        self.assertEqual(state["agent_runs"], [])
        self.assertIn("--allow-agent-run is required", state["outbox"][-1]["text"])

    def test_execute_task_does_not_start_agent_backend(self):
        state = default_state()
        task = add_task(state)
        task["status"] = "ready"
        task["auto_execute"] = True
        task["agent_backend"] = "ai-cli"

        executed = execute_task_action(state, {"task_id": task["id"]}, task_timeout=1)

        self.assertEqual(executed, 0)
        self.assertEqual(state["agent_runs"], [])
        self.assertIn("command and auto_execute", state["outbox"][-1]["text"])

    def test_autonomous_run_verification_requires_allow_verify(self):
        state = default_state()
        event = {"id": 1, "type": "passive_tick"}

        apply_action_plan(
            state,
            event,
            {"summary": "verify", "decisions": []},
            {"summary": "verify", "actions": [{"type": "run_verification", "reason": "check tests"}]},
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="act",
            allow_verify=False,
            verify_command="python -m unittest",
        )

        self.assertEqual(state["verification_runs"], [])
        self.assertIn("--allow-verify is required", state["outbox"][-1]["text"])

    def test_autonomous_run_verification_records_result(self):
        state = default_state()
        event = {"id": 1, "type": "passive_tick"}

        def fake_run_command_record(command, cwd=None, timeout=300):
            return {
                "command": command,
                "argv": ["python", "-m", "unittest"],
                "cwd": "/tmp/repo",
                "started_at": "start",
                "finished_at": "end",
                "exit_code": 0,
                "stdout": "OK",
                "stderr": "",
            }

        with patch("mew.agent.run_command_record", side_effect=fake_run_command_record):
            apply_action_plan(
                state,
                event,
                {"summary": "verify", "decisions": []},
                {"summary": "verify", "actions": [{"type": "run_verification", "reason": "check tests"}]},
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                autonomous=True,
                autonomy_level="act",
                allow_verify=True,
                verify_command="python -m unittest",
                verify_timeout=10,
            )

        self.assertEqual(len(state["verification_runs"]), 1)
        self.assertEqual(state["verification_runs"][0]["exit_code"], 0)
        self.assertEqual(state["verification_runs"][0]["reason"], "check tests")
        self.assertIn("Verification passed", state["outbox"][-1]["text"])

    def test_autonomous_run_verification_failure_creates_attention(self):
        state = default_state()
        event = {"id": 1, "type": "passive_tick"}

        def fake_run_command_record(command, cwd=None, timeout=300):
            return {
                "command": command,
                "argv": ["python", "-m", "unittest"],
                "cwd": "/tmp/repo",
                "started_at": "start",
                "finished_at": "end",
                "exit_code": 1,
                "stdout": "",
                "stderr": "FAILED",
            }

        with patch("mew.agent.run_command_record", side_effect=fake_run_command_record):
            apply_action_plan(
                state,
                event,
                {"summary": "verify", "decisions": []},
                {"summary": "verify", "actions": [{"type": "run_verification"}]},
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                autonomous=True,
                autonomy_level="act",
                allow_verify=True,
                verify_command="python -m unittest",
            )

        self.assertEqual(state["verification_runs"][0]["exit_code"], 1)
        self.assertIn("Verification failed", state["outbox"][-1]["text"])
        self.assertEqual(state["attention"]["items"][0]["kind"], "verification")

    def test_autonomous_dispatch_starts_when_allowed(self):
        state = default_state()
        task = add_task(state)
        task["status"] = "ready"
        task["auto_execute"] = True
        plan = create_task_plan(state, task)
        event = {"id": 1, "type": "passive_tick"}

        def fake_start_agent_run(state_arg, run):
            run["status"] = "running"
            run["external_pid"] = 123
            sync_task_with_agent_run(state_arg, run, now_iso())
            return run

        with patch("mew.agent.start_agent_run", side_effect=fake_start_agent_run):
            apply_action_plan(
                state,
                event,
                {"summary": "dispatch task", "decisions": []},
                {
                    "summary": "dispatch task",
                    "actions": [{"type": "dispatch_task", "task_id": task["id"], "plan_id": plan["id"]}],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                autonomous=True,
                autonomy_level="act",
                allow_agent_run=True,
            )

        self.assertEqual(len(state["agent_runs"]), 1)
        self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
        self.assertEqual(state["agent_runs"][0]["status"], "running")
        self.assertEqual(task["status"], "running")

    def test_autonomous_review_run_does_not_change_task_status(self):
        state = default_state()
        task = add_task(state)
        plan = create_task_plan(state, task)
        implementation = create_implementation_run_from_plan(state, task, plan, dry_run=True)
        implementation["status"] = "completed"
        task["status"] = "done"
        event = {"id": 1, "type": "passive_tick"}

        def fake_start_agent_run(state_arg, run):
            run["status"] = "running"
            run["external_pid"] = 456
            sync_task_with_agent_run(state_arg, run, now_iso())
            return run

        with patch("mew.agent.start_agent_run", side_effect=fake_start_agent_run):
            apply_action_plan(
                state,
                event,
                {"summary": "review implementation", "decisions": []},
                {
                    "summary": "review implementation",
                    "actions": [{"type": "review_agent_run", "run_id": implementation["id"]}],
                },
                now_iso(),
                allow_task_execution=False,
                task_timeout=1,
                autonomous=True,
                autonomy_level="act",
                allow_agent_run=True,
            )

        self.assertEqual(len(state["agent_runs"]), 2)
        self.assertEqual(state["agent_runs"][1]["purpose"], "review")
        self.assertEqual(state["agent_runs"][1]["review_of_run_id"], implementation["id"])
        self.assertEqual(task["status"], "done")

    def test_autonomous_followup_review_creates_one_task(self):
        state = default_state()
        task = add_task(state)
        review = {
            "id": 9,
            "task_id": task["id"],
            "purpose": "review",
            "status": "completed",
            "result": "STATUS: needs_fix\nFOLLOW_UP:\n- Add one regression test",
            "stdout": "",
            "followup_task_id": None,
        }
        state["agent_runs"].append(review)
        event = {"id": 1, "type": "passive_tick"}
        action_plan = {
            "summary": "follow up review",
            "actions": [{"type": "followup_review", "run_id": review["id"]}],
        }

        apply_action_plan(
            state,
            event,
            {"summary": "follow up review", "decisions": []},
            action_plan,
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="propose",
        )
        apply_action_plan(
            state,
            event,
            {"summary": "follow up review", "decisions": []},
            action_plan,
            now_iso(),
            allow_task_execution=False,
            task_timeout=1,
            autonomous=True,
            autonomy_level="propose",
        )

        self.assertEqual(len(state["tasks"]), 2)
        self.assertEqual(review["followup_task_id"], state["tasks"][1]["id"])

    def test_autonomous_decision_collects_running_run_even_with_open_question(self):
        state = default_state()
        task = add_task(state)
        implementation = create_implementation_run_from_plan(
            state,
            task,
            create_task_plan(state, task),
            dry_run=True,
        )
        implementation["status"] = "running"
        implementation["external_pid"] = 123
        add_question(state, "Still need user input", related_task_id=task["id"])

        plan = deterministic_decision_plan(
            state,
            {"id": 1, "type": "passive_tick"},
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="propose",
            allow_agent_run=False,
        )

        self.assertIn("wait_for_user", [decision["type"] for decision in plan["decisions"]])
        self.assertIn("collect_agent_result", [decision["type"] for decision in plan["decisions"]])

    def test_autonomous_decision_dispatch_requires_allow_agent_run(self):
        state = default_state()
        task = add_task(state)
        task["status"] = "ready"
        task["auto_execute"] = True
        create_task_plan(state, task)
        event = {"id": 1, "type": "passive_tick"}

        blocked_plan = deterministic_decision_plan(
            state,
            event,
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=False,
        )
        allowed_plan = deterministic_decision_plan(
            state,
            event,
            now_iso(),
            allow_task_execution=False,
            autonomous=True,
            autonomy_level="act",
            allow_agent_run=True,
        )

        self.assertNotIn("dispatch_task", [decision["type"] for decision in blocked_plan["decisions"]])
        self.assertIn("dispatch_task", [decision["type"] for decision in allowed_plan["decisions"]])

    def test_migration_adds_plan_and_run_defaults(self):
        state = default_state()
        task = add_task(state)
        task.pop("plans")
        task.pop("latest_plan_id")
        state["agent_runs"].append(
            {
                "id": 1,
                "task_id": task["id"],
                "backend": "ai-cli",
                "model": "codex-ultra",
                "status": "created",
                "command": ["ai-cli", "run"],
                "started_at": None,
                "external_pid": None,
            }
        )
        state["next_ids"].pop("plan")
        state["next_ids"]["task"] = 1
        state["next_ids"]["agent_run"] = 1

        migrated = migrate_state(state)

        self.assertEqual(migrated["tasks"][0]["plans"], [])
        self.assertIsNone(migrated["tasks"][0]["latest_plan_id"])
        self.assertEqual(migrated["agent_runs"][0]["purpose"], "implementation")
        self.assertEqual(migrated["agent_runs"][0]["status"], "dry_run")
        self.assertIn("plan", migrated["next_ids"])
        self.assertGreater(migrated["next_ids"]["task"], task["id"])
        self.assertGreater(migrated["next_ids"]["agent_run"], migrated["agent_runs"][0]["id"])

    def test_cli_plan_dispatch_review_dry_run_flow(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "CLI programmer task", "--description", "x"]), 0)
                    self.assertEqual(main(["task", "plan", "1", "--agent-model", "gpt-5.1-codex-mini"]), 0)
                    self.assertEqual(main(["task", "dispatch", "1", "--dry-run"]), 0)
                    self.assertEqual(main(["agent", "review", "1", "--dry-run", "--force"]), 0)
                    state = load_state()
                    state["agent_runs"][0]["status"] = "failed"
                    save_state(state)
                    self.assertEqual(main(["agent", "retry", "1", "--dry-run"]), 0)

                state = load_state()
                task = state["tasks"][0]
                self.assertEqual(len(task["plans"]), 1)
                self.assertEqual(len(state["agent_runs"]), 3)
                self.assertEqual(state["agent_runs"][0]["purpose"], "implementation")
                self.assertEqual(state["agent_runs"][1]["purpose"], "review")
                self.assertEqual(state["agent_runs"][2]["purpose"], "implementation")
                self.assertEqual(state["agent_runs"][0]["status"], "failed")
                self.assertEqual(state["agent_runs"][1]["status"], "dry_run")
                self.assertEqual(state["agent_runs"][2]["status"], "dry_run")
                self.assertIn("--prompt-file", state["agent_runs"][0]["command"])
                self.assertIn("--prompt-file", state["agent_runs"][1]["command"])
                self.assertIn("--prompt-file", state["agent_runs"][2]["command"])
                self.assertTrue(os.path.exists(state["agent_runs"][0]["prompt_file"]))
                self.assertTrue(os.path.exists(state["agent_runs"][1]["prompt_file"]))
                self.assertTrue(os.path.exists(state["agent_runs"][2]["prompt_file"]))
                self.assertEqual(task["agent_run_id"], state["agent_runs"][2]["id"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
