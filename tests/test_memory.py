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
from mew.symbol_index import rebuild_symbol_index
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

            file_pair = backend.write(
                "work_session.py changes usually need tests/test_work_session.py updates.",
                scope="private",
                memory_type="project",
                memory_kind="file-pair",
                name="work_session pair",
                source_path="src/mew/work_session.py",
                test_path="tests/test_work_session.py",
                structural_evidence="same-session read of both files plus observed co-edit",
                focused_test_green=True,
            )
            self.assertEqual(file_pair.memory_kind, "file-pair")
            self.assertEqual(file_pair.source_path, "src/mew/work_session.py")
            self.assertEqual(file_pair.test_path, "tests/test_work_session.py")
            self.assertTrue(file_pair.focused_test_green)

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

            with self.assertRaisesRegex(ValueError, "--structural-evidence"):
                backend.write(
                    "Broken file pair",
                    scope="private",
                    memory_type="project",
                    memory_kind="file-pair",
                    name="Broken pair",
                    source_path="src/mew/work_session.py",
                    test_path="tests/test_work_session.py",
                    focused_test_green=True,
                )

            with self.assertRaisesRegex(ValueError, "--focused-test-green"):
                backend.write(
                    "Broken file pair",
                    scope="private",
                    memory_type="project",
                    memory_kind="file-pair",
                    name="Broken pair",
                    source_path="src/mew/work_session.py",
                    test_path="tests/test_work_session.py",
                    structural_evidence="same-session read of both files",
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
                                "--source-path",
                                "src/mew/work_session.py",
                                "--test-path",
                                "tests/test_work_session.py",
                                "--structural-evidence",
                                "same-session read of both targets",
                                "--focused-test-green",
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

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["memory", "--active", "--resolve-source-path", "src/mew/cli.py"]), 1)
                self.assertIn("--active cannot be combined", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_resolve_source_path_reports_pair_and_memory_ids(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                backend = FileMemoryBackend(".")
                entry = backend.write(
                    "commands.py and test_memory.py should stay aligned.",
                    scope="private",
                    memory_type="project",
                    memory_kind="file-pair",
                    name="commands/test memory pair",
                    source_path="src/mew/commands.py",
                    test_path="tests/test_memory.py",
                    structural_evidence="same-session source/test review",
                    focused_test_green=True,
                )
                rebuild_symbol_index(".")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["memory", "--resolve-source-path", "src/mew/commands.py", "--json"]),
                        0,
                    )
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["resolved"]["source_path"], "src/mew/commands.py")
                self.assertEqual(payload["resolved"]["test_path"], "tests/test_memory.py")
                self.assertEqual(payload["resolved"]["memory_ids"], [entry.id])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--resolve-source-path", "src/mew/commands.py"]), 0)
                text = stdout.getvalue()
                self.assertIn("source_path: src/mew/commands.py", text)
                self.assertIn("test_path: tests/test_memory.py", text)
                self.assertIn(f"memory_ids: {entry.id}", text)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--resolve-test-path", "tests/test_memory.py", "--json"]), 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["resolved"]["source_path"], "src/mew/commands.py")
                self.assertEqual(payload["resolved"]["test_path"], "tests/test_memory.py")
                self.assertEqual(payload["resolved"]["memory_ids"], [entry.id])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--resolve-test-path", "tests/test_memory.py"]), 0)
                text = stdout.getvalue()
                self.assertIn("source_path: src/mew/commands.py", text)
                self.assertIn("test_path: tests/test_memory.py", text)
                self.assertIn(f"memory_ids: {entry.id}", text)

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["memory", "--resolve-source-path", "src/mew/missing.py"]), 1)
                self.assertIn("typed memory not found for source path", stderr.getvalue())

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(main(["memory", "--resolve-test-path", "tests/missing_test.py"]), 1)
                self.assertIn("typed memory not found for test path", stderr.getvalue())

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(["memory", "--list", "--resolve-source-path", "src/mew/commands.py"]),
                        1,
                    )
                self.assertIn("choose only one", stderr.getvalue())

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(["memory", "--list", "--resolve-test-path", "tests/test_memory.py"]),
                        1,
                    )
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

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Missing file-pair structure",
                                "--type",
                                "project",
                                "--kind",
                                "file-pair",
                                "--name",
                                "Broken pair",
                                "--source-path",
                                "src/mew/work_session.py",
                                "--test-path",
                                "tests/test_work_session.py",
                                "--focused-test-green",
                            ]
                        ),
                        1,
                    )
                self.assertIn("--structural-evidence", stderr.getvalue())

                with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Missing file-pair green test",
                                "--type",
                                "project",
                                "--kind",
                                "file-pair",
                                "--name",
                                "Broken pair",
                                "--source-path",
                                "src/mew/work_session.py",
                                "--test-path",
                                "tests/test_work_session.py",
                                "--structural-evidence",
                                "same-session read of both files",
                            ]
                        ),
                        1,
                    )
                self.assertIn("--focused-test-green", stderr.getvalue())
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_add_file_pair_surfaces_structural_fields(self):
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
                                "work_session.py maps to tests/test_work_session.py",
                                "--type",
                                "project",
                                "--kind",
                                "file-pair",
                                "--scope",
                                "private",
                                "--name",
                                "work_session pair",
                                "--source-path",
                                "src/mew/work_session.py",
                                "--test-path",
                                "tests/test_work_session.py",
                                "--structural-evidence",
                                "same-session read of both targets and observed co-edit",
                                "--focused-test-green",
                                "--json",
                            ]
                        ),
                        0,
                    )
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["entry"]["memory_kind"], "file-pair")
                self.assertEqual(data["entry"]["source_path"], "src/mew/work_session.py")
                self.assertEqual(data["entry"]["test_path"], "tests/test_work_session.py")
                self.assertEqual(
                    data["entry"]["structural_evidence"],
                    "same-session read of both targets and observed co-edit",
                )
                self.assertTrue(data["entry"]["focused_test_green"])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["memory", "--resolve-source-path", "src/mew/work_session.py", "--json"]),
                        0,
                    )
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["resolved"]["source_path"], "src/mew/work_session.py")
                self.assertEqual(payload["resolved"]["test_path"], "tests/test_work_session.py")
                self.assertEqual(payload["resolved"]["memory_ids"], [data["entry"]["id"]])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(["memory", "--resolve-test-path", "tests/test_work_session.py", "--json"]),
                        0,
                    )
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["resolved"]["source_path"], "src/mew/work_session.py")
                self.assertEqual(payload["resolved"]["test_path"], "tests/test_work_session.py")
                self.assertEqual(payload["resolved"]["memory_ids"], [data["entry"]["id"]])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--show", data["entry"]["id"]]), 0)
                text = stdout.getvalue()
                self.assertIn("source_path: src/mew/work_session.py", text)
                self.assertIn("test_path: tests/test_work_session.py", text)
                self.assertIn("focused_test_green: yes", text)
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_reviewer_diffs_surfaces_json_and_human_output(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--reviewer-diffs", "--json"]), 0)
                self.assertEqual(json.loads(stdout.getvalue()), {"records": []})

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--reviewer-diffs"]), 0)
                self.assertEqual(stdout.getvalue(), "No reviewer diff records.\n")

                durable = Path(".mew") / "durable"
                durable.mkdir(parents=True, exist_ok=True)
                payload = {
                    "task_id": 12,
                    "session_id": 34,
                    "path": "src/mew/commands.py",
                    "recorded_at": "2026-04-22T00:00:00Z",
                    "ai_draft": {"tool": "write_file", "diff": "draft"},
                    "reviewer_approved": {"status": "applied"},
                    "ai_final": {"diff": "final"},
                }
                (durable / "reviewer_diffs.jsonl").write_text(
                    json.dumps(payload, ensure_ascii=False) + "\n",
                    encoding="utf-8",
                )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--reviewer-diffs", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                self.assertEqual(data["records"], [payload])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--reviewer-diffs"]), 0)
                text = stdout.getvalue()
                self.assertIn("task=#12", text)
                self.assertIn("session=#34", text)
                self.assertIn("tool=write_file", text)
                self.assertIn("recorded_at=2026-04-22T00:00:00Z", text)
                self.assertIn("path=src/mew/commands.py", text)
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_reviewer_diffs_collides_with_other_read_only_flags(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["memory", "--reviewer-diffs", "--list"]), 1)
        self.assertIn("choose only one", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["memory", "--reviewer-diffs", "--search", "trace"]), 1)
        self.assertIn("cannot be combined", stderr.getvalue())

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

    def test_cli_memory_veto_log_reads_durable_log(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--veto-log", "--json"]), 0)
                self.assertEqual(json.loads(stdout.getvalue())["records"], [])

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Remember this note so the veto log has an entry.",
                                "--type",
                                "project",
                                "--kind",
                                "failure-shield",
                                "--scope",
                                "private",
                                "--name",
                                "Veto log note",
                                "--approved",
                                "--symptom",
                                "stale durable note was reused",
                                "--root-cause",
                                "veto history was hidden",
                                "--fix",
                                "surface the durable veto log",
                                "--stop-rule",
                                "stop if veto log cannot be inspected",
                                "--json",
                            ]
                        ),
                        0,
                    )
                entry_id = json.loads(stdout.getvalue())["entry"]["id"]

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--veto",
                                entry_id,
                                "--reason",
                                "reviewer rejected this durable note",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--veto-log", "--json"]), 0)
                payload = json.loads(stdout.getvalue())
                self.assertEqual(payload["records"][-1]["entry_id"], entry_id)
                self.assertEqual(payload["records"][-1]["reason"], "reviewer rejected this durable note")

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--veto-log"]), 0)
                text = stdout.getvalue()
                self.assertIn(f"entry_id={entry_id}", text)
                self.assertIn("reason=reviewer rejected this durable note", text)
            finally:
                os.chdir(old_cwd)

    def test_cli_memory_veto_log_collides_with_other_memory_modes(self):
        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["memory", "--veto-log", "--list"]), 1)
        self.assertIn("choose only one", stderr.getvalue())

        with redirect_stdout(StringIO()), redirect_stderr(StringIO()) as stderr:
            self.assertEqual(main(["memory", "--veto-log", "--search", "trace"]), 1)
        self.assertIn("cannot be combined", stderr.getvalue())

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

    def test_cli_memory_active_revises_and_drops_file_pair_entries(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                Path("src").mkdir()
                Path("tests").mkdir()
                Path("src/demo.py").write_text("def demo():\n    return 1\n", encoding="utf-8")
                Path("tests/test_demo.py").write_text("def test_demo():\n    assert True\n", encoding="utf-8")

                with redirect_stdout(StringIO()):
                    self.assertEqual(
                        main(
                            [
                                "memory",
                                "--add",
                                "Active Recall Debug file pair for src/demo.py and tests/test_demo.py.",
                                "--type",
                                "project",
                                "--scope",
                                "private",
                                "--name",
                                "Active Recall Debug pair",
                                "--kind",
                                "file-pair",
                                "--source-path",
                                "src/demo.py",
                                "--test-path",
                                "tests/test_demo.py",
                                "--structural-evidence",
                                "same-session read of src/demo.py and tests/test_demo.py",
                                "--focused-test-green",
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        main(
                            [
                                "task",
                                "add",
                                "Active Recall Debug pair",
                                "--kind",
                                "coding",
                                "--description",
                                "Check active typed memory injection for the Active Recall Debug pair.",
                            ]
                        ),
                        0,
                    )

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--active", "--task-id", "1", "--json"]), 0)
                data = json.loads(stdout.getvalue())
                active_memory = data["active_memory"]
                file_pair = next(item for item in active_memory["items"] if item.get("memory_kind") == "file-pair")
                self.assertEqual(file_pair["revise_status"], "kept")
                self.assertEqual(file_pair["source_path"], "src/demo.py")
                self.assertEqual(file_pair["test_path"], "tests/test_demo.py")
                self.assertNotIn("dropped_items", active_memory)

                Path("tests/test_demo.py").unlink()

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["memory", "--active", "--task-id", "1", "--json"]), 0)
                dropped_data = json.loads(stdout.getvalue())
                dropped_memory = dropped_data["active_memory"]
                self.assertFalse(
                    any(item.get("memory_kind") == "file-pair" for item in dropped_memory["items"]),
                    dropped_memory,
                )
                self.assertEqual(dropped_memory["dropped_items"][0]["drop_reason"], "precondition_miss")
                self.assertEqual(dropped_memory["dropped_items"][0]["missing_paths"], ["tests/test_demo.py"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
