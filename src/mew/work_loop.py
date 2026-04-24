import json
import multiprocessing
import hashlib
from pathlib import Path
import re
import time
from io import StringIO
import tokenize

from .agent import call_model_json_with_retries as _agent_call_model_json_with_retries
from .config import DEFAULT_CODEX_MODEL, DEFAULT_CODEX_WEB_BASE_URL, DEFAULT_MODEL_BACKEND
from .errors import MewError, ModelBackendError
from .patch_draft import (
    PATCH_BLOCKER_RECOVERY_ACTIONS,
    compile_patch_draft,
    compile_patch_draft_previews,
)
from .reasoning_policy import codex_reasoning_effort_scope, select_work_reasoning_policy
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
WORK_WRITE_READY_DRAFT_PROMPT_CONTRACT_VERSION = "v2"
WORK_WRITE_READY_TINY_DRAFT_PROMPT_CONTRACT_VERSION = "v3"
WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT = "low"
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


def _work_model_timeout_guard_available():
    if not hasattr(multiprocessing, "get_context"):
        return False
    try:
        multiprocessing.get_context("fork")
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

    context = multiprocessing.get_context("fork")
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
        "approval_status": call.get("approval_status") or "",
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
        "failures",
        "unresolved_failure",
        "recurring_failures",
        "repair_anchor_observations",
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
    prompt_context_mode = _effective_prompt_context_mode(prompt_context_mode, resume, model_turns)
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
        active_work_todo = resume.get("active_work_todo")
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


def _write_ready_recent_windows_from_target_paths(work_session, resume):
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
    matched = []
    for path in ordered_paths:
        for item in recent_windows:
            if not _work_paths_match(item.get("path"), path):
                continue
            if not item.get("text") or item.get("context_truncated"):
                break
            matched.append(item)
            break
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
    cached_refs = _write_ready_cached_refs_from_active_work_todo(resume)
    exact_windows = _write_ready_exact_windows_for_cached_refs(work_session, cached_refs)
    if exact_windows and _write_ready_recent_windows_are_structurally_complete(exact_windows):
        return exact_windows
    recent_windows = [
        _write_ready_window_with_draft_window(window)
        for window in _write_ready_recent_windows_from_active_work_todo(work_session, resume)
    ]
    if recent_windows and _write_ready_recent_windows_are_structurally_complete(recent_windows):
        return recent_windows
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

    refs_by_path = {}
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
        refs_by_path[matching_path] = {
            **ref,
            "path": matching_path,
            "line_start": bounds[0],
            "line_end": bounds[1],
        }
    if set(refs_by_path) != set(target_paths):
        return []
    return [refs_by_path[path] for path in target_paths]


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
    return stripped.startswith(("def ", "async def ", "@"))


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

    for start_index in start_indices:
        candidate_text = "".join(lines[start_index:])
        if _write_ready_window_text_is_structurally_complete(candidate_text):
            return build_draft_window(
                start_index,
                len(lines) - 1,
                candidate_text,
                "trimmed leading structural fragment",
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
        return True
    return bool(delimiter_stack)


def _write_ready_window_text_is_structurally_complete(text):
    text = str(text or "")
    significant_lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not significant_lines:
        return False
    first_line = significant_lines[0]
    first_line_stripped = first_line.lstrip()
    first_keyword = first_line_stripped.split()[0].rstrip(":") if first_line_stripped else ""
    if first_line and first_line[0].isspace():
        if not first_line_stripped.startswith(("def ", "async def ", "@")):
            return False
    if first_line_stripped.endswith(":") and first_keyword in {"else", "elif", "except", "finally"}:
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
    actions = []
    seen = set()
    for match in span_pattern.finditer(text):
        raw_path = match.group("path").strip().strip("`'\"")
        path = next((item for item in allowed_paths if _work_paths_match(raw_path, item)), "")
        if not path:
            continue
        try:
            line_start = int(match.group("start"))
            line_end = int(match.group("end"))
        except (TypeError, ValueError):
            continue
        if line_start <= 0 or line_end < line_start:
            continue
        line_count = line_end - line_start + 1
        if line_count > 1000:
            continue
        key = (path, line_start, line_count)
        if key in seen:
            continue
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

    recent_windows = [
        item
        for item in (work_session.get("recent_read_file_windows") or [])
        if isinstance(item, dict) and item.get("path")
    ]

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
        for call in reversed(tool_calls):
            if not isinstance(call, dict) or call.get("tool") != "search_text":
                continue
            if str(call.get("status") or "") != "completed":
                continue
            parameters = call.get("parameters") if isinstance(call.get("parameters"), dict) else {}
            if not _work_paths_match(parameters.get("path"), target_path):
                continue
            if str(parameters.get("reason") or "") != "locate explicitly requested write-ready cached window":
                continue
            result = call.get("result") if isinstance(call.get("result"), dict) else {}
            snippets = result.get("snippets") if isinstance(result.get("snippets"), list) else []
            anchor_line = 0
            anchor_score = -10
            for snippet in snippets:
                if not isinstance(snippet, dict) or not _work_paths_match(snippet.get("path"), target_path):
                    continue
                score, line = snippet_anchor(snippet)
                if line > 0 and score > anchor_score:
                    anchor_score = score
                    anchor_line = line
            if anchor_line <= 0:
                break
            line_start = max(1, anchor_line - 120)
            line_count = 520
            line_end = line_start + line_count - 1
            if already_read(target_path, line_start, line_end):
                break
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
        "refresh",
        "source",
        "structurally",
        "targeted",
        "tests",
        "the",
        "window",
        "windows",
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
    def canonical_path(path):
        normalized = normalize_work_path(path)
        if not normalized:
            return ""

        candidate = Path(normalized)
        if candidate.is_absolute():
            try:
                return candidate.resolve(strict=False).relative_to(Path.cwd().resolve()).as_posix()
            except ValueError:
                return normalized
            except OSError:
                return normalized

        root_without_leading_slash = str(Path.cwd().resolve()).lstrip("/")
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
        "source": {"target_paths": target_paths},
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
    tiny_write_ready_draft_inherited_reasoning_effort = reasoning_effort or ""
    tiny_write_ready_draft_inherited_reasoning_effort_source = reasoning_effort_source or "auto"
    tiny_write_ready_draft_reasoning_effort = (
        tiny_write_ready_draft_inherited_reasoning_effort
        if tiny_write_ready_draft_inherited_reasoning_effort_source == "env_override"
        else WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT
    )
    tiny_write_ready_draft_reasoning_effort_source = (
        "env_override"
        if tiny_write_ready_draft_inherited_reasoning_effort_source == "env_override"
        else "tiny_draft_auto_override"
    )
    metrics = {
        "tiny_write_ready_draft_attempted": True,
        "tiny_write_ready_draft_outcome": "",
        "tiny_write_ready_draft_prompt_chars": len(prompt),
        "tiny_write_ready_draft_timeout_seconds": timeout_seconds,
        "tiny_write_ready_draft_reasoning_effort": tiny_write_ready_draft_reasoning_effort,
        "tiny_write_ready_draft_inherited_reasoning_effort": (
            tiny_write_ready_draft_inherited_reasoning_effort
        ),
        "tiny_write_ready_draft_reasoning_effort_source": (
            tiny_write_ready_draft_reasoning_effort_source
        ),
        "tiny_write_ready_draft_inherited_reasoning_effort_source": (
            tiny_write_ready_draft_inherited_reasoning_effort_source
        ),
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
    action = normalize_work_model_action(action_plan)
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
    return {
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
        "allowed_roots": {
            "read": capabilities.get("allowed_read_roots") or [],
            "write": capabilities.get("allowed_write_roots") or [],
        },
        "focused_verify_command": str(((active_work_todo.get("source") or {}).get("verify_command") or "")).strip(),
    }


def build_write_ready_tiny_draft_model_context(context):
    fast_path = _work_write_ready_fast_path_details(context)
    if not fast_path.get("active"):
        return {}
    write_ready_context = build_write_ready_work_model_context(context)
    if not write_ready_context:
        return {}
    resume = ((context or {}).get("work_session") or {}).get("resume") or {}
    actionable_target_paths = _write_ready_tiny_draft_observation_target_paths(resume)
    if not actionable_target_paths:
        actionable_target_paths = [str(path or "") for path in (fast_path.get("cached_paths") or []) if str(path).strip()]
    recent_windows = fast_path.get("recent_windows") or []
    active_work_todo = write_ready_context.get("active_work_todo") or {}
    plan_item_observations = resume.get("plan_item_observations") or []
    first_observation = plan_item_observations[0] if plan_item_observations and isinstance(plan_item_observations[0], dict) else {}
    actionable_plan_item = ""
    stale_refresh_blocker_cleared = bool(
        fast_path.get("activation_source") == "active_work_todo_complete_reads"
        and _write_ready_refresh_blocker_cleared_by_complete_windows(
            resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {},
            recent_windows,
        )
    )
    if stale_refresh_blocker_cleared:
        actionable_plan_item = _write_ready_refreshed_draft_plan_item(
            resume,
            resume.get("active_work_todo") if isinstance(resume.get("active_work_todo"), dict) else {},
            first_observation,
        )
    elif first_observation:
        actionable_plan_item = str(first_observation.get("plan_item") or "").strip()
    if actionable_plan_item:
        active_todo_plan_item = actionable_plan_item
    else:
        active_todo_plan_item = str((active_work_todo.get("source") or {}).get("plan_item") or "").strip()
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
    return {
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
        "allowed_roots": {
            "write": list(((write_ready_context.get("allowed_roots") or {}).get("write") or [])),
        },
    }


def _work_action_schema_text():
    return (
        "{\n"
        '  "summary": "short reason",\n'
        '  "working_memory": {"hypothesis": "what appears true now", "next_step": "what to do after reentry", "plan_items": ["short remaining steps when more than one concrete step remains (max 3)"], "target_paths": ["narrow files or dirs to revisit first"], "open_questions": ["unknowns"], "last_verified_state": "latest verification state"},\n'
        '  "action": {\n'
        '    "type": "batch|inspect_dir|read_file|search_text|glob|git_status|git_diff|git_log|run_tests|run_command|write_file|edit_file|edit_file_hunks|finish|send_message|ask_user|remember|wait",\n'
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
        '"edits": [{"old": "edit_file_hunks old text", "new": "replacement"}], '
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
        '    "edits": [{"old": "edit_file_hunks old text", "new": "replacement"}],\n'
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


def is_resident_loop_command(command):
    return is_resident_mew_loop_command(command)


def build_work_think_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Choose exactly one next action for this active coding work session.\n"
        "Treat guidance as the user's current instruction for this turn. If guidance asks for fresh inspection and read tools are available, use a targeted read action before finishing; do not finish solely because older notes or prior turns claim enough context. "
        "Fields named guidance_snapshot under prior turns or resume decisions are historical audit records, not current instructions. "
        "Treat the capabilities object as current and authoritative; if a read/write/verify root or command is allowed there, do not ask the user to pass the same flag again. "
        "Use prior tool_calls as your observation history. If you need more evidence, choose one narrow read tool. "
        "Use work_session.resume.active_memory as durable typed recall about the user, project, feedback, or references; treat it as relevant context, but verify project facts with tools before relying on them for code changes. If active_memory.compacted_for_prompt is true, memory bodies were intentionally omitted; use id/path/name/description as pointers and read only the narrow source you need. Do not use read_file on .mew/memory/private paths surfaced in active_memory; their excerpt is already present in the prompt and those files are sensitive. "
        "Use work_session.effort as operational pressure. If effort.pressure is high, avoid broad exploration and prefer finish, remember, or ask_user with a concise state summary and a concrete replan. If effort.pressure is medium, choose a narrow next action and refresh working_memory so the next reentry is not stale. "
        "If working_memory.target_paths lists likely files or directories for the next step, and one already names the likely file or directory, prefer a direct read_file on one of those target_paths before repeating same-surface search_text; otherwise prefer those paths before a broader project search, and keep that list short and current. "
        "If work_session.resume.target_path_cached_window_observations already names a recent read_file window for that target_path, prefer refreshing that direct cached window before repeating same-surface search_text to rediscover the file. "
        "If work_session.resume.plan_item_observations lists a first remaining plan item paired to a target path or cached window, prefer that resume-side observation before broader search_text or rediscovery, and prune completed working_memory.plan_items as the task advances. "
        "If work_session.resume.plan_item_observations[0].edit_ready is true and cached_windows already cover the current paired target paths, prefer one paired dry-run edit over another same-path reread on those cached paths. "
        "Drop a working_memory.target_paths entry once it is no longer needed for the next step instead of carrying stale paths forward. "
        "If the latest search_text already returned the same path/query with the line anchor you need, do not rerun that same search_text; switch to a narrow read_file on the anchored window instead. "
        "If work_session.resume.low_yield_observations lists repeated zero-match searches, do not keep searching that same path/pattern; use the suggested_next to switch to a targeted read, a single broader path, an edit from known context, or finish with a concrete replan. "
        "If work_session.resume.redundant_search_observations shows that the same successful search_text was already repeated on this surface, use its suggested_next read_file replacement instead of rerunning search_text again. "
        "If work_session.resume.adjacent_read_observations shows overlapping or near-adjacent read_file windows on the same path, use its suggested_next merged read instead of inching through more small reads. "
        "If work_session.resume.repair_anchor_observations lists source/test windows from a failed batch or repair loop, prefer those exact anchors before fresh same-surface search_text or broader rereads. "
        "Use work_session.resume.continuity as the reentry contract. If continuity.status is weak or broken, or continuity.missing is non-empty, treat continuity.recommendation as the first repair queue before side-effecting actions; prefer targeted reads, remember, or ask_user to repair missing memory, risk, next-action, approval, recovery, verifier, budget, decision, or user-pivot state. "
        "For code navigation, prefer search_text for symbols or option names before broad read_file; after search_text gives line numbers, use read_file with line_start and line_count to inspect only the relevant window. Explicit line_start/line_count reads auto-scale max_chars for edit preparation, so prefer one bridging line-window read over repeating the same span when a single-file edit needs a larger exact old-text window. If a handler definition is not in the current file but the symbol appears imported, search the broader project tree or allowed read root for that symbol instead of repeating same-file searches. "
        "If current guidance, recent windows, or the latest failure already name an exact line_start/line_count window, refresh that same targeted window instead of falling back to an offset read_file from the top of the file. "
        "If you need multiple independent read-only observations, prefer one batch action with up to five read-only tools. If work_session.recent_read_file_windows already contains the exact recent path/span or old text needed for edit preparation, reuse that recent window instead of issuing another same-span read_file. If a needed recent_read_file_windows entry is context_truncated, fall back to the matching read_file tool_calls result text before declaring that old text unrecoverable. "
        "If you already know the exact paired tests/** and src/mew/** edits, you may use one batch action with up to five write/edit tools; this paired-write constraint applies to code write batches under tests/** and src/mew/**. Docs-only single edit_file/write_file actions in other allowed write roots may be proposed directly when the target path is clear. For a code write batch, every write must be under tests/** or src/mew/**, and at least one test edit plus one source edit is required. Use at most one write/edit per file path in the batch; if the same file needs multiple disjoint hunks, prefer one edit_file_hunks action for that path instead of multiple same-path writes. If exact old text is already cached for those same-file hunks, do not return wait just because of the one-write-per-path rule; rewrite that file as one edit_file_hunks action and continue toward the reviewer-visible dry-run batch. If the full required write set would exceed five tools, do not propose a partial batch that drops sibling edits; choose a narrower complete slice or do one more narrow read to reduce the write set first. mew will force writes to dry-run previews and keep approval/verification gated. Do not mix reads with write batches. "
        "If you can make a small safe edit, use edit_file, edit_file_hunks, or write_file. For edit_file you must include exact old and new strings; for edit_file_hunks you must give one path plus a non-empty edits list of exact old/new pairs for disjoint hunks in that same file. If you are not sure of the exact old string, use work_session.recent_read_file_windows when available or read the smallest relevant file window first. Once a prior line-window read or recent_read_file_windows entry contains the exact old string, do not reread the full file solely to prepare edit_file or edit_file_hunks. Writes default to dry_run=true; set dry_run=false only when verification is configured. "
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
        "Do not use run_command to invoke resident mew loops or the printed Next CLI controls such as mew work, mew do, mew chat, or mew run; those controls are for a human operator outside the active session. "
        "Use finish when the task is done or when an investigation/recommendation task has a concrete conclusion. "
        "If work_session.resume.same_surface_audit.status indicates a sibling-surface audit is still needed after src/mew edits, do one narrow audit step or record why the sibling surface is already covered or out of scope before finish. "
        "For implementation tasks with allowed write roots, do not finish merely because the next edit is clear; if exact old/new text or file content is available, propose the dry-run edit_file/write_file action instead. "
        "When finishing after investigation, evaluation, or recommendation guidance, include the concrete conclusion in action.summary or action.reason so the user does not have to infer it from prior tool output. "
        "Include a compact working_memory object that restates your current hypothesis, "
        "next intended step, open questions, and latest verified state for future reentry; "
        "If more than one concrete step remains, keep working_memory.plan_items as a short checklist of up to 3 remaining steps and prune completed items as work is completed. "
        "Keep working_memory.open_questions limited to unanswered items and drop resolved questions once answered. "
        "keep it short and do not copy raw logs. "
        "For finish, set task_done=true only when the task itself should be marked done.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def build_work_write_ready_think_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Write-ready fast path is active.\n"
        "The active_work_todo already names the paired src/test slice to draft.\n"
        "Return the standard work JSON schema below and exactly one next action.\n"
        "Use write_ready_fast_path.cached_window_texts as the exact old text source for edit_file/edit_file_hunks.\n"
        "Keep the action inside active_work_todo.source.target_paths and allowed_roots.write.\n"
        "Prefer one paired dry-run batch under tests/** and src/mew/** now.\n"
        "If one file needs multiple hunks, use a single edit_file_hunks action for that path instead of returning wait for the one-write-per-path rule.\n"
        "Do not add read, search, glob, git, shell, or verification actions on this fast path.\n"
        "Do not broaden scope, roots, or the focused verify command.\n"
        "If you still cannot draft the dry-run batch, return wait with one exact blocker tied to the cached windows.\n"
        "Do not invent uncached old text and do not propose a partial sibling edit set.\n"
        f"Schema:\n{_work_action_schema_text()}\n\n"
        f"FocusedContext JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def build_work_write_ready_tiny_draft_prompt(context):
    return (
        "You are the THINK phase for mew work mode.\n"
        "Return only JSON. Do not use markdown.\n"
        "Write-ready tiny draft lane is active.\n"
        "Return exactly one patch artifact for the active paired src/test slice.\n"
        "Allowed kinds are patch_proposal or patch_blocker.\n"
        "Use only active_work_todo.source.target_paths and write_ready_fast_path.cached_window_texts.\n"
        "Stay inside allowed_roots.write and do not invent uncached old text.\n"
        "Do not return tool actions, read/search actions, shell commands, approvals, or verification steps.\n"
        "If one file needs multiple hunks, express them in one files[i].edits array.\n"
        "If drafting cannot proceed from the cached windows, return patch_blocker with one stable code and detail.\n"
        "Use cached_window_incomplete when the cached text exists but ends mid-block; use missing_exact_cached_window_texts when exact cached text is absent.\n"
        "Schema:\n"
        "{\n"
        '  "kind": "patch_proposal|patch_blocker",\n'
        '  "summary": "short reason",\n'
        '  "files": [{"path": "src/mew/file.py", "edits": [{"old": "exact old text", "new": "replacement text"}]}],\n'
        '  "code": "blocker code when kind=patch_blocker",\n'
        '  "detail": "why drafting cannot proceed"\n'
        "}\n\n"
        f"FocusedContext JSON:\n{json.dumps(context, ensure_ascii=False, separators=(',', ':'))}"
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
            if dropped_tool_count:
                return {
                    "type": "wait",
                    "reason": "write batch exceeds 5 tools; choose a narrower complete slice instead of dropping required sibling edits",
                }
            if saw_non_write_tool:
                return {
                    "type": "wait",
                    "reason": "write batch cannot mix read-only tools; use a separate read step before paired writes",
                }
            paired_reason = paired_write_batch_rejection_reason(normalized_tools)
            if paired_reason:
                return {"type": "wait", "reason": paired_reason}
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
        "edits",
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
    if action_type == "read_file":
        return bool(action.get("path"))
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


def paired_write_batch_rejection_reason(tools):
    write_tools = [dict(tool) for tool in tools or [] if (tool or {}).get("type") in WRITE_WORK_TOOLS]
    if len(write_tools) < 2:
        return "write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each"
    if not all(valid_paired_write_batch_sub_action(tool) for tool in write_tools):
        return "write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each"
    duplicates = duplicate_paired_write_batch_paths(write_tools)
    if duplicates:
        return (
            "write batch may include at most one write/edit per file path; "
            f"collapse same-file hunks into a single edit_file or edit_file_hunks for {duplicates[0]}"
        )
    tests_tools = [tool for tool in write_tools if _work_batch_path_is_tests(tool.get("path"))]
    source_tools = [tool for tool in write_tools if _work_batch_path_is_mew_source(tool.get("path"))]
    if not tests_tools or not source_tools or len(tests_tools) + len(source_tools) != len(write_tools):
        return "write batch is limited to write/edit tools under tests/** and src/mew/** with at least one of each"
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


def normalize_paired_write_batch_tools(tools):
    write_tools = [dict(tool) for tool in tools or [] if (tool or {}).get("type") in WRITE_WORK_TOOLS]
    if len(write_tools) < 2:
        return []
    if not all(valid_paired_write_batch_sub_action(tool) for tool in write_tools):
        return []
    if duplicate_paired_write_batch_paths(write_tools):
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
    think_prompt = (
        build_work_write_ready_think_prompt(write_ready_context)
        if write_ready_context
        else build_work_think_prompt(context)
    )
    think_prompt_static_chars = 0
    think_prompt_dynamic_chars = 0
    if write_ready_fast_path.get("active"):
        think_prompt_static_chars, think_prompt_dynamic_chars = _write_ready_draft_prompt_chars(think_prompt)
    think_timeout = (
        max(float(timeout), WORK_WRITE_READY_FAST_PATH_MODEL_TIMEOUT_SECONDS)
        if write_ready_context
        else float(timeout)
    )
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
        "reasoning_policy": reasoning_policy,
        "reasoning_effort": reasoning_policy.get("effort") or "",
        "prompt_context_mode": prompt_context_mode,
        "write_ready_fast_path": bool(write_ready_fast_path.get("active")),
        "write_ready_fast_path_reason": write_ready_fast_path.get("reason") or "",
    }
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
        return {
            "decision_plan": preflight_block.get("decision_plan") or {},
            "action_plan": preflight_block.get("action_plan") or {},
            "action": preflight_block.get("action") or {"type": "wait", "reason": "preflight blocker"},
            "context": context,
            "model_metrics": model_metrics,
            "model_stream": {"phases": [], "chunks": 0, "chars": 0},
        }
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
                "tiny_write_ready_draft_reasoning_effort": (
                    reasoning_policy.get("effort") or ""
                    if (reasoning_policy.get("source") or "auto") == "env_override"
                    else WORK_WRITE_READY_TINY_DRAFT_REASONING_EFFORT
                ),
                "tiny_write_ready_draft_reasoning_effort_source": (
                    "env_override"
                    if (reasoning_policy.get("source") or "auto") == "env_override"
                    else "tiny_draft_auto_override"
                ),
                "tiny_write_ready_draft_inherited_reasoning_effort": (
                    reasoning_policy.get("effort") or ""
                ),
                "tiny_write_ready_draft_inherited_reasoning_effort_source": (
                    reasoning_policy.get("source") or "auto"
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
            if progress:
                progress(f"session #{session.get('id')}: ACT ok action={action.get('type') or 'unknown'}")
            return {
                "decision_plan": tiny_result.get("decision_plan") or {},
                "action_plan": tiny_result.get("action_plan") or {},
                "action": action,
                "context": context,
                "model_metrics": model_metrics,
                "model_stream": compact_model_stream(stream_deltas),
            }
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
            return {
                "decision_plan": decision_plan,
                "action_plan": action_plan,
                "action": action,
                "context": context,
                "model_metrics": model_metrics,
                "model_stream": compact_model_stream(stream_deltas),
            }
        raise
    think_elapsed = time.monotonic() - think_started
    if progress:
        progress(f"session #{session.get('id')}: THINK ok")
    model_metrics["think"]["elapsed_seconds"] = _round_seconds(tiny_write_ready_elapsed + think_elapsed)
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
