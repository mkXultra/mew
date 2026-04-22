import os
import tempfile
from pathlib import Path
import unittest

from mew.patch_draft import compile_patch_draft
from mew.work_loop import _write_ready_patch_draft_environment


class WorkLoopPatchDraftCanonicalizationTests(unittest.TestCase):
    def _build_write_ready_context(self, active_todo_target_paths):
        return {
            "work_session": {
                "resume": {
                    "active_work_todo": {
                        "id": "todo-402-1",
                        "source": {"target_paths": list(active_todo_target_paths)},
                    },
                },
            },
        }

    def test_write_ready_patch_draft_environment_canonicalizes_missing_leading_slash_cwd_paths(self):
        repo_root = Path.cwd().resolve()
        absolute_source_path = repo_root / "src/mew/dogfood.py"
        malformed_absolute_source_path = str(absolute_source_path).lstrip("/")
        write_ready_fast_path = {
            "recent_windows": [
                {
                    "path": malformed_absolute_source_path,
                    "line_start": 1,
                    "line_end": 1,
                    "text": "import json\n",
                    "context_truncated": False,
                }
            ]
        }
        context = self._build_write_ready_context(["src/mew/dogfood.py"])

        environment = _write_ready_patch_draft_environment(
            session={},
            context=context,
            write_ready_fast_path=write_ready_fast_path,
        )

        self.assertEqual(list(environment["cached_windows"].keys()), ["src/mew/dogfood.py"])
        self.assertEqual(environment["todo"]["source"]["target_paths"], ["src/mew/dogfood.py"])

    def test_write_ready_patch_draft_compiler_uses_canonicalized_window_path_keys(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmpdir:
            draft_root = Path(tmpdir)
            draft_target = draft_root / "work_loop_patch_draft.txt"
            draft_target.write_text("alpha=1\n", encoding="utf-8")
            relative_target = draft_target.relative_to(Path.cwd()).as_posix()

            write_ready_fast_path = {
                "recent_windows": [
                    {
                        "path": str(draft_target).lstrip("/"),
                        "line_start": 1,
                        "line_end": 1,
                        "text": "alpha=1\n",
                        "context_truncated": False,
                    }
                ],
            }
            context = self._build_write_ready_context([relative_target])
            environment = _write_ready_patch_draft_environment(
                session={},
                context=context,
                write_ready_fast_path=write_ready_fast_path,
            )
            proposal = {
                "kind": "patch_proposal",
                "summary": "normalize window path canonicalization",
                "files": [
                    {
                        "path": relative_target,
                        "edits": [{"old": "alpha=1\n", "new": "alpha=2\n"}],
                    }
                ],
            }

            validator_result = compile_patch_draft(
                todo=environment["todo"],
                proposal=proposal,
                cached_windows=environment["cached_windows"],
                live_files=environment["live_files"],
                allowed_write_roots=["."],
            )

            self.assertEqual(validator_result.get("kind"), "patch_draft")
            self.assertNotEqual(
                validator_result.get("code"),
                "missing_exact_cached_window_texts",
            )

    def test_compile_patch_draft_with_paired_malformed_cwd_rooted_absolute_window_paths(self):
        old_cwd = os.getcwd()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmpdir:
            os.chdir(tmpdir)
            try:
                source_path = Path("src/mew/dogfood.py")
                test_path = Path("tests/test_dogfood.py")
                source_path.parent.mkdir(parents=True, exist_ok=True)
                test_path.parent.mkdir(parents=True, exist_ok=True)
                source_text = "PAIR_REGRESSION_SOURCE = 1\n"
                test_text = "PAIR_REGRESSION_TEST = 1\n"
                source_path.write_text(source_text, encoding="utf-8")
                test_path.write_text(test_text, encoding="utf-8")

                cwd = Path.cwd().resolve()
                write_ready_fast_path = {
                    "recent_windows": [
                        {
                            "path": str(cwd / str(source_path)).lstrip("/"),
                            "line_start": 1,
                            "line_end": 1,
                            "text": source_text,
                            "context_truncated": False,
                        },
                        {
                            "path": str(cwd / str(test_path)).lstrip("/"),
                            "line_start": 1,
                            "line_end": 1,
                            "text": test_text,
                            "context_truncated": False,
                        },
                    ],
                }
                context = self._build_write_ready_context(["src/mew/dogfood.py", "tests/test_dogfood.py"])
                environment = _write_ready_patch_draft_environment(
                    session={},
                    context=context,
                    write_ready_fast_path=write_ready_fast_path,
                )
                proposal = {
                    "kind": "patch_proposal",
                    "summary": "paired malformed recent-window path regression",
                    "files": [
                        {
                            "path": "src/mew/dogfood.py",
                            "edits": [{"old": source_text, "new": "PAIR_REGRESSION_SOURCE = 2\n"}],
                        },
                        {
                            "path": "tests/test_dogfood.py",
                            "edits": [{"old": test_text, "new": "PAIR_REGRESSION_TEST = 2\n"}],
                        },
                    ],
                }

                validator_result = compile_patch_draft(
                    todo=environment["todo"],
                    proposal=proposal,
                    cached_windows=environment["cached_windows"],
                    live_files=environment["live_files"],
                    allowed_write_roots=["."],
                )
            finally:
                os.chdir(old_cwd)

        self.assertEqual(validator_result.get("kind"), "patch_draft")
        self.assertNotEqual(validator_result.get("code"), "missing_exact_cached_window_texts")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
