import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

from mew.cli import main
from mew.state import load_state, save_state, state_lock
from mew.work_session import build_work_session_resume, format_work_session_resume


class WorkRejectionFrontierTests(unittest.TestCase):
    def test_reject_tool_records_structured_frontier_and_resume_next_action(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "add", "Reject generic cleanup", "--kind", "coding", "--json"]), 0)
                task_id = str(json.loads(stdout.getvalue())["task"]["id"])
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", task_id, "--start-session"]), 0)
                with state_lock():
                    state = load_state()
                    session = state["work_sessions"][0]
                    session["tool_calls"].append(
                        {
                            "id": 1,
                            "tool": "edit_file",
                            "status": "completed",
                            "parameters": {"path": "README.md"},
                            "result": {
                                "dry_run": True,
                                "changed": True,
                                "diff_preview": "- old\n+ generic cleanup substitution\n",
                            },
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                task_id,
                                "--reject-tool",
                                "1",
                                "--reject-reason",
                                "generic cleanup substitution unrelated to the active criterion",
                                "--json",
                            ]
                        ),
                        0,
                    )
                rejected = json.loads(stdout.getvalue())
                frontier = rejected["rejection_frontier"]
                self.assertEqual(frontier["drift_class"], "generic_cleanup_substitution")
                self.assertEqual(frontier["rejected_patch_family"], "generic_cleanup")
                self.assertIn("block generic cleanup", frontier["stop_rule"])
                self.assertEqual(rejected["rejected_tool_call"]["rejection_frontier_id"], frontier["id"])

                state = load_state()
                session = state["work_sessions"][0]
                resume = build_work_session_resume(session, task=state["tasks"][0], state=state)
                self.assertEqual(resume["active_rejection_frontier"]["id"], frontier["id"])
                resume_text = format_work_session_resume(resume)
                self.assertIn("active_rejection_frontier:", resume_text)
                self.assertIn("rejection_next_action:", resume_text)
            finally:
                os.chdir(old_cwd)

    def test_reject_tool_classifies_unpaired_source_edit_frontier(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(main(["task", "add", "Reject unpaired source", "--kind", "coding", "--json"]), 0)
                task_id = str(json.loads(stdout.getvalue())["task"]["id"])
                with redirect_stdout(StringIO()):
                    self.assertEqual(main(["work", task_id, "--start-session"]), 0)
                with state_lock():
                    state = load_state()
                    state["work_sessions"][0]["tool_calls"].append(
                        {
                            "id": 7,
                            "tool": "edit_file",
                            "status": "completed",
                            "parameters": {"path": "src/mew/work_session.py"},
                            "result": {"dry_run": True, "changed": True, "diff_preview": "- old\n+ new\n"},
                        }
                    )
                    save_state(state)

                with redirect_stdout(StringIO()) as stdout:
                    self.assertEqual(
                        main(
                            [
                                "work",
                                task_id,
                                "--reject-tool",
                                "7",
                                "--reject-reason",
                                "unpaired source edit",
                                "--json",
                            ]
                        ),
                        0,
                    )
                frontier = json.loads(stdout.getvalue())["rejection_frontier"]
                self.assertEqual(frontier["drift_class"], "unpaired_source_edit")
                self.assertEqual(frontier["rejected_patch_family"], "unpaired_source_edit")
                self.assertIn("paired tests/**", frontier["stop_rule"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
