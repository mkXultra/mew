from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from mew.cli import build_parser
from mew.commands import cmd_metrics
from mew.implementation_lane_baseline import (
    format_implementation_lane_baseline_report,
    summarize_implementation_lane_baseline,
    summarize_implementation_lane_baseline_from_summaries,
)


def test_implementation_lane_baseline_combines_real_summary_shapes() -> None:
    summary = summarize_implementation_lane_baseline_from_summaries(
        mew_first_summary={
            "kind": "mew_first_calibration",
            "attempts_total": 5,
            "gate": {
                "clean_or_practical_successes": 2,
                "success_rate": 0.4,
                "success_gap": 3,
                "gate_blocking_task_ids": [11, 12, 11, 13, 12],
                "gate_blocker_result_class_counts": {"partial_mew_first": 1, "supervisor_owned": 1},
            },
            "counts": {
                "result_class": {
                    "partial_mew_first": 1,
                    "supervisor_rescue": 1,
                    "supervisor_owned": 1,
                },
                "drift_class": {"wrong_target_substitution": 1},
                "rejected_patch_family": {"synthetic_schema_substitution": 1},
            },
        },
        observation_metrics={
            "kind": "coding",
            "reliability": {
                "approvals": {"total": 5, "rejected": 2},
                "verification": {"total": 4, "failed": 1},
            },
            "self_hosting": {
                "first_edit_proposal_seconds": {"count": 3, "median": 12.0, "p95": 30.0, "max": 44.0},
            },
            "diagnostics": {
                "slow_first_edit_proposals": [
                    {
                        "session_id": 99,
                        "task_id": 11,
                        "task_title": "Slow patch",
                        "task_status": "ready",
                        "first_edit_proposal_seconds": 44.0,
                        "first_write_tool_call_id": 123,
                        "first_write_tool": "edit_file",
                        "first_write_path": "src/mew/metrics.py",
                        "started_at": "2026-04-19T00:00:44Z",
                        "first_model_summary": "Planned too long before editing.",
                    }
                ],
            },
        },
        side_project_summary={
            "kind": "side_project_dogfood",
            "ledger_path": "proof-artifacts/side.jsonl",
            "rows_total": 3,
            "gate": {
                "clean_or_practical": 1,
                "success_rate": 0.333,
                "failed": 1,
                "structural_repairs_required": 1,
                "rescue_edits_total": 2,
            },
        },
    )

    assert summary["kind"] == "implementation_lane_baseline"
    assert summary["mew_first"]["supervisor_rescue_count"] == 2
    assert summary["mew_first"]["rescue_partial_count"] == 3
    assert summary["mew_first"]["rescue_partial_rate"] == 0.6
    assert summary["mew_first"]["gate_blocking_task_ids"] == [11, 12, 13]
    assert summary["mew_first"]["failure_classes"]["result_class"]["supervisor_owned"] == 1
    assert summary["mew_first"]["failure_classes"]["drift_class"] == {"wrong_target_substitution": 1}
    assert summary["approval"] == {"total": 5, "rejected": 2, "rejection_rate": 0.4}
    assert summary["verifier"] == {"total": 4, "failed": 1, "failure_rate": 0.25}
    assert summary["first_edit_latency"]["count"] == 3
    assert summary["first_edit_latency"]["median"] == 12.0
    assert summary["first_edit_latency"]["p95"] == 30.0
    assert summary["first_edit_latency"]["max"] == 44.0
    assert summary["first_edit_latency"]["samples"][0]["session_id"] == 99
    assert summary["first_edit_latency"]["samples"][0]["first_write_path"] == "src/mew/metrics.py"
    assert summary["side_project"]["rows_total"] == 3
    assert summary["side_project"]["clean_or_practical"] == 1
    assert summary["side_project"]["rescue_rate"] == 0.667
    assert summary["side_project"]["codex_product_code_rescue_edits"] == 2
    assert summary["recommended_first_bottleneck"]["name"] == "mew_first_rescue_partial"

    text = format_implementation_lane_baseline_report(summary)
    assert "Implementation-lane baseline" in text
    assert "mew_first: success=2/5 rescue_partial=3 rescue_partial_rate=0.6" in text
    assert "failure_classes:" in text
    assert "approval: rejected=2/5 rejection_rate=0.4" in text
    assert "verifier: failed=1/4 failure_rate=0.25" in text
    assert "first_edit_latency: count=3 median=12.0 p95=30.0 max=44.0" in text
    assert "slow_first_edit_proposal: session=99 task=11 status=ready seconds=44.0" in text
    assert "first_write=#123 tool=edit_file path=src/mew/metrics.py" in text
    assert "first_model_summary: Planned too long before editing." in text
    assert (
        "side_project: rows=3 success=1 success_rate=0.333 failed=1 "
        "structural_repairs=1 codex_product_code_rescue_edits=2 rescue_rate=0.667"
        in text
    )
    assert "recommended_first_bottleneck: mew_first_rescue_partial" in text


def test_implementation_lane_baseline_wrapper_calls_existing_producers(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "ROADMAP_STATUS.md"
    source.write_text("# status\n", encoding="utf-8")
    calls = {}

    def fake_mew_first(*, source_path, limit):
        calls["mew_first"] = {"source_path": source_path, "limit": limit}
        return {
            "attempts_total": 1,
            "gate": {"clean_or_practical_successes": 1, "success_rate": 1.0, "success_gap": 0},
            "counts": {"result_class": {"clean_mew_first": 1}},
        }

    def fake_observation(state, *, kind=None, limit=None, sample_limit=None):
        calls["observation"] = {"state": state, "kind": kind, "limit": limit, "sample_limit": sample_limit}
        return {
            "reliability": {
                "approvals": {"total": 2, "rejected": 0},
                "verification": {"total": 2, "failed": 0},
            },
            "self_hosting": {"first_edit_proposal_seconds": {"count": 1, "median": 7.0, "p95": 7.0}},
        }

    def fake_side_project(*, path, limit):
        calls["side_project"] = {"path": path, "limit": limit}
        return {
            "ledger_path": str(path),
            "rows_total": 0,
            "gate": {
                "clean_or_practical": 0,
                "success_rate": None,
                "failed": 0,
                "structural_repairs_required": 0,
                "rescue_edits_total": 0,
            },
        }

    monkeypatch.setattr("mew.implementation_lane_baseline.summarize_mew_first_calibration", fake_mew_first)
    monkeypatch.setattr("mew.implementation_lane_baseline.build_observation_metrics", fake_observation)
    monkeypatch.setattr("mew.implementation_lane_baseline.summarize_side_project_dogfood", fake_side_project)

    summary = summarize_implementation_lane_baseline(
        state={"work_sessions": []},
        source_path=source,
        limit=10,
        sample_limit=2,
        side_project_ledger_path="ledger.jsonl",
    )

    assert calls["mew_first"] == {"source_path": source, "limit": 10}
    assert calls["observation"] == {
        "state": {"work_sessions": []},
        "kind": "coding",
        "limit": 10,
        "sample_limit": 2,
    }
    assert calls["side_project"] == {"path": "ledger.jsonl", "limit": 10}
    assert summary["inputs"]["side_project_ledger_path"] == "ledger.jsonl"
    assert summary["recommended_first_bottleneck"]["name"] == "none_measured"


def test_metrics_parser_accepts_implementation_lane_flags() -> None:
    args = build_parser().parse_args(
        [
            "metrics",
            "--implementation-lane",
            "--source-file",
            "status.md",
            "--side-project-ledger",
            "ledger.jsonl",
            "--json",
        ]
    )

    assert args.implementation_lane is True
    assert args.source_file == "status.md"
    assert args.side_project_ledger == "ledger.jsonl"
    assert args.json is True


def test_cmd_metrics_implementation_lane_text_output(monkeypatch, capsys) -> None:
    def fake_load_state():
        return {"work_sessions": []}

    def fake_summary(**kwargs):
        assert kwargs == {
            "state": {"work_sessions": []},
            "source_path": "status.md",
            "limit": 10,
            "sample_limit": 3,
            "side_project_ledger_path": "ledger.jsonl",
        }
        return {
            "inputs": {"source_path": "status.md"},
            "mew_first": {
                "attempts_total": 1,
                "clean_or_practical_successes": 0,
                "rescue_partial_count": 1,
                "rescue_partial_rate": 1.0,
                "success_gap": 1,
            },
            "approval": {"total": 4, "rejected": 1, "rejection_rate": 0.25},
            "verifier": {"total": 3, "failed": 0, "failure_rate": 0.0},
            "first_edit_latency": {
                "count": 2,
                "median": 7.0,
                "p95": 15.0,
                "max": 15.0,
                "samples": [
                    {
                        "session_id": 7,
                        "task_id": 2,
                        "task_status": "ready",
                        "first_edit_proposal_seconds": 15.0,
                        "first_write_tool_call_id": 8,
                        "first_write_tool": "edit_file",
                        "first_write_path": "src/mew/commands.py",
                        "started_at": "2026-04-19T00:00:15Z",
                        "first_model_summary": "Found implementation surface.",
                    }
                ],
            },
            "side_project": {
                "rows_total": 0,
                "clean_or_practical": 0,
                "success_rate": None,
                "failed": 0,
                "structural_repairs_required": 0,
                "rescue_edits_total": 0,
                "rescue_rate": None,
            },
            "recommended_first_bottleneck": {
                "name": "mew_first_rescue_partial",
                "value": 1,
                "reason": "measured",
            },
        }

    monkeypatch.setattr("mew.commands.load_state", fake_load_state)
    monkeypatch.setattr("mew.commands.summarize_implementation_lane_baseline", fake_summary)
    args = Namespace(
        implementation_lane=True,
        mew_first=False,
        source_file="status.md",
        side_project_ledger="ledger.jsonl",
        limit=10,
        sample_limit=3,
        json=False,
    )

    assert cmd_metrics(args) == 0
    output = capsys.readouterr().out
    assert "Implementation-lane baseline" in output
    assert "approval: rejected=1/4 rejection_rate=0.25" in output
    assert "slow_first_edit_proposal: session=7 task=2 status=ready seconds=15.0" in output
    assert "first_model_summary: Found implementation surface." in output
    assert "recommended_first_bottleneck: mew_first_rescue_partial" in output


def test_cmd_metrics_implementation_lane_defaults_to_wide_mew_first_window(monkeypatch, capsys) -> None:
    def fake_summary(**kwargs):
        assert kwargs["limit"] == 100
        return {
            "inputs": {"source_path": "ROADMAP_STATUS.md"},
            "mew_first": {
                "attempts_total": 0,
                "clean_or_practical_successes": 0,
                "rescue_partial_count": 0,
                "rescue_partial_rate": None,
                "success_gap": 0,
                "failure_classes": {},
            },
            "approval": {"total": 0, "rejected": 0, "rejection_rate": None},
            "verifier": {"total": 0, "failed": 0, "failure_rate": None},
            "first_edit_latency": {"count": 0, "median": None, "p95": None, "max": None},
            "side_project": {
                "rows_total": 0,
                "clean_or_practical": 0,
                "success_rate": None,
                "failed": 0,
                "structural_repairs_required": 0,
                "rescue_edits_total": 0,
                "rescue_rate": None,
            },
            "recommended_first_bottleneck": {
                "name": "none_measured",
                "value": 0,
                "reason": "none",
            },
        }

    monkeypatch.setattr("mew.commands.load_state", lambda: {"work_sessions": []})
    monkeypatch.setattr("mew.commands.summarize_implementation_lane_baseline", fake_summary)
    args = Namespace(
        implementation_lane=True,
        mew_first=False,
        source_file="ROADMAP_STATUS.md",
        side_project_ledger=None,
        limit=None,
        sample_limit=3,
        json=False,
    )

    assert cmd_metrics(args) == 0
    assert "Implementation-lane baseline" in capsys.readouterr().out
