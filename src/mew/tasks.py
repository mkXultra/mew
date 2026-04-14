from pathlib import Path
import shlex
import subprocess

from .config import MAX_COMMAND_OUTPUT_CHARS
from .errors import MewError
from .state import add_outbox_message, has_unread_outbox_message
from .timeutil import now_iso


def open_tasks(state):
    return [task for task in state["tasks"] if task.get("status") != "done"]

def task_sort_key(task):
    status_order = {"ready": 0, "todo": 1, "blocked": 2, "done": 3}
    priority_order = {"high": 0, "normal": 1, "low": 2}
    return (
        status_order.get(task.get("status"), 9),
        priority_order.get(task.get("priority"), 9),
        task.get("created_at") or "",
    )

def summarize_tasks(state):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    if not tasks:
        return "No open tasks."

    counts = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1

    count_text = ", ".join(f"{status}: {count}" for status, count in sorted(counts.items()))
    next_task = tasks[0]
    return (
        f"{len(tasks)} open task(s) ({count_text}). "
        f"Next candidate: #{next_task['id']} {next_task['title']}."
    )

def executable_tasks(state):
    return [
        task
        for task in sorted(open_tasks(state), key=task_sort_key)
        if task.get("status") == "ready"
        and task.get("auto_execute")
        and task.get("command")
    ]

def task_question(task):
    if task.get("status") == "todo":
        return f"Task #{task['id']} is todo. Should I make it ready, block it, or add execution details?"
    if task.get("status") == "ready" and not task.get("command") and not task.get("agent_backend"):
        return f"Task #{task['id']} is ready but has no command. What should I execute for it?"
    if task.get("status") == "blocked":
        return f"Task #{task['id']} is blocked. What information is needed to unblock it?"
    return ""

def passive_question(state):
    tasks = sorted(open_tasks(state), key=task_sort_key)
    if not tasks:
        return "What task should I track next?"

    return task_question(tasks[0])

def clip_output(text, limit=MAX_COMMAND_OUTPUT_CHARS):
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... output truncated ..."

def resolve_task_cwd(task):
    cwd = task.get("cwd") or "."
    path = Path(cwd).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path

def execute_task_command(task, timeout):
    command = task.get("command") or ""
    if not command.strip():
        raise MewError("task has no command")

    args = shlex.split(command)
    if not args:
        raise MewError("task command is empty")

    cwd = resolve_task_cwd(task)
    if not cwd.exists() or not cwd.is_dir():
        raise MewError(f"task cwd does not exist: {cwd}")

    started_at = now_iso()
    result = subprocess.run(
        args,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout,
        shell=False,
    )
    finished_at = now_iso()

    return {
        "command": command,
        "cwd": str(cwd),
        "started_at": started_at,
        "finished_at": finished_at,
        "exit_code": result.returncode,
        "stdout": clip_output(result.stdout),
        "stderr": clip_output(result.stderr),
    }

def execute_one_autonomous_task(state, timeout):
    tasks = executable_tasks(state)
    if not tasks:
        question = passive_question(state)
        if question:
            if not has_unread_outbox_message(state, "question", question):
                add_outbox_message(state, "question", question)
        return 0

    task = tasks[0]
    current_time = now_iso()
    task["status"] = "running"
    task["updated_at"] = current_time
    add_outbox_message(
        state,
        "info",
        f"Executing task #{task['id']}: {task['title']} command={task['command']}",
    )

    try:
        run = execute_task_command(task, timeout)
        task.setdefault("runs", []).append(run)
        if run["exit_code"] == 0:
            task["status"] = "done"
            text = f"Task #{task['id']} completed successfully."
        else:
            task["status"] = "blocked"
            text = f"Task #{task['id']} failed with exit code {run['exit_code']}."
        if run.get("stdout"):
            text += f"\nstdout:\n{run['stdout']}"
        if run.get("stderr"):
            text += f"\nstderr:\n{run['stderr']}"
        add_outbox_message(state, "info" if run["exit_code"] == 0 else "warning", text)
    except (MewError, subprocess.TimeoutExpired) as exc:
        task.setdefault("runs", []).append(
            {
                "command": task.get("command"),
                "cwd": str(resolve_task_cwd(task)),
                "started_at": current_time,
                "finished_at": now_iso(),
                "exit_code": None,
                "stdout": "",
                "stderr": str(exc),
            }
        )
        task["status"] = "blocked"
        add_outbox_message(state, "warning", f"Task #{task['id']} execution failed: {exc}")

    task["updated_at"] = now_iso()
    return 1

def normalize_task_id(value):
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

def task_by_id(state, task_id):
    normalized = normalize_task_id(task_id)
    if normalized is None:
        return None
    for task in state["tasks"]:
        if task.get("id") == normalized:
            return task
    return None

def execute_task_action(state, action, task_timeout):
    task = task_by_id(state, action.get("task_id"))
    if not task:
        add_outbox_message(state, "warning", f"Cannot execute missing task #{action.get('task_id')}")
        return 0
    if not (task.get("status") == "ready" and task.get("auto_execute") and task.get("command")):
        add_outbox_message(
            state,
            "warning",
            f"Refused to execute task #{task['id']}: task is not ready with command and auto_execute.",
            related_task_id=task["id"],
        )
        return 0

    current_time = now_iso()
    task["status"] = "running"
    task["updated_at"] = current_time
    add_outbox_message(
        state,
        "info",
        f"Executing task #{task['id']}: {task['title']} command={task['command']}",
        related_task_id=task["id"],
    )

    try:
        run = execute_task_command(task, task_timeout)
        task.setdefault("runs", []).append(run)
        if run["exit_code"] == 0:
            task["status"] = "done"
            text = f"Task #{task['id']} completed successfully."
        else:
            task["status"] = "blocked"
            text = f"Task #{task['id']} failed with exit code {run['exit_code']}."
        if run.get("stdout"):
            text += f"\nstdout:\n{run['stdout']}"
        if run.get("stderr"):
            text += f"\nstderr:\n{run['stderr']}"
        add_outbox_message(
            state,
            "info" if run["exit_code"] == 0 else "warning",
            text,
            related_task_id=task["id"],
        )
    except (MewError, subprocess.TimeoutExpired) as exc:
        task.setdefault("runs", []).append(
            {
                "command": task.get("command"),
                "cwd": str(resolve_task_cwd(task)),
                "started_at": current_time,
                "finished_at": now_iso(),
                "exit_code": None,
                "stdout": "",
                "stderr": str(exc),
            }
        )
        task["status"] = "blocked"
        add_outbox_message(
            state,
            "warning",
            f"Task #{task['id']} execution failed: {exc}",
            related_task_id=task["id"],
        )

    task["updated_at"] = now_iso()
    return 1

def format_task(task):
    return f"#{task['id']} [{task['status']}/{task['priority']}] {task['title']}"

def find_task(state, task_id):
    for task in state["tasks"]:
        if str(task["id"]) == str(task_id):
            return task
    return None
