from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

MAX_ITEMS = 8


@dataclass
class OutputPaths:
    dream: Path
    journal: Path


def load_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
        elif isinstance(item, dict):
            for key in ("summary", "title", "text", "note"):
                text = item.get(key)
                if isinstance(text, str) and text.strip():
                    items.append(text.strip())
                    break
    return items


def collect_learnings(state: dict[str, Any]) -> list[str]:
    learnings: list[str] = []
    for key in ("learnings", "changes", "decisions"):
        learnings.extend(_string_items(state.get(key)))
    for task in reversed(state.get("tasks", [])):
        if not isinstance(task, dict) or task.get("status") != "done":
            continue
        notes = task.get("notes")
        if not isinstance(notes, str):
            continue
        for line in reversed(notes.splitlines()):
            text = line.strip()
            if " done: " in text:
                learnings.append(text.split(" done: ", 1)[1].strip())
                break
            if text.startswith("Work session finished:"):
                learnings.append(text.removeprefix("Work session finished:").strip())
                break
        if len(learnings) >= MAX_ITEMS:
            break
    return learnings[:MAX_ITEMS]


def active_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = []
    for task in state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        if task.get("status") == "done":
            continue
        tasks.append(task)
    return tasks[:MAX_ITEMS]


def render_dream(day: str, state: dict[str, Any]) -> str:
    tasks = active_tasks(state)
    lines = [f"# Dream {day}", "", "## Active tasks"]
    if tasks:
        for task in tasks:
            title = task.get("title", "Untitled")
            status = task.get("status", "unknown")
            lines.append(f"- {title} [{status}]")
    else:
        lines.append("- No tasks recorded")
    lines.extend(["", "## Learnings"])
    learnings = collect_learnings(state)
    if learnings:
        for learning in learnings:
            lines.append(f"- {learning}")
    else:
        lines.append("- No learnings recorded")
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
    paths.dream.write_text(dream_text, encoding="utf-8")
    paths.journal.write_text(journal_text, encoding="utf-8")


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
