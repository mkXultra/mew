from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .desk import active_work_sessions_for_desk
from .report_io import write_generated_report
from .timeutil import now_date_iso
from .work_session import build_work_session_resume


MAX_ITEMS = 8
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_date(value: str) -> str:
    if not DATE_PATTERN.fullmatch(value):
        raise ValueError("date must be in YYYY-MM-DD format")
    return value


def resolve_self_memory_date(explicit_date: str | None = None) -> str:
    if explicit_date:
        return validate_date(explicit_date)
    return validate_date(now_date_iso())


def self_memory_path(output_dir: Path, day: str) -> Path:
    return output_dir / ".mew" / "self" / f"learned-{day}.md"


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


def string_items(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        if isinstance(item, str):
            text = normalize_text(item)
            if text:
                items.append(text)
        elif isinstance(item, dict):
            for key in ("summary", "title", "text", "note"):
                text = normalize_text(item.get(key))
                if text:
                    items.append(text)
                    break
    return items


def task_note_learning(task: dict[str, Any]) -> str:
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


def task_items(state: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = state.get("tasks")
    if not isinstance(tasks, list):
        return []
    return [task for task in tasks if isinstance(task, dict)]


def raw_self_learning_candidates(state: dict[str, Any]) -> list[str]:
    learnings = []
    for key in ("learnings", "changes", "decisions"):
        learnings.extend(string_items(state.get(key)))
    memory = state.get("memory")
    if isinstance(memory, dict):
        deep = memory.get("deep")
        if isinstance(deep, dict):
            learnings.extend(string_items(deep.get("decisions")))
            learnings.extend(string_items(deep.get("project")))
    for task in reversed(task_items(state)):
        if task.get("status") != "done":
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
    memory = state.get("memory")
    if isinstance(memory, dict):
        deep = memory.get("deep")
        if isinstance(deep, dict):
            traits.extend(string_items(deep.get("preferences")))
    traits.extend(infer_repeated_traits(state))
    return unique(traits)


def collect_self_learnings(state: dict[str, Any]) -> list[str]:
    return unique(raw_self_learning_candidates(state))


def task_title_by_id(state: dict[str, Any]) -> dict[str, str]:
    titles = {}
    for task in task_items(state):
        task_id = task.get("id")
        title = normalize_text(task.get("title"))
        if task_id is not None and title:
            titles[str(task_id)] = title
    return titles


def collect_continuity_cues(state: dict[str, Any]) -> list[str]:
    tasks = task_items(state)
    state_for_desk = {**state, "tasks": tasks}
    tasks_by_id = {str(task.get("id")): task for task in tasks}
    titles = {
        task_id: normalize_text(task.get("title"))
        for task_id, task in tasks_by_id.items()
        if normalize_text(task.get("title"))
    }
    cues = []
    for session in active_work_sessions_for_desk(state_for_desk):
        session_id = session.get("id", "?")
        task_id = session.get("task_id")
        task_record = tasks_by_id.get(str(task_id)) if task_id is not None else None
        resume = build_work_session_resume(session, task=task_record, limit=3, state=state) or {}
        goal = normalize_text(resume.get("goal") or session.get("goal") or session.get("title")) or "Untitled"
        task = f" task #{task_id}" if task_id is not None else ""
        task_title = titles.get(str(task_id), "") if task_id is not None else ""
        if task_title:
            task = f"{task}: {task_title}"
        phase = normalize_text(session.get("phase") or resume.get("phase")) or "unknown phase"
        cue = f"Work session #{session_id}{task} is {phase}: {goal}"
        continuity = resume.get("continuity") or {}
        if continuity:
            cue = f"{cue}; continuity: {continuity.get('score') or '-'} {continuity.get('status') or 'unknown'}"
            recommendation = continuity.get("recommendation") or {}
            if continuity.get("missing") and recommendation.get("summary"):
                cue = f"{cue}; repair: {normalize_text(recommendation.get('summary'))}"
        next_action = normalize_text(session.get("next_action") or resume.get("next_action"))
        if next_action:
            cue = f"{cue}; next: {next_action}"
        cues.append(cue)
    return unique(cues)


def build_self_memory_view_model(state: dict[str, Any], explicit_date: str | None = None) -> dict[str, Any]:
    return {
        "date": resolve_self_memory_date(explicit_date),
        "traits": collect_traits(state),
        "learnings": collect_self_learnings(state),
        "continuity_cues": collect_continuity_cues(state),
    }


def render_self_memory_markdown(view_model: dict[str, Any]) -> str:
    lines = [f"# Mew Self Memory {view_model['date']}", ""]

    lines.append("## Durable traits")
    traits = view_model["traits"]
    if traits:
        for trait in traits:
            lines.append(f"- {trait}")
    else:
        lines.append("- No durable traits recorded")

    lines.extend(["", "## Recent self learnings"])
    learnings = view_model["learnings"]
    if learnings:
        for learning in learnings:
            lines.append(f"- {learning}")
    else:
        lines.append("- No self learnings recorded")

    lines.extend(["", "## Continuity cues"])
    cues = view_model["continuity_cues"]
    if cues:
        for cue in cues:
            lines.append(f"- {cue}")
    else:
        lines.append("- No active continuity cues")

    return "\n".join(lines) + "\n"


def format_self_memory_view(view_model: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Mew self memory {view_model['date']}",
            f"traits: {len(view_model['traits'])}",
            f"learnings: {len(view_model['learnings'])}",
            f"continuity_cues: {len(view_model['continuity_cues'])}",
        ]
    )


def write_self_memory_report(view_model: dict[str, Any], output_dir: Path) -> Path:
    path = self_memory_path(output_dir, view_model["date"])
    write_generated_report(path, render_self_memory_markdown(view_model))
    return path
