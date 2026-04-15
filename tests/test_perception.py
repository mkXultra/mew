import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.perception import format_perception, perceive_workspace, recent_file_changes_observation


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
        git = next(item for item in perception["observations"] if item["type"] == "git_status")
        self.assertEqual(git["type"], "git_status")
        self.assertEqual(git["status"], "ok")
        self.assertEqual(git["branch"], "main")
        self.assertFalse(git["clean"])
        self.assertEqual(git["changes"][0], " M src/mew/perception.py")

    def test_perception_collects_recent_file_changes_under_allowed_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            recent = root / "recent.txt"
            recent.write_text("recent", encoding="utf-8")

            with patch(
                "mew.perception.run_command_record",
                return_value={"cwd": str(root), "exit_code": 0, "stdout": "## main\n", "stderr": ""},
            ):
                perception = perceive_workspace(allowed_read_roots=[tmp], cwd=tmp)

        changes = next(
            item for item in perception["observations"] if item["type"] == "recent_file_changes"
        )
        self.assertEqual(changes["status"], "ok")
        self.assertTrue(any(file_item["path"].endswith("recent.txt") for file_item in changes["files"]))

    def test_recent_file_changes_skips_sensitive_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / "auth.json").write_text("secret", encoding="utf-8")
            (root / "visible.txt").write_text("visible", encoding="utf-8")

            observation = recent_file_changes_observation([root])

        paths = [file_item["path"] for file_item in observation["files"]]
        self.assertTrue(any(path.endswith("visible.txt") for path in paths))
        self.assertFalse(any(path.endswith("auth.json") for path in paths))

    def test_perception_observer_errors_do_not_block_other_observers(self):
        class FailingObserver:
            name = "failing"

            def observe(self, cwd, roots):
                raise RuntimeError("boom")

        class GoodObserver:
            name = "good"

            def observe(self, cwd, roots):
                return [{"type": "good", "status": "ok"}]

        with tempfile.TemporaryDirectory() as tmp:
            with patch("mew.perception.OBSERVERS", [FailingObserver(), GoodObserver()]):
                perception = perceive_workspace(allowed_read_roots=[tmp], cwd=tmp)

        observations = perception["observations"]
        self.assertIn({"type": "failing", "status": "error", "error": "boom"}, observations)
        self.assertIn({"type": "good", "status": "ok"}, observations)

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
                    {
                        "type": "recent_file_changes",
                        "status": "ok",
                        "files": [{"path": "/repo/file.py", "mtime": "now", "size": 12}],
                        "scanned": 1,
                        "truncated": False,
                    },
                ]
            }
        )

        self.assertIn("cwd: /repo", text)
        self.assertIn("read_scope: allowed", text)
        self.assertIn("branch: main", text)
        self.assertIn(" M file.py", text)
        self.assertIn("recent_file_changes: ok", text)
        self.assertIn("/repo/file.py", text)


if __name__ == "__main__":
    unittest.main()
