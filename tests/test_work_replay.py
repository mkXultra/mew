import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.patch_draft import compile_patch_draft
from mew.work_replay import (
    REPLAYS_ROOT,
    mark_patch_draft_compiler_replay_non_counted,
    write_work_model_failure_replay,
    write_patch_draft_compiler_replay,
)


class PatchDraftCompilerReplayTests(unittest.TestCase):
    FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "work_loop" / "patch_draft"

    @staticmethod
    def _load_fixture_scenario(name):
        with (PatchDraftCompilerReplayTests.FIXTURE_DIR / name / "scenario.json").open(
            encoding="utf-8",
        ) as fp:
            return json.load(fp)

    def test_patch_draft_compiler_replay_path_shape_and_attempt_increment(self):
        session_id = 3
        todo_id = "todo-3-2"
        todo = {"id": todo_id}
        proposal = {"kind": "patch_request"}
        validator_result = {"kind": "patch_draft", "status": "validated"}
        cached_windows = {}
        live_files = {}
        allowed_write_roots = ["."]

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        first = write_patch_draft_compiler_replay(
                            session_id=session_id,
                            todo_id=todo_id,
                            todo=todo,
                            proposal=proposal,
                            cached_windows=cached_windows,
                            live_files=live_files,
                            allowed_write_roots=allowed_write_roots,
                            validator_result=validator_result,
                        )
                        second = write_patch_draft_compiler_replay(
                            session_id=session_id,
                            todo_id=todo_id,
                            todo=todo,
                            proposal=proposal,
                            cached_windows=cached_windows,
                            live_files=live_files,
                            allowed_write_roots=allowed_write_roots,
                            validator_result=validator_result,
                        )

                self.assertTrue(first)
                self.assertTrue(second)
                self.assertNotEqual(first, second)

                first_path = Path(first)
                second_path = Path(second)
                self.assertIn("2026-04-22", str(first_path))
                self.assertIn("2026-04-22", str(second_path))
                self.assertIn(f"session-{session_id}", first_path.parts)
                self.assertIn(f"todo-{todo_id}", first_path.parts)
                self.assertIn("attempt-1", str(first_path))
                self.assertIn("attempt-2", str(second_path))

                self.assertEqual(first_path.name, "replay_metadata.json")
                self.assertEqual(first_path.parent.name, "attempt-1")
                self.assertEqual(second_path.parent.name, "attempt-2")
            finally:
                os.chdir(old_cwd)

    def test_patch_draft_compiler_replay_writes_expected_payload_files(self):
        session_id = "s-9"
        todo_id = "todo-9-1"
        todo = {"id": todo_id, "source": {"target_paths": ["src/mew/patch_draft.py"]}}
        proposal = {"kind": "patch_request", "payload": "value"}
        validator_result = {"kind": "patch_blocker", "code": "write_policy_violation"}
        cached_windows = {"src/mew/patch_draft.py": {"path": "src/mew/patch_draft.py", "text": "before", "line_start": 1, "line_end": 1}}
        live_files = {"src/mew/patch_draft.py": {"text": "before", "sha256": "abc123"}}
        allowed_write_roots = ["."]

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        metadata_path = write_patch_draft_compiler_replay(
                            session_id=session_id,
                            todo_id=todo_id,
                            todo=todo,
                            proposal=proposal,
                            cached_windows=cached_windows,
                            live_files=live_files,
                            allowed_write_roots=allowed_write_roots,
                            validator_result=validator_result,
                        )

                self.assertTrue(metadata_path)
                base_dir = Path(metadata_path).parent
                self.assertEqual(json.loads((base_dir / "todo.json").read_text(encoding="utf-8")), todo)
                self.assertEqual(
                    json.loads((base_dir / "proposal.json").read_text(encoding="utf-8")),
                    proposal,
                )
                self.assertEqual(
                    json.loads((base_dir / "validator_result.json").read_text(encoding="utf-8")),
                    validator_result,
                )
                self.assertEqual(
                    json.loads((base_dir / "cached_windows.json").read_text(encoding="utf-8")),
                    cached_windows,
                )
                self.assertEqual(
                    json.loads((base_dir / "live_files.json").read_text(encoding="utf-8")),
                    live_files,
                )
                self.assertEqual(
                    json.loads((base_dir / "allowed_write_roots.json").read_text(encoding="utf-8")),
                    allowed_write_roots,
                )

                metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
                self.assertEqual(metadata["schema_version"], 1)
                self.assertEqual(metadata["bundle"], "patch_draft_compiler")
                self.assertEqual(metadata["session_id"], str(session_id))
                self.assertEqual(metadata["todo_id"], todo_id)
                self.assertTrue(metadata["calibration_counted"])
                self.assertEqual(metadata["calibration_exclusion_reason"], "")
                self.assertEqual(metadata["attempt"], 1)
                self.assertEqual(metadata["captured_at"], "2026-04-22T10:00:00Z")
                self.assertEqual(metadata["files"]["todo"], "todo.json")
                self.assertEqual(metadata["files"]["proposal"], "proposal.json")
                self.assertEqual(metadata["files"]["cached_windows"], "cached_windows.json")
                self.assertEqual(metadata["files"]["live_files"], "live_files.json")
                self.assertEqual(metadata["files"]["allowed_write_roots"], "allowed_write_roots.json")
                self.assertEqual(metadata["files"]["validator_result"], "validator_result.json")
            finally:
                os.chdir(old_cwd)

    def test_mark_patch_draft_compiler_replay_non_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                metadata_path = Path(tmp) / "replay_metadata.json"
                metadata_path.write_text(
                    json.dumps(
                        {
                            "schema_version": 1,
                            "bundle": "patch_draft_compiler",
                            "calibration_counted": True,
                            "calibration_exclusion_reason": "",
                            "files": {"validator_result": "validator_result.json"},
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                Path(tmp, "validator_result.json").write_text(
                    json.dumps({"kind": "patch_draft", "status": "validated"}),
                    encoding="utf-8",
                )

                updated = mark_patch_draft_compiler_replay_non_counted(
                    metadata_path,
                    reason="reviewer rejected",
                )
                self.assertTrue(updated)
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertFalse(metadata["calibration_counted"])
                self.assertEqual(metadata["calibration_exclusion_reason"], "reviewer rejected")
            finally:
                os.chdir(old_cwd)

    def test_write_work_model_failure_replay_persists_cohort_fields(self):
        session = {
            "id": 13,
            "active_work_todo": {"id": "todo-13"},
        }
        model_turn = {
            "id": 77,
            "summary": "model failed during tiny preview",
            "model_metrics": {
                "write_ready_fast_path": True,
                "draft_prompt_contract_version": "v3",
                "tiny_write_ready_draft_prompt_contract_version": "v4",
                "tiny_write_ready_draft_exit_stage": "compiler_fallback",
                "tiny_write_ready_draft_fallback_reason": "timeout",
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        with patch(
                            "mew.work_replay._current_git_head",
                            return_value="1111111111111111111111111111111111111111",
                        ):
                            report_path = write_work_model_failure_replay(
                                session=session,
                                model_turn=model_turn,
                                exc=RuntimeError("timeout"),
                            )

                self.assertTrue(report_path)
                report = json.loads(Path(report_path).read_text(encoding="utf-8"))
                self.assertEqual(
                    report["git_head"],
                    "1111111111111111111111111111111111111111",
                )
                self.assertEqual(
                    report["bucket_tag"],
                    "contract=v3/tiny=v4/exit=compiler_fallback",
                )
                self.assertEqual(report["blocker_code"], "timeout")
            finally:
                os.chdir(old_cwd)

    def test_write_patch_draft_compiler_replay_persists_cohort_fields(self):
        session_id = "s-11"
        todo_id = "todo-11-1"
        todo = {
            "id": todo_id,
            "draft_prompt_contract_version": "v3",
            "tiny_write_ready_draft_prompt_contract_version": "v4",
        }
        proposal = {"kind": "patch_request"}
        validator_result = {"kind": "patch_draft", "code": "patch_blocker"}
        cached_windows = {}
        live_files = {}
        allowed_write_roots = ["."]

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        with patch(
                            "mew.work_replay._current_git_head",
                            return_value="2222222222222222222222222222222222222222",
                        ):
                            metadata_path = write_patch_draft_compiler_replay(
                                session_id=session_id,
                                todo_id=todo_id,
                                todo=todo,
                                proposal=proposal,
                                cached_windows=cached_windows,
                                live_files=live_files,
                                allowed_write_roots=allowed_write_roots,
                                validator_result=validator_result,
                            )

                self.assertTrue(metadata_path)
                metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
                self.assertEqual(metadata["git_head"], "2222222222222222222222222222222222222222")
                self.assertEqual(
                    metadata["bucket_tag"],
                    "code=patch_blocker/contract=v3/tiny=v4",
                )
                self.assertEqual(metadata["blocker_code"], "patch_blocker")
            finally:
                os.chdir(old_cwd)

    def test_write_work_model_failure_replay_non_git_head_fallback(self):
        session = {
            "id": 14,
            "active_work_todo": {"id": "todo-14"},
        }
        model_turn = {
            "id": 88,
            "summary": "model failed with non-git fallback",
            "model_metrics": {
                "write_ready_fast_path": True,
            },
        }

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        with patch(
                            "mew.work_replay.subprocess.run",
                            side_effect=OSError("not a git repo"),
                        ):
                            report_path = write_work_model_failure_replay(
                                session=session,
                                model_turn=model_turn,
                                exc=RuntimeError("timeout"),
                            )

                self.assertTrue(report_path)
                report = json.loads(Path(report_path).read_text(encoding="utf-8"))
                self.assertEqual(report["git_head"], "")
            finally:
                os.chdir(old_cwd)

    def test_write_patch_draft_compiler_replay_bucket_tag_without_contracts_is_code_only(self):
        session_id = "s-12"
        todo_id = "todo-12-1"
        todo = {
            "id": todo_id,
        }
        proposal = {"kind": "patch_request"}
        validator_result = {"kind": "patch_draft", "code": "patch_blocker"}
        cached_windows = {}
        live_files = {}
        allowed_write_roots = ["."]

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        metadata_path = write_patch_draft_compiler_replay(
                            session_id=session_id,
                            todo_id=todo_id,
                            todo=todo,
                            proposal=proposal,
                            cached_windows=cached_windows,
                            live_files=live_files,
                            allowed_write_roots=allowed_write_roots,
                            validator_result=validator_result,
                        )

                self.assertTrue(metadata_path)
                metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
                self.assertEqual(metadata["bucket_tag"], "code=patch_blocker")

            finally:
                os.chdir(old_cwd)

    def test_write_patch_draft_compiler_replay_non_git_head_fallback(self):
        session_id = "s-13"
        todo_id = "todo-13-1"
        todo = {"id": todo_id}
        proposal = {"kind": "patch_request"}
        validator_result = {"kind": "patch_draft", "code": "patch_blocker"}
        cached_windows = {}
        live_files = {}
        allowed_write_roots = ["."]

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                with patch("mew.work_replay.now_date_iso", return_value="2026-04-22"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-22T10:00:00Z"):
                        with patch(
                            "mew.work_replay.subprocess.run",
                            side_effect=OSError("not a git repo"),
                        ):
                            metadata_path = write_patch_draft_compiler_replay(
                                session_id=session_id,
                                todo_id=todo_id,
                                todo=todo,
                                proposal=proposal,
                                cached_windows=cached_windows,
                                live_files=live_files,
                                allowed_write_roots=allowed_write_roots,
                                validator_result=validator_result,
                            )

                self.assertTrue(metadata_path)
                metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
                self.assertEqual(metadata["git_head"], "")
            finally:
                os.chdir(old_cwd)

    def test_patch_draft_compiler_replay_missing_session_or_todo_id_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertIsNone(
                    write_patch_draft_compiler_replay(
                        session_id=None,
                        todo_id="todo-1",
                        todo={},
                        proposal={},
                        cached_windows={},
                        live_files={},
                        allowed_write_roots=["."],
                        validator_result={},
                    )
                )
                self.assertIsNone(
                    write_patch_draft_compiler_replay(
                        session_id="1",
                        todo_id="   ",
                        todo={},
                        proposal={},
                        cached_windows={},
                        live_files={},
                        allowed_write_roots=["."],
                        validator_result={},
                    )
                )
                self.assertFalse((Path(tmp) / REPLAYS_ROOT).exists())
            finally:
                os.chdir(old_cwd)

    def test_patch_draft_compiler_replay_invalid_required_payload_is_noop(self):
        todo = {"id": "todo-1"}
        cached_windows = {}
        live_files = {}
        validator_result = {"kind": "patch_draft", "status": "validated"}

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self.assertIsNone(
                    write_patch_draft_compiler_replay(
                        session_id=1,
                        todo_id="todo-1",
                        todo=todo,
                        proposal=[],
                        cached_windows=cached_windows,
                        live_files=live_files,
                        allowed_write_roots=["."],
                        validator_result=validator_result,
                    )
                )
                self.assertFalse((Path(tmp) / REPLAYS_ROOT).exists())
            finally:
                os.chdir(old_cwd)

    def test_patch_draft_compiler_replay_sanitizes_path_components(self):
        session_id = "session/1"
        todo_id = "todo/9/1"
        todo = {"id": todo_id}
        proposal = {"kind": "patch_request"}
        cached_windows = {}
        live_files = {}
        validator_result = {"kind": "patch_draft", "status": "validated"}

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                metadata_path = write_patch_draft_compiler_replay(
                    session_id=session_id,
                    todo_id=todo_id,
                    todo=todo,
                    proposal=proposal,
                    cached_windows=cached_windows,
                    live_files=live_files,
                    allowed_write_roots=["."],
                    validator_result=validator_result,
                )

                self.assertTrue(metadata_path)
                attempt_dir = Path(metadata_path).parent
                self.assertEqual(attempt_dir.parent.parent.name, "session-session-1")
                self.assertEqual(attempt_dir.parent.name, "todo-todo-9-1")
                self.assertNotIn("todo/9/1", str(metadata_path))
            finally:
                os.chdir(old_cwd)

    def test_patch_draft_compiler_replay_roundtrip_matches_compile_patch_draft(self):
        scenario = self._load_fixture_scenario("paired_src_test_happy")

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                metadata_path = write_patch_draft_compiler_replay(
                    session_id="session-17",
                    todo_id=scenario["todo"]["id"],
                    todo=scenario["todo"],
                    proposal=scenario["model_output"],
                    cached_windows=scenario["cached_windows"],
                    live_files=scenario["live_files"],
                    allowed_write_roots=scenario["allowed_write_roots"],
                    validator_result=scenario["expected"],
                )
                self.assertTrue(metadata_path)
                base_dir = Path(metadata_path).parent
                payload = {
                    "todo": json.loads((base_dir / "todo.json").read_text(encoding="utf-8")),
                    "proposal": json.loads((base_dir / "proposal.json").read_text(encoding="utf-8")),
                    "cached_windows": json.loads((base_dir / "cached_windows.json").read_text(encoding="utf-8")),
                    "live_files": json.loads((base_dir / "live_files.json").read_text(encoding="utf-8")),
                    "allowed_write_roots": json.loads((base_dir / "allowed_write_roots.json").read_text(encoding="utf-8")),
                    "validator_result": json.loads((base_dir / "validator_result.json").read_text(encoding="utf-8")),
                }

                artifact = compile_patch_draft(
                    todo=payload["todo"],
                    proposal=payload["proposal"],
                    cached_windows=payload["cached_windows"],
                    live_files=payload["live_files"],
                    allowed_write_roots=payload["allowed_write_roots"],
                )

                self.assertEqual(artifact["kind"], scenario["expected"]["kind"])
                self.assertEqual(artifact["status"], scenario["expected"]["status"])
                self.assertEqual(payload["validator_result"], scenario["expected"])
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
