import unittest

from mew.cli import build_parser
from mew.commands import _parse_chat_work_ai_args


class WorkDeliberationCliTests(unittest.TestCase):
    def test_work_parser_accepts_deliberation_controls(self):
        args = build_parser().parse_args(
            [
                "work",
                "17",
                "--live",
                "--deliberate",
                "--no-auto-deliberation",
                "--allow-read",
                ".",
            ]
        )

        self.assertEqual(args.task_id, "17")
        self.assertTrue(args.live)
        self.assertTrue(args.deliberate)
        self.assertTrue(args.no_auto_deliberation)

    def test_chat_work_ai_parser_accepts_deliberation_controls(self):
        args, error = _parse_chat_work_ai_args(
            [
                "live",
                "17",
                "--deliberate",
                "--no-auto-deliberation",
                "--allow-read",
                ".",
            ]
        )

        self.assertFalse(error)
        self.assertEqual(args.task_id, "17")
        self.assertTrue(args.deliberate)
        self.assertTrue(args.no_auto_deliberation)


if __name__ == "__main__":
    unittest.main()
