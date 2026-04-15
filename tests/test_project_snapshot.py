import unittest

from mew.project_snapshot import (
    format_project_snapshot,
    snapshot_for_context,
    update_project_snapshot_from_read_result,
)
from mew.state import default_state


class ProjectSnapshotTests(unittest.TestCase):
    def test_inspect_dir_updates_root_shape_and_project_type(self):
        state = default_state()
        update_project_snapshot_from_read_result(
            state,
            "inspect_dir",
            {
                "path": "/repo",
                "entries": [
                    {"name": "src", "type": "dir", "size": 100},
                    {"name": "tests", "type": "dir", "size": 100},
                    {"name": "pyproject.toml", "type": "file", "size": 120},
                    {"name": "README.md", "type": "file", "size": 80},
                ],
                "truncated": False,
            },
            "now",
        )

        snapshot = state["memory"]["deep"]["project_snapshot"]

        self.assertEqual(snapshot["updated_at"], "now")
        self.assertEqual(snapshot["project_types"], ["python"])
        self.assertEqual(snapshot["roots"][0]["path"], "/repo")
        self.assertEqual(snapshot["roots"][0]["key_dirs"], ["src", "tests"])
        self.assertEqual(snapshot["roots"][0]["key_files"], ["pyproject.toml", "README.md"])

    def test_read_pyproject_updates_package_summary(self):
        state = default_state()
        update_project_snapshot_from_read_result(
            state,
            "read_file",
            {
                "path": "/repo/pyproject.toml",
                "size": 200,
                "truncated": False,
                "text": (
                    "[project]\n"
                    'name = "mew"\n'
                    'version = "0.1.0"\n'
                    'requires-python = ">=3.9"\n\n'
                    "[project.scripts]\n"
                    'mew = "mew.cli:main"\n'
                ),
            },
            "now",
        )

        snapshot = state["memory"]["deep"]["project_snapshot"]

        self.assertEqual(snapshot["project_types"], ["python"])
        self.assertEqual(snapshot["package"]["name"], "mew")
        self.assertEqual(snapshot["package"]["scripts"], {"mew": "mew.cli:main"})
        self.assertEqual(snapshot["files"][0]["kind"], "pyproject")

    def test_context_snapshot_is_bounded(self):
        state = default_state()
        long_text = "detail " * 200
        for index in range(12):
            update_project_snapshot_from_read_result(
                state,
                "read_file",
                {
                    "path": f"/repo/file-{index}.md",
                    "size": 100,
                    "truncated": False,
                    "text": long_text,
                },
                f"now-{index}",
            )

        context = snapshot_for_context(state["memory"]["deep"]["project_snapshot"])

        self.assertEqual(len(context["files"]), 10)
        self.assertLessEqual(len(context["files"][0]["summary"]), 320)

    def test_python_file_summary_uses_structure_not_raw_prefix(self):
        state = default_state()
        update_project_snapshot_from_read_result(
            state,
            "read_file",
            {
                "path": "/repo/src/mew/example.py",
                "size": 200,
                "truncated": False,
                "text": (
                    "import json\n"
                    "from pathlib import Path\n\n"
                    "class Runner:\n"
                    "    pass\n\n"
                    "def main():\n"
                    "    return Path('.')\n"
                ),
            },
            "now",
        )

        file_item = state["memory"]["deep"]["project_snapshot"]["files"][0]

        self.assertEqual(file_item["kind"], "python")
        self.assertIn("imports=json, pathlib", file_item["summary"])
        self.assertIn("classes=Runner", file_item["summary"])
        self.assertIn("functions=main", file_item["summary"])

    def test_format_project_snapshot_prints_compact_summary(self):
        state = default_state()
        update_project_snapshot_from_read_result(
            state,
            "inspect_dir",
            {
                "path": "/repo",
                "entries": [{"name": "package.json", "type": "file", "size": 10}],
                "truncated": False,
            },
            "now",
        )

        text = format_project_snapshot(state["memory"]["deep"]["project_snapshot"])

        self.assertIn("project_snapshot_updated_at: now", text)
        self.assertIn("project_types: node", text)


if __name__ == "__main__":
    unittest.main()
