import json
import multiprocessing
import hashlib
import os
from pathlib import Path
import re
import sys
import textwrap
import time
from io import StringIO
import tokenize

from .acceptance import extract_acceptance_constraints
from .agent import call_model_json_with_retries as _agent_call_model_json_with_retries
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, DEFAULT_MODEL_BACKEND
from .deliberation import (
    DELIBERATION_RESULT_SCHEMA_CONTRACT,
    build_deliberation_attempt_record,
    build_deliberation_fallback_event,
    evaluate_deliberation_request,
    validate_deliberation_result,
)
from .errors import MewError, ModelBackendError
from .patch_draft import (
    PATCH_BLOCKER_RECOVERY_ACTIONS,
    compile_patch_draft,
    compile_patch_draft_previews,
)
from .prompt_sections import (
    CACHE_POLICY_CACHEABLE,
    CACHE_POLICY_DYNAMIC,
    CACHE_POLICY_SESSION,
    PromptSection,
    STABILITY_DYNAMIC,
    STABILITY_SEMI_STATIC,
    STABILITY_STATIC,
    prompt_section_metrics,
    render_prompt_sections,
)
from .reasoning_policy import (
    codex_reasoning_effort_scope,
    normalize_reasoning_effort,
    select_work_reasoning_policy,
)
from .tasks import clip_output, task_scope_target_paths
from .test_discovery import normalize_work_path
from .timeutil import now_iso
from .toolbox import is_resident_mew_loop_command
from .work_replay import write_patch_draft_compiler_replay
from .work_session import (
    APPROVAL_STATUS_INDETERMINATE,
    GIT_WORK_TOOLS,
    READ_ONLY_WORK_TOOLS,
    WORK_TOOLS,
    WRITE_WORK_TOOLS,
    attach_work_resume_world_state,
    build_work_session_resume,
    compact_model_turns_for_prompt,
    work_session_default_cwd,
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
WORK_RECOVERY_CONTEXT_WINDOW_CANDIDATES = ((4, 2), (2, 1), (1, 1))
WORK_COMPACT_TASK_TEXT_LIMIT = 1200
WORK_COMPACT_RESUME_TEXT_LIMIT = 600
WORK_COMPACT_RESUME_ITEM_LIMIT = 6
WORK_COMPACT_ACTIVE_MEMORY_ITEM_LIMIT = 3
WORK_COMPACT_ACTIVE_MEMORY_TERMS_LIMIT = 12
WORK_RECOVERY_RESUME_TEXT_LIMIT = 320
WORK_RECOVERY_RESUME_ITEM_LIMIT = 4
WORK_RECOVERY_DECISION_ITEM_LIMIT = 2
WORK_RECOVERY_DECISION_TEXT_LIMIT = 160
WORK_RECOVERY_DECISION_GUIDANCE_LIMIT = 120
WORK_RECENT_READ_FILE_WINDOW_LIMIT = 5
WORK_RECENT_READ_FILE_WINDOW_TEXT_LIMIT = 6000
WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS = 90.0
WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS = 30.0
WORK_DELIBERATION_MODEL_TIMEOUT_SECONDS = 120.0
WORK_DELIBERATION_REASONING_EFFORT = "high"
WORK_DELIBERATION_MAX_ATTEMPTS_PER_TODO = 1
WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION = "v2"
WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION = "v4"
WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT = "low"
WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT_ENV = "MEW_WRITE_READY_TINY_DRAFT_REASONING_EFFORT"
WORK_WRITE_READY_RECENT_WINDOWS_PER_TARGET_PATH = 3
WORK_WRITE_READY_TIMEOUT_BLOCKER_CODE = "drafting_timeout_after_complete_cached_refs_no_artifact"
WORK_WRITE_READY_REFRESH_RECOVERABLE_BLOCKER_CODES = {
    "missing_exact_cached_window_texts",
    "cached_window_incomplete",
    "cached_window_text_truncated",
    "stale_cached_window_text",
    "old_text_not_found",
}
WORK_WRITE_READY_STRUCTURAL_NARROW_MIN_LINES = 80
WORK_LINE_WINDOW_ESTIMATED_CHARS_PER_LINE = 200
WORK_SESSION_KNOWLEDGE_LIMIT = 30
WORK_SESSION_KNOWLEDGE_BUDGET = 3000
WORK_TASK_NOTES_CONTEXT_LINES = 12
WORK_MODEL_PROCESS_JOIN_GRACE_SECONDS = 1.0
WORK_TASK_GOAL_TERM_RE = re.compile(r"\b[A-Za-z0-9]+(?:[_-][A-Za-z0-9]+)+\b")
WORK_TASK_GOAL_TERM_STOPWORDS = {
    "dry-run",
    "fast-path",
    "github-issue",
    "implementation-lane",
    "no-testmon",
    "prompt-only",
    "roadmap_status",
    "mew-first",
    "self-improve",
    "self-improvement",
    "side-pj",
    "side-project",
    "test-only",
    "write-ready",
}
WORK_TASK_GOAL_REQUIRED_TERMS_LIMIT = 10
WORK_TASK_GOAL_MILESTONE_TERMS_LIMIT = 4
WORK_TASK_GOAL_PATH_FRAGMENT_RE = re.compile(r"\b(?:src|tests)/[A-Za-z0-9_./-]+")
WORK_TASK_GOAL_DESCRIPTION_APPENDIX_MARKERS = (
    "\n\nRecently completed git commits.",
    "\n\nCurrent coding focus:",
    "\n\nRecent friction",
    "\n\nActive work sessions",
    "\n\nTasks",
    "\n\nConstraints:",
)


def _work_model_timeout_context_name():
    return "spawn" if sys.platform == "darwin" else "fork"


def _work_model_timeout_guard_available():
    if not hasattr(multiprocessing, "get_context"):
        return False
    try:
        multiprocessing.get_context(_work_model_timeout_context_name())
    except ValueError:
        return False
    return True


def _terminate_work_model_process(process):
    if not process.is_alive():
        process.join(timeout=WORK_MODEL_PROCESS_JOIN_GRACE_SECONDS)
        return
    process.terminate()
    process.join(timeout=WORK_MODEL_PROCESS_JOIN_GRACE_SECONDS)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=WORK_MODEL_PROCESS_JOIN_GRACE_SECONDS)


def _work_model_call_child(send_conn, args, kwargs):
    try:
        result = _agent_call_model_json_with_retries(*args, **kwargs)
        send_conn.send({"status": "ok", "result": result})
    except BaseException as exc:
        send_conn.send(
            {
                "status": "error",
                "error_type": exc.__class__.__name__,
                "message": str(exc),
            }
        )
    finally:
        send_conn.close()


def _call_model_json_without_guard(*args, **kwargs):
    return _agent_call_model_json_with_retries(*args, **kwargs)


def call_model_json_with_retries(*args, **kwargs):
    kwargs.setdefault("retry_delays", ())
    on_text_delta = kwargs.get("on_text_delta")
    timeout = kwargs.get("timeout")
    if timeout is None and len(args) > 5:
        timeout = args[5]
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        timeout_value = None
    if (
        on_text_delta
        or timeout_value is None
        or timeout_value <= 0
        or not _work_model_timeout_guard_available()
    ):
        return _agent_call_model_json_with_retries(*args, **kwargs)

    context = multiprocessing.get_context(_work_model_timeout_context_name())
    recv_conn, send_conn = context.Pipe(duplex=False)
    process = context.Process(
        target=_work_model_call_child,
        args=(send_conn, args, kwargs),
        daemon=True,
    )
    process.start()
    send_conn.close()
    payload = None
    child_crash = None
    try:
        if recv_conn.poll(timeout_value):
            try:
                payload = recv_conn.recv()
            except (EOFError, BrokenPipeError, OSError) as exc:
                child_crash = exc
        else:
            _terminate_work_model_process(process)
            raise ModelBackendError("request timed out")
    finally:
        recv_conn.close()
    process.join(timeout=WORK_MODEL_PROCESS_JOIN_GRACE_SECONDS)
    if child_crash is not None:
        _terminate_work_model_process(process)
        return _call_model_json_without_guard(*args, **kwargs)
    if payload is None:
        raise ModelBackendError("request timed out")
    if payload.get("status") == "ok":
        return payload.get("result")
    error_message = str(payload.get("message") or "work model call failed")
    error_type = str(payload.get("error_type") or "")
    if error_type == "MewError":
        raise MewError(error_message)
    raise ModelBackendError(error_message)


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
        compact = {
            "operation": result.get("operation"),
            "path": result.get("path"),
            "changed": result.get("changed"),
            "dry_run": result.get("dry_run"),
            "written": result.get("written"),
            "rolled_back": result.get("rolled_back"),
            "verification_exit_code": result.get("verification_exit_code"),
            "batch_rollback_reason": result.get("batch_rollback_reason"),
            "rollback_error": result.get("rollback_error"),
            "diff_omitted": result.get("diff_omitted"),
        }
        if not result.get("diff_omitted"):
            compact["diff"] = clip_output(result.get("diff") or "", result_text_limit)
        return compact
    return {"raw": _json_clip(result)}


def _compact_parameters(parameters, *, text_limit=1000):
    compact = {}
    for key, value in dict(parameters or {}).items():
        if isinstance(value, str):
            compact[key] = clip_output(value, text_limit)
        else:
            compact[key] = value
    return compact


WRITE_BODY_PARAMETER_KEYS = {"old", "new", "content", "edits"}


def _write_call_body_should_be_omitted(call):
    if not isinstance(call, dict) or call.get("tool") not in WRITE_WORK_TOOLS:
        return False
    result = call.get("result") if isinstance(call.get("result"), dict) else {}
    if result.get("rolled_back"):
        return True
    return str(call.get("approval_status") or "") == "rejected"


def _compact_resolved_write_parameters(parameters, *, text_limit=1000):
    compact = {}
    omitted = []
    for key, value in dict(parameters or {}).items():
        if key in WRITE_BODY_PARAMETER_KEYS:
            omitted.append(key)
            continue
        if isinstance(value, str):
            compact[key] = clip_output(value, text_limit)
        else:
            compact[key] = value
    if omitted:
        compact["omitted_write_body_fields"] = sorted(omitted)
    return compact


def _omit_resolved_write_result_body(result):
    result = dict(result or {})
    if result.get("diff"):
        result.pop("diff", None)
        result["diff_omitted"] = True
    return result


def _reasoning_value_text(value):
    if isinstance(value, str):
        return value
    return _json_clip(value, 2000)


def _line_window_auto_max_chars(parameters):
    parameters = parameters or {}
    try:
        base = max(
            1,
            min(int(parameters.get("max_chars") or WORK_MODEL_READ_FILE_DEFAULT_MAX_CHARS), 50000),
        )
    except (TypeError, ValueError):
        base = WORK_MODEL_READ_FILE_DEFAULT_MAX_CHARS
    if parameters.get("line_start") is None or parameters.get("line_count") is None:
        return base
    if parameters.get("max_chars") is not None:
        return base
    try:
        line_count = max(1, min(int(parameters.get("line_count")), 1000))
    except (TypeError, ValueError):
        return base
    return max(base, min(50000, line_count * WORK_LINE_WINDOW_ESTIMATED_CHARS_PER_LINE))


def _read_file_context_text_limit_for_call(call, *, compact_prompt):
    base = WORK_COMPACT_READ_FILE_CONTEXT_TEXT_LIMIT if compact_prompt else WORK_READ_FILE_CONTEXT_TEXT_LIMIT
    if compact_prompt or (call or {}).get("tool") != "read_file":
        return base
    parameters = (call or {}).get("parameters") or {}
    if parameters.get("line_start") is None or parameters.get("line_count") is None:
        return base
    return max(base, _line_window_auto_max_chars(parameters))


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
    read_file_text_limit = _read_file_context_text_limit_for_call(call, compact_prompt=compact_prompt)
    list_item_text_limit = (
        WORK_COMPACT_LIST_ITEM_CONTEXT_TEXT_LIMIT if compact_prompt else WORK_LIST_ITEM_CONTEXT_TEXT_LIMIT
    )
    list_item_limit = WORK_COMPACT_LIST_CONTEXT_ITEM_LIMIT if compact_prompt else WORK_LIST_CONTEXT_ITEM_LIMIT
    omit_write_body = _write_call_body_should_be_omitted(call)
    result_for_prompt = call.get("result") or {}
    if omit_write_body:
        result_for_prompt = _omit_resolved_write_result_body(result_for_prompt)
    item = {
        "id": call.get("id"),
        "tool": tool,
        "status": call.get("status"),
        "parameters": (
            _compact_resolved_write_parameters(
                call.get("parameters") or {},
                text_limit=400 if compact_prompt else 1000,
            )
            if omit_write_body
            else _compact_parameters(
                call.get("parameters") or {},
                text_limit=400 if compact_prompt else 1000,
            )
        ),
        "summary": clip_output(call.get("summary") or "", result_text_limit),
        "error": clip_output(call.get("error") or "", result_text_limit),
        "approval_status": call.get("approval_status") or "",
        "rejection_reason": clip_output(call.get("rejection_reason") or "", result_text_limit),
        "result": _compact_tool_result(
            tool,
            result_for_prompt,
            read_file_text_limit=read_file_text_limit,
            result_text_limit=result_text_limit,
            list_item_text_limit=list_item_text_limit,
            list_item_limit=list_item_limit,
        ),
        "started_at": call.get("started_at"),
        "finished_at": call.get("finished_at"),
    }
    if omit_write_body:
        item["resolved_write_body_omitted"] = True
    if compact_prompt:
        item["prompt_context_compacted"] = True
    if call.get("command_evidence_ref"):
        item["command_evidence_ref"] = call.get("command_evidence_ref")
    if call.get("repeat_guard"):
        item["repeat_guard"] = _compact_context_value(
            call.get("repeat_guard"),
            text_limit=list_item_text_limit,
            item_limit=list_item_limit,
        )
    if call.get("broad_read_guard"):
        item["broad_read_guard"] = _compact_context_value(
            call.get("broad_read_guard"),
            text_limit=list_item_text_limit,
            item_limit=list_item_limit,
        )
    return item


def work_model_turn_for_model(turn, *, prompt_context_mode="full"):
    action = turn.get("action") or {}
    model_metrics = turn.get("model_metrics") or {}
    decision_plan = turn.get("decision_plan") or {}
    working_memory = decision_plan.get("working_memory") if isinstance(decision_plan.get("working_memory"), dict) else {}
    compact_prompt = prompt_context_mode != "full"
    text_limit = 1000 if compact_prompt else WORK_RESULT_TEXT_LIMIT
    item = {
        "id": turn.get("id"),
        "status": turn.get("status"),
        "action": {
            key: value
            for key, value in action.items()
            if key
            in (
                "type",
                "tool",
                "path",
                "query",
                "pattern",
                "reason",
                "summary",
                "note",
                "text",
                "question",
                "command",
            )
        },
        "guidance_snapshot": clip_output(work_turn_guidance_snapshot(turn), text_limit),
        "tool_call_id": turn.get("tool_call_id"),
        "tool_call_ids": turn.get("tool_call_ids") or [],
        "summary": clip_output(turn.get("summary") or "", text_limit),
        "reasoning": clip_output(compact_turn_reasoning(turn), text_limit),
        "error": clip_output(turn.get("error") or "", text_limit),
        "started_at": turn.get("started_at"),
        "finished_at": turn.get("finished_at"),
        "target_paths": [
            str(path)
            for path in (working_memory.get("target_paths") or [])
            if isinstance(path, str) and path
        ],
        "write_ready_fast_path": model_metrics.get("write_ready_fast_path"),
        "write_ready_fast_path_reason": str(model_metrics.get("write_ready_fast_path_reason") or ""),
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


def _recent_read_line_window_map(window):
    if not isinstance(window, dict) or window.get("context_truncated"):
        return None
    path = window.get("path")
    line_start = window.get("line_start")
    line_end = window.get("line_end")
    text = window.get("text")
    if not path or text is None or not isinstance(line_start, int) or not isinstance(line_end, int):
        return None
    if line_end < line_start:
        return None
    pieces = str(text).splitlines(keepends=True)
    expected = line_end - line_start + 1
    if len(pieces) != expected:
        return None
    return {line_start + index: piece for index, piece in enumerate(pieces)}


def _merge_recent_read_line_window(
    existing,
    candidate,
    *,
    text_limit,
    existing_text_limit,
    candidate_text_limit,
):
    if not isinstance(existing, dict) or not isinstance(candidate, dict):
        return False
    if existing.get("path") != candidate.get("path"):
        return False
    existing_start = existing.get("line_start")
    existing_end = existing.get("line_end")
    candidate_start = candidate.get("line_start")
    candidate_end = candidate.get("line_end")
    if not all(isinstance(value, int) for value in (existing_start, existing_end, candidate_start, candidate_end)):
        return False
    if candidate_start > existing_end + 1 or existing_start > candidate_end + 1:
        return False
    existing_map = _recent_read_line_window_map(existing)
    candidate_map = _recent_read_line_window_map(candidate)
    if existing_map is None or candidate_map is None:
        return False
    merged_start = min(existing_start, candidate_start)
    merged_end = max(existing_end, candidate_end)
    expected_lines = list(range(merged_start, merged_end + 1))
    merged_map = dict(candidate_map)
    merged_map.update(existing_map)
    if sorted(merged_map) != expected_lines:
        return False
    merged_text = "".join(merged_map[line] for line in expected_lines)
    merge_text_limit = max(text_limit, existing_text_limit, candidate_text_limit)
    existing["line_start"] = merged_start
    existing["line_end"] = merged_end
    existing["text"] = clip_output(merged_text, merge_text_limit)
    existing["visible_chars"] = min(len(merged_text), merge_text_limit)
    existing["source_text_chars"] = len(merged_text)
    existing["context_truncated"] = len(merged_text) > merge_text_limit
    existing["complete_file"] = bool(existing.get("complete_file") or candidate.get("complete_file"))
    return True


def _recent_read_window_text_limit(call, *, default):
    if (call or {}).get("tool") != "read_file":
        return default
    parameters = (call or {}).get("parameters") or {}
    result = (call or {}).get("result") or {}
    if parameters.get("line_start") is None or parameters.get("line_count") is None:
        return default
    if result.get("truncated"):
        return default
    return max(default, _line_window_auto_max_chars(parameters))


def _read_file_call_has_complete_file_result(call):
    if (call or {}).get("tool") != "read_file" or (call or {}).get("status") != "completed":
        return False
    result = (call or {}).get("result") if isinstance((call or {}).get("result"), dict) else {}
    parameters = (call or {}).get("parameters") if isinstance((call or {}).get("parameters"), dict) else {}
    text = result.get("text")
    if not isinstance(text, str) or not text:
        return False
    if any(bool(result.get(key)) for key in ("context_truncated", "source_truncated", "truncated")):
        return False
    line_start = result.get("line_start")
    line_end = result.get("line_end")
    if line_start is not None or line_end is not None:
        try:
            line_start = int(line_start or 0)
            line_end = int(line_end or 0)
        except (TypeError, ValueError):
            return False
        return line_start == 1 and line_end >= line_start and result.get("has_more_lines") is False
    try:
        offset = int(result.get("offset", parameters.get("offset", 0)) or 0)
    except (TypeError, ValueError):
        return False
    return offset == 0 and result.get("next_offset") in (None, "")


def build_recent_read_file_windows(
    calls,
    *,
    limit=WORK_RECENT_READ_FILE_WINDOW_LIMIT,
    text_limit=WORK_RECENT_READ_FILE_WINDOW_TEXT_LIMIT,
):
    windows = []
    window_text_limits = []
    for call in reversed(list(calls or [])):
        if call.get("tool") != "read_file" or call.get("status") != "completed":
            continue
        result = call.get("result") or {}
        text = result.get("text") or ""
        if not text:
            continue
        window_text_limit = _recent_read_window_text_limit(call, default=text_limit)
        clipped = clip_output(text, window_text_limit)
        candidate = {
            "tool_call_id": call.get("id"),
            "path": result.get("path") or (call.get("parameters") or {}).get("path"),
            "line_start": result.get("line_start"),
            "line_end": result.get("line_end"),
            "offset": result.get("offset"),
            "next_line": result.get("next_line"),
            "has_more_lines": result.get("has_more_lines"),
            "text": clipped,
            "visible_chars": min(len(text), window_text_limit),
            "source_text_chars": len(text),
            "context_truncated": len(text) > window_text_limit,
            "complete_file": _read_file_call_has_complete_file_result(call),
        }
        merged = False
        for index, existing in enumerate(windows):
            if _merge_recent_read_line_window(
                existing,
                candidate,
                text_limit=text_limit,
                existing_text_limit=window_text_limits[index],
                candidate_text_limit=window_text_limit,
            ):
                window_text_limits[index] = max(window_text_limits[index], window_text_limit)
                merged = True
                break
        if not merged and len(windows) < limit:
            windows.append(candidate)
            window_text_limits.append(window_text_limit)
    return windows


def _json_size(value):
    try:
        return len(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError):
        return len(str(value))


def _sha1_hex(value):
    return hashlib.sha1(str(value).encode("utf-8")).hexdigest()


def _write_ready_draft_window_signature(window):
    if not isinstance(window, dict):
        return ""
    return "sha1:" + _sha1_hex(
        f"{window.get('path')}|{window.get('line_start')}|{window.get('line_end')}|{window.get('text') or ''}"
    )


def _write_ready_draft_prompt_chars(think_prompt):
    prompt = str(think_prompt or "")
    marker = "\nFocusedContext JSON:\n"
    marker_index = prompt.find(marker)
    if marker_index < 0:
        return len(prompt), 0
    marker_end = marker_index + len(marker)
    return marker_end, len(prompt) - marker_end


def _write_ready_draft_runtime_mode(stream_model):
    if stream_model:
        return "streaming"
    return "guarded" if _work_model_timeout_guard_available() else "fallback_unguarded"


def _write_ready_draft_attempts(session, write_ready_fast_path_active):
    turns = list((session or {}).get("model_turns") or [])
    attempts = 0
    for turn in turns:
        metrics = turn.get("model_metrics") or {}
        if bool(metrics.get("write_ready_fast_path")):
            attempts += 1
    if write_ready_fast_path_active:
        attempts += 1
    return attempts


def _write_ready_tiny_draft_timeout(timeout):
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        timeout_value = WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS
    if timeout_value <= 0:
        timeout_value = WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS
    return min(timeout_value, WORK_WRITE_READY_TINY_DRAFT_MODEL_TIMEOUT_SECONDS)


def _tiny_write_ready_draft_reasoning_metrics(reasoning_effort="", reasoning_effort_source="", env=None):
    env = os.environ if env is None else env
    inherited_reasoning_effort = str(reasoning_effort or "")
    inherited_reasoning_effort_source = str(reasoning_effort_source or "auto")
    dedicated_override = normalize_reasoning_effort(
        env.get(WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT_ENV)
    )
    if dedicated_override:
        effective_reasoning_effort = dedicated_override
        effective_reasoning_effort_source = "tiny_draft_env_override"
    else:
        effective_reasoning_effort = WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT
        effective_reasoning_effort_source = "tiny_draft_auto_override"
    return {
        "tiny_write_ready_draft_reasoning_effort": effective_reasoning_effort,
        "tiny_write_ready_draft_inherited_reasoning_effort": inherited_reasoning_effort,
        "tiny_write_ready_draft_reasoning_effort_source": effective_reasoning_effort_source,
        "tiny_write_ready_draft_inherited_reasoning_effort_source": inherited_reasoning_effort_source,
    }


def _work_model_error_looks_like_timeout(exc):
    text = str(exc or "").lower()
    return "timed out" in text or "timeout" in text


def _work_model_error_looks_like_refusal(exc):
    name = exc.__class__.__name__.lower()
    text = str(exc or "").lower()
    return "refusal" in name or "model returned refusal" in text


def _stable_write_ready_tiny_draft_blocker_reason(blocker):
    code = str((blocker or {}).get("code") or "").strip() or "unspecified_blocker"
    return f"write-ready tiny draft blocker: {code}"


def _work_loop_tiny_write_ready_draft_blocker_payload(blocker):
    blocker = blocker if isinstance(blocker, dict) else {}
    todo_id = str(blocker.get("todo_id") or "").strip()
    payload = {
        "code": str(blocker.get("code") or "").strip(),
        "detail": str(blocker.get("detail") or "").strip(),
    }
    if todo_id:
        payload["todo_id"] = todo_id
    path = str(blocker.get("path") or "").strip()
    if path:
        payload["path"] = path
    try:
        line_start = int(blocker.get("line_start"))
        if line_start > 0:
            payload["line_start"] = line_start
    except (TypeError, ValueError):
        pass
    try:
        line_end = int(blocker.get("line_end"))
        if line_end > 0:
            payload["line_end"] = line_end
    except (TypeError, ValueError):
        pass
    return payload


def _work_loop_write_ready_timeout_blocker_plan(*, todo_id, exc):
    error_detail = clip_output(str(exc), 500)
    detail = (
        "write-ready draft model timed out after complete cached source/test windows were "
        "available and before a patch proposal, blocker, tool action, or compiler replay "
        "artifact was produced"
    )
    if error_detail:
        detail = f"{detail}: {error_detail}"
    blocker_payload = _work_loop_tiny_write_ready_draft_blocker_payload(
        {
            "code": WORK_WRITE_READY_TIMEOUT_BLOCKER_CODE,
            "detail": detail,
            "todo_id": todo_id,
        }
    )
    blocker_payload["calibration_counted"] = False
    blocker_payload["calibration_exclusion_reason"] = (
        "same-session patch_draft compiler replay artifact was not written"
    )
    action = {
        "type": "wait",
        "reason": _stable_write_ready_tiny_draft_blocker_reason(blocker_payload),
    }
    action_plan = {
        "summary": detail,
        "action": action,
        "act_mode": "tiny_write_ready_draft",
        "blocker": blocker_payload,
    }
    if todo_id:
        action_plan["todo_id"] = todo_id
    decision_plan = {
        "summary": detail,
        "kind": "patch_blocker",
        "code": blocker_payload["code"],
        "detail": detail,
        "blocker": blocker_payload,
    }
    if todo_id:
        decision_plan["todo_id"] = todo_id
    return decision_plan, action_plan, action


def _work_loop_active_todo_id_from_context(context):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    resume = work_session.get("resume") if isinstance(work_session, dict) else {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume, dict) else {}
    if not isinstance(active_work_todo, dict):
        return ""
    return str(active_work_todo.get("id") or "").strip()


def _work_loop_model_metrics_have_patch_replay_or_artifact(model_metrics):
    metrics = model_metrics if isinstance(model_metrics, dict) else {}
    if str(metrics.get("patch_draft_compiler_replay_path") or "").strip():
        return True
    artifact_kinds = {
        str(metrics.get("patch_draft_compiler_artifact_kind") or "").strip(),
        str(metrics.get("tiny_write_ready_draft_compiler_artifact_kind") or "").strip(),
    }
    return bool(artifact_kinds & {"patch_draft", "patch_blocker"})


def _work_deliberation_reviewer_commanded(guidance):
    lowered = str(guidance or "").casefold()
    return any(
        marker in lowered
        for marker in (
            "deliberation",
            "deliberate",
            "high-effort",
            "high effort",
            "escalate",
            "deep reasoning",
        )
    )


def _work_deliberation_task_shape(task, guidance=""):
    text = "\n".join(
        str(part or "")
        for part in (
            (task or {}).get("title") if isinstance(task, dict) else "",
            (task or {}).get("description") if isinstance(task, dict) else "",
            guidance,
        )
        if str(part or "").strip()
    ).casefold()
    if any(marker in text for marker in ("cross-file", "cross file", "multi-file", "multi file")):
        return "cross_file"
    if any(marker in text for marker in ("design", "architecture", "policy", "roadmap")):
        return "design"
    if any(marker in text for marker in ("abstract", "conceptual", "strategy")):
        return "abstract"
    return ""


def _work_deliberation_attempts_for_todo(resume, todo_id, blocker_code):
    attempts = (resume or {}).get("deliberation_attempts")
    if not isinstance(attempts, list):
        return []
    todo_id = str(todo_id or "").strip()
    blocker_code = str(blocker_code or "").strip()
    return [
        item
        for item in attempts
        if isinstance(item, dict)
        and str(item.get("todo_id") or "").strip() == todo_id
        and str(item.get("blocker_code") or "").strip() == blocker_code
    ]


def _work_deliberation_trace_patch(decision, *, latest_result=None, fallback_event=None):
    attempt = build_deliberation_attempt_record(decision)
    cost_events = [
        dict(event)
        for event in ((decision or {}).get("cost_events") or [])
        if isinstance(event, dict)
    ]
    if isinstance(fallback_event, dict) and fallback_event:
        cost_events.append(dict(fallback_event))
    if latest_result is None:
        latest_result = {
            "lane_attempt_id": attempt.get("lane_attempt_id") or "",
            "status": "reserved" if attempt.get("allowed") else "fallback",
            "reason": attempt.get("reason") or "",
            "fallback_lane": attempt.get("fallback_lane") or "tiny",
        }
    return {
        "attempt": attempt,
        "cost_events": cost_events,
        "latest_result": dict(latest_result or {}),
    }


def _work_deliberation_trace_metrics_from_patch(trace_patch):
    attempt = (trace_patch or {}).get("attempt") if isinstance(trace_patch, dict) else {}
    latest = (trace_patch or {}).get("latest_result") if isinstance(trace_patch, dict) else {}
    return {
        "attempted": bool((attempt or {}).get("allowed")),
        "lane_attempt_id": (attempt or {}).get("lane_attempt_id") or "",
        "todo_id": (attempt or {}).get("todo_id") or "",
        "blocker_code": (attempt or {}).get("blocker_code") or "",
        "status": (latest or {}).get("status") or "",
        "reason": (latest or {}).get("reason") or (attempt or {}).get("reason") or "",
        "fallback_lane": (latest or {}).get("fallback_lane") or (attempt or {}).get("fallback_lane") or "tiny",
        "requested_model": (attempt or {}).get("requested_model") or "",
        "effective_model": (attempt or {}).get("effective_model") or "",
        "effective_effort": (attempt or {}).get("effective_effort") or "",
        "timeout_seconds": (attempt or {}).get("timeout_seconds") or 0,
    }


def _work_plan_with_session_trace_patch(result, trace_patch):
    if not trace_patch:
        return result
    planned = dict(result or {})
    planned["session_trace_patch"] = trace_patch
    return planned


def _work_deliberation_preflight_decision(
    context,
    *,
    model_backend,
    model,
    timeout,
    guidance="",
    deliberation_requested=False,
    auto_deliberation=True,
    timeout_ceiling=False,
):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    resume = (work_session or {}).get("resume") if isinstance(work_session, dict) else {}
    active_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    if not active_todo:
        return {}
    blocker = active_todo.get("blocker") if isinstance(active_todo.get("blocker"), dict) else {}
    blocker_code = str(blocker.get("code") or "").strip()
    if not blocker_code:
        return {}
    todo_id = str(active_todo.get("id") or "").strip()
    previous_attempts = _work_deliberation_attempts_for_todo(resume, todo_id, blocker_code)
    if previous_attempts:
        return {}
    attempts = active_todo.get("attempts") if isinstance(active_todo.get("attempts"), dict) else {}
    try:
        draft_attempts = int(attempts.get("draft") or 0)
    except (TypeError, ValueError):
        draft_attempts = 0
    if timeout_ceiling:
        deliberation_timeout = max(float(timeout or 0), 0.0)
    else:
        deliberation_timeout = max(float(timeout or 0), WORK_DELIBERATION_MODEL_TIMEOUT_SECONDS)
    return evaluate_deliberation_request(
        todo=active_todo,
        blocker_code=blocker_code,
        binding={
            "backend": model_backend,
            "model": model,
            "requested_effort": WORK_DELIBERATION_REASONING_EFFORT,
            "timeout_seconds": deliberation_timeout,
            "schema_contract": DELIBERATION_RESULT_SCHEMA_CONTRACT,
        },
        budget={
            "max_attempts_per_todo": WORK_DELIBERATION_MAX_ATTEMPTS_PER_TODO,
            "attempts_used": len(previous_attempts),
        },
        reviewer_commanded=bool(deliberation_requested) or _work_deliberation_reviewer_commanded(guidance),
        auto_deliberation_enabled=bool(auto_deliberation),
        task_shape=_work_deliberation_task_shape((context or {}).get("task") or {}, guidance=guidance),
        repeated=draft_attempts > 1,
        refusal_classified=blocker_code == "model_returned_refusal" and bool(blocker.get("detail")),
        created_at=(context or {}).get("current_time") or "",
    )


def build_work_deliberation_prompt(context, decision):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    resume = (work_session or {}).get("resume") if isinstance(work_session, dict) else {}
    active_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    blocker = active_todo.get("blocker") if isinstance(active_todo.get("blocker"), dict) else {}
    focused_context = {
        "task": (context or {}).get("task") or {},
        "active_work_todo": {
            "id": active_todo.get("id") or "",
            "lane": active_todo.get("lane") or "tiny",
            "status": active_todo.get("status") or "",
            "source": active_todo.get("source") or {},
            "attempts": active_todo.get("attempts") or {},
            "blocker": blocker,
        },
        "deliberation_request": {
            "lane_attempt_id": (decision or {}).get("lane_attempt_id") or "",
            "reason": (decision or {}).get("reason") or "",
            "budget_snapshot": (decision or {}).get("budget_snapshot") or {},
            "schema_contract": DELIBERATION_RESULT_SCHEMA_CONTRACT,
        },
        "recent_decisions": list((resume or {}).get("recent_decisions") or [])[-3:],
        "working_memory": (resume or {}).get("working_memory") or {},
        "failed_patch_repair": (resume or {}).get("failed_patch_repair") or {},
        "broad_rollback_slice_repair": (resume or {}).get("broad_rollback_slice_repair") or {},
        "retry_context": (resume or {}).get("retry_context") or {},
    }
    return (
        "You are the read-only deliberation lane for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "You do not write files, execute tools, approve changes, or replace the tiny implementation lane.\n"
        "Analyze the active blocker and produce a compact strategy that a reviewer can inspect.\n"
        "Do not include hidden chain-of-thought or raw transcript. Use a distilled reasoning_summary only.\n"
        "Schema:\n"
        "{\n"
        '  "kind": "deliberation_result",\n'
        '  "schema_version": 1,\n'
        f'  "todo_id": "{(decision or {}).get("todo_id") or ""}",\n'
        '  "lane": "deliberation",\n'
        f'  "blocker_code": "{(decision or {}).get("blocker_code") or ""}",\n'
        '  "decision": "propose_patch_strategy|decline_escalation|needs_state_refresh",\n'
        '  "situation": "short task and blocker summary",\n'
        '  "reasoning_summary": "distilled reasoning, no raw hidden transcript",\n'
        '  "recommended_next": "retry_tiny|refresh_state|ask_reviewer|finish_blocked",\n'
        '  "expected_trace_candidate": true,\n'
        '  "confidence": "low|medium|high"\n'
        "}\n\n"
        f"FocusedContext JSON:\n{json.dumps(focused_context, ensure_ascii=False, indent=2)}"
    )


def _attempt_work_deliberation_lane(
    *,
    context,
    model_auth,
    model,
    base_url,
    model_backend,
    timeout,
    guidance="",
    deliberation_requested=False,
    auto_deliberation=True,
    timeout_ceiling=False,
    progress=None,
    current_time="",
):
    decision = _work_deliberation_preflight_decision(
        context,
        model_backend=model_backend,
        model=model,
        timeout=timeout,
        guidance=guidance,
        deliberation_requested=deliberation_requested,
        auto_deliberation=auto_deliberation,
        timeout_ceiling=timeout_ceiling,
    )
    if not decision:
        return {}

    trace_patch = _work_deliberation_trace_patch(decision)
    result = {
        "status": "preflight_blocked",
        "decision": decision,
        "trace_patch": trace_patch,
        "metrics": _work_deliberation_trace_metrics_from_patch(trace_patch),
    }
    if not decision.get("allowed"):
        return result

    prompt = build_work_deliberation_prompt(context, decision)
    started = time.monotonic()
    try:
        with codex_reasoning_effort_scope(
            ((decision.get("binding") or {}).get("effective_effort") or WORK_DELIBERATION_REASONING_EFFORT)
        ):
            payload = call_model_json_with_retries(
                model_backend,
                model_auth,
                prompt,
                model,
                base_url,
                (decision.get("binding") or {}).get("timeout_seconds") or timeout,
                log_prefix=(
                    f"{current_time}: work_deliberation {model_backend} "
                    f"session={((context or {}).get('work_session') or {}).get('id')}"
                ),
            )
    except Exception as exc:
        fallback_reason = "timeout" if _work_model_error_looks_like_timeout(exc) else "model_error"
        fallback_event = build_deliberation_fallback_event(
            reason=fallback_reason,
            todo_id=decision.get("todo_id") or "",
            blocker_code=decision.get("blocker_code") or "",
            lane_attempt_id=decision.get("lane_attempt_id") or "",
            created_at=current_time,
        )
        trace_patch = _work_deliberation_trace_patch(
            decision,
            fallback_event=fallback_event,
            latest_result={
                "lane_attempt_id": decision.get("lane_attempt_id") or "",
                "status": "fallback",
                "reason": fallback_reason,
                "fallback_lane": "tiny",
            },
        )
        metrics = _work_deliberation_trace_metrics_from_patch(trace_patch)
        metrics.update(
            {
                "prompt_chars": len(prompt),
                "elapsed_seconds": _round_seconds(time.monotonic() - started),
                "error": clip_output(str(exc), 500),
            }
        )
        if progress:
            progress(
                f"session #{((context or {}).get('work_session') or {}).get('id')}: "
                f"DELIBERATION fallback reason={fallback_reason}"
            )
        return {
            "status": "fallback",
            "decision": decision,
            "trace_patch": trace_patch,
            "metrics": metrics,
        }

    validation = validate_deliberation_result(
        payload,
        todo_id=decision.get("todo_id") or "",
        blocker_code=decision.get("blocker_code") or "",
    )
    if not validation.get("ok"):
        fallback_reason = str(validation.get("reason") or "validation_failed")
        fallback_event = build_deliberation_fallback_event(
            reason=fallback_reason,
            todo_id=decision.get("todo_id") or "",
            blocker_code=decision.get("blocker_code") or "",
            lane_attempt_id=decision.get("lane_attempt_id") or "",
            created_at=current_time,
        )
        trace_patch = _work_deliberation_trace_patch(
            decision,
            fallback_event=fallback_event,
            latest_result={
                "lane_attempt_id": decision.get("lane_attempt_id") or "",
                "status": "fallback",
                "reason": fallback_reason,
                "fallback_lane": "tiny",
                "invalid_fields": validation.get("invalid_fields") or [],
            },
        )
        metrics = _work_deliberation_trace_metrics_from_patch(trace_patch)
        metrics.update(
            {
                "prompt_chars": len(prompt),
                "elapsed_seconds": _round_seconds(time.monotonic() - started),
                "invalid_fields": validation.get("invalid_fields") or [],
            }
        )
        if progress:
            progress(
                f"session #{((context or {}).get('work_session') or {}).get('id')}: "
                f"DELIBERATION fallback reason={fallback_reason}"
            )
        return {
            "status": "fallback",
            "decision": decision,
            "trace_patch": trace_patch,
            "metrics": metrics,
            "validation": validation,
        }

    latest_result = {
        "lane_attempt_id": decision.get("lane_attempt_id") or "",
        "status": "result_ready",
        "reason": decision.get("reason") or "",
        "fallback_lane": "tiny",
        "result": validation.get("result") or {},
    }
    trace_patch = _work_deliberation_trace_patch(decision, latest_result=latest_result)
    metrics = _work_deliberation_trace_metrics_from_patch(trace_patch)
    metrics.update(
        {
            "prompt_chars": len(prompt),
            "elapsed_seconds": _round_seconds(time.monotonic() - started),
            "result_decision": (validation.get("result") or {}).get("decision") or "",
            "recommended_next": (validation.get("result") or {}).get("recommended_next") or "",
            "expected_trace_candidate": bool((validation.get("result") or {}).get("expected_trace_candidate")),
        }
    )
    action = {
        "type": "wait",
        "reason": "deliberation result ready for reviewer approval before internalization",
        "summary": (validation.get("result") or {}).get("reasoning_summary") or "",
    }
    if progress:
        progress(f"session #{((context or {}).get('work_session') or {}).get('id')}: DELIBERATION ok")
    return {
        "status": "result_ready",
        "decision": decision,
        "trace_patch": trace_patch,
        "metrics": metrics,
        "validation": validation,
        "action": action,
        "decision_plan": {
            "summary": (validation.get("result") or {}).get("situation") or "deliberation result ready",
            "deliberation_result": validation.get("result") or {},
        },
        "action_plan": {
            "summary": (validation.get("result") or {}).get("reasoning_summary") or "deliberation result ready",
            "action": action,
            "act_mode": "deliberation",
        },
    }


def _empty_patch_draft_compiler_observation():
    return {
        "patch_draft_compiler_ran": False,
        "patch_draft_compiler_artifact_kind": "",
        "patch_draft_compiler_replay_path": "",
        "patch_draft_compiler_error": "",
    }


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
                "memory_kind",
                "key",
                "name",
                "description",
                "created_at",
                "storage",
                "path",
                "score",
                "reason",
                "matched_terms",
                "situation",
                "verdict",
                "abstraction_level",
                "source_lane",
                "source_lane_attempt_id",
                "source_blocker_code",
                "source_bundle_ref",
                "same_shape_key",
                "reviewer_decision_ref",
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


def compact_resume_notes_for_prompt(notes, *, item_limit=3, text_limit=240):
    notes = notes if isinstance(notes, list) else []
    compacted = []
    for note in notes[-item_limit:]:
        if isinstance(note, dict):
            compact = {}
            if note.get("created_at"):
                compact["created_at"] = note.get("created_at")
            if note.get("source"):
                compact["source"] = note.get("source")
            compact["text"] = clip_output(str(note.get("text") or ""), text_limit)
        else:
            compact = {"text": clip_output(str(note or ""), text_limit)}
        compacted.append(compact)
    return compacted


def _decision_has_structural_context(decision):
    if not isinstance(decision, dict):
        return False
    return bool(
        decision.get("plan_items")
        or decision.get("target_paths")
        or decision.get("open_questions")
        or decision.get("last_verified_state")
    )


def compact_recent_decisions_for_prompt(decisions, *, item_limit=4, text_limit=240, guidance_limit=160):
    decisions = decisions if isinstance(decisions, list) else []
    compacted = []
    for decision in decisions[-item_limit:]:
        if not isinstance(decision, dict):
            compacted.append({"summary": clip_output(str(decision or ""), text_limit)})
            continue
        compact = {
            "model_turn_id": decision.get("model_turn_id"),
            "status": decision.get("status"),
            "action": decision.get("action"),
            "summary": clip_output(str(decision.get("summary") or ""), text_limit),
            "tool_call_id": decision.get("tool_call_id"),
        }
        if decision.get("plan_items"):
            compact["plan_items"] = _compact_context_value(
                decision.get("plan_items"),
                text_limit=guidance_limit,
                item_limit=3,
            )
        if decision.get("target_paths"):
            compact["target_paths"] = _compact_context_value(
                decision.get("target_paths"),
                text_limit=guidance_limit,
                item_limit=3,
            )
        if decision.get("open_questions"):
            compact["open_questions"] = _compact_context_value(
                decision.get("open_questions"),
                text_limit=guidance_limit,
                item_limit=3,
            )
        if decision.get("last_verified_state"):
            compact["last_verified_state"] = clip_output(
                str(decision.get("last_verified_state") or ""),
                guidance_limit,
            )
        guidance = str(decision.get("guidance_snapshot") or decision.get("guidance") or "").strip()
        if guidance:
            if _decision_has_structural_context(decision) or decision.get("status") == "completed":
                compact["guidance_snapshot"] = clip_output(guidance, guidance_limit)
            else:
                compact["guidance_omitted"] = True
        compacted.append(compact)
    return compacted


def compact_recovery_plan_for_prompt(recovery_plan, *, item_limit=3, text_limit=200):
    recovery_plan = recovery_plan if isinstance(recovery_plan, dict) else {}
    compact_items = []
    for item in (recovery_plan.get("items") or [])[:item_limit]:
        if not isinstance(item, dict):
            compact_items.append({"summary": clip_output(str(item or ""), text_limit)})
            continue
        compact = {
            "kind": item.get("kind"),
            "action": item.get("action"),
            "effect_classification": item.get("effect_classification"),
            "reason": clip_output(str(item.get("reason") or ""), text_limit),
            "safety": item.get("safety"),
            "source_summary": clip_output(str(item.get("source_summary") or ""), text_limit),
        }
        if compact_items and compact == {
            key: compact_items[-1].get(key)
            for key in ("kind", "action", "effect_classification", "reason", "safety", "source_summary")
        }:
            compact_items[-1]["repeat_count"] = compact_items[-1].get("repeat_count", 1) + 1
            continue
        compact_items.append(compact)
    compact = {}
    if recovery_plan.get("next_action"):
        compact["next_action"] = clip_output(str(recovery_plan.get("next_action") or ""), text_limit)
    if compact_items:
        compact["items"] = compact_items
    return compact


def compact_resume_for_prompt(resume, *, mode="compact_memory"):
    compacted = dict(resume or {})
    if mode == "compact_recovery":
        resume_text_limit = WORK_RECOVERY_RESUME_TEXT_LIMIT
        resume_item_limit = WORK_RECOVERY_RESUME_ITEM_LIMIT
        decision_item_limit = WORK_RECOVERY_DECISION_ITEM_LIMIT
        decision_text_limit = WORK_RECOVERY_DECISION_TEXT_LIMIT
        decision_guidance_limit = WORK_RECOVERY_DECISION_GUIDANCE_LIMIT
        active_memory_item_limit = max(1, WORK_COMPACT_ACTIVE_MEMORY_ITEM_LIMIT - 1)
    else:
        resume_text_limit = WORK_COMPACT_RESUME_TEXT_LIMIT
        resume_item_limit = WORK_COMPACT_RESUME_ITEM_LIMIT
        decision_item_limit = 4
        decision_text_limit = 240
        decision_guidance_limit = 160
        active_memory_item_limit = WORK_COMPACT_ACTIVE_MEMORY_ITEM_LIMIT
    compacted["active_memory"] = compact_active_memory_for_prompt(
        compacted.get("active_memory"),
        mode=mode,
        item_limit=active_memory_item_limit,
    )
    compacted["notes"] = compact_resume_notes_for_prompt(compacted.get("notes"))
    compacted["recent_decisions"] = compact_recent_decisions_for_prompt(
        compacted.get("recent_decisions"),
        item_limit=decision_item_limit,
        text_limit=decision_text_limit,
        guidance_limit=decision_guidance_limit,
    )
    compacted["recovery_plan"] = compact_recovery_plan_for_prompt(compacted.get("recovery_plan"))
    for key in (
        "goal",
        "working_memory",
        "compressed_prior_think",
        "same_surface_audit",
        "continuity",
        "effort",
        "low_yield_observations",
        "search_anchor_observations",
        "recent_read_images_observations",
        "failures",
        "unresolved_failure",
        "recurring_failures",
        "repair_anchor_observations",
        "suggested_safe_reobserve",
        "retry_context",
        "world_state",
        "files_touched",
        "queued_followups",
        "pending_steer",
        "next_action",
    ):
        if key in compacted:
            compacted[key] = _compact_context_value(
                compacted.get(key),
                text_limit=resume_text_limit,
                item_limit=resume_item_limit,
            )
    compacted["prompt_context"] = {
        "mode": mode,
        "active_memory_body_injection": "omitted",
        "resume_text_limit": resume_text_limit,
        "resume_item_limit": resume_item_limit,
    }
    return compacted


def work_prompt_context_mode(reasoning_policy, *, compact_live=False):
    if compact_live:
        return "compact_memory"
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
    def structural_refresh_history_call(call):
        parameters = (call or {}).get("parameters")
        parameters = parameters if isinstance(parameters, dict) else {}
        return {
            "id": (call or {}).get("id"),
            "tool": (call or {}).get("tool"),
            "status": (call or {}).get("status"),
            "parameters": {
                "path": parameters.get("path"),
                "line_start": parameters.get("line_start"),
                "line_count": parameters.get("line_count"),
                "reason": parameters.get("reason"),
            },
        }

    prompt_compacted = prompt_context_mode != "full"
    prompt_model_turns = compact_model_turns_for_prompt(model_turns)
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
            for turn in prompt_model_turns[-recent_turn_count:]
        ],
    }
    work_context["explicit_refresh_search_tool_calls"] = [
        work_tool_call_for_model(call, prompt_context_mode=prompt_context_mode)
        for call in tool_calls
        if (call or {}).get("tool") == "search_text"
        and str((call or {}).get("status") or "") == "completed"
        and str(((call or {}).get("parameters") or {}).get("reason") or "")
        == "locate explicitly requested write-ready cached window"
    ][-10:]
    work_context["structural_refresh_read_tool_calls"] = [
        structural_refresh_history_call(call)
        for call in tool_calls
        if (call or {}).get("tool") == "read_file"
        and str((call or {}).get("status") or "") == "completed"
        and str(((call or {}).get("parameters") or {}).get("reason") or "")
        == "refresh structurally incomplete write-ready cached window"
    ][-10:]
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
            "total_model_turns": len(prompt_model_turns),
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
    if prompt_context_mode == "compact_recovery":
        candidates = WORK_RECOVERY_CONTEXT_WINDOW_CANDIDATES
    else:
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


def _latest_model_turn_timed_out(model_turns):
    for turn in reversed(list(model_turns or [])):
        if str((turn or {}).get("status") or "") != "failed":
            continue
        error_text = " ".join(
            str((turn or {}).get(field) or "")
            for field in ("error", "summary", "finished_note")
        ).casefold()
        if "request timed out" in error_text:
            return True
    return False


def _effective_prompt_context_mode(prompt_context_mode, resume, model_turns):
    if prompt_context_mode == "full":
        return "full"
    pending_steer = str(((resume or {}).get("pending_steer") or {}).get("text") or "").strip()
    if pending_steer and _latest_model_turn_timed_out(model_turns):
        return "compact_recovery"
    return prompt_context_mode


def _prompt_context_mode_for_wall_clock(prompt_context_mode, *, timeout_ceiling=False):
    if timeout_ceiling and prompt_context_mode == "full":
        return "compact_recovery"
    return prompt_context_mode


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
    run_step_index=None,
    run_max_steps=None,
):
    tool_calls = list(session.get("tool_calls") or [])
    model_turns = list(session.get("model_turns") or [])
    work_cwd = work_session_default_cwd(session, task=task) or "."
    resume = build_work_session_resume(session, task=task, limit=8, state=state, current_time=current_time)
    prompt_context_mode = _effective_prompt_context_mode(prompt_context_mode, resume, model_turns)
    world_state = build_work_world_state(
        resume,
        allowed_read_roots or [],
        file_limit=DEFAULT_WORLD_STATE_FILE_LIMIT,
        cwd=work_cwd,
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
    current_run = build_current_work_run_budget(run_step_index, run_max_steps)
    if current_run:
        work_context["current_run"] = current_run
    task_description = task.get("description") if task else session.get("goal")
    task_notes = (task or {}).get("notes") or ""
    acceptance_constraints = extract_acceptance_constraints(task_description or "")
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
            "cwd": work_cwd,
            "acceptance_constraints": acceptance_constraints,
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


def build_current_work_run_budget(run_step_index=None, run_max_steps=None):
    try:
        step_index = int(run_step_index)
        max_steps = int(run_max_steps)
    except (TypeError, ValueError):
        return {}
    if step_index <= 0 or max_steps <= 0:
        return {}
    return {
        "step_index": step_index,
        "max_steps": max_steps,
        "remaining_steps_including_current": max(0, max_steps - step_index + 1),
        "remaining_steps_after_current": max(0, max_steps - step_index),
        "can_continue_after_current": step_index < max_steps,
        "budget_source": "current_cli_invocation",
        "note": (
            "This is the current command's step budget. work_session.effort is "
            "historical session pressure, not a hard stop by itself."
        ),
    }


def _write_ready_fast_path_steer_text(context, resume):
    steer_text = str(((resume or {}).get("pending_steer") or {}).get("text") or "")
    if not steer_text:
        steer_text = str((context or {}).get("guidance") or "")
    return steer_text


def _write_ready_fast_path_steer_requests_write(steer_text):
    if not steer_text:
        return True
    steer_lower = str(steer_text or "").lower()
    return any(
        needle in steer_lower
        for needle in ("dry-run", "dry run", "paired dry-run", "paired dry run", "draft")
    )


def _write_ready_cached_window_refresh_plan_item(plan_item):
    lowered = str(plan_item or "").strip().casefold()
    if not lowered:
        return False
    if not re.search(r"\brefresh(?:ing)?\b", lowered):
        return False
    return (
        "cached window" in lowered
        or "cached windows" in lowered
        or "exact window" in lowered
        or "exact windows" in lowered
    )


def _write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo):
    if not isinstance(active_work_todo, dict):
        return False
    blocker = active_work_todo.get("blocker") if isinstance(active_work_todo.get("blocker"), dict) else {}
    if not blocker:
        return False
    code = str(blocker.get("code") or "").strip()
    recovery_action = str(blocker.get("recovery_action") or "").strip()
    if code in WORK_WRITE_READY_REFRESH_RECOVERABLE_BLOCKER_CODES:
        return True
    return recovery_action == PATCH_BLOCKER_RECOVERY_ACTIONS.get("missing_exact_cached_window_texts")


def _write_ready_active_todo_is_refresh_recovery(active_work_todo, first_observation=None):
    if not isinstance(active_work_todo, dict):
        return False
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    candidates = [
        str(source.get("plan_item") or "").strip(),
        str((first_observation or {}).get("plan_item") or "").strip(),
    ]
    return any(_write_ready_cached_window_refresh_plan_item(candidate) for candidate in candidates)


def _write_ready_complete_windows_cover_active_todo_source(active_work_todo, complete_windows):
    source = active_work_todo.get("source") if isinstance((active_work_todo or {}).get("source"), dict) else {}
    source_paths = _write_ready_paired_target_paths(source.get("target_paths") or [])
    window_paths = _write_ready_paired_target_paths(
        [
            str(item.get("path") or "").strip()
            for item in complete_windows or []
            if isinstance(item, dict) and str(item.get("path") or "").strip()
        ]
    )
    if not source_paths or not window_paths:
        return False
    return all(
        any(_work_paths_match(source_path, window_path) for window_path in window_paths)
        for source_path in source_paths
    )


def _write_ready_refresh_blocker_cleared_by_complete_windows(active_work_todo, complete_windows):
    return (
        _write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo)
        and _write_ready_complete_windows_cover_active_todo_source(active_work_todo, complete_windows)
    )


def _write_ready_refreshed_draft_plan_item(resume, active_work_todo, first_observation=None):
    source = active_work_todo.get("source") if isinstance((active_work_todo or {}).get("source"), dict) else {}
    working_memory = (resume or {}).get("working_memory") if isinstance((resume or {}).get("working_memory"), dict) else {}
    candidates = [
        str(source.get("plan_item") or "").strip(),
        str((first_observation or {}).get("plan_item") or "").strip(),
    ]
    candidates.extend(str(item or "").strip() for item in working_memory.get("plan_items") or [])
    for candidate in candidates:
        if not candidate or _write_ready_cached_window_refresh_plan_item(candidate):
            continue
        lowered = candidate.casefold()
        if _write_ready_fast_path_steer_requests_write(candidate) or any(
            marker in lowered
            for marker in ("no-change", "no change", "no_material_change", "no material")
        ):
            return candidate
    for candidate in candidates:
        if candidate and not _write_ready_cached_window_refresh_plan_item(candidate):
            return candidate
    return (
        "Draft one paired dry-run edit from the refreshed exact cached windows, "
        "or report no_material_change if no concrete change remains."
    )


def _write_ready_locator_only_plan_item(plan_item):
    text = str(plan_item or "").strip()
    if not text:
        return False
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in (
            "draft",
            "implement",
            "fix",
            "repair",
            "update",
            "write",
            "emit",
            "patch",
            "change",
            "modify",
            "apply",
            "add ",
        )
    ):
        return False
    return bool(
        re.search(r"\b(locate|find|read|inspect|search|open|identify)\b", lowered)
        or "insertion point" in lowered
        or "source anchor" in lowered
    )


def _write_ready_task_goal_draft_plan_item(context, steer_text=""):
    task = (context or {}).get("task") if isinstance((context or {}).get("task"), dict) else {}
    title = str(task.get("title") or "").strip()
    description = str(task.get("description") or "").strip()
    guidance = clip_output(str(steer_text or "").strip(), 500)
    pieces = []
    if title or description:
        goal_parts = []
        if title:
            goal_parts.append(title)
        if description:
            goal_parts.append(description)
        pieces.append("Task goal: " + " - ".join(goal_parts))
    if guidance:
        pieces.append("Current guidance: " + guidance)
    pieces.append(
        "Complete cached source/test windows are available; draft only the patch that implements this task goal."
    )
    return "\n".join(pieces)


def _write_ready_locator_replacement_requests_write(context, steer_text=""):
    text_parts = [str(steer_text or "").strip()]
    task = (context or {}).get("task") if isinstance((context or {}).get("task"), dict) else {}
    text_parts.extend(
        str(task.get(key) or "").strip()
        for key in ("title", "description")
    )
    combined = "\n".join(part for part in text_parts if part).casefold()
    if not combined:
        return True
    if any(
        marker in combined
        for marker in (
            "do not change",
            "don't change",
            "no-change",
            "no change",
            "no_material_change",
            "inspect only",
            "read-only",
            "read only",
        )
    ):
        return False
    return _write_ready_fast_path_steer_requests_write(steer_text) or any(
        re.search(pattern, combined)
        for pattern in (
            r"\bimplement\b",
            r"\bimplementation\b",
            r"\bedit\b",
            r"\badd\b",
            r"\bfix\b",
            r"\bpatch\b",
            r"\bupdate\b",
            r"\bchange\b",
            r"\bwrite\b",
        )
    )


def _write_ready_completed_read_frontier_plan_item(plan_item, target_paths):
    text = str(plan_item or "").strip()
    lowered = text.casefold()
    if not lowered:
        return False
    first_word = re.sub(r"[^a-z_-].*", "", lowered)
    if first_word not in {
        "check",
        "examine",
        "inspect",
        "open",
        "read",
        "review",
        "scan",
        "skim",
    }:
        return False
    if any(marker in lowered for marker in ("apply", "draft", "edit", "finish", "repair", "run ", "verify", "write")):
        return False
    for path in target_paths or []:
        normalized = _normalized_work_path(path).casefold()
        basename = normalized.rsplit("/", 1)[-1]
        if normalized and normalized in lowered:
            return True
        if basename and basename in lowered:
            return True
    return False


def _write_ready_complete_read_frontier_allows_not_ready_override(first_observation, resume, complete_windows):
    target_paths = [
        str(item.get("path") or "").strip()
        for item in complete_windows or []
        if isinstance(item, dict) and str(item.get("path") or "").strip()
    ]
    if not _write_ready_paired_target_paths(target_paths):
        return False
    first_plan_item = str((first_observation or {}).get("plan_item") or "").strip()
    active_work_todo = (resume or {}).get("active_work_todo") if isinstance(resume, dict) else {}
    if _write_ready_refresh_blocker_cleared_by_complete_windows(active_work_todo, complete_windows):
        return True
    source = active_work_todo.get("source") if isinstance((active_work_todo or {}).get("source"), dict) else {}
    source_plan_item = str((source or {}).get("plan_item") or "").strip()
    return any(
        _write_ready_completed_read_frontier_plan_item(candidate, target_paths)
        for candidate in (first_plan_item, source_plan_item)
        if candidate
    )


def _work_write_ready_fast_path_state(context):
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") or {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    active_todo_status = str((active_work_todo or {}).get("status") or "").strip()
    if active_todo_status == "completed":
        return {"active": False, "reason": "active_work_todo_completed"}
    observations = resume.get("plan_item_observations") or []
    complete_active_windows = _write_ready_complete_recent_windows_from_active_work_todo(work_session, resume)
    steer_text = _write_ready_fast_path_steer_text(context, resume)
    if not observations:
        if complete_active_windows and _write_ready_complete_read_frontier_allows_not_ready_override(
            {},
            resume,
            complete_active_windows,
        ):
            if not _write_ready_fast_path_steer_requests_write(steer_text):
                return {"active": False, "reason": "guidance_not_requesting_write"}
            return {
                "active": True,
                "reason": "paired_complete_reads_edit_ready",
                "plan_item": {},
                "cached_windows": complete_active_windows,
                "activation_source": "active_work_todo_complete_reads",
                "steer_text": steer_text,
            }
        return {"active": False, "reason": "missing_plan_item_observations"}
    first = observations[0] or {}
    if _write_ready_fast_path_verifier_closeout_passed(context):
        source = {}
        if isinstance(active_work_todo, dict) and isinstance(active_work_todo.get("source"), dict):
            source = active_work_todo.get("source") or {}
        plan_item_text = str(first.get("plan_item") or source.get("plan_item") or "").strip()
        if _work_plan_item_is_verifier_closeout(plan_item_text):
            return {"active": False, "reason": "verifier_closeout_plan_item"}
    if complete_active_windows and _write_ready_refresh_blocker_cleared_by_complete_windows(
        resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {},
        complete_active_windows,
    ):
        if not _write_ready_fast_path_steer_requests_write(steer_text):
            return {"active": False, "reason": "guidance_not_requesting_write"}
        return {
            "active": True,
            "reason": "paired_complete_reads_edit_ready",
            "plan_item": first,
            "cached_windows": complete_active_windows,
            "activation_source": "active_work_todo_complete_reads",
            "steer_text": steer_text,
        }
    if not first.get("edit_ready"):
        plan_item_text = str(first.get("plan_item") or "").strip()
        if (
            complete_active_windows
            and not _work_plan_item_is_verifier_closeout(plan_item_text)
            and _write_ready_complete_read_frontier_allows_not_ready_override(
                first,
                resume,
                complete_active_windows,
            )
        ):
            if not _write_ready_fast_path_steer_requests_write(steer_text):
                return {"active": False, "reason": "guidance_not_requesting_write"}
            return {
                "active": True,
                "reason": "paired_complete_reads_edit_ready",
                "plan_item": first,
                "cached_windows": complete_active_windows,
                "activation_source": "active_work_todo_complete_reads",
                "steer_text": steer_text,
            }
        return {"active": False, "reason": "first_plan_item_not_edit_ready"}
    cached_windows = [
        item
        for item in (first.get("cached_windows") or [])
        if isinstance(item, dict) and item.get("path")
    ]
    activation_source = "plan_item_observations"
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    if _write_ready_active_todo_has_refresh_cached_window_blocker(
        active_work_todo
    ) or _write_ready_active_todo_is_refresh_recovery(active_work_todo, first):
        refreshed_windows = _write_ready_recent_windows_from_active_work_todo(work_session, resume)
        if refreshed_windows and _write_ready_recent_windows_are_structurally_complete(refreshed_windows):
            cached_windows = refreshed_windows
            activation_source = "active_work_todo_complete_reads"
    if len(cached_windows) < 2:
        cached_windows = _write_ready_cached_refs_from_active_work_todo(resume)
        if cached_windows:
            activation_source = "active_work_todo_cached_refs"
        else:
            cached_windows = _write_ready_recent_windows_from_active_work_todo(work_session, resume)
            if cached_windows:
                activation_source = "active_work_todo_fallback"
        if not cached_windows:
            return {"active": False, "reason": "insufficient_cached_windows"}
    has_tests = any(_work_batch_path_is_tests(item.get("path")) for item in cached_windows)
    has_source = any(_work_batch_path_is_mew_source(item.get("path")) for item in cached_windows)
    if not (has_tests and has_source):
        return {"active": False, "reason": "missing_source_test_pair"}

    if not _write_ready_fast_path_steer_requests_write(steer_text):
        return {"active": False, "reason": "guidance_not_requesting_write"}
    return {
        "active": True,
        "reason": "paired_cached_windows_edit_ready",
        "plan_item": observations[0] if observations else {},
        "cached_windows": cached_windows,
        "activation_source": activation_source,
        "steer_text": steer_text,
    }


def _work_plan_item_is_verifier_closeout(plan_item):
    text = str(plan_item or "").strip().casefold()
    if not text:
        return False
    no_change_finish = ("no-change" in text or "no change" in text) and any(
        marker in text for marker in ("record", "finish", "close")
    )
    conditional_green = any(
        marker in text
        for marker in (
            "if green",
            "if it passes",
            "if it succeeds",
            "if verifier passes",
            "if verification passes",
            "if the verifier passes",
            "if the verifier succeeds",
            "if the focused verifier passes",
            "if the focused verifier succeeds",
        )
    )
    conditional_failure_branch = any(
        marker in text
        for marker in (
            "otherwise repair",
            "otherwise edit",
            "if it fails",
            "if verifier fails",
            "if verification fails",
            "if the verifier fails",
            "if the focused verifier fails",
        )
    )
    if no_change_finish and conditional_green and conditional_failure_branch:
        return True
    repair_or_edit = any(marker in text for marker in ("repair", "edit"))
    source_test_intent = any(
        marker in text
        for marker in (
            "paired source/test",
            "source/test",
            "src/test",
            "source test",
            "source and test",
            "source/tests",
        )
    )
    if repair_or_edit and source_test_intent:
        return False
    if "ledger" in text:
        return True
    if repair_or_edit:
        return False
    closeout_markers = (
        "calibration ledger",
        "closeout",
        "non-counted",
        "non counted",
        "preserved verifier",
        "verifier evidence",
    )
    if any(marker in text for marker in closeout_markers):
        return True
    if no_change_finish:
        if not any(marker in text for marker in ("repair", "edit", "patch")):
            return True
    return "finish" in text and "verifier" in text


def _write_ready_recent_windows_from_target_paths(work_session, resume, *, prefer_newer=False):
    recent_windows = list((work_session or {}).get("recent_read_file_windows") or [])
    if not recent_windows:
        return []
    target_paths = []
    working_memory = (resume or {}).get("working_memory") or {}
    for path in working_memory.get("target_paths") or []:
        if isinstance(path, str) and path:
            target_paths.append(path)
    for item in (resume or {}).get("target_path_cached_window_observations") or []:
        path = (item or {}).get("path")
        if isinstance(path, str) and path:
            target_paths.append(path)
    ordered_paths = []
    for path in target_paths:
        if any(_work_paths_match(path, existing) for existing in ordered_paths):
            continue
        ordered_paths.append(path)
    def window_score(item):
        prepared = _write_ready_window_with_draft_window(item)
        draft_window = _write_ready_structural_window_for_draft(prepared)
        complete = _write_ready_window_text_is_structurally_complete(
            (draft_window or {}).get("text") or ""
        )
        try:
            span = int((draft_window or {}).get("line_end") or 0) - int(
                (draft_window or {}).get("line_start") or 0
            )
        except (TypeError, ValueError):
            span = 0
        try:
            tool_call_id = int(item.get("tool_call_id") or 0)
        except (TypeError, ValueError):
            tool_call_id = 0
        if prefer_newer:
            return (1 if complete else 0, tool_call_id, -span)
        return (1 if complete else 0, -span, tool_call_id)

    def window_complete(item):
        draft_window = _write_ready_structural_window_for_draft(item)
        return _write_ready_window_text_is_structurally_complete(
            (draft_window or {}).get("text") or ""
        )

    def windows_overlap(left, right):
        try:
            left_start = int(left.get("line_start") or 0)
            left_end = int(left.get("line_end") or 0)
            right_start = int(right.get("line_start") or 0)
            right_end = int(right.get("line_end") or 0)
        except (TypeError, ValueError):
            return False
        if left_start <= 0 or right_start <= 0 or left_end < left_start or right_end < right_start:
            return False
        return left_start <= right_end and right_start <= left_end

    matched = []
    for path in ordered_paths:
        candidates = []
        for item in recent_windows:
            if not _work_paths_match(item.get("path"), path):
                continue
            if not item.get("text") or item.get("context_truncated"):
                continue
            candidates.append(_write_ready_window_with_draft_window(item))
        if candidates:
            selected = []
            complete_candidates = [candidate for candidate in candidates if window_complete(candidate)]
            ranked_candidates = complete_candidates or candidates
            for candidate in sorted(ranked_candidates, key=window_score, reverse=True):
                if any(windows_overlap(candidate, existing) for existing in selected):
                    continue
                selected.append(candidate)
                if len(selected) >= WORK_WRITE_READY_RECENT_WINDOWS_PER_TARGET_PATH:
                    break
            matched.extend(
                sorted(
                    selected,
                    key=lambda item: int(item.get("line_start") or 0),
                )
            )
    if len(matched) < 2:
        return []
    has_tests = any(_work_batch_path_is_tests(item.get("path")) for item in matched)
    has_source = any(_work_batch_path_is_mew_source(item.get("path")) for item in matched)
    if not (has_tests and has_source):
        return []
    return matched


def _write_ready_recent_windows_from_active_work_todo(work_session, resume):
    resume = resume if isinstance(resume, dict) else {}
    active_work_todo = resume.get("active_work_todo") or {}
    if not isinstance(active_work_todo, dict):
        return []
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    if not isinstance(source, dict):
        return []
    target_paths = []
    for path in source.get("target_paths") or []:
        if not isinstance(path, str) or not path:
            continue
        if any(_work_paths_match(path, existing) for existing in target_paths):
            continue
        target_paths.append(path)
    if not target_paths:
        return []
    return _write_ready_recent_windows_from_target_paths(
        work_session,
        {
            "working_memory": {"target_paths": target_paths},
            "target_path_cached_window_observations": [
                {"path": path} for path in target_paths
            ],
        },
        prefer_newer=_write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo),
    )


def _write_ready_paired_target_paths(target_paths):
    paths = []
    for path in target_paths or []:
        if not isinstance(path, str) or not path:
            continue
        if any(_work_paths_match(path, existing) for existing in paths):
            continue
        paths.append(path)
    if len(paths) != 2:
        return []
    if not any(_work_batch_path_is_mew_source(path) for path in paths):
        return []
    if not any(_work_batch_path_is_tests(path) for path in paths):
        return []
    return paths


def _write_ready_complete_recent_windows_from_target_paths(work_session, target_paths):
    target_paths = _write_ready_paired_target_paths(target_paths)
    if not target_paths:
        return []
    recent_windows = [
        item
        for item in (work_session or {}).get("recent_read_file_windows") or []
        if isinstance(item, dict) and item.get("path")
    ]
    raw_calls_by_id = {
        call.get("id"): call
        for call in (work_session or {}).get("tool_calls") or []
        if isinstance(call, dict) and call.get("id") is not None
    }
    windows_by_path = {}
    for target_path in target_paths:
        for window in recent_windows:
            if not _work_paths_match(window.get("path"), target_path):
                continue
            raw_call = raw_calls_by_id.get(window.get("tool_call_id"))
            complete_file = bool(window.get("complete_file"))
            if not complete_file and raw_call:
                complete_file = _read_file_call_has_complete_file_result(raw_call)
            if not complete_file:
                continue
            if not window.get("text") or window.get("context_truncated"):
                continue
            if _write_ready_window_stale_after_later_write(work_session, window, target_path):
                continue
            windows_by_path[target_path] = {**window, "path": target_path, "context_truncated": False}
            break
        if target_path not in windows_by_path:
            window = _write_ready_latest_complete_read_window_for_path(work_session, target_path)
            if not window:
                return []
            windows_by_path[target_path] = window
    return [windows_by_path[path] for path in target_paths]


def _write_ready_complete_recent_windows_from_active_work_todo(work_session, resume):
    active_work_todo = (resume or {}).get("active_work_todo") if isinstance(resume, dict) else {}
    if not isinstance(active_work_todo, dict):
        return []
    status = str(active_work_todo.get("status") or "").strip()
    refresh_blocker = _write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo)
    if status not in ("queued", "drafting"):
        if not (status == "blocked_on_patch" and refresh_blocker):
            return []
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    complete_windows = _write_ready_complete_recent_windows_from_target_paths(
        work_session,
        source.get("target_paths") or [],
    )
    if status != "blocked_on_patch":
        return complete_windows
    if _write_ready_refresh_blocker_cleared_by_complete_windows(active_work_todo, complete_windows):
        return complete_windows
    recent_windows = [
        _write_ready_window_with_draft_window(window)
        for window in _write_ready_recent_windows_from_active_work_todo(work_session, resume)
    ]
    if recent_windows and _write_ready_recent_windows_are_structurally_complete(recent_windows):
        return recent_windows
    cached_refs = _write_ready_cached_refs_from_active_work_todo(resume)
    exact_windows = _write_ready_exact_windows_for_cached_refs(work_session, cached_refs)
    if exact_windows and _write_ready_recent_windows_are_structurally_complete(exact_windows):
        return exact_windows
    return []


def _write_ready_active_work_todo_status_allows_cached_refs(active_work_todo):
    status = str((active_work_todo or {}).get("status") or "").strip()
    if status in ("queued", "drafting"):
        return True
    if status != "blocked_on_patch":
        return False
    return _write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo)


def _write_ready_active_work_todo_source(active_work_todo):
    if not isinstance(active_work_todo, dict):
        return {}
    source = active_work_todo.get("source")
    if not isinstance(source, dict):
        return {}
    return source


def _write_ready_completed_write_touches_target_path(call, target_path):
    if not isinstance(call, dict) or call.get("tool") not in WRITE_WORK_TOOLS:
        return False
    if str(call.get("status") or "").strip() != "completed":
        return False
    result = call.get("result") if isinstance(call.get("result"), dict) else {}
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    path = result.get("path") or parameters.get("path") or ""
    if not path or not _work_paths_match(path, target_path):
        return False
    applied = bool(parameters.get("apply") or result.get("applied"))
    non_dry_run = result.get("dry_run") is False
    written_non_dry_run = bool(result.get("written")) and result.get("dry_run") is not True
    return applied or non_dry_run or written_non_dry_run


def _write_ready_call_id_matches(left, right):
    if left is None or right is None:
        return False
    return str(left) == str(right)


def _write_ready_call_id_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _write_ready_window_stale_after_later_write(work_session, window, target_path):
    tool_call_id = (window or {}).get("tool_call_id")
    if tool_call_id is None:
        return False
    calls = [call for call in (work_session or {}).get("tool_calls") or [] if isinstance(call, dict)]
    later_write = False
    for call in reversed(calls):
        if _write_ready_completed_write_touches_target_path(call, target_path):
            later_write = True
            continue
        if _write_ready_call_id_matches(call.get("id"), tool_call_id):
            return later_write

    read_id = _write_ready_call_id_int(tool_call_id)
    if read_id is None:
        return False
    for call in calls:
        call_id = _write_ready_call_id_int(call.get("id"))
        if call_id is None or call_id <= read_id:
            continue
        if _write_ready_completed_write_touches_target_path(call, target_path):
            return True
    return False


def _write_ready_text_line_count(text):
    return max(1, len(str(text or "").splitlines()))


def _write_ready_complete_read_window_from_call(call, target_path):
    if not _read_file_call_has_complete_file_result(call):
        return {}
    result = call.get("result") if isinstance(call.get("result"), dict) else {}
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    path = result.get("path") or parameters.get("path") or ""
    if not path or not _work_paths_match(path, target_path):
        return {}
    text = result.get("text")
    if not isinstance(text, str) or not text:
        return {}
    line_start = result.get("line_start")
    line_end = result.get("line_end")
    if line_start is not None or line_end is not None:
        try:
            line_start = int(line_start or 0)
            line_end = int(line_end or 0)
        except (TypeError, ValueError):
            return {}
        if line_start <= 0 or line_end < line_start:
            return {}
    else:
        line_start = 1
        line_end = _write_ready_text_line_count(text)
    return {
        "path": target_path,
        "tool_call_id": call.get("id"),
        "line_start": line_start,
        "line_end": line_end,
        "offset": result.get("offset", parameters.get("offset")),
        "text": text,
        "visible_chars": len(text),
        "source_text_chars": len(text),
        "context_truncated": False,
        "complete_file": True,
    }


def _write_ready_latest_complete_read_window_for_path(work_session, target_path):
    later_write = False
    for call in reversed(list((work_session or {}).get("tool_calls") or [])):
        if not isinstance(call, dict):
            continue
        if _write_ready_completed_write_touches_target_path(call, target_path):
            later_write = True
            continue
        window = _write_ready_complete_read_window_from_call(call, target_path)
        if not window:
            continue
        if later_write:
            return {}
        return window
    return {}


def _write_ready_cached_ref_bounds(cached):
    try:
        line_start = int((cached or {}).get("line_start") or 0)
        line_end = int((cached or {}).get("line_end") or 0)
    except (TypeError, ValueError):
        return ()
    if line_start <= 0 or line_end < line_start:
        return ()
    return line_start, line_end


def _write_ready_cached_refs_from_active_work_todo(resume):
    active_work_todo = (resume or {}).get("active_work_todo") if isinstance(resume, dict) else {}
    if not isinstance(active_work_todo, dict):
        return []
    if not _write_ready_active_work_todo_status_allows_cached_refs(active_work_todo):
        return []
    source = _write_ready_active_work_todo_source(active_work_todo)
    target_paths = _write_ready_paired_target_paths(source.get("target_paths") or [])
    if not target_paths:
        return []

    refs_by_path = {path: [] for path in target_paths}
    for ref in active_work_todo.get("cached_window_refs") or []:
        if not isinstance(ref, dict) or bool(ref.get("context_truncated")):
            continue
        bounds = _write_ready_cached_ref_bounds(ref)
        if not bounds:
            continue
        matching_path = ""
        for target_path in target_paths:
            if _work_paths_match(ref.get("path"), target_path):
                matching_path = target_path
                break
        if not matching_path:
            continue
        refs_by_path.setdefault(matching_path, []).append(
            {
                **ref,
                "path": matching_path,
                "line_start": bounds[0],
                "line_end": bounds[1],
            }
        )
    if any(not refs_by_path.get(path) for path in target_paths):
        return []
    refs = []
    for path in target_paths:
        refs.extend(
            sorted(
                refs_by_path.get(path) or [],
                key=lambda item: int(item.get("line_start") or 0),
            )
        )
    return refs


def _write_ready_read_call_window_for_cached_ref(call, cached):
    if not isinstance(call, dict) or call.get("tool") != "read_file":
        return {}
    if str(call.get("status") or "").strip() != "completed":
        return {}
    path = (cached or {}).get("path")
    result = call.get("result") if isinstance(call.get("result"), dict) else {}
    parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
    call_path = result.get("path") or parameters.get("path") or ""
    if not path or not call_path or not _work_paths_match(call_path, path):
        return {}
    text = result.get("text")
    if not isinstance(text, str) or not text:
        return {}
    if any(bool(result.get(key)) for key in ("context_truncated", "source_truncated", "truncated")):
        return {}

    bounds = _write_ready_cached_ref_bounds(cached)
    if not bounds:
        return {}
    cached_start, cached_end = bounds
    line_start = result.get("line_start")
    line_end = result.get("line_end")
    complete_file = False
    if line_start is not None or line_end is not None:
        try:
            line_start = int(line_start or 0)
            line_end = int(line_end or 0)
        except (TypeError, ValueError):
            return {}
        if line_start <= 0 or line_end < line_start:
            return {}
        complete_file = _read_file_call_has_complete_file_result(call)
    else:
        if not _read_file_call_has_complete_file_result(call):
            return {}
        line_start = 1
        line_end = _write_ready_text_line_count(text)
        complete_file = True
    if line_start > cached_start or line_end < cached_end:
        return {}
    return {
        "path": path,
        "tool_call_id": call.get("id"),
        "line_start": line_start,
        "line_end": line_end,
        "offset": result.get("offset", parameters.get("offset")),
        "text": text,
        "visible_chars": len(text),
        "source_text_chars": len(text),
        "context_truncated": False,
        "complete_file": complete_file,
    }


def _write_ready_tool_call_window_for_cached_ref(work_session, cached):
    later_write = False
    path = (cached or {}).get("path")
    for call in reversed(list((work_session or {}).get("tool_calls") or [])):
        if not isinstance(call, dict):
            continue
        if _write_ready_completed_write_touches_target_path(call, path):
            later_write = True
            continue
        window = _write_ready_read_call_window_for_cached_ref(call, cached)
        if not window:
            continue
        if later_write:
            return {}
        return _write_ready_window_with_draft_window(window)
    return {}


def _write_ready_exact_windows_for_cached_refs(work_session, cached_refs):
    windows = []
    for cached in cached_refs or []:
        if not isinstance(cached, dict):
            return []
        window = _write_ready_recent_window_for_cached_ref(
            cached,
            (work_session or {}).get("recent_read_file_windows") or [],
        )
        if window and _write_ready_window_stale_after_later_write(work_session, window, cached.get("path")):
            window = {}
        if not window:
            window = _write_ready_tool_call_window_for_cached_ref(work_session, cached)
        if not window:
            return []
        windows.append(window)
    return windows


def _write_ready_recent_window_covers_cached_ref(window, cached):
    if not _work_paths_match((window or {}).get("path"), (cached or {}).get("path")):
        return False
    if not (window or {}).get("text") or (window or {}).get("context_truncated"):
        return False
    try:
        window_start = int((window or {}).get("line_start") or 0)
        window_end = int((window or {}).get("line_end") or 0)
        cached_start = int((cached or {}).get("line_start") or 0)
        cached_end = int((cached or {}).get("line_end") or 0)
    except (TypeError, ValueError):
        return False
    if window_start <= 0 or window_end < window_start:
        return False
    if cached_start <= 0 or cached_end < cached_start:
        return False
    return window_start <= cached_start and window_end >= cached_end


def _write_ready_recent_window_for_cached_ref(cached, recent_windows):
    candidates = [
        item
        for item in recent_windows or []
        if _write_ready_recent_window_covers_cached_ref(item, cached)
    ]
    if not candidates:
        return {}
    prepared_candidates = [
        _write_ready_window_with_draft_window(item)
        for item in candidates
    ]

    def score(item):
        draft_window = _write_ready_structural_window_for_draft(item)
        try:
            span = int(draft_window.get("line_end") or 0) - int(draft_window.get("line_start") or 0)
        except (TypeError, ValueError):
            span = 0
        complete = _write_ready_window_text_is_structurally_complete(draft_window.get("text") or "")
        try:
            tool_call_id = int(item.get("tool_call_id") or 0)
        except (TypeError, ValueError):
            tool_call_id = 0
        return (1 if complete else 0, -span, tool_call_id)

    return max(prepared_candidates, key=score)


def _write_ready_window_structural_start_candidate(line):
    stripped = str(line or "").lstrip()
    if not stripped.strip():
        return False
    if not str(line or "")[0:1].isspace():
        return True
    if stripped.startswith(("def ", "async def ", "@")):
        return True
    return _write_ready_indented_simple_statement_start_line_is_allowed(stripped)


def _write_ready_structural_window_for_draft(window):
    window = window if isinstance(window, dict) else {}
    draft_window = window.get("draft_window") if isinstance(window.get("draft_window"), dict) else {}
    if draft_window.get("text"):
        return draft_window
    return window


def _write_ready_window_with_draft_window(window):
    window = window if isinstance(window, dict) else {}
    draft_window = _write_ready_structurally_complete_draft_window(window)
    if not draft_window:
        return window
    prepared = dict(window)
    prepared["draft_window"] = draft_window
    return prepared


def _write_ready_structurally_complete_draft_window(window):
    window = window if isinstance(window, dict) else {}
    text = window.get("text")
    if not isinstance(text, str) or not text:
        return {}
    if window.get("context_truncated"):
        return {}
    if _write_ready_window_text_is_structurally_complete(text):
        return {}
    try:
        line_start = int(window.get("line_start") or 0)
        line_end = int(window.get("line_end") or 0)
    except (TypeError, ValueError):
        return {}
    if line_start <= 0 or line_end < line_start:
        return {}
    lines = text.splitlines(keepends=True)
    line_span = line_end - line_start + 1
    if line_span < WORK_WRITE_READY_STRUCTURAL_NARROW_MIN_LINES:
        return {}
    if len(lines) != line_span:
        return {}
    start_indices = [
        index
        for index, line in enumerate(lines)
        if _write_ready_window_structural_start_candidate(line)
    ]
    if not start_indices:
        return {}
    significant_end_indices = [
        index
        for index, line in enumerate(lines)
        if str(line or "").strip()
    ]
    if not significant_end_indices:
        return {}

    def build_draft_window(start_index, end_index, candidate_text, reason):
        return {
            "path": window.get("path"),
            "tool_call_id": window.get("tool_call_id"),
            "line_start": line_start + start_index,
            "line_end": line_start + end_index,
            "text": candidate_text,
            "visible_chars": len(candidate_text),
            "source_text_chars": len(candidate_text),
            "context_truncated": False,
            "complete_file": False,
            "narrowed_from_line_start": line_start,
            "narrowed_from_line_end": line_end,
            "narrowed_reason": reason,
        }

    min_candidate_lines = min(WORK_WRITE_READY_STRUCTURAL_NARROW_MIN_LINES, line_span)
    last_index = len(lines) - 1
    for start_index in start_indices:
        for end_index in reversed(significant_end_indices):
            if end_index < start_index:
                break
            if end_index - start_index + 1 < min_candidate_lines:
                break
            candidate_text = "".join(lines[start_index : end_index + 1])
            if not _write_ready_window_text_is_structurally_complete(candidate_text):
                continue
            if start_index == 0:
                reason = "trimmed trailing structural fragment"
            elif end_index == last_index:
                reason = "trimmed leading structural fragment"
            else:
                reason = "trimmed leading and trailing structural fragments"
            return build_draft_window(
                start_index,
                end_index,
                candidate_text,
                reason,
            )
    return {}


def _write_ready_window_has_unmatched_delimiters(text):
    delimiter_pairs = {")": "(", "]": "[", "}": "{"}
    delimiter_stack = []
    try:
        for token in tokenize.generate_tokens(StringIO(text).readline):
            if token.type != tokenize.OP:
                continue
            token_text = token.string
            if token_text in "([{":
                delimiter_stack.append(token_text)
                continue
            expected_open = delimiter_pairs.get(token_text)
            if not expected_open:
                continue
            if not delimiter_stack or delimiter_stack[-1] != expected_open:
                return True
            delimiter_stack.pop()
    except tokenize.TokenError as exc:
        error_text = str(exc)
        if "EOF in multi-line statement" in error_text or "EOF in multi-line string" in error_text:
            return True
        return bool(delimiter_stack)
    except (IndentationError, SyntaxError):
        dedented = textwrap.dedent(str(text or ""))
        if dedented and dedented != str(text or ""):
            return _write_ready_window_has_unmatched_delimiters(dedented)
        return True
    return bool(delimiter_stack)


def _write_ready_indented_statement_fragment_is_allowed(significant_lines):
    if not significant_lines:
        return False
    first_line = significant_lines[0]
    if not first_line or not first_line[0].isspace():
        return True
    first_stripped = first_line.lstrip()
    first_indent = len(first_line) - len(first_stripped)
    if first_stripped.startswith(("def ", "async def ", "@")):
        for line in significant_lines:
            stripped = line.lstrip()
            if len(line) - len(stripped) < first_indent and not stripped.startswith("#"):
                return False
        return True
    for line in significant_lines:
        stripped = line.lstrip()
        if len(line) - len(stripped) < first_indent:
            return False
    if re.match(
        r"[A-Za-z_][A-Za-z0-9_]*(?:\s*:\s*[^=]+)?\s*=",
        first_stripped,
    ) and re.search(r"=\s*[\[\{\(]", first_stripped):
        return True
    if first_stripped.rstrip().endswith("(") and re.match(r"[A-Za-z_][A-Za-z0-9_.]*\s*\(", first_stripped):
        return True
    if _write_ready_literal_sequence_fragment_is_allowed(significant_lines, first_indent):
        return True
    if _write_ready_indented_simple_statement_sequence_is_allowed(significant_lines, first_indent):
        return True
    return False


def _write_ready_indented_simple_statement_start_line_is_allowed(stripped):
    stripped = str(stripped or "").strip()
    if not stripped or stripped.startswith("#") or stripped.endswith(":"):
        return False
    if re.match(r"^[\]\)\}]+,?$", stripped):
        return True
    if stripped.startswith(("import ", "from ")):
        return True
    if re.match(r"[A-Za-z_][A-Za-z0-9_.]*(?:\s*:\s*[^=]+)?\s*(?:=|\+=|-=|\*=|/=|//=|%=|\|=|&=|\^=)", stripped):
        return True
    return bool(re.match(r"[A-Za-z_][A-Za-z0-9_.]*\s*\(", stripped))


def _write_ready_indented_simple_statement_sequence_is_allowed(significant_lines, base_indent):
    if not significant_lines:
        return False
    base_statement_indexes = []
    for index, line in enumerate(significant_lines):
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent < base_indent:
            return False
        if indent > base_indent or stripped.startswith("#"):
            continue
        if stripped.startswith("return"):
            if index == 0:
                return False
            base_statement_indexes.append(index)
            continue
        if not _write_ready_indented_simple_statement_start_line_is_allowed(stripped):
            return False
        base_statement_indexes.append(index)
    if not base_statement_indexes:
        return False
    if len(base_statement_indexes) < 3:
        return False
    for index in base_statement_indexes:
        stripped = significant_lines[index].lstrip()
        if stripped.startswith("return") and index != base_statement_indexes[-1]:
            return False
    return True


def _write_ready_literal_sequence_fragment_is_allowed(significant_lines, base_indent):
    if not significant_lines:
        return False
    for line in significant_lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent != base_indent:
            return False
        if not stripped.startswith(("\"", "'")):
            return False
        if not stripped.rstrip().endswith((",", ")", "]", "}")):
            return False
    return True


def _write_ready_control_flow_fragment_is_allowed(significant_lines):
    if not significant_lines:
        return False
    first_line = significant_lines[0]
    first_stripped = first_line.lstrip()
    first_indent = len(first_line) - len(first_stripped)
    if not first_stripped.endswith(":"):
        return False
    first_keyword = first_stripped.split()[0].rstrip(":") if first_stripped else ""
    if first_keyword not in {"else", "elif", "except", "finally"}:
        return False
    saw_body = False
    for line in significant_lines[1:]:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent > first_indent:
            saw_body = True
            continue
        if saw_body and indent == first_indent and stripped.startswith(("elif ", "else:", "except ", "finally:")):
            return True
        if saw_body and indent < first_indent:
            return True
    return False


def _write_ready_window_text_is_structurally_complete(text):
    text = str(text or "")
    significant_lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not significant_lines:
        return False
    first_line = significant_lines[0]
    first_line_stripped = first_line.lstrip()
    first_keyword = first_line_stripped.split()[0].rstrip(":") if first_line_stripped else ""
    if first_line_stripped.endswith(":") and first_keyword in {"else", "elif", "except", "finally"}:
        return _write_ready_control_flow_fragment_is_allowed(significant_lines)
    if first_line and first_line[0].isspace():
        if not _write_ready_indented_statement_fragment_is_allowed(significant_lines):
            return False
    last_line = significant_lines[-1].lstrip()
    if last_line.endswith(":") or last_line.startswith(("def ", "class ", "async def ", "@")):
        return False
    if _write_ready_window_has_unmatched_delimiters(text):
        return False
    if _write_ready_window_ends_in_minimal_late_block(text):
        return False
    return True


def _write_ready_window_ends_in_minimal_late_block(text):
    lines = str(text or "").splitlines()
    significant = [(index, line) for index, line in enumerate(lines) if line.strip()]
    if not significant:
        return False
    first_significant_index = significant[0][0]

    block_starts = []
    for index, line in significant:
        stripped = line.lstrip()
        if stripped.startswith(("def ", "async def ", "class ")):
            block_starts.append((index, len(line) - len(stripped)))
    if not block_starts:
        return False

    last_block_index, last_block_indent = block_starts[-1]
    if last_block_index == first_significant_index:
        return False
    if not any(indent == last_block_indent for _, indent in block_starts[:-1]):
        return False

    body_lines = 0
    saw_closing_or_sibling = False
    for index, line in significant:
        if index <= last_block_index:
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if indent <= last_block_indent:
            saw_closing_or_sibling = True
            break
        body_lines += 1
    return not saw_closing_or_sibling and body_lines <= 1


def _write_ready_recent_windows_are_structurally_complete(recent_windows):
    for item in recent_windows or []:
        draft_window = _write_ready_structural_window_for_draft(item)
        if not _write_ready_window_text_is_structurally_complete((draft_window or {}).get("text") or ""):
            return False
    return True


def _work_write_ready_fast_path_verify_command(context):
    resume = (context or {}).get("work_session", {}).get("resume") or {}
    active_work_todo = resume.get("active_work_todo") or {}
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    return str(source.get("verify_command") or "").strip()


def _write_ready_failed_patch_repair_for_targets(resume, target_paths):
    repair = (resume or {}).get("failed_patch_repair")
    if not isinstance(repair, dict):
        return {}
    repair_paths = _write_ready_paired_target_paths(repair.get("proposal_paths") or [])
    target_paths = _write_ready_paired_target_paths(target_paths or [])
    if target_paths and repair_paths and not set(repair_paths).issubset(set(target_paths)):
        return {}
    result = {
        "kind": "failed_patch_repair",
        "model_turn_id": repair.get("model_turn_id"),
        "failed_tool_call_id": repair.get("failed_tool_call_id"),
        "failed_path": str(repair.get("failed_path") or "").strip(),
        "proposal_summary": str(repair.get("proposal_summary") or "").strip(),
        "proposal_paths": repair_paths or target_paths,
        "must_preserve_terms": [
            str(term)
            for term in (repair.get("must_preserve_terms") or [])
            if str(term).strip()
        ][:8],
        "proposal_snippets": [
            item
            for item in (repair.get("proposal_snippets") or [])
            if isinstance(item, dict)
        ][:4],
        "repair_instruction": str(repair.get("repair_instruction") or "").strip(),
    }
    if not any(str((item or {}).get("new_snippet") or "").strip() for item in result["proposal_snippets"]):
        return {}
    return {key: value for key, value in result.items() if value not in (None, "", [])}


def _write_ready_task_goal_required_terms(context, resume=None):
    context = context if isinstance(context, dict) else {}
    resume = resume if isinstance(resume, dict) else ((context.get("work_session") or {}).get("resume") or {})
    task = context.get("task") if isinstance(context.get("task"), dict) else {}
    text_parts = [
        str(task.get("title") or ""),
        _write_ready_task_goal_description_text(task.get("description") or ""),
        str(context.get("guidance") or ""),
    ]
    pending_steer = resume.get("pending_steer") if isinstance(resume.get("pending_steer"), dict) else {}
    text_parts.append(str(pending_steer.get("text") or ""))
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    text_parts.append(str(source.get("plan_item") or ""))

    terms = []
    seen = set()
    for text in text_parts:
        text = WORK_TASK_GOAL_PATH_FRAGMENT_RE.sub(" ", text)
        for match in WORK_TASK_GOAL_TERM_RE.finditer(text):
            term = match.group(0).strip()
            key = term.casefold()
            if key in WORK_TASK_GOAL_TERM_STOPWORDS:
                continue
            if key in seen:
                continue
            seen.add(key)
            terms.append(term)

    milestone_terms = [term for term in terms if term.casefold().startswith("m6_")]
    if milestone_terms:
        milestone_keys = {term.casefold() for term in milestone_terms}
        structured_terms = [
            term
            for term in terms
            if "_" in term and term.casefold() not in milestone_keys
        ]
        structured_keys = {term.casefold() for term in structured_terms}
        other_terms = [
            term
            for term in terms
            if term.casefold() not in milestone_keys and term.casefold() not in structured_keys
        ]
        selected = []
        selected_keys = set()
        for group in (
            milestone_terms[:WORK_TASK_GOAL_MILESTONE_TERMS_LIMIT],
            structured_terms,
            other_terms,
        ):
            for term in group:
                key = term.casefold()
                if key in selected_keys:
                    continue
                selected.append(term)
                selected_keys.add(key)
                if len(selected) >= WORK_TASK_GOAL_REQUIRED_TERMS_LIMIT:
                    return selected
        return selected
    return terms[:4]


def _write_ready_task_goal_description_text(description):
    text = str(description or "")
    focus_match = re.search(r"(?:^|\n)Focus:\n", text)
    if focus_match:
        text = text[focus_match.end() :]
    for marker in WORK_TASK_GOAL_DESCRIPTION_APPENDIX_MARKERS:
        marker_index = text.find(marker)
        if marker_index >= 0:
            text = text[:marker_index]
    return text.strip()


def _work_write_ready_fast_path_latest_completed_verifier_tool_call(context):
    work_session = (context or {}).get("work_session") or {}
    latest_call = {}
    for call in reversed(list(work_session.get("tool_calls") or [])):
        if str(call.get("status") or "").strip() == "completed":
            latest_call = call
            break
    if latest_call.get("tool") != "run_tests":
        return {}
    result = latest_call.get("result") or {}
    verification = result.get("verification")
    if isinstance(verification, dict):
        command = str(verification.get("command") or "").strip()
        exit_code = verification.get("exit_code")
    else:
        command = str(result.get("command") or (latest_call.get("parameters") or {}).get("command") or "").strip()
        exit_code = result.get("exit_code")
    if exit_code is None or not command:
        return {}
    try:
        passed = int(exit_code) == 0
    except (TypeError, ValueError):
        passed = False
    return {
        "id": latest_call.get("id"),
        "command": command,
        "status": "passed" if passed else "failed",
    }


def _work_write_ready_fast_path_latest_completed_verifier_model_turn(context):
    work_session = (context or {}).get("work_session") or {}
    tool_calls = list(work_session.get("tool_calls") or [])
    tool_calls_by_id = {
        call.get("id"): call for call in tool_calls if isinstance(call, dict) and call.get("id") is not None
    }
    for turn in reversed(list(work_session.get("model_turns") or [])):
        if str(turn.get("status") or "").strip() != "completed":
            continue
        action = turn.get("action") or {}
        if action.get("type") != "run_tests":
            continue
        command = str(action.get("command") or "").strip()
        linked_tool_call_id = turn.get("tool_call_id")
        linked_tool_call = tool_calls_by_id.get(linked_tool_call_id) if linked_tool_call_id is not None else {}
        if not command and linked_tool_call and str(linked_tool_call.get("status") or "").strip() == "completed":
            if linked_tool_call.get("tool") == "run_tests":
                result = linked_tool_call.get("result") or {}
                verification = result.get("verification")
                if isinstance(verification, dict):
                    command = str(verification.get("command") or "").strip()
                else:
                    command = str(
                        result.get("command")
                        or (linked_tool_call.get("parameters") or {}).get("command")
                        or ""
                    ).strip()
        if not command:
            continue
        decision_plan = turn.get("decision_plan") if isinstance(turn.get("decision_plan"), dict) else {}
        working_memory = (
            decision_plan.get("working_memory") if isinstance(decision_plan.get("working_memory"), dict) else {}
        )
        target_paths = turn.get("target_paths")
        if not target_paths:
            target_paths = decision_plan.get("target_paths")
        if not target_paths:
            target_paths = working_memory.get("target_paths")
        metrics = turn.get("model_metrics") if isinstance(turn.get("model_metrics"), dict) else {}
        write_ready_fast_path = turn.get("write_ready_fast_path")
        if write_ready_fast_path is None and "write_ready_fast_path" in metrics:
            write_ready_fast_path = metrics.get("write_ready_fast_path")
        write_ready_fast_path_reason = str(turn.get("write_ready_fast_path_reason") or "").strip()
        if not write_ready_fast_path_reason:
            write_ready_fast_path_reason = str(metrics.get("write_ready_fast_path_reason") or "").strip()
        return {
            "id": turn.get("id"),
            "tool_call_id": turn.get("tool_call_id"),
            "command": command,
            "target_paths": [
                str(path)
                for path in (target_paths or [])
                if isinstance(path, str) and path
            ],
            "write_ready_fast_path": write_ready_fast_path,
            "write_ready_fast_path_reason": write_ready_fast_path_reason,
        }
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    closeout = resume.get("latest_verifier_closeout") if isinstance(resume.get("latest_verifier_closeout"), dict) else {}
    if closeout:
        return {
            "id": closeout.get("model_turn_id"),
            "tool_call_id": closeout.get("tool_call_id"),
            "command": str(closeout.get("command") or "").strip(),
            "target_paths": [
                str(path)
                for path in (closeout.get("target_paths") or [])
                if isinstance(path, str) and path
            ],
            "write_ready_fast_path": closeout.get("write_ready_fast_path"),
            "write_ready_fast_path_reason": str(closeout.get("write_ready_fast_path_reason") or "").strip(),
        }
    return {}


def _write_ready_fast_path_verifier_closeout_passed(context):
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") or {}
    active_work_todo = resume.get("active_work_todo") or {}
    status = str(active_work_todo.get("status") or "").strip()
    if status not in ("drafting", "queued"):
        return False
    verify_command = _work_write_ready_fast_path_verify_command(context)
    if not verify_command:
        return False
    verifier_tool_call = _work_write_ready_fast_path_latest_completed_verifier_tool_call(context)
    if str(verifier_tool_call.get("status") or "") != "passed":
        return False
    verifier_model_turn = _work_write_ready_fast_path_latest_completed_verifier_model_turn(context)
    if str(verifier_tool_call.get("command") or "") != verify_command:
        return False
    if str(verifier_model_turn.get("command") or "") != verify_command:
        return False
    expected_target_paths = [
        str(path)
        for path in ((active_work_todo.get("source") or {}).get("target_paths") or [])
        if isinstance(path, str) and path
    ]
    observed_target_paths = [
        str(path)
        for path in (verifier_model_turn.get("target_paths") or [])
        if isinstance(path, str) and path
    ]
    if len(expected_target_paths) != len(observed_target_paths):
        return False
    if any(
        not any(_work_paths_match(expected, observed) for observed in observed_target_paths)
        for expected in expected_target_paths
    ):
        return False
    if verifier_model_turn.get("write_ready_fast_path") is not False:
        return False
    if not str(verifier_model_turn.get("write_ready_fast_path_reason") or ""):
        return False
    turn_tool_call_id = verifier_model_turn.get("tool_call_id")
    tool_call_id = verifier_tool_call.get("id")
    if turn_tool_call_id is None or tool_call_id is None:
        return False
    return turn_tool_call_id == tool_call_id


def _calibration_measured_contract_text(task, context=None):
    task = task or {}
    parts = [
        str(task.get(field) or "").strip()
        for field in ("title", "description", "notes")
        if task.get(field) is not None
    ]
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    pending_steer = resume.get("pending_steer") if isinstance(resume.get("pending_steer"), dict) else {}
    steer_text = str(pending_steer.get("text") or "").strip()
    if steer_text:
        parts.append(steer_text)
    guidance = str((context or {}).get("guidance") or "").strip()
    if guidance:
        parts.append(guidance)
    return " ".join(part for part in parts if part).lower().strip()


def _is_calibration_measured_patch_draft_task(task, context=None):
    text = _calibration_measured_contract_text(task, context)
    if not text:
        return False
    has_sample_marker = "sample" in text
    has_current_head_marker = any(
        marker in text
        for marker in (
            "current-head",
            "current head",
            "current_head",
        )
    )
    has_patch_draft_marker = any(
        marker in text
        for marker in ("patchdraft", "patch draft", "patch_draft")
    )
    has_measurement_contract_marker = any(
        marker in text
        for marker in (
            "replay bundle",
            "get one live replay result",
            "count the sample only if",
            "calibration ledger row",
            "counted replay bundle",
            "exact non-counted conclusion",
            "do not finish from a passing verifier alone",
        )
    )
    has_current_head_patch_draft_markers = has_current_head_marker and has_patch_draft_marker
    if has_current_head_patch_draft_markers and has_measurement_contract_marker:
        return True
    has_current_head_sample_patch_draft_markers = (
        has_sample_marker
        and has_current_head_patch_draft_markers
    )
    return bool(
        has_current_head_sample_patch_draft_markers
        and _calibration_measured_patch_draft_task_scope_target_paths(task)
    )


def _calibration_measured_patch_draft_task_forbids_verifier_only_finish(task, context=None):
    return _calibration_measured_task_forbids_verifier_only_finish(task, context)


def _calibration_measured_task_forbids_verifier_only_finish(task, context=None):
    text = _calibration_measured_contract_text(task, context)
    return any(
        marker in text
        for marker in (
            "do not finish from a passing verifier alone",
            "do not finish from a passing unit test alone",
            "do not finish from a passing test alone",
        )
    )


def _is_calibration_measured_finish_gated_task(task, context=None):
    return _is_calibration_measured_patch_draft_task(
        task,
        context,
    ) or _calibration_measured_task_forbids_verifier_only_finish(task, context)


def _calibration_measured_patch_draft_has_paired_patch_evidence(context):
    work_session = (context or {}).get("work_session") or {}
    source_seen = False
    test_seen = False
    for call in work_session.get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        if str(call.get("status") or "") != "completed":
            continue
        if str(call.get("tool") or "") not in {"write_file", "edit_file", "edit_file_hunks"}:
            continue
        if call.get("approval_status") in ("rejected", "failed", APPROVAL_STATUS_INDETERMINATE):
            continue
        result = call.get("result") if isinstance(call.get("result"), dict) else {}
        changed = result.get("changed")
        if changed is False:
            continue
        path = str(
            result.get("path")
            or (call.get("parameters") or {}).get("path")
            or ""
        ).strip()
        if not path:
            continue
        if _work_batch_path_is_mew_source(path):
            source_seen = True
        if _work_batch_path_is_tests(path):
            test_seen = True
        if source_seen and test_seen:
            return True
    return False


def _calibration_measured_patch_draft_expected_target_paths(target_paths):
    normalized_paths = []
    for path in target_paths or []:
        normalized_path = normalize_work_path(path)
        if normalized_path:
            normalized_paths.append(normalized_path)
    if len(normalized_paths) != 2 or len(set(normalized_paths)) != 2:
        return []
    if not any(_work_batch_path_is_mew_source(path) for path in normalized_paths):
        return []
    if not any(_work_batch_path_is_tests(path) for path in normalized_paths):
        return []
    return normalized_paths


def _calibration_measured_patch_draft_task_scope_target_paths(task):
    return _calibration_measured_patch_draft_expected_target_paths(
        task_scope_target_paths(task)
    )


def _calibration_measured_patch_draft_scoped_target_paths(context, task=None):
    resume = ((context or {}).get("work_session") or {}).get("resume") or {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    target_paths = _calibration_measured_patch_draft_expected_target_paths(
        source.get("target_paths") or []
    )
    if target_paths:
        return target_paths
    if active_work_todo:
        return []
    return _calibration_measured_patch_draft_task_scope_target_paths(task)


def _calibration_measured_patch_draft_matching_target_path(path, target_paths):
    normalized_path = normalize_work_path(path)
    if not normalized_path:
        return ""
    for target_path in target_paths or []:
        if _work_paths_match(normalized_path, target_path):
            return target_path
    return ""


def _calibration_measured_patch_draft_recent_window_is_exact(window, raw_call=None):
    window = window if isinstance(window, dict) else {}
    raw_call = raw_call if isinstance(raw_call, dict) else {}
    raw_result = raw_call.get("result") if isinstance(raw_call.get("result"), dict) else {}
    if any(bool(window.get(key)) for key in ("context_truncated", "source_truncated", "truncated")):
        return False
    if any(bool(raw_result.get(key)) for key in ("context_truncated", "source_truncated", "truncated")):
        return False
    if not isinstance(window.get("text"), str) or not window.get("text"):
        return False

    line_start = window.get("line_start")
    line_end = window.get("line_end")
    if line_start is None and line_end is None:
        offset = window.get("offset")
        if offset is None:
            offset = raw_result.get("offset")
        try:
            offset = int(offset or 0)
        except (TypeError, ValueError):
            return False
        if offset != 0:
            return False
        if raw_result.get("next_offset") not in (None, ""):
            return False
        return True

    try:
        line_start = int(line_start or 0)
        line_end = int(line_end or 0)
    except (TypeError, ValueError):
        return False
    if line_start != 1 or line_end < line_start:
        return False
    return raw_result.get("has_more_lines") is False


def _calibration_measured_patch_draft_exact_recent_windows_from_task_scope(
    work_session,
    target_paths,
    *,
    session=None,
):
    raw_calls = list((session or {}).get("tool_calls") or [])
    if not raw_calls:
        raw_calls = list((work_session or {}).get("tool_calls") or [])
    raw_calls_by_id = {
        call.get("id"): call
        for call in raw_calls
        if isinstance(call, dict) and call.get("id") is not None
    }
    windows_by_path = {}
    for window in (work_session or {}).get("recent_read_file_windows") or []:
        if not isinstance(window, dict):
            continue
        path = _calibration_measured_patch_draft_matching_target_path(
            window.get("path"),
            target_paths,
        )
        if not path or path in windows_by_path:
            continue
        raw_call = raw_calls_by_id.get(window.get("tool_call_id"))
        if not _calibration_measured_patch_draft_recent_window_is_exact(window, raw_call):
            return []
        normalized_window = {
            **window,
            "path": path,
            "context_truncated": False,
        }
        line_start = normalized_window.get("line_start")
        line_end = normalized_window.get("line_end")
        if line_start is not None or line_end is not None:
            normalized_window["line_start"] = int(line_start)
            normalized_window["line_end"] = int(line_end)
        windows_by_path[path] = normalized_window
    if set(windows_by_path) != set(target_paths):
        return []
    return [windows_by_path[path] for path in target_paths]


def _calibration_measured_patch_draft_exact_recent_windows(context, task=None, session=None):
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    target_paths = _calibration_measured_patch_draft_scoped_target_paths(context, task=task)
    if not target_paths:
        return []
    if not active_work_todo:
        return _calibration_measured_patch_draft_exact_recent_windows_from_task_scope(
            work_session,
            target_paths,
            session=session,
        )
    refs_by_path = {}
    window_refs = list(active_work_todo.get("cached_window_refs") or [])
    if not window_refs:
        window_refs = list(resume.get("target_path_cached_window_observations") or [])
    for ref in window_refs:
        if not isinstance(ref, dict):
            continue
        path = _calibration_measured_patch_draft_matching_target_path(
            ref.get("path"),
            target_paths,
        )
        if not path:
            continue
        if bool(ref.get("context_truncated")):
            return []
        try:
            line_start = int(ref.get("line_start") or 0)
            line_end = int(ref.get("line_end") or 0)
        except (TypeError, ValueError):
            return []
        if line_start <= 0 or line_end < line_start:
            return []
        refs_by_path[path] = {**ref, "path": path, "line_start": line_start, "line_end": line_end}
    if set(refs_by_path) != set(target_paths):
        return []

    windows_by_path = {}
    for window in work_session.get("recent_read_file_windows") or []:
        if not isinstance(window, dict):
            continue
        path = _calibration_measured_patch_draft_matching_target_path(
            window.get("path"),
            refs_by_path.keys(),
        )
        ref = refs_by_path.get(path)
        if not ref:
            continue
        try:
            line_start = int(window.get("line_start") or 0)
            line_end = int(window.get("line_end") or 0)
        except (TypeError, ValueError):
            continue
        if line_start > ref["line_start"] or line_end < ref["line_end"]:
            continue
        if any(bool(window.get(key)) for key in ("context_truncated", "source_truncated", "truncated")):
            return []
        if not isinstance(window.get("text"), str) or not window.get("text"):
            return []
        windows_by_path[path] = {
            **window,
            "path": path,
            "line_start": line_start,
            "line_end": line_end,
            "context_truncated": False,
        }
    if set(windows_by_path) != set(target_paths):
        return []
    return [windows_by_path[path] for path in target_paths]


def _calibration_measured_patch_draft_verifier_closeout_passed(task, context):
    if _write_ready_fast_path_verifier_closeout_passed(context):
        return True

    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    if active_work_todo:
        return False

    expected_target_paths = _calibration_measured_patch_draft_scoped_target_paths(
        context,
        task=task,
    )
    if not expected_target_paths:
        return False
    verifier_tool_call = _work_write_ready_fast_path_latest_completed_verifier_tool_call(context)
    if str(verifier_tool_call.get("status") or "") != "passed":
        return False
    verifier_model_turn = _work_write_ready_fast_path_latest_completed_verifier_model_turn(context)
    if not verifier_model_turn:
        return False
    verify_command = str(verifier_tool_call.get("command") or "").strip()
    if not verify_command or str(verifier_model_turn.get("command") or "").strip() != verify_command:
        return False
    observed_target_paths = [
        str(path)
        for path in (verifier_model_turn.get("target_paths") or [])
        if isinstance(path, str) and path
    ]
    if len(expected_target_paths) != len(observed_target_paths):
        return False
    if any(
        not any(_work_paths_match(expected, observed) for observed in observed_target_paths)
        for expected in expected_target_paths
    ):
        return False
    if verifier_model_turn.get("write_ready_fast_path") is not False:
        return False
    turn_tool_call_id = verifier_model_turn.get("tool_call_id")
    tool_call_id = verifier_tool_call.get("id")
    if turn_tool_call_id is None or tool_call_id is None:
        return False
    return turn_tool_call_id == tool_call_id


def _calibration_measured_patch_draft_no_change_replay_action(
    *,
    task,
    session,
    context,
    model_metrics,
    allowed_write_roots=None,
):
    if not session:
        return {}
    if not _calibration_measured_patch_draft_verifier_closeout_passed(task, context):
        return {}
    recent_windows = _calibration_measured_patch_draft_exact_recent_windows(
        context,
        task=task,
        session=session,
    )
    if not recent_windows:
        return {}
    resume = ((context or {}).get("work_session") or {}).get("resume") or {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    todo_id = str(active_work_todo.get("id") or "").strip()
    if not todo_id:
        session_id = str(
            (session or {}).get("id")
            or ((context or {}).get("work_session") or {}).get("id")
            or ""
        ).strip()
        todo_id = f"session-{session_id}-patch-draft-no-change" if session_id else "patch-draft-no-change"
    proposal = {
        "kind": "patch_blocker",
        "summary": "no concrete draftable change after matching verifier closeout",
        "code": "no_material_change",
        "detail": (
            "calibration-measured patch_draft finish attempted after exact scoped windows "
            "and matching green verifier evidence, but no concrete draftable change was emitted"
        ),
    }
    compiled = _compile_write_ready_patch_draft_proposal(
        session=session,
        context=context,
        proposal=proposal,
        write_ready_fast_path={"recent_windows": recent_windows},
        allowed_write_roots=allowed_write_roots,
        todo_id_override=todo_id,
    )
    observation = compiled.get("observation") or _empty_patch_draft_compiler_observation()
    if any(observation.get(key) for key in observation):
        model_metrics.update(observation)
    validator_result = compiled.get("validator_result") if isinstance(compiled.get("validator_result"), dict) else {}
    if validator_result.get("kind") != "patch_blocker":
        return {}
    blocker_payload = _work_loop_tiny_write_ready_draft_blocker_payload(validator_result)
    if todo_id:
        blocker_payload["todo_id"] = todo_id
    replay_path = str((observation or {}).get("patch_draft_compiler_replay_path") or "").strip()
    if replay_path:
        blocker_payload["replay_path"] = replay_path
    else:
        blocker_payload["calibration_counted"] = False
        blocker_payload["calibration_exclusion_reason"] = (
            "same-session patch_draft compiler replay artifact was not written"
        )
    model_metrics.update(
        {
            "tiny_write_ready_draft_outcome": "blocker",
            "tiny_write_ready_draft_fallback_reason": "",
            "tiny_write_ready_draft_compiler_artifact_kind": "patch_blocker",
        }
    )
    return {
        "type": "wait",
        "reason": _stable_write_ready_tiny_draft_blocker_reason(validator_result),
        "todo_id": todo_id,
        "blocker": blocker_payload,
    }


def _calibration_measured_finish_is_no_change_closeout(action, action_plan=None):
    action = action if isinstance(action, dict) else {}
    action_plan = action_plan if isinstance(action_plan, dict) else {}
    planned_action = (
        action_plan.get("action") if isinstance(action_plan.get("action"), dict) else {}
    )
    text = " ".join(
        str(value or "")
        for value in (
            action.get("reason"),
            action.get("summary"),
            action_plan.get("summary"),
            planned_action.get("reason"),
            planned_action.get("summary"),
        )
    ).casefold()
    return any(
        marker in text
        for marker in (
            "no-change",
            "no change",
            "no concrete",
            "no_material",
            "no_material_change",
            "no material",
            "nothing to change",
            "already satisfied",
        )
    )


def _calibration_measured_patch_draft_finish_allowed(task, context, model_metrics):
    def valid_replay_path(candidate):
        replay_path = str(candidate or "").strip()
        if not replay_path:
            return False
        path = Path(replay_path)
        if not path.is_file():
            return False
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return False
        if not isinstance(metadata, dict):
            return False
        if metadata.get("schema_version") != 1:
            return False
        if metadata.get("bundle") != "patch_draft_compiler":
            return False
        files = metadata.get("files") if isinstance(metadata.get("files"), dict) else {}
        for key in (
            "todo",
            "proposal",
            "cached_windows",
            "live_files",
            "allowed_write_roots",
            "validator_result",
        ):
            relative_path = str(files.get(key) or "").strip()
            if not relative_path or Path(relative_path).is_absolute():
                return False
            payload_path = path.parent / relative_path
            if not payload_path.is_file():
                return False
        work_session = (context or {}).get("work_session") or {}
        resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
        session_id = str(work_session.get("id") or resume.get("session_id") or "").strip()
        if session_id and str(metadata.get("session_id") or "").strip() != session_id:
            return False
        active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
        todo_id = str(active_work_todo.get("id") or "").strip()
        if todo_id and str(metadata.get("todo_id") or "").strip() != todo_id:
            return False
        return True

    replay_path = str((model_metrics or {}).get("patch_draft_compiler_replay_path") or "").strip()
    if valid_replay_path(replay_path):
        return True
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    latest_replay = (
        resume.get("latest_patch_draft_compiler_replay")
        if isinstance(resume.get("latest_patch_draft_compiler_replay"), dict)
        else {}
    )
    replay_path = str(latest_replay.get("path") or "").strip()
    if valid_replay_path(replay_path):
        return True
    if _calibration_measured_patch_draft_has_paired_patch_evidence(context):
        return True
    if (
        _write_ready_fast_path_verifier_closeout_passed(context)
        and not _calibration_measured_patch_draft_task_forbids_verifier_only_finish(task, context)
    ):
        return True
    return False


def _enforce_calibration_measured_patch_draft_finish_gate(
    task,
    context,
    action,
    model_metrics,
    *,
    session=None,
    allowed_write_roots=None,
    action_plan=None,
):
    if str((action or {}).get("type") or "") != "finish":
        return action
    if not _is_calibration_measured_finish_gated_task(task, context):
        return action
    if _calibration_measured_patch_draft_finish_allowed(task, context, model_metrics):
        return action
    if (
        _is_calibration_measured_patch_draft_task(task, context)
        and _calibration_measured_finish_is_no_change_closeout(action, action_plan)
    ):
        replay_action = _calibration_measured_patch_draft_no_change_replay_action(
            task=task,
            session=session,
            context=context,
            model_metrics=model_metrics,
            allowed_write_roots=allowed_write_roots,
        )
        if replay_action:
            if isinstance(action_plan, dict):
                action_plan["summary"] = replay_action.get("reason") or action_plan.get("summary") or ""
                action_plan["action"] = replay_action
                action_plan["act_mode"] = "tiny_write_ready_draft"
                if replay_action.get("todo_id"):
                    action_plan["todo_id"] = replay_action.get("todo_id")
                if isinstance(replay_action.get("blocker"), dict):
                    action_plan["blocker"] = replay_action.get("blocker")
            return replay_action
    return {
        "type": "wait",
        "reason": (
            "finish is blocked: calibration-measured tasks require "
            "a same-session replay artifact or reviewer-visible paired patch evidence; "
            "verifier-only closeout is not enough for this task"
        ),
    }


def _work_write_ready_fast_path_details(context):
    fast_path = _work_write_ready_fast_path_state(context)
    if not fast_path.get("active"):
        return fast_path
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") or {}
    cached_paths = [item.get("path") for item in fast_path.get("cached_windows") or []]
    recent_windows = []
    if fast_path.get("activation_source") == "active_work_todo_complete_reads":
        recent_windows = list(fast_path.get("cached_windows") or [])
    else:
        recent_windows = _write_ready_exact_windows_for_cached_refs(
            work_session,
            fast_path.get("cached_windows") or [],
        )
    if not recent_windows:
        if fast_path.get("activation_source") == "active_work_todo_cached_refs":
            return {
                **fast_path,
                "active": False,
                "reason": "missing_exact_cached_window_texts",
            }
        recent_windows = _write_ready_recent_windows_from_target_paths(work_session, resume)
        if not recent_windows:
            return {
                **fast_path,
                "active": False,
                "reason": "missing_exact_cached_window_texts",
            }
    recent_windows = [
        _write_ready_window_with_draft_window(window)
        for window in recent_windows
    ]
    if not _write_ready_recent_windows_are_structurally_complete(recent_windows):
        if _write_ready_fast_path_verifier_closeout_passed(context):
            return {
                **fast_path,
                "recent_windows": recent_windows,
                "cached_paths": cached_paths,
            }
        return {
            **fast_path,
            "active": False,
            "reason": "insufficient_cached_window_context",
            "recent_windows": recent_windows,
            "cached_paths": cached_paths,
        }
    return {
        **fast_path,
        "recent_windows": recent_windows,
        "cached_paths": cached_paths,
    }


def _work_write_ready_explicit_refresh_read_actions(context, target_paths):
    text_parts = []
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    pending_steer = resume.get("pending_steer") if isinstance(resume.get("pending_steer"), dict) else {}
    steer_text = str(pending_steer.get("text") or "").strip()
    if steer_text:
        text_parts.append(steer_text)
    guidance = str((context or {}).get("guidance") or "").strip()
    if guidance:
        text_parts.append(guidance)
    if not text_parts:
        return []

    allowed_paths = [str(path or "").strip() for path in target_paths or [] if str(path or "").strip()]
    if not allowed_paths:
        return []
    text = "\n".join(text_parts)
    path_pattern = r"[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+"
    span_pattern = re.compile(
        rf"(?P<path>{path_pattern})\s*(?:[:,]?\s*)"
        r"(?:lines?|line span|line window|window)\s+"
        r"(?P<start>\d{1,7})\s*(?:-|\.{2}|:|to)\s*(?P<end>\d{1,7})",
        re.IGNORECASE,
    )
    not_path_chunk = rf"(?:(?!{path_pattern}).)"
    line_start_count_pattern = re.compile(
        rf"(?P<path>{path_pattern})"
        rf"(?P<body>{not_path_chunk}{{0,160}}?)"
        r"\b(?:line[_ -]?start|start[_ -]?line)\s*(?:=|:)?\s*(?P<start>\d{1,7})"
        rf"(?P<middle>{not_path_chunk}{{0,160}}?)"
        r"\b(?:line[_ -]?count|count)\s*(?:=|:)?\s*(?P<count>\d{1,5})",
        re.IGNORECASE | re.DOTALL,
    )
    actions = []
    seen = set()
    def add_action(raw_path, line_start, line_count):
        path = next((item for item in allowed_paths if _work_paths_match(raw_path, item)), "")
        if not path:
            return
        try:
            line_start = int(line_start)
            line_count = int(line_count)
        except (TypeError, ValueError):
            return
        if line_start <= 0 or line_count <= 0 or line_count > 1000:
            return
        key = (path, line_start, line_count)
        if key in seen:
            return
        seen.add(key)
        actions.append(
            {
                "type": "read_file",
                "path": path,
                "line_start": line_start,
                "line_count": line_count,
                "reason": "refresh explicitly requested write-ready cached window",
            }
        )

    candidates = []
    for match in line_start_count_pattern.finditer(text):
        candidates.append(
            (
                match.start(),
                match.group("path").strip().strip("`'\""),
                match.group("start"),
                match.group("count"),
            )
        )
    for match in span_pattern.finditer(text):
        raw_path = match.group("path").strip().strip("`'\"")
        try:
            line_start = int(match.group("start"))
            line_end = int(match.group("end"))
        except (TypeError, ValueError):
            continue
        if line_start <= 0 or line_end < line_start:
            continue
        line_count = line_end - line_start + 1
        candidates.append((match.start(), raw_path, line_start, line_count))
    for _, raw_path, line_start, line_count in sorted(candidates, key=lambda item: item[0]):
        add_action(raw_path, line_start, line_count)
        if len(actions) >= 5:
            break
    if actions:
        return actions
    return _work_write_ready_explicit_refresh_search_actions(text, allowed_paths, work_session)


def _work_write_ready_explicit_refresh_search_actions(text, allowed_paths, work_session=None):
    lowered = (text or "").casefold()
    if not re.search(r"\b(refresh|read|around)\b", lowered):
        return []
    actions = []
    seen = set()
    blocked_tokens = _work_write_ready_refresh_path_query_tokens(allowed_paths)
    for path in allowed_paths:
        segment = _work_write_ready_refresh_text_segment(text, path)
        query = _work_write_ready_refresh_query(segment, blocked_tokens=blocked_tokens)
        if not query:
            continue
        if _work_write_ready_explicit_refresh_search_already_completed(
            work_session,
            path,
            query,
        ):
            continue
        if _work_write_ready_explicit_refresh_search_already_zero_match(
            work_session,
            path,
            query,
        ):
            continue
        key = (path, query)
        if key in seen:
            continue
        seen.add(key)
        actions.append(
            {
                "type": "search_text",
                "path": path,
                "query": query,
                "reason": "locate explicitly requested write-ready cached window",
            }
        )
        if len(actions) >= 5:
            break
    return actions


def _work_write_ready_explicit_refresh_search_already_completed(work_session, path, query):
    if not isinstance(work_session, dict):
        return False
    for collection_name in ("explicit_refresh_search_tool_calls", "tool_calls"):
        for call in work_session.get(collection_name) or []:
            if not isinstance(call, dict):
                continue
            if call.get("tool") != "search_text" or str(call.get("status") or "") != "completed":
                continue
            parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
            if str(parameters.get("reason") or "") != "locate explicitly requested write-ready cached window":
                continue
            if not _work_paths_match(parameters.get("path"), path):
                continue
            if str(parameters.get("query") or "") != str(query or ""):
                continue
            return True
    return False


def _work_write_ready_refresh_path_query_tokens(paths):
    tokens = set()
    for path in paths or []:
        raw_path = str(path or "").strip()
        if not raw_path:
            continue
        path_obj = Path(raw_path)
        for raw_token in (
            raw_path,
            path_obj.name,
            path_obj.stem,
            *path_obj.parts,
            *re.split(r"[^A-Za-z0-9_]+", raw_path),
        ):
            token = str(raw_token or "").strip().strip("_")
            if token:
                tokens.add(token.casefold())
    return tokens


def _work_write_ready_explicit_refresh_search_already_zero_match(work_session, path, query):
    if not isinstance(work_session, dict):
        return False
    for collection_name in ("explicit_refresh_search_tool_calls", "tool_calls"):
        for call in work_session.get(collection_name) or []:
            if not isinstance(call, dict):
                continue
            if call.get("tool") != "search_text" or str(call.get("status") or "") != "completed":
                continue
            parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
            if str(parameters.get("reason") or "") != "locate explicitly requested write-ready cached window":
                continue
            if not _work_paths_match(parameters.get("path"), path):
                continue
            if str(parameters.get("query") or "") != str(query or ""):
                continue
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            snippets = result.get("snippets")
            matches = result.get("matches")
            if isinstance(matches, list) and len(matches) == 0:
                return True
            if not isinstance(matches, list) and isinstance(snippets, list) and len(snippets) == 0:
                return True
    return False


def _work_write_ready_structural_refresh_paths(work_session):
    paths = []
    if not isinstance(work_session, dict):
        return paths
    tool_calls = []
    seen_call_ids = set()
    for collection_name in ("structural_refresh_read_tool_calls", "tool_calls"):
        for call in work_session.get(collection_name) or []:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            if call_id is not None and call_id in seen_call_ids:
                continue
            if call_id is not None:
                seen_call_ids.add(call_id)
            tool_calls.append(call)
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        if call.get("tool") != "read_file" or str(call.get("status") or "") != "completed":
            continue
        parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
        if str(parameters.get("reason") or "") != "refresh structurally incomplete write-ready cached window":
            continue
        path = str(parameters.get("path") or "").strip()
        if path and not any(_work_paths_match(path, existing) for existing in paths):
            paths.append(path)
    return paths


def _work_write_ready_structural_refresh_exhausted_for_paths(work_session, target_paths):
    target_paths = [str(path or "").strip() for path in target_paths or [] if str(path or "").strip()]
    if not target_paths:
        return False
    refreshed_paths = _work_write_ready_structural_refresh_paths(work_session)
    if not refreshed_paths:
        return False
    return all(
        any(_work_paths_match(path, refreshed_path) for refreshed_path in refreshed_paths)
        for path in target_paths
    )


def _work_write_ready_refresh_search_result_read_actions(work_session, target_paths):
    work_session = work_session if isinstance(work_session, dict) else {}
    tool_calls = []
    seen_call_ids = set()
    for collection_name in ("explicit_refresh_search_tool_calls", "tool_calls"):
        for call in work_session.get(collection_name) or []:
            if not isinstance(call, dict):
                continue
            call_id = call.get("id")
            if call_id is not None and call_id in seen_call_ids:
                continue
            if call_id is not None:
                seen_call_ids.add(call_id)
            tool_calls.append(call)
    target_paths = [str(path or "").strip() for path in target_paths or [] if str(path or "").strip()]
    for call in tool_calls:
        if call.get("tool") != "search_text" or str(call.get("status") or "") != "completed":
            continue
        parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
        if str(parameters.get("reason") or "") != "locate explicitly requested write-ready cached window":
            continue
        path = str(parameters.get("path") or "").strip()
        if path and not any(_work_paths_match(path, existing) for existing in target_paths):
            target_paths.append(path)
    if not target_paths:
        return []

    def usable_anchor_search(call):
        if not isinstance(call, dict) or call.get("tool") != "search_text":
            return False
        if str(call.get("status") or "") != "completed":
            return False
        parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
        reason = str(parameters.get("reason") or "").strip()
        return reason in ("", "locate explicitly requested write-ready cached window")

    recent_windows = [
        item
        for item in (work_session.get("recent_read_file_windows") or [])
        if isinstance(item, dict) and item.get("path")
    ]

    def anchor_proximity_score(path, anchor_line):
        try:
            anchor_line = int(anchor_line or 0)
        except (TypeError, ValueError):
            anchor_line = 0
        if anchor_line <= 0:
            return 0
        best = 0
        for window in recent_windows:
            if not _work_paths_match(window.get("path"), path):
                continue
            try:
                window_start = int(window.get("line_start") or 0)
                window_end = int(window.get("line_end") or 0)
            except (TypeError, ValueError):
                continue
            if window_start <= 0 or window_end < window_start:
                continue
            if window_start <= anchor_line <= window_end:
                return 100
            distance = min(abs(anchor_line - window_start), abs(anchor_line - window_end))
            if distance <= 250:
                best = max(best, 50 - min(distance // 10, 49))
        return best

    def already_read(path, line_start, line_end):
        for window in recent_windows:
            if not _work_paths_match(window.get("path"), path):
                continue
            try:
                window_start = int(window.get("line_start") or 0)
                window_end = int(window.get("line_end") or 0)
            except (TypeError, ValueError):
                continue
            if window_start <= line_start and window_end >= line_end:
                if window.get("text") and not window.get("context_truncated"):
                    return True
        return False

    def snippet_anchor(snippet):
        if not isinstance(snippet, dict):
            return (0, 0)
        try:
            anchor_line = int(snippet.get("line") or snippet.get("start_line") or 0)
        except (TypeError, ValueError):
            anchor_line = 0
        if anchor_line <= 0:
            return (0, 0)
        match_text = ""
        for line in snippet.get("lines") or []:
            if not isinstance(line, dict):
                continue
            try:
                line_number = int(line.get("line") or 0)
            except (TypeError, ValueError):
                line_number = 0
            if line.get("match") or line_number == anchor_line:
                match_text = str(line.get("text") or "")
                break
        stripped = match_text.strip()
        score = 1
        if stripped.startswith(("def ", "async def ", "class ")):
            score += 5
        if stripped.startswith("def test_"):
            score += 2
        if "\"query\"" in stripped or "'query'" in stripped:
            score -= 3
        return (score, anchor_line)

    actions = []
    for target_path in target_paths:
        candidate_anchors = []
        for call in reversed(tool_calls):
            if not usable_anchor_search(call):
                continue
            parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
            if not _work_paths_match(parameters.get("path"), target_path):
                continue
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            snippets = result.get("snippets") if isinstance(result.get("snippets"), list) else []
            if not snippets:
                if not any(_work_paths_match(window.get("path"), target_path) for window in recent_windows):
                    break
                continue
            for snippet in snippets:
                if not isinstance(snippet, dict) or not _work_paths_match(snippet.get("path"), target_path):
                    continue
                score, line = snippet_anchor(snippet)
                score += anchor_proximity_score(target_path, line)
                if line > 0:
                    candidate_anchors.append((score, line))
        if not candidate_anchors:
            continue

        anchor_lines = {line for _, line in candidate_anchors if line > 0}

        def read_window_bounds(anchor_line):
            line_start = max(1, anchor_line - 120)
            line_count = 520
            line_end = line_start + line_count - 1
            return line_start, line_count, line_end

        def window_anchor_coverage(anchor_line):
            line_start, _, line_end = read_window_bounds(anchor_line)
            return sum(1 for line in anchor_lines if line_start <= line <= line_end)

        ranked_candidates = sorted(
            candidate_anchors,
            key=lambda item: (item[0] + 20 * window_anchor_coverage(item[1]), -item[1]),
            reverse=True,
        )
        for _, anchor_line in ranked_candidates:
            line_start, line_count, line_end = read_window_bounds(anchor_line)
            if already_read(target_path, line_start, line_end):
                continue
            actions.append(
                {
                    "type": "read_file",
                    "path": target_path,
                    "line_start": line_start,
                    "line_count": line_count,
                    "reason": "read explicitly located write-ready cached window",
                }
            )
            break
        if len(actions) >= 5:
            break
    return actions


def _work_write_ready_cached_window_refresh_read_actions(work_session, cached_windows):
    recent_windows = [
        item
        for item in (work_session or {}).get("recent_read_file_windows") or []
        if isinstance(item, dict) and item.get("path")
    ]
    tool_calls_by_id = {
        call.get("id"): call
        for call in (work_session or {}).get("tool_calls") or []
        if isinstance(call, dict) and call.get("id") is not None
    }

    def came_from_structural_refresh(cached):
        call = tool_calls_by_id.get((cached or {}).get("tool_call_id"))
        parameters = call.get("parameters") if isinstance(call, dict) else {}
        if not isinstance(parameters, dict):
            return False
        return str(parameters.get("reason") or "") == "refresh structurally incomplete write-ready cached window"

    def already_read(path, line_start, line_end):
        for window in recent_windows:
            if not _work_paths_match(window.get("path"), path):
                continue
            try:
                window_start = int(window.get("line_start") or 0)
                window_end = int(window.get("line_end") or 0)
            except (TypeError, ValueError):
                continue
            if window_start <= line_start and window_end >= line_end:
                if window.get("text") and not window.get("context_truncated"):
                    return True
        return False

    actions = []
    seen = set()
    structurally_refreshed_paths = _work_write_ready_structural_refresh_paths(work_session)
    for cached in cached_windows or []:
        if not isinstance(cached, dict):
            continue
        if came_from_structural_refresh(cached):
            continue
        path = str(cached.get("path") or "").strip()
        if not path:
            continue
        if any(_work_paths_match(path, existing) for existing in structurally_refreshed_paths):
            continue
        try:
            cached_start = int(cached.get("line_start") or 0)
            cached_end = int(cached.get("line_end") or 0)
        except (TypeError, ValueError):
            continue
        if cached_start <= 0 or cached_end < cached_start:
            continue
        cached_span = cached_end - cached_start + 1
        if cached_span > 1000:
            continue
        top_broad_next_line = cached.get("next_line")
        if top_broad_next_line is not None:
            try:
                top_broad_next_line = int(top_broad_next_line)
            except (TypeError, ValueError):
                top_broad_next_line = None
        if top_broad_next_line is None:
            for window in recent_windows:
                if not _work_paths_match(window.get("path"), path):
                    continue
                if window.get("line_start") != cached_start or window.get("line_end") != cached_end:
                    continue
                try:
                    top_broad_next_line = int(window.get("next_line"))
                except (TypeError, ValueError):
                    pass
                break

        if cached_start == 1 and cached_span >= 1000 and top_broad_next_line:
            line_start = max(1, top_broad_next_line)
            line_count = 1000
        else:
            line_start = max(1, cached_start - 120)
            line_count = max(520, cached_end - line_start + 121)
            if line_count > 1000:
                line_count = 1000
                min_start_to_cover_ref = max(1, cached_end - line_count + 1)
                line_start = min(max(line_start, min_start_to_cover_ref), cached_start)
        line_end = line_start + line_count - 1
        key = (path, line_start, line_count)
        if key in seen or already_read(path, line_start, line_end):
            continue
        seen.add(key)
        actions.append(
            {
                "type": "read_file",
                "path": path,
                "line_start": line_start,
                "line_count": line_count,
                "reason": "refresh structurally incomplete write-ready cached window",
            }
        )
        if len(actions) >= 5:
            break
    return actions


def _work_write_ready_refresh_text_segment(text, path):
    text = text or ""
    path = str(path or "").strip()
    if _work_batch_path_is_mew_source(path):
        match = re.search(r"\bsource\s+around\s+(?P<cues>[^.;\n]+)", text, re.IGNORECASE)
        if match:
            return match.group("cues")
    if _work_batch_path_is_tests(path):
        match = re.search(r"\btests?\s+around\s+(?P<cues>[^.;\n]+)", text, re.IGNORECASE)
        if match:
            return match.group("cues")

    lowered = text.casefold()
    path_index = lowered.find(path.casefold()) if path else -1
    if path_index >= 0:
        start = max(0, path_index - 240)
        end = min(len(text), path_index + len(path) + 240)
        return text[start:end]
    return text


def _work_write_ready_refresh_query(text, blocked_tokens=None):
    stopwords = {
        "and",
        "around",
        "before",
        "cached",
        "cases",
        "complete",
        "decision",
        "draft",
        "drafting",
        "exact",
        "finish",
        "helpers",
        "line",
        "lines",
        "read",
        "read_file",
        "refresh",
        "source",
        "search_text",
        "structurally",
        "targeted",
        "tests",
        "the",
        "window",
        "windows",
        "write_file",
        "edit_file",
        "edit_file_hunks",
    }
    stopwords |= {
        str(token or "").strip().strip("_").casefold()
        for token in (blocked_tokens or [])
        if str(token or "").strip().strip("_")
    }
    candidates = []
    for match in re.finditer(r"[A-Za-z_][A-Za-z0-9_]{2,}", text or ""):
        token = match.group(0).strip("_")
        lowered = token.casefold()
        if lowered in stopwords:
            continue
        if lowered in {"src", "mew", "py", "test", "tests", "work", "session"}:
            continue
        score = 0
        if "_" in token:
            score += 4
        if len(token) >= 8:
            score += 1
        if lowered.startswith(("test_", "finish_", "no_", "calibration")):
            score += 1
        candidates.append((score, match.start(), token))
    if not candidates:
        return ""
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][2]


def _work_write_ready_guidance_forbids_widening(context, resume):
    text_parts = []
    guidance = str((context or {}).get("guidance") or "").strip()
    if guidance:
        text_parts.append(guidance)
    pending_steer = (resume or {}).get("pending_steer")
    if isinstance(pending_steer, dict):
        steer_text = str(pending_steer.get("text") or "").strip()
        if steer_text:
            text_parts.append(steer_text)
    text = "\n".join(text_parts).casefold()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "do not widen",
            "don't widen",
            "no widening",
        )
    )


def _work_write_ready_guidance_forbids_refresh(context, resume):
    text_parts = []
    guidance = str((context or {}).get("guidance") or "").strip()
    if guidance:
        text_parts.append(guidance)
    pending_steer = (resume or {}).get("pending_steer")
    if isinstance(pending_steer, dict):
        steer_text = str(pending_steer.get("text") or "").strip()
        if steer_text:
            text_parts.append(steer_text)
    text = "\n".join(text_parts).casefold()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "do not refresh",
            "don't refresh",
            "no refresh",
            "do not reread",
            "don't reread",
            "no reread",
            "do not read again",
            "don't read again",
        )
    )


def _work_write_ready_guidance_requests_refresh_before_draft(context, resume):
    text_parts = []
    guidance = str((context or {}).get("guidance") or "").strip()
    if guidance:
        text_parts.append(guidance)
    pending_steer = (resume or {}).get("pending_steer")
    if isinstance(pending_steer, dict):
        steer_text = str(pending_steer.get("text") or "").strip()
        if steer_text:
            text_parts.append(steer_text)
    text = "\n".join(text_parts).casefold()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "read-only",
            "read only",
            "do not draft",
            "don't draft",
            "no draft",
            "just cache",
            "read_file",
            "first read",
            "read exact",
            "exact source text",
            "recover missing exact",
            "before any patch attempt",
            "before any patch",
        )
    )


def _work_write_ready_explicit_refresh_before_tiny_draft(context, write_ready_fast_path):
    fast_path = write_ready_fast_path if isinstance(write_ready_fast_path, dict) else {}
    if not fast_path.get("active"):
        return {}
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    if not _work_write_ready_guidance_requests_refresh_before_draft(context, resume):
        return {}
    target_paths = _write_ready_tiny_draft_observation_target_paths(resume)
    if not target_paths:
        active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
        source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
        target_paths = _write_ready_paired_target_paths(source.get("target_paths") or [])
    if not target_paths:
        target_paths = _write_ready_paired_target_paths(
            [item.get("path") for item in (fast_path.get("recent_windows") or fast_path.get("cached_windows") or [])]
        )
    if not target_paths:
        return {}
    refresh_actions = _work_write_ready_explicit_refresh_read_actions(context, target_paths)
    if not refresh_actions:
        return {}
    action = {
        "type": "batch",
        "tools": refresh_actions,
        "reason": "write-ready active fast path: refresh explicitly requested windows before tiny draft",
    }
    decision_plan = {
        "summary": action["reason"],
        "working_memory": {
            "hypothesis": "The current guidance asks to refresh exact cached windows before drafting.",
            "next_step": "Retry the paired dry-run draft after these exact windows are cached.",
            "plan_items": [
                "Refresh the explicitly requested exact windows.",
                "Retry the paired tiny draft after the refreshed windows are available.",
            ],
            "target_paths": target_paths,
            "last_verified_state": "Write-ready fast path was active, but refresh-before-draft guidance takes precedence.",
        },
    }
    return {
        "decision_plan": decision_plan,
        "action_plan": {
            "summary": action["reason"],
            "action": action,
            "act_mode": "deterministic",
        },
        "action": action,
        "cached_windows_for_replay": fast_path.get("recent_windows") or fast_path.get("cached_windows") or [],
    }


def _work_rejection_frontier_active_reviewer_rejection(context):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    resume = (work_session or {}).get("resume") if isinstance((work_session or {}).get("resume"), dict) else {}
    frontier = (
        resume.get("active_rejection_frontier")
        if isinstance(resume.get("active_rejection_frontier"), dict)
        else {}
    )
    if str(frontier.get("status") or "active") != "active":
        return {}
    if str(frontier.get("drift_class") or "") != "reviewer_rejected_patch":
        return {}
    return frontier


def _work_rejection_frontier_call_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _work_rejection_frontier_has_recovery_read_after(context, frontier):
    source_call_id = _work_rejection_frontier_call_id((frontier or {}).get("source_tool_call_id"))
    if source_call_id is None:
        return False
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    for call in (work_session or {}).get("tool_calls") or []:
        if not isinstance(call, dict):
            continue
        call_id = _work_rejection_frontier_call_id(call.get("id"))
        if call_id is None or call_id <= source_call_id:
            continue
        if str(call.get("status") or "") != "completed":
            continue
        if str(call.get("tool") or "") == "read_file":
            return True
    return False


def _work_rejection_frontier_window_read_action(item, reason):
    if not isinstance(item, dict):
        return {}
    path = str(item.get("path") or "").strip()
    if not path:
        return {}
    action = {
        "type": "read_file",
        "path": path,
        "reason": reason,
    }
    try:
        line_start = int(item.get("line_start") or 0)
        line_end = int(item.get("line_end") or 0)
    except (TypeError, ValueError):
        line_start = 0
        line_end = 0
    if line_start > 0 and line_end >= line_start:
        action["line_start"] = line_start
        action["line_count"] = line_end - line_start + 1
    return action


def _work_rejection_frontier_target_read_actions(context, write_ready_fast_path=None):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    resume = (work_session or {}).get("resume") if isinstance((work_session or {}).get("resume"), dict) else {}
    fast_path = write_ready_fast_path if isinstance(write_ready_fast_path, dict) else {}
    reason = "active reviewer rejection frontier requires a fresh read_file recovery before another write draft"
    candidates = []
    active_work_todo = (
        resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    )
    candidates.extend(active_work_todo.get("cached_window_refs") or [])
    candidates.extend(fast_path.get("recent_windows") or [])
    candidates.extend(fast_path.get("cached_windows") or [])
    for observation in resume.get("plan_item_observations") or []:
        if isinstance(observation, dict):
            candidates.extend(observation.get("cached_windows") or [])
    candidates.extend(resume.get("target_path_cached_window_observations") or [])

    actions = []
    seen = set()
    for candidate in candidates:
        action = _work_rejection_frontier_window_read_action(candidate, reason)
        if not action:
            continue
        key = (
            _normalized_work_path(action.get("path")),
            action.get("line_start"),
            action.get("line_count"),
        )
        if key in seen:
            continue
        seen.add(key)
        actions.append(action)
        if len(actions) >= 5:
            break
    if actions:
        return actions

    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    target_paths = _write_ready_paired_target_paths(source.get("target_paths") or [])
    frontier = _work_rejection_frontier_active_reviewer_rejection(context)
    frontier_path = str((frontier or {}).get("path") or "").strip()
    if frontier_path and not any(_work_paths_match(frontier_path, path) for path in target_paths):
        target_paths.append(frontier_path)
    for path in target_paths[:5]:
        actions.append({"type": "read_file", "path": path, "reason": reason})
    return actions


def _work_rejection_frontier_recovery_action(context, write_ready_fast_path=None):
    frontier = _work_rejection_frontier_active_reviewer_rejection(context)
    if not frontier:
        return {}
    if _work_rejection_frontier_has_recovery_read_after(context, frontier):
        return {}
    read_actions = _work_rejection_frontier_target_read_actions(context, write_ready_fast_path)
    if not read_actions:
        return {
            "type": "wait",
            "reason": "active reviewer rejection frontier requires a fresh read_file recovery before another write draft",
        }
    if len(read_actions) == 1:
        return read_actions[0]
    return {
        "type": "batch",
        "tools": read_actions,
        "reason": "active reviewer rejection frontier requires fresh read_file recovery before another write draft",
    }


def _work_action_is_write_draft(action):
    action = action if isinstance(action, dict) else {}
    action_type = str(action.get("type") or "").strip()
    if action_type in WRITE_WORK_TOOLS:
        return True
    if action_type != "batch":
        return False
    return any(
        isinstance(tool, dict) and str(tool.get("type") or "").strip() in WRITE_WORK_TOOLS
        for tool in action.get("tools") or []
    )


def _enforce_rejection_frontier_recovery_gate(context, action, write_ready_fast_path=None):
    if not _work_action_is_write_draft(action):
        return action
    recovery_action = _work_rejection_frontier_recovery_action(context, write_ready_fast_path)
    return recovery_action or action


def _work_write_ready_cached_window_incomplete_preflight_blocker(
    *,
    refresh_forbidden,
    refresh_exhausted,
):
    if refresh_forbidden:
        detail = "refresh is forbidden by current guidance and cached windows remain structurally incomplete"
    elif refresh_exhausted:
        detail = "structural refresh was already attempted for each paired target path"
    else:
        detail = "paired cached windows remain structurally incomplete before drafting"
    return {
        "kind": "patch_blocker",
        "summary": "cached windows remain structurally incomplete",
        "code": "cached_window_incomplete",
        "detail": detail,
    }


def _work_write_ready_preflight_block(context, write_ready_fast_path):
    fast_path = write_ready_fast_path if isinstance(write_ready_fast_path, dict) else {}
    if fast_path.get("active"):
        return {}
    if str(fast_path.get("reason") or "") != "insufficient_cached_window_context":
        return {}
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    observations = resume.get("plan_item_observations") or []
    first = observations[0] if observations and isinstance(observations[0], dict) else {}
    if not first.get("edit_ready"):
        return {}
    cached_windows = [
        item
        for item in (first.get("cached_windows") or [])
        if isinstance(item, dict) and item.get("path")
    ]
    if len(cached_windows) < 2:
        cached_windows = _write_ready_recent_windows_from_active_work_todo(work_session, resume)
    if len(cached_windows) < 2:
        return {}
    target_paths = []
    has_source = False
    has_tests = False
    for item in cached_windows:
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if not any(_work_paths_match(path, existing) for existing in target_paths):
            target_paths.append(path)
        has_source = has_source or _work_batch_path_is_mew_source(path)
        has_tests = has_tests or _work_batch_path_is_tests(path)
    if not (has_source and has_tests):
        return {}
    summary = (
        "Write-ready preflight blocked: paired cached windows are not structurally complete enough "
        "for a draft turn."
    )
    next_step = "Refresh the paired exact cached windows before drafting again."
    decision_plan = {
        "summary": summary,
        "working_memory": {
            "hypothesis": summary,
            "next_step": next_step,
            "plan_items": [
                next_step,
                "Retry the paired dry-run draft after the refreshed windows are exact and complete.",
            ],
            "target_paths": target_paths,
            "last_verified_state": "Drafting was preflight-blocked before a model call.",
        },
    }
    refresh_forbidden = _work_write_ready_guidance_forbids_refresh(context, resume)
    refresh_exhausted = _work_write_ready_structural_refresh_exhausted_for_paths(
        work_session,
        target_paths,
    )
    refresh_actions = []
    if not refresh_forbidden:
        refresh_actions = _work_write_ready_explicit_refresh_read_actions(context, target_paths)
    if not refresh_actions and not refresh_forbidden:
        refresh_actions = _work_write_ready_refresh_search_result_read_actions(work_session, target_paths)
    if not refresh_actions and not refresh_forbidden:
        if not _work_write_ready_guidance_forbids_widening(context, resume):
            refresh_actions = _work_write_ready_cached_window_refresh_read_actions(
                work_session,
                cached_windows,
            )
    if refresh_actions:
        action = {
            "type": "batch",
            "tools": refresh_actions,
            "reason": (
                "write-ready preflight blocker: refresh explicitly requested cached windows "
                "before drafting"
            ),
        }
    else:
        blocker = {}
        if refresh_forbidden or refresh_exhausted:
            blocker = _work_write_ready_cached_window_incomplete_preflight_blocker(
                refresh_forbidden=refresh_forbidden,
                refresh_exhausted=refresh_exhausted,
            )
        action = {
            "type": "wait",
            "reason": _stable_write_ready_tiny_draft_blocker_reason(blocker)
            if blocker
            else (
                "write-ready preflight blocker: paired cached windows are not structurally complete; "
                "refresh cached windows before drafting"
            ),
        }
        if blocker:
            decision_plan["blocker"] = blocker
    return {
        "decision_plan": decision_plan,
        "action_plan": {
            "summary": action["reason"],
            "action": action,
            "act_mode": "tiny_write_ready_draft" if decision_plan.get("blocker") else "deterministic",
            **({"blocker": decision_plan["blocker"]} if decision_plan.get("blocker") else {}),
        },
        "action": action,
        "cached_windows_for_replay": (
            write_ready_fast_path.get("recent_windows")
            if isinstance(write_ready_fast_path, dict)
            else []
        )
        or _write_ready_recent_windows_from_active_work_todo(work_session, resume)
        or cached_windows,
    }


def _shadow_compile_patch_draft_for_write_ready_turn(
    *,
    session,
    context,
    action_plan,
    action,
    write_ready_fast_path,
    allowed_write_roots=None,
):
    observation = _empty_patch_draft_compiler_observation()
    proposal = _write_ready_patch_draft_proposal_from_action(
        action_plan=action_plan,
        action=action,
    )
    if not proposal:
        observation["patch_draft_compiler_artifact_kind"] = "unadapted"
        return observation
    return _compile_write_ready_patch_draft_proposal(
        session=session,
        context=context,
        proposal=proposal,
        write_ready_fast_path=write_ready_fast_path,
        allowed_write_roots=allowed_write_roots,
    ).get("observation") or observation


def _write_ready_patch_draft_environment(
    *,
    session,
    context,
    write_ready_fast_path,
    todo_id_override="",
):
    raw_cwd = (((context or {}).get("task") or {}).get("cwd") or ".")
    workspace_root = Path(raw_cwd).expanduser()
    if not workspace_root.is_absolute():
        workspace_root = Path.cwd() / workspace_root
    workspace_root = workspace_root.resolve(strict=False)

    def canonical_path(path):
        normalized = normalize_work_path(path)
        if not normalized:
            return ""

        candidate = Path(normalized)
        if candidate.is_absolute():
            try:
                return candidate.resolve(strict=False).relative_to(workspace_root).as_posix()
            except ValueError:
                return normalized
            except OSError:
                return normalized

        root_without_leading_slash = str(workspace_root).lstrip("/")
        if root_without_leading_slash and normalized.startswith(f"{root_without_leading_slash}/"):
            normalized = normalized[len(root_without_leading_slash) + 1 :]

        return normalized

    fast_path = write_ready_fast_path if isinstance(write_ready_fast_path, dict) else {}
    recent_windows = fast_path.get("recent_windows") or []
    resume = ((context or {}).get("work_session") or {}).get("resume") or {}
    active_work_todo = resume.get("active_work_todo") or (session or {}).get("active_work_todo") or {}
    todo_source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    target_paths = []
    for path in todo_source.get("target_paths") or []:
        normalized_path = canonical_path(path)
        if normalized_path:
            target_paths.append(normalized_path)
    if not target_paths:
        working_memory = resume.get("working_memory") if isinstance(resume.get("working_memory"), dict) else {}
        for path in working_memory.get("target_paths") or []:
            normalized_path = canonical_path(path)
            if normalized_path:
                target_paths.append(normalized_path)
    if not target_paths:
        for item in recent_windows:
            if not isinstance(item, dict):
                continue
            normalized_path = canonical_path(item.get("path"))
            if normalized_path:
                target_paths.append(normalized_path)
    todo = {
        "id": str(active_work_todo.get("id") or todo_id_override or "").strip(),
        "lane": str(active_work_todo.get("lane") or "").strip() or "tiny",
        "source": {
            "target_paths": target_paths,
            "required_terms": _write_ready_task_goal_required_terms(context, resume),
        },
    }
    cached_windows = {}
    for window in recent_windows:
        if not isinstance(window, dict):
            continue
        path = canonical_path(window.get("path"))
        if not path:
            continue
        cached_window = {
            "path": path,
            "line_start": window.get("line_start"),
            "line_end": window.get("line_end"),
            "text": window.get("text") or "",
            "context_truncated": bool(window.get("context_truncated")),
        }
        if window.get("window_sha256"):
            cached_window["window_sha256"] = window.get("window_sha256")
        if window.get("file_sha256"):
            cached_window["file_sha256"] = window.get("file_sha256")
        cached_windows.setdefault(path, []).append(cached_window)

    live_files = {}
    for path in cached_windows:
        file_path = Path(path)
        if not file_path.exists():
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = file_path.read_bytes().decode("utf-8", errors="replace")
        live_files[path] = {
            "text": text,
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    return {
        "todo": todo,
        "cached_windows": cached_windows,
        "live_files": live_files,
    }


def _write_ready_patch_draft_proposal_from_action(
    *,
    action_plan,
    action,
):
    action = action if isinstance(action, dict) else {}
    action_plan = action_plan if isinstance(action_plan, dict) else {}
    summary = (
        str(action_plan.get("summary") or action.get("summary") or action.get("reason") or "").strip()
        or "shadow write-ready compiler proposal"
    )
    action_type = str(action.get("type") or "").strip()
    if action_type == "batch":
        candidate_tools = action.get("tools") or []
    elif action_type in {"edit_file", "edit_file_hunks"}:
        candidate_tools = [action]
    else:
        return None

    proposal_files = []
    for tool in candidate_tools:
        if not isinstance(tool, dict):
            return None
        tool_type = str(tool.get("type") or "").strip()
        path = normalize_work_path(tool.get("path"))
        if not path:
            return None
        if tool_type == "edit_file":
            old = tool.get("old")
            new = tool.get("new")
            if not isinstance(old, str) or old == "" or not isinstance(new, str):
                return None
            proposal_files.append({"path": path, "edits": [{"old": old, "new": new}]})
            continue
        if tool_type == "edit_file_hunks":
            edits = tool.get("edits")
            valid_edits = (
                isinstance(edits, list)
                and bool(edits)
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("old"), str)
                    and item.get("old") != ""
                    and isinstance(item.get("new"), str)
                    for item in edits
                )
            )
            if not valid_edits:
                return None
            proposal_files.append(
                {
                    "path": path,
                    "edits": [{"old": item.get("old"), "new": item.get("new")} for item in edits],
                }
            )
            continue
        return None

    return {
        "kind": "patch_proposal",
        "summary": summary,
        "files": proposal_files,
    }


def _work_loop_patch_blocker_describes_no_material_change(proposal):
    proposal = proposal if isinstance(proposal, dict) else {}
    code = str(proposal.get("code") or "").strip()
    if not code or code in PATCH_BLOCKER_RECOVERY_ACTIONS:
        return False
    text = re.sub(
        r"\s+",
        " ",
        " ".join(
            str(proposal.get(field) or "")
            for field in ("summary", "detail", "reason")
            if proposal.get(field) is not None
        ),
    ).casefold()
    if not text:
        return False
    uncertainty_pattern = re.compile(
        r"\b(?:whether|may|might|could|uncertain|unsure|not sure)\b"
        r"|\b(?:before deciding|deciding whether|decide whether)\b"
        r"|\bneed(?:s|ed)?\b.{0,80}\b(?:before|decid|whether|exact cached|"
        r"cached windows|inspect|check|review|verify|read|fetch|refresh)\b"
        r"|\bshould\s+(?:inspect|check|review|verify|read|fetch|refresh|decide)\b"
    )
    if uncertainty_pattern.search(text):
        return False
    conclusion_pattern = re.compile(
        r"\bno concrete code change (?:was |is )?specified\b"
        r"|\bno concrete code change to draft\b"
        r"|\bno concrete change to draft\b"
        r"|\bno concrete draftable change\b"
        r"|\bno material change remains?\b"
        r"|\bnothing to change\b"
        r"|\bno draftable change remains?\b"
    )
    return bool(conclusion_pattern.search(text))


def _normalize_work_loop_patch_blocker_proposal(proposal):
    proposal = proposal if isinstance(proposal, dict) else {}
    if str(proposal.get("kind") or "").strip() != "patch_blocker":
        return proposal
    if not _work_loop_patch_blocker_describes_no_material_change(proposal):
        return proposal
    normalized = dict(proposal)
    normalized["code"] = "no_material_change"
    if not str(normalized.get("detail") or "").strip():
        normalized["detail"] = (
            str(proposal.get("summary") or proposal.get("reason") or "").strip()
            or "model reported no concrete draftable change"
        )
    return normalized


def _compile_write_ready_patch_draft_proposal(
    *,
    session,
    context,
    proposal,
    write_ready_fast_path,
    allowed_write_roots=None,
    todo_id_override="",
):
    observation = _empty_patch_draft_compiler_observation()
    proposal = proposal if isinstance(proposal, dict) else {}
    proposal = _normalize_work_loop_patch_blocker_proposal(proposal)
    environment = _write_ready_patch_draft_environment(
        session=session,
        context=context,
        write_ready_fast_path=write_ready_fast_path,
        todo_id_override=todo_id_override,
    )
    todo = environment.get("todo") or {}
    cached_windows = environment.get("cached_windows") or {}
    live_files = environment.get("live_files") or {}
    validator_result = {}
    preview_result = None
    previews = []
    try:
        validator_result = compile_patch_draft(
            todo=todo,
            proposal=proposal,
            cached_windows=cached_windows,
            live_files=live_files,
            allowed_write_roots=allowed_write_roots or [],
        )
        observation["patch_draft_compiler_ran"] = True
        observation["patch_draft_compiler_artifact_kind"] = str(validator_result.get("kind") or "").strip()
        if observation["patch_draft_compiler_artifact_kind"] == "patch_draft":
            preview_result = compile_patch_draft_previews(
                validator_result,
                allowed_write_roots=allowed_write_roots or [],
            )
            if isinstance(preview_result, list):
                previews = preview_result
        replay_path = write_patch_draft_compiler_replay(
            session_id=(session or {}).get("id"),
            todo_id=todo.get("id") or "",
            todo=todo,
            proposal=proposal,
            cached_windows=cached_windows,
            live_files=live_files,
            allowed_write_roots=list(allowed_write_roots or []),
            validator_result=validator_result,
        )
        if replay_path:
            observation["patch_draft_compiler_replay_path"] = str(Path(replay_path).resolve())
    except Exception as exc:
        observation["patch_draft_compiler_artifact_kind"] = "exception"
        observation["patch_draft_compiler_replay_path"] = ""
        observation["patch_draft_compiler_error"] = clip_output(str(exc), 500)
    return {
        "observation": observation,
        "validator_result": validator_result,
        "preview_result": preview_result,
        "previews": previews,
    }


def _attempt_write_ready_tiny_draft_turn(
    *,
    session,
    context,
    tiny_context,
    write_ready_fast_path,
    model_auth,
    model,
    base_url,
    model_backend,
    timeout,
    allowed_write_roots=None,
    reasoning_effort="",
    reasoning_effort_source="",
    current_time="",
    think_kwargs=None,
):
    prompt = build_work_write_ready_tiny_draft_prompt(tiny_context)
    timeout_seconds = _write_ready_tiny_draft_timeout(timeout)
    tiny_reasoning_metrics = _tiny_write_ready_draft_reasoning_metrics(
        reasoning_effort,
        reasoning_effort_source,
    )
    tiny_write_ready_draft_reasoning_effort = tiny_reasoning_metrics[
        "tiny_write_ready_draft_reasoning_effort"
    ]
    metrics = {
        "tiny_write_ready_draft_attempted": True,
        "tiny_write_ready_draft_outcome": "",
        "tiny_write_ready_draft_prompt_chars": len(prompt),
        "tiny_write_ready_draft_timeout_seconds": timeout_seconds,
        **tiny_reasoning_metrics,
        "tiny_write_ready_draft_fallback_reason": "",
        "tiny_write_ready_draft_error": "",
        "tiny_write_ready_draft_compiler_artifact_kind": "",
        "tiny_write_ready_draft_elapsed_seconds": 0.0,
        "tiny_write_ready_draft_timeout_budget_utilization": 0.0,
        "tiny_write_ready_draft_exit_stage": "",
    }
    started = time.monotonic()
    tiny_write_ready_todo_id = _work_loop_active_todo_id_from_context(context)

    def _finalize_tiny_draft_metrics(exit_stage):
        elapsed_seconds = time.monotonic() - started
        metrics["tiny_write_ready_draft_elapsed_seconds"] = elapsed_seconds
        metrics["tiny_write_ready_draft_timeout_budget_utilization"] = (
            elapsed_seconds / timeout_seconds if timeout_seconds else 0.0
        )
        metrics["tiny_write_ready_draft_exit_stage"] = exit_stage
        return elapsed_seconds

    try:
        with codex_reasoning_effort_scope(tiny_write_ready_draft_reasoning_effort):
            decision_plan = call_model_json_with_retries(
                model_backend,
                model_auth,
                prompt,
                model,
                base_url,
                timeout_seconds,
                log_prefix=f"{current_time}: work_write_ready_tiny_draft {model_backend} session={session.get('id')}",
                **(think_kwargs or {}),
            )
    except Exception as exc:
        if _work_model_error_looks_like_refusal(exc):
            refusal_detail = clip_output(str(exc), 500)
            blocker_payload = _work_loop_tiny_write_ready_draft_blocker_payload(
                {
                    "code": "model_returned_refusal",
                    "detail": refusal_detail,
                    "todo_id": tiny_write_ready_todo_id,
                }
            )
            action = {
                "type": "wait",
                "reason": _stable_write_ready_tiny_draft_blocker_reason(blocker_payload),
            }
            action_plan = {
                "summary": refusal_detail or action["reason"],
                "action": action,
                "act_mode": "tiny_write_ready_draft",
                "blocker": blocker_payload,
            }
            if tiny_write_ready_todo_id:
                action_plan["todo_id"] = tiny_write_ready_todo_id
            metrics["tiny_write_ready_draft_outcome"] = "blocker"
            metrics["tiny_write_ready_draft_fallback_reason"] = ""
            metrics["tiny_write_ready_draft_error"] = refusal_detail
            return {
                "status": "blocker",
                "decision_plan": {
                    "summary": refusal_detail or action_plan["summary"],
                },
                "action_plan": action_plan,
                "action": action,
                "metrics": metrics,
                "elapsed_seconds": _finalize_tiny_draft_metrics("model_exception_refusal"),
                "compiler_observed": False,
            }

        if _work_model_error_looks_like_timeout(exc):
            decision_plan, action_plan, action = _work_loop_write_ready_timeout_blocker_plan(
                todo_id=tiny_write_ready_todo_id,
                exc=exc,
            )
            metrics["tiny_write_ready_draft_outcome"] = "blocker"
            metrics["tiny_write_ready_draft_fallback_reason"] = ""
            metrics["tiny_write_ready_draft_error"] = clip_output(str(exc), 500)
            return {
                "status": "blocker",
                "decision_plan": decision_plan,
                "action_plan": action_plan,
                "action": action,
                "metrics": metrics,
                "elapsed_seconds": _finalize_tiny_draft_metrics(
                    "model_exception_timeout_blocker"
                ),
                "compiler_observed": False,
            }

        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_exit_stage"] = "model_exception"
        metrics["tiny_write_ready_draft_fallback_reason"] = "error"
        metrics["tiny_write_ready_draft_error"] = clip_output(str(exc), 500)
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("model_exception"),
            "compiler_observed": False,
        }

    if not isinstance(decision_plan, dict):
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = "invalid_shape"
        metrics["tiny_write_ready_draft_exit_stage"] = "non_dict_response"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("non_dict_response"),
            "compiler_observed": False,
        }

    proposal_kind = str(decision_plan.get("kind") or "").strip()
    if proposal_kind not in {"patch_proposal", "patch_blocker"}:
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = "invalid_shape"
        metrics["tiny_write_ready_draft_exit_stage"] = "unknown_kind"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("unknown_kind"),
            "compiler_observed": False,
        }

    compiled = _compile_write_ready_patch_draft_proposal(
        session=session,
        context=context,
        proposal=decision_plan,
        write_ready_fast_path=write_ready_fast_path,
        allowed_write_roots=allowed_write_roots,
    )
    observation = compiled.get("observation") or _empty_patch_draft_compiler_observation()
    metrics["tiny_write_ready_draft_compiler_artifact_kind"] = (
        observation.get("patch_draft_compiler_artifact_kind") or ""
    )
    if observation.get("patch_draft_compiler_error"):
        metrics["tiny_write_ready_draft_error"] = observation.get("patch_draft_compiler_error") or ""
    if any(observation.get(key) for key in observation):
        metrics.update(observation)
    compiler_observed = bool(
        observation.get("patch_draft_compiler_artifact_kind")
        or observation.get("patch_draft_compiler_ran")
        or observation.get("patch_draft_compiler_replay_path")
        or observation.get("patch_draft_compiler_error")
    )
    validator_result = compiled.get("validator_result") or {}
    if proposal_kind == "patch_blocker":
        code = str(validator_result.get("code") or "").strip()
        if validator_result.get("kind") != "patch_blocker" or not code or code == "model_returned_non_schema":
            metrics["tiny_write_ready_draft_outcome"] = "fallback"
            metrics["tiny_write_ready_draft_fallback_reason"] = "invalid_shape"
            return {
                "status": "fallback",
                "metrics": metrics,
                "elapsed_seconds": _finalize_tiny_draft_metrics("blocker_invalid_shape"),
                "compiler_observed": compiler_observed,
            }
        action = {
            "type": "wait",
            "reason": _stable_write_ready_tiny_draft_blocker_reason(validator_result),
        }
        blocker_payload = _work_loop_tiny_write_ready_draft_blocker_payload(validator_result)
        action_plan = {
            "summary": decision_plan.get("summary") or validator_result.get("detail") or action["reason"],
            "action": action,
            "act_mode": "tiny_write_ready_draft",
            "blocker": blocker_payload,
        }
        if tiny_write_ready_todo_id:
            action_plan["todo_id"] = tiny_write_ready_todo_id
        metrics["tiny_write_ready_draft_outcome"] = "blocker"
        metrics["tiny_write_ready_draft_exit_stage"] = "blocker_accepted"
        return {
            "status": "blocker",
            "decision_plan": decision_plan,
            "action_plan": action_plan,
            "action": action,
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("blocker_accepted"),
            "compiler_observed": compiler_observed,
        }

    compiler_kind = str(validator_result.get("kind") or "").strip()
    if compiler_kind != "patch_draft":
        code = str(validator_result.get("code") or "").strip()
        if compiler_kind == "patch_blocker" and code and code != "model_returned_non_schema":
            action = {
                "type": "wait",
                "reason": _stable_write_ready_tiny_draft_blocker_reason(validator_result),
            }
            blocker_payload = _work_loop_tiny_write_ready_draft_blocker_payload(validator_result)
            action_plan = {
                "summary": decision_plan.get("summary") or validator_result.get("detail") or action["reason"],
                "action": action,
                "act_mode": "tiny_write_ready_draft",
                "blocker": blocker_payload,
            }
            if tiny_write_ready_todo_id:
                action_plan["todo_id"] = tiny_write_ready_todo_id
            metrics["tiny_write_ready_draft_outcome"] = "blocker"
            metrics["tiny_write_ready_draft_exit_stage"] = "compiler_blocker"
            return {
                "status": "blocker",
                "decision_plan": decision_plan,
                "action_plan": action_plan,
                "action": action,
                "metrics": metrics,
                "elapsed_seconds": _finalize_tiny_draft_metrics("compiler_blocker"),
                "compiler_observed": compiler_observed,
            }
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = (
            "invalid_shape" if code == "model_returned_non_schema" else f"compiler_{code or 'unusable_output'}"
        )
        metrics["tiny_write_ready_draft_exit_stage"] = "compiler_fallback"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("compiler_fallback"),
            "compiler_observed": compiler_observed,
        }

    preview_result = compiled.get("preview_result")
    previews = list(compiled.get("previews") or [])
    if isinstance(preview_result, dict) and preview_result.get("kind") == "patch_blocker":
        code = str(preview_result.get("code") or "").strip()
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = f"preview_{code or 'patch_blocker'}"
        metrics["tiny_write_ready_draft_exit_stage"] = "preview_blocker"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("preview_blocker"),
            "compiler_observed": compiler_observed,
        }
    if not previews:
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = "preview_unusable"
        metrics["tiny_write_ready_draft_exit_stage"] = "preview_unusable"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("preview_unusable"),
            "compiler_observed": compiler_observed,
        }

    preview_action = {"type": "batch", "tools": previews} if len(previews) > 1 else dict(previews[0])
    action_plan = {
        "summary": decision_plan.get("summary") or validator_result.get("summary") or "draft write-ready preview",
        "action": preview_action,
        "act_mode": "tiny_write_ready_draft",
    }
    if tiny_write_ready_todo_id:
        action_plan["todo_id"] = tiny_write_ready_todo_id
    action = normalize_work_model_action(
        action_plan,
        allowed_write_roots=allowed_write_roots,
        default_cwd=(((context or {}).get("task") or {}).get("cwd") or ""),
    )
    if action.get("type") == "wait":
        metrics["tiny_write_ready_draft_outcome"] = "fallback"
        metrics["tiny_write_ready_draft_fallback_reason"] = "translated_preview_unusable"
        metrics["tiny_write_ready_draft_exit_stage"] = "translated_preview_unusable"
        return {
            "status": "fallback",
            "metrics": metrics,
            "elapsed_seconds": _finalize_tiny_draft_metrics("translated_preview_unusable"),
            "compiler_observed": compiler_observed,
        }
    metrics["tiny_write_ready_draft_outcome"] = "succeeded"
    metrics["tiny_write_ready_draft_exit_stage"] = "succeeded"
    return {
        "status": "succeeded",
        "decision_plan": decision_plan,
        "action_plan": action_plan,
        "action": action,
        "metrics": metrics,
        "elapsed_seconds": _finalize_tiny_draft_metrics("succeeded"),
        "compiler_observed": compiler_observed,
    }


def _write_ready_prompt_target_paths(active_work_todo, recent_windows):
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    target_paths = []
    for path in source.get("target_paths") or []:
        if not isinstance(path, str) or not path:
            continue
        if any(_work_paths_match(path, existing) for existing in target_paths):
            continue
        target_paths.append(path)
    for item in recent_windows:
        path = item.get("path")
        if not isinstance(path, str) or not path:
            continue
        if any(_work_paths_match(path, existing) for existing in target_paths):
            continue
        target_paths.append(path)
    return target_paths


def _write_ready_prompt_active_work_todo(resume, recent_windows, *, clear_refresh_blocker=False):
    resume = resume if isinstance(resume, dict) else {}
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    blocker = active_work_todo.get("blocker") if isinstance(active_work_todo.get("blocker"), dict) else {}
    attempts = active_work_todo.get("attempts") if isinstance(active_work_todo.get("attempts"), dict) else {}
    plan_item_observations = resume.get("plan_item_observations") or []
    first_observation = plan_item_observations[0] if plan_item_observations else {}
    suggested_verify_command = resume.get("suggested_verify_command") or {}
    verify_command = str(
        source.get("verify_command")
        or (
            suggested_verify_command.get("command")
            if isinstance(suggested_verify_command, dict)
            else ""
        )
        or ""
    ).strip()
    target_paths = _write_ready_prompt_target_paths(active_work_todo, recent_windows)
    status = str(active_work_todo.get("status") or "").strip()
    if not status and (target_paths or first_observation.get("plan_item")):
        status = "drafting"
    if clear_refresh_blocker and _write_ready_active_todo_has_refresh_cached_window_blocker(active_work_todo):
        status = "drafting"
        blocker = {}
    plan_item = str(source.get("plan_item") or first_observation.get("plan_item") or "").strip()
    if clear_refresh_blocker and _write_ready_cached_window_refresh_plan_item(plan_item):
        plan_item = _write_ready_refreshed_draft_plan_item(resume, active_work_todo, first_observation)
    return {
        "id": str(active_work_todo.get("id") or "").strip(),
        "status": status,
        "source": {
            "plan_item": plan_item,
            "target_paths": target_paths,
            "verify_command": verify_command,
        },
        "attempts": {
            "draft": attempts.get("draft") or 0,
            "review": attempts.get("review") or 0,
        },
        "blocker": {
            "code": str(blocker.get("code") or "").strip(),
            "recovery_action": str(blocker.get("recovery_action") or "").strip(),
        },
    }


def _write_ready_tiny_draft_observation_target_paths(resume):
    resume = resume if isinstance(resume, dict) else {}
    plan_item_observations = (resume or {}).get("plan_item_observations") or []
    target_paths = []
    if isinstance(plan_item_observations, list) and plan_item_observations:
        first_observation = plan_item_observations[0]
        if isinstance(first_observation, dict):
            for item in first_observation.get("cached_windows") or []:
                path = item.get("path")
                if not isinstance(path, str) or not path:
                    continue
                if any(_work_paths_match(path, existing) for existing in target_paths):
                    continue
                target_paths.append(path)
            if not target_paths:
                target_path = first_observation.get("target_path")
                if isinstance(target_path, str) and target_path:
                    target_paths.append(target_path)
    if len(target_paths) >= 2:
        return target_paths
    active_work_todo = resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    source = active_work_todo.get("source") if isinstance(active_work_todo.get("source"), dict) else {}
    for path in source.get("target_paths") or []:
        if not isinstance(path, str) or not path:
            continue
        if any(_work_paths_match(path, existing) for existing in target_paths):
            continue
        target_paths.append(path)
    if len(target_paths) >= 2:
        has_tests = any(_work_batch_path_is_tests(path) for path in target_paths)
        has_source = any(_work_batch_path_is_mew_source(path) for path in target_paths)
        if has_tests and has_source:
            return target_paths
    return target_paths


def _write_ready_cached_window_prompt_item(item):
    item = item if isinstance(item, dict) else {}
    draft_window = item.get("draft_window") if isinstance(item.get("draft_window"), dict) else {}
    prompt_window = draft_window if draft_window.get("text") else item
    payload = {
        "path": item.get("path") or prompt_window.get("path"),
        "line_start": prompt_window.get("line_start"),
        "line_end": prompt_window.get("line_end"),
        "tool_call_id": item.get("tool_call_id") or prompt_window.get("tool_call_id"),
        "text": prompt_window.get("text") or "",
    }
    if draft_window:
        payload["source_line_start"] = item.get("line_start")
        payload["source_line_end"] = item.get("line_end")
        payload["source_text_chars"] = item.get("source_text_chars")
        payload["draft_window_reason"] = draft_window.get("narrowed_reason") or ""
    return payload


def _write_ready_tiny_cached_window_prompt_item(item):
    item = item if isinstance(item, dict) else {}
    draft_window = item.get("draft_window") if isinstance(item.get("draft_window"), dict) else {}
    prompt_window = draft_window if draft_window.get("text") else item
    return {
        "path": item.get("path") or prompt_window.get("path"),
        "text": prompt_window.get("text") or "",
    }


def build_write_ready_work_model_context(context):
    fast_path = _work_write_ready_fast_path_details(context)
    if not fast_path.get("active"):
        return {}
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") or {}
    recent_windows = fast_path.get("recent_windows") or []
    clear_refresh_blocker = bool(
        fast_path.get("activation_source") == "active_work_todo_complete_reads"
        and _write_ready_refresh_blocker_cleared_by_complete_windows(
            resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {},
            recent_windows,
        )
    )
    active_work_todo = _write_ready_prompt_active_work_todo(
        resume,
        recent_windows,
        clear_refresh_blocker=clear_refresh_blocker,
    )
    capabilities = (context or {}).get("capabilities") or {}
    target_paths = list(((active_work_todo.get("source") or {}).get("target_paths") or []))
    failed_patch_repair = _write_ready_failed_patch_repair_for_targets(resume, target_paths)
    required_terms = _write_ready_task_goal_required_terms(context, resume)
    result = {
        "current_run": work_session.get("current_run") or {},
        "active_work_todo": active_work_todo,
        "write_ready_fast_path": {
            "active": True,
            "reason": "paired cached windows are edit-ready; draft one dry-run batch or report one exact blocker",
            "activation_source": fast_path.get("activation_source") or "plan_item_observations",
            "cached_window_texts": [
                _write_ready_cached_window_prompt_item(item)
                for item in recent_windows
            ],
        },
        "task_goal": {
            "required_terms": required_terms,
        },
        "allowed_roots": {
            "read": capabilities.get("allowed_read_roots") or [],
            "write": capabilities.get("allowed_write_roots") or [],
        },
        "focused_verify_command": str(((active_work_todo.get("source") or {}).get("verify_command") or "")).strip(),
    }
    if failed_patch_repair:
        result["failed_patch_repair"] = failed_patch_repair
    retry_context = resume.get("retry_context") if isinstance(resume.get("retry_context"), dict) else {}
    if retry_context:
        result["retry_context"] = retry_context
    return result


def build_write_ready_tiny_draft_model_context(context):
    fast_path = _work_write_ready_fast_path_details(context)
    if not fast_path.get("active"):
        return {}
    write_ready_context = build_write_ready_work_model_context(context)
    if not write_ready_context:
        return {}
    work_session = (context or {}).get("work_session") or {}
    resume = work_session.get("resume") or {}
    actionable_target_paths = _write_ready_tiny_draft_observation_target_paths(resume)
    if not actionable_target_paths:
        actionable_target_paths = [str(path or "") for path in (fast_path.get("cached_paths") or []) if str(path).strip()]
    recent_windows = fast_path.get("recent_windows") or []
    active_work_todo = write_ready_context.get("active_work_todo") or {}
    required_terms = list(((write_ready_context.get("task_goal") or {}).get("required_terms") or []))
    plan_item_observations = resume.get("plan_item_observations") or []
    first_observation = plan_item_observations[0] if plan_item_observations and isinstance(plan_item_observations[0], dict) else {}
    actionable_plan_item = ""
    active_work_todo_resume = (
        resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {}
    )
    recovered_refresh_recovery = bool(
        fast_path.get("activation_source") == "active_work_todo_complete_reads"
        and (
            _write_ready_refresh_blocker_cleared_by_complete_windows(
                active_work_todo_resume,
                recent_windows,
            )
            or _write_ready_active_todo_is_refresh_recovery(active_work_todo_resume, first_observation)
        )
    )
    def task_goal_plan_item():
        task = (context or {}).get("task") if isinstance((context or {}).get("task"), dict) else {}
        title = str(task.get("title") or "").strip()
        description = str(task.get("description") or "").strip()
        if not title and not description:
            return ""
        pieces = []
        if title:
            pieces.append(title)
        if description:
            pieces.append(description)
        return "Task goal: " + " - ".join(pieces)

    if recovered_refresh_recovery:
        actionable_plan_item = _write_ready_refreshed_draft_plan_item(
            resume,
            active_work_todo_resume,
            first_observation,
        )
        task_goal = task_goal_plan_item()
        if task_goal and (
            actionable_plan_item.startswith("Draft one paired dry-run edit from the refreshed exact cached windows")
            or _write_ready_cached_window_refresh_plan_item(actionable_plan_item)
        ):
            actionable_plan_item = (
                f"{task_goal}\n"
                "Recovered from a cached-window refresh blocker; draft only the patch that implements this task goal."
            )
    elif first_observation:
        actionable_plan_item = str(first_observation.get("plan_item") or "").strip()
    if actionable_plan_item:
        active_todo_plan_item = actionable_plan_item
    else:
        active_todo_plan_item = str((active_work_todo.get("source") or {}).get("plan_item") or "").strip()
    steer_text = str(fast_path.get("steer_text") or _write_ready_fast_path_steer_text(context, resume) or "").strip()
    if (
        _write_ready_locator_replacement_requests_write(context, steer_text)
        and _write_ready_locator_only_plan_item(active_todo_plan_item)
    ):
        active_todo_plan_item = _write_ready_task_goal_draft_plan_item(context, steer_text)
    if actionable_target_paths:
        active_todo_target_paths = actionable_target_paths
        cached_window_texts = [
            _write_ready_tiny_cached_window_prompt_item(item)
            for item in recent_windows
            if isinstance(item, dict)
            and any(_work_paths_match(item.get("path"), action_path) for action_path in actionable_target_paths)
        ]
    else:
        active_todo_target_paths = list(((active_work_todo.get("source") or {}).get("target_paths") or []))
        cached_window_texts = [
            _write_ready_tiny_cached_window_prompt_item(item)
            for item in recent_windows
        ]
    failed_patch_repair = _write_ready_failed_patch_repair_for_targets(resume, active_todo_target_paths)
    if failed_patch_repair:
        active_todo_plan_item = (
            f"{failed_patch_repair.get('repair_instruction') or 'Repair the same failed patch proposal.'}\n"
            f"Original proposal summary: {failed_patch_repair.get('proposal_summary') or ''}"
        ).strip()
    result = {
        "current_run": work_session.get("current_run") or {},
        "active_work_todo": {
            "source": {
                "plan_item": active_todo_plan_item,
                "target_paths": active_todo_target_paths,
            },
        },
        "write_ready_fast_path": {
            "active": True,
            "reason": "paired cached windows are edit-ready; emit one patch artifact or one blocker",
            "cached_window_texts": cached_window_texts,
        },
        "task_goal": {
            "required_terms": required_terms,
        },
        "allowed_roots": {
            "write": list(((write_ready_context.get("allowed_roots") or {}).get("write") or [])),
        },
    }
    active_memory = resume.get("active_memory") if isinstance(resume.get("active_memory"), dict) else {}
    if active_memory:
        result["active_memory"] = compact_active_memory_for_prompt(
            active_memory,
            mode="tiny_write_ready",
        )
    if failed_patch_repair:
        result["failed_patch_repair"] = failed_patch_repair
    retry_context = resume.get("retry_context") if isinstance(resume.get("retry_context"), dict) else {}
    if retry_context:
        result["retry_context"] = retry_context
    return result


def _work_action_schema_text():
    return (
        "{\n"
        '  "summary": "short reason",\n'
        '  "working_memory": {"hypothesis": "what appears true now", "next_step": "what to do after reentry", "plan_items": ["short remaining steps when more than one concrete step remains (max 3)"], "target_paths": ["narrow files or dirs to revisit first"], "open_questions": ["unknowns"], "last_verified_state": "latest verification state", "implementation_contract": {"objective": "hard task contract", "source_inventory": [{"path": "provided source/binary/artifact", "status": "needs_grounding|grounded", "reason": "why it matters"}], "prohibited_surrogates": ["stubs/dummy outputs/nearby tools that would not satisfy the task"], "open_contract_gaps": ["remaining source/verifier/artifact/behavior proof gap"]}, "acceptance_constraints": ["explicit stated constraints still relevant"], "acceptance_checks": [{"constraint": "constraint text", "status": "unknown|verified|blocked", "evidence": "tool output, diff, or file inspection used as proof", "evidence_refs": [{"kind": "command_evidence", "id": 1}]}]},\n'
        '  "action": {\n'
        '    "type": "batch|inspect_dir|analyze_table|read_file|read_image|read_images|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|edit_file_hunks|finish|send_message|ask_user|remember|wait",\n'
        '    "tools": ['
        '{"type": "inspect_dir|analyze_table|read_file|read_image|read_images|search_text|glob|git_status|git_diff|git_log|write_file|edit_file", '
        '"path": "required for analyze_table/read_file/read_image/glob/search_text", '
        '"paths": "required list for read_images", '
        '"query": "required for search_text; literal fixed-string, so use batch for OR searches", '
        '"pattern": "required for glob; optional rg glob filter for search_text", '
        '"max_chars": "optional read_file cap", '
        '"line_start": "optional 1-based read_file starting line from search_text results", '
        '"line_count": "optional read_file line count", '
        '"content": "write_file content", '
        '"old": "edit_file old text", '
        '"new": "edit_file new text", '
        '"edits": [{"old": "edit_file_hunks old text", "new": "replacement"}], '
        '"create": false, '
        '"replace_all": false, '
        '"dry_run": true, '
        '"timeout": "optional run_tests/run_command timeout seconds"}],\n'
        '    "path": "optional path",\n'
        '    "query": "search_text literal fixed-string query",\n'
        '    "pattern": "glob pattern",\n'
        '    "max_chars": "optional read_file cap",\n'
        '    "line_start": "optional 1-based read_file starting line from search_text results",\n'
        '    "line_count": "optional read_file line count",\n'
        '    "max_rows": "optional analyze_table row cap",\n'
        '    "max_extrema": "optional analyze_table local-extrema cap",\n'
        '    "paths": "required list for read_images",\n'
        '    "detail": "optional read_image/read_images detail low|high|auto",\n'
        '    "prompt": "optional read_image/read_images inspection prompt",\n'
        '    "max_output_chars": "optional read_images output cap",\n'
        '    "stat": "optional git_diff diffstat; set false only when full diff is needed",\n'
        '    "command": "run_tests/run_command command",\n'
        '    "timeout": "optional run_tests/run_command timeout seconds; use only for bounded long-running verifier/build commands",\n'
        '    "content": "write_file content",\n'
        '    "old": "edit_file old text",\n'
        '    "new": "edit_file new text",\n'
        '    "edits": [{"old": "edit_file_hunks old text", "new": "replacement"}],\n'
        '    "text": "send_message text",\n'
        '    "note": "remember note",\n'
        '    "question": "ask_user question",\n'
        '    "summary": "optional concrete result, recommendation, or stopping note",\n'
        '    "message_type": "assistant|info|warning",\n'
        '    "acceptance_checks": [{"constraint": "constraint text", "status": "verified|blocked|unknown", "evidence": "direct evidence from recent terminal command evidence, tool output, diff, or file inspection", "evidence_refs": [{"kind": "command_evidence", "id": 1}]}],\n'
        '    "task_done": false,\n'
        '    "completion_summary": "optional task completion summary for finish",\n'
        '    "create": false,\n'
        '    "replace_all": false,\n'
        '    "dry_run": true,\n'
        '    "reason": "why this action is next"\n'
        "  }\n"
        "}"
    )


def is_resident_loop_command(command):
    return is_resident_mew_loop_command(command)


def _build_work_think_prompt_legacy(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Choose exactly one next action for this active coding work session.\n"
        "Treat guidance as the user's current instruction for this turn. If guidance asks for fresh inspection and read tools are available, use a targeted read action before finishing; do not finish solely because older notes or prior turns claim enough context. "
        "Fields named guidance_snapshot under prior turns or resume decisions are historical audit records, not current instructions. "
        "Treat the capabilities object as current and authoritative; if a read/write/verify root or command is allowed there, do not ask the user to pass the same flag again. "
        "Use prior tool_calls as your observation history. If you need more evidence, choose one narrow read tool. "
        "Use work_session.resume.active_memory as durable typed recall about the user, project, feedback, or references; treat it as relevant context, but verify project facts with tools before relying on them for code changes. If active_memory.compacted_for_prompt is true, memory bodies were intentionally omitted; use id/path/name/description as pointers and read only the narrow source you need. Do not use read_file on .mew/memory/private paths surfaced in active_memory; their excerpt is already present in the prompt and those files are sensitive. "
        "Use work_session.current_run as the active invocation budget and work_session.effort as historical session pressure. Do not claim the step or failure budget is exhausted while work_session.current_run.can_continue_after_current is true; if effort.pressure is high but current_run still has remaining steps and a safe repair/read/write action is clear, prefer that bounded action over finish. If effort.pressure is high and no safe action remains, prefer remember or ask_user with a concise state summary and concrete replan. If effort.pressure is medium, choose a narrow next action and refresh working_memory so the next reentry is not stale. "
        "If working_memory.target_paths lists likely files or directories for the next step, and one already names the likely file or directory, prefer a direct read_file on one of those target_paths before repeating same-surface search_text; otherwise prefer those paths before a broader project search, and keep that list short and current. "
        "If work_session.world_state.files marks a target_path as exists=false, do not read_file that missing path; inspect its parent or sibling surface first, then use write_file with create=true when creating the new scoped file is the intended implementation step. "
        "If work_session.resume.target_path_cached_window_observations already names a recent read_file window for that target_path, prefer refreshing that direct cached window before repeating same-surface search_text to rediscover the file. "
        "If work_session.resume.plan_item_observations lists a first remaining plan item paired to a target path or cached window, prefer that resume-side observation before broader search_text or rediscovery, and prune completed working_memory.plan_items as the task advances. "
        "If work_session.resume.plan_item_observations[0].edit_ready is true and cached_windows already cover the current paired target paths, prefer one paired dry-run edit over another same-path reread on those cached paths. "
        "To reduce first-edit-latency, do not spend another turn on same-surface rediscovery when the first-edit old text is already available in cached windows for the scoped source/test slice. "
        "Drop a working_memory.target_paths entry once it is no longer needed for the next step instead of carrying stale paths forward. "
        "If the latest search_text already returned the same path/query with the line anchor you need, do not rerun that same search_text; switch to a narrow read_file on the anchored window instead. "
        "If work_session.resume.search_anchor_observations lists successful search_text anchors, use its suggested_next read_file before repeating that same search_text. "
        "If work_session.resume.low_yield_observations lists repeated zero-match searches, do not keep searching that same path/pattern; use the suggested_next to switch to a targeted read, a single broader path, an edit from known context, or finish with a concrete replan. "
        "If work_session.resume.redundant_search_observations shows that the same successful search_text was already repeated on this surface, use its suggested_next read_file replacement instead of rerunning search_text again. "
        "If work_session.resume.adjacent_read_observations shows overlapping or near-adjacent read_file windows on the same path, use its suggested_next merged read instead of inching through more small reads. "
        "If work_session.resume.repair_anchor_observations lists source/test windows from a failed batch or repair loop, prefer those exact anchors before fresh same-surface search_text or broader rereads. "
        "If work_session.resume.failed_patch_repair is present, the previous write proposal was on-task but failed on exact old text; repair that same proposal using current anchors, preserve its must_preserve_terms/proposal_snippets, and do not substitute a nearby patch. "
        "If work_session.resume.broad_rollback_slice_repair is present, stop retrying the whole broad patch. Choose one smaller complete slice that includes its source, local tests/docs/report evidence, and verifier; record the remaining scope in working_memory before continuing. If broad_rollback_slice_repair.slice_focus is presentation_readability, split the visible text/wrapping/bubble/row/readability slice first before reconnecting broader live/state behavior. "
        "If work_session.resume.retry_context is present, treat it as the authoritative compact state after a rejected or rolled-back write: use its latest failure/status, target_windows, and pending_constraints, and do not reuse raw patch bodies from rejected or rolled-back tool_calls. "
        "Use work_session.resume.continuity as the reentry contract. If continuity.status is weak or broken, or continuity.missing is non-empty, treat continuity.recommendation as the first repair queue before side-effecting actions; prefer targeted reads, remember, or ask_user to repair missing memory, risk, next-action, approval, recovery, verifier, budget, decision, or user-pivot state. "
        "For code navigation, prefer search_text for symbols or option names before broad read_file; after search_text gives line numbers, use read_file with line_start and line_count to inspect only the relevant window. Explicit line_start/line_count reads auto-scale max_chars for edit preparation, so prefer one bridging line-window read over repeating the same span when a single-file edit needs a larger exact old-text window. If a handler definition is not in the current file but the symbol appears imported, search the broader project tree or allowed read root for that symbol instead of repeating same-file searches. "
        "If current guidance, recent windows, or the latest failure already name an exact line_start/line_count window, refresh that same targeted window instead of falling back to an offset read_file from the top of the file. "
        "If you need multiple independent read-only observations, prefer one batch action with up to five read-only tools. If work_session.recent_read_file_windows already contains the exact recent path/span or old text needed for edit preparation, reuse that recent window instead of issuing another same-span read_file. If a needed recent_read_file_windows entry is context_truncated, fall back to the matching read_file tool_calls result text before declaring that old text unrecoverable. "
        "If you already know the exact scoped edits, you may use one batch action with up to five write/edit tools under capabilities.allowed_write_roots. For mew core source edits under src/mew/**, include a paired tests/** edit in the same batch; this paired-write constraint applies to code write batches under mew core paths. For non-core product roots such as experiments/**, keep every write under the declared root and include local tests when the task scope calls for them. Docs-only single edit_file/write_file actions in other allowed write roots may be proposed directly when the target path is clear. Use at most one write/edit per file path in the batch; if the same file needs multiple disjoint hunks, prefer one edit_file_hunks action for that path instead of multiple same-path writes. If exact old text is already cached for those same-file hunks, do not return wait just because of the one-write-per-path rule; rewrite that file as one edit_file_hunks action and continue toward the reviewer-visible dry-run batch. If a large full-file write set cannot safely fit in one strict JSON batch, emit one complete file write/edit as a direct action and continue with the remaining sibling files on later turns; do not return wait solely because the multi-file batch would be too large. If the full required write set would exceed five tools, do not propose a partial batch that drops sibling edits; choose a narrower complete slice, one complete file action, or one more narrow read to reduce the write set first. mew will force writes to dry-run previews and keep approval/verification gated. Do not mix reads, wait, remember, finish, or blockers into write batches; if you cannot produce the complete write/edit slice, return one top-level wait instead of a batch containing wait. "
        "If you can make a small safe edit, use edit_file, edit_file_hunks, or write_file. For edit_file you must include exact old and new strings; for edit_file_hunks you must give one path plus a non-empty edits list of exact old/new pairs for disjoint hunks in that same file. If you are not sure of the exact old string, use work_session.recent_read_file_windows when available or read the smallest relevant file window first. Once a prior line-window read or recent_read_file_windows entry contains the exact old string, do not reread the full file solely to prepare edit_file or edit_file_hunks. Writes default to dry_run=true; set dry_run=false only when verification is configured. "
        "When editing mew source under src/mew, include a paired tests/ change in the same work session when practical; if the write boundary stops you before the test edit, use any pairing_status.suggested_test_path from the resume/cells as the first test-file candidate and record the intended test in working_memory.next_step. If a targeted test-file search misses, search tests/ or the likely test module before concluding that no paired test surface exists. "
        "Use run_tests for the configured verification command or a narrow test command. "
        "If work_session.resume.suggested_verify_command.command is present and no verify_command is configured, prefer that suggested command before inventing a broader verifier. "
        "If verification_confidence.status is narrow after source edits and suggested_verify_command.command exists, prefer run_tests with that broader suggested verifier before finish unless guidance explicitly says the task is narrow-only. "
        "If the latest verification or write/apply step failed and the failure is not obviously permission/environment related, prefer one narrow repair step using the failing output or suggested_safe_reobserve before finish or ask_user. "
        "If work_session.resume.verifier_failure_repair_agenda is present, treat it as the active repair queue: use its error_lines, source_locations, symbols, runtime_contract_gap, and latest_changed_dry_run_write to make one small applied edit batch before broader exploration. If runtime_contract_gap is present for a VM, emulator, interpreter, simulator, or custom runtime harness, preserve its kind/signature and map the built artifact with readelf/nm/objdump/addr2line plus runtime source reads before another rebuild. If the failure names multiple same-family symbols or source locations, repair the visible sibling set together instead of fixing only the first occurrence. If the traceback points into an installed/generated artifact but the workspace contains matching source under allowed write roots, inspect/edit the workspace source and reinstall or reverify rather than patching the installed artifact directly. "
        "If work_session.resume.stale_runtime_artifact_risk is present, the prior self-check created a /tmp runtime artifact that may short-circuit a fresh external verifier. Preserve the proof in acceptance_checks or working_memory.last_verified_state, then run a small cleanup command to clean stale runtime artifacts before finish unless the task explicitly requires that artifact to pre-exist. "
        "A runnable smoke command with exit_code=0 is not enough to finish when the task asks for generated artifacts, saved files, stdout/stderr text, rendered frames, screenshots, or other externally checked behavior; before finish, inspect those artifact/output properties or run a small command that asserts them. If those acceptance properties remain unverified, keep working or remember the exact unverified acceptance gap instead of claiming the verifier demonstrated it. "
        "For runtime frame, screenshot, or image-output tasks, artifact existence, nonzero pixels, valid headers, or self-consistent dimensions are not enough; cite a completed tool that checks expected dimensions/resolution, reference similarity, or exact stdout/boot markers before finish. "
        "For external dependency/source acquisition tasks, identify the authoritative source channel before invasive repair: prefer project docs, package-manager metadata, official release/distribution archives, signed checksums, release notes, or upstream download pages when available. Use a non-Python source fetch tool such as curl, wget, gh, or git for authority-producing archive acquisition; if the image lacks one and a package manager exists, install curl or wget before the source fetch. Python download snippets are only last-resort transport and should be paired with non-Python authority evidence before finish. When proving saved source authority from an existing archive and saved authority metadata, use top-level failing readback commands such as `test -f archive; sha256sum archive; tar -tzf archive` rather than wrapping hash/list readbacks in `if`, `while`, `|| true`, pipes, redirection, or other optional control-flow. Place or repeat saved source readbacks after noisy build/install output and close to the final artifact proof, so retained command output still includes metadata, archive hash, and archive root. Treat VCS-generated tag/archive URLs as source-tree fallbacks that may omit release packaging or compatibility shims. If a build from one source artifact hits dependency/API incompatibility, record source provenance in working_memory and evaluate a higher-authority source option before alternate toolchain surgery. "
        "For long dependency/toolchain/source-build tasks, preserve work_session.resume.long_build_state when present. Prerequisite installation, configure, dependency generation, or partial make/build output is progress, not completion, while a required final executable/artifact is missing. Before installing a distro toolchain for a source project with version constraints, run or inspect the smallest compatibility probe; if configure or package-manager output invalidates a toolchain/package path, record it in working_memory and switch paths instead of retrying it. If configure rejects an installed dependency version but the source tree is otherwise grounded, inspect ./configure --help or equivalent project help and try cheap source-provided compatibility/override flags before building an alternate toolchain from scratch. When probing configure/project help through grep, rg, awk, sed, or another filter, include external/use-external/prebuilt/system/library terms or inspect unfiltered help before concluding no source-provided external/prebuilt branch exists. If a package manager offers prebuilt dependencies and the project exposes or likely supports a source compatibility override, try the prebuilt dependency plus override path before starting a version-pinned source-built dependency/toolchain install; once source help or configure exposes an external/prebuilt compatibility branch, commit to one coherent branch early and reserve enough wall budget for its final artifact build instead of serially probing weaker branches. A plain ignore-version or allow-unsupported configure retry is not the same as trying an exposed external/prebuilt/system dependency branch; if that plain override fails with a dependency API or library-location mismatch, install the missing prebuilt/dev package when available and retry the external/prebuilt branch before starting version-pinned source toolchain work. If compatibility repair turns into edits under a vendored/third-party dependency or proof library while the final artifact is still missing, stop local dependency patch surgery and switch to a supported dependency version or source-provided external/prebuilt dependency branch before another long rebuild. For release archive/tag source builds, a versioned archive URL, tag/root directory, or tarball identity can ground the patch-level release even when an internal VERSION file only records the major/minor series; do not abort just because internal files omit a patch suffix already grounded by the archive/tag. If a Makefile/CMake/project build reports missing generated dependencies, missing source-path prefixes, or absent dependency files, run the project's dependency-generation/configure target before repeating the final target. When the task names one final executable/artifact, inspect available build targets and prefer the shortest explicit target that produces that artifact (for example the executable name) over full project, proof, doc, test, or all-target builds unless the task explicitly requires the full build. For compiler/toolchain tasks, a trivial return-only smoke binary is not enough if the toolchain has runtime or standard-library link requirements; install or configure the project's runtime/library target and verify a program that exercises the default link path before finish. If a default compile/link smoke fails with a missing runtime library such as 'cannot find -lfoo', do not restart source acquisition, configure, or clean rebuild; build/install the shortest runtime/library target into the default lookup path and rerun the same default smoke. If a local smoke only passes by adding custom runtime/library flags such as -stdlib, -L, LD_LIBRARY_PATH, or LIBRARY_PATH, treat that as diagnostic only; install/configure the runtime into the default lookup path and rerun the same compile/link smoke without those custom path flags before finish. If runtime install reports a missing library artifact, build the shortest explicit runtime-library target first, then retry install and the default-link smoke. If parent make reports no rule for a runtime/lib*.a or similar subdir library target, switch to the runtime subdirectory's own Makefile with make -C <runtime-dir> all/install instead of retrying the invalid parent target path. Do not restart package-manager or source-tree setup after a compatible toolchain path is found; allocate remaining wall budget to one shortest idempotent continuation command that produces the missing final artifact. For genuinely long prerequisite or source-build commands, set a bounded run_command timeout sized to the remaining wall budget instead of repeatedly slicing the same build into default-timeout commands. Then prove the final artifact exists and is executable/invokable before finish. "
        "For black-box or query-only model extraction tasks, do not read or copy visible fixture internals such as hidden weights from the provided source; local checks against exposed fixture weights are not enough to finish. Before task_done=true, cite synthetic, randomized, or holdout validation that demonstrates the method generalizes beyond the visible fixture. "
        "For model/checkpoint/tokenizer inference, sampling, or continuation tasks, compile success, byte size, the advertised CLI shape, and 'printed N tokens' are not enough. Before finish, cite completed tool output that proves model-output equivalence with a reference/golden/oracle continuation, argmax/top-1 token match, logits check, token-id match, or expected continuation. A reference/oracle built by copying, slicing, lightly modifying the current candidate implementation, or generating a new /tmp oracle source in this same work session is not independent evidence; if finish is blocked for model inference evidence/provenance, do not repeat finish with the same tool id or same oracle source. Run a new grounding/repair command or keep the exact model-output contract gap open. "
        "For numeric analysis, fitting, optimization, ranking, or scientific scripting tasks, prefer analyze_table on CSV/TSV/whitespace numeric source files before choosing fit windows, scales, extrema, or output values. A schema-only, finite-number, or single-fit residual check is not enough; before finish, cite a completed grounding tool whose output contains an independent cross-check such as an alternative method, recomputation, holdout, bootstrap, or sensitivity/stability validation against the input data, plus residual/error checks, expected peak/location windows, sign/range constraints, or a direct recomputation of the requested metric. "
        "For answer-from-artifact tasks such as images, boards, puzzles, diagrams, screenshots, or data files, reading back the output file or checking output format is not enough; independently derive or verify the semantic answer from the source artifact, and if the task asks for all winning/valid answers, prove completeness instead of writing a single plausible answer. "
        "When a source artifact is a PDF or text-bearing document, prefer read_file first; it extracts PDF text when possible and avoids lossy shell-side rendering. "
        "When a source artifact is an image, screenshot, diagram, board, plot, or code screenshot and read_image is available, prefer read_image before lossy ASCII rendering or manual OCR commands. "
        "When you have multiple related frames, pages, screenshots, or contact sheets, prefer one read_images call with a narrow task-specific prompt over repeated read_image calls; use bash/Python to transform video or documents into a small ordered image set, then read_images to summarize or transcribe the sequence. read_images can accept up to 16 images when the total payload is within limits; for long ordered sequences, use the largest chronological chunks that fit instead of many small chunks. If the ordered set is too large for one read_images call, split it into chronological chunks and summarize each chunk compactly before continuing. "
        "If work_session.resume.recent_read_images_observations contains a transcript or visual summary for a needed ordered chunk, reuse that observation instead of re-reading the same images; after a long read_images chunk, carry forward a compact transcript in working_memory before reading another chunk. "
        "read_image/read_images support image files only; if they report an unsupported document type, continue with read_file or other document/text observations instead of repeating the same visual read. "
        "If a task names an exact external ground-truth command, tool, binary, or required flags, run that exact command shape or a verifier that invokes it before finish; surrogate libraries, approximations, or nearby tools are not enough unless the task explicitly allows them. If a task says the user can run an exact backticked command example, verify that advertised command shape from the task cwd; do not insert a cd wrapper, change cwd, or verify only a nearby invocation whose compiler/output defaults differ. If prior command output says the exact command is NOT_FOUND, command not found, executable not found, or otherwise unavailable, do not install or use a surrogate package/library/API as a substitute; either run/install the exact command within current capabilities or return wait/remember with that exact blocker. Cite the completed run_command or run_tests command_evidence id in acceptance_checks evidence_refs when available. "
        "For hard implementation tasks with provided source, binaries, fixtures, or artifacts, keep working_memory.implementation_contract current: objective, source_inventory, prohibited_surrogates, and open_contract_gaps. Before finish with task_done=true, cite completed read/search/command evidence that grounds each provided source or binary, and cite verifier/artifact/behavior evidence separately. "
        "For hard runtime or VM tasks, command exit code alone is not final verifier state transfer. If the task says a fresh runtime command writes a /tmp artifact such as a frame, screenshot, log, socket, or pid file, prove the artifact was created by the final verifier-shaped command from the final cwd and cite that tool id before finish; if it cannot be reproduced, keep working_memory.final_verifier_state_transfer or last_verified_state focused on that blocker instead of finishing. "
        "If runtime evidence shows the verifier-read artifact path is /tmp/foo but your proof only checks frames/foo, output/foo, or a root copy, do not finish; prove the exact /tmp verifier path or explicitly copy/link the verified output there and verify that path before cleanup/handoff. "
        "For stateful user-facing output tasks where copy, labels, messages, speech, or status text must reflect live/current state, label-only assertions are not enough. Before finish, cite semantic contrast proof: one positive injected/current-state assertion and one negative fixture, demo, static, or fallback assertion that does not claim live state. "
        "Treat task.acceptance_constraints as a first-class checklist. Keep working_memory.acceptance_constraints and working_memory.acceptance_checks current. Before finish with task_done=true, action.acceptance_checks must cover every stated constraint with status=verified and direct evidence from recent terminal-success command evidence, tool output, diff, or file inspection. For run_command/run_tests evidence, prefer evidence_refs such as {\"kind\":\"command_evidence\",\"id\":N}; legacy {\"kind\":\"tool_call\",\"id\":N} refs are still accepted for older observations. Finish is only a candidate until the deterministic done gate resolves those refs. If one constraint is an edit-scope rule such as only allowed edits, specified replacements, or do-not-edit paths, verify that constraint explicitly with a post-edit validator, diff, or final inspection tool call after the latest write, and cite that tool id in the evidence; a successful compile, smoke command, output file, or write history alone does not prove it. "
        "When a rollback verifier failure has one small clear localized cause and the worktree is clean, keep that compact repair in-session and center it on the failed assertion/output and target path before switching to remember, checkpoint, or stop due pressure. "
        "For API, schema, protocol, config, or CLI contract tasks, preserve exact literal contract names from the task text for messages, methods, fields, keys, flags, endpoints, ports, and filenames. Do not substitute synonyms or nearby response-field names, such as using val when the task says value. Internal smoke tests and verifier commands must instantiate and assert the exact names from the task text, not the names you accidentally implemented. "
        "Do not invent test-only assertions for behavior you have not observed in source, command output, or current tests; inspect the producer first or make the paired source change in the same plan. For tests and verifier commands, prefer behavior, contract, output, state, or docs-visible assertions over exact source text phrase assertions unless the task explicitly requires a literal public string or security-sensitive marker. For contract/docs-heavy slices, compare documented headings/surfaces against actual renderer or CLI output instead of treating file creation as proof. For tasks involving watch, continuous, polling, listen, or other repeated modes, verifier planning must require bounded-loop or repeated-observation proof of external behavior; where relevant, include interval/interrupt handling or output-rewrite evidence, and do not accept internal mode flags alone. If a task mentions KeyboardInterrupt, Ctrl-C, SIGINT, cancellation, canceling, or cleanup, verify process-level cancellation/interrupt behavior when practical instead of only checking in-process coroutine cancellation. For Python async task orchestration where cancellation cleanup matters, prefer structured concurrency such as asyncio.TaskGroup, or explicitly prove that gather/semaphore code cancels and awaits only the started work. When verifying concurrency limits with cancellation, cover below-limit, exactly-at-limit, and above-limit cases when practical; one happy-path concurrency check is not enough. "
        "If investigation shows the task premise is false, already covered, or intentionally handled by existing tests, do not force a source edit; prefer run_tests to validate the conclusion, then finish with a no-change summary and task_done=true only if the investigation task is complete. "
        "For unittest verification, prefer a module-level command unless you have confirmed the exact class and method name in the current file or just created that method in the applied write. "
        "Do not use run_tests to invoke resident mew loops such as mew do, mew chat, mew run, or mew work --live; finish, remember, or ask_user instead. "
        "Use run_command only when shell is explicitly allowed. Prefer simple argv-style commands, but run_command executes top-level shell operators such as &&, ||, ;, |, background &, and redirection through a bash-compatible shell when those operators are needed. run_tests remains a single non-shell argv verifier. "
        "capabilities.allowed_write_roots constrain native write_file/edit_file/edit_file_hunks tools; they are not by themselves a reason to wait when shell is explicitly allowed and the task acceptance criteria require system service state. For tasks that explicitly require localhost daemons, system users, package or service config, ports, or exact verifier-visible paths such as /git, /srv, /var, /run, or /etc in an isolated work container, prefer one bounded run_command that configures the exact requested external interface and then verifies it, instead of waiting solely for more native write roots. Keep such shell commands narrow, avoid host secrets and sensitive paths, and do not substitute a /tmp-only implementation when the verifier requires an exact path or interface such as git@localhost:/git/project. "
        "Do not use run_command to invoke resident mew loops or the printed Next CLI controls such as mew work, mew do, mew chat, or mew run; those controls are for a human operator outside the active session. "
        "Use finish when the task is done or when an investigation/recommendation task has a concrete conclusion. Do not use finish merely because historical effort warnings mention step_budget or failure_budget while current_run says another step is available. "
        "Before finishing an implementation task that touched user-facing surfaces, account for the task acceptance criteria, README or usage docs, CLI stdout or output-file behavior, tests run, and any explicitly unverified modes in action.summary or action.completion_summary. "
        "If work_session.resume.same_surface_audit.status indicates a sibling-surface audit is still needed after src/mew edits, do one narrow audit step or record why the sibling surface is already covered or out of scope before finish. "
        "For implementation tasks with allowed write roots, do not finish merely because the next edit is clear; if exact old/new text or file content is available, propose the dry-run edit_file/write_file action instead. "
        "When finishing after investigation, evaluation, or recommendation guidance, include the concrete conclusion in action.summary or action.reason so the user does not have to infer it from prior tool output. "
        "Include a compact working_memory object that restates your current hypothesis, "
        "next intended step, open questions, and latest verified state for future reentry; "
        "If more than one concrete step remains, keep working_memory.plan_items as a short checklist of up to 3 remaining steps and prune completed items as work is completed. "
        "For hard tasks, preserve working_memory.implementation_contract across turns and shrink open_contract_gaps only after cited tool evidence grounds the source, verifier, artifact, or behavior. "
        "Keep working_memory.open_questions limited to unanswered items and drop resolved questions once answered. "
        "keep it short and do not copy raw logs. "
        "For finish, set task_done=true only when the task itself should be marked done.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


_LONG_DEPENDENCY_PROFILE_START = "For long dependency/toolchain/source-build tasks,"
_LONG_DEPENDENCY_PROFILE_END = "Then prove the final artifact exists and is executable/invokable before finish. "
_SOURCE_ACQUISITION_PROFILE_START = "For external dependency/source acquisition tasks,"
_SOURCE_ACQUISITION_PROFILE_END = "before alternate toolchain surgery. "
_RUNTIME_LINK_PROOF_START = "For compiler/toolchain tasks,"
_RUNTIME_LINK_PROOF_END = (
    "If runtime install reports a missing library artifact, build the shortest explicit runtime-library "
    "target first, then retry install and the default-link smoke. If parent make reports no rule for "
    "a runtime/lib*.a or similar subdir library target, switch to the runtime subdirectory's own Makefile "
    "with make -C <runtime-dir> all/install instead of retrying the invalid parent target path. "
)
_RECOVERY_BUDGET_START = "Do not restart package-manager or source-tree setup after a compatible toolchain path is found;"
_RECOVERY_BUDGET_END = (
    "For genuinely long prerequisite or source-build commands, set a bounded run_command timeout sized to "
    "the remaining wall budget instead of repeatedly slicing the same build into default-timeout commands. "
)


def _extract_prompt_span(text, start, end):
    start_index = text.find(start)
    if start_index < 0:
        return text, "", ""
    end_index = text.find(end, start_index)
    if end_index < 0:
        return text, "", ""
    end_index += len(end)
    return text[:start_index], text[start_index:end_index], text[end_index:]


def _remove_prompt_span(text, start, end):
    before, span, after = _extract_prompt_span(text, start, end)
    if not span:
        return text, ""
    return f"{before.rstrip()} {after.lstrip()}".strip(), span.strip()


def _work_think_dynamic_failure_evidence_section(context):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    work_session = work_session if isinstance(work_session, dict) else {}
    resume = work_session.get("resume") if isinstance(work_session.get("resume"), dict) else {}
    context_compaction = work_session.get("context_compaction") if isinstance(work_session.get("context_compaction"), dict) else {}
    evidence = {
        "prompt_context_mode": context_compaction.get("prompt_context_mode") or "full",
        "has_failed_patch_repair": bool(resume.get("failed_patch_repair")),
        "has_retry_context": bool(resume.get("retry_context")),
        "has_verifier_failure_repair_agenda": bool(resume.get("verifier_failure_repair_agenda")),
        "has_long_build_state": bool(resume.get("long_build_state")),
        "has_stale_runtime_artifact_risk": bool(resume.get("stale_runtime_artifact_risk")),
        "has_continuity": bool(resume.get("continuity")),
    }
    return (
        "DynamicFailureEvidence\n"
        "Use this small dynamic index as routing evidence before adding new generic prompt text. "
        "If a relevant flag is true, inspect the matching work_session.resume object in Context JSON "
        "and repair through the lowest durable layer first: detector/resume, profile/contract, tool/runtime, "
        "then prompt section. Do not add another task-specific sentence when a structural detector or profile "
        "would preserve the same lesson across tasks.\n"
        f"Evidence index JSON:\n{json.dumps(evidence, ensure_ascii=False, sort_keys=True)}"
    )


def _work_think_compact_recovery_section(context):
    work_session = (context or {}).get("work_session") if isinstance(context, dict) else {}
    work_session = work_session if isinstance(work_session, dict) else {}
    compaction = work_session.get("context_compaction") if isinstance(work_session.get("context_compaction"), dict) else {}
    mode = compaction.get("prompt_context_mode") or "full"
    return (
        "CompactRecovery\n"
        "When prompt context is compacted, use work_session.resume, recent_read_file_windows, "
        "target_path_cached_window_observations, and working_memory as the reentry contract. "
        "If the exact old text or verifier state is absent, do one narrow recovery read or remember the "
        "specific blocker instead of guessing. If mode is compact_recovery, avoid broad rediscovery and "
        "choose the smallest action that restores source, verifier, risk, or next-action state.\n"
        f"Current prompt_context_mode: {mode}"
    )


def build_work_think_prompt_sections(context):
    legacy_prompt = _build_work_think_prompt_legacy(context)
    context_marker = "\n\nContext JSON:\n"
    if context_marker in legacy_prompt:
        prompt_before_context, context_json = legacy_prompt.split(context_marker, 1)
    else:
        prompt_before_context = legacy_prompt
        context_json = json.dumps(context, ensure_ascii=False, indent=2)
    schema_marker = "\nSchema:\n"
    if schema_marker in prompt_before_context:
        implementation_prompt, schema_text = prompt_before_context.rsplit(schema_marker, 1)
    else:
        implementation_prompt = prompt_before_context
        schema_text = _work_action_schema_text()

    before_source_acquisition, source_acquisition_profile, after_source_acquisition = _extract_prompt_span(
        implementation_prompt,
        _SOURCE_ACQUISITION_PROFILE_START,
        _SOURCE_ACQUISITION_PROFILE_END,
    )
    profile_source = after_source_acquisition if source_acquisition_profile else implementation_prompt

    before_long_dependency, long_dependency_profile, after_long_dependency = _extract_prompt_span(
        profile_source,
        _LONG_DEPENDENCY_PROFILE_START,
        _LONG_DEPENDENCY_PROFILE_END,
    )
    if not long_dependency_profile:
        before_long_dependency = profile_source
        after_long_dependency = ""
    if source_acquisition_profile:
        before_long_dependency = f"{before_source_acquisition.rstrip()} {before_long_dependency.lstrip()}".strip()

    long_dependency_profile, runtime_link_proof = _remove_prompt_span(
        long_dependency_profile,
        _RUNTIME_LINK_PROOF_START,
        _RUNTIME_LINK_PROOF_END,
    )
    long_dependency_profile, recovery_budget = _remove_prompt_span(
        long_dependency_profile,
        _RECOVERY_BUDGET_START,
        _RECOVERY_BUDGET_END,
    )

    sections = [
        PromptSection(
            id="implementation_lane_base",
            version="v1",
            title="ImplementationLaneBase",
            content=before_long_dependency.strip(),
            stability=STABILITY_STATIC,
            cache_policy=CACHE_POLICY_CACHEABLE,
            profile="implement",
        )
    ]
    if source_acquisition_profile:
        sections.append(
            PromptSection(
                id="source_acquisition_profile",
                version="v1",
                title="SourceAcquisitionProfile",
                content=source_acquisition_profile.strip(),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="source_acquisition",
            )
        )
    if long_dependency_profile:
        sections.append(
            PromptSection(
                id="long_dependency_profile",
                version="v1",
                title="LongDependencyProfile",
                content=long_dependency_profile.strip(),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="long_dependency",
            )
        )
    if runtime_link_proof:
        sections.append(
            PromptSection(
                id="runtime_link_proof",
                version="v1",
                title="RuntimeLinkProof",
                content=runtime_link_proof.strip(),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="long_dependency",
            )
        )
    if recovery_budget:
        sections.append(
            PromptSection(
                id="recovery_budget",
                version="v1",
                title="RecoveryBudget",
                content=recovery_budget.strip(),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="long_dependency",
            )
        )
    if after_long_dependency.strip():
        sections.append(
            PromptSection(
                id="implementation_lane_base_continuation",
                version="v1",
                title="ImplementationLaneBaseContinuation",
                content=after_long_dependency.strip(),
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="implement",
            )
        )
    sections.extend(
        [
            PromptSection(
                id="work_action_schema",
                version="v1",
                title="Schema",
                content=f"Schema:\n{schema_text.strip()}",
                stability=STABILITY_STATIC,
                cache_policy=CACHE_POLICY_CACHEABLE,
                profile="implement",
            ),
            PromptSection(
                id="compact_recovery",
                version="v1",
                title="CompactRecovery",
                content=_work_think_compact_recovery_section(context),
                stability=STABILITY_SEMI_STATIC,
                cache_policy=CACHE_POLICY_SESSION,
                profile="implement",
            ),
            PromptSection(
                id="dynamic_failure_evidence",
                version="v1",
                title="DynamicFailureEvidence",
                content=_work_think_dynamic_failure_evidence_section(context),
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement",
            ),
            PromptSection(
                id="context_json",
                version="v1",
                title="Context JSON",
                content=f"Context JSON:\n{context_json.strip()}",
                stability=STABILITY_DYNAMIC,
                cache_policy=CACHE_POLICY_DYNAMIC,
                profile="implement",
            ),
        ]
    )
    return sections


def build_work_think_prompt_bundle(context):
    sections = build_work_think_prompt_sections(context)
    prompt = render_prompt_sections(sections)
    return prompt, prompt_section_metrics(sections)


def build_work_think_prompt(context):
    prompt, _metrics = build_work_think_prompt_bundle(context)
    return prompt


def build_work_write_ready_think_prompt(context):
    schema = (
        '{"summary":"short reason",'
        '"working_memory":{"hypothesis":"current narrow read","next_step":"next reentry step",'
        '"plan_items":["up to 3 remaining steps"],"target_paths":["scoped paths"],'
        '"open_questions":["unknowns"],"last_verified_state":"latest verifier state",'
        '"acceptance_constraints":["task constraints"],'
        '"acceptance_checks":[{"constraint":"text","status":"unknown|verified|blocked","evidence":"proof","evidence_refs":[{"kind":"tool_call","id":1}]}]},'
        '"action":{"type": "batch|inspect_dir|read_file|read_image|read_images|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|edit_file_hunks|finish|send_message|ask_user|remember|wait",'
        '"tools":[{"type":"write_file|edit_file|edit_file_hunks","path":"target path",'
        '"content":"write_file content","old":"exact old text","new":"replacement",'
        '"edits":[{"old":"exact old text","new":"replacement"}],"create":false,'
        '"replace_all":false,"dry_run":true}],'
        '"path":"target path","content":"write_file content","old":"exact old text",'
        '"new":"replacement","edits":[{"old":"exact old text","new":"replacement"}],'
        '"create":false,"replace_all":false,"dry_run":true,'
        '"reason":"why this scoped draft or blocker is next"}}'
    )
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Write-ready fast path is active.\n"
        "The active_work_todo already names the paired src/test slice to draft.\n"
        "Return exactly one next action using the schema below.\n"
        "Use write_ready_fast_path.cached_window_texts as the exact old text source for edit_file/edit_file_hunks.\n"
        "Keep the action inside active_work_todo.source.target_paths and allowed_roots.write.\n"
        "Treat required terms as semantic anchors, not fields to copy; return wait with blocker task_goal_term_missing if they cannot naturally fit this scoped edit.\n"
        "If failed_patch_repair or retry_context is present, repair that same proposal/current target window and keep its constraints instead of switching to a nearby easier patch.\n"
        "If broad_rollback_slice_repair is present, do not retry the full broad patch; select one smaller complete source/test/docs slice and carry remaining scope in working_memory.\n"
        "Use current_run as the active invocation budget; historical effort pressure is not a hard stop while current_run can continue.\n"
        "Preserve exact public contract names from the task text: methods, fields, flags, endpoints, filenames, CLI strings, and documented output names.\n"
        "For numeric, artifact, visual, watch, cancellation, or concurrency tasks, draft code/tests that make semantic verification possible rather than schema-only or smoke-only proof.\n"
        "For tests and verifier commands, prefer behavior, contract, output, state, or docs-visible assertions over exact source text phrase assertions unless the task explicitly requires a literal public string or security-sensitive marker; for contract/docs-heavy slices, compare documented headings/surfaces with actual renderer or CLI output instead of file creation as proof. For watch, continuous, polling, listen tasks require bounded-loop or repeated-observation proof plus interval/interrupt handling or output-rewrite evidence; do not accept internal mode flags alone. If task mentions KeyboardInterrupt, Ctrl-C, SIGINT, prefer process-level cancellation/interrupt behavior over in-process coroutine cancellation. For Python async cancellation, prefer structured concurrency such as asyncio.TaskGroup or prove gather/semaphore code cancels and awaits only the started work. For concurrency limits cover below-limit, exactly-at-limit, and above-limit; one happy-path concurrency check is not enough.\n"
        "When a rollback verifier failure has one small clear localized cause, the worktree is clean, and current_run can continue, keep the compact repair in-session and center it on the failed assertion/output and target path before switching to remember, checkpoint, or stop due pressure.\n"
        "Prefer one scoped dry-run batch under active_work_todo.source.target_paths now. Prefer one paired dry-run batch for mew core target paths: paired tests/** plus src/mew/**. For non-core allowed roots, stay inside the declared product root and include local tests when they are in scope.\n"
        "If one file needs multiple hunks, use a single edit_file_hunks action for that path instead of returning wait for the one-write-per-path rule.\n"
        "If a large multi-file write_file batch would be too large for strict JSON, emit one complete file write/edit as a direct action and continue sibling files on later turns.\n"
        "Do not add read, search, glob, git, shell, or verification actions on this fast path.\n"
        "Do not broaden scope, roots, or the focused verify command.\n"
        "If you still cannot draft the dry-run batch, return wait with one exact blocker tied to the cached windows.\n"
        "Do not invent uncached old text and do not propose a partial sibling edit set.\n"
        f"Schema:\n{schema}\n\n"
        f"FocusedContext JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def build_work_write_ready_tiny_draft_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Write-ready tiny draft lane is active.\n"
        "Return patch_proposal or patch_blocker, not work action JSON/action/tools.\n"
        "Use only active_work_todo.source.target_paths and write_ready_fast_path.cached_window_texts for patch content.\n"
        "For task_goal.required_terms, use semantic anchors from the task goal, not product fields to copy; do not add fields or keys solely because a required term names them. Never persist a key named required_terms unless explicitly asked. Use blocker task_goal_term_missing when anchors cannot fit naturally.\n"
        "Repair the same failed_patch_repair or retry_context target. Use current_run as the active invocation budget.\n"
        "If broad_rollback_slice_repair is present, do not retry the full broad patch; select one smaller complete source/test/docs slice and carry remaining scope in working_memory.\n"
        "Verifier keys: prefer behavior, contract, output, state, or docs-visible assertions; over exact source text phrase assertions; unless the task explicitly requires a literal public string or security-sensitive marker; contract/docs-heavy slices; documented headings/surfaces; actual renderer or CLI output; file creation as proof; watch, continuous, polling, listen; bounded-loop or repeated-observation proof; interval/interrupt handling or output-rewrite evidence; do not accept internal mode flags alone; KeyboardInterrupt, Ctrl-C, SIGINT; process-level cancellation/interrupt behavior; in-process coroutine cancellation; structured concurrency such as asyncio.TaskGroup; gather/semaphore code cancels and awaits only the started work; below-limit, exactly-at-limit, and above-limit; one happy-path concurrency check is not enough.\n"
        "When a rollback verifier failure has one small clear localized cause, the worktree is clean, and current_run still has remaining steps, keep that compact repair in-session and center it on the failed assertion/output and target path before switching to remember, checkpoint, or stop due pressure.\n"
        "Stay inside allowed_roots.write; do not invent uncached old text.\n"
        "Do not return tool actions, read/search actions, shell commands, approvals, or verification steps.\n"
        "Keep mew core patches paired across src/mew/** and tests/**; otherwise stay inside active_work_todo.source.target_paths. Put multiple hunks for one file in one files[i].edits array.\n"
        "If drafting cannot proceed from the cached windows, return patch_blocker with one stable code and detail.\n"
        "Use cached_window_incomplete when the cached text exists but ends mid-block; use missing_exact_cached_window_texts when exact cached text is absent.\n"
        'Schema: {"kind": "patch_proposal|patch_blocker", "summary": "short", "files": [{"path": "src/mew/file.py", "edits": [{"old": "exact old text", "new": "replacement"}]}], "code": "blocker code", "detail": "blocker detail"}\n\n'
        f"FocusedContext JSON:\n{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
    )


def build_work_act_prompt(context, decision_plan):
    return (
        "You are the ACT phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Normalize the THINK decision into one executable action. Preserve the intent, but remove unsupported fields. "
        "Never broaden file roots or permissions. If the decision is unsafe or unsupported, return wait with a reason.\n"
        "If THINK selected run_command, capabilities.allow_shell is true, and the task explicitly requires system service state such as localhost daemons, system users, package/service config, ports, or verifier-visible paths like /git, /srv, /var, /run, or /etc, do not convert that shell command to wait solely because native allowed_write_roots exclude those paths. allowed_write_roots constrain native write_file/edit_file/edit_file_hunks tools, not shell-authorized service setup by itself. Preserve the run_command when it is bounded and exact-interface oriented; still reject resident mew loop commands, unsupported actions, sensitive host-secret access, or broad unrelated system changes.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"ThinkDecision JSON:\n{json.dumps(decision_plan, ensure_ascii=False, indent=2)}"
    )


def normalize_work_model_action(
    action_plan,
    verify_command="",
    suggested_verify_command="",
    allowed_write_roots=None,
    default_cwd="",
):
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
        invalid_write_batch_tool_types = []
        dropped_tool_count = 0
        for item in raw_tools:
            if not isinstance(item, dict):
                continue
            raw_sub_type = str(item.get("type") or item.get("tool") or "").strip()
            sub_action = normalize_work_model_action(
                {"action": item},
                verify_command=verify_command,
                suggested_verify_command=suggested_verify_command,
                allowed_write_roots=allowed_write_roots,
                default_cwd=default_cwd,
            )
            dropped_tool_count += int(sub_action.get("truncated_tools") or 0)
            if sub_action.get("type") == "batch":
                sub_actions = sub_action.get("tools") or []
            else:
                sub_actions = [sub_action]
            for candidate in sub_actions:
                if candidate.get("type") in WRITE_WORK_TOOLS:
                    saw_write_tool = True
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
                    if raw_sub_type and raw_sub_type not in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS):
                        invalid_write_batch_tool_types.append(raw_sub_type)
        if not normalized_tools:
            return {"type": "wait", "reason": "batch requires at least one read-only tool"}
        if saw_write_tool:
            if saw_non_write_tool:
                if invalid_write_batch_tool_types:
                    unique_types = ", ".join(dict.fromkeys(invalid_write_batch_tool_types))
                    return {
                        "type": "wait",
                        "reason": (
                            f"write batch cannot mix non-write tools ({unique_types}); "
                            "emit the blocker/wait as a separate turn before or after paired writes"
                        ),
                    }
                return {
                    "type": "wait",
                    "reason": "write batch cannot mix read-only tools; use a separate read step before paired writes",
                }
            raw_write_tools = list(normalized_tools)
            collapsed_write_tools = collapse_same_path_edit_file_write_batch_tools(raw_write_tools)
            if dropped_tool_count or len(collapsed_write_tools) > 5:
                return {
                    "type": "wait",
                    "reason": "write batch exceeds 5 tools; choose a narrower complete slice instead of dropping required sibling edits",
                }
            paired_reason = paired_write_batch_rejection_reason(
                raw_write_tools,
                allowed_write_roots=allowed_write_roots,
                cwd=default_cwd,
            )
            if paired_reason:
                return {"type": "wait", "reason": paired_reason}
            paired_tools = normalize_paired_write_batch_tools(
                raw_write_tools,
                allowed_write_roots=allowed_write_roots,
                cwd=default_cwd,
            )
            if not paired_tools:
                return {
                    "type": "wait",
                    "reason": "write batch could not be normalized inside the declared write roots",
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
        "paths",
        "query",
        "pattern",
        "max_chars",
        "max_output_chars",
        "timeout",
        "detail",
        "prompt",
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
        "edits",
        "reason",
        "text",
        "summary",
        "note",
        "question",
        "message_type",
        "completion_summary",
        "acceptance_checks",
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
    if (
        action_type == "edit_file"
        and normalized.get("edits") is not None
        and (edit_old is None or edit_new is None)
    ):
        action_type = "edit_file_hunks"
        normalized["type"] = "edit_file_hunks"
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
    if action_type == "edit_file_hunks":
        edits = normalized.get("edits")
        valid_edits = (
            isinstance(edits, list)
            and bool(edits)
            and all(
                isinstance(item, dict)
                and isinstance(item.get("old"), str)
                and item.get("old") != ""
                and isinstance(item.get("new"), str)
                for item in edits
            )
        )
        if not normalized.get("path") or not valid_edits:
            if normalized.get("path"):
                read_action = {
                    "type": "read_file",
                    "path": normalized.get("path"),
                    "reason": "edit_file_hunks requires one path plus exact old/new hunk pairs; read the target window before retrying",
                }
                for key in ("line_start", "line_count", "summary"):
                    if normalized.get(key) is not None:
                        read_action[key] = normalized.get(key)
                return read_action
            return {
                "type": "wait",
                "reason": "edit_file_hunks requires path plus a non-empty edits list of exact old/new pairs",
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
    if action_type in {"analyze_table", "read_file", "read_image"}:
        return bool(action.get("path"))
    if action_type == "read_images":
        paths = action.get("paths")
        return isinstance(paths, list) and bool(paths)
    if action_type == "search_text":
        return bool(action.get("query"))
    if action_type == "glob":
        return bool(action.get("pattern"))
    return action_type in (READ_ONLY_WORK_TOOLS | GIT_WORK_TOOLS)


def _normalized_work_path(path):
    return str(path or "").replace("\\", "/").lstrip("./")


def _work_paths_match(left, right):
    normalized_left = _normalized_work_path(left)
    normalized_right = _normalized_work_path(right)
    if not normalized_left or not normalized_right:
        return False
    return (
        normalized_left == normalized_right
        or normalized_left.endswith(f"/{normalized_right}")
        or normalized_right.endswith(f"/{normalized_left}")
    )


def _work_batch_path_is_tests(path):
    normalized = _normalized_work_path(path)
    return normalized == "tests" or normalized.startswith("tests/")


def _work_batch_path_is_mew_source(path):
    normalized = _normalized_work_path(path)
    return normalized.startswith("src/mew/") and normalized.endswith(".py")


def _work_batch_path_under_allowed_write_roots(path, allowed_write_roots=None, cwd=""):
    if not str(path or "").strip():
        return False
    roots = [root for root in (allowed_write_roots or []) if str(root or "").strip()]
    if not roots:
        return False
    base = Path(cwd or ".").expanduser()
    if not base.is_absolute():
        base = Path.cwd() / base
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = candidate.resolve(strict=False)
    for root in roots:
        root_text = str(root or "").strip()
        if root_text in {".", "*"}:
            return True
        root_path = Path(root_text).expanduser()
        if not root_path.is_absolute():
            root_path = base / root_path
        root_path = root_path.resolve(strict=False)
        try:
            candidate.relative_to(root_path)
            return True
        except ValueError:
            continue
        except OSError:
            continue
    return False


def duplicate_paired_write_batch_paths(tools):
    seen = set()
    duplicates = []
    for tool in tools or []:
        path = _normalized_work_path((tool or {}).get("path"))
        if not path:
            continue
        if path in seen and path not in duplicates:
            duplicates.append(path)
            continue
        seen.add(path)
    return duplicates


def collapse_same_path_edit_file_write_batch_tools(tools):
    copied_tools = [dict(tool) for tool in tools or []]
    path_indexes = {}
    for index, tool in enumerate(copied_tools):
        path = _normalized_work_path(tool.get('path'))
        if not path:
            continue
        path_indexes.setdefault(path, []).append(index)
    duplicate_paths = [path for path, indexes in path_indexes.items() if len(indexes) > 1]
    if not duplicate_paths:
        return copied_tools

    def collapseable_edits(tool):
        tool_type = tool.get("type")
        if tool_type == "edit_file":
            if tool.get("replace_all"):
                return None
            old = tool.get("old")
            new = tool.get("new")
            if not isinstance(old, str) or old == "" or not isinstance(new, str):
                return None
            return [{"old": old, "new": new}]
        if tool_type == "edit_file_hunks":
            edits = tool.get("edits")
            if not isinstance(edits, list) or not edits:
                return None
            normalized_edits = []
            for edit in edits:
                if not isinstance(edit, dict):
                    return None
                old = edit.get("old")
                new = edit.get("new")
                if not isinstance(old, str) or old == "" or not isinstance(new, str):
                    return None
                normalized_edits.append({"old": old, "new": new})
            return normalized_edits
        return None

    path_edits = {}
    for path in duplicate_paths:
        edits = []
        for index in path_indexes[path]:
            collapsed_edits = collapseable_edits(copied_tools[index])
            if collapsed_edits is None:
                return copied_tools
            edits.extend(collapsed_edits)
        if not edits:
            return copied_tools
        path_edits[path] = edits
    normalized = []
    collapsed_paths = set()
    for tool in copied_tools:
        path = _normalized_work_path(tool.get('path'))
        if path in duplicate_paths:
            if path in collapsed_paths:
                continue
            collapsed_tool = dict(tool)
            collapsed_tool.pop('old', None)
            collapsed_tool.pop('new', None)
            collapsed_tool['type'] = 'edit_file_hunks'
            collapsed_tool['edits'] = path_edits[path]
            normalized.append(collapsed_tool)
            collapsed_paths.add(path)
            continue
        normalized.append(tool)
    return normalized


def paired_write_batch_rejection_reason(tools, allowed_write_roots=None, cwd=""):
    write_tools = []
    for raw_tool in tools or []:
        tool = dict(raw_tool)
        if not tool.get("type") and tool.get("tool"):
            tool["type"] = tool.get("tool")
        if tool.get("type") in WRITE_WORK_TOOLS:
            write_tools.append(tool)
    if len(write_tools) < 2:
        return "write batch requires at least two write/edit tools for a complete scoped slice"
    if not all(valid_paired_write_batch_sub_action(tool) for tool in write_tools):
        return "write batch contains an invalid write/edit tool; provide path and exact content or old/new hunks"
    write_tools = collapse_same_path_edit_file_write_batch_tools(write_tools)
    if not write_tools:
        return "write batch requires at least one write/edit tool"
    duplicates = duplicate_paired_write_batch_paths(write_tools)
    if duplicates:
        return (
            "write batch may include at most one write/edit per file path; "
            f"collapse same-file hunks into a single edit_file or edit_file_hunks for {duplicates[0]}"
        )
    tests_tools = [tool for tool in write_tools if _work_batch_path_is_tests(tool.get("path"))]
    source_tools = [tool for tool in write_tools if _work_batch_path_is_mew_source(tool.get("path"))]
    if source_tools and (not tests_tools or len(tests_tools) + len(source_tools) != len(write_tools)):
        return "write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each"
    if source_tools:
        return ""
    if all(
        _work_batch_path_under_allowed_write_roots(tool.get("path"), allowed_write_roots, cwd=cwd)
        for tool in write_tools
    ):
        return ""
    if allowed_write_roots:
        return "write batch contains paths outside the declared allowed_write_roots"
    return ""


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
    if action_type == "edit_file_hunks":
        edits = action.get("edits")
        return bool(action.get("path")) and isinstance(edits, list) and bool(edits) and all(
            isinstance(item, dict)
            and isinstance(item.get("old"), str)
            and item.get("old") != ""
            and isinstance(item.get("new"), str)
            for item in edits
        )
    return False


def normalize_paired_write_batch_tools(tools, allowed_write_roots=None, cwd=""):
    write_tools = []
    for raw_tool in tools or []:
        tool = dict(raw_tool)
        if not tool.get("type") and tool.get("tool"):
            tool["type"] = tool.get("tool")
        if tool.get("type") in WRITE_WORK_TOOLS:
            write_tools.append(tool)
    if len(write_tools) < 2:
        return []
    if not all(valid_paired_write_batch_sub_action(tool) for tool in write_tools):
        return []
    write_tools = collapse_same_path_edit_file_write_batch_tools(write_tools)
    if not write_tools:
        return []
    if duplicate_paired_write_batch_paths(write_tools):
        return []
    tests_tools = [tool for tool in write_tools if _work_batch_path_is_tests(tool.get("path"))]
    source_tools = [tool for tool in write_tools if _work_batch_path_is_mew_source(tool.get("path"))]
    if source_tools and (not tests_tools or len(tests_tools) + len(source_tools) != len(write_tools)):
        return []
    if not source_tools and not all(
        _work_batch_path_under_allowed_write_roots(tool.get("path"), allowed_write_roots, cwd=cwd)
        for tool in write_tools
    ):
        return []
    source_path = source_tools[0].get("path") if source_tools else ""
    normalized = []
    ordered_tools = [*tests_tools, *source_tools] if source_tools else write_tools
    for raw_tool in ordered_tools:
        tool = dict(raw_tool)
        tool["apply"] = False
        tool["dry_run"] = True
        if source_path and raw_tool in tests_tools:
            tool["defer_verify_on_approval"] = True
            tool["paired_test_source_path"] = source_path
        normalized.append(tool)
    return normalized


def _coerce_work_tool_timeout(value):
    if value is None:
        return None
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        return None
    if timeout <= 0:
        return None
    return timeout


def work_tool_parameters_from_action(
    action,
    allowed_write_roots=None,
    allow_shell=False,
    allow_verify=False,
    verify_command="",
    verify_timeout=300,
    default_cwd="",
):
    parameters = dict(action or {})
    action_type = action.get("type") or action.get("tool")
    parameters.pop("type", None)
    if default_cwd and parameters.get("cwd") in (None, "", "."):
        parameters["cwd"] = default_cwd
    parameters["allowed_write_roots"] = allowed_write_roots or []
    parameters["allow_shell"] = bool(allow_shell)
    parameters["allow_verify"] = bool(allow_verify)
    if verify_command and not parameters.get("verify_command"):
        parameters["verify_command"] = verify_command
    if default_cwd and parameters.get("verify_cwd") in (None, "", "."):
        parameters["verify_cwd"] = parameters.get("cwd") or default_cwd
    else:
        parameters.setdefault("verify_cwd", parameters.get("cwd") or ".")
    parameters.setdefault("verify_timeout", verify_timeout)
    if action_type in {"run_command", "run_tests"} and parameters.get("timeout") is not None:
        timeout = _coerce_work_tool_timeout(parameters.get("timeout"))
        if timeout is None:
            parameters.pop("timeout", None)
        else:
            parameters["timeout"] = timeout
    if action_type == "read_file":
        try:
            parameters["max_chars"] = _line_window_auto_max_chars(parameters)
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
    compact_live=False,
    deliberation_requested=False,
    auto_deliberation=True,
    run_step_index=None,
    run_max_steps=None,
    timeout_ceiling=False,
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
    prompt_context_mode = work_prompt_context_mode(
        reasoning_policy,
        compact_live=compact_live,
    )
    prompt_context_mode = _prompt_context_mode_for_wall_clock(
        prompt_context_mode,
        timeout_ceiling=timeout_ceiling,
    )
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
        run_step_index=run_step_index,
        run_max_steps=run_max_steps,
    )
    write_ready_fast_path = _work_write_ready_fast_path_details(context)
    write_ready_context = (
        build_write_ready_work_model_context(context)
        if write_ready_fast_path.get("active")
        else {}
    )
    tiny_write_ready_context = (
        build_write_ready_tiny_draft_model_context(context)
        if write_ready_fast_path.get("active")
        else {}
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
    think_prompt_section_metrics = {}
    if write_ready_context:
        think_prompt = build_work_write_ready_think_prompt(write_ready_context)
    else:
        think_prompt, think_prompt_section_metrics = build_work_think_prompt_bundle(context)
    think_prompt_static_chars = 0
    think_prompt_dynamic_chars = 0
    if write_ready_fast_path.get("active"):
        think_prompt_static_chars, think_prompt_dynamic_chars = _write_ready_draft_prompt_chars(think_prompt)
    think_timeout = float(timeout)
    if write_ready_context and not timeout_ceiling:
        think_timeout = max(think_timeout, WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS)
    tiny_write_ready_prompt = (
        build_work_write_ready_tiny_draft_prompt(tiny_write_ready_context)
        if tiny_write_ready_context
        else ""
    )
    tiny_write_ready_timeout = (
        _write_ready_tiny_draft_timeout(timeout)
        if tiny_write_ready_context
        else 0.0
    )
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
            "timeout_seconds": think_timeout,
        },
        "prompt_sections": {"think": think_prompt_section_metrics} if think_prompt_section_metrics else {},
        "reasoning_policy": reasoning_policy,
        "reasoning_effort": reasoning_policy.get("effort") or "",
        "prompt_context_mode": prompt_context_mode,
        "write_ready_fast_path": bool(write_ready_fast_path.get("active")),
        "write_ready_fast_path_reason": write_ready_fast_path.get("reason") or "",
    }
    session_trace_patch = {}
    deliberation_result = _attempt_work_deliberation_lane(
        context=context,
        model_auth=model_auth,
        model=model,
        base_url=base_url,
        model_backend=model_backend,
        timeout=timeout,
        guidance=guidance,
        deliberation_requested=deliberation_requested and not timeout_ceiling,
        auto_deliberation=auto_deliberation and not timeout_ceiling,
        timeout_ceiling=timeout_ceiling,
        progress=progress,
        current_time=current_time,
    )
    if deliberation_result:
        session_trace_patch = deliberation_result.get("trace_patch") or {}
        model_metrics["deliberation"] = deliberation_result.get("metrics") or {}
        if deliberation_result.get("status") == "result_ready":
            metrics = deliberation_result.get("metrics") or {}
            model_metrics["think"] = {
                "prompt_chars": metrics.get("prompt_chars") or 0,
                "timeout_seconds": metrics.get("timeout_seconds") or WORK_DELIBERATION_MODEL_TIMEOUT_SECONDS,
                "elapsed_seconds": metrics.get("elapsed_seconds") or 0.0,
            }
            model_metrics["act"] = {
                "prompt_chars": 0,
                "elapsed_seconds": 0.0,
                "mode": "deliberation",
            }
            model_metrics["total_model_seconds"] = _round_seconds(
                (model_metrics.get("think") or {}).get("elapsed_seconds", 0.0)
                + (model_metrics.get("act") or {}).get("elapsed_seconds", 0.0)
            )
            if pre_model_metrics_sink:
                pre_model_metrics_sink(dict(model_metrics))
            return _work_plan_with_session_trace_patch(
                {
                    "decision_plan": deliberation_result.get("decision_plan") or {},
                    "action_plan": deliberation_result.get("action_plan") or {},
                    "action": deliberation_result.get("action")
                    or {"type": "wait", "reason": "deliberation result ready"},
                    "context": context,
                    "model_metrics": model_metrics,
                    "model_stream": {"phases": [], "chunks": 0, "chars": 0},
                },
                session_trace_patch,
            )
    preflight_block = _work_write_ready_preflight_block(context, write_ready_fast_path)
    if preflight_block:
        preflight_blocker = (
            (preflight_block.get("action_plan") or {}).get("blocker")
            if isinstance(preflight_block.get("action_plan"), dict)
            else {}
        )
        if isinstance(preflight_blocker, dict) and preflight_blocker:
            preflight_replay_fast_path = {
                **(write_ready_fast_path if isinstance(write_ready_fast_path, dict) else {}),
                "recent_windows": preflight_block.get("cached_windows_for_replay") or [],
                "cached_windows": preflight_block.get("cached_windows_for_replay") or [],
            }
            compiled = _compile_write_ready_patch_draft_proposal(
                session=session,
                context=context,
                proposal=preflight_blocker,
                write_ready_fast_path=preflight_replay_fast_path,
                allowed_write_roots=allowed_write_roots or [],
            )
            observation = compiled.get("observation") or _empty_patch_draft_compiler_observation()
            if any(observation.get(key) for key in observation):
                model_metrics.update(observation)
                model_metrics["tiny_write_ready_draft_outcome"] = "blocker"
                model_metrics["tiny_write_ready_draft_compiler_artifact_kind"] = (
                    observation.get("patch_draft_compiler_artifact_kind") or ""
                )
                if observation.get("patch_draft_compiler_error"):
                    model_metrics["tiny_write_ready_draft_error"] = (
                        observation.get("patch_draft_compiler_error") or ""
                    )
        model_metrics["think"] = {
            "prompt_chars": 0,
            "timeout_seconds": 0.0,
            "elapsed_seconds": 0.0,
        }
        model_metrics["act"] = {
            "prompt_chars": 0,
            "elapsed_seconds": 0.0,
            "mode": "deterministic",
        }
        model_metrics["total_model_seconds"] = 0.0
        if pre_model_metrics_sink:
            pre_model_metrics_sink(dict(model_metrics))
        if progress:
            progress(
                f"session #{session.get('id')}: preflight blocker {write_ready_fast_path.get('reason') or 'unknown'}"
            )
        return _work_plan_with_session_trace_patch(
            {
                "decision_plan": preflight_block.get("decision_plan") or {},
                "action_plan": preflight_block.get("action_plan") or {},
                "action": preflight_block.get("action") or {"type": "wait", "reason": "preflight blocker"},
                "context": context,
                "model_metrics": model_metrics,
                "model_stream": {"phases": [], "chunks": 0, "chars": 0},
            },
            session_trace_patch,
        )
    explicit_refresh_before_draft = _work_write_ready_explicit_refresh_before_tiny_draft(
        context,
        write_ready_fast_path,
    )
    if explicit_refresh_before_draft:
        model_metrics["think"] = {
            "prompt_chars": 0,
            "timeout_seconds": 0.0,
            "elapsed_seconds": 0.0,
        }
        model_metrics["act"] = {
            "prompt_chars": 0,
            "elapsed_seconds": 0.0,
            "mode": "deterministic",
        }
        model_metrics["total_model_seconds"] = 0.0
        if pre_model_metrics_sink:
            pre_model_metrics_sink(dict(model_metrics))
        if progress:
            progress(f"session #{session.get('id')}: explicit refresh before tiny draft")
        return _work_plan_with_session_trace_patch(
            {
                "decision_plan": explicit_refresh_before_draft.get("decision_plan") or {},
                "action_plan": explicit_refresh_before_draft.get("action_plan") or {},
                "action": explicit_refresh_before_draft.get("action") or {"type": "wait", "reason": "refresh unavailable"},
                "context": context,
                "model_metrics": model_metrics,
                "model_stream": {"phases": [], "chunks": 0, "chars": 0},
            },
            session_trace_patch,
        )
    rejection_frontier_recovery = (
        _work_rejection_frontier_recovery_action(context, write_ready_fast_path)
        if write_ready_fast_path.get("active")
        else {}
    )
    if rejection_frontier_recovery:
        model_metrics["think"] = {
            "prompt_chars": 0,
            "timeout_seconds": 0.0,
            "elapsed_seconds": 0.0,
        }
        model_metrics["act"] = {
            "prompt_chars": 0,
            "elapsed_seconds": 0.0,
            "mode": "deterministic",
        }
        model_metrics["total_model_seconds"] = 0.0
        if pre_model_metrics_sink:
            pre_model_metrics_sink(dict(model_metrics))
        if progress:
            progress(f"session #{session.get('id')}: rejection frontier recovery before redraft")
        return _work_plan_with_session_trace_patch(
            {
                "decision_plan": {
                    "summary": rejection_frontier_recovery.get("reason")
                    or "refresh exact context before redrafting after reviewer rejection",
                },
                "action_plan": {
                    "summary": rejection_frontier_recovery.get("reason")
                    or "refresh exact context before redrafting after reviewer rejection",
                    "action": rejection_frontier_recovery,
                    "act_mode": "deterministic",
                },
                "action": rejection_frontier_recovery,
                "context": context,
                "model_metrics": model_metrics,
                "model_stream": {"phases": [], "chunks": 0, "chars": 0},
            },
            session_trace_patch,
        )
    if write_ready_fast_path.get("active"):
        draft_windows = (
            write_ready_fast_path.get("recent_windows")
            or write_ready_fast_path.get("cached_windows")
            or []
        )
        model_metrics.update(
            {
                "draft_phase": "write_ready",
                "draft_attempts": _write_ready_draft_attempts(session, write_ready_fast_path.get("active")),
                "cached_window_ref_count": len(draft_windows),
                "cached_window_hashes": [
                    _write_ready_draft_window_signature(item) for item in draft_windows
                ],
                "draft_runtime_mode": _write_ready_draft_runtime_mode(stream_model),
                "draft_prompt_contract_version": WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION,
                "draft_prompt_static_chars": think_prompt_static_chars,
                "draft_prompt_dynamic_chars": think_prompt_dynamic_chars,
                "draft_retry_same_prefix": False,
                "patch_draft_compiler_ran": False,
                "patch_draft_compiler_artifact_kind": "",
                "patch_draft_compiler_replay_path": "",
                "patch_draft_compiler_error": "",
                "tiny_write_ready_draft_attempted": bool(tiny_write_ready_prompt),
                "tiny_write_ready_draft_outcome": "",
                "tiny_write_ready_draft_prompt_chars": len(tiny_write_ready_prompt),
                "tiny_write_ready_draft_timeout_seconds": tiny_write_ready_timeout,
                "tiny_write_ready_draft_fallback_reason": "",
                "tiny_write_ready_draft_error": "",
                "tiny_write_ready_draft_compiler_artifact_kind": "",
                **_tiny_write_ready_draft_reasoning_metrics(
                    reasoning_policy.get("effort") or "",
                    reasoning_policy.get("source") or "auto",
                ),
                "tiny_write_ready_draft_prompt_contract_version": (
                    WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION
                ),
            }
        )
    if pre_model_metrics_sink:
        pre_model_metrics_sink(dict(model_metrics))
    tiny_write_ready_elapsed = 0.0
    skip_shadow_compile = False
    if tiny_write_ready_context:
        tiny_result = _attempt_write_ready_tiny_draft_turn(
            session=session,
            context=context,
            tiny_context=tiny_write_ready_context,
            write_ready_fast_path=write_ready_fast_path,
            model_auth=model_auth,
            model=model,
            base_url=base_url,
            model_backend=model_backend,
            timeout=timeout,
            allowed_write_roots=allowed_write_roots,
            reasoning_effort=reasoning_policy.get("effort") or "",
            reasoning_effort_source=reasoning_policy.get("source") or "",
            current_time=current_time,
            think_kwargs=think_kwargs,
        )
        tiny_write_ready_elapsed = float(tiny_result.get("elapsed_seconds") or 0.0)
        model_metrics.update(tiny_result.get("metrics") or {})
        skip_shadow_compile = bool(tiny_result.get("compiler_observed"))
        if tiny_result.get("status") != "fallback":
            if progress:
                progress(f"session #{session.get('id')}: THINK ok")
            model_metrics["think"] = {
                "prompt_chars": len(tiny_write_ready_prompt),
                "timeout_seconds": tiny_write_ready_timeout,
                "elapsed_seconds": _round_seconds(tiny_write_ready_elapsed),
            }
            model_metrics["act"] = {
                "prompt_chars": 0,
                "elapsed_seconds": 0.0,
                "mode": "tiny_write_ready_draft",
            }
            model_metrics["total_model_seconds"] = _round_seconds(
                (model_metrics.get("think") or {}).get("elapsed_seconds", 0.0)
                + (model_metrics.get("act") or {}).get("elapsed_seconds", 0.0)
            )
            action = tiny_result.get("action") or {"type": "wait", "reason": "missing action"}
            action = _enforce_calibration_measured_patch_draft_finish_gate(
                task=task,
                context=context,
                action=action,
                model_metrics=model_metrics,
                session=session,
                allowed_write_roots=allowed_write_roots,
                action_plan=tiny_result.get("action_plan"),
            )
            action_plan = tiny_result.get("action_plan") if isinstance(tiny_result.get("action_plan"), dict) else {}
            gated_action = _enforce_rejection_frontier_recovery_gate(
                context,
                action,
                write_ready_fast_path,
            )
            if gated_action is not action:
                action = gated_action
                action_plan["action"] = action
                action_plan["summary"] = (
                    action.get("reason")
                    or action_plan.get("summary")
                    or "refresh exact context before redrafting after reviewer rejection"
                )
            if progress:
                progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
            return _work_plan_with_session_trace_patch(
                {
                    "decision_plan": tiny_result.get("decision_plan") or {},
                    "action_plan": action_plan,
                    "action": action,
                    "context": context,
                    "model_metrics": model_metrics,
                    "model_stream": compact_model_stream(stream_deltas),
                },
                session_trace_patch,
            )
        if timeout_ceiling:
            model_metrics["think"]["elapsed_seconds"] = _round_seconds(tiny_write_ready_elapsed)
            model_metrics["act"] = {
                "prompt_chars": 0,
                "elapsed_seconds": 0.0,
                "mode": "timeout_ceiling",
            }
            model_metrics["total_model_seconds"] = _round_seconds(tiny_write_ready_elapsed)
            action = {
                "type": "wait",
                "reason": "wall-clock timeout ceiling prevented broad fallback after tiny write-ready draft",
            }
            action_plan = {
                "summary": action["reason"],
                "action": action,
                "act_mode": "timeout_ceiling",
            }
            if pre_model_metrics_sink:
                pre_model_metrics_sink(dict(model_metrics))
            if progress:
                progress(f"session #{session.get('id')}: timeout ceiling stopped broad fallback")
            return _work_plan_with_session_trace_patch(
                {
                    "decision_plan": {"summary": action["reason"]},
                    "action_plan": action_plan,
                    "action": action,
                    "context": context,
                    "model_metrics": model_metrics,
                    "model_stream": compact_model_stream(stream_deltas),
                },
                session_trace_patch,
            )
        if pre_model_metrics_sink:
            pre_model_metrics_sink(dict(model_metrics))
    think_started = time.monotonic()
    try:
        with codex_reasoning_effort_scope(reasoning_policy.get("effort")):
            decision_plan = call_model_json_with_retries(
                model_backend,
                model_auth,
                think_prompt,
                model,
                base_url,
                think_timeout,
                log_prefix=f"{current_time}: work_think {model_backend} session={session.get('id')}",
                **think_kwargs,
            )
    except Exception as exc:
        if (
            write_ready_fast_path.get("active")
            and _work_model_error_looks_like_timeout(exc)
            and not _work_loop_model_metrics_have_patch_replay_or_artifact(model_metrics)
        ):
            think_elapsed = time.monotonic() - think_started
            todo_id = _work_loop_active_todo_id_from_context(context)
            decision_plan, action_plan, action = _work_loop_write_ready_timeout_blocker_plan(
                todo_id=todo_id,
                exc=exc,
            )
            model_metrics["tiny_write_ready_draft_outcome"] = "blocker"
            model_metrics["tiny_write_ready_draft_fallback_reason"] = ""
            model_metrics["tiny_write_ready_draft_error"] = clip_output(str(exc), 500)
            model_metrics["tiny_write_ready_draft_exit_stage"] = "broad_model_timeout_blocker"
            model_metrics["think"]["elapsed_seconds"] = _round_seconds(
                tiny_write_ready_elapsed + think_elapsed
            )
            model_metrics["act"] = {
                "prompt_chars": 0,
                "elapsed_seconds": 0.0,
                "mode": "tiny_write_ready_draft",
            }
            model_metrics["total_model_seconds"] = _round_seconds(
                (model_metrics.get("think") or {}).get("elapsed_seconds", 0.0)
                + (model_metrics.get("act") or {}).get("elapsed_seconds", 0.0)
            )
            if progress:
                progress(
                    f"session #{session.get('id')}: THINK timeout converted to write-ready blocker"
                )
                progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
            return _work_plan_with_session_trace_patch(
                {
                    "decision_plan": decision_plan,
                    "action_plan": action_plan,
                    "action": action,
                    "context": context,
                    "model_metrics": model_metrics,
                    "model_stream": compact_model_stream(stream_deltas),
                },
                session_trace_patch,
            )
        raise
    think_elapsed = time.monotonic() - think_started
    if progress:
        progress(f"session #{session.get('id')}: THINK ok")
    model_metrics["think"]["elapsed_seconds"] = _round_seconds(tiny_write_ready_elapsed + think_elapsed)
    work_default_cwd = (((context or {}).get("task") or {}).get("cwd") or "")
    if act_mode == "deterministic":
        action = normalize_work_model_action(
            decision_plan,
            verify_command=verify_command,
            suggested_verify_command=suggested_verify_command,
            allowed_write_roots=allowed_write_roots,
            default_cwd=work_default_cwd,
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
        allowed_write_roots=allowed_write_roots,
        default_cwd=work_default_cwd,
    )
    if write_ready_fast_path.get("active") and not skip_shadow_compile:
        model_metrics.update(
            _shadow_compile_patch_draft_for_write_ready_turn(
                session=session,
                context=context,
                action_plan=action_plan,
                action=action,
                write_ready_fast_path=write_ready_fast_path,
                allowed_write_roots=allowed_write_roots,
            )
        )
    action = _enforce_calibration_measured_patch_draft_finish_gate(
        task=task,
        context=context,
        action=action,
        model_metrics=model_metrics,
        session=session,
        allowed_write_roots=allowed_write_roots,
        action_plan=action_plan,
    )
    gated_action = _enforce_rejection_frontier_recovery_gate(
        context,
        action,
        write_ready_fast_path,
    )
    if gated_action is not action:
        action = gated_action
        if isinstance(action_plan, dict):
            action_plan["action"] = action
            action_plan["summary"] = (
                action.get("reason")
                or action_plan.get("summary")
                or "refresh exact context before redrafting after reviewer rejection"
            )
    model_metrics["total_model_seconds"] = _round_seconds(
        (model_metrics.get("think") or {}).get("elapsed_seconds", 0.0)
        + (model_metrics.get("act") or {}).get("elapsed_seconds", 0.0)
    )
    if progress:
        progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
    return _work_plan_with_session_trace_patch(
        {
            "decision_plan": decision_plan,
            "action_plan": action_plan,
            "action": action,
            "context": context,
            "model_metrics": model_metrics,
            "model_stream": compact_model_stream(stream_deltas),
        },
        session_trace_patch,
    )
