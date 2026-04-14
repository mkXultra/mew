import tempfile
import unittest
from pathlib import Path

from mew.write_tools import edit_file, write_file


class WriteToolsTests(unittest.TestCase):
    def test_write_refuses_path_outside_allowed_root(self):
        with tempfile.TemporaryDirectory() as allowed, tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "notes.md"

            with self.assertRaisesRegex(ValueError, "outside allowed write roots"):
                write_file(str(path), "hello", [allowed], create=True)

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


if __name__ == "__main__":
    unittest.main()
