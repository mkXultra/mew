import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.passive_bundle import generate_bundle
from mew.state import add_question, load_state, save_state, state_lock


def write_report(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PassiveBundleTests(unittest.TestCase):
    def test_generate_bundle_composes_existing_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_report(root, ".mew/journal/2026-04-17.md", "# Mew Journal\n\nJournal hint.\n")
            write_report(root, ".mew/mood/2026-04-17.md", "\n# Mew Mood\n\nCurrent mood: **steady**\n")

            result = generate_bundle(root, root, explicit_date="2026-04-17")
            text = result.path.read_text(encoding="utf-8")

            self.assertEqual(result.included, ["Journal", "Mood"])
            self.assertEqual(result.missing, ["Morning Paper", "Dream", "Self Memory"])
            self.assertIn("# Mew Passive Bundle 2026-04-17", text)
            self.assertIn("- included: Journal, Mood", text)
            self.assertIn("- Journal: Journal hint.", text)
            self.assertIn("## Mood", text)
            self.assertNotIn("# Mew Mood", text)

    def test_generate_bundle_handles_no_reports_and_heading_only_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty_result = generate_bundle(root, root, explicit_date="2026-04-17")
            empty_text = empty_result.path.read_text(encoding="utf-8")
            self.assertIn("- included: none", empty_text)
            self.assertIn("No reports found", empty_text)

            write_report(root, ".mew/journal/2026-04-18.md", "# Mew Journal\n\n## Morning\n")
            heading_result = generate_bundle(root, root, explicit_date="2026-04-18")
            heading_text = heading_result.path.read_text(encoding="utf-8")
            self.assertIn("- Journal: Morning", heading_text)

    def test_generate_bundle_prioritizes_continuity_risk_reentry_hint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_report(
                root,
                ".mew/morning-paper/2026-04-17.md",
                "\n".join(
                    [
                        "# Mew Morning Paper",
                        "",
                        "Top pick: Passive AI shells",
                        "",
                        "## Interests",
                        "- agents",
                        "",
                        "## Continuity risks",
                        "- work session #5 task #1: weak 6/9; repair: refresh working memory",
                        "",
                        "## Top picks",
                        "",
                        "### 1. Passive AI shells",
                    ]
                )
                + "\n",
            )

            result = generate_bundle(root, root, explicit_date="2026-04-17")
            text = result.path.read_text(encoding="utf-8")

            self.assertIn(
                "- Morning Paper: work session #5 task #1: weak 6/9; repair: refresh working memory",
                text,
            )
            self.assertNotIn("- Morning Paper: Top pick: Passive AI shells", text)

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

    def test_bundle_command_rejects_invalid_date(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["bundle", "--date", "../../outside"])

        self.assertEqual(code, 1)
        self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

    def test_bundle_command_rejects_json_with_show(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["bundle", "--json", "--show"])

        self.assertEqual(code, 1)
        self.assertIn("--json and --show cannot be used together", stderr.getvalue())

    def test_bundle_command_can_generate_core_reports_before_composing(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with state_lock():
                    state = load_state()
                    state["tasks"].append({"id": 1, "title": "Open work", "status": "ready"})
                    add_question(state, "Need input?")
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    code = main(["bundle", "--date", "2026-04-17", "--generate-core", "--json"])
                data = json.loads(stdout.getvalue())
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            self.assertEqual(data["included"], ["Journal", "Mood", "Dream", "Self Memory"])
            self.assertEqual([item["type"] for item in data["generated"]], ["Journal", "Mood", "Self Memory", "Dream"])
            self.assertTrue((Path(tmp) / ".mew" / "journal" / "2026-04-17.md").exists())
            self.assertTrue((Path(tmp) / ".mew" / "mood" / "2026-04-17.md").exists())
            self.assertTrue((Path(tmp) / ".mew" / "self" / "learned-2026-04-17.md").exists())
            self.assertTrue((Path(tmp) / ".mew" / "dreams" / "2026-04-17.md").exists())

    def test_bundle_command_can_generate_morning_paper_from_feed(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feed = root / "feed.json"
            feed.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "title": "Passive AI shell",
                                "source": "local",
                                "summary": "Useful for mew.",
                                "tags": ["passive-ai"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    code = main(
                        [
                            "bundle",
                            "--date",
                            "2026-04-17",
                            "--generate-core",
                            "--morning-feed",
                            str(feed),
                            "--interest",
                            "passive-ai",
                            "--json",
                        ]
                    )
                data = json.loads(stdout.getvalue())
            finally:
                os.chdir(old_cwd)

            self.assertEqual(code, 0)
            self.assertEqual(data["included"], ["Journal", "Mood", "Morning Paper", "Dream", "Self Memory"])
            self.assertIn("Morning Paper", [item["type"] for item in data["generated"]])

    def test_bundle_command_rejects_morning_feed_without_generate_core(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["bundle", "--morning-feed", "feed.json"])

        self.assertEqual(code, 1)
        self.assertIn("--morning-feed requires --generate-core", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["bundle", "--generate-core", "--interest", "ai"])

        self.assertEqual(code, 1)
        self.assertIn("--interest requires --morning-feed", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            code = main(["bundle", "--generate-core", "--limit", "3"])

        self.assertEqual(code, 1)
        self.assertIn("--limit requires --morning-feed", stderr.getvalue())

    def test_bundle_command_reports_invalid_morning_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "feed.json"
            feed.write_text("{not json", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                code = main(["bundle", "--generate-core", "--morning-feed", str(feed)])

        self.assertEqual(code, 1)
        self.assertIn("failed to read feed", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
