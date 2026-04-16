import os
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from mew.cli import main
from mew.memory import compact_memory, search_memory
from mew.state import default_state, load_state, save_state


def add_recent_events(state, count):
    recent = state["memory"]["shallow"]["recent_events"]
    for index in range(count):
        recent.append(
            {
                "at": f"t{index}",
                "event_id": index + 1,
                "event_type": "passive_tick",
                "summary": f"summary {index}",
            }
        )


class MemoryTests(unittest.TestCase):
    def test_compact_memory_moves_recent_to_project_note(self):
        state = default_state()
        state["memory"]["shallow"]["current_context"] = "Working context"
        add_recent_events(state, 8)

        note = compact_memory(state, keep_recent=3)

        self.assertIn("Compacted recent events: 5", note)
        self.assertEqual(len(state["memory"]["shallow"]["recent_events"]), 3)
        self.assertEqual(len(state["memory"]["deep"]["project"]), 1)

    def test_compact_memory_dry_run_does_not_mutate(self):
        state = default_state()
        add_recent_events(state, 3)

        compact_memory(state, keep_recent=1, dry_run=True)

        self.assertEqual(len(state["memory"]["shallow"]["recent_events"]), 3)
        self.assertEqual(state["memory"]["deep"]["project"], [])

    def test_search_memory_finds_shallow_and_deep_entries(self):
        state = default_state()
        state["memory"]["shallow"]["current_context"] = "Working on model trace logs"
        state["memory"]["deep"]["decisions"].append("Keep running-task focus as the default.")
        add_recent_events(state, 2)

        trace_results = search_memory(state, "model trace")
        self.assertEqual(trace_results[0]["key"], "current_context")

        focus_results = search_memory(state, "running focus")
        self.assertEqual(focus_results[0]["scope"], "deep")
        self.assertEqual(focus_results[0]["key"], "decisions")

    def test_cli_memory_compact(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = load_state()
                add_recent_events(state, 4)
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--compact", "--keep-recent", "1"]), 0)

                self.assertIn("Memory compact", stdout.getvalue())
                state = load_state()
                self.assertEqual(len(state["memory"]["shallow"]["recent_events"]), 1)
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_search(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                state = load_state()
                state["memory"]["shallow"]["current_context"] = "Trace logs are useful for runtime debugging."
                state["memory"]["deep"]["project"].append("Model runtime should expose trace search.")
                save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--search", "trace"]), 0)
                output = stdout.getvalue()
                self.assertIn("shallow.current_context", output)
                self.assertIn("deep.project", output)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--search", "runtime", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["query"], "runtime")
                self.assertTrue(data["matches"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
