from __future__ import annotations

import argparse

from scripts.run_workframe_variant_step_checks import comparison_has_red, select_variants, summarize_variant_results


def test_select_variants_uses_reviewed_m6_24_comparison_plan() -> None:
    args = argparse.Namespace(variants=None, comparison_plan="m6-24-tool-harness")

    assert select_variants(args) == ("transcript_tool_nav", "transition_contract", "minimal")


def test_select_variants_keeps_explicit_values_over_plan() -> None:
    args = argparse.Namespace(variants=["current"], comparison_plan="m6-24-tool-harness")

    assert select_variants(args) == ("current",)


def test_variant_summary_records_green_and_red_same_shape_rows() -> None:
    summary = summarize_variant_results(
        [
            {
                "variant": "transcript_tool_nav",
                "returncode": 0,
                "elapsed_seconds": 10.5,
                "summaries": [
                    {
                        "external_reward": 1.0,
                        "stop_reason": "done",
                        "model_turns": 4,
                        "tool_calls": 6,
                        "tool_results": 6,
                        "wall_elapsed_seconds": 120.0,
                        "prompt_chars": 12345,
                        "observer_detail_enabled": True,
                        "observer_detail_written": True,
                        "observer_detail_exists": True,
                        "proof_manifest_path": "/tmp/proof-manifest.json",
                        "history_path": "/tmp/history.json",
                        "trace_dir": "/tmp/normalized-trace",
                    }
                ],
            },
            {
                "variant": "transition_contract",
                "returncode": 2,
                "elapsed_seconds": 11.5,
                "summaries": [
                    {
                        "external_reward": 0.0,
                        "observer_detail_enabled": True,
                        "observer_detail_written": False,
                        "observer_detail_exists": False,
                    }
                ],
            },
        ]
    )

    rows = summary["rows"]
    assert rows[0]["status"] == "green"
    assert rows[0]["variant"] == "transcript_tool_nav"
    assert rows[0]["tool_calls"] == 6
    assert rows[0]["trial_count"] == 1
    assert rows[1]["status"] == "red"
    assert rows[1]["red_reasons"] == [
        "runner_returncode_nonzero",
        "observer_detail_missing",
        "external_reward_zero",
    ]
    assert summary["green_candidates"] == ["transcript_tool_nav"]
    assert summary["default_flip_decision"] == "not_selected_by_runner"
    assert comparison_has_red({"comparison": summary}) is True


def test_variant_summary_keeps_dry_run_out_of_green_candidates() -> None:
    summary = summarize_variant_results(
        [
            {
                "variant": "transcript_tool_nav",
                "status": "dry_run",
                "command": ["python", "scripts/run_harbor_mew_diagnostic.py"],
            }
        ]
    )

    assert summary["rows"][0]["status"] == "dry_run"
    assert summary["green_candidates"] == []
    assert summary["red_flags"] == []


def test_variant_summary_rejects_live_result_without_summary() -> None:
    summary = summarize_variant_results(
        [
            {
                "variant": "transition_contract",
                "returncode": 0,
                "summaries": [],
            }
        ]
    )

    assert summary["rows"][0]["status"] == "red"
    assert summary["rows"][0]["red_reasons"] == ["summary_missing"]
    assert summary["red_flags"] == [{"variant": "transition_contract", "reasons": ["summary_missing"]}]


def test_variant_summary_rejects_later_failed_trial() -> None:
    summary = summarize_variant_results(
        [
            {
                "variant": "transition_contract",
                "returncode": 0,
                "summaries": [
                    {
                        "external_reward": 1.0,
                        "observer_detail_enabled": True,
                        "observer_detail_written": True,
                        "observer_detail_exists": True,
                    },
                    {
                        "external_reward": 0.0,
                        "observer_detail_enabled": True,
                        "observer_detail_written": True,
                        "observer_detail_exists": True,
                    },
                ],
            }
        ]
    )

    row = summary["rows"][0]
    assert row["status"] == "red"
    assert row["trial_count"] == 2
    assert row["external_rewards"] == [1.0, 0.0]
    assert row["min_external_reward"] == 0.0
    assert row["red_reasons"] == ["external_reward_zero"]
    assert summary["green_candidates"] == []
