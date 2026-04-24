import os
from pathlib import Path
import tempfile
import unittest

from mew.state import default_state
from mew.watchers import scan_watch_paths


class WatcherTests(unittest.TestCase):
    def test_scan_watch_paths_baselines_then_queues_file_change(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                path = Path("watched.txt")
                path.write_text("one\n", encoding="utf-8")
                state = default_state()

                baseline = scan_watch_paths(state, [str(path)], current_time="2026-04-20T00:00:00Z")
                repeat = scan_watch_paths(state, [str(path)], current_time="2026-04-20T00:00:01Z")
                path.write_text("two changed\n", encoding="utf-8")
                changed = scan_watch_paths(
                    state,
                    [str(path)],
                    current_time="2026-04-20T00:00:02Z",
                    active=True,
                )

                self.assertEqual(baseline["events"], [])
                self.assertTrue(baseline["changed"])
                self.assertEqual(repeat["events"], [])
                self.assertFalse(repeat["changed"])
                self.assertEqual(len(changed["events"]), 1)
                event = changed["events"][0]
                self.assertEqual(event["type"], "file_change")
                self.assertEqual(event["source"], "daemon_watch")
                self.assertEqual(event["payload"]["path"], "watched.txt")
                self.assertEqual(event["payload"]["change_kind"], "modified")
                self.assertEqual(state["watchers"]["items"][0]["status"], "active")
                self.assertEqual(state["watchers"]["items"][0]["last_event_id"], event["id"])
            finally:
                os.chdir(old_cwd)

    def test_scan_watch_paths_prunes_unrequested_file_watchers(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                first = Path("first.txt")
                second = Path("second.txt")
                first.write_text("one\n", encoding="utf-8")
                second.write_text("two\n", encoding="utf-8")
                state = default_state()

                baseline = scan_watch_paths(state, [str(first)], current_time="2026-04-20T00:00:00Z", active=True)
                rebound = scan_watch_paths(state, [str(second)], current_time="2026-04-20T00:00:01Z", active=True)

                self.assertTrue(baseline["changed"])
                self.assertTrue(rebound["changed"])
                self.assertEqual(state["watchers"]["count"], 1)
                self.assertEqual(state["watchers"]["active_count"], 1)
                self.assertEqual(len(state["watchers"]["items"]), 1)
                self.assertEqual(state["watchers"]["items"][0]["path"], "second.txt")
                self.assertEqual(state["watchers"]["items"][0]["status"], "active")
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
