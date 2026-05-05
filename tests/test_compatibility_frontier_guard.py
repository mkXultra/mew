import unittest
from unittest.mock import patch


class ActiveCompatibilityFrontierWorkLoopGuardTests(unittest.TestCase):
    def _frontier(self, *, guard_mode="block_finish"):
        return {
            "id": "compat-frontier-1",
            "status": "open",
            "failure_signature": {
                "kind": "runtime_failure",
                "fingerprint": "sha256:frontier",
                "family_key": "family:frontier",
                "failing_tests": ["tests/test_runtime.py::test_behavior"],
                "runtime_component_kind": "unknown",
            },
            "evidence_refs": [{"kind": "tool_call", "id": 1}],
            "anchors": [
                {
                    "id": "anchor-runtime-adapter",
                    "kind": "source_location",
                    "path": "src/runtime_adapter.py",
                    "line": 40,
                    "read_status": "unread",
                }
            ],
            "open_candidates": [
                {
                    "id": "candidate-runtime-adapter",
                    "kind": "path",
                    "path": "src/runtime_adapter.py",
                    "status": "unexplored",
                }
            ],
            "closure_state": {
                "state": "read_needed",
                "reason": "same-family compatibility frontier has open evidence obligations",
                "evidence_strength": "blocking",
                "guard_mode": guard_mode,
                "blocked_action_kinds": ["broad_verifier", "finish", "repeat_search"],
                "broad_verifier_allowed": False,
                "finish_allowed": False,
                "next_action": "read_file src/runtime_adapter.py:40",
            },
        }

    def _state_and_session(self, frontier):
        session = {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Repair compatibility frontier",
            "goal": "Close sibling compatibility obligations before broad verification.",
            "created_at": "2026-05-05T00:00:00Z",
            "updated_at": "2026-05-05T00:00:00Z",
            "tool_calls": [],
            "model_turns": [],
            "active_compatibility_frontier": frontier,
        }
        task = {
            "id": 1,
            "title": "Repair compatibility frontier",
            "description": "Close the active compatibility frontier.",
            "status": "todo",
            "kind": "coding",
        }
        return {"next_ids": {"work_model_turn": 1}, "tasks": [task], "work_sessions": [session]}, session, task

    def test_plan_work_model_turn_redirects_broad_verifier_with_frontier_guard_metrics(self):
        from mew.work_loop import plan_work_model_turn

        state, session, task = self._state_and_session(self._frontier())

        with patch(
            "mew.work_loop.call_model_json_with_retries",
            return_value={
                "summary": "rerun broad verifier",
                "action": {"type": "run_tests", "command": "pytest -q"},
            },
        ):
            planned = plan_work_model_turn(
                state,
                session,
                task,
                {"path": "auth.json"},
                allowed_read_roots=["."],
                allowed_write_roots=["."],
                allow_verify=True,
                act_mode="deterministic",
            )

        self.assertEqual(planned["action"]["type"], "read_file")
        self.assertEqual(planned["action"]["path"], "src/runtime_adapter.py")
        self.assertEqual(planned["action"]["line_start"], 20)
        guard = planned["model_metrics"]["active_compatibility_frontier_guard"]
        self.assertEqual(guard["frontier_id"], "compat-frontier-1")
        self.assertEqual(guard["blocked_action_kind"], "broad_verifier")
        self.assertEqual(guard["original_action_type"], "run_tests")
        self.assertEqual(guard["replacement_action_type"], "read_file")
        self.assertEqual(planned["action_plan"]["action"]["type"], "read_file")

    def test_plan_work_model_turn_does_not_block_prompt_nudge_frontier(self):
        from mew.work_loop import plan_work_model_turn

        state, session, task = self._state_and_session(self._frontier(guard_mode="prompt_nudge"))

        with patch(
            "mew.work_loop.call_model_json_with_retries",
            return_value={
                "summary": "rerun broad verifier",
                "action": {"type": "run_tests", "command": "pytest -q"},
            },
        ):
            planned = plan_work_model_turn(
                state,
                session,
                task,
                {"path": "auth.json"},
                allowed_read_roots=["."],
                allowed_write_roots=["."],
                allow_verify=True,
                act_mode="deterministic",
            )

        self.assertEqual(planned["action"]["type"], "run_tests")
        self.assertNotIn("active_compatibility_frontier_guard", planned["model_metrics"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
