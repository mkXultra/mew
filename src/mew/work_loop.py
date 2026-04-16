import json

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
)
from .work_world import DEFAULT_WORLD_STATE_FILE_LIMIT, build_work_world_state


WORK_BATCH_ACTIONS = {"batch"}
WORK_CONTROL_ACTIONS = {"finish", "send_message", "ask_user", "remember", "wait"}
WORK_MODEL_ACTIONS = set(WORK_TOOLS) | WORK_CONTROL_ACTIONS
WORK_MODEL_ACTIONS |= WORK_BATCH_ACTIONS
WORK_RESULT_TEXT_LIMIT = 20000
WORK_READ_FILE_CONTEXT_TEXT_LIMIT = 12000
WORK_CONTEXT_RECENT_TOOL_CALLS = 12
WORK_SESSION_KNOWLEDGE_LIMIT = 30
WORK_SESSION_KNOWLEDGE_BUDGET = 3000


def _json_clip(value, limit=WORK_RESULT_TEXT_LIMIT):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return clip_output(text, limit)


def _compact_tool_result(tool, result):
    result = result or {}
    if tool == "read_file":
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
        return {
            key: result.get(key)
            for key in ("path", "query", "pattern", "entries", "matches", "truncated")
            if key in result
        }
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
    return {
        "date": {"now": current_time},
        "task": {
            "id": task.get("id") if task else session.get("task_id"),
            "title": task.get("title") if task else session.get("title"),
            "description": task.get("description") if task else session.get("goal"),
            "status": task.get("status") if task else "",
            "kind": task.get("kind") if task else "",
            "notes": clip_output((task or {}).get("notes") or "", WORK_RESULT_TEXT_LIMIT),
            "cwd": (task or {}).get("cwd") or ".",
        },
        "work_session": {
            "id": session.get("id"),
            "status": session.get("status"),
            "goal": session.get("goal"),
            "created_at": session.get("created_at"),
            "updated_at": session.get("updated_at"),
            "resume": resume,
            "world_state": world_state,
            "session_knowledge": build_session_knowledge(tool_calls),
            "tool_calls": [
                work_tool_call_for_model(call)
                for call in tool_calls[-WORK_CONTEXT_RECENT_TOOL_CALLS:]
            ],
            "model_turns": [
                work_model_turn_for_model(turn)
                for turn in model_turns[-8:]
            ],
        },
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
        '  "action": {\n'
        '    "type": "batch|inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|finish|send_message|ask_user|remember|wait",\n'
        '    "tools": [{"type": "inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log", "path": "required for read_file/glob/search_text", "query": "required for search_text", "pattern": "required for glob"}],\n'
        '    "path": "optional path",\n'
        '    "query": "search_text query",\n'
        '    "pattern": "glob pattern",\n'
        '    "command": "run_tests/run_command command",\n'
        '    "content": "write_file content",\n'
        '    "old": "edit_file old text",\n'
        '    "new": "edit_file new text",\n'
        '    "text": "send_message text",\n'
        '    "note": "remember note",\n'
        '    "question": "ask_user question",\n'
        '    "message_type": "assistant|info|warning",\n'
        '    "create": false,\n'
        '    "replace_all": false,\n'
        '    "dry_run": true,\n'
        '    "reason": "why this action is next"\n'
        "  }\n"
        "}"
    )


def build_work_think_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Choose exactly one next action for this active coding work session.\n"
        "Use prior tool_calls as your observation history. If you need more evidence, choose one narrow read tool. "
        "If you need multiple independent read-only observations, prefer one batch action with up to five read-only tools. "
        "If you can make a small safe edit, use edit_file or write_file. Writes default to dry_run=true; set dry_run=false only when verification is configured. "
        "Use run_tests for the configured verification command or a narrow test command. Use run_command only when shell is explicitly allowed. "
        "Use finish when the task is done or the next step is clear enough to stop.\n"
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
        "command",
        "cwd",
        "base",
        "limit",
        "offset",
        "content",
        "old",
        "new",
        "reason",
        "text",
        "summary",
        "note",
        "question",
        "message_type",
    ):
        if action.get(key) is not None:
            normalized[key] = action.get(key)
    for key in ("create", "replace_all", "staged", "stat"):
        if action.get(key) is not None:
            normalized[key] = bool(action.get(key))

    if not normalized.get("summary") and action_plan.get("summary"):
        normalized["summary"] = action_plan.get("summary")
    if action_type in WRITE_WORK_TOOLS:
        dry_run = action.get("dry_run")
        normalized["apply"] = bool(action.get("apply")) or dry_run is False
    if action_type == "run_tests" and not normalized.get("command") and verify_command:
        normalized["command"] = verify_command
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
    parameters.pop("type", None)
    parameters["allowed_write_roots"] = allowed_write_roots or []
    parameters["allow_shell"] = bool(allow_shell)
    parameters["allow_verify"] = bool(allow_verify)
    if verify_command and not parameters.get("verify_command"):
        parameters["verify_command"] = verify_command
    parameters.setdefault("verify_cwd", ".")
    parameters.setdefault("verify_timeout", verify_timeout)
    return parameters


def model_delta_progress(progress, session_id, phase):
    if not progress:
        return None

    def emit(delta):
        text = " ".join((delta or "").split())
        if text:
            progress(f"session #{session_id}: {phase} delta {clip_output(text, 240)}")

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
    if progress:
        progress(f"session #{session.get('id')}: THINK start")
    think_delta = model_delta_progress(progress, session.get("id"), "THINK") if stream_model else None
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
        act_delta = model_delta_progress(progress, session.get("id"), "ACT") if stream_model else None
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
    }
