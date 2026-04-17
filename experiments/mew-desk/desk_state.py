from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class OutputPaths:
    json_path: Path
    markdown_path: Path


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


def build_paths(output_dir: Path, day: str) -> OutputPaths:
    base = output_dir / ".mew" / "desk"
    return OutputPaths(json_path=base / f"{day}.json", markdown_path=base / f"{day}.md")


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def open_tasks(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() != "done"
    ]


def open_questions(state: dict[str, Any]) -> list[dict[str, Any]]:
    questions = []
    for message in state.get("outbox", []):
        if not isinstance(message, dict):
            continue
        if message.get("requires_reply") and not message.get("answered_at"):
            questions.append(message)
    return questions


def open_attention_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    attention = state.get("attention")
    if not isinstance(attention, dict):
        return []
    items = attention.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("status") == "open"]


def active_work_sessions(state: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = []
    single_session = state.get("work_session")
    if isinstance(single_session, dict):
        sessions.append(single_session)
    raw_sessions = state.get("work_sessions")
    if isinstance(raw_sessions, list):
        sessions.extend(session for session in raw_sessions if isinstance(session, dict))
    return [session for session in sessions if session.get("status") == "active"]


def runtime_phase(state: dict[str, Any]) -> str:
    runtime = state.get("runtime_status")
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("state") != "running":
        return ""
    return normalize_text(runtime.get("current_phase"))


def choose_pet_state(state: dict[str, Any]) -> str:
    if open_questions(state) or open_attention_items(state):
        return "alerting"
    phase = runtime_phase(state)
    if phase in ("planning", "thinking"):
        return "thinking"
    if phase in ("applying", "acting", "executing"):
        return "typing"
    if active_work_sessions(state):
        return "typing"
    return "sleeping"


def task_label(task: dict[str, Any]) -> str:
    task_id = task.get("id")
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    prefix = f"#{task_id} " if task_id is not None else ""
    return f"{prefix}{title} [{status}]"


def focus_summary(state: dict[str, Any]) -> str:
    questions = open_questions(state)
    if questions:
        text = normalize_text(questions[0].get("text")) or "Question needs a reply"
        return f"Waiting for reply: {text}"
    sessions = active_work_sessions(state)
    if sessions:
        goal = normalize_text(sessions[-1].get("goal") or sessions[-1].get("title")) or "active work"
        return f"Working on: {goal}"
    tasks = open_tasks(state)
    if tasks:
        return f"Next: {task_label(tasks[0])}"
    return "No active work recorded"


def build_view_model(day: str, state: dict[str, Any]) -> dict[str, Any]:
    questions = open_questions(state)
    tasks = open_tasks(state)
    sessions = active_work_sessions(state)
    return {
        "date": day,
        "pet_state": choose_pet_state(state),
        "focus": focus_summary(state),
        "counts": {
            "open_tasks": len(tasks),
            "open_questions": len(questions),
            "active_work_sessions": len(sessions),
            "open_attention": len(open_attention_items(state)),
        },
    }


def render_markdown(view_model: dict[str, Any]) -> str:
    counts = view_model["counts"]
    return "\n".join(
        [
            f"# Mew Desk {view_model['date']}",
            "",
            f"- pet_state: {view_model['pet_state']}",
            f"- focus: {view_model['focus']}",
            f"- open_tasks: {counts['open_tasks']}",
            f"- open_questions: {counts['open_questions']}",
            f"- active_work_sessions: {counts['active_work_sessions']}",
            f"- open_attention: {counts['open_attention']}",
            "",
        ]
    )


def write_outputs(paths: OutputPaths, view_model: dict[str, Any]) -> None:
    paths.json_path.parent.mkdir(parents=True, exist_ok=True)
    paths.json_path.write_text(json.dumps(view_model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    paths.markdown_path.write_text(render_markdown(view_model), encoding="utf-8")


def generate(state_path: Path, output_dir: Path, explicit_date: str | None = None) -> OutputPaths:
    state = load_state(state_path)
    day = resolve_date(state, explicit_date)
    paths = build_paths(output_dir, day)
    write_outputs(paths, build_view_model(day, state))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a mew desktop-pet view model from state JSON")
    parser.add_argument("state_path", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("."))
    parser.add_argument("--date")
    args = parser.parse_args(argv)

    paths = generate(args.state_path, args.output_dir, args.date)
    print(paths.json_path)
    print(paths.markdown_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
