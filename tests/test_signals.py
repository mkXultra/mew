import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from mew.cli import main
from mew.signals import (
    disable_signal_source,
    enable_signal_source,
    record_signal_observation,
)
from mew.state import default_state


class SignalTests(unittest.TestCase):
    def test_signal_source_gate_budget_and_event_journal(self):
        state = default_state()
        source = enable_signal_source(
            state,
            "hn",
            kind="rss",
            reason="track engineering stories",
            budget_limit=2,
            current_time="2026-04-20T00:00:00Z",
        )

        first = record_signal_observation(
            state,
            "hn",
            kind="rss_item",
            summary="New Python release discussion",
            reason_for_use="might affect this project",
            payload={"url": "https://example.test/python"},
            current_time="2026-04-20T00:01:00Z",
        )
        second = record_signal_observation(
            state,
            "hn",
            kind="rss_item",
            summary="New terminal UX discussion",
            reason_for_use="mew CLI inspiration",
            current_time="2026-04-20T00:02:00Z",
        )
        third = record_signal_observation(
            state,
            "hn",
            kind="rss_item",
            summary="Budget overflow",
            reason_for_use="should be blocked",
            current_time="2026-04-20T00:03:00Z",
        )

        self.assertEqual(source["budget"]["limit"], 2)
        self.assertEqual(first["status"], "recorded")
        self.assertEqual(second["status"], "recorded")
        self.assertEqual(third["status"], "blocked")
        self.assertEqual(third["reason"], "budget_exhausted")
        self.assertEqual(len(state["signals"]["journal"]), 2)
        self.assertEqual(state["signals"]["journal"][0]["event_id"], 1)
        self.assertEqual(state["inbox"][0]["type"], "signal_observed")
        self.assertEqual(state["inbox"][0]["source"], "signal:hn")

        disable_signal_source(state, "hn", current_time="2026-04-20T00:04:00Z")
        disabled = record_signal_observation(
            state,
            "hn",
            kind="rss_item",
            summary="Disabled source",
            reason_for_use="should be blocked",
            current_time="2026-04-20T00:05:00Z",
        )
        self.assertEqual(disabled["reason"], "source_disabled")

    def test_signals_cli_enable_record_and_journal(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "signals",
                                "enable",
                                "hn",
                                "--kind",
                                "rss",
                                "--reason",
                                "watch engineering links",
                                "--budget",
                                "2",
                                "--json",
                            ]
                        ),
                        0,
                    )
                enabled = json.loads(stdout.getvalue())
                self.assertEqual(enabled["source"]["name"], "hn")
                self.assertTrue(enabled["source"]["enabled"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "signals",
                                "record",
                                "hn",
                                "--kind",
                                "rss_item",
                                "--summary",
                                "Interesting daemon article",
                                "--reason",
                                "M7 signal dogfood",
                                "--payload",
                                '{"url":"https://example.test/daemon"}',
                                "--json",
                            ]
                        ),
                        0,
                    )
                recorded = json.loads(stdout.getvalue())
                self.assertEqual(recorded["status"], "recorded")
                self.assertEqual(recorded["signal"]["event_id"], 1)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["signals", "journal", "--json"]), 0)
                journal = json.loads(stdout.getvalue())
                self.assertEqual(journal["journal"][0]["source"], "hn")
                self.assertEqual(journal["journal"][0]["kind"], "rss_item")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["signals", "journal"]), 0)
                journal_text = stdout.getvalue()
                self.assertIn("#1 hn:rss_item", journal_text)
                self.assertIn("Interesting daemon article", journal_text)
                self.assertIn("reason_for_use=M7 signal dogfood", journal_text)
                self.assertIn("recorded_at=", journal_text)

                with redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["signals", "disable", "hn"]), 0)
                    self.assertEqual(
                        main(
                            [
                                "signals",
                                "record",
                                "hn",
                                "--summary",
                                "Should not queue",
                                "--reason",
                                "disabled gate",
                            ]
                        ),
                        1,
                    )
                self.assertIn("signal blocked: source_disabled", stderr.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
