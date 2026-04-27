import unittest

from mew.signals import enable_signal_source, fetch_signal_source, parse_signal_feed
from mew.state import default_state


RSS_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<rss version='2.0'>
  <channel>
    <title>Example RSS</title>
    <item>
      <title>Interesting mew post</title>
      <link>https://example.test/rss-item</link>
    </item>
  </channel>
</rss>
"""

ATOM_FEED = """<?xml version='1.0' encoding='UTF-8'?>
<feed xmlns='http://www.w3.org/2005/Atom'>
  <title>Example Atom</title>
  <entry>
    <title>Interesting atom post</title>
    <link href='https://example.test/atom-item' />
  </entry>
</feed>
"""


class SignalFetchTests(unittest.TestCase):
    def test_parse_signal_feed_accepts_rss_and_atom(self):
        rss_item = parse_signal_feed(RSS_FEED)
        atom_item = parse_signal_feed(ATOM_FEED)

        self.assertEqual(rss_item["summary"], "Interesting mew post")
        self.assertEqual(rss_item["payload"]["url"], "https://example.test/rss-item")
        self.assertEqual(atom_item["summary"], "Interesting atom post")
        self.assertEqual(atom_item["payload"]["url"], "https://example.test/atom-item")

    def test_fetch_signal_source_records_first_feed_item(self):
        state = default_state()
        enable_signal_source(
            state,
            "hn",
            kind="atom",
            reason="track engineering stories",
            config={"url": "https://example.test/feed.xml"},
            current_time="2026-04-20T00:00:00Z",
        )

        class FakeResponse:
            def __init__(self, text):
                self.text = text

            def read(self):
                return self.text.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        calls = []

        def fake_open(url, timeout=10):
            calls.append((url, timeout))
            return FakeResponse(RSS_FEED)

        result = fetch_signal_source(
            state,
            "hn",
            opener=fake_open,
            current_time="2026-04-20T00:01:00Z",
        )

        self.assertEqual(calls, [("https://example.test/feed.xml", 10)])
        self.assertEqual(result["status"], "recorded")
        self.assertEqual(len(state["signals"]["journal"]), 1)
        self.assertEqual(result["signal"]["summary"], "Interesting mew post")
        self.assertEqual(result["signal"]["payload"]["url"], "https://example.test/rss-item")
        self.assertEqual(result["signal"]["payload"]["feed_url"], "https://example.test/feed.xml")
        self.assertEqual(result["signal"]["event_id"], 1)
        self.assertEqual(state["inbox"][0]["type"], "signal_observed")

    def test_fetch_signal_source_checks_budget_before_network(self):
        state = default_state()
        enable_signal_source(
            state,
            "hn",
            kind="rss",
            reason="track engineering stories",
            budget_limit=0,
            config={"url": "https://example.test/feed.xml"},
            current_time="2026-04-20T00:00:00Z",
        )
        calls = []

        def fake_open(url, timeout=10):
            calls.append((url, timeout))
            raise AssertionError("budget-exhausted source should not be fetched")

        result = fetch_signal_source(
            state,
            "hn",
            opener=fake_open,
            current_time="2026-04-20T00:01:00Z",
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "budget_exhausted")
        self.assertEqual(calls, [])
        self.assertEqual(state["signals"]["journal"], [])
