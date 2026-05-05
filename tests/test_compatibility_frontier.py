import json
import unittest

from mew.compatibility_frontier import (
    build_failure_signature,
    category_overlap,
    family_transition,
    update_session_active_compatibility_frontier,
)
from mew.work_session import build_work_session_resume, format_work_session_resume


class CompatibilityFrontierTests(unittest.TestCase):
    def test_failure_signature_ignores_volatile_ids_and_temp_roots(self):
        agenda_a = {
            "source_tool_call_id": 1,
            "tool": "run_tests",
            "command": "/tmp/job-a/bin/python -m pytest tests/test_runtime.py::test_behavior",
            "cwd": "/tmp/job-a",
            "exit_code": 1,
            "error_lines": [
                "AttributeError: module 'runtime' has no attribute 'missing_feature'",
                "FAILED tests/test_runtime.py::test_behavior - AttributeError",
            ],
            "source_locations": [{"path": "/tmp/job-a/src/runtime_adapter.py", "line": "12"}],
            "symbols": ["missing_feature"],
        }
        call_a = {
            "id": 1,
            "tool": "run_tests",
            "status": "completed",
            "parameters": {
                "command": agenda_a["command"],
                "cwd": agenda_a["cwd"],
                "execution_contract": {"stage": "targeted", "proof_role": "targeted"},
            },
            "result": {"exit_code": 1},
        }
        agenda_b = {
            **agenda_a,
            "source_tool_call_id": 99,
            "command": "/tmp/job-b/bin/python -m pytest tests/test_runtime.py::test_behavior",
            "cwd": "/tmp/job-b",
            "source_locations": [{"path": "/tmp/job-b/src/runtime_adapter.py", "line": "12"}],
        }
        call_b = {
            **call_a,
            "id": 99,
            "parameters": {
                "command": agenda_b["command"],
                "cwd": agenda_b["cwd"],
                "execution_contract": {"stage": "targeted", "proof_role": "targeted"},
            },
        }

        signature_a = build_failure_signature(agenda_a, source_call=call_a)
        signature_b = build_failure_signature(agenda_b, source_call=call_b)

        self.assertEqual(signature_a["fingerprint"], signature_b["fingerprint"])
        self.assertEqual(signature_a["family_key"], signature_b["family_key"])
        self.assertNotEqual(signature_a["source_tool_call_id"], signature_b["source_tool_call_id"])

    def test_family_transition_detects_narrower_primary_categories(self):
        previous = {
            "failure_signature": {
                "family_key": "previous",
                "command_shape": "pytest tests/test_runtime.py",
                "token_categories": {
                    "error_tokens": ["assertionerror"],
                    "missing_symbol_tokens": [],
                    "failing_test_tokens": [
                        "tests/test_runtime.py::test_behavior_a",
                        "tests/test_runtime.py::test_behavior_b",
                    ],
                    "stack_anchor_tokens": ["src/runtime_adapter.py"],
                    "component_tokens": ["native_module"],
                    "platform_tokens": [],
                },
            }
        }
        new_signature = {
            "family_key": "new",
            "command_shape": "pytest tests/test_runtime.py",
            "token_categories": {
                "error_tokens": ["assertionerror"],
                "missing_symbol_tokens": [],
                "failing_test_tokens": ["tests/test_runtime.py::test_behavior_b"],
                "stack_anchor_tokens": ["src/runtime_adapter.py"],
                "component_tokens": ["native_module"],
                "platform_tokens": [],
            },
        }

        transition, overlap = family_transition(new_signature, previous)

        self.assertEqual(transition, "narrower")
        self.assertTrue(overlap["narrower"])
        self.assertIn("failing_test_tokens", overlap["narrowed_categories"])

    def test_runtime_and_platform_overlap_alone_does_not_move_family(self):
        previous_signature = {
            "family_key": "previous",
            "command_shape": "python -c import runtime",
            "token_categories": {
                "error_tokens": [],
                "missing_symbol_tokens": [],
                "failing_test_tokens": [],
                "stack_anchor_tokens": [],
                "component_tokens": ["native_module"],
                "platform_tokens": ["python-3.13"],
            },
        }
        new_signature = {
            "family_key": "new",
            "command_shape": "python -c import runtime",
            "token_categories": {
                "error_tokens": [],
                "missing_symbol_tokens": [],
                "failing_test_tokens": [],
                "stack_anchor_tokens": [],
                "component_tokens": ["native_module"],
                "platform_tokens": ["python-3.13"],
            },
        }

        overlap = category_overlap(new_signature, previous_signature)
        transition, _ = family_transition(new_signature, {"failure_signature": previous_signature})

        self.assertFalse(overlap["primary_overlap"])
        self.assertFalse(overlap["moved"])
        self.assertEqual(transition, "new")

    def test_equal_family_key_from_secondary_only_evidence_does_not_force_same_family(self):
        agenda_a = {
            "source_tool_call_id": 1,
            "tool": "run_command",
            "command": "python load_alpha.py",
            "cwd": "/repo",
            "exit_code": 1,
            "error_lines": ["dlopen build/alpha.so could not load entry 17"],
            "source_locations": [],
            "symbols": [],
        }
        agenda_b = {
            **agenda_a,
            "source_tool_call_id": 2,
            "command": "python load_beta.py",
            "error_lines": ["dlopen build/beta.so could not load entry 42"],
        }
        signature_a = build_failure_signature(
            agenda_a,
            source_call={
                "id": 1,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": agenda_a["command"], "cwd": agenda_a["cwd"]},
                "result": {"exit_code": 1},
            },
        )
        signature_b = build_failure_signature(
            agenda_b,
            source_call={
                "id": 2,
                "tool": "run_command",
                "status": "completed",
                "parameters": {"command": agenda_b["command"], "cwd": agenda_b["cwd"]},
                "result": {"exit_code": 1},
            },
        )

        transition, overlap = family_transition(signature_b, {"failure_signature": signature_a})

        self.assertEqual(signature_a["family_key"], signature_b["family_key"])
        self.assertNotEqual(signature_a["fingerprint"], signature_b["fingerprint"])
        self.assertFalse(overlap["primary_overlap"])
        self.assertEqual(transition, "new")

    def test_moved_family_transition_creates_new_frontier_and_preserves_prior_evidence_refs(self):
        previous_agenda = {
            "source_tool_call_id": 1,
            "tool": "run_tests",
            "command": "pytest tests/test_loader.py::test_load",
            "cwd": "/repo",
            "exit_code": 1,
            "error_lines": ["RuntimeError: behavior invocation failed"],
            "source_locations": [{"path": "/repo/src/loader.py", "line": "10"}],
            "symbols": [],
        }
        previous_signature = build_failure_signature(
            previous_agenda,
            source_call={
                "id": 1,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": previous_agenda["command"], "cwd": previous_agenda["cwd"]},
                "result": {"exit_code": 1},
            },
        )
        session = {
            "id": 8,
            "updated_at": "2026-05-05T00:00:00Z",
            "active_compatibility_frontier_ordinal": 1,
            "active_compatibility_frontier": {
                "id": "compat-frontier-8-1",
                "created_at": "2026-05-05T00:00:00Z",
                "failure_signature": previous_signature,
                "evidence_refs": [{"kind": "tool_call", "id": 1, "summary": "previous verifier evidence"}],
            },
        }
        moved_agenda = {
            "source_tool_call_id": 2,
            "tool": "run_tests",
            "command": "pytest tests/test_behavior.py::test_invoke",
            "cwd": "/repo",
            "exit_code": 1,
            "error_lines": ["RuntimeError: behavior invocation failed"],
            "source_locations": [{"path": "/repo/src/behavior.py", "line": "21"}],
            "symbols": [],
        }
        calls = [
            {
                "id": 2,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": moved_agenda["command"], "cwd": moved_agenda["cwd"]},
                "result": {"command": moved_agenda["command"], "cwd": moved_agenda["cwd"], "exit_code": 1},
            }
        ]

        frontier = update_session_active_compatibility_frontier(
            session,
            calls,
            verifier_failure_repair_agenda=moved_agenda,
            search_anchor_observations=[],
            current_time="2026-05-05T00:00:01Z",
        )

        self.assertEqual(frontier["family_transition"]["state"], "moved")
        self.assertEqual(frontier["family_transition"]["previous_frontier_id"], "compat-frontier-8-1")
        self.assertEqual(frontier["id"], "compat-frontier-8-2")
        self.assertTrue(any(ref.get("id") == 1 for ref in frontier["evidence_refs"]))
        self.assertTrue(any(ref.get("id") == 2 for ref in frontier["evidence_refs"]))

    def test_update_session_builds_frontier_from_reused_agenda_and_search_anchors(self):
        session = {"id": 7, "updated_at": "2026-05-05T00:00:00Z"}
        agenda = {
            "source_tool_call_id": 3,
            "tool": "run_tests",
            "command": "pytest tests/test_runtime.py::test_behavior",
            "cwd": "/repo",
            "exit_code": 1,
            "error_lines": [
                "Traceback (most recent call last):",
                "AttributeError: module 'runtime' has no attribute 'missing_feature'",
                "FAILED tests/test_runtime.py::test_behavior - AttributeError",
            ],
            "source_locations": [{"path": "/repo/src/runtime_adapter.py", "line": "12"}],
            "symbols": ["missing_feature"],
            "sibling_search_queries": ["missing_feature"],
        }
        calls = [
            {
                "id": 3,
                "tool": "run_tests",
                "status": "completed",
                "parameters": {"command": agenda["command"], "cwd": agenda["cwd"]},
                "result": {"command": agenda["command"], "cwd": agenda["cwd"], "exit_code": 1},
            }
        ]
        search_anchors = [
            {
                "tool": "search_text",
                "path": "src/runtime_adapter.py",
                "query": "missing_feature",
                "tool_call_id": 4,
                "first_match_line": 40,
            }
        ]

        frontier = update_session_active_compatibility_frontier(
            session,
            calls,
            verifier_failure_repair_agenda=agenda,
            search_anchor_observations=search_anchors,
            current_time="2026-05-05T00:00:01Z",
        )

        self.assertEqual(session["active_compatibility_frontier"], frontier)
        self.assertEqual(frontier["family_transition"]["state"], "new")
        self.assertEqual(frontier["failure_signature"]["source_tool_call_id"], 3)
        self.assertIn("missing_feature", frontier["failure_signature"]["token_categories"]["missing_symbol_tokens"])
        self.assertTrue(frontier["evidence_refs"])
        self.assertTrue(any(anchor["kind"] == "search_match" for anchor in frontier["anchors"]))
        self.assertTrue(any(candidate["kind"] == "symbol" for candidate in frontier["sibling_candidates"]))
        self.assertEqual(frontier["closure_state"]["state"], "read_needed")
        self.assertNotIn("Traceback (most recent call last):", json.dumps(frontier))
        self.assertNotIn("module 'runtime' has no attribute", json.dumps(frontier))

    def test_work_session_resume_updates_canonical_session_state_only_for_phase_1(self):
        stderr = "\n".join(
            [
                "Traceback (most recent call last):",
                '  File "/repo/src/runtime_adapter.py", line 12, in invoke',
                "    runtime.missing_feature()",
                "AttributeError: module 'runtime' has no attribute 'missing_feature'",
                "FAILED tests/test_runtime.py::test_behavior - AttributeError",
            ]
        )
        session = {
            "id": 11,
            "task_id": 1,
            "status": "active",
            "title": "Repair runtime behavior",
            "goal": "Use verifier output to drive the next edit.",
            "updated_at": "2026-05-05T00:00:00Z",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "run_tests",
                    "status": "completed",
                    "parameters": {"command": "pytest tests/test_runtime.py::test_behavior", "cwd": "/repo"},
                    "result": {
                        "command": "pytest tests/test_runtime.py::test_behavior",
                        "cwd": "/repo",
                        "exit_code": 1,
                        "stderr": stderr,
                    },
                    "error": "run_tests failed with exit_code=1",
                },
                {
                    "id": 2,
                    "tool": "search_text",
                    "status": "completed",
                    "parameters": {"path": "src", "query": "missing_feature"},
                    "result": {
                        "path": "src",
                        "query": "missing_feature",
                        "matches": ["src/runtime_adapter.py:40:def missing_feature_bridge():"],
                    },
                },
            ],
            "model_turns": [],
        }

        resume = build_work_session_resume(session)
        frontier = session["active_compatibility_frontier"]
        resume_frontier = resume["active_compatibility_frontier"]
        text = format_work_session_resume(resume)

        self.assertEqual(frontier["failure_signature"]["source_tool_call_id"], 1)
        self.assertEqual(resume_frontier["failure_signature"]["source_tool_call_id"], 1)
        self.assertEqual(frontier["family_transition"]["state"], "new")
        self.assertEqual(resume["search_anchor_observations"][0]["path"], "src/runtime_adapter.py")
        self.assertTrue(frontier["compact_summary"]["failure_signature"])
        self.assertTrue(resume_frontier["compact_summary"]["failure_signature"])
        self.assertTrue(resume_frontier["open_candidates"])
        self.assertIn("resume active compatibility frontier: read_file", resume["next_action"])
        self.assertIn("active_compatibility_frontier:", text)
        self.assertIn("compatibility_frontier_next: read_file", text)
        self.assertNotIn("module 'runtime' has no attribute", json.dumps(resume_frontier))


if __name__ == "__main__":
    unittest.main()
