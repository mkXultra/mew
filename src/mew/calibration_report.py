"""Derived v0 classifier for the M6.11 calibration ledger."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .calibration_ledger import CalibrationLedgerRow, coerce_calibration_rows, load_calibration_ledger

CLASSIFIER_VERSION = "m6_12.v0"

ARCHETYPE_PRIORITY: tuple[str, ...] = (
    "preflight_gap",
    "cached_window_integrity",
    "drafting_timeout",
    "drafting_no_change",
    "write_policy_block",
    "timeout_family_no_bundle",
    "verifier_config_evidence",
    "measurement_process_gap",
    "live_finish_gate_validation",
    "no_change_non_calibration",
    "positive_outcome_v0",
    "fix_first_evidence",
    "drafting_other",
    "model_failure_other",
    "unclassified_v0",
)

CACHED_WINDOW_BLOCKERS = frozenset(
    {
        "insufficient_cached_window_context",
        "cached_window_incomplete",
        "insufficient_cached_context",
        "missing_exact_cached_window_texts_after_targeted_nontruncated_windows",
        "cached_window_incomplete_after_mid_block_test_window",
        "missing_exact_cached_window_texts",
        "cached_window_refs_not_hydrated_to_exact_window_texts",
    }
)

DRAFTING_TIMEOUT_BLOCKERS = frozenset(
    {
        "timeout",
        "drafting_timeout_after_complete_cached_refs_no_artifact",
        "model_auth_timed_out_object",
        "medium_small_impl_predraft_timeout_after_full_pair_read_no_artifact",
    }
)

DRAFTING_NO_CHANGE_BLOCKERS = frozenset(
    {
        "no_material_change",
        "verifier_green_no_change_overridden_by_overlapping_hunks",
        "no_concrete_draftable_change",
    }
)

WRITE_POLICY_BLOCKERS = frozenset(
    {
        "old_text_not_found",
        "write_policy_violation",
        "unpaired_source_edit_blocked",
    }
)

KNOWN_DRAFTING_BLOCKERS = (
    CACHED_WINDOW_BLOCKERS
    | DRAFTING_TIMEOUT_BLOCKERS
    | DRAFTING_NO_CHANGE_BLOCKERS
    | WRITE_POLICY_BLOCKERS
)

TIMEOUT_FAMILY_REVIEWER_DECISIONS = frozenset(
    {
        "accepted_as_no_bundle_timeout_family_evidence",
        "accepted_as_no_bundle_timeout_family_fix_first_evidence",
    }
)

MEASUREMENT_PROCESS_REVIEWER_DECISIONS = frozenset(
    {
        "accepted_as_no_bundle_measurement_process_gap_evidence",
        "accepted_as_no_bundle_measurement_path_evidence",
        "accepted_as_non_counted_measurement_artifact_evidence",
    }
)

POSITIVE_COUNTEDNESS = frozenset(
    {
        "positive_verifier_backed_no_change",
        "positive_paired_patch_verifier",
        "current_head_positive_verifier_backed_no_change",
        "positive_test_only_patch_verifier",
        "positive_current_head_paired_dry_run_applied_verified_after_reasoning_policy_fixes",
        "positive_current_head_paired_dry_run_applied_verified_after_cached_ref_hydration_fix",
    }
)

POSITIVE_REVIEWER_DECISIONS = frozenset(
    {
        "approved_positive_paired_patch_verifier",
        "approved_current_head_positive_verifier_backed_no_change",
        "approved_positive_current_head_fix_evidence_apply_and_verify",
        "approved_positive_current_head_cached_ref_hydration_write_ready_path",
        "approve_counted_paired_patch",
        "approve_counted_test_only_patch",
    }
)

POSITIVE_REVIEWER_OMISSIONS = frozenset(
    {
        "accept_no_change",
        "accept_recovered_no_change",
        "approve_commit",
    }
)


@dataclass(frozen=True)
class ClassifiedCalibrationRow:
    row: CalibrationLedgerRow
    archetype: str

    @property
    def row_ref(self) -> str:
        return self.row.row_ref


@dataclass(frozen=True)
class CalibrationSummary:
    classifier_version: str
    total_rows: int
    counts: Mapping[str, int]
    rows: tuple[ClassifiedCalibrationRow, ...]

    def archetypes_active(self) -> list[dict[str, Any]]:
        return [
            {"name": archetype, "counted": self.counts.get(archetype, 0)}
            for archetype in ARCHETYPE_PRIORITY
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "classifier_version": self.classifier_version,
            "total_rows": self.total_rows,
            "archetypes_active": self.archetypes_active(),
            "counts": dict(self.counts),
        }


def _field(row: CalibrationLedgerRow, name: str) -> str:
    return row.text_field(name)


def _nested_failure_code(row: CalibrationLedgerRow) -> str:
    direct = row.field("failure_code")
    if direct not in (None, ""):
        return str(direct)
    failure = row.field("failure")
    if isinstance(failure, Mapping):
        code = failure.get("code")
        if code not in (None, ""):
            return str(code)
    return ""


def _has_compiler_replay_bundle(row: CalibrationLedgerRow) -> bool:
    value = row.field("replay_bundle_path")
    if value in (None, "", "null"):
        return False
    replay_bundle_path = str(value).replace("\\", "/")
    return (
        "/.mew/replays/work-loop/" in f"/{replay_bundle_path}"
        and replay_bundle_path.endswith("/replay_metadata.json")
    )


def _is_model_failure(row: CalibrationLedgerRow) -> bool:
    report_kind = _field(row, "report_kind") or _field(row, "report_type") or _field(row, "kind")
    return report_kind == "work-loop-model-failure" or bool(_nested_failure_code(row))


def _is_preflight_gap(row: CalibrationLedgerRow) -> bool:
    countedness = _field(row, "countedness").lower()
    reviewer_decision = _field(row, "reviewer_decision").lower()
    return (
        "preflight" in countedness
        or "preflight" in reviewer_decision
        or countedness == "non_counted_no_artifact_live_preflight_validation"
    )


def _is_positive_outcome(row: CalibrationLedgerRow) -> bool:
    countedness = _field(row, "countedness")
    reviewer_decision = _field(row, "reviewer_decision")
    if countedness.startswith("fix_first_") or countedness == "counted_fix_first_blocker":
        return False
    return countedness in POSITIVE_COUNTEDNESS or reviewer_decision in POSITIVE_REVIEWER_DECISIONS


def _is_fix_first_evidence(row: CalibrationLedgerRow) -> bool:
    countedness = _field(row, "countedness")
    return countedness.startswith("fix_first_") or countedness == "counted_fix_first_blocker"


def classify_calibration_row(row: CalibrationLedgerRow) -> str:
    """Classify one row using the §4.2.A.2 v0 post-priority order."""

    blocker_code = _field(row, "blocker_code")
    reviewer_decision = _field(row, "reviewer_decision")

    if _is_preflight_gap(row):
        return "preflight_gap"
    if blocker_code in CACHED_WINDOW_BLOCKERS:
        return "cached_window_integrity"
    if blocker_code in DRAFTING_TIMEOUT_BLOCKERS or (
        _is_model_failure(row) and _nested_failure_code(row) == "request_timed_out"
    ):
        return "drafting_timeout"
    if blocker_code in DRAFTING_NO_CHANGE_BLOCKERS:
        return "drafting_no_change"
    if blocker_code in WRITE_POLICY_BLOCKERS:
        return "write_policy_block"
    if reviewer_decision in TIMEOUT_FAMILY_REVIEWER_DECISIONS:
        return "timeout_family_no_bundle"
    if reviewer_decision == "accepted_as_no_bundle_verifier_config_evidence":
        return "verifier_config_evidence"
    if reviewer_decision in MEASUREMENT_PROCESS_REVIEWER_DECISIONS:
        return "measurement_process_gap"
    if reviewer_decision == "accepted_as_live_finish_gate_validation_not_replay_incidence":
        return "live_finish_gate_validation"
    if reviewer_decision == "accepted_as_no_change_non_calibration":
        return "no_change_non_calibration"
    if _is_positive_outcome(row):
        return "positive_outcome_v0"
    if _is_fix_first_evidence(row):
        return "fix_first_evidence"
    if _has_compiler_replay_bundle(row) and blocker_code and blocker_code not in KNOWN_DRAFTING_BLOCKERS:
        return "drafting_other"
    if _is_model_failure(row) and _nested_failure_code(row) != "request_timed_out":
        return "model_failure_other"
    return "unclassified_v0"


def classify_calibration_rows(
    rows: Iterable[CalibrationLedgerRow | Mapping[str, Any]],
) -> tuple[ClassifiedCalibrationRow, ...]:
    coerced = coerce_calibration_rows(rows)
    return tuple(
        ClassifiedCalibrationRow(row=row, archetype=classify_calibration_row(row))
        for row in coerced
    )


def summarize_calibration_rows(
    rows: Iterable[CalibrationLedgerRow | Mapping[str, Any]],
) -> CalibrationSummary:
    classified = classify_calibration_rows(rows)
    counter = Counter(item.archetype for item in classified)
    counts = {archetype: counter.get(archetype, 0) for archetype in ARCHETYPE_PRIORITY}
    return CalibrationSummary(
        classifier_version=CLASSIFIER_VERSION,
        total_rows=len(classified),
        counts=counts,
        rows=classified,
    )


def summarize_calibration_ledger(path: str = "proof-artifacts/m6_11_calibration_ledger.jsonl") -> CalibrationSummary:
    return summarize_calibration_rows(load_calibration_ledger(path))
