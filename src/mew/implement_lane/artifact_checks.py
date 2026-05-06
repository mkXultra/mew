"""Deterministic expected-artifact checks for implement_v2."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any, Mapping

from .execution_evidence import ArtifactEvidence, ExecutionContract, ExpectedArtifact


def capture_pre_run_artifact_stats(
    artifacts: tuple[ExpectedArtifact, ...] | list[ExpectedArtifact],
    *,
    workspace: object,
    allowed_roots: tuple[str, ...] | list[str],
) -> dict[str, dict[str, Any]]:
    """Capture pre-run stats for path artifacts.

    Missing artifacts are represented as `exists=false` instead of raising. A
    path outside allowed roots still raises because the contract is unsafe.
    """

    stats: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if _target_type(artifact) != "path":
            continue
        path = _resolve_artifact_path(artifact, workspace=workspace, allowed_roots=allowed_roots)
        stats[artifact.id] = _stat_path(path)
    return stats


def check_expected_artifacts(
    contract: ExecutionContract,
    *,
    command_run_id: str,
    tool_run_record_id: str,
    run_started_at: object,
    workspace: object,
    allowed_roots: tuple[str, ...] | list[str],
    pre_run_stats: Mapping[str, Mapping[str, Any]] | None = None,
    previous_evidence: tuple[ArtifactEvidence, ...] | list[ArtifactEvidence] = (),
    stream_outputs: Mapping[str, str] | None = None,
) -> tuple[ArtifactEvidence, ...]:
    return tuple(
        check_expected_artifact(
            artifact,
            contract_id=contract.id,
            command_run_id=command_run_id,
            tool_run_record_id=tool_run_record_id,
            run_started_at=run_started_at,
            workspace=workspace,
            allowed_roots=allowed_roots,
            pre_run_stat=dict((pre_run_stats or {}).get(artifact.id) or {}),
            previous_evidence=previous_evidence,
            stream_outputs=stream_outputs,
        )
        for artifact in contract.expected_artifacts
    )


def check_expected_artifact(
    artifact: ExpectedArtifact,
    *,
    contract_id: str,
    command_run_id: str,
    tool_run_record_id: str,
    run_started_at: object,
    workspace: object,
    allowed_roots: tuple[str, ...] | list[str],
    pre_run_stat: Mapping[str, Any] | None = None,
    previous_evidence: tuple[ArtifactEvidence, ...] | list[ArtifactEvidence] = (),
    stream_outputs: Mapping[str, str] | None = None,
) -> ArtifactEvidence:
    target_type = _target_type(artifact)
    checks = artifact.checks or ({"type": "exists", "severity": "blocking"},)
    pre_stat = dict(pre_run_stat or {})
    post_stat: dict[str, Any] = {}
    target = dict(artifact.target)
    path = artifact.path
    stream_text = ""
    if target_type == "path":
        resolved = _resolve_artifact_path(artifact, workspace=workspace, allowed_roots=allowed_roots)
        path = str(resolved)
        post_stat = _stat_path(resolved)
    elif target_type == "stream":
        stream = str(target.get("stream") or artifact.kind or "")
        stream_text = _stream_text(
            stream_outputs or {},
            stream=stream,
            source_tool_run_record_id=str(target.get("source_tool_run_record_id") or tool_run_record_id),
            current_tool_run_record_id=tool_run_record_id,
        )
        post_stat = {"exists": bool(stream_text), "size": len(stream_text), "mtime": None, "path": ""}
    else:
        post_stat = {"exists": False, "size": None, "mtime": None, "path": ""}

    observed_checks: list[dict[str, Any]] = []
    status = "passed"
    blocking = False
    for index, check in enumerate(checks):
        result = _run_check(
            artifact,
            check=dict(check),
            index=index,
            target_type=target_type,
            path=Path(path) if path else None,
            stream_text=stream_text,
            pre_stat=pre_stat,
            post_stat=post_stat,
            run_started_at=run_started_at,
            previous_evidence=previous_evidence,
        )
        observed_checks.append(result)
        if result["passed"] is None:
            if status != "failed":
                status = "partial"
            if result.get("severity") == "blocking":
                blocking = True
        elif result["passed"] is False and result.get("severity") == "blocking":
            status = "failed"
            blocking = True
    return ArtifactEvidence(
        evidence_id=f"artifact-evidence:{artifact.id}:{tool_run_record_id}",
        artifact_id=artifact.id,
        command_run_id=command_run_id,
        tool_run_record_id=tool_run_record_id,
        contract_id=contract_id,
        substep_id=artifact.producer_substep_id,
        target=target,
        path=path,
        kind=artifact.kind,
        required=artifact.required,
        source=artifact.source,
        confidence=artifact.confidence,
        freshness=artifact.freshness,
        pre_run_stat=pre_stat,
        post_run_stat=post_stat,
        checks=tuple(observed_checks),
        status=status,  # type: ignore[arg-type]
        blocking=blocking,
    )


def _run_check(
    artifact: ExpectedArtifact,
    *,
    check: dict[str, Any],
    index: int,
    target_type: str,
    path: Path | None,
    stream_text: str,
    pre_stat: Mapping[str, Any],
    post_stat: Mapping[str, Any],
    run_started_at: object,
    previous_evidence: tuple[ArtifactEvidence, ...] | list[ArtifactEvidence],
) -> dict[str, Any]:
    check_type = str(check.get("type") or "exists")
    severity = str(check.get("severity") or "blocking")
    passed: bool | None
    message = ""
    observed: dict[str, Any] = {}
    if check_type == "exists":
        passed = bool(post_stat.get("exists"))
        observed = {"exists": passed}
    elif check_type == "non_empty":
        exists = bool(post_stat.get("exists"))
        size = post_stat.get("size")
        passed = exists and isinstance(size, int | float) and size > 0
        observed = {"exists": exists, "size": size}
    elif check_type == "size_between":
        size = post_stat.get("size")
        minimum = int(check.get("min", 0))
        maximum = int(check.get("max", 2**63 - 1))
        passed = isinstance(size, int | float) and minimum <= size <= maximum
        observed = {"size": size, "min": minimum, "max": maximum}
    elif check_type == "mtime_after":
        passed, observed = _mtime_after_result(
            artifact,
            run_started_at=run_started_at,
            pre_stat=pre_stat,
            post_stat=post_stat,
            previous_evidence=previous_evidence,
        )
    elif check_type == "kind":
        expected = str(check.get("expected") or artifact.kind)
        passed, observed = _kind_check(path=path, expected=expected, post_stat=post_stat)
    elif check_type == "json_schema":
        passed, observed = _json_check(path=path, stream_text=stream_text, target_type=target_type)
    elif check_type == "text_contains":
        needle = str(check.get("text") or check.get("expected") or "")
        text = _text_for_check(path=path, stream_text=stream_text, target_type=target_type)
        passed = needle in text if needle else False
        observed = {"text_present": passed, "needle": needle}
    elif check_type == "regex":
        pattern = str(check.get("pattern") or "")
        text = _text_for_check(path=path, stream_text=stream_text, target_type=target_type)
        passed = bool(pattern) and re.search(pattern, text) is not None
        observed = {"regex_matched": passed, "pattern": pattern}
    else:
        passed = None
        message = f"unsupported artifact check type: {check_type}"
        observed = {"type": check_type}
    if passed is False and not message:
        message = f"artifact {artifact.id} check {check_type} failed"
    if passed is None and not message:
        message = f"artifact {artifact.id} check {check_type} is partial"
    return {
        "id": f"{artifact.id}:{check_type}:{index}",
        "type": check_type,
        "passed": passed,
        "severity": severity,
        "observed": observed,
        "message": message,
    }


def _mtime_after_result(
    artifact: ExpectedArtifact,
    *,
    run_started_at: object,
    pre_stat: Mapping[str, Any],
    post_stat: Mapping[str, Any],
    previous_evidence: tuple[ArtifactEvidence, ...] | list[ArtifactEvidence],
) -> tuple[bool | None, dict[str, Any]]:
    post_mtime = _optional_float(post_stat.get("mtime"))
    if not post_stat.get("exists") or post_mtime is None:
        return False, {"exists": bool(post_stat.get("exists")), "mtime": post_stat.get("mtime")}
    if artifact.freshness == "created_after_run_start":
        if not pre_stat:
            return None, {"reason": "missing_pre_run_stat", "post_mtime": post_mtime}
        run_started = _timestamp(run_started_at)
        if run_started is None:
            return None, {"reason": "invalid_run_started_at", "post_mtime": post_mtime}
        passed = not bool(pre_stat.get("exists")) and post_mtime >= run_started
        return passed, {"pre_exists": bool(pre_stat.get("exists")), "post_mtime": post_mtime, "run_started_at": run_started}
    if artifact.freshness == "modified_after_previous_check":
        previous_mtime = _latest_previous_mtime(artifact.id, str(post_stat.get("path") or ""), previous_evidence)
        if previous_mtime is None:
            return None, {"reason": "missing_previous_evidence", "post_mtime": post_mtime}
        return post_mtime > previous_mtime, {"post_mtime": post_mtime, "previous_mtime": previous_mtime}
    if artifact.freshness == "modified_after_run_start":
        run_started = _timestamp(run_started_at)
        if run_started is None:
            return None, {"reason": "invalid_run_started_at", "post_mtime": post_mtime}
        return post_mtime >= run_started, {"post_mtime": post_mtime, "run_started_at": run_started}
    return True, {"freshness": artifact.freshness, "post_mtime": post_mtime}


def _kind_check(*, path: Path | None, expected: str, post_stat: Mapping[str, Any]) -> tuple[bool, dict[str, Any]]:
    if not post_stat.get("exists") or path is None:
        return False, {"exists": bool(post_stat.get("exists")), "expected": expected}
    if expected in {"file", "binary", "log", "report"}:
        passed = path.is_file()
    elif expected == "directory":
        passed = path.is_dir()
    elif expected == "executable":
        passed = path.is_file() and os.access(path, os.X_OK)
    elif expected == "json":
        passed = _json_check(path=path, stream_text="", target_type="path")[0] is True
    elif expected in {"image", "bmp"}:
        passed = path.is_file() and _path_has_bmp_header(path)
    else:
        passed = path.exists()
    return passed, {"expected": expected, "path": str(path)}


def _json_check(*, path: Path | None, stream_text: str, target_type: str) -> tuple[bool, dict[str, Any]]:
    try:
        if target_type == "stream":
            json.loads(stream_text)
        elif path is not None:
            json.loads(path.read_text(encoding="utf-8"))
        else:
            return False, {"json": "missing_target"}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return False, {"json": "invalid", "error": str(exc)}
    return True, {"json": "valid"}


def _text_for_check(*, path: Path | None, stream_text: str, target_type: str) -> str:
    if target_type == "stream":
        return stream_text
    if path is None or not path.exists() or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _stream_text(
    stream_outputs: Mapping[str, Any],
    *,
    stream: str,
    source_tool_run_record_id: str,
    current_tool_run_record_id: str,
) -> str:
    scoped = stream_outputs.get(source_tool_run_record_id)
    if isinstance(scoped, Mapping):
        return str(scoped.get(stream) or "")
    if source_tool_run_record_id == current_tool_run_record_id:
        return str(stream_outputs.get(stream) or "")
    return ""


def _resolve_artifact_path(
    artifact: ExpectedArtifact,
    *,
    workspace: object,
    allowed_roots: tuple[str, ...] | list[str],
) -> Path:
    raw_path = str(artifact.path or artifact.target.get("path") or "")
    if not raw_path:
        raise ValueError(f"artifact {artifact.id} has no path target")
    workspace_path = Path(str(workspace or ".")).expanduser().resolve(strict=False)
    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace_path / candidate
    resolved = candidate.resolve(strict=False)
    roots = tuple(Path(str(root)).expanduser().resolve(strict=False) for root in allowed_roots)
    if not roots:
        raise ValueError("artifact checks require at least one allowed root")
    for root in roots:
        if resolved == root or _is_relative_to(resolved, root):
            return resolved
    allowed = ", ".join(str(root) for root in roots)
    raise ValueError(f"artifact path is outside allowed roots: {resolved}; allowed={allowed}")


def _stat_path(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"exists": False, "path": str(path), "mtime": None, "size": None, "kind": "missing"}
    if path.is_dir():
        kind = "directory"
    elif path.is_file():
        kind = "file"
    else:
        kind = "other"
    return {"exists": True, "path": str(path), "mtime": stat.st_mtime, "size": stat.st_size, "kind": kind}


def _target_type(artifact: ExpectedArtifact) -> str:
    target_type = str(artifact.target.get("type") or "")
    if target_type:
        return target_type
    if artifact.kind in {"stdout", "stderr"}:
        return "stream"
    return "path"


def _latest_previous_mtime(
    artifact_id: str,
    path: str,
    previous_evidence: tuple[ArtifactEvidence, ...] | list[ArtifactEvidence],
) -> float | None:
    mtimes = [
        _optional_float(evidence.post_run_stat.get("mtime"))
        for evidence in previous_evidence
        if evidence.artifact_id == artifact_id and str(evidence.path or evidence.post_run_stat.get("path") or "") == path
    ]
    real_mtimes = [mtime for mtime in mtimes if mtime is not None]
    return max(real_mtimes) if real_mtimes else None


def _timestamp(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    text = str(value or "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        pass
    try:
        from datetime import datetime

        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _path_has_bmp_header(path: Path) -> bool:
    try:
        return path.read_bytes()[:2] == b"BM"
    except OSError:
        return False


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


__all__ = [
    "capture_pre_run_artifact_stats",
    "check_expected_artifact",
    "check_expected_artifacts",
]
