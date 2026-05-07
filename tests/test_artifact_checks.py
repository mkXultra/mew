import os

import pytest

from mew.implement_lane.artifact_checks import (
    capture_pre_run_artifact_stats,
    check_expected_artifact,
    check_expected_artifacts,
)
from mew.implement_lane.execution_evidence import ExpectedArtifact, normalize_execution_contract


def test_path_artifact_exists_non_empty_and_kind_pass(tmp_path) -> None:
    artifact_path = tmp_path / "frame.bmp"
    artifact_path.write_bytes(b"BM" + b"\x00" * 60)
    artifact = ExpectedArtifact(
        id="frame",
        kind="file",
        target={"type": "path", "path": "frame.bmp"},
        path="frame.bmp",
        checks=(
            {"type": "exists", "severity": "blocking"},
            {"type": "non_empty", "severity": "blocking"},
            {"type": "kind", "expected": "bmp", "severity": "blocking"},
        ),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=artifact_path.stat().st_mtime - 1,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    assert evidence.status == "passed"
    assert evidence.blocking is False
    assert [check["passed"] for check in evidence.checks] == [True, True, True]


def test_missing_required_artifact_fails_blocking_exists(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="output",
        target={"type": "path", "path": "missing.txt"},
        path="missing.txt",
        checks=({"type": "exists", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    assert evidence.status == "failed"
    assert evidence.blocking is True
    assert evidence.post_run_stat["exists"] is False


def test_created_after_run_start_requires_pre_run_stat(tmp_path) -> None:
    artifact_path = tmp_path / "new.txt"
    artifact_path.write_text("hello", encoding="utf-8")
    artifact = ExpectedArtifact(
        id="new",
        target={"type": "path", "path": "new.txt"},
        path="new.txt",
        freshness="created_after_run_start",
        checks=({"type": "mtime_after", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=artifact_path.stat().st_mtime - 1,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    assert evidence.status == "partial"
    assert evidence.blocking is True
    assert evidence.checks[0]["observed"]["reason"] == "missing_pre_run_stat"


def test_blocking_failed_check_is_not_downgraded_by_later_partial_check(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="missing",
        target={"type": "path", "path": "missing.txt"},
        path="missing.txt",
        freshness="created_after_run_start",
        checks=(
            {"type": "exists", "severity": "blocking"},
            {"type": "mtime_after", "severity": "blocking"},
        ),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    assert evidence.status == "failed"
    assert evidence.checks[0]["passed"] is False
    assert evidence.checks[1]["passed"] is False


def test_created_after_run_start_with_invalid_run_started_is_partial(tmp_path) -> None:
    artifact_path = tmp_path / "new.txt"
    artifact_path.write_text("hello", encoding="utf-8")
    artifact = ExpectedArtifact(
        id="new",
        target={"type": "path", "path": "new.txt"},
        path="new.txt",
        freshness="created_after_run_start",
        checks=({"type": "mtime_after", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at="not-a-time",
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        pre_run_stat={"exists": False, "mtime": None, "size": None},
    )

    assert evidence.status == "partial"
    assert evidence.checks[0]["observed"]["reason"] == "invalid_run_started_at"


def test_capture_pre_run_stat_allows_missing_path_inside_allowed_root(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="future",
        target={"type": "path", "path": "future.txt"},
        path="future.txt",
    )

    stats = capture_pre_run_artifact_stats([artifact], workspace=tmp_path, allowed_roots=[str(tmp_path)])

    assert stats["future"]["exists"] is False
    assert stats["future"]["path"].endswith("future.txt")


def test_created_after_run_start_passes_with_missing_pre_run_stat_and_fresh_post(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="future",
        target={"type": "path", "path": "future.txt"},
        path="future.txt",
        freshness="created_after_run_start",
        checks=({"type": "mtime_after", "severity": "blocking"},),
    )
    pre_stats = capture_pre_run_artifact_stats([artifact], workspace=tmp_path, allowed_roots=[str(tmp_path)])
    artifact_path = tmp_path / "future.txt"
    artifact_path.write_text("created", encoding="utf-8")

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=artifact_path.stat().st_mtime - 1,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        pre_run_stat=pre_stats["future"],
    )

    assert evidence.status == "passed"
    assert evidence.checks[0]["observed"]["pre_exists"] is False


def test_path_outside_allowed_roots_is_rejected(tmp_path) -> None:
    outside = tmp_path.parent / "outside-artifact.txt"
    artifact = ExpectedArtifact(
        id="outside",
        target={"type": "path", "path": str(outside)},
        path=str(outside),
    )

    with pytest.raises(ValueError, match="outside allowed roots"):
        check_expected_artifact(
            artifact,
            contract_id="contract:1",
            command_run_id="command-run:1",
            tool_run_record_id="tool-run-record:1",
            run_started_at=0,
            workspace=tmp_path,
            allowed_roots=[str(tmp_path)],
        )


def test_stream_text_contains_is_explicit_stream_target_only(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="stdout-proof",
        kind="stdout",
        target={"type": "stream", "stream": "stdout", "source_tool_run_record_id": "tool-run-record:1"},
        checks=({"type": "text_contains", "text": "OK", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        stream_outputs={"stdout": "OK\n"},
    )

    assert evidence.status == "passed"
    assert evidence.post_run_stat["size"] == 3


def test_normalized_stdout_artifact_checks_current_tool_stream(tmp_path) -> None:
    contract = normalize_execution_contract(
        {
            "id": "contract:stdout",
            "expected_artifacts": [
                {
                    "target": "stdout",
                    "checks": [
                        {"kind": "non_empty"},
                        {"kind": "text_contains", "value": "ELF"},
                    ],
                },
                {
                    "id": "stdout-stream-field",
                    "stream": "stdout",
                    "checks": [{"kind": "text_contains", "value": "MIPS"}],
                }
            ],
        }
    )

    evidence = check_expected_artifacts(
        contract,
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        stream_outputs={"stdout": "ELF 32-bit MSB executable, MIPS\n"},
    )

    assert [item.status for item in evidence] == ["passed", "passed"]
    assert [item.kind for item in evidence] == ["stdout", "stdout"]
    assert [item.target for item in evidence] == [
        {"type": "stream", "stream": "stdout"},
        {"type": "stream", "stream": "stdout"},
    ]
    assert [check["type"] for check in evidence[0].checks] == ["non_empty", "text_contains"]
    assert evidence[1].checks[0]["type"] == "text_contains"


def test_stream_target_cannot_pass_against_another_tool_record_output(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="stdout-proof",
        kind="stdout",
        target={"type": "stream", "stream": "stdout", "source_tool_run_record_id": "tool-run-record:expected"},
        checks=({"type": "text_contains", "text": "OK", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:actual",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        stream_outputs={"stdout": "OK\n"},
    )

    assert evidence.status == "failed"
    assert evidence.post_run_stat["exists"] is False


def test_stream_target_can_use_scoped_tool_record_output(tmp_path) -> None:
    artifact = ExpectedArtifact(
        id="stdout-proof",
        kind="stdout",
        target={"type": "stream", "stream": "stdout", "source_tool_run_record_id": "tool-run-record:expected"},
        checks=({"type": "text_contains", "text": "OK", "severity": "blocking"},),
    )

    evidence = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:actual",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        stream_outputs={"tool-run-record:expected": {"stdout": "OK\n"}},
    )

    assert evidence.status == "passed"


def test_previous_check_freshness_uses_prior_evidence_mtime(tmp_path) -> None:
    artifact_path = tmp_path / "artifact.txt"
    artifact_path.write_text("v1", encoding="utf-8")
    artifact = ExpectedArtifact(
        id="artifact",
        target={"type": "path", "path": "artifact.txt"},
        path="artifact.txt",
        freshness="modified_after_previous_check",
        checks=({"type": "mtime_after", "severity": "blocking"},),
    )
    first = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )
    os.utime(artifact_path, (artifact_path.stat().st_atime + 2, artifact_path.stat().st_mtime + 2))

    second = check_expected_artifact(
        artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:2",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        previous_evidence=[first],
    )

    assert first.status == "partial"
    assert second.status == "passed"


def test_previous_check_freshness_requires_same_artifact_path_identity(tmp_path) -> None:
    first_path = tmp_path / "first.txt"
    second_path = tmp_path / "second.txt"
    first_path.write_text("v1", encoding="utf-8")
    second_path.write_text("v2", encoding="utf-8")
    first_artifact = ExpectedArtifact(
        id="artifact",
        target={"type": "path", "path": "first.txt"},
        path="first.txt",
    )
    second_artifact = ExpectedArtifact(
        id="artifact",
        target={"type": "path", "path": "second.txt"},
        path="second.txt",
        freshness="modified_after_previous_check",
        checks=({"type": "mtime_after", "severity": "blocking"},),
    )
    first = check_expected_artifact(
        first_artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    second = check_expected_artifact(
        second_artifact,
        contract_id="contract:1",
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:2",
        run_started_at=0,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
        previous_evidence=[first],
    )

    assert second.status == "partial"
    assert second.checks[0]["observed"]["reason"] == "missing_previous_evidence"


def test_check_expected_artifacts_uses_contract_expected_artifacts(tmp_path) -> None:
    artifact_path = tmp_path / "result.json"
    artifact_path.write_text('{"ok": true}', encoding="utf-8")
    contract = normalize_execution_contract(
        {
            "id": "contract:1",
            "expected_artifacts": [
                {
                    "id": "result",
                    "kind": "json",
                    "target": {"type": "path", "path": "result.json"},
                    "path": "result.json",
                    "checks": [{"type": "json_schema", "severity": "blocking"}],
                }
            ],
        }
    )

    evidence = check_expected_artifacts(
        contract,
        command_run_id="command-run:1",
        tool_run_record_id="tool-run-record:1",
        run_started_at=artifact_path.stat().st_mtime - 1,
        workspace=tmp_path,
        allowed_roots=[str(tmp_path)],
    )

    assert len(evidence) == 1
    assert evidence[0].status == "passed"
