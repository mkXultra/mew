import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mew.patch_draft import compile_patch_draft
from mew.proof_summary import summarize_m6_11_replay_calibration
from mew.work_loop import (
    _compile_write_ready_patch_draft_proposal,
    _work_write_ready_fast_path_details,
    _work_write_ready_fast_path_state,
    _write_ready_tiny_draft_observation_target_paths,
)
from mew.work_replay import (
    REPLAYS_ROOT,
    PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON,
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

    @staticmethod
    def _build_write_ready_replay_context(
        scenario,
        *,
        session_id=438,
        observation_paths=None,
    ):
        target_paths = list((scenario.get("todo") or {}).get("source", {}).get("target_paths") or [])
        observation_target_paths = (
            list(observation_paths) if observation_paths is not None else list(target_paths)
        )
        cached_windows = scenario.get("cached_windows") or {}
        observation_windows = []
        recent_read_file_windows = []
        for index, path in enumerate(target_paths, start=11):
            window = dict(cached_windows.get(path) or {})
            recent_read_file_windows.append(
                {
                    "tool_call_id": index,
                    "path": path,
                    "line_start": window.get("line_start"),
                    "line_end": window.get("line_end"),
                    "text": window.get("text") or "",
                    "context_truncated": bool(window.get("context_truncated")),
                    "window_sha256": window.get("window_sha256"),
                    "file_sha256": window.get("file_sha256"),
                }
            )
            if path not in observation_target_paths:
                continue
            observation_windows.append(
                {
                    "path": path,
                    "line_start": window.get("line_start"),
                    "line_end": window.get("line_end"),
                }
            )

        plan_item = "Draft one paired dry-run edit batch for " + " and ".join(target_paths)
        return {
            "task": {
                "id": session_id,
                "title": "Write-ready replay harness",
                "description": "Deterministically exercise the write-ready fast-path replay seam.",
                "status": "todo",
                "kind": "coding",
            },
            "work_session": {
                "id": session_id,
                "status": "active",
                "resume": {
                    "active_work_todo": {
                        "id": (scenario.get("todo") or {}).get("id") or f"todo-{session_id}",
                        "status": "drafting",
                        "source": {
                            "plan_item": plan_item,
                            "target_paths": target_paths,
                            "verify_command": "uv run python -m unittest tests.test_patch_draft",
                        },
                        "attempts": {"draft": 0, "review": 0},
                    },
                    "plan_item_observations": [
                        {
                            "plan_item": plan_item,
                            "target_path": observation_target_paths[0] if observation_target_paths else "",
                            "edit_ready": True,
                            "cached_windows": observation_windows,
                        }
                    ],
                    "target_path_cached_window_observations": [
                        {"path": path} for path in target_paths
                    ],
                    "recent_decisions": [],
                    "notes": [],
                },
                "recent_read_file_windows": recent_read_file_windows,
            },
            "capabilities": {
                "allowed_write_roots": list(scenario.get("allowed_write_roots") or ["."]),
            },
            "guidance": "Draft one paired dry-run edit using the exact cached windows.",
        }

    @staticmethod
    def _materialize_live_files(scenario):
        for path, payload in (scenario.get("live_files") or {}).items():
            file_path = Path(path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text((payload or {}).get("text") or "", encoding="utf-8")

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

    def test_write_patch_draft_compiler_replay_auto_non_native_blocker_is_not_counted(self):
        session_id = "s-10a"
        todo_id = "todo-10-1"
        todo = {"id": todo_id}
        proposal = {
            "kind": "patch_blocker",
            "code": "insufficient_cached_window_text",
            "detail": "model-authored pass-through blocker",
        }
        validator_result = proposal.copy()
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
                self.assertFalse(metadata["calibration_counted"])
                self.assertEqual(
                    metadata["calibration_exclusion_reason"],
                    PATCH_DRAFT_COMPILER_PASSTHROUGH_NON_NATIVE_EXCLUSION_REASON,
                )
                self.assertEqual(metadata["blocker_code"], "insufficient_cached_window_text")
            finally:
                os.chdir(old_cwd)

    def test_write_patch_draft_compiler_replay_retains_counted_native_blocker(self):
        session_id = "s-10b"
        todo_id = "todo-10-2"
        todo = {"id": todo_id}
        proposal = {"kind": "patch_blocker", "code": "missing_exact_cached_window_texts"}
        validator_result = proposal.copy()
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
                self.assertTrue(metadata["calibration_counted"])
                self.assertEqual(metadata["calibration_exclusion_reason"], "")
                self.assertEqual(
                    metadata["blocker_code"],
                    "missing_exact_cached_window_texts",
                )
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

    def test_write_ready_fast_path_emits_counted_bundle_from_synthesized_resume(self):
        scenario = self._load_fixture_scenario("paired_src_test_happy")
        target_paths = list((scenario.get("todo") or {}).get("source", {}).get("target_paths") or [])
        context = self._build_write_ready_replay_context(scenario, session_id=438)

        with tempfile.TemporaryDirectory() as tmp:
            old_cwd = os.getcwd()
            os.chdir(tmp)
            try:
                self._materialize_live_files(scenario)

                with patch("mew.work_replay.now_date_iso", return_value="2026-04-23"):
                    with patch("mew.work_replay.now_iso", return_value="2026-04-23T10:00:00Z"):
                        with patch("mew.work_replay._current_git_head", return_value="HEAD-438"):
                            with patch("mew.proof_summary._current_git_head", return_value="HEAD-438"):
                                fast_path = _work_write_ready_fast_path_state(context)
                                details = _work_write_ready_fast_path_details(context)
                                replay = _compile_write_ready_patch_draft_proposal(
                                    session={
                                        "id": context["work_session"]["id"],
                                        "active_work_todo": context["work_session"]["resume"]["active_work_todo"],
                                    },
                                    context=context,
                                    proposal=scenario["model_output"],
                                    write_ready_fast_path=details,
                                    allowed_write_roots=scenario["allowed_write_roots"],
                                )
                                calibration = summarize_m6_11_replay_calibration(
                                    Path(tmp) / REPLAYS_ROOT
                                )["calibration"]

                self.assertTrue(fast_path["active"])
                self.assertEqual(fast_path["reason"], "paired_cached_windows_edit_ready")
                self.assertEqual(fast_path["activation_source"], "plan_item_observations")
                self.assertTrue(details["active"])
                self.assertEqual(
                    [item["path"] for item in details["recent_windows"]],
                    target_paths,
                )
                self.assertEqual(
                    _write_ready_tiny_draft_observation_target_paths(
                        context["work_session"]["resume"]
                    ),
                    target_paths,
                )

                observation = replay["observation"]
                validator_result = replay["validator_result"]
                self.assertTrue(observation["patch_draft_compiler_ran"])
                self.assertEqual(observation["patch_draft_compiler_artifact_kind"], "patch_draft")
                self.assertTrue(observation["patch_draft_compiler_replay_path"])
                self.assertEqual(validator_result["kind"], "patch_draft")
                self.assertEqual(validator_result["status"], "validated")

                metadata_path = Path(observation["patch_draft_compiler_replay_path"])
                self.assertTrue(metadata_path.is_file())
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                self.assertEqual(metadata["bundle"], "patch_draft_compiler")
                self.assertTrue(metadata["calibration_counted"])
                self.assertEqual(metadata["git_head"], "HEAD-438")

                current_head = calibration["cohorts"]["current_head"]
                self.assertEqual(calibration["total_bundles"], 1)
                self.assertEqual(current_head["total_bundles"], 1)
                self.assertEqual(current_head["compiler_bundles"], 1)
                self.assertEqual(
                    current_head["bundle_type_counts"],
                    {"patch_draft_compiler.other": 1},
                )
                self.assertEqual(current_head["malformed_relevant_bundle_count"], 0)
            finally:
                os.chdir(old_cwd)

    def test_write_ready_tiny_draft_target_paths_fall_back_to_active_work_todo_pair(self):
        scenario = self._load_fixture_scenario("paired_src_test_happy")
        target_paths = list((scenario.get("todo") or {}).get("source", {}).get("target_paths") or [])
        resume = self._build_write_ready_replay_context(
            scenario,
            observation_paths=target_paths[:1],
        )["work_session"]["resume"]

        self.assertEqual(
            _write_ready_tiny_draft_observation_target_paths(resume),
            target_paths,
        )


if __name__ == "__main__":
    unittest.main()
