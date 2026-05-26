#!/usr/bin/env python3
"""Compare provider-visible request shape across saved native artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mew.implement_lane.provider_visible_artifact_compare import (  # noqa: E402
    write_provider_visible_artifact_compare_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--artifact",
        action="append",
        required=True,
        metavar="LABEL=PATH",
        help="artifact label plus artifact root or native-provider-requests.json path; repeatable",
    )
    parser.add_argument("--out-json", required=True, help="output JSON report path")
    parser.add_argument("--out-md", required=True, help="output Markdown report path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        artifacts = [_parse_artifact(value) for value in args.artifact]
        report = write_provider_visible_artifact_compare_report(
            artifacts=artifacts,
            out_json=args.out_json,
            out_md=args.out_md,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary should report artifact problems.
        print(f"compare provider-visible artifacts: {exc}", file=sys.stderr)
        return 1
    print(f"provider-visible compare JSON: {Path(args.out_json).expanduser().resolve(strict=False)}")
    print(f"provider-visible compare Markdown: {Path(args.out_md).expanduser().resolve(strict=False)}")
    for line in report.get("diff_summary") or []:
        print(f"- {line}")
    return 0


def _parse_artifact(value: str) -> tuple[str, str]:
    label, sep, path = value.partition("=")
    if not sep or not label.strip() or not path.strip():
        raise ValueError("--artifact must be LABEL=PATH")
    return label.strip(), path.strip()


if __name__ == "__main__":
    raise SystemExit(main())
