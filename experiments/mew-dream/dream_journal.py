from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class OutputPaths:
    dream: Path
    journal: Path


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_date(state: dict[str, Any], explicit_date: str | None = None) -> str:
    if explicit_date:
        return explicit_date
    for key in ("date", "today", "current_date"):
        value = state.get(key)
        if isinstance(value, str) and value:
            return value
    return datetime.now().date().isoformat()


def build_paths(base_dir: Path, day: str) -> OutputPaths:
    return OutputPaths(
        dream=base_dir / ".mew" / "dreams" / f"{day}.md",
        journal=base_dir / ".mew" / "journal" / f"{day}.md",
    )


def render_dream(day: str, state: dict[str, Any]) -> str:
    tasks = state.get("tasks", [])
    lines = [f"# Dream {day}", "", "## Active tasks"]
    if tasks:
        for task in tasks:
            title = task.get("title", "Untitled")
            status = task.get("status", "unknown")
            lines.append(f"- {title} [{status}]")
    else:
        lines.append("- No tasks recorded")
    return "\n".join(lines) + "\n"


def render_journal(day: str, state: dict[str, Any]) -> str:
    notes = state.get("notes", [])
    lines = [f"# Journal {day}", "", "## Notes"]
    if notes:
        for note in notes:
            lines.append(f"- {note}")
    else:
        lines.append("- No notes recorded")
    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, dream_text: str, journal_text: str) -> None:
    paths.dream.parent.mkdir(parents=True, exist_ok=True)
    paths.journal.parent.mkdir(parents=True, exist_ok=True)
    paths.dream.write_text(dream_text)
    paths.journal.write_text(journal_text)


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_dream(day, state), render_journal(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate mew dream/journal markdown from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.dream)
    print(paths.journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
