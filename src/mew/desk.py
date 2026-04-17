from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .state import open_questions as canonical_open_questions


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value

def resolve_desk_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(datetime.now().date().isoformat())


def normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def open_tasks_for_desk(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() != "done"
    ]


def open_questions_for_desk(state: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(state.get("questions"), list):
        return list(canonical_open_questions(state))
    questions = []
    for message in state.get("outbox", []):
        if not isinstance(message, dict):
            continue
        if message.get("requires_reply") and not message.get("answered_at"):
            questions.append(message)
    return questions


def open_attention_for_desk(state: dict[str, Any]) -> list[dict[str, Any]]:
    attention = state.get("attention")
    if not isinstance(attention, dict):
        return []
    items = attention.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict) and item.get("status") == "open"]


def active_work_sessions_for_desk(state: dict[str, Any]) -> list[dict[str, Any]]:
    sessions = []
    single_session = state.get("work_session")
    if isinstance(single_session, dict):
        sessions.append(single_session)
    raw_sessions = state.get("work_sessions")
    if isinstance(raw_sessions, list):
        sessions.extend(session for session in raw_sessions if isinstance(session, dict))
    tasks_by_id = {str(task.get("id")): task for task in state.get("tasks", []) if isinstance(task, dict)}
    active = []
    seen = set()
    for session in sessions:
        session_id = session.get("id")
        key = str(session_id) if session_id is not None else f"object:{id(session)}"
        if key in seen:
            continue
        seen.add(key)
        if session.get("status") != "active":
            continue
        task_id = session.get("task_id")
        task = tasks_by_id.get(str(task_id)) if task_id is not None else None
        if task and task.get("status") == "done":
            continue
        active.append(session)
    return active


def runtime_phase_for_desk(state: dict[str, Any]) -> str:
    runtime = state.get("runtime_status")
    if not isinstance(runtime, dict):
        return ""
    if runtime.get("state") != "running":
        return ""
    return normalize_text(runtime.get("current_phase"))


def choose_pet_state(state: dict[str, Any]) -> str:
    if open_questions_for_desk(state) or open_attention_for_desk(state):
        return "alerting"
    phase = runtime_phase_for_desk(state)
    if phase in ("planning", "thinking", "precomputing"):
        return "thinking"
    if phase in ("applying", "acting", "executing", "committing"):
        return "typing"
    if active_work_sessions_for_desk(state):
        return "typing"
    return "sleeping"


def task_label(task: dict[str, Any]) -> str:
    task_id = task.get("id")
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    prefix = f"#{task_id} " if task_id is not None else ""
    return f"{prefix}{title} [{status}]"


def focus_summary(state: dict[str, Any]) -> str:
    questions = open_questions_for_desk(state)
    if questions:
        text = normalize_text(questions[0].get("text")) or "Question needs a reply"
        return f"Waiting for reply: {text}"
    sessions = active_work_sessions_for_desk(state)
    if sessions:
        goal = normalize_text(sessions[-1].get("goal") or sessions[-1].get("title")) or "active work"
        return f"Working on: {goal}"
    tasks = open_tasks_for_desk(state)
    if tasks:
        return f"Next: {task_label(tasks[0])}"
    return "No active work recorded"


def build_desk_view_model(state: dict[str, Any], explicit_date: str | None = None) -> dict[str, Any]:
    day = resolve_desk_date(explicit_date)
    questions = open_questions_for_desk(state)
    tasks = open_tasks_for_desk(state)
    sessions = active_work_sessions_for_desk(state)
    attention = open_attention_for_desk(state)
    return {
        "date": day,
        "pet_state": choose_pet_state(state),
        "focus": focus_summary(state),
        "counts": {
            "open_tasks": len(tasks),
            "open_questions": len(questions),
            "active_work_sessions": len(sessions),
            "open_attention": len(attention),
        },
    }


def format_desk_view(view_model: dict[str, Any]) -> str:
    counts = view_model["counts"]
    return "\n".join(
        [
            f"Mew desk {view_model['date']}",
            f"pet_state: {view_model['pet_state']}",
            f"focus: {view_model['focus']}",
            f"open_tasks: {counts['open_tasks']}",
            f"open_questions: {counts['open_questions']}",
            f"active_work_sessions: {counts['active_work_sessions']}",
            f"open_attention: {counts['open_attention']}",
        ]
    )


def render_desk_markdown(view_model: dict[str, Any]) -> str:
    lines = format_desk_view(view_model).splitlines()
    title = lines[0] if lines else "Mew desk"
    body = "\n".join(f"- {line}" for line in lines[1:])
    return f"# {title}\n\n{body}\n"


def write_desk_view(view_model: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    day = view_model["date"]
    base = output_dir / ".mew" / "desk"
    base.mkdir(parents=True, exist_ok=True)
    json_path = base / f"{day}.json"
    markdown_path = base / f"{day}.md"
    json_path.write_text(json.dumps(view_model, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_desk_markdown(view_model), encoding="utf-8")
    return json_path, markdown_path
