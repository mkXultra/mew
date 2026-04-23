import unittest
import json
from pathlib import Path

from mew.patch_draft import (
    PATCH_BLOCKER_RECOVERY_ACTIONS,
    compile_patch_draft,
    compile_patch_draft_previews,
    sha256_text,
)


def _todo(*paths):
    return {
        "id": "todo-17",
        "source": {
            "target_paths": list(paths),
        },
    }


def _window(path, text, *, line_start=1, line_end=20, file_text=None, context_truncated=False):
    source_text = text if file_text is None else file_text
    return {
        "path": path,
        "line_start": line_start,
        "line_end": line_end,
        "text": text,
        "context_truncated": context_truncated,
        "window_sha256": sha256_text(text),
        "file_sha256": sha256_text(source_text),
    }


def _live_file(text, *, sha256=None):
    return {
        "text": text,
        "sha256": sha256 or sha256_text(text),
    }


ALLOWED_WRITE_ROOTS = ["."]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "work_loop" / "patch_draft"


def _load_fixture(name):
    path = FIXTURE_DIR / name / "scenario.json"
    with path.open("r", encoding="utf-8") as fp:
        return json.load(fp)


def _hydrate_fixture_payload(payload):
    for raw_window in (payload.get("cached_windows") or {}).values():
        if not isinstance(raw_window, dict):
            continue
        text = raw_window.get("text")
        if "window_sha256" not in raw_window and isinstance(text, str):
            raw_window["window_sha256"] = sha256_text(text)
        if "file_sha256" not in raw_window and isinstance(text, str):
            raw_window["file_sha256"] = sha256_text(text)

    for raw_live in (payload.get("live_files") or {}).values():
        if not isinstance(raw_live, dict):
            continue
        text = raw_live.get("text")
        if "sha256" not in raw_live and isinstance(text, str):
            raw_live["sha256"] = sha256_text(text)

    return payload


def _run_fixture_case(case_name):
    scenario = _hydrate_fixture_payload(_load_fixture(case_name))

    artifact = compile_patch_draft(
        todo=scenario["todo"],
        proposal=scenario["model_output"],
        cached_windows=scenario["cached_windows"],
        live_files=scenario["live_files"],
        allowed_write_roots=scenario.get("allowed_write_roots", ALLOWED_WRITE_ROOTS),
    )

    return scenario, artifact


def _run_fixture_preview_case(case_name):
    scenario, artifact = _run_fixture_case(case_name)
    return scenario, artifact, compile_patch_draft_previews(
        artifact,
        allowed_write_roots=scenario.get("allowed_write_roots", ALLOWED_WRITE_ROOTS),
    )


def _assert_fixture_expectation(test_case, scenario, artifact):
    expected = scenario["expected"]
    test_case.assertEqual(artifact["kind"], expected["kind"])

    if expected["kind"] == "patch_draft":
        test_case.assertEqual(artifact["status"], expected.get("status"))
        test_case.assertEqual(artifact["todo_id"], expected.get("todo_id", scenario["todo"].get("id")))
        if "file_count" in expected:
            test_case.assertEqual(len(artifact["files"]), expected["file_count"])
        if "file_kinds" in expected:
            test_case.assertEqual([item["kind"] for item in artifact["files"]], expected["file_kinds"])
        for fragment in expected.get("diff_contains", []):
            test_case.assertIn(fragment, artifact["unified_diff"])
        return

    test_case.assertEqual(artifact["code"], expected["code"])
    if "detail_contains" in expected:
        test_case.assertIn(expected["detail_contains"], artifact["detail"])
    if "path" in expected:
        test_case.assertEqual(artifact["path"], expected["path"])


class PatchDraftFixtureTests(unittest.TestCase):
    def test_compile_patch_draft_fixture_paired_src_test_happy(self):
        scenario, artifact = _run_fixture_case("paired_src_test_happy")
        _assert_fixture_expectation(self, scenario, artifact)

    def test_compile_patch_draft_fixture_ambiguous_old_text_match(self):
        scenario, artifact = _run_fixture_case("ambiguous_old_text_match")
        _assert_fixture_expectation(self, scenario, artifact)

    def test_compile_patch_draft_fixture_stale_cached_window_text(self):
        scenario, artifact = _run_fixture_case("stale_cached_window_text")
        _assert_fixture_expectation(self, scenario, artifact)


class PatchDraftTranslatorFixtureTests(unittest.TestCase):
    def test_compile_patch_draft_previews_from_fixture_happy_path(self):
        scenario, artifact, preview = _run_fixture_preview_case("paired_src_test_happy")
        self.assertEqual(artifact["kind"], "patch_draft")
        self.assertEqual(artifact["status"], "validated")
        self.assertEqual(artifact["todo_id"], scenario["todo"]["id"])

        self.assertEqual(len(preview), 2)
        self.assertEqual(preview[0]["type"], "edit_file")
        self.assertEqual(preview[1]["type"], "edit_file")
        self.assertEqual(preview[0]["path"], "src/mew/patch_draft.py")
        self.assertEqual(preview[1]["path"], "tests/test_patch_draft.py")
        self.assertEqual(preview[0]["path"], scenario["todo"]["source"]["target_paths"][0])
        self.assertEqual(preview[1]["path"], scenario["todo"]["source"]["target_paths"][1])
        self.assertEqual(preview[0]["old"], "return 41")
        self.assertEqual(preview[1]["new"], "meaning(), 42")
        self.assertTrue(preview[0]["dry_run"])
        self.assertTrue(preview[1]["dry_run"])
        self.assertFalse(preview[0]["apply"])
        self.assertFalse(preview[1]["apply"])

    def test_compile_patch_draft_previews_blocker_passthrough(self):
        blocker = {
            "kind": "patch_blocker",
            "todo_id": "todo-17",
            "code": "stale_cached_window_text",
            "detail": "cached window no longer matches live",
            "recovery_action": "refresh_cached_window",
        }

        preview = compile_patch_draft_previews(
            blocker,
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(preview, blocker)

    def test_compile_patch_draft_previews_rejects_invalid_draft(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {"kind": "edit_file", "path": "src/mew/patch_draft.py", "edits": "bad"},
            ],
        }

        preview = compile_patch_draft_previews(
            artifact,
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(preview["kind"], "patch_blocker")
        self.assertEqual(preview["code"], "model_returned_non_schema")

    def test_compile_patch_draft_previews_requires_allowed_write_roots(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {
                    "kind": "edit_file",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 42"}],
                }
            ],
        }

        preview = compile_patch_draft_previews(
            artifact,
            allowed_write_roots=[],
        )

        self.assertEqual(preview["kind"], "patch_blocker")
        self.assertEqual(preview["code"], "write_policy_violation")
        self.assertIn("allowed_write_roots is required", preview["detail"])

    def test_compile_patch_draft_previews_rejects_path_outside_allowed_roots(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {
                    "kind": "edit_file_hunks",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 42"}],
                }
            ],
        }

        preview = compile_patch_draft_previews(
            artifact,
            allowed_write_roots=["/tmp/forbidden-root"],
        )

        self.assertEqual(preview["kind"], "patch_blocker")
        self.assertEqual(preview["code"], "write_policy_violation")
        self.assertEqual(preview["path"], "src/mew/patch_draft.py")

    def test_compile_patch_draft_previews_rejects_duplicate_same_path_entries(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {
                    "kind": "edit_file",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 42"}],
                },
                {
                    "kind": "edit_file_hunks",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 43"}],
                },
            ],
        }

        preview = compile_patch_draft_previews(
            artifact,
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(preview["kind"], "patch_blocker")
        self.assertEqual(preview["code"], "model_returned_non_schema")
        self.assertIn("duplicate path", preview["detail"])

    def test_compile_patch_draft_previews_single_hunk_shape(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {
                    "kind": "edit_file",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 42"}],
                }
            ],
        }

        preview = compile_patch_draft_previews(artifact, allowed_write_roots=ALLOWED_WRITE_ROOTS)

        self.assertIsInstance(preview, list)
        self.assertEqual(len(preview), 1)
        self.assertEqual(
            preview[0],
            {
                "type": "edit_file",
                "path": "src/mew/patch_draft.py",
                "old": "return 41",
                "new": "return 42",
                "apply": False,
                "dry_run": True,
            },
        )

    def test_compile_patch_draft_previews_multi_hunk_shape_and_order(self):
        artifact = {
            "kind": "patch_draft",
            "todo_id": "todo-17",
            "status": "validated",
            "files": [
                {
                    "kind": "edit_file_hunks",
                    "path": "tests/test_patch_draft.py",
                    "edits": [
                        {"old": "def alpha\n", "new": "def beta\n"},
                        {"old": "def gamma\n", "new": "def omega\n"},
                    ],
                },
                {
                    "kind": "edit_file",
                    "path": "src/mew/patch_draft.py",
                    "edits": [{"old": "return 41", "new": "return 42"}],
                },
            ],
        }

        preview = compile_patch_draft_previews(artifact, allowed_write_roots=ALLOWED_WRITE_ROOTS)

        self.assertEqual([item["path"] for item in preview], ["tests/test_patch_draft.py", "src/mew/patch_draft.py"])
        self.assertEqual(preview[0]["type"], "edit_file_hunks")
        self.assertEqual(preview[1]["type"], "edit_file")
        self.assertEqual(
            preview[0]["edits"],
            [
                {"old": "def alpha\n", "new": "def beta\n"},
                {"old": "def gamma\n", "new": "def omega\n"},
            ],
        )


class PatchDraftTests(unittest.TestCase):
    def test_compile_patch_draft_validates_paired_src_and_test_edit(self):
        source_path = "src/mew/patch_draft.py"
        test_path = "tests/test_patch_draft.py"
        source_before = "def meaning():\n    return 41\n"
        test_before = (
            "def test_meaning(self):\n"
            "    self.assertEqual(meaning(), 41)\n"
        )
        proposal = {
            "kind": "patch_proposal",
            "summary": "increment the paired meaning value",
            "files": [
                {
                    "path": source_path,
                    "edits": [{"old": "return 41", "new": "return 42"}],
                },
                {
                    "path": test_path,
                    "edits": [{"old": "meaning(), 41", "new": "meaning(), 42"}],
                },
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(source_path, test_path),
            proposal=proposal,
            cached_windows={
                source_path: _window(source_path, source_before),
                test_path: _window(test_path, test_before),
            },
            live_files={
                source_path: _live_file(source_before),
                test_path: _live_file(test_before),
            },
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_draft")
        self.assertEqual(artifact["status"], "validated")
        self.assertEqual(artifact["todo_id"], "todo-17")
        self.assertEqual(len(artifact["files"]), 2)
        self.assertEqual(
            [item["kind"] for item in artifact["files"]],
            ["edit_file", "edit_file"],
        )
        self.assertIn("--- a/src/mew/patch_draft.py", artifact["unified_diff"])
        self.assertIn("+++ b/tests/test_patch_draft.py", artifact["unified_diff"])
        self.assertIn("+    return 42", artifact["unified_diff"])
        self.assertIn("+    self.assertEqual(meaning(), 42)", artifact["unified_diff"])
        self.assertTrue(all(item["pre_file_sha256"] != item["post_file_sha256"] for item in artifact["files"]))

    def test_compile_patch_draft_blocks_src_edit_when_paired_test_outside_target_paths(self):
        source_path = "src/mew/patch_draft.py"
        test_path = "tests/test_patch_draft.py"
        source_before = "def meaning():\n    return 41\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": source_path,
                    "edits": [{"old": "return 41", "new": "return 42"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(source_path),
            proposal=proposal,
            cached_windows={
                source_path: _window(source_path, source_before),
            },
            live_files={
                source_path: _live_file(source_before),
            },
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "write_policy_violation")
        self.assertEqual(artifact["path"], test_path)
        self.assertEqual(
            artifact["detail"],
            "paired test path is outside the active WorkTodo target_paths",
        )

    def test_compile_patch_draft_blocks_overlapping_same_path_hunks(self):
        path = "tests/test_patch_draft.py"
        before_text = "abcdef\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [
                        {"old": "abcd", "new": "ABCD"},
                        {"old": "cdef", "new": "CDEF"},
                    ],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "overlapping_hunks")
        self.assertEqual(artifact["path"], path)

    def test_compile_patch_draft_blocks_when_old_text_missing_from_cached_window(self):
        path = "tests/test_patch_draft.py"
        before_text = "def test_meaning(self):\n    self.assertEqual(meaning(), 41)\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "meaning(), 99", "new": "meaning(), 42"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "old_text_not_found")
        self.assertEqual(artifact["path"], path)
        self.assertEqual(artifact["recovery_action"], "refresh_cached_window")

    def test_compile_patch_draft_blocks_when_live_text_and_hash_disagree(self):
        path = "tests/test_patch_draft.py"
        before_text = "value = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "value = 1", "new": "value = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text, sha256=sha256_text("different\n"))},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "stale_cached_window_text")
        self.assertEqual(artifact["detail"], "provided live file text/hash mismatch")
        self.assertEqual(artifact["recovery_action"], "refresh_cached_window")

    def test_compile_patch_draft_block_duplicate_same_path_files(self):
        path = "tests/test_patch_draft.py"
        before_text = "a\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "a", "new": "b"}],
                },
                {
                    "path": path,
                    "edits": [{"old": "a", "new": "c"}],
                },
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "model_returned_non_schema")
        self.assertIn("duplicate", artifact["detail"])

    def test_compile_patch_draft_validates_same_file_multi_hunk_happy_path(self):
        path = "tests/test_patch_draft.py"
        before_text = "alpha\nbeta\n\ngamma\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [
                        {"old": "alpha\n", "new": "ALPHA\n"},
                        {"old": "gamma\n", "new": "GAMMA\n"},
                    ],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_draft")
        self.assertEqual(artifact["files"][0]["kind"], "edit_file_hunks")
        self.assertEqual(artifact["files"][0]["pre_file_sha256"], sha256_text(before_text))
        self.assertNotEqual(artifact["files"][0]["pre_file_sha256"], artifact["files"][0]["post_file_sha256"])
        self.assertIn("+ALPHA", artifact["unified_diff"])
        self.assertIn("+GAMMA", artifact["unified_diff"])

    def test_compile_patch_draft_blocks_ambiguous_old_text_match(self):
        path = "tests/test_patch_draft.py"
        before_text = "x = 1\nx = 1\nx = 2\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "x = 1", "new": "x = 3"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "ambiguous_old_text_match")
        self.assertIn("matched 2 times", artifact["detail"])

    def test_compile_patch_draft_blocks_missing_exact_cached_window_texts(self):
        path = "tests/test_patch_draft.py"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "alpha", "new": "beta"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={},
            live_files={path: _live_file("alpha")},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "missing_exact_cached_window_texts")

    def test_compile_patch_draft_blocks_cached_window_text_truncated(self):
        path = "tests/test_patch_draft.py"
        before_text = "a = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "a = 1", "new": "a = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={
                path: _window(path, before_text, context_truncated=True),
            },
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "cached_window_text_truncated")

    def test_compile_patch_draft_blocks_no_material_change(self):
        path = "tests/test_patch_draft.py"
        before_text = "a = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "a = 1", "new": "a = 1"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "no_material_change")

    def test_compile_patch_draft_blocks_write_policy_violation(self):
        path = "docs/sample.txt"
        before_text = "text\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "text", "new": "updated"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: _live_file(before_text)},
            allowed_write_roots=["/tmp"],
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "write_policy_violation")
        self.assertEqual(artifact["detail"], "proposal path is outside allowed_write_roots")

    def test_compile_patch_draft_blocks_write_policy_violation_when_roots_missing(self):
        path = "tests/test_patch_draft.py"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "x = 1", "new": "x = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, "x = 1\n")},
            live_files={path: _live_file("x = 1\n")},
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "write_policy_violation")
        self.assertEqual(artifact["detail"], "allowed_write_roots is required for validation")

    def test_compile_patch_draft_blocks_model_returned_refusal(self):
        artifact = compile_patch_draft(
            todo=_todo("tests/test_patch_draft.py"),
            proposal={
                "kind": "patch_blocker",
                "code": "model_returned_refusal",
                "path": "tests/test_patch_draft.py",
                "detail": "model refused to propose changes",
            },
            cached_windows={},
            live_files={},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "model_returned_refusal")
        self.assertEqual(artifact["recovery_action"], "inspect_refusal")

    def test_compile_patch_draft_blocks_non_dict_proposal(self):
        artifact = compile_patch_draft(
            todo=_todo("tests/test_patch_draft.py"),
            proposal="wait for approval",
            cached_windows={},
            live_files={},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "model_returned_non_schema")
        self.assertEqual(artifact["recovery_action"], "retry_with_schema")

    def test_compile_patch_draft_blocks_unpaired_source_edit(self):
        source_path = "src/mew/patch_draft.py"
        source_before = "def meaning():\n    return 41\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": source_path,
                    "edits": [{"old": "return 41", "new": "return 42"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(source_path, "tests/test_patch_draft.py"),
            proposal=proposal,
            cached_windows={source_path: _window(source_path, source_before)},
            live_files={source_path: _live_file(source_before)},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "unpaired_source_edit_blocked")
        self.assertEqual(artifact["path"], source_path)
        self.assertIn("tests/test_patch_draft.py", artifact["detail"])

    def test_compile_patch_draft_blocks_missing_live_file_payload(self):
        path = "tests/test_patch_draft.py"
        before_text = "value = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "value = 1", "new": "value = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "stale_cached_window_text")
        self.assertEqual(artifact["detail"], "missing live file payload")

    def test_compile_patch_draft_blocks_missing_live_file_text(self):
        path = "tests/test_patch_draft.py"
        before_text = "value = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "value = 1", "new": "value = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: {}},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "stale_cached_window_text")
        self.assertEqual(artifact["detail"], "missing live file text")

    def test_compile_patch_draft_blocks_missing_live_file_sha256(self):
        path = "tests/test_patch_draft.py"
        before_text = "value = 1\n"
        proposal = {
            "kind": "patch_proposal",
            "files": [
                {
                    "path": path,
                    "edits": [{"old": "value = 1", "new": "value = 2"}],
                }
            ],
        }

        artifact = compile_patch_draft(
            todo=_todo(path),
            proposal=proposal,
            cached_windows={path: _window(path, before_text)},
            live_files={path: {"text": before_text}},
            allowed_write_roots=ALLOWED_WRITE_ROOTS,
        )

        self.assertEqual(artifact["kind"], "patch_blocker")
        self.assertEqual(artifact["code"], "stale_cached_window_text")
        self.assertEqual(artifact["detail"], "missing live file sha256")

    def test_recovery_action_vocabulary_is_frozen_for_phase_2(self):
        self.assertEqual(
            PATCH_BLOCKER_RECOVERY_ACTIONS,
            {
                "missing_exact_cached_window_texts": "refresh_cached_window",
                "cached_window_text_truncated": "refresh_cached_window",
                "stale_cached_window_text": "refresh_cached_window",
                "old_text_not_found": "refresh_cached_window",
                "ambiguous_old_text_match": "narrow_old_text",
                "overlapping_hunks": "merge_or_split_hunks",
                "no_material_change": "revise_patch",
                "unpaired_source_edit_blocked": "add_paired_test_edit",
                "write_policy_violation": "revise_patch_scope",
                "model_returned_non_schema": "retry_with_schema",
                "model_returned_refusal": "inspect_refusal",
                "review_rejected": "revise_patch_from_review_findings",
            },
        )


if __name__ == "__main__":
    unittest.main()
