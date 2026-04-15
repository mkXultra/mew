import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mew.config import LOG_FILE, STATE_DIR, STATE_FILE
from mew.dogfood import (
    build_dogfood_report,
    build_runtime_command,
    copy_source_workspace,
    format_dogfood_loop_report,
    format_dogfood_report,
    prepopulate_project_snapshot,
    prepare_dogfood_workspace,
)
from mew.state import add_event, add_outbox_message, default_state


class DogfoodTests(unittest.TestCase):
    def test_prepare_workspace_creates_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace, created = prepare_dogfood_workspace(Path(tmp) / "dog")

            self.assertFalse(created)
            self.assertTrue((workspace / "README.md").exists())

    def test_build_runtime_command_keeps_ai_optional(self):
        args = SimpleNamespace(
            interval=3,
            poll_interval=0.2,
            autonomy_level="act",
            model_timeout=45,
            ai=False,
            auth=None,
            model_backend="codex",
            model="",
            base_url="",
            allow_write=False,
            allow_verify=False,
            verify_command="",
            verify_interval_minutes=0.05,
        )

        command = build_runtime_command(args, Path("/tmp/work"))

        self.assertIn("--autonomous", command)
        self.assertNotIn("--ai", command)

    def test_build_runtime_command_resolves_relative_auth_before_workspace_cwd(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                args = SimpleNamespace(
                    interval=3,
                    poll_interval=0.2,
                    autonomy_level="act",
                    model_timeout=45,
                    ai=True,
                    auth="auth.json",
                    model_backend="codex",
                    model="",
                    base_url="",
                    allow_write=False,
                    allow_verify=False,
                    verify_command="",
                    verify_interval_minutes=0.05,
                )

                command = build_runtime_command(args, Path("/tmp/work"))

                self.assertEqual(command[command.index("--auth") + 1], str((Path(tmp) / "auth.json").resolve()))
            finally:
                os.chdir(old_cwd)

    def test_copy_source_workspace_skips_sensitive_state_and_large_files(self):
        with tempfile.TemporaryDirectory() as source_tmp, tempfile.TemporaryDirectory() as workspace_tmp:
            source = Path(source_tmp)
            workspace = Path(workspace_tmp)
            (source / "src").mkdir()
            (source / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (source / "auth.json").write_text("secret", encoding="utf-8")
            (source / ".mew").mkdir()
            (source / ".mew" / "state.json").write_text("{}", encoding="utf-8")
            (source / "large.txt").write_text("x" * 200, encoding="utf-8")

            result = copy_source_workspace(source, workspace, max_file_bytes=100)

            self.assertEqual(result["copied_files"], 1)
            self.assertTrue((workspace / "src" / "app.py").exists())
            self.assertFalse((workspace / "auth.json").exists())
            self.assertFalse((workspace / ".mew").exists())
            self.assertFalse((workspace / "large.txt").exists())

    def test_build_report_summarizes_state_and_runtime_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".mew").mkdir()
            state = default_state()
            state["runtime_status"]["last_cycle_reason"] = "passive_tick"
            state["runtime_status"]["last_cycle_duration_seconds"] = 1.25
            state["runtime_status"]["last_processed_count"] = 1
            event = add_event(state, "passive_tick", "runtime")
            event["processed_at"] = "done"
            event["decision_plan"] = {
                "summary": "x",
                "schema_issues": [{"level": "warning", "path": "decisions[0].type", "message": "unsupported"}],
            }
            add_outbox_message(state, "info", "hello", event_id=event["id"])
            state["thought_journal"].append(
                {
                    "id": 1,
                    "event_id": event["id"],
                    "event_type": "passive_tick",
                    "summary": "Inspected workspace.",
                    "actions": [{"type": "inspect_dir", "path": str(workspace)}],
                    "counts": {"actions": 1, "messages": 1},
                    "open_threads": [],
                    "resolved_threads": [],
                    "dropped_threads": [],
                }
            )
            state["memory"]["deep"]["project_snapshot"] = {
                "updated_at": "now",
                "project_types": ["python"],
                "roots": [],
                "files": [],
                "searches": [],
                "package": {"name": "mew"},
            }
            (workspace / STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
            (workspace / LOG_FILE).write_text(
                "- now: think_phase codex ok event=1\n- now: act_phase codex ok event=1\n",
                encoding="utf-8",
            )

            runtime_out_path = workspace / STATE_DIR / "dogfood-runtime.out"
            runtime_out_path.write_text(
                "mew runtime started pid=1\nprocessed 1 event(s) reason=startup\nmew runtime stopped\n",
                encoding="utf-8",
            )

            report = build_dogfood_report(workspace, ["mew", "run"], 0, 1.5)
            text = format_dogfood_report(report)

            self.assertEqual(report["events"]["processed"], 1)
            self.assertEqual(report["model_phases"]["think_ok"], 1)
            self.assertEqual(report["runtime_status"]["last_cycle_reason"], "passive_tick")
            self.assertEqual(report["actions"], {"inspect_dir": 1})
            self.assertEqual(report["plan_schema_issues"]["count"], 1)
            self.assertEqual(report["project_snapshot"]["project_types"], ["python"])
            self.assertEqual(report["active_dropped_threads"]["thought_count"], 0)
            self.assertIn("Recent activity", text)
            self.assertIn("Project snapshot", text)
            self.assertIn("runtime_cycle:", text)
            self.assertEqual(len(report["runtime_output_tail"]), 3)
            self.assertIn("Runtime output (last lines)", text)
            self.assertIn("mew runtime stopped", text)
            self.assertIn("plan_schema_issues", text)

    def test_prepopulate_project_snapshot_writes_dogfood_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "src").mkdir()
            (workspace / "tests").mkdir()
            (workspace / "README.md").write_text("# Demo\n", encoding="utf-8")
            (workspace / "pyproject.toml").write_text('[project]\nname = "demo"\n', encoding="utf-8")

            report = prepopulate_project_snapshot(workspace)
            state = json.loads((workspace / STATE_FILE).read_text(encoding="utf-8"))

            self.assertEqual(len(report["read_files"]), 2)
            self.assertEqual(state["memory"]["deep"]["project_snapshot"]["package"]["name"], "demo")
            self.assertEqual(state["dogfood"]["pre_snapshot"]["path"], str(workspace.resolve()))

    def test_format_dogfood_loop_report_summarizes_cycles(self):
        text = format_dogfood_loop_report(
            {
                "generated_at": "now",
                "workspace": "/tmp/dog",
                "cycle_count": 2,
                "exit_codes": [0, 0],
                "final_events": {"processed": 3, "total": 3},
                "final_model_phases": {"think_ok": 2, "act_ok": 2},
                "final_runtime_status": {
                    "last_cycle_reason": "passive_tick",
                    "last_cycle_duration_seconds": 1.2,
                    "last_processed_count": 3,
                },
                "final_plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                "final_dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                "final_active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                "final_next_move": "keep going",
                "final_project_snapshot": {"updated_at": "now", "project_types": ["python"]},
                "cycles": [
                    {
                        "cycle": 1,
                        "exit_code": 0,
                        "duration_seconds": 1.2,
                        "events": {"processed": 1, "total": 1},
                        "model_phases": {"think_ok": 1, "act_ok": 1},
                        "dropped_threads": {"thought_count": 0, "latest": []},
                        "active_dropped_threads": {"thought_count": 0, "latest": []},
                        "plan_schema_issues": {"count": 0, "by_level": {}, "latest": []},
                        "next_move": "cycle one",
                    },
                    {
                        "cycle": 2,
                        "exit_code": 0,
                        "duration_seconds": 1.4,
                        "events": {"processed": 3, "total": 3},
                        "model_phases": {"think_ok": 2, "act_ok": 2},
                        "dropped_threads": {"thought_count": 1, "latest": ["carry this"]},
                        "active_dropped_threads": {"thought_count": 1, "thought_id": 2, "latest": ["carry this"]},
                        "plan_schema_issues": {"count": 1, "by_level": {"warning": 1}, "latest": []},
                        "next_move": "keep going",
                    },
                ],
            }
        )

        self.assertIn("cycles: 2", text)
        self.assertIn("Cycle summaries", text)
        self.assertIn("final_dropped_threads", text)
        self.assertIn("final_active_dropped_threads", text)
        self.assertIn("dropped_threads=1", text)
        self.assertIn("active_dropped_threads=1", text)
        self.assertIn("schema_issues=1", text)
        self.assertIn("final_plan_schema_issues", text)
        self.assertIn("final_runtime_cycle", text)
        self.assertIn("Final project snapshot", text)
        self.assertIn("Final next useful move: keep going", text)


if __name__ == "__main__":
    unittest.main()
