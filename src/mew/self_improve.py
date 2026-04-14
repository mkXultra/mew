from .brief import build_brief, next_move
from .programmer import create_task_plan, latest_task_plan
from .state import next_id
from .tasks import open_tasks
from .timeutil import now_iso


DEFAULT_SELF_IMPROVE_TITLE = "Improve mew itself"


def open_task_with_title(state, title):
    normalized = (title or "").strip().casefold()
    for task in open_tasks(state):
        if (task.get("title") or "").strip().casefold() == normalized:
            return task
    return None


def build_self_improve_description(state, focus=""):
    focus_text = focus.strip() if isinstance(focus, str) else ""
    return (
        "Improve mew through one small, reviewable code or documentation change.\n\n"
        f"Focus:\n{focus_text or next_move(state)}\n\n"
        "Current brief:\n"
        f"{build_brief(state, limit=5)}\n\n"
        "Constraints:\n"
        "- Keep the change small.\n"
        "- Preserve unrelated user changes.\n"
        "- Run relevant checks or explain why they were skipped.\n"
        "- Update tests or docs when behavior changes.\n"
    )


def create_self_improve_task(
    state,
    title=None,
    description=None,
    focus="",
    cwd=".",
    priority="normal",
    ready=False,
    auto_execute=False,
    agent_model=None,
    force=False,
):
    title = title or DEFAULT_SELF_IMPROVE_TITLE
    task = None if force else open_task_with_title(state, title)
    created = False
    current_time = now_iso()

    if task is None:
        task = {
            "id": next_id(state, "task"),
            "title": title,
            "description": description or build_self_improve_description(state, focus=focus),
            "status": "ready" if ready else "todo",
            "priority": priority,
            "notes": f"Created by mew self-improve at {current_time}.",
            "command": "",
            "cwd": cwd or ".",
            "auto_execute": bool(auto_execute),
            "agent_backend": "",
            "agent_model": agent_model or "",
            "agent_prompt": "",
            "agent_run_id": None,
            "plans": [],
            "latest_plan_id": None,
            "runs": [],
            "created_at": current_time,
            "updated_at": current_time,
        }
        state["tasks"].append(task)
        created = True
    else:
        if description:
            task["description"] = description
        if focus and not description:
            task["description"] = build_self_improve_description(state, focus=focus)
        if ready:
            task["status"] = "ready"
        if auto_execute:
            task["auto_execute"] = True
        if cwd:
            task["cwd"] = cwd
        if agent_model:
            task["agent_model"] = agent_model
        task["updated_at"] = current_time

    return task, created


def ensure_self_improve_plan(state, task, agent_model=None, review_model=None, force=False):
    plan = None if force else latest_task_plan(task)
    if plan:
        return plan, False
    plan = create_task_plan(
        state,
        task,
        cwd=task.get("cwd") or ".",
        model=agent_model or task.get("agent_model") or None,
        review_model=review_model,
        objective=task.get("description") or task.get("title"),
        approach=(
            "Inspect the current mew codebase, make one focused improvement, "
            "then run the smallest relevant verification."
        ),
    )
    return plan, True
