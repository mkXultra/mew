"""Artifact and failure helpers for memory evaluation runs."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .hashing import stable_hash, without_keys


ARTIFACT_SCHEMA_VERSION = "memory_eval_artifact.v1"
FAILURE_FIELDS = {
    "failure_id",
    "stage",
    "severity",
    "type",
    "message",
    "request_id",
    "operation_id",
    "evidence_id",
    "gate_id",
    "metric_id",
    "expected",
    "actual",
    "adapter_status",
    "retry_count",
    "hash",
}


def make_failure(
    *,
    stage: str,
    type: str,
    message: str,
    request_id: str | None = None,
    operation_id: str | None = None,
    evidence_id: str | None = None,
    gate_id: str | None = None,
    metric_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    adapter_status: str = "success",
    severity: str = "error",
    retry_count: int = 0,
    failure_id: str | None = None,
) -> dict[str, Any]:
    seed = {
        "stage": stage,
        "type": type,
        "request_id": request_id,
        "operation_id": operation_id,
        "evidence_id": evidence_id,
        "gate_id": gate_id,
        "metric_id": metric_id,
        "expected": expected,
        "actual": actual,
    }
    failure = {
        "failure_id": failure_id or _failure_id(seed),
        "stage": stage,
        "severity": severity,
        "type": type,
        "message": message,
        "request_id": request_id,
        "operation_id": operation_id,
        "evidence_id": evidence_id,
        "gate_id": gate_id,
        "metric_id": metric_id,
        "expected": expected,
        "actual": actual,
        "adapter_status": adapter_status,
        "retry_count": retry_count,
        "hash": None,
    }
    failure["hash"] = stable_hash(without_keys(failure, {"hash"}))
    return failure


def gate_result(gate_id: str, passed: bool, reason: str) -> dict[str, Any]:
    return {"gate_id": gate_id, "passed": bool(passed), "reason": reason}


def write_artifact(path: str | Path, artifact: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _failure_id(seed: Mapping[str, Any]) -> str:
    request = _safe_id(seed.get("request_id") or seed.get("operation_id") or "run")
    kind = _safe_id(seed.get("type") or "failure")
    suffix = stable_hash(seed).split(":", 1)[1][:12]
    return f"fail_{request}_{kind}_{suffix}"


def _safe_id(value: Any) -> str:
    text = str(value or "none").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "none"
