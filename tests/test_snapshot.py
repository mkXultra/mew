import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from mew.cli import main
from mew.snapshot import load_snapshot, save_snapshot, snapshot_path, take_snapshot
from mew.state import default_state


def snapshot_state():
    state = default_state()
    state["tasks"].append(
        {
            "id": 1,
            "title": "Snapshot task",
            "kind": "coding",
            "description": "Exercise persistent snapshot state.",
            "status": "ready",
            "priority": "normal",
            "created_at": "2026-04-20T00:00:00Z",
            "updated_at": "2026-04-20T00:00:00Z",
        }
    )
    state["runtime_effects"].append({"id": 7, "type": "passive_tick", "created_at": "now"})
    state["work_sessions"].append(
        {
            "id": 1,
            "task_id": 1,
            "status": "active",
            "title": "Snapshot task",
            "goal": "Exercise persistent snapshot state.",
            "created_at": "2026-04-20T00:00:00Z",
            "updated_at": "2026-04-20T00:01:00Z",
            "tool_calls": [
                {
                    "id": 1,
                    "tool": "read_file",
                    "status": "completed",
                    "parameters": {"path": "README.md"},
                    "result": {"path": "README.md", "text": "before"},
                    "summary": "Read README.md",
                },
                {
                    "id": 2,
                    "tool": "edit_file",
                    "status": "completed",
                    "parameters": {"path": "README.md"},
                    "result": {
                        "path": "README.md",
                        "dry_run": True,
                        "changed": True,
                        "written": False,
                        "matched": 1,
                        "diff": "--- a/README.md\n+++ b/README.md\n@@\n-before\n+after\n",
                    },
                    "summary": "Prepared README.md edit",
                },
            ],
            "model_turns": [
                {
                    "id": 1,
                    "status": "completed",
                    "decision_plan": {
                        "working_memory": {
                            "hypothesis": "Snapshot should remember pending approval.",
                            "next_step": "Approve the README.md edit, then verify.",
                        }
                    },
                    "action": {"type": "finish"},
                    "summary": "Paused for snapshot.",
                    "started_at": "2026-04-20T00:00:00Z",
                    "finished_at": "2026-04-20T00:01:00Z",
                }
            ],
        }
    )
    return state


class SnapshotTests(unittest.TestCase):
    def test_take_save_load_work_session_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = snapshot_state()

            snapshot = take_snapshot(1, state=state, base_dir=tmp, current_time="2026-04-20T00:02:00Z")
            path = save_snapshot(snapshot, base_dir=tmp)
            loaded = load_snapshot(1, state=state, base_dir=tmp)

            self.assertEqual(path, snapshot_path(1, base_dir=tmp))
            self.assertTrue(path.exists())
            self.assertIsNotNone(loaded)
            self.assertTrue(loaded.usable)
            self.assertEqual(loaded.snapshot.session_id, "1")
            self.assertEqual(loaded.snapshot.task_id, "1")
            self.assertEqual(loaded.snapshot.last_effect_id, 7)
            self.assertEqual(loaded.snapshot.touched_files, ["README.md"])
            self.assertEqual(len(loaded.snapshot.pending_approvals), 1)
            self.assertEqual(
                loaded.snapshot.working_memory["next_step"],
                "Approve the README.md edit, then verify.",
            )
            self.assertEqual(loaded.snapshot.continuity_status, "usable")

    def test_load_snapshot_reports_state_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = snapshot_state()
            save_snapshot(take_snapshot(1, state=state, base_dir=tmp), base_dir=tmp)
            state["tasks"][0]["title"] = "Changed after snapshot"

            loaded = load_snapshot(1, state=state, base_dir=tmp)

            self.assertIsNotNone(loaded)
            self.assertFalse(loaded.usable)
            self.assertIn("state_hash differs from current state", loaded.drift_notes)
            self.assertTrue(loaded.partial_reasons)

    def test_load_snapshot_preserves_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = snapshot_path("future/session", base_dir=tmp)
            path.parent.mkdir(parents=True)
            payload = take_snapshot(1, state=snapshot_state(), base_dir=tmp).to_dict()
            payload["future_field"] = {"kept": True}
            path.write_text(json.dumps(payload), encoding="utf-8")

            loaded = load_snapshot("future/session", state=snapshot_state(), base_dir=tmp)

            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.snapshot.unknown_fields["future_field"], {"kept": True})
            self.assertEqual(loaded.snapshot.to_dict()["future_field"], {"kept": True})

    def test_work_close_session_saves_snapshot(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["task", "add", "Snapshot CLI task", "--kind", "coding", "--ready"]), 0)
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", "1", "--start-session"]), 0)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["work", "1", "--close-session", "--json"]), 0)

                data = json.loads(stdout.getvalue())
                snapshot_file = Path(data["snapshot_path"])
                self.assertTrue(snapshot_file.exists())
                loaded = load_snapshot(data["work_session"]["id"])
                self.assertIsNotNone(loaded)
                self.assertTrue(loaded.usable)
                self.assertEqual(loaded.snapshot.closed_at, data["work_session"]["updated_at"])

                with redirect_stdout(StringIO()) as resume_stdout:
                    self.assertEqual(main(["work", "1", "--session", "--resume", "--json"]), 0)
                resume_data = json.loads(resume_stdout.getvalue())
                self.assertEqual(resume_data["snapshot"]["status"], "usable")
                self.assertEqual(resume_data["snapshot"]["path"], data["snapshot_path"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
