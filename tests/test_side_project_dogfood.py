from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from mew.cli import build_parser
from mew.commands import cmd_side_dogfood
from mew.side_project_dogfood import (
    append_side_project_dogfood_record,
    dogfood_record_template,
    format_side_project_dogfood_report,
    load_side_project_dogfood_ledger,
    normalize_side_project_dogfood_record,
    summarize_side_project_dogfood,
)


def _record(**overrides: object) -> dict[str, object]:
    record = dogfood_record_template()
    record.update(
        {
            "task_id": 701,
            "session_id": 702,
            "side_project": "mew-companion-log",
            "branch_or_worktree": "../mew-side-companion",
            "task_summary": "Add journal markdown scaffold.",
            "task_kind": "coding",
            "codex_cli_used_as": "operator",
            "first_edit_latency": 12.25,
            "read_turns_before_edit": 3,
            "files_changed": ["src/mew_companion_log/journal.py"],
            "tests_run": ["uv run pytest -q"],
            "reviewer_rejections": 1,
            "verifier_failures": 0,
            "rescue_edits": 0,
            "outcome": "practical",
            "failure_class": "none_observed",
            "repair_required": False,
            "proof_artifacts": ["proof-artifacts/side/example.json"],
            "commit": "abc1234",
        }
    )
    record.update(overrides)
    return record


def test_template_contains_required_measurement_fields() -> None:
    template = dogfood_record_template()

    for field in (
        "task_id",
        "session_id",
        "side_project",
        "branch_or_worktree",
        "codex_cli_used_as",
        "first_edit_latency",
        "read_turns_before_edit",
        "reviewer_rejections",
        "verifier_failures",
        "rescue_edits",
        "outcome",
        "failure_class",
        "repair_required",
        "proof_artifacts",
        "commit",
    ):
        assert field in template
    assert template["codex_cli_used_as"] == "operator"


def test_append_and_summarize_side_project_dogfood_ledger(tmp_path: Path) -> None:
    ledger = tmp_path / "side_project_dogfood_ledger.jsonl"
    append_side_project_dogfood_record(_record(outcome="practical"), path=ledger)
    append_side_project_dogfood_record(
        _record(
            task_id=703,
            outcome="failed",
            failure_class="cached_window_integrity",
            repair_required=True,
            verifier_failures=1,
            rescue_edits=2,
            codex_cli_used_as="fallback",
        ),
        path=ledger,
    )

    rows = load_side_project_dogfood_ledger(ledger)
    summary = summarize_side_project_dogfood(path=ledger, limit=1)
    text = format_side_project_dogfood_report(summary)

    assert [row.field("task_id") for row in rows] == [701, 703]
    assert summary["rows_total"] == 2
    assert summary["gate"]["clean_or_practical"] == 1
    assert summary["gate"]["rescue_edits_total"] == 2
    assert summary["counts"]["codex_cli_used_as"] == {"operator": 1, "fallback": 1}
    assert summary["attempts"][0]["task_id"] == 703
    assert "Side-project dogfood telemetry" in text
    assert "failure_class: cached_window_integrity=1 none_observed=1" in text


def test_normalize_rejects_unknown_codex_cli_role() -> None:
    with pytest.raises(ValueError, match="codex_cli_used_as must be one of"):
        normalize_side_project_dogfood_record(_record(codex_cli_used_as="author"))


def test_side_dogfood_parser_and_append_command(tmp_path: Path, capsys) -> None:
    ledger = tmp_path / "ledger.jsonl"
    payload = tmp_path / "record.json"
    payload.write_text(json.dumps(_record()), encoding="utf-8")

    args = build_parser().parse_args(
        [
            "side-dogfood",
            "append",
            "--input",
            str(payload),
            "--ledger",
            str(ledger),
            "--json",
        ]
    )

    assert args.side_dogfood_action == "append"
    assert args.func(args) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["kind"] == "side_project_dogfood_append"
    assert output["line_number"] == 1
    assert output["record"]["task_id"] == 701
    assert ledger.exists()


def test_side_dogfood_report_command_handles_missing_ledger(capsys) -> None:
    args = Namespace(
        side_dogfood_action="report",
        ledger="does-not-exist.jsonl",
        limit=10,
        json=True,
    )

    assert cmd_side_dogfood(args) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["kind"] == "side_project_dogfood"
    assert output["rows_total"] == 0
