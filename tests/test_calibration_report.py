from __future__ import annotations

import json
from pathlib import Path

import pytest

from mew.calibration_ledger import CalibrationLedgerRow, load_calibration_ledger
from mew.calibration_report import (
    ARCHETYPE_PRIORITY,
    POSITIVE_REVIEWER_OMISSIONS,
    classify_calibration_row,
    summarize_calibration_ledger,
    summarize_calibration_rows,
)


def row(**fields: object) -> CalibrationLedgerRow:
    return CalibrationLedgerRow(line_number=1, data=fields)


def test_parser_reads_jsonl_fixture_without_mutating(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text(
        json.dumps({"row_ref": "fixture-1", "countedness": "positive_paired_patch_verifier"})
        + "\n\n"
        + json.dumps({"row": 2, "reviewer_decision": "accepted_as_no_bundle_timeout_family_evidence"})
        + "\n",
        encoding="utf-8",
    )

    parsed = load_calibration_ledger(ledger)

    assert [item.row_ref for item in parsed] == ["fixture-1", "2"]
    assert parsed[0].text_field("countedness") == "positive_paired_patch_verifier"
    assert parsed[1].text_field("reviewer_decision") == "accepted_as_no_bundle_timeout_family_evidence"
    assert ledger.read_text(encoding="utf-8").count("\n") == 3


def test_priority_edge_cases_preflight_and_blockers_win_before_fallbacks() -> None:
    summary = summarize_calibration_rows(
        [
            {
                "countedness": "Fix_First_Preflight_Refresh_Gap",
                "blocker_code": "cached_window_incomplete",
                "reviewer_decision": "approve_commit",
            },
            {
                "countedness": "counted_fix_first_blocker",
                "blocker_code": "insufficient_cached_window_context",
            },
            {
                "countedness": "fix_first_remediation",
                "blocker_code": "unrecognised_closeout_blocker",
            },
            {
                "replay_bundle_path": ".mew/replays/work-loop/571/replay_metadata.json",
                "blocker_code": "future_compiler_blocker",
            },
            {
                "replay_bundle_path": ".mew/reports/work-loop/571/replay_metadata.json",
                "blocker_code": "future_compiler_blocker",
            },
            {
                "replay_bundle_path": ".mew/replays/work-loop/571/report.json",
                "blocker_code": "future_compiler_blocker",
            },
            {"report_kind": "work-loop-model-failure", "failure": {"code": "request_timed_out"}},
        ]
    )

    assert summary.counts["preflight_gap"] == 1
    assert summary.counts["cached_window_integrity"] == 1
    assert summary.counts["fix_first_evidence"] == 1
    assert summary.counts["drafting_other"] == 1
    assert summary.counts["drafting_timeout"] == 1
    assert summary.counts["unclassified_v0"] == 2


def test_positive_outcome_v0_guard_and_inclusion_sets() -> None:
    assert classify_calibration_row(
        row(countedness="positive_current_head_paired_dry_run_applied_verified_after_reasoning_policy_fixes")
    ) == "positive_outcome_v0"
    assert classify_calibration_row(
        row(countedness="positive_current_head_paired_dry_run_applied_verified_after_cached_ref_hydration_fix")
    ) == "positive_outcome_v0"
    assert classify_calibration_row(
        row(reviewer_decision="approved_positive_current_head_fix_evidence_apply_and_verify")
    ) == "positive_outcome_v0"
    assert classify_calibration_row(
        row(reviewer_decision="approved_positive_current_head_cached_ref_hydration_write_ready_path")
    ) == "positive_outcome_v0"

    assert classify_calibration_row(
        row(countedness="fix_first_remediation", reviewer_decision="approve_commit")
    ) == "fix_first_evidence"
    assert classify_calibration_row(
        row(countedness="counted_fix_first_blocker", reviewer_decision="approved_positive_paired_patch_verifier")
    ) == "fix_first_evidence"

    for omitted in POSITIVE_REVIEWER_OMISSIONS:
        assert classify_calibration_row(row(reviewer_decision=omitted)) == "unclassified_v0"


@pytest.mark.parametrize("archetype", ARCHETYPE_PRIORITY)
def test_summary_always_emits_declared_archetype_keys(archetype: str) -> None:
    summary = summarize_calibration_rows([])
    assert archetype in summary.counts
    assert summary.counts[archetype] == 0


def test_real_ledger_post_priority_totals_match_design_doc() -> None:
    summary = summarize_calibration_ledger("proof-artifacts/m6_11_calibration_ledger.jsonl")

    assert summary.total_rows == 127
    assert dict(summary.counts) == {
        "preflight_gap": 9,
        "cached_window_integrity": 17,
        "drafting_timeout": 12,
        "drafting_no_change": 6,
        "write_policy_block": 4,
        "timeout_family_no_bundle": 5,
        "verifier_config_evidence": 2,
        "measurement_process_gap": 6,
        "live_finish_gate_validation": 3,
        "no_change_non_calibration": 4,
        "positive_outcome_v0": 42,
        "fix_first_evidence": 3,
        "drafting_other": 0,
        "model_failure_other": 0,
        "unclassified_v0": 14,
    }
    assert sum(summary.counts.values()) == 127
    assert summary.as_dict()["archetypes_active"][0] == {"name": "preflight_gap", "counted": 9}
