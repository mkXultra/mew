import unittest

from mew.commands import _paired_write_batch_actions
from mew.work_loop import normalize_work_model_action


class WorkWriteScopeTests(unittest.TestCase):
    def test_non_core_allowed_write_root_batch_is_not_forced_into_src_mew_pair(self):
        raw_tools = [
            {
                "type": "write_file",
                "path": "experiments/mew-companion-log/companion_log.py",
                "content": "def main():\n    return 'ok'\n",
            },
            {
                "type": "write_file",
                "path": "experiments/mew-companion-log/tests/test_companion_log.py",
                "content": "from companion_log import main\n\n\ndef test_main():\n    assert main() == 'ok'\n",
            },
        ]
        action = normalize_work_model_action(
            {
                "action": {
                    "type": "batch",
                    "tools": raw_tools,
                }
            },
            allowed_write_roots=["experiments/mew-companion-log"],
        )

        self.assertEqual(action["type"], "batch")
        self.assertEqual(len(action["tools"]), 2)
        self.assertTrue(all(tool["dry_run"] for tool in action["tools"]))
        self.assertEqual(
            [tool["path"] for tool in action["tools"]],
            [
                "experiments/mew-companion-log/companion_log.py",
                "experiments/mew-companion-log/tests/test_companion_log.py",
            ],
        )
        executable = _paired_write_batch_actions(
            raw_tools,
            allowed_write_roots=["experiments/mew-companion-log"],
        )
        self.assertEqual([tool["path"] for tool in executable], [tool["path"] for tool in raw_tools])
        self.assertTrue(all(tool["dry_run"] for tool in executable))

    def test_non_core_write_batch_still_respects_declared_write_roots(self):
        action = normalize_work_model_action(
            {
                "action": {
                    "type": "batch",
                    "tools": [
                        {
                            "type": "write_file",
                            "path": "experiments/mew-companion-log/companion_log.py",
                            "content": "def main():\n    return 'ok'\n",
                        },
                        {
                            "type": "write_file",
                            "path": "other-project/tests/test_companion_log.py",
                            "content": "def test_main():\n    assert True\n",
                        },
                    ],
                }
            },
            allowed_write_roots=["experiments/mew-companion-log"],
        )

        self.assertEqual(action["type"], "wait")
        self.assertIn("outside the declared allowed_write_roots", action["reason"])

    def test_core_src_mew_batch_still_requires_paired_root_tests_edit(self):
        action = normalize_work_model_action(
            {
                "action": {
                    "type": "batch",
                    "tools": [
                        {
                            "type": "write_file",
                            "path": "src/mew/example.py",
                            "content": "VALUE = 1\n",
                        },
                        {
                            "type": "write_file",
                            "path": "docs/example.md",
                            "content": "example\n",
                        },
                    ],
                }
            },
            allowed_write_roots=["."],
        )

        self.assertEqual(action["type"], "wait")
        self.assertIn("tests/** and src/mew/**", action["reason"])


if __name__ == "__main__":
    unittest.main()
