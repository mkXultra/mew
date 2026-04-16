import os
import tempfile
import unittest
from unittest.mock import patch

from mew.agent import plan_event
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

                records = read_model_traces(limit=1)
                self.assertEqual(len(records), 1)
                self.assertNotIn("prompt", records[0])
                self.assertEqual(records[0]["prompt_chars"], len("secret prompt"))
                self.assertEqual(len(records[0]["prompt_sha256"]), 64)

                records = read_model_traces(limit=1, include_prompt=True)
                self.assertEqual(records[0]["prompt"], "secret prompt")
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


if __name__ == "__main__":
    unittest.main()
