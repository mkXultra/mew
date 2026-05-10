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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_name", help="Terminal-Bench task name, e.g. make-mips-interpreter.")
    parser.add_argument(
        "--variant",
        action="append",
        dest="variants",
        help="WorkFrame variant to run. Repeat for multiple variants. Defaults to current.",
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


def run_variants(args: argparse.Namespace) -> dict[str, object]:
    variants = tuple(args.variants or DEFAULT_VARIANTS)
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
        "variants": list(variants),
        "results": results,
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
    return 1 if any(item.get("returncode") not in (None, 0) for item in summary["results"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
