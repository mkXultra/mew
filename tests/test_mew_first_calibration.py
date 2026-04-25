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


def test_extract_mew_first_attempts_skips_substrate_repairs_and_classifies_latest_10() -> None:
    attempts = extract_mew_first_attempts(M6_9_FIXTURE, limit=10)

    assert [attempt.task_id for attempt in attempts] == [592, 593, 595, 596, 597, 598, 599, 600, 601, 602]
    assert [attempt.result_class for attempt in attempts] == [
        "partial_mew_first",
        "practical_mew_first",
        "clean_mew_first",
        "clean_mew_first",
        "practical_mew_first",
        "supervisor_rescue",
        "supervisor_rescue",
        "supervisor_rescue",
        "supervisor_owned",
        "supervisor_owned_or_unknown",
    ]
    assert attempts[7].drift_class == "generic_cleanup_substitution"
    assert attempts[7].rejected_patch_family == "generic_cleanup"


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
        "passed": False,
    }
    assert summary["included_attempt_sections"] == ["### M6.9:", "### M6.10:"]
    assert summary["counts"]["result_class"]["supervisor_rescue"] == 3
    text = format_mew_first_calibration_report(summary)
    assert "included_attempt_sections: ### M6.9:, ### M6.10:" in text
    assert "gate: 4/10 clean_or_practical threshold=7 success_gap=3 passed=False" in text
    assert "#599 supervisor_rescue" in text


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

    assert [attempt.task_id for attempt in attempts][-2:] == [602, 606]
    assert attempts[-1].result_class == "clean_mew_first"
    assert attempts[-1].patch_owner == "mew"


def test_reviewer_steered_mew_first_attempt_is_practical_not_clean() -> None:
    text = """
### M6.10: Execution Accelerators

- Task `#606` landed a bounded mew-first implementation evidence slice. The
  reviewer steer was needed to stop read-only churn, then the fresh mew-first
  session drafted the paired source/test patch and the supervisor approved
  without rescue edits. Validation covered focused tests.
"""

    attempts = extract_mew_first_attempts(text, limit=10)

    assert attempts[-1].result_class == "practical_mew_first"
    assert attempts[-1].autonomy_credit == "practical"


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
    assert payload["attempts"][-1]["task_id"] == 602
