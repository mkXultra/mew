import os
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.memory import add_deep_memory, compact_memory, recall_memory, search_memory
from mew.state import default_state, load_state, save_state
from mew.typed_memory import FileMemoryBackend


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

    def test_search_memory_returns_focused_project_snapshot_leaf(self):
        state = default_state()
        state["memory"]["deep"]["project_snapshot"] = {
            "updated_at": "now",
            "files": [
                {
                    "path": "README.md",
                    "kind": "readme",
                    "summary": "Nebula anchor runtime notes for model continuity.",
                }
            ],
        }

        summary_results = search_memory(state, "nebula anchor")

        self.assertEqual(summary_results[0]["scope"], "deep")
        self.assertEqual(summary_results[0]["key"], "project_snapshot.files[0].summary")
        self.assertEqual(summary_results[0]["text"], "Nebula anchor runtime notes for model continuity.")
        self.assertEqual(summary_results[0]["source_path"], "README.md")
        self.assertNotIn("{", summary_results[0]["text"])

    def test_search_memory_matches_project_snapshot_paths(self):
        state = default_state()
        state["memory"]["deep"]["project_snapshot"] = {
            "updated_at": "now",
            "files": [{"path": "docs/continuity.md", "summary": "Long-running session notes."}],
        }

        path_results = search_memory(state, "docs/continuity.md")

        self.assertEqual(path_results[0]["key"], "project_snapshot.files[0].path")
        self.assertEqual(path_results[0]["text"], "docs/continuity.md")

    def test_add_deep_memory_records_timestamped_entry(self):
        state = default_state()

        entry = add_deep_memory(state, "decisions", "Preserve passive-first design.", current_time="now")

        self.assertEqual(entry, "now: Preserve passive-first design.")
        self.assertEqual(state["memory"]["deep"]["decisions"], [entry])

    def test_file_memory_backend_writes_typed_scoped_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileMemoryBackend(tmp)

            entry = backend.write(
                "Prefer compact diffs when reviewing mew.",
                scope="private",
                memory_type="user",
                name="Review preference",
                description="Human prefers compact diffs.",
                created_at="2026-04-19T00:00:00Z",
            )

            self.assertEqual(entry.scope, "private")
            self.assertEqual(entry.memory_type, "user")
            self.assertTrue(entry.path.exists())
            text = entry.path.read_text(encoding="utf-8")
            self.assertIn('type = "user"', text)
            self.assertIn("Prefer compact diffs", text)
            recalled = backend.recall("compact diffs", scope="private", memory_type="user")
            self.assertEqual(recalled[0].name, "Review preference")

    def test_recall_memory_filters_typed_memory_without_migrating_legacy(self):
        state = default_state()
        state["memory"]["deep"]["project"].append("Legacy project fact about runtime traces.")
        with tempfile.TemporaryDirectory() as tmp:
            FileMemoryBackend(tmp).write(
                "Runtime trace preference belongs to the user.",
                scope="private",
                memory_type="user",
                name="Trace preference",
                created_at="2026-04-19T00:00:00Z",
            )

            user_results = recall_memory(
                state,
                "runtime trace",
                base_dir=tmp,
                memory_type="user",
            )
            unknown_results = recall_memory(
                state,
                "runtime trace",
                base_dir=tmp,
                memory_type="unknown",
            )

        self.assertEqual(user_results[0]["memory_type"], "user")
        self.assertEqual(user_results[0]["name"], "Trace preference")
        self.assertEqual(unknown_results[0]["memory_type"], "unknown")
        self.assertEqual(unknown_results[0]["storage"], "state")

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

    def test_cli_memory_add(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["memory", "--add", "Mew is a model runtime.", "--category", "decisions"]),
                        0,
                    )
                self.assertIn("remembered decisions", stdout.getvalue())

                state = load_state()
                self.assertIn("Mew is a model runtime.", state["memory"]["deep"]["decisions"][0])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--search", "model runtime", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["matches"][0]["key"], "decisions")
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_and_search_typed_memory(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "The mew project should prioritize typed memory.",
                                "--type",
                                "project",
                                "--scope",
                                "private",
                                "--name",
                                "Typed memory priority",
                                "--description",
                                "Next inhabitation slice.",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["entry"]["memory_type"], "project")
                self.assertTrue((Path(data["entry"]["path"])).exists())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["memory", "--search", "inhabitation slice", "--type", "project", "--json"]),
                        0,
                    )
                search_data = json.loads(stdout.getvalue())
                self.assertEqual(search_data["matches"][0]["name"], "Typed memory priority")
                self.assertEqual(search_data["matches"][0]["memory_scope"], "private")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--deep"]), 0)
                self.assertIn("typed_memory:", stdout.getvalue())
                self.assertIn("private.project Typed memory priority", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_rejects_typed_metadata_without_type(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["memory", "--add", "remember this", "--scope", "private"]), 1)

        self.assertIn("requires --type", stderr.getvalue())

    def test_cli_memory_active_surfaces_injected_typed_memory(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "For Active Recall Debug, inspect README.md before finishing.",
                                "--type",
                                "project",
                                "--scope",
                                "private",
                                "--name",
                                "Active recall debug route",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "task",
                                "add",
                                "Active Recall Debug",
                                "--kind",
                                "coding",
                                "--description",
                                "Check active typed memory injection.",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--active", "--task-id", "1", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                active_memory = data["active_memory"]
                self.assertEqual(data["task"]["id"], 1)
                self.assertTrue(
                    any(item["name"] == "Active recall debug route" for item in active_memory["items"]),
                    active_memory,
                )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--active", "--task-id", "1"]), 0)
                text = stdout.getvalue()
                self.assertIn("Active memory for task #1", text)
                self.assertIn("Active recall debug route", text)
                self.assertIn("created_at=", text)
                self.assertIn("score=", text)
                self.assertIn("matched=", text)

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["memory", "--active", "--search", "debug"]), 1)
                self.assertIn("cannot be combined", stderr.getvalue())
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
