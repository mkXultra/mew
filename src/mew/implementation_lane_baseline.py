"""M6.16 implementation-lane baseline reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .metrics import build_observation_metrics
from .mew_first_calibration import summarize_mew_first_calibration
from .side_project_dogfood import DEFAULT_LEDGER_PATH, summarize_side_project_dogfood


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _int(value: Any) -> int:
    number = _number(value)
    if number is None:
        return 0
    return int(number)


def _rate(numerator: int | float | None, denominator: int | float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(float(numerator) / float(denominator), 3)


def _first_edit_latency(observation_metrics: Mapping[str, Any]) -> dict[str, Any]:
    self_hosting = _mapping(observation_metrics.get("self_hosting"))
    first_edit = _mapping(self_hosting.get("first_edit_proposal_seconds"))
    return {
        "count": _int(first_edit.get("count")),
        "median": _number(first_edit.get("median")),
        "p95": _number(first_edit.get("p95")),
        "max": _number(first_edit.get("max")),
    }


def _recommend_first_bottleneck(summary: Mapping[str, Any]) -> dict[str, Any]:
    mew_first = _mapping(summary.get("mew_first"))
    approval = _mapping(summary.get("approval"))
    verifier = _mapping(summary.get("verifier"))
    first_edit = _mapping(summary.get("first_edit_latency"))
    side_project = _mapping(summary.get("side_project"))

    candidates = [
        (
            "mew_first_rescue_partial",
            _int(mew_first.get("rescue_partial_count")),
            "recent mew-first attempts still require partial or supervisor rescue",
        ),
        (
            "approval_rejections",
            _int(approval.get("rejected")),
            "implementation drafts are still being rejected by the reviewer gate",
        ),
        (
            "verifier_failures",
            _int(verifier.get("failed")),
            "verification failures need an explicit retry or repair path",
        ),
        (
            "first_edit_latency",
            _number(first_edit.get("p95")) if (_number(first_edit.get("p95")) or 0.0) > 300.0 else 0,
            "first edit proposal latency is too slow for ordinary coding tasks",
        ),
        (
            "side_project_structural_repairs",
            _int(side_project.get("structural_repairs_required")),
            "side-project dogfood exposed structural implementation-lane repairs",
        ),
    ]
    for name, value, reason in candidates:
        if value:
            return {"name": name, "value": value, "reason": reason}
    return {"name": "none_measured", "value": 0, "reason": "no non-zero implementation-lane bottleneck was measured"}


def summarize_implementation_lane_baseline_from_summaries(
    *,
    mew_first_summary: Mapping[str, Any],
    observation_metrics: Mapping[str, Any],
    side_project_summary: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a read-only M6.16 baseline from existing telemetry summaries."""

    mew_first_gate = _mapping(mew_first_summary.get("gate"))
    mew_first_counts = _mapping(mew_first_summary.get("counts"))
    result_counts = _mapping(mew_first_counts.get("result_class"))
    drift_counts = _mapping(mew_first_counts.get("drift_class"))
    rejected_patch_counts = _mapping(mew_first_counts.get("rejected_patch_family"))
    gate_blocker_counts = _mapping(mew_first_gate.get("gate_blocker_result_class_counts"))
    attempts_total = _int(mew_first_summary.get("attempts_total"))
    partial_count = _int(result_counts.get("partial_mew_first"))
    supervisor_rescue_count = sum(
        _int(result_counts.get(result_class))
        for result_class in ("supervisor_rescue", "supervisor_owned", "supervisor_owned_or_unknown")
    )
    rescue_partial_count = partial_count + supervisor_rescue_count

    reliability = _mapping(observation_metrics.get("reliability"))
    approvals = _mapping(reliability.get("approvals"))
    verification = _mapping(reliability.get("verification"))
    approval_total = _int(approvals.get("total"))
    approval_rejected = _int(approvals.get("rejected"))
    verifier_total = _int(verification.get("total"))
    verifier_failed = _int(verification.get("failed"))

    side_gate = _mapping(side_project_summary.get("gate"))
    side_rows_total = _int(side_project_summary.get("rows_total"))
    side_success = _int(side_gate.get("clean_or_practical"))
    side_rescue_edits = _int(side_gate.get("rescue_edits_total"))

    summary: dict[str, Any] = {
        "kind": "implementation_lane_baseline",
        "schema_version": 1,
        "mew_first": {
            "attempts_total": attempts_total,
            "clean_or_practical_successes": _int(mew_first_gate.get("clean_or_practical_successes")),
            "success_rate": mew_first_gate.get("success_rate"),
            "success_gap": _int(mew_first_gate.get("success_gap")),
            "partial_count": partial_count,
            "supervisor_rescue_count": supervisor_rescue_count,
            "rescue_partial_count": rescue_partial_count,
            "rescue_partial_rate": _rate(rescue_partial_count, attempts_total),
            "gate_blocking_task_ids": mew_first_gate.get("gate_blocking_task_ids") or [],
            "failure_classes": {
                "result_class": dict(result_counts),
                "gate_blocker_result_class": dict(gate_blocker_counts),
                "drift_class": dict(drift_counts),
                "rejected_patch_family": dict(rejected_patch_counts),
            },
        },
        "approval": {
            "total": approval_total,
            "rejected": approval_rejected,
            "rejection_rate": _rate(approval_rejected, approval_total),
        },
        "verifier": {
            "total": verifier_total,
            "failed": verifier_failed,
            "failure_rate": _rate(verifier_failed, verifier_total),
        },
        "first_edit_latency": _first_edit_latency(observation_metrics),
        "side_project": {
            "ledger_path": side_project_summary.get("ledger_path"),
            "rows_total": side_rows_total,
            "clean_or_practical": side_success,
            "success_rate": side_gate.get("success_rate"),
            "failed": _int(side_gate.get("failed")),
            "structural_repairs_required": _int(side_gate.get("structural_repairs_required")),
            "rescue_edits_total": side_rescue_edits,
            "rescue_rate": _rate(side_rescue_edits, side_rows_total),
        },
    }
    summary["recommended_first_bottleneck"] = _recommend_first_bottleneck(summary)
    return summary


def summarize_implementation_lane_baseline(
    *,
    state: Mapping[str, Any],
    source_path: str | Path = "ROADMAP_STATUS.md",
    limit: int = 10,
    sample_limit: int = 3,
    side_project_ledger_path: str | Path | None = None,
) -> dict[str, Any]:
    """Summarize the current implementation lane from existing read-only data."""

    mew_first_summary = summarize_mew_first_calibration(source_path=source_path, limit=limit)
    observation_metrics = build_observation_metrics(
        state,
        kind="coding",
        limit=limit,
        sample_limit=sample_limit,
    )
    ledger_path = side_project_ledger_path or DEFAULT_LEDGER_PATH
    side_project_summary = summarize_side_project_dogfood(path=ledger_path, limit=limit)
    summary = summarize_implementation_lane_baseline_from_summaries(
        mew_first_summary=mew_first_summary,
        observation_metrics=observation_metrics,
        side_project_summary=side_project_summary,
    )
    summary["inputs"] = {
        "source_path": str(source_path),
        "limit": limit,
        "sample_limit": sample_limit,
        "observation_kind": "coding",
        "side_project_ledger_path": str(ledger_path),
    }
    return summary


def format_implementation_lane_baseline_report(summary: Mapping[str, Any]) -> str:
    inputs = _mapping(summary.get("inputs"))
    mew_first = _mapping(summary.get("mew_first"))
    approval = _mapping(summary.get("approval"))
    verifier = _mapping(summary.get("verifier"))
    first_edit = _mapping(summary.get("first_edit_latency"))
    side_project = _mapping(summary.get("side_project"))
    recommendation = _mapping(summary.get("recommended_first_bottleneck"))
    lines = [
        "Implementation-lane baseline",
        f"source: {inputs.get('source_path')}",
        (
            "mew_first: "
            f"success={mew_first.get('clean_or_practical_successes')}/{mew_first.get('attempts_total')} "
            f"rescue_partial={mew_first.get('rescue_partial_count')} "
            f"rescue_partial_rate={mew_first.get('rescue_partial_rate')} "
            f"success_gap={mew_first.get('success_gap')}"
        ),
        (
            "approval: "
            f"rejected={approval.get('rejected')}/{approval.get('total')} "
            f"rejection_rate={approval.get('rejection_rate')}"
        ),
        f"failure_classes: {mew_first.get('failure_classes')}",
        (
            "verifier: "
            f"failed={verifier.get('failed')}/{verifier.get('total')} "
            f"failure_rate={verifier.get('failure_rate')}"
        ),
        (
            "first_edit_latency: "
            f"count={first_edit.get('count')} median={first_edit.get('median')} "
            f"p95={first_edit.get('p95')} max={first_edit.get('max')}"
        ),
        (
            "side_project: "
            f"rows={side_project.get('rows_total')} "
            f"success={side_project.get('clean_or_practical')} "
            f"success_rate={side_project.get('success_rate')} "
            f"failed={side_project.get('failed')} "
            f"structural_repairs={side_project.get('structural_repairs_required')} "
            f"rescue_edits={side_project.get('rescue_edits_total')} "
            f"rescue_rate={side_project.get('rescue_rate')}"
        ),
        (
            "recommended_first_bottleneck: "
            f"{recommendation.get('name')} value={recommendation.get('value')} "
            f"reason={recommendation.get('reason')}"
        ),
    ]
    return "\n".join(lines)
