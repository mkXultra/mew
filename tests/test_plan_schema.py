import unittest

from mew.plan_schema import ACTION_TYPES, DECISION_TYPES, validate_plan_items


class PlanSchemaTests(unittest.TestCase):
    def test_accepts_supported_item_with_required_fields(self):
        issues = validate_plan_items(
            [{"type": "write_file", "path": "src/file.py", "content": "print('ok')"}],
            ACTION_TYPES,
            "actions",
        )

        self.assertEqual(issues, [])

    def test_reports_warning_for_non_object_item(self):
        issues = validate_plan_items(["bad"], ACTION_TYPES, "actions")

        self.assertEqual(
            issues,
            [{"level": "warning", "path": "actions[0]", "message": "must be an object"}],
        )

    def test_reports_warning_for_unsupported_type(self):
        issues = validate_plan_items(
            [{"type": "unknown", "path": "src/file.py"}],
            ACTION_TYPES,
            "actions",
        )

        self.assertEqual(
            issues,
            [
                {
                    "level": "warning",
                    "path": "actions[0].type",
                    "message": "unsupported type 'unknown'",
                }
            ],
        )

    def test_reports_error_for_blank_required_string(self):
        issues = validate_plan_items(
            [{"type": "send_message", "text": "   "}],
            ACTION_TYPES,
            "actions",
        )

        self.assertEqual(
            issues,
            [
                {
                    "level": "error",
                    "path": "actions[0].text",
                    "message": "required for this type",
                }
            ],
        )

    def test_reports_error_for_missing_required_non_string(self):
        issues = validate_plan_items(
            [{"type": "execute_task"}],
            DECISION_TYPES,
            "decisions",
        )

        self.assertEqual(
            issues,
            [
                {
                    "level": "error",
                    "path": "decisions[0].task_id",
                    "message": "required for this type",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()