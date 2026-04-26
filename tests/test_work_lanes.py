import unittest

from mew.work_lanes import (
    DELIBERATION_LANE,
    LANE_LAYOUT_LANE_SCOPED,
    LANE_LAYOUT_LEGACY,
    LANE_LAYOUT_UNSUPPORTED,
    LANE_ROLE_AUTHORITATIVE,
    LANE_ROLE_MIRROR,
    LANE_ROLE_SHADOW,
    LANE_ROLE_UNSUPPORTED,
    MIRROR_LANE,
    TINY_LANE,
    get_work_lane_view,
    get_work_todo_lane_view,
    list_supported_work_lanes,
)


class WorkLaneRegistryTests(unittest.TestCase):
    def test_work_lane_registry_lists_supported_lanes_in_order(self):
        lanes = list_supported_work_lanes()

        self.assertEqual([lane.name for lane in lanes], [TINY_LANE, MIRROR_LANE, DELIBERATION_LANE])
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
