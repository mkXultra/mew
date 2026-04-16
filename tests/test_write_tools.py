import tempfile
import unittest
from pathlib import Path

from mew.write_tools import (
    edit_file,
    restore_write_snapshot,
    snapshot_write_path,
    write_file,
)


class WriteToolsTests(unittest.TestCase):
    def test_write_refuses_path_outside_allowed_root(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "notes.md"

            with self.assertRaisesRegex(ValueError, "outside allowed write roots"):
                write_file(str(path), "hello", [allowed], create=True)

    def test_write_allows_exact_new_file_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"

            result = write_file(str(path), "hello\n", [str(path)], create=True)

            self.assertTrue(result["written"])
            self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")

    def test_edit_refuses_missing_old_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello mew\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "old text was not found"):
                edit_file(str(path), "missing", "shell", [tmp])

    def test_edit_refuses_multiple_matches_without_replace_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("mew mew\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "matched 2 times"):
                edit_file(str(path), "mew", "shell", [tmp])

    def test_write_and_edit_enforce_size_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "content is too large"):
                write_file(str(path), "x" * 11, [tmp], max_chars=10)

            with self.assertRaisesRegex(ValueError, "edited content is too large"):
                edit_file(str(path), "hello", "x" * 20, [tmp], max_chars=10)

    def test_snapshot_restore_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("before\n", encoding="utf-8")

            snapshot = snapshot_write_path(str(path), [tmp])
            write_file(str(path), "after\n", [tmp])
            rollback = restore_write_snapshot(snapshot)

            self.assertEqual(path.read_text(encoding="utf-8"), "before\n")
            self.assertTrue(rollback["restored"])
            self.assertFalse(rollback["removed_created_file"])

    def test_snapshot_restore_created_file_removes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"

            snapshot = snapshot_write_path(str(path), [tmp], create=True)
            write_file(str(path), "created\n", [tmp], create=True)
            rollback = restore_write_snapshot(snapshot)

            self.assertFalse(path.exists())
            self.assertTrue(rollback["restored"])
            self.assertTrue(rollback["removed_created_file"])


if __name__ == "__main__":
    unittest.main()
