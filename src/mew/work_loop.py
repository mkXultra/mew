import json
import os
import shlex

from .agent import call_model_json_with_retries
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, DEFAULT_MODEL_BACKEND
from .tasks import clip_output
from .timeutil import now_iso
from .work_session import (
    GIT_WORK_TOOLS,
    READ_ONLY_WORK_TOOLS,
    WORK_TOOLS,
    WRITE_WORK_TOOLS,
    build_work_session_resume,
    work_turn_guidance_snapshot,
)
from .work_world import DEFAULT_WORLD_STATE_FILE_LIMIT, build_work_world_state


WORK_BATCH_ACTIONS = {"batch"}
WORK_CONTROL_ACTIONS = {"finish", "send_message", "ask_user", "remember", "wait"}
WORK_MODEL_ACTIONS = set(WORK_TOOLS) | WORK_CONTROL_ACTIONS
WORK_MODEL_ACTIONS |= WORK_BATCH_ACTIONS
WORK_RESULT_TEXT_LIMIT = 20000
WORK_READ_FILE_CONTEXT_TEXT_LIMIT = 12000
WORK_MODEL_READ_FILE_DEFAULT_MAX_CHARS = WORK_READ_FILE_CONTEXT_TEXT_LIMIT
WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT = 1000
WORK_LIST_CONTEXT_ITEM_LIMIT = 100
WORK_CONTEXT_RECENT_TOOL_CALLS = 12
WORK_CONTEXT_BUDGET = 120000
WORK_CONTEXT_WINDOW_CANDIDATES = ((12, 8), (8, 6), (6, 4), (4, 2), (2, 2))
WORK_SESSION_KNOWLEDGE_LIMIT = 30
WORK_SESSION_KNOWLEDGE_BUDGET = 3000


def clip_work_task_notes(notes, limit=WORK_RESULT_TEXT_LIMIT):
    if not notes:
        return ""
    notes = str(notes)
    if len(notes) <= limit:
        return notes
    tail = notes[-limit:]
    line_break = tail.find("\n")
    if line_break != -1:
        tail = tail[line_break + 1 :]
    return "[...older task notes omitted...]\n" + tail


def _json_clip(value, limit=WORK_RESULT_TEXT_LIMIT):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return clip_output(text, limit)


def _compact_context_value(value, text_limit=WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT):
    if isinstance(value, str):
        return clip_output(value, text_limit)
    if isinstance(value, list):
        return [_compact_context_value(item, text_limit=text_limit) for item in value[:WORK_LIST_CONTEXT_ITEM_LIMIT]]
    if isinstance(value, dict):
        return {key: _compact_context_value(item, text_limit=text_limit) for key, item in value.items()}
    return value


def _compact_context_items(items):
    items = items if isinstance(items, list) else []
    return [_compact_context_value(item) for item in items[:WORK_LIST_CONTEXT_ITEM_LIMIT]]


def _compact_tool_result(tool, result):
    result = result or {}
    if tool == "read_file":
        if result.get("line_start") is not None:
            text = result.get("text") or ""
            context_truncated = len(text) > WORK_READ_FILE_CONTEXT_TEXT_LIMIT
            return {
                "path": result.get("path"),
                "line_start": result.get("line_start"),
                "line_end": result.get("line_end"),
                "next_line": result.get("next_line"),
                "text": clip_output(text, WORK_READ_FILE_CONTEXT_TEXT_LIMIT),
                "visible_chars": min(len(text), WORK_READ_FILE_CONTEXT_TEXT_LIMIT),
                "source_text_chars": len(text),
                "context_truncated": context_truncated,
                "source_truncated": bool(result.get("truncated")),
                "truncated": bool(result.get("truncated")) or context_truncated,
            }
        offset = result.get("offset") or 0
        text = result.get("text") or ""
        context_truncated = len(text) > WORK_READ_FILE_CONTEXT_TEXT_LIMIT
        visible_chars = min(len(text), WORK_READ_FILE_CONTEXT_TEXT_LIMIT)
        next_offset = result.get("next_offset")
        if context_truncated:
            next_offset = offset + visible_chars
        return {
            "path": result.get("path"),
            "offset": offset,
            "next_offset": next_offset,
            "text": clip_output(text, WORK_READ_FILE_CONTEXT_TEXT_LIMIT),
            "visible_chars": visible_chars,
            "source_text_chars": len(text),
            "context_truncated": context_truncated,
            "source_truncated": bool(result.get("truncated")),
            "truncated": bool(result.get("truncated")) or context_truncated,
        }
    if tool in ("inspect_dir", "glob", "search_text"):
        compact = {
            key: result.get(key)
            for key in ("path", "query", "pattern", "truncated")
            if key in result
        }
        if "entries" in result:
            entries = result.get("entries") or []
            compact["entries"] = _compact_context_items(entries)
            compact["entries_context_truncated"] = len(entries) > len(compact["entries"])
        if "matches" in result:
            matches = result.get("matches") or []
            compact["matches"] = _compact_context_items(matches)
            compact["matches_context_truncated"] = len(matches) > len(compact["matches"])
        if "snippets" in result:
            snippets = result.get("snippets") or []
            compact["snippets"] = _compact_context_items(snippets)
            compact["snippets_context_truncated"] = len(snippets) > len(compact["snippets"])
        return compact
    if tool in ("run_command", "run_tests", "git_status", "git_diff", "git_log"):
        return {
            "command": result.get("command"),
            "cwd": result.get("cwd"),
            "exit_code": result.get("exit_code"),
            "stdout": clip_output(result.get("stdout") or "", WORK_RESULT_TEXT_LIMIT),
            "stderr": clip_output(result.get("stderr") or "", WORK_RESULT_TEXT_LIMIT),
        }
    if tool in WRITE_WORK_TOOLS:
        return {
            "operation": result.get("operation"),
            "path": result.get("path"),
            "changed": result.get("changed"),
            "dry_run": result.get("dry_run"),
            "written": result.get("written"),
            "rolled_back": result.get("rolled_back"),
            "verification_exit_code": result.get("verification_exit_code"),
            "rollback_error": result.get("rollback_error"),
            "diff": clip_output(result.get("diff") or "", WORK_RESULT_TEXT_LIMIT),
        }
    return {"raw": _json_clip(result)}


def _compact_parameters(parameters):
    compact = {}
    for key, value in dict(parameters or {}).items():
        if isinstance(value, str):
            compact[key] = clip_output(value, 1000)
        else:
            compact[key] = value
    return compact


def _reasoning_value_text(value):
    if isinstance(value, str):
        return value
    return _json_clip(value, 2000)


def compact_turn_reasoning(turn):
    decision_plan = turn.get("decision_plan") or {}
    if not isinstance(decision_plan, dict) or not decision_plan:
        return ""
    parts = []
    for key, value in decision_plan.items():
        if key == "action" or value in (None, "", [], {}):
            continue
        parts.append(f"{key}: {clip_output(_reasoning_value_text(value), 2000)}")
    return clip_output("\n".join(parts), 4000)


def work_tool_call_for_model(call):
    tool = call.get("tool") or ""
    return {
        "id": call.get("id"),
        "tool": tool,
        "status": call.get("status"),
        "parameters": _compact_parameters(call.get("parameters") or {}),
        "summary": clip_output(call.get("summary") or "", WORK_RESULT_TEXT_LIMIT),
        "error": clip_output(call.get("error") or "", WORK_RESULT_TEXT_LIMIT),
        "result": _compact_tool_result(tool, call.get("result") or {}),
        "started_at": call.get("started_at"),
        "finished_at": call.get("finished_at"),
    }


def work_model_turn_for_model(turn):
    action = turn.get("action") or {}
    return {
        "id": turn.get("id"),
        "status": turn.get("status"),
        "action": {
            key: value
            for key, value in action.items()
            if key in ("type", "tool", "path", "query", "pattern", "reason", "summary", "note", "text", "question")
        },
        "guidance_snapshot": work_turn_guidance_snapshot(turn),
        "tool_call_id": turn.get("tool_call_id"),
        "tool_call_ids": turn.get("tool_call_ids") or [],
        "summary": clip_output(turn.get("summary") or "", WORK_RESULT_TEXT_LIMIT),
        "reasoning": compact_turn_reasoning(turn),
        "error": clip_output(turn.get("error") or "", WORK_RESULT_TEXT_LIMIT),
        "started_at": turn.get("started_at"),
        "finished_at": turn.get("finished_at"),
    }


def _count_items(value, key):
    items = (value or {}).get(key) or []
    return len(items) if isinstance(items, list) else 0


def digest_tool_call(call):
    tool = call.get("tool") or "unknown"
    result = call.get("result") or {}
    parameters = call.get("parameters") or {}
    path = result.get("path") or parameters.get("path") or parameters.get("cwd") or ""
    if tool == "read_file":
        text = result.get("text") or ""
        line_count = len(text.splitlines())
        if result.get("line_start") is not None:
            summary = (
                f"read_file {path or '(unknown)'} "
                f"lines={result.get('line_start')}-{result.get('line_end')} visible_lines={line_count} "
                f"truncated={bool(result.get('truncated'))}"
            )
        else:
            summary = (
                f"read_file {path or '(unknown)'} "
                f"lines={line_count} offset={result.get('offset', parameters.get('offset', 0))} "
                f"truncated={bool(result.get('truncated'))}"
            )
    elif tool == "inspect_dir":
        summary = f"inspect_dir {path or '.'} entries={_count_items(result, 'entries')}"
    elif tool == "search_text":
        query = parameters.get("query") or result.get("query") or ""
        summary = (
            f"search_text {query!r} "
            f"in {path or '.'} matches={_count_items(result, 'matches')}"
        )
    elif tool == "glob":
        pattern = parameters.get("pattern") or result.get("pattern") or ""
        summary = (
            f"glob {pattern!r} "
            f"in {path or '.'} matches={_count_items(result, 'matches')}"
        )
    elif tool in ("run_command", "run_tests", "git_status", "git_diff", "git_log"):
        summary = f"{tool} exit={result.get('exit_code')} command={result.get('command') or parameters.get('command') or ''}"
    elif tool in WRITE_WORK_TOOLS:
        verification = result.get("verification") or {}
        summary = (
            f"{tool} {path or '(unknown)'} changed={bool(result.get('changed'))} "
            f"dry_run={bool(result.get('dry_run'))} written={bool(result.get('written'))} "
            f"verification_exit={verification.get('exit_code', result.get('verification_exit_code'))}"
        )
    else:
        summary = call.get("summary") or call.get("error") or tool
    return {
        "tool_call_id": call.get("id"),
        "tool": tool,
        "status": call.get("status"),
        "summary": clip_output(summary, 300),
    }


def build_session_knowledge(calls, recent_count=WORK_CONTEXT_RECENT_TOOL_CALLS):
    older_calls = list(calls or [])[:-recent_count]
    entries = []
    for call in reversed(older_calls[-WORK_SESSION_KNOWLEDGE_LIMIT:]):
        entry = digest_tool_call(call)
        candidate = entries + [entry]
        if len(json.dumps(candidate, ensure_ascii=False)) > WORK_SESSION_KNOWLEDGE_BUDGET:
            break
        entries = candidate
    return entries


def _json_size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return len(str(value))


def build_work_session_context(
    session,
    task,
    tool_calls,
    model_turns,
    resume,
    world_state,
    recent_tool_count=WORK_CONTEXT_RECENT_TOOL_CALLS,
    recent_turn_count=8,
    compacted=False,
):
    work_context = {
        "id": session.get("id"),
        "status": session.get("status"),
        "goal": session.get("goal"),
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "resume": resume,
        "world_state": world_state,
        "session_knowledge": build_session_knowledge(tool_calls, recent_count=recent_tool_count),
        "tool_calls": [
            work_tool_call_for_model(call)
            for call in tool_calls[-recent_tool_count:]
        ],
        "model_turns": [
            work_model_turn_for_model(turn)
            for turn in model_turns[-recent_turn_count:]
        ],
    }
    if compacted:
        work_context["context_compaction"] = {
            "compacted": True,
            "budget_chars": WORK_CONTEXT_BUDGET,
            "recent_tool_calls": recent_tool_count,
            "recent_model_turns": recent_turn_count,
            "total_tool_calls": len(tool_calls),
            "total_model_turns": len(model_turns),
            "note": "Recent work context was compacted due to session size; use remember for durable observations.",
        }
    return work_context


def build_budgeted_work_session_context(session, task, tool_calls, model_turns, resume, world_state):
    chosen = None
    for index, (recent_tool_count, recent_turn_count) in enumerate(WORK_CONTEXT_WINDOW_CANDIDATES):
        candidate = build_work_session_context(
            session,
            task,
            tool_calls,
            model_turns,
            resume,
            world_state,
            recent_tool_count=recent_tool_count,
            recent_turn_count=recent_turn_count,
            compacted=index > 0,
        )
        if _json_size(candidate) <= WORK_CONTEXT_BUDGET:
            return candidate
        chosen = candidate
    if chosen is not None:
        chosen["context_compaction"]["final_size_chars"] = _json_size(chosen)
    return chosen or build_work_session_context(session, task, tool_calls, model_turns, resume, world_state)


def build_work_model_context(
    state,
    session,
    task,
    current_time,
    allowed_read_roots=None,
    allowed_write_roots=None,
    allow_shell=False,
    allow_verify=False,
    verify_command="",
    guidance="",
):
    tool_calls = list(session.get("tool_calls") or [])
    model_turns = list(session.get("model_turns") or [])
    resume = build_work_session_resume(session, task=task, limit=8)
    world_state = build_work_world_state(
        resume,
        allowed_read_roots or [],
        file_limit=DEFAULT_WORLD_STATE_FILE_LIMIT,
    )
    work_context = build_budgeted_work_session_context(
        session,
        task,
        tool_calls,
        model_turns,
        resume,
        world_state,
    )
    return {
        "date": {"now": current_time},
        "task": {
            "id": task.get("id") if task else session.get("task_id"),
            "title": task.get("title") if task else session.get("title"),
            "description": task.get("description") if task else session.get("goal"),
            "status": task.get("status") if task else "",
            "kind": task.get("kind") if task else "",
            "notes": clip_work_task_notes((task or {}).get("notes") or "", WORK_RESULT_TEXT_LIMIT),
            "cwd": (task or {}).get("cwd") or ".",
        },
        "work_session": work_context,
        "capabilities": {
            "tools": sorted(WORK_TOOLS),
            "control_actions": sorted(WORK_CONTROL_ACTIONS),
            "allowed_read_roots": allowed_read_roots or [],
            "allowed_write_roots": allowed_write_roots or [],
            "allow_shell": bool(allow_shell),
            "allow_verify": bool(allow_verify),
            "verify_command_configured": bool(verify_command),
        },
        "guidance": guidance or "",
    }


def _work_action_schema_text():
    return (
        "{\n"
        '  "summary": "short reason",\n'
        '  "working_memory": {"hypothesis": "what appears true now", "next_step": "what to do after reentry", "open_questions": ["unknowns"], "last_verified_state": "latest verification state"},\n'
        '  "action": {\n'
        '    "type": "batch|inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|finish|send_message|ask_user|remember|wait",\n'
        '    "tools": ['
        '{"type": "inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log", '
        '"path": "required for read_file/glob/search_text", '
        '"query": "required for search_text", '
        '"pattern": "required for glob", '
        '"max_chars": "optional read_file cap", '
        '"line_start": "optional 1-based read_file starting line from search_text results", '
        '"line_count": "optional read_file line count"}],\n'
        '    "path": "optional path",\n'
        '    "query": "search_text query",\n'
        '    "pattern": "glob pattern",\n'
        '    "max_chars": "optional read_file cap",\n'
        '    "line_start": "optional 1-based read_file starting line from search_text results",\n'
        '    "line_count": "optional read_file line count",\n'
        '    "stat": "optional git_diff diffstat; set false only when full diff is needed",\n'
        '    "command": "run_tests/run_command command",\n'
        '    "content": "write_file content",\n'
        '    "old": "edit_file old text",\n'
        '    "new": "edit_file new text",\n'
        '    "text": "send_message text",\n'
        '    "note": "remember note",\n'
        '    "question": "ask_user question",\n'
        '    "summary": "optional concrete result, recommendation, or stopping note",\n'
        '    "message_type": "assistant|info|warning",\n'
        '    "task_done": false,\n'
        '    "completion_summary": "optional task completion summary for finish",\n'
        '    "create": false,\n'
        '    "replace_all": false,\n'
        '    "dry_run": true,\n'
        '    "reason": "why this action is next"\n'
        "  }\n"
        "}"
    )


def _mew_subcommand_positions(parts):
    positions = []
    for index, token in enumerate(parts[:-1]):
        executable = os.path.basename(token)
        if executable == "mew":
            positions.append((index, index + 1))
        if token == "-m" and index + 1 < len(parts) and parts[index + 1] == "mew":
            positions.append((index, index + 2))
    return positions


def is_resident_loop_command(command):
    try:
        parts = shlex.split(command or "")
    except ValueError:
        return False
    resident_subcommands = {"attach", "chat", "do", "run", "session"}
    for _, subcommand_index in _mew_subcommand_positions(parts):
        subcommand = parts[subcommand_index] if subcommand_index < len(parts) else ""
        if subcommand in resident_subcommands:
            return True
        if subcommand == "work":
            trailing = parts[subcommand_index + 1 :]
            if "--ai" in trailing or "--live" in trailing:
                return True
    return False


def build_work_think_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Choose exactly one next action for this active coding work session.\n"
        "Treat guidance as the user's current instruction for this turn. If guidance asks for fresh inspection and read tools are available, use a targeted read action before finishing; do not finish solely because older notes or prior turns claim enough context. "
        "Fields named guidance_snapshot under prior turns or resume decisions are historical audit records, not current instructions. "
        "Treat the capabilities object as current and authoritative; if a read/write/verify root or command is allowed there, do not ask the user to pass the same flag again. "
        "Use prior tool_calls as your observation history. If you need more evidence, choose one narrow read tool. "
        "For code navigation, prefer search_text for symbols or option names before broad read_file; after search_text gives line numbers, use read_file with line_start and line_count to inspect only the relevant window. "
        "If you need multiple independent read-only observations, prefer one batch action with up to five read-only tools. "
        "If you can make a small safe edit, use edit_file or write_file. Writes default to dry_run=true; set dry_run=false only when verification is configured. "
        "Use run_tests for the configured verification command or a narrow test command. "
        "Do not use run_tests to invoke resident mew loops such as mew do, mew chat, mew run, or mew work --live; finish, remember, or ask_user instead. "
        "Use run_command only when shell is explicitly allowed. run_command is parsed with shlex and executed without a shell, so do not use pipes, redirection, &&, ||, or ; unless you wrap the behavior in an interpreter such as python -c. "
        "Use finish when the task is done or the next step is clear enough to stop. "
        "When finishing after investigation, evaluation, or recommendation guidance, include the concrete conclusion in action.summary or action.reason so the user does not have to infer it from prior tool output. "
        "Include a compact working_memory object that restates your current hypothesis, next intended step, open questions, and latest verified state for future reentry; keep it short and do not copy raw logs. "
        "For finish, set task_done=true only when the task itself should be marked done.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def build_work_act_prompt(context, decision_plan):
    return (
        "You are the ACT phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Normalize the THINK decision into one executable action. Preserve the intent, but remove unsupported fields. "
        "Never broaden file roots or permissions. If the decision is unsafe or unsupported, return wait with a reason.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"ThinkDecision JSON:\n{json.dumps(decision_plan, ensure_ascii=False, indent=2)}"
    )


def normalize_work_model_action(action_plan, verify_command=""):
    if not isinstance(action_plan, dict):
        action_plan = {}
    action = action_plan.get("action")
    if not isinstance(action, dict):
        actions = action_plan.get("actions")
        action = actions[0] if isinstance(actions, list) and actions and isinstance(actions[0], dict) else {}

    action_type = str(action.get("type") or action.get("tool") or "").strip()
    if action_type in ("done", "complete"):
        action_type = "finish"
    if action_type == "message":
        action_type = "send_message"
    if action_type not in WORK_MODEL_ACTIONS:
        return {
            "type": "wait",
            "reason": f"unsupported work action: {action_type or 'missing'}",
        }

    if action_type == "batch":
        raw_tools = action.get("tools") or action.get("actions") or []
        normalized_tools = []
        for item in raw_tools[:5]:
            if not isinstance(item, dict):
                continue
            sub_action = normalize_work_model_action({"action": item}, verify_command=verify_command)
            if sub_action.get("type") in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS) and valid_batch_sub_action(sub_action):
                normalized_tools.append(sub_action)
        if not normalized_tools:
            return {"type": "wait", "reason": "batch requires at least one read-only tool"}
        normalized = {"type": "batch", "tools": normalized_tools}
        if action.get("reason") is not None:
            normalized["reason"] = action.get("reason")
        if action_plan.get("summary"):
            normalized["summary"] = action_plan.get("summary")
        return normalized

    normalized = {"type": action_type}
    for key in (
        "path",
        "query",
        "pattern",
        "max_chars",
        "command",
        "cwd",
        "base",
        "limit",
        "offset",
        "line_start",
        "line_count",
        "content",
        "old",
        "new",
        "reason",
        "text",
        "summary",
        "note",
        "question",
        "message_type",
        "completion_summary",
    ):
        if action.get(key) is not None:
            normalized[key] = action.get(key)
    for key in ("create", "replace_all", "staged", "stat", "task_done"):
        if action.get(key) is not None:
            normalized[key] = bool(action.get(key))
    if action_type == "read_file" and normalized.get("line_start") is None:
        for alias in ("start_line", "line"):
            if action.get(alias) is not None:
                normalized["line_start"] = action.get(alias)
                break

    if not normalized.get("summary") and action_plan.get("summary"):
        normalized["summary"] = action_plan.get("summary")
    if action_type in WRITE_WORK_TOOLS:
        dry_run = action.get("dry_run")
        normalized["apply"] = bool(action.get("apply")) or dry_run is False
    if action_type == "run_tests":
        if not normalized.get("command") and verify_command:
            normalized["command"] = verify_command
        if is_resident_loop_command(normalized.get("command") or ""):
            return {
                "type": "wait",
                "reason": "run_tests cannot invoke a resident mew loop; use the configured verifier, finish, remember, or ask_user",
            }
    return normalized


def valid_batch_sub_action(action):
    action_type = (action or {}).get("type")
    if action_type == "read_file":
        return bool(action.get("path"))
    if action_type == "search_text":
        return bool(action.get("query"))
    if action_type == "glob":
        return bool(action.get("pattern"))
    return action_type in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS)


def work_tool_parameters_from_action(
    action,
    allowed_write_roots=None,
    allow_shell=False,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
):
    parameters = dict(action or {})
    action_type = action.get("type") or action.get("tool")
    parameters.pop("type", None)
    parameters["allowed_write_roots"] = allowed_write_roots or []
    parameters["allow_shell"] = bool(allow_shell)
    parameters["allow_verify"] = bool(allow_verify)
    if verify_command and not parameters.get("verify_command"):
        parameters["verify_command"] = verify_command
    parameters.setdefault("verify_cwd", ".")
    parameters.setdefault("verify_timeout", verify_timeout)
    if action_type == "read_file":
        try:
            parameters["max_chars"] = max(
                1,
                min(int(parameters.get("max_chars") or WORK_MODEL_READ_FILE_DEFAULT_MAX_CHARS), 50000),
            )
        except (TypeError, ValueError):
            parameters["max_chars"] = WORK_MODEL_READ_FILE_DEFAULT_MAX_CHARS
        for key, maximum in (("line_start", 1_000_000), ("line_count", 1000)):
            if parameters.get(key) is None:
                continue
            try:
                parameters[key] = max(1, min(int(parameters.get(key)), maximum))
            except (TypeError, ValueError):
                parameters.pop(key, None)
    if action_type == "search_text":
        try:
            parameters["context_lines"] = max(0, min(int(parameters.get("context_lines") or 3), 5))
        except (TypeError, ValueError):
            parameters["context_lines"] = 3
    if action_type == "git_diff" and "stat" not in parameters:
        parameters["stat"] = True
    return parameters


def compact_model_stream(deltas):
    if not deltas:
        return {}
    phases = []
    for phase in ("THINK", "ACT"):
        texts = [item.get("text") or "" for item in deltas if item.get("phase") == phase]
        if not texts:
            continue
        joined = "".join(texts)
        phases.append(
            {
                "phase": phase,
                "chunks": len(texts),
                "chars": len(joined),
                "preview": clip_output(joined, 500),
            }
        )
    return {"phases": phases, "chunks": len(deltas), "chars": sum(len(item.get("text") or "") for item in deltas)}


def model_delta_progress(progress, session_id, phase, sink=None):
    if not progress and sink is None:
        return None

    def emit(delta):
        raw_text = delta if isinstance(delta, str) else str(delta or "")
        display_text = " ".join(raw_text.split())
        if raw_text and sink:
            sink(phase, raw_text)
        if display_text and progress:
            progress(f"session #{session_id}: {phase} delta {clip_output(display_text, 240)}")

    return emit


def plan_work_model_turn(
    state,
    session,
    task,
    model_auth,
    model=DEFAULT_CODEX_MODEL,
    base_url=DEFAULT_CODEX_WEB_BASE_URL,
    model_backend=DEFAULT_MODEL_BACKEND,
    timeout=60,
    allowed_read_roots=None,
    allowed_write_roots=None,
    allow_shell=False,
    allow_verify=False,
    verify_command="",
    guidance="",
    progress=None,
    act_mode="model",
    stream_model=False,
    model_delta_sink=None,
    progress_model_deltas=True,
):
    current_time = now_iso()
    context = build_work_model_context(
        state,
        session,
        task,
        current_time,
        allowed_read_roots=allowed_read_roots,
        allowed_write_roots=allowed_write_roots,
        allow_shell=allow_shell,
        allow_verify=allow_verify,
        verify_command=verify_command,
        guidance=guidance,
    )
    stream_deltas = []

    def capture_delta(phase, text):
        stream_deltas.append({"phase": phase, "text": text})
        if model_delta_sink:
            model_delta_sink(phase, text)

    if progress:
        progress(f"session #{session.get('id')}: THINK start")
    delta_progress = progress if progress_model_deltas else None
    think_delta = model_delta_progress(delta_progress, session.get("id"), "THINK", sink=capture_delta) if stream_model else None
    think_kwargs = {"on_text_delta": think_delta} if think_delta else {}
    decision_plan = call_model_json_with_retries(
        model_backend,
        model_auth,
        build_work_think_prompt(context),
        model,
        base_url,
        timeout,
        log_prefix=f"{current_time}: work_think {model_backend} session={session.get('id')}",
        **think_kwargs,
    )
    if progress:
        progress(f"session #{session.get('id')}: THINK ok")
    if act_mode == "deterministic":
        action = normalize_work_model_action(decision_plan, verify_command=verify_command)
        action_plan = {
            "summary": decision_plan.get("summary") or action.get("summary") or action.get("reason") or "",
            "action": action,
            "act_mode": "deterministic",
        }
        if progress:
            progress(f"session #{session.get('id')}: ACT deterministic action={action.get('type') or 'unknown'}")
    else:
        if progress:
            progress(f"session #{session.get('id')}: ACT start")
        act_delta = model_delta_progress(delta_progress, session.get("id"), "ACT", sink=capture_delta) if stream_model else None
        act_kwargs = {"on_text_delta": act_delta} if act_delta else {}
        action_plan = call_model_json_with_retries(
            model_backend,
            model_auth,
            build_work_act_prompt(context, decision_plan),
            model,
            base_url,
            timeout,
            log_prefix=f"{current_time}: work_act {model_backend} session={session.get('id')}",
            **act_kwargs,
        )
    action = normalize_work_model_action(action_plan, verify_command=verify_command)
    if progress:
        progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
    return {
        "decision_plan": decision_plan,
        "action_plan": action_plan,
        "action": action,
        "context": context,
        "model_stream": compact_model_stream(stream_deltas),
    }
