import unittest

from mew.tasks import (
    build_task_selector_proposal,
    infer_task_kind,
    normalize_task_id,
    normalize_task_scope,
    task_kind,
    task_kind_report,
    task_needs_programmer_plan,
    task_question,
    task_scope_target_paths,
    task_sort_key,
)


class TaskKindTests(unittest.TestCase):
    def test_normalize_task_id_accepts_display_ids(self):
        self.assertEqual(normalize_task_id("#12"), 12)
        self.assertEqual(normalize_task_id(" 12 "), 12)
        self.assertIsNone(normalize_task_id("#abc"))

    def test_infer_task_kind_handles_collision_words(self):
        self.assertEqual(infer_task_kind("Research API pricing"), "research")
        self.assertEqual(infer_task_kind("Pay API invoice"), "admin")
        self.assertEqual(infer_task_kind("Review tax documents"), "admin")
        self.assertEqual(infer_task_kind("補助金について調べる"), "research")
        self.assertEqual(infer_task_kind("Fix the broken kitchen faucet"), "unknown")
        self.assertEqual(infer_task_kind("Implement API client"), "coding")
        self.assertEqual(infer_task_kind("Implement tax calculator"), "coding")
        self.assertEqual(infer_task_kind("Implement email parser"), "coding")
        self.assertEqual(infer_task_kind("Investigate a mew CLI test failure in wait_outbox"), "coding")
        self.assertEqual(infer_task_kind("Fix unit test failure"), "coding")
        self.assertEqual(infer_task_kind("Return JSON from API"), "coding")

    def test_infer_task_kind_does_not_let_housekeeping_notes_dominate(self):
        self.assertEqual(
            infer_task_kind(
                "補助金について調べる",
                description="利用可能な補助金を調査する。",
                notes="Proposed by mew from event #1.",
            ),
            "research",
        )

    def test_task_kind_prefers_explicit_override(self):
        task = {
            "title": "Research API pricing",
            "kind": "coding",
        }

        self.assertEqual(task_kind(task), "coding")

    def test_task_kind_report_detects_explicit_mismatch(self):
        report = task_kind_report({"id": 1, "title": "補助金について調べる", "kind": "coding", "status": "todo"})

        self.assertEqual(report["stored_kind"], "coding")
        self.assertEqual(report["inferred_kind"], "research")
        self.assertEqual(report["effective_kind"], "coding")
        self.assertTrue(report["mismatch"])

    def test_task_kind_report_does_not_treat_unknown_inference_as_mismatch(self):
        report = task_kind_report({"id": 1, "title": "Ambiguous thing", "kind": "coding", "status": "todo"})

        self.assertEqual(report["inferred_kind"], "unknown")
        self.assertFalse(report["mismatch"])

    def test_task_selector_proposal_requires_approval(self):
        proposal = build_task_selector_proposal(
            {"id": 10, "title": "Previous task"},
            {"id": 11, "title": "Implement bounded selector"},
            "M6.8 next bounded roadmap task",
        )

        self.assertEqual(proposal["previous_task_id"], 10)
        self.assertEqual(proposal["proposed_task_id"], 11)
        self.assertEqual(proposal["proposed_task_title"], "Implement bounded selector")
        self.assertEqual(proposal["selector_reason"], "M6.8 next bounded roadmap task")
        self.assertTrue(proposal["approval_required"])
        self.assertEqual(proposal["memory_signal_refs"], [])
        self.assertEqual(proposal["failure_cluster_reason"], "")
        self.assertEqual(proposal["preference_signal_refs"], [])
        self.assertFalse(proposal["blocked"])
        self.assertEqual(proposal["blocked_reason"], "")
        self.assertFalse(proposal["governance_violation"])

    def test_task_selector_proposal_preserves_optional_signal_refs(self):
        proposal = build_task_selector_proposal(
            {"id": 10},
            {"title": "Investigate next coding task"},
            "Recent failure makes this bounded follow-up useful",
            memory_signal_refs=("memory://task/10",),
            failure_cluster_reason="same verifier failure cluster",
            preference_signal_refs=["preference://small-patches"],
        )

        self.assertIsNone(proposal["proposed_task_id"])
        self.assertEqual(proposal["proposed_task_title"], "Investigate next coding task")
        self.assertEqual(proposal["memory_signal_refs"], ["memory://task/10"])
        self.assertEqual(proposal["failure_cluster_reason"], "same verifier failure cluster")
        self.assertEqual(proposal["preference_signal_refs"], ["preference://small-patches"])
        self.assertTrue(proposal["approval_required"])

    def test_task_selector_proposal_formats_detail_reason(self):
        proposal = build_task_selector_proposal(
            {"id": 10},
            {
                "id": 11,
                "title": "Dispatch next selector slice",
                "scope": {"target_paths": ["src/mew/tasks.py", "tests/test_tasks.py"]},
            },
            {
                "lane-dispatch": "choose the active implementation lane",
                "reviewer-gated": "wait for approval before switching tasks",
                "meta-loop": "avoid recursive selector churn",
                "expected-value": "prefer the highest bounded payoff",
            },
        )

        self.assertEqual(
            proposal["selector_reason"],
            "lane-dispatch: choose the active implementation lane\n"
            "reviewer-gated: wait for approval before switching tasks\n"
            "meta-loop: avoid recursive selector churn\n"
            "expected-value: prefer the highest bounded payoff",
        )
        self.assertTrue(proposal["approval_required"])
        lane_dispatch = proposal["lane_dispatch"]
        self.assertEqual(lane_dispatch["authoritative_lane"], "tiny")
        self.assertEqual(lane_dispatch["helper_lanes"], ["deliberation", "mirror"])
        self.assertEqual(lane_dispatch["fallback_lane"], "tiny")
        self.assertEqual(lane_dispatch["verifier"], "uv run python -m unittest tests.test_tasks")
        self.assertIn("reviewer approval", lane_dispatch["budget"])
        self.assertIn("tiny is the implementation default", lane_dispatch["expected_value_rationale"])
        self.assertEqual(
            lane_dispatch["repair_route"],
            "M6.14 repair episode for structural implementation-lane failures",
        )
        self.assertEqual(lane_dispatch["reviewer_gate"], "approval_required")

    def test_task_selector_proposal_blocks_governance_and_status_targets(self):
        proposal = build_task_selector_proposal(
            {"id": 10},
            {
                "id": 12,
                "title": "Close milestone and update governance",
                "description": "Edit ROADMAP_STATUS.md after policy review.",
                "notes": "Requires permissions and skills updates.",
                "scope": {"target_paths": ["ROADMAP_STATUS.md"]},
            },
            "Governance target should be flagged, not executed",
        )

        self.assertTrue(proposal["approval_required"])
        self.assertTrue(proposal["blocked"])
        self.assertTrue(proposal["governance_violation"])
        self.assertIn("ROADMAP_STATUS.md", proposal["blocked_reason"])

    def test_task_selector_proposal_allows_guardrail_context_in_description(self):
        proposal = build_task_selector_proposal(
            {"id": 12},
            {
                "id": 13,
                "title": "Fix selector target-surface false positive",
                "description": (
                    "Refine coding task detection while preserving governance/status "
                    "guardrails around ROADMAP_STATUS.md, policy, permissions, and skills."
                ),
                "kind": "coding",
                "scope": {"target_paths": ["src/mew/tasks.py", "tests/test_tasks.py"]},
            },
            "Safe coding task that describes guardrails without targeting them",
        )

        self.assertTrue(proposal["approval_required"])
        self.assertFalse(proposal["blocked"])
        self.assertFalse(proposal["governance_violation"])
        self.assertEqual(proposal["blocked_reason"], "")

    def test_normalize_task_scope_requires_matching_source_test_pair(self):
        self.assertEqual(
            normalize_task_scope({"target_paths": ["tests/test_commands.py", "./src/mew/commands.py"]}),
            {"target_paths": ["src/mew/commands.py", "tests/test_commands.py"]},
        )
        self.assertEqual(
            normalize_task_scope({"target_paths": ["src/mew/commands.py", "tests/test_work_session.py"]}),
            {},
        )

    def test_task_scope_target_paths_returns_normalized_pair(self):
        self.assertEqual(
            task_scope_target_paths({"scope": {"target_paths": ["./tests/test_tasks.py", "src/mew/tasks.py"]}}),
            ["src/mew/tasks.py", "tests/test_tasks.py"],
        )

    def test_running_tasks_sort_before_ready_tasks(self):
        tasks = [
            {"id": 1, "status": "ready", "priority": "high", "created_at": "1"},
            {"id": 2, "status": "running", "priority": "normal", "created_at": "2"},
        ]

        self.assertEqual([task["id"] for task in sorted(tasks, key=task_sort_key)], [2, 1])

    def test_task_needs_programmer_plan_uses_resolvable_latest_plan(self):
        task = {
            "title": "Implement API client",
            "kind": "coding",
            "status": "todo",
            "plans": [],
            "latest_plan_id": 99,
        }
        self.assertTrue(task_needs_programmer_plan(task))

        task["plans"] = [{"id": 1, "status": "planned"}]
        self.assertFalse(task_needs_programmer_plan(task))

    def test_ready_research_task_question_does_not_ask_for_command_execution(self):
        question = task_question(
            {
                "id": 20,
                "title": "補助金について調べる",
                "kind": "research",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )

        self.assertIn("ready research work", question)
        self.assertIn("research criteria", question)
        self.assertNotIn("What should I execute", question)

    def test_ready_coding_task_question_points_to_coding_cockpit(self):
        question = task_question(
            {
                "id": 21,
                "title": "Implement runtime cleanup",
                "kind": "coding",
                "status": "ready",
                "command": "",
                "agent_backend": "",
            }
        )

        self.assertIn("ready coding work", question)
        self.assertIn("./mew code 21", question)
        self.assertIn("add constraints", question)
        self.assertNotIn("dispatch it to an agent", question)


if __name__ == "__main__":
    unittest.main()
