from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .cli_command import mew_command
from .state import open_questions as canonical_open_questions
from .tasks import task_kind
from .timeutil import now_iso, parse_time
from .work_session import build_work_session_effort, format_work_effort_brief


DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_DETAIL_ITEMS = 3
MAX_DETAIL_SUMMARY_LENGTH = 140
MAX_ACTION_ITEMS = 8


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


def normalize_kind_filter(kind: str | None) -> str:
    return normalize_text(kind).casefold()


def effective_task_kind(task: dict[str, Any]) -> str:
    return normalize_text(task.get("effective_kind")).casefold() or task_kind(task)


def task_matches_kind(task: dict[str, Any] | None, kind: str) -> bool:
    if not kind:
        return True
    if not isinstance(task, dict):
        return False
    return effective_task_kind(task) == kind


def task_ids_for_kind(state: dict[str, Any], kind: str) -> set[str]:
    if not kind:
        return set()
    return {
        str(task.get("id"))
        for task in state.get("tasks", [])
        if isinstance(task, dict) and task.get("id") is not None and task_matches_kind(task, kind)
    }


def related_task_identity(item: dict[str, Any]) -> str:
    task_id = item.get("related_task_id")
    if task_id is None:
        task_id = item.get("task_id")
    return "" if task_id is None else str(task_id)


def filter_items_by_task_kind(items: list[dict[str, Any]], task_ids: set[str], kind: str) -> list[dict[str, Any]]:
    if not kind:
        return items
    return [item for item in items if related_task_identity(item) in task_ids]


def stale_for_seconds(item: dict[str, Any], current_time: str | None, *keys: str) -> int | None:
    reference = parse_time(current_time) or parse_time(now_iso())
    if not reference:
        return None
    for key in keys:
        timestamp = parse_time(item.get(key))
        if not timestamp:
            continue
        try:
            return int(max(0.0, (reference - timestamp).total_seconds()))
        except TypeError:
            return None
    return None


def attach_action_metadata(action: dict[str, Any], reason: str, stale_seconds: int | None) -> dict[str, Any]:
    action["reason"] = reason
    if stale_seconds is not None:
        action["stale_for_seconds"] = stale_seconds
    return action


def format_stale_duration(seconds: Any) -> str:
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return ""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def open_tasks_for_desk(state: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    kind_filter = normalize_kind_filter(kind)
    return [
        task
        for task in state.get("tasks", [])
        if isinstance(task, dict) and normalize_text(task.get("status")).casefold() != "done"
        and task_matches_kind(task, kind_filter)
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


def active_work_sessions_for_desk(state: dict[str, Any], kind: str | None = None) -> list[dict[str, Any]]:
    kind_filter = normalize_kind_filter(kind)
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
        if kind_filter and not task_matches_kind(task, kind_filter):
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


def choose_pet_state(
    state: dict[str, Any],
    questions: list[dict[str, Any]] | None = None,
    attention: list[dict[str, Any]] | None = None,
    sessions: list[dict[str, Any]] | None = None,
) -> str:
    if questions is None:
        questions = open_questions_for_desk(state)
    if attention is None:
        attention = open_attention_for_desk(state)
    if sessions is None:
        sessions = active_work_sessions_for_desk(state)
    if questions or attention:
        return "alerting"
    phase = runtime_phase_for_desk(state)
    if phase in ("planning", "thinking", "precomputing"):
        return "thinking"
    if phase in ("applying", "acting", "executing", "committing"):
        return "typing"
    if sessions:
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
    kind = effective_task_kind(task)
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
    effort = build_work_session_effort(session)
    effort_summary = format_work_effort_brief(effort)
    item = {
        "kind": "work_session",
        "label": f"Work session #{session_id}" if session_id is not None else "Work session",
        "summary": compact_detail_summary(session.get("goal"), session.get("title")) or "active work",
        "status": normalize_text(session.get("status")) or "active",
        "effort": effort,
    }
    if effort_summary:
        item["effort_summary"] = effort_summary
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


def question_action_item(question: dict[str, Any], current_time: str | None = None) -> dict[str, Any]:
    question_id = question.get("id") or question.get("question_id")
    action = {
        "kind": "reply",
        "label": "Reply to question",
        "command": mew_command("chat"),
    }
    if question_id is not None:
        action["id"] = question_id
        action["question_id"] = question_id
        action["label"] = f"Reply to question #{question_id}"
        action["command"] = mew_command("reply", question_id, "<reply>")
    related_task_id = question.get("related_task_id")
    if related_task_id is not None:
        action["task_id"] = related_task_id
    return attach_action_metadata(
        action,
        "open question requires a reply",
        stale_for_seconds(question, current_time, "created_at", "updated_at"),
    )


def work_session_action_item(session: dict[str, Any], current_time: str | None = None) -> dict[str, Any]:
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
        action["id"] = session_id
        action["session_id"] = session_id
    effort = build_work_session_effort(session)
    effort_summary = format_work_effort_brief(effort)
    if effort_summary:
        action["effort_summary"] = effort_summary
    return attach_action_metadata(
        action,
        "active work session can be resumed",
        stale_for_seconds(session, current_time, "updated_at", "created_at"),
    )


def task_action_item(task: dict[str, Any], current_time: str | None = None) -> dict[str, Any]:
    task_id = task.get("id")
    if task_id is None:
        return attach_action_metadata(
            {"kind": "open_task", "label": "Open next task", "command": mew_command("task", "list")},
            "open task is available",
            stale_for_seconds(task, current_time, "updated_at", "created_at"),
        )
    kind = normalize_text(task.get("effective_kind")).casefold() or task_kind(task)
    command = mew_command("code", task_id) if kind == "coding" else mew_command("task", "show", task_id)
    return attach_action_metadata(
        {
            "kind": "open_task",
            "label": f"Open task #{task_id}",
            "command": command,
            "id": task_id,
            "task_id": task_id,
            "task_kind": kind,
        },
        "open task is available",
        stale_for_seconds(task, current_time, "updated_at", "created_at"),
    )


def attention_action_item(item: dict[str, Any], current_time: str | None = None) -> dict[str, Any]:
    attention_id = item.get("id")
    action = {
        "kind": "review_attention",
        "label": "Review attention",
        "command": mew_command("attention"),
    }
    if attention_id is not None:
        action["id"] = attention_id
        action["attention_id"] = attention_id
        action["label"] = f"Review attention #{attention_id}"
    for key in ("task_id", "agent_run_id", "question_id"):
        if item.get(key) is not None:
            action[key] = item.get(key)
    return attach_action_metadata(
        action,
        "independent attention item is open",
        stale_for_seconds(item, current_time, "created_at", "updated_at"),
    )


def action_identity(value: Any) -> str:
    return "" if value is None else str(value)


def _append_unique_action(actions: list[dict[str, Any]], seen: set[tuple[Any, ...]], action: dict[str, Any]) -> None:
    key = (
        action.get("kind"),
        action_identity(action.get("id")),
        action_identity(action.get("task_id")),
        action_identity(action.get("question_id")),
        action_identity(action.get("session_id")),
        action_identity(action.get("attention_id")),
        action.get("command"),
    )
    if key in seen:
        return
    seen.add(key)
    actions.append(action)


def desk_actions_for_desk(
    questions: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    sessions: list[dict[str, Any]],
    attention: list[dict[str, Any]],
    limit: int = MAX_ACTION_ITEMS,
    current_time: str | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    question_ids = {
        action_identity(question.get("id") or question.get("question_id"))
        for question in questions
        if question.get("id") is not None or question.get("question_id") is not None
    }
    active_task_ids = {action_identity(session.get("task_id")) for session in sessions if session.get("task_id") is not None}
    for question in questions:
        _append_unique_action(actions, seen, question_action_item(question, current_time=current_time))
    for session in reversed(sessions):
        _append_unique_action(actions, seen, work_session_action_item(session, current_time=current_time))
    for item in attention:
        if action_identity(item.get("question_id")) in question_ids:
            continue
        _append_unique_action(actions, seen, attention_action_item(item, current_time=current_time))
    for task in tasks:
        if action_identity(task.get("id")) in active_task_ids:
            continue
        _append_unique_action(actions, seen, task_action_item(task, current_time=current_time))
    return actions[: max(0, int(limit))]


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


def primary_action_for_desk(state: dict[str, Any], kind: str | None = None) -> dict[str, Any] | None:
    kind_filter = normalize_kind_filter(kind)
    task_ids = task_ids_for_kind(state, kind_filter)
    questions = filter_items_by_task_kind(open_questions_for_desk(state), task_ids, kind_filter)
    tasks = open_tasks_for_desk(state, kind_filter)
    sessions = active_work_sessions_for_desk(state, kind_filter)
    attention = filter_items_by_task_kind(open_attention_for_desk(state), task_ids, kind_filter)
    actions = desk_actions_for_desk(questions, tasks, sessions, attention, limit=1)
    return actions[0] if actions else None


def action_display_identity(action: dict[str, Any] | None) -> tuple[str, str]:
    if not isinstance(action, dict):
        return ("", "")
    return (normalize_text(action.get("kind")), normalize_text(action.get("command")))


def focus_summary(
    state: dict[str, Any],
    questions: list[dict[str, Any]] | None = None,
    sessions: list[dict[str, Any]] | None = None,
    tasks: list[dict[str, Any]] | None = None,
) -> str:
    if questions is None:
        questions = open_questions_for_desk(state)
    if questions:
        text = normalize_text(questions[0].get("text")) or "Question needs a reply"
        return f"Waiting for reply: {text}"
    if sessions is None:
        sessions = active_work_sessions_for_desk(state)
    if sessions:
        goal = normalize_text(sessions[-1].get("goal") or sessions[-1].get("title")) or "active work"
        return f"Working on: {goal}"
    if tasks is None:
        tasks = open_tasks_for_desk(state)
    if tasks:
        return f"Next: {task_label(tasks[0])}"
    return "No active work recorded"


def build_desk_view_model(
    state: dict[str, Any],
    explicit_date: str | None = None,
    current_time: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    day = resolve_desk_date(explicit_date)
    kind_filter = normalize_kind_filter(kind)
    task_ids = task_ids_for_kind(state, kind_filter)
    questions = filter_items_by_task_kind(open_questions_for_desk(state), task_ids, kind_filter)
    tasks = open_tasks_for_desk(state, kind_filter)
    sessions = active_work_sessions_for_desk(state, kind_filter)
    attention = filter_items_by_task_kind(open_attention_for_desk(state), task_ids, kind_filter)
    actions = desk_actions_for_desk(questions, tasks, sessions, attention, current_time=current_time)
    primary_action = actions[0] if actions else None
    view_model = {
        "date": day,
        "pet_state": choose_pet_state(state, questions=questions, attention=attention, sessions=sessions),
        "focus": focus_summary(state, questions=questions, sessions=sessions, tasks=tasks),
        "primary_action": primary_action,
        "actions": actions,
        "counts": {
            "open_tasks": len(tasks),
            "open_questions": len(questions),
            "active_work_sessions": len(sessions),
            "open_attention": len(attention),
        },
        "details": desk_detail_items(questions, tasks, sessions, attention),
    }
    if kind_filter:
        view_model["kind"] = kind_filter
    return view_model


def format_desk_view(view_model: dict[str, Any]) -> str:
    counts = view_model["counts"]
    lines = [
        f"Mew desk {view_model['date']}",
        f"pet_state: {view_model['pet_state']}",
        f"focus: {view_model['focus']}",
    ]
    kind = normalize_text(view_model.get("kind"))
    if kind:
        lines.insert(1, f"kind: {kind}")
    action = view_model.get("primary_action")
    if isinstance(action, dict):
        label = normalize_text(action.get("label"))
        command = normalize_text(action.get("command"))
        if label:
            lines.append(f"primary_action: {label}")
        if command:
            lines.append(f"primary_command: {command}")
    actions = view_model.get("actions")
    if isinstance(actions, list) and actions:
        action_lines = []
        primary_identity = action_display_identity(action)
        for item in actions[:MAX_ACTION_ITEMS]:
            if not isinstance(item, dict):
                continue
            if primary_identity != ("", "") and action_display_identity(item) == primary_identity:
                continue
            label = normalize_text(item.get("label")) or normalize_text(item.get("kind")) or "action"
            command = normalize_text(item.get("command"))
            reason = normalize_text(item.get("reason"))
            effort_summary = normalize_text(item.get("effort_summary"))
            detail = f"  - {label}"
            if reason:
                detail += f": {reason}"
            if effort_summary:
                detail += f" [{effort_summary}]"
            if item.get("stale_for_seconds") is not None:
                stale_text = format_stale_duration(item.get("stale_for_seconds"))
                if stale_text:
                    detail += f" stale_for={stale_text}"
            if command:
                detail += f" -> {command}"
            action_lines.append(detail)
        if action_lines:
            lines.append("actions:")
            lines.extend(action_lines)
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
                effort_summary = normalize_text(item.get("effort_summary"))
                command = normalize_text(item.get("command"))
                detail = f"  - {label}"
                if summary:
                    detail += f": {summary}"
                if effort_summary:
                    detail += f" [{effort_summary}]"
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
