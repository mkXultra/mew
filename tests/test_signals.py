import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

import mew.signals as signals_module
from mew.cli import main
from mew.signals import (
    disable_signal_source,
    enable_signal_source,
    record_signal_observation,
    select_signal_proof_source,
)
from mew.state import default_state


class SignalTests(unittest.TestCase):
    def test_select_signal_proof_source_prefers_enabled_budgeted_feed(self):
        state = default_state()
        enable_signal_source(
            state,
            "hn",
            kind="rss",
            reason="track engineering stories",
            budget_limit=1,
            config={"url": "https://example.test/hn.xml"},
            current_time="2026-04-20T00:00:00Z",
        )
        record_signal_observation(
            state,
            "hn",
            kind="rss_item",
            summary="Already spent",
            reason_for_use="consume proof budget",
            current_time="2026-04-20T00:01:00Z",
        )
        enable_signal_source(
            state,
            "notes",
            kind="manual",
            reason="not fetchable",
            current_time="2026-04-20T00:02:00Z",
        )
        enable_signal_source(
            state,
            "blog",
            kind="atom",
            reason="watch release notes",
            budget_limit=2,
            config={"url": "https://example.test/feed.atom"},
            current_time="2026-04-20T00:03:00Z",
        )

        selected = select_signal_proof_source(
            state,
            current_time="2026-04-20T00:04:00Z",
        )

        self.assertEqual(selected["status"], "selected")
        self.assertEqual(selected["proof"]["source"], "blog")
        self.assertEqual(selected["proof"]["kind"], "atom")
        self.assertEqual(selected["proof"]["url"], "https://example.test/feed.atom")
        self.assertEqual(selected["proof"]["budget_remaining"], 2)
        self.assertEqual(selected["candidates"][0]["name"], "hn")
        self.assertIn("budget_exhausted", selected["candidates"][0]["blockers"])
        self.assertIn("unsupported_source_kind", selected["candidates"][1]["blockers"])
        selected["source"]["reason"] = "mutated copy"
        self.assertEqual(state["signals"]["sources"][2]["reason"], "watch release notes")

    def test_select_signal_proof_source_preserves_zero_limit_and_refreshes_day_view(self):
        state = default_state()
        enable_signal_source(
            state,
            "zero",
            kind="rss",
            reason="disabled by budget",
            budget_limit=0,
            config={"url": "https://example.test/zero.xml"},
            current_time="2026-04-19T00:00:00Z",
        )
        enable_signal_source(
            state,
            "stale",
            kind="rss",
            reason="daily budget should refresh in read-only view",
            budget_limit=1,
            config={"url": "https://example.test/stale.xml"},
            current_time="2026-04-19T00:01:00Z",
        )
        record_signal_observation(
            state,
            "stale",
            kind="rss_item",
            summary="Yesterday's budget",
            reason_for_use="consume yesterday",
            current_time="2026-04-19T00:02:00Z",
        )

        selected = select_signal_proof_source(
            state,
            current_time="2026-04-20T00:00:00Z",
        )

        self.assertEqual(selected["status"], "selected")
        self.assertEqual(selected["proof"]["source"], "stale")
        self.assertEqual(selected["proof"]["budget_remaining"], 1)
        self.assertEqual(selected["candidates"][0]["budget"]["limit"], 0)
        self.assertIn("budget_exhausted", selected["candidates"][0]["blockers"])
        self.assertEqual(selected["candidates"][1]["budget"]["window_key"], "2026-04-20")
        self.assertEqual(selected["candidates"][1]["budget"]["used"], 0)
        self.assertEqual(state["signals"]["sources"][1]["budget"]["window_key"], "2026-04-19")
        self.assertEqual(state["signals"]["sources"][1]["budget"]["used"], 1)

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

    def test_signals_cli_proof_source_help_exposes_reviewer_visible_auto_fetch(self):
        with redirect_stdout(StringIO()) as stdout:
            with self.assertRaises(SystemExit) as raised:
                main(["signals", "proof-source", "--help"])

        self.assertEqual(raised.exception.code, 0)
        help_text = stdout.getvalue()
        self.assertIn("proof-source", help_text)
        self.assertIn("reviewer-visible auto-fetch proof source", help_text)

    def test_signals_cli_fetch_records_gated_observation(self):
        old_cwd = os.getcwd()
        old_urlopen = signals_module.urlopen

        class FakeResponse:
            def read(self):
                return (
                    "<?xml version='1.0' encoding='UTF-8'?>"
                    "<rss version='2.0'><channel><item>"
                    "<title>Fixture feed item</title>"
                    "<link>https://example.test/item</link>"
                    "</item></channel></rss>"
                ).encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        calls = []

        def fake_urlopen(url, timeout=10):
            calls.append((url, timeout))
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            signals_module.urlopen = fake_urlopen
            try:
                with redirect_stdout(StringIO()):
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
                                "--config",
                                '{"url":"https://example.test/feed.xml"}',
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["signals", "fetch", "hn", "--json"]), 0)
                fetched = json.loads(stdout.getvalue())
                self.assertEqual(fetched["status"], "recorded")
                self.assertEqual(fetched["signal"]["source"], "hn")
                self.assertEqual(fetched["signal"]["summary"], "Fixture feed item")
                self.assertEqual(fetched["signal"]["payload"]["url"], "https://example.test/item")
                self.assertEqual(fetched["signal"]["reason_for_use"], "watch engineering links")
                self.assertEqual(calls, [("https://example.test/feed.xml", 10)])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["signals", "journal", "--json"]), 0)
                journal = json.loads(stdout.getvalue())
                self.assertEqual(journal["journal"][0]["summary"], "Fixture feed item")

                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["signals", "disable", "hn"]), 0)
                signals_module.urlopen = old_urlopen
                with redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["signals", "fetch", "hn"]), 1)
                self.assertIn("signal blocked: source_disabled", stderr.getvalue())
            finally:
                signals_module.urlopen = old_urlopen
                os.chdir(old_cwd)

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
