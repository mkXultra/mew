from .read_tools import glob_paths, inspect_dir, read_file, search_text, summarize_read_result
from .state import next_id
from .tasks import clip_output, find_task
from .timeutil import now_iso
from .toolbox import format_command_record, run_command_record
from .write_tools import (
    edit_file,
    restore_write_snapshot,
    snapshot_write_path,
    summarize_write_result,
    write_file,
)


WORK_SESSION_STATUSES = {"active", "closed"}
WORK_TOOL_STATUSES = {"running", "completed", "failed"}
WORK_MODEL_TURN_STATUSES = {"running", "completed", "failed"}
WORK_TOOLS = {
    "inspect_dir",
    "read_file",
    "search_text",
    "glob",
    "run_command",
    "run_tests",
    "write_file",
    "edit_file",
}
READ_ONLY_WORK_TOOLS = {"inspect_dir", "read_file", "search_text", "glob"}
WRITE_WORK_TOOLS = {"write_file", "edit_file"}


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
        "last_model_turn_id": None,
        "tool_calls": [],
        "model_turns": [],
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


def find_work_model_turn(session, turn_id):
    if not session or turn_id is None:
        return None
    for turn in session.get("model_turns") or []:
        if str(turn.get("id")) == str(turn_id):
            return turn
    return None


def start_work_model_turn(state, session, decision_plan, action_plan, action):
    current_time = now_iso()
    turn = {
        "id": next_id(state, "work_model_turn"),
        "session_id": session.get("id"),
        "task_id": session.get("task_id"),
        "status": "running",
        "decision_plan": dict(decision_plan or {}),
        "action_plan": dict(action_plan or {}),
        "action": dict(action or {}),
        "tool_call_id": None,
        "summary": (action_plan or {}).get("summary") or (decision_plan or {}).get("summary") or "",
        "error": "",
        "started_at": current_time,
        "finished_at": None,
    }
    session.setdefault("model_turns", []).append(turn)
    session["last_model_turn_id"] = turn["id"]
    session["updated_at"] = current_time
    return turn


def finish_work_model_turn(state, session_id, turn_id, tool_call_id=None, error=""):
    session = find_work_session(state, session_id)
    turn = find_work_model_turn(session, turn_id)
    if not turn:
        return None
    finished_at = now_iso()
    turn["tool_call_id"] = tool_call_id
    if error:
        turn["status"] = "failed"
        turn["error"] = str(error)
        turn["summary"] = clip_output(f"model turn failed: {error}", 4000)
    else:
        turn["status"] = "completed"
        action = turn.get("action") or {}
        action_type = action.get("type") or action.get("tool") or "unknown"
        turn["summary"] = clip_output(turn.get("summary") or f"selected {action_type}", 4000)
    turn["finished_at"] = finished_at
    if session:
        session["updated_at"] = finished_at
    return turn


def execute_work_tool(tool, parameters, allowed_read_roots):
    parameters = dict(parameters or {})
    if tool not in WORK_TOOLS:
        raise ValueError(f"unsupported work tool: {tool}")
    if tool in READ_ONLY_WORK_TOOLS and not allowed_read_roots:
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
    if tool == "glob":
        return glob_paths(
            parameters.get("pattern") or "",
            parameters.get("path") or ".",
            allowed_read_roots,
            max_matches=parameters.get("max_matches", 100),
        )
    if tool in WRITE_WORK_TOOLS:
        return execute_work_write_tool(tool, parameters)
    if tool == "run_tests":
        if not parameters.get("allow_verify"):
            raise ValueError("verification is disabled; pass --allow-verify")
        command = parameters.get("command") or ""
        if not command:
            raise ValueError("run_tests command is empty")
        return run_command_record(command, cwd=parameters.get("cwd") or ".", timeout=parameters.get("timeout", 300))
    if not parameters.get("allow_shell"):
        raise ValueError("shell command execution is disabled; pass --allow-shell")
    command = parameters.get("command") or ""
    if not command:
        raise ValueError("run_command command is empty")
    return run_command_record(
        command,
        cwd=parameters.get("cwd") or ".",
        timeout=parameters.get("timeout", 300),
    )


def execute_work_write_tool(tool, parameters):
    allowed_write_roots = parameters.get("allowed_write_roots") or []
    if not allowed_write_roots:
        raise ValueError("write is disabled; pass --allow-write PATH")

    apply = bool(parameters.get("apply"))
    if apply and (not parameters.get("allow_verify") or not parameters.get("verify_command")):
        raise ValueError("applied writes require --allow-verify and --verify-command")
    if tool == "write_file" and "content" not in parameters:
        raise ValueError("write_file requires --content")
    if tool == "edit_file" and "old" not in parameters:
        raise ValueError("edit_file requires --old")
    if tool == "edit_file" and "new" not in parameters:
        raise ValueError("edit_file requires --new")

    path = parameters.get("path") or ""
    snapshot = None
    if apply:
        snapshot = snapshot_write_path(
            path,
            allowed_write_roots,
            create=tool == "write_file" and bool(parameters.get("create")),
        )

    if tool == "write_file":
        result = write_file(
            path,
            parameters.get("content", ""),
            allowed_write_roots,
            create=bool(parameters.get("create")),
            dry_run=not apply,
        )
    else:
        result = edit_file(
            path,
            parameters.get("old") or "",
            parameters.get("new") or "",
            allowed_write_roots,
            replace_all=bool(parameters.get("replace_all")),
            dry_run=not apply,
        )

    result["applied"] = bool(apply)
    if apply and result.get("written"):
        verification = run_command_record(
            parameters.get("verify_command") or "",
            cwd=parameters.get("verify_cwd") or ".",
            timeout=parameters.get("verify_timeout", 300),
        )
        result["verification"] = verification
        result["verification_exit_code"] = verification.get("exit_code")
        if verification.get("exit_code") != 0 and snapshot:
            try:
                result["rollback"] = restore_write_snapshot(snapshot)
                result["rolled_back"] = True
            except (OSError, ValueError) as exc:
                result["rollback_error"] = str(exc)
                result["rolled_back"] = False
        else:
            result["rolled_back"] = False
    return result


def work_tool_result_error(tool, result):
    result = result or {}
    if tool in WRITE_WORK_TOOLS:
        if "verification_exit_code" in result and result.get("verification_exit_code") != 0:
            exit_code = result.get("verification_exit_code")
            if result.get("rolled_back"):
                suffix = "; rolled back"
            elif result.get("rollback_error"):
                suffix = f"; rollback failed: {result.get('rollback_error')}"
            else:
                suffix = ""
            return f"verification failed with exit_code={exit_code}{suffix}"
    return ""


def summarize_work_tool_result(tool, result):
    if tool in READ_ONLY_WORK_TOOLS:
        return summarize_read_result(tool, result or {})
    if tool in WRITE_WORK_TOOLS:
        summary = summarize_write_result(result or {})
        verification = (result or {}).get("verification")
        if verification:
            summary += "\nverification:\n" + format_command_record(verification)
        if (result or {}).get("rolled_back"):
            summary += "\nrolled_back: True"
        if (result or {}).get("rollback_error"):
            summary += f"\nrollback_error: {(result or {}).get('rollback_error')}"
        return summary
    return format_command_record(result or {})


def finish_work_tool_call(state, session_id, tool_call_id, result=None, error=""):
    session = find_work_session(state, session_id)
    tool_call = find_work_tool_call(session, tool_call_id)
    if not tool_call:
        return None
    finished_at = now_iso()
    if result is not None:
        tool_call["result"] = result
    if error:
        tool_call["status"] = "failed"
        tool_call["error"] = str(error)
        tool_call["summary"] = f"{tool_call.get('tool')} failed: {error}"
        if result is not None:
            summary = summarize_work_tool_result(tool_call.get("tool"), result or {})
            if summary:
                tool_call["summary"] = clip_output(tool_call["summary"] + "\n" + summary, 4000)
    else:
        tool_call["status"] = "completed"
        tool_call["summary"] = clip_output(summarize_work_tool_result(tool_call.get("tool"), result or {}), 4000)
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


def format_work_session(session, task=None, limit=8, details=False):
    if not session:
        return "No active work session."
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    lines = [
        f"Work session #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        f"goal: {session.get('goal') or ''}",
        f"created_at: {session.get('created_at')}",
        f"updated_at: {session.get('updated_at')}",
        f"model_turns={len(turns)} tool_calls={len(calls)}",
    ]
    if details:
        paths = []
        for call in calls:
            result = call.get("result") or {}
            parameters = call.get("parameters") or {}
            path = result.get("path") or parameters.get("path")
            if path and path not in paths:
                paths.append(path)
        lines.extend(["", "Files"])
        if paths:
            lines.extend(f"- {path}" for path in paths[-limit:])
        else:
            lines.append("(none)")

        lines.extend(["", "Model turns"])
        if turns:
            for turn in turns[-limit:]:
                action = turn.get("action") or {}
                action_type = action.get("type") or action.get("tool") or "unknown"
                tool_call_id = turn.get("tool_call_id")
                tool_text = f" tool_call=#{tool_call_id}" if tool_call_id else ""
                lines.append(
                    f"#{turn.get('id')} [{turn.get('status')}] {action_type}{tool_text} "
                    f"{turn.get('summary') or turn.get('error') or ''}"
                )
        else:
            lines.append("(none)")

        write_calls = [
            call
            for call in calls
            if call.get("tool") in WRITE_WORK_TOOLS and (call.get("result") or {}).get("diff")
        ]
        lines.extend(["", "Recent diffs"])
        if write_calls:
            for call in write_calls[-limit:]:
                result = call.get("result") or {}
                approval = f" approval={call.get('approval_status')}" if call.get("approval_status") else ""
                lines.append(
                    f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                    f"written={result.get('written')} rolled_back={result.get('rolled_back')} "
                    f"verification_exit_code={result.get('verification_exit_code')}{approval}"
                )
                lines.append(result.get("diff") or "")
        else:
            lines.append("(none)")

    lines.extend(
        [
            "",
            "Tool calls",
        ]
    )
    recent_calls = calls[-limit:]
    if not recent_calls:
        lines.append("(none)")
    else:
        for call in recent_calls:
            lines.append(
                f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                f"{call.get('summary') or call.get('error') or ''}"
            )
    return "\n".join(lines)


def work_session_task(state, session):
    if not session:
        return None
    return find_task(state, session.get("task_id"))
