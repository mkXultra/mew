from .read_tools import glob_paths, inspect_dir, read_file, search_text, summarize_read_result
from .state import next_id
from .tasks import clip_output, find_task
from .timeutil import now_iso


WORK_SESSION_STATUSES = {"active", "closed"}
WORK_TOOL_STATUSES = {"running", "completed", "failed"}
READ_ONLY_WORK_TOOLS = {"inspect_dir", "read_file", "search_text", "glob"}


def active_work_session(state):
    for session in reversed(state.get("work_sessions", [])):
        if session.get("status") == "active":
            return session
    return None


def work_session_for_task(state, task_id):
    wanted = str(task_id)
    for session in reversed(state.get("work_sessions", [])):
        if str(session.get("task_id")) == wanted and session.get("status") == "active":
            return session
    return None


def find_work_session(state, session_id):
    if session_id is None:
        return None
    for session in state.get("work_sessions", []):
        if str(session.get("id")) == str(session_id):
            return session
    return None


def find_work_tool_call(session, tool_call_id):
    if not session or tool_call_id is None:
        return None
    for call in session.get("tool_calls") or []:
        if str(call.get("id")) == str(tool_call_id):
            return call
    return None


def create_work_session(state, task, current_time=None):
    current_time = current_time or now_iso()
    existing = work_session_for_task(state, task.get("id"))
    if existing:
        existing["updated_at"] = current_time
        return existing, False

    session = {
        "id": next_id(state, "work_session"),
        "task_id": task.get("id"),
        "status": "active",
        "title": task.get("title") or "",
        "goal": task.get("description") or task.get("title") or "",
        "created_at": current_time,
        "updated_at": current_time,
        "last_tool_call_id": None,
        "tool_calls": [],
    }
    state.setdefault("work_sessions", []).append(session)
    return session, True


def close_work_session(session, current_time=None):
    current_time = current_time or now_iso()
    session["status"] = "closed"
    session["updated_at"] = current_time
    return session


def start_work_tool_call(state, session, tool, parameters):
    current_time = now_iso()
    tool_call = {
        "id": next_id(state, "work_tool_call"),
        "session_id": session.get("id"),
        "task_id": session.get("task_id"),
        "tool": tool,
        "status": "running",
        "parameters": dict(parameters or {}),
        "result": None,
        "summary": "",
        "error": "",
        "started_at": current_time,
        "finished_at": None,
    }
    session.setdefault("tool_calls", []).append(tool_call)
    session["last_tool_call_id"] = tool_call["id"]
    session["updated_at"] = current_time
    return tool_call


def execute_work_tool(tool, parameters, allowed_read_roots):
    parameters = dict(parameters or {})
    if tool not in READ_ONLY_WORK_TOOLS:
        raise ValueError(f"unsupported work tool: {tool}")
    if not allowed_read_roots:
        raise ValueError("work tool read access is disabled; pass --allow-read PATH")

    if tool == "inspect_dir":
        return inspect_dir(parameters.get("path") or ".", allowed_read_roots, limit=parameters.get("limit", 50))
    if tool == "read_file":
        return read_file(
            parameters.get("path") or "",
            allowed_read_roots,
            max_chars=parameters.get("max_chars", 6000),
        )
    if tool == "search_text":
        return search_text(
            parameters.get("query") or "",
            parameters.get("path") or ".",
            allowed_read_roots,
            max_matches=parameters.get("max_matches", 50),
        )
    return glob_paths(
        parameters.get("pattern") or "",
        parameters.get("path") or ".",
        allowed_read_roots,
        max_matches=parameters.get("max_matches", 100),
    )


def finish_work_tool_call(state, session_id, tool_call_id, result=None, error=""):
    session = find_work_session(state, session_id)
    tool_call = find_work_tool_call(session, tool_call_id)
    if not tool_call:
        return None
    finished_at = now_iso()
    if error:
        tool_call["status"] = "failed"
        tool_call["error"] = str(error)
        tool_call["summary"] = f"{tool_call.get('tool')} failed: {error}"
    else:
        tool_call["status"] = "completed"
        tool_call["result"] = result
        tool_call["summary"] = clip_output(summarize_read_result(tool_call.get("tool"), result or {}), 4000)
    tool_call["finished_at"] = finished_at
    if session:
        session["updated_at"] = finished_at
    return tool_call


def run_work_tool(state, session, tool, parameters, allowed_read_roots):
    tool_call = start_work_tool_call(state, session, tool, parameters)

    try:
        result = execute_work_tool(tool, parameters, allowed_read_roots)
        return finish_work_tool_call(state, session.get("id"), tool_call.get("id"), result=result)
    except (OSError, ValueError) as exc:
        return finish_work_tool_call(state, session.get("id"), tool_call.get("id"), error=str(exc))


def format_work_session(session, task=None, limit=8):
    if not session:
        return "No active work session."
    lines = [
        f"Work session #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        f"goal: {session.get('goal') or ''}",
        f"created_at: {session.get('created_at')}",
        f"updated_at: {session.get('updated_at')}",
        "",
        "Tool calls",
    ]
    calls = list(session.get("tool_calls") or [])[-limit:]
    if not calls:
        lines.append("(none)")
    else:
        for call in calls:
            lines.append(
                f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                f"{call.get('summary') or call.get('error') or ''}"
            )
    return "\n".join(lines)


def work_session_task(state, session):
    if not session:
        return None
    return find_task(state, session.get("task_id"))
