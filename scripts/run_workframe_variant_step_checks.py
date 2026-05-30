#!/usr/bin/env python3
"""Run same-shape mew Harbor diagnostics for WorkFrame reducer variants."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


DEFAULT_VARIANTS = ("current",)
COMPARISON_PLAN_VARIANTS = {
    "m6-24-tool-harness": ("transcript_tool_nav", "transition_contract", "minimal"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_name", help="Terminal-Bench task name, e.g. make-mips-interpreter.")
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        help="WorkFrame variant to run. Repeat for multiple variants. Defaults to current.",
    )
    parser.add_argument(
        "--comparison-plan",
        choices=tuple(sorted(COMPARISON_PLAN_VARIANTS)),
        help=(
            "Use a reviewed same-shape variant set. Explicit --variant values "
            "still take precedence."
        ),
    )
    parser.add_argument("--mode", default="step-check-10min", choices=("step-check-10min", "speed-proof", "proof-5"))
    parser.add_argument("--jobs-root", type=Path, default=Path("proof-artifacts/terminal-bench/harbor-smoke"))
    parser.add_argument("--output", type=Path, help="Optional JSON summary path.")
    parser.add_argument("--max-parallel", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _extra_args(values: Sequence[str]) -> list[str]:
    args = list(values)
    if args and args[0] == "--":
        return args[1:]
    return args


def _command(task_name: str, *, variant: str, mode: str, jobs_root: Path, extra_args: Sequence[str]) -> list[str]:
    return [
        sys.executable,
        "scripts/run_harbor_mew_diagnostic.py",
        task_name,
        "--mode",
        mode,
        "--jobs-root",
        str(jobs_root),
        "--workframe-variant",
        variant,
        *_extra_args(extra_args),
    ]


def _parse_json_lines(text: str) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            items.append(data)
    return items


def select_variants(args: argparse.Namespace) -> tuple[str, ...]:
    if args.variants:
        return tuple(str(item) for item in args.variants)
    plan = str(getattr(args, "comparison_plan", "") or "")
    if plan:
        return COMPARISON_PLAN_VARIANTS[plan]
    return DEFAULT_VARIANTS


def summarize_variant_results(results: Sequence[dict[str, object]]) -> dict[str, object]:
    rows = [_variant_result_row(item) for item in results]
    red_flags = [
        {"variant": row["variant"], "reasons": row["red_reasons"]}
        for row in rows
        if row["status"] == "red"
    ]
    green_candidates = [
        row["variant"]
        for row in rows
        if row["status"] == "green"
    ]
    return {
        "schema_version": 1,
        "rows": rows,
        "red_flags": red_flags,
        "green_candidates": green_candidates,
        "default_flip_decision": "not_selected_by_runner",
        "default_flip_policy": (
            "This runner records same-shape evidence only; changing the runtime "
            "default requires a separate reviewed commit."
        ),
    }


def comparison_has_red(summary: dict[str, object]) -> bool:
    comparison = summary.get("comparison")
    if not isinstance(comparison, dict):
        return False
    rows = comparison.get("rows")
    if not isinstance(rows, list):
        return False
    return any(isinstance(row, dict) and row.get("status") == "red" for row in rows)


def _variant_result_row(result: dict[str, object]) -> dict[str, object]:
    summaries = _summary_items(result)
    first_summary = summaries[0] if summaries else {}
    returncode = result.get("returncode")
    dry_run = result.get("status") == "dry_run"
    rewards = [summary.get("external_reward") for summary in summaries]
    numeric_rewards = [_float_or_none(value) for value in rewards]
    numeric_rewards = [value for value in numeric_rewards if value is not None]
    observer_missing_count = sum(1 for summary in summaries if not _observer_detail_ok(summary))
    work_exit_codes = [summary.get("work_exit_code") for summary in summaries]
    nonzero_work_exit_codes = [
        value for value in work_exit_codes if _int_or_none(value) not in (None, 0)
    ]
    red_reasons: list[str] = []
    if dry_run:
        status = "dry_run"
    else:
        if not summaries:
            red_reasons.append("summary_missing")
        if returncode not in (None, 0):
            red_reasons.append("runner_returncode_nonzero")
        if nonzero_work_exit_codes:
            red_reasons.append("work_exit_code_nonzero")
        if observer_missing_count:
            red_reasons.append("observer_detail_missing")
        if any(value == 0.0 for value in numeric_rewards):
            red_reasons.append("external_reward_zero")
        status = "red" if red_reasons else "green"
    return {
        "variant": result.get("variant"),
        "status": status,
        "red_reasons": red_reasons,
        "trial_count": len(summaries),
        "returncode": returncode,
        "work_exit_code": first_summary.get("work_exit_code"),
        "work_exit_codes": work_exit_codes,
        "elapsed_seconds": result.get("elapsed_seconds"),
        "external_reward": first_summary.get("external_reward"),
        "external_rewards": rewards,
        "min_external_reward": min(numeric_rewards) if numeric_rewards else None,
        "max_external_reward": max(numeric_rewards) if numeric_rewards else None,
        "stop_reason": first_summary.get("stop_reason"),
        "stop_reasons": [summary.get("stop_reason") for summary in summaries],
        "model_turns": first_summary.get("model_turns"),
        "tool_calls": first_summary.get("tool_calls"),
        "tool_results": first_summary.get("tool_results"),
        "wall_elapsed_seconds": first_summary.get("wall_elapsed_seconds"),
        "prompt_chars": first_summary.get("prompt_chars"),
        "observer_detail_written": bool(first_summary.get("observer_detail_written")),
        "observer_missing_count": observer_missing_count,
        "proof_manifest_path": first_summary.get("proof_manifest_path", ""),
        "history_path": first_summary.get("history_path", ""),
        "trace_dir": first_summary.get("trace_dir", ""),
    }


def _summary_items(result: dict[str, object]) -> list[dict[str, object]]:
    summaries = result.get("summaries")
    if not isinstance(summaries, list):
        return []
    return [item for item in summaries if isinstance(item, dict)]


def _observer_detail_ok(summary: dict[str, object]) -> bool:
    return bool(summary.get("observer_detail_enabled")) and bool(
        summary.get("observer_detail_written")
    ) and bool(summary.get("observer_detail_exists"))


def _float_or_none(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def run_variants(args: argparse.Namespace) -> dict[str, object]:
    variants = select_variants(args)
    max_parallel = max(1, int(args.max_parallel or 1))
    pending = list(variants)
    running: list[tuple[str, subprocess.Popen[str], float, list[str]]] = []
    results: list[dict[str, object]] = []
    while pending or running:
        while pending and len(running) < max_parallel:
            variant = pending.pop(0)
            command = _command(
                args.task_name,
                variant=variant,
                mode=args.mode,
                jobs_root=args.jobs_root,
                extra_args=getattr(args, "diagnostic_args", ()),
            )
            if args.dry_run:
                results.append({"variant": variant, "command": command, "status": "dry_run"})
                continue
            running.append(
                (
                    variant,
                    subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE),
                    time.monotonic(),
                    command,
                )
            )
        if not running:
            continue
        next_running: list[tuple[str, subprocess.Popen[str], float, list[str]]] = []
        for variant, process, started, command in running:
            if process.poll() is None:
                next_running.append((variant, process, started, command))
                continue
            stdout, stderr = process.communicate()
            results.append(
                {
                    "variant": variant,
                    "command": command,
                    "returncode": process.returncode,
                    "elapsed_seconds": round(max(0.0, time.monotonic() - started), 3),
                    "summaries": _parse_json_lines(stdout),
                    "stdout_tail": stdout.splitlines()[-20:],
                    "stderr_tail": stderr.splitlines()[-20:],
                }
            )
        running = next_running
        if running:
            time.sleep(1)
    return {
        "schema_version": 1,
        "task_name": args.task_name,
        "mode": args.mode,
        "comparison_plan": str(getattr(args, "comparison_plan", "") or ""),
        "variants": list(variants),
        "results": results,
        "comparison": summarize_variant_results(results),
    }


def main(argv: Sequence[str] | None = None) -> int:
    args, diagnostic_args = build_parser().parse_known_args(argv)
    args.diagnostic_args = _extra_args(diagnostic_args)
    summary = run_variants(args)
    text = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    has_nonzero_return = any(item.get("returncode") not in (None, 0) for item in summary["results"])
    return 1 if has_nonzero_return or comparison_has_red(summary) else 0


if __name__ == "__main__":
    raise SystemExit(main())
