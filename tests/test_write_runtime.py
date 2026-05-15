import json
from pathlib import Path

import pytest

from mew.implement_lane.types import ToolCallEnvelope
from mew.implement_lane.write_runtime import ImplementV2WriteRuntime


def _tool_call(tool_name: str, arguments: dict[str, object]) -> ToolCallEnvelope:
    return ToolCallEnvelope(
        lane_attempt_id="attempt-1",
        provider="test",
        provider_call_id="call-1",
        mew_tool_call_id="mew-call-1",
        tool_name=tool_name,
        arguments=arguments,
        status="validated",
    )


def test_apply_patch_output_card_is_typed_concise_and_ref_backed(tmp_path: Path) -> None:
    target = tmp_path / "worker.py"
    target.write_text("value = 'old'\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: worker.py",
        "@@",
        "-value = 'old'",
        "+value = 'new'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "completed"
    assert target.read_text(encoding="utf-8") == "value = 'new'\n"
    payload = result.content[0]
    assert isinstance(payload, dict)
    card = payload["mutation_output_card"]
    assert card["kind"] == "mutation_output_card"
    assert card["operation"] == "apply_patch"
    assert card["status"] == "applied"
    assert card["path"].endswith("worker.py")
    assert "diff" not in card
    assert card["diff_ref"] in result.content_refs
    assert card["snapshot_refs"]["pre"] in result.content_refs
    assert card["snapshot_refs"]["post"] in result.content_refs
    assert result.evidence_refs == (card["mutation_ref"],)
    assert card["mutation_ref"] in card["artifact_refs"]
    assert "value = 'new'" not in json.dumps(card, sort_keys=True)
    assert len(json.dumps(card, sort_keys=True)) < 5000
    assert payload["summary"].startswith("apply_patch applied")


def test_apply_patch_multi_file_output_card_lists_changed_paths(tmp_path: Path) -> None:
    first = tmp_path / "alpha.py"
    second = tmp_path / "beta.py"
    first.write_text("alpha = 'old'\n", encoding="utf-8")
    second.write_text("beta = 'old'\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        "-alpha = 'old'",
        "+alpha = 'new'",
        "*** Update File: beta.py",
        "@@",
        "-beta = 'old'",
        "+beta = 'new'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "completed"
    assert first.read_text(encoding="utf-8") == "alpha = 'new'\n"
    assert second.read_text(encoding="utf-8") == "beta = 'new'\n"
    payload = result.content[0]
    assert isinstance(payload, dict)
    card = payload["mutation_output_card"]
    assert card["operation"] == "apply_patch"
    assert card["status"] == "applied"
    assert card["path"] == ""
    assert card["changed_paths"] == ["alpha.py", "beta.py"]
    assert card["diff_stats"] == {"added": 2, "removed": 2}
    assert payload["patch_operation"] == "multi_file"
    assert payload["patch_file_count"] == 2
    assert payload["patch_transport"]["paths"] == ["alpha.py", "beta.py"]
    assert payload["typed_source_mutation"]["changed_paths"] == ["alpha.py", "beta.py"]
    assert card["diff_ref"] in result.content_refs
    assert result.evidence_refs == (card["mutation_ref"],)
    assert [Path(str(effect["path"])).name for effect in result.side_effects] == ["alpha.py", "beta.py"]
    assert "alpha = 'new'" not in json.dumps(card, sort_keys=True)
    assert "beta = 'new'" not in json.dumps(card, sort_keys=True)


def test_apply_patch_multi_file_duplicate_canonical_path_fails_before_mutation(tmp_path: Path) -> None:
    target = tmp_path / "alpha.py"
    target.write_text("alpha = 'old'\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        "-alpha = 'old'",
        "+alpha = 'new'",
        "*** Update File: ./alpha.py",
        "@@",
        "-alpha = 'new'",
        "+alpha = 'newer'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "duplicate or parent/child target path" in str(result.content[0]["reason"])
    assert target.read_text(encoding="utf-8") == "alpha = 'old'\n"


def test_apply_patch_multi_file_parent_child_conflict_fails_before_mutation(tmp_path: Path) -> None:
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Add File: pkg",
        "+not a directory",
        "*** Add File: pkg/mod.py",
        "+value = 1",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "parent/child target path" in str(result.content[0]["reason"])
    assert not (tmp_path / "pkg").exists()
    assert not (tmp_path / "pkg" / "mod.py").exists()


def test_apply_patch_multi_file_case_alias_existing_path_fails_before_mutation(tmp_path: Path) -> None:
    target = tmp_path / "alpha.py"
    alias = tmp_path / "ALPHA.py"
    target.write_text("alpha = 'old'\n", encoding="utf-8")
    try:
        same_file = alias.exists() and alias.samefile(target)
    except OSError:
        same_file = False
    if not same_file:
        pytest.skip("filesystem is case-sensitive for this path")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        "-alpha = 'old'",
        "+alpha = 'new'",
        "*** Update File: ALPHA.py",
        "@@",
        "-alpha = 'new'",
        "+alpha = 'newer'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "duplicate or parent/child target path" in str(result.content[0]["reason"])
    assert target.read_text(encoding="utf-8") == "alpha = 'old'\n"


def test_apply_patch_multi_file_case_alias_new_paths_fail_before_mutation(tmp_path: Path) -> None:
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Add File: alpha.py",
        "+alpha = 'new'",
        "*** Add File: ALPHA.py",
        "+alpha = 'newer'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "duplicate or parent/child target path" in str(result.content[0]["reason"])
    assert not (tmp_path / "alpha.py").exists()
    assert not (tmp_path / "ALPHA.py").exists()


def test_apply_patch_multi_file_case_parent_child_conflict_fails_before_mutation(tmp_path: Path) -> None:
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Add File: pkg",
        "+not a directory",
        "*** Add File: PKG/mod.py",
        "+value = 1",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "duplicate or parent/child target path" in str(result.content[0]["reason"])
    assert not (tmp_path / "pkg").exists()
    assert not (tmp_path / "PKG").exists()


def test_apply_patch_multi_file_unicode_alias_new_paths_fail_before_mutation(tmp_path: Path) -> None:
    composed = "café.py"
    decomposed = "cafe\u0301.py"
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        f"*** Add File: {composed}",
        "+value = 'new'",
        f"*** Add File: {decomposed}",
        "+value = 'newer'",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "duplicate or parent/child target path" in str(result.content[0]["reason"])
    assert not (tmp_path / composed).exists()
    assert not (tmp_path / decomposed).exists()


def test_apply_patch_multi_file_existing_file_parent_conflict_fails_before_mutation(tmp_path: Path) -> None:
    alpha = tmp_path / "alpha.py"
    alpha.write_text("alpha = 'old'\n", encoding="utf-8")
    (tmp_path / "pkg").write_text("not a directory\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        "-alpha = 'old'",
        "+alpha = 'new'",
        "*** Add File: pkg/mod.py",
        "+value = 1",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "failed"
    assert "file-valued parent path" in str(result.content[0]["reason"])
    assert alpha.read_text(encoding="utf-8") == "alpha = 'old'\n"
    assert (tmp_path / "pkg").read_text(encoding="utf-8") == "not a directory\n"


def test_apply_patch_multi_file_stale_precondition_reports_failed_status(tmp_path: Path) -> None:
    first = tmp_path / "alpha.py"
    second = tmp_path / "beta.py"
    first.write_text("alpha = 'old'\n", encoding="utf-8")
    second.write_text("beta = 'old'\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        "-alpha = 'old'",
        "+alpha = 'new'",
        "*** Update File: beta.py",
        "@@",
        "-beta = 'old'",
        "+beta = 'new'",
        "*** End Patch",
    ]

    result = runtime.execute(
        _tool_call(
            "apply_patch",
            {
                "patch_lines": patch_lines,
                "apply": True,
                "expected_pre_sha256": "0" * 64,
            },
        )
    )

    assert result.status == "failed"
    assert result.content[0]["failure_class"] == "stale_source_precondition"
    assert first.read_text(encoding="utf-8") == "alpha = 'old'\n"
    assert second.read_text(encoding="utf-8") == "beta = 'old'\n"


def test_apply_patch_context_line_that_looks_like_header_is_not_file_header(tmp_path: Path) -> None:
    first = tmp_path / "alpha.py"
    second = tmp_path / "beta.py"
    first.write_text("before\n*** Update File: beta.py\nafter\n", encoding="utf-8")
    second.write_text("after\n", encoding="utf-8")
    runtime = ImplementV2WriteRuntime(
        workspace=tmp_path,
        allowed_write_roots=(str(tmp_path),),
        approved_write_calls=(
            {"provider_call_id": "call-1", "status": "approved", "approval_id": "approval-1"},
        ),
        artifact_dir=tmp_path / "artifacts",
    )
    patch_lines = [
        "*** Begin Patch",
        "*** Update File: alpha.py",
        "@@",
        " before",
        " *** Update File: beta.py",
        "-after",
        "+done",
        "*** End Patch",
    ]

    result = runtime.execute(_tool_call("apply_patch", {"patch_lines": patch_lines, "apply": True}))

    assert result.status == "completed"
    assert first.read_text(encoding="utf-8") == "before\n*** Update File: beta.py\ndone\n"
    assert second.read_text(encoding="utf-8") == "after\n"
    assert result.content[0]["patch_operation"] == "update_file"
