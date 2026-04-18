from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .cli_command import mew_command
from .state import open_questions as canonical_open_questions
from .tasks import task_kind


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DETAIL_ITEMS = 3
MAX_DETAIL_SUMMARY_LENGTH = 140


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


def compact_detail_summary(*values: Any) -> str:
    text = " ".join(part for part in (normalize_text(value) for value in values) if part)
    if not text:
        return ""
    if len(text) <= MAX_DETAIL_SUMMARY_LENGTH:
        return text
    return text[: MAX_DETAIL_SUMMARY_LENGTH - 3].rstrip() + "..."


def question_detail_item(question: dict[str, Any]) -> dict[str, Any]:
    question_id = question.get("id") or question.get("question_id")
    item = {
        "kind": "question",
        "label": f"Question #{question_id}" if question_id is not None else "Question",
        "summary": compact_detail_summary(question.get("text")) or "Question needs a reply",
        "status": normalize_text(question.get("status")) or "open",
    }
    if question_id is not None:
        item["id"] = question_id
        item["command"] = mew_command("reply", question_id, "<reply>")
    related_task_id = question.get("related_task_id")
    if related_task_id is not None:
        item["task_id"] = related_task_id
    return item


def task_detail_item(task: dict[str, Any]) -> dict[str, Any]:
    task_id = task.get("id")
    kind = normalize_text(task.get("effective_kind")).casefold() or task_kind(task)
    item = {
        "kind": "task",
        "label": f"Task #{task_id}" if task_id is not None else "Task",
        "summary": compact_detail_summary(task.get("title")) or "Untitled",
        "status": normalize_text(task.get("status")) or "unknown",
        "task_kind": kind,
    }
    if task_id is not None:
        item["id"] = task_id
        item["task_id"] = task_id
        item["command"] = mew_command("code", task_id) if kind == "coding" else mew_command("task", "show", task_id)
    return item


def work_session_detail_item(session: dict[str, Any]) -> dict[str, Any]:
    session_id = session.get("id")
    task_id = session.get("task_id")
    item = {
        "kind": "work_session",
        "label": f"Work session #{session_id}" if session_id is not None else "Work session",
        "summary": compact_detail_summary(session.get("goal"), session.get("title")) or "active work",
        "status": normalize_text(session.get("status")) or "active",
    }
    if session_id is not None:
        item["id"] = session_id
    if task_id is not None:
        item["task_id"] = task_id
        item["command"] = mew_command("work", task_id, "--session", "--resume", "--allow-read", ".")
    else:
        item["command"] = mew_command("work", "--session", "--resume", "--allow-read", ".")
    return item


def attention_detail_item(item: dict[str, Any]) -> dict[str, Any]:
    attention_id = item.get("id")
    title = normalize_text(item.get("title")) or "Needs attention"
    reason = normalize_text(item.get("reason"))
    detail = {
        "kind": "attention",
        "label": f"Attention #{attention_id}" if attention_id is not None else "Attention",
        "summary": compact_detail_summary(title, reason),
        "status": normalize_text(item.get("status")) or "open",
        "command": mew_command("attention"),
    }
    if attention_id is not None:
        detail["id"] = attention_id
    for key in ("task_id", "agent_run_id", "question_id"):
        if item.get(key) is not None:
            detail[key] = item.get(key)
    return detail


def desk_detail_items(
    questions: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    attention: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        "questions": [question_detail_item(question) for question in questions[:MAX_DETAIL_ITEMS]],
        "tasks": [task_detail_item(task) for task in tasks[:MAX_DETAIL_ITEMS]],
        "active_work_sessions": [work_session_detail_item(session) for session in sessions[-MAX_DETAIL_ITEMS:]],
        "attention": [attention_detail_item(item) for item in attention[:MAX_DETAIL_ITEMS]],
    }


def primary_action_for_desk(state: dict[str, Any]) -> dict[str, Any] | None:
    questions = open_questions_for_desk(state)
    if questions:
        question = questions[0]
        question_id = question.get("id") or question.get("question_id")
        action = {
            "kind": "reply",
            "label": "Reply to question",
            "command": mew_command("chat"),
        }
        if question_id is not None:
            action["question_id"] = question_id
            action["label"] = f"Reply to question #{question_id}"
            action["command"] = mew_command("reply", question_id, "<reply>")
        related_task_id = question.get("related_task_id")
        if related_task_id is not None:
            action["task_id"] = related_task_id
        return action

    sessions = active_work_sessions_for_desk(state)
    if sessions:
        session = sessions[-1]
        task_id = session.get("task_id")
        session_id = session.get("id")
        action = {
            "kind": "resume_work",
            "label": "Resume active work",
            "command": mew_command("work", "--session", "--resume", "--allow-read", "."),
        }
        if task_id is not None:
            action["task_id"] = task_id
            action["label"] = f"Resume task #{task_id}"
            action["command"] = mew_command("work", task_id, "--session", "--resume", "--allow-read", ".")
        if session_id is not None:
            action["session_id"] = session_id
        return action

    tasks = open_tasks_for_desk(state)
    if tasks:
        task = tasks[0]
        task_id = task.get("id")
        if task_id is None:
            return {"kind": "open_task", "label": "Open next task", "command": mew_command("task", "list")}
        kind = normalize_text(task.get("effective_kind")).casefold() or task_kind(task)
        command = mew_command("code", task_id) if kind == "coding" else mew_command("task", "show", task_id)
        return {
            "kind": "open_task",
            "label": f"Open task #{task_id}",
            "command": command,
            "task_id": task_id,
        }

    return None


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
    primary_action = primary_action_for_desk(state)
    return {
        "date": day,
        "pet_state": choose_pet_state(state),
        "focus": focus_summary(state),
        "primary_action": primary_action,
        "counts": {
            "open_tasks": len(tasks),
            "open_questions": len(questions),
            "active_work_sessions": len(sessions),
            "open_attention": len(attention),
        },
        "details": desk_detail_items(questions, tasks, sessions, attention),
    }


def format_desk_view(view_model: dict[str, Any]) -> str:
    counts = view_model["counts"]
    lines = [
        f"Mew desk {view_model['date']}",
        f"pet_state: {view_model['pet_state']}",
        f"focus: {view_model['focus']}",
    ]
    action = view_model.get("primary_action")
    if isinstance(action, dict):
        label = normalize_text(action.get("label"))
        command = normalize_text(action.get("command"))
        if label:
            lines.append(f"primary_action: {label}")
        if command:
            lines.append(f"primary_command: {command}")
    lines.extend(
        [
            f"open_tasks: {counts['open_tasks']}",
            f"open_questions: {counts['open_questions']}",
            f"active_work_sessions: {counts['active_work_sessions']}",
            f"open_attention: {counts['open_attention']}",
        ]
    )
    details = view_model.get("details")
    if isinstance(details, dict):
        for key in ("questions", "active_work_sessions", "tasks", "attention"):
            items = details.get(key)
            if not isinstance(items, list) or not items:
                continue
            lines.append(f"{key}:")
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = normalize_text(item.get("label")) or key
                summary = normalize_text(item.get("summary"))
                command = normalize_text(item.get("command"))
                detail = f"  - {label}"
                if summary:
                    detail += f": {summary}"
                if command:
                    detail += f" -> {command}"
                lines.append(detail)
    return "\n".join(lines)


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
