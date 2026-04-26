import unittest
from unittest.mock import patch

from mew.work_loop import _attempt_work_deliberation_lane
from mew.work_session import apply_work_session_trace_patch


class WorkDeliberationLoopTests(unittest.TestCase):
    def _context(self, blocker_code="review_rejected"):
        return {
            "current_time": "2026-04-26T09:30:00Z",
            "task": {
                "id": 17,
                "title": "Cross-file reviewer rejection",
                "description": "Repair a cross-file design issue after review_rejected.",
                "status": "todo",
                "kind": "coding",
            },
            "work_session": {
                "id": 12,
                "resume": {
                    "active_work_todo": {
                        "id": "todo-17-1",
                        "lane": "tiny",
                        "status": "blocked_on_patch",
                        "source": {
                            "plan_item": "Repair the reviewed source/test patch.",
                            "target_paths": ["src/mew/work_loop.py", "tests/test_work_deliberation_loop.py"],
                            "verify_command": "uv run python -m unittest tests.test_work_deliberation_loop",
                        },
                        "attempts": {"draft": 2, "review": 1},
                        "blocker": {
                            "code": blocker_code,
                            "detail": "Reviewer rejected the patch because the design fix was incomplete.",
                        },
                    },
                    "deliberation_attempts": [],
                    "recent_decisions": [],
                    "working_memory": {
                        "hypothesis": "The tiny lane needs one higher-level repair strategy.",
                    },
                },
            },
        }

    def test_deliberation_lane_returns_review_ready_result_and_trace_patch(self):
        model_output = {
            "kind": "deliberation_result",
            "schema_version": 1,
            "todo_id": "todo-17-1",
            "lane": "deliberation",
            "blocker_code": "review_rejected",
            "decision": "propose_patch_strategy",
            "situation": "The reviewer rejected a cross-file patch.",
            "reasoning_summary": "Keep tiny as the writer and retry with one paired source/test strategy.",
            "recommended_next": "retry_tiny",
            "expected_trace_candidate": True,
            "confidence": "high",
        }

        with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output) as call_model:
            result = _attempt_work_deliberation_lane(
                context=self._context(),
                model_auth={"kind": "test"},
                model="gpt-5.5",
                base_url="https://example.invalid",
                model_backend="codex",
                timeout=60,
                deliberation_requested=True,
                current_time="2026-04-26T09:30:00Z",
            )

        self.assertEqual(result["status"], "result_ready")
        self.assertEqual(result["action"]["type"], "wait")
        self.assertEqual(result["decision"]["reason"], "reviewer_commanded")
        self.assertEqual(result["metrics"]["effective_model"], "gpt-5.5")
        self.assertEqual(result["metrics"]["effective_effort"], "high")
        call_model.assert_called_once()

        session = {}
        self.assertTrue(apply_work_session_trace_patch(session, result["trace_patch"]))
        self.assertEqual(session["deliberation_attempts"][0]["lane_attempt_id"], "lane-deliberation-todo-17-1-attempt-1")
        self.assertEqual(session["latest_deliberation_result"]["status"], "result_ready")
        self.assertEqual(
            [event["event"] for event in session["deliberation_cost_events"]],
            ["budget_checked", "budget_reserved"],
        )

    def test_deliberation_lane_non_schema_falls_back_to_tiny_trace(self):
        with patch("mew.work_loop.call_model_json_with_retries", return_value="raw prose") as call_model:
            result = _attempt_work_deliberation_lane(
                context=self._context(),
                model_auth={"kind": "test"},
                model="gpt-5.5",
                base_url="https://example.invalid",
                model_backend="codex",
                timeout=60,
                current_time="2026-04-26T09:31:00Z",
            )

        self.assertEqual(result["status"], "fallback")
        self.assertEqual(result["metrics"]["status"], "fallback")
        self.assertEqual(result["metrics"]["reason"], "non_schema")
        call_model.assert_called_once()

        session = {}
        self.assertTrue(apply_work_session_trace_patch(session, result["trace_patch"]))
        self.assertEqual(session["latest_deliberation_result"]["status"], "fallback")
        self.assertEqual(session["latest_deliberation_result"]["reason"], "non_schema")
        self.assertIn(
            "deliberation_fallback",
            [event["event"] for event in session["deliberation_cost_events"]],
        )

    def test_no_auto_deliberation_blocks_automatic_and_does_not_call_model(self):
        with patch("mew.work_loop.call_model_json_with_retries") as call_model:
            result = _attempt_work_deliberation_lane(
                context=self._context(),
                model_auth={"kind": "test"},
                model="gpt-5.5",
                base_url="https://example.invalid",
                model_backend="codex",
                timeout=60,
                auto_deliberation=False,
                current_time="2026-04-26T09:31:30Z",
            )

        self.assertEqual(result["status"], "preflight_blocked")
        self.assertEqual(result["metrics"]["status"], "fallback")
        self.assertEqual(result["metrics"]["reason"], "auto_deliberation_disabled")
        call_model.assert_not_called()

    def test_deliberate_overrides_disabled_auto_deliberation(self):
        model_output = {
            "kind": "deliberation_result",
            "schema_version": 1,
            "todo_id": "todo-17-1",
            "lane": "deliberation",
            "blocker_code": "review_rejected",
            "decision": "propose_patch_strategy",
            "situation": "The reviewer rejected a cross-file patch.",
            "reasoning_summary": "Retry tiny with the reviewer invariant first.",
            "recommended_next": "retry_tiny",
            "expected_trace_candidate": True,
            "confidence": "medium",
        }

        with patch("mew.work_loop.call_model_json_with_retries", return_value=model_output) as call_model:
            result = _attempt_work_deliberation_lane(
                context=self._context(),
                model_auth={"kind": "test"},
                model="gpt-5.5",
                base_url="https://example.invalid",
                model_backend="codex",
                timeout=60,
                deliberation_requested=True,
                auto_deliberation=False,
                current_time="2026-04-26T09:31:45Z",
            )

        self.assertEqual(result["status"], "result_ready")
        self.assertEqual(result["decision"]["reason"], "reviewer_commanded")
        call_model.assert_called_once()

    def test_deliberation_lane_state_limited_blocker_does_not_call_model(self):
        with patch("mew.work_loop.call_model_json_with_retries") as call_model:
            result = _attempt_work_deliberation_lane(
                context=self._context(blocker_code="stale_cached_window_text"),
                model_auth={"kind": "test"},
                model="gpt-5.5",
                base_url="https://example.invalid",
                model_backend="codex",
                timeout=60,
                current_time="2026-04-26T09:32:00Z",
            )

        self.assertEqual(result["status"], "preflight_blocked")
        self.assertEqual(result["metrics"]["status"], "fallback")
        self.assertEqual(result["metrics"]["reason"], "state_refresh_required")
        call_model.assert_not_called()


if __name__ == "__main__":
    unittest.main()
