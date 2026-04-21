import unittest

from mew.context_checkpoint import _parse_git_status_short


class ContextCheckpointTests(unittest.TestCase):
    def test_parse_git_status_short_marks_untracked_only(self):
        parsed = _parse_git_status_short("?? auth.plus.json\n?? auth.pro.json\n")

        self.assertEqual(parsed["status"], "untracked_only")
        self.assertEqual(parsed["dirty_paths"], ["auth.plus.json", "auth.pro.json"])
        self.assertEqual(parsed["tracked_dirty_paths"], [])
        self.assertEqual(parsed["untracked_paths"], ["auth.plus.json", "auth.pro.json"])

    def test_parse_git_status_short_keeps_tracked_dirty(self):
        parsed = _parse_git_status_short(" M src/mew/brief.py\n?? auth.plus.json\n")

        self.assertEqual(parsed["status"], "dirty")
        self.assertEqual(parsed["dirty_paths"], ["src/mew/brief.py", "auth.plus.json"])
        self.assertEqual(parsed["tracked_dirty_paths"], ["src/mew/brief.py"])
        self.assertEqual(parsed["untracked_paths"], ["auth.plus.json"])


if __name__ == "__main__":
    unittest.main()
