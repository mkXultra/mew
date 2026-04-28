import tempfile
import unittest
from pathlib import Path

from mew.data_tools import analyze_table
from mew.work_session import execute_work_tool


class DataToolsTests(unittest.TestCase):
    def test_analyze_table_profiles_decimal_comma_tsv_and_extrema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "spectrum.tsv"
            table.write_text(
                "x\ty\n"
                "1,0\t10,0\n"
                "2,0\t30,0\n"
                "3,0\t20,0\n"
                "4,0\t40,0\n"
                "5,0\t15,0\n",
                encoding="utf-8",
            )

            result = analyze_table(str(table), [str(root)])

        self.assertEqual(result["type"], "table_analysis")
        self.assertEqual(result["delimiter_guess"], "tab")
        self.assertEqual(result["parsed_rows"], 5)
        self.assertEqual(result["skipped_nonempty_lines"], 1)
        self.assertEqual(result["column_count"], 2)
        self.assertEqual(result["columns"][0]["min"], 1.0)
        self.assertEqual(result["columns"][0]["max"], 5.0)
        self.assertTrue(result["columns"][0]["monotonic_increasing"])
        maxima = result["pairs"][0]["top_local_maxima"]
        self.assertEqual([item["x"] for item in maxima[:2]], [4.0, 2.0])
        self.assertEqual(result["pairs"][0]["global_max"]["x"], 4.0)

    def test_analyze_table_rejects_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as allowed:
            with tempfile.TemporaryDirectory() as outside:
                table = Path(outside) / "table.tsv"
                table.write_text("1 2\n", encoding="utf-8")

                with self.assertRaisesRegex(ValueError, "outside allowed read roots"):
                    analyze_table(str(table), [allowed])

    def test_analyze_table_handles_comma_separated_integer_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "data.csv"
            table.write_text("1,2,3\n4,5,6\n", encoding="utf-8")

            result = analyze_table(str(table), [str(root)])

        self.assertEqual(result["delimiter_guess"], "comma")
        self.assertEqual(result["column_count"], 3)
        self.assertEqual(result["columns"][0]["min"], 1.0)
        self.assertEqual(result["columns"][1]["max"], 5.0)

    def test_analyze_table_handles_two_column_comma_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "data.csv"
            table.write_text("1,2\n3,4\n", encoding="utf-8")

            result = analyze_table(str(table), [str(root)])

        self.assertEqual(result["delimiter_guess"], "comma")
        self.assertEqual(result["column_count"], 2)
        self.assertEqual(result["parsed_rows"], 2)
        self.assertEqual(result["columns"][0]["max"], 3.0)
        self.assertEqual(result["columns"][1]["max"], 4.0)

    def test_analyze_table_handles_comma_csv_with_spaces_and_decimal_points(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "data.csv"
            table.write_text("1.1, 2.2\n3.3, 4.4\n", encoding="utf-8")

            result = analyze_table(str(table), [str(root)])

        self.assertEqual(result["delimiter_guess"], "comma")
        self.assertEqual(result["column_count"], 2)
        self.assertEqual(result["columns"][0]["min"], 1.1)
        self.assertEqual(result["columns"][1]["max"], 4.4)

    def test_execute_work_tool_analyze_table_uses_cwd_and_read_roots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            table = root / "data.txt"
            table.write_text("1 2\n2 4\n3 3\n", encoding="utf-8")

            result = execute_work_tool(
                "analyze_table",
                {"path": "data.txt", "cwd": str(root), "max_extrema": 3},
                [str(root)],
            )

        self.assertEqual(result["path"], str(table.resolve()))
        self.assertEqual(result["parsed_rows"], 3)
        self.assertEqual(result["pairs"][0]["global_max"]["y"], 4.0)


if __name__ == "__main__":
    unittest.main()
