import tempfile
import unittest
from pathlib import Path

from mew.write_tools import (
    edit_file,
    edit_file_hunks,
    restore_write_snapshot,
    snapshot_write_path,
    summarize_write_result,
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

    def test_write_allows_missing_directory_root_for_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "experiments" / "mew-dream"
            path = root / "README.md"

            result = write_file(str(path), "hello\n", [str(root)], create=True)

            self.assertTrue(result["written"])
            self.assertEqual(path.read_text(encoding="utf-8"), "hello\n")

    def test_edit_refuses_missing_old_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello mew\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "old text was not found; confirm the exact existing text before retrying"):
                edit_file(str(path), "missing", "shell", [tmp])
            with self.assertRaisesRegex(ValueError, "use read_file on the latest target window first"):
                edit_file(str(path), "missing", "shell", [tmp])

    def test_edit_refuses_multiple_matches_without_replace_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("mew mew\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "matched 2 times;.*include surrounding context"):
                edit_file(str(path), "mew", "shell", [tmp])

    def test_edit_missing_path_recommends_write_file_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "new_notes.md"

            with self.assertRaisesRegex(ValueError, "use write_file with --create/create=True"):
                edit_file(str(path), "mew", "shell", [tmp])

    def test_write_and_edit_enforce_size_limits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "content is too large"):
                write_file(str(path), "x" * 11, [tmp], max_chars=10)

            with self.assertRaisesRegex(ValueError, "edited content is too large"):
                edit_file(str(path), "hello", "x" * 20, [tmp], max_chars=10)

    def test_edit_allows_small_replacement_in_large_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.py"
            path.write_text("x" * 120000 + "\nold_call()\n", encoding="utf-8")

            result = edit_file(str(path), "old_call()", "new_call()", [tmp], max_chars=100)

            self.assertTrue(result["written"])
            self.assertIn("new_call()", path.read_text(encoding="utf-8"))
            self.assertNotIn("old_call()", path.read_text(encoding="utf-8"))

    def test_edit_diff_stats_use_unclipped_diff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.py"
            path.write_text("prefix " + ("x" * 20000) + " old_call()\n", encoding="utf-8")

            result = edit_file(str(path), "old_call()", "new_call()", [tmp], dry_run=True, max_chars=100)

            self.assertTrue(result["changed"])
            self.assertEqual(result["diff_stats"], {"added": 1, "removed": 1})
            self.assertIn("... output truncated ...", result["diff"])

    def test_edit_diff_stats_count_no_newline_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.py"
            path.write_text("prefix " + ("x" * 20000) + " old_call()", encoding="utf-8")

            result = edit_file(str(path), "old_call()", "new_call()", [tmp], dry_run=True, max_chars=100)

            self.assertTrue(result["changed"])
            self.assertEqual(result["diff_stats"], {"added": 1, "removed": 1})
            self.assertIn("... output truncated ...", result["diff"])

    def test_edit_marks_no_op_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("hello mew\n", encoding="utf-8")

            result = edit_file(str(path), "hello", "hello", [tmp], dry_run=True)

            self.assertFalse(result["changed"])
            self.assertTrue(result["no_op"])
            self.assertEqual(result["no_op_reason"], "old and new text are identical")
            self.assertFalse(result["written"])

            summary = summarize_write_result(result)
            self.assertIn("no_op: old and new text are identical; file content is unchanged", summary)
            self.assertIn("re-read the target window", summary)

    def test_edit_file_hunks_applies_disjoint_replacements_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.py"
            path.write_text("alpha = 1\nmiddle = 2\nomega = 3\n", encoding="utf-8")

            result = edit_file_hunks(
                str(path),
                [
                    {"old": "alpha = 1", "new": "alpha = 10"},
                    {"old": "omega = 3", "new": "omega = 30"},
                ],
                [tmp],
            )

            self.assertTrue(result["written"])
            self.assertEqual(result["hunk_count"], 2)
            self.assertEqual(path.read_text(encoding="utf-8"), "alpha = 10\nmiddle = 2\nomega = 30\n")
            summary = summarize_write_result(result)
            self.assertIn("hunks: 2", summary)

    def test_edit_file_hunks_refuses_duplicate_match_hunk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.py"
            path.write_text("value = old\nvalue = old\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "matched 2 times"):
                edit_file_hunks(
                    str(path),
                    [{"old": "value = old", "new": "value = new"}],
                    [tmp],
                    dry_run=True,
                )

    def test_edit_file_hunks_refuses_overlapping_hunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.py"
            path.write_text("abcdef\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "edit hunks overlap"):
                edit_file_hunks(
                    str(path),
                    [
                        {"old": "abcd", "new": "ABCD"},
                        {"old": "cdef", "new": "CDEF"},
                    ],
                    [tmp],
                    dry_run=True,
                )

    def test_edit_file_hunks_refuses_duplicate_adjacent_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dogfood.py"
            before_text = (
                '    report["artifacts"] = {\n'
                '        "phase": "phase1",\n'
                '        "comparator_source": "m6_6",\n'
                '        "durable_recall_active": True,\n'
                '        "b0_comparator_wall_seconds": b0_comparator_wall_seconds,\n'
                '        "budget_wall_seconds": budget_wall_seconds,\n'
                "    }\n"
                "    return report\n"
                "\n"
                "\n"
                "def run_next_scenario(workspace):\n"
                "    return None\n"
            )
            path.write_text(before_text, encoding="utf-8")
            old = (
                '        "phase": "phase1",\n'
                '        "comparator_source": "m6_6",\n'
                '        "durable_recall_active": True,\n'
            )

            with self.assertRaisesRegex(ValueError, "duplicated adjacent context"):
                edit_file_hunks(
                    str(path),
                    [
                        {
                            "old": old,
                            "new": (
                                old
                                + '        "b0_comparator_wall_seconds": b0_comparator_wall_seconds,\n'
                                + '        "budget_wall_seconds": budget_wall_seconds,\n'
                                + "    }\n"
                                + "    return report\n"
                                + "\n"
                                + "\n"
                                + "def run_m6_9_phase2_regression_scenario(workspace):\n"
                                + "    return None\n"
                            ),
                        }
                    ],
                    [tmp],
                    dry_run=True,
                )

    def test_edit_file_hunks_allows_non_duplicate_insertion_after_old_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "multi.py"
            path.write_text("alpha\nomega\n", encoding="utf-8")

            result = edit_file_hunks(
                str(path),
                [{"old": "alpha\n", "new": "alpha\nbeta\n"}],
                [tmp],
                dry_run=True,
            )

            self.assertTrue(result["changed"])
            self.assertIn("+beta", result["diff"])

    def test_edit_file_refuses_duplicate_adjacent_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "notes.md"
            path.write_text("alpha\nomega\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "duplicated adjacent context"):
                edit_file(str(path), "alpha\n", "alpha\nomega\n", [tmp], dry_run=True)

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
