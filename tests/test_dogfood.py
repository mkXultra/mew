import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from mew.config import LOG_FILE, STATE_DIR, STATE_FILE
from mew.dogfood import (
    build_dogfood_report,
    build_runtime_command,
    format_dogfood_report,
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

    def test_build_report_summarizes_state_and_runtime_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / ".mew").mkdir()
            state = default_state()
            event = add_event(state, "passive_tick", "runtime")
            event["processed_at"] = "done"
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
            self.assertEqual(report["actions"], {"inspect_dir": 1})
            self.assertIn("Recent activity", text)
            self.assertEqual(len(report["runtime_output_tail"]), 3)
            self.assertIn("Runtime output (last lines)", text)
            self.assertIn("mew runtime stopped", text)


if __name__ == "__main__":
    unittest.main()
