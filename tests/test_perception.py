import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.perception import format_perception, perceive_workspace


class PerceptionTests(unittest.TestCase):
    def test_perception_is_disabled_without_allowed_read_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            perception = perceive_workspace(cwd=tmp)

        observations = perception["observations"]
        self.assertEqual(observations[0]["type"], "workspace")
        self.assertEqual(observations[1]["type"], "read_scope")
        self.assertEqual(observations[1]["status"], "disabled")

    def test_perception_collects_git_status_under_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with patch(
                "mew.perception.run_command_record",
                return_value={
                    "cwd": str(root),
                    "exit_code": 0,
                    "stdout": "## main\n M src/mew/perception.py\n?? tests/test_perception.py\n",
                    "stderr": "",
                },
            ) as run:
                perception = perceive_workspace(allowed_read_roots=[tmp], cwd=tmp)

        run.assert_called_once_with("git status --short --branch", cwd=str(root), timeout=5)
        git = perception["observations"][-1]
        self.assertEqual(git["type"], "git_status")
        self.assertEqual(git["status"], "ok")
        self.assertEqual(git["branch"], "main")
        self.assertFalse(git["clean"])
        self.assertEqual(git["changes"][0], " M src/mew/perception.py")

    def test_perception_blocks_cwd_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            allowed = root / "allowed"
            blocked = root / "blocked"
            allowed.mkdir()
            blocked.mkdir()
            perception = perceive_workspace(allowed_read_roots=[str(allowed)], cwd=str(blocked))

        self.assertEqual(perception["observations"][1]["type"], "read_scope")
        self.assertEqual(perception["observations"][1]["status"], "blocked")

    def test_format_perception_prints_git_changes(self):
        text = format_perception(
            {
                "observations": [
                    {
                        "type": "workspace",
                        "cwd": "/repo",
                        "allowed_read_roots": ["/repo"],
                    },
                    {"type": "read_scope", "status": "allowed"},
                    {
                        "type": "git_status",
                        "status": "ok",
                        "exit_code": 0,
                        "clean": False,
                        "branch": "main",
                        "changes": [" M file.py"],
                    },
                ]
            }
        )

        self.assertIn("cwd: /repo", text)
        self.assertIn("read_scope: allowed", text)
        self.assertIn("branch: main", text)
        self.assertIn(" M file.py", text)


if __name__ == "__main__":
    unittest.main()
