import json
import os
import shlex
import time

from .agent import call_model_json_with_retries
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, DEFAULT_MODEL_BACKEND
from .reasoning_policy import codex_reasoning_effort_scope, select_work_reasoning_policy
from .tasks import clip_output
from .timeutil import now_iso
from .work_session import (
    GIT_WORK_TOOLS,
    READ_ONLY_WORK_TOOLS,
    WORK_TOOLS,
    WRITE_WORK_TOOLS,
    attach_work_resume_world_state,
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
WORK_MODEL_SEARCH_TEXT_DEFAULT_MAX_MATCHES = 20
WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT = 1000
WORK_LIST_CONTEXT_ITEM_LIMIT = 100
WORK_CONTEXT_RECENT_TOOL_CALLS = 12
WORK_CONTEXT_BUDGET = 120000
WORK_CONTEXT_WINDOW_CANDIDATES = ((12, 8), (8, 6), (6, 4), (4, 2), (2, 2))
WORK_COMPACT_RESULT_TEXT_LIMIT = 4000
WORK_COMPACT_READ_FILE_CONTEXT_TEXT_LIMIT = 1200
WORK_COMPACT_LIST_ITEM_CONTEXT_TEXT_LIMIT = 300
WORK_COMPACT_LIST_CONTEXT_ITEM_LIMIT = 20
WORK_COMPACT_CONTEXT_BUDGET = 25000
WORK_COMPACT_CONTEXT_WINDOW_CANDIDATES = ((6, 4), (4, 2), (2, 2), (1, 1))
WORK_COMPACT_TASK_TEXT_LIMIT = 1200
WORK_COMPACT_RESUME_TEXT_LIMIT = 600
WORK_COMPACT_RESUME_ITEM_LIMIT = 6
WORK_COMPACT_ACTIVE_MEMORY_ITEM_LIMIT = 3
WORK_COMPACT_ACTIVE_MEMORY_TERMS_LIMIT = 12
WORK_RECENT_READ_FILE_WINDOW_LIMIT = 2
WORK_RECENT_READ_FILE_WINDOW_TEXT_LIMIT = 6000
WORK_SESSION_KNOWLEDGE_LIMIT = 30
WORK_SESSION_KNOWLEDGE_BUDGET = 3000
WORK_TASK_NOTES_CONTEXT_LINES = 12


def clip_work_task_notes(notes, limit=WORK_RESULT_TEXT_LIMIT, max_lines=WORK_TASK_NOTES_CONTEXT_LINES):
    if not notes:
        return ""
    notes = str(notes)
    lines = notes.splitlines()
    if len(lines) > max_lines:
        notes = "[...older task notes omitted...]\n" + "\n".join(lines[-max_lines:])
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


def _compact_context_value(
    value,
    text_limit=WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT,
    item_limit=WORK_LIST_CONTEXT_ITEM_LIMIT,
):
    if isinstance(value, str):
        return clip_output(value, text_limit)
    if isinstance(value, list):
        return [
            _compact_context_value(item, text_limit=text_limit, item_limit=item_limit)
            for item in value[:item_limit]
        ]
    if isinstance(value, dict):
        return {
            key: _compact_context_value(item, text_limit=text_limit, item_limit=item_limit)
            for key, item in value.items()
        }
    return value


def _compact_context_items(
    items,
    text_limit=WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT,
    item_limit=WORK_LIST_CONTEXT_ITEM_LIMIT,
):
    items = items if isinstance(items, list) else []
    return [
        _compact_context_value(item, text_limit=text_limit, item_limit=item_limit)
        for item in items[:item_limit]
    ]


def _compact_tool_result(
    tool,
    result,
    *,
    read_file_text_limit=WORK_READ_FILE_CONTEXT_TEXT_LIMIT,
    result_text_limit=WORK_RESULT_TEXT_LIMIT,
    list_item_text_limit=WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT,
    list_item_limit=WORK_LIST_CONTEXT_ITEM_LIMIT,
):
    result = result or {}
    if tool == "read_file":
        if result.get("line_start") is not None:
            text = result.get("text") or ""
            context_truncated = len(text) > read_file_text_limit
            return {
                "path": result.get("path"),
                "line_start": result.get("line_start"),
                "line_end": result.get("line_end"),
                "next_line": result.get("next_line"),
                "text": clip_output(text, read_file_text_limit),
                "visible_chars": min(len(text), read_file_text_limit),
                "source_text_chars": len(text),
                "context_truncated": context_truncated,
                "source_truncated": bool(result.get("truncated")),
                "truncated": bool(result.get("truncated")) or context_truncated,
            }
        offset = result.get("offset") or 0
        text = result.get("text") or ""
        context_truncated = len(text) > read_file_text_limit
        visible_chars = min(len(text), read_file_text_limit)
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
            compact["entries"] = _compact_context_items(
                entries,
                text_limit=list_item_text_limit,
                item_limit=list_item_limit,
            )
            compact["entries_context_truncated"] = len(entries) > len(compact["entries"])
        if "matches" in result:
            matches = result.get("matches") or []
            compact["matches"] = _compact_context_items(
                matches,
                text_limit=list_item_text_limit,
                item_limit=list_item_limit,
            )
            compact["matches_context_truncated"] = len(matches) > len(compact["matches"])
        if "snippets" in result:
            snippets = result.get("snippets") or []
            compact["snippets"] = _compact_context_items(
                snippets,
                text_limit=list_item_text_limit,
                item_limit=list_item_limit,
            )
            compact["snippets_context_truncated"] = len(snippets) > len(compact["snippets"])
        return compact
    if tool in ("run_command", "run_tests", "git_status", "git_diff", "git_log"):
        return {
            "command": result.get("command"),
            "cwd": result.get("cwd"),
            "exit_code": result.get("exit_code"),
            "stdout": clip_output(result.get("stdout") or "", result_text_limit),
            "stderr": clip_output(result.get("stderr") or "", result_text_limit),
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
            "diff": clip_output(result.get("diff") or "", result_text_limit),
        }
    return {"raw": _json_clip(result)}


def _compact_parameters(parameters, *, text_limit=1000):
    compact = {}
    for key, value in dict(parameters or {}).items():
        if isinstance(value, str):
            compact[key] = clip_output(value, text_limit)
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


def work_tool_call_for_model(call, *, prompt_context_mode="full"):
    tool = call.get("tool") or ""
    compact_prompt = prompt_context_mode != "full"
    result_text_limit = WORK_COMPACT_RESULT_TEXT_LIMIT if compact_prompt else WORK_RESULT_TEXT_LIMIT
    read_file_text_limit = (
        WORK_COMPACT_READ_FILE_CONTEXT_TEXT_LIMIT if compact_prompt else WORK_READ_FILE_CONTEXT_TEXT_LIMIT
    )
    list_item_text_limit = (
        WORK_COMPACT_LIST_ITEM_CONTEXT_TEXT_LIMIT if compact_prompt else WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT
    )
    list_item_limit = WORK_COMPACT_LIST_CONTEXT_ITEM_LIMIT if compact_prompt else WORK_LIST_CONTEXT_ITEM_LIMIT
    item = {
        "id": call.get("id"),
        "tool": tool,
        "status": call.get("status"),
        "parameters": _compact_parameters(
            call.get("parameters") or {},
            text_limit=400 if compact_prompt else 1000,
        ),
        "summary": clip_output(call.get("summary") or "", result_text_limit),
        "error": clip_output(call.get("error") or "", result_text_limit),
        "result": _compact_tool_result(
            tool,
            call.get("result") or {},
            read_file_text_limit=read_file_text_limit,
            result_text_limit=result_text_limit,
            list_item_text_limit=list_item_text_limit,
            list_item_limit=list_item_limit,
        ),
        "started_at": call.get("started_at"),
        "finished_at": call.get("finished_at"),
    }
    if compact_prompt:
        item["prompt_context_compacted"] = True
    if call.get("repeat_guard"):
        item["repeat_guard"] = _compact_context_value(
            call.get("repeat_guard"),
            text_limit=list_item_text_limit,
            item_limit=list_item_limit,
        )
    return item


def work_model_turn_for_model(turn, *, prompt_context_mode="full"):
    action = turn.get("action") or {}
    compact_prompt = prompt_context_mode != "full"
    text_limit = 1000 if compact_prompt else WORK_RESULT_TEXT_LIMIT
    item = {
        "id": turn.get("id"),
        "status": turn.get("status"),
        "action": {
            key: value
            for key, value in action.items()
            if key in ("type", "tool", "path", "query", "pattern", "reason", "summary", "note", "text", "question")
        },
        "guidance_snapshot": clip_output(work_turn_guidance_snapshot(turn), text_limit),
        "tool_call_id": turn.get("tool_call_id"),
        "tool_call_ids": turn.get("tool_call_ids") or [],
        "summary": clip_output(turn.get("summary") or "", text_limit),
        "reasoning": clip_output(compact_turn_reasoning(turn), text_limit),
        "error": clip_output(turn.get("error") or "", text_limit),
        "started_at": turn.get("started_at"),
        "finished_at": turn.get("finished_at"),
    }
    if compact_prompt:
        item["prompt_context_compacted"] = True
    return item


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


def build_recent_read_file_windows(
    calls,
    *,
    limit=WORK_RECENT_READ_FILE_WINDOW_LIMIT,
    text_limit=WORK_RECENT_READ_FILE_WINDOW_TEXT_LIMIT,
):
    windows = []
    for call in reversed(list(calls or [])):
        if len(windows) >= limit:
            break
        if call.get("tool") != "read_file" or call.get("status") != "completed":
            continue
        result = call.get("result") or {}
        text = result.get("text") or ""
        if not text:
            continue
        clipped = clip_output(text, text_limit)
        windows.append(
            {
                "tool_call_id": call.get("id"),
                "path": result.get("path") or (call.get("parameters") or {}).get("path"),
                "line_start": result.get("line_start"),
                "line_end": result.get("line_end"),
                "offset": result.get("offset"),
                "text": clipped,
                "visible_chars": min(len(text), text_limit),
                "source_text_chars": len(text),
                "context_truncated": len(text) > text_limit,
            }
        )
    return windows


def _json_size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return len(str(value))


def _round_seconds(value):
    return round(float(value), 3)


def _active_memory_metrics(context):
    resume = ((context or {}).get("work_session") or {}).get("resume") or {}
    active_memory = resume.get("active_memory") or []
    if isinstance(active_memory, dict):
        entries = len(active_memory.get("items") or [])
    else:
        entries = len(active_memory) if isinstance(active_memory, list) else 0
    return {
        "active_memory_chars": _json_size(active_memory),
        "active_memory_entries": entries,
    }


def _recent_read_window_metrics(context):
    work_session = (context or {}).get("work_session") or {}
    windows = work_session.get("recent_read_file_windows") or []
    if not isinstance(windows, list):
        windows = []
    return {
        "recent_read_window_chars": _json_size(windows),
        "recent_read_window_count": len(windows),
    }


def compact_active_memory_for_prompt(
    active_memory,
    *,
    mode="compact_memory",
    item_limit=WORK_COMPACT_ACTIVE_MEMORY_ITEM_LIMIT,
    terms_limit=WORK_COMPACT_ACTIVE_MEMORY_TERMS_LIMIT,
):
    active_memory = active_memory if isinstance(active_memory, dict) else {}
    items = []
    source_items = active_memory.get("items") or []
    for item in source_items[:item_limit]:
        if not isinstance(item, dict):
            continue
        compact = {
            key: item.get(key)
            for key in (
                "id",
                "scope",
                "memory_scope",
                "type",
                "memory_type",
                "key",
                "name",
                "description",
                "created_at",
                "storage",
                "path",
                "score",
                "reason",
                "matched_terms",
            )
            if item.get(key) not in (None, "", [], {})
        }
        if item.get("text"):
            compact["text_omitted"] = True
        items.append(compact)
    return {
        "source": active_memory.get("source") or ".mew/memory",
        "terms": list(active_memory.get("terms") or [])[:terms_limit],
        "items": items,
        "total": active_memory.get("total") or len(items),
        "shown": len(items),
        "truncated": bool(active_memory.get("truncated")),
        "compacted_for_prompt": True,
        "prompt_context_mode": mode,
        "note": "Memory bodies are omitted in this prompt mode; use id/path as pointers and verify facts with tools.",
    }


def compact_resume_for_prompt(resume, *, mode="compact_memory"):
    compacted = dict(resume or {})
    compacted["active_memory"] = compact_active_memory_for_prompt(
        compacted.get("active_memory"),
        mode=mode,
    )
    for key in (
        "goal",
        "working_memory",
        "recovery_plan",
        "recent_decisions",
        "compressed_prior_think",
        "same_surface_audit",
        "continuity",
        "effort",
        "notes",
        "low_yield_observations",
        "failures",
        "unresolved_failure",
        "recurring_failures",
        "suggested_safe_reobserve",
        "world_state",
        "files_touched",
        "queued_followups",
        "pending_steer",
        "next_action",
    ):
        if key in compacted:
            compacted[key] = _compact_context_value(
                compacted.get(key),
                text_limit=WORK_COMPACT_RESUME_TEXT_LIMIT,
                item_limit=WORK_COMPACT_RESUME_ITEM_LIMIT,
            )
    compacted["prompt_context"] = {
        "mode": mode,
        "active_memory_body_injection": "omitted",
        "resume_text_limit": WORK_COMPACT_RESUME_TEXT_LIMIT,
        "resume_item_limit": WORK_COMPACT_RESUME_ITEM_LIMIT,
    }
    return compacted


def work_prompt_context_mode(reasoning_policy):
    if (reasoning_policy or {}).get("effort") in {"high", "xhigh"}:
        return "full"
    if (reasoning_policy or {}).get("work_type") == "high_risk":
        return "full"
    return "compact_memory"


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
    prompt_context_mode="full",
):
    prompt_compacted = prompt_context_mode != "full"
    goal = session.get("goal")
    if prompt_compacted:
        goal = clip_output(goal or "", WORK_COMPACT_TASK_TEXT_LIMIT)
    work_context = {
        "id": session.get("id"),
        "status": session.get("status"),
        "goal": goal,
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "effort": (resume or {}).get("effort") or {},
        "resume": resume,
        "world_state": world_state,
        "session_knowledge": build_session_knowledge(tool_calls, recent_count=recent_tool_count),
        "tool_calls": [
            work_tool_call_for_model(call, prompt_context_mode=prompt_context_mode)
            for call in tool_calls[-recent_tool_count:]
        ],
        "model_turns": [
            work_model_turn_for_model(turn, prompt_context_mode=prompt_context_mode)
            for turn in model_turns[-recent_turn_count:]
        ],
    }
    work_context["recent_read_file_windows"] = build_recent_read_file_windows(tool_calls)
    if compacted or prompt_compacted:
        note = "Recent work context was compacted due to session size; use remember for durable observations."
        if work_context.get("recent_read_file_windows"):
            note = (
                "Recent work context was reduced; use recent_read_file_windows for exact recent file text "
                "and keep any new read_file window narrow."
            )
        work_context["context_compaction"] = {
            "compacted": bool(compacted),
            "prompt_context_compacted": prompt_compacted,
            "prompt_context_mode": prompt_context_mode,
            "budget_chars": WORK_COMPACT_CONTEXT_BUDGET if prompt_compacted else WORK_CONTEXT_BUDGET,
            "recent_tool_calls": recent_tool_count,
            "recent_model_turns": recent_turn_count,
            "total_tool_calls": len(tool_calls),
            "total_model_turns": len(model_turns),
            "note": note,
        }
    return work_context


def build_budgeted_work_session_context(
    session,
    task,
    tool_calls,
    model_turns,
    resume,
    world_state,
    *,
    prompt_context_mode="full",
):
    chosen = None
    prompt_compacted = prompt_context_mode != "full"
    budget = WORK_COMPACT_CONTEXT_BUDGET if prompt_compacted else WORK_CONTEXT_BUDGET
    candidates = WORK_COMPACT_CONTEXT_WINDOW_CANDIDATES if prompt_compacted else WORK_CONTEXT_WINDOW_CANDIDATES
    for index, (recent_tool_count, recent_turn_count) in enumerate(candidates):
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
            prompt_context_mode=prompt_context_mode,
        )
        if _json_size(candidate) <= budget:
            return candidate
        chosen = candidate
    if chosen is not None:
        chosen["context_compaction"]["final_size_chars"] = _json_size(chosen)
    return chosen or build_work_session_context(
        session,
        task,
        tool_calls,
        model_turns,
        resume,
        world_state,
        prompt_context_mode=prompt_context_mode,
    )


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
    prompt_context_mode="full",
):
    tool_calls = list(session.get("tool_calls") or [])
    model_turns = list(session.get("model_turns") or [])
    resume = build_work_session_resume(session, task=task, limit=8, state=state, current_time=current_time)
    world_state = build_work_world_state(
        resume,
        allowed_read_roots or [],
        file_limit=DEFAULT_WORLD_STATE_FILE_LIMIT,
    )
    resume = attach_work_resume_world_state(resume, world_state)
    if prompt_context_mode != "full":
        resume = compact_resume_for_prompt(resume, mode=prompt_context_mode)
    work_context = build_budgeted_work_session_context(
        session,
        task,
        tool_calls,
        model_turns,
        resume,
        world_state,
        prompt_context_mode=prompt_context_mode,
    )
    task_description = task.get("description") if task else session.get("goal")
    task_notes = (task or {}).get("notes") or ""
    if prompt_context_mode != "full":
        task_description = clip_output(task_description or "", WORK_COMPACT_TASK_TEXT_LIMIT)
        task_notes = clip_work_task_notes(task_notes, WORK_COMPACT_TASK_TEXT_LIMIT)
    return {
        "date": {"now": current_time},
        "task": {
            "id": task.get("id") if task else session.get("task_id"),
            "title": task.get("title") if task else session.get("title"),
            "description": task_description,
            "status": task.get("status") if task else "",
            "kind": task.get("kind") if task else "",
            "notes": clip_work_task_notes(task_notes, WORK_RESULT_TEXT_LIMIT),
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
        '  "working_memory": {"hypothesis": "what appears true now", "next_step": "what to do after reentry", "target_paths": ["narrow files or dirs to revisit first"], "open_questions": ["unknowns"], "last_verified_state": "latest verification state"},\n'
        '  "action": {\n'
        '    "type": "batch|inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|finish|send_message|ask_user|remember|wait",\n'
        '    "tools": ['
        '{"type": "inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log|write_file|edit_file", '
        '"path": "required for read_file/glob/search_text", '
        '"query": "required for search_text; literal fixed-string, so use batch for OR searches", '
        '"pattern": "required for glob; optional rg glob filter for search_text", '
        '"max_chars": "optional read_file cap", '
        '"line_start": "optional 1-based read_file starting line from search_text results", '
        '"line_count": "optional read_file line count", '
        '"content": "write_file content", '
        '"old": "edit_file old text", '
        '"new": "edit_file new text", '
        '"create": false, '
        '"replace_all": false, '
        '"dry_run": true}],\n'
        '    "path": "optional path",\n'
        '    "query": "search_text literal fixed-string query",\n'
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
        "Use work_session.resume.active_memory as durable typed recall about the user, project, feedback, or references; treat it as relevant context, but verify project facts with tools before relying on them for code changes. If active_memory.compacted_for_prompt is true, memory bodies were intentionally omitted; use id/path/name/description as pointers and read only the narrow source you need. "
        "Use work_session.effort as operational pressure. If effort.pressure is high, avoid broad exploration and prefer finish, remember, or ask_user with a concise state summary and a concrete replan. If effort.pressure is medium, choose a narrow next action and refresh working_memory so the next reentry is not stale. "
        "If working_memory.target_paths lists likely files or directories for the next step, and one already names the likely file or directory, prefer a direct read_file on one of those target_paths before repeating same-surface search_text; otherwise prefer those paths before a broader project search, and keep that list short and current. "
        "If work_session.resume.low_yield_observations lists repeated zero-match searches, do not keep searching that same path/pattern; use the suggested_next to switch to a targeted read, a single broader path, an edit from known context, or finish with a concrete replan. "
        "Use work_session.resume.continuity as the reentry contract. If continuity.status is weak or broken, or continuity.missing is non-empty, treat continuity.recommendation as the first repair queue before side-effecting actions; prefer targeted reads, remember, or ask_user to repair missing memory, risk, next-action, approval, recovery, verifier, budget, decision, or user-pivot state. "
        "For code navigation, prefer search_text for symbols or option names before broad read_file; after search_text gives line numbers, use read_file with line_start and line_count to inspect only the relevant window. If a handler definition is not in the current file but the symbol appears imported, search the broader project tree or allowed read root for that symbol instead of repeating same-file searches. "
        "If you need multiple independent read-only observations, prefer one batch action with up to five read-only tools. If work_session.recent_read_file_windows already contains the exact recent path/span or old text needed for edit preparation, reuse that recent window instead of issuing another same-span read_file. "
        "If you already know the exact paired tests/** and src/mew/** edits, you may use one batch action with up to five write/edit tools; this paired-write constraint applies to code write batches under tests/** and src/mew/**. Docs-only single edit_file/write_file actions in other allowed write roots may be proposed directly when the target path is clear. For a code write batch, every write must be under tests/** or src/mew/**, and at least one test edit plus one source edit is required. mew will force writes to dry-run previews and keep approval/verification gated. Do not mix reads with write batches. "
        "If you can make a small safe edit, use edit_file or write_file. For edit_file you must include exact old and new strings; if you are not sure of the exact old string, use work_session.recent_read_file_windows when available or read the smallest relevant file window first. Once a prior line-window read or recent_read_file_windows entry contains the exact old string, do not reread the full file solely to prepare edit_file. Writes default to dry_run=true; set dry_run=false only when verification is configured. "
        "When editing mew source under src/mew, include a paired tests/ change in the same work session when practical; if the write boundary stops you before the test edit, use any pairing_status.suggested_test_path from the resume/cells as the first test-file candidate and record the intended test in working_memory.next_step. If a targeted test-file search misses, search tests/ or the likely test module before concluding that no paired test surface exists. "
        "Use run_tests for the configured verification command or a narrow test command. "
        "If work_session.resume.suggested_verify_command.command is present and no verify_command is configured, prefer that suggested command before inventing a broader verifier. "
        "If verification_confidence.status is narrow after source edits and suggested_verify_command.command exists, prefer run_tests with that broader suggested verifier before finish unless guidance explicitly says the task is narrow-only. "
        "If the latest verification or write/apply step failed and the failure is not obviously permission/environment related, prefer one narrow repair step using the failing output or suggested_safe_reobserve before finish or ask_user. "
        "Do not invent test-only assertions for behavior you have not observed in source, command output, or current tests; inspect the producer first or make the paired source change in the same plan. "
        "If investigation shows the task premise is false, already covered, or intentionally handled by existing tests, do not force a source edit; prefer run_tests to validate the conclusion, then finish with a no-change summary and task_done=true only if the investigation task is complete. "
        "For unittest verification, prefer a module-level command unless you have confirmed the exact class and method name in the current file or just created that method in the applied write. "
        "Do not use run_tests to invoke resident mew loops such as mew do, mew chat, mew run, or mew work --live; finish, remember, or ask_user instead. "
        "Use run_command only when shell is explicitly allowed. run_command is parsed with shlex and executed without a shell, so do not use pipes, redirection, &&, ||, or ; unless you wrap the behavior in an interpreter such as python -c. "
        "Use finish when the task is done or when an investigation/recommendation task has a concrete conclusion. "
        "If work_session.resume.same_surface_audit.status indicates a sibling-surface audit is still needed after src/mew edits, do one narrow audit step or record why the sibling surface is already covered or out of scope before finish. "
        "For implementation tasks with allowed write roots, do not finish merely because the next edit is clear; if exact old/new text or file content is available, propose the dry-run edit_file/write_file action instead. "
        "When finishing after investigation, evaluation, or recommendation guidance, include the concrete conclusion in action.summary or action.reason so the user does not have to infer it from prior tool output. "
        "Include a compact working_memory object that restates your current hypothesis, "
        "next intended step, open questions, and latest verified state for future reentry; "
        "keep it short and do not copy raw logs. "
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


def normalize_work_model_action(action_plan, verify_command="", suggested_verify_command=""):
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
        saw_write_tool = False
        saw_non_write_tool = False
        dropped_tool_count = 0
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            sub_action = normalize_work_model_action(
                {"action": item},
                verify_command=verify_command,
                suggested_verify_command=suggested_verify_command,
            )
            dropped_tool_count += int(sub_action.get("truncated_tools") or 0)
            if sub_action.get("type") == "batch":
                sub_actions = sub_action.get("tools") or []
            else:
                sub_actions = [sub_action]
            for candidate in sub_actions:
                if candidate.get("type") in WRITE_WORK_TOOLS:
                    saw_write_tool = True
                    if len(normalized_tools) >= 5:
                        dropped_tool_count += 1
                        continue
                    normalized_tools.append(candidate)
                    continue
                if candidate.get("type") in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS) and valid_batch_sub_action(candidate):
                    saw_non_write_tool = True
                    if len(normalized_tools) >= 5:
                        dropped_tool_count += 1
                        continue
                    normalized_tools.append(candidate)
                else:
                    saw_non_write_tool = True
        if not normalized_tools:
            return {"type": "wait", "reason": "batch requires at least one read-only tool"}
        if saw_write_tool:
            if saw_non_write_tool:
                return {
                    "type": "wait",
                    "reason": "write batch cannot mix read-only tools; use a separate read step before paired writes",
                }
            paired_tools = normalize_paired_write_batch_tools(normalized_tools)
            if not paired_tools:
                return {
                    "type": "wait",
                    "reason": "write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each",
                }
            normalized_tools = paired_tools
        normalized = {"type": "batch", "tools": normalized_tools}
        if action.get("reason") is not None:
            normalized["reason"] = action.get("reason")
        if dropped_tool_count:
            normalized["truncated_tools"] = dropped_tool_count
            suffix = f"batch is limited to 5 tools; dropped {dropped_tool_count} additional tool(s)"
            normalized["reason"] = f"{normalized.get('reason')}; {suffix}" if normalized.get("reason") else suffix
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
    if action_type == "search_text":
        all_split_queries = split_pipe_search_query(normalized.get("query"), limit=None)
        unique_split_queries = list(dict.fromkeys(all_split_queries))
        split_queries = unique_split_queries[:5]
        if split_queries:
            tools = []
            for query in split_queries:
                tool = {
                    key: value
                    for key, value in normalized.items()
                    if key not in ("reason", "summary")
                }
                tool["query"] = query
                tools.append(tool)
            result = {
                "type": "batch",
                "tools": tools,
                "reason": normalized.get("reason")
                or "search_text uses literal fixed-string queries; split pipe-separated query into separate searches",
            }
            if normalized.get("summary"):
                result["summary"] = normalized.get("summary")
            dropped_tool_count = len(unique_split_queries) - len(split_queries)
            if dropped_tool_count:
                result["truncated_tools"] = dropped_tool_count
                result["reason"] = (
                    f"{result.get('reason')}; batch is limited to 5 tools; "
                    f"dropped {dropped_tool_count} additional search(es)"
                )
            return result

    if (
        action_type != "finish"
        and not (action_type == "wait" and normalized.get("reason"))
        and not normalized.get("summary")
        and action_plan.get("summary")
    ):
        normalized["summary"] = action_plan.get("summary")
    edit_old = normalized.get("old")
    edit_new = normalized.get("new")
    if action_type == "edit_file" and (
        not normalized.get("path")
        or not isinstance(edit_old, str)
        or edit_old == ""
        or not isinstance(edit_new, str)
    ):
        if normalized.get("path"):
            read_action = {
                "type": "read_file",
                "path": normalized.get("path"),
                "reason": "edit_file requires exact old and new strings; read the target window before retrying",
            }
            for key in ("line_start", "line_count", "summary"):
                if normalized.get(key) is not None:
                    read_action[key] = normalized.get(key)
            return read_action
        return {
            "type": "wait",
            "reason": "edit_file requires path plus exact old and new strings",
        }
    if action_type in WRITE_WORK_TOOLS:
        dry_run = action.get("dry_run")
        normalized["apply"] = bool(action.get("apply")) or dry_run is False
    if action_type == "run_tests":
        if not normalized.get("command"):
            if verify_command:
                normalized["command"] = verify_command
            elif suggested_verify_command:
                normalized["command"] = suggested_verify_command
        if is_resident_loop_command(normalized.get("command") or ""):
            return {
                "type": "wait",
                "reason": "run_tests cannot invoke a resident mew loop; use the configured verifier, finish, remember, or ask_user",
            }
    return normalized


def split_pipe_search_query(query, limit=5):
    if not isinstance(query, str) or "|" not in query:
        return []
    parts = [part.strip() for part in query.split("|") if part.strip()]
    if len(parts) < 2:
        return []
    return parts if limit is None else parts[:limit]


def valid_batch_sub_action(action):
    action_type = (action or {}).get("type")
    if action_type == "read_file":
        return bool(action.get("path"))
    if action_type == "search_text":
        return bool(action.get("query"))
    if action_type == "glob":
        return bool(action.get("pattern"))
    return action_type in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS)


def _normalized_work_path(path):
    return str(path or "").replace("\\", "/").lstrip("./")


def _work_batch_path_is_tests(path):
    normalized = _normalized_work_path(path)
    return normalized == "tests" or normalized.startswith("tests/")


def _work_batch_path_is_mew_source(path):
    normalized = _normalized_work_path(path)
    return normalized.startswith("src/mew/") and normalized.endswith(".py")


def valid_paired_write_batch_sub_action(action):
    action_type = (action or {}).get("type")
    if action_type == "write_file":
        return bool(action.get("path")) and isinstance(action.get("content"), str)
    if action_type == "edit_file":
        return (
            bool(action.get("path"))
            and isinstance(action.get("old"), str)
            and action.get("old") != ""
            and isinstance(action.get("new"), str)
        )
    return False


def normalize_paired_write_batch_tools(tools):
    write_tools = [dict(tool) for tool in tools or [] if (tool or {}).get("type") in WRITE_WORK_TOOLS]
    if len(write_tools) < 2:
        return []
    if not all(valid_paired_write_batch_sub_action(tool) for tool in write_tools):
        return []
    tests_tools = [tool for tool in write_tools if _work_batch_path_is_tests(tool.get("path"))]
    source_tools = [tool for tool in write_tools if _work_batch_path_is_mew_source(tool.get("path"))]
    if not tests_tools or not source_tools or len(tests_tools) + len(source_tools) != len(write_tools):
        return []
    source_path = source_tools[0].get("path")
    normalized = []
    for raw_tool in [*tests_tools, *source_tools]:
        tool = dict(raw_tool)
        tool["apply"] = False
        tool["dry_run"] = True
        if raw_tool in tests_tools:
            tool["defer_verify_on_approval"] = True
            tool["paired_test_source_path"] = source_path
        normalized.append(tool)
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
            parameters["max_matches"] = max(
                1,
                min(int(parameters.get("max_matches") or WORK_MODEL_SEARCH_TEXT_DEFAULT_MAX_MATCHES), 50),
            )
        except (TypeError, ValueError):
            parameters["max_matches"] = WORK_MODEL_SEARCH_TEXT_DEFAULT_MAX_MATCHES
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
    pre_model_metrics_sink=None,
):
    current_time = now_iso()
    capabilities = {
        "tools": sorted(WORK_TOOLS),
        "control_actions": sorted(WORK_CONTROL_ACTIONS),
        "allowed_read_roots": allowed_read_roots or [],
        "allowed_write_roots": allowed_write_roots or [],
        "allow_shell": bool(allow_shell),
        "allow_verify": bool(allow_verify),
        "verify_command_configured": bool(verify_command),
    }
    reasoning_policy = select_work_reasoning_policy(
        task,
        guidance=guidance,
        capabilities=capabilities,
    )
    prompt_context_mode = work_prompt_context_mode(reasoning_policy)
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
        prompt_context_mode=prompt_context_mode,
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
    think_prompt = build_work_think_prompt(context)
    work_session_context = (context or {}).get("work_session") or {}
    resume_context = work_session_context.get("resume") or {}
    suggested_verify_command = ""
    if isinstance(resume_context.get("suggested_verify_command"), dict):
        suggested_verify_command = str(
            (resume_context.get("suggested_verify_command") or {}).get("command") or ""
        )
    model_metrics = {
        "context_chars": _json_size(context),
        "work_session_chars": _json_size(work_session_context),
        "resume_chars": _json_size(work_session_context.get("resume")),
        "tool_context_chars": _json_size(work_session_context.get("tool_calls")),
        "model_turn_context_chars": _json_size(work_session_context.get("model_turns")),
        **_active_memory_metrics(context),
        **_recent_read_window_metrics(context),
        "think": {
            "prompt_chars": len(think_prompt),
        },
        "reasoning_policy": reasoning_policy,
        "reasoning_effort": reasoning_policy.get("effort") or "",
        "prompt_context_mode": prompt_context_mode,
    }
    if pre_model_metrics_sink:
        pre_model_metrics_sink(dict(model_metrics))
    think_started = time.monotonic()
    with codex_reasoning_effort_scope(reasoning_policy.get("effort")):
        decision_plan = call_model_json_with_retries(
            model_backend,
            model_auth,
            think_prompt,
            model,
            base_url,
            timeout,
            log_prefix=f"{current_time}: work_think {model_backend} session={session.get('id')}",
            **think_kwargs,
        )
    think_elapsed = time.monotonic() - think_started
    if progress:
        progress(f"session #{session.get('id')}: THINK ok")
    model_metrics["think"]["elapsed_seconds"] = _round_seconds(think_elapsed)
    if act_mode == "deterministic":
        action = normalize_work_model_action(
            decision_plan,
            verify_command=verify_command,
            suggested_verify_command=suggested_verify_command,
        )
        action_summary = action.get("reason") if action.get("type") == "wait" and action.get("reason") else ""
        action_plan = {
            "summary": action_summary or decision_plan.get("summary") or action.get("summary") or action.get("reason") or "",
            "action": action,
            "act_mode": "deterministic",
        }
        model_metrics["act"] = {
            "prompt_chars": 0,
            "elapsed_seconds": 0.0,
            "mode": "deterministic",
        }
        if progress:
            progress(f"session #{session.get('id')}: ACT deterministic action={action.get('type') or 'unknown'}")
    else:
        if progress:
            progress(f"session #{session.get('id')}: ACT start")
        act_delta = model_delta_progress(delta_progress, session.get("id"), "ACT", sink=capture_delta) if stream_model else None
        act_kwargs = {"on_text_delta": act_delta} if act_delta else {}
        act_prompt = build_work_act_prompt(context, decision_plan)
        act_started = time.monotonic()
        with codex_reasoning_effort_scope(reasoning_policy.get("effort")):
            action_plan = call_model_json_with_retries(
                model_backend,
                model_auth,
                act_prompt,
                model,
                base_url,
                timeout,
                log_prefix=f"{current_time}: work_act {model_backend} session={session.get('id')}",
                **act_kwargs,
            )
        act_elapsed = time.monotonic() - act_started
        model_metrics["act"] = {
            "prompt_chars": len(act_prompt),
            "elapsed_seconds": _round_seconds(act_elapsed),
            "mode": "model",
        }
    action = normalize_work_model_action(
        action_plan,
        verify_command=verify_command,
        suggested_verify_command=suggested_verify_command,
    )
    model_metrics["total_model_seconds"] = _round_seconds(
        (model_metrics.get("think") or {}).get("elapsed_seconds", 0.0)
        + (model_metrics.get("act") or {}).get("elapsed_seconds", 0.0)
    )
    if progress:
        progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
    return {
        "decision_plan": decision_plan,
        "action_plan": action_plan,
        "action": action,
        "context": context,
        "model_metrics": model_metrics,
        "model_stream": compact_model_stream(stream_deltas),
    }
