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
    self_memory: Path


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
    return OutputPaths(self_memory=base_dir / ".mew" / "self" / f"learned-{day}.md")


def unique(items: list[str], limit: int = MAX_ITEMS) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = " ".join(item.strip().split())
        if not normalized or normalized.casefold() in seen:
            continue
        seen.add(normalized.casefold())
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def normalize_text(item: str) -> str:
    return " ".join(item.strip().split())


def string_items(value: Any) -> list[str]:
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


def task_note_learning(task: dict[str, Any]) -> str:
    notes = task.get("notes")
    if not isinstance(notes, str):
        return ""
    for line in reversed(notes.splitlines()):
        text = line.strip()
        if " done: " in text:
            return text.split(" done: ", 1)[1].strip()
        if text.startswith("Work session finished:"):
            return text.removeprefix("Work session finished:").strip()
    return ""


def raw_self_learning_candidates(state: dict[str, Any]) -> list[str]:
    learnings = []
    for key in ("learnings", "changes", "decisions"):
        learnings.extend(string_items(state.get(key)))
    for task in reversed(state.get("tasks", [])):
        if not isinstance(task, dict) or task.get("status") != "done":
            continue
        learning = task_note_learning(task)
        if learning:
            learnings.append(learning)
    return learnings


def infer_repeated_traits(state: dict[str, Any]) -> list[str]:
    counts: dict[str, int] = {}
    originals: dict[str, str] = {}
    for item in raw_self_learning_candidates(state):
        normalized = normalize_text(item)
        if not normalized:
            continue
        key = normalized.casefold()
        counts[key] = counts.get(key, 0) + 1
        originals.setdefault(key, normalized)
    return [originals[key] for key, count in counts.items() if count >= 2]


def collect_traits(state: dict[str, Any]) -> list[str]:
    traits = []
    traits.extend(string_items(state.get("traits")))
    self_memory = state.get("self_memory")
    if isinstance(self_memory, dict):
        traits.extend(string_items(self_memory.get("traits")))
    traits.extend(infer_repeated_traits(state))
    return unique(traits)


def collect_self_learnings(state: dict[str, Any]) -> list[str]:
    learnings = raw_self_learning_candidates(state)
    return unique(learnings)


def task_title_by_id(state: dict[str, Any]) -> dict[str, str]:
    titles = {}
    for task in state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        title = task.get("title")
        if task_id is not None and isinstance(title, str) and title.strip():
            titles[str(task_id)] = title.strip()
    return titles


def active_work_sessions(state: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = []
    single_session = state.get("work_session")
    if isinstance(single_session, dict):
        sessions.append(single_session)
    raw_sessions = state.get("work_sessions")
    if isinstance(raw_sessions, list):
        sessions.extend(session for session in raw_sessions if isinstance(session, dict))
    return [session for session in sessions if session.get("status") == "active"][-MAX_ITEMS:]


def collect_continuity_cues(state: dict[str, Any]) -> list[str]:
    titles = task_title_by_id(state)
    cues = []
    for session in active_work_sessions(state):
        session_id = session.get("id", "?")
        goal = str(session.get("goal") or session.get("title") or "Untitled").strip()
        task_id = session.get("task_id")
        task = f" task #{task_id}" if task_id is not None else ""
        task_title = titles.get(str(task_id), "") if task_id is not None else ""
        if task_title:
            task = f"{task}: {task_title}"
        phase = session.get("phase") or "unknown phase"
        cue = f"Work session #{session_id}{task} is {phase}: {goal}"
        next_action = session.get("next_action")
        if isinstance(next_action, str) and next_action.strip():
            cue = f"{cue}; next: {next_action.strip()}"
        cues.append(cue)
    return unique(cues)


def render_self_memory(day: str, state: dict[str, Any]) -> str:
    lines = [f"# Mew Self Memory {day}", ""]

    lines.append("## Durable traits")
    traits = collect_traits(state)
    if traits:
        for trait in traits:
            lines.append(f"- {trait}")
    else:
        lines.append("- No durable traits recorded")

    lines.extend(["", "## Recent self learnings"])
    learnings = collect_self_learnings(state)
    if learnings:
        for learning in learnings:
            lines.append(f"- {learning}")
    else:
        lines.append("- No self learnings recorded")

    lines.extend(["", "## Continuity cues"])
    cues = collect_continuity_cues(state)
    if cues:
        for cue in cues:
            lines.append(f"- {cue}")
    else:
        lines.append("- No active continuity cues")

    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, self_memory_text: str) -> None:
    paths.self_memory.parent.mkdir(parents=True, exist_ok=True)
    paths.self_memory.write_text(self_memory_text, encoding="utf-8")


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_self_memory(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate mew self-memory markdown from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.self_memory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
