"""Default-switch gate for implement_v2 tool-surface profiles."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from statistics import median

from .tool_registry import CODEX_HOT_PATH_PROFILE_ID, MEW_LEGACY_PROFILE_ID

DEFAULT_SWITCH_GATE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ToolSurfaceDefaultSwitchGateResult:
    status: str
    can_switch_default: bool
    reasons: tuple[str, ...]
    metrics: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": DEFAULT_SWITCH_GATE_SCHEMA_VERSION,
            "gate": "tool_surface_default_switch",
            "status": self.status,
            "can_switch_default": self.can_switch_default,
            "reasons": list(self.reasons),
            "metrics": dict(self.metrics),
        }


def evaluate_tool_surface_default_switch_gate(
    reports: Iterable[Mapping[str, object] | object],
    *,
    reviewer_accepted: bool = False,
    fixed_ab_set_id: str = "",
    min_pair_count: int = 1,
    visible_bytes_safety_reason: str = "",
) -> ToolSurfaceDefaultSwitchGateResult:
    """Evaluate whether `codex_hot_path` may become the default profile."""

    normalized = tuple(_report_dict(report) for report in reports)
    pairs = tuple(_pair_rows(report) for report in normalized if _pair_rows(report) is not None)
    baseline_rows = tuple(pair[0] for pair in pairs)
    candidate_rows = tuple(pair[1] for pair in pairs)
    reasons: list[str] = []

    if not fixed_ab_set_id:
        reasons.append("fixed_ab_set_id_required")
    if len(pairs) < min_pair_count:
        reasons.append("not_enough_comparable_ab_pairs")
    if any(report.get("ab_comparable") is not True for report in normalized):
        reasons.append("all_reports_must_be_ab_comparable")
    if any(report.get("default_switch_evidence_included") is not True for report in normalized):
        reasons.append("all_reports_must_be_included_as_default_switch_evidence")
    if not reviewer_accepted:
        reasons.append("reviewer_acceptance_required")

    if candidate_rows:
        if any(row.get("provider_visible_forbidden_scan_ok") is not True for row in candidate_rows):
            reasons.append("candidate_provider_visible_forbidden_scan_failed")
        if any(row.get("hidden_steering_markers") for row in candidate_rows):
            reasons.append("candidate_hidden_steering_markers_present")
        if any(row.get("render_leak_ok") is not True for row in candidate_rows):
            reasons.append("candidate_render_leak_failed")
        if any(row.get("every_call_has_exactly_one_output") is not True for row in candidate_rows):
            reasons.append("candidate_pairing_failed")
        if any(_proof_replay_ok(row) is not True for row in candidate_rows):
            reasons.append("candidate_proof_replay_failed")
        if any(row.get("verifier_evidence_preserved") is not True for row in candidate_rows):
            reasons.append("candidate_verifier_evidence_not_preserved")
        if any(_successful(row) and _adapter_or_capability_failure_count(row) > 0 for row in candidate_rows):
            reasons.append("candidate_write_stdin_or_adapter_limitation_in_successful_trace")
    else:
        reasons.append("candidate_rows_missing")

    if baseline_rows and candidate_rows:
        baseline_success = _success_rate(baseline_rows)
        candidate_success = _success_rate(candidate_rows)
        if candidate_success < baseline_success:
            reasons.append("candidate_success_rate_worse_than_baseline")
        baseline_acceptance = _acceptance_rate(baseline_rows)
        candidate_acceptance = _acceptance_rate(candidate_rows)
        if candidate_acceptance < baseline_acceptance:
            reasons.append("candidate_acceptance_rate_worse_than_baseline")
        baseline_zero_write_timeout = _zero_write_timeout_rate(baseline_rows)
        candidate_zero_write_timeout = _zero_write_timeout_rate(candidate_rows)
        if candidate_zero_write_timeout > baseline_zero_write_timeout:
            reasons.append("candidate_zero_write_timeout_rate_worse_than_baseline")
        if any(
            _has_numeric((baseline_row,), "first_write_turn")
            and not _has_numeric((candidate_row,), "first_write_turn")
            for baseline_row, candidate_row in pairs
        ):
            reasons.append("candidate_first_write_evidence_missing")
        if _median(candidate_rows, "first_write_turn") > _median(baseline_rows, "first_write_turn"):
            reasons.append("candidate_first_write_median_worse_than_baseline")
        if _p95(candidate_rows, "first_write_turn") > _p95(baseline_rows, "first_write_turn"):
            reasons.append("candidate_first_write_p95_worse_than_baseline")
        candidate_probe = _median(candidate_rows, "probe_count_before_first_write")
        baseline_probe = _median(baseline_rows, "probe_count_before_first_write")
        if candidate_probe > baseline_probe and candidate_success <= baseline_success:
            reasons.append("candidate_probe_count_worse_without_success_gain")
        if _median_latency(candidate_rows, "failed_verifier_to_next_edit_latency") > _median_latency(
            baseline_rows,
            "failed_verifier_to_next_edit_latency",
        ):
            reasons.append("candidate_failed_verifier_to_next_edit_latency_worse")
        if any(_failed_verifier_without_next_edit(row) for row in candidate_rows):
            reasons.append("candidate_failed_verifier_without_next_edit")
        candidate_visible_bytes = _visible_bytes(candidate_rows)
        baseline_visible_bytes = _visible_bytes(baseline_rows)
        if candidate_visible_bytes > baseline_visible_bytes and not visible_bytes_safety_reason:
            reasons.append("candidate_visible_bytes_higher_without_safety_reason")
    else:
        baseline_success = 0.0
        candidate_success = 0.0
        baseline_acceptance = 0.0
        candidate_acceptance = 0.0
        baseline_zero_write_timeout = 0.0
        candidate_zero_write_timeout = 0.0
        baseline_visible_bytes = 0
        candidate_visible_bytes = 0

    unique_reasons = tuple(dict.fromkeys(reasons))
    can_switch = not unique_reasons
    metrics = {
        "fixed_ab_set_id": fixed_ab_set_id,
        "report_count": len(normalized),
        "pair_count": len(pairs),
        "min_pair_count": min_pair_count,
        "reviewer_accepted": bool(reviewer_accepted),
        "baseline_success_rate": baseline_success,
        "candidate_success_rate": candidate_success,
        "baseline_acceptance_rate": baseline_acceptance,
        "candidate_acceptance_rate": candidate_acceptance,
        "baseline_zero_write_timeout_rate": baseline_zero_write_timeout,
        "candidate_zero_write_timeout_rate": candidate_zero_write_timeout,
        "baseline_visible_bytes": baseline_visible_bytes,
        "candidate_visible_bytes": candidate_visible_bytes,
        "visible_bytes_safety_reason": visible_bytes_safety_reason,
    }
    return ToolSurfaceDefaultSwitchGateResult(
        status="ready" if can_switch else "blocked",
        can_switch_default=can_switch,
        reasons=unique_reasons,
        metrics=metrics,
    )


def load_tool_surface_ab_reports(paths: Iterable[object]) -> tuple[dict[str, object], ...]:
    """Load A/B report JSON files for the default-switch gate."""

    reports = []
    for raw_path in paths:
        path = Path(str(raw_path)).expanduser()
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, Mapping):
            raise ValueError(f"expected A/B report object: {path}")
        reports.append(dict(data))
    return tuple(reports)


def _report_dict(report: Mapping[str, object] | object) -> dict[str, object]:
    return dict(report) if isinstance(report, Mapping) else {}


def _pair_rows(report: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]] | None:
    if report.get("ab_comparable") is not True or report.get("default_switch_evidence_included") is not True:
        return None
    rows = [dict(row) for row in report.get("rows") or [] if isinstance(row, Mapping)]
    by_profile = {str(row.get("profile_id") or ""): row for row in rows}
    baseline = by_profile.get(MEW_LEGACY_PROFILE_ID)
    candidate = by_profile.get(CODEX_HOT_PATH_PROFILE_ID)
    if baseline is None or candidate is None:
        return None
    return baseline, candidate


def _successful(row: Mapping[str, object]) -> bool:
    return str(row.get("lane_status") or "").casefold() == "completed"


def _accepted(row: Mapping[str, object]) -> bool:
    return str(row.get("accepted_finish_status") or "").casefold() == "accepted"


def _success_rate(rows: tuple[dict[str, object], ...]) -> float:
    return _rate(rows, predicate=_successful)


def _acceptance_rate(rows: tuple[dict[str, object], ...]) -> float:
    return _rate(rows, predicate=_accepted)


def _rate(rows: tuple[dict[str, object], ...], *, predicate) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if predicate(row)) / len(rows)


def _proof_replay_ok(row: Mapping[str, object]) -> bool:
    status = row.get("proof_replay_status")
    if not isinstance(status, Mapping):
        return False
    return (
        status.get("proof_manifest_present") is True
        and status.get("transcript_hash_matches_manifest") is True
        and status.get("evidence_observation_present") is True
    )


def _adapter_or_capability_failure_count(row: Mapping[str, object]) -> int:
    return int(row.get("argument_adapter_failure_count") or 0) + int(row.get("unsupported_capability_count") or 0)


def _zero_write_timeout_rate(rows: tuple[dict[str, object], ...]) -> float:
    if not rows:
        return 0.0
    count = 0
    for row in rows:
        status = str(row.get("lane_status") or "").casefold()
        mutation_count = int(row.get("mutation_count") or 0)
        timeout_like = "timeout" in status or "budget" in status or row.get("zero_write_timeout") is True
        if mutation_count == 0 and timeout_like:
            count += 1
    return count / len(rows)


def _median(rows: tuple[dict[str, object], ...], key: str) -> float:
    values = _numeric_values(rows, key)
    if not values:
        return 0.0
    return float(median(values))


def _p95(rows: tuple[dict[str, object], ...], key: str) -> float:
    values = sorted(_numeric_values(rows, key))
    if not values:
        return 0.0
    index = min(len(values) - 1, int(round((len(values) - 1) * 0.95)))
    return float(values[index])


def _median_latency(rows: tuple[dict[str, object], ...], key: str) -> float:
    values = []
    for row in rows:
        latency = row.get(key)
        if isinstance(latency, Mapping):
            value = latency.get("latency_turns")
            if value not in (None, ""):
                values.append(float(value))
    if not values:
        return 0.0
    return float(median(values))


def _numeric_values(rows: tuple[dict[str, object], ...], key: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(key)
        if value in (None, ""):
            continue
        values.append(float(value))
    return values


def _has_numeric(rows: tuple[dict[str, object], ...], key: str) -> bool:
    return bool(_numeric_values(rows, key))


def _failed_verifier_without_next_edit(row: Mapping[str, object]) -> bool:
    latency = row.get("failed_verifier_to_next_edit_latency")
    if not isinstance(latency, Mapping):
        return False
    return bool(latency.get("failed_verifier_call_id")) and not bool(latency.get("next_edit_call_id"))


def _visible_bytes(rows: tuple[dict[str, object], ...]) -> int:
    return sum(
        int(row.get("provider_visible_output_bytes") or 0)
        + int(row.get("provider_visible_schema_bytes") or 0)
        + int(row.get("provider_request_inventory_bytes") or 0)
        for row in rows
    )


__all__ = [
    "DEFAULT_SWITCH_GATE_SCHEMA_VERSION",
    "ToolSurfaceDefaultSwitchGateResult",
    "evaluate_tool_surface_default_switch_gate",
    "load_tool_surface_ab_reports",
]
