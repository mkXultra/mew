import unittest
import os
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from mew.cli import build_parser
from mew.commands import _parse_chat_work_ai_args, cmd_work_ai
from mew.state import load_state, save_state, state_lock
from mew.work_session import create_work_session


class WorkDeliberationCliTests(unittest.TestCase):
    def _seed_blocked_session(self):
        with state_lock():
            state = load_state()
            task = {
                "id": 1,
                "title": "Cross-file reviewer rejection",
                "description": "Repair a cross-file design issue after review_rejected.",
                "status": "todo",
                "priority": "normal",
                "kind": "coding",
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
                "created_at": "2026-04-26T09:40:00Z",
                "updated_at": "2026-04-26T09:40:00Z",
            }
            state["tasks"].append(task)
            session, _created = create_work_session(state, task)
            target_paths = ["src/mew/work_loop.py", "tests/test_work_deliberation_loop.py"]
            plan_item = "Repair the reviewed source/test patch."
            session["startup_memory"] = {
                "plan_items": [plan_item],
                "target_paths": target_paths,
            }
            session["tool_calls"] = [
                {
                    "id": index,
                    "tool": "read_file",
                    "status": "completed",
                    "parameters": {"path": path, "offset": 0},
                    "result": {
                        "path": path,
                        "text": "line 1\n",
                        "offset": 0,
                        "next_offset": "",
                        "line_start": 1,
                        "line_end": 1,
                        "has_more_lines": False,
                        "context_truncated": False,
                    },
                }
                for index, path in enumerate(target_paths, start=1)
            ]
            session["active_work_todo"] = {
                "id": "todo-1-1",
                "lane": "tiny",
                "status": "blocked_on_patch",
                "source": {
                    "plan_item": plan_item,
                    "target_paths": target_paths,
                    "verify_command": "uv run python -m unittest tests.test_work_deliberation_loop",
                },
                "attempts": {"draft": 2, "review": 1},
                "blocker": {
                    "code": "review_rejected",
                    "detail": "Reviewer rejected the patch because the design fix was incomplete.",
                },
                "created_at": "2026-04-26T09:40:00Z",
                "updated_at": "2026-04-26T09:40:00Z",
            }
            save_state(state)
            return task, session

    def _work_args(self, *extra):
        return build_parser().parse_args(
            [
                "work",
                "1",
                "--ai",
                "--auth",
                "auth.json",
                "--model-backend",
                "codex",
                "--model",
                "gpt-5.5",
                "--max-steps",
                "1",
                "--act-mode",
                "deterministic",
                "--allow-read",
                ".",
                "--quiet",
                "--json",
                *extra,
            ]
        )

    def _deliberation_payload(self, reason="Retry tiny with the reviewer invariant first."):
        return {
            "kind": "deliberation_result",
            "schema_version": 1,
            "todo_id": "todo-1-1",
            "lane": "deliberation",
            "blocker_code": "review_rejected",
            "decision": "propose_patch_strategy",
            "situation": "The reviewer rejected a cross-file patch.",
            "reasoning_summary": reason,
            "recommended_next": "retry_tiny",
            "expected_trace_candidate": True,
            "confidence": "high",
        }

    def test_work_parser_accepts_deliberation_controls(self):
        args = build_parser().parse_args(
            [
                "work",
                "17",
                "--live",
                "--deliberate",
                "--no-auto-deliberation",
                "--allow-read",
                ".",
            ]
        )

        self.assertEqual(args.task_id, "17")
        self.assertTrue(args.live)
        self.assertTrue(args.deliberate)
        self.assertTrue(args.no_auto_deliberation)

    def test_chat_work_ai_parser_accepts_deliberation_controls(self):
        args, error = _parse_chat_work_ai_args(
            [
                "live",
                "17",
                "--deliberate",
                "--no-auto-deliberation",
                "--allow-read",
                ".",
            ]
        )

        self.assertFalse(error)
        self.assertEqual(args.task_id, "17")
        self.assertTrue(args.deliberate)
        self.assertTrue(args.no_auto_deliberation)

    def test_work_ai_deliberate_persists_reviewer_commanded_trace(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                self._seed_blocked_session()
                model_calls = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    model_calls.append(str(log_prefix or ""))
                    return self._deliberation_payload()

                with patch("mew.commands.load_model_auth", return_value={"kind": "test"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()):
                            exit_code = cmd_work_ai(self._work_args("--deliberate"))

                self.assertEqual(exit_code, 0)
                self.assertTrue(any("work_deliberation" in call for call in model_calls))
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["deliberation_attempts"][0]["reason"], "reviewer_commanded")
                self.assertEqual(session["latest_deliberation_result"]["status"], "result_ready")
            finally:
                os.chdir(old_cwd)

    def test_work_ai_automatic_eligible_persists_trace_without_explicit_deliberate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                self._seed_blocked_session()

                with patch("mew.commands.load_model_auth", return_value={"kind": "test"}):
                    with patch(
                        "mew.work_loop.call_model_json_with_retries",
                        return_value=self._deliberation_payload("Automatic escalation found the same retry strategy."),
                    ):
                        with redirect_stdout(StringIO()):
                            exit_code = cmd_work_ai(self._work_args())

                self.assertEqual(exit_code, 0)
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["deliberation_attempts"][0]["reason"], "automatic_eligible")
                self.assertEqual(session["latest_deliberation_result"]["status"], "result_ready")
            finally:
                os.chdir(old_cwd)

    def test_work_ai_no_auto_deliberation_records_fallback_and_keeps_tiny_callable(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                self._seed_blocked_session()
                model_calls = []

                def fake_model(model_backend, model_auth, prompt, model, base_url, timeout, log_prefix=None, **kwargs):
                    model_calls.append(str(log_prefix or ""))
                    return {
                        "summary": "tiny fallback still callable",
                        "action": {"type": "wait", "reason": "tiny fallback still callable"},
                    }

                with patch("mew.commands.load_model_auth", return_value={"kind": "test"}):
                    with patch("mew.work_loop.call_model_json_with_retries", side_effect=fake_model):
                        with redirect_stdout(StringIO()):
                            exit_code = cmd_work_ai(self._work_args("--no-auto-deliberation"))

                self.assertEqual(exit_code, 0)
                self.assertFalse(any("work_deliberation" in call for call in model_calls))
                self.assertTrue(model_calls)
                state = load_state()
                session = state["work_sessions"][0]
                self.assertEqual(session["deliberation_attempts"][0]["reason"], "auto_deliberation_disabled")
                self.assertEqual(session["latest_deliberation_result"]["status"], "fallback")
                self.assertEqual(session["model_turns"][-1]["action"]["reason"], "tiny fallback still callable")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
