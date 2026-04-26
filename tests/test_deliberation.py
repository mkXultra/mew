import unittest

from mew.deliberation import (
    DELIBERATION_BUDGET_POLICY_VERSION,
    DELIBERATION_COST_EVENT_BUDGET_BLOCKED,
    DELIBERATION_COST_EVENT_BUDGET_CHECKED,
    DELIBERATION_COST_EVENT_BUDGET_RESERVED,
    DELIBERATION_COST_EVENT_FALLBACK_TO_TINY,
    DELIBERATION_RESULT_SCHEMA_CONTRACT,
    append_deliberation_decision_to_session,
    build_deliberation_fallback_event,
    evaluate_deliberation_request,
    normalize_deliberation_binding,
    validate_deliberation_result,
)


class DeliberationPolicyTests(unittest.TestCase):
    def _binding(self):
        return {
            "backend": "codex",
            "model": "gpt-5.5",
            "requested_effort": "high",
            "timeout_seconds": 120,
            "schema_contract": DELIBERATION_RESULT_SCHEMA_CONTRACT,
        }

    def test_normalize_deliberation_binding_logs_requested_and_effective_values(self):
        binding = normalize_deliberation_binding(self._binding())

        self.assertTrue(binding["configured"])
        self.assertEqual(binding["requested_backend"], "codex")
        self.assertEqual(binding["requested_model"], "gpt-5.5")
        self.assertEqual(binding["requested_effort"], "high")
        self.assertEqual(binding["effective_backend"], "codex")
        self.assertEqual(binding["effective_model"], "gpt-5.5")
        self.assertEqual(binding["effective_effort"], "high")
        self.assertEqual(binding["effort_resolution_reason"], "accepted")
        self.assertEqual(binding["timeout_seconds"], 120)
        self.assertEqual(binding["schema_contract"], DELIBERATION_RESULT_SCHEMA_CONTRACT)

    def test_normalize_deliberation_binding_rejects_unsupported_effort(self):
        binding = normalize_deliberation_binding(
            {
                "backend": "codex",
                "model": "gpt-5.5",
                "requested_effort": "ultra",
                "timeout_seconds": 120,
            }
        )

        self.assertFalse(binding["configured"])
        self.assertIn("effort", binding["missing_fields"])
        self.assertEqual(binding["requested_effort"], "ultra")
        self.assertEqual(binding["effective_effort"], "")
        self.assertEqual(binding["effort_resolution_reason"], "unsupported_effort")

    def test_reviewer_command_allowed_under_binding_and_budget(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-17", "lane": "tiny"},
            blocker_code="no_material_change",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 2, "attempts_used": 0},
            reviewer_commanded=True,
            created_at="2026-04-26T09:10:00Z",
        )

        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["decision"], "attempt")
        self.assertEqual(decision["reason"], "reviewer_commanded")
        self.assertEqual(decision["lane"], "deliberation")
        self.assertEqual(decision["fallback_lane"], "tiny")
        self.assertEqual(decision["lane_attempt_id"], "lane-deliberation-todo-17-attempt-1")
        self.assertEqual(
            [event["event"] for event in decision["cost_events"]],
            [DELIBERATION_COST_EVENT_BUDGET_CHECKED, DELIBERATION_COST_EVENT_BUDGET_RESERVED],
        )
        self.assertEqual(decision["budget_snapshot"]["reserved"]["attempts"], 1)
        self.assertEqual(decision["budget_snapshot"]["remaining"]["attempts"], 1)
        self.assertEqual(
            decision["budget_snapshot"]["budget_policy_version"],
            DELIBERATION_BUDGET_POLICY_VERSION,
        )
        self.assertEqual(decision["binding"]["effective_model"], "gpt-5.5")
        self.assertEqual(decision["binding"]["effective_effort"], "high")

    def test_automatic_review_rejected_allowed_under_binding_and_budget(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-18", "lane": "tiny"},
            blocker_code="review_rejected",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
        )

        self.assertTrue(decision["allowed"])
        self.assertEqual(decision["reason"], "automatic_eligible")
        self.assertEqual(decision["budget_snapshot"]["remaining"]["attempts"], 0)

    def test_auto_deliberation_disabled_blocks_automatic_but_not_reviewer_command(self):
        blocked = evaluate_deliberation_request(
            todo={"id": "todo-18", "lane": "tiny"},
            blocker_code="review_rejected",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            reviewer_commanded=False,
            auto_deliberation_enabled=False,
        )
        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], "auto_deliberation_disabled")

        commanded = evaluate_deliberation_request(
            todo={"id": "todo-18", "lane": "tiny"},
            blocker_code="review_rejected",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            reviewer_commanded=True,
            auto_deliberation_enabled=False,
        )
        self.assertTrue(commanded["allowed"])
        self.assertEqual(commanded["reason"], "reviewer_commanded")

    def test_policy_limit_blocks_even_when_reviewer_commanded(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-19", "lane": "tiny"},
            blocker_code="write_policy_violation",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            reviewer_commanded=True,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "policy_limit")
        self.assertEqual(decision["fallback_lane"], "tiny")
        self.assertEqual(decision["cost_events"], [])

    def test_state_limit_blocks_before_budget(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-20", "lane": "tiny"},
            blocker_code="stale_cached_window_text",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 0, "attempts_used": 0},
            reviewer_commanded=True,
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "state_refresh_required")
        self.assertEqual(decision["cost_events"], [])

    def test_missing_binding_blocks_eligible_request(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-21", "lane": "tiny"},
            blocker_code="review_rejected",
            binding={},
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "missing_model_binding")
        self.assertFalse(decision["binding"]["configured"])

    def test_budget_exhaustion_records_block_and_fallback_cost_events(self):
        decision = evaluate_deliberation_request(
            todo={"id": "todo-22", "lane": "tiny"},
            blocker_code="review_rejected",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 1},
            created_at="2026-04-26T09:12:00Z",
        )

        self.assertFalse(decision["allowed"])
        self.assertEqual(decision["reason"], "budget_exceeded")
        self.assertEqual(
            [event["event"] for event in decision["cost_events"]],
            [
                DELIBERATION_COST_EVENT_BUDGET_CHECKED,
                DELIBERATION_COST_EVENT_BUDGET_BLOCKED,
                DELIBERATION_COST_EVENT_FALLBACK_TO_TINY,
            ],
        )
        self.assertEqual(decision["cost_events"][1]["reason"], "budget_exceeded")
        self.assertEqual(decision["cost_events"][2]["reason"], "budget_exceeded")

    def test_no_material_change_auto_requires_abstract_or_repeated_shape(self):
        blocked = evaluate_deliberation_request(
            todo={"id": "todo-23", "lane": "tiny"},
            blocker_code="no_material_change",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
        )
        abstract_allowed = evaluate_deliberation_request(
            todo={"id": "todo-23", "lane": "tiny"},
            blocker_code="no_material_change",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            task_shape="abstract",
        )

        self.assertFalse(blocked["allowed"])
        self.assertEqual(blocked["reason"], "ineligible_blocker")
        self.assertTrue(abstract_allowed["allowed"])
        self.assertEqual(abstract_allowed["reason"], "automatic_eligible")

    def test_non_schema_reviewer_command_requires_repeated_failure(self):
        first = evaluate_deliberation_request(
            todo={"id": "todo-24", "lane": "tiny"},
            blocker_code="model_returned_non_schema",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            reviewer_commanded=True,
        )
        repeated = evaluate_deliberation_request(
            todo={"id": "todo-24", "lane": "tiny"},
            blocker_code="model_returned_non_schema",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 1, "attempts_used": 0},
            reviewer_commanded=True,
            repeated=True,
        )

        self.assertFalse(first["allowed"])
        self.assertEqual(first["reason"], "schema_retry_required")
        self.assertTrue(repeated["allowed"])
        self.assertEqual(repeated["reason"], "reviewer_commanded")

    def test_build_deliberation_fallback_event_shape(self):
        event = build_deliberation_fallback_event(
            reason="timeout",
            todo_id="todo-25",
            blocker_code="review_rejected",
            lane_attempt_id="lane-deliberation-todo-25-attempt-1",
            created_at="2026-04-26T09:13:00Z",
        )

        self.assertEqual(
            event,
            {
                "event": "deliberation_fallback",
                "reason": "timeout",
                "fallback_lane": "tiny",
                "todo_id": "todo-25",
                "blocker_code": "review_rejected",
                "lane_attempt_id": "lane-deliberation-todo-25-attempt-1",
                "created_at": "2026-04-26T09:13:00Z",
            },
        )

    def test_append_deliberation_decision_to_session_records_attempt_and_cost_events(self):
        session = {"id": 12}
        decision = evaluate_deliberation_request(
            todo={"id": "todo-26", "lane": "tiny"},
            blocker_code="review_rejected",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 2, "attempts_used": 0},
            created_at="2026-04-26T09:14:00Z",
        )

        attempt = append_deliberation_decision_to_session(session, decision)

        self.assertEqual(attempt["lane"], "deliberation")
        self.assertEqual(attempt["fallback_lane"], "tiny")
        self.assertEqual(attempt["lane_attempt_id"], "lane-deliberation-todo-26-attempt-1")
        self.assertTrue(attempt["allowed"])
        self.assertEqual(attempt["decision"], "attempt")
        self.assertEqual(attempt["requested_model"], "gpt-5.5")
        self.assertEqual(attempt["effective_effort"], "high")
        self.assertEqual(attempt["schema_contract"], DELIBERATION_RESULT_SCHEMA_CONTRACT)
        self.assertEqual(session["deliberation_attempts"], [attempt])
        self.assertEqual(
            [event["event"] for event in session["deliberation_cost_events"]],
            [DELIBERATION_COST_EVENT_BUDGET_CHECKED, DELIBERATION_COST_EVENT_BUDGET_RESERVED],
        )
        self.assertEqual(
            session["latest_deliberation_result"],
            {
                "lane_attempt_id": "lane-deliberation-todo-26-attempt-1",
                "status": "reserved",
                "reason": "automatic_eligible",
                "fallback_lane": "tiny",
            },
        )

    def test_append_blocked_deliberation_decision_records_fallback_result(self):
        session = {"id": 13}
        decision = evaluate_deliberation_request(
            todo={"id": "todo-27", "lane": "tiny"},
            blocker_code="write_policy_violation",
            binding=self._binding(),
            budget={"max_attempts_per_todo": 2, "attempts_used": 0},
            reviewer_commanded=True,
        )

        attempt = append_deliberation_decision_to_session(session, decision)

        self.assertFalse(attempt["allowed"])
        self.assertEqual(attempt["reason"], "policy_limit")
        self.assertEqual(session["deliberation_cost_events"], [])
        self.assertEqual(
            session["latest_deliberation_result"],
            {
                "lane_attempt_id": "lane-deliberation-todo-27-attempt-1",
                "status": "fallback",
                "reason": "policy_limit",
                "fallback_lane": "tiny",
            },
        )

    def test_validate_deliberation_result_accepts_v1_contract(self):
        validation = validate_deliberation_result(
            {
                "kind": "deliberation_result",
                "schema_version": 1,
                "todo_id": "todo-28",
                "lane": "deliberation",
                "blocker_code": "review_rejected",
                "decision": "propose_patch_strategy",
                "situation": "Reviewer rejected the patch because the paired test was missing.",
                "reasoning_summary": "Add the source and paired test edit in the same patch.",
                "recommended_next": "retry_tiny",
                "expected_trace_candidate": True,
                "confidence": "high",
            },
            todo_id="todo-28",
            blocker_code="review_rejected",
        )

        self.assertTrue(validation["ok"])
        self.assertEqual(validation["reason"], "")
        self.assertEqual(validation["invalid_fields"], [])
        result = validation["result"]
        self.assertEqual(result["decision"], "propose_patch_strategy")
        self.assertTrue(result["expected_trace_candidate"])

    def test_validate_deliberation_result_rejects_non_schema_payload(self):
        validation = validate_deliberation_result(
            "raw prose",
            todo_id="todo-29",
            blocker_code="review_rejected",
        )

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["reason"], "non_schema")
        self.assertEqual(validation["result"], {})

    def test_validate_deliberation_result_reports_invalid_fields(self):
        validation = validate_deliberation_result(
            {
                "kind": "message",
                "schema_version": 2,
                "todo_id": "other",
                "lane": "tiny",
                "blocker_code": "wrong",
                "decision": "freeform",
                "situation": "",
                "reasoning_summary": "",
                "recommended_next": "apply_patch",
                "confidence": "certain",
            },
            todo_id="todo-30",
            blocker_code="review_rejected",
        )

        self.assertFalse(validation["ok"])
        self.assertEqual(validation["reason"], "validation_failed")
        self.assertEqual(
            validation["invalid_fields"],
            [
                "kind",
                "schema_version",
                "todo_id",
                "lane",
                "blocker_code",
                "decision",
                "recommended_next",
                "confidence",
                "situation",
                "reasoning_summary",
            ],
        )


if __name__ == "__main__":
    unittest.main()
