import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.morning_paper import build_morning_paper_view_model, format_morning_paper_view, render_morning_paper_markdown


def write_feed(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "title": "Passive AI shells",
                        "source": "HN",
                        "url": "https://example.com/passive-ai",
                        "summary": "A note on local-first agent shells.",
                        "tags": ["ai", "agents", "local-first"],
                    },
                    {
                        "title": "Database indexing",
                        "source": "Blog",
                        "summary": "A practical database article.",
                        "tags": ["database"],
                    },
                    {
                        "title": "Daily planning for coding agents",
                        "source": "arXiv",
                        "summary": "Agent planning and reentry.",
                        "topics": ["planning"],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )


class MorningPaperTests(unittest.TestCase):
    def test_build_morning_paper_ranks_by_interests(self):
        items = [
            {"title": "Passive AI shells", "source": "HN", "tags": ["ai", "agents"], "summary": "Local agents."},
            {"title": "Database indexing", "source": "Blog", "tags": ["database"], "summary": "Indexes."},
            {"title": "Coding agent planning", "source": "arXiv", "summary": "Planning for agents."},
        ]
        state = {"interests": ["agents"]}

        view = build_morning_paper_view_model(items, state, explicit_date="2026-04-17", limit=3)
        text = render_morning_paper_markdown(view)

        self.assertEqual(view["date"], "2026-04-17")
        self.assertEqual(view["top_picks"][0]["title"], "Passive AI shells")
        self.assertEqual(view["top_picks"][0]["score"], 10)
        self.assertIn("matched tag `agents`", view["top_picks"][0]["reasons"])
        self.assertEqual(view["continuity_risks"], [])
        self.assertIn("# Mew Morning Paper 2026-04-17", text)
        self.assertNotIn("## Continuity risks", text)
        self.assertIn("## Explore later", text)

    def test_build_morning_paper_surfaces_weak_work_continuity(self):
        state = {
            "interests": ["agents"],
            "tasks": [{"id": 1, "title": "Investigate handoff", "status": "ready"}],
            "work_sessions": [
                {
                    "id": 5,
                    "task_id": 1,
                    "status": "active",
                    "goal": "Continue work",
                    "phase": "idle",
                    "tool_calls": [
                        {
                            "id": 1,
                            "tool": "read_file",
                            "status": "completed",
                            "summary": "x" * 210_000,
                            "result": {"path": "src/mew/morning_paper.py"},
                        }
                    ],
                }
            ],
        }

        view = build_morning_paper_view_model([], state, explicit_date="2026-04-17")
        text = render_morning_paper_markdown(view)
        summary = format_morning_paper_view(view)

        self.assertEqual(len(view["continuity_risks"]), 1)
        self.assertEqual(view["continuity_risks"][0]["status"], "weak")
        self.assertEqual(view["continuity_risks"][0]["score"], "6/9")
        self.assertIn("## Continuity risks", text)
        self.assertIn(
            "- work session #5 task #1: weak 6/9; repair: refresh working memory",
            text,
        )
        self.assertIn("continuity_risks: 1", summary)

    def test_explicit_interest_overrides_empty_state(self):
        items = [{"title": "Local-first agent", "source": "Blog", "summary": "local-first workflow"}]

        view = build_morning_paper_view_model(
            items,
            {},
            explicit_date="2026-04-17",
            explicit_interests=["local-first"],
        )

        self.assertEqual(view["interests"], ["local-first"])
        self.assertEqual(view["top_picks"][0]["score"], 4)

    def test_learned_preferences_feed_interests(self):
        items = [{"title": "Passive AI shell", "source": "Blog", "tags": ["passive-ai"], "summary": "agent shell"}]
        state = {"memory": {"deep": {"preferences": ["2026-04-17T00:00:00Z: interested in passive-ai and agents"]}}}

        view = build_morning_paper_view_model(items, state, explicit_date="2026-04-17")

        self.assertIn("passive-ai", view["interests"])
        self.assertIn("agents", view["interests"])
        self.assertEqual(view["top_picks"][0]["score"], 10)

    def test_limit_must_be_positive(self):
        with self.assertRaises(ValueError):
            build_morning_paper_view_model([], {}, explicit_date="2026-04-17", limit=0)

    def test_morning_paper_command_outputs_json_and_can_write_report(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feed = root / "feed.json"
            write_feed(feed)
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "morning-paper",
                                str(feed),
                                "--date",
                                "2026-04-17",
                                "--interest",
                                "agents",
                                "--write",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                path = Path(data["path"])
            finally:
                os.chdir(old_cwd)

            self.assertEqual(data["top_picks"], 2)
            self.assertEqual(path, Path(".mew/morning-paper/2026-04-17.md"))
            self.assertTrue((root / path).exists())

    def test_morning_paper_command_rejects_invalid_date_limit_and_json_show(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "feed.json"
            write_feed(feed)

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["morning-paper", str(feed), "--date", "../../outside"]), 1)
            self.assertIn("date must be in YYYY-MM-DD format", stderr.getvalue())

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["morning-paper", str(feed), "--limit", "0"]), 1)
            self.assertIn("limit must be positive", stderr.getvalue())

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(main(["morning-paper", str(feed), "--json", "--show"]), 1)
            self.assertIn("--json and --show cannot be used together", stderr.getvalue())

    def test_morning_paper_command_reports_write_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            feed = root / "feed.json"
            write_feed(feed)
            output_file = root / "not-a-dir"
            output_file.write_text("", encoding="utf-8")

            with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                self.assertEqual(
                    main(["morning-paper", str(feed), "--write", "--output-dir", str(output_file)]),
                    1,
                )

        self.assertIn("failed to write report", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
