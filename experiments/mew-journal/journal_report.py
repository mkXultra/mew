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
    return OutputPaths(journal=base_dir / ".mew" / "journal" / f"{day}.md")


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def unique(items: list[str], limit: int = MAX_ITEMS) -> list[str]:
    seen = set()
    result = []
    for item in items:
        normalized = normalize_text(item)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def task_ref(task: dict[str, Any]) -> str:
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    kind = normalize_text(task.get("kind"))
    task_id = task.get("id")
    prefix = f"#{task_id} " if task_id is not None else ""
    suffix = f" [{status}"
    if kind:
        suffix = f"{suffix}/{kind}"
    return f"{prefix}{title}{suffix}]"


def priority_rank(task: dict[str, Any]) -> tuple[int, int]:
    status_rank = {
        "running": 0,
        "in_progress": 0,
        "ready": 1,
        "todo": 2,
        "blocked": 3,
    }
    priority_rank_map = {"high": 0, "normal": 1, "low": 2}
    status = normalize_text(task.get("status")).casefold()
    priority = normalize_text(task.get("priority")).casefold()
    return (status_rank.get(status, 4), priority_rank_map.get(priority, 1))


def active_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = [task for task in state.get("tasks", []) if isinstance(task, dict) and task.get("status") != "done"]
    return sorted(tasks, key=priority_rank)[:MAX_ITEMS]


def completed_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = [task for task in state.get("tasks", []) if isinstance(task, dict) and task.get("status") == "done"]
    return list(reversed(tasks))[:MAX_ITEMS]


def task_done_note(task: dict[str, Any]) -> str:
    notes = task.get("notes")
    if not isinstance(notes, str):
        return ""
    for line in reversed(notes.splitlines()):
        text = line.strip()
        if " done: " in text:
            return normalize_text(text.split(" done: ", 1)[1])
        if text.startswith("Work session finished:"):
            return normalize_text(text.removeprefix("Work session finished:"))
    return ""


def task_title_by_id(state: dict[str, Any]) -> dict[str, str]:
    titles = {}
    for task in state.get("tasks", []):
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        title = normalize_text(task.get("title"))
        if task_id is not None and title:
            titles[str(task_id)] = title
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


def work_session_lines(state: dict[str, Any]) -> list[str]:
    titles = task_title_by_id(state)
    lines = []
    for session in active_work_sessions(state):
        session_id = session.get("id", "?")
        goal = normalize_text(session.get("goal") or session.get("title")) or "Untitled"
        phase = normalize_text(session.get("phase")) or "unknown"
        task_id = session.get("task_id")
        task = ""
        if task_id is not None:
            title = titles.get(str(task_id), "")
            task = f" task #{task_id}"
            if title:
                task = f"{task}: {title}"
        line = f"Work session #{session_id}{task} is {phase}: {goal}"
        next_action = normalize_text(session.get("next_action"))
        if next_action:
            line = f"{line}; next: {next_action}"
        lines.append(line)
    return unique(lines)


def open_question_lines(state: dict[str, Any]) -> list[str]:
    lines = []
    for message in state.get("outbox", []):
        if not isinstance(message, dict):
            continue
        if not message.get("requires_reply") or message.get("answered_at"):
            continue
        text = normalize_text(message.get("text"))
        if not text:
            continue
        question_id = message.get("question_id") or message.get("id")
        task_id = message.get("related_task_id")
        prefix = f"Question #{question_id}"
        if task_id is not None:
            prefix = f"{prefix} for task #{task_id}"
        lines.append(f"{prefix}: {text}")
    return unique(lines)


def runtime_effect_lines(state: dict[str, Any]) -> list[str]:
    lines = []
    effects = state.get("runtime_effects")
    if not isinstance(effects, list):
        return lines
    for effect in reversed(effects):
        if not isinstance(effect, dict):
            continue
        effect_id = effect.get("id", "?")
        reason = normalize_text(effect.get("reason")) or "unknown"
        status = normalize_text(effect.get("status")) or "unknown"
        summary = normalize_text(effect.get("summary") or effect.get("outcome"))
        actions = ",".join(effect.get("action_types") or []) or "-"
        line = f"effect #{effect_id} [{status}/{reason}] actions={actions}"
        if summary:
            line = f"{line}: {summary}"
        lines.append(line)
        if len(lines) >= MAX_ITEMS:
            break
    return lines


def morning_note(state: dict[str, Any]) -> str:
    questions = open_question_lines(state)
    if questions:
        return "Start by clearing the oldest unanswered question before adding more autonomous work."
    sessions = work_session_lines(state)
    if sessions:
        return "Resume the active work session first so context does not leak across days."
    tasks = active_tasks(state)
    if tasks:
        return f"Start with {task_ref(tasks[0])}."
    return "No active work is recorded; choose one small useful task before the day gets noisy."


def tomorrow_hints(state: dict[str, Any]) -> list[str]:
    hints = []
    for question in open_question_lines(state):
        hints.append(f"Answer or close: {question}")
    for session in work_session_lines(state):
        hints.append(f"Resume: {session}")
    for task in active_tasks(state):
        hints.append(f"Move forward: {task_ref(task)}")
    return unique(hints)


def render_list(lines: list[str], fallback: str) -> list[str]:
    if not lines:
        return [f"- {fallback}"]
    return [f"- {line}" for line in lines[:MAX_ITEMS]]


def render_journal(day: str, state: dict[str, Any]) -> str:
    completed = []
    for task in completed_tasks(state):
        note = task_done_note(task)
        line = task_ref(task)
        if note:
            line = f"{line}: {note}"
        completed.append(line)

    active = [task_ref(task) for task in active_tasks(state)]
    questions = open_question_lines(state)
    sessions = work_session_lines(state)
    effects = runtime_effect_lines(state)
    hints = tomorrow_hints(state)

    lines = [
        f"# Mew Journal {day}",
        "",
        "## Morning",
        "",
        "### Yesterday",
        *render_list(completed or effects, "No completed work or runtime effects recorded"),
        "",
        "### Today",
        *render_list(active, "No active tasks recorded"),
        "",
        "### Mew note",
        f"- {morning_note(state)}",
        "",
        "## Evening",
        "",
        "### Progress",
        *render_list(completed + effects, "No progress recorded"),
        "",
        "### Stuck points",
        *render_list(questions + sessions, "No stuck points recorded"),
        "",
        "### Tomorrow hints",
        *render_list(hints, "Pick one small task and make it ready"),
    ]
    return "\n".join(lines) + "\n"


def write_outputs(paths: OutputPaths, journal_text: str) -> None:
    paths.journal.parent.mkdir(parents=True, exist_ok=True)
    paths.journal.write_text(journal_text, encoding="utf-8")


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, render_journal(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a mew morning/evening journal from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.journal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
