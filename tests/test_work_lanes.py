import unittest

from mew.work_lanes import (
    DELIBERATION_LANE,
    IMPLEMENT_V1_LANE,
    IMPLEMENT_V2_LANE,
    LANE_LAYOUT_LANE_SCOPED,
    LANE_LAYOUT_LEGACY,
    LANE_LAYOUT_UNSUPPORTED,
    LANE_ROLE_AUTHORITATIVE,
    LANE_ROLE_MIRROR,
    LANE_ROLE_SHADOW,
    LANE_ROLE_UNSUPPORTED,
    MIRROR_LANE,
    TINY_LANE,
    build_lane_attempt_event,
    get_work_lane_view,
    get_work_todo_lane_view,
    list_supported_work_lanes,
)


class WorkLaneRegistryTests(unittest.TestCase):
    def test_work_lane_registry_lists_supported_lanes_in_order(self):
        lanes = list_supported_work_lanes()

        self.assertEqual(
            [lane.name for lane in lanes],
            [TINY_LANE, IMPLEMENT_V1_LANE, IMPLEMENT_V2_LANE, MIRROR_LANE, DELIBERATION_LANE],
        )
        self.assertTrue(all(lane.supported for lane in lanes))

    def test_work_lane_tiny_is_authoritative_write_capable_legacy_lane(self):
        lane = get_work_lane_view(TINY_LANE)

        self.assertTrue(lane.supported)
        self.assertTrue(lane.authoritative)
        self.assertTrue(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_LEGACY)
        self.assertEqual(lane.role, LANE_ROLE_AUTHORITATIVE)
        self.assertFalse(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, TINY_LANE)
        self.assertTrue(lane.runtime_available)

    def test_work_lane_implement_v1_is_authoritative_lane_scoped_runtime(self):
        lane = get_work_lane_view(IMPLEMENT_V1_LANE)

        self.assertTrue(lane.supported)
        self.assertTrue(lane.authoritative)
        self.assertTrue(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_LANE_SCOPED)
        self.assertEqual(lane.role, LANE_ROLE_AUTHORITATIVE)
        self.assertFalse(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, TINY_LANE)
        self.assertTrue(lane.runtime_available)

    def test_work_lane_implement_v2_is_explicit_authoritative_runtime(self):
        lane = get_work_lane_view(IMPLEMENT_V2_LANE)

        self.assertTrue(lane.supported)
        self.assertTrue(lane.authoritative)
        self.assertTrue(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_LANE_SCOPED)
        self.assertEqual(lane.role, LANE_ROLE_AUTHORITATIVE)
        self.assertTrue(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, IMPLEMENT_V1_LANE)
        self.assertTrue(lane.runtime_available)

    def test_work_lane_mirror_is_non_authoritative_mirror_with_tiny_fallback(self):
        lane = get_work_lane_view(MIRROR_LANE)

        self.assertTrue(lane.supported)
        self.assertFalse(lane.authoritative)
        self.assertFalse(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_LANE_SCOPED)
        self.assertEqual(lane.role, LANE_ROLE_MIRROR)
        self.assertFalse(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, TINY_LANE)

    def test_work_lane_deliberation_is_shadow_model_bound_with_tiny_fallback(self):
        lane = get_work_lane_view(DELIBERATION_LANE)

        self.assertTrue(lane.supported)
        self.assertFalse(lane.authoritative)
        self.assertFalse(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_LANE_SCOPED)
        self.assertEqual(lane.role, LANE_ROLE_SHADOW)
        self.assertTrue(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, TINY_LANE)

    def test_work_lane_missing_or_empty_lookup_uses_legacy_tiny_default(self):
        for lane_value in (None, ""):
            with self.subTest(lane_value=lane_value):
                lane = get_work_lane_view(lane_value)
                self.assertEqual(lane.name, TINY_LANE)
                self.assertTrue(lane.supported)
                self.assertTrue(lane.write_capable)
                self.assertEqual(lane.role, LANE_ROLE_AUTHORITATIVE)
                self.assertEqual(lane.fallback_lane, TINY_LANE)

    def test_lane_attempt_event_defaults_to_tiny_implementation_with_v0_fields(self):
        event = build_lane_attempt_event(
            task_id=649,
            session_id=636,
            task_kind="coding",
            task_shape="bounded_source_test_patch",
            model_backend="codex",
            model="gpt-5.5",
            effort="high",
            timeout_seconds=60,
        )

        self.assertEqual(
            event,
            {
                "event": "lane_attempt",
                "task_id": 649,
                "session_id": 636,
                "task_kind": "coding",
                "lane": TINY_LANE,
                "lane_display_name": "implementation",
                "task_shape": "bounded_source_test_patch",
                "blocker_code": "",
                "model_backend": "codex",
                "model": "gpt-5.5",
                "effort": "high",
                "timeout_seconds": 60,
                "budget_reserved": None,
                "budget_spent_or_estimated": None,
                "first_output_latency_seconds": None,
                "first_edit_latency_seconds": None,
                "approval_rejected": False,
                "verifier_failed": False,
                "fallback_taken": False,
                "rescue_edit_used": False,
                "reviewer_decision": "",
                "outcome": "",
                "later_reuse_value": "unknown",
            },
        )

    def test_lane_attempt_event_preserves_unknown_lane_without_mutating_todo(self):
        todo = {"id": "todo-1-1", "lane": "experimental", "status": "drafting"}

        event = build_lane_attempt_event(
            task_id=1,
            session_id=2,
            task_kind="coding",
            lane=todo["lane"],
        )

        self.assertEqual(todo["lane"], "experimental")
        self.assertEqual(event["event"], "lane_attempt")
        self.assertEqual(event["lane"], "experimental")
        self.assertEqual(event["lane_display_name"], "unsupported")

    def test_work_lane_unknown_todo_lookup_is_unsupported_without_mutating_lane_string(self):
        todo = {"id": "todo-1-1", "lane": "experimental", "status": "drafting"}

        lane = get_work_todo_lane_view(todo)

        self.assertEqual(todo["lane"], "experimental")
        self.assertEqual(lane.name, "experimental")
        self.assertFalse(lane.supported)
        self.assertFalse(lane.authoritative)
        self.assertFalse(lane.write_capable)
        self.assertEqual(lane.layout, LANE_LAYOUT_UNSUPPORTED)
        self.assertEqual(lane.role, LANE_ROLE_UNSUPPORTED)
        self.assertFalse(lane.requires_model_binding)
        self.assertEqual(lane.fallback_lane, TINY_LANE)


if __name__ == "__main__":
    unittest.main()
