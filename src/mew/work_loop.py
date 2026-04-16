import json

from .agent import call_model_json_with_retries
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, DEFAULT_MODEL_BACKEND
from .tasks import clip_output
from .timeutil import now_iso
from .work_session import WORK_TOOLS, WRITE_WORK_TOOLS


WORK_CONTROL_ACTIONS = {"finish", "send_message", "ask_user", "wait"}
WORK_MODEL_ACTIONS = set(WORK_TOOLS) | WORK_CONTROL_ACTIONS
WORK_RESULT_TEXT_LIMIT = 4000


def _json_clip(value, limit=WORK_RESULT_TEXT_LIMIT):
    try:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        text = str(value)
    return clip_output(text, limit)


def _compact_tool_result(tool, result):
    result = result or {}
    if tool == "read_file":
        return {
            "path": result.get("path"),
            "text": clip_output(result.get("text") or "", WORK_RESULT_TEXT_LIMIT),
            "truncated": bool(result.get("truncated")),
        }
    if tool in ("inspect_dir", "glob", "search_text"):
        return {
            key: result.get(key)
            for key in ("path", "query", "pattern", "entries", "matches", "truncated")
            if key in result
        }
    if tool in ("run_command", "run_tests"):
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
            if key in ("type", "tool", "path", "query", "pattern", "reason", "summary")
        },
        "tool_call_id": turn.get("tool_call_id"),
        "summary": clip_output(turn.get("summary") or "", WORK_RESULT_TEXT_LIMIT),
        "error": clip_output(turn.get("error") or "", WORK_RESULT_TEXT_LIMIT),
        "started_at": turn.get("started_at"),
        "finished_at": turn.get("finished_at"),
    }


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
            "tool_calls": [
                work_tool_call_for_model(call)
                for call in list(session.get("tool_calls") or [])[-12:]
            ],
            "model_turns": [
                work_model_turn_for_model(turn)
                for turn in list(session.get("model_turns") or [])[-8:]
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
        '    "type": "inspect_dir|read_file|search_text|glob|run_tests|run_command|write_file|edit_file|finish|send_message|ask_user|wait",\n'
        '    "path": "optional path",\n'
        '    "query": "search_text query",\n'
        '    "pattern": "glob pattern",\n'
        '    "command": "run_tests/run_command command",\n'
        '    "content": "write_file content",\n'
        '    "old": "edit_file old text",\n'
        '    "new": "edit_file new text",\n'
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

    normalized = {"type": action_type}
    for key in (
        "path",
        "query",
        "pattern",
        "command",
        "content",
        "old",
        "new",
        "reason",
        "text",
        "summary",
        "question",
    ):
        if action.get(key) is not None:
            normalized[key] = action.get(key)
    for key in ("create", "replace_all"):
        if action.get(key) is not None:
            normalized[key] = bool(action.get(key))

    if action_type in WRITE_WORK_TOOLS:
        dry_run = action.get("dry_run")
        normalized["apply"] = bool(action.get("apply")) or dry_run is False
    if action_type == "run_tests" and not normalized.get("command") and verify_command:
        normalized["command"] = verify_command
    return normalized


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
    decision_plan = call_model_json_with_retries(
        model_backend,
        model_auth,
        build_work_think_prompt(context),
        model,
        base_url,
        timeout,
        log_prefix=f"{current_time}: work_think {model_backend} session={session.get('id')}",
    )
    if progress:
        progress(f"session #{session.get('id')}: THINK ok")
        progress(f"session #{session.get('id')}: ACT start")
    action_plan = call_model_json_with_retries(
        model_backend,
        model_auth,
        build_work_act_prompt(context, decision_plan),
        model,
        base_url,
        timeout,
        log_prefix=f"{current_time}: work_act {model_backend} session={session.get('id')}",
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
