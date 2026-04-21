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
            self.assertEqual(entry.memory_kind, "")
            self.assertTrue(entry.path.exists())
            text = entry.path.read_text(encoding="utf-8")
            self.assertIn('type = "user"', text)
            self.assertIn("Prefer compact diffs", text)
            recalled = backend.recall("compact diffs", scope="private", memory_type="user")
            self.assertEqual(recalled[0].name, "Review preference")

    def test_file_memory_backend_supports_project_memory_kind(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileMemoryBackend(tmp)

            entry = backend.write(
                "Reviewer approved keeping scope fences explicit.",
                scope="private",
                memory_type="project",
                memory_kind="reviewer-steering",
                name="Scope fence rule",
                description="Keep scope fences explicit.",
                created_at="2026-04-19T00:00:00Z",
                approved=True,
                why="repeated reviewer correction",
                how_to_apply="keep scope fences explicit in future edits",
            )

            self.assertEqual(entry.memory_kind, "reviewer-steering")
            text = entry.path.read_text(encoding="utf-8")
            self.assertIn('kind = "reviewer-steering"', text)
            self.assertIn('approved = "true"', text)
            self.assertIn('why = "repeated reviewer correction"', text)
            self.assertIn('how_to_apply = "keep scope fences explicit in future edits"', text)
            recalled = backend.recall(
                "scope fences",
                scope="private",
                memory_type="project",
                memory_kind="reviewer-steering",
            )
            self.assertEqual(recalled[0].memory_kind, "reviewer-steering")
            self.assertTrue(recalled[0].approved)

    def test_file_memory_backend_write_gate_rejects_incomplete_reviewer_steering(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FileMemoryBackend(tmp)

            with self.assertRaisesRegex(ValueError, "--approved"):
                backend.write(
                    "Reviewer note",
                    scope="private",
                    memory_type="project",
                    memory_kind="reviewer-steering",
                    name="Broken steering",
                )

            with self.assertRaisesRegex(ValueError, "--rationale"):
                backend.write(
                    "Reusable coding loop template",
                    scope="private",
                    memory_type="project",
                    memory_kind="task-template",
                    name="Loop template",
                    approved=True,
                )

            template = backend.write(
                "Use focused verifier first, then broader unittest.",
                scope="private",
                memory_type="project",
                memory_kind="task-template",
                name="Verifier ordering template",
                approved=True,
                rationale="keeps reviewer-gated iterations small and repeatable",
            )
            self.assertEqual(template.memory_kind, "task-template")
            self.assertEqual(template.rationale, "keeps reviewer-gated iterations small and repeatable")

            shield = backend.write(
                "Avoid repeating the stale veto pattern.",
                scope="private",
                memory_type="project",
                memory_kind="failure-shield",
                name="Failure shield note",
                approved=True,
                symptom="veto pattern repeated",
                root_cause="durable stale note reused without reviewer context",
                fix="record reviewer veto before reusing the note",
                stop_rule="stop if reviewer context is missing",
            )
            self.assertEqual(shield.memory_kind, "failure-shield")
            self.assertEqual(shield.root_cause, "durable stale note reused without reviewer context")

            with self.assertRaisesRegex(ValueError, "--root-cause"):
                backend.write(
                    "Broken failure shield",
                    scope="private",
                    memory_type="project",
                    memory_kind="failure-shield",
                    name="Broken shield",
                    approved=True,
                    symptom="stale note reused",
                    fix="record reviewer veto",
                    stop_rule="stop if reviewer context is missing",
                )

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
                                "--kind",
                                "reviewer-steering",
                                "--scope",
                                "private",
                                "--name",
                                "Typed memory priority",
                                "--description",
                                "Next inhabitation slice.",
                                "--approved",
                                "--why",
                                "reviewer approved this durable rule",
                                "--how-to-apply",
                                "reuse it on future typed-memory changes",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["entry"]["memory_type"], "project")
                self.assertEqual(data["entry"]["memory_kind"], "reviewer-steering")
                self.assertTrue(data["entry"]["approved"])
                self.assertEqual(data["entry"]["why"], "reviewer approved this durable rule")
                self.assertEqual(data["entry"]["how_to_apply"], "reuse it on future typed-memory changes")
                self.assertTrue((Path(data["entry"]["path"])).exists())

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--search",
                                "inhabitation slice",
                                "--type",
                                "project",
                                "--kind",
                                "reviewer-steering",
                                "--json",
                            ]
                        ),
                        0,
                    )
                search_data = json.loads(stdout.getvalue())
                self.assertEqual(search_data["matches"][0]["name"], "Typed memory priority")
                self.assertEqual(search_data["matches"][0]["memory_scope"], "private")
                self.assertEqual(search_data["matches"][0]["memory_kind"], "reviewer-steering")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--deep"]), 0)
                self.assertIn("typed_memory:", stdout.getvalue())
                self.assertIn("private.project.reviewer-steering Typed memory priority", stdout.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_list_and_show_typed_memory_by_id(self):
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
                                "Keep reviewer steering memories concise.",
                                "--type",
                                "project",
                                "--kind",
                                "reviewer-steering",
                                "--scope",
                                "private",
                                "--name",
                                "Reviewer steering note",
                                "--approved",
                                "--why",
                                "reviewer wants durable steering",
                                "--how-to-apply",
                                "apply this rule on future memory edits",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Remember the matching test path for work_session changes.",
                                "--type",
                                "project",
                                "--kind",
                                "file-pair",
                                "--scope",
                                "private",
                                "--name",
                                "Paired test note",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--list",
                                "--type",
                                "project",
                                "--kind",
                                "reviewer-steering",
                                "--json",
                            ]
                        ),
                        0,
                    )
                list_data = json.loads(stdout.getvalue())
                self.assertEqual(len(list_data["entries"]), 1)
                entry = list_data["entries"][0]
                self.assertEqual(entry["memory_kind"], "reviewer-steering")
                self.assertEqual(entry["name"], "Reviewer steering note")
                self.assertTrue(entry["approved"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--show", entry["id"], "--json"]), 0)
                show_data = json.loads(stdout.getvalue())
                self.assertEqual(show_data["entry"]["id"], entry["id"])
                self.assertEqual(show_data["entry"]["name"], "Reviewer steering note")
                self.assertIn("Keep reviewer steering memories concise.", show_data["entry"]["text"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--show", entry["id"]]), 0)
                text = stdout.getvalue()
                self.assertIn(f"id: {entry['id']}", text)
                self.assertIn("label: private.project.reviewer-steering", text)
                self.assertIn("Reviewer steering note", text)

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["memory", "--list", "--show", entry["id"]]), 1)
                self.assertIn("choose only one", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_rejects_incomplete_d2_write_gate(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Missing reviewer approval",
                                "--type",
                                "project",
                                "--kind",
                                "reviewer-steering",
                                "--name",
                                "Broken steering",
                            ]
                        ),
                        1,
                    )
                self.assertIn("--approved", stderr.getvalue())

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Missing rationale",
                                "--type",
                                "project",
                                "--kind",
                                "task-template",
                                "--name",
                                "Broken template",
                                "--approved",
                            ]
                        ),
                        1,
                    )
                self.assertIn("--rationale", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_veto_hides_entry_from_list_and_surfaces_reason_in_show(self):
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
                                "Remember this bad durable note just long enough to veto it.",
                                "--type",
                                "project",
                                "--kind",
                                "failure-shield",
                                "--scope",
                                "private",
                                "--name",
                                "Bad durable note",
                                "--approved",
                                "--symptom",
                                "stale bad note was reused",
                                "--root-cause",
                                "reviewer veto was not remembered",
                                "--fix",
                                "persist the veto before reuse",
                                "--stop-rule",
                                "stop if reviewer context is missing",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--list", "--type", "project", "--json"]), 0)
                entry = json.loads(stdout.getvalue())["entries"][0]
                entry_path = Path(entry["path"])
                before_text = entry_path.read_text(encoding="utf-8")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--veto",
                                entry["id"],
                                "--reason",
                                "reviewer rejected this stale note",
                                "--json",
                            ]
                        ),
                        0,
                    )
                veto_data = json.loads(stdout.getvalue())
                self.assertEqual(veto_data["veto"]["entry_id"], entry["id"])
                self.assertEqual(veto_data["veto"]["reason"], "reviewer rejected this stale note")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--list", "--type", "project", "--json"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["entries"], [])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--show", entry["id"], "--json"]), 0)
                show_data = json.loads(stdout.getvalue())
                self.assertTrue(show_data["entry"]["vetoed"])
                self.assertEqual(show_data["entry"]["veto_reason"], "reviewer rejected this stale note")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--show", entry["id"]]), 0)
                text = stdout.getvalue()
                self.assertIn("vetoed: yes", text)
                self.assertIn("veto_reason: reviewer rejected this stale note", text)

                self.assertEqual(entry_path.read_text(encoding="utf-8"), before_text)

                veto_log = Path(".mew/durable/vetoes.jsonl")
                self.assertTrue(veto_log.exists())
                payload = json.loads(veto_log.read_text(encoding="utf-8").strip().splitlines()[-1])
                self.assertEqual(payload["entry_id"], entry["id"])
                self.assertEqual(payload["reason"], "reviewer rejected this stale note")
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_rejects_reasoning_trace_direct_write(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Store abstract reasoning trace.",
                                "--type",
                                "project",
                                "--kind",
                                "reasoning-trace",
                            ]
                        ),
                        1,
                    )
                self.assertIn("schema-only until Phase 2", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_rejects_incomplete_failure_shield(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Missing failure shield root cause",
                                "--type",
                                "project",
                                "--kind",
                                "failure-shield",
                                "--name",
                                "Broken shield",
                                "--approved",
                                "--symptom",
                                "stale note reused",
                                "--fix",
                                "persist a blocker",
                                "--stop-rule",
                                "stop if reviewer context is missing",
                            ]
                        ),
                        1,
                    )
                self.assertIn("--root-cause", stderr.getvalue())
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
