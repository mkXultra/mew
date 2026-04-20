from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .desk import active_work_sessions_for_desk, open_tasks_for_desk
from .report_io import write_generated_report
from .self_memory import collect_self_learnings, normalize_text, task_title_by_id
from .timeutil import now_date_iso
from .work_session import build_work_session_resume


MAX_ITEMS = 8
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


def resolve_dream_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(now_date_iso())


def dream_path(output_dir: Path, day: str) -> Path:
    return output_dir / ".mew" / "dreams" / f"{day}.md"


def task_ref(task: dict[str, Any]) -> str:
    title = normalize_text(task.get("title")) or "Untitled"
    status = normalize_text(task.get("status")) or "unknown"
    task_id = task.get("id")
    prefix = f"#{task_id} " if task_id is not None else ""
    return f"{prefix}{title} [{status}]"


def work_session_lines(state: dict[str, Any]) -> list[str]:
    titles = task_title_by_id(state)
    tasks_by_id = {str(task.get("id")): task for task in state.get("tasks", []) if isinstance(task, dict)}
    lines = []
    for session in active_work_sessions_for_desk(state)[:MAX_ITEMS]:
        session_id = session.get("id", "?")
        task_id = session.get("task_id")
        task_record = tasks_by_id.get(str(task_id)) if task_id is not None else None
        resume = build_work_session_resume(session, task=task_record, limit=3, state=state) or {}
        goal = normalize_text(resume.get("goal") or session.get("goal") or session.get("title")) or "Untitled"
        task = f" task #{task_id}" if task_id is not None else ""
        title = titles.get(str(task_id), "") if task_id is not None else ""
        if title:
            task = f"{task}: {title}"
        phase = normalize_text(session.get("phase") or resume.get("phase")) or "unknown"
        line = f"#{session_id}{task}: {goal} [{phase}]"
        continuity = resume.get("continuity") or {}
        if continuity:
            line = f"{line}; continuity: {continuity.get('score') or '-'} {continuity.get('status') or 'unknown'}"
            recommendation = continuity.get("recommendation") or {}
            if continuity.get("missing") and recommendation.get("summary"):
                line = f"{line}; repair: {normalize_text(recommendation.get('summary'))}"
        next_action = normalize_text(session.get("next_action") or resume.get("next_action"))
        if next_action:
            line = f"{line}; next: {next_action}"
        lines.append(line)
    return lines


def build_dream_view_model(state: dict[str, Any], explicit_date: str | None = None) -> dict[str, Any]:
    return {
        "date": resolve_dream_date(explicit_date),
        "active_tasks": [task_ref(task) for task in open_tasks_for_desk(state)[:MAX_ITEMS]],
        "active_work_sessions": work_session_lines(state),
        "learnings": collect_self_learnings(state)[:MAX_ITEMS],
    }


def render_section(title: str, items: list[str], fallback: str) -> list[str]:
    lines = [f"## {title}"]
    if items:
        for item in items:
            lines.append(f"- {item}")
    else:
        lines.append(f"- {fallback}")
    return lines


def render_dream_markdown(view_model: dict[str, Any]) -> str:
    lines = [
        f"# Mew Dream {view_model['date']}",
        "",
        *render_section("Active tasks", view_model["active_tasks"], "No active tasks recorded"),
        "",
        *render_section("Active work sessions", view_model["active_work_sessions"], "No active work sessions"),
        "",
        *render_section("Learnings", view_model["learnings"], "No learnings recorded"),
    ]
    return "\n".join(lines) + "\n"


def format_dream_view(view_model: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Mew dream {view_model['date']}",
            f"active_tasks: {len(view_model['active_tasks'])}",
            f"active_work_sessions: {len(view_model['active_work_sessions'])}",
            f"learnings: {len(view_model['learnings'])}",
        ]
    )


def write_dream_report(view_model: dict[str, Any], output_dir: Path) -> Path:
    path = dream_path(output_dir, view_model["date"])
    write_generated_report(path, render_dream_markdown(view_model))
    return path
