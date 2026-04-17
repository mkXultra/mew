import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.passive_bundle import generate_bundle


def write_report(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PassiveBundleTests(unittest.TestCase):
    def test_generate_bundle_composes_existing_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_report(root, ".mew/journal/2026-04-17.md", "# Mew Journal\n\nJournal hint.\n")
            write_report(root, ".mew/mood/2026-04-17.md", "# Mew Mood\n\nCurrent mood: **steady**\n")

            result = generate_bundle(root, root, explicit_date="2026-04-17")
            text = result.path.read_text(encoding="utf-8")

            self.assertEqual(result.included, ["Journal", "Mood"])
            self.assertEqual(result.missing, ["Morning Paper", "Dream", "Self Memory"])
            self.assertIn("# Mew Passive Bundle 2026-04-17", text)
            self.assertIn("- included: Journal, Mood", text)
            self.assertIn("- Journal: Journal hint.", text)
            self.assertIn("## Mood", text)
            self.assertNotIn("# Mew Mood", text)

    def test_bundle_command_prints_path_and_writes_file(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                root = Path(tmp)
                write_report(root, ".mew/journal/2026-04-17.md", "# Mew Journal\n\nJournal hint.\n")

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["bundle", "--date", "2026-04-17"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            path = Path(stdout.getvalue().strip())
            self.assertEqual(path, Path(".mew/passive-bundle/2026-04-17.md"))
            self.assertTrue((root / path).exists())

    def test_bundle_command_show_and_json(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                root = Path(tmp)
                write_report(root, ".mew/mood/2026-04-17.md", "# Mew Mood\n\nCurrent mood: **steady**\n")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["bundle", "--date", "2026-04-17", "--show"]), 0)
                self.assertIn("Current mood: **steady**", stdout.getvalue())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["bundle", "--date", "2026-04-17", "--json"]), 0)
                data = json.loads(stdout.getvalue())
            finally:
                os.chdir(old_cwd)

            self.assertEqual(data["included"], ["Mood"])
            self.assertIn("Journal", data["missing"])


if __name__ == "__main__":
    unittest.main()
