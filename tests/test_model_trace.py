import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from mew.agent import plan_event
from mew.cli import main
from mew.model_trace import append_model_trace, read_model_traces
from mew.state import add_event, default_state
from mew.timeutil import now_iso


class ModelTraceTests(unittest.TestCase):
    def test_append_and_read_model_trace_hides_prompt_by_default(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                append_model_trace(
                    at="now",
                    phase="think",
                    event={"id": 1, "type": "user_message"},
                    backend="codex",
                    model="test-model",
                    status="ok",
                    prompt="secret prompt",
                    plan={"summary": "ok", "decisions": []},
                )
                append_model_trace(
                    at="later",
                    phase="think_reflex",
                    event={"id": 1, "type": "user_message"},
                    backend="codex",
                    model="test-model",
                    status="ok",
                    prompt="reflex prompt",
                    plan={"summary": "reflex", "decisions": []},
                )

                records = read_model_traces(limit=1)
                self.assertEqual(len(records), 1)
                self.assertNotIn("prompt", records[0])
                self.assertEqual(records[0]["prompt_chars"], len("reflex prompt"))
                self.assertEqual(len(records[0]["prompt_sha256"]), 64)

                records = read_model_traces(limit=1, include_prompt=True, phase="think")
                self.assertEqual(records[0]["prompt"], "secret prompt")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["trace", "--phase", "think_reflex", "--json"]), 0)
                trace_data = json.loads(stdout.getvalue())
                self.assertEqual(trace_data["phase"], "think_reflex")
                self.assertEqual(len(trace_data["traces"]), 1)
                self.assertEqual(trace_data["traces"][0]["phase"], "think_reflex")
            finally:
                os.chdir(old_cwd)

    def test_plan_event_can_trace_think_and_act_prompts(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = default_state()
                event = add_event(state, "user_message", "test", {"text": "What next?"})

                responses = [
                    {
                        "summary": "think",
                        "decisions": [{"type": "remember", "summary": "think"}],
                    },
                    {
                        "summary": "act",
                        "actions": [{"type": "record_memory", "summary": "act"}],
                    },
                ]
                with patch("mew.agent.call_model_json", side_effect=responses):
                    decision_plan, action_plan = plan_event(
                        state,
                        event,
                        now_iso(),
                        model_auth={"access_token": "token"},
                        model="test-model",
                        base_url="https://example.invalid",
                        model_backend="codex",
                        trace_model=True,
                        log_phases=False,
                    )

                self.assertEqual(decision_plan["summary"], "think")
                self.assertEqual(action_plan["summary"], "act")
                records = read_model_traces(limit=5, include_prompt=True)
                self.assertEqual([record["phase"] for record in records], ["think", "act"])
                self.assertTrue(records[0]["prompt"].startswith("You are the THINK phase"))
                self.assertTrue(records[1]["prompt"].startswith("You are the ACT phase"))
                self.assertEqual(records[0]["plan"]["summary"], "think")
                self.assertEqual(records[1]["plan"]["summary"], "act")
            finally:
                os.chdir(old_cwd)

    def test_reflex_think_trace_is_labeled(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("README.md").write_text("reflex trace marker\n", encoding="utf-8")
                state = default_state()
                event = add_event(state, "user_message", "test", {"text": "inspect"})
                responses = [
                    {
                        "summary": "read",
                        "decisions": [{"type": "read_file", "path": "README.md"}],
                    },
                    {
                        "summary": "observed",
                        "decisions": [{"type": "remember", "summary": "observed"}],
                    },
                    {
                        "summary": "act",
                        "actions": [{"type": "record_memory", "summary": "act"}],
                    },
                ]

                with patch("mew.agent.call_model_json", side_effect=responses):
                    plan_event(
                        state,
                        event,
                        now_iso(),
                        model_auth={"access_token": "token"},
                        model="test-model",
                        base_url="https://example.invalid",
                        model_backend="codex",
                        trace_model=True,
                        log_phases=False,
                        allowed_read_roots=[tmp],
                        max_reflex_rounds=1,
                    )

                records = read_model_traces(limit=5)
                self.assertEqual([record["phase"] for record in records], ["think", "think_reflex", "act"])
                self.assertEqual(records[1]["plan"]["summary"], "observed")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
