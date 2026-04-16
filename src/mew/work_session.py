import json
import shlex

from .read_tools import (
    DEFAULT_READ_MAX_CHARS,
    glob_paths,
    inspect_dir,
    read_file,
    resolve_allowed_path,
    search_text,
    summarize_read_result,
)
from .state import next_id
from .tasks import clip_output, find_task
from .timeutil import now_iso
from .toolbox import format_command_record, run_command_record, run_command_record_streaming, run_git_tool
from .write_tools import (
    edit_file,
    restore_write_snapshot,
    snapshot_write_path,
    summarize_write_result,
    write_file,
)


WORK_SESSION_STATUSES = {"active", "closed"}
WORK_TOOL_STATUSES = {"running", "completed", "failed", "interrupted"}
WORK_MODEL_TURN_STATUSES = {"running", "completed", "failed", "interrupted"}
WORK_TOOLS = {
    "inspect_dir",
    "read_file",
    "search_text",
    "glob",
    "run_command",
    "run_tests",
    "git_status",
    "git_diff",
    "git_log",
    "write_file",
    "edit_file",
}
READ_ONLY_WORK_TOOLS = {"inspect_dir", "read_file", "search_text", "glob"}
GIT_WORK_TOOLS = {"git_status", "git_diff", "git_log"}
COMMAND_WORK_TOOLS = {"run_command", "run_tests"} | GIT_WORK_TOOLS
WRITE_WORK_TOOLS = {"write_file", "edit_file"}
WORK_ACTION_DISPLAY_FIELDS = (
    "path",
    "query",
    "pattern",
    "command",
    "cwd",
    "base",
    "limit",
    "offset",
    "apply",
    "create",
    "replace_all",
    "staged",
    "stat",
)


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


def latest_work_session_for_task(state, task_id):
    wanted = str(task_id)
    for session in reversed(state.get("work_sessions", [])):
        if str(session.get("task_id")) == wanted:
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

    latest = latest_work_session_for_task(state, task.get("id"))
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
    if latest and latest.get("default_options"):
        session["default_options"] = json.loads(json.dumps(latest.get("default_options") or {}))
    state.setdefault("work_sessions", []).append(session)
    return session, True


def close_work_session(session, current_time=None):
    current_time = current_time or now_iso()
    session["status"] = "closed"
    session["updated_at"] = current_time
    return session


def request_work_session_stop(session, reason="", current_time=None):
    current_time = current_time or now_iso()
    session["stop_requested_at"] = current_time
    session["stop_reason"] = reason or "stop requested"
    session["updated_at"] = current_time
    return session


def add_work_session_note(session, text, source="user", current_time=None):
    current_time = current_time or now_iso()
    note = {
        "created_at": current_time,
        "source": source or "user",
        "text": text or "",
    }
    notes = session.setdefault("notes", [])
    notes.append(note)
    del notes[:-50]
    session["updated_at"] = current_time
    return note


def consume_work_session_stop(session, current_time=None):
    if not session or not session.get("stop_requested_at"):
        return None
    current_time = current_time or now_iso()
    stop = {
        "requested_at": session.get("stop_requested_at"),
        "reason": session.get("stop_reason") or "stop requested",
    }
    session["last_stop_request"] = stop
    session["stop_acknowledged_at"] = current_time
    session.pop("stop_requested_at", None)
    session.pop("stop_reason", None)
    session["updated_at"] = current_time
    return stop


def mark_running_work_interrupted(state, current_time=None):
    current_time = current_time or now_iso()
    repairs = []
    for session in state.get("work_sessions", []):
        if not isinstance(session, dict):
            continue
        changed = False
        recovery_hint = (
            f"Review work session #{session.get('id')} resume, verify world state, then retry or choose a new action."
        )
        for call in session.get("tool_calls") or []:
            if not isinstance(call, dict) or call.get("status") != "running":
                continue
            call["status"] = "interrupted"
            call["finished_at"] = current_time
            call["error"] = call.get("error") or "Interrupted before the work tool completed."
            call["summary"] = call.get("summary") or "interrupted work tool call"
            call["recovery_hint"] = recovery_hint
            repairs.append(
                {
                    "type": "interrupted_work_tool_call",
                    "session_id": session.get("id"),
                    "task_id": session.get("task_id"),
                    "tool_call_id": call.get("id"),
                    "tool": call.get("tool"),
                    "old_status": "running",
                    "new_status": "interrupted",
                    "recovery_hint": recovery_hint,
                }
            )
            changed = True
        for turn in session.get("model_turns") or []:
            if not isinstance(turn, dict) or turn.get("status") != "running":
                continue
            turn["status"] = "interrupted"
            turn["finished_at"] = current_time
            turn["error"] = turn.get("error") or "Interrupted before the work model turn completed."
            turn["summary"] = turn.get("summary") or "interrupted work model turn"
            turn["recovery_hint"] = recovery_hint
            repairs.append(
                {
                    "type": "interrupted_work_model_turn",
                    "session_id": session.get("id"),
                    "task_id": session.get("task_id"),
                    "model_turn_id": turn.get("id"),
                    "old_status": "running",
                    "new_status": "interrupted",
                    "recovery_hint": recovery_hint,
                }
            )
            changed = True
        if changed:
            session["updated_at"] = current_time
    return repairs


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


def update_work_model_turn_plan(state, session_id, turn_id, decision_plan, action_plan, action):
    session = find_work_session(state, session_id)
    turn = find_work_model_turn(session, turn_id)
    if not turn:
        return None
    current_time = now_iso()
    turn["decision_plan"] = dict(decision_plan or {})
    turn["action_plan"] = dict(action_plan or {})
    turn["action"] = dict(action or {})
    turn["summary"] = (action_plan or {}).get("summary") or (decision_plan or {}).get("summary") or turn.get("summary") or ""
    turn["updated_at"] = current_time
    if session:
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


def run_command_for_work(command, cwd=".", timeout=300, on_output=None):
    if on_output:
        return run_command_record_streaming(command, cwd=cwd, timeout=timeout, on_output=on_output)
    return run_command_record(command, cwd=cwd, timeout=timeout)


def execute_work_tool(tool, parameters, allowed_read_roots, on_output=None):
    parameters = dict(parameters or {})
    if tool not in WORK_TOOLS:
        raise ValueError(f"unsupported work tool: {tool}")
    if tool in READ_ONLY_WORK_TOOLS and not allowed_read_roots:
        raise ValueError("work tool read access is disabled; pass --allow-read PATH")
    if tool in GIT_WORK_TOOLS and not allowed_read_roots:
        raise ValueError("git inspection is disabled; pass --allow-read PATH")

    if tool == "inspect_dir":
        return inspect_dir(parameters.get("path") or ".", allowed_read_roots, limit=parameters.get("limit", 50))
    if tool == "read_file":
        return read_file(
            parameters.get("path") or "",
            allowed_read_roots,
            max_chars=parameters.get("max_chars", DEFAULT_READ_MAX_CHARS),
            offset=parameters.get("offset", 0),
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
    if tool in GIT_WORK_TOOLS:
        cwd = resolve_allowed_path(parameters.get("cwd") or ".", allowed_read_roots)
        if tool == "git_status":
            return run_git_tool("status", cwd=str(cwd))
        if tool == "git_diff":
            return run_git_tool(
                "diff",
                cwd=str(cwd),
                staged=bool(parameters.get("staged")),
                stat=bool(parameters.get("stat")),
                base=parameters.get("base") or "",
            )
        return run_git_tool("log", cwd=str(cwd), limit=parameters.get("limit", 20))
    if tool in WRITE_WORK_TOOLS:
        return execute_work_write_tool(tool, parameters, on_output=on_output)
    if tool == "run_tests":
        if not parameters.get("allow_verify"):
            raise ValueError("verification is disabled; pass --allow-verify")
        command = parameters.get("command") or ""
        if not command:
            raise ValueError("run_tests command is empty")
        return run_command_for_work(
            command,
            cwd=parameters.get("cwd") or ".",
            timeout=parameters.get("timeout", 300),
            on_output=on_output,
        )
    if not parameters.get("allow_shell"):
        raise ValueError("shell command execution is disabled; pass --allow-shell")
    command = parameters.get("command") or ""
    if not command:
        raise ValueError("run_command command is empty")
    return run_command_for_work(
        command,
        cwd=parameters.get("cwd") or ".",
        timeout=parameters.get("timeout", 300),
        on_output=on_output,
    )


def execute_work_write_tool(tool, parameters, on_output=None):
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
        verification = run_command_for_work(
            parameters.get("verify_command") or "",
            cwd=parameters.get("verify_cwd") or ".",
            timeout=parameters.get("verify_timeout", 300),
            on_output=on_output,
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
    if tool == "run_tests" and "exit_code" in result and result.get("exit_code") != 0:
        return f"verification failed with exit_code={result.get('exit_code')}"
    if tool in GIT_WORK_TOOLS and "exit_code" in result and result.get("exit_code") != 0:
        return f"{tool} failed with exit_code={result.get('exit_code')}"
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


def clip_tail(text, max_chars=1200):
    text = text or ""
    if len(text) <= max_chars:
        return text
    return "[...snip...]\n" + text[-max_chars:]


def format_command_failure_summary(record, max_chars=1200):
    record = record or {}
    lines = [
        f"command: {record.get('command')}",
        f"cwd: {record.get('cwd')}",
        f"exit_code: {record.get('exit_code')}",
    ]
    stderr = record.get("stderr") or ""
    stdout = record.get("stdout") or ""
    if stderr:
        lines.extend(["stderr:", clip_tail(stderr, max_chars)])
    if stdout:
        lines.extend(["stdout:", clip_tail(stdout, max_chars)])
    return "\n".join(lines)


def summarize_work_tool_result(tool, result):
    if tool in READ_ONLY_WORK_TOOLS:
        return summarize_read_result(tool, result or {})
    if tool in WRITE_WORK_TOOLS:
        summary = summarize_write_result(result or {})
        verification = (result or {}).get("verification")
        if verification:
            if verification.get("exit_code") == 0:
                summary += "\nverification:\n" + format_command_record(verification)
            else:
                summary += "\nverification_failure:\n" + format_command_failure_summary(verification)
        if (result or {}).get("rolled_back"):
            summary += "\nrolled_back: True"
        if (result or {}).get("rollback_error"):
            summary += f"\nrollback_error: {(result or {}).get('rollback_error')}"
        return summary
    if tool == "run_tests" and (result or {}).get("exit_code") != 0:
        return format_command_failure_summary(result or {})
    if tool in GIT_WORK_TOOLS:
        return format_command_record(result or {})
    return format_command_record(result or {})


def compact_work_tool_summary(call):
    tool = call.get("tool")
    result = call.get("result") or {}
    summary = call.get("summary") or call.get("error") or ""
    if tool == "read_file":
        suffix = " (truncated)" if result.get("truncated") else ""
        offset = result.get("offset") or 0
        next_text = f" next_offset={result.get('next_offset')}" if result.get("next_offset") is not None else ""
        return (
            f"Read file {result.get('path') or (call.get('parameters') or {}).get('path')} "
            f"size={result.get('size')} chars offset={offset}{next_text}{suffix}"
        )
    if tool == "search_text":
        suffix = " (truncated)" if result.get("truncated") else ""
        return (
            f"Searched {result.get('path') or (call.get('parameters') or {}).get('path')} "
            f"for {result.get('query')!r} matches={len(result.get('matches') or [])}{suffix}"
        )
    if tool == "glob":
        suffix = " (truncated)" if result.get("truncated") else ""
        return (
            f"Globbed {result.get('path') or (call.get('parameters') or {}).get('path')} "
            f"for {result.get('pattern')!r} matches={len(result.get('matches') or [])}{suffix}"
        )
    return summary


def work_tool_failure_record(call):
    result = call.get("result") or {}
    if call.get("tool") == "run_tests" and "exit_code" in result and result.get("exit_code") != 0:
        return result
    if call.get("tool") in WRITE_WORK_TOOLS:
        verification = result.get("verification") or {}
        if "exit_code" in verification and verification.get("exit_code") != 0:
            return verification
    return None


def work_call_path(call):
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    return result.get("path") or parameters.get("path") or ""


def latest_work_verify_command(calls, task=None):
    command = (task or {}).get("command") or ""
    for call in calls:
        result = call.get("result") or {}
        if call.get("tool") == "run_tests" and result.get("command"):
            command = result.get("command")
        verification = result.get("verification") or {}
        if verification.get("command"):
            command = verification.get("command")
    return command


def _json_size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return len(str(value))


def _context_pressure(chars):
    if chars >= 200000:
        return "high"
    if chars >= 80000:
        return "medium"
    return "low"


def build_work_context_metrics(calls, turns):
    calls = list(calls or [])
    turns = list(turns or [])
    recent_calls = calls[-12:]
    recent_turns = turns[-8:]
    recent_chars = _json_size({"tool_calls": recent_calls, "model_turns": recent_turns})
    total_chars = _json_size({"tool_calls": calls, "model_turns": turns})
    return {
        "tool_calls": len(calls),
        "model_turns": len(turns),
        "recent_context_chars": recent_chars,
        "total_session_chars": total_chars,
        "pressure": _context_pressure(total_chars),
    }


def work_session_phase(session, calls, turns, pending_approvals):
    if not session:
        return "none"
    if session.get("status") == "closed":
        return "closed"
    if session.get("stop_requested_at"):
        return "stop_requested"
    if pending_approvals:
        return "awaiting_approval"
    if any((call or {}).get("status") == "running" for call in calls):
        return "running_tool"
    if any((turn or {}).get("status") == "running" for turn in turns):
        return "planning"
    latest_call = calls[-1] if calls else None
    latest_turn = turns[-1] if turns else None
    latest_call_interrupted = (latest_call or {}).get("status") == "interrupted" and not (latest_call or {}).get("recovery_status")
    latest_turn_interrupted = (latest_turn or {}).get("status") == "interrupted" and not (latest_turn or {}).get("recovery_status")
    if latest_call_interrupted or latest_turn_interrupted:
        return "interrupted"
    if latest_call and (latest_call.get("status") == "failed" or work_tool_failure_record(latest_call)):
        return "failed"
    return "idle"


def build_work_recovery_plan(session, calls, turns, limit=8):
    items = []
    task_id = (session or {}).get("task_id")
    interrupted_tool_ids = {
        call.get("id")
        for call in calls
        if call.get("status") == "interrupted" and not call.get("recovery_status")
    }
    latest_retryable_tool_id = None
    for call in calls:
        if call.get("status") != "interrupted" or call.get("recovery_status"):
            continue
        if call.get("tool") in READ_ONLY_WORK_TOOLS or call.get("tool") in GIT_WORK_TOOLS:
            latest_retryable_tool_id = call.get("id")
    for call in calls:
        if call.get("status") != "interrupted" or call.get("recovery_status"):
            continue
        tool = call.get("tool") or "unknown"
        if tool in READ_ONLY_WORK_TOOLS or tool in GIT_WORK_TOOLS:
            action = "retry_tool"
            safety = "read_only"
            reason = "interrupted read/git inspection can be retried after verifying read roots"
        elif tool in WRITE_WORK_TOOLS:
            action = "needs_user_review"
            safety = "write"
            reason = "interrupted write must be reviewed before retry or rollback"
        elif tool in COMMAND_WORK_TOOLS:
            action = "needs_user_review"
            safety = "command"
            reason = "interrupted command or verification may have side effects"
        else:
            action = "needs_user_review"
            safety = "unknown"
            reason = "interrupted tool type is not automatically recoverable"
        item = {
            "kind": "tool_call",
            "tool_call_id": call.get("id"),
            "tool": tool,
            "action": action,
            "safety": safety,
            "reason": reason,
        }
        if action == "retry_tool" and call.get("id") == latest_retryable_tool_id:
            item["hint"] = f"mew work {task_id} --recover-session --allow-read <path>"
        items.append(item)

    for turn in turns:
        if turn.get("status") != "interrupted" or turn.get("recovery_status"):
            continue
        if turn.get("tool_call_id") in interrupted_tool_ids:
            continue
        items.append(
            {
                "kind": "model_turn",
                "model_turn_id": turn.get("id"),
                "action": "replan",
                "safety": "no_tool_started",
                "reason": "interrupted model planning has no committed tool result; verify world state and run a new work step",
                "hint": f"mew work {task_id} --live --allow-read <path>",
            }
        )

    items = items[-limit:]
    if not items:
        return {}
    if any(item.get("action") == "needs_user_review" for item in items):
        next_action = "verify the world and review interrupted side-effecting work before retry"
    elif any(item.get("action") == "retry_tool" for item in items):
        next_action = "verify the world, then retry recoverable interrupted read/git tool after checking read roots"
    else:
        next_action = "verify world state and replan the interrupted model step"
    return {"next_action": next_action, "items": items}


def build_work_session_resume(session, task=None, limit=8):
    if not session:
        return None
    calls = list(session.get("tool_calls") or [])
    turns = list(session.get("model_turns") or [])
    verify_command = latest_work_verify_command(calls, task=task)
    verify_command_hint = shlex.quote(verify_command) if verify_command else '"<command>"'
    paths = []
    commands = []
    failures = []
    pending_approvals = []

    for call in calls:
        path = work_call_path(call)
        if path and path not in paths:
            paths.append(path)

        result = call.get("result") or {}
        if call.get("tool") in COMMAND_WORK_TOOLS:
            commands.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": call.get("tool"),
                    "command": result.get("command"),
                    "cwd": result.get("cwd"),
                    "exit_code": result.get("exit_code"),
                }
            )
        verification = result.get("verification") or {}
        if verification:
            commands.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": "verification",
                    "command": verification.get("command"),
                    "cwd": verification.get("cwd"),
                    "exit_code": verification.get("exit_code"),
                }
            )

        failure_record = work_tool_failure_record(call)
        if call.get("status") in ("failed", "interrupted") or failure_record:
            failures.append(
                {
                    "tool_call_id": call.get("id"),
                    "tool": call.get("tool"),
                    "error": call.get("error") or "",
                    "summary": call.get("summary") or "",
                    "exit_code": (failure_record or result).get("exit_code"),
                }
            )

        if (
            call.get("tool") in WRITE_WORK_TOOLS
            and result.get("dry_run")
            and result.get("changed")
            and not call.get("approval_status")
        ):
            tool_call_id = call.get("id")
            write_path = path or "."
            pending_approvals.append(
                {
                    "tool_call_id": tool_call_id,
                    "tool": call.get("tool"),
                    "path": path,
                    "summary": call.get("summary") or "",
                    "approve_hint": (
                        f"/work-session approve {tool_call_id} --allow-write {shlex.quote(write_path)} "
                        f"--allow-verify --verify-command {verify_command_hint}"
                    ),
                    "reject_hint": f"/work-session reject {tool_call_id} <reason>",
                }
            )

    recent_decisions = []
    for turn in turns[-limit:]:
        action = turn.get("action") or {}
        recent_decisions.append(
            {
                "model_turn_id": turn.get("id"),
                "status": turn.get("status"),
                "action": action.get("type") or action.get("tool") or "unknown",
                "summary": turn.get("finished_note") or turn.get("summary") or turn.get("error") or "",
                "tool_call_id": turn.get("tool_call_id"),
            }
        )

    phase = work_session_phase(session, calls, turns, pending_approvals)
    latest_call = calls[-1] if calls else None
    latest_failed = bool(
        latest_call
        and (
            latest_call.get("status") in ("failed", "interrupted")
            or work_tool_failure_record(latest_call)
        )
    )

    if session.get("status") == "closed":
        next_action = "review this closed work session or start a new one with mew work --ai"
    elif phase == "stop_requested":
        next_action = "stop requested; the running work loop should pause at the next boundary"
    elif pending_approvals:
        next_action = "approve or reject pending write tool calls"
    elif phase == "running_tool":
        next_action = "wait for the running work tool, or run mew repair if the process died"
    elif phase == "planning":
        next_action = "wait for the running work model turn, or run mew repair if the process died"
    elif phase == "interrupted":
        next_action = "inspect interrupted work state, verify the world, then retry or choose a new action"
    elif latest_failed:
        next_action = "inspect the latest failure and decide whether to retry, edit, or ask the user"
    else:
        next_action = "continue the work session with /continue in chat or mew work --live"

    recovery_plan = build_work_recovery_plan(session, calls, turns, limit=limit)
    if recovery_plan.get("next_action") and phase in ("interrupted", "idle", "failed"):
        next_action = recovery_plan["next_action"]

    return {
        "session_id": session.get("id"),
        "task_id": session.get("task_id"),
        "status": session.get("status"),
        "title": session.get("title") or (task or {}).get("title") or "",
        "goal": session.get("goal") or "",
        "phase": phase,
        "updated_at": session.get("updated_at"),
        "files_touched": paths[-limit:],
        "commands": commands[-limit:],
        "failures": failures[-limit:],
        "pending_approvals": pending_approvals[-limit:],
        "notes": list(session.get("notes") or [])[-limit:],
        "recent_decisions": recent_decisions,
        "context": build_work_context_metrics(calls, turns),
        "last_stop_request": session.get("last_stop_request") or {},
        "recovery_plan": recovery_plan,
        "next_action": next_action,
    }


def format_work_session_resume(resume):
    if not resume:
        return "No active work session."
    lines = [
        f"Work resume #{resume.get('session_id')} [{resume.get('status')}] task=#{resume.get('task_id')}",
        f"title: {resume.get('title') or ''}",
        f"phase: {resume.get('phase') or 'unknown'}",
        f"updated_at: {resume.get('updated_at')}",
        "",
        "Files touched",
    ]
    files = resume.get("files_touched") or []
    if files:
        lines.extend(f"- {path}" for path in files)
    else:
        lines.append("(none)")

    lines.extend(["", "Commands"])
    commands = resume.get("commands") or []
    if commands:
        for command in commands:
            lines.append(
                f"#{command.get('tool_call_id')} {command.get('tool')} "
                f"exit={command.get('exit_code')} {command.get('command') or ''}"
            )
    else:
        lines.append("(none)")

    lines.extend(["", "Pending approvals"])
    approvals = resume.get("pending_approvals") or []
    if approvals:
        for approval in approvals:
            lines.append(f"#{approval.get('tool_call_id')} {approval.get('tool')} {approval.get('path') or ''}")
            if approval.get("approve_hint"):
                lines.append(f"  approve: {approval.get('approve_hint')}")
            if approval.get("reject_hint"):
                lines.append(f"  reject: {approval.get('reject_hint')}")
    else:
        lines.append("(none)")

    lines.extend(["", "Failures"])
    failures = resume.get("failures") or []
    if failures:
        for failure in failures:
            lines.append(
                f"#{failure.get('tool_call_id')} {failure.get('tool')} "
                f"exit={failure.get('exit_code')} {failure.get('error') or failure.get('summary') or ''}"
            )
    else:
        lines.append("(none)")

    lines.extend(["", "Work notes"])
    notes = resume.get("notes") or []
    if notes:
        for note in notes:
            source = note.get("source") or "note"
            lines.append(f"- {note.get('created_at') or ''} [{source}] {note.get('text') or ''}".strip())
    else:
        lines.append("(none)")

    lines.extend(["", "Recent decisions"])
    decisions = resume.get("recent_decisions") or []
    if decisions:
        for decision in decisions:
            tool_text = f" tool_call=#{decision.get('tool_call_id')}" if decision.get("tool_call_id") else ""
            lines.append(
                f"#{decision.get('model_turn_id')} [{decision.get('status')}] "
                f"{decision.get('action')}{tool_text} {decision.get('summary') or ''}"
            )
    else:
        lines.append("(none)")

    last_stop = resume.get("last_stop_request") or {}
    if last_stop:
        lines.extend(["", "Last stop request"])
        lines.append(f"{last_stop.get('requested_at') or ''} {last_stop.get('reason') or ''}".strip())

    recovery = resume.get("recovery_plan") or {}
    if recovery:
        lines.extend(["", "Recovery plan"])
        for item in recovery.get("items") or []:
            target = f"tool_call=#{item.get('tool_call_id')}" if item.get("kind") == "tool_call" else f"model_turn=#{item.get('model_turn_id')}"
            lines.append(
                f"- {target} action={item.get('action')} safety={item.get('safety')} "
                f"{item.get('reason') or ''}"
            )
            if item.get("hint"):
                lines.append(f"  hint: {item.get('hint')}")

    world = resume.get("world_state") or {}
    if world:
        lines.extend(["", "World state"])
        git_status = world.get("git_status") or {}
        git_exit = git_status.get("exit_code")
        if git_exit == 0:
            git_detail = git_status.get("stdout") or "(clean)"
        else:
            git_detail = git_status.get("stderr") or git_status.get("stdout") or "(unavailable)"
        lines.append(f"git_status exit={git_exit} {git_detail}")
        files = world.get("files") or []
        if files:
            for item in files[:8]:
                state = "exists" if item.get("exists") else "missing" if item.get("exists") is False else "unknown"
                detail = item.get("error") or f"{item.get('type') or ''} size={item.get('size')}"
                lines.append(f"- {state} {item.get('path')}: {detail}")
        else:
            lines.append("(no files)")

    context = resume.get("context") or {}
    lines.extend(["", "Context pressure"])
    if context:
        lines.append(
            f"pressure={context.get('pressure')} "
            f"tool_calls={context.get('tool_calls')} model_turns={context.get('model_turns')} "
            f"recent_chars={context.get('recent_context_chars')} total_chars={context.get('total_session_chars')}"
        )
    else:
        lines.append("(unknown)")

    lines.extend(["", "Next action", resume.get("next_action") or ""])
    return "\n".join(lines)


def _display_value(action, parameters, key):
    if action.get(key) is not None:
        return action.get(key)
    return parameters.get(key)


def format_work_action(action, parameters=None, tool_call_id=None):
    action = dict(action or {})
    parameters = dict(parameters or {})
    action_type = action.get("type") or action.get("tool") or "unknown"
    lines = [f"action: {action_type}"]
    if tool_call_id:
        lines.append(f"tool_call: #{tool_call_id}")
    reason = (
        action.get("reason")
        or action.get("summary")
        or action.get("text")
        or action.get("note")
        or action.get("question")
        or ""
    )
    if reason:
        lines.append(f"reason: {clip_output(str(reason), 500)}")
    if action_type == "batch":
        tools = action.get("tools") or []
        lines.append(f"tools: {len(tools)}")
        for index, tool in enumerate(tools[:5], start=1):
            tool_type = tool.get("type") or tool.get("tool") or "unknown"
            details = []
            for key in ("path", "query", "pattern", "command", "cwd", "base", "offset", "limit"):
                value = tool.get(key)
                if value is not None and value != "":
                    details.append(f"{key}={clip_output(str(value), 120)}")
            suffix = " " + " ".join(details) if details else ""
            lines.append(f"- {index}. {tool_type}{suffix}")
        return "\n".join(lines)
    for key in WORK_ACTION_DISPLAY_FIELDS:
        value = _display_value(action, parameters, key)
        if value is None or value == "":
            continue
        if isinstance(value, bool) and not value and key != "apply":
            continue
        lines.append(f"{key}: {clip_output(str(value), 500)}")
    for key in ("content", "old", "new"):
        value = _display_value(action, parameters, key)
        if value is not None:
            lines.append(f"{key}: {len(str(value))} chars")
    return "\n".join(lines)


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
    resume = build_work_session_resume(session, task=task, limit=limit)
    lines = [
        f"Work session #{session.get('id')} [{session.get('status')}] task=#{session.get('task_id')}",
        f"title: {session.get('title') or (task or {}).get('title') or ''}",
        f"goal: {session.get('goal') or ''}",
        f"phase: {(resume or {}).get('phase') or 'unknown'}",
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
                tool_call_ids = turn.get("tool_call_ids") or []
                if tool_call_ids:
                    tool_text = " tool_calls=" + ",".join(f"#{value}" for value in tool_call_ids)
                else:
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

        failure_calls = [(call, work_tool_failure_record(call)) for call in calls]
        failure_calls = [(call, record) for call, record in failure_calls if record]
        lines.extend(["", "Verification failures"])
        if failure_calls:
            for call, record in failure_calls[-limit:]:
                lines.append(
                    f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                    f"{call.get('error') or ''}"
                )
                lines.append(format_command_failure_summary(record))
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
            summary = call.get("summary") or call.get("error") or ""
            if not details:
                summary = compact_work_tool_summary(call)
            lines.append(
                f"#{call.get('id')} [{call.get('status')}] {call.get('tool')} "
                f"{summary}"
            )
    return "\n".join(lines)


def work_session_task(state, session):
    if not session:
        return None
    return find_task(state, session.get("task_id"))
