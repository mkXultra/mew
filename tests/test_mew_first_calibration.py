from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from mew.cli import build_parser
from mew.commands import cmd_metrics
from mew.mew_first_calibration import (
    extract_mew_first_attempts,
    format_mew_first_calibration_report,
    summarize_mew_first_calibration,
)


M6_9_FIXTURE = """
### M6.9: Durable Coding Intelligence

- Task `#590` added a shape as supervisor-rescue product progress. The
  supervisor rejected the incorrect draft and made the edit directly. Count
  this as product progress, not mew-first autonomy credit. Validation covered
  focused tests.
- Task `#591` landed a bounded M6.9 substrate repair for the failure class.
- Task `#592` landed the sixth shape as mixed mew-first/product progress:
  mew produced the final paired source/test patch and verification passed, but
  the supervisor supplied exact local cached windows and one retry steer.
- Task `#593` landed after a stale-session restart note. The fresh mew-first
  session drafted the paired source/test patch and the supervisor approved
  without rescue edits. Validation covered focused tests.
- Task `#595` landed. The fresh mew-first session read exact source/test
  windows, drafted the paired source/test patch, and the supervisor approved
  without rescue edits. Validation covered focused tests.
- Task `#596` landed. The fresh mew-first session read exact source/test
  windows, drafted the paired source/test patch, and the supervisor approved
  without rescue edits. Validation covered focused tests.
- Task `#597` landed after a transient empty model response and restarted
  mew-first session; the supervisor approved without rescue edits. Validation
  covered focused tests.
- Task `#598` added a scenario. The first mew-first session drifted into an
  M6.11-only artifact tweak, so the supervisor rescued the product slice.
  Validation covered focused tests.
- Task `#599` added a scenario. The mew-first session drifted into a rejected
  `m6_9-symbol-index-hit` artifact tweak, so the supervisor rescued the bounded
  product slice. Validation covered focused tests.
- Task `#600` added a scenario. The mew-first session drifted into a rejected
  generic dogfood cleanup/default patch, so the supervisor rescued the bounded
  product slice. Validation covered focused tests.
- Task `#601` is supervisor-owned product progress that enabled a minimal
  reasoning-trace proof. Validation covered focused tests.
- Task `#602` extended reviewer-steering from one durable reviewer-correction
  rule to a three-rule matrix. Validation covered focused tests.

### M6.10: Execution Accelerators
"""


M6_16_REVIEW_REPAIR_FIXTURE = """
### M6.16: Calibration

- Task `#674` landed the GitHub issue `#6` side-dogfood ledger-semantics
  slice as practical mew-first evidence. `mew side-dogfood report` now states
  that `rescue_edits` is a numeric Codex product-code rescue count and excludes
  operator steering, reviewer rejection, verifier follow-up, and generic
  repair. Count this as practical mew-first without rescue edits and
  without supervisor product-code rescue: session `#659` authored the initial
  paired source/test patch; codex-ultra review found a non-integral float
  truncation bug and missing machine-readable alias; session `#660` repaired
  both. Valid proof passed. Codex-ultra re-review reported no findings.
"""


M6_16_REVIEW_REPAIR_WITHOUT_RESCUE_EDITS_ONLY_FIXTURE = """
### M6.16: Calibration

- Task `#671` landed the side-dogfood validation slice as practical mew-first
  evidence. Count this as practical mew-first without rescue edits: session
  `#650` authored the initial paired source/test patch; codex-ultra review
  found the verifier only checked internal flags; session `#651` repaired the
  behavior-visible proof. Valid proof passed. Codex-ultra re-review reported no
  findings.
"""


M6_16_CLEAN_NO_RESCUE_FIXTURE = """
### M6.16: Calibration

- Task `#675` landed a bounded formatter slice as clean mew-first evidence. The
  mew-first session authored the paired source/test patch without rescue edits.
  Valid proof passed without reviewer findings.
"""


def test_extract_mew_first_attempts_skips_substrate_repairs_and_classifies_latest_10() -> None:
    attempts = extract_mew_first_attempts(M6_9_FIXTURE, limit=10)

    assert [attempt.task_id for attempt in attempts] == [602, 601, 600, 599, 598, 597, 596, 595, 593, 592]
    assert [attempt.result_class for attempt in attempts] == [
        "supervisor_owned_or_unknown",
        "supervisor_owned",
        "supervisor_rescue",
        "supervisor_rescue",
        "supervisor_rescue",
        "practical_mew_first",
        "clean_mew_first",
        "clean_mew_first",
        "practical_mew_first",
        "partial_mew_first",
    ]
    attempt_by_task_id = {attempt.task_id: attempt for attempt in attempts}
    assert attempt_by_task_id[600].drift_class == "generic_cleanup_substitution"
    assert attempt_by_task_id[600].rejected_patch_family == "generic_cleanup"


def test_reviewer_repaired_mew_first_without_supervisor_rescue_is_practical(tmp_path: Path) -> None:
    attempts = extract_mew_first_attempts(M6_16_REVIEW_REPAIR_FIXTURE, limit=10)

    assert [attempt.task_id for attempt in attempts] == [674]
    assert attempts[0].result_class == "practical_mew_first"
    assert attempts[0].patch_owner == "mew"
    assert attempts[0].autonomy_credit == "practical"

    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text(M6_16_REVIEW_REPAIR_FIXTURE, encoding="utf-8")

    summary = summarize_mew_first_calibration(source_path=source, limit=10)

    assert summary["gate"]["gate_success_task_ids"] == [674]
    assert summary["gate"]["gate_blocking_task_ids"] == []
    assert summary["counts"]["result_class"]["practical_mew_first"] == 1


def test_reviewer_repaired_practical_credit_without_rescue_edits_only_is_practical() -> None:
    attempts = extract_mew_first_attempts(
        M6_16_REVIEW_REPAIR_WITHOUT_RESCUE_EDITS_ONLY_FIXTURE,
        limit=10,
    )

    assert [attempt.task_id for attempt in attempts] == [671]
    assert attempts[0].result_class == "practical_mew_first"
    assert attempts[0].patch_owner == "mew"
    assert attempts[0].autonomy_credit == "practical"


def test_clean_mew_first_without_rescue_edits_stays_clean() -> None:
    attempts = extract_mew_first_attempts(M6_16_CLEAN_NO_RESCUE_FIXTURE, limit=10)

    assert [attempt.task_id for attempt in attempts] == [675]
    assert attempts[0].result_class == "clean_mew_first"
    assert attempts[0].patch_owner == "mew"
    assert attempts[0].autonomy_credit == "clean"


def test_summarize_mew_first_calibration_gate_and_format(tmp_path: Path) -> None:
    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text(M6_9_FIXTURE, encoding="utf-8")

    summary = summarize_mew_first_calibration(source_path=source, limit=10)

    assert summary["gate"]["success_gap"] == 3
    assert summary["gate"] == {
        "success_threshold": 7,
        "clean_or_practical_successes": 4,
        "success_gap": 3,
        "success_rate": 0.4,
        "gate_success_task_ids": [597, 596, 595, 593],
        "gate_blocking_task_ids": [602, 601, 600, 599, 598, 592],
        "gate_blocker_result_class_counts": {
            "partial_mew_first": 1,
            "supervisor_rescue": 3,
            "supervisor_owned": 1,
            "supervisor_owned_or_unknown": 1,
        },
        "passed": False,
    }
    assert summary["attempt_window_task_ids"] == [602, 601, 600, 599, 598, 597, 596, 595, 593, 592]
    assert summary["included_attempt_sections"] == ["### M6.9:", "### M6.10:"]
    assert summary["counts"]["result_class"]["supervisor_rescue"] == 3
    text = format_mew_first_calibration_report(summary)
    assert "included_attempt_sections: ### M6.9:, ### M6.10:" in text
    assert "attempt_window: #602 #601 #600 #599 #598 #597 #596 #595 #593 #592" in text
    assert "gate: 4/10 clean_or_practical threshold=7 success_gap=3 passed=False" in text
    assert "gate_successes: #597 #596 #595 #593" in text
    assert "gate_blockers: #602 #601 #600 #599 #598 #592" in text
    assert "gate_blocker_classes: partial_mew_first=1 supervisor_owned=1 supervisor_owned_or_unknown=1 supervisor_rescue=3" in text
    assert "#599 supervisor_rescue" in text


def test_summarize_mew_first_calibration_reports_only_found_attempt_sections(tmp_path: Path) -> None:
    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text(
        """
### M6.10: Execution Accelerators

- Task `#606` landed a post-D1/D2 M6.10 mew-first implementation slice.
  The fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
""",
        encoding="utf-8",
    )

    summary = summarize_mew_first_calibration(source_path=source, limit=10)

    assert summary["included_attempt_sections"] == ["### M6.10:"]
    assert [attempt["task_id"] for attempt in summary["attempts"]] == [606]


def test_extract_mew_first_attempts_includes_m6_10_attempts_after_m6_9() -> None:
    text = (
        M6_9_FIXTURE
        + """
- Task `#606` landed a post-D1/D2 M6.10 mew-first implementation slice.
  The fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
"""
    )

    attempts = extract_mew_first_attempts(text, limit=10)

    assert [attempt.task_id for attempt in attempts][:2] == [606, 602]
    assert attempts[0].result_class == "clean_mew_first"
    assert attempts[0].patch_owner == "mew"


def test_extract_mew_first_attempts_limit_selects_newest_task_ids_first() -> None:
    text = """
### M6.16: Calibration

- Task `#675` landed a bounded formatter slice as clean mew-first evidence.
  The fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Valid proof passed.
- Task `#674` landed a side-dogfood ledger-semantics slice as practical
  mew-first evidence after reviewer repair. Valid proof passed.
- Task `#673` landed a bounded mew-first implementation evidence slice. The
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.

### M6.10: Execution Accelerators

- Task `#629` landed an older mew-first implementation evidence slice. The
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
- Task `#631` landed an older mew-first implementation evidence slice. The
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
- Task `#632` landed an older mew-first implementation evidence slice. The
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
"""

    attempts = extract_mew_first_attempts(text, limit=3)

    assert [attempt.task_id for attempt in attempts] == [675, 674, 673]


def test_reviewer_steered_mew_first_attempt_is_practical_not_clean() -> None:
    text = """
### M6.10: Execution Accelerators

- Task `#606` landed a bounded mew-first implementation evidence slice. The
  first reviewer-rejected patch had the wrong target, then the reviewer steer
  was needed to stop read-only churn. The fresh mew-first session drafted the
  paired source/test patch and the supervisor approved without rescue edits.
  Validation covered focused tests.
"""

    attempts = extract_mew_first_attempts(text, limit=10)

    assert attempts[-1].result_class == "practical_mew_first"
    assert attempts[-1].autonomy_credit == "practical"
    assert attempts[-1].drift_class == "wrong_target_substitution"
    assert attempts[-1].rejected_patch_family == "reviewer_rejected_patch"
    assert attempts[-1].failure_scope == "polish"
    assert attempts[-1].failure_scope_confidence == "medium"
    assert attempts[-1].recommended_route == "same_task_retry_if_repeated"
    assert "reviewer_steer_required" in attempts[-1].diagnosis_signals


def test_failure_scope_diagnosis_routes_structural_invalid_transient_and_ambiguous() -> None:
    text = """
### M6.16: Codex-Grade Implementation Lane

- Task `#680` added a slice as supervisor rescue after the mew-first session
  repeatedly drifted into a wrong-target patch and lost the retry frontier.
  Validation covered focused tests.
- Task `#681` failed as a mew-first implementation attempt because the task
  used an invalid task verifier. The task scope needed correction before retry.
- Task `#682` failed as a mew-first implementation attempt after a transient
  empty model response and restarted without changing product code.
- Task `#683` landed as mixed mew-first/product progress, but the final route
  is not clear from the evidence. Validation covered focused tests.
"""

    attempts = extract_mew_first_attempts(text, limit=10)
    by_id = {attempt.task_id: attempt for attempt in attempts}

    assert by_id[680].failure_scope == "structural"
    assert by_id[680].recommended_route == "m6_14_repair"
    assert by_id[680].structural_reason == "wrong_target_substitution"
    assert "lost_retry_frontier" in by_id[680].diagnosis_signals
    assert by_id[681].failure_scope == "invalid_task_spec"
    assert by_id[681].recommended_route == "fix_task_spec_then_retry"
    assert by_id[682].failure_scope == "transient_model"
    assert by_id[682].recommended_route == "retry_same_task"
    assert by_id[683].failure_scope == "ambiguous"
    assert by_id[683].recommended_route == "collect_replay_or_reviewer_evidence"


def test_mew_first_calibration_reports_failure_scope_counts(tmp_path: Path) -> None:
    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text(
        """
### M6.16: Codex-Grade Implementation Lane

- Task `#690` produced a supervisor-owned rescue after a wrong-target patch.
  Validation covered focused tests.
- Task `#691` landed a practical mew-first slice after a reviewer steer. The
  fresh mew-first session drafted the patch and the supervisor approved
  without rescue edits. Validation covered focused tests.
""",
        encoding="utf-8",
    )

    summary = summarize_mew_first_calibration(source_path=source, limit=10)
    text = format_mew_first_calibration_report(summary)

    assert summary["counts"]["failure_scope"] == {"polish": 1, "structural": 1}
    assert summary["counts"]["structural_reason"] == {"wrong_target_substitution": 1}
    assert "failure_scopes: polish=1 structural=1" in text
    assert "structural_reasons: wrong_target_substitution=1" in text
    assert "route=m6_14_repair" in text


def test_success_after_blocker_fixes_stays_in_attempt_window() -> None:
    text = """
### M6.16: Codex-Grade Implementation Lane

- Task `#660` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#661` and `#662` blocker fixes. Count
  this as `success_after_substrate_fix`: the fresh mew-first session drafted
  the paired source/test patch and the supervisor approved without product
  rescue edits; a reviewer steer was needed only to replace an invalid task
  verifier. Valid proof passed.
"""

    attempts = extract_mew_first_attempts(text, limit=10)

    assert [attempt.task_id for attempt in attempts] == [660]
    assert attempts[-1].result_class == "practical_mew_first"
    assert attempts[-1].autonomy_credit == "practical"


def test_extract_mew_first_attempts_classifies_task_goal_and_synthetic_schema_substitution() -> None:
    text = """
### M6.16: Codex-Grade Implementation Lane

- Task `#656` produced a supervisor-owned rescue after failed mew-first
  attempts. The final retry drifted into a wrong-target calibration parser
  patch and recorded task-goal/substitution fragility plus
  synthetic_schema_substitution after reviewer feedback.
"""

    attempts = extract_mew_first_attempts(text, limit=10)

    assert len(attempts) == 1
    assert attempts[0].result_class == "supervisor_owned"
    assert attempts[0].drift_class == "task_goal_substitution"
    assert attempts[0].rejected_patch_family == "task_goal_substitution"


def test_extract_mew_first_attempts_ignores_narrative_status_bullets_but_keeps_attempt_prefixes() -> None:
    text = """
### M6.16: Codex-Grade Implementation Lane

- The supervisor-owned baseline surface adds a measurement-quality status note
  after task `#659` so the metrics evidence stays visible. This is narrative
  calibration context, not a mew-first attempt entry, even though it mentions
  product progress and supervisor ownership.
- #639 mew-first note landed a bounded implementation evidence slice. The
  fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
- Task `#660` then landed as bounded mew-first implementation evidence for
  M6.16 measurement quality after the `#661` and `#662` blocker fixes. Count
  this as `success_after_substrate_fix`: the fresh mew-first session drafted
  the paired source/test patch and the supervisor approved without product
  rescue edits; a reviewer steer was needed only to replace an invalid task
  verifier. Valid proof passed.
- follow-up `#664` landed a bounded mew-first implementation evidence slice.
  The fresh mew-first session drafted the paired source/test patch and the
  supervisor approved without rescue edits. Validation covered focused tests.
"""

    attempts = extract_mew_first_attempts(text, limit=10)

    assert [attempt.task_id for attempt in attempts] == [664, 660, 639]
    assert attempts[0].result_class == "clean_mew_first"
    assert attempts[1].result_class == "practical_mew_first"
    assert attempts[2].result_class == "clean_mew_first"


def test_metrics_parser_accepts_mew_first_calibration_flags() -> None:
    args = build_parser().parse_args(["metrics", "--mew-first", "--source-file", "status.md", "--json"])

    assert args.mew_first is True
    assert args.source_file == "status.md"
    assert args.json is True


def test_cmd_metrics_mew_first_json_output(tmp_path: Path, capsys) -> None:
    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text(M6_9_FIXTURE, encoding="utf-8")
    args = Namespace(mew_first=True, source_file=str(source), limit=10, json=True)

    assert cmd_metrics(args) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["kind"] == "mew_first_calibration"
    assert payload["gate"]["clean_or_practical_successes"] == 4
    assert payload["attempts"][0]["task_id"] == 602
