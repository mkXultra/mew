#!/usr/bin/env python3
"""Render a markdown companion report from a mew session fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def render_report(session: dict[str, Any]) -> str:
    """Return a compact markdown companion report for a session fixture."""
    title = session.get("title") or session.get("id") or "Untitled session"
    status = session.get("status", "unknown")
    goal = session.get("goal", "")
    highlights = _as_list(session.get("highlights"))
    next_steps = _as_list(session.get("next_steps"))

    lines = [f"# Companion Log: {title}", "", f"- Status: {status}"]
    if goal:
        lines.append(f"- Goal: {goal}")

    if highlights:
        lines.extend(["", "## Highlights"])
        lines.extend(f"- {item}" for item in highlights)

    if next_steps:
        lines.extend(["", "## Next Steps"])
        lines.extend(f"- {item}" for item in next_steps)

    lines.append("")
    return "\n".join(lines)


def load_session(path: Path) -> dict[str, Any]:
    """Load a session fixture from JSON."""
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("fixture JSON must contain an object at the top level")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a markdown companion report from a fixture JSON file."
    )
    parser.add_argument("fixture", type=Path, help="Path to a fixture JSON file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Write the markdown report to this file instead of stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = render_report(load_session(args.fixture))
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
