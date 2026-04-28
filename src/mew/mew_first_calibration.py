"""M6.10 mew-first implementation calibration economics."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

DEFAULT_MILESTONE_STATUS_PATH = Path("ROADMAP_STATUS.md")
SUCCESS_CLASSES = frozenset({"clean_mew_first", "practical_mew_first"})
DEFAULT_ATTEMPT_SECTION_HEADINGS = ("### M6.9:", "### M6.10:", "### M6.16:")
STRUCTURAL_DRIFT_CLASSES = frozenset(
    {
        "task_goal_substitution",
        "synthetic_schema_substitution",
        "wrong_target_substitution",
        "cached_window_integrity",
    }
)
STRUCTURAL_REJECTED_PATCH_FAMILIES = frozenset(
    {
        "task_goal_substitution",
        "synthetic_schema_substitution",
        "unpaired_source_edit",
    }
)


@dataclass(frozen=True)
class MewFirstAttempt:
    task_id: int
    result_class: str
    patch_owner: str
    autonomy_credit: str
    drift_class: str
    rejected_patch_family: str
    verifier_status: str
    failure_scope: str
    failure_scope_confidence: str
    diagnosis_signals: tuple[str, ...]
    recommended_route: str
    structural_reason: str
    source_excerpt: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "result_class": self.result_class,
            "patch_owner": self.patch_owner,
            "autonomy_credit": self.autonomy_credit,
            "drift_class": self.drift_class,
            "rejected_patch_family": self.rejected_patch_family,
            "verifier_status": self.verifier_status,
            "failure_scope": self.failure_scope,
            "failure_scope_confidence": self.failure_scope_confidence,
            "diagnosis_signals": list(self.diagnosis_signals),
            "recommended_route": self.recommended_route,
            "structural_reason": self.structural_reason,
            "source_excerpt": self.source_excerpt,
        }


def _milestone_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start < 0:
        return ""
    next_heading = text.find("\n### ", start + len(heading))
    if next_heading < 0:
        return text[start:]
    return text[start:next_heading]


def _milestone_sections(text: str, headings: Iterable[str] = DEFAULT_ATTEMPT_SECTION_HEADINGS) -> Iterable[str]:
    found = []
    for heading in headings:
        start = text.find(heading)
        if start >= 0:
            found.append((start, _milestone_section(text, heading)))
    if not found:
        yield text
        return
    for _, section in sorted(found, key=lambda item: item[0]):
        if section:
            yield section


def _bullet_blocks(text: str) -> Iterable[str]:
    current: list[str] = []
    for line in text.splitlines():
        if line.startswith("- "):
            if current:
                yield "\n".join(current).strip()
            current = [line]
        elif current and (line.startswith("  ") or not line.strip()):
            current.append(line)
        elif current:
            yield "\n".join(current).strip()
            current = []
    if current:
        yield "\n".join(current).strip()


def _task_id(block: str) -> int | None:
    match = re.search(r"`#(\d+)`|#(\d+)", block)
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _has_attempt_entry_prefix(block: str) -> bool:
    first_line = next((line for line in block.splitlines() if line.strip()), "")
    first_line = _norm(first_line)
    return (
        re.match(r"^- (?:task|follow-up) `?#\d+`?(?:\s|$)", first_line) is not None
        or re.match(r"^- #\d+(?:\s|$)", first_line) is not None
        or re.match(r"^- retry after `?#\d+`?(?:\s|$)", first_line) is not None
    )


def _is_attempt_block(block: str) -> bool:
    lowered = _norm(block)
    if "substrate repair" in lowered or "write-ready refresh repair" in lowered:
        return False
    if not _has_attempt_entry_prefix(block):
        return False
    return any(
        marker in lowered
        for marker in (
            "mew-first",
            "supervisor",
            "rescue",
            "drifted",
            "validation covered",
            "implementation evidence",
            "product progress",
        )
    )


def _result_class(block: str) -> str:
    lowered = _norm(block)
    if "mixed mew-first" in lowered or "partial autonomy" in lowered:
        return "partial_mew_first"
    if "supervisor-rescue" in lowered or "supervisor rescued" in lowered:
        return "supervisor_rescue"
    if "supervisor-owned" in lowered:
        return "supervisor_owned"
    if "not mew-first" in lowered or "not autonomy credit" in lowered:
        return "supervisor_rescue"

    has_mew_first = "mew-first" in lowered
    has_no_supervisor_product_rescue = (
        "without supervisor product-code rescue" in lowered
        or "no supervisor product-code rescue" in lowered
    )
    reviewer_mediated_repair = (
        (
            "review found" in lowered
            or "reviewer found" in lowered
            or "codex-ultra review found" in lowered
        )
        and ("repaired" in lowered or "repair" in lowered)
    ) or (
        "re-review reported no findings" in lowered
        and ("repaired" in lowered or "repair" in lowered)
    )
    explicit_practical_credit = (
        "practical mew-first" in lowered
        or "practical mew first" in lowered
        or "practical autonomy" in lowered
    )
    if (
        has_mew_first
        and has_no_supervisor_product_rescue
        and (reviewer_mediated_repair or explicit_practical_credit)
    ):
        return "practical_mew_first"
    if has_mew_first and "without rescue edits" in lowered:
        if reviewer_mediated_repair and explicit_practical_credit:
            return "practical_mew_first"
        if (
            "reviewer steer" in lowered
            or "steer was needed" in lowered
            or "stale-session" in lowered
            or "restarted" in lowered
            or "restart" in lowered
        ):
            return "practical_mew_first"
        return "clean_mew_first"
    if "bounded mew-first implementation evidence" in lowered:
        return "practical_mew_first"
    if has_mew_first:
        return "partial_mew_first"
    return "supervisor_owned_or_unknown"


def _patch_owner(result_class: str) -> str:
    if result_class in SUCCESS_CLASSES:
        return "mew"
    if result_class == "partial_mew_first":
        return "mixed"
    return "supervisor"


def _autonomy_credit(result_class: str) -> str:
    if result_class == "clean_mew_first":
        return "clean"
    if result_class == "practical_mew_first":
        return "practical"
    if result_class == "partial_mew_first":
        return "partial"
    return "none"


def _drift_class(block: str) -> str:
    lowered = _norm(block)
    if "task-goal" in lowered or "task goal" in lowered:
        return "task_goal_substitution"
    if "synthetic_schema_substitution" in lowered or "synthetic-schema" in lowered:
        return "synthetic_schema_substitution"
    if "m6.11-only artifact tweak" in lowered:
        return "wrong_milestone_artifact_tweak"
    if "symbol-index-hit" in lowered and "artifact tweak" in lowered:
        return "existing_scenario_artifact_tweak"
    if "wrong-target" in lowered or "wrong target" in lowered:
        return "wrong_target_substitution"
    if "generic dogfood cleanup" in lowered or "generic cleanup" in lowered:
        return "generic_cleanup_substitution"
    if "runtime-focus summary" in lowered:
        return "unrelated_runtime_focus_summary"
    if "test-only assertion" in lowered:
        return "unrelated_test_only_assertion"
    if "stale session" in lowered or "stale-session" in lowered:
        return "stale_session_context"
    if "transient empty model response" in lowered:
        return "transient_model_empty_response"
    if "cached_window_incomplete" in lowered or "missing_exact_cached_window" in lowered:
        return "cached_window_integrity"
    return "none_observed"


def _rejected_patch_family(block: str) -> str:
    lowered = _norm(block)
    if "task-goal" in lowered or "task goal" in lowered:
        return "task_goal_substitution"
    if "synthetic_schema_substitution" in lowered or "synthetic-schema" in lowered:
        return "synthetic_schema_substitution"
    if "reviewer-rejected patch" in lowered or "reviewer rejected patch" in lowered:
        return "reviewer_rejected_patch"
    if "existing-scenario artifact tweak" in lowered or "artifact tweak" in lowered:
        return "existing_scenario_artifact_tweak"
    if "generic dogfood cleanup" in lowered or "generic cleanup" in lowered:
        return "generic_cleanup"
    if "unpaired-source-edit" in lowered or "unpaired source edit" in lowered:
        return "unpaired_source_edit"
    if "missing focused verifier" in lowered:
        return "missing_focused_verifier"
    if "test-only assertion" in lowered:
        return "test_only_patch"
    return "none_recorded"


def _verifier_status(block: str) -> str:
    lowered = _norm(block)
    if (
        "validation covered" in lowered
        or "validation passed" in lowered
        or "valid proof passed" in lowered
        or "verification passed" in lowered
    ):
        return "passed"
    if "focused verifier" in lowered and "passed" in lowered:
        return "passed"
    return "unknown"


def _diagnosis_signals(
    *,
    block: str,
    result_class: str,
    drift_class: str,
    rejected_patch_family: str,
    verifier_status: str,
) -> tuple[str, ...]:
    lowered = _norm(block)
    signals: list[str] = []
    if drift_class != "none_observed":
        signals.append(drift_class)
    if rejected_patch_family != "none_recorded" and rejected_patch_family not in signals:
        signals.append(rejected_patch_family)
    if result_class in {"supervisor_rescue", "supervisor_owned", "supervisor_owned_or_unknown"}:
        signals.append("supervisor_product_rescue_required")
    if result_class == "partial_mew_first":
        signals.append("partial_autonomy")
    if verifier_status != "passed" and result_class not in SUCCESS_CLASSES:
        signals.append("verifier_not_proven")
    if "reviewer steer" in lowered or "steer was needed" in lowered:
        signals.append("reviewer_steer_required")
    if "reviewer rejected" in lowered or "reviewer-rejected" in lowered:
        signals.append("reviewer_rejection")
    if "no patch artifact" in lowered or "missing patch artifact" in lowered:
        signals.append("missing_patch_artifact")
    if "lost retry frontier" in lowered or "lost the retry frontier" in lowered:
        signals.append("lost_retry_frontier")
    if "invalid task verifier" in lowered or "invalid verifier" in lowered:
        signals.append("invalid_task_spec")
    if "transient empty model response" in lowered or "timeout" in lowered or "quota" in lowered:
        signals.append("transient_model")
    deduped: list[str] = []
    for signal in signals:
        if signal not in deduped:
            deduped.append(signal)
    return tuple(deduped)


def _diagnose_failure_scope(
    *,
    result_class: str,
    drift_class: str,
    rejected_patch_family: str,
    verifier_status: str,
    signals: tuple[str, ...],
) -> tuple[str, str, str, str]:
    """Return failure_scope, confidence, recommended_route, structural_reason."""

    signal_set = set(signals)
    structural_reason = ""
    for candidate in (
        drift_class,
        rejected_patch_family,
        "missing_patch_artifact",
        "lost_retry_frontier",
        "supervisor_product_rescue_required",
    ):
        if (
            candidate in STRUCTURAL_DRIFT_CLASSES
            or candidate in STRUCTURAL_REJECTED_PATCH_FAMILIES
            or candidate in signal_set
            and candidate in {"missing_patch_artifact", "lost_retry_frontier", "supervisor_product_rescue_required"}
        ):
            structural_reason = candidate
            break

    if "invalid_task_spec" in signal_set or rejected_patch_family == "missing_focused_verifier":
        return "invalid_task_spec", "high", "fix_task_spec_then_retry", ""
    if "transient_model" in signal_set or drift_class == "transient_model_empty_response":
        return "transient_model", "high", "retry_same_task", ""
    if structural_reason and result_class not in SUCCESS_CLASSES:
        return "structural", "high", "m6_14_repair", structural_reason
    if result_class == "partial_mew_first":
        return "ambiguous", "medium", "collect_replay_or_reviewer_evidence", structural_reason
    if result_class in SUCCESS_CLASSES:
        if "reviewer_steer_required" in signal_set or "reviewer_rejection" in signal_set:
            return "polish", "medium", "same_task_retry_if_repeated", ""
        return "none_observed", "high", "no_action", ""
    if structural_reason:
        return "structural", "medium", "m6_14_repair", structural_reason
    if verifier_status != "passed":
        return "ambiguous", "medium", "collect_replay_or_reviewer_evidence", ""
    return "ambiguous", "low", "collect_replay_or_reviewer_evidence", ""


def _excerpt(block: str, *, limit: int = 220) -> str:
    compact = " ".join(line.strip() for line in block.splitlines())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def extract_mew_first_attempts(text: str, *, limit: int = 10) -> list[MewFirstAttempt]:
    attempts: list[MewFirstAttempt] = []
    for section in _milestone_sections(text):
        for block in _bullet_blocks(section):
            task_id = _task_id(block)
            if task_id is None or not _is_attempt_block(block):
                continue
            result_class = _result_class(block)
            drift_class = _drift_class(block)
            rejected_patch_family = _rejected_patch_family(block)
            verifier_status = _verifier_status(block)
            diagnosis_signals = _diagnosis_signals(
                block=block,
                result_class=result_class,
                drift_class=drift_class,
                rejected_patch_family=rejected_patch_family,
                verifier_status=verifier_status,
            )
            failure_scope, confidence, recommended_route, structural_reason = _diagnose_failure_scope(
                result_class=result_class,
                drift_class=drift_class,
                rejected_patch_family=rejected_patch_family,
                verifier_status=verifier_status,
                signals=diagnosis_signals,
            )
            attempts.append(
                MewFirstAttempt(
                    task_id=task_id,
                    result_class=result_class,
                    patch_owner=_patch_owner(result_class),
                    autonomy_credit=_autonomy_credit(result_class),
                    drift_class=drift_class,
                    rejected_patch_family=rejected_patch_family,
                    verifier_status=verifier_status,
                    failure_scope=failure_scope,
                    failure_scope_confidence=confidence,
                    diagnosis_signals=diagnosis_signals,
                    recommended_route=recommended_route,
                    structural_reason=structural_reason,
                    source_excerpt=_excerpt(block),
                )
            )
    return sorted(attempts, key=lambda attempt: attempt.task_id, reverse=True)[:limit]


def summarize_mew_first_calibration(
    *,
    source_path: str | Path = DEFAULT_MILESTONE_STATUS_PATH,
    limit: int = 10,
    gate_success_threshold: int = 7,
) -> dict[str, Any]:
    path = Path(source_path)
    text = path.read_text(encoding="utf-8")
    attempts = extract_mew_first_attempts(text, limit=limit)
    result_counts = Counter(attempt.result_class for attempt in attempts)
    drift_counts = Counter(attempt.drift_class for attempt in attempts)
    rejected_counts = Counter(attempt.rejected_patch_family for attempt in attempts)
    failure_scope_counts = Counter(attempt.failure_scope for attempt in attempts)
    structural_reason_counts = Counter(
        attempt.structural_reason for attempt in attempts if attempt.structural_reason
    )
    recommended_route_counts = Counter(attempt.recommended_route for attempt in attempts)
    gate_success_task_ids = [
        attempt.task_id
        for attempt in attempts
        if attempt.result_class in SUCCESS_CLASSES
    ]
    clean_or_practical = len(gate_success_task_ids)
    gate_blocking_task_ids = [
        attempt.task_id
        for attempt in attempts
        if attempt.result_class not in SUCCESS_CLASSES
    ]
    gate_blocker_result_class_counts = Counter(
        attempt.result_class
        for attempt in attempts
        if attempt.result_class not in SUCCESS_CLASSES
    )
    section_headings = [
        heading
        for _, heading in sorted(
            (text.find(heading), heading)
            for heading in DEFAULT_ATTEMPT_SECTION_HEADINGS
            if text.find(heading) >= 0
        )
    ]
    total = len(attempts)
    return {
        "kind": "mew_first_calibration",
        "schema_version": 1,
        "source_path": str(path),
        "limit": limit,
        "included_attempt_sections": section_headings,
        "attempts_total": total,
        "attempt_window_task_ids": [attempt.task_id for attempt in attempts],
        "gate": {
            "success_threshold": gate_success_threshold,
            "clean_or_practical_successes": clean_or_practical,
            "success_gap": max(0, gate_success_threshold - clean_or_practical),
            "success_rate": round(clean_or_practical / total, 3) if total else None,
            "gate_success_task_ids": gate_success_task_ids,
            "gate_blocking_task_ids": gate_blocking_task_ids,
            "gate_blocker_result_class_counts": dict(gate_blocker_result_class_counts),
            "passed": total >= limit and clean_or_practical >= gate_success_threshold,
        },
        "counts": {
            "result_class": dict(result_counts),
            "drift_class": dict(drift_counts),
            "rejected_patch_family": dict(rejected_counts),
            "failure_scope": dict(failure_scope_counts),
            "structural_reason": dict(structural_reason_counts),
            "recommended_route": dict(recommended_route_counts),
        },
        "attempts": [attempt.as_dict() for attempt in attempts],
    }


def format_mew_first_calibration_report(summary: Mapping[str, Any]) -> str:
    gate = summary.get("gate") or {}
    counts = summary.get("counts") or {}
    result_counts = counts.get("result_class") or {}
    included_sections = summary.get("included_attempt_sections") or []
    attempt_window_task_ids = summary.get("attempt_window_task_ids") or []
    gate_success_task_ids = gate.get("gate_success_task_ids") or []
    gate_blocking_task_ids = gate.get("gate_blocking_task_ids") or []
    gate_blocker_result_class_counts = gate.get("gate_blocker_result_class_counts") or {}
    lines = [
        "Mew-first calibration economics",
        f"source: {summary.get('source_path')}",
    ]
    if included_sections:
        section_bits = [str(section) for section in included_sections]
        lines.append("included_attempt_sections: " + ", ".join(section_bits))
    if attempt_window_task_ids:
        window_bits = [f"#{task_id}" for task_id in attempt_window_task_ids]
        lines.append("attempt_window: " + " ".join(window_bits))
    lines.append(
        (
            "gate: "
            f"{gate.get('clean_or_practical_successes')}/{summary.get('attempts_total')} "
            f"clean_or_practical threshold={gate.get('success_threshold')} "
            f"success_gap={gate.get('success_gap')} "
            f"passed={bool(gate.get('passed'))}"
        )
    )
    if gate_success_task_ids:
        success_bits = [f"#{task_id}" for task_id in gate_success_task_ids]
        lines.append("gate_successes: " + " ".join(success_bits))
    if gate_blocking_task_ids:
        blocker_bits = [f"#{task_id}" for task_id in gate_blocking_task_ids]
        lines.append("gate_blockers: " + " ".join(blocker_bits))
    if gate_blocker_result_class_counts:
        blocker_class_bits = [
            f"{key}={value}"
            for key, value in sorted(gate_blocker_result_class_counts.items())
        ]
        lines.append("gate_blocker_classes: " + " ".join(blocker_class_bits))
    if result_counts:
        result_bits = [f"{key}={value}" for key, value in sorted(result_counts.items())]
        lines.append("result_classes: " + " ".join(result_bits))
    drift_counts = counts.get("drift_class") or {}
    if drift_counts:
        drift_bits = [f"{key}={value}" for key, value in sorted(drift_counts.items())]
        lines.append("drift_classes: " + " ".join(drift_bits))
    rejected_counts = counts.get("rejected_patch_family") or {}
    if rejected_counts:
        rejected_bits = [f"{key}={value}" for key, value in sorted(rejected_counts.items())]
        lines.append("rejected_patch_families: " + " ".join(rejected_bits))
    failure_scope_counts = counts.get("failure_scope") or {}
    if failure_scope_counts:
        scope_bits = [f"{key}={value}" for key, value in sorted(failure_scope_counts.items())]
        lines.append("failure_scopes: " + " ".join(scope_bits))
    structural_reason_counts = counts.get("structural_reason") or {}
    if structural_reason_counts:
        reason_bits = [f"{key}={value}" for key, value in sorted(structural_reason_counts.items())]
        lines.append("structural_reasons: " + " ".join(reason_bits))
    route_counts = counts.get("recommended_route") or {}
    if route_counts:
        route_bits = [f"{key}={value}" for key, value in sorted(route_counts.items())]
        lines.append("recommended_routes: " + " ".join(route_bits))
    lines.append("attempts:")
    for attempt in summary.get("attempts") or []:
        lines.append(
            "- "
            f"#{attempt.get('task_id')} {attempt.get('result_class')} "
            f"owner={attempt.get('patch_owner')} credit={attempt.get('autonomy_credit')} "
            f"drift={attempt.get('drift_class')} rejected={attempt.get('rejected_patch_family')} "
            f"verifier={attempt.get('verifier_status')} "
            f"scope={attempt.get('failure_scope')} confidence={attempt.get('failure_scope_confidence')} "
            f"route={attempt.get('recommended_route')}"
        )
        signals = attempt.get("diagnosis_signals") or []
        if signals:
            lines.append("  signals: " + " ".join(str(signal) for signal in signals))
        structural_reason = attempt.get("structural_reason")
        if structural_reason:
            lines.append(f"  structural_reason: {structural_reason}")
    return "\n".join(lines)
